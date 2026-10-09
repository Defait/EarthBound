"""Pre-generate a fixed-seed test world on the headless server with Chunky, and time it.

Usage (from the repo root):
    tools/.venv/Scripts/python tools/pregen.py [--radius 1024] [--place 41.89,12.51 | --center X,Z]
                                               [--seed pregen] [--world world-pregen] [--fresh] [--no-sync]
                                               [--no-cache | --at REV]

Chunky is added to the test server for this run only (never to the pack).
The world lands in tools/.server/<world>; open it with the other tools:
    tools/.venv/Scripts/python tools/worldview/serve.py tools/.server/world-pregen
    tools/.venv/Scripts/python tools/recipes/serve.py --world tools/.server/world-pregen
--place takes latitude,longitude for TFC: Real World worlds (Equal Earth map).

A fresh world is cached (tools/worldcache.py): the same settings with the same pack copy the cached world in and
skip the server, and `--at HEAD` fetches the world made before your uncommitted change without the server at all.
--no-cache generates anyway; --no-sync never uses the cache (the server may not hold the pack).
"""
import argparse
import json
import os
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mclib.paths import utf8_console  # noqa: E402
from mclib.server import DONE_RE, TestServer, download  # noqa: E402
import worldcache  # noqa: E402

# Chunky formats numbers with the system locale, e.g. "17,84%" and "65,3 cps".
PROGRESS_RE = re.compile(r"\[Chunky\] Task running .*?Processed: ([\d,.\s]+) chunks \(([\d.,]+)%\).*?Rate: ([\d.,]+) cps", re.I)
FINISHED_RE = r"\[Chunky\] Task finished"


def chunky_jar(srv, mc, loader):
    q = urllib.parse.urlencode({"loaders": json.dumps([loader]), "game_versions": json.dumps([mc])})
    req = urllib.request.Request(f"https://api.modrinth.com/v2/project/chunky/version?{q}", headers={"User-Agent": "mc-pack-tools"})
    versions = json.load(urllib.request.urlopen(req, timeout=30))
    if not versions:
        raise SystemExit(f"No Chunky build for {loader} {mc} on Modrinth")
    f = next(x for x in versions[0]["files"] if x.get("primary")) if any(x.get("primary") for x in versions[0]["files"]) else versions[0]["files"][0]
    dest = srv.path(".cache", f["filename"])
    if not os.path.exists(dest):
        download(f["url"], dest)
    return dest


def projection_for(world_dir):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from worldview.geo import load_projection
    return load_projection(world_dir, [os.path.join(os.path.dirname(world_dir), "mods")])


def main():
    utf8_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--radius", type=int, default=1024, help="half-width of the square to generate, in blocks")
    ap.add_argument("--center", help="X,Z block center (default: world spawn)")
    ap.add_argument("--place", help="LAT,LON center for TFC: Real World worlds, e.g. 41.89,12.51")
    ap.add_argument("--seed", default="pregen")
    ap.add_argument("--world", default="world-pregen")
    ap.add_argument("--fresh", action="store_true", help="delete the world first")
    ap.add_argument("--no-sync", action="store_true")
    ap.add_argument("--xmx", default="8G")
    ap.add_argument("--timeout", type=int, default=6 * 3600, help="seconds to allow for generation")
    ap.add_argument("--no-cache", action="store_true", help="generate even when a cached world matches (and refresh it)")
    ap.add_argument("--at", metavar="REV", help="only fetch the cached world for the pack as committed at REV (e.g. HEAD); never starts the server")
    args = ap.parse_args()

    world_dir = os.path.join(worldcache.SERVER_DIR, args.world)
    params = {"seed": args.seed, "radius": args.radius, "place": args.place, "center": args.center}
    fresh = args.fresh or not os.path.exists(world_dir)
    pkey = None
    if args.at:
        hit = worldcache.lookup("pregen", params, worldcache.pack_key(args.at))
        if not hit:
            raise SystemExit(f"No cached world for these settings with the pack at {args.at}. It is cached when generated "
                             f"with the pack in that state (e.g. before changing it), or see: tools/worldcache.py list")
        return reuse(hit, world_dir)
    if not fresh:
        print("Adding to the existing world, so the cache is not used (--fresh starts over).")
    elif args.no_sync:
        print("--no-sync: the cache is not used (the server may not hold the pack).")
    else:
        pkey = worldcache.pack_key()
        hit = None if args.no_cache else worldcache.lookup("pregen", params, pkey)
        if hit:
            return reuse(hit, world_dir)

    srv = TestServer()
    srv.ensure_installed()
    if not args.no_sync:
        srv.sync_pack()
    srv.set_extra_mods([chunky_jar(srv, srv.pack["versions"]["minecraft"], srv.loader)])
    srv.set_dev_scripts({})
    if args.fresh:
        shutil.rmtree(world_dir, ignore_errors=True)
    srv.write_properties(args.world, args.seed)

    print(f"Starting server for {args.world} (seed '{args.seed}')...")
    srv.start(args.xmx)
    if not srv.wait_for(DONE_RE.pattern, 900):
        srv.stop()
        raise SystemExit("Server didn't start; see tools/.server/logs/latest.log")

    center = None
    if args.place:
        lat, lon = (float(v) for v in args.place.split(","))
        proj = projection_for(world_dir)
        if not proj:
            srv.stop()
            raise SystemExit("--place needs a TFC: Real World world (no tfc_real_world server config found)")
        x, z = proj.to_block(lon, lat)
        center = (round(x), round(z))
        print(f"{lat}, {lon} -> block x {center[0]}, z {center[1]}")
    elif args.center:
        center = tuple(int(v) for v in args.center.split(","))

    srv.command("chunky world minecraft:overworld")
    srv.command("chunky shape square")
    srv.command(f"chunky center {center[0]} {center[1]}" if center else "chunky spawn")
    srv.command(f"chunky radius {args.radius}")
    chunks_expected = (2 * args.radius // 16 + 1) ** 2
    print(f"Generating a {2 * args.radius}x{2 * args.radius} block square (~{chunks_expected:,} chunks)...")
    t0 = time.time()
    srv.command("chunky start")
    srv.command("chunky confirm")   # only needed when Chunky asks to overwrite an existing task
    last = 0
    finished = None
    end = time.time() + args.timeout
    while time.time() < end:
        line = srv.wait_for(r"\[Chunky\]", 60)
        if line is None:
            if srv.proc.poll() is not None:
                break
            continue
        if re.search(FINISHED_RE, line.string):
            finished = line.string
            break
        m = PROGRESS_RE.search(line.string)
        if m and time.time() - last > 15:
            last = time.time()
            print(f"  {m[2]}% · {m[1]} chunks · {m[3]} chunks/s")
    elapsed = time.time() - t0
    srv.command("save-all flush")
    srv.wait_for(r"Saved the game", 300)
    srv.stop()
    srv.set_extra_mods([])
    if not finished:
        raise SystemExit("Generation did not finish (timed out or the server stopped); see tools/.server/logs/latest.log")
    print(finished.split("]: ", 1)[-1])
    print(f"Done in {elapsed:.0f}s (~{chunks_expected / max(elapsed, 1):.1f} chunks/s overall).")
    if pkey:
        worldcache.store("pregen", params, pkey, world_dir, {"seconds": round(elapsed), "center": center,
                                                             "chunky": finished.split("]: ", 1)[-1]})
    report(world_dir)


def reuse(hit, world_dir):
    worldcache.restore(hit, world_dir)
    meta = hit[1]
    print(f"Reused the cached world ({worldcache.describe(meta)}, generated in {meta.get('seconds', '?')}s); "
          "no server run. --no-cache generates it again.")
    print("Done in 0s (cached).")
    report(world_dir)


def report(world_dir):
    print(f"World: {world_dir}")
    print(f"  View it:  tools/.venv/Scripts/python tools/worldview/serve.py {os.path.relpath(world_dir)}")
    print(f"  Seed the progression checker with it:  tools/.venv/Scripts/python tools/recipes/serve.py --world {os.path.relpath(world_dir)}")


if __name__ == "__main__":
    main()
