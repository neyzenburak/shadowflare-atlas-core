"""Save the loaded character once through the original game-thread writer."""
import hashlib
import json
from pathlib import Path
import struct
import time

from live_drop import (Game,Code,ROOT,LOCK,HOOK,ORIGINAL,GAME_MODE,Alloc,Free,Flush,
                       check,backup_saves)
from grail_store import read_save,character_name

SAVE=0x44b580
SAVE_END=0x44cab5
SAVE_SHA='aa16c3a20b1686ae58d3ce68dbeaa505654422ee78919f4b96d91023f4fc3495'


def make_stub(base,data):
    c=Code(base).emit('9c 60 3b 0d').u32(data+4).branch('0f 85','exit')
    c.emit('b8').u32(1).emit('ba').u32(2).emit('f0 0f b1 15').u32(data).branch('0f 85','exit')
    c.emit('83 3d').u32(GAME_MODE).emit('00').branch('0f 85','fail')
    c.emit('8b 81 58 04 00 00 3b 05').u32(data+8).branch('0f 85','fail')
    c.emit('8b f9 8b 41 34 a3').u32(data+16)
    c.call(SAVE).emit('a3').u32(data+12)
    c.emit('c7 05').u32(data).u32(3).branch('e9','exit')
    c.mark('fail').emit('c7 05').u32(data).u32(4)
    c.mark('exit').emit('61 9d').data.extend(ORIGINAL)
    c.branch('e9',HOOK+len(ORIGINAL))
    return c.finish()


def save_current(timeout=30):
    if not LOCK.acquire(False):raise RuntimeError('Another game operation is running')
    game=None;base=0;installed=False;data=0
    try:
        game=Game(write=True);state=game.state();player=state['player']
        if hashlib.sha256(game.read(SAVE,SAVE_END-SAVE)).hexdigest()!=SAVE_SHA:
            raise RuntimeError('Original character-save function did not match')
        obj=game.words(0x482dcc)[0]
        pointer=game.words(obj)[0]
        filename=game.read(pointer,64).split(b'\0',1)[0].decode('ascii')
        if Path(filename).name.lower() not in {f'{n:04d}.ssv' for n in range(6)}:
            raise RuntimeError('Unknown native character save path')
        source=game.path.parent/filename
        old_backup=backup_saves(game)
        base=Alloc(game.h,None,4096,0x3000,0x40);check(base,'Allocate native save request')
        data=base+0xc00;stub=make_stub(base,data)
        game.write(base,stub);game.write(data,struct.pack('<8I',1,player,state['map'],0,0,0,0,0))
        check(Flush(game.h,base,len(stub)),'Flush save request')
        detour=b'\xe9'+struct.pack('<i',base-HOOK-5)+b'\x90'
        game.patch(ORIGINAL,detour);installed=True
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            status=game.words(data,8)
            if status[0] in (3,4):break
            time.sleep(.025)
        game.patch(detour,ORIGINAL);installed=False
        for unused in range(500):
            with game.suspended() as handles:
                active=game.words(data)[0]==2 or any(base<=ip<base+4096 for ip in game.ips(handles))
            if not active:break
            time.sleep(.01)
        else:raise RuntimeError('Save is still executing; request memory retained')
        status=game.words(data,8)
        if status[0]!=3 or status[3]!=1:raise RuntimeError('Native save did not complete; return to unpaused game')
        raw=source.read_bytes();parsed=read_save(raw)
        name=character_name(game.read(player+0x10,12))
        if parsed['name']!=name or parsed['level']!=status[4]:raise RuntimeError('Saved character identity did not match')
        backup=Path(backup_saves(game))
        # Keep exploration masks alongside the freshly verified character file.
        for p in source.parent.glob('*.msk'):(backup/p.name).write_bytes(p.read_bytes())
        result=dict(saved=True,pid=game.pid,player=player,name=name,level=parsed['level'],
                    file=str(source),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),
                    modified=source.stat().st_mtime,backup=str(backup),previousBackup=old_backup,
                    hookRestored=game.read(HOOK,len(ORIGINAL))==ORIGINAL)
        (backup/'save-verification.json').write_text(json.dumps(result,indent=2),'utf8')
        return result
    finally:
        if game:
            if installed:
                try:game.patch(detour,ORIGINAL);installed=False
                except Exception:pass
            if base and not installed:
                try:
                    with game.suspended() as handles:
                        safe=game.words(data)[0]!=2 and not any(base<=ip<base+4096 for ip in game.ips(handles))
                    if safe:Free(game.h,base,0,0x8000)
                except Exception:pass
            game.close()
        LOCK.release()
