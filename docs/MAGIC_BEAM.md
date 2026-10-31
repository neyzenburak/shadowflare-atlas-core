# High-roll Magic beam

The compact **Valuable Magic beams** card independently toggles blue native
world-render beacons. Premium gold beacons retain their own switch. Selection
does not hide or modify any items, identify them, change their rolls or record
them in the Premium grail. The setting persists in local
`app/magic-beam-settings.json`, excluded from Git and the distribution ZIP.

133 Magic templates qualify as candidates: Angel, Saint Angel, Conqueror and
Legendary. For each variable, nonnegative additional stat, the actual instance
value must satisfy `min + ceil(80 * (max-min) / 100) <= value <= max`.
Every such stat must pass independently; there is no average score. Fixed
bonuses and negative penalties do not participate. Dedicated HP/MP, recovery,
running and chant utility prefixes are excluded. A variable chant bonus within
an eligible Angel package is included. Each exact item template supplies its
own bounds, including the Legendary Beast Boots evasion exception.

`app/magic_beam_rules.py` stores the derived 133 ID/category rules and 512
instance-field thresholds from the verified original Item.Ibn analysis. The
source analysis is local at `../shadowflare-drop-analysis/magic-affix-work`.
The native roll generator writes the actual bonus into the minimum-word field
before identification, so no identification or tooltip extraction is required.

The existing main-thread render hook scans the current ground list once.
Candidate lookup uses a sorted binary table. Eligible visible Magic items
produce one additive blue DIB packet each; ordinary loot generates no packets.
There is no artificial beacon/item cap. Both immutable 16-frame atlases together
use about 2 MiB; they remain allocated until game exit after detachment because
queued native packets may still reference them. Native viewport clipping and
camera projection are shared with the Premium effect. Panels/HUD draw above
the beams; building/tree height-aware occlusion is not implemented.

Native tests verify all 133 templates at their exact thresholds and each of 512
individual failing-stat cases with all other stats maximized. Unknown/lower
prefixes and uninitialized rolls fail. The item memory remains byte-identical,
including unidentified flags. Gold/blue toggle combinations are independent.
Original renderer tests also verify viewport/camera tracking, packet flags,
register/stack preservation, ground-list changes and additive blending.
