#!/usr/bin/env python3
"""
NCAA Football 2005 Texture Archive Parser

Parses TERF texture archives (PLYRFACE.DAT, STADATA.DAT, etc.)
for texture replacement modding.

PLYRFACE.DAT:
- 1,087,488 bytes, TERF archive
- DIR1 at 0x800, ~144 files
- Player face textures (GameCube I8/RGB5A3/CMPR)

GameCube Texture Formats:
- I8: 8-bit intensity, 8x4 tiles, 1 byte/pixel
- RGB5A3: 16-bit color, 4x4 tiles, 2 bytes/pixel
- CMPR: S3TC/DXT1 compressed, 8x8 tiles, 4 bits/pixel

For PWA: Use Blob.slice() to extract DAT, modify textures,
rebuild ISO via Blob concatenation (same as roster editor).
"""

from pathlib import Path
import struct

# Texture archive locations in ISO
TEXTURE_ARCHIVES = {
    'PLYRFACE.DAT': {'offset': 0x121964FC, 'size': 1087488, 'desc': 'Player faces'},
    'STADATA.DAT': {'offset': None, 'size': 16762176, 'desc': 'Stadium textures'},
    'STADIUMS.DAT': {'offset': None, 'size': 287321536, 'desc': 'Stadium models/textures'},
}


class TerfArchive:
    """Parser for TERF texture archives."""
    
    def __init__(self, dat_path):
        self.path = Path(dat_path)
        self.data = bytearray(self.path.read_bytes())
        
        if self.data[0:4] != b'TERF':
            raise ValueError("Not a TERF archive")
        
        # Find DIR1
        self.dir1_offset = self.data.find(b'DIR1')
        if self.dir1_offset < 0:
            raise ValueError("No DIR1 found")
        
        print(f"TERF archive: {len(self.data)} bytes")
        print(f"DIR1 at 0x{self.dir1_offset:X}")
        
        # Parse directory entries
        # Format appears to be: [offset:4][size:4][...] ?
        # Need to reverse-engineer from MaddenAmp Terf.cs
        self.entries = self._parse_dir1()
    
    def _parse_dir1(self):
        """Parse DIR1 entries. Returns list of (offset, size)."""
        # TODO: Implement based on MaddenAmp/MaddenEditor/Core/DAT/Terf.cs
        # For now, return empty - needs RE work
        print("  DIR1 parsing not yet implemented (see Terf.cs reference)")
        return []
    
    def extract_file(self, index, output_path):
        """Extract a file from the archive."""
        if index >= len(self.entries):
            raise IndexError(f"File {index} out of range")
        offset, size = self.entries[index]
        data = self.data[offset:offset+size]
        Path(output_path).write_bytes(data)
        print(f"Extracted file {index}: {size} bytes to {output_path}")
    
    def replace_file(self, index, new_data):
        """Replace a file in the archive (must be same size)."""
        if index >= len(self.entries):
            raise IndexError(f"File {index} out of range")
        offset, size = self.entries[index]
        if len(new_data) != size:
            raise ValueError(f"New data must be {size} bytes, got {len(new_data)}")
        self.data[offset:offset+size] = new_data
        print(f"Replaced file {index} ({size} bytes)")
    
    def save(self, output_path):
        """Save modified archive."""
        Path(output_path).write_bytes(bytes(self.data))
        print(f"Saved to {output_path}")


def patch_iso_texture(iso_path, dat_name, dat_data, output_iso_path):
    """
    Patch a texture DAT in the ISO.
    
    Args:
        iso_path: Input ISO path
        dat_name: e.g., 'PLYRFACE.DAT'
        dat_data: Modified DAT bytes (must match original size)
        output_iso_path: Output ISO path
    """
    if dat_name not in TEXTURE_ARCHIVES:
        raise ValueError(f"Unknown archive: {dat_name}")
    
    info = TEXTURE_ARCHIVES[dat_name]
    if info['offset'] is None:
        raise ValueError(f"ISO offset for {dat_name} not yet determined")
    
    if len(dat_data) != info['size']:
        raise ValueError(f"DAT must be {info['size']} bytes")
    
    import shutil
    print(f"Copying ISO...")
    shutil.copy2(iso_path, output_iso_path)
    
    print(f"Patching {dat_name} at 0x{info['offset']:X}...")
    with open(output_iso_path, 'r+b') as f:
        f.seek(info['offset'])
        f.write(dat_data)
    
    print("ISO patched!")


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: texture_parser.py <PLYRFACE.DAT>")
        print("\nTexture modding framework - DIR1 parsing in progress.")
        print("See ~/workspace/recon/MaddenAmp/MaddenEditor/Core/DAT/Terf.cs for reference.")
        sys.exit(1)
    
    archive = TerfArchive(sys.argv[1])
