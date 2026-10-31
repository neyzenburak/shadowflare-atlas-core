# Misc / Special / Scenario Items

The fifth Atlas tab works offline. It does not connect to the game or change
quests or saves. Its map buttons open the actual game maps inside Atlas. To
travel in the running game, use **Teleport to entry point** in **Maps**.

## Coverage

- 39 entries: ten consumables and 29 special items in `4:99000000–99000028`.
- 84 fixed placements for 15 item types across 12 maps.
- Four card trades, linking to ingredient locations and the NPC's map.
- Four scenario rewards created after defeating their guardian groups.
- Dorojan's antidote dialogue and Barshival's relic delivery package.
- Special-item sources in standard monster tables and available NPC turn-in branches.
- White Cloth, Red Thread and Silver Needle have unverified acquisition routes.
  Mrs. Morris's branch that accepts these items is shown separately. This does
  not establish that the items are unused or were removed during development.

Search covers item, NPC and map names, including the map where a trade
ingredient is found. Filters select source and item types. Different acquisition
routes for the same item have separate steps. Atlas item panels link back to
this guide.

## Verified triggers

Card dialogue requires **completion of quest 32, Stop Jurg**. Carrying the same
card changes the available dialogue branch. A trade consumes one ingredient;
the card appears at the NPC's **current** X + 200 / Y position. Markers show
starting positions, and NPCs may move.

| Card | NPC | NPC map | Ingredient | Fixed ingredient location |
|---|---|---|---|---|
| Jack | Oscar | Town of Losmans | Mandragora | Lunafuld Beach |
| Queen | Quina | Ponse, Village of Dwarves | Akebi Fruit | Gungstonwald |
| King | Buzzed | A Town of Antalusia | Vitality Source | Ruins of Carn |
| Joker | Barmera | Town of Calado | Mental Source | Coldea Cave |

| Scenario reward | Map | Guardians to defeat |
|---|---|---|
| Angel's Nail | Dragon Cave | Magic Dragon ×2, Saint Dragon |
| Silver Orb | The Ruins of Lukuna | Dark Lesser Demon |
| Gold Orb | The Ruins of Zeres | Lightning Lesser Demon |
| Tears of Oberon | Dark Elves Hiding Place | Flame / Water / Earth / Lightning / Dark Crimson |

These rewards do not come from the guardians' standard loot pools. The scenario
checks that no active actors remain in the guardian group, then creates the
item at the chest location. A separate scenario flag prevents repeat creation.

During the poisoning storyline's antidote quest, Dorojan gives Antidote in
exchange for Fruit of Poreno brought from Ponero Cave. When starting quest 37,
Take the sacred relics to Saint Sena, Barshival places the three relics directly
in the special-item area. These are not unconditional early-game item sources.

## Data and coordinates

`tools/build_scenario_items.py` reads 209 MCT and 209 SCS files with bounds/EOF
checks. It validates the annotated reward commands, NPC references, quest 32
condition and numeric Table.Tbd groups, and stops on unrecognized formats.
An NPC's `DELETEITEM` command indicates **use or turn-in**, not acquisition;
those links are kept separate. Source MCT/SCS SHA-256 values accompany the data.

Markers use the game's projection from local world coordinates:
`screenX = trunc((X-Y)*15/100)`, `screenY = trunc((X+Y)*10/100)`.
C's division toward zero is preserved for negative coordinates. Monster and
scenery rendering is unchanged; markers are a layer over the Atlas map.

```powershell
python tools/build_scenario_items.py --game 'C:\Games\ShadowFlare'
node tests/test_scenario_items.cjs
# The DOM test requires the jsdom development dependency:
node tests/test_scenario_page.cjs
```

The generated `app/assets/scenario-items.js` contains game-derived data. It is
excluded from Git, included in local ZIPs and supported by the existing asset
importer. Building it does not change game files, saves or live companion settings.
