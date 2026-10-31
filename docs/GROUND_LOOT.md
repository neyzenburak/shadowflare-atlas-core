# Ground loot visibility and selling

The **White / Magic loot** card in Control Desk provides two separate actions:

- **Hide / Show:** Temporarily hide ground Plain/Magic weapons, armor and
  accessories. Premiums, consumables, Mine, gold and special items stay visible.
  Hidden equipment does not block mouse selection; showing it again restores
  the same item. Magic beams follow the visibility setting too.
- **Sell white and Magic ground loot:** Convert all eligible equipment on the
  current map into gold at the game's unidentified sale value. With **Save before
  operation** selected, current progress is saved and the Save folder backed up.
  Gold is left at the character's feet for manual pickup. Selling is permanent.

The save checkbox defaults to off. Its choice is remembered in the browser,
independently of map travel's save option. With it off, Atlas skips its preliminary
save/backup step. Other features' saving behavior, such as lowering the level,
is unaffected.

## Native implementation

`458a1c` begins preparing a ground item's sprite packet. Hiding skips this packet
for categories 0–2 / qualities 0–1 and continues at shared update `458cc3`.
Position, animation physics, linked lists and save data are unchanged. Inventory
and merchant rendering use separate functions. Native mouse queries obtain
world IDs from draw packets, so an object without a packet does not become a
selection target in front of a Premium.

Sales use the existing one-shot game-thread request mechanism at `443490`.
Each candidate is resolved again by world ID through `4299e0`, with pointer,
map, category and quality revalidated. Its identification flag is temporarily
set to 0 within the same native call; `4661c0(1)` calculates the merchant value,
then the original flag is restored. Premiums are excluded before that calculation.

The total uses 64 bits. **All** required gold objects are allocated through the
game factory before equipment is deleted. Allocation failure frees the reserved
objects and leaves the equipment in place. Native `427a00` detaches from the
world; `465640` deletes from the item bank. Gold equal to successful sales is
placed as normal gold objects through `466440` / `4663e0` / `427970`.
Each bag holds at most 2,147,483,647; any remainder creates additional bags.

The known grail detour at item deletion is accounted for through its verified
original-byte reader; foreign changes fail SHA validation. Auto-pickup pauses
throughout the request. Its previous setting resumes after publishing the
sale-gold exclusion table. An uncertain result or failure to publish exclusions
disables auto-pickup.

## Manual collection of sale gold

`sale-gold-ledger.json` records local character/save identity, map, position and
amount. Native auto-pickup reads a separate table; the first match binds a
record to a live world ID. A different object reusing an address does not inherit
the exclusion. Position/amount matching can rebind it in a new game process.
The native gold save format is unchanged. The ledger remains local and is
excluded from GitHub and distribution ZIPs.

## Verification

`tests/test_ground_loot.py` executes generated x86 against the original EXE in
Unicorn: draw packets and mouse IDs, equivalent physics, native sale values,
identification-flag preservation, Premium/consumable exclusions, rollback on
factory failure, totals exceeding 32 bits, a 1,500-item pile and manual-only
sale gold. Beam tests and actual frontend control tests also cover this option.
Assembly sources are `tools/native/ground_loot.asm` and `tools/native/loot_qol.asm`;
build them with `tools/build_ground_loot.py` and `tools/build_loot_qol.py`.
The running companion needs no additional pip package.

`test_operation_save.py` verifies both operations call the actual save path
when requested, skip it when disabled, and never save during read-only diagnostics.
