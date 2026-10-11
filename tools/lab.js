// Dev-only script of the worldgen feature lab (tools/lab.py). lab.py copies it into the lab server's
// local/kubejs/local_server_scripts; it is never part of the pack.
// It polls lab/job.json every few ticks, runs the job and writes lab/result-<id>.json (jobs and results are files, so nothing
// depends on the process that started the server). A "reload" job makes the script reload itself (kubejs reload
// server-scripts), which is how an edited copy of this file gets in without a restart: KubeJS does not allow eval.
// A handler may return labPending({ poll, finish, abort, timeoutMs }): the job then spans several ticks (poll runs every tick
// until it says true, then finish returns the result); chunks are generated in parallel that way, through tickets.
// Notes: every server script shares one top-level scope, so every top-level name here starts with Lab/lab/LAB (a const that
// another script also declares aborts this whole script). Function-local variables use var; Rhino rejects block-scoped
// const in callbacks that run repeatedly. The polling part comes first and uses nothing that can fail to load, so a broken
// edit further down can still be replaced by a reload job.

const LAB_DIR = 'lab/'
const LAB_POLL_TICKS = 4
const LAB_HEARTBEAT_TICKS = 100

var LAB = {
  ticks: 0, served: 0, lastId: 0, reloads: 0, startedAt: Date.now(), idleTicks: 0, stopping: false, reloadPending: false, pending: null,
  config: { boot_id: '', idle_minutes: 30 }, lastJob: null
}
var LAB_HANDLERS = {}

function labOut(msg) {
  console.info('[lab] ' + msg)
}

function labRead(path) {
  try {
    return JSON.parse(String(JsonIO.readString(path)))
  } catch (e) {
    return null
  }
}

function labWrite(path, obj) {
  JsonIO.write(path, JsonIO.parseRaw(JSON.stringify(obj)))
}

function labStatus(state) {
  labWrite(LAB_DIR + 'status.json', {
    state: state, boot_id: LAB.config.boot_id, ticks: LAB.ticks, served: LAB.served, last_id: LAB.lastId, reloads: LAB.reloads,
    uptime_s: Math.round((Date.now() - LAB.startedAt) / 1000), idle_s: Math.round(LAB.idleTicks / 20), busy: LAB.pending ? LAB.pending.job.kind : null,
    idle_limit_s: Math.round(LAB.config.idle_minutes * 60), now: Date.now(), last_job: LAB.lastJob
  })
}

function labPending(opts) {
  return { __pending: opts }
}

function labRun(server, job) {
  if (job.kind === 'ping') return { ok: true, pong: true }
  if (job.kind === 'stop') {
    LAB.stopping = true
    return { ok: true, stopping: true }
  }
  if (job.kind === 'reload') {
    LAB.reloadPending = true
    return { ok: true, reloading: true }
  }
  if (job.kind === 'cmd') {       // development: run a console command; its output lands in the lab's console log
    server.runCommand(job.command)
    return { ok: true }
  }
  if (job.kind === 'config') {
    for (var k in job.config) LAB.config[k] = job.config[k]
    return { ok: true, config: LAB.config }
  }
  var h = LAB_HANDLERS[job.kind]
  if (!h) return { ok: false, error: 'unknown job kind ' + job.kind }
  return h(server, job)
}

// Write the result of a finished job. Rhino's catch does not see everything (a RuntimeException thrown from its own natives
// goes past it), so callers run this from a finally block with whatever is known by then.
function labFinish(server, job, t0, res) {
  res.id = job.id
  res.ms = Date.now() - t0
  LAB.served++
  LAB.lastJob = { id: job.id, kind: job.kind, ms: res.ms, ok: res.ok !== false, at: Date.now() }
  try {
    labWrite(LAB_DIR + 'result-' + job.id + '.json', res)
  } catch (e2) {
    labWrite(LAB_DIR + 'result-' + job.id + '.json', { id: job.id, ok: false, error: 'result not serialisable: ' + e2 })
  }
  labStatus(LAB.stopping ? 'stopping' : 'ready')
  if (LAB.stopping) server.halt(false)
  if (LAB.reloadPending) {
    LAB.reloadPending = false
    labOut('reloading server scripts')
    server.runCommand('kubejs reload server-scripts')
  }
}

function labErr(job, e) {
  var res = { ok: false, error: String(e), stack: e && e.stack ? String(e.stack).split('\n').slice(0, 12).join('\n') : '' }
  labOut('job ' + job.id + ' (' + job.kind + ') failed: ' + res.error)
  return res
}

function labPoll(server) {
  var job = labRead(LAB_DIR + 'job.json')
  if (job === null || typeof job.id !== 'number' || job.id <= LAB.lastId) {
    LAB.idleTicks += LAB_POLL_TICKS
    if (LAB.idleTicks >= LAB.config.idle_minutes * 60 * 20 && !LAB.stopping) {
      labOut('idle for ' + LAB.config.idle_minutes + ' minutes; stopping')
      LAB.stopping = true
      labStatus('stopping')
      server.halt(false)
    }
    return
  }
  LAB.lastId = job.id
  LAB.idleTicks = 0
  var t0 = Date.now()
  var res = { ok: false, error: 'the job threw something the script cannot catch (see the lab console log)' }
  try {
    try {
      res = labRun(server, job)
      if (!res || typeof res !== 'object') res = { ok: false, error: 'the handler for ' + job.kind + ' returned nothing' }
      if (res.__pending) {
        var p = res.__pending
        LAB.pending = { job: job, t0: t0, p: p, deadline: t0 + (p.timeoutMs || 600000) }
        res = null
      }
    } catch (e) {
      res = labErr(job, e)
    }
  } finally {
    if (res !== null) labFinish(server, job, t0, res)
  }
}

function labPendingTick(server) {
  var pe = LAB.pending
  var res = { ok: false, error: 'the job threw something the script cannot catch (see the lab console log)' }
  try {
    try {
      if (Date.now() > pe.deadline) {
        LAB.pending = null
        if (pe.p.abort) pe.p.abort(server)
        res = { ok: false, error: 'timed out after ' + Math.round((Date.now() - pe.t0) / 1000) + ' s' + (pe.p.progress ? ' (' + pe.p.progress() + ')' : '') }
      } else if (pe.p.poll(server)) {
        LAB.pending = null
        res = pe.p.finish(server)
        if (!res || typeof res !== 'object') {
          res = { ok: false, error: 'the handler for ' + pe.job.kind + ' returned nothing' }
        } else if (res.__pending) {          // the next stage of the same job
          var np = res.__pending
          LAB.pending = { job: pe.job, t0: pe.t0, p: np, deadline: Date.now() + (np.timeoutMs || 600000) }
          res = null
        }
      } else {
        res = null
      }
    } catch (e) {
      LAB.pending = null
      try {
        if (pe.p.abort) pe.p.abort(server)
      } catch (e3) {
        labOut('abort failed: ' + e3)
      }
      res = labErr(pe.job, e)
    }
  } finally {
    if (res !== null) {
      LAB.pending = null
      labFinish(server, pe.job, pe.t0, res)
    }
  }
}

;(function () {
  var cfg = labRead(LAB_DIR + 'config.json')
  if (cfg) for (var k in cfg) LAB.config[k] = cfg[k]
  // a script reload keeps counting: pick up where the last status left off (same boot only)
  var st = labRead(LAB_DIR + 'status.json')
  if (st && st.boot_id === LAB.config.boot_id) {
    LAB.lastId = st.last_id || 0
    LAB.served = st.served || 0
    LAB.reloads = (st.reloads || 0) + 1
  }
  labOut('script loaded (boot ' + LAB.config.boot_id + ', load ' + LAB.reloads + ', idle shutdown after ' + LAB.config.idle_minutes + ' min)')
})()

ServerEvents.tick(event => {
  LAB.ticks++
  if (LAB.pending) labPendingTick(event.server)
  else if (LAB.ticks % LAB_POLL_TICKS === 0) labPoll(event.server)
  if ((LAB.ticks === 1 || LAB.ticks % LAB_HEARTBEAT_TICKS === 0) && !LAB.stopping) labStatus('ready')
})

// ====================================================================== from here on: the work (may fail to load; polling still runs)

function labClass(name) {
  try {
    return Java.loadClass(name)
  } catch (e) {
    console.info('[lab] class ' + name + ' is not available: ' + e)
    return null
  }
}

const $LabRL = labClass('net.minecraft.resources.ResourceLocation')
const $LabRegistries = labClass('net.minecraft.core.registries.Registries')
const $LabBuiltIn = labClass('net.minecraft.core.registries.BuiltInRegistries')
const $LabJsonOps = labClass('com.mojang.serialization.JsonOps')
const $LabPlacedFeature = labClass('net.minecraft.world.level.levelgen.placement.PlacedFeature')
const $LabPlacementContext = labClass('net.minecraft.world.level.levelgen.placement.PlacementContext')
const $LabOptional = labClass('java.util.Optional')
const $LabWorldgenRandom = labClass('net.minecraft.world.level.levelgen.WorldgenRandom')
const $LabXoroshiro = labClass('net.minecraft.world.level.levelgen.XoroshiroRandomSource')
const $LabBlockPos = labClass('net.minecraft.core.BlockPos')
const $LabMutablePos = labClass('net.minecraft.core.BlockPos$MutableBlockPos')
const $LabChunkPos = labClass('net.minecraft.world.level.ChunkPos')
const $LabBlock = labClass('net.minecraft.world.level.block.Block')
const $LabQuart = labClass('net.minecraft.core.QuartPos')
const $LabHeightmap = labClass('net.minecraft.world.level.levelgen.Heightmap$Types')
const $LabTicketType = labClass('net.minecraft.server.level.TicketType')
const $LabBiomeNoise = labClass('net.dries007.tfc.world.biome.BiomeNoise')

function labTryit(name, out, fn) {
  try {
    out[name] = fn()
  } catch (e) {
    out[name] = { error: String(e) }
  }
}

function labDecode(codec, level, text) {
  var el = JsonIO.parseRaw(text)
  var ops = level.registryAccess().createSerializationContext($LabJsonOps.INSTANCE)
  var r = codec.parse(ops, el)
  var e = r.error()
  if (e.isPresent()) return { error: String(e.get().message()) }
  return { value: r.result().get() }
}

function labBiomeFn(level) {
  var src = level.getChunkSource().getGenerator().getBiomeSource()
  var sampler = level.getChunkSource().randomState().sampler()
  return function (x, y, z) {
    return String(src.getNoiseBiome($LabQuart.fromBlock(x), $LabQuart.fromBlock(y), $LabQuart.fromBlock(z), sampler).unwrapKey().get().location())
  }
}

// block name of a state, cached by the state's global id (a JS object per Java object would defeat a cache keyed on objects)
function labNamer() {
  var names = {}
  return {
    id: function (state) {
      var id = $LabBlock.getId(state)
      if (names[id] === undefined) names[id] = String($LabBuiltIn.BLOCK.getKey(state.getBlock()))
      return id
    },
    name: function (id) {
      return names[id]
    }
  }
}

// ------------------------------------------------------------------ chunk helpers
// Chunks of a biome around a centre (chunk coordinates), nearest rings first. Chunkless: the biome source is asked at each chunk's middle column.
function labFindChunks(level, biomeId, cx0, cz0, wantN, box, maxRing) {
  var biomeAt = labBiomeFn(level)
  var out = []
  var lookups = 0
  if (box) maxRing = Math.max(Math.abs(box[0] - cx0), Math.abs(box[2] - cx0), Math.abs(box[1] - cz0), Math.abs(box[3] - cz0))
  function test(cx, cz) {
    if (box && (cx < box[0] || cx > box[2] || cz < box[1] || cz > box[3])) return
    lookups++
    if (biomeId === null || biomeAt(cx * 16 + 8, 64, cz * 16 + 8) === biomeId) out.push([cx, cz])
  }
  for (var r = 0; r <= maxRing; r++) {
    if (wantN > 0 && out.length >= wantN) break
    if (r === 0) {
      test(cx0, cz0)
      continue
    }
    for (var a = -r; a <= r; a++) {
      test(cx0 + a, cz0 - r)
      test(cx0 + a, cz0 + r)
    }
    for (var b = -r + 1; b <= r - 1; b++) {
      test(cx0 - r, cz0 + b)
      test(cx0 + r, cz0 + b)
    }
  }
  if (wantN > 0 && out.length > wantN) out.length = wantN
  return { chunks: out, lookups: lookups }
}

// the chunks plus their eight neighbours, once each: [[cx, cz], ...]
function labWithRing(chunks) {
  var seen = {}
  var all = []
  for (var i = 0; i < chunks.length; i++) {
    for (var dx = -1; dx <= 1; dx++) {
      for (var dz = -1; dz <= 1; dz++) {
        var k = (chunks[i][0] + dx) + ',' + (chunks[i][1] + dz)
        if (seen[k] === undefined) {
          seen[k] = true
          all.push([chunks[i][0] + dx, chunks[i][1] + dz])
        }
      }
    }
  }
  return all
}

// Ask for the chunks with tickets (they generate in parallel on the server's workers). Returns a handle for labChunksReady / labRelease.
function labRequestChunks(level, all) {
  var cache = level.getChunkSource()
  var pos = []
  for (var i = 0; i < all.length; i++) {
    var cp = new $LabChunkPos(all[i][0], all[i][1])
    cache.addRegionTicket($LabTicketType.FORCED, cp, 0, cp)
    pos.push(cp)
  }
  return { cache: cache, pos: pos, all: all, ready: 0 }
}

function labChunksReady(h) {
  var n = 0
  for (var i = 0; i < h.all.length; i++) {
    if (h.cache.getChunkNow(h.all[i][0], h.all[i][1]) !== null) n++
  }
  h.ready = n
  return n === h.all.length
}

function labRelease(h) {
  for (var i = 0; i < h.pos.length; i++) h.cache.removeRegionTicket($LabTicketType.FORCED, h.pos[i], 0, h.pos[i])
}

// ------------------------------------------------------------------ info and development probes
LAB_HANDLERS.info = function (server, job) {
  var out = { ok: true }
  var level = server.overworld()
  var gen = level.getChunkSource().getGenerator()
  labTryit('level', out, function () {
    return { seed: String(level.getSeed()), seaLevel: Number(level.getSeaLevel()), minY: Number(level.getMinBuildHeight()), maxY: Number(level.getMaxBuildHeight()), gen: String(gen) }
  })
  labTryit('registries', out, function () {
    var ra = level.registryAccess()
    return { configured: Number(ra.registryOrThrow($LabRegistries.CONFIGURED_FEATURE).size()), placed: Number(ra.registryOrThrow($LabRegistries.PLACED_FEATURE).size()),
      biome: Number(ra.registryOrThrow($LabRegistries.BIOME).size()), feature_types: Number($LabBuiltIn.FEATURE.size()), placement_types: Number($LabBuiltIn.PLACEMENT_MODIFIER_TYPE.size()) }
  })
  labTryit('biomes', out, function () {
    var ids = []
    level.registryAccess().registryOrThrow($LabRegistries.BIOME).keySet().forEach(function (k) { ids.push(String(k)) })
    ids.sort()
    return ids
  })
  return out
}

// the blocks of columns, as runs of one kind from the bottom up (development): { columns: [[x, z, y0, y1]] }
LAB_HANDLERS.peek = function (server, job) {
  var level = server.overworld()
  var namer = labNamer()
  var mp = new $LabMutablePos()
  var out = []
  for (var i = 0; i < job.columns.length; i++) {
    var c = job.columns[i]
    level.getChunk(c[0] >> 4, c[1] >> 4)
    var runs = []
    var last = null
    for (var y = c[2]; y <= c[3]; y++) {
      var nm = namer.name(namer.id(level.getBlockState(mp.set(c[0], y, c[1]))))
      if (nm === last) runs[runs.length - 1][2] = y
      else runs.push([nm, y, y])
      last = nm
    }
    out.push({ x: c[0], z: c[1], runs: runs, floor: Number(level.getHeight($LabHeightmap.OCEAN_FLOOR, c[0], c[1])) - 1, surface: Number(level.getHeight($LabHeightmap.WORLD_SURFACE, c[0], c[1])) - 1 })
  }
  return { ok: true, columns: out }
}

// ------------------------------------------------------------------ check: do the files parse?
// directory under worldgen/ -> [class, field]
const LAB_CODECS = {
  configured_feature: ['net.minecraft.world.level.levelgen.feature.ConfiguredFeature', 'DIRECT_CODEC'],
  placed_feature: ['net.minecraft.world.level.levelgen.placement.PlacedFeature', 'DIRECT_CODEC'],
  structure: ['net.minecraft.world.level.levelgen.structure.Structure', 'DIRECT_CODEC'],
  structure_set: ['net.minecraft.world.level.levelgen.structure.StructureSet', 'DIRECT_CODEC'],
  template_pool: ['net.minecraft.world.level.levelgen.structure.pools.StructureTemplatePool', 'DIRECT_CODEC'],
  processor_list: ['net.minecraft.world.level.levelgen.structure.templatesystem.StructureProcessorType', 'DIRECT_CODEC'],
  biome: ['net.minecraft.world.level.biome.Biome', 'DIRECT_CODEC']
}

LAB_HANDLERS.check = function (server, job) {
  var level = server.overworld()
  var codecs = {}
  var results = []
  for (var i = 0; i < job.items.length; i++) {
    var item = job.items[i]
    var rec = { id: item.id, kind: item.kind, file: item.file }
    results.push(rec)
    if (codecs[item.kind] === undefined) {
      codecs[item.kind] = null
      var spec = LAB_CODECS[item.kind]
      if (spec) {
        try {
          codecs[item.kind] = Java.loadClass(spec[0])[spec[1]]
        } catch (e) {
          codecs[item.kind] = null
        }
      }
    }
    if (!codecs[item.kind]) {
      rec.skipped = 'no codec for ' + item.kind
      continue
    }
    try {
      var d = labDecode(codecs[item.kind], level, item.json)
      if (d.error) rec.error = d.error
    } catch (e2) {
      rec.error = String(e2)
    }
  }
  return { ok: true, results: results }
}

// ------------------------------------------------------------------ place: run a placed feature the way chunk decoration does, in chunks of a biome
const LAB_TERRAIN_FREE = {
  'minecraft:rarity_filter': 1, 'minecraft:in_square': 1, 'minecraft:count': 1, 'minecraft:random_offset': 1, 'minecraft:fixed_placement': 1,
  'minecraft:noise_based_count': 1, 'minecraft:noise_threshold_count': 1, 'minecraft:height_range': 1, 'minecraft:biome': 1, 'tfc:ocean_ridge': 1
}

function labModifiers(placed) {
  var ml = placed.placement()
  var mods = []
  var stats = []
  for (var i = 0; i < ml.size(); i++) {
    var m = ml.get(i)
    mods.push(m)
    stats.push({ type: String($LabBuiltIn.PLACEMENT_MODIFIER_TYPE.getKey(m.type())), in: 0, out: 0 })
  }
  return { mods: mods, stats: stats }
}

// Run the modifier chain from a chunk's origin, as ChunkGenerator.applyBiomeDecoration does, and return the positions that reach the feature.
// stopAtTerrain: stop before the first modifier that needs terrain (the chunks need not exist then).
function labChain(ctx, wr, mods, stats, origin, stopAtTerrain) {
  var positions = [origin]
  for (var mi = 0; mi < mods.length; mi++) {
    if (stopAtTerrain && LAB_TERRAIN_FREE[stats[mi].type] !== 1) {
      stats[mi].blocked = (stats[mi].blocked || 0) + positions.length
      return { positions: positions, stopped: mi }
    }
    var next = []
    for (var pi = 0; pi < positions.length; pi++) {
      var lst = mods[mi].getPositions(ctx, wr, positions[pi]).toList()
      for (var li = 0, ln = lst.size(); li < ln; li++) next.push(lst.get(li))
    }
    stats[mi].in += positions.length
    stats[mi].out += next.length
    positions = next
    if (positions.length === 0) break
  }
  return { positions: positions, stopped: -1 }
}

function labChunkRandom(level, cx, cz, seed, step) {
  // like ChunkGenerator.applyBiomeDecoration: a WorldgenRandom over a Xoroshiro source (a legacy LCG source correlates a rare rarity roll with the rolls after it)
  var wr = new $LabWorldgenRandom(new $LabXoroshiro(1, 2))
  var ds = wr.setDecorationSeed(level.getSeed(), cx * 16, cz * 16)
  wr.setFeatureSeed(ds, seed, step)
  return wr
}

function labCountBlocks(level, chunks, wanted, ymin, ymax) {
  var total = {}
  var namer = labNamer()
  var minSec = level.getMinSection()
  var s0 = Math.max(0, (ymin >> 4) - minSec - 1)
  var s1 = Math.min(Number(level.getSectionsCount()) - 1, (ymax >> 4) - minSec + 1)
  for (var i = 0; i < chunks.length; i++) {
    var ch = level.getChunk(chunks[i][0], chunks[i][1])
    for (var si = s0; si <= s1; si++) {
      ch.getSection(si).getStates().count(function (state, count) {
        var nm = namer.name(namer.id(state))
        if (wanted[nm] === true) total[nm] = (total[nm] || 0) + Number(count)
      })
    }
  }
  return total
}

// Chunks come in batches (a window of thousands would not fit in memory at once): each batch is loaded with its neighbours,
// handled, restored and released before the next. perBatch(batch, all, loadMs, index, count) runs with the batch's chunks loaded;
// done() makes the result.
function labBatched(level, sel, batchSize, timeoutMs, perBatch, done) {
  var ordered = sel.slice()
  if (ordered.length > batchSize) ordered.sort(function (a, b) { return a[1] !== b[1] ? a[1] - b[1] : a[0] - b[0] })   // rows, so batches are strips
  var batches = []
  for (var i = 0; i < ordered.length; i += batchSize) batches.push(ordered.slice(i, i + batchSize))
  var bi = 0
  function stage() {
    var batch = batches[bi]
    var all = labWithRing(batch)
    var h = labRequestChunks(level, all)
    var t0 = Date.now()
    return labPending({
      poll: function () { return labChunksReady(h) },
      finish: function () {
        var loadMs = Date.now() - t0
        try {
          perBatch(batch, all, loadMs, bi, batches.length)
        } finally {
          labRelease(h)
        }
        bi++
        return bi < batches.length ? stage() : done()
      },
      abort: function () { labRelease(h) },
      progress: function () { return 'batch ' + (bi + 1) + '/' + batches.length + ': ' + h.ready + '/' + all.length + ' chunks loaded' },
      timeoutMs: timeoutMs
    })
  }
  return stage()
}

const LAB_CALLOUT = { 'minecraft:air': 1, 'minecraft:cave_air': 1, 'minecraft:void_air': 1, 'minecraft:water': 1 }

function labNewAcc() {
  return { reached: 0, placedTrue: 0, snaps: 0, identity: 0, changed: 0, written: {}, seen: {}, restored: 0, restoreBad: 0, restoreFirstBad: null,
    t: { place: 0, scan: 0, restore: 0, pre: 0, load: 0 }, batches: 0 }
}

// One batch: run the chain in each chunk with block writes captured, read what changed, count the neighbours, put the terrain back.
function labPlaceBatch(level, gen, placed, cm, ctx, cf, namer, sel, job, acc) {
  var t0 = Date.now()
  var snaps = level.capturedBlockSnapshots
  snaps.clear()
  level.captureBlockSnapshots = true
  try {
    for (var ci = 0; ci < sel.length; ci++) {
      var cx = sel[ci][0]
      var cz = sel[ci][1]
      var wr = labChunkRandom(level, cx, cz, job.seed, job.step)
      var origin = new $LabBlockPos(cx * 16, level.getMinBuildHeight(), cz * 16)
      var chain = labChain(ctx, wr, cm.mods, cm.stats, origin, false)
      acc.reached += chain.positions.length
      for (var qi = 0; qi < chain.positions.length; qi++) {
        if (cf.place(level, gen, wr, chain.positions[qi])) acc.placedTrue++
      }
    }
  } finally {
    level.captureBlockSnapshots = false
  }
  acc.t.place += Date.now() - t0

  // what changed: first original state per position, then what stands there now
  var t1 = Date.now()
  var n = Number(snaps.size())
  acc.snaps += n
  var origId = {}
  var uniq = []
  for (var i = 0; i < n; i++) {
    var s = snaps.get(i)
    var p = s.getPos()
    var x = p.getX()
    var y = p.getY()
    var z = p.getZ()
    var key = x + ',' + y + ',' + z
    if (origId[key] === undefined) {
      origId[key] = namer.id(s.getState())
      uniq.push([x, y, z, key])
    }
  }
  var mp = new $LabMutablePos()
  var written = acc.written
  var changed = []
  var batchNames = {}
  for (var u = 0; u < uniq.length; u++) {
    var q = uniq[u]
    var fid = namer.id(level.getBlockState(mp.set(q[0], q[1], q[2])))
    var oid = origId[q[3]]
    if (fid === oid) {
      acc.identity++
      continue
    }
    changed.push([q[0], q[1], q[2], fid, oid])
    var name = namer.name(fid)
    batchNames[name] = true
    var w = written[name]
    if (w === undefined) w = written[name] = { blocks: 0, chunk_set: {}, ymin: 1e9, ymax: -1e9, first: [], replaced: {}, top_columns: 0, neighbours: {}, touch_examples: {}, runs: {}, preexisting: 0 }
    w.blocks++
    w.chunk_set[(q[0] >> 4) + ',' + (q[2] >> 4)] = true
    if (q[1] < w.ymin) w.ymin = q[1]
    if (q[1] > w.ymax) w.ymax = q[1]
    if (w.first.length < job.first_n) w.first.push([q[0], q[1], q[2]])
    var on = namer.name(oid)
    w.replaced[on] = (w.replaced[on] || 0) + 1
    if (Number(level.getHeight($LabHeightmap.OCEAN_FLOOR, q[0], q[2])) - 1 === q[1]) w.top_columns++
  }
  acc.changed += changed.length

  // vertical runs: how many columns hold 1, 2, 3 ... blocks of a kind stacked (chimneys, spikes, pillars)
  var colsOf = {}
  for (var e = 0; e < changed.length; e++) {
    var en = namer.name(changed[e][3])
    var cmap = colsOf[en]
    if (cmap === undefined) cmap = colsOf[en] = {}
    var ck = changed[e][0] + ',' + changed[e][2]
    if (cmap[ck] === undefined) cmap[ck] = [changed[e][1]]
    else cmap[ck].push(changed[e][1])
  }
  for (var rn in colsOf) {
    var hist = written[rn].runs
    var cm2 = colsOf[rn]
    for (var ck2 in cm2) {
      var ys = cm2[ck2]
      ys.sort(function (a, b) { return a - b })
      var len = 1
      for (var yi = 1; yi <= ys.length; yi++) {
        if (yi < ys.length && ys[yi] === ys[yi - 1] + 1) {
          len++
        } else {
          hist[len] = (hist[len] || 0) + 1
          len = 1
        }
      }
    }
  }

  // what touches the written blocks (the six neighbours of each), up to a cap per block id over the whole run
  var cap = job.neighbour_cap
  for (var c = 0; c < changed.length; c++) {
    var chg = changed[c]
    var nm = namer.name(chg[3])
    var wv = written[nm]
    acc.seen[nm] = (acc.seen[nm] || 0) + 1
    if (acc.seen[nm] > cap) {
      wv.neighbours_sampled = true
      continue
    }
    for (var d = 0; d < 6; d++) {
      var nid = namer.id(level.getBlockState(mp.set(chg[0] + (d === 0 ? 1 : d === 1 ? -1 : 0), chg[1] + (d === 2 ? 1 : d === 3 ? -1 : 0), chg[2] + (d === 4 ? 1 : d === 5 ? -1 : 0))))
      var nn = namer.name(nid)
      wv.neighbours[nn] = (wv.neighbours[nn] || 0) + 1
      if (LAB_CALLOUT[nn] === 1) {         // where the air and the vanilla water are: a few examples per written kind
        var ex = wv.touch_examples[nn]
        if (ex === undefined) ex = wv.touch_examples[nn] = []
        if (ex.length < job.first_n) ex.push([chg[0], chg[1], chg[2]])
      }
    }
  }
  acc.t.scan += Date.now() - t1

  // put everything back, newest write first, and check
  var t2 = Date.now()
  for (var r = n - 1; r >= 0; r--) {
    var s2 = snaps.get(r)
    var p2 = s2.getPos()
    level.getChunkAt(p2).setBlockState(p2, s2.getState(), false)
  }
  snaps.clear()
  for (var v = 0; v < uniq.length; v++) {
    var qv = uniq[v]
    if (namer.id(level.getBlockState(mp.set(qv[0], qv[1], qv[2]))) !== origId[qv[3]]) {
      acc.restoreBad++
      if (acc.restoreFirstBad === null) acc.restoreFirstBad = [qv[0], qv[1], qv[2]]
    }
  }
  acc.restored += uniq.length
  acc.t.restore += Date.now() - t2

  // blocks of the written kinds that the chunks held anyway (counted after the restore, so they are not the feature's)
  var names = Object.keys(batchNames)
  if (names.length) {
    var t3 = Date.now()
    var ymin = 1e9
    var ymax = -1e9
    for (var k = 0; k < names.length; k++) {
      ymin = Math.min(ymin, written[names[k]].ymin)
      ymax = Math.max(ymax, written[names[k]].ymax)
    }
    var pre = labCountBlocks(level, sel, batchNames, ymin, ymax)
    for (var k2 = 0; k2 < names.length; k2++) written[names[k2]].preexisting += pre[names[k2]] || 0
    acc.t.pre += Date.now() - t3
  }
}

LAB_HANDLERS.place = function (server, job) {
  var level = server.overworld()
  var gen = level.getChunkSource().getGenerator()
  var out = { ok: true, timing: {} }
  var t0 = Date.now()
  var dec = labDecode($LabPlacedFeature.DIRECT_CODEC, level, job.feature.json)
  if (dec.error) return { ok: false, decode_error: dec.error }
  var placed = dec.value
  var cx0 = Math.floor(job.center[0] / 16)
  var cz0 = Math.floor(job.center[1] / 16)
  var found = labFindChunks(level, job.biome, cx0, cz0, job.chunks, job.box, job.max_ring)
  out.biome_lookups = found.lookups
  out.chunks_found = found.chunks.length
  out.timing.select_ms = Date.now() - t0
  if (!found.chunks.length) {
    out.ok = false
    out.error = 'no chunk of ' + job.biome + ' within ' + job.max_ring + ' chunks of the centre' + (job.box ? ' inside the window' : '')
    return out
  }
  out.chunk_sample = found.chunks.slice(0, 10)
  var cm = labModifiers(placed)
  var ctx = new $LabPlacementContext(level, gen, $LabOptional.of(placed))
  var cf = placed.feature().value()
  var namer = labNamer()
  var acc = labNewAcc()
  out.chunks_loaded = 0
  return labBatched(level, found.chunks, job.batch, job.timeout_ms,
    function (batch, all, loadMs, bi, nb) {
      acc.t.load += loadMs
      acc.batches++
      out.chunks_loaded += all.length
      labPlaceBatch(level, gen, placed, cm, ctx, cf, namer, batch, job, acc)
    },
    function () {
      out.modifiers = cm.stats
      out.positions_reached = acc.reached
      out.place_true = acc.placedTrue
      out.snapshots = acc.snaps
      out.identity_writes = acc.identity
      out.changed = acc.changed
      out.batches = acc.batches
      out.restore = { positions: acc.restored, mismatches: acc.restoreBad, first_mismatch: acc.restoreFirstBad }
      out.timing.load_ms = acc.t.load
      out.timing.place_ms = acc.t.place
      out.timing.scan_ms = acc.t.scan
      out.timing.restore_ms = acc.t.restore
      out.timing.preexisting_ms = acc.t.pre
      var result = {}
      for (var nm in acc.written) {
        var w = acc.written[nm]
        result[nm] = { blocks: w.blocks, chunks_with: Object.keys(w.chunk_set).length, y: [w.ymin, w.ymax], first: w.first, replaced: w.replaced,
          top_columns: w.top_columns, neighbours: w.neighbours, touch_examples: w.touch_examples, runs: w.runs, neighbours_sampled: w.neighbours_sampled === true, preexisting: w.preexisting }
      }
      out.written = result
      return out
    })
}

// ------------------------------------------------------------------ where: which chunks and positions pass the placement modifiers (no placing)
LAB_HANDLERS.where = function (server, job) {
  var level = server.overworld()
  var gen = level.getChunkSource().getGenerator()
  var out = { ok: true, timing: {} }
  var t0 = Date.now()
  var dec = labDecode($LabPlacedFeature.DIRECT_CODEC, level, job.feature.json)
  if (dec.error) return { ok: false, decode_error: dec.error }
  var placed = dec.value
  var cx0 = Math.floor(job.center[0] / 16)
  var cz0 = Math.floor(job.center[1] / 16)
  var found = labFindChunks(level, job.biome, cx0, cz0, job.chunks, job.box, job.max_ring)
  var sel = found.chunks
  out.biome_lookups = found.lookups
  out.chunks_found = sel.length
  out.timing.select_ms = Date.now() - t0
  if (!sel.length) {
    out.ok = false
    out.error = 'no chunk of ' + job.biome + ' within ' + job.max_ring + ' chunks of the centre' + (job.box ? ' inside the window' : '')
    return out
  }
  var seed = level.getSeed()
  var cm = labModifiers(placed)
  var ctx = new $LabPlacementContext(level, gen, $LabOptional.of(placed))
  var tally = { reached: 0, chunksReached: 0, stopped: -1 }

  function chainSome(chunks) {
    for (var ci = 0; ci < chunks.length; ci++) {
      var wr = labChunkRandom(level, chunks[ci][0], chunks[ci][1], job.seed, job.step)
      var origin = new $LabBlockPos(chunks[ci][0] * 16, level.getMinBuildHeight(), chunks[ci][1] * 16)
      var chain = labChain(ctx, wr, cm.mods, cm.stats, origin, !job.terrain)
      if (chain.stopped >= 0) tally.stopped = chain.stopped
      tally.reached += chain.positions.length
      if (chain.positions.length) tally.chunksReached++
    }
  }

  function bands() {
    if (!job.bands || !job.bands.length) return
    var counts = []
    for (var b = 0; b < job.bands.length; b++) counts.push(0)
    var sum = 0
    var minD = 1e18
    var maxD = -1e18
    for (var ci = 0; ci < sel.length; ci++) {
      var bx = sel[ci][0] * 16 + (job.band_at === 'corner' ? 0 : 8)
      var bz = sel[ci][1] * 16 + (job.band_at === 'corner' ? 0 : 8)
      var d = Number($LabBiomeNoise.getOceanRidgeWarpedEdgeDistanceAndScale(bx, bz, seed, false).x)
      sum += d
      if (d < minD) minD = d
      if (d > maxD) maxD = d
      for (var bi = 0; bi < job.bands.length; bi++) {
        if (d >= job.bands[bi][0] && d <= job.bands[bi][1]) counts[bi]++
      }
    }
    out.bands = { at: job.band_at, ranges: job.bands, chunks: counts, distance: { min: minD, max: maxD, mean: sum / sel.length } }
  }

  function finish() {
    bands()
    out.modifiers = cm.stats
    out.positions_reached = tally.reached
    out.chunks_reached = tally.chunksReached
    out.stopped_before = tally.stopped >= 0 ? cm.stats[tally.stopped].type : null
    out.terrain_free = {}
    for (var m = 0; m < cm.stats.length; m++) out.terrain_free[cm.stats[m].type] = LAB_TERRAIN_FREE[cm.stats[m].type] === 1
    return out
  }

  if (!job.terrain) {
    var t1 = Date.now()
    chainSome(sel)
    out.timing.chain_ms = Date.now() - t1
    return finish()
  }
  // with terrain the chunks have to exist: in batches, like place
  out.timing.load_ms = 0
  out.timing.chain_ms = 0
  return labBatched(level, sel, job.batch, job.timeout_ms,
    function (batch, all, loadMs) {
      out.timing.load_ms += loadMs
      var t2 = Date.now()
      chainSome(batch)
      out.timing.chain_ms += Date.now() - t2
    },
    finish)
}

// ------------------------------------------------------------------ ids of a registry
LAB_HANDLERS.ids = function (server, job) {
  var level = server.overworld()
  var key = $LabRegistries[job.registry]
  if (key === undefined) return { ok: false, error: 'no registry ' + job.registry + ' (BIOME, STRUCTURE, PLACED_FEATURE, CONFIGURED_FEATURE, STRUCTURE_SET, TEMPLATE_POOL, PROCESSOR_LIST ...)' }
  var ids = []
  level.registryAccess().registryOrThrow(key).keySet().forEach(function (k) { ids.push(String(k)) })
  ids.sort()
  return { ok: true, ids: ids }
}

// ------------------------------------------------------------------ structure: place a structure of any mod at chosen spots and read its pieces back
const $LabBoundingBox = labClass('net.minecraft.world.level.levelgen.structure.BoundingBox')
const $LabAABB = labClass('net.minecraft.world.phys.AABB')
const $LabEntity = labClass('net.minecraft.world.entity.Entity')
const $LabEntityRemoval = labClass('net.minecraft.world.entity.Entity$RemovalReason')

const LAB_VANILLA_OK = { 'minecraft:air': 1, 'minecraft:cave_air': 1, 'minecraft:void_air': 1, 'minecraft:water': 1, 'minecraft:lava': 1, 'minecraft:bedrock': 1 }

LAB_HANDLERS.structure = function (server, job) {
  var level = server.overworld()
  var gen = level.getChunkSource().getGenerator()
  var out = { ok: true, timing: {}, spots: [] }
  var reg = level.registryAccess().registryOrThrow($LabRegistries.STRUCTURE)
  var structure = reg.get($LabRL.parse(job.structure))
  if (structure === null) return { ok: false, error: 'no structure ' + job.structure + ' in the lab\'s registries (lab.py ids STRUCTURE lists them; a structure added or changed since the lab booted needs lab.py restart)' }
  var t0 = Date.now()
  // 1. the starts, chunkless (the structure asks the generator for heights, not the chunks)
  var starts = []
  for (var i = 0; i < job.spots.length; i++) {
    var sp = job.spots[i]
    var cp = new $LabChunkPos(sp[0] >> 4, sp[1] >> 4)
    var spot = { x: sp[0], z: sp[1] }
    out.spots.push(spot)
    try {
      var start = structure.generate(level.registryAccess(), gen, gen.getBiomeSource(), level.getChunkSource().randomState(), level.getStructureManager(), level.getSeed() + job.seed, cp, 0, level, function (h) { return true })
      if (start.isValid()) {
        spot.placed = true
        var box = start.getBoundingBox()
        spot.box = [box.minX(), box.minY(), box.minZ(), box.maxX(), box.maxY(), box.maxZ()]
        spot.pieces = Number(start.getPieces().size())
        starts.push({ spot: spot, start: start, box: box })
      } else {
        spot.placed = false
        spot.reason = 'the structure produced no start here (its own checks: biome, terrain, water, height)'
      }
    } catch (e) {
      spot.placed = false
      spot.reason = String(e)
    }
  }
  out.timing.generate_ms = Date.now() - t0
  if (!starts.length) return out
  // 2. the chunks the starts cover, with one chunk around, in one go
  var seen = {}
  var all = []
  for (var si = 0; si < starts.length; si++) {
    var b = starts[si].box
    for (var cx = (b.minX() >> 4) - 1; cx <= (b.maxX() >> 4) + 1; cx++) {
      for (var cz = (b.minZ() >> 4) - 1; cz <= (b.maxZ() >> 4) + 1; cz++) {
        var k = cx + ',' + cz
        if (seen[k] === undefined) {
          seen[k] = true
          all.push([cx, cz])
        }
      }
    }
  }
  out.chunks_loaded = all.length
  var h = labRequestChunks(level, all)
  var tLoad = Date.now()
  return labPending({
    poll: function () { return labChunksReady(h) },
    finish: function () {
      out.timing.load_ms = Date.now() - tLoad
      try {
        labStructureRun(level, gen, starts, job, out)
      } finally {
        labRelease(h)
      }
      return out
    },
    abort: function () { labRelease(h) },
    progress: function () { return h.ready + '/' + all.length + ' chunks loaded' },
    timeoutMs: job.timeout_ms
  })
}

// Put the captured writes back, newest first, and check every position against its first original state.
function labRestore(level, snaps, namer) {
  var n = Number(snaps.size())
  var origId = {}
  var uniq = []
  for (var i = 0; i < n; i++) {
    var s = snaps.get(i)
    var p = s.getPos()
    var key = p.getX() + ',' + p.getY() + ',' + p.getZ()
    if (origId[key] === undefined) {
      origId[key] = namer.id(s.getState())
      uniq.push([p.getX(), p.getY(), p.getZ(), key])
    }
  }
  for (var r = n - 1; r >= 0; r--) {
    var s2 = snaps.get(r)
    var p2 = s2.getPos()
    level.getChunkAt(p2).setBlockState(p2, s2.getState(), false)
  }
  snaps.clear()
  var mp = new $LabMutablePos()
  var bad = 0
  for (var v = 0; v < uniq.length; v++) {
    if (namer.id(level.getBlockState(mp.set(uniq[v][0], uniq[v][1], uniq[v][2]))) !== origId[uniq[v][3]]) bad++
  }
  return { snapshots: n, positions: uniq.length, mismatches: bad }
}

function labStructureRun(level, gen, starts, job, out) {
  var namer = labNamer()
  var mp = new $LabMutablePos()
  var snaps = level.capturedBlockSnapshots
  var tAll = Date.now()
  for (var si = 0; si < starts.length; si++) {
    var st = starts[si]
    var spot = st.spot
    var b = st.box
    var aabb = new $LabAABB(b.minX() - 2, b.minY() - 2, b.minZ() - 2, b.maxX() + 3, b.maxY() + 3, b.maxZ() + 3)
    var before = {}
    var existing = level.getEntitiesOfClass($LabEntity, aabb)
    for (var ei = 0; ei < existing.size(); ei++) before[String(existing.get(ei))] = true
    snaps.clear()
    level.captureBlockSnapshots = true
    var tp = Date.now()
    try {
      for (var cx = b.minX() >> 4; cx <= b.maxX() >> 4; cx++) {
        for (var cz = b.minZ() >> 4; cz <= b.maxZ() >> 4; cz++) {
          level.getChunk(cx, cz)
          st.start.placeInChunk(level, level.structureManager(), gen, level.getRandom(),
            new $LabBoundingBox(cx << 4, level.getMinBuildHeight(), cz << 4, (cx << 4) + 15, level.getMaxBuildHeight(), (cz << 4) + 15), new $LabChunkPos(cx, cz))
        }
      }
    } finally {
      level.captureBlockSnapshots = false
    }
    spot.place_ms = Date.now() - tp
    spot.writes = Number(snaps.size())

    // what stands in the pieces' boxes now (the boxes also hold terrain: water, rock, air)
    var counts = {}
    var cells = 0
    var water = 0
    var fluid = 0
    var air = 0
    var vanilla = {}
    var containers = {}
    var firstPos = {}
    var pieces = st.start.getPieces()
    var done = {}
    for (var pi = 0; pi < pieces.size(); pi++) {
      var pb = pieces.get(pi).getBoundingBox()
      for (var x = pb.minX(); x <= pb.maxX(); x++) {
        for (var z = pb.minZ(); z <= pb.maxZ(); z++) {
          for (var y = pb.minY(); y <= pb.maxY(); y++) {
            var key = x + ',' + y + ',' + z
            if (done[key] === true) continue
            done[key] = true
            cells++
            var state = level.getBlockState(mp.set(x, y, z))
            var nm = namer.name(namer.id(state))
            counts[nm] = (counts[nm] || 0) + 1
            if (nm === 'minecraft:water') water++
            else if (nm.indexOf('tfc:fluid/') === 0) fluid++
            else if (nm === 'minecraft:air' || nm === 'minecraft:cave_air') air++
            else if (nm.indexOf('minecraft:') === 0 && LAB_VANILLA_OK[nm] !== 1) {
              vanilla[nm] = (vanilla[nm] || 0) + 1
              if (firstPos[nm] === undefined) firstPos[nm] = [x, y, z]
            }
            if (state.hasBlockEntity()) {
              var be = level.getBlockEntity(mp)
              if (be !== null) {
                var tag = be.saveWithoutMetadata(level.registryAccess())
                var table = tag.contains('LootTable') ? String(tag.getString('LootTable')) : null
                var ck = nm + (table ? ' <- ' + table : (tag.contains('Items') ? ' (items set)' : ''))
                containers[ck] = (containers[ck] || 0) + 1
              }
            }
          }
        }
      }
    }
    spot.cells = cells
    spot.water_cells = water
    spot.fluid_cells = fluid
    spot.air_cells = air
    var top = Object.keys(counts).sort(function (a, c) { return counts[c] - counts[a] }).slice(0, job.top_n)
    spot.blocks = {}
    for (var t = 0; t < top.length; t++) spot.blocks[top[t]] = counts[top[t]]
    spot.vanilla_left = vanilla
    spot.vanilla_first = firstPos
    spot.containers = containers

    // entities the structure added go, then the blocks
    var after = level.getEntitiesOfClass($LabEntity, aabb)
    var removed = 0
    for (var ai = 0; ai < after.size(); ai++) {
      var en = after.get(ai)
      if (before[String(en)] !== true) {
        en.remove($LabEntityRemoval.DISCARDED)
        removed++
      }
    }
    spot.entities_added = removed
    spot.restore = labRestore(level, snaps, namer)
  }
  out.timing.place_ms = Date.now() - tAll
}
