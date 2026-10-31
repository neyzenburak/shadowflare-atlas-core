# Rain and widescreen

Interface fix v7 adapts rain to the active resolution. No separate toggle is
needed; it is enabled with **Widescreen > Apply fixes**. The existing rain is
used: map weather, color, speed, angle and line length remain unchanged.
Maps without rain do not gain it.

Original routine `0x41fe20` spawns drops in `rand() % 1000 - 180` and frees a
node when its Y position reaches 479. Widescreen enlarged the world without
changing those constants. Since drops slope left, ones born to the right of
the screen must enter the visible area while falling.

The new horizontal margin is `ceil(180 * height / 480)`, spawn width is
`screen width + 2 * margin`, and deletion threshold is `height - 1`.
At 640×480 all three match the original values. At 1920×900 the margin is
338 and spawn width 2596. Spawn count scales by that width divided by 1000;
fractional remainder carries into the next frame to preserve density.
Height already affects drop lifetime and does not multiply spawn count again.

The patch wraps the routine at its entry. Because the original loop rereads
the intensity field for every spawn, that field is scaled for the call and
restored before returning. Both arguments, return value and callee-saved
registers are preserved. Turning rain off stops new spawns; existing drops
expire normally. Game EXE/DLL files are not modified.

Restoration verifies code bytes. If a rain call is still active, its small
return-code allocation remains until game exit, preventing return into freed memory.

`tests/test_rain_fix.py` executes original x86 in Unicorn:

- Identical random sequence, nodes and draw packets at 640×480.
- Wind margin and bottom-right coverage at six resolutions from 640×480 to 7680×4320.
- Exact fractional spawn totals over 1000 frames, stopping and intensity changes.
- Survival past the old lower boundary and deletion at the new one.
- Actual bottom-right line drawing at 1920×900 with original `RKC_UPDIB` and `RKC_DIB`.
- Complete instruction boundaries with no branches jumping inside new patches.
- Completion when disabled during a call, and freeing idle allocations.

EXE/DLL fixtures are not distributed. Set `SHADOWFLARE_FIXTURE_DIR` to the
folder containing your local copies.
