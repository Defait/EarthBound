// Apply Almost Unified's choices to GregTech recipes.
//
// Almost Unified 1.4.2's GregTech unifier reads the old capability keys ("item"), but GregTech
// 8.0 writes namespaced ones ("gtceu:item"), so GregTech's recipes keep GregTech's own ingots,
// plates and rods (e.g. 448 recipes still output gtceu:steel_ingot). Until that's fixed upstream,
// this asks Almost Unified which item won each tag and applies the same choice here:
// outputs become the winning item, and inputs that name a losing item accept the whole tag.
// See docs/design.md ("Unification": TFC items win).

ServerEvents.recipes(event => {
  var replaced = 0
  AlmostUnified.getTags().forEach(tag => {
    var target = AlmostUnified.getTagTargetItem(tag)
    if (target.isEmpty()) return
    var targetId = String(target.id)
    AlmostUnified.getTagEntries(tag).forEach(entry => {
      var id = String(entry)
      if (id === targetId) return
      event.replaceOutput({ mod: 'gtceu' }, id, targetId)
      event.replaceInput({ mod: 'gtceu' }, id, '#' + tag)
      replaced++
    })
  })
  console.info(`[unification] applied ${replaced} Almost Unified replacements to GregTech recipes`)
})
