"""Execute the passive update and one-shot factory ABI before live injection."""
import copy
import hashlib
from pathlib import Path
import struct
import sys
import unittest

from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
from unicorn.x86_const import *
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
import mob_spawn as m
try:
    import pefile
    fixture=ROOT.parent/'shadowflare-drop-analysis/resolution-fix/ShadowFlare.exe'
    IMAGE=pefile.PE(str(fixture)).get_memory_mapped_image() if fixture.exists() else None
except ImportError:IMAGE=None

BASE=0x30000000;BEHAVIOR=BASE+0x10000;STACK=BASE+0x20000
PLAYER=BASE+0x30000;MAP=PLAYER+0x1000;MANAGER=MAP+0x1000
RESOURCE=MANAGER+0x1000;NODE=RESOURCE+0x1000;ENEMY=NODE+0x1000
LIST=ENEMY+0x1000;STOP=BASE+0x4ff00;D=BASE+m.DATA


class Machine:
    def __init__(self,parts=0,quantity=1,height=0):
        self.u=Uc(UC_ARCH_X86,UC_MODE_32)
        self.u.mem_map(0x400000,0x100000);self.u.mem_map(BASE,0x400000)
        self.u.mem_write(BASE,m.make_request(BASE,BEHAVIOR,17,parts,height=height,quantity=quantity))
        self.u.mem_write(BASE+m.FLAGS,m.insert_flag(BASE+m.FLAGS))
        self.u.mem_write(BEHAVIOR,m.passive_image(BEHAVIOR))
        self.put(D,1,PLAYER,MAP,0,0,0,0,0,0xe0e0e0,1,0,0)
        self.put(PLAYER+0x458,MAP);self.put(PLAYER+0x1a4,100)
        self.put(PLAYER+0x2e0,1000,2000)
        self.put(MAP+0x30,MANAGER);self.put(MAP+0x3c,MAP+0x300)
        self.put(MAP+0x58,MAP+0x400)
        self.put(0x47305c,BASE+0x4f040);self.put(0x473058,BASE+0x4f080)
        self.heap=BASE+0x40000
        self.put(MAP+0x14,40000000)
        self.put(BASE+m.CANDIDATES,400,0)
        self.put(BASE+m.RECT,-80,-80,79,79)
        config=[0]*72;config[4]=config[8]=150;config[47]=1
        self.u.mem_write(BASE+m.CONFIG,struct.pack('<72i',*config))
        self.u.mem_write(BASE+m.NAME,b'Red Goblin\0')
        self.put(0x48ce18,LIST);self.put(0x473468,BASE+0x4f000)
        self.put(0x48ce08,RESOURCE+0x100)
        self.put(RESOURCE+0xc,1);self.put(NODE,2,m.TYPE,ENEMY,0)
        self.put(ENEMY,0x476d98);self.put(ENEMY+0xd4,150)
        self.calls=[];self.blocked=False;self.collides=False;self.occupied=set()
        self.created=[];self.enemy=ENEMY;self.quantity=quantity
        self.init_valid=True
        for a in (BASE+0x4f000,BASE+0x4f040,BASE+0x4f080,BASE+m.GROUND,0x4145b0,0x455ee0,0x456080,
                  0x4299e0,0x4298c0,0x453aa0,0x458f40,0x454130,0x429be0,
                  0x458f70,BEHAVIOR+m.IDLE,0x459f60,m.HOOK+6):
            self.u.hook_add(UC_HOOK_CODE,self.hook,begin=a,end=a)
        if quantity>1:self.u.hook_add(UC_HOOK_CODE,self.hook,begin=BASE+m.FLAGS,end=BASE+m.FLAGS)
    def put(self,a,*v):self.u.mem_write(a,struct.pack('<'+'I'*len(v),*(i&0xffffffff for i in v)))
    def words(self,a,n=1):return struct.unpack('<'+'I'*n,self.u.mem_read(a,n*4))
    def ret(self,value=1,nargs=0):
        sp=self.u.reg_read(UC_X86_REG_ESP);ret=self.words(sp)[0]
        self.u.reg_write(UC_X86_REG_EAX,value);self.u.reg_write(UC_X86_REG_ESP,sp+4+nargs*4)
        self.u.reg_write(UC_X86_REG_EIP,ret)
    def hook(self,u,a,size,user):
        sp=u.reg_read(UC_X86_REG_ESP);ecx=u.reg_read(UC_X86_REG_ECX)
        if a==m.HOOK+6:u.emu_stop();return
        self.calls.append(a)
        if a==BASE+0x4f000:self.ret(LIST,1)
        elif a==BASE+m.FLAGS:self.ret(1)
        elif a==BASE+0x4f040:
            flags,size=self.words(sp+4,2);assert flags==0x40
            pointer=self.heap;self.heap+=(size+15)//16*16;self.ret(pointer,2)
        elif a==BASE+0x4f080:self.ret(0,1)
        elif a==BASE+m.GROUND:self.ret(int(not self.blocked))
        elif a==0x4145b0:
            assert self.words(sp+4,7)==(MAP,0xffffffff,D+16,BASE+m.RECT,0,0,0)
            self.ret(int(not self.collides),7)
        elif a==0x455ee0:
            assert self.words(sp+4,2)==(2,17);self.ret(RESOURCE,2)
        elif a==0x456080:
            assert ecx==RESOURCE;self.put(RESOURCE+4,1);self.ret(1,1)
        elif a==0x4299e0:
            assert ecx==MANAGER;self.ret(NODE if self.words(sp+4)[0] in self.occupied else 0,1)
        elif a==0x4298c0:
            args=self.words(sp+4,2);assert args[0]==m.TYPE
            self.enemy=ENEMY if not self.created else BASE+0x100000+len(self.created)*0x400
            self.created.append(self.enemy);self.occupied.add(args[1])
            self.put(NODE+8,self.enemy);self.put(self.enemy+4,args[1]);self.ret(NODE,2)
        elif a==0x453aa0:
            args=self.words(sp+4,8)
            assert ecx==self.enemy
            assert args==(MAP,self.words(D+24)[0],m.TYPE,D+16,BASE+m.RECT,0,0,17)
            self.put(self.enemy+0x18,*self.words(D+16,2))
            for offset in (0x14,0x38,0x3c,0x40,0x44,0x48,0x58):
                self.put(self.enemy+offset,1 if self.init_valid else 0)
            if self.init_valid:
                self.put(self.enemy+0x38,2)
                for i,offset in enumerate((0x3c,0x40,0x44,0x48)):
                    self.put(self.enemy+offset,LIST+0x400+i*0x100)
            self.ret(1,8)
        elif a==0x458f40:
            pointer=self.words(sp+4)[0]
            self.u.mem_write(self.enemy+0xc4,bytes(self.u.mem_read(pointer,288)));self.ret(1,1)
        elif a==0x454130:self.ret(1,1)
        elif a==0x429be0:self.ret(1,1)
        elif a==BEHAVIOR+m.IDLE:
            assert ecx==ENEMY;self.ret(0)
        elif a==0x459f60:
            assert ecx==ENEMY;self.ret(0)
        elif a==0x458f70:
            assert ecx==ENEMY;self.ret(77)
    def run(self,entry=BASE,player=PLAYER):
        self.put(STACK,STOP)
        regs={UC_X86_REG_EBX:111,UC_X86_REG_ESI:222,UC_X86_REG_EDI:333,UC_X86_REG_EBP:444}
        for r,v in regs.items():self.u.reg_write(r,v)
        self.u.reg_write(UC_X86_REG_ESP,STACK);self.u.reg_write(UC_X86_REG_ECX,player)
        self.u.emu_start(entry,STOP,count=3000000)
        for r,v in regs.items():assert self.u.reg_read(r)==v
        # Hook exit replays the original six-byte function prologue.
        assert self.u.reg_read(UC_X86_REG_ESP)==(STACK-20 if entry==BASE else STACK+4)


class MobSpawnTests(unittest.TestCase):
    @unittest.skipUnless(IMAGE,'Original game executable fixture required')
    def test_plan_matches_original_code_and_native_config_converter(self):
        for f in m.PLAN['verified']:
            raw=IMAGE[f['address']-0x400000:f['address']-0x400000+f['size']]
            self.assertEqual(hashlib.sha256(raw).hexdigest(),f['sha256'])
        u=Uc(UC_ARCH_X86,UC_MODE_32);u.mem_map(0x400000,0x100000);u.mem_map(BASE,0x50000)
        u.mem_write(0x400000,IMAGE)
        # Exercise the original scenario loader's stat conversion with distinct
        # values in every source field, rather than restating our mapping.
        values=tuple(range(100,179));u.mem_write(STACK+0x3b4,struct.pack('<79i',*values))
        u.reg_write(UC_X86_REG_ESP,STACK)
        u.mem_write(0x428eef,bytes.fromhex('b8 00 00 00 00 90'))
        u.mem_write(0x428efc,bytes.fromhex('83 c4 08 31 c0 90'))
        u.emu_start(0x428c95,0x428f19,count=10000)
        self.assertEqual(bytes(u.mem_read(STACK+0x294,288)),m.native_config(values))
    def test_source_record_carries_visual_tint_but_not_script_flags(self):
        values=tuple(range(79));payload=struct.pack('<79i',*values)
        record=(struct.pack('<3i',12,17,3)+b'Bob'+struct.pack('<i',0xe0c080)
                +struct.pack('<7i',555,100,200,-80,-80,79,79)
                +struct.pack('<3i',5,2,123)+struct.pack('<i',456)+struct.pack('<2i',0,1)+payload)
        raw=b'MCED DATA v0000\0'+record
        sample=dict(file_offset=16,identifier=12,pattern=17,values=list(values))
        r=m.source_record(raw,sample)
        self.assertEqual(r['tint'],0xe0c080)
        self.assertEqual(r['rect'],(-80,-80,79,79))
        for broken in (raw[:-1],raw[:16]+b'\0'*len(record)):
            with self.assertRaises(ValueError):m.source_record(broken,sample)
        wrong=copy.deepcopy(sample);wrong['values'][3]=999
        with self.assertRaises(ValueError):m.source_record(raw,wrong)
    def test_native_factory_arguments_placement_config_and_instance_only_vtable(self):
        f=Machine();f.run()
        self.assertEqual(f.words(D)[0],3)
        self.assertEqual(f.words(ENEMY)[0],BEHAVIOR+m.VTABLE)
        self.assertEqual(f.words(ENEMY+0x18,2),(1400,2000))
        self.assertEqual(f.words(ENEMY+0xd4)[0],150)
        self.assertEqual(f.words(ENEMY+0x180)[0],1)
        self.assertEqual(f.words(0x476d98,10),(0,)*10) # original table untouched
        self.assertEqual(f.words(MAP+0x14)[0],40000001)
    def test_existing_identifier_is_skipped(self):
        f=Machine();f.occupied={40000000,40000001};f.run()
        self.assertEqual(f.words(ENEMY+4)[0],40000002)
        self.assertEqual(f.words(MAP+0x14)[0],40000003)
    def test_spawn_registers_interaction_flags_and_enemy_life_preserving_quest_progress(self):
        f=Machine();control=MAP+0x400
        f.put(control+0x18,2,LIST+0x100)
        f.put(LIST+0x100,50000001,37,99,250000001,63,88)
        f.put(control+8,1,LIST+0x200);f.put(LIST+0x200,14000100,0,55)
        f.run()
        count,pointer=f.words(control+0x18,2)
        rows=[f.words(pointer+i*12,3) for i in range(count)]
        self.assertEqual(rows,[(50000001,37,99),(140000000,1,0),(240000000,1,0),
                               (250000001,63,88),(340000000,1,0)])
        count,pointer=f.words(control+8,2)
        self.assertEqual(count,2)
        self.assertEqual(f.words(pointer,6),(14000100,0,55,40000000,1,0))
    def test_model_part_visibility_and_colors_use_native_count_and_source_array_stride(self):
        f=Machine(parts=256)
        raw=(struct.pack('<256I',*([1,0]+[1]*254))
             +struct.pack('<256H',*([1000,700]+[1000]*254))
             +struct.pack('<256H',*([350,650]+[1000]*254))
             +struct.pack('<256H',*([100,600]+[1000]*254)))
        f.u.mem_write(BASE+m.ANIMATION,raw);f.run()
        self.assertEqual(f.words(D)[0],3)
        self.assertEqual(f.words(LIST+0x400,2),(1,0))
        self.assertEqual(bytes(f.u.mem_read(LIST+0x500,4)),struct.pack('<2H',1000,700))
        self.assertEqual(bytes(f.u.mem_read(LIST+0x600,4)),struct.pack('<2H',350,650))
        self.assertEqual(bytes(f.u.mem_read(LIST+0x700,4)),struct.pack('<2H',100,600))
    def test_blocked_ground_never_inserts_or_consumes_id(self):
        for terrain in (True,False):
            f=Machine();f.blocked=terrain;f.collides=not terrain;f.run()
            self.assertEqual(f.words(D)[0],4)
            self.assertNotIn(0x4298c0,f.calls)
            self.assertEqual(f.words(MAP+0x14)[0],40000000)
    def test_partial_initialization_is_removed_before_native_tick(self):
        f=Machine();f.init_valid=False;f.run()
        self.assertEqual(f.words(D)[0],4);self.assertIn(0x429be0,f.calls)
        self.assertEqual(f.words(D+12)[0],0)
    def test_other_player_and_multiplayer_cannot_spawn(self):
        for other in (False,True):
            f=Machine()
            if not other:f.put(m.GAME_MODE,2)
            f.run(player=PLAYER+100 if other else PLAYER)
            self.assertNotIn(0x4298c0,f.calls)
    def test_alive_update_only_draws_and_syncs_without_ai_movement_or_attacks(self):
        f=Machine();f.put(ENEMY+0x14,RESOURCE);f.put(RESOURCE+4,1)
        f.put(ENEMY+0x338,2);f.run(BEHAVIOR,ENEMY)
        self.assertEqual(f.calls,[BEHAVIOR+m.IDLE,0x459f60])
        self.assertEqual(f.words(ENEMY+0x338)[0],1)
        self.assertEqual(f.words(ENEMY+0x34c)[0],0) # real projectile code rejects inactive enemies
    def test_batch_2000_distinct_instances_share_one_position_and_private_behavior(self):
        f=Machine(quantity=2000);f.run()
        self.assertEqual(f.words(D)[0],3);self.assertEqual(f.words(D+48)[0],2000)
        pointers=f.words(BASE+m.RESULTS,2000);identifiers=f.words(BASE+m.IDS,2000)
        self.assertEqual(len(set(pointers)),2000);self.assertEqual(len(set(identifiers)),2000)
        self.assertEqual(f.calls.count(0x4145b0),1)
        for pointer in pointers:
            self.assertEqual(f.words(pointer+0x18,2),(1400,2000))
            self.assertEqual(f.words(pointer)[0],BEHAVIOR+m.VTABLE)
    def test_batch_quantity_rejects_zero_overflow_fractions_and_booleans(self):
        for n in (0,-1,2001,True,False,1.5,'2000'):
            with self.assertRaises(ValueError):m.spawn_quantity(n)
        self.assertEqual(m.spawn_quantity(2000),2000)
    def test_native_label_height_is_preserved(self):
        f=Machine(height=70);f.run()
        self.assertEqual(f.words(ENEMY+0x34)[0],70)
        self.assertEqual(f.words(ENEMY+0xb8)[0],1)
    @unittest.skipUnless(IMAGE,'Original game executable fixture required')
    def test_original_projectile_gate_accepts_passive_enemy_and_rejects_inactive_one(self):
        for inactive in (0,1):
            f=Machine();f.put(ENEMY+0x34c,inactive)
            for start,end in ((0x45ea43,0x45ea6d),(0x434cd0,0x434ce0)):
                f.u.mem_write(start,IMAGE[start-0x400000:end-0x400000])
            f.u.reg_write(UC_X86_REG_EBX,NODE);f.u.reg_write(UC_X86_REG_ESP,STACK)
            f.u.hook_add(UC_HOOK_CODE,lambda u,a,n,x:u.emu_stop(),begin=0x45ebbd,end=0x45ebbd)
            f.u.emu_start(0x45ea43,0x45ea6d,count=100)
            self.assertEqual(f.u.reg_read(UC_X86_REG_EIP),0x45ebbd if inactive else 0x45ea6d)
    def test_dead_update_passes_to_original_death_and_drop_function(self):
        f=Machine();f.put(ENEMY+0xd4,0);f.run(BEHAVIOR,ENEMY)
        self.assertEqual(f.calls,[0x458f70])
        self.assertEqual(f.u.reg_read(UC_X86_REG_EAX),77)
    def test_idle_clone_removes_all_three_native_attack_emissions_and_relocates(self):
        image=m.passive_image(BEHAVIOR);idle=m.PLAN['idle']
        for at in idle['suppressedCalls']:
            self.assertEqual(image[m.IDLE+at:m.IDLE+at+5],bytes.fromhex('83c4089090'))
        for fix in idle['relocations']:
            target=BEHAVIOR+m.IDLE+fix['end']+struct.unpack_from('<i',image,m.IDLE+fix['offset'])[0]
            expected=fix['target']
            if idle['address']<=expected<idle['address']+438:expected+=BEHAVIOR+m.IDLE-idle['address']
            self.assertEqual(target,expected)
        table=struct.unpack_from('<10I',image,m.VTABLE)
        self.assertEqual(table[2],BEHAVIOR)
        self.assertEqual(table[:2]+table[3:],tuple(m.PLAN['vtable'][:2]+m.PLAN['vtable'][3:]))
    def test_selection_rejects_negative_outside_and_boolean_indices(self):
        data={'mobs':[{'variants':[{'pattern':1,'sample':True}]}]}
        for mi,vi in ((True,0),(-1,0),(1,0),(0,-1),(0,1),(0,False)):
            with self.assertRaises(ValueError):m.selection(data,mi,vi)
    def test_placement_distance_accounts_for_boss_and_player_body(self):
        offsets=m.candidate_offsets((-700,-600,699,599),(-80,-80,79,79))
        self.assertEqual(len(offsets),32);self.assertEqual(offsets[0],(940,0))
        self.assertEqual(len(set(offsets)),32)


if __name__=='__main__':unittest.main()
