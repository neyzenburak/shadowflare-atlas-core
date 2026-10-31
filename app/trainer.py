"""Optional user-supplied CT controls and independently implemented Atlas extras."""
import ctypes as C
from ctypes import wintypes as W
import hashlib,json,struct,threading,time
from live_drop import Game,Code,ROOT,LOCK,Alloc,Free,Flush,Protect,api,check,backup_saves
import blackjack
from ct_table import empty_table,load as load_table,parse as parse_table
from ct_asm import assemble

VERSION=3
LOCAL=ROOT/'trainer-local'
PLAN=load_table(LOCAL)
RECORDS={r['id']:r for r in PLAN['records']}
RECORDS[blackjack.ID]=blackjack.RECORD
GetExitCode=api('GetExitCodeProcess',W.BOOL,[W.HANDLE,C.POINTER(W.DWORD)])

def companion(game,player):
    """Follow the map's native entity list (427AA0/4299E0), match vtable/owner."""
    map_ptr=game.words(player+0x458)[0]
    manager=game.words(map_ptr+0x30)[0] if map_ptr else 0
    node=game.words(manager+8)[0] if manager else 0
    seen=set()
    while node and node not in seen:
        seen.add(node)
        raw=game.words(node,4);obj=raw[2];node=raw[3]
        if obj and game.words(obj)[0]==0x476e38 and game.words(obj+0x214)[0]==player:return obj
    return 0

def resolve(game,record,state,pet=0,cache=None):
    cache={} if cache is None else cache
    def word(address):
        if address not in cache:cache[address]=game.words(address)[0]
        return cache[address]
    root=record['address'];offsets=record['offsets'];chain=[]
    if root in ('fallbackPtr','fallbackComPtr'):
        address=state['player'] if root=='fallbackPtr' else pet
        if not address:raise ValueError('Yoldaş şu an haritada bulunmuyor.')
        chain.append(address)
        if not offsets:return None,address,tuple(chain)
        offsets=list(reversed(offsets))
        address+=offsets[0]
        for offset in offsets[1:]:
            pointer=word(address)
            if not pointer:raise ValueError('Bu yuvada takılı eşya yok.')
            chain.append(pointer);address=pointer+offset
    elif root.startswith('0x') and 0x47d000<=int(root,16)<0x4b0000:
        address=int(root,16)
        for offset in reversed(offsets):
            pointer=word(address)
            if not pointer:raise ValueError('Boş işaretçi.')
            chain.append(pointer);address=pointer+offset
    else:raise ValueError('Tabloda doğrulanmamış adres.')
    item_id=word(chain[1]+0x14) if root=='fallbackPtr' and offsets and 0x4e8<=offsets[0]<=0x508 and len(chain)>1 else None
    binding=hashlib.sha256(repr((state['pid'],state['player'],root,chain,address,item_id)).encode()).hexdigest()[:24]
    return address,binding,tuple(chain)

class Trainer:
    def __init__(self,start_worker=True):
        self.lock=threading.RLock();self.game=None;self.active={};self.frozen={};self.undo=[]
        self.player=None;self.backup=None;self.message='';self.stop=threading.Event();self.worker=None
        if start_worker:
            self.worker=threading.Thread(target=self._follow,daemon=True);self.worker.start()
    def info(self):
        with self.lock:return dict(version=VERSION,active=list(self.active),frozen=list(self.frozen),undoCount=len(self.undo),backup=self.backup,message=self.message,
                                   blackjack=blackjack.snapshot(self.game),table=dict(source=PLAN['source'],sha256=PLAN['sha256'],**PLAN['counts']))
    def table(self):
        with self.lock:return {k:v for k,v in PLAN.items()if k not in ('patches','actions')}
    def import_table(self,raw,filename='local.ct'):
        from game_paths import locate
        folder=locate()
        if folder is None:raise ValueError('Önce oyun klasörünü seç.')
        data=parse_table(raw,folder/'ShadowFlare.exe',filename)
        with self.lock:
            if not LOCK.acquire(False):raise RuntimeError('Önceki oyun işlemini bekle.')
            try:
                for ident in list(self.active):
                    if ident.startswith('ct:'):self._disable(ident)
                self.frozen.clear();self.undo.clear()
                LOCAL.mkdir(exist_ok=True)
                temp=LOCAL/'table.tmp';temp.write_text(json.dumps(data,ensure_ascii=False),'utf8');temp.replace(LOCAL/'table.json')
                PLAN.clear();PLAN.update(data);RECORDS.clear();RECORDS.update({r['id']:r for r in data['records']});RECORDS[blackjack.ID]=blackjack.RECORD
                self.message='CT içe aktarıldı; Lua çalıştırılmadı.'
                return self.table()
            finally:LOCK.release()
    def remove_table(self):
        with self.lock:
            if not LOCK.acquire(False):raise RuntimeError('Önceki oyun işlemini bekle.')
            try:
                for ident in list(self.active):
                    if ident.startswith('ct:'):self._disable(ident)
                self.frozen.clear();self.undo.clear()
                (LOCAL/'table.json').unlink(missing_ok=True)
                PLAN.clear();PLAN.update(empty_table());RECORDS.clear();RECORDS[blackjack.ID]=blackjack.RECORD
                self.message='Yerel CT kaldırıldı.';return self.table()
            finally:LOCK.release()
    def _connect(self):
        if self.game:
            code=W.DWORD()
            if not GetExitCode(self.game.h,C.byref(code)) or code.value!=259:
                self.game.close();self.game=None;self.active.clear();self.frozen.clear();self.undo.clear();self.backup=None;self.player=None
        if self.game is None:self.game=Game(write=True)
        return self.game
    def _state(self,game):
        state=game.state()
        if self.player!=state['player']:
            self.frozen.clear();self.undo.clear();self.player=state['player'];self.backup=None
        return state
    def _backup(self,game):
        if not self.backup:self.backup=backup_saves(game)
    def read(self,ids):
        if not isinstance(ids,list) or len(ids)>1000 or any(not isinstance(i,str) or i not in RECORDS or RECORDS[i]['kind']!='value' for i in ids):raise ValueError('Geçersiz tablo kayıtları.')
        with self.lock:
            game=self._connect();state=self._state(game);cache={};pet=companion(game,state['player']) if any(RECORDS[i]['address']=='fallbackComPtr' for i in ids) else 0
            values={}
            for ident in ids:
                r=RECORDS[ident]
                try:
                    address,binding,_=resolve(game,r,state,pet,cache)
                    if address is None:values[ident]=dict(value=binding,address=binding,readOnly=True);continue
                    if r['type']=='String':
                        raw=game.read(address,r['length']).split(b'\0',1)[0]
                        values[ident]=dict(value=raw.decode('cp1252',errors='replace'),address=address,binding=binding,maxBytes=len(raw))
                    else:values[ident]=dict(value=struct.unpack('<i' if r['signed'] else '<I',game.read(address,4))[0],address=address,binding=binding)
                except (OSError,ValueError,RuntimeError) as error:values[ident]=dict(error=str(error))
            return dict(pid=game.pid,player=state['player'],companion=pet,values=values,**self.info())
    def _target(self,ident,binding):
        r=RECORDS.get(ident)
        if not r or r['kind']!='value' or r['readOnly']:raise ValueError('Bu kayıt düzenlenebilir bir değer değil.')
        game=self._connect();state=self._state(game)
        pet=companion(game,state['player']) if r['address']=='fallbackComPtr' else 0
        address,current,chain=resolve(game,r,state,pet)
        if not isinstance(binding,str) or binding!=current:raise ValueError('Karakter veya eşya değişmiş. Değerleri yenileyip tekrar dene.')
        return game,state,r,address,current
    def _encode(self,game,r,address,value):
        if r['type']=='String':
            if not isinstance(value,str) or '\0' in value:raise ValueError('Geçersiz eşya adı.')
            raw=value.encode('cp1252');previous=game.read(address,r['length']).split(b'\0',1)[0]
            if len(raw)>len(previous):raise ValueError(f'Bu adın ayrılmış alanı {len(previous)} bayt. Daha kısa veya aynı uzunlukta bir ad gir.')
            return raw+b'\0'+b'\0'*(len(previous)-len(raw))
        if isinstance(value,bool) or not isinstance(value,int):raise ValueError('Tam sayı gir.')
        lo=r.get('minimum',-2147483648 if r['signed'] else 0);hi=r.get('maximum',2147483647 if r['signed'] else 4294967295)
        if not lo<=value<=hi:raise ValueError(f'Değer {lo}–{hi} aralığında olmalı.')
        if r.get('choices') and value not in [c[0] for c in r['choices']]:raise ValueError('Tablodaki seçeneklerden birini seç.')
        return struct.pack('<i' if r['signed'] else '<I',value)
    def write(self,ident,value,binding,freeze=False):
        if not isinstance(freeze,bool):raise ValueError('Geçersiz sabitleme ayarı.')
        with self.lock:
            if not LOCK.acquire(False):raise RuntimeError('Önceki oyun işleminin tamamlanmasını bekle.')
            try:
                game,state,r,address,current=self._target(ident,binding);raw=self._encode(game,r,address,value)
                if freeze and r['type']=='String':raise ValueError('Adlar bir kez uygulanır; sayı sabitlemesi kullan.')
                self._backup(game)
                with game.suspended():
                    # Re-resolve after suspension so an equipment change cannot race a write.
                    self._target(ident,binding)
                    before=game.read(address,len(raw));game.write(address,raw)
                self.undo.append(dict(player=state['player'],writes=[(ident,binding,address,before,raw)]));self.undo=self.undo[-100:]
                if freeze:self.frozen[ident]=dict(binding=current,value=value)
                else:self.frozen.pop(ident,None)
                self.message='Değer uygulandı.';return self.info()
            finally:LOCK.release()
    def unfreeze(self,ident):
        with self.lock:self.frozen.pop(ident,None);return self.info()
    def reset(self):
        with self.lock:
            if not LOCK.acquire(False):raise RuntimeError('Önceki oyun işlemini bekle.')
            try:
                self.frozen.clear()
                if self.active:
                    self._connect()
                    for ident in list(self.active):self._disable(ident)
                self.message='Trainer hileleri ve sabitlemeler kapatıldı.';return self.info()
            finally:LOCK.release()
    def action(self,ident):
        if ident not in PLAN['actions']:raise ValueError('Geçersiz tek seferlik işlem.')
        with self.lock:
            if not LOCK.acquire(False):raise RuntimeError('Önceki oyun işlemini bekle.')
            try:
                specs=PLAN['actions'][ident]
                roots={s['root']for s in specs}
                if len(roots)!=1:raise ValueError('Tek işlemde farklı nesneler değiştirilemez.')
                pet=next(iter(roots))=='fallbackComPtr'
                game=self._connect();state=self._state(game);self._backup(game);target=state['player']
                if pet:
                    target=companion(game,target)
                    if not target:raise ValueError('Yoldaş şu an haritada bulunmuyor.')
                writes=[]
                with game.suspended():
                    if game.state()['player']!=state['player']:raise ValueError('Karakter değişmiş; yeniden dene.')
                    if pet and companion(game,state['player'])!=target:raise ValueError('Yoldaş değişmiş; yeniden dene.')
                    try:
                        for spec in specs:
                            address=target+spec['offset'];after=bytes.fromhex(spec['data']);before=game.read(address,len(after))
                            game.write(address,after);writes.append((None,target,address,before,after))
                    except Exception:
                        for _,_,a,b,_ in reversed(writes):game.write(a,b)
                        raise
                self.undo.append(dict(player=state['player'],target=target,companion=pet,writes=writes));self.undo=self.undo[-100:]
                self.message='Tek seferlik işlem uygulandı.';return self.info()
            finally:LOCK.release()
    def revert(self):
        with self.lock:
            if not self.undo:raise ValueError('Geri alınacak işlem yok.')
            if not LOCK.acquire(False):raise RuntimeError('Önceki oyun işlemini bekle.')
            try:
                game=self._connect();state=self._state(game)
                if not self.undo:raise ValueError('Karakter değişmiş; önceki oturumun işlemi geri alınamaz.')
                entry=self.undo[-1]
                with game.suspended():
                    if entry['player']!=state['player']:raise ValueError('Önceki karakterin adreslerine yazılmaz.')
                    if entry.get('companion') and companion(game,state['player'])!=entry['target']:raise ValueError('Yoldaş değişmiş; eski adresine yazılmaz.')
                    for ident,binding,address,before,after in entry['writes']:
                        if ident:self._target(ident,binding)
                        if game.read(address,len(after))!=after:raise ValueError('Oyun bu değeri değiştirmiş; eski değere otomatik dönülmedi.')
                    for ident,binding,address,before,after in entry['writes']:
                        game.write(address,before)
                        if ident:self.frozen.pop(ident,None)
                self.undo.pop();self.message='Son değer işlemi geri alındı.';return self.info()
            finally:LOCK.release()
    def _patch(self,changes):
        game=self.game
        for _ in range(100):
            with game.suspended() as handles:
                if any(c['address']<ip<c['address']+len(c['before']) for c in changes for ip in game.ips(handles)):continue
                if any(game.read(c['address'],len(c['before']))!=c['before'] for c in changes):raise RuntimeError('Bu oyun kodunda başka bir yama var; üzerine yazılmadı.')
                done=[]
                try:
                    for c in changes:done.append(c);self._code_write(c['address'],c['after'])
                except Exception:
                    for c in reversed(done):self._code_write(c['address'],c['before'])
                    raise
                return
            time.sleep(.005)
        raise RuntimeError('Güvenli kod sınırı bulunamadı; yeniden dene.')
    def _code_write(self,address,raw):
        old=W.DWORD();check(Protect(self.game.h,address,len(raw),0x40,C.byref(old)),'Protect trainer code')
        try:self.game.write(address,raw);check(Flush(self.game.h,address,len(raw)),'Flush trainer code')
        finally:
            previous=W.DWORD();check(Protect(self.game.h,address,len(raw),old.value,C.byref(previous)),'Restore trainer protection')
    def toggle(self,ident,enabled):
        if ident not in PLAN['patches'] and ident!=blackjack.ID or not isinstance(enabled,bool):raise ValueError('Geçersiz hile seçimi.')
        with self.lock:
            if not LOCK.acquire(False):raise RuntimeError('Önceki oyun işlemini bekle.')
            try:
                game=self._connect()
                if not enabled:self._disable(ident);return self.info()
                self._state(game)
                if ident in self.active:return self.info()
                if ident==blackjack.ID:blackjack.verify(game)
                self._backup(game)
                changes=([dict(address=blackjack.HOOK,before=blackjack.ORIGINAL,after=b'')] if ident==blackjack.ID else
                         [dict(address=c['address'],before=bytes.fromhex(c['before']),after=bytes.fromhex(c['after'])) for c in PLAN['patches'][ident]]);base=0
                try:
                    if ident!=blackjack.ID and RECORDS[ident].get('allocated'):
                        base=Alloc(game.h,None,4096,0x3000,0x40);check(base,'Allocate local CT patch')
                        assembled,stub=assemble(RECORDS[ident]['script'],base)
                        if len(assembled)!=len(changes):raise ValueError('CT yerleşimi değişti.')
                        for target,source in zip(changes,assembled):
                            if target['address']!=source['address']or len(source['after'])>len(target['before']):raise ValueError('CT yerleşimi değişti.')
                            target['after']=source['after'].ljust(len(target['before']),b'\x90')
                        game.write(base,stub);check(Flush(game.h,base,len(stub)),'Flush local CT patch')
                    elif ident==blackjack.ID:
                        base=Alloc(game.h,None,blackjack.ALLOCATION,0x3000,0x40);check(base,'Allocate blackjack trainer')
                        stub=blackjack.make_stub(base)
                        game.write(base,stub);check(Flush(game.h,base,len(stub)),'Flush blackjack trainer')
                        changes[0]['after']=blackjack.detour(base)
                    self._patch(changes)
                    self.active[ident]=dict(changes=changes,base=base)
                except Exception:
                    if base:Free(game.h,base,0,0x8000)
                    raise
                self.message='Hile açıldı: '+RECORDS[ident]['label'];return self.info()
            finally:LOCK.release()
    def _disable(self,ident):
        entry=self.active.get(ident)
        if not entry:return
        self._patch([dict(address=c['address'],before=c['after'],after=c['before']) for c in entry['changes']])
        if entry['base']:
            with self.game.suspended() as handles:
                if not any(entry['base']<=ip<entry['base']+4096 for ip in self.game.ips(handles)):Free(self.game.h,entry['base'],0,0x8000)
        del self.active[ident];self.message='Hile kapatıldı: '+RECORDS[ident]['label']
    def _follow(self):
        while not self.stop.wait(.25):
            with self.lock:
                if not self.game or not (self.active or self.frozen or self.undo):continue
                if not LOCK.acquire(False):continue
                try:
                    game=self._connect()
                    try:state=self._state(game)
                    except Exception:
                        self.frozen.clear();self.undo.clear();self.player=None;self.backup=None
                        for ident in list(self.active):self._disable(ident)
                        self.message='Karakter oturumu kapandı; hileler ve sabitlemeler kapatıldı.';continue
                    for ident,item in list(self.frozen.items()):
                        try:
                            game,state,r,address,binding=self._target(ident,item['binding']);raw=self._encode(game,r,address,item['value'])
                            with game.suspended():self._target(ident,item['binding']);game.write(address,raw)
                        except Exception:self.frozen.pop(ident,None);self.message='Karakter/eşya değişti; ilgili sabitleme kapatıldı.'
                except Exception as error:self.message=str(error)
                finally:LOCK.release()
    def close(self):
        self.stop.set()
        with self.lock:
            self.frozen.clear()
            if self.game:
                with LOCK:
                    for ident in list(self.active):
                        try:self._disable(ident)
                        except Exception as error:self.message=str(error)
                self.game.close();self.game=None
        if self.worker:self.worker.join(timeout=2)
