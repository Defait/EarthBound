// Create addons against the pack's design (docs/design.md: "Create addons").
//
// - Woodencog: andesite alloy knapped or chiseled straight from rock would skip the bronze-age gate
//   (andesite alloy needs zinc or bronze nuggets). Its crushing of TFC ores into TFC powder clashes
//   with the pack's crushing of the same ores into GregTech crushed ore (gregtech/ore_processing.js);
//   with two crushing recipes for one input the wheel's output would be arbitrary. Its heated basin
//   recipes (alloying, melting ore) stay: a basin on a charcoal forge is the heat source. Its saw
//   recipes for mud bricks use TFC 1.20's soil names (kubejs/data overrides switch them off); they're
//   redone here for TFC 4's soils.
// - Steam 'n' Rails: locometal boilers are fired with GregTech coke instead of blaze rods.
// - Power Loader: the chunk loaders' respawn anchor needs the Nether; a wrought iron block (andesite
//   loader) or a steel block (brass loader) stands in for it. An empty loader comes alive by capturing
//   a Ghast, also Nether-only, so creepers can be captured too.
// - Create Big Cannons: cannons are cast from any fluid in its molten-metal tags, so TFC's molten
//   cast iron, bronzes and steel pour straight into its moulds. Its heated mixing of iron and coal
//   into steel goes: with Woodencog's forge-heated basins it would skip TFC's pig iron route.

ServerEvents.recipes(event => {
  event.remove({ mod: 'woodencog', output: 'create:andesite_alloy' })
  event.remove({ id: /^woodencog:crushing\/ore\// })
  ;['alfisol', 'andisol', 'aridisol', 'entisol', 'fluvisol', 'mollisol', 'oxisol', 'podzol'].forEach(soil => {
    var bricks = `tfc:mud_bricks/${soil}`
    event.custom({ type: 'create:cutting', ingredients: [{ item: bricks }], results: [{ id: `${bricks}_stairs` }] })
      .id(`pack:cutting/mud_bricks/${soil}_stairs`)
    event.custom({ type: 'create:cutting', ingredients: [{ item: bricks }], results: [{ id: `${bricks}_slab`, count: 2 }] })
      .id(`pack:cutting/mud_bricks/${soil}_slab`)
  })

  event.replaceInput({ mod: 'railways' }, 'minecraft:blaze_rod', '#c:gems/coke')

  event.remove({ id: 'createbigcannons:mixing/alloy_steel' })

  event.replaceInput({ id: 'create_power_loader:empty_andesite_chunk_loader' }, 'minecraft:respawn_anchor', '#c:storage_blocks/wrought_iron')
  event.replaceInput({ id: 'create_power_loader:empty_brass_chunk_loader' }, 'minecraft:respawn_anchor', '#c:storage_blocks/steel')
})

ServerEvents.tags('entity_type', event => {
  event.add('create_power_loader:chunk_loader_capturable', 'minecraft:creeper')
})

ServerEvents.tags('fluid', event => {
  var molten = {
    'c:molten_cast_iron': ['cast_iron'],
    'c:molten_bronze': ['bronze', 'bismuth_bronze', 'black_bronze'],
    'c:molten_steel': ['steel']
  }
  Object.keys(molten).forEach(tag => {
    molten[tag].forEach(metal => {
      event.add(tag, [`tfc:metal/${metal}`, `tfc:metal/flowing_${metal}`])
    })
  })
})
