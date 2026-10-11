// UNTESTED, OPTIONAL. Sea-floor ores (kubejs/startup_scripts/sea_floor.js) drop GregTech raw ores. GregTech gives every raw ore a
// furnace recipe (minecraft:smelting, ids gtceu:smelting/smelt_raw_<ore>_ore_to_ingot) that the pack's smelting stations run from the
// low pressure steam furnace (checker step 16) or Create's fan (24): chalcopyrite -> TFC copper ingot, pyrite -> cast iron, sphalerite
// -> zinc, galena -> lead ingot, cobaltite -> cobalt ingot, pyrolusite -> manganese ingot, and barite, pollucite, pitchblende -> dust.
// None of those metals is earlier than today (copper 6, zinc 6, cast iron 16, lead and cobalt 20), but each is a 1:1 shortcut round
// GregTech's own ore chain (macerator x2, washer, centrifuge by-products, which is where niobium, caesium and uranium come from).
// Removing them keeps "GregTech ore goes through GregTech machines", the way compat/metal_gates.js keeps iron on the bloomery. Crushed,
// purified and refined ore and dust smelting stay as GregTech has them.

ServerEvents.recipes(event => {
  event.remove({
    type: 'minecraft:smelting',
    id: /^gtceu:smelting\/smelt_raw_(chalcopyrite|pyrite|sphalerite|galena|barite|pyrolusite|cobaltite|pitchblende|pollucite)_ore_to_ingot$/
  })
})
