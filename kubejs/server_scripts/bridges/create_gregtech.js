// Create and GregTech work through each other's recipes (docs/design.md: "Create <-> GregTech").
//
// Create makes GregTech's early intermediates:
// - The mechanical press presses ingots into GregTech plates, one for one, like GregTech's bender
//   (by hand GregTech needs two ingots per plate). Create already did this for copper, iron, gold
//   and brass, whose Create sheets unify to GregTech plates; this adds the other early metals,
//   TFC's alloys and rubber.
// - The mechanical saw slits a plate into two single wires, the rate of GregTech's wiremill
//   (one ingot, two wires); by hand a plate makes one.
// - Crushing wheels and the millstone crush TFC ores into GregTech crushed ore
//   (gregtech/ore_processing.js).
//
// GregTech's LV components are built from Create parts, like for like: a motor's two rods become
// Create shafts, a pump's bronze pipe becomes a Create mechanical pump, and a piston's small gear
// becomes a Create cogwheel, in both the crafting and the assembler recipes.

const PRESSED_PLATES = ['tin', 'bronze', 'steel', 'zinc', 'nickel', 'lead', 'silver', 'invar', 'red_alloy', 'tin_alloy',
  'cupronickel', 'potin', 'electrum', 'battery_alloy', 'bismuth_bronze', 'black_bronze', 'rose_gold', 'sterling_silver',
  'black_steel', 'red_steel', 'blue_steel', 'annealed_copper', 'rubber']
const SAWN_WIRES = ['copper', 'annealed_copper', 'tin', 'red_alloy', 'gold', 'silver', 'lead', 'cupronickel', 'electrum',
  'nickel']

ServerEvents.recipes(event => {
  PRESSED_PLATES.forEach(metal => {
    event.custom({
      type: 'create:pressing',
      ingredients: [{ tag: `c:ingots/${metal}` }],
      results: [{ id: `gtceu:${metal}_plate` }],
    }).id(`pack:pressing/${metal}_plate`)
  })

  SAWN_WIRES.forEach(metal => {
    event.custom({
      type: 'create:cutting',
      ingredients: [{ tag: `c:plates/${metal}` }],
      results: [{ id: `gtceu:${metal}_single_wire`, count: 2 }],
      processing_time: 100,
    }).id(`pack:cutting/${metal}_single_wire`)
  })

  var motors = { id: /^gtceu:(shaped|assembler)\/electric_motor_lv_/ }
  // Unification may not have run yet, so iron rods can still be named by the iron tag.
  ;['#c:rods/iron', '#c:rods/wrought_iron', '#c:rods/steel'].forEach(rod => {
    event.replaceInput(motors, rod, 'create:shaft')
  })
  event.replaceInput({ id: /^gtceu:(shaped|assembler)\/electric_pump_lv_/ }, 'gtceu:bronze_normal_fluid_pipe', 'create:mechanical_pump')
  event.replaceInput({ id: /^gtceu:(shaped|assembler)\/electric_piston_lv$/ }, '#c:small_gears/steel', 'create:cogwheel')
})
