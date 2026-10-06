// Keep TFC's iron and steel milestones (docs/design.md: "Era order"): wrought iron comes from the
// bloomery and steel from pig iron, whichever mod's machines do the work.
//
// - Iron ores and iron dusts smelt into TFC cast iron, the way everything iron melts into cast
//   iron in TFC (wrought iron included). GregTech's furnace recipes turned crushed hematite,
//   magnetite, limonite and pyrite, their dusts, and iron dust (a byproduct of crushing magnetite)
//   straight into iron, which is wrought iron here. GregTech's steam furnace and Create's fan run
//   those recipes, so they would have skipped the bloomery.
// - Chainmail no longer smelts into iron nuggets. Create makes chains from zinc and GregTech makes
//   chainmail from chains, so vanilla's recycling recipe turned zinc into iron.
// - GregTech's primitive blast furnace refines TFC pig iron into steel (instead of iron, which is
//   wrought iron here), so it's a faster way to finish pig iron, not a way around TFC's blast
//   furnace. Its iron-block recipes are gone (TFC has no pig iron block), and so are its slower
//   duplicates that took plain iron, which became the same recipes.

const PBF = 'gtceu:primitive_blast_furnace'

ServerEvents.recipes(event => {
  // Unification may not have run yet, so match both the vanilla and the TFC iron ingot.
  var oreSmelting = { type: 'minecraft:smelting', id: /^gtceu:smelting\/smelt_/ }
  ;['minecraft:iron_ingot', 'tfc:metal/ingot/wrought_iron'].forEach(iron => {
    event.replaceOutput(oreSmelting, iron, 'tfc:metal/ingot/cast_iron')
  })

  var ironGear = ['pickaxe', 'shovel', 'axe', 'hoe', 'sword', 'helmet', 'chestplate', 'leggings', 'boots', 'horse_armor']
    .map(piece => `minecraft:iron_${piece}`)
  event.remove({ id: 'minecraft:iron_nugget_from_smelting' })
  event.remove({ id: 'minecraft:iron_nugget_from_blasting' })
  event.smelting('minecraft:iron_nugget', ironGear).xp(0.1).id('pack:iron_nugget_from_smelting')
  event.blasting('minecraft:iron_nugget', ironGear).xp(0.1).id('pack:iron_nugget_from_blasting')

  event.remove({ type: PBF, input: '#c:storage_blocks/wrought_iron' })
  event.remove({ type: PBF, not: { id: /_wrought$/ } })
  ;['#c:ingots/iron', '#c:ingots/wrought_iron'].forEach(iron => {
    event.replaceInput({ type: PBF }, iron, '#c:ingots/pig_iron')
  })
})
