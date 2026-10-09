package pack.world.api;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import net.dries007.tfc.util.EnvironmentHelpers;
import net.dries007.tfc.world.ChunkGeneratorExtension;
import net.dries007.tfc.world.chunkdata.ChunkData;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.ChunkGenerator;
import net.minecraft.world.level.levelgen.structure.BoundingBox;
import net.minecraft.world.level.levelgen.structure.Structure;
import net.minecraft.world.level.levelgen.structure.StructureSet;
import net.minecraft.world.level.levelgen.structure.StructureStart;
import pack.world.geo.GeographicPlacement;
import pack.world.geo.RegionGeometry;
import pack.world.geo.RegionPlacement;
import pack.world.geo.SiteGuard;
import pack.world.keepclear.KeepClear;
import pack.world.structure.GuardedJigsawStructure;
import pack.world.materials.AlloyPolicy;
import pack.world.materials.BlockFamilies;
import pack.world.materials.LocalMaterialsProcessor;
import pack.world.materials.Materials;
import pack.world.skin.StructureSkin;

/**
 * Static helpers for the pack's dev-only KubeJS scripts (tools/structures_test.js, tools/worldgen_check.js). Plain types in and
 * out so Rhino can call them.
 */
public final class PackWorldApi
{
    private PackWorldApi() {}

    /** The materials local_materials resolves at a position with default settings: {rock, wood, sand, tfc}. */
    public static Map<String, String> materialsAt(ServerLevel level, int x, int y, int z)
    {
        final Materials m = Materials.resolve(level, new BlockPos(x, y, z), new Materials.Choice("local", "local", "local", 2, AlloyPolicy.WORK, "granite"));
        final Map<String, String> out = new LinkedHashMap<>();
        out.put("rock", m.rock());
        out.put("wood", m.wood());
        out.put("sand", m.sand());
        out.put("tfc", String.valueOf(m.fromTfc()));
        return out;
    }

    /**
     * What local_materials turns a placeholder block id into for the given materials (default placeholders: granite, oak,
     * alfisol, yellow): the target block id, or the input id when it isn't a placeholder. "minecraft:air" means removed.
     * The same code path as world generation, minus decay.
     */
    public static String mapId(String blockId, String rock, String wood, String soil, String sand, String alloyPolicy)
    {
        final ResourceLocation id = ResourceLocation.parse(blockId);
        final Optional<Block> block = BuiltInRegistries.BLOCK.getOptional(id);
        final BlockFamilies.Parsed parsed = BlockFamilies.parseLocal(id);
        if (block.isEmpty() || parsed == null)
        {
            return blockId;
        }
        final LocalMaterialsProcessor.Placeholders p = LocalMaterialsProcessor.Placeholders.DEFAULT;
        final String placeholder = switch (parsed.kind())
        {
            case ROCK, ORE -> p.rock();
            case WOOD -> p.wood();
            case SOIL -> p.soil();
            case SAND -> p.sand();
        };
        if (!parsed.material().equals(placeholder))
        {
            return blockId;
        }
        final AlloyPolicy policy = AlloyPolicy.valueOf(alloyPolicy.toUpperCase(java.util.Locale.ROOT));
        final String effectiveRock = policy == AlloyPolicy.SUBSTITUTE && BlockFamilies.ALLOY_ROCKS.contains(rock) ? "granite" : rock;
        final Materials m = new Materials(effectiveRock, wood, sand, true);
        final BlockState state = LocalMaterialsProcessor.map(block.get().defaultBlockState(), id, parsed, m, soil, null, policy, "granite", new HashMap<>());
        return BuiltInRegistries.BLOCK.getKey(state.getBlock()).toString();
    }

    /**
     * As {@link #mapId} for a structure with wood ranks (placeholders oak, spruce and birch, in that order): {@code woods} are the resolved
     * ranks, best first ("oak" for TFC's, "afc:mahogany" for ArborFirmaCraft's); a rank past the end uses the last, as in play.
     */
    public static String mapIdRanked(String blockId, String rock, List<String> woods, String soil, String sand, String alloyPolicy)
    {
        final ResourceLocation id = ResourceLocation.parse(blockId);
        final Optional<Block> block = BuiltInRegistries.BLOCK.getOptional(id);
        final BlockFamilies.Parsed parsed = BlockFamilies.parseLocal(id);
        if (block.isEmpty() || parsed == null)
        {
            return blockId;
        }
        final List<String> ranks = List.of("oak", "spruce", "birch");
        final LocalMaterialsProcessor.Placeholders p = LocalMaterialsProcessor.Placeholders.DEFAULT;
        String wood = woods.get(0);
        final boolean placeholder;
        switch (parsed.kind())
        {
            case WOOD ->
            {
                placeholder = ranks.contains(parsed.material());
                wood = woods.get(Math.min(Math.max(ranks.indexOf(parsed.material()), 0), woods.size() - 1));
            }
            case ROCK, ORE -> placeholder = parsed.material().equals(p.rock());
            case SOIL -> placeholder = parsed.material().equals(p.soil());
            default -> placeholder = parsed.material().equals(p.sand());
        }
        if (!placeholder)
        {
            return blockId;
        }
        final AlloyPolicy policy = AlloyPolicy.valueOf(alloyPolicy.toUpperCase(java.util.Locale.ROOT));
        final String effectiveRock = policy == AlloyPolicy.SUBSTITUTE && BlockFamilies.ALLOY_ROCKS.contains(rock) ? "granite" : rock;
        final BlockState state = LocalMaterialsProcessor.map(block.get().defaultBlockState(), id, parsed, new Materials(effectiveRock, wood, sand, true), soil, null,
            policy, "granite", new HashMap<>());
        return BuiltInRegistries.BLOCK.getKey(state.getBlock()).toString();
    }

    /** The woods a structure with ranks would use at a position, best first: "oak" for TFC's, "afc:mahogany" for ArborFirmaCraft's. */
    public static List<String> woodsAt(ServerLevel level, int x, int y, int z, int count, boolean modded)
    {
        return Materials.resolveRanked(level, new BlockPos(x, y, z), count, modded).woods();
    }

    /** Block x and z of a latitude and longitude, as TFC: Real World places its own waypoints; empty without that mod. */
    public static int[] blockOf(double latitude, double longitude)
    {
        return RegionPlacement.blockOf(latitude, longitude);
    }

    /** Every region placement of the level's structure sets: {set id: {spacing, separation, regions: {name: [vertices, area in chunks squared, minX, minZ, maxX, maxZ]}, exclude: {...}}}. */
    public static Map<String, Map<String, Object>> regionSets(ServerLevel level)
    {
        final Map<String, Map<String, Object>> out = new LinkedHashMap<>();
        level.registryAccess().registryOrThrow(Registries.STRUCTURE_SET).entrySet().forEach(e ->
        {
            if (e.getValue().placement() instanceof RegionPlacement placement)
            {
                final Map<String, Object> row = new LinkedHashMap<>();
                row.put("spacing", placement.spacing());
                row.put("separation", placement.separation());
                row.put("regions", shapes(placement.shapes(false)));
                row.put("exclude", shapes(placement.shapes(true)));
                row.put("declared", placement.zones().regions().size());
                out.put(e.getKey().location().toString(), row);
            }
        });
        return out;
    }

    private static Map<String, List<Double>> shapes(List<RegionGeometry.Shape> shapes)
    {
        final Map<String, List<Double>> out = new LinkedHashMap<>();
        shapes.forEach(s ->
        {
            final double[] b = s.bounds();
            out.put(s.name(), List.of((double) s.vertices(), s.area() / 256.0, b[0], b[1], b[2], b[3]));
        });
        return out;
    }

    /** The regions of a set containing a latitude and longitude (excluded ones as "!name"). */
    public static List<String> regionsAt(ServerLevel level, String setId, double latitude, double longitude)
    {
        final int[] xz = RegionPlacement.blockOf(latitude, longitude);
        final RegionPlacement placement = regionPlacement(level, setId);
        return placement == null || xz.length == 0 ? List.of() : placement.regionsAtBlock(xz[0], xz[1]);
    }

    /** The three steps of a region set's placement at a chunk: {grid, region, climate, structureChunk}. */
    public static Map<String, Boolean> placementAt(ServerLevel level, String setId, int chunkX, int chunkZ)
    {
        final Map<String, Boolean> out = new LinkedHashMap<>();
        final RegionPlacement placement = regionPlacement(level, setId);
        if (placement == null)
        {
            return out;
        }
        final var state = level.getChunkSource().getGeneratorState();
        out.put("grid", placement.gridCandidate(state, chunkX, chunkZ));
        out.put("region", placement.regionContains(chunkX, chunkZ));
        out.put("climate", placement.climateAllows(state, chunkX, chunkZ));
        out.put("structureChunk", placement.isStructureChunk(state, chunkX, chunkZ));
        return out;
    }

    private static RegionPlacement regionPlacement(ServerLevel level, String setId)
    {
        final StructureSet set = level.registryAccess().registryOrThrow(Registries.STRUCTURE_SET).get(ResourceLocation.parse(setId));
        return set != null && set.placement() instanceof RegionPlacement p ? p : null;
    }

    /**
     * What the village guard sees for a start piece centred at a block: {pass, reason, min, max, wet, samples}, or empty if the structure
     * is not a guarded jigsaw. Builds the generation context the way StructureCheck.canCreateStructure does.
     */
    public static Map<String, Object> guardAt(ServerLevel level, String structureId, int x, int z)
    {
        final Map<String, Object> out = new LinkedHashMap<>();
        final Structure structure = level.registryAccess().registryOrThrow(Registries.STRUCTURE).get(ResourceLocation.parse(structureId));
        if (!(structure instanceof GuardedJigsawStructure guarded))
        {
            return out;
        }
        final ChunkGenerator generator = level.getChunkSource().getGenerator();
        final Structure.GenerationContext context = new Structure.GenerationContext(level.registryAccess(), generator, generator.getBiomeSource(),
            level.getChunkSource().randomState(), level.getServer().getStructureManager(), level.getSeed(), new ChunkPos(new BlockPos(x, 64, z)), level,
            structure.biomes()::contains);
        final GuardedJigsawStructure.Verdict verdict = guarded.inspect(context, new BlockPos(x, 64, z));
        out.put("pass", verdict.pass());
        out.put("reason", verdict.reason());
        out.put("min", verdict.min());
        out.put("max", verdict.max());
        out.put("wet", verdict.wet());
        out.put("samples", verdict.samples());
        return out;
    }

    /**
     * What a guard of the given radius and sample count sees around a block, without refusing anything (for tuning the guard's limits):
     * {min, max, wet, samples} of the column heights and the number of wet columns, using the first structure of the set's generation context.
     */
    public static Map<String, Object> guardProbe(ServerLevel level, int x, int z, int radius, int samples)
    {
        final Map<String, Object> out = new LinkedHashMap<>();
        final ChunkGenerator generator = level.getChunkSource().getGenerator();
        final Structure.GenerationContext context = new Structure.GenerationContext(level.registryAccess(), generator, generator.getBiomeSource(),
            level.getChunkSource().randomState(), level.getServer().getStructureManager(), level.getSeed(), new ChunkPos(new BlockPos(x, 64, z)), level,
            biome -> true);
        final GuardedJigsawStructure.Verdict verdict = new GuardedJigsawStructure.Guard(radius, samples, 384, 1.0).evaluate(context, new BlockPos(x, 64, z));
        out.put("min", verdict.min());
        out.put("max", verdict.max());
        out.put("wet", verdict.wet());
        out.put("samples", verdict.samples());
        return out;
    }

    /** The biome id at a block column (the noise biome the structure placement sees). */
    public static String biomeAt(ServerLevel level, int x, int z)
    {
        final ChunkGenerator generator = level.getChunkSource().getGenerator();
        return generator.getBiomeSource().getNoiseBiome(net.minecraft.core.QuartPos.fromBlock(x), net.minecraft.core.QuartPos.fromBlock(64),
            net.minecraft.core.QuartPos.fromBlock(z), level.getChunkSource().randomState().sampler()).unwrapKey().map(k -> k.location().toString()).orElse("?");
    }

    /** The guard's sample columns for a centre: [[dx, dz], ...]. */
    public static List<List<Integer>> guardOffsets(int radius, int samples)
    {
        final List<List<Integer>> out = new ArrayList<>();
        for (int[] o : new GuardedJigsawStructure.Guard(radius, samples, 8, 0.1).offsets())
        {
            out.add(List.of(o[0], o[1]));
        }
        return out;
    }

    /** The village guard's counters: attempts, refusedBiome, refusedWater, refusedSlope, passed, nanos (the guard's own time). */
    public static Map<String, Long> guardStats()
    {
        final long[] s = GuardedJigsawStructure.stats();
        final Map<String, Long> out = new LinkedHashMap<>();
        final String[] names = {"attempts", "refusedBiome", "refusedWater", "refusedSlope", "passed", "nanos"};
        for (int i = 0; i < names.length; i++)
        {
            out.put(names[i], s[i]);
        }
        return out;
    }

    public static void guardReset()
    {
        GuardedJigsawStructure.resetStats();
    }

    /** Switches the village guard on or off (what /pack_world guard does). */
    public static void setGuard(boolean on)
    {
        GuardedJigsawStructure.enabled = on;
    }

    /** The structure skin's counters (changed, rewritten, mapped, removed, alloy, foundation; chunks:<namespace>). */
    public static Map<String, Long> skinStats()
    {
        return StructureSkin.stats();
    }

    /** Blocks structures wrote that the skin has no rule for, with counts (vanilla ones are gaps in the table). */
    public static Map<String, Long> skinUnmapped()
    {
        return StructureSkin.unmapped();
    }

    /** Per structure id: blocks written, ground columns and floating ones (before/after the foundation), block census before/after. */
    public static Map<String, Map<String, Object>> skinMetrics()
    {
        return StructureSkin.metrics();
    }

    public static void skinCensus(boolean on)
    {
        StructureSkin.setCensus(on);
    }

    public static void skinReset()
    {
        StructureSkin.resetStats();
    }

    /** {rules, namespaces, unknown}: the loaded table's size, the structure namespaces it applies to, and unknown block ids. */
    public static Map<String, String> skinConfig()
    {
        final Map<String, String> out = new LinkedHashMap<>();
        out.put("rules", String.valueOf(StructureSkin.config().ruleCount()));
        out.put("namespaces", String.valueOf(new java.util.TreeSet<>(StructureSkin.config().namespaces())));
        out.put("unknown", String.valueOf(new java.util.TreeSet<>(StructureSkin.config().unknownBlocks())));
        return out;
    }

    /** The keep-clear counters: trees_blocked, logs_blocked, boulders_blocked, suppressed:&lt;structure id&gt;. */
    public static Map<String, Long> keepClearStats()
    {
        return KeepClear.stats();
    }

    public static void keepClearReset()
    {
        KeepClear.resetStats();
    }

    /** What the loaded keep-clear data says about a structure id: {@code trees=.. holds=.. yields=..}. */
    public static String keepClearDescribe(String structureId)
    {
        return KeepClear.describe(ResourceLocation.parse(structureId));
    }

    /** The loaded keep-clear data as text. */
    public static String keepClearConfig()
    {
        return KeepClear.config().toString();
    }

    /**
     * The anchor {@code pack_world:local_materials} uses for every piece of this structure: the centre of the start piece (its first piece)
     * at that piece's lowest y; the rock, sand and woods of a structure are those at this position.
     */
    public static int[] anchorOf(StructureStart start)
    {
        final BoundingBox box = start.getPieces().get(0).getBoundingBox();
        final BlockPos centre = box.getCenter();
        return new int[] {centre.getX(), box.minY(), centre.getZ()};
    }

    /**
     * TFC's climate at a chunk as a region-placed structure's climate test sees it (the chunk's minimum corner at y 0): {temperature,
     * rainfall, groundwater, forest} (forest density 0 to 4); all zero without a TFC generator.
     */
    public static Map<String, Double> climateAt(ServerLevel level, int chunkX, int chunkZ)
    {
        final Map<String, Double> out = new LinkedHashMap<>();
        final ChunkGenerator generator = level.getChunkSource().getGenerator();
        if (generator instanceof ChunkGeneratorExtension ext)
        {
            final ChunkPos chunk = new ChunkPos(chunkX, chunkZ);
            final BlockPos pos = new BlockPos(chunk.getMinBlockX(), 0, chunk.getMinBlockZ());
            final ChunkData data = ext.chunkDataGenerator().createAndGenerate(chunk);
            out.put("temperature", (double) EnvironmentHelpers.adjustAvgTempForElev(0, data.getAverageSeaLevelTemp(pos)));
            out.put("rainfall", (double) data.getAverageRainfall(pos));
            out.put("groundwater", (double) data.getAverageGroundwater(pos));
            out.put("forest", (double) data.getForestType().getDensity());
        }
        else
        {
            out.put("temperature", 0.0);
            out.put("rainfall", 0.0);
            out.put("groundwater", 0.0);
            out.put("forest", 0.0);
        }
        return out;
    }

    /** Every geographic site: {name: {chunkX, chunkZ, blockX, blockZ, enabled (0/1)}}; empty arrays without TFC: Real World. */
    public static Map<String, int[]> sites(ServerLevel level)
    {
        final Map<String, int[]> out = new LinkedHashMap<>();
        for (Map.Entry<String, GeographicPlacement> e : SiteGuard.sites(level).entrySet())
        {
            final ChunkPos chunk = e.getValue().siteChunk();
            final int[] xz = e.getValue().siteBlock();
            out.put(e.getKey(), chunk == null ? new int[0] : new int[] {chunk.x, chunk.z, xz[0], xz[1], SiteGuard.allowed(e.getKey()) ? 1 : 0});
        }
        return out;
    }
}
