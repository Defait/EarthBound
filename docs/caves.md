# Caves

The pack's caves replace TFC's (`docs/design.md`, *Caves*). Everything is data under `kubejs/data/`, and JSON can't hold
comments, so the notes are here (KubeJS refuses a `README.md` in its data folder: no upper case in file names). Cave shape
(density functions, noise, carvers and the block tags they carve) is **continuity-breaking**: changing it seams against
explored terrain, so it is frozen with the rest of the overworld (`tools/worldgen_check.py`). Decoration (placed features)
only affects chunks generated afterwards.

## Shape

TFC carves with two systems, both overridden here:

- **Noise caves**: TFC's `tfc:noise_caves` density function (`kubejs/data/tfc/worldgen/density_function/noise_caves.json`) now
  takes the pack's caves, `pack:caves/styles` (`kubejs/data/pack/worldgen/density_function/caves/`), and keeps TFC's own fade (full strength below y 20, solid towards y 320).
  TFC's spaghetti tunnels are gone and `tfc:noodle_caves` is a constant -1 (noodles off).
  - `styles`: a 2D noise (`style`, ~2 km regions) picks one of three cave styles per region, about a third each:
    - `chambers`: TFC's cheese chambers at twice the size and fewer of them, plus rare great caverns;
    - `caverns`: fewer chambers, many great caverns (up to a couple of hundred blocks across, y -60 to 20);
    - `shafts`: few chambers, tall pits and shafts.
  - `entrances`: TFC's entrance noise, rarer.
  - The noises (`kubejs/data/pack/worldgen/noise/caves/`) copy vanilla's cave noises' octaves under the pack's own keys (own seeds), at
    the scales used here; nothing in `minecraft:` is overridden.
- **Carvers**: TFC's three (`kubejs/data/tfc/worldgen/configured_carver/`) are fewer and bigger: `cave` 0.02 -> 0.005 (radius
  x2.5-4), `deep_cave` 0.08 -> 0.015 (x3.5-6), `canyon` 0.01 -> 0.02, deeper (y -20 to 60) and wider (chasms).
  One more, `karst_cave` (0.025, x3-5), is added to every TFC biome by `kubejs/data/pack/neoforge/biome_modifier/cave_carvers.json`
  (the biome tag `kubejs/data/pack/tags/worldgen/biome/overworld.json` lists all 125 TFC biomes; re-list them if TFC adds biomes). It only cuts
  limestone, dolomite, chalk and marble (`kubejs/data/pack/tags/block/karst_cave_rock.json`), so karst country is more cavernous than
  other rock. (Basalt lava tubes the same way were tried and dropped: too few and too small to notice.)

## Decoration

Added to TFC's `#tfc:in_biome/underground_decoration` (`kubejs/data/tfc/tags/worldgen/placed_feature/in_biome/`); the
features are in `kubejs/data/pack/worldgen/{configured,placed}_feature/caves/`:

- `mossy_floor`, `mossy_ceiling`: in about half the caves of warm (10 C and up), wet (250 mm and up) areas, a patch of
  cave floor or ceiling turns to TFC's mossy cobble of the same rock (`mossy_rock`, only blocks with a face open to the
  cave), then moss carpets go on a mossy floor and glow-berry cave vines hang from a mossy ceiling (`moss_carpets`,
  `cave_vines`; TFC's `tfc:if_then` runs them only where the patch placed). Glow berries are a TFC food
  (`kubejs/data/pack/tfc/food/glow_berries.json`): a decaying fruit. Vanilla moss blocks were tried first and dropped:
  how much moss lands on a chunk border depends on the order neighbouring chunks are decorated, and moss replacing rock
  moved `worldgen_check.py --golden`'s rock census past its limit between two runs of the same seed. Mossy cobble keeps
  each rock's kind, so the census doesn't move.
- `glow_lichen`: on rock walls and ceilings below y 0.
- `karst_calcite`: calcite stalactites (TFC's `tfc:calcite` block) under karst-rock ceilings. Placed as a block column:
  TFC's own thin-spike calcite and icicle features placed nothing in any test world. Cave walls and ceilings are mostly
  TFC's hardened rock, so rock checks list raw and hardened.
- `ice_cave`: TFC's own ice cave feature (ice floors, ice balls, icicles), unused by TFC itself, where the average
  temperature at that depth is -4 C or below.
- TFC's rock spikes, large spikes and columns are denser (`kubejs/data/tfc/worldgen/placed_feature/`).

`tfc:climate` placement with `fuzzy: true` needs both a min and a max for each value it checks: an open bound makes the
fuzzy test fail silently and nothing places.

## Measuring

`worldgen_check.py` records this as one terrain entry in `tools/worldgen_baseline.json` (2026-10-07). Before and after
numbers (1 km squares at Rome, Tokyo, Yakutsk and Lhasa, same seed) are in `docs/design.md`, *Caves*. Decoration per
chunk after the change: mossy cobble on 40-80 cave faces in warm, wet areas (Rome, Tokyo), 2-5 moss carpets and 1-4
cave vines there, glow lichen 17-20 everywhere, calcite about 5 in karst (Tokyo), packed and blue ice about 7 where it
is -4 C or colder (Yakutsk).
