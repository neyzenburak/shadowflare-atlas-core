import struct,sys,unittest
from pathlib import Path
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32
from unicorn.x86_const import *
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from grail_policy import policy_image,make_lookup,HEADER,found_keys

BASE=0x31000000;POLICY=BASE+0x2000;SLOT=BASE+0x1000;ITEM=BASE+0x4000
MANAGER=BASE+0x5000;PLAYER=BASE+0x6000;FILE=BASE+0x7000;STOP=BASE+0x8000;STACK=BASE+0x9000
class PolicyFixture:
    def __init__(self,keys,found):
        self.u=Uc(UC_ARCH_X86,UC_MODE_32);self.u.mem_map(0x400000,0x100000);self.u.mem_map(BASE,0x10000)
        self.u.mem_write(BASE,make_lookup(BASE,SLOT));self.put(SLOT,POLICY)
        self.u.mem_write(POLICY,policy_image(keys,found,PLAYER,b'Save\\0001.Ssv\0',b'Hero',True))
        self.put(0x48ce0c,MANAGER);self.put(MANAGER,1,MANAGER+0x100,0);self.put(MANAGER+0x100,PLAYER)
        self.put(0x482dcc,MANAGER+0x200);self.put(MANAGER+0x200,FILE)
        self.u.mem_write(FILE,b'Save\\0001.Ssv\0');self.u.mem_write(PLAYER+0x10,b'Hero')
    def put(self,a,*v):self.u.mem_write(a,struct.pack('<'+'I'*len(v),*v))
    def call(self,cat,ident):
        self.put(ITEM+0xc,cat);self.put(ITEM+0x14,ident)
        self.put(STACK,STOP);self.u.reg_write(UC_X86_REG_ESP,STACK);self.u.reg_write(UC_X86_REG_ECX,ITEM)
        saved={UC_X86_REG_EBX:101,UC_X86_REG_ESI:202,UC_X86_REG_EDI:303,UC_X86_REG_EBP:404}
        for r,v in saved.items():self.u.reg_write(r,v)
        self.u.emu_start(BASE,STOP,count=10000)
        assert self.u.reg_read(UC_X86_REG_ESP)==STACK+4
        for r,v in saved.items():assert self.u.reg_read(r)==v
        return self.u.reg_read(UC_X86_REG_EAX)

class PolicyTests(unittest.TestCase):
    def test_binary_lookup_keeps_category_and_unsigned_full_template_id(self):
        keys=['0:1','0:2147483649','1:1','2:4294967295']
        f=PolicyFixture(keys,['1:1'])
        for n,key in enumerate(keys):
            ptr=f.call(*map(int,key.split(':')));self.assertEqual(ptr,POLICY+HEADER+n*12)
            self.assertEqual(struct.unpack('<I',f.u.mem_read(ptr+8,4))[0],int(key=='1:1'))
        for key in ((0,0),(0,2),(2,1),(3,1)):self.assertEqual(f.call(*key),0)
    def test_stale_character_save_slot_and_unavailable_table_fail_open(self):
        changes=[(SLOT,[0]),(POLICY,[0]),(POLICY+4,[PLAYER+4]),(PLAYER+0x10,[0]),
                 (FILE+4,[0]),(0x48ce0c,[0]),(MANAGER,[0]),(MANAGER+8,[1]),
                 (MANAGER+4,[0]),(MANAGER+0x100,[PLAYER+4]),(POLICY+36,[4097]),(0x482db0,[1])]
        for address,values in changes:
            with self.subTest(address=address):
                f=PolicyFixture(['0:1'],['0:1']);f.put(address,*values);self.assertEqual(f.call(0,1),0)
    def test_completed_evidence_matches_grail_ui_and_empty_table_is_safe(self):
        self.assertEqual(found_keys({'a':{'first_owned':'date'},'b':{'first_pickup':'date'},'c':{'manual':1},'d':{'manual':0}}),{'a','b','c'})
        self.assertEqual(PolicyFixture([],[]).call(0,1),0)

if __name__=='__main__':unittest.main()
