"""Display names and icons for items and fluids, read from the game and mod jars."""
import os
import struct
import zlib

import numpy as np

from worldview.colors import Assets, _model_textures, _resolve_ref, _split, decode_png

ICON_KEYS = ("layer0", "all", "top", "front", "side", "texture", "cross", "particle", "end")


def encode_png(rgba):
    h, w, _ = rgba.shape
    raw = b"".join(b"\x00" + rgba[y].tobytes() for y in range(h))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


class GameAssets:
    def __init__(self, jars):
        self.assets = Assets(jars)
        self.lang = {}
        for path in sorted(p for p in self.assets.files if p.endswith("/lang/en_us.json")):
            data = self.assets.json(path)
            if isinstance(data, dict):
                self.lang.update({k: v for k, v in data.items() if isinstance(v, str)})
        self._icons = {}

    def name(self, node):
        kind, rid = node.split(":", 1)
        ns, path = _split(rid)
        dotted = path.replace("/", ".")
        keys = ([f"item.{ns}.{dotted}", f"block.{ns}.{dotted}"] if kind == "i" else
                [f"fluid_type.{ns}.{dotted}", f"fluid.{ns}.{dotted}", f"block.{ns}.{dotted}", f"item.{ns}.{dotted}_bucket"])
        for k in keys:
            if k in self.lang:
                return self.lang[k].replace(" Bucket", "") if k.endswith("_bucket") else self.lang[k]
        return path.split("/")[-1].replace("_", " ").title()

    def _texture_for(self, node):
        kind, rid = node.split(":", 1)
        ns, path = _split(rid)
        candidates = []
        if kind == "i":
            candidates += [f"{ns}:item/{path}", f"{ns}:block/{path}"]
        else:
            candidates += [f"{ns}:block/{path}", f"{ns}:item/{path}_bucket"]
        for model in candidates:
            tex = _model_textures(self.assets, model)
            for k in ICON_KEYS:
                t = _resolve_ref(tex, k)
                if isinstance(t, str):
                    return t
        for guess in ([f"{ns}:item/{path}", f"{ns}:block/{path}"] if kind == "i" else [f"{ns}:block/{path}_still", f"{ns}:block/fluid/{path}_still"]):
            gns, gpath = _split(guess)
            if f"assets/{gns}/textures/{gpath}.png" in self.assets.files:
                return guess
        return None

    def icon(self, node):
        """PNG bytes (first animation frame) or None."""
        if node in self._icons:
            return self._icons[node]
        png = None
        tex = self._texture_for(node)
        if tex:
            ns, path = _split(tex)
            data = self.assets.read(f"assets/{ns}/textures/{path}.png")
            if data:
                try:
                    img = decode_png(data)
                    w = img.shape[1]
                    png = encode_png(np.ascontiguousarray(img[:w, :w, :4]))
                except Exception:
                    png = None
        self._icons[node] = png
        return png
