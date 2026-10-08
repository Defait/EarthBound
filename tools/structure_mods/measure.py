"""Generate test areas with Chunky and record what the structure skin does (the structure mods' fit to the pack).

Usage (from the repo root):
    tools/.venv/Scripts/python tools/structure_mods/measure.py [--places paris=48.86,2.35 ...] [--radius 1024]
                                                               [--mode after|before] [--seed pregen] [--keep-world] [--no-sync]

For each place: a fresh world `world-sm-<place>-<mode>` on the test server (Chunky added for the run only, like tools/pregen.py),
a dev-only KubeJS script (measure.js) that switches the skin's measurements on, Chunky over a square of 2*radius blocks. Written to
tools/.data/structure_mods/<place>-<mode>.json: the skin's counters, the blocks structures wrote that it has no rule for, and per
structure the blocks written before/after the skin, ground columns and floating ones before/after the foundation, plus chunks per
second. `--mode before` adds a world datapack with `{"dry_run": true}`: the skin measures but rewrites nothing, which is the
state without the skin (other mods' own processors still run). The default places are the structure trial's: Paris, the Mongolian
steppe, Cairo and Stockholm. Uses the test server: take the lock first when other agents work (see the integration notes).
"""
import argparse
import json
import os
import re
import shutil
import sys
import time

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)
from mclib.paths import DATA_DIR, utf8_console  # noqa: E402
from mclib.server import DONE_RE, TestServer  # noqa: E402
import pregen as PG  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(DATA_DIR, "structure_mods")
DEFAULT_PLACES = {"paris": (48.86, 2.35), "steppe": (47.9, 106.9), "cairo": (30.0, 31.2), "stockholm": (59.3, 18.1)}
TOTAL_RE = re.compile(r"Total time: (?:(\d+):)?(\d+):(\d+)")


def run_place(srv, name, lat, lon, radius, mode, seed, keep, timeout, suffix=""):
    world = f"world-sm-{name}-{mode}{suffix}"
    world_dir = srv.path(world)
    shutil.rmtree(world_dir, ignore_errors=True)
    shutil.rmtree(srv.path("local", "structure-mods"), ignore_errors=True)
    if mode == "before":
        dp = os.path.join(world_dir, "datapacks", "skin-dry-run")
        os.makedirs(os.path.join(dp, "data", "pack", "pack_world", "structure_skin"))
        with open(os.path.join(dp, "data", "pack", "pack_world", "structure_skin", "zz_dry_run.json"), "w") as f:
            json.dump({"dry_run": True}, f)
        with open(os.path.join(dp, "pack.mcmeta"), "w") as f:
            json.dump({"pack": {"pack_format": 48, "description": "skin dry run (tools/structure_mods/measure.py)"}}, f)
    srv.write_properties(world, seed)
    print(f"[{name}/{mode}] starting server ({lat}, {lon}, radius {radius})...")
    srv.start("8G")
    if not srv.wait_for(DONE_RE.pattern, 900):
        srv.stop()
        raise SystemExit("Server didn't start; see tools/.server/logs/latest.log")
    proj = PG.projection_for(world_dir)
    if not proj:
        srv.stop()
        raise SystemExit("no TFC: Real World projection for the world")
    x, z = proj.to_block(lon, lat)
    cx, cz = round(x), round(z)
    srv.command("chunky world minecraft:overworld")
    srv.command("chunky shape square")
    srv.command(f"chunky center {cx} {cz}")
    srv.command(f"chunky radius {radius}")
    t0 = time.time()
    srv.command("chunky start")
    srv.command("chunky confirm")
    finished, last = None, 0
    while time.time() < t0 + timeout:
        line = srv.wait_for(r"\[Chunky\]", 60)
        if line is None:
            if srv.proc.poll() is not None:
                break
            continue
        if re.search(PG.FINISHED_RE, line.string):
            finished = line.string
            break
        m = PG.PROGRESS_RE.search(line.string)
        if m and time.time() - last > 60:
            last = time.time()
            print(f"  {m[2]}% · {m[1]} chunks · {m[3]} chunks/s")
    elapsed = time.time() - t0
    time.sleep(8)            # the script dumps every 5 seconds
    srv.command("save-all flush")
    srv.wait_for(r"Saved the game", 300)
    srv.stop()
    if not finished:
        raise SystemExit("generation did not finish; see tools/.server/logs/latest.log")
    chunks = (2 * radius // 16 + 1) ** 2
    m = TOTAL_RE.search(finished)
    seconds = (int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + int(m.group(3))) if m else elapsed
    stats_file = srv.path("local", "structure-mods", "stats.json")
    stats = json.load(open(stats_file)) if os.path.exists(stats_file) else {}
    stats.update({"place": name, "lat": lat, "lon": lon, "center": [cx, cz], "radius": radius, "mode": mode, "seed": seed,
                  "chunks": chunks, "seconds": seconds, "chunks_per_second": round(chunks / max(seconds, 1), 1), "chunky": finished.split("]: ", 1)[-1]})
    os.makedirs(OUT, exist_ok=True)
    dest = os.path.join(OUT, f"{name}-{mode}{suffix}.json")
    with open(dest, "w") as f:
        json.dump(stats, f, indent=1)
    print(f"[{name}/{mode}] {chunks} chunks in {seconds}s = {stats['chunks_per_second']} chunks/s; stats {dest}")
    if not keep:
        shutil.rmtree(world_dir, ignore_errors=True)
    return stats


def main():
    utf8_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--places", nargs="*", help="name=lat,lon ... (default: paris steppe cairo stockholm)")
    ap.add_argument("--radius", type=int, default=1024)
    ap.add_argument("--mode", choices=["after", "before"], default="after")
    ap.add_argument("--seed", default="pregen")
    ap.add_argument("--no-census", action="store_true", help="leave the per-structure measurements off (they cost generation speed): only the counters and chunks/s")
    ap.add_argument("--keep-world", action="store_true")
    ap.add_argument("--no-sync", action="store_true")
    ap.add_argument("--timeout", type=int, default=3 * 3600)
    args = ap.parse_args()
    places = dict(DEFAULT_PLACES)
    if args.places:
        places = {}
        for p in args.places:
            if "=" in p:
                n, ll = p.split("=", 1)
                lat, lon = (float(v) for v in ll.split(","))
                places[n] = (lat, lon)
            else:
                places[p] = DEFAULT_PLACES[p]

    srv = TestServer()
    srv.ensure_installed()
    if not args.no_sync:
        srv.sync_pack()
    srv.set_extra_mods([PG.chunky_jar(srv, srv.pack["versions"]["minecraft"], srv.loader)])
    script = open(os.path.join(HERE, "measure.js"), encoding="utf-8").read()
    script = re.sub(r"/\*CENSUS\*/.*?/\*END\*/", "/*CENSUS*/ " + ("false" if args.no_census else "true") + " /*END*/", script, flags=re.S)
    os.makedirs(OUT, exist_ok=True)
    script_path = os.path.join(OUT, "measure_run.js")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script)
    srv.set_dev_scripts({"structure_mods_measure.js": script_path})
    try:
        for name, (lat, lon) in places.items():
            run_place(srv, name, lat, lon, args.radius, args.mode, args.seed, args.keep_world, args.timeout, "-nocensus" if args.no_census else "")
    finally:
        srv.set_dev_scripts({})
        srv.set_extra_mods([])


if __name__ == "__main__":
    main()
