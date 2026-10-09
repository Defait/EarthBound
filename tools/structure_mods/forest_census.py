"""Tree leaves inside the pieces' boxes of every structure in generated worlds, per structure namespace (docs/lived-in.md, *Keeping the land clear*).

Usage: tools/.venv/Scripts/python tools/structure_mods/forest_census.py WORLD_DIR [WORLD_DIR ...] [--ids pack,towns_and_towers,mvs:*,...] [--out FILE.json]

Reads the Anvil files without a server. For every structure start in a fully generated chunk whose id matches --ids (namespaces, ids, or prefixes
ending in `*`; default: the namespaces that keep trees out, see `kubejs/data/pack/pack_world/keep_clear/structures.json`) it counts the TFC and
ArborFirmaCraft leaves inside the boxes of its pieces and in the 6-block ring around them. Run it on the same area generated with and without the
keep-clear data (or before and after pack_world 1.3.0) for the comparison; the world seed gives the same starts both times. The leaves of trees
the structure builds itself (Moog's tree structures, T&T's orchards) count too, so those namespaces' ids are left out by default.
"""
import argparse
import collections
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import worldreader as L  # noqa: E402
import village_census as VC  # noqa: E402

REPO = os.path.dirname(os.path.dirname(HERE))
KEEP = os.path.join(REPO, "kubejs", "data", "pack", "pack_world", "keep_clear", "structures.json")
LEAVES = re.compile(r"^(?:tfc|afc):wood/leaves/")
RING = 6


def matcher(entries):
    pats = []
    for e in entries:
        pats.append(re.compile("^" + ".*".join(re.escape(p) for p in e.split("*")) + "$") if "*" in e else (re.compile("^" + re.escape(e) + ":") if ":" not in e else re.compile("^" + re.escape(e) + "$")))
    return lambda sid: any(p.match(sid) for p in pats)


def default_ids():
    cfg = json.load(open(KEEP, encoding="utf-8"))
    return cfg["trees"], cfg.get("exclude_trees", [])


def census(world, want, skip, max_size):
    reader = L.WorldReader(world)
    starts = {}
    for cx, cz, root in reader.iter_all():
        if not str(root.get("Status", "")).endswith("full"):
            continue
        for sid, chunk, pieces in VC.starts_of(root):
            if chunk == (cx, cz) and want(sid) and not skip(sid) and pieces:
                starts[(sid, chunk)] = pieces
    out = collections.defaultdict(lambda: {"starts": 0, "pieces": 0, "leaves_in_boxes": 0, "leaves_in_ring": 0, "with_leaves": 0})
    by_id = collections.defaultdict(lambda: {"starts": 0, "leaves_in_boxes": 0})
    for (sid, _chunk), pieces in sorted(starts.items()):
        boxes = [b for b, _ in pieces]
        x0, y0, z0 = min(b[0] for b in boxes) - RING, min(b[1] for b in boxes) - 1, min(b[2] for b in boxes) - RING
        x1, y1, z1 = max(b[3] for b in boxes) + RING, min(max(b[4] for b in boxes) + 34, 318), max(b[5] for b in boxes) + RING
        if max(x1 - x0, z1 - z0) > max_size or y0 >= y1:
            continue
        # the box reaches up to 34 blocks over the pieces; deep boxes (a mineshaft's) are cut at the terrain by the caller's --max-size
        arr, pal = reader.box(x0, max(y0, -64), z0, x1, y1, z1)
        # leaves a template places are persistent; a tree that grew there is not
        leaf = np.array([bool(LEAVES.match(n)) and p.get("persistent") != "true" for n, p in pal])[arr]
        inside = np.zeros(arr.shape, bool)
        foot = np.zeros((arr.shape[0], arr.shape[2]), bool)
        for b in boxes:
            ya, yb = max(b[1] - max(y0, -64), 0), min(b[4] - max(y0, -64) + 1, arr.shape[1])
            inside[b[0] - x0:b[3] - x0 + 1, ya:yb, b[2] - z0:b[5] - z0 + 1] = True
            foot[b[0] - x0:b[3] - x0 + 1, b[2] - z0:b[5] - z0 + 1] = True
        ring = VC.dilate(foot, RING) & ~foot
        ns = sid.split(":")[0]
        row = out[ns]
        n_in = int((leaf & inside).sum())
        row["starts"] += 1
        row["pieces"] += len(pieces)
        row["leaves_in_boxes"] += n_in
        row["leaves_in_ring"] += int((leaf & ring[:, None, :]).sum())
        row["with_leaves"] += 1 if n_in else 0
        by_id[sid]["starts"] += 1
        by_id[sid]["leaves_in_boxes"] += n_in
    return out, by_id


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("worlds", nargs="+")
    ap.add_argument("--ids", help="comma-separated namespaces, ids, or prefixes ending in * (default: the keep-clear data's `trees`, minus its `exclude_trees`)")
    ap.add_argument("--max-size", type=int, default=140, help="skip structures wider than this (default 140)")
    ap.add_argument("--by-id", type=int, default=0, help="also list the N structure ids with the most leaves in their boxes")
    ap.add_argument("--out")
    args = ap.parse_args()
    if args.ids:
        want, skip = matcher([x.strip() for x in args.ids.split(",")]), (lambda sid: False)
    else:
        inc, exc = default_ids()
        want, skip = matcher(inc), matcher(exc)
    total = collections.defaultdict(lambda: collections.Counter())
    by_id = collections.defaultdict(lambda: collections.Counter())
    report = {}
    for w in args.worlds:
        res, ids = census(w, want, skip, args.max_size)
        report[w] = res
        for sid, row in ids.items():
            by_id[sid].update(row)
        for ns, row in res.items():
            total[ns].update(row)
    print(f"{'namespace':20}{'starts':>7}{'pieces':>7}{'leaves in boxes':>16}{'with leaves':>12}{'leaves in 6-ring':>17}")
    for ns, row in sorted(total.items()):
        print(f"{ns:20}{row['starts']:>7}{row['pieces']:>7}{row['leaves_in_boxes']:>16}{row['with_leaves']:>12}{row['leaves_in_ring']:>17}")
    if args.by_id:
        print()
        for sid, row in sorted(by_id.items(), key=lambda kv: -kv[1]["leaves_in_boxes"])[:args.by_id]:
            print(f"{sid:50}{row['starts']:>5} starts{row['leaves_in_boxes']:>8} leaves in boxes")
    if args.out:
        json.dump({"worlds": args.worlds, "per_world": {k: dict(v) for k, v in report.items()}, "total": {k: dict(v) for k, v in total.items()}}, open(args.out, "w"), indent=1)


if __name__ == "__main__":
    main()
