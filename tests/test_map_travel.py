"""Verify map requests and execute native entrance lookup for all 209 scenarios."""
import hashlib
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest

from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
from unicorn.x86_const import *

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'app'))
import map_travel as m
from test_mob_spawn import IMAGE

BASE = 0x30000000
PLAYER = BASE+0x10000
MAP = BASE+0x20000
POINTS = BASE+0x30000
STACK = BASE+0xf0000


class Machine:
    def __init__(self):
        self.u = Uc(UC_ARCH_X86, UC_MODE_32)
        self.u.mem_map(0x400000, 0x100000)
        self.u.mem_map(BASE, 0x100000)
        if IMAGE:
            self.u.mem_write(0x400000, IMAGE)
        self.put(m.GAME_MODE, 0)
        self.put(0x482cd4, 0xffffffff)
        self.put(0x48d778, 0xffffffff)
        self.put(PLAYER+0x1a4, 999)
        self.put(PLAYER+0x458, MAP)

    def put(self, address, *values):
        self.u.mem_write(address, struct.pack('<'+'I'*len(values), *(v & 0xffffffff for v in values)))

    def words(self, address, count=1):
        return struct.unpack('<'+'I'*count, self.u.mem_read(address, count*4))

    def request(self, sid='00000000', same=True, reset=True):
        self.u.mem_write(BASE, m.make_request(BASE, sid, m.MAPS[sid]['entry']))
        if reset:
            self.put(BASE+m.DATA, 1, PLAYER, MAP)
        self.u.reg_write(UC_X86_REG_ECX, PLAYER if same else PLAYER+4)
        self.u.reg_write(UC_X86_REG_ESP, STACK)
        self.u.emu_start(BASE, m.HOOK+len(m.ORIGINAL), count=10000)

    def enter(self, target, slot, same_zone):
        for i, row in enumerate(target['points']):
            ident, x, y, direction = row
            self.put(POINTS+i*16, ident, direction, x, y)
        self.put(MAP+0x34, 4, POINTS)
        self.put(PLAYER+4, slot)
        self.put(STACK+0x140, target['entry'])
        self.put(STACK+0x14c, 0xffffffff)
        self.u.reg_write(UC_X86_REG_ESP, STACK)
        self.u.reg_write(UC_X86_REG_ESI, MAP)
        self.u.reg_write(UC_X86_REG_EBX, PLAYER)
        start, stop = (0x4262b7, 0x42631a) if same_zone else (0x426e80, 0x427380)
        self.u.emu_start(start, stop, count=10000)
        assert self.u.reg_read(UC_X86_REG_EIP) == stop


def synthetic_mct(points):
    raw = b'MCED DATA v0000\x1a'+bytes(260+260+12+256)
    raw += struct.pack('<7i', *([0]*7))  # three preload lists + four empty entity categories
    raw += struct.pack('<i', len(points))
    raw += b''.join(struct.pack('<4i', *p) for p in points)
    return raw+bytes(12)


class MapTravelTests(unittest.TestCase):
    def test_live_identity_keeps_negative_world_coordinates_signed(self):
        game = SimpleNamespace(pid=42,
            state=lambda:dict(pid=42,player=PLAYER,map=MAP,x=0xffffff85,y=0xfffffe38),
            words=lambda address: (0,) if address==PLAYER+4 else (3,),
            read=lambda address,size: struct.pack('<2i',-123,-456) if address==PLAYER+0x2e0 else b'Hero\0'+bytes(7))
        result=m.identity(game)
        self.assertEqual((result['x'],result['y']),(-123,-456))
        self.assertEqual(result['sid'],'00000003')
        self.assertEqual(result['slot'],0)

    def test_only_scenarios_with_verified_entrances_are_allowed(self):
        self.assertEqual(len(m.MAPS), 209)
        for sid in ('f00_03', 'd03_11_00', 'd03_12_00', '00000002', '../00000000', 0, None, True):
            with self.assertRaises(ValueError):
                m.selection(sid)
        self.assertEqual(m.selection('00000000')['entry'], 0)
        self.assertEqual(m.selection('03240000')['entry'], 50)
        self.assertEqual(m.selection('04130000')['entry'], 50)

    def test_request_publishes_exact_native_fields_once(self):
        f = Machine()
        f.request('03240000')
        self.assertEqual(f.words(BASE+m.DATA)[0], 3)
        self.assertEqual(f.words(PLAYER+0x43c, 3), (1, 3240000, 50))
        self.assertEqual(f.words(PLAYER+0x454)[0], 0xffffffff)
        f.put(PLAYER+0x440, 999)
        f.request('03240000', reset=False)
        self.assertEqual(f.words(PLAYER+0x440)[0], 999)

    def test_bound_character_only_and_failed_preconditions_do_not_queue(self):
        f = Machine()
        f.request(same=False)
        self.assertEqual(f.words(BASE+m.DATA)[0], 1)
        self.assertEqual(f.words(PLAYER+0x43c)[0], 0)
        for address, value in ((m.GAME_MODE, 1), (PLAYER+0x1a4, 0), (PLAYER+0x458, MAP+4),
                               (PLAYER+0x43c, 1), (0x48ce34, 1), (0x482cd4, 123), (0x48d778, 300)):
            f = Machine()
            f.put(address, value)
            f.request()
            self.assertEqual(f.words(BASE+m.DATA)[0], 4)
            self.assertEqual(f.words(PLAYER+0x440)[0], 0)
        f = Machine()
        f.put(PLAYER+0x2dc, 1)  # This is the action/movement state, not the held-item pointer.
        f.request()
        self.assertEqual(f.words(BASE+m.DATA)[0], 3)

    def test_unreviewed_entry_numbers_are_rejected(self):
        with self.assertRaises(ValueError):
            m.make_request(BASE, '00000000', 50)
        with self.assertRaises(ValueError):
            m.make_request(BASE, '03240000', 0)

    @unittest.skipUnless(IMAGE, 'Original EXE fixture required')
    def test_verified_native_blocks_match_original_executable(self):
        for span in m.PLAN['verified']:
            a = span['address']-0x400000
            self.assertEqual(hashlib.sha256(IMAGE[a:a+span['length']]).hexdigest(), span['sha256'])

    @unittest.skipUnless(IMAGE, 'Original EXE fixture required')
    def test_all_209_entrances_resolve_through_native_same_and_cross_zone_code(self):
        f = Machine()
        for target in m.MAPS.values():
            for slot in range(4):
                for same_zone in (False, True):
                    f.enter(target, slot, same_zone)
                    point = target['points'][slot]
                    actual = struct.unpack('<2i', f.u.mem_read(PLAYER+0x2e0, 8))
                    self.assertEqual(actual, tuple(point[1:3]), (target['id'], slot, same_zone))
                    self.assertEqual(f.words(PLAYER+0x31c)[0], point[3])

    def test_mct_parser_validates_entrances_and_truncation(self):
        points = m.MAPS['03240000']['points']
        raw = synthetic_mct(points)
        self.assertEqual(m.points_from_mct(raw), points)
        for length in (0, 15, 16, 803, len(raw)-1):
            with self.assertRaises(ValueError):
                m.points_from_mct(raw[:length])
        with self.assertRaises(ValueError):
            m.points_from_mct(raw+b'unknown')

    def test_translation_changes_can_preserve_entrances_but_changed_points_are_rejected(self):
        target = dict(m.MAPS['03240000'], mctSHA256='not-the-test-file-hash')
        with tempfile.TemporaryDirectory() as folder:
            game = SimpleNamespace(path=Path(folder)/'ShadowFlare.exe')
            scenario = Path(folder)/'Scenario'/target['id']
            scenario.mkdir(parents=True)
            (scenario/'Scenario.Scs').write_bytes(b'ScenaScriptV000\0')
            raw = synthetic_mct(target['points'])
            (scenario/'Scenario.Mct').write_bytes(raw)
            m.validate_destination(game, target)
            points = [list(p) for p in target['points']]
            points[0][1] += 1
            (scenario/'Scenario.Mct').write_bytes(synthetic_mct(points))
            with self.assertRaises(ValueError):
                m.validate_destination(game, target)

    def test_all_source_files_match_the_built_entrance_plan(self):
        source = ROOT.parent/'shadowflare-drop-analysis/input/Scenario'
        if not source.is_dir():
            self.skipTest('Original MCT fixtures required')
        for target in m.MAPS.values():
            raw = (source/target['id']/'Scenario.Mct').read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), target['mctSHA256'])
            points = {p[0]: p for p in m.points_from_mct(raw)}
            self.assertEqual([points[target['entry']*4+i] for i in range(4)], target['points'])


if __name__ == '__main__':
    unittest.main()
