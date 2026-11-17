# NCAA Football 2005 Editor (GameCube) — Fixed Build

Editing tools for EA Sports NCAA Football 2005 (GameCube, Game ID GCUE69) — rosters, textures, and 3D models.

**This package is the “fixed” drop** that addresses the previous visibility problem (only a handful of teams/players showing) and wires the real parsers into the desktop player editor.

## What was fixed (v1.2.0)

- Desktop player editor (`ncaa05_player_editor.py`) now uses the real `GCIPlayTable` / `IsoPlayTable` instead of placeholders.
- Full player list is loaded (no artificial 5-team or 100-player hard limit).
- GCI path supports name + rating editing and save-with-backup.
- ISO / LEAGUE.DAT path loads all discovered YALP sections and exposes ratings.

Still research-preview quality overall. Team names in ISO mode remain “Player N” until the name table is fully mapped. Mobile PWA is unchanged in this zip (use the live GitHub Pages version or the desktop editor).

## Tools

### 1. Roster Editor
- **GCI saves**: Parse and edit player ratings from GameCube memory-card saves (`gci_play_parser.py`, `roster_editor.py`, `ncaa05_player_editor.py`)
- **ISO**: Edit the ~27k-player LEAGUE.DAT database (`iso_play_parser.py`)
- 16+ ratings per player, in-place style editing for GCI

### 1b. Roster CSV + Mod Packages (MacDog850-style workflow)
The Player Editor has four toolbar buttons — **Export Roster CSV**,
**Import Roster CSV**, **Export Mod Package**, **Import Mod Package**
(`ncaa05_roster_csv.py`, `ncaa05_modpack.py`; also usable from the
command line, `python ncaa05_roster_csv.py --help` /
`python ncaa05_modpack.py --help`).

- **Export Roster CSV** dumps all 7,324 players to a spreadsheet:
  PGID (the stable player key), team, first + last name, and all 62
  non-name PLAY field values (the 23 name-letter fields are carried
  as the decoded name strings, not as numbers). Works from a GCI save
  or from an ISO image — the ISO export reads the **default roster**
  stored in TEMPLATE.DAT (TEMPLATE+0x1BA340), which is the same
  7,324-player roster as the save. A bare LEAGUE.DAT has no player
  records and is refused with an explanation.
- **Import Roster CSV** applies an edited CSV back. It validates
  everything first (row count, PGID set, name length/alphabet, field
  ranges, the RCHD/PHED overlap) and refuses to write anything if
  anything fails — bad characters and over-long names are reported
  per row, never silently replaced or truncated. GCI imports apply to
  the live table (click Save afterwards); ISO imports write a NEW ISO
  file (the input is never overwritten). A backup is written first.
- **Mod packages** are zips in the MacDog850 shape
  (`manifest.json` + `blobs/<sha256>`, format `ncaa05-mod-v1`):
  name, identity (base file sha256 + size), changes (one roster file:
  the GCI, or TEMPLATE.DAT for an ISO), package_version, source.
  The package carries the changed roster file only — never the whole
  ISO. Import verifies blob hashes, base identity, and the current
  roster hash before applying, and refuses on any mismatch (tampered
  package, wrong base, already-modified target).
- **Team column: not yet mappable.** The CSV's `team` column is
  empty in v1 exports and import refuses any non-empty value: no PLAY
  field carries a team, and the per-team DBs' YSLP record layout (the
  only candidate mapping) is still undecoded. See the module docs in
  `ncaa05_roster_csv.py` for the full findings.
- **PWA:** the mobile PWA does not have this workflow yet — it has no
  zip implementation at all, so the port needs a JS zip reader/writer
  (a follow-up round; the desktop module is the reference).

### 2. Texture Editor
- **TERF/DIR1 parsing** of texture archives
- **GameCube CMPR codec**
- See `texture_parser.py`

### 3. Model Swap
- Whole-entry mesh swapping in PLADATA.DAT etc. (`model_swap.py`)

### 4. Helmet Pack + Helmet Finishes (`helmets/`)
- Adds three helmet shells to the player models in PLADATA.DAT: Speedflex (Revolution slot, plus its facemask as
  the RevoG2B mask), "Helmet" by osha22 (Schutt slot) and "Football Helmet" by ZionCaesar (Adams slot).
  The standard helmet stays stock.
- Per helmet type finish: **Glossy** (game default), **Matte** (shine pass off) or **Chrome** (shine pass doubled).
  Decals/stickers never get the shine, so they look the same on every finish.
- Desktop editor: **Helmets (PLADATA)** tab -> Open PLADATA.DAT -> pick finishes -> Save.
- Command line:

```bash
python helmets/helmet_pack.py show PLADATA.DAT
python helmets/helmet_pack.py install PLADATA.DAT PLADATA_new.DAT --finish revo=matte schutt=chrome adams=gloss std=gloss
```

- Put the saved file back into the disc image as `/PLADATA.DAT` (the file grows, so rebuild the image, e.g.
  GCRebuilder). Not yet verified in Dolphin. Credits/licences: `helmets/PACK_NOTES.txt` (all CC-BY-4.0).

## Quick Start (Desktop)

```bash
pip install PyQt5
python ncaa05_player_editor.py
```

Open a `.gci` (recommended for full name editing) or an ISO / extracted LEAGUE.DAT.

Command-line GCI:

```bash
python roster_editor.py your_roster.gci
python roster_editor.py your_roster.gci --edit 0 PSPD 90 --save modified.gci
```

## Mobile / PWA

Still available at the original GitHub Pages links:

- Roster: https://jtfresh90.github.io/NCAA-05-Roster-Editor/mobile/
- Texture / Model tools also under `/mobile/`

## Research notes
- EA uses TERF archives
- Player faces: 128×128 CMPR with mipmaps
- Player names are not licensed (generic or generated)
- See original repo docs for format research

## License
For use with legally obtained copies of NCAA Football 2005 (GameCube).
