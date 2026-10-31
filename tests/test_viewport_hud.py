"""HUD pixels, clipping and mouse input share one coordinate transform."""
from pathlib import Path
import struct
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from display_fix import packet_proxy,hud_rect_proxy,hud_input_wrapper,RIGHT_PACKET_RANGES,build_changes


class HUDTests(unittest.TestCase):
    def machine(self,code):
        from unicorn import Uc,UC_ARCH_X86,UC_MODE_32
        u=Uc(UC_ARCH_X86,UC_MODE_32)
        for address,size in ((0x400000,0x100000),(0x2000000,0x4000),(0x3000000,0x20000)):u.mem_map(address,size)
        u.mem_write(0x2000000,code);return u

    def test_packet_translates_both_axes_for_hud_but_preserves_world_packets(self):
        from unicorn.x86_const import UC_X86_REG_ESP
        code=packet_proxy(0x2000000,0x400100,1280,7,RIGHT_PACKET_RANGES,640,(),True,420)
        for caller,expected in ((0x4039e1,(640,420)),(0x404fdb,(640,420)),(0x42fdc0,(0,0))):
            u=self.machine(code);stack=0x3001000;args=[0]*19
            u.mem_write(stack,struct.pack('<20I',caller,*args));u.reg_write(UC_X86_REG_ESP,stack)
            u.emu_start(0x2000000,0x400100,count=300)
            after=struct.unpack('<20I',u.mem_read(stack,80))
            self.assertEqual((after[7],after[8]),expected);self.assertEqual(u.reg_read(UC_X86_REG_ESP),stack)

    def test_destination_extent_and_clip_rectangle_move_with_the_image(self):
        from unicorn.x86_const import UC_X86_REG_ESP
        code=packet_proxy(0x2000000,0x400100,1280,7,RIGHT_PACKET_RANGES,640,(),True,420)
        u=self.machine(code);stack=0x3001000;args=[0]*19;args[5]=0x800;args[8]=100;args[9]=200
        u.mem_write(stack,struct.pack('<20I',0x404017,*args));u.reg_write(UC_X86_REG_ESP,stack)
        u.emu_start(0x2000000,0x400100,count=300)
        self.assertEqual(struct.unpack('<2I',u.mem_read(stack+36,8)),(740,620))
        u=self.machine(hud_rect_proxy(0x2000000,0x400100,640,420))
        u.mem_write(stack,struct.pack('<6I',0x403fd6,0x3002000,81,425,200,436));u.reg_write(UC_X86_REG_ESP,stack)
        u.emu_start(0x2000000,0x400100,count=300)
        self.assertEqual(struct.unpack('<4I',u.mem_read(stack+8,16)),(721,845,840,856))

    def test_mouse_is_local_during_native_call_and_restored_afterward(self):
        from unicorn import UC_HOOK_CODE
        from unicorn.x86_const import UC_X86_REG_ESP,UC_X86_REG_EIP,UC_X86_REG_ECX,UC_X86_REG_EAX
        counter=0x3006000;u=self.machine(hud_input_wrapper(0x2000000,0x400200,640,420,counter))
        stack=0x3001000;manager=0x3002000;array=0x3003000;player=0x3004000;point=0x3005000
        u.mem_write(0x48ce0c,struct.pack('<I',manager));u.mem_write(manager,struct.pack('<3I',1,array,0))
        u.mem_write(array,struct.pack('<I',player));u.mem_write(player+0x3fc,struct.pack('<I',point))
        u.mem_write(point,struct.pack('<2I',997,833));u.mem_write(stack,struct.pack('<I',0x400100))
        u.reg_write(UC_X86_REG_ESP,stack);u.reg_write(UC_X86_REG_ECX,player);seen=[]
        def native(machine,address,size,user):
            if address!=0x400200:return
            seen.append(tuple(struct.unpack('<2I',machine.mem_read(point,8))))
            sp=machine.reg_read(UC_X86_REG_ESP);ret=struct.unpack('<I',machine.mem_read(sp,4))[0]
            machine.reg_write(UC_X86_REG_EAX,123);machine.reg_write(UC_X86_REG_ESP,sp+4);machine.reg_write(UC_X86_REG_EIP,ret)
        u.hook_add(UC_HOOK_CODE,native);u.emu_start(0x2000000,0x400100,count=300)
        self.assertEqual(seen,[(357,413)])
        self.assertEqual(struct.unpack('<2I',u.mem_read(point,8)),(997,833))
        self.assertEqual(struct.unpack('<I',u.mem_read(counter,4))[0],0)
        self.assertEqual(u.reg_read(UC_X86_REG_EAX),123)

    def test_complete_native_display_plan_fits_the_allocated_block(self):
        changes,chunks=build_changes(0x2000000,1920,900,0x10001000,0x10002000,True,0x10003000)
        self.assertTrue(any(c['address']==0x473624 for c in changes))
        self.assertTrue(any(c['address']==0x445bd0 for c in changes))
        self.assertLess(max(a+len(b)for a,b in chunks),0x2003f00)


if __name__=='__main__':unittest.main()
