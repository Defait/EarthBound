"""The pack's villages in a generated world (docs/lived-in.md, *Settlements*): what stands there, who lives there, what they overlap.

Usage: tools/.venv/Scripts/python tools/structure_mods/village_census.py WORLD_DIR [--out OUT.json] [--json]

Reads the Anvil files of WORLD_DIR (a world made by tools/pregen.py, or a test world) without a server. For every start of a
`pack:village/<culture>_<variant>` structure in a fully generated chunk it reports: where (chunk, block box and size), how many pieces and of
which buildings, how many of them are NPC spots, the Easy NPCs found inside its box (name, trades), the loot tables of its containers, and
every other structure whose pieces overlap its pieces (by namespace: Towns and Towers, Moog's, TFC Huts, the pack's own ruins, another village).
A summary per culture closes the report: villages, pieces per village, NPCs per village, overlaps.
"""
import argparse
import collections
import json
import os
import sys

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


def census(world):
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
        for key in set(k for c in {(cx, cz) for b in boxes for cx in range(b[0] >> 4, (b[3] >> 4) + 1) for cz in range(b[2] >> 4, (b[5] >> 4) + 1)}
                       for k in index.get(c, [])):
            if key == (sid, chunk) or key not in starts:
                continue
            if any(boxes_overlap(b, ob) for b in boxes for ob, _ in starts[key]):
                overlaps[key[0]] += 1
        report.append({"id": sid, "chunk": list(chunk), "box": [x0, y0, z0, x1, y1, z1], "size": [x1 - x0 + 1, y1 - y0 + 1, z1 - z0 + 1],
                       "pieces": len(pieces), "npc_pieces": npc_pieces, "templates": dict(names), "overlaps": dict(overlaps), "npcs": [], "loot": {}, "chests": 0})
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
                     "chests": round(sum(v["chests"] for v in vs) / n, 1), "overlaps": dict(ov)})
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("world")
    ap.add_argument("--out")
    ap.add_argument("--json", action="store_true", help="print the whole report as JSON")
    args = ap.parse_args()
    report = census(args.world)
    rows = summary(report)
    if args.json:
        print(json.dumps({"villages": report, "summary": rows}, indent=1))
    else:
        for v in report:
            who = [(n["name"], n["trades"]) + (() if n.get("drop", 0) == 0 else ("%d above %s" % (n["drop"], n["floor"]),)) for n in v["npcs"]]
            print(f"{v['id']} chunk {v['chunk']} box {v['box']} {v['size'][0]}x{v['size'][2]} {v['pieces']} pieces ({v['npc_pieces']} NPC spots), "
                  f"NPCs {who}, chests {v['chests']} {v['loot']}, overlaps {v['overlaps']}")
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
