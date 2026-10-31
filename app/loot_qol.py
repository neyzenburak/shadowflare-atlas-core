"""Native, main-thread proximity pickup and durable consumable stacks."""
import atexit,hashlib,json,struct,threading,time
from contextlib import contextmanager
from live_drop import Game,ROOT,LOCK,Alloc,Free,Flush,Protect,check,C,W,backup_saves
from drop_event import remote_export
from hover_lifetime import GetExitCodeProcess
from loot_qol_core import image,DATA,SIZE,OFFSETS

VERSION=8
SETTINGS=ROOT/'qol-settings.json'
HOOKS=(
    (0x443496,'8bf133ed57','update'),
    (0x466c40,'518b0133d2','consume'),
    (0x4661c0,'83ec0c5355','price'),
    (0x465e52,'5f5e5d5bc21c00','draw'),
    (0x445a40,'568bf183be2416000001','right'),
    (0x443341,'8b8e70150000','split'),
    (0x449fbd,'833d3cce480001','pickup'),
    (0x446ce2,'e8d9fe0100','insert'),
    (0x41b541,'8946048b8bcc000000','ground_save'),
    (0x462d30,'64a100000000','factory'),
    (0x4663c0,'8b44240489411c','identified'),
)

def patches(base):
    return [(at,bytes.fromhex(before),(b'\xe8' if name=='insert' else b'\xe9')+struct.pack('<i',base+OFFSETS[name]-at-5)+b'\x90'*(len(bytes.fromhex(before))-5)) for at,before,name in HOOKS]

def resident_patches(base,version):
    return [(at,old,(b'\xe9'+after[1:] if at==0x446ce2 and version<3 else after))
            for at,old,after in patches(base) if version>=5 or at!=0x4663c0]

def valid_radius(value):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or int(value)!=value or not 1<=value<=20:
        raise ValueError('Toplama halkası 1–20 arasında bir tam sayı olmalı.')
    return int(value)

def quantity(kind,instance):
    n=instance&0xffff
    return n if kind==3 and instance&0xffff0000==0x53540000 and 2<=n<=999 else 1

class LootQoL:
    def __init__(self,gold_policy=None):
        self.game=None;self.base=0;self.backup=None;self.message='Oyun bekleniyor.'
        self.auto=False;self.stacks=False;self.radius=1;self.manifest=None
        self.merge_pending=False
        self.paused=0
        self.gold_policy=gold_policy
        self.lock=threading.RLock();self.stop=threading.Event();self.worker=None
        try:
            saved=json.loads(SETTINGS.read_text('utf8'))
            self.auto=saved.get('autoPickup') is True;self.stacks=saved.get('potionStacks') is True
            self.radius=valid_radius(saved.get('radius',1))
        except (OSError,ValueError,TypeError):pass
        atexit.register(self.close)
    def start(self):
        with self.lock:
            if self.worker is None:
                self.worker=threading.Thread(target=self._follow,daemon=True);self.worker.start()
    def info(self):
        with self.lock:
            counters=(0,)*4;protected=0;manual_gold=0
            if self.game:
                try:
                    counters=self.game.words(self.base+DATA+12,4)
                    protected=self.game.words(self.base+DATA+64)[0]
                    manual_gold=self.game.words(self.base+DATA+72)[0]
                except OSError:self.game.close();self.game=None;self.base=0
            active=self.game is not None
            return dict(version=VERSION,active=active,pid=self.game.pid if active else None,
                        autoPickup=self.auto,potionStacks=self.stacks,radius=self.radius,maxRadius=20,
                        pickedUp=counters[0],mergedUnits=counters[1],splits=counters[2],consumedUnits=counters[3],
                        protectedIdentificationUpdates=protected,manualGoldSkipped=manual_gold,stackLimit=999,message=self.message,backup=self.backup)
    def set(self,body):
        if not isinstance(body,dict) or not body or set(body)-{'autoPickup','potionStacks','radius','merge'}:
            raise ValueError('Geçersiz ganimet ayarı.')
        for key in ('autoPickup','potionStacks','merge'):
            if key in body and not isinstance(body[key],bool):raise ValueError('Aç/kapat değeri geçersiz.')
        radius=valid_radius(body['radius']) if 'radius' in body else self.radius
        with self.lock:
            old=self.stacks
            self.auto=body.get('autoPickup',self.auto);self.stacks=body.get('potionStacks',self.stacks);self.radius=radius
            self.merge_pending=self.stacks and (self.merge_pending or not old or body.get('merge',False))
            SETTINGS.write_text(json.dumps(dict(autoPickup=self.auto,potionStacks=self.stacks,radius=self.radius),indent=2),'utf8')
            if self.game:
                self.refresh_gold_policy()
                self.game.write(self.base+DATA,struct.pack('<3I',self.auto and not self.paused,self.stacks,self.radius))
                self.game.write(self.base+DATA+48,struct.pack('<I',int(self.merge_pending)));self.merge_pending=False
        self.start()
        return self.info()
    @contextmanager
    def pause_pickup(self):
        """Let one-item spawn verify its ground result before auto collection."""
        with self.lock:
            self.paused+=1
            if self.game:self.game.write(self.base+DATA,b'\0'*4)
        try:yield
        finally:
            with self.lock:
                self.paused-=1
                if self.game:self.game.write(self.base+DATA,struct.pack('<I',self.auto and not self.paused))
    def refresh_gold_policy(self):
        with self.lock:
            if self.game and self.gold_policy:
                self.game.write(self.base+DATA+68,struct.pack('<I',self.gold_policy(self.game)))
    def _follow(self):
        while not self.stop.wait(.6):
            with self.lock:
                try:
                    if self.game:
                        status=W.DWORD()
                        if not GetExitCodeProcess(self.game.h,C.byref(status)) or status.value!=259:
                            self.game.close();self.game=None;self.base=0
                        elif any(self.game.read(at,len(after))!=after for at,_,after in patches(self.base)):
                            raise RuntimeError('Ganimet yamasının girişlerinden biri değişti.')
                    if not self.game and LOCK.acquire(False):
                        try:self._attach()
                        finally:LOCK.release()
                except Exception as error:self.message=str(error)
    def _attach(self):
        game=Game(write=True);base=0;previous=[];counters=None
        try:
            # Hooks stay resident after closing the helper, so existing stacks
            # remain usable. An authenticated local manifest permits adoption
            # after restart; never interpret an arbitrary detour as our own.
            first=game.read(HOOKS[0][0],5)
            folder=ROOT/'qol-sessions';folder.mkdir(exist_ok=True)
            if first!=bytes.fromhex(HOOKS[0][1]):
                for path in folder.glob(f'{game.pid}-*.json'):
                    meta=json.loads(path.read_text('utf8'));candidate=meta['base']
                    if meta.get('version') not in (1,2,3,4,5,6,7,VERSION):continue
                    resident_hooks=resident_patches(candidate,meta['version'])
                    if all(game.read(at,len(after))==after for at,_,after in resident_hooks):
                        expected=image(candidate)
                        resident=game.read(candidate,DATA)
                        if resident==expected[:DATA] and resident_hooks==patches(candidate):
                            base=candidate;self.manifest=str(path);self.backup=meta.get('backup');break
                        if hashlib.sha256(resident).hexdigest()!=meta.get('codeSHA256'):continue
                        # Keep the prior allocation alive for any native call
                        # returning into it. Switch all entries while suspended;
                        # an old continuation can safely finish its original ABI.
                        previous=resident_hooks;counters=game.read(candidate+DATA+12,16)
                        game.write(candidate+DATA,b'\0'*8)
                        with game.suspended():
                            for at,old,after in reversed(previous):game.patch_at(at,after,old)
                        self.backup=meta.get('backup');break
                if not base and not previous:raise RuntimeError('Ganimet girişindeki yama tanınmadı; üzerine yazılmadı.')
            if not base:
                for at,before,_ in patches(0x10000000):
                    if game.read(at,len(before))!=before:raise RuntimeError(f'Ganimet giriş noktası tanınmadı: {at:08x}')
                self.backup=backup_saves(game)
                base=Alloc(game.h,None,SIZE,0x3000,0x40);check(base,'Allocate loot QoL')
                raw=image(base)
                struct.pack_into('<3I',raw,DATA,self.auto and not self.paused,self.stacks,self.radius)
                struct.pack_into('<II',raw,DATA+40,remote_export(game,'kernel32.dll','GetTickCount'),remote_export(game,'user32.dll','GetKeyState'))
                struct.pack_into('<I',raw,DATA+48,int(self.merge_pending))
                if self.gold_policy:struct.pack_into('<I',raw,DATA+68,self.gold_policy(game))
                if counters:raw[DATA+12:DATA+28]=counters
                game.write(base,bytes(raw));check(Flush(game.h,base,DATA),'Flush loot QoL')
                installed=[]
                try:
                    # Install together: the game cannot observe only half of
                    # the pickup/save/consume hooks during a running frame.
                    for _ in range(100):
                        with game.suspended() as handles:
                            if any(at<=ip<at+len(old) for ip in game.ips(handles) for at,old,_ in patches(base)):continue
                            for at,old,after in patches(base):
                                game.patch_at(at,old,after);installed.append((at,old,after))
                            break
                        time.sleep(.005)
                    else:raise RuntimeError('Ganimet yaması için güvenli giriş bulunamadı.')
                except Exception:
                    for at,old,after in reversed(installed):game.patch_at(at,after,old)
                    raise
                path=folder/f'{game.pid}-{time.time_ns()}.json'
                path.write_text(json.dumps(dict(version=VERSION,pid=game.pid,base=base,size=SIZE,backup=self.backup,
                    gameFileModified=False,codeSHA256=hashlib.sha256(raw[:DATA]).hexdigest()),indent=2),'utf8');self.manifest=str(path)
            self.game=game;self.base=base
            self.refresh_gold_policy()
            game.write(base+DATA,struct.pack('<3I',self.auto and not self.paused,self.stacks,self.radius))
            if self.merge_pending:game.write(base+DATA+48,struct.pack('<I',1));self.merge_pending=False
            self.message='Oyuna bağlı.'
        finally:
            if game is not self.game:
                if previous:
                    with game.suspended():
                        for at,old,after in previous:
                            if game.read(at,len(old))==old:game.patch_at(at,old,after)
                # Never free an installed detour target if writing its manifest
                # failed. The running character's stack handlers must survive.
                if base and game.read(HOOKS[0][0],5)==bytes.fromhex(HOOKS[0][1]):Free(game.h,base,0,0x8000)
                game.close()
    def close(self):
        self.stop.set()
        if self.worker and self.worker is not threading.current_thread():self.worker.join(2)
        with self.lock:
            if self.game:
                try:self.game.write(self.base+DATA,b'\0'*8)
                finally:self.game.close();self.game=None;self.base=0
