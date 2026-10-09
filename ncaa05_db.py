#!/usr/bin/env python3
"""
ncaa05_db.py - EA DB format parser for NCAA Football 2005 (GameCube)

Parses EA's DB database format found in LEAGUE.DAT (inside TERF archives).
Based on reverse engineering of NCAA Football 2005 (USA), Game ID GCUE69.

Status: v1.0.0 Research Preview
- Team names: extracted (148 teams)
- PLAY table: located (0x12A098)
- Player records: structure TBD
- Ratings: not yet located

EA DB Format (from Madden modding community):
- Tables: PLAY (players), TEAM (teams), etc.
- Fields: 4-char codes (PPOS=position, PFNA=first name, etc.)
- PPOS: 0=QB, 1=HB, 2=FB, 3=WR, 4=TE, 5=LT, 6=LG, 7=C, 8=RG, 9=RT,
        10=LEDG, 11=REDG, 12=DT, 13=SAM, 14=MIKE, 15=WILL, 16=CB,
        17=FS, 18=SS, 19=K, 20=P
"""

import struct
import re
from pathlib import Path

# Game constants
GAME_ID = "GCUE69"
LEAGUE_DAT_ISO_OFF = 0x4E352D78
LEAGUE_DAT_SIZE = 2176504


def find_iso_file(iso_path, target_name):
    """
    Locate a file inside a GameCube ISO via the disc header + FST.
    Works with any dump layout (raw, NKit, etc.) — no hardcoded offsets.
    Returns (offset, size). Raises ValueError with a clear message on failure.
    """
    target = target_name.upper()
    with open(iso_path, 'rb') as f:
        # Disc header: game ID at 0x00, FST offset at 0x424, FST size at 0x428
        f.seek(0)
        game_id = f.read(6).decode('ascii', errors='replace')
        f.seek(0x424)
        fst_off, fst_size = struct.unpack('>II', f.read(8))

        if not fst_off or not fst_size or fst_size > 0x100000:
            raise ValueError(
                f"Bad FST header (off=0x{fst_off:x}, size=0x{fst_size:x}). "
                "Is this a GameCube ISO?"
            )

        f.seek(fst_off)
        fst = f.read(fst_size)
        num_entries = struct.unpack('>I', fst[8:12])[0]
        if num_entries > 10000:
            raise ValueError("FST looks corrupt (too many entries).")

        str_tab = num_entries * 12
        for i in range(1, num_entries):
            e_off = i * 12
            if fst[e_off] == 1:  # directory
                continue
            name_off = (fst[e_off + 1] << 16) | (fst[e_off + 2] << 8) | fst[e_off + 3]
            end = fst.index(b'\x00', str_tab + name_off, str_tab + name_off + 64)
            name = fst[str_tab + name_off:end].decode('ascii', errors='replace')
            if name.upper() == target:
                offset, size = struct.unpack('>II', fst[e_off + 4:e_off + 12])
                return offset, size, game_id

    raise ValueError(f"{target_name} not found in ISO file table.")


def extract_league_dat_from_iso(iso_path):
    """Extract LEAGUE.DAT bytes from a GameCube ISO. Returns bytes."""
    offset, size, game_id = find_iso_file(iso_path, 'LEAGUE.DAT')
    if game_id != GAME_ID:
        print(f"Warning: game ID is {game_id} (expected {GAME_ID})")
    with open(iso_path, 'rb') as f:
        f.seek(offset)
        data = f.read(size)
    if len(data) != size:
        raise ValueError(
            f"ISO file appears truncated: FST says {size} bytes for LEAGUE.DAT "
            f"but only {len(data)} readable. Your ISO download is incomplete — "
            f"re-download it and try again."
        )
    if b'YALP' not in data[:0x10000]:
        raise ValueError("LEAGUE.DAT has no YALP sections — wrong file or corrupted ISO.")
    return data

# DB magic
DB_MAGIC = b'DB\x00'

# Position names (from EA DB docs)
POSITION_NAMES = {
    0: 'QB', 1: 'HB', 2: 'FB', 3: 'WR', 4: 'TE',
    5: 'LT', 6: 'LG', 7: 'C', 8: 'RG', 9: 'RT',
    10: 'LEDG', 11: 'REDG', 12: 'DT', 13: 'SAM', 14: 'MIKE',
    15: 'WILL', 16: 'CB', 17: 'FS', 18: 'SS', 19: 'K', 20: 'P',
}

class EADatabase:
    """Parser for EA DB format."""
    
    def __init__(self, data, offset=0):
        self.data = data
        self.offset = offset
        if data[offset:offset+3] != b'DB\x00':
            raise ValueError("Not an EA DB file")
    
    def find_tables(self):
        """Find all table names in the DB."""
        # Tables are 4-char uppercase codes
        # Look for common ones
        tables = []
        for name in [b'PLAY', b'TEAM', b'PPOS', b'COCH']:
            pos = self.data.find(name, self.offset)
            if pos != -1:
                tables.append((name.decode(), pos - self.offset))
        return tables

def extract_team_names(league_dat_path):
    """
    Extract team names from LEAGUE.DAT.
    Accepts a file path or raw bytes.
    Returns list of team names.
    """
    if isinstance(league_dat_path, (bytes, bytearray)):
        data = bytes(league_dat_path)
    else:
        with open(league_dat_path, 'rb') as f:
            data = f.read()
    
    # Pattern: \x04\xff<Name>!
    pattern = rb'\x04\xff([A-Za-z .&\'-]+?)!'
    matches = re.findall(pattern, data)
    
    teams = []
    for name in matches:
        try:
            decoded = name.decode('ascii', errors='ignore').strip()
            if decoded and len(decoded) > 2:
                teams.append(decoded)
        except:
            pass
    
    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for t in teams:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    
    return unique

def main():
    import sys
    if len(sys.argv) < 2:
        print("Usage: ncaa05_db.py <league.dat>")
        print("Extracts team names from NCAA 2005 LEAGUE.DAT")
        print()
        print("Status: v1.0.0 Research Preview")
        print("- Team names: extracted")
        print("- Player rosters: TBD (PLAY table located, record format under research)")
        sys.exit(1)
    
    teams = extract_team_names(sys.argv[1])
    print(f"Found {len(teams)} teams:")
    for name in teams[:30]:
        print(f"  {name}")
    if len(teams) > 30:
        print(f"  ... and {len(teams)-30} more")

if __name__ == '__main__':
    main()
