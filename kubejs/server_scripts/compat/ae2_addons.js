// AE2's addons against the pack's design (docs/design.md: "AE2 addons"), on top of compat/ae2.js: ExtendedAE
// (with Glodium), AE2 Wireless Terminals, MEGA Cells, ME Requester and AE2 Import Export Card. None of them
// has worldgen or power of its own, so they land wherever their AE2 ingredients do: processors 54, drive 55,
// terminal 56, controller 63 (ae2.js).
//
// - ExtendedAE: its infinity cells (an endless water cell and an endless cobblestone cell, a diamond, a 16k
//   component, quartz glass and two buckets each) are not obtainable: those two recipes are removed. The
//   rest asks for AE2 parts and sits behind them. Its second silicon source is closed: a quartz blend
//   (quartz dust, sand and coal, smelted, blasted or enriched) made AE2's own silicon, and a recipe that
//   turns a block of silicon (eight GregTech silicon ingots around one of AE2's) into nine of AE2's, which
//   ae2.js keeps out of #c:silicon on purpose; with them, processors would skip GregTech's silicon. All of
//   them are removed; the block of silicon that the circuit cutter reads is GregTech's. The entro crystal
//   has no worldgen: an entro seed (sky dust, three ender dusts, redstone, glowstone, sand) right-clicked
//   on a fluix block makes an entroized budding block, which grows clusters like AE2's certus one; its
//   crystal assembler and machine frame come after those, and its concurrent processor press asks for
//   three eyes of ender, which are GregTech's chemistry (61). Nothing else changes.
// - AE2 Wireless Terminals: wireless terminals, pattern terminals, the universal ones and the magnet card sit
//   on AE2's wireless terminal (63, ender pearl chemistry for the wireless receiver). The quantum bridge card
//   takes an entangled singularity in place of the quantum link chamber, so it comes after the singularity
//   and the pair made from it (72), not before: it lets a terminal use a quantum bridge at any range.
// - MEGA Cells: the housing, components and cells are built from sky steel, sky bronze or osmium ingots (sky
//   stone, a charged certus crystal and an ingot of copper or iron in lava, 62; osmium is GregTech's, 79) and
//   from its accumulation processor. Its own press for those is a singularity between two of AE2's presses
//   (the singularity is 71). ExtendedAE's circuit cutter could print the processor from a block of sky steel
//   without the press, so that recipe is removed: the first accumulation processor comes after the press,
//   and with it every mega cell, interface, pattern provider and crafting unit, well past every AE2 cell they supersede
//   (256k, 62). Before the press only the sky ingots, the housings, the compression card and the cell dock exist. Its press copy asks for an iron block, which here is TFC's wrought iron block; the bulk cell
//   takes red steel where it asked for a netherite ingot. Its cells for Mekanism, Ars Nouveau, Botania and
//   soul/experience storage need mods the pack does not have (the recipes carry load conditions) and stay
//   unreachable.
// - ME Requester and AE2 Import Export Card: AE2 parts and the card on AE2's advanced card (55, diamonds and
//   processors). Its block picker card needs a diamond pickaxe, which TFC worlds do not have (diamonds are
//   TFC gems and the vanilla tool recipes are gone), and breaks blocks from a network; left unreachable.

ServerEvents.recipes(event => {
  // --- ExtendedAE
  ;[
    'extendedae:water_cell',
    'extendedae:cobblestone_cell',
    'extendedae:quartz_blend',
    'extendedae:quartz_blend_alt',
    'extendedae:blasting/quartz_blend',
    'extendedae:smelting/quartz_blend',
    'extendedae:mek/quartz_blend',
    'extendedae:silicon_block',
    'extendedae:silicon_decompress',
    // prints MEGA's accumulation processor from a block of sky steel, which would skip MEGA's own press
    'extendedae:cutter/accumulation_processor'
  ].forEach(id => event.remove({ id: id }))

  // --- Wireless Terminals: the quantum bridge card is the end of a pair
  event.replaceInput({ id: 'ae2wtlib:quantum_bridge_card' }, 'ae2:quantum_link', 'ae2:quantum_entangled_singularity')

  // --- MEGA Cells
  event.replaceInput({ id: 'megacells:cells/standard/bulk_item_cell' }, '#c:ingots/netherite', '#c:ingots/red_steel')
  // AE2 recipe type of its own, restated as ae2.js does for the presses
  event.remove({ id: 'megacells:inscriber/accumulation_processor_press_extra' })
  event.custom({
    type: 'ae2:inscriber', mode: 'inscribe',
    ingredients: { top: { item: 'megacells:accumulation_processor_press' }, middle: { tag: 'c:storage_blocks/wrought_iron' } },
    result: { id: 'megacells:accumulation_processor_press', count: 1 }
  }).id('megacells:inscriber/accumulation_processor_press_extra')
})
