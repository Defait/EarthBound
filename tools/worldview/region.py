"""Read chunks out of Anvil region files (.mca) and unpack block states.

Only the 1.18+ chunk layout is supported (top-level "sections" list with
"block_states" palettes), which covers every 1.21.x world.
"""
import gzip
import os
import re
import zlib

import numpy as np

from . import nbt

REGION_RE = re.compile(r"^r\.(-?\d+)\.(-?\d+)\.mca$")


def list_regions(region_dir):
    """Yield (rx, rz, path) for every region file in a directory."""
    for name in sorted(os.listdir(region_dir)):
        m = REGION_RE.match(name)
        if m:
            yield int(m.group(1)), int(m.group(2)), os.path.join(region_dir, name)


def iter_chunks(path):
    """Yield (local_x, local_z, root_compound) for each chunk in a region file."""
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < 8192:
        return
    for i in range(1024):
        off = int.from_bytes(data[i * 4:i * 4 + 3], "big")
        if off == 0:
            continue
        start = off * 4096
        length = int.from_bytes(data[start:start + 4], "big")
        ctype = data[start + 4]
        lx, lz = i % 32, i // 32
        if ctype & 0x80:
            # Oversized chunk stored next to the region file as c.<x>.<z>.mcc
            rx, rz = map(int, REGION_RE.match(os.path.basename(path)).groups())
            ext = os.path.join(os.path.dirname(path), f"c.{rx * 32 + lx}.{rz * 32 + lz}.mcc")
            with open(ext, "rb") as f:
                payload = f.read()
        else:
            payload = data[start + 5:start + 4 + length]
        ctype &= 0x7F
        if ctype == 2:
            raw = zlib.decompress(payload)
        elif ctype == 1:
            raw = gzip.decompress(payload)
        elif ctype == 3:
            raw = payload
        else:
            raise ValueError(f"{path}: chunk compression type {ctype} not supported (LZ4?)")
        yield lx, lz, nbt.loads(raw)


def unpack_indices(packed, palette_len):
    """Unpack a 1.16+ block_states long array into 4096 palette indices (y, z, x order)."""
    bits = max(4, int(palette_len - 1).bit_length())
    per_long = 64 // bits
    longs = packed  # native-endian uint64, see chunk_sections()
    shifts = (np.arange(per_long, dtype=np.uint64) * np.uint64(bits))
    mask = np.uint64((1 << bits) - 1)
    out = (longs[:, None] >> shifts[None, :]) & mask
    return out.reshape(-1)[:4096].astype(np.uint16)


def chunk_sections(root):
    """Return (status, [(section_y, palette_names, packed_or_None), ...]) for a chunk.

    Sections without block states (lighting-only padding above/below the
    world) are skipped. packed is None when the palette has a single entry.
    """
    status = root.get("Status", "")
    out = []
    for sec in root.get("sections", []):
        bs = sec.get("block_states")
        if not bs:
            continue
        names = [p["Name"] for p in bs["palette"]]
        data = bs.get("data")
        if data is not None:
            # NBT longs are big-endian; convert to native int64, then reinterpret as unsigned.
            data = np.asarray(data, dtype=np.int64).view(np.uint64)
        out.append((sec["Y"], names, data))
    return status, out
