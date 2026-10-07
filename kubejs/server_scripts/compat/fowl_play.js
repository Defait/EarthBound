// Fowl Play's birds in TFC's world (docs/design.md: "Atmosphere").
//
// - Where: Fowl Play adds its birds to the biomes in its fowlplay:spawns_* tags, which name vanilla and
//   common biome tags; in TFC that put ducks and geese on every river, gulls on every shore and hawks on
//   ice sheets, and the tree birds nowhere. TFC's biomes are landforms, not climates, so the tags name
//   landforms only: tree and field birds anywhere on land, geese on fresh water and marshes, gulls on
//   shores. The climate (temperature, groundwater, forest) is the fauna rule of
//   startup_scripts/fowl_play.js. TFC biomes stay out of c:is_overworld: other mods' worldgen keys on it.
// - Duck and penguin get no biomes: TFC has its own, which are livestock and part of its food system.
// - Food: every Fowl Play bird drops only feathers, so none of them is a food source. Seed-eaters also
//   take TFC seeds (#c:seeds) for taming, breeding geese and feeding.
// - Predators: TFC's land predators and cats hunt the birds as they do TFC's own game birds, and the
//   birds avoid TFC's predators.
// Adapted from TerraFirmaGreg (LGPL-3.0, see licenses/TerraFirmaGreg-quests.txt).

// TFC's 125 biomes minus its oceans (c:is_ocean) and ice sheets (tfc:is_ice_sheet). TFC's biome list is
// frozen with the overworld (docs/design.md: "Overworld").
const FOWL_PLAY_LAND = ['active_shield_volcano', 'ancient_shield_volcano', 'badlands', 'burren_badlands',
  'burren_badlands_tall', 'burren_plains', 'burren_plateau', 'burren_roche_moutonee', 'buttes', 'canyons',
  'cenote_canyons', 'cenote_highlands', 'cenote_hills', 'cenote_plains', 'cenote_plateau', 'cenote_rolling_hills',
  'coastal_dunes', 'collisional_mountains', 'doline_canyons', 'doline_highlands', 'doline_hills', 'doline_plains',
  'doline_plateau', 'doline_rolling_hills', 'dormant_shield_volcano', 'drumlins', 'dune_sea', 'embayments',
  'extinct_shield_volcano', 'extreme_doline_mountains', 'extreme_doline_plateau', 'glacially_carved_mountains',
  'glacially_carved_oceanic_mountains', 'glacially_carved_volcanic_mountains',
  'glacially_carved_volcanic_oceanic_mountains', 'glaciated_mountains', 'glaciated_oceanic_mountains',
  'glaciated_shield_volcano', 'glaciated_volcanic_mountains', 'glaciated_volcanic_oceanic_mountains', 'grassy_dunes',
  'guano_island', 'highlands', 'hills', 'hoodoos', 'inverted_patterned_ground', 'knob_and_kettle', 'lake', 'low_canyons',
  'lowlands', 'meltwater_lake', 'mesas', 'mountain_lake', 'mountains', 'mud_flats', 'oceanic_mountain_lake',
  'oceanic_mountains', 'oceanic_volcanic_arc', 'old_mountain_lake', 'old_mountains', 'old_shield_volcano_shore',
  'patterned_ground', 'plains', 'plateau', 'plateau_lake', 'plateau_wide', 'rift_lake', 'rift_valley', 'river',
  'river_valley', 'rocky_plateau', 'rocky_shores', 'rolling_hills', 'salt_flats', 'salt_marsh', 'sea_stacks',
  'setback_cliffs', 'shield_volcano_shore', 'shilin_canyons', 'shilin_highlands', 'shilin_hills', 'shilin_plains',
  'shilin_plateau', 'shore', 'stair_step_canyons', 'stone_circles', 'sunken_shield_volcano', 'terrace_lower',
  'terrace_upper', 'tidal_flats', 'tower_karst_bay', 'tower_karst_canyons', 'tower_karst_highlands',
  'tower_karst_hills', 'tower_karst_lake', 'tower_karst_plains', 'tuyas', 'volcanic_island',
  'volcanic_mountain_islands', 'volcanic_mountain_lake', 'volcanic_mountains', 'volcanic_oceanic_mountain_lake',
  'volcanic_oceanic_mountains', 'whorled_canyons']
// Shores and coasts (c:is_beach, tfc:is_coastal_cliffs) plus salt marsh, mud flats and karst bays.
const FOWL_PLAY_SHORE = ['coastal_dunes', 'embayments', 'guano_island', 'mud_flats', 'old_shield_volcano_shore',
  'rocky_shores', 'salt_marsh', 'sea_stacks', 'setback_cliffs', 'shield_volcano_shore', 'shore', 'terrace_lower',
  'terrace_upper', 'tidal_flats', 'tower_karst_bay']
// Rivers, lakes and marshes (c:is_river, c:is_lake, c:is_swamp, mud flats), without subglacial lakes.
const FOWL_PLAY_FRESH_WATER = ['inverted_patterned_ground', 'lake', 'lowlands', 'meltwater_lake', 'mountain_lake',
  'mud_flats', 'oceanic_mountain_lake', 'old_mountain_lake', 'patterned_ground', 'plateau_lake', 'rift_lake', 'river',
  'river_valley', 'salt_marsh', 'tidal_flats', 'tower_karst_lake', 'volcanic_mountain_lake',
  'volcanic_oceanic_mountain_lake']

const FOWL_PLAY_HABITATS = {
  blue_jays: FOWL_PLAY_LAND, cardinals: FOWL_PLAY_LAND, chickadees: FOWL_PLAY_LAND, crows: FOWL_PLAY_LAND,
  hawks: FOWL_PLAY_LAND, pigeons: FOWL_PLAY_LAND, ravens: FOWL_PLAY_LAND, robins: FOWL_PLAY_LAND,
  sparrows: FOWL_PLAY_LAND, geese: FOWL_PLAY_FRESH_WATER, gulls: FOWL_PLAY_SHORE, ducks: [], penguins: [],
}
const FOWL_PLAY_SEED_EATERS = ['blue_jay', 'cardinal', 'chickadee', 'crow', 'goose', 'pigeon', 'raven', 'robin', 'sparrow']
const FOWL_PLAY_WILD = ['blue_jay', 'cardinal', 'chickadee', 'crow', 'goose', 'gull', 'hawk', 'pigeon', 'raven', 'robin',
  'sparrow']

ServerEvents.tags('worldgen/biome', event => {
  Object.keys(FOWL_PLAY_HABITATS).forEach(name => {
    let tag = `fowlplay:spawns_${name}`
    event.removeAll(tag)
    FOWL_PLAY_HABITATS[name].forEach(biome => event.add(tag, `tfc:${biome}`))
  })
})

ServerEvents.tags('item', event => {
  FOWL_PLAY_SEED_EATERS.forEach(bird => event.add(`fowlplay:${bird}_food`, '#c:seeds'))
})

ServerEvents.tags('entity_type', event => {
  FOWL_PLAY_WILD.forEach(bird => {
    event.add('tfc:hunted_by_land_predators', `fowlplay:${bird}`)
    event.add(`fowlplay:${bird}_avoids`, '#tfc:land_predators')
  })
  event.add('tfc:hunted_by_cats', '#fowlplay:passerines')
})
