"""Ctrl + left click uses native projection, collision and position history."""
import atexit
import hashlib
import json
import struct
import threading
import time

from live_drop import Game,Code,ROOT,LOCK,Alloc,Free,Flush,check,backup_saves,C,W
from hover_lifetime import GetExitCodeProcess

VERSION=2
CALLSITE=0x443571
HANDLER=0x441c00
ORIGINAL=bytes.fromhex('e88ae6ffff')
GROUND=0x800
DATA=0x1000
SIZE=0x2000
SETTINGS=ROOT/'teleport-settings.json'
PANELS=tuple(range(0x48ce38,0x48ce70,4))
VERIFIED=((4410544, 26, 'b529e99540013fcb90181f3a39621b4861663e7b92d97df68f5d53d951da1f17'), (4277680, 977, '7e71f23834d58add86d56ef0f24359b0d6acf683b4502d07d7cb98d45d9c33aa'), (4539120, 24, '8e5178eb42f8204d596f570be4170e2f6ec73b55cd7e5832ae2f7af2ba255964'), (4516192, 58, '9611aff9563b69b79784df6c4b5846a20946814eae781d39b06b9f1fa90480db'))


def ground_guard(base):
    """ECX=live ground, EDX=point, EAX=body rectangle; bound every covered cell."""
    c=Code(base).emit('55 8b ec 83 ec 10 53 56 57 8b d9 8b f2 8b f8')
    for offset in (0x18,0x1c,0x20,0x24):
        c.emit('83 7b').emit(f'{offset:02x} 00').branch('0f 8e','blocked')
    c.emit('83 7b 30 00').branch('0f 84','blocked')
    for point,rect,mag,origin,count,local in ((0,0,0x18,0x28,0x20,4),(0,8,0x18,0x28,0x20,8),
                                            (4,4,0x1c,0x2c,0x24,12),(4,12,0x1c,0x2c,0x24,16)):
        c.emit('8b 46').emit(f'{point:02x} 03 47 {rect:02x}').branch('0f 80','blocked')
        c.emit('99 f7 7b').emit(f'{mag:02x} 85 d2').branch('0f 89',f'floor{local}')
        c.emit('48').mark(f'floor{local}').emit('2b 43').emit(f'{origin:02x} 3b 43 {count:02x}')
        c.branch('0f 83','blocked').emit('89 45').emit(f'{256-local:02x}')
    c.emit('8b 45 fc 3b 45 f8').branch('0f 8f','blocked')
    c.emit('8b 45 f4 3b 45 f0').branch('0f 8f','blocked')
    c.mark('row').emit('8b 4b 30 8b 0c 81 85 c9').branch('0f 84','blocked')
    c.emit('8b 55 fc').mark('cell').emit('f6 04 51 01').branch('0f 85','blocked')
    c.emit('42 3b 55 f8').branch('0f 8e','cell')
    c.emit('40 3b 45 f0').branch('0f 8e','row')
    c.emit('b8 01 00 00 00').branch('e9','done')
    c.mark('blocked').emit('31 c0')
    c.mark('done').emit('5f 5e 5b 8b e5 5d c3')
    return c.finish()


def make_image(base,enabled=False):
    d=base+DATA
    c=Code(base).emit('55 8b ec 83 ec 10 53 56 57 8b f1 f0 ff 05').u32(d)
    c.emit('ff 05').u32(d+44)
    c.emit('83 3d').u32(d+4).emit('01').branch('0f 85','fallback')
    c.emit('83 3d').u32(0x482db0).emit('00').branch('0f 85','fallback')
    c.emit('8b 0d').u32(0x48ce0c).emit('85 c9').branch('0f 84','fallback')
    c.branch('e8',0x434cb0).emit('3b c6').branch('0f 85','fallback')
    c.emit('83 be a4 01 00 00 00').branch('0f 8e','fallback')
    for offset in (0x2dc,0x404,0x410,0x43c):
        c.emit('83 be').u32(offset).emit('00').branch('0f 85','fallback')
    c.emit('83 3d').u32(0x48ce34).emit('00').branch('0f 85','fallback')
    c.emit('83 3d').u32(0x48d778).emit('ff').branch('0f 85','fallback')
    for flag in PANELS:c.emit('83 3d').u32(flag).emit('00').branch('0f 85','fallback')
    c.emit('6a 11 ff 15').u32(0x4735c0).emit('66 a9 00 80').branch('0f 84','fallback')
    c.emit('8b 86 f8 03 00 00 85 c0').branch('0f 84','fallback')
    c.emit('83 78 10 01').branch('0f 84','new_click')
    c.emit('83 78 08 01').branch('0f 85','fallback')
    c.emit('83 3d').u32(d+40).emit('01').branch('0f 84','handled')
    c.branch('e9','fallback')
    c.mark('new_click')
    c.emit('8b be fc 03 00 00 85 ff').branch('0f 84','fallback')
    c.emit('ff 77 04 ff 37 8b ce').branch('e8',0x445750)
    c.emit('85 c0').branch('0f 84','fallback')
    c.emit('c7 05').u32(d+40).u32(1)
    # The exact world transform used immediately after this native click call.
    c.emit('8b 07 a3').u32(d+16).emit('03 05').u32(0x48cdf4).emit('2b 05').u32(0x48cdfc)
    c.emit('8b 57 04 89 15').u32(d+20).emit('03 15').u32(0x48cdf8).emit('2b 15').u32(0x48ce00)
    c.emit('8b 0d').u32(0x482d14).emit('85 c9').branch('0f 84','blocked')
    c.emit('8d 7d fc 57 8d 7d f8 57 52 50 ff 15').u32(0x47341c)
    c.emit('8b 45 f8 a3').u32(d+24).emit('8b 45 fc a3').u32(d+28)
    c.emit('8b 86 58 04 00 00 85 c0').branch('0f 84','blocked')
    c.emit('8b 48 3c 85 c9').branch('0f 84','blocked')
    c.emit('8d 96 e8 02 00 00 89 d0 8d 55 f8').branch('e8',base+GROUND)
    c.emit('85 c0').branch('0f 84','blocked')
    # Same body rectangle and collision routine as walking, including scenery
    # and other bodies. The endpoint is checked; intervening walls need no path.
    c.emit('6a 00 6a 00 6a 00 8d 86 e8 02 00 00 50 8d 45 f8 50 ff b6 c8 03 00 00')
    c.emit('ff b6 58 04 00 00 b9').u32(0x482df4).branch('e8',0x4145b0)
    c.emit('83 f8 01').branch('0f 85','blocked')
    c.emit('8b 86 e0 02 00 00 a3').u32(d+32)
    c.emit('8b 86 e4 02 00 00 a3').u32(d+36)
    c.emit('8b 45 f8 89 86 e0 02 00 00 8b 45 fc 89 86 e4 02 00 00')
    c.emit('6a 01 8b ce').branch('e8',0x44e960)
    c.emit('8d 86 e0 02 00 00 50 8d 8e 78 03 00 00').branch('e8',0x4542f0)
    c.emit('c7 86 18 03 00 00 01 00 00 00 c7 86 14 03 00 00 00 00 00 00')
    c.emit('c7 86 08 03 00 00 00 00 00 00 f0 ff 05').u32(d+8).branch('e9','handled')
    c.mark('blocked').emit('f0 ff 05').u32(d+12)
    c.mark('handled').emit('b8 01 00 00 00').branch('e9','done')
    c.mark('fallback').emit('c7 05').u32(d+40).u32(0).emit('8b ce').branch('e8',HANDLER)
    c.mark('done').emit('5f 5e 5b 8b e5 5d 9c f0 ff 0d').u32(d).emit('9d c3')
    raw=c.finish();guard=ground_guard(base+GROUND)
    assert len(raw)<GROUND and GROUND+len(guard)<DATA
    image=bytearray(SIZE);image[:len(raw)]=raw;image[GROUND:GROUND+len(guard)]=guard
    struct.pack_into('<I',image,DATA+4,int(enabled))
    return bytes(image)


class CtrlTeleport:
    def __init__(self):
        self.game=None;self.base=0;self.detour=None;self.requested=False
        self.backup=None;self.message='Ctrl + tık kapalı.';self.counts=(0,0)
        self.lock=threading.RLock();self.stop=threading.Event();self.worker=None
        try:self.requested=json.loads(SETTINGS.read_text('utf8')).get('enabled') is True
        except (OSError,ValueError,TypeError,AttributeError):pass
        atexit.register(self.close)
    def start(self):
        with self.lock:
            if self.worker is None:self.worker=threading.Thread(target=self._follow,daemon=True);self.worker.start()
    def info(self):
        with self.lock:
            if self.game:
                try:self.counts=self.game.words(self.base+DATA+8,2)
                except OSError:self.game.close();self.game=None;self.base=0
            return dict(version=VERSION,active=bool(self.game and self.requested),requested=self.requested,
                        pid=self.game.pid if self.game else None,teleports=self.counts[0],blocked=self.counts[1],
                        message=self.message,backup=self.backup)
    def set(self,enabled):
        if not isinstance(enabled,bool):raise ValueError('Aç veya Kapat seçilmeli.')
        with self.lock:
            SETTINGS.write_text(json.dumps({'enabled':enabled},indent=2),'utf8');self.requested=enabled
            if self.game:self.game.write(self.base+DATA+4,struct.pack('<I',int(enabled)))
            self.message='Ctrl + sol tık: yürünebilir zemine ışınlan.' if enabled else 'Ctrl + tık kapalı.'
        self.start();return self.info()
    def inspect(self):
        with self.lock:
            if not self.game:raise RuntimeError('Işınlanma yardımcısı bağlı değil.')
            game=self.game
            with game.suspended():
                state=game.state();p=state['player']
                return dict(**state,counters=game.words(self.base+DATA+8,2),
                    lastScreen=struct.unpack('<ii',game.read(self.base+DATA+16,8)),
                    lastTarget=struct.unpack('<ii',game.read(self.base+DATA+24,8)),
                    lastOrigin=struct.unpack('<ii',game.read(self.base+DATA+32,8)),
                    heldGesture=game.words(self.base+DATA+40)[0],
                    inputFrames=game.words(self.base+DATA+44)[0],
                    panels={hex(a):game.words(a)[0] for a in PANELS},
                    body=struct.unpack('<4i',game.read(p+0x2e8,16)))
    def _follow(self):
        while not self.stop.wait(.6):
            with self.lock:
                try:
                    if self.game:
                        code=W.DWORD()
                        if not GetExitCodeProcess(self.game.h,C.byref(code)) or code.value!=259:
                            self.game.close();self.game=None;self.base=0;self.detour=None;self.counts=(0,0)
                        elif self.game.read(CALLSITE,5)!=self.detour:raise RuntimeError('Sol tık çağrısı değişti.')
                    if self.requested and not self.game and LOCK.acquire(False):
                        try:self._attach()
                        finally:LOCK.release()
                except Exception as error:self.message=str(error)
    def _attach(self):
        game=Game(write=True);base=0;installed=False
        try:
            game.state()
            if game.read(CALLSITE,5)!=ORIGINAL:raise RuntimeError('Özgün sol tık çağrısı tanınmadı.')
            for at,n,digest in VERIFIED:
                if hashlib.sha256(game.read(at,n)).hexdigest()!=digest:raise RuntimeError(f'Işınlanma işlevi tanınmadı: {at:08x}')
            self.backup=backup_saves(game)
            base=Alloc(game.h,None,SIZE,0x3000,0x40);check(base,'Allocate Ctrl-click teleport')
            image=make_image(base,self.requested);game.write(base,image);check(Flush(game.h,base,SIZE),'Flush teleport')
            detour=b'\xe8'+struct.pack('<i',base-CALLSITE-5)
            game.patch_at(CALLSITE,ORIGINAL,detour);installed=True
            self.game,self.base,self.detour=game,base,detour
            folder=ROOT/'teleport-sessions';folder.mkdir(exist_ok=True)
            (folder/f'{game.pid}-{time.time_ns()}.json').write_text(json.dumps(dict(pid=game.pid,base=base,
                version=VERSION,callsite=CALLSITE,before=ORIGINAL.hex(),after=detour.hex(),backup=self.backup,
                codeSHA256=hashlib.sha256(image).hexdigest(),gameFileModified=False),indent=2),'utf8')
            self.message='Ctrl + sol tık: yürünebilir zemine ışınlan.'
        finally:
            if game is not self.game:
                if base and not installed:Free(game.h,base,0,0x8000)
                game.close()
    def close(self):
        self.stop.set()
        if self.worker and self.worker is not threading.current_thread():self.worker.join(2)
        with self.lock:
            if not self.game:return
            game,base=self.game,self.base
            try:
                game.write(base+DATA+4,b'\0'*4);game.patch_at(CALLSITE,self.detour,ORIGINAL)
                for unused in range(500):
                    with game.suspended() as handles:
                        safe=game.words(base+DATA)[0]==0 and not any(base<=ip<base+SIZE for ip in game.ips(handles))
                    if safe:check(Free(game.h,base,0,0x8000),'Free teleport');break
                    time.sleep(.01)
            finally:game.close();self.game=None;self.base=0;self.detour=None
