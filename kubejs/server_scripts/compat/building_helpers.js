// Building helpers against the pack's design (docs/design.md: "Building helpers"): Construction Sticks and
// Measurements. Build Guide (client only) and Armor Poser have no recipes.
//
// - Construction Sticks: a stick is one ingot (or gem) and two sticks on the diagonal, and each tier places more blocks
//   and lasts longer. Its tiers are vanilla's (wood, copper, iron, diamond, netherite), so they follow the metal
//   ladder Sophisticated Storage and Roads and Roofs' mattocks use: wooden (any rod), copper (a copper ingot, as it
//   was), iron (a wrought iron ingot; vanilla iron is unreachable and Almost Unified would turn it into this anyway,
//   stated here so it does not depend on that), diamond (a steel ingot: a cut diamond from TFC's kimberlite is
//   reachable before wrought iron, which would put the stick above the iron one in the wrong order), netherite (a red
//   steel ingot: the Nether is closed, as for Sophisticated Storage's netherite tier). The items keep the mod's names.
//   Upgrades are smithing templates (angel: mid-air placing; battery: FE instead of durability; replacement, destruction
//   and unbreakable): angel and battery are built from what the pack has (the battery asks for a potato, which TFC
//   worlds lack, so it takes TFC's). The destruction template (diamond pickaxe, TNT: removes blocks without a tool, so it
//   would skip TFC's tool tiers), the replacement template (sculk) and the unbreakable one (nether star, crying
//   obsidian) cannot be made here: their ingredients are unreachable, which is checked by the progression checker, and
//   the destruction template is removed outright.
// - Measurements: one tape measure, made of wool and an iron ingot (a wrought iron ingot, via Almost Unified; stated).
// - Build Guide: a client-side overlay, no items.

ServerEvents.recipes(event => {
  // Construction Sticks: tiers on the metal ladder
  function stick(name, ingredient) {
    var id = `constructionstick:${name}_stick`
    event.remove({ id: id })
    event.shaped(id, ['  X', ' # ', '#  '], { '#': '#c:rods/wooden', X: ingredient }).id(id)
  }
  stick('iron', '#c:ingots/wrought_iron')
  stick('diamond', '#c:ingots/steel')
  stick('netherite', '#c:ingots/red_steel')

  // upgrade templates
  event.replaceInput({ id: 'constructionstick:template_battery' }, 'minecraft:potato', 'tfc:food/potato')
  event.remove({ id: 'constructionstick:template_destruction' })

  // Measurements: a wrought iron ingot
  event.replaceInput({ id: 'measurements:tape_measure' }, '#c:ingots/iron', '#c:ingots/wrought_iron')
})
