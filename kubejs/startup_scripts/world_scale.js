// New worlds use a 20 m per block Earth (docs/design.md: "World scale").
//
// TFC: Real World caps its map radius at 100,000 blocks (~172 m per block) in config/tfc_real_world/
// common.toml and on the create-world tab, but reads each world's own serverconfig/tfc_real_world/
// server.toml without that cap. When a world starts for the first time the mod copies common.toml
// into server.toml; this runs just before that and writes server.toml itself, with the 20 m scale
// in place of the default (and maximum) 100,000 x 50,000. A world that already has a server.toml
// (every world after its first start, or one an admin prepared) and any other scale a player chose
// on the create-world tab are left alone.
//
// Files go through NightConfig (NeoForge's TOML library) and Minecraft's FileUtil; KubeJS doesn't let
// scripts use java.nio.

const $WorldScalePriority = Java.loadClass('net.neoforged.bus.api.EventPriority')
const $WorldScaleAboutToStart = Java.loadClass('net.neoforged.neoforge.event.server.ServerAboutToStartEvent')
const $WorldScaleLevelResource = Java.loadClass('net.minecraft.world.level.storage.LevelResource')
const $WorldScaleToml = Java.loadClass('com.electronwill.nightconfig.core.file.CommentedFileConfig')
const $WorldScaleNotFound = Java.loadClass('com.electronwill.nightconfig.core.file.FileNotFoundAction')
const $WorldScaleInteger = Java.loadClass('java.lang.Integer')
const $WorldScaleFileUtil = Java.loadClass('net.minecraft.FileUtil')

// Equal Earth half extents at 1:1 are 17,243,963 x 8,392,930 m; divided by 20 m per block.
const WORLD_SCALE_FROM = { h: 100000, v: 50000 }
const WORLD_SCALE_TO = { h: 862198, v: 419647 }
// Key paths as lists: from JS a dotted string would reach NightConfig's get/set(List) as one key.
const WORLD_SCALE_H_KEY = ['generation_modes', 'horizontal_scale']
const WORLD_SCALE_V_KEY = ['generation_modes', 'vertical_scale']

NativeEvents.onEvent($WorldScalePriority.HIGHEST, $WorldScaleAboutToStart, event => {
  // An exception here would stop the world from loading; on any error the mod's own copy of
  // common.toml (~172 m per block) applies instead.
  try {
    worldScaleNewWorld(event.getServer())
  } catch (e) {
    console.error(`[world-scale] couldn't set the 20 m scale, using common.toml's: ${e}`)
  }
})

function worldScaleNewWorld(server) {
  // NightConfig's builder(File) and builder(Path) both match a Path from JS, so the overload is named.
  // resolve(String) by name: KubeJS turns a string into a game-directory Path, and resolve(Path)
  // with that absolute path would drop the world folder.
  var targetPath = server.getWorldPath($WorldScaleLevelResource.ROOT)['resolve(java.lang.String)']('serverconfig/tfc_real_world/server.toml')
  var commonPath = server.getServerDirectory()['resolve(java.lang.String)']('config/tfc_real_world/common.toml')

  var existing = $WorldScaleToml['builder(java.nio.file.Path)'](targetPath).onFileNotFound($WorldScaleNotFound.READ_NOTHING).build()
  existing.load()
  var isNew = existing.isEmpty()
  existing.close()
  if (!isNew) return

  var common = $WorldScaleToml['builder(java.nio.file.Path)'](commonPath).onFileNotFound($WorldScaleNotFound.READ_NOTHING).preserveInsertionOrder().build()
  common.load()
  var h = common.get(WORLD_SCALE_H_KEY)
  var v = common.get(WORLD_SCALE_V_KEY)
  if (common.isEmpty() || Number(h) !== WORLD_SCALE_FROM.h || Number(v) !== WORLD_SCALE_FROM.v) {
    console.info(`[world-scale] new world keeps the map radius from ${commonPath} (${h} x ${v}, ${common.size()} entries)`)
    common.close()
    return
  }

  $WorldScaleFileUtil.createDirectoriesSafe(targetPath.getParent())
  var target = $WorldScaleToml['builder(java.nio.file.Path)'](targetPath).onFileNotFound($WorldScaleNotFound.CREATE_EMPTY).preserveInsertionOrder().sync().build()
  target.load()
  target.putAll(common)
  target.putAllComments(common)
  target.set(WORLD_SCALE_H_KEY, $WorldScaleInteger.valueOf(WORLD_SCALE_TO.h))
  target.set(WORLD_SCALE_V_KEY, $WorldScaleInteger.valueOf(WORLD_SCALE_TO.v))
  target.save()
  target.close()
  common.close()
  console.info(`[world-scale] new world: map radius ${WORLD_SCALE_TO.h} x ${WORLD_SCALE_TO.v} blocks (20 m per block) in ${targetPath}`)
}
