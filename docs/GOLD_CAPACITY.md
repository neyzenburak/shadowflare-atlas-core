# Large gold purses

Bridge protocol 10 installs `gold_capacity.py` automatically. Each native
category 4 / template 0 purse holds 0–2,147,483,647 gold in its existing signed
32-bit value field. No currency is granted and existing purses are not forcibly
combined. Drag one purse onto another to consolidate them. Native Shift + right
click still splits an amount through the original numeric prompt.

The patch covers backpack and warehouse merging, closed-inventory pickup,
merchant income, nonfull-purse selection and minimum-purse selection for
spending. The old 10,001 minimum-search sentinel also needed replacement;
otherwise purchases would stop finding purses above 10,000. Empty-slot and
existing-purse capacity sums saturate instead of wrapping signed integers.
Remainders stay in another purse, or a failed capacity admission leaves the
inventory unchanged. Auto-pickup's read-only preflight uses the new limit.

The native aggregate-money API itself returns a signed 32-bit value. If several
purses together exceed 2,147,483,647, its displayed/queried total saturates at
that number. The individual purse amounts remain intact and spending debits the
real list, including across multiple purses. This does not introduce a 64-bit
total-money UI. Ordinary monster/death gold-drop packet sizes remain original.

Gold retains the original save value field and record layout. Run Atlas when
loading and using large purses: the original game's 10k merge logic cannot
safely operate on them. Closing/restarting the helper leaves verified resident
gold code until the game exits. A manifest permits adoption on helper restart.
The EXE/save files are not patched; a save backup precedes first installation.

Eleven native Unicorn tests execute original merchant, capacity, insertion,
selection and spending code: merging past 10k, a full INT_MAX purse, 36 empty
slots, partial room, exact rejection, excess preservation and multiple purses
whose true combined value exceeds the native aggregate API. Maximum-value
spending also exercises the replaced minimum-search sentinel.
The original gold save-payload writer and loader round-trip INT_MAX unchanged;
the original gold price getter returns the amount without multiplication wrap.
The auto-pickup module separately tests large-purse preflight in a full bag.

## Version 2: inventory-render crash

The initial total-money hook overwrote `466d8a..466d92`, including a native
branch destination at `466d8d`. Non-gold inventory objects could branch into the
middle of that detour. The crash capture located the invalid read at `466d8e`.
Version 2 hooks the total function's entry at `466d70` and provides its entire
small traversal; none of the old loop's internal branches are now overwritten.
Regression cases contain interleaved equipment, consumables, Mine and gold,
plus no-gold/empty inventories and repeated calls. The captured actual backpack
also replays with the correct 64,509 result. Current save checksum and bytes
match the last pre-patch backup; no restore or save edits were performed.

Live version-2 validation on 24 October 2026: the player confirmed that opening
the inventory and combining purses work. The read-only inventory snapshot then
showed one purse containing 334,509 gold and the v2 capacity handler active.
