#!/usr/bin/env python3
"""
NCAA Football 2005 (GameCube) GCI Roster Parser

Parses the PLAY table from a GCI save file's embedded DB.
Based on reverse-engineering of ncaa_football_2005_roster_usa.gci
from https://gc-saves.com/container/283

Format summary:
- GCI file contains DB at offset 0x880, size 0x730E0
- DB has YALP (PLAY) table with GameCube-transformed field names
- Schema: 85 fields, 16-byte BE descriptors [name][size][type][bit_offset]
- Records: 52 bytes each at DB offset 0xA6F8, 16-byte header, data at +16
- Names: 6-bit alphabet (0=empty, 1-26=a-z, 27-52=A-Z, 53='-', 54="'", 55='.', 56=' ')
- Ratings: 5-bit fields (PPOS, PTHA, PACC, PSPD, etc.)
"""

from pathlib import Path
import struct
import json

# 6-bit character alphabet (from NCAA DB Editor source)
ALPHABET = {0: ''}
for i in range(1, 27):
    ALPHABET[i] = chr(ord('a') + i - 1)
for i in range(27, 53):
    ALPHABET[i] = chr(ord('A') + i - 27)
ALPHABET.update({
    53: '-', 54: "'", 55: '.', 56: ' ', 57: '@', 58: '±'
})
# Reverse lookup for encoding
CHAR_TO_VAL = {v: k for k, v in ALPHABET.items() if v}

# GCI/DB constants
GCI_DB_OFFSET = 0x880
GCI_DB_SIZE = 0x730E0
PLAY_SCHEMA_OFFSET = 0xA198
PLAY_TABLE_HEADER_OFFSET = 0xA6F8  # 16-byte table header
PLAY_RECORDS_OFFSET = 0xA708  # Records start after 16-byte header
PLAY_RECORD_SIZE = 52
PLAY_DATA_OFFSET = 0  # No per-record header; schema offsets are absolute


def get_bits(buf, bit_off, bit_len):
    """Extract bits, MSB-first (big-endian bit order)."""
    val = 0
    for i in range(bit_len):
        byte_idx = (bit_off + i) // 8
        bit_idx = 7 - ((bit_off + i) % 8)
        if byte_idx < len(buf) and (buf[byte_idx] >> bit_idx & 1):
            val |= 1 << (bit_len - 1 - i)
    return val


def set_bits(buf, bit_off, bit_len, val):
    """Set bits, MSB-first (big-endian bit order)."""
    buf = bytearray(buf)
    for i in range(bit_len):
        byte_idx = (bit_off + i) // 8
        bit_idx = 7 - ((bit_off + i) % 8)
        bit_val = (val >> (bit_len - 1 - i)) & 1
        if bit_val:
            buf[byte_idx] |= (1 << bit_idx)
        else:
            buf[byte_idx] &= ~(1 << bit_idx)
    return bytes(buf)


def gc_to_pc_name(gc_name):
    """Convert GameCube (reversed) field name to PC name."""
    return gc_name[::-1]


def parse_schema(db_data, schema_offset=PLAY_SCHEMA_OFFSET):
    """
    Parse the PLAY table schema from the DB.
    Returns dict of {pc_name: (size_bits, bit_offset)}.
    """
    fields = {}
    off = schema_offset
    
    while off + 16 <= len(db_data):
        name_bytes = db_data[off:off+4]
        
        # Check for separator
        if name_bytes[:3] == b'\x21\x00\x04':
            off += 3
            continue
        
        try:
            name = name_bytes.decode('ascii')
        except:
            break
        
        if not all(c.isalnum() or c == '_' for c in name):
            break
        
        size = struct.unpack('>I', db_data[off+4:off+8])[0]
        ftype = struct.unpack('>I', db_data[off+8:off+12])[0]
        
        if size > 5000 or ftype > 20:
            break
        
        # Check for inline separator
        if db_data[off+12:off+15] == b'\x21\x00\x04':
            off += 15
            continue
        
        bit_off = struct.unpack('>I', db_data[off+12:off+16])[0]
        if bit_off > 10000:
            break
        
        pc_name = gc_to_pc_name(name)
        fields[pc_name] = (size, bit_off)
        off += 16
        
        if len(fields) > 200:
            break
    
    return fields


def decode_name(rec_data, fields, prefix, count):
    """Decode a 6-bit packed name (PF01-PF10 or PL01-PL13)."""
    name = ''
    for i in range(1, count + 1):
        fname = f'{prefix}{i:02d}'
        if fname not in fields:
            continue
        size, bit = fields[fname]
        v = get_bits(rec_data, bit, size)
        if v == 0:
            break
        name += ALPHABET.get(v, '?')
    return name


def encode_name(name, max_len):
    """
    Encode a name to 6-bit values.
    Returns list of 6-bit values, padded with 0.
    """
    vals = []
    for c in name[:max_len]:
        # Try exact match, then case-insensitive
        if c in CHAR_TO_VAL:
            vals.append(CHAR_TO_VAL[c])
        elif c.upper() in CHAR_TO_VAL:
            vals.append(CHAR_TO_VAL[c.upper()])
        elif c.lower() in CHAR_TO_VAL:
            vals.append(CHAR_TO_VAL[c.lower()])
        else:
            vals.append(56)  # space for unknown
    # Pad with zeros
    while len(vals) < max_len:
        vals.append(0)
    return vals[:max_len]


class GCIPlayTable:
    """Parser for the PLAY table in a GCI save's DB."""
    
    def __init__(self, gci_path):
        self.gci_path = Path(gci_path)
        self.gci_data = self.gci_path.read_bytes()
        
        # Extract DB
        self.db_offset = self.gci_data.find(b'DB')
        if self.db_offset < 0:
            raise ValueError("No DB marker found in GCI")
        
        self.db_data = self.gci_data[self.db_offset:self.db_offset + GCI_DB_SIZE]
        
        # Parse schema
        self.fields = parse_schema(self.db_data)
        
        # Find records
        self.records_offset = PLAY_RECORDS_OFFSET
        self.record_size = PLAY_RECORD_SIZE
        self.data_offset = PLAY_DATA_OFFSET
        
        # Count records (estimate from DB size)
        # Records go from 0xA6F8 to end of table data
        # For now, we'll parse until we hit invalid data
        self._count_records()
    
    def _count_records(self):
        """Estimate record count by scanning for valid records."""
        # The table data size is in the header, but for now
        # we'll use a heuristic: scan until PGID-like pattern breaks
        # Actually, let's just use a reasonable default and allow iteration
        # 
        # From the GCI, the PLAY table appears to have ~1000+ players
        # (enough for all teams). We'll detect by checking for
        # non-zero data.
        max_possible = (len(self.db_data) - self.records_offset) // self.record_size
        # Cap at reasonable number for NCAA (approx 120 teams * 70 players = 8400)
        # But GCI roster is likely smaller. Let's scan.
        count = 0
        for i in range(min(max_possible, 10000)):
            rec_off = self.records_offset + i * self.record_size
            rec = self.db_data[rec_off:rec_off + self.record_size]
            if len(rec) < self.record_size:
                break
            # Check if record has any non-zero data beyond header
            data_part = rec[self.data_offset:]
            if all(b == 0 for b in data_part):
                # Empty record, but might be valid (skip, continue counting?)
                # For now, break on first fully empty
                # Actually, let's continue - empty might be valid
                pass
            count += 1
            # Safety: if we've seen 5000 empty in a row, stop
            # (simplified - just cap at 2000 for now)
            if count >= 2000:
                break
        self.record_count = count
    
    def get_record(self, index):
        """Get raw record data (52 bytes) for player index."""
        if index >= self.record_count:
            raise IndexError(f"Record {index} out of range ({self.record_count})")
        off = self.records_offset + index * self.record_size
        return self.db_data[off:off + self.record_size]
    
    def get_player_data(self, index):
        """Get player data portion (36 bytes after 16-byte header)."""
        rec = self.get_record(index)
        return rec[self.data_offset:]
    
    def get_field(self, index, field_name):
        """Get a field value for a player."""
        if field_name not in self.fields:
            raise KeyError(f"Unknown field: {field_name}")
        size, bit = self.fields[field_name]
        data = self.get_player_data(index)
        return get_bits(data, bit, size)
    
    def set_field(self, index, field_name, value):
        """Set a field value for a player (modifies DB in memory)."""
        if field_name not in self.fields:
            raise KeyError(f"Unknown field: {field_name}")
        size, bit = self.fields[field_name]
        max_val = (1 << size) - 1
        if value < 0 or value > max_val:
            raise ValueError(f"Value {value} out of range for {field_name} (0-{max_val})")
        
        # Get record offset in DB
        rec_off = self.records_offset + index * self.record_size + self.data_offset
        rec_data = self.db_data[rec_off:rec_off + (self.record_size - self.data_offset)]
        
        # Set bits
        new_data = set_bits(rec_data, bit, size, value)
        
        # Update DB (in memory)
        db_list = bytearray(self.db_data)
        db_list[rec_off:rec_off + len(new_data)] = new_data
        self.db_data = bytes(db_list)
    
    def get_player_name(self, index):
        """Get player's first and last name."""
        data = self.get_player_data(index)
        first = decode_name(data, self.fields, 'PF', 10)
        last = decode_name(data, self.fields, 'PL', 13)
        return first, last
    
    def set_player_name(self, index, first_name, last_name):
        """Set player's first and last name."""
        # Encode names
        first_vals = encode_name(first_name, 10)
        last_vals = encode_name(last_name, 13)
        
        # Get record
        rec_off = self.records_offset + index * self.record_size + self.data_offset
        rec_data = bytearray(self.db_data[rec_off:rec_off + (self.record_size - self.data_offset)])
        
        # Set first name fields (PF01-PF10)
        # Note: PF10 is at a different bit offset than PF01-PF09!
        # PF10@46, PF01@58, PF02@76, etc. (from schema)
        for i, val in enumerate(first_vals, 1):
            fname = f'PF{i:02d}'
            if fname in self.fields:
                size, bit = self.fields[fname]
                # Set bits manually
                for b in range(size):
                    byte_idx = (bit + b) // 8
                    bit_idx = 7 - ((bit + b) % 8)
                    bit_val = (val >> (size - 1 - b)) & 1
                    if bit_val:
                        rec_data[byte_idx] |= (1 << bit_idx)
                    else:
                        rec_data[byte_idx] &= ~(1 << bit_idx)
        
        # Set last name fields (PL01-PL13)
        for i, val in enumerate(last_vals, 1):
            fname = f'PL{i:02d}'
            if fname in self.fields:
                size, bit = self.fields[fname]
                for b in range(size):
                    byte_idx = (bit + b) // 8
                    bit_idx = 7 - ((bit + b) % 8)
                    bit_val = (val >> (size - 1 - b)) & 1
                    if bit_val:
                        rec_data[byte_idx] |= (1 << bit_idx)
                    else:
                        rec_data[byte_idx] &= ~(1 << bit_idx)
        
        # Update DB
        db_list = bytearray(self.db_data)
        db_list[rec_off:rec_off + len(rec_data)] = rec_data
        self.db_data = bytes(db_list)
    
    def save_gci(self, output_path):
        """Write modified DB back to GCI file."""
        # Reconstruct GCI with modified DB
        gci_list = bytearray(self.gci_data)
        gci_list[self.db_offset:self.db_offset + len(self.db_data)] = self.db_data
        Path(output_path).write_bytes(bytes(gci_list))
        print(f"Saved modified GCI to {output_path}")
    
    def list_players(self, limit=10):
        """List players with their ratings (for debugging)."""
        print(f"PLAY table: {len(self.fields)} fields, {self.record_count} records")
        print()
        for i in range(min(limit, self.record_count)):
            first, last = self.get_player_name(i)
            try:
                ppos = self.get_field(i, 'PPOS')
                povR = self.get_field(i, 'POVR')
                print(f"  [{i}] '{first} {last}' PPOS={ppos} POVR={povR}")
            except KeyError:
                print(f"  [{i}] '{first} {last}'")


def main():
    import sys
    if len(sys.argv) < 2:
        print("Usage: gci_play_parser.py <gci_file> [output_gci]")
        sys.exit(1)
    
    gci_path = sys.argv[1]
    table = GCIPlayTable(gci_path)
    table.list_players(10)
    
    # Example: set player 0's name
    if len(sys.argv) >= 3:
        print("\nSetting player 0 name to 'Test Player'...")
        table.set_player_name(0, "Test", "Player")
        first, last = table.get_player_name(0)
        print(f"  New name: '{first} {last}'")
        table.save_gci(sys.argv[2])


if __name__ == '__main__':
    main()
