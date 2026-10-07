#!/usr/bin/env python3
"""
NCAA Football 2005 GCI Roster Editor (v1)

A simple command-line roster editor for NCAA 05 GameCube GCI saves.
Parses the PLAY table and allows viewing/editing player ratings.

Usage:
  python roster_editor.py <gci_file>
  python roster_editor.py <gci_file> --edit <player_idx> <field> <value>
  python roster_editor.py <gci_file> --save <output_gci>
"""

import sys
from pathlib import Path
from gci_play_parser import GCIPlayTable

# Key rating fields to display
DISPLAY_FIELDS = ['PPOS', 'PTHA', 'PACC', 'PSPD', 'PAGI', 'PAWR', 'POVR', 'PKAC', 'PPOW']

# Position names (approximate mapping)
POSITIONS = {
    0: 'QB', 1: 'HB', 2: 'FB', 3: 'WR', 4: 'TE',
    5: 'LT', 6: 'LG', 7: 'C', 8: 'RG', 9: 'RT',
    10: 'LE', 11: 'RE', 12: 'DT', 13: 'LOLB', 14: 'MLB',
    15: 'ROLB', 16: 'CB', 17: 'FS', 18: 'SS', 19: 'K', 20: 'P'
}


def format_player(table, idx):
    """Format a player for display."""
    first, last = table.get_player_name(idx)
    name = f"{first} {last}".strip() or f"Player {idx}"
    
    fields = {}
    for fname in DISPLAY_FIELDS:
        try:
            fields[fname] = table.get_field(idx, fname)
        except KeyError:
            fields[fname] = '?'
    
    pos = fields.get('PPOS', '?')
    pos_name = POSITIONS.get(pos, f'POS{pos}') if isinstance(pos, int) else pos
    
    return f"[{idx:4d}] {name:20s} {pos_name:4s} " + " ".join(
        f"{k}={v}" for k, v in fields.items() if k != 'PPOS'
    )


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    gci_path = sys.argv[1]
    print(f"Loading {gci_path}...")
    table = GCIPlayTable(gci_path)
    print(f"Loaded: {len(table.fields)} fields, {table.record_count} records")
    print()
    
    # Handle commands
    if '--edit' in sys.argv:
        # --edit <idx> <field> <value>
        idx = sys.argv.index('--edit')
        player_idx = int(sys.argv[idx+1])
        field = sys.argv[idx+2]
        value = int(sys.argv[idx+3])
        
        print(f"Setting player {player_idx} {field} = {value}")
        old_val = table.get_field(player_idx, field)
        table.set_field(player_idx, field, value)
        new_val = table.get_field(player_idx, field)
        print(f"  Changed from {old_val} to {new_val}")
        
        # Save to output if specified
        if '--save' in sys.argv:
            sidx = sys.argv.index('--save')
            out_path = sys.argv[sidx+1]
            table.save_gci(out_path)
    elif '--save' in sys.argv:
        sidx = sys.argv.index('--save')
        out_path = sys.argv[sidx+1]
        table.save_gci(out_path)
    elif '--setname' in sys.argv:
        # --setname <idx> <first> <last>
        idx = sys.argv.index('--setname')
        player_idx = int(sys.argv[idx+1])
        first = sys.argv[idx+2]
        last = sys.argv[idx+3] if idx+3 < len(sys.argv) and not sys.argv[idx+3].startswith('--') else ""
        
        print(f"Setting player {player_idx} name to '{first} {last}'")
        table.set_player_name(player_idx, first, last)
        nf, nl = table.get_player_name(player_idx)
        print(f"  New name: '{nf} {nl}'")
        
        if '--save' in sys.argv:
            sidx = sys.argv.index('--save')
            out_path = sys.argv[sidx+1]
            table.save_gci(out_path)
    else:
        # List players
        limit = 20
        if '--all' in sys.argv:
            limit = table.record_count
        elif '--limit' in sys.argv:
            lidx = sys.argv.index('--limit')
            limit = int(sys.argv[lidx+1])
        
        print(f"First {limit} players:")
        print()
        for i in range(min(limit, table.record_count)):
            try:
                print(format_player(table, i))
            except Exception as e:
                print(f"[{i:4d}] Error: {e}")
                break


if __name__ == '__main__':
    main()
