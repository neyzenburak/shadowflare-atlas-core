import json,struct,sys,tempfile,unittest
import hashlib,threading
from types import SimpleNamespace
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from grail_store import GrailStore,read_save,SAVE_TABLE,profile_id
from grail_native import make_image,patches,decode_record,DATA,RING,SIZE,PICKUP,INSERT,DELETE,POLICY
from grail_policy import policy_image,HEADER
from grail import Grail
from quick_sell import make_image as sale_image,VERIFIED
from test_quick_sell import Fixture,IMAGE,BASE,PLAYER,ITEM,STACK,STOP
from unicorn.x86_const import *

class NativeFixture(Fixture):
    def __init__(self,inventory=False,items=(),mode=0):
        super().__init__(items,inventory=inventory,mode=mode)
        self.u.mem_map(BASE+8192,SIZE-8192);self.u.mem_write(BASE,make_image(BASE))
        for at,before,after in patches(BASE):self.u.mem_write(at,after)
        self.put(0x482dcc,PLAYER+0x8000);self.put(PLAYER+0x8000,PLAYER+0x8100)
        self.u.mem_write(PLAYER+0x8100,b'Save\\0001.Ssv\0');self.u.mem_write(PLAYER+0x10,b'GoodOldDays\0')
        self.put(PLAYER+0x458,PLAYER+0x7000);self.put(PLAYER+0x7004,10001)
        self.put(PLAYER+0x34,11);self.put(PLAYER+0x2e0,12345,67890)
        self.item=self.create(kind=0,subtype=10000000,w=2,h=3,sell=2000)
        self.put(self.item+0x18,2);self.put(self.item+0x7c,-1);self.put(self.item+0x1c,471)
        self.removals=[]
    def intercept(self,u,a,size,user):
        n={0x427a00:8,0x4456d0:12,0x452910:0,0x450080:0}.get(a)
        if n is None:return super().intercept(u,a,size,user)
        sp=u.reg_read(UC_X86_REG_ESP);ret=self.words(sp)[0]
        if a==0x427a00:self.removals.append(self.words(sp+4,2))
        u.reg_write(UC_X86_REG_EAX,1);u.reg_write(UC_X86_REG_ESP,sp+4+n);u.reg_write(UC_X86_REG_EIP,ret)
    def call(self,address,args=(),this=PLAYER):
        # Keep the stop sentinel outside the chronicle's private data/ring area.
        result=super().call(address,args,this)
        self.assert_idle();return result
    def assert_idle(self):assert self.words(BASE+DATA)[0]==0
    def pickup(self,index=7,item=None):return self.call(PICKUP,(index,self.item if item is None else item))
    def events(self):
        n=self.words(BASE+DATA+4)[0]
        return [decode_record(bytes(self.u.mem_read(BASE+RING+((seq-1)&2047)*64,64)),seq) for seq in range(1,n+1)]

@unittest.skipIf(IMAGE is None,'Local original EXE fixture required')
class GrailNativeTests(unittest.TestCase):
    def test_success_updates_shared_policy_immediately_but_held_item_does_not(self):
        for inventory in (False,True):
            f=NativeFixture(inventory=inventory)
            f.put(0x48ce0c,PLAYER+0x8200);f.put(PLAYER+0x8200,1,PLAYER+0x8300,0);f.put(PLAYER+0x8300,PLAYER)
            f.u.mem_write(BASE+POLICY,policy_image(['0:10000000'],[],PLAYER,b'Save\\0001.Ssv\0',b'GoodOldDays\0',True))
            flag=BASE+POLICY+HEADER+8
            f.pickup();self.assertEqual(f.words(flag)[0],int(not inventory))
            if inventory:f.call(INSERT,(f.item,),PLAYER+0x514)
            self.assertEqual(f.words(flag)[0],1);self.assertEqual(len(f.events()),1)
    def test_quick_sale_and_native_collector_work_together(self):
        f=NativeFixture();f.pickup();self.assertEqual(len(f.events()),1)
        sell_base=BASE+0x30000;f.u.mem_map(sell_base,4096);f.u.mem_write(sell_base,sale_image(sell_base))
        f.u.mem_write(0x447290,IMAGE[0x47290:0x47290+32]);f.put(PLAYER+0x4000,352,280)
        f.put(0x48ce44,1);f.put(0x48ce3c,1)
        self.assertEqual(f.call(sell_base),1);self.assertEqual(f.gold(),2000)
        self.assertEqual(len(f.events()),1);self.assertEqual(f.freed,[f.item])
    def test_native_sha_validation_projects_only_the_exact_owned_detour(self):
        f=NativeFixture();game=SimpleNamespace(pid=1,read=lambda at,n:bytes(f.u.mem_read(at,n)))
        owner=SimpleNamespace(lock=threading.RLock(),game=game,installed=patches(BASE))
        for at,n,digest in VERIFIED:
            raw=Grail.original_bytes(owner,game,at,n);self.assertEqual(hashlib.sha256(raw).hexdigest(),digest)
        f.u.mem_write(DELETE,b'\x90')
        with self.assertRaises(RuntimeError):Grail.original_bytes(owner,game,DELETE,0x5a)
    def test_native_success_records_only_after_backpack_insertion(self):
        f=NativeFixture();self.assertEqual(f.pickup(),1)
        self.assertIn(f.item,[row[0] for row in f.snapshot()]);e=f.events();self.assertEqual(len(e),1)
        self.assertEqual(e[0],dict(filename='Save\\0001.Ssv',name='GoodOldDays',key='0:10000000',map=10001,x=12345,y=67890,instance=471,level=11,player=PLAYER))
        self.assertEqual(f.words(BASE+DATA+8)[0],0)
    def test_open_inventory_cursor_waits_for_backpack_placement(self):
        f=NativeFixture(inventory=True);self.assertEqual(f.pickup(),1)
        self.assertEqual(f.words(0x48ce34)[0],f.item);self.assertFalse(f.events())
        f.call(INSERT,(f.item,),PLAYER+0x514);self.assertEqual(len(f.events()),1)
        self.assertIn(f.item,[r[0] for r in f.snapshot()])
    def test_full_backpack_failed_pickup_does_not_record_or_count_later_buy(self):
        f=NativeFixture(items=[dict(x=x,y=y) for y in range(4) for x in range(9)])
        before=f.snapshot();self.assertEqual(f.pickup(),0);self.assertEqual(f.snapshot(),before)
        self.assertFalse(f.events());self.assertEqual(f.words(BASE+DATA+8)[0],0)
        f.call(INSERT,(f.item,),PLAYER+0x514);self.assertFalse(f.events())
    def test_nonpremium_multiplayer_and_non_ground_rewards_are_excluded(self):
        for case in ('magic','multiplayer','reward'):
            f=NativeFixture(mode=int(case=='multiplayer'))
            if case=='magic':f.put(f.item+0x18,1)
            self.assertEqual(f.pickup(index=-1 if case=='reward' else 7),1)
            self.assertFalse(f.events())
    def test_second_failed_pickup_preserves_the_item_already_on_cursor(self):
        f=NativeFixture(inventory=True);self.assertEqual(f.pickup(),1)
        other=f.create(kind=0,subtype=10000100);f.put(other+0x18,2);f.put(other+0x7c,-1)
        self.assertEqual(f.pickup(item=other),0);self.assertEqual(f.words(BASE+DATA+8)[0],f.item)
        f.call(INSERT,(f.item,),PLAYER+0x514);self.assertEqual(f.events()[0]['key'],'0:10000000')
    def test_destroyed_cursor_item_cannot_match_a_reused_pointer(self):
        f=NativeFixture(inventory=True);f.pickup()
        f.call(DELETE,(0x48ce34,),PLAYER+0xa000);self.assertEqual(f.words(BASE+DATA+8)[0],0)
        f.u.mem_write(f.item,b'\0'*0x90);f.call(INSERT,(f.item,),PLAYER+0x514)
        self.assertFalse(f.events())
    def test_non_backpack_storage_does_not_complete_cursor_pickup(self):
        f=NativeFixture(inventory=True);f.pickup();f.call(INSERT,(f.item,),PLAYER+0x520)
        self.assertFalse(f.events())
    def test_ring_wrap_keeps_last_records_and_committed_sequence(self):
        f=NativeFixture()
        for i in range(2050):
            f.put(BASE+DATA+8,f.item,PLAYER);f.call(INSERT,(f.item,),PLAYER+0x514)
        self.assertEqual(f.words(BASE+DATA+4)[0],2050)
        self.assertEqual(decode_record(bytes(f.u.mem_read(BASE+RING+64,64)),2050)['player'],0)

class GrailStoreTests(unittest.TestCase):
    def test_profiles_separate_slots_and_names_and_persist_after_sale(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'journal.db';s=GrailStore(path,['0:1','1:2'])
            a=s.observe('game','0001.ssv','Hero',10);b=s.observe('game','0002.ssv','Hero',10)
            self.assertNotEqual(a,b);self.assertTrue(s.collect(a,'0:1',10001));self.assertFalse(s.collect(a,'0:1',10001))
            s.observe('game','0001.ssv','Hero',11,[])
            again=GrailStore(path,['0:1','1:2']);self.assertEqual(again.view(a)['entries']['0:1']['pickups'],2)
            self.assertFalse(again.view(b)['entries']);self.assertEqual(profile_id('GAME','0001.Ssv','Hero'),a)
    def test_baseline_manual_and_pickup_keep_distinct_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            s=GrailStore(Path(folder)/'j.db',['0:1','1:2']);a=s.observe('game','0001.ssv','Hero',10,['0:1','3:3'])
            self.assertFalse(s.collect(a,'0:1',0));s.mark(a,'1:2',True);s.mark(a,'1:2',False)
            entries=s.view(a)['entries'];self.assertIsNotNone(entries['0:1']['first_owned']);self.assertIsNotNone(entries['0:1']['first_pickup'])
            self.assertNotIn('1:2',entries);self.assertNotIn('3:3',entries)
            with self.assertRaises(ValueError):s.mark(a,'9:9',True)
            with self.assertRaises(ValueError):s.mark('missing','0:1',True)
    def test_save_codec_and_prefix_decode_match_known_equipment(self):
        hero=bytearray(0x160);hero[:5]=b'Hero\0';struct.pack_into('<I',hero,0x24,11)
        body=bytes(hero)+struct.pack('<6I',1,0,10000000,471,4,0)+struct.pack('<10I',*([0]*10))+struct.pack('<7I',1,1,21300,472,2,3,0)
        inverse=bytes(SAVE_TABLE.index(i) for i in range(256));seed=71
        encoded=bytes(inverse[v^seed] for v in body);checksum=sum(v if v<128 else v-256 for v in body)
        raw=b'ShadowFlare0005\0'+hero+struct.pack('<IBi',len(body),seed,checksum)+encoded
        self.assertEqual(read_save(raw),dict(name='Hero',level=11,owned=['0:10000000','1:21300']))
        damaged=bytearray(raw);damaged[-1]^=1
        with self.assertRaises(ValueError):read_save(damaged)
        with self.assertRaises(ValueError):read_save(raw[:-1])

if __name__=='__main__':unittest.main()
