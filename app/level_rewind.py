"""Lower level/clear current EXP once on the game thread, preserving base stats."""
import hashlib
import json
import struct
import time

from live_drop import Game, Code, ROOT, LOCK, HOOK, ORIGINAL, GAME_MODE, Alloc, Free, Flush, check
from experience import character, verify
from native_save import save_current

DATA = 0x800
BEFORE = 0x900
AFTER = 0xa00
SIZE = 4096
STAT_OFFSET = 0x38
STAT_BYTES = 0x88
REFRESH = 0x450080
LEVEL_UP = 0x412fb0


def target_level(value, current):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value < current <= 100:
        raise ValueError('Hedef seviye 1 ile mevcut seviyenin bir eksiği arasında olmalı.')
    return value


def validate_controls(info):
    if {ident.removeprefix('ct:') for ident in info.get('frozen', ())} & {'975', '972'}:
        raise ValueError('Önce Trainer içindeki seviye ve EXP sabitlemelerini kapat.')
    if '2196' in {ident.removeprefix('ct:') for ident in info.get('active', ())}:
        raise ValueError('Önce Trainer içindeki tek yaratıkla seviye atlama seçeneğini kapat.')


def make_request(base, target, current):
    target_level(target, current)
    d = base+DATA
    c = Code(base).emit('9c 60 3b 0d').u32(d+4).branch('0f 85', 'exit')
    c.emit('b8').u32(1).emit('ba').u32(2).emit('f0 0f b1 15').u32(d).branch('0f 85', 'exit')
    c.emit('83 3d').u32(GAME_MODE).emit('00').branch('0f 85', 'fail')
    c.emit('8b e9 8b 81 58 04 00 00 3b 05').u32(d+8).branch('0f 85', 'fail')
    c.emit('83 b9 a4 01 00 00 00').branch('0f 8e', 'fail')
    c.emit('81 79 34').u32(current).branch('0f 85', 'fail')
    c.emit('8b 81 e8 00 00 00 a3').u32(d+12)
    c.emit('8d 71 38 bf').u32(base+BEFORE).emit('b9').u32(STAT_BYTES//4).emit('f3 a5')
    c.emit('c7 45 34').u32(target).emit('c7 85 e8 00 00 00').u32(0)
    c.emit('8b cd').branch('e8', REFRESH)
    c.emit('8d 75 38 bf').u32(base+AFTER).emit('b9').u32(STAT_BYTES//4).emit('f3 a5')
    c.emit('be').u32(base+BEFORE).emit('bf').u32(base+AFTER).emit('b9').u32(STAT_BYTES//4)
    c.emit('f3 a7').branch('0f 85', 'rollback')
    c.emit('c7 05').u32(d).u32(3).branch('e9', 'exit')
    c.mark('rollback').emit('be').u32(base+BEFORE).emit('8d 7d 38 b9').u32(STAT_BYTES//4).emit('f3 a5')
    c.emit('c7 45 34').u32(current).emit('a1').u32(d+12).emit('89 85 e8 00 00 00')
    c.emit('8b cd').branch('e8', REFRESH)
    c.emit('c7 05').u32(d).u32(5).branch('e9', 'exit')
    c.mark('fail').emit('c7 05').u32(d).u32(4)
    c.mark('exit').emit('61 9d')
    c.data.extend(ORIGINAL)
    c.branch('e9', HOOK+len(ORIGINAL))
    return c.finish()


def rewind(target, binding, trainer_info, timeout=30):
    validate_controls(trainer_info)
    current = character()
    target_level(target, current['level'])
    if not isinstance(binding, str) or binding != current['binding']:
        raise ValueError('Karakter veya seviye değişmiş. Durumu yenileyip tekrar dene.')
    # First persist and back up the actual current progress through the original writer.
    saved = save_current(timeout)
    if not LOCK.acquire(False):
        raise RuntimeError('Önceki oyun işleminin tamamlanmasını bekle.')
    game = None
    base = 0
    installed = False
    d = 0
    try:
        game = Game(write=True)
        state = game.state()
        if character(game)['binding'] != binding:
            raise ValueError('Kayıt sırasında karakter veya seviye değişmiş; seviye düşürülmedi.')
        verify(game, (1, 2, 3))
        if game.read(0x41368f, 2) != bytes.fromhex('72 42'):
            raise ValueError('Normal seviye atlama kontrolü değiştirilmiş; önce o yamayı kapat.')
        base = Alloc(game.h, None, SIZE, 0x3000, 0x40)
        check(base, 'Allocate level rewind')
        d = base+DATA
        image = bytearray(SIZE)
        stub = make_request(base, target, current['level'])
        image[:len(stub)] = stub
        struct.pack_into('<4I', image, DATA, 1, state['player'], state['map'], 0)
        game.write(base, bytes(image))
        check(Flush(game.h, base, DATA), 'Flush level rewind')
        detour = b'\xe9'+struct.pack('<i', base-HOOK-5)+b'\x90'
        game.patch(ORIGINAL, detour)
        installed = True
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            status = game.words(d)[0]
            if status in (3, 4, 5):
                break
            time.sleep(.025)
        game.patch(detour, ORIGINAL)
        installed = False
        for unused in range(500):
            with game.suspended() as handles:
                active = game.words(d)[0] == 2 or any(base <= ip < base+SIZE for ip in game.ips(handles))
            if not active:
                break
            time.sleep(.01)
        else:
            raise RuntimeError('Seviye isteği hâlâ çalışıyor; istek belleği korundu.')
        status = game.words(d)[0]
        if status == 5:
            raise RuntimeError('Stat farkı görüldü; önceki seviye ve statlar geri yüklendi.')
        if status != 3:
            raise RuntimeError('Seviye düşürülmedi; oyuna dönüp yeniden deneyebilirsin.')
        before = game.read(base+BEFORE, STAT_BYTES)
        after = game.read(base+AFTER, STAT_BYTES)
        if before != after:
            raise RuntimeError('Stat koruma doğrulaması başarısız.')
        result = dict(kind='level-rewind', name=current['name'], previousLevel=current['level'],
                      level=target, exp=0, statsPreserved=True, bonusMode='native-level-up',
                      backup=saved['backup'], saved=saved,
                      statsSHA256=hashlib.sha256(before).hexdigest(), hookRestored=True)
        folder = ROOT/'experience-sessions'
        folder.mkdir(exist_ok=True)
        (folder/f'{game.pid}-{time.time_ns()}-rewind.json').write_text(json.dumps(result, indent=2), 'utf8')
        return result
    finally:
        if game:
            if installed:
                try:
                    game.patch(detour, ORIGINAL)
                    installed = False
                except Exception:
                    pass
            if base and not installed:
                try:
                    with game.suspended() as handles:
                        safe = game.words(d)[0] != 2 and not any(base <= ip < base+SIZE for ip in game.ips(handles))
                    if safe:
                        Free(game.h, base, 0, 0x8000)
                except Exception:
                    pass
            game.close()
        LOCK.release()
