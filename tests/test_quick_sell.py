"""Exercise native hit testing, sale branch, gold handling and unlink code."""
import os,sys,json,struct,unittest
from pathlib import Path
import pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
from unicorn.x86_const import *
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from quick_sell import make_image,SALE_THUNK,DATA_OFFSET
from display_fix import argument_stub,jump,PATCH_DATA
from live_drop import GAME_MODE
FIXTURE=Path(os.environ.get('SHADOWFLARE_FIXTURE_DIR',ROOT.parent/'shadowflare-drop-analysis/resolution-fix'))/'ShadowFlare.exe'
IMAGE=pefile.PE(str(FIXTURE)).get_memory_mapped_image() if FIXTURE.exists() else None
BASE=0x31000000;STOP=BASE+0x1800;STACK=0x32010000;PLAYER=0x33000000;MOUSE=PLAYER+0x4000
ITEM=PLAYER+0x10000;VTABLE=PLAYER+0x9000;DTOR=BASE+0xf00

class Fixture:
    def __init__(self,items,width=1920,slot=(0,0),merchant=True,inventory=True,held=0,modal=False,mode=0):
        self.u=Uc(UC_ARCH_X86,UC_MODE_32);self.next_item=ITEM;self.prices={};self.freed=[];self.messages=[];self.fallback=0;self.lookups=[];self.modal=modal
        for a,n in ((0,4096),(0x400000,0x100000),(BASE,8192),(STACK-0x10000,0x20000),(PLAYER,0x100000)):self.u.mem_map(a,n)
        self.u.mem_write(0x400000,IMAGE);self.u.mem_write(BASE,make_image(BASE));self.put(VTABLE,DTOR)
        self.put(0x48ce44,int(merchant));self.put(0x48ce3c,int(inventory));self.put(0x48ce34,held);self.put(GAME_MODE,mode)
        self.put(PLAYER+0x3fc,MOUSE);self.put(0x48ce14,PLAYER+0xa000);self.put(PLAYER+0x588,1)
        self.put(MOUSE,width-640+336+slot[0]*32+16,264+slot[1]*32+16)
        original=bytes.fromhex(json.loads(PATCH_DATA.read_text('utf8'))['entries'][str(0x447290)])
        self.u.mem_write(BASE+0xa00,argument_stub(BASE+0xa00,original,0x447290+len(original),-(width-640),[(1,False)]))
        self.u.mem_write(0x447290,jump(0x447290,BASE+0xa00,len(original)))
        self.items=[self.create(**i) for i in items]
        self.put(PLAYER+0x514,self.items[0] if self.items else 0)
        for i,p in enumerate(self.items):self.put(p+0x8c,self.items[i+1] if i+1<len(self.items) else 0)
        self.u.hook_add(UC_HOOK_CODE,self.intercept)
    def put(self,a,*v):self.u.mem_write(a,struct.pack('<'+'I'*len(v),*(x&0xffffffff for x in v)))
    def words(self,a,n=1):return struct.unpack('<'+'I'*n,self.u.mem_read(a,n*4))
    def create(self,kind=3,subtype=1,x=0,y=0,w=1,h=1,buy=100,sell=25,value=0):
        p=self.next_item;self.next_item+=0x200
        self.put(p,VTABLE);self.put(p+0xc,kind);self.put(p+0x14,subtype);self.put(p+0x20,w,h)
        self.put(p+0x40,value);self.put(p+0x48,x,y);self.prices[p]=(buy,sell)
        return p
    def intercept(self,u,a,size,user):
        if a not in (0x406aa0,0x44a6f0,0x4661c0,0x462d30,0x417260,DTOR):return
        sp=u.reg_read(UC_X86_REG_ESP);ret=self.words(sp)[0];obj=u.reg_read(UC_X86_REG_ECX);result=0
        if a==0x406aa0:n=8;result=int(self.modal)
        elif a==0x44a6f0:n=0;result=0x55;self.fallback+=1
        elif a==0x4661c0:
            n=4;which=self.words(sp+4)[0];assert which in (0,1)
            if self.words(obj+0xc)[0]==4 and self.words(obj+0x14)[0]==0:result=self.words(obj+0x40)[0]
            else:result=self.prices[obj][which];self.lookups.append((obj,which))
        elif a==0x462d30:
            n=12;assert self.words(sp+4,3)==(4,0,0);result=self.create(kind=4,subtype=0,buy=0,sell=0)
        elif a==0x417260:
            n=20;args=self.words(sp+4,5);assert args[0]==0 and args[2:]==(0,0xffffffff,1);self.messages.append(args)
        else:
            n=4;assert self.words(sp+4)[0]==1;assert obj not in self.freed;self.freed.append(obj)
            u.mem_write(obj,b'\xdd'*0x90)
        u.reg_write(UC_X86_REG_EAX,result&0xffffffff);u.reg_write(UC_X86_REG_ESP,sp+4+n);u.reg_write(UC_X86_REG_EIP,ret)
    def call(self,address,args=(),this=PLAYER):
        self.put(STACK,STOP,*args);self.u.reg_write(UC_X86_REG_ESP,STACK);self.u.reg_write(UC_X86_REG_ECX,this)
        saved={UC_X86_REG_EBX:101,UC_X86_REG_EBP:202,UC_X86_REG_ESI:303,UC_X86_REG_EDI:404}
        for r,v in saved.items():self.u.reg_write(r,v)
        self.u.emu_start(address,STOP,count=10000000)
        assert self.u.reg_read(UC_X86_REG_EIP)==STOP and self.u.reg_read(UC_X86_REG_ESP)==STACK+4+len(args)*4
        for r,v in saved.items():assert self.u.reg_read(r)==v
        assert self.words(BASE+DATA_OFFSET)[0]==0
        return self.u.reg_read(UC_X86_REG_EAX)
    def native_sale(self,item):
        self.call(0x466be0,(item,),PLAYER+0x514);self.put(0x48ce34,item)
        return self.call(BASE+SALE_THUNK)
    def snapshot(self):
        out=[];p=self.words(PLAYER+0x514)[0]
        while p:
            assert p not in self.freed and len(out)<100
            out.append((p,*self.words(p+0xc),*self.words(p+0x14),*self.words(p+0x40),*self.words(p+0x48,2)))
            p=self.words(p+0x8c)[0]
        return out
    def gold(self):return sum(row[3] for row in self.snapshot() if row[1:3]==(4,0))

@unittest.skipIf(IMAGE is None,'Local original EXE fixture required')
class QuickSellTests(unittest.TestCase):
    def compare_success(self,items,width=1920,slot=(0,0),item_index=0):
        fast=Fixture(items,width,slot);native=Fixture(items,width,slot)
        self.assertEqual(fast.call(BASE),1);self.assertEqual(native.native_sale(native.items[item_index]),1)
        self.assertEqual(fast.snapshot(),native.snapshot());self.assertEqual(fast.gold(),native.gold())
        self.assertEqual(fast.freed,native.freed);self.assertEqual(fast.messages,native.messages)
        self.assertEqual(fast.words(0x48ce34)[0],0);self.assertEqual(fast.words(BASE+DATA_OFFSET+4,3),(1,0,1))
        return fast
    def test_sale_uses_native_price_and_gold_creation_across_resolutions(self):
        for width in (640,1024,1366,1920):
            fast=self.compare_success([dict(sell=137)],width)
            self.assertEqual(fast.gold(),137);self.assertEqual(fast.lookups,[(ITEM,0),(ITEM,1)])
    def test_every_cell_of_large_item_selects_the_same_owner(self):
        for slot in ((x,y) for y in range(3) for x in range(2)):
            self.compare_success([dict(kind=1,w=2,h=3,sell=257)],slot=slot)
    def test_partial_gold_stack_and_overflow_match_original_sale(self):
        fast=self.compare_success([dict(sell=25),dict(kind=4,subtype=0,x=1,value=9990)])
        self.assertEqual(fast.gold(),10015)
    def test_gold_capacity_rejection_restores_exact_inventory_and_cursor(self):
        items=[dict(sell=20001)]+[dict(kind=4,subtype=0,x=1,value=10000)]
        items += [dict(x=i%9,y=i//9) for i in range(2,36)]
        f=Fixture(items);before=f.snapshot();self.assertEqual(f.call(BASE),1)
        self.assertEqual(f.snapshot(),before);self.assertEqual(f.words(0x48ce34)[0],0)
        self.assertEqual(f.words(BASE+DATA_OFFSET+4,3),(0,1,1));self.assertEqual(f.gold(),10000)
        self.assertFalse(f.freed or f.messages)
    def test_unsellable_items_and_gold_stay_unchanged(self):
        for item in (dict(buy=0),dict(buy=-1),dict(kind=4,subtype=0,value=8737)):
            f=Fixture([dict(x=4),item],slot=(0,0));before=f.snapshot();self.assertEqual(f.call(BASE),1)
            self.assertEqual(f.snapshot(),before);self.assertEqual(f.words(0x48ce34)[0],0)
            self.assertFalse(f.freed or f.messages);self.assertEqual(f.words(BASE+DATA_OFFSET+4,3),(0,1,1))
    def test_original_rules_allow_zero_sale_price_when_base_value_is_positive(self):
        f=self.compare_success([dict(buy=1,sell=0)]);self.assertEqual(f.gold(),0)
    def test_empty_slot_and_modal_ui_do_not_sell_or_use_items(self):
        for f in (Fixture([]),Fixture([{}],modal=True)):
            before=f.snapshot();self.assertEqual(f.call(BASE),1);self.assertEqual(f.snapshot(),before)
            self.assertFalse(f.freed or f.messages or f.fallback);self.assertEqual(f.words(BASE+DATA_OFFSET+4,3),(0,0,0))
    def test_nonmerchant_hidden_inventory_and_multiplayer_keep_original_handler(self):
        for options in (dict(merchant=False),dict(inventory=False),dict(mode=1),dict(held=ITEM)):
            f=Fixture([{}],**options);before=f.snapshot();self.assertEqual(f.call(BASE),0x55)
            self.assertEqual(f.fallback,1);self.assertEqual(f.snapshot(),before);self.assertFalse(f.freed or f.messages)
    def test_vendor_equipment_and_special_slots_keep_original_handler(self):
        for x,y in ((50,100),(1850,40),(1660,180)):
            f=Fixture([{}]);f.put(MOUSE,x,y);before=f.snapshot();self.assertEqual(f.call(BASE),0x55)
            self.assertEqual(f.fallback,1);self.assertEqual(f.snapshot(),before)
    def test_rapid_repeated_clicks_do_not_sell_replacement_gold(self):
        f=Fixture([dict(sell=137)])
        for _ in range(10):self.assertEqual(f.call(BASE),1)
        self.assertEqual(f.words(BASE+DATA_OFFSET+4,3),(1,9,10));self.assertEqual(f.gold(),137);self.assertEqual(f.freed,[ITEM])

if __name__=='__main__':unittest.main()
