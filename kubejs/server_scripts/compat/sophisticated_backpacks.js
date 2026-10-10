// Sophisticated Backpacks against the pack's design (docs/design.md: "Sophisticated Backpacks").
//
// It is Sophisticated Storage's twin (same author, same Core, same upgrades), so it is fitted the same way
// (compat/sophisticated_storage.js) and the two share a ladder.
//
// - Tiers: copper, iron, gold and diamond backpacks are tags already (iron is TFC wrought iron through
//   Almost Unified, diamond the gem TFC's kimberlite gives): steps 14, 20, 21, 22. Netherite has no
//   source here (the Nether is closed), so the top tier takes red steel as Sophisticated Storage's
//   netherite chest does (38). Its upgrade is a smithing recipe of the mod's own (template, backpack, ingot),
//   restated with red steel sheets as the template and an ingot as the addition; the backpack keeps its contents.
// - The base backpack is an iron-age good: it takes two wrought iron ingots in place of two of its strings (leather,
//   string, a wooden chest and the iron; a recipe type of the mod's own, restated), so stone, copper and bronze
//   keep TFC's own carrying limits. 27 slots and one upgrade slot, carried on the back. Base 20; the tiers
//   above follow it by their own materials (copper 21, iron 21, gold 22, diamond 23).
// - Stack upgrades: the storage mod's stack upgrades and these are the same thing under other names, and the
//   storage mod's recipes already convert one into the other (backpack starter = storage 1+, tier 1 = 2, tier
//   2 = 3, tier 3 = 4, tier 4 = 5, omega = omega). They would multiply a slot's stack limit and so skip
//   TFC's item size limits, so they sit on the storage ladder's GregTech materials, rung for rung: starter
//   aluminium blocks (40), tier 1 stainless steel (49), tier 2 titanium (66), tier 3 tungsten steel (76),
//   tier 4 iridium (80), omega nine of those (81). The conversions between tiers use the same ingredients,
//   so they follow; if they did not, the cheap backpack route would undercut the storage one through the
//   mod's own conversion recipes. Up to three stack upgrades per backpack (server config).
// - TFC's size and weight rules: a TFC chest refuses every item larger than the server config's
//   chestMaximumItemSize ("large": no log, door, boat, barrel, anvil, large vessel, and no tool but the knife and
//   chisel), and carrying many very heavy things overburdens a player, counting the player's own inventory only.
//   A backpack on the back is neither. The pack's own mod (mod/, pack_world 1.5.0, StorageSizeMixin) makes the
//   inventory under every Sophisticated Backpack and every Sophisticated Storage block refuse what TFC's chest
//   refuses, by calling TFC's own check (TFCChestBlockEntity.isValid: ItemSizeManager's size of the stack against
//   that config value), so there is no list and the rule follows TFC's config and any item TFC sizes. Taking
//   things out is unaffected, so what a storage already held stays retrievable. The overburden rule still
//   counts what the player carries directly. An earlier hand-kept list of 599 ids is gone.
//   Tools and weapons are the exception, for backpacks only (the mixin matches the handler's class by name): the c:tools
//   item tag (TFC's, GregTech's, vanilla-style and AE2's tools, shields and bows; no buckets, anvils or machines) goes in a
//   backpack although TFC sizes them "very large" and a chest refuses them, since spares are what a backpack is for and the
//   tool swapper upgrade swaps from them. Sophisticated Storage's blocks keep matching a TFC chest exactly.
// - Tool swapper: wooden tools in its recipe are the vanilla ones, which TFC worlds lack; any tool of the
//   kind does.
// - Left as they are, unreachable on purpose: the feeding upgrades (golden apple, golden carrot and
//   glistering melon, vanilla foods TFC lacks; they would also auto-eat past TFC's food rules), alchemy
//   (ghast tear, blaze rod, fermented spider eye), the mob catcher's advanced tier (wither skull), inception,
//   everlasting and the two infinity upgrades (nether stars, end crystals).
// - What does land, and where (the magnet, refill, void and mob catcher upgrades take ender pearls, so they
//   wait for GregTech's ender chemistry, 61; furnace upgrades need a furnace, smoker or blast furnace item,
//   which is GregTech-assembled here, 38 to 40): the mob catcher can pick up TFC livestock; battery upgrades
//   store FE but make none; pump and tank upgrades handle fluids like any tank. Its chest loot modifiers
//   are not in global_loot_modifiers.json (the loot lane replaces the list), so no structure chest holds a backpack.

ServerEvents.recipes(event => {
  // --- base backpack: two wrought iron ingots in the place of two strings
  event.remove({ id: 'sophisticatedbackpacks:backpack' })
  event.custom({
    type: 'sophisticatedbackpacks:basic_backpack',
    category: 'misc',
    pattern: ['SLS', 'ICI', 'LLL'],
    key: { S: { tag: 'c:strings' }, L: { tag: 'c:leathers' }, I: { tag: 'c:ingots/wrought_iron' }, C: { tag: 'c:chests/wooden' } },
    result: { id: 'sophisticatedbackpacks:backpack', count: 1 }
  }).id('sophisticatedbackpacks:backpack')

  // --- stack upgrades on the storage mod's rungs
  var STACK = /^sophisticatedbackpacks:stack_upgrade/
  ;[['#c:storage_blocks/copper', '#c:storage_blocks/aluminium'],
    ['#c:storage_blocks/iron', '#c:storage_blocks/stainless_steel'],
    ['#c:storage_blocks/wrought_iron', '#c:storage_blocks/stainless_steel'],
    ['#c:storage_blocks/gold', '#c:storage_blocks/titanium'],
    ['#c:storage_blocks/diamond', '#c:storage_blocks/tungsten_steel'],
    ['#c:storage_blocks/netherite', '#c:storage_blocks/iridium']
  ].forEach(pair => event.replaceInput({ id: STACK }, pair[0], pair[1]))

  // --- netherite backpack: red steel in place of the template and the ingot
  event.remove({ id: 'sophisticatedbackpacks:netherite_backpack' })
  event.custom({
    type: 'sophisticatedbackpacks:smithing_backpack_upgrade',
    template: { tag: 'c:sheets/red_steel' },
    base: { item: 'sophisticatedbackpacks:diamond_backpack' },
    addition: { tag: 'c:ingots/red_steel' },
    result: { id: 'sophisticatedbackpacks:netherite_backpack', count: 1 }
  }).id('sophisticatedbackpacks:netherite_backpack')

  // --- tool swapper: any tool of each kind in place of the wooden ones
  var swapper = { id: 'sophisticatedbackpacks:tool_swapper_upgrade' }
  event.replaceInput(swapper, 'minecraft:wooden_pickaxe', '#minecraft:pickaxes')
  event.replaceInput(swapper, 'minecraft:wooden_axe', '#minecraft:axes')
  event.replaceInput(swapper, 'minecraft:wooden_shovel', '#minecraft:shovels')
  event.replaceInput(swapper, 'minecraft:wooden_sword', '#minecraft:swords')
})
