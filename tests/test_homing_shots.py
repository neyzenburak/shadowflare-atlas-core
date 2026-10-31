"""Run the detour, original volleys and native Flame Strike movement in x86."""
import hashlib
import math
import os
from pathlib import Path
import struct
import sys
import unittest

import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import *

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'app'))
from homing_shots import make_stub, CALLSITE, CREATE, ORIGINAL, DATA, VERIFIED

FIX = Path(os.environ.get('SHADOWFLARE_FIXTURE_DIR', ROOT.parent/'shadowflare-drop-analysis/input'))/'ShadowFlare.exe'
PE = pefile.PE(str(FIX)) if FIX.exists() else None
EXE = PE.get_memory_mapped_image() if PE else None
BASE = 0x30000000
STACK = 0x31010000
PLAYER = 0x32000000
MAP = PLAYER+0x10000
MANAGER = MAP+0x1000
BLOCK = MAP+0x2000
MONSTER = MAP+0x3000
EFFECT = MAP+0x4000
PACKET = MAP+0x5000
PROJECTILE = MAP+0x6000
ITEM = MAP+0x8000
STOP = BASE+0xf00


class Fixture:
    def __init__(self, enabled=1, kind=1, target=555, owner=7):
        self.u = Uc(UC_ARCH_X86, UC_MODE_32)
        for a, n in ((0, 0x1000), (0x400000, 0x100000), (BASE, 0x10000),
                     (STACK-0x10000, 0x20000), (PLAYER, 0x40000)):
            self.u.mem_map(a, n)
        self.u.mem_write(0x400000, EXE)
        self.u.mem_write(BASE, make_stub(BASE))
        self.u.mem_write(CALLSITE, b'\xe8'+struct.pack('<i', BASE-CALLSITE-5))
        self.put(BASE+DATA+4, enabled)
        self.put(0x48ce0c, MANAGER+0x100)
        self.put(MANAGER+0x100, 1, MANAGER+0x200, 0)
        self.put(MANAGER+0x200, PLAYER)
        self.put(PLAYER+4, 7)
        self.put(PLAYER+0x458, MAP)
        self.put(PLAYER+0x1a4, 100)
        self.put(MAP+0x30, MANAGER)
        self.put(MANAGER, 1, MANAGER+0x300)
        self.put(MANAGER+0x300, BLOCK)
        self.put(BLOCK, 2, 0, MONSTER)
        self.put(MONSTER+4, 555)
        self.put(MONSTER+0xd4, 100)
        self.put(MONSTER+0x18, 1000, -300)
        self.put(EFFECT, MAP)
        self.put(EFFECT+0xc, kind, 1, owner, 20, target, 100, 350)
        self.put(EFFECT+0x40, 8)
        self.put(EFFECT+0x60, 0)
        self.u.mem_write(EFFECT+0x64, bytes((i*17)%256 for i in range(0x134)))
        self.u.mem_write(PACKET, bytes((i*11)%256 for i in range(0x1f8)))
        self.created = []
        self.volley = []
        self.u.reg_write(UC_X86_REG_FPCW, 0x37f)
        self.u.hook_add(UC_HOOK_CODE, self.hook)

    def put(self, a, *values):
        self.u.mem_write(a, struct.pack('<'+'I'*len(values), *(v & 0xffffffff for v in values)))

    def words(self, a, n=1):
        return struct.unpack('<'+'I'*n, self.u.mem_read(a, n*4))

    def ret(self, count, value=1):
        sp = self.u.reg_read(UC_X86_REG_ESP)
        self.u.reg_write(UC_X86_REG_EAX, value)
        self.u.reg_write(UC_X86_REG_ESP, sp+4+count*4)
        self.u.reg_write(UC_X86_REG_EIP, self.words(sp)[0])

    def hook(self, u, at, size, user):
        if at == CREATE:
            sp = u.reg_read(UC_X86_REG_ESP)
            template, packet = self.words(sp+4, 2)
            self.created.append((template, bytes(u.mem_read(packet, 0x1f8))))
            self.ret(2, 777)
        elif at == 0x455ee0:
            self.ret(2, ITEM)
        elif at == BASE+0x800:  # character animation lookup
            self.ret(1, ITEM)
        elif at == BASE+0x810:
            self.ret(1, ITEM)
        elif at == BASE+0x820:
            self.ret(1, 16)
        elif at == BASE+0x830:  # native OBJECTDISP ctor only
            self.ret(0, u.reg_read(UC_X86_REG_ECX))
        elif at == 0x42fdc0:
            sp = u.reg_read(UC_X86_REG_ESP)
            self.volley.append(self.words(sp+4, 22))
            self.ret(22)

    def gate(self):
        regs = {UC_X86_REG_EAX: 11, UC_X86_REG_EBX: EFFECT,
                UC_X86_REG_ECX: MAP, UC_X86_REG_EDX: 44, UC_X86_REG_ESI: 55,
                UC_X86_REG_EDI: 66, UC_X86_REG_EBP: 77}
        for r, v in regs.items():
            self.u.reg_write(r, v)
        self.put(STACK, STOP, 123, PACKET)
        self.u.reg_write(UC_X86_REG_ESP, STACK)
        self.u.reg_write(UC_X86_REG_EFLAGS, 0x246)
        # Stop just before the original constructor; inspect its complete ABI.
        self.u.emu_start(BASE, CREATE, count=10000)
        for r, v in regs.items():
            assert self.u.reg_read(r) == v, (r, v, self.u.reg_read(r))
        assert self.u.reg_read(UC_X86_REG_EFLAGS) == 0x246
        assert self.u.reg_read(UC_X86_REG_ESP) == STACK
        assert self.words(STACK, 3) == (STOP, 123, PACKET)
        assert self.words(BASE+DATA)[0] == 0
        return bytes(self.u.mem_read(PACKET, 0x1f8))

    def controller(self, visual=0):
        for i, offset in ((0x473344, 0x800), (0x473438, 0x810), (0x47343c, 0x820)):
            self.put(i, BASE+offset)
        self.put(ITEM+0x34, 1)
        self.put(STACK, STOP, visual)
        self.u.reg_write(UC_X86_REG_ECX, EFFECT)
        self.u.reg_write(UC_X86_REG_ESP, STACK)
        self.u.emu_start(0x42a300, STOP, count=100000)
        assert self.u.reg_read(UC_X86_REG_EIP) == STOP
        assert self.u.reg_read(UC_X86_REG_ESP) == STACK+8
        return self.created

    def movement(self, mode=1, heading=0, target_xy=(1000, -300)):
        self.put(0x473364, BASE+0x830)
        self.put(PROJECTILE+0xd8, mode, 20, 20, 555)
        self.put(PROJECTILE+0x5c, MAP)
        self.put(PROJECTILE+0xa9c, 1)
        self.put(PROJECTILE+0x118, 100)
        self.put(PROJECTILE+0x11c, 0, 0)
        self.u.mem_write(PROJECTILE+0x108, struct.pack('<d', heading))
        result = []
        for frame in range(8):
            self.put(MONSTER+0x18, target_xy[0]+frame*20, target_xy[1]-frame*10)
            self.put(STACK, STOP)
            self.u.reg_write(UC_X86_REG_ESP, STACK)
            self.u.reg_write(UC_X86_REG_ECX, PROJECTILE)
            self.u.emu_start(0x45e1e0, 0x45e555, count=100000)
            assert self.u.reg_read(UC_X86_REG_EIP) == 0x45e555
            sp = self.u.reg_read(UC_X86_REG_ESP)
            xy = struct.unpack('<ii', self.u.mem_read(sp+0x48, 8))
            self.put(PROJECTILE+0x18, *xy)
            result.append((xy, struct.unpack('<d', self.u.mem_read(PROJECTILE+0x108, 8))[0]))
        return result

    def weapon_volley(self, count, double=False):
        # Execute the actual two native ranged-weapon emission loops. Only
        # enqueueing the effect is intercepted, so counts/angles are native.
        self.put(ITEM+0x104, 100, 0, 0)
        self.put(PLAYER+0x1264, 555)
        self.put(MAP+0x5c, MANAGER)
        self.put(STACK+0xc, PACKET)
        self.put(STACK+0x10, 1)
        self.put(STACK+0x14, count if double else 1)
        self.u.mem_write(STACK+0x18, struct.pack('<d', .25))
        self.put(STACK+0x20, count)
        for i in range(count):
            self.u.mem_write(PACKET+i*8, struct.pack('<d', (i-(count-1)/2)*.1))
        self.u.reg_write(UC_X86_REG_ESP, STACK)
        self.u.reg_write(UC_X86_REG_EBX, PLAYER)
        self.u.reg_write(UC_X86_REG_ESI, ITEM)
        self.u.reg_write(UC_X86_REG_EDI, PACKET if double else 8)
        self.u.emu_start(0x438695 if double else 0x438861, 0x4388fa, count=100000)
        assert self.u.reg_read(UC_X86_REG_EIP) == 0x4388fa
        assert self.u.reg_read(UC_X86_REG_ESP) == STACK
        return self.volley


@unittest.skipIf(EXE is None, 'Local original EXE fixture required')
class HomingTests(unittest.TestCase):
    def test_verified_native_code_and_hook_fingerprints(self):
        self.assertEqual(PE.get_data(CALLSITE-0x400000, 5), ORIGINAL)
        for a, n, sha in VERIFIED:
            self.assertEqual(hashlib.sha256(PE.get_data(a-0x400000, n)).hexdigest(), sha)

    def test_only_two_steering_fields_change_with_exact_caller_preservation(self):
        f = Fixture()
        before = bytes(f.u.mem_read(PACKET, 0x1f8))
        after = f.gate()
        self.assertEqual(after[:8], before[:8])
        self.assertEqual(after[8:16], struct.pack('<II', 1, 20))
        self.assertEqual(after[16:], before[16:])
        self.assertEqual(f.words(BASE+DATA+8, 2), (1, 0))

    def test_disabled_multiplayer_other_player_and_spells_are_unchanged(self):
        cases = [Fixture(enabled=0), Fixture(owner=8), Fixture(kind=10015), Fixture(kind=10011)]
        f = Fixture(); f.put(0x482db0, 1); cases.append(f)
        f = Fixture(); f.put(PLAYER+0x458, MAP+0x100); cases.append(f)
        f = Fixture(); f.put(PLAYER+0x1a4, 0); cases.append(f)
        for f in cases:
            before = bytes(f.u.mem_read(PACKET, 0x1f8))
            self.assertEqual(f.gate(), before)
            self.assertEqual(f.words(BASE+DATA+8, 2), (0, 0))

    def test_no_target_dead_target_npc_and_stale_id_use_original_flight(self):
        cases = [Fixture(target=-1), Fixture(target=444)]
        f = Fixture(); f.put(MONSTER+0xd4, 0); cases.append(f)
        f = Fixture(); f.put(BLOCK, 0); cases.append(f)
        f = Fixture(); f.put(EFFECT+0x18, 1); cases.append(f)
        for f in cases:
            before = bytes(f.u.mem_read(PACKET, 0x1f8))
            self.assertEqual(f.gate(), before)
            self.assertEqual(f.words(BASE+DATA+8, 2), (0, 1))

    def test_native_weapon_packets_keep_damage_art_speed_and_all_other_fields(self):
        for kind in range(8):
            with self.subTest(kind=kind):
                slow, fast = Fixture(enabled=0, kind=kind), Fixture(kind=kind)
                a, b = slow.controller(), fast.controller()
                self.assertEqual(len(a), 1)
                self.assertEqual(len(b), 1)
                self.assertEqual(a[0][0], b[0][0])
                original, changed = a[0][1], b[0][1]
                self.assertEqual(changed[:8], original[:8])
                self.assertEqual(changed[8:16], struct.pack('<II', 1, 20))
                self.assertEqual(changed[16:], original[16:])

    def test_all_native_volley_counts_and_double_shot_fixed_origin_are_supported(self):
        for count in range(1, 8):
            f = Fixture()
            volley = f.weapon_volley(count, double=count == 2)
            self.assertEqual(len(volley), count)
            for args in volley:
                # Native argument order: effect, source type, player, target
                # type, target id, speed. The two-shot path has source type 0.
                self.assertEqual(args[:6], (1, 0 if count == 2 else 1, 7, 20, 555, 100))
                self.assertEqual(args[6], 350)
                part = Fixture()
                part.put(EFFECT+0x10, args[1])
                result = part.gate()
                self.assertEqual(result[8:16], struct.pack('<II', 1, 20))

    def test_native_movement_curves_toward_moving_monster(self):
        for heading in (-.4, -.2, 0, .2, .4, .6, .8):
            result = Fixture().movement(heading=heading)
            xy, last_heading = result[-1]
            self.assertGreater(xy[0], 500)
            self.assertLess(xy[1], -150)
            self.assertTrue(math.isfinite(last_heading))
            self.assertNotAlmostEqual(last_heading, heading)

    def test_native_target_loss_and_death_stop_steering_without_new_target(self):
        for dead in (False, True):
            f = Fixture()
            if dead:
                f.put(MONSTER+0xd4, 0)
            else:
                f.put(MONSTER+4, 556)
            result = f.movement(heading=.1)
            self.assertEqual(f.words(PROJECTILE+0xa9c)[0], 0)
            self.assertTrue(all(abs(h-.1) < 1e-12 for xy, h in result))


if __name__ == '__main__':
    unittest.main()
