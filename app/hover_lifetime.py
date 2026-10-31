"""Repair the native render-generation lifetime of the shared mouse hit list.

The normal frame builds manager+0xa758 against screen+0x3c, then Screen::Render
swaps 0x38/0x3c and frees the old 0x3c generation. The later cursor renderer
still dereferences the cached list. Rebuild the native hit list immediately
after the swap, using the new surviving generation. No loot, selection, object
capacity or exception handler is changed.
"""
import atexit,ctypes as C,json,struct,threading,time
from live_drop import Game,Code,Alloc,Free,Flush,check,ROOT,LOCK,W,api

CALLSITE=0x41ebf1
RENDER=0x4030f0
REBUILD=0x40ede0
ORIGINAL=b'\xe8'+struct.pack('<i',RENDER-CALLSITE-5)
DATA_OFFSET=0x300
ALLOC_SIZE=4096
GetExitCodeProcess=api('GetExitCodeProcess',W.BOOL,[W.HANDLE,C.POINTER(W.DWORD)])

def make_stub(base):
    c=Code(base);data=base+DATA_OFFSET
    c.emit('9c f0 ff 05').u32(data).emit('9d')
    c.branch('e8',RENDER)
    # Save the exact post-render machine state, including the engine-manager EBP.
    c.emit('9c 60 8b cd').branch('e8',REBUILD)
    c.emit('f0 ff 05').u32(data+4)
    c.emit('f0 ff 0d').u32(data)
    c.emit('61 9d c3')
    raw=c.finish();assert len(raw)<DATA_OFFSET
    return raw

class HoverLifetimeFix:
    def __init__(self,start_worker=True):
        self.game=None;self.base=0;self.detour=None;self.manifest=None
        self.message='Oyun bekleniyor.';self.frames=0
        self._lock=threading.RLock();self._stop=threading.Event();self.worker=None
        if start_worker:
            self.worker=threading.Thread(target=self._follow,daemon=True);self.worker.start()
        atexit.register(self.close)
    def enable(self):
        with self._lock:
            if self.worker is None:
                self.worker=threading.Thread(target=self._follow,daemon=True);self.worker.start()
        return self.info()
    def info(self):
        with self._lock:
            if self.game:
                try:
                    self.frames=self.game.words(self.base+DATA_OFFSET+4)[0]
                except OSError:
                    self.game.close();self.game=None;self.base=0;self.detour=None
            return dict(version=1,active=self.game is not None,pid=self.game.pid if self.game else None,
                framesRefreshed=self.frames,manifest=self.manifest,message=self.message,
                method='refresh-native-hit-list-after-render-generation-swap',itemLimit=None)
    def _follow(self):
        while not self._stop.wait(.8):
            with self._lock:
                try:self._attempt()
                except Exception as error:self.message=str(error)
    def _attempt(self):
        if self.game:
            exit_code=W.DWORD()
            if not GetExitCodeProcess(self.game.h,C.byref(exit_code)) or exit_code.value!=259:
                self.game.close();self.game=None;self.base=0;self.detour=None
                self.message='Oyun bekleniyor.'
                return
            if self.game.read(CALLSITE,5)!=self.detour:
                raise RuntimeError('Fare listesi düzeltmesinin çağrısı değişmiş; üzerine yazılmadı.')
            return
        if not LOCK.acquire(False):return
        game=None;base=0;installed=False
        try:
            game=Game(write=True)
            if game.read(CALLSITE,5)!=ORIGINAL:raise RuntimeError('Ekran nesnesi geçişinde başka bir yama var; üzerine yazılmadı.')
            # Validate the source and consumers of the captured stale generation.
            expected={0x403257:'8b563c8b46388bca89563889463c',0x403540:'8b413cc3',
                      0x40ede0:'83ec0853558bd9',0x41f369:'8d8d58a70000'}
            for address,raw in expected.items():
                if game.read(address,len(bytes.fromhex(raw)))!=bytes.fromhex(raw):
                    raise RuntimeError(f'Fare listesi yaşam döngüsü tanınmadı: {address:08x}')
            base=Alloc(game.h,None,ALLOC_SIZE,0x3000,0x40);check(base,'Allocate native hit-list refresh')
            stub=make_stub(base);game.write(base,stub);game.write(base+DATA_OFFSET,b'\0'*8)
            check(Flush(game.h,base,len(stub)),'Flush native hit-list refresh')
            detour=b'\xe8'+struct.pack('<i',base-CALLSITE-5)
            game.patch_at(CALLSITE,ORIGINAL,detour);installed=True
            self.game,self.base,self.detour=game,base,detour;self.frames=0
            folder=ROOT/'hover-lifetime-sessions';folder.mkdir(exist_ok=True)
            path=folder/f'{game.pid}-{time.time_ns()}.json'
            record=dict(pid=game.pid,base=base,callsite=CALLSITE,before=ORIGINAL.hex(),after=detour.hex(),
                stub=stub.hex(),method='Native hover-cache rebuild after render generation swap',
                itemLimit=None,dropRNGChanged=False,gameFileModified=False)
            path.write_text(json.dumps(record,indent=2),encoding='utf8');self.manifest=str(path)
            self.message='Fare nesne listesi, ekran listesi değiştikten sonra güncelleniyor.'
        finally:
            if game is not self.game:
                if base and not installed:Free(game.h,base,0,0x8000)
                if game:game.close()
            LOCK.release()
    def _detach(self):
        if not self.game:return
        game=self.game;base=self.base
        try:
            game.patch_at(CALLSITE,self.detour,ORIGINAL)
            deadline=time.monotonic()+10;safe=False
            while time.monotonic()<deadline:
                with game.suspended() as handles:
                    safe=game.words(base+DATA_OFFSET)[0]==0 and not any(base<=ip<base+ALLOC_SIZE for ip in game.ips(handles))
                    self.frames=game.words(base+DATA_OFFSET+4)[0]
                if safe:break
                time.sleep(.01)
            if safe:check(Free(game.h,base,0,0x8000),'Free native hit-list refresh')
        finally:
            game.close();self.game=None;self.base=0;self.detour=None
    def close(self):
        self._stop.set()
        if self.worker and self.worker is not threading.current_thread():self.worker.join(2)
        with self._lock:
            try:self._detach()
            except OSError:pass
