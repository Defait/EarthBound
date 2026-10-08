"""Multi-piece jigsaw villages for tools/structures/build.py (catalogue section "villages", docs/lived-in.md).

build.py's own structures are one pool of size-1 pieces. A village is a graph: a start piece, streets that branch, buildings that
hang off the street ends, NPC spots in the buildings, fallbacks when a pool can't place anything. This module reads the catalogue's
`villages` and `regions` sections and writes, through build.py's own file writer and checks:

    kubejs/data/pack/worldgen/structure/village/<id>_<variant>.json         jigsaw structure (or pack_world:guarded_jigsaw)
    kubejs/data/pack/worldgen/structure_set/village/<id>.json               placement: pack_world:region (or tfc:climate)
    kubejs/data/pack/worldgen/template_pool/village/<id>/<variant>/<pool>.json
    kubejs/data/pack/worldgen/processor_list/village/<id>/<variant>/<list>.json
    kubejs/data/pack/structure/village/<id>/<variant>/<piece>.nbt           templates (post-pass and lint like every template)
    kubejs/data/pack/structure/village/<id>/npc/<npc>[_spawner].nbt         one-block NPC pieces: a jigsaw and an Easy NPC
    kubejs/data/pack/loot_table/chests/village/<id>/<class>.json
    kubejs/data/pack/tags/worldgen/biome/has_structure/village/<id>.json    and tags/block/village_rottable.json
    kubejs/data/pack/easy_npc/preset/humanoid/<npc>.npc.snbt

Catalogue shape (JSON; "//" notes are not part of it):
  "regions": {"<name>": {"polygon": [[lat, lon], ...]}  or  {"box": [south, west, north, east]}, "note": "..."}
  "villages": {"settings": {"mode": "off"|"climate"|"region"}, "defaults": {...merged into every village...},
    "<id>": {
      "title", "era" (loot era: stone, copper or bronze), "kind": "village"|"monument",
      "step": the generation step the pieces are placed in (default "surface_structures"; "top_layer_modification" places them after the
              forest, so the template's air clears the trees inside the village instead of the trees growing over it),
      "set": {"regions": [names], "exclude": [names], "climate": {...tfc:climate's climate object...},
              "spacing", "separation", "salt", "spread_type", "landforms": [groups of "landforms"], "biomes": [extra TFC biome names]},
      "guard": {...pack_world:guarded_jigsaw's guard...},               // used in mode "region"
      "materials": {...pack_world:local_materials fields shared by the culture's lists...},
      "npcs": {"<npc id>": {...like the top-level "npcs" entries...}},
      "loot": {"<class>": {"rolls": [a, b], "entries": [...]}}, "pieces": {"<piece>": {"loot": "<class>"}},
      "variants": {"<variant>": {
        "weight", "size" (jigsaw depth), "max_distance", "terrain_adaptation", "heightmap", "start": "<pool>", "start_ground",
        "processors": {"<list>": {"marker": "street"|"plain"|null, "street": {...}, "rot": 0.9, "local_materials": {...}, "foundation": {...}}},
        "pools": {"<pool>": {"fallback": "<pool>" or "minecraft:empty" (default),
                  "elements": [{"piece": "<name>", "weight": n, "processors": "<list>", "projection": "rigid"|"terrain_matching"},
                               {"empty": true, "weight": n},
                               {"npc": "<npc id>", "weight": n, "spawner": false}]}}}}}}   (every pool with NPCs also exists as `<pool>_low`, generated)
Pieces are templates/village/<id>/<variant>/<piece>.nbt (written by tfg_import.py or saved by hand); their jigsaw blocks name the
pools `pack:village/<id>/<variant>/<pool>`. Pools here are weights and fallbacks only (vanilla has no limit elements, and Lithostitched is
not in the pack): `build.py --simulate N --layout` places villages with vanilla's jigsaw rules on flat ground and prints how many of each
building and NPC one gets, to tune the weights. Element shorthand: {"pieces": [a, b], <shared fields>} is one element per piece. An
empty element ends the attempt for that jigsaw (vanilla tries the pool's elements in weight order and the fallback pool's after them).
NPC pieces hang on `pack:npc_connector` jigsaws that TFG's templates keep where its illagers stood; a village can use NPCs of another
village (`npcs_from`). Region polygons may list `anchors` and `outside` cities the lint checks them against.
"""
import collections
import copy
import os
import random

NS = "pack"
MARKER = "tfc:rock/bricks/andesite"            # tfg_import.py's road marker: the processor lists turn it into paths
WATER = ["minecraft:water", "tfc:fluid/river_water", "tfc:fluid/salt_water"]
ERAS = ("stone", "copper", "bronze")
STEPS = ("raw_generation", "lakes", "local_modifications", "underground_structures", "surface_structures", "strongholds", "underground_ores",
         "underground_decoration", "fluid_springs", "vegetal_decoration", "top_layer_modification")
MODES = ("off", "climate", "region")
CLIMATE_KEYS = {"min_temperature", "max_temperature", "min_groundwater", "max_groundwater", "min_rain_variance", "max_rain_variance",
                "rain_variance_absolute", "min_forest", "max_forest", "forest_types", "fuzzy", "ignore_rivers"}
REJECTED_CLIMATE = {"min_rainfall": "TFC 4 has no rainfall bounds: use min_groundwater with ignore_rivers",
                    "max_rainfall": "TFC 4 has no rainfall bounds: use max_groundwater with ignore_rivers",
                    "min_elevation": "tfc:climate checks structures at y = 0, so elevation bounds don't work",
                    "max_elevation": "tfc:climate checks structures at y = 0, so elevation bounds don't work"}
DEFAULT_VANILLA = ["minecraft:water", "minecraft:torch", "minecraft:wall_torch"]
DEFAULT_NAMESPACES = ["framedblocks", "rnr"]
MAX_TEMPLATE = 96      # structure references reach 8 chunks; a bigger piece would be cut at the edge of what is loaded


class Ctx:
    """What build.py hands over: its writers, problem list, knowledge of the pack and its template helpers."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


# ------------------------------------------------------------------------------------------------------------------ helpers
def deep_merge(a, b):
    out = copy.deepcopy(a)
    for k, v in (b or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def expand(pools):
    """Element shorthand: {"pieces": [a, b, ...], <shared fields>} stands for one {"piece": a, ...} per name."""
    out = {}
    for name, pool in pools.items():
        els = []
        for e in pool["elements"]:
            if "pieces" in e:
                shared = {k: v for k, v in e.items() if k != "pieces"}
                els += [dict(shared, piece=pc) for pc in e["pieces"]]
            else:
                els.append(e)
        out[name] = dict(pool, elements=els)
    return out


def marker_rules(kind, params, wood="oak"):
    """`minecraft:rule` processors that turn tfg_import.py's road marker into paths: planks over water (or air), then a random mix of
    road gravel, trodden path and grass, and compacted gravel for the rest. Placeholders (granite, oak, alfisol) become local ones
    in local_materials, which runs after every processor."""
    if kind in (None, "none"):
        return []
    over = list(WATER) + (["minecraft:air"] if params.get("over_air") else [])
    rules = [{"input_predicate": {"predicate_type": "minecraft:block_match", "block": MARKER},
              "location_predicate": {"predicate_type": "minecraft:block_match", "block": w},
              "output_state": {"Name": f"tfc:wood/planks/{wood}"}} for w in over]
    if kind == "street":
        for p, out in ((params.get("gravel", 0.1), "rnr:rock/gravel_road/granite"), (params.get("path", 0.15), "tfc:grass_path/alfisol"),
                       (params.get("grass", 0.1), "tfc:grass/alfisol")):
            if p:
                rules.append({"input_predicate": {"predicate_type": "minecraft:random_block_match", "block": MARKER, "probability": p},
                              "location_predicate": {"predicate_type": "minecraft:always_true"}, "output_state": {"Name": out}})
    rules.append({"input_predicate": {"predicate_type": "minecraft:random_block_match", "block": MARKER, "probability": 1.0},
                  "location_predicate": {"predicate_type": "minecraft:always_true"}, "output_state": {"Name": params.get("base", "rnr:hoggin")}})
    return [{"processor_type": "minecraft:rule", "rules": rules}]


def region_json(regions, name):
    r = regions[name]
    out = {"name": name}
    if "polygon" in r:
        out["polygon"] = [[float(a), float(b)] for a, b in r["polygon"]]
    elif "box" in r:
        out["box"] = [float(v) for v in r["box"]]
    return out


def point_in_polygon(poly, lat, lon):
    inside, j = False, len(poly) - 1
    for i in range(len(poly)):
        yi, xi = poly[i]
        yj, xj = poly[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


# ------------------------------------------------------------------------------------------------------- NPC pieces
def npc_piece(ctx, data, spawner, low=False):
    """A one-block piece that hangs on a village's `pack:npc_connector` jigsaw (on a floor, facing up): its own jigsaw faces down and is
    replaced by air, an Easy NPC entity stands in that cell. With `spawner`, a single spawner sits two blocks lower, under the floor.
    With `low` the entity stands one cell lower, in the parent jigsaw's own cell: TFG put most of its mob jigsaws in the air cell above the floor,
    so the child (one cell further up) would hold the NPC a block above the floor.
    The processor list `pack:village/npc` (npc_fixup) gives every placed copy its own NPC."""
    N, spawner_block_nbt = ctx.N, ctx.spawner_block_nbt
    jig = {"id": "minecraft:jigsaw", "name": f"{NS}:npc_connector", "target": "minecraft:empty", "pool": "minecraft:empty", "joint": "rollable",
           "final_state": "minecraft:air"}
    palette = [{"Name": "minecraft:jigsaw", "Properties": {"orientation": "down_north"}}]
    if spawner:
        palette.append({"Name": "easy_npc:single_spawner"})
        blocks = [{"pos": N.List([N.Int(0), N.Int(2), N.Int(0)]), "state": N.Int(0), "nbt": jig},
                  {"pos": N.List([N.Int(0), N.Int(0), N.Int(0)]), "state": N.Int(1), "nbt": spawner_block_nbt(data)}]
        size, entities = [1, 3, 1], []
    else:
        blocks = [{"pos": N.List([N.Int(0), N.Int(0), N.Int(0)]), "state": N.Int(0), "nbt": jig}]
        size = [1, 1, 1]
        dy = -1 if low else 0
        entities = [{"pos": N.List([N.Double(0.5), N.Double(float(dy)), N.Double(0.5)]), "blockPos": N.List([N.Int(0), N.Int(dy), N.Int(0)]),
                     "nbt": dict(data)}]
    return {"DataVersion": N.Int(3955), "size": N.List([N.Int(v) for v in size]), "palette": N.List(palette, kind=N.COMPOUND),
            "blocks": N.List(blocks, kind=N.COMPOUND), "entities": N.List(entities, kind=N.COMPOUND)}


# ------------------------------------------------------------------------------------------------------- the emitter
def emit(cat, ctx, mode):
    """Write every village (mode "climate" or "region") or just check them (mode "off", the default). Returns a summary list."""
    V = cat.get("villages") or {}
    regions = {k: v for k, v in (cat.get("regions") or {}).items() if not k.startswith("_")}
    if not V:
        return []
    write = mode != "off"
    put, put_json = (ctx.put, ctx.put_json) if write else (lambda *a, **k: None, lambda *a, **k: None)
    problems = ctx.problems
    defaults = V.get("defaults", {})
    lint_cfg = V.get("lint", {})
    allow = {"namespaces": lint_cfg.get("namespaces", DEFAULT_NAMESPACES), "vanilla": lint_cfg.get("vanilla", DEFAULT_VANILLA)}
    summary = []
    # regions used anywhere must exist and make sense
    for name, r in regions.items():
        poly = r.get("polygon")
        if poly is not None:
            if len(poly) < 3:
                problems.add(f"region {name}", "a polygon needs at least 3 vertices")
            for lat, lon in poly:
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    problems.add(f"region {name}", f"vertex {[lat, lon]} is outside the globe (use [latitude, longitude])")
        elif "box" in r:
            s, w, n, e = r["box"]
            if not (-90 <= s < n <= 90 and -180 <= w < e <= 180):
                problems.add(f"region {name}", f"box {r['box']} must be [south, west, north, east] with south < north and west < east")
        else:
            problems.add(f"region {name}", "needs a polygon or a box")
        # anchors: places that must be inside (and, under "outside", must not be): catches swapped [lat, lon] and sloppy edges
        for kind, want in (("anchors", True), ("outside", False)):
            for label, lat, lon in r.get(kind, []):
                if "box" in r:
                    s_, w_, n_, e_ = r["box"]
                    inside = s_ <= lat <= n_ and w_ <= lon <= e_
                elif poly is not None:
                    inside = point_in_polygon(poly, lat, lon)
                else:
                    continue
                if inside != want:
                    problems.add(f"region {name}", f"{label} ({lat}, {lon}) should be {'inside' if want else 'outside'} but is {'inside' if inside else 'outside'}")
    rottable = set()
    ids = [c for c in V if c not in ("settings", "defaults", "lint") and not c.startswith("_")]
    salts = {}                      # a salt shared by two sets would line their grids up: every set gets its own
    for sid, spec in (cat.get("structures") or {}).items():
        salts.setdefault(spec.get("salt"), sid)
    for sid, spec in (cat.get("sites") or {}).items():
        if not sid.startswith("_"):
            salts.setdefault(spec.get("salt"), f"site {sid}")
    for cid in ids:
        salt = V[cid].get("set", {}).get("salt")
        if salt in salts:
            problems.add(f"village {cid}", f"salt {salt} is already used by {salts[salt]}")
        salts.setdefault(salt, f"village {cid}")
    owners = {}                     # NPC id -> (village, spec): a village's pools may use NPCs defined in another (npcs_from)
    for cid in ids:
        for npc_id, spec in (V[cid].get("npcs") or {}).items():
            if not npc_id.startswith("_"):
                if npc_id in owners or npc_id in ctx.npcs:
                    problems.add(f"village {cid}", f"NPC id {npc_id} is already defined elsewhere")
                owners[npc_id] = (cid, spec)
    for cid in ids:
        vc = deep_merge(defaults, V[cid])
        summary.append(emit_one(cid, vc, regions, ctx, mode, put, put_json, allow, rottable, owners))
    if rottable and write:
        # a tag naming an unregistered id is dropped whole, and the processors using it with it: another mod's ids are optional entries
        values = [{"id": b, "required": False} if not b.startswith(("tfc:", "minecraft:")) else b for b in sorted(rottable)]
        put_json(os.path.join(ctx.DATA, "tags", "block", "village_rottable.json"), {"replace": False, "values": values})
    return summary


def emit_one(cid, vc, regions, ctx, mode, put, put_json, allow, rottable, owners):
    N = ctx.N
    problems = ctx.problems
    DATA, NS_ = ctx.DATA, ctx.NS
    where = f"village {cid}"
    era = vc.get("era", "bronze")
    if era not in ERAS:
        problems.add(where, f"era {era!r} is not one of {ERAS}")
    if vc.get("step", "surface_structures") not in STEPS:
        problems.add(where, f"step {vc.get('step')!r} is not a generation step ({', '.join(STEPS)})")
    templates = os.path.join(ctx.TEMPLATES, "village", cid)
    # ---- NPCs of this village
    npcs = {}
    for src in vc.get("npcs_from", []):
        for npc_id, (owner, spec) in owners.items():
            if owner == src:
                npcs[npc_id] = ctx.npc_data(npc_id, spec)[1]
    for npc_id, spec in (vc.get("npcs") or {}).items():
        if npc_id.startswith("_"):
            continue
        preset, data = ctx.npc_data(npc_id, spec)
        npcs[npc_id] = data
        put(os.path.join(DATA, "easy_npc", "preset", "humanoid", f"{npc_id}.npc.snbt"), (N.to_snbt(preset) + "\n").encode("utf-8"))
        sells = [t["sell"][0] for t in spec["trades"]]
        buys = [t["buy"][0] for t in spec["trades"]] + [t["buy_b"][0] for t in spec["trades"] if "buy_b" in t]
        for s in sells:
            if s.startswith("tfc:food/"):
                problems.add(f"npc {npc_id}", f"sells food ({s}): its stored stack would carry the authoring world's date")
        ctx.lint_items(f"npc {npc_id}", sells, era, ctx.caps, ctx.items_known, ctx.steps, problems)
        ctx.lint_items(f"npc {npc_id} (buys)", buys, None, ctx.caps, ctx.items_known, None, problems)
        for t in spec["trades"]:
            if t["sell"][0].startswith("tfc:food/") or any(x.startswith("gtceu:") or x.startswith("create:") for x in (t["sell"][0], t["buy"][0])):
                problems.add(f"npc {npc_id}", f"trade {t} leaves the era's goods")
    # ---- loot classes -> tables
    loot_names = {}
    for cls, spec in (vc.get("loot") or {}).items():
        if cls.startswith("_"):
            continue
        name = f"village/{cid}/{cls}"
        loot_names[cls] = f"{NS_}:chests/{name}"
        put_json(os.path.join(DATA, "loot_table", "chests", *name.split("/")) + ".json", ctx.loot_table(spec))
        ctx.lint_items(f"loot {name}", [e["item"] for e in spec["entries"]], era, ctx.caps, ctx.items_known, ctx.steps, problems)
    pieces_cfg = vc.get("pieces") or {}
    default_loot = loot_names.get(vc.get("default_loot", "default"))
    # ---- the set
    sset = vc["set"]
    check_set(where, sset, regions, problems, ctx)
    variants = vc["variants"]
    structure_ids = []
    stats = {"id": cid, "variants": {}, "npcs": sorted(npcs)}
    for vid, v in variants.items():
        sid = f"village/{cid}_{vid}"
        vwhere = f"{where}/{vid}"
        v = deep_merge({"size": 6, "max_distance": 96, "terrain_adaptation": "beard_thin", "heightmap": "WORLD_SURFACE_WG", "start": "start",
                        "start_ground": 0, "weight": 1}, v)
        if not (1 <= v["size"] <= 20):
            problems.add(vwhere, f"size {v['size']} must be 1..20 (jigsaw depth)")
        if not (1 <= v["max_distance"] <= 128):
            problems.add(vwhere, f"max_distance {v['max_distance']} must be 1..128")
        pools = v["pools"] = expand(v["pools"])
        for pname in [k for k, pool in pools.items() if any("npc" in e and not e.get("spawner") for e in pool["elements"])]:
            # every NPC pool has a `_low` twin whose pieces stand one cell lower (jigsaws the importer found in the air above a floor name it)
            pools[pname + "_low"] = dict(pools[pname], elements=[dict(e, low=True) if "npc" in e else e for e in pools[pname]["elements"]])
        if v["start"] not in pools:
            problems.add(vwhere, f"start pool {v['start']!r} is not defined")
        # processor lists
        lists = v.get("processors", {})
        base_lm = vc.get("materials", {})
        for lname, spec in lists.items():
            procs = []
            if spec.get("rot"):
                procs.append({"processor_type": "minecraft:block_rot", "integrity": spec["rot"], "rottable_blocks": f"#{NS_}:village_rottable"})
                rottable |= village_rottable(vc)
            procs += marker_rules(spec.get("marker"), spec.get("street", {}), wood=vc.get("marker_wood", "oak"))
            lm = deep_merge(base_lm, spec.get("local_materials", {}))
            if "foundation" in spec:
                lm["foundation"] = deep_merge(lm.get("foundation", {}), spec["foundation"])
            if "foundation" in lm:
                lm["foundation"].setdefault("ground", v["start_ground"])
            if spec.get("local_materials") is not False:
                procs.append(dict({"processor_type": "pack_world:local_materials"}, **lm))
            if ctx.blocks_known is not None:                      # a block id that doesn't exist makes the whole processor list fail to load
                for proc in procs:
                    for rule in proc.get("rules", []):
                        for blk in (rule["input_predicate"].get("block"), rule["location_predicate"].get("block"), rule["output_state"]["Name"]):
                            if blk and blk not in ctx.blocks_known:
                                problems.add(f"{vwhere}/{lname}", f"processor rule names unknown block {blk}")
            put_json(os.path.join(DATA, "worldgen", "processor_list", "village", cid, vid, f"{lname}.json"), {"processors": procs})
        # pieces and pools
        used = collections.OrderedDict()
        for pname, pool in pools.items():
            fb = pool.get("fallback", "minecraft:empty")
            if fb != "minecraft:empty" and fb not in pools:
                problems.add(f"{vwhere}/{pname}", f"fallback pool {fb!r} is not defined")
            elements = []
            for e in pool["elements"]:
                w = e.get("weight", 1)
                if "empty" in e:
                    elements.append({"weight": w, "element": {"element_type": "minecraft:empty_pool_element"}})
                elif "npc" in e:
                    nid = e["npc"]
                    if nid not in npcs:
                        problems.add(f"{vwhere}/{pname}", f"NPC {nid!r} is not defined in this village's npcs")
                        continue
                    spawner = bool(e.get("spawner"))
                    low = bool(e.get("low"))
                    pid = f"{nid}_spawner" if spawner else f"{nid}_low" if low else nid
                    used.setdefault(("npc", pid, nid, spawner, low), []).append(pname)
                    elements.append({"weight": w, "element": {"element_type": "minecraft:single_pool_element",
                                                              "location": f"{NS_}:village/{cid}/npc/{pid}", "processors": f"{NS_}:village/npc",
                                                              "projection": "rigid"}})
                else:
                    piece = e["piece"]
                    lname = e.get("processors", "structures")
                    if lname not in lists:
                        problems.add(f"{vwhere}/{pname}", f"piece {piece} names processor list {lname!r}, which this variant doesn't define")
                    used.setdefault(("piece", piece), []).append(pname)
                    elements.append({"weight": w, "element": {"element_type": "minecraft:single_pool_element",
                                                              "location": f"{NS_}:village/{cid}/{vid}/{piece}",
                                                              "processors": f"{NS_}:village/{cid}/{vid}/{lname}",
                                                              "projection": e.get("projection", "rigid")}})
            if not elements:
                problems.add(f"{vwhere}/{pname}", "pool has no usable element")
            put_json(os.path.join(DATA, "worldgen", "template_pool", "village", cid, vid, f"{pname}.json"),
                     {"fallback": "minecraft:empty" if fb == "minecraft:empty" else f"{NS_}:village/{cid}/{vid}/{fb}", "elements": elements})
        # templates
        names = {}          # piece -> set of jigsaw names it offers
        links = []          # (from piece, pool, target)
        marker_pieces = set()
        for key in used:
            if key[0] == "npc":
                _, pid, nid, spawner, low = key
                put(os.path.join(DATA, "structure", "village", cid, "npc", f"{pid}.nbt"), N.dumps(npc_piece(ctx, npcs[nid], spawner, low)))
                continue
            piece = key[1]
            path = os.path.join(templates, vid, f"{piece}.nbt")
            if not os.path.exists(path):
                problems.add(f"{vwhere}/{piece}", f"template missing: {os.path.relpath(path, ctx.REPO)} (run tfg_import.py or save one by hand)")
                continue
            root = N.read(path)
            size = [int(x) for x in root["size"]]
            if max(size[0], size[2]) > MAX_TEMPLATE or size[1] > 128:
                problems.add(f"{vwhere}/{piece}", f"template is {size}: more than {MAX_TEMPLATE} wide or 128 tall")
            loot = loot_names.get(pieces_cfg.get(piece, {}).get("loot", "")) or default_loot
            root = ctx.post_pass(sid, root, loot, {**ctx.npcs, **npcs}, problems)
            ctx.lint_template(f"{vwhere}/{piece}", root, ctx.blocks_known, problems, allow)
            pal = root["palette"]
            finals = {str((b.get("nbt") or {}).get("final_state", "minecraft:air")).split("[")[0] for b in root["blocks"]
                      if pal[int(b["state"])]["Name"] == "minecraft:jigsaw"}
            ctx.lint_template(f"{vwhere}/{piece} (jigsaw final_state)", {"palette": [{"Name": n} for n in sorted(finals)], "entities": []},
                              ctx.blocks_known, problems, allow)
            for b in root["blocks"]:
                nm = pal[int(b["state"])]["Name"]
                if nm == MARKER:
                    marker_pieces.add(piece)
                nb = b.get("nbt") or {}
                if nm == "minecraft:jigsaw":
                    names.setdefault(piece, set()).add(nb.get("name", "minecraft:empty"))
                    pool = nb.get("pool", "minecraft:empty")
                    if pool != "minecraft:empty":
                        links.append((piece, pool, nb.get("target", "minecraft:empty")))
            put(os.path.join(DATA, "structure", "village", cid, vid, f"{piece}.nbt"), N.dumps(root))
        # the marker needs a rule processor wherever a piece holds it
        for key, in_pools in used.items():
            if key[0] != "piece" or key[1] not in marker_pieces:
                continue
            for pname in in_pools:
                for e in pools[pname]["elements"]:
                    if e.get("piece") == key[1] and not lists.get(e.get("processors", "structures"), {}).get("marker"):
                        problems.add(f"{vwhere}/{key[1]}", f"holds the road marker but its processor list {e.get('processors', 'structures')!r} has no marker rule")
        lint_graph(vwhere, cid, vid, pools, names, links, problems)
        for pname, pool in pools.items():
            for e in pool["elements"]:
                if "piece" in e and e["piece"] not in {k[1] for k in used if k[0] == "piece"}:
                    problems.add(f"{vwhere}/{pname}", f"piece {e['piece']} unresolved")
        structure_ids.append((sid, v["weight"]))
        shared = {"biomes": f"#{NS_}:has_structure/village/{cid}", "step": vc.get("step", "surface_structures"), "spawn_overrides": {},
                  "terrain_adaptation": v["terrain_adaptation"], "start_pool": f"{NS_}:village/{cid}/{vid}/{v['start']}", "size": v["size"],
                  "start_height": {"absolute": -v["start_ground"]}, "project_start_to_heightmap": v["heightmap"],
                  "max_distance_from_center": v["max_distance"], "use_expansion_hack": False}
        if mode == "region":
            guard = deep_merge(vc.get("guard", {}), v.get("guard", {}))
            body = dict({"type": "pack_world:guarded_jigsaw"}, **shared)
            body["guard"] = guard
        else:
            body = dict({"type": "minecraft:jigsaw"}, **shared)
        put_json(os.path.join(DATA, "worldgen", "structure", "village", f"{cid}_{vid}.json"), body)
        stats["variants"][vid] = {"pieces": sorted({k[1] for k in used if k[0] == "piece"}), "npc_pieces": sorted({k[1] for k in used if k[0] == "npc"})}
    # NPC fixup list (shared)
    put_json(os.path.join(DATA, "worldgen", "processor_list", "village", "npc.json"), {"processors": [{"processor_type": "pack_world:npc_fixup"}]})
    # the set and its biome tag
    put_json(os.path.join(DATA, "worldgen", "structure_set", "village", f"{cid}.json"),
             {"structures": [{"structure": f"{NS_}:{sid}", "weight": w} for sid, w in structure_ids], "placement": placement(cid, sset, regions, mode)})
    members = sorted({b for g in sset.get("landforms", []) for b in ctx.landforms.get(g, [])} | set(sset.get("biomes", [])))
    if ctx.biomes:
        for b in members:
            if b not in ctx.biomes:
                problems.add(where, f"no TFC biome {b}")
    put_json(os.path.join(DATA, "tags", "worldgen", "biome", "has_structure", "village", f"{cid}.json"),
             {"replace": False, "values": [f"tfc:{b}" for b in members]})
    stats["biomes"] = len(members)
    stats["salt"] = sset.get("salt")
    return stats


def village_rottable(vc):
    """Blocks block_rot may remove from a ruined village: the placeholder woods' planks and shapes, thatch and shingles."""
    out = set()
    for w in ("oak", "spruce", "birch"):
        for sh in ("", "_stairs", "_slab"):
            out.add(f"tfc:wood/planks/{w}{sh}")
            out.add(f"rnr:wood/shingles/{w}{sh}")
        out.add(f"tfc:wood/fence/{w}")
        out.add(f"tfc:wood/log_fence/{w}")
    out |= {"tfc:thatch", "rnr:thatch_roof", "rnr:thatch_roof_stairs", "rnr:thatch_roof_slab", "tfc:wattle/white", "tfc:wattle/unstained"}
    return out


def placement(cid, sset, regions, mode):
    climate = dict(sset.get("climate", {}))
    base = {"salt": sset["salt"], "spacing": sset["spacing"], "separation": sset["separation"]}
    if mode == "region":
        out = dict({"type": "pack_world:region"}, **base)
        out["spread_type"] = sset.get("spread_type", "linear")
        out["regions"] = [region_json(regions, n) for n in sset.get("regions", [])]
        if sset.get("exclude"):
            out["exclude"] = [region_json(regions, n) for n in sset["exclude"]]
        out["climate"] = climate
        out["outside"] = sset.get("outside", "never")
        return out
    return dict({"type": "tfc:climate"}, **base, climate=climate)


def check_set(where, sset, regions, problems, ctx):
    for k in ("salt", "spacing", "separation"):
        if k not in sset:
            problems.add(where, f"set needs {k}")
            return
    if sset["spacing"] <= sset["separation"]:
        problems.add(where, "spacing must exceed separation")
    if sset["spacing"] > 4096:
        problems.add(where, "spacing is capped at 4096 chunks")
    if not -2**31 <= sset["salt"] < 2**31:
        problems.add(where, f"salt {sset['salt']} must fit an int")
    for key in ("regions", "exclude"):
        for n in sset.get(key, []):
            if n not in regions:
                problems.add(where, f"{key}: unknown region {n!r}")
    if not sset.get("regions"):
        problems.add(where, "set has no regions (in mode \"region\" the village would never place)")
    climate = sset.get("climate", {})
    for k in climate:
        if k in REJECTED_CLIMATE:
            problems.add(where, f"climate.{k}: {REJECTED_CLIMATE[k]}")
        elif k not in CLIMATE_KEYS:
            problems.add(where, f"climate.{k} is not a field of tfc:climate")
    for k in ("min_forest", "max_forest"):
        if k in climate and not isinstance(climate[k], int):
            problems.add(where, f"climate.{k} must be an integer (forest density 0..4), not {climate[k]!r}")
    if climate.get("fuzzy") and not all(k in climate for k in ("min_temperature", "max_temperature", "min_groundwater", "max_groundwater")):
        problems.add(where, "fuzzy climate needs both temperature and groundwater bounds (it never places otherwise)")
    for lo, hi in (("min_temperature", "max_temperature"), ("min_groundwater", "max_groundwater")):
        if lo in climate and hi in climate and climate[lo] >= climate[hi]:
            problems.add(where, f"climate.{lo} is not below {hi}")
    for g in sset.get("landforms", []):
        if g not in ctx.landforms:
            problems.add(where, f"unknown landform group {g!r}")


def lint_graph(where, cid, vid, pools, names, links, problems):
    """Every jigsaw must name an existing pool and a target some element of that pool (or its fallbacks) can accept."""
    prefix = f"{NS}:village/{cid}/{vid}/"
    pool_pieces = {}
    for pname, pool in pools.items():
        pool_pieces[pname] = {e["piece"] for e in pool["elements"] if "piece" in e}
    npc_pools = {p for p, pool in pools.items() if any("npc" in e for e in pool["elements"])}

    def reachable(pname, seen=()):
        out = set(pool_pieces.get(pname, ()))
        fb = pools.get(pname, {}).get("fallback", "minecraft:empty")
        if fb != "minecraft:empty" and fb not in seen and fb in pools:
            out |= reachable(fb, seen + (pname,))
        return out

    reported = set()
    for piece, pool, target in links:
        if not pool.startswith(prefix):
            if pool != "minecraft:empty":
                problems.add(f"{where}/{piece}", f"jigsaw pool {pool} is outside {prefix}")
            continue
        pname = pool[len(prefix):]
        if pname not in pools:
            if (piece, pname) not in reported:
                problems.add(f"{where}/{piece}", f"jigsaw pool {pname!r} is not defined in this variant")
                reported.add((piece, pname))
            continue
        if pname in npc_pools:
            continue
        cands = reachable(pname)
        if cands and not any(target in names.get(c, ()) for c in cands):
            if (piece, pname, target) not in reported:
                problems.add(f"{where}/{piece}", f"jigsaw to {pname} wants {target}, which no piece of that pool offers")
                reported.add((piece, pname, target))


# ---------------------------------------------------------------------------------------------- jigsaw simulation (info)
DIRS = {"north": (0, 0, -1), "south": (0, 0, 1), "east": (1, 0, 0), "west": (-1, 0, 0), "up": (0, 1, 0), "down": (0, -1, 0)}
OPP = {"north": "south", "south": "north", "east": "west", "west": "east", "up": "down", "down": "up"}
CW = {"north": "east", "east": "south", "south": "west", "west": "north", "up": "up", "down": "down"}


def rot_dir(d, r):
    for _ in range(r):
        d = CW[d]
    return d


def rot_pos(p, r):
    x, y, z = p
    for _ in range(r):
        x, z = -z, x                      # clockwise 90 degrees about the origin, as StructureTemplate.transform does
    return (x, y, z)


class Tpl:
    """What the layout simulation needs of a piece: its size and its jigsaw blocks."""

    def __init__(self, size, jigs):
        self.size, self.jigs = size, jigs

    def box(self, r, origin):
        sx, sy, sz = self.size
        a = rot_pos((0, 0, 0), r)
        b = rot_pos((sx - 1, sy - 1, sz - 1), r)
        lo = tuple(min(a[i], b[i]) + origin[i] for i in range(3))
        hi = tuple(max(a[i], b[i]) + origin[i] for i in range(3))
        return lo, hi                      # inclusive cell ranges


def boxes_overlap(a, b):
    return all(a[0][i] <= b[1][i] and b[0][i] <= a[1][i] for i in range(3))


def box_inside(inner, outer):
    return all(outer[0][i] <= inner[0][i] and inner[1][i] <= outer[1][i] for i in range(3))


def simulate(cat, cid, vid, ctx, n=100, seed=1, layout=False):
    """Place villages of this variant the way vanilla's jigsaw placement does (flat ground, no terrain): the start piece, then breadth
    first every jigsaw of every piece in turn, pool elements tried in weight order (an empty element ends the attempt, the fallback pool
    follows), four rotations, a child must fit inside the max-distance box and clear of every placed piece (an NPC spot inside its parent's
    box need only fit there), depth limited by `size`. Returns (pieces per village, NPCs per village, mean extent in blocks, sample).
    A guide for weights, not the game's own count: heights, terrain adaptation and the exact shuffle order are not modelled."""
    N = ctx.N
    vc = deep_merge(cat["villages"].get("defaults", {}), cat["villages"][cid])
    v = deep_merge({"size": 6, "max_distance": 96}, vc["variants"][vid])
    pools = expand(v["pools"])
    depth_max, maxd = v["size"], v["max_distance"]
    root_dir = os.path.join(ctx.TEMPLATES, "village", cid, vid)
    pre = f"{NS}:village/{cid}/{vid}/"
    cache = {}

    def tpl(piece):
        if piece == "@npc":
            return Tpl((1, 1, 1), [((0, 0, 0), "down", "north", f"{NS}:npc_connector", "minecraft:empty", "minecraft:empty", "rollable")])
        if piece not in cache:
            path = os.path.join(root_dir, f"{piece}.nbt")
            if not os.path.exists(path):
                cache[piece] = None
            else:
                r = N.read(path)
                pal = r["palette"]
                jigs = []
                for b in r["blocks"]:
                    st = pal[int(b["state"])]
                    if st["Name"] == "minecraft:jigsaw":
                        nb = b.get("nbt") or {}
                        front, _, top = st["Properties"]["orientation"].partition("_")
                        jigs.append((tuple(int(c) for c in b["pos"]), front, top, nb.get("name", "minecraft:empty"), nb.get("target", "minecraft:empty"),
                                     nb.get("pool", "minecraft:empty"), nb.get("joint", "rollable")))
                cache[piece] = Tpl(tuple(int(c) for c in r["size"]), jigs)
        return cache[piece]

    def order(pname, rng):
        els = list(pools[pname]["elements"])
        out = []
        while els:
            x = rng.random() * sum(e.get("weight", 1) for e in els)
            for i, e in enumerate(els):
                x -= e.get("weight", 1)
                if x <= 0:
                    out.append(els.pop(i))
                    break
        return out

    def candidates(pname, rng):
        out = order(pname, rng)
        fb = pools[pname].get("fallback", "minecraft:empty")
        if fb in pools:
            out += order(fb, rng)
        return out

    rng = random.Random(seed)
    counts, npcs, extents = collections.Counter(), collections.Counter(), []
    sample = None
    for run in range(n):
        first = rng.choice(pools[v["start"]]["elements"])
        t0 = tpl(first["piece"])
        if t0 is None:
            return {}, {}, (0, 0), None
        r0 = rng.randrange(4)
        b0 = t0.box(r0, (0, 0, 0))
        cx, cz = (b0[0][0] + b0[1][0]) // 2, (b0[0][2] + b0[1][2]) // 2
        dist_box = ((cx - maxd, -10 ** 6, cz - maxd), (cx + maxd, 10 ** 6, cz + maxd))
        placed = [(first, t0, r0, (0, 0, 0), b0, 0)]
        boxes = [b0]
        queue = collections.deque([0])
        while queue:
            pi = queue.popleft()
            el, t, r, origin, box, depth = placed[pi]
            if depth >= depth_max:
                continue
            jigs = list(t.jigs)
            rng.shuffle(jigs)
            interior = []                    # children placed inside this piece's own box
            for pos, front, top, name, target, pool, joint in jigs:
                if not pool.startswith(pre) or pool[len(pre):] not in pools or target == "minecraft:empty":
                    continue
                pname = pool[len(pre):]
                gpos = tuple(rot_pos(pos, r)[i] + origin[i] for i in range(3))
                gfront = rot_dir(front, r)
                tc = tuple(gpos[i] + DIRS[gfront][i] for i in range(3))
                inside_parent = all(box[0][i] <= tc[i] <= box[1][i] for i in range(3))
                gtop = rot_dir(top, r)
                done = False
                for cand in candidates(pname, rng):
                    if "empty" in cand:
                        break
                    ct = tpl("@npc") if "npc" in cand else tpl(cand["piece"])
                    if ct is None:
                        continue
                    for cr in rng.sample(range(4), 4):
                        for cpos, cfront, ctop, cname, ctarget, cpool, cjoint in ct.jigs:
                            if cname != target or rot_dir(cfront, cr) != OPP[gfront]:
                                continue
                            if joint != "rollable" and rot_dir(ctop, cr) != gtop:
                                continue
                            corigin = tuple(tc[i] - rot_pos(cpos, cr)[i] for i in range(3))
                            cbox = ct.box(cr, corigin)
                            if inside_parent:
                                if not box_inside(cbox, box) or any(boxes_overlap(cbox, o) for o in interior):
                                    continue
                                interior.append(cbox)
                            else:
                                if not box_inside(cbox, dist_box) or any(boxes_overlap(cbox, o) for o in boxes):
                                    continue
                                boxes.append(cbox)
                            placed.append((cand, ct, cr, corigin, cbox, depth + 1))
                            queue.append(len(placed) - 1)
                            done = True
                            break
                        if done:
                            break
                    if done:
                        break
        for el, t, r, o, bx, d in placed:
            if "npc" in el:
                npcs[el["npc"]] += 1
            else:
                counts[el["piece"]] += 1
        lo = [min(b[0][i] for b in boxes) for i in (0, 2)]
        hi = [max(b[1][i] for b in boxes) for i in (0, 2)]
        extents.append((hi[0] - lo[0] + 1, hi[1] - lo[1] + 1))
        if layout and run == 0:
            sample = [(e.get("piece") or "@" + e.get("npc", "?"), r_, bx) for e, _, r_, _, bx, _ in placed]
    k = max(1, n)
    mean_ext = (round(sum(e[0] for e in extents) / k), round(sum(e[1] for e in extents) / k))
    return ({a: round(c / k, 2) for a, c in sorted(counts.items(), key=lambda kv: -kv[1])},
            {a: round(c / k, 2) for a, c in sorted(npcs.items())}, mean_ext, sample)


def ascii_layout(sample, width=110):
    """A top-down sketch of one simulated village: each piece's box filled with its letter (NPC spots are *)."""
    if not sample:
        return ""
    xs = [b[0][0] for _, _, b in sample] + [b[1][0] for _, _, b in sample]
    zs = [b[0][2] for _, _, b in sample] + [b[1][2] for _, _, b in sample]
    x0, z0 = min(xs), min(zs)
    w, h = max(xs) - x0 + 1, max(zs) - z0 + 1
    step = max(1, (w + width - 1) // width)
    names = {}
    grid = [["." for _ in range((w + step - 1) // step)] for _ in range((h + step - 1) // step)]
    for name, _, b in sample:
        if name.startswith("@"):
            letter = "*"
        else:
            letter = names.setdefault(name, chr(ord("A") + len(names) % 26))
        for z in range(b[0][2], b[1][2] + 1, step):
            for x in range(b[0][0], b[1][0] + 1, step):
                if letter != "*" or grid[(z - z0) // step][(x - x0) // step] != ".":
                    grid[(z - z0) // step][(x - x0) // step] = letter if letter != "*" else "*"
    legend = ", ".join(f"{v}={k}" for k, v in names.items())
    return "\n".join("".join(r) for r in grid) + f"\n({w} x {h} blocks, {step} per character) {legend}"
