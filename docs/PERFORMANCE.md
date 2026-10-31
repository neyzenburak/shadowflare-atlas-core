# Heavy loot: 23 October 2026

The final recorded implementation is rendering performance v11. During a
20-second walk among dense loot piles, it measured **29.65 FPS** while keeping
all 2,293 ground items. The player confirmed that the previous movement stutter
had improved.

| Walking measurement | Result |
|---|---:|
| Completed frames / duration | 593 / 20.0004 s |
| Median recorded frame interval | 33.19 ms |
| 95th / 99th percentile | 37.55 / 41.94 ms |
| Longest recorded interval | 60.20 ms |
| Recorded intervals over 50 ms / 100 ms | 2 / 0 |

Measurement polls the game's completed-frame counter about every 2 ms without
suspending game threads. The 25 frame transitions missed between reads are
counted separately; their individual timings are not invented. FPS uses the
whole counter difference, while percentiles use only captured intervals.

## Comparison and limits

The first comparison used the same process, view and 2,293 items:

| Implementation | Frames | Duration | FPS |
|---|---:|---:|---:|
| Previous direct list sorting | 73 | 5.0003 s | 14.60 |
| Incremental relation table | 121 | 5.0039 s | 24.18 |
| Relation table + sequential overlap lookups | 121 | 5.0007 s | 24.20 |

The final addition gave no clear extra FPS in that initial view, but removed
repeated index searches. A later highlight-loop fix reached about 28 FPS. The
player reported that even attempting a pickup with a full backpack changed
smoothness, and standing at some dense positions still stuttered.

Intermediate v10 reached about 29 FPS while stationary, but movement still
stuttered. v11 removed cache rebuilds caused by visible-list size changes.
Its final measurement was taken while walking.

The final run used the same process and 2,293 items as earlier measurements,
but the character had moved, so it is not a camera-identical comparison with
the initial 14.60 FPS result. No fixed FPS across all densities or correction
of every game bug is claimed.

Thread-context sampling briefly suspends threads and can affect performance.
Passive counter recording does not; the two methods are kept separate. Local
diagnostics and memory images are not uploaded to GitHub.

## Why the final change was needed

Objects shifting position in the list made the previous cache treat many fixed
objects as changed. Matching only object memory addresses also failed live:
recreated render objects continually invalidated the cache. That attempt stayed
near 15 FPS and is not part of the final implementation.

v11 matches the complete sorting geometry `(left, top, right, bottom, group)`.
Hashing only finds candidates; all five values are compared exactly. Matching
old geometry reuses the same matrix cell. After unchanged inputs are matched,
unmatched inputs from the first pass take remaining free cells. Only rows and
columns involving changed geometry are recomputed. Original input order is
stored separately to preserve tie-breaking and cycle resolution.

Items with identical positions/geometries remain distinct inputs. There is
no visual merging, deletion or item/roll cap. Eight cache entries serve
different lists; that is not an item capacity limit. Allocations grow in
multiples of 256 records and remain allocated when the visible count shrinks.
Replacing an entry frees its old allocation.

Relations for geometry that leaves the original list during movement may remain
cached. An active-input bitmask includes only objects listed by the original
game in that frame when calculating degrees and order. The transposed relation
matrix computes active indegrees without rebuilding every relation when visible
list size changes. Newly visible objects do not force every old object to be
recomputed.

## Preserved behavior

- The relation matches the original DLL, including signed 32-bit addition
  behavior and choosing the first remaining object in dependency cycles.
- Original input order breaks equal-priority ties. Moved cells retain original
  flag/transparency reset behavior.
- No data is read through old render objects/cells. Current cells refresh on
  every call. A hash collision never counts as an approximate match.
- Allocation failure falls back to the previous full-list algorithm without
  deleting items.
- Sequential lookup applies only to four verified loops: three overlap loops
  and one object-highlight loop. Caller, list, head cell, stack frame and sort
  generation are checked; other calls use original Get.
- Highlight-loop code, accessed RGB functions and import targets are verified.
  The loop does not change object links or list membership.
- Shutdown restores calls, then frees cache allocations and the 8 KB code area
  once active calls finish.

Each cache allocation uses growing capacity `C`, `H = nextpow2(2*C)` and row
width `S = C/8`:

```text
48*C + 8*H + S + 2*C*S bytes
```

The first section holds metadata, result order, degrees, changed inputs and
original input order. The others contain exact geometry lookup, the active
input mask and forward/transposed relation bit tables.

## Verification and scope

Thirty-three tests execute the local original DLL in Unicorn as the oracle.
With the original EXE available, both highlight-loop versions also run, comparing
RGB changes, object links and final register values.

Coverage includes sorting, cell properties, bidirectional links, stack/register
layout, negative/overflowing coordinates, refreshed render cells/objects,
changed geometry/order, duplicate geometry, deliberate hash collisions,
visibility changes, excluding inactive geometry, capacity growth, return to a
previous list size, cache eviction and allocation failure. All 5,000 objects
remain without a capacity cap; 5,000 sequential lookups are verified for both
Get types. Different generations/lists and foreign callers use the original path.

Original EXE/DLL fixtures and personal game data stay local. Runtime requires
no assembler, Unicorn or additional pip dependency.
