package pack.world.materials;

import java.util.HashMap;
import java.util.Map;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.level.LevelReader;
import net.minecraft.world.level.levelgen.Heightmap;
import net.minecraft.world.level.levelgen.structure.BoundingBox;
import org.jetbrains.annotations.Nullable;

/**
 * The soil order of the ground under a column (TFC picks soils with noise inside a chunk, so this is per column). Only
 * columns inside the chunk being placed are read: reading outside the generating region can crash world generation.
 * Blocks outside it are placed by their own chunk's call, which samples them there.
 */
public final class SoilSampler
{
    private static final int DEPTH = 10;

    private final LevelReader level;
    @Nullable private final BoundingBox box;
    private final String fallback;
    private final Map<Long, String> columns = new HashMap<>();
    @Nullable private String chunkSoil;
    private boolean chunkScanned;

    public SoilSampler(LevelReader level, @Nullable BoundingBox box, String fallback)
    {
        this.level = level;
        this.box = box;
        this.fallback = fallback;
    }

    public String at(BlockPos pos)
    {
        if (box == null || !box.isInside(pos))
        {
            return fallback;
        }
        final String soil = columns.computeIfAbsent(BlockPos.asLong(pos.getX(), 0, pos.getZ()), k -> scan(pos.getX(), pos.getZ()));
        return soil != null ? soil : chunkSoil();
    }

    private String chunkSoil()
    {
        if (!chunkScanned && box != null)
        {
            chunkScanned = true;
            final int[][] probes = {{8, 8}, {2, 2}, {13, 2}, {2, 13}, {13, 13}};
            for (int[] p : probes)
            {
                final String soil = scan(box.minX() + p[0], box.minZ() + p[1]);
                if (soil != null)
                {
                    chunkSoil = soil;
                    break;
                }
            }
        }
        return chunkSoil != null ? chunkSoil : fallback;
    }

    @Nullable
    private String scan(int x, int z)
    {
        final int top = level.getHeight(Heightmap.Types.WORLD_SURFACE_WG, x, z);
        final BlockPos.MutableBlockPos cursor = new BlockPos.MutableBlockPos();
        for (int y = top; y > top - DEPTH && y > level.getMinBuildHeight(); y--)
        {
            final BlockFamilies.Parsed parsed = BlockFamilies.parse(BuiltInRegistries.BLOCK.getKey(level.getBlockState(cursor.set(x, y, z)).getBlock()));
            if (parsed != null && parsed.kind() == BlockFamilies.Kind.SOIL)
            {
                return parsed.material();
            }
        }
        return null;
    }
}
