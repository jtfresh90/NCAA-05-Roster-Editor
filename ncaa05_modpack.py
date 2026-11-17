#!/usr/bin/env python3
"""
NCAA Football 2005 (GameCube) — mod packages.

The shippable form of a roster edit, in the shape of MacDog850's
NCAA 2K3 Mod Studio packages (format "ncaa2k3-mod-v1"): a zip holding
a manifest.json plus the changed file(s) as blobs.  Only the changed
roster file travels — never the whole ISO.

Package layout (mirrors the reference .2k3mod exactly):
  manifest.json
  blobs/<sha256>            # raw bytes of each changed file

Manifest (format "ncaa05-mod-v1"):
  {
    "format": "ncaa05-mod-v1",
    "name": "<user-given mod name>",
    "identity": {"sha256": "<whole base file sha256>",
                 "size": <base file bytes>,
                 "file": "<base file name>"},
    "changes": {
      "TEMPLATE.DAT": {"sha256": "<modified file sha256>",
                       "original_sha256": "<base file sha256>",
                       "size": <modified file bytes>,
                       "description": "<what the edit was>",
                       "time": "2026-11-17 16:50:00"},
      ... or "<gci file name>": {...} for GCI saves ...
    },
    "package_version": 1,
    "source": "NCAA Football 2005 GameCube ISO"
              | "NCAA Football 2005 GameCube GCI save"
  }

Rules (same safety posture as the CSV import):
  * A package is built from a source whose in-memory roster differs
    from its base; a no-change source refuses to pack.
  * Applying verifies, in order, and refuses on ANY mismatch:
    1. manifest format is "ncaa05-mod-v1" (a 2K3 pack is refused
       with a clear message, never misapplied);
    2. every blob's sha256 and size match the manifest (tamper check);
    3. the target file's whole-file sha256 matches identity.sha256
       (the pack was built against a different base);
    4. the target's current roster-file hash matches
       original_sha256 (the roster was already modified).
  * Applying never overwrites its input: it writes a new file, after
    backing the target's original roster bytes up first (same backup
    rule as the CSV import).
"""

import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from ncaa05_roster_csv import (
    IsoRoster, GciRoster, RosterCsvError, TEMPLATE_DB_OFFSET,
    TEMPLATE_DB_SIZE, _sha256_file, _utcnow, import_csv, load_roster,
)

FORMAT = "ncaa05-mod-v1"
PACKAGE_VERSION = 1

SOURCE_LABEL = {
    'iso': "NCAA Football 2005 GameCube ISO",
    'gci': "NCAA Football 2005 GameCube GCI save",
}


class ModpackError(Exception):
    """Raised when a package is refused; nothing is written."""


def _changed_file(source):
    """(key, original_bytes, modified_bytes) for the roster file."""
    if source.kind == 'iso':
        return ("TEMPLATE.DAT",
                bytes(source.template_data),
                source.modified_template_bytes())
    return (source.path.name,
            Path(source.path).read_bytes(),
            source.modified_bytes())


def export_pack(source, name, out_zip, description="Roster CSV import"):
    """Pack the source's current in-memory roster against its base.
    Returns (changed_key, modified_sha256)."""
    key, original, modified = _changed_file(source)
    return export_pack_bytes(source.kind, source.path, key,
                             original, modified, name, out_zip,
                             description)


def export_pack_bytes(kind, base_path, changed_key, original_bytes,
                      modified_bytes, name, out_zip,
                      description="Roster CSV import"):
    """Pack explicit byte strings (used when the caller merged edits
    from more than one in-memory store — e.g. the Player Editor's
    Players tab + Tables tab — before packing)."""
    if original_bytes == modified_bytes:
        raise ModpackError(
            "Nothing changed — the roster in memory is identical to "
            "the base. Make an edit (CSV import or editor change) "
            "before exporting a package.")
    mod_sha = hashlib.sha256(modified_bytes).hexdigest()
    orig_sha = hashlib.sha256(original_bytes).hexdigest()
    identity_sha = _sha256_file(base_path)
    manifest = {
        "format": FORMAT,
        "name": name,
        "identity": {
            "sha256": identity_sha,
            "size": Path(base_path).stat().st_size,
            "file": Path(base_path).name,
        },
        "changes": {
            changed_key: {
                "sha256": mod_sha,
                "original_sha256": orig_sha,
                "size": len(modified_bytes),
                "description": description,
                "time": _utcnow(),
            },
        },
        "package_version": PACKAGE_VERSION,
        "source": SOURCE_LABEL[kind],
    }
    out_zip = Path(out_zip)
    with zipfile.ZipFile(out_zip, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('manifest.json',
                   json.dumps(manifest, indent=2) + '\n')
        z.writestr(f'blobs/{mod_sha}', modified_bytes)
    print(f"Exported mod package {out_zip} ({changed_key}: "
          f"{len(original_bytes)} -> {len(modified_bytes)} bytes)")
    return changed_key, mod_sha


def build_pack(source_path, csv_path, name, out_zip,
               description="Roster CSV import"):
    """Load a roster, apply a CSV in memory, pack the result."""
    source = load_roster(source_path)
    import_csv(source, csv_path)
    return export_pack(source, name, out_zip, description)


def _read_manifest(pack_path):
    try:
        with zipfile.ZipFile(pack_path) as z:
            raw = z.read('manifest.json')
    except (zipfile.BadZipFile, KeyError) as e:
        raise ModpackError(f"Not a readable mod package: {e}")
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ModpackError(f"manifest.json is not valid JSON: {e}")
    if manifest.get('format') != FORMAT:
        raise ModpackError(
            f"Unsupported package format: {manifest.get('format')!r} "
            f"(this tool reads {FORMAT!r} only). A MacDog850 2K3 pack "
            "('ncaa2k3-mod-v1') is for Xbox NCAA 2K3, not NCAA 05.")
    return manifest


def apply_pack(pack_path, target_path, out_path):
    """Apply a package to a target (.iso or .gci), writing a NEW file.
    Verifies blob hashes, base identity, and current roster hash
    before touching anything. Returns the changed file key."""
    pack_path, target_path, out_path = (
        Path(pack_path), Path(target_path), Path(out_path))
    if out_path.resolve() == target_path.resolve():
        raise ModpackError(
            f"Refusing to overwrite the target: {target_path}")
    manifest = _read_manifest(pack_path)
    changes = manifest.get('changes') or {}
    if len(changes) != 1:
        raise ModpackError(
            f"Package has {len(changes)} changed file(s); this tool "
            "handles exactly one roster file per package.")
    key, change = next(iter(changes.items()))

    # --- 1. blob integrity (tamper check) ---
    with zipfile.ZipFile(pack_path) as z:
        names = z.namelist()
        blob_name = f"blobs/{change['sha256']}"
        if blob_name not in names:
            raise ModpackError(
                f"Package is missing its blob {blob_name}")
        blob = z.read(blob_name)
    if hashlib.sha256(blob).hexdigest() != change['sha256']:
        raise ModpackError(
            f"Blob {blob_name} fails its sha256 check — the package "
            "has been tampered with or corrupted. Refused.")
    if len(blob) != change['size']:
        raise ModpackError(
            f"Blob size {len(blob)} != manifest size {change['size']}.")

    # --- 2. target kind + base identity ---
    suffix = target_path.suffix.lower()
    expect_source = SOURCE_LABEL.get(
        'iso' if suffix == '.iso' else 'gci' if suffix == '.gci' else '?')
    if manifest.get('source') != expect_source:
        raise ModpackError(
            f"Package is for {manifest.get('source')!r} but the target "
            f"is a {suffix} file ({expect_source}).")
    identity = manifest.get('identity') or {}
    actual_identity = _sha256_file(target_path)
    if actual_identity != identity.get('sha256'):
        raise ModpackError(
            "Target identity mismatch — this package was built "
            "against a different base file.\n"
            f"  expected base sha256: {identity.get('sha256')}\n"
            f"  target file sha256:   {actual_identity}\n"
            "Export a package against your own base file instead.")

    # --- 3. current roster hash must equal the package's original ---
    if suffix == '.iso':
        source = IsoRoster(target_path)
        current = bytes(source.template_data)
        kind = 'iso'
    else:
        current = target_path.read_bytes()
        kind = 'gci'
    if hashlib.sha256(current).hexdigest() != change['original_sha256']:
        raise ModpackError(
            "Target roster is already modified — its current hash "
            "does not match the package's original_sha256.\n"
            f"  expected original: {change['original_sha256']}\n"
            f"  target roster now: {hashlib.sha256(current).hexdigest()}\n"
            "Apply the package to an unmodified base instead.")

    # --- 4. apply to a copy, then verify by re-reading ---
    if kind == 'iso':
        if len(blob) != len(current):
            raise ModpackError(
                f"Blob is {len(blob)} bytes but TEMPLATE.DAT is "
                f"{len(current)} — refusing (sizes must match exactly).")
        bak = target_path.with_suffix('.iso.template.bak')
        if not bak.exists():
            bak.write_bytes(current)
            print(f"Backed up original TEMPLATE.DAT to {bak.name}")
        print(f"Copying ISO to {out_path} ...")
        shutil.copy2(target_path, out_path)
        # The blob IS the whole TEMPLATE.DAT, so it goes at the file's
        # start (template_off) — NOT at the DB offset inside it.
        with open(out_path, 'r+b') as f:
            f.seek(source.template_off)
            f.write(blob)
        with open(out_path, 'rb') as f:
            f.seek(source.template_off)
            check = f.read(len(blob))
        if check != blob:
            raise ModpackError(
                "Post-write verification failed: the patched "
                "TEMPLATE.DAT does not match the package blob.")
    else:
        bak = target_path.with_suffix('.gci.bak')
        if not bak.exists():
            shutil.copy2(target_path, bak)
            print(f"Backed up original to {bak.name}")
        out_path.write_bytes(blob)
        if _sha256_file(out_path) != change['sha256']:
            raise ModpackError(
                "Post-write verification failed: the written GCI "
                "does not match the package blob.")
    print(f"Applied package {pack_path.name} to {out_path} ({key})")
    return key


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        description="NCAA 05 GameCube mod packages (MacDog850 shape)")
    sub = ap.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('build', help='apply a CSV, pack the result')
    b.add_argument('source', help='.gci save or .iso image (never overwritten)')
    b.add_argument('csv', help='input CSV path')
    b.add_argument('name', help='mod name for the manifest')
    b.add_argument('out_zip', help='output .zip package path')
    b.add_argument('--description', default='Roster CSV import')
    a = sub.add_parser('apply', help='apply a package to a target copy')
    a.add_argument('pack', help='input .zip package path')
    a.add_argument('target', help='.gci save or .iso image (never overwritten)')
    a.add_argument('-o', '--output', required=True,
                   help='output .gci/.iso path')
    args = ap.parse_args(argv)
    if args.cmd == 'build':
        build_pack(args.source, args.csv, args.name, args.out_zip,
                   args.description)
    else:
        apply_pack(args.pack, args.target, args.output)
    return 0


if __name__ == '__main__':
    sys.exit(main())
