# Warrior special skills

Toggle the **Special skills** card in Control Desk; its preference is stored
locally. Skills work only for a living local Warrior (class 6) in single-player,
with game panels/story screens closed and no item on the cursor. Choose Omega
or Meteor. **Left Alt + right-click** starts one cast; Omega requires a monster
under the cursor. Right Alt is not used. Ordinary right-clicks, other classes,
skill selection and mana remain unchanged.

Another special cast cannot start during Omega flight or meteor/warhead descent.
As soon as meteors or warheads hit, a new cast becomes available; previous
flames and mushroom clouds independently finish their remaining three seconds.
Lingering ground effects do not call damage. Flight is cancelled if its target
dies or the map, character or class changes. A long chase has a 45-second
lifetime. Toggling cancels active flight. Changing the selected skill or surprise
mode also cancels the current visual cycle without undoing damage already dealt.

## Meteor shower and surprise mode

At cast time, living monsters in the actual game viewport are selected. This
uses the current `screen +0x10` view rectangle, `+0x40` camera offset and native
projection scale, with no hardcoded 1920×900 limit. A small body margin includes
monsters intersecting the viewport edge. NPCs, dead objects, monsters on other
maps and those far offscreen are excluded. Duplicate list links do not select
a target twice.

Each meteor/warhead binds to its monster's ID/pointer pair. Position is reread
during the 0.85-second descent to follow moving targets. Dead targets are not
replaced. After impact, flames or a mushroom cloud stay at the world impact
position for three seconds and move with the camera. Ground effects are separate
from flight objects: a new cast neither deletes older effects nor resets their
lifetimes. Map/class changes clear them.

Impact deals Attack ×3 once. Flames/clouds do not call additional damage, so
overlapping areas do not double it. Nearby visuals may be combined for drawing,
but damage is applied to every unique target separately. Native processing uses
batches of at most 64 records, rechecking type, ID, object pointer, living state
and map for each record. A record is marked consumed before its call; duplicates
within a batch are skipped. Python also deduplicates between batches.

## Routing and collision

`omega_path.py` performs A* in the game's actual isometric projection. The
eight-direction search includes the previous direction in its state, allowing
45- or 90-degree turns. Straight segments merge. Short connections to the
start/target obey the same angle rule. A moving target is followed, and a
recomputed path inherits the flying beam's current direction.

Terrain comes from the live map's collision cells. Current rectangles of doors
and other solid scene objects are included. Every full edge is sampled; clear
endpoints alone are insufficient. During travel, small point batches are checked
again on the original game thread through terrain bounds and collision path
`0x4145b0`. The original routine decides whether an object is open/passable.

A point rejected by the game is fed back into routing, which searches around
that obstacle instead of repeatedly trying the same invalid route and cancelling
after two failures. Segment/circle intersection checks keep tiny new obstacles
from being missed between samples. With no route, the beam advances to the
first obstacle and fades with smoke.

Omega no longer uses a fixed pixel speed. A one-second arrival deadline is set
at launch; progress uses remaining distance and time. Rerouting does not reset
the deadline. Moving-target searches run at most about once every 0.28 seconds.
The final light trail fades over 0.15 seconds. The head never advances without
successful collision validation; actual frame rate, final target correction or
routing around a new obstacle can extend travel time.

## Damage and identity

The game's input path is temporarily hooked at `0x441cf2`. A living monster
from the original target list is bound by ID, pointer, map and source character.
Current displayed Attack (`player +0x1b4`), rather than base Attack, is read
and multiplied by three.

Damage is applied only when the beam arrives. Target identity is resolved
again through original `0x4299e0`; type, pointer, living state and distance are
revalidated. NPCs, stale objects, other characters/maps cannot be damaged.
Ordinary target loss does not transfer the shot to another monster.

Original monster-hit routine `0x459690` is called. Packet source type is 0 and
source ID is the player's slot. `packet +0x94 = 1` selects the original fixed-
damage path in `0x412a40`, returning `packet +0x10` without random multipliers
or defense reduction. Damage is therefore exactly Attack ×3. Low HP clamps to
zero normally. The game handles HP, death, EXP and drops.

## Rendering and lifetime

At drawing branch `0x41ebfd`, original flags and both branch outcomes are
preserved. The neon-red body, bright core, tip sparks and collision smoke use
the game's own additive DIB packets through `RKC_UPDIB::SetPacket`.
`RKC_RPGSCRN::CalcRealPos` and current camera offset anchor the effect inside
the game rather than a desktop overlay. Offscreen segments are clipped.

Omega uses 24 small DIBs; meteors, explosions, flames, warheads and mushroom
clouds use another 52. `special_effects.py` generates them procedurally without
new runtime dependencies. Each visual has its own size/anchor entry. Drawing
uses three 4,096-record buffers and a native reader-buffer protocol, preventing
Python from overwriting coordinates currently read by the game. Queued packets
can retain DIB references, so allocated image atlases are kept after companion
shutdown; Windows reclaims them when the game exits.

Input and drawing hooks check a 2.5-second companion heartbeat. Both hooks are
restored during shutdown. No persistent EXE change is made. Their hook points
are separate from Ctrl-click teleport and Premium/Magic item beams.

## Building and verification

Runtime uses only the Python standard library. Inspectable assembly lives in
`tools/omega_input.asm` and `tools/omega_render.asm`.
`python tools/build_omega_beam_plan.py` generates `app/omega-beam-plan.json`
with developer dependencies. Native fingerprints and DLL rendering functions
are checked before attaching.

`tests/test_omega_beam.py` executes actual x86 at two loading addresses,
original DLL projection and the fixed-damage fast path in an emulator. It checks
class/key/panel gates, target identity, one hit only at arrival, collision-call
ABI, original drawing branches, closed rooms, obstacle feedback and turns toward
moving targets. Frontend tests exercise actual toggles and disabled controls
with an older companion.

In the 29 October 2026 live test, Attack 887 reduced target HP from 10,000 to
7,339, 4,678 and 2,017: each complete hit dealt 2,661. The next hit killed it
normally. The player saw the red beam and confirmed that the routing fix reached
a target through a corridor where the beam had previously faded. Final moving-
target records contained no turn greater than 90 degrees.

Later that day, the player verified the faster Omega, moving-target meteors,
three-second flames and surprise-mode mushroom clouds. The final nuclear cast
hit all six visible targets; each target with sufficient HP took 2,661 damage.
Of 248 tests, one environment-dependent case was skipped and the rest passed.
Coverage included native batch damage, one hit per duplicate target, viewport
selection, target tracking, three-second visuals and skill/checkbox UI events.

Recast tests accept a second native Alt + right-click while the first ground
effect is still visible. Each effect's lifetime starts at its own impact.
Both meteor and surprise modes also verify that an old cloud expiring does
not release a newer descent's cast lock, ground effects never add damage,
and map/class changes clear effects.
