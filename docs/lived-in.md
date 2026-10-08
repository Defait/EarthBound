# A lived-in overworld: ruins, rare inhabitants and ancient sites

Designed and partly built 2026-10-07. *Status* below is what exists, how it tested, how to build the
mod, how to add hand-built templates and what to look at in game. The numbered sections after it are
the design as reviewed, kept for the reasoning and for the parts still to build; the questions in §8
were answered with the defaults offered there.

Sources: `docs/design.md` (the authority), `tools/README.md`, research notes kept outside the repo
(TFC jar findings, processor and Easy NPC source reading), `javap` (JDK 22) on the jars in
`tools/.server/mods` and `tools/.server/libraries`, the TFC 1.21.x source, Easy NPC's source (branch
`1.21.1`, commit 2c7fb93), and the newest recipe
dump (`tools/.data/dumps/20261007-102324-diorite`) plus `tools/quests/pack_query.py` for item ids and
progression steps. "Verified" below means read in bytecode or source in this session; anything else is
marked *unverified*.

---

## Status (2026-10-07)

### What is built

| Part | Where | State |
|---|---|---|
| The mod, `pack_world` 1.2.0 | source in `mod/`, jar in `mods/pack_world-1.2.0.jar` (both sides) | `local_materials` and `npc_fixup` processors, `geographic` placement with `SiteGuard` and `/pack_world sites`, the `climate` loot condition, `PackWorldApi` for tests, (1.1.0) the structure skin for other mods' structures (below): one mixin, into `StructureStart.placeInChunk`, and (1.2.0) the settlements' side (*Settlements*, below): the `pack_world:region` placement, the `pack_world:guarded_jigsaw` structure type with `/pack_world guard`, wood ranks (ArborFirmaCraft's trees included), Roads and Roofs and Framed Blocks camouflage in `local_materials`. About 3,600 lines, no blocks or items. |
| Generator | `tools/structures/` (`catalogue.json`, `build.py`, `shapes.py`, `nbt.py`, and for the settlements `villages.py`, `tfg_import.py`, `village_tune.py`) | 15 structures, 3 NPCs and 10 sites in the catalogue, and 7 villages (9 structures, 146 templates, 20 NPCs). 9 structures generate today, from 24 procedural variants; 6 structures and the 10 sites wait for hand-built templates. |
| Generated data | `kubejs/data/pack/`: `worldgen/{structure,structure_set,template_pool,processor_list}/`, `structure/`, `loot_table/chests/`, `tags/worldgen/biome/has_structure/`, `tags/block/ruin_rottable.json`, `easy_npc/preset/humanoid/`; `config/tfc_real_world/geography/pack/waypoints/` | written by `build.py`; edit the catalogue, not these. The cave files in the same namespace are never touched. |
| Easy NPC 7.14.0 | `mods/easy-npc-core.pw.toml`, `mods/easy-npc-config-ui.pw.toml` (both sides) | draft presets for the trader, smith and hermit, generated from the catalogue |
| Tests | `tools/structures_test.py` + `.js` (the villages too); `tools/structure_mods/village_census.py` (villages in a generated world); `mod/checks/RegionGeometryCheck.java` (the region geometry, no server); `tools/worldgen_check.py`, `.js` and `tools/mclib/jarscan.py` (§6); `tools/mod_report.py` lists the local jar | see below |

Live: hunters' camp, prospector's camp, mine adit, bloomery ruin, cairn, standing stones, wayside shrine,
barrow, wreck, and the seven villages of *Settlements* (below). Waiting for templates: the three homesteads, the trading post, the hermit and the
travelling smith (the inhabited spots), and the ten sites; `build.py` lists them and writes their
structure, set, pool and tag as soon as a template is there. The sites' waypoints are already in TFC:
Real World's geography screen ("Ancient site"), so they show on the map before anything stands there.

Differences from the design below:

- **Foundation per column.** TFC's terrain adaptation only fills about 2 blocks under a structure, so
  `local_materials` grows a foundation down from each column that rests on the template's ground layer
  to the terrain, inside the chunk being generated, up to `max_depth` (4 for camps and the shrine, 6
  for the cairn, bloomery and adit, 10 for the barrow; the stones and the wreck need none). The ground
  layer comes from the catalogue variant (`ground`), so hand-built templates get it too.
- **Wreck spacing 20 chunks** (separation 6): it only fits beaches and shores, so even then it is rare.
- **NPCs are generated drafts** (Easy NPC's humanoid with its default skin, the catalogue's name,
  greeting, tips and barter trades), until the author edits them in game and exports them (below).
- **The strict alloy rule removes loose rocks.** Where the local rock is andesite, basalt, dacite,
  rhyolite or diorite, a ruin's raw rock becomes smooth, cobble becomes cracked bricks, mossy cobble
  mossy bricks, and loose rocks are left out (they have no worked form).
- **Structures don't avoid each other** (no exclusion zones between sets); at these densities overlaps
  are rare.

### What is tested and how it came out

`tools/structures_test.py` on a fresh world at six places (Rome, Stockholm, Lhasa, Manaus, Cairo, Kansas):

- **Local materials.** Every placeholder of every template, through the mod's own code, for all 21 TFC
  rocks (with the alloy rule), 20 woods, 8 soils and 7 sands: every result exists and nothing stays a
  placeholder. In 54 copies generated the way `/place` does and 24 structures found where they generate
  naturally: no placeholder leaked, no vanilla block, no rough alloy rock, and no rock or wood other
  than the local ones (TFC's own rock generator and forest config at the structure's anchor).
- **Floating.** Natural structures (terrain adaptation, foundation and decoration as in play): none of
  1,168 ground columns float. Copies placed into existing terrain (no terrain adaptation, so worse than
  play): 2 of 2,406 columns over a 2-block gap (one each at a wayside shrine near Lhasa and a hunters'
  camp near Manaus). Two fixes came out of this: the barrow (up to 39 of 76 columns over gaps of up to
  9 blocks on slopes) and the mine adit (its portal and spoil heap, up to 8 of 9 columns over 4 blocks)
  now grow foundations; both test clean.
- **Natural decoration comes after structures.** TFC places boulders, forest, loose rocks and snow in
  later generation steps, so they can land on a structure: 2 of 24 natural samples were partly covered
  (boulders on a basalt cairn, natural diorite at a menhir). That is natural rock, not a leak.
- **Loot.** Every table rolled 200 times: all within the era caps, nothing on the deny-list (wrought
  iron and later metals, Create, GregTech, vanilla iron, the bloomery).
- **NPCs.** A test structure holding the trader as an entity and the smith as a single spawner, placed
  twice: two separate traders (own UUIDs), no owner, 11 trades and 3 dialogs kept, each one's home set
  where it stands; each spawner has its own spawner and NPC UUID, with no owner or home. Not tested: a
  spawner actually spawning (Easy NPC waits for a real player nearby), a player trading, NPC behaviour
  over days. Look at those in game.
- **Density**, structures per 1,000 × 1,000 blocks, averaged over ±8,000 blocks around the six places
  (from the placement grid, climate and biome, nothing generated): cairn 3.1, hunters' camp 1.9, wayside
  shrine 1.1, standing stones 1.1, barrow 0.67, prospector's camp 0.62, mine adit 0.56, bloomery ruin
  0.15, wreck 0.04. Together about 9 per km², one every ~330 blocks on average; more in temperate,
  wet country where most windows overlap, fewer in deserts and the far north.
- **worldgen_check.** `--golden` passes. The nine structures are accepted new-chunks-only additions in
  `tools/worldgen_baseline.json` (signatures recorded); the per-chunk census leaves out chunks any
  structure reaches, on both sides; biomes, chunk data, rock, ore and caves are unchanged.
- `smoke.py` passes with the mod and Easy NPC.

### Building the mod

ModDevGradle 2.0.148 on Gradle 9.2.1, against NeoForge 21.1.255. The wrapper was generated locally
(`gradle wrapper` from the downloaded distribution; its sha256 is pinned in
`gradle/wrapper/gradle-wrapper.properties`).

```
cd mod
JAVA_HOME="C:\Program Files\Java\jdk-22.0.1" ./gradlew build      # -> build/libs/pack_world-<version>.jar
```

The workaround: ModDevGradle asks for a Java 21 toolchain, for compiling and for NeoForm Runtime (which
decompiles and recompiles Minecraft). None is installed and Gradle must not download one
(`org.gradle.java.installations.auto-download=false` in `gradle.properties`), so `build.gradle` sets
the toolchain to the JDK running Gradle, points NeoForm Runtime's tasks at the same `java`, and
compiles with `--release 21`. Any JDK 21 or newer works. No client run is configured (it would
download Minecraft's assets) and no Parchment. TFC and TFC: Real World are compile-only, taken from
`tools/.server/mods` (on a fresh checkout, run any test tool first so they are there).

The first build downloaded about 433 MB: the Gradle 9.2.1 bin zip (135.5 MB, services.gradle.org),
209 MB of artifacts Gradle resolved (maven.neoforged.net 252 files, libraries.minecraft.net 127,
plugins.gradle.org 9, nothing from Maven Central), and from Mojang the Minecraft 1.21.1 client and
server jars (26.8 and 51.6 MB), client mappings (9.6 MB) and version manifests (0.3 MB). `~/.gradle` is
about 700 MB afterwards. Later builds download nothing.

The region geometry has an offline check that needs no server: after `./gradlew compileJava`, `"$JAVA_HOME/bin/java" -cp build/classes/java/main checks/RegionGeometryCheck.java` (an L-shaped polygon, densifying across the antimeridian, a box over it, a region over the map's seam, a shape the projection clamps to a sliver).

After a code change: build, copy the jar from `mod/build/libs/` into `mods/` (with a new version,
delete the old jar from `mods/` and from `tools/.server/mods`, since packwiz-installer never removes
files), `packwiz refresh`, then `structures_test.py` and `worldgen_check.py --golden`. The mod's classes
are hashed, so any change is a new-chunks-only finding; accept it with a reason once the tests pass.

### Adding hand-built templates

1. Build in a creative test world from the placeholder materials, which become the local ones: TFC
   granite blocks (raw, cobble, bricks, smooth, stairs, slabs, walls, ...) for the local rock, TFC oak
   (logs, planks, supports, fences, doors, chests, ...) for the climate's typical tree, alfisol soil
   (dirt, grass, farmland, mud bricks, ...) for the column's soil, and yellow sand and sandstone for the
   local sand. Only `tfc:` blocks, air, structure void and jigsaw blocks; the lint lists anything else.
2. Leave chests empty: every empty TFC chest gets the structure's loot table.
3. For an NPC, put a structure block in DATA mode where it stands, with the metadata `npc:trader`
   (an entity) or `npc:smith:spawner` (an Easy NPC single spawner); ids are the catalogue's `npcs`.
   To change an NPC, edit it in game with Easy NPC's editor, export the preset, and save it as
   `tools/structures/npcs/<id>.npc.snbt`; it replaces the catalogue draft (owner, UUID and home are
   stripped).
4. Save with a structure block (SAVE mode, up to 48 per side; it writes
   `<world>/generated/minecraft/structure/<name>.nbt`) and copy the file to
   `tools/structures/templates/<structure>/<variant>.nbt` under the catalogue's names:
   `homestead_temperate/longhouse`, `homestead_dry/courtyard_house`, `homestead_boreal/log_cabin`,
   `trading_post/post`, `hermit/hut`, `travelling_smith/camp`, and `site/<site>/main` for the sites.
   A file named like a procedural variant replaces that variant. Create's schematic files (the same
   format) work for bigger builds.
5. Set the variant's `ground` in the catalogue: the template layer (0 = the bottom) that replaces the
   topsoil, so floors usually sit on it and things stand one layer above. Layers below it go into the
   ground (cellars, footings). All variants of a structure share one ground layer.
6. `tools/structures/build.py` (the lint must be clean), `structures_test.py --only <structure>`, a
   look in game with `/place structure pack:<structure>`, then `worldgen_check.py --golden` and
   `--accept "<reason>"`. For a site, also check where it lands (`structures_test.py` reports its chunk
   and whether it is dry land; an `offset` in the catalogue moves it).

### In game: what to look at

In a **new** single-player world (structures only generate in new chunks; cheats on):

1. `/locate structure pack:cairn`, then the same for `hunters_camp`, `wayside_shrine`, `standing_stones`,
   `barrow`, `prospector_camp`, `mine_adit`, `bloomery_ruin` and `wreck` (shores; may be far). `/locate`
   checks TFC's climate for each candidate, so it can take a few seconds. Teleport and look:
   - Is it the local rock and wood? Compare with the raw rock in a nearby cliff or cave and the trees
     around. In andesite, basalt, dacite, rhyolite or diorite country: only smooth rock and bricks, no
     cobble or loose rocks.
   - Does it sit in the ground: nothing floating on slopes, no foundation sticking out oddly, the
     barrow mound and the adit's cut into the hill reading naturally?
   - Open the chests: era-appropriate loot (stone, copper, a little bronze), nothing from Create or
     GregTech.
   - Mossy and cracked bricks, missing blocks: do the ruins look old enough, or too ruined?
2. `/place structure pack:<id>` drops a copy at your feet for quick comparisons (without terrain
   adaptation, so on slopes it can float where a natural one wouldn't).
3. Fly around a temperate start for a while: does about one ruin every few hundred blocks feel right?
   Spacing per structure is in the catalogue.
4. Open TFC: Real World's map (the inventory tab): the ten "Ancient site" waypoints under their regions
   (Stonehenge, Newgrange, Skara Brae, Ötzi's pass, Knossos, Göbekli Tepe, Çatalhöyük, Mohenjo-daro,
   Keweenaw, Caral). Nothing stands there yet: `/pack_world sites` answers "No geographic sites are
   defined." until their templates exist.
5. NPCs: `/easy_npc preset import data pack:easy_npc/preset/humanoid/trader.npc.snbt ~ ~ ~` (also
   `smith`, `hermit`). Talk to it: greeting, "Let's trade." (barter for TFC goods), "Any advice?". Check
   the trades make sense for the era, that it stays put, and how it behaves at night and after a
   restart. If you change it, export it into `tools/structures/npcs/` (step 3 above).

### Other mods' structures: the structure skin (2026-10-08)

The pack also generates other mods' structures, fitted to it (decision row *Structure mods* in `docs/design.md`): YUNG's Better
Dungeons and Better Mineshafts (underground), Moog's Voyager Structures (MVS: small things, wells, houses, trees, carts), Moog's
Missing Villages (MMV), Moog's Temples Reimagined (MTR), Towns and Towers (T&T: villages and pillager outposts) and TFC Huts (a
Neolithic hut village). TFC Structure Compat lets them start in TFC biomes; everything else on this page is the pack's own fitting.
Measured on four 2,064 × 2,064 block squares (Paris, the Mongolian steppe, Cairo, Stockholm: 6,816 km² at 20 m per block, the same
areas and seed as the trial that preceded this): MVS 1,021 starts (one per 6.7 km², about 130 blocks apart: 60 per 1,000 × 1,000
blocks), Better Dungeons 755 (one per 9.0 km², underground), Better Mineshafts 223 (one per 30.6 km², underground), T&T 22 villages
and outposts, TFC Huts 25 settlements (13 at Paris, 11 at Stockholm, 1 at the steppe, none at Cairo: it needs plains, hills or
plateau), MMV 3, MTR 2. The pack's own ruins stay as they were. Moog's density lives in `config/moogs_structures.json` (frequency
multipliers: universal, per mod, per structure) and `config/cristellib/mvs/structure_placement_config.json5` (spacing and separation
per structure; Cristel Lib writes the same file for every structure mod, TFC Huts' included); the pack ships neither, so the
defaults apply, and neither was changed.

**Where they start.** The compat mod's structure files name `#c:is_overworld` and thirteen other `c:is_*` biome tags and puts TFC's
biomes into them. The pack keeps TFC biomes out of those shared tags (GregTech's swamp rubber trees spread from 5 to 17 TFC biomes
through them), so `tools/structure_mods/biome_tags.py` undoes the additions (`kubejs/data/c/tags/worldgen/biome/`, `remove` lists
that keep TFC's own entries; a tag file needs `values` even with only `remove`) and gives the compat's 104 MVS structure files a
copy with `biomes` pointing at `#pack:tfc_structures/*` (the biomes each tag held with the compat). The rubber trees are back to 5
biomes. MVS is pinned to 5.0.11 (`packwiz pin`): 5.0.14 and later drop six template pools the compat overrides, and the server then
refuses to load. TFC Huts' own biome tag (plains, hills, rolling hills, plateau, low canyons) predates TFC 4.2's karst biomes, so
`kubejs/data/tfchuts/tags/worldgen/biome/settlement.json` adds their plains, hills, rolling hills and plateau variants.

**The skin (`pack_world` 1.1.0).** The compat rewrites vanilla blocks to TFC ones in the templates of nine namespaces, with the
chunk's rock but no andesite-alloy rule, and not at all for T&T (its templates live in `kaisyn`) or for Better Mineshafts (its
pieces are code). The skin works after the fact, on whatever a structure wrote, for the structure namespaces listed in
`kubejs/data/pack/pack_world/structure_skin/structures.json` (`towns_and_towers`, `mvs`, `mmv`, `mtr`, `betterdungeons`,
`bettermineshafts`, `tfchuts`):

- **One mixin**, `StructureStartMixin`, into `StructureStart.placeInChunk`, which every structure goes through when it places its
  pieces in a chunk. At the start it snapshots the pieces' area in that chunk; at the end it compares: whatever changed was written
  by the structure, whoever built it (template, code, another mod's processor), and natural terrain never changes. (Dynamic TFC
  Structures takes the same route with a second mixin into `ProtoChunk.setBlockState` to record writes; comparing needs none.)
  Both injections are `required`, so a Minecraft or NeoForge update that moves the method stops the game from loading instead of
  silently skipping the skin; failures inside them are logged once and the structure is left as generated. `worldgen_check.py`
  lists the mixin among those into worldgen code. The rest is plain code: `skin/SkinConfig` (data and reload listener),
  `skin/StructureSkin` (the pass), and the existing `materials/` classes.
- **Materials.** `blocks.json` (generated by `tools/structure_mods/skin_table.py`, 1,060 vanilla blocks, plus TFC's iron-age and
  precious metal blocks) maps each block to a TFC one; targets that are placeholders (granite, oak, spruce and acacia as wood ranks,
  alfisol, yellow) become the surface rock at the structure's start, the climate's best-fitting trees (rank 0 the best fit, then the
  next two; vanilla oak and birch take rank 0, spruce and dark oak rank 1, jungle, acacia, mangrove, crimson and warped rank 2), the
  column's soil and the local sand, through the same code as `pack_world:local_materials`, with the same property copying (stairs,
  slabs, walls, fences, doors, log axes, leaves) and the same andesite-alloy rule: raw, hardened, cobble, mossy and loose andesite,
  basalt, dacite, rhyolite and diorite become smooth rock, cracked or mossy bricks, or nothing. Rough alloy rock another mod's
  processor already placed gets the same treatment (TFC rock blocks are only touched when they are alloy rock and the structure
  wrote them). Vanilla ores become the local raw rock; iron bars and doors become wooden fences and doors; iron, gold, emerald,
  diamond, lapis and coal blocks become smooth rock or polished alabaster; anvils become rock anvils; beds become thatch beds;
  hay becomes thatch; coloured terracotta becomes wattle, concrete alabaster; crops become TFC crops on TFC farmland (sown fresh: TFC's crop block entities start at no growth); water
  becomes TFC river water; chests and signs keep their loot table and text (the block entity's data is carried over); TFC's own
  wrought iron, steel and gold blocks that the compat writes become copper blocks or alabaster. Left alone by design: glass and
  panes, torches, lanterns, chains, rails, ladders, cobwebs, vines, snow and ice, wool, carpets and banners, skulls, spawners,
  redstone parts and similar decoration with no TFC counterpart (5% of the blocks the templates hold, see `skin_table.py --census`).
  Job-site blocks (barrel, lectern, composter, smoker, blast furnace, smithing table ...) turn into TFC blocks that aren't
  villager job sites, so structure villagers stay unemployed unless a player gives them a vanilla one.
- **Items.** `items.json` maps what structures hand to armor stands, mobs, item frames, dropped items and chests with baked-in
  contents (not loot tables) to copper and bronze gear: iron, gold and chainmail gear to copper, diamond and netherite to bronze,
  raw and refined iron, gold, diamonds and emeralds to copper ore, copper ingots or flint, and the compat's wrought iron and steel
  gear to copper.
- **Foundations.** Surface structures get a foundation of local raw rock under footprint columns that hang above the ground: columns
  whose lowest solid block (leaves and logs don't count: a canopy and its branches aren't a floor) is within three blocks of its
  piece's bottom, so roofs, eaves and balconies don't get pillars, and two or more blocks above the terrain. The fill goes down to
  8 blocks and stops at water; floating islands are excluded (`structures.json`).
- **Cross-chunk consistency.** Materials come from the structure's start chunk (TFC's surface rock, forest and sand are pure
  functions of the position) and soil from the column's own chunk, so every chunk of a structure agrees in any generation order.
  Where a column has no soil under it the fallback is alfisol.
- **Wood.** The climate's woods come from TFC's own forest entries by TFC's own distance rule. ArborFirmaCraft's forests replace
  most of TFC's trees, but its species are not building materials in `pack_world`: a village in an araucaria forest is built of
  the TFC wood that fits the climate best.
- **Adding or changing a structure mod.** Add its structure namespace to `structures.json`, run `tools/structure_mods/census.py
  --json` and `skin_table.py --check --census` (it lists vanilla ids with no rule and what stays vanilla), then `measure.py`.
  Set `"dry_run": true` in a datapack file under `pack_world/structure_skin/` to make the skin only count (what `measure.py --mode
  before` does).

**Loot and trades.** Chests of these structures use era-capped TFC loot, 171 tables written by `tools/loot/` (stone, copper or
bronze per structure, the original's size kept); GregTech's nine global loot modifiers (steel, damascus steel, silver, chromium and
gems into vanilla dungeon, mineshaft, village and stronghold tables) are switched off by a higher-priority empty
`neoforge/loot_modifiers/global_loot_modifiers.json`; `tools/loot/lint.py` rolls every chest, archaeology and gift table the pack
knows 300 times against the deny-list and the caps. Lootr, which the pack carries for servers, converts every container with a loot
table, TFC and AFC chests included, into its own per-player chest (it leaves TFC barrels, which have no loot table); to keep the
pack's own TFC chests as they are, set `loot_modid_blacklist = ["pack"]` under `[whitelist]` in `config/lootr-common.toml`
(not set). Villagers and wandering traders barter TFC goods under the same caps (`kubejs/config/villager_trades.json`, see the
*Villagers* row in `docs/design.md`); TFC Huts' villagers, plains villagers from vanilla's pool `minecraft:village/plains/villagers`
that its templates name, have no profession and trade nothing.

**Measured** (same four areas and seed; `tools/structure_mods/measure.py`, `report.py`; "before" is what the structures wrote with
the other mods' own processing (the compat's rewrite included) and before the skin, recorded in the same run, "after" what the skin
left; "vanilla" counts the blocks structures wrote that are vanilla, without those TFC's own world also has: air, water, lava,
bedrock, snow, ice, so the trial's shares, taken against a base world, differ in definition; floating columns are ground columns, in
footprints of surface structures only, whose lowest solid block is two or more above the terrain, so underground structures show
only incidental ones):

| structures | blocks written | vanilla before | vanilla after | rough alloy rock before / after | iron-age metal blocks before / after | ground columns | floating before / after | foundation blocks |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| towns_and_towers | 87,654 | 99.6% | 4.0% | 0 / 0 | 0 / 0 | 33,978 | 585 / 53 | 2,958 |
| mvs | 290,261 | 50.6% | 3.3% | 1,804 / 0 | 888 / 0 | 28,979 | 2,175 / 296 | 10,942 |
| mmv | 11,251 | 33.3% | 3.9% | 0 / 0 | 16 / 0 | 1,619 | 21 / 0 | 74 |
| mtr | 77,086 | 61.2% | 0.9% | 9,535 / 0 | 83 / 0 | 7,373 | 0 / 0 | 0 |
| betterdungeons | 1,306,173 | 19.2% | 2.8% | 82,194 / 0 | 8,459 / 0 | 256,936 | 17 / 17 | 0 |
| bettermineshafts | 2,578,101 | 89.2% | 8.2% | 0 / 0 | 0 / 0 | 628,366 | 67 / 67 | 0 |
| tfchuts | 41,362 | 1.1% | 0.0% | 0 / 0 | 0 / 0 | 13,243 | 157 / 0 | 715 |

**In game: what to look at.** In a new world: (1) a T&T village or an MVS house (`/locate structure towns_and_towers:village_grove`,
`mvs:house`; TFC Huts: `tfchuts:settlement`): local rock and wood, soil under paths and farms, no cobble or raw rock of andesite,
basalt, dacite, rhyolite or diorite (smooth rock and bricks instead), farms with TFC crops, beds as thatch beds, a foundation under
houses on slopes; (2) open chests: TFC loot only (and Lootr's chest model); (3) a dungeon or mineshaft: local rock, no vanilla ores
in the walls; (4) villagers: unemployed in the
structures, trades in TFC goods once they have a vanilla job site block; wandering traders carry the pack's offers; (5) iron-age
metal blocks (chains, bars) in structures should be copper.

### Settlements: villages by real region (2026-10-08)

Seven kinds of village, converted from TerraFirmaGreg's settlements (LGPL-3.0; `licenses/TerraFirmaGreg-structures.txt`; 146 templates in
`tools/structures/templates/village/<culture>/<variant>/<piece>.nbt`, made by `tools/structures/tfg_import.py`, which rewrites their blocks to
TFC 4, the placeholder materials, Framed Blocks and Roads and Roofs) and generated from the catalogue's `regions` and `villages` sections by
`tools/structures/villages.py` (called by `build.py`). They are new-chunks-only like the rest, switched on by `villages.settings.mode` =
`region` in `catalogue.json` (`pack_world` 1.2.0 is needed: the structure sets name its two new types).

| Village | Where (catalogue `regions`) | Climate window | Spacing / separation (chunks) | Variants (weight) | Easy NPCs | Loot |
|---|---|---|---|---|---|---|
| `norse` | Scandinavia, Iceland, the Faroes, the Northern Isles, the Hebrides and Caithness | -14 to 16 °C, rainfall 200+ | 96 / 64 | living 65, ruined 22, burned 13 | farmer, weaver, herder, smith | house, smithy |
| `arabic` | the Maghreb to Arabia | 10 to 36 °C, groundwater 30+ (rivers count: valley and oasis towns) | 96 / 64 | living | potter, merchant, dyer, well keeper, smith | house, smithy, caravanserai |
| `malay` | the Malay peninsula, east and south Sumatra, the Borneo coast (not West Sumatra) | 22 to 36 °C, rainfall 380+ | 96 / 64 | living | cook, boatwright, weaver, smith | house, smithy |
| `minang` | West Sumatra (the rumah gadang) | 18 to 36 °C, rainfall 380+ | 64 / 40 | living | the Malay NPCs | house, smithy |
| `steppe` | Kazakh steppe, Mongolia, Inner Mongolia, northern Xinjiang, Altai | -10 to 16 °C, rainfall 20 to 300, forest 2 at most | 64 / 40 | living (yurt camps) | herder, feltmaker, bowyer, elder | house, archery |
| `temperate` | Atlantic Europe | 2 to 17 °C, rainfall 200 to 450 | 48 / 24 | living (a farmhouse and a track) | farmer, shepherd, orchardist | house |
| `aqueduct` | the Mediterranean basin | 8 to 26 °C, rainfall up to 450 | 192 / 160 | main (an aqueduct) | none | none |

**Placement: `pack_world:region`.** A random-spread placement (one candidate chunk per spacing × spacing cell, vanilla's grid, with its own salt per
village: `2026101001` to `07`) that only accepts a candidate whose chunk centre lies inside one of the set's `regions` and outside every `exclude`
(Malay excludes West Sumatra, which belongs to the Minangkabau), and whose chunk passes TFC's climate test (the same code as `tfc:climate`: the
set's `climate` object is TFC's, tested at the chunk with `ignore_rivers` where the window is about rain). A region is a polygon of `[latitude,
longitude]` vertices or a `box` `[south, west, north, east]` (west greater than east crosses the antimeridian). Edges are densified to one degree
in latitude and longitude, every vertex goes through TFC: Real World's own `WaypointCoordinates.toBlockXZ` (so a region lies where its cities lie in
this world, whatever the map's scale or profile), and containment is tested in block space; the projected shapes are cached per world
configuration. Edges that span half the map or shapes narrower than 16 blocks (a map profile that doesn't contain the region) are dropped with one
error in the log. Without TFC: Real World `outside` says what happens (`never`, the default: nothing; `anywhere`: the climate decides alone).
`/locate structure pack:village/norse_living` asks the grid and then `applyAdditionalChunkRestrictions`, where the region test also sits, so a
search outside a region costs a compare per cell, not a chunk load. Nothing in the placement reads chunks except TFC's chunk data for the climate:
the result doesn't depend on generation order. Checked by `structures_test.py`: 21 reference cities inside their set only, the block
coordinates equal to `tools/worldview/geo.py`'s projection, and, in every region, the same cells as `tfc:climate` would give.

**The guard: `pack_world:guarded_jigsaw`.** `JigsawStructure` is final, so this structure type wraps one (every vanilla field, flat in the same JSON
object, plus a `guard`) and takes its settings; the vanilla structure runs untouched and decides where the pieces go. Before it is accepted the guard
looks at 13 columns on a golden-angle spiral of `radius` blocks around the start piece's centre (the biome there must be in the village's biome tag,
which `build.py` makes from the catalogue's `landforms` groups): refused when more than `max_water_fraction` of them are water (a lake, river or ocean
biome, or below sea level) or when their highest and lowest surface differ by more than `max_height_difference`. Pure function of the world seed and
the chunk (no random numbers, heights and biomes from the generator), so chunk generation, `/locate` and `/place structure` agree; about 0.8 ms per
attempt. `/pack_world guard off` (permission 2, not saved) switches it off to place a village by hand with `/place structure pack:village/norse_living`;
`on` brings it back. The guard judges only the disc, not the whole village (`max_distance_from_center` is 80 to 100): the outer streets follow the
ground (`terrain_matching`) and every rigid piece, the start piece included, gets a foundation of the column's own soil, up to 10 blocks.

**Materials: `local_materials` 1.2.0.** The village processors list `wood_ranks: ["oak", "spruce", "birch"]`: the three placeholder woods are the climate's
best-fitting tree, its second and its third (a culture's most used wood became `oak` in the importer, the next `spruce`, every other one `birch`), clamped
when the climate has fewer trees. Besides TFC's blocks the processor maps Roads and Roofs: `rnr:wood/shingles/*` take the wood, `rnr:rock/<variant>/*`
(gravel, sett and cobbled roads) the rock, `rnr:tamped_alfisol` the soil of the column; and the camouflage of Framed Blocks (`camo` and `camo_two` in
the block entity, 4,500 of them in the templates), which becomes the local wood, rock or soil too, so a framed wall is the same wood as the plank wall next
to it. **ArborFirmaCraft:** its forests replace TFC's, so most of the trees around a village are its species. `modded_woods` (default `["afc"]` whenever
ranks are used; `[]` restricts them to TFC's trees) lets the ranks draw on the forest entries as they are: an entry's wood is the one its fallen log is
made of (`afc:tree/live_oak` is TFC's oak, `afc:tree/mahogany` is `afc:wood/log/mahogany`), and the 14 ArborFirmaCraft woods that come with the whole set of TFC's
wood blocks and shingles (araucaria, baobab, beech, cypress, eucalyptus, fig, ginkgo, hevea, ipe, ironwood, mahoe, mahogany, teak, tualang) are used as
`afc:wood/<variant>/<wood>`; other species (kauri, poplar, rubber fig ...) have no planks and are skipped. A Malay village in a tualang and hevea forest is
built of tualang and hevea; one beside a Bergen fjord of araucaria and cypress if those are the trees that grow there (ArborFirmaCraft gives them TFC's
climate windows, not their real ranges). The structure skin of other mods' structures (above) still uses TFC's trees only. Each piece resolves rock and woods at its own position,
so a village that straddles a rock boundary or a change of tree is built of both, and a piece that is outside every tree's window uses the nearest one.

**Inhabitants, loot, decoration.** Twenty Easy NPC presets (generated drafts with default skins, `Invulnerable`, no owner; export an edited one into
`tools/structures/npcs/<id>.npc.snbt` to replace its draft): each has a greeting, two tips and three to six barter trades in TFC goods inside the bronze cap, and stands on a
`pack:npc_connector` jigsaw spot where TFG's illagers stood (TFG's spots are mostly in the air cell above a floor: those name a `_low` twin of the pool, generated for every pool with NPCs, whose pieces
place the NPC one cell lower, so it stands on the floor); about half the spots stay empty (a pool says so), the ruined and burned Norse variants have none. Chests keep their
`LootTable` (the era-capped tables `pack:chests/village/<culture>/<class>`); Lootr turns them into per-player chests when they are opened. Streets are `rnr:hoggin`
and road gravel, trodden path and grass mixed by a rule processor over the road marker (`tfc:rock/bricks/andesite` in the templates), planks over water. The vanilla
blocks left in the templates are water, torches (TFC's own burns out in a template) and the sixteen carpets TFG used (about 190, in the Arabic, Malay and steppe
pieces; a carpet with nothing under it in its template was dropped, Domum Ornamentum's floating carpets became carpets of their colour). Banners, flower pots and
Chalk marks are gone, ladders are Framed ladders, Firmalife and Macaw's furniture is TFC planks and slabs, Macaw's roofs (Malay) are Roads and Roofs shingle stairs
and slabs.

**Tuning a village.** Everything is in `tools/structures/catalogue.json`; rebuild with `build.py --strict` and `packwiz refresh`.

- *Spacing*: `villages.<id>.set.spacing` and `separation` (chunks; vanilla's random spread: one candidate chunk per spacing × spacing cell, at most spacing minus separation chunks from the cell's corner, so
  neighbours are never closer than separation; separation below spacing), `salt` (unique), `spread_type`. A smaller spacing is more cells, not more villages per cell: how many cells pass is the next two points.
- *Regions*: the top-level `regions` (`polygon` of `[latitude, longitude]`, or `box`), listed in `set.regions` and `set.exclude`. `anchors` and `outside` name cities that
  must be inside and outside; the lint checks them (it caught two polygons that missed Malacca and Alexandria). `tools/structures/villages.py` has a Python mirror of
  the polygon test, `tools/worldview/geo.py` of the projection.
- *Climate and biome*: `set.climate` (TFC's climate fields: temperature, groundwater, rain variance, forest; `ignore_rivers` makes groundwater mean rainfall; elevation bounds
  don't work in structure placement) and `set.landforms` (groups from the top-level `landforms`, which become the biome tag `pack:has_structure/village/<id>`) and `set.biomes`.
- *Guard*: `villages.defaults.guard`, a village's `guard` or a variant's: `radius`, `samples`, `max_height_difference`, `max_water_fraction`.
- *How many survive*: `tools/structures_test.py --villages --per-set 0 --acceptance` records, for every placement cell across a set's regions, the biome and what the guard sees
  (no chunks are generated, about three minutes), and `tools/structures/village_tune.py` replays the catalogue's biome groups and guard on it, or yours (`--max-diff 14
  --landforms +coast --water 0.2`), and prints the villages per million blocks squared and the mean distance between neighbours with the reasons for refusals. The numbers
  in the catalogue now come from it (a first guess had refused nine cells in ten in Norway).
- *Foundations and the rest*: the processor lists' `foundation`, `rot` and `decay`, the variants' `size`, `max_distance`, `terrain_adaptation`, and the pools' weights
  (`build.py --simulate 100 --layout` shows how many of each building one gets).

**Adding hand-built templates for a culture.** Build in creative from the placeholder materials (TFC granite for the rock, alfisol for the soil, yellow sand, oak, spruce and birch
for the three ranked woods; Framed Blocks, Roads and Roofs, vanilla torches and carpets are allowed; the road marker is `tfc:rock/bricks/andesite`), connect pieces with jigsaw
blocks (name and target `pack:connector`, pool `pack:village/<culture>/<variant>/<pool>`; an NPC spot is a jigsaw on a floor facing up that targets `pack:npc_connector` and names
an `npc_*` pool), save with a structure block (up to 96 wide and 128 tall, because a structure's references reach eight chunks) and copy the file to
`tools/structures/templates/village/<culture>/<variant>/<piece>.nbt`. Add the piece to a pool of that variant in the catalogue (`pools.<pool>.elements`, with a weight, a
processor list and optionally `projection: terrain_matching` for streets and a `loot` class under `pieces`); `build.py --strict` says what is missing (a jigsaw naming a pool that
doesn't exist, a target no piece offers, a block the lint doesn't allow). `tfg_import.py` rewrites the folders of the cultures it converts, so don't run it again over hand-built
pieces: it is only needed when its tables change. A new culture is a `regions` entry (with anchors), a `villages` entry (copy a similar one) and a template folder.
`build.py --simulate 100 --layout` draws the layouts before anything is generated.

**How many, and where.** `tools/structures_test.py --villages --per-set 0 --acceptance` over each set's regions (cells that pass the region and climate tests, then the biome
at the cell's centre and the guard; sea, mountains and desert are most of what is refused): villages per million blocks squared of a region's area (sea and mountains
included) and the mean distance between neighbours, with the catalogue's biome groups and guards.

| Village | Cells passing region and climate | Biome in the tag | Guard passes | Per 10^6 blocks² | Mean gap | Mostly refused for |
|---|---:|---:|---:|---:|---:|---|
| `temperate` | 894 of 2,040 | 632 | 361 | 0.67 | 1,200 | ocean, water in the disc, canyons |
| `minang` | 198 | 153 | 46 | 0.23 | 2,100 | ocean reef and atolls, slope |
| `steppe` | 901 | 512 | 198 | 0.11 | 3,000 | slope, water, collisional mountains, badlands |
| `norse` | 1,107 | 514 | 253 | 0.10 | 3,200 | ocean, lakes, oceanic mountains, slope |
| `malay` | 338 | 76 | 27 | 0.03 | 5,500 | ocean atolls, mountains, slope |
| `aqueduct` | 1,158 | 309 | 244 | 0.02 | 6,700 | deep ocean, ocean, mountains |
| `arabic` | 338 of 2,652 (every third cell) | 87 | 33 | 0.01 | 9,400 | dune sea, buttes and mesas, slope |

The first guesses (norse 9 blocks, steppe and Malay 6, temperate 5) refused nine cells in ten; the census made the limits (12 to 14, Malay 10, temperate 7) and took biome groups only
where a culture lives there (the minang highlands are volcanic mountains, so that set takes the `mountain` group; temperate takes `upland`). Eight 2,048 × 2,048 block areas generated with
`pregen.py` (seed `pregen`; 59 to 65 chunks per second with the villages in the pack, 64.9 averaged over four other areas before them: no measurable cost) around Bergen, Fes (Morocco),
Ulaanbaatar, Cairo, Kuala Lumpur, Padang (West Sumatra), Normandy and Provence: one Norse village near Bergen (17 pieces, 6 NPCs), one Minangkabau village in West Sumatra (14 pieces,
5 NPCs), six farmsteads in Normandy (2 to 3 pieces, 1 NPC each) and none in the other five, which is what the table says (a village every 1,000 to 9,000 blocks of its region is rarely
inside a 2,000 block square). `/locate` from the same places (seed `structures`, a test world) answers in 12 to 200 ms with a real village 200 to 9,200 blocks away (Stockholm 214, Bergen 423,
Padang 588, Fes 826, Kuala Lumpur 1,601, Ulaanbaatar 1,862, Normandy 352, Provence 5,112, Cairo 9,156). The guard costs about 0.8 ms an attempt.

**Measured on generated villages** (`structures_test.py`: the three nearest natural villages to each culture's test places, and every variant placed with `/place`'s method and the guard off; 21 natural and 9 placed):

| | pieces (NPC spots) | NPCs standing | Rock, wood | Floating ground columns | Notes |
|---|---|---|---|---|---|
| Norse living | 15 to 28 (4 to 11) | all | gneiss, dacite, chalk; araucaria, cypress, pine, sycamore, willow, birch | 0 of 578 to 1,777 | ruined 11 pieces, burned 9, no NPCs (placed) |
| Arabic | 30 to 53 (3 to 10) | all | chert, andesite, shale, basalt (smooth, never raw: the alloy rule); pine, araucaria, cypress, baobab | 0 of 1,212 to 2,216 | Framed camo is local brick or sandstone |
| Malay | 20 to 39 (4 to 10) | all | conglomerate, shale, dolomite; kapok, tualang, hevea, fig, mahogany | 0 of 186 to 392 | Roads and Roofs roofs in the local woods |
| Minang | 6 to 45 (0 to 6) | all | diorite (smooth), chert; kapok, tualang, hevea, fig, mahogany | 0 of 65 to 224 | the rumah gadang start piece |
| Steppe | 5 to 22 (0 to 5) | all | shale, conglomerate, dolomite; pine, chestnut, ginkgo | 0 of 524 to 1,139 | wattle camouflage kept on every yurt wall (346 white, 224 black of 600 sampled) |
| Temperate | 2 to 3 (1) | all | shale, claystone; araucaria, mahogany | 0 of 245 to 249 | a farmhouse and a track |
| Aqueduct | 15 to 16 (0) | none | conglomerate, claystone, limestone | 0 of 98 to 108 | the legs stand in the ground (their ground layer is the footing) |

No placeholder (oak, spruce, birch, granite, alfisol, yellow) is left where a local material was expected, no vanilla block other than water, torches and carpets, no rough andesite-alloy
rock, every chest has its loot table (ArborFirmaCraft's chests take them too: a Norse village of araucaria has 10 of 10), the Easy NPCs are all invulnerable, ownerless and have 3 to 6
trades. `tools/loot/lint.py` rolled all 268 chest tables 300 times each (the 12 village tables with them): nothing deny-listed or over the caps. `worldgen_check.py --golden` records the new
structures, the processors and the pack_world classes as new-chunks-only. What the tests found and the pack now does about it: TFG's NPC jigsaws sit in the air above the floor, so the NPC
piece one cell further up would hold its NPC a block above it: those spots name a `_low` pool whose pieces place the NPC one cell lower (every pool with NPCs has one, generated); the start
pieces and the plaza pieces used the street processor list, which has no foundation (a yurt hung 3 blocks over a slope), so every list has one now (10 blocks of the column's own soil).

**Known gaps.** Each piece resolves rock and woods at its own position, so a village across a change of tree has houses of two accent woods (about half of them; the main wood is the same). Villages in dense forest are overgrown: TFC's trees grow around and over them (placing the structure after the vegetation, step `top_layer_modification`, was tried and made it
worse, the template's air only clears its own box; `villages.<id>.step` stays as an option). Neighbouring structures of other mods overlap them (`tools/structure_mods/village_census.py` on
the 14 villages of the test areas: Moog's Voyager Structures in 5 (a fire camp, a windmill, a well tower, a house, palm trees), Better Mineshafts' boxes in 2 below them, a pack hunters' camp in
1; Towns and Towers and TFC Huts in none): no structure set avoids another in this pack. Framed Blocks' camouflage axes are not rotated with a rotated piece. A giant ArborFirmaCraft tree
can still grow through a roof now and then (one block in 4,000).

**In game: what to look at.** In a *new* world (structures only generate in new chunks; cheats on):

1. `/locate structure pack:village/norse_living`, then `norse_ruined`, `norse_burned`, `arabic_living`, `malay_living`, `minang_living`, `steppe_living`, `temperate_living`
   and `aqueduct_main` (all `pack:village/...`). The search answers from anywhere in 10 to 200 ms (a village near the place `/startat` put you at, or a
   few thousand blocks away; nothing at all if no region is in reach). To arrive near one: `/startat 60.4 5.3` (Bergen), `34.0 -5.0` (Fes), `47.9 106.9` (Mongolia),
   `3.1 101.7` (Malay peninsula), `-0.9 100.4` (West Sumatra), `49.2 -0.4` (Normandy), `43.9 4.6` (Provence).
2. In a village: is the rock and wood the local one (compare with the cliffs and the forest, ArborFirmaCraft's trees included; never granite, oak, spruce and birch by default, and no raw
   andesite-alloy rock), do Framed walls match the planks next to them, are streets hoggin, gravel and path (planks over water), are the NPCs on the floor, do their trades
   (`Open the NPC`) make sense for the era, do chests roll the village's loot (Lootr shows its own chest), do the Malay roofs (shingle stairs and slabs) and the yurts (wattle felt)
   look right, do the torches stay lit.
3. The variants by hand: `/pack_world guard off`, `/place structure pack:village/norse_ruined` (and `norse_burned`, `arabic_living` ...), `/pack_world guard on`. With the guard on a `/place` on steep ground refuses.
4. What to judge: villages in forests are overgrown, other mods' structures overlapping them, and how far apart villages feel (the table above).

---

## 0. Summary

- **A small Java mod, `pack_world`** (code only, ~800 lines at the time of this design; since then one mixin for the structure skin, see *Status*; no blocks or items):
  1. `pack_world:local_materials`, a structure processor that turns placeholder TFC blocks (granite,
     oak, alfisol, yellow sand) into the local surface rock, the climate's most typical tree and the
     column's soil, keeping every block property (stairs, slabs, walls, log axes, TFC's `fluid`).
     It also enforces the andesite-alloy rule (no rough andesite, basalt, dacite, rhyolite or diorite
     in ruins), and can weather bricks and grow foundations down to the ground.
  2. `pack_world:npc_fixup`, a processor that cleans Easy NPC data in templates (owner, home position,
     spawner UUIDs) so every placed copy is its own NPC.
  3. `pack_world:geographic`, a structure placement that puts one structure at a real latitude and
     longitude through TFC: Real World's own projection (`WaypointCoordinates.toBlockXZ`), so the site
     and its Real World waypoint coincide. A per-world guard keeps sites out of worlds that were
     already explored when the site was added.
  4. A small static API for the test scripts. Optional later: a `pack_world:climate` loot condition.
- **Data, not code, for everything else**: structures, sets (TFC's `tfc:climate` placement), pools,
  processor lists, loot tables, biome tags and templates live in `kubejs/data/pack/...`, generated
  from one catalogue by a Python tool, like the quest book.
- **15 structures**: 12 ruins and traces (hunters' camp, prospector's camp, mine adit, collapsed
  bloomery smithy, cairn, standing stones, wayside shrine, barrow, coastal wreck, three abandoned
  homesteads for temperate, dry and boreal climates) and 3 rare inhabited spots (trading post, hermit,
  travelling smith) with Easy NPC traders. Plus about 10 **real ancient sites** at their coordinates
  (Stonehenge, Newgrange, Skara Brae, Ötzi's pass, Knossos, Göbekli Tepe, Çatalhöyük, Mohenjo-daro,
  the Old Copper pits of the Keweenaw, Caral).
- **Density**: about one ruin every ~300 blocks of travel in settled climates, an inhabited spot every
  ~1,500-2,000 blocks; all spacing is per structure set and easy to tune.
- **Loot** saves time inside an era and never skips one: every loot item id was checked against the
  dump; the generator lints loot against the progression checker's steps and a hard deny-list
  (wrought iron and later metals, Create, GregTech, vanilla iron, the bloomery).
- **worldgen_check** needs four changes so accepted structures don't trip the golden tier: per-chunk
  census so chunks covered by structures can be left out symmetrically, a signature per accepted
  structure, the geographic sites' chunks recorded and compared, and structure templates and the mod's
  code hashed in tier 0.
- **Build**: ModDevGradle is the right project layout, but its first build downloads roughly
  450-550 MB (Gradle itself, NeoForm/NeoForge artifacts, Minecraft and its libraries). A ~60-line `build.py`
  can compile the same source tree with the installed JDK 22 against the jars the test server already
  has, with no downloads at all; I recommend starting there. (Decided: ModDevGradle; the first build
  downloaded about 433 MB, see *Status*.)

---

## 1. The mod

### 1.1 Name and scope

| | |
|---|---|
| Mod id | `pack_world` (display name "Pack World", Java package `pack.world`). Alternatives: `lived_in`, `pack_structures`. |
| Data namespace | `pack` (already used by the pack's tags, e.g. `pack:andesite_like`), so structures read `pack:hunters_camp`; the mod's own registry types are `pack_world:local_materials`, `pack_world:npc_fixup`, `pack_world:geographic`. |
| License | MIT (like Dynamic TFC Structures, whose idea this follows; no code is copied). |
| Sides | Both (single-player runs the integrated server). `displayTest = "IGNORE_SERVER_VERSION"` is not needed: the pack ships it everywhere. No client code. |
| Dependencies | `tfc` required (`[4.2.11,4.3)`), `tfc_real_world` optional (the geographic placement is inert without it), `neoforge` `[21.1.255,)`. |

In scope:

| Piece | Kind | Why it must be Java |
|---|---|---|
| `local_materials` | `StructureProcessor` | TFC's surface rock and forest choice only exist in Java (`ChunkDataGenerator`, `ForestConfig`); vanilla `rule` processors can only read the block already at the target position. |
| `npc_fixup` | `StructureProcessor` (block and entity hooks) | Easy NPC data in templates carries the author's UUIDs and coordinates (see §4). |
| `geographic` | `StructurePlacementType` (extends `RandomSpreadStructurePlacement`) | No data-driven placement can name one chunk. |
| `SiteGuard` | `SavedData` + `/pack_world sites` command | Keeps fixed-position sites out of terrain explored before they existed (§1.7). |
| `PackWorldApi` | static helpers | Called from dev-only KubeJS scripts in the tests and in `worldgen_check.js`. |
| *optional* `pack_world:climate` | `LootItemCondition` | Seeds and saplings in chests that grow where the chest is (TFC has no climate loot condition; its loot types are `isolated`, `burnt_out`, `sluice`, `is_male`, `always_true`, `not_predated`, `crop_yield_uniform`, `animal_yield`, `copy_fluid`, `rotten`, `apply_stack_size`). |

Out of scope: blocks, items, entities, mixins, networking, configs, client code, worldgen features.
Not needed as dependencies: Lithostitched (MIT; its property-preserving `block_swap`, `condition` and
per-structure `apply_random` processors cover decay and swaps, but not local materials, which the mod
does anyway), TFC Structure Compat and Dynamic TFC Structures (both adapt *other mods'* structures, the
latter through mixins into `StructureStart`; this design uses a plain processor instead).
KubeJS 7 has no worldgen events, so all structure data is plain JSON in `kubejs/data` (KubeJS adds its
data folder to the world loader's pack list through `WorldLoaderPackConfigMixin`, so worldgen
registries load from it; verify with the first structure, tier 1 of `worldgen_check.py` lists it).

### 1.2 Project layout and build

*Built with ModDevGradle as in* Status *(with a toolchain workaround); the zero-download `build.py`
below was not needed and does not exist.*

**ModDevGradle, not NeoGradle.** ModDevGradle (MDG, `net.neoforged.moddev`) is NeoForged's
recommended plugin for single-loader mods and what the official 1.21.1 MDK uses today (MDG 2.0.148,
Gradle 9.2.1 wrapper, NeoForge 21.1.256; read from `NeoForgeMDKs/MDK-1.21.1-ModDevGradle`). It is a thin
layer over NeoForm Runtime: less configuration, faster first setup, no run-config machinery to debug.
NeoGradle is the older, heavier plugin for multi-project/multi-loader builds; nothing here needs it.

```
mod/                                  (add /mod/ to .packwizignore; only the built jar ships)
  build.gradle, settings.gradle, gradle.properties, gradlew, gradlew.bat, gradle/wrapper/...
  build.py                            zero-download build (below)
  src/main/java/pack/world/
    PackWorld.java                    @Mod: DeferredRegisters, event listeners
    materials/LocalMaterialsProcessor.java   codec + finalizeProcessing
    materials/Materials.java          resolve(): rock, wood, sand colour at an anchor; per-column soil
    materials/BlockFamilies.java      id parsing (rock/ore/wood/soil/sand) and property copy
    npc/NpcFixupProcessor.java
    geo/GeographicPlacement.java      codec + isPlacementChunk + getPotentialStructureChunk
    geo/SiteGuard.java                SavedData, LevelEvent.Load hook, /pack_world sites
    loot/ClimateCondition.java        (optional)
    api/PackWorldApi.java
  src/main/resources/META-INF/neoforge.mods.toml
```

`build.gradle` essentials:

```groovy
plugins { id 'java-library'; id 'net.neoforged.moddev' version '2.0.148' }
version = '1.0.0'; group = 'pack.world'
// No java.toolchain block: only JDK 8/11/18/20/22 are installed and a toolchain of 21 would make
// Gradle download a JDK. Run Gradle on JDK 22 and compile for 21:
tasks.withType(JavaCompile).configureEach { options.release = 21 }
neoForge {
    version = '21.1.255'                      // the pack's NeoForge, not the MDK's .256
    mods { pack_world { sourceSet sourceSets.main } }
    runs { server { server() } }              // optional; the headless test server is the real test bed
}
def serverMods = file('../tools/.server/mods')
dependencies {
    compileOnly fileTree(serverMods) { include 'TerraFirmaCraft-NeoForge-1.21.1-*.jar', 'TFC-Real-World-NeoForge-1.21.1-*.jar' }
}
```

Compile-only references to TFC (EUPL-1.2) and TFC: Real World (MIT) don't bundle or modify their code;
the built jar contains only our classes. The jars come from `tools/.server/mods`, which packwiz keeps
on the pack's exact versions, so no Maven repository and no second download is needed.

**Zero-download build (`mod/build.py`, recommended to start).** NeoForge 1.21.1 runs on Mojang names,
and the test server's installation already holds everything a compiler needs (checked with `javap`):
`libraries/net/neoforged/neoforge/21.1.255/neoforge-21.1.255-server.jar` (NeoForge's patched Minecraft
classes, e.g. `StructureProcessor` with its `processEntity` hook),
`libraries/net/minecraft/server/1.21.1-20240808.144430/server-1.21.1-20240808.144430-srg.jar` (the rest
of Minecraft, Mojang-named despite the file name), `neoforge-21.1.255-universal.jar` (NeoForge API:
`DeferredRegister`, events), the ~90 library jars listed in
`libraries/net/neoforged/neoforge/21.1.255/win_args.txt`, and the TFC and Real World jars in `mods/`.
`build.py` puts the patched jar first on the classpath, runs `javac --release 21 -proc:none` with JDK
22 (`C:\Program Files\Java\jdk-22.0.1`), and packs classes plus `src/main/resources` into
`../mods/pack_world-<version>.jar`. Cost: no IDE integration, no decompiled sources, no gametest run
type; compile errors still catch every API change. Both builds use the same source tree, so moving
to MDG later is a copy of `build.gradle`.

`neoforge.mods.toml`:

```toml
modLoader = "javafml"
loaderVersion = "[4,)"
license = "MIT"
[[mods]]
modId = "pack_world"
version = "1.0.0"
displayName = "Pack World"
description = "Local materials, Easy NPC fix-ups and real-world placement for the pack's structures."
[[dependencies.pack_world]]
modId = "tfc"
type = "required"
versionRange = "[4.2.11,4.3)"
ordering = "AFTER"
side = "BOTH"
[[dependencies.pack_world]]
modId = "tfc_real_world"
type = "optional"
versionRange = "[4.2.0,4.3)"
ordering = "AFTER"
side = "BOTH"
[[dependencies.pack_world]]
modId = "neoforge"
type = "required"
versionRange = "[21.1.255,)"
ordering = "NONE"
side = "BOTH"
```

### 1.3 Downloads a ModDevGradle build needs (for approval)

Only for the MDG path; `build.py` needs none. Sizes are approximate.

| What | From | Size | Needed for |
|---|---|---|---|
| Gradle distribution (`gradle-9.2.1-bin.zip`, or 8.14.x) | services.gradle.org | ~130-145 MB (current 9.x bin zips are 128-145 MB, 8.14.5 is 132 MB) | running Gradle at all |
| MDG plugin 2.0.148 and its tools (NeoForm Runtime, JavaSourceTransformer, installer tools, Vineflower decompiler) | plugins.gradle.org, maven.neoforged.net | ~20-40 MB | setting up Minecraft for compilation |
| NeoForge 21.1.255 userdev and universal jars, NeoForm `1.21.1-20240808.144430` | maven.neoforged.net | ~10-20 MB | the NeoForge API and patches |
| Minecraft 1.21.1 client and server jars, client and server mappings, version manifest | piston-meta / piston-data.mojang.com | ~26 + ~51 + ~10 + ~8 MB | the classes to compile against |
| Minecraft's libraries (LWJGL, Netty, DFU, Brigadier, ...) | libraries.minecraft.net, Maven Central | ~80-120 MB | compile classpath |
| Minecraft assets | resources.download.minecraft.net | ~400-600 MB | **only** `runClient`; never run it here |
| Parchment mappings | maven.parchmentmc.org | ~5 MB | optional parameter names; skip |
| A JDK 21 | foojay / Adoptium | ~190 MB | **avoid**: only if a `java.toolchain` of 21 is declared |

Total for compile-only use: about 300-400 MB downloaded, roughly 1 GB in `~/.gradle` after
decompiling. TFC and Real World add nothing (local files).

### 1.4 The TFC and Real World API it uses (exact signatures, `javap` on the pack's jars)

TFC 4.2.11 (`TerraFirmaCraft-NeoForge-1.21.1-4.2.11.jar`, EUPL-1.2):

```java
// net.dries007.tfc.world.ChunkGeneratorExtension  (TFCChunkGenerator implements it)
static ChunkGeneratorExtension getFromStructureState(ChunkGeneratorStructureState)
ChunkDataGenerator chunkDataGenerator()
RockLayerSettings rockLayerSettings()                       // default method

// net.dries007.tfc.world.chunkdata.ChunkDataGenerator
ChunkData createAndGenerate(ChunkPos)                       // partial data: rainfall, rain variance,
                                                            // base groundwater, temperature, forest type
RockSettings generateSurfaceRock(int x, int z)              // pure function of x, z
RockSettings generateRock(int x, int y, int z, int surfaceY, ChunkRockDataCache)

// net.dries007.tfc.world.chunkdata.ChunkData
static ChunkData get(LevelReader, BlockPos) / get(LevelReader, ChunkPos) / get(ChunkAccess)
RockData getRockData()
float getAverageSeaLevelTemp(BlockPos), getAverageGroundwater(BlockPos), getRainVariance(BlockPos),
      getAverageRainfall(BlockPos), getBaseGroundwater(BlockPos)
ForestType getForestType()

// net.dries007.tfc.world.chunkdata.RockData
RockSettings getSurfaceRock(int x, int z)   // = generator.generateSurfaceRock(x, z)
RockSettings getRock(int x, int y, int z)

// net.dries007.tfc.world.settings.RockSettings (record)
Block raw(), hardened(), gravel(), cobble(), sand(), sandstone()
Optional<Block> spike(), loose(), mossyLoose();  Optional<Boolean> karst(), mafic()

// net.dries007.tfc.world.feature.tree.ForestConfig (record): HolderSet<ConfiguredFeature<?,?>> entries()
// configured feature tfc:forest = {"type":"tfc:forest","config":{"entries":"#tfc:forest_trees"}},
// entries tfc:tree/<wood>_entry for 19 woods (all but mangrove)
// net.dries007.tfc.world.feature.tree.ForestConfig$Entry (record)
ClimatePlacement climate(); boolean isValid(float temp, float groundwater, float rainVar, float elevation)
float distanceFromMean(float temp, float groundwater, float rainVar, float elevation)
Optional<BlockState> fallenLog(), bushLog(); Holder<ConfiguredFeature<?,?>> treeFeature()

// net.dries007.tfc.world.chunkdata.ForestType (enum: GRASSLAND ... DEAD_BAMBOO), int getDensity()

// net.dries007.tfc.world.placement.ClimatePlacement (also the `climate` object of tfc:climate)
ClimatePlacement(float minTemp, float maxTemp, float minGroundwater, float maxGroundwater,
    float minRainVariance, float maxRainVariance, boolean rainVarianceAbsolute, int minForest,
    int maxForest, List<ForestType> types, int minElevation, int maxElevation, boolean fuzzy,
    boolean ignoreRivers)
boolean isValid(ChunkData, BlockPos, RandomSource, boolean useNorthHemisphereRainVar)
boolean isValidNonHemispheral(ChunkData, BlockPos, RandomSource)

// net.dries007.tfc.world.structure.ClimateStructurePlacement extends RandomSpreadStructurePlacement
ClimateStructurePlacement(Vec3i, StructurePlacement$FrequencyReductionMethod, float frequency, int salt,
    Optional<StructurePlacement$ExclusionZone>, ClimateStructurePlacement$ClimateSettings)
// ClimateSettings(int spacing, int separation, RandomSpreadType, ClimatePlacement climate)
// registered as "tfc:climate" (TFCStructureHooks.CLIMATE)

// helpers
static float net.dries007.tfc.util.EnvironmentHelpers.adjustAvgTempForElev(int y, float avgTemp)
static boolean net.dries007.tfc.client.overworld.SolarCalculator.getInNorthernHemisphere(BlockPos, Level)
// enums with blocks (not needed if ids are built by name, see 1.5):
// Rock {GRANITE..MARBLE: 21}, Rock$BlockType {RAW, HARDENED, SMOOTH, COBBLE, BRICKS, GRAVEL, SPIKE,
//   CRACKED_BRICKS, MOSSY_BRICKS, MOSSY_COBBLE, CHISELED, LOOSE, MOSSY_LOOSE, PRESSURE_PLATE, BUTTON,
//   AQUEDUCT, ROPE_ANCHOR}; Supplier<? extends Block> getBlock(Rock$BlockType), getStair/getSlab/getWall
// Wood {ACACIA..WILLOW: 20}, Wood$BlockType {LOG ... CRATE: 43}; Supplier<Block> getBlock(Wood$BlockType)
```

TFC: Real World 4.2.0 (`TFC-Real-World-NeoForge-1.21.1-4.2.0.jar`, MIT):

```java
// net.yazloysasha.tfcrealworld.util.geography.WaypointCoordinates
static int[] toBlockXZ(double latitude, double longitude)   // what the waypoint markers use: fits the
                                                            // longitude to the configured edges, projects,
                                                            // clamps to the map, rounds
// net.yazloysasha.tfcrealworld.util.projection.ProjectionManager
static double[] geographicToClassic(double longitude, double latitude)   // what startat.js uses
static double[] classicToGeographic(double x, double z)
// net.yazloysasha.tfcrealworld.util.geography.GeographyManager
static List<GeographyNode> allWaypoints(); static GeographyNode get(String ref)
```

Vanilla and NeoForge hooks (from `neoforge-21.1.255-server.jar` and the Mojang-named server jar):

```java
// StructureProcessor
StructureBlockInfo processBlock(LevelReader, BlockPos offset, BlockPos pos, StructureBlockInfo original,
                                StructureBlockInfo current, StructurePlaceSettings)
List<StructureBlockInfo> finalizeProcessing(ServerLevelAccessor, BlockPos offset, BlockPos pos,
                                List<StructureBlockInfo> originals, List<StructureBlockInfo> processed,
                                StructurePlaceSettings)                 // once per template placement call
StructureEntityInfo processEntity(LevelReader, BlockPos, StructureEntityInfo, StructureEntityInfo,
                                StructurePlaceSettings, StructureTemplate)          // NeoForge patch
// StructurePlacement: protected static placementCodec(RecordCodecBuilder.Instance) (salt, frequency,
//   frequency_reduction_method, exclusion_zone, locate_offset), protected abstract
//   isPlacementChunk(ChunkGeneratorStructureState, int, int)
// RandomSpreadStructurePlacement(Vec3i, FrequencyReductionMethod, float, int, Optional<ExclusionZone>,
//   int spacing, int separation, RandomSpreadType); public ChunkPos getPotentialStructureChunk(long, int, int)
// Registries.STRUCTURE_PROCESSOR, Registries.STRUCTURE_PLACEMENT (DeferredRegister targets)
```

### 1.5 `pack_world:local_materials`

**Placeholder scheme.** Templates are built from real TFC blocks of one designated rock, wood, soil
and sand colour; the processor rewrites the material part of each block id and copies the block state
property by property. TFC names every variant by a fixed pattern (checked in the dump), so one parser
covers every shape without a hand-written table:

| Family | Id pattern (placeholder in bold) | Notes |
|---|---|---|
| rock | `tfc:rock/<variant>/`**`granite`**`[_stairs\|_slab\|_wall]` | variants: raw, hardened, smooth, cobble, bricks, cracked_bricks, mossy_bricks, mossy_cobble, chiseled, gravel, loose, mossy_loose, spike, button, pressure_plate, aqueduct, rope_anchor, anvil (igneous rocks only), magma (some rocks). Stairs/slab/wall exist for raw, smooth, cobble, bricks, cracked/mossy bricks, mossy cobble. |
| ore | `tfc:ore/<grade>_<mineral>/`**`granite`** | ores sit in the local rock. |
| wood | `tfc:wood/<variant>/[<metal>/]`**`oak`**`[_stairs\|_slab]` | 41 variants incl. log, stripped_log, wood, planks, fence, log_fence, door, trapdoor, vertical_support, horizontal_support, chest, barrel, workbench, shelf, sign, hanging_sign/<metal>. |
| soil | `tfc:<variant>/`**`alfisol`**`[_stairs\|_slab\|_wall]` | grass, dirt, coarse_dirt, rooted_dirt, mud, clay, clay_grass, duff, farmland, grass_path, mud_bricks, drying_bricks, muddy_roots. |
| sand | `tfc:<variant>/`**`yellow`**`[...]` | sand, raw/smooth/cut sandstone and their shapes. |

Why TFC placeholders rather than vanilla blocks: they cover every TFC-only variant (loose rocks,
supports, aqueducts, rope anchors, ores in rock), the author builds with the real look, and an
unprocessed template still looks right. The cost: a template that really wants granite must say so
(`"rock": "granite"` fixes it). Leaks can't be told apart from genuine granite, so the palette test
(§1.10) checks the mapping itself instead.

**JSON codec** (all fields optional; `//` comments in this document's JSON are annotations, not part
of the files):

```json
{
  "processor_type": "pack_world:local_materials",
  "placeholders": {"rock": "granite", "wood": "oak", "soil": "alfisol", "sand": "yellow"},
  "rock": "local",            // or a fixed TFC rock name
  "wood": "local",            // or a fixed TFC wood name
  "soil": "local",            // or a fixed soil order
  "wood_variety": 2,          // pick among the N best-fitting trees (by piece position), 1 = always the best
  "alloy_rock": "work",       // "work" | "substitute" | "allow" (see below)
  "substitute_rock": "granite",
  "decay": {"cracked": 0.15, "mossy": 0.25, "missing": 0.0},   // bricks/cobble only, per-block seeded
  "foundation": {"max_depth": 8, "variant": "raw"}             // fill under the lowest layer, see below
}
```

**Algorithm.** Everything happens in `finalizeProcessing`, which vanilla calls once per template per
chunk being placed, after every processor's `processBlock` (so vanilla `block_rot` or `rule` decay
runs first, on placeholders):

1. *Anchor.* The piece position (`offset`). One anchor per piece means one material set per building,
   identical in every chunk the piece spans (each chunk's call recomputes the same answer). Pieces of
   a multi-piece structure can differ only if they straddle a TFC rock patch edge (~1 km patches).
2. *Resolve* (cached per anchor in a small concurrent LRU):
   - generator = `level.getLevel().getChunkSource().getGenerator()`; if it is not a
     `ChunkGeneratorExtension`, use the fallbacks.
   - **rock**: `ext.chunkDataGenerator().generateSurfaceRock(x, z)`; the name is the path end of
     `raw()`'s id (`tfc:rock/raw/basalt` → `basalt`); `sand()` gives the sand colour. A pure function of
     x, z: no chunk access, no dependence on generation order.
   - **wood**: `ChunkData d = ext.chunkDataGenerator().createAndGenerate(new ChunkPos(anchor))` (the
     same partial data `tfc:climate` uses); temperature `adjustAvgTempForElev(y, d.getAverageSeaLevelTemp)`,
     groundwater `d.getAverageGroundwater`, rain variance `d.getRainVariance` negated in the southern
     hemisphere (`SolarCalculator.getInNorthernHemisphere`, which Real World patches for real
     latitudes). Read the `tfc:forest` configured feature from the registry, keep entries whose
     `isValid(temp, gw, rainVar, y)`, sort by `distanceFromMean` exactly as TFC's `ForestFeature.getTrees`
     does, take entry `hash(anchor) % min(wood_variety, n)`. The wood name is the entry holder's key
     (`tfc:tree/<wood>_entry`). If no tree is valid (grassland, desert, tundra), take the entry with the
     smallest `distanceFromMean` among all: timber brought from the nearest woods.
   - **soil**: per column, not per anchor (TFC picks soils with noise inside a chunk). For each soil
     placeholder inside the chunk being placed (`settings.getBoundingBox()`), scan the column down from
     `WORLD_SURFACE_WG` for up to 8 blocks for a `tfc:<soil block>/<order>`; if none, use the order found
     nearest in the same chunk, else the fixed fallback `alfisol`. Columns outside the current chunk are
     never read (reading outside the generating region can crash worldgen); those blocks are mapped in
     their own chunk's call.
3. *Map* each block: parse the id; if its material is the placeholder, build the target id, look it up
   in `BuiltInRegistries.BLOCK`, and copy every property whose name and value exist on the target
   (facing/half/shape/waterlogged on stairs, type on slabs, the side connections on walls, `axis` on
   logs, TFC's `fluid`, `natural=false` on logs, `persistent` on leaves). Rotation and mirroring are
   applied by vanilla *after* processing, so the processor sees unrotated states and needs no rotation
   logic. Block entity NBT (a chest's `LootTable`) is carried over unchanged; all TFC chests share one
   block entity type (`TFCBlockEntities.CHEST`, a `ChestBlockEntity` subclass, verified), and vanilla
   adds a per-placement `LootTableSeed` to randomizable containers.
4. *Andesite-alloy rule* (design.md, "Create opens"): the alloy accepts raw or cobble andesite,
   basalt, dacite, rhyolite and diorite (`#pack:andesite_alloy_rock`), and their loose rocks craft into
   cobble. When the resolved rock is one of these five:
   - `"work"` (default): rough variants become worked variants of the same rock, which keep the local
     look but can't feed the recipe: raw/hardened → smooth, cobble → cracked_bricks, mossy_cobble →
     mossy_bricks (shapes kept: `cobble/basalt_stairs` → `cracked_bricks/basalt_stairs`), loose and
     mossy_loose → removed (air), rock anvil → the substitute rock's anvil (gabbro if the substitute is
     not igneous). Gravel, spikes, bricks, smooth, chiseled, aqueducts and ores stay.
   - `"substitute"`: every rock block of the structure uses `substitute_rock` instead.
   - `"allow"`: no change (see open question 4: in basalt country the player is already standing on
     basalt).
5. *Decay* (optional): per block, seeded by position: bricks → cracked or mossy bricks, cobble → mossy
   cobble, `missing` → air. Name-based, so stairs stay stairs (vanilla `rule` outputs fixed states and
   would lose stair shapes).
6. *Foundation* (optional): for solid placeholder-rock or soil blocks in the template's lowest layer
   inside the current chunk, add blocks below them down to the first solid natural block (max
   `max_depth`), using the resolved rock's `variant` (alloy rule applied) or soil. `finalizeProcessing`
   may add block infos; vanilla places any info inside the chunk's box, and the box is the full column
   height. This is the answer to floating pieces (§2.1).

**Missing data:**

| Case | Behaviour |
|---|---|
| Not a TFC generator (a future planet dimension) | fallback rock `granite`, wood `oak`, soil `alfisol`, logged once per dimension |
| Surface rock is not a `tfc:rock/raw/*` block (another mod's rock) | `substitute_rock` |
| Target variant doesn't exist (anvil in a sedimentary rock, magma) | anvil → smooth, magma → raw, otherwise keep the placeholder block; logged once per template and id |
| No forest entry at all (registry altered) | fallback wood |
| Soil not found | nearest in chunk, then `alfisol` |
| Real World absent | rock/wood/soil unaffected (TFC alone provides them) |

Threading and cost: worldgen places structures on many threads; the processor holds no mutable
state except the LRU (`ConcurrentHashMap` with a size cap) and a per-call `Map<Block, Block>`.
`generateSurfaceRock` and `createAndGenerate` are what TFC's own structure placement calls off-thread.

### 1.6 `pack_world:npc_fixup`

```json
{"processor_type": "pack_world:npc_fixup", "strip": ["Owner", "Navigation.Home"], "unique_spawner_uuid": true}
```

- `processEntity`: for entities whose id is in the `easy_npc` namespace, remove `Owner` (so no player
  owns and can edit it; operators still can) and `Navigation.Home` (absolute coordinates of where the
  author built it; without it, Easy NPC's `finalizeSpawn` sets the home to where it was placed).
  Vanilla already removes the entity `UUID` and assigns a fresh one.
- `processBlock`: for `easy_npc` spawner block entities, replace the entity UUID inside
  `StoredPresetData.data` and `SpawnData.entity`, and the spawner's own `UUID`, with UUIDs derived from
  the block position and world seed, so each placed spawner owns one stable NPC (§4 explains why).
- Uses NBT keys only: no compile dependency on Easy NPC; if Easy NPC is absent the processor does nothing
  (vanilla drops unknown entities and blocks from templates).

### 1.7 `pack_world:geographic`

```json
"placement": {
  "type": "pack_world:geographic",
  "site": "stonehenge",
  "latitude": 51.1789, "longitude": -1.8262,
  "offset": [0, 0],            // optional block nudge after projection (coastal sites)
  "salt": 51178901             // required by vanilla's placement codec; unused for the choice
}
```

- **Codec**: `placementCodec(instance)` (salt, frequency, frequency_reduction_method, exclusion_zone,
  locate_offset) plus `site`, `latitude`, `longitude`, `offset`. Constructed as a
  `RandomSpreadStructurePlacement` with spacing 4096, separation 0 (TFC's `ClimateStructurePlacement`
  extends the same class); `type()` returns ours.
- **`isPlacementChunk(state, cx, cz)`**: `cx, cz == siteChunk()` and `SiteGuard.enabled(site)`.
  `siteChunk()` = `WaypointCoordinates.toBlockXZ(lat, lon)` + offset, `>> 4`, cached together with the
  Real World values it depends on (scale and map edges, read from `TFCRealWorldConfig` on each call and
  compared), so switching between single-player worlds with different scales recomputes it. Using the
  waypoint's own function puts the structure exactly under its Real World marker. Without Real World:
  always false.
- **`getPotentialStructureChunk(seed, rx, rz)`** returns the site chunk, so `/locate structure
  pack:site/stonehenge` finds it from anywhere on the map (vanilla's random-spread search asks every
  grid cell for its candidate; with spacing 4096 the first ring already covers it).
- **Players far apart** (`/startat` on different continents): nothing depends on players. Each site is a
  pure function of its coordinates and the world's Real World settings, generated when anyone first
  comes near.
- **Generation order**: a structure start is created when its start chunk reaches `structure_starts`;
  any chunk within 8 chunks that generates first pulls the start chunk to that (cheap, terrain-free)
  status during its `structure_references` step. So pieces and terrain adaptation come out the same
  whichever side players approach from. Nothing in the placement reads chunks.
- **Only new chunks**: a random-spread structure can only start in a new chunk, so it never lands in
  explored land (at most a frontier piece is cut off, as with every new-chunks-only structure). A fixed
  site is different: it *will* land on its coordinates, explored or not. If the start chunk already
  exists, nothing generates; if it is new but some footprint chunks exist, half a site appears.
  `SiteGuard` prevents both: on `LevelEvent.Load` of the overworld, a world whose `SavedData`
  (`pack_world_sites`) is absent records the current site list if its game time is 0 (a new world),
  or an empty list otherwise (a world that existed before the mod). A site missing from the list never
  places; `/pack_world sites enable <site>` (operators) adds it after checking the area is unexplored,
  and `/pack_world sites` lists sites with chunk, block position and state. Since the sites ship before
  the first long-lived world, every real world gets them all.

### 1.8 Optional: `pack_world:climate` loot condition

`{"condition": "pack_world:climate", "min_temperature": 4, "max_temperature": 22, "min_groundwater": 150}`
reads TFC's chunk data at the loot origin (the chest, rolled when first opened, by then a full chunk).
Lets one homestead loot table hold rice for warm wet places and rye for cold ones.

### 1.9 Where the jar lives

packwiz takes local files: "just drop them in the mods folder alongside the .pw.toml files" (packwiz
docs, "Adding mods"), then `packwiz refresh`. The jar becomes a plain `[[files]]` entry in
`index.toml` with its sha256, `packwiz serve` (the test server's sync, `mclib/server.py`) and any
pack host serve it, and packwiz-installer installs it on both sides (plain files carry no side). A
Modrinth or CurseForge export puts it under overrides. Committed: `mod/` sources plus
`mods/pack_world-<version>.jar` (tens of KB). Small tooling follow-ups: `mod_report.py` should list it as
a local mod (no Modrinth metadata), and `.packwizignore` gets `/mod/`. Before it enters the pack, test
runs can add the freshly built jar with `TestServer.set_extra_mods([...])`, as `pregen.py` does with
Chunky.

### 1.10 Testing

Gametests need MDG's dev runtime with TFC on the runtime classpath; the repo already has a better
harness, the headless test server with dev-only KubeJS scripts. A new `tools/structures_test.py`
(modelled on `startat_test.py`, one fresh world, ~3 minutes) runs:

1. **Palette test, exhaustive, no chunk generation**: for every template, call
   `PackWorldApi.mapTemplate(id, rock, wood, soil, sand, alloyPolicy)` for all 21 rocks × 20 woods × 8
   soils × 7 sands: every output id exists, no placeholder id survives, block properties survive, no
   rough variant of an alloy rock appears under `"work"`.
2. **Placement in the world**: `/place structure <id> x y z` (bypasses spacing and biome) at five
   rocksample places with different rock and climate (e.g. Rome, Stockholm, Lhasa, Manaus, Cairo).
   Python reads the region files (`tools/worldview/region.py`) and checks the blocks against
   `PackWorldApi.materialsAt` for that anchor, the chest loot tables, the NPC (present, no `Owner`, home
   inside the structure), and **floating**: per template column, the air gap between the lowest placed
   block and the ground (fail above 1 block).
3. **Loot lint**: roll each loot table 200 times in-game (`LootTable.getRandomItems`), and check every
   item against the deny-list and the table's step cap from the progression checker (§2.1).
4. **Sites**: each site's chunk from `PackWorldApi.sites()` equals `toBlockXZ >> 4`, `/locate` finds
   it, and the start position is dry land (TFC biome not ocean/lake/river) with the start-point
   finder from `startat.js`; a site in water fails and asks for an `offset`.
5. **Density estimate**: `PackWorldApi.estimateDensity(setId, n)` asks each structure set's placement
   for `n` random land chunks without generating anything (`isStructureChunk` plus the biome at the
   chunk centre) and reports structures per 1,000 × 1,000 blocks, for tuning spacing.

Plus the existing loop: `smoke.py`, then `worldgen_check.py --golden` and `--accept` (§6).

### 1.11 Maintenance across TFC and Real World updates

- TFC surface used: 2 generator methods, 5 `ChunkData` getters, `RockSettings.raw()/sand()`, the
  `ForestConfig` entry record and its two methods, two helpers, the `tfc:forest` feature id and the
  block naming patterns. Real World: one static method and its config. TFC and Real World updates are
  already rare and gated by `worldgen_check.py` (no terrain change allowed), so each update costs a
  rebuild (compile errors show API breaks), `structures_test.py` (the palette test catches renamed
  variants) and the usual `worldgen_check`. Estimate: 15 minutes per update, a few hours if TFC renames
  blocks or reworks forests.
- Easy NPC: no compile dependency; NBT key renames (`StoredPresetData`, `Navigation.Home`, `Owner`) are
  caught by the NPC checks.
- NeoForge 1.21.1 point releases: the processor and placement APIs are vanilla and stable.
- A Minecraft version change would be a port, but the pack is pinned to 1.21.1.

---

## 2. The structure catalogue

### 2.1 Shared conventions

**Files** (all written by `tools/structures/build.py` from `tools/structures/catalogue.json`):

```
kubejs/data/pack/worldgen/structure/<id>.json            jigsaw structure
kubejs/data/pack/worldgen/structure_set/<id>.json        tfc:climate or pack_world:geographic placement
kubejs/data/pack/worldgen/template_pool/<id>/start.json  (+ further pools for multi-piece ones)
kubejs/data/pack/worldgen/processor_list/<name>.json
kubejs/data/pack/structure/<id>/<piece>.nbt              templates
kubejs/data/pack/loot_table/chests/<id>.json
kubejs/data/pack/tags/worldgen/biome/has_structure/<id>.json
config/tfc_real_world/geography/pack/waypoints/<site>.json   (sites only)
```

**Landform groups.** TFC biomes are landforms, not climates (125 biomes; no `is_land` tag), so the
generator expands named groups into explicit biome lists per structure tag. Groups (from TFC's own
`tfc:`/`c:` tags and biome list):

| Group | Biomes |
|---|---|
| LOWLAND | plains, lowlands, rolling_hills, hills, mud_flats, river_valley? (*check it isn't water at the start position*), salt_marsh (only where named), knob_and_kettle, drumlins, the karst plains (burren/cenote/doline/shilin/tower_karst_plains) |
| UPLAND | highlands, plateau, plateau_wide, rocky_plateau, the karst hills/highlands/plateaus, canyons, low_canyons, old_mountains |
| MOUNTAIN | `#tfc:is_continental_mountains`, `#tfc:is_oceanic_mountains`, collisional_mountains, volcanic_mountains (no lakes) |
| DRY | badlands, buttes, mesas, hoodoos, dune_sea, grassy_dunes, salt_flats, stair_step_canyons, whorled_canyons, rocky_plateau |
| COLD | drumlins, knob_and_kettle, patterned_ground, inverted_patterned_ground, stone_circles, tuyas |
| COAST | shore, coastal_dunes, embayments, tidal_flats, rocky_shores, sea_stacks, setback_cliffs, terrace_lower, terrace_upper (TFC files these under `#tfc:is_ocean`) |
| never | oceans, lakes (`#c:is_lake`), river, ice sheets (`#tfc:is_ice_sheet`), glaciated mountains, active volcanoes |

**`tfc:climate` gotchas** (verified in 4.2.11 bytecode and the 1.21.x source):

- The placement evaluates the climate at `BlockPos(chunk minX, 0, chunk minZ)`: **y is always 0**. So
  `min_elevation`/`max_elevation` see 0 (leave them out), and temperature is the sea-level average
  (TFC doesn't adjust below sea level). Altitude is expressed with landform groups.
- With `"fuzzy": true`, give both bounds of temperature and groundwater: the default bounds are
  infinite, the midpoint is NaN, and the check never passes.
- Scales: temperature in °C (annual mean), groundwater 0-500 (rain plus rivers; TFC's oak wants
  210-500, acacia 90-500, blackwood 35-215), rain variance -1..1, forest density 0-4.
- Spacing must exceed separation; spacing ≤ 4096 chunks.

**Density at 20 m per block.** One attempt per `spacing` × `spacing` chunk cell; with a share `p` of
cells passing climate and landform, instances of one structure average about `16·spacing/√p` blocks
apart. Walking (~4.3 blocks/s) a player sweeps a ~400-block-wide band, ~6 million blocks² an hour; an
airship far more. Targets: ruins of all kinds together ~1 per 250-350 blocks in settled climates (the
sum below gives ~3.4e-3 structures per chunk², i.e. ~17 chunks ≈ 280 blocks between neighbours),
inhabited spots ~1 per 1,500-2,000 blocks (≈ 2 per hour of walking). The table's spacing is per set and
is the main tuning knob.

| spacing (chunks) | 20 | 24 | 32 | 40 | 48 | 64 | 96 | 112 | 128 |
|---|---|---|---|---|---|---|---|---|---|
| cell size (blocks) | 320 | 384 | 512 | 640 | 768 | 1,024 | 1,536 | 1,792 | 2,048 |
| mean distance at p = 0.3 | 580 | 700 | 935 | 1,170 | 1,400 | 1,870 | 2,800 | 3,270 | 3,740 |

**Terrain adaptation under TFC.** TFC's noise filler adds the Beardifier to its density (verified,
`ChunkNoiseFiller.calculateBlockStateAtNoise`), so `beard_thin`, `beard_box`, `bury` and `encapsulate`
work. But TFC clamps terrain density to [-1, 1] and slides it down by 0.2 per block above the surface
height, so the beard's contribution (well under 1) can only raise ground by about 2 blocks; vanilla's
gentler gradient lets it fill much more. That explains the floating structures TFC Structure Compat
reported (my reading of the code; *unverified until the float test*). Hence: `beard_thin` for surface
structures, templates with a 2-4 block skirt of placeholder rock below the floor, and the processor's
`foundation` option for anything on slopes; flatter landform groups for large footprints. Underground
pieces use `none`: the beard would carve air up to ~12 blocks above an underground floor. TFC's
`surfaceHeight` in chunk data is computed before the beard (verified), so structures don't change
`tfc:chunk_data`.

**Placement height.** `project_start_to_heightmap: WORLD_SURFACE_WG` (TFC overrides `getBaseHeight`
with its own height), `OCEAN_FLOOR_WG` for the wreck. Single-piece structures use pools with several
weighted variants (`size` 1); the trading post is the only multi-piece one.

**Building rules for templates.** Cobble and mossy cobble are in TFC's `#tfc:can_landslide` and slide
when a neighbour updates: use them only at ground level and as rubble; walls from bricks, raw or
smooth rock (raw and smooth can collapse when a collapse is triggered next to them; bricks don't).
Mine galleries need TFC supports. No vanilla blocks except air, structure void and jigsaw (the golden
check flags any other); TFC chests (`tfc:wood/chest/oak`) for loot.

**Loot rules** (design.md: saves time inside an era, never skips one):

- Deny-list, checked by the linter: `tfc:metal/*/(wrought_iron|cast_iron|pig_iron|steel|black_steel|
  red_steel|blue_steel)` and the weak/high-carbon intermediates, `tfc:raw_iron_bloom`,
  `tfc:refined_iron_bloom`, `tfc:bloomery`, `tfc:blast_furnace`, any `create:`, `gtceu:` or
  `minecraft:iron_*` item.
- Step caps from the progression checker (`tools/.data/quests/pack_items.json`): stone-age loot ≤ step 6,
  copper age ≤ 8, bronze age ≤ 13 (for reference: ceramic molds 5, copper ingot 6, copper tools 7,
  bronze ingot 7, bronze tools 8, copper sheet 12, rope/burlap/glue 13, cut gems 16, wrought iron 19).
  Items the checker can't reach (wild seeds, fruit saplings, wool, jam jars) are allowed explicitly.
- Food is fine: chest loot is rolled when the chest is first opened, so it is fresh then. TFC's
  `tfc:rotten` loot function is available for graves. Fixed containers in templates (placed items,
  ingot piles, vessels) never hold food: their NBT would carry the authoring world's dates.
- All ids below were checked against the dump (184 items, 0 missing) and pack_query's steps.

### 2.2 Overview

| # | Id | Era | Footprint | Landforms | Climate (`tfc:climate`) | Spacing / sep | Adaptation | Template |
|---|---|---|---|---|---|---|---|---|
| 1 | `hunters_camp` | stone | 9×9×5 | LOWLAND, UPLAND | t -12..24, gw 60..450 | 24 / 8 | beard_thin | procedural |
| 2 | `prospector_camp` | copper | 11×11×6 | UPLAND, MOUNTAIN | t -10..30, gw 30..450 | 40 / 14 | beard_thin | hand + post-pass |
| 3 | `mine_adit` | copper-bronze | 7×20×7, ~12 deep | UPLAND, MOUNTAIN | t -12..30, gw 0..500 | 48 / 16 | none | hand + post-pass |
| 4 | `bloomery_ruin` | late bronze | 13×11×9 | LOWLAND, UPLAND | t -5..28, gw 100..450, forest ≥ 1 | 64 / 20 | beard_thin | hand + post-pass |
| 5 | `cairn` | stone-copper | 5×5×5 | UPLAND, MOUNTAIN, COLD | any | 20 / 6 | beard_thin | procedural |
| 6 | `standing_stones` | stone | 3×3 to 17×17 | LOWLAND, UPLAND, COLD | t -10..24, gw 40..450 | 32 / 10 | beard_thin | procedural |
| 7 | `wayside_shrine` | copper | 3×3×4 | LOWLAND, UPLAND | t -10..30, gw 40..450 | 32 / 10 | beard_thin | procedural |
| 8 | `barrow` | stone-copper | 9×21×6 | LOWLAND, UPLAND | t -6..20, gw 100..450 | 40 / 12 | beard_thin | procedural + hand chamber |
| 9 | `wreck` | bronze | 7×19×7 | COAST | t -5..32 | 36 / 12 | beard_thin (OCEAN_FLOOR_WG) | hand + post-pass |
| 10 | `homestead_temperate` | copper-bronze | 15×13×8 | LOWLAND | t 2..20, gw 180..450, fuzzy | 40 / 14 | beard_thin | hand + post-pass |
| 11 | `homestead_dry` | copper-bronze | 13×13×6 | LOWLAND, DRY | t 10..32, gw 30..180, fuzzy | 40 / 14 | beard_thin | hand + post-pass |
| 12 | `homestead_boreal` | copper | 11×11×7 | LOWLAND, UPLAND, COLD | t -14..4, gw 120..450 | 40 / 14 | beard_thin | hand + post-pass |
| 13 | `trading_post` (inhabited) | bronze | ~35×35 (4-6 pieces) | LOWLAND (river valleys preferred) | t -6..26, gw 80..450 | 128 / 40 | beard_thin | hand, multi-piece |
| 14 | `hermit` (inhabited) | copper | 9×9×7 | UPLAND, MOUNTAIN, forests | t -14..22, gw 100..500, forest ≥ 2 | 96 / 32 | beard_thin | hand + post-pass |
| 15 | `travelling_smith` (inhabited) | bronze | 13×9×6 | LOWLAND, UPLAND | t -6..28, gw 60..450 | 112 / 36 | beard_thin | hand + post-pass |

Wood and rock for every structure come from `local_materials` unless noted; "palette" below lists the
placeholder blocks used. Climate windows overlap on purpose at the homestead edges (fuzzy); salts are
unique per set (e.g. 2026100701..15).

### 2.3 Entries

**1. Hunters' camp** (stone age). A season's camp of people who followed the herds: a firepit in a ring
of loose rocks, one or two lean-tos of logs and thatch, a drying frame of sticks, bones and flint flakes
on the ground, a small cache under the lean-to.
Palette: `tfc:rock/loose/granite`, `tfc:rock/mossy_loose/granite`, `tfc:wood/log/oak`,
`tfc:wood/log_fence/oak`, `tfc:thatch`, `tfc:firepit` (unlit), `tfc:groundcover/bone`,
`tfc:groundcover/flint`, `tfc:groundcover/stick`, `tfc:wood/chest/oak`, `tfc:grass_path/alfisol`.
Loot `pack:chests/hunters_camp` (2-4 rolls): `minecraft:flint` 2-5 (w20), `tfc:straw` 4-12 (15),
`minecraft:bone` 1-4 (12), `tfc:stone/knife_head/sedimentary` and `/igneous_extrusive` (8 each),
`tfc:stone/javelin_head/sedimentary` (8), `tfc:stone/axe_head/igneous_intrusive` (6), `tfc:firestarter`
(6), `tfc:small_raw_hide` (8), `minecraft:feather` 2-6 (6), `tfc:food/venison` or `tfc:food/rabbit` 1-2
with `tfc:rotten` (4), `tfc:seeds/jute` 1-3 (4). Cap: step 6.

**2. Prospector's camp** (copper age). A tent of log frame and thatch, a sluice by the water if any
(`tfc:wood/sluice/oak`), sample stones laid out on a plank table, a pan, a chest.
Palette: `tfc:wood/log/oak`, `tfc:wood/planks/oak[_slab]`, `tfc:thatch`, `tfc:wood/sluice/oak`,
`tfc:ore/small_native_copper`, `tfc:ore/small_malachite`, `tfc:ore/small_cassiterite` (surface
indicator blocks), `tfc:rock/cobble/granite` (fire ring), `tfc:wood/chest/oak`.
Loot `pack:chests/prospector_camp` (2-4): `tfc:ore/small_native_copper`, `small_malachite`,
`small_cassiterite`, `small_tetrahedrite`, `small_sphalerite`, `small_hematite` 1-3 (10 each),
`tfc:ore/poor_native_copper`, `poor_cassiterite` 1-4 (8 each), `tfc:ore/normal_malachite` 1-2 (4),
`tfc:pan/empty` (5), `tfc:ceramic/propick_head_mold` (4), `tfc:ceramic/vessel` (4), `minecraft:charcoal`
2-6 (6), `tfc:powder/flux` 1-3 (3), `tfc:food/barley_bread` 1-2 (4), `tfc:metal/propick_head/copper` (2),
`tfc:metal/propick/copper` (1). Cap: step 8. (Later: a `pack_world` loot function could pick ores
whose TFC veins occur in the local rock; *not in scope*.)

**3. Mine adit** (copper to bronze). An inclined drift from the surface down ~12 blocks to a short
gallery: square-set TFC supports every 3 blocks, a few poor ore blocks left in the walls, dead torches,
a cave-in of rubble at the end, a crate of gear. Built as a sloped shaft so it works on any ground
(a horizontal adit would need a hillside the jigsaw can't choose). Adaptation `none`; the entrance
template carries its own collar of placeholder rock and soil.
Palette: `tfc:wood/vertical_support/oak`, `tfc:wood/horizontal_support/oak`, `tfc:rock/raw/granite`,
`tfc:rock/cobble/granite` (cave-in only), `tfc:rock/gravel/granite`, `tfc:ore/poor_native_copper/granite`,
`tfc:ore/poor_malachite/granite`, `tfc:dead_wall_torch`, `tfc:wood/chest/oak`, `tfc:dirt/alfisol`.
Loot `pack:chests/mine_adit` (2-3): `tfc:ore/poor_native_copper`, `poor_cassiterite`,
`poor_tetrahedrite` 2-6 (10 each), `tfc:torch` 2-6 (8), `minecraft:charcoal` 2-6 (6),
`tfc:ceramic/pickaxe_head_mold` (4), `tfc:metal/pickaxe_head/copper` (4), `tfc:rope` 1-3 (4),
`tfc:metal/chisel/copper` (3), `minecraft:bone` (3), `tfc:metal/ingot/copper` (2). Cap: step 13.

**4. Collapsed bloomery smithy** (end of the bronze age: people who tried iron). A roofless stone
smithy, its chimney fallen into a heap of bricks, charcoal layers in the corner, a rock anvil (igneous
rock only, otherwise none), an ingot pile with one or two copper ingots, a chest. No bloomery block and
no iron: the hint is the iron ore in the chest.
Palette: `tfc:rock/bricks/granite[_stairs|_slab|_wall]`, `tfc:rock/cracked_bricks/granite`,
`tfc:rock/mossy_bricks/granite`, `tfc:rock/smooth/granite`, `tfc:rock/anvil/granite`,
`tfc:charcoal_pile`, `tfc:ingot_pile` (fixed NBT: copper), `tfc:wood/planks/oak`, `tfc:wood/chest/oak`.
Processor: `decay {cracked 0.2, mossy 0.25}`, `block_rot` 0.85 on bricks.
Loot `pack:chests/bloomery_ruin` (2-4): `minecraft:charcoal` 4-12 (10), `tfc:ceramic/ingot_mold` (8),
`tfc:powder/flux` 2-6 (8), `tfc:fire_clay` 2-4 (6), `tfc:ceramic/fire_brick` 2-8 (5),
`tfc:metal/ingot/copper` 1-2 (5), `tfc:ceramic/axe_head_mold`, `pickaxe_head_mold`, `hammer_head_mold`,
`saw_blade_mold`, `chisel_head_mold` (4 each), `tfc:ore/normal_hematite`, `normal_limonite`,
`normal_magnetite` 1-4 (4 each), `tfc:metal/ingot/bronze` (2), `tfc:metal/ingot/tin` (2),
`tfc:crucible` (1). Cap: step 13.

**5. Cairn** (stone to copper age). A cone of stones on high ground; half the variants are waymarkers,
half hide a stone cist with grave goods.
Palette: `tfc:rock/raw/granite[_slab]`, `tfc:rock/mossy_cobble/granite` (base ring only),
`tfc:rock/loose/granite`, `tfc:rock/mossy_loose/granite`, `tfc:wood/chest/oak` (cist variants).
Loot `pack:chests/cairn` (1-2): `minecraft:bone` 1-3 (10), `tfc:stone/axe_head/metamorphic` (6),
`tfc:stone/knife_head/igneous_intrusive` (6), `tfc:ceramic/jug` (3), `tfc:ceramic/bowl` (3),
`tfc:metal/knife/copper` (2), `tfc:ore/amethyst` (1), `tfc:ore/opal` (1). Cap: step 8.

**6. Standing stones** (stone age). A lone menhir, a pair, a short row, or (1 in 6) a ring of 7-12 stones
up to 17 blocks across; one variant in four has a buried offering pit.
Palette: `tfc:rock/raw/granite`, `tfc:rock/smooth/granite`, `tfc:rock/mossy_loose/granite`,
`tfc:wood/chest/oak` (buried, offering variants).
Loot `pack:chests/standing_stones_offering` (1-2): `tfc:ceramic/bowl` (6), `tfc:seeds/barley`, `oat`,
`rye` 1-3 (4 each), `minecraft:bone` (4), `tfc:metal/ingot/copper` (1). Cap: step 6.

**7. Wayside shrine** (copper age). A knee-high stone niche with a stone slab roof, a candle, an offering
bowl and jug (placed items with fixed contents: bowl, candle; never food), sometimes a small chest.
Palette: `tfc:rock/bricks/granite[_slab|_stairs]`, `tfc:rock/smooth/granite_slab`, `tfc:candle`,
`tfc:placed_item`, `tfc:grass_path/alfisol`, `tfc:wood/chest/oak` (1 variant in 3).
Loot `pack:chests/wayside_shrine` (1-2): `tfc:candle` 1-2 (6), `tfc:powder/salt` 1-2 (6), `tfc:seeds/*` of
common crops 1-3 (4 each; with the optional climate condition later), `tfc:ceramic/jug` (4),
`tfc:jar/cherry`, `tfc:jar/plum` (2 each). Cap: step 8.

**8. Barrow** (stone to copper age). A long earthen mound with a stone-lined passage and a chamber; a
small fenced graveyard of slab headstones as the cheaper variant.
Palette: `tfc:grass/alfisol`, `tfc:dirt/alfisol` (mound), `tfc:rock/raw/granite`,
`tfc:rock/smooth/granite[_slab]`, `tfc:rock/mossy_bricks/granite`, `tfc:wood/fence/oak` (graveyard),
`tfc:wood/chest/oak`.
Loot `pack:chests/barrow` (2-3): `minecraft:bone` 1-4 (10), `tfc:ceramic/jug`, `tfc:ceramic/bowl` (6 each),
`tfc:metal/knife/copper` (5), `tfc:bone_needle` (5), `tfc:metal/axe_head/copper`,
`tfc:metal/javelin_head/copper` (3 each), `tfc:metal/ingot/gold` (1), `tfc:ore/amethyst`, `tfc:ore/opal`,
`tfc:ore/lapis_lazuli` (1 each), `tfc:metal/knife/bronze` (1). Cap: step 8.

**9. Coastal wreck** (bronze age; after the Uluburun wreck, which carried copper and tin ingots). A
plank-built hull on its side on the beach, ribs of logs, a broken mast, cargo spilled in the sand.
Palette: `tfc:wood/planks/oak[_stairs|_slab]`, `tfc:wood/log/oak`, `tfc:wood/stripped_log/oak`,
`tfc:wood/fence/oak`, `tfc:sand/yellow`, `tfc:groundcover/driftwood` (as block), `tfc:wood/chest/oak`
×2, `tfc:ingot_pile` (fixed: copper).
Loot `pack:chests/wreck` (3-5): `tfc:metal/ingot/copper` 1-4 (10), `tfc:powder/salt` 2-6 (8),
`tfc:metal/ingot/tin` 1-3 (6), `tfc:rope` 1-4 (6), `tfc:ceramic/jug` (5), `tfc:burlap_cloth` 1-3 (5),
`tfc:jar/olive`, `tfc:jar/cherry`, `tfc:jar/plum` 1-2 (4 each), `tfc:ceramic/large_vessel` (3),
`tfc:metal/fish_hook/copper` (3), `tfc:glue` 1-2 (2), `tfc:metal/ingot/bronze` (2),
`tfc:ore/lapis_lazuli` (1). Cap: step 13. (Tin is the bronze gate for tin-poor starts; open question 13.)

**10. Abandoned homestead, temperate** (copper to bronze age). A wattle-and-daub longhouse with a thatch
roof partly fallen in, a hearth, a loom frame, a fenced garden gone wild (`tfc:wild_crop/barley`,
`/wheat`), a woodpile.
Palette: `tfc:wattle` (daubed/framed states), `tfc:thatch`, `tfc:wood/log/oak`,
`tfc:wood/planks/oak[_slab]`, `tfc:wood/door/oak`, `tfc:wood/fence/oak`, `tfc:wood/fence_gate/oak`,
`tfc:wood/loom/oak`, `tfc:firepit`, `tfc:log_pile`, `tfc:rock/cobble/granite` (hearth, ground level),
`tfc:farmland/alfisol`, `tfc:grass_path/alfisol`, `tfc:wild_crop/barley`, `tfc:wood/chest/oak`.
Loot `pack:chests/homestead_temperate` (3-5): `tfc:straw` 4-16 (8), seeds `tfc:seeds/barley`, `oat`,
`rye`, `wheat`, `beet`, `cabbage`, `carrot`, `onion`, `garlic`, `potato`, `green_bean`, `jute` 1-4
(5 each), `tfc:food/barley_grain`, `wheat_grain` 2-6 (4 each), `tfc:ceramic/jug`, `pot`, `bowl`,
`vessel` (4 each), `tfc:spindle` (3), `tfc:wool_yarn` 2-6 (3), `tfc:bone_needle` (3),
`tfc:ceramic/spindle_head` (2), `tfc:handstone` (2), `tfc:plant/red_apple_sapling`, `plum_sapling`,
`cherry_sapling` (1 each). Cap: step 13.

**11. Abandoned homestead, dry** (copper to bronze age). A flat-roofed mud-brick house around a small
court, a cistern, storage jars.
Palette: `tfc:mud_bricks/alfisol[_stairs|_slab|_wall]` (becomes the local soil's bricks),
`tfc:smooth_mud_bricks`, `tfc:wood/log/oak` (roof beams: acacia/blackwood/palm locally),
`tfc:thatch`, `tfc:ceramic/large_vessel` (empty blocks), `tfc:rock/smooth/granite`, `tfc:sand/yellow`,
`tfc:wood/chest/oak`.
Loot `pack:chests/homestead_dry` (3-5): `tfc:seeds/maize`, `squash`, `soybean`, `red_bell_pepper`,
`tomato`, `onion`, `papyrus` 1-4 (5 each), `tfc:powder/salt` 2-6 (6), `tfc:ceramic/jug`, `pot`,
`large_vessel` (4 each), `tfc:jar/olive` (3), `tfc:plant/olive_sapling`, `lemon_sapling`,
`orange_sapling` (1 each), `tfc:straw` (6). Cap: step 13.

**12. Abandoned homestead, boreal** (copper age). A low log cabin with a turf roof, a smoke hole, a fish
rack, hides.
Palette: `tfc:wood/log/oak` (spruce/pine/white cedar/aspen locally), `tfc:wood/planks/oak`,
`tfc:grass/alfisol` and `tfc:dirt/alfisol` (turf roof), `tfc:firepit`, `tfc:rock/raw/granite`
(hearth), `tfc:wood/chest/oak`.
Loot `pack:chests/homestead_boreal` (3-4): `tfc:seeds/rye`, `potato`, `cabbage`, `garlic` 1-3
(5 each), `tfc:medium_raw_hide` (5), `tfc:small_sheepskin_hide` (4), `tfc:food/salmon` or
`tfc:food/cod` 1-3 (4), `tfc:groundcover/pinecone` 2-6 (4), `minecraft:feather` 2-6 (4),
`tfc:metal/fish_hook/copper` (2), `tfc:wool_cloth` (2). Cap: step 13.

**13. Trading post** (inhabited, bronze age). A log palisade (`tfc:wood/log_fence`) around a longhouse,
a market awning, a pen and a storehouse, on a river valley if possible. One trader (spawner, §4),
optionally a second (a potter). Multi-piece jigsaw: centre (longhouse + yard), 2-4 side pieces
(storehouse, awning, pen, gate), `max_distance_from_center` 48, `size` 3.
Palette: wood family (log, log_fence, planks, stairs, door, trapdoor, chest, barrel, workbench, shelf),
`tfc:thatch`, `tfc:rock/bricks/granite` (hearth, footings), `tfc:grass_path/alfisol`.
Loot (storehouse) `pack:chests/trading_post` (2-3): `tfc:burlap_cloth`, `tfc:rope`, `tfc:powder/salt`,
`tfc:ceramic/jug`, `tfc:straw`, seeds. Easy NPC: `pack:trader` (§4). Cap: step 13.

**14. Hermit's hut** (inhabited, copper age). A stone-and-turf hut against a rock outcrop with a herb
garden, deep in forest or high up. One hermit (single entity in the template; one-off, so killing him
is final). Easy NPC: `pack:hermit`.
Palette: `tfc:rock/raw/granite`, `tfc:rock/mossy_cobble/granite` (ground course), `tfc:thatch`,
`tfc:grass/alfisol`, `tfc:wood/log/oak`, `tfc:wood/door/oak`, `tfc:firepit`, `tfc:wood/chest/oak`.

**15. Travelling smith** (inhabited, bronze age). A camp with a cart (fences and planks, no wheels in
TFC), a charcoal forge (`tfc:charcoal_forge`, unlit, no bellows), a rock anvil, sacks, a lean-to. One
smith (spawner). Easy NPC: `pack:smith`.
Palette: wood family, `tfc:charcoal_forge`, `tfc:rock/anvil/granite` (non-igneous → smooth),
`tfc:charcoal_pile`, `tfc:thatch`, `tfc:rock/cobble/granite` (forge pit).

### 2.4 Example data (hunters' camp)

```json
// kubejs/data/pack/worldgen/structure/hunters_camp.json
{"type": "minecraft:jigsaw", "biomes": "#pack:has_structure/hunters_camp", "step": "surface_structures",
 "spawn_overrides": {}, "terrain_adaptation": "beard_thin", "start_pool": "pack:hunters_camp/start",
 "size": 1, "start_height": {"absolute": 0}, "project_start_to_heightmap": "WORLD_SURFACE_WG",
 "max_distance_from_center": 32, "use_expansion_hack": false}

// kubejs/data/pack/worldgen/structure_set/hunters_camp.json
{"structures": [{"structure": "pack:hunters_camp", "weight": 1}],
 "placement": {"type": "tfc:climate", "salt": 2026100701, "spacing": 24, "separation": 8,
   "climate": {"min_temperature": -12, "max_temperature": 24, "min_groundwater": 60, "max_groundwater": 450}}}

// kubejs/data/pack/worldgen/template_pool/hunters_camp/start.json
{"fallback": "minecraft:empty", "elements": [
  {"weight": 3, "element": {"element_type": "minecraft:single_pool_element", "location": "pack:hunters_camp/lean_to_a",
                            "processors": "pack:camp", "projection": "rigid"}},
  {"weight": 2, "element": {"element_type": "minecraft:single_pool_element", "location": "pack:hunters_camp/two_shelters",
                            "processors": "pack:camp", "projection": "rigid"}}]}

// kubejs/data/pack/worldgen/processor_list/camp.json
{"processors": [
  {"processor_type": "minecraft:block_rot", "integrity": 0.9, "rottable_blocks": "#pack:ruin_rottable"},
  {"processor_type": "pack_world:local_materials", "foundation": {"max_depth": 4, "variant": "raw"}}]}

// kubejs/data/pack/loot_table/chests/hunters_camp.json (excerpt)
{"type": "minecraft:chest", "pools": [{"rolls": {"type": "minecraft:uniform", "min": 2, "max": 4}, "entries": [
  {"type": "minecraft:item", "name": "minecraft:flint", "weight": 20,
   "functions": [{"function": "minecraft:set_count", "count": {"type": "minecraft:uniform", "min": 2, "max": 5}}]},
  {"type": "minecraft:item", "name": "tfc:food/venison", "weight": 4, "functions": [{"function": "tfc:rotten"}]}]}]}
```

---

## 3. How the NBT templates get made

| | (a) Built by hand in creative | (b) Generated in Python | (c) Mix |
|---|---|---|---|
| How | Build with TFC blocks of the placeholder materials in a creative TFC world; save with a structure block (≤ 48×48×48, lands in `<world>/generated/<ns>/structure/`) or Create's schematic and quill (larger, `schematics/*.nbt`, same vanilla structure format, entities included); copy into `kubejs/data/pack/structure/`. | Shapes in code (rings, cones, mounds, walls, decay passes) written as structure NBT (gzip compound: `DataVersion` 3955, `size`, `palette`, `blocks`, `entities`) by a small NBT writer next to `tools/worldview/nbt.py`. | Hand-built base; a Python post-pass adds variants (decay, rubble), places loot chests with their `LootTable`, injects NPC entities from preset files, strips UUIDs, and lints. |
| Good at | Architecture, interiors, anything that needs an eye. | Stones, piles, mounds, rows, rings; many variants for free; reviewable diffs of the generator instead of binary files. | Both; one source of truth for loot and NPCs. |
| Weak at | Variants cost author time; NBT diffs are opaque; easy to leak a wrong block or a UUID. | Buildings look procedural. | Two steps. |
| Author time | 1-3 h per building | none | building time only |

**Recommendation.**

- Procedural (b): cairn, standing stones (incl. Carnac rows, Göbekli Tepe's T-pillars), barrow mound
  (chamber can be hand-built), hunters' camp, wayside shrine, the stone circle of Nabta Playa.
- Hand-built with post-pass (c): prospector's camp, mine adit, bloomery smithy, wreck, the three
  homesteads, trading post (multi-piece with jigsaw blocks), hermit, smith, and the detailed sites
  (Knossos, Skara Brae, Çatalhöyük, Newgrange's interior, Mohenjo-daro, Stonehenge's trilithons can
  be either).
- Nothing purely hand-built: every template goes through the post-pass and linter.

**Tooling** (`tools/structures/`, like `tools/quests/`):

- `catalogue.json`: per structure the set, climate, landform groups, adaptation, pools and variants,
  processor list, loot table, NPCs; per site the coordinates, offset, waypoint text.
- `build.py`: writes every file in §2.1, then lints: every block id and item id exists in the newest
  dump; only `tfc:`, `easy_npc:`, air, structure void and jigsaw blocks in templates; no rough alloy rock
  in templates that fix their rock; loot against the deny-list and the step caps; no food in fixed
  containers; no `UUID`/`Owner`/`Navigation.Home` left in entity NBT; template sizes ≤ 96 in x/z
  (structure references reach 8 chunks).
- `shapes.py` (procedural generators with a seed per variant), `nbtwrite.py` (writer), `import.py`
  (copies a saved structure-block or schematic file in, normalising it).
- Authoring loop: build, save, `import.py`, `build.py`, restart a creative test world, preview with
  `/place structure pack:<id> ~ ~ ~` (applies processors, ignores spacing and biome), iterate.
  `/place template` shows the raw placeholders.

---

## 4. Easy NPC

**What to install.** Easy NPC 7.14.0 for NeoForge 1.21.1 (MIT): `easy_npc-neoforge-1.21.1-7.14.0.jar`
(core, 3.0 MB, client and server required) and `easy_npc_config_ui-neoforge-1.21.1-7.14.0.jar` (1.2 MB,
the editor screens). The "Easy NPC (Bundle)" project is a 25 KB jar that only pulls those two in.
Dialogue and trading screens are in core (`client/screen/dialog/DialogScreen`, vanilla merchant screen);
config-ui is for editing. Ship both so operators can fix NPCs on servers; players can't edit an NPC
they don't own. Both are new-chunks-only content (blocks and entities in templates), accepted with the
structures.

**Do its entities survive in structure NBT? Yes, verified.**

- Vanilla jigsaw pieces place template entities: `SinglePoolElement.getSettings` sets
  `setIgnoreEntities(false)` and `setFinalizeEntities(true)` (bytecode), `placeEntities` removes the
  stored `UUID` and calls `Mob.finalizeSpawn(..., MobSpawnType.STRUCTURE, ...)`.
- Easy NPC keeps its whole configuration (dialogue, trades, skin, actions) in the entity NBT
  (`addEasyNPCBaseAdditionalSaveData`), so a fresh UUID loses nothing. Its `finalizeEasyNPCSpawn` only
  registers default data when the `FINALIZED` status flag is unset, so a configured NPC stays
  configured, and it sets the home position only if missing.
- Two leftovers from the authoring world must go (done by `npc_fixup` and checked by the linter):
  `Owner` (the author's UUID; whoever owns it can edit it) and `Navigation.Home` (absolute coordinates of
  the build site, which the NPC would try to walk back to). NPCs are persistent
  (`setPersistenceRequired`).

**Spawner blocks** (`EasyNPCSpawnerBlockEntity`, types `default`, `single`, `group`, `world`, `boss`):
the spawner keeps the full preset in `StoredPresetData` and spawns when a player is within range.
`single` (respawn one specific NPC if it is gone) keys on one entity UUID; copied verbatim into a
template, every trading post in the world would share that UUID, so only one of them could ever have
its trader alive. Stripping the UUID doesn't work either: on load the spawner re-reads
`StoredPresetData`, gets no UUID and never spawns (`canSpawnBasedOnConditions` returns false for a
missing UUID). Hence `npc_fixup` writes a UUID derived from the position and seed. `group` and `world`
count every NPC with the same preset across the dimension or world, so they cap the whole world, not
one post.

**Which to use.** Trading post and travelling smith: a `single` spawner hidden under a floor block,
with the per-placement UUID, so the trader comes back if killed. Hermit: a plain entity in the template,
one-off.

**Presets and trades.** Author each NPC in game with the config UI (skin, dialogue, trades), export it
(`.npc.snbt`), and keep it in `tools/structures/npcs/<id>.npc.snbt`; `build.py` injects its `data`
compound into the template (entity or spawner), so the template and the preset never drift. Exported
presets also go to `kubejs/data/pack/easy_npc/preset/humanoid/` so operators can spawn one by hand
(Easy NPC accepts `preset/`, `<ns>/easy_npc/preset/` and `default_preset/` resource paths; check which
one the UI lists). Trades are vanilla merchant offers (`Offers.Recipes[{buy, buyB, sell, maxUses, ...}]`)
with Easy NPC's `TradingData` (`Type: ADVANCED`, `ResetsEveryMin` to restock). Use the export's own item
format (1.21 components); the bundled sample presets still use the pre-1.20.5 `Count`/`tag` format.
Never put food in trades: a stored food stack carries the authoring world's creation date. No
`COMMAND` actions in dialogue (they run commands).

Barter, no currency (TFC has none); prices in goods the player has at that era. Starting lists (all ids
checked):

| NPC | Sells | For |
|---|---|---|
| Trader | `tfc:seeds/barley`, `oat`, `rye`, `beet`, `onion`, `jute` ×4 | 6 `tfc:straw` or 1 `tfc:medium_raw_hide` |
| | `tfc:ceramic/large_vessel` | 2 `tfc:metal/ingot/copper` |
| | `tfc:powder/salt` ×4 | 1 `tfc:metal/ingot/copper` |
| | `tfc:rope` ×2, `tfc:burlap_cloth` ×2 | 8 `tfc:jute_fiber` |
| | `tfc:jar/cherry`, `tfc:jar/plum` | 1 `tfc:metal/ingot/copper` |
| | `tfc:plant/red_apple_sapling`, `cherry_sapling`, `olive_sapling` (1 per restock) | 4 `tfc:metal/ingot/copper` |
| Hermit | `tfc:plant/plum_sapling`, `peach_sapling`, `lemon_sapling`, `orange_sapling` (1 per restock) | 3 `tfc:metal/ingot/copper` + 1 `tfc:ceramic/jug` |
| | `tfc:flower_cutting` ×2 | 1 `tfc:ceramic/bowl` |
| | lore and tips (dialogue only) | |
| Smith | `tfc:metal/ingot/copper` | 12 `tfc:ore/normal_malachite` (worse than smelting; it saves the vessel step) |
| | `tfc:metal/knife/copper`, `chisel/copper`, `propick/copper`, `saw/copper` | 2-3 `tfc:metal/ingot/copper` |
| | `tfc:ceramic/ingot_mold`, `saw_blade_mold`, `propick_head_mold` | 4 `minecraft:charcoal` |
| | `tfc:powder/flux` ×4 | 1 `tfc:metal/ingot/copper` |
| | `tfc:metal/pickaxe/bronze` | 2 `tfc:metal/ingot/tin` + 1 `tfc:metal/ingot/copper` (tin makes it a bronze-age trade) |

**Dialogue tone.** Short, plain, in the world, never about "players" or game terms; each NPC gives one
or two useful hints in character. Examples:

- Trader: "Salt, cloth, seed. Bring hides or worked copper and we'll talk. The river carries everyone
  past here sooner or later."
- Hermit: "Green stain on a cliff means copper under it. Red earth, sometimes tin nearby. I stopped
  digging. You won't."
- Smith: "Clay first, then fire, then metal. A mould that cracks in the fire was wet; dry it a day.
  Bring me tin and I'll show you what copper wants to be."

---

## 5. Real-world ancient sites

At 20 m per block real monuments are tiny (Stonehenge's 33 m circle is under 2 blocks; the 1.2 km
Ménec rows at Carnac are 58 blocks), so sites are built at game scale (30-90 blocks across): evocative,
not surveyed. Each is one structure set with a `pack_world:geographic` placement and a Real World
waypoint. Materials are fixed where the site is known for a stone (`local_materials` with a fixed rock),
local otherwise. Block positions below are for the pack's 20 m world (`tools/worldview/geo.py` with
the map's edges -170..190 longitude), to be confirmed by the site test; coastal ones may need an
`offset` because Real World's coastline is ~3.5 km per pixel at this scale.

| Site | Lat, lon | Block x, z (chunk) | Era (TFC fit) | Contents | Materials and notes |
|---|---|---|---|---|---|
| **Stonehenge** | 51.1789, -1.8262 | -46,275, -305,812 (-2893, -19114) | late Neolithic to early Bronze Age (stone → bronze) | sarsen ring with lintels and the trilithon horseshoe (~40 blocks), a ditch and bank, the Avenue, 2-3 round barrows with grave goods (copper knife, jug, a rare bronze knife) | fixed `tfc:raw_sandstone`/`smooth_sandstone` for sarsens, local chalk elsewhere |
| **Newgrange** | 53.6947, -6.4753 | -63,087, -318,056 (-3943, -19879) | Neolithic passage tomb (stone) | round mound ~40 blocks, quartz facade (smooth quartzite), carved kerbstones (chiseled), long passage to a cross-shaped chamber with stone basins, a roof-box opening facing the midwinter sunrise (south-east) | fixed quartzite facade, local rock passage |
| **Skara Brae** | 59.0486, -3.3419 | -48,600, -342,565 (-3038, -21411) | Neolithic village (stone) | 6-8 sunken stone houses joined by covered passages, stone dressers and box beds, hearths, all buried in a midden mound | local flagstone; coastal, likely needs `offset` |
| **Ötzi's pass** (Tisenjoch) | 46.7790, 10.8402 | 3,404, -283,411 (212, -17714) | Copper Age (c. 3230 BC) | a rock gully below the ridge, a cairn, a frozen camp: copper axe (`tfc:metal/axe/copper`) and stone knife in a chest, birch-bark containers (jugs), arrows, embers | local rock; may land on glaciated biome, then needs `offset` |
| **Knossos** | 35.2981, 25.1631 | 66,166, -220,039 (4135, -13753) | Bronze Age Minoan palace | central court, colonnades (stripped logs painted with red wattle), storerooms of large vessels (`tfc:ceramic/large_vessel/*` blocks, empty), a throne room, a stair; chests with bronze and tin ingots, bronze tools, sealed olive jars | local limestone; a keeper NPC is possible (open question 6) |
| **Göbekli Tepe** | 37.2231, 38.9225 | 124,854, -231,093 (7803, -14444) | Pre-Pottery Neolithic (stone, no pottery) | 3-4 round enclosures of T-shaped pillars with carved reliefs, half buried (`bury`) | local limestone; loot only stone tools, flint, bone |
| **Çatalhöyük** | 37.6667, 32.8281 | 98,292, -233,618 (6143, -14602) | Neolithic town (stone → first copper) | honeycomb of mud-brick houses without streets, entered by roof hatches and ladders, painted walls (stained wattle), horned bull benches (bone), obsidian blades (`tfc:obsidian_knife`), native copper beads | local soil's mud bricks; ladders are vanilla (`minecraft:ladder`, accept or use supports) |
| **Mohenjo-daro** | 27.3292, 68.1389 | 263,514, -172,809 (16469, -10801) | Bronze Age Indus city | grid of brick houses with wells and covered drains, the Great Bath (stepped pool), a granary; copper and bronze tools, barley and wheat seeds, pottery | mud bricks (fired brick would be `minecraft:bricks`, a vanilla block) |
| **Old Copper pits, Keweenaw** | 47.2466, -88.4540 | -397,523, -285,847 (-24846, -17866) | Archaic native copper mining (c. 4000-1000 BC; copper) | shallow pits with stone hammers, native copper left in the rock (`tfc:ore/rich_native_copper/<rock>`), a camp; copper awls and knives | local rock; the only site in North America |
| **Caral** | -10.8931, -77.5203 | -415,608, 70,074 (-25976, 4379) | Norte Chico, pre-ceramic (stone) | stepped platform mounds around a sunken circular plaza; rope and jute (knotted records), squash and bean seeds, no pottery | local rock; the only site in South America |

Alternates: Nabta Playa (22.5086, 30.7256: a Neolithic stone circle in the Sahara, x 95,642 z -143,279),
Sannai-Maruyama (40.8114, 140.6964: Jōmon pit houses and the six-post chestnut tower, x 552,015
z -251,266), Carnac (47.5929, -3.0814: menhir rows, procedural), Great Orme mines (53.3333, -3.8556:
Bronze Age malachite galleries, a headland so likely water at map scale; Timna in the Negev is an
inland copper alternative).

**Waypoints.** Real World reads `config/tfc_real_world/geography/<namespace>/
{continents,regions,subregions,waypoints}/*.json` (`FMLPaths.CONFIGDIR`, so client and server both get
them from the pack's `config/`) besides its own `default` namespace (verified:
`GeographyManager.discoverFromExternal`), and injects a "visit" advancement per waypoint. Parents are
plain refs, so ours can hang under its subregions:

```json
// config/tfc_real_world/geography/pack/waypoints/stonehenge.json
{"parent": "default:subregion/great_britain",
 "title_lang": {"en_us": "Stonehenge"},
 "subtitle_lang": {"en_us": "Ancient site"},
 "description_lang": {"en_us": "Visit the great stones on the chalk plain"},
 "latitude": 51.1789, "longitude": -1.8262}
```

Parents for the shortlist: great_britain (Stonehenge, Skara Brae), ireland, italy (Tisenjoch is on the
Austrian-Italian border; austria also exists), crete, turkey (Göbekli Tepe, Çatalhöyük), pakistan,
michigan, peru. `build.py` writes waypoint and structure set from the same catalogue entry; with an
`offset`, the waypoint keeps the real coordinates (a few hundred blocks off is fine for a marker).
*Unverified*: that titles fall back to `en_us` in other languages.

---

## 6. worldgen_check changes

Today the tiers would see structures this way: tier 1 flags each new structure as "can start in N TFC
biomes" (new-chunks-only, acceptable); `structure_set`, `template_pool` and `processor_list` changes are
"info"; tier 0 doesn't hash templates (its `DATA_RE` covers `worldgen/` and `tags/worldgen/` but not
`structure/*.nbt`); tier 3 flags structure starts, Easy NPC blocks and entities as new (acceptable), but
also sees the underground census move wherever a structure or its terrain adaptation reaches below the
census line (beards, the adit, buried cists). The census is classed continuity-breaking, and `--accept`
refuses while any continuity finding remains. Changes:

1. **Per-chunk census and structure coverage in tier 3.** In `golden_fingerprint`, record for each chunk
   the structure ids in `structures.References` and `structures.starts` (references come from each
   start's bounding box, which vanilla inflates by 12 blocks when the structure has a terrain
   adaptation, so they cover the beard), and the census grouped per chunk (`census_groups`, only
   non-zero groups; ~650 chunks × ~12 groups, ~100 KB in the baseline, or a sidecar
   `tools/worldgen_golden_census.json`). In `diff_golden`, compare the census summed over chunks covered
   by no structure in either run; report "N chunks under structures X, Y left out of the census".
   Biomes and `tfc:chunk_data` stay compared in every chunk: structures can't change them (TFC computes
   surface heights before the beard), so a difference there is still continuity-breaking. An old
   baseline without per-chunk data falls back to today's comparison and asks for `--update --golden`.
2. **A signature per accepted structure (tier 1).** In `worldgen_check.js`, for each structure that can
   start in a TFC biome, hash its JSON, its structure set's placement, the template pools it can reach,
   their processor lists and template files (read through the server's resource manager). Store them as
   `tier1.structures.sigs`. A changed signature of an accepted structure becomes a new-chunks-only
   finding ("structure pack:barrow changed: templates"), because chunks generated after the change would
   join old halves to new ones; re-accept on purpose.
3. **Geographic sites (tier 1).** Ask `PackWorldApi.sites()` for each site's chunk and record
   `{site: [cx, cz, lat, lon]}`; a moved site is new-chunks-only ("existing worlds may get a second copy
   or half a site"). A Real World change that moves sites also moves terrain and is refused anyway.
4. **Tier 0.** Add `structure/.+\.nbt` to `jarscan.DATA_RE` (jars and `kubejs/data`); add the pack's own
   mod to a `STRUCTURE_CODE_MODS = {"pack_world"}` set whose class hashes are compared: a code change
   is new-chunks-only (needs `--accept`), a version bump with identical classes is info.
5. **How accepted structures are recorded.** `--accept` keeps its human-readable `what` lines and adds
   machine-readable fields, plus a top-level `structures` map that later runs compare against:

   ```json
   "accepted": [{"date": "2026-10-20", "reason": "lived-in structures, phase 3", "terrain": false,
     "findings": [{"what": "structure pack:cairn can start in 31 TFC biomes", "mod": "pack_world (kubejs/data/pack)",
                   "tier": 1, "kind": "structure", "id": "pack:cairn", "sig": "3f9a1c02"}]}],
   "structures": {"pack:cairn": {"sig": "3f9a1c02", "set": "pack:cairn", "since": "2026-10-20"},
                  "pack:site/stonehenge": {"sig": "...", "site": [-2893, -19114], "since": "2026-10-20"}}
   ```

   Golden-area starts, `easy_npc` blocks and entities are recorded as today (they join the known sets).
6. *Optional*: a ninth golden area around one site (Stonehenge, 81 chunks, ~20 s) to see a fixed site
   generate in every `--golden` run.

Also note in `tools/README.md` that single-player worlds created with "Generate Structures" off get no
structures and no sites (vanilla's switch also gates TFC's structure step).

---

## 7. Phased plan

Estimates are agent working time plus the author's building time where noted; one test server, so
test runs are serial.

| Phase | Work | Effort |
|---|---|---|
| 0. Decisions | Answer §8; approve Easy NPC; decide build path (MDG downloads or `build.py`) | author, ~1 h |
| 1. Mod core + one structure | `build.py`, `local_materials` (rock, wood, soil, alloy rule, property copy), `PackWorldApi`; the cairn end to end (procedural template, set, tag, loot); `structures_test.py` palette and placement checks; the float test on five places; decide skirt vs `foundation` | 3 days |
| 2. worldgen_check | changes 1-5 of §6, a golden run with the cairn, `--accept` | 2 days |
| 3. Generator and procedural structures | `tools/structures/` (writer, shapes, catalogue, build, linter incl. loot caps); hunters' camp, standing stones, wayside shrine, barrow | 3 days |
| 4. Hand-built ruins | homesteads ×3, prospector's camp, adit, bloomery smithy, wreck: author builds (1-3 h each), agent imports, adds variants, loot, tests | author ~2 days, agent 3 days |
| 5. Easy NPC and inhabited spots | add Easy NPC, `npc_fixup`, author three NPCs in game, trading post (multi-piece), hermit, smith; NPC checks; optional climate loot condition | author ~1 day, agent 3 days |
| 6. Ancient sites | `geographic` placement, `SiteGuard` and command, waypoints, site test; build 10 sites (most hand-built, ~2-4 h each) | author ~3-4 days, agent 3 days |
| 7. Tuning and release | density estimate and pregen walks (`pregen.py --place`, `worldview`), spacing tuning, final golden run and `--accept`, design.md and README updates | 2 days |

Minimum useful slice: phases 1-3 (about 8 days) give the mod, the checks and five procedural ruins.
Everything must land before the first long-lived world (design.md, "Overworld").

---

## 8. Open questions for the author

*Answered 2026-10-07: ModDevGradle, Easy NPC yes, procedural templates first with hand-built ones
later, and the defaults for the rest (names `pack_world`/`pack`, this density, the ten sites with
waypoints, barter, these era caps, the strict alloy rule, tin rare, local rock at sites).*

1. **Names**: mod id `pack_world` and data namespace `pack`, or something else?
2. **Build**: approve the ModDevGradle downloads (§1.3, ~300-400 MB plus Gradle), or start with the
   zero-download `build.py`?
3. **Easy NPC**: add core and config UI (both sides)? Or no NPCs, and "inhabited" spots become recently
   abandoned?
4. **Alloy rock in local ruins**: in basalt or andesite country the ground already is alloy rock. Keep the
   strict rule (default `"work"`: smooth and bricks instead of raw and cobble), or allow local rough
   rock where it is the surface rock anyway?
5. **Density**: about one ruin per ~300 blocks and one inhabited spot per ~1,500-2,000 blocks, right?
   More or fewer inhabited spots?
6. **Sites**: which ten; how generous their loot; should some have a keeper NPC (Knossos, Stonehenge)?
7. **Waypoints** for the sites in Real World's geography screen (with visit advancements): yes?
8. **NPC death**: traders respawn (spawner), hermit doesn't; or all one-off?
9. **Prices**: barter as in §4, or a pack currency (e.g. copper ingots everywhere)?
10. **Era caps for loot**: stone ≤ 6, copper ≤ 8, bronze ≤ 13 checker steps; bronze items in random
    ruins at all?
11. **Building time**: is about a week of creative building (homesteads, trading post, sites) available,
    or should more be procedural?
12. **Existing worlds**: the `SiteGuard` rule (sites only in worlds created with them, operators can
    enable later) acceptable?
13. **Tin in wrecks and the smith's bronze trades**: tin is the bronze gate for tin-poor starts. Keep it
    rare there, or leave tin out of loot entirely?
14. **Fixed materials at sites**: sandstone for Stonehenge's sarsens and quartzite at Newgrange, or
    local rock everywhere?

---

## Appendix: verified facts this design relies on

- TFC 4.2.11: `TFCChunkGenerator.fillFromNoise` builds `ChunkNoiseFiller` with
  `Beardifier.forStructuresInChunk`; the filler adds the beard to a density clamped to [-1, 1] with a
  0.2/block slide above the surface height; `chunkData.generateFull(filler.surfaceHeight(), ...)` runs
  before the noise fill (source, 1.21.x branch).
- TFC 4.2.11 `ClimateStructurePlacement.isPlacementChunk` builds `new BlockPos(minX, 0, minZ)` and calls
  `createAndGenerate(chunkPos)` then `isValidNonHemispheral` (bytecode). `ClimatePlacement`'s fuzzy
  check divides by `max - min` of defaults ±∞ (source).
- `ForestFeature.getTrees` filters `isValid(temp, groundwater, rainVar, y)` and sorts by
  `distanceFromMean`; rain variance is negated in the southern hemisphere via `SolarCalculator`.
- `RockData.getSurfaceRock(x, z)` = `generator.generateSurfaceRock(x, z)`.
- TFC tags: `#tfc:can_landslide` holds every cobble and mossy cobble; `#tfc:can_collapse` holds
  `#c:stones`, `#c:stones/smooth`, `#c:stones/spike`, ores.
- No TFC climate loot condition; `tfc:rotten` exists.
- Real World 4.2.0: external geography from `FMLPaths.CONFIGDIR/tfc_real_world/geography/<ns>/`;
  `WaypointCoordinates.toBlockXZ(lat, lon)` = `geographicToClassic(fitLongitude(lon), lat)`, clamped and
  rounded; one advancement per waypoint.
- Vanilla 1.21.1 (NeoForge 21.1.255): jigsaw single pool elements place entities and finalize them;
  `StructureTemplate.processBlockInfos` calls every processor's `finalizeProcessing`; NeoForge's
  `processEntity` hook exists.
- Easy NPC 1.21.1 branch: spawner semantics, `Navigation.Home`, `Owner`, `FINALIZED` flag, preset paths
  and formats as described in §4; core 3.0 MB, config UI 1.2 MB, bundle 25 KB (Modrinth API).
- KubeJS 2101.7.2 injects its data pack through `WorldLoaderPackConfigMixin` and `WorldLoaderMixin`.
- packwiz: local jars in `mods/` are indexed by `packwiz refresh` (packwiz docs).
- MDK 1.21.1: MDG 2.0.148, Gradle 9.2.1, NeoForge 21.1.256 (NeoForgeMDKs repo).
- Item and block ids: 184 loot ids and ~80 template block ids checked against
  `tools/.data/dumps/20261007-102324-diorite` (only `tfc:sheet_pile` and `tfc:plant/hay` don't exist and
  aren't used).
