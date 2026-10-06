// /startat <latitude> <longitude>: a once-per-player start anywhere on Earth (docs/design.md:
// "Starting place").
//
// Single-player worlds choose their spawn latitude/longitude on TFC: Real World's create-world tab.
// On a server everyone arrives at the server's spawn, and each player can then use /startat once
// to move to a real place, e.g. /startat 59.33 18.07 for Stockholm. The point is projected the
// way world generation projects it; if it's water (or the map is too coarse to have the city on
// land) the nearest dry ground within 48 blocks is used. The player is teleported there and it
// becomes their respawn point. Operators can use it any number of times, and
// /startat reset <player> gives a player their use back.

const $ProjectionManager = Java.loadClass('net.yazloysasha.tfcrealworld.util.projection.ProjectionManager')
const $Heightmap = Java.loadClass('net.minecraft.world.level.levelgen.Heightmap$Types')
const $BlockPos = Java.loadClass('net.minecraft.core.BlockPos')
const $Level = Java.loadClass('net.minecraft.world.level.Level')

const STARTAT_USED = 'pack_startat_used'
const STARTAT_SEARCH = 48
const STARTAT_STEP = 8

// Dry ground at the top of column (x, z), or null for water, lava or the void. Loads (and if
// needed generates) the chunk first; the height of an unloaded column reads as the world bottom.
function startAtSurface(level, x, z) {
  level.getChunk(x >> 4, z >> 4)
  var y = level.getHeight($Heightmap.MOTION_BLOCKING_NO_LEAVES, x, z)
  if (y <= level.getMinBuildHeight()) return null
  if (!level.getBlockState(new $BlockPos(x, y - 1, z)).getFluidState().isEmpty()) return null
  return { x: x, y: y, z: z }
}

// Block position for a latitude/longitude, then dry ground nearest to it in growing square rings.
function startAtFind(level, lat, lon) {
  var xz = $ProjectionManager.geographicToClassic(lon, lat)
  var cx = Math.round(xz[0])
  var cz = Math.round(xz[1])
  for (var r = 0; r <= STARTAT_SEARCH; r += STARTAT_STEP) {
    for (var dx = -r; dx <= r; dx += STARTAT_STEP) {
      for (var dz = -r; dz <= r; dz += STARTAT_STEP) {
        if (Math.max(Math.abs(dx), Math.abs(dz)) !== r) continue
        var spot = startAtSurface(level, cx + dx, cz + dz)
        if (spot) return { point: { x: cx, z: cz }, spot: spot }
      }
    }
  }
  return { point: { x: cx, z: cz }, spot: null }
}

function startAtPlace(lat, lon) {
  return `${Math.abs(lat).toFixed(2)}°${lat >= 0 ? 'N' : 'S'} ${Math.abs(lon).toFixed(2)}°${lon >= 0 ? 'E' : 'W'}`
}

ServerEvents.commandRegistry(event => {
  var Commands = event.commands
  var Arguments = event.arguments

  // Java command exceptions thrown inside these callbacks reach players only as "An unexpected
  // error occurred", so the commands check for those cases themselves.
  function run(ctx) {
    var source = ctx.source
    var player = source.getPlayer()
    if (!player) {
      source.sendFailure(Text.red('Only players can use /startat.'))
      return 0
    }
    var server = source.server
    var lat = Arguments.DOUBLE.getResult(ctx, 'latitude')
    var lon = Arguments.DOUBLE.getResult(ctx, 'longitude')
    if (lat < -90 || lat > 90 || lon < -180 || lon > 180) {
      source.sendFailure(Text.red('Latitude must be -90 to 90 and longitude -180 to 180 (south and west are negative).'))
      return 0
    }
    var used = server.persistentData.getCompound(STARTAT_USED)
    var uuid = String(player.profile.id)
    var unlimited = source.hasPermission(2)
    if (used.getBoolean(uuid) && !unlimited) {
      source.sendFailure(Text.red('You have already used /startat. An operator can give it back with /startat reset.'))
      return 0
    }

    var level = server.overworld()
    var found = startAtFind(level, lat, lon)
    if (!found.spot) {
      source.sendFailure(Text.red(`${startAtPlace(lat, lon)} (x ${found.point.x}, z ${found.point.z}) is open water. Pick a point on land; your /startat is still unused.`))
      return 0
    }
    var s = found.spot
    try {
      player.teleportToLevel(level, s.x + 0.5, s.y, s.z + 0.5, player.yaw, player.pitch)
      player.setRespawnPosition($Level.OVERWORLD, new $BlockPos(s.x, s.y, s.z), 0.0, true, false)
    } catch (e) {
      console.error(`[startat] moving ${player.username} to ${s.x} ${s.y} ${s.z} failed: ${e}`)
      source.sendFailure(Text.red('The teleport failed (see the server log); your /startat is still unused.'))
      return 0
    }
    if (!unlimited) {
      used.putBoolean(uuid, true)
      server.persistentData.put(STARTAT_USED, used)
    }
    player.tell(Text.green(`Welcome to ${startAtPlace(lat, lon)} (x ${s.x}, y ${s.y}, z ${s.z}). This is now your respawn point.`)
      .append(unlimited ? '' : Text.gray(' That was your one /startat.')))
    return 1
  }

  event.register(Commands.literal('startat')
    .then(Commands.literal('reset')
      .requires(source => source.hasPermission(2))
      .then(Commands.argument('player', Arguments.PLAYER.create(event))
        .executes(ctx => {
          var target = null
          try {
            target = Arguments.PLAYER.getResult(ctx, 'player')
          } catch (e) {
            ctx.source.sendFailure(Text.red('No such player online.'))
            return 0
          }
          var used = ctx.source.server.persistentData.getCompound(STARTAT_USED)
          used.remove(String(target.profile.id))
          ctx.source.server.persistentData.put(STARTAT_USED, used)
          ctx.source.sendSuccess(() => Text.of(`${target.username} can use /startat again.`), true)
          return 1
        })))
    .then(Commands.argument('latitude', Arguments.DOUBLE.create(event))
      .then(Commands.argument('longitude', Arguments.DOUBLE.create(event))
        .executes(ctx => run(ctx)))))
})
