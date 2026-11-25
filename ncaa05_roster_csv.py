#!/usr/bin/env python3
"""
NCAA Football 2005 (GameCube) — roster CSV export / import.

MacDog850-style workflow for NCAA 05: dump the whole roster to a CSV
(edit names and ratings in a spreadsheet), import it back, and ship the
result as a mod package (see ncaa05_modpack.py).  The CSV is the human
face of the PLAY table; the package is the shippable form.

SOURCES (both verified against real data, 2026-11-17):
  * GCI save — the roster GCI's embedded DB (DB+0xA724, 7,324 records,
    52 bytes each).  Proven by the PLAY layout work of 2026-10-23.
  * ISO — the DEFAULT roster is a stored DB inside TEMPLATE.DAT at
    TEMPLATE+0x1BA340 (same 3-table directory, same 85-field PLAY schema,
    same 7,324 PGIDs in the same order as the roster GCI).  Proven by
    direct decode on the retail ISO (sha256 5e864afc...): 85 fields,
    7,324 non-zero records, PGID set identical to the GCI's.
    LEAGUE.DAT's team DBs carry YALP schema only — no player records
    live there, so LEAGUE.DAT is NOT a roster source.

CSV FORMAT (one row per player, keyed by PGID — the stable unique ID):
  pgid, team, first_name, last_name, <62 non-name PLAY field codes>
  * Field columns are in record bit order, header cells are
    "CODE" or "CODE:Friendly label" (labels from the editor's
    FIELD_LABELS where known).
  * The 23 name-letter fields (PF01-PF10, PL01-PL13) are NOT separate
    columns: names are carried as the decoded first_name/last_name
    strings and re-encoded into the letter fields on import.
  * RCHD (16 bits @ 0) overlaps PHED (4 bits @ 0); import writes
    fields in bit order, wider first, so RCHD lands before PHED and a
    read-back pass verifies every field afterwards.
  * team comes from pgid_team_mapping.csv (decoded from LEAGUE.DAT's
    TEAM table + per-team DBs, 2026-11-17; TGID = PGID // 70).  No
    PLAY field carries a team, so the column is informational:
    export fills it from the mapping; import checks a non-empty
    value against the mapping and REFUSES a mismatch rather than
    silently dropping it (a CSV cannot move a player between
    teams — team is derived from the player ID).  An empty team
    value is accepted, so CSVs exported before the mapping existed
    still import.

SAFETY (same rules as the desktop editor):
  * Import NEVER overwrites its input: it writes a new file.
  * Import validates EVERYTHING first (row count, PGID set, names,
    field ranges, team column) and writes nothing if anything fails.
  * After applying, every field of every record is read back and
    compared to the CSV; any mismatch aborts the write.
  * A backup of the source is written first (GCI: whole file to
    <source>.bak if not already present; ISO: the TEMPLATE.DAT bytes
    to <source>.template.bak if not already present).
  * Name import writes the letters plus ONE terminator 0 and
    preserves any stale values in letter slots past the terminator
    (the roster GCI carries a stale 'b' at PL12 on 6 of its 7 named
    players).  Decode stops at the first 0, so those bits are
    invisible to every reader; preserving them is what makes an
    unchanged import byte-identical.  The editor's own
    set_player_name still zeroes all slots (existing behavior).
  * Name characters outside the 6-bit alphabet (a-z, A-Z, '-', "'",
    '.', ' ', '@', '+/-') are reported per row and refuse the import
    — never silently replaced with a space.  Over-long names
    (first > 10, last > 13) are likewise refused, never truncated.

KNOWN GAPS (reported, not papered over):
  * Default-roster players have NO names in the PLAY records
    (TEMPLATE.DAT: 0 of 7,324 named; the roster GCI has 7 named —
    created players).  The CSV is therefore the vehicle for ADDING
    names to the default roster, exactly like MacDog850's
    "2002 Roster Name Update" for Xbox 2K3.
  * The PWA port is a follow-up round: the desktop module is the
    reference implementation.
"""

import csv
import hashlib
import shutil
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from gci_play_parser import (
    ALPHABET, CHAR_TO_VAL, GCIPlayTable, corrected_fields, decode_name,
    encode_name, get_bits, parse_schema, set_bits,
    GCI_DB_SIZE, PLAY_FIELD_START_OVERRIDES,
    PLAY_RECORDS_OFFSET, PLAY_RECORD_SIZE,
)
from ncaa05_db import find_iso_file, GAME_ID

# ---------------------------------------------------------------- constants

# TEMPLATE.DAT layout inside the ISO (verified on the retail ISO).
TEMPLATE_DB_OFFSET = 0x1BA340
TEMPLATE_DB_SIZE = 0x730E0
EXPECTED_RECORD_COUNT = 7324

# pgid -> team name, decoded from LEAGUE.DAT (TEAM table + per-team
# DBs, 2026-11-17; TGID = PGID // 70).  Data file next to this module.
TEAM_MAPPING_PATH = Path(__file__).parent / 'pgid_team_mapping.csv'
_team_mapping_cache = None

# Name-letter fields are carried as decoded strings, not columns.
NAME_FIELDS = {f'PF{i:02d}' for i in range(1, 11)} | \
              {f'PL{i:02d}' for i in range(1, 14)}

# Friendly labels for CSV headers (same dictionary as the desktop
# editor's FIELD_LABELS, plus the name-letter pattern).
FIELD_LABELS = {
    'PGID': 'Player ID', 'PPOS': 'Position', 'PJEN': 'Jersey Number',
    'PHGT': 'Height', 'PWGT': 'Weight', 'PTEN': 'Tendency',
    'POVR': 'Overall', 'PTHA': 'Throw Accuracy', 'PTHP': 'Throw Power',
    'PSPD': 'Speed', 'PACC': 'Acceleration', 'PAGI': 'Agility',
    'PAWR': 'Awareness', 'PSTR': 'Strength', 'PSTA': 'Stamina',
    'PCTH': 'Catching', 'PCAR': 'Carrying', 'PBTK': 'Break Tackle',
    'PTAK': 'Tackling', 'PPBK': 'Pass Block', 'PRBK': 'Run Block',
    'PKAC': 'Kick Accuracy', 'PKPR': 'Kick Power', 'PKPW': 'Kick Power',
    'PJMP': 'Jumping', 'PINJ': 'Injury', 'PHED': 'Head',
    'PHCL': 'Hair Color', 'PEYE': 'Eye Paint', 'PVIS': 'Visor',
}


def _field_label(code):
    if code in FIELD_LABELS:
        return FIELD_LABELS[code]
    return None


def _csv_columns(fields):
    """Column order: keys first, then the 62 non-name fields in bit
    order (ties: wider field first, so RCHD lands before PHED)."""
    non_name = [(c, s, b) for c, (s, b) in fields.items()
                if c not in NAME_FIELDS]
    non_name.sort(key=lambda t: (t[2], -t[1], t[0]))
    cols = ['pgid', 'team', 'first_name', 'last_name']
    for code, _size, _bit in non_name:
        label = _field_label(code)
        cols.append(f'{code}:{label}' if label else code)
    return cols


def _column_code(header_cell):
    """'PPOS:Position' -> 'PPOS'; 'PJEN' -> 'PJEN'."""
    return header_cell.split(':', 1)[0]


class RosterCsvError(Exception):
    """Raised with a human-readable list of problems; nothing is written."""


# ---------------------------------------------------------------- sources

class GciRoster:
    """Roster source backed by a GCI save (wraps GCIPlayTable)."""

    kind = 'gci'

    def __init__(self, path=None, table=None):
        if table is not None:
            self.table = table
            self.path = Path(table.gci_path)
        else:
            self.path = Path(path)
            self.table = GCIPlayTable(str(self.path))
        self.fields = self.table.fields
        self.record_count = self.table.record_count
        self._pgid_index = None

    def pgid(self, i):
        return self.table.get_field(i, 'PGID')

    def get_field(self, i, code):
        return self.table.get_field(i, code)

    def set_field(self, i, code, value):
        self.table.set_field(i, code, value)

    def get_player_name(self, i):
        return self.table.get_player_name(i)

    def set_player_name(self, i, first, last):
        self.table.set_player_name(i, first, last)

    def raw_record(self, i):
        return bytes(self.table.get_record(i))

    def pgid_set(self):
        if self._pgid_index is None:
            self._pgid_index = {
                self.pgid(i): i for i in range(self.record_count)}
        return self._pgid_index

    def modified_bytes(self):
        """Full GCI bytes with the in-memory DB applied."""
        gci = bytearray(self.table.gci_data)
        gci[self.table.db_offset:
            self.table.db_offset + len(self.table.db_data)] = \
            self.table.db_data
        return bytes(gci)

    def write(self, out_path):
        out_path = Path(out_path)
        if out_path.resolve() == self.path.resolve():
            raise RosterCsvError(
                f"Refusing to overwrite the input GCI: {self.path}")
        _backup_once(self.path, self.path.with_suffix('.gci.bak'))
        self.table.save_gci(str(out_path))

    def verify(self):
        problems = []
        if self.record_count != EXPECTED_RECORD_COUNT:
            problems.append(
                f"record count {self.record_count} != "
                f"{EXPECTED_RECORD_COUNT}")
        if len(self.fields) != 85:
            problems.append(f"field count {len(self.fields)} != 85")
        if len(self.pgid_set()) != self.record_count:
            problems.append("PGIDs are not unique")
        return problems


class IsoRoster:
    """Roster source backed by the default roster DB inside an ISO's
    TEMPLATE.DAT (TEMPLATE+0x1BA340, verified on load)."""

    kind = 'iso'

    def __init__(self, iso_path):
        self.path = Path(iso_path)
        self.template_off, self.template_size, game_id = find_iso_file(
            str(self.path), 'TEMPLATE.DAT')
        if game_id != GAME_ID:
            print(f"Warning: game ID is {game_id} (expected {GAME_ID})")
        with open(self.path, 'rb') as f:
            f.seek(self.template_off)
            self.template_data = bytearray(f.read(self.template_size))
        self._load_db()

    def _load_db(self):
        if len(self.template_data) < TEMPLATE_DB_OFFSET + TEMPLATE_DB_SIZE:
            raise RosterCsvError(
                "TEMPLATE.DAT is shorter than the expected DB location "
                f"(needs {TEMPLATE_DB_OFFSET + TEMPLATE_DB_SIZE} bytes, "
                f"has {len(self.template_data)})")
        db = bytes(self.template_data[
            TEMPLATE_DB_OFFSET:TEMPLATE_DB_OFFSET + TEMPLATE_DB_SIZE])
        if db[:2] != b'DB':
            raise RosterCsvError(
                f"No DB marker at TEMPLATE+0x{TEMPLATE_DB_OFFSET:X} — "
                "wrong file or corrupted ISO.")
        size_field = struct.unpack('>I', db[8:12])[0]
        if size_field != TEMPLATE_DB_SIZE:
            raise RosterCsvError(
                f"DB size field 0x{size_field:X} != "
                f"0x{TEMPLATE_DB_SIZE:X} at TEMPLATE+0x{TEMPLATE_DB_OFFSET:X}")
        count = struct.unpack('>I', db[0x10:0x14])[0]
        entries = {}
        for i in range(count):
            o = 0x18 + i * 8
            try:
                name = db[o:o + 4].decode('ascii')
            except Exception:
                raise RosterCsvError("DB directory entry is not ASCII")
            entries[name] = struct.unpack('>I', db[o + 4:o + 8])[0]
        if entries.get('YALP') != 0xA138 or count != 3:
            raise RosterCsvError(
                f"DB directory mismatch at TEMPLATE+0x{TEMPLATE_DB_OFFSET:X}: "
                f"count={count}, entries={entries} "
                "(expected 3 entries with YALP at 0xA138)")
        self.fields = corrected_fields(
            parse_schema(db), PLAY_FIELD_START_OVERRIDES)
        if len(self.fields) != 85:
            raise RosterCsvError(
                f"PLAY schema parsed to {len(self.fields)} fields != 85")
        self.db = bytearray(db)
        self.record_count = self._count_records()
        if self.record_count != EXPECTED_RECORD_COUNT:
            raise RosterCsvError(
                f"record run is {self.record_count} != "
                f"{EXPECTED_RECORD_COUNT}")
        self._pgid_index = None

    def _count_records(self):
        count = 0
        max_possible = (len(self.db) - PLAY_RECORDS_OFFSET) // PLAY_RECORD_SIZE
        for i in range(max_possible):
            off = PLAY_RECORDS_OFFSET + i * PLAY_RECORD_SIZE
            rec = self.db[off:off + PLAY_RECORD_SIZE]
            if len(rec) < PLAY_RECORD_SIZE or all(b == 0 for b in rec):
                break
            count += 1
        return count

    def _record_bytes(self, i):
        off = PLAY_RECORDS_OFFSET + i * PLAY_RECORD_SIZE
        return bytes(self.db[off:off + PLAY_RECORD_SIZE])

    def pgid(self, i):
        size, bit = self.fields['PGID']
        return get_bits(self._record_bytes(i), bit, size)

    def get_field(self, i, code):
        if code not in self.fields:
            raise KeyError(f"Unknown field: {code}")
        size, bit = self.fields[code]
        return get_bits(self._record_bytes(i), bit, size)

    def set_field(self, i, code, value):
        if code not in self.fields:
            raise KeyError(f"Unknown field: {code}")
        size, bit = self.fields[code]
        if not (0 <= value < (1 << size)):
            raise ValueError(
                f"Value {value} out of range for {code} (0-{(1 << size) - 1})")
        off = PLAY_RECORDS_OFFSET + i * PLAY_RECORD_SIZE
        rec = self._record_bytes(i)
        new = set_bits(rec, bit, size, value)
        self.db[off:off + PLAY_RECORD_SIZE] = new

    def get_player_name(self, i):
        rec = self._record_bytes(i)
        return (decode_name(rec, self.fields, 'PF', 10),
                decode_name(rec, self.fields, 'PL', 13))

    def set_player_name(self, i, first, last):
        off = PLAY_RECORDS_OFFSET + i * PLAY_RECORD_SIZE
        rec = bytearray(self._record_bytes(i))
        for prefix, name, max_len in (('PF', first, 10), ('PL', last, 13)):
            vals = encode_name(name, max_len)
            for j, val in enumerate(vals, 1):
                fname = f'{prefix}{j:02d}'
                if fname not in self.fields:
                    continue
                size, bit = self.fields[fname]
                for b in range(size):
                    byte_idx = (bit + b) // 8
                    bit_idx = 7 - ((bit + b) % 8)
                    bit_val = (val >> (size - 1 - b)) & 1
                    if bit_val:
                        rec[byte_idx] |= (1 << bit_idx)
                    else:
                        rec[byte_idx] &= ~(1 << bit_idx)
        self.db[off:off + PLAY_RECORD_SIZE] = bytes(rec)

    def raw_record(self, i):
        return self._record_bytes(i)

    def pgid_set(self):
        if self._pgid_index is None:
            self._pgid_index = {
                self.pgid(i): i for i in range(self.record_count)}
        return self._pgid_index

    def modified_template_bytes(self):
        """Full TEMPLATE.DAT bytes with the in-memory DB applied."""
        out = bytearray(self.template_data)
        out[TEMPLATE_DB_OFFSET:TEMPLATE_DB_OFFSET + TEMPLATE_DB_SIZE] = \
            self.db
        return bytes(out)

    def write(self, out_path):
        """Write a NEW ISO with the modified TEMPLATE.DAT spliced in.
        The input ISO is never overwritten."""
        out_path = Path(out_path)
        if out_path.resolve() == self.path.resolve():
            raise RosterCsvError(
                f"Refusing to overwrite the input ISO: {self.path}")
        bak = self.path.with_suffix('.iso.template.bak')
        if not bak.exists():
            bak.write_bytes(bytes(self.template_data))
            print(f"Backed up original TEMPLATE.DAT to {bak.name}")
        print(f"Copying ISO to {out_path} ...")
        shutil.copy2(self.path, out_path)
        with open(out_path, 'r+b') as f:
            f.seek(self.template_off + TEMPLATE_DB_OFFSET)
            f.write(bytes(self.db))
        print(f"Wrote modified ISO to {out_path}")

    def verify(self):
        problems = []
        if self.record_count != EXPECTED_RECORD_COUNT:
            problems.append(
                f"record count {self.record_count} != "
                f"{EXPECTED_RECORD_COUNT}")
        if len(self.pgid_set()) != self.record_count:
            problems.append("PGIDs are not unique")
        return problems


def _backup_once(source_path, backup_path):
    backup_path = Path(backup_path)
    if not backup_path.exists():
        shutil.copy2(source_path, backup_path)
        print(f"Backed up original to {backup_path.name}")


def load_roster(path):
    """Load a roster source from a .gci save or a .iso image."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == '.gci':
        return GciRoster(path)
    if suffix == '.iso':
        return IsoRoster(path)
    raise RosterCsvError(
        f"Unsupported roster source: {path} (need .gci or .iso)")


# ---------------------------------------------------------------- CSV

def _load_team_mapping():
    """Load pgid -> team name from TEAM_MAPPING_PATH.  A missing or
    unreadable file degrades to {} (export leaves team blank; import
    then only accepts empty team values) instead of crashing."""
    global _team_mapping_cache
    if _team_mapping_cache is None:
        mapping = {}
        try:
            with open(TEAM_MAPPING_PATH, newline='',
                      encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    try:
                        mapping[int(row['pgid'])] = row['team']
                    except (KeyError, TypeError, ValueError):
                        continue
        except OSError:
            mapping = {}
        _team_mapping_cache = mapping
    return _team_mapping_cache


def export_csv(source, csv_path):
    """Dump every player to CSV. Returns (rows, named_count)."""
    problems = source.verify()
    if problems:
        raise RosterCsvError(
            "Source failed verification: " + "; ".join(problems))
    cols = _csv_columns(source.fields)
    codes = [_column_code(c) for c in cols[4:]]
    mapping = _load_team_mapping()
    named = 0
    unmapped = 0
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(cols)
        for i in range(source.record_count):
            first, last = source.get_player_name(i)
            if first or last:
                named += 1
            pgid = source.pgid(i)
            team = mapping.get(pgid)
            if team is None:
                unmapped += 1
                team = ''
            row = [pgid, team, first, last]
            row += [source.get_field(i, code) for code in codes]
            w.writerow(row)
    print(f"Exported {source.record_count} players "
          f"({named} named) to {csv_path}")
    if unmapped:
        print(f"Note: {unmapped} player(s) have no team in "
              f"{TEAM_MAPPING_PATH.name}; team left blank")
    return source.record_count, named


def _validate_name(value, max_len, row_no, field, errors):
    """Name rules: length cap + alphabet only. Returns True if OK."""
    if len(value) > max_len:
        errors.append(
            f"row {row_no}: {field} '{value}' is {len(value)} chars "
            f"(max {max_len}) — over-long names are refused, never "
            "truncated")
        return False
    bad = sorted({c for c in value if c not in CHAR_TO_VAL})
    if bad:
        errors.append(
            f"row {row_no}: {field} '{value}' uses characters the "
            f"6-bit alphabet cannot store: {bad} — unsupported "
            "characters are refused, never replaced with a space")
        return False
    return True


def _set_name_preserving(source, i, first, last):
    """Write a name the way the CSV import does: the name's letters,
    then ONE terminator 0, leaving every letter slot past the
    terminator untouched.

    Why: decode stops at the first 0, so a value in a slot past the
    terminator is invisible to every reader — but the roster GCI
    carries exactly that (a stale 'b', value 2, at PL12 on 6 of its
    7 named players, left over from an earlier longer name).  The
    editor's set_player_name zeroes ALL slots, which would clear
    those bits and break the no-change round-trip.  Writing letters
    + one terminator preserves them, so an unchanged import is
    byte-identical, while a shortened name still terminates cleanly
    (the old letters past the new terminator stay invisible)."""
    for prefix, name, max_len in (('PF', first, 10), ('PL', last, 13)):
        vals = [CHAR_TO_VAL[c] for c in name[:max_len]]
        for j, val in enumerate(vals, 1):
            source.set_field(i, f'{prefix}{j:02d}', val)
        if len(vals) < max_len:
            source.set_field(i, f'{prefix}{len(vals) + 1:02d}', 0)


def _overlapping_pairs(fields):
    """Pairs of fields whose bit ranges intersect.  In the 05 PLAY
    schema this is exactly one pair: RCHD (16 bits @ 0) overlaps
    PHED (4 bits @ 0) — the same physical bits viewed two ways."""
    items = sorted(fields.items(), key=lambda kv: (kv[1][1], kv[0]))
    pairs = []
    for x in range(len(items)):
        for y in range(x + 1, len(items)):
            ca, (sa, ba) = items[x]
            cb, (sb, bb) = items[y]
            if ba + sa <= bb:
                break
            if max(ba, bb) < min(ba + sa, bb + sb):
                pairs.append((ca, cb))
    return pairs


def _overlap_errors(fields, values, row_no, errors):
    """Check the CSV's values agree on shared bits.  RCHD/PHED:
    PHED must equal the top 4 bits of RCHD."""
    for ca, cb in _overlapping_pairs(fields):
        if ca not in values or cb not in values:
            continue  # already reported as a bad value above
        sa, ba = fields[ca]
        sb, bb = fields[cb]
        lo = max(ba, bb)
        hi = min(ba + sa, bb + sb)
        va, vb = values[ca], values[cb]
        ok = True
        for p in range(lo, hi):
            bit_a = (va >> (sa - 1 - (p - ba))) & 1
            bit_b = (vb >> (sb - 1 - (p - bb))) & 1
            if bit_a != bit_b:
                ok = False
                break
        if not ok:
            errors.append(
                f"row {row_no}: {ca}={va} conflicts with {cb}={vb} — "
                f"they share the same bits ({ca} is {sa} bits @ {ba}, "
                f"{cb} is {sb} bits @ {bb}), so their values must "
                "agree on the overlap")


def import_csv(source, csv_path):
    """Read a CSV and apply it to the source IN MEMORY (no file is
    written here — call source.write() afterwards).  Validates
    everything first; on any error raises RosterCsvError with the
    full list and applies nothing.  Returns the number of players
    whose bytes changed."""
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise RosterCsvError("CSV has no header row")
        # Normalize keys: header cells are "CODE" or "CODE:Label";
        # data rows are keyed by plain field code from here on.
        rows = [{_column_code(k): (v if v is not None else '')
                 for k, v in row.items()}
                for row in reader]

    problems = source.verify()
    if problems:
        raise RosterCsvError(
            "Source failed verification: " + "; ".join(problems))

    expected_cols = _csv_columns(source.fields)
    got_cols = [_column_code(c) for c in reader.fieldnames]
    if got_cols != [_column_code(c) for c in expected_cols]:
        missing = [c for c in expected_cols if _column_code(c) not in got_cols]
        extra = [c for c in reader.fieldnames
                 if _column_code(c) not in
                 [_column_code(c) for c in expected_cols]]
        raise RosterCsvError(
            "CSV header does not match this roster's columns. "
            f"Missing: {missing or 'none'}. Extra: {extra or 'none'}.")

    field_codes = [_column_code(c) for c in expected_cols[4:]]
    errors = []

    # --- row count + PGID set (full-roster import only) ---
    if len(rows) != source.record_count:
        errors.append(
            f"CSV has {len(rows)} rows, roster has "
            f"{source.record_count} — import takes the full roster only, "
            "export it, edit it, and import the whole file back")
    pgid_index = source.pgid_set()
    seen = {}
    for n, row in enumerate(rows, 2):
        raw = (row.get('pgid') or '').strip()
        try:
            pgid = int(raw)
        except ValueError:
            errors.append(f"row {n}: pgid '{raw}' is not an integer")
            continue
        if pgid not in pgid_index:
            errors.append(
                f"row {n}: pgid {pgid} is not in this roster")
        elif pgid in seen:
            errors.append(
                f"row {n}: pgid {pgid} appears twice "
                f"(rows {seen[pgid]} and {n})")
        else:
            seen[pgid] = n

    # --- team column: derived from PGID via pgid_team_mapping.csv ---
    # Team is a function of the player ID (TGID = PGID // 70), so a
    # CSV cannot move a player between teams: the value is checked,
    # never applied.  Empty is accepted (CSVs exported before the
    # mapping existed); a non-empty value must match the mapping
    # exactly or the import is refused.
    mapping = _load_team_mapping()
    for n, row in enumerate(rows, 2):
        team = (row.get('team') or '').strip()
        if not team:
            continue
        try:
            pgid = int((row.get('pgid') or '').strip())
        except ValueError:
            continue  # already reported above
        if pgid not in pgid_index:
            continue  # already reported above
        expected = mapping.get(pgid)
        if expected is None:
            errors.append(
                f"row {n}: team '{team}' cannot be verified — pgid "
                f"{pgid} is not in {TEAM_MAPPING_PATH.name}; leave "
                "the team column empty")
        elif team != expected:
            errors.append(
                f"row {n}: team '{team}' does not match pgid {pgid} "
                f"(expected '{expected}') — team comes from the "
                "player ID, so a CSV cannot move a player between "
                "teams")

    # --- names + field values ---
    for n, row in enumerate(rows, 2):
        _validate_name((row.get('first_name') or ''), 10,
                       n, 'first_name', errors)
        _validate_name((row.get('last_name') or ''), 13,
                       n, 'last_name', errors)
        values = {}
        for code in field_codes:
            raw = (row.get(code) or '').strip()
            try:
                value = int(raw)
            except ValueError:
                errors.append(
                    f"row {n}: {code} '{raw}' is not an integer")
                continue
            size, _bit = source.fields[code]
            if not (0 <= value < (1 << size)):
                errors.append(
                    f"row {n}: {code}={value} out of range "
                    f"(0-{(1 << size) - 1})")
            values[code] = value
        if values:
            _overlap_errors(source.fields, values, n, errors)

    if errors:
        raise RosterCsvError(
            f"CSV import refused ({len(errors)} problem(s)):\n" +
            "\n".join(f"  - {e}" for e in errors[:40]) +
            (f"\n  ... and {len(errors) - 40} more" if len(errors) > 40 else ""))

    # --- apply (bit order, wider first so RCHD lands before PHED) ---
    ordered = sorted(source.fields.items(),
                     key=lambda kv: (kv[1][1], -kv[1][0], kv[0]))
    apply_order = [c for c, _ in ordered
                   if c in field_codes]
    before = [source.raw_record(i) for i in range(source.record_count)]
    for row in rows:
        pgid = int(row['pgid'])
        i = pgid_index[pgid]
        for code in apply_order:
            source.set_field(i, code, int((row.get(code) or '').strip()))
        first = (row.get('first_name') or '')
        last = (row.get('last_name') or '')
        _set_name_preserving(source, i, first, last)

    # --- read-back verification: every field of every record + names ---
    mismatches = 0
    for row in rows:
        pgid = int(row['pgid'])
        i = pgid_index[pgid]
        for code in field_codes:
            raw = (row.get(code) or '').strip()
            if source.get_field(i, code) != int(raw):
                mismatches += 1
                if mismatches <= 5:
                    print(f"  read-back mismatch: pgid {pgid} {code} "
                          f"expected {raw}, got {source.get_field(i, code)}")
        first, last = source.get_player_name(i)
        if first != (row.get('first_name') or '') or \
                last != (row.get('last_name') or ''):
            mismatches += 1
            if mismatches <= 5:
                print(f"  read-back mismatch: pgid {pgid} name "
                      f"expected '{row.get('first_name') or ''} "
                      f"{row.get('last_name') or ''}', got '{first} {last}'")
    if mismatches:
        raise RosterCsvError(
            f"Read-back verification failed ({mismatches} mismatched "
            "field(s)) — nothing was written. This is a bug, not a "
            "bad CSV; report it with the CSV attached.")

    changed = sum(1 for i in range(source.record_count)
                  if source.raw_record(i) != before[i])
    print(f"CSV applied in memory: {changed} of {source.record_count} "
          "records changed (call source.write() to save)")
    return changed


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _utcnow():
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        description="NCAA 05 GameCube roster CSV export/import")
    sub = ap.add_subparsers(dest='cmd', required=True)
    e = sub.add_parser('export', help='dump a roster to CSV')
    e.add_argument('source', help='.gci save or .iso image')
    e.add_argument('csv', help='output CSV path')
    i = sub.add_parser('import', help='apply a CSV to a roster copy')
    i.add_argument('source', help='.gci save or .iso image (never overwritten)')
    i.add_argument('csv', help='input CSV path')
    i.add_argument('-o', '--output', required=True,
                   help='output .gci/.iso path (must differ from source)')
    args = ap.parse_args(argv)

    if args.cmd == 'export':
        source = load_roster(args.source)
        export_csv(source, args.csv)
    else:
        source = load_roster(args.source)
        import_csv(source, args.csv)
        source.write(args.output)
    return 0


if __name__ == '__main__':
    sys.exit(main())
