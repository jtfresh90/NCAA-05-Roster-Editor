#!/usr/bin/env python3
"""
NCAA Football 2005 ISO LEAGUE.DAT PLAY Table Parser

Parses the 420 YALP (PLAY) sections from LEAGUE.DAT.
Each section is self-contained with its own schema and records.

LEAGUE.DAT structure:
- TERF archive, 2,176,504 bytes
- 420 YALP sections, each ~3.8-5.5 KB
- Each section: [YALP marker][metadata][schema][records]

This parser finds all YALP sections and provides unified access
to players across all sections (like the GCI's single table).
"""

from pathlib import Path
import struct
from gci_play_parser import (
    parse_schema, get_bits, set_bits, decode_name, encode_name,
    ALPHABET, CHAR_TO_VAL, gc_to_pc_name
)

# LEAGUE.DAT constants
LEAGUE_DAT_SIZE = 2176504
LEAGUE_DAT_ISO_OFFSET = 0x4E352D78


class YalpSection:
    """A single YALP section from LEAGUE.DAT."""
    
    def __init__(self, data, offset):
        self.data = data  # Full LEAGUE.DAT
        self.offset = offset  # Offset of YALP marker
        
        # Find schema (look for 01FP within 0x2000 bytes)
        self.schema_offset = None
        for i in range(offset, min(offset + 0x2000, len(data))):
            if data[i:i+4] == b'01FP':
                self.schema_offset = i
                break
        
        if self.schema_offset is None:
            raise ValueError(f"No schema found in YALP at 0x{offset:X}")
        
        # Parse schema
        self.fields = parse_schema(data, self.schema_offset)
        
        # Find records (after schema)
        # Schema ends where parsing stopped; records follow
        # For now, estimate: schema is ~85*16=1360 bytes
        # Records start after schema + possible padding
        self.records_offset = self._find_records()
        
        # Section size: distance to next YALP or end
        next_yalp = data.find(b'YALP', offset + 1)
        if next_yalp < 0:
            self.section_size = len(data) - offset
        else:
            # Make sure it's a real section start (not false positive)
            # Real sections are at least 0x1000 apart
            if next_yalp - offset < 0x100:
                # False positive, find next
                pos = next_yalp + 1
                while True:
                    nxt = data.find(b'YALP', pos)
                    if nxt < 0 or nxt - offset >= 0x100:
                        next_yalp = nxt
                        break
                    pos = nxt + 1
            self.section_size = (next_yalp - offset) if next_yalp > 0 else (len(data) - offset)
    
    def _find_records(self):
        """Find where records start after schema."""
        # Parse schema to find end
        off = self.schema_offset
        while off + 16 <= len(self.data):
            name_bytes = self.data[off:off+4]
            if name_bytes[:3] == b'\x21\x00\x04':
                off += 3
                continue
            try:
                name = name_bytes.decode('ascii')
            except:
                break
            if not all(c.isalnum() or c == '_' for c in name):
                break
            size = struct.unpack('>I', self.data[off+4:off+8])[0]
            ftype = struct.unpack('>I', self.data[off+8:off+12])[0]
            if size > 5000 or ftype > 20:
                break
            if self.data[off+12:off+15] == b'\x21\x00\x04':
                off += 15
                continue
            bit_off = struct.unpack('>I', self.data[off+12:off+16])[0]
            if bit_off > 10000:
                break
            off += 16
            if off - self.schema_offset > 2000:  # Safety
                break
        
        # Records start at off, but there might be a header
        # Look for the pattern: records are 52 bytes, should have non-zero data
        # For now, return off (we'll refine)
        return off
    
    def get_record_count(self):
        """Estimate record count in this section."""
        # Available space for records
        avail = self.section_size - (self.records_offset - self.offset)
        # Each record is 52 bytes
        return max(0, avail // 52)


class IsoPlayTable:
    """Unified PLAY table across all YALP sections in LEAGUE.DAT."""
    
    def __init__(self, league_dat_path):
        self.path = Path(league_dat_path)
        self.data = bytearray(self.path.read_bytes())
        
        if len(self.data) != LEAGUE_DAT_SIZE:
            print(f"Warning: LEAGUE.DAT size {len(self.data)} != expected {LEAGUE_DAT_SIZE}")
        
        # Find all YALP sections
        print("Finding YALP sections...")
        self.sections = []
        pos = 0
        while True:
            idx = self.data.find(b'YALP', pos)
            if idx < 0:
                break
            # Skip if too close to previous (false positive)
            if self.sections and idx - self.sections[-1].offset < 0x1000:
                pos = idx + 1
                continue
            try:
                section = YalpSection(self.data, idx)
                # Only keep sections with valid schema (85-ish fields)
                if 80 <= len(section.fields) <= 90:
                    self.sections.append(section)
                    print(f"  Section {len(self.sections)}: 0x{idx:X}, {len(section.fields)} fields")
            except ValueError:
                pass  # Skip invalid sections
            pos = idx + 1
            if len(self.sections) >= 500:  # Safety
                break
        
        print(f"Found {len(self.sections)} valid YALP sections")
        
        # Build unified player index
        # Each section has its own records; we'll map global idx -> (section, local_idx)
        self._build_index()
    
    def _build_index(self):
        """Build mapping from global player index to (section, local index)."""
        self.index = []  # List of (section_idx, local_idx)
        for si, section in enumerate(self.sections):
            count = section.get_record_count()
            # Cap at reasonable per-section (maybe 100 players per team?)
            count = min(count, 100)
            for li in range(count):
                self.index.append((si, li))
        print(f"Total players indexed: {len(self.index)}")
    
    def get_field(self, global_idx, field_name):
        """Get field value for player by global index."""
        if global_idx >= len(self.index):
            raise IndexError(f"Player {global_idx} out of range")
        si, li = self.index[global_idx]
        section = self.sections[si]
        
        if field_name not in section.fields:
            raise KeyError(f"Unknown field: {field_name}")
        
        size, bit = section.fields[field_name]
        rec_off = section.records_offset + li * 52
        rec_data = self.data[rec_off:rec_off+52]
        return get_bits(rec_data, bit, size)
    
    def set_field(self, global_idx, field_name, value):
        """Set field value for player by global index."""
        if global_idx >= len(self.index):
            raise IndexError(f"Player {global_idx} out of range")
        si, li = self.index[global_idx]
        section = self.sections[si]
        
        if field_name not in section.fields:
            raise KeyError(f"Unknown field: {field_name}")
        
        size, bit = section.fields[field_name]
        max_val = (1 << size) - 1
        if not (0 <= value <= max_val):
            raise ValueError(f"Value {value} out of range for {field_name}")
        
        rec_off = section.records_offset + li * 52
        rec_data = self.data[rec_off:rec_off+52]
        new_data = set_bits(rec_data, bit, size, value)
        self.data[rec_off:rec_off+52] = new_data
    
    def save(self, output_path):
        """Save modified LEAGUE.DAT."""
        Path(output_path).write_bytes(bytes(self.data))
        print(f"Saved to {output_path}")


def patch_iso(iso_path, league_dat_path, output_iso_path):
    """
    Patch an ISO with a modified LEAGUE.DAT.
    
    This does an in-place replacement: the modified LEAGUE.DAT must be
    the same size as the original (2,176,504 bytes).
    """
    iso_path = Path(iso_path)
    league_dat_path = Path(league_dat_path)
    output_iso_path = Path(output_iso_path)
    
    # Read modified LEAGUE.DAT
    league_data = league_dat_path.read_bytes()
    if len(league_data) != LEAGUE_DAT_SIZE:
        raise ValueError(f"LEAGUE.DAT must be {LEAGUE_DAT_SIZE} bytes, got {len(league_data)}")
    
    # Copy ISO and patch
    print(f"Reading ISO: {iso_path}")
    print(f"  This may take a moment for large ISOs...")
    
    # For large ISOs, we can do a streaming copy with patch
    # But for simplicity, read fully (2GB is okay on desktop)
    import shutil
    print(f"Copying ISO to {output_iso_path}...")
    shutil.copy2(iso_path, output_iso_path)
    
    print(f"Patching LEAGUE.DAT at offset 0x{LEAGUE_DAT_ISO_OFFSET:X}...")
    with open(output_iso_path, 'r+b') as f:
        f.seek(LEAGUE_DAT_ISO_OFFSET)
        f.write(league_data)
    
    print("ISO patched successfully!")


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage:")
        print(f"  {sys.argv[0]} <league.dat> --list")
        print(f"  {sys.argv[0]} <league.dat> --edit <player> <field> <value> --save <out.dat>")
        print(f"  {sys.argv[0]} --patch-iso <input.iso> <league.dat> <output.iso>")
        sys.exit(1)
    
    if sys.argv[1] == '--patch-iso':
        patch_iso(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        table = IsoPlayTable(sys.argv[1])
        if '--list' in sys.argv:
            for i in range(min(10, len(table.index))):
                try:
                    ppos = table.get_field(i, 'PPOS')
                    print(f"Player {i}: PPOS={ppos}")
                except:
                    break
