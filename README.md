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

#### Per-team helmet finishes (main.dol patch)
- The game picks the helmet shine from the helmet type. A small `main.dol` patch (`helmets/team_finish.py`) makes
  it look up the player's **team** instead: each team ID can be Glossy, Matte or Chrome, overriding the
  helmet-type finish. Stickers/decals are unaffected.
- Desktop editor: Helmets tab -> **Open main.dol** -> set each team's finish (optionally load team names from
  LEAGUE.DAT) -> **Save main.dol as...**. Needs the helmet pack installed in PLADATA.DAT as well (chrome uses
  extra shine options that the pack adds to the player models).
- Command line:

```bash
python helmets/team_finish.py set main.dol main_new.dol 12=matte 40=chrome
python helmets/team_finish.py show main_new.dol
```

- Put the patched DOL back as the disc's boot file (`sys/main.dol`) and rebuild the image.
- How it works: hooks at 0x802f5454 / 0x8005a824 remember each side's team ID (TOID) when uniforms are set up;
  hooks at 0x802464a4 / 0x80246710 (where the EnvMap shine option is chosen) switch it to "none" for matte or to
  the doubled "Chr*" option for chrome. Code and the 512-entry team table live in a new DOL section at 0x80001800.
  Tested in a PowerPC emulator; not yet verified in Dolphin. The team-name column is a guess from LEAGUE.DAT order
  until team IDs are confirmed in game.

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
