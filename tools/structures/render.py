"""Textured isometric renders of structure templates (.nbt), for browsing candidate structures (docs/lived-in.md).

Usage (from the repo root):
    tools/.venv/Scripts/python tools/structures/render.py PATH [PATH ...] [--out DIR] [--views sw,ne] [--size 800]
        [--scale A] [--colors 256] [--jigsaw] [--tint auto|plains|desert|taiga|snowy] [--mc-jar JAR] [--assets JAR ...]
        [--stats]
PATH is a template file or a folder (searched for *.nbt). Writes DIR/<name>_<view>.png (default DIR: ./render-out) and, with
--stats, prints one JSON line per template (size, block count, top blocks, stand-in and untextured counts, and the ids that
are neither TFC 4 nor vanilla with what each was drawn as).

What it draws: a 2:1 isometric view (camera at a corner, looking down), one 16-texel block face per 16 px at scale 16, so the
picture is pixel-art true to the textures. Each block's real model is read from the jars, blockstate -> model -> parent chain,
so stairs, slabs, fences, walls, panes, doors, trapdoors, torches, plants, TFC's rock/wood/soil variants and other mods' blocks
come out as they look in game, with the top face lit and the two sides shaded. Textures and models come only from local jars:
TFC's, the Minecraft client's and the mods in tools/.server/mods (the order is TFC, Minecraft, the rest). Air, structure voids,
structure blocks and (unless --jigsaw) jigsaw blocks are hidden. Only numpy is needed: PNG decoding and the palette PNG encoder
(median-cut quantiser, small files) are written here, so no Pillow.

Blocks no jar knows (other mods' blocks in templates built for a different pack, TFC 3 ids): TFC 3 wood/rock/soil ids are
mapped to TFC 4 ones (loam -> alfisol and so on), and the rest get a stand-in: the shape of the nearest vanilla block (stairs,
slab, fence, wall, door, carpet, chest...) from keywords in the id, with the texture of the nearest TFC material, or, for
Framed Blocks, of the camouflage block saved in the template. Stand-ins are counted as "substituted"; ones that end up a flat
colour are counted as "untextured". Either way the id is listed in "foreign" (not TFC 4 or vanilla) in the statistics.

Approximations (they stay approximate on purpose):
  - Tinted textures (grass, foliage, water) get one fixed colour per biome profile, not the world's climate colours.
  - Blocks drawn by entity renderers (chests, beds, signs, banners, skulls, shulker boxes, bells...) and blocks with a model
    but no elements are drawn as plain boxes with the block's own particle texture (the planks, for chests); blocks the game
    draws with code alone (ingot piles, scrapings) are left out ("no_model_ids").
  - Fences, panes, bars and walls whose saved connections are all off get them recomputed from their neighbours; other
    neighbour-driven shapes (stairs corners, door halves, redstone) are drawn as saved. Random model variants always use the
    first; TFC's leaves and plants are drawn in their summer variant; other custom model loaders from their elements, if any.
  - Translucent blocks (water, glass, ice) are alpha-blended per block; only the outer skin of a body of water is drawn.
  - Occlusion is by whole blocks: a block is skipped only when the three neighbours facing the camera are solid cubes.
  - Shapes the stand-ins cannot give (Macaw's roofs, framed slopes and prisms, furniture) are stairs, slabs or cubes.
"""
import argparse
import glob
import json
import math
import os
import re
import struct
import sys
import zipfile
import zlib
from collections import Counter

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
REPO = os.path.dirname(TOOLS)
sys.path.insert(0, HERE)

import nbt as N  # noqa: E402

MODS_DIR = os.path.join(TOOLS, ".server", "mods")
HIDDEN = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air", "minecraft:structure_void", "minecraft:structure_block",
          "minecraft:barrier", "minecraft:light", "minecraft:jigsaw", "tfc:light"}
DIRS = {"up": (0, 1, 0), "down": (0, -1, 0), "north": (0, 0, -1), "south": (0, 0, 1), "west": (-1, 0, 0), "east": (1, 0, 0)}
VIEWS = {"se": 0, "sw": 1, "nw": 2, "ne": 3}  # corner the camera looks from; the canonical camera is at +x +z (south-east)

# fixed biome-profile colours for tint indices (vanilla's own plains/desert/taiga/snowy values)
TINTS = {
    "plains": {"grass": (0x91, 0xBD, 0x59), "foliage": (0x77, 0xAB, 0x2F)},
    "desert": {"grass": (0xBF, 0xB7, 0x55), "foliage": (0xAE, 0xA4, 0x2A)},
    "taiga": {"grass": (0x86, 0xB7, 0x83), "foliage": (0x68, 0xA4, 0x64)},
    "snowy": {"grass": (0x80, 0xB4, 0x97), "foliage": (0x60, 0xA1, 0x7B)},
}
WATER_TINT = (0x3F, 0x76, 0xE4)
FIXED_FOLIAGE = {"spruce_leaves": (0x61, 0x99, 0x61), "birch_leaves": (0x80, 0xA7, 0x55), "lily_pad": (0x20, 0x80, 0x30)}


# ======================================================================== PNG (numpy + zlib only)
def png_decode(data):
    """PNG bytes -> float32 RGBA array (h, w, 4) in 0..1, or None for what is not supported (interlaced)."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    pos, idat, plte, trns = 8, [], None, None
    while pos < len(data):
        n, typ = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        pos += 12 + n
        if typ == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
        elif typ == b"PLTE":
            plte = np.frombuffer(body, np.uint8).reshape(-1, 3)
        elif typ == b"tRNS":
            trns = body
        elif typ == b"IDAT":
            idat.append(body)
        elif typ == b"IEND":
            break
    if interlace:
        return None
    chans = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    bits = depth * chans
    stride = (w * bits + 7) // 8
    bpp = max(1, bits // 8)
    raw = zlib.decompress(b"".join(idat))
    out = np.zeros((h, stride), np.uint8)
    prev = np.zeros(stride, np.uint8)
    p = 0
    for y in range(h):
        f = raw[p]
        row = np.frombuffer(raw, np.uint8, stride, p + 1).copy()
        p += stride + 1
        if f == 1:
            r = row.reshape(-1, bpp) if stride % bpp == 0 else None
            if r is not None:
                row = np.cumsum(r, axis=0, dtype=np.uint8).reshape(-1)
            else:
                for i in range(bpp, stride):
                    row[i] = (int(row[i]) + int(row[i - bpp])) & 255
        elif f == 2:
            row = (row + prev).astype(np.uint8)
        elif f == 3:
            rl, pl = row.tolist(), prev.tolist()
            for i in range(stride):
                left = rl[i - bpp] if i >= bpp else 0
                rl[i] = (rl[i] + ((left + pl[i]) >> 1)) & 255
            row = np.array(rl, np.uint8)
        elif f == 4:
            rl, pl = row.tolist(), prev.tolist()
            for i in range(stride):
                a = rl[i - bpp] if i >= bpp else 0
                b = pl[i]
                c = pl[i - bpp] if i >= bpp else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                rl[i] = (rl[i] + pr) & 255
            row = np.array(rl, np.uint8)
        out[y] = row
        prev = row
    if depth == 16:
        samples = out.reshape(h, -1, 2)[:, :, 0].reshape(h, w, chans)
    elif depth == 8:
        samples = out.reshape(h, w, chans)
    else:  # 1, 2, 4 bits (grey or palette)
        per = 8 // depth
        bitsarr = np.unpackbits(out, axis=1).reshape(h, -1, depth)
        vals = (bitsarr * (1 << np.arange(depth - 1, -1, -1))).sum(axis=2)[:, :w]
        samples = vals.reshape(h, w, 1).astype(np.uint8)
        if ctype == 0:
            samples = (samples * (255 // (2 ** depth - 1))).astype(np.uint8)
    if ctype == 3:
        pal = plte.astype(np.float32) / 255
        idx = samples[:, :, 0]
        rgb = pal[np.minimum(idx, len(pal) - 1)]
        alpha = np.ones((h, w), np.float32)
        if trns:
            ta = np.full(len(pal), 255, np.uint8)
            ta[:len(trns)] = np.frombuffer(trns, np.uint8)[:len(pal)]
            alpha = (ta[np.minimum(idx, len(pal) - 1)] / 255).astype(np.float32)
        return np.dstack([rgb, alpha]).astype(np.float32)
    s = samples.astype(np.float32) / 255
    if ctype == 0:
        return np.dstack([s, s, s, np.ones((h, w, 1), np.float32)])
    if ctype == 4:
        return np.dstack([s[:, :, :1], s[:, :, :1], s[:, :, :1], s[:, :, 1:2]])
    if ctype == 2:
        return np.dstack([s, np.ones((h, w, 1), np.float32)])
    return s


def _chunk(typ, body):
    return struct.pack(">I", len(body)) + typ + body + struct.pack(">I", zlib.crc32(typ + body) & 0xFFFFFFFF)


def _filtered(img, bpp):
    """Scanlines of img (h, stride) uint8 with the cheapest of None/Sub/Up per row (smallest sum of absolute residuals)."""
    h, stride = img.shape
    out = bytearray()
    prev = np.zeros(stride, np.uint8)
    for y in range(h):
        row = img[y]
        cands = [row]
        sub = row.copy()
        sub[bpp:] = row[bpp:] - row[:-bpp]
        cands.append(sub)
        cands.append((row - prev).astype(np.uint8))
        best, bf = None, 0
        for f, c in enumerate(cands):
            sc = np.abs(c.astype(np.int8).astype(np.int32)).sum()
            if best is None or sc < best:
                best, bf = sc, f
        out.append(bf)
        out += cands[bf].tobytes()
        prev = row
    return bytes(out)


def png_encode_rgba(rgba):
    """uint8 (h, w, 4) -> PNG bytes, truecolour with alpha."""
    h, w, _ = rgba.shape
    body = _filtered(rgba.reshape(h, w * 4), 4)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(body, 9)) + _chunk(b"IEND", b""))


def quantize(rgba, ncolors=256):
    """Median-cut an RGBA image to <= ncolors palette entries (alpha kept per entry). Returns (indices (h,w), palette (n,4))."""
    h, w, _ = rgba.shape
    flat = rgba.reshape(-1, 4)
    key = flat.astype(np.uint32)
    packed = (key[:, 0] << 24) | (key[:, 1] << 16) | (key[:, 2] << 8) | key[:, 3]
    uniq, inv, counts = np.unique(packed, return_inverse=True, return_counts=True)
    cols = np.stack([(uniq >> 24) & 255, (uniq >> 16) & 255, (uniq >> 8) & 255, uniq & 255], axis=1).astype(np.float32)
    if len(uniq) <= ncolors:
        return inv.reshape(h, w).astype(np.uint8), cols.astype(np.uint8)
    # fully transparent pixels get their own entry; the rest are split by median cut (alpha scaled so it counts)
    clear = cols[:, 3] == 0
    pal = []
    work = np.where(~clear)[0]
    boxes = [work]
    target = ncolors - (1 if clear.any() else 0)
    scale = np.array([1, 1, 1, 0.6], np.float32)
    while len(boxes) < target:
        best, bi = -1, -1
        for i, b in enumerate(boxes):
            if len(b) < 2:
                continue
            c = cols[b] * scale
            ext = (c.max(axis=0) - c.min(axis=0))
            sc = ext.max() * counts[b].sum() ** 0.5
            if sc > best:
                best, bi = sc, i
        if bi < 0:
            break
        b = boxes.pop(bi)
        c = cols[b] * scale
        ch = int(np.argmax(c.max(axis=0) - c.min(axis=0)))
        order = b[np.argsort(c[:, ch], kind="stable")]
        cum = np.cumsum(counts[order])
        cut = int(np.searchsorted(cum, cum[-1] / 2)) + 1
        cut = min(max(cut, 1), len(order) - 1)
        boxes.append(order[:cut])
        boxes.append(order[cut:])
    palette = np.array([np.average(cols[b], axis=0, weights=counts[b]) for b in boxes], np.float32)
    owner = np.zeros(len(uniq), np.int32)
    for i in range(0, len(uniq), 4096):
        part = cols[i:i + 4096] * scale
        d = ((part[:, None, :] - (palette * scale)[None, :, :]) ** 2).sum(axis=2)
        owner[i:i + 4096] = d.argmin(axis=1)
    if clear.any():
        palette = np.vstack([palette, [[0, 0, 0, 0]]])
        owner[clear] = len(palette) - 1
    return owner[inv].reshape(h, w).astype(np.uint8), np.clip(np.round(palette), 0, 255).astype(np.uint8)


def png_encode(rgba, ncolors=256):
    """uint8 (h, w, 4) -> PNG bytes: a palette PNG with per-entry alpha (tRNS), falling back to truecolour above 256 colours."""
    if ncolors > 256 or ncolors <= 0:
        return png_encode_rgba(rgba)
    h, w, _ = rgba.shape
    idx, pal = quantize(rgba, ncolors)
    trns = pal[:, 3].tobytes()
    parts = [b"\x89PNG\r\n\x1a\n", _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 3, 0, 0, 0)),
             _chunk(b"PLTE", pal[:, :3].tobytes())]
    if (pal[:, 3] != 255).any():
        parts.append(_chunk(b"tRNS", trns))
    parts.append(_chunk(b"IDAT", zlib.compress(_filtered(idx, 1), 9)))
    parts.append(_chunk(b"IEND", b""))
    return b"".join(parts)


_AREA = {}


def resize_area(img, nh, nw):
    """Box-filter a float32 RGBA image (premultiplied during the average) to (nh, nw)."""
    h, w, _ = img.shape

    def mat(n_old, n_new):
        k = (n_old, n_new)
        if k not in _AREA:
            m = np.zeros((n_new, n_old), np.float32)
            sc = n_old / n_new
            for i in range(n_new):
                lo, hi = i * sc, (i + 1) * sc
                for j in range(int(lo), min(int(math.ceil(hi - 1e-9)), n_old)):
                    m[i, j] = max(0.0, min(hi, j + 1) - max(lo, j))
            _AREA[k] = m / sc
        return _AREA[k]
    pm = img.copy()
    pm[:, :, :3] *= pm[:, :, 3:4]
    out = np.einsum("ij,jkc->ikc", mat(h, nh), pm)
    out = np.einsum("kj,ijc->ikc", mat(w, nw), out)
    a = out[:, :, 3:4]
    out[:, :, :3] = np.where(a > 1e-6, out[:, :, :3] / np.maximum(a, 1e-6), 0)
    return out


# ======================================================================== assets
def find_mc_jar():
    cands = [os.environ.get("MC_CLIENT_JAR", "")]
    cands += glob.glob(os.path.join(os.environ.get("APPDATA", ""), "PrismLauncher", "libraries", "net", "minecraft", "client", "1.21.1", "client-1.21.1*.jar"))
    cands += glob.glob(os.path.join(os.path.expanduser("~"), ".gradle", "caches", "**", "client-1.21.1*.jar"), recursive=True)
    cands += glob.glob(os.path.join(os.path.expanduser("~"), ".minecraft", "versions", "1.21.1", "1.21.1.jar"))
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


def default_jars(mc_jar=None, extra=()):
    tfc = sorted(glob.glob(os.path.join(MODS_DIR, "TerraFirmaCraft-NeoForge-1.21.1-*.jar")))
    mc = mc_jar or find_mc_jar()
    rest = [j for j in sorted(glob.glob(os.path.join(MODS_DIR, "*.jar"))) if j not in tfc]
    return tfc + ([mc] if mc else []) + list(extra) + rest


class Assets:
    """Resource lookup across jars in priority order: the first jar holding an assets/ path wins."""

    def __init__(self, jars):
        self.zips, self.index = [], {}
        self.namespaces = set()
        for j in jars:
            try:
                z = zipfile.ZipFile(j)
            except (OSError, zipfile.BadZipFile):
                continue
            zi = len(self.zips)
            self.zips.append(z)
            for n in z.namelist():
                if n.startswith("assets/") and not n.endswith("/"):
                    self.index.setdefault(n, zi)
                    self.namespaces.add(n.split("/", 2)[1])
        self._json, self._tex = {}, {}

    def read(self, path):
        zi = self.index.get(path)
        return None if zi is None else self.zips[zi].read(path)

    def has(self, path):
        return path in self.index

    def json(self, path):
        if path not in self._json:
            raw = self.read(path)
            try:
                self._json[path] = json.loads(raw.decode("utf-8-sig")) if raw is not None else None
            except ValueError:
                self._json[path] = None
        return self._json[path]

    def texture(self, tid):
        """float32 RGBA (h, w, 4) of a texture id ('ns:block/x' or 'flat:RRGGBB'); the first frame of an animated strip."""
        if tid in self._tex:
            return self._tex[tid]
        arr = None
        if tid.startswith("flat:"):
            c = tid[5:]
            arr = np.array([[[int(c[0:2], 16) / 255, int(c[2:4], 16) / 255, int(c[4:6], 16) / 255, 1.0]]], np.float32)
        else:
            ns, _, p = tid.rpartition(":")
            ns = ns or "minecraft"
            raw = self.read(f"assets/{ns}/textures/{p}.png")
            if raw is not None:
                try:
                    arr = png_decode(raw)
                except Exception:
                    arr = None
                if arr is not None and arr.shape[0] > arr.shape[1] and arr.shape[0] % arr.shape[1] == 0:
                    arr = arr[:arr.shape[1]]
        self._tex[tid] = arr
        return arr


def split_id(i, default="minecraft"):
    ns, _, p = i.rpartition(":")
    return (ns or default), p


# ======================================================================== models
def rot_axis(p, origin, axis, deg):
    """Right-handed rotation of point p about the axis through origin."""
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    x, y, z = (p[0] - origin[0], p[1] - origin[1], p[2] - origin[2])
    if axis == "x":
        y, z = y * c - z * s, y * s + z * c
    elif axis == "y":
        x, z = x * c + z * s, -x * s + z * c
    else:
        x, y = x * c - y * s, x * s + y * c
    return (x + origin[0], y + origin[1], z + origin[2])


def default_uv(d, f, t):
    if d == "up":
        return [f[0], f[2], t[0], t[2]]
    if d == "down":
        return [f[0], 16 - t[2], t[0], 16 - f[2]]
    if d == "north":
        return [16 - t[0], 16 - t[1], 16 - f[0], 16 - f[1]]
    if d == "south":
        return [f[0], 16 - t[1], t[0], 16 - f[1]]
    if d == "west":
        return [f[2], 16 - t[1], t[2], 16 - f[1]]
    return [16 - t[2], 16 - t[1], 16 - f[2], 16 - f[1]]


def face_frame(d, f, t):
    """(origin, U, V) in 0..1 block units: the texture's top-left corner and its right and down edges for that face."""
    f = [v / 16 for v in f]
    t = [v / 16 for v in t]
    dx, dy, dz = t[0] - f[0], t[1] - f[1], t[2] - f[2]
    if d == "up":
        return (f[0], t[1], f[2]), (dx, 0, 0), (0, 0, dz)
    if d == "down":
        return (f[0], f[1], t[2]), (dx, 0, 0), (0, 0, -dz)
    if d == "north":
        return (t[0], t[1], f[2]), (-dx, 0, 0), (0, -dy, 0)
    if d == "south":
        return (f[0], t[1], t[2]), (dx, 0, 0), (0, -dy, 0)
    if d == "west":
        return (f[0], t[1], f[2]), (0, 0, dz), (0, -dy, 0)
    return (t[0], t[1], t[2]), (0, 0, -dz), (0, -dy, 0)


def _rot_vec(v, axis, deg):
    return rot_axis(v, (0, 0, 0), axis, deg)


def shade_of(n):
    """Brightness of a face by its normal: top 1.0, the two visible sides 0.80 (+z) and 0.62 (+x), bottom 0.5."""
    ny = n[1]
    return max(ny, 0) + 0.5 * max(-ny, 0) + 0.80 * abs(n[2]) + 0.62 * abs(n[0])


def fluid_kind(name):
    """'water' or 'lava' for fluid blocks (vanilla's and TFC's), else None."""
    m = re.match(r"^(?:minecraft|tfc):(?:fluid/)?([a-z_]*(water|lava))$", name)
    return m.group(2) if m else None


DEFAULT_VALUES = {"false", "0", "none", "bottom", "lower", "straight", "normal", "floor", "north", "low"}


class Models:
    """blockstate -> model -> baked quads, with the fallbacks for blocks no model describes."""

    def __init__(self, assets):
        self.A = assets
        self._model, self._baked, self._opaque = {}, {}, {}

    # ---- blockstates
    def blockstate(self, name):
        ns, p = split_id(name)
        return self.A.json(f"assets/{ns}/blockstates/{p}.json")

    @staticmethod
    def _pv(v):
        return str(v).lower() if isinstance(v, bool) else str(v)

    @classmethod
    def _cond(cls, when, props):
        if "OR" in when:
            return any(cls._cond(w, props) for w in when["OR"])
        if "AND" in when:
            return all(cls._cond(w, props) for w in when["AND"])
        for k, v in when.items():
            have = props.get(k)
            want = cls._pv(v).split("|")
            if have is None:  # a property the template did not save: its usual default
                if not any(w in DEFAULT_VALUES for w in want):
                    return False
            elif have not in want:
                return False
        return True

    def parts_for(self, name, props):
        """The (model id, x, y, uvlock) list a blockstate gives for these properties, or None if it has no blockstate."""
        bs = self.blockstate(name)
        if not bs:
            return None
        out = []
        if "variants" in bs:
            best, bscore = None, -1
            for key, val in bs["variants"].items():
                score, ok = 0, True
                for pair in (key.split(",") if key and key != "normal" else []):
                    k, _, v = pair.partition("=")
                    if k in props:
                        if props[k] == v:
                            score += 1
                        else:
                            ok = False
                            break
                if ok and score > bscore:
                    best, bscore = val, score
            if best is None:
                best = next(iter(bs["variants"].values()), None)
            if isinstance(best, list):
                best = best[0]
            if best and "model" in best:
                out.append((best["model"], best.get("x", 0), best.get("y", 0), best.get("uvlock", False)))
        for part in bs.get("multipart", []):
            if "when" in part and not self._cond(part["when"], props):
                continue
            ap = part["apply"]
            if isinstance(ap, list):
                ap = ap[0]
            out.append((ap["model"], ap.get("x", 0), ap.get("y", 0), ap.get("uvlock", False)))
        return out

    # ---- models
    def model(self, mid):
        """Resolved model: {'elements': [...], 'textures': {name: id}} through the parent chain, or None."""
        if mid in self._model:
            return self._model[mid]
        self._model[mid] = None
        ns, p = split_id(mid)
        j = self.A.json(f"assets/{ns}/models/{p}.json")
        if j is None:
            return None
        for variant in ("dense_leaves", "blooming", "seeding", "budding", "sprouting", "dormant", "dying"):
            if isinstance(j.get(variant), dict) and "parent" in j[variant]:  # TFC's seasonal models: summer look
                r = self.model(j[variant]["parent"])
                self._model[mid] = r
                return r
        textures, elements = {}, None
        parent = j.get("parent")
        if parent:
            pm = None if parent.endswith(("builtin/generated", "builtin/entity", "builtin/missing")) else self.model(parent)
            if pm:
                textures = dict(pm["textures"])
                elements = pm["elements"]
        textures.update(j.get("textures", {}))
        if "elements" in j:
            elements = j["elements"]
        self._model[mid] = {"elements": elements or [], "textures": textures}
        return self._model[mid]

    def resolve_tex(self, textures, ref):
        seen = 0
        while ref and ref.startswith("#") and seen < 12:
            ref = textures.get(ref[1:])
            seen += 1
        return None if (ref is None or ref.startswith("#")) else ref

    # ---- baking
    def bake_model(self, model, xr, yr, uvlock, name, view_yaw, tint, override=None):
        quads = []
        for el in model["elements"]:
            f, t = el["from"], el["to"]
            rot = el.get("rotation")
            shade = el.get("shade", True)
            for d, fc in el.get("faces", {}).items():
                if d not in DIRS:
                    continue
                tex = override or self.resolve_tex(model["textures"], fc.get("texture"))
                uv = fc.get("uv") or default_uv(d, f, t)
                org, U, V = face_frame(d, f, t)
                pts = [org, tuple(org[i] + U[i] for i in range(3)), tuple(org[i] + V[i] for i in range(3))]
                nrm = DIRS[d]
                if rot:
                    ax, ang = rot["axis"], rot["angle"]
                    o = tuple(v / 16 for v in rot["origin"])
                    pts = [rot_axis(p, o, ax, ang) for p in pts]
                    nrm = _rot_vec(nrm, ax, ang)
                    if rot.get("rescale") and ang:
                        k = 1 / math.cos(math.radians(abs(ang)))
                        sc = {"x": (1, k, k), "y": (k, 1, k), "z": (k, k, 1)}[ax]
                        pts = [tuple(o[i] + (p[i] - o[i]) * sc[i] for i in range(3)) for p in pts]
                c = (0.5, 0.5, 0.5)
                if xr:
                    pts = [rot_axis(p, c, "x", -xr) for p in pts]
                    nrm = _rot_vec(nrm, "x", -xr)
                total_y = (yr + view_yaw) % 360
                if total_y:
                    pts = [rot_axis(p, c, "y", -total_y) for p in pts]
                    nrm = _rot_vec(nrm, "y", -total_y)
                trot = fc.get("rotation", 0)
                if uvlock and d == "up" and yr:
                    trot = (trot + 360 - yr) % 360
                ti = fc.get("tintindex")
                quads.append({
                    "A": np.array(pts[0], np.float64), "U": np.array(pts[1], np.float64) - np.array(pts[0], np.float64),
                    "V": np.array(pts[2], np.float64) - np.array(pts[0], np.float64), "n": nrm, "tex": tex, "uv": uv,
                    "rot": trot, "tint": self.tint_for(name, ti, tint) if ti is not None else None,
                    "light": shade_of(nrm) if shade else 1.0, "alpha": fc.get("alpha", 1.0)})
        return quads

    @staticmethod
    def tint_for(name, ti, profile):
        short = name.split(":")[-1]
        if "water" in short:
            return WATER_TINT
        for k, v in FIXED_FOLIAGE.items():
            if short.endswith(k) or short.endswith("/" + k):
                return v
        prof = TINTS[profile]
        if "leaves" in short or "vine" in short or "foliage" in short:
            return prof["foliage"]
        return prof["grass"]

    def synthetic(self, name, props, particle):
        """Model dict for blocks drawn by entity renderers or with no model; None to use the flat-colour cube."""
        short = name.split(":")[-1]
        base = short.split("/")[-1]
        kind = short.split("/")[0] if "/" in short else base
        t = {"all": particle} if particle else None
        if t is None:
            return None

        def box(f, to, faces=("up", "down", "north", "south", "west", "east")):
            return {"from": f, "to": to, "faces": {d: {"texture": "#all"} for d in faces}}
        facing = props.get("facing", "south")
        if "chest" in short or "barrel" in short or "crate" in short:
            return {"elements": [box([1, 0, 1], [15, 14, 15])], "textures": t}
        if "bed" in short:
            return {"elements": [box([0, 3, 0], [16, 9, 16])], "textures": t}
        if "wall_sign" in short or "wall_hanging" in short:
            bx = {"north": ([0, 4, 14], [16, 12, 16]), "south": ([0, 4, 0], [16, 12, 2]),
                  "east": ([0, 4, 0], [2, 12, 16]), "west": ([14, 4, 0], [16, 12, 16])}[facing if facing in DIRS else "south"]
            return {"elements": [box(*bx)], "textures": t}
        if "sign" in short:
            return {"elements": [box([7, 0, 7], [9, 8, 9]), box([0, 8, 7], [16, 16, 9])], "textures": t}
        if "banner" in short:
            return {"elements": [box([7, 0, 7], [9, 24, 9])] if "wall" not in short else [box([0, 4, 14], [16, 20, 16])], "textures": t}
        if "skull" in short or "head" in short:
            return {"elements": [box([4, 0, 4], [12, 8, 12])], "textures": t}
        if "shulker" in short or "decorated_pot" in short:
            return {"elements": [box([1, 0, 1], [15, 14, 15])], "textures": t}
        if short.endswith("slab"):
            return {"elements": [box([0, 0, 0], [16, 8, 16])], "textures": t}
        return {"elements": [box([0, 0, 0], [16, 16, 16])], "textures": t}

    def particle_of(self, parts):
        for mid, *_ in parts:
            m = self.model(mid)
            if m:
                p = self.resolve_tex(m["textures"], "#particle")
                if p:
                    return p
                for k in m["textures"]:
                    r = self.resolve_tex(m["textures"], "#" + k)
                    if r and self.A.texture(r) is not None:
                        return r
        return None

    def name_colour(self, name):
        h = 0
        for ch in name:
            h = (h * 131 + ord(ch)) & 0xFFFFFF
        r, g, b = (h >> 16) & 255, (h >> 8) & 255, h & 255
        # keep it mid-tone so it never reads as air or void
        return "%02x%02x%02x" % (90 + r % 120, 90 + g % 120, 90 + b % 120)

    def bake(self, name, props, view_yaw, tint, override=None):
        """(quads, status) for a block state: status 'ok', 'partial' (a texture missing), 'flat' (no model or texture).
        `override` is a texture id that replaces every face's texture (stand-ins keep a block's shape but not its look)."""
        key = (name, tuple(sorted(props.items())), view_yaw, tint, override)
        if key in self._baked:
            return self._baked[key]
        quads, status = self._bake(name, props, view_yaw, tint, override)
        self._baked[key] = (quads, status)
        return quads, status

    def _bake(self, name, props, view_yaw, tint, override=None):
        short = name.split(":")[-1]
        fk = fluid_kind(name)
        if fk == "water":
            m = {"elements": [{"from": [0, 0, 0], "to": [16, 14, 16], "faces": {d: {"texture": "#all", "tintindex": 0, "alpha": 0.62}
                                                                               for d in DIRS}}],
                 "textures": {"all": "minecraft:block/water_still"}}
            return self.bake_model(m, 0, 0, False, name, view_yaw, tint), "ok"
        if fk == "lava":
            m = {"elements": [{"from": [0, 0, 0], "to": [16, 14, 16], "faces": {d: {"texture": "#all"} for d in DIRS}}],
                 "textures": {"all": "minecraft:block/lava_still"}}
            return self.bake_model(m, 0, 0, False, name, view_yaw, tint), "ok"
        parts = self.parts_for(name, props)
        quads, missing, used = [], False, False
        if parts:
            for mid, xr, yr, uvl in parts:
                m = self.model(mid)
                if not m:
                    continue
                if not m["elements"]:
                    sm = self.synthetic(name, props, self.particle_of([(mid,)]))
                    if sm:
                        m = sm
                    else:
                        continue
                used = True
                quads += self.bake_model(m, xr, yr, uvl, name, view_yaw, tint, override)
        if parts is not None and not used:  # blockstate known but nothing drawable (e.g. only a particle)
            particle = self.particle_of(parts) if parts else None
            sm = self.synthetic(name, props, particle)
            if sm:
                quads = self.bake_model(sm, 0, 0, False, name, view_yaw, tint, override)
                used = True
            elif parts is not None and all(self.model(mid) is not None for mid, *_ in parts) and not particle:
                return [], "empty"  # drawn by code in game (ingot piles, scrapings): nothing to show
        if used:
            for q in quads:
                if q["tex"] is None or self.A.texture(q["tex"]) is None:
                    missing = True
                    q["tex"] = "flat:" + self.name_colour(name)
            return quads, ("partial" if missing else "ok")
        # no blockstate or no model: a flat-colour box (a slab or a full cube)
        h = 8 if short.endswith("slab") else 16
        m = {"elements": [{"from": [0, 0, 0], "to": [16, h, 16], "faces": {d: {"texture": "#all"} for d in DIRS}}],
             "textures": {"all": override or "flat:" + self.name_colour(name)}}
        return self.bake_model(m, 0, 0, False, name, view_yaw, tint), "flat"

    def is_opaque_cube(self, name, props):
        """True for a full cube whose faces are all fully opaque: it hides what is behind it."""
        key = (name, tuple(sorted(props.items())))
        if key in self._opaque:
            return self._opaque[key]
        res = False
        short = name.split(":")[-1]
        if not fluid_kind(name):
            parts = self.parts_for(name, props)
            if parts and len(parts) >= 1:
                for mid, *_ in parts:
                    m = self.model(mid)
                    if not m:
                        continue
                    for el in m["elements"]:
                        if el["from"] == [0, 0, 0] and el["to"] == [16, 16, 16] and all(d in el.get("faces", {}) for d in DIRS):
                            ok = True
                            for d, fc in el["faces"].items():
                                tid = self.resolve_tex(m["textures"], fc.get("texture"))
                                tx = self.A.texture(tid) if tid else None
                                if tx is None or (tx[:, :, 3] < 0.999).any():
                                    ok = False
                                    break
                            if ok:
                                res = True
        self._opaque[key] = res
        return res


# ======================================================================== sprite + canvas
class SpriteMaker:
    def __init__(self, assets):
        self.A = assets
        self._mip = {}

    def mip(self, tid, a):
        k = (tid, a)
        if k not in self._mip:
            tx = self.A.texture(tid)
            if tx is not None and a < tx.shape[1]:
                tx = resize_area(tx, a, a)
            self._mip[k] = tx
        return self._mip[k]

    def make(self, quads, a):
        """Premultiplied RGBA float sprite of the quads at `a` px per block unit, plus the offset of its top-left corner from
        the block's origin corner on screen."""
        if not quads:
            return None
        pts = []
        for q in quads:
            for s, t in ((0, 0), (1, 0), (0, 1), (1, 1)):
                p = q["A"] + s * q["U"] + t * q["V"]
                pts.append(((p[0] - p[2]) * a, (p[0] + p[2]) * a / 2 - p[1] * a))
        pts = np.array(pts)
        x0, y0 = int(math.floor(pts[:, 0].min())), int(math.floor(pts[:, 1].min()))
        x1, y1 = int(math.ceil(pts[:, 0].max())), int(math.ceil(pts[:, 1].max()))
        w, h = max(1, x1 - x0), max(1, y1 - y0)
        col = np.zeros((h, w, 4), np.float32)
        depth = np.full((h, w), -1e9, np.float32)
        for q in quads:
            nz = q["n"][0] + q["n"][1] + q["n"][2]
            if nz < 1e-6:
                continue
            tex = self.mip(q["tex"], a)
            if tex is None:
                continue
            A, U, V = q["A"], q["U"], q["V"]
            sa = np.array([(A[0] - A[2]) * a, (A[0] + A[2]) * a / 2 - A[1] * a])
            su = np.array([(U[0] - U[2]) * a, (U[0] + U[2]) * a / 2 - U[1] * a])
            sv = np.array([(V[0] - V[2]) * a, (V[0] + V[2]) * a / 2 - V[1] * a])
            det = su[0] * sv[1] - su[1] * sv[0]
            if abs(det) < 1e-6:
                continue
            cs = np.array([sa, sa + su, sa + sv, sa + su + sv])
            bx0 = max(int(math.floor(cs[:, 0].min())) - x0, 0)
            bx1 = min(int(math.ceil(cs[:, 0].max())) - x0, w)
            by0 = max(int(math.floor(cs[:, 1].min())) - y0, 0)
            by1 = min(int(math.ceil(cs[:, 1].max())) - y0, h)
            if bx1 <= bx0 or by1 <= by0:
                continue
            px = (np.arange(bx0, bx1) + x0 + 0.5)[None, :] - sa[0]
            py = (np.arange(by0, by1) + y0 + 0.5)[:, None] - sa[1]
            s = (px * sv[1] - py * sv[0]) / det
            t = (su[0] * py - su[1] * px) / det
            eps = 1e-4
            inside = (s >= -eps) & (s < 1 + eps) & (t >= -eps) & (t < 1 + eps)
            if not inside.any():
                continue
            sc, tc = np.clip(s, 0, 0.99999), np.clip(t, 0, 0.99999)
            r = q["rot"]
            if r == 90:
                ts, tt = tc, 1 - sc
            elif r == 180:
                ts, tt = 1 - sc, 1 - tc
            elif r == 270:
                ts, tt = 1 - tc, sc
            else:
                ts, tt = sc, tc
            u0, v0, u1, v1 = q["uv"]
            th, tw = tex.shape[:2]
            ci = np.clip(np.floor((u0 + ts * (u1 - u0)) / 16 * tw).astype(int), 0, tw - 1)
            ri = np.clip(np.floor((v0 + tt * (v1 - v0)) / 16 * th).astype(int), 0, th - 1)
            px4 = tex[ri, ci]
            rgb = px4[:, :, :3] * q["light"]
            if q["tint"] is not None:
                rgb = rgb * (np.array(q["tint"], np.float32) / 255)
            al = px4[:, :, 3] * q["alpha"]
            d = (A[0] + A[1] + A[2]) + s * (U[0] + U[1] + U[2]) + t * (V[0] + V[1] + V[2])
            vis = inside & (al > 0.04)
            if not vis.any():
                continue
            sub = col[by0:by1, bx0:bx1]
            dsub = depth[by0:by1, bx0:bx1]
            src = np.dstack([rgb * al[:, :, None], al])
            closer = vis & (d > dsub)
            behind = vis & ~closer
            sub[closer] = src[closer] + sub[closer] * (1 - al[closer])[:, None]
            sub[behind] = sub[behind] + src[behind] * (1 - sub[behind][:, 3:4])
            dsub[closer & (al > 0.5)] = d[closer & (al > 0.5)]
        return col, x0, y0


# ======================================================================== templates
class Template:
    def __init__(self, root, name=""):
        self.name = name
        size = root.get("size") or [0, 0, 0]
        self.size = tuple(int(v) for v in size)
        pal = root.get("palette")
        if pal is None and root.get("palettes"):
            pal = root["palettes"][0]
        self.palette = []
        for e in pal or []:
            self.palette.append((str(e["Name"]), {k: str(v) for k, v in (e.get("Properties") or {}).items()}))
        self.blocks = [(tuple(int(c) for c in b["pos"]), int(b["state"])) for b in root.get("blocks", [])]
        # Framed Blocks keep the block they imitate in their block entity: {camo: {state: {Name: ...}}}
        self.camo = {}
        for b in root.get("blocks", []):
            c = (b.get("nbt") or {}).get("camo")
            if isinstance(c, dict) and isinstance(c.get("state"), dict) and "Name" in c["state"]:
                self.camo[tuple(int(v) for v in b["pos"])] = c["state"]["Name"]


def load_template(path_or_bytes, name=""):
    data = path_or_bytes if isinstance(path_or_bytes, (bytes, bytearray)) else open(path_or_bytes, "rb").read()
    return Template(N.loads(bytes(data)), name)


# TFC 3 (Minecraft 1.20.1) soil names that TFC 4 replaced (loam, sandy loam, silt, silty loam -> its eight soils)
SOIL3 = {"loam": "alfisol", "sandy_loam": "aridisol", "silt": "fluvisol", "silty_loam": "mollisol"}
# extra woods other mods add, drawn as the nearest-looking TFC wood
EXTRA_WOODS = {"cypress": "white_cedar", "mahogany": "rosewood", "ironwood": "blackwood", "teak": "hickory", "baobab": "sequoia",
               "gum_arabic": "acacia", "eucalyptus": "douglas_fir", "fig": "mangrove", "ebony": "blackwood", "jacaranda": "rosewood"}
MOD_WOOD_VARIANTS = ("fence", "log_fence", "fence_gate", "door", "trapdoor", "tool_rack", "bookshelf", "workbench", "loom", "button",
                     "pressure_plate", "sign", "barrel", "chest", "sewing_table", "scribing_table")
WOOD_SUFFIXES = ("fence_gate", "log_fence", "fence", "door", "trapdoor", "button", "pressure_plate", "tool_rack", "bookshelf", "loom",
                 "workbench", "lectern", "scribing_table", "sewing_table", "shelf", "crate")
COLOURS = ("white", "orange", "magenta", "light_blue", "yellow", "lime", "pink", "gray", "light_gray", "cyan", "purple", "blue",
           "brown", "green", "red", "black")
# keyword -> vanilla block whose model gives the shape of a block no jar knows (checked in this order)
SHAPES = [("fence_gate", "minecraft:oak_fence_gate"), ("trapdoor", "minecraft:oak_trapdoor"), ("door", "minecraft:oak_door"),
          ("stairs", "minecraft:oak_stairs"), ("slope", "minecraft:oak_stairs"), ("prism", "minecraft:oak_stairs"),
          ("slab", "minecraft:oak_slab"), ("panel", "minecraft:oak_slab"), ("board", "minecraft:oak_slab"), ("tile", "minecraft:oak_slab"),
          ("strip", "minecraft:oak_slab"), ("fence", "minecraft:oak_fence"), ("wall", "minecraft:cobblestone_wall"),
          ("pillar", "minecraft:oak_fence"), ("ladder", "minecraft:ladder"), ("pane", "minecraft:glass_pane"),
          ("carpet", "minecraft:white_carpet"), ("chest", "minecraft:chest"), ("roof", "minecraft:oak_stairs")]
FLAT_KEYWORDS = [("thatch", "c9b45a"), ("sand", "dccf9a"), ("brick", "9b6a55"), ("stone", "8a8a8a"), ("rock", "8a8a8a"),
                 ("gravel", "8c8680"), ("road", "8c8680"), ("plank", "b08a58"), ("wood", "9a7a4a"), ("log", "6a5030"),
                 ("shingle", "6a4a38"), ("glass", "b8d8e8"), ("carpet", "b0b0b0"), ("clay", "a0624a"), ("dirt", "70573a")]


class Eff:
    """What to draw for one placed block: a block id and properties the jars can model, an optional texture that replaces
    its own, and how it was found: 'direct', 'alt' (TFC 3 id -> TFC 4), 'standin' (another mod's block, approximated) or 'hide'."""
    __slots__ = ("name", "props", "override", "kind")

    def __init__(self, name, props, override=None, kind="direct"):
        self.name, self.props, self.override, self.kind = name, props, override, kind


class Renderer:
    def __init__(self, assets=None, jars=None):
        self.A = assets or Assets(jars or default_jars())
        self.M = Models(self.A)
        self.S = SpriteMaker(self.A)
        self._sprites, self._eff = {}, {}
        base = "assets/tfc/blockstates/wood/planks/"
        self.woods = {n[len(base):-5] for n in self.A.index
                      if n.startswith(base) and "/" not in n[len(base):] and not n.endswith(("_stairs.json", "_slab.json"))}

    def has(self, i):
        return self.M.blockstate(i) is not None

    # ------------------------------------------------------------------ ids
    def wood_for(self, w):
        w = w[len("stripped_"):] if w.startswith("stripped_") else w
        if w in self.woods:
            return w
        if w in EXTRA_WOODS and EXTRA_WOODS[w] in self.woods:
            return EXTRA_WOODS[w]
        h = sum(ord(c) for c in w)
        return sorted(self.woods)[h % len(self.woods)] if self.woods else "oak"

    def tfc_alternatives(self, name):
        """TFC 4 ids for a TFC 3-style or other mod's wood, rock and soil block (candidates in order)."""
        ns, p = split_id(name)
        out = []
        for old, new in SOIL3.items():
            if re.search(r"/" + old + r"(_slab|_stairs|_wall)?$", p):
                out.append(f"{ns}:" + re.sub(r"/" + old + r"(?=(_slab|_stairs|_wall)?$)", "/" + new, p))
        m = re.match(r"^wood/(?P<kind>[a-z_]+)/(?P<rest>[a-z_]+)$", p)
        if m:
            kind, rest = m.group("kind"), m.group("rest")
            suf = next((x for x in ("slab", "stairs") + WOOD_SUFFIXES if rest.endswith("_" + x) and len(rest) > len(x) + 1), None)
            w = self.wood_for(rest[:-len(suf) - 1] if suf else rest)
            if kind == "planks":
                out.append(f"tfc:wood/planks/{w}_{suf}" if suf in ("slab", "stairs") else (f"tfc:wood/{suf}/{w}" if suf else f"tfc:wood/planks/{w}"))
            elif kind in ("log", "stripped_log", "wood", "stripped_wood", "leaves", "sapling", "twig", "chest", "trapped_chest", "bookshelf",
                          "workbench", "loom", "tool_rack", "lectern", "door", "trapdoor", "fence", "fence_gate", "log_fence", "sign", "shelf"):
                out.append(f"tfc:wood/{kind}/{w}")
            elif "barrel" in kind or "shelf" in kind:
                out.append(f"tfc:wood/barrel/{w}")
            elif kind in ("lumber", "support", "axle"):
                out.append(f"tfc:wood/vertical_support/{w}")
        m = re.match(r"^rock/(raw|hardened|bricks|smooth|cobble|mossy_cobble|mossy_bricks|cracked_bricks|loose|spike|gravel)/(.+)$", p)
        if m:
            out.append(f"tfc:rock/{m.group(1)}/{m.group(2)}")
        if p == "thatch":
            out.append("tfc:thatch")
        if p.startswith("grass/") or p.startswith("dirt/"):
            out.append(f"tfc:{p}")
        return out

    def material_texture(self, block):
        """A texture id that stands for a block: the first of its model's textures (all, side, top, particle, ...) that is
        nearly opaque, else the most opaque one; None if the block has no model."""
        e = self.effective(block, {})
        if e.kind == "hide":
            return None
        cands = []
        for mid, *_ in self.M.parts_for(e.name, e.props) or []:
            m = self.M.model(mid)
            if not m:
                continue
            for k in ("all", "side", "texture", "top", "particle", *m["textures"]):
                tid = self.M.resolve_tex(m["textures"], "#" + k)
                if tid and tid not in cands and self.A.texture(tid) is not None:
                    cands.append(tid)
        for tid in cands:
            if self.A.texture(tid)[:, :, 3].mean() >= 0.95:
                return tid
        return max(cands, key=lambda t: self.A.texture(t)[:, :, 3].mean()) if cands else None

    def _shape_standin(self, name, props, override):
        short = name.split(":")[-1]
        for kw, base in SHAPES:
            if kw in short:
                p = dict(props)
                if base.endswith("_slab"):
                    p["type"] = "top" if props.get("top") == "true" or props.get("half") == "top" else (p.get("type") or "bottom")
                if base.endswith("cobblestone_wall"):
                    for k in ("north", "east", "south", "west"):
                        if p.get(k) == "true":
                            p[k] = "low"
                    p.setdefault("up", "true")
                return Eff(base, p, override, "standin")
        return Eff("minecraft:stone", {}, override, "standin")

    def effective(self, name, props, camo=None):
        key = (name, tuple(sorted(props.items())), camo)
        if key in self._eff:
            return self._eff[key]
        e = self._effective(name, props, camo)
        self._eff[key] = e
        return e

    def mod_renames(self, name):
        """Ids of the addon mods' 1.21 releases for a 1.20 id (found by comparing the TFG templates with the 1.21.1 jars)."""
        out = []
        m = re.match(r"^afc:wood/planks/([a-z_]+?)_(" + "|".join(sorted(MOD_WOOD_VARIANTS, key=len, reverse=True)) + r")$", name)
        if m:
            out.append(f"afc:wood/{m.group(2)}/{m.group(1)}")
        m = re.match(r"^(afc|firmalife):wood/big_barrel/([a-z_]+)$", name)
        if m:
            out.append(f"{m.group(1)}:wood/keg/{m.group(2)}")
        m = re.match(r"^firmalife:cured_oven_(bottom|top|chimney|hopper)$", name)
        if m:
            out.append(f"firmalife:clay_oven_{m.group(1)}")
        if name == "rnr:tamped_loam":
            out.append("rnr:tamped_alfisol")
        return out

    def _effective(self, name, props, camo):
        if name in HIDDEN:
            return Eff(name, props, None, "hide")
        ns, p = split_id(name)
        if ns == "framedblocks" and self.has(name):
            # Framed Blocks generates its shapes in code (every blockstate points at a cube model): the shape comes from the id
            # and the look from the camouflage block saved in each placed block.
            ov = self.material_texture(camo) if camo else None
            return self._shape_standin(name, props, ov or "flat:b08a58")
        if ns == "lootr":
            return Eff("minecraft:chest", {k: v for k, v in props.items() if k in ("facing", "type")}, None, "standin")
        if self.has(name):
            return Eff(name, props)
        short = p.split("/")[-1]
        if ns == "additionalplacements":
            return self.effective(p.replace(".", ":", 1), props, camo)
        for alt in self.mod_renames(name):
            if self.has(alt):
                return Eff(alt, props, None, "alt")
        for alt in self.tfc_alternatives(name):
            if self.has(alt):
                return Eff(alt, props, None, "alt")
        # decals and the like: nothing to draw
        if ns == "chalk" or p.endswith("dead_grass") or "groundcover" in p:
            return Eff(name, props, None, "hide")
        # framed blocks: the camouflage block's look in the shape the frame's id says
        if ns == "framedblocks":
            ov = self.material_texture(camo) if camo else None
            return self._shape_standin(name, props, ov or "flat:b08a58")
        if ns == "lootr":
            return Eff("minecraft:chest", {k: v for k, v in props.items() if k in ("facing", "type")}, None, "standin")
        colour = next((c for c in sorted(COLOURS, key=len, reverse=True) if re.search(r"(^|_|/)" + c + r"(_|$)", p)), None)
        if "carpet" in p:
            return Eff(f"minecraft:{colour or 'white'}_carpet", {}, None, "standin")
        if "paperwall" in p:
            return self._shape_standin("pane", props, self.material_texture("minecraft:white_wool"))
        if "vase" in p:
            v = f"tfc:ceramic/large_vessel/{colour}" if colour and self.has(f"tfc:ceramic/large_vessel/{colour}") else "tfc:ceramic/large_vessel"
            return Eff(v, {}, None, "standin") if self.has(v) else Eff("minecraft:flower_pot", {}, None, "standin")
        # materials by name: rock roads, thatch, shingles, roofs, furniture
        m = re.search(r"(gravel|cobbled|sett)_road/([a-z_]+?)(?:_(slab|stairs))?$", p)
        if m:
            variant = {"gravel": "gravel", "cobbled": "cobble", "sett": "bricks"}[m.group(1)]
            tex = self.material_texture(f"tfc:rock/{variant}/{m.group(2)}")
            return self._shape_standin("x_" + (m.group(3) or "block"), props, tex or "flat:8c8680")
        if "thatch" in p:
            return self._shape_standin(short, props, self.material_texture("tfc:thatch") or "flat:c9b45a")
        if short in ("hoggin", "tamped_loam", "base_course"):
            return Eff("minecraft:coarse_dirt", {}, None, "standin")
        m = re.search(r"shingles/([a-z_]+?)(?:_(slab|stairs))?$", p)
        if m:
            w = self.wood_for(m.group(1))
            return self._shape_standin("x_" + (m.group(2) or "block"), props, self.material_texture(f"tfc:wood/planks/{w}"))
        m = re.match(r"^(roofs|furniture|bridges|fences)/([a-z_]+?)_(?:roofs|furniture|bridges|fences)/", p)
        if m:
            w = self.wood_for(m.group(2))
            tex = self.material_texture(f"tfc:wood/planks/{w}")
            shape = {"roofs": "stairs", "furniture": "slab", "bridges": "fence" if "pier" in short else "slab", "fences": "fence"}[m.group(1)]
            return self._shape_standin("x_" + shape, props, tex)
        if "watercraft_frame" in p or "roofing" in p:
            return Eff("tfc:wood/planks/oak", {}, None, "standin")
        if "chimney" in p:
            return Eff("minecraft:bricks", {}, None, "standin")
        if "sand_stone_bricks" in p:
            return Eff("minecraft:cut_sandstone", {}, None, "standin")
        # anything else: its shape from the name, a flat colour from keywords
        flat = next((c for k, c in FLAT_KEYWORDS if k in p), None)
        if "charred" in p:
            flat = "2a2622"
        if "ash_pile" in p:
            flat = "9a9690"
        return self._shape_standin(short, props, "flat:" + (flat or self.M.name_colour(name)))

    def known(self, e):
        """True when the drawn id is a TFC 4 or vanilla block (its namespace is tfc or minecraft and a jar has its blockstate)."""
        return e.kind in ("direct", "alt") and e.name.split(":")[0] in ("minecraft", "tfc")

    # ------------------------------------------------------------------ rendering
    def render(self, tpl, views=("sw", "ne"), size=800, scale=None, jigsaw=False, tint="plains"):
        """Draw a Template. Returns (stats, {view: uint8 RGBA array}). `size` is the target long side in pixels unless `scale`
        (px per block, even) is given."""
        sx, sy, sz = tpl.size
        pal = tpl.palette
        grid = np.full((max(sx, 1), max(sy, 1), max(sz, 1)), -1, np.int32)
        ids = Counter()
        for (x, y, z), si in tpl.blocks:
            if not (0 <= x < sx and 0 <= y < sy and 0 <= z < sz) or si >= len(pal):
                continue
            raw = pal[si][0]
            if raw == "minecraft:jigsaw" and jigsaw:
                pass
            elif self.effective(raw, pal[si][1]).kind == "hide":
                continue
            grid[x, y, z] = si
            ids[raw] += 1
        stats = {"blocks": int(sum(ids.values())), "top_blocks": [[k, v] for k, v in ids.most_common(8)], "distinct_blocks": len(ids)}
        self._mark_connecting(pal)
        foreign = {}
        for n in ids:  # ids that are neither TFC 4 nor vanilla, and what they were drawn as
            e = self.effective(n, {}, None)
            if n == "minecraft:jigsaw" or self.known(e) and e.kind == "direct":
                continue
            how = {"alt": f"id mapped to {e.name}", "standin": f"stand-in {e.name}" + (f" with {e.override}" if e.override else ""),
                   "hide": "not drawn", "direct": "drawn from its own mod's assets"}[e.kind]
            if n.startswith("framedblocks:") and e.kind == "standin":
                how = f"stand-in {e.name}, textured from the camouflage block saved in each placed block"
            foreign[n] = how
        stats["foreign"] = sorted(foreign)
        stats["foreign_drawn_as"] = {k: foreign[k] for k in sorted(foreign)}
        untex, subst = Counter(), Counter()
        self._nomodel = Counter()
        images = {}
        for v in views:
            images[v] = self._draw(tpl, grid, pal, VIEWS[v], size, scale, tint, untex, subst)
        stats["untextured_ids"] = sorted(untex)
        stats["untextured"] = int(sum(untex.values()) // max(len(views), 1))
        stats["substituted"] = int(sum(subst.values()) // max(len(views), 1))
        stats["substituted_ids"] = sorted(subst)
        stats["no_model_ids"] = sorted(self._nomodel)
        stats["scale"] = images[views[0]][1] if images else None
        return stats, {v: im[0] for v, im in images.items()}

    def _mark_connecting(self, pal):
        """Fence-like palette entries whose saved connections are all off get connections from their neighbours when drawn."""
        self._conn = {}
        for i, (n, p) in enumerate(pal):
            short = n.split(":")[-1]
            if not all(k in p for k in ("north", "east", "south", "west")):
                continue
            if any(p[k] not in ("false", "none") for k in ("north", "east", "south", "west")):
                continue
            if "gate" in short:
                continue
            if short.endswith("_wall"):
                self._conn[i] = "wall"
            elif "fence" in short:
                self._conn[i] = "fence"
            elif "pane" in short or "bars" in short:
                self._conn[i] = "pane"

    def _state_at(self, grid, pal, i, x, y, z, sx, sz):
        kind = self._conn.get(i)
        n, p = pal[i]
        if not kind:
            return p
        p = dict(p)
        for k, (dx, dz) in {"north": (0, -1), "east": (1, 0), "south": (0, 1), "west": (-1, 0)}.items():
            xx, zz = x + dx, z + dz
            c = False
            if 0 <= xx < sx and 0 <= zz < sz and grid[xx, y, zz] >= 0:
                nn, np_ = pal[grid[xx, y, zz]]
                same = (nn.split(":")[-1].split("/")[0] == n.split(":")[-1].split("/")[0])
                e = self.effective(nn, np_)
                full = e.override is None and self.M.is_opaque_cube(e.name, e.props)
                if kind == "fence":
                    c = (same and "gate" not in nn) or "fence_gate" in nn or full
                elif kind == "wall":
                    c = same or "fence_gate" in nn or full
                else:
                    c = same or full or "glass" in nn
            if kind == "wall":
                p[k] = "low" if c else "none"
            else:
                p[k] = "true" if c else "false"
        if kind == "wall":
            p["up"] = "true"
        return p

    def _draw(self, tpl, grid, pal, k, size, scale, tint, untex_ids, subst_ids):
        sx, sy, sz = grid.shape
        yaw = (360 - 90 * k) % 360  # the models' rotation about y that goes with the view's quarter turns
        xs, ys, zs = np.nonzero(grid >= 0)
        if len(xs) == 0:
            return np.zeros((8, 8, 4), np.uint8), 0
        # canonical grid coordinates after the view rotation (same maps as the models' yaw)
        if k == 0:
            X, Z = xs, zs
        elif k == 1:
            X, Z = zs, (sx - 1 - xs)
        elif k == 2:
            X, Z = (sx - 1 - xs), (sz - 1 - zs)
        else:
            X, Z = (sz - 1 - zs), xs
        Y = ys
        nx = sz if k in (1, 3) else sx
        nz = sx if k in (1, 3) else sz
        ids = grid[xs, ys, zs]
        # occupancy grids in canonical coordinates: opaque cubes, water
        opq = np.zeros((nx + 1, sy + 1, nz + 1), bool)
        wat = np.zeros((nx + 1, sy + 1, nz + 1), bool)
        opm = np.zeros(len(pal), bool)
        wam = np.zeros(len(pal), bool)
        for i, (n, p) in enumerate(pal):
            e = self.effective(n, p)
            opm[i] = e.kind in ("direct", "alt") and self.M.is_opaque_cube(e.name, e.props)
            wam[i] = fluid_kind(e.name) == "water"
        opq[X, Y, Z] = opm[ids]
        wat[X, Y, Z] = wam[ids]
        # extents in units of a block (a = 1) of the anchors
        ax = (X - Z).astype(np.float64)
        ay = (X + Z) / 2 - Y
        ux0, ux1 = ax.min() - 1, ax.max() + 1
        uy0, uy1 = ay.min() - 1, ay.max() + 1.5
        long_units = max(ux1 - ux0, uy1 - uy0)
        if scale:
            a = int(scale)
        else:
            a = int(round(size / long_units / 2)) * 2
            a = max(2, min(a, 48))
        a -= a % 2
        a = max(a, 2)
        W = int(math.ceil((ux1 - ux0) * a)) + 2
        H = int(math.ceil((uy1 - uy0) * a)) + 2
        canvas = np.zeros((H, W, 4), np.float32)
        order = np.argsort(X + Y + Z, kind="stable")
        for oi in order:
            x, y, z = int(xs[oi]), int(ys[oi]), int(zs[oi])
            cx, cy, cz = int(X[oi]), int(Y[oi]), int(Z[oi])
            si = int(ids[oi])
            # hidden when the three camera-facing neighbours are opaque cubes (or, for water, water as well)
            w = wam[si]
            if (opq[cx + 1, cy, cz] or (w and wat[cx + 1, cy, cz])) and (opq[cx, cy + 1, cz] or (w and wat[cx, cy + 1, cz])) \
                    and (opq[cx, cy, cz + 1] or (w and wat[cx, cy, cz + 1])):
                continue
            raw = pal[si][0]
            p = self._state_at(grid, pal, si, x, y, z, sx, sz)
            e = self.effective(raw, p, tpl.camo.get((x, y, z)))
            sk = (e.name, tuple(sorted(e.props.items())), e.override, raw == "minecraft:jigsaw", yaw, a, tint)
            sp = self._sprites.get(sk)
            if sp is None:
                if raw == "minecraft:jigsaw":
                    quads, status = self._jigsaw_quads(yaw), "ok"
                else:
                    quads, status = self.M.bake(e.name, e.props, yaw, tint, e.override)
                sp = (self.S.make(quads, a), status)
                self._sprites[sk] = sp
            spr, status = sp
            if status == "empty":
                self._nomodel[raw] += 1
            if status in ("flat", "partial") or (e.kind == "standin" and (e.override or "").startswith("flat:")):
                untex_ids[raw] += 1
            elif e.kind == "standin":
                subst_ids[raw] += 1
            if spr is None:
                continue
            col, ox, oy = spr
            ah, aw = col.shape[:2]
            px = int(round((cx - cz) * a - ux0 * a)) + ox
            py = int(round(((cx + cz) * a / 2 - cy * a) - uy0 * a)) + oy
            x0, y0 = max(px, 0), max(py, 0)
            x1, y1 = min(px + aw, W), min(py + ah, H)
            if x1 <= x0 or y1 <= y0:
                continue
            s = col[y0 - py:y1 - py, x0 - px:x1 - px]
            reg = canvas[y0:y1, x0:x1]
            reg[:] = s + reg * (1 - s[:, :, 3:4])
        a_ = canvas[:, :, 3:4]
        rgb = np.where(a_ > 1e-6, canvas[:, :, :3] / np.maximum(a_, 1e-6), 0)
        out = np.dstack([np.clip(rgb * 255 + 0.5, 0, 255), np.clip(a_ * 255 + 0.5, 0, 255)]).astype(np.uint8)
        ys_, xs_ = np.nonzero(out[:, :, 3] > 0)
        if len(xs_):
            out = out[max(ys_.min() - 4, 0):ys_.max() + 5, max(xs_.min() - 4, 0):xs_.max() + 5]
        return out, a

    def _jigsaw_quads(self, yaw):
        m = {"elements": [{"from": [3, 3, 3], "to": [13, 13, 13], "faces": {d: {"texture": "#all"} for d in DIRS}}],
             "textures": {"all": "flat:d040d0"}}
        return self.M.bake_model(m, 0, 0, False, "minecraft:jigsaw", yaw, "plains")


# ======================================================================== CLI
def guess_tint(path):
    p = path.lower().replace("\\", "/")
    if any(w in p for w in ("desert", "savanna", "mesa", "badlands", "arabic", "sand")):
        return "desert"
    if any(w in p for w in ("snow", "ice", "christmas")):
        return "snowy"
    if any(w in p for w in ("taiga", "norse", "spruce")):
        return "taiga"
    return "plains"


def collect(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            for root, _, files in os.walk(p):
                out += [os.path.join(root, f) for f in sorted(files) if f.endswith(".nbt")]
        else:
            out += glob.glob(p) or [p]
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--out", default="render-out")
    ap.add_argument("--views", default="sw,ne", help="comma list of se, sw, nw, ne (the corner the camera looks from)")
    ap.add_argument("--size", type=int, default=800, help="target long side in px (picks an even px-per-block scale from 2 to 48)")
    ap.add_argument("--scale", type=int, help="fixed px per block (even); 16 is texel-exact")
    ap.add_argument("--colors", type=int, default=256, help="palette size of the PNG (0 = truecolour)")
    ap.add_argument("--jigsaw", action="store_true", help="draw jigsaw blocks as magenta markers")
    ap.add_argument("--tint", default="auto", choices=["auto"] + list(TINTS))
    ap.add_argument("--mc-jar", help="Minecraft 1.21.1 client jar (default: found under PrismLauncher or ~/.gradle)")
    ap.add_argument("--assets", nargs="*", default=[], help="extra jars searched after TFC and Minecraft")
    ap.add_argument("--stats", action="store_true", help="print one JSON line of statistics per template")
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    r = Renderer(jars=default_jars(args.mc_jar, args.assets))
    views = [v for v in args.views.split(",") if v]
    failed = 0
    for f in collect(args.paths):
        name = os.path.splitext(os.path.basename(f))[0]
        try:
            tpl = load_template(f, name)
            tint = guess_tint(f) if args.tint == "auto" else args.tint
            stats, imgs = r.render(tpl, views, args.size, args.scale, args.jigsaw, tint)
        except Exception as e:  # a bad file should not stop a folder run
            print(f"{name}: FAILED {type(e).__name__}: {e}", file=sys.stderr)
            failed += 1
            continue
        if stats["blocks"] == 0:
            print(f"{name}: no blocks (entities or structure voids only), skipped")
            continue
        written = []
        for v, im in imgs.items():
            out = os.path.join(args.out, f"{name}_{v}.png")
            with open(out, "wb") as fh:
                fh.write(png_encode(im, args.colors))
            written.append(out)
        stats.update({"template": f, "size": list(tpl.size), "images": written})
        if args.stats:
            print(json.dumps(stats))
        else:
            print(f"{name}: {stats['blocks']} blocks, {stats['substituted']} stand-ins, {stats['untextured']} untextured -> "
                  + ", ".join(f"{os.path.basename(w)} ({os.path.getsize(w) // 1024} KB)" for w in written))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
