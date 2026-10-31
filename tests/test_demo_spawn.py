"""Execute the explicit high-roll demo on a newly allocated native item only."""
import struct,sys,unittest
from pathlib import Path
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_ESP,UC_X86_REG_ECX,UC_X86_REG_EAX,UC_X86_REG_EIP
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from live_drop import make_stub,maximum_roll_fields,CREATE_ITEM,SET_POSITION,DROP_ITEM,HOOK


class DemoSpawnTests(unittest.TestCase):
    def test_only_new_magic_bonuses_change_and_item_stays_unidentified(self):
        base=0x30000000;data=base+0xc00;stack=base+0x10000;player=base+0x20000;item=base+0x24000
        u=Uc(UC_ARCH_X86,UC_MODE_32);u.mem_map(0x400000,0x100000);u.mem_map(base,0x30000)
        def put(a,*values):u.mem_write(a,struct.pack('<'+'I'*len(values),*values))
        def word(a):return struct.unpack('<I',u.mem_read(a,4))[0]
        put(data,1,player,player+0x10000,0,0,0,0,0)
        put(player+0x458,player+0x10000);put(player+0x1a4,100);put(player+0x2e0,10000,20000)
        put(0x48ce14,1);put(item+0x18,1);put(item+0x1c,0);put(item+0x1d4,1)
        u.mem_write(base,make_stub(base,data,0,72,maximum_roll=True))
        def hook(u,a,size,user):
            if a not in (CREATE_ITEM,SET_POSITION,DROP_ITEM):return
            sp=u.reg_read(UC_X86_REG_ESP);ret=word(sp)
            n={CREATE_ITEM:12,SET_POSITION:8,DROP_ITEM:12}[a]
            if a==SET_POSITION:put(item+0x48,word(sp+4),word(sp+8))
            u.reg_write(UC_X86_REG_EAX,item if a==CREATE_ITEM else 1)
            u.reg_write(UC_X86_REG_ESP,sp+4+n);u.reg_write(UC_X86_REG_EIP,ret)
        u.hook_add(UC_HOOK_CODE,hook);u.reg_write(UC_X86_REG_ESP,stack);u.reg_write(UC_X86_REG_ECX,player)
        u.emu_start(base,HOOK+6,count=10000)
        self.assertEqual(word(data),3)
        self.assertEqual([word(item+o) for o,v in maximum_roll_fields(0,72,True)],[40,80,70])
        self.assertEqual((word(item+0x1c),word(item+0x1d4)),(0,1))
        self.assertEqual((word(item+0x48),word(item+0x4c)),(10200,20000))

    def test_demo_rejects_other_templates_and_invalid_flag(self):
        for category,ident,enabled in ((0,0,True),(4,0,True),(0,72,'yes')):
            with self.assertRaises(ValueError):maximum_roll_fields(category,ident,enabled)
        self.assertEqual(maximum_roll_fields(0,0,False),())


if __name__=='__main__':unittest.main()
