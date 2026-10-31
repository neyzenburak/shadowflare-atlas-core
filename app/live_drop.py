"""One-item ShadowFlare v2.004 drop using the game's own main-thread functions.

No game/save file patching. A temporary six-byte entry detour is restored after
the request. The exact executable and original instruction bytes are checked.
Only the local single-player character can execute a request.
"""
from pathlib import Path
from contextlib import contextmanager
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
import struct
import time
import shutil
import threading

ROOT=Path(__file__).resolve().parent
DIST=ROOT/'dist' if (ROOT/'dist/data.js').exists() else ROOT
HOOK=0x443490
ORIGINAL=bytes.fromhex('83 ec 08 53 55 56')
PLAYER_LIST=0x48ce0c
ITEM_BANK=0x48ce14
GAME_MODE=0x482db0
CREATE_ITEM=0x462d30
SET_POSITION=0x4663e0
DROP_ITEM=0x452420
LOCK=threading.Lock()

def catalogue():
    text=(DIST/'data.js').read_text('utf-8')
    return json.loads(text.split('=',1)[1].strip().removesuffix(';'))

class Code:
    def __init__(self,base):self.base=base;self.data=bytearray();self.labels={};self.fixups=[]
    def emit(self,h):self.data.extend(bytes.fromhex(h));return self
    def u32(self,n):self.data.extend(struct.pack('<I',n&0xffffffff));return self
    def mark(self,name):self.labels[name]=len(self.data);return self
    def branch(self,op,name):self.emit(op);self.fixups.append((len(self.data),name));self.u32(0);return self
    def call(self,address):return self.emit('b8').u32(address).emit('ff d0')
    def finish(self):
        for at,name in self.fixups:
            target=self.labels[name]+self.base if isinstance(name,str) else name
            struct.pack_into('<i',self.data,at,target-(self.base+at+4))
        return bytes(self.data)

def spawn_quantity(category,value):
    if isinstance(value,bool) or not isinstance(value,int) or not 1<=value<=999:
        raise ValueError('Eşya adedi 1–999 arasında bir tam sayı olmalı.')
    if category!=3 and value!=1:raise ValueError('Yalnızca tüketilebilir eşyalar yığın olarak oluşturulabilir.')
    return value

def maximum_roll_fields(category,ident,enabled=False):
    """Explicit demo request: only the new eligible Magic item's random bonuses."""
    if not isinstance(enabled,bool):raise ValueError('Maksimum roll seçimi aç/kapat olmalı.')
    if not enabled:return ()
    from magic_beam_rules import RULES
    fields=next((stats for cat,item,stats in RULES if (cat,item)==(category,ident)),None)
    if fields is None:raise ValueError('Maksimum roll denemesi yalnızca mavi ışın adaylarında kullanılabilir.')
    return tuple((offset,maximum) for offset,threshold,maximum in fields)


def make_stub(base,data,category,ident,quantity=1,maximum_roll=False):
    quantity=spawn_quantity(category,quantity)
    fields=maximum_roll_fields(category,ident,maximum_roll)
    c=Code(base)
    c.emit('9c 60')                              # preserve caller flags/registers
    c.emit('3b 0d').u32(data+4).branch('0f 85','exit') # ECX must be local character
    c.emit('b8').u32(1).emit('ba').u32(2)
    c.emit('f0 0f b1 15').u32(data).branch('0f 85','exit') # pending -> executing once
    c.emit('8b f9')                              # EDI = character
    c.emit('83 3d').u32(GAME_MODE).emit('00').branch('0f 85','fail')
    c.emit('8b 87 58 04 00 00 3b 05').u32(data+8).branch('0f 85','fail')
    c.emit('83 bf a4 01 00 00 00').branch('0f 8e','fail') # living player only
    c.emit('8b 0d').u32(ITEM_BANK).emit('85 c9').branch('0f 84','fail')
    c.emit('6a 00 68').u32(ident).emit('68').u32(category).call(CREATE_ITEM)
    c.emit('a3').u32(data+12).emit('85 c0').branch('0f 84','fail')
    c.emit('8b f0')                              # ESI = newly constructed item
    if fields:
        c.emit('83 7e 18 01').branch('0f 85','fail')
        for offset,value in fields:c.emit('c7 86').u32(offset).u32(value)
    if quantity>1:c.emit('c7 46 1c').u32(0x53540000|quantity)
    c.emit('8b 87 e0 02 00 00 05 c8 00 00 00') # player position +0x2e0, adjacent +200
    c.emit('8b 97 e4 02 00 00')                  # player +0x2e4 (enemy layout differs)
    c.emit('a3').u32(data+16).emit('89 15').u32(data+20)
    c.emit('52 50 8b ce').call(SET_POSITION)
    c.emit('6a 00 ff 35').u32(data+8).emit('56 8b cf').call(DROP_ITEM)
    c.emit('a3').u32(data+24)
    c.emit('c7 05').u32(data).u32(3).branch('e9','exit')
    c.mark('fail').emit('c7 05').u32(data).u32(4)
    c.mark('exit').emit('61 9d').data.extend(ORIGINAL)
    c.branch('e9',HOOK+len(ORIGINAL))
    return c.finish()

class PROCESSENTRY32W(C.Structure):
    _fields_=[('dwSize',W.DWORD),('cntUsage',W.DWORD),('th32ProcessID',W.DWORD),
      ('th32DefaultHeapID',C.c_size_t),('th32ModuleID',W.DWORD),('cntThreads',W.DWORD),
      ('th32ParentProcessID',W.DWORD),('pcPriClassBase',W.LONG),('dwFlags',W.DWORD),('szExeFile',W.WCHAR*260)]
class THREADENTRY32(C.Structure):
    _fields_=[('dwSize',W.DWORD),('cntUsage',W.DWORD),('th32ThreadID',W.DWORD),
      ('th32OwnerProcessID',W.DWORD),('tpBasePri',W.LONG),('tpDeltaPri',W.LONG),('dwFlags',W.DWORD)]
class WOW64_FLOATING_SAVE_AREA(C.Structure):
    _fields_=[(n,W.DWORD) for n in ['ControlWord','StatusWord','TagWord','ErrorOffset','ErrorSelector','DataOffset','DataSelector']]+[('RegisterArea',C.c_byte*80),('Cr0NpxState',W.DWORD)]
class WOW64_CONTEXT(C.Structure):
    _fields_=[('ContextFlags',W.DWORD)]+[(n,W.DWORD) for n in ['Dr0','Dr1','Dr2','Dr3','Dr6','Dr7']]+[('FloatSave',WOW64_FLOATING_SAVE_AREA)]+[(n,W.DWORD) for n in ['SegGs','SegFs','SegEs','SegDs','Edi','Esi','Ebx','Edx','Ecx','Eax','Ebp','Eip','SegCs','EFlags','Esp','SegSs']]+[('ExtendedRegisters',C.c_byte*512)]

K=C.WinDLL('kernel32',use_last_error=True)
def api(name,restype,args):
    f=getattr(K,name);f.restype=restype;f.argtypes=args;return f
OpenProcess=api('OpenProcess',W.HANDLE,[W.DWORD,W.BOOL,W.DWORD])
CloseHandle=api('CloseHandle',W.BOOL,[W.HANDLE])
Snapshot=api('CreateToolhelp32Snapshot',W.HANDLE,[W.DWORD,W.DWORD])
ProcessFirst=api('Process32FirstW',W.BOOL,[W.HANDLE,C.POINTER(PROCESSENTRY32W)])
ProcessNext=api('Process32NextW',W.BOOL,[W.HANDLE,C.POINTER(PROCESSENTRY32W)])
ThreadFirst=api('Thread32First',W.BOOL,[W.HANDLE,C.POINTER(THREADENTRY32)])
ThreadNext=api('Thread32Next',W.BOOL,[W.HANDLE,C.POINTER(THREADENTRY32)])
OpenThread=api('OpenThread',W.HANDLE,[W.DWORD,W.BOOL,W.DWORD])
Suspend=api('SuspendThread',W.DWORD,[W.HANDLE])
Resume=api('ResumeThread',W.DWORD,[W.HANDLE])
GetContext=api('Wow64GetThreadContext' if C.sizeof(C.c_void_p)==8 else 'GetThreadContext',W.BOOL,[W.HANDLE,C.POINTER(WOW64_CONTEXT)])
ReadMemory=api('ReadProcessMemory',W.BOOL,[W.HANDLE,C.c_void_p,C.c_void_p,C.c_size_t,C.POINTER(C.c_size_t)])
WriteMemory=api('WriteProcessMemory',W.BOOL,[W.HANDLE,C.c_void_p,C.c_void_p,C.c_size_t,C.POINTER(C.c_size_t)])
Alloc=api('VirtualAllocEx',C.c_void_p,[W.HANDLE,C.c_void_p,C.c_size_t,W.DWORD,W.DWORD])
Free=api('VirtualFreeEx',W.BOOL,[W.HANDLE,C.c_void_p,C.c_size_t,W.DWORD])
Protect=api('VirtualProtectEx',W.BOOL,[W.HANDLE,C.c_void_p,C.c_size_t,W.DWORD,C.POINTER(W.DWORD)])
Flush=api('FlushInstructionCache',W.BOOL,[W.HANDLE,C.c_void_p,C.c_size_t])
ImageName=api('QueryFullProcessImageNameW',W.BOOL,[W.HANDLE,W.DWORD,W.LPWSTR,C.POINTER(W.DWORD)])

def check(ok,operation):
    if not ok:raise OSError(C.get_last_error(),operation)

def game_pids():
    h=Snapshot(2,0);check(h not in (0,C.c_void_p(-1).value),'Process snapshot')
    try:
        e=PROCESSENTRY32W();e.dwSize=C.sizeof(e);ok=ProcessFirst(h,C.byref(e));found=[]
        while ok:
            if e.szExeFile.lower()=='shadowflare.exe':found.append(e.th32ProcessID)
            ok=ProcessNext(h,C.byref(e))
        return found
    finally:CloseHandle(h)

class Game:
    def __init__(self,pid=None,write=False):
        pids=[pid] if pid else game_pids()
        if len(pids)!=1:raise RuntimeError('Tam olarak bir ShadowFlare oyunu açık olmalı.')
        self.pid=pids[0];self.h=OpenProcess(0x438 if write else 0x410,False,self.pid)
        if not self.h:
            if C.get_last_error()==5:raise PermissionError('Oyun yönetici yetkisiyle açık. Canlı drop yardımcısını yönetici olarak başlat.')
            raise C.WinError(C.get_last_error())
        self.path=self.image_path()
        expected=catalogue()['provenance']['exeSha256']
        if hashlib.sha256(self.path.read_bytes()).hexdigest()!=expected:
            self.close();raise RuntimeError('Bu çalıştırılabilir dosya doğrulanmış ShadowFlare v2.004 ile eşleşmiyor.')
        if self.read(HOOK,len(ORIGINAL))!=ORIGINAL:
            self.close();raise RuntimeError('Oyun kodu beklenen durumda değil; mevcut başka bir yamaya dokunulmadı.')
    def close(self):
        if self.h:CloseHandle(self.h);self.h=None
    def image_path(self):
        b=C.create_unicode_buffer(32768);n=W.DWORD(len(b));check(ImageName(self.h,0,b,C.byref(n)),'Game path');return Path(b.value)
    def read(self,a,n):
        b=C.create_string_buffer(n);got=C.c_size_t();check(ReadMemory(self.h,a,b,n,C.byref(got)),'Read game memory')
        if got.value!=n:raise RuntimeError('Incomplete memory read')
        return b.raw
    def words(self,a,n=1):return struct.unpack('<'+'I'*n,self.read(a,n*4))
    def write(self,a,b):
        got=C.c_size_t();check(WriteMemory(self.h,a,b,len(b),C.byref(got)),'Write game request')
        if got.value!=len(b):raise RuntimeError('Incomplete memory write')
    def state(self):
        if self.words(GAME_MODE)[0]!=0:raise RuntimeError('Canlı drop yalnızca tek oyunculu oyunda çalışır.')
        manager=self.words(PLAYER_LIST)[0]
        count,array,index=self.words(manager,3)
        if index>=count or count>4:raise RuntimeError('Karakter yüklenmiş değil; oyunun içine gir.')
        player=self.words(array+index*4)[0]
        map_ptr=self.words(player+0x458)[0]
        if not map_ptr or self.words(player+0x1a4)[0]==0:raise RuntimeError('Canlı bir karakter ve açık harita bekleniyor.')
        x,y=self.words(player+0x2e0,2)
        return dict(pid=self.pid,player=player,map=map_ptr,x=x,y=y)
    def threads(self):
        h=Snapshot(4,0);check(h not in (0,C.c_void_p(-1).value),'Thread snapshot')
        try:
            e=THREADENTRY32();e.dwSize=C.sizeof(e);ok=ThreadFirst(h,C.byref(e));ids=[]
            while ok:
                if e.th32OwnerProcessID==self.pid:ids.append(e.th32ThreadID)
                ok=ThreadNext(h,C.byref(e))
            return ids
        finally:CloseHandle(h)
    @contextmanager
    def suspended(self):
        handles=[]
        try:
            for tid in self.threads():
                h=OpenThread(0x4a,False,tid);check(h,'Open game thread')
                if Suspend(h)==0xffffffff:CloseHandle(h);raise C.WinError(C.get_last_error())
                handles.append(h)
            yield handles
        finally:
            for h in reversed(handles):Resume(h);CloseHandle(h)
    def ips(self,handles):
        out=[]
        for h in handles:
            ctx=WOW64_CONTEXT();ctx.ContextFlags=0x10001
            check(GetContext(h,C.byref(ctx)),'Read game thread context');out.append(ctx.Eip)
        return out
    def patch(self,expected,replacement):
        return self.patch_at(HOOK,expected,replacement)
    def patch_at(self,address,expected,replacement):
        if len(expected)!=len(replacement):raise ValueError('Patch lengths must match')
        for _ in range(100):
            with self.suspended() as handles:
                if any(address<ip<address+len(expected) for ip in self.ips(handles)):continue
                if self.read(address,len(expected))!=expected:raise RuntimeError('Hook changed; refusing to overwrite it.')
                old=W.DWORD();check(Protect(self.h,address,len(replacement),0x40,C.byref(old)),'Protect request entry')
                try:self.write(address,replacement);check(Flush(self.h,address,len(replacement)),'Flush game code')
                finally:
                    prev=W.DWORD();check(Protect(self.h,address,len(replacement),old.value,C.byref(prev)),'Restore game code protection')
                return
            time.sleep(.005)
        raise RuntimeError('Could not find a safe instruction boundary.')
    def ground_items(self,map_ptr):
        head=self.words(self.words(map_ptr+0x4c)[0])[0];seen=set();out=[]
        while head and head not in seen and len(out)<10000:
            seen.add(head);out.append(head);head=self.words(head+0x8c)[0]
        return out

def backup_saves(game):
    source=game.path.parent/'Save'
    dest=ROOT/'live-drop-backups'/(time.strftime('%Y%m%d-%H%M%S')+f'-{time.time_ns()%1000000000:09d}')
    dest.mkdir(parents=True,exist_ok=False)
    records=[]
    for p in source.iterdir():
        if p.is_file() and p.suffix.lower() in ('.ssv','.bmp'):
            raw=p.read_bytes();(dest/p.name).write_bytes(raw);records.append({'name':p.name,'sha256':hashlib.sha256(raw).hexdigest()})
    (dest/'manifest.json').write_text(json.dumps(records,indent=2),'utf-8')
    return str(dest)

def drop_one(key,pid=None,timeout=45,quantity=1,maximum_roll=False):
    if not LOCK.acquire(False):raise RuntimeError('Önceki drop isteği hâlâ sürüyor.')
    game=None;base=0;state_at=0;installed=False;detour=None;backup=None
    try:
        data=catalogue();item=next((i for i in data['items'] if i['key']==key),None)
        if not item:raise ValueError('Bilinmeyen eşya kaydı.')
        category,ident=map(int,key.split(':'));quantity=spawn_quantity(category,quantity)
        fields=maximum_roll_fields(category,ident,maximum_roll)
        game=Game(pid,write=True);before=game.state()
        backup=backup_saves(game)
        base=Alloc(game.h,None,4096,0x3000,0x40);check(base,'Allocate temporary drop request')
        state_at=base+0xc00
        stub=make_stub(base,state_at,category,ident,quantity,maximum_roll)
        game.write(base,stub)
        check(Flush(game.h,base,len(stub)),'Flush temporary request code')
        game.write(state_at,struct.pack('<8I',1,before['player'],before['map'],0,0,0,0,0))
        detour=b'\xe9'+struct.pack('<i',base-HOOK-5)+b'\x90'
        game.patch(ORIGINAL,detour);installed=True
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            status=game.words(state_at,8)
            if status[0] in (3,4):break
            time.sleep(.04)
        # Detach first; a request that has not entered cannot fire after timeout.
        game.patch(detour,ORIGINAL);installed=False
        for _ in range(250):
            with game.suspended() as handles:
                active=game.words(state_at)[0]==2 or any(base<=ip<base+len(stub) for ip in game.ips(handles))
            if not active:break
            time.sleep(.01)
        else:raise RuntimeError('Request still executing; temporary memory retained rather than freed.')
        status=game.words(state_at,8)
        if status[0]!=3:
            if status[3]:raise RuntimeError('Eşya oluşturuldu ancak son yerleştirme doğrulanamadı; yeniden deneme yapma.')
            raise RuntimeError('Drop gerçekleşmedi. Oyunun içine dön; duraklatma menüsü kapalı olmalı.')
        ptr=status[3]
        actual_id=game.words(ptr+0x14)[0]
        x,y=game.words(ptr+0x48,2)
        on_ground=ptr in game.ground_items(before['map'])
        if actual_id!=ident or not on_ground:raise RuntimeError('Native çağrı döndü, fakat yerdeki eşya doğrulanamadı. Tekrar istek gönderme.')
        if quantity>1 and game.words(ptr+0x1c)[0]!=(0x53540000|quantity):raise RuntimeError('Yığın oluşturuldu fakat adedi doğrulanamadı; tekrar deneme yapma.')
        if fields and any(game.words(ptr+offset)[0]!=value for offset,value in fields):raise RuntimeError('Deneme eşyasının roll değerleri doğrulanamadı; tekrar deneme yapma.')
        result=dict(status='success',key=key,name=item['name'],level=item['level'],pid=game.pid,
                    itemPointer=ptr,x=x,y=y,playerX=x-200,playerY=y,
                    onGround=True,quantity=quantity,maximumRoll=maximum_roll,hookRestored=game.read(HOOK,6)==ORIGINAL,backup=backup)
        log=ROOT/'live-drop-log.jsonl'
        with log.open('a',encoding='utf-8') as f:f.write(json.dumps(result,ensure_ascii=False)+'\n')
        return result
    finally:
        if game:
            if installed:
                try:game.patch(detour,ORIGINAL)
                except Exception:pass
            if base:
                try:
                    with game.suspended() as handles:safe=(not state_at or game.words(state_at)[0]!=2) and not any(base<=ip<base+4096 for ip in game.ips(handles))
                    if safe and not installed:Free(game.h,base,0,0x8000)
                except Exception:pass
            game.close()
        LOCK.release()

def status():
    game=None
    try:
        game=Game();s=game.state();return {'ready':True,**s}
    except Exception as e:return {'ready':False,'message':str(e),'needsAdmin':isinstance(e,PermissionError)}
    finally:
        if game:game.close()

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--spawn');parser.add_argument('--status',action='store_true');args=parser.parse_args()
    print(json.dumps(drop_one(args.spawn) if args.spawn else status(),ensure_ascii=True,indent=2))
