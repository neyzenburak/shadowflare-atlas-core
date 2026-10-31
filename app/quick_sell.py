"""Right-click backpack sales through the original merchant sale branch.

The native hit test supplies the slot, including the wide-screen correction.
Pricing, gold capacity, notifications and destruction stay in the native sale
path. Rejected sales restore the exact original inventory link and cursor.
"""
import atexit,hashlib,json,struct,threading,time
from live_drop import Game,Code,ROOT,LOCK,Alloc,Free,Flush,check,backup_saves,C,W,GAME_MODE
from hover_lifetime import GetExitCodeProcess

CALLSITE=0x445a7b
ORIGINAL_HANDLER=0x44a6f0
ORIGINAL=b'\xe8'+struct.pack('<i',ORIGINAL_HANDLER-CALLSITE-5)
SALE_BRANCH=0x44831c
SALE_THUNK=0x600
DATA_OFFSET=0x800
ALLOC_SIZE=4096
VERIFIED=(
    (0x44831c,0x99,'85919fe039198a26f229a65890875c325b2f12d66c5eeae12fd367e78ea5136e'),
    (0x448481,12,'2b4c9dc98304740b3c00057812ea00c24262725593565ae38e09d3c94fd3081b'),
    (0x466b00,0x5d,'6e41019fa1a772e08132d66f5d9bca9b554a20c61fec8c2eb3731f8679f00ed0'),
    (0x466be0,0x54,'de488d94e5c7fdbce47369c0c4de307152d3704b69e802228817d2eb494ffaef'),
    (0x466e10,0x16c,'7c9712beef51e0fd63256e9107380b96c19084ac5443b420cb1e705e677f200c'),
    (0x465640,0x5a,'f3f55fe46435dce3f690df49aaf654fc73d2c784a24e2a6ca862c680ada8ca95'),
)

def inventory_snapshot():
    """Local, read-only verification of backpack membership and native gold."""
    from loot_qol import quantity
    game=Game()
    try:
        state=game.state()
        with game.suspended():
            items=[];seen=set();pointer=game.words(state['player']+0x514)[0]
            while pointer:
                if pointer in seen:raise RuntimeError('Inventory list contains a cycle')
                seen.add(pointer)
                kind=game.words(pointer+0xc)[0];ident=game.words(pointer+0x14)[0]
                width,height=game.words(pointer+0x20,2);x,y=game.words(pointer+0x48,2)
                instance=game.words(pointer+0x1c)[0]
                items.append(dict(pointer=pointer,kind=kind,id=ident,width=width,height=height,x=x,y=y,value=game.words(pointer+0x40)[0],quantity=quantity(kind,instance),instance=instance))
                pointer=game.words(pointer+0x8c)[0]
            merchant,inventory=game.words(0x48ce44)[0],game.words(0x48ce3c)[0]
            held=game.words(0x48ce34)[0]
            hotbar=[];seen=set();pointer=game.words(state['player']+0x518)[0]
            while pointer:
                if pointer in seen:raise RuntimeError('Hotbar list contains a cycle')
                seen.add(pointer);kind=game.words(pointer+0xc)[0];instance=game.words(pointer+0x1c)[0]
                hotbar.append(dict(pointer=pointer,kind=kind,id=game.words(pointer+0x14)[0],quantity=quantity(kind,instance),instance=instance,x=game.words(pointer+0x48)[0],y=game.words(pointer+0x4c)[0]))
                pointer=game.words(pointer+0x8c)[0]
            held_item=None
            if held:
                held_kind=game.words(held+0xc)[0];held_instance=game.words(held+0x1c)[0]
                held_item=dict(pointer=held,kind=held_kind,id=game.words(held+0x14)[0],instance=held_instance,quantity=quantity(held_kind,held_instance))
        return dict(pid=game.pid,player=state['player'],items=items,
                    gold=sum(i['value'] for i in items if i['kind']==4 and i['id']==0),
                    merchantOpen=merchant==1,inventoryOpen=inventory==1,held=held,heldItem=held_item,hotbarItems=hotbar)
    finally:game.close()

def make_image(base):
    data=base+DATA_OFFSET
    c=Code(base).emit('9c f0 ff 05').u32(data).emit('9d 55 8b ec 83 ec 08 53 56 57 8b f1')
    c.emit('83 3d').u32(GAME_MODE).emit('00').branch('0f 85','fallback')
    for flag in (0x48ce44,0x48ce3c):
        c.emit('83 3d').u32(flag).emit('01').branch('0f 85','fallback')
    c.emit('83 3d').u32(0x48ce34).emit('00').branch('0f 85','fallback')
    # Hit-test arguments: x,y,&column,&row. No guessed resolution constants.
    c.emit('8b 86 fc 03 00 00 8d 55 f8 52 8d 55 fc 52 ff 70 04 ff 30 8b ce').branch('e8',0x447290)
    c.emit('83 f8 09').branch('0f 85','fallback')
    # Preserve the original admission check for active modal UI.
    c.emit('6a 02 6a ff b9').u32(0x482df4).branch('e8',0x406aa0)
    c.emit('83 f8 01').branch('0f 84','handled')
    c.emit('6a ff 6a ff ff 75 f8 ff 75 fc 8d 8e 14 05 00 00').branch('e8',0x466b00)
    c.emit('8b f8 85 ff').branch('0f 84','handled')
    # Save the link containing this item so a rejected sale restores list order.
    c.emit('8d 9e 14 05 00 00').mark('find_link').emit('8b 03 85 c0').branch('0f 84','handled')
    c.emit('3b c7').branch('0f 84','found_link')
    c.emit('8d 98 8c 00 00 00').branch('e9','find_link')
    c.mark('found_link').emit('f0 ff 05').u32(data+12)
    c.emit('89 3d').u32(0x48ce34).emit('57 8d 8e 14 05 00 00').branch('e8',0x466be0)
    c.emit('8b ce').branch('e8',base+SALE_THUNK)
    c.emit('83 3d').u32(0x48ce34).emit('00').branch('0f 84','sold')
    # The native rejected path does not mutate gold or other inventory links.
    c.emit('89 3b c7 05').u32(0x48ce34).u32(0).emit('f0 ff 05').u32(data+8)
    c.branch('e9','handled').mark('sold').emit('f0 ff 05').u32(data+4)
    c.mark('handled').emit('b8 01 00 00 00').branch('e9','return')
    c.mark('fallback').emit('8b ce').branch('e8',ORIGINAL_HANDLER)
    c.mark('return').emit('5f 5e 5b 8b e5 5d 9c f0 ff 0d').u32(data).emit('9d c3')
    raw=c.finish();assert len(raw)<SALE_THUNK
    # Match the native merchant function's stack and saved-register frame.
    tail=Code(base+SALE_THUNK).emit('83 ec 0c 53 55 56 57 8b f1 c7 44 24 10 01 00 00 00').branch('e9',SALE_BRANCH).finish()
    image=bytearray(DATA_OFFSET+16);image[:len(raw)]=raw;image[SALE_THUNK:SALE_THUNK+len(tail)]=tail
    return bytes(image)

class QuickSellFix:
    def __init__(self,verified_reader=None):
        self.game=None;self.base=0;self.detour=None;self.manifest=None;self.backup=None
        self.requested=False;self.counts=(0,0,0);self.message='Sağ tıkla satış kapalı.'
        self.lock=threading.RLock();self.stop=threading.Event();self.worker=None
        self.verified_reader=verified_reader
        atexit.register(self.close)
    def info(self):
        with self.lock:
            if self.game:
                try:self.counts=self.game.words(self.base+DATA_OFFSET+4,3)
                except OSError:self.game.close();self.game=None;self.base=0
            return dict(version=1,active=self.game is not None,requested=self.requested,
                        pid=self.game.pid if self.game else None,sold=self.counts[0],rejected=self.counts[1],
                        attempts=self.counts[2],message=self.message,manifest=self.manifest,backup=self.backup)
    def enable(self):
        with self.lock:
            self.requested=True
            if not self.game:self.message='Oyun bekleniyor.'
            if self.worker is None:self.worker=threading.Thread(target=self._follow,daemon=True);self.worker.start()
        return self.info()
    def disable(self):
        with self.lock:
            self.requested=False;self._detach();self.message='Sağ tıkla satış kapalı.'
            return self.info()
    def _follow(self):
        while not self.stop.wait(.8):
            with self.lock:
                if not self.requested:continue
                try:self._attempt()
                except Exception as error:self.message=str(error)
    def _attempt(self):
        if self.game:
            code=W.DWORD()
            if not GetExitCodeProcess(self.game.h,C.byref(code)) or code.value!=259:
                self.game.close();self.game=None;self.base=0;self.message='Oyun bekleniyor.';return
            if self.game.read(CALLSITE,5)!=self.detour:raise RuntimeError('Sağ tık çağrısı başka bir yama tarafından değiştirildi.')
            return
        if not LOCK.acquire(False):return
        game=None;base=0;installed=False
        try:
            game=Game(write=True);game.state()
            if game.read(CALLSITE,5)!=ORIGINAL:raise RuntimeError('Envanter sağ tık çağrısı tanınmadı; üzerine yazılmadı.')
            for at,n,digest in VERIFIED:
                raw=self.verified_reader(game,at,n) if self.verified_reader else game.read(at,n)
                if hashlib.sha256(raw).hexdigest()!=digest:raise RuntimeError(f'Satış işlevi tanınmadı: {at:08x}')
            self.backup=backup_saves(game)
            base=Alloc(game.h,None,ALLOC_SIZE,0x3000,0x40);check(base,'Allocate right-click sale')
            raw=make_image(base);game.write(base,raw);check(Flush(game.h,base,len(raw)),'Flush right-click sale')
            detour=b'\xe8'+struct.pack('<i',base-CALLSITE-5)
            game.patch_at(CALLSITE,ORIGINAL,detour);installed=True
            self.game,self.base,self.detour=game,base,detour;self.counts=(0,0,0)
            folder=ROOT/'quick-sell-sessions';folder.mkdir(exist_ok=True);path=folder/f'{game.pid}-{time.time_ns()}.json'
            path.write_text(json.dumps(dict(pid=game.pid,base=base,callsite=CALLSITE,before=ORIGINAL.hex(),after=detour.hex(),
                stub=raw.hex(),backup=self.backup,gameFileModified=False,method='native-merchant-sale-branch'),indent=2),'utf8')
            self.manifest=str(path);self.message='Satıcı açıkken çantadaki eşyaya sağ tıkla: sat.'
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
                    self.counts=game.words(base+DATA_OFFSET+4,3)
                if safe:break
                time.sleep(.01)
            if safe:check(Free(game.h,base,0,0x8000),'Free right-click sale')
        finally:game.close();self.game=None;self.base=0
    def close(self):
        self.stop.set()
        if self.worker and self.worker is not threading.current_thread():self.worker.join(2)
        with self.lock:
            try:self._detach()
            except OSError:pass
