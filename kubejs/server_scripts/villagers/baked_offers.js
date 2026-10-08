// Villagers and wandering traders that already hold offers from before the pack's trades get new ones (docs/design.md:
// "Villagers"; the trades themselves are startup_scripts/villager_trades.js).
//
// A villager's offers are made the first time anything asks for them (saving the entity does) and then stay in its data, so three
// kinds hold trades the pack never made: wandering traders whose offers are saved in a structure template (Moog's Voyager
// Structures' carts and Towns and Towers' trader camps: 12 templates, emerald offers, all of which load in this version); villagers
// and traders in worlds generated or saved before the trades changed (a scanned world's Moog's Voyager armorers held vanilla iron
// armour offers, made when the world was saved); and cured zombie villagers. When any villager or wandering trader joins the world
// holding an item that no trade of the file mentions, it gets new offers from the pack's lists, the way vanilla fills them: two
// per villager level up to its own, five generic and one rare for the wandering trader. Offers that are all the pack's pass
// untouched, so a villager that has levelled up keeps its uses. Villagers with a profession but a level above 5 (Moog's Voyager
// smiths are level 99) have no list for that level and, as in vanilla, no offers.
//
// KubeJS's Rhino turns an empty ItemStack (a trade's absent second price) into null, and can't call a method on a Java map
// keyed by int, so the code asks fresh entities for offers instead of reading the trade lists (see startup_scripts/villager_trades.js).

const $BakedEntityType = Java.loadClass('net.minecraft.world.entity.EntityType')
const $BakedVillagerData = Java.loadClass('net.minecraft.world.entity.npc.VillagerData')
const $BakedBuiltIn = Java.loadClass('net.minecraft.core.registries.BuiltInRegistries')

const BAKED_FILE = 'kubejs/config/villager_trades.json'
const BAKED_FLAG = 'pack_trades'
var bakedKnown = null

// Every item id the trades file mentions (read once per script load, so again after /reload).
function bakedKnownItems() {
  if (bakedKnown != null) return bakedKnown
  var table = JSON.parse(String(JsonIO.toString(JsonIO.readJson(BAKED_FILE))))
  var ids = {}
  function add(trade) {
    ;['buy', 'buy_b', 'sell'].forEach(k => { if (trade[k]) ids[trade[k][0]] = true })
  }
  Object.keys(table.professions).forEach(p => {
    for (var l = 1; l <= 5; l++) table.professions[p][String(l)].forEach(add)
  })
  table.wandering_trader.generic.forEach(add)
  table.wandering_trader.rare.forEach(add)
  bakedKnown = ids
  return ids
}

function bakedTypeId(entity) {
  return String(Java.loadClass('net.minecraft.world.entity.EntityType').getKey(entity.getType()))
}

function bakedItemId(stack) {
  return String($BakedBuiltIn.ITEM.getKey(stack.getItem()))
}

// New offers the way vanilla makes them: fresh villagers (not added to the world) of the same profession, one for each level up to the
// villager's own, are asked for theirs (each fills two from its level's list), and a fresh wandering trader for its five generic and
// one rare. The lists themselves stay out of it: a Java map keyed by int can't be asked from KubeJS's Rhino (startup_scripts/villager_trades.js).
function bakedReroll(entity, wanderer) {
  var level = entity.level
  var offers = entity.getOffers()
  offers.clear()
  if (wanderer) {
    offers.addAll($BakedEntityType.WANDERING_TRADER.create(level).getOffers())
    return
  }
  var data = entity.getVillagerData()
  for (var l = 1; l <= Math.min(data.getLevel(), 5); l++) {
    var fresh = $BakedEntityType.VILLAGER.create(level)
    fresh.setVillagerData(new $BakedVillagerData(data.getType(), data.getProfession(), l))
    offers.addAll(fresh.getOffers())
  }
}

function bakedCheck(event, wanderer) {
  var entity = event.entity
  if (entity.level.isClientSide()) return
  try {
    var data = entity.persistentData
    if (data.getInt(BAKED_FLAG) === 1) return
    data.putInt(BAKED_FLAG, 1)
    var known = bakedKnownItems()
    var offers = entity.getOffers()
    var foreign = null
    for (var i = 0; i < offers.size() && foreign == null; i++) {
      var offer = offers.get(i)
      var stacks = [offer.getResult(), offer.getBaseCostA(), offer.getCostB()]
      for (var j = 0; j < stacks.length; j++) {
        // (an empty stack, the absent second price, reads as null in KubeJS's Rhino)
        if (stacks[j] != null && !stacks[j].isEmpty() && !known[bakedItemId(stacks[j])]) {
          foreign = bakedItemId(stacks[j])
          break
        }
      }
    }
    if (foreign == null) return
    bakedReroll(entity, wanderer)
    console.info(`[villager-trades] new offers for ${bakedTypeId(entity)} at ${Math.floor(entity.x)} ${Math.floor(entity.y)} ${Math.floor(entity.z)}: ` +
      `had ${foreign}, which no trade of ${BAKED_FILE} uses`)
  } catch (e) {
    console.error(`[villager-trades] couldn't check the offers of ${bakedTypeId(entity)}: ${e}`)
  }
}

EntityEvents.spawned('minecraft:villager', event => bakedCheck(event, false))
EntityEvents.spawned('minecraft:wandering_trader', event => bakedCheck(event, true))
