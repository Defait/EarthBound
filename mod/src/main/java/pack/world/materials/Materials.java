package pack.world.materials;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import net.dries007.tfc.client.overworld.SolarCalculator;
import net.dries007.tfc.util.EnvironmentHelpers;
import net.dries007.tfc.world.ChunkGeneratorExtension;
import net.dries007.tfc.world.chunkdata.ChunkData;
import net.dries007.tfc.world.feature.tree.ForestConfig;
import net.dries007.tfc.world.placement.ClimatePlacement;
import net.dries007.tfc.world.settings.RockSettings;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Holder;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.ResourceKey;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.chunk.ChunkGenerator;
import net.minecraft.world.level.levelgen.feature.ConfiguredFeature;
import org.jetbrains.annotations.Nullable;

/**
 * The materials of one structure piece: the surface rock at its anchor, the climate's most typical tree there, and the
 * sand of that rock. Soil is per column (see {@link SoilSampler}). Everything comes from TFC's own generators and is a pure
 * function of the position, so every chunk a piece spans gets the same answer, in any generation order.
 *
 * @param fromTfc false when the level has no TFC generator and the fallbacks were used
 */
public record Materials(String rock, String wood, String sand, boolean fromTfc)
{
    public static final ResourceLocation FOREST = ResourceLocation.fromNamespaceAndPath("tfc", "forest");

    /** The fixed and fallback choices a processor carries. "local" means: ask TFC. */
    public record Choice(String rock, String wood, String sand, int woodVariety, AlloyPolicy policy, String substituteRock)
    {
        boolean localRock() { return rock.equals("local"); }
        boolean localWood() { return wood.equals("local"); }
        boolean localSand() { return sand.equals("local"); }
    }

    public static Materials resolve(ServerLevel level, BlockPos anchor, Choice choice)
    {
        final ChunkGenerator generator = level.getChunkSource().getGenerator();
        final ChunkGeneratorExtension ext = generator instanceof ChunkGeneratorExtension e ? e : null;

        String rock = choice.localRock() ? null : choice.rock();
        String sand = choice.localSand() ? null : choice.sand();
        String wood = choice.localWood() ? null : choice.wood();
        if (ext != null && (rock == null || sand == null))
        {
            final RockSettings settings = ext.chunkDataGenerator().generateSurfaceRock(anchor.getX(), anchor.getZ());
            if (rock == null)
            {
                rock = lastSegment(settings.raw(), "rock/raw/", BlockFamilies.ROCKS);
            }
            if (sand == null)
            {
                sand = lastSegment(settings.sand(), "sand/", BlockFamilies.SANDS);
            }
        }
        if (ext != null && wood == null)
        {
            wood = forestWood(level, ext, anchor, choice.woodVariety());
        }
        final boolean fromTfc = ext != null;
        if (rock == null)
        {
            rock = choice.substituteRock();
        }
        if (choice.policy() == AlloyPolicy.SUBSTITUTE && BlockFamilies.ALLOY_ROCKS.contains(rock))
        {
            rock = choice.substituteRock();
        }
        return new Materials(rock, wood == null ? "oak" : wood, sand == null ? "yellow" : sand, fromTfc);
    }

    /**
     * The tree TFC's forests would grow at this position: entries whose climate is valid, ordered by TFC's own
     * {@code distanceFromMean} (as {@code ForestFeature.getTrees} does), one of the first {@code variety} picked by position.
     * Where no tree grows (grassland, desert, tundra), the entry whose climate window is nearest: timber from the nearest woods.
     */
    @Nullable
    static String forestWood(ServerLevel level, ChunkGeneratorExtension ext, BlockPos anchor, int variety)
    {
        final ConfiguredFeature<?, ?> forest = level.registryAccess().registryOrThrow(Registries.CONFIGURED_FEATURE).get(FOREST);
        if (forest == null || !(forest.config() instanceof ForestConfig config))
        {
            return null;
        }
        final ChunkData data = ext.chunkDataGenerator().createAndGenerate(new ChunkPos(anchor));
        final int y = anchor.getY();
        final float temperature = EnvironmentHelpers.adjustAvgTempForElev(y, data.getAverageSeaLevelTemp(anchor));
        final float groundwater = data.getAverageGroundwater(anchor);
        final float rainVariance = data.getRainVariance(anchor) * (SolarCalculator.getInNorthernHemisphere(anchor, level) ? 1f : -1f);

        record Candidate(String wood, ForestConfig.Entry entry, float distance) {}
        final List<Candidate> valid = new ArrayList<>();
        final List<Candidate> all = new ArrayList<>();
        for (Holder<ConfiguredFeature<?, ?>> holder : config.entries())
        {
            if (!(holder.value().config() instanceof ForestConfig.Entry entry))
            {
                continue;
            }
            final String wood = holder.unwrapKey().map(ResourceKey::location).map(Materials::woodOfEntry).orElse(null);
            if (wood == null)
            {
                continue;
            }
            all.add(new Candidate(wood, entry, outsideClimate(entry.climate(), temperature, groundwater, rainVariance)));
            if (entry.isValid(temperature, groundwater, rainVariance, y))
            {
                valid.add(new Candidate(wood, entry, entry.distanceFromMean(temperature, groundwater, rainVariance, y)));
            }
        }
        if (!valid.isEmpty())
        {
            valid.sort(Comparator.comparingDouble(Candidate::distance));
            final int n = Math.min(Math.max(variety, 1), valid.size());
            final int index = Math.floorMod(BlockFamilies.positionSeed(anchor.getX(), 0, anchor.getZ()), n);
            return valid.get(index).wood();
        }
        return all.stream().min(Comparator.comparingDouble(Candidate::distance)).map(Candidate::wood).orElse(null);
    }

    /** How far a climate lies outside an entry's window, in rough units of 10 °C, 100 of groundwater, 1 of rain variance. */
    static float outsideClimate(ClimatePlacement c, float temperature, float groundwater, float rainVariance)
    {
        final float rv = c.isRainVarianceAbsolute() ? Math.abs(rainVariance) : rainVariance;
        return outside(temperature, c.getMinTemp(), c.getMaxTemp()) / 10f
            + outside(groundwater, c.getMinGroundwater(), c.getMaxGroundwater()) / 100f
            + outside(rv, c.getMinRainVariance(), c.getMaxRainVariance());
    }

    private static float outside(float value, float min, float max)
    {
        return value < min ? min - value : value > max ? value - max : 0f;
    }

    /** tfc:tree/oak_entry -> oak */
    @Nullable
    static String woodOfEntry(ResourceLocation id)
    {
        String path = id.getPath();
        if (path.startsWith("tree/"))
        {
            path = path.substring(5);
        }
        if (path.endsWith("_entry"))
        {
            path = path.substring(0, path.length() - 6);
        }
        return BlockFamilies.WOODS.contains(path) ? path : null;
    }

    @Nullable
    private static String lastSegment(Block block, String prefix, List<String> allowed)
    {
        final ResourceLocation id = BuiltInRegistries.BLOCK.getKey(block);
        if (!"tfc".equals(id.getNamespace()) || !id.getPath().startsWith(prefix))
        {
            return null;
        }
        final String name = id.getPath().substring(prefix.length());
        return allowed.contains(name) ? name : null;
    }
}
