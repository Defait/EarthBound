// CC: Tweaked and Create: Avionics against the pack's design (docs/design.md: "CC: Tweaked").
//
// - Computers: a computer took stone, redstone and a glass pane, which is the copper age (step 19). A
//   computer is electronics here: the redstone in the middle is a GregTech circuit, the basic electronic
//   circuit (LV) for a normal computer (34) and the good one (MV) for an advanced one built from scratch; the
//   mod's upgrade recipe (a normal computer and seven gold ingots) makes an advanced computer at 35. Monitors, disk
//   drives, printers, cables and wired modems stay as they are (stone, glass, redstone): they do nothing
//   without a computer. Wireless modems take ender pearls (normal) or an eye of ender (advanced), so they
//   wait for GregTech's ender chemistry (61, 62).
// - Turtles: a turtle is a computer in a steel casing with a chest (normal: steel plates, 35; the advanced one
//   upgrades from it, 36). The recipe type is the mod's own and is restated. Pocket computers asked for a golden
//   apple, which TFC worlds lack; they take a GregTech battery instead, a sodium one (LV, 38) for a normal and an
//   MV one for an advanced pocket computer (39, 40).
// - What a turtle can do: it digs, farms and fights only with a tool upgrade. CC's upgrades are data
//   (data/<ns>/computercraft/turtle_upgrade, type computercraft:tool, any item), and the mod's own five name the
//   vanilla diamond tools, which TFC worlds cannot make (the gem is TFC's, the vanilla tool recipes are gone).
//   kubejs/data/pack/computercraft/turtle_upgrade/ adds five of GregTech's aluminium tools in their place
//   (pickaxe, axe, shovel, hoe, sword, with the vanilla ones' breakable tags and damage multipliers): a turtle
//   and a tool in the crafting grid make the tooled turtle, as for the vanilla ones. Aluminium is the
//   gate: its ingot comes out of the electric blast furnace (38) and the tools are 40, level with the MV machine
//   hull (41), so a mining or farming turtle cannot exist before MV, long after Create's drills, harvesters and
//   deployers. A plain turtle (35) still only moves, places, crafts, carries and takes modems. The mod ships a
//   crafting recipe per upgrade as data files (computercraft:impostor_shaped, a turtle and the tool side by side
//   make a turtle with the upgrade), so the ten for the five tools and two turtle kinds are written here.
// - Create: Avionics has no recipes or items of its own: it makes Create: Simulated's and Aeronautics' blocks
//   (physics assembler, thrusters, propellers, gimbals, sensors) peripherals of a computer, so ships can be
//   flown by program. With computers at 34 and up, program-flown airships come after electricity, not at the
//   brass age airships start in (21). Its ComputerCraft peripherals for Create itself come from Simulated's.
// - The command computer needs a command block and stays out of reach; config/computercraft-server.toml is
//   the mod's default (command computers also need creative mode there).

ServerEvents.recipes(event => {
  event.replaceInput({ id: 'computercraft:computer_normal' }, '#c:dusts/redstone', 'gtceu:basic_electronic_circuit')
  event.replaceInput({ id: 'computercraft:computer_advanced' }, '#c:dusts/redstone', 'gtceu:good_electronic_circuit')

  // turtles: a recipe type of the mod's own (it copies the computer's id and label onto the turtle)
  function turtle(kind, plate) {
    var id = `computercraft:turtle_${kind}`
    var computer = `computercraft:computer_${kind}`
    event.remove({ id: id })
    event.custom({
      type: 'computercraft:transform_shaped',
      category: 'redstone',
      pattern: ['###', '#C#', '#I#'],
      key: { '#': { tag: plate }, C: { item: computer }, I: { tag: 'c:chests/wooden' } },
      result: { id: id, count: 1 },
      function: [{ from: { item: computer }, type: 'computercraft:copy_components' }]
    }).id(id)
  }
  turtle('normal', 'c:plates/steel')
  turtle('advanced', 'c:plates/stainless_steel')

  // pocket computers: a battery in place of the golden apple
  event.replaceInput({ id: 'computercraft:pocket_computer_normal' }, 'minecraft:golden_apple', 'gtceu:lv_sodium_battery')
  event.replaceInput({ id: 'computercraft:pocket_computer_advanced' }, 'minecraft:golden_apple', 'gtceu:mv_sodium_battery')

  // tooled turtles: a turtle and an aluminium tool side by side (the mod's own recipes for its upgrades, for ours)
  ;['pickaxe', 'axe', 'shovel', 'hoe', 'sword'].forEach(tool => {
    ;['normal', 'advanced'].forEach(kind => {
      event.custom({
        type: 'computercraft:impostor_shaped',
        category: 'redstone',
        group: `computercraft:turtle_${kind}`,
        pattern: ['#T'],
        key: { '#': { item: `gtceu:aluminium_${tool}` }, T: { item: `computercraft:turtle_${kind}` } },
        result: { id: `computercraft:turtle_${kind}`, count: 1, components: { 'computercraft:right_turtle_upgrade': { id: `pack:aluminium_${tool}` } } }
      }).id(`pack:computercraft/turtle_${kind}_aluminium_${tool}`)
    })
  })
})
