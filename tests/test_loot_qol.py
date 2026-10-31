"""Execute the generated x86 against original native inventory/price code."""
import json,os,struct,sys,unittest
from pathlib import Path
import pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
from unicorn.x86_const import *
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from loot_qol import HOOKS,patches,valid_radius,quantity
from loot_qol_core import image,OFFSETS,DATA,SIZE
FIX=Path(os.environ.get('SHADOWFLARE_FIXTURE_DIR',ROOT.parent/'shadowflare-drop-analysis/input'))/'ShadowFlare.exe'
EXE=pefile.PE(str(FIX)).get_memory_mapped_image() if FIX.exists() else None
BASE=0x31000000;STACK=0x32010000;PLAYER=0x33000000;STOP=BASE+0x3f00
MAP=PLAYER+0x10000;MANAGER=MAP+0x1000;BANK=MAP+0x2000
TICK=BASE+0x3e00;KEY=BASE+0x3e10

class Fixture:
    def __init__(self,base=BASE):
        self.base=base;self.u=Uc(UC_ARCH_X86,UC_MODE_32)
        for a,n in ((0,4096),(0x400000,0x100000),(base,0x10000),(STACK-0x10000,0x20000),(PLAYER,0x100000)):self.u.mem_map(a,n)
        self.u.mem_write(0x400000,EXE);self.u.mem_write(base,bytes(image(base)))
        for a,_,b in patches(base):self.u.mem_write(a,b)
        self.put(base+DATA+8,1);self.put(base+DATA+40,TICK,KEY)
        self.put(0x48ce0c,MANAGER+0x500);self.put(MANAGER+0x500,1,MANAGER+0x520,0);self.put(MANAGER+0x520,PLAYER)
        self.put(0x48ce14,BANK);self.put(PLAYER+0x458,MAP);self.put(PLAYER+0x1a4,100)
        self.put(PLAYER+0x2c0,10);self.put(MAP+0x30,MANAGER);self.put(MAP+0x14,10000)
        self.next_item=PLAYER+0x20000;self.next_cell=PLAYER+0x60000;self.freed=[];self.draws=[];self.ground=[];self.created=[];self.modal=[];self.shift=True;self.fail_factory=False
        self.u.hook_add(UC_HOOK_CODE,self.intercept)
    def put(self,a,*v):self.u.mem_write(a,struct.pack('<'+'I'*len(v),*(x&0xffffffff for x in v)))
    def words(self,a,n=1):return struct.unpack('<'+'I'*n,self.u.mem_read(a,n*4))
    def ret(self,n,result=1):
        esp=self.u.reg_read(UC_X86_REG_ESP);self.u.reg_write(UC_X86_REG_EAX,result)
        self.u.reg_write(UC_X86_REG_ESP,esp+4+n*4);self.u.reg_write(UC_X86_REG_EIP,self.words(esp)[0])
    def create(self,kind=3,ident=0,q=1,x=0,y=0,w=1,h=1):
        p=self.next_item;self.next_item+=0x200
        self.put(p+0xc,kind);self.put(p+0x14,ident);self.put(p+0x1c,(0x53540000|q) if q>1 else 1)
        self.put(p+0x20,w,h);self.put(p+0x40,100,1);self.put(p+0x48,x,y);self.put(p+0x7c,0xffffffff)
        return p
    def bag(self,items):
        self.put(PLAYER+0x514,items[0] if items else 0)
        for a,b in zip(items,items[1:]+[0]):self.put(a+0x8c,b)
    def list(self,head):
        result=[];p=self.words(head)[0]
        while p:
            assert p not in result,'cycle';result.append(p);p=self.words(p+0x8c)[0]
        return result
    def ground_item(self,p):
        c=self.next_cell;self.next_cell+=0x200;d=c+0x20
        ident=self.words(MAP+0x14)[0];self.put(MAP+0x14,ident+1)
        self.put(c,3,30000000,d,0);self.put(d+4,ident);self.put(d+0xcc,p)
        if self.ground:self.put(self.ground[-1]+0xc,c)
        else:self.put(MANAGER+8,c)
        self.ground.append(c)
    def intercept(self,u,a,n,data):
        esp=u.reg_read(UC_X86_REG_ESP);ecx=u.reg_read(UC_X86_REG_ECX)
        if a==TICK:self.ret(0,1000)
        elif a==KEY:self.ret(1,0x8000 if self.shift else 0)
        elif a==self.base+OFFSETS['factory_original']:
            kind,ident,_=self.words(esp+4,3)
            p=0 if self.fail_factory else self.create(kind=kind,ident=ident);self.created.append(p);self.ret(3,p)
        elif a==0x465640:
            at=self.words(esp+4)[0];p=self.words(at)[0];self.freed.append(p);self.put(at,0);self.ret(1)
        elif a in (0x450080,0x452910):self.ret(0)
        elif a==0x4456d0:self.ret(3)
        elif a==0x405590:self.draws.append(self.words(esp+4,6));self.ret(6)
        elif a==0x427a00:
            ident,p=self.words(esp+4,2)
            cell=next(c for c in self.ground if self.words(self.words(c+8)[0]+4)[0]==ident)
            i=self.ground.index(cell);nxt=self.words(cell+0xc)[0]
            self.put(self.ground[i-1]+0xc if i else MANAGER+8,nxt);self.ground.remove(cell);self.ret(2)
        elif a==0x427970:
            p,_,_=self.words(esp+4,3);self.ground_item(p);self.ret(3,self.words(MAP+0x14)[0]-1)
        elif a==0x447290:
            _,_,x,y=self.words(esp+4,4);self.put(x,0);self.put(y,0);self.ret(4,9)
        elif a==0x441ab0:self.modal.append(self.words(esp+4,3));self.ret(3)
        elif a==self.base+OFFSETS['right_original']:self.ret(0,7)
        elif a==0x473f00:self.ret(4)
    def run(self,name,args=(),this=PLAYER,stop=STOP,regs=None):
        self.put(STACK,stop,*args);self.u.reg_write(UC_X86_REG_ESP,STACK);self.u.reg_write(UC_X86_REG_ECX,this)
        for r,v in (regs or {}).items():self.u.reg_write(r,v)
        self.u.emu_start(self.base+OFFSETS[name],stop,count=1000000)
        assert self.u.reg_read(UC_X86_REG_EIP)==stop,(name,hex(self.u.reg_read(UC_X86_REG_EIP)))
        return self.u.reg_read(UC_X86_REG_EAX)
    def q(self,p):return quantity(self.words(p+0xc)[0],self.words(p+0x1c)[0])

class ScriptFixture(Fixture):
    """Original DELETEITEM interpreter, original item lookup, real stack hook."""
    def intercept(self,u,a,n,data):
        esp=u.reg_read(UC_X86_REG_ESP)
        if a==BASE+0x3e20:
            self.ret(1,PLAYER+0xe0000+self.words(esp+4)[0]*8);return
        if a==0x4346b0:
            self.ret(1,self.words(self.words(esp+4)[0]+4)[0]);return
        super().intercept(u,a,n,data)
    def delete_item(self,kind,ident):
        self.put(0x4734c8,BASE+0x3e20);self.put(PLAYER+0xe0000,1,kind,1,ident)
        sp=STACK-0x800;self.put(sp,101,102,103,104);self.put(sp+0x7ac,STOP,0,0,0)
        self.u.reg_write(UC_X86_REG_ESP,sp);self.u.reg_write(UC_X86_REG_ESI,PLAYER+0xe1000);self.u.reg_write(UC_X86_REG_EDI,PLAYER+0xe2000)
        self.u.emu_start(0x433ced,STOP,count=100000)
        assert self.u.reg_read(UC_X86_REG_EIP)==STOP
        assert self.u.reg_read(UC_X86_REG_ESP)==sp+0x7bc
        assert [self.u.reg_read(r) for r in (UC_X86_REG_EDI,UC_X86_REG_ESI,UC_X86_REG_EBP,UC_X86_REG_EBX)]==[101,102,103,104]


@unittest.skipUnless(EXE,'Original ShadowFlare fixture required')
class NativeScriptTradeTests(unittest.TestCase):
    def test_each_card_ingredient_loses_only_one_unit_through_original_script(self):
        for ident in (40000000,40000001,40000008,40000009):
            f=ScriptFixture();p=f.create(ident=ident,q=7);f.bag([p]);f.delete_item(3,ident)
            self.assertEqual(f.q(p),6);self.assertEqual(f.freed,[]);self.assertEqual(f.list(PLAYER+0x514),[p])
    def test_special_item_page_trade_preserves_remainder(self):
        f=ScriptFixture();p=f.create(ident=40000000,q=4);f.put(PLAYER+0x548,p)
        f.delete_item(3,40000000);self.assertEqual(f.q(p),3);self.assertEqual(f.freed,[])
        self.assertEqual(f.list(PLAYER+0x548),[p])
    def test_repeated_trades_delete_exactly_the_last_unit_and_keep_other_items(self):
        f=ScriptFixture();other=f.create(ident=40000001,q=9);p=f.create(ident=40000000,q=3);f.bag([other,p])
        for q in (2,1):f.delete_item(3,40000000);self.assertEqual(f.q(p),q);self.assertEqual(f.freed,[])
        f.delete_item(3,40000000);self.assertEqual(f.list(PLAYER+0x514),[other]);self.assertEqual(f.q(other),9);self.assertEqual(f.freed,[p])
    def test_non_consumable_script_deletion_keeps_original_whole_item_behavior(self):
        f=ScriptFixture();p=f.create(kind=0,ident=123);f.bag([p]);f.delete_item(0,123)
        self.assertEqual(f.list(PLAYER+0x514),[]);self.assertEqual(f.freed,[p])


@unittest.skipUnless(EXE,'Original ShadowFlare fixture required')
class NativeLootTests(unittest.TestCase):
    def test_verified_hook_bytes_match_original_exe(self):
        for a,b,n in HOOKS:self.assertEqual(EXE[a-0x400000:a-0x400000+len(bytes.fromhex(b))],bytes.fromhex(b),n)
    def test_merge_caps_at_999_and_preserves_remainder(self):
        f=Fixture();a=f.create(q=997);b=f.create(q=10);f.bag([a])
        self.assertEqual(f.run('merge',[b],PLAYER+0x514),b);self.assertEqual((f.q(a),f.q(b)),(999,8));self.assertEqual(f.freed,[])
    def test_merge_matches_exact_id_and_destroys_only_absorbed_source(self):
        f=Fixture();a=f.create(ident=1);b=f.create(ident=0,q=2);c=f.create(ident=0,q=3);f.bag([a,b])
        self.assertEqual(f.run('merge',[c],PLAYER+0x514),0);self.assertEqual(f.q(b),5);self.assertEqual(f.q(a),1);self.assertEqual(f.freed,[c])
    def test_normalize_bag_once_without_cycles_or_lost_counts(self):
        f=Fixture();items=[f.create(ident=i%2,q=2,x=i) for i in range(6)];f.bag(items);f.run('normalize')
        remain=f.list(PLAYER+0x514);self.assertEqual(len(remain),2);self.assertEqual(sorted(f.q(p) for p in remain),[6,6])
    def test_consumption_decrements_exactly_one_and_keeps_last_single_native(self):
        f=Fixture();p=f.create(q=3);f.bag([p])
        for expected in (2,1):f.run('consume',[p],PLAYER+0x514,stop=0x442f62);self.assertEqual(f.q(p),expected)
        f.run('consume',[p],PLAYER+0x514,stop=0x442f62);self.assertEqual(f.freed,[p]);self.assertEqual(f.list(PLAYER+0x514),[])
    def test_non_consumption_delete_still_removes_whole_stack(self):
        f=Fixture();p=f.create(q=9);f.bag([p]);f.run('consume',[p],PLAYER+0x514);self.assertEqual(f.freed,[p])
    def test_native_price_scales_by_quantity_and_does_not_affect_equipment(self):
        f=Fixture();p=f.create(q=12);self.assertEqual(f.run('price',[0],p),1200)
        self.assertEqual(f.run('price',[1],p),300)
        f.put(p+0xc,0);self.assertEqual(f.run('price',[0],p),100)
    def test_native_identify_all_preserves_consumable_counts(self):
        f=Fixture();items=[f.create(ident=1,q=10),f.create(ident=10000001,q=5),f.create(ident=20000001,q=4),f.create(kind=1,ident=80000041)]
        f.put(items[-1]+0x1c,0);f.bag(items)
        f.put(STACK,STOP,1);f.u.reg_write(UC_X86_REG_ESP,STACK);f.u.reg_write(UC_X86_REG_ECX,PLAYER+0x514)
        f.u.emu_start(0x4670d0,STOP,count=100000)
        self.assertEqual([f.q(p) for p in items[:3]],[10,5,4])
        self.assertEqual(f.words(items[-1]+0x1c)[0],1)
    def test_identify_then_hotbar_consumes_only_one_tablet(self):
        f=Fixture();p=f.create(ident=1,q=10);f.bag([p])
        f.put(STACK,STOP,1);f.u.reg_write(UC_X86_REG_ESP,STACK);f.u.reg_write(UC_X86_REG_ECX,PLAYER+0x514)
        f.u.emu_start(0x4670d0,STOP,count=100000)
        f.run('consume',[p],PLAYER+0x514,stop=0x442f62)
        self.assertEqual(f.q(p),9);self.assertEqual(f.freed,[])
    def test_identification_setter_preserves_flags_and_allows_saved_count(self):
        f=Fixture();p=f.create(q=999)
        for status,expected in ((1,999),(0,999),(0x53540007,7)):
            f.put(STACK,STOP,status);f.u.reg_write(UC_X86_REG_ESP,STACK);f.u.reg_write(UC_X86_REG_ECX,p)
            f.u.reg_write(UC_X86_REG_EDX,0xabcdef12);f.u.reg_write(UC_X86_REG_EFLAGS,0x247)
            f.u.emu_start(0x4663c0,STOP,count=100000)
            self.assertEqual(f.q(p),expected);self.assertEqual(f.u.reg_read(UC_X86_REG_EAX),status)
            self.assertEqual(f.u.reg_read(UC_X86_REG_EDX),0xabcdef12);self.assertEqual(f.u.reg_read(UC_X86_REG_EFLAGS),0x247)
    def test_counted_recovery_spawn_keeps_requested_template_and_quantity(self):
        from live_drop import make_stub
        f=Fixture();base=0x35000000;data=base+0xc00;f.u.mem_map(base,0x10000)
        f.u.mem_write(base,make_stub(base,data,3,1,10));f.put(data,1,PLAYER,MAP,0,0,0,0,0)
        def drop(u,a,n,_):
            if a==0x452420:
                p=f.words(u.reg_read(UC_X86_REG_ESP)+4)[0];f.ground_item(p);f.ret(3,1)
        f.u.hook_add(UC_HOOK_CODE,drop)
        f.put(STACK,STOP);f.u.reg_write(UC_X86_REG_ESP,STACK);f.u.reg_write(UC_X86_REG_ECX,PLAYER)
        f.u.emu_start(base,0x443496,count=100000)
        p=f.words(data+12)[0];self.assertEqual(f.words(data)[0],3)
        self.assertEqual((f.words(p+0xc)[0],f.words(p+0x14)[0],f.q(p)),(3,1,10))
        self.assertEqual(f.words(p+0x48,2),(200,0));self.assertEqual(len(f.ground),1)
    def test_identify_then_native_right_click_sale_keeps_other_stacks(self):
        from test_quick_sell import Fixture as SaleFixture,BASE as SALE_BASE,PLAYER as SALE_PLAYER
        f=SaleFixture([dict(kind=1,subtype=21100,sell=250),dict(kind=3,subtype=1,x=1),dict(kind=3,subtype=10000001,x=2),dict(kind=3,subtype=20000001,x=3),dict(kind=4,subtype=0,x=4,value=100)])
        base=0x35000000;f.u.mem_map(base,0x10000);f.u.mem_write(base,bytes(image(base)))
        for at,old,after in patches(base):
            if at==0x4663c0:f.u.mem_write(at,after)
        for p,q in zip(f.items[1:4],(10,5,4)):f.put(p+0x1c,0x53540000|q)
        self.assertEqual(f.call(0x4670d0,(1,),SALE_PLAYER+0x514),1)
        self.assertEqual(f.call(SALE_BASE),1)
        self.assertEqual([quantity(3,f.words(p+0x1c)[0]) for p in f.items[1:4]],[10,5,4])
        self.assertEqual(f.freed,[f.items[0]]);self.assertEqual(f.gold(),350)
    def test_inventory_count_uses_original_draw_coordinates(self):
        f=Fixture();p=f.create(q=123)
        # Native item drawing's four saved registers precede seven arguments.
        f.put(STACK,1,2,3,4,STOP,99,14,800,264,0,0,0)
        f.u.reg_write(UC_X86_REG_ESP,STACK);f.u.reg_write(UC_X86_REG_ESI,p)
        f.u.emu_start(BASE+OFFSETS['draw'],STOP,count=100000)
        self.assertEqual(f.draws,[(99,14,123,829,285,0)])
    def test_split_partial_and_place_remains_separate(self):
        f=Fixture();p=f.create(q=30);f.bag([p]);f.put(PLAYER+0x1570,p,0)
        f.run('split',stop=0x4433fb,regs={UC_X86_REG_ESI:PLAYER,UC_X86_REG_EDI:7})
        held=f.words(0x48ce34)[0];self.assertEqual((f.q(p),f.q(held)),(23,7))
        f.run('insert',[held],PLAYER+0x514);self.assertEqual(len(f.list(PLAYER+0x514)),2)
    def test_original_inventory_callsite_passes_real_held_item(self):
        # Regression: a native CALL substitution must emit CALL, not JMP.
        # Enter the actual executable's callsite with its already-pushed item.
        for merging in (False,True):
            f=Fixture();f.put(BASE+DATA+4,int(merging));p=f.create(q=3);held=f.create(q=2);f.bag([p]);f.put(0x48ce34,held)
            f.put(STACK,held);f.u.reg_write(UC_X86_REG_ESP,STACK);f.u.reg_write(UC_X86_REG_ECX,PLAYER+0x514)
            f.u.emu_start(0x446ce2,0x446ce7,count=100000)
            self.assertEqual(f.u.reg_read(UC_X86_REG_ESP),STACK+4)
            self.assertEqual(f.list(PLAYER+0x514),[p] if merging else [held,p])
            self.assertEqual(f.q(p),5 if merging else 3)
    def test_split_whole_unlinks_original_without_allocating(self):
        f=Fixture();p=f.create(q=4);f.bag([p]);f.put(PLAYER+0x1570,p,0)
        f.run('split',stop=0x4433fb,regs={UC_X86_REG_ESI:PLAYER,UC_X86_REG_EDI:4})
        self.assertEqual(f.words(0x48ce34)[0],p);self.assertEqual(f.list(PLAYER+0x514),[]);self.assertEqual(f.created,[])
    def test_split_allocation_failure_does_not_change_source(self):
        f=Fixture();p=f.create(q=10);f.bag([p]);f.put(PLAYER+0x1570,p,0);f.fail_factory=True
        f.run('split',stop=0x4433fb,regs={UC_X86_REG_ESI:PLAYER,UC_X86_REG_EDI:3})
        self.assertEqual(f.q(p),10);self.assertEqual(f.words(0x48ce34)[0],0)
    def test_right_click_shift_opens_quantity_prompt(self):
        f=Fixture();p=f.create(q=40);f.bag([p]);f.put(0x48ce3c,1);f.put(PLAYER+0x3fc,PLAYER+0x7000);f.put(PLAYER+0x7000,1000,300)
        f.put(0x473618,0x473f00)
        self.assertEqual(f.run('right'),1);self.assertEqual(f.modal,[(976,276,40)])
    def test_ordinary_right_click_falls_back_to_existing_handlers(self):
        f=Fixture();f.shift=False;self.assertEqual(f.run('right'),7)
    def test_ground_save_factory_roundtrip_every_potion_type_and_999(self):
        f=Fixture();record=PLAYER+0x8000;entity=PLAYER+0x9000
        for ident in (0,3,10000003,20000002,30000008,40000009):
            p=f.create(ident=ident,q=999);f.put(entity+0xcc,p)
            f.run('ground_save',stop=0x41b54a,regs={UC_X86_REG_EAX:ident,UC_X86_REG_EBX:entity,UC_X86_REG_ESI:record})
            encoded=f.words(record+4)[0];clone=f.run('factory',[3,encoded,0],BANK)
            self.assertEqual((f.words(clone+0x14)[0],f.q(clone)),(ident,999))
    def test_auto_pickup_native_backpack_merge_and_filter(self):
        f=Fixture();f.put(BASE+DATA,1,1,1);p=f.create(q=5);f.bag([p])
        for kind,ident in ((3,0),(4,1),(4,9),(0,1)):
            f.ground_item(f.create(kind=kind,ident=ident,x=170,y=170))
        f.run('update',stop=0x44349b)
        self.assertEqual(f.q(p),6);self.assertEqual(f.words(PLAYER+0x328)[0],1);self.assertEqual(len(f.ground),2);self.assertEqual(f.words(BASE+DATA+12)[0],2)
    def test_adjustable_radius_includes_boundary_and_excludes_next_ring(self):
        for radius in (1,2,3,20):
            f=Fixture();f.put(BASE+DATA,1,0,radius)
            f.ground_item(f.create(x=240*radius,y=0));f.ground_item(f.create(x=240*radius+1,y=0))
            f.run('update',stop=0x44349b);self.assertEqual(len(f.ground),1)
    def test_full_backpack_restores_ground_item_and_inventory_flag(self):
        f=Fixture();f.put(BASE+DATA,1,0,1);f.put(0x48ce3c,1)
        f.bag([f.create(kind=0,w=9,h=4)]);p=f.create(x=100,y=100);f.ground_item(p);original_cell=f.ground[0]
        f.run('update',stop=0x44349b)
        self.assertEqual(len(f.ground),1);self.assertEqual(f.words(p+0x48,2),(100,100));self.assertEqual(f.words(0x48ce3c)[0],1);self.assertEqual(f.words(0x48ce34)[0],0)
        self.assertEqual(f.ground[0],original_cell)
    def test_full_bag_partial_stack_transfer_preserves_both_sides(self):
        f=Fixture();f.put(BASE+DATA,1,1,1)
        existing=f.create(q=998);f.bag([existing,f.create(kind=0,x=1,y=0,w=8,h=4),f.create(kind=0,x=0,y=1,w=1,h=3)])
        p=f.create(q=5,x=100,y=100);f.ground_item(p)
        f.run('update',stop=0x44349b)
        self.assertEqual((f.q(existing),f.q(p)),(999,4));self.assertEqual(len(f.ground),1)
    def test_held_item_blocks_automatic_pickup(self):
        f=Fixture();f.put(BASE+DATA,1,1,20);f.put(0x48ce34,123);f.ground_item(f.create());f.run('update',stop=0x44349b);self.assertEqual(len(f.ground),1)
    def test_gold_preflight_uses_large_purse_capacity_even_with_no_empty_slots(self):
        f=Fixture();p=f.create(kind=4,ident=0);f.put(p+0x40,10000)
        f.bag([p,f.create(kind=0,x=1,w=8,h=4),f.create(kind=0,x=0,y=1,w=1,h=3)])
        incoming=f.create(kind=4,ident=0,x=100,y=100)
        self.assertEqual(f.run('can_accept',[incoming],PLAYER),1)
        f.put(p+0x40,0x7fffffff)
        self.assertEqual(f.run('can_accept',[incoming],PLAYER),0)
    def test_relocation_runs_at_different_allocated_base(self):
        f=Fixture(0x34000000);p=f.create(q=7);self.assertEqual(f.run('price',[0],p),700)

class SettingsTests(unittest.TestCase):
    def test_radius_rejects_invalid_values(self):
        for v in (None,True,'20',0,21,1.1):
            with self.assertRaises(ValueError):valid_radius(v)
        self.assertEqual(valid_radius(20),20)

if __name__=='__main__':unittest.main()
