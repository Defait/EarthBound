package pack.world.geo;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import com.mojang.serialization.Codec;
import com.mojang.serialization.DataResult;
import com.mojang.serialization.MapCodec;
import com.mojang.serialization.codecs.RecordCodecBuilder;
import net.dries007.tfc.world.ChunkGeneratorExtension;
import net.dries007.tfc.world.chunkdata.ChunkData;
import net.dries007.tfc.world.placement.ClimatePlacement;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Vec3i;
import net.minecraft.util.StringRepresentable;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.chunk.ChunkGeneratorStructureState;
import net.minecraft.world.level.levelgen.LegacyRandomSource;
import net.minecraft.world.level.levelgen.WorldgenRandom;
import net.minecraft.world.level.levelgen.structure.placement.RandomSpreadStructurePlacement;
import net.minecraft.world.level.levelgen.structure.placement.RandomSpreadType;
import net.minecraft.world.level.levelgen.structure.placement.StructurePlacementType;
import net.neoforged.fml.ModList;
import org.jetbrains.annotations.Nullable;
import pack.world.PackWorld;

/**
 * {@code pack_world:region}: random spread placement that only starts structures inside real-world regions (latitude/longitude
 * polygons or boxes, through the same projection TFC: Real World uses for its waypoints) and where TFC's climate allows,
 * exactly as {@code tfc:climate} would. A village of Norse houses belongs to Scandinavia, not to every cold place on Earth.
 * <p>
 * The three tests, in order of cost: the spread grid (one candidate chunk per spacing x spacing cell, vanilla's), the region
 * (a bounding box and an even-odd polygon test in block space, on shapes projected once per world configuration), and TFC's
 * climate at the candidate chunk (the same code as {@code ClimateStructurePlacement}). {@code /locate} asks the grid for its
 * candidates and then {@link #applyAdditionalChunkRestrictions}, so the region test also sits there: cells outside every region
 * cost a compare, not a chunk load. Nothing here reads chunks, so the result doesn't depend on generation order.
 * <p>
 * Without TFC: Real World the regions mean nothing: {@code outside} says whether the structure then starts everywhere
 * ({@code anywhere}) or nowhere ({@code never}, the default).
 */
public class RegionPlacement extends RandomSpreadStructurePlacement
{
    public enum Outside implements StringRepresentable
    {
        NEVER("never"),
        ANYWHERE("anywhere");

        public static final Codec<Outside> CODEC = StringRepresentable.fromEnum(Outside::values);

        private final String name;

        Outside(String name)
        {
            this.name = name;
        }

        @Override
        public String getSerializedName()
        {
            return name;
        }
    }

    public record LatLon(double lat, double lon)
    {
        static final Codec<LatLon> CODEC = Codec.DOUBLE.listOf().comapFlatMap(
            l -> l.size() == 2 && Math.abs(l.get(0)) <= 90 && Math.abs(l.get(1)) <= 180
                ? DataResult.success(new LatLon(l.get(0), l.get(1))) : DataResult.error(() -> "expected [latitude, longitude]: " + l),
            p -> List.of(p.lat(), p.lon()));
    }

    /** Exactly one of {@code polygon} or {@code box}; optional fields so that encoding reproduces the JSON as it was written. */
    public record Region(String name, Optional<List<LatLon>> polygon, Optional<List<Double>> box)
    {
        static final Codec<Region> CODEC = RecordCodecBuilder.<Region>create(i -> i.group(
            Codec.STRING.fieldOf("name").forGetter(Region::name),
            LatLon.CODEC.listOf().optionalFieldOf("polygon").forGetter(Region::polygon),
            Codec.DOUBLE.listOf().optionalFieldOf("box").forGetter(Region::box)
        ).apply(i, Region::new)).validate(Region::check);

        private static DataResult<Region> check(Region r)
        {
            if (r.name.isEmpty())
            {
                return DataResult.error(() -> "a region needs a name");
            }
            if (r.polygon.isPresent() == r.box.isPresent())
            {
                return DataResult.error(() -> "region " + r.name + " needs exactly one of polygon and box");
            }
            if (r.polygon.isPresent() && r.polygon.get().size() < 3)
            {
                return DataResult.error(() -> "region " + r.name + ": a polygon needs at least 3 vertices");
            }
            if (r.box.isPresent())
            {
                final List<Double> b = r.box.get();
                if (b.size() != 4 || Math.abs(b.get(0)) > 90 || Math.abs(b.get(2)) > 90 || Math.abs(b.get(1)) > 180 || Math.abs(b.get(3)) > 180
                    || b.get(0) >= b.get(2) || b.get(1).equals(b.get(3)))
                {
                    return DataResult.error(() -> "region " + r.name + ": a box is [south, west, north, east] with south < north and west != east"
                        + " (west > east crosses the antimeridian): " + b);
                }
            }
            return DataResult.success(r);
        }

        List<RegionGeometry.Point> ring()
        {
            if (polygon.isPresent())
            {
                final List<RegionGeometry.Point> out = new ArrayList<>();
                polygon.get().forEach(p -> out.add(new RegionGeometry.Point(p.lat(), p.lon())));
                return out;
            }
            final List<Double> b = box.orElseThrow();
            return RegionGeometry.boxRing(b.get(0), b.get(1), b.get(2), b.get(3));
        }
    }

    public record Spread(int spacing, int separation, RandomSpreadType type)
    {
        static final MapCodec<Spread> CODEC = RecordCodecBuilder.mapCodec(i -> i.group(
            Codec.intRange(0, 4096).fieldOf("spacing").forGetter(Spread::spacing),
            Codec.intRange(0, 4096).fieldOf("separation").forGetter(Spread::separation),
            RandomSpreadType.CODEC.optionalFieldOf("spread_type", RandomSpreadType.LINEAR).forGetter(Spread::type)
        ).apply(i, Spread::new));
    }

    public record Zones(List<Region> regions, List<Region> exclude, Outside outside)
    {
        static final MapCodec<Zones> CODEC = RecordCodecBuilder.mapCodec(i -> i.group(
            Region.CODEC.listOf().fieldOf("regions").forGetter(Zones::regions),
            Region.CODEC.listOf().optionalFieldOf("exclude", List.of()).forGetter(Zones::exclude),
            Outside.CODEC.optionalFieldOf("outside", Outside.NEVER).forGetter(Zones::outside)
        ).apply(i, Zones::new));
    }

    public static final MapCodec<RegionPlacement> CODEC = RecordCodecBuilder.<RegionPlacement>mapCodec(i -> placementCodec(i).and(i.group(
        Spread.CODEC.forGetter(RegionPlacement::spread),
        Zones.CODEC.forGetter(RegionPlacement::zones),
        ClimatePlacement.CODEC.codec().fieldOf("climate").forGetter(RegionPlacement::climate)
    )).apply(i, RegionPlacement::new)).validate(RegionPlacement::check);

    /** The projected shapes for one world configuration. */
    private record Projected(String key, List<RegionGeometry.Shape> include, List<RegionGeometry.Shape> exclude) {}

    private static final Set<String> WARNED = ConcurrentHashMap.newKeySet();

    private final Spread spread;
    private final Zones zones;
    private final ClimatePlacement climate;
    @Nullable private volatile Projected projected;

    @SuppressWarnings("deprecation")
    public RegionPlacement(Vec3i locateOffset, FrequencyReductionMethod frequencyReductionMethod, float frequency, int salt,
                           Optional<ExclusionZone> exclusionZone, Spread spread, Zones zones, ClimatePlacement climate)
    {
        super(locateOffset, frequencyReductionMethod, frequency, salt, exclusionZone, spread.spacing(), spread.separation(), spread.type());
        this.spread = spread;
        this.zones = zones;
        this.climate = climate;
    }

    private static DataResult<RegionPlacement> check(RegionPlacement p)
    {
        if (p.spread.spacing() <= p.spread.separation())
        {
            return DataResult.error(() -> "Spacing has to be larger than separation");
        }
        if (p.zones.regions().isEmpty())
        {
            return DataResult.error(() -> "A region placement needs at least one region");
        }
        return DataResult.success(p);
    }

    public Spread spread()
    {
        return spread;
    }

    public Zones zones()
    {
        return zones;
    }

    public ClimatePlacement climate()
    {
        return climate;
    }

    @Override
    protected boolean isPlacementChunk(ChunkGeneratorStructureState state, int chunkX, int chunkZ)
    {
        return super.isPlacementChunk(state, chunkX, chunkZ) && regionContains(chunkX, chunkZ) && climateAllows(state, chunkX, chunkZ);
    }

    /** {@code /locate} reaches a cell's candidate here before it builds a start: the region test keeps far cells cheap. */
    @Override
    public boolean applyAdditionalChunkRestrictions(int chunkX, int chunkZ, long seed)
    {
        return super.applyAdditionalChunkRestrictions(chunkX, chunkZ, seed) && regionContains(chunkX, chunkZ);
    }

    @Override
    public StructurePlacementType<?> type()
    {
        return PackWorld.REGION.get();
    }

    /** Block x and z of a latitude and longitude as TFC: Real World places its waypoints; empty without that mod. */
    public static int[] blockOf(double latitude, double longitude)
    {
        return ModList.get().isLoaded("tfc_real_world") ? RealWorld.toBlockXZ(latitude, longitude) : new int[0];
    }

    /** Step 1 alone (the spread grid), for tests. */
    public boolean gridCandidate(ChunkGeneratorStructureState state, int chunkX, int chunkZ)
    {
        return super.isPlacementChunk(state, chunkX, chunkZ);
    }

    /** Step 3 alone (TFC's climate at the chunk), for tests. */
    public boolean climateAllows(ChunkGeneratorStructureState state, int chunkX, int chunkZ)
    {
        final ChunkGeneratorExtension generator = ChunkGeneratorExtension.getFromStructureState(state);
        if (generator == null)
        {
            return false;
        }
        final ChunkPos chunk = new ChunkPos(chunkX, chunkZ);
        final BlockPos pos = new BlockPos(chunk.getMinBlockX(), 0, chunk.getMinBlockZ());
        final ChunkData data = generator.chunkDataGenerator().createAndGenerate(chunk);
        final WorldgenRandom random = new WorldgenRandom(new LegacyRandomSource(0L));
        random.setLargeFeatureWithSalt(state.getLevelSeed(), chunkX, chunkZ, salt());
        return climate.isValidNonHemispheral(data, pos, random);
    }

    /** Step 2 alone: is the chunk's centre inside a region and outside every excluded one? */
    public boolean regionContains(int chunkX, int chunkZ)
    {
        if (!ModList.get().isLoaded("tfc_real_world"))
        {
            return zones.outside() == Outside.ANYWHERE;
        }
        final Projected p = projected();
        if (p == null)
        {
            return false;
        }
        final double x = (chunkX << 4) + 8;
        final double z = (chunkZ << 4) + 8;
        boolean in = false;
        for (RegionGeometry.Shape shape : p.include())
        {
            if (shape.contains(x, z))
            {
                in = true;
                break;
            }
        }
        if (!in)
        {
            return false;
        }
        for (RegionGeometry.Shape shape : p.exclude())
        {
            if (shape.contains(x, z))
            {
                return false;
            }
        }
        return true;
    }

    /** The names of the regions containing a block position, excluded ones as {@code "!name"}; empty without TFC: Real World. */
    public List<String> regionsAtBlock(double x, double z)
    {
        final List<String> out = new ArrayList<>();
        final Projected p = ModList.get().isLoaded("tfc_real_world") ? projected() : null;
        if (p != null)
        {
            p.include().forEach(s -> { if (s.contains(x, z)) out.add(s.name()); });
            p.exclude().forEach(s -> { if (s.contains(x, z)) out.add("!" + s.name()); });
        }
        return out;
    }

    /** The projected shapes of this world (included, or excluded), for tests; empty without TFC: Real World. */
    public List<RegionGeometry.Shape> shapes(boolean excluded)
    {
        final Projected p = ModList.get().isLoaded("tfc_real_world") ? projected() : null;
        return p == null ? List.of() : excluded ? p.exclude() : p.include();
    }

    @Nullable
    private Projected projected()
    {
        final String key;
        try
        {
            key = RealWorld.configKey();
        }
        catch (RuntimeException e)
        {
            return null;                    // the Real World config isn't loaded yet: answer "no" now, and ask again next time
        }
        Projected p = projected;
        if (p == null || !p.key().equals(key))
        {
            try
            {
                p = new Projected(key, project(zones.regions()), project(zones.exclude()));
            }
            catch (RuntimeException e)
            {
                return null;
            }
            projected = p;
        }
        return p;
    }

    private List<RegionGeometry.Shape> project(List<Region> regions)
    {
        final List<RegionGeometry.Shape> out = new ArrayList<>();
        final double seam = RealWorld.horizontalScale();
        for (Region region : regions)
        {
            final String[] problem = new String[1];
            final RegionGeometry.Shape shape = RegionGeometry.project(region.name(), region.ring(), RealWorld::toBlockXZ, 16, seam, problem);
            if (shape == null)
            {
                if (WARNED.add(region.name() + problem[0]))
                {
                    PackWorld.LOGGER.error("pack_world:region: region {} is dropped, it is {}", region.name(), problem[0]);
                }
                continue;
            }
            out.add(shape);
        }
        return List.copyOf(out);
    }
}
