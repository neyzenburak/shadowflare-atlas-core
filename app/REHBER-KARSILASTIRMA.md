# Comparing the Premium guide with game data

18 October 2026. Sources: 15 Premium item pages linked from the user's local
`herşey/Guide.html` and their original JPGs. The originals were not modified.
Text in quest and map images is outside this comparison's scope.

## How the guide is organized

The HTML contains no item records or JavaScript classifier. It displays long,
pre-rendered JPGs. Items are grouped into one-/two-handed swords, katanas, axes,
crossbows, staves, armor, helmets, greaves, shields and accessories. Some groups
are also split by required level. Searching the HTML for an item name therefore
does not find the items shown inside images.

## Findings

The game data has 457 Premium records with quality class 2. The guide contains
452 identified panels. Titles were extracted with OCR; low-confidence readings
were checked against the originals. There are 443 individually matched records.
Nine Monolis panels and nine Monolis records share a name: the family is present,
but individual color/property variants have not been matched.

These five names are absent from the reviewed Premium lists:

| Record | Name | Required level | Standard drop source |
|---|---|---:|---|
| 0:13000600 | Caster Force | 40 | Yes; for example Devil Jurg |
| 0:80000041 | 備前長船義直 | 35 | Yes; for example Ancient Dragon |
| 1:31500 | Saint Robe: Premium record | 50 | Yes; for example Devil Dignosis |
| 2:200007 | Mithril Pendant | 25 | Yes; for example Phantom Extra Gargoyle |
| 2:200020 | Kyanite Ring | 30 | Yes; for example Ancient Dragon |

Saint Robe also has a Plain record with the same name. This finding concerns
only Premium `1:31500`; a shared name does not imply the same quality or record.

These five are not merely unreachable file entries: they are selectable
candidates in the reviewed standard tables, and scenarios contain monsters
using those groups. No live-kill experiment was performed. Absence from the
guide does not prove beta, removed, unused or previously unknown content.

## Tesla Blade correction

Both Tesla Blades appear in `sw51_80.jpg`:

| Record | Approximate title Y | Required level | Base Attack | Sale Price |
|---|---:|---:|---:|---:|
| 0:80000128 | 2689 px | 75 | 3000 | 10000 |
| 0:80000127 | 3414 px | 80 | 5400 | 50000 |

Name, base Attack, level and price match two separate game records. Where the
local guide image is available, the Atlas source button scrolls to this position.

## Presentation

Actual Font00.njp bitmap glyphs and inventory icons are used. Base values are
shown separately from extra properties: Knuckle Breaker's base Attack 20 and
additional Attack +45 occupy different sections. Accessory required levels
come from each game record's own field. The frame was redrawn, while its dark
stone texture comes from the original Status.njp interface artwork.
