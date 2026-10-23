#!/usr/bin/env python3
"""
NCAA Football 2005 (GameCube) GCI Save — Generic EA DB Table Parser

Generalises gci_play_parser.py from the single PLAY table to every table
listed in a GCI save's embedded EA database (DB) directory.

Empirical layout (reverse-engineered from
~/workspace/recon/ncaa05/gci/ncaa05_roster.gci, Oct 23 2026):

- The GCI contains one DB blob: first b'DB' in the file, total size is the
  BE32 at DB+8 (0x730E0 for the roster GCI; same value GCIPlayTable uses).
- DB directory: BE32 table count at DB+0x10, then count entries at
  DB+0x18, each [4-char GameCube (reversed) name][BE32 value].  In the
  roster GCI: count=3 — THCD (DCHT) value 0x0, YALP (PLAY) value 0xA138,
  NYDT (TDYN) value 0x72658.  There is NO TEAM (MAET) or COCH (HCOC)
  entry in this file, and those byte strings occur nowhere in the DB.
- Each table's block starts at its directory value V:
    V+0x30  4 hash bytes
    V+0x34  BE32 (2 for PLAY/TDYN, 6 for DCHT — meaning unconfirmed)
    V+0x38  BE32 record size in bytes (PLAY 52, DCHT 4, TDYN 20)
    V+0x3C  BE32 record bits - 1 (415, 31, 159 — matches record size)
    V+0x40  BE32 0
    V+0x44  4 bytes (TDYN: 00 77 00 77 = 119, 119 — matches its record
            count twice; PLAY/DCHT hold hash-like values)
    V+0x48  00 00 FF FF
    V+0x4C  1 byte = descriptor count + 1 (PLAY 86 vs 85 parsed,
            DCHT 3 vs 2, TDYN 14 vs 13), then 7 zero bytes
    V+0x54  4 hash bytes
    V+0x58  BE32 3
    V+0x5C  BE32 (PLAY 40, DCHT 0, TDYN 32 — meaning unconfirmed)
    V+0x60  field descriptors — parsed with gci_play_parser.parse_schema,
            the exact function the PLAY parser uses.
- Records follow the schema after a short table-specific data header:
    PLAY  schema ends DB+0xA6E8, "YSLP" header, records at DB+0xA708
          (== gci_play_parser.PLAY_RECORDS_OFFSET), 52 bytes each.
    DCHT  schema ends DB+0x80, "pedd" + 4 bytes, records at DB+0x88,
          4 bytes each; 7,728 consecutive non-zero records, then zero
          padding (next non-zero structure is far later in the region).
    TDYN  schema ends DB+0x72788, "VORT" + 8 bytes, records at
          DB+0x72794, 20 bytes each; (DB end - 0x72794) / 20 == 119
          exactly, filling the DB to its last byte.

Field access uses the SAME convention as gci_play_parser.GCIPlayTable:
the descriptor's stored word is the field's starting bit offset, bits are
MSB-first (get_bits/set_bits from gci_play_parser).  For PLAY this parser
is validated to reproduce GCIPlayTable exactly (same 85 fields, same
2,000 records, same values).  For TDYN the convention decodes cleanly:
the 8-bit team-rating fields (TRLB/TRQB/TRDE/TROF/TROL/...) land on
plausible rating bytes (64-95) in all 119 records.  For DCHT the two
fields (PGID/PPOS) round-trip through get/set like every other field;
the array at DB+0x88 reads as a PGID-ordered index (PGID = first u16
under an end-exclusive reading) — its exact in-game semantics are not
fully confirmed, and this parser does not claim otherwise.

Known limitation (pre-existing, not introduced here): whether the PLAY
record bytes at DB+0xA708 decode to semantically plausible players was
already flagged as unresolved in the Oct 12 2026 recon notes
(~/workspace/recon/ncaa05/YALP_LOCATION_FINDINGS_2026-10-12.md §4).  This
parser deliberately reproduces the shipped parser's PLAY behaviour
bit-for-bit instead of inventing a new PLAY theory.
"""

from pathlib import Path
import struct

from gci_play_parser import (
    get_bits, set_bits, gc_to_pc_name, parse_schema, decode_name,
    encode_name, GCI_DB_SIZE, PLAY_RECORDS_OFFSET, PLAY_RECORD_SIZE,
)

# DB directory constants (DB-relative)
DIR_COUNT_OFFSET = 0x10
DIR_ENTRIES_OFFSET = 0x18
DIR_ENTRY_SIZE = 8  # [name:4][value:BE32]

# Table block constants (relative to the table's directory value V)
HDR_RECORD_SIZE_OFFSET = 0x38
HDR_RECORD_BITS_OFFSET = 0x3C
HDR_FIELD_COUNT_OFFSET = 0x4C
SCHEMA_OFFSET_FROM_VALUE = 0x60

# Empirically derived record placement for the tables in the roster GCI.
# PLAY uses the shipped parser's constants verbatim.  For tables not in
# this map (e.g. TEAM/COCH in a dynasty save), a documented heuristic is
# used: records start 8 bytes after the schema ends and the record count
# is the run of consecutive non-zero records inside the table's region.
KNOWN_RECORD_LAYOUT = {
    # pc_name: (data_header_len_after_schema, count_mode)
    'PLAY': (PLAY_RECORDS_OFFSET - 0xA6E8, 'legacy'),   # header len 32
    'DCHT': (8, 'nonzero_run'),
    'TDYN': (12, 'fill_to_region_end'),
}


def _schema_end(db_data, schema_offset):
    """Walk descriptors exactly like parse_schema and return the offset
    where parsing stops (first byte after the last descriptor)."""
    off = schema_offset
    count = 0
    while off + 16 <= len(db_data):
        name_bytes = db_data[off:off + 4]
        if name_bytes[:3] == b'\x21\x00\x04':
            off += 3
            continue
        try:
            name = name_bytes.decode('ascii')
        except Exception:
            break
        if not all(c.isalnum() or c == '_' for c in name):
            break
        size = struct.unpack('>I', db_data[off + 4:off + 8])[0]
        ftype = struct.unpack('>I', db_data[off + 8:off + 12])[0]
        if size > 5000 or ftype > 20:
            break
        if db_data[off + 12:off + 15] == b'\x21\x00\x04':
            off += 15
            count += 1
            continue
        bit_off = struct.unpack('>I', db_data[off + 12:off + 16])[0]
        if bit_off > 10000:
            break
        off += 16
        count += 1
        if count > 200:
            break
    return off


class GCITable:
    """One table in a GCI save's embedded DB (generic PLAY counterpart)."""

    def __init__(self, db, gc_name, dir_value, region_end):
        self._db = db  # GCIDatabase (owns the mutable DB bytearray)
        self.gc_name = gc_name
        self.name = gc_to_pc_name(gc_name)
        self.dir_value = dir_value
        self.region_end = region_end

        data = bytes(db.db_data)
        v = dir_value
        # Header words (see module docstring for the empirical layout)
        self.header_word_34 = struct.unpack('>I', data[v + 0x34:v + 0x38])[0]
        self.record_size = struct.unpack(
            '>I', data[v + HDR_RECORD_SIZE_OFFSET:v + HDR_RECORD_SIZE_OFFSET + 4])[0]
        self.record_bits = struct.unpack(
            '>I', data[v + HDR_RECORD_BITS_OFFSET:v + HDR_RECORD_BITS_OFFSET + 4])[0]
        self.header_field_count_byte = data[v + HDR_FIELD_COUNT_OFFSET]
        self.header_word_5c = struct.unpack('>I', data[v + 0x5C:v + 0x60])[0]

        # Schema — the exact parser the PLAY parser uses
        self.schema_offset = v + SCHEMA_OFFSET_FROM_VALUE
        self.fields = parse_schema(data, self.schema_offset)
        self.schema_end = _schema_end(data, self.schema_offset)

        # Records
        self.records_offset, self.record_count = self._locate_records(data)

    # -- record location -------------------------------------------------
    def _locate_records(self, data):
        layout = KNOWN_RECORD_LAYOUT.get(self.name)
        if self.name == 'PLAY':
            # Reproduce gci_play_parser exactly: fixed offset/size, and
            # the record count comes from GCIPlayTable's own algorithm.
            return PLAY_RECORDS_OFFSET, self._db._legacy_play_count

        if layout is not None:
            header_len, count_mode = layout
        else:
            header_len, count_mode = 8, 'nonzero_run'

        records_offset = self.schema_end + header_len
        region_end = self.region_end

        if count_mode == 'fill_to_region_end':
            span = region_end - records_offset
            count = span // self.record_size if self.record_size else 0
            return records_offset, count

        # 'nonzero_run': consecutive records that are not all zero,
        # bounded by the table's region.
        count = 0
        max_records = (region_end - records_offset) // self.record_size
        for i in range(max_records):
            off = records_offset + i * self.record_size
            rec = data[off:off + self.record_size]
            if len(rec) < self.record_size or all(b == 0 for b in rec):
                break
            count += 1
        return records_offset, count

    # -- record / field access (same bit logic as GCIPlayTable) ----------
    def get_record(self, index):
        if index >= self.record_count:
            raise IndexError(
                f"Record {index} out of range ({self.record_count})")
        off = self.records_offset + index * self.record_size
        return bytes(self._db.db_data[off:off + self.record_size])

    def get_field(self, index, field_name):
        if field_name not in self.fields:
            raise KeyError(f"Unknown field: {field_name}")
        size, bit = self.fields[field_name]
        data = self.get_record(index)
        return get_bits(data, bit, size)

    def set_field(self, index, field_name, value):
        if field_name not in self.fields:
            raise KeyError(f"Unknown field: {field_name}")
        size, bit = self.fields[field_name]
        max_val = (1 << size) - 1
        if value < 0 or value > max_val:
            raise ValueError(
                f"Value {value} out of range for {field_name} (0-{max_val})")
        rec_off = self.records_offset + index * self.record_size
        rec_data = bytes(self._db.db_data[rec_off:rec_off + self.record_size])
        new_data = set_bits(rec_data, bit, size, value)
        self._db.db_data[rec_off:rec_off + self.record_size] = new_data

    # -- PLAY-style name helpers (only meaningful when PF/PL fields exist)
    def get_player_name(self, index):
        data = self.get_record(index)
        first = decode_name(data, self.fields, 'PF', 10)
        last = decode_name(data, self.fields, 'PL', 13)
        return first, last

    def set_player_name(self, index, first_name, last_name):
        """Identical algorithm to GCIPlayTable.set_player_name."""
        first_vals = encode_name(first_name, 10)
        last_vals = encode_name(last_name, 13)
        rec_off = self.records_offset + index * self.record_size
        rec_data = bytearray(
            bytes(self._db.db_data[rec_off:rec_off + self.record_size]))

        for i, val in enumerate(first_vals, 1):
            fname = f'PF{i:02d}'
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

        self._db.db_data[rec_off:rec_off + self.record_size] = bytes(rec_data)


class GCIDatabase:
    """A GCI save's embedded EA database: all tables in its directory."""

    def __init__(self, gci_path):
        self.gci_path = Path(gci_path)
        self.gci_data = self.gci_path.read_bytes()

        # DB location/size — same derivation as GCIPlayTable (its size
        # constant is the BE32 stored at DB+8 in this file; fall back to
        # the constant if the stored value looks wrong).
        self.db_offset = self.gci_data.find(b'DB')
        if self.db_offset < 0:
            raise ValueError("No DB marker found in GCI")
        stored_size = struct.unpack(
            '>I', self.gci_data[self.db_offset + 8:self.db_offset + 12])[0]
        if 0 < stored_size <= len(self.gci_data) - self.db_offset:
            self.db_size = stored_size
        else:
            self.db_size = GCI_DB_SIZE
        self.db_data = bytearray(
            self.gci_data[self.db_offset:self.db_offset + self.db_size])

        # Legacy PLAY count, computed with GCIPlayTable's own algorithm
        # so the generic PLAY table matches it exactly.
        self._legacy_play_count = self._count_legacy_play_records()

        # Directory
        self.tables = {}
        self.table_order = []
        entries = self._parse_directory()
        values = [value for _, value in entries]
        for i, (gc_name, value) in enumerate(entries):
            region_end = values[i + 1] if i + 1 < len(values) else self.db_size
            table = GCITable(self, gc_name, value, region_end)
            self.tables[table.name] = table
            self.table_order.append(table.name)

    def _count_legacy_play_records(self):
        """Verbatim copy of GCIPlayTable._count_records' counting loop
        (caps at 2,000 records), run against this DB's bytes."""
        records_offset = PLAY_RECORDS_OFFSET
        record_size = PLAY_RECORD_SIZE
        data = bytes(self.db_data)
        max_possible = (len(data) - records_offset) // record_size
        count = 0
        for i in range(min(max_possible, 10000)):
            rec_off = records_offset + i * record_size
            rec = data[rec_off:rec_off + record_size]
            if len(rec) < record_size:
                break
            count += 1
            if count >= 2000:
                break
        return count

    def _parse_directory(self):
        """Parse the DB table directory. Returns [(gc_name, value), ...]."""
        data = bytes(self.db_data)
        if len(data) < DIR_ENTRIES_OFFSET + DIR_ENTRY_SIZE:
            return []
        count = struct.unpack(
            '>I', data[DIR_COUNT_OFFSET:DIR_COUNT_OFFSET + 4])[0]
        if count <= 0 or count > 64:
            return []
        entries = []
        for i in range(count):
            off = DIR_ENTRIES_OFFSET + i * DIR_ENTRY_SIZE
            name_bytes = data[off:off + 4]
            try:
                gc_name = name_bytes.decode('ascii')
            except Exception:
                break
            if not all(c.isalnum() or c == '_' for c in gc_name):
                break
            value = struct.unpack('>I', data[off + 4:off + 8])[0]
            entries.append((gc_name, value))
        return entries

    def save_gci(self, output_path):
        """Write the GCI back with the (possibly modified) DB bytes."""
        gci_list = bytearray(self.gci_data)
        gci_list[self.db_offset:self.db_offset + len(self.db_data)] = \
            bytes(self.db_data)
        Path(output_path).write_bytes(bytes(gci_list))
        print(f"Saved modified GCI to {output_path}")


def main():
    import sys
    if len(sys.argv) < 2:
        print("Usage: gci_db_parser.py <gci_file>")
        sys.exit(1)
    db = GCIDatabase(sys.argv[1])
    print(f"DB at file offset 0x{db.db_offset:X}, size 0x{db.db_size:X}")
    print(f"Tables ({len(db.tables)}):")
    for name in db.table_order:
        t = db.tables[name]
        print(f"  {t.gc_name} ({name}): dir value 0x{t.dir_value:X}, "
              f"schema at DB+0x{t.schema_offset:X} ({len(t.fields)} fields), "
              f"records at DB+0x{t.records_offset:X} "
              f"({t.record_count} x {t.record_size} bytes)")


if __name__ == '__main__':
    main()
