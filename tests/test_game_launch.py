"""Independent viewport code: native fingerprints, geometry and x86 ABI."""
from pathlib import Path
import json
import struct
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from resolution_layout import geometry,validate_size
from resolution_native import build_changes,scene_clip,scene_camera
from game_launch import GameLauncher
from ct_table import image_bytes


class ResolutionTests(unittest.TestCase):
    def test_geometry_and_invalid_dimensions(self):
        self.assertEqual((geometry(1920,900)['dx'],geometry(1920,900)['dy']),(640,420))
        self.assertEqual((geometry(1365,769)['halfWidth'],geometry(1365,769)['halfHeight']),(682,384))
        for size in ((True,900),(1920,900.5),(639,900),(1920,479),(7681,900),(1920,4321)):
            with self.assertRaises(ValueError):validate_size(*size)

    def test_original_game_spans_and_complete_instructions(self):
        exe=ROOT.parent/'shadowflare-drop-analysis/input/ShadowFlare.exe'
        if not exe.exists():self.skipTest('Local original executable fixture required')
        import capstone
        cs=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_32)
        for width,height in ((640,480),(1365,769),(1920,900),(2560,1440)):
            changes,chunks=build_changes(0x2000000,width,height)
            self.assertEqual(len(changes),33)
            for row in changes:
                self.assertEqual(image_bytes(exe,row['address'],len(row['before'])),row['before'])
                self.assertEqual(len(row['after']),len(row['before']))
                self.assertEqual(sum(i.size for i in cs.disasm(row['after'],row['address'])),len(row['after']))
            mapping={r['address']:r for r in changes}
            self.assertEqual(struct.unpack_from('<I',mapping[0x40265a]['after'],1)[0],height)
            self.assertEqual(struct.unpack_from('<I',mapping[0x40265f]['after'],1)[0],width)

    def test_existing_game_is_never_closed_or_reconfigured(self):
        launcher=GameLauncher();before=launcher.settings.copy()
        with patch('live_drop.game_pids',return_value=[1234]),patch.object(launcher,'configure')as configure:
            with self.assertRaisesRegex(RuntimeError,'zaten'):launcher.launch({'width':1280,'height':720})
            configure.assert_not_called()
        self.assertEqual(launcher.settings,before)

    def test_startup_keeps_display_fix_original_bytes(self):
        changes,chunks=build_changes(0x2000000,1920,900)
        patched={r['address']+i:b for r in changes for i,b in enumerate(r['after'])}
        plan=json.loads((ROOT/'app/display-fix-plan.json').read_text('utf8'))
        spans=[(r['address'],bytes.fromhex(r['before']))for r in plan['immediates']]
        spans += [(int(a),bytes.fromhex(b))for a,b in plan['entries'].items()]
        for address,before in spans:
            for i,b in enumerate(before):
                if address+i in patched:self.assertEqual(patched[address+i],b,f'{address+i:08x}')

    def machine(self):
        from unicorn import Uc,UC_ARCH_X86,UC_MODE_32
        u=Uc(UC_ARCH_X86,UC_MODE_32)
        for address,size in ((0x400000,0x100000),(0x2000000,0x1000),(0x3000000,0x20000)):u.mem_map(address,size)
        return u

    def test_clip_uses_whole_client_without_panel_offsets(self):
        from unicorn import UC_HOOK_CODE
        from unicorn.x86_const import UC_X86_REG_ESP,UC_X86_REG_EIP
        for width,height in ((640,480),(1920,900)):
            u=self.machine();stack=0x3001000;target=0x400100
            u.mem_write(0x2000000,scene_clip(0x2000000,width,height));u.mem_write(0x473624,struct.pack('<I',target))
            u.reg_write(UC_X86_REG_ESP,stack);calls=[]
            def api(machine,address,size,user):
                if address!=target:return
                sp=machine.reg_read(UC_X86_REG_ESP);ret,rect,left,top,right,bottom=struct.unpack('<6I',machine.mem_read(sp,24))
                calls.append((left,top,right,bottom));machine.mem_write(rect,struct.pack('<4I',left,top,right,bottom))
                machine.reg_write(UC_X86_REG_ESP,sp+24);machine.reg_write(UC_X86_REG_EIP,ret)
            u.hook_add(UC_HOOK_CODE,api);u.emu_start(0x2000000,0x41ea11,count=100)
            self.assertEqual(calls,[(0,0,width-1,height-1)])
            self.assertEqual(u.reg_read(UC_X86_REG_ESP),stack)
            self.assertEqual(struct.unpack('<I',u.mem_read(stack+0x10,4))[0],width)
            self.assertEqual(struct.unpack('<I',u.mem_read(stack+0x24,4))[0],0)

    def test_camera_centers_on_player_and_clears_both_panel_offsets(self):
        from unicorn.x86_const import UC_X86_REG_ESI,UC_X86_REG_EDI,UC_X86_REG_EBP
        for width,height in ((1365,769),(1920,900)):
            u=self.machine();owner=0x3000000
            u.mem_write(0x2000000,scene_camera(0x2000000,width,height))
            u.mem_write(owner+0xa000,struct.pack('<4I',10000,20000,320,160))
            u.reg_write(UC_X86_REG_EBP,owner);u.reg_write(UC_X86_REG_EDI,owner+0xa000);u.reg_write(UC_X86_REG_ESI,owner+0xa004)
            u.emu_start(0x2000000,0x41eac1,count=100)
            self.assertEqual(struct.unpack('<4I',u.mem_read(owner+0xa000,16)),(10000-width//2,20000-height//2,0,0))

    def test_scene_clip_retains_native_transition_only_in_the_original_modes(self):
        from unicorn import UC_HOOK_CODE
        from unicorn.x86_const import UC_X86_REG_ESP,UC_X86_REG_EIP
        for mode in (0,1,16,17):
            u=self.machine();stack=0x3001000;u.reg_write(UC_X86_REG_ESP,stack)
            u.mem_write(0x2000000,scene_clip(0x2000000,1920,900))
            u.mem_write(0x473624,struct.pack('<I',0x400100));u.mem_write(0x48d70c,struct.pack('<I',2))
            u.mem_write(stack+0x60,struct.pack('<I',mode));calls=[]
            def native(machine,address,size,user):
                if address not in (0x400100,0x44e830):return
                sp=machine.reg_read(UC_X86_REG_ESP);ret=struct.unpack('<I',machine.mem_read(sp,4))[0]
                if address==0x44e830:calls.append(address)
                machine.reg_write(UC_X86_REG_ESP,sp+(24 if address==0x400100 else 4));machine.reg_write(UC_X86_REG_EIP,ret)
            u.hook_add(UC_HOOK_CODE,native);u.emu_start(0x2000000,0x41ea11,count=200)
            self.assertEqual(len(calls),int(mode==0))
            self.assertEqual(struct.unpack('<I',u.mem_read(0x48d70c,4))[0],0 if mode==0 else 2)


if __name__=='__main__':unittest.main()
