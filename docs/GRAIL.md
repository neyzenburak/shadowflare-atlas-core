# Premium Chronicle: v2

The grail covers 457 distinct catalogue identities with `rarity == 2`.
Different identities sharing a name remain separate entries. Game/save files
are not modified. With the local companion running, successful ground-to-
backpack transfers by the single-player character are observed.

Of these, 456 Premiums have a positive nominal chance in the standard pools
used by monsters. Gamble Boots is absent from those pools; its card is marked
and available through **Not in standard monster pools**. This does not rule
out quest or special reward routes.

## What the evidence means

- **Picked up from the ground:** Tracking observed the completed backpack
  insertion. SQLite stores the first pickup time, region and later pickup
  count. Selling, dropping or leaving the character does not erase that history.
- **Owned before tracking:** Seen in equipment/backpack on the first save scan,
  or equipment/backpack/storage on the first live connection to this character.
  This cannot establish the date, source monster or whether it was purchased.
- **Marked manually:** The user pressed Found it to record a remembered find.
  The mark can be removed without deleting automatic pickup evidence.
- **Not recorded:** The journal has no evidence. This does not prove the item
  never dropped. A save's item list cannot reconstruct all previously sold items.

Progress is the union of the three evidence types; each item counts once.
Picking up an already-owned or manually marked item adds its date and pickup
count without increasing the collection total again. First-find notifications
appear in Atlas; in-game tooltips and identification are not changed.

## Save decoding and character separation

`ShadowFlare0005` is decoded read-only. The clear character header is followed
by body size, XOR key and signed-byte checksum. The body is first decoded with
the 256-byte native inverse table, then XOR is applied. Checksum, size and the
repeated character header are validated. Eleven equipment fields and main
backpack records are read according to their size fields, without guessing
by searching for item IDs. An incomplete or inconsistent read during autosave
is ignored until the next scan.

Profile identity derives from game folder, save slot and character name.
Different saves with the same name remain separate. Reusing the same slot and
name for a new character shares the old profile: no verified persistent
character GUID is available to distinguish that recreation automatically.
Changing the slot or name creates a separate profile. The active save path
comes from the game's own active file object, not a similar-name match.

## Native observation

`grail_native.py` places reversible detours at three verified entry points:

1. `0x449ef0`: Ground pickup. Once world object ID, single-player mode, empty
   cursor and Premium quality are verified, pending item/character identities
   are stored privately. The original function runs. Failure clears the pending
   mark. A failed second click while holding another item does not corrupt the
   previous pending pickup.
2. `0x466bc0`: Original list-insertion instructions run unchanged. An event is
   published only when the inserted object matches the pending ground pickup
   and the destination is exactly this character's main backpack. Holding it
   on the cursor with inventory open does not count; later backpack placement
   does. Direct insertion into storage does not count.
3. `0x465640`: Deleting the pending cursor object clears its mark. A reused
   memory address therefore cannot turn a merchant purchase into a pickup.

Purchases, rewards inserted directly into the backpack, failed full-backpack
clicks and non-Premium items do not create pickup records. An item manually
created and **dropped on the ground** does count when subsequently collected;
the system does not prove which enemy originally generated an item.

Small native records are completed before publishing their sequence number.
Python persists them approximately every 250 ms. The 2,048-event ring is not
a loot/item cap. If the consumer falls behind far enough to overrun it, the
lost-event count is persisted and displayed. Tracking cannot backfill time
when the companion was closed. Shutdown restores entry points, drains completed
events and frees private memory once in-flight calls and instruction pointers
are safe.

Right-click selling verifies the same deletion function. `Grail.original_bytes`
provides the original view only when its own installed detour bytes still match
exactly; QuickSell's SHA-256 checks use that view. Foreign patches are not hidden.

## Storage and interface

v2 publishes a shared, character-bound native table for the drop filter and
red beams. Browsing another profile does not change that table. The actual
local player, name and save path are verified on every read, so stale data
cannot carry across a character change. Updates are published only when data
changes, briefly suspending the game. Pending pickup events are drained again
during publication so an unpersisted successful pickup mark is not lost.

Immediately after writing to the journal ring, the successful backpack-insertion
hook also marks the shared table entry as found. Cursor holding, failed pickups,
storage and merchant operations do not set that mark. The duplicate filter and
red spirals on other ground copies can therefore update after the same game call.
Shared grail memory is not freed before dependent drop/beam hooks are disabled.

Data lives in `app/grail-data/chronicle.sqlite3`. Operations use transactions,
and DB connections close after each operation. This folder, save backups and
native session manifests are excluded from Git and distribution ZIPs.
**Download journal** exports the selected profile's evidence fields as JSON.
Artwork uses existing local Atlas icons. The UI provides search, category/status
filters, level/name/date sorting, 48-card pages, character selection and automatic
following of the active character.

## Verification

Fourteen grail tests execute the original EXE's actual pickup branch, slot
search, insertion and deletion code in Unicorn. UI/sound and map-extraction
dependencies use test doubles. Coverage includes success, full backpack,
cursor placement, a failed second click, merchant/reward exclusions, reused
object addresses, storage, ring wraparound, selling alongside QuickSell and
original SHA checks. Pure-data tests cover profile separation, persistence,
duplicate counts, removal of manual marks, save decoding and corrupt-save rejection.

Live validation on 23 October 2026 recorded Bloody No-Mask moving from ground
to backpack, including time, region, identity and one pickup. Because the item
was already owned, the collection total did not rise. Character switching,
search, marking/unmarking and actual JSON download were verified in the UI.
The journal survived a companion restart.

A later first pickup of Knuckle Breaker recorded Cold Ruins and its pickup time,
raised progress to 3/457 and displayed a real first-find notification. Both
recollecting an owned item and recording/notifying a new entry were verified live.
