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
- CMPR: S3TC/DXT1 compressed, 8x8 tiles (four 4x4 DXT1 blocks), 32 bytes/tile

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


# === CMPR (GameCube DXT1) Codec ===
# CMPR: 8x8 pixel tile = 4x 4x4 DXT1 blocks = 32 bytes
# Each 4x4 DXT1 block: [color0:2][color1:2][indices:4] = 8 bytes
# Colors are RGB565 BE

def rgb565_to_rgb888(c):
    """Convert RGB565 BE to (r,g,b) 8-bit."""
    r = ((c >> 11) & 0x1F) * 255 // 31
    g = ((c >> 5) & 0x3F) * 255 // 63
    b = (c & 0x1F) * 255 // 31
    return (r, g, b)

def rgb888_to_rgb565(r, g, b):
    """Convert (r,g,b) 8-bit to RGB565 BE."""
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)

def decode_dxt1_block(data, x0, y0, pixels, width):
    """Decode a 4x4 DXT1 block into pixels dict."""
    c0 = struct.unpack('>H', data[0:2])[0]
    c1 = struct.unpack('>H', data[2:4])[0]
    indices = struct.unpack('>I', data[4:8])[0]
    
    r0, g0, b0 = rgb565_to_rgb888(c0)
    r1, g1, b1 = rgb565_to_rgb888(c1)
    
    # DXT1 color palette
    if c0 > c1:
        # 4 colors
        colors = [
            (r0, g0, b0),
            (r1, g1, b1),
            ((2*r0 + r1)//3, (2*g0 + g1)//3, (2*b0 + b1)//3),
            ((r0 + 2*r1)//3, (g0 + 2*g1)//3, (b0 + 2*b1)//3),
        ]
    else:
        # 3 colors + transparent
        colors = [
            (r0, g0, b0),
            (r1, g1, b1),
            ((r0 + r1)//2, (g0 + g1)//2, (b0 + b1)//2),
            (0, 0, 0),  # transparent (we'll use black)
        ]
    
    for y in range(4):
        for x in range(4):
            idx = (indices >> (2 * (y*4 + x))) & 0x03
            px, py = x0 + x, y0 + y
            if 0 <= px < width:
                pixels[(px, py)] = colors[idx]

def decode_cmpr(data, width, height):
    """
    Decode GameCube CMPR texture.
    Returns PIL Image in RGB mode.
    """
    from PIL import Image
    img = Image.new('RGB', (width, height))
    pixels = img.load()
    
    # CMPR: 8x8 tiles, each 32 bytes (4x DXT1 blocks)
    tile_w = (width + 7) // 8
    tile_h = (height + 7) // 8
    
    offset = 0
    for ty in range(tile_h):
        for tx in range(tile_w):
            # Each 8x8 tile has 4 DXT1 blocks in Z-order:
            # [0,1]
            # [2,3]
            # Actually GC order: top-left, top-right, bottom-left, bottom-right
            for by in range(2):
                for bx in range(2):
                    if offset + 8 > len(data):
                        break
                    block = data[offset:offset+8]
                    x0 = tx*8 + bx*4
                    y0 = ty*8 + by*4
                    # Decode into temp dict then copy
                    tmp = {}
                    decode_dxt1_block(block, 0, 0, tmp, 4)
                    for (px, py), color in tmp.items():
                        gx, gy = x0 + px, y0 + py
                        if gx < width and gy < height:
                            pixels[gx, gy] = color
                    offset += 8
    
    return img

def encode_cmpr(img, width=64, height=64):
    """
    Encode PIL Image to GameCube CMPR.
    Simple encoder: uses basic DXT1 compression.
    Returns 32 bytes per 8x8 tile.
    """
    if img.mode != 'RGB':
        img = img.convert('RGB')
    img = img.resize((width, height), Image.LANCZOS)
    pixels = img.load()
    
    output = bytearray()
    tile_w = (width + 7) // 8
    tile_h = (height + 7) // 8
    
    for ty in range(tile_h):
        for tx in range(tile_w):
            for by in range(2):
                for bx in range(2):
                    # Get 4x4 block pixels
                    block_pixels = []
                    for y in range(4):
                        for x in range(4):
                            gx = tx*8 + bx*4 + x
                            gy = ty*8 + by*4 + y
                            if gx < width and gy < height:
                                block_pixels.append(pixels[gx, gy])
                            else:
                                block_pixels.append((0, 0, 0))
                    
                    # Simple DXT1: find min/max colors
                    # (Naive implementation - for better quality use proper compressor)
                    rs = [p[0] for p in block_pixels]
                    gs = [p[1] for p in block_pixels]
                    bs = [p[2] for p in block_pixels]
                    
                    # Use extremes
                    min_c = (min(rs), min(gs), min(bs))
                    max_c = (max(rs), max(gs), max(bs))
                    
                    c0 = rgb888_to_rgb565(*max_c)
                    c1 = rgb888_to_rgb565(*min_c)
                    if c0 < c1:
                        c0, c1 = c1, c0
                    
                    # Assign indices (nearest color)
                    r0, g0, b0 = rgb565_to_rgb888(c0)
                    r1, g1, b1 = rgb565_to_rgb888(c1)
                    colors = [(r0,g0,b0), (r1,g1,b1),
                              ((2*r0+r1)//3, (2*g0+g1)//3, (2*b0+b1)//3),
                              ((r0+2*r1)//3, (g0+2*g1)//3, (b0+2*b1)//3)]
                    
                    indices = 0
                    for i, (r,g,b) in enumerate(block_pixels):
                        # Find nearest
                        best = 0
                        best_dist = float('inf')
                        for ci, (cr,cg,cb) in enumerate(colors):
                            dist = (r-cr)**2 + (g-cg)**2 + (b-cb)**2
                            if dist < best_dist:
                                best_dist = dist
                                best = ci
                        indices |= (best << (2*i))
                    
                    output.extend(struct.pack('>H', c0))
                    output.extend(struct.pack('>H', c1))
                    output.extend(struct.pack('>I', indices))
    
    return bytes(output)


class TerfArchive:
    """Parser for TERF texture archives."""
    
    def __init__(self, dat_path):
        self.path = Path(dat_path)
        self.data = bytearray(self.path.read_bytes())
        
        if self.data[0:4] != b'TERF':
            raise ValueError("Not a TERF archive")
        
        # TERF Header (16 bytes):
        # 'TERF' (4), header_len (4), unknown (4), file_pad (2), num_files (2)
        self.header_len = struct.unpack('>I', self.data[4:8])[0]
        self.unknown = struct.unpack('>I', self.data[8:12])[0]
        self.file_pad = struct.unpack('>H', self.data[12:14])[0]
        self.num_files = struct.unpack('>H', self.data[14:16])[0]
        
        # Find DIR1
        self.dir1_offset = self.data.find(b'DIR1')
        if self.dir1_offset < 0:
            raise ValueError("No DIR1 found")
        
        self.dir1_len = struct.unpack('>I', self.data[self.dir1_offset+4:self.dir1_offset+8])[0]
        
        # Find DATA
        self.data_offset = self.data.find(b'DATA')
        if self.data_offset < 0:
            raise ValueError("No DATA found")
        self.data_len = struct.unpack('>I', self.data[self.data_offset+4:self.data_offset+8])[0]
        # DATA content starts after 8-byte header
        self.data_content_offset = self.data_offset + 8
        
        print(f"TERF archive: {len(self.data)} bytes")
        print(f"  Files: {self.num_files}, File pad: 0x{self.file_pad:X}")
        print(f"  DIR1 at 0x{self.dir1_offset:X}, len 0x{self.dir1_len:X}")
        print(f"  DATA at 0x{self.data_offset:X}, content at 0x{self.data_content_offset:X}")
        
        # Parse directory entries
        # Each: [offset:4 BE][length:4 BE] = 8 bytes
        # Offset is relative to DATA content start
        self.entries = []
        for i in range(self.num_files):
            off = self.dir1_offset + 8 + i*8
            f_offset = struct.unpack('>I', self.data[off:off+4])[0]
            f_length = struct.unpack('>I', self.data[off+4:off+8])[0]
            abs_offset = self.data_content_offset + f_offset
            self.entries.append((abs_offset, f_length))
        
        print(f"  Parsed {len(self.entries)} directory entries")
    
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
