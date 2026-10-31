"""Give local weapon projectiles the native Flame Strike steering parameters.

The original weapon volley, projectile template, damage, lifetime, collision
and target-loss handling remain in charge. Only a new projectile's steering
mode and turn rate change, before the native constructor copies the packet.
"""
import atexit
import hashlib
import json
import struct
import threading
import time

from live_drop import Game, Code, ROOT, LOCK, Alloc, Free, Flush, check, backup_saves, C, W
from hover_lifetime import GetExitCodeProcess

VERSION = 1
CALLSITE = 0x42a777
CREATE = 0x429dd0
ORIGINAL = bytes.fromhex('e854f6ffff')
DATA = 0x400
SIZE = 0x1000
SETTINGS = ROOT / 'homing-settings.json'
# Generated from the original, independently verified v2.004 executable.
VERIFIED = (
    (0x42a300, 0x540, '5625373c69e93c8843412e4c8414925e35da5801d2c50dc5290a55e0d1cd5d4d'),
    (0x429dd0, 0x69, '72f07fba82ac02fcd6d802b935bab57dc0413c640a94ba4c72b5809f812376c8'),
    (0x4299e0, 0x5b, '79d5574ebc9870a92d1780b382ed25f6bb5bc268533f0a3390b7d4f0f1c95c45'),
    (0x45e1a0, 0x3c, '9d709e4cf1372e97598b5517f048ff44be97e5b998904432e5e48d5d856f8359'),
    (0x45e1e0, 0x375, 'bbf0c3676a0b285127002f3016ac20949a97991e93ad21fd4ea36450e15adad0'),
    (0x42da20, 0x70, '7548363cf36c35b62097bd07b413ce2a94f028f44102669358a8521d68766010'),
    (0x438861, 0x99, 'c731e6e9aec560afa23acd9fdaef0ab56ee705265c3e91944a1b3d197d96e0e0'),
)


def make_stub(base):
    d = base + DATA
    c = Code(base)
    c.emit('9c 60 f0 ff 05').u32(d)  # preserve the complete native caller
    c.emit('83 3d').u32(d+4).emit('01').branch('0f 85', 'done')
    c.emit('83 3d').u32(0x482db0).emit('00').branch('0f 85', 'done')
    # This call site belongs to the small 0..7 weapon-effect dispatcher.
    # Its other case (10015) and spell dispatchers retain their own packets.
    c.emit('83 7b 0c 07').branch('0f 87', 'done')
    # The native double-shot path uses a fixed origin (0), other volleys use
    # the player's origin (1). Both retain the source player id at +0x14.
    c.emit('83 7b 10 01').branch('0f 87', 'done')
    c.emit('8b 0d').u32(0x48ce0c).emit('85 c9').branch('0f 84', 'done')
    c.emit('8b 01 85 c0').branch('0f 84', 'done')
    c.emit('83 f8 04').branch('0f 87', 'done')
    c.emit('8b 51 08 3b d0').branch('0f 83', 'done')
    c.emit('8b 41 04 85 c0').branch('0f 84', 'done')
    c.emit('8b 3c 90 85 ff').branch('0f 84', 'done')  # selected player
    c.emit('8b 47 04 3b 43 14').branch('0f 85', 'done')
    c.emit('83 bf a4 01 00 00 00').branch('0f 8e', 'done')
    c.emit('8b 87 58 04 00 00 3b 03').branch('0f 85', 'done')
    # No raw enemy pointer is retained: resolve the native stable entity id.
    c.emit('83 7b 18 01').branch('0f 84', 'no_target')
    c.emit('8b 43 1c 85 c0').branch('0f 88', 'no_target')
    c.emit('8b 0b 8b 49 30 85 c9').branch('0f 84', 'no_target')
    c.emit('50').call(0x4299e0)
    c.emit('85 c0').branch('0f 84', 'no_target')
    c.emit('83 38 02').branch('0f 85', 'no_target')  # living monster
    c.emit('8b 40 08 85 c0').branch('0f 84', 'no_target')
    c.emit('83 b8 d4 00 00 00 00').branch('0f 8e', 'no_target')
    # At entry: return address, template id, packet pointer. PUSHFD/PUSHAD
    # add 36 bytes. ESI = original packet; nothing else is rewritten.
    c.emit('8b 74 24 2c 85 f6').branch('0f 84', 'done')
    c.emit('c7 46 08').u32(1)   # native incremental tracking movement
    c.emit('c7 46 0c').u32(20)  # same turn rate as Flame Strike (0x42da24)
    c.emit('ff 05').u32(d+8).branch('e9', 'done')
    c.mark('no_target').emit('ff 05').u32(d+12)
    c.mark('done').emit('f0 ff 0d').u32(d).emit('61 9d')
    # Tail call preserves the original arguments and return address exactly.
    c.branch('e9', CREATE)
    raw = c.finish()
    assert len(raw) < DATA
    return raw


def snapshot():
    """Short, read-only sample of native weapon projectiles for validation."""
    game = Game()
    try:
        with game.suspended():
            state = game.state()
            player = state['player']
            owner = game.words(player+4)[0]
            manager = game.words(state['map']+0x30)[0]
            count, array = game.words(manager, 2)
            if count > 20000:
                raise RuntimeError('Haritadaki nesne listesi tanınmadı.')
            shots = []
            for block in game.words(array, count) if count else ():
                kind, _, obj = game.words(block, 3)
                if kind != 4 or not obj:
                    continue
                source_kind, source_id = game.words(obj+0xd0, 2)
                if source_kind > 1 or source_id != owner:
                    continue
                shots.append(dict(id=game.words(obj+4)[0], template=game.words(obj+0xc)[0],
                    xy=struct.unpack('<ii', game.read(obj+0x18, 8)),
                    mode=game.words(obj+0xd8)[0], turn=game.words(obj+0xdc)[0],
                    target=game.words(obj+0xe4)[0], tracking=game.words(obj+0xa9c)[0],
                    heading=struct.unpack('<d', game.read(obj+0x108, 8))[0]))
            weapon = game.words(player+0x4f4)[0]
            return dict(**state, shots=shots, weapon=game.words(weapon+0x14)[0] if weapon else None,
                        weaponMode=game.words(weapon+0x100)[0] if weapon else None)
    finally:
        game.close()


class HomingShots:
    def __init__(self):
        self.game = None
        self.base = 0
        self.detour = None
        self.requested = False
        self.counts = (0, 0)
        self.backup = None
        self.message = 'Güdümlü atış kapalı.'
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.worker = None
        try:
            self.requested = json.loads(SETTINGS.read_text('utf8')).get('enabled') is True
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        atexit.register(self.close)

    def start(self):
        with self.lock:
            if self.worker is None:
                self.worker = threading.Thread(target=self._follow, daemon=True)
                self.worker.start()

    def info(self):
        with self.lock:
            if self.game:
                try:
                    self.counts = self.game.words(self.base+DATA+8, 2)
                except OSError:
                    self.game.close()
                    self.game = None
                    self.base = 0
            return dict(version=VERSION, active=bool(self.game and self.requested),
                        requested=self.requested, converted=self.counts[0],
                        withoutTarget=self.counts[1], message=self.message,
                        pid=self.game.pid if self.game else None,
                        method='native-flame-strike-steering', backup=self.backup)

    def set(self, enabled):
        if not isinstance(enabled, bool):
            raise ValueError('Güdümlü atış için Aç veya Kapat seçilmeli.')
        with self.lock:
            SETTINGS.write_text(json.dumps({'enabled': enabled}, indent=2), 'utf8')
            self.requested = enabled
            if self.game:
                self.game.write(self.base+DATA+4, struct.pack('<I', enabled))
            self.message = ('Açık · hedeflediğin yaratığı oklar ve taşlar izler.'
                            if self.game and enabled else 'Oyun bağlantısı bekleniyor.'
                            if enabled else 'Güdümlü atış kapalı.')
        self.start()
        return self.info()

    def _follow(self):
        while not self.stop.wait(.6):
            with self.lock:
                try:
                    if self.game:
                        state = W.DWORD()
                        if not GetExitCodeProcess(self.game.h, C.byref(state)) or state.value != 259:
                            self.game.close()
                            self.game = None
                            self.base = 0
                            self.detour = None
                            self.counts = (0, 0)
                        elif self.game.read(CALLSITE, 5) != self.detour:
                            raise RuntimeError('Mermi oluşturma çağrısı başka bir yama tarafından değiştirildi.')
                    if self.requested and not self.game and LOCK.acquire(False):
                        try:
                            self._attach()
                        finally:
                            LOCK.release()
                except Exception as error:
                    self.message = str(error)

    def _attach(self):
        game = Game(write=True)
        base = 0
        installed = False
        try:
            game.state()
            if game.read(CALLSITE, 5) != ORIGINAL:
                raise RuntimeError('Silah mermisi oluşturma noktası tanınmadı.')
            for at, length, digest in VERIFIED:
                if hashlib.sha256(game.read(at, length)).hexdigest() != digest:
                    raise RuntimeError(f'Güdümlü atış işlevi tanınmadı: {at:08x}')
            self.backup = backup_saves(game)
            base = Alloc(game.h, None, SIZE, 0x3000, 0x40)
            check(base, 'Allocate homing weapon shots')
            raw = bytearray(SIZE)
            stub = make_stub(base)
            raw[:len(stub)] = stub
            struct.pack_into('<I', raw, DATA+4, int(self.requested))
            game.write(base, bytes(raw))
            check(Flush(game.h, base, DATA), 'Flush homing weapon shots')
            detour = b'\xe8'+struct.pack('<i', base-CALLSITE-5)
            game.patch_at(CALLSITE, ORIGINAL, detour)
            installed = True
            self.game, self.base, self.detour = game, base, detour
            folder = ROOT/'homing-sessions'
            folder.mkdir(exist_ok=True)
            (folder/f'{game.pid}-{time.time_ns()}.json').write_text(json.dumps(dict(
                pid=game.pid, base=base, version=VERSION, callsite=CALLSITE,
                before=ORIGINAL.hex(), after=detour.hex(),
                codeSHA256=hashlib.sha256(stub).hexdigest(), backup=self.backup,
                gameFileModified=False), indent=2), 'utf8')
            self.message = 'Açık · hedeflediğin yaratığı oklar ve taşlar izler.'
        finally:
            if game is not self.game:
                if base and not installed:
                    Free(game.h, base, 0, 0x8000)
                game.close()

    def close(self):
        self.stop.set()
        if self.worker and self.worker is not threading.current_thread():
            self.worker.join(2)
        with self.lock:
            if not self.game:
                return
            game, base = self.game, self.base
            try:
                game.write(base+DATA+4, b'\0'*4)
                game.patch_at(CALLSITE, self.detour, ORIGINAL)
                deadline = time.monotonic()+5
                while time.monotonic() < deadline:
                    with game.suspended() as handles:
                        safe = (game.words(base+DATA)[0] == 0 and
                                not any(base <= ip < base+SIZE for ip in game.ips(handles)))
                    if safe:
                        check(Free(game.h, base, 0, 0x8000), 'Free homing weapon shots')
                        break
                    time.sleep(.01)
            finally:
                game.close()
                self.game = None
                self.base = 0
                self.detour = None
