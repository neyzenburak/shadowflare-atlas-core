# Proximity pickup and consumable stacks

The current controls use bridge protocol 17. The native module is version 8.
Runtime dependencies remain Python standard library only. Developer assembly
source: `tools/native/loot_qol.asm`; regenerate with `tools/build_loot_qol.py`.

## Pickup

Only the loaded local single-player actor runs the update hook, at `443496`.
The existing temporary drop request's first six bytes at `443490` remain
unchanged. Ground entity type 3 is traversed on the original game thread at
250 ms intervals, preserving the next cell before any native removal.

Eligible items are category 3 consumables and category 4 IDs 0/1 (Gold/Mine).
Quest items and equipment remain manual. A ring multiplier n, integer 1–20,
uses the same eight vertices as drop spreading: `(240n,0)`, `(170n,170n)`, etc.
The inclusion test is `170*max(abs(dx),abs(dy)) + 70*min(...) <= 40800*n`.

Read-only native space checks and matching nonfull stacks precede pickup.
Full bags and Mine reservoirs do not repeatedly remove/recreate their loot.
`449ef0` performs actual pickup, gold merging and Mine accounting. Inventory
open is temporarily cleared during this synchronous call to avoid taking
over the mouse cursor. A held item or quantity modal suspends auto pickup.
Failure restores the remaining object and original world coordinates using
native map insertion; partial gold/stack transfers retain the remainder.
New entity IDs created by recovery cannot be revisited by the same scan.

## Stacks

Only category 3's nonzero identified field, item `+1c`, carries quantity:
one unit uses native `1`, and counts 2–999 use `53540000 | count`.
This field is already serialized for inventory/hotbar/storage, so their
record sizes and native save checksums are unchanged. The current single
hotbar template continues to consume matching backpack items first.

Native identify-all `4670d0` calls the identified setter for every backpack
and warehouse item, including consumables. Version 5 also hooks that setter
at `4663c0`: ordinary 0/1 flag updates preserve valid category 3 count tags.
Equipment identification works normally; serialized tagged counts still
replace the value during loading. EAX, EDX and incoming flags retain the
original setter's behavior. A diagnostic counter reports preserved updates.

`466c40` decrements a counted item only at verified successful potion-use
and scenario-trade return addresses, including keyboard and mouse hotbar paths. Final units
use native unlink/destruction. Sales and other deletion callers remove the
whole stack. `4661c0` multiplies the original native unit price by count.

Scenario `DELETEITEM` (opcode `3b`, native handler `433ced`) removes a single
original item from the special-item pages or backpack before granting a trade
reward. Version 8 recognizes its two returns, `433d53` and `433d7b`, as one-unit
consumption for category 3 stacks. This prevents a card exchange from deleting
an entire stack of Vitality Source, Mental Source, Mandragora or Akebi Fruit.
Equipment, quest items and explicit whole-stack sales retain their behavior.
The tests execute the original interpreter and item lookup, including repeated
exchanges down to the last unit and the special-item-page path.

Closed-inventory pickup merges exact template IDs into backpack stacks.
Normal empty-slot insertion merges too; an explicitly split cursor item is
exempt once. Enabling stacks explicitly can normalize an existing bag once.
Saved preferences and helper restarts do not normalize split stacks again.

The inventory item's `465e52` epilogue queues the count through native
`405590` drawing, using original font and corrected draw coordinates.
The `445a40` dispatcher intercepts Shift + right-click only for counted
backpack consumables. Native hit testing `447290` supplies the actual slot,
including the wide-screen offset. `441ab0` opens the existing quantity modal.
At `443341`, a partial split allocates first, then transfers exactly the
requested quantity onto the cursor. A whole split unlinks the original.
Invalid quantity, missing source, held cursor and allocation failure leave
the source intact. The source must still belong to the backpack.

Ground consumable records lack the identified field. Their existing 16-byte
record stores a reserved template ID instead: `53000000 | (count<<7) |
(group<<4) | variant`. Factory entry `462d30` decodes only this reserved
category 3 namespace, constructs the normal template, then restores count.
Equipment, gold, Mine and uncounted consumables retain their original data.
Consequently, counted saves must be loaded with Atlas running. They are not
a standalone unmodified-game format extension.

## Lifecycle and verification

Opening the helper installs the known executable's verified hook bytes.
Turning merging off keeps existing counts usable. Closing the helper stops
pickup/merging but retains the small resident native handlers until game
exit; otherwise an unmodified consume could delete a whole counted item.
A local per-process manifest permits verified adoption after restart.
Upgrade code retains old allocations while native callers finish returning.
Save backups and session manifests are local, excluded from Git and ZIP.

The first live trial exposed an incorrect jump substitution at the native
inventory insertion CALL at `446ce2`. Crash capture showed a null item sent
to the linked-list insertion observer. Version 4 emits CALL there and has a
regression test entering that actual executable callsite with its real
stack layout. All other installed sites are entry/continuation jumps.

`tests/test_loot_qol.py` executes generated x86 against the original executable
in Unicorn. Tests cover exact template merging, 999 overflow, native prices,
one-unit consumption, final destruction, source membership, split allocation
failure, the native insertion callsite, split placement, native numeric prompt,
font coordinates, ground count encoding, relocation, all requested radius
boundaries, full-capacity preflight and failed partial transfer recovery.
Identify regressions execute native identify-all, then the real right-click
merchant sale branch on unrelated equipment; 10/5/4 consumable counts remain
unchanged. Identify followed by a hotbar consume leaves exactly nine of ten.
The authorized incident refund uses one counted native spawn, validates the
template and count on the ground, then resumes the prior pickup settings.
Live validation also confirmed the refunded ten-unit Tablet+ stack stayed at
ten in the backpack after NPC identify-all and right-click equipment sales;
the native preserved-update counter advanced. Other consumables were not
restored as part of that refund.

Version 6 updates the gold auto-pickup capacity preflight for the resident
2,147,483,647-purse patch; potion stack semantics remain unchanged. See
`docs/GOLD_CAPACITY.md`.
