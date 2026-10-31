# Premium loot beam v3

Gold beacons select ground equipment with category 0–2 and native rarity 2.
Version 2 adds independently toggled high-roll Magic blue beacons; see
`docs/MAGIC_BEAM.md`. Both colors share the existing single render hook.
Version 3 adds three rotating red helices around the gold pillar for Premium
templates missing from the loaded character's Grail. It is independent of the
drop event and its duplicate filter. Existing ground items qualify too.
The shared character-bound Grail lookup selects a third immutable frame atlas;
there is still only one packet per eligible item. A completed pickup changes
the shared found flag immediately. Other copies on the ground then use gold.
Unknown/stale character policies fall back to gold without a false red marker.
The main-thread hook at `0041EBF6` runs after native world packets are queued,
before HUD/panels. It reads the current local player's map ground list directly;
no retained item pointers, item mutations or extra hit-test objects are used.
Pickup, map changes and character changes therefore remove obsolete beacons on
the next normal world frame. Only single player is enabled.

The exact original seven-byte comparison is replayed, preserving its flags for
the following conditional branch. The hook preserves all registers and stack.
The original EXE hash, patch bytes, native packet method and projection method
are verified. The packet method's one SEH relocation is normalized before SHA
verification. The existing resolution, grail, sale and render fixes use separate
patch sites and remain active.

Sixteen immutable, procedurally generated 96×224 BGR DIB frames contain an amber
pillar, elliptic ground halo and five rising motes. These are code-generated
effect pixels; no game art or new pip dependency is required. Native projection
(`RKC_RPGSCRN::CalcRealPos`) and the current screen manager scroll offsets place
the effect at the real item position. Animation uses the native tick counter.

One custom-DIB packet per visible Premium is sent through native
`RKC_UPDIB::SetPacket`, in the current double-buffer block and world VScreen.
Flags `0x1022` select custom DIB, additive blend and the native world viewport.
The underlying `RKC_DIB::TransferToDIBEx` adds source RGB with saturation; black
source pixels leave the scene intact. The beam is a visible world marker above
the completed world sprites, with panels/HUD drawn above it. It does not attempt
height-aware occlusion by buildings or trees or cast light onto world geometry.

The current ground list is scanned once per world frame; normal and ineligible
Magic items generate no effect packets. Offscreen rectangles are skipped. Neither
the item count nor Premium count is capped. This is not a claim of constant FPS
at arbitrary Premium density.

The HTML panel offers enable/disable and the current visible effect count.
Loopback mutation uses the existing Origin and token checks. The option is
preserved on authenticated helper restart. `--no-premium-beam` disables it at
startup. Disabling flips the native flag and adds no more gold packets. Detaching
restores original code; all three immutable atlases (about 3 MiB) remain until the game
exits, because native double-buffered packets may still reference its pixels.
Re-enabling within a helper session reuses the same allocation.

## Validation — 23 October 2026

Ten tests execute actual x86 hook code with the original projection DLL and
native packet/DIB routines. They cover register/stack/flag preservation,
rarity/category selection, camera translation, viewport culling, missing map or
player, multiplayer exclusion, disable, ground-list changes, 500 ordinary items,
DIB headers/animation, real additive color output and clipped/offscreen draws.
Set `SHADOWFLARE_BEAM_FIXTURE_DIR` to a local directory containing original
`RKC_RPGSCRN.dll`, `RKC_UPDIB.dll`, `RKC_DIB.dll` to run all native cases.

Live validation at 1920×900: the player dropped a Premium armor item, the native
counter reported one visible beacon and a screenshot showed the gold pillar
and halo at the item's position after camera movement. The player confirmed
the beam was visible and disappeared when the item was picked back up. The
HTML panel's off/on buttons were also exercised. This live check used one
Premium beacon, not a synthetic mass-Premium scene.

## Validation — 25 October 2026

The full suite ran 180 tests successfully (one unrelated fixture was skipped).
New native cases cover same-ID/different-category keys, save/player/name
binding, missing vs found colors, successful insertion vs held/failed pickup,
×1 duplicate filtering, and unchanged roll counts without forced rerolls.
The player confirmed red helices on existing loot. The renderer reported 88
visible Premium beacons, four missing. Levantine, Styx's Frozen Armor and
Stromgald Bowgun were then collected and recorded as first finds; the missing
beacon count fell as those items left the ground.
