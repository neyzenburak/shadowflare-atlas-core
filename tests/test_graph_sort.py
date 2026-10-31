"""Compare optimized ordering/metadata with the original x86 DLL, not a model."""
from pathlib import Path
import itertools,random,struct,unittest,sys,os
import pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
from unicorn.x86_const import *
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from graph_sort import make_image,DATA_OFFSET

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=Path(os.environ.get('SHADOWFLARE_FIXTURE_DIR',ROOT.parent/'shadowflare-drop-analysis/resolution-fix'))/'RKC_RPGSCRN.dll'
DLL=pefile.PE(str(FIXTURE)).get_memory_mapped_image() if FIXTURE.exists() else None
ORIGINAL=0x10006d00;FAST=0x31000000;STOP=FAST+0x1000;STACK=0x32010000
LIST=0x33000000;OBJECT=LIST+0x1000;CELL=LIST+0x100000;HEAP=LIST+0x200000

def run(objects,fast=False,allocation_failure=False,repeat=1,mutate=False,metrics=False,sizes=None,reorder=None,list_keys=False,expected_allocations=None):
    object_pool=objects
    if sizes:objects=object_pool[:sizes[0]]
    u=Uc(UC_ARCH_X86,UC_MODE_32)
    for a,size in ((0,4096),(0x10000000,0x20000),(FAST,8192),(STACK-0x10000,0x20000),(LIST,0x1000000)):u.mem_map(a,size)
    u.mem_write(0x10000000,DLL);u.mem_write(FAST,make_image(FAST,STOP+0x100,STOP+0x120))
    def put(a,*v):u.mem_write(a,struct.pack('<'+'I'*len(v),*(x&0xffffffff for x in v)))
    def words(a,n=1):return struct.unpack('<'+'I'*n,u.mem_read(a,n*4))
    put(0,0xffffffff);put(LIST+4,CELL if objects else 0)
    for i,(x,y,rect,flags) in enumerate(object_pool):
        obj=OBJECT+i*0x80;cell=CELL+i*0x20
        put(obj+4,x,y);put(obj+0x28,*rect);put(obj+0x1c,flags)
        if i>=len(objects):continue
        identity=0 if reorder=='duplicate' and i+1==len(objects) else i
        put(cell,0x55,111+i,OBJECT+identity*0x80,cell-0x20 if i else 0,cell+0x20 if i+1<len(objects) else 0)
    allocations=[];frees=[];scratch=[];scratch_freed=[];scratch_cursor=[HEAP]
    def allocator(uc,a,size,user):
        sp=uc.reg_read(UC_X86_REG_ESP);arg=words(sp+4)[0]
        if a==STOP+0x100:
            n=(len(objects)+255)&~255;buckets=1<<((2*n-1).bit_length());stride=n//8
            assert words(sp+4,4)==(0,n*48+buckets*8+stride+2*n*stride,0x3000,4)
            result=0 if allocation_failure else scratch_cursor[0]
            if result:
                scratch.append(result);scratch_cursor[0]+=(words(sp+8)[0]+4095)&~4095
            uc.reg_write(UC_X86_REG_EIP,words(sp)[0]);uc.reg_write(UC_X86_REG_ESP,sp+20);uc.reg_write(UC_X86_REG_EAX,result);return
        elif a==STOP+0x120:
            pointer,zero,flag=words(sp+4,3)
            assert pointer in scratch and pointer not in scratch_freed and (zero,flag)==(0,0x8000)
            scratch_freed.append(pointer)
            uc.reg_write(UC_X86_REG_EIP,words(sp)[0]);uc.reg_write(UC_X86_REG_ESP,sp+16);uc.reg_write(UC_X86_REG_EAX,1);return
        elif a==0x100072f9:
            result=HEAP+len(allocations)*0x20;allocations.append(result);self_size=arg
            assert self_size==20
        else:result=0;frees.append(arg)
        uc.reg_write(UC_X86_REG_EIP,words(sp)[0]);uc.reg_write(UC_X86_REG_ESP,sp+4);uc.reg_write(UC_X86_REG_EAX,result)
    for a in (0x100072ee,0x100072f9,STOP+0x100,STOP+0x120):u.hook_add(UC_HOOK_CODE,allocator,begin=a,end=a)
    regs={UC_X86_REG_EBX:101,UC_X86_REG_ESI:202,UC_X86_REG_EDI:303,UC_X86_REG_EBP:404}
    for r,v in regs.items():u.reg_write(r,v)
    for frame in range(repeat):
        current_list=LIST+frame*0x100 if list_keys else LIST
        identities=list(range(len(objects)))
        if reorder=='duplicate':identities[-1]=0
        if frame:
            if sizes:objects=object_pool[:sizes[frame]]
            identities=list(range(len(objects)))
            if reorder=='shuffle':random.Random(frame+987).shuffle(identities)
            elif reorder=='rotate':identities=identities[frame:]+identities[:frame]
            elif reorder=='duplicate':identities[-1]=0
            elif reorder=='replace':
                identities[-1]=len(objects)+frame
                u.mem_write(OBJECT+identities[-1]*0x80,bytes(u.mem_read(OBJECT,0x80)))
            elif reorder=='rebuilt':
                for i in range(len(objects)):
                    identities[i]=frame*512+i
                    u.mem_write(OBJECT+identities[i]*0x80,bytes(u.mem_read(OBJECT+i*0x80,0x80)))
            elif reorder=='window':identities=list(range((frame%4)*13,(frame%4)*13+len(objects)))
            # Fresh display cells, preserving input order, as the engine does
            # when render generations change. Cached pointers must be replaced.
            cells=LIST+0x800000+0x20000*frame
            put(current_list+4,cells if objects else 0)
            for i in range(len(objects)):
                cell=cells+i*0x20
                put(cell,0x55,111+i,OBJECT+identities[i]*0x80,cell-0x20 if i else 0,cell+0x20 if i+1<len(objects) else 0)
            if mutate=='random':
                rng=random.Random(frame+131)
                for _ in range(5):
                    obj=OBJECT+rng.randrange(len(objects))*0x80
                    put(obj+4,rng.randrange(-300,301),rng.randrange(-300,301))
                    put(obj+0x1c,rng.randrange(512))
                    put(obj+0x28,*(rng.randrange(-80,81) for _ in range(4)))
            elif mutate:
                put(OBJECT+4,7777+frame,-3333-frame)
                put(OBJECT+0x1c,0x20 if frame%2 else 0)
        put(STACK,STOP);u.reg_write(UC_X86_REG_ESP,STACK);u.reg_write(UC_X86_REG_ECX,current_list)
        u.emu_start(FAST if fast else ORIGINAL,STOP,count=2000000000)
    assert u.reg_read(UC_X86_REG_EIP)==STOP
    assert u.reg_read(UC_X86_REG_ESP)==STACK+4
    assert u.reg_read(UC_X86_REG_EAX)==1
    for r,v in regs.items():assert u.reg_read(r)==v
    out=[];cell=words(current_list+4)[0];prev=0
    while cell:
        flag,trans,obj,left,right=words(cell,5)
        assert left==prev and len(out)<len(objects)
        out.append(((obj-OBJECT)//0x80,flag&0xffff,trans));prev=cell;cell=right
    assert len(out)==len(objects)
    assert sorted(q[0] for q in out)==sorted(identities)
    if fast:
        assert not allocations and not frees
        assert words(FAST+DATA_OFFSET,2)==(0,repeat)
        assert all(pointer in scratch for pointer in scratch_freed)
        assert len(scratch_freed)==len(set(scratch_freed)) # each replaced buffer freed once
        assert bool(scratch)==(len(objects)>=32 and not allocation_failure)
        assert len(scratch)<=repeat
        if expected_allocations is not None:assert len(scratch)==expected_allocations
        assert words(FAST+0x600)[0]==0
    if metrics=='details':return out,words(FAST+0x608,6)
    if metrics:return out,words(FAST+0x608,2)
    return out

@unittest.skipIf(DLL is None,'Set SHADOWFLARE_FIXTURE_DIR to the local original DLL directory')
class RenderSortTests(unittest.TestCase):
    def compare(self,objects):self.assertEqual(run(objects,True),run(objects,False))
    def test_empty_singleton_and_metadata(self):
        for n in (0,1,2):self.compare([(i*10,i*10,(-10,-10,10,10),0) for i in range(n)])
    def test_all_flag_priorities_and_ties(self):
        for flags in itertools.permutations((0,0x100,0x80,0x20)):
            self.compare([(0,0,(-10,-10,10,10),f) for f in flags]*10)
    def test_adversarial_geometry_and_signed_overflow(self):
        for seed in range(60):
            rng=random.Random(seed)
            objects=[]
            for i in range(rng.randrange(2,45)):
                rect=tuple(rng.randrange(-120,121) for _ in range(4))
                objects.append((rng.choice([-2147483648,2147483647,rng.randrange(-200,201)]),rng.randrange(-200,201),rect,rng.randrange(512)))
            self.compare(objects)
    def test_dense_equal_and_reverse_depth_orders(self):
        for n in (60,120):
            self.compare([(0,0,(-10,-10,10,10),0)]*n)
            self.compare([(i*3,i*4,(-10,-10,10,10),0) for i in reversed(range(n))])
    def test_large_list_has_no_capacity_limit(self):
        out=run([(0,0,(-10,-10,10,10),0)]*5000,True)
        self.assertEqual([q[0] for q in out],list(range(5000)))
    def test_allocation_failure_falls_back_without_losing_items(self):
        objects=[(i*3,i*4,(-10,-10,10,10),0) for i in reversed(range(80))]
        self.assertEqual(run(objects,True,allocation_failure=True),run(objects,False))
    def test_exact_cache_reuses_order_with_new_render_cells(self):
        rng=random.Random(57)
        objects=[(rng.randrange(-200,201),rng.randrange(-200,201),(-40,-40,40,40),rng.randrange(512)) for _ in range(80)]
        out,counts=run(objects,True,repeat=3,metrics=True)
        self.assertEqual(out,run(objects,False,repeat=3))
        self.assertEqual(counts,(2,1))
    def test_changed_metadata_rebuilds_cache(self):
        objects=[(i*3,i*4,(-10,-10,10,10),0) for i in range(80)]
        out,counts=run(objects,True,repeat=3,mutate=True,metrics=True)
        self.assertEqual(out,run(objects,False,repeat=3,mutate=True))
        self.assertEqual(counts,(1,2)) # metadata change with unchanged edges can reuse exact order
    def test_incremental_graph_matches_native_across_geometry_changes(self):
        rng=random.Random(97)
        objects=[(rng.randrange(-200,201),rng.randrange(-200,201),(-40,-40,40,40),rng.randrange(512)) for _ in range(80)]
        self.assertEqual(run(objects,True,repeat=12,mutate='random'),run(objects,False,repeat=12,mutate='random'))
    def test_picking_items_resizes_and_releases_previous_buffers(self):
        objects=[(i*3,i*4,(-10,-10,10,10),0) for i in range(80)]
        self.assertEqual(run(objects,True,repeat=3,sizes=[80,40,35]),run(objects,False,repeat=3,sizes=[80,40,35]))
    def test_input_reordering_preserves_native_ties_and_moved_cell_properties(self):
        rng=random.Random(317)
        for objects in ([(0,0,(-10,-10,10,10),0)]*80,[(rng.randrange(-200,201),rng.randrange(-200,201),(-40,-40,40,40),rng.randrange(512)) for _ in range(80)]):
            for reorder in ('rotate','shuffle'):
                self.assertEqual(run(objects,True,repeat=5,reorder=reorder),run(objects,False,repeat=5,reorder=reorder))
    def test_same_count_replacement_rebuilds_membership_without_stale_pointers(self):
        objects=[(i*3,i*4,(-10,-10,10,10),0) for i in range(80)]
        self.assertEqual(run(objects,True,repeat=4,reorder='replace'),run(objects,False,repeat=4,reorder='replace'))
    def test_duplicate_objects_preserve_all_native_cells(self):
        objects=[(i*3,i*4,(-10,-10,10,10),0) for i in range(80)]
        self.assertEqual(run(objects,True,repeat=3,reorder='duplicate'),run(objects,False,repeat=3,reorder='duplicate'))
    def test_reordering_static_objects_does_not_recompute_their_geometry(self):
        objects=[(i*3,i*4,(-10,-10,10,10),0) for i in range(80)]
        out,stats=run(objects,True,repeat=5,reorder='shuffle',metrics='details')
        self.assertEqual(out,run(objects,False,repeat=5,reorder='shuffle'))
        self.assertEqual(stats[2:],(0,1,5,0)) # unchanged geometry, one membership build, changed input order
    def test_rebuilt_native_objects_keep_exact_geometry_cache(self):
        objects=[(i*3,i*4,(-10,-10,10,10),0) for i in range(80)]
        out,stats=run(objects,True,repeat=4,reorder='rebuilt',metrics='details')
        self.assertEqual(out,run(objects,False,repeat=4,reorder='rebuilt'))
        self.assertEqual(stats[:4],(3,1,0,1))
    def test_revisiting_list_sizes_reuses_their_exact_cache(self):
        objects=[(i*3,i*4,(-10,-10,10,10),0) for i in range(80)]
        out,stats=run(objects,True,repeat=4,sizes=[80,40,80,40],metrics='details',expected_allocations=1)
        self.assertEqual(out,run(objects,False,repeat=4,sizes=[80,40,80,40]))
        self.assertEqual(stats[:2],(0,4)) # active membership changes; the same allocation is retained
    def test_cache_eviction_releases_old_buffers_once(self):
        objects=[(i*3,i*4,(-10,-10,10,10),0) for i in range(80)]
        sizes=list(range(80,70,-1))
        self.assertEqual(run(objects,True,repeat=10,sizes=sizes,list_keys=True),run(objects,False,repeat=10,sizes=sizes,list_keys=True))
    def test_geometry_hash_collisions_still_compare_every_exact_value(self):
        # R=200,B=200 and R=201,B=72 collide in the rotate/xor hash.
        # Their exact tuples and their ordering relationships remain distinct.
        objects=[(0,0,rect,0) for rect in ((0,0,200,200),(0,0,201,72),(0,0,200,100))]*30
        self.assertEqual(run(objects,True,repeat=4,reorder='shuffle'),run(objects,False,repeat=4,reorder='shuffle'))
    def test_walking_visibility_changes_keep_inactive_geometry_out_of_ordering(self):
        rng=random.Random(837)
        objects=[(rng.randrange(-200,201),rng.randrange(-200,201),(-40,-40,40,40),rng.randrange(512)) for _ in range(300)]
        sizes=[80,70,90,60,100,75,95,80]
        out,stats=run(objects,True,repeat=8,sizes=sizes,reorder='window',metrics='details',expected_allocations=1)
        self.assertEqual(out,run(objects,False,repeat=8,sizes=sizes,reorder='window'))
        self.assertEqual(stats[3],1)
    def test_capacity_grows_for_more_objects_and_stays_allocated_when_view_shrinks(self):
        objects=[(i*3,i*4,(-10,-10,10,10),i%4*0x20) for i in range(300)]
        sizes=[80,260,100,280,40,300]
        self.assertEqual(run(objects,True,repeat=6,sizes=sizes,expected_allocations=2),run(objects,False,repeat=6,sizes=sizes))

if __name__=='__main__':unittest.main()
