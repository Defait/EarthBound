package pack.world.api;

import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockState;
import pack.world.geo.GeographicPlacement;
import pack.world.geo.SiteGuard;
import pack.world.materials.AlloyPolicy;
import pack.world.materials.BlockFamilies;
import pack.world.materials.LocalMaterialsProcessor;
import pack.world.materials.Materials;

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
        final BlockFamilies.Parsed parsed = BlockFamilies.parse(id);
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
