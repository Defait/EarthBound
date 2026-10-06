"""Scan a world's region files into per-region summaries, cached on disk.

Per region we keep, for fully generated chunks only:
  * the surface block and height of every column (for the map),
  * block counts per chunk per 16-block section (for heatmaps),
  * block counts per Y level (for distributions),
  * the packed block data itself (for slices), stored separately so it
    can be loaded lazily.
"""
import functools
import os
import pickle
import threading
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np

from . import region

CACHE_VERSION = 2
CLIMATE_FIELDS = ("temperature", "rainfall", "rainVariance", "baseGroundwater", "forestType")
AIR = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air"}
MISSING = 0xFFFF
# Generated regions within this many regions of each other form one map area (see World._find_areas).
AREA_GAP = 4


def cache_dir_for(world_dir, region_dir):
    """Where scans of one world's region folder are cached (shared by all tools)."""
    import hashlib
    import re
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", os.path.basename(os.path.normpath(world_dir)))
    key = hashlib.sha1(os.path.abspath(region_dir).encode()).hexdigest()[:10]
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", f"{slug}-{key}")


def _cache_paths(cache_dir, path):
    base = os.path.join(cache_dir, os.path.basename(path))
    return base + ".summary.pkl", base + ".sections.pkl"


def _region_key(path):
    st = os.stat(path)
    return f"{CACHE_VERSION}-{st.st_mtime_ns}-{st.st_size}"


def _climate(root):
    """TFC's per-chunk climate (average of the four corner values), if the chunk has it."""
    data = (root.get("neoforge:attachments") or {}).get("tfc:chunk_data")
    if not isinstance(data, dict):
        return None
    out = {}
    for k in CLIMATE_FIELDS:
        v = data.get(k)
        if isinstance(v, dict) and v:
            out[k] = float(sum(v.values()) / len(v))
        elif isinstance(v, (int, float)):
            out[k] = float(v)
    return out or None


def _cached(cache_dir, path):
    sum_path, sec_path = _cache_paths(cache_dir, path)
    if not (os.path.exists(sum_path) and os.path.exists(sec_path)):
        return False
    try:
        with open(sum_path, "rb") as f:
            return pickle.load(f).get("key") == _region_key(path)
    except Exception:
        return False


def scan_region(path, cache_dir):
    """Summarize one region file, reusing the cache when the file is unchanged."""
    sum_path, sec_path = _cache_paths(cache_dir, path)
    key = _region_key(path)
    if os.path.exists(sum_path) and os.path.exists(sec_path):
        try:
            with open(sum_path, "rb") as f:
                cached = pickle.load(f)
            if cached.get("key") == key:
                return sum_path
        except Exception:
            pass

    names, name_ids = [], {}
    is_air = []

    def local_id(n):
        i = name_ids.get(n)
        if i is None:
            i = name_ids[n] = len(names)
            names.append(n)
            is_air.append(n in AIR)
        return i

    raw = []  # (cx, cz, [(sy, lut, packed)], climate)
    partial = 0
    rx, rz = map(int, region.REGION_RE.match(os.path.basename(path)).groups())
    for lx, lz, root in region.iter_chunks(path):
        status, secs = region.chunk_sections(root)
        if status != "minecraft:full" or not secs:
            partial += 1
            continue
        packed = []
        for sy, pal, data in secs:
            lut = np.array([local_id(n) for n in pal], dtype=np.uint16)
            packed.append((sy, lut, data))
        raw.append((rx * 32 + lx, rz * 32 + lz, packed, _climate(root)))

    air_id = local_id("minecraft:air")
    secmin = min((s[0] for _, _, p, _ in raw for s in p), default=0)
    secmax = max((s[0] for _, _, p, _ in raw for s in p), default=-1)
    nsec = secmax - secmin + 1
    H = nsec * 16
    air_mask = np.array(is_air, dtype=bool)
    ycounts = np.zeros((len(names), H), dtype=np.int64)
    chunks, sections = [], {}
    yrow = np.arange(H)[:, None]

    for cx, cz, packed, climate in raw:
        arr = np.full((H, 16, 16), air_id, dtype=np.uint16)
        for sy, lut, data in packed:
            y0 = (sy - secmin) * 16
            if data is None:
                arr[y0:y0 + 16] = lut[0]
            else:
                arr[y0:y0 + 16] = lut[region.unpack_indices(data, len(lut))].reshape(16, 16, 16)
        sections[(cx, cz)] = packed

        solid = ~air_mask[arr]
        top_from_above = np.argmax(solid[::-1], axis=0)
        has = solid.any(axis=0)
        top = H - 1 - top_from_above
        surf_id = np.where(has, np.take_along_axis(arr, top[None], axis=0)[0], MISSING).astype(np.uint16)
        surf_y = np.where(has, top + secmin * 16, -32768).astype(np.int16)

        u, inv = np.unique(arr.reshape(H, 256), return_inverse=True)
        inv = inv.reshape(H, 256)
        per_y = np.bincount((inv + yrow * len(u)).ravel(), minlength=H * len(u)).reshape(H, len(u)).T
        ycounts[u] += per_y
        chunks.append({
            "cx": cx, "cz": cz,
            "surf_id": surf_id, "surf_y": surf_y,
            "ids": u.astype(np.uint16),
            "sec_counts": per_y.reshape(len(u), nsec, 16).sum(-1).astype(np.int32),
            "climate": climate,
        })

    summary = {
        "key": key, "rx": rx, "rz": rz, "names": names, "secmin": secmin, "nsec": nsec,
        "chunks": chunks, "ycounts": ycounts[:len(names)], "partial": partial,
    }
    os.makedirs(cache_dir, exist_ok=True)
    with open(sec_path, "wb") as f:
        pickle.dump(sections, f, protocol=pickle.HIGHEST_PROTOCOL)
    with open(sum_path, "wb") as f:
        pickle.dump(summary, f, protocol=pickle.HIGHEST_PROTOCOL)
    return sum_path


class World:
    """Merged, globally indexed view of all scanned regions."""

    def __init__(self, region_dir, cache_dir):
        self.region_dir = region_dir
        self.cache_dir = cache_dir
        self.progress = (0, 0)
        self.ready = False
        self.error = None
        self.scan_seconds = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ scan
    def scan(self, workers=None):
        try:
            t0 = time.time()
            paths = [p for _, _, p in region.list_regions(self.region_dir)]
            self.progress = (0, len(paths))
            sum_paths = []
            # Regions already in the cache load in-process; only stale ones go to worker processes.
            stale = [p for p in paths if not _cached(self.cache_dir, p)]
            for p in paths:
                if p not in stale:
                    sum_paths.append(scan_region(p, self.cache_dir))
            self.progress = (len(sum_paths), len(paths))
            if len(stale) <= 1:
                for p in stale:
                    sum_paths.append(scan_region(p, self.cache_dir))
                    self.progress = (len(sum_paths), len(paths))
            else:
                with ProcessPoolExecutor(max_workers=workers or min(len(stale), os.cpu_count() or 2)) as ex:
                    futs = [ex.submit(scan_region, p, self.cache_dir) for p in stale]
                    for fut in as_completed(futs):
                        sum_paths.append(fut.result())
                        self.progress = (len(sum_paths), len(paths))
            self._merge(sorted(sum_paths))
            self.scan_seconds = time.time() - t0
            self.ready = True
        except Exception as e:  # surfaced through /api/status
            import traceback
            self.error = "".join(traceback.format_exception(e))

    def _merge(self, sum_paths):
        self.names, self.name_ids = [], {}
        self.regions = {}
        summaries = []
        for sp in sum_paths:
            with open(sp, "rb") as f:
                s = pickle.load(f)
            s["sum_path"] = sp
            s["lut"] = np.array([self._gid(n) for n in s["names"]], dtype=np.uint16)
            summaries.append(s)
        self.air_id = self._gid("minecraft:air")
        populated = [s for s in summaries if s["chunks"]]
        self.secmin = min((s["secmin"] for s in populated), default=0)
        secmax = max((s["secmin"] + s["nsec"] - 1 for s in populated), default=-1)
        self.nsec = secmax - self.secmin + 1
        self.H = self.nsec * 16
        self.ymin = self.secmin * 16
        self.ycounts = np.zeros((len(self.names), self.H), dtype=np.int64)
        self.chunks = {}
        self.partial = 0
        for s in summaries:
            self.partial += s["partial"]
            self.regions[(s["rx"], s["rz"])] = s
            if not s["chunks"]:
                continue
            off = (s["secmin"] - self.secmin) * 16
            self.ycounts[s["lut"], off:off + s["ycounts"].shape[1]] += s["ycounts"]
            soff = s["secmin"] - self.secmin
            for c in s["chunks"]:
                c["gids"] = s["lut"][c["ids"]]
                c["soff"] = soff
                c["region"] = (s["rx"], s["rz"])
                self.chunks[(c["cx"], c["cz"])] = c
        self.totals = self.ycounts.sum(axis=1)
        self.areas = self._find_areas()
        self.select_area(0)

    # ------------------------------------------------------------------ areas
    def _find_areas(self, gap=AREA_GAP):
        """Groups of generated regions near each other (within `gap` regions), largest first.

        A world explored in one place is one area; teleporting across a big map (e.g. /startat on
        TFC: Real World) leaves islands of terrain hundreds of thousands of blocks apart, and one
        image spanning all of them wouldn't fit in memory, so the map shows one area at a time.
        """
        regions = sorted({c["region"] for c in self.chunks.values()})
        parent = {r: r for r in regions}

        def find(r):
            while parent[r] != r:
                parent[r] = parent[parent[r]]
                r = parent[r]
            return r

        for i, a in enumerate(regions):
            for b in regions[i + 1:]:
                if b[0] - a[0] > gap:
                    break
                if abs(b[1] - a[1]) <= gap:
                    parent[find(a)] = find(b)
        groups = {}
        for (cx, cz) in self.chunks:
            root = find((cx >> 5, cz >> 5))
            g = groups.setdefault(root, [cx, cz, cx, cz, 0])
            g[0], g[1], g[2], g[3] = min(g[0], cx), min(g[1], cz), max(g[2], cx), max(g[3], cz)
            g[4] += 1
        areas = [{"cbox": tuple(g[:4]), "chunks": g[4]} for g in groups.values()]
        return sorted(areas, key=lambda a: -a["chunks"])

    def select_area(self, i):
        """Make area i the one the map, climate and heatmaps cover."""
        if not self.areas:
            self.area, self.cbox = 0, (0, 0, -1, -1)
            return
        self.area = max(0, min(int(i), len(self.areas) - 1))
        self.cbox = self.areas[self.area]["cbox"]

    def area_at(self, x, z):
        """Index of the area containing block x, z (or the nearest one)."""
        cx, cz = int(x) >> 4, int(z) >> 4

        def dist(a):
            x0, z0, x1, z1 = a["cbox"]
            return max(x0 - cx, cx - x1, 0) + max(z0 - cz, cz - z1, 0)
        return min(range(len(self.areas)), key=lambda i: dist(self.areas[i])) if self.areas else 0

    def _in_box(self, cx, cz):
        x0, z0, x1, z1 = self.cbox
        return x0 <= cx <= x1 and z0 <= cz <= z1

    def _gid(self, n):
        i = self.name_ids.get(n)
        if i is None:
            i = self.name_ids[n] = len(self.names)
            self.names.append(n)
        return i

    # -------------------------------------------------------------- queries
    @functools.lru_cache(maxsize=16)
    def _sections(self, rkey):
        s = self.regions[rkey]
        _, sec_path = _cache_paths(self.cache_dir, os.path.join(self.region_dir, f"r.{rkey[0]}.{rkey[1]}.mca"))
        with open(sec_path, "rb") as f:
            return pickle.load(f)

    def _chunk_sections(self, cx, cz):
        c = self.chunks.get((cx, cz))
        if c is None:
            return None, None
        with self._lock:
            secs = self._sections(c["region"])
        return secs.get((cx, cz)), self.regions[c["region"]]["lut"]

    def chunk_blocks(self, cx, cz):
        """(H, 16, 16) global ids in (y, z, x) order, or None if not generated."""
        packed, lut = self._chunk_sections(cx, cz)
        if packed is None:
            return None
        arr = np.full((self.H, 16, 16), self.air_id, dtype=np.uint16)
        for sy, sec_lut, data in packed:
            y0 = (sy - self.secmin) * 16
            g = lut[sec_lut]
            if data is None:
                arr[y0:y0 + 16] = g[0]
            else:
                arr[y0:y0 + 16] = g[region.unpack_indices(data, len(sec_lut))].reshape(16, 16, 16)
        return arr

    def slice_y(self, y, x0, x1, z0, z1):
        out = np.full((z1 - z0, x1 - x0), MISSING, dtype=np.uint16)
        sy, ly = y >> 4, y & 15
        for cz in range(z0 >> 4, ((z1 - 1) >> 4) + 1):
            for cx in range(x0 >> 4, ((x1 - 1) >> 4) + 1):
                packed, lut = self._chunk_sections(cx, cz)
                if packed is None:
                    continue
                layer = np.full((16, 16), self.air_id, dtype=np.uint16)
                for s, sec_lut, data in packed:
                    if s == sy:
                        g = lut[sec_lut]
                        layer = (np.full((16, 16), g[0], np.uint16) if data is None else
                                 g[region.unpack_indices(data, len(sec_lut))].reshape(16, 16, 16)[ly])
                        break
                self._paste(out, layer, cx * 16 - x0, cz * 16 - z0)
        return out

    def slice_vertical(self, axis, pos, a0, a1):
        """Vertical cut at x=pos (axis 'x', spanning z) or z=pos (axis 'z', spanning x).

        Returns (H, a1 - a0) with row 0 at the top of the world.
        """
        out = np.full((self.H, a1 - a0), MISSING, dtype=np.uint16)
        for c in range(a0 >> 4, ((a1 - 1) >> 4) + 1):
            cx, cz = (pos >> 4, c) if axis == "x" else (c, pos >> 4)
            arr = self.chunk_blocks(cx, cz)
            if arr is None:
                continue
            strip = arr[:, :, pos & 15] if axis == "x" else arr[:, pos & 15, :]
            self._paste(out, strip[::-1], c * 16 - a0, 0)
        return out

    @staticmethod
    def _paste(out, tile, col, row):
        h, w = tile.shape
        r0, c0 = max(row, 0), max(col, 0)
        r1, c1 = min(row + h, out.shape[0]), min(col + w, out.shape[1])
        if r0 < r1 and c0 < c1:
            out[r0:r1, c0:c1] = tile[r0 - row:r1 - row, c0 - col:c1 - col]

    def surface(self, step=1):
        cx0, cz0, cx1, cz1 = self.cbox
        W, Hh = (cx1 - cx0 + 1) * 16, (cz1 - cz0 + 1) * 16
        ids = np.full((Hh, W), MISSING, dtype=np.uint16)
        ys = np.full((Hh, W), -32768, dtype=np.int16)
        luts = {k: np.append(s["lut"], np.uint16(MISSING)) for k, s in self.regions.items()}
        for (cx, cz), c in self.chunks.items():
            if not self._in_box(cx, cz):
                continue
            r, q = (cz - cz0) * 16, (cx - cx0) * 16
            lut = luts[c["region"]]
            sid = np.where(c["surf_id"] == MISSING, len(lut) - 1, c["surf_id"])
            ids[r:r + 16, q:q + 16] = lut[sid]
            ys[r:r + 16, q:q + 16] = c["surf_y"]
        return ids[::step, ::step], ys[::step, ::step]

    def climate(self, field):
        """Per-chunk climate value over the chunk bounding box (NaN where missing)."""
        cx0, cz0, cx1, cz1 = self.cbox
        out = np.full((cz1 - cz0 + 1, cx1 - cx0 + 1), np.nan, dtype=np.float32)
        for (cx, cz), c in self.chunks.items():
            if not self._in_box(cx, cz):
                continue
            v = (c.get("climate") or {}).get(field)
            if v is not None:
                out[cz - cz0, cx - cx0] = v
        return out

    def host_rock(self, gids, limit=12):
        """What the given blocks touch: counts of neighbouring block ids over all their faces."""
        gids = np.array(sorted(set(gids)), dtype=np.uint16)
        counts = np.zeros(len(self.names), dtype=np.int64)
        for (cx, cz), c in self.chunks.items():
            if not np.isin(c["gids"], gids).any():
                continue
            arr = self.chunk_blocks(cx, cz)
            m = np.isin(arr, gids)
            for axis in range(3):
                for a_sl, b_sl in ((slice(1, None), slice(None, -1)), (slice(None, -1), slice(1, None))):
                    src = [slice(None)] * 3
                    nb = [slice(None)] * 3
                    src[axis], nb[axis] = a_sl, b_sl
                    counts += np.bincount(arr[tuple(nb)][m[tuple(src)]], minlength=len(self.names))
        counts[gids] = 0
        total = int(counts.sum())
        top = np.argsort(counts)[::-1][:limit]
        return total, [(int(i), int(counts[i])) for i in top if counts[i] > 0]

    def heatmap(self, gid, ylo=None, yhi=None):
        cx0, cz0, cx1, cz1 = self.cbox
        out = np.full((cz1 - cz0 + 1, cx1 - cx0 + 1), -1, dtype=np.int64)
        slo = 0 if ylo is None else max(0, (ylo >> 4) - self.secmin)
        shi = self.nsec - 1 if yhi is None else min(self.nsec - 1, (yhi >> 4) - self.secmin)
        for (cx, cz), c in self.chunks.items():
            if not self._in_box(cx, cz):
                continue
            hit = np.nonzero(c["gids"] == gid)[0]
            v = 0
            if len(hit):
                row = c["sec_counts"][hit[0]]
                a, b = slo - c["soff"], shi - c["soff"]
                v = int(row[max(a, 0):max(b + 1, 0)].sum())
            out[cz - cz0, cx - cx0] = v
        return out
