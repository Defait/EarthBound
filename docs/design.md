# Pack design

TerraFirmaCraft on a real-scale Earth, mechanized with Create, industrialized with GregTech,
with Create Aeronautics for travel. Minecraft 1.21.1, NeoForge.

Decided 2026-10-06. The progression checker (`tools/recipes/progression.json`) encodes these
decisions as rules; when a rule breaks, the explorer shows the shortcut.

## Decisions

| Area | Decision |
|---|---|
| Era order | **TFC → Create → GregTech.** TFC carries stone → copper → bronze → wrought iron → steel; Create mechanizes from the bronze age; GregTech's steam age builds on Create. Iron and steel stay TFC milestones whichever mod's machines do the work: wrought iron comes only from the bloomery (anything iron that's smelted or melted becomes cast iron, as in TFC), and steel only from TFC pig iron (GregTech's primitive blast furnace refines pig iron instead of iron). |
| Unification | **TFC items win** for every metal TFC has (copper, bronze family, brass, tin, zinc, nickel, silver, gold, wrought/pig/cast iron, the steels), over vanilla too. Exceptions: vanilla lapis and emerald win, because enchanting and villager trading only accept the vanilla items. **Iron means TFC wrought iron**: Almost Unified maps iron ingots, nuggets, blocks, plates and rods onto wrought iron. Ore blocks aren't unified; TFC's per-rock ores are the real ores. GregTech items cover materials TFC doesn't have. |
| GregTech ores | **Off.** GregTech's ore veins are switched off everywhere (TFC's overworld never placed them; the Nether and End would have). GregTech's raw materials come from TFC ores: the macerator turns TFC ore pieces into GregTech crushed ore at twice TFC's yield (the way it doubles a vanilla raw ore; one crushed ore per 50 mB of TFC metal), and mineral and gem ores count as a GregTech ore block (1 → 2 crushed). From there GregTech's usual chain applies. GregTech-only minerals come from its processing chains, or are added later as TFC-style veins. |
| Difficulty | **Moderate.** TFC survival as designed, GregTech at default settings, Create gated but not punishing. |
| Create opens | **Bronze age.** Andesite alloy is made from TFC igneous extrusive rock (andesite, basalt, dacite or rhyolite, raw or cobble; chosen so Create can start in most regions of a real-geology Earth) + zinc or bronze nuggets, so water wheels, shafts and millstones arrive early. Create uses TFC sheets wherever it used metal plates, and the mechanical press takes a wrought iron double sheet, so heavy machines (press, mixer, deployer, saw) need TFC wrought iron sheets. Create's belts, spout, funnels, tunnels and pulleys take leather or TFC burlap cloth (or either kind of dried kelp) instead of vanilla dried kelp, which TFC worlds lack. |
| GregTech steam | **Fire bricks + a Create mechanical pump.** Every GregTech boiler (coal, lava, solar; low and high pressure) needs a Create mechanical pump, and the vanilla furnace in GregTech's recipes becomes TFC fire bricks, so GregTech's steam age can't skip Create. With the pump being a bronze-age part, steam starts in the late bronze age (checker: first boiler at step 15, after the pump at 14 and before wrought iron at 19). GregTech's high-pressure steam and LV electrics need TFC steel. |
| Airships | **With Create's brass tier.** Create Aeronautics propellers and envelopes need brass (TFC brass = copper + zinc). |
| Create ↔ GregTech | **Through recipes**, no extra mods. Create makes GregTech's early intermediates: the press makes GregTech plates from ingots (one for one, like GregTech's bender), the saw slits plates into wires (two per plate, like the wiremill), and crushing wheels and the millstone crush TFC ores into GregTech crushed ore (crushing wheels at the macerator's rate, the millstone at TFC's yield). GregTech's LV components are built from Create parts, like for like: motors around Create shafts, pumps around a Create mechanical pump, pistons geared with a Create cogwheel. And all GregTech power comes from boilers (steam turbines for electricity), so nothing in GregTech runs without Create. The electric blast furnace is built from TFC's blast furnace instead of the vanilla one. |
| World scale | **~200 m per block, the maximum** TFC: Real World allows: map radius 100,000 × 50,000 (200,000 × 100,000 blocks). Ore and rock density per area are unchanged; climate zones and travel distances grow. |
| Starting place | Single-player: each player types a latitude/longitude when creating the world. Servers: a **once-per-player start command** (e.g. `/startat 59.33 18.07` for Stockholm) teleports a new player to a safe surface spot at that point. |
| Players | **Both** single-player and small servers; the headless smoke test stays part of every change. |

## Known gaps (from the recipe explorer)

The first blockers (no vanilla andesite for Create, no vanilla furnace for GregTech's steam age, duplicate materials across mods, no TFC nuggets, no dried kelp) are fixed by steps 1–5. Still open:

- Create's blaze burner needs the Nether (netherrack, a blaze), so Create's heated and superheated mixing wait for it. TFC's alloying covers brass.
- Aeronautics' adjustable burner (hot-air balloons) needs a vanilla coal block, and Simulated's red portable engine a vanilla blast furnace (only a GregTech LV assembler makes one); both for step 6.
- Cosmetic: Create's decorative stones (asurine, limestone, …) need vanilla stones TFC doesn't generate; waxing copper needs honeycomb.

## Implementation order

1. ~~**Unification**~~ (done): `config/almostunified/` (TFC first, iron → wrought iron, ores excluded) plus `kubejs/server_scripts/unification/gregtech.js` for GregTech's recipes (see *Upstream issues*).
2. ~~**Create entry**~~ (done): `kubejs/server_scripts/create/entry.js` (igneous extrusive rock for andesite, bronze nuggets, TFC sheets for plates, TFC diorite/granite for Create's stone recipes, TFC stripped logs in the common tags) and `kubejs/server_scripts/compat/vanilla_substitutes.js` (TFC workbenches count as crafting tables). Checker: andesite alloy step 7, water wheel 11, press 24, deployer 30, crushing wheel 31.
3. ~~**GregTech steam entry**~~ (done): `kubejs/server_scripts/gregtech/steam_entry.js`. Checker: first boiler step 15, steam macerator 17, high-pressure boiler 30.
4. ~~**GregTech ore processing**~~ (done): `kubejs/server_scripts/gregtech/ore_processing.js` (veins off, 67 macerator recipes for TFC ores) and `kubejs/server_scripts/compat/metal_gates.js` (GregTech's iron smelting gives cast iron, no chainmail → iron recycling, primitive blast furnace takes pig iron). Adding GregTech's furnaces and Create's fan as smelting stations in the checker exposed the chainmail and primitive-blast-furnace shortcuts, which already existed. Checker: steam macerator step 17, crushed ores 18, steel 27, LV machine hull 33. Sulfur from TFC sulfur and pyrite lets the steam alloy smelter vulcanize rubber, which cleared the tin cable blocker.
5. ~~**Create ↔ GregTech recipe bridges**~~ (done): `kubejs/server_scripts/bridges/create_gregtech.js` (press → plates for 23 more metals, saw → wires for 10, Create shafts/pumps/cogwheels in LV motors/pumps/pistons), Create crushing and milling of TFC ores in `gregtech/ore_processing.js`, and in `compat/vanilla_substitutes.js` the belting substitute for dried kelp and TFC's blast furnace in the electric blast furnace. The checker now models power (steam machines need a boiler, electric machines a generator with fuel) and knows that steam machines run any LV-tier recipe; without power modeled it had GregTech running without Create. Checker: belt connector step 13, first crushed ore 12 (millstone), LV motor 27, LV machine hull 30, electric blast furnace 34, electricity 35 (steam turbine).
6. **Airships at brass**: brass in propellers, envelopes and engines; a TFC fuel block for the adjustable burner; a TFC blast furnace (or another part) in the red portable engine.
7. **World defaults**: `defaultconfigs/tfc_real_world/server.toml` with the 200 m/block scale; the `/startat` command for servers.

After each step: `tools/recipes/dump.py --label <step>`, compare dumps, check the Progression page, run `tools/smoke.py`.

## Upstream issues to track

- **Almost Unified 1.4.2 doesn't unify GregTech 8.0 recipes.** Its GregTech unifier reads the old capability keys (`item`), while GregTech 8.0 writes `gtceu:item`. Workaround: `kubejs/server_scripts/unification/gregtech.js` asks Almost Unified for each tag's winning item and applies it to GregTech recipes.
- **GregTech 8.0 drops its recycling recipes when any KubeJS recipe script exists.** `GTRecipes` skips recycling generation when KubeJS has recipe listeners, but the 1.21 KubeJS plugin no longer runs it afterwards (1.20.1 did, in `injectRuntimeRecipes`). About 3,300 macerator/arc furnace recycling recipes are missing; none are needed for progression. Recheck with a dump comparison after GregTech updates.
- **TFC clay-ball recipes fail after `/reload`** (stack size 16 vs. outputs of 20–32); fine after a restart.

## Open questions

- Nether access in a TFC world (portals, blazes) and whether Create's blaze burner should get another route.
- Whether GregTech-only minerals (bauxite, ilmenite, …) should become TFC-style veins later.
