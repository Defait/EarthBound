// Dev-only check of the pack's structures (docs/lived-in.md), run by tools/structures_test.py.
// Copied into the test server's local/kubejs/local_server_scripts for one run; never part of the pack.
// Note: function-local variables use var; Rhino rejects block-scoped const in callbacks that run repeatedly.
const $StructTestApi = Java.loadClass('pack.world.api.PackWorldApi')
const $StructTestProjection = Java.loadClass('net.yazloysasha.tfcrealworld.util.projection.ProjectionManager')
const $StructTestWaypoints = Java.loadClass('net.yazloysasha.tfcrealworld.util.geography.WaypointCoordinates')
const $StructTestRL = Java.loadClass('net.minecraft.resources.ResourceLocation')
const $StructTestRK = Java.loadClass('net.minecraft.resources.ResourceKey')
const $StructTestRegistries = Java.loadClass('net.minecraft.core.registries.Registries')
const $StructTestBuiltIn = Java.loadClass('net.minecraft.core.registries.BuiltInRegistries')
const $StructTestTagKey = Java.loadClass('net.minecraft.tags.TagKey')
const $StructTestBlockPos = Java.loadClass('net.minecraft.core.BlockPos')
const $StructTestHeightmap = Java.loadClass('net.minecraft.world.level.levelgen.Heightmap$Types')
const $StructTestQuart = Java.loadClass('net.minecraft.core.QuartPos')
const $StructTestLootParams = Java.loadClass('net.minecraft.world.level.storage.loot.LootParams$Builder')
const $StructTestLootParamSets = Java.loadClass('net.minecraft.world.level.storage.loot.parameters.LootContextParamSets')
const $StructTestLootContextParams = Java.loadClass('net.minecraft.world.level.storage.loot.parameters.LootContextParams')
const $StructTestVec3 = Java.loadClass('net.minecraft.world.phys.Vec3')
const $StructTestRandomSpread = Java.loadClass('net.minecraft.world.level.levelgen.structure.placement.RandomSpreadStructurePlacement')
const $StructTestChunkPos = Java.loadClass('net.minecraft.world.level.ChunkPos')
const $StructTestBox = Java.loadClass('net.minecraft.world.level.levelgen.structure.BoundingBox')
const $StructTestTemplate = Java.loadClass('net.minecraft.world.level.levelgen.structure.templatesystem.StructureTemplate')
const $StructTestPlaceSettings = Java.loadClass('net.minecraft.world.level.levelgen.structure.templatesystem.StructurePlaceSettings')
const $StructTestAABB = Java.loadClass('net.minecraft.world.phys.AABB')
const $StructTestCompound = Java.loadClass('net.minecraft.nbt.CompoundTag')
const $StructTestEntity = Java.loadClass('net.minecraft.world.entity.Entity')

// Replaced by the Python tool.
const STRUCT_TEST_JOB = /*JOB*/ {
  structures: [], places: [], placeholders: { rock: [], wood: [], soil: [], sand: [] }, deny: [], lootTables: [], densityRadius: 8000, naturalPerStructure: 3, templates: {}
} /*END*/

const STRUCT_TEST_OUT = 'local/structures-test/'
const STRUCT_TEST_ROCKS = ['granite', 'diorite', 'gabbro', 'shale', 'claystone', 'limestone', 'conglomerate', 'dolomite', 'chert', 'chalk',
  'tuff', 'rhyolite', 'basalt', 'andesite', 'dacite', 'quartzite', 'slate', 'phyllite', 'schist', 'gneiss', 'marble']
const STRUCT_TEST_ALLOY = { andesite: 1, basalt: 1, dacite: 1, rhyolite: 1, diorite: 1 }
const STRUCT_TEST_WOODS = ['acacia', 'ash', 'aspen', 'birch', 'blackwood', 'chestnut', 'douglas_fir', 'hickory', 'kapok', 'mangrove', 'maple',
  'oak', 'palm', 'pine', 'rosewood', 'sequoia', 'spruce', 'sycamore', 'white_cedar', 'willow']
const STRUCT_TEST_SOILS = ['entisol', 'aridisol', 'oxisol', 'fluvisol', 'andisol', 'podzol', 'alfisol', 'mollisol']
const STRUCT_TEST_SANDS = ['brown', 'white', 'black', 'red', 'yellow', 'green', 'pink']
const STRUCT_TEST_ROUGH = /^tfc:rock\/(raw|hardened|cobble|mossy_cobble|loose|mossy_loose)\/(andesite|basalt|dacite|rhyolite|diorite)(_stairs|_slab|_wall)?$/
// Variants that never occur naturally: if one of these is still the placeholder after processing, it leaked.
const STRUCT_TEST_ROCK_LEAK = /^tfc:rock\/(smooth|cobble|bricks|cracked_bricks|mossy_bricks|mossy_cobble|chiseled)\/granite(_stairs|_slab|_wall)?$|^tfc:rock\/raw\/granite_(stairs|slab|wall)$/
const STRUCT_TEST_WOOD_LEAK = /^tfc:wood\/(planks|chest|trapped_chest|fence|fence_gate|log_fence|vertical_support|horizontal_support|door|trapdoor|stripped_log)\/oak(_stairs|_slab)?$/
// Natural blocks a structure's box can contain besides its own (ground, fluids, plants).
const STRUCT_TEST_VANILLA_OK = { 'minecraft:air': 1, 'minecraft:cave_air': 1, 'minecraft:water': 1, 'minecraft:lava': 1, 'minecraft:bedrock': 1,
  'minecraft:ice': 1, 'minecraft:packed_ice': 1, 'minecraft:blue_ice': 1, 'minecraft:snow_block': 1, 'minecraft:cobweb': 1, 'minecraft:hanging_roots': 1, 'minecraft:bamboo': 1, 'minecraft:bamboo_sapling': 1 }

ServerEvents.loaded(event => {
  var server = event.server
  var level = server.overworld()
  var results = { checks: [], placements: [], loot: {}, sites: {}, density: {} }
  var failures = 0
  function check(name, ok, detail) {
    if (!ok) failures++
    results.checks.push({ name: name, ok: !!ok, detail: String(detail) })
    console.info(`[structures-test] ${ok ? 'PASS' : 'FAIL'} ${name}: ${detail}`)
  }
  function blockExists(id) {
    return id === 'minecraft:air' || $StructTestBuiltIn.BLOCK.containsKey($StructTestRL.parse(id))
  }
  function idAt(x, y, z) {
    return String($StructTestBuiltIn.BLOCK.getKey(level.getBlockState(new $StructTestBlockPos(x, y, z)).getBlock()))
  }
  try {
    if (!STRUCT_TEST_JOB.villagesOnly) {
      structTestPalette(STRUCT_TEST_JOB, check, blockExists)
      // natural starts first: the /place copies would overwrite natural ones that happen to lie in the same spots
      structTestNatural(level, STRUCT_TEST_JOB, results, check, idAt)
      if (!STRUCT_TEST_JOB.naturalOnly) structTestPlacements(server, level, STRUCT_TEST_JOB, results, check, idAt)
      structTestNpcs(server, level, STRUCT_TEST_JOB, results, check)
      structTestLoot(server, level, STRUCT_TEST_JOB, results, check)
      structTestSites(level, results, check)
      structTestDensity(level, STRUCT_TEST_JOB, results)
    }
  } catch (e) {
    check('script', false, String(e) + (e && e.stack ? ' ' + String(e.stack).replace(/\s+/g, ' ') : ''))
  }
  try {
    if (STRUCT_TEST_JOB.villageJob) structTestVillages(server, level, STRUCT_TEST_JOB, results, check, idAt)
  } catch (e) {
    check('villages script', false, String(e) + (e && e.stack ? ' ' + String(e.stack).replace(/\s+/g, ' ') : ''))
  }
  JsonIO.write(STRUCT_TEST_OUT + 'results.json', results)
  console.info(`[structures-test] done: ${failures} failed`)
})

// Every placeholder id of every template, through the processor's own mapping, for every rock, wood, soil and sand.
// the boxes of the ruins this script placed by hand next to the places (/place style, nothing keeps them off a natural village that happens to stand there): their blocks are not the village's
var STRUCT_TEST_COPIES = []
function structTestInCopy(x, z) {
  for (var i = 0; i < STRUCT_TEST_COPIES.length; i++) {
    var b = STRUCT_TEST_COPIES[i]
    if (x >= b[0] && x <= b[2] && z >= b[1] && z <= b[3]) return true
  }
  return false
}

function structTestPalette(job, check, blockExists) {
  var bad = []
  var n = 0
  ;['work', 'substitute', 'allow'].forEach(function (policy) {
    STRUCT_TEST_ROCKS.forEach(function (rock) {
      job.placeholders.rock.forEach(function (id) {
        var out = String($StructTestApi.mapId(id, rock, 'oak', 'alfisol', 'yellow', policy))
        n++
        if (!blockExists(out)) bad.push(`${id} -> ${out} (${rock}, ${policy}): no such block`)
        // An alloy rock's rough variants become the substitute (granite) under "substitute", and its anvil under "work".
        else if (rock !== 'granite' && out === id && !(STRUCT_TEST_ALLOY[rock] && (policy === 'substitute' || id.indexOf('/anvil/') > 0))) bad.push(`${id} unchanged for ${rock} (${policy})`)
        else if (policy !== 'allow' && STRUCT_TEST_ROUGH.test(out)) bad.push(`${id} -> ${out}: andesite alloy rock (${policy})`)
      })
    })
  })
  STRUCT_TEST_WOODS.forEach(function (wood) {
    job.placeholders.wood.forEach(function (id) {
      var out = String($StructTestApi.mapId(id, 'gabbro', wood, 'alfisol', 'yellow', 'work'))
      n++
      if (!blockExists(out) || (wood !== 'oak' && out === id)) bad.push(`${id} -> ${out} (${wood})`)
    })
  })
  STRUCT_TEST_SOILS.forEach(function (soil) {
    job.placeholders.soil.forEach(function (id) {
      var out = String($StructTestApi.mapId(id, 'gabbro', 'oak', soil, 'yellow', 'work'))
      n++
      if (!blockExists(out) || (soil !== 'alfisol' && out === id)) bad.push(`${id} -> ${out} (${soil})`)
    })
  })
  STRUCT_TEST_SANDS.forEach(function (sand) {
    job.placeholders.sand.forEach(function (id) {
      var out = String($StructTestApi.mapId(id, 'gabbro', 'oak', 'alfisol', sand, 'work'))
      n++
      if (!blockExists(out) || (sand !== 'yellow' && out === id)) bad.push(`${id} -> ${out} (${sand})`)
    })
  })
  check('palette maps every placeholder', bad.length === 0, `${n} mappings` + (bad.length ? `; ${bad.length} bad: ${bad.slice(0, 12).join('; ')}` : ''))
}

// Each structure generated the way /place does (generate a start at a chunk, place its pieces into the existing terrain) at
// real places with different rock and climate, and its box read back. Without terrain adaptation: the beard only applies to
// chunks generated with the structure, which the natural check below covers.
function structTestPlacements(server, level, job, results, check, idAt) {
  var structReg = level.registryAccess().registryOrThrow($StructTestRegistries.STRUCTURE)
  var generator = level.getChunkSource().getGenerator()
  job.places.forEach(function (place) {
    var found = startAtFind(level, place[1], place[2])
    if (!found.spot) {
      check(`dry ground at ${place[0]}`, false, `point ${found.point.x},${found.point.z}`)
      return
    }
    job.structures.forEach(function (s, i) {
      var x = found.spot.x + (i % 3) * 96
      var z = found.spot.z + Math.floor(i / 3) * 96
      var structure = structTestStructure(structReg, s.id)
      var start = structure.generate(level.registryAccess(), generator, generator.getBiomeSource(), level.getChunkSource().randomState(),
        level.getStructureManager(), level.getSeed(), new $StructTestChunkPos(x >> 4, z >> 4), 0, level, function (h) { return true })
      var rec = { kind: 'placed', place: place[0], structure: s.id, at: [x, z], placed: start.isValid() }
      if (rec.placed) {
        var box = start.getBoundingBox()
        STRUCT_TEST_COPIES.push([box.minX(), box.minZ(), box.maxX(), box.maxZ()])
        for (var cx = box.minX() >> 4; cx <= box.maxX() >> 4; cx++) {
          for (var cz = box.minZ() >> 4; cz <= box.maxZ() >> 4; cz++) {
            level.getChunk(cx, cz)
            start.placeInChunk(level, level.structureManager(), generator, level.getRandom(),
              new $StructTestBox(cx << 4, level.getMinBuildHeight(), cz << 4, (cx << 4) + 15, level.getMaxBuildHeight(), (cz << 4) + 15), new $StructTestChunkPos(cx, cz))
          }
        }
        structTestInspect(level, start, s, rec, idAt)
      }
      results.placements.push(rec)
      check(`${s.id} placed at ${place[0]} (${rec.expected ? rec.expected.rock + ', ' + rec.expected.wood : '?'})`, structTestOk(rec), structTestDetail(rec))
    })
  })
}

// Natural generation: the nearest real starts of each structure to the places (from its placement's own grid, climate and
// biome checks), their chunks generated normally, so terrain adaptation, decoration and the processors all run as in play.
function structTestNatural(level, job, results, check, idAt) {
  var structReg = level.registryAccess().registryOrThrow($StructTestRegistries.STRUCTURE)
  var setReg = level.registryAccess().registryOrThrow($StructTestRegistries.STRUCTURE_SET)
  var state = level.getChunkSource().getGeneratorState()
  var seed = level.getSeed()
  job.structures.forEach(function (s) {
    var set = structTestStructure(setReg, s.id)
    var structure = structTestStructure(structReg, s.id)
    var placement = set.placement()
    var spacing = placement.spacing()
    var found = 0
    var tried = 0
    for (var p = 0; p < job.places.length && found < job.naturalPerStructure; p++) {
      var xz = $StructTestProjection.geographicToClassic(job.places[p][2], job.places[p][1])
      var cx0 = Math.floor(xz[0] / 16)
      var cz0 = Math.floor(xz[1] / 16)
      var candidates = []
      for (var r = 0; r <= 6 && candidates.length < 2; r++) {
        for (var a = -r; a <= r; a++) {
          for (var b = -r; b <= r; b++) {
            if (Math.max(Math.abs(a), Math.abs(b)) !== r) continue
            var c = placement.getPotentialStructureChunk(seed, cx0 + a * spacing, cz0 + b * spacing)
            if (placement.isStructureChunk(state, c.x, c.z)) candidates.push(c)
          }
        }
      }
      for (var k = 0; k < candidates.length && found < job.naturalPerStructure; k++) {
        var c = candidates[k]
        tried++
        var start = level.getChunk(c.x, c.z).getStartForStructure(structure)
        if (start === null || !start.isValid()) continue
        var box = start.getBoundingBox()
        for (var gx = (box.minX() >> 4) - 1; gx <= (box.maxX() >> 4) + 1; gx++) {
          for (var gz = (box.minZ() >> 4) - 1; gz <= (box.maxZ() >> 4) + 1; gz++) level.getChunk(gx, gz)
        }
        var rec = { kind: 'natural', place: job.places[p][0], structure: s.id, at: [box.getCenter().getX(), box.getCenter().getZ()], placed: true }
        structTestInspect(level, start, s, rec, idAt)
        results.placements.push(rec)
        check(`${s.id} natural near ${job.places[p][0]} at ${rec.at} (${rec.expected.rock}, ${rec.expected.wood})`, structTestOk(rec), structTestDetail(rec))
        found++
      }
    }
    if (!found) console.info(`[structures-test] NOTE ${s.id}: no natural start near the places (${tried} climate-valid grid chunks had none: biome)`)
  })
}

function structTestStructure(reg, id) {
  var out = null
  reg.entrySet().forEach(function (e) { if (String(e.getKey().location()) === 'pack:' + id) out = e.getValue() })
  return out
}

// What a placed structure holds, checked at exactly the spots its templates place blocks (the structure's box also holds
// natural terrain: TFC's boulders are local cobble, caves grow vines): placeholder leaks, vanilla blocks, rough alloy rock,
// rock and wood other than the local ones, missing blocks (decay, rot), floating ground-layer blocks, chests.
function structTestInspect(level, start, s, rec, idAt) {
  var pieces = start.getPieces()
  var anchor = $StructTestApi.anchorOf(start)       // the centre of the start piece at its lowest y: where local_materials resolves for every piece
  var mat = $StructTestApi.materialsAt(level, anchor[0], anchor[1], anchor[2])
  rec.expected = { rock: String(mat.get('rock')), wood: String(mat.get('wood')), sand: String(mat.get('sand')) }
  rec.leaks = []
  rec.vanilla = []
  rec.alloy = []
  rec.otherRock = []
  rec.otherWood = []
  rec.chests = 0
  rec.columns = 0
  rec.floatColumns = 0
  rec.maxGap = 0
  rec.templateBlocks = 0
  rec.missing = 0
  rec.templates = []
  rec.details = []
  rec.overwritten = []
  var counts = {}
  function add(list, v) { if (list.indexOf(v) < 0) list.push(v) }
  pieces.forEach(function (piece) {
    var m = /(pack[a-z_]*:[a-z0-9_\/]+)/.exec(String(piece.getElement()))
    var tid = m ? m[1] : null
    var blocks = tid ? STRUCT_TEST_JOB.templates[tid] : null
    rec.templates.push(tid)
    if (!blocks) return
    var settings = new $StructTestPlaceSettings().setRotation(piece.getRotation())
    var origin = piece.getPosition()
    blocks.forEach(function (b) {
      var rel = $StructTestTemplate.calculateRelativePosition(settings, new $StructTestBlockPos(b[0], b[1], b[2]))
      var pos = rel.offset(origin)
      var id = String($StructTestBuiltIn.BLOCK.getKey(level.getBlockState(pos).getBlock()))
      rec.templateBlocks++
      counts[id] = (counts[id] || 0) + 1
      if (id === 'minecraft:air' || id === 'minecraft:cave_air') rec.missing++
      if ((id === 'minecraft:air' || STRUCT_TEST_ROUGH.test(id) || /hardened/.test(id)) && rec.details.length < 24)
        rec.details.push(`${b[3]} @${b[0]},${b[1]},${b[2]} -> ${id} at ${pos.getX()},${pos.getY()},${pos.getZ()}`)
      if (rec.expected.rock !== 'granite' && STRUCT_TEST_ROCK_LEAK.test(id)) add(rec.leaks, id)
      if (rec.expected.wood !== 'oak' && STRUCT_TEST_WOOD_LEAK.test(id)) add(rec.leaks, id)
      if (id.indexOf('minecraft:') === 0 && !STRUCT_TEST_VANILLA_OK[id]) add(rec.vanilla, id)
      // Natural generation runs TFC's later decoration (boulders, forests, cave decoration) after the structure step, and it can
      // overwrite a structure's blocks with natural local rock: that is noted, not failed. A /place copy has no later decoration.
      if (STRUCT_TEST_ROUGH.test(id) && /^tfc:rock\//.test(b[3])) add(rec.kind === 'natural' ? rec.overwritten : rec.alloy, id)
      var r = /^tfc:rock\/(smooth|cobble|bricks|cracked_bricks|mossy_bricks|mossy_cobble|chiseled|raw|loose|mossy_loose|anvil)\/([a-z]+)/.exec(id)
      if (r && r[2] !== rec.expected.rock && !(r[1] === 'anvil' && STRUCT_TEST_ALLOY[rec.expected.rock])) add(rec.otherRock, r[2])
      var w = /^tfc:wood\/(planks|chest|fence|fence_gate|log_fence|log|vertical_support|horizontal_support|door|stripped_log)\/([a-z_]+?)(_stairs|_slab)?$/.exec(id)
      if (w && w[2] !== rec.expected.wood) add(rec.otherWood, w[2])
      if (/^tfc:wood\/chest\//.test(id)) rec.chests++
      if (b[1] === s.ground && !b[4] && id !== 'minecraft:air') {
        rec.columns++
        var gap = 0
        for (var dy = pos.getY() - 1; dy > pos.getY() - 24; dy--) {
          var below = level.getBlockState(new $StructTestBlockPos(pos.getX(), dy, pos.getZ()))
          if (!(below.isAir() || below.canBeReplaced()) || !below.getFluidState().isEmpty()) break
          gap++
        }
        if (gap >= 2) {
          rec.floatColumns++
          if (rec.details.length < 24) rec.details.push(`${b[3]} @${b[0]},${b[1]},${b[2]} floats ${gap} at ${pos.getX()},${pos.getY()},${pos.getZ()}`)
        }
        if (gap > rec.maxGap) rec.maxGap = gap
      }
    })
  })
  rec.blocks = counts
}

function structTestOk(rec) {
  return rec.placed && !rec.leaks.length && !rec.vanilla.length && !rec.alloy.length
}

function structTestDetail(rec) {
  if (!rec.placed) return 'did not place'
  return `${rec.templateBlocks} template blocks (${rec.missing} gone), leaks [${rec.leaks}], vanilla [${rec.vanilla}], alloy [${rec.alloy}], ` +
    (rec.overwritten.length ? `overwritten by natural decoration [${rec.overwritten}], ` : '') +
    `other rocks [${rec.otherRock}], other woods [${rec.otherWood}], chests ${rec.chests}, floating ground blocks ${rec.floatColumns}/${rec.columns} (max gap ${rec.maxGap})`
}

// The NPC fixture (pack_test:npc, made by tools/structures_test.py from the catalogue's presets) placed twice: each copy's trader
// is its own entity with its trades, no owner and a home where it stands; each copy's smith spawner has its own NPC UUID.
function structTestNpcs(server, level, job, results, check) {
  var structure = null
  level.registryAccess().registryOrThrow($StructTestRegistries.STRUCTURE).entrySet().forEach(function (e) {
    if (String(e.getKey().location()) === 'pack_test:npc') structure = e.getValue()
  })
  if (!structure) {
    check('NPC fixture', false, 'pack_test:npc is not registered')
    return
  }
  var generator = level.getChunkSource().getGenerator()
  var found = startAtFind(level, 38.5, -98.0)
  var copies = []
  ;[0, 64].forEach(function (dx) {
    var x = found.spot.x + dx
    var z = found.spot.z + 300
    var start = structure.generate(level.registryAccess(), generator, generator.getBiomeSource(), level.getChunkSource().randomState(),
      level.getStructureManager(), level.getSeed(), new $StructTestChunkPos(x >> 4, z >> 4), 0, level, function (h) { return true })
    if (!start.isValid()) return
    var box = start.getBoundingBox()
    for (var cx = box.minX() >> 4; cx <= box.maxX() >> 4; cx++) {
      for (var cz = box.minZ() >> 4; cz <= box.maxZ() >> 4; cz++) {
        level.getChunk(cx, cz)
        start.placeInChunk(level, level.structureManager(), generator, level.getRandom(),
          new $StructTestBox(cx << 4, level.getMinBuildHeight(), cz << 4, (cx << 4) + 15, level.getMaxBuildHeight(), (cz << 4) + 15), new $StructTestChunkPos(cx, cz))
      }
    }
    var copy = { box: [box.minX(), box.minY(), box.minZ(), box.maxX(), box.maxY(), box.maxZ()], npcs: [], spawners: [] }
    var aabb = new $StructTestAABB(box.minX() - 2, box.minY() - 2, box.minZ() - 2, box.maxX() + 3, box.maxY() + 3, box.maxZ() + 3)
    var near = level.getEntitiesOfClass($StructTestEntity, aabb.inflate(16))
    near.forEach(function (en) {
      // Easy NPC's entities aren't found by the entity-type registry from here (it answers its default, minecraft:pig), so
      // they are recognised by their saved data
      var tag = en.saveWithoutId(new $StructTestCompound())
      if (!tag.contains('EasyNPCVersion')) return
      var id = String(en.getEncodeId())
      var offers = tag.getCompound('Offers')
      var recipes = offers.contains('Recipes', 9) ? offers.getList('Recipes', 10).size() : (offers.contains('Recipes', 10) ? offers.getCompound('Recipes').getList('Recipes', 10).size() : 0)
      var nav = tag.getCompound('Navigation')
      var home = nav.contains('Home') ? [nav.getCompound('Home').getInt('X'), nav.getCompound('Home').getInt('Y'), nav.getCompound('Home').getInt('Z')] : null
      copy.npcs.push({ id: id, uuid: String(tag.getUUID('UUID')), name: String(en.getName().getString()), owner: tag.contains('Owner'), home: home,
        at: [Math.floor(en.getX()), Math.floor(en.getY()), Math.floor(en.getZ())], recipes: recipes, dialogs: tag.getCompound('DialogData').getList('DialogDataSet', 10).size() })
    })
    for (var bx = box.minX(); bx <= box.maxX(); bx++) {
      for (var bz = box.minZ(); bz <= box.maxZ(); bz++) {
        for (var by = box.minY(); by <= box.maxY(); by++) {
          var bp = new $StructTestBlockPos(bx, by, bz)
          var be = level.getBlockEntity(bp)
          if (!be) continue
          var bid = String($StructTestBuiltIn.BLOCK.getKey(level.getBlockState(bp).getBlock()))
          if (bid.indexOf('easy_npc:') !== 0) continue
          var t = be.saveWithoutMetadata(level.registryAccess())
          var stored = t.getCompound('StoredPresetData')
          copy.spawners.push({ block: bid, uuid: t.hasUUID('UUID') ? String(t.getUUID('UUID')) : null,
            npc: stored.hasUUID('UUID') ? String(stored.getUUID('UUID')) : null, owner: stored.contains('Owner'),
            home: stored.getCompound('Navigation').contains('Home'), recipes: stored.getCompound('Offers').getList('Recipes', 10).size() })
        }
      }
    }
    copies.push(copy)
  })
  results.npcs = copies
  if (copies.length < 2) {
    check('NPC fixture placed twice', false, `${copies.length} copies`)
    return
  }
  var a = copies[0], b = copies[1]
  var ok = a.npcs.length === 1 && b.npcs.length === 1
  check('one trader per copy', ok, `${a.npcs.length} and ${b.npcs.length} Easy NPC entities`)
  if (ok) {
    check('traders are separate entities', a.npcs[0].uuid !== b.npcs[0].uuid, `${a.npcs[0].uuid} / ${b.npcs[0].uuid}`)
    check('trader has no owner', !a.npcs[0].owner && !b.npcs[0].owner, `owner ${a.npcs[0].owner} / ${b.npcs[0].owner}`)
    check('trader keeps its trades and dialogue', a.npcs[0].recipes > 0 && a.npcs[0].dialogs > 0, `${a.npcs[0].recipes} trades, ${a.npcs[0].dialogs} dialogs, name ${a.npcs[0].name}`)
    var h = a.npcs[0].home
    check('trader home is where it stands', h !== null && Math.abs(h[0] - a.npcs[0].at[0]) <= 2 && Math.abs(h[2] - a.npcs[0].at[2]) <= 2, `home ${h}, at ${a.npcs[0].at}`)
  }
  var sok = a.spawners.length === 1 && b.spawners.length === 1
  check('one smith spawner per copy', sok, `${a.spawners.length} and ${b.spawners.length}`)
  if (sok) {
    check('spawners have their own NPC UUIDs', a.spawners[0].npc && b.spawners[0].npc && a.spawners[0].npc !== b.spawners[0].npc && a.spawners[0].uuid !== b.spawners[0].uuid,
      `npc ${a.spawners[0].npc} / ${b.spawners[0].npc}, spawner ${a.spawners[0].uuid} / ${b.spawners[0].uuid}`)
    check('spawner preset has no owner or home', !a.spawners[0].owner && !a.spawners[0].home, `owner ${a.spawners[0].owner}, home ${a.spawners[0].home}, ${a.spawners[0].recipes} trades`)
  }
}

// Every pack loot table rolled 200 times at a real chest position: loads, gives items, none on the deny-list.
function structTestLoot(server, level, job, results, check) {
  var deny = job.deny.map(function (p) { return new RegExp(p) })
  var origin = new $StructTestVec3(0.5, 64, 0.5)
  job.lootTables.forEach(function (t) {
    var table = server.reloadableRegistries().getLootTable($StructTestRK.create($StructTestRegistries.LOOT_TABLE, $StructTestRL.parse(t)))
    var seen = {}
    var bad = []
    for (var i = 0; i < 200; i++) {
      var params = new $StructTestLootParams(level).withParameter($StructTestLootContextParams.ORIGIN, origin).create($StructTestLootParamSets.CHEST)
      table.getRandomItems(params).forEach(function (stack) {
        var id = String($StructTestBuiltIn.ITEM.getKey(stack.getItem()))
        seen[id] = (seen[id] || 0) + Number(stack.getCount())
        if (deny.some(function (r) { return r.test(id) })) bad.push(id)
      })
    }
    results.loot[t] = seen
    check(`loot ${t}`, Object.keys(seen).length > 0 && bad.length === 0, `${Object.keys(seen).length} items` + (bad.length ? `, denied: ${bad}` : ''))
  })
}

// Real-world sites: where they start, that it matches the Real World waypoint position, and that it is dry land.
function structTestSites(level, results, check) {
  var siteTag = $StructTestTagKey.create($StructTestRegistries.BIOME, $StructTestRL.parse('pack:has_structure/site'))
  $StructTestApi.sites(level).entrySet().forEach(function (e) {
    var site = String(e.getKey())
    var v = e.getValue()
    if (v.length === 0) {
      check(`site ${site}`, false, 'no position (TFC: Real World missing?)')
      return
    }
    level.getChunk(v[0], v[1])
    var biome = level.getBiome(new $StructTestBlockPos(v[2], 64, v[3]))
    var land = biome.is(siteTag)
    results.sites[site] = { chunk: [v[0], v[1]], block: [v[2], v[3]], enabled: v[4], biome: String(biome.unwrapKey().get().location()), land: land }
    check(`site ${site} on land`, land, `block ${v[2]}, ${v[3]}, biome ${results.sites[site].biome}` + (land ? '' : ' (needs an offset in the catalogue)'))
  })
}

// Structures per 1,000 x 1,000 blocks around each place: every grid cell's candidate chunk, its climate and biome checks,
// without generating anything.
function structTestDensity(level, job, results) {
  var generator = level.getChunkSource().getGenerator()
  var state = level.getChunkSource().getGeneratorState()
  var sampler = level.getChunkSource().randomState().sampler()
  var seed = level.getSeed()
  var setReg = level.registryAccess().registryOrThrow($StructTestRegistries.STRUCTURE_SET)
  setReg.entrySet().forEach(function (e) {
    var id = String(e.getKey().location())
    if (id.indexOf('pack:') !== 0 || id.indexOf('pack:site/') === 0) return
    var set = e.getValue()
    var placement = set.placement()
    if (!(placement instanceof $StructTestRandomSpread)) return
    var structure = set.structures().get(0).structure().value()
    var spacing = placement.spacing()
    var hits = 0
    var area = 0
    job.places.forEach(function (place) {
      var xz = $StructTestProjection.geographicToClassic(place[2], place[1])
      var r = job.densityRadius
      var c0x = Math.floor((xz[0] - r) / 16 / spacing)
      var c1x = Math.floor((xz[0] + r) / 16 / spacing)
      var c0z = Math.floor((xz[1] - r) / 16 / spacing)
      var c1z = Math.floor((xz[1] + r) / 16 / spacing)
      for (var rx = c0x; rx <= c1x; rx++) {
        for (var rz = c0z; rz <= c1z; rz++) {
          var chunk = placement.getPotentialStructureChunk(seed, rx * spacing, rz * spacing)
          if (!placement.isStructureChunk(state, chunk.x, chunk.z)) continue
          var bx = chunk.getMiddleBlockX()
          var bz = chunk.getMiddleBlockZ()
          var biome = generator.getBiomeSource().getNoiseBiome($StructTestQuart.fromBlock(bx), $StructTestQuart.fromBlock(64), $StructTestQuart.fromBlock(bz), sampler)
          if (structure.biomes().contains(biome)) hits++
        }
      }
      area += (2 * r) * (2 * r)
    })
    results.density[id] = { hits: hits, perMillionBlocks2: hits / (area / 1e6), spacing: spacing }
    console.info(`[structures-test] density ${id}: ${(hits / (area / 1e6)).toFixed(2)} per 1000x1000 blocks (${hits} in ${job.places.length} areas)`)
  })
}

// ---------------------------------------------------------------------------------------------------------------------------------
// Villages (docs/lived-in.md, "Settlements"): pack_world:region placement, pack_world:guarded_jigsaw, wood ranks, camouflage, NPCs.
// The job (STRUCT_TEST_JOB.villageJob) comes from tools/structures_test.py: sets, structures, templates (non-air blocks, jigsaws left out),
// region reference points, test places per culture, the catalogue's NPCs.

const $VtStructurePlacement = Java.loadClass('net.minecraft.world.level.levelgen.structure.placement.StructurePlacement')
const $VtStructure = Java.loadClass('net.minecraft.world.level.levelgen.structure.Structure')
const $VtJsonOps = Java.loadClass('com.mojang.serialization.JsonOps')
const $VtChunkStatus = Java.loadClass('net.minecraft.world.level.chunk.status.ChunkStatus')
const $VtHeightmap = Java.loadClass('net.minecraft.world.level.levelgen.Heightmap$Types')
const $VtMaterials = Java.loadClass('pack.world.api.PackWorldApi')

function vtList(l) {
  var out = []
  l.forEach(function (x) { out.push(x) })
  return out
}

function vtStrings(l) {
  return vtList(l).map(function (x) { return String(x) })
}

function structTestVillages(server, level, job, results, check, idAt) {
  var vj = job.villageJob
  results.villages = { regions: {}, guard: {}, found: [], placed: [] }
  $VtMaterials.setGuard(true)
  $VtMaterials.guardReset()
  $VtMaterials.keepClearReset()
  // a stage that throws is a failure of its own and the others still run
  var stage = function (name, fn) {
    try { fn() } catch (e) { check('villages: ' + name, false, String(e) + (e && e.stack ? ' ' + String(e.stack).replace(/\s+/g, ' ') : '')) }
  }
  stage('regions', function () { vtRegions(level, vj, results, check) })
  stage('guard', function () { vtGuard(level, vj, results, check) })
  stage('codecs', function () { vtCodec(level, vj, results, check) })
  stage('equivalence with tfc:climate', function () { vtEquivalence(level, vj, results, check) })
  stage('wood palette', function () { vtWoodPalette(vj, check) })
  stage('keep clear', function () { vtKeepClear(level, results, check) })
  if (vj.acceptance) stage('acceptance census', function () { vtAcceptance(level, vj, results, check) })
  stage('locate', function () { vtLocate(level, vj, results, check) })
  stage('natural villages', function () { vtNatural(server, level, vj, results, check) })
  stage('placed villages', function () { vtPlaced(server, level, vj, results, check) })
  var stats = $VtMaterials.guardStats()
  var s = {}
  stats.forEach(function (k, v) { s[String(k)] = Number(v) })
  results.villages.guardStats = s
  var kc = {}
  $VtMaterials.keepClearStats().forEach(function (k, v) { kc[String(k)] = Number(v) })
  results.villages.keepClearStats = kc
  console.info(`[structures-test] keep clear: ${JSON.stringify(kc)}`)
  console.info(`[structures-test] guard: ${s.attempts} attempts, ${s.passed} passed, ${s.refusedBiome} wrong biome, ${s.refusedWater} water, ${s.refusedSlope} slope; ` +
    `${s.attempts ? (s.nanos / s.attempts / 1e6).toFixed(1) : 0} ms per attempt`)
}

// ---- keep clear (docs/lived-in.md, *Keeping the land clear*): the data is loaded, says what it should about a few structures, and TFC's
// boulders carry the filter. What it does in a world is read back from the natural villages below (leaves over their pieces).
const $VtMutablePos = Java.loadClass('net.minecraft.core.BlockPos$MutableBlockPos')
const $VtBlockTags = Java.loadClass('net.minecraft.tags.BlockTags')
function vtKeepClear(level, results, check) {
  var cfg = String($VtMaterials.keepClearConfig())
  check('keep clear: data loaded', cfg.indexOf('DISABLED') < 0 && cfg.indexOf('holds Matcher[namespaces=[], ids=[], globs=[]]') < 0, cfg.slice(0, 160))
  var want = [
    ['pack:village/norse_living', 'trees=true holds=true yields=false'], ['pack:village/aqueduct_main', 'trees=true holds=true yields=false'],
    ['pack:cairn', 'trees=true holds=false yields=true'], ['mvs:house', 'trees=true holds=false yields=true'], ['mvs:windmill', 'trees=true holds=false yields=true'],
    ['mvs:oak_tree', 'trees=false holds=false yields=true'], ['mvs:boulder', 'trees=false holds=false yields=true'],
    ['towns_and_towers:village_grove', 'trees=true holds=false yields=true'], ['tfchuts:settlement', 'trees=true holds=false yields=true'],
    ['betterdungeons:small_dungeon', 'trees=false holds=false yields=true'], ['bettermineshafts:mineshaft_mesa', 'trees=false holds=false yields=true'],
    ['minecraft:village_plains', 'trees=false holds=false yields=false']]
  want.forEach(function (w) {
    var got = String($VtMaterials.keepClearDescribe(w[0]))
    results.villages.keepClear = results.villages.keepClear || {}
    results.villages.keepClear[w[0]] = got
    check('keep clear: ' + w[0], got === w[1], got + (got === w[1] ? '' : ', wanted ' + w[1]))
  })
  var placedReg = level.registryAccess().registryOrThrow($StructTestRegistries.PLACED_FEATURE)
  ;['raw_boulder', 'cobble_boulder', 'mossy_boulder', 'raw_boulder_small', 'cobble_boulder_small', 'mossy_boulder_small'].forEach(function (name) {
    var pf = placedReg.get($StructTestRL.parse('tfc:' + name))
    var has = false
    if (pf) pf.placement().forEach(function (m) { if (String(m).indexOf('KeepClearFilter') >= 0) has = true })
    check('keep clear: tfc:' + name + ' has the pack_world:keep_clear filter', has, has ? 'present' : (pf ? 'placement without it' : 'no such placed feature'))
  })
}

// leaves of trees that grew inside the pieces' boxes (TFC's and ArborFirmaCraft's)
function vtLeaves(level, start) {
  var mp = new $VtMutablePos()
  var inBoxes = 0
  start.getPieces().forEach(function (piece) {
    var b = piece.getBoundingBox()
    for (var x = b.minX(); x <= b.maxX(); x++) for (var z = b.minZ(); z <= b.maxZ(); z++) for (var y = b.minY(); y <= b.maxY(); y++) {
      var bs = level.getBlockState(mp.set(x, y, z))
      // a template's own leaves are persistent (an orchard tree): only trees that grew there count
      if (bs['is(net.minecraft.tags.TagKey)']($VtBlockTags.LEAVES) && String(bs).indexOf('persistent=true') < 0) inBoxes++
    }
  })
  return inBoxes
}

// ---- regions: loaded, projected as declared, reference points inside the right set and no other, blockOf equal to the Python projection
function vtRegions(level, vj, results, check) {
  var sets = $VtMaterials.regionSets(level)
  vj.sets.forEach(function (s) {
    var row = sets.get('pack:' + s.id)
    if (!row) {
      check(`region set ${s.id} is a pack_world:region placement`, false, 'not registered or not a region placement')
      return
    }
    var inc = vtList(row.get('regions').keySet()).map(String)
    var exc = vtList(row.get('exclude').keySet()).map(String)
    var ok = inc.length === s.regions.length && exc.length === s.exclude.length
    check(`region set ${s.id}: every region projects`, ok, `declared ${s.regions.length}+${s.exclude.length}, projected ${inc.length}+${exc.length}`)
    var areas = {}
    inc.forEach(function (n) { areas[n] = Math.round(row.get('regions').get(n).get(1)) })
    results.villages.regions[s.id] = { spacing: Number(row.get('spacing')), regions: areas, exclude: exc }
  })
  var bad = []
  vj.regionChecks.forEach(function (rc) {
    var xz = $VtMaterials.blockOf(rc.lat, rc.lon)
    var dx = Math.abs(xz[0] - rc.block[0])
    var dz = Math.abs(xz[1] - rc.block[1])
    if (dx > 1 || dz > 1) bad.push(`${rc.name} block ${xz[0]},${xz[1]} vs ${rc.block[0]},${rc.block[1]}`)
    vj.sets.forEach(function (s) {
      var names = vtStrings($VtMaterials.regionsAt(level, 'pack:' + s.id, rc.lat, rc.lon))
      var inside = names.some(function (n) { return n.charAt(0) !== '!' }) && !names.some(function (n) { return n.charAt(0) === '!' })
      var want = rc.sets.indexOf(s.id) >= 0
      if (inside !== want) bad.push(`${rc.name} ${inside ? 'is' : 'is not'} in ${s.id} (${names})`)
    })
    // the placement step agrees at the chunk of the point
    vj.sets.forEach(function (s) {
      var step = $VtMaterials.placementAt(level, 'pack:' + s.id, xz[0] >> 4, xz[1] >> 4)
      var inside = step.get('region') === true
      if (inside !== (rc.sets.indexOf(s.id) >= 0)) bad.push(`${rc.name}: placement region step ${inside} for ${s.id}`)
    })
  })
  check(`region reference points (${vj.regionChecks.length} places x ${vj.sets.length} sets)`, bad.length === 0, bad.length ? `${bad.length} wrong: ${bad.slice(0, 6).join('; ')}` : 'all inside their set and outside the others; blockOf equals the Python projection')
}

// ---- the guard: sample layout, determinism, a mid-ocean point and a mountain are refused, flat ground passes
function vtGuard(level, vj, results, check) {
  var server_runCommand = function (c) { level.getServer().getCommands().performPrefixedCommand(level.getServer().createCommandSourceStack(), c) }
  var offsets = $VtMaterials.guardOffsets(48, 13)
  var got = vtList(offsets).map(function (o) { return `(${o.get(0)},${o.get(1)})` }).join(' ')
  var want = '(0,0) (-10,9) (2,-20) (15,19) (-27,-5) (26,-17) (-9,33) (-17,-33) (37,13) (-38,16) (19,-40) (14,44) (-42,-24)'
  check('guard sample layout (13 columns, radius 48)', got === want, got === want ? 'as specified' : got)
  var sid = vj.guardStructure
  var ocean = $VtMaterials.blockOf(48.0, -30.0)
  var r1 = $VtMaterials.guardAt(level, 'pack:' + sid, ocean[0], ocean[1])
  check('guard refuses the open sea', r1.size() > 0 && r1.get('pass') === false && String(r1.get('reason')) === 'water', String(r1))
  var alps = $VtMaterials.blockOf(46.55, 10.1)
  var r2 = $VtMaterials.guardAt(level, 'pack:' + sid, alps[0], alps[1])
  check('guard refuses mountains (Alps)', r2.size() > 0 && r2.get('pass') === false, String(r2))
  var found = vj.guardFlat
  var flats = []
  found.forEach(function (p) {
    var xz = $VtMaterials.blockOf(p[1], p[2])
    var a = $VtMaterials.guardAt(level, 'pack:' + sid, xz[0], xz[1])
    var b = $VtMaterials.guardAt(level, 'pack:' + sid, xz[0], xz[1])
    var c = $VtMaterials.guardAt(level, 'pack:' + sid, xz[0], xz[1])
    var same = String(a) === String(b) && String(b) === String(c)
    flats.push(`${p[0]} ${a.get('pass') ? 'pass' : 'refused ' + a.get('reason')} (${a.get('min')}..${a.get('max')}, wet ${a.get('wet')})${same ? '' : ' UNSTABLE'}`)
    results.villages.guard[p[0]] = String(a)
    if (!same) check(`guard is stable at ${p[0]}`, false, `${a} / ${b} / ${c}`)
  })
  console.info(`[structures-test] NOTE guard at flat candidates: ${flats.join('; ')}`)
  // the switch: /pack_world guard off lets /place put a village on the Alps, on brings the refusal back
  var structure = structTestStructure(level.registryAccess().registryOrThrow($StructTestRegistries.STRUCTURE), sid)
  var generator = level.getChunkSource().getGenerator()
  var tryAt = function () {
    var start = structure.generate(level.registryAccess(), generator, generator.getBiomeSource(), level.getChunkSource().randomState(),
      level.getStructureManager(), level.getSeed(), new $StructTestChunkPos(alps[0] >> 4, alps[1] >> 4), 0, level, function (h) { return true })
    return start.isValid()
  }
  server_runCommand('pack_world guard on')
  var on = tryAt()
  server_runCommand('pack_world guard off')
  var off = tryAt()
  server_runCommand('pack_world guard on')
  var again = tryAt()
  check('/pack_world guard off places on rough ground, on refuses it', !on && off && !again, `on ${on}, off ${off}, on again ${again}`)
}

// ---- codecs: every village set and structure survives encode/decode, with its fields
function vtCodec(level, vj, results, check) {
  var setReg = level.registryAccess().registryOrThrow($StructTestRegistries.STRUCTURE_SET)
  var structReg = level.registryAccess().registryOrThrow($StructTestRegistries.STRUCTURE)
  var ops = level.registryAccess().createSerializationContext($VtJsonOps.INSTANCE)   // registry ops: pools and biomes encode as ids (plain JsonOps recurses through the pool graph)
  var bad = []
  vj.sets.forEach(function (s) {
    var set = structTestStructure(setReg, s.id)
    var placement = set.placement()
    var json = $VtStructurePlacement.CODEC.encodeStart(ops, placement).getOrThrow()
    var again = $VtStructurePlacement.CODEC.parse(ops, json).getOrThrow()
    var json2 = $VtStructurePlacement.CODEC.encodeStart(ops, again).getOrThrow()
    if (String(json) !== String(json2)) bad.push(`${s.id} placement does not round-trip`)
    if (Number(json.get('salt').getAsInt()) !== s.salt || Number(json.get('spacing').getAsInt()) !== s.spacing) bad.push(`${s.id} salt/spacing`)
    if (String(json.get('type').getAsString()) !== 'pack_world:region') bad.push(`${s.id} type ${json.get('type')}`)
    if (json.get('regions').size() !== s.regions.length) bad.push(`${s.id} region count`)
    s.structures.forEach(function (st) {
      var structure = structTestStructure(structReg, st.id)
      var sj = $VtStructure.DIRECT_CODEC.encodeStart(ops, structure).getOrThrow()
      var sj2 = $VtStructure.DIRECT_CODEC.encodeStart(ops, $VtStructure.DIRECT_CODEC.parse(ops, sj).getOrThrow()).getOrThrow()
      if (String(sj) !== String(sj2)) bad.push(`${st.id} structure does not round-trip`)
      var g = sj.get('guard')
      // fields equal to the codec's defaults (radius 48, 13 samples, difference 8, water 0.1) are not written back
      var gi = function (k, d) { return g && g.has(k) ? Number(g.get(k).getAsDouble()) : d }
      if (String(sj.get('type').getAsString()) !== 'pack_world:guarded_jigsaw' || !g || gi('radius', 48) !== st.guard.radius ||
        gi('max_height_difference', 8) !== st.guard.max_height_difference || gi('samples', 13) !== st.guard.samples) bad.push(`${st.id} guard fields`)
    })
  })
  check('village sets and structures round-trip through their codecs', bad.length === 0, bad.length ? bad.join('; ') : `${vj.sets.length} sets, ${vj.structures.length} structures`)
}

// ---- equivalence with TFC: the same grid, salt and climate under tfc:climate give the same answer as pack_world:region's grid + climate
function vtEquivalence(level, vj, results, check) {
  var setReg = level.registryAccess().registryOrThrow($StructTestRegistries.STRUCTURE_SET)
  var state = level.getChunkSource().getGeneratorState()
  var seed = level.getSeed()
  var ops = level.registryAccess().createSerializationContext($VtJsonOps.INSTANCE)
  var bad = []
  var summary = []
  vj.sets.forEach(function (s) {
    var set = structTestStructure(setReg, s.id)
    var placement = set.placement()
    var json = $VtStructurePlacement.CODEC.encodeStart(ops, placement).getOrThrow().deepCopy()
    json.addProperty('type', 'tfc:climate')
    json.remove('regions')
    json.remove('exclude')
    json.remove('outside')
    var tfc = $VtStructurePlacement.CODEC.parse(ops, json).getOrThrow()
    var spacing = placement.spacing()
    var n = 0
    var yes = 0
    var outsideYes = 0
    var places = vj.places[s.culture] || []
    places.forEach(function (p) {
      var xz = $VtMaterials.blockOf(p[1], p[2])
      var cx0 = Math.floor(xz[0] / 16)
      var cz0 = Math.floor(xz[1] / 16)
      for (var a = -6; a <= 6; a++) {
        for (var b = -6; b <= 6; b++) {
          var c = placement.getPotentialStructureChunk(seed, cx0 + a * spacing, cz0 + b * spacing)
          var region = placement.regionContains(c.x, c.z)
          var ours = placement.isStructureChunk(state, c.x, c.z)
          var theirs = tfc.isStructureChunk(state, c.x, c.z)
          n++
          if (region) {
            if (ours !== theirs) bad.push(`${s.id} ${c.x},${c.z}: region ${ours} vs tfc:climate ${theirs}`)
            if (ours) yes++
          } else if (ours) {
            outsideYes++
          }
        }
      }
    })
    if (outsideYes) bad.push(`${s.id}: ${outsideYes} placements outside the region`)
    summary.push(`${s.culture} ${n} cells ${yes} placed`)
  })
  check('region placement equals tfc:climate inside the region, and places nothing outside', bad.length === 0, bad.length ? bad.slice(0, 5).join('; ') : summary.join(', '))
}

// ---- wood ranks and Roads and Roofs / Framed materials through the mod's own mapping, for every rock, wood (TFC and ArborFirmaCraft), soil
function vtWoodPalette(vj, check) {
  var bad = []
  var n = 0
  var woodSets = vj.woodSets
  vj.placeholders.wood.forEach(function (id) {
    woodSets.forEach(function (ws) {
      var out = String($VtMaterials.mapIdRanked(id, 'gabbro', ws, 'alfisol', 'yellow', 'work'))
      n++
      if (!vtBlockExists(out)) bad.push(`${id} -> ${out} (${ws})`)
    })
  })
  vj.placeholders.rnrRock.forEach(function (id) {
    STRUCT_TEST_ROCKS.forEach(function (rock) {
      var out = String($VtMaterials.mapIdRanked(id, rock, ['oak'], 'alfisol', 'yellow', 'work'))
      n++
      if (!vtBlockExists(out) || (rock !== 'granite' && out === id)) bad.push(`${id} -> ${out} (${rock})`)
      if (/\/(raw|cobble|loose)\//.test(out) && STRUCT_TEST_ROUGH.test(out)) bad.push(`${id} -> ${out}: alloy rock`)
    })
  })
  vj.placeholders.rnrSoil.forEach(function (id) {
    STRUCT_TEST_SOILS.forEach(function (soil) {
      var out = String($VtMaterials.mapIdRanked(id, 'gabbro', ['oak'], soil, 'yellow', 'work'))
      n++
      if (!vtBlockExists(out) || (soil !== 'alfisol' && out === id)) bad.push(`${id} -> ${out} (${soil})`)
    })
  })
  // ranks: three trees, fewer trees (clamped), and a rank that is not a placeholder is left alone
  var m3 = String($VtMaterials.mapIdRanked('tfc:wood/planks/spruce_stairs', 'gabbro', ['maple', 'ash', 'pine'], 'alfisol', 'yellow', 'work'))
  var m1 = String($VtMaterials.mapIdRanked('tfc:wood/planks/birch', 'gabbro', ['maple'], 'alfisol', 'yellow', 'work'))
  var mafc = String($VtMaterials.mapIdRanked('rnr:wood/shingles/oak_slab', 'gabbro', ['afc:mahogany', 'oak', 'ash'], 'alfisol', 'yellow', 'work'))
  var mafc2 = String($VtMaterials.mapIdRanked('tfc:wood/door/oak', 'gabbro', ['afc:teak', 'oak', 'ash'], 'alfisol', 'yellow', 'work'))
  var keep = String($VtMaterials.mapIdRanked('tfc:wood/planks/acacia', 'gabbro', ['maple', 'ash', 'pine'], 'alfisol', 'yellow', 'work'))
  if (m3 !== 'tfc:wood/planks/ash_stairs') bad.push(`rank 1 of maple,ash,pine gave ${m3}`)
  if (m1 !== 'tfc:wood/planks/maple') bad.push(`clamped rank gave ${m1}`)
  if (mafc !== 'rnr:wood/shingles/mahogany_slab') bad.push(`afc shingles gave ${mafc}`)
  if (mafc2 !== 'afc:wood/door/teak') bad.push(`afc door gave ${mafc2}`)
  if (keep !== 'tfc:wood/planks/acacia') bad.push(`a non-placeholder wood changed: ${keep}`)
  check('wood ranks, Roads and Roofs and AFC woods map to existing blocks', bad.length === 0, `${n} mappings` + (bad.length ? `; ${bad.length} bad: ${bad.slice(0, 10).join('; ')}` : ''))
}

function vtBlockExists(id) {
  return id === 'minecraft:air' || $StructTestBuiltIn.BLOCK.containsKey($StructTestRL.parse(id))
}

// ---- natural villages: the nearest valid starts to the test places, chunks generated normally
function vtNatural(server, level, vj, results, check) {
  var structReg = level.registryAccess().registryOrThrow($StructTestRegistries.STRUCTURE)
  var setReg = level.registryAccess().registryOrThrow($StructTestRegistries.STRUCTURE_SET)
  var state = level.getChunkSource().getGeneratorState()
  var seed = level.getSeed()
  var generator = level.getChunkSource().getGenerator()
  var sampler = level.getChunkSource().randomState().sampler()
  vj.sets.forEach(function (s) {
    var set = structTestStructure(setReg, s.id)
    var placement = set.placement()
    var spacing = placement.spacing()
    var structures = s.structures.map(function (st) { return { id: st.id, variant: st.variant, structure: structTestStructure(structReg, st.id), ground: st.ground } })
    var scan = { cells: 0, region: 0, placed: 0, noStart: 0, valid: 0, why: {} }
    var wanted = vj.perSet
    var foundHere = 0
    var places = vj.places[s.culture] || []
    for (var pi = 0; pi < places.length && foundHere < wanted; pi++) {
      var p = places[pi]
      var xz = $VtMaterials.blockOf(p[1], p[2])
      var cx0 = Math.floor(xz[0] / 16)
      var cz0 = Math.floor(xz[1] / 16)
      var perPlace = 0
      for (var r = 0; r <= vj.maxRing && perPlace < Math.ceil(wanted / places.length) && foundHere < wanted; r++) {
        for (var a = -r; a <= r; a++) {
          for (var b = -r; b <= r; b++) {
            if (Math.max(Math.abs(a), Math.abs(b)) !== r) continue
            var c = placement.getPotentialStructureChunk(seed, cx0 + a * spacing, cz0 + b * spacing)
            scan.cells++
            if (!placement.regionContains(c.x, c.z)) continue
            scan.region++
            if (!placement.isStructureChunk(state, c.x, c.z)) continue
            scan.placed++
            var chunk = level.getChunk(c.x, c.z, $VtChunkStatus.STRUCTURE_STARTS)
            var start = null
            var which = null
            structures.forEach(function (st) {
              var found = chunk.getStartForStructure(st.structure)
              if (found !== null && found.isValid() && start === null) { start = found; which = st }
            })
            if (start === null) {
              scan.noStart++
              var bx = c.getMiddleBlockX()
              var bz = c.getMiddleBlockZ()
              var biome = generator.getBiomeSource().getNoiseBiome($StructTestQuart.fromBlock(bx), $StructTestQuart.fromBlock(64), $StructTestQuart.fromBlock(bz), sampler)
              var why
              if (!structures[0].structure.biomes().contains(biome)) {
                why = 'biome ' + String(biome.unwrapKey().get().location())
              } else {
                var gr = $VtMaterials.guardAt(level, 'pack:' + structures[0].id, bx, bz)
                why = gr.size() ? (gr.get('pass') ? 'guard passes at the chunk centre (start piece elsewhere)' : String(gr.get('reason')) + (String(gr.get('reason')) === 'slope' ? ' ' + (Number(gr.get('max')) - Number(gr.get('min'))) : '')) : 'guard n/a'
              }
              scan.why[why] = (scan.why[why] || 0) + 1
              continue
            }
            scan.valid++
            if (perPlace >= Math.ceil(wanted / places.length) || foundHere >= wanted) continue
            var t0 = Date.now()
            var box = start.getBoundingBox()
            for (var gx = (box.minX() >> 4) - 1; gx <= (box.maxX() >> 4) + 1; gx++) {
              for (var gz = (box.minZ() >> 4) - 1; gz <= (box.maxZ() >> 4) + 1; gz++) level.getChunk(gx, gz)
            }
            var rec = { kind: 'natural', place: p[0], structure: which.id, at: [box.getCenter().getX(), box.getCenter().getZ()], placed: true, genMs: Date.now() - t0 }
            vtInspect(level, start, which, rec, vj)
            results.villages.found.push(rec)
            check(`${which.id} natural near ${p[0]} at ${rec.at}`, vtOk(rec), vtDetail(rec))
            perPlace++
            foundHere++
          }
        }
      }
    }
    results.villages.found.push({ kind: 'scan', set: s.id, scan: scan })
    console.info(`[structures-test] NOTE ${s.id} scan: ${scan.cells} grid cells, ${scan.region} in region, ${scan.placed} with climate, ${scan.valid} with a valid start (${scan.noStart} refused by biome or guard), ${foundHere} generated; refused for: ${JSON.stringify(scan.why)}`)
    if (!foundHere) console.info(`[structures-test] NOTE ${s.id}: no natural village within ${vj.maxRing} cells of the places`)
  })
}

// ---- every structure placed the way /place does (guard off): all variants get looked at, whether or not one happens to be near
function vtPlaced(server, level, vj, results, check) {
  var structReg = level.registryAccess().registryOrThrow($StructTestRegistries.STRUCTURE)
  var generator = level.getChunkSource().getGenerator()
  $VtMaterials.setGuard(false)
  var i = 0
  vj.structures.forEach(function (st) {
    var places = vj.places[st.culture] || []
    var p = places[0]
    var found = startAtFind(level, p[1], p[2])
    if (!found.spot) {
      check(`dry ground at ${p[0]}`, false, `point ${found.point.x},${found.point.z}`)
      return
    }
    var x = found.spot.x + 150 * (i % 3)
    var z = found.spot.z + 150 * Math.floor(i / 3) + 400
    i++
    var structure = structTestStructure(structReg, st.id)
    var t0 = Date.now()
    var start = structure.generate(level.registryAccess(), generator, generator.getBiomeSource(), level.getChunkSource().randomState(),
      level.getStructureManager(), level.getSeed(), new $StructTestChunkPos(x >> 4, z >> 4), 0, level, function (h) { return true })
    var rec = { kind: 'placed', place: p[0], structure: st.id, at: [x, z], placed: start.isValid() }
    if (rec.placed) {
      var box = start.getBoundingBox()
      for (var cx = box.minX() >> 4; cx <= box.maxX() >> 4; cx++) {
        for (var cz = box.minZ() >> 4; cz <= box.maxZ() >> 4; cz++) {
          level.getChunk(cx, cz)
          start.placeInChunk(level, level.structureManager(), generator, level.getRandom(),
            new $StructTestBox(cx << 4, level.getMinBuildHeight(), cz << 4, (cx << 4) + 15, level.getMaxBuildHeight(), (cz << 4) + 15), new $StructTestChunkPos(cx, cz))
        }
      }
      rec.genMs = Date.now() - t0
      vtInspect(level, start, st, rec, vj)
    }
    results.villages.placed.push(rec)
    check(`${st.id} placed at ${p[0]}`, vtOk(rec), vtDetail(rec))
  })
  $VtMaterials.setGuard(true)
}

function vtOk(rec) {
  return rec.placed && !rec.leaks.length && !rec.vanilla.length && !rec.alloy.length && rec.npcExpected === rec.npcCount &&
    // an NPC whose floor is missing falls a block or two when it spawns (they are invulnerable): a few of those are the template's, not a finding
    rec.npcs.every(function (n) { return !n.owner && n.trades > 0 && n.drop <= 3 }) && rec.npcs.filter(function (n) { return n.drop > 0 }).length <= Math.max(1, rec.npcs.length * 0.1) &&
    !rec.mixed && (rec.kind === 'placed' || (rec.floatColumns <= Math.max(2, rec.columns * 0.02) && rec.leavesInBoxes <= 200))
}

function vtDetail(rec) {
  if (!rec.placed) return 'did not place'
  return `${rec.pieces} pieces (${rec.npcPieces} NPC), ${rec.templateBlocks} template blocks (${rec.missing} gone), NPCs ${rec.npcCount}/${rec.npcExpected} ${JSON.stringify(rec.npcNames)} (trades ${rec.npcs.map(function (n) { return n.trades }).join(',')}, ${rec.npcs.filter(function (n) { return n.invulnerable }).length} invulnerable, ${rec.npcs.filter(function (n) { return n.noGravity }).length} without gravity, ${rec.npcs.filter(function (n) { return n.drop > 0 }).length} above the floor), ` +
    `leaks [${rec.leaks}], vanilla [${rec.vanilla}], alloy [${rec.alloy}], other rocks [${rec.otherRock}], other woods [${rec.otherWood}], ` +
    `rock ${rec.rockSet}, woods ${rec.woodSet}${rec.mixed ? ' MIXED (built of woods ' + Object.keys(rec.usedWoods) + ', rocks ' + Object.keys(rec.usedRocks) + ')' : ''}, chests ${rec.chests} (loot ${rec.lootChests}), framed ${rec.framed} (camo ${JSON.stringify(rec.camoTop)}), ` +
    `${rec.leavesInBoxes >= 0 ? 'leaves in the boxes ' + rec.leavesInBoxes + ', ' : ''}floating ${rec.floatColumns}/${rec.columns} (max gap ${rec.maxGap}), ground offset ${JSON.stringify(rec.groundOffset)}, terrain pieces ${rec.terrainPieces || 0}, ${rec.genMs} ms` +
    (rec.details.length ? `; details: ${rec.details.slice(0, 4).join(' | ')}` : '')
}

// What a placed village holds, checked at exactly the spots its templates place blocks, piece by piece. A village has one rock and one set of
// three woods (the ones at its start piece's centre, PackWorldApi.anchorOf); a block of another wood or rock in any piece is a finding.
function vtInspect(level, start, st, rec, vj) {
  var pieces = start.getPieces()
  var box = start.getBoundingBox()
  var generator = level.getChunkSource().getGenerator()
  var randomState = level.getChunkSource().randomState()
  rec.box = [box.minX(), box.minY(), box.minZ(), box.maxX(), box.maxY(), box.maxZ()]
  rec.size = [box.getXSpan(), box.getYSpan(), box.getZSpan()]
  rec.pieces = pieces.size()
  rec.npcPieces = 0
  rec.byPiece = {}
  rec.leaks = []
  rec.vanilla = []
  rec.alloy = []
  rec.otherRock = []
  rec.otherWood = []
  rec.rocks = {}
  rec.woods = {}
  rec.usedWoods = {}
  rec.usedRocks = {}
  var anchor = $VtMaterials.anchorOf(start)
  rec.anchor = [anchor[0], anchor[1], anchor[2]]
  var anchorRock = String($VtMaterials.materialsAt(level, anchor[0], anchor[1], anchor[2]).get('rock'))
  var anchorWoods = vtStrings($VtMaterials.woodsAt(level, anchor[0], anchor[1], anchor[2], 3, true))
  rec.chests = 0
  rec.lootChests = 0
  rec.lootTables = {}
  rec.framed = 0
  rec.camo = {}
  rec.columns = 0
  rec.floatColumns = 0
  rec.maxGap = 0
  rec.templateBlocks = 0
  rec.missing = 0
  rec.details = []
  rec.groundOffset = { buried3: 0, buried1: 0, flush: 0, raised1: 0, raised3: 0 }
  var counts = {}
  var sampleN = 0
  function add(list, v) { if (list.indexOf(v) < 0) list.push(v) }
  pieces.forEach(function (piece) {
    var m = /(pack[a-z_]*:[a-z0-9_\/]+)/.exec(String(piece.getElement()))
    var tid = m ? m[1] : null
    if (!tid) return
    var short = tid.replace('pack:village/', '')
    rec.byPiece[short] = (rec.byPiece[short] || 0) + 1
    if (tid.indexOf('/npc/') > 0) {
      rec.npcPieces++
      return
    }
    var blocks = vj.templates[tid]
    if (!blocks) return
    // terrain-matching pieces (streets) are bent to the ground block by block: their cells are not where the template puts them
    if (String(piece.getElement().getProjection()).toLowerCase().indexOf('terrain') >= 0) {
      rec.terrainPieces = (rec.terrainPieces || 0) + 1
      return
    }
    var origin = piece.getPosition()
    // one choice per village: the rock and the three woods are those at the start piece's centre, whichever piece a block belongs to
    var rock = anchorRock
    var woods = anchorWoods
    rec.rocks[rock] = (rec.rocks[rock] || 0) + 1
    rec.woods[woods.join('/')] = (rec.woods[woods.join('/')] || 0) + 1
    var settings = new $StructTestPlaceSettings().setRotation(piece.getRotation())
    blocks.forEach(function (b) {
      var rel = $StructTestTemplate.calculateRelativePosition(settings, new $StructTestBlockPos(b[0], b[1], b[2]))
      var pos = rel.offset(origin)
      if (structTestInCopy(pos.getX(), pos.getZ())) return
      var id = String($StructTestBuiltIn.BLOCK.getKey(level.getBlockState(pos).getBlock()))
      var want = vtWoodTarget(b[3], woods)
      rec.templateBlocks++
      counts[id] = (counts[id] || 0) + 1
      if (id === 'minecraft:air' || id === 'minecraft:cave_air') rec.missing++
      // placeholders that the mapping should have replaced
      if (want !== null && want !== b[3] && id === b[3]) {
        add(rec.leaks, `${id} (wood rank ${woods.join('/')})`)
        if (rec.details.length < 20) rec.details.push(`unmapped ${id} (should be ${want}), piece ${short} at ${pos.getX()},${pos.getY()},${pos.getZ()}`)
      }
      if (rock !== 'granite' && STRUCT_TEST_ROCK_LEAK.test(id)) add(rec.leaks, id)
      if (rock !== 'granite' && /^rnr:rock\/[a-z_]+\/granite/.test(id)) add(rec.leaks, id)
      if (/^rnr:tamped_alfisol/.test(b[3]) && false) add(rec.leaks, id)
      if (id.indexOf('minecraft:') === 0 && !STRUCT_TEST_VANILLA_OK[id] && vj.vanillaOk.indexOf(id) < 0) {
        add(rec.vanilla, id)
        if (rec.details.length < 20) rec.details.push(`vanilla ${id} where ${b[3]} should be, piece ${short} at ${pos.getX()},${pos.getY()},${pos.getZ()}`)
      }
      if (STRUCT_TEST_ROUGH.test(id) && /^tfc:rock\//.test(b[3])) {
        add(rec.kind === 'natural' ? rec.overwritten || (rec.overwritten = []) : rec.alloy, id)
        if (rec.details.length < 20) rec.details.push(`rough ${id} where ${b[3]} should be, piece ${short} rock ${rock} at ${pos.getX()},${pos.getY()},${pos.getZ()}`)
      }
      var r = /^(?:tfc|rnr):rock\/(smooth|cobble|bricks|cracked_bricks|mossy_bricks|mossy_cobble|chiseled|raw|loose|mossy_loose|anvil|gravel_road|sett_road|cobbled_road)\/([a-z]+)/.exec(id)
      if (r && /^(smooth|bricks|cracked_bricks|mossy_bricks|chiseled|gravel_road|sett_road|cobbled_road)$/.test(r[1])) rec.usedRocks[r[2]] = (rec.usedRocks[r[2]] || 0) + 1
      if (r && r[2] !== rock && !(r[1] === 'anvil' && STRUCT_TEST_ALLOY[rock])) {
        add(rec.otherRock, r[2])
        if (rec.details.length < 20) rec.details.push(`rock ${id} where ${b[3]} should be (${rock}), piece ${short} at ${pos.getX()},${pos.getY()},${pos.getZ()}`)
      }
      var w = /^(?:tfc|afc):wood\/(planks|chest|fence|fence_gate|log_fence|log|vertical_support|horizontal_support|door|stripped_log|trapdoor)\/([a-z_]+?)(_stairs|_slab)?$/.exec(id)
      var rs = /^rnr:wood\/shingles\/([a-z_]+?)(_stairs|_slab)?$/.exec(id)
      var wname = w ? w[2] : rs ? rs[1] : null
      if (wname && b[3].indexOf('palm_mosaic') < 0) {
        if (!(w && w[1] === 'log')) rec.usedWoods[wname] = (rec.usedWoods[wname] || 0) + 1      // a natural trunk inside a piece's cells is not one of the village's woods
        var okWood = woods.some(function (x) { return x.replace('afc:', '') === wname })
        if (!okWood) {
          add(rec.otherWood, wname)
          if (rec.details.length < 20) rec.details.push(`wood ${id} where ${b[3]} should be (${woods.join('/')}), piece ${short} at ${pos.getX()},${pos.getY()},${pos.getZ()}`)
        }
      }
      if (/^tfc:wood\/chest\/|^afc:wood\/chest\/|^lootr:/.test(id)) {
        rec.chests++
        var be = level.getBlockEntity(pos)
        if (be) {
          var tag = be.saveWithoutMetadata(level.registryAccess())
          var lt = String(tag.getString('LootTable'))
          if (lt) { rec.lootChests++; rec.lootTables[lt] = (rec.lootTables[lt] || 0) + 1 }
        }
      }
      if (id.indexOf('framedblocks:') === 0 && sampleN < 600) {
        sampleN++
        rec.framed++
        var fbe = level.getBlockEntity(pos)
        if (fbe) {
          var ftag = fbe.saveWithoutMetadata(level.registryAccess())
          var camo = ftag.contains('camo') ? String(ftag.getCompound('camo').getCompound('state').getString('Name')) : '(none)'
          rec.camo[camo] = (rec.camo[camo] || 0) + 1
        } else {
          rec.camo['(no block entity)'] = (rec.camo['(no block entity)'] || 0) + 1
        }
      }
      // ground layer: floating over air, and how far from the natural surface (TFC's own base height at the column)
      if (b[1] === st.ground && !b[4] && id !== 'minecraft:air') {
        rec.columns++
        var gap = 0
        for (var dy = pos.getY() - 1; dy > pos.getY() - 24; dy--) {
          var below = level.getBlockState(new $StructTestBlockPos(pos.getX(), dy, pos.getZ()))
          if (!(below.isAir() || below.canBeReplaced()) || !below.getFluidState().isEmpty()) break
          gap++
        }
        if (gap >= 2) {
          rec.floatColumns++
          if (rec.details.length < 12) rec.details.push(`${tid} ${b[3]} @${b[0]},${b[1]},${b[2]} floats ${gap} at ${pos.getX()},${pos.getY()},${pos.getZ()}`)
        }
        if (gap > rec.maxGap) rec.maxGap = gap
        if (rec.columns % 6 === 0) {
          var h = generator.getBaseHeight(pos.getX(), pos.getZ(), $VtHeightmap.WORLD_SURFACE_WG, level, randomState)
          var off = pos.getY() - (h - 1)
          var g = rec.groundOffset
          if (off <= -3) g.buried3++; else if (off < 0) g.buried1++; else if (off === 0) g.flush++; else if (off <= 2) g.raised1++; else g.raised3++
        }
      }
    })
  })
  rec.blocks = counts
  rec.rockSet = Object.keys(rec.rocks).join('/')
  rec.woodSet = Object.keys(rec.woods).join(' | ')
  rec.leavesInBoxes = rec.kind === 'natural' ? vtLeaves(level, start) : -1
  // one rock and one set of woods per village: the built blocks (not the natural ground or trunks that show in a piece's cells) use no more
  var anchorNames = {}
  anchorWoods.forEach(function (x) { anchorNames[x.replace('afc:', '')] = true })
  rec.mixed = Object.keys(rec.usedWoods).length > Object.keys(anchorNames).length || Object.keys(rec.usedRocks).length > 1
  rec.camoTop = {}
  Object.keys(rec.camo).sort(function (a, b) { return rec.camo[b] - rec.camo[a] }).slice(0, 4).forEach(function (k) { rec.camoTop[k] = rec.camo[k] })
  // Easy NPCs standing in the village
  var aabb = new $StructTestAABB(box.minX() - 2, box.minY() - 8, box.minZ() - 2, box.maxX() + 3, box.maxY() + 16, box.maxZ() + 3)
  var near = level.getEntitiesOfClass($StructTestEntity, aabb)
  rec.npcs = []
  near.forEach(function (en) {
    var tag = en.saveWithoutId(new $StructTestCompound())
    if (!tag.contains('EasyNPCVersion')) return
    var offers = tag.getCompound('Offers')
    var recipes = offers.contains('Recipes', 9) ? offers.getList('Recipes', 10).size() : (offers.contains('Recipes', 10) ? offers.getCompound('Recipes').getList('Recipes', 10).size() : 0)
    // air between its feet and what it would stand on (0 = it stands)
    var fx = Math.floor(en.getX()), fy = Math.floor(en.getY()), fz = Math.floor(en.getZ())
    var drop = 0
    while (drop < 8) {
      var under = level.getBlockState(new $StructTestBlockPos(fx, fy - 1 - drop, fz))
      if (!(under.isAir() || under.canBeReplaced()) || !under.getFluidState().isEmpty()) break
      drop++
    }
    rec.npcs.push({ drop: drop, name: String(en.getName().getString()), uuid: String(tag.getUUID('UUID')), owner: tag.contains('Owner'), trades: recipes,
      invulnerable: tag.getBoolean('Invulnerable'), noGravity: tag.getBoolean('NoGravity') || en.isNoGravity(), at: [Math.floor(en.getX()), Math.floor(en.getY()), Math.floor(en.getZ())],
      dialogs: tag.getCompound('DialogData').getList('DialogDataSet', 10).size() })
  })
  rec.npcCount = rec.npcs.length
  rec.npcExpected = rec.npcPieces
  rec.npcNames = {}
  rec.npcs.forEach(function (n) { rec.npcNames[n.name] = (rec.npcNames[n.name] || 0) + 1 })
}

// The block a placeholder wood block becomes with the piece's woods (best first): tfc:wood/<v>/oak -> tfc:wood/<v>/<woods[0]>; ArborFirmaCraft
// woods swap the namespace; shingles keep rnr. null for anything that is not a ranked placeholder.
function vtWoodTarget(tid, woods) {
  var m = /^(tfc:wood\/[a-z_]+\/|rnr:wood\/shingles\/)(oak|spruce|birch)(_stairs|_slab)?$/.exec(tid)
  if (!m) return null
  var rank = m[2] === 'oak' ? 0 : m[2] === 'spruce' ? 1 : 2
  var w = woods[Math.min(rank, woods.length - 1)]
  var shape = m[3] || ''
  if (w.indexOf(':') > 0) {
    var parts = w.split(':')
    return m[1].indexOf('tfc:') === 0 ? parts[0] + ':' + m[1].substring(4) + parts[1] + shape : m[1] + parts[1] + shape
  }
  return m[1] + w + shape
}

// ---- acceptance census (--acceptance): every placement cell of each village set across its regions (those that pass the climate test are
// flagged), with the biome at its centre, what a guard of radius 48 and of radius 24 sees (heights and wet columns) and TFC's climate there,
// written to the results so that tools can try other climate windows, biome sets and guard limits without a server (docs/lived-in.md,
// *Tuning a village*)
function vtAcceptance(level, vj, results, check) {
  var setReg = level.registryAccess().registryOrThrow($StructTestRegistries.STRUCTURE_SET)
  var state = level.getChunkSource().getGeneratorState()
  var seed = level.getSeed()
  var sets = $VtMaterials.regionSets(level)
  results.villages.acceptance = {}
  vj.sets.forEach(function (s) {
    var set = structTestStructure(setReg, s.id)
    var placement = set.placement()
    var spacing = placement.spacing()
    var row = sets.get('pack:' + s.id)
    var x0 = 1e18, z0 = 1e18, x1 = -1e18, z1 = -1e18
    row.get('regions').forEach(function (name, v) {
      x0 = Math.min(x0, Number(v.get(2))); z0 = Math.min(z0, Number(v.get(3))); x1 = Math.max(x1, Number(v.get(4))); z1 = Math.max(z1, Number(v.get(5)))
    })
    var ax0 = Math.floor(x0 / 16 / spacing) - 1, ax1 = Math.floor(x1 / 16 / spacing) + 1
    var az0 = Math.floor(z0 / 16 / spacing) - 1, az1 = Math.floor(z1 / 16 / spacing) + 1
    var total = (ax1 - ax0 + 1) * (az1 - az0 + 1)
    var stride = Math.max(1, Math.ceil(Math.sqrt(total / vj.acceptanceCells)))
    var recs = []
    var inRegion = 0
    var climateOk = 0
    var considered = 0
    for (var a = ax0; a <= ax1; a += stride) {
      for (var b = az0; b <= az1; b += stride) {
        var c = placement.getPotentialStructureChunk(seed, a * spacing, b * spacing)
        considered++
        if (!placement.regionContains(c.x, c.z)) continue
        inRegion++
        var ok = placement.isStructureChunk(state, c.x, c.z)
        var bx = c.getMiddleBlockX()
        var bz = c.getMiddleBlockZ()
        var p48 = $VtMaterials.guardProbe(level, bx, bz, 48, 13)
        var p24 = $VtMaterials.guardProbe(level, bx, bz, 24, 13)
        var cl = $VtMaterials.climateAt(level, c.x, c.z)
        // every cell in a region, with whether the climate lets it through and the climate's numbers, so that tools can try other windows
        recs.push([c.x, c.z, String($VtMaterials.biomeAt(level, bx, bz)), Number(p48.get('min')), Number(p48.get('max')), Number(p48.get('wet')),
          Number(p24.get('min')), Number(p24.get('max')), Number(p24.get('wet')), ok ? 1 : 0,
          Math.round(Number(cl.get('temperature')) * 10) / 10, Math.round(Number(cl.get('rainfall'))), Math.round(Number(cl.get('groundwater'))), Number(cl.get('forest'))])
        if (ok) climateOk++
      }
    }
    results.villages.acceptance[s.id] = { spacing: spacing, stride: stride, considered: considered, inRegion: inRegion, climate: climateOk, cells: recs }
    console.info(`[structures-test] NOTE acceptance ${s.id}: ${considered} cells sampled (stride ${stride}), ${inRegion} in region, ${climateOk} with climate`)
  })
}

// ---- /locate: what the command's search (ChunkGenerator.findNearestMapStructure, radius 100 cells) answers from each test place, how long it
// takes, and whether the answer is a real village (its cell passes the placement, its chunk holds a valid start)
const $VtHolderSet = Java.loadClass('net.minecraft.core.HolderSet')
function vtLocate(level, vj, results, check) {
  var generator = level.getChunkSource().getGenerator()
  var structReg = level.registryAccess().registryOrThrow($StructTestRegistries.STRUCTURE)
  var setReg = level.registryAccess().registryOrThrow($StructTestRegistries.STRUCTURE_SET)
  var state = level.getChunkSource().getGeneratorState()
  results.villages.locate = []
  var bad = []
  var lines = []
  vj.sets.forEach(function (s) {
    var placement = structTestStructure(setReg, s.id).placement()
    s.structures.forEach(function (st, i) {
      if (i > 0) return                                   // the variants share the placement; the first one is enough for the search
      var holder = null
      structReg.holders().forEach(function (h) { if (String(h.key().location()) === 'pack:' + st.id) holder = h })
      var places = vj.places[s.culture] || []
      places.forEach(function (p) {
        var xz = $VtMaterials.blockOf(p[1], p[2])
        var t0 = Date.now()
        var res = generator.findNearestMapStructure(level, $VtHolderSet['direct(java.util.List)'](Java.loadClass('java.util.List').of(holder)), new $StructTestBlockPos(xz[0], 64, xz[1]), 100, false)
        var ms = Date.now() - t0
        var rec = { structure: st.id, from: p[0], ms: ms }
        if (res === null) {
          rec.found = false
          lines.push(`${st.id} from ${p[0]}: nothing within 100 cells (${ms} ms)`)
        } else {
          var pos = res.getFirst()
          var cx = pos.getX() >> 4
          var cz = pos.getZ() >> 4
          var d = Math.round(Math.hypot(pos.getX() - xz[0], pos.getZ() - xz[1]))
          var region = placement.regionContains(cx, cz)
          var placed = placement.isStructureChunk(state, cx, cz)
          var chunk = level.getChunk(cx, cz, $VtChunkStatus.STRUCTURE_STARTS)
          var real = false
          s.structures.forEach(function (o) {
            var start = chunk.getStartForStructure(structTestStructure(structReg, o.id))
            if (start !== null && start.isValid()) real = true
          })
          rec.found = true
          rec.at = [pos.getX(), pos.getZ()]
          rec.distance = d
          rec.region = region
          rec.climate = placed
          rec.real = real
          lines.push(`${st.id} from ${p[0]}: ${pos.getX()},${pos.getZ()} (${d} blocks, ${ms} ms)${region ? '' : ' OUTSIDE THE REGION'}${placed ? '' : ' climate fails'}${real ? '' : ' no start there'}`)
          if (!region) bad.push(`${st.id} from ${p[0]}: outside the region`)
          if (!real) bad.push(`${st.id} from ${p[0]}: ${pos.getX()},${pos.getZ()} holds no village`)
        }
        results.villages.locate.push(rec)
      })
    })
  })
  console.info(`[structures-test] NOTE locate: ${lines.join('; ')}`)
  check('/locate answers real villages inside the regions', bad.length === 0, bad.length ? bad.join('; ') : lines.length + ' searches')
}
