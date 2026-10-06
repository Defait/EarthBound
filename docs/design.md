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
| Create opens | **Bronze age.** Andesite alloy is made from TFC igneous extrusive rock (andesite, basalt, dacite or rhyolite, raw or cobble; chosen so Create can start in most regions of a real-geology Earth) + zinc or bronze nuggets, so water wheels, shafts and millstones arrive early. Create uses TFC sheets wherever it used metal plates, and the mechanical press takes a wrought iron double sheet, so heavy machines (press, mixer, deployer, saw) need TFC wrought iron sheets. |
| GregTech steam | **Fire bricks + a Create mechanical pump.** Every GregTech boiler (coal, lava, solar; low and high pressure) needs a Create mechanical pump, and the vanilla furnace in GregTech's recipes becomes TFC fire bricks, so GregTech's steam age can't skip Create. With the pump being a bronze-age part, steam starts in the late bronze age (checker: first boiler at step 15, after the pump at 14 and before wrought iron at 19). GregTech's high-pressure steam and LV electrics need TFC steel. |
| Airships | **With Create's brass tier.** Create Aeronautics propellers and envelopes need brass (TFC brass = copper + zinc). |
| Create ↔ GregTech | **Through recipes**, no extra mods. Create machines make GregTech's early intermediates (pressed plates, rolled wires, milled dusts); GregTech machines need Create parts. |
| World scale | **~200 m per block, the maximum** TFC: Real World allows: map radius 100,000 × 50,000 (200,000 × 100,000 blocks). Ore and rock density per area are unchanged; climate zones and travel distances grow. |
| Starting place | Single-player: each player types a latitude/longitude when creating the world. Servers: a **once-per-player start command** (e.g. `/startat 59.33 18.07` for Stockholm) teleports a new player to a safe surface spot at that point. |
| Players | **Both** single-player and small servers; the headless smoke test stays part of every change. |

## Known blockers (from the recipe explorer)

- Create is unreachable: all andesite alloy recipes need `minecraft:andesite`, which TFC worlds don't contain (80 recipes depend on the alloy).
- GregTech's steam age is unreachable: its first boiler, steam furnace and steam alloy smelter need `minecraft:furnace`, which only a GregTech assembler can make.
- 67 unification tags hold items from several mods (two steels, three brasses, …).
- GregTech generates no ores in TFC worlds (its rubber trees do generate); its veins in the Nether and End are now off too.
- TFC has no metal nuggets; zinc and bronze nuggets come from Create/GregTech and need a recipe from TFC ingots.

## Implementation order

1. ~~**Unification**~~ (done): `config/almostunified/` (TFC first, iron → wrought iron, ores excluded) plus `kubejs/server_scripts/unification/gregtech.js` for GregTech's recipes (see *Upstream issues*).
2. ~~**Create entry**~~ (done): `kubejs/server_scripts/create/entry.js` (igneous extrusive rock for andesite, bronze nuggets, TFC sheets for plates, TFC diorite/granite for Create's stone recipes, TFC stripped logs in the common tags) and `kubejs/server_scripts/compat/vanilla_substitutes.js` (TFC workbenches count as crafting tables). Checker: andesite alloy step 7, water wheel 11, press 24, deployer 30, crushing wheel 31.
3. ~~**GregTech steam entry**~~ (done): `kubejs/server_scripts/gregtech/steam_entry.js`. Checker: first boiler step 15, steam macerator 17, high-pressure boiler 30.
4. ~~**GregTech ore processing**~~ (done): `kubejs/server_scripts/gregtech/ore_processing.js` (veins off, 67 macerator recipes for TFC ores) and `kubejs/server_scripts/compat/metal_gates.js` (GregTech's iron smelting gives cast iron, no chainmail → iron recycling, primitive blast furnace takes pig iron). Adding GregTech's furnaces and Create's fan as smelting stations in the checker exposed the chainmail and primitive-blast-furnace shortcuts, which already existed. Checker: steam macerator step 17, crushed ores 18, steel 27, LV machine hull 33. Sulfur from TFC sulfur and pyrite lets the steam alloy smelter vulcanize rubber, which cleared the tin cable blocker.
5. **Create ↔ GregTech recipe bridges**: Create press/rolling/milling recipes for GregTech plates, wires and dusts; Create parts in early GregTech machines. Known blockers past the LV hull: LV circuits need a glass tube (only an LV alloy smelter or a forming press makes one) and red alloy cable; the electric blast furnace needs a vanilla blast furnace (which needs a vanilla furnace, made only in a GregTech assembler) and invar for its heatproof casings.
6. **Airships at brass**: brass in propellers, envelopes and engines.
7. **World defaults**: `defaultconfigs/tfc_real_world/server.toml` with the 200 m/block scale; the `/startat` command for servers.

After each step: `tools/recipes/dump.py --label <step>`, compare dumps, check the Progression page, run `tools/smoke.py`.

## Upstream issues to track

- **Almost Unified 1.4.2 doesn't unify GregTech 8.0 recipes.** Its GregTech unifier reads the old capability keys (`item`), while GregTech 8.0 writes `gtceu:item`. Workaround: `kubejs/server_scripts/unification/gregtech.js` asks Almost Unified for each tag's winning item and applies it to GregTech recipes.
- **GregTech 8.0 drops its recycling recipes when any KubeJS recipe script exists.** `GTRecipes` skips recycling generation when KubeJS has recipe listeners, but the 1.21 KubeJS plugin no longer runs it afterwards (1.20.1 did, in `injectRuntimeRecipes`). About 3,300 macerator/arc furnace recycling recipes are missing; none are needed for progression. Recheck with a dump comparison after GregTech updates.
- **TFC clay-ball recipes fail after `/reload`** (stack size 16 vs. outputs of 20–32); fine after a restart.

## Open questions

- Exact Create → GregTech bridge recipes, and which GregTech LV machines require Create parts.
- Whether GregTech-only minerals (bauxite, ilmenite, …) should become TFC-style veins later.
