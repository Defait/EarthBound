// Dev-only check run by tools/rocksample.py: how far is TFC's igneous extrusive rock (andesite, basalt, dacite,
// rhyolite: what Create's andesite alloy needs) from a start, without generating any chunks.
// The Python tool rewrites the job line below and copies this file into the test server's
// local/kubejs/local_server_scripts for one run; it is never part of the pack.
// Rock comes from TFC's own ChunkDataGenerator (the same call chunk generation makes, see docs in rocksample.py).
// Note: function-local variables use var; Rhino rejects block-scoped const in callbacks that run repeatedly.
const $RockSampleProjection = Java.loadClass('net.yazloysasha.tfcrealworld.util.projection.ProjectionManager')
const $RockSampleConfig = Java.loadClass('net.yazloysasha.tfcrealworld.config.TFCRealWorldConfig')
const $RockSampleTectonics = Java.loadClass('net.yazloysasha.tfcrealworld.world.tectonics.TectonicsMap')
const $RockSampleContinents = Java.loadClass('net.yazloysasha.tfcrealworld.world.noise.png.PNGContinentNoise')
const $RockSampleHotspots = Java.loadClass('net.yazloysasha.tfcrealworld.world.volcano.MapHotspotLayout')
const $RockSampleRegistries = Java.loadClass('net.minecraft.core.registries.BuiltInRegistries')
const $RockSampleHeightmap = Java.loadClass('net.minecraft.world.level.levelgen.Heightmap$Types')

// Replaced by the Python tool. named: [[name, lat, lon, x, z]] (x, z null unless given in blocks), candidates: [[x, z]] for random land points,
// probes: [[x, z, y, tag]] rock lookups for checking against a generated world.
const ROCKSAMPLE_JOB = /*JOB*/ {
  expectH: 862198, expectV: 419647, rocks: ['andesite', 'basalt', 'dacite', 'rhyolite'], step: 32, cap: 25000, depths: [25, 50, 75, 100], heightBudget: 2000,
  placeSeconds: 300, startSearch: 48, named: [], random: 0, candidates: [], probes: []
} /*END*/

function rocksampleOut(tag, obj) {
  console.info('[rocksample] ' + tag + ' ' + JSON.stringify(obj))
}

ServerEvents.loaded(event => {
  console.info('[rocksample] start')
  try {
    rocksampleRun(event.server, ROCKSAMPLE_JOB)
  } catch (e) {
    console.info('[rocksample] FATAL ' + e + (e && e.stack ? ' ' + String(e.stack).replace(/\s+/g, ' ') : ''))
  }
  console.info('[rocksample] done')
})

function rocksampleRun(server, job) {
  var level = server.overworld()
  var generator = level.getChunkSource().getGenerator() // net.dries007.tfc.world.TFCChunkGenerator
  var cdg = generator.chunkDataGenerator() // RegionChunkDataGenerator
  var randomState = level.getChunkSource().randomState()
  var seaLevel = Number(generator.getSeaLevel())
  var H = Number(String($RockSampleConfig.HORIZONTAL_SCALE.get()))
  var V = Number(String($RockSampleConfig.VERTICAL_SCALE.get()))
  var seed = String(level.getSeed())
  rocksampleOut('I', { H: H, V: V, seaLevel: seaLevel, seed: seed, rocks: job.rocks, generator: String(generator) })
  if (H !== job.expectH || V !== job.expectV) {
    console.info('[rocksample] FATAL map radius is ' + H + ' x ' + V + ', expected ' + job.expectH + ' x ' + job.expectV + ' (20 m per block); is world_scale.js in the pack and the world fresh?')
    return
  }

  function rockName(rs) {
    return String($RockSampleRegistries.BLOCK.getKey(rs.raw())).replace('tfc:rock/raw/', '')
  }

  // The target RockSettings (job.rocks, default the four extrusive rocks) by identity (fast); falls back to
  // comparing names if identity misbehaves.
  var target = {}
  for (var ti = 0; ti < job.rocks.length; ti++) target[job.rocks[ti]] = true
  var ext = []
  var all = generator.rockLayerSettings().getRocks().iterator()
  while (all.hasNext()) {
    var rs0 = all.next()
    if (target[rockName(rs0)] === true) ext.push(rs0)
  }
  if (ext.length !== job.rocks.length) {
    console.info('[rocksample] FATAL target rocks ' + JSON.stringify(job.rocks) + ' are not all TFC rock layer rocks (found ' + ext.length + ')')
    return
  }
  var nameMode = false
  function isExtById(rs) {
    for (var q = 0; q < ext.length; q++) if (rs === ext[q]) return true
    return false
  }
  function isExtByName(rs) {
    return target[rockName(rs)] === true
  }
  var isExt = nameMode ? isExtByName : isExtById
  function selfTest(x0, z0) {
    var bad = 0
    for (var a = 0; a < 20; a++) {
      for (var b = 0; b < 20; b++) {
        var rs = cdg.generateSurfaceRock(x0 + a * 200, z0 + b * 200)
        if (isExtById(rs) !== isExtByName(rs)) bad++
      }
    }
    return bad
  }

  // Open sea (the continent map says ocean for the whole 3x3 grid cells around) is below sea level without a height call.
  function surelySea(cx, cz) {
    if (!contForSea) return false
    try {
      for (var a = -1; a <= 1; a++) {
        for (var b = -1; b <= 1; b++) {
          if (String(contForSea.bandAtGridHard(cx / 128 + a, cz / 128 + b)) !== 'OCEAN') return false
        }
      }
      return true
    } catch (e4) {
      contForSea = null
      return false
    }
  }

  function topAt(x, z) {
    return Number(generator.getBaseHeight(x, z, $RockSampleHeightmap.WORLD_SURFACE_WG, level, randomState))
  }

  // Category estimate (Real World's tectonics and continent maps through the mod's own sampler, then
  // ChooseRocks' 5x5 rule). The region point that holds the real category isn't reachable from a script.
  var zoneOf = null
  var contForSea = null
  try {
    var tec = $RockSampleTectonics.tryCreate(H, V)
    var cont = new $RockSampleContinents(H, V)
    contForSea = cont
    var hot = null
    try {
      hot = $RockSampleHotspots.create(tec, 0)
    } catch (e1) {
      hot = null
    }
    var points = {}
    var pointAt = function (gx, gz) {
      var key = gx + ',' + gz
      var p = points[key]
      if (p) return p
      var cls = tec.classAtGrid(gx, gz)
      var band = String(cont.bandAtGridHard(gx + 0.5, gz + 0.5))
      var relief = String(cls.land().name())
      var volcanism = String(cls.volcanism().name())
      var islandish = relief !== 'MOUNTAIN' && (band === 'ISLAND' || (band === 'OCEAN' && cont.anyIslandInCell(gx, gz)))
      p = { land: false, island: false, volcanic: false, mountain: false, hot: false }
      if (islandish && volcanism === 'ARC') {
        p.volcanic = true
      } else if (islandish) {
        p.land = true
        p.island = true
        p.volcanic = volcanism !== 'NONE'
      } else if (band === 'OCEAN') {
        p.volcanic = volcanism === 'ARC'
      } else {
        p.land = true
        p.volcanic = volcanism !== 'NONE'
      }
      var age = hot ? Number(hot.ageAtGrid(gx, gz)) : 0
      if (age > 0) {
        p.hot = true
        if (age !== 4) p.land = true
      }
      p.mountain = p.land && relief === 'MOUNTAIN'
      points[key] = p
      return p
    }
    zoneOf = function (x, z) {
      var gx = Math.floor(x / 128)
      var gz = Math.floor(z / 128)
      var type = pointAt(gx, gz).land ? 'LAND' : 'OCEAN'
      var best = 1000
      for (var dx = -2; dx <= 2; dx++) {
        for (var dz = -2; dz <= 2; dz++) {
          var p = pointAt(gx + dx, gz + dz)
          var d = Math.abs(dx) + Math.abs(dz)
          if (d < best) {
            if ((p.island && d < 4) || p.hot || p.volcanic) {
              type = 'VOLCANIC'
              best = d
            } else if (p.mountain && d < 3) {
              type = 'UPLIFT'
              best = d
            }
          }
        }
      }
      return type
    }
  } catch (e2) {
    console.info('[rocksample] zone estimate unavailable: ' + e2)
    zoneOf = null
  }
  var zoneSafe = function (zx, zz) {
    if (!zoneOf) return null
    try {
      return zoneOf(zx, zz)
    } catch (e3) {
      console.info('[rocksample] zone estimate failed: ' + e3)
      zoneOf = null
      return null
    }
  }

  // ---------------------------------------------------------------- probes (checking against a generated world)
  var probes = job.probes
  for (var pi = 0; pi < probes.length; pi++) {
    var pr = probes[pi]
    var ptop = topAt(pr[0], pr[1])
    var po = { tag: pr[3], x: pr[0], z: pr[1], y: pr[2], top: ptop, rock: rockName(cdg.generateRock(pr[0], pr[2], pr[1], ptop, null)) }
    rocksampleOut('P', po)
  }

  // ---------------------------------------------------------------- the search around one start
  function evaluate(x, z, meta) {
    var t0 = Date.now()
    var step = job.step
    var cap = job.cap
    var depths = job.depths
    var top = topAt(x, z)
    var res = { surface: { any: null, land: null }, dig: { any: null, land: null }, columns: 0, heightCalls: 0, cut: false, timedOut: false }
    var landMemo = {}
    var isLand = function (cx, cz) {
      var k = cx + ',' + cz
      var v = landMemo[k]
      if (v !== undefined) return v
      if (surelySea(cx, cz)) {
        landMemo[k] = false
        return false
      }
      if (res.heightCalls >= job.heightBudget) {
        res.cut = true
        return null
      }
      res.heightCalls++
      v = topAt(cx, cz) > seaLevel
      landMemo[k] = v
      return v
    }
    var consider = function (rec, e, cx, cz, depth) {
      var needAny = rec.any === null || e < rec.any.d
      var needLand = rec.land === null || e < rec.land.d
      if (!needAny && !needLand) return
      var l = isLand(cx, cz)
      var hit = { d: Math.round(e), x: cx, z: cz, land: l, depth: depth }
      if (needAny) {
        if (rec.any !== null && rec.any.land === true && (rec.land === null || rec.any.d < rec.land.d)) rec.land = rec.any
        rec.any = hit
      }
      if (l === true && (rec.land === null || e < rec.land.d)) rec.land = hit
    }
    var settled = function (rec, ringBlocks) {
      if (rec.any === null || ringBlocks <= rec.any.d) return false
      if (rec.land !== null) return ringBlocks > rec.land.d
      return res.cut
    }

    var maxR = Math.floor(cap / step)
    var stop = false
    for (var r = 0; r <= maxR && !stop; r++) {
      var ringBlocks = r * step
      if (settled(res.surface, ringBlocks) && settled(res.dig, ringBlocks)) break
      var n = r === 0 ? 1 : 8 * r
      for (var idx = 0; idx < n; idx++) {
        var i = 0
        var j = 0
        if (r > 0) {
          var side = Math.floor(idx / (2 * r))
          var t = idx % (2 * r)
          if (side === 0) { i = -r + t; j = -r } else if (side === 1) { i = r; j = -r + t } else if (side === 2) { i = r - t; j = r } else { i = -r; j = r - t }
        }
        var e = Math.sqrt(i * i + j * j) * step
        if (e > cap) continue
        var cx = x + i * step
        var cz = z + j * step
        res.columns++
        if ((res.columns & 2047) === 0 && Date.now() - t0 > job.placeSeconds * 1000) {
          res.timedOut = true
          stop = true
          break
        }
        if (isExt(cdg.generateSurfaceRock(cx, cz))) {
          consider(res.surface, e, cx, cz, 0)
          consider(res.dig, e, cx, cz, 0)
        } else if (res.dig.any === null || e < res.dig.any.d || res.dig.land === null || e < res.dig.land.d) {
          // not at the surface: is it under the next ~100 blocks? (surface 0, y = -depth so the 125 m height squash never applies)
          for (var k = 0; k < depths.length; k++) {
            if (isExt(cdg.generateRock(cx, -depths[k], cz, 0, null))) {
              consider(res.dig, e, cx, cz, depths[k])
              break
            }
          }
        }
      }
    }

    var layers = {}
    layers['0'] = rockName(cdg.generateRock(x, top, z, top, null))
    for (var m = 0; m < depths.length; m++) layers[String(depths[m])] = rockName(cdg.generateRock(x, top - depths[m], z, top, null))
    var rec = {
      x: x, z: z, top: top, dry: top > seaLevel, zone: zoneSafe(x, z), rock: layers['0'],
      deeper: layers, surface: res.surface, dig: res.dig, columns: res.columns, heightCalls: res.heightCalls,
      landCut: res.cut, timedOut: res.timedOut, ms: Date.now() - t0
    }
    for (var key in meta) rec[key] = meta[key]
    return rec
  }

  // Start the way /startat does: nearest dry ground within a few blocks of the projected point.
  function findStart(x, z) {
    if (topAt(x, z) > seaLevel) return { x: x, z: z, moved: 0 }
    var range = job.startSearch
    for (var r = 8; r <= range; r += 8) {
      for (var dx = -r; dx <= r; dx += 8) {
        for (var dz = -r; dz <= r; dz += 8) {
          if (Math.max(Math.abs(dx), Math.abs(dz)) !== r) continue
          if (topAt(x + dx, z + dz) > seaLevel) return { x: x + dx, z: z + dz, moved: Math.round(Math.sqrt(dx * dx + dz * dz)) }
        }
      }
    }
    return { x: x, z: z, moved: 0 }
  }

  var tAll = Date.now()
  var warm = true
  var named = job.named
  for (var ni = 0; ni < named.length; ni++) {
    var pl = named[ni]
    // [name, lat, lon, x, z]: x and z (blocks) win when given, otherwise project (longitude, latitude) -> [x, z]
    var xz = pl.length > 4 && pl[3] !== null ? [pl[3], pl[4]] : $RockSampleProjection.geographicToClassic(pl[2], pl[1])
    var start = findStart(Math.round(xz[0]), Math.round(xz[1]))
    if (warm) {
      warm = false
      var bad = selfTest(start.x, start.z)
      rocksampleOut('I', { identityVsNameMismatches: bad, extrusiveObjects: ext.length })
      if (bad > 0 && !nameMode) {
        nameMode = true
        isExt = isExtByName
      }
    }
    rocksampleOut('R', evaluate(start.x, start.z, { mode: 'named', name: pl[0], lat: pl[1], lon: pl[2], moved: start.moved }))
    console.info('[rocksample] progress named ' + (ni + 1) + '/' + named.length + ' ' + Math.round((Date.now() - tAll) / 1000) + ' s')
  }

  // Random land points: candidates were drawn uniformly over the (equal-area) map rectangle; keep those on
  // continent-map land that are also dry in the terrain, until job.random are found.
  if (job.random > 0) {
    var cont2 = new $RockSampleContinents(H, V)
    var cands = job.candidates
    var taken = 0
    var looked = 0
    for (var ci = 0; ci < cands.length && taken < job.random; ci++) {
      var cxx = cands[ci][0]
      var czz = cands[ci][1]
      looked++
      if (String(cont2.bandAtGridHard(cxx / 128, czz / 128)) !== 'LAND') continue
      if (!(topAt(cxx, czz) > seaLevel)) continue
      if (warm) {
        warm = false
        var bad2 = selfTest(cxx, czz)
        rocksampleOut('I', { identityVsNameMismatches: bad2, extrusiveObjects: ext.length })
        if (bad2 > 0 && !nameMode) {
          nameMode = true
          isExt = isExtByName
        }
      }
      taken++
      rocksampleOut('R', evaluate(cxx, czz, { mode: 'random', index: taken }))
      console.info('[rocksample] progress random ' + taken + '/' + job.random + ' (' + looked + ' candidates looked at) ' + Math.round((Date.now() - tAll) / 1000) + ' s')
    }
    if (taken < job.random) console.info('[rocksample] only ' + taken + ' of ' + job.random + ' random land points found in ' + cands.length + ' candidates')
  }
  console.info('[rocksample] searched in ' + Math.round((Date.now() - tAll) / 1000) + ' s')
}
