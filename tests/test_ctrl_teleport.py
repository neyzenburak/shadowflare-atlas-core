"""Execute Ctrl-click, native projection, terrain tests and native warp bookkeeping."""
import hashlib
import os
from pathlib import Path
import struct
import sys
import unittest

import pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
from unicorn.x86_const import *
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from ctrl_teleport import make_image,ground_guard,CALLSITE,HANDLER,ORIGINAL,VERIFIED,GROUND,DATA,PANELS,SIZE
from display_fix import world_gate,jump

FIX=Path(os.environ.get('SHADOWFLARE_FIXTURE_DIR',ROOT.parent/'shadowflare-drop-analysis/resolution-fix'))
EXE=pefile.PE(str(FIX/'ShadowFlare.exe')) if (FIX/'ShadowFlare.exe').exists() else None
RPG=pefile.PE(str(FIX/'RKC_RPGSCRN.dll')) if (FIX/'RKC_RPGSCRN.dll').exists() else None
BASE=0x30000000;STACK=0x31010000;PLAYER=0x32000000;INPUT=PLAYER+0x3000;MOUSE=PLAYER+0x3800
MAP=PLAYER+0x4000;GRID=PLAYER+0x5000;SCREEN=PLAYER+0x6000;MANAGER=PLAYER+0x7000
ROWS=PLAYER+0x10000;CELLS=PLAYER+0x20000;STOP=BASE+0x1e00;KEY=BASE+0x1f00;RECT=KEY+0x20


class Fixture:
    def __init__(self,width=1920,height=900,native_collision=False):
        self.u=Uc(UC_ARCH_X86,UC_MODE_32)
        for a,n in ((0,0x1000),(0x400000,0x100000),(0x10000000,0x20000),(BASE,0x10000),(STACK-0x10000,0x20000),(PLAYER,0x100000)):
            self.u.mem_map(a,n)
        self.u.mem_write(0x400000,EXE.get_memory_mapped_image())
        self.u.mem_write(0x10000000,RPG.get_memory_mapped_image())
        exports={e.name:0x10000000+e.address for e in RPG.DIRECTORY_ENTRY_EXPORT.symbols}
        for entry in EXE.DIRECTORY_ENTRY_IMPORT:
            for i in entry.imports:
                if i.name in exports:self.put(i.address,exports[i.name])
        self.u.mem_write(BASE,make_image(BASE,True))
        self.u.mem_write(BASE+0x1800,world_gate(BASE+0x1800,width,height))
        self.u.mem_write(0x445750,jump(0x445750,BASE+0x1800))
        self.put(0x4735c0,KEY);self.put(0x473624,RECT)
        self.put(0x48ce0c,MANAGER);self.put(MANAGER,1,MANAGER+0x100,0);self.put(MANAGER+0x100,PLAYER)
        self.put(PLAYER+4,7);self.put(PLAYER+0x3c8,7);self.put(PLAYER+0x1a4,950)
        self.put(PLAYER+0x3f8,INPUT,MOUSE);self.put(PLAYER+0x458,MAP)
        self.put(PLAYER+0x2e0,80,80,-40,-40,40,40)
        self.put(PLAYER+0x314,2,2);self.put(PLAYER+0x378,3)
        self.put(INPUT+8,1);self.put(INPUT+0x10,1)
        self.put(0x48d778,-1);self.put(0x482db0,0)
        self.put(0x482d14,SCREEN);self.put(SCREEN+0x18,10,5)
        self.put(MAP+0x3c,GRID);self.put(MAP+0x44,MAP+0x100,MAP+0x200)
        self.put(GRID+0x18,160,160,400,400,-200,-200,ROWS)
        for y in range(400):self.put(ROWS+y*4,CELLS+y*800)
        self.ctrl=True;self.collision=True;self.fallback=[];self.collisions=[];self.projections=[]
        for a in (KEY,RECT,HANDLER):self.u.hook_add(UC_HOOK_CODE,self.hook,begin=a,end=a)
        if not native_collision:self.u.hook_add(UC_HOOK_CODE,self.hook,begin=0x4145b0,end=0x4145b0)
    def put(self,a,*v):self.u.mem_write(a,struct.pack('<'+'I'*len(v),*(i&0xffffffff for i in v)))
    def words(self,a,n=1):return struct.unpack('<'+'I'*n,self.u.mem_read(a,n*4))
    def signed(self,a,n=1):return struct.unpack('<'+'i'*n,self.u.mem_read(a,n*4))
    def ret(self,value=1,nargs=0):
        sp=self.u.reg_read(UC_X86_REG_ESP);ret=self.words(sp)[0]
        self.u.reg_write(UC_X86_REG_EAX,value);self.u.reg_write(UC_X86_REG_ESP,sp+4+nargs*4);self.u.reg_write(UC_X86_REG_EIP,ret)
    def hook(self,u,a,size,user):
        sp=u.reg_read(UC_X86_REG_ESP)
        if a==KEY:
            assert self.words(sp+4)[0]==17;self.ret(0x8000 if self.ctrl else 0,1)
        elif a==RECT:
            args=self.words(sp+4,5);self.put(args[0],*args[1:]);self.ret(1,5)
        elif a==HANDLER:self.fallback.append(u.reg_read(UC_X86_REG_ECX));self.ret(37)
        elif a==0x4145b0:
            self.collisions.append(self.words(sp+4,7));self.ret(int(self.collision),7)
    def block(self,x,y,flag=1):
        self.u.mem_write(CELLS+((y+200)*400+x+200)*2,struct.pack('<H',flag))
    def run(self,x=1300,y=500):
        self.put(MOUSE,x,y);self.put(STACK,STOP)
        regs={UC_X86_REG_EBX:111,UC_X86_REG_ESI:222,UC_X86_REG_EDI:333,UC_X86_REG_EBP:444}
        for r,v in regs.items():self.u.reg_write(r,v)
        self.u.reg_write(UC_X86_REG_ESP,STACK);self.u.reg_write(UC_X86_REG_ECX,PLAYER)
        self.u.emu_start(BASE,STOP,count=1000000)
        assert self.u.reg_read(UC_X86_REG_EIP)==STOP
        assert self.u.reg_read(UC_X86_REG_ESP)==STACK+4
        for r,v in regs.items():assert self.u.reg_read(r)==v
        assert self.words(BASE+DATA)[0]==0
        return self.u.reg_read(UC_X86_REG_EAX)


@unittest.skipUnless(EXE and RPG,'Original EXE and renderer fixtures required')
class CtrlTeleportTests(unittest.TestCase):
    def test_native_hook_and_callee_fingerprints(self):
        image=EXE.get_memory_mapped_image()
        self.assertEqual(image[CALLSITE-0x400000:CALLSITE-0x400000+5],ORIGINAL)
        for a,n,digest in VERIFIED:self.assertEqual(hashlib.sha256(image[a-0x400000:a-0x400000+n]).hexdigest(),digest)
        self.assertEqual(len(make_image(BASE)),SIZE)
    def test_native_projection_history_path_and_action_match_successful_warp(self):
        f=Fixture();before=bytes(f.u.mem_read(PLAYER,0x1700));self.assertEqual(f.run(),1)
        target=(11500,-1501)
        self.assertEqual(f.signed(PLAYER+0x2e0,2),target)
        self.assertEqual(f.words(BASE+DATA+8,2),(1,0))
        self.assertEqual(f.signed(BASE+DATA+16,6),(1300,500,*target,80,80))
        self.assertEqual(f.words(PLAYER+0x378)[0],0xffffffff)
        self.assertEqual(f.signed(PLAYER+0x398,2),target)
        self.assertEqual(f.words(PLAYER+0x314,2),(0,1))
        self.assertEqual(f.words(PLAYER+0x1a4)[0],950)
        self.assertEqual(f.fallback,[])
        self.assertTrue(all(f.signed(PLAYER+0xca4+i*8,2)==target for i in range(180)))
        args=f.collisions[0];self.assertEqual(args[:2],(MAP,7));self.assertEqual(args[3:],(PLAYER+0x2e8,0,0,0))
        self.assertEqual(f.signed(args[2],2),target)
        self.assertEqual(bytes(f.u.mem_read(PLAYER+0x4e8,0x600)),before[0x4e8:0xae8])
    def test_original_camera_offsets_and_negative_coordinates_are_used(self):
        f=Fixture();f.put(0x48cdf4,200,-100,30,20);f.run(1400,500)
        self.assertEqual(f.signed(PLAYER+0x2e0,2),(11650,-4051))
    def test_wide_screen_clicks_remain_accurate_across_resolutions(self):
        for w,h in ((640,480),(1024,768),(1366,768),(1920,900)):
            f=Fixture(w,h);f.run(w-80,h//2)
            self.assertEqual(f.signed(PLAYER+0x2e0,2),(5*(w-80)+10*(h//2),-5*(w-80)+10*(h//2)-(1 if -5*(w-80)+10*(h//2)<0 else 0)))
    def test_no_control_disabled_other_player_dead_and_busy_keep_native_handler(self):
        cases=[lambda f:setattr(f,'ctrl',False),lambda f:f.put(BASE+DATA+4,0),lambda f:f.put(MANAGER+8,-1),
               lambda f:f.put(0x482db0,1),lambda f:f.put(PLAYER+0x1a4,0),lambda f:f.put(PLAYER+0x404,1),
               lambda f:f.put(PLAYER+0x43c,1),lambda f:f.put(PLAYER+0x2dc,1),lambda f:f.put(PLAYER+0x410,1),
               lambda f:f.put(0x48d778,300),lambda f:f.put(0x48ce34,PLAYER+0x8000)]
        for setup in cases:
            f=Fixture();setup(f);self.assertEqual(f.run(),37);self.assertEqual(f.fallback,[PLAYER]);self.assertEqual(f.signed(PLAYER+0x2e0,2),(80,80))
    def test_every_panel_including_map_inventory_and_skills_keeps_native_click(self):
        for flag in PANELS:
            f=Fixture();f.put(flag,1);self.assertEqual(f.run(),37);self.assertEqual(f.words(BASE+DATA+8)[0],0)
    def test_closed_text_dialog_can_leave_input_mode_one_without_blocking_teleport(self):
        f=Fixture();f.put(0x48d708,1)
        self.assertEqual(f.run(),1);self.assertEqual(f.words(BASE+DATA+8)[0],1)
    def test_hotbar_hud_and_outside_client_do_not_teleport(self):
        for x,y in ((960,870),(660,820),(1020,820),(-1,400),(1920,400),(1500,900)):
            f=Fixture();self.assertEqual(f.run(x,y),37,(x,y));self.assertEqual(f.words(BASE+DATA+8)[0],0)
    def test_walls_body_edges_and_outside_map_consume_click_without_moving(self):
        for x,y,blocked in ((1300,500,(71,-10)),(1300,500,(72,-10)),(1300,506,(72,-9))):
            f=Fixture();f.block(*blocked);self.assertEqual(f.run(x,y),1)
            self.assertEqual(f.words(BASE+DATA+8,2),(0,1));self.assertEqual(f.signed(PLAYER+0x2e0,2),(80,80))
        f=Fixture();f.put(GRID+0x28,0,0);f.run();self.assertEqual(f.words(BASE+DATA+12)[0],1)
    def test_native_collision_rejection_keeps_position_history_and_path(self):
        f=Fixture();f.collision=False;before=bytes(f.u.mem_read(PLAYER,0x1700));f.run()
        self.assertEqual(bytes(f.u.mem_read(PLAYER,0x1700)),before)
        self.assertEqual(f.words(BASE+DATA+8,2),(0,1));self.assertEqual(f.fallback,[])
    def test_held_button_cannot_chain_teleport_or_leak_into_normal_movement(self):
        f=Fixture();f.run();f.put(INPUT+0x10,0)
        for i in range(20):self.assertEqual(f.run(1500+i,550),1)
        self.assertEqual(f.words(BASE+DATA+8,2),(1,0));self.assertEqual(f.fallback,[])
        f.put(INPUT+8,0);self.assertEqual(f.run(),37)
        f.put(INPUT+8,1);f.put(INPUT+0x10,1);f.run(1500,550)
        self.assertEqual(f.words(BASE+DATA+8)[0],2)
    def test_right_click_and_adding_control_to_an_existing_left_hold_do_not_warp(self):
        f=Fixture();f.put(INPUT+0x10,0);f.put(INPUT+0x2c,1)
        self.assertEqual(f.run(),37);self.assertEqual(f.words(BASE+DATA+8)[0],0)
    def test_full_original_collision_function_accepts_real_ground_and_rejects_blocked_cells(self):
        f=Fixture(native_collision=True);self.assertEqual(f.run(),1)
        self.assertEqual(f.words(BASE+DATA+8,2),(1,0))
        # Check native collision independently too: bypass the preceding guard.
        f=Fixture(native_collision=True);f.block(71,-10)
        point=PLAYER+0x9000;f.put(point,11500,-1500)
        f.put(STACK,STOP,MAP,7,point,PLAYER+0x2e8,0,0,0)
        f.u.reg_write(UC_X86_REG_ESP,STACK);f.u.reg_write(UC_X86_REG_ECX,0x482df4)
        f.u.emu_start(0x4145b0,STOP,count=1000000)
        self.assertEqual(f.u.reg_read(UC_X86_REG_EIP),STOP)
        self.assertEqual(f.u.reg_read(UC_X86_REG_EAX),0)


if __name__=='__main__':unittest.main()
