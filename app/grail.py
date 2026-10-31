"""Local Premium grail: baseline evidence plus native successful pickup events."""
import atexit,json,struct,threading,time
from pathlib import Path
from live_drop import Game,ROOT,LOCK,Alloc,Free,Flush,check,backup_saves,catalogue
from grail_store import GrailStore,read_save,save_name,character_name,now
from grail_native import make_image,patches,decode_record,DATA,RING,CAPACITY,RECORD,SIZE,INSERT,INSERT_BYTES,PICKUP,PICKUP_BYTES,DELETE,DELETE_BYTES,POLICY
from grail_policy import policy_image,found_keys

VERSION=2

class Grail:
    def __init__(self):
        self.store=None;self.game=None;self.base=0;self.installed=[];self.sequence=0
        self.current=None;self.message='Karakter bekleniyor.';self.backup=None
        self.directory=None;self.missed=0;self.events=[];self.revision=0;self.last_scan=0
        self.lock=threading.RLock();self.stop=threading.Event();self.worker=None
        self.items={i['key']:i for i in catalogue()['items'] if i['rarity']==2}
        self.policy_binding=None;self.policy_revision=-1;self.policy_found=frozenset();self.policy_ready=False
        atexit.register(self.close)
    def start(self):
        with self.lock:
            if self.store is None:self.store=GrailStore(ROOT/'grail-data/chronicle.sqlite3',self.items)
            self.directory=self.store.setting('gameDirectory')
            self.missed=int(self.store.setting('missedEvents') or 0)
            if self.worker is None:self.worker=threading.Thread(target=self._follow,daemon=True);self.worker.start()
    def info(self):
        with self.lock:return dict(version=VERSION,active=self.game is not None,current=self.current,message=self.message,revision=self.revision,missedEvents=self.missed,recent=self.events[-12:])
    def policy(self,pid):
        """The active save's policy, never the profile browsed in the web UI."""
        with self.lock:
            ready=bool(self.game and self.game.pid==pid and self.policy_ready)
            return dict(address=self.base+POLICY if ready else 0,ready=ready,
                        profile=self.current if ready else None,foundKeys=sorted(self.policy_found) if ready else [])
    def original_bytes(self,game,address,size):
        """Validate our exact installed detour before projecting original bytes.

        Allows another Atlas feature to keep its native SHA checks intact.
        A foreign modification is never hidden by this projection.
        """
        with self.lock:
            raw=bytearray(game.read(address,size))
            if not self.game or game.pid!=self.game.pid:return bytes(raw)
            for at,before,after in self.installed:
                lo=max(at,address);hi=min(at+len(after),address+size)
                if lo>=hi:continue
                if game.read(at,len(after))!=after:raise RuntimeError('Grail yaması başka bir işlem tarafından değiştirildi.')
                raw[lo-address:hi-address]=before[lo-at:hi-at]
            return bytes(raw)
    def view(self,profile=None):
        with self.lock:
            result=self.store.view(profile or self.current) if self.store else dict(profiles=[],selected=None,entries={},total=len(self.items))
            return {**result,**self.info()}
    def mark(self,profile,key,found):
        with self.lock:
            if not self.store:raise ValueError('Grail henüz açılmadı.')
            self.store.mark(profile,key,found);self.revision+=1;return self.view(profile)
    def _filename(self,game):
        obj=game.words(0x482dcc)[0]
        if not obj:raise ValueError('Karakter kayıt dosyası bekleniyor.')
        pointer=game.words(obj)[0]
        return save_name(game.read(pointer,14).split(b'\0',1)[0].decode('ascii'))
    def _identity(self,game,state):
        raw=game.read(state['player']+0x10,0x28)
        return self._filename(game),character_name(raw),struct.unpack_from('<I',raw,0x24)[0]
    def _owned(self,game,state):
        owned=set();player=state['player']
        with game.suspended():
            pointers=list(game.words(player+0x4e8,11))
            for head in game.words(player+0x514,17):
                seen=set()
                while head:
                    if head in seen:raise ValueError('Envanter bağlantısı döngü içeriyor.')
                    seen.add(head);pointers.append(head);head=game.words(head+0x8c)[0]
            for p in set(pointers)-{0}:
                kind=game.words(p+0xc)[0];ident=game.words(p+0x14)[0];key=f'{kind}:{ident}'
                if key in self.items:owned.add(key)
        return owned
    def _scan_saves(self):
        if not self.directory or time.monotonic()-self.last_scan<10:return
        self.last_scan=time.monotonic()
        for p in (Path(self.directory)/'Save').glob('*'):
            if p.suffix.lower()!='.ssv':continue
            try:
                data=read_save(p.read_bytes())
                ident=self.store.observe(self.directory,p.name,data['name'],data['level'])
                if not self.store.setting('saveSeeded:'+ident):
                    self.store.observe(self.directory,p.name,data['name'],data['level'],data['owned'])
                    self.store.setting('saveSeeded:'+ident,'1');self.revision+=1
            except (ValueError,OSError,struct.error):continue # autosave may be writing
    def _follow(self):
        while not self.stop.wait(.25):
            with self.lock:
                try:
                    if self.game:
                        self._drain()
                        state=self.game.state();filename,name,level=self._identity(self.game,state)
                        self.current=self.store.observe(self.directory,filename,name,level)
                        self._seed_live(state,filename,name,level)
                        self._publish_policy(state)
                        self.message='Yerden çantaya alınan Premium eşyalar kaydediliyor.'
                    elif LOCK.acquire(False):
                        try:self._attach()
                        finally:LOCK.release()
                    self._scan_saves()
                except Exception as error:
                    self.message=str(error)
                    if self.game:
                        # A menu/dead character can be transient. Keep the native recorder.
                        try:self.game.read(self.base+DATA,4)
                        except OSError:self.game.close();self.game=None;self.base=0;self.current=None;self.policy_ready=False
    def _publish_policy(self,state,force=False):
        if not force and self.policy_revision==self.revision and self.policy_binding==(state['player'],self.current):return
        # Re-drain while the game is paused so publication cannot erase a found
        # flag committed by a pickup between the earlier drain and this write.
        with self.game.suspended():
            self._drain()
            state=self.game.state();filename,name,level=self._identity(self.game,state)
            self.current=self.store.observe(self.directory,filename,name,level)
            obj=self.game.words(0x482dcc)[0];pointer=self.game.words(obj)[0]
            raw_name=self.game.read(state['player']+0x10,12);raw_file=self.game.read(pointer,14)
            found=found_keys(self.store.view(self.current)['entries'])
            raw=policy_image(self.items,found,state['player'],raw_file,raw_name,ready=True)
            self.game.write(self.base+POLICY,raw)
            self.policy_binding=(state['player'],self.current);self.policy_revision=self.revision
            self.policy_found=found;self.policy_ready=True
    def _seed_live(self,state,filename,name,level):
        key='liveSeeded:'+self.current
        if not self.store.setting(key):
            self.store.observe(self.directory,filename,name,level,self._owned(self.game,state))
            self.store.setting(key,'1');self.revision+=1
    def _attach(self):
        game=Game(write=True);base=0;installed=[]
        try:
            state=game.state();filename,name,level=self._identity(game,state)
            self.directory=str(game.path.parent);self.store.setting('gameDirectory',self.directory)
            self._scan_saves()
            self.current=self.store.observe(self.directory,filename,name,level)
            # Establish current possessions before accepting any new pickup event.
            if not self.store.setting('liveSeeded:'+self.current):
                self.store.observe(self.directory,filename,name,level,self._owned(game,state))
                self.store.setting('liveSeeded:'+self.current,'1')
            for at,old in ((PICKUP,PICKUP_BYTES),(INSERT,INSERT_BYTES),(DELETE,DELETE_BYTES)):
                if game.read(at,len(old))!=old:raise RuntimeError(f'Grail işlevi tanınmadı: {at:08x}')
            self.backup=backup_saves(game)
            base=Alloc(game.h,None,SIZE,0x3000,0x40);check(base,'Allocate Premium chronicle')
            raw=make_image(base,self.items);game.write(base,raw);check(Flush(game.h,base,0x1000),'Flush Premium chronicle')
            for at,before,after in patches(base):game.patch_at(at,before,after);installed.append((at,before,after))
            self.game,self.base,self.installed,self.sequence=game,base,installed,0
            self._publish_policy(state,force=True)
            folder=ROOT/'grail-sessions';folder.mkdir(exist_ok=True)
            (folder/f'{game.pid}-{time.time_ns()}.json').write_text(json.dumps(dict(pid=game.pid,base=base,backup=self.backup,
                patches=[dict(address=a,before=b.hex(),after=c.hex()) for a,b,c in installed],gameFileModified=False),indent=2),'utf8')
            self.message='Yerden çantaya alınan Premium eşyalar kaydediliyor.';self.revision+=1
        finally:
            if game is not self.game:
                for at,before,after in reversed(installed):game.patch_at(at,after,before)
                if base:
                    # On an install failure, drain all entered wrappers before freeing.
                    self._wait_idle(game,base)
                game.close()
    def _drain(self):
        end=self.game.words(self.base+DATA+4)[0]
        available=(end-self.sequence)&0xffffffff
        if available>CAPACITY:
            self.missed+=available-CAPACITY;self.sequence=(end-CAPACITY)&0xffffffff
            self.store.setting('missedEvents',str(self.missed))
        while self.sequence!=end:
            sequence=(self.sequence+1)&0xffffffff;at=self.base+RING+((sequence-1)&(CAPACITY-1))*RECORD
            raw=self.game.read(at,RECORD)
            if self.game.words(at)[0]!=sequence or struct.unpack_from('<I',raw)[0]!=sequence:break
            event=decode_record(raw,sequence)
            filename=save_name(event['filename'])
            ident=self.store.observe(self.directory,filename,event['name'],event['level'])
            first=self.store.collect(ident,event['key'],event['map'])
            self.events.append(dict(profile=ident,key=event['key'],name=self.items.get(event['key'],{}).get('name',event['key']),first=first,time=now()))
            self.events=self.events[-32:];self.sequence=sequence;self.revision+=1
    def _wait_idle(self,game,base):
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            with game.suspended() as handles:
                safe=game.words(base+DATA)[0]==0 and not any(base<=ip<base+SIZE for ip in game.ips(handles))
            if safe:check(Free(game.h,base,0,0x8000),'Free Premium chronicle');return
            time.sleep(.01)
    def close(self):
        self.stop.set()
        if self.worker and self.worker is not threading.current_thread():self.worker.join(2)
        with self.lock:
            if not self.game:return
            try:
                for at,before,after in reversed(self.installed):self.game.patch_at(at,after,before)
                self._drain();self._wait_idle(self.game,self.base)
            except (OSError,RuntimeError):pass
            finally:self.game.close();self.game=None;self.base=0;self.policy_ready=False
