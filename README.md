# NCAA Football 2005 Editor (GameCube)

Editing tools for EA Sports NCAA Football 2005 (GameCube, Game ID GCUE69) — rosters, textures, and 3D models.

## Tools

### 1. Roster Editor
- **GCI saves**: Parse and edit player ratings from GameCube memory-card saves (`gci_play_parser.py`, `roster_editor.py`)
- **ISO**: Edit the 27,526-player LEAGUE.DAT database directly in the ISO (`iso_play_parser.py`)
- 16 ratings per player, in-place ISO patching

### 2. Texture Editor
- **TERF/DIR1 parsing** of texture archives (PLYRFACE, COACFACE, ICONS, UIS_*)
- **GameCube CMPR codec** — decode to PNG, encode PNG back to CMPR (Python + JavaScript)
- **HD mode**: import 256×256 textures; DAT and ISO grow, quality preserved
- **Always-quality imports**: full mipmap chains regenerated from source (no stale mipmaps)
- Safe ISO rebuild with FST update (`texture_parser.py`)

### 3. Model Swap
- **Whole-entry mesh swapping** in PLADATA.DAT (2,672 player/equipment models), UIS_MODL.DAT (111 menu models), FANDATA.DAT (257 crowd models)
- trey31 method: swap model blobs between slots, no geometry decoding needed (`model_swap.py`)
- Safe TERF rebuild + ISO/FST update

## Usage

### Mobile (iOS/Android PWA) — no computer needed
Open in Safari (iOS) or Chrome (Android), then "Add to Home Screen":

- **Roster Editor**: https://jtfresh90.github.io/NCAA-05-Roster-Editor/mobile/
- **Texture Editor**: https://jtfresh90.github.io/NCAA-05-Roster-Editor/mobile/texture.html
- **Model Swap**: https://jtfresh90.github.io/NCAA-05-Roster-Editor/mobile/models.html

Load your ISO in the browser, edit, download the patched ISO.

### Desktop (Windows EXE)
Download the EXE from [Releases](https://github.com/jtfresh90/NCAA-05-Roster-Editor/releases). No Python required.

### Python
```bash
# Roster (GCI)
python roster_editor.py ncaa05_roster.gci

# Textures (with HD + mipmaps)
python texture_parser.py

# Models (swap entries 2117 <-> 2118)
python model_swap.py PLADATA.DAT --swap 2117 2118 -o PLADATA_SWAPPED.DAT
```

## Research notes
- EA uses TERF archives (not Sega's DAT format)
- Player faces: 128×128 CMPR with mipmaps in PLYRFACE.DAT
- Player names are not stored in-game (no licensed names in NCAA 05)
- Model files use EA proprietary compression; mesh-swap works without decoding
- See `docs/` and `~/workspace/recon/ncaa05/` for format research

## Building

### Windows EXE
The GitHub workflow (`.github/workflows/build-windows-exe.yml`) builds a standalone EXE via PyInstaller on each release.

## License
For use with legally obtained copies of NCAA Football 2005 (GameCube).
