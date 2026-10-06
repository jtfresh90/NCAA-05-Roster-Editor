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
    Returns list of team names.
    """
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
