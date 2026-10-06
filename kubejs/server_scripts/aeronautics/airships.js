// Airships unlock with brass (docs/design.md: "Airships").
//
// Every way to get airborne needs brass: lift (hot-air burner, steam vent, envelopes) and thrust
// (all propellers). Ground vehicles and the physics assembler stay brass-free.
// - Hot-air burner: its "fire" is a vanilla coal block, which TFC worlds lack, so TFC coal and
//   charcoal count too (the burner itself burns no fuel; it runs on redstone). Its andesite alloy
//   becomes brass plates.
// - Steam vent: brass plate instead of the gold one.
// - Envelopes: brass nuggets instead of sticks (about one brass ingot per 18 envelopes by hand,
//   27 with a deployer).
// - Andesite propeller (and the wooden one made from it): a brass casing instead of the wooden
//   slab, like the propeller bearing, smart propeller and gyroscopic bearing already have.
// - Portable engine: TFC fire bricks instead of the vanilla blast furnace (as in GregTech's
//   steam machines) and a brass top plate.

ServerEvents.tags('item', event => {
  event.add('aeronautics:burner_fire', '#minecraft:coals')
})

ServerEvents.recipes(event => {
  event.replaceInput({ id: 'aeronautics:adjustable_burner' }, 'create:andesite_alloy', '#c:plates/brass')

  event.replaceInput({ id: 'aeronautics:steam_vent' }, '#c:plates/gold', '#c:plates/brass')

  var envelopes = { id: /^aeronautics:(deploying\/deploying_envelope_[a-z_]+|[a-z_]+_envelope)$/ }
  event.replaceInput(envelopes, 'minecraft:stick', '#c:nuggets/brass')

  event.replaceInput({ id: 'aeronautics:andesite_propeller' }, '#minecraft:wooden_slabs', 'create:brass_casing')

  event.replaceInput({ id: 'simulated:red_portable_engine' }, 'minecraft:blast_furnace', 'tfc:fire_bricks')
  // Unification may not have run yet, so the plate can still be named by the iron tag.
  ;['#c:plates/iron', '#c:plates/wrought_iron'].forEach(plate => {
    event.replaceInput({ id: 'simulated:red_portable_engine' }, plate, '#c:plates/brass')
  })
})
