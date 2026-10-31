"""Resident 32-bit gold purses, with overflow-safe native capacity accounting."""
import atexit, hashlib, json, struct, threading, time
from live_drop import Game, Code, ROOT, LOCK, Alloc, Free, Flush, check, backup_saves, C, W
from hover_lifetime import GetExitCodeProcess

VERSION = 2
LIMIT = 0x7fffffff
SIZE = 4096

# Only gold handling is changed. Monster/death drop sizes remain original.
CONSTANTS = (
    (0x446d92, 10000, LIMIT), (0x446df3, -10000, -LIMIT), (0x446dfe, 10000, LIMIT),
    (0x446ec4, 10000, LIMIT), (0x446ef1, -10000, -LIMIT), (0x446f02, 10000, LIMIT),
    (0x447b78, 10000, LIMIT), (0x447be0, -10000, -LIMIT), (0x447beb, 10000, LIMIT),
    (0x447f62, 10000, LIMIT), (0x447fca, -10000, -LIMIT), (0x447fd5, 10000, LIMIT),
    (0x44a03b, 10000, LIMIT), (0x44a065, -10000, -LIMIT), (0x44a074, 10000, LIMIT),
    (0x466cee, 10000, LIMIT),
    # Native minimum-purse selection must also find a completely full purse.
    (0x466d16, 10001, 0x80000000),
    (0x466eaa, 10000, LIMIT), (0x466ebb, -10000, -LIMIT), (0x466ec2, 10000, LIMIT),
    (0x466f1b, 10000, LIMIT), (0x466f22, 10000, LIMIT), (0x466f2f, 10000, LIMIT),
)
HOOKS = ((0x466e31, 'ba102700002bd303f2', 0),
         (0x466e69, '81c610270000', 0x80),
         (0x466d70, '8b0933c085c9', 0x100))


def patches(base):
    result = [(a, struct.pack('<I', old & 0xffffffff), struct.pack('<I', new & 0xffffffff))
              for a, old, new in CONSTANTS]
    result.append((0x466d30, b'\x7d', b'\x73'))  # unsigned >= for 0x80000000 sentinel
    for at, old, offset in HOOKS:
        before = bytes.fromhex(old)
        after = b'\xe9'+struct.pack('<i', base+offset-at-5)+b'\x90'*(len(before)-5)
        result.append((at, before, after))
    return result


def make_image(base):
    raw = bytearray(SIZE)
    c = Code(base).emit('ba').u32(LIMIT).emit('2b d3 03 f2')
    c.branch('0f 81', 'done').emit('be').u32(LIMIT)
    c.mark('done').branch('e9', 0x466e3a)
    raw[:len(c.finish())] = c.finish()
    c = Code(base+0x80).emit('81 c6').u32(LIMIT)
    c.branch('0f 81', 'done').emit('be').u32(LIMIT)
    c.mark('done').branch('e9', 0x466e6f)
    raw[0x80:0x80+len(c.finish())] = c.finish()
    # The native API returns signed int. Saturate its aggregate, while retaining
    # every purse's full amount; spending still debits the actual linked list.
    # Detour the ENTRY, not the add's surrounding instructions: the original
    # loop branches into its mov-next instruction for all non-gold items.
    c = Code(base+0x100).emit('8b 09 33 c0 85 c9').branch('0f 84', 'done')
    c.emit('ba 04 00 00 00')
    c.mark('loop').emit('39 51 0c').branch('0f 85', 'next')
    c.emit('83 79 14 00').branch('0f 85', 'next')
    c.emit('03 41 40').branch('0f 81', 'next').emit('b8').u32(LIMIT)
    c.mark('next').emit('8b 89 8c 00 00 00 85 c9').branch('0f 85', 'loop')
    c.mark('done').emit('c3')
    raw[0x100:0x100+len(c.finish())] = c.finish()
    return bytes(raw)


def original_bytes(game, address, length, reader=None):
    """Normalize our known resident patches for other modules' hash checks."""
    raw = bytearray(reader(game, address, length) if reader else game.read(address, length))
    # The detour destination identifies the image; no process pointers are kept.
    detour = game.read(HOOKS[0][0], 5)
    if detour[:1] != b'\xe9':
        return bytes(raw)
    base = HOOKS[0][0]+5+struct.unpack('<i', detour[1:])[0]
    if game.read(base, 0x180) != make_image(base)[:0x180]:
        return bytes(raw)
    for at, before, after in patches(base):
        lo, hi = max(address, at), min(address+length, at+len(before))
        if lo < hi and game.read(at, len(after)) == after:
            raw[lo-address:hi-address] = before[lo-at:hi-at]
    return bytes(raw)


class GoldCapacity:
    def __init__(self):
        self.game = None
        self.base = 0
        self.backup = None
        self.message = 'Altın kesesi düzeltmesi oyun bağlantısını bekliyor.'
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.worker = None
        atexit.register(self.close)

    def start(self):
        with self.lock:
            if self.worker is None:
                self.worker = threading.Thread(target=self._follow, daemon=True)
                self.worker.start()

    def info(self):
        with self.lock:
            return dict(version=VERSION, active=bool(self.game), limit=LIMIT,
                        pid=self.game.pid if self.game else None,
                        message=self.message, backup=self.backup)

    def _follow(self):
        while not self.stop.wait(.6):
            with self.lock:
                try:
                    if self.game:
                        state = W.DWORD()
                        if not GetExitCodeProcess(self.game.h, C.byref(state)) or state.value != 259:
                            self.game.close(); self.game = None; self.base = 0
                        elif any(self.game.read(a, len(after)) != after for a, _, after in patches(self.base)):
                            raise RuntimeError('Altın kesesi yaması değiştirildi.')
                    if not self.game and LOCK.acquire(False):
                        try: self._attach()
                        finally: LOCK.release()
                except Exception as error:
                    self.message = str(error)

    def _attach(self):
        game = Game(write=True)
        base = 0
        installed = []
        try:
            game.state()
            folder = ROOT/'gold-sessions'
            folder.mkdir(exist_ok=True)
            for path in folder.glob(f'{game.pid}-*.json'):
                try:
                    meta = json.loads(path.read_text('utf8'))
                    candidate = meta['base']
                    if (meta.get('version') == VERSION and
                            game.read(candidate, SIZE) == make_image(candidate) and
                            all(game.read(a, len(after)) == after for a, _, after in patches(candidate))):
                        base = candidate; self.backup = meta.get('backup'); break
                except (OSError, ValueError, KeyError, TypeError):
                    continue
            if not base:
                for at, before, _ in patches(0x10000000):
                    if game.read(at, len(before)) != before:
                        raise RuntimeError(f'Altın işlevi tanınmadı: {at:08x}')
                self.backup = backup_saves(game)
                base = Alloc(game.h, None, SIZE, 0x3000, 0x40)
                check(base, 'Allocate gold capacity')
                raw = make_image(base)
                game.write(base, raw)
                check(Flush(game.h, base, SIZE), 'Flush gold capacity')
                # Persist adoption data before making game code visible. A disk
                # failure must not undo a patch after a large purse was created.
                (folder/f'{game.pid}-{time.time_ns()}.json').write_text(json.dumps(dict(
                    version=VERSION, pid=game.pid, base=base, backup=self.backup,
                    codeSHA256=hashlib.sha256(raw).hexdigest(), gameFileModified=False), indent=2), 'utf8')
                for _ in range(100):
                    with game.suspended() as handles:
                        if any(lo <= ip < hi for ip in game.ips(handles) for lo, hi in (
                                (0x446d00, 0x447250), (0x447a00, 0x448010),
                                (0x449ef0, 0x44a300), (0x4661c0, 0x466300),
                                (0x466cd0, 0x466f80))):
                            continue
                        for at, before, after in patches(base):
                            game.patch_at(at, before, after); installed.append((at, before, after))
                        break
                    time.sleep(.005)
                else:
                    raise RuntimeError('Altın işleminin bitmesi bekleniyor.')
            self.game, self.base = game, base
            self.message = 'Açık · altın kesesi başına 2.147.483.647.'
        finally:
            if game is not self.game:
                for at, before, after in reversed(installed):
                    game.patch_at(at, after, before)
                if base: Free(game.h, base, 0, 0x8000)
                game.close()

    def close(self):
        self.stop.set()
        if self.worker and self.worker is not threading.current_thread():
            self.worker.join(2)
        with self.lock:
            # Keep resident handlers: restoring a 10k merge against a larger
            # existing purse would damage it. Next helper adopts this image.
            if self.game: self.game.close()
            self.game = None
