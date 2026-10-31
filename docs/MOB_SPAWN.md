# Spawning monsters with AI disabled

Select a monster and appearance/loot variant in Drop Atlas. Enter a whole
number from 1 to 2000 in **Quantity** below its preview, then press **Spawn
selected monster nearby**. Return to the game; its update loop completes the
request. Every monster in one batch overlaps at the same world coordinates.

**Remove my last spawned group** removes only the last request's monsters,
without producing loot or EXP. Normal monsters are untouched. Missing members
of an already-partially-removed group are skipped. Associated living/interaction
records are cleaned up while existing quest flags are preserved.

Passing a 2000-instance code test does not mean the game renders that batch
smoothly. A live batch of 2000 Dread Raptor caused severe slowdown. After removing
the last group, a five-second measurement showed 29.8 FPS with no frames over
50 ms. Start small; 2000 is not a performance guarantee.

The initial point is nearby walkable ground with enough room for the monster's
actual body. Later instances share that point. Each has a separate identity,
HP, hit registration and death. The selected scenario variant supplies HP,
level, appearance, part colors and loot group. Death uses current loot rules,
including the active multiplier and grail filter.

Living spawned monsters do not walk or attack. Damage, targeting, death
animation, loot and cleanup follow original game paths. Other monsters' AI is
unchanged. These spawns are not persistent edits to the map.

## Implementation

- `mob_spawn.py` validates the Atlas record against its original `Scenario.Mct`
  entry. The 79-field source properties are converted into the original loader's
  72-field layout.
- Active part masks and RGB multipliers are preserved. Source animation-array
  length is separate from the model's actual part count.
- The original object factory, shared constructor, property loader and name
  loader run on the main game thread. Each instance receives a new unused ID.
- Records are appended in order to the live enemy table and three interaction
  flags. Every field of existing quest/monster records is preserved. Arrays
  use the game's own allocator and are freed by its original map cleanup.
- Only the new instance's virtual-table update function changes. Idle drawing
  and animation remain active; three attack-producing paths in the idle
  animation are removed. At zero HP, the original death update resumes.
- Activity field `+34c` is zero; otherwise the original projectile code skips
  a visible target. `+34` is the source label height, keeping the name/HP bar
  above the monster instead of at its feet.
- The temporary request detour is removed and freed. The shared passive code
  page remains until game exit so instance return addresses stay valid. A
  restarted companion reuses that page after verification.

Quantity bounds are enforced in HTML and on the server. Partial requests
report the actual created count and are not retried automatically. Session
records live under `app/mob-spawn-sessions/`, excluded from Git and ZIPs.

## Verification

`tests/test_mob_spawn.py` executes x86 in Unicorn: factory-call order, terrain
rejection, ID collisions, interaction-record preservation, original property
conversion, part colors, passive updates, death transition and 2000 distinct
instances at one point. With the original EXE fixture, plan code fingerprints
are checked too.
