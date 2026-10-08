"""Undo TFC Structure Compat's additions to the `c:is_*` biome tags, and keep its structures on TFC biomes.

    tools/.venv/Scripts/python tools/structure_mods/biome_tags.py [--compat JAR] [--tfc JAR] [--check]

The compat mod puts TFC's biomes into `#c:is_overworld` and thirteen other `c:is_*` tags so that Moog's Voyager Structures (whose
structure definitions it overrides, 115 of them name those tags in `biomes`) generate in TFC. The pack keeps TFC biomes out of
those tags (docs/design.md: other mods' worldgen keys on them; GregTech's swamp rubber trees spread from 5 to 17 TFC biomes).
This writes, from the two jars:

  kubejs/data/c/tags/worldgen/biome/<tag>.json                        {"values": [], "remove": [what the compat added]}: TFC's own entries stay
  kubejs/data/pack/tags/worldgen/biome/tfc_structures/<name>.json     the biomes each tag held with the compat: what the structures use
  kubejs/data/mvs/worldgen/structure/<id>.json                        the compat's MVS structure files with `biomes` pointed at those

Re-run after updating the compat mod (the generated MVS files are copies of its MIT-licensed data, see licenses/).
"""
import argparse
import glob
import json
import os
import re
import sys
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODS = os.path.join(REPO, "tools", ".server", "mods")
DATA = os.path.join(REPO, "kubejs", "data")
CTAGS = "data/c/tags/worldgen/biome/"
TAGS_NS = "tfc_structures"


def read_json(z, name):
    return json.loads(z.read(name).decode("utf-8"))


def entries(doc):
    out = []
    for v in doc.get("values", []):
        out.append(v["id"] if isinstance(v, dict) else v)
    return out


def resolve(zfile, ref, seen=None):
    """Biome ids a tag reference ('#ns:path') resolves to inside one jar (tags it doesn't hold resolve to nothing)."""
    seen = seen or set()
    if ref in seen:
        return set()
    seen.add(ref)
    ns, path = ref[1:].split(":", 1)
    name = f"data/{ns}/tags/worldgen/biome/{path}.json"
    if name not in zfile.namelist():
        return set()
    out = set()
    for e in entries(read_json(zfile, name)):
        out |= resolve(zfile, e, seen) if e.startswith("#") else {e}
    return out


def write(path, doc):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compat")
    ap.add_argument("--tfc")
    ap.add_argument("--check", action="store_true", help="only report")
    args = ap.parse_args()
    compat_jar = args.compat or (glob.glob(os.path.join(MODS, "tfc_str_compat*.jar")) or [None])[0]
    tfc_jar = args.tfc or (glob.glob(os.path.join(MODS, "TerraFirmaCraft-NeoForge-*.jar")) or [None])[0]
    if not compat_jar or not tfc_jar:
        raise SystemExit("need the compat and TFC jars (run a tool that syncs the test server first)")
    zc, zt = zipfile.ZipFile(compat_jar), zipfile.ZipFile(tfc_jar)

    tags = sorted(n[len(CTAGS):-5] for n in zc.namelist() if n.startswith(CTAGS) and n.endswith(".json"))
    removed, held = {}, {}
    for tag in tags:
        added = set(entries(read_json(zc, CTAGS + tag + ".json")))
        own = set()
        if CTAGS + tag + ".json" in zt.namelist():
            for e in entries(read_json(zt, CTAGS + tag + ".json")):
                own |= resolve(zt, e) if e.startswith("#") else {e}
        removed[tag] = sorted(b for b in added if b.startswith("tfc:") and b not in own)
        held[tag] = sorted((added | own) - {b for b in added | own if not b.startswith("tfc:")})
        print(f"c:{tag}: compat adds {len(added)}, TFC's own {len(own)}, removed {len(removed[tag])}")

    # structure files that name one of those tags in `biomes`
    structs = {}
    for n in zc.namelist():
        if n.startswith("data/mvs/worldgen/structure/") and n.endswith(".json"):
            doc = read_json(zc, n)
            b = doc.get("biomes")
            if isinstance(b, str) and b.startswith("#c:is_") and b[len("#c:"):] in removed:
                structs[n.rsplit("/", 1)[1]] = doc
    print(f"{len(structs)} MVS structure files point at the changed tags")
    if args.check:
        return

    for tag in tags:
        if removed[tag]:
            write(os.path.join(DATA, "c", "tags", "worldgen", "biome", tag + ".json"), {"values": [], "remove": removed[tag]})
    used = set()
    for name, doc in sorted(structs.items()):
        tag = doc["biomes"][len("#c:"):]
        used.add(tag)
        doc = dict(doc)
        doc["biomes"] = f"#pack:{TAGS_NS}/{tag[len('is_'):]}"
        write(os.path.join(DATA, "mvs", "worldgen", "structure", name), doc)
    for tag in sorted(used):
        write(os.path.join(DATA, "pack", "tags", "worldgen", "biome", TAGS_NS, tag[len("is_"):] + ".json"), {"values": held[tag]})
    print("wrote", len(structs), "structures,", len(used), "tfc_structures tags and", sum(1 for t in tags if removed[t]), "remove files")


if __name__ == "__main__":
    sys.exit(main())
