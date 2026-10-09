package pack.world.ocean;

import net.dries007.tfc.world.biome.BiomeNoise;
import net.dries007.tfc.world.noise.Noise2D;

/**
 * Deeper oceans inside the existing world height (docs/design.md, "Oceans"). TFC hard-codes each ocean biome's floor in
 * {@code TFCBiomes}: a pair of offsets from sea level given to {@code BiomeNoise.ocean} (and {@code oceanTrench}), and the floor
 * noise runs between {@code 63 + min} and {@code 63 + max}. TFC: Real World only chooses which of those biomes goes where, so
 * moving the pairs deepens every ocean it generates without touching its map. {@code OceanDepthMixin} remaps the pairs on the way
 * into the two noise builders; a pair is remapped as a whole, so biomes that share one (the atolls and the volcanic arc share the
 * ocean's, the ridge and the atolls of the deep sea the deep ocean's) stay level with each other.
 * <p>
 * The ocean ridge builds its floor from the deep ocean's pair and then lays an absolute profile (y 13 to 51) over it, measured for
 * the old floor (y 17 to 33): on a floor about 40 blocks lower that profile would be a plateau at y 13 under the whole biome. So the
 * ridge is rebuilt as the new deep floor plus the old ridge's height above the old floor: the same crest, flank and axis relief,
 * standing on the new floor.
 * <p>
 * Atolls and stratovolcanoes (TFC's {@code CenteredFeatureNoise}) have the same trouble: a foot at a fixed y, laid over the floor as
 * {@code max(floor, profile)}, that was under every old floor and is a ledge over the new ones. {@link #atollFoot} and
 * {@link #stratovolcano} keep the foot under the floor; the tops stay where they were.
 */
public final class OceanDepths
{
    // {old min, old max, new min, new max}, offsets from sea level. The reef's (-16, -8) is not listed: it stays as it was.
    private static final int[][] OCEAN = {{-26, -12, -32, -14}, {-46, -30, -95, -65}};
    private static final int[][] TRENCH = {{-60, -46, -112, -95}};
    /** The deep ocean's pair, which {@code oceanRidge} asks {@code ocean} for. */
    private static final int RIDGE_MIN = -46, RIDGE_MAX = -30;

    /** How far under the floor an atoll's or a volcano's foot is kept (22 is how far y 3, an atoll's foot, was under the old deep floor's middle). */
    private static final double FOOT_BELOW_FLOOR = 22.0;

    /** Set while the ridge builds its old floor and old relief, so {@link #ocean} leaves the pair as TFC wrote it. */
    private static final ThreadLocal<Boolean> ORIGINAL = new ThreadLocal<>();

    private OceanDepths() {}

    /** The depth pair {@code BiomeNoise.ocean} should use for the pair TFC asked for. */
    public static int[] ocean(int min, int max)
    {
        return ORIGINAL.get() != null ? new int[] {min, max} : remap(OCEAN, min, max);
    }

    /** The depth pair {@code BiomeNoise.oceanTrench} should use for the pair TFC asked for. */
    public static int[] trench(int min, int max)
    {
        return remap(TRENCH, min, max);
    }

    /** The ridge, as the new deep floor plus the old ridge's height over the old deep floor. */
    public static Noise2D ridge(long seed, java.util.function.LongFunction<Noise2D> original)
    {
        final Noise2D oldRidge, oldFloor;
        ORIGINAL.set(Boolean.TRUE);
        try
        {
            oldRidge = original.apply(seed);
            oldFloor = BiomeNoise.ocean(seed, RIDGE_MIN, RIDGE_MAX);
        }
        finally
        {
            ORIGINAL.remove();
        }
        final Noise2D newFloor = BiomeNoise.ocean(seed, RIDGE_MIN, RIDGE_MAX);
        return (x, z) -> newFloor.noise(x, z) + (oldRidge.noise(x, z) - oldFloor.noise(x, z));
    }

    /**
     * The foot of an atoll's profile: TFC's y 3, but never more than 22 blocks under the floor the atoll stands on (22 is how far
     * y 3 was under the old deep floor's middle, y 25). On the shallow ocean's floors (y 31 and up) that is y 3 as before.
     */
    public static double atollFoot(double foot, double floor)
    {
        return Math.min(foot, floor - FOOT_BELOW_FLOOR);
    }

    /**
     * A stratovolcano's height at a column (TFC's {@code max(profile, floor)}), with the profile's foot lowered under a deep floor.
     * The profile is {@code 63 + base + shape * scale}, and outside the cone its skirt ends in a constant (measured: shape about
     * -0.26 at the cell's edge), so y -1 for the volcanic arc (base -12, scale 200) and 11 for the volcanic islands and coasts
     * (base 0). That was under nearly every old floor; over a trench it is a flat ledge across the rest of the volcano's cell. So the
     * part of the profile under the cone's top is stretched down: the top stays where it was, the foot goes to
     * {@link #FOOT_BELOW_FLOOR} blocks under the floor, and nothing changes where the floor is high (the arc's own floor, y 31 to 49).
     */
    public static double stratovolcano(double height, double floor, double scale, double base)
    {
        return lowerFoot(height, floor, 63.0 + base - 0.26 * scale, 63.0 + base + scale);
    }

    /** Stretches {@code height} (a profile that rises from {@code foot} to {@code peak}, or the floor) so that its foot is under {@code floor}. */
    private static double lowerFoot(double height, double floor, double foot, double peak)
    {
        if (height <= floor || peak <= foot)
        {
            return height;
        }
        double newFoot = Math.min(foot, floor - FOOT_BELOW_FLOOR);
        if (newFoot >= foot)
        {
            return height;
        }
        return Math.max(floor, peak - (peak - height) * (peak - newFoot) / (peak - foot));
    }

    private static int[] remap(int[][] table, int min, int max)
    {
        for (int[] row : table)
        {
            if (row[0] == min && row[1] == max)
            {
                return new int[] {row[2], row[3]};
            }
        }
        return new int[] {min, max};
    }
}
