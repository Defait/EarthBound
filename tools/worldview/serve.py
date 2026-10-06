"""Local web viewer for Minecraft world saves: map, slices, Y distribution, heatmaps.

Usage (from the repo root):
    tools/.venv/Scripts/python tools/worldview/serve.py [WORLD] [--compare OTHER_WORLD] [--dim overworld|nether|end]

WORLD is a path to a world folder or the name of a world in the instance's
saves folder; it defaults to the most recently played world. The instance
defaults to $WORLDVIEW_INSTANCE or Prism's GregWorld instance. Saves are only
read, never written; run /save-all (or quit) first so the files are current.
"""
import argparse
import glob
import gzip
import json
import os
import re
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from worldview import colors, nbt  # noqa: E402
from worldview.geo import load_projection  # noqa: E402
from worldview.index import MISSING, World, cache_dir_for  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PRISM = os.path.join(os.environ.get("APPDATA", ""), "PrismLauncher")
DEFAULT_INSTANCE = os.environ.get("WORLDVIEW_INSTANCE") or os.path.join(PRISM, "instances", "GregWorld", "minecraft")
DIMS = {"overworld": "region", "nether": os.path.join("DIM-1", "region"), "end": os.path.join("DIM1", "region")}
MAX_SLICE_CELLS = 4096 * 4096

ORE_RE = re.compile(r"(^|[:/_])ores?($|[/_])")
ROCK_RE = re.compile(r"^tfc:rock/(raw|hardened)/|^minecraft:(stone|deepslate|tuff|granite|diorite|andesite|"
                     r"calcite|basalt|smooth_basalt|blackstone|netherrack|end_stone)$")
FLUID_RE = re.compile(r"water|lava|^tfc:fluid/")


def resolve_world(arg, instance):
    saves = os.path.join(instance, "saves")
    if arg and os.path.isdir(arg):
        return os.path.abspath(arg)
    if arg:
        p = os.path.join(saves, arg)
        if os.path.isdir(p):
            return p
        sys.exit(f"World '{arg}' not found (looked for a folder and in {saves})")
    worlds = [p for p in glob.glob(os.path.join(saves, "*")) if os.path.exists(os.path.join(p, "level.dat"))]
    if not worlds:
        sys.exit(f"No worlds found in {saves}; pass a world path")
    return max(worlds, key=lambda p: os.path.getmtime(os.path.join(p, "level.dat")))


def game_version(world):
    try:
        with gzip.open(os.path.join(world, "level.dat")) as f:
            return nbt.loads(f.read())["Data"]["Version"]["Name"]
    except Exception:
        return None


def build_colors(names, jars):
    assets = colors.Assets(jars)
    out = []
    for n in names:
        (r, g, b), src = colors.block_color(assets, n)
        out.append(("#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255)), src))
    return out


class Source:
    """One scanned world (A, or B when comparing)."""

    def __init__(self, world_dir, dim, jars, mod_dirs):
        self.world_dir = world_dir
        self.dim = dim
        self.jars = jars
        region_dir = os.path.join(world_dir, DIMS.get(dim, dim))
        if not os.path.isdir(region_dir):
            sys.exit(f"No region folder at {region_dir}")
        self.region_dir = region_dir
        self.cache_dir = cache_dir_for(world_dir, region_dir)
        self.world = World(region_dir, self.cache_dir)
        self.version = game_version(world_dir)
        self.projection = load_projection(world_dir, mod_dirs) if dim == "overworld" else None
        self.info = None

    def start_scan(self):
        def run():
            self.world.scan()
            if self.world.ready:
                w = self.world
                cols = build_colors(w.names, self.jars)
                has_climate = any(c.get("climate") for c in w.chunks.values())
                self.info = {
                    "world": os.path.basename(os.path.normpath(self.world_dir)), "path": self.world_dir,
                    "dim": self.dim, "version": self.version,
                    "ymin": w.ymin, "height": w.H, "cbox": w.cbox, "chunks": len(w.chunks),
                    "partial": w.partial, "scanSeconds": round(w.scan_seconds, 2),
                    "climate": has_climate, "geo": self.projection.params() if self.projection else None,
                    "blocks": [{
                        "id": i, "name": n, "color": cols[i][0], "src": cols[i][1], "total": int(w.totals[i]),
                        "air": n in ("minecraft:air", "minecraft:cave_air", "minecraft:void_air"),
                        "ore": bool(ORE_RE.search(n)), "rock": bool(ROCK_RE.search(n)), "fluid": bool(FLUID_RE.search(n)),
                    } for i, n in enumerate(w.names)],
                }
        threading.Thread(target=run, daemon=True).start()

    def rescan(self):
        """Re-read the save; unchanged regions come straight from the cache."""
        self.info = None
        self.world = World(self.region_dir, self.cache_dir)
        self.start_scan()


class App:
    def __init__(self, sources):
        self.sources = sources   # {"a": Source, "b": Source}

    def start_scan(self):
        for s in {id(s): s for s in self.sources.values()}.values():   # A and B may be the same world
            s.start_scan()

    def ready(self):
        return all(s.info is not None for s in self.sources.values())


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj).encode(), "application/json")

        def _binary(self, header, *arrays):
            h = json.dumps(header).encode()
            h += b" " * ((-(4 + len(h))) % 8)
            body = len(h).to_bytes(4, "little") + h + b"".join(np.ascontiguousarray(a).tobytes() for a in arrays)
            self._send(200, body, "application/octet-stream")

        def do_GET(self):
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                if url.path in ("/", "/index.html"):
                    with open(os.path.join(HERE, "viewer.html"), "rb") as f:
                        return self._send(200, f.read(), "text/html; charset=utf-8")
                if url.path == "/api/status":
                    uniq = {id(s): s for s in app.sources.values()}.values()
                    done = sum(s.world.progress[0] for s in uniq)
                    total = sum(s.world.progress[1] for s in uniq)
                    err = next((s.world.error for s in app.sources.values() if s.world.error), None)
                    return self._json({"ready": app.ready(), "progress": [done, total], "error": err,
                                       "worlds": sorted(app.sources)})
                if url.path == "/api/rescan":
                    for s in {id(s): s for s in app.sources.values()}.values():
                        s.rescan()
                    return self._json({"ok": True})
                if not app.ready():
                    return self._json({"error": "scan in progress"}, 503)
                src = app.sources.get(q.get("w", "a"))
                if src is None:
                    return self._json({"error": "no such world"}, 404)
                w = src.world
                if url.path == "/api/info":
                    return self._json(src.info)
                if url.path == "/api/surface":
                    step = max(1, int(q.get("step", 1)))
                    ids, ys = w.surface(step)
                    return self._binary({"w": ids.shape[1], "h": ids.shape[0], "x0": w.cbox[0] * 16,
                                         "z0": w.cbox[1] * 16, "step": step}, ids.astype("<u2"), ys.astype("<i2"))
                if url.path == "/api/slice":
                    axis, pos = q["axis"], int(q["pos"])
                    a0, a1 = int(q["a0"]), int(q["a1"])
                    if axis == "y":
                        b0, b1 = int(q["b0"]), int(q["b1"])
                        if (a1 - a0) * (b1 - b0) > MAX_SLICE_CELLS or a1 <= a0 or b1 <= b0:
                            return self._json({"error": "slice too large or empty"}, 400)
                        arr = w.slice_y(pos, a0, a1, b0, b1)
                    else:
                        if (a1 - a0) * w.H > MAX_SLICE_CELLS or a1 <= a0:
                            return self._json({"error": "slice too large or empty"}, 400)
                        arr = w.slice_vertical(axis, pos, a0, a1)
                    return self._binary({"w": arr.shape[1], "h": arr.shape[0], "axis": axis, "pos": pos,
                                         "a0": a0, "b0": int(q.get("b0", 0)), "ytop": w.ymin + w.H - 1},
                                        arr.astype("<u2"))
                if url.path == "/api/ydist":
                    # ids index this world's block list; names= lets the other world be queried by block name
                    if "names" in q:
                        ids = [w.name_ids[n] for n in q["names"].split(",") if n in w.name_ids]
                    else:
                        ids = [int(i) for i in q.get("ids", "").split(",") if i]
                    return self._json({"ymin": w.ymin, "chunks": len(w.chunks),
                                       "series": {w.names[i]: w.ycounts[i].tolist() for i in ids}})
                if url.path == "/api/hostrock":
                    names = q.get("names", "").split(",")
                    ids = [w.name_ids[n] for n in names if n in w.name_ids]
                    total, top = w.host_rock(ids) if ids else (0, [])
                    return self._json({"total": total, "top": [{"name": w.names[i], "count": c} for i, c in top]})
                if url.path == "/api/heatmap":
                    ids = [int(i) for i in q["ids"].split(",") if i]
                    ylo = int(q["ylo"]) if "ylo" in q else None
                    yhi = int(q["yhi"]) if "yhi" in q else None
                    hm = sum(w.heatmap(i, ylo, yhi) for i in ids)
                    hm[hm < 0] = -1  # missing chunks summed to -len(ids)
                    return self._json({"cx0": w.cbox[0], "cz0": w.cbox[1], "w": hm.shape[1], "h": hm.shape[0],
                                       "values": hm.ravel().tolist()})
                if url.path == "/api/climate":
                    grid = w.climate(q["field"])
                    vals = [None if v != v else round(float(v), 3) for v in grid.ravel()]
                    return self._json({"cx0": w.cbox[0], "cz0": w.cbox[1], "w": grid.shape[1], "h": grid.shape[0],
                                       "field": q["field"], "values": vals})
                if url.path == "/api/geo":
                    if not src.projection:
                        return self._json({"error": "not a TFC: Real World world"}, 404)
                    p = src.projection
                    if "x" in q:
                        lon, lat = p.to_geo(float(q["x"]), float(q["z"]))
                        return self._json({"lon": lon, "lat": lat})
                    lon, lat = float(q["lon"]), float(q["lat"])
                    x, z = p.to_block(lon, lat)
                    return self._json({"x": x, "z": z})
                if url.path == "/api/geogrid":
                    # Graticule polylines in block coordinates, clipped by the client.
                    if not src.projection:
                        return self._json({"lines": []})
                    p = src.projection
                    step = float(q.get("step", 10))
                    lines = []
                    lat = -90 + step
                    while lat < 90:
                        a = p.to_block(p.west + 1e-6, lat)
                        b = p.to_block(p.east - 1e-6, lat)
                        lines.append({"label": f"{abs(lat):g}°{'N' if lat > 0 else 'S' if lat < 0 else ''}", "kind": "lat",
                                      "pts": [a, b]})
                        lat += step
                    lon = p.west
                    while lon <= p.east + 1e-9:
                        pts = [p.to_block(lon, la) for la in [x / 2 for x in range(-180, 181)]]
                        norm = (lon + 180) % 360 - 180
                        lines.append({"label": f"{abs(norm):g}°{'E' if norm > 0 else 'W' if norm < 0 else ''}", "kind": "lon",
                                      "pts": pts})
                        lon += step
                    return self._json({"lines": lines})
                return self._json({"error": "not found"}, 404)
            except (KeyError, ValueError) as e:
                return self._json({"error": f"bad request: {e}"}, 400)
            except Exception as e:
                return self._json({"error": repr(e)}, 500)

    return Handler


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("world", nargs="?", help="world folder path or name in the instance's saves")
    ap.add_argument("--compare", help="a second world (path or save name) to compare against, shown as world B")
    ap.add_argument("--instance", default=DEFAULT_INSTANCE, help="instance .minecraft folder (for saves and mod jars)")
    ap.add_argument("--dim", default="overworld", help="overworld, nether, end, or a region folder relative to the world")
    ap.add_argument("--client-jar", help="vanilla client jar for textures (auto-detected from Prism's libraries)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    world = resolve_world(args.world, args.instance)
    version = game_version(world)
    client = args.client_jar or os.path.join(PRISM, "libraries", "com", "mojang", "minecraft", str(version),
                                             f"minecraft-{version}-client.jar")
    mod_dirs = [os.path.join(args.instance, "mods")]
    jars = ([client] if os.path.exists(client) else []) + sorted(glob.glob(os.path.join(mod_dirs[0], "*.jar")))
    if not os.path.exists(client):
        print(f"warning: vanilla client jar not found ({client}); vanilla blocks get fallback colors")

    sources = {"a": Source(world, args.dim, jars, mod_dirs)}
    if args.compare:
        other = resolve_world(args.compare, args.instance)
        same = os.path.normcase(os.path.abspath(other)) == os.path.normcase(os.path.abspath(world))
        sources["b"] = sources["a"] if same else Source(other, args.dim, jars, mod_dirs)
    app = App(sources)
    app.start_scan()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(app))
    url = f"http://127.0.0.1:{args.port}/"
    print(f"World A: {world} [{args.dim}, {version}]" + (f"\nWorld B: {sources['b'].world_dir}" if args.compare else "")
          + f"\nViewer: {url}  (Ctrl+C to stop)", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
