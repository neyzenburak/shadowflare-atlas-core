"""Scale only the native player's kill EXP; leave the native level-up path intact."""
import atexit
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import struct
import threading
import time

from live_drop import Game, Code, ROOT, LOCK, GAME_MODE, Alloc, Free, Flush, check
from drop_event import remote_tick_count, GetTickCount, LEASE_MS
from trainer import GetExitCode
from grail_store import character_name

VERSION = 1
PLAN = json.loads((ROOT/'experience-plan.json').read_text('utf8'))
HOOK = PLAN['hook']
ORIGINAL = bytes.fromhex(PLAN['original'])
DATA = 0x800
SIZE = 4096
WORDS = 8  # in-flight, factor, heartbeat, awards, last raw, last awarded, reserved, reserved


def multiplier(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 1000:
        raise ValueError('EXP çarpanı 1–1000 arasında bir tam sayı olmalı.')
    return value


def verify(game, indices=(0,)):
    for i in indices:
        span = PLAN['verified'][i]
        if hashlib.sha256(game.read(span['address'], span['length'])).hexdigest() != span['sha256']:
            raise RuntimeError('Oyunun deneyim/seviye işlevi doğrulanamadı.')


def character(game=None):
    own = game is None
    try:
        if own:
            game = Game()
        state = game.state()
        p = state['player']
        level, = game.words(p+0x34)
        exp, = game.words(p+0xe8)
        if not 1 <= level <= 100:
            raise RuntimeError('Karakter seviyesi tanınmadı.')
        name = character_name(game.read(p+0x10, 12))
        binding = hashlib.sha256(repr((game.pid, p, name, level)).encode()).hexdigest()[:24]
        return dict(ready=True, pid=game.pid, player=p, name=name, level=level, exp=exp,
                    required=PLAN['levelRequirements'][level-1], binding=binding)
    finally:
        if own and game:
            game.close()


def character_info():
    try:
        return dict(version=VERSION, **character())
    except (OSError, ValueError, RuntimeError) as error:
        return dict(version=VERSION, ready=False, message=str(error))


def make_stub(base, tick):
    d = base+DATA
    c = Code(base).emit('9c 60 ff 05').u32(d)
    c.emit('ff 05').u32(d+12).emit('89 15').u32(d+16)  # raw gain EDX
    c.emit('83 3d').u32(GAME_MODE).emit('00').branch('0f 85', 'normal')
    c.call(tick).emit('2b 05').u32(d+8).emit('3d').u32(LEASE_MS).branch('0f 87', 'normal')
    c.emit('8b 1d').u32(d+4).emit('83 fb 01').branch('0f 86', 'normal')
    c.emit('81 fb e8 03 00 00').branch('0f 87', 'normal')
    c.emit('8b 44 24 14 f7 e3 85 d2').branch('0f 85', 'maximum')  # unsigned 64-bit raw*factor
    c.emit('03 44 24 1c').branch('0f 82', 'maximum')  # current EXP + scaled gain
    c.branch('e9', 'store')
    c.mark('maximum').emit('b8 ff ff ff ff')
    c.mark('store').emit('8b c8 2b 4c 24 1c 89 0d').u32(d+20)  # actual credited gain
    c.emit('89 44 24 1c 8b 5c 24 04 89 83 e8 00 00 00')
    c.emit('ff 0d').u32(d).emit('61 9d').branch('e9', HOOK+len(ORIGINAL))
    # With x1, expired lease, or multiplayer, replay the exact original instructions.
    c.mark('normal').emit('8b 44 24 14 a3').u32(d+20)
    c.emit('ff 0d').u32(d).emit('61 9d')
    c.data.extend(ORIGINAL)
    c.branch('e9', HOOK+len(ORIGINAL))
    raw = c.finish()
    assert len(raw) < DATA
    return raw


class ExperienceEvent:
    def __init__(self):
        self.game = None
        self.base = 0
        self.detour = None
        self.factor = 1
        self.message = ''
        self.counts = (0, 0, 0)
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.worker = None
        atexit.register(self.close)

    def start(self):
        with self.lock:
            if self.worker is None:
                self.worker = threading.Thread(target=self._follow, daemon=True)
                self.worker.start()

    def _alive(self):
        if self.game:
            result = W.DWORD()
            if not GetExitCode(self.game.h, C.byref(result)) or result.value != 259:
                self.game.close()
                self.game, self.base, self.detour = None, 0, None
                self.counts = (0, 0, 0)

    def info(self):
        with self.lock:
            self._alive()
            if self.game:
                try:
                    self.counts = self.game.words(self.base+DATA+12, 3)
                except OSError:
                    self.message = 'Deneyim sayacı okunamadı.'
            return dict(version=VERSION, active=bool(self.game and self.factor > 1),
                        multiplier=self.factor if self.game else 1, requested=self.factor,
                        awards=self.counts[0], lastRaw=self.counts[1], lastAwarded=self.counts[2],
                        pid=self.game.pid if self.game else None, message=self.message,
                        method='native-kill-experience', maxMultiplier=1000)

    def set(self, value):
        factor = multiplier(value)
        with self.lock:
            self._alive()
            if factor > 1 and not self.game:
                if not LOCK.acquire(False):
                    raise RuntimeError('Önceki oyun işleminin tamamlanmasını bekle.')
                try:
                    self._attach()
                finally:
                    LOCK.release()
            if self.game:
                if factor > 1:
                    self.game.state()
                self.game.write(self.base+DATA+4, struct.pack('<2I', factor, GetTickCount()))
            self.factor = factor
            self.message = ''
        self.start()
        return self.info()

    def _attach(self):
        game = Game(write=True)
        base = 0
        installed = False
        try:
            game.state()
            verify(game)
            if game.read(HOOK, len(ORIGINAL)) != ORIGINAL:
                raise RuntimeError('Deneyim ekleme noktasında başka bir yama var.')
            base = Alloc(game.h, None, SIZE, 0x3000, 0x40)
            check(base, 'Allocate experience event')
            raw = bytearray(SIZE)
            stub = make_stub(base, remote_tick_count(game))
            raw[:len(stub)] = stub
            struct.pack_into('<3I', raw, DATA, 0, 1, GetTickCount())
            game.write(base, bytes(raw))
            check(Flush(game.h, base, DATA), 'Flush experience event')
            detour = b'\xe9'+struct.pack('<i', base-HOOK-5)+b'\x90'*(len(ORIGINAL)-5)
            game.patch_at(HOOK, ORIGINAL, detour)
            installed = True
            self.game, self.base, self.detour = game, base, detour
        finally:
            if game is not self.game:
                if base and not installed:
                    Free(game.h, base, 0, 0x8000)
                game.close()

    def _follow(self):
        while not self.stop.wait(.6):
            with self.lock:
                try:
                    self._alive()
                    if self.game:
                        if self.game.read(HOOK, len(ORIGINAL)) != self.detour:
                            raise RuntimeError('Deneyim kancası değişmiş; çarpan uygulanmıyor.')
                        self.game.write(self.base+DATA+8, struct.pack('<I', GetTickCount()))
                    elif self.factor > 1 and LOCK.acquire(False):
                        try:
                            self._attach()
                            self.game.write(self.base+DATA+4, struct.pack('<2I', self.factor, GetTickCount()))
                        finally:
                            LOCK.release()
                except Exception as error:
                    self.message = str(error)

    def close(self):
        self.stop.set()
        if self.worker and self.worker is not threading.current_thread():
            self.worker.join(2)
        with self.lock:
            if not self.game:
                return
            game, base = self.game, self.base
            try:
                self._alive()
                if not self.game:
                    return
                game.write(base+DATA+4, struct.pack('<I', 1))
                game.patch_at(HOOK, self.detour, ORIGINAL)
                deadline = time.monotonic()+5
                while time.monotonic() < deadline:
                    with game.suspended() as handles:
                        safe = (game.words(base+DATA)[0] == 0 and
                                not any(base <= ip < base+SIZE for ip in game.ips(handles)))
                    if safe:
                        check(Free(game.h, base, 0, 0x8000), 'Free experience event')
                        break
                    time.sleep(.01)
            finally:
                game.close()
                self.game, self.base, self.detour = None, 0, None
