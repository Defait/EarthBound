"""How many villages a set's biome tag and guard let through, from a recorded census (docs/lived-in.md, *Tuning a village*).

Usage (from the repo root):
    tools/.venv/Scripts/python tools/structures_test.py --villages --per-set 0 --acceptance        # records the census (no chunks, a few minutes)
    tools/.venv/Scripts/python tools/structures/village_tune.py [RESULTS.json] [--set norse] [--landforms +coast,-cold] [--biomes +tfc:x]
                                                                  [--max-diff 14] [--radius 24] [--water 0.2] [--show 12]

The census (`tools/.data/reports/structures-*.json`, `villages.acceptance`) holds, for every placement cell of each village set across its
regions that passes the region and climate tests, the biome at its centre and the heights a guard of radius 48 and of radius 24 sees.
This applies the catalogue's biome groups and guard to it (or the overrides on the command line: they change nothing in the catalogue)
and prints per set the cells that survive each test, why the others do not, and the density: villages per million blocks squared of the
regions' area and the mean distance between neighbours. To keep a change, edit `structures/catalogue.json` (`villages.<id>.set.landforms`,
`.guard`) and rebuild.
"""
import argparse
import collections
import glob
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
CATALOGUE = os.path.join(HERE, "catalogue.json")


def latest_results():
    files = sorted(glob.glob(os.path.join(TOOLS, ".data", "reports", "structures-*.json")), key=os.path.getmtime)
    for f in reversed(files):
        try:
            if "acceptance" in json.load(open(f, encoding="utf-8")).get("villages", {}):
                return f
        except (OSError, ValueError):
            continue
    raise SystemExit("No structures-*.json with an acceptance census: run structures_test.py --villages --per-set 0 --acceptance")


def biome_set(cat, vsp, add_groups, drop_groups, extra):
    groups = [g for g in vsp.get("landforms", []) if g not in drop_groups] + [g for g in add_groups if g not in vsp.get("landforms", [])]
    members = set(vsp.get("biomes", [])) | set(extra)
    for g in groups:
        members |= set(cat["landforms"].get(g, []))
    return {f"tfc:{b}" if ":" not in b else b for b in members}, groups


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results", nargs="?")
    ap.add_argument("--set", help="one village (norse, arabic, ...)")
    ap.add_argument("--landforms", default="", help="landform groups to add (+name) or drop (-name), comma-separated")
    ap.add_argument("--biomes", default="", help="biomes to add (+tfc:name)")
    ap.add_argument("--max-diff", type=int, help="override max_height_difference")
    ap.add_argument("--radius", type=int, choices=(24, 48), help="the census holds radius 24 and 48; default the village's own")
    ap.add_argument("--water", type=float, help="override max_water_fraction")
    ap.add_argument("--show", type=int, default=8, help="reasons to list per village")
    args = ap.parse_args()
    cat = json.load(open(CATALOGUE, encoding="utf-8"))
    results = json.load(open(args.results or latest_results(), encoding="utf-8"))["villages"]
    census = results["acceptance"]
    add = [x[1:] for x in args.landforms.split(",") if x.startswith("+")]
    drop = [x[1:] for x in args.landforms.split(",") if x.startswith("-")]
    extra = [x[1:] for x in args.biomes.split(",") if x.startswith("+")]
    V = cat["villages"]
    defaults = V.get("defaults", {})
    print(f"{'village':10} {'cells':>6} {'climate':>7} {'biome':>6} {'guard':>6}  {'villages':>8} {'per 1e6 blocks2':>15} {'mean gap':>9}   landforms / guard")
    for cid, row in sorted(census.items()):
        name = cid.split("/")[1]
        if args.set and name != args.set:
            continue
        vsp = V[name]
        g = dict(defaults.get("guard", {}))
        g.update(vsp.get("guard", {}))
        for v in vsp["variants"].values():
            g.update(v.get("guard", {}))
        if args.max_diff is not None:
            g["max_height_difference"] = args.max_diff
        if args.water is not None:
            g["max_water_fraction"] = args.water
        radius = args.radius or g.get("radius", 48)
        samples = g.get("samples", 13)
        allowed_wet = math.floor(g.get("max_water_fraction", 0.1) * samples + 1e-9)
        members, groups = biome_set(cat, vsp["set"], add, drop, extra)
        stride2 = row["stride"] ** 2
        why = collections.Counter()
        biome_ok = guard_ok = 0
        for _cx, _cz, biome, mn48, mx48, wet48, mn24, mx24, wet24 in row["cells"]:
            mn, mx, wet = (mn48, mx48, wet48) if radius >= 48 else (mn24, mx24, wet24)
            if biome not in members:
                why["biome " + biome] += 1
                continue
            biome_ok += 1
            if wet > allowed_wet:
                why["water"] += 1
            elif mx - mn > g.get("max_height_difference", 8):
                why["slope"] += 1
            else:
                guard_ok += 1
        regions = results["regions"][cid]["regions"]
        area_blocks = sum(regions.values()) * 256            # chunks^2 -> blocks^2; overlapping regions of one set are counted twice (they do not overlap)
        villages = guard_ok * stride2
        density = villages / (area_blocks / 1e6) if area_blocks else 0
        gap = math.sqrt(1e6 / density) if density else float("inf")
        print(f"{name:10} {row['considered']:>6} {len(row['cells']):>7} {biome_ok:>6} {guard_ok:>6}  {villages:>8} {density:>15.3f} {gap:>9.0f}   "
              f"{','.join(groups)}{'+' + ','.join(extra) if extra else ''} / radius {radius}, difference {g.get('max_height_difference', 8)}, water {g.get('max_water_fraction', 0.1)}")
        for reason, n in why.most_common(args.show):
            print(f"{'':10} {n:>6}  {reason}")


if __name__ == "__main__":
    main()
