"""Undo only the recorded batch, preserving unrelated mobs and quest flags."""
import hashlib
import struct
import unittest

from test_mob_spawn import Machine,BASE,PLAYER,MAP,NODE,ENEMY,LIST,IMAGE
import mob_cleanup as c


def machine(count=1,missing=False):
    f=Machine();f.u.mem_write(BASE,c.make_request(BASE,count))
    f.u.mem_write(BASE+c.ERASE,c.erase_flag(BASE+c.ERASE))
    f.put(BASE+c.DATA,1,PLAYER,MAP,0,0,0)
    for i in range(count):f.put(BASE+c.RECORDS+i*12,123+i,ENEMY,0x476d98)
    f.put(ENEMY+0x5c,MAP);f.occupied=set() if missing else set(range(123,123+count))
    return f


class MobCleanupTests(unittest.TestCase):
    def test_verified_native_lookup_destruction_and_removal(self):
        if not IMAGE:self.skipTest('Original EXE fixture required')
        for a,n,digest in c.VERIFIED:
            self.assertEqual(hashlib.sha256(IMAGE[a-0x400000:a-0x400000+n]).hexdigest(),digest)
    def test_removes_only_matching_pointer_type_vtable_and_map(self):
        for field,value in ((NODE,5),(NODE+4,1),(NODE+8,ENEMY+4),
                            (ENEMY,0x12345678),(ENEMY+0x5c,MAP+4)):
            f=machine();f.put(field,value);f.run()
            self.assertEqual(f.words(BASE+c.DATA+12,3),(0,1,0))
            self.assertNotIn(0x429be0,f.calls)
        f=machine();f.run()
        self.assertEqual(f.words(BASE+c.DATA+12,2),(1,0))
        self.assertEqual(f.calls.count(0x429be0),1)
    def test_missing_entities_are_safe_and_do_not_require_dereferencing_old_pointer(self):
        f=machine(missing=True);f.put(BASE+c.RECORDS+4,0xdeadbeef);f.run()
        self.assertEqual(f.words(BASE+c.DATA+12,3),(0,1,0))
        self.assertNotIn(0x429be0,f.calls)
    def test_removes_four_owned_flags_while_preserving_quest_values_and_sort_order(self):
        for missing in (False,True):
            f=machine(missing=missing);control=MAP+0x400
            net=[(77,35,81),(100000123,1,0),(200000123,1,0),(250000000,42,29),(300000123,1,0)]
            f.put(control+0x18,len(net),LIST+0x100)
            f.put(LIST+0x100,*(v for row in net for v in row))
            f.put(control+8,2,LIST+0x300);f.put(LIST+0x300,123,1,0,999,63,88)
            f.run()
            self.assertEqual(f.words(BASE+c.DATA+20)[0],4)
            self.assertEqual(f.words(control+0x18)[0],2)
            self.assertEqual(f.words(LIST+0x100,6),(77,35,81,250000000,42,29))
            self.assertEqual(f.words(control+8)[0],1)
            self.assertEqual(f.words(LIST+0x300,3),(999,63,88))
    def test_cleanup_loop_accepts_full_2000_batch_without_death_or_loot_calls(self):
        f=machine(count=2000);f.run()
        self.assertEqual(f.words(BASE+c.DATA+12,2),(2000,0))
        self.assertEqual(f.calls.count(0x429be0),2000)
        self.assertNotIn(0x458f70,f.calls)
    def test_last_batch_selection_does_not_include_earlier_spawns(self):
        rows=[dict(pid=1,map=2,backup=b,identifier=i) for i,b in enumerate(('earlier','last','last'))]
        self.assertEqual(c.last_batch(rows,1,2),rows[1:])
        with self.assertRaises(ValueError):c.last_batch(rows,1,3)
        with self.assertRaises(ValueError):c.last_batch(rows,99,2)
        with self.assertRaises(ValueError):c.last_batch(rows+[rows[-1]],1,2)


if __name__=='__main__':unittest.main()
