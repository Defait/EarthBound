package pack.world.structure;

import java.util.Optional;
import java.util.concurrent.atomic.LongAdder;
import com.mojang.serialization.MapCodec;
import com.mojang.serialization.codecs.RecordCodecBuilder;
import com.mojang.serialization.Codec;
import net.dries007.tfc.world.ChunkGeneratorExtension;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Holder;
import net.minecraft.core.QuartPos;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.tags.TagKey;
import net.minecraft.world.level.biome.Biome;
import net.minecraft.world.level.chunk.ChunkGenerator;
import net.minecraft.world.level.levelgen.Heightmap;
import net.minecraft.world.level.levelgen.structure.Structure;
import net.minecraft.world.level.levelgen.structure.StructureType;
import net.minecraft.world.level.levelgen.structure.structures.JigsawStructure;
import pack.world.PackWorld;

/**
 * {@code pack_world:guarded_jigsaw}: a jigsaw structure (every vanilla field, flat in the same JSON object) that refuses to start
 * on ground a village cannot sit on: too steep, or too wet. {@code JigsawStructure} is final, so this wraps one and takes its
 * settings; the vanilla structure runs untouched and decides where the pieces go, the guard only looks at the ground around the
 * start piece's centre and says yes or no.
 * <p>
 * Pure function of (world seed, generator, start chunk): fixed sample columns, no random numbers, nothing read from chunks (heights
 * and biomes come from the generator), so every caller (chunk generation, {@code /locate}, {@code /place structure}) gets the same
 * answer in any order. Costs a handful of generator height queries per start attempt; start attempts only happen in the cells of a
 * structure set's own grid.
 */
public final class GuardedJigsawStructure extends Structure
{
    /**
     * @param radius              blocks from the start piece's centre to the outermost sample column (the guard judges that disc, not
     *                            the whole area the village may spread over)
     * @param samples             columns tested, the centre included (1 = the centre only)
     * @param maxHeightDifference refuse when the highest and lowest sampled surface differ by more than this many blocks
     * @param maxWaterFraction    refuse when more than this share of the columns is water (lake, river, ocean or below sea level)
     */
    public record Guard(int radius, int samples, int maxHeightDifference, double maxWaterFraction)
    {
        public static final MapCodec<Guard> CODEC = RecordCodecBuilder.mapCodec(i -> i.group(
            Codec.intRange(1, 128).optionalFieldOf("radius", 48).forGetter(Guard::radius),
            Codec.intRange(1, 64).optionalFieldOf("samples", 13).forGetter(Guard::samples),
            Codec.intRange(0, 384).optionalFieldOf("max_height_difference", 8).forGetter(Guard::maxHeightDifference),
            Codec.doubleRange(0, 1).optionalFieldOf("max_water_fraction", 0.1).forGetter(Guard::maxWaterFraction)
        ).apply(i, Guard::new));

        /** The sample columns relative to the centre: the centre, then a golden-angle spiral that covers the disc evenly. */
        public int[][] offsets()
        {
            final int[][] out = new int[samples][2];
            for (int i = 1; i < samples; i++)
            {
                final double r = radius * Math.sqrt(i / (double) (samples - 1));
                final double theta = i * 2.399963229728653;
                out[i][0] = (int) Math.floor(r * Math.cos(theta) + 0.5);
                out[i][1] = (int) Math.floor(r * Math.sin(theta) + 0.5);
            }
            return out;
        }

        public int allowedWet()
        {
            return (int) Math.floor(maxWaterFraction * samples + 1e-9);
        }

        /** What the guard sees around a start piece centre, without touching the counters. */
        public Verdict evaluate(GenerationContext context, BlockPos centre)
        {
            final ChunkGenerator generator = context.chunkGenerator();
            final boolean tfc = generator instanceof ChunkGeneratorExtension;
            final int sea = generator.getSeaLevel();
            final int[][] offsets = offsets();
            final int allowedWet = allowedWet();
            // phase 1, cheap (a biome lookup reads climate layers, TFC ignores y): refuse on water alone before any height query
            final boolean[] biomeWet = new boolean[offsets.length];
            int wet = 0;
            for (int i = 0; i < offsets.length; i++)
            {
                final int x = centre.getX() + offsets[i][0];
                final int z = centre.getZ() + offsets[i][1];
                if (waterBiome(context, x, sea, z))
                {
                    biomeWet[i] = true;
                    if (++wet > allowedWet)
                    {
                        return Verdict.refuse("water", 0, 0, wet, offsets.length);
                    }
                }
            }
            // phase 2, the heights, leaving as soon as the ground is too steep or too wet
            int min = Integer.MAX_VALUE;
            int max = Integer.MIN_VALUE;
            for (int i = 0; i < offsets.length; i++)
            {
                final int x = centre.getX() + offsets[i][0];
                final int z = centre.getZ() + offsets[i][1];
                final int h = generator.getBaseHeight(x, z, Heightmap.Types.WORLD_SURFACE_WG, context.heightAccessor(), context.randomState());
                min = Math.min(min, h);
                max = Math.max(max, h);
                if (max - min > maxHeightDifference)
                {
                    return Verdict.refuse("slope", min, max, wet, offsets.length);
                }
                // below sea level is water as well where the generator is TFC's (a non-TFC generator's surface height is the water's own)
                if (tfc && h < sea && !biomeWet[i] && ++wet > allowedWet)
                {
                    return Verdict.refuse("water", min, max, wet, offsets.length);
                }
            }
            return Verdict.pass(min, max, wet, offsets.length);
        }
    }

    /** What the guard saw: {@code pass}, or why not ({@code water} or {@code slope}), and the numbers. */
    public record Verdict(boolean pass, String reason, int min, int max, int wet, int samples)
    {
        static Verdict pass(int min, int max, int wet, int samples)
        {
            return new Verdict(true, "", min, max, wet, samples);
        }

        static Verdict refuse(String reason, int min, int max, int wet, int samples)
        {
            return new Verdict(false, reason, min, max, wet, samples);
        }
    }

    public static final MapCodec<GuardedJigsawStructure> CODEC = RecordCodecBuilder.mapCodec(i -> i.group(
        JigsawStructure.CODEC.forGetter(GuardedJigsawStructure::jigsaw),
        Guard.CODEC.fieldOf("guard").forGetter(GuardedJigsawStructure::guard)
    ).apply(i, GuardedJigsawStructure::new));

    private static final TagKey<Biome> LAKE = tag("is_lake");
    private static final TagKey<Biome> OCEAN = tag("is_ocean");
    private static final TagKey<Biome> RIVER = tag("is_river");

    /** {@code /pack_world guard off} switches the guard off (not saved): for placing a village by hand with {@code /place}. */
    public static volatile boolean enabled = true;

    private static final LongAdder ATTEMPTS = new LongAdder();
    private static final LongAdder REFUSED_BIOME = new LongAdder();
    private static final LongAdder REFUSED_WATER = new LongAdder();
    private static final LongAdder REFUSED_SLOPE = new LongAdder();
    private static final LongAdder PASSED = new LongAdder();
    private static final LongAdder NANOS = new LongAdder();

    private final JigsawStructure jigsaw;
    private final Guard guard;

    public GuardedJigsawStructure(JigsawStructure jigsaw, Guard guard)
    {
        // the wrapper's settings must be the inner structure's: a dimension keeps a structure set only if some structure's biomes
        // meet the biome source (ChunkGeneratorStructureState.createForNormal), so default settings would silently never generate
        super(new StructureSettings(jigsaw.biomes(), jigsaw.spawnOverrides(), jigsaw.step(), jigsaw.terrainAdaptation()));
        this.jigsaw = jigsaw;
        this.guard = guard;
    }

    public JigsawStructure jigsaw()
    {
        return jigsaw;
    }

    public Guard guard()
    {
        return guard;
    }

    private static TagKey<Biome> tag(String name)
    {
        return TagKey.create(Registries.BIOME, ResourceLocation.fromNamespaceAndPath("c", name));
    }

    @Override
    protected Optional<GenerationStub> findGenerationPoint(GenerationContext context)
    {
        final Optional<GenerationStub> stub = jigsaw.findGenerationPoint(context);      // vanilla's, untouched; uses context.random() as it would
        if (stub.isEmpty() || !enabled)
        {
            return stub;
        }
        ATTEMPTS.increment();
        final long start = System.nanoTime();
        try
        {
            final BlockPos centre = stub.get().position();
            if (!validBiome(context, centre.getX(), centre.getY(), centre.getZ()))      // what findValidGenerationPoint does next, before the costly part
            {
                REFUSED_BIOME.increment();
                return Optional.empty();
            }
            return inspect(context, centre).pass() ? stub : Optional.empty();
        }
        finally
        {
            NANOS.add(System.nanoTime() - start);
        }
    }

    /** The guard's verdict for a start piece centre, with the counters updated. */
    public Verdict inspect(GenerationContext context, BlockPos centre)
    {
        final Verdict verdict = guard.evaluate(context, centre);
        if (verdict.pass())
        {
            PASSED.increment();
        }
        else if (verdict.reason().equals("water"))
        {
            REFUSED_WATER.increment();
        }
        else
        {
            REFUSED_SLOPE.increment();
        }
        return verdict;
    }

    private static boolean waterBiome(GenerationContext context, int x, int y, int z)
    {
        final Holder<Biome> biome = biomeAt(context, x, y, z);
        return biome.is(LAKE) || biome.is(OCEAN) || biome.is(RIVER);
    }

    private static boolean validBiome(GenerationContext context, int x, int y, int z)
    {
        return context.validBiome().test(biomeAt(context, x, y, z));
    }

    private static Holder<Biome> biomeAt(GenerationContext context, int x, int y, int z)
    {
        return context.biomeSource().getNoiseBiome(QuartPos.fromBlock(x), QuartPos.fromBlock(y), QuartPos.fromBlock(z), context.randomState().sampler());
    }

    @Override
    public StructureType<?> type()
    {
        return PackWorld.GUARDED_JIGSAW.get();
    }

    /** attempts, refusedBiome, refusedWater, refusedSlope, passed and nanos spent (the guard and the vanilla start it follows). */
    public static long[] stats()
    {
        return new long[] {ATTEMPTS.sum(), REFUSED_BIOME.sum(), REFUSED_WATER.sum(), REFUSED_SLOPE.sum(), PASSED.sum(), NANOS.sum()};
    }

    public static void resetStats()
    {
        ATTEMPTS.reset();
        REFUSED_BIOME.reset();
        REFUSED_WATER.reset();
        REFUSED_SLOPE.reset();
        PASSED.reset();
        NANOS.reset();
    }
}
