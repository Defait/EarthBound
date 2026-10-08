"""Read generated worlds (Anvil region files) for the structure trial: structure starts, block boxes, block entities.

Uses tools/worldview's nbt and region modules. A WorldReader keeps each region file's bytes and parses chunks on demand.
"""
import gzip
import os
import re
import sys
import zlib
from collections import OrderedDict

import numpy as np

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)
from worldview import nbt as WN  # noqa: E402
from worldview import region as WR  # noqa: E402

REGION_RE = re.compile(r"^r\.(-?\d+)\.(-?\d+)\.mca$")
AIRS = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air"}


class WorldReader:
    def __init__(self, world_dir, cache_chunks=600):
        self.dir = world_dir
        self.rdir = os.path.join(world_dir, "region")
        self.regions = {}
        self.files = {}
        for name in os.listdir(self.rdir):
            m = REGION_RE.match(name)
            if m:
                self.files[(int(m.group(1)), int(m.group(2)))] = os.path.join(self.rdir, name)
        self._data = OrderedDict()
        self._chunks = OrderedDict()
        self.cache_chunks = cache_chunks

    def _region_bytes(self, rx, rz):
        k = (rx, rz)
        if k in self._data:
            self._data.move_to_end(k)
            return self._data[k]
        p = self.files.get(k)
        if not p:
            return None
        with open(p, "rb") as f:
            d = f.read()
        self._data[k] = d
        if len(self._data) > 6:
            self._data.popitem(last=False)
        return d

    def chunk(self, cx, cz):
        key = (cx, cz)
        if key in self._chunks:
            self._chunks.move_to_end(key)
            return self._chunks[key]
        rx, rz = cx >> 5, cz >> 5
        data = self._region_bytes(rx, rz)
        root = None
        if data is not None and len(data) >= 8192:
            i = (cx & 31) + (cz & 31) * 32
            off = int.from_bytes(data[i * 4:i * 4 + 3], "big")
            if off:
                start = off * 4096
                length = int.from_bytes(data[start:start + 4], "big")
                ctype = data[start + 4]
                if ctype & 0x80:
                    ext = os.path.join(self.rdir, f"c.{cx}.{cz}.mcc")
                    payload = open(ext, "rb").read()
                else:
                    payload = data[start + 5:start + 4 + length]
                ctype &= 0x7F
                raw = zlib.decompress(payload) if ctype == 2 else gzip.decompress(payload) if ctype == 1 else payload
                root = WN.loads(raw)
        self._chunks[key] = root
        if len(self._chunks) > self.cache_chunks:
            self._chunks.popitem(last=False)
        return root

    def all_chunk_coords(self):
        for (rx, rz), p in sorted(self.files.items()):
            data = open(p, "rb").read()
            if len(data) < 8192:
                continue
            for i in range(1024):
                if int.from_bytes(data[i * 4:i * 4 + 3], "big"):
                    yield rx * 32 + (i % 32), rz * 32 + (i // 32)

    def iter_all(self):
        """Yield (cx, cz, root) for every chunk, region by region (each region file read once)."""
        for (rx, rz), p in sorted(self.files.items()):
            for lx, lz, root in WR.iter_chunks(p):
                yield rx * 32 + lx, rz * 32 + lz, root

    # ---------------------------------------------------------------- blocks
    def box(self, x0, y0, z0, x1, y1, z1):
        """Blocks in the inclusive box as (ids int32 array [x,y,z], palette list of (name, props dict)). Missing chunks/sections are air."""
        sx, sy, sz = x1 - x0 + 1, y1 - y0 + 1, z1 - z0 + 1
        arr = np.zeros((sx, sy, sz), np.int32)
        pal_index = {("minecraft:air", ()): 0}
        pal = [("minecraft:air", {})]
        for cx in range(x0 >> 4, (x1 >> 4) + 1):
            for cz in range(z0 >> 4, (z1 >> 4) + 1):
                root = self.chunk(cx, cz)
                if not root:
                    continue
                for sec in root.get("sections", []):
                    sy0 = sec["Y"] * 16
                    if sy0 + 15 < y0 or sy0 > y1:
                        continue
                    bs = sec.get("block_states")
                    if not bs:
                        continue
                    entries = bs["palette"]
                    local = np.zeros(len(entries), np.int32)
                    for i, e in enumerate(entries):
                        props = tuple(sorted((e.get("Properties") or {}).items()))
                        key = (e["Name"], props)
                        if key not in pal_index:
                            pal_index[key] = len(pal)
                            pal.append((e["Name"], dict(props)))
                        local[i] = pal_index[key]
                    data = bs.get("data")
                    if data is None:
                        idx = np.zeros(4096, np.int32)
                    else:
                        packed = np.asarray(data, dtype=np.int64).view(np.uint64)
                        idx = WR.unpack_indices(packed, len(entries)).astype(np.int32)
                    blk = local[idx].reshape(16, 16, 16)      # [y, z, x]
                    # intersection of the section with the box, in world coordinates
                    wx0, wx1 = max(x0, cx * 16), min(x1, cx * 16 + 15)
                    wz0, wz1 = max(z0, cz * 16), min(z1, cz * 16 + 15)
                    wy0, wy1 = max(y0, sy0), min(y1, sy0 + 15)
                    sub = blk[wy0 - sy0:wy1 - sy0 + 1, wz0 - cz * 16:wz1 - cz * 16 + 1, wx0 - cx * 16:wx1 - cx * 16 + 1]   # [y, z, x]
                    arr[wx0 - x0:wx1 - x0 + 1, wy0 - y0:wy1 - y0 + 1, wz0 - z0:wz1 - z0 + 1] = sub.transpose(2, 0, 1)
        return arr, pal

    def block_entities(self, x0, y0, z0, x1, y1, z1):
        out = []
        for cx in range(x0 >> 4, (x1 >> 4) + 1):
            for cz in range(z0 >> 4, (z1 >> 4) + 1):
                root = self.chunk(cx, cz)
                if not root:
                    continue
                for be in root.get("block_entities", []):
                    if x0 <= be["x"] <= x1 and y0 <= be["y"] <= y1 and z0 <= be["z"] <= z1:
                        out.append(be)
        return out


def structure_starts(root):
    """[(structure id, start chunk x, z, [bounding boxes of its pieces], piece ids)] for a chunk's own starts."""
    out = []
    st = (root.get("structures") or {}).get("starts") or {}
    for name, s in st.items():
        if not isinstance(s, dict) or s.get("id") in (None, "INVALID"):
            continue
        boxes, pids = [], []
        for c in (s.get("Children") or s.get("children") or []):
            bb = c.get("BB")
            if bb is not None and len(bb) == 6:
                boxes.append([int(v) for v in bb])
            pids.append(c.get("id"))
        out.append((name, int(s.get("ChunkX", 0)), int(s.get("ChunkZ", 0)), boxes, pids))
    return out


# ---------------------------------------------------------------- fast scan (no full NBT parse)
_STRUCT_KEY = b"\x0a\x00\x0astructures"
_STATUS_KEY = b"\x08\x00\x06Status"


def iter_raw(world_dir):
    """Yield (cx, cz, raw uncompressed chunk NBT bytes) for every chunk, reading each region file once."""
    rdir = os.path.join(world_dir, "region")
    for name in sorted(os.listdir(rdir)):
        m = REGION_RE.match(name)
        if not m:
            continue
        rx, rz = int(m.group(1)), int(m.group(2))
        data = open(os.path.join(rdir, name), "rb").read()
        if len(data) < 8192:
            continue
        for i in range(1024):
            off = int.from_bytes(data[i * 4:i * 4 + 3], "big")
            if not off:
                continue
            start = off * 4096
            length = int.from_bytes(data[start:start + 4], "big")
            ctype = data[start + 4]
            lx, lz = i % 32, i // 32
            if ctype & 0x80:
                payload = open(os.path.join(rdir, f"c.{rx * 32 + lx}.{rz * 32 + lz}.mcc"), "rb").read()
            else:
                payload = data[start + 5:start + 4 + length]
            ctype &= 0x7F
            raw = zlib.decompress(payload) if ctype == 2 else gzip.decompress(payload) if ctype == 1 else payload
            yield rx * 32 + lx, rz * 32 + lz, raw


def fast_chunk_info(raw):
    """(status, structures compound or None) from raw chunk NBT without parsing the sections."""
    status = None
    j = raw.find(_STATUS_KEY)
    if j >= 0:
        p = j + len(_STATUS_KEY)
        n = int.from_bytes(raw[p:p + 2], "big")
        status = raw[p + 2:p + 2 + n].decode("utf-8", "replace")
    structures = None
    i = raw.find(_STRUCT_KEY)
    if i >= 0:
        r = WN._Reader(raw)
        r.pos = i + len(_STRUCT_KEY)
        structures = r.payload(10)
    return status, structures


def starts_of(structures):
    out = []
    st = (structures or {}).get("starts") or {}
    for name, s in st.items():
        if not isinstance(s, dict) or s.get("id") in (None, "INVALID"):
            continue
        boxes, pids = [], []
        for c in (s.get("Children") or s.get("children") or []):
            bb = c.get("BB")
            if bb is not None and len(bb) == 6:
                boxes.append([int(v) for v in bb])
            pids.append(c.get("id"))
        out.append((name, int(s.get("ChunkX", 0)), int(s.get("ChunkZ", 0)), boxes, pids))
    return out
