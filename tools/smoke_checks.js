// Dev-only checks the smoke test (tools/smoke.py) runs on the headless server; never part of the pack.
// A failure is thrown, so KubeJS logs it as an error and the smoke test fails.
//
// Recipe-viewer mixins: GregTech bundles ModularUI, whose mixins into JEI's recipe layout classes
// only run when those classes load, which on a client happens the first time EMI draws a JEI-plugin
// recipe (all of Create's). If one fails, every such recipe shows "render failure" in EMI. Loading
// the classes here applies the same mixins on the server, so a JEI or GregTech update that breaks
// them shows up in the smoke test. (JEI 19.50+ removed a field ModularUI 3.3.1 needs; see
// docs/design.md, "Upstream issues".)
ServerEvents.loaded(event => {
  ;['mezz.jei.library.gui.ingredients.RecipeSlot', 'mezz.jei.library.gui.recipes.RecipeLayout',
    'mezz.jei.library.gui.recipes.layout.builder.RecipeLayoutBuilder', 'mezz.jei.gui.recipes.RecipeGuiLogic'].forEach(name => {
    Java.loadClass(name)
  })
  console.info('[smoke-checks] JEI recipe layout classes load with their mixins')
})
