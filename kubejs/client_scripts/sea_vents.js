// Vent cues, client side only (docs/design.md, "Deep sea"). UNTESTED: written without a game client.
// Server-side random-tick puffs fire once per ~68 s per block (3 random ticks per 16^3 section per tick), far too rare
// for smoke; a client scan costs the server nothing. Every second the nearby chunk sections that contain a chimney are
// scanned for tips (a chimney with no chimney above it); each tick the near tips emit smoke and bubbles, and the
// nearest one now and then a sound.
const $MC = Java.loadClass('net.minecraft.client.Minecraft')
const $P = Java.loadClass('net.minecraft.core.particles.ParticleTypes')
const $Sounds = Java.loadClass('net.minecraft.sounds.SoundEvents')
const $SoundSource = Java.loadClass('net.minecraft.sounds.SoundSource')
const $BlockPos = Java.loadClass('net.minecraft.core.BlockPos')

const BLACK = 'pack:sulfide_chimney'
const WHITE = 'pack:anhydrite_chimney'
const SCAN_EVERY = 20      // ticks
const SCAN_CHUNKS = 2      // radius in chunks (32+ blocks: the server's particle range and about a diver's sight)
const MAX_TIPS = 40
let tips = []              // [x, y, z, isBlack]

function isChimney(state) {
  const id = state.block.id
  return id == BLACK || id == WHITE
}

function scan(mc) {
  const level = mc.level, p = mc.player
  const found = []
  const pcx = Math.floor(p.x) >> 4, pcz = Math.floor(p.z) >> 4
  for (let dx = -SCAN_CHUNKS; dx <= SCAN_CHUNKS; dx++) {
    for (let dz = -SCAN_CHUNKS; dz <= SCAN_CHUNKS; dz++) {
      if (!level.hasChunk(pcx + dx, pcz + dz)) continue
      const chunk = level.getChunk(pcx + dx, pcz + dz)
      const secs = chunk.getSections()
      for (let i = 0; i < secs.length; i++) {
        const sec = secs[i]
        if (sec.hasOnlyAir() || !sec.maybeHas(s => isChimney(s))) continue   // palette check: cheap
        const y0 = (chunk.getMinSection() + i) << 4
        for (let x = 0; x < 16; x++) for (let y = 0; y < 16; y++) for (let z = 0; z < 16; z++) {
          const st = sec.getBlockState(x, y, z)
          if (!isChimney(st)) continue
          const bx = ((pcx + dx) << 4) + x, by = y0 + y, bz = ((pcz + dz) << 4) + z
          const above = level.getBlockState(new $BlockPos(bx, by + 1, bz))
          if (!isChimney(above)) found.push([bx, by, bz, st.block.id == BLACK])
        }
      }
    }
  }
  found.sort((a, b) => (a[0] - p.x) ** 2 + (a[2] - p.z) ** 2 - ((b[0] - p.x) ** 2 + (b[2] - p.z) ** 2))
  tips = found.slice(0, MAX_TIPS)
}

ClientEvents.tick(event => {
  const mc = $MC.getInstance()
  const level = mc.level, p = mc.player
  if (!level || !p) { tips = []; return }
  if (level.getGameTime() % SCAN_EVERY == 0) scan(mc)
  const r = Math.random
  for (const t of tips) {
    const x = t[0] + 0.5, y = t[1] + 1.05, z = t[2] + 0.5
    if ((x - p.x) ** 2 + (y - p.y) ** 2 + (z - p.z) ** 2 > 32 * 32) continue
    if (t[3]) {
      // black smoker: LARGE_SMOKE is drawn dark grey to black (SmokeParticle colours are 0-0.3); squid ink for bursts
      if (r() < 0.6) level.addParticle($P.LARGE_SMOKE, true, x + (r() - .5) * .4, y, z + (r() - .5) * .4, (r() - .5) * .02, 0.2 + r() * 0.15, (r() - .5) * .02)
      if (r() < 0.15) level.addParticle($P.SQUID_INK, true, x, y + .2, z, 0, 0.12, 0)
    } else {
      // white smoker: campfire smoke is a long-lived pale column
      if (r() < 0.25) level.addParticle($P.CAMPFIRE_COSY_SMOKE, true, x + (r() - .5) * .3, y, z + (r() - .5) * .3, 0, 0.06 + r() * .03, 0)
    }
    if (r() < 0.08) level.addParticle($P.BUBBLE_COLUMN_UP, true, x + (r() - .5) * .6, y, z + (r() - .5) * .6, 0, 0.1, 0)
  }
  if (tips.length && level.getGameTime() % 60 == 0) {
    const t = tips[0]
    if ((t[0] - p.x) ** 2 + (t[1] - p.y) ** 2 + (t[2] - p.z) ** 2 < 400) {
      level.playLocalSound(t[0] + .5, t[1] + 1, t[2] + .5, $Sounds.BUBBLE_COLUMN_UPWARDS_AMBIENT, $SoundSource.AMBIENT, 0.9, 0.6, false)
    }
  }
})
