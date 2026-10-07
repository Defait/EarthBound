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
  'minecraft:ice': 1, 'minecraft:packed_ice': 1, 'minecraft:blue_ice': 1, 'minecraft:snow_block': 1, 'minecraft:cobweb': 1, 'minecraft:hanging_roots': 1 }

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
    structTestPalette(STRUCT_TEST_JOB, check, blockExists)
    // natural starts first: the /place copies would overwrite natural ones that happen to lie in the same spots
    structTestNatural(level, STRUCT_TEST_JOB, results, check, idAt)
    if (!STRUCT_TEST_JOB.naturalOnly) structTestPlacements(server, level, STRUCT_TEST_JOB, results, check, idAt)
    structTestNpcs(server, level, STRUCT_TEST_JOB, results, check)
    structTestLoot(server, level, STRUCT_TEST_JOB, results, check)
    structTestSites(level, results, check)
    structTestDensity(level, STRUCT_TEST_JOB, results)
  } catch (e) {
    check('script', false, String(e) + (e && e.stack ? ' ' + String(e.stack).replace(/\s+/g, ' ') : ''))
  }
  JsonIO.write(STRUCT_TEST_OUT + 'results.json', results)
  console.info(`[structures-test] done: ${failures} failed`)
})

// Every placeholder id of every template, through the processor's own mapping, for every rock, wood, soil and sand.
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
  var anchor = pieces.get(0).getPosition()
  var mat = $StructTestApi.materialsAt(level, anchor.getX(), anchor.getY(), anchor.getZ())
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
