"""Execute the beacon's actual x86 hook and the original native projection."""
import os,sys,struct,unittest
from pathlib import Path
import pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
from unicorn.x86_const import *
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from premium_beam import (make_image,make_stub,WIDTH,HEIGHT,ANCHOR_X,ANCHOR_Y,
                          FRAME_COUNT,FRAME_STRIDE,FRAME_BYTES,FRAMES,SIZE,DATA,HOOK,
                          BLUE_FRAMES,RED_FRAMES,RULE_CHECK,RULE_TABLE,RULE_BYTES,RULES,make_rule_check,GRAIL_CHECK)
from grail_policy import make_lookup,policy_image
FIX=Path(os.environ.get('SHADOWFLARE_BEAM_FIXTURE_DIR',ROOT.parent/'shadowflare-drop-analysis/beam-work'))
BASE=0x30000000;STACK=0x31008000;MANAGER=0x32000000
PACKET_FN=0x33000000;SCREEN=MANAGER+0xc000;PROJECTION=MANAGER+0xd000
PLAYER=MANAGER+0xe000;MAP=MANAGER+0x10000;ITEMS=MANAGER+0x12000

class Fixture:
    def __init__(self,items,scroll=(0,0),viewport=(0,0,1920,900),enabled=1,mode=0,magic=0,found=None,wrong_character=False):
        self.u=Uc(UC_ARCH_X86,UC_MODE_32);self.calls=[]
        for a,n in ((0x400000,0x100000),(0x10000000,0x20000),(BASE,SIZE),(0x31000000,0x10000),(MANAGER,0x200000),(PACKET_FN,0x1000)):
            self.u.mem_map(a,n)
        pe=pefile.PE(str(FIX/'RKC_RPGSCRN.dll'));self.u.mem_write(0x10000000,pe.get_memory_mapped_image())
        self.u.mem_write(BASE,make_stub(BASE,PACKET_FN,0x10001600))
        self.u.mem_write(BASE+RULE_CHECK,make_rule_check(BASE))
        self.u.mem_write(BASE+GRAIL_CHECK,make_lookup(BASE+GRAIL_CHECK,BASE+DATA+32))
        self.u.mem_write(BASE+RULE_TABLE,RULE_BYTES)
        self.put(BASE+DATA+4,enabled);self.put(0x482db0,mode)
        self.put(BASE+DATA+16,magic)
        self.put(0x48ce0c,MANAGER+0xf000);self.put(MANAGER+0xf000,1,MANAGER+0xf100,0)
        self.put(MANAGER+0xf100,PLAYER);self.put(PLAYER+0x458,MAP)
        self.put(MAP+0x4c,MANAGER+0x11000);self.put(MANAGER+0x11000,ITEMS if items else 0)
        self.put(0x482d1c,SCREEN);self.put(0x482d14,PROJECTION);self.put(0x482d10,MANAGER+0xf200)
        self.put(SCREEN+0x10,*viewport);self.put(SCREEN+0x20,7);self.put(SCREEN+0x40,*scroll)
        self.put(PROJECTION+0x18,10,5);self.put(0x48ce98,20)
        self.put(MANAGER+0xa744,1)
        for i,item in enumerate(items):
            p=ITEMS+i*0x800
            self.put(p+0xc,item.get('category',0));self.put(p+0x14,123+i,item.get('rarity',2))
            if 'id' in item:self.put(p+0x14,item['id'])
            self.put(p+0x1c,item.get('identified',0))
            for offset,value in item.get('stats',()):self.put(p+offset,value)
            self.put(p+0x48,*item.get('xy',(5000,0)))
            self.put(p+0x8c,p+0x800 if i+1<len(items) else 0)
        if found is not None:
            filename=b'Save\\0001.Ssv\0';name=b'Hero\0'
            self.put(0x482dcc,MANAGER+0x180000);self.put(MANAGER+0x180000,MANAGER+0x180100)
            self.u.mem_write(MANAGER+0x180100,filename);self.u.mem_write(PLAYER+0x10,name)
            keys=[f'{i.get("category",0)}:{i.get("id",123+n)}' for n,i in enumerate(items) if i.get('category',0)<=2 and i.get('rarity',2)==2]
            self.u.mem_write(MANAGER+0x190000,policy_image(keys,found,PLAYER,filename,name,True))
            self.put(BASE+DATA+32,MANAGER+0x190000)
            if wrong_character:self.u.mem_write(PLAYER+0x10,b'Other')
        self.u.hook_add(UC_HOOK_CODE,self.hook)
    def put(self,a,*v):self.u.mem_write(a,struct.pack('<'+'I'*len(v),*(i&0xffffffff for i in v)))
    def words(self,a,n=1):return struct.unpack('<'+'I'*n,self.u.mem_read(a,n*4))
    def hook(self,u,address,size,user):
        if address!=PACKET_FN:return
        sp=u.reg_read(UC_X86_REG_ESP);args=self.words(sp+4,18)
        self.calls.append(args)
        # Deliberately clobber caller-saved registers, as the real method may.
        for reg in (UC_X86_REG_EAX,UC_X86_REG_ECX,UC_X86_REG_EDX):u.reg_write(reg,0xdeadbeef)
        u.reg_write(UC_X86_REG_EIP,self.words(sp)[0]);u.reg_write(UC_X86_REG_ESP,sp+76)
    def run(self):
        saved={UC_X86_REG_EAX:101,UC_X86_REG_EBX:1,UC_X86_REG_ECX:303,
            UC_X86_REG_EDX:404,UC_X86_REG_ESI:505,UC_X86_REG_EDI:606,UC_X86_REG_EBP:MANAGER}
        for r,v in saved.items():self.u.reg_write(r,v)
        self.u.reg_write(UC_X86_REG_ESP,STACK);self.u.reg_write(UC_X86_REG_EFLAGS,0x202)
        self.u.emu_start(BASE,HOOK+7,count=5000000)
        assert self.u.reg_read(UC_X86_REG_EIP)==HOOK+7
        assert self.u.reg_read(UC_X86_REG_ESP)==STACK
        for r,v in saved.items():assert self.u.reg_read(r)==v,(r,v,self.u.reg_read(r))
        assert self.u.reg_read(UC_X86_REG_EFLAGS)&0x40 # original cmp [manager+a744],1
        assert self.words(BASE+DATA)[0]==0
        return self.calls

@unittest.skipUnless((FIX/'RKC_RPGSCRN.dll').exists(),'Native renderer fixture required')
class BeamNativeTests(unittest.TestCase):
    def test_hidden_magic_beacon_is_suppressed_while_premium_beacon_stays(self):
        category,ident,stats=RULES[0]
        magic=dict(category=category,id=ident,rarity=1,stats=[(offset,maximum) for offset,threshold,maximum in stats])
        f=Fixture([{},magic],magic=1)
        flag=MANAGER+0x1f000;f.put(flag,1);f.put(BASE+DATA+40,flag)
        calls=f.run();self.assertEqual(len(calls),1);self.assertEqual(f.words(BASE+DATA+28)[0],0)
    def test_only_premium_equipment_uses_native_additive_world_packet(self):
        f=Fixture([dict(rarity=0),dict(rarity=1),dict(category=3),{},dict(category=2)])
        calls=f.run();self.assertEqual(len(calls),2)
        for a in calls:
            self.assertEqual(a[:6],(1,7,0,0,0xffffffff,0x1022))
            self.assertEqual(a[6:8],(500-ANCHOR_X,250-ANCHOR_Y))
            self.assertEqual(a[8:16],(1000,1000,1000,1000,0,1000,1000,1000))
            self.assertEqual(a[16],SCREEN+0x10)
            self.assertTrue(BASE+FRAMES<=a[17]<BASE+SIZE)
            self.assertEqual((a[17]-BASE-FRAMES)%FRAME_STRIDE,0)
    def test_camera_scroll_and_native_projection_match_item_world_position(self):
        f=Fixture([dict(xy=(8000,2000))],scroll=(450,200))
        a=f.run()[0];self.assertEqual(a[6:8],(600-450-ANCHOR_X,500-200-ANCHOR_Y))
    def test_offscreen_effects_are_culled_but_edge_intersections_survive(self):
        self.assertEqual(Fixture([dict(xy=(90000,0))]).run(),[])
        self.assertEqual(len(Fixture([dict(xy=(0,0))]).run()),1)
    def test_disable_empty_map_missing_player_and_multiplayer_add_nothing(self):
        for f in (Fixture([{}],enabled=0),Fixture([]),Fixture([{}],mode=1)):
            self.assertEqual(f.run(),[])
        f=Fixture([{}]);f.put(PLAYER+0x458,0);self.assertEqual(f.run(),[])
        f=Fixture([{}]);f.put(MANAGER+0xf000+8,1);self.assertEqual(f.run(),[])
    def test_each_frame_reads_current_ground_membership_without_stale_pointers(self):
        f=Fixture([{},{}]);self.assertEqual(len(f.run()),2)
        f.calls.clear();f.put(ITEMS+0x8c,0);self.assertEqual(len(f.run()),1)
        f.calls.clear();f.put(MANAGER+0x11000,0);self.assertEqual(f.run(),[])
    def test_magic_all_133_templates_pass_at_threshold_and_remain_unidentified(self):
        items=[dict(category=c,id=i,rarity=1,stats=[(o,t) for o,t,m in stats]) for c,i,stats in RULES]
        f=Fixture(items,enabled=0,magic=1)
        before=bytes(f.u.mem_read(ITEMS,len(items)*0x800))
        calls=f.run();self.assertEqual(len(calls),len(RULES))
        self.assertEqual(f.words(BASE+DATA+28)[0],len(RULES))
        self.assertTrue(all(BASE+BLUE_FRAMES<=a[17]<BASE+RULE_TABLE for a in calls))
        self.assertEqual(bytes(f.u.mem_read(ITEMS,len(items)*0x800)),before)
    def test_each_of_512_random_bonuses_must_independently_meet_threshold(self):
        f=Fixture([],enabled=0,magic=1)
        for category,ident,stats in RULES:
            f.put(ITEMS+0xc,category);f.put(ITEMS+0x14,ident,1)
            for offset,threshold,maximum in stats:f.put(ITEMS+offset,maximum)
            for offset,threshold,maximum in stats:
                f.put(ITEMS+offset,threshold-1)
                f.put(STACK,BASE+0x700)
                f.u.reg_write(UC_X86_REG_ESP,STACK);f.u.reg_write(UC_X86_REG_ECX,ITEMS)
                f.u.emu_start(BASE+RULE_CHECK,BASE+0x700,count=10000)
                self.assertEqual(f.u.reg_read(UC_X86_REG_EAX),0,(category,ident,offset))
                f.put(ITEMS+offset,maximum)
    def test_magic_wrong_prefix_low_roll_or_uninitialized_rolls_have_no_beam(self):
        c,i,stats=next(r for r in RULES if r[:2]==(0,3000814))
        good=dict(category=c,id=i,rarity=1,stats=[(o,t) for o,t,m in stats])
        bad={**good,'stats':[(o,t-1) for o,t,m in stats]}
        unknown={**good,'id':3000813} # Spiritual is intentionally excluded
        f=Fixture([good,bad,unknown,dict(rarity=1,id=i)],magic=1)
        self.assertEqual(len(f.run()),1)
        self.assertEqual(f.words(BASE+DATA+28)[0],1)
    def test_gold_and_blue_toggles_are_independent(self):
        c,i,stats=RULES[0];magic=dict(category=c,id=i,rarity=1,stats=[(o,t) for o,t,m in stats])
        for gold,blue,expected in ((1,0,1),(0,1,1),(1,1,2),(0,0,0)):
            f=Fixture([{},magic],enabled=gold,magic=blue)
            self.assertEqual(len(f.run()),expected)
    def test_many_normal_drops_do_not_allocate_effect_packets(self):
        f=Fixture([dict(rarity=0)]*500+[{}]);self.assertEqual(len(f.run()),1)
    def test_missing_premium_uses_red_orbits_without_a_drop_event(self):
        f=Fixture([dict(id=1),dict(id=2),dict(id=1,category=1)],found=['0:1'])
        calls=f.run();starts=[a[17]-((10+[1,2,1][n])%16)*FRAME_STRIDE-BASE for n,a in enumerate(calls)]
        self.assertEqual(starts,[FRAMES,RED_FRAMES,RED_FRAMES])
        self.assertEqual(f.words(BASE+DATA+8)[0],3);self.assertEqual(f.words(BASE+DATA+36)[0],2)
        self.assertEqual(Fixture([dict(id=1)],found=[],wrong_character=True).run()[0][17],BASE+FRAMES+11*FRAME_STRIDE)

class BeamImageTests(unittest.TestCase):
    def test_generated_frames_have_valid_immutable_dib_headers(self):
        raw=make_image(BASE,PACKET_FN,0x10001600);self.assertEqual(len(raw),SIZE)
        frames=[]
        for i in range(FRAME_COUNT):
            at=FRAMES+i*FRAME_STRIDE
            self.assertEqual(struct.unpack_from('<III',raw,at),(BASE+at+16,0,BASE+at+64))
            self.assertEqual(struct.unpack_from('<IiiHH',raw,at+16),(40,WIDTH,HEIGHT,1,24))
            pixels=raw[at+64:at+64+FRAME_BYTES];frames.append(pixels)
            self.assertEqual(pixels[:3],b'\0'*3)
            self.assertGreater(max(pixels),100)
        self.assertEqual(len(set(frames)),FRAME_COUNT)

@unittest.skipUnless((FIX/'RKC_UPDIB.dll').exists() and (FIX/'RKC_DIB.dll').exists(),'Native blend fixtures required')
class BeamBlendTests(unittest.TestCase):
    def render(self,x=112,y=13,clip=(0,0,319,239),blue=False):
        u=Uc(UC_ARCH_X86,UC_MODE_32)
        for a,n in ((0x10000000,0x20000),(0x20000000,0x20000),(BASE,0x100000),(0x31000000,0x10000)):u.mem_map(a,n)
        for name,base in (('RKC_UPDIB.dll',0x10000000),('RKC_DIB.dll',0x20000000)):
            pe=pefile.PE(str(FIX/name));pe.relocate_image(base);u.mem_write(base,pe.get_memory_mapped_image())
        def put(a,*v):u.mem_write(a,struct.pack('<'+'I'*len(v),*(i&0xffffffff for i in v)))
        def call(fn,this,args):
            put(STACK,BASE+0xff000,*args);u.reg_write(UC_X86_REG_ESP,STACK);u.reg_write(UC_X86_REG_ECX,this)
            u.emu_start(fn,BASE+0xff000,count=50000000)
            self.assertEqual(u.reg_read(UC_X86_REG_EIP),BASE+0xff000)
            self.assertEqual(u.reg_read(UC_X86_REG_ESP),STACK+4+4*len(args))
        start=BLUE_FRAMES if blue else FRAMES
        frame=make_image(BASE,PACKET_FN,0x10001600)[start:start+FRAME_STRIDE]
        # Relocate just the first immutable DIB into this fixture.
        frame=bytearray(frame);struct.pack_into('<III',frame,0,BASE+0x310,0,BASE+0x340)
        u.mem_write(BASE+0x300,bytes(frame))
        put(BASE+0x20000,BASE+0x20100,0,BASE+0x21000)
        u.mem_write(BASE+0x20100,struct.pack('<IiiHHIIIIII',40,320,240,1,24,0,320*240*3,0,0,0,0))
        background=bytes((30,60,90))*320*240;u.mem_write(BASE+0x21000,background)
        put(BASE+0x200,*clip);put(0x100090f0,0x20005260)
        call(0x100034a0,BASE+0x100,[BASE,0,0,0xffffffff,0x1022,x,y,1000,1000,1000,1000,0,1000,1000,1000,BASE+0x200,BASE+0x300])
        call(0x10003550,BASE+0x100,[BASE+0x20000,0])
        return bytes(u.mem_read(BASE+0x21000,len(background)))
    def pixel(self,raw,x,y):return tuple(raw[((239-y)*320+x)*3:((239-y)*320+x)*3+3])
    def test_original_engine_adds_gold_without_a_black_background(self):
        raw=self.render()
        self.assertEqual(self.pixel(raw,0,0),(30,60,90))
        p=self.pixel(raw,160,220);self.assertGreater(p[0],30);self.assertGreater(p[1],60);self.assertEqual(p[2],255)
    def test_original_engine_renders_magic_pillar_blue(self):
        raw=self.render(blue=True)
        self.assertEqual(self.pixel(raw,0,0),(30,60,90))
        b,g,r=self.pixel(raw,160,220)
        self.assertEqual(b,255);self.assertGreater(g,60);self.assertTrue(90<r<255)
    def test_native_world_viewport_clips_the_pillar_and_halo(self):
        raw=self.render(clip=(0,0,150,239))
        self.assertEqual(self.pixel(raw,160,220),(30,60,90))
        self.assertNotEqual(self.pixel(raw,148,220),(30,60,90))
    def test_native_blitter_handles_partly_offscreen_beams(self):
        raw=self.render(x=-48,y=-50)
        self.assertNotEqual(self.pixel(raw,0,150),(30,60,90))
        self.assertEqual(self.pixel(raw,319,239),(30,60,90))

if __name__=='__main__':unittest.main()
