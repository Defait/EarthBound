// Sophisticated Storage against the pack's design (docs/design.md: "Sophisticated Storage").
//
// - Woods: its chests, barrels, limited barrels and storage connectors have one recipe per vanilla wood
//   (the wood is the style of the block, there are no TFC woods in its registry), all asking for vanilla
//   planks and slabs, which TFC worlds don't have. They take any planks or wooden slab instead, TFC's and
//   ArborFirmaCraft's (the mod's own generic recipes already did), so the style is chosen at the bench.
// - Tiers: copper, iron, gold and diamond were already tags (iron is TFC wrought iron through Almost
//   Unified, diamond the gem TFC's kimberlite gives). Netherite has no source here (the Nether is closed),
//   so the top tier takes red steel, as the red steel diving gear does in compat/create_addons.js
//   (copper, wrought iron, gold, diamond, red steel chests: steps 12, 20, 21, 22, 38; every upgrade needs
//   the one before it).
// - Stack upgrades multiply a slot's stack limit, which would let TFC's item size and weight limits be
//   skipped, so they follow GregTech's tiers and each needs the one before: tier 1 (x2) takes steel plates
//   (step 29), tier 1+ aluminium (40), tier 2 stainless steel (49), tier 3 titanium (66), tier 4 tungsten
//   steel (76), tier 5 (80) and the omega tier (81, nine of tier 5) iridium. The mod's conversion recipes use the
//   same ingredients, so they follow. Nothing else multiplies stack size: the chest, barrel and shulker
//   tiers add slots (the config's slot counts), limited barrels hold a fixed slot count, and the server
//   config has no stack setting except the cap of two stack upgrades per storage; the downgrade upgrades
//   only lower it.
// - Create's fluid tank, item vault and everything built on them (stock link, requester, shipping
//   containers) ask for #c:barrels/wooden, which held only the vanilla barrel (a GregTech assembler part,
//   step 38): Sophisticated Storage adds its plain barrel to the tag, planks and a lever, and those
//   recipes dropped by 25 steps. The barrel is taken out of the tag again, so they sit where they did.
// - Left as they are, unreachable on purpose: shulker boxes (the shell is End-only), the alchemy and
//   feeding upgrades (ghast tear, fermented spider eye, golden apple, glistering melon: Nether) and the
//   ender linker (blaze rods).

const VANILLA_WOODS = ['oak', 'spruce', 'birch', 'jungle', 'acacia', 'dark_oak', 'mangrove', 'cherry', 'bamboo', 'crimson', 'warped']

ServerEvents.tags('item', event => {
  event.remove('c:barrels/wooden', 'sophisticatedstorage:barrel')
})

ServerEvents.recipes(event => {
  VANILLA_WOODS.forEach(wood => {
    event.replaceInput({ mod: 'sophisticatedstorage' }, `minecraft:${wood}_planks`, '#minecraft:planks')
    event.replaceInput({ mod: 'sophisticatedstorage' }, `minecraft:${wood}_slab`, '#minecraft:wooden_slabs')
  })
  event.replaceInput({ mod: 'sophisticatedstorage' }, '#c:ingots/netherite', '#c:ingots/red_steel')
  event.replaceInput({ mod: 'sophisticatedstorage' }, '#c:storage_blocks/netherite', '#c:storage_blocks/red_steel')

  // stack upgrades: each tier moves to a GregTech material, so TFC's item size limits hold through the TFC game
  var STACK = /^sophisticatedstorage:stack_upgrade/
  ;[['#minecraft:logs', '#c:plates/steel'],
    ['#c:ingots/copper', '#c:ingots/aluminium'], ['#c:storage_blocks/copper', '#c:storage_blocks/aluminium'],
    ['#c:ingots/wrought_iron', '#c:ingots/stainless_steel'], ['#c:storage_blocks/wrought_iron', '#c:storage_blocks/stainless_steel'],
    ['#c:ingots/gold', '#c:ingots/titanium'], ['#c:storage_blocks/gold', '#c:storage_blocks/titanium'],
    ['#c:gems/diamond', '#c:ingots/tungsten_steel'], ['#c:storage_blocks/diamond', '#c:storage_blocks/tungsten_steel'],
    ['#c:ingots/red_steel', '#c:ingots/iridium'], ['#c:storage_blocks/red_steel', '#c:storage_blocks/iridium']
  ].forEach(pair => event.replaceInput({ id: STACK }, pair[0], pair[1]))

  // the tier upgrades of chests, barrels and shulker boxes are recipe types of the mod's own: restated
  function toRedSteel(id, type, base, result, ingots) {
    event.remove({ id: id })
    event.custom({
      type: type, category: 'misc',
      ingredients: [{ item: base }].concat(Array(ingots).fill({ tag: 'c:ingots/red_steel' })),
      result: { id: result, count: 1 }
    }).id(id)
  }
  var tierUpgrade = 'sophisticatedstorage:storage_tier_upgrade_shapeless'
  toRedSteel('sophisticatedstorage:netherite_barrel', tierUpgrade, 'sophisticatedstorage:diamond_barrel', 'sophisticatedstorage:netherite_barrel', 1)
  toRedSteel('sophisticatedstorage:netherite_chest', tierUpgrade, 'sophisticatedstorage:diamond_chest', 'sophisticatedstorage:netherite_chest', 1)
  toRedSteel('sophisticatedstorage:netherite_shulker_box', tierUpgrade, 'sophisticatedstorage:diamond_shulker_box', 'sophisticatedstorage:netherite_shulker_box', 1)
  toRedSteel('sophisticatedstorage:double_netherite_chest', 'sophisticatedstorage:double_chest_tier_upgrade_shapeless',
    'sophisticatedstorage:diamond_chest', 'sophisticatedstorage:netherite_chest', 2)
  ;[1, 2, 3, 4].forEach(n => {
    toRedSteel(`sophisticatedstorage:limited_netherite_barrel_${n}`, tierUpgrade, `sophisticatedstorage:limited_diamond_barrel_${n}`,
      `sophisticatedstorage:limited_netherite_barrel_${n}`, 1)
  })
})
