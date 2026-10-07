"""How far is igneous extrusive rock from a start? Samples TFC's rock map without generating chunks.

Usage (from the repo root):
    tools/.venv/Scripts/python tools/rocksample.py [--places [NAME ...]] [--random N] [--rng-seed 1]
                                                   [--validate WORLD ...] [--seed pregen] [--keep-world] [--no-sync]

Create's andesite alloy needs TFC igneous extrusive rock (andesite, basalt, dacite, rhyolite), and a start can
be far from it. Chunky takes minutes per 2 km square, so this asks the running server instead: a dev-only
KubeJS script (tools/rocksample.js, copied in for this run only) calls TFC's ChunkDataGenerator, the same
code chunk generation uses for rock, on a fresh headless world at the pack's 20 m per block scale. No chunk
is generated; the first query in each ~12,000 block region builds that region's map data.

For each place (lat,lon) it reports the rock at the start (surface and below), the estimated rock category,
and the distance in blocks to the nearest column whose surface (layer 0) rock is extrusive, searched outward in
square rings of --step blocks up to --cap. A second search also counts rock reachable by digging down to the
deepest --depths value. Each is reported as the nearest hit anywhere (marked land or sea: a seabed hit needs
diving or dredging) and the nearest hit on dry land (surface height above sea level). ">cap" means none found.

  --places [NAME|NAME=LAT,LON|NAME@X,Z ...]  named places (default: the built-in list of 43 cities; with names, only those;
                 NAME@X,Z gives block coordinates instead of lat/lon)
  --random N     N random land points worldwide, uniform by area (the Equal Earth map is equal-area), drawn with a
                 fixed RNG seed, rejected unless on continent-map land and dry; prints the share of them with
                 extrusive rock within 500 / 1000 / 2000 / 5000 / 10000 / 25000 blocks
  --rocks A,B,...  the target rocks (TFC rock names) for the searches, default andesite,basalt,dacite,rhyolite; e.g. add
                 diorite to see how much closer andesite's intrusive twin is. The tables then say which rocks.
  --validate WORLD ...  finished worlds (name under tools/.server, or a path) made with the same --seed at the
                 same scale, e.g. world-rock-rome world-rock-kansas: reads the first raw rock below the surface
                 at ~50 chunk centers each and checks the sampler gives the same rock at the same block

The sampler reads the rock layers only. TFC also places granite, diorite and gabbro dikes (tfc:pipe_vein, radius 18,
rarity 300 per chunk each) that replace whatever raw rock they cross, so in a checked world ~2% of columns hold a
dike instead of the sampled rock; a dike only ever takes extrusive rock away, never adds it.

Each run uses a fresh world (tools/.server/world-rocksample), the same server as pregen.py and the other
tools, so don't run it while another one is using the test server. Results: a table on stdout and
tools/.data/reports/rocksample-<timestamp>.json.
"""
import argparse
import json
import os
import random
import re
import shutil
import sys
import time

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
from mclib.paths import DATA_DIR, utf8_console  # noqa: E402
from mclib.server import TestServer  # noqa: E402

WORLD = "world-rocksample"
# The pack's 20 m per block map radius (kubejs/startup_scripts/world_scale.js); the script refuses any other.
H, V = 862198, 419647
THRESHOLDS = [500, 1000, 2000, 5000, 10000, 25000]
TAG_RE = re.compile(r"\[rocksample\] ([IRP]) (\{.*\})\s*$")

DEFAULT_PLACES = [
    ("Rome", 41.89, 12.51), ("Kansas", 38.5, -98.0), ("Moscow", 55.75, 37.62), ("Stockholm", 59.33, 18.07),
    ("Tokyo", 35.68, 139.69), ("London", 51.51, -0.13), ("Paris", 48.86, 2.35), ("Berlin", 52.52, 13.40),
    ("Cairo", 30.04, 31.24), ("Lagos", 6.52, 3.38), ("Nairobi", -1.29, 36.82), ("Cape Town", -33.92, 18.42),
    ("Mumbai", 19.08, 72.88), ("Delhi", 28.61, 77.21), ("Beijing", 39.90, 116.40), ("Shanghai", 31.23, 121.47),
    ("Sydney", -33.87, 151.21), ("Alice Springs", -23.70, 133.88), ("Auckland", -36.85, 174.76),
    ("New York", 40.71, -74.01), ("Chicago", 41.88, -87.63), ("Denver", 39.74, -104.99),
    ("Los Angeles", 34.05, -118.24), ("Mexico City", 19.43, -99.13), ("Toronto", 43.65, -79.38),
    ("Winnipeg", 49.90, -97.14), ("Lima", -12.05, -77.04), ("Sao Paulo", -23.55, -46.63),
    ("Buenos Aires", -34.60, -58.38), ("Manaus", -3.12, -60.02), ("Reykjavik", 64.15, -21.94),
    ("Anchorage", 61.22, -149.90), ("Riyadh", 24.71, 46.68), ("Tehran", 35.69, 51.39), ("Kathmandu", 27.72, 85.32),
    ("Lhasa", 29.65, 91.17), ("Zurich", 47.37, 8.54), ("Innsbruck", 47.27, 11.39), ("La Paz", -16.50, -68.15),
    ("Ulaanbaatar", 47.89, 106.91), ("Yakutsk", 62.03, 129.73), ("Astana", 51.17, 71.45), ("Kisangani", 0.52, 25.19),
]


def parse_places(tokens):
    """[] / None -> the whole default list; otherwise default names (case-insensitive), NAME=LAT,LON or NAME@X,Z (blocks).

    Returns (name, lat, lon, x, z); x and z are None unless the place was given in blocks.
    """
    if not tokens:
        return [(n, la, lo, None, None) for n, la, lo in DEFAULT_PLACES]
    by_name = {n.lower(): (n, la, lo) for n, la, lo in DEFAULT_PLACES}
    out = []
    for t in tokens:
        if "@" in t:
            name, xz = t.split("@", 1)
            x, z = (int(v) for v in xz.split(","))
            out.append((name, None, None, x, z))
        elif "=" in t:
            name, ll = t.split("=", 1)
            la, lo = (float(v) for v in ll.split(","))
            out.append((name, la, lo, None, None))
        elif t.lower() in by_name:
            out.append((*by_name[t.lower()], None, None))
        else:
            raise SystemExit(f"Unknown place '{t}': use a default name, NAME=LAT,LON or NAME@X,Z")
    return out


# ------------------------------------------------------------------ checking against generated worlds
def world_probes(world, n, rng, skip=None):
    """First raw rock below the surface at ~n chunk centers of a finished world: [(x, z, y, tag, rock)].

    skip: (x, z, radius) in blocks; chunk centers within it are left out (the spawn area near Rome that every
    test world also has, for worlds that are about somewhere else).
    """
    import zlib

    from worldview import nbt
    from worldview import region as R

    wdir = world if os.path.isabs(world) or os.path.exists(world) else os.path.join(TOOLS, ".server", world)
    rdir = os.path.join(wdir, "region")
    if not os.path.isdir(rdir):
        raise SystemExit(f"No region folder in {wdir}")
    name = os.path.basename(os.path.normpath(wdir))
    entries = []
    for rx, rz, path in R.list_regions(rdir):
        with open(path, "rb") as f:
            head = f.read(4096)
        for i in range(1024):
            if int.from_bytes(head[i * 4:i * 4 + 3], "big"):
                entries.append((rx, rz, i, path))
    rng.shuffle(entries)

    def read_chunk(path, i):
        with open(path, "rb") as f:
            f.seek(int.from_bytes(f.read(4096)[i * 4:i * 4 + 3], "big") * 4096)
            length = int.from_bytes(f.read(4), "big")
            ctype = f.read(1)[0]
            payload = f.read(length - 1)
        if ctype & 0x80:
            return None
        return nbt.loads(zlib.decompress(payload) if ctype == 2 else payload)

    out = []
    for rx, rz, i, path in entries:
        if len(out) >= n:
            break
        root = read_chunk(path, i)
        if root is None:
            continue
        status, sections = R.chunk_sections(root)
        if status != "minecraft:full":
            continue
        hit = None
        for sy, names, data in sorted(sections, key=lambda s: -s[0]):
            if not any(nm.startswith("tfc:rock/raw/") for nm in names):
                continue
            idx = R.unpack_indices(data, len(names)).reshape(16, 16, 16) if data is not None else None
            for y in range(15, -1, -1):
                nm = names[0] if idx is None else names[idx[y, 8, 8]]   # (y, z, x) at the chunk's middle column
                if nm.startswith("tfc:rock/raw/"):
                    hit = (sy * 16 + y, nm.rsplit("/", 1)[1])
                    break
            if hit:
                break
        # tfc:tuff comes from tuff-ring and badlands surface builders, not from the rock layers the sampler reads.
        if not hit or hit[1] == "tuff":
            continue
        cx = rx * 32 + i % 32
        cz = rz * 32 + i // 32
        if skip and abs(cx * 16 + 8 - skip[0]) <= skip[2] and abs(cz * 16 + 8 - skip[1]) <= skip[2]:
            continue
        out.append((cx * 16 + 8, cz * 16 + 8, hit[0], f"{name}:{cx},{cz}", hit[1]))
    return out


# ------------------------------------------------------------------ the run
def write_job_script(job):
    with open(os.path.join(TOOLS, "rocksample.js"), encoding="utf-8") as f:
        src = f.read()
    m = re.search(r"/\*JOB\*/.*?/\*END\*/", src, re.S)
    if not m:
        raise SystemExit("tools/rocksample.js lost its /*JOB*/ ... /*END*/ placeholder")
    out = src[:m.start()] + "/*JOB*/ " + json.dumps(job, separators=(",", ":")) + " /*END*/" + src[m.end():]
    dest = os.path.join(DATA_DIR, "rocksample", "rocksample.js")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(out)
    return dest


def wait_lines(srv, pattern, timeout, start=0, echo=None):
    """Poll srv.lines from index start for a match. Returns (match, next_index); match is None on timeout/exit."""
    rx = re.compile(pattern)
    end = time.time() + timeout
    i = start
    while time.time() < end:
        while i < len(srv.lines):
            line = srv.lines[i]
            i += 1
            if echo and echo.search(line):
                print("  " + line[line.index("[rocksample]"):] if "[rocksample]" in line else "  " + line)
            m = rx.search(line)
            if m:
                return m, i
        if srv.proc.poll() is not None:
            return None, i
        time.sleep(0.5)
    return None, i


def run_server(script, args):
    srv = TestServer()
    srv.ensure_installed()
    if not args.no_sync:
        srv.sync_pack()
    srv.set_extra_mods([])
    srv.set_dev_scripts({"rocksample.js": script})
    shutil.rmtree(srv.path(WORLD), ignore_errors=True)
    srv.write_properties(WORLD, args.seed)
    print(f"Starting server for a fresh {WORLD} (seed '{args.seed}')...")
    srv.start(args.xmx)
    echo = re.compile(r"\[rocksample\] (progress|I |FATAL|zone|only|searched)")
    try:
        started, pos = wait_lines(srv, r"\[rocksample\] start", 1200, 0, echo)
        if not started:
            tail = "\n".join(srv.lines[-30:])
            raise SystemExit("The sampler script never started (server crashed, or the script didn't load):\n" + tail)
        done, pos = wait_lines(srv, r"\[rocksample\] done", args.timeout, pos, echo)
        if not done:
            print("Timed out or the server stopped before the sampler finished; using what it printed so far.")
    finally:
        srv.set_dev_scripts({})
        srv.stop()
    lines = list(srv.lines)
    scale = None
    toml = srv.path(WORLD, "serverconfig", "tfc_real_world", "server.toml")
    if os.path.exists(toml):
        with open(toml, encoding="utf-8") as f:
            scale = dict(re.findall(r"(horizontal_scale|vertical_scale) = (\d+)", f.read()))
    if not args.keep_world:
        shutil.rmtree(srv.path(WORLD), ignore_errors=True)
    return lines, scale


def ints(v):
    """KubeJS prints whole numbers as 10527.0; turn them back into ints."""
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, list):
        return [ints(x) for x in v]
    if isinstance(v, dict):
        return {k: ints(x) for k, x in v.items()}
    return v


def parse_output(lines):
    info, recs, probes, fatal = [], [], [], []
    for line in lines:
        if "[rocksample] FATAL" in line:
            fatal.append(line[line.index("[rocksample] FATAL"):])
        m = TAG_RE.search(line)
        if not m:
            continue
        obj = ints(json.loads(m.group(2)))
        {"I": info, "R": recs, "P": probes}[m.group(1)].append(obj)
    return info, recs, probes, fatal


# ------------------------------------------------------------------ reporting
def hit_text(hit, rec, cap, dig=False):
    if hit is None:
        if rec.get("timedOut"):
            return "timeout"
        return f">{cap:,}"
    mark = {True: "land", False: "sea", None: "?"}[hit.get("land")]
    deep = f" @-{hit['depth']}" if dig and hit.get("depth") else ""
    return f"{hit['d']:,} {mark}{deep}"


def land_text(rec_part, rec, cap, dig=False):
    if rec_part["land"] is None and rec.get("landCut") and rec_part["any"] is not None:
        return "? (height budget)"
    return hit_text(rec_part["land"], rec, cap, dig)


def print_table(rows, cap, rocks=None):
    head = ["place", "block x,z", "zone~", "rock", "surface: nearest", "surface: nearest land", "dig: nearest", "dig: nearest land"]
    body = []
    for r in rows:
        where = f"{r['x']},{r['z']}" + (f" (+{r['moved']})" if r.get("moved") else "") + ("" if r["dry"] else " SEA")
        body.append([r.get("name", f"#{r.get('index', '')}"), where, r.get("zone") or "?", r["rock"],
                     hit_text(r["surface"]["any"], r, cap), land_text(r["surface"], r, cap),
                     hit_text(r["dig"]["any"], r, cap, True), land_text(r["dig"], r, cap, True)])
    widths = [max(len(head[c]), *(len(b[c]) for b in body)) for c in range(len(head))]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*head))
    print(fmt.format(*("-" * w for w in widths)))
    for b in body:
        print(fmt.format(*b))
    print("Distances in blocks (20 m each). 'land'/'sea': the hit column's terrain is above/below sea level (a sea hit needs diving or dredging).")
    if rocks:
        print(f"Target rocks: {', '.join(rocks)}.")
    print("'@-N': extrusive only N blocks below the surface. zone~ is an estimate of TFC's rock category from the map data.")


def distribution(rows, key, which):
    """Share of rows whose nearest hit (key: surface/dig, which: any/land) is within each threshold."""
    n = len(rows)
    out = {}
    for t in THRESHOLDS:
        c = sum(1 for r in rows if r[key][which] is not None and r[key][which]["d"] <= t)
        out[t] = c / n if n else 0.0
    return out


def print_distribution(rows, cap, rocks=None):
    what = f"{'/'.join(rocks)} rock" if rocks else "extrusive rock"
    print(f"\n{len(rows)} random land points (uniform by area, dry, fixed RNG seed): share with {what} within N blocks")
    head = ["", *[f"{t:,}" for t in THRESHOLDS], f">{cap:,}/unresolved"]
    lines = []
    for label, key, which in (("surface, anywhere", "surface", "any"), ("surface, on land", "surface", "land"),
                              ("dig <=depth, anywhere", "dig", "any"), ("dig <=depth, on land", "dig", "land")):
        d = distribution(rows, key, which)
        miss = sum(1 for r in rows if r[key][which] is None)
        lines.append([label, *[f"{100 * d[t]:.0f}%" for t in THRESHOLDS], f"{miss}"])
    widths = [max(len(head[c]), *(len(b[c]) for b in lines)) for c in range(len(head))]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*head))
    for b in lines:
        print(fmt.format(*b))
    zones = {}
    for r in rows:
        zones[r.get("zone") or "?"] = zones.get(r.get("zone") or "?", 0) + 1
    print("zones (estimate): " + ", ".join(f"{k} {v}" for k, v in sorted(zones.items())))
    cut = sum(1 for r in rows if r.get("landCut"))
    timed = sum(1 for r in rows if r.get("timedOut"))
    if cut or timed:
        print(f"{cut} points hit the height-call budget (their 'on land' answer may be missing), {timed} timed out.")


EXTRUSIVE = {"andesite", "basalt", "dacite", "rhyolite"}
ROCK_LAYER_ROCKS = {"andesite", "basalt", "dacite", "rhyolite", "diorite", "gabbro", "granite", "gneiss", "schist", "phyllite", "slate",
                    "marble", "quartzite", "chalk", "chert", "claystone", "conglomerate", "dolomite", "limestone", "shale"}


def check_probes(probes, expected, targets=EXTRUSIVE):
    """expected: {tag: (x, z, y, rock)}. Returns per-world match counts, mismatches, and extrusive agreement."""
    out = {}
    for p in probes:
        world = p["tag"].split(":")[0]
        x, z, y, rock = expected[p["tag"]]
        w = out.setdefault(world, {"n": 0, "match": 0, "extWorld": 0, "extSampler": 0, "extBoth": 0,
                                   "mismatches": []})
        w["n"] += 1
        w["extWorld"] += rock in targets
        w["extSampler"] += p["rock"] in targets
        w["extBoth"] += rock in targets and p["rock"] in targets
        if p["rock"] == rock:
            w["match"] += 1
        else:
            w["mismatches"].append({"tag": p["tag"], "x": x, "y": y, "z": z, "world": rock, "sampler": p["rock"],
                                    "samplerTop": p["top"]})
    return out


def main():
    utf8_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--places", nargs="*", metavar="NAME", help="named places (see above); no names = the default list")
    ap.add_argument("--rocks", default="andesite,basalt,dacite,rhyolite", help="comma list of target rocks (default the extrusive four)")
    ap.add_argument("--random", type=int, default=0, metavar="N", help="also sample N random land points")
    ap.add_argument("--rng-seed", type=int, default=1, help="RNG seed for --random (default 1)")
    ap.add_argument("--validate", nargs="+", metavar="WORLD", default=[], help="compare against finished world(s)")
    ap.add_argument("--validate-n", type=int, default=50, help="columns per world for --validate")
    ap.add_argument("--spawn-skip", type=int, default=1000,
                    help="--validate leaves out chunks within this many blocks of Rome's spawn (10527,-257213) in worlds not named *rome*")
    ap.add_argument("--seed", default="pregen", help="world seed (default pregen, what world-rock-* used)")
    ap.add_argument("--step", type=int, default=32, help="ring search step in blocks")
    ap.add_argument("--cap", type=int, default=25000, help="search radius in blocks")
    ap.add_argument("--depths", default="25,50,75,100", help="dig depths below the surface to look at")
    ap.add_argument("--height-budget", type=int, default=2000, help="max terrain-height calls per place for land/sea checks")
    ap.add_argument("--start-search", type=int, default=48,
                    help="blocks to look for dry ground around a named place that is under water (like /startat; 0 = start exactly there)")
    ap.add_argument("--place-seconds", type=int, default=300, help="give up searching one place after this long")
    ap.add_argument("--out", help="JSON report path (default tools/.data/reports/rocksample-<timestamp>.json)")
    ap.add_argument("--keep-world", action="store_true")
    ap.add_argument("--no-sync", action="store_true", help="skip packwiz-installer")
    ap.add_argument("--xmx", default="6G")
    ap.add_argument("--timeout", type=int, default=4 * 3600, help="seconds to allow for the sampling itself")
    args = ap.parse_args()

    # Named places run by default, unless only --random or --validate was asked for.
    rocks = [r.strip() for r in args.rocks.split(",") if r.strip()]
    bad = [r for r in rocks if r not in ROCK_LAYER_ROCKS]
    if not rocks or bad:
        raise SystemExit(f"--rocks: unknown rock(s) {bad or rocks}; use TFC rock layer names, e.g. {sorted(ROCK_LAYER_ROCKS)}")
    custom = set(rocks) != EXTRUSIVE
    run_named = args.places is not None or (not args.random and not args.validate)
    named = parse_places(args.places) if run_named else []
    rng = random.Random(args.rng_seed)
    candidates = [[round(rng.uniform(-H, H)), round(rng.uniform(-V, V))] for _ in range(args.random * 14)]

    expected, probes = {}, []
    vrng = random.Random(args.rng_seed)
    for world in args.validate:
        # Every test world also has a few dozen chunks around the spawn near Rome; keep Rome's own world honest too.
        skip = None if "rome" in os.path.basename(os.path.normpath(world)).lower() else (10527, -257213, args.spawn_skip)
        found = world_probes(world, args.validate_n, vrng, skip)
        for x, z, y, tag, rock in found:
            probes.append([x, z, y, tag])
            expected[tag] = (x, z, y, rock)
        print(f"{world}: {len(found)} columns to check")

    job = {"expectH": H, "expectV": V, "rocks": rocks, "step": args.step, "cap": args.cap, "depths": [int(d) for d in args.depths.split(",")],
           "heightBudget": args.height_budget, "placeSeconds": args.place_seconds, "startSearch": args.start_search,
           "named": [list(p) for p in named], "random": args.random, "candidates": candidates, "probes": probes}
    script = write_job_script(job)
    t0 = time.time()
    lines, scale = run_server(script, args)
    info, recs, got, fatal = parse_output(lines)
    elapsed = time.time() - t0

    ok = bool(recs or got) and not fatal
    for f in fatal:
        print("  " + f)
    if scale and (scale.get("horizontal_scale") != str(H) or scale.get("vertical_scale") != str(V)):
        print(f"WARNING: the world's server.toml has {scale}, not the 20 m scale {H} x {V}")
        ok = False

    named_rows = [r for r in recs if r["mode"] == "named"]
    random_rows = [r for r in recs if r["mode"] == "random"]
    if named_rows:
        print()
        print_table(named_rows, args.cap, rocks if custom else None)
    if args.random:
        if random_rows:
            lat_lon = None
            try:
                from worldview.geo import Projection
                lat_lon = Projection(H, V, -170.0, 190.0, -90.0, 90.0)
            except Exception as e:  # numpy missing etc.: labels are optional
                print(f"(no lat/lon labels for random points: {e})")
            for r in random_rows:
                if lat_lon:
                    r["lon"], r["lat"] = (round(v, 3) for v in lat_lon.to_geo(r["x"], r["z"]))
            print_distribution(random_rows, args.cap, rocks if custom else None)
        else:
            print("No random points were sampled.")
            ok = False

    validation = None
    if args.validate:
        validation = check_probes(got, expected, set(rocks))
        print()
        for world, v in validation.items():
            print(f"{world}: sampler's rock matches the generated world at {v['match']}/{v['n']} columns "
                  f"; extrusive in the world {v['extWorld']}, in the sampler "
                  f"{v['extSampler']}, both {v['extBoth']}")
            for m in v["mismatches"][:10]:
                print(f"    {m['x']},{m['y']},{m['z']}: world {m['world']}, sampler {m['sampler']} (sampler surface y {m['samplerTop']})")
        total = sum(v["n"] for v in validation.values())
        agree = sum(v["match"] for v in validation.values())
        if not total or agree < 0.9 * total:
            ok = False

    report = {"generated": time.strftime("%Y-%m-%d %H:%M:%S"), "seconds": round(elapsed), "seed": args.seed, "rocks": rocks, "scale": [H, V],
              "step": args.step, "cap": args.cap, "depths": job["depths"], "rngSeed": args.rng_seed, "info": info,
              "named": named_rows, "random": random_rows, "validation": validation, "fatal": fatal}
    if random_rows:
        report["distribution"] = {f"{key}.{which}": {str(t): v for t, v in distribution(random_rows, key, which).items()}
                                  for key in ("surface", "dig") for which in ("any", "land")}
    out = args.out or os.path.join(DATA_DIR, "reports", f"rocksample-{time.strftime('%Y%m%d-%H%M%S')}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    print(f"\nReport: {out}  ({elapsed:.0f} s)")
    print("Verdict: " + ("OK" if ok else "FAIL"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
