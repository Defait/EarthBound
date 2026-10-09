"""The pack's villages in a generated world (docs/lived-in.md, *Settlements*): what stands there, who lives there, what they overlap.

Usage: tools/.venv/Scripts/python tools/structure_mods/village_census.py WORLD_DIR [--out OUT.json] [--json]

Reads the Anvil files of WORLD_DIR (a world made by tools/pregen.py, or a test world) without a server. For every start of a
`pack:village/<culture>_<variant>` structure in a fully generated chunk it reports: where (chunk, block box and size), how many pieces and of
which buildings, how many of them are NPC spots, the Easy NPCs found inside its box (name, trades), the loot tables of its containers, and
every other structure whose pieces overlap its pieces (by namespace: Towns and Towers, Moog's, TFC Huts, the pack's own ruins, another village).
A piece that `pack_world`'s keep-clear did not place keeps its box in the world's data, so box overlaps cannot tell: --skipped SERVER_LOG (a server log
holding `pack_world keep-clear: a piece of ... is not placed` lines, which the run logs, the first 400) moves those pieces from `overlaps` to
`suppressed`. With --trees it also counts the tree leaves (TFC and ArborFirmaCraft; village-built logs can't be told from trunks, so they are counted apart) inside the village:
in the pieces' own boxes, over their footprint (the columns above and below the boxes), and in a ring of 1 to 6 blocks around the footprint; and which woods and rocks the buildings are
made of (one village should use one rock and at most three woods). A summary per culture closes the report: villages, pieces per village, NPCs per
village, overlaps, and with --trees the tree and material figures.
"""
import argparse
import collections
import json
import os
import re
import sys

import numpy as np

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from worldview import region as WR  # noqa: E402
import worldreader as L  # noqa: E402


def piece_name(child):
    el = child.get("pool_element") or {}
    loc = el.get("location")
    return loc if isinstance(loc, str) else None


def starts_of(root):
    """[(structure id, (chunk x, z), [(box, template or None)])] of the structures that start in this chunk."""
    out = []
    for st in ((root.get("structures") or {}).get("starts") or {}).values():
        if not isinstance(st, dict) or st.get("id") in (None, "INVALID"):
            continue
        pieces = []
        for ch in st.get("Children", []):
            bb = ch.get("BB")
            if bb is not None and len(bb) == 6:
                pieces.append(([int(v) for v in bb], piece_name(ch)))
        out.append((st["id"], (int(st["ChunkX"]), int(st["ChunkZ"])), pieces))
    return out


SKIPPED_RE = re.compile(r"keep-clear: a piece of (\S+) at BoundingBox\{minX=(-?\d+), minY=(-?\d+), minZ=(-?\d+), maxX=(-?\d+), maxY=(-?\d+), maxZ=(-?\d+)\} is not placed")


def skipped_pieces(logs):
    """{(structure id, (minX, minY, minZ, maxX, maxY, maxZ))} of the pieces the logs say were not placed."""
    out = set()
    for path in logs or []:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = SKIPPED_RE.search(line)
                if m:
                    out.add((m.group(1), tuple(int(m.group(i)) for i in range(2, 8))))
    return out


def boxes_overlap(a, b):
    return a[0] <= b[3] and b[0] <= a[3] and a[1] <= b[4] and b[1] <= a[4] and a[2] <= b[5] and b[2] <= a[5]


def text_of(value):
    """A custom name as plain text (it is stored as a JSON string or a compound)."""
    if isinstance(value, str):
        try:
            doc = json.loads(value)
        except ValueError:
            return value
        if isinstance(doc, dict):
            return str(doc.get("text", value))
        return str(doc)
    if isinstance(value, dict):
        return str(value.get("text", value))
    return str(value)



LEAVES_RE = re.compile(r"^(?:tfc|afc):wood/leaves/")
LOG_RE = re.compile(r"^(?:tfc|afc):wood/log/")
BUILT_WOOD_RE = re.compile(r"^(?:tfc|afc):wood/(?:planks|vertical_support|horizontal_support|fence|fence_gate|log_fence|door|trapdoor|stripped_log|stripped_wood|wood|chest|barrel|lectern|loom|sign|workbench)/([a-z_]+?)(?:_stairs|_slab)?$")
SHINGLES_RE = re.compile(r"^rnr:wood/shingles/([a-z_]+?)(?:_stairs|_slab)?$")
BUILT_ROCK_RE = re.compile(r"^(?:tfc|rnr):rock/(?:smooth|bricks|cracked_bricks|mossy_bricks|chiseled|gravel_road|sett_road|cobbled_road|polished)/([a-z]+)")
RING = 6
SKY = 34            # how far above the highest piece the tree count reads (the tallest trees are about 30 high)


def dilate(mask, k):
    """Chebyshev dilation of a 2D boolean mask by k cells."""
    out = mask.copy()
    for _ in range(k):
        p = np.pad(out, 1)
        out = p[1:-1, 1:-1] | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:] | p[:-2, :-2] | p[2:, 2:] | p[:-2, 2:] | p[2:, :-2]
    return out


def vegetation(reader, pieces):
    """Tree blocks and building materials of one village. pieces: [(box, template)] of the village start."""
    boxes = [b for b, _ in pieces]
    x0, y0, z0 = min(b[0] for b in boxes) - RING, min(b[1] for b in boxes) - 2, min(b[2] for b in boxes) - RING
    x1, y1, z1 = max(b[3] for b in boxes) + RING, max(b[4] for b in boxes) + SKY, max(b[5] for b in boxes) + RING
    arr, pal = reader.box(x0, y0, z0, x1, min(y1, 318), z1)
    # leaves a template places are persistent (an orchard tree in a farmstead); a tree that grew there is not
    leaf = np.array([bool(LEAVES_RE.match(n)) and p.get("persistent") != "true" for n, p in pal])
    log = np.array([bool(LOG_RE.match(n)) for n, _ in pal])
    tree = leaf | log
    sx, sy, sz = arr.shape
    inside = np.zeros(arr.shape, bool)
    foot = np.zeros((sx, sz), bool)
    for b in boxes:
        xs, xe = b[0] - x0, b[3] - x0 + 1
        ys, ye = max(b[1] - y0, 0), min(b[4] - y0 + 1, sy)
        zs, ze = b[2] - z0, b[5] - z0 + 1
        inside[xs:xe, ys:ye, zs:ze] = True
        foot[xs:xe, zs:ze] = True
    ring = dilate(foot, RING) & ~foot
    ring_near = dilate(foot, 3) & ~foot
    is_tree, is_leaf = tree[arr], leaf[arr]
    out = {
        "tree_in_boxes": int((is_tree & inside).sum()), "leaves_in_boxes": int((is_leaf & inside).sum()),
        "tree_over_footprint": int((is_tree & foot[:, None, :]).sum()), "leaves_over_footprint": int((is_leaf & foot[:, None, :]).sum()),
        "tree_in_ring": int((is_tree & ring[:, None, :]).sum()), "leaves_in_ring": int((is_leaf & ring[:, None, :]).sum()),
        "leaves_in_ring3": int((is_leaf & ring_near[:, None, :]).sum()),
        "footprint_columns": int(foot.sum()),
    }
    woods, rocks = collections.Counter(), collections.Counter()
    for i, (n, _) in enumerate(pal):
        c = int(((arr == i) & inside).sum()) if n != "minecraft:air" and (BUILT_WOOD_RE.match(n) or SHINGLES_RE.match(n) or BUILT_ROCK_RE.match(n)) else 0
        if not c:
            continue
        m = BUILT_WOOD_RE.match(n) or SHINGLES_RE.match(n)
        if m:
            # Roads and Roofs' shingles carry the bare name of a TFC or an ArborFirmaCraft wood, so the two are one wood here
            if m.group(1) != "palm_mosaic":         # the Arabic templates' fixed decoration, not one of the village's woods
                woods[m.group(1)] += c
        else:
            rocks[BUILT_ROCK_RE.match(n).group(1)] += c
    out["woods"], out["rocks"] = dict(woods.most_common()), dict(rocks.most_common())
    return out


def census(world, trees=False, skipped=None):
    rdir = os.path.join(world, "region")
    starts = {}
    full = set()
    for _rx, _rz, path in WR.list_regions(rdir):
        for _lx, _lz, root in WR.iter_chunks(path):
            is_full = str(root.get("Status", "")).endswith("full")
            for sid, chunk, pieces in starts_of(root):
                starts[(sid, chunk)] = pieces
                if is_full:
                    full.add((sid, chunk))
    villages = [(k, v) for k, v in starts.items() if k[0].startswith("pack:village/") and k in full]
    # which chunk touches which start (for the overlap and block entity lookups)
    index = collections.defaultdict(list)
    for key, pieces in starts.items():
        touched = set()
        for box, _ in pieces:
            for cx in range(box[0] >> 4, (box[3] >> 4) + 1):
                for cz in range(box[2] >> 4, (box[5] >> 4) + 1):
                    touched.add((cx, cz))
        for c in touched:
            index[c].append(key)
    report = []
    for (sid, chunk), pieces in sorted(villages):
        boxes = [b for b, _ in pieces]
        x0, y0, z0 = min(b[0] for b in boxes), min(b[1] for b in boxes), min(b[2] for b in boxes)
        x1, y1, z1 = max(b[3] for b in boxes), max(b[4] for b in boxes), max(b[5] for b in boxes)
        names = collections.Counter((t.replace("pack:village/", "") if t else "?") for _, t in pieces)
        npc_pieces = sum(n for k, n in names.items() if "/npc/" in k)
        overlaps = collections.Counter()
        suppressed = collections.Counter()
        for key in set(k for c in {(cx, cz) for b in boxes for cx in range(b[0] >> 4, (b[3] >> 4) + 1) for cz in range(b[2] >> 4, (b[5] >> 4) + 1)}
                       for k in index.get(c, [])):
            if key == (sid, chunk) or key not in starts:
                continue
            hits = [(b, ob) for b in boxes for ob, _ in starts[key] if boxes_overlap(b, ob)]
            if hits:
                if skipped and all((key[0], tuple(ob)) in skipped for _b, ob in hits):
                    suppressed[key[0]] += 1
                else:
                    overlaps[key[0]] += 1
        report.append({"id": sid, "chunk": list(chunk), "box": [x0, y0, z0, x1, y1, z1], "size": [x1 - x0 + 1, y1 - y0 + 1, z1 - z0 + 1],
                       "pieces": len(pieces), "npc_pieces": npc_pieces, "templates": dict(names), "overlaps": dict(overlaps), "suppressed": dict(suppressed), "npcs": [], "loot": {}, "chests": 0,
                       "_pieces": pieces})
    by_chunk = collections.defaultdict(list)
    for v in report:
        b = v["box"]
        for cx in range(b[0] >> 4, (b[3] >> 4) + 1):
            for cz in range(b[2] >> 4, (b[5] >> 4) + 1):
                by_chunk[(cx, cz)].append(v)
    for _rx, _rz, path in WR.list_regions(rdir):
        for _lx, _lz, root in WR.iter_chunks(path):
            for v in by_chunk.get((int(root.get("xPos", 0)), int(root.get("zPos", 0))), []):
                b = v["box"]
                for be in root.get("block_entities", []) or []:
                    x, y, z = int(be["x"]), int(be["y"]), int(be["z"])
                    if b[0] <= x <= b[3] and b[1] <= y <= b[4] and b[2] <= z <= b[5] and be.get("LootTable"):
                        v["chests"] += 1
                        v["loot"][be["LootTable"]] = v["loot"].get(be["LootTable"], 0) + 1
    edir = os.path.join(world, "entities")
    if os.path.isdir(edir):
        for _rx, _rz, path in WR.list_regions(edir):
            for _lx, _lz, root in WR.iter_chunks(path):
                pos = root.get("Position", [0, 0])
                for v in by_chunk.get((int(pos[0]), int(pos[1])), []):
                    b = v["box"]
                    for e in root.get("Entities", []) or []:
                        p = e.get("Pos")
                        if not p or not (b[0] - 2 <= p[0] <= b[3] + 3 and b[1] - 8 <= p[1] <= b[4] + 16 and b[2] - 2 <= p[2] <= b[5] + 3):
                            continue
                        if "EasyNPCVersion" not in e and not str(e.get("id", "")).startswith("easy_npc:"):
                            continue
                        offers = e.get("Offers") or {}
                        recipes = offers.get("Recipes")
                        if isinstance(recipes, dict):
                            recipes = recipes.get("Recipes")
                        v["npcs"].append({"name": text_of(e.get("CustomName", e.get("Name", "?"))), "id": e.get("id"), "pos": [int(p[0]), int(p[1]), int(p[2])],
                                          "trades": len(recipes) if isinstance(recipes, list) else 0, "owner": "Owner" in e,
                                          "invulnerable": bool(e.get("Invulnerable"))})
    # do the NPCs stand on something, in free space? (a block under their feet, air at their feet and head)
    reader = L.WorldReader(world)
    for v in report:
        if trees:
            v["vegetation"] = vegetation(reader, v["_pieces"])
        del v["_pieces"]
        for n in v["npcs"]:
            x, y, z = n["pos"]
            arr, pal = reader.box(x, y - 8, z, x, y + 1, z)         # column from 8 below the NPC's feet to its head
            col = [pal[int(arr[0, i, 0])][0] for i in range(arr.shape[1])]
            free = lambda b: b in ("minecraft:air", "minecraft:cave_air") or "carpet" in b or b.startswith("tfc:plant/")
            head, feet = col[9], col[8]
            drop = 0
            while drop < 8 and free(col[7 - drop]):
                drop += 1
            n["floor"] = col[7 - drop] if drop < 8 else "?"
            n["drop"] = drop                                     # air cells between its feet and what it would stand on (it falls that far when the chunk ticks)
            n["standing"] = drop == 0 and free(feet) and free(head)
    return report


def summary(report):
    by = collections.defaultdict(list)
    for v in report:
        by[v["id"].replace("pack:village/", "")].append(v)
    rows = []
    for k, vs in sorted(by.items()):
        n = len(vs)
        ov = collections.Counter()
        for v in vs:
            ov.update(v["overlaps"])
        rows.append({"village": k, "count": n, "pieces": round(sum(v["pieces"] for v in vs) / n, 1), "npc_pieces": round(sum(v["npc_pieces"] for v in vs) / n, 1),
                     "npcs": round(sum(len(v["npcs"]) for v in vs) / n, 1), "npcs_dropping": sum(1 for v in vs for x in v["npcs"] if x.get("drop", 0) > 0), "max_drop": max([x.get("drop", 0) for v in vs for x in v["npcs"]] or [0]), "size": [round(sum(v["size"][i] for v in vs) / n) for i in (0, 2)],
                     "chests": round(sum(v["chests"] for v in vs) / n, 1), "overlaps": dict(ov),
                     "suppressed": dict(sum((collections.Counter(v.get("suppressed", {})) for v in vs), collections.Counter()))})
        if all("vegetation" in v for v in vs):
            veg = [v["vegetation"] for v in vs]
            rows[-1].update({
                "leaves_in_boxes": sum(x["leaves_in_boxes"] for x in veg), "leaves_over_footprint": sum(x["leaves_over_footprint"] for x in veg),
                "leaves_in_ring": sum(x["leaves_in_ring"] for x in veg), "logs_in_boxes": sum(x["tree_in_boxes"] - x["leaves_in_boxes"] for x in veg),
                "footprint_columns": sum(x["footprint_columns"] for x in veg),
                "woods_per_village": round(sum(len(x["woods"]) for x in veg) / n, 2), "rocks_per_village": round(sum(len(x["rocks"]) for x in veg) / n, 2),
                "villages_over_3_woods": sum(1 for x in veg if len(x["woods"]) > 3), "villages_over_1_rock": sum(1 for x in veg if len(x["rocks"]) > 1)})
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("world")
    ap.add_argument("--out")
    ap.add_argument("--json", action="store_true", help="print the whole report as JSON")
    ap.add_argument("--skipped", nargs="+", help="server logs with `keep-clear: a piece of ... is not placed` lines: those pieces count as suppressed, not as overlaps")
    ap.add_argument("--trees", action="store_true", help="also count tree blocks inside and around each village and the woods and rocks it is built of")
    args = ap.parse_args()
    report = census(args.world, args.trees, skipped_pieces(args.skipped))
    rows = summary(report)
    if args.json:
        print(json.dumps({"villages": report, "summary": rows}, indent=1))
    else:
        for v in report:
            who = [(n["name"], n["trades"]) + (() if n.get("drop", 0) == 0 else ("%d above %s" % (n["drop"], n["floor"]),)) for n in v["npcs"]]
            print(f"{v['id']} chunk {v['chunk']} box {v['box']} {v['size'][0]}x{v['size'][2]} {v['pieces']} pieces ({v['npc_pieces']} NPC spots), "
                  f"NPCs {who}, chests {v['chests']} {v['loot']}, overlaps {v['overlaps']}" + (f", not placed {v['suppressed']}" if v.get("suppressed") else ""))
            if "vegetation" in v:
                g = v["vegetation"]
                print(f"    leaves: {g['leaves_in_boxes']} in the pieces' boxes, {g['leaves_over_footprint']} over the {g['footprint_columns']} footprint columns, "
                      f"{g['leaves_in_ring']} in the 6-block ring; logs (natural and built) in the boxes {g['tree_in_boxes'] - g['leaves_in_boxes']}; woods {g['woods']}; rocks {g['rocks']}")
        print()
        for r in rows:
            print(r)
        if not report:
            print("no village starts in fully generated chunks")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"world": args.world, "villages": report, "summary": rows}, f, indent=1)


if __name__ == "__main__":
    main()
