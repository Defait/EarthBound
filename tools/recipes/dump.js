// Dev-only recipe, tag and loot dump for the recipe explorer.
// Note: function-local variables use var; Rhino rejects block-scoped const in callbacks that run repeatedly.
// tools/recipes/dump.py copies this into the test server's local/kubejs/local_server_scripts;
// it is never part of the pack. Output: local/pack-dump/ on the test server.
const $JsonOps = Java.loadClass('com.mojang.serialization.JsonOps')
const $RegistryOps = Java.loadClass('net.minecraft.resources.RegistryOps')
const $Recipe = Java.loadClass('net.minecraft.world.item.crafting.Recipe')
const $Registries = Java.loadClass('net.minecraft.core.registries.Registries')
const $BuiltInRegistries = Java.loadClass('net.minecraft.core.registries.BuiltInRegistries')
const $ResourceKey = Java.loadClass('net.minecraft.resources.ResourceKey')
const $LootTable = Java.loadClass('net.minecraft.world.level.storage.loot.LootTable')
const $JsonObject = Java.loadClass('com.google.gson.JsonObject')
const $JsonArray = Java.loadClass('com.google.gson.JsonArray')

const OUT = 'local/pack-dump/'

// ids and tags of one registry
function registryDump(server, key) {
  var reg = server.registryAccess().registryOrThrow(key)
  var ids = new $JsonArray()
  reg.keySet().forEach(id => ids.add(String(id)))
  var tags = new $JsonObject()
  reg.getTags().forEach(pair => {
    var members = new $JsonArray()
    pair.getSecond().forEach(holder => members.add(String(holder.unwrapKey().get().location())))
    tags.add(String(pair.getFirst().location()), members)
  })
  var out = new $JsonObject()
  out.add('ids', ids)
  out.add('tags', tags)
  return out
}

ServerEvents.loaded(event => {
  const server = event.server
  const t0 = Date.now()
  const ops = $RegistryOps.create($JsonOps.INSTANCE, server.registryAccess())

  const byType = {}
  let total = 0
  let failed = 0
  server.getRecipeManager().getRecipes().forEach(holder => {
    var recipe = holder.value()
    var type = String($BuiltInRegistries.RECIPE_TYPE.getKey(recipe.getType()))
    var entry = new $JsonObject()
    entry.addProperty('id', String(holder.id()))
    entry.addProperty('type', type)
    try {
      var encoded = $Recipe.CODEC.encodeStart(ops, recipe)
      var json = encoded.result()
      if (json.isPresent()) {
        entry.add('json', json.get())
      } else {
        failed++
        entry.addProperty('error', String(encoded.error().get().message()))
      }
    } catch (e) {
      failed++
      entry.addProperty('error', String(e))
    }
    if (!byType[type]) byType[type] = new $JsonArray()
    byType[type].add(entry)
    total++
  })

  const types = new $JsonObject()
  for (const type in byType) {
    JsonIO.write(OUT + 'recipes/' + type.replace(':', '/') + '.json', byType[type])
    types.addProperty(type, byType[type].size())
  }

  JsonIO.write(OUT + 'items.json', registryDump(server, $Registries.ITEM))
  JsonIO.write(OUT + 'fluids.json', registryDump(server, $Registries.FLUID))
  JsonIO.write(OUT + 'blocks.json', registryDump(server, $Registries.BLOCK))

  // Block loot tables, so the explorer knows what mining a block yields.
  let loot = 0
  try {
    var reloadable = server.reloadableRegistries()
    var tables = new $JsonObject()
    reloadable.getKeys($Registries.LOOT_TABLE).forEach(id => {
      var name = String(id)
      if (name.indexOf(':blocks/') < 0) return
      try {
        var table = reloadable.getLootTable($ResourceKey.create($Registries.LOOT_TABLE, id))
        var json = $LootTable.DIRECT_CODEC.encodeStart(ops, table).result()
        if (json.isPresent()) {
          tables.add(name, json.get())
          loot++
        }
      } catch (e) {
        // skip tables that don't encode
      }
    })
    JsonIO.write(OUT + 'loot_blocks.json', tables)
  } catch (e) {
    console.warn('[pack-dump] block loot tables skipped: ' + e)
  }

  // Sizes of datapack registries the pack changes. GregTech's KubeJS removal keeps ore veins in the
  // registry but stops them generating, so ore veins also report how many can still generate.
  const registries = new $JsonObject()
  ;['gtceu:ore_vein', 'gtceu:bedrock_ore', 'gtceu:bedrock_fluid'].forEach(name => {
    var reg = server.registryAccess().registry($ResourceKey.createRegistryKey(name))
    if (!reg.isPresent()) return
    registries.addProperty(name, reg.get().size())
    if (name === 'gtceu:ore_vein') {
      var active = 0
      reg.get().forEach(def => { if (def.canGenerate()) active++ })
      registries.addProperty(name + ' (generating)', active)
    }
  })

  const index = new $JsonObject()
  index.add('registries', registries)
  index.add('recipe_types', types)
  index.addProperty('recipes', total)
  index.addProperty('failed', failed)
  index.addProperty('loot_tables', loot)
  index.addProperty('millis', Date.now() - t0)
  JsonIO.write(OUT + 'index.json', index)
  console.info('[pack-dump] done: ' + total + ' recipes (' + failed + ' not encodable), ' + loot + ' block loot tables in ' + (Date.now() - t0) + ' ms')
})
