"""Port TerraFirmaGreg's settlement templates to this pack (docs/lived-in.md, tools/README.md).

Usage (from the repo root):
    tools/.venv/Scripts/python tools/structures/tfg_import.py [--tfg DIR] [--out DIR] [--culture NAME ...] [--strict]
    tools/.venv/Scripts/python tools/structures/tfg_import.py fetch [--tfg DIR]        # clone TFG at the pinned commit

Reads the structure templates of TerraFirmaGreg's Modpack-Modern (LGPL-3.0, pinned commit below; its folder
kubejs/data/tfg/structures/{norse,arabic,malay,yurts,temperate,aqueduct}) and writes this pack's versions of them to
tools/structures/templates/village/<culture>/<variant>/<piece>.nbt, where build.py picks them up (the catalogue's "villages"
section names the pieces and their jigsaw pools). Deterministic: the same clone gives the same bytes. Re-run after editing the
tables below, never edit the output by hand.

What it changes (every converted file is a modified copy of TerraFirmaGreg's; see licenses/TerraFirmaGreg-structures.txt):
  - the data version (1.20.1 -> 1.21.1) and every block id: TFC 3 -> TFC 4 renames (soils, `planks/<wood>_door`-style ids),
    ArborFirmaCraft 2 and Firmalife 3 renames, then the substitutes for mods this pack dropped or can't get (Macaw's roofs and
    furniture, Domum Ornamentum, Firmalife, Carpeted, Firmaciv, Additional Placements, Chalk, TFG's own blocks). Mods the pack keeps
    (Framed Blocks, Roads and Roofs) stay where their blocks are the best shape available.
  - materials become the pack's placeholders, so pack_world:local_materials makes them local: every rock is `granite`, every soil
    `alfisol`, sand colour `yellow` (accent colours stay), and each culture's woods are ranked by use and become `oak` (most used),
    `spruce` and `birch`, in blocks, in Roads and Roofs shingles and in Framed Blocks camouflage.
  - block entities are stripped or rebuilt: inventories, authoring-world times, GregTech tools and other mods' data go; Framed Blocks
    keep their (remapped) camouflage; chests become TFC chests (build.py gives them the village's loot table); thatch beds keep
    their look. Entities (a plow cart) and ominous banners are dropped.
  - jigsaw blocks: pools and targets move into this pack (`pack:village/<culture>/<variant>/<pool>`, connector `pack:connector`),
    TFG's hostile "primitive illager" spawn spots (`mob_*` pools) point at peaceful Easy NPC pools or at nothing, and final states
    go through the block table.
Everything it could not map stays in the output under its original id (so build.py's lint fails on it), is counted and listed in the
report: tools/structures/templates/village/_import.json (per piece: size, blocks, jigsaws, substitutions) and the printed summary.
"""
import argparse
import collections
import glob
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
REPO = os.path.dirname(TOOLS)
sys.path.insert(0, HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(TOOLS, "recipes"))

import nbt as N  # noqa: E402

PIN = "1be1a1c4bb64c50807ff8f0988830b122557aac2"
REMOTE = "https://github.com/TerraFirmaGreg-Team/Modpack-Modern"
SRC = os.path.join("kubejs", "data", "tfg", "structures")
DEFAULT_TFG = os.path.join(TOOLS, ".data", "tfg-structures")
OUT_DEFAULT = os.path.join(HERE, "templates", "village")
DATA_VERSION = 3955  # Minecraft 1.21.1
NS = "pack"

# ----------------------------------------------------------------------------------------------------- what to import
# TFG folder -> pack variant, per culture. A variant lists the TFG folders its pieces come from: the burned variant reuses the
# ruined streets (copied, so their jigsaw pools point at the burned variant's own pools).
CULTURES = {
    "norse": {
        "src": "norse",
        "variants": {"living": ["baseline"], "ruined": ["ruins", "burned"], "burned": ["ruins", "burned"]},
        "names": {"norse_root": "gathering_shelter", "norse_longhouse": "longhouse", "norse_smithy": "smithy",
                  "norse_farmhouse": "farmhouse", "norse_farmhousebig": "large_farmhouse", "norse_mosshouse": "turf_house",
                  "norse_burial": "burial_mound"},
        "pool_names": {"start_pool": "start", "paths": "paths", "buildings": "buildings"},
        "villages": ("norse_village_living", "norse_village_ruined"),
        # mob spots -> Easy NPC pools of the pack (inhabited variants only; everything else is empty)
        "npc": {"mob_weak": "npc_commoner", "mob_outdoors": "npc_outdoors", "mob_gatherer": "npc_outdoors"},
        "npc_by_piece": {"smithy": {"mob_strong": "npc_smith"}},
    },
    "arabic": {
        "src": "arabic",
        "variants": {"living": ["baseline"]},
        "names": {"barracks": "caravanserai", "house1": "courtyard_house_1", "house2": "courtyard_house_2", "house3": "courtyard_house_3",
                  "house4": "courtyard_house_4", "stall_gray": "stall_grey", "house_garden": "garden_house"},
        "pool_names": {"start_pool": "start", "paths": "paths", "buildings": "buildings"},
        "villages": ("arabic_village_living",),
        "npc": {"mob_weak": "npc_commoner", "mob_outdoors": "npc_outdoors", "mob_gatherer": "npc_outdoors", "mob_goat": "npc_outdoors"},
        "npc_by_piece": {"smithy": {"mob_strong": "npc_smith"}, "well": {"mob_strong": "npc_outdoors"},
                         "caravanserai": {"mob_strong": "npc_merchant", "mob_ranged": "npc_commoner"}},
    },
    "malay": {
        "src": "malay",
        "variants": {"living": ["baseline"]},
        "names": {"smithy_start_pool": "smithy", "gadang": "rumah_gadang", "bujang_basic": "rumah_bujang_a",
                  "bujang_basic1": "rumah_bujang_b", "bujang_basic2": "rumah_bujang_c", "bujang_two_way": "rumah_bujang_dual_a",
                  "bujang_two_way1": "rumah_bujang_dual_b", "bujang_two_way2": "rumah_bujang_dual_c", "kitchen": "kitchen"},
        "pool_names": {"start_pool": "start", "paths": "paths", "buildings": "buildings"},
        "villages": ("malay_village_living",),
        "npc": {"mob_weak": "npc_commoner", "mob_outdoors": "npc_outdoors", "mob_gatherer": "npc_outdoors"},
        "npc_by_piece": {"smithy": {"mob_strong": "npc_smith"}, "kitchen": {"mob_weak": "npc_cook"}, "sloop": {"mob_weak": "npc_boatwright"}},
        "dead_targets": ["rumah_gandang_stilts"],       # the gadang stacks on itself through a jigsaw no other piece offers: unused
        "exclude": ["rumah_gadang"],                     # the rumah gadang is Minangkabau: see "minang"
        # TFG's kitchen, smithy and sloop have no mob spots: one NPC jigsaw on a floor cell of each
        "npc_spots": {"kitchen": ["npc_cook", "open"], "smithy": "npc_smith", "sloop": ["npc_boatwright", "open"]},
    },
    "minang": {                     # West Sumatra: the same buildings as malay, but the rumah gadang is Minangkabau and only stands here
        "src": "malay",
        "variants": {"living": ["baseline"]},
        "names": None,                # same names as malay
        "pool_names": {"start_pool": "start", "paths": "paths", "buildings": "buildings"},
        "villages": ("malay_village_living",),
        "same_as": "malay",
    },
    "steppe": {
        "src": "yurts",
        "variants": {"living": ["baseline"]},
        "names": {"throne_house": "gathering_tent", "monument": "deer_stones", "tower": "lookout", "house1": "yurt_1", "house2": "yurt_2",
                  "house3": "yurt_3", "shooting_range": "archery_ground"},
        "pool_names": {"start_pool": "start", "paths": "paths", "buildings": "buildings"},
        "villages": ("yurts_village_living",),
        "npc": {"mob_weak": "npc_commoner", "mob_outdoors": "npc_outdoors", "mob_gatherer": "npc_outdoors", "mob_horse": "npc_outdoors"},
        "npc_by_piece": {"workshop": {"mob_strong": "npc_feltmaker", "mob_ranged": "npc_feltmaker"}, "archery_ground": {"mob_ranged": "npc_bowyer"},
                         "stable": {"mob_horse": "npc_outdoors"}},
    },
    "temperate": {
        "src": "temperate",
        "variants": {"living": [""]},
        "names": {"plains_temperate_house_0_0": "farmhouse_a", "plains_temperate_house_0_1": "farmhouse_b", "plains_temperate_house_0_2": "farmhouse_c",
                  "plains_temperate_road_0_0": "track_a", "plains_temperate_road_0_1": "track_b"},
        "pool_names": {},
        "villages": (),
        "npc": {},
        "npc_by_piece": {},
        # TFG's farmhouses have no mob spots: put one NPC jigsaw on a floor cell inside each house (see find_spot)
        "npc_spots": {"farmhouse_a": "npc_farmer", "farmhouse_b": "npc_farmer", "farmhouse_c": "npc_farmer"},
    },
    "aqueduct": {
        "src": "aqueduct",
        "variants": {"main": [""]},
        "names": {},
        "pool_names": {},
        "villages": (),
        "npc": {},
        "npc_by_piece": {},
    },
}
POOL_RENAMES = {"plains_temperate_house_0_pool": "start", "plains_temperate_road_0_pool": "track", "aqueduct_pool": "start",
                "aqueduct_connector_pool": "connector", "aqueduct_leg_pool": "leg", "aqueduct_tank_pool": "tank"}
for _k, _c in list(CULTURES.items()):
    if _c.get("same_as"):
        _base = dict(CULTURES[_c["same_as"]])
        _base.update({k: v for k, v in _c.items() if k not in ("names", "same_as", "src") and v is not None})
        _base.pop("exclude", None)
        CULTURES[_k] = _base
STUB_DIRS = ("illager_generic", "mobs_generic")   # one-entity mob stubs: replaced by the pack's NPC pieces, never imported

# ------------------------------------------------------------------------------------------------------ block tables
TFC_WOODS = ["acacia", "ash", "aspen", "birch", "blackwood", "chestnut", "douglas_fir", "hickory", "kapok", "mangrove", "maple", "oak",
             "palm", "pine", "rosewood", "sequoia", "spruce", "sycamore", "white_cedar", "willow"]
AFC_WOODS = ["cypress", "mahogany", "teak", "ironwood", "baobab", "gum_arabic", "poplar", "eucalyptus", "fig", "ebony", "jacaranda"]
WOODS = TFC_WOODS + AFC_WOODS
WOOD_RE = "|".join(sorted(WOODS, key=len, reverse=True))
RANKS = ["oak", "spruce", "birch"]       # most used, second, third and every further wood of a culture (pack_world:local_materials "wood_ranks")
ROCK_RE = ("granite|diorite|gabbro|shale|claystone|limestone|conglomerate|dolomite|chert|chalk|tuff|rhyolite|basalt|andesite|dacite|"
           "quartzite|slate|phyllite|schist|gneiss|marble")
SOIL3_RE = "loam|sandy_loam|silt|silty_loam|alfisol|andisol|aridisol|entisol|fluvisol|mollisol|oxisol|podzol"
SOIL_BLOCKS = "grass|dirt|coarse_dirt|rooted_dirt|mud|clay|clay_grass|duff|clay_duff|farmland|grass_path|mud_bricks|drying_bricks|muddy_roots"
SAND_COLOURS = "brown|white|black|red|yellow|green|pink"
SHAPE_RE = r"(?P<shape>_stairs|_slab|_wall)?"
# wood variants that TFC 3 named `planks/<wood>_<variant>`
OLD_PLANK_VARIANTS = ("log_fence", "fence_gate", "fence", "door", "trapdoor", "tool_rack", "bookshelf", "workbench", "loom", "button",
                      "pressure_plate", "sign", "barrel", "chest", "sewing_table", "scribing_table")
ROAD_MARKER = "tfc:rock/bricks/andesite"   # TFG's marker for every road tile; the pools' rule processors turn it into paths

# Blocks that go away entirely (decor of mods the pack doesn't have, ominous banners, authoring-world props)
DROP = {"create:black_seat", "minecraft:white_wall_banner", "minecraft:white_banner", "minecraft:flower_pot", "minecraft:potted_cornflower", "create:white_table_cloth",
        "createaddition:chocolate_cake", "tfc:placed_item", "tfc:scraping", "tfc:ingot_pile", "tfc:double_ingot_pile", "firmalife:wood/hanger",
        "tfc:tree_roots"}
DROP_RE = [r"^chalk:", r"^tfg:.*_carpet$", r"^firmalife:wood/hanger/"]
# Vanilla carpets stay (floor decoration: the pack has them and the lint allows them); Domum Ornamentum's floating carpets become the carpet
# of their colour. A carpet that would hang in the air (nothing under it in the template, and not on the bottom layer) is dropped in convert():
# vanilla carpets pop off without support.
CARPET_COLOURS = {"white", "orange", "magenta", "light_blue", "yellow", "lime", "pink", "gray", "light_gray", "cyan", "purple", "blue", "brown", "green",
                  "red", "black"}
FLOATING_CARPET_RE = re.compile(r"^domum_ornamentum:(?P<c>[a-z_]+)_floating_carpet$")
# 1:1 renames after the soil/wood/rock folding (None = air)
EXACT = {
    "minecraft:cave_air": "minecraft:air", "minecraft:void_air": "minecraft:air",
    "minecraft:moss_block": "tfc:grass/alfisol", "minecraft:hay_block": "tfc:thatch", "minecraft:target": "tfc:thatch",
    "minecraft:bricks": "tfc:rock/bricks/granite", "minecraft:brick_stairs": "tfc:rock/bricks/granite_stairs",
    "minecraft:brick_slab": "tfc:rock/bricks/granite_slab", "minecraft:bone_block": "tfc:rock/chiseled/granite",
    "minecraft:campfire": "tfc:firepit", "minecraft:sandstone_slab": "tfc:cut_sandstone/yellow_slab",
    "tfc:wall_torch": "minecraft:wall_torch", "tfc:torch": "minecraft:torch",
    "domum_ornamentum:sand_stone_bricks": "tfc:cut_sandstone/yellow",
    "domum_ornamentum:blockpaperwall": "tfc:wattle/white", "domum_ornamentum:panel": "WOOD:planks:_slab",
    "domum_ornamentum:vanilla_slab_compat": "WOOD:planks:_slab",
    "tfg:charred_log": "WOOD:log", "tfg:ash_pile": "tfc:charcoal_pile", "tfg:gabbro_support": "tfc:rock/bricks/granite_wall",
    "tfg:grass/oxisol": "tfc:grass/alfisol", "tfg:grass_path/oxisol": "tfc:grass_path/alfisol",
    "firmaciv:watercraft_frame_flat": "WOOD:planks:_slab", "firmaciv:watercraft_frame_angled": "WOOD:planks:_stairs",
    "firmaciv:wood/blackwood_roofing": "WOOD:planks:_slab",
    "minecraft:ladder": "framedblocks:framed_ladder",
    "lootr:lootr_chest": "WOOD:chest",
    "tfc:log_pile": "WOOD:log",
    "tfc:drying_bricks/silt": "tfc:mud_bricks/alfisol",
    "rnr:tamped_loam": "rnr:tamped_alfisol",
    "firmalife:cured_oven_bottom": "tfc:mud_bricks/alfisol", "firmalife:cured_oven_top": "tfc:mud_bricks/alfisol",
    "firmalife:cured_oven_chimney": "tfc:mud_bricks/alfisol_wall", "createdeco:copper_sheet_metal": "tfc:metal/block/copper",
}
# Roads and Roofs blocks that stay as they are (no material in the id; the pack keeps the mod for roads and roofs)
RNR_KEEP = {"rnr:hoggin", "rnr:hoggin_slab", "rnr:thatch_roof", "rnr:thatch_roof_slab", "rnr:thatch_roof_stairs", "rnr:base_course", "rnr:tamped_alfisol"}
VANILLA_KEEP = {"minecraft:air", "minecraft:structure_void", "minecraft:jigsaw", "minecraft:water", "minecraft:torch", "minecraft:wall_torch"}
# Macaw's roofs (kapok_roofs in TFG) -> Roads and Roofs shingles; see roof_block(). Furniture: chairs -> stairs, tables -> slabs
MCW_ROOF_RE = re.compile(r"^mcw_tfc_aio:roofs/(?P<wood>[a-z_]+?)_roofs/(?P=wood)_(?P<kind>roof|lower_roof|upper_lower_roof|top_roof|steep_roof|upper_steep_roof|attic_roof)$")
MCW_FURN_RE = re.compile(r"^mcw_tfc_aio:furniture/[a-z_]+_furniture/(?:stripped_)?(?:%s)_(?P<kind>chair|stool_chair|table|coffee_table)$" % WOOD_RE)
MCW_PIER_RE = re.compile(r"^mcw_tfc_aio:bridges/")
VASE_RE = re.compile(r"^tfg:decorative_vase/(?:generated/)?(?P<colour>[a-z_]+)$")
VESSELS = {"magenta", "orange", "black", "brown", "yellow", "pink", "gray", "light_blue", "lime", "green", "red", "white", "blue", "purple",
           "light_gray", "cyan"}
OPPOSITE = {"north": "south", "south": "north", "east": "west", "west": "east"}
ROOF_MODE = "shingles"      # Malay roofs: "shingles" (Roads and Roofs stairs and slabs, the default) or "framed" (experimental), see roof_block()
UNKNOWN_PROPS = {"branch_direction", "placer", "attachments"}   # Dynamic Trees and TFG leftovers


def known_blocks():
    """The block registry of the newest recipe dump, to check every target id exists (None without a dump)."""
    try:
        from model import latest_dump
        dump = latest_dump()
    except (SystemExit, Exception):  # noqa: BLE001 - no dump on a fresh checkout: validation is skipped
        return None
    try:
        return set(json.load(open(os.path.join(dump, "blocks.json"), encoding="utf-8"))["ids"])
    except OSError:
        return None


class Result:
    """What one source block becomes: name, properties, block entity (or None) and how it was decided (for the report)."""
    __slots__ = ("name", "props", "nbt", "how")

    def __init__(self, name, props, nbt=None, how="map"):
        self.name, self.props, self.nbt, self.how = name, props, nbt, how


class Culture:
    """Per-culture state: wood ranks (by use) and the block mapper."""

    def __init__(self, key, cfg, known):
        self.key, self.cfg, self.known = key, cfg, known
        self.wood_use = collections.Counter()
        self.rank = {}
        self.report = collections.defaultdict(collections.Counter)    # how -> (source id -> target id) -> count
        self.unmapped = collections.Counter()
        self.missing_target = collections.Counter()

    # ---- wood ranks
    def count_wood(self, name, props, nbt):
        w = wood_of(name)
        if w:
            self.wood_use[w] += 1
        for k in ("camo", "camo_two"):
            c = (nbt or {}).get(k)
            if isinstance(c, dict) and isinstance(c.get("state"), dict):
                w = wood_of(c["state"].get("Name", ""))
                if w:
                    self.wood_use[w] += 1
        mimic = (nbt or {}).get("Mimic")
        if isinstance(mimic, dict):
            w = wood_of(mimic.get("Name", ""))
            if w:
                self.wood_use[w] += 1

    def assign_ranks(self):
        order = sorted(self.wood_use, key=lambda w: (-self.wood_use[w], w))
        self.rank = {w: RANKS[min(i, len(RANKS) - 1)] for i, w in enumerate(order)}
        self.order = order

    def wood(self, w):
        return self.rank.get(w, RANKS[-1])

    # ---- the block table
    def block(self, name, props, nbt):
        """Map one source block. Returns a Result (name None = removed)."""
        props = {k: v for k, v in (props or {}).items() if k not in UNKNOWN_PROPS}
        r = self._map(name, props, nbt)
        if r.name is not None and self.known is not None and r.name not in self.known and not r.name.startswith("easy_npc:"):
            self.missing_target[(name, r.name)] += 1
        return r

    def _map(self, name, props, nbt):
        if name in DROP or any(re.match(p, name) for p in DROP_RE):
            return Result(None, None, how="drop")
        if name == ROAD_MARKER:
            return Result(name, props, how="keep")
        m = FLOATING_CARPET_RE.match(name)
        if m and m.group("c") in CARPET_COLOURS:
            return Result(f"minecraft:{m.group('c')}_carpet", {}, how="carpet")
        m = re.match(r"^minecraft:(?P<c>[a-z_]+)_carpet$", name)
        if m and m.group("c") in CARPET_COLOURS:
            return Result(name, {}, how="carpet")
        if name in VANILLA_KEEP:
            return Result(name, props, nbt, how="keep")
        # Additional Placements: `additionalplacements:<ns>.<path with slashes>` is a placeable variant of the block it names
        m = re.match(r"^additionalplacements:([a-z_]+)\.(.+)$", name)
        if m:
            inner = f"{m.group(1)}:{m.group(2)}"
            p = {k: v for k, v in props.items() if k in ("facing", "half", "shape", "type", "waterlogged")}
            if p.get("type") not in (None, "bottom", "top", "double"):
                p["type"] = "bottom"
            r = self._map(inner, p, None)
            return Result(r.name, r.props, r.nbt, how="additionalplacements")
        m = VASE_RE.match(name)
        if m:
            c = m.group("colour")
            return Result(f"tfc:ceramic/large_vessel/{c if c in VESSELS else 'white'}", {}, how="vase")
        # Macaw's: roofs become Roads and Roofs shingles; furniture and piers become plain wood blocks
        m = MCW_ROOF_RE.match(name)
        if m:
            return self.roof_block(m.group("kind"), props, m.group("wood"))
        m = MCW_FURN_RE.match(name)
        if m:
            return self.furniture(m.group("kind"), name, props)
        if MCW_PIER_RE.match(name):
            return Result("tfc:wood/log/" + self.wood(self._wood_in(name)), {"axis": "y"}, how="mcw-pier")
        if name == "carpeted:carpet_slab":
            mimic = (nbt or {}).get("Mimic") or {}
            r = self._map(mimic.get("Name", "tfc:smooth_sandstone/yellow_slab"), dict(mimic.get("Properties") or {}), None)
            return Result(r.name, r.props, how="carpeted")
        e = EXACT.get(name)
        if e is not None:
            return self._finish_exact(name, e, props, nbt)
        r = self._fold(name, props, nbt)
        if r is not None:
            return r
        if self.known is not None and name in self.known and name.split(":")[0] in ("tfc", "framedblocks", "rnr", "easy_npc", "minecraft"):
            return Result(name, props, nbt, how="keep")
        self.unmapped[name] += 1
        return Result(name, props, nbt, how="UNMAPPED")

    def _finish_exact(self, name, target, props, nbt):
        if target.startswith("WOOD:"):
            parts = target.split(":")
            variant, suffix = parts[1], (parts[2] if len(parts) > 2 else "")
            w = self.wood(self._wood_in(name, nbt))
            p = dict(props)
            if variant == "chest":
                p = {k: v for k, v in p.items() if k in ("facing", "type")}
                return Result(f"tfc:wood/chest/{w}", p, how="lootr")
            if variant == "log":
                return Result(f"tfc:wood/log/{w}", {"axis": props.get("axis", "y")}, how="map")
            if suffix == "_slab":
                return Result(f"tfc:wood/planks/{w}_slab", {"type": props.get("type", "bottom") if props.get("type") in ("bottom", "top", "double") else "bottom"}, how="map")
            if suffix == "_stairs":
                return Result(f"tfc:wood/planks/{w}_stairs", {k: v for k, v in p.items() if k in ("facing", "half", "shape")}, how="map")
            return Result(f"tfc:wood/{variant}/{w}", p, how="map")
        if target == "tfc:charcoal_pile":
            return Result(target, {"layers": props.get("layers", "1")}, how="map")
        keep = {k: v for k, v in props.items()}
        if target in ("tfc:thatch", "tfc:rock/chiseled/granite", "tfc:rock/bricks/granite", "tfc:cut_sandstone/yellow", "tfc:wattle/white",
                      "tfc:grass/alfisol", "tfc:mud_bricks/alfisol"):
            keep = {}
        if target == "tfc:grass/alfisol":
            keep = {"snowy": "false"}
        if target in ("minecraft:torch", "minecraft:wall_torch"):
            keep = {k: v for k, v in props.items() if k == "facing"}
        if target == "tfc:firepit":
            keep = {}
        if target == "framedblocks:framed_ladder":
            keep = {k: v for k, v in props.items() if k in ("facing", "waterlogged")}
            camo = {"camo": {"type": "framedblocks:block", "state": {"Name": f"tfc:wood/planks/{RANKS[0]}"}}}
            return Result(target, keep, framed_be("framedblocks:framed_tile", camo["camo"]), how="ladder")
        if target.endswith(("_stairs", "_slab", "_wall")):
            keep = {k: v for k, v in props.items() if k in ("facing", "half", "shape", "type", "waterlogged", "north", "east", "south", "west", "up")}
        return Result(target, keep, how="exact")

    def _wood_in(self, name, nbt=None):
        w = wood_of(name)
        if w:
            return w
        if nbt:
            for k in ("camo", "textureData"):
                v = nbt.get(k)
                if isinstance(v, dict):
                    for x in (v.get("state", {}).get("Name", ""),) + tuple(str(y) for y in v.values()):
                        w = wood_of(x)
                        if w:
                            return w
        return self.order[0] if getattr(self, "order", None) else TFC_WOODS[0]

    # ---- folding into the pack's placeholders
    def _fold(self, name, props, nbt):
        # wood families: tfc:/afc:/firmalife: ids; the wood becomes its rank
        m = re.match(r"^(?:tfc|afc|firmalife):wood/(?P<variant>[a-z_]+)/(?:(?P<metal>[a-z_]+)/)?(?P<w>%s)(?P<shape>_stairs|_slab)?$" % WOOD_RE, name)
        if m and m.group("variant") not in ("keg", "big_barrel", "food_shelf", "stomping_barrel", "jar_shelf", "hanger", "jarbnet", "wine_shelf", "barrel_press"):
            v = m.group("variant")
            if v == "planks" and m.group("metal"):
                return None
            path = f"tfc:wood/{v}/" + (m.group("metal") + "/" if m.group("metal") else "") + self.wood(m.group("w")) + (m.group("shape") or "")
            return Result(path, self._wood_props(props, v), nbt_for(path, nbt), how="wood")
        if re.match(r"^tfc:wood/planks/palm_mosaic(?:_stairs|_slab)?$", name):       # TFC has a mosaic for palm only: a fixed accent
            return Result(name, props, how="keep")
        m = re.match(r"^(?:tfc|afc):wood/planks/(?P<w>%s)(?P<shape>_stairs|_slab)?$" % WOOD_RE, name)
        if m:
            path = f"tfc:wood/planks/{self.wood(m.group('w'))}{m.group('shape') or ''}"
            return Result(path, props, how="wood")
        m = re.match(r"^(?:tfc|afc):wood/planks/(?P<w>%s)_(?P<v>%s)$" % (WOOD_RE, "|".join(OLD_PLANK_VARIANTS)), name)
        if m:                                                      # TFC 3: planks/<wood>_door -> wood/door/<wood>
            path = f"tfc:wood/{m.group('v')}/{self.wood(m.group('w'))}"
            return Result(path, self._wood_props(props, m.group("v")), nbt_for(path, nbt), how="tfc3-wood")
        m = re.match(r"^(?:tfc|afc|firmalife):wood/(?:jar_shelf|food_shelf|hanger|wine_shelf)/(?P<w>%s)$" % WOOD_RE, name)
        if m:
            return Result(f"tfc:wood/shelf/{self.wood(m.group('w'))}", {k: v for k, v in props.items() if k in ("facing",)}, how="wood")
        m = re.match(r"^(?:afc|firmalife|tfc):wood/(?:keg|big_barrel|stomping_barrel|barrel_press)/(?P<w>%s)$" % WOOD_RE, name)
        if m:
            return Result(f"tfc:wood/barrel/{self.wood(m.group('w'))}", {}, how="barrel")
        m = re.match(r"^rnr:wood/shingles/(?P<w>%s)(?P<shape>_stairs|_slab)?$" % WOOD_RE, name)
        if m:
            return Result(f"rnr:wood/shingles/{self.wood(m.group('w'))}{m.group('shape') or ''}", props, how="shingles")
        # rock families fold into granite (the marker was returned before)
        m = re.match(r"^tfc:rock/(?P<v>[a-z_]+)/(?P<r>%s)%s$" % (ROCK_RE, SHAPE_RE), name)
        if m:
            return Result(f"tfc:rock/{m.group('v')}/granite{m.group('shape') or ''}", props, nbt_for(name, nbt), how="rock")
        m = re.match(r"^tfc:ore/(?P<g>[a-z_]+)/(?P<r>%s)$" % ROCK_RE, name)
        if m:
            return Result(f"tfc:ore/{m.group('g')}/granite", props, how="rock")
        m = re.match(r"^rnr:rock/(?P<v>[a-z_]+)/(?P<r>%s)(?P<shape>_stairs|_slab)?$" % ROCK_RE, name)
        if m:
            return Result(f"rnr:rock/{m.group('v')}/granite{m.group('shape') or ''}", props, how="rock")
        # soils (TFC 3's four loams and TFC 4's eight orders) fold into alfisol
        m = re.match(r"^tfc:(?P<b>%s)/(?P<s>%s)%s$" % (SOIL_BLOCKS, SOIL3_RE, SHAPE_RE), name)
        if m:
            return Result(f"tfc:{m.group('b')}/alfisol{m.group('shape') or ''}", props, None, how="soil")
        m = re.match(r"^tfc:mud/(?P<s>%s)$" % SOIL3_RE, name)
        if m:
            return Result("tfc:mud/alfisol", props, how="soil")
        m = re.match(r"^tfc:(?P<b>sand|raw_sandstone|smooth_sandstone|cut_sandstone)/(?P<c>%s)%s$" % (SAND_COLOURS, SHAPE_RE), name)
        if m and m.group("c") == "yellow":
            return Result(name, props, how="keep")
        if m:                                                      # accent colours stay fixed (red, brown, white, black trim)
            return Result(name, props, how="keep")
        if name == "tfc:wood/planks/jar_shelf":
            return None
        if name.startswith("tfc:plant/dead_grass") or name == "tfc:groundcover/dead_grass":
            return Result("tfc:plant/dry_grass", props, how="tfc3")
        if name == "tfc:wooden_bowl":
            return Result(name, {}, how="keep")
        if name == "tfc:thatch_bed":
            return Result(name, props, thatch_bed_be(), how="thatch-bed")
        if name.startswith("framedblocks:"):
            return Result(name, props, self.framed_be(nbt), how="framed")
        if name in RNR_KEEP:
            return Result(name, props, how="keep")
        m = re.match(r"^firmaciv:wood/watercraft_frame/(?P<k>flat|angled)/(?P<w>%s)$" % WOOD_RE, name)
        if m:
            w = self.wood(m.group("w"))
            if m.group("k") == "flat":
                return Result(f"tfc:wood/planks/{w}_slab", {"type": "bottom"}, how="firmaciv")
            return Result(f"tfc:wood/planks/{w}_stairs", {k: v for k, v in props.items() if k in ("facing", "half", "shape")}, how="firmaciv")
        if name.startswith("tfc:") and (name.startswith(("tfc:plant/", "tfc:ceramic/", "tfc:metal/block/", "tfc:wattle", "tfc:thatch", "tfc:dead_", "tfc:charcoal", "tfc:groundcover/",
                                                         "tfc:smooth_mud", "tfc:quern", "tfc:pot", "tfc:firepit", "tfc:barrel_rack", "tfc:berry", "tfc:bowl", "tfc:candle",
                                                         "tfc:fluid", "tfc:bellows"))):
            return Result(name, props, nbt_for(name, nbt), how="keep")
        return None

    def _wood_props(self, props, variant):
        p = dict(props)
        if variant == "leaves":
            p["persistent"] = "true"
        return p

    # ---- Framed Blocks keep their shape and camouflage; the camouflage block goes through the table (so its wood becomes a rank)
    def framed_be(self, nbt):
        if not nbt:
            return None
        out = {}
        for k in ("camo", "camo_two"):
            c = nbt.get(k)
            if isinstance(c, dict) and isinstance(c.get("state"), dict):
                st = c["state"]
                r = self.block(st.get("Name", "minecraft:air"), dict(st.get("Properties") or {}), None)
                if r.name is None:
                    r = Result("tfc:wood/planks/" + RANKS[0], {})
                state = {"Name": r.name}
                if r.props:
                    state["Properties"] = dict(r.props)
                out[k] = {"type": c.get("type", "framedblocks:block"), "state": state}
        if not out:
            return None
        res = {"id": nbt.get("id", "framedblocks:framed_tile")}
        res.update(out)
        for k in ("glowing", "intangible", "reinforced"):
            if k in nbt:
                res[k] = nbt[k]
        return res

    # ---- Macaw's roofs. Their blocks are stairs-like (facing, half, shape, waterlogged) with a 22.5 degree slope, built in pairs
    # of a "lower roof" (the upper part of the rise) and an "upper lower roof" (the lower part), so one block of rise per two of
    # run. Shingle stairs and slabs in the same cells give the same rise per run with half-block steps.
    def roof_block(self, kind, props, wood):
        w = self.wood(wood)                                   # the roof keeps the wood it was made of (its rank)
        if ROOF_MODE == "framed" and kind in ("lower_roof", "upper_lower_roof"):
            return self.framed_roof(kind, props, w)
        stairs = {k: v for k, v in props.items() if k in ("facing", "half", "shape", "waterlogged")}
        if kind in ("roof", "lower_roof", "steep_roof", "attic_roof"):
            return Result(f"rnr:wood/shingles/{w}_stairs", stairs, how="macaw-roof->shingle stairs")
        if kind in ("upper_lower_roof", "upper_steep_roof"):
            return Result(f"rnr:wood/shingles/{w}_slab", {"type": "top" if props.get("half") == "top" else "bottom"}, how="macaw-roof->shingle slab")
        return Result(f"rnr:wood/shingles/{w}_slab", {"type": "bottom"}, how="macaw-top->shingle slab")      # top_roof: the ridge

    def framed_roof(self, kind, props, w):
        """EXPERIMENTAL (--malay-roofs framed): the 1:2 slope as TFG's own yurts build it, a framed slope slab (the lower half of the rise) and an
        elevated one (the upper half) facing the high side like stairs; the property set is copied from the yurt roofs, not tested in game."""
        top = "true" if props.get("half") == "top" else "false"
        common = {"waterlogged": props.get("waterlogged", "false"), "solid": "true", "yslope": "true", "facing": props.get("facing", "north"),
                  "propagates_skylight": "false", "glowing": "false", "top": top}
        camo = {"type": "framedblocks:block", "state": {"Name": f"tfc:wood/planks/{w}"}}
        if kind == "upper_lower_roof":
            return Result("framedblocks:framed_slope_slab", dict(common, top_half="false"), framed_be("framedblocks:framed_tile", camo), how="macaw-roof->framed slope slab")
        return Result("framedblocks:framed_elevated_slope_slab", common, framed_be("framedblocks:framed_tile", camo), how="macaw-roof->framed elevated slope slab")

    def furniture(self, kind, name, props):
        w = self.wood(wood_of(name) or self.order[0])
        if kind in ("chair", "stool_chair"):
            facing = OPPOSITE.get(props.get("facing", "south"), "north")      # a chair faces the way you sit; a stair's tall side is its back
            return Result(f"tfc:wood/planks/{w}_stairs", {"facing": facing, "half": "bottom", "shape": "straight"}, how="mcw-chair")
        return Result(f"tfc:wood/planks/{w}_slab", {"type": "top" if kind == "table" else "bottom"}, how="mcw-table")


def wood_of(name):
    """The wood a block id is made of (TFC, ArborFirmaCraft, Firmalife, Roads and Roofs, Macaw's, TFC 3 style), or None."""
    if not isinstance(name, str):
        return None
    m = re.match(r"^(?:tfc|afc|firmalife|rnr):wood/(?:[a-z_]+/)+(?P<w>%s)(?:_mosaic)?(?:_stairs|_slab)?$" % WOOD_RE, name)
    if m:
        return m.group("w")
    m = re.match(r"^(?:tfc|afc):wood/planks/(?P<w>%s)(?:_mosaic)?(?:_stairs|_slab|_%s)?$" % (WOOD_RE, "|".join(OLD_PLANK_VARIANTS)), name)
    if m:
        return m.group("w")
    m = re.match(r"^mcw_tfc_aio:[a-z_]+/(?P<w>%s)_[a-z_]+/" % WOOD_RE, name) or re.match(r"^mcw_tfc_aio:.*?(?P<w>%s)_" % WOOD_RE, name)
    if m:
        return m.group("w")
    m = re.match(r"^afc:wood/(?:[a-z_]+/)+(?P<w>%s)$" % WOOD_RE, name)
    if m:
        return m.group("w")
    m = re.match(r"^firmaciv:wood/watercraft_frame/[a-z]+/(?P<w>%s)$" % WOOD_RE, name) or re.match(r"^firmaciv:wood/(?P<w>%s)_roofing$" % WOOD_RE, name)
    if m:
        return m.group("w")
    return None


def nbt_for(target, nbt):
    """The block entity a target block keeps: none for TFC's inventories and tick counters (they are authoring-world state)."""
    return None


def thatch_bed_be():
    """A thatch bed shows the block it is made of; its stored hide was in the 1.20 item format and goes."""
    thatch = {"Name": "tfc:thatch", "Properties": {"fluid": "empty"}}
    return {"id": "tfc:thatch_bed", "FootBlockState": dict(thatch), "HeadBlockState": dict(thatch), "inventory": {"Size": N.Int(1), "Items": N.List([], kind=N.COMPOUND)}}


def framed_be(id_, camo):
    return {"id": id_, "camo": camo, "glowing": N.Byte(0), "intangible": N.Byte(0), "reinforced": N.Byte(0)}


# ------------------------------------------------------------------------------------------------------- the importer
def parse_state(s):
    """'ns:block[a=b,c=d]' -> (name, props)"""
    m = re.match(r"^([^\[]+)(?:\[(.*)\])?$", s)
    props = {}
    if m.group(2):
        for kv in m.group(2).split(","):
            k, _, v = kv.partition("=")
            props[k.strip()] = v.strip()
    return m.group(1), props


def fmt_state(name, props):
    if not props:
        return name
    return name + "[" + ",".join(f"{k}={v}" for k, v in sorted(props.items())) + "]"


def to_str_props(d):
    return {str(k): str(v) for k, v in (d or {}).items()}


def find_spot(grid, size, mode="room"):
    """A floor cell for an NPC: solid, two free cells above it; mode "room" (inside a building) also wants a roof within eight blocks and
    a wall in each direction within six, mode "open" takes any floor. The lowest floor first, then the closest to the template's
    centre. (x, y, z) or None."""
    sx, sy, sz = size
    cx, cz = (sx - 1) / 2, (sz - 1) / 2
    airish = ("minecraft:air", "minecraft:structure_void", None)

    def solid(c):
        b = grid.get(c)
        return b is not None and b[0] not in airish and b[0] != "minecraft:jigsaw" and not b[0].startswith(("tfc:plant/", "tfc:groundcover/"))

    def free(c):
        b = grid.get(c)
        return b is None or b[0] in ("minecraft:air", "minecraft:structure_void")

    best = None
    for (x, y, z), (name, _) in grid.items():
        if not solid((x, y, z)) or not free((x, y + 1, z)) or not free((x, y + 2, z)):
            continue
        if mode == "room":
            if not any(solid((x, y + k, z)) for k in range(3, 9)):
                continue
            if not all(any(solid((x + dx * k, y + h, z + dz * k)) for k in range(1, 7) for h in (1, 2)) for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                continue
        key = (y, (x - cx) ** 2 + (z - cz) ** 2, x, z)
        if best is None or key < best:
            best = key
    return None if best is None else (best[2], best[0], best[3])


class Importer:
    def __init__(self, tfg_dir, out_dir, only=None, known=None):
        self.tfg, self.out = tfg_dir, out_dir
        self.only = set(only or CULTURES)
        self.known = known
        self.index = {}
        self.cultures = {}
        self.notes = []

    # ---- sources
    def sources(self, cult):
        cfg = CULTURES[cult]
        base = os.path.join(self.tfg, SRC, cfg["src"])
        out = {}                                              # variant -> [(tfg subdir, path)]
        for variant, dirs in cfg["variants"].items():
            files = []
            for d in dirs:
                folder = os.path.join(base, d) if d else base
                for f in sorted(glob.glob(os.path.join(folder, "*.nbt"))):
                    if self.piece_name(cult, f, d) in cfg.get("exclude", ()):
                        continue
                    files.append((d, f))
            out[variant] = files
        return out

    def piece_name(self, cult, fname, sub=""):
        base = os.path.splitext(os.path.basename(fname))[0]
        cfg = CULTURES[cult]
        stripped = re.sub(r"_(base|ruin|burn)$", "", base)
        name = cfg["names"].get(stripped, cfg["names"].get(base, stripped))
        return name + "_burned" if sub == "burned" else name      # a burned piece and the ruin of the same building are two pieces

    # ---- one template
    def convert(self, cult, variant, piece, path):
        cfg = CULTURES[cult]
        c = self.cultures[cult]
        root = N.read(path)
        pal = root["palette"]
        states = [(e["Name"], to_str_props(e.get("Properties"))) for e in pal]
        out_palette, index, blocks = [], {}, []
        stats = collections.Counter()
        jig = collections.Counter()
        not_solid = ("minecraft:air", "minecraft:cave_air", "minecraft:void_air", "minecraft:structure_void", "minecraft:jigsaw")
        solid_src = {tuple(int(v) for v in b["pos"]) for b in root["blocks"] if states[int(b["state"])][0] not in not_solid}
        for b in root["blocks"]:
            name, props = states[int(b["state"])]
            nbt = b.get("nbt")
            pos = [int(v) for v in b["pos"]]
            if name == "minecraft:jigsaw":
                # TFG put most of its mob jigsaws in the air cell right above a floor: the piece hung on one is a cell too high, so those name the `_low` twin of the pool
                low = (pos[0], pos[1] - 1, pos[2]) in solid_src
                j = self.jigsaw(cult, variant, piece, props, nbt, jig, low)
                res = Result("minecraft:jigsaw", {"orientation": props.get("orientation", "up_north")}, j, how="jigsaw")
            else:
                res = c.block(name, props, nbt)
                if res.how == "drop":
                    stats["dropped"] += 1
                    c.report["drop"][name] += 1
                    continue
                if res.how == "UNMAPPED":
                    stats["unmapped"] += 1
                else:
                    c.report[res.how][(name, res.name)] += 1
            if res.name is None:
                continue
            nb = res.nbt
            if nb is not None:
                nb = dict(nb)
            if res.name.startswith("tfc:wood/chest/"):
                nb = {"id": "tfc:chest"}
            key = (res.name, tuple(sorted((res.props or {}).items())))
            if key not in index:
                index[key] = len(out_palette)
                entry = {"Name": res.name}
                if res.props:
                    entry["Properties"] = dict(sorted(res.props.items()))
                out_palette.append(entry)
            nb_ = {"pos": N.List([N.Int(v) for v in pos]), "state": N.Int(index[key])}
            if nb is not None:
                nb_["nbt"] = nb
            blocks.append(nb_)
            if res.name not in ("minecraft:air", "minecraft:structure_void", "minecraft:jigsaw"):
                stats["blocks"] += 1
            stats["total"] += 1
        # carpets need something to lie on (vanilla pops them off otherwise): drop the ones over air inside the template
        solid_at = {tuple(int(v) for v in nb_["pos"]) for nb_ in blocks
                    if out_palette[int(nb_["state"])]["Name"] not in ("minecraft:air", "minecraft:structure_void", "minecraft:jigsaw")
                    and not out_palette[int(nb_["state"])]["Name"].endswith("_carpet")}
        kept = []
        for nb_ in blocks:
            p_ = tuple(int(v) for v in nb_["pos"])
            if out_palette[int(nb_["state"])]["Name"].endswith("_carpet") and p_[1] > 0 and (p_[0], p_[1] - 1, p_[2]) not in solid_at:
                stats["dropped"] += 1
                stats["blocks"] -= 1
                stats["total"] -= 1
                c.report["drop"]["minecraft:*_carpet (nothing under it)"] += 1
                continue
            kept.append(nb_)
        blocks = kept
        spot_pool = cfg.get("npc_spots", {}).get(piece)
        if spot_pool and variant == "living":
            spot_pool, spot_mode = spot_pool if isinstance(spot_pool, (list, tuple)) else (spot_pool, "room")
            grid = {tuple(int(v) for v in nb_["pos"]): (out_palette[int(nb_["state"])]["Name"], out_palette[int(nb_["state"])].get("Properties")) for nb_ in blocks}
            spot = find_spot(grid, [int(v) for v in root["size"]], spot_mode)
            if spot is None:
                self.notes.append(f"{cult}/{variant}/{piece}: no floor cell for an NPC spot")
            else:
                floor_name, floor_props = grid[spot]
                state = len(out_palette)
                out_palette.append({"Name": "minecraft:jigsaw", "Properties": {"orientation": "up_north"}})
                for i, nb_ in enumerate(blocks):
                    if tuple(int(v) for v in nb_["pos"]) == spot:
                        blocks[i] = {"pos": nb_["pos"], "state": N.Int(state), "nbt": {
                            "id": "minecraft:jigsaw", "name": "minecraft:empty", "target": f"{NS}:npc_connector",
                            "pool": f"{NS}:village/{cult}/{variant}/{spot_pool}", "joint": "rollable",
                            "final_state": fmt_state(floor_name, floor_props or {})}}
                        break
                jig[("minecraft:empty", f"{NS}:npc_connector", f"{NS}:village/{cult}/{variant}/{spot_pool}")] += 1
                stats["npc_spot"] = list(spot)
        # an air block is only worth keeping inside the template's box (it carves); keep them all, they are the interiors
        template = {"DataVersion": N.Int(DATA_VERSION), "size": N.List([N.Int(v) for v in root["size"]]),
                    "palette": N.List(out_palette, kind=N.COMPOUND), "blocks": N.List(blocks, kind=N.COMPOUND),
                    "entities": N.List([], kind=N.COMPOUND)}
        dropped_entities = [str(e["nbt"].get("id")) for e in root.get("entities", [])]
        return template, stats, jig, dropped_entities

    def jigsaw(self, cult, variant, piece, props, nbt, counter, low=False):
        cfg = CULTURES[cult]
        nbt = nbt or {}
        pool = nbt.get("pool", "minecraft:empty")
        name = nbt.get("name", "minecraft:empty")
        target = nbt.get("target", "minecraft:empty")
        new_pool = self.pool(cult, variant, piece, pool)
        new_name = self.connector(name)
        new_target = self.connector(target)
        if any(d in target or d in name for d in cfg.get("dead_targets", ())):
            new_pool, new_target, new_name = "minecraft:empty", "minecraft:empty", "minecraft:empty"
        final = nbt.get("final_state", "minecraft:air")
        fn, fp = parse_state(final)
        r = self.cultures[cult].block(fn, fp, None)
        final_state = "minecraft:air" if r.name is None else fmt_state(r.name, r.props)
        if low and final_state == "minecraft:air" and new_pool != "minecraft:empty" and pool.split("/")[-1].startswith("mob_"):
            new_pool += "_low"
        counter[(new_name, new_target, new_pool)] += 1
        return {"id": "minecraft:jigsaw", "name": new_name, "target": new_target, "pool": new_pool, "joint": nbt.get("joint", "rollable"),
                "final_state": final_state}

    @staticmethod
    def connector(n):
        if n in ("minecraft:empty", ""):
            return "minecraft:empty"
        short = n.split(":")[-1]
        if short == "":                                      # a few TFG jigsaws target "minecraft:" (nothing)
            return "minecraft:empty"
        if short == "any_connector":
            return f"{NS}:connector"
        if short == "mob_connector":
            return f"{NS}:npc_connector"
        short = short.replace("aquaduct_", "aqueduct_").replace("plains_temperate_", "")     # TFG's own typo in two aqueduct targets
        return f"{NS}:{short}"

    def pool(self, cult, variant, piece, pool):
        cfg = CULTURES[cult]
        if pool in ("minecraft:empty", ""):
            return "minecraft:empty"
        short = pool.split("/")[-1]
        m = re.match(r"^(?P<v>[a-z]+_village_(?:living|ruined))_(?P<k>start_pool|buildings|paths)$", short)
        if m:
            kind = cfg["pool_names"].get(m.group("k"), m.group("k"))
            return f"{NS}:village/{cult}/{variant}/{kind}"
        if short.startswith("mob_"):
            if variant != "living":
                return "minecraft:empty"
            pool_map = dict(cfg["npc"])
            pool_map.update(cfg["npc_by_piece"].get(piece, {}))
            tgt = pool_map.get(short)
            return f"{NS}:village/{cult}/{variant}/{tgt}" if tgt else "minecraft:empty"
        # temperate and aqueduct name their own pools (house/road stubs, legs, connectors)
        m = re.match(r"^tfg:(?:temperate|aqueduct)/(?P<n>[a-z0-9_]+)$", pool)
        if m and m.group("n") in POOL_RENAMES:
            return f"{NS}:village/{cult}/{variant}/{POOL_RENAMES[m.group('n')]}"
        self.unknown_pools.add(pool)
        return pool

    # ---- the run
    def run(self):
        self.unknown_pools = set()
        summary = {}
        index = {}
        for cult in CULTURES:
            if cult not in self.only:
                continue
            c = Culture(cult, CULTURES[cult], self.known)
            self.cultures[cult] = c
            srcs = self.sources(cult)
            files = [(v, p) for v, lst in srcs.items() for _, p in lst]
            if not files:
                print(f"{cult}: no templates under {os.path.join(self.tfg, SRC, CULTURES[cult]['src'])}", file=sys.stderr)
                continue
            # wood ranks come from every template of the culture, counted once per source file
            seen = set()
            for v, p in files:
                if p in seen:
                    continue
                seen.add(p)
                r = N.read(p)
                st = [(e["Name"], to_str_props(e.get("Properties"))) for e in r["palette"]]
                for b in r["blocks"]:
                    n, pr = st[int(b["state"])]
                    c.count_wood(n, pr, b.get("nbt"))
            c.assign_ranks()
            shutil.rmtree(os.path.join(self.out, cult), ignore_errors=True)       # no orphans from an earlier naming
            index[cult] = {"woods": {w: {"blocks": c.wood_use[w], "rank": c.rank[w]} for w in c.order}, "pieces": {}}
            for variant, lst in srcs.items():
                for d, path in lst:
                    piece = self.piece_name(cult, path, d)
                    tpl, stats, jig, ents = self.convert(cult, variant, piece, path)
                    dest = os.path.join(self.out, cult, variant, piece + ".nbt")
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    N.write(dest, tpl)
                    index[cult]["pieces"][f"{variant}/{piece}"] = {
                        "source": os.path.join(SRC, CULTURES[cult]["src"], d, os.path.basename(path)).replace("\\", "/"),
                        "size": [int(v) for v in tpl["size"]], "blocks": stats["blocks"], "dropped": stats["dropped"], "unmapped": stats["unmapped"],
                        "dropped_entities": ents, "npc_spot": stats.get("npc_spot"),
                        "jigsaws": [{"name": k[0], "target": k[1], "pool": k[2], "count": n} for k, n in sorted(jig.items())]}
            summary[cult] = c
        self.index = index
        self.summary = summary
        return index

    def write_report(self):
        rep = {"tfg_commit": PIN, "data_version": DATA_VERSION, "cultures": self.index, "unmapped": {}, "missing_targets": {}, "substitutions": {}}
        for cult, c in self.summary.items():
            rep["unmapped"][cult] = dict(sorted(c.unmapped.items(), key=lambda kv: -kv[1]))
            rep["missing_targets"][cult] = [{"from": a, "to": b, "count": n} for (a, b), n in sorted(c.missing_target.items(), key=lambda kv: -kv[1])]
            subs = {}
            for how, m in sorted(c.report.items()):
                if how in ("keep", "jigsaw"):
                    continue
                subs[how] = sum(m.values()) if how == "drop" else {f"{a} -> {b}": n for (a, b), n in sorted(m.items(), key=lambda kv: -kv[1])}
            rep["substitutions"][cult] = subs
        rep["unknown_pools"] = sorted(self.unknown_pools)
        path = os.path.join(self.out, "_import.json")
        if os.path.exists(path) and set(self.summary) != set(CULTURES):          # a partial run keeps the other cultures' entries
            old = json.load(open(path, encoding="utf-8"))
            for key in ("cultures", "unmapped", "missing_targets", "substitutions"):
                merged = dict(old.get(key, {}))
                merged.update(rep[key])
                rep[key] = {c: merged[c] for c in CULTURES if c in merged}
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(rep, indent=1, ensure_ascii=False) + "\n")
        return rep


# ------------------------------------------------------------------------------------------------------------ main
def fetch(tfg):
    if os.path.isdir(os.path.join(tfg, ".git")):
        subprocess.check_call(["git", "-C", tfg, "fetch", "--depth", "1", "origin", PIN])
    else:
        os.makedirs(tfg, exist_ok=True)
        subprocess.check_call(["git", "init", tfg])
        subprocess.check_call(["git", "-C", tfg, "remote", "add", "origin", REMOTE])
        subprocess.check_call(["git", "-C", tfg, "fetch", "--depth", "1", "--filter=blob:none", "origin", PIN])
    subprocess.check_call(["git", "-C", tfg, "sparse-checkout", "set", "--no-cone", "/kubejs/data/tfg/structures/", "/LICENSE"])
    subprocess.check_call(["git", "-C", tfg, "checkout", "--force", PIN])


def pinned(tfg):
    try:
        head = subprocess.check_output(["git", "-C", tfg, "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return head


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", nargs="?", default="import", choices=["import", "fetch"])
    ap.add_argument("--tfg", default=DEFAULT_TFG, help="TerraFirmaGreg clone (default tools/.data/tfg-structures; `fetch` makes it)")
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--culture", nargs="*", help="only these cultures (default all): " + ", ".join(CULTURES))
    ap.add_argument("--strict", action="store_true", help="exit 1 when a block could not be mapped or a target block does not exist")
    ap.add_argument("--no-validate", action="store_true", help="don't check target ids against the newest recipe dump")
    ap.add_argument("--malay-roofs", choices=["shingles", "framed"], default="shingles",
                    help="what Macaw's roofs become: Roads and Roofs shingle stairs and slabs (default, drawn faithfully by render.py) or Framed Blocks "
                         "slope slabs (exact 1:2 slope, copied from TFG's yurts, untested in game); write to another --out to compare")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    global ROOF_MODE
    ROOF_MODE = args.malay_roofs
    tfg = os.path.abspath(args.tfg)
    if args.action == "fetch":
        fetch(tfg)
        print(f"TFG at {PIN} in {tfg}")
        return 0
    head = pinned(tfg)
    if head is None:
        print(f"{tfg} is not a git clone: run `tfg_import.py fetch` (or pass --tfg)", file=sys.stderr)
        return 2
    if head != PIN:
        print(f"{tfg} is at {head[:12]}, the importer is written for {PIN[:12]}; check out the pinned commit", file=sys.stderr)
        return 2
    known = None if args.no_validate else known_blocks()
    if known is None and not args.no_validate:
        print("(no recipe dump: target ids are not checked against the block registry)", file=sys.stderr)
    imp = Importer(tfg, os.path.abspath(args.out), args.culture, known)
    imp.run()
    rep = imp.write_report()
    total_unmapped = 0
    print(f"TerraFirmaGreg {PIN[:12]} -> {os.path.relpath(args.out, REPO) if args.out.startswith(REPO) else args.out}")
    for cult, c in imp.summary.items():
        pieces = rep["cultures"][cult]["pieces"]
        blocks = sum(p["blocks"] for p in pieces.values())
        print(f"\n{cult}: {len(pieces)} templates, {blocks} blocks; woods "
              + ", ".join(f"{w}->{r['rank']} ({r['blocks']})" for w, r in rep["cultures"][cult]["woods"].items()))
        drop = c.report.get("drop", {})
        if drop:
            print(f"  dropped {sum(drop.values())}: " + ", ".join(f"{k} x{n}" for k, n in drop.most_common()))
        for how, m in sorted(c.report.items()):
            if how in ("keep", "drop", "jigsaw", "wood", "tfc3-wood", "soil", "rock", "shingles", "map", "exact", "tfc3"):
                continue
            print(f"  {how}: " + ", ".join(f"{a} -> {b} x{n}" for (a, b), n in sorted(m.items(), key=lambda kv: -kv[1])[:6]))
        if c.unmapped:
            total_unmapped += sum(c.unmapped.values())
            print(f"  UNMAPPED ({sum(c.unmapped.values())} blocks): " + ", ".join(f"{k} x{n}" for k, n in c.unmapped.most_common()))
        if c.missing_target:
            total_unmapped += sum(c.missing_target.values())
            print(f"  targets missing from the registry: " + ", ".join(f"{a} -> {b} x{n}" for (a, b), n in c.missing_target.most_common()))
    for note in imp.notes:
        print("  note: " + note)
    if imp.unknown_pools:
        print("\nunknown jigsaw pools (left as they were): " + ", ".join(sorted(imp.unknown_pools)))
    print(f"\nreport: {os.path.join(args.out, '_import.json')}")
    return 1 if (args.strict and (total_unmapped or imp.unknown_pools)) else 0


if __name__ == "__main__":
    sys.exit(main())
