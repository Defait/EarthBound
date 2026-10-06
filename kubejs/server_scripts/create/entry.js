// Create's entry into a TFC world (docs/design.md: "Create opens").
//
// - Vanilla andesite doesn't exist in TFC worlds. Create's andesite recipes take any TFC
//   igneous extrusive rock instead (andesite, basalt, dacite, rhyolite; raw or cobble), so
//   Create can start wherever volcanic rock is around, not only where andesite is.
// - TFC has no metal nuggets. Zinc nuggets already come from Create's ingot -> nugget recipe;
//   bronze nuggets get the same, so andesite alloy is a bronze-age (zinc or bronze) material.
// - Where Create used metal plates, it uses TFC sheets of the same metal (made on the anvil).
//   That puts the whisk, electron tube, saw and brass hand behind TFC metalworking.
// - The mechanical press takes a TFC wrought iron double sheet instead of an iron block, so
//   heavy machines need wrought iron sheets rather than nine iron ingots.
// - TFC's stripped logs and woods join the common tags, so andesite casings can be made.
// - Create's other vanilla-stone recipes (crushing diorite for quartz, milling granite) take the
//   TFC rock of the same name, which keeps rose quartz and electron tubes reachable. Only recipes
//   that name the stone itself are changed: a broader ingredient that happens to include it (any
//   stone, for TFC's handstone or Create's millstone) stays as it is. Create's decorative palette
//   (cut, polished, bricks) takes the TFC rock through Create's stone-type tags.

const ANDESITE_LIKE = ['andesite', 'basalt', 'dacite', 'rhyolite']
const TFC_SHEET_METALS = ['bismuth', 'bismuth_bronze', 'black_bronze', 'black_steel', 'blue_steel', 'brass', 'bronze',
  'cast_iron', 'copper', 'gold', 'nickel', 'red_steel', 'rose_gold', 'silver', 'steel', 'sterling_silver', 'tin',
  'wrought_iron', 'zinc']

// Vanilla stones Create uses that have a TFC rock of the same name.
const SAME_NAME_ROCKS = ['diorite', 'granite']
// The Create recipes that ask for these stones by item (from Create's recipe files).
const STONE_ITEM_RECIPES = {
  andesite: ['create:crafting/materials/andesite_alloy', 'create:crafting/materials/andesite_alloy_from_zinc',
    'create:mixing/andesite_alloy', 'create:mixing/andesite_alloy_from_zinc', 'create:milling/andesite'],
  diorite: ['create:crushing/diorite'],
  granite: ['create:milling/granite']
}

ServerEvents.tags('item', event => {
  ANDESITE_LIKE.forEach(rock => {
    event.add('pack:andesite_like', `tfc:rock/raw/${rock}`)
    event.add('pack:andesite_like', `tfc:rock/cobble/${rock}`)
  })
  SAME_NAME_ROCKS.forEach(rock => {
    event.add(`pack:${rock}_like`, `tfc:rock/raw/${rock}`)
    event.add(`pack:${rock}_like`, `tfc:rock/cobble/${rock}`)
  })
  ;['andesite'].concat(SAME_NAME_ROCKS).forEach(rock => {
    event.add(`create:stone_types/${rock}`, [`tfc:rock/raw/${rock}`, `tfc:rock/cobble/${rock}`])
  })
  event.add('c:stripped_logs', /^tfc:wood\/stripped_log\//)
  event.add('c:stripped_woods', /^tfc:wood\/stripped_wood\//)
})

ServerEvents.recipes(event => {
  Object.keys(STONE_ITEM_RECIPES).forEach(rock => {
    STONE_ITEM_RECIPES[rock].forEach(id => {
      event.replaceInput({ id: id }, `minecraft:${rock}`, `#pack:${rock}_like`)
    })
  })

  event.shapeless('9x gtceu:bronze_nugget', ['#c:ingots/bronze']).id('pack:create/bronze_nugget_from_ingot')

  TFC_SHEET_METALS.forEach(metal => {
    event.replaceInput({ mod: 'create' }, `#c:plates/${metal}`, `#c:sheets/${metal}`)
  })

  event.replaceInput({ id: 'create:crafting/kinetics/mechanical_press' }, '#c:storage_blocks/wrought_iron',
    'tfc:metal/double_sheet/wrought_iron')
})
