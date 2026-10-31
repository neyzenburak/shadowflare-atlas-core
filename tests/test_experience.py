"""Execute EXP detours and the original level-up code in a 32-bit emulator."""
import hashlib
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import Mock, patch

from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import *

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'app'))
import experience as e
import level_rewind as r
from test_mob_spawn import IMAGE

BASE = 0x30000000
PLAYER = BASE+0x10000
MAP = BASE+0x20000
MONSTER = BASE+0x30000
CONTROL = BASE+0x40000
TICK = BASE+0xe0000
TABLE = TICK+0x100
VALUE = TICK+0x200
STOP = BASE+0xff000
STACK = BASE+0xf0000
XP_STUB = BASE+0x2000


class Machine:
    def __init__(self, factor=1000, level=79):
        self.u = Uc(UC_ARCH_X86, UC_MODE_32)
        self.u.mem_map(0x400000, 0x100000)
        self.u.mem_map(BASE, 0x100000)
        if IMAGE:
            self.u.mem_write(0x400000, IMAGE)
        self.u.mem_write(XP_STUB, e.make_stub(XP_STUB, TICK))
        self.put(XP_STUB+e.DATA, 0, factor, 1000, 0, 0, 0, 0, 0)
        self.put(PLAYER+0x34, level)
        self.put(PLAYER+0x194, level)
        self.put(PLAYER+0x458, MAP)
        self.put(PLAYER+0x1a4, 999)
        self.put(PLAYER+0x28, 0, 6)
        self.u.mem_write(PLAYER+0xec, bytes([6])*100)
        self.put(PLAYER+0x38, *range(1000, 1000+r.STAT_BYTES//4))
        self.put(MONSTER+0xe4, 150)
        self.put(MONSTER+0x288, 150)
        self.put(MONSTER+0x17c, 100000)
        self.put(CONTROL+0xa714, *([0xffffffff]*8))
        self.put(0x47353c, TABLE)
        self.put(0x473540, VALUE)
        self.tick = 1001
        self.calls = []
        self.corrupt_refresh = False
        self.u.hook_add(UC_HOOK_CODE, self.hook)

    def put(self, a, *values):
        self.u.mem_write(a, struct.pack('<'+'I'*len(values), *(n & 0xffffffff for n in values)))

    def words(self, a, count=1):
        return struct.unpack('<'+'I'*count, self.u.mem_read(a, 4*count))

    def ret(self, args=0, value=0):
        sp = self.u.reg_read(UC_X86_REG_ESP)
        dest = self.words(sp)[0]
        self.u.reg_write(UC_X86_REG_ESP, sp+4+4*args)
        self.u.reg_write(UC_X86_REG_EAX, value & 0xffffffff)
        self.u.reg_write(UC_X86_REG_EIP, dest)

    def hook(self, u, address, size, unused):
        sp = u.reg_read(UC_X86_REG_ESP)
        if address == TICK:
            self.ret(value=self.tick)
        elif address == TABLE:
            ident = self.words(sp+4)[0]
            self.ret(1, BASE+0xc0000+ident*16)
        elif address == VALUE:
            ident = (u.reg_read(UC_X86_REG_ECX)-BASE-0xc0000)//16
            row, col = self.words(sp+4, 2)
            value = (e.PLAN['levelRequirements'][row] if ident == 13 else
                     e.PLAN['contribution'][row] if ident == 14 else
                     row+2 if 897 <= ident <= 910 else 1000000000)
            self.ret(2, value)
        elif address == 0x434c90:
            self.ret(1, PLAYER)
        elif address in (0x434cd0, 0x4299e0, 0x451a00, 0x452a90):
            self.ret()
        elif address in (0x427aa0, 0x412e20):
            self.ret(1)
        elif address == r.REFRESH:
            self.calls.append(address)
            self.put(PLAYER+0x194, self.words(PLAYER+0x34)[0])
            if self.corrupt_refresh:
                self.put(PLAYER+0x38, 1)
                self.corrupt_refresh = False
            self.ret()
        elif address == 0x450fb0:
            self.ret(4)
        elif address == 0x4456d0:
            self.ret(3)
        elif address == r.LEVEL_UP:
            self.calls.append(address)  # Execute the actual original function, including additive bonuses.

    def kill(self):
        self.u.mem_write(e.HOOK, b'\xe9'+struct.pack('<i', XP_STUB-e.HOOK-5)+b'\x90'*3)
        self.put(STACK, STOP, MONSTER, 0, 0)
        self.u.reg_write(UC_X86_REG_ESP, STACK)
        self.u.reg_write(UC_X86_REG_ECX, CONTROL)
        self.u.emu_start(0x4134a0, STOP, count=100000)
        assert self.u.reg_read(UC_X86_REG_EIP) == STOP

    def rewind(self, target=78, current=79):
        self.u.mem_write(BASE, r.make_request(BASE, target, current))
        self.put(BASE+r.DATA, 1, PLAYER, MAP, 0)
        self.u.reg_write(UC_X86_REG_ESP, STACK)
        self.u.reg_write(UC_X86_REG_ECX, PLAYER)
        self.u.emu_start(BASE, r.HOOK+len(r.ORIGINAL), count=100000)


class ExperienceTests(unittest.TestCase):
    def test_native_fingerprints_and_complete_instruction_boundary(self):
        if not IMAGE:
            self.skipTest('Original EXE fixture required')
        self.assertEqual(IMAGE[e.HOOK-0x400000:e.HOOK-0x400000+8], e.ORIGINAL)
        for span in e.PLAN['verified']:
            a = span['address']-0x400000
            self.assertEqual(hashlib.sha256(IMAGE[a:a+span['length']]).hexdigest(), span['sha256'])

    def test_multiplier_validation(self):
        for value in (0, -1, 1001, True, 1.5, '100', None):
            with self.assertRaises(ValueError):
                e.multiplier(value)
        for value in (1, 2, 1000):
            self.assertEqual(e.multiplier(value), value)

    def test_event_can_be_disabled_while_player_is_dead_or_unloaded(self):
        event = e.ExperienceEvent()
        game = Mock()
        game.state.side_effect = RuntimeError('No living character')
        event.game, event.base, event.factor = game, BASE, 1000
        try:
            with patch.object(event, '_alive'), patch.object(event, 'start'), patch.object(event, 'info', return_value={}):
                event.set(1)
                game.state.assert_not_called()
                self.assertEqual(event.factor, 1)
                self.assertEqual(game.write.call_args.args[0], BASE+e.DATA+4)
                with self.assertRaises(RuntimeError):
                    event.set(2)
        finally:
            event.game = None

    def stub(self, raw=111, current=12, factor=1000, age=1, mode=0):
        f = Machine(factor)
        f.tick = (1000+age) & 0xffffffff
        f.put(e.GAME_MODE, mode)
        f.put(PLAYER+0xe8, current)
        u = f.u
        for reg, value in ((UC_X86_REG_EAX, current), (UC_X86_REG_EDX, raw),
                           (UC_X86_REG_ESI, PLAYER), (UC_X86_REG_EBX, 123),
                           (UC_X86_REG_ECX, 567), (UC_X86_REG_EDI, 789), (UC_X86_REG_EBP, 987)):
            u.reg_write(reg, value)
        u.reg_write(UC_X86_REG_ESP, STACK)
        u.emu_start(XP_STUB, e.HOOK+len(e.ORIGINAL), count=1000)
        self.assertEqual(f.words(XP_STUB+e.DATA)[0], 0)
        for reg, value in ((UC_X86_REG_EDX, raw), (UC_X86_REG_ESI, PLAYER),
                           (UC_X86_REG_EBX, 123), (UC_X86_REG_ECX, 567),
                           (UC_X86_REG_EDI, 789), (UC_X86_REG_EBP, 987), (UC_X86_REG_ESP, STACK)):
            self.assertEqual(u.reg_read(reg), value)
        self.assertEqual(u.reg_read(UC_X86_REG_EAX), f.words(PLAYER+0xe8)[0])
        return f

    def test_exact_raw_scale_and_counter(self):
        for factor in (1, 2, 100, 1000):
            f = self.stub(factor=factor)
            self.assertEqual(f.words(PLAYER+0xe8)[0], 12+111*factor)
            self.assertEqual(f.words(XP_STUB+e.DATA+12, 3), (1, 111, 111*factor))

    def test_expired_lease_multiplayer_and_invalid_factor_replay_native(self):
        for kwargs in ({'age':5001}, {'mode':1}, {'factor':0}, {'factor':1001}):
            self.assertEqual(self.stub(**kwargs).words(PLAYER+0xe8)[0], 123)
        self.assertEqual(self.stub(age=-1).words(PLAYER+0xe8)[0], 123)

    def test_large_gain_and_addition_do_not_wrap(self):
        for raw, current in ((10000000, 12), (1000000, 4000000000)):
            f = self.stub(raw=raw, current=current)
            self.assertEqual(f.words(PLAYER+0xe8)[0], 0xffffffff)
            self.assertEqual(f.words(XP_STUB+e.DATA+20)[0], 0xffffffff-current)
        self.assertEqual(self.stub(raw=0).words(PLAYER+0xe8)[0], 12)

    @unittest.skipUnless(IMAGE, 'Original EXE fixture required')
    def test_full_native_kill_scales_xp_but_counts_exactly_one_kill(self):
        for factor in (1, 2, 100):
            f = Machine(factor)
            f.kill()
            self.assertEqual(f.words(PLAYER+0xe8)[0], 100000*factor)
            self.assertEqual(f.words(PLAYER+0xc0)[0], 1)
            self.assertEqual(f.words(PLAYER+0x1550)[0], 1)
            self.assertEqual(f.words(PLAYER+0x34)[0], 79)

    @unittest.skipUnless(IMAGE, 'Original EXE fixture required')
    def test_native_damage_contribution_precedes_multiplier(self):
        f = Machine(2)
        f.put(MONSTER+0x288, 75)  # 50% contribution -> 50,000 raw -> 100,000 awarded.
        f.kill()
        self.assertEqual(f.words(PLAYER+0xe8)[0], 100000)
        self.assertEqual(f.words(XP_STUB+e.DATA+16, 2), (50000, 100000))

    def test_lower_level_preserves_all_base_stats_and_clears_xp_once(self):
        f = Machine()
        before = bytes(f.u.mem_read(PLAYER+r.STAT_OFFSET, r.STAT_BYTES))
        f.put(PLAYER+0xe8, 54321)
        f.rewind()
        self.assertEqual(f.words(BASE+r.DATA)[0], 3)
        self.assertEqual(f.words(PLAYER+0x34)[0], 78)
        self.assertEqual(f.words(PLAYER+0x194)[0], 78)
        self.assertEqual(f.words(PLAYER+0xe8)[0], 0)
        self.assertEqual(bytes(f.u.mem_read(PLAYER+r.STAT_OFFSET, r.STAT_BYTES)), before)
        self.assertEqual(f.calls, [r.REFRESH])
        f.u.reg_write(UC_X86_REG_ESP, STACK)
        f.u.reg_write(UC_X86_REG_ECX, PLAYER)
        f.u.emu_start(BASE, r.HOOK+len(r.ORIGINAL), count=10000)
        self.assertEqual(f.calls, [r.REFRESH])  # A completed request cannot run twice.

    def test_rewind_rejects_stale_level_dead_player_and_changed_map(self):
        for address, value in ((PLAYER+0x34, 80), (PLAYER+0x1a4, 0), (PLAYER+0x458, MAP+4), (e.GAME_MODE, 1)):
            f = Machine()
            f.put(address, value)
            f.rewind()
            self.assertEqual(f.words(BASE+r.DATA)[0], 4)
            self.assertEqual(f.calls, [])

    def test_unexpected_stat_change_rolls_back_level_exp_and_stats(self):
        f = Machine()
        f.corrupt_refresh = True
        f.put(PLAYER+0xe8, 54321)
        before = bytes(f.u.mem_read(PLAYER+r.STAT_OFFSET, r.STAT_BYTES))
        f.rewind()
        self.assertEqual(f.words(BASE+r.DATA)[0], 5)
        self.assertEqual(f.words(PLAYER+0x34)[0], 79)
        self.assertEqual(f.words(PLAYER+0xe8)[0], 54321)
        self.assertEqual(bytes(f.u.mem_read(PLAYER+r.STAT_OFFSET, r.STAT_BYTES)), before)

    @unittest.skipUnless(IMAGE, 'Original EXE fixture required')
    def test_relevel_uses_original_additive_bonus_path_again(self):
        f = Machine()
        before = f.words(PLAYER+0x38, 15)
        f.rewind()
        f.kill()  # Original 0x412fb0 executes; mocked table returns known bonus values.
        self.assertEqual(f.words(PLAYER+0x34)[0], 79)
        self.assertEqual(f.words(PLAYER+0xe8)[0], 0)
        self.assertEqual(f.calls.count(r.LEVEL_UP), 1)
        self.assertEqual(f.words(PLAYER+0x38)[0], before[0]+2)
        self.assertEqual(f.words(PLAYER+0x3c)[0], before[1]+3)
        self.assertEqual(f.words(PLAYER+0x40)[0], before[2]+4)
        f.rewind()
        f.kill()
        self.assertEqual(f.words(PLAYER+0x38)[0], before[0]+4)
        self.assertEqual(f.calls.count(r.LEVEL_UP), 2)

    def test_rewind_limits_and_conflicting_trainer_controls(self):
        for value in (0, 79, 80, 100, True, 78.5, '78', None):
            with self.assertRaises(ValueError):
                r.target_level(value, 79)
        self.assertEqual(r.target_level(78, 79), 78)
        for info in ({'active':['2196']}, {'frozen':['975']}, {'frozen':['972']}):
            with self.assertRaises(ValueError):
                r.validate_controls(info)
        r.validate_controls({'active':['234'], 'frozen':[]})


if __name__ == '__main__':
    unittest.main()
