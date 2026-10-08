// Dev-only check of villager and wandering trader trades (docs/design.md: "Villagers"), run by tools/villagers_test.py.
// Copied into the test server's local/kubejs/local_server_scripts for one run; never part of the pack.
// Note: function-local variables use var; Rhino rejects block-scoped const in callbacks that run repeatedly.
const $VTestRL = Java.loadClass('net.minecraft.resources.ResourceLocation')
const $VTestBuiltIn = Java.loadClass('net.minecraft.core.registries.BuiltInRegistries')
const $VTestRegistries = Java.loadClass('net.minecraft.core.registries.Registries')
const $VTestRK = Java.loadClass('net.minecraft.resources.ResourceKey')
const $VTestEntityType = Java.loadClass('net.minecraft.world.entity.EntityType')
const $VTestVillagerTrades = Java.loadClass('net.minecraft.world.entity.npc.VillagerTrades')
const $VTestVillagerData = Java.loadClass('net.minecraft.world.entity.npc.VillagerData')
const $VTestVillagerType = Java.loadClass('net.minecraft.world.entity.npc.VillagerType')
const $VTestInteger = Java.loadClass('java.lang.Integer')
const $VTestHashMap = Java.loadClass('java.util.HashMap')
const $VTestAbstractVillager = Java.loadClass('net.minecraft.world.entity.npc.AbstractVillager')
const $VTestMerchantOffer = Java.loadClass('net.minecraft.world.item.trading.MerchantOffer')
const $VTestMerchantOffers = Java.loadClass('net.minecraft.world.item.trading.MerchantOffers')
const $VTestItemCost = Java.loadClass('net.minecraft.world.item.trading.ItemCost')
const $VTestItemStack = Java.loadClass('net.minecraft.world.item.ItemStack')
const $VTestItems = Java.loadClass('net.minecraft.world.item.Items')
const $VTestBlockPos = Java.loadClass('net.minecraft.core.BlockPos')
const $VTestHeightmap = Java.loadClass('net.minecraft.world.level.levelgen.Heightmap$Types')
const $VTestPlaceSettings = Java.loadClass('net.minecraft.world.level.levelgen.structure.templatesystem.StructurePlaceSettings')
const $VTestCompound = Java.loadClass('net.minecraft.nbt.CompoundTag')
const $VTestNbtOps = Java.loadClass('net.minecraft.nbt.NbtOps')
const $VTestAABB = Java.loadClass('net.minecraft.world.phys.AABB')
const $VTestVec3 = Java.loadClass('net.minecraft.world.phys.Vec3')
const $VTestLootParams = Java.loadClass('net.minecraft.world.level.storage.loot.LootParams$Builder')
const $VTestLootParamSets = Java.loadClass('net.minecraft.world.level.storage.loot.parameters.LootContextParamSets')
const $VTestLootContextParams = Java.loadClass('net.minecraft.world.level.storage.loot.parameters.LootContextParams')
const $VTestPriority = Java.loadClass('net.neoforged.bus.api.EventPriority')
const $VTestVillagerTradesEvent = Java.loadClass('net.neoforged.neoforge.event.village.VillagerTradesEvent')
const $VTestWandererTradesEvent = Java.loadClass('net.neoforged.neoforge.event.village.WandererTradesEvent')

// Replaced by the Python tool.
const VTEST_JOB = /*JOB*/ { table: { professions: {}, wandering_trader: { generic: [], rare: [] }, xp: {}, wanderer_eras: {} }, deny: [], caps: {}, allow: [], steps: null, levelEra: {}, templates: [], earlyMetal: '$^' } /*END*/

const VTEST_OUT = 'local/villagers-test/'

// The lists NeoForge hands the event (vanilla's plus any mod's), before the pack's startup script replaces them (it listens at the
// lowest priority, this at the highest). Server scripts are loaded before the data load that posts the events.
var vtBefore = {}
function vtCopy(list) {
  var out = []
  for (var i = 0; i < list.size(); i++) out.push(list.get(i))
  return out
}
// (An exception in a listener would stop the server from starting, so these catch. fastutil's Int2ObjectMap can't be asked from
// KubeJS's Rhino directly, hence the HashMap copies: see startup_scripts/villager_trades.js.)
var vtBeforeErrors = []
NativeEvents.onEvent($VTestPriority.HIGHEST, $VTestVillagerTradesEvent, event => {
  try {
    var prof = String($VTestBuiltIn.VILLAGER_PROFESSION.getKey(event.getType()))
    var trades = new $VTestHashMap(event.getTrades())
    for (var l = 1; l <= 5; l++) vtBefore[`${prof}|${l}`] = vtCopy(trades.get($VTestInteger.valueOf(l)))
  } catch (e) {
    vtBeforeErrors.push(String(e))
  }
})
NativeEvents.onEvent($VTestPriority.HIGHEST, $VTestWandererTradesEvent, event => {
  try {
    vtBefore['wandering_trader|generic'] = vtCopy(event.getGenericTrades())
    vtBefore['wandering_trader|rare'] = vtCopy(event.getRareTrades())
  } catch (e) {
    vtBeforeErrors.push(String(e))
  }
})

ServerEvents.loaded(event => {
  var server = event.server
  var level = server.overworld()
  var results = { checks: [], stats: {}, vanilla: {}, live: {}, templates: [], loot: {} }
  var failures = 0
  function check(name, ok, detail) {
    if (!ok) failures++
    results.checks.push({ name: name, ok: !!ok, detail: String(detail) })
    console.info(`[villagers-test] ${ok ? 'PASS' : 'FAIL'} ${name}: ${detail}`)
  }
  function stat(name, value) {
    results.stats[name] = value
    console.info(`[villagers-test] STAT ${name}: ${typeof value === 'object' ? JSON.stringify(value) : value}`)
  }
  var ctx = { server: server, level: level, results: results, check: check, stat: stat, job: VTEST_JOB, expected: vtExpected(VTEST_JOB) }
  ;[['vanilla before', vtVanilla], ['stack sizes', vtStacks], ['spawned villagers', vtSpawned], ['wandering traders', vtWanderers],
    ['synthetic baked offers', vtSynthetic], ['structure templates', vtTemplates], ['loot of golems, illagers and gifts', vtLoot]].forEach(function (s) {
    try {
      s[1](ctx)
    } catch (e) {
      check(s[0], false, String(e) + (e && e.stack ? ' ' + String(e.stack).replace(/\s+/g, ' ').slice(0, 600) : ''))
    }
  })
  JsonIO.write(VTEST_OUT + 'results.json', results)
  console.info(`[villagers-test] done: ${failures} failed`)
})

// ---------------------------------------------------------------------------------------------------------- helpers
function vtItemId(stack) {
  return String($VTestBuiltIn.ITEM.getKey(stack.getItem()))
}

function vtSigParts(buy, buyN, buyB, buyBN, sell, sellN, uses, xp) {
  return `${buy}x${buyN}` + (buyB ? `+${buyB}x${buyBN}` : '') + `>${sell}x${sellN}|${uses}|${xp}`
}

function vtOfferSig(offer) {
  var a = offer.getBaseCostA()
  var b = offer.getCostB()   // (an empty stack, the absent second price, reads as null in KubeJS's Rhino)
  var r = offer.getResult()
  var hasB = b != null && !b.isEmpty()
  return vtSigParts(vtItemId(a), a.getCount(), hasB ? vtItemId(b) : null, hasB ? b.getCount() : 0, vtItemId(r), r.getCount(), offer.getMaxUses(), offer.getXp())
}

function vtTradeSig(trade, xp) {
  return vtSigParts(trade.buy[0], trade.buy[1], trade.buy_b ? trade.buy_b[0] : null, trade.buy_b ? trade.buy_b[1] : 0, trade.sell[0], trade.sell[1],
    trade.max_uses, trade.xp != null ? trade.xp : xp)
}

// {'minecraft:farmer|2': [sig, ...], 'wandering_trader|generic': [...]}
function vtExpected(job) {
  var out = {}
  Object.keys(job.table.professions).forEach(function (p) {
    for (var l = 1; l <= 5; l++) {
      out[`${p}|${l}`] = (job.table.professions[p][String(l)] || []).map(function (t) { return vtTradeSig(t, job.table.xp[String(l)]) })
    }
  })
  out['wandering_trader|generic'] = job.table.wandering_trader.generic.map(function (t) { return vtTradeSig(t, 0) })
  out['wandering_trader|rare'] = job.table.wandering_trader.rare.map(function (t) { return vtTradeSig(t, 0) })
  return out
}

function vtProfessions() {
  var ids = []
  $VTestBuiltIn.VILLAGER_PROFESSION.keySet().forEach(function (rl) { ids.push(String(rl)) })
  return ids.sort()
}

function vtProfession(id) {
  return $VTestBuiltIn.VILLAGER_PROFESSION.get($VTestRL.parse(id))
}

function vtVillager(level, profId, lvl) {
  var v = $VTestEntityType.VILLAGER.create(level)
  v.setVillagerData(new $VTestVillagerData($VTestVillagerType.PLAINS, vtProfession(profId), lvl))
  return v
}

// The rules every result and price must meet, by the real item (so a rename can't hide behind the file's ids).
function vtRules(ctx, where, offer, eraName) {
  var job = ctx.job
  var deny = vtDeny(job)
  var problems = []
  var early = new RegExp(job.earlyMetal)
  var stacks = [['sells', offer.getResult()], ['buys', offer.getBaseCostA()], ['buys', offer.getCostB()]]
  stacks.forEach(function (pair) {
    var role = pair[0]
    var stack = pair[1]
    if (stack == null || stack.isEmpty()) return
    var id = vtItemId(stack)
    if (id === 'minecraft:air') problems.push(`${where}: ${role} air`)
    if (id.endsWith(':emerald')) problems.push(`${where}: ${role} ${id}`)
    if (deny.some(function (r) { return r.test(id) })) problems.push(`${where}: ${role} ${id} is on the deny-list`)
    if (eraName !== 'bronze' && early.test(id)) problems.push(`${where}: ${role} ${id} is bronze-age or later in a ${eraName} trade`)
    if (stack.getCount() > stack.getMaxStackSize()) problems.push(`${where}: ${role} ${stack.getCount()} x ${id} is more than a stack (${stack.getMaxStackSize()})`)
    if (stack.isEnchanted() || id === 'minecraft:enchanted_book') problems.push(`${where}: ${role} an enchanted ${id}`)
    if (role === 'sells' && job.steps) {
      var step = job.steps[id]
      var cap = job.caps[eraName]
      if (step === undefined) problems.push(`${where}: ${id} is not in the checked item list`)
      else if (step === null) {
        if (!job.allow.some(function (a) { return new RegExp(a).test(id) })) problems.push(`${where}: sells ${id}, unreachable for the progression checker`)
      } else if (step > cap) problems.push(`${where}: sells ${id} (step ${step}) above the ${eraName} cap ${cap}`)
    }
  })
  return problems
}

var vtDenyCache = null
function vtDeny(job) {
  if (vtDenyCache == null) vtDenyCache = job.deny.map(function (p) { return new RegExp(p) })
  return vtDenyCache
}

function vtDiff(live, expected) {
  var missing = expected.filter(function (s) { return live.indexOf(s) < 0 })
  var extra = live.filter(function (s) { return expected.indexOf(s) < 0 })
  return { missing: missing, extra: extra }
}

// ---------------------------------------------------------------------------------------------------------- vanilla before
// The lists recorded above, asked what they would have sold.
function vtVanilla(ctx) {
  var keys = Object.keys(vtBefore)
  if (keys.length === 0) {
    ctx.check('vanilla trades were recorded', false, 'the HIGHEST-priority listener of this script saw no VillagerTradesEvent (the server scripts loaded after the data load?)' + (vtBeforeErrors.length ? '; errors: ' + vtBeforeErrors.join('; ') : ''))
    return
  }
  var level = ctx.level
  var sampler = $VTestEntityType.VILLAGER.create(level)
  var deny = vtDeny(ctx.job)
  var total = 0, denied = 0, emerald = 0, enchanted = 0, maps = 0, errors = 0, modded = 0
  var classes = {}
  var perProfession = {}
  keys.sort().forEach(function (key) {
    var list = vtBefore[key]
    var prof = key.split('|')[0]
    for (var i = 0; i < list.length; i++) {
      var listing = list[i]
      var cls = String(listing).split('@')[0]   // (KubeJS hides getClass)
      classes[cls] = (classes[cls] || 0) + 1
      if (cls.indexOf('net.minecraft.world.entity.npc.VillagerTrades$') !== 0) modded++
      var rec = { key: key, cls: cls.split('$').pop(), sells: [], buys: [], emerald: false, enchanted: false, map: false, error: false }
      if (cls.indexOf('TreasureMap') >= 0) {
        rec.map = true   // asking would search the world for a structure
      } else {
        for (var n = 0; n < 8; n++) {
          try {
            var offer = listing.getOffer(sampler, level.getRandom())
            if (offer == null) continue
            var r = offer.getResult()
            var rid = vtItemId(r)
            if (rec.sells.indexOf(rid) < 0) rec.sells.push(rid)
            ;[offer.getBaseCostA(), offer.getCostB()].forEach(function (c) {
              if (c != null && !c.isEmpty() && rec.buys.indexOf(vtItemId(c)) < 0) rec.buys.push(vtItemId(c))
            })
            if (r.isEnchanted() || rid === 'minecraft:enchanted_book') rec.enchanted = true
          } catch (e) {
            rec.error = true
          }
        }
      }
      rec.emerald = rec.sells.concat(rec.buys).some(function (id) { return id === 'minecraft:emerald' })
      rec.denied = rec.sells.filter(function (id) { return deny.some(function (rx) { return rx.test(id) }) })
      total++
      if (rec.denied.length) denied++
      if (rec.emerald) emerald++
      if (rec.enchanted) enchanted++
      if (rec.map) maps++
      if (rec.error) errors++
      var pp = perProfession[prof] || (perProfession[prof] = { listings: 0, denied: 0 })
      pp.listings++
      if (rec.denied.length) pp.denied++
      ;(results_vanilla(ctx, key)).push(rec)
    }
  })
  ctx.stat('vanilla listings', total)
  ctx.stat('vanilla listings with a deny-listed result', denied)
  ctx.stat('vanilla listings using emeralds', emerald)
  ctx.stat('vanilla enchanted results', enchanted)
  ctx.stat('vanilla map listings', maps)
  ctx.stat('vanilla listings from other mods', modded)
  ctx.stat('vanilla listing classes', classes)
  ctx.stat('vanilla per profession', perProfession)
  ctx.check('vanilla trades were recorded', total > 0, `${total} listings (${errors} could not be sampled)`)
}

function results_vanilla(ctx, key) {
  return ctx.results.vanilla[key] || (ctx.results.vanilla[key] = [])
}

// ---------------------------------------------------------------------------------------------------------- stack sizes
// A price or result bigger than its item's stack can't be offered (the trading screen has one slot per price), and the startup
// script rejects it: list every one.
function vtStacks(ctx) {
  var bad = []
  var n = 0
  var sizes = {}
  function look(where, pair) {
    if (!pair) return
    var rl = $VTestRL.tryParse(String(pair[0]))
    if (rl == null || !$VTestBuiltIn.ITEM.containsKey(rl)) {
      bad.push(`${where}: no item ${pair[0]}`)
      return
    }
    var max = new $VTestItemStack($VTestBuiltIn.ITEM.get(rl), 1).getMaxStackSize()
    sizes[pair[0]] = Number(max)
    n++
    if (pair[1] > max) bad.push(`${where}: ${pair[0]} x${pair[1]} but a stack holds ${max}`)
  }
  var table = ctx.job.table
  Object.keys(table.professions).forEach(function (p) {
    for (var l = 1; l <= 5; l++) {
      table.professions[p][String(l)].forEach(function (t, i) {
        var where = `${p} level ${l} #${i + 1}`
        look(where + ' buy', t.buy)
        look(where + ' buy_b', t.buy_b)
        look(where + ' sell', t.sell)
      })
    }
  })
  ;['generic', 'rare'].forEach(function (k) {
    table.wandering_trader[k].forEach(function (t, i) {
      look(`wandering trader ${k} #${i + 1} buy`, t.buy)
      look(`wandering trader ${k} #${i + 1} sell`, t.sell)
    })
  })
  ctx.stat('max stack sizes of the items traded', sizes)
  ctx.check('every price and result fits a stack', bad.length === 0, `${n} stacks` + (bad.length ? `; ${bad.length} too big: ${bad.slice(0, 40).join('; ')}` : ''))
}

// ---------------------------------------------------------------------------------------------------------- spawned villagers
// A villager of every profession at every level, made the way the game makes one (nothing but its profession and level set),
// asked for its offers: two per level from that level's list, all from the file.
function vtSpawned(ctx) {
  var level = ctx.level
  var profs = vtProfessions()
  var inTable = Object.keys(ctx.job.table.professions)
  inTable.forEach(function (p) {
    ctx.check(`profession ${p} exists`, profs.indexOf(p) >= 0, profs.indexOf(p) >= 0 ? 'registered' : 'not a registered villager profession')
  })
  var samples = 30
  var asked = 0
  var empty = 0
  var offersSeen = 0
  profs.forEach(function (pid) {
    var bad = []
    var perLevel = {}
    for (var lvl = 1; lvl <= 5; lvl++) {
      var pool = ctx.expected[`${pid}|${lvl}`] || []
      var union = {}
      for (var n = 0; n < samples; n++) {
        var v = vtVillager(level, pid, lvl)
        var offers = v.getOffers()
        asked++
        var sigs = []
        for (var i = 0; i < offers.size(); i++) {
          sigs.push(vtOfferSig(offers.get(i)))
          union[sigs[i]] = true
          var problems = vtRules(ctx, `${pid} level ${lvl} villager`, offers.get(i), ctx.job.levelEra[String(lvl)])
          if (problems.length) bad.push(problems[0])
        }
        offersSeen += sigs.length
        var want = Math.min(2, pool.length)
        if (sigs.length !== want) bad.push(`level ${lvl}: ${sigs.length} offers, expected ${want}`)
        if (sigs.length === 0) empty++
        if (new Set(sigs).size !== sigs.length) bad.push(`level ${lvl}: the same offer twice`)
      }
      var seen = Object.keys(union)
      var d = vtDiff(seen, pool)
      if (d.extra.length) bad.push(`level ${lvl}: offers not in the file: ${d.extra.slice(0, 2)}`)
      if (d.missing.length) bad.push(`level ${lvl}: ${d.missing.length} of ${pool.length} listed offers never came up in ${samples} villagers: ${d.missing.slice(0, 2)}`)
      perLevel[lvl] = seen
    }
    ctx.results.live[pid] = perLevel
    var total = [1, 2, 3, 4, 5].reduce(function (a, l) { return a + perLevel[l].length }, 0)
    ctx.check(`${pid} villagers offer the file's trades`, bad.length === 0, `${total} different offers over 5 levels` + (bad.length ? `; ${bad.length} problems: ${bad.slice(0, 5).join('; ')}` : ''))
  })
  ctx.stat('villagers asked for offers', asked)
}

// ---------------------------------------------------------------------------------------------------------- wandering traders
function vtWanderers(ctx) {
  var level = ctx.level
  var generic = ctx.expected['wandering_trader|generic']
  var rare = ctx.expected['wandering_trader|rare']
  var bad = []
  var seen = {}
  var lots = 60
  for (var n = 0; n < lots; n++) {
    var t = $VTestEntityType.WANDERING_TRADER.create(level)
    var offers = t.getOffers()
    if (offers.size() !== 6) bad.push(`${offers.size()} offers, expected 5 generic + 1 rare`)
    var rareSeen = 0
    for (var i = 0; i < offers.size(); i++) {
      var sig = vtOfferSig(offers.get(i))
      seen[sig] = true
      if (rare.indexOf(sig) >= 0) rareSeen++
      else if (generic.indexOf(sig) < 0) bad.push(`offer ${sig} is not in the file`)
      var problems = vtRules(ctx, 'wandering trader', offers.get(i), rare.indexOf(sig) >= 0 ? 'bronze' : 'copper')
      if (problems.length) bad.push(problems[0])
    }
    if (rareSeen !== 1) bad.push(`${rareSeen} rare offers, expected 1`)
  }
  ctx.check('wandering traders offer the file\'s trades', bad.length === 0, `${lots} traders, ${Object.keys(seen).length} different offers seen of ${generic.length + rare.length}` + (bad.length ? `; ${bad.length} problems: ${bad.slice(0, 5).join('; ')}` : ''))
}

// ---------------------------------------------------------------------------------------------------------- synthetic baked offers
// A villager and a wandering trader that hold emerald-for-iron offers (as a structure template or an old save would hand them
// over) join the world: the pack's script must give them offers from the file. A villager with its own offers keeps them.
function vtSynthetic(ctx) {
  var level = ctx.level
  var found = startAtFind(level, 38.5, -98.0)
  var x = found.spot.x + 40
  var z = found.spot.z + 40
  level.getChunk(x >> 4, z >> 4)
  var y = level.getHeight($VTestHeightmap.WORLD_SURFACE, x, z)
  function emeraldOffer() {
    return new $VTestMerchantOffer(new $VTestItemCost($VTestItems.EMERALD, 4), new $VTestItemStack($VTestItems.IRON_CHESTPLATE, 1), 4, 1, 0.05)
  }
  function joined(entity) {
    entity.setPos(x + 0.5, y + 1, z + 0.5)
    level.addFreshEntity(entity)
    return entity
  }
  // villager: farmer level 2 with a baked iron chestplate offer
  var v = vtVillager(level, 'minecraft:farmer', 2)
  v.getOffers().add(emeraldOffer())
  joined(v)
  var vo = v.getOffers()
  var vsigs = []
  for (var i = 0; i < vo.size(); i++) vsigs.push(vtOfferSig(vo.get(i)))
  var pool = (ctx.expected['minecraft:farmer|1'] || []).concat(ctx.expected['minecraft:farmer|2'] || [])
  var vok = vsigs.length === 4 && vsigs.every(function (s) { return pool.indexOf(s) >= 0 })
  ctx.check('villager with baked emerald offers gets the file\'s', vok, `${vsigs.length} offers after: ${vsigs.map(function (s) { return s.split('|')[0] }).join(', ')}`)
  v.discard()

  // wandering trader with a baked offer
  var w = $VTestEntityType.WANDERING_TRADER.create(level)
  w.getOffers().add(emeraldOffer())
  joined(w)
  var wo = w.getOffers()
  var wall = ctx.expected['wandering_trader|generic'].concat(ctx.expected['wandering_trader|rare'])
  var wsigs = []
  for (var j = 0; j < wo.size(); j++) wsigs.push(vtOfferSig(wo.get(j)))
  var wok = wsigs.length === 6 && wsigs.every(function (s) { return wall.indexOf(s) >= 0 })
  ctx.check('wandering trader with baked emerald offers gets the file\'s', wok, `${wsigs.length} offers after: ${wsigs.map(function (s) { return s.split('|')[0] }).join(', ')}`)
  w.discard()

  // a villager with its own offers keeps them (and their uses)
  var k = vtVillager(level, 'minecraft:toolsmith', 3)
  var ko = k.getOffers()
  ko.get(0).increaseUses()
  var before = []
  for (var a = 0; a < ko.size(); a++) before.push(vtOfferSig(ko.get(a)) + '#' + ko.get(a).getUses())
  joined(k)
  var after = []
  for (var b = 0; b < k.getOffers().size(); b++) after.push(vtOfferSig(k.getOffers().get(b)) + '#' + k.getOffers().get(b).getUses())
  ctx.check('a villager with its own offers keeps them', before.join(',') === after.join(','), `${before.length} offers before and ${after.length} after`)
  k.discard()
}

// ---------------------------------------------------------------------------------------------------------- templates
// Every template of the pack's jars that holds a villager, a wandering trader or a zombie villager, placed with its entities the
// way a jigsaw piece does it (StructureTemplate.placeInWorld). First: do its baked offers load in this version at all? Then:
// what do the entities offer once they have joined the world?
function vtTemplates(ctx) {
  var level = ctx.level
  var manager = level.getStructureManager()
  var found = startAtFind(level, 38.5, -98.0)
  var baseX = found.spot.x + 200
  var baseZ = found.spot.z + 200
  var templates = ctx.job.templates
  var generic = ctx.expected['wandering_trader|generic']
  var rare = ctx.expected['wandering_trader|rare']
  var badAfter = []
  var counts = { templates: 0, villagers: 0, traders: 0, zombies: 0, bakedTemplates: 0, bakedLoads: 0, bakedFails: 0, missing: 0 }
  var missingNames = []
  templates.forEach(function (info, index) {
    var rl = $VTestRL.parse(info.template)
    var opt = manager.get(rl)
    if (!opt.isPresent()) {
      counts.missing++
      missingNames.push(info.template)
      ctx.results.templates.push({ template: info.template, error: 'template not found' })
      return
    }
    var tmpl = opt.get()
    counts.templates++
    var rec = { template: info.template, entities: info.entities, baked: 0, bakedLoads: 0, after: [] }
    // 1. do the baked offers load?
    var tag = tmpl.save(new $VTestCompound())
    var ents = tag.getList('entities', 10)
    for (var e = 0; e < ents.size(); e++) {
      var nbt = ents.getCompound(e).getCompound('nbt')
      if (!nbt.contains('Offers')) continue
      rec.baked++
      var res = $VTestMerchantOffers.CODEC.parse(level.registryAccess().createSerializationContext($VTestNbtOps.INSTANCE), nbt.get('Offers'))
      if (res.result().isPresent()) {
        rec.bakedLoads++
        var items = {}
        var offs = res.result().get()
        for (var q = 0; q < offs.size(); q++) {
          items[vtItemId(offs.get(q).getResult())] = true
          items[vtItemId(offs.get(q).getBaseCostA())] = true
        }
        rec.bakedItems = Object.keys(items)
      } else {
        rec.bakedError = String(res.error().get().message()).slice(0, 200)
      }
    }
    if (rec.baked) {
      counts.bakedTemplates++
      if (rec.bakedLoads === rec.baked) counts.bakedLoads++
      else counts.bakedFails++
    }
    // 2. place it and read what the entities hold
    var x = baseX + (index % 24) * 24
    var z = baseZ + Math.floor(index / 24) * 24
    for (var cx = (x >> 4) - 1; cx <= ((x + 24) >> 4); cx++) for (var cz = (z >> 4) - 1; cz <= ((z + 24) >> 4); cz++) level.getChunk(cx, cz)
    var y = level.getHeight($VTestHeightmap.WORLD_SURFACE, x, z) + 1
    var pos = new $VTestBlockPos(x, y, z)
    tmpl.placeInWorld(level, pos, pos, new $VTestPlaceSettings(), level.getRandom(), 2)
    var size = tmpl.getSize()
    var box = new $VTestAABB(x - 1, y - 2, z - 1, x + size.getX() + 2, y + size.getY() + 2, z + size.getZ() + 2)
    var near = level.getEntitiesOfClass($VTestAbstractVillager, box)
    for (var n = 0; n < near.size(); n++) {
      var en = near.get(n)
      var isTrader = String($VTestEntityType.getKey(en.getType())) === 'minecraft:wandering_trader'
      if (isTrader) counts.traders++
      else counts.villagers++
      var data = isTrader ? null : en.getVillagerData()
      var profId = isTrader ? 'wandering_trader' : String($VTestBuiltIn.VILLAGER_PROFESSION.getKey(data.getProfession()))
      var lvl = isTrader ? 0 : data.getLevel()
      var offers = en.getOffers()
      var sigs = []
      for (var i = 0; i < offers.size(); i++) {
        var sig = vtOfferSig(offers.get(i))
        sigs.push(sig)
        var allowed
        if (isTrader) allowed = generic.indexOf(sig) >= 0 || rare.indexOf(sig) >= 0
        else {
          allowed = false
          for (var l = 1; l <= 5; l++) if ((ctx.expected[`${profId}|${l}`] || []).indexOf(sig) >= 0) allowed = true
        }
        if (!allowed) badAfter.push(`${info.template}: ${profId} holds ${sig.split('|')[0]}`)
      }
      rec.after.push({ profession: profId, level: lvl, offers: sigs.length, rerolled: en.persistentData.getInt('pack_trades') === 1 })
      if (sigs.length === 0 && isTrader) badAfter.push(`${info.template}: wandering trader without offers`)
    }
    var zn = level.getEntitiesOfClass(Java.loadClass('net.minecraft.world.entity.monster.ZombieVillager'), box)
    counts.zombies += zn.size()
    near.forEach(function (en) { en.discard() })
    ctx.results.templates.push(rec)
  })
  ctx.stat('templates with villagers, traders or zombie villagers', counts)
  ctx.check('every template was found', counts.missing === 0, `${counts.templates} placed, ${counts.missing} missing` + (missingNames.length ? ': ' + missingNames.join(', ') : ''))
  ctx.check('entities from templates hold the file\'s trades', badAfter.length === 0 && counts.villagers + counts.traders > 0,
    `${counts.villagers} villagers and ${counts.traders} wandering traders placed from ${counts.templates} templates` + (badAfter.length ? `; ${badAfter.length} problems: ${badAfter.slice(0, 5).join('; ')}` : ''))
  ctx.check('baked offers (info)', true, `${counts.bakedTemplates} templates carry offers: ${counts.bakedLoads} load in this version, ${counts.bakedFails} fail to load`)
}

// ---------------------------------------------------------------------------------------------------------- loot
// What an iron golem, the illagers, a witch, a zombie villager and every Hero of the Village gift hand out, rolled 300 times and
// written to the results; tools/villagers_test.py judges them (the golem and the gifts are overridden in kubejs/data/minecraft/
// loot_table/: gifts by the pack's loot tables, the golem drops iron ore instead of ingots).
function vtLoot(ctx) {
  var level = ctx.level
  var server = ctx.server
  var origin = new $VTestVec3(0.5, 64, 0.5)
  var tables = [['minecraft:entities/iron_golem', 'iron_golem', 'entity'], ['minecraft:entities/vindicator', 'vindicator', 'entity'],
    ['minecraft:entities/pillager', 'pillager', 'entity'], ['minecraft:entities/evoker', 'evoker', 'entity'],
    ['minecraft:entities/witch', 'witch', 'entity'], ['minecraft:entities/zombie_villager', 'zombie_villager', 'entity']]
  ;['armorer', 'butcher', 'cartographer', 'cleric', 'farmer', 'fisherman', 'fletcher', 'leatherworker', 'librarian', 'mason', 'shepherd', 'toolsmith', 'weaponsmith'].forEach(function (p) {
    tables.push([`minecraft:gameplay/hero_of_the_village/${p}_gift`, 'villager', 'gift'])
  })
  tables.forEach(function (t) {
    var table = server.reloadableRegistries().getLootTable($VTestRK.create($VTestRegistries.LOOT_TABLE, $VTestRL.parse(t[0])))
    var entity = $VTestEntityType.byString(t[1]).get().create(level)
    var seen = {}
    for (var i = 0; i < 300; i++) {
      var builder = new $VTestLootParams(level).withParameter($VTestLootContextParams.THIS_ENTITY, entity).withParameter($VTestLootContextParams.ORIGIN, origin)
      var params
      if (t[2] === 'gift') params = builder.create($VTestLootParamSets.GIFT)
      else params = builder.withParameter($VTestLootContextParams.DAMAGE_SOURCE, level.damageSources().generic()).create($VTestLootParamSets.ENTITY)
      table.getRandomItems(params).forEach(function (stack) {
        var id = vtItemId(stack)
        seen[id] = (seen[id] || 0) + Number(stack.getCount())
      })
    }
    ctx.results.loot[t[0]] = seen
  })
  ctx.stat('loot tables rolled', Object.keys(ctx.results.loot).length)
}
