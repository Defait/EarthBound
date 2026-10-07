// Dev-only fingerprint of the overworld's generation, run by tools/worldgen_check.py (see its docstring).
// The Python tool rewrites the job line below and copies this file into the test server's
// local/kubejs/local_server_scripts for one run; it is never part of the pack.
// Everything is read from the running server without generating chunks: the effective registries (after
// biome modifiers and datapacks), the generator, and TFC's own height, biome, rock and climate maps at fixed
// points. Results go to local/worldgen-check/*.json on the test server; the Python side hashes and compares them.
// Note: function-local variables use var; Rhino rejects block-scoped const in callbacks that run repeatedly.
const $WorldgenCheckJsonOps = Java.loadClass('com.mojang.serialization.JsonOps')
const $WorldgenCheckRegistryOps = Java.loadClass('net.minecraft.resources.RegistryOps')
const $WorldgenCheckRegistries = Java.loadClass('net.minecraft.core.registries.Registries')
const $WorldgenCheckBuiltIn = Java.loadClass('net.minecraft.core.registries.BuiltInRegistries')
const $WorldgenCheckResourceKey = Java.loadClass('net.minecraft.resources.ResourceKey')
const $WorldgenCheckHooks = Java.loadClass('net.neoforged.neoforge.registries.DataPackRegistriesHooks')
const $WorldgenCheckChunkGenerator = Java.loadClass('net.minecraft.world.level.chunk.ChunkGenerator')
const $WorldgenCheckJsonObject = Java.loadClass('com.google.gson.JsonObject')
const $WorldgenCheckCarving = Java.loadClass('net.minecraft.world.level.levelgen.GenerationStep$Carving')
const $WorldgenCheckMobCategory = Java.loadClass('net.minecraft.world.entity.MobCategory')
const $WorldgenCheckHeightmap = Java.loadClass('net.minecraft.world.level.levelgen.Heightmap$Types')
const $WorldgenCheckChunkPos = Java.loadClass('net.minecraft.world.level.ChunkPos')

// Replaced by the Python tool. named: [[name, lat, lon]], offsets: [[dx, dz]] around each named place, anchors: [[x, z]]
// candidates for the random clusters (the first `land` on continent-map land and `sea` in open ocean are used, each with
// anchorOffsets around it), depths: rock lookups below the surface.
const WORLDGEN_JOB = /*JOB*/ {
  expectH: 862198, expectV: 419647, named: [], offsets: [], anchors: [], land: 0, sea: 0, anchorOffsets: [], depths: [25, 50, 100]
} /*END*/

const WORLDGEN_OUT = 'local/worldgen-check/'

function worldgenCheckClass(name) {
  try {
    return Java.loadClass(name)
  } catch (e) {
    return null
  }
}

ServerEvents.loaded(event => {
  console.info('[worldgen-check] start')
  try {
    worldgenCheckRun(event.server, WORLDGEN_JOB)
  } catch (e) {
    console.info('[worldgen-check] FATAL ' + e + (e && e.stack ? ' ' + String(e.stack).replace(/\s+/g, ' ') : ''))
  }
  // tools/worldgen_check.py waits for this line.
  console.info('[worldgen-check] done')
})

function worldgenCheckRun(server, job) {
  var level = server.overworld()
  var generator = level.getChunkSource().getGenerator() // net.dries007.tfc.world.TFCChunkGenerator
  var randomState = level.getChunkSource().randomState()
  var Config = worldgenCheckClass('net.yazloysasha.tfcrealworld.config.TFCRealWorldConfig')
  var H = Config ? Number(String(Config.HORIZONTAL_SCALE.get())) : null
  var V = Config ? Number(String(Config.VERTICAL_SCALE.get())) : null
  console.info('[worldgen-check] map radius ' + H + ' x ' + V + ', generator ' + String(generator).split('@')[0])
  if (H !== job.expectH || V !== job.expectV) {
    console.info('[worldgen-check] FATAL map radius is ' + H + ' x ' + V + ', expected ' + job.expectH + ' x ' + job.expectV +
      ' (20 m per block); is world_scale.js in the pack and the world fresh?')
    return
  }
  var t0 = Date.now()
  worldgenCheckTier1(server, level, generator, H, V)
  console.info('[worldgen-check] registries, biomes and modifiers in ' + (Date.now() - t0) + ' ms')
  t0 = Date.now()
  worldgenCheckTier2(server, level, generator, randomState, job)
  console.info('[worldgen-check] sampled points in ' + Math.round((Date.now() - t0) / 100) / 10 + ' s')
}

// ------------------------------------------------------------------ tier 1: effective registries
function worldgenCheckTier1(server, level, generator, H, V) {
  var access = server.registryAccess()
  var ops = $WorldgenCheckRegistryOps.create($WorldgenCheckJsonOps.INSTANCE, access)
  var info = { scale: [H, V], seaLevel: Number(generator.getSeaLevel()), minY: Number(generator.getMinY()), genDepth: Number(generator.getGenDepth()) }

  function encoded(codec, value) {
    var r = codec.encodeStart(ops, value)
    if (!r.result().isPresent()) throw new Error('cannot encode: ' + r.error().get().message())
    return r.result().get()
  }
  function toPlain(json) {
    return JSON.parse(String(json))
  }
  function idOf(holder) {
    return String(holder.unwrapKey().get().location())
  }

  // The generator and dimension type exactly as the world's level.dat would store them (TFC's rock layers included).
  info.generatorClass = String(generator).split('@')[0]
  info.biomeSourceClass = String(generator.getBiomeSource()).split('@')[0]
  info.generator = toPlain(encoded($WorldgenCheckChunkGenerator.CODEC, generator))
  info.dimensionType = toPlain(encoded(Java.loadClass('net.minecraft.world.level.dimension.DimensionType').DIRECT_CODEC, level.dimensionType()))
  info.dimensionTypeHeight = Number(level.dimensionType().height())
  info.dimensionTypeMinY = Number(level.dimensionType().minY())

  var possible = {}
  var possibleList = []
  generator.getBiomeSource().possibleBiomes().forEach(function (h) {
    var id = idOf(h)
    possible[id] = h
    possibleList.push(id)
  })
  possibleList.sort()
  info.possibleBiomes = possibleList

  // Biomes after biome modifiers: ordered feature ids per decoration slot, carvers, mob spawns.
  var biomes = {}
  var carvings = $WorldgenCheckCarving.values()
  var categories = $WorldgenCheckMobCategory.values()
  possibleList.forEach(function (id) {
    var biome = possible[id].value()
    var settings = biome.getGenerationSettings()
    var slots = []
    var lists = settings.features()
    for (var i = 0; i < lists.size(); i++) {
      var ids = []
      lists.get(i).forEach(function (f) { ids.push(idOf(f)) })
      slots.push(ids)
    }
    var carvers = {}
    for (var c = 0; c < carvings.length; c++) {
      var cids = []
      settings.getCarvers(carvings[c]).forEach(function (h) { cids.push(idOf(h)) })
      if (cids.length) carvers[String(carvings[c])] = cids
    }
    var spawns = {}
    var mobs = biome.getMobSettings()
    for (var m = 0; m < categories.length; m++) {
      var list = mobs.getMobs(categories[m]).unwrap()
      var entries = []
      for (var q = 0; q < list.size(); q++) {
        var d = list.get(q)
        entries.push(String(d.type.builtInRegistryHolder().key().location()) + '*' + d.minCount + '-' + d.maxCount + ':' + d.getWeight().asInt())
      }
      if (entries.length) spawns[String(categories[m])] = entries
    }
    biomes[id] = { features: slots, carvers: carvers, spawns: spawns }
  })
  JsonIO.write(WORLDGEN_OUT + 'biomes.json', biomes)

  // Biome tags that hold a possible (TFC) biome: any modifier or structure aimed at them lands in TFC.
  var biomeReg = access.registryOrThrow($WorldgenCheckRegistries.BIOME)
  var tagMembers = {}
  var tagsWithTfc = {}
  biomeReg.getTags().forEach(function (pair) {
    var tag = String(pair.getFirst().location())
    var members = []
    var hit = []
    pair.getSecond().forEach(function (h) {
      var id = idOf(h)
      members.push(id)
      if (possible[id]) hit.push(id)
    })
    tagMembers[tag] = members
    if (hit.length) tagsWithTfc[tag] = { total: members.length, tfc: hit.sort() }
  })
  info.biomeTags = tagsWithTfc

  // A biome list as modifiers write it: "#tag", "id", or a list of ids. Returns the possible biomes it selects.
  function selectedBiomes(spec) {
    var out = {}
    function add(id) {
      if (String(id).charAt(0) === '#') {
        var members = tagMembers[String(id).substring(1)] || []
        members.forEach(function (m) { if (possible[m]) out[m] = true })
      } else if (possible[String(id)]) {
        out[String(id)] = true
      }
    }
    if (spec === undefined || spec === null) return null
    if (typeof spec === 'string') add(spec)
    else spec.forEach(add)
    return Object.keys(out).sort()
  }

  // Structures whose biome list includes a possible biome (vanilla ones never do; a modded one targeting a c: tag would).
  var structureReg = access.registryOrThrow($WorldgenCheckRegistries.STRUCTURE)
  var structures = { total: 0, hits: {} }
  var structureHits = {}
  structureReg.entrySet().forEach(function (e) {
    structures.total++
    var hit = []
    e.getValue().biomes().forEach(function (h) { if (possible[idOf(h)]) hit.push(idOf(h)) })
    if (hit.length) {
      structures.hits[String(e.getKey().location())] = hit.sort()
      structureHits[String(e.getKey().location())] = true
    }
  })
  info.structures = structures

  // Every datapack registry that can touch generation, content-encoded for hashing on the Python side.
  var wanted = function (key) {
    var ns = String(key.location().getNamespace())
    var path = String(key.location().getPath())
    return path.indexOf('worldgen/') === 0 || path === 'dimension' || path === 'dimension_type' || ns === 'neoforge' || ns === 'gtceu'
  }
  var regs = $WorldgenCheckHooks.getDataPackRegistriesWithDimensions().toList()
  var registryInfo = {}
  var modifiers = {}
  for (var i = 0; i < regs.size(); i++) {
    var rd = regs.get(i)
    var key = rd.key()
    if (!wanted(key)) continue
    var reg = access.registry(key)
    if (!reg.isPresent()) continue
    var name = String(key.location())
    var dump = new $WorldgenCheckJsonObject()
    var failed = []
    var codec = rd.elementCodec()
    reg.get().entrySet().forEach(function (e) {
      var id = String(e.getKey().location())
      try {
        dump.add(id, encoded(codec, e.getValue()))
      } catch (ex) {
        failed.push(id)
      }
    })
    JsonIO.write(WORLDGEN_OUT + 'registry-' + name.replace(/[:\/]/g, '_') + '.json', dump)
    registryInfo[name] = { n: Number(reg.get().size()), failed: failed }
    if (name === 'neoforge:biome_modifier' || name === 'neoforge:structure_modifier') {
      var kind = name === 'neoforge:biome_modifier' ? 'biomes' : 'structures'
      reg.get().entrySet().forEach(function (e) {
        var json = toPlain(encoded(codec, e.getValue()))
        var mod = { json: json, kind: kind, hits: [] }
        if (kind === 'biomes') {
          mod.hits = selectedBiomes(json.biomes) || []
        } else if (json.structures !== undefined) {
          // structure modifiers name structures, not biomes: count the targeted structures that can start in a possible biome
          var specs = typeof json.structures === 'string' ? [json.structures] : json.structures
          specs.forEach(function (s) {
            if (String(s).charAt(0) !== '#' && structureHits[String(s)]) mod.hits.push(String(s))
          })
        }
        modifiers[String(e.getKey().location())] = mod
      })
    }
  }
  info.registries = registryInfo
  info.modifiers = modifiers

  // GregTech ore veins that can still generate; the pack switches them all off (docs/design.md, "GregTech ores").
  var veinReg = access.registry($WorldgenCheckResourceKey.createRegistryKey('gtceu:ore_vein'))
  if (veinReg.isPresent()) {
    var generating = []
    veinReg.get().entrySet().forEach(function (e) {
      if (e.getValue().canGenerate()) generating.push(String(e.getKey().location()))
    })
    info.oreVeins = { registered: Number(veinReg.get().size()), generating: generating.sort() }
  }

  // Runtime values of the configs that gate worldgen the generic file reader can't see (everything else is read from the config files).
  var config = {}
  try {
    var gt = worldgenCheckClass('com.gregtechceu.gtceu.config.ConfigHolder').INSTANCE.worldgen
    config.gtRubberTreeSpawnChance = Number(gt.rubberTreeSpawnChance)
    config.gtRemoveVanillaOreGen = String(gt.oreVeins.removeVanillaOreGen) === 'true'
  } catch (e) {
    config.gtError = String(e)
  }
  try {
    config.createDisableWorldGen = String(worldgenCheckClass('com.simibubi.create.infrastructure.config.AllConfigs').common().worldGen.disable.get()) === 'true'
  } catch (e) {
    config.createError = String(e)
  }
  info.config = config

  JsonIO.write(WORLDGEN_OUT + 'info.json', info)
}

// ------------------------------------------------------------------ tier 2: sampled points
function worldgenCheckTier2(server, level, generator, randomState, job) {
  var cdg = generator.chunkDataGenerator() // RegionChunkDataGenerator
  var biomeSource = generator.getBiomeSource()
  var sampler = randomState.sampler()
  var Projection = worldgenCheckClass('net.yazloysasha.tfcrealworld.util.projection.ProjectionManager')
  var Continents = worldgenCheckClass('net.yazloysasha.tfcrealworld.world.noise.png.PNGContinentNoise')
  var depths = job.depths

  function rockName(rs) {
    return String($WorldgenCheckBuiltIn.BLOCK.getKey(rs.raw())).replace('tfc:rock/raw/', '')
  }
  function round(v, digits) {
    var f = Math.pow(10, digits)
    return Math.round(Number(v) * f) / f
  }
  // [x, z, height, biome, surface rock, rock at each depth..., rainfall, rain variance, sea-level temperature, groundwater, forest type]
  function sample(x, z) {
    var top = Number(generator.getBaseHeight(x, z, $WorldgenCheckHeightmap.WORLD_SURFACE_WG, level, randomState))
    var biome = String(biomeSource.getNoiseBiome(x >> 2, top >> 2, z >> 2, sampler).unwrapKey().get().location())
    var out = [x, z, top, biome, rockName(cdg.generateSurfaceRock(x, z))]
    for (var d = 0; d < depths.length; d++) out.push(rockName(cdg.generateRock(x, top - depths[d], z, top, null)))
    var data = cdg.createAndGenerate(new $WorldgenCheckChunkPos(x >> 4, z >> 4))
    out.push(round(data.getAverageRainfall(x, z), 2), round(data.getRainVariance(x, z), 3), round(data.getAverageSeaLevelTemp(x, z), 2),
      round(data.getBaseGroundwater(x, z), 3), String(data.getForestType()))
    return out
  }

  var clusters = []
  function cluster(name, kind, cx, cz, offsets) {
    var pts = [sample(cx, cz)]
    for (var i = 0; i < offsets.length; i++) pts.push(sample(cx + offsets[i][0], cz + offsets[i][1]))
    clusters.push({ name: name, kind: kind, x: cx, z: cz, points: pts })
  }

  // The named places: rocksample.py's cities, projected like world generation does.
  for (var n = 0; n < job.named.length; n++) {
    var p = job.named[n]
    var xz = Projection.geographicToClassic(p[2], p[1])
    cluster(p[0], 'place', Math.round(xz[0]), Math.round(xz[1]), job.offsets)
  }
  // Random clusters over the whole map: the first candidates on land and in open ocean (the continent map says so for the
  // whole 3x3 grid cells around), so both are covered whatever share of the rectangle each takes.
  var land = 0
  var sea = 0
  var continents = Continents ? new Continents(job.expectH, job.expectV) : null
  for (var a = 0; a < job.anchors.length && (land < job.land || sea < job.sea); a++) {
    var ax = job.anchors[a][0]
    var az = job.anchors[a][1]
    var band = continents ? String(continents.bandAtGridHard(ax / 128, az / 128)) : 'LAND'
    if (band === 'LAND' && land < job.land) {
      land++
      cluster('land-' + land, 'land', ax, az, job.anchorOffsets)
    } else if (band === 'OCEAN' && sea < job.sea) {
      sea++
      cluster('sea-' + sea, 'sea', ax, az, job.anchorOffsets)
    }
  }
  JsonIO.write(WORLDGEN_OUT + 'points.json', { clusters: clusters })
  console.info('[worldgen-check] ' + clusters.length + ' clusters, ' + clusters.reduce(function (s, c) { return s + c.points.length }, 0) + ' points')
}
