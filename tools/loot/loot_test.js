// Dev-only: dump and roll every loot table the running pack knows. Run by tools/loot/lint.py (copied into the test server's
// local/kubejs/local_server_scripts for one run; never part of the pack).
//
// For every table in the loot table registry whose type is a chest, archaeology or gift table (the loot a player finds, not
// block drops or mob drops) it writes the table as the server loaded it (LootTable.DIRECT_CODEC to JSON, so datapack
// overrides, nested tables and functions are what really counts), the members of every item tag it names, and what comes
// out of rolling it ROLLS times through the normal pipeline (getRandomItems, so NeoForge's global loot modifiers apply).
// It also lists the global loot modifiers that are active. Result: local/loot-test/results.json.
// Note: function-local variables use var; Rhino rejects block-scoped const in callbacks that run repeatedly.
const $LTRK = Java.loadClass('net.minecraft.resources.ResourceKey')
const $LTRL = Java.loadClass('net.minecraft.resources.ResourceLocation')
const $LTRegistries = Java.loadClass('net.minecraft.core.registries.Registries')
const $LTBuiltIn = Java.loadClass('net.minecraft.core.registries.BuiltInRegistries')
const $LTTagKey = Java.loadClass('net.minecraft.tags.TagKey')
const $LTParams = Java.loadClass('net.minecraft.world.level.storage.loot.LootParams$Builder')
const $LTParamSets = Java.loadClass('net.minecraft.world.level.storage.loot.parameters.LootContextParamSets')
const $LTCtxParams = Java.loadClass('net.minecraft.world.level.storage.loot.parameters.LootContextParams')
const $LTLootTable = Java.loadClass('net.minecraft.world.level.storage.loot.LootTable')
const $LTJsonOps = Java.loadClass('com.mojang.serialization.JsonOps')
const $LTVec3 = Java.loadClass('net.minecraft.world.phys.Vec3')
const $LTEntityType = Java.loadClass('net.minecraft.world.entity.EntityType')
const $LTRegistryOps = Java.loadClass('net.minecraft.resources.RegistryOps')

// Replaced by the Python tool.
const LOOT_TEST_JOB = /*JOB*/ { rolls: 300, kinds: ['minecraft:chest', 'minecraft:generic', 'minecraft:archaeology', 'minecraft:gift'] } /*END*/

function lootTestParamSetName(table) {
  var enc = $LTParamSets.CODEC.encodeStart($LTJsonOps.INSTANCE, table.getParamSet()).result()
  return enc.isPresent() ? String(enc.get().getAsString()) : '?'
}

// The table as the winning data pack wrote it (the resource), else re-encoded with the registries (some functions need them).
function lootTestJson(server, id, table) {
  try {
    var path = $LTRL.fromNamespaceAndPath(id.getNamespace(), 'loot_table/' + id.getPath() + '.json')
    var opt = server.getResourceManager().getResource(path)
    if (opt.isPresent()) {
      var rd = opt.get().openAsReader()
      var text = ''
      var line
      while ((line = rd.readLine()) !== null) text += line + ' '
      rd.close()
      return JSON.stringify(JSON.parse(text))
    }
  } catch (e) { /* fall through to the codec */ }
  try {
    var ops = $LTRegistryOps.create($LTJsonOps.INSTANCE, server.registryAccess())
    var enc = $LTLootTable.DIRECT_CODEC.encodeStart(ops, table).result()
    if (enc.isPresent()) return String(enc.get().toString())
  } catch (e) { /* no JSON */ }
  return null
}

function lootTestTags(json, tags, itemReg) {
  // every {"type": "minecraft:tag", "name": ...} entry anywhere in the table
  var text = String(json)
  var rx = /"type":"minecraft:tag","name":"([a-z0-9_.\-]+:[a-z0-9_\/.\-]+)"|"name":"([a-z0-9_.\-]+:[a-z0-9_\/.\-]+)","type":"minecraft:tag"/g
  var m
  while ((m = rx.exec(text)) !== null) {
    var name = m[1] || m[2]
    if (tags[name]) continue
    var members = []
    var opt = itemReg.getTag($LTTagKey.create($LTRegistries.ITEM, $LTRL.parse(name)))
    if (opt.isPresent()) {
      opt.get().forEach(function (holder) { members.push(String(itemReg.getKey(holder.value()))) })
    }
    tags[name] = members
  }
}

ServerEvents.loaded(event => {
  var server = event.server
  var level = server.overworld()
  var regs = server.reloadableRegistries()
  var results = { rolls: LOOT_TEST_JOB.rolls, tables: {}, skipped: {}, tags: {}, modifiers: null, errors: [] }

  // The global loot modifier lists of every data pack in load order (NeoForge's LootModifierManager walks them with "replace" clearing
  // what came before), and, best effort, the modifiers it holds.
  try {
    var stack = server.getResourceManager().getResourceStack($LTRL.fromNamespaceAndPath('neoforge', 'loot_modifiers/global_loot_modifiers.json'))
    var lists = []
    for (var q = 0; q < stack.size(); q++) {
      var res = stack.get(q)
      var rd = res.openAsReader()
      var text = ''
      var line
      while ((line = rd.readLine()) !== null) text += line + ' '
      rd.close()
      lists.push({ pack: String(res.sourcePackId()), json: JSON.parse(text) })
    }
    results.modifier_lists = lists
  } catch (e) {
    results.errors.push('global loot modifier lists: ' + e)
  }

  var itemReg = $LTBuiltIn.ITEM
  var entity = $LTEntityType.PIG.create(level)
  var origin = new $LTVec3(0.5, 64, 0.5)
  var keys = regs.getKeys($LTRegistries.LOOT_TABLE).toArray()
  var seenKinds = {}
  for (var k = 0; k < keys.length; k++) {
    var id = String(keys[k])
    try {
      var table = regs.getLootTable($LTRK.create($LTRegistries.LOOT_TABLE, keys[k]))
      var kind = lootTestParamSetName(table)
      seenKinds[kind] = (seenKinds[kind] || 0) + 1
      if (LOOT_TEST_JOB.kinds.indexOf(kind) < 0) {
        results.skipped[id] = kind
        continue
      }
      var json = lootTestJson(server, keys[k], table)
      var rec = { kind: kind, json: json ? JSON.parse(json) : null, seen: {}, empty: 0, rolls: 0, components: {}, error: null }
      results.tables[id] = rec
      if (json) lootTestTags(json, results.tags, itemReg)
      // an untyped table is "generic" (all parameters required); a chest fills it with chest parameters
      var ps = kind === 'minecraft:generic' ? $LTParamSets.CHEST : table.getParamSet()
      var allowed = ps.getAllowed()
      try {
        for (var i = 0; i < LOOT_TEST_JOB.rolls; i++) {
          var b = new $LTParams(level)
          if (allowed.contains($LTCtxParams.ORIGIN)) b = b.withParameter($LTCtxParams.ORIGIN, origin)
          if (allowed.contains($LTCtxParams.THIS_ENTITY)) b = b.withParameter($LTCtxParams.THIS_ENTITY, entity)
          var stacks = table.getRandomItems(b.create(ps))
          var n = 0
          for (var s = 0; s < stacks.size(); s++) {
            var stack = stacks.get(s)
            if (stack.isEmpty()) continue
            n++
            var item = String(itemReg.getKey(stack.getItem()))
            rec.seen[item] = (rec.seen[item] || 0) + Number(stack.getCount())
            var patch = stack.getComponentsPatch()
            if (!patch.isEmpty()) {
              patch.entrySet().forEach(function (e) {
                var key = item + ' ' + String(e.getKey())
                rec.components[key] = (rec.components[key] || 0) + 1
              })
            }
          }
          if (n === 0) rec.empty++
          rec.rolls++
        }
      } catch (e) {
        rec.error = String(e)
      }
    } catch (e) {
      results.tables[id] = { kind: '?', json: null, seen: {}, empty: 0, rolls: 0, components: {}, error: String(e) }
    }
  }
  results.kinds = seenKinds
  JsonIO.write('local/loot-test/results.json', results)
  console.info('[loot-test] done: ' + Object.keys(results.tables).length + ' tables rolled, ' + Object.keys(results.skipped).length + ' skipped')
  lootTestLootr(server, level)
})

// What does Lootr convert? Containers with a loot table, as a structure would leave them, are set in a loaded chunk; a while
// later the blocks are read back (a Lootr container has a lootr: id). Informational (lint.py prints it).
function lootTestLootr(server, level) {
  var table = 'minecraft:chests/simple_dungeon'
  var blocks = ['tfc:wood/chest/oak', 'tfc:wood/trapped_chest/oak', 'minecraft:chest', 'minecraft:trapped_chest', 'minecraft:barrel',
    'tfc:wood/barrel/oak', 'afc:wood/chest/baobab', 'minecraft:decorated_pot', 'minecraft:shulker_box', 'minecraft:suspicious_sand', 'minecraft:suspicious_gravel']
  var out = { table: table, blocks: {}, errors: [] }
  var BlockPos = Java.loadClass('net.minecraft.core.BlockPos')
  var x0 = 40
  try {
    ;[x0 >> 4, (x0 + 24) >> 4].forEach(function (cx) { level.getChunk(cx, 0); level.setChunkForced(cx, 0, true) })
    var src = server.createCommandSourceStack()
    var cmds = server.getCommands()
    blocks.forEach(function (b, i) {
      var cmd = 'setblock ' + (x0 + i * 2) + ' 200 0 ' + b + '{LootTable:"' + table + '"} replace'
      out.blocks[b] = { cmd: cmd, after: null, loot: null }
      try { cmds.performPrefixedCommand(src, cmd) } catch (e) { out.errors.push(cmd + ': ' + e) }
    })
  } catch (e) {
    out.errors.push('setup: ' + e)
  }
  server.scheduleInTicks(300, function () {
    try {
      blocks.forEach(function (b, i) {
        var pos = new BlockPos(x0 + i * 2, 200, 0)
        try {
          out.blocks[b].after = String($LTBuiltIn.BLOCK.getKey(level.getBlockState(pos).getBlock()))
          var be = level.getBlockEntity(pos)
          if (be) {
            out.blocks[b].entity = String($LTBuiltIn.BLOCK_ENTITY_TYPE.getKey(be.getType()))
            out.blocks[b].loot = String(be.saveWithFullMetadata(level.registryAccess()).getString('LootTable'))
          }
        } catch (e) {
          out.errors.push(b + ': ' + e)
        }
      })
    } catch (e) {
      out.errors.push('readback: ' + e)
    }
    JsonIO.write('local/loot-test/lootr.json', out)
    console.info('[loot-test] lootr done')
  })
}
