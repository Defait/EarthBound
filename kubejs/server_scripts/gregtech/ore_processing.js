// GregTech's ore processing runs on TFC's ores (docs/design.md: "GregTech ores").
//
// - GregTech's own ore veins are switched off (GregTech's removal keeps them registered but stops
//   them generating). TFC's overworld never placed them, but the Nether and the End would have.
// - TFC ore pieces go into GregTech's macerator (steam or electric) and come out as GregTech
//   crushed ore, which then follows GregTech's usual chain (washing, purifying, centrifuging,
//   smelting). The macerator doubles TFC's yield, the way it doubles a vanilla raw ore: a crushed
//   ore is one ingot (100 mB), so every 50 mB of TFC ore gives one crushed ore.
//     small (10 mB) 5 -> 1, poor (15 mB) 10 -> 3, normal (25 mB) 2 -> 1, rich (35 mB) 10 -> 7
//   Mineral and gem ores (one piece per block, no grades) count as a GregTech ore block: 1 -> 2.
// - Create crushes TFC ores into the same crushed ores (docs/design.md: "Create <-> GregTech").
//   Create machines take one piece at a time, so fractions become chances: crushing wheels match
//   the macerator (a rich piece gives a crushed ore 70% of the time), and the millstone gives
//   TFC's own yield, half of that, like GregTech's forge hammer does for its ores.
// - What the crushed iron ores smelt into is set in compat/metal_gates.js (TFC cast iron).

// TFC graded ore -> GregTech material with crushed ore.
const GRADED_ORES = {
  native_copper: 'copper', native_gold: 'gold', native_silver: 'silver',
  hematite: 'hematite', magnetite: 'magnetite', limonite: 'yellow_limonite',
  cassiterite: 'cassiterite', garnierite: 'garnierite', malachite: 'malachite',
  sphalerite: 'sphalerite', tetrahedrite: 'tetrahedrite',
}
// GregTech has no bismuthinite ore, so TFC's goes straight to bismuth dust at the same rate.
const GRADED_TO_DUST = { bismuthinite: 'bismuth' }

// [count in, count out] per grade: twice TFC's metal, one crushed ore per 50 mB.
const GRADES = { small: [5, 1], poor: [10, 3], normal: [2, 1], rich: [10, 7] }

// TFC mineral/gem ore -> GregTech material with crushed ore.
const MINERAL_ORES = {
  cinnabar: 'cinnabar', graphite: 'graphite', saltpeter: 'saltpeter', sulfur: 'sulfur',
  sylvite: 'rock_salt', halite: 'salt', gypsum: 'gypsum', pyrite: 'pyrite',
  amethyst: 'amethyst', diamond: 'diamond', emerald: 'emerald', lapis_lazuli: 'lapis',
  opal: 'opal', ruby: 'ruby', sapphire: 'sapphire', topaz: 'topaz',
}
const MINERAL_TO_DUST = { borax: 'borax' }

GTCEuServerEvents.oreVeins(event => {
  event.removeAll()
})

ServerEvents.recipes(event => {
  function macerate(input, count, output, outCount) {
    // GregTech recipes take their id as the first argument (.id() clashes with the schema's id key);
    // GregTech inserts the machine type, so this becomes e.g. pack:macerator/rich_hematite.
    event.recipes.gtceu.macerator(`pack:${input.split('/')[1]}`)
      .itemInputs(`${count}x ${input}`)
      .itemOutputs(`${outCount}x ${output}`)
      .duration(200 * outCount)
      .EUt(2, 1)
  }

  function createProcess(type, input, output, perPiece, time) {
    var result = perPiece >= 1 ? { id: output, count: perPiece } : { id: output, chance: perPiece }
    event.custom({ type: `create:${type}`, ingredients: [{ item: input }], results: [result], processing_time: time })
      .id(`pack:${type}/${input.split('/')[1]}`)
  }

  // [TFC item, pieces in, GregTech output, count out, doubled]: the macerator's rate. Ores are
  // doubled (see above); coal isn't.
  var entries = []
  Object.keys(GRADES).forEach(grade => {
    var counts = GRADES[grade]
    Object.keys(GRADED_ORES).forEach(ore => {
      entries.push([`tfc:ore/${grade}_${ore}`, counts[0], `gtceu:crushed_${GRADED_ORES[ore]}_ore`, counts[1], true])
    })
    Object.keys(GRADED_TO_DUST).forEach(ore => {
      entries.push([`tfc:ore/${grade}_${ore}`, counts[0], `gtceu:${GRADED_TO_DUST[ore]}_dust`, counts[1], true])
    })
  })
  Object.keys(MINERAL_ORES).forEach(ore => {
    entries.push([`tfc:ore/${ore}`, 1, `gtceu:crushed_${MINERAL_ORES[ore]}_ore`, 2, true])
  })
  Object.keys(MINERAL_TO_DUST).forEach(ore => {
    entries.push([`tfc:ore/${ore}`, 1, `gtceu:${MINERAL_TO_DUST[ore]}_dust`, 2, true])
  })
  // TFC coal is already the fuel itself, like a vanilla coal: one piece grinds to one dust.
  entries.push(['tfc:ore/bituminous_coal', 1, 'gtceu:coal_dust', 1, false])
  entries.push(['tfc:ore/lignite', 2, 'gtceu:coal_dust', 1, false])

  entries.forEach(e => {
    var perPiece = e[3] / e[1]
    macerate(e[0], e[1], e[2], e[3])
    createProcess('crushing', e[0], e[2], perPiece, 250)
    createProcess('milling', e[0], e[2], e[4] ? perPiece / 2 : perPiece, 200)
  })
})
