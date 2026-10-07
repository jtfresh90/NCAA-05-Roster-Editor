"""
EA RefPack decompressor.
Based on public documentation of the RefPack/QFS format used in EA games.
Reference: https://github.com/vdmkenny/openreliant/blob/HEAD/docs/formats/refpack.md
"""

def decompress_refpack(data, expected_size=None):
    """
    Decompress RefPack data.
    
    Args:
        data: bytes of compressed data (after any header)
        expected_size: expected decompressed size (for validation)
    
    Returns:
        bytes of decompressed data
    """
    output = bytearray()
    pos = 0
    data_len = len(data)
    
    while pos < data_len:
        b0 = data[pos]
        pos += 1
        
        if b0 < 0x80:
            # 2-byte command: literals + short match
            if pos >= data_len:
                break
            b1 = data[pos]
            pos += 1
            
            literals = b0 & 3
            length = ((b0 >> 2) & 7) + 3
            distance = ((b0 & 0x60) << 3) + b1 + 1
            
            # Copy literals
            for _ in range(literals):
                if pos >= data_len:
                    break
                output.append(data[pos])
                pos += 1
            
            # Copy match
            for _ in range(length):
                output.append(output[len(output) - distance])
                
        elif b0 < 0xC0:
            # 3-byte command: literals + medium match
            if pos + 1 >= data_len:
                break
            b1 = data[pos]
            b2 = data[pos + 1]
            pos += 2
            
            literals = (b1 >> 6) & 3
            length = (b0 & 0x3F) + 4
            distance = ((b1 & 0x3F) << 8) + b2 + 1
            
            for _ in range(literals):
                if pos >= data_len:
                    break
                output.append(data[pos])
                pos += 1
            
            for _ in range(length):
                output.append(output[len(output) - distance])
                
        elif b0 < 0xE0:
            # 4-byte command: literals + long match
            if pos + 2 >= data_len:
                break
            b1 = data[pos]
            b2 = data[pos + 1]
            b3 = data[pos + 2]
            pos += 3
            
            literals = b0 & 3
            length = ((b0 & 0x0C) << 6) + b3 + 5
            distance = ((b0 & 0x10) << 12) + (b1 << 8) + b2 + 1
            
            for _ in range(literals):
                if pos >= data_len:
                    break
                output.append(data[pos])
                pos += 1
            
            for _ in range(length):
                output.append(output[len(output) - distance])
                
        elif b0 < 0xFC:
            # 1-byte command: literals only
            literals = ((b0 & 0x1F) << 2) + 4
            for _ in range(literals):
                if pos >= data_len:
                    break
                output.append(data[pos])
                pos += 1
        else:
            # 0xFC-0xFF: end of stream (with 0-3 literals)
            literals = b0 & 3
            for _ in range(literals):
                if pos >= data_len:
                    break
                output.append(data[pos])
                pos += 1
            break
    
    result = bytes(output)
    if expected_size and len(result) != expected_size:
        print(f"Warning: decompressed {len(result)} bytes, expected {expected_size}")
    
    return result


def decompress_with_header(data):
    """
    Decompress RefPack data with EA header.
    Header format: 2 bytes magic (0x10FB) + 3 bytes BE decompressed size
    """
    if len(data) < 5:
        raise ValueError("Data too short for RefPack header")
    
    magic = (data[0] << 8) | data[1]
    if magic != 0x10FB:
        # Try without header
        print(f"No RefPack header (magic=0x{magic:04x}), trying raw...")
        return decompress_refpack(data)
    
    expected = (data[2] << 16) | (data[3] << 8) | data[4]
    print(f"RefPack header: expected {expected} bytes")
    return decompress_refpack(data[5:], expected)


if __name__ == "__main__":
    import sys, os
    # Test on PLADATA.DAT
    path = os.path.expanduser("~/workspace/discs/ncaa05/ncaa05-extracted/P-GCUE/files/PLADATA.DAT")
    with open(path, 'rb') as f:
        f.seek(0x46af800)
        data = f.read(0x2437a)  # Size from file 1's table
    
    print(f"Read {len(data)} bytes from 0x46af800")
    print(f"First 8 bytes: {data[:8].hex()}")
    
    try:
        result = decompress_with_header(data)
        print(f"Decompressed to {len(result)} bytes")
        print(f"First 32 bytes hex: {result[:32].hex()}")
    except Exception as e:
        print(f"Failed: {e}")
        import traceback
        traceback.print_exc()
