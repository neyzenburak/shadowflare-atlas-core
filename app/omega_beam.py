"""Warrior-only, obstacle-aware Omega beam; native input, rendering and damage."""
import atexit
import hashlib
import json
import math
import struct
import threading
import time
from functools import lru_cache

from live_drop import Game,ROOT,LOCK,Alloc,Flush,check,C,W
from hover_lifetime import GetExitCodeProcess
from ctrl_teleport import ground_guard
from premium_beam import PACKET,CALC
from drop_event import remote_export,remote_tick_count,GetTickCount
from omega_path import project,unproject,find_route,wall_route,along,length,link,simplify,heading,prefix,turn_ok,deadline_distance
from meteor_skill import MeteorSkill,SPRITE_COUNT,GROUND_SECONDS
from special_effects import SPECS,pixels

VERSION=4
PLAN=json.loads((ROOT/'omega-beam-plan.json').read_text('utf8'))
SIZE=PLAN['size'];DATA=0x2000;GUARD=0x1c00;ATLAS=0x18000
BUFFERS=(0x50000,0x69000,0x82000)
STRIDE=6976;FRAME_SIZE=48;SPRITES=24
INPUT_HOOK=0x441cf2;INPUT_ORIGINAL=bytes.fromhex('8b86f8030000')
RENDER_HOOK=0x41ebfd;RENDER_ORIGINAL=bytes.fromhex('0f852d050000')
SETTINGS=ROOT/'omega-beam-settings.json'


def relocate(part,base,packet,calc,tick):
    raw=bytearray.fromhex(part['code']);delta=base-PLAN['referenceBase']
    exports={0x1f000000:packet,0x1f001000:calc,0x1f002000:tick}
    for fix in part['fixes']:
        at=fix['offset']
        if fix['kind']=='absolute':
            struct.pack_into('<I',raw,at,struct.unpack_from('<I',raw,at)[0]+delta)
        else:
            target=exports.get(fix['target'],fix['target'])
            struct.pack_into('<i',raw,at,target-base-fix['end'])
    return bytes(raw)


@lru_cache(maxsize=SPRITES)
def sprite(index):
    """Immutable additive BGR glow stamps, sparks and expanding smoke."""
    raw=bytearray(48*48*3)
    for y in range(48):
        for x in range(48):
            dx=x-24;dy=y-24;r=math.hypot(dx,dy)
            if index<8:
                fade=(index+1)/8
                core=math.exp(-r*r/1.7);glow=math.exp(-r*r/17)*.32
                value=(core+glow)*fade
                rgb=(min(255,round(value*255)),min(255,round(core*150*fade)),min(255,round(core*175*fade)))
            elif index<16:
                age=(index-8)/7;radius=3+age*15
                cloud=math.exp(-((r/radius)**2)*1.7)*(.52*(1-age))
                cloud*=.8+.2*math.sin(dx*.9+dy*.4+index)
                rgb=(round(cloud*170),round(cloud*155),round(cloud*160))
            else:
                fade=(index-15)/8
                value=math.exp(-r*r/3)*fade
                rgb=(round(value*255),round(value*70),round(value*40))
            at=((47-y)*48+x)*3;raw[at:at+3]=bytes(reversed(rgb))
    return bytes(raw)


def make_image(base,packet,calc,tick,enabled):
    image=bytearray(SIZE)
    for part in PLAN['parts']:
        code=relocate(part,base,packet,calc,tick)
        image[part['offset']:part['offset']+len(code)]=code
    guard=ground_guard(base+GUARD);assert GUARD+len(guard)<DATA
    image[GUARD:GUARD+len(guard)]=guard
    struct.pack_into('<I',image,DATA+4,int(enabled))
    struct.pack_into('<I',image,DATA+80,GetTickCount())
    # Source kind 0 = local player. Native +94 bypasses random damage formula.
    struct.pack_into('<I',image,0x2200+0x94,1)
    for off in (0x88,0xa4,0xac,0x124,0x128):struct.pack_into('<i',image,0x2200+off,-1)
    struct.pack_into('<4i',image,0x2340,-12,-12,12,12)
    for index in range(SPRITES):
        at=ATLAS+index*STRIDE
        struct.pack_into('<III',image,at,base+at+16,0,base+at+64)
        struct.pack_into('<IiiHHIIIIII',image,at+16,40,48,48,1,24,0,6912,0,0,0,0)
        image[at+64:at+64+6912]=sprite(index)
        struct.pack_into('<6I',image,0x42000+index*24,base+at,48,48,24,24,0)
    at=0xa0000;index=SPRITES
    for kind,(width,height,ax,ay,count) in SPECS.items():
        size=width*height*3;stride=(64+size+15)&~15
        for frame in range(count):
            struct.pack_into('<III',image,at,base+at+16,0,base+at+64)
            struct.pack_into('<IiiHHIIIIII',image,at+16,40,width,height,1,24,0,size,0,0,0,0)
            image[at+64:at+64+size]=pixels(kind,frame)
            struct.pack_into('<6I',image,0x42000+index*24,base+at,width,height,ax,ay,0)
            index+=1;at+=stride
    assert index==SPRITE_COUNT and at<SIZE
    struct.pack_into('<I',image,DATA+184,SPRITE_COUNT)
    return bytes(image)


class Scene:
    """Live terrain plus the same solid scene-object rectangles used by walking."""
    def __init__(self,game,map_pointer):
        self.game=game;self.map=map_pointer;self.rows={};self.obstacles=[];self.native_blocks=[]
        ground=game.words(map_pointer+0x3c)[0]
        self.mx,self.my,self.w,self.h,self.ox,self.oy,rows=struct.unpack('<7i',game.read(ground+0x18,28))
        if not (0<self.mx<=10000 and 0<self.my<=10000 and 0<self.w<100000 and 0<self.h<100000 and self.w*self.h<=40000000):
            raise RuntimeError('Omega: zemin tablosu tanınmadı.')
        self.pointers=game.words(rows,self.h)
        projection=game.words(0x482d14)[0];self.scale=game.words(projection+0x18,2)
        if not all(0<n<=1000 for n in self.scale):raise RuntimeError('Omega: dünya izdüşümü tanınmadı.')
        self.refresh_obstacles()

    def refresh_obstacles(self):
        manager=self.game.words(self.map+0x30)[0];count,array=self.game.words(manager,2)
        if count>100000:raise RuntimeError('Omega: bölge nesneleri tanınmadı.')
        obstacles=[]
        for block in self.game.words(array,count) if count else ():
            kind,_,obj=self.game.words(block,3)
            if kind!=0 or not obj:continue
            raw=self.game.read(obj,0xfc)
            if struct.unpack_from('<i',raw,0xf8)[0]==1:continue
            x,y=struct.unpack_from('<2i',raw,0x18);a,b,c,d=struct.unpack_from('<4i',raw,0x20)
            if a<=c and b<=d and (c>a or d>b):obstacles.append((x+a,y+b,x+c,y+d))
        self.obstacles=obstacles

    def free_world(self,p):
        x,y=p;r=12
        a=math.floor((x-r)/self.mx)-self.ox;c=math.floor((x+r)/self.mx)-self.ox
        b=math.floor((y-r)/self.my)-self.oy;d=math.floor((y+r)/self.my)-self.oy
        if a<0 or b<0 or c>=self.w or d>=self.h:return False
        for row in range(b,d+1):
            if row not in self.rows:self.rows[row]=self.game.read(self.pointers[row],self.w*2)
            for column in range(a,c+1):
                if self.rows[row][column*2]&1:return False
        return not any(left-r<=x<=right+r and top-r<=y<=bottom+r for left,top,right,bottom in self.obstacles) and not any(
            math.hypot(x-bx,y-by)<radius for bx,by,radius in self.native_blocks)

    def learn_block(self,point,head):
        # Keep the last native-approved head outside the new exclusion, even
        # when an obstacle was discovered immediately in front of the beam.
        radius=min(max(35,min(self.mx,self.my)/2),math.dist(point,head)*.65)
        self.native_blocks.append((*point,max(1,radius)))

    def clear(self,a,b):
        u=unproject(a,self.scale);v=unproject(b,self.scale)
        dx=v[0]-u[0];dy=v[1]-u[1];square=dx*dx+dy*dy
        for x,y,radius in self.native_blocks:
            t=max(0,min(1,((x-u[0])*dx+(y-u[1])*dy)/square)) if square else 0
            if math.hypot(u[0]+t*dx-x,u[1]+t*dy-y)<radius:return False
        n=max(1,math.ceil(math.dist(u,v)/max(1,min(self.mx,self.my)/3)))
        return all(self.free_world((u[0]+(v[0]-u[0])*i/n,u[1]+(v[1]-u[1])*i/n)) for i in range(n+1))


class OmegaBeam(MeteorSkill):
    def __init__(self):
        self.lock=threading.RLock();self.stop=threading.Event();self.worker=None
        self.game=None;self.base=0;self.requested=False;self.flight=None;self.sequence=0
        self.aftermaths=[]
        self.message='Özel yetenekler kapalı.';self.last={};self.detours=[];self.retired=[]
        self.skill='omega';self.surprise=False
        try:
            settings=json.loads(SETTINGS.read_text('utf8'));self.requested=settings.get('enabled') is True
            self.skill=settings.get('skill','omega') if settings.get('skill','omega') in ('omega','meteor') else 'omega'
            self.surprise=settings.get('surprise') is True
        except (OSError,ValueError,TypeError,AttributeError):pass
        atexit.register(self.close)

    def start(self):
        with self.lock:
            if self.worker is None:
                self.worker=threading.Thread(target=self._follow,daemon=True);self.worker.start()

    def info(self):
        with self.lock:
            result=dict(version=VERSION,requested=self.requested,active=bool(self.game and self.requested),
                        message=self.message,gesture='Left Alt + right click',classRequired=6,
                        damageMultiplier=3,travelling=self.flight is not None,last=self.last)
            result.update(skill=self.skill,surprise=self.surprise,omegaSeconds=1.0,groundSeconds=3.0,
                          lingering=len(self.aftermaths),recast='on-impact')
            if self.game:
                try:
                    result.update(casts=self.game.words(self.base+DATA+8)[0],hits=self.game.words(self.base+DATA+16)[0],
                                  blocked=self.game.words(self.base+DATA+20)[0],pid=self.game.pid)
                except OSError:result['active']=False
            return result

    def set(self,enabled=None,skill=None,surprise=None):
        if enabled is not None and not isinstance(enabled,bool):raise ValueError('Aç veya Kapat seçilmeli.')
        if skill is not None and skill not in ('omega','meteor'):raise ValueError('Bilinmeyen özel yetenek.')
        if surprise is not None and not isinstance(surprise,bool):raise ValueError('Sürpriz mod seçimi geçersiz.')
        if enabled is None and skill is None and surprise is None:raise ValueError('Yetenek ayarı eksik.')
        with self.lock:
            if enabled is not None:self.requested=enabled
            if skill is not None:self.skill=skill
            if surprise is not None:self.surprise=surprise
            SETTINGS.write_text(json.dumps({'enabled':self.requested,'skill':self.skill,'surprise':self.surprise},indent=2),'utf8')
            self.aftermaths=[]
            if self.game:
                self.game.write(self.base+DATA+4,b'\0'*4);self.flight=None
                self.game.write(self.base+DATA+60,b'\0'*4)
                self.sequence=self.game.words(self.base+DATA+8)[0]
                self.game.write(self.base+DATA+156,struct.pack('<2I',int(self.skill=='meteor'),self.surprise))
                self.game.write(self.base+DATA+120,b'\0'*4);self._publish([])
                self.game.write(self.base+DATA+4,struct.pack('<I',self.requested))
            self.message='Sol Alt + sağ tık · yalnızca Warrior · Attack ×3.' if self.requested else 'Özel yetenekler kapalı.'
        self.start();return self.info()

    def _attach(self):
        game=Game(write=True);installed=[]
        try:
            game.state()
            for span in PLAN['verified']:
                if hashlib.sha256(game.read(span['address'],span['length'])).hexdigest()!=span['sha256']:
                    raise RuntimeError(f"Omega: özgün işlev doğrulanamadı ({span['address']:08x}).")
            packet=remote_export(game,'RKC_UPDIB.dll',PACKET);calc=remote_export(game,'RKC_RPGSCRN.dll',CALC)
            for address,size,digest in ((packet,0x140,'12fde797624a1432a1fc1ab8261aea95a999a307b77360bfacd8a47d4fd0d2de'),
                    (calc,0x4c,'017f757c2afde317c2d7ed9f63d882fd1e63a4f06a939480fa1df37a57f6eb8e')):
                raw=bytearray(game.read(address,size))
                if address==packet:
                    if struct.unpack_from('<I',raw,3)[0]!=packet-0x1960+0x8048:raise RuntimeError('Omega: efekt modülü tanınmadı.')
                    struct.pack_into('<I',raw,3,0x10008048)
                if hashlib.sha256(raw).hexdigest()!=digest:raise RuntimeError('Omega: çizim işlevi tanınmadı.')
            tick=remote_tick_count(game)
            base=Alloc(game.h,None,SIZE,0x3000,0x40);check(base,'Allocate Omega beam')
            image=bytearray(make_image(base,packet,calc,tick,self.requested))
            struct.pack_into('<2I',image,DATA+156,int(self.skill=='meteor'),self.surprise)
            game.write(base,bytes(image));check(Flush(game.h,base,DATA),'Flush Omega beam')
            for address,original,offset in ((INPUT_HOOK,INPUT_ORIGINAL,0),(RENDER_HOOK,RENDER_ORIGINAL,0x1000)):
                after=b'\xe9'+struct.pack('<i',base+offset-address-5)+b'\x90'
                game.patch_at(address,original,after);installed.append((address,original,after))
            self.game=game;self.base=base;self.detours=installed;self.sequence=0
            self.message='Sol Alt + sağ tık · yalnızca Warrior · Attack ×3.'
            folder=ROOT/'omega-sessions';folder.mkdir(exist_ok=True)
            (folder/f'{game.pid}-{time.time_ns()}-attach.json').write_text(json.dumps(dict(pid=game.pid,base=base,
                version=VERSION,hooks=[dict(address=a,before=b.hex(),after=c.hex()) for a,b,c in installed],
                gameFileModified=False),indent=2),'utf8')
        finally:
            if game is not self.game:
                for a,b,c in reversed(installed):game.patch_at(a,c,b)
                game.close()

    def _publish(self,records):
        game=self.game;d=self.base+DATA
        records=list(records);now=time.monotonic()
        if self.aftermaths:
            try:
                state=game.state()
                warrior=game.words(state['player']+0x2c)[0]==6
                self.aftermaths=[f for f in self.aftermaths if warrior and f['player']==state['player']
                    and f['map']==state['map'] and 0<=now-f['impact']<GROUND_SECONDS]
            except (OSError,RuntimeError):self.aftermaths=[]
            for effect in self.aftermaths:records.extend(self._meteor_records(effect,now))
        active,reader=game.words(d+132,2)
        choices=[self.base+n for n in BUFFERS if self.base+n not in (active,reader)]
        if not choices:return
        target=choices[0];records=records[:4096]
        flight=self.flight or (self.aftermaths[-1] if self.aftermaths else None)
        raw=bytearray(struct.pack('<4I',len(records),flight['map'] if flight else 0,flight['player'] if flight else 0,0))
        for record in records:raw.extend(struct.pack('<6i',*record))
        game.write(target,bytes(raw));game.write(d+132,struct.pack('<I',target))

    def _command(self,kind,points=()):
        d=self.base+DATA;game=self.game
        if game.words(d+60)[0]:raise RuntimeError('Omega: önceki oyun çağrısı bitmedi.')
        if kind==1:
            if not 1<=len(points)<=64:raise ValueError('Invalid Omega collision batch')
            game.write(self.base+0x2400,b''.join(struct.pack('<2i',*p) for p in points))
            game.write(d+84,struct.pack('<I',len(points)))
        game.write(d+64,b'\0'*4);game.write(d+60,struct.pack('<I',kind))
        until=time.monotonic()+.9
        while time.monotonic()<until and not self.stop.wait(.002):
            if game.words(d+60)[0]==0:return game.words(d+64)[0]
        raise RuntimeError('Omega: oyun duraklatıldı veya giriş döngüsü bekleniyor.')

    def _begin(self,words):
        if words[41]==1:return self._begin_meteor(words)
        player,map_pointer,ident,pointer,x,y,tx,ty,damage=words[6:15]
        signed=lambda n:n if n<0x80000000 else n-0x100000000
        start=(signed(x),signed(y));target=(signed(tx),signed(ty))
        scene=Scene(self.game,map_pointer);a=project(start,scene.scale);b=project(target,scene.scale)
        route=find_route(a,b,scene.clear)
        blocked=route is None
        if blocked:route=wall_route(a,b,scene.clear)
        now=time.monotonic()
        self.flight=dict(player=player,map=map_pointer,id=ident,pointer=pointer,damage=damage,scene=scene,
                         route=route,distance=0,total=length(route),lastTime=now,started=now,ended=None,
                         blocked=blocked,lastTarget=target,lastAim=now,replans=0,deadline=now+1.0)
        self.last=dict(damage=damage,pathPoints=len(route),pathPixels=round(length(route)),noPath=blocked)
        self.message='Omega yolunu izliyor.' if not blocked else 'Yol kapalı · ilk engelde sönecek.'

    def _valid_target(self,f):
        state=self.game.state()
        if state['player']!=f['player'] or state['map']!=f['map']:return None
        if self.game.words(f['player']+0x2c)[0]!=6:return None
        # This pointer is read-only. The native hit gate resolves the stable ID
        # and verifies kind + pointer again before it can perform any write.
        raw=self.game.read(f['pointer'],0xd8)
        if struct.unpack_from('<I',raw,4)[0]!=f['id'] or struct.unpack_from('<I',raw,0x5c)[0]!=f['map'] or struct.unpack_from('<i',raw,0xd4)[0]<=0:return None
        return struct.unpack_from('<2i',raw,0x18)

    def _draw(self,now):
        f=self.flight;scene=f['scene'];records=[];path=f['route'];travel=f['distance']
        age=0 if f['ended'] is None else now-f['ended'];fade=max(0,1-age/.15)
        if fade<=0:
            self.flight=None;self.game.write(self.base+DATA+120,b'\0'*4);self._publish([]);return
        spacing=max(2.4,travel/850)
        for i in range(max(1,math.ceil(travel/spacing))+1):
            at=min(travel,i*spacing);p=along(path,at);x,y=unproject(p,scene.scale)
            height=-43+14*at/max(f['total'],1)
            glow=fade*(.55+.45*(at/max(travel,1)))
            sprite_id=max(0,min(7,round(glow*7)))
            records.append((round(x),round(y),0,round(height),sprite_id,0))
        head=along(path,travel);x,y=unproject(head,scene.scale)
        if f['ended'] is None:
            for i in range(8):
                angle=now*4+i*2.399;radius=2+(i%3)*2
                records.append((round(x),round(y),round(math.cos(angle)*radius),round(-29+math.sin(angle)*radius),23-i%5,0))
        elif f['blocked']:
            for i in range(7):
                angle=i*2.399;radius=age*19
                records.append((round(x),round(y),round(math.cos(angle)*radius),round(-29-age*22+math.sin(angle)*radius),8+min(7,int(age/.55*7)),0))
        else:
            for i in range(12):
                angle=i*2.399;radius=age*65
                records.append((round(x),round(y),round(math.cos(angle)*radius),round(-29+math.sin(angle)*radius),16+max(0,min(7,int(fade*7))),0))
        self._publish(records)

    def _tick_flight(self,now):
        f=self.flight
        if f['ended'] is not None:self._draw(now);return
        target=self._valid_target(f)
        if target is None:
            self.flight=None;self.game.write(self.base+DATA+120,b'\0'*4);self._publish([]);return
        scene=f['scene'];previous=f['lastTime'];f['lastTime']=now
        if now-f['started']>45:
            f['blocked']=True;f['ended']=now;self.last['reason']='flight-expired';self._draw(now);return
        if not f['blocked'] and now-f['lastAim']>.28:
            f['lastAim']=now
            if math.dist(project(target,scene.scale),f['route'][-1])>10:
                old=prefix(f['route'],f['distance']);head=old[-1]
                direction=heading(*old[-2:]) if len(old)>1 else 8
                new=find_route(head,project(target,scene.scale),scene.clear,max_nodes=40000,initial_heading=direction)
                if new is not None:
                    f['route']=simplify(old+new[1:]);f['total']=length(f['route']);f['lastTarget']=target
        end=deadline_distance(f['distance'],f['total'],previous,now,f['deadline'])
        if end>f['distance']:
            # Probe the real traversed polyline, densely enough to catch a door
            # closing after planning; all calls execute on the original thread.
            n=max(1,math.ceil((end-f['distance'])*100/min(scene.scale)/35))
            points=[tuple(round(v) for v in unproject(along(f['route'],f['distance']+(end-f['distance'])*i/n),scene.scale)) for i in range(1,n+1)]
            valid=True;blocked_point=None
            for at in range(0,len(points),64):
                batch=points[at:at+64];status=self._command(1,batch)
                if status!=1:
                    valid=False
                    if status==2:
                        index=self.game.words(self.base+DATA+88)[0]
                        if index<len(batch):blocked_point=batch[index]
                    break
            if not valid:
                scene.refresh_obstacles();head=along(f['route'],f['distance'])
                if blocked_point is not None:
                    scene.learn_block(blocked_point,unproject(head,scene.scale));self.last['lastBlockedWorld']=blocked_point
                old=prefix(f['route'],f['distance']);direction=heading(*old[-2:]) if len(old)>1 else 8
                new=find_route(head,project(target,scene.scale),scene.clear,max_nodes=40000,initial_heading=direction)
                if new is not None and blocked_point is not None:
                    f['replans']+=1;f['route']=simplify(old+new[1:]);f['total']=length(f['route'])
                    self.last.update(replans=f['replans'],learnedObstacles=len(scene.native_blocks))
                else:
                    f['blocked']=True;f['ended']=now;self.last['reason']='native-obstacle-no-alternative' if blocked_point else 'native-target-invalid'
                self._draw(now);return
            f['distance']=end
        if f['distance']>=f['total']:
            if not f['blocked']:
                actual=project(target,scene.scale)
                if math.dist(actual,f['route'][-1])>2:
                    tails=[simplify(t) for t in link(f['route'][-1],actual)]
                    tail=next((t for t in tails if all(scene.clear(a,b) for a,b in zip(t,t[1:]))
                               and all(turn_ok(*r) for r in zip(t,t[1:],t[2:]))
                               and (len(f['route'])<2 or len(t)<2 or turn_ok(*f['route'][-2:],t[1]))),None)
                    if tail is None:
                        direction=heading(*f['route'][-2:]) if len(f['route'])>1 else 8
                        tail=find_route(f['route'][-1],actual,scene.clear,max_nodes=40000,initial_heading=direction)
                    if tail:
                        f['route']=simplify(f['route']+tail[1:]);f['total']=length(f['route']);self._draw(now);return
                    f['blocked']=True
                else:
                    head=tuple(round(v) for v in unproject(f['route'][-1],scene.scale))
                    self.game.write(self.base+DATA+72,struct.pack('<2i',*head))
                    result=self._command(2)
                    before,after=self.game.words(self.base+DATA+112,2)
                    self.last.update(hit=result==3,hpBefore=before,hpAfter=after,actualDamage=before-after if result==3 else 0)
                    f['blocked']=result!=3
            f['ended']=now
            self.message='İsabet · Attack ×3.' if not f['blocked'] else 'Işın engelde söndü.'
            folder=ROOT/'omega-sessions';folder.mkdir(exist_ok=True)
            self.last['pathPoints']=len(f['route']);self.last['pathPixels']=round(f['total'])
            self.last['travelSeconds']=round(time.monotonic()-f['started'],3)
            (folder/f'{self.game.pid}-{time.time_ns()}-cast.json').write_text(json.dumps(dict(**self.last,
                route=f['route'],target=f['id'],blocked=f['blocked']),indent=2),'utf8')
        self._draw(now)

    def inspect(self):
        with self.lock:
            game=self.game or Game();own=game is not self.game
            try:
                state=game.state();p=state['player'];projection=game.words(0x482d14)[0]
                return dict(**state,classId=game.words(p+0x2c)[0],attack=game.words(p+0x1b4)[0],
                            projection=game.words(projection+0x18,2),info=self.info(),
                            native=game.words(self.base+DATA,48) if self.game else None,
                            flight={k:v for k,v in (self.flight or {}).items() if k!='scene'})
            finally:
                if own:game.close()

    def _follow(self):
        while not self.stop.wait(.018 if self.flight or self.aftermaths else .08):
            with self.lock:
                try:
                    if self.game:
                        code=W.DWORD()
                        if not GetExitCodeProcess(self.game.h,C.byref(code)) or code.value!=259:
                            self.game.close();self.game=None;self.base=0;self.flight=None;self.aftermaths=[];self.detours=[]
                    if self.requested and not self.game and LOCK.acquire(False):
                        try:self._attach()
                        finally:LOCK.release()
                    if not self.game or not self.requested:continue
                    self.game.write(self.base+DATA+80,struct.pack('<I',GetTickCount()))
                    words=self.game.words(self.base+DATA,48)
                    if words[2]!=self.sequence:
                        self.sequence=words[2];self._begin(words)
                    if self.flight:
                        if self.flight.get('kind')=='meteor':self._tick_meteor(time.monotonic())
                        else:self._tick_flight(time.monotonic())
                    elif self.aftermaths:self._publish([])
                except Exception as error:
                    self.message=str(error);self.flight=None
                    if self.game:
                        try:
                            self.game.write(self.base+DATA+60,b'\0'*4)
                            self.game.write(self.base+DATA+120,b'\0'*4);self._publish([])
                        except OSError:self.game.close();self.game=None;self.base=0

    def close(self):
        self.stop.set()
        if self.worker and self.worker is not threading.current_thread():self.worker.join(2)
        with self.lock:
            if not self.game:return
            game=self.game
            try:
                game.write(self.base+DATA+4,b'\0'*4)
                for a,b,c in reversed(self.detours):game.patch_at(a,c,b)
                # Native double-buffered render packets may still own atlas DIBs.
                self.retired.append((game.pid,self.base))
            finally:game.close();self.game=None;self.base=0;self.flight=None;self.aftermaths=[]
