# Monster sorting and map travel

## Monster catalogue

Selecting **Monsters** adds three sorting choices:

- Raw EXP: highest first
- Raw EXP: lowest first
- Episode and map progression

EXP sorting uses the highest raw EXP across all variants of a monster. Cards
show the minimum–maximum range; opening a card selects the highest-EXP variant.
Zero EXP is valid, and unknown values sort last. Ties use the first guide
encounter, then name order.

Progression sorting uses guide Episode and map `order` fields in `SF_WORLD.maps`.
The earliest map containing the monster determines its position. Its card
shows that Episode/map and opens the variant from that location. This is not
an assertion of story activation order for monsters enabled later by quest
conditions. Text search preserves the chosen order. Switching back to items
restores item sorting choices.

## Live map transitions

Select a region in **Maps**, then press **Teleport to entry point**.
**Save before operation** defaults to off. Its browser preference is independent
of ground selling's save option. If selected, the game's own writer saves
current progress, verifies it and creates a backup. Otherwise Atlas skips that
preliminary step. Returning to the game runs the original area transition.
Target scenario, character and entry point are verified. The game loads the
camera, companion and map objects. Selecting the current map also returns to
that map's entrance.

There are 209 supported scenario maps. The normal starting entry group is 0.
Maps `03240000` and `04130000` have no group 0, so the first complete entry
group, 50, is used: point IDs 200–203 in the file. All four player slots are
verified. The button is disabled for scenario-less previews `f00_03`,
`d03_11_00` and `d03_12_00`; these resources have no playable scenario or entry.

A transition cannot start while holding an item. This checks held-item pointer
`0x48ce34`; player `+0x2dc` is movement/action state and is not used for this
check. Requests require a living, unchanged local character in single-player.
Another pending transition or an open story screen causes rejection.

## Native path and tests

A temporary one-shot request at the player update entry writes the same four
fields as original `CHANGESCENARIO` (`0x43218f..0x4321ba`) on the game thread:
`+0x440` target scenario, `+0x444` entry group, `+0x454 = -1` player selector,
and finally `+0x43c = 1` to mark the transition pending.
Original control loop `0x41e825` loads through `0x41c9a0` and `0x426200`.
The companion does not call the loader from its own thread, write scenario
files or manually change quest/waypoint unlock flags.

The native entry ID is `entry group × 4 + player slot`. `0x427930` finds it in
the scenario point table. Original reader `0x429467..0x4294e3` loads points
from `Scenario.Mct`, converting file records `[id,x,y,direction]` into memory
layout `[id,direction,x,y]`. Both same-area and cross-area entry paths were
inspected and executed separately. No persistent EXE modification is made.

`map-travel-plan.json` contains all 209 scenario IDs, four starting points and
native function fingerprints. If an installed MCT differs, it is fully parsed
and its actual entries compared exactly; translated text alone is not a
blocker. Developers can regenerate the plan from research fixtures with
`python tools/build_map_travel_plan.py`.

`test_map_travel.py` executes 209 × 4 × 2 = 1,672 entry resolutions using
original EXE instructions in an x86 emulator. It also tests every source MCT,
identity binding, one-shot execution, corrupt files, held items and competing
requests. Node tests cover EXP/guide order, correct variants, search, unknown
values and actual live-control events.

## Live verification

On 26 October 2026, Berini Village → Remote Town completed at `[89898, 2811]`,
followed by Remote Town → Immortal Remains at `[95281, -5532]`. Both positions
matched the actual target-file entrances exactly, and each operation restored
the temporary entry hook. Negative Y was also verified as a signed integer.
The player separately confirmed appearing at the map entrance in the game.
