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
