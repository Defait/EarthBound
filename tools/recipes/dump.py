"""Dump every recipe, item/fluid/block tag and block loot table from the pack.

Usage (from the repo root):
    tools/.venv/Scripts/python tools/recipes/dump.py [--no-sync] [--label NAME]

Boots the headless test server with a dev-only KubeJS script (never part of
the pack) that encodes all loaded recipes, then copies the result to
tools/.data/dumps/<timestamp>[-label]/. The explorer reads the newest dump.
"""
import argparse
import json
import os
import shutil
import sys
import time

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)

from mclib.pack import mods  # noqa: E402
from mclib.paths import DATA_DIR, utf8_console  # noqa: E402
from mclib.server import DONE_RE, TestServer  # noqa: E402

DUMPS = os.path.join(DATA_DIR, "dumps")
SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dump.js")


def main():
    utf8_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-sync", action="store_true", help="skip packwiz-installer")
    ap.add_argument("--label", default="", help="suffix for the dump folder, e.g. 'before-copper-change'")
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args()

    srv = TestServer()
    srv.ensure_installed()
    if not args.no_sync:
        srv.sync_pack()
    srv.set_extra_mods([])
    srv.set_dev_scripts({"pack_dump.js": SCRIPT})
    out = srv.path("local", "pack-dump")
    shutil.rmtree(out, ignore_errors=True)
    srv.write_properties("world-dump", "dump")

    print("Starting server with the dump script...")
    t0 = time.time()
    srv.start()
    ok = srv.wait_for(DONE_RE.pattern, args.timeout) and srv.wait_for(r"\[pack-dump\] done", 600)
    if ok:
        print("  " + ok.string.split("]: ", 1)[-1])
    srv.stop()
    srv.set_dev_scripts({})
    if not ok or not os.path.exists(os.path.join(out, "index.json")):
        raise SystemExit("Dump failed; check tools/.server/logs/latest.log (or run tools/logtriage.py --server)")

    name = time.strftime("%Y%m%d-%H%M%S") + (f"-{args.label}" if args.label else "")
    dest = os.path.join(DUMPS, name)
    shutil.copytree(out, dest)
    meta = {
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "pack": srv.pack["versions"],
        "mods": {os.path.basename(p): d.get("filename") for p, d in mods()},
    }
    with open(os.path.join(dest, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    index = json.load(open(os.path.join(dest, "index.json")))
    print(f"Dumped {int(index['recipes'])} recipes in {len(index['recipe_types'])} types "
          f"({int(index['failed'])} not encodable), {int(index['loot_tables'])} block loot tables "
          f"in {time.time() - t0:.0f}s -> {dest}")


if __name__ == "__main__":
    main()
