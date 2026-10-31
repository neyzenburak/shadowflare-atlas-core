"""Run the original weather generator, particle movement and native line renderer."""
from contextlib import nullcontext
import math
import os
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

import pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
from unicorn.x86_const import *

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from rain_fix import HOOK,ORIGINAL,patches,rain_geometry,rain_wrapper,snapshot,OBJECT as NATIVE_OBJECT
import display_fix as display
from display_fix import build_changes,jump,RAIN_STATE,MODAL_INFLIGHT

FIX=Path(os.environ.get('SHADOWFLARE_FIXTURE_DIR',ROOT.parent/'shadowflare-drop-analysis/input'))
EXE=pefile.PE(str(FIX/'ShadowFlare.exe')).get_memory_mapped_image() if (FIX/'ShadowFlare.exe').exists() else None
BASE=0x30000000
STATE=BASE+RAIN_STATE
TRAMPOLINE=BASE+0x1000
STACK=0x31010000
OBJECT=0x32000000
NODES=OBJECT+0x1000
STOP=BASE+0xf00
PACKET_FN=BASE+0xe00
RAND=0x467c6e
MALLOC=0x467889
FREE=0x46787e


class RainFixture:
    def __init__(self,width=1920,height=900,patched=True,intensity=10,stub_native=False):
        self.u=Uc(UC_ARCH_X86,UC_MODE_32)
        for a,n in ((0x400000,0x100000),(BASE,0x10000),(STACK-0x10000,0x20000),(OBJECT,0x40000)):
            self.u.mem_map(a,n)
        self.u.mem_write(0x400000,EXE)
        self.put(0x473564,PACKET_FN)
        self.put(OBJECT,0,intensity,0xe08080,0)
        self.seed=7;self.allocated=[];self.freed=[];self.packets=[];self.counts=[]
        self.forced_rand=[]
        if patched:
            self.u.mem_write(TRAMPOLINE,ORIGINAL+jump(TRAMPOLINE+len(ORIGINAL),HOOK+len(ORIGINAL)))
            self.u.mem_write(BASE,rain_wrapper(BASE,TRAMPOLINE,STATE,width,height))
            self.u.mem_write(HOOK,jump(HOOK,BASE,len(ORIGINAL)))
            for a,before,after,label in patches(width,height):self.u.mem_write(a,after)
        for a in (RAND,MALLOC,FREE,PACKET_FN):self.u.hook_add(UC_HOOK_CODE,self.hook,begin=a,end=a)
        if stub_native:self.u.hook_add(UC_HOOK_CODE,self.native_stub,begin=TRAMPOLINE,end=TRAMPOLINE)

    def put(self,a,*v):self.u.mem_write(a,struct.pack('<'+'I'*len(v),*(x&0xffffffff for x in v)))
    def words(self,a,n=1):return struct.unpack('<'+'I'*n,self.u.mem_read(a,4*n))
    def ret(self,value=1,nargs=0):
        sp=self.u.reg_read(UC_X86_REG_ESP);ret=self.words(sp)[0]
        self.u.reg_write(UC_X86_REG_EAX,value&0xffffffff)
        self.u.reg_write(UC_X86_REG_ESP,sp+4+nargs*4);self.u.reg_write(UC_X86_REG_EIP,ret)
    def native_stub(self,u,a,size,user):
        sp=u.reg_read(UC_X86_REG_ESP)
        self.counts.append((self.words(sp+4,2),self.words(OBJECT+4)[0],u.reg_read(UC_X86_REG_ECX)))
        self.ret(0xabcdef01,2)
    def hook(self,u,a,size,user):
        sp=u.reg_read(UC_X86_REG_ESP)
        if a==RAND:
            self.seed=(self.seed*214013+2531011)&0xffffffff
            self.ret(self.forced_rand.pop(0) if self.forced_rand else (self.seed>>16)&0x7fff)
        elif a==MALLOC:
            assert self.words(sp+4)[0]==48
            node=NODES+len(self.allocated)*64;self.allocated.append(node);self.ret(node)
        elif a==FREE:self.freed.append(self.words(sp+4)[0]);self.ret()
        elif a==PACKET_FN:
            self.packets.append(self.words(sp+4,18));self.ret(1,18)
    def frame(self,spawn=1,block=17):
        self.put(STACK,STOP,spawn,block)
        regs=((UC_X86_REG_EBX,0x1234),(UC_X86_REG_ESI,0x5678),(UC_X86_REG_EDI,0xabcd),(UC_X86_REG_EBP,0xef01))
        for reg,value in regs:self.u.reg_write(reg,value)
        self.u.reg_write(UC_X86_REG_ESP,STACK);self.u.reg_write(UC_X86_REG_ECX,OBJECT)
        self.u.emu_start(HOOK,STOP,count=1000000)
        assert self.u.reg_read(UC_X86_REG_EIP)==STOP
        assert self.u.reg_read(UC_X86_REG_ESP)==STACK+12
        for reg,value in regs:assert self.u.reg_read(reg)==value
        return self.packets
    def node(self,x=100,age=25,angle=4.5):
        n=NODES
        self.put(n,age,x,-30,0)
        self.u.mem_write(n+16,struct.pack('<d',angle))
        self.put(n+24,2500,0,10,700,0xe08080,0)
        self.put(OBJECT+12,n)
        return n


@unittest.skipUnless(EXE,'Original ShadowFlare fixture required')
class RainTests(unittest.TestCase):
    def test_byte_fingerprints_and_entire_instruction_boundaries(self):
        import capstone
        self.assertEqual(EXE[HOOK-0x400000:HOOK-0x400000+len(ORIGINAL)],ORIGINAL)
        md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_32);md.detail=True
        changes,chunks=build_changes(BASE,1920,900,0x10001400,0x10001600)
        rain=[c for c in changes if 'rain' in c['label']]
        self.assertEqual(len(rain),4)
        for c in rain:
            a=c['address'];before=bytes.fromhex(c['before']);after=bytes.fromhex(c['after'])
            self.assertEqual(EXE[a-0x400000:a-0x400000+len(before)],before)
            self.assertEqual(sum(i.size for i in md.disasm(before,a)),len(before))
            self.assertEqual(len(before),len(after))
            for i in md.disasm(EXE[HOOK-0x400000:0x41ffe3-0x400000],HOOK):
                if i.group(capstone.CS_GRP_JUMP) and i.operands[0].type==capstone.x86.X86_OP_IMM:
                    self.assertFalse(a<i.operands[0].imm<a+len(before))
        self.assertLess(max(a+len(code) for a,code in chunks),BASE+MODAL_INFLIGHT)

    def test_original_resolution_has_identical_particles_random_calls_and_packets(self):
        old=RainFixture(640,480,False);new=RainFixture(640,480,True)
        for unused in range(3):
            old.frame();new.frame()
            self.assertEqual(old.seed,new.seed)
            self.assertEqual(old.packets,new.packets)
            self.assertEqual(old.words(OBJECT,4),new.words(OBJECT,4))
            for a in old.allocated:self.assertEqual(bytes(old.u.mem_read(a,48)),bytes(new.u.mem_read(a,48)))
        self.assertEqual(new.words(OBJECT+4)[0],10)

    def test_native_births_use_full_width_and_fractional_density(self):
        f=RainFixture(intensity=1);span,margin=rain_geometry(1920,900)
        f.forced_rand=[0,0,0,0,0,span-1,0,0,0,0]
        f.frame()
        self.assertEqual(len(f.allocated),2)
        self.assertEqual([struct.unpack('<i',f.u.mem_read(a+4,4))[0] for a in f.allocated],[-margin,1920+margin-1])
        self.assertEqual(f.words(OBJECT+4)[0],1)
        self.assertEqual(f.words(STATE+4)[0],span%1000)
        f.frame();self.assertEqual(len(f.allocated),5)

    def test_fractional_rate_is_exact_and_original_arguments_and_return_survive(self):
        for width,height in ((640,480),(1024,768),(1366,768),(1920,900),(2560,1440),(7680,4320)):
            f=RainFixture(width,height,intensity=3,stub_native=True)
            for unused in range(1000):f.frame(block=29)
            span,_=rain_geometry(width,height)
            self.assertEqual(sum(n for args,n,obj in f.counts),3*span)
            self.assertTrue(all(args==(1,29) and obj==OBJECT for args,n,obj in f.counts))
            self.assertEqual(f.words(OBJECT+4)[0],3)
            self.assertEqual(f.words(STATE)[0],0)
            self.assertEqual(f.u.reg_read(UC_X86_REG_EAX),0xabcdef01)
            self.assertEqual(f.words(STATE+4)[0],0)

    def test_weather_stop_zero_intensity_and_rate_changes(self):
        f=RainFixture(intensity=1,stub_native=True);f.frame()
        remainder=f.words(STATE+4)[0]
        f.frame(spawn=0)
        self.assertEqual(f.counts[-1][0],(0,17))
        self.assertEqual(f.words(STATE+4)[0],remainder)
        self.assertEqual(f.words(STATE+16)[0],0)
        for count in (0,-1,10):
            f.put(OBJECT+4,count);f.frame()
            self.assertEqual(f.words(OBJECT+4)[0],count&0xffffffff)
        self.assertEqual(f.words(STATE+4)[0],(10*rain_geometry(1920,900)[0])%1000)

    def test_existing_particles_continue_below_old_bottom_then_expire_natively(self):
        old=RainFixture(patched=False,intensity=0);new=RainFixture(intensity=0)
        a=old.node();new.node()
        old.frame(0);new.frame(0)
        self.assertEqual(old.freed,[a]);self.assertEqual(old.words(OBJECT+12)[0],0)
        self.assertEqual(new.freed,[]);self.assertEqual(len(new.packets),1)
        self.assertGreater(new.packets[0][7],480)
        new.put(a,45);new.frame(0)
        self.assertEqual(new.freed,[a]);self.assertEqual(new.words(OBJECT+12)[0],0)

    def detach(self,f,active_ip):
        fix=display.DisplayFix(start_worker=False);fix.game=f;fix.base=BASE
        f.pid=123;f.h=123;f.write=f.u.mem_write;f.close=lambda:None
        f.suspended=lambda:nullcontext([]);f.ips=lambda handles:[active_ip]
        f.read=lambda a,n:bytes(f.u.mem_read(a,n))
        fix.changes=[dict(address=HOOK,before=ORIGINAL.hex(),after=f.read(HOOK,len(ORIGINAL)).hex())]
        fix.changes.extend(dict(address=a,before=b.hex(),after=c.hex()) for a,b,c,label in patches(1920,900))
        freed=[]
        def exit_code(h,out):out._obj.value=259;return 1
        with patch.object(display,'ExitCode',exit_code),patch.object(display,'Free',lambda *args:freed.append(args) or 1),patch.object(display.DisplayFix,'_write',staticmethod(lambda game,a,raw:game.write(a,raw))):
            fix._detach()
        self.assertIsNone(fix.game)
        for c in fix.changes:self.assertEqual(f.read(c['address'],len(bytes.fromhex(c['before']))),bytes.fromhex(c['before']))
        return freed

    def test_detach_retains_wrapper_while_original_weather_call_is_running(self):
        f=RainFixture();f.put(STACK,STOP,1,17)
        f.u.reg_write(UC_X86_REG_ESP,STACK);f.u.reg_write(UC_X86_REG_ECX,OBJECT)
        f.u.emu_start(HOOK,HOOK+len(ORIGINAL),count=10000)
        self.assertEqual(f.words(STATE)[0],1)
        self.assertEqual(f.words(OBJECT+4)[0],25)
        self.assertEqual(self.detach(f,HOOK+len(ORIGINAL)),[])
        f.u.emu_start(HOOK+len(ORIGINAL),STOP,count=1000000)
        self.assertEqual(f.u.reg_read(UC_X86_REG_EIP),STOP)
        self.assertEqual(f.u.reg_read(UC_X86_REG_ESP),STACK+12)
        self.assertEqual(f.words(OBJECT+4)[0],10)
        self.assertEqual(f.words(STATE)[0],0)

    def test_detach_releases_idle_wrapper_and_restores_every_weather_instruction(self):
        f=RainFixture();f.frame()
        self.assertEqual(len(self.detach(f,0x401000)),1)

    def test_snapshot_reads_existing_native_particles_without_modification(self):
        f=RainFixture(intensity=0);f.node(x=1880,age=36);f.frame(0)
        f.u.mem_write(NATIVE_OBJECT,bytes(f.u.mem_read(OBJECT,16)))
        before=bytes(f.u.mem_read(NODES,48))
        f.read=lambda a,n:bytes(f.u.mem_read(a,n))
        result=snapshot(f,1920,900,STATE)
        self.assertEqual((result['particles'],result['visible']),(1,1))
        self.assertEqual(result['thirds'][2][2],1)
        self.assertEqual(result['nativeIntensity'],0)
        self.assertEqual(bytes(f.u.mem_read(NODES,48)),before)

    def test_wind_margin_covers_right_edge_at_every_height(self):
        for width,height in ((640,480),(1024,768),(1366,768),(1920,900),(2560,1440),(7680,4320)):
            f=RainFixture(width,height,intensity=0)
            angle=4.712388000000001-3.141592/10
            age=int((height-10+30)/(-math.sin(angle)*25))
            drift=int(math.cos(angle)*(2500*age//100))
            start_x=width-10-drift
            span,margin=rain_geometry(width,height)
            self.assertLess(start_x,width+margin)
            f.node(x=start_x,age=age,angle=angle);f.frame(0)
            self.assertEqual(f.freed,[])
            p=f.packets[-1]
            self.assertEqual(p[1:6],(19,0,0,0,0x200))
            self.assertEqual(p[6],width-10)
            self.assertTrue(height-40<=p[7]<height)


@unittest.skipUnless(EXE and (FIX/'RKC_UPDIB.dll').exists() and (FIX/'RKC_DIB.dll').exists(),'Native renderer fixtures required')
class RainRenderingTests(unittest.TestCase):
    def test_original_packet_renderer_draws_rain_in_the_new_right_bottom_area(self):
        f=RainFixture(intensity=0);f.node(x=1880,age=36);f.frame(0)
        packet=f.packets[-1];x,y=packet[6:8]
        self.assertGreater(x,1000);self.assertGreater(y,480)
        u=f.u
        for filename,base in (('RKC_UPDIB.dll',0x10000000),('RKC_DIB.dll',0x20000000)):
            pe=pefile.PE(str(FIX/filename));pe.relocate_image(base)
            raw=pe.get_memory_mapped_image();u.mem_map(base,(len(raw)+4095)&~4095);u.mem_write(base,raw)
        pixels=0x33000000;size=1920*900*3
        u.mem_map(pixels,(size+4095)&~4095)
        f.put(OBJECT+0x20000,OBJECT+0x20100,0,pixels)
        u.mem_write(OBJECT+0x20100,struct.pack('<IiiHHIIIIII',40,1920,900,1,24,0,size,0,0,0,0))
        f.put(OBJECT+0x20200,0,0,1919,899)
        f.put(0x100090e4,0x20001ad0)
        def call(fn,this,args):
            f.put(STACK,STOP,*args);u.reg_write(UC_X86_REG_ESP,STACK);u.reg_write(UC_X86_REG_ECX,this)
            u.emu_start(fn,STOP,count=1000000)
            self.assertEqual(u.reg_read(UC_X86_REG_EIP),STOP)
            self.assertEqual(u.reg_read(UC_X86_REG_ESP),STACK+4+4*len(args))
        call(0x100034a0,BASE+0x2000,[BASE+0x3000,*packet[2:]])
        call(0x100040a0,BASE+0x2000,[OBJECT+0x20000,OBJECT+0x20200])
        raw=bytes(u.mem_read(pixels,size))
        self.assertTrue(any(raw[((899-y)*1920+x)*3:((899-y)*1920+x)*3+3]))
        self.assertEqual(raw[:1920*3],bytes(1920*3))
        self.assertEqual(raw[((899-200)*1920+200)*3:((899-200)*1920+200)*3+3],bytes(3))


if __name__=='__main__':unittest.main()
