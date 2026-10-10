// Complicated Bees against the pack's design (docs/design.md: "Complicated Bees").
//
// The owner's idea is GregTech: New Horizons' bees: Forestry-style genetics (princess, drone, queen, mutation
// recipes, frames, an analyzer) feeding a chain of combs into resources. This is the conservative minimum that
// keeps that and cannot break the TFC and GregTech progression; the choices that are left open are in design.md.
//
// - Starting bees: wild bee nests are the only source of a first princess and drones, and the mod places them
//   by biome modifier into vanilla and a few other mods' biomes by id (forest, plains, jungle, desert, lush
//   caves, crimson, warped, the end highlands, Biomes O' Plenty, Terralith and so on). TFC's biomes are
//   none of those, so no nest generates in a TFC world (tools/worldgen_check.py agrees: nothing to accept), and
//   the pack's worldgen stays as it is. The nests are crafted instead: four straw, hide glue (an iron-age
//   good here, ArborFirmaCraft's tree tap) and one marker for the species (log, flower, sand, leaves), shapeless,
//   for the four overworld species that start Forestry-style lines, forest, plains, desert and jungle. Break
//   the nest without silk touch for a princess, drones and combs (nest 14, first princess and comb 15, glue 13).
//   The Nether and End nests (crimson, warped, ender) and the lush cave one (rocky) have no recipe. An apiary
//   asks for a comb and an iron ingot (20), so keeping bees starts in the iron age.
// - Combs, comb by comb: the mod's own centrifuge (block, 38) turns a comb into beeswax and honey droplets and
//   nothing else. The resource a comb stands for (it was a vanilla item, among them diamonds, netherite scrap, raw
//   iron and ender pearl shards) comes from a GregTech macerator recipe that takes the comb, and the machine's
//   voltage tier is the gate: GregTech recipes need a machine of the tier their EUt asks for. LV (a steam or
//   electric macerator; the recipes come within reach at step 18): coal, copper, iron and gold combs and
//   redstone; MV (44): lapis, quartz, amethyst and glowstone; HV (58): diamond and emerald. The input is the comb
//   of that type (a component-matching ingredient), so a comb gives only its own resource. Each gives a 25% chance of one TFC or GregTech item of a material the
//   pack has before that tier anyway (small TFC copper, hematite and gold ores, TFC coal, GregTech gem dusts,
//   redstone and glowstone dust), so nothing enters earlier than its own step and nothing new (no netherite, no
//   titanium, no ender pearl) enters. The netherite comb gives wax and honey only, the mysterious comb no pearl
//   shard, and the recipe that turned a shard into an ender pearl is removed.
// - Power: the furnace generator and the honey generator make FE from fuel and honey, which the pack does not
//   allow outside GregTech (ae2.js: AE2's own generators went for the same reason). Both recipes are removed;
//   the multiblocks (gyrofuge, mellarium) take their FE from GregTech cables like AE2 does.
// - Climate: Complicated Bees reads vanilla biome temperature and humidity, and TFC biomes keep vanilla's
//   defaults, so every TFC biome is "normal" to a bee; the mod's own temperature units and hydroregulators
//   (frames and blocks) still work. TFC's climate does not reach bees.
// - Left as they are, unreachable on purpose: the hot frame (magma block, nether bricks), the deadly frame
//   (crying obsidian, skull), the twisted and withered upgrades (soul fire, nether star), the endenic upgrade
//   (chorus, dragon's breath), the rain shield (heart of the sea), the bee staff (blaze rod) and the
//   gyrofuge's advanced units (nether stars, netherite). Honey bottles have no source here (they were never
//   needed): droplets still make honey bread and honey porkchops.

var BEE_NESTS = {
  forest: '#minecraft:logs',
  plains: '#minecraft:small_flowers',
  desert: '#c:sands',
  jungle: '#minecraft:leaves'
}

// resource per comb and the EUt of the GregTech recipe that gives it (30 is LV, 120 MV, 480 HV); null leaves wax and honey only
var COMB_RESOURCE = {
  coal: ['tfc:ore/bituminous_coal', 30],
  copper: ['tfc:ore/small_native_copper', 30],
  iron: ['tfc:ore/small_hematite', 30],
  gold: ['tfc:ore/small_native_gold', 30],
  redstone: ['minecraft:redstone', 30],
  lapis: ['gtceu:lapis_dust', 120],
  quartz: ['gtceu:nether_quartz_dust', 120],
  amethyst: ['gtceu:amethyst_dust', 120],
  glowstone: ['minecraft:glowstone_dust', 120],
  diamond: ['gtceu:diamond_dust', 480],
  emerald: ['gtceu:emerald_dust', 480],
  netherite: null
}

var $SizedIngredient = Java.loadClass('net.neoforged.neoforge.common.crafting.SizedIngredient')
var $DataComponentIngredient = Java.loadClass('net.neoforged.neoforge.common.crafting.DataComponentIngredient')

ServerEvents.recipes(event => {
  // --- starting bees: a nest per species
  Object.keys(BEE_NESTS).forEach(species => {
    var nest = Item.of(`complicated_bees:bee_nest[minecraft:block_entity_data={id:"complicated_bees:bee_nest",species:"complicated_bees:${species}"}]`)
    event.shapeless(nest, ['4x tfc:straw', 'tfc:glue', BEE_NESTS[species]]).id(`pack:complicated_bees/${species}_nest`)
  })

  // --- combs: wax and honey from the mod's centrifuge, the resource from a GregTech macerator of the tier
  Object.keys(COMB_RESOURCE).forEach(type => {
    var id = `complicated_bees:centrifuge/${type}_comb`
    event.remove({ id: id })
    event.custom({
      type: 'complicated_bees:centrifuge',
      input: { type: 'neoforge:components', components: { 'complicated_bees:comb_type': `complicated_bees:${type}` }, items: 'complicated_bees:comb' },
      outputs: [
        { item: 'complicated_bees:beeswax', count: 1, chance: 0.5 },
        { item: 'complicated_bees:honey_droplet', count: 1, chance: 0.3 }
      ]
    }).id(id)
    if (COMB_RESOURCE[type]) {
      // a plain item input would take any comb for every resource: the input is a component-matching ingredient (the
      // comb type), as the mod's own centrifuge recipes use
      var comb = Item.of(`complicated_bees:comb[complicated_bees:comb_type="complicated_bees:${type}"]`)
      var input = new $SizedIngredient($DataComponentIngredient.of(false, comb), 1)
      event.recipes.gtceu.macerator(`pack:complicated_bees/${type}_comb`)
        .itemInputs(input)
        .chancedOutput(COMB_RESOURCE[type][0], 2500)
        .duration(100)
        .EUt(COMB_RESOURCE[type][1], 1)
    }
  })
  var mysterious = 'complicated_bees:centrifuge/mysterious_comb'
  event.remove({ id: mysterious })
  event.custom({
    type: 'complicated_bees:centrifuge',
    input: { type: 'neoforge:components', components: { 'complicated_bees:comb_type': 'complicated_bees:mysterious' }, items: 'complicated_bees:comb' },
    outputs: [
      { item: 'complicated_bees:beeswax', count: 1, chance: 0.5 },
      { item: 'complicated_bees:honey_droplet', count: 1, chance: 0.5 }
    ]
  }).id(mysterious)
  event.remove({ id: 'complicated_bees:shard_to_pearl' })

  // --- power: GregTech only
  event.remove({ id: 'complicated_bees:furnace_generator' })
  event.remove({ id: 'complicated_bees:honey_generator' })
})
