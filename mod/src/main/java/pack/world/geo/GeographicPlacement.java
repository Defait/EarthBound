package pack.world.geo;

import java.util.List;
import java.util.Optional;
import com.mojang.serialization.Codec;
import com.mojang.serialization.DataResult;
import com.mojang.serialization.MapCodec;
import com.mojang.serialization.codecs.RecordCodecBuilder;
import net.minecraft.core.Vec3i;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.chunk.ChunkGeneratorStructureState;
import net.minecraft.world.level.levelgen.structure.placement.RandomSpreadStructurePlacement;
import net.minecraft.world.level.levelgen.structure.placement.RandomSpreadType;
import net.minecraft.world.level.levelgen.structure.placement.StructurePlacementType;
import net.neoforged.fml.ModList;
import org.jetbrains.annotations.Nullable;
import pack.world.PackWorld;

/**
 * {@code pack_world:geographic}: one structure at a real latitude and longitude. The start chunk is where TFC: Real World puts
 * the matching waypoint ({@code WaypointCoordinates.toBlockXZ}), plus an optional block offset (for coastal sites the map's
 * coastline puts in the sea). Nothing reads chunks, so the result doesn't depend on generation order or on where players are.
 * <p>
 * Extends random spread (as TFC's climate placement does) so {@code /locate} works: every grid cell's candidate is the site.
 * Sites only place in worlds whose {@link SiteGuard} lists them.
 */
public class GeographicPlacement extends RandomSpreadStructurePlacement
{
    public record Site(String name, double latitude, double longitude, List<Integer> offset)
    {
        public static final MapCodec<Site> CODEC = RecordCodecBuilder.mapCodec(i -> i.group(
            Codec.STRING.fieldOf("site").forGetter(Site::name),
            Codec.doubleRange(-90, 90).fieldOf("latitude").forGetter(Site::latitude),
            Codec.doubleRange(-180, 180).fieldOf("longitude").forGetter(Site::longitude),
            Codec.INT.listOf().validate(l -> l.size() == 2 ? DataResult.success(l) : DataResult.error(() -> "offset must be [x, z]"))
                .optionalFieldOf("offset", List.of(0, 0)).forGetter(Site::offset)
        ).apply(i, Site::new));
    }

    public static final MapCodec<GeographicPlacement> CODEC = RecordCodecBuilder.mapCodec(i ->
        placementCodec(i).and(Site.CODEC.forGetter(GeographicPlacement::site)).apply(i, GeographicPlacement::new));

    private static final int SPACING = 4096;

    private final Site site;
    @Nullable private volatile Cached cached;

    private record Cached(String key, ChunkPos chunk, int x, int z) {}

    @SuppressWarnings("deprecation")
    public GeographicPlacement(Vec3i locateOffset, FrequencyReductionMethod frequencyReductionMethod, float frequency, int salt,
                               Optional<ExclusionZone> exclusionZone, Site site)
    {
        super(locateOffset, frequencyReductionMethod, frequency, salt, exclusionZone, SPACING, 0, RandomSpreadType.LINEAR);
        this.site = site;
    }

    public Site site()
    {
        return site;
    }

    /** The site's start chunk in this world, or null without TFC: Real World. */
    @Nullable
    public ChunkPos siteChunk()
    {
        final Cached c = resolve();
        return c == null ? null : c.chunk();
    }

    /** The site's block x and z (after the offset), or null without TFC: Real World. */
    @Nullable
    public int[] siteBlock()
    {
        final Cached c = resolve();
        return c == null ? null : new int[] {c.x(), c.z()};
    }

    @Nullable
    private Cached resolve()
    {
        if (!ModList.get().isLoaded("tfc_real_world"))
        {
            return null;
        }
        final String key = RealWorld.configKey();
        Cached c = cached;
        if (c == null || !c.key().equals(key))
        {
            final int[] xz = RealWorld.toBlockXZ(site.latitude(), site.longitude());
            final int x = xz[0] + site.offset().get(0);
            final int z = xz[1] + site.offset().get(1);
            c = new Cached(key, new ChunkPos(x >> 4, z >> 4), x, z);
            cached = c;
        }
        return c;
    }

    @Override
    protected boolean isPlacementChunk(ChunkGeneratorStructureState state, int chunkX, int chunkZ)
    {
        final ChunkPos chunk = siteChunk();
        return chunk != null && chunk.x == chunkX && chunk.z == chunkZ && SiteGuard.allowed(site.name());
    }

    @Override
    public ChunkPos getPotentialStructureChunk(long seed, int regionX, int regionZ)
    {
        final ChunkPos chunk = siteChunk();
        return chunk != null ? chunk : super.getPotentialStructureChunk(seed, regionX, regionZ);
    }

    @Override
    public StructurePlacementType<?> type()
    {
        return PackWorld.GEOGRAPHIC.get();
    }
}
