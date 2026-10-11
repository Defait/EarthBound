// A title on screen the first time a player comes near a real place (docs/design.md: "Place names").
//
// TFC: Real World ships 401 named waypoints (cities and landmarks, with latitude and longitude, grouped into
// subregions, regions and continents) and its own geography screen; it records a visit only within 32 blocks of a
// waypoint (640 m at the pack's 20 m per block), as an advancement toast. This script uses the same list through the
// mod's own API (GeographyManager.allWaypoints(), which also holds the pack's ancient sites in
// config/tfc_real_world/geography/pack/) and projects each waypoint to blocks the way the mod does
// (WaypointCoordinates.toBlockXZ), so no data is copied. Every 2 seconds each player in the overworld is compared
// with the waypoints: the nearest one within PLACE_RADIUS blocks that the player has not been told about yet is sent as a
// vanilla title (the place) and subtitle (its subtitle if it has one, such as "Ancient site", otherwise its subregion and
// region, "Tuscany, Italy"). Once per player and place: the places seen are kept in the world's persistent data by
// player UUID, like /startat's use (they survive restarts and deaths). Traveler's Titles would name TFC's biomes
// (landforms such as "rolling hills"), not places.
//
// PLACE_RADIUS is in blocks, so it is a distance on the map that depends on the world's scale: 400 blocks is 8 km at
// 20 m per block (a city and its outskirts, about the size of the waypoint's own disk). Dimensions other than the
// overworld are skipped. Region polygons (tools/structures/catalogue.json) are not needed.

const $GeographyManager = Java.loadClass('net.yazloysasha.tfcrealworld.util.geography.GeographyManager')
const $GeographyKind = Java.loadClass('net.yazloysasha.tfcrealworld.util.geography.GeographyKind')
const $WaypointCoordinates = Java.loadClass('net.yazloysasha.tfcrealworld.util.geography.WaypointCoordinates')
const $TitlesPacket = Java.loadClass('net.minecraft.network.protocol.game.ClientboundSetTitlesAnimationPacket')
const $TitlePacket = Java.loadClass('net.minecraft.network.protocol.game.ClientboundSetTitleTextPacket')
const $SubtitlePacket = Java.loadClass('net.minecraft.network.protocol.game.ClientboundSetSubtitleTextPacket')

const PLACES_SEEN = 'pack_places_seen'
const PLACE_RADIUS = 400
const PLACE_INTERVAL = 40
const PLACE_LANG = 'en_us'

// Top-level functions are shared by the server scripts (tools/smoke_checks.js calls placesLoad and placesNearest).
var PLACES_LIST = null

// The waypoints with their block positions, built on first use (the projection needs the world's config).
function placesLoad() {
  if (PLACES_LIST) return PLACES_LIST
  $GeographyManager.initialize()
  var out = []
  var all = $GeographyManager.allWaypoints()
  for (var i = 0; i < all.size(); i++) {
    var node = all.get(i)
    var lat = node.latitude()
    var lon = node.longitude()
    if (lat == null || lon == null) continue
    var xz = $WaypointCoordinates.toBlockXZ(Number(lat), Number(lon))
    out.push({ ref: String(node.ref()), x: Number(xz[0]), z: Number(xz[1]), title: String(node.getTitle(PLACE_LANG)), subtitle: placesSubtitle(node) })
  }
  PLACES_LIST = out
  return out
}

// The waypoint's own subtitle, or the titles of its subregion and region.
function placesSubtitle(node) {
  if (node.hasSubtitle(PLACE_LANG)) return String(node.getSubtitle(PLACE_LANG))
  var names = []
  var parent = node.parentRef() ? $GeographyManager.get(String(node.parentRef())) : null
  for (var depth = 0; parent && depth < 4; depth++) {
    if (parent.kind() === $GeographyKind.SUBREGION || parent.kind() === $GeographyKind.REGION) names.push(String(parent.getTitle(PLACE_LANG)))
    parent = parent.parentRef() ? $GeographyManager.get(String(parent.parentRef())) : null
  }
  return names.slice(0, 2).join(', ')
}

// The nearest waypoint within the radius of a block position that `skip(ref)` does not exclude, or null.
function placesNearest(x, z, skip) {
  var best = null
  var bestD = PLACE_RADIUS * PLACE_RADIUS
  var list = placesLoad()
  for (var i = 0; i < list.length; i++) {
    var w = list[i]
    var d = (w.x - x) * (w.x - x) + (w.z - z) * (w.z - z)
    if (d <= bestD && !(skip && skip(w.ref))) {
      best = w
      bestD = d
    }
  }
  return best
}

function placesShow(player, place) {
  player.connection.send(new $TitlesPacket(10, 70, 20))
  player.connection.send(new $SubtitlePacket(Text.gray(place.subtitle)))
  player.connection.send(new $TitlePacket(Text.gold(place.title)))
}

PlayerEvents.tick(event => {
  var player = event.player
  if (player.tickCount % PLACE_INTERVAL !== 0 || String(player.level.dimension) !== 'minecraft:overworld') return
  var server = player.server
  var seenAll = server.persistentData.getCompound(PLACES_SEEN)
  var uuid = String(player.profile.id)
  var seen = seenAll.getCompound(uuid)
  var place = null
  try {
    place = placesNearest(player.x, player.z, ref => seen.getBoolean(ref))
  } catch (e) {
    console.error(`[place-titles] ${e}`)
    return
  }
  if (!place) return
  seen.putBoolean(place.ref, true)
  seenAll.put(uuid, seen)
  server.persistentData.put(PLACES_SEEN, seenAll)
  placesShow(player, place)
})
