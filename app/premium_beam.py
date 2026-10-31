"""Reversible Premium loot beacons queued in the native world render pass.

Only cosmetic packets are added. Item data, hit testing and grail are untouched.
The immutable 24-bit DIB frames use the engine's additive blend, not an overlay.
"""
import atexit,hashlib,json,math,struct,threading,time
from functools import lru_cache
from live_drop import Game,Code,ROOT,LOCK,Alloc,Free,Flush,check
from drop_event import remote_export
from hover_lifetime import GetExitCodeProcess,C,W
from magic_beam_rules import RULES
from grail_policy import make_lookup

HOOK=0x41ebf6
ORIGINAL=bytes.fromhex('83 bd 44 a7 00 00 01')
DATA=0x800
FRAMES=0x1000
WIDTH=96
HEIGHT=224
ANCHOR_X=48
ANCHOR_Y=207
FRAME_COUNT=16
FRAME_BYTES=WIDTH*HEIGHT*3
FRAME_STRIDE=(64+FRAME_BYTES+15)&~15
BLUE_FRAMES=FRAMES+FRAME_COUNT*FRAME_STRIDE
RED_FRAMES=BLUE_FRAMES+FRAME_COUNT*FRAME_STRIDE
RULE_TABLE=RED_FRAMES+FRAME_COUNT*FRAME_STRIDE
RULE_CHECK=0x500
GRAIL_CHECK=0x600
SETTINGS=ROOT/'magic-beam-settings.json'
VERSION=4


def rule_table():
    header=bytearray(len(RULES)*16);checks=bytearray()
    for i,(category,ident,stats) in enumerate(RULES):
        struct.pack_into('<4I',header,i*16,category,ident,len(header)+len(checks),len(stats))
        for offset,threshold,maximum in stats:checks.extend(struct.pack('<3I',offset,threshold,maximum))
    return bytes(header+checks)


RULE_BYTES=rule_table()
SIZE=(RULE_TABLE+len(RULE_BYTES)+4095)&~4095
PACKET='?SetPacket@RKC_UPDIB@@QAEHJJJJJJJJJJJJJFFFPAUtagRECT@@PAVRKC_DIB@@@Z'
CALC='?CalcRealPos@RKC_RPGSCRN@@QAEXJJPAJ0@Z'

def jump(source,target):
    return b'\xe9'+struct.pack('<i',target-source-5)+b'\x90\x90'

@lru_cache(maxsize=FRAME_COUNT*3)
def frame_pixels(index,blue=False,grail=False):
    """Bottom-up BGR: warm pillar, elliptic halo and gently rising motes."""
    phase=2*math.pi*index/FRAME_COUNT
    out=bytearray(FRAME_BYTES)
    for y in range(HEIGHT):
        h=ANCHOR_Y-y
        for x in range(WIDTH):
            dx=x-ANCHOR_X
            value=0.0
            if 0<=h<=202:
                fade=min(1,h/8+0.15)*min(1,(202-h)/45)
                width=2.2+1.8*(h/202)
                core=math.exp(-(dx/width)**2)*.61
                haze=math.exp(-(dx/(width*3.2))**2)*.13
                value=(core+haze)*fade*(.91+.09*math.sin(phase+h*.045))
            ellipse=(dx/31)**2+((y-ANCHOR_Y)/10)**2
            value+=.42*math.exp(-ellipse*2.0)
            value+=.13*math.exp(-((math.sqrt(ellipse)-.82)/.12)**2)
            for mote in range(5):
                rise=(index/FRAME_COUNT*170+mote*37)%180
                mx=math.sin(mote*2.4+phase*.25)*11
                my=ANCHOR_Y-rise
                value+=.45*math.exp(-((dx-mx)/1.25)**2-((y-my)/2.3)**2)
            # Pale gold centre, amber outer haze. Black adds no light.
            r=min(255,round(value*(64 if blue else 244)));g=min(255,round(value*(160 if blue else 158)));b=min(255,round(value*(255 if blue else 45)))
            if abs(dx)<1.8 and 5<h<175:
                b=min(255,b+round(47*min(1,value)))
                g=min(255,g+round(25*min(1,value)))
            if grail and 0<=h<=198:
                # Three red helices orbit the unchanged golden pillar. Phase
                # repeats exactly over the frame cycle and follows game time.
                red=0.0;edge=min(1,h/9)*min(1,(198-h)/22)
                for arm in range(3):
                    angle=phase+h*.055+arm*2*math.pi/3
                    orbit=math.sin(angle)*(14+5*h/198)
                    depth=.55+.45*(math.cos(angle)+1)/2
                    red+=edge*depth*(.86*math.exp(-((dx-orbit)/1.2)**2)+.16*math.exp(-((dx-orbit)/3.7)**2))
                r=min(255,r+round(red*255));g=min(255,g+round(red*23));b=min(255,b+round(red*32))
            at=((HEIGHT-1-y)*WIDTH+x)*3
            out[at:at+3]=bytes((b,g,r))
    return bytes(out)

def make_rule_check(base):
    """Read-only binary template lookup and independent AND of native rolls."""
    c=Code(base+RULE_CHECK).emit('53 56 57 55 8b f1 33 db bf').u32(len(RULES))
    c.mark('search').emit('3b df').branch('0f 83','fail')
    c.emit('8d 04 3b d1 e8 8b e8 c1 e0 04 05').u32(base+RULE_TABLE)
    c.emit('8b 56 0c 3b 10').branch('0f 82','lower').branch('0f 87','higher')
    c.emit('8b 56 14 3b 50 04').branch('0f 82','lower').branch('0f 87','higher')
    c.emit('8b 48 0c 8b 40 08 05').u32(base+RULE_TABLE)
    c.mark('stat').emit('8b 10 8b 14 16 3b 50 04').branch('0f 8c','fail')
    c.emit('3b 50 08').branch('0f 8f','fail')
    c.emit('83 c0 0c 49').branch('0f 85','stat')
    c.emit('b8 01 00 00 00').branch('e9','done')
    c.mark('lower').emit('8b fd').branch('e9','search')
    c.mark('higher').emit('8d 5d 01').branch('e9','search')
    c.mark('fail').emit('33 c0').mark('done').emit('5d 5f 5e 5b c3')
    raw=c.finish();assert RULE_CHECK+len(raw)<DATA
    return raw


def make_stub(base,packet,calc):
    d=base+DATA;c=Code(base)
    c.emit('9c 60 f0 ff 05').u32(d) # in flight, exact caller state
    c.emit('c7 05').u32(d+8).u32(0) # visible Premium count this frame
    c.emit('c7 05').u32(d+28).u32(0)
    c.emit('c7 05').u32(d+36).u32(0)
    c.emit('a1').u32(d+4).emit('0b 05').u32(d+16).branch('0f 84','done')
    c.emit('83 3d').u32(0x482db0).emit('00').branch('0f 85','done')
    c.emit('8b 0d').u32(0x48ce0c).emit('85 c9').branch('0f 84','done')
    c.emit('8b 01 85 c0').branch('0f 84','done').emit('83 f8 04').branch('0f 87','done')
    c.emit('8b 51 08 3b d0').branch('0f 83','done')
    c.emit('8b 41 04 85 c0').branch('0f 84','done')
    c.emit('8b 04 90 85 c0').branch('0f 84','done')
    c.emit('8b 80 58 04 00 00 85 c0').branch('0f 84','done')
    c.emit('8b 40 4c 85 c0').branch('0f 84','done')
    c.emit('8b 30') # ESI ground list, traversed only on game's main thread
    c.emit('8b 3d').u32(0x482d1c).emit('85 ff').branch('0f 84','done')
    c.mark('loop').emit('85 f6').branch('0f 84','done')
    c.emit('83 7e 0c 02').branch('0f 87','next')
    c.emit('83 7e 18 02').branch('0f 85','magic')
    c.emit('83 3d').u32(d+4).emit('01').branch('0f 85','next')
    c.emit('bd').u32(base+FRAMES)
    c.emit('8b ce').branch('e8',base+GRAIL_CHECK).emit('85 c0').branch('0f 84','project')
    c.emit('83 78 08 00').branch('0f 85','project')
    c.emit('bd').u32(base+RED_FRAMES).branch('e9','project')
    c.mark('magic').emit('83 7e 18 01').branch('0f 85','next')
    c.emit('83 3d').u32(d+16).emit('01').branch('0f 85','next')
    c.emit('a1').u32(d+40).emit('85 c0').branch('0f 84','magic_visible')
    c.emit('83 38 01').branch('0f 84','next')
    c.mark('magic_visible')
    c.emit('8b ce').branch('e8',base+RULE_CHECK).emit('85 c0').branch('0f 84','next')
    c.emit('bd').u32(base+BLUE_FRAMES)
    # Project with native camera scale, then use this frame's scroll offsets.
    c.mark('project').emit('68').u32(d+24).emit('68').u32(d+20)
    c.emit('ff 76 4c ff 76 48 8b 0d').u32(0x482d14).call(calc)
    c.emit('a1').u32(d+20).emit('2b 47 40 2d').u32(ANCHOR_X).emit('a3').u32(d+20)
    c.emit('8b 15').u32(d+24).emit('2b 57 44 81 ea').u32(ANCHOR_Y).emit('89 15').u32(d+24)
    # Cull only effect rectangles outside the current world viewport.
    c.emit('3b 47 18').branch('0f 8f','next')
    c.emit('05').u32(WIDTH).emit('3b 47 10').branch('0f 8c','next')
    c.emit('3b 57 1c').branch('0f 8f','next')
    c.emit('81 c2').u32(HEIGHT).emit('3b 57 14').branch('0f 8c','next')
    # Stagger animated frames by persistent item identity, independent of FPS.
    c.emit('a1').u32(0x48ce98).emit('c1 e8 01 03 46 14 83 e0 0f')
    c.emit('69 c0').u32(FRAME_STRIDE).emit('03 c5')
    c.emit('50 8d 47 10 50') # custom DIB, clipped to native world RECT
    for value in (1000,1000,1000,0,1000,1000,1000,1000):c.emit('68').u32(value)
    c.emit('ff 35').u32(d+24).emit('ff 35').u32(d+20)
    for value in (0x1022,0xffffffff,0,0):c.emit('68').u32(value)
    c.emit('ff 77 20 53 8b 0d').u32(0x482d10).call(packet)
    c.emit('81 fd').u32(base+BLUE_FRAMES).branch('0f 84','magic_count')
    c.emit('81 fd').u32(base+RED_FRAMES).branch('0f 85','gold_count')
    c.emit('ff 05').u32(d+36)
    c.mark('gold_count')
    c.emit('ff 05').u32(d+8).branch('e9','next')
    c.mark('magic_count').emit('ff 05').u32(d+28)
    c.mark('next').emit('8b b6 8c 00 00 00').branch('e9','loop')
    c.mark('done').emit('ff 05').u32(d+12)
    c.emit('f0 ff 0d').u32(d).emit('61 9d')
    c.data.extend(ORIGINAL);c.branch('e9',HOOK+len(ORIGINAL))
    raw=c.finish();assert len(raw)<RULE_CHECK
    return raw

def make_image(base,packet,calc):
    out=bytearray(SIZE);stub=make_stub(base,packet,calc);out[:len(stub)]=stub
    check_code=make_rule_check(base);out[RULE_CHECK:RULE_CHECK+len(check_code)]=check_code
    grail_check=make_lookup(base+GRAIL_CHECK,base+DATA+32);assert GRAIL_CHECK+len(grail_check)<DATA
    out[GRAIL_CHECK:GRAIL_CHECK+len(grail_check)]=grail_check
    out[RULE_TABLE:RULE_TABLE+len(RULE_BYTES)]=RULE_BYTES
    struct.pack_into('<I',out,DATA+4,1)
    for blue,grail,start in ((False,False,FRAMES),(True,False,BLUE_FRAMES),(False,True,RED_FRAMES)):
        for i in range(FRAME_COUNT):
            at=start+i*FRAME_STRIDE
            struct.pack_into('<III',out,at,base+at+16,0,base+at+64)
            struct.pack_into('<IiiHHIIIIII',out,at+16,40,WIDTH,HEIGHT,1,24,0,FRAME_BYTES,0,0,0,0)
            out[at+64:at+64+FRAME_BYTES]=frame_pixels(i,blue,grail)
    return bytes(out)

class PremiumBeam:
    def __init__(self,grail_policy=None,visibility_policy=None):
        self.game=None;self.base=0;self.detour=None;self.requested=False;self.worker=None
        self.lock=threading.RLock();self.stop=threading.Event();self.message='Premium ışını kapalı.'
        self.retired=[]
        self.magic_requested=False
        self.grail_policy=grail_policy
        self.visibility_policy=visibility_policy
        try:self.magic_requested=json.loads(SETTINGS.read_text('utf8')).get('enabled') is True
        except (OSError,ValueError,TypeError,AttributeError):pass
        atexit.register(self.close)
    def info(self):
        with self.lock:
            count=frames=missing=0
            if self.game:
                try:
                    count,frames=self.game.words(self.base+DATA+8,2)
                    missing=self.game.words(self.base+DATA+36)[0]
                except OSError:self.game.close();self.game=None;self.base=0;self.detour=None
            return dict(version=VERSION,active=bool(self.game and self.requested),requested=self.requested,
                        visible=count,missingVisible=missing,frames=frames,message=self.message,method='native-additive-world-packets')
    def magic_info(self):
        with self.lock:
            count=0
            if self.game:
                try:count=self.game.words(self.base+DATA+28)[0]
                except OSError:pass
            return dict(version=1,active=bool(self.game and self.magic_requested),requested=self.magic_requested,
                        visible=count,threshold=80,templates=len(RULES),
                        message='Açık · üst prefix ve her değişken bonus en az %80.' if self.game and self.magic_requested
                        else 'Mavi ışın hazırlanıyor.' if self.magic_requested else 'Mavi ışın kapalı.')
    def start(self):
        with self.lock:
            if self.magic_requested:self._start_worker()
    def _start_worker(self):
        if self.worker is None:
            self.worker=threading.Thread(target=self._follow,daemon=True);self.worker.start()
    def set_magic(self,enabled):
        if not isinstance(enabled,bool):raise ValueError('Mavi ışın için Aç veya Kapat seçilmeli.')
        with self.lock:
            SETTINGS.write_text(json.dumps({'enabled':enabled},indent=2),'utf8')
            self.magic_requested=enabled
            if enabled:self._start_worker()
            if self.game:self.game.write(self.base+DATA+16,struct.pack('<I',enabled))
        return self.magic_info()
    def enable(self):
        with self.lock:
            self.requested=True
            self._start_worker()
            if self.game:self.game.write(self.base+DATA+4,struct.pack('<I',1))
            self.message='Açık · yerdeki Premium eşyalarda altın ışın.' if self.game else 'Premium ışını hazırlanıyor.'
        return self.info()
    def disable(self):
        with self.lock:
            self.requested=False
            if self.game:self.game.write(self.base+DATA+4,b'\0'*4)
            self.message='Premium ışını kapalı.'
        return self.info()
    def _follow(self):
        while not self.stop.wait(.6):
            with self.lock:
                try:
                    if self.game:
                        status=W.DWORD()
                        if not GetExitCodeProcess(self.game.h,C.byref(status)) or status.value!=259:
                            self.game.close();self.game=None;self.base=0;self.detour=None
                        elif self.game.read(HOOK,7)!=self.detour:raise RuntimeError('Premium çizim girişi başka bir yama tarafından değiştirildi.')
                        else:
                            if self.grail_policy:self.game.write(self.base+DATA+32,struct.pack('<I',self.grail_policy(self.game.pid)['address']))
                            if self.visibility_policy:self.game.write(self.base+DATA+40,struct.pack('<I',self.visibility_policy(self.game.pid)))
                    if (self.requested or self.magic_requested) and not self.game and LOCK.acquire(False):
                        try:self._attach()
                        finally:LOCK.release()
                except Exception as error:self.message=str(error)
    def _attach(self):
        game=Game(write=True);base=0
        try:
            if game.read(HOOK,7)!=ORIGINAL:raise RuntimeError('Premium ışınının çizim noktası tanınmadı.')
            packet=remote_export(game,'RKC_UPDIB.dll',PACKET)
            calc=remote_export(game,'RKC_RPGSCRN.dll',CALC)
            # Verify the exact functions used, including the additive DIB path.
            for address,size,sha in ((packet,0x140,'12fde797624a1432a1fc1ab8261aea95a999a307b77360bfacd8a47d4fd0d2de'),
                    (calc,0x4c,'017f757c2afde317c2d7ed9f63d882fd1e63a4f06a939480fa1df37a57f6eb8e')):
                code=bytearray(game.read(address,size))
                if address==packet:
                    # This function's sole PE relocation is its SEH table.
                    if struct.unpack_from('<I',code,3)[0]!=packet-0x1960+0x8048:raise RuntimeError('Efekt çizim modülü tanınmadı.')
                    struct.pack_into('<I',code,3,0x10008048)
                if hashlib.sha256(code).hexdigest()!=sha:raise RuntimeError('Oyun efekt çizimi tanınmadı.')
            base=Alloc(game.h,None,SIZE,0x3000,0x40);check(base,'Allocate Premium beam frames')
            raw=bytearray(make_image(base,packet,calc))
            struct.pack_into('<I',raw,DATA+4,int(self.requested))
            struct.pack_into('<I',raw,DATA+16,int(self.magic_requested))
            if self.grail_policy:struct.pack_into('<I',raw,DATA+32,self.grail_policy(game.pid)['address'])
            if self.visibility_policy:struct.pack_into('<I',raw,DATA+40,self.visibility_policy(game.pid))
            game.write(base,bytes(raw))
            check(Flush(game.h,base,DATA),'Flush Premium beam renderer')
            after=jump(HOOK,base);game.patch_at(HOOK,ORIGINAL,after)
            self.game,self.base,self.detour=game,base,after
            folder=ROOT/'beam-sessions';folder.mkdir(exist_ok=True)
            (folder/f'{game.pid}-{time.time_ns()}.json').write_text(json.dumps(dict(pid=game.pid,base=base,size=SIZE,
                address=HOOK,before=ORIGINAL.hex(),after=after.hex(),gameFileModified=False,frameSHA256=hashlib.sha256(raw[FRAMES:]).hexdigest()),indent=2),'utf8')
            self.message='Açık · yerdeki Premium eşyalarda altın ışın.'
        finally:
            if game is not self.game:
                if base:Free(game.h,base,0,0x8000)
                game.close()
    def snapshot(self):
        """Fixed, read-only renderer/ground fields for local visual validation."""
        game=Game()
        try:
            state=game.state();items=[]
            with game.suspended():
                for p in game.ground_items(state['map']):
                    cat=game.words(p+0xc)[0];rarity=game.words(p+0x18)[0]
                    if cat<=2 and rarity==2:items.append(dict(pointer=p,category=cat,id=game.words(p+0x14)[0],xy=game.words(p+0x48,2)))
                screen=game.words(0x482d1c)[0];projection=game.words(0x482d14)[0]
                return dict(**state,items=items,screen=game.words(screen,20),projection=game.words(projection,12),beam=self.info())
        finally:game.close()
    def close(self):
        self.stop.set()
        if self.worker and self.worker is not threading.current_thread():self.worker.join(2)
        with self.lock:
            if not self.game:return
            game=self.game
            try:
                game.write(self.base+DATA+4,b'\0'*4)
                game.write(self.base+DATA+16,b'\0'*4)
                game.patch_at(HOOK,self.detour,ORIGINAL)
                # Queued native packets can still reference this frame atlas.
                # Retain its immutable frame atlas until process exit; never free a DIB
                # still held by a double-buffered native packet generation.
                self.retired.append((game.pid,self.base))
            finally:game.close();self.game=None;self.base=0;self.detour=None
