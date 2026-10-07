// Fowl Play's birds spawn only where TFC's climate suits them (docs/design.md: "Atmosphere").
//
// TFC's own animals carry a fauna definition (temperature, groundwater, forest density) that their
// spawn rules check; each Fowl Play bird gets one too, in kubejs/data/fowlplay/tfc/fauna/, and KubeJS
// TFC replaces Fowl Play's spawn rules with it. Replace, not combine: Fowl Play's tree birds want vanilla
// leaves under them, which TFC's leaves aren't, and its water and shore birds would otherwise spawn on any
// water or shore in any climate. Tree birds spawn on open ground (clearings, forest edges) and fly up to
// perch; geese and gulls on the surface, water included. tools/smoke_checks.js checks that the climate
// rule is the one that applies. Fowl Play's duck and penguin aren't here: TFC has both, so server_scripts/compat/fowl_play.js
// gives them no biomes. Adapted from TerraFirmaGreg (LGPL-3.0, see licenses/TerraFirmaGreg-quests.txt).

const $FowlPlayHeightmap = Java.loadClass('net.minecraft.world.level.levelgen.Heightmap$Types')

TFCEvents.faunaSpawns(event => {
  ;['blue_jay', 'cardinal', 'chickadee', 'crow', 'hawk', 'pigeon', 'raven', 'robin', 'sparrow'].forEach(bird => {
    event.replace(`fowlplay:${bird}`, event.onGround(), $FowlPlayHeightmap.WORLD_SURFACE)
  })
  ;['goose', 'gull'].forEach(bird => {
    event.replace(`fowlplay:${bird}`, event.noRestrictions(), $FowlPlayHeightmap.WORLD_SURFACE)
  })
})
