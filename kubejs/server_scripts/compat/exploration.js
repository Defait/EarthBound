// Rewards for exploring: Comforts, Paragliders, Little Joys and Artifacts against the pack's design
// (docs/design.md: "Exploration rewards"). Their loot is the loot lane's (tools/loot/loot.json); what is here are
// the recipes, and the notes on what each mod does in a TFC world.
//
// - Comforts: sleeping bags (three wool in a column) and hammocks (wool, string, sticks) need nothing TFC lacks:
//   vanilla wool is made from string and dyed in the barrel, string and sticks are TFC's. The rope and nail that
//   hangs a hammock asked for an iron ingot (or a rope tag nothing fills); TFC Huts ships TFC versions, which now
//   have their mod: comforts:rope_and_nail_shapeless_tfc (a TFC rope and a wrought iron ingot make two) loads, and its
//   shaped twin (comforts:rope_and_nail_tfc) is not among the loaded recipes (its pattern has rows of unequal width).
//   Comforts' own two are removed, so a nail is an iron-age good (checker step 20) and a sleeping bag or hammock
//   is a wool one (11 to 14).
// - Paragliders: the glider is sticks and leather (a wooden-rod and leather recipe, copper age) and slows a fall or
//   glides on stamina, so it opens no gate (flight proper is Create Aeronautics' and needs brass). Its energizing
//   mixture asks for a vanilla carrot, which TFC worlds lack, so it takes TFC's carrot; the enduring mixture needs a
//   golden carrot and stays out of reach. Hearts and stamina: a goddess statue turns 4 spirit orbs into a heart
//   container or a stamina vessel (the mod's own bargains, kept; config/paraglider-server.toml caps them at 10
//   hearts and 10 vessels, so 80 orbs for everything). Orbs are exploration loot placed by tools/loot/loot.json
//   (the mod's loot modifiers are switched off). The statue is not generated (the mod's structures name vanilla
//   biomes and are stripped in kubejs/data/paraglider/tags/worldgen/biome/has_structure/); it is crafted: a gold
//   ingot and six cobbles, so the orbs are the gate. The horned statue (trades hearts for emeralds) and the
//   Nether statue are not available.
// - Little Joys: dig spots and fishing spots appear near the player on matching ground and give a loot table; the
//   dig spot recipes (kubejs/data/littlejoys/recipe/dig_spot/tfc_*.json) name TFC's grass, dirt, clay, mud, sand
//   and gravel, and every table is the loot lane's (era capped, TFC goods). Its gold rush (mining a vanilla ore
//   with a pickaxe sets off a shower of that ore's drops) and drop rush (harvesting a vanilla crop does) key on
//   vanilla blocks TFC worlds lack; they are left that way on purpose: a TFC ore or crop that multiplied its yield
//   would be a shortcut. The mod has no fallen stars.
// - Artifacts: treasure items. Their loot modifiers into vanilla tables are off (the global list is replaced) and
//   its chests and barrels are the loot lane's. The only way to one is a campsite chest or a mimic's drop; the
//   campsite is its single-chest form (kubejs/data/artifacts/worldgen/placed_feature/), added to TFC's biomes by
//   kubejs/data/pack/neoforge/biome_modifier/artifacts_campsite.json, with TFC chests
//   (kubejs/data/artifacts/tags/block/campsite_chests.json). The full campsite is not used: its barrel, furnaces,
//   anvil, brewing stand and beds are vanilla blocks hard-coded in the mod, and a broken vanilla barrel or furnace
//   is an item the pack gates (GregTech assembles them). Which artifacts: see "Artifacts" in docs/design.md; six
//   are left out (digging claws mine without a tool tier, the pickaxe heater smelts ore as it is mined, rooted
//   boots and the everlasting beef feed past TFC's food rules, the helium flamingo flies, the universal attractor is
//   a magnet). Skeletons, zombies and piglins carry none (their equipment tables are emptied in tools/loot/loot.json).

ServerEvents.recipes(event => {
  // Comforts: TFC Huts' rope and nail recipe (wrought iron) stands in for the mod's own
  event.remove({ id: 'comforts:rope_and_nail' })
  event.remove({ id: 'comforts:shapeless_rope_and_nail' })

  // Paragliders: TFC's carrot in the energizing mixture
  event.remove({ id: 'paraglider:energizing_mixture' })
  event.custom({
    type: 'minecraft:crafting_shapeless',
    category: 'misc',
    ingredients: [{ type: 'paraglider:water_bottle' }, { item: 'tfc:food/carrot' }],
    result: { id: 'paraglider:energizing_mixture', count: 1 }
  }).id('paraglider:energizing_mixture')

  // Paragliders: the goddess statue (bargains of the mod: 4 orbs for a heart container or a stamina vessel)
  event.shaped('paraglider:goddess_statue', [' G ', 'CCC', 'CCC'], { G: '#c:ingots/gold', C: '#c:cobblestones' }).id('pack:paraglider/goddess_statue')

  // Artifacts: the eternal steak is cooked from the everlasting beef, which is not in the loot
  event.remove({ id: /^artifacts:eternal_steak/ })
})
