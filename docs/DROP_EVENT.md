# Drop events with a Premium-only option

In the live drop event, **Apply to Premiums only** takes effect together with
the multiplier when you press **Apply multiplier**. The choice is stored locally;
when upgrading a running companion, the launcher transfers both settings.
When the multiplier and grail filter are disabled, the original loot call is restored.

## Roll behavior

- At ×100, the original loot function runs exactly 100 times.
- All results of the first normal roll are preserved. If a boss has multiple
  attempts in its normal roll, all are preserved. With the grail duplicate
  filter below enabled, already-found Premiums are excluded from this roll too.
- With Premium-only enabled, the next 99 rolls accept only Premium equipment
  in categories 0/1/2 with actual item quality 2.
- Non-Premium results are discarded without rerolling. Empty results remain
  empty; a bonus roll does not guarantee a Premium.
- Magic/Plain equipment, Tablet/Meat/Capsule and other consumables do not benefit
  from the multiplier. The existing ×1 exceptions for Mine and gold remain.
- With Premium-only disabled, the previous event behavior applies: all loot
  except Mine and gold benefits from the multiplier.

Existing ground items are untouched. Accepted new items use the existing
terrain-aware octagonal spreading. No item or roll cap is introduced.

## Implementation

**Exclude Premiums already found by this character** is an independent duplicate
filter. It covers all monster loot results, including the first normal roll,
and remains active at ×1. Recorded pickups, equipment owned before tracking
and manual **Found it** marks count as found, matching the grail UI. Exact
category/template identities are checked; different-level records sharing a
name are not merged. Manual item drops, merchants and quest rewards are outside
this monster filter. Rejected items are not replaced by other Premiums.

The sorted table from `grail_policy.py` lives in private grail memory. Each native
read verifies the local player address, 12 name bytes and 14 save-path bytes.
A character change or unready table prevents using the previous character's
records. The successful-pickup hook marks the entry during the same game call;
Python persists the events in the journal. State includes `excludeFound`,
`filterActive`, `grailReady`, `grailProfile`, `foundKeys` and `duplicatesSkipped`.
Cache keys include the policy and found identities. Suppressed items have zero
Atlas probability, and source/map lists refresh accordingly.

`drop_event.py` v5 only replaces the enemy-death call at `0x45a01c`. A verified
copy of the loot function receives per-death context through a hidden stack
argument. Multiplier and Premium-only settings are read together from one aligned
DWORD, so changing settings cannot alter the policy of an in-progress death.

Bonus Mine/gold results are skipped before creation, as before. Other bonus
results pass once through the original `0x462d30` factory, preserving native
random property generation. Premium checks read the actual object's category
at `+0xc` and quality at `+0x18`, rather than guessing from names or IDs.
Before entering the map, a rejected object is removed through the verified
bank deletion function `0x465640(Item**)`. Accepted Premiums return to the
original placement/insertion path. During verification, the known grail observer
detour at that same deletion entry is represented by its verified original bytes;
the observer remains installed at runtime. Foreign patches are not overwritten.

API: `POST /api/live/event` with `{"multiplier":100,"premiumOnly":true,"excludeFound":true}`.
Omitted options retain their current values. State includes `premiumOnly`,
`bonusNonPremiumsSkipped` and `bonusPremiumsAccepted`. The last two counters
cover bonus rolls only, excluding the first normal roll.

Atlas displays `1 - (1-p)^multiplier` for Premiums and the normal probability
for other items. Expected quantities follow the same per-item rule. Item,
monster and map caches include this option alongside the multiplier.

## Verification

`python -m unittest discover -s tests -p test_drop_event.py -v` runs 13 Unicorn
tests against the original EXE. Game-code tests skip when the local copyrighted
EXE fixture is absent. Coverage includes rejecting Plain/Magic/consumables,
all three Premium categories, every normal boss attempt, ×1000, failed creation,
object deletion, settings changes during a roll, multiplayer/lease fallback,
and stack/register preservation.

`node tests/test_event_model.cjs` checks probabilities, map caches and the actual
`live.js` control flow. Polling preserves an unapplied checkbox draft; a failed
request does not change Atlas probabilities.

In the live test on 25 October 2026, seven monster deaths completed 700 rolls
without closing the process. Bonus rolls accepted 10 Premiums and rejected
405 non-Premium items and 5 Mine. These are results of that test, not a guarantee
of Premium drops. The character was saved through the original game routine
and backed up before applying the change.

In the v5 live test later that day, five new monsters completed 5,000 rolls;
14 previously found Premium results were rejected before entering the world.
Red grail beams were also verified on existing ground items without new kills.
