// GregTech's steam age builds on Create (docs/design.md: "GregTech steam").
//
// The vanilla furnace these recipes asked for can't be made in a TFC world (only a GregTech
// assembler makes one), so the steam age couldn't start. Instead:
// - Every boiler needs a Create mechanical pump (the water feed). Steam machines all run on
//   boiler steam, so this one gate puts the whole steam age behind Create. Without it the lava
//   and solar boilers would start the steam age with no Create at all.
// - Coal boilers swap the furnace for the pump and vanilla bricks for TFC fire bricks.
// - Lava boilers' glass window slot becomes the pump; solar boilers' middle plate does.
// - Other machines with a firebox (steam furnace, steam alloy smelter, multi smelter) use TFC
//   fire bricks where they had a furnace.

const PUMP = 'create:mechanical_pump'
const FIRE_BRICKS = 'tfc:fire_bricks'

ServerEvents.recipes(event => {
  ;['gtceu:shaped/steam_boiler_coal_bronze', 'gtceu:shaped/steam_boiler_coal_steel'].forEach(id => {
    event.replaceInput({ id: id }, 'minecraft:furnace', PUMP)
    event.replaceInput({ id: id }, 'minecraft:bricks', FIRE_BRICKS)
  })

  ;['gtceu:shaped/steam_boiler_lava_bronze', 'gtceu:shaped/steam_boiler_lava_steel'].forEach(id => {
    event.replaceInput({ id: id }, 'minecraft:glass', PUMP)
  })

  // Glass appears three times in the solar boilers, so these are rewritten with the pump
  // in the middle of the plate row; everything else matches GregTech's pattern.
  event.remove({ id: 'gtceu:shaped/steam_boiler_solar_bronze' })
  event.shaped('gtceu:lp_steam_solar_boiler', ['GGG', 'SUS', 'PMP'], {
    G: 'minecraft:glass', S: '#c:plates/silver', U: PUMP,
    P: 'gtceu:bronze_small_fluid_pipe', M: 'gtceu:bronze_brick_casing',
  }).id('pack:gregtech/steam_boiler_solar_bronze')
  event.remove({ id: 'gtceu:shaped/steam_boiler_solar_steel' })
  event.shaped('gtceu:hp_steam_solar_boiler', ['GGG', 'SUS', 'PMP'], {
    G: 'minecraft:glass', S: '#c:double_plates/silver', U: PUMP,
    P: 'gtceu:steel_small_fluid_pipe', M: 'gtceu:steel_brick_casing',
  }).id('pack:gregtech/steam_boiler_solar_steel')

  ;['gtceu:shaped/steam_furnace_bronze', 'gtceu:shaped/steam_alloy_smelter_bronze', 'gtceu:shaped/multi_furnace'].forEach(id => {
    event.replaceInput({ id: id }, 'minecraft:furnace', FIRE_BRICKS)
  })
})
