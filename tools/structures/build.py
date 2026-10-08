"""Build the pack's structures from tools/structures/catalogue.json (docs/lived-in.md).

Usage (from the repo root):
    tools/.venv/Scripts/python tools/structures/build.py [--out DIR] [--no-lint] [--strict]

Writes, under --out (default: the repo root):
    kubejs/data/pack/worldgen/{structure,structure_set,template_pool,processor_list}/...
    kubejs/data/pack/structure/<structure>/<variant>.nbt          templates
    kubejs/data/pack/loot_table/chests/<table>.json
    kubejs/data/pack/tags/worldgen/biome/has_structure/<structure>.json, tags/block/ruin_rottable.json
    kubejs/data/pack/easy_npc/preset/humanoid/<npc>.npc.snbt       Easy NPC presets
    config/tfc_real_world/geography/pack/waypoints/<site>.json     Real World waypoints (visit advancements)
Those folders are generated: edit the catalogue (or shapes.py) and rebuild.

Templates come from two places:
  - procedural variants name a builder in shapes.py;
  - hand-built variants are files tools/structures/templates/<structure>/<variant>.nbt (sites:
    tools/structures/templates/site/<site>/<variant>.nbt). Save them with a structure block (it writes
    <world>/generated/minecraft/structure/<name>.nbt) or Create's schematic and quill (schematics/<name>.nbt), built from
    the placeholder materials (rock granite, wood oak, soil alfisol, sand yellow), and copy them there. A hand-built file
    also replaces a procedural variant of the same name. A structure with no template yet is skipped (listed at the end).
Villages (multi-piece jigsaw structures, catalogue sections "regions" and "villages": streets, buildings, NPC spots, per-piece
processors, real-region placement) are handled by villages.py; their templates come from tfg_import.py, which converts TerraFirmaGreg's
settlements into tools/structures/templates/village/<culture>/<variant>/<piece>.nbt. `--villages off` (the catalogue's default)
checks them without writing, `climate` writes them for the pack's current jar, `region` writes the final form (pack_world:region and
pack_world:guarded_jigsaw, which need the jar described in the placement spec). `--simulate [N] [--layout]` places villages on flat ground
the way vanilla's jigsaw placement does and prints piece and NPC counts.
The post-pass, for every template: empty TFC chests get the structure's loot table; a DATA structure block whose metadata
is "npc:<id>" becomes that Easy NPC (an entity; "npc:<id>:spawner" a single spawner); Easy NPC entity data loses Owner,
Navigation.Home and UUID. The lint checks every block and item against the newest recipe dump, loot against the era caps
and deny-list, and biome ids against TFC's jar; problems are listed, and --strict makes them fatal.
"""
import argparse
import glob
import json
import os
import re
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
REPO = os.path.dirname(TOOLS)
sys.path.insert(0, HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(TOOLS, "recipes"))
sys.path.insert(0, os.path.join(TOOLS, "quests"))

import nbt as N  # noqa: E402
import shapes  # noqa: E402
import villages  # noqa: E402

NS = "pack"
CATALOGUE = os.path.join(HERE, "catalogue.json")
TEMPLATES = os.path.join(HERE, "templates")
NPC_DIR = os.path.join(HERE, "npcs")
DATA = os.path.join("kubejs", "data", NS)
# What the generator owns and clears before writing. Other features share the pack namespace (the cave rework writes
# kubejs/data/pack/worldgen/{noise,density_function,configured_carver,...} and tags), so only structure-specific folders and
# files are listed here, never a whole worldgen/ or tags/ folder.
OWNED_DIRS = [os.path.join(DATA, *p.split("/")) for p in (
    "worldgen/structure", "worldgen/structure_set", "worldgen/template_pool", "worldgen/processor_list", "structure",
    "loot_table/chests", "tags/worldgen/biome/has_structure", "easy_npc/preset/humanoid")] + [
    os.path.join("config", "tfc_real_world", "geography", NS)]
OWNED_FILES = [os.path.join(DATA, "tags", "block", "ruin_rottable.json"), os.path.join(DATA, "tags", "block", "village_rottable.json")]
VANILLA_OK = {"minecraft:air", "minecraft:structure_void", "minecraft:jigsaw"}
CHESTS = re.compile(r"^tfc:wood/(trapped_)?chest/[a-z_]+$")
SITE_EXCLUDE_TAGS = ["is_ocean", "is_ice_sheet", "is_river"]
SITE_KEEP = {"shore", "coastal_dunes", "embayments", "tidal_flats", "rocky_shores", "sea_stacks", "setback_cliffs", "terrace_lower",
             "terrace_upper", "old_shield_volcano_shore", "shield_volcano_shore"}
LAKES = {"lake", "meltwater_lake", "mountain_lake", "oceanic_mountain_lake", "old_mountain_lake", "plateau_lake", "rift_lake",
         "subglacial_lake", "tower_karst_lake", "volcanic_mountain_lake", "volcanic_oceanic_mountain_lake"}


class Problems(list):
    def add(self, where, msg):
        self.append(f"{where}: {msg}")


# ------------------------------------------------------------------ pack facts
def tfc_jar():
    jars = glob.glob(os.path.join(TOOLS, ".server", "mods", "TerraFirmaCraft-NeoForge-1.21.1-*.jar"))
    return jars[0] if jars else None


def tfc_biomes():
    """All TFC biome ids and the members of TFC's own biome tags, read from the jar."""
    jar = tfc_jar()
    if not jar:
        return None, {}
    z = zipfile.ZipFile(jar)
    biomes = sorted(n.split("/")[-1][:-5] for n in z.namelist() if re.match(r"data/tfc/worldgen/biome/[a-z_]+\.json$", n))
    tags = {}
    for n in z.namelist():
        m = re.match(r"data/tfc/tags/worldgen/biome/([a-z_]+)\.json$", n)
        if m:
            tags[m.group(1)] = json.loads(z.read(n))["values"]

    def expand(tag, seen=()):
        out = set()
        for v in tags.get(tag, []):
            if v.startswith("#tfc:"):
                if v[5:] not in seen:
                    out |= expand(v[5:], seen + (tag,))
            else:
                out.add(v.split(":")[1])
        return out
    return biomes, {t: expand(t) for t in tags}


def pack_ids():
    """Block and item ids of the newest recipe dump, and the progression steps (pack_query's cache)."""
    try:
        from model import latest_dump
        dump = latest_dump()
    except SystemExit:
        return None, None, None
    blocks = set(json.load(open(os.path.join(dump, "blocks.json"), encoding="utf-8"))["ids"])
    items = set(json.load(open(os.path.join(dump, "items.json"), encoding="utf-8"))["ids"])
    steps = None
    try:
        import pack_query
        steps = {k: v["step"] for k, v in pack_query.load()["items"].items()}
    except Exception as e:  # the step check is optional
        print(f"(no progression steps: {e})", file=sys.stderr)
    return blocks, items, steps


# ------------------------------------------------------------------ Easy NPC presets
def npc_data(npc_id, spec):
    """The entity compound of an NPC: an exported preset (tools/structures/npcs/<id>.npc.snbt) wins over the catalogue draft."""
    path = os.path.join(NPC_DIR, f"{npc_id}.npc.snbt")
    if os.path.exists(path):
        preset = N.from_snbt(open(path, encoding="utf-8").read())
        data = preset.get("data", preset)
        return preset, strip_npc(data)
    name = spec["name"]
    texts = [{"Text": spec["greeting"]}]
    buttons = N.List([{"Label": "trade", "Name": "Let's trade.", "Actions": N.List([{"Type": "OPEN_TRADING_SCREEN", "ExecAsUser": N.Byte(1), "PermLevel": N.Int(0)}])}])
    dialogs = []
    for i, tip in enumerate(spec.get("tips", [])):
        buttons.append({"Label": f"ask_{i}", "Name": ["Any advice?", "Anything else?"][min(i, 1)],
                        "Actions": N.List([{"Type": "OPEN_NAMED_DIALOG", "Cmd": f"tip_{i}"}])})
        dialogs.append({"Label": f"tip_{i}", "Name": f"Advice {i + 1}", "Priority": N.Int(0), "Texts": N.List([{"Text": tip}]),
                        "Buttons": N.List([{"Label": "back", "Name": "Thanks.", "Actions": N.List([{"Type": "OPEN_DEFAULT_DIALOG"}])}])})
    dialogs.insert(0, {"Label": "default", "Name": "Greeting", "Priority": N.Int(10), "Texts": N.List(texts), "Buttons": buttons})
    recipes = []
    for t in spec["trades"]:
        r = {"buy": {"id": t["buy"][0], "count": N.Int(t["buy"][1])}, "sell": {"id": t["sell"][0], "count": N.Int(t["sell"][1])},
             "maxUses": N.Int(t.get("max_uses", 8)), "uses": N.Int(0), "rewardExp": N.Byte(0), "xp": N.Int(0),
             "priceMultiplier": N.Float(0.0), "specialPrice": N.Int(0), "demand": N.Int(0)}
        if "buy_b" in t:
            r["buyB"] = {"id": t["buy_b"][0], "count": N.Int(t["buy_b"][1])}
        recipes.append(r)
    data = {
        "id": "easy_npc:humanoid",
        "CustomName": json.dumps({"text": name}),
        "CustomNameVisible": N.Byte(1),
        "PersistenceRequired": N.Byte(1),
        "EasyNPCVersion": N.Int(3),
        "SkinData": {"Type": "DEFAULT", "Name": spec.get("skin", "NOOR"), "Content": "", "URL": "", "UUID": N.IntArray([0, 0, 0, 0]),
                     "DisableLayers": N.Byte(0), "Timestamp": N.Long(0)},
        "ActionData": {"ActionEventSet": {"ON_INTERACTION": N.List([{"Type": "OPEN_DEFAULT_DIALOG"}])}},
        "DialogData": {"Type": "CUSTOM", "DialogDataSet": N.List(dialogs)},
        "Offers": {"Recipes": N.List(recipes)},
        "TradingData": {"TradingDataSet": {"Type": "ADVANCED", "ResetsEveryMin": N.Int(spec.get("reset_minutes", 60)), "MaxUses": N.Int(0),
                                           "RewardedXP": N.Int(0)}},
        "ObjectiveData": {"HasObjectives": N.Byte(1), "ObjectiveDataSet": N.List([{"Prio": N.Int(9), "Type": "LOOK_AT_PLAYER"},
                                                                                   {"Prio": N.Int(10), "Type": "LOOK_AT_MOB"},
                                                                                   {"Prio": N.Int(9), "Type": "LOOK_AT_RESET"}])},
        "Status": {"finalized": N.Byte(1)},
    }
    if spec.get("invulnerable"):       # village shopkeepers: no spawner brings them back, so nothing may kill them
        data["Invulnerable"] = N.Byte(1)
    preset = {"PresetMetadata": {"author": "pack", "category": "Pack", "name": name, "entityTypeId": "easy_npc:humanoid",
                                 "description": f"{name} for the pack's structures (generated draft; edit in game and export to tools/structures/npcs/{npc_id}.npc.snbt).",
                                 "version": "1.0.0", "created": N.Long(0), "modified": N.Long(0)},
              "data": data}
    return preset, data


def strip_npc(data):
    data = dict(data)
    for k in ("Owner", "UUID", "Pos", "Motion", "Rotation"):
        data.pop(k, None)
    nav = data.get("Navigation")
    if isinstance(nav, dict) and "Home" in nav:
        data["Navigation"] = {k: v for k, v in nav.items() if k != "Home"}
    return data


# ------------------------------------------------------------------ templates
def build_template(sid, variant):
    """(template root compound, ground layer, source) for a variant, or (None, None, reason)."""
    name = variant["name"]
    folder = os.path.join(TEMPLATES, *sid.split("/"))
    hand = os.path.join(folder, f"{name}.nbt")
    if os.path.exists(hand):
        return N.read(hand), variant.get("ground", 0), "hand-built"
    if variant.get("template"):
        return None, None, f"waiting for {os.path.relpath(hand, REPO)}"
    t = shapes.BUILDERS[variant["builder"]](variant.get("seed", 0), **variant.get("args", {}))
    root = t.to_nbt()
    return root, t.ground, f"procedural {t.stats()}"


def post_pass(sid, root, loot, npcs, problems):
    """Loot tables on empty chests, Easy NPCs from DATA markers, NPC data cleanup."""
    palette = root["palette"]
    blocks = root["blocks"]
    keep, extra_entities = N.List(kind=N.COMPOUND), []
    for b in blocks:
        state = palette[b["state"]]
        name = state["Name"]
        nbt = b.get("nbt")
        if CHESTS.match(name):
            nbt = dict(nbt or {})
            if "LootTable" not in nbt and not nbt.get("Items"):
                if loot:
                    nbt["LootTable"] = loot
                else:
                    problems.add(sid, f"chest at {list(b['pos'])} has no loot table and the structure defines none")
            nbt.setdefault("id", "tfc:chest")
            b["nbt"] = nbt
        if name == "minecraft:structure_block":
            meta = (nbt or {}).get("metadata", "")
            m = re.match(r"^npc:([a-z_]+)(:spawner)?$", meta)
            if not m:
                problems.add(sid, f"structure block at {list(b['pos'])} with metadata {meta!r} (only npc:<id> markers are allowed)")
                continue
            npc_id = m.group(1)
            if npc_id not in npcs:
                problems.add(sid, f"NPC marker for unknown NPC {npc_id!r}")
                continue
            data = npcs[npc_id]
            x, y, z = (int(v) for v in b["pos"])
            if m.group(2):
                sp = len(palette)
                palette.append({"Name": "easy_npc:single_spawner"})
                b["state"] = N.Int(sp)
                b["nbt"] = spawner_block_nbt(data)
            else:
                air = _palette_index(palette, {"Name": "minecraft:air"})
                b["state"] = N.Int(air)
                b.pop("nbt", None)
                extra_entities.append({"pos": N.List([N.Double(x + 0.5), N.Double(y), N.Double(z + 0.5)]),
                                       "blockPos": N.List([N.Int(x), N.Int(y), N.Int(z)]), "nbt": dict(data)})
        keep.append(b)
    # drop palette entries nothing uses any more (the markers' structure blocks), renumbering the blocks
    used = sorted({int(b["state"]) for b in keep})
    remap = {old: new for new, old in enumerate(used)}
    root["palette"] = N.List([palette[i] for i in used], kind=N.COMPOUND)
    for b in keep:
        b["state"] = N.Int(remap[int(b["state"])])
    root["blocks"] = keep
    ents = N.List(list(root.get("entities") or []), kind=N.COMPOUND)
    for e in ents:
        if str(e["nbt"].get("id", "")).startswith("easy_npc:"):
            e["nbt"] = strip_npc(e["nbt"])
    ents.extend(extra_entities)
    root["entities"] = ents
    return root


def spawner_block_nbt(data):
    """The block entity of an Easy NPC single spawner holding one NPC preset (npc_fixup gives each placed copy its own UUIDs)."""
    return {"id": "easy_npc:easy_npc_spawner_entity", "SpawnData": {"entity": dict(data)}, "StoredPresetData": dict(data),
            "Delay": N.Short(20), "MinSpawnDelay": N.Short(200), "MaxSpawnDelay": N.Short(800), "SpawnCount": N.Short(1),
            "MaxNearbyEntities": N.Short(1), "RequiredPlayerRange": N.Short(32), "SpawnRange": N.Short(2)}


def _palette_index(palette, entry):
    for i, p in enumerate(palette):
        if p.get("Name") == entry["Name"] and not p.get("Properties"):
            return i
    palette.append(entry)
    return len(palette) - 1


def lint_template(sid, root, blocks_known, problems, allow=None):
    """Blocks in a template: only TFC's, air, structure void and jigsaw. `allow` (villages) adds {"namespaces": [...], "vanilla": [...]}:
    mods the pack keeps for these buildings, and a short list of vanilla blocks."""
    names = {p["Name"] for p in root["palette"]}
    extra_ns = set((allow or {}).get("namespaces", ()))
    extra_vanilla = set((allow or {}).get("vanilla", ()))
    for n in sorted(names):
        ns = n.split(":")[0]
        if ns == "minecraft" and n not in VANILLA_OK and n not in extra_vanilla:
            problems.add(sid, f"vanilla block {n} (the golden check flags vanilla blocks; use the TFC one)")
        elif ns == "easy_npc":
            continue
        elif ns in extra_ns:
            if blocks_known is not None and n not in blocks_known:
                problems.add(sid, f"unknown block {n}")
        elif ns not in ("minecraft", "tfc"):
            problems.add(sid, f"block from another mod: {n}")
        elif blocks_known is not None and ns == "tfc" and n not in blocks_known:
            problems.add(sid, f"unknown block {n}")
    for e in root.get("entities") or []:
        eid = str(e["nbt"].get("id", ""))
        if not eid.startswith("easy_npc:"):
            problems.add(sid, f"entity {eid} in template (only Easy NPCs belong in templates)")
        for k in ("Owner", "UUID"):
            if k in e["nbt"]:
                problems.add(sid, f"entity {eid} still has {k}")
        if "Home" in (e["nbt"].get("Navigation") or {}):
            problems.add(sid, f"entity {eid} still has Navigation.Home")


# ------------------------------------------------------------------ loot
def loot_table(spec):
    entries = []
    for e in spec["entries"]:
        fns = []
        if "count" in e:
            lo, hi = e["count"]
            fns.append({"function": "minecraft:set_count", "count": {"type": "minecraft:uniform", "min": lo, "max": hi}})
        if e.get("rotten"):
            fns.append({"function": "tfc:rotten"})
        if e.get("climate"):
            entries.append({"type": "minecraft:item", "name": e["item"], "weight": e.get("weight", 1), "functions": fns,
                            "conditions": [dict({"condition": "pack_world:climate"}, **e["climate"])]})
            continue
        entry = {"type": "minecraft:item", "name": e["item"], "weight": e.get("weight", 1)}
        if fns:
            entry["functions"] = fns
        entries.append(entry)
    lo, hi = spec["rolls"]
    return {"type": "minecraft:chest", "pools": [{"rolls": {"type": "minecraft:uniform", "min": lo, "max": hi}, "entries": entries}]}


def lint_items(where, ids, era, caps, items_known, steps, problems):
    deny = [re.compile(p) for p in caps["deny"]]
    allow = [re.compile(p) for p in caps["allow_unreachable"]]
    cap = caps.get(era)
    for i in ids:
        if items_known is not None and i not in items_known:
            problems.add(where, f"unknown item {i}")
            continue
        if any(d.search(i) for d in deny):
            problems.add(where, f"{i} is on the deny-list (skips an era)")
        if steps is None or cap is None:
            continue
        s = steps.get(i)
        if s is None:
            if not any(a.search(i) for a in allow):
                problems.add(where, f"{i} is unreachable for the progression checker and not in allow_unreachable")
        elif s > cap:
            problems.add(where, f"{i} is step {s}, above the {era} cap {cap}")


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=REPO, help="root to write under (default: the repo); use a staging folder to review")
    ap.add_argument("--no-lint", action="store_true", help="skip the checks against the recipe dump and TFC's jar")
    ap.add_argument("--strict", action="store_true", help="exit 1 when the lint finds anything")
    ap.add_argument("--villages", choices=list(villages.MODES), help="the ported villages (catalogue 'villages'): off = check them, write nothing "
                    "(default: villages.settings.mode in the catalogue); climate = write them with tfc:climate placement and plain jigsaw "
                    "(loads on the pack's current jar); region = write them with pack_world:region and pack_world:guarded_jigsaw (needs the jar "
                    "that has them: SPEC.md)")
    ap.add_argument("--simulate", type=int, nargs="?", const=60, metavar="N", help="place N villages of each variant on flat ground the way vanilla's jigsaw "
                    "placement does and print the mean pieces, NPCs and extent (default 60)")
    ap.add_argument("--layout", action="store_true", help="with --simulate, also sketch one village per variant")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    cat = json.load(open(CATALOGUE, encoding="utf-8"))
    out = os.path.abspath(args.out)
    problems = Problems()
    blocks_known, items_known, steps = (None, None, None) if args.no_lint else pack_ids()
    biomes, biome_tags = (None, {}) if args.no_lint else tfc_biomes()

    for rel in OWNED_DIRS:
        shutil.rmtree(os.path.join(out, rel), ignore_errors=True)
    for rel in OWNED_FILES:
        if os.path.exists(os.path.join(out, rel)):
            os.remove(os.path.join(out, rel))
    files = {}

    def put(rel, content):
        files[rel] = content

    def put_json(rel, obj):
        put(rel, (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))

    landforms = {k: v for k, v in cat["landforms"].items() if isinstance(v, list)}
    if biomes:
        excluded = set()
        for t in SITE_EXCLUDE_TAGS:
            excluded |= biome_tags.get(t, set())
        excluded = (excluded - SITE_KEEP) | LAKES | {"deep_ocean", "deep_ocean_trench", "ocean", "ocean_reef", "ocean_ridge", "ocean_atolls",
                                                    "deep_ocean_atolls", "oceanic_volcanic_arc", "river"}
        landforms["site"] = [b for b in biomes if b not in excluded and not b.startswith("ice_sheet") and not b.startswith("glaciated_")
                             or b in ("glaciated_mountains",)]
        for g, members in landforms.items():
            for b in members:
                if b not in biomes:
                    problems.add(f"landform {g}", f"no TFC biome {b}")

    caps = cat["loot_caps"]
    npcs = {}
    for npc_id, spec in cat["npcs"].items():
        if npc_id.startswith("_"):
            continue
        preset, data = npc_data(npc_id, spec)
        npcs[npc_id] = data
        put(os.path.join(DATA, "easy_npc", "preset", "humanoid", f"{npc_id}.npc.snbt"), (N.to_snbt(preset) + "\n").encode("utf-8"))
        trade_items = [t["buy"][0] for t in spec["trades"]] + [t["buy_b"][0] for t in spec["trades"] if "buy_b" in t]
        sells = [t["sell"][0] for t in spec["trades"]]
        for s in sells:
            if s.startswith("tfc:food/"):
                problems.add(f"npc {npc_id}", f"sells food ({s}): its stored stack would carry the authoring world's date")
        lint_items(f"npc {npc_id}", sells, "bronze", caps, items_known, steps, problems)
        lint_items(f"npc {npc_id} (buys)", trade_items, None, caps, items_known, None, problems)

    rottable = set()
    built, waiting = [], []

    def emit_structure(sid, spec, biome_tag, placement, era, loot_name):
        variants, grounds, sources = [], set(), []
        for v in spec["variants"]:
            root, ground, source = build_template(sid, v)
            if root is None:
                sources.append(f"{v['name']}: {source}")
                continue
            root = post_pass(sid, root, loot_name, npcs, problems)
            if not args.no_lint:
                lint_template(f"{sid}/{v['name']}", root, blocks_known, problems)
            for p in root["palette"]:
                n = p["Name"]
                if re.match(r"^tfc:rock/(bricks|cracked_bricks|mossy_bricks|cobble|mossy_cobble)/granite", n):
                    rottable.add(n)
            put(os.path.join(DATA, "structure", *sid.split("/"), f"{v['name']}.nbt"), N.dumps(root))
            variants.append(v)
            grounds.add(ground)
            sources.append(f"{v['name']}: {source}")
        if not variants:
            waiting.append((sid, sources))
            return
        if len(grounds) > 1:
            problems.add(sid, f"variants have different ground layers {sorted(grounds)}; they share one start height")
        ground = grounds.pop()
        procs = []
        p = spec.get("processors", {})
        if p.get("rot"):
            procs.append({"processor_type": "minecraft:block_rot", "integrity": p["rot"], "rottable_blocks": f"#{NS}:ruin_rottable"})
        lm = json.loads(json.dumps(p.get("local_materials", {})))
        if "foundation" in lm:
            lm["foundation"].setdefault("ground", ground)    # fill under every column that rests on the ground layer
        procs.append(dict({"processor_type": "pack_world:local_materials"}, **lm))
        if p.get("npc_fixup") or spec.get("npcs"):
            procs.append({"processor_type": "pack_world:npc_fixup"})
        put_json(os.path.join(DATA, "worldgen", "processor_list", *sid.split("/")) + ".json", {"processors": procs})
        put_json(os.path.join(DATA, "worldgen", "template_pool", *sid.split("/"), "start.json"), {
            "fallback": "minecraft:empty",
            "elements": [{"weight": v.get("weight", 1), "element": {"element_type": "minecraft:single_pool_element",
                                                                     "location": f"{NS}:{sid}/{v['name']}", "processors": f"{NS}:{sid}",
                                                                     "projection": "rigid"}} for v in variants]})
        put_json(os.path.join(DATA, "worldgen", "structure", *sid.split("/")) + ".json", {
            "type": "minecraft:jigsaw", "biomes": biome_tag, "step": "surface_structures", "spawn_overrides": {},
            "terrain_adaptation": spec.get("terrain_adaptation", "beard_thin"), "start_pool": f"{NS}:{sid}/start", "size": 1,
            "start_height": {"absolute": -ground}, "project_start_to_heightmap": spec.get("heightmap", "WORLD_SURFACE_WG"),
            "max_distance_from_center": 80, "use_expansion_hack": False})
        put_json(os.path.join(DATA, "worldgen", "structure_set", *sid.split("/")) + ".json",
                 {"structures": [{"structure": f"{NS}:{sid}", "weight": 1}], "placement": placement})
        built.append((sid, sources))

    for sid, spec in cat["structures"].items():
        climate = {k: v for k, v in spec.get("climate", {}).items()}
        if climate.get("fuzzy") and not all(k in climate for k in ("min_temperature", "max_temperature", "min_groundwater", "max_groundwater")):
            problems.add(sid, "fuzzy climate needs both temperature and groundwater bounds (it never places otherwise)")
        if any(k in climate for k in ("min_elevation", "max_elevation")):
            problems.add(sid, "tfc:climate checks structures at y = 0: elevation bounds don't work")
        placement = {"type": "tfc:climate", "salt": spec["salt"], "spacing": spec["spacing"], "separation": spec["separation"], "climate": climate}
        loot_name = spec.get("loot_table", sid)
        if spec.get("loot"):
            put_json(os.path.join(DATA, "loot_table", "chests", f"{loot_name}.json"), loot_table(spec["loot"]))
            lint_items(f"loot {loot_name}", [e["item"] for e in spec["loot"]["entries"]], spec["era"], caps, items_known, steps, problems)
        emit_structure(sid, spec, f"#{NS}:has_structure/{sid}", placement, spec["era"], f"{NS}:chests/{loot_name}" if spec.get("loot") else None)
        if built and built[-1][0] == sid:
            members = sorted({b for g in spec["landforms"] for b in landforms.get(g, [])})
            put_json(os.path.join(DATA, "tags", "worldgen", "biome", "has_structure", f"{sid}.json"),
                     {"replace": False, "values": [f"tfc:{b}" for b in members]})

    for era, spec in cat.get("site_loot", {}).items():
        if era.startswith("_"):
            continue
        put_json(os.path.join(DATA, "loot_table", "chests", f"site_{era}.json"), loot_table(spec))
        lint_items(f"loot site_{era}", [e["item"] for e in spec["entries"]], era, caps, items_known, steps, problems)
    for site, s in cat["sites"].items():
        if site.startswith("_"):
            continue
        waypoint = {"parent": s["parent"], "title_lang": {"en_us": s["title"]}, "subtitle_lang": {"en_us": "Ancient site"},
                    "description_lang": {"en_us": s["description"]}, "latitude": s["latitude"], "longitude": s["longitude"]}
        put_json(os.path.join("config", "tfc_real_world", "geography", NS, "waypoints", f"{site}.json"), waypoint)
        placement = {"type": "pack_world:geographic", "site": site, "latitude": s["latitude"], "longitude": s["longitude"],
                     "offset": s.get("offset", [0, 0]), "salt": s["salt"]}
        spec = {"variants": s.get("variants", [{"name": "main", "template": True, "ground": s.get("ground", 0)}]),
                "terrain_adaptation": s.get("terrain_adaptation", "beard_thin"),
                "processors": {"local_materials": dict({"rock": s["rock"]} if s.get("rock", "local") != "local" else {},
                                                       **s.get("local_materials", {})), "npc_fixup": True}}
        emit_structure(f"site/{site}", spec, f"#{NS}:has_structure/site", placement, s.get("loot_era", "bronze"),
                       f"{NS}:chests/site_{s.get('loot_era', 'bronze')}")

    vmode = args.villages or (cat.get("villages") or {}).get("settings", {}).get("mode", "off")
    vctx = villages.Ctx(put=put, put_json=put_json, problems=problems, N=N, spawner_block_nbt=spawner_block_nbt, npc_data=npc_data, post_pass=post_pass,
                        lint_template=lint_template if not args.no_lint else (lambda *a, **k: None), loot_table=loot_table, lint_items=lint_items,
                        DATA=DATA, NS=NS, TEMPLATES=TEMPLATES, REPO=REPO, caps=caps, items_known=items_known, steps=steps, blocks_known=blocks_known,
                        landforms=landforms, biomes=biomes, npcs=npcs, lint=not args.no_lint)
    vsummary = villages.emit(cat, vctx, vmode)

    if any(sid.startswith("site/") for sid, _ in built):
        put_json(os.path.join(DATA, "tags", "worldgen", "biome", "has_structure", "site.json"),
                 {"replace": False, "values": [f"tfc:{b}" for b in landforms.get("site", [])]})
    rottable |= {f"tfc:rock/{v}/granite{sh}" for v in ("bricks", "cracked_bricks", "mossy_bricks", "cobble", "mossy_cobble")
                 for sh in ("", "_stairs", "_slab", "_wall")}
    put_json(os.path.join(DATA, "tags", "block", "ruin_rottable.json"), {"replace": False, "values": sorted(rottable)})

    for rel, content in sorted(files.items()):
        path = os.path.join(out, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(content)

    print(f"Wrote {len(files)} files under {out}")
    print(f"\nStructures generated ({len(built)}):")
    for sid, sources in built:
        print(f"  {sid}: " + "; ".join(sources))
    if vsummary:
        print(f"\nVillages (mode {vmode}{'' if vmode != 'off' else ': checked, nothing written'}):")
        for st in vsummary:
            print(f"  {st['id']}: " + "; ".join(f"{v} {len(d['pieces'])} pieces" for v, d in st["variants"].items())
                  + f"; NPCs {', '.join(st['npcs']) or '-'}; {st['biomes']} biomes")
        if args.simulate:
            for st in vsummary:
                for vid in st["variants"]:
                    pieces, npcn, ext, sample = villages.simulate(cat, st["id"], vid, vctx, n=args.simulate, layout=args.layout)
                    print(f"  {st['id']}/{vid}, per village (flat-ground jigsaw simulation, mean {ext[0]} x {ext[1]} blocks): "
                          + ", ".join(f"{k} {n}" for k, n in pieces.items()) + ("; NPCs: " + ", ".join(f"{k} {n}" for k, n in npcn.items()) if npcn else ""))
                    if args.layout and sample:
                        print(villages.ascii_layout(sample))
    if waiting:
        print(f"\nWaiting for hand-built templates ({len(waiting)}), skipped:")
        for sid, sources in waiting:
            print(f"  {sid}: " + "; ".join(sources))
    if problems:
        print(f"\nLint ({len(problems)}):")
        for p in problems:
            print(f"  {p}")
    elif not args.no_lint:
        print("\nLint: clean")
    return 1 if (problems and args.strict) else 0


if __name__ == "__main__":
    sys.exit(main())
