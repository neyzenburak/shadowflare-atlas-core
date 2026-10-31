# EXP events and earning levels again

Under **Control Desk > EXP event**, the slider and number field accept ×1–1000.
**Apply** multiplies the raw EXP awarded to the character for monster kills;
**×1 > Disable** restores normal gains. This is independent of drop events.
Companion EXP, weapon/spell development, kill counters and quest rewards are
not multiplied. The initial multiplier is ×1.

The original level-up rule remains: at most one level per kill, with surplus
EXP reset on leveling up. The character's natural level cap is 100.

In **Lower level, keep stats**, enter a level below your current one and press
the button. The operation first saves current progress through the game's own
writer, verifies it and creates a backup. After returning to the game, the
level changes once and current EXP resets. Base stats, items, quests and
learned skills remain. At the next level-up, the game adds bonuses again from
its own class history and growth tables. For example, 79 → 78 → 79 grants
those bonuses again; Atlas does not write bonus amounts manually. The request
is rejected while level/EXP freezes or one-kill level-up are enabled.

Monster cards show **RAW EXP** for the selected variant at full damage
contribution, before multipliers. The extraction checked 18,788 placements and
1,496 variants. One Enemy Hole variant has 600 or 800 EXP depending on its
placement, so it displays 600–800. Other variants each have one value. When
damage contribution is shared, the game's contribution table applies before
the EXP multiplier.

## Native implementation

- ShadowFlare v2.004 player kill-EXP path: `0x4134a0`.
- Two complete instructions at `0x413579` (8 bytes) are temporarily redirected.
  At entry, EAX holds current EXP, EDX the calculated raw gain and ESI the local
  player. The multiplied total is written to player `+0xe8`; the rest of the
  function remains original. The next flag use in normal flow comes from its own CMP.
- At ×1, in multiplayer or after the five-second companion heartbeat expires,
  the exact original instructions run. Disabling removes the detour. During an
  active event, a 64-bit product and overflow checks prevent the 32-bit EXP
  counter from wrapping to zero.
- Scenario field 13 populates native monster `+0x17c`. Table 14 provides damage
  contribution; table 13 provides the EXP required for the next level.
- Lowering the level runs on the game thread through a one-shot request at the
  player update entry. Only `+0x34` and `+0xe8` change; original `0x450080`
  refreshes derived stats. Base stats at `+0x38..+0xbf` are compared before and
  after. Any difference restores previous stats, level and EXP. Player, map,
  living state and expected level are rechecked.
- Original level-up function `0x412fb0` first increases level, records class
  history, then **adds** table bonuses to base stats. No highest-level-ever
  check blocks repeating a level. That function is not modified.

`experience-plan.json` contains SHA-256 fingerprints for supported native blocks.
Developers can regenerate it with `python tools/build_experience_plan.py`; local
EXE/table/placement research dumps are required. The builder also updates local
`data.js` variants with EXP ranges from actual placements.

## Verification

`tests/test_experience.py` executes multipliers, heartbeat, multiplayer fallback,
overflow, ABI and level changes in an x86 emulator. With the original EXE fixture,
it runs real kill-EXP and level-up instructions, checking contribution-before-
multiplier order, one kill-counter increment, EXP reset and two repetitions of
79 → 78 → 79 bonuses. Only table and sound/UI dependencies use test doubles.
The Node control test checks polling preserves the multiplier draft, bounds,
character binding and display of the completed level request.

In the live 81 → 80 test, base stats remained byte-identical. After returning
to 81, HP increased 1,635 → 1,665, MP 1,435 → 1,465, Strength 434 → 438
and Attack 320 → 326. The native hook recorded 100,000 raw EXP becoming
100,000,000 at ×1000. The event was returned to ×1 afterward. Browser controls,
actual character level, the monster EXP card and toggles were verified with no
console errors.
