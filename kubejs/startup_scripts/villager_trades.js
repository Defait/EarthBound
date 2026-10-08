// Villager and wandering trader trades are TFC barter, not emeralds and iron (docs/design.md: "Villagers").
//
// TFC 4 has no villagers, but the structure mods the pack keeps (Towns and Towers, Moog's Voyager Structures, Moog's Missing
// Villages) place vanilla ones, and vanilla villagers trade emeralds for iron and diamond gear, enchanted books, potions and
// maps, skipping every era. NeoForge builds each profession's trade list when a world's data loads (VillagerTradingManager,
// on the tags update of a server data load, so again after /reload) and posts VillagerTradesEvent and WandererTradesEvent so
// mods can change them. This listens with the lowest priority, so it also overrides any mod that adds trades, and replaces
// every list with the one in kubejs/config/villager_trades.json: per profession and villager level, the offers that level can
// show (a villager picks two per level, as in vanilla); for the wandering trader the generic and the rare list.
// A profession or level missing from the file has no trades. If the file can't be read or is broken, the lists are left empty
// (never vanilla's) and the error is logged; tools/villagers_test.py checks the file and what villagers really offer.
// server_scripts/villagers/baked_offers.js handles villagers that already hold offers (structure templates, old saves).
//
// Trades are NeoForge's BasicItemListing (price, optional second price, result, max uses, villager xp, price multiplier).
// Inputs match by item only. Food is never a result: a stack made now would carry the time the world loaded as its creation date.
//
// Two quirks of KubeJS's Rhino shape the code: a Java map keyed by int (the event's trades) throws on any method call, so a HashMap
// copy (same list objects) is used; and an empty ItemStack becomes null, so ItemStack.EMPTY can't be passed as an absent price.

const $VtPriority = Java.loadClass('net.neoforged.bus.api.EventPriority')
const $VtVillagerTradesEvent = Java.loadClass('net.neoforged.neoforge.event.village.VillagerTradesEvent')
const $VtWandererTradesEvent = Java.loadClass('net.neoforged.neoforge.event.village.WandererTradesEvent')
const $VtListing = Java.loadClass('net.neoforged.neoforge.common.BasicItemListing')
const $VtItemStack = Java.loadClass('net.minecraft.world.item.ItemStack')
const $VtBuiltIn = Java.loadClass('net.minecraft.core.registries.BuiltInRegistries')
const $VtRL = Java.loadClass('net.minecraft.resources.ResourceLocation')
const $VtInteger = Java.loadClass('java.lang.Integer')
const $VtHashMap = Java.loadClass('java.util.HashMap')

const VT_FILE = 'kubejs/config/villager_trades.json'
const VT_TAG = '[villager-trades]'

function vtLoad() {
  return JSON.parse(String(JsonIO.toString(JsonIO.readJson(VT_FILE))))
}

// [id, count] -> ItemStack, or null (logged) when the item doesn't exist or the count doesn't fit a stack.
function vtStack(pair, where, errors) {
  if (!pair || pair.length !== 2) {
    errors.push(`${where}: expected [id, count], got ${JSON.stringify(pair)}`)
    return null
  }
  var rl = $VtRL.tryParse(String(pair[0]))
  if (rl == null || !$VtBuiltIn.ITEM.containsKey(rl)) {
    errors.push(`${where}: no item ${pair[0]}`)
    return null
  }
  var count = Number(pair[1])
  var stack = new $VtItemStack($VtBuiltIn.ITEM.get(rl), count)
  if (stack.isEmpty() || count < 1 || count > stack.getMaxStackSize() || count !== Math.floor(count)) {
    errors.push(`${where}: ${pair[0]} x${pair[1]} doesn't fit a stack of ${stack.getMaxStackSize()}`)
    return null
  }
  return stack
}

// KubeJS's Rhino turns an empty ItemStack into null (ItemStack.EMPTY reads as undefined, and so does an air stack made here), so a
// trade with one price uses BasicItemListing's constructor without a second price instead of passing an empty one.
function vtListing(trade, xpDefault, multiplier, where, errors) {
  var price = vtStack(trade.buy, `${where} buy`, errors)
  var price2 = trade.buy_b ? vtStack(trade.buy_b, `${where} buy_b`, errors) : null
  var sale = vtStack(trade.sell, `${where} sell`, errors)
  if (price == null || (trade.buy_b && price2 == null) || sale == null) return null
  var uses = Number(trade.max_uses)
  if (!(uses >= 1)) {
    errors.push(`${where}: max_uses ${trade.max_uses}`)
    return null
  }
  var xp = trade.xp != null ? Number(trade.xp) : xpDefault
  if (price2 == null) return new $VtListing(price, sale, uses, xp, multiplier)
  return new $VtListing(price, price2, sale, uses, xp, multiplier)
}

function vtReport(what, listings, errors) {
  console.info(`${VT_TAG} ${what}: ${listings} offers` + (errors.length ? `, ${errors.length} rejected` : ''))
  for (var i = 0; i < errors.length; i++) console.error(`${VT_TAG} rejected ${errors[i]}`)
}

// The event's map is a fastutil Int2ObjectMap, and KubeJS's Rhino looks a property up in a Java map before it looks for the method,
// which throws for an int-keyed map (even for .get). A HashMap copy holds the same list objects and has none of that.
NativeEvents.onEvent($VtPriority.LOWEST, $VtVillagerTradesEvent, event => {
  var profession = String($VtBuiltIn.VILLAGER_PROFESSION.getKey(event.getType()))
  var trades = new $VtHashMap(event.getTrades())
  var errors = []
  var count = 0
  try {
    var table = vtLoad()
    var spec = table.professions[profession]
    if (spec == null && profession !== 'minecraft:none' && profession !== 'minecraft:nitwit') {
      // a profession from another mod: no trades, and say so once per reload
      console.warn(`${VT_TAG} ${profession} has no entry in ${VT_FILE}: no trades`)
    }
    for (var lvl = 1; lvl <= 5; lvl++) {
      var list = trades.get($VtInteger.valueOf(lvl))
      list.clear()
      var entries = spec != null ? spec[String(lvl)] : null
      if (entries == null) continue
      for (var i = 0; i < entries.length; i++) {
        var listing = vtListing(entries[i], table.xp[String(lvl)], table.price_multiplier, `${profession} level ${lvl} #${i + 1}`, errors)
        if (listing != null) {
          list.add(listing)
          count++
        }
      }
    }
    if (spec != null) vtReport(profession, count, errors)
  } catch (e) {
    // fail closed: no trades at all, not vanilla's
    for (var l = 1; l <= 5; l++) trades.get($VtInteger.valueOf(l)).clear()
    console.error(`${VT_TAG} ${profession}: couldn't apply ${VT_FILE}, no trades: ${e}`)
  }
})

NativeEvents.onEvent($VtPriority.LOWEST, $VtWandererTradesEvent, event => {
  var generic = event.getGenericTrades()
  var rare = event.getRareTrades()
  var errors = []
  var count = 0
  try {
    var table = vtLoad()
    var spec = table.wandering_trader
    generic.clear()
    rare.clear()
    var kinds = ['generic', 'rare']
    var targets = [generic, rare]
    for (var k = 0; k < kinds.length; k++) {
      var entries = spec[kinds[k]]
      for (var i = 0; i < entries.length; i++) {
        var listing = vtListing(entries[i], 0, table.price_multiplier, `wandering trader ${kinds[k]} #${i + 1}`, errors)
        if (listing != null) {
          targets[k].add(listing)
          count++
        }
      }
    }
    vtReport('wandering trader', count, errors)
  } catch (e) {
    generic.clear()
    rare.clear()
    console.error(`${VT_TAG} wandering trader: couldn't apply ${VT_FILE}, no trades: ${e}`)
  }
})
