"""Reversible ground visibility, native unidentified liquidation, manual gold.

No inventory or equipment bytes are edited by visibility. Sale currency uses a
separate, character-scoped pickup exclusion table; ordinary gold is unchanged.
"""
import atexit,hashlib,json,struct,threading,time
from live_drop import Game,ROOT,LOCK,HOOK,ORIGINAL,Alloc,Free,Flush,check,C,W
from hover_lifetime import GetExitCodeProcess
from ground_loot_core import image,DATA,SIZE,OFFSETS
from operation_save import optional_save,save_choice

VERSION=2
DRAW_HOOK=0x458a1c
DRAW_ORIGINAL=bytes.fromhex('8b8ecc000000')
SETTINGS=ROOT/'ground-loot-settings.json'
SESSIONS=ROOT/'ground-loot-sessions'
LEDGER=ROOT/'sale-gold-ledger.json'
VERIFIED=((0x427970,128,'09a36bdfe4e5b98124c6955f4b07297bd4e919a457e291ecc12aa3d2ec41fa3e'),
          (0x427a00,57,'de8c5c8fc96d644902d36c02c476cd4b802b2c9932bf962abca77e7fb22aad4b'),
          (0x465640,90,'f3f55fe46435dce3f690df49aaf654fc73d2c784a24e2a6ca862c680ada8ca95'),
          (0x4661c6,454,'7ccb1c99c6eca710857c7d5bc0d88bd83fbc1e35d4ba24ea82a936241536ea27'))

class GroundSaleError(RuntimeError):
    """Currency may exist without a verified pickup exemption."""


def eligible(category,rarity):return category in (0,1,2) and rarity in (0,1)
def binding(state):return ':'.join(str(state[k]) for k in ('pid','player','map'))
def detour(at,target,n=6):return b'\xe9'+struct.pack('<i',target-at-5)+b'\x90'*(n-5)
def selected_ids(value):
    if value is None:return None
    if not isinstance(value,list) or not value or any(isinstance(i,bool) or not isinstance(i,int) or not 0<=i<=0xffffffff for i in value):
        raise ValueError('Geçerli dünya eşya kimlikleri gerekli.')
    return set(value)


def ground_equipment(game,state):
    """Untrusted snapshot: the native request revalidates every world ID."""
    manager=game.words(state['map']+0x30)[0];p=game.words(manager+8)[0]
    seen=set();rows=[]
    while p:
        if p in seen:raise RuntimeError('Yerdeki eşya listesi değişti; yeniden dene.')
        seen.add(p);kind,_,obj,next_pointer=game.words(p,4)
        if kind==3 and obj:
            item=game.words(obj+0xcc)[0]
            if item:
                category,_,ident,rarity=game.words(item+0xc,4)
                if eligible(category,rarity):
                    rows.append(dict(item=item,identifier=game.words(obj+4)[0],category=category,id=ident,rarity=rarity))
        p=next_pointer
    return rows


class SaleGoldLedger:
    """A separate native predicate; gold itself keeps its normal save format.

    Rows match owner + map + amount + position, then bind to the live entity ID.
    Thus reloads keep sale gold manual, and a reused pointer is never sufficient.
    Old immutable tables are retained until process exit to protect native reads.
    """
    def __init__(self):
        self.lock=threading.RLock();self.rows=[];self.generation=0;self.cache={}
        try:self.rows=json.loads(LEDGER.read_text('utf8'))['gold']
        except (OSError,ValueError,KeyError,TypeError):pass
    def policy(self,game):
        with self.lock:
            key=(game.pid,self.generation)
            if key in self.cache:return self.cache[key]
            raw=bytearray(struct.pack('<I',len(self.rows)))
            for r in self.rows:
                owner=bytes.fromhex(r['owner']);assert len(owner)==12
                same=r['pid']==game.pid
                raw.extend(owner+struct.pack('<6I',r['sid'],r['x'],r['y'],r['value'],r['map'] if same else 0,r['identifier'] if same else 0)+bytes.fromhex(r['file']).ljust(16,b'\0'))
            if not self.rows:self.cache[key]=0;return 0
            address=Alloc(game.h,None,(len(raw)+4095)&~4095,0x3000,0x04);check(address,'Allocate manual sale gold policy')
            game.write(address,bytes(raw));self.cache[key]=address;return address
    def register(self,game,state,gold):
        with self.lock:
            owner=game.read(state['player']+0x10,12).hex();sid=game.words(state['map']+4)[0]
            filename=game.read(game.words(game.words(0x482dcc)[0])[0],14).hex()
            for g in gold:self.rows.append(dict(owner=owner,file=filename,sid=sid,pid=game.pid,map=state['map'],**g))
            self.generation+=1
            temporary=LEDGER.with_suffix('.tmp')
            temporary.write_text(json.dumps({'version':1,'gold':self.rows},indent=2),'utf8');temporary.replace(LEDGER)


class GroundVisibility:
    def __init__(self):
        self.game=None;self.base=0;self.requested=False;self.message='Beyaz ve mavi ekipmanlar görünür.'
        self.lock=threading.RLock();self.stop=threading.Event();self.worker=None
        try:self.requested=json.loads(SETTINGS.read_text('utf8')).get('hidden') is True
        except (OSError,ValueError,TypeError):pass
        atexit.register(self.close)
    def start(self):
        with self.lock:
            if self.worker is None:self.worker=threading.Thread(target=self._follow,daemon=True);self.worker.start()
    def info(self):
        with self.lock:
            return dict(version=VERSION,requested=self.requested,active=bool(self.game),hidden=bool(self.game and self.requested),
                        pid=self.game.pid if self.game else None,message=self.message)
    def policy(self,pid):
        with self.lock:return self.base+DATA if self.game and self.game.pid==pid else 0
    def set(self,enabled):
        if not isinstance(enabled,bool):raise ValueError('Gizle/göster değeri aç/kapat olmalı.')
        with self.lock:
            self.requested=enabled
            SETTINGS.write_text(json.dumps({'hidden':enabled}),'utf8')
            if self.game:self.game.write(self.base+DATA,struct.pack('<I',enabled))
            self.message=('Beyaz ve mavi ekipmanlar gizli; Premium, altın ve tüketilebilirler görünür.' if self.game else 'Gizleme hazırlanıyor; oyun bağlantısı bekleniyor.') if enabled else 'Beyaz ve mavi ekipmanlar görünür.'
        self.start();return self.info()
    def _follow(self):
        while not self.stop.wait(.4):
            with self.lock:
                try:
                    if self.game:
                        result=W.DWORD()
                        if not GetExitCodeProcess(self.game.h,C.byref(result)) or result.value!=259:
                            self.game.close();self.game=None;self.base=0
                        elif self.game.read(DRAW_HOOK,6)!=detour(DRAW_HOOK,self.base):
                            raise RuntimeError('Yerdeki eşya çizim girişi değişti.')
                    if self.requested and not self.game and LOCK.acquire(False):
                        try:self._attach()
                        finally:LOCK.release()
                except Exception as e:self.message=str(e)
    def _attach(self):
        game=Game(write=True);base=0;installed=False
        try:
            game.state();before=game.read(DRAW_HOOK,6)
            SESSIONS.mkdir(exist_ok=True)
            if before!=DRAW_ORIGINAL:
                for path in SESSIONS.glob(f'{game.pid}-visibility-*.json'):
                    meta=json.loads(path.read_text('utf8'));candidate=meta['base']
                    if before==detour(DRAW_HOOK,candidate) and game.read(candidate,DATA)==image(candidate)[:DATA]:
                        base=candidate;installed=True;break
                if not base:raise RuntimeError('Eşya çizim yaması tanınmadı; üzerine yazılmadı.')
            if not base:
                base=Alloc(game.h,None,SIZE,0x3000,0x40);check(base,'Allocate ground visibility')
                raw=image(base);struct.pack_into('<I',raw,DATA,int(self.requested));game.write(base,bytes(raw))
                check(Flush(game.h,base,DATA),'Flush ground visibility')
                (SESSIONS/f'{game.pid}-visibility-{time.time_ns()}.json').write_text(json.dumps(dict(base=base,pid=game.pid,version=VERSION)),'utf8')
                game.patch_at(DRAW_HOOK,DRAW_ORIGINAL,detour(DRAW_HOOK,base));installed=True
            game.write(base+DATA,struct.pack('<I',self.requested));self.game,self.base=game,base
            self.message='Beyaz ve mavi ekipmanlar gizli; Premium, altın ve tüketilebilirler görünür.' if self.requested else 'Beyaz ve mavi ekipmanlar görünür.'
        finally:
            if game is not self.game:
                if base and not installed:Free(game.h,base,0,0x8000)
                game.close()
    def close(self):
        self.stop.set()
        if self.worker and self.worker is not threading.current_thread():self.worker.join(2)
        with self.lock:
            if self.game:
                try:
                    self.game.write(self.base+DATA,b'\0'*4)
                    self.game.patch_at(DRAW_HOOK,detour(DRAW_HOOK,self.base),DRAW_ORIGINAL)
                except OSError:pass
                finally:
                    # Premium beam may still hold this read-only flag address.
                    self.game.close();self.game=None;self.base=0


def sell_ground(expected_binding,ledger,refresh_policy,timeout=60,identifiers=None,dry_run=False,verified_reader=None,save_before=False):
    save_choice(save_before)
    chosen=selected_ids(identifiers)
    probe=Game()
    try:
        if binding(probe.state())!=expected_binding:raise ValueError('Karakter veya harita değişmiş; durumu yenile.')
    finally:probe.close()
    saved=optional_save(save_before and not dry_run,timeout)
    backup=saved['backup'] if saved else None
    if not LOCK.acquire(False):raise RuntimeError('Önceki oyun işlemi sürüyor.')
    game=None;base=0;installed=False;d=0;policy_published=False
    try:
        game=Game(write=True);state=game.state()
        if binding(state)!=expected_binding:raise ValueError('İstek hazırlanırken harita değişti; satış yapılmadı.')
        for at,n,digest in VERIFIED:
            raw=verified_reader(game,at,n) if verified_reader else game.read(at,n)
            if hashlib.sha256(raw).hexdigest()!=digest:raise RuntimeError(f'Satış işlevi tanınmadı: {at:08x}')
        if game.words(0x48ce34)[0]:raise ValueError('Önce farede tuttuğun eşyayı bırak.')
        rows=ground_equipment(game,state)
        if chosen is not None:rows=[r for r in rows if r['identifier'] in chosen]
        n=len(rows)
        if not n:
            if dry_run:return dict(**state,count=0,quote=0,items=[],hookRestored=True)
            return dict(sold=0,gold=0,bags=0,backup=backup,saved=bool(saved))
        total_size=(SIZE+n*36+4095)&~4095
        base=Alloc(game.h,None,total_size,0x3000,0x40);check(base,'Allocate ground liquidation')
        raw=image(base);d=base+DATA;records=base+SIZE;cash=records+n*16
        struct.pack_into('<6I',raw,DATA,1,state['player'],state['map'],n,records,int(not dry_run))
        struct.pack_into('<I',raw,DATA+64,cash)
        game.write(base,bytes(raw));game.write(records,b''.join(struct.pack('<4I',r['item'],r['identifier'],0,0) for r in rows))
        check(Flush(game.h,base,DATA),'Flush ground liquidation')
        patch=detour(HOOK,base+OFFSETS['request']);game.patch(ORIGINAL,patch);installed=True
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if game.words(d)[0] in (3,4):break
            time.sleep(.025)
        game.patch(patch,ORIGINAL);installed=False
        while game.words(d)[0]==2:
            # Executing requests are never freed or replayed after timeout.
            if time.monotonic()>deadline+30:raise RuntimeError('Satış çalışmaya devam ediyor; sonuç tekrar gönderilmedi.')
            time.sleep(.025)
        result=game.words(d,23)
        if result[0]!=3:raise RuntimeError('Satış tamamlanmadı; oyuna dön.'+(' İşlem öncesi kayıt alındı.' if saved else ''))
        proceeds=result[8]+(result[9]<<32);gold=[]
        if dry_run:
            for i,row in enumerate(rows):row['salePrice']=game.words(records+i*16+8)[0]
            return dict(**state,count=result[6],quote=proceeds,items=rows,hookRestored=True)
        for i in range(result[10]):
            item,ident,value,x,y=game.words(cash+i*20,5)
            if game.words(item+0xc)[0]!=4 or game.words(item+0x14)[0]!=0 or game.words(item+0x40)[0]!=value:
                raise RuntimeError('Yere bırakılan satış altınının değeri doğrulanamadı.')
            gold.append(dict(item=item,identifier=ident,value=value,x=x,y=y))
        if sum(g['value'] for g in gold)!=proceeds:raise RuntimeError('Satış toplamı ile yerdeki altın eşleşmedi.')
        ledger.register(game,state,gold)
        refresh_policy()
        policy_published=True
        audit=dict(**state,sold=result[7],gold=proceeds,bags=len(gold),currency=gold,items=rows,backup=backup,saved=bool(saved),hookRestored=True)
        SESSIONS.mkdir(exist_ok=True)
        (SESSIONS/f'{game.pid}-sale-{time.time_ns()}.json').write_text(json.dumps(audit,indent=2),'utf8')
        return audit
    except Exception as e:
        if not dry_run and game and d and not policy_published:
            try:
                status=game.words(d,11)
                if status[0]==2 or (status[0]==3 and status[10]):raise GroundSaleError(str(e)) from e
            except OSError:raise GroundSaleError(str(e)) from e
        raise
    finally:
        if game:
            if installed:
                try:game.patch(patch,ORIGINAL);installed=False
                except OSError:pass
            if base and not installed:
                try:
                    with game.suspended() as handles:
                        safe=game.words(d)[0]!=2 and not any(base<=ip<base+total_size for ip in game.ips(handles))
                    if safe:Free(game.h,base,0,0x8000)
                except OSError:pass
            game.close()
        LOCK.release()
