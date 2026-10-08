"""Summarise tools/.data/structure_mods/<place>-<before|after>.json (from measure.py): what the structure skin changed.

Usage: tools/.venv/Scripts/python tools/structure_mods/report.py [--places paris steppe ...] [--json OUT]

Per structure namespace (towns_and_towers, mvs, mmv, mtr, betterdungeons, bettermineshafts, tfchuts), summed over the places:
blocks the structures wrote (without air), the share that is vanilla, rough alloy rock (raw/cobble/hardened/mossy/loose of andesite,
basalt, dacite, rhyolite or diorite), TFC iron-age metal blocks, ground columns and floating ones (the lowest solid block of a
column two or more blocks above the terrain), the foundation blocks added, and chunks per second. "before" is the dry-run world
(the skin only measuring), "after" the same area with the skin on.
"""
import argparse
import collections
import json
import os
import re
import sys

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)
from mclib.paths import DATA_DIR  # noqa: E402

OUT = os.path.join(DATA_DIR, "structure_mods")
ROUGH = re.compile(r"^tfc:rock/(raw|hardened|cobble|mossy_cobble|loose|mossy_loose)/(andesite|basalt|dacite|rhyolite|diorite)(_stairs|_slab|_wall)?$")
IRON_AGE = re.compile(r"^tfc:metal/[a-z_]+/(wrought_iron|cast_iron|pig_iron|steel|black_steel|blue_steel|red_steel)(_[a-z]+)?$|^tfc:metal/(block|anvil|lamp|chain|bars|grate|trapdoor)/(wrought_iron|cast_iron|steel|black_steel|blue_steel|red_steel)")
# vanilla blocks TFC's own world has (so they don't count as the structures' vanilla leftovers)
NATURAL = {"minecraft:water", "minecraft:lava", "minecraft:bedrock", "minecraft:ice", "minecraft:snow", "minecraft:snow_block",
           "minecraft:packed_ice", "minecraft:blue_ice", "minecraft:cave_air", "minecraft:air", "minecraft:void_air"}


def load(place, mode):
    p = os.path.join(OUT, f"{place}-{mode}.json")
    return json.load(open(p)) if os.path.exists(p) else None


# floating by design: they are not a placement failure
FLOATING_BY_DESIGN = {"mvs:floating_islands", "mvs:large_floating_island"}


def namespace(structure_id):
    return structure_id.split(":", 1)[0]


def summarise(docs, stage):
    """docs: [measure.py outputs]; stage 'before'|'after' -> {namespace: {...}}"""
    out = collections.defaultdict(lambda: collections.Counter())
    for doc in docs:
        for sid, m in doc["metrics"].items():
            ns = namespace(sid)
            c = out[ns]
            blocks = m[stage]
            c["starts"] += 0
            c["chunks"] += m["chunks"]
            if sid not in FLOATING_BY_DESIGN:
                c["columns"] += m["columns"]
            if sid not in FLOATING_BY_DESIGN:
                c["floating"] += m["floating_" + stage]
            c["foundation"] += m["foundation"] if stage == "after" else 0
            for b, n in blocks.items():
                c["blocks"] += n
                if b.startswith("minecraft:") and b not in NATURAL:
                    c["vanilla"] += n
                if ROUGH.match(b):
                    c["alloy"] += n
                if IRON_AGE.match(b):
                    c["iron_age"] += n
                if b.startswith("tfc:"):
                    c["tfc"] += n
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--places", nargs="*", default=["paris", "steppe", "cairo", "stockholm"])
    ap.add_argument("--json")
    ap.add_argument("--markdown", action="store_true", help="print the table as markdown (for docs/lived-in.md)")
    args = ap.parse_args()
    before = [d for d in (load(p, "before") for p in args.places) if d]
    after = [d for d in (load(p, "after") for p in args.places) if d]
    if not after:
        raise SystemExit("no after-runs found in " + OUT)
    result = {"places": args.places}
    # an "after" run also records what the structures wrote before the skin ("before" blocks, floating before the foundation), measured
    # in the same run with the same definitions; the dry-run worlds only add the generation speed without the skin
    b = summarise(after, "before")
    a = summarise(after, "after")
    print(f"{'namespace':18} {'blocks':>9} {'vanilla before':>15} {'after':>8} {'alloy before':>13} {'after':>6} {'iron-age b':>10} {'a':>5} {'columns':>8} {'floating b':>10} {'a':>6} {'foundation':>10}")
    for ns in sorted(a):
        x = a[ns]
        y = b.get(ns, collections.Counter()) if b else collections.Counter()
        pct = lambda n, d: f"{100 * n / max(d, 1):5.1f}%"
        print(f"{ns:18} {x['blocks']:9} {y['vanilla']:7} {pct(y['vanilla'], y['blocks']):>7} {x['vanilla']:3}{pct(x['vanilla'], x['blocks']):>7}"
              f" {y['alloy']:8} {x['alloy']:6} {y['iron_age']:10} {x['iron_age']:5} {x['columns']:8} {y['floating']:10} {x['floating']:6} {x['foundation']:10}")
        result[ns] = {"blocks_after": x["blocks"], "blocks_before": y["blocks"], "vanilla_before": y["vanilla"], "vanilla_after": x["vanilla"],
                      "alloy_before": y["alloy"], "alloy_after": x["alloy"], "iron_age_before": y["iron_age"], "iron_age_after": x["iron_age"],
                      "columns": x["columns"], "floating_before": y["floating"], "floating_after": x["floating"], "foundation": x["foundation"]}
    if args.markdown:
        print()
        print("| structures | blocks written | vanilla before | vanilla after | rough alloy rock before / after | iron-age metal blocks before / after | ground columns | floating before / after | foundation blocks |")
        print("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        order = ["towns_and_towers", "mvs", "mmv", "mtr", "betterdungeons", "bettermineshafts", "tfchuts"]
        for ns in [n for n in order if n in a] + [n for n in sorted(a) if n not in order]:
            x, y = a[ns], (b.get(ns) if b else None) or collections.Counter()
            pct = lambda n, d: f"{100 * n / max(d, 1):.1f}%"
            print(f"| {ns} | {y['blocks'] or x['blocks']:,} | {pct(y['vanilla'], y['blocks'])} | {pct(x['vanilla'], x['blocks'])} | {y['alloy']:,} / {x['alloy']:,} | {y['iron_age']:,} / {x['iron_age']:,} | {x['columns']:,} | {y['floating']:,} / {x['floating']:,} | {x['foundation']:,} |")
        print()
    for label, docs in (("before", before), ("after", after)):
        if docs:
            rates = [d["chunks_per_second"] for d in docs]
            listing = ", ".join(d["place"] + " " + str(d["chunks_per_second"]) for d in docs)
            print(f"chunks/s {label}: {listing}  mean {sum(rates) / len(rates):.1f}")
            result["cps_" + label] = rates
    left = collections.Counter()
    for d in after:
        for sid, m in d["metrics"].items():
            for blk, n in m["after"].items():
                if blk.startswith("minecraft:") and blk not in NATURAL:
                    left[blk] += n
    print("vanilla blocks left after the skin (top 25):", ", ".join(f"{k[10:]} {v}" for k, v in left.most_common(25)))
    unmapped = collections.Counter()
    for d in after:
        for blk, n in d.get("unmapped", {}).items():
            if not blk.startswith("tfc:"):
                unmapped[blk] += n
    if unmapped:
        print("blocks written with no rule that aren't TFC:", dict(unmapped.most_common(20)))
    if args.json:
        json.dump(result, open(args.json, "w"), indent=1)


if __name__ == "__main__":
    main()
