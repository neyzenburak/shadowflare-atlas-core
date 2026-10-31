import os,sys,struct,unittest
from pathlib import Path
import pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
from unicorn.x86_const import *
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from render_index import make_stub,CALLERS,BLOCK_CALLERS,make_block_stub
FIXTURE=Path(os.environ.get('SHADOWFLARE_FIXTURE_DIR',ROOT.parent/'shadowflare-drop-analysis/resolution-fix'))/'RKC_RPGSCRN.dll'
DLL=pefile.PE(str(FIXTURE)).get_memory_mapped_image() if FIXTURE.exists() else None
BASE=0x3100000;DATA=BASE+0x300;CACHE=BASE+0x700;STACK=0x320f0000;LIST=0x3300000;CELL=LIST+0x1000;NATIVE=0x10006a00

@unittest.skipIf(DLL is None,'Local original DLL fixture required')
class IndexTests(unittest.TestCase):
    callers=CALLERS
    native=NATIVE
    next_offset=16
    stride=32
    factory=staticmethod(make_stub)
    def run_case(self,requests,mutations=None):
        u=Uc(UC_ARCH_X86,UC_MODE_32)
        for a,size in ((0x400000,0x100000),(0x10000000,0x20000),(BASE,4096),(STACK-0x10000,0x20000),(LIST,0x100000)):u.mem_map(a,size)
        u.mem_write(0x10000000,DLL);u.mem_write(BASE,self.factory(BASE,self.native,DATA,CACHE))
        def put(a,*v):u.mem_write(a,struct.pack('<'+'I'*len(v),*(x&0xffffffff for x in v)))
        def words(a,n=1):return struct.unpack('<'+'I'*n,u.mem_read(a,n*4))
        for list_index in range(2):
            put(LIST+list_index*0x100+4,CELL+list_index*0x60000)
            for i in range(5000):put(CELL+list_index*0x60000+i*self.stride+self.next_offset,CELL+list_index*0x60000+(i+1)*self.stride if i<4999 else 0)
        counts=[0]
        u.hook_add(UC_HOOK_CODE,lambda *a:counts.__setitem__(0,counts[0]+1),begin=self.native,end=self.native)
        regs={UC_X86_REG_EBX:101,UC_X86_REG_ESI:202,UC_X86_REG_EDI:303,UC_X86_REG_EBP:404}
        expected_orders=[list(range(5000)),list(range(5000))]
        for request_index,(caller,index,generation,which) in enumerate(requests):
            if mutations and request_index in mutations:
                expected_orders[which]=mutations[request_index]
                order=expected_orders[which];start=CELL+which*0x60000
                put(LIST+which*0x100+4,start+order[0]*self.stride if order else 0)
                for j,item in enumerate(order):put(start+item*self.stride+self.next_offset,start+order[j+1]*self.stride if j+1<len(order) else 0)
            put(DATA+4,generation)
            for r,v in regs.items():u.reg_write(r,v)
            put(STACK,caller,index);u.reg_write(UC_X86_REG_ESP,STACK);u.reg_write(UC_X86_REG_ECX,LIST+which*0x100)
            u.emu_start(BASE,caller,count=1000000)
            got=u.reg_read(UC_X86_REG_EAX)
            order=expected_orders[which]
            self.assertEqual(got,CELL+which*0x60000+order[index]*self.stride if 0<=index<len(order) else 0)
            self.assertEqual(u.reg_read(UC_X86_REG_ESP),STACK+8)
            self.assertEqual(words(DATA)[0],0)
            for r,v in regs.items():self.assertEqual(u.reg_read(r),v)
        return counts[0]
    def test_five_thousand_objects_keep_exact_native_lookup_results(self):
        self.assertEqual(self.run_case([(self.callers[0],i,1,0) for i in range(5000)]),1)
    def test_nonsequential_and_foreign_calls_keep_native_path(self):
        self.assertEqual(self.run_case([(0x404000,i,1,0) for i in (0,1,2)]),3)
        self.assertEqual(self.run_case([(self.callers[0],i,1,0) for i in (10,2,90,-1,5000)]),5)
    def test_generation_and_list_changes_invalidate_cached_links(self):
        self.assertEqual(self.run_case([(self.callers[0],0,1,0),(self.callers[0],1,2,0),(self.callers[0],2,2,1)]),3)
    def test_callers_have_independent_cursors(self):
        self.assertEqual(self.run_case([(c,i,1,0) for i in range(100) for c in self.callers]),len(self.callers))
    def test_new_loop_refreshes_changed_links_with_same_head_and_generation(self):
        requests=[(self.callers[0],i,1,0) for _ in range(2) for i in range(100)]
        self.assertEqual(self.run_case(requests,{100:[0]+list(range(4999,0,-1))}),2)
    def test_empty_then_refilled_list_does_not_reuse_old_objects(self):
        requests=[(self.callers[0],i,1,0) for i in (0,1,0,0,1)]
        self.assertEqual(self.run_case(requests,{2:[],3:list(range(4999,0,-1))}),3)

class BlockIndexTests(IndexTests):
    callers=BLOCK_CALLERS
    native=0x10005990
    next_offset=0x3c
    stride=64
    factory=staticmethod(make_block_stub)
    def test_original_highlight_loop_keeps_rgb_updates_and_object_links(self):
        executable=FIXTURE.parent/'ShadowFlare.exe'
        if not executable.exists():self.skipTest('Local original EXE fixture required')
        image=pefile.PE(str(executable)).get_memory_mapped_image()
        def run(optimized,target):
            u=Uc(UC_ARCH_X86,UC_MODE_32)
            for a,size in ((0x400000,0x100000),(0x10000000,0x20000),(BASE,4096),(STACK-0x10000,0x20000),(LIST,0x100000)):u.mem_map(a,size)
            u.mem_write(0x400000,image);u.mem_write(0x10000000,DLL)
            def put(a,*v):u.mem_write(a,struct.pack('<'+'I'*len(v),*v))
            imports={0x473444:0x59e0,0x473318:0x5990,0x47345c:0x4c40,
                     0x473440:0x5450,0x473334:0x5460,0x473338:0x5470,
                     0x473448:0x5550,0x473450:0x5560,0x473418:0x5570}
            for address,offset in imports.items():put(address,0x10000000+offset)
            if optimized:
                u.mem_write(BASE,make_block_stub(BASE,self.native,DATA,CACHE));put(0x473318,BASE)
            screen=LIST+0xe0000;put(0x482d1c,screen);put(screen+0x38,LIST);put(LIST+4,CELL)
            count=512
            for i in range(count):
                p=CELL+i*64;put(p+0xc,i%3);put(p+0x38,p-64 if i else 0,p+64 if i+1<count else 0)
                u.mem_write(p+0x20,struct.pack('<hhh',32700-i,-32700+i,i-100))
            put(STACK+0x24,target);u.reg_write(UC_X86_REG_ESP,STACK)
            u.emu_start(0x40f841,0x40f8ed,count=10000000)
            registers=tuple(u.reg_read(r) for r in (UC_X86_REG_EAX,UC_X86_REG_EBX,UC_X86_REG_ECX,UC_X86_REG_EDX,UC_X86_REG_ESI,UC_X86_REG_EDI,UC_X86_REG_EBP,UC_X86_REG_ESP,UC_X86_REG_EFLAGS))
            return bytes(u.mem_read(CELL,count*64)),registers
        for target in (0,1,7):self.assertEqual(run(False,target),run(True,target))

if __name__=='__main__':unittest.main()
