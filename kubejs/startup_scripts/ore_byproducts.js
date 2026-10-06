// GregTech-only elements as by-products of TFC ores (docs/design.md: "GregTech ores").
//
// With GregTech's ore veins off, some elements had no source and progression stopped at early MV
// (arsenic for MV circuits, vanadium for the MV cutter, titanium, tungsten, neodymium and
// molybdenum later). Here they come out of TFC ores that carry them in real deposits, as GregTech
// by-products, so GregTech's own chains turn them into the element:
// - tetrahedrite grades into arsenic-bearing tennantite: realgar (centrifuge: arsenic, LV);
// - magnetite is often titanomagnetite: vanadium magnetite (centrifuge: vanadium, LV) and
//   ilmenite (electric blast furnace: rutile, then titanium, HV);
// - cassiterite placers and greisens carry monazite (rare earths: neodymium, LV) and scheelite
//   (tungsten, EV);
// - malachite caps porphyry copper deposits, whose molybdenite gives molybdenum (LV).
// Slot 0 is the ore washer's and the impure dust centrifuge's by-product, slot 1 the thermal
// centrifuge's and the pure dust centrifuge's, so each appears with LV machines. The by-products
// they replace (iron and tin from their own ores, zinc, bismuth, gold, calcite) all have TFC ores of
// their own.

const $ByproductMaterials = Java.loadClass('com.gregtechceu.gtceu.common.data.GTMaterials')
const $ByproductPropertyKey = Java.loadClass('com.gregtechceu.gtceu.api.data.chemical.material.properties.PropertyKey')
const $ByproductList = Java.loadClass('java.util.ArrayList')

// [ore material, by-product slot, new by-product]
const ORE_BYPRODUCTS = [
  ['Tetrahedrite', 1, 'Realgar'],
  ['Magnetite', 0, 'VanadiumMagnetite'],
  ['Magnetite', 1, 'Ilmenite'],
  ['Cassiterite', 0, 'Monazite'],
  ['Cassiterite', 1, 'Scheelite'],
  ['Malachite', 1, 'Molybdenite']
]

GTCEuStartupEvents.materialModification(event => {
  ORE_BYPRODUCTS.forEach(entry => {
    var ore = $ByproductMaterials[entry[0]].getProperty($ByproductPropertyKey.ORE)
    var list = new $ByproductList(ore.getOreByProducts())
    var added = $ByproductMaterials[entry[2]]
    while (list.size() <= entry[1]) list.add(added)
    var replaced = list.set(entry[1], added)
    ore['setOreByProducts(java.util.Collection)'](list)
    console.info(`[ore-byproducts] ${entry[0]} slot ${entry[1]}: ${replaced.getName()} -> ${added.getName()}`)
  })
})
