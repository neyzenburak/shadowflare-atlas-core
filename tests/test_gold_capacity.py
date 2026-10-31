"""Run actual native gold merge, merchant, spending and list selection paths."""
import struct, unittest
from test_quick_sell import Fixture, IMAGE, PLAYER, BASE
from unicorn.x86_const import UC_X86_REG_ECX
from gold_capacity import LIMIT, make_image, patches, original_bytes

GOLD_BASE = 0x35000000


class GoldFixture(Fixture):
    def __init__(self, items, **kwargs):
        super().__init__(items, **kwargs)
        self.u.mem_map(GOLD_BASE, 4096)
        self.u.mem_write(GOLD_BASE, make_image(GOLD_BASE))
        # Native price getter can query an optional bonus-cost table. Its absence
        # is a valid native branch; all gold values still execute the real getter.
        self.put(0x47353c, GOLD_BASE+0x300)
        self.u.mem_write(GOLD_BASE+0x300, bytes.fromhex('31c0c20400'))
        for at, before, after in patches(GOLD_BASE):
            assert bytes(self.u.mem_read(at, len(before))) == before, hex(at)
            self.u.mem_write(at, after)

    def intercept(self, u, address, size, user):
        if address == 0x4661c0:
            obj = u.reg_read(UC_X86_REG_ECX)
            if self.words(obj+0xc)[0] == 4 and self.words(obj+0x14)[0] == 0:
                return
        super().intercept(u, address, size, user)

    def add(self, amount, width=9, height=4):
        return self.call(0x466e10, (amount, width, height), PLAYER+0x514)

    def spend(self, amount):
        return self.call(0x466da0, (amount,), PLAYER+0x514)


@unittest.skipIf(IMAGE is None, 'Local original EXE fixture required')
class GoldTests(unittest.TestCase):
    def test_inventory_total_with_equipment_potions_mine_and_gold_interleaved(self):
        items=[dict(kind=1,subtype=80000001,value=123456),
               dict(kind=4,subtype=0,x=1,value=10000),
               dict(kind=3,subtype=1,x=2,value=999),
               dict(kind=4,subtype=1,x=3,value=987),
               dict(kind=4,subtype=0,x=4,value=2147480000),
               dict(kind=0,subtype=72,x=5,value=777)]
        f=GoldFixture(items)
        for _ in range(20):
            self.assertEqual(f.call(0x466d70,(),PLAYER+0x514),LIMIT)
        self.assertEqual(f.spend(20000),1)
        self.assertEqual(f.gold(),2147470000)
        self.assertEqual(len(f.snapshot()),5)

    def test_total_of_inventory_with_no_gold_and_empty_inventory(self):
        for items in ([],[dict(kind=1),dict(kind=3,x=1),dict(kind=4,subtype=1,x=2)]):
            f=GoldFixture(items)
            self.assertEqual(f.call(0x466d70,(),PLAYER+0x514),0)

    def test_native_save_payload_and_load_preserve_full_signed_integer(self):
        for amount in (10001, 1000000000, LIMIT):
            f = GoldFixture([dict(kind=4, subtype=0, value=amount)])
            record = PLAYER+0x20000
            self.assertEqual(f.call(0x466a90, (record,), f.items[0]), 1)
            self.assertEqual(f.words(record)[0], amount)
            clone = f.create(kind=4, subtype=0)
            self.assertEqual(f.call(0x466a70, (record,), clone), 1)
            self.assertEqual(f.words(clone+0x40)[0], amount)
            self.assertEqual(f.call(0x4661c0, (0,), clone), amount)

    def test_known_resident_patches_normalize_for_merchant_hash_verification(self):
        f = GoldFixture([])
        class Reader:
            def read(self, a, n): return bytes(f.u.mem_read(a, n))
        self.assertEqual(original_bytes(Reader(), 0x466e10, 0x16c), IMAGE[0x66e10:0x66f7c])

    def test_sale_merges_past_ten_thousand_in_the_same_purse(self):
        f = GoldFixture([dict(sell=25000), dict(kind=4, subtype=0, x=1, value=9990)])
        f.call(BASE)
        self.assertEqual(f.gold(), 34990)
        self.assertEqual(len(f.snapshot()), 1)

    def test_empty_slots_capacity_does_not_overflow(self):
        for amount in (10001, 1000000000, LIMIT):
            f = GoldFixture([])
            self.assertEqual(f.add(amount), 1)
            self.assertEqual(f.gold(), amount)
            self.assertEqual(len(f.snapshot()), 1)

    def test_near_limit_merge_preserves_all_excess_in_another_purse(self):
        f = GoldFixture([dict(kind=4, subtype=0, value=LIMIT-10)])
        self.assertEqual(f.add(25), 1)
        self.assertEqual([r[3] for r in f.snapshot()], [15, LIMIT])
        self.assertEqual(f.gold(), LIMIT+15)

    def test_insufficient_capacity_is_atomic(self):
        f = GoldFixture([dict(kind=4, subtype=0, value=LIMIT-10)])
        before = f.snapshot()
        self.assertEqual(f.add(11, 1, 1), 0)
        self.assertEqual(f.snapshot(), before)
        self.assertEqual(f.add(10, 1, 1), 1)
        self.assertEqual(f.gold(), LIMIT)

    def test_spending_finds_a_purse_above_old_sentinel_and_at_new_maximum(self):
        for amount in (10001, 1000000000, LIMIT):
            f = GoldFixture([dict(kind=4, subtype=0, value=amount)])
            self.assertEqual(f.spend(10001), 1)
            self.assertEqual(f.gold(), amount-10001)
            if amount == 10001: self.assertEqual(len(f.freed), 1)

    def test_spending_combines_large_purses_without_signed_total_wrap(self):
        f = GoldFixture([dict(kind=4, subtype=0, value=LIMIT),
                         dict(kind=4, subtype=0, x=1, value=1000000000)])
        self.assertEqual(f.call(0x466d70, (), PLAYER+0x514), LIMIT)
        self.assertEqual(f.spend(LIMIT), 1)
        self.assertEqual(f.gold(), 1000000000)

    def test_full_purse_does_not_accept_more_or_disappear(self):
        f = GoldFixture([dict(kind=4, subtype=0, value=LIMIT)])
        before = f.snapshot()
        self.assertEqual(f.add(1, 1, 1), 0)
        self.assertEqual(f.snapshot(), before)
        self.assertEqual(f.call(0x466cd0, (), PLAYER+0x514), 0)


if __name__ == '__main__': unittest.main()
