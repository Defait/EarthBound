"""Generates the structure skin's block table: every vanilla block -> its TFC counterpart (or left alone / removed).

    tools/.venv/Scripts/python tools/structure_mods/skin_table.py [--dump DIR] [--check] [--census FILE]

Writes kubejs/data/pack/pack_world/structure_skin/blocks.json from the rules below. The skin (mod/, `pack_world`) applies the table
to the blocks a configured structure wrote (docs/lived-in.md, "Structure skin"). A target is a TFC block id; when its material
is a placeholder (granite for rock, oak/spruce/acacia for the woods in rank order, alfisol for soil, yellow for sand) the skin
makes it the local rock / climate tree / column soil / local sand, with the andesite-alloy rule applied. "@air" removes a block,
"@keep" leaves it (decoration with no TFC counterpart: glass, torches, rails, spawners ...).

Every vanilla block id of the newest recipe dump gets an entry, so the in-game counter of blocks without a rule only ever shows
ids that arrived after this table was made. --check prints what the rules leave vanilla, weighted by the structure templates'
block counts (tools/structure_mods/census.py --json), so gaps are easy to see.
"""
import argparse
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(REPO, "kubejs", "data", "pack", "pack_world", "structure_skin", "blocks.json")
DUMPS = os.path.join(REPO, "tools", ".data", "dumps")

# Vanilla wood -> wood placeholder (rank 0 = oak = the climate's best-fitting tree, 1 = spruce, 2 = acacia).
WOODS = {"oak": "oak", "birch": "oak", "cherry": "oak", "bamboo": "oak", "spruce": "spruce", "dark_oak": "spruce",
         "jungle": "acacia", "acacia": "acacia", "mangrove": "acacia", "crimson": "acacia", "warped": "acacia"}
COLORS = ["white", "orange", "magenta", "light_blue", "yellow", "lime", "pink", "gray", "light_gray", "cyan", "purple", "blue",
          "brown", "green", "red", "black"]
SHAPES = ["_slab", "_stairs", "_wall"]
KEEP = "@keep"
AIR = "@air"

# Exact entries; everything else goes through the families below. Values are TFC ids, "@keep" or "@air".
EXACT = {
    # stone and rock
    "stone": "tfc:rock/raw/granite", "infested_stone": "tfc:rock/raw/granite", "andesite": "tfc:rock/raw/granite",
    "diorite": "tfc:rock/raw/granite", "granite": "tfc:rock/raw/granite", "basalt": "tfc:rock/raw/granite",
    "blackstone": "tfc:rock/raw/granite", "deepslate": "tfc:rock/raw/granite", "infested_deepslate": "tfc:rock/raw/granite",
    "tuff": "tfc:rock/raw/granite", "calcite": "tfc:rock/raw/granite", "dripstone_block": "tfc:rock/raw/granite",
    "netherrack": "tfc:rock/raw/granite", "end_stone": "tfc:rock/raw/granite", "reinforced_deepslate": "tfc:rock/raw/granite",
    "magma_block": "tfc:rock/raw/granite", "obsidian": "tfc:rock/raw/granite", "crying_obsidian": "tfc:rock/raw/granite",
    "ancient_debris": "tfc:rock/raw/granite", "gilded_blackstone": "tfc:rock/raw/granite", "amethyst_block": "tfc:rock/raw/granite",
    "bone_block": "tfc:alabaster/polished/white", "smooth_basalt": "tfc:rock/smooth/granite",
    "cobblestone": "tfc:rock/cobble/granite", "infested_cobblestone": "tfc:rock/cobble/granite", "cobbled_deepslate": "tfc:rock/cobble/granite",
    "mossy_cobblestone": "tfc:rock/mossy_cobble/granite",
    "stone_bricks": "tfc:rock/bricks/granite", "infested_stone_bricks": "tfc:rock/bricks/granite", "bricks": "tfc:rock/bricks/granite",
    "deepslate_bricks": "tfc:rock/bricks/granite", "deepslate_tiles": "tfc:rock/bricks/granite", "nether_bricks": "tfc:rock/bricks/granite",
    "red_nether_bricks": "tfc:rock/bricks/granite", "end_stone_bricks": "tfc:rock/bricks/granite", "tuff_bricks": "tfc:rock/bricks/granite",
    "polished_blackstone_bricks": "tfc:rock/bricks/granite", "prismarine_bricks": "tfc:rock/bricks/granite", "prismarine": "tfc:rock/bricks/granite",
    "dark_prismarine": "tfc:rock/bricks/granite", "quartz_bricks": "tfc:rock/bricks/granite",
    "cracked_stone_bricks": "tfc:rock/cracked_bricks/granite", "infested_cracked_stone_bricks": "tfc:rock/cracked_bricks/granite",
    "cracked_deepslate_bricks": "tfc:rock/cracked_bricks/granite", "cracked_deepslate_tiles": "tfc:rock/cracked_bricks/granite",
    "cracked_nether_bricks": "tfc:rock/cracked_bricks/granite", "cracked_polished_blackstone_bricks": "tfc:rock/cracked_bricks/granite",
    "mossy_stone_bricks": "tfc:rock/mossy_bricks/granite", "infested_mossy_stone_bricks": "tfc:rock/mossy_bricks/granite",
    "chiseled_stone_bricks": "tfc:rock/chiseled/granite", "infested_chiseled_stone_bricks": "tfc:rock/chiseled/granite",
    "chiseled_deepslate": "tfc:rock/chiseled/granite", "chiseled_nether_bricks": "tfc:rock/chiseled/granite",
    "chiseled_polished_blackstone": "tfc:rock/chiseled/granite", "chiseled_tuff": "tfc:rock/chiseled/granite",
    "chiseled_tuff_bricks": "tfc:rock/chiseled/granite", "chiseled_copper": "tfc:rock/chiseled/granite",
    "smooth_stone": "tfc:rock/smooth/granite", "polished_andesite": "tfc:rock/smooth/granite", "polished_diorite": "tfc:rock/smooth/granite",
    "polished_granite": "tfc:rock/smooth/granite", "polished_deepslate": "tfc:rock/smooth/granite", "polished_blackstone": "tfc:rock/smooth/granite",
    "polished_basalt": "tfc:rock/smooth/granite", "polished_tuff": "tfc:rock/smooth/granite",
    "stone_button": "tfc:rock/button/granite", "polished_blackstone_button": "tfc:rock/button/granite",
    "stone_pressure_plate": "tfc:rock/pressure_plate/granite", "polished_blackstone_pressure_plate": "tfc:rock/pressure_plate/granite",
    "stone_slab": "tfc:rock/raw/granite_slab", "stone_stairs": "tfc:rock/raw/granite_stairs", "smooth_stone_slab": "tfc:rock/smooth/granite_slab",
    "petrified_oak_slab": "tfc:wood/planks/oak_slab",
    # sand, sandstone, gravel
    "sand": "tfc:sand/yellow", "red_sand": "tfc:sand/yellow", "suspicious_sand": "tfc:sand/yellow", "gravel": "tfc:rock/gravel/granite",
    "suspicious_gravel": "tfc:rock/gravel/granite", "soul_sand": "tfc:sand/yellow", "soul_soil": "tfc:dirt/alfisol",
    "sandstone": "tfc:raw_sandstone/yellow", "red_sandstone": "tfc:raw_sandstone/yellow", "smooth_sandstone": "tfc:smooth_sandstone/yellow",
    "smooth_red_sandstone": "tfc:smooth_sandstone/yellow", "cut_sandstone": "tfc:cut_sandstone/yellow", "cut_red_sandstone": "tfc:cut_sandstone/yellow",
    "chiseled_sandstone": "tfc:cut_sandstone/yellow", "chiseled_red_sandstone": "tfc:cut_sandstone/yellow",
    # soil
    "dirt": "tfc:dirt/alfisol", "coarse_dirt": "tfc:coarse_dirt/alfisol", "rooted_dirt": "tfc:rooted_dirt/alfisol", "podzol": "tfc:dirt/alfisol",
    "grass_block": "tfc:grass/alfisol", "mycelium": "tfc:grass/alfisol", "crimson_nylium": "tfc:grass/alfisol", "warped_nylium": "tfc:grass/alfisol",
    "dirt_path": "tfc:grass_path/alfisol", "farmland": "tfc:farmland/alfisol", "clay": "tfc:clay/alfisol", "mud": "tfc:mud/alfisol",
    "packed_mud": "tfc:mud_bricks/alfisol", "mud_bricks": "tfc:mud_bricks/alfisol", "muddy_mangrove_roots": "tfc:muddy_roots/alfisol",
    "moss_block": "tfc:grass/alfisol", "mangrove_roots": AIR, "terracotta": "tfc:mud_bricks/alfisol", "hay_block": "tfc:thatch",
    "dried_kelp_block": "tfc:thatch", "nether_wart_block": "tfc:wattle/red", "warped_wart_block": "tfc:wattle/cyan",
    # metal and mineral blocks, ores
    "iron_block": "tfc:rock/smooth/granite", "raw_iron_block": "tfc:rock/raw/granite", "raw_gold_block": "tfc:rock/raw/granite",
    "raw_copper_block": "tfc:rock/raw/granite", "netherite_block": "tfc:alabaster/polished/black", "gold_block": "tfc:alabaster/polished/yellow",
    "emerald_block": "tfc:alabaster/polished/lime", "diamond_block": "tfc:alabaster/polished/light_blue", "lapis_block": "tfc:alabaster/polished/blue",
    "coal_block": "tfc:alabaster/polished/black", "redstone_block": "tfc:alabaster/polished/red", "copper_block": "tfc:alabaster/polished/orange",
    "quartz_block": "tfc:alabaster/polished/white", "quartz_pillar": "tfc:alabaster/polished/white", "chiseled_quartz_block": "tfc:alabaster/polished/white",
    "smooth_quartz": "tfc:alabaster/polished/white", "purpur_block": "tfc:alabaster/polished/purple", "purpur_pillar": "tfc:alabaster/polished/purple",
    "iron_bars": "tfc:wood/fence/oak", "iron_door": "tfc:wood/door/oak", "iron_trapdoor": "tfc:wood/trapdoor/oak",
    "anvil": "tfc:rock/anvil/granite", "chipped_anvil": "tfc:rock/anvil/granite", "damaged_anvil": "tfc:rock/anvil/granite",
    "cauldron": "tfc:wood/barrel/oak", "water_cauldron": "tfc:wood/barrel/oak", "lava_cauldron": "tfc:wood/barrel/oak",
    "powder_snow_cauldron": "tfc:wood/barrel/oak", "nether_brick_fence": "tfc:rock/bricks/granite_wall",
    # wood-ish furniture and workstations
    "chest": "tfc:wood/chest/oak", "trapped_chest": "tfc:wood/trapped_chest/oak", "barrel": "tfc:wood/barrel/oak",
    "bookshelf": "tfc:wood/bookshelf/oak", "chiseled_bookshelf": "tfc:wood/bookshelf/oak", "lectern": "tfc:wood/lectern/oak",
    "loom": "tfc:wood/loom/oak", "crafting_table": "tfc:wood/workbench/oak", "cartography_table": "tfc:wood/workbench/oak",
    "fletching_table": "tfc:wood/workbench/oak", "smithing_table": "tfc:wood/workbench/oak", "composter": "tfc:composter",
    "stonecutter": "tfc:rock/chiseled/granite", "grindstone": "tfc:rock/smooth/granite", "furnace": "tfc:rock/bricks/granite",
    "blast_furnace": "tfc:rock/bricks/granite", "smoker": "tfc:rock/bricks/granite", "brewing_stand": AIR, "bell": "tfc:bronze_bell",
    "crafter": "tfc:wood/workbench/oak", "enchanting_table": KEEP, "ender_chest": KEEP, "lodestone": "tfc:rock/smooth/granite",
    "scaffolding": KEEP, "ladder": KEEP, "campfire": KEEP, "soul_campfire": KEEP,
    # plants and crops
    "wheat": "tfc:crop/wheat", "carrots": "tfc:crop/carrot", "potatoes": "tfc:crop/potato", "beetroots": "tfc:crop/beet",
    "melon_stem": "tfc:crop/melon", "attached_melon_stem": AIR, "pumpkin_stem": "tfc:crop/pumpkin", "attached_pumpkin_stem": AIR,
    "melon": "tfc:melon", "pumpkin": "tfc:pumpkin", "carved_pumpkin": "tfc:jack_o_lantern", "jack_o_lantern": "tfc:jack_o_lantern",
    "sugar_cane": AIR, "cactus": AIR, "bamboo": AIR, "bamboo_sapling": AIR, "cocoa": AIR, "sweet_berry_bush": AIR, "nether_wart": AIR,
    "short_grass": AIR, "tall_grass": AIR, "fern": AIR, "large_fern": AIR, "dead_bush": AIR, "lilac": AIR, "rose_bush": AIR, "peony": AIR,
    "sunflower": AIR, "dandelion": AIR, "poppy": AIR, "blue_orchid": AIR, "allium": AIR, "azure_bluet": AIR, "red_tulip": AIR,
    "orange_tulip": AIR, "white_tulip": AIR, "pink_tulip": AIR, "oxeye_daisy": AIR, "cornflower": AIR, "lily_of_the_valley": AIR,
    "torchflower": AIR, "torchflower_crop": AIR, "pitcher_plant": AIR, "pitcher_crop": AIR, "wither_rose": AIR, "pink_petals": AIR,
    "azalea": AIR, "flowering_azalea": AIR, "moss_carpet": AIR, "lily_pad": AIR, "big_dripleaf": AIR, "big_dripleaf_stem": AIR,
    "small_dripleaf": AIR, "spore_blossom": AIR, "hanging_roots": AIR, "glow_lichen": KEEP, "seagrass": AIR, "tall_seagrass": AIR,
    "kelp": AIR, "kelp_plant": AIR, "sea_pickle": AIR, "crimson_fungus": AIR, "warped_fungus": AIR, "crimson_roots": AIR,
    "warped_roots": AIR, "nether_sprouts": AIR, "weeping_vines": AIR, "weeping_vines_plant": AIR, "twisting_vines": AIR,
    "twisting_vines_plant": AIR, "chorus_flower": AIR, "chorus_plant": AIR, "mangrove_propagule": AIR, "brown_mushroom": AIR,
    "red_mushroom": AIR, "brown_mushroom_block": "tfc:thatch", "red_mushroom_block": "tfc:thatch", "mushroom_stem": "tfc:thatch",
    "azalea_leaves": "tfc:wood/leaves/oak", "flowering_azalea_leaves": "tfc:wood/leaves/oak",
    # fluids
    "water": "tfc:fluid/river_water", "bubble_column": AIR, "lava": KEEP,
    # beds, banners, wool and the like (kept as decoration unless TFC has a counterpart)
    "air": KEEP, "cave_air": KEEP, "void_air": KEEP, "bedrock": KEEP, "barrier": KEEP, "light": KEEP, "structure_void": KEEP,
    "structure_block": KEEP, "jigsaw": KEEP, "command_block": AIR, "chain_command_block": AIR, "repeating_command_block": AIR,
    "end_portal": KEEP, "end_portal_frame": KEEP, "end_gateway": KEEP, "nether_portal": KEEP, "dragon_egg": KEEP, "beacon": KEEP,
    "conduit": KEEP, "respawn_anchor": KEEP, "fire": KEEP, "soul_fire": KEEP,
}

REGEX = []   # (compiled regex, function(match) -> target)


def rule(pattern):
    def deco(fn):
        REGEX.append((re.compile(pattern), fn))
        return fn
    return deco


def shaped(name):
    """('cobblestone_slab') -> ('cobblestone', '_slab'); names without a shape suffix keep ''."""
    for s in SHAPES:
        if name.endswith(s):
            return name[: -len(s)], s
    return name, ""


# --- wood families ---------------------------------------------------------------------------------------------------------
wood_names = "|".join(sorted(WOODS, key=len, reverse=True))


@rule(rf"^({wood_names})_(planks|stairs|slab|fence|fence_gate|door|trapdoor|pressure_plate|button|sign|wall_sign|hanging_sign|wall_hanging_sign|"
      rf"log|wood|leaves|sapling|stem|hyphae|block|mosaic|mosaic_slab|mosaic_stairs)$")
def wood(m):
    w, part = WOODS[m.group(1)], m.group(2)
    table = {"planks": f"tfc:wood/planks/{w}", "stairs": f"tfc:wood/planks/{w}_stairs", "slab": f"tfc:wood/planks/{w}_slab",
             "mosaic": f"tfc:wood/planks/{w}", "mosaic_slab": f"tfc:wood/planks/{w}_slab", "mosaic_stairs": f"tfc:wood/planks/{w}_stairs",
             "fence": f"tfc:wood/fence/{w}", "fence_gate": f"tfc:wood/fence_gate/{w}", "door": f"tfc:wood/door/{w}",
             "trapdoor": f"tfc:wood/trapdoor/{w}", "pressure_plate": f"tfc:wood/pressure_plate/{w}", "button": f"tfc:wood/button/{w}",
             "sign": f"tfc:wood/sign/{w}", "wall_sign": f"tfc:wood/wall_sign/{w}",
             "hanging_sign": f"tfc:wood/hanging_sign/copper/{w}", "wall_hanging_sign": f"tfc:wood/wall_hanging_sign/copper/{w}",
             "log": f"tfc:wood/log/{w}", "stem": f"tfc:wood/log/{w}", "wood": f"tfc:wood/wood/{w}", "hyphae": f"tfc:wood/wood/{w}",
             "leaves": f"tfc:wood/leaves/{w}", "sapling": f"tfc:wood/sapling/{w}", "block": f"tfc:wood/log/{w}"}
    return table[part]


@rule(rf"^stripped_({wood_names})_(log|wood|stem|hyphae|block)$")
def stripped(m):
    w, part = WOODS[m.group(1)], m.group(2)
    return f"tfc:wood/stripped_{'wood' if part in ('wood', 'hyphae') else 'log'}/{w}"


@rule(rf"^potted_({wood_names})_sapling$")
def potted_sapling(m):
    return f"tfc:wood/potted_sapling/{WOODS[m.group(1)]}"


# --- stone families ---------------------------------------------------------------------------------------------------------
STONE_BASE = {   # vanilla base name (without shape) -> TFC variant
    "cobblestone": "cobble", "cobbled_deepslate": "cobble", "mossy_cobblestone": "mossy_cobble",
    "stone_brick": "bricks", "brick": "bricks", "deepslate_brick": "bricks", "deepslate_tile": "bricks", "nether_brick": "bricks",
    "red_nether_brick": "bricks", "end_stone_brick": "bricks", "tuff_brick": "bricks", "polished_blackstone_brick": "bricks",
    "prismarine_brick": "bricks", "prismarine": "bricks", "dark_prismarine": "bricks", "mossy_stone_brick": "mossy_bricks",
    "andesite": "raw", "diorite": "raw", "granite": "raw", "blackstone": "raw", "tuff": "raw", "end_stone": "raw", "stone": "raw",
    "polished_andesite": "smooth", "polished_diorite": "smooth", "polished_granite": "smooth", "polished_deepslate": "smooth",
    "polished_blackstone": "smooth", "polished_tuff": "smooth", "smooth_stone": "smooth", "cobbled_deepslate_x": "cobble",
    "sandstone": None, "red_sandstone": None, "smooth_sandstone": None, "smooth_red_sandstone": None, "cut_sandstone": None,
    "cut_red_sandstone": None, "mud_brick": "mud", "quartz": "alabaster", "smooth_quartz": "alabaster", "purpur": "alabaster_purple",
    "cut_copper": "alabaster_orange", "exposed_cut_copper": "alabaster_orange", "weathered_cut_copper": "alabaster_cyan",
    "oxidized_cut_copper": "alabaster_cyan", "waxed_cut_copper": "alabaster_orange", "waxed_exposed_cut_copper": "alabaster_orange",
    "waxed_weathered_cut_copper": "alabaster_cyan", "waxed_oxidized_cut_copper": "alabaster_cyan",
}


@rule(r"^([a-z_]+?)(_slab|_stairs|_wall)$")
def stone_shape(m):
    base, shape = m.group(1), m.group(2)
    variant = STONE_BASE.get(base)
    if base in ("sandstone", "red_sandstone"):
        return f"tfc:raw_sandstone/yellow{shape}"
    if base in ("smooth_sandstone", "smooth_red_sandstone"):
        return f"tfc:smooth_sandstone/yellow{shape}"
    if base in ("cut_sandstone", "cut_red_sandstone"):
        return f"tfc:cut_sandstone/yellow{shape}"
    if variant == "mud":
        return f"tfc:mud_bricks/alfisol{shape}"
    if variant == "alabaster":
        return f"tfc:alabaster/polished/white{shape}"
    if variant and variant.startswith("alabaster_"):
        return f"tfc:alabaster/polished/{variant.split('_', 1)[1]}{shape}"
    if variant:
        return f"tfc:rock/{variant}/granite{shape}"
    return None


# --- ores and similar -------------------------------------------------------------------------------------------------------
@rule(r"^(deepslate_)?(coal|iron|copper|gold|lapis|redstone|emerald|diamond)_ore$|^nether_(gold|quartz)_ore$")
def ore(m):
    return "tfc:rock/raw/granite"


# --- copper family (all oxidation stages, waxed) ------------------------------------------------------------------------------
@rule(r"^(waxed_)?(exposed_|weathered_|oxidized_)?(copper|copper_block|copper_bulb|copper_grate|chiseled_copper)$")
def copper_blocks(m):
    return "tfc:alabaster/polished/" + ("cyan" if m.group(2) in ("weathered_", "oxidized_") else "orange")


@rule(r"^(waxed_)?(exposed_|weathered_|oxidized_)?(cut_copper)$")
def cut_copper_block(m):
    return "tfc:alabaster/polished/" + ("cyan" if m.group(2) in ("weathered_", "oxidized_") else "orange")


@rule(r"^(waxed_)?(exposed_|weathered_|oxidized_)?copper_door$")
def copper_door(m):
    return "tfc:wood/door/oak"


@rule(r"^(waxed_)?(exposed_|weathered_|oxidized_)?copper_trapdoor$")
def copper_trapdoor(m):
    return "tfc:wood/trapdoor/oak"


# --- colours ------------------------------------------------------------------------------------------------------------------
color_names = "|".join(sorted(COLORS, key=len, reverse=True))


@rule(rf"^({color_names})_bed$")
def bed(m):
    return "tfc:thatch_bed"


@rule(rf"^({color_names})_terracotta$|^({color_names})_glazed_terracotta$")
def terracotta(m):
    return f"tfc:wattle/{m.group(1) or m.group(2)}"


@rule(rf"^({color_names})_concrete$")
def concrete(m):
    return f"tfc:alabaster/polished/{m.group(1)}"


@rule(rf"^({color_names})_concrete_powder$")
def concrete_powder(m):
    return f"tfc:alabaster/raw/{m.group(1)}"


# decoration kept as it is: wool, carpets, banners, candles, glass, shulker boxes, corals, froglights ...
KEEP_RE = re.compile(
    rf"^({color_names})_(wool|carpet|banner|wall_banner|candle|candle_cake|stained_glass|stained_glass_pane|shulker_box)$|"
    r"^(candle|candle_cake|glass|glass_pane|tinted_glass|shulker_box|cake|torch|wall_torch|soul_torch|soul_wall_torch|redstone_torch|"
    r"redstone_wall_torch|lantern|soul_lantern|end_rod|glowstone|shroomlight|sea_lantern|redstone_lamp|ochre_froglight|verdant_froglight|"
    r"pearlescent_froglight|chain|rail|powered_rail|detector_rail|activator_rail|tnt|tripwire|tripwire_hook|lever|piston|sticky_piston|"
    r"piston_head|moving_piston|hopper|dropper|dispenser|observer|comparator|repeater|daylight_detector|redstone_wire|note_block|"
    r"jukebox|target|lightning_rod|spawner|trial_spawner|vault|heavy_core|decorated_pot|flower_pot|vine|cobweb|snow|snow_block|ice|packed_ice|"
    r"blue_ice|frosted_ice|powder_snow|slime_block|honey_block|honeycomb_block|bee_nest|beehive|sponge|wet_sponge|sculk|sculk_catalyst|"
    r"sculk_sensor|calibrated_sculk_sensor|sculk_shrieker|sculk_vein|amethyst_cluster|small_amethyst_bud|medium_amethyst_bud|"
    r"large_amethyst_bud|budding_amethyst|pointed_dripstone|cave_vines|cave_vines_plant|glow_lichen|sniffer_egg|turtle_egg|frogspawn|"
    r"light_weighted_pressure_plate|heavy_weighted_pressure_plate|creeper_head|creeper_wall_head|dragon_head|dragon_wall_head|piglin_head|"
    r"piglin_wall_head|player_head|player_wall_head|skeleton_skull|skeleton_wall_skull|wither_skeleton_skull|wither_skeleton_wall_skull|"
    r"zombie_head|zombie_wall_head)$|"
    r"^potted_|^(dead_)?(brain|bubble|fire|horn|tube)_coral(_block|_fan|_wall_fan)?$")


def target_for(name):
    if name in EXACT:
        return EXACT[name]
    for rx, fn in REGEX:
        m = rx.match(name)
        if m:
            t = fn(m)
            if t:
                return t
    if KEEP_RE.match(name):
        return KEEP
    return None


IRON_AGE_METALS = ("wrought_iron", "cast_iron", "steel", "black_steel", "blue_steel", "red_steel")
IRON_AGE_RE = re.compile(r"^tfc:metal/(?P<family>[a-z_]+)/(?P<metal>" + "|".join(IRON_AGE_METALS) + r")(?P<shape>_slab|_stairs)?$")


def iron_age_substitutes(ids):
    """TFC's own iron-age metal blocks that other mods' processors write (the compat turns chains, bars and anvils into wrought
    iron): free iron-age metal would skip the bloomery, so they become the copper block of the same family."""
    out = {}
    for i in sorted(ids):
        m = IRON_AGE_RE.match(i)
        if m:
            t = f"tfc:metal/{m.group('family')}/copper{m.group('shape') or ''}"
            if t in ids:
                out[i] = t
    return out


GEAR_SLOTS = {"helmet": "helmet", "chestplate": "chestplate", "leggings": "greaves", "boots": "boots"}
TOOLS_MAP = ["sword", "axe", "pickaxe", "shovel", "hoe"]
# vanilla metal tier -> the TFC metal that stands in (iron age and gold are not on offer: copper and bronze age only)
TIER_METAL = {"iron": "copper", "golden": "copper", "chainmail": "copper", "diamond": "bronze", "netherite": "bronze", "stone": None,
              "wooden": None, "leather": None}


def item_table(items):
    """Vanilla gear and TFC iron-age gear that structures put on entities -> copper/bronze gear. Written as `items` in items.json."""
    out = {}
    for tier, metal in TIER_METAL.items():
        if metal is None:
            continue
        for slot, tfc_slot in GEAR_SLOTS.items():
            src, dst = f"minecraft:{tier}_{slot}", f"tfc:metal/{tfc_slot}/{metal}"
            if src in items and dst in items:
                out[src] = dst
        for tool in TOOLS_MAP:
            src, dst = f"minecraft:{tier}_{tool}", f"tfc:metal/{tool}/{metal}"
            if src in items and dst in items:
                out[src] = dst
    for src, dst in {"minecraft:iron_ingot": "tfc:metal/ingot/copper", "minecraft:iron_nugget": "minecraft:flint", "minecraft:gold_ingot": "tfc:metal/ingot/copper",
                     "minecraft:gold_nugget": "minecraft:flint", "minecraft:diamond": "minecraft:flint", "minecraft:emerald": "minecraft:flint",
                     "minecraft:raw_iron": "tfc:ore/small_native_copper", "minecraft:iron_horse_armor": "tfc:metal/horse_armor/copper",
                     "minecraft:golden_horse_armor": "tfc:metal/horse_armor/copper", "minecraft:diamond_horse_armor": "tfc:metal/horse_armor/bronze",
                     "minecraft:shield": "tfc:metal/shield/copper", "minecraft:golden_apple": "tfc:food/red_apple",
                     "minecraft:enchanted_golden_apple": "tfc:food/red_apple", "minecraft:totem_of_undying": "minecraft:flint",
                     "minecraft:iron_ore": "tfc:ore/small_native_copper", "minecraft:deepslate_iron_ore": "tfc:ore/small_native_copper",
                     "minecraft:raw_iron_block": "tfc:ore/small_native_copper", "minecraft:iron_block": "tfc:metal/ingot/copper",
                     "minecraft:gold_ore": "tfc:ore/small_native_copper", "minecraft:deepslate_gold_ore": "tfc:ore/small_native_copper",
                     "minecraft:raw_gold": "tfc:ore/small_native_copper", "minecraft:gold_block": "tfc:metal/ingot/copper",
                     "minecraft:diamond_ore": "minecraft:flint", "minecraft:emerald_ore": "minecraft:flint",
                     "minecraft:diamond_block": "minecraft:flint", "minecraft:emerald_block": "minecraft:flint",
                     "minecraft:netherite_ingot": "tfc:metal/ingot/bronze", "minecraft:netherite_scrap": "minecraft:flint",
                     "minecraft:iron_horse_armor_x": "tfc:metal/horse_armor/copper"}.items():
        if src in items and dst in items:
            out[src] = dst
    # TFC's own iron-age gear (the compat dresses armor stands in wrought iron armor)
    for i in sorted(items):
        m = re.match(r"^tfc:metal/(?P<kind>[a-z_]+)/(?:wrought_iron|cast_iron|steel|black_steel|blue_steel|red_steel)$", i)
        if m:
            dst = f"tfc:metal/{m.group('kind')}/copper"
            if dst in items:
                out[i] = dst
    return out


# metals whose storage blocks structures must not hand out (gold and silver are late in this pack, brass opens airships): polished alabaster
PRECIOUS = {"gold": "yellow", "silver": "light_gray", "sterling_silver": "light_gray", "rose_gold": "pink", "brass": "yellow", "nickel": "gray"}
PRECIOUS_RE = re.compile(r"^tfc:metal/(?P<family>block|exposed_block|weathered_block|oxidized_block)/(?P<metal>" + "|".join(PRECIOUS) + r")(?P<shape>_slab|_stairs)?$")


def precious_substitutes(ids):
    out = {}
    for i in sorted(ids):
        m = PRECIOUS_RE.match(i)
        if m:
            t = f"tfc:alabaster/polished/{PRECIOUS[m.group('metal')]}{m.group('shape') or ''}"
            if t in ids:
                out[i] = t
    return out


def load_items(dump):
    return set(json.load(open(os.path.join(dump, "items.json")))["ids"])


def load_blocks(dump):
    return json.load(open(os.path.join(dump, "blocks.json")))["ids"]


def newest_dump():
    dumps = sorted(d for d in glob.glob(os.path.join(DUMPS, "*")) if os.path.exists(os.path.join(d, "blocks.json")))
    return dumps[-1]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dump")
    ap.add_argument("--check", action="store_true", help="report gaps and bad targets, write nothing")
    ap.add_argument("--census", help="census_templates.json from census.py, to weight the report")
    args = ap.parse_args()
    dump = args.dump or newest_dump()
    ids = set(load_blocks(dump))
    vanilla = sorted(i for i in ids if i.startswith("minecraft:"))
    table, gaps, bad = {}, [], []
    for full in vanilla:
        name = full[len("minecraft:"):]
        t = target_for(name)
        if t is None:
            gaps.append(full)
            continue
        if not t.startswith("@") and t not in ids:
            bad.append((full, t))
        table[full] = t
    weight = {}
    if args.census:
        for v in json.load(open(args.census)).values():
            for b, c in v["blocks"].items():
                weight[b] = weight.get(b, 0) + c
    print(f"{len(vanilla)} vanilla blocks in {os.path.basename(dump)}: {len(table)} with a rule, {len(gaps)} without")
    if bad:
        print("targets that don't exist:")
        for f, t in bad:
            print("  ", f, "->", t)
    if gaps:
        gaps.sort(key=lambda g: -weight.get(g, 0))
        print("no rule:", ", ".join(f"{g[10:]}({weight.get(g, 0)})" for g in gaps[:80]))
    if weight:
        left = {}
        for b, c in weight.items():
            if table.get(b) == KEEP and b not in ("minecraft:air", "minecraft:jigsaw", "minecraft:structure_void", "minecraft:cave_air"):
                left[b] = c
        total = sum(c for b, c in weight.items() if b.startswith("minecraft:") and b not in ("minecraft:air", "minecraft:jigsaw", "minecraft:structure_void"))
        kept = sum(left.values())
        print(f"template blocks (non-air vanilla): {total}; left vanilla by design: {kept} ({100 * kept / max(total, 1):.1f}%)")
        for b, c in sorted(left.items(), key=lambda kv: -kv[1])[:40]:
            print(f"   keep {b} {c}")
    if args.check:
        return 1 if (bad or gaps) else 0
    if bad:
        raise SystemExit("fix the bad targets first")
    for g in gaps:
        table[g] = KEEP
    table.update(iron_age_substitutes(ids))
    table.update(precious_substitutes(ids))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    out = {"_about": "Generated by tools/structure_mods/skin_table.py; edit the rules there, not this file.",
           "blocks": {k: table[k] for k in sorted(table)}}
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=1)
        f.write("\n")
    print("wrote", os.path.relpath(OUT, REPO))
    gear = item_table(load_items(dump))
    items_out = os.path.join(os.path.dirname(OUT), "items.json")
    with open(items_out, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"_about": "Generated by tools/structure_mods/skin_table.py.", "items": {k: gear[k] for k in sorted(gear)}}, f, indent=1)
        f.write("\n")
    print("wrote", os.path.relpath(items_out, REPO), f"({len(gear)} items)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
