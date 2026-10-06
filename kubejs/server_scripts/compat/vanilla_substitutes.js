// Recipes that ask for vanilla items TFC replaces with its own.
//
// - Crafting table: TFC players craft per-wood workbenches instead (tagged
//   c:player_workstations/crafting_tables). Create's mechanical crafter and blueprint, the
//   vanilla crafter and the smithing table asked for minecraft:crafting_table specifically.
// - Dried kelp: TFC worlds have no vanilla kelp, and TFC's own dried kelp comes from giant kelp,
//   a regional ocean plant. Create's belts, spout, funnels, tunnels and pulleys take any
//   pack:belting instead: leather or TFC burlap cloth (flat leather and canvas belts drove real
//   line shafts), or either kind of dried kelp.
// - Blast furnace: GregTech's electric blast furnace is built from TFC's blast furnace instead of
//   the vanilla one, which TFC worlds can only get from a GregTech assembler.
// - Coal: GregTech's coal recipes (the coke oven among them) take #c:gems/coal, which only held
//   vanilla coal. TFC's bituminous coal is the same thing; lignite stays out (a poor coking coal).

ServerEvents.tags('item', event => {
  event.add('pack:belting', ['minecraft:leather', 'tfc:burlap_cloth', 'minecraft:dried_kelp', 'tfc:food/dried_kelp'])
  event.add('c:gems/coal', 'tfc:ore/bituminous_coal')
})

ServerEvents.recipes(event => {
  event.replaceInput({}, 'minecraft:crafting_table', '#c:player_workstations/crafting_tables')

  ;['minecraft:dried_kelp', 'minecraft:dried_kelp_block'].forEach(kelp => {
    event.replaceInput({ not: { mod: 'minecraft' } }, kelp, '#pack:belting')
  })

  event.replaceInput({ mod: 'gtceu' }, 'minecraft:blast_furnace', 'tfc:blast_furnace')
})
