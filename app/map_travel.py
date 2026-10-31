"""Queue the original CHANGESCENARIO action; native code loads and places the player."""
import hashlib
import json
import struct
import time

from live_drop import Game, Code, ROOT, LOCK, HOOK, ORIGINAL, GAME_MODE, Alloc, Free, Flush, check
from grail_store import character_name
from operation_save import optional_save,save_choice

VERSION = 4
PLAN = json.loads((ROOT/'map-travel-plan.json').read_text('utf8'))
MAPS = {m['id']: m for m in PLAN['maps']}
DATA = 0x800
SIZE = 4096


def selection(sid):
    if not isinstance(sid, str) or sid not in MAPS:
        raise ValueError('Bu haritanın oynanabilir senaryosu ve doğrulanmış giriş noktası yok.')
    return MAPS[sid]


def points_from_mct(raw):
    """Parse entrance records, allowing translated text without guessing offsets."""
    cursor = 0

    def take(n):
        nonlocal cursor
        if n < 0 or cursor+n > len(raw):
            raise ValueError('Haritanın senaryo dosyası eksik veya bozuk.')
        result = raw[cursor:cursor+n]
        cursor += n
        return result

    def integer():
        return struct.unpack('<i', take(4))[0]

    def count():
        value = integer()
        if not 0 <= value < 100000:
            raise ValueError('Senaryodaki kayıt sayısı tanınmadı.')
        return value

    if take(16) != b'MCED DATA v0000\x1a':
        raise ValueError('Haritanın senaryo biçimi tanınmadı.')
    take(260+260+12+256)
    for _ in range(3):
        take(count()*4)
    for size in (52, 44, 316, 16):
        for _ in range(count()):
            take(8)
            length = count()
            take(length)
            if length:
                take(4)
            take(4+8+16+4)
            take(count()*4)
            if integer() == 1:
                take(count()*10)
            take(4+size)
    points = [list(struct.unpack('<4i', take(16))) for _ in range(count())]
    take(12)
    if cursor != len(raw):
        raise ValueError('Senaryo sonundaki giriş kayıtları doğrulanamadı.')
    return points


def verify(game):
    for span in PLAN['verified']:
        if hashlib.sha256(game.read(span['address'], span['length'])).hexdigest() != span['sha256']:
            raise RuntimeError('Oyunun özgün bölge geçişi işlevi doğrulanamadı.')


def identity(game):
    state = game.state()
    p = state['player']
    # World coordinates are signed; Game.state's generic DWORD snapshot is unsigned.
    state['x'], state['y'] = struct.unpack('<2i', game.read(p+0x2e0, 8))
    sid = f"{game.words(state['map']+4)[0]:08d}"
    slot = game.words(p+4)[0]
    if slot > 3:
        raise RuntimeError('Yerel oyuncunun giriş yuvası tanınmadı.')
    name = character_name(game.read(p+0x10, 12))
    binding = hashlib.sha256(repr((game.pid, p, name, sid)).encode()).hexdigest()[:24]
    return dict(**state, sid=sid, slot=slot, name=name, binding=binding)


def info():
    game = None
    try:
        game = Game()
        state = identity(game)
        p = state['player']
        pending = game.words(p+0x43c)[0] != 0 or game.words(0x482cd4)[0] != 0xffffffff
        holding = game.words(0x48ce34)[0] != 0
        story = game.words(0x48d778)[0] != 0xffffffff
        reason = ('Önce devam eden bölge geçişinin bitmesini bekle.' if pending else
                  'Önce elindeki eşyayı bir yuvaya bırak.' if holding else
                  'Önce hikâye ekranından oyuna dön.' if story else '')
        return dict(version=VERSION, ready=True, canTravel=not reason, binding=state['binding'],
                    currentMap=state['sid'], currentName=MAPS.get(state['sid'], {}).get('name', state['sid']),
                    name=state['name'], maps=len(MAPS), message=reason)
    except (OSError, ValueError, RuntimeError) as error:
        return dict(version=VERSION, ready=False, canTravel=False, message=str(error), maps=len(MAPS))
    finally:
        if game:
            game.close()


def validate_destination(game, target):
    folder = game.path.parent/'Scenario'/target['id']
    raw = (folder/'Scenario.Mct').read_bytes()
    if not (folder/'Scenario.Scs').is_file():
        raise ValueError('Hedef haritanın senaryo betiği bulunamadı.')
    # A translated file may have a different hash; the actual entrance records
    # must still match exactly. No text or script is executed by the helper.
    if hashlib.sha256(raw).hexdigest() != target['mctSHA256']:
        points = {row[0]: row for row in points_from_mct(raw)}
        if any(points.get(row[0]) != row for row in target['points']):
            raise ValueError('Hedef haritanın giriş noktaları kurulumla eşleşmiyor.')


def make_request(base, sid, entry):
    selection(sid)
    if entry != MAPS[sid]['entry']:
        raise ValueError('Senaryonun başlangıç girişi değiştirilmez.')
    d = base+DATA
    c = Code(base).emit('9c 60 3b 0d').u32(d+4).branch('0f 85', 'exit')
    c.emit('b8').u32(1).emit('ba').u32(2).emit('f0 0f b1 15').u32(d).branch('0f 85', 'exit')
    c.emit('83 3d').u32(GAME_MODE).emit('00').branch('0f 85', 'fail')
    c.emit('8b 81 58 04 00 00 3b 05').u32(d+8).branch('0f 85', 'fail')
    c.emit('83 b9 a4 01 00 00 00').branch('0f 8e', 'fail')
    c.emit('83 b9 3c 04 00 00 00').branch('0f 85', 'fail')
    c.emit('83 3d').u32(0x48ce34).emit('00').branch('0f 85', 'fail')
    c.emit('83 3d').u32(0x482cd4).emit('ff').branch('0f 85', 'fail')
    c.emit('83 3d').u32(0x48d778).emit('ff').branch('0f 85', 'fail')
    # Exactly the four fields written by native CHANGESCENARIO. Publish last.
    c.emit('c7 81 40 04 00 00').u32(int(sid, 10))
    c.emit('c7 81 44 04 00 00').u32(entry)
    c.emit('c7 81 54 04 00 00 ff ff ff ff')
    c.emit('c7 81 3c 04 00 00 01 00 00 00')
    c.emit('c7 05').u32(d).u32(3).branch('e9', 'exit')
    c.mark('fail').emit('c7 05').u32(d).u32(4)
    c.mark('exit').emit('61 9d')
    c.data.extend(ORIGINAL)
    c.branch('e9', HOOK+len(ORIGINAL))
    return c.finish()


def travel(sid, binding, timeout=45, save_before=False):
    save_choice(save_before)
    target = selection(sid)
    game = Game()
    try:
        state = identity(game)
        if not isinstance(binding, str) or binding != state['binding']:
            raise ValueError('Karakter veya bulunduğun harita değişmiş; durumu yenile.')
        verify(game)
        validate_destination(game, target)
    finally:
        game.close()
    saved = optional_save(save_before)
    if not LOCK.acquire(False):
        raise RuntimeError('Önceki oyun işleminin tamamlanmasını bekle.')
    game = None
    base = 0
    d = 0
    installed = False
    try:
        game = Game(write=True)
        state = identity(game)
        if state['binding'] != binding:
            raise ValueError('İstek hazırlanırken karakter veya harita değişmiş; ışınlanma uygulanmadı.')
        expected = target['points'][state['slot']]
        base = Alloc(game.h, None, SIZE, 0x3000, 0x40)
        check(base, 'Allocate map travel request')
        d = base+DATA
        image = bytearray(SIZE)
        stub = make_request(base, sid, target['entry'])
        image[:len(stub)] = stub
        struct.pack_into('<3I', image, DATA, 1, state['player'], state['map'])
        game.write(base, bytes(image))
        check(Flush(game.h, base, DATA), 'Flush map travel request')
        detour = b'\xe9'+struct.pack('<i', base-HOOK-5)+b'\x90'
        game.patch(ORIGINAL, detour)
        installed = True
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            status = game.words(d)[0]
            if status in (3, 4):
                break
            time.sleep(.025)
        game.patch(detour, ORIGINAL)
        installed = False
        if game.words(d)[0] != 3:
            raise RuntimeError('Geçiş başlamadı. Oyuna dön; elinde eşya ve başka geçiş isteği olmasın.')
        arrived = None
        while time.monotonic() < deadline:
            try:
                with game.suspended():
                    current = identity(game)
                    pending = game.words(current['player']+0x43c)[0]
                    if current['player'] != state['player'] or current['name'] != state['name']:
                        raise ValueError('Geçiş sırasında açık karakter değişti.')
                    if current['sid'] == sid and not pending:
                        arrived = current
                        break
            except (OSError, RuntimeError):
                pass  # Native loading temporarily replaces map objects and player lists.
            time.sleep(.05)
        if not arrived:
            raise RuntimeError('Geçiş oyuna iletildi, varış henüz doğrulanamadı. Tekrar basmadan önce oyunu kontrol et.')
        result = dict(kind='map-travel', name=target['name'], map=sid, previousMap=state['sid'],
                      entry=target['entry'], position=[arrived['x'], arrived['y']],
                      expectedPosition=expected[1:3], saved=saved or False, backup=saved['backup'] if saved else None,
                      entranceVerified=max(abs(arrived['x']-expected[1]),abs(arrived['y']-expected[2])) <= 500,
                      method='native-change-scenario', hookRestored=True)
        folder = ROOT/'map-travel-sessions'
        folder.mkdir(exist_ok=True)
        (folder/f'{game.pid}-{time.time_ns()}.json').write_text(json.dumps(result, indent=2), 'utf8')
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
                    for unused in range(500):
                        with game.suspended() as handles:
                            safe = game.words(d)[0] != 2 and not any(base <= ip < base+SIZE for ip in game.ips(handles))
                        if safe:
                            Free(game.h, base, 0, 0x8000)
                            break
                        time.sleep(.01)
                except Exception:
                    pass
            game.close()
        LOCK.release()
