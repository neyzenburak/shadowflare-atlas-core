"""Reversible, byte-verified UI corrections for ShadowFlare v2.004.

Complements the existing resolution patch. All changes live in the process;
original EXE, patterns, configurator and saves remain untouched.
"""
import json
import struct
import threading
import time
from pathlib import Path
from rain_fix import rain_wrapper, snapshot as rain_snapshot, patches as rain_patches, HOOK as RAIN_HOOK, ORIGINAL as RAIN_ORIGINAL
from live_drop import Game, Code, Alloc, Free, Flush, Protect, check, W, C, ROOT, LOCK, api

VERSION=8
PATCH_DATA=ROOT/'display-fix-plan.json'
IAT_PACKET=0x473564
IAT_STRINGS=0x47356c
IAT_RECT=0x473624
HUD_DRAW_RANGES=((0x403950,0x404aa0),(0x404ee0,0x4053c0))
ExitCode=api('GetExitCodeProcess',W.BOOL,[W.HANDLE,C.POINTER(W.DWORD)])
MODAL_INFLIGHT=0x3f00
RAIN_STATE=0x3f04
RESOLUTION_SETTLE_SECONDS=1.5
RIGHT_PACKET_RANGES=((0x404aa0,0x404c00),(0x406aa0,0x406c80),
                     (0x407522,0x40775c),(0x408a80,0x408cd3),(0x40f900,0x40f9e0))
RIGHT_TEXT_RANGES=((0x408a80,0x408cd3),)
RIGHT_ICON_RANGES=((0x407435,0x407436),(0x40750c,0x40750d),(0x4077ef,0x4077f0))
CENTER_RANGES=((0x40cea0,0x40d4d0),(0x40f9e0,0x410340),(0x4103c0,0x412220))

def jump(source,target,n=5):
    return b'\xe9'+struct.pack('<i',target-source-5)+b'\x90'*(n-5)

def filter_return(c,ranges,yes,no):
    """EAX is the original return address. Branch on exact caller ranges."""
    for i,(lo,hi) in enumerate(ranges):
        c.emit('3d').u32(lo).branch('0f 82',f'next{i}')
        c.emit('3d').u32(hi).branch('0f 82',yes)
        c.mark(f'next{i}')
    c.branch('e9',no)

def argument_stub(base,original,continuation,delta,args,ranges=None,center_delta=0,center_ranges=(),hud_y=None,hud_delta=(0,0)):
    c=Code(base).emit('9c 50')
    if hud_y is not None:
        c.emit('8b 44 24 08')
        for index,(lo,hi) in enumerate(HUD_DRAW_RANGES):
            c.emit('3d').u32(lo).branch('0f 82',f'hudNext{index}')
            c.emit('3d').u32(hi).branch('0f 82','hudShift').mark(f'hudNext{index}')
        c.branch('e9','normalShift').mark('hudShift')
        xarg=args[0][0]
        for arg,value in ((xarg,hud_delta[0]),(hud_y,hud_delta[1])):
            c.emit('81 44 24').emit(f'{8+arg*4:02x}').u32(value)
        # Packet flag 0x800 supplies an explicit destination extent.
        if xarg==7:
            c.emit('f7 44 24 20').u32(0x800).branch('0f 84','hudDone')
            for arg,value in ((9,hud_delta[0]),(10,hud_delta[1])):
                c.emit('81 44 24').emit(f'{8+arg*4:02x}').u32(value)
        c.mark('hudDone').branch('e9','done').mark('normalShift')
    if ranges:
        c.emit('8b 44 24 08');filter_return(c,ranges,'shift','centerCheck')
    c.mark('shift')
    for arg,optional in args:
        offset=8+arg*4
        if optional=='rect':
            c.emit('f7 44 24 20').u32(0x800).branch('0f 84',f'skip{arg}')
        elif optional:
            c.emit('83 7c 24').emit(f'{offset:02x} ff').branch('0f 84',f'skip{arg}')
        c.emit('81 44 24').emit(f'{offset:02x}').u32(delta)
        if optional:c.mark(f'skip{arg}')
    c.branch('e9','done').mark('centerCheck')
    # Use disjoint labels for the second caller classifier.
    for index,(lo,hi) in enumerate(center_ranges):
        c.emit('3d').u32(lo).branch('0f 82',f'centerNext{index}')
        c.emit('3d').u32(hi).branch('0f 82','centerShift')
        c.mark(f'centerNext{index}')
    c.branch('e9','done').mark('centerShift')
    for arg,optional in args:
        offset=8+arg*4
        if optional=='rect':c.emit('f7 44 24 20').u32(0x800).branch('0f 84',f'centerSkip{arg}')
        elif optional:c.emit('83 7c 24').emit(f'{offset:02x} ff').branch('0f 84',f'centerSkip{arg}')
        c.emit('81 44 24').emit(f'{offset:02x}').u32(center_delta)
        if optional:c.mark(f'centerSkip{arg}')
    c.mark('done').emit('58 9d')
    c.data.extend(original);c.branch('e9',continuation)
    return c.finish()

def packet_proxy(base,original,delta,arg,ranges,center_delta=0,center_ranges=(),native_viewport=False,bottom=0):
    args=[(arg,False)]+([(9,'rect')] if arg==7 else [])
    return argument_stub(base,b'',original,delta,args,ranges,center_delta,center_ranges,
                         (8 if arg==7 else 5)if native_viewport else None,(center_delta,bottom))


def hud_rect_proxy(base,target,dx,dy):
    c=Code(base).emit('9c 50 8b 44 24 08')
    filter_return(c,HUD_DRAW_RANGES,'translate','done')
    c.mark('translate')
    for arg,delta in ((2,dx),(3,dy),(4,dx),(5,dy)):
        c.emit('81 44 24').emit(f'{8+arg*4:02x}').u32(delta)
    c.mark('done').emit('58 9d').branch('e9',target)
    return c.finish()


def hud_input_wrapper(base,trampoline,dx,dy,inflight):
    c=Code(base).emit('55 8b ec 53 56 57 8b d9')
    c.emit('f0 ff 05').u32(inflight)
    c.emit('a1').u32(0x48ce0c).emit('8b 48 08 8b 40 04 8b 34 88 8b be fc 03 00 00')
    c.emit('ff 37 ff 77 04 81 2f').u32(dx).emit('81 6f 04').u32(dy)
    c.emit('8b cb').call(trampoline)
    c.emit('8f 47 04 8f 07 f0 ff 0d').u32(inflight)
    c.emit('5f 5e 5b 5d c3')
    return c.finish()

def cursor_wrapper(base,trampoline,delta,nargs,point_arg=None,inflight=None):
    """Temporarily use modal-local mouse X; restore before returning to world."""
    c=Code(base).emit('55 8b ec 53 56 57 8b f9')
    if inflight:c.emit('f0 ff 05').u32(inflight)
    c.emit('a1').u32(0x48ce0c).emit('8b 48 08 8b 40 04 8b 34 88')
    c.emit('8b b6 fc 03 00 00 8b 1e 81 2e').u32(delta)
    for arg in range(nargs,0,-1):
        c.emit('ff 75').emit(f'{4+arg*4:02x}')
    if point_arg:
        # The copied arguments, not the caller's originals, are normalized.
        c.emit('81 6c 24').emit(f'{(point_arg-1)*4:02x}').u32(delta)
    c.emit('8b cf').call(trampoline)
    c.emit('89 1e')
    if inflight:c.emit('f0 ff 0d').u32(inflight)
    c.emit('5f 5e 5b 5d c2').data.extend(struct.pack('<H',nargs*4))
    return c.finish()

def world_gate(base,width,height,panels=True):
    """Only the pixels actually occupied by visible UI block world clicks."""
    c=Code(base).emit('8b 4c 24 04 8b 54 24 08') # ECX=x, EDX=y
    c.emit('85 c9').branch('0f 88','blocked')
    c.emit('85 d2').branch('0f 88','blocked')
    c.emit('81 f9').u32(width).branch('0f 8d','blocked')
    c.emit('81 fa').u32(height).branch('0f 8d','blocked')
    dx=(width-640)//2;dy=height-480
    counter=0
    def rect(x0,y0,x1,y1):
        nonlocal counter
        label=f'outside{counter}';counter+=1
        for op,value,branch in [('81 f9',x0,'0f 8c'),('81 f9',x1,'0f 8d'),
                                ('81 fa',y0,'0f 8c'),('81 fa',y1,'0f 8d')]:
            c.emit(op).u32(value).branch(branch,label)
        c.branch('e9','blocked').mark(label)
    rect(dx,height-68,dx+640,height)
    rect(dx+589,height-78,dx+640,height-68)
    # Partner toggle and the spell icon protrude above the main HUD.
    rect(dx,height-82,dx+112,height-68)
    rect(dx+356,height-82,dx+388,height-68)
    for flag in ((0x48ce54,0x48ce58,0x48ce5c,0x48ce60,0x48ce6c) if panels else ()):
        c.emit('83 3d').u32(flag).emit('01').branch('0f 84','blocked')
    for flag in ((0x48ce3c,0x48ce68) if panels else ()):
        label=f'flag{flag:x}'
        c.emit('83 3d').u32(flag).emit('01').branch('0f 85',label)
        rect(width-320,0,width,416);c.mark(label)
    for flag in ((0x48ce38,0x48ce40,0x48ce44,0x48ce48,0x48ce4c,0x48ce50,0x48ce64) if panels else ()):
        label=f'flag{flag:x}'
        c.emit('83 3d').u32(flag).emit('01').branch('0f 85',label)
        rect(0,0,320,416);c.mark(label)
    c.emit('83 3d').u32(0x48ce9c).emit('02').branch('0f 85','allowed')
    rect(dx+301,dy+399,dx+340,dy+409)
    rect(dx+314,dy+393,dx+327,dy+399)
    c.mark('allowed').emit('b8 01 00 00 00 c2 08 00')
    c.mark('blocked').emit('31 c0 c2 08 00')
    return c.finish()

def build_changes(base,width,height,packet,strings,native_viewport=False,setrect=None):
    if not 640<=width<=7680 or not 480<=height<=4320:
        raise RuntimeError('Desteklenmeyen oyun boyutu.')
    plan=json.loads(PATCH_DATA.read_text('utf-8'));changes=[];chunks=[]
    right=width-640;hud=(width-640)//2;bottom=height-480
    def add(address,before,after,label):
        changes.append(dict(address=address,before=before.hex(),after=after.hex(),label=label))
    for entry in plan['immediates']:
        old=bytes.fromhex(entry['before']);new=bytearray(old)
        shift={'right':right,'hudX':hud,'hudY':bottom}[entry['anchor']]
        if entry.get('negative'):shift=-shift
        value=(entry['value']+shift)&0xffffffff
        new[entry['offset']:entry['offset']+entry['size']]=value.to_bytes(4,'little')[:entry['size']]
        add(entry['address'],old,bytes(new),entry['label'])
    pos=base
    def append(code):
        nonlocal pos
        start=pos;chunks.append((pos,code));pos=(pos+len(code)+15)&~15
        return start
    for address,name,args,ranges,delta in [
        (0x447290,'inventory slot hit test',[(1,False)],None,-right),
        (0x465cb0,'inventory icon',[(3,False),(5,True)],RIGHT_ICON_RANGES,right),
        (0x405590,'inventory numbers',[(4,False)],RIGHT_TEXT_RANGES,right)]:
        original=bytes.fromhex(plan['entries'][str(address)])
        center=CENTER_RANGES if address!=0x447290 else ()
        start=append(argument_stub(pos,original,address+len(original),delta,args,ranges,hud,center))
        add(address,original,jump(address,start,len(original)),name)
    for address,nargs,point_arg in ((0x40cea0,1,None),(0x40f9e0,5,2),(0x4103c0,5,2)):
        original=bytes.fromhex(plan['entries'][str(address)])
        trampoline=append(original+jump(pos+len(original),address+len(original)))
        start=append(cursor_wrapper(pos,trampoline,hud,nargs,point_arg,base+MODAL_INFLIGHT))
        add(address,original,jump(address,start,len(original)),'modal local input')
    original=bytes.fromhex(plan['entries'][str(0x445750)])
    start=append(world_gate(pos,width,height))
    add(0x445750,original,jump(0x445750,start,len(original)),'visible UI world gate')
    # The earlier right-button dispatcher has its own HUD test. The resolution
    # helper left its old Menu rectangle and a full-width bottom strip active.
    # Use the visible HUD geometry here too, without consuming panel close/use
    # clicks handled by the following native routines.
    gate=append(world_gate(pos,width,height,panels=False))
    code=Code(pos).emit('8b 89 fc 03 00 00 ff 71 04 ff 31').call(gate).emit('83 f0 01 c3').finish()
    start=append(code);original=bytes.fromhex(plan['entries'][str(0x44a9b0)])
    add(0x44a9b0,original,jump(0x44a9b0,start,len(original)),'visible HUD right-click gate')
    for iat,target,arg,ranges,name in ((IAT_PACKET,packet,7,RIGHT_PACKET_RANGES,'inventory sprites'),
                                      (IAT_STRINGS,strings,4,RIGHT_TEXT_RANGES,'inventory labels')):
        start=append(packet_proxy(pos,target,right,arg,ranges,hud,CENTER_RANGES,native_viewport,bottom))
        add(iat,struct.pack('<I',target),struct.pack('<I',start),name)
    if native_viewport:
        if setrect is None:raise ValueError('Native SetRect export is required')
        start=append(hud_rect_proxy(pos,setrect,hud,bottom))
        add(IAT_RECT,struct.pack('<I',setrect),struct.pack('<I',start),'HUD clipping coordinates')
        native=json.loads((ROOT/'viewport-plan.json').read_text('utf8'))
        for address in (0x445bd0,0x447570):
            original=bytes.fromhex(native['entries'][str(address)])
            trampoline=append(original+jump(pos+len(original),address+len(original)))
            start=append(hud_input_wrapper(pos,trampoline,hud,bottom,base+MODAL_INFLIGHT))
            add(address,original,jump(address,start,len(original)),'HUD local mouse coordinates')
    trampoline=append(RAIN_ORIGINAL+jump(pos+len(RAIN_ORIGINAL),RAIN_HOOK+len(RAIN_ORIGINAL)))
    start=append(rain_wrapper(pos,trampoline,base+RAIN_STATE,width,height))
    add(RAIN_HOOK,RAIN_ORIGINAL,jump(RAIN_HOOK,start,len(RAIN_ORIGINAL)),'resolution-aware native rain')
    for address,before,after,label in rain_patches(width,height):add(address,before,after,label)
    if pos>base+MODAL_INFLIGHT:raise RuntimeError('UI yama alanı aşıldı.')
    return changes,chunks

class DisplayFix:
    def __init__(self,start_worker=True):
        self.game=None;self.base=0;self.changes=[];self.manifest=None;self.width=0;self.height=0;self.message=''
        self.requested=False;self._candidate=None;self._candidate_since=0
        self._lock=threading.RLock();self._stop=threading.Event();self.worker=None
        if start_worker:
            self.worker=threading.Thread(target=self._follow_game,daemon=True);self.worker.start()
    def info(self):
        with self._lock:return self._info()
    def _info(self):
        if self.game:
            exit_code=W.DWORD()
            if not ExitCode(self.game.h,C.byref(exit_code)) or exit_code.value!=259:
                self.game.close();self.game=None
        return dict(active=self.game is not None,pid=self.game.pid if self.game else None,
                    width=self.width,height=self.height,manifest=self.manifest,
                    version=VERSION,rainFullScreen=self.game is not None,message=self.message,requested=self.requested,
                    pending=self.requested and self.game is None)
    def enable(self):
        with self._lock:
            self.requested=True;self._attempt()
            return self._info()
    def inspect_rain(self):
        with self._lock:
            if not self._info()['active']:raise RuntimeError('Display fix is not active')
            with self.game.suspended():
                return rain_snapshot(self.game,self.width,self.height,self.base+RAIN_STATE)
    def _follow_game(self):
        while not self._stop.wait(.8):
            with self._lock:
                if self.requested:self._attempt()
    def _attempt(self):
        try:self._apply()
        except Exception as error:self.message=str(error)
    @staticmethod
    def _resolution(game):
        if game.read(0x40265a,1)!=b'\x68' or game.read(0x40265f,1)!=b'\x68':
            raise RuntimeError('Çözünürlük kodu tanınmadı.')
        height=game.words(0x40265b)[0];width=game.words(0x402660)[0]
        if not 640<=width<=7680 or not 480<=height<=4320:
            raise RuntimeError('Desteklenmeyen oyun boyutu.')
        return width,height
    def _apply(self):
        self.info()
        if self.game and self._resolution(self.game)==(self.width,self.height):return self.info()
        if not LOCK.acquire(False):raise RuntimeError('Önceki oyun işleminin bitmesini bekle.')
        game=None;base=0;installed=[]
        try:
            if self.game:self._detach()
            game=Game(write=True)
            # Display hooks do not depend on a loaded character or drop mode.
            # Wait for the original resolution patcher to finish its writes.
            width,height=self._resolution(game);candidate=(game.pid,width,height)
            if candidate!=self._candidate:
                self._candidate=candidate;self._candidate_since=time.monotonic()
            if time.monotonic()-self._candidate_since<RESOLUTION_SETTLE_SECONDS:
                self.message=f'{width} × {height} çözünürlük yamasının tamamlanması bekleniyor.'
                game.close();return self._info()
            # Reject foreign renderer hooks instead of chaining unknown code.
            packet,strings=game.words(IAT_PACKET)[0],game.words(IAT_STRINGS)[0]
            from drop_event import remote_export
            if (packet!=remote_export(game,'RKC_UPDIB.dll','?SetPacket@RKC_UPDIB@@QAEHJJJJJJJJJJJJJFFFPAUtagRECT@@PAVRKC_DIB@@@Z') or
                strings!=remote_export(game,'RKC_UPDIB.dll','?SetStringsPacket@RKC_UPDIB@@QAEHJJJJJPADEEEJJJJJ@Z')):
                raise RuntimeError('Oyun görüntüleme girişleri tanınmadı.')
            from resolution_native import installed as native_installed
            native=native_installed(game);setrect=None
            if native:
                setrect=remote_export(game,'user32.dll','SetRect')
                if game.words(IAT_RECT)[0]!=setrect:raise RuntimeError('SetRect girişinde başka bir yama var.')
            base=Alloc(game.h,None,0x4000,0x3000,0x40);check(base,'Allocate UI correction')
            changes,chunks=build_changes(base,width,height,packet,strings,native,setrect)
            for change in changes:
                if game.read(change['address'],len(bytes.fromhex(change['before'])))!=bytes.fromhex(change['before']):
                    raise RuntimeError(f"Başka yama ile çakışma: {change['label']} ({change['address']:08x}).")
            for address,code in chunks:game.write(address,code)
            check(Flush(game.h,base,0x4000),'Flush UI correction')
            record=dict(pid=game.pid,width=width,height=height,base=base,changes=changes)
            path=ROOT/'display-fix-sessions'/f'{game.pid}-{time.time_ns()}.json'
            path.parent.mkdir(exist_ok=True);path.write_text(json.dumps(record,indent=2),'utf-8')
            # Keep every related code/input/render change atomic to the game.
            with game.suspended() as handles:
                spans=[(x['address'],x['address']+len(bytes.fromhex(x['before']))) for x in changes]
                if any(lo<ip<hi for ip in game.ips(handles) for lo,hi in spans):
                    raise RuntimeError('Oyun arayüz kodunda; tekrar uygula.')
                for change in changes:
                    self._write(game,change['address'],bytes.fromhex(change['after']));installed.append(change)
            self.game,self.base,self.changes=game,base,changes
            self.width,self.height,self.manifest=width,height,str(path);self.message=''
            return self.info()
        except Exception:
            if game:
                with game.suspended():
                    for change in reversed(installed):self._write(game,change['address'],bytes.fromhex(change['before']))
                if base:Free(game.h,base,0,0x8000)
                game.close()
            raise
        finally:LOCK.release()
    @staticmethod
    def _write(game,address,raw):
        old=W.DWORD();check(Protect(game.h,address,len(raw),0x40,C.byref(old)),'Protect UI code')
        try:game.write(address,raw);check(Flush(game.h,address,len(raw)),'Flush UI code')
        finally:
            previous=W.DWORD();check(Protect(game.h,address,len(raw),old.value,C.byref(previous)),'Restore UI protection')
    def close(self):
        with self._lock:
            self.requested=False;self._candidate=None
            if not LOCK.acquire(False):raise RuntimeError('Önceki oyun işleminin bitmesini bekle.')
            try:self._detach();self.message='Arayüz düzeltmesi kapalı.'
            finally:LOCK.release()
    def shutdown(self):
        self._stop.set()
        self.close()
        if self.worker:self.worker.join(2)
    def _detach(self):
        self.info()
        if not self.game:return
        game=self.game
        # Reattach points first; a thread returning through a thunk may still
        # need the allocated memory. Retain 16 KB until game exit in that case.
        spans=[(c['address'],c['address']+len(bytes.fromhex(c['after']))) for c in self.changes]
        for _ in range(100):
            with game.suspended() as handles:
                ips=game.ips(handles)
                if any(lo<ip<hi for ip in ips for lo,hi in spans):continue
                for change in self.changes:
                    if game.read(change['address'],len(bytes.fromhex(change['after'])))!=bytes.fromhex(change['after']):
                        raise RuntimeError('UI yaması değişti; yabancı kodun üzerine yazılmadı.')
                for change in reversed(self.changes):self._write(game,change['address'],bytes.fromhex(change['before']))
                safe=(game.words(self.base+MODAL_INFLIGHT)[0]==0 and
                      game.words(self.base+RAIN_STATE)[0]==0 and
                      not any(self.base<=ip<self.base+0x4000 for ip in ips))
                if safe:Free(game.h,self.base,0,0x8000)
                break
            time.sleep(.005)
        else:raise RuntimeError('Arayüz güvenli bir kod sınırında değil; tekrar geri al.')
        game.close();self.game=None
