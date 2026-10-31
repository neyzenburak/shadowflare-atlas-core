# User-supplied local tables

Core includes a small CT importer and no third-party table. On the Control
Desk, open Trainer and choose **CT dosyası ekle**. Select your own `.ct` file
(maximum 4 MB). The helper needs a selected compatible game folder, but no
loaded character is required to import a table.

The imported XML is treated as data. Lua is not executed, arbitrary symbols
or DLL addresses are not accepted, and unknown assembly is not executed.
Unsupported records remain visible with their reason. The importer is not a
general implementation of Cheat Engine or its Auto Assembler language.

Supported operations are 32-bit values, bounded strings, supported player/
companion pointer chains, simple one-time byte writes, and a limited x86
instruction subset for static patches and one bounded allocation. Native code
patches use original executable bytes as their before-image and end on whole
instructions. Turning a patch off restores that exact before-image. Conflicting
patches are rejected instead of being layered over unknown bytes.

Table labels, scripts and structure descriptions are shown only after local
import. Data is persisted in `app/trainer-local/table.json`. This folder is
ignored by Git and not selected by the package builder. **Tabloyu kaldır**
restores active imported patches, clears their value freezes and undo data,
and removes the local table. Atlas-authored controls remain available.

Asset setup always produces an empty trainer catalogue and never searches the
game folder for a table. Importing old asset ZIPs cannot replace the empty
catalogue or copy a top-level CT file. Packaging rejects a nonempty bundled
trainer catalogue and excludes `.ct` files and the local import folder.

Verification with the user's existing local table: 836 records, 749 value
fields, 20 static toggles and three one-time actions were recognized. All 20
toggles were enabled and disabled in an isolated running game copy; every
modified byte was restored. The original table and these imported records
are not test fixtures in this repository.
