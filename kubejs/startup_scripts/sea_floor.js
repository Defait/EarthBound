// Sea-floor deposits (docs/design.md, "Deep sea"): five full-cube blocks that the worldgen in
// kubejs/data/pack/worldgen/*/ocean/ places on TFC's ridge, deep ocean and volcanic arc floors. Drops are GregTech raw ores
// (kubejs/data/pack/loot_table/blocks/), which GregTech's macerator turns into crushed ore, so no recipe is added.
//
// Full cubes only, on purpose: a block that replaces a TFC salt water source must not be waterloggable (a vanilla waterlogged
// state would put vanilla water into a TFC ocean). Textures are vanilla placeholders: replace with the pack's own art.

const $SoundType = Java.loadClass('net.minecraft.world.level.block.SoundType')
const $Particles = Java.loadClass('net.minecraft.core.particles.ParticleTypes')

StartupEvents.registry('block', event => {
  // A vent chimney: dark mineral, glows a little, puffs black water from its tip now and then (a "black smoker").
  event.create('pack:sulfide_chimney')
    .hardness(4.0).resistance(6.0)
    .soundType($SoundType.DEEPSLATE)
    .requiresTool()
    .tagBlock('minecraft:mineable/pickaxe')
    .lightLevel(0.3)
    .randomTick(cb => {
      const level = cb.level
      const pos = cb.block.pos
      // only the tip puffs: there is water, not another chimney block, above it
      if (!level.getBlockState(pos.above()).getFluidState().isEmpty() && cb.random.nextFloat() < 0.6) {
        level.sendParticles($Particles.SQUID_INK, pos.x + 0.5, pos.y + 1.1, pos.z + 0.5, 4, 0.1, 0.2, 0.1, 0.05)
        level.sendParticles($Particles.BUBBLE, pos.x + 0.5, pos.y + 1.1, pos.z + 0.5, 4, 0.2, 0.3, 0.2, 0.1)
      }
    })
    .texture('minecraft:block/blackstone')
    .displayName('Sulfide Chimney')

  // A white smoker: anhydrite (gypsum stands in for it) and a little zinc sulfide, pale and cooler (the arc's back-arc vents). Barite would be as real but its barium would pull the superconductors forward.
  event.create('pack:anhydrite_chimney')
    .hardness(3.0).resistance(5.0)
    .soundType($SoundType.CALCITE)
    .requiresTool()
    .tagBlock('minecraft:mineable/pickaxe')
    .texture('minecraft:block/calcite')
    .displayName('Anhydrite Chimney')

  // The mound a chimney field stands on, and the sulfide a vent leaves around itself.
  event.create('pack:sulfide_mound')
    .hardness(3.0).resistance(5.0)
    .soundType($SoundType.DEEPSLATE)
    .requiresTool()
    .tagBlock('minecraft:mineable/pickaxe')
    .texture('minecraft:block/deepslate_coal_ore')
    .displayName('Sulfide Mound')

  // Manganese nodule bed: mud with nodules lying on it. Shovel, so a diver can sweep a field quickly.
  event.create('pack:nodule_bed')
    .hardness(1.0).resistance(1.0)
    .soundType($SoundType.GRAVEL)
    .tagBlock('minecraft:mineable/shovel')
    .texture('minecraft:block/dirt')
    .displayName('Nodule Bed')

  // Ferromanganese crust on the ridge and arc rock.
  event.create('pack:mn_crust')
    .hardness(4.5).resistance(6.0)
    .soundType($SoundType.STONE)
    .requiresTool()
    .tagBlock('minecraft:mineable/pickaxe')
    .texture('minecraft:block/tuff')
    .displayName('Manganese Crust')
})
