"""Average block colors from the textures inside the game and mod jars.

Resolution per block id "ns:path":
  blockstates/path.json -> first variant/multipart model -> model parent chain
  -> texture (preferring all/top/end/side/...) -> alpha-weighted average color.
Falls back to textures/block/path.png, then to a stable hashed color.
Grayscale textures that the game tints at runtime (grass, leaves, water)
get a fixed tint so they don't all come out gray.
"""
import colorsys
import hashlib
import io
import json
import re
import struct
import zipfile
import zlib

import numpy as np

# "overlay" first: ore blocks are a rock texture plus an ore overlay, and the
# overlay is what makes them recognizable.
TEXTURE_KEYS = ("overlay", "all", "texture", "top", "end", "side", "cross", "plant", "particle")

TINTS = [
    (re.compile(r"water|fluid/(salt|spring|river)"), (0.25, 0.46, 0.89)),
    (re.compile(r"leaves|vine"), (0.36, 0.67, 0.19)),
    (re.compile(r"grass|fern|bush|lily_pad|moss"), (0.49, 0.74, 0.35)),
]


# --------------------------------------------------------------------------- PNG
def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return np.where((pa <= pb) & (pa <= pc), a, np.where(pb <= pc, b, c))


def decode_png(data):
    """Decode a PNG into an (h, w, 4) uint8 RGBA array. Non-interlaced only."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos, idat, plte, trns = 8, [], None, None
    while pos < len(data):
        (n,) = struct.unpack_from(">I", data, pos)
        kind = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + n]
        pos += 12 + n
        if kind == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
        elif kind == b"PLTE":
            plte = np.frombuffer(body, np.uint8).reshape(-1, 3)
        elif kind == b"tRNS":
            trns = np.frombuffer(body, np.uint8)
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            break
    if interlace:
        raise ValueError("interlaced PNG")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    bpp_bits = channels * depth
    stride = (w * bpp_bits + 7) // 8
    bpp = max(1, bpp_bits // 8)
    raw = np.frombuffer(zlib.decompress(b"".join(idat)), np.uint8)
    rows = np.zeros((h, stride), np.int32)
    prev = np.zeros(stride, np.int32)
    for y in range(h):
        f = raw[y * (stride + 1)]
        line = raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)].astype(np.int32)
        if f == 1:
            for x in range(bpp, stride):
                line[x] = (line[x] + line[x - bpp]) & 0xFF
        elif f == 2:
            line = (line + prev) & 0xFF
        elif f == 3:
            for x in range(stride):
                left = line[x - bpp] if x >= bpp else 0
                line[x] = (line[x] + ((left + prev[x]) >> 1)) & 0xFF
        elif f == 4:
            for x in range(stride):
                a = line[x - bpp] if x >= bpp else 0
                c = prev[x - bpp] if x >= bpp else 0
                line[x] = (line[x] + int(_paeth(a, prev[x], c))) & 0xFF
        rows[y] = line
        prev = line
    rows = rows.astype(np.uint8)
    if depth < 8:
        bits = np.unpackbits(rows, axis=1)
        vals = bits.reshape(h, -1, depth)
        weights = (1 << np.arange(depth - 1, -1, -1)).astype(np.uint8)
        samples = (vals * weights).sum(-1)[:, :w * channels].astype(np.uint8)
        if ctype == 0:
            samples = (samples.astype(np.uint16) * 255 // ((1 << depth) - 1)).astype(np.uint8)
    elif depth == 16:
        samples = rows.reshape(h, -1, 2)[:, :, 0]
    else:
        samples = rows
    px = samples.reshape(h, w, channels)
    if ctype == 3:
        idx = px[:, :, 0]
        rgb = plte[idx]
        alpha = np.full((h, w), 255, np.uint8)
        if trns is not None:
            t = np.full(256, 255, np.uint8)
            t[:len(trns)] = trns
            alpha = t[idx]
        return np.dstack([rgb, alpha])
    if ctype == 0:
        g = px[:, :, 0]
        return np.dstack([g, g, g, np.full_like(g, 255)])
    if ctype == 4:
        g = px[:, :, 0]
        return np.dstack([g, g, g, px[:, :, 1]])
    if ctype == 2:
        return np.dstack([px, np.full((h, w), 255, np.uint8)])
    return px


# ------------------------------------------------------------------- asset index
class Assets:
    """Index of assets/ files across a set of jars, including nested jar-in-jar."""

    def __init__(self, jar_paths):
        self.files = {}  # "assets/ns/..." -> (ZipFile, name)
        self._zips = []
        for p in jar_paths:
            try:
                self._add(zipfile.ZipFile(p))
            except (zipfile.BadZipFile, OSError):
                pass

    def _add(self, zf, depth=0):
        self._zips.append(zf)
        for name in zf.namelist():
            if name.startswith("assets/"):
                self.files.setdefault(name, (zf, name))
            elif depth < 2 and name.startswith("META-INF/jarjar/") and name.endswith(".jar"):
                try:
                    self._add(zipfile.ZipFile(io.BytesIO(zf.read(name))), depth + 1)
                except zipfile.BadZipFile:
                    pass

    def read(self, path):
        hit = self.files.get(path)
        return hit[0].read(hit[1]) if hit else None

    def json(self, path):
        data = self.read(path)
        if data is None:
            return None
        try:
            return json.loads(data.decode("utf-8", errors="replace"))
        except ValueError:
            return None


def _split(rid, default_ns="minecraft"):
    rid = rid.lstrip("#")
    return rid.split(":", 1) if ":" in rid else (default_ns, rid)


def _model_textures(assets, model_id, depth=0):
    if depth > 12:
        return {}
    ns, path = _split(model_id)
    model = assets.json(f"assets/{ns}/models/{path}.json")
    if not model:
        return {}
    return _inline_textures(assets, model, depth)


def _inline_textures(assets, model, depth):
    tex = {}
    if "parent" in model:
        tex.update(_model_textures(assets, model["parent"], depth + 1))
    tex.update(model.get("textures", {}))
    if not tex:
        # Custom loaders (TFC leaves/plants, NeoForge composite) wrap sub-models
        # in their own keys; use the first one that looks like a model.
        subs = list(model.get("children", {}).values()) if isinstance(model.get("children"), dict) else []
        subs += [v for v in model.values() if isinstance(v, dict)]
        for sub in subs:
            if "parent" in sub or "textures" in sub:
                tex = _inline_textures(assets, sub, depth + 1)
                if tex:
                    break
    return tex


def _first_model(state):
    if not state:
        return None
    if "variants" in state and state["variants"]:
        v = next(iter(state["variants"].values()))
        v = v[0] if isinstance(v, list) else v
        return v.get("model")
    for part in state.get("multipart", []):
        a = part.get("apply")
        a = a[0] if isinstance(a, list) else a
        if a and "model" in a:
            return a["model"]
    return None


def _resolve_ref(tex, key, depth=0):
    v = tex.get(key)
    while isinstance(v, str) and v.startswith("#") and depth < 10:
        v = tex.get(v[1:])
        depth += 1
    return v


def _texture_color(assets, tex_id):
    ns, path = _split(tex_id)
    data = assets.read(f"assets/{ns}/textures/{path}.png")
    if data is None:
        return None
    try:
        img = decode_png(data).astype(np.float64)
    except Exception:
        return None
    a = img[:, :, 3] / 255.0
    if a.sum() < 1:
        return None
    rgb = (img[:, :, :3] * a[:, :, None]).sum((0, 1)) / a.sum()
    return rgb / 255.0


def hashed_color(name):
    h = int(hashlib.md5(name.encode()).hexdigest()[:8], 16)
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360.0, 0.55, 0.75)
    return r, g, b


def block_color(assets, name):
    """Return ((r, g, b) floats 0-1, source) for a block id."""
    ns, path = _split(name)
    tex_id = None
    model = _first_model(assets.json(f"assets/{ns}/blockstates/{path}.json"))
    if model:
        tex = _model_textures(assets, model)
        for k in TEXTURE_KEYS:
            tex_id = _resolve_ref(tex, k)
            if isinstance(tex_id, str):
                break
        else:
            tex_id = next((_resolve_ref(tex, k) for k in tex if isinstance(_resolve_ref(tex, k), str)), None)
    rgb = _texture_color(assets, tex_id) if tex_id else None
    if rgb is None:
        rgb = _texture_color(assets, f"{ns}:block/{path}")
    if rgb is None:
        return hashed_color(name), "hashed"
    r, g, b = rgb
    _, l, s = colorsys.rgb_to_hls(r, g, b)
    if s < 0.15:
        for pattern, tint in TINTS:
            if pattern.search(path):
                return (min(1, r * tint[0] / max(l, 0.2)),
                        min(1, g * tint[1] / max(l, 0.2)),
                        min(1, b * tint[2] / max(l, 0.2))), "tinted"
    return (r, g, b), "texture"
