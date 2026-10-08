// ArborFirmaCraft against the pack's gates (docs/design.md: "Structure mods").
//
// AFC's trees grow in forests next to (and, in places, instead of) TFC's, so anything the pack
// asks of a TFC tree has to accept an AFC tree too, or a start in an AFC forest is cut off:
// - Create's casings (andesite, copper, brass) are made from a stripped log or wood. The pack
//   put only TFC's stripped logs and woods into the common tags (create/entry.js), and AFC's
//   stripped logs are in no common tag, so an AFC-only forest could not open Create at all.
//
// What is deliberately left alone, because AFC already sits behind the right gates:
// - The tree tap is anvil-made from a wrought iron sheet, so sap, syrup, sugar and latex are
//   iron-age (checker: tap 23, latex 24, rubber bar 25, sugar 26); TFC's own sugar (12) and glue
//   (13) stay cheaper, so AFC gives no early shortcut. A progression rule keeps it that way.
// - AFC's latex, rubber bar, sap and syrup are in no common item or fluid tag, so they feed no
//   GregTech recipe: GregTech's rubber (an LV gate) still comes from its own resin and chemistry.
//   Nothing consumes the rubber bar. Its only GregTech overlap is the wood tags (planks, logs,
//   chests, sticks, saplings), where AFC wood does what TFC wood does.

ServerEvents.tags('item', event => {
  event.add('c:stripped_logs', /^afc:wood\/stripped_log\//)
  event.add('c:stripped_woods', /^afc:wood\/stripped_wood\//)
})
