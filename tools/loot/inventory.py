"""Static inventory of the chest loot tables the pack's mods can put in a world, read from the mod jars (no server).

Usage (from the repo root):
    tools/.venv/Scripts/python tools/loot/inventory.py [--mods DIR] [--json FILE] [--md FILE] [--used FILE]

Where a loot table id can come from:
  defined      a loot table JSON in a mod jar (or vanilla's server jar) whose type is not block/entity: chest, archaeology,
               untyped. GregTech's `gtceu:chests/extra/*` are listed as "gregtech" because its global loot modifiers add them
               to vanilla tables (see tools/loot/gen.py, `neoforge/loot_modifiers/global_loot_modifiers.json`).
  template     a `LootTable` tag inside a structure template (.nbt, gzip NBT) in a jar: chests, barrels, minecart entities,
               brushable sand/gravel, decorated pots, dispensers; any block entity or entity, found recursively.
  json         a `loot_table`/`LootTable` key, or any string that is a known loot table id, in a jar's data JSON (structure,
               template pool, processor list, feature, ...).
  class        a string constant in a mod's classes (YUNG's Better Dungeons and Mineshafts build some pieces in code) that is
               a known table id, or the path of one in that mod's namespace. Constants that look like loot tables but are not
               known ones are listed under "unresolved".
  used         tables seen in generated test worlds (the settlement trial's loot_tables_used.json), when --used is given.
Importable: scan() returns the dict that the JSON file holds.
"""
import argparse
import glob
import io
import json
import os
import re
import struct
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
REPO = os.path.dirname(TOOLS)
sys.path.insert(0, os.path.join(TOOLS, "structures"))

import nbt as N  # noqa: E402

MODS_DIR = os.path.join(TOOLS, ".server", "mods")
# Mods whose structures or classes can put a loot table into the world (others only add block drops).
STRUCTURE_MODS = {
    "tfc_str_compat": "tfc_str_compat-*.jar", "betterdungeons": "YungsBetterDungeons-*.jar",
    "bettermineshafts": "YungsBetterMineshafts-*.jar", "mvs": "MoogsVoyagerStructures-*.jar",
    "mmv": "MoogsMissingVillages-*.jar", "mtr": "MoogsTemplesReimagined-*.jar", "t_and_t": "t_and_t-*.jar",
    "structurelib": "MoogsStructureLib-*.jar", "yungsapi": "YungsApi-*.jar", "tfchuts": "TFCHuts-*.jar",
    "cristellib": "cristellib-*.jar", "pack_world": "pack_world-*.jar", "lootr": "lootr-*.jar",
}
VANILLA_JAR_GLOB = os.path.join(TOOLS, ".server", "libraries", "net", "minecraft", "server", "*", "server-*-extra.jar")
LOOT_PATH = re.compile(r"^data/([^/]+)/loot_tables?/(.+)\.json$")
SKIP_TYPES = {"minecraft:block", "minecraft:entity", "minecraft:empty"}
ID_RE = re.compile(r"^[a-z0-9_.\-]+:[a-z0-9_/.\-]+$")
JSON_DIRS = re.compile(r"^data/[^/]+/(worldgen|structure|neoforge|forge|tfc|pools|jigsaw|loot_modifiers|advancement|functions?)/.*\.json$")


def walk_jar(zf, label):
    """Yield (label, zipfile) for a jar and every JarJar jar nested in it."""
    yield label, zf
    for n in zf.namelist():
        if n.startswith("META-INF/jarjar/") and n.endswith(".jar"):
            yield from walk_jar(zipfile.ZipFile(io.BytesIO(zf.read(n))), label + ">" + os.path.basename(n))


def cp_strings(data):
    """The Utf8 constants of a class file, and the (class, name) of every field it reads from BuiltInLootTables."""
    p = 8
    n = struct.unpack(">H", data[p:p + 2])[0]
    p += 2
    utf = {}
    classes = {}
    nat = {}
    fields = []
    i = 1
    while i < n:
        t = data[p]
        p += 1
        if t == 1:
            ln = struct.unpack(">H", data[p:p + 2])[0]
            p += 2
            utf[i] = data[p:p + ln].decode("utf-8", "replace")
            p += ln
        elif t in (3, 4):
            p += 4
        elif t in (5, 6):
            p += 8
            i += 1
        elif t == 7:
            classes[i] = struct.unpack(">H", data[p:p + 2])[0]
            p += 2
        elif t in (8, 16, 19, 20):
            p += 2
        elif t == 9:
            fields.append(struct.unpack(">HH", data[p:p + 4]))
            p += 4
        elif t == 12:
            nat[i] = struct.unpack(">H", data[p:p + 2])[0]
            p += 4
        elif t in (10, 11, 17, 18):
            p += 4
        elif t == 15:
            p += 3
        else:
            raise ValueError(f"constant pool tag {t}")
        i += 1
    refs = []
    for ci, nti in fields:
        cn = utf.get(classes.get(ci, 0), "")
        if cn.endswith("BuiltInLootTables"):
            refs.append(utf.get(nat.get(nti, 0), ""))
    return list(utf.values()), refs


LOOT_KEYS = ("LootTable", "loot_table", "ominous_loot_table")
# Items = containers (chests, barrels, furnaces), Item/item = item frames, lecterns, item entities, ArmorItems/HandItems = armor stands and mobs
ITEM_KEYS = ("Items", "Item", "item", "ArmorItems", "HandItems", "SaddleItem", "Inventory", "RecordItem", "Book")


def loot_tags(tag, path=""):
    """Every loot table string in an NBT value (block entities, entities, vault configs), with where it sits."""
    if isinstance(tag, dict):
        for k, v in tag.items():
            if k in LOOT_KEYS and isinstance(v, str):
                yield v, path
            else:
                yield from loot_tags(v, path + "/" + k)
    elif isinstance(tag, list):
        for v in tag:
            yield from loot_tags(v, path)


def baked_items(tag, key=""):
    """Item stacks written into a template (chest Items, item frames, armor stands, ...): they bypass loot tables."""
    if isinstance(tag, dict):
        if key in ITEM_KEYS and isinstance(tag.get("id"), str) and ("count" in tag or "Count" in tag):
            yield tag["id"], key
        for k, v in tag.items():
            yield from baked_items(v, k)
    elif isinstance(tag, list):
        for v in tag:
            yield from baked_items(v, key)


def walk_json(v):
    """Every string value of a JSON document with its key."""
    if isinstance(v, dict):
        for k, x in v.items():
            if isinstance(x, str):
                yield k, x
            else:
                yield from walk_json(x)
    elif isinstance(v, list):
        for x in v:
            if isinstance(x, str):
                yield None, x
            else:
                yield from walk_json(x)


def short_mod(jar_label):
    base = os.path.basename(jar_label.split(">")[0])
    for mod, pat in STRUCTURE_MODS.items():
        if glob.fnmatch.fnmatch(base, pat):
            return mod
    return re.sub(r"[-_.]?\d.*$", "", base).lower() or base


def scan(mods_dir=MODS_DIR, used_file=None):
    tables = {}

    def entry(tid):
        return tables.setdefault(tid, {"defined_by": [], "type": None, "templates": {}, "json": {}, "classes": {}, "gregtech_adds_to": []})

    jars = []
    vanilla = glob.glob(VANILLA_JAR_GLOB)
    if vanilla:
        jars.append(("minecraft", vanilla[0]))
    for jar in sorted(glob.glob(os.path.join(mods_dir, "*.jar"))):
        jars.append((short_mod(jar), jar))

    # pass 1: definitions
    opened = []
    for mod, jar in jars:
        z = zipfile.ZipFile(jar)
        for label, zf in walk_jar(z, os.path.basename(jar)):
            opened.append((mod, label, zf))
            for n in zf.namelist():
                m = LOOT_PATH.match(n)
                if not m:
                    continue
                try:
                    doc = json.loads(zf.read(n))
                except ValueError:
                    continue
                t = doc.get("type", "(untyped)")
                if t in SKIP_TYPES:
                    continue
                e = entry(f"{m.group(1)}:{m.group(2)}")
                e["type"] = t
                e["defined_by"].append(mod if mod != "minecraft" else "vanilla")
    known = set(tables)
    by_path = {}
    for tid in known:
        by_path.setdefault(tid.split(":", 1)[1], set()).add(tid)

    # BuiltInLootTables.<FIELD> -> the vanilla table ids it can name (field names are the path after chests/ in upper case)
    builtin = {}
    for tid in known:
        if tid.startswith("minecraft:"):
            rest = tid.split(":", 1)[1].split("/", 1)[1]
            for key in {rest.replace("/", "_"), rest.rsplit("/", 1)[-1]}:
                builtin.setdefault(key.upper(), set()).add(tid)

    # pass 2: users
    unresolved = {}
    baked = {}
    special = {}
    for mod, label, zf in opened:
        if mod not in STRUCTURE_MODS and mod != "minecraft":
            continue
        for n in zf.namelist():
            if n.endswith(".nbt") and re.match(r"^data/[^/]+/structures?/", n):
                try:
                    root = N.loads(zf.read(n))
                except Exception:
                    continue
                for tid, where in loot_tags(root):
                    entry(tid)["templates"].setdefault(mod, []).append(f"{n[5:-4]} {where}".strip())
                for iid, key in baked_items(root):
                    baked.setdefault(iid, {}).setdefault(mod, {}).setdefault(key, set()).add(n[5:-4])
                for b in root.get("palette", []):
                    if b.get("Name") in ("minecraft:vault", "minecraft:trial_spawner", "minecraft:spawner"):
                        special.setdefault(b["Name"], {}).setdefault(mod, set()).add(n[5:-4])
            elif n.endswith(".json") and not LOOT_PATH.match(n) and JSON_DIRS.match(n):
                try:
                    doc = json.loads(zf.read(n))
                except ValueError:
                    continue
                for k, s in walk_json(doc):
                    if (k in ("loot_table", "LootTable") and isinstance(s, str)) or s in known:
                        if ID_RE.match(s):
                            entry(s)["json"].setdefault(mod, []).append(n[5:-5])
            elif n.endswith(".class") and mod != "lootr":
                try:
                    strings, refs = cp_strings(zf.read(n))
                except Exception:
                    continue
                cls = n.rsplit("/", 1)[-1][:-6]
                for field in refs:
                    for tid in builtin.get(field, ()):
                        entry(tid)["classes"].setdefault(mod, []).append(cls)
                for s in strings:
                    if s in known and ID_RE.match(s):
                        entry(s)["classes"].setdefault(mod, []).append(cls)
                    elif s in by_path and "/" in s:
                        for tid in by_path[s]:
                            entry(tid)["classes"].setdefault(mod, []).append(cls)
                    elif re.search(r"(^|/)chests/|loot_table", s) and not re.search(r"[A-Z]\w*\.java|^\(|;|\s", s) and len(s) < 100:
                        if s not in by_path and s not in known:
                            unresolved.setdefault(s, set()).add(f"{mod}:{cls}")

    # global loot modifier lists (neoforge:loot_modifiers/global_loot_modifiers.json of every jar), and which tables GregTech's add to
    glm = {}
    for mod, label, zf in opened:
        for n in zf.namelist():
            if n == "data/neoforge/loot_modifiers/global_loot_modifiers.json":
                doc = json.loads(zf.read(n))
                glm[label] = {"replace": bool(doc.get("replace")), "entries": doc.get("entries", [])}
        for n in zf.namelist():
            if re.match(r"^data/[^/]+/loot_modifiers/chests/.+\.json$", n):
                doc = json.loads(zf.read(n))
                for c in doc.get("conditions", []):
                    if c.get("condition") == "neoforge:loot_table_id":
                        entry(c["loot_table_id"])["gregtech_adds_to"].append(doc.get("table"))
                        entry(doc["table"])["defined_by"] = sorted(set(entry(doc["table"])["defined_by"]) | {"gregtech"})

    used = {}
    if used_file and os.path.exists(used_file):
        used = json.load(open(used_file, encoding="utf-8")).get("tables", {})
        for tid, count in used.items():
            entry(tid)["seen_in_worlds"] = count

    for e in tables.values():
        for k in ("templates", "json", "classes"):
            e[k] = {m: sorted(set(v)) for m, v in sorted(e[k].items())}
        e["defined_by"] = sorted(set(e["defined_by"]))
    return {"tables": dict(sorted(tables.items())), "unresolved": {k: sorted(v) for k, v in sorted(unresolved.items())},
            "global_loot_modifiers": glm,
            "baked_items": {i: {m: {k: len(t) for k, t in sorted(ks.items())} for m, ks in sorted(v.items())} for i, v in sorted(baked.items())},
            "special_blocks": {b: {m: len(t) for m, t in sorted(v.items())} for b, v in sorted(special.items())}}


CACHE = os.path.join(TOOLS, ".data", "loot", "inventory.json")


def cached(mods_dir=MODS_DIR):
    """scan(), kept in tools/.data/loot/inventory.json until a jar changes (a scan reads every structure template: about a minute)."""
    jars = sorted(glob.glob(os.path.join(mods_dir, "*.jar"))) + glob.glob(VANILLA_JAR_GLOB)
    key = [[os.path.basename(j), os.path.getsize(j), int(os.path.getmtime(j))] for j in jars]
    if os.path.exists(CACHE):
        try:
            with open(CACHE, encoding="utf-8") as f:
                doc = json.load(f)
            if doc.get("key") == key:
                return doc["inventory"]
        except ValueError:
            pass
    inv = scan(mods_dir)
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump({"key": key, "inventory": inv}, f)
    return inv


def sources_of(e):
    s = []
    if e["defined_by"]:
        s.append("jar data")
    if "gregtech" in e["defined_by"]:
        s = ["GregTech-injected"]
    if e["templates"]:
        s.append("template")
    if e["json"]:
        s.append("worldgen json")
    if e["classes"]:
        s.append("class")
    if e.get("seen_in_worlds"):
        s.append("seen in worlds")
    if "vanilla" in e["defined_by"]:
        s.insert(0, "vanilla")
    return s


def users_of(e):
    u = set(e["templates"]) | set(e["json"]) | set(e["classes"])
    return sorted(u)


def to_markdown(inv):
    rows = ["| table | type | defined by | used by (template / json / class) | seen in worlds |", "|---|---|---|---|---|"]
    for tid, e in inv["tables"].items():
        used = []
        for k, label in (("templates", "tpl"), ("json", "json"), ("classes", "cls")):
            for m, v in e[k].items():
                used.append(f"{m} {label} x{len(v)}")
        rows.append(f"| `{tid}` | {e['type'] or '-'} | {', '.join(e['defined_by']) or '(none: referenced only)'} | {'; '.join(used) or '-'} | {e.get('seen_in_worlds', '')} |")
    return "\n".join(rows) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mods", default=MODS_DIR)
    ap.add_argument("--json", help="write the inventory here")
    ap.add_argument("--md", help="write a table here")
    ap.add_argument("--used", help="loot_tables_used.json of the settlement trial (tables seen in generated worlds)")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    inv = scan(args.mods, args.used)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(inv, f, indent=1, sort_keys=False)
    if args.md:
        with open(args.md, "w", encoding="utf-8") as f:
            f.write(to_markdown(inv))
    print(f"{len(inv['tables'])} tables; unresolved constants: {len(inv['unresolved'])}")
    for s, w in inv["unresolved"].items():
        print("  unresolved", s, w)


if __name__ == "__main__":
    main()
