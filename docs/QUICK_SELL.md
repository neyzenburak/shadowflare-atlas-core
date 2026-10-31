# Right-click selling: v1

With merchant and inventory open, right-clicking a backpack item invokes the
original sale operation. **Live controls > Right-click to sell** provides toggles
and a count of sales completed since enabling. The companion enables it on
startup; `--no-quick-sell` starts with it off. Restarting a running companion
preserves the enabled/disabled choice.

## Operation

- The inventory right-click call at `0x445a7b` is wrapped. The original
  `0x44a6f0` handler runs if the merchant is closed, the backpack is hidden,
  an item is on the cursor or the target is not a backpack cell. Multiplayer
  does not use the shortcut.
- Original `0x447290` hit-testing locates the cell. The existing widescreen
  coordinate transform is used; no fixed screen resolution is assumed.
- `0x466b00` finds the actual record of a multi-cell item. The item is temporarily
  detached from the backpack list and placed in the game's held-item field.
- Original merchant sale branch `0x44831c` runs with its own stack frame.
  Sellability, normal/sale prices, gold insertion and capacity checks,
  notification and item deletion remain its original calls.
- If the game rejects the sale, the original list link and empty cursor are
  restored. Item coordinates and list order remain intact. Right-clicking an
  unsellable purse or unpriced item does not fall through to consuming it.

The merchant's own right-click buying handler `0x44b020` is unchanged.
Equipped items, special-item slots and the Mine holder are outside this shortcut.
Prices are not fixed; trainer price changes still pass through the original
function. The game EXE file is not modified.

## Lifecycle

Before installation, the call and relevant original function bytes are checked
and saves backed up. Local manifest `app/quick-sell-sessions/` records the old/new
call, code allocation and backup. Disabling first restores the original call;
allocation is freed only when no call remains in flight and no thread instruction
pointer lies inside it. The feature reconnects automatically to a new game
process. It targets verified single-player v2.004.

## Verification

Ten Unicorn tests in `tests/test_quick_sell.py` execute the local original EXE's
sale branch, list operations, hit-testing, gold insertion and deletion. Shortcut
inventory/gold/deletion/notification results are compared with direct drag-to-
sell results. The price table, notification queue and test-object creation/
deletion use test dependencies.

Coverage includes widths 640/1024/1366/1920, every cell of multi-cell items,
filling a purse and creating another, exact rollback when a full backpack
cannot accept gold, unsellable items/gold, original zero-sale-price behavior,
empty cells, modal windows, fallback with merchant/backpack closed or an item
held, multiplayer, equipment/special areas and repeated clicks. Stack balance
and callee-saved registers are also checked.

During live validation on 23 October 2026, the player confirmed right-click
selling. Initially 13 sales completed, gold rose from 8,737 to 10,002 and no
item remained on the cursor. UI toggles were verified; after re-enabling,
four more items were sold. The ten new tests and existing 33 performance tests
passed. Automated tests cover both accepted and rejected sales; live validation
used the player's current merchant.
