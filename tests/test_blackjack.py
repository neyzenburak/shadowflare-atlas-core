"""Run the real x86 dealer, scorer and result code with the blackjack detour."""
from pathlib import Path
import random
import struct
import sys
import unittest
from contextlib import nullcontext
from unittest.mock import patch

import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import *

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
import blackjack as b

EXE=ROOT.parent/'shadowflare-drop-analysis/input/ShadowFlare.exe'
IMAGE=pefile.PE(str(EXE)).get_memory_mapped_image() if EXE.exists() else None
BASE=0x30000000
STACK=BASE+0xe0000
STOP=BASE+0xff000
OTHER=BASE+0x10000


class Machine:
    def __init__(self,seed=0,patched=True):
        self.u=Uc(UC_ARCH_X86,UC_MODE_32)
        self.u.mem_map(0x400000,0x100000);self.u.mem_map(BASE,0x100000)
        self.u.mem_write(0x400000,IMAGE);self.u.mem_write(BASE,b.make_stub(BASE))
        self.rng=random.Random(seed);self.sequence=[];self.rng_calls=0
        self.u.hook_add(UC_HOOK_CODE,self.intercept)
        self.install(patched);self.reset()
    def install(self,enabled):self.u.mem_write(b.HOOK,b.detour(BASE) if enabled else b.ORIGINAL)
    def read(self,address,length):return bytes(self.u.mem_read(address,length))
    def words(self,address,count=1):return struct.unpack('<'+'I'*count,self.read(address,count*4))
    def put(self,address,*values):self.u.mem_write(address,struct.pack('<'+'I'*len(values),*(v&0xffffffff for v in values)))
    def intercept(self,u,address,size,data):
        if address!=0x467c6e:return
        self.rng_calls+=1
        value=self.sequence.pop(0) if self.sequence else self.rng.randrange(32768)
        sp=u.reg_read(UC_X86_REG_ESP);ret=self.words(sp)[0]
        u.reg_write(UC_X86_REG_EAX,value);u.reg_write(UC_X86_REG_ESP,sp+4);u.reg_write(UC_X86_REG_EIP,ret)
    def call(self,address,args=(),this=b.MANAGER):
        self.put(STACK,STOP,*args);self.u.reg_write(UC_X86_REG_ESP,STACK);self.u.reg_write(UC_X86_REG_ECX,this)
        preserved={UC_X86_REG_EBX:101,UC_X86_REG_EBP:202,UC_X86_REG_ESI:303,UC_X86_REG_EDI:404}
        for register,value in preserved.items():self.u.reg_write(register,value)
        self.u.emu_start(address,STOP,count=2000000)
        assert self.u.reg_read(UC_X86_REG_EIP)==STOP,'native deal did not terminate'
        assert self.u.reg_read(UC_X86_REG_ESP)==STACK+4+len(args)*4,'stack changed'
        for register,value in preserved.items():assert self.u.reg_read(register)==value,'callee-saved register changed'
        return self.u.reg_read(UC_X86_REG_EAX)
    def reset(self,this=b.MANAGER):self.call(0x403560,this=this);self.put(b.WINDOW_FLAG,1)
    def draw(self,side,joker=0,hidden=0,this=b.MANAGER):return self.call(0x4035a0,(side,joker,hidden),this)
    def cards(self,side,this=b.MANAGER):
        offset=0 if side==1 else 0x44;count=self.words(this+offset)[0]
        return self.words(this+offset+4,count)
    def deal(self,joker=0):
        # This is the order in 40DB4D / 40DB7D / 40DBAC / 40DBE0.
        for side,hidden in [(0,0),(1,0),(0,1),(1,0)]:self.draw(side,joker,hidden)
    def score(self,side):return self.call(0x4036d0,(side,))


@unittest.skipIf(IMAGE is None,'Local original EXE fixture required')
class BlackjackTests(unittest.TestCase):
    def test_real_initial_deals_have_king_ace_and_native_21(self):
        for seed in range(128):
            m=Machine(seed);m.deal()
            self.assertEqual([v&0xffff for v in m.cards(1)],[13,1])
            self.assertEqual(m.score(1),21)
            all_cards=m.cards(0)+m.cards(1)
            self.assertEqual(len(set(v&0x7fffffff for v in all_cards)),4)
            self.assertTrue(m.cards(0)[1]&0x80000000)
            self.assertTrue(all(not v&0x80000000 for v in m.cards(1)))
    def test_dealer_only_draws_and_other_manager_are_unchanged(self):
        for side,this in [(0,b.MANAGER),(1,OTHER),(0,OTHER)]:
            for seed in range(8):
                native,cheat=Machine(seed,False),Machine(seed,True)
                native.reset(this);cheat.reset(this)
                for _ in range(8):
                    native.draw(side,this=this);cheat.draw(side,this=this)
                self.assertEqual(native.cards(side,this),cheat.cards(side,this))
                self.assertEqual(native.rng_calls,cheat.rng_calls)
    def test_duplicate_forced_rank_retries_with_a_new_suit(self):
        m=Machine();m.put(b.MANAGER+0x44,1,13)  # dealer already has K, suit 0
        m.sequence=[0,13]
        m.draw(1)
        self.assertEqual(m.cards(1),(0x1000d,));self.assertEqual(m.rng_calls,2)
    def test_optional_joker_cannot_create_an_invalid_king_sprite(self):
        m=Machine();m.sequence=[52,52];m.draw(1,joker=1);m.draw(1,joker=1)
        self.assertEqual(m.cards(1),(13,1));self.assertEqual(m.score(1),21)
    def test_later_hits_keep_native_rank_and_hidden_flag(self):
        m=Machine();m.draw(1);m.draw(1);m.sequence=[7];m.draw(1,hidden=1)
        self.assertEqual(m.cards(1)[2],0x80000008)
    def test_native_result_keeps_draw_and_natural_blackjack_rules(self):
        for dealer,result in [([9,10],1),([13,0x10001],0),([7,6,8],1)]:
            m=Machine();m.draw(1);m.draw(1);m.put(b.MANAGER+0x44,len(dealer),*dealer)
            self.assertEqual(m.call(0x4037c0),result)
    def test_disable_restores_original_dealing(self):
        for seed in range(8):
            m,native=Machine(seed),Machine(seed,False);m.install(False);m.deal();native.deal()
            self.assertEqual(m.cards(1),native.cards(1));self.assertEqual(m.cards(0),native.cards(0))
            self.assertEqual(m.read(b.HOOK,len(b.ORIGINAL)),b.ORIGINAL)
    def test_fingerprints_and_snapshot(self):
        m=Machine(patched=False);b.verify(m);m.install(True);m.deal();snap=b.snapshot(m)
        self.assertTrue(snap['windowOpen']);self.assertEqual([c['label'] for c in snap['playerCards']],['K','A'])
        self.assertEqual(snap['dealerCount'],2)
        with self.assertRaises(RuntimeError):b.verify(m)
        m.put(b.MANAGER,17);self.assertIsNone(b.snapshot(m))
        self.assertIsNone(b.snapshot(None))
    def test_trainer_toggle_and_reset_restore_the_native_generator(self):
        import trainer
        m=Machine(patched=False);m.h=42;m.write=lambda address,raw:m.u.mem_write(address,raw)
        m.suspended=lambda:nullcontext([]);m.ips=lambda handles:[]
        control=trainer.Trainer(start_worker=False);control.game=m
        control._connect=lambda:m;control._state=lambda game:{'player':123};control._backup=lambda game:None
        def apply(changes):
            for change in changes:
                self.assertEqual(m.read(change['address'],len(change['before'])),change['before'])
                m.write(change['address'],change['after'])
        control._patch=apply
        with patch.object(trainer,'Alloc',return_value=BASE),patch.object(trainer,'Flush',return_value=True),patch.object(trainer,'Free',return_value=True) as free:
            state=control.toggle(b.ID,True);self.assertIn(b.ID,state['active']);self.assertEqual(state['version'],3)
            m.deal();self.assertEqual([c['label'] for c in control.info()['blackjack']['playerCards']],['K','A'])
            control.reset();self.assertNotIn(b.ID,control.info()['active']);self.assertEqual(m.read(b.HOOK,len(b.ORIGINAL)),b.ORIGINAL)
            free.assert_called_once()
        control.game=None
        for ident,enabled in [('invalid',True),(b.ID,'true')]:
            with self.assertRaises(ValueError):control.toggle(ident,enabled)


if __name__=='__main__':unittest.main()
