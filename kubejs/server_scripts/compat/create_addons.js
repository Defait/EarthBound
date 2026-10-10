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
// - Design n Decor: dyeing an industrial cogwheel takes any from its tag, which lists only the dyed
//   ones; the plain cogwheel joins it so the first one can be dyed.
// - Power Loader: the chunk loaders' respawn anchor needs the Nether; a wrought iron block (andesite
//   loader) or a steel block (brass loader) stands in for it. An empty loader comes alive by capturing
//   a Ghast, also Nether-only, so creepers can be captured too.
// - Create Big Cannons: cannons are cast from any fluid in its molten-metal tags, so TFC's molten
//   cast iron, bronzes and steel pour straight into its moulds. Its heated mixing of iron and coal
//   into steel goes: with Woodencog's forge-heated basins it would skip TFC's pig iron route.
// - Create Propulsion: Simulated and Create Aeronautics: Gadgets & Gizmos (the createpropulsion and
//   createthrusters namespaces): thrust is a way to get airborne, so it unlocks with brass like every
//   propeller (docs/design.md, "Airships": the solid fuel and RCS thrusters get a brass casing, the others
//   had one or brass plates already). Their vanilla leftovers: the blast furnace of the burners is TFC's, the
//   oxidizer is made from saltpeter instead of nether wart, pine resin from the conifers TFC has, and G&G's
//   thruster takes Propulsion's liquid burner in place of the blaze burner (the Nether is closed). Platinum is
//   GregTech's (their recipes already name it). What needs a blaze burner, soul sand's nether kin or a
//   campfire (the thruster upgrade chain, the smoking upgrades) stays unreachable, like the blaze burner.
//   Propulsion's data also adds a 5% platinum nugget to Create's washing of crushed raw gold, which would
//   hand out GregTech's platinum (HV chemistry, step 61) at step 26; the recipe is put back as Create has it.
// - Create: Numismatics has no way to make a coin (the starter currency in config is zero), so a bank would
//   stay empty: coins are stamped in the mechanical press from one ingot of a metal the pack has, copper for
//   the spur, bronze for the bevel, brass for the sprocket. The cog, crown and sun are not minted: the bank
//   exchanges coins by value (deposit adds a coin's value in spurs to the account, a withdrawal takes any
//   coin out of it), so higher coins come from depositing lower ones. One copper ingot is one spur, the
//   way villagers and the Easy NPC traders already price in copper ingots. Delete the block marked "coin
//   mint" to take it out.
// - Create Aquatic Ambitions: its channeling recipes run on its mechanical conduit, which takes a vanilla
//   conduit (a heart of the sea: ocean treasure, which TFC worlds don't have), so they, the prismarine
//   alloy and the trident stay unreachable; the checker is told (progression.json, station).
// - Create: Enchantment Industry: vanilla enchanting is not a gate here (design.md, "Villagers"), so the
//   mod is left as it is: its grindstone, printer, experience fluid and bottles work; the blaze enchanter
//   and forger need a blaze burner and stay unreachable.

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

  // Create Propulsion and Gadgets & Gizmos
  event.replaceInput({ mod: 'createpropulsion' }, 'minecraft:blast_furnace', 'tfc:blast_furnace')
  event.replaceInput({ id: 'createpropulsion:mixing/oxidizer' }, 'minecraft:nether_wart', '#pack:oxidizer_salts')
  event.replaceInput({ id: 'createpropulsion:crushing/spruce_log' }, 'minecraft:spruce_log', '#pack:resin_logs')
  event.replaceInput({ id: 'createthrusters:thruster' }, 'create:empty_blaze_burner', 'createpropulsion:liquid_burner')
  event.replaceInput({ id: 'createthrusters:double_button' }, 'minecraft:oak_button', '#minecraft:wooden_buttons')
  event.replaceInput({ id: 'createpropulsion:crafting/solid_fuel_thruster' }, 'create:andesite_alloy', 'create:brass_casing')
  event.replaceInput({ id: 'createthrusters:rcs_thruster' }, 'create:shaft', 'create:brass_casing')

  event.remove({ id: 'create:splashing/crushed_raw_gold' })
  event.custom({
    type: 'create:splashing',
    ingredients: [{ item: 'create:crushed_raw_gold' }],
    results: [{ id: 'minecraft:gold_nugget', count: 9 }, { id: 'minecraft:quartz', chance: 0.5 }]
  }).id('create:splashing/crushed_raw_gold')

  // Bells & Whistles' metro window asks for the glass tag that is empty; the blocks tag is the one with glass
  event.remove({ id: 'bellsandwhistles:metro/metro_window' })
  event.shapeless('6x bellsandwhistles:metro_window', ['bellsandwhistles:metro_casing', '#c:glass_blocks']).id('pack:bellsandwhistles/metro_window')

  // coin mint: one ingot, one coin (spur, bevel, sprocket)
  var coins = { spur: 'copper', bevel: 'bronze', sprocket: 'brass' }
  Object.keys(coins).forEach(coin => {
    event.custom({ type: 'create:pressing', ingredients: [{ tag: `c:ingots/${coins[coin]}` }], results: [{ id: `numismatics:${coin}` }] })
      .id(`pack:numismatics/${coin}`)
  })

  event.replaceInput({ id: 'create_power_loader:empty_andesite_chunk_loader' }, 'minecraft:respawn_anchor', '#c:storage_blocks/wrought_iron')
  event.replaceInput({ id: 'create_power_loader:empty_brass_chunk_loader' }, 'minecraft:respawn_anchor', '#c:storage_blocks/steel')
})

ServerEvents.tags('item', event => {
  event.add('dndecor:industrial_cogwheels', 'dndecor:industrial_cogwheel')
  event.add('pack:oxidizer_salts', ['tfc:powder/saltpeter', '#c:dusts/saltpeter'])
  ;['pine', 'spruce', 'douglas_fir', 'sequoia', 'white_cedar'].forEach(wood => event.add('pack:resin_logs', `tfc:wood/log/${wood}`))
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
