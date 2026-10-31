# Ctrl + left-click teleport

Version 2 was verified in a running game on 24 October 2026: the player
confirmed teleporting to clear ground and rejecting a wall. The initial
version mistook the input type of a closed text window for an active panel;
v2 checks the actual window flags. A regression test covers that case.

Toggle it under **Live controls > Ctrl-click teleport**. The preference is
stored locally. In single-player mode, hold Ctrl and left-click the ground
with every game panel closed. Each press runs once; holding and dragging
does not trigger repeated teleports.

The original input handler runs while inventory, status, skill, map, merchant,
dialogue, quantity or story panels are active. HUD clicks, ordinary left-clicks
and right-clicks are preserved. Teleport does not run with an item on the cursor.

The destination uses the original camera offsets and `CalcWorldPos` conversion.
All live terrain cells covered by the character's foot rectangle are checked;
out-of-map and blocked cells are rejected. The movement collision routine
`0x4145b0` then checks scene objects and characters. The route between the
endpoints need not be clear; the destination must be valid to stand on.

On success, position changes, the original `0x44e960(1)` refreshes position
history, and `0x4542f0` clears the previous walking target. Movement state
returns to idle. The game's normal update handles the camera and character
rendering. A rejected destination does not move the character.

Only the call at `0x443571` is replaced; its original target is input handler
`0x441c00`. The verified five-byte call ends on an instruction boundary and
does not overlap stack or merchant shortcut patches. Routines are hash-checked.
Disabling restores the original call; allocated code is not freed until any
in-flight call finishes. EXE/DLL files are not modified.

`tests/test_ctrl_teleport.py` executes x86 code, including the original coordinate
conversion, position history, walking reset and collision routines. Coverage
includes four resolutions, negative coordinates, camera offsets, obstacles at
the character's edge, map boundaries, every panel flag, HUD, disabling and
held-button behavior. The original EXE and `RKC_RPGSCRN.dll` remain local fixtures.

## Saving without closing the game

Authenticated local `POST /api/live/save` runs the original `0x44b580` save
routine once on the selected character's game thread. The game stays open.
The completed file is verified by character name, level, size and checksum;
character files and map exploration masks are then copied to a local backup.
The previous save is also backed up before the operation. This uses the game's
own save format and current stack quantities rather than recreating that format.
