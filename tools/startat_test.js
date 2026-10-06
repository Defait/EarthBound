// Dev-only check of /startat (kubejs/server_scripts/world/startat.js), run by tools/startat_test.py.
// Copied into the test server's local/kubejs/local_server_scripts; never part of the pack.
// Note: function-local variables use var; Rhino rejects block-scoped const in callbacks that run repeatedly.
const $StartAtTestFakePlayers = Java.loadClass('net.neoforged.neoforge.common.util.FakePlayerFactory')
const $StartAtTestProfile = Java.loadClass('com.mojang.authlib.GameProfile')
const $StartAtTestUUID = Java.loadClass('java.util.UUID')

ServerEvents.loaded(event => {
  var server = event.server
  var level = server.overworld()
  var failures = 0
  function check(name, ok, detail) {
    if (!ok) failures++
    console.info(`[startat-test] ${ok ? 'PASS' : 'FAIL'} ${name}: ${detail}`)
  }

  // The finder: land at or near real places, nothing in open ocean.
  ;[['Rome', 41.89, 12.51], ['Stockholm', 59.33, 18.07], ['Shanghai', 31.23, 121.47], ['Cape Town', -33.92, 18.42],
    ['Lima', -12.05, -77.04]].forEach(p => {
    var r = startAtFind(level, p[1], p[2])
    var detail = r.spot ? `point ${r.point.x},${r.point.z} -> ${r.spot.x},${r.spot.y},${r.spot.z}` : `point ${r.point.x},${r.point.z}, no dry ground`
    check(`finds land at ${p[0]}`, !!r.spot, detail)
  })
  var ocean = startAtFind(level, 30.0, -40.0)
  check('refuses the mid-Atlantic', !ocean.spot, `point ${ocean.point.x},${ocean.point.z}`)

  // The command, as a non-op player whose messages go to the console.
  var fake = $StartAtTestFakePlayers.get(level, new $StartAtTestProfile($StartAtTestUUID.fromString('00000000-0000-0000-0000-00000000beef'), 'startat_tester'))
  var source = fake.createCommandSourceStack().withSource(server).withPermission(0)
  var key = String(fake.profile.id)
  function run(cmd) {
    server.getCommands().performPrefixedCommand(source, cmd)
    var pos = fake.blockPosition()
    var respawn = fake.getRespawnPosition()
    return { x: Number(pos.x), y: Number(pos.y), z: Number(pos.z), respawn: respawn ? `${respawn.x},${respawn.y},${respawn.z}` : null,
      used: server.persistentData.getCompound('pack_startat_used').getBoolean(key) }
  }
  var before = fake.blockPosition()
  var s = run('startat 30 -40')
  check('open water keeps the use', !s.used && s.x === Number(before.x) && s.z === Number(before.z), JSON.stringify(s))
  var stockholm = startAtFind(level, 59.33, 18.07).spot
  s = run('startat 59.33 18.07')
  check('teleports to Stockholm', s.x === stockholm.x && s.z === stockholm.z && s.used, JSON.stringify(s))
  check('sets the respawn point', s.respawn === `${stockholm.x},${stockholm.y},${stockholm.z}`, String(s.respawn))
  s = run('startat 31.23 121.47')
  check('refuses a second use', s.x === stockholm.x && s.z === stockholm.z, JSON.stringify(s))
  s = run('startat 100 0')
  check('rejects latitude 100', s.x === stockholm.x && s.z === stockholm.z, JSON.stringify(s))

  server.persistentData.getCompound('pack_startat_used').remove(key)
  console.info(`[startat-test] done: ${failures} failed`)
})
