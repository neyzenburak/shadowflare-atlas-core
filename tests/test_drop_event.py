"""Execute native loot rounds, filtered item lifetimes and argument preservation."""
import hashlib,math,os,struct,sys,unittest,threading
from types import SimpleNamespace
from pathlib import Path
import pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
from unicorn.x86_const import *
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from drop_event import (make_event_image,packed_options,CALLSITE,ORIGINAL_CALL,
    NATIVE_DROP,NATIVE_BYTES,EVENT_DATA,EVENT_WORDS,LEASE_MS,POLICY_SLOT)
from grail_policy import policy_image
from live_drop import GAME_MODE
from grail_native import make_image as grail_image,patches as grail_patches,DATA as GRAIL_DATA
from grail import Grail
FIXTURE=Path(os.environ.get('SHADOWFLARE_FIXTURE_DIR',ROOT.parent/'shadowflare-drop-analysis/resolution-fix'))/'ShadowFlare.exe'
IMAGE=pefile.PE(str(FIXTURE)).get_memory_mapped_image() if FIXTURE.exists() else None
BASE=0x31000000;STACK=0x32010000;GAME=0x33000000;PLAYERS=GAME+0x10000
ENEMY=GAME+0x20000;ITEMS=GAME+0x30000;BANK=GAME+0x90000;VTABLE=BANK+0x1000
STOP=BASE+0x1800;TIMER=STOP+0x100;TABLE=STOP+0x200;CELL=STOP+0x300;DTOR=STOP+0x400

class LootFixture:
    def __init__(self,selections=((0,0,0),),factor=100,premium=True,attempts=1,
                 age=0,mode=0,threshold=100,null_every=0,change_options=None,grail=False,
                 exclude=False,found=None,policy_ready=True,policy_mismatch=False):
        # Synthetic selector rows use fixed IDs. The original EXE performs the
        # threshold/slot draws and the actual item-position/map insertion path.
        self.u=Uc(UC_ARCH_X86,UC_MODE_32);self.data=BASE+EVENT_DATA
        for a,n in ((0x400000,0x100000),(BASE,8192),(STACK-0x10000,0x20000),(GAME,0x100000)):self.u.mem_map(a,n)
        self.u.mem_write(0x400000,IMAGE);self.u.mem_write(BASE,make_event_image(BASE,TIMER))
        self.u.mem_write(CALLSITE,b'\xe8'+struct.pack('<i',BASE-CALLSITE-5))
        self.put(self.data,packed_options(factor,premium,exclude),100000-age,*([0]*(EVENT_WORDS-2)))
        self.put(GAME_MODE,mode);self.put(0x48ce14,BANK);self.put(0x48ce0c,GAME)
        self.put(GAME+0xa018,PLAYERS);self.put(ENEMY+0x180,0);self.put(ENEMY+0x18,10000,20000)
        self.put(0x47353c,TABLE);self.put(0x473540,CELL);self.put(VTABLE,DTOR)
        if found is not None:
            filename=b'Save\\0001.Ssv\0';name=b'Hero\0'
            self.put(GAME,1,GAME+0xf000,0);self.put(GAME+0xf000,PLAYERS)
            self.put(0x482dcc,GAME+0xc0100);self.put(GAME+0xc0100,GAME+0xc0000)
            self.u.mem_write(GAME+0xc0000,filename);self.u.mem_write(PLAYERS+0x10,name)
            keys=[f'{c}:{i}' for c,i,r in selections if c<=2 and r==2]
            policy=policy_image(keys,found,PLAYERS,filename,name,policy_ready)
            self.u.mem_write(GAME+0xb0000,policy);self.put(BASE+POLICY_SLOT,GAME+0xb0000)
            if policy_mismatch:self.u.mem_write(PLAYERS+0x10,b'Other')
        if grail:
            self.grail_base=0x34000000;image=grail_image(self.grail_base)
            self.u.mem_map(self.grail_base,(len(image)+4095)&~4095);self.u.mem_write(self.grail_base,image)
            for at,old,after in grail_patches(self.grail_base):
                assert bytes(self.u.mem_read(at,len(old)))==old
                self.u.mem_write(at,after)
        self.selections=selections;self.attempts=attempts;self.threshold=threshold
        self.random_calls=[];self.draw=0;self.created=[];self.freed=[];self.ground=[]
        self.null_every=null_every;self.factory_calls=[];self.change_options=change_options
        self.u.hook_add(UC_HOOK_CODE,self.intercept)
    def put(self,a,*v):self.u.mem_write(a,struct.pack('<'+'I'*len(v),*(x&0xffffffff for x in v)))
    def words(self,a,n=1):return struct.unpack('<'+'I'*n,self.u.mem_read(a,n*4))
    def signed(self,a,n):return struct.unpack('<'+'i'*n,self.u.mem_read(a,n*4))
    def ret(self,value,args=0):
        sp=self.u.reg_read(UC_X86_REG_ESP);target=self.words(sp)[0]
        self.u.reg_write(UC_X86_REG_EAX,value&0xffffffff)
        self.u.reg_write(UC_X86_REG_ESP,sp+4+4*args);self.u.reg_write(UC_X86_REG_EIP,target)
    def intercept(self,u,a,size,user):
        if a not in (TIMER,TABLE,CELL,DTOR,0x467c6e,0x462d30,0x434c90,0x434cb0,0x4140a0,0x452420):return
        sp=u.reg_read(UC_X86_REG_ESP);obj=u.reg_read(UC_X86_REG_ECX)
        if a==TIMER:self.ret(100000)
        elif a==TABLE:self.ret(TABLE+0x1000+self.words(sp+4)[0]*4,1)
        elif a==CELL:
            table=(obj-TABLE-0x1000)//4;row,col=self.words(sp+4,2)
            if table==30:
                value=self.attempts if col==0 else self.threshold if col==1 else ((col-2)//2)%len(self.selections) if col%2==0 else 111
            else:
                assert table==31
                cat,ident,_=self.selections[row];value=(cat,-1,-1,ident,1)[col]
            self.ret(value,2)
        elif a==0x467c6e:
            value=0 if self.draw%2==0 else (self.draw//2)%10
            self.random_calls.append(value);self.draw+=1;self.ret(value)
        elif a==0x462d30:
            args=self.words(sp+4,3);cat,ident,_=args
            assert obj==BANK and args[2]==0
            self.factory_calls.append(args)
            if self.change_options and len(self.factory_calls)==2:self.put(self.data,self.change_options)
            if self.null_every and len(self.factory_calls)%self.null_every==0:self.ret(0,3);return
            rarity=next(r for c,i,r in self.selections if (c,i)==(cat,ident))
            ptr=ITEMS+len(self.factory_calls)*0x100;self.put(ptr,VTABLE);self.put(ptr+0xc,cat)
            self.put(ptr+0x14,ident,rarity);self.created.append(ptr);self.ret(ptr,3)
        elif a==DTOR:
            assert self.words(sp+4)[0]==1 and obj not in self.freed and obj not in self.ground
            self.freed.append(obj);u.mem_write(obj,b'\xdd'*0x90);self.ret(0,1)
        elif a==0x434c90:
            index=self.words(sp+4)[0];self.put(PLAYERS+0x2d8,int(index==0));self.ret(PLAYERS,1)
        elif a==0x434cb0:self.ret(PLAYERS)
        elif a==0x4140a0:
            origin,lo,hi,radius,out=self.words(sp+4,5)
            angle=struct.unpack('<d',struct.pack('<II',lo,hi))[0];x,y=self.signed(origin,2)
            self.put(out,x+round(radius*math.cos(angle)),y+round(radius*math.sin(angle)));self.ret(1,5)
        elif a==0x452420:
            ptr=self.words(sp+4)[0];assert ptr in self.created and ptr not in self.freed
            self.ground.append(ptr);self.ret(1,3)
    def run(self,direct=False):
        args=(0,0,10000,20000,0,0) if direct else ()
        self.put(STACK,STOP,*args);self.u.reg_write(UC_X86_REG_ESP,STACK)
        self.u.reg_write(UC_X86_REG_ECX,GAME if direct else ENEMY)
        registers={UC_X86_REG_EBX:101,UC_X86_REG_ESI:202,UC_X86_REG_EDI:303,UC_X86_REG_EBP:404}
        for r,v in registers.items():self.u.reg_write(r,v)
        self.u.emu_start(NATIVE_DROP if direct else 0x45a000,STOP,count=10000000)
        assert self.u.reg_read(UC_X86_REG_EIP)==STOP
        assert self.u.reg_read(UC_X86_REG_ESP)==STACK+4+len(args)*4
        for r,v in registers.items():assert self.u.reg_read(r)==v
        assert bytes(self.u.mem_read(NATIVE_DROP,len(NATIVE_BYTES)))==NATIVE_BYTES
        assert set(self.created)==set(self.freed)|set(self.ground)
        assert not set(self.freed)&set(self.ground)
        self.counts=self.words(self.data,EVENT_WORDS);return self
    def kinds(self):return [(*self.words(p+0xc),*self.words(p+0x14,2)) for p in self.ground]

@unittest.skipIf(IMAGE is None,'Local original EXE fixture required')
class DropEventNativeTests(unittest.TestCase):
    def test_bonus_normal_magic_consumables_are_rejected_without_changing_rng(self):
        selections=((0,1,0),(0,0x80000001,1),(3,7,0),(4,2,0),(4,3,0))
        for selection in selections:
            with self.subTest(selection=selection):
                em=LootFixture(selections=(selection,)).run()
                normal=LootFixture(selections=(selection,),premium=False).run()
                self.assertEqual(em.kinds(),[selection]);self.assertEqual(len(em.freed),99)
                self.assertEqual(em.counts[3:6],(1,100,1));self.assertEqual(em.counts[9:11],(99,0))
                self.assertEqual(em.random_calls,normal.random_calls)
                self.assertEqual(em.factory_calls,normal.factory_calls)
    def test_all_three_premium_categories_multiply_even_with_small_ids(self):
        for cat in (0,1,2):
            em=LootFixture(selections=((cat,1,2),)).run()
            self.assertEqual(len(em.ground),100);self.assertEqual(em.freed,[])
            self.assertEqual(em.counts[9:11],(0,99))
    def test_rarity_alone_does_not_accept_non_equipment(self):
        em=LootFixture(selections=((3,0x80000001,2),)).run()
        self.assertEqual(len(em.ground),1);self.assertEqual(len(em.freed),99)
    def test_boss_preserves_whole_normal_round_and_no_forced_premium_reroll(self):
        choices=((0,1,0),(0,2,1),(0,3,2),(1,4,2),(2,5,2),(3,6,0),(4,2,0),(4,3,0),(4,0,0),(4,1,0))
        em=LootFixture(selections=choices,attempts=10).run()
        self.assertEqual(em.kinds()[:10],list(choices))
        self.assertEqual(em.kinds()[10:],list(choices[2:5])*99)
        self.assertEqual(em.counts[3:8],(1,100,8+3*99,99,99))
        self.assertEqual(em.counts[9:11],(495,297))
        self.assertEqual(len(em.random_calls),2000)
        positions=[em.signed(p+0x48,2) for p in em.ground if em.words(p+0xc)[0]!=4 or em.words(p+0x14)[0]>1]
        self.assertEqual(len(set(positions)),len(positions))
    def test_original_mode_and_thousand_rounds_keep_existing_exemptions(self):
        for premium in (False,True):
            em=LootFixture(selections=((4,0,0),(4,1,0),(0,2,2)),factor=1000,premium=premium,attempts=3).run()
            self.assertEqual(em.counts[3:5],(1,1000))
            self.assertEqual(sum(c==4 and i==0 for c,i,r in em.kinds()),1)
            self.assertEqual(sum(c==4 and i==1 for c,i,r in em.kinds()),1)
    def test_factory_failure_has_no_destructor_or_invalid_map_entry(self):
        em=LootFixture(selections=((0,1,0),(0,2,2)),null_every=3).run()
        self.assertEqual(len(em.created),67);self.assertEqual(len(em.ground)+len(em.freed),67)
        self.assertEqual(em.counts[9],len(em.freed));self.assertEqual(em.counts[10],len(em.ground)-1)
    def test_disabled_expired_multiplayer_and_direct_calls_keep_native_loot(self):
        for options in ({'factor':1},{'age':LEASE_MS+1},{'mode':1},{'mode':2}):
            em=LootFixture(selections=((0,1,0),),attempts=3,**options).run()
            self.assertEqual(len(em.ground),3);self.assertEqual(em.freed,[])
            self.assertEqual(em.counts[3:5],(0,1))
        direct=LootFixture(selections=((0,1,0),),attempts=3).run(direct=True)
        self.assertEqual(len(direct.ground),3);self.assertEqual(direct.counts[2:],(0,)*(EVENT_WORDS-2))
    def test_mode_is_captured_per_death_even_when_global_options_change(self):
        em=LootFixture(change_options=packed_options(2,False)).run()
        self.assertEqual(len(em.ground),1);self.assertEqual(em.counts[9:11],(99,0))
        em=LootFixture(premium=False,change_options=packed_options(2,True)).run()
        self.assertEqual(len(em.ground),100);self.assertEqual(em.freed,[])
    def test_native_deleter_fingerprint_is_the_verified_original(self):
        self.assertEqual(hashlib.sha256(IMAGE[0x65640:0x6569a]).hexdigest(),
                         'f3f55fe46435dce3f690df49aaf654fc73d2c784a24e2a6ca862c680ada8ca95')
    def test_grail_delete_observer_is_preserved_and_filtering_does_not_record_finds(self):
        em=LootFixture(selections=((0,1,0),(0,2,2)),grail=True).run()
        self.assertEqual(len(em.freed),49);self.assertEqual(len(em.ground),51)
        self.assertEqual(em.words(em.grail_base+GRAIL_DATA,3),(0,0,0))
        game=SimpleNamespace(pid=1,read=lambda a,n:bytes(em.u.mem_read(a,n)))
        observer=SimpleNamespace(lock=threading.RLock(),game=game,installed=grail_patches(em.grail_base))
        projected=Grail.original_bytes(observer,game,0x465640,0x5a)
        self.assertEqual(projected,IMAGE[0x65640:0x6569a])
        em.u.mem_write(0x465640,b'\x90')
        with self.assertRaises(RuntimeError):Grail.original_bytes(observer,game,0x465640,0x5a)
    def test_found_premium_is_rejected_including_normal_round_without_rerolls(self):
        selections=((0,1,2),(0,2,2),(0,3,1),(3,4,0))
        em=LootFixture(selections=selections,exclude=True,found=['0:1'],attempts=10).run()
        self.assertNotIn((0,1,2),em.kinds());self.assertIn((0,2,2),em.kinds())
        self.assertIn((0,3,1),em.kinds()[:10]);self.assertIn((3,4,0),em.kinds()[:10])
        self.assertEqual(em.counts[11],300)
        baseline=LootFixture(selections=selections,exclude=False,attempts=10).run()
        self.assertEqual(em.factory_calls,baseline.factory_calls);self.assertEqual(em.random_calls,baseline.random_calls)
    def test_found_filter_works_at_one_x_and_cannot_inherit_other_character(self):
        for options in ({'policy_ready':False},{'policy_mismatch':True},{'exclude':False}):
            em=LootFixture(selections=((0,1,2),),factor=1,found=['0:1'],**({'exclude':True}|options)).run()
            self.assertEqual(len(em.ground),1);self.assertEqual(em.counts[11],0)
        em=LootFixture(selections=((0,1,2),),factor=1,exclude=True,found=['0:1']).run()
        self.assertEqual(em.ground,[]);self.assertEqual(em.counts[11],1)

class EventOptionsTests(unittest.TestCase):
    def test_options_reject_invalid_factors_and_modes(self):
        self.assertEqual(packed_options(100,True),0x10064)
        self.assertEqual(packed_options(1000,False),1000)
        for value in (True,False,0,-1,1001,1.5,'100',None):
            with self.assertRaises(ValueError):packed_options(value,False)
        for mode in (0,1,'true',None):
            with self.assertRaises(ValueError):packed_options(100,mode)

if __name__=='__main__':unittest.main()
