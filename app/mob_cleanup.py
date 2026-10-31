"""Undo the last logged spawn batch on the game thread, without death or loot."""
import hashlib
import json
import struct
import time

from live_drop import Game,Code,ROOT,LOCK,HOOK,ORIGINAL,GAME_MODE,Alloc,Free,Flush,check,backup_saves
from mob_spawn import SESSIONS,VTABLE,TYPE,passive_image

SIZE=0x8000
DATA=0x800
RECORDS=0x1000
ERASE=0x400
VERIFIED=((0x4299e0,80,'be2b10fb6b42e1b895044b1b7e14b1cba2cf21c3bee57f2ab820326861fa647a'),
          (0x429be0,175,'33e6b1b5003611c84f9a1796661b88224577884eea2a188da811e2b13a0c0f5b'),
          (0x4297e0,187,'f542f76c1315d009c4bd24f12b02c68d0969729899edae9d72164029953ac179'))


def last_batch(records,pid,map_pointer):
    if not records:return []
    last=records[-1]
    if last['pid']!=pid or last['map']!=map_pointer:
        raise ValueError('Son doğurduğun grup şu anki haritada değil.')
    rows=[r for r in records if r['pid']==pid and r['map']==map_pointer and r['backup']==last['backup']]
    if not 1<=len(rows)<=2000:raise ValueError('Son doğurma grubunun kaydı doğrulanamadı.')
    if len({r['identifier'] for r in rows})!=len(rows):raise ValueError('Tekrarlanan yaratık kimliği.')
    return rows


def make_request(base,count):
    if not 1<=count<=2000:raise ValueError('Invalid cleanup size')
    d=base+DATA
    c=Code(base).emit('9c 60 3b 0d').u32(d+4).branch('0f 85','exit')
    c.emit('b8').u32(1).emit('ba').u32(2).emit('f0 0f b1 15').u32(d).branch('0f 85','exit')
    c.emit('fc 83 3d').u32(GAME_MODE).emit('00').branch('0f 85','fail')
    c.emit('8b 99 58 04 00 00 3b 1d').u32(d+8).branch('0f 85','fail')
    c.emit('be').u32(base+RECORDS).emit('bd').u32(count)
    c.mark('next').emit('ff 36 8b 4b 30').branch('e8',0x4299e0)
    c.emit('85 c0').branch('0f 84','missing')
    c.emit('83 38 02').branch('0f 85','skip')
    c.emit('81 78 04').u32(TYPE).branch('0f 85','skip')
    c.emit('8b 78 08 3b 7e 04').branch('0f 85','skip')
    c.emit('8b 17 3b 56 08').branch('0f 85','skip')
    c.emit('39 5f 5c').branch('0f 85','skip')
    c.emit('50 8b 4b 30').branch('e8',0x429be0)
    c.emit('ff 05').u32(d+12).branch('e9','flags')
    c.mark('missing').emit('ff 05').u32(d+16)
    c.mark('flags')
    for namespace,offset in ((100000000,0x18),(200000000,0x18),(300000000,0x18),(0,8)):
        c.emit('8b 16 81 c2').u32(namespace).emit('8b 4b 58 83 c1').emit(f'{offset:02x}')
        c.branch('e8',base+ERASE).emit('01 05').u32(d+20)
    c.branch('e9','advance')
    c.mark('skip').emit('ff 05').u32(d+16)
    c.mark('advance').emit('83 c6 0c 4d').branch('0f 85','next')
    c.emit('c7 05').u32(d).u32(3).branch('e9','exit')
    c.mark('fail').emit('c7 05').u32(d).u32(4)
    c.mark('exit').emit('61 9d').data.extend(ORIGINAL)
    c.branch('e9',HOOK+len(ORIGINAL))
    raw=c.finish();assert len(raw)<ERASE
    return raw


def erase_flag(base):
    """ECX=&count/array, EDX=key; erase only that 12-byte native record."""
    c=Code(base).emit('53 56 57 8b d9 8b 39 8b 73 04 85 ff').branch('0f 84','absent')
    c.emit('85 f6').branch('0f 84','absent').emit('8b cf 8b fe')
    c.mark('scan').emit('39 17').branch('0f 84','found')
    c.emit('83 c7 0c 49').branch('0f 85','scan')
    c.mark('absent').emit('31 c0').branch('e9','done')
    c.mark('found').emit('49 8d 0c 49 8d 77 0c f3 a5 ff 0b b8 01 00 00 00')
    c.mark('done').emit('5f 5e 5b c3')
    return c.finish()


def cleanup_last(timeout=180,batch=None):
    if not LOCK.acquire(False):raise RuntimeError('Önceki oyun işlemi sürüyor.')
    game=None;base=0;d=0;installed=False
    try:
        game=Game(write=True);state=game.state()
        for address,size,digest in VERIFIED:
            if hashlib.sha256(game.read(address,size)).hexdigest()!=digest:
                raise RuntimeError('Özgün yaratık temizleme kodu doğrulanamadı.')
        path=SESSIONS/f'{game.pid}-spawns.jsonl'
        records=[json.loads(line) for line in path.read_text('utf8').splitlines()]
        if batch is not None:
            if not isinstance(batch,str) or len(batch)>500:raise ValueError('Geçersiz doğurma grubu.')
            records=[r for r in records if r['backup']==batch]
            if not records:raise ValueError('Doğurma grubu bu oturumda bulunamadı.')
        rows=last_batch(records,game.pid,state['map'])
        if not rows:return dict(kind='mob-cleanup',removed=0,skipped=0)
        for address in {r['behavior'] for r in rows}:
            if game.read(address,4096)!=passive_image(address):
                raise RuntimeError('Doğurduğumuz yaratıkların pasif kodu doğrulanamadı.')
        backup=backup_saves(game)
        base=Alloc(game.h,None,SIZE,0x3000,0x40);check(base,'Allocate spawn undo request')
        d=base+DATA;stub=make_request(base,len(rows));image=bytearray(SIZE)
        image[:len(stub)]=stub
        erase=erase_flag(base+ERASE);image[ERASE:ERASE+len(erase)]=erase
        struct.pack_into('<6I',image,DATA,1,state['player'],state['map'],0,0,0)
        for i,row in enumerate(rows):
            struct.pack_into('<3I',image,RECORDS+12*i,row['identifier'],row['pointer'],row['behavior']+VTABLE)
        game.write(base,bytes(image));check(Flush(game.h,base,SIZE),'Flush spawn undo')
        detour=b'\xe9'+struct.pack('<i',base-HOOK-5)+b'\x90'
        game.patch(ORIGINAL,detour);installed=True
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            status=game.words(d,6)
            if status[0] in (3,4):break
            time.sleep(.05)
        game.patch(detour,ORIGINAL);installed=False
        for unused in range(500):
            with game.suspended() as handles:
                active=game.words(d)[0]==2 or any(base<=ip<base+SIZE for ip in game.ips(handles))
            if not active:break
            time.sleep(.01)
        else:raise RuntimeError('Temizleme hâlâ sürüyor; istek belleği korundu.')
        status=game.words(d,6)
        if status[0]!=3:raise RuntimeError('Temizleme oyun döngüsünde henüz çalışamadı.')
        result=dict(kind='mob-cleanup',pid=game.pid,map=state['map'],removed=status[3],skipped=status[4],
                    registryRemoved=status[5],requested=len(rows),batch=rows[-1]['backup'],backup=backup,
                    hookRestored=game.read(HOOK,6)==ORIGINAL)
        with (SESSIONS/f'{game.pid}-cleanup.jsonl').open('a',encoding='utf8') as f:f.write(json.dumps(result)+'\n')
        return result
    finally:
        if game:
            if installed:
                try:game.patch(detour,ORIGINAL);installed=False
                except Exception:pass
            if base and not installed:
                try:
                    with game.suspended() as handles:
                        safe=game.words(d)[0]!=2 and not any(base<=ip<base+SIZE for ip in game.ips(handles))
                    if safe:Free(game.h,base,0,0x8000)
                except Exception:pass
            game.close()
        LOCK.release()
