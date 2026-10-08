// Dev-only: records what the structure skin (pack_world) does while Chunky generates an area. Run by tools/structure_mods/measure.py,
// copied into the test server's local/kubejs/local_server_scripts for one run; never part of the pack.
// Writes local/structure-mods/stats.json every 5 seconds: the skin's counters, the blocks structures wrote that it has no rule for,
// and the per-structure metrics (blocks before/after, ground columns, floating columns before/after the foundation).
const $SMApi = Java.loadClass('pack.world.api.PackWorldApi')
const SM_CENSUS = /*CENSUS*/ true /*END*/   // measure.py --no-census sets false (the census costs generation speed)

function smToJs(value) {
  // Java maps/numbers -> plain JS so JsonIO can write them
  if (value === null || value === undefined) return null
  if (typeof value === 'number' || typeof value === 'string' || typeof value === 'boolean') return value
  if (typeof value.entrySet === 'function') {
    var out = {}
    var it = value.entrySet().iterator()
    while (it.hasNext()) {
      var e = it.next()
      out[String(e.getKey())] = smToJs(e.getValue())
    }
    return out
  }
  var n = Number(value)
  return isNaN(n) ? String(value) : n
}

function smDump(server) {
  JsonIO.write('local/structure-mods/stats.json', {
    config: smToJs($SMApi.skinConfig()),
    stats: smToJs($SMApi.skinStats()),
    unmapped: smToJs($SMApi.skinUnmapped()),
    metrics: smToJs($SMApi.skinMetrics()),
    tick: Number(server.getTickCount())
  })
}

ServerEvents.loaded(event => {
  $SMApi.skinReset()
  $SMApi.skinCensus(SM_CENSUS)
  console.info('[structure-mods] census ' + SM_CENSUS + '; skin ' + $SMApi.skinConfig())
})

ServerEvents.tick(event => {
  if (event.server.getTickCount() % 100 === 0) smDump(event.server)
})
