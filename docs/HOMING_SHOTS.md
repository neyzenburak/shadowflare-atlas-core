# Homing arrows and stones

Use **Live controls > Homing arrows and stones > Enable / Disable**. Normal
weapon shots from the crossbow, bowgun, bow and slingshot families follow a
directly targeted monster through Flame Strike's own steering code. The local
preference is stored in `app/homing-settings.json`; new installations default to off.

Every projectile tracks independently in single and multiple shots. Weapon
shot count, spread angles, appearance, damage data, speed, lifetime and collision
checks are preserved. Only new projectiles change; those already airborne
finish their current flight. Firing at the ground without targeting a monster
uses the original flight. If the target dies or disappears, native Flame Strike
behavior stops tracking without selecting another target. Original hit/wall
checks remain; this feature does not guarantee a hit.

## Native implementation

`0x42a777` is the normal weapon effect's projectile-creation call. Original
`CALL 0x429dd0` is redirected to a short wrapper preserving the call ABI,
EFLAGS and all general-purpose registers. It only applies in single-player
to the local character's normal weapon effects (0–7), on the same map and
with a living monster target. Spell effects and enemy shots are excluded.

Original `0x42a300` prepares the projectile packet. Before the original
constructor copies it, only two fields change:

| Packet field | Object field | Value | Purpose |
|---|---|---|---|
| `+0x08` | `+0xd8` | 1 | Per-frame target tracking |
| `+0x0c` | `+0xdc` | 20 | Flame Strike turn speed |

Flame Strike uses these settings along `0x42d6e0` / `0x42da24`. Actual projectile
movement remains in `0x45e1e0`. Native target IDs, target loss, angle normalization
and `0x4140a0` movement math are unchanged. No raw target memory pointer is retained.

The native source for double shots is marked as fixed position (0), while the
other shots use player position (1). Both are validated by source character ID,
preventing two-arrow weapons from being excluded accidentally.

The verified EXE and SHA-256 values of seven code regions are checked. Saves
are backed up before the first attachment. Game EXE/DLL files and save contents
are not modified. Shutdown restores the call; wrapper memory is kept until
in-flight calls finish.

## Verification

`tests/test_homing_shots.py` contains eight tests executing the original x86
code inside Unicorn:

- 1–7 projectiles and the double-shot source in both real weapon firing loops.
- Exact visual, damage, speed and other packet-field preservation across eight
  normal effect types; only the two steering fields change.
- Turning toward a moving target through real native movement, angle and x87 math.
- Fallback for dead/lost targets, NPCs, other characters/maps and multiplayer.
- Preservation of registers, flags, stack and original constructor arguments.

On 24 October 2026, **116/116 project tests passed**. Live memory samples of a
three-shot weapon were also collected: 82 distinct projectiles appeared in
60 samples; seven observed in multiple samples changed direction during flight.
These are sampled observations, not total hit or homing-projectile counts.

Local API: `POST /api/live/homing-shots`, body `{"enabled":true/false}`.
Existing localhost Origin/Host and session-token checks apply. State appears
under `homingShots`. The read-only diagnostic sample is limited to fixed fields:
`POST /api/live/diagnostic {"homingShots":true}`.
