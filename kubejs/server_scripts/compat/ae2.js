// Applied Energistics 2 against the pack's design (docs/design.md: "AE2").
//
// - Power: AE2 is an FE consumer and takes GregTech's electricity, nothing else. GregTech cables hand
//   EU to FE blocks natively (config/gtceu.yaml, nativeEUToFE; its converters stay off), so an energy
//   acceptor next to a cable is the whole bridge, bound by the cable's voltage like any machine. AE2's own
//   generators would skip that: the vibration chamber burns coal or charcoal for AE, the crystal
//   resonance generator makes it from nothing, and an annihilation plane at world height passively
//   makes sky dust (switched off in config/ae2-common.toml). All three are gone.
// - Certus quartz and silicon are GregTech's: gtceu:certus_quartz_gem and dust win (TFC has no certus, and
//   Almost Unified doesn't merge AE2's, whose recipes mix gems with charged crystals), and the printed
//   silicon takes GregTech's silicon ingot (c:silicon), so processors sit behind the electric blast
//   furnace. AE2's own crystals (growth clusters) still work as inputs and convert 1:1 to GregTech's.
//   Charged certus, fluix, quartz glass and the rest are AE2's own and are left as they are.
// - Meteorites: AE2 gets its sky stone and its presses from them, but they place only in
//   #minecraft:is_overworld, which holds no TFC biome, so TFC worlds have none (tools/worldgen_check.py
//   would say if that changed). Without them: the four presses are crafted from TFC steel plates around
//   their print material (and copy each other in the inscriber as AE2 does, from a TFC wrought iron
//   block in place of the iron one), and sky dust comes from GregTech's mixer (obsidian, ender pearl and
//   certus dust), which puts the controller and the other sky stone parts at the ender pearl chemistry.
//   The meteorite compass, which finds only meteorites, goes. The name press is crafted the same way (around
//   paper). The quantum bridge's singularity and the matter balls, which AE2 also gives only as meteorite
//   loot, are made in GregTech's assembler: matter balls (and so paint balls) in an HV assembler from sky
//   dust, and the singularity, after the controller (63), in an EV assembler from a controller, titanium
//   plates and an EV emitter (step 71); the entangled pair comes from it with AE2's own explosion.

ServerEvents.tags('item', event => {
  event.add('pack:certus_crystals', ['gtceu:certus_quartz_gem', 'ae2:certus_quartz_crystal'])
  event.add('pack:certus_dusts', ['gtceu:certus_quartz_dust', 'ae2:certus_quartz_dust'])
  event.add('c:silicon', '#c:ingots/silicon')
  event.remove('c:silicon', 'ae2:silicon')
})

ServerEvents.recipes(event => {
  // --- power: GregTech only
  ;[
    'ae2:network/blocks/energy_vibration_chamber',
    'ae2:network/crystal_resonance_generator',
    // AE2's own silicon from certus dust in a furnace
    'ae2:smelting/silicon_from_certus_quartz_dust',
    'ae2:blasting/silicon_from_certus_quartz_dust',
    // finds meteorites, which TFC worlds don't have
    'ae2:charger/meteorite_compass'
  ].forEach(id => event.remove({ id: id }))

  // --- certus quartz is GregTech's
  event.replaceInput({ mod: 'ae2' }, 'ae2:certus_quartz_crystal', '#pack:certus_crystals')
  event.replaceInput({ mod: 'ae2' }, 'ae2:certus_quartz_dust', '#pack:certus_dusts')
  event.replaceOutput({ mod: 'ae2' }, 'ae2:certus_quartz_crystal', 'gtceu:certus_quartz_gem')
  event.replaceOutput({ mod: 'ae2' }, 'ae2:certus_quartz_dust', 'gtceu:certus_quartz_dust')
  event.replaceOutput({ id: /^create:.*\/compat\/ae2\// }, 'ae2:certus_quartz_dust', 'gtceu:certus_quartz_dust')
  event.shapeless('gtceu:certus_quartz_gem', ['ae2:certus_quartz_crystal']).id('pack:ae2/certus_crystal_unified')
  event.shapeless('gtceu:certus_quartz_dust', ['ae2:certus_quartz_dust']).id('pack:ae2/certus_dust_unified')

  // AE2's custom recipe types: KubeJS can't rewrite their inputs, so they're restated
  function restate(id, json) {
    event.remove({ id: id })
    event.custom(json).id(id)
  }
  restate('ae2:charger/charged_certus_quartz_crystal', {
    type: 'ae2:charger',
    ingredient: { tag: 'pack:certus_crystals' },
    result: { id: 'ae2:charged_certus_quartz_crystal', count: 1 }
  })
  restate('ae2:transform/certus_quartz_crystals', {
    type: 'ae2:transform',
    ingredients: [{ item: 'ae2:charged_certus_quartz_crystal' }, { tag: 'pack:certus_dusts' }],
    result: { id: 'gtceu:certus_quartz_gem', count: 2 }
  })
  restate('ae2:inscriber/certus_quartz_dust', {
    type: 'ae2:inscriber', mode: 'inscribe',
    ingredients: { middle: { tag: 'pack:certus_crystals' } },
    result: { id: 'gtceu:certus_quartz_dust', count: 1 }
  })
  restate('ae2:inscriber/calculation_processor_print', {
    type: 'ae2:inscriber', mode: 'inscribe',
    ingredients: { top: { item: 'ae2:calculation_processor_press' }, middle: { tag: 'pack:certus_crystals' } },
    result: { id: 'ae2:printed_calculation_processor', count: 1 }
  })

  // --- presses: copied from a TFC wrought iron block in place of the iron block, crafted from steel plates
  ;['silicon', 'logic_processor', 'engineering_processor', 'calculation_processor'].forEach(name => {
    var press = `ae2:${name}_press`
    restate(`ae2:inscriber/${name}_press`, {
      type: 'ae2:inscriber', mode: 'inscribe',
      ingredients: { top: { item: press }, middle: { tag: 'c:storage_blocks/wrought_iron' } },
      result: { id: press, count: 1 }
    })
  })
  var centre = {
    'ae2:silicon_press': '#c:ingots/silicon',
    'ae2:logic_processor_press': '#c:ingots/gold',
    'ae2:engineering_processor_press': '#c:gems/diamond',
    'ae2:calculation_processor_press': '#pack:certus_crystals',
    'ae2:name_press': 'minecraft:paper'
  }
  Object.keys(centre).forEach(press => {
    event.shaped(press, [' P ', 'PMP', ' P '], { P: '#c:plates/steel', M: centre[press] })
      .id(`pack:ae2/${press.split(':')[1]}`)
  })

  // --- sky stone: sky dust, then AE2's own smelting of it into sky stone
  event.recipes.gtceu.mixer('pack:ae2_sky_dust')
    .itemInputs('2x #c:dusts/obsidian', '#c:dusts/ender_pearl', '#c:dusts/certus_quartz')
    .itemOutputs('2x ae2:sky_dust')
    .duration(200)
    .EUt(30, 1)

  event.recipes.gtceu.assembler('pack:ae2_matter_balls')
    .itemInputs('ae2:sky_dust', '#c:dusts/certus_quartz', '#c:plates/steel')
    .itemOutputs('8x ae2:matter_ball')
    .duration(100)
    .EUt(120, 1)
  event.recipes.gtceu.assembler('pack:ae2_singularity')
    .itemInputs('ae2:controller', '4x #c:plates/titanium', 'gtceu:ev_emitter')
    .itemOutputs('ae2:singularity')
    .duration(600)
    .EUt(1920, 1)
})
