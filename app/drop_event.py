"""Repeat monster loot, exempt mines/gold, spread items on native walkable ground.

The monster callsite is separate from script rewards and the native gold roll.
The verified native function is copied with two local call substitutions. Only
bonus Mine/gold construction is skipped. Optional Premium-only mode constructs
each other bonus result once and destroys non-Premium results through the native
item bank; selection is never rerolled. The whole first native round is kept.
Each accepted item gets its own position. No global creation/position
hooks are installed. A hidden stack argument keeps separate death contexts.
Octagonal positions are traced against the live judge plane; a terrain obstacle
clips the ray to its last clear point without discarding the item or RNG roll.
"""
import atexit
import ctypes as C
from ctypes import wintypes as W
import json
import hashlib
import struct
import threading
import time
from live_drop import (Game,Code,ROOT,LOCK,K,api,check,Snapshot,CloseHandle,
                       Alloc,Free,Flush,GAME_MODE,backup_saves)
from placement_core import CORE as PLACEMENT_CORE
from grail_policy import make_lookup

CALLSITE=0x45a01c
NATIVE_DROP=0x417550
ORIGINAL_CALL=bytes.fromhex('e8 2f d5 fb ff')
MAX_MULTIPLIER=1000
VERSION=5
PREMIUM_ONLY_BIT=0x10000
EXCLUDE_FOUND_BIT=0x20000
SETTINGS=ROOT/'drop-event-settings.json'
LEASE_MS=5000
CLONE_OFFSET=0x200
CREATE_OFFSET=0x1000
POLICY_LOOKUP=0x1300
POLICY_SLOT=0xc30
ALLOC_SIZE=8192
POSITION_OFFSET=0x900
VERTEX_OFFSET=0xb00
EVENT_DATA=0xc00
PLACEMENT_OFFSET=0xd00
EVENT_WORDS=13
SPREAD_RADIUS=240
SPREAD_DIAGONAL=170
VERTICES=((240,0),(170,170),(0,240),(-170,170),(-240,0),(-170,-170),(0,-240),(170,-170))
DROP_PLAN=json.loads((ROOT/'drop-event-plan.json').read_text('utf-8'))
NATIVE_BYTES=bytes.fromhex(DROP_PLAN['bytes'])
GetTickCount=api('GetTickCount',W.DWORD,[])

def packed_options(multiplier,premium_only,exclude_found=False):
    if isinstance(multiplier,bool) or not isinstance(multiplier,int) or not 1<=multiplier<=MAX_MULTIPLIER:
        raise ValueError('Çarpan 1–1000 arasında tam sayı olmalı.')
    if not isinstance(premium_only,bool):raise ValueError('Premium seçimi aç/kapat olmalı.')
    if not isinstance(exclude_found,bool):raise ValueError('Grail filtresi aç/kapat olmalı.')
    return multiplier|(PREMIUM_ONLY_BIT if premium_only else 0)|(EXCLUDE_FOUND_BIT if exclude_found else 0)

class MODULEENTRY32W(C.Structure):
    _fields_=[(n,W.DWORD) for n in ('dwSize','th32ModuleID','th32ProcessID','GlblcntUsage','ProccntUsage')]+[
        ('modBaseAddr',C.c_void_p),('modBaseSize',W.DWORD),('hModule',W.HMODULE),
        ('szModule',W.WCHAR*256),('szExePath',W.WCHAR*260)]
ModuleFirst=api('Module32FirstW',W.BOOL,[W.HANDLE,C.POINTER(MODULEENTRY32W)])
ModuleNext=api('Module32NextW',W.BOOL,[W.HANDLE,C.POINTER(MODULEENTRY32W)])

def remote_export(game,module_name,symbol_name):
    """Resolve a 32-bit, already-loaded export, including forwarded exports."""
    h=Snapshot(0x18,game.pid)
    check(h not in (0,C.c_void_p(-1).value),'Snapshot game modules')
    modules={}
    try:
        e=MODULEENTRY32W();e.dwSize=C.sizeof(e);ok=ModuleFirst(h,C.byref(e))
        while ok:
            modules[e.szModule.lower()]=e.modBaseAddr
            ok=ModuleNext(h,C.byref(e))
    finally:CloseHandle(h)
    def resolve(module,symbol,depth=0):
        if depth>5:raise RuntimeError('Forwarded timer export loop')
        base=modules.get(module.lower())
        if not base:raise RuntimeError('Game timer module not loaded: '+module)
        nt=game.words(base+0x3c)[0]
        if game.read(base+nt,4)!=b'PE\0\0' or game.read(base+nt+24,2)!=b'\x0b\x01':
            raise RuntimeError('Expected a 32-bit game timer module')
        rva,size=game.words(base+nt+24+96,2)
        if not 40<=size<=0x1000000:raise RuntimeError('Invalid timer export directory')
        directory=game.read(base+rva,size)
        ordinal_base,function_count,name_count,functions,names,ordinals=struct.unpack_from('<6I',directory,16)
        if max(function_count,name_count)>100000:raise RuntimeError('Invalid timer export count')
        function_rvas=game.words(base+functions,function_count)
        name_rvas=game.words(base+names,name_count)
        ords=struct.unpack('<'+'H'*name_count,game.read(base+ordinals,name_count*2))
        def string_at(address):
            offset=address-rva
            if 0<=offset<len(directory):return directory[offset:].split(b'\0',1)[0].decode('ascii')
            raise RuntimeError('Timer export string outside directory')
        if symbol.startswith('#'):
            ordinal=int(symbol[1:])-ordinal_base
        else:
            ordinal=next((ords[i] for i,name in enumerate(name_rvas) if string_at(name)==symbol),None)
        if ordinal is None or not 0<=ordinal<len(function_rvas):raise RuntimeError('Game timer export not found')
        target=function_rvas[ordinal]
        if rva<=target<rva+size:
            forwarded=string_at(target);name,entry=forwarded.rsplit('.',1)
            return resolve(name+'.dll',entry,depth+1)
        return base+target
    return resolve(module_name,symbol_name)

def remote_tick_count(game):
    return remote_export(game,'kernel32.dll','GetTickCount')

def make_event_stub(base,data,timer):
    c=Code(base)
    c.emit('55 8b ec 83 ec 20 53 56 57') # 32-byte per-death context, saved registers
    c.emit('8b f9 8d 75 e0 33 c0 89 06 89 46 04 89 46 08 89 46 1c')
    # context: enabled, round, actual-item index, origin x/y, selected category/id
    c.emit('8b 45 10 89 46 0c 8b 45 14 89 46 10')
    c.emit('bb').u32(1)   # EDI = native this, ESI = context; EBX = normal round
    c.emit('f0 ff 05').u32(data+8) # in-flight covers calls outside this allocation
    c.emit('83 3d').u32(GAME_MODE).emit('00').branch('0f 85','loop')
    c.call(timer).emit('2b 05').u32(data+4).emit('3d').u32(LEASE_MS).branch('0f 87','loop')
    # Capture factor and Premium-only mode from one aligned DWORD. A setting
    # change cannot alter a death's already-captured bonus-round policy.
    c.emit('a1').u32(data).emit('8b d0 c1 ea 10 83 fa 03').branch('0f 87','loop')
    c.emit('25 ff ff 00 00 83 f8 01').branch('0f 8c','loop')
    c.emit('3d').u32(MAX_MULTIPLIER).branch('0f 87','loop')
    c.emit('83 f8 01').branch('0f 85','capture')
    c.emit('f7 c2 02 00 00 00').branch('0f 84','loop')
    c.mark('capture')
    c.emit('89 56 1c 8b d8 83 f8 01').branch('0f 84','captured')
    c.emit('c7 06').u32(1)
    c.mark('captured').emit('f0 ff 05').u32(data+12)
    c.mark('loop')
    c.emit('56') # hidden seventh argument; native argument positions remain unchanged
    for offset in (0x1c,0x18,0x14,0x10,0x0c,0x08):c.emit('ff 75').emit(f'{offset:02x}')
    c.emit('8b cf').call(base+CLONE_OFFSET).emit('83 c4 04')
    c.emit('f0 ff 05').u32(data+16) # original rounds actually completed
    c.emit('ff 46 04 4b').branch('0f 85','loop')
    c.emit('f0 ff 0d').u32(data+8)
    c.emit('5f 5e 5b 8b e5 5d c2 18 00')
    return c.finish()

def relocate_drop(base,create,position):
    raw=bytearray(NATIVE_BYTES);start=DROP_PLAN['address']
    for r in DROP_PLAN['relocations']:
        if 'absolute' in r:struct.pack_into('<I',raw,r['offset'],base+r['absolute']-start)
        else:struct.pack_into('<i',raw,r['offset'],r['target']-(base+r['end']))
    for site,target in ((DROP_PLAN['createCall'],create),(DROP_PLAN['positionCall'],position)):
        at=site-start;assert raw[at]==0xe8
        struct.pack_into('<i',raw,at+1,target-(base+at+5))
    return bytes(raw)

def make_create_filter(base,data,lookup):
    c=Code(base)
    # Native frame = 0x64 bytes, three arguments + return address = 0x10.
    # Seventh argument is entry ESP+0x1c, hence current ESP+0x90.
    c.emit('8b 94 24 90 00 00 00 8b 44 24 04 89 42 14 8b 44 24 08 89 42 18')
    c.emit('83 3a 00').branch('0f 84','ordinary')
    c.emit('83 7a 04 00').branch('0f 8e','ordinary')
    c.emit('83 7c 24 04 04').branch('0f 85','ordinary')
    c.emit('83 f8 01').branch('0f 84','mine')
    c.emit('83 f8 00').branch('0f 84','gold')
    c.mark('ordinary').emit('f7 42 1c 02 00 00 00').branch('0f 85','construct')
    c.emit('f7 42 1c 01 00 00 00').branch('0f 84','native')
    c.emit('83 3a 00').branch('0f 84','native')
    c.emit('83 7a 04 00').branch('0f 8f','construct')
    c.mark('native').branch('e9',0x462d30)
    c.mark('mine').emit('f0 ff 05').u32(data+24).emit('33 c0 c2 0c 00')
    c.mark('gold').emit('f0 ff 05').u32(data+28).emit('33 c0 c2 0c 00')
    # Construct once through the native factory, retaining all random stat
    # draws. Rejected bonus items never enter the map or occupy a loot slot.
    c.mark('construct').emit('56 57 8b f1 8b fa ff 74 24 14 ff 74 24 14 ff 74 24 14')
    c.branch('e8',0x462d30).emit('85 c0').branch('0f 84','return_item')
    c.emit('83 78 0c 02').branch('0f 87','non_premium')
    c.emit('83 78 18 02').branch('0f 85','non_premium')
    c.emit('f7 47 1c 02 00 00 00').branch('0f 84','accept_premium')
    c.emit('50 8b c8').branch('e8',lookup).emit('85 c0').branch('0f 84','unknown')
    c.emit('83 78 08 01').branch('0f 84','found')
    c.mark('unknown').emit('58').branch('e9','accept_premium')
    c.mark('found').emit('58 f0 ff 05').u32(data+44).branch('e9','destroy')
    c.mark('accept_premium').emit('83 3f 00').branch('0f 84','return_item')
    c.emit('83 7f 04 00').branch('0f 8e','return_item')
    c.emit('f0 ff 05').u32(data+40).branch('e9','return_item')
    c.mark('non_premium').emit('f7 47 1c 01 00 00 00').branch('0f 84','return_item')
    c.emit('83 3f 00').branch('0f 84','return_item')
    c.emit('83 7f 04 00').branch('0f 8e','return_item')
    c.emit('f0 ff 05').u32(data+36)
    c.mark('destroy').emit('50 8d 04 24 50 8b ce').branch('e8',0x465640)
    c.emit('83 c4 04 31 c0')
    c.mark('return_item').emit('5f 5e c2 0c 00')
    return c.finish()

def make_position_stub(base,data,vertices,placement):
    c=Code(base)
    # Two arguments instead of three: hidden context is at current ESP+0x8c.
    c.emit('8b 94 24 8c 00 00 00 83 3a 00').branch('0f 84','native')
    c.emit('83 7a 14 04').branch('0f 85','spread')
    c.emit('83 7a 18 01').branch('0f 84','native')
    c.emit('83 7a 18 00').branch('0f 84','native')
    c.mark('spread').emit('55 8b ec 53 56 57 8b f2 8b d9 8b 46 08 ff 46 08 bf').u32(1)
    c.mark('ring').emit('8b d7 c1 e2 03 3b c2').branch('0f 82','located')
    c.emit('2b c2 47').branch('e9','ring')
    c.mark('located').emit('33 d2 f7 f7 c1 e0 04') # edge/index and subdivision; 8*r slots/ring
    c.emit('8b 88').u32(vertices).emit('0f af cf 51')
    c.emit('8b 88').u32(vertices+8).emit('0f af ca 03 0c 24 03 4e 0c 89 0c 24')
    c.emit('8b 88').u32(vertices+4).emit('0f af cf 51')
    c.emit('8b 88').u32(vertices+12).emit('0f af ca 03 0c 24 03 4e 10')
    c.emit('58 58 51 50 8b ce').call(placement)
    c.emit('52 50 8b cb').call(0x4663e0)
    c.emit('f0 ff 05').u32(data+20).emit('5f 5e 5b 5d c2 08 00')
    c.mark('native').branch('e9',0x4663e0)
    return c.finish()

def make_placement_stub(data):
    return PLACEMENT_CORE.replace(bytes.fromhex('11111111'),struct.pack('<I',data+32))

def make_event_image(base,timer):
    data=base+EVENT_DATA
    table=b''.join(struct.pack('<4i',x,y,VERTICES[(i+1)%8][0]-x,VERTICES[(i+1)%8][1]-y) for i,(x,y) in enumerate(VERTICES))
    parts=[(0,make_event_stub(base,data,timer)),
           (CLONE_OFFSET,relocate_drop(base+CLONE_OFFSET,base+CREATE_OFFSET,base+POSITION_OFFSET)),
           (CREATE_OFFSET,make_create_filter(base+CREATE_OFFSET,data,base+POLICY_LOOKUP)),
           (POSITION_OFFSET,make_position_stub(base+POSITION_OFFSET,data,base+VERTEX_OFFSET,base+PLACEMENT_OFFSET)),
           (VERTEX_OFFSET,table),(PLACEMENT_OFFSET,make_placement_stub(data)),
           (POLICY_LOOKUP,make_lookup(base+POLICY_LOOKUP,base+POLICY_SLOT))]
    parts.sort(key=lambda part:part[0])
    for (offset,raw),(next_offset,_) in zip(parts,parts[1:]):assert offset+len(raw)<=next_offset
    assert parts[-1][0]+len(parts[-1][1])<=ALLOC_SIZE
    image=bytearray(parts[-1][0]+len(parts[-1][1]))
    for offset,raw in parts:image[offset:offset+len(raw)]=raw
    return bytes(image)

class DropEvent:
    def __init__(self,verified_reader=None,grail_policy=None):
        self.lock=threading.RLock();self.game=None;self.base=0;self.detour=None
        self.verified_reader=verified_reader
        self.grail_policy=grail_policy;self.exclude_found=False;self.duplicates_skipped=0
        self.factor=1;self.backup=None;self.message='Etkinlik kapalı. Normal drop: ×1.'
        self.premium_only=False;self.last_filter_counts=(0,0)
        try:
            settings=json.loads(SETTINGS.read_text('utf8'));self.premium_only=settings.get('premiumOnly') is True
            self.exclude_found=settings.get('excludeFound') is True
        except (OSError,ValueError,TypeError,AttributeError):pass
        self.last_counts=(0,0);self.last_layout_counts=(0,0,0);self.last_adjusted=0;self.stopping=threading.Event()
        self.worker=threading.Thread(target=self._heartbeat,daemon=True);self.worker.start()
        atexit.register(self.close)
    def _heartbeat(self):
        while not self.stopping.wait(.8):
            with self.lock:
                if not self.game:
                    if self.exclude_found:
                        try:self.set(1)
                        except Exception as error:self.message=str(error)
                    continue
                try:
                    self.game.write(self.base+0xc04,struct.pack('<I',GetTickCount()))
                    self.game.write(self.base+POLICY_SLOT,struct.pack('<I',self._policy()['address']))
                    if self.game.read(CALLSITE,5)!=self.detour:
                        self.message='Oyun bağlantısı değişti. Çarpanı yeniden başlatmadan önce oyunu kontrol et.'
                        self.game.close();self.game=None;self.factor=1
                except Exception:
                    self.message='Oyun kapandı veya bağlantı kesildi. Etkinlik sona erdi.'
                    self.game.close();self.game=None;self.factor=1
    def info(self):
        with self.lock:
            if self.game:
                try:
                    values=self.game.words(self.base+EVENT_DATA,EVENT_WORDS)
                    self.last_counts=(values[3],values[4])
                    self.last_layout_counts=tuple(values[5:8])
                    self.last_adjusted=values[8]
                    self.last_filter_counts=tuple(values[9:11])
                    self.duplicates_skipped=values[11]
                except Exception:pass
            policy=self._policy()
            return dict(supported=True,active=self.game is not None and self.factor>1,
                        multiplier=self.factor,maxMultiplier=MAX_MULTIPLIER,
                        monsterDrops=self.last_counts[0],nativeRounds=self.last_counts[1],
                        version=VERSION,premiumOnly=self.premium_only,layout='terrain-clipped-octagonal-rings',mineMultiplier=1,goldMultiplier=1,
                        bonusNonPremiumsSkipped=self.last_filter_counts[0],bonusPremiumsAccepted=self.last_filter_counts[1],
                        excludeFound=self.exclude_found,filterActive=bool(self.game and self.exclude_found),
                        duplicatesSkipped=self.duplicates_skipped,grailReady=policy['ready'],grailProfile=policy.get('profile'),foundKeys=policy['foundKeys'],
                        terrainAdjustedItems=self.last_adjusted,
                        spreadItems=self.last_layout_counts[0],bonusMinesSkipped=self.last_layout_counts[1],
                        bonusGoldSkipped=self.last_layout_counts[2],message=self.message,backup=self.backup)
    def _policy(self):
        return self.grail_policy(self.game.pid) if self.grail_policy and self.game else dict(address=0,ready=False,foundKeys=[])
    def set(self,multiplier,premium_only=None,exclude_found=None):
        mode=self.premium_only if premium_only is None else premium_only
        exclude=self.exclude_found if exclude_found is None else exclude_found
        options=packed_options(multiplier,mode,exclude)
        if not LOCK.acquire(False):raise RuntimeError('Önceki oyun işleminin tamamlanmasını bekle.')
        try:
            with self.lock:
                if multiplier==1 and not exclude:
                    self._disable();self.premium_only=mode;self.exclude_found=exclude;self._save_settings();return self.info()
                if self.game:
                    self.game.state() # still a living single-player character
                    self.game.write(self.base+EVENT_DATA,struct.pack('<2I',options,GetTickCount()))
                    self.factor=multiplier;self.premium_only=mode
                    self.exclude_found=exclude
                else:
                    game=Game(write=True);base=0;installed=False
                    try:
                        game.state()
                        if game.read(CALLSITE,5)!=ORIGINAL_CALL:raise RuntimeError('Düşman drop çağrısında başka bir yama var; üzerine yazılmadı.')
                        if game.read(NATIVE_DROP,len(NATIVE_BYTES))!=NATIVE_BYTES:raise RuntimeError('Özgün ganimet kodu değişmiş; üzerine yazılmadı.')
                        deleter=self.verified_reader(game,0x465640,0x5a) if self.verified_reader else game.read(0x465640,0x5a)
                        if hashlib.sha256(deleter).hexdigest()!='f3f55fe46435dce3f690df49aaf654fc73d2c784a24e2a6ca862c680ada8ca95':
                            raise RuntimeError('Özgün eşya kaldırma işlevi tanınmadı.')
                        for address,raw in ((0x473414,'8b5424048b4118'),(0x473420,'8b5424048b4128')):
                            expected=bytes.fromhex(raw)
                            if game.read(game.words(address)[0],len(expected))!=expected:raise RuntimeError('Zemin çarpışma tablosu tanınmadı.')
                        timer=remote_tick_count(game)
                        self.backup=backup_saves(game)
                        base=Alloc(game.h,None,ALLOC_SIZE,0x3000,0x40);check(base,'Allocate drop multiplier')
                        stub=make_event_image(base,timer)
                        game.write(base,stub);check(Flush(game.h,base,len(stub)),'Flush drop multiplier')
                        policy=self.grail_policy(game.pid) if self.grail_policy else dict(address=0)
                        game.write(base+EVENT_DATA,struct.pack('<13I',options,GetTickCount(),0,0,0,0,0,0,0,0,0,0,policy['address']))
                        detour=b'\xe8'+struct.pack('<i',base-CALLSITE-5)
                        game.patch_at(CALLSITE,ORIGINAL_CALL,detour);installed=True
                        self.game,self.base,self.detour,self.factor=game,base,detour,multiplier
                        self.premium_only=mode;self.exclude_found=exclude;self.last_filter_counts=(0,0);self.duplicates_skipped=0
                        self.last_counts=(0,0)
                        self.last_layout_counts=(0,0,0)
                        self.last_adjusted=0
                    except Exception:
                        if base and not installed:Free(game.h,base,0,0x8000)
                        game.close();raise
                self.message=f'Etkinlik açık: eşya turları ×{multiplier}; '+('ek turlarda yalnızca Premium. Normal tur korunur.' if mode else 'Mine ve altın ×1. Sekizgen dağıtım zemini kontrol eder.')
                if exclude:self.message+=' Bu karakterin bulduğu Premium sonuçlar normal tur dahil elenir.'
                self._save_settings()
                self._log('enabled')
                return self.info()
        finally:LOCK.release()
    def _save_settings(self):
        SETTINGS.write_text(json.dumps({'premiumOnly':self.premium_only,'excludeFound':self.exclude_found},indent=2),'utf8')
    def _disable(self):
        if not self.game:self.factor=1;self.message='Etkinlik kapalı. Normal drop: ×1.';return
        game=self.game;base=self.base;safe=False
        # An already-running drop finishes its captured round count.
        game.write(base+0xc00,struct.pack('<I',1))
        game.patch_at(CALLSITE,self.detour,ORIGINAL_CALL)
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            with game.suspended() as handles:
                values=game.words(base+EVENT_DATA,EVENT_WORDS)
                safe=values[2]==0 and not any(base<=ip<base+ALLOC_SIZE for ip in game.ips(handles))
                self.last_counts=(values[3],values[4])
                self.last_layout_counts=tuple(values[5:8])
                self.last_adjusted=values[8]
                self.last_filter_counts=tuple(values[9:11])
                self.duplicates_skipped=values[11]
            if safe:break
            time.sleep(.01)
        restored=game.read(CALLSITE,5)==ORIGINAL_CALL
        if safe:check(Free(game.h,base,0,0x8000),'Free drop multiplier')
        self.factor=1;self.message='Etkinlik kapalı. Oyunun özgün drop çağrısı geri yüklendi.'
        self._log('disabled',hookRestored=restored,temporaryMemoryFreed=safe)
        game.close();self.game=None;self.base=0;self.detour=None
        if not restored:raise RuntimeError('Drop çağrısının geri yüklendiği doğrulanamadı.')
    def _log(self,action,**extra):
        record=dict(time=time.strftime('%Y-%m-%d %H:%M:%S'),action=action,multiplier=self.factor,
                    premiumOnly=self.premium_only,bonusNonPremiumsSkipped=self.last_filter_counts[0],bonusPremiumsAccepted=self.last_filter_counts[1],
                    excludeFound=self.exclude_found,duplicatesSkipped=self.duplicates_skipped,
                    pid=self.game.pid if self.game else None,monsterDrops=self.last_counts[0],
                    nativeRounds=self.last_counts[1],spreadItems=self.last_layout_counts[0],
                    terrainAdjustedItems=self.last_adjusted,
                    bonusMinesSkipped=self.last_layout_counts[1],bonusGoldSkipped=self.last_layout_counts[2],**extra)
        with (ROOT/'drop-event-log.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(record)+'\n')
    def close(self):
        self.stopping.set()
        with self.lock:
            try:self._disable()
            except Exception:
                # Stop heartbeats even if a game process is already gone.
                if self.game:self.game.close();self.game=None
                self.factor=1
