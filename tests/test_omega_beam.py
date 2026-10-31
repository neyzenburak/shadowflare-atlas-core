"""Run the actual x86 gates, native projection and fixed damage fast path."""
import hashlib
import math
from pathlib import Path
import struct
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import tempfile
import pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
from unicorn.x86_const import *
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
import omega_beam as m
from omega_path import project,unproject,find_route,wall_route,length,turn_ok,prefix,heading,deadline_distance
from meteor_skill import visible_targets,unique_targets,EFFECT_INDEX
from special_effects import SPECS
import meteor_skill
from test_mob_spawn import IMAGE

MEM=0x32000000;PLAYER=MEM+0x1000;MAP=MEM+0x4000;ENEMY=MEM+0x6000
BLOCK=MEM+0x7000;INPUT=MEM+0x8000;SCREEN=MEM+0x9000;PROJECTION=MEM+0xa000
STACK=MEM+0xe000;TICK=MEM+0xf000;KEY=TICK+0x10;COUNT=TICK+0x20
INDEX=TICK+0x30;RECORD=TICK+0x40;IDENT=TICK+0x50;PACKET=TICK+0x60


class Machine:
    def __init__(self,base=0x30000000):
        self.u=Uc(UC_ARCH_X86,UC_MODE_32);self.base=base;self.d=base+m.DATA
        self.u.mem_map(0x400000,0x100000);self.u.mem_map(MEM,0x10000)
        self.u.mem_map(base,m.SIZE);self.u.mem_map(0x10000000,0x20000)
        if IMAGE:self.u.mem_write(0x400000,IMAGE)
        dll=pefile.PE(str(ROOT.parent/'shadowflare-drop-analysis/beam-work/RKC_RPGSCRN.dll'))
        self.u.mem_write(0x10000000,dll.get_memory_mapped_image())
        self.u.mem_write(base,m.make_image(base,PACKET,0x10001600,TICK,True))
        self.put(self.d+80,900);self.put(0x48d778,-1)
        self.put(PLAYER+0x2c,6);self.put(PLAYER+0x1a4,100);self.put(PLAYER+0x1b4,777)
        self.put(PLAYER+0x458,MAP);self.put(PLAYER+0x3f8,INPUT);self.put(PLAYER+4,0)
        self.put(PLAYER+0x2e0,1000,2000);self.put(INPUT+0x24,1,0,1)
        self.put(MAP+0x30,MEM+0xb000);self.put(MAP+0x3c,MEM+0xc000)
        self.put(BLOCK,2,2,ENEMY);self.put(ENEMY+4,123)
        self.put(ENEMY+0xd4,9999);self.put(ENEMY+0x5c,MAP);self.put(ENEMY+0x18,2000,2000)
        self.put(0x48ce0c,MEM+0xd000);self.put(0x482d1c,SCREEN);self.put(0x482d14,PROJECTION)
        self.put(PROJECTION+0x18,10,5);self.put(SCREEN+0x10,0,0,1920,900)
        for address,target in ((0x4735c0,KEY),(0x47334c,COUNT),(0x473350,INDEX),(0x473354,RECORD),(0x47345c,IDENT)):
            self.put(address,target)
        self.left_alt=True;self.hover=True;self.blocked=False;self.calls=[];self.packets=[];self.lookup={123:BLOCK}
        self.u.hook_add(UC_HOOK_CODE,self.hook)

    def put(self,a,*v):self.u.mem_write(a,struct.pack('<'+'I'*len(v),*(n&0xffffffff for n in v)))
    def words(self,a,n=1):return struct.unpack('<'+'I'*n,self.u.mem_read(a,n*4))
    def ret(self,value=1,args=0):
        sp=self.u.reg_read(UC_X86_REG_ESP);self.u.reg_write(UC_X86_REG_EIP,self.words(sp)[0])
        self.u.reg_write(UC_X86_REG_ESP,sp+4+args*4);self.u.reg_write(UC_X86_REG_EAX,value)

    def hook(self,u,a,size,user):
        sp=u.reg_read(UC_X86_REG_ESP)
        if a in (0x441cad,0x441cf8,0x41f130,0x41ec03):u.emu_stop();return
        if a==0x434cb0:self.ret(PLAYER)
        elif a==TICK:self.ret(1000)
        elif a==KEY:
            self.assert_key=self.words(sp+4)[0];self.ret(0x8000 if self.left_alt else 0,1)
        elif a==COUNT:self.ret(1 if self.hover else 0)
        elif a==INDEX:self.ret(MEM+0x100,1)
        elif a==RECORD:self.ret(MEM+0x120)
        elif a==IDENT:self.ret(123)
        elif a==0x4299e0:self.ret(self.lookup.get(self.words(sp+4)[0],0),1)
        elif a==self.base+m.GUARD:self.ret(0 if self.blocked else 1)
        elif a==0x4145b0:
            args=self.words(sp+4,7)
            assert args==(MAP,0xffffffff,args[2],self.base+0x2340,0,2,1),args
            self.calls.append(('probe',self.words(args[2],2)));self.ret(0 if self.blocked else 1,7)
        elif a==0x459690:
            packet,point=self.words(sp+4,2);assert packet==self.base+0x2200
            assert self.words(packet+0x94)[0]==1
            assert self.words(packet)[0]==0
            assert self.words(packet+8)[0]==0
            damage=self.words(packet+0x10)[0]
            self.calls.append(('damage',damage));self.put(ENEMY+0xd4,max(0,self.words(ENEMY+0xd4)[0]-damage))
            self.ret(1,2)
        elif a==PACKET:
            self.packets.append(self.words(sp+4,18))
            for r in (UC_X86_REG_EAX,UC_X86_REG_ECX,UC_X86_REG_EDX):u.reg_write(r,0xdeadbeef)
            self.ret(1,18)

    def run(self,render=False,zf=True):
        saved={UC_X86_REG_EBX:123,UC_X86_REG_ECX:234,UC_X86_REG_EDX:345,
               UC_X86_REG_ESI:PLAYER,UC_X86_REG_EDI:567,UC_X86_REG_EBP:678}
        for r,v in saved.items():self.u.reg_write(r,v)
        self.u.reg_write(UC_X86_REG_ESP,STACK)
        flags=0x202|(0x40 if zf else 0);self.u.reg_write(UC_X86_REG_EFLAGS,flags)
        self.u.emu_start(self.base+(0x1000 if render else 0),0,count=100000)
        assert self.u.reg_read(UC_X86_REG_ESP)==STACK
        for r,v in saved.items():assert self.u.reg_read(r)==v,(r,v,self.u.reg_read(r))
        assert self.u.reg_read(UC_X86_REG_EFLAGS)==flags
        return self.u.reg_read(UC_X86_REG_EIP)


class PathTests(unittest.TestCase):
    def test_one_second_arrival_is_independent_of_length_and_replanning(self):
        for total in (10,100,2000,15000):
            distance=0;previous=0
            for now in (.07,.19,.45,.67,.93,1.0):
                distance=deadline_distance(distance,total,previous,now,1.0);previous=now
            self.assertEqual(distance,total)
        self.assertEqual(deadline_distance(80,900,.9,1.0,1.0),900)
    def assert_angles(self,route):
        for a,b in zip(route,route[1:]):
            dx=abs(a[0]-b[0]);dy=abs(a[1]-b[1])
            self.assertTrue(dx<1e-6 or dy<1e-6 or abs(dx-dy)<1e-6,(a,b))
        for i in range(len(route)-2):self.assertTrue(turn_ok(*route[i:i+3]))

    def test_route_goes_around_wall_with_45_90_turns(self):
        def clear(a,b):
            for i in range(41):
                x=a[0]+(b[0]-a[0])*i/40;y=a[1]+(b[1]-a[1])*i/40
                if not (-30<=x<=200 and -120<=y<=120) or 45<=x<=75 and -48<=y<=48:return False
            return True
        route=find_route((0,0),(140,0),clear)
        self.assertIsNotNone(route);self.assert_angles(route)
        self.assertTrue(all(clear(a,b) for a,b in zip(route,route[1:])))
        self.assertGreater(length(route),140)

    def test_closed_chamber_fails_and_ray_stops_at_first_wall(self):
        clear=lambda a,b:all(-30<=a[i]<=30 and -30<=b[i]<=30 for i in (0,1))
        self.assertIsNone(find_route((0,0),(120,0),clear))
        route=wall_route((0,0),(120,0),clear)
        self.assertLessEqual(route[-1][0],30);self.assertGreater(route[-1][0],25)

    def test_projection_round_trip_negative_coordinates(self):
        for p in ((-1500,4000),(0,0),(93000,-7000)):
            q=unproject(project(p,(10,5)),(10,5))
            self.assertAlmostEqual(p[0],q[0]);self.assertAlmostEqual(p[1],q[1])

    def test_moving_target_behind_beam_does_not_introduce_135_or_180_turn(self):
        old=prefix([(0,0),(96,0)],60)
        route=find_route(old[-1],(12,-12),lambda a,b:all(-100<=n<=200 for p in (a,b) for n in p),
                         initial_heading=heading(*old[-2:]))
        self.assertIsNotNone(route);self.assert_angles(old+route[1:])

    def test_native_rejected_point_is_fed_back_into_route_search(self):
        scene=object.__new__(m.Scene);scene.mx=scene.my=100;scene.native_blocks=[]
        scene.learn_block((65,0),(48,0))
        self.assertLess(scene.native_blocks[0][2],17)
        def clear(a,b):
            return all(-120<=v<=160 for p in (a,b) for v in p) and all(
                all(math.hypot(a[0]+(b[0]-a[0])*i/40-x,a[1]+(b[1]-a[1])*i/40-y)>=r for i in range(41))
                for x,y,r in scene.native_blocks)
        route=find_route((48,0),(120,0),clear,initial_heading=0)
        self.assertIsNotNone(route);self.assert_angles(route)
        self.assertTrue(all(clear(a,b) for a,b in zip(route,route[1:])))


@unittest.skipIf(IMAGE is None,'Original executable fixture required')
class NativeTests(unittest.TestCase):
    def test_original_fingerprints(self):
        for s in m.PLAN['verified']:
            raw=IMAGE[s['address']-0x400000:s['address']-0x400000+s['length']]
            self.assertEqual(hashlib.sha256(raw).hexdigest(),s['sha256'])
        self.assertEqual(IMAGE[m.INPUT_HOOK-0x400000:m.INPUT_HOOK-0x400000+6],m.INPUT_ORIGINAL)
        self.assertEqual(IMAGE[m.RENDER_HOOK-0x400000:m.RENDER_HOOK-0x400000+6],m.RENDER_ORIGINAL)

    def test_capture_real_left_alt_warrior_target_and_attack_times_three(self):
        for base in (0x30000000,0x34000000):
            f=Machine(base);self.assertEqual(f.run(),0x441cad)
            self.assertEqual(f.assert_key,0xa4)
            self.assertEqual(f.words(f.d+24,9),(PLAYER,MAP,123,ENEMY,1000,2000,2000,2000,2331))
            self.assertEqual(f.words(f.d+8)[0],1)

    def test_other_classes_right_alt_panels_and_disabled_do_not_capture(self):
        for address,value in ((PLAYER+0x2c,5),(PLAYER+0x2c,9),(0x482db0,1),(0x48ce3c,1),(0x48ce34,123),(0x48d778,2)):
            f=Machine();f.put(address,value);self.assertEqual(f.run(),0x441cf8);self.assertEqual(f.words(f.d+8)[0],0)
        f=Machine();f.left_alt=False;self.assertEqual(f.run(),0x441cf8)
        f=Machine();f.put(f.d+4,0);self.assertEqual(f.run(),0x441cf8)

    def test_held_right_does_not_repeat_and_empty_hover_is_safe(self):
        f=Machine();f.run();f.run();self.assertEqual(f.words(f.d+8)[0],1)
        f=Machine();f.hover=False;self.assertEqual(f.run(),0x441cad);self.assertEqual(f.words(f.d+8)[0],0)

    def test_real_collision_probe_contract_and_blocked_acknowledgement(self):
        f=Machine();f.run();f.put(f.d+84,2);f.put(f.base+0x2400,1200,2100,1300,2200)
        f.put(f.d+60,1);f.run()
        self.assertEqual(f.words(f.d+60,2),(0,1));self.assertEqual(len(f.calls),2)
        f.blocked=True;f.put(f.d+60,1);f.run();self.assertEqual(f.words(f.d+64)[0],2)
        self.assertEqual(f.words(f.d+88)[0],0)

    def test_damage_only_on_arrival_and_id_pointer_map_guards(self):
        f=Machine();f.run();self.assertEqual(f.calls,[])
        f.put(f.d+72,2000,2000);f.put(f.d+60,2);f.run()
        self.assertEqual(f.calls,[('damage',2331)]);self.assertEqual(f.words(f.d+112,2),(9999,7668))
        f.run();self.assertEqual(len(f.calls),1)
        for address,value in ((m.DATA+32,999),(m.DATA+36,ENEMY+8),(m.DATA+28,MAP+8),(m.DATA+72,90000)):
            f=Machine();f.run();f.put(f.d+72,2000,2000);f.put(f.base+address,value);f.put(f.d+60,2);f.run()
            self.assertFalse(f.calls);self.assertEqual(f.words(f.d+64)[0],4)
        f=Machine();f.run();f.put(BLOCK,0);f.put(f.d+60,2);f.run();self.assertFalse(f.calls)

    def test_meteor_capture_does_not_require_hover_and_latches_surprise(self):
        f=Machine();f.hover=False;f.put(f.d+156,1,1)
        self.assertEqual(f.run(),0x441cad)
        self.assertEqual(f.words(f.d+8)[0],1)
        self.assertEqual(f.words(f.d+164,3),(1,1,1000))
        self.assertEqual(f.words(f.d+56)[0],2331)

    def test_native_meteor_batch_hits_each_id_once_and_is_idempotent(self):
        f=Machine();f.run()
        second=ENEMY+0x800;node=BLOCK+0x80;f.put(node,2,2,second);f.lookup[124]=node
        f.put(second+4,124);f.put(second+0x5c,MAP);f.put(second+0xd4,5000)
        rows=[(123,ENEMY),(123,ENEMY),(124,second),(999,ENEMY)]
        for i,(ident,ptr) in enumerate(rows):f.put(f.base+0x2800+i*32,ident,ptr,0,0,0,0,0,0)
        f.put(f.d+176,len(rows));f.put(f.d+60,3);f.run()
        self.assertEqual(f.calls,[('damage',2331),('damage',2331)])
        self.assertEqual([f.words(f.base+0x2800+i*32+24)[0] for i in range(4)],[1,2,1,2])
        f.put(f.d+60,3);f.run();self.assertEqual(len(f.calls),2)

    def test_large_mushroom_sprite_uses_its_own_anchor_and_dib(self):
        f=Machine();buffer=f.base+m.BUFFERS[0];index=EFFECT_INDEX['mushroom']
        f.put(buffer,1,MAP,PLAYER,0);f.put(buffer+16,5000,1000,0,0,index,0);f.put(f.d+132,buffer)
        f.run(render=True);p=f.packets[0]
        self.assertEqual(p[6:8],(400-96,300-205))
        self.assertEqual(p[17],f.words(f.base+0x42000+index*24)[0])

    def test_visible_selection_excludes_dead_npc_offscreen_and_duplicate_links(self):
        f=Machine();array=MEM+0xd100;manager=MEM+0xb000
        f.put(manager,5,array)
        rows=[]
        for i,(kind,hp,xy) in enumerate([(2,100,(8000,2000)),(2,0,(8000,2000)),(0,100,(8000,2000)),(2,100,(90000,0))]):
            block=BLOCK+i*0x40;obj=ENEMY+i*0x200
            f.put(block,kind,2,obj);f.put(obj+4,123+i);f.put(obj+0x18,*xy)
            f.put(obj+0x5c,MAP);f.put(obj+0xd4,hp);rows.append(block)
        f.put(array,*rows,rows[0]);f.put(SCREEN+0x40,450,200)
        game=SimpleNamespace(words=f.words,read=lambda a,n:bytes(f.u.mem_read(a,n)))
        targets,scale,viewport=visible_targets(game,MAP)
        self.assertEqual([t['id'] for t in targets],[123])
        self.assertEqual(scale,(10,5));self.assertEqual(viewport,(0,0,1920,900))

    def test_projectiles_follow_their_own_target_and_do_not_retarget_dead_enemy(self):
        f=Machine();target=dict(id=123,pointer=ENEMY,xy=(2000,2000),alive=True)
        game=SimpleNamespace(words=f.words,read=lambda a,n:bytes(f.u.mem_read(a,n)))
        controller=SimpleNamespace(game=game);flight=dict(map=MAP,targets=[target])
        f.put(ENEMY+0x18,2600,2900)
        meteor_skill.MeteorSkill._refresh_meteor_targets(controller,flight)
        self.assertEqual(target['xy'],(2600,2900));self.assertTrue(target['alive'])
        f.put(ENEMY+0xd4,0);meteor_skill.MeteorSkill._refresh_meteor_targets(controller,flight)
        self.assertFalse(target['alive'])

    def test_recast_at_impact_keeps_both_ground_effects_for_their_own_three_seconds(self):
        for surprise in (False,True):
            f=Machine();f.put(f.d+156,1,int(surprise));f.run()
            game=SimpleNamespace(words=f.words,state=lambda:dict(player=PLAYER,map=MAP),
                write=lambda a,b:f.u.mem_write(a,b),read=lambda a,n:bytes(f.u.mem_read(a,n)))
            controller=object.__new__(m.OmegaBeam);controller.game=game;controller.base=f.base
            controller.aftermaths=[];controller.last={};hits=[]
            def hit(flight):
                hits.append(flight)
                for target in flight['targets']:target['impactXY']=target['xy']
                controller.last['hitCount']=len(unique_targets(flight['targets']))
            controller._meteor_hits=hit
            target=dict(id=123,pointer=ENEMY,xy=(2000,2000),alive=True)
            controller.flight=dict(kind='meteor',player=PLAYER,map=MAP,targets=[target,target.copy()],
                                   scale=(10,5),surprise=surprise,started=0,impact=None,hit=False)
            with patch('time.monotonic',return_value=.9):controller._tick_meteor(.9)
            self.assertIsNone(controller.flight);self.assertEqual(len(controller.aftermaths),1)
            self.assertEqual(f.words(f.d+120)[0],0)
            buffer=f.words(f.d+132)[0];self.assertGreater(f.words(buffer)[0],0)
            # A real native gesture is admitted while the first flames/clouds
            # are still visible; a second fall does not remove them.
            f.run();self.assertEqual(f.words(f.d+8)[0],2)
            with patch('time.monotonic',return_value=1.0),patch('meteor_skill.visible_targets',return_value=([target.copy()],(10,5),(0,0,1920,900))):
                controller._begin_meteor(f.words(f.d,48))
                controller._draw_meteor(1.0)
            self.assertEqual(len(controller.aftermaths),1)
            self.assertIsNotNone(controller.flight)
            with patch('time.monotonic',return_value=1.9):controller._tick_meteor(1.9)
            self.assertEqual(len(hits),2);self.assertEqual(len(controller.aftermaths),2)
            self.assertIsNone(controller.flight);self.assertEqual(f.words(f.d+120)[0],0)
            controller._meteor_hits=lambda *a:(_ for _ in ()).throw(AssertionError('Ground effects must not hit'))
            third=None
            for now,count in ((2.0,2),(3.89,2),(3.91,1),(4.91,0)):
                if now==3.89:
                    f.run()
                    with patch('time.monotonic',return_value=3.8),patch('meteor_skill.visible_targets',return_value=([target.copy()],(10,5),(0,0,1920,900))):
                        controller._begin_meteor(f.words(f.d,48))
                    third=controller.flight
                with patch('time.monotonic',return_value=now):controller._publish([])
                self.assertEqual(len(controller.aftermaths),count)
                if third is not None:
                    self.assertIs(controller.flight,third)
                    self.assertEqual(f.words(f.d+120)[0],1,'An expired cloud must not unlock a new falling projectile')
            self.assertEqual(f.words(f.words(f.d+132)[0])[0],0)

    def test_lingering_effects_are_removed_on_map_or_class_change(self):
        for destination,cls in ((MAP+8,6),(MAP,5)):
            f=Machine();f.put(PLAYER+0x2c,cls)
            controller=object.__new__(m.OmegaBeam);controller.base=f.base;controller.flight=None
            controller.game=SimpleNamespace(words=f.words,state=lambda:dict(player=PLAYER,map=destination),
                                            write=lambda a,b:f.u.mem_write(a,b))
            controller.aftermaths=[dict(player=PLAYER,map=MAP,impact=1.0)]
            with patch('time.monotonic',return_value=2.0):controller._publish([])
            self.assertEqual(controller.aftermaths,[])
            self.assertEqual(f.words(f.words(f.d+132)[0])[0],0)

    def test_original_damage_calculator_returns_exact_fixed_damage(self):
        f=Machine();packet=f.base+0x2200;f.put(packet+0x10,2331)
        f.put(STACK,KEY,packet,MEM);f.u.reg_write(UC_X86_REG_ESP,STACK)
        f.u.emu_start(0x412a40,KEY,count=1000)
        self.assertEqual(f.u.reg_read(UC_X86_REG_EAX),2331)
        self.assertEqual(f.u.reg_read(UC_X86_REG_ESP),STACK+12)

    def test_renderer_projection_packet_abi_and_both_original_branch_outcomes(self):
        for zf in (True,False):
            f=Machine();buffer=f.base+m.BUFFERS[0]
            f.put(buffer,1,MAP,PLAYER,0);f.put(buffer+16,5000,1000,0,-40,7,0)
            f.put(f.d+132,buffer)
            self.assertEqual(f.run(render=True,zf=zf),0x41ec03 if zf else 0x41f130)
            self.assertEqual(len(f.packets),1)
            p=f.packets[0];self.assertEqual(p[6:8],(400-24,300-40-24))
            self.assertEqual(p[17],f.base+m.ATLAS+7*m.STRIDE)
            self.assertEqual(f.words(f.d+136)[0],0)
            self.assertEqual(f.words(f.d+128)[0],0)

    def test_renderer_does_not_draw_other_map_player_class_or_invalid_count(self):
        for map_pointer,player,count,cls in ((MAP+8,PLAYER,1,6),(MAP,PLAYER+8,1,6),(MAP,PLAYER,4097,6),(MAP,PLAYER,1,5)):
            f=Machine();buffer=f.base+m.BUFFERS[0];f.put(buffer,count,map_pointer,player,0)
            f.put(f.d+132,buffer);f.put(PLAYER+0x2c,cls);f.run(render=True);self.assertEqual(len(f.packets),0)


if __name__=='__main__':unittest.main()
