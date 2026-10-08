"""Block census of the structure templates inside the structure mods' jars (no world needed).

Usage: tools/.venv/Scripts/python tools/structure_mods/census.py [--json OUT.json] [--vanilla-only]

Lists, per mod jar and template namespace, how many blocks of each block id its templates hold, so the vanilla ->
TFC table (kubejs/data/pack/pack_world/structure_skin/*.json) can be checked for gaps: any vanilla or foreign
id that the table doesn't map shows up under "unmapped".
"""
import argparse
import collections
import glob
import json
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "structures"))
import nbt  # noqa: E402  (read-only use of the structure generator's NBT reader)

REPO = os.path.dirname(os.path.dirname(HERE))
MODS = os.path.join(REPO, "tools", ".server", "mods")
JARS = ["MoogsVoyagerStructures", "MoogsMissingVillages", "MoogsTemplesReimagined", "t_and_t", "YungsBetterDungeons",
        "YungsBetterMineshafts", "TFCHuts", "tfc_str_compat"]


def census(jar):
    out = collections.defaultdict(collections.Counter)    # template namespace -> block id -> n
    ents = collections.defaultdict(collections.Counter)
    with zipfile.ZipFile(jar) as z:
        for name in z.namelist():
            parts = name.split("/")
            if len(parts) < 4 or parts[0] != "data" or parts[2] != "structure" or not name.endswith(".nbt"):
                continue
            root = nbt.loads(z.read(name))
            palette = [p["Name"] for p in root["palette"]]
            for b in root["blocks"]:
                out[parts[1]][palette[b["state"]]] += 1
            for e in root.get("entities", []):
                ents[parts[1]][e["nbt"].get("id", "?")] += 1
    return out, ents


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    ap.add_argument("--vanilla-only", action="store_true")
    args = ap.parse_args()
    report = {}
    for key in JARS:
        for jar in glob.glob(os.path.join(MODS, key + "*.jar")):
            blocks, ents = census(jar)
            for ns in blocks:
                report[f"{os.path.basename(jar)}:{ns}"] = {"blocks": dict(blocks[ns].most_common()), "entities": dict(ents[ns].most_common())}
    if args.json:
        with open(args.json, "w") as f:
            json.dump(report, f, indent=1)
    total = collections.Counter()
    for k, v in report.items():
        n = sum(v["blocks"].values())
        van = sum(c for b, c in v["blocks"].items() if b.startswith("minecraft:") and b not in ("minecraft:air", "minecraft:jigsaw", "minecraft:structure_void"))
        print(f"{k}: {n} blocks, {van} vanilla (non-air)")
        for b, c in v["blocks"].items():
            if not args.vanilla_only or b.startswith("minecraft:"):
                total[b] += c
    print()
    for b, c in total.most_common():
        print(c, b)


if __name__ == "__main__":
    main()
