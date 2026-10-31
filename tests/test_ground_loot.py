"""Run ground hooks with the original native price and ground unlink code."""
import struct,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import *
from test_loot_qol import Fixture,EXE,BASE,DATA as QDATA,PLAYER,MAP,MANAGER,STACK,STOP
from ground_loot import DRAW_HOOK,DRAW_ORIGINAL,VERIFIED,eligible,detour
from ground_loot_core import image,DATA,OFFSETS

GL=0x35000000;RECORDS=GL+0x3000;CASH=GL+0x40000;HEAD=MAP+0x3800

class SaleFixture(Fixture):
    def __init__(self):
        super().__init__();self.u.mem_map(GL,0x100000);self.u.mem_write(GL,bytes(image(GL)))
        self.u.mem_map(0x34000000,0x600000);self.next_cell=0x34300000
        self.put(MAP+0x4c,HEAD);self.fail_after=None;self.by_id={}
    def ground_item(self,p):
        super().ground_item(p);cell=self.ground[-1];obj=self.words(cell+8)[0]
        self.put(obj+0x5c,MAP);self.put(p+0x8c,self.words(HEAD)[0]);self.put(HEAD,p)
        self.by_id[self.words(obj+4)[0]]=cell
    def intercept(self,u,a,n,data):
        esp=u.reg_read(UC_X86_REG_ESP)
        if a==0x427a00:return # execute the actual native world + item unlink
        if a==0x4299e0:
            ident=self.words(esp+4)[0]
            node=self.by_id.get(ident,0)
            self.ret(1,node);return
        if a==0x429be0:
            cell=self.words(esp+4)[0];i=self.ground.index(cell);nxt=self.words(cell+0xc)[0]
            self.by_id.pop(self.words(self.words(cell+8)[0]+4)[0])
            self.put(self.ground[i-1]+0xc if i else MANAGER+8,nxt);self.ground.remove(cell);self.ret(1);return
        if a==BASE+0x1100 and self.fail_after==len(self.created):
            self.created.append(0);self.ret(3,0);return
        super().intercept(u,a,n,data)
    def gear(self,kind=2,rarity=0,value=400,identified=1):
        p=self.create(kind=kind);self.put(p+0x18,rarity,identified);self.put(p+0x40,value,1)
        self.put(p+0xb8,100,100);self.ground_item(p);return p
    def request(self,items,command=1,player=PLAYER,map_pointer=MAP):
        self.put(GL+DATA,1,player,map_pointer,len(items),RECORDS,command)
        self.put(GL+DATA+64,CASH)
        for i,p in enumerate(items):
            ident=next(self.words(self.words(c+8)[0]+4)[0] for c in self.ground if self.words(self.words(c+8)[0]+0xcc)[0]==p)
            self.put(RECORDS+i*16,p,ident,0,0)
        saved={UC_X86_REG_EAX:101,UC_X86_REG_EBX:102,UC_X86_REG_EDX:103,UC_X86_REG_ESI:104,UC_X86_REG_EDI:105,UC_X86_REG_EBP:106}
        for r,v in saved.items():self.u.reg_write(r,v)
        self.put(STACK,STOP);self.u.reg_write(UC_X86_REG_ESP,STACK);self.u.reg_write(UC_X86_REG_ECX,PLAYER)
        self.u.emu_start(GL+OFFSETS['request'],0x443496,count=20000000)
        assert self.u.reg_read(UC_X86_REG_EIP)==0x443496
        assert self.u.reg_read(UC_X86_REG_ESP)==STACK-20
        for r,v in saved.items():assert self.u.reg_read(r)==v,(r,v,self.u.reg_read(r))
        return self.words(GL+DATA,23)


class DrawFixture(SaleFixture):
    def __init__(self):
        super().__init__();self.packets=[]
        for slot,target in ((0x473344,GL+0x80000),(0x47332c,GL+0x80010),(0x4733bc,GL+0x80020)):self.put(slot,target)
    def intercept(self,u,a,n,data):
        if a in (0x466400,0x427b00,0x466410):self.ret(0,1000);return
        if a in (0x4663a0,0x403530):self.ret(0,123);return
        if a==GL+0x80000:self.ret(1,GL+0x90000);return
        if a==GL+0x80010:self.ret(0,1);return
        if a==GL+0x80020:
            self.packets.append(self.words(u.reg_read(UC_X86_REG_ESP)+4,20));self.ret(20);return
        super().intercept(u,a,n,data)
    def draw(self,hidden):
        p=self.gear();obj=self.words(self.ground[-1]+8)[0]
        self.put(obj+0xd0,2,1600,280,0);self.put(GL+DATA,hidden)
        self.u.mem_write(DRAW_HOOK,detour(DRAW_HOOK,GL))
        self.u.reg_write(UC_X86_REG_ESP,STACK);self.u.reg_write(UC_X86_REG_ESI,obj)
        self.u.reg_write(UC_X86_REG_EBX,GL+0x90000);self.u.reg_write(UC_X86_REG_EDI,0);self.u.reg_write(UC_X86_REG_EBP,37)
        self.u.emu_start(DRAW_HOOK,0x458d8a,count=10000)
        assert self.u.reg_read(UC_X86_REG_ESP)==STACK
        return p,obj


@unittest.skipUnless(EXE,'Original ShadowFlare fixture required')
class GroundNativeTests(unittest.TestCase):
    def test_original_world_draw_omits_hit_packet_but_keeps_identical_physics(self):
        shown=DrawFixture();p,obj=shown.draw(False)
        hidden=DrawFixture();hp,ho=hidden.draw(True)
        self.assertEqual(len(shown.packets),1);self.assertEqual(hidden.packets,[])
        self.assertEqual(shown.packets[0][13],shown.words(obj+4)[0]) # native hit-test identity
        self.assertEqual(bytes(shown.u.mem_read(obj,0xe4)),bytes(hidden.u.mem_read(ho,0xe4)))
        self.assertEqual(bytes(shown.u.mem_read(p,0x200)),bytes(hidden.u.mem_read(hp,0x200)))
        self.assertEqual(shown.list(HEAD),hidden.list(HEAD))
    def test_verified_functions_and_hook_match_original(self):
        import hashlib
        self.assertEqual(EXE[DRAW_HOOK-0x400000:DRAW_HOOK-0x400000+6],DRAW_ORIGINAL)
        for a,n,digest in VERIFIED:self.assertEqual(hashlib.sha256(EXE[a-0x400000:a-0x400000+n]).hexdigest(),digest)
    def test_visibility_routes_only_plain_and_magic_equipment_and_preserves_registers(self):
        for hidden in (0,1):
            for category in range(5):
                for rarity in range(4):
                    f=SaleFixture();p=f.gear(category,rarity);obj=f.words(f.ground[0]+8)[0]
                    f.put(GL+DATA,hidden);f.u.mem_write(DRAW_HOOK,detour(DRAW_HOOK,GL))
                    f.put(STACK,0);f.u.reg_write(UC_X86_REG_ESP,STACK)
                    saved={UC_X86_REG_ESI:obj,UC_X86_REG_EAX:123,UC_X86_REG_EBX:456,UC_X86_REG_EDI:789,UC_X86_REG_EBP:987,UC_X86_REG_EDX:654}
                    for r,v in saved.items():f.u.reg_write(r,v)
                    f.u.reg_write(UC_X86_REG_ECX,321);f.u.reg_write(UC_X86_REG_EFLAGS,0x247)
                    target=0x458cc3 if hidden and eligible(category,rarity) else 0x458a22
                    before=bytes(f.u.mem_read(p,0x200))
                    f.u.emu_start(DRAW_HOOK,target,count=1000)
                    self.assertEqual(f.u.reg_read(UC_X86_REG_EIP),target)
                    self.assertEqual(f.u.reg_read(UC_X86_REG_ESP),STACK)
                    self.assertEqual(f.u.reg_read(UC_X86_REG_ECX),321 if target==0x458cc3 else p)
                    for r,v in saved.items():self.assertEqual(f.u.reg_read(r),v)
                    self.assertEqual(f.u.reg_read(UC_X86_REG_EFLAGS),0x247)
                    self.assertEqual(bytes(f.u.mem_read(p,0x200)),before)
    def test_sale_uses_real_native_quarter_price_and_keeps_premium_and_supplies(self):
        f=SaleFixture();white=f.gear(rarity=0);blue=f.gear(rarity=1,identified=1)
        retained=[f.gear(rarity=2),f.gear(rarity=3),f.gear(kind=3),f.gear(kind=4)]
        before={p:bytes(f.u.mem_read(p,0x8c)) for p in retained}
        result=f.request([white,blue,*retained])
        self.assertEqual((result[0],result[6],result[7],result[8],result[10]),(3,2,2,200,1))
        self.assertEqual(set(f.freed),{white,blue})
        self.assertEqual(f.words(CASH+8)[0],200)
        gold=f.words(CASH)[0];self.assertEqual(f.words(gold+0x40)[0],200)
        self.assertEqual(f.words(PLAYER+0x514)[0],0) # no gold credited to backpack
        self.assertEqual(set(f.list(HEAD)),set(retained+[gold]))
        for p,raw in before.items():self.assertEqual(bytes(f.u.mem_read(p,0x8c)),raw)
    def test_quote_restores_identification_and_never_creates_or_deletes(self):
        f=SaleFixture();items=[f.gear(k,r,identified=flag) for k,r,flag in ((0,0,0),(1,1,1),(2,1,0))]
        before=[bytes(f.u.mem_read(p,0x200)) for p in items]
        result=f.request(items,command=0)
        self.assertEqual((result[0],result[6],result[7],result[8]),(3,3,0,300))
        self.assertEqual(f.created,[]);self.assertEqual(f.freed,[])
        self.assertEqual([bytes(f.u.mem_read(p,0x200)) for p in items],before)
    def test_all_currency_reserved_before_deleting_and_allocation_failure_rolls_back(self):
        f=SaleFixture();items=[f.gear(value=0x7fffffff) for _ in range(5)]
        f.fail_after=1;before=set(f.list(HEAD));result=f.request(items)
        self.assertEqual(result[0],4);self.assertEqual(result[7],0)
        self.assertEqual(set(f.list(HEAD)),before);self.assertTrue(all(p not in f.freed for p in items))
        self.assertEqual(f.freed,[f.created[0]])
    def test_64_bit_proceeds_split_without_loss_or_signed_overflow(self):
        f=SaleFixture();items=[f.gear(value=0x7fffffff) for _ in range(5)];result=f.request(items)
        total=5*(0x7fffffff//4)
        self.assertEqual(result[8]+(result[9]<<32),total)
        self.assertEqual(result[10],2)
        self.assertEqual([f.words(CASH+i*20+8)[0] for i in range(2)],[0x7fffffff,total-0x7fffffff])
    def test_wrong_map_and_held_item_reject_without_any_item_mutation(self):
        for held,wrong in ((1,False),(0,True)):
            f=SaleFixture();p=f.gear();f.put(0x48ce34,held)
            result=f.request([p],map_pointer=MAP+4 if wrong else MAP)
            self.assertEqual(result[0],4);self.assertEqual(f.created,[]);self.assertEqual(f.freed,[])
    def test_empty_request_completes_without_allocating_currency(self):
        f=SaleFixture();r=f.request([]);self.assertEqual(r[0],3);self.assertEqual(f.created,[])
    def test_large_ground_set_keeps_every_gold_unit(self):
        f=SaleFixture();items=[f.gear(rarity=i%2) for i in range(1500)]
        result=f.request(items);self.assertEqual((result[7],result[8],result[10]),(1500,150000,1))
        self.assertEqual(len(f.list(HEAD)),1)


@unittest.skipUnless(EXE,'Original ShadowFlare fixture required')
class ManualGoldTests(unittest.TestCase):
    def prepare(self):
        f=Fixture();p=f.create(kind=4,ident=0,x=100,y=100);f.ground_item(p)
        entity=f.words(f.ground[0]+8)[0];ident=f.words(entity+4)[0]
        table=PLAYER+0xf0000;f.put(table,1,*([0]*3),123,100,100,100,MAP,ident)
        filename=b'0000.ssv\0'.ljust(16,b'\0');f.u.mem_write(table+40,filename)
        f.put(0x482dcc,PLAYER+0xf1100);f.put(PLAYER+0xf1100,PLAYER+0xf1000);f.u.mem_write(PLAYER+0xf1000,filename)
        f.put(MAP+4,123);f.put(BASE+QDATA+68,table)
        f.put(BASE+QDATA,1,0,20);return f,p,entity,table
    def test_sale_gold_is_skipped_but_ordinary_gold_is_picked_up(self):
        f,p,_,_=self.prepare();ordinary=f.create(kind=4,ident=0,x=101,y=100);f.ground_item(ordinary)
        f.run('update',stop=0x44349b)
        self.assertEqual(len(f.ground),1);self.assertEqual(f.words(f.words(f.ground[0]+8)[0]+0xcc)[0],p)
        self.assertEqual(f.words(BASE+QDATA+12)[0],1)
        self.assertEqual(f.words(BASE+QDATA+72)[0],1)
    def test_record_rebinds_after_save_reload_then_rejects_a_reused_entity_pointer(self):
        f,p,entity,table=self.prepare();f.put(table+4+28,0,0)
        f.run('update',stop=0x44349b);self.assertEqual(len(f.ground),1)
        self.assertEqual(f.words(table+4+28,2),(MAP,f.words(entity+4)[0]))
        f.put(entity+4,f.words(entity+4)[0]+1);f.put(MAP+0x14,f.words(entity+4)[0]+1);f.put(BASE+QDATA+32,0)
        f.run('update',stop=0x44349b);self.assertEqual(len(f.ground),0)
    def test_other_character_or_value_is_not_excluded(self):
        for offset in (4,4+24,4+36):
            f,p,_,table=self.prepare();f.put(table+offset,999)
            f.run('update',stop=0x44349b);self.assertEqual(len(f.ground),0)
    def test_second_policy_row_is_reached_without_losing_count_or_stack(self):
        f,p,_,table=self.prepare();row=bytes(f.u.mem_read(table+4,52))
        f.put(table,2);f.u.mem_write(table+56,row);f.put(table+4+24,999)
        f.run('update',stop=0x44349b);self.assertEqual(len(f.ground),1)
        self.assertEqual(f.words(BASE+QDATA+72)[0],1)
    def test_actual_persisted_ledger_builds_a_working_native_policy_after_restart(self):
        import tempfile
        from unittest.mock import patch
        import ground_loot
        f,p,entity,table=self.prepare()
        class MemoryGame:
            pid=1234;h=0
            def read(self,a,n):return bytes(f.u.mem_read(a,n))
            def words(self,a,n=1):return f.words(a,n)
            def write(self,a,raw):f.u.mem_write(a,raw)
        game=MemoryGame()
        with tempfile.TemporaryDirectory() as folder,patch.object(ground_loot,'LEDGER',Path(folder)/'ledger.json'),patch.object(ground_loot,'Alloc',return_value=table):
            ledger=ground_loot.SaleGoldLedger()
            ledger.register(game,dict(player=PLAYER,map=MAP),[dict(item=p,identifier=f.words(entity+4)[0],value=100,x=100,y=100)])
            game.pid+=1 # fresh process: bind from the normal saved gold fingerprint
            restored=ground_loot.SaleGoldLedger();address=restored.policy(game)
            f.put(BASE+QDATA+68,address);f.run('update',stop=0x44349b)
            self.assertEqual(len(f.ground),1);self.assertEqual(f.words(BASE+QDATA+72)[0],1)

if __name__=='__main__':unittest.main()
