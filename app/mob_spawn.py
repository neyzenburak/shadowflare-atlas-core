"""Spawn one catalogue enemy on the game thread, with a private passive vtable.

Only the new instance uses our update method. Native damage, death, loot and
destruction stay intact. Its executable page lives until the game process exits.
"""
import hashlib
import json
from pathlib import Path
import re
import struct
import time

from live_drop import (Game, Code, ROOT, LOCK, HOOK, ORIGINAL, GAME_MODE,
                       Alloc, Free, Flush, check, backup_saves, catalogue)
from ctrl_teleport import ground_guard

VERSION = 4
PLAN = json.loads((ROOT/'mob-spawn-plan.json').read_text('utf8'))
TYPE = 20000000
IDLE = 0x100
VTABLE = 0x400
GROUND = 0x800
FLAGS = 0x600
DATA = 0xb00
CONFIG = 0xc00
RECT = 0xd20
NAME = 0xd40
CANDIDATES = 0xe40
ANIMATION = 0x1000
RESULTS = 0x1b00
IDS = 0x3b00
SIZE = 0x6000
BEHAVIOR_SIZE = 4096
SESSIONS = ROOT/'mob-spawn-sessions'


def selection(data, mob_id, variant):
    if any(isinstance(v, bool) or not isinstance(v, int) for v in (mob_id, variant)):
        raise ValueError('Yaratık ve varyant numarası tam sayı olmalı.')
    if not 0 <= mob_id < len(data['mobs']):raise ValueError('Bilinmeyen yaratık.')
    mob = data['mobs'][mob_id]
    if not 0 <= variant < len(mob['variants']):raise ValueError('Bilinmeyen yaratık varyantı.')
    v = mob['variants'][variant]
    if v['pattern'] < 0 or not v.get('sample'):raise ValueError('Bu varyantın doğurma verisi yok.')
    return mob, v


def spawn_quantity(value):
    if isinstance(value,bool) or not isinstance(value,int) or not 1<=value<=2000:
        raise ValueError('Yaratık adedi 1–2000 arasında bir tam sayı olmalı.')
    return value


def source_record(raw, sample):
    """Verify the original placement record, without inheriting its quest flags."""
    if raw[:15] != b'MCED DATA v0000':raise ValueError('Yaratık kaynak dosyası tanınmadı.')
    at = sample['file_offset']
    def take(n):
        nonlocal at
        if not 0 <= n <= len(raw) or not 16 <= at <= len(raw)-n:
            raise ValueError('Eksik yaratık kaydı.')
        result = raw[at:at+n];at += n;return result
    def words(n=1):return struct.unpack('<'+'i'*n, take(4*n))
    ident, pattern, length = words(3)
    if (ident, pattern) != (sample['identifier'], sample['pattern']) or not 0 <= length <= 255:
        raise ValueError('Yaratık kaynak kaydı Atlas ile eşleşmedi.')
    name = take(length).split(b'\0', 1)[0]
    tint = words()[0] if length else 0xe0e0e0
    height=words()[0];words(2)
    rect = words(4)
    direction, count = words(2)
    if not 0 <= count <= 10000:raise ValueError('Geçersiz yaratık koşulları.')
    take(count*4)
    animation = words()[0]
    parts = 0;colors = b''
    if animation == 1:
        count = words()[0]
        if not 0 <= count <= 256:raise ValueError('Geçersiz yaratık animasyonu.')
        parts = count;colors = take(count*10)
    elif animation != 0:raise ValueError('Bilinmeyen yaratık animasyon kaydı.')
    tail = words()[0]
    values = words(79)
    if list(values) != sample['values']:raise ValueError('Yaratık özellikleri Atlas ile eşleşmedi.')
    if not (rect[0] <= rect[2] and rect[1] <= rect[3]
            and all(abs(x) <= 10000 for x in rect)):
        raise ValueError('Yaratığın gövde ölçüleri desteklenmiyor.')
    return dict(rect=rect, name=name, tint=tint, tail=tail, values=values,
                parts=parts, colors=colors, height=height)


def native_config(values):
    if len(values) != 79:raise ValueError('Eksik yaratık özellikleri.')
    result = [values[i] if i is not None else 0 for i in PLAN['configMap']]
    if result[4] <= 0:raise ValueError('Yaratığın can değeri geçersiz.')
    return struct.pack('<72i', *result)


def candidate_offsets(rect, player_rect):
    distance = max(abs(x) for x in rect)+max(abs(x) for x in player_rect)+160
    distance = max(400, distance)
    directions = ((1,0),(1,1),(0,1),(-1,1),(-1,0),(-1,-1),(0,-1),(1,-1))
    return [(x*r*distance, y*r*distance) for r in (1,2,3,4) for x,y in directions]


def passive_image(base):
    # HP zero returns to the original death state machine, including loot.
    c = Code(base).emit('83 b9 d4 00 00 00 00').branch('0f 8e', 0x458f70)
    # +34c is the native out-of-range/inactive flag. Projectiles explicitly
    # reject it when set, even if the enemy is visible and targetable.
    c.emit('56 8b f1 c7 86 4c 03 00 00 00 00 00 00')
    c.emit('8b 4e 14 85 c9').branch('0f 84', 'sync')
    c.emit('83 79 04 00').branch('0f 85', 'loaded')
    c.emit('6a 00').branch('e8', 0x456080)
    c.mark('loaded').emit('83 be 38 03 00 00 00').branch('0f 8e', 'draw')
    c.emit('ff 8e 38 03 00 00')  # native hit flash ends normally
    c.mark('draw').emit('8b ce').branch('e8', base+IDLE)
    c.mark('sync').emit('8b ce').branch('e8', 0x459f60).emit('5e 33 c0 c3')
    code = c.finish();assert len(code) <= IDLE
    idle = PLAN['idle'];original = idle['address'];clone = bytearray.fromhex(idle['bytes'])
    for fix in idle['relocations']:
        target = fix['target']
        if original <= target < original+len(clone):target += base+IDLE-original
        struct.pack_into('<i', clone, fix['offset'], target-(base+IDLE+fix['end']))
    for offset in idle['suppressedCalls']:
        assert clone[offset] == 0xe8
        clone[offset:offset+5] = bytes.fromhex('83 c4 08 90 90')
    vtable = list(PLAN['vtable']);vtable[2] = base
    image = bytearray(BEHAVIOR_SIZE);image[:len(code)] = code
    image[IDLE:IDLE+len(clone)] = clone
    struct.pack_into('<10I', image, VTABLE, *vtable)
    return bytes(image)


def behavior_page(game):
    SESSIONS.mkdir(exist_ok=True)
    path = SESSIONS/f'{game.pid}-behavior.json'
    try:
        base = json.loads(path.read_text('utf8'))['base']
        if game.read(base, BEHAVIOR_SIZE) == passive_image(base):return base
    except (OSError, ValueError, KeyError, TypeError):pass
    base = Alloc(game.h, None, BEHAVIOR_SIZE, 0x3000, 0x40);check(base, 'Allocate passive enemy behavior')
    try:
        image = passive_image(base);game.write(base, image)
        check(Flush(game.h, base, BEHAVIOR_SIZE), 'Flush passive enemy behavior')
        path.write_text(json.dumps(dict(pid=game.pid, base=base, version=VERSION)), 'utf8')
        return base
    except Exception:
        Free(game.h, base, 0, 0x8000);raise


def upgrade_existing():
    """Update only our verified private callbacks; never touch native enemy AI."""
    if not LOCK.acquire(timeout=5):return {'message':'Oyun işlemi sürüyor.'}
    game = None
    report={'callbacks':0,'instances':0,'errors':[]}
    try:
        game = Game(write=True);path=SESSIONS/f'{game.pid}-spawns.jsonl'
        if not path.exists():return report
        records=[json.loads(line) for line in path.read_text('utf8').splitlines()]
        for base in {r['behavior'] for r in records}:
            expected=bytearray(passive_image(base)[:4096]);expected[22]=1
            try:
                if game.read(base,4096)==bytes(expected):
                    game.patch_at(base+22,b'\x01',b'\x00');report['callbacks']+=1
            except OSError as e:report['errors'].append(str(e));continue
        state=game.state();data=catalogue()
        for row in records:
            if row['map']!=state['map'] or row.get('version',1)>=3:continue
            mob,v=selection(data,row['mob'],row['variant']);sample=v['sample']
            source=game.path.parent/'Scenario'/sample['scenario']/'Scenario.Mct'
            record=source_record(source.read_bytes(),sample)
            with game.suspended():
                node=game.words(game.words(state['map']+0x30)[0]+8)[0];seen=set()
                while node and node not in seen:
                    seen.add(node);kind,cat,pointer,node=game.words(node,4)
                    if (kind==2 and pointer==row['pointer'] and game.words(pointer+4)[0]==row['identifier']
                            and game.words(pointer)[0]==row['behavior']+VTABLE):
                        game.write(pointer+0x34,struct.pack('<i',record['height']))
                        game.write(pointer+0xb8,struct.pack('<I',1));report['instances']+=1;break
        return report
    except (OSError,RuntimeError,ValueError,KeyError) as e:
        report['errors'].append(str(e));return report
    finally:
        if game:game.close()
        LOCK.release()


def insert_flag(base):
    """ECX=&count/array, EDX=key: add (key,1,0), preserving all live flags.

    The enemy-alive table and the three interaction flags use sorted native
    12-byte records. Allocate with the game's allocator so its destructor owns it.
    """
    c=Code(base).emit('55 53 56 57 51 52 8b e9 8b 59 04 8b 31')
    c.emit('81 fe').u32(100000).branch('0f 83','fail')
    c.emit('85 f6').branch('0f 84','allocate')
    c.emit('85 db').branch('0f 84','fail')
    c.emit('8b cb 8b c6').mark('existing').emit('39 11').branch('0f 84','success')
    c.emit('83 c1 0c 48').branch('0f 85','existing')
    c.mark('allocate').emit('8d 46 01 8d 04 40 c1 e0 02 50 6a 40 ff 15').u32(0x47305c)
    c.emit('85 c0').branch('0f 84','fail')
    c.emit('50 8b f8 8b cb 8b 55 00 8b 74 24 04 31 ed') # ESI=key, EDX=count
    c.mark('copy').emit('85 d2').branch('0f 84','append')
    c.emit('85 ed').branch('0f 85','old')
    c.emit('3b 31').branch('0f 8f','old')
    c.emit('89 37 c7 47 04 01 00 00 00 c7 47 08 00 00 00 00 83 c7 0c 45')
    c.mark('old')
    for offset in (0,4,8):c.emit('8b 41').emit(f'{offset:02x} 89 47 {offset:02x}')
    c.emit('83 c1 0c 83 c7 0c 4a').branch('e9','copy')
    c.mark('append').emit('85 ed').branch('0f 85','commit')
    c.emit('89 37 c7 47 04 01 00 00 00 c7 47 08 00 00 00 00')
    c.mark('commit').emit('58 8b 4c 24 04 89 41 04 ff 01 85 db').branch('0f 84','success')
    c.emit('53 ff 15').u32(0x473058)
    c.mark('success').emit('b8 01 00 00 00').branch('e9','done')
    c.mark('fail').emit('31 c0')
    c.mark('done').emit('83 c4 08 5f 5e 5b 5d c3')
    return c.finish()


def make_request(base, behavior, pattern, parts=0, legacy=None, height=0, quantity=1):
    quantity=spawn_quantity(quantity)
    d = base+DATA
    c = Code(base).emit('9c 60 3b 0d').u32(d+4).branch('0f 85', 'exit')
    c.emit('b8').u32(1).emit('ba').u32(2).emit('f0 0f b1 15').u32(d).branch('0f 85', 'exit')
    c.emit('fc')
    c.emit('8b f9 83 3d').u32(GAME_MODE).emit('00').branch('0f 85', 'fail')
    c.emit('83 bf a4 01 00 00 00').branch('0f 8e', 'fail')
    c.emit('8b 9f 58 04 00 00 3b 1d').u32(d+8).branch('0f 85', 'fail')
    # Only valid native AI-list indices may reach native damage/death helpers.
    c.emit('8b 0d').u32(0x48ce18).emit('85 c9').branch('0f 84', 'fail')
    c.emit('6a 00 ff 15').u32(0x473468).emit('85 c0').branch('0f 84', 'fail')
    c.emit('8b 0d').u32(0x48ce08).emit('85 c9').branch('0f 84', 'fail')
    c.emit('68').u32(pattern).emit('6a 02').branch('e8', 0x455ee0)
    c.emit('85 c0').branch('0f 84', 'fail')
    c.emit('83 78 0c 00').branch('0f 8e', 'fail')
    c.emit('a3').u32(d+40)
    # Check terrain and scenery before allocating/inserting an enemy.
    c.emit('be').u32(base+CANDIDATES).emit('bd').u32(32)
    c.mark('candidate').emit('8b 06 03 87 e0 02 00 00 a3').u32(d+16)
    c.emit('8b 46 04 03 87 e4 02 00 00 a3').u32(d+20)
    c.emit('8b 4b 3c 85 c9').branch('0f 84', 'fail')
    c.emit('ba').u32(d+16).emit('b8').u32(base+RECT).branch('e8', base+GROUND)
    c.emit('85 c0').branch('0f 84', 'next')
    c.emit('6a 00 6a 00 6a 00 68').u32(base+RECT).emit('68').u32(d+16)
    c.emit('6a ff 53 b9').u32(0x482df4).branch('e8', 0x4145b0)
    c.emit('83 f8 01').branch('0f 84', 'position')
    c.mark('next').emit('83 c6 08 4d').branch('0f 85', 'candidate')
    c.emit('c7 05').u32(d+44).u32(1).branch('e9', 'fail')
    c.mark('position').emit('8b 35').u32(d+40).emit('83 7e 04 00').branch('0f 85', 'resource')
    c.emit('6a 00 8b ce').branch('e8', 0x456080)
    c.mark('resource').emit('83 7e 04 00').branch('0f 84', 'fail')
    # The map's dynamic ID counter is shared with native dynamic spawns.
    c.mark('spawn_next').emit('8b 73 14 bd').u32(1024)
    c.mark('unique').emit('81 fe').u32(0x7ffffffe).branch('0f 83', 'fail')
    c.emit('56 8b 4b 30').branch('e8', 0x4299e0).emit('85 c0').branch('0f 84', 'insert')
    c.emit('46 4d').branch('0f 85', 'unique').branch('e9', 'fail')
    c.mark('insert').emit('89 35').u32(d+24).emit('8d 46 01 89 43 14')
    c.emit('56 68').u32(TYPE).emit('8b 4b 30').branch('e8', 0x4298c0)
    c.emit('85 c0').branch('0f 84', 'fail')
    c.emit('a3').u32(d+28).emit('8b 78 08 89 3d').u32(d+12)
    c.emit('68').u32(pattern).emit('6a 00 6a 00 68').u32(base+RECT)
    c.emit('68').u32(d+16).emit('68').u32(TYPE).emit('56 53 8b cf').branch('e8', 0x453aa0)
    # Abort and remove a partially initialized object before the next tick.
    for offset in (0x14,0x38,0x3c,0x40,0x44,0x48,0x58):
        c.emit('83 7f').emit(f'{offset:02x} 00').branch('0f 84', 'remove')
    c.emit('c7 47 34').u32(height)
    c.emit('c7 87 b8 00 00 00 01 00 00 00')
    for offset in (0x4c,0x50,0x54):c.emit('c7 47').emit(f'{offset:02x}').u32(1)
    # Appearance, solid body, targetability, and the native enemy-alive table.
    for namespace,offset in ((100000000,0x18),(200000000,0x18),(300000000,0x18),(0,8)):
        c.emit('8b 15').u32(d+24).emit('81 c2').u32(namespace)
        c.emit('8b 4b 58 83 c1').emit(f'{offset:02x}').branch('e8',base+FLAGS)
        c.emit('85 c0').branch('0f 84','remove')
    if parts:
        c.emit('81 7f 38').u32(parts).branch('0f 87','remove')
        c.emit('8b ef');source=base+ANIMATION
        for offset,width in ((0x3c,4),(0x40,2),(0x44,2),(0x48,2)):
            c.emit('be').u32(source).emit('8b 7d').emit(f'{offset:02x} 8b 4d 38 c1 e1').emit(f'{2 if width==4 else 1:02x} f3 a4')
            source+=parts*width
        c.emit('8b fd')
    c.emit('8b 05').u32(d+32).emit('89 87 bc 00 00 00')
    c.emit('8b 05').u32(d+36).emit('89 87 c0 00 00 00')
    c.emit('68').u32(base+CONFIG).emit('8b cf').branch('e8', 0x458f40)
    c.emit('68').u32(base+NAME).emit('8b cf').branch('e8', 0x454130)
    c.emit('c7 07').u32(behavior+VTABLE)
    c.emit('8b 05').u32(d+48).emit('89 3c 85').u32(base+RESULTS)
    c.emit('8b 15').u32(d+24).emit('89 14 85').u32(base+IDS)
    c.emit('40 a3').u32(d+48).emit('3d').u32(quantity).branch('0f 82','spawn_next')
    if legacy:
        ident,pointer,vtable=legacy
        c.emit('68').u32(ident).emit('8b 4b 30').branch('e8',0x4299e0)
        c.emit('85 c0').branch('0f 84','created')
        c.emit('81 78 08').u32(pointer).branch('0f 85','created')
        c.emit('81 3d').u32(pointer).u32(vtable).branch('0f 85','created')
        c.emit('50 8b 4b 30').branch('e8',0x429be0)
        c.mark('created')
    c.emit('c7 05').u32(d).u32(3).branch('e9', 'exit')
    c.mark('remove').emit('ff 35').u32(d+28).emit('8b 4b 30').branch('e8', 0x429be0)
    c.emit('c7 05').u32(d+12).u32(0)
    c.mark('fail').emit('c7 05').u32(d).u32(4)
    c.mark('exit').emit('61 9d').data.extend(ORIGINAL)
    c.branch('e9', HOOK+len(ORIGINAL))
    raw = c.finish();assert len(raw) < FLAGS
    return raw


def spawn(mob_id, variant=0, quantity=1, timeout=45):
    if not LOCK.acquire(False):raise RuntimeError('Önceki oyun işlemi hâlâ sürüyor.')
    game = None;base = 0;installed = False;d = 0
    try:
        quantity=spawn_quantity(quantity);mob, v = selection(catalogue(), mob_id, variant)
        game = Game(write=True);before = game.state()
        for f in PLAN['verified']:
            if hashlib.sha256(game.read(f['address'], f['size'])).hexdigest() != f['sha256']:
                raise RuntimeError('Yaratık oluşturma kodu beklenen sürümle eşleşmedi.')
        sample = v['sample'];scenario = sample['scenario']
        if not re.fullmatch('[0-9]{8}', scenario):raise ValueError('Geçersiz kaynak harita.')
        record = source_record((game.path.parent/'Scenario'/scenario/'Scenario.Mct').read_bytes(), sample)
        config = native_config(record['values'])
        offsets = candidate_offsets(record['rect'], struct.unpack('<4i', game.read(before['player']+0x2e8,16)))
        backup = backup_saves(game);behavior = behavior_page(game)
        legacy = None;old_log = SESSIONS/f'{game.pid}-spawns.jsonl'
        if old_log.exists():
            for line in old_log.read_text('utf8').splitlines():
                old = json.loads(line)
                if old.get('version',1)<2 and old['map']==before['map']:
                    legacy=(old['identifier'],old['pointer'],old['behavior']+VTABLE);break
        base = Alloc(game.h, None, SIZE, 0x3000, 0x40);check(base, 'Allocate enemy spawn request')
        d = base+DATA;stub = make_request(base, behavior, v['pattern'], record['parts'], legacy,
                                        record['height'],quantity)
        image = bytearray(SIZE);image[:len(stub)] = stub
        flags = insert_flag(base+FLAGS);image[FLAGS:FLAGS+len(flags)] = flags
        guard = ground_guard(base+GROUND);image[GROUND:GROUND+len(guard)] = guard
        struct.pack_into('<14I', image, DATA, 1, before['player'], before['map'], 0,0,0,0,0,
                         record['tint']&0xffffffff, record['tail']&0xffffffff,0,0,0,quantity)
        image[CONFIG:CONFIG+len(config)] = config
        struct.pack_into('<4i', image, RECT, *record['rect'])
        name = record['name'] or mob['name'].encode('cp932', errors='replace')[:255]
        image[NAME:NAME+len(name)+1] = name+b'\0'
        for i, xy in enumerate(offsets):struct.pack_into('<2i', image, CANDIDATES+i*8, *xy)
        image[ANIMATION:ANIMATION+len(record['colors'])] = record['colors']
        game.write(base, bytes(image));check(Flush(game.h, base, SIZE), 'Flush enemy spawn request')
        detour = b'\xe9'+struct.pack('<i', base-HOOK-5)+b'\x90'
        game.patch(ORIGINAL, detour);installed = True
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            status = game.words(d, 14)
            if status[0] in (3,4):break
            time.sleep(.025)
        game.patch(detour, ORIGINAL);installed = False
        for unused in range(500):
            with game.suspended() as handles:
                active = game.words(d)[0] == 2 or any(base <= ip < base+SIZE for ip in game.ips(handles))
            if not active:break
            time.sleep(.01)
        else:raise RuntimeError('Doğurma işlemi sürüyor; yeniden tıklamadan oyunu kontrol et.')
        status = game.words(d, 14)
        completed=status[12]
        if status[0] != 3 and not completed:
            if status[11] == 1:raise RuntimeError('Yakınında bu yaratığın sığabileceği boş, yürünebilir yer yok.')
            raise RuntimeError('Yaratık doğmadı. Oyuna dön; duraklatma menüsü kapalı olmalı.')
        pointers=game.words(base+RESULTS,completed)
        identifiers=game.words(base+IDS,completed)
        if not 1<=completed<=quantity or len(set(pointers))!=completed:
            raise RuntimeError('Doğurma adedi doğrulanamadı; tekrar deneme yapma.')
        pointer=pointers[-1]
        result = dict(status='success', kind='mob', version=VERSION, mob=mob_id, variant=variant, name=mob['name'],
                      pid=game.pid, map=before['map'], pointer=pointer, identifier=status[6],
                      x=struct.unpack('<i',struct.pack('<I',status[4]))[0],
                      y=struct.unpack('<i',struct.pack('<I',status[5]))[0],
                      pattern=v['pattern'], group=v['group'], noAI=True, quantity=completed,
                      requestedQuantity=quantity, partial=completed!=quantity,
                      behavior=behavior, backup=backup, hookRestored=game.read(HOOK,6)==ORIGINAL)
        with (SESSIONS/f'{game.pid}-spawns.jsonl').open('a',encoding='utf8') as f:
            for index,pointer in enumerate(pointers):
                f.write(json.dumps(dict(result,pointer=pointer,identifier=identifiers[index]),ensure_ascii=False)+'\n')
        return result
    finally:
        if game:
            if installed:
                try:game.patch(detour, ORIGINAL);installed = False
                except Exception:pass
            if base and not installed:
                try:
                    with game.suspended() as handles:
                        safe = game.words(d)[0] != 2 and not any(base <= ip < base+SIZE for ip in game.ips(handles))
                    if safe:Free(game.h, base, 0, 0x8000)
                except Exception:pass
            game.close()
        LOCK.release()


def inspect(detail=False):
    """Read live instances by map membership, never dereference a freed enemy."""
    game = Game()
    try:
        path = SESSIONS/f'{game.pid}-spawns.jsonl'
        records = [json.loads(line) for line in path.read_text('utf8').splitlines()] if path.exists() else []
        with game.suspended():
            state = game.state();manager = game.words(state['map']+0x30)[0]
            node = game.words(manager+8)[0];live = {};seen = set()
            while node and node not in seen and len(seen)<100000:
                seen.add(node);kind,cat,pointer,node = game.words(node,4)
                if kind == 2:live[game.words(pointer+4)[0]] = pointer
            out = []
            for record in records[-100:]:
                pointer = live.get(record['identifier']) if record['map']==state['map'] else None
                row = dict(record, present=pointer==record['pointer'])
                if row['present']:
                    row.update(position=struct.unpack('<2i',game.read(pointer+0x18,8)),
                               hp=game.words(pointer+0xd4)[0], action=game.words(pointer+0x1f4)[0],
                               frame=game.words(pointer+0x1e8)[0], vtable=game.words(pointer)[0])
                    if detail:row['raw']=game.read(pointer,0x350).hex()
                out.append(row)
            normal=[]
            if detail:
                spawned={r['pointer'] for r in records}
                for ident,pointer in live.items():
                    if pointer not in spawned and len(normal)<5:
                        normal.append(dict(identifier=ident,pointer=pointer,raw=game.read(pointer,0x350).hex()))
            return dict(pid=game.pid, instances=out,normal=normal)
    finally:game.close()
