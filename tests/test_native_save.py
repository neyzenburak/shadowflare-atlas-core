"""The save request runs once on the local player's update, then restores it."""
import hashlib
from pathlib import Path
import struct
import sys
import unittest

from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
from unicorn.x86_const import *
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from native_save import make_stub,SAVE,SAVE_END,SAVE_SHA
from live_drop import HOOK,ORIGINAL,GAME_MODE

BASE=0x30000000;DATA=BASE+0xc00;PLAYER=BASE+0x20000;STACK=BASE+0x18000


class NativeSaveTests(unittest.TestCase):
    def run_request(self,mode=0,other=False,map_changed=False):
        u=Uc(UC_ARCH_X86,UC_MODE_32);u.mem_map(0x400000,0x100000);u.mem_map(BASE,0x30000)
        def put(a,*v):u.mem_write(a,struct.pack('<'+'I'*len(v),*v))
        def word(a):return struct.unpack('<I',u.mem_read(a,4))[0]
        put(DATA,1,PLAYER,12345,0,0,0,0,0);put(GAME_MODE,mode)
        put(PLAYER+0x458,12346 if map_changed else 12345);put(PLAYER+0x34,42)
        u.mem_write(BASE,make_stub(BASE,DATA));calls=[]
        def save(u,a,size,user):
            calls.append(u.reg_read(UC_X86_REG_ECX));sp=u.reg_read(UC_X86_REG_ESP)
            u.reg_write(UC_X86_REG_EAX,1);u.reg_write(UC_X86_REG_EDX,0xfedcba98)
            u.reg_write(UC_X86_REG_ESP,sp+4);u.reg_write(UC_X86_REG_EIP,word(sp))
        u.hook_add(UC_HOOK_CODE,save,begin=SAVE,end=SAVE)
        for unused in range(3):
            regs={UC_X86_REG_EAX:11,UC_X86_REG_EBX:22,UC_X86_REG_ECX:PLAYER+100 if other else PLAYER,
                  UC_X86_REG_EDX:44,UC_X86_REG_ESI:55,UC_X86_REG_EDI:66,UC_X86_REG_EBP:77}
            for r,v in regs.items():u.reg_write(r,v)
            u.reg_write(UC_X86_REG_ESP,STACK);u.emu_start(BASE,HOOK+len(ORIGINAL),count=10000)
            self.assertEqual(u.reg_read(UC_X86_REG_ESP),STACK-20)
            for r,v in regs.items():self.assertEqual(u.reg_read(r),v)
        return calls,[word(DATA+i*4) for i in range(8)]
    def test_saves_once_with_exact_player_and_preserves_native_caller(self):
        calls,status=self.run_request()
        self.assertEqual(calls,[PLAYER]);self.assertEqual((status[0],status[3],status[4]),(3,1,42))
    def test_other_players_network_mode_and_changed_maps_cannot_save(self):
        for args in ({'other':True},{'mode':1},{'map_changed':True}):
            calls,status=self.run_request(**args);self.assertEqual(calls,[])
            self.assertEqual(status[0],1 if args.get('other') else 4)
    def test_save_fingerprint_covers_the_whole_original_writer(self):
        fixture=Path(__file__).resolve().parents[2]/'shadowflare-drop-analysis/input/ShadowFlare.exe'
        if not fixture.exists():self.skipTest('Original native EXE fixture required')
        import pefile
        raw=pefile.PE(str(fixture)).get_memory_mapped_image()
        self.assertEqual(hashlib.sha256(raw[SAVE-0x400000:SAVE_END-0x400000]).hexdigest(),SAVE_SHA)


if __name__=='__main__':unittest.main()
