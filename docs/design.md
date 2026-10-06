# Pack design

TerraFirmaCraft on a real-scale Earth, mechanized with Create, industrialized with GregTech,
with Create Aeronautics for travel. Minecraft 1.21.1, NeoForge.

Decided 2026-10-06. The progression checker (`tools/recipes/progression.json`) encodes these
decisions as rules; when a rule breaks, the explorer shows the shortcut.

## Decisions

| Area | Decision |
|---|---|
| Era order | **TFC → Create → GregTech.** TFC carries stone → copper → bronze → wrought iron → steel; Create mechanizes from the bronze age; GregTech's steam age builds on Create. |
| Unification | **TFC items win** for every metal TFC has (copper, bronze family, brass, tin, zinc, nickel, silver, gold, wrought/pig/cast iron, the steels), over vanilla too. Exceptions: vanilla lapis and emerald win, because enchanting and villager trading only accept the vanilla items. **Iron means TFC wrought iron**: Almost Unified maps iron ingots, nuggets, blocks, plates and rods onto wrought iron. Ore blocks aren't unified; TFC's per-rock ores are the real ores. GregTech items cover materials TFC doesn't have. |
| GregTech ores | **Off.** GregTech's raw materials come from TFC ores, processed in GregTech machines. GregTech-only minerals come from its processing chains, or are added later as TFC-style veins. |
| Difficulty | **Moderate.** TFC survival as designed, GregTech at default settings, Create gated but not punishing. |
| Create opens | **Bronze age.** Andesite alloy is made from TFC andesite + zinc or bronze nuggets, so water wheels, shafts and millstones arrive early. Heavy machines (mechanical press, mixer, deployer) need TFC wrought iron sheets. |
| GregTech steam | **Fire bricks + a Create part.** In GregTech's steam recipes, the vanilla furnace (uncraftable here) is replaced by TFC fire bricks plus a Create machine part, so GregTech builds on Create, which in practice means the wrought-iron age. GregTech's high-pressure steam and LV electrics need TFC steel. |
| Airships | **With Create's brass tier.** Create Aeronautics propellers and envelopes need brass (TFC brass = copper + zinc). |
| Create ↔ GregTech | **Through recipes**, no extra mods. Create machines make GregTech's early intermediates (pressed plates, rolled wires, milled dusts); GregTech machines need Create parts. |
| World scale | **~200 m per block, the maximum** TFC: Real World allows: map radius 100,000 × 50,000 (200,000 × 100,000 blocks). Ore and rock density per area are unchanged; climate zones and travel distances grow. |
| Starting place | Single-player: each player types a latitude/longitude when creating the world. Servers: a **once-per-player start command** (e.g. `/startat 59.33 18.07` for Stockholm) teleports a new player to a safe surface spot at that point. |
| Players | **Both** single-player and small servers; the headless smoke test stays part of every change. |

## Known blockers (from the recipe explorer)

- Create is unreachable: all andesite alloy recipes need `minecraft:andesite`, which TFC worlds don't contain (80 recipes depend on the alloy).
- GregTech's steam age is unreachable: its first boiler, steam furnace and steam alloy smelter need `minecraft:furnace`, which only a GregTech assembler can make.
- 67 unification tags hold items from several mods (two steels, three brasses, …).
- GregTech generates no ores in TFC worlds (its rubber trees do generate).
- TFC has no metal nuggets; zinc and bronze nuggets come from Create/GregTech and need a recipe from TFC ingots.

## Implementation order

1. ~~**Unification**~~ (done): `config/almostunified/` (TFC first, iron → wrought iron, ores excluded) plus `kubejs/server_scripts/unification/gregtech.js` for GregTech's recipes (see *Upstream issues*).
2. **Create entry**: andesite alloy from TFC andesite + zinc/bronze nuggets; nugget recipes from TFC ingots; wrought iron sheets in the press, mixer and deployer.
3. **GregTech steam entry**: swap the vanilla furnace for TFC fire bricks + a Create part in the ten recipes that use it, and vanilla bricks for TFC equivalents.
4. **GregTech ore processing**: GregTech ore generation off; TFC ore items accepted by macerators, ore washers and furnaces.
5. **Create ↔ GregTech recipe bridges**: Create press/rolling/milling recipes for GregTech plates, wires and dusts; Create parts in early GregTech machines.
6. **Airships at brass**: brass in propellers, envelopes and engines.
7. **World defaults**: `defaultconfigs/tfc_real_world/server.toml` with the 200 m/block scale; the `/startat` command for servers.

After each step: `tools/recipes/dump.py --label <step>`, compare dumps, check the Progression page, run `tools/smoke.py`.

## Upstream issues to track

- **Almost Unified 1.4.2 doesn't unify GregTech 8.0 recipes.** Its GregTech unifier reads the old capability keys (`item`), while GregTech 8.0 writes `gtceu:item`. Workaround: `kubejs/server_scripts/unification/gregtech.js` asks Almost Unified for each tag's winning item and applies it to GregTech recipes.
- **GregTech 8.0 drops its recycling recipes when any KubeJS recipe script exists.** `GTRecipes` skips recycling generation when KubeJS has recipe listeners, but the 1.21 KubeJS plugin no longer runs it afterwards (1.20.1 did, in `injectRuntimeRecipes`). About 3,300 macerator/arc furnace recycling recipes are missing; none are needed for progression. Recheck with a dump comparison after GregTech updates.
- **TFC clay-ball recipes fail after `/reload`** (stack size 16 vs. outputs of 20–32); fine after a restart.

## Open questions

- Which Create part goes into GregTech's first boiler (fluid tank, mechanical pump, or press)?
- Exact Create → GregTech bridge recipes, and which GregTech LV machines require Create parts.
- Whether GregTech-only minerals (bauxite, ilmenite, …) should become TFC-style veins later.
