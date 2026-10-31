"""Preserve native sprite ordering with an exact geometry multiset graph.

Verified sort and sequential lookup imports are redirected. Object membership,
native comparisons, selection policy and moved-cell metadata stay the same.
Temporary storage scales with list length; allocation failure uses complete
direct traversal. Duplicate geometries/cells stay distinct; nothing is capped.
"""
import atexit,hashlib,json,struct,threading,time
from live_drop import Game,Code,ROOT,LOCK,Alloc,Free,Flush,check
from drop_event import remote_export
from hover_lifetime import GetExitCodeProcess,C,W
from graph_sort import make_stub,make_image,CACHE_OFFSET,CACHE_SLOTS
from render_insert import make_insert_image,patches as insertion_patches
from render_index import IMPORT as INDEX_IMPORT,CODE_OFFSET as INDEX_CODE,CACHE_OFFSET as INDEX_CACHE,LOOP_SHA256,make_stub as make_index_stub
from render_index import BLOCK_IMPORT,BLOCK_CODE,BLOCK_CACHE,BLOCK_LOOP_SHA256,make_block_stub

IMPORT=0x473374
DATA_OFFSET=0x300
ALLOC_SIZE=8192
SYMBOL='?SortDisplayObject@RKC_RPGSCRN_OBJECTDISP@@QAEHXZ'
NATIVE_SHA256='cf056c10686485397f903e240e7fd4e3b29e3bfb1a10121045c939f435c4dbf5'

class RenderSortFix:
    def __init__(self):
        self.game=None;self.base=0;self.before=None;self.after=None;self.manifest=None;self.patches=[]
        self.message='Oyun bekleniyor.';self.sorts=0;self.cache_hits=0;self.cache_misses=0
        self.cache_diagnostics=(0,0,0,0)
        self.lock=threading.RLock();self.stop=threading.Event();self.worker=None
        atexit.register(self.close)
    def enable(self):
        with self.lock:
            if self.worker is None:
                self.worker=threading.Thread(target=self._follow,daemon=True);self.worker.start()
        return self.info()
    def info(self):
        with self.lock:
            if self.game:
                try:
                    self.sorts=self.game.words(self.base+DATA_OFFSET+4)[0]
                    self.cache_hits,self.cache_misses=self.game.words(self.base+CACHE_OFFSET+8,2)
                    self.cache_diagnostics=self.game.words(self.base+CACHE_OFFSET+16,4)
                except OSError:self.game.close();self.game=None;self.base=0
            return dict(version=11,active=self.game is not None,pid=self.game.pid if self.game else None,
                        sortsCompleted=self.sorts,message=self.message,manifest=self.manifest,
                        exactCacheHits=self.cache_hits,exactCacheMisses=self.cache_misses,
                        changedObjectsLastSort=self.cache_diagnostics[0],membershipRebuilds=self.cache_diagnostics[1],
                        inputReorders=self.cache_diagnostics[2],duplicateFallbacks=self.cache_diagnostics[3],
                        method='native-order-exact-geometry-graph-and-sequential-list-lookups',itemLimit=None)
    def _follow(self):
        while not self.stop.wait(.8):
            with self.lock:
                try:self._attempt()
                except Exception as error:self.message=str(error)
    def inspect_cache(self):
        """Read fixed cache metadata for local performance diagnosis only."""
        with self.lock:
            if not self.game:raise RuntimeError('Renderer is not attached')
            game=self.game
            for _ in range(200):
                with game.suspended():
                    if game.words(self.base+CACHE_OFFSET)[0]==0:
                        out=[]
                        for i in range(CACHE_SLOTS):
                            key,buffer,count=game.words(self.base+CACHE_OFFSET+32+i*24,3)
                            active_count=game.words(self.base+CACHE_OFFSET+52+i*24)[0]
                            if buffer and 0<count<1000000:
                                data=game.words(buffer,count*8)
                                out.append(dict(key=key,buffer=buffer,capacity=count,count=active_count,metadata=[list(data[j*8+1:j*8+6]) for j in range(count)]))
                        return out
                time.sleep(.002)
            raise RuntimeError('Could not sample a completed sort cache')
    def _attempt(self):
        if self.game:
            code=W.DWORD()
            if not GetExitCodeProcess(self.game.h,C.byref(code)) or code.value!=259:
                self.game.close();self.game=None;self.base=0;self.message='Oyun bekleniyor.'
                return
            if any(self.game.read(at,len(after))!=after for at,before,after in self.patches):raise RuntimeError('Çizim sıralaması başka bir yama tarafından değiştirildi.')
            return
        if not LOCK.acquire(False):return
        game=None;base=0;installed=False;applied=[]
        try:
            game=Game(write=True);native=remote_export(game,'RKC_RPGSCRN.dll',SYMBOL)
            before=struct.pack('<I',native)
            if game.read(IMPORT,4)!=before:raise RuntimeError('Çizim sıralaması çağrısı özgün değil; üzerine yazılmadı.')
            if hashlib.sha256(game.read(native,0x18b)).hexdigest()!=NATIVE_SHA256:raise RuntimeError('Oyun çizim sıralaması tanınmadı.')
            if hashlib.sha256(game.read(0x4032c0,0x25c)).hexdigest()!=LOOP_SHA256:raise RuntimeError('Çizim örtüşme döngüsü tanınmadı.')
            if hashlib.sha256(game.read(0x40f841,0xac)).hexdigest()!=BLOCK_LOOP_SHA256:raise RuntimeError('Nesne vurgu döngüsü tanınmadı.')
            dll=native-0x6d00
            for at,expected in ((dll+0x59e0,bytes.fromhex('8b490433c085c9')),(dll+0x6a20,bytes.fromhex('8b490433c085c9')),(dll+0x6a00,bytes.fromhex('8b410433c985c0')),(dll+0x5990,bytes.fromhex('8b410433c985c0'))):
                if game.read(at,len(expected))!=expected:raise RuntimeError('Çizim listesi işlemleri tanınmadı.')
            # These accessors are the highlight loop's only writes; none may
            # mutate object membership or links while a cursor is reused.
            for address,offset,raw in ((0x47345c,0x4c40,'8b410cc3'),(0x473440,0x5450,'668b4120c3'),
                    (0x473334,0x5460,'668b4122c3'),(0x473338,0x5470,'668b4124c3'),
                    (0x473448,0x5550,'668b44240466894120c20400'),(0x473450,0x5560,'668b44240466894122c20400'),
                    (0x473418,0x5570,'668b44240466894124c20400')):
                if game.words(address)[0]!=dll+offset or game.read(dll+offset,len(bytes.fromhex(raw)))!=bytes.fromhex(raw):
                    raise RuntimeError('Nesne vurgu özellikleri tanınmadı.')
            base=Alloc(game.h,None,ALLOC_SIZE,0x3000,0x40);check(base,'Allocate display sorting')
            stub=make_image(base,remote_export(game,'kernel32.dll','VirtualAlloc'),remote_export(game,'kernel32.dll','VirtualFree'))
            assert len(stub)<INDEX_CODE, 'Sort and lookup thunks overlap'
            game.write(base,stub);game.write(base+DATA_OFFSET,b'\0'*8)
            for offset,raw in make_insert_image(base,dll):game.write(base+offset,raw)
            index_original=struct.pack('<I',dll+0x6a00)
            game.write(base+INDEX_CODE,make_index_stub(base+INDEX_CODE,dll+0x6a00,base+DATA_OFFSET,base+INDEX_CACHE))
            game.write(base+BLOCK_CODE,make_block_stub(base+BLOCK_CODE,dll+0x5990,base+DATA_OFFSET,base+BLOCK_CACHE))
            check(Flush(game.h,base,ALLOC_SIZE),'Flush display sorting')
            after=struct.pack('<I',base);patches=[(IMPORT,before,after),(INDEX_IMPORT,index_original,struct.pack('<I',base+INDEX_CODE)),
                (BLOCK_IMPORT,struct.pack('<I',dll+0x5990),struct.pack('<I',base+BLOCK_CODE)),*insertion_patches(base,dll)]
            for at,expected,replacement in patches:
                if game.read(at,len(expected))!=expected:raise RuntimeError('Çizim listesinde başka bir yama var; üzerine yazılmadı.')
            try:
                for at,expected,replacement in patches:
                    game.patch_at(at,expected,replacement);applied.append((at,expected,replacement));installed=True
            except Exception:
                for at,expected,replacement in reversed(applied):game.patch_at(at,replacement,expected)
                raise
            self.game,self.base,self.before,self.after=game,base,before,after;self.sorts=0
            self.patches=patches
            folder=ROOT/'render-sort-sessions';folder.mkdir(exist_ok=True)
            path=folder/f'{game.pid}-{time.time_ns()}.json'
            path.write_text(json.dumps(dict(pid=game.pid,base=base,importAddress=IMPORT,before=before.hex(),after=after.hex(),
                stub=stub.hex(),patches=[dict(address=at,before=a.hex(),after=b.hex()) for at,a,b in patches],nativeSHA256=NATIVE_SHA256,itemLimit=None,gameFileModified=False),indent=2),'utf8')
            self.manifest=str(path);self.message='Çizim sırası, değişen nesnelerin ilişkileri güncellenerek özgün kurallarla hesaplanıyor.'
        finally:
            if game is not self.game:
                if base and not installed:Free(game.h,base,0,0x8000)
                if game:game.close()
            LOCK.release()
    def _detach(self):
        if not self.game:return
        game=self.game;base=self.base
        try:
            for at,before,after in reversed(self.patches):game.patch_at(at,after,before)
            deadline=time.monotonic()+10;safe=False
            while time.monotonic()<deadline:
                with game.suspended() as handles:
                    safe=game.words(base+DATA_OFFSET)[0]==0 and not any(base<=ip<base+ALLOC_SIZE for ip in game.ips(handles))
                    self.sorts=game.words(base+DATA_OFFSET+4)[0]
                    buffers=[game.words(base+CACHE_OFFSET+36+i*24)[0] for i in range(CACHE_SLOTS)] if safe else []
                if safe:break
                time.sleep(.01)
            if safe:
                for buffer in buffers:
                    if buffer:check(Free(game.h,buffer,0,0x8000),'Free display sort cache')
                check(Free(game.h,base,0,0x8000),'Free display sorting')
        finally:game.close();self.game=None;self.base=0
    def close(self):
        self.stop.set()
        if self.worker and self.worker is not threading.current_thread():self.worker.join(2)
        with self.lock:
            try:self._detach()
            except OSError:pass
