"""Give TFC's boulders (and any other placed feature listed here) the `pack_world:keep_clear` placement filter.

    tools/.venv/Scripts/python tools/structure_mods/keep_clear_overrides.py [--tfc JAR] [--check]

TFC's boulders write their blocks without asking what is there (`BouldersFeature` puts a blob up to nine blocks across over whatever stands in
it), and they are placed after structures, so one landing on a village overwrote houses. `pack_world:keep_clear` (docs/lived-in.md, *Keeping the
land clear*) refuses a position within `margin` blocks of a piece of a structure that keeps trees out. The filter is added as the last placement
modifier of TFC's own placed feature, copied from the TFC jar into `kubejs/data/tfc/worldgen/placed_feature/<name>.json`. TFC's forests need no
file: a mixin in `pack_world` asks the same question for every trunk. Re-run after updating TFC (`--check` says whether the copies are stale);
`worldgen_check.py` hashes the TFC jar's worldgen data and the files here.
"""
import argparse
import glob
import json
import os
import sys
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODS = os.path.join(REPO, "tools", ".server", "mods")
OUT = os.path.join(REPO, "kubejs", "data", "tfc", "worldgen", "placed_feature")

# placed feature -> margin (blocks): the boulders' blob is up to nine across (6 to 9 radius); a baby boulder (TFC places them through a patch of six
# random placed features: it is the inner `_small` one, which has its own heightmap, that knows where the ground is) is five blocks at most
FEATURES = {
    "raw_boulder": 10,
    "cobble_boulder": 10,
    "mossy_boulder": 10,
    "raw_boulder_small": 3,
    "cobble_boulder_small": 3,
    "mossy_boulder_small": 3,
}


def build(zf):
    out = {}
    for name, margin in FEATURES.items():
        doc = json.loads(zf.read(f"data/tfc/worldgen/placed_feature/{name}.json").decode("utf-8"))
        doc["placement"] = [m for m in doc["placement"] if m.get("type") != "pack_world:keep_clear"] + [{"type": "pack_world:keep_clear", "margin": margin}]
        out[name] = json.dumps(doc, separators=(",", ":")) + "\n"
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tfc", help="TFC jar (default: the test server's)")
    ap.add_argument("--check", action="store_true", help="write nothing; exit 1 if the files differ from what TFC's jar would give")
    args = ap.parse_args()
    jar = args.tfc or next(iter(sorted(glob.glob(os.path.join(MODS, "TerraFirmaCraft-NeoForge-1.21.1-*.jar")))), None)
    if not jar:
        raise SystemExit("TFC's jar isn't in tools/.server/mods: run a tool that syncs the test server first")
    wanted = build(zipfile.ZipFile(jar))
    stale = []
    for name, text in wanted.items():
        path = os.path.join(OUT, name + ".json")
        have = open(path, encoding="utf-8").read() if os.path.exists(path) else None
        if have != text:
            stale.append(name)
            if not args.check:
                os.makedirs(OUT, exist_ok=True)
                with open(path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(text)
    verb = "differ from" if args.check else "rewritten from"
    print(f"{len(wanted)} placed features; {len(stale)} {verb} {os.path.basename(jar)}" + (f": {', '.join(stale)}" if stale else ""))
    sys.exit(1 if (args.check and stale) else 0)


if __name__ == "__main__":
    main()
