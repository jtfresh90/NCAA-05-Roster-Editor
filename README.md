# NCAA Football 2005 Roster Editor (GameCube)

Roster tools for EA Sports NCAA Football 2005 (GameCube, Game ID GCUE69).

## Status: v1.0.0 Research Preview

This is an early research release. The EA DB format is under active reverse engineering.

### What works
- **Team browser**: Extract and list all 175 teams from LEAGUE.DAT
- **DB parser**: Basic EA DB format parsing (`ncaa05_db.py`)

### Research boundaries
- **Player rosters**: PLAY table located (0x12A098), record format TBD
- **Player ratings**: Not yet located
- **ISO writing**: Not implemented (read-only in v1.0.0)

### Format notes
- EA uses TERF archives (not Sega's DAT)
- `LEAGUE.DAT` (2.1MB) contains team/player database
- EA DB format: tables with 4-char names (PLAY, TEAM, etc.)
- Team names stored as `\x04\xff<Name>!` pattern
- PPOS field: 0=QB, 1=HB, 2=FB, 3=WR, 4=TE, 5=LT, 6=LG, 7=C, 8=RG, 9=RT, 10=LEDG, 11=REDG, 12=DT, 13=SAM, 14=MIKE, 15=WILL, 16=CB, 17=FS, 18=SS, 19=K, 20=P

## Usage

### Desktop (Windows EXE)
Download the EXE from Releases. No Python required.

1. Extract `LEAGUE.DAT` from your NCAA 2005 ISO (offset 0x4E352D78, 2.1MB)
2. Run the editor, open LEAGUE.DAT
3. Browse teams

### Mobile (iOS/Android PWA)
Open https://jtfresh90.github.io/NCAA-05-Roster-Editor/mobile/ in Safari (iOS) or Chrome (Android), then "Add to Home Screen".

### Python
```bash
python ncaa05_db.py league.dat
```

## Building

### Windows EXE
The GitHub workflow builds a standalone EXE via PyInstaller on each release.

## License
For use with legally obtained copies of NCAA Football 2005 (GameCube).
