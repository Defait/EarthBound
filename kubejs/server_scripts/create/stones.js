// Create's stones from TFC rock (docs/design.md: "Create addons").
//
// Create's decorative palette (and Create Deco's and Design n Decor's on top of it) starts from
// stones that Create places in vanilla world generation, which TFC worlds don't have. Once a base
// stone exists, Create's own stonecutting makes every cut, polished and brick variant of it.
// - Plain stones, by the stonecutter (or a mechanical saw): limestone and dripstone from TFC
//   limestone, calcite from chalk (both calcium carbonate), tuff from TFC's tuff.
// - Create's four coloured stones are ore stones in its own worlds: crushing them gives crushed
//   zinc, iron, gold or copper. Here they're dyed TFC cobble from a mixer, and their crushing
//   recipes go, so they stay decorative and ore still comes only from TFC's veins.

ServerEvents.recipes(event => {
  var cut = {
    'create:limestone': 'limestone',
    'minecraft:dripstone_block': 'limestone',
    'minecraft:calcite': 'chalk',
    'minecraft:tuff': 'tuff'
  }
  Object.keys(cut).forEach(stone => {
    var rock = cut[stone]
    event.stonecutting(stone, [`tfc:rock/raw/${rock}`, `tfc:rock/cobble/${rock}`])
      .id(`pack:stonecutting/${stone.split(':')[1]}_from_${rock}`)
  })

  var dyed = { asurine: 'blue', crimsite: 'red', ochrum: 'yellow', veridium: 'green' }
  Object.keys(dyed).forEach(stone => {
    var cobble = { tag: 'c:cobblestones/normal' }
    event.custom({
      type: 'create:mixing',
      ingredients: [cobble, cobble, cobble, cobble, { tag: `c:dyes/${dyed[stone]}` }],
      results: [{ id: `create:${stone}`, count: 4 }]
    }).id(`pack:mixing/${stone}`)
    event.remove({ id: `create:crushing/${stone}` })
    event.remove({ id: `create:crushing/${stone}_recycling` })
  })
})
