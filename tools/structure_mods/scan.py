"""Read a generated world (Anvil files) for what the structure mods left in it: starts, containers and loot tables, entities.

Usage: tools/.venv/Scripts/python tools/structure_mods/scan.py WORLD_DIR [--out OUT.json] [--skip pack,minecraft]

Finds every structure start in the chunks' `structures.starts` (piece boxes included), then counts, inside those boxes:
block entities by type, chests and other containers by loot table (and the loot tables used), and from `entities/`: entity types,
villagers by profession and level and whether they carry baked-in offers, and what armor stands, item frames and mobs wear
or hold (iron, diamond and other deny-listed gear is flagged: tools/structures/catalogue.json `loot_caps.deny`).
Structures of the namespaces in --skip (default: the pack's own, `pack`) are ignored.
"""
import argparse
import collections
import json
import os
import re
import sys
import zlib

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)
from worldview import nbt as WN  # noqa: E402
from worldview import region as WR  # noqa: E402

CATALOGUE = os.path.join(TOOLS, "structures", "catalogue.json")


def starts_of(root):
    """[(structure id, start chunk (x, z), [boxes])] of the structures that *start* in this chunk."""
    out = []
    for sid, st in ((root.get("structures") or {}).get("starts") or {}).items():
        if not isinstance(st, dict) or st.get("id") in (None, "INVALID"):
            continue
        boxes = []
        for ch in st.get("Children", []):
            bb = ch.get("BB")
            if bb is not None and len(bb) == 6:
                boxes.append([int(v) for v in bb])
        out.append((st["id"], (int(st["ChunkX"]), int(st["ChunkZ"])), boxes))
    return out


def inside(boxes, x, y, z, margin=0):
    for b in boxes:
        if b[0] - margin <= x <= b[3] + margin and b[1] - margin <= y <= b[4] + margin and b[2] - margin <= z <= b[5] + margin:
            return True
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("world")
    ap.add_argument("--out")
    ap.add_argument("--skip", default="pack,minecraft")
    args = ap.parse_args()
    skip = set(args.skip.split(","))
    deny = [re.compile(p) for p in json.load(open(CATALOGUE, encoding="utf-8"))["loot_caps"]["deny"]]
    rdir = os.path.join(args.world, "region")

    starts = {}            # (id, chunk) -> boxes
    full_starts = set()    # those whose start chunk was generated in full (Chunky's square), not just a neighbour kept for it
    for _rx, _rz, path in WR.list_regions(rdir):
        for _lx, _lz, root in WR.iter_chunks(path):
            full = str(root.get("Status", "")).endswith("full")
            for sid, chunk, boxes in starts_of(root):
                if sid.split(":")[0] in skip:
                    continue
                starts[(sid, chunk)] = boxes
                if full:
                    full_starts.add((sid, chunk))
    by_id = collections.Counter(sid for sid, _ in full_starts)
    print(f"{len(full_starts)} structure starts in fully generated chunks ({len(starts)} counting the border chunks) of {len(by_id)} kinds")

    # one box list per start, indexed by region of the world for the lookups below
    index = collections.defaultdict(list)       # chunk (x, z) -> [(sid, boxes)] for every chunk any piece box touches
    for (sid, _chunk), boxes in starts.items():
        touched = set()
        for b in boxes:
            for cx in range(b[0] >> 4, (b[3] >> 4) + 1):
                for cz in range(b[2] >> 4, (b[5] >> 4) + 1):
                    touched.add((cx, cz))
        for c in touched:
            index[c].append((sid, boxes))

    be_types = collections.Counter()
    loot = collections.Counter()
    loot_by_ns = collections.defaultdict(collections.Counter)
    containers = collections.Counter()
    for _rx, _rz, path in WR.list_regions(rdir):
        for lx, lz, root in WR.iter_chunks(path):
            cx, cz = int(root.get("xPos", 0)), int(root.get("zPos", 0))
            owners = index.get((cx, cz))
            if not owners:
                continue
            for be in root.get("block_entities", []) or []:
                x, y, z = int(be["x"]), int(be["y"]), int(be["z"])
                owner = next((sid for sid, boxes in owners if inside(boxes, x, y, z)), None)
                if owner is None:
                    continue
                ns = owner.split(":")[0]
                bid = be.get("id", "?")
                be_types[f"{ns}|{bid}"] += 1
                table = be.get("LootTable")
                if table:
                    loot[table] += 1
                    loot_by_ns[ns][table] += 1
                if "Items" in be or table:
                    containers[f"{ns}|{bid}|{'loot' if table else 'items' if be.get('Items') else 'empty'}"] += 1
    print("block entities in structures:", dict(be_types.most_common(12)))
    print("loot tables in use:", len(loot), "; containers:", dict(containers.most_common(12)))

    ents = collections.Counter()
    villagers = collections.Counter()
    equip = collections.Counter()
    flagged = collections.Counter()
    edir = os.path.join(args.world, "entities")
    if os.path.isdir(edir):
        for _rx, _rz, path in WR.list_regions(edir):
            for _lx, _lz, root in WR.iter_chunks(path):
                owners = index.get((int(root.get("Position", [0, 0])[0]), int(root.get("Position", [0, 0])[1])))
                if not owners:
                    continue
                for e in root.get("Entities", []) or []:
                    pos = e.get("Pos")
                    if not pos:
                        continue
                    x, y, z = float(pos[0]), float(pos[1]), float(pos[2])
                    owner = next((sid for sid, boxes in owners if inside(boxes, x, y, z, 3)), None)
                    if owner is None:
                        continue
                    ns = owner.split(":")[0]
                    eid = e.get("id", "?")
                    ents[f"{ns}|{eid}"] += 1
                    if eid in ("minecraft:villager", "minecraft:wandering_trader"):
                        vd = e.get("VillagerData") or {}
                        villagers[f"{ns}|{eid}|{vd.get('profession', '-')}|{vd.get('level', '-')}|offers={'Offers' in e}"] += 1
                    items = []
                    for key in ("ArmorItems", "HandItems"):
                        for it in e.get(key, []) or []:
                            if it and it.get("id"):
                                items.append(it["id"])
                    for key in ("Item", "Inventory"):
                        v = e.get(key)
                        for it in ([v] if isinstance(v, dict) else v or []):
                            if it and it.get("id"):
                                items.append(it["id"])
                    for it in items:
                        equip[f"{ns}|{eid}|{it}"] += 1
                        if any(d.search(it) for d in deny):
                            flagged[f"{ns}|{eid}|{it}"] += 1
    print("entities:", dict(ents.most_common(15)))
    print("villagers:", dict(villagers.most_common(15)))
    print("deny-listed equipment on entities:", dict(flagged.most_common(15)))
    result = {"world": args.world, "starts": dict(by_id), "block_entities": dict(be_types), "containers": dict(containers),
              "loot_tables": dict(loot), "loot_by_namespace": {k: dict(v) for k, v in loot_by_ns.items()}, "entities": dict(ents),
              "villagers": dict(villagers), "equipment": dict(equip), "equipment_denied": dict(flagged)}
    if args.out:
        with open(args.out, "w") as f:
            json.dump(result, f, indent=1)


if __name__ == "__main__":
    main()
