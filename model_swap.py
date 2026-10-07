"""
NCAA Football 2005 (GameCube) - Model Swap Tool

Based on trey31's Madden 08 PC mesh-swap method:
Swap entire model entries within DAT archives without decoding geometry.

Supported archives:
  PLADATA.DAT  (147MB, 2672 files) - Player models/equipment
  UIS_MODL.DAT ( 76MB,  111 files) - UI/menu high-detail models
  FANDATA.DAT  (  2MB,  257 files) - Fan/crowd models
  STADATA.DAT  ( 16MB,    ? files) - Stadium data

Usage:
    python3 model_swap.py PLADATA.DAT --swap 2117 2118 -o PLADATA_SWAPPED.DAT
    python3 model_swap.py PLADATA.DAT --list --size 1607
    python3 model_swap.py PLADATA.DAT --info 2117
"""

import os
import sys
import struct
import argparse
from collections import Counter

# Import TERF parser
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from texture_parser import TerfArchive


def list_by_size(archive_path, target_size=None):
    """List files grouped by size."""
    archive = TerfArchive(archive_path)
    
    if target_size:
        print(f"Files with size {target_size} bytes:")
        for i, (offset, size) in enumerate(archive.entries):
            if size == target_size:
                print(f"  [{i}] offset=0x{offset:x} size={size}")
    else:
        # Show size clusters
        sizes = Counter(size for _, size in archive.entries)
        print("Top 30 most common sizes:")
        for size, count in sizes.most_common(30):
            print(f"  {size:>8} bytes: {count:>4} files")


def info(archive_path, index):
    """Show info about a specific file."""
    archive = TerfArchive(archive_path)
    if index >= archive.num_files:
        print(f"Invalid index {index} (max {archive.num_files-1})")
        return
    
    offset, size = archive.entries[index]
    print(f"File [{index}]:")
    print(f"  Offset: 0x{offset:x}")
    print(f"  Size: {size} bytes (0x{size:x})")
    
    # Read first 64 bytes
    with open(archive_path, 'rb') as f:
        f.seek(offset)
        data = f.read(64)
    
    print(f"  First 32 bytes: {data[:32].hex()}")
    
    # Check COMP table for uncompressed size
    comp_offset = 0x5400  # Found earlier
    try:
        with open(archive_path, 'rb') as f:
            f.seek(comp_offset + 8 + index * 8)
            level = struct.unpack('>I', f.read(4))[0]
            uncomp = struct.unpack('>I', f.read(4))[0]
            print(f"  COMP: level={level}, uncompressed={uncomp} bytes")
            if uncomp != size:
                print(f"  Note: compressed ({size} -> {uncomp})")
    except:
        pass


def swap_entries(archive_path, idx_a, idx_b, output_path):
    """
    Swap two entries in the TERF archive.
    Uses rebuild_with_replacements to handle size differences.
    """
    archive = TerfArchive(archive_path)
    
    if idx_a >= archive.num_files or idx_b >= archive.num_files:
        print(f"Invalid indices (max {archive.num_files-1})")
        return False
    
    offset_a, size_a = archive.entries[idx_a]
    offset_b, size_b = archive.entries[idx_b]
    
    print(f"Swapping [{idx_a}] ({size_a} bytes) <-> [{idx_b}] ({size_b} bytes)")
    
    # Read both files
    with open(archive_path, 'rb') as f:
        f.seek(offset_a)
        data_a = f.read(size_a)
        f.seek(offset_b)
        data_b = f.read(size_b)
    
    # Swap via rebuild
    replacements = {
        idx_a: data_b,
        idx_b: data_a,
    }
    
    print("Rebuilding TERF...")
    new_data = archive.rebuild_with_replacements(replacements)
    
    print(f"Writing to {output_path}...")
    print(f"  Original: {os.path.getsize(archive_path)} bytes")
    print(f"  New: {len(new_data)} bytes")
    
    with open(output_path, 'wb') as f:
        f.write(new_data)
    
    print("Done!")
    return True


def main():
    parser = argparse.ArgumentParser(description="NCAA 05 Model Swap Tool")
    parser.add_argument("archive", help="Path to PLADATA.DAT")
    parser.add_argument("--swap", nargs=2, type=int, metavar=("A", "B"),
                        help="Swap entries A and B")
    parser.add_argument("-o", "--output", help="Output path for swapped DAT")
    parser.add_argument("--list", action="store_true",
                        help="List files by size")
    parser.add_argument("--size", type=int,
                        help="Filter --list by exact size")
    parser.add_argument("--info", type=int, metavar="INDEX",
                        help="Show info about a file")
    
    args = parser.parse_args()
    
    if args.swap:
        if not args.output:
            print("Error: --output required with --swap")
            sys.exit(1)
        swap_entries(args.archive, args.swap[0], args.swap[1], args.output)
    elif args.info is not None:
        info(args.archive, args.info)
    elif args.list:
        list_by_size(args.archive, args.size)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
