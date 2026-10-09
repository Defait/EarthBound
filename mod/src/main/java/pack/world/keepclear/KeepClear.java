package pack.world.keepclear;

import java.lang.ref.WeakReference;
import java.util.ArrayList;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.LongAdder;
import net.minecraft.core.BlockPos;
import it.unimi.dsi.fastutil.longs.LongSet;
import net.minecraft.core.Registry;
import net.minecraft.core.RegistryAccess;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.level.WorldGenRegion;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.StructureManager;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.level.levelgen.structure.BoundingBox;
import net.minecraft.world.level.levelgen.structure.Structure;
import net.minecraft.world.level.levelgen.structure.StructurePiece;
import net.minecraft.world.level.levelgen.structure.StructureStart;
import pack.world.PackWorld;

/**
 * Keeps the land around structures clear (docs/lived-in.md, "Keeping the land clear"). Structures are placed before TFC's and
 * ArborFirmaCraft's forests and boulders, which know nothing of them: a village used to come out buried in trees and boulders, and
 * other mods' structures overlapped it. Everything here reads the structure starts that the generation step guarantees around a
 * chunk (the references of the 3 x 3 chunks around it), so it is a pure function of the world seed and the chunk: any order of
 * generation gives the same result.
 * <ul>
 *     <li><b>Trees.</b> {@code ForestFeatureMixin} asks {@link #treeBlocked} for every trunk TFC's forest feature wants to place (and
 *     bushes), and {@link #blockWriteBlocked} for every block of a fallen log. A trunk is refused within {@code solid} blocks of a piece
 *     of a structure that keeps trees out, and thins out to nothing by {@code margin} blocks (by a hash of the column, so the edge is
 *     ragged, not a rectangle).</li>
 *     <li><b>Boulders and the like.</b> The placement filter {@code pack_world:keep_clear} ({@link KeepClearFilter}) does the same with
 *     a distance, for placed features that data overrides give it.</li>
 *     <li><b>Overlaps.</b> {@code StructureStartMixin} asks {@link #suppressed} before a piece of a structure that yields is placed:
 *     not where it overlaps (box plus a little) a piece of a structure that holds the ground, e.g. Moog's wells, windmills and
 *     fire camps in a village, or a mineshaft under its foundations.</li>
 * </ul>
 */
public final class KeepClear
{
    private static volatile KeepClearConfig config = KeepClearConfig.EMPTY;
    private static final Map<Structure, Kind> KINDS = new ConcurrentHashMap<>();
    private static final ThreadLocal<Scope> SCOPE = new ThreadLocal<>();
    private static final ThreadLocal<Cached> CACHE = new ThreadLocal<>();
    private static final ThreadLocal<Filtered> FILTERED = new ThreadLocal<>();
    private static final Map<String, LongAdder> STATS = new ConcurrentHashMap<>();
    private static final Set<String> WARNED = ConcurrentHashMap.newKeySet();
    private static final Set<String> SKIPPED = ConcurrentHashMap.newKeySet();
    private static final LongAdder ZONES = new LongAdder();
    private static final LongAdder ZONE_NANOS = new LongAdder();
    private static final LongAdder TESTS = new LongAdder();
    private static final LongAdder TEST_NANOS = new LongAdder();
    private static final AtomicInteger LOGGED = new AtomicInteger();
    private static final int LOG_LIMIT = 400;

    private KeepClear() {}

    /** What the config says about one structure. */
    private record Kind(boolean trees, boolean holds, boolean yields)
    {
        static final Kind NONE = new Kind(false, false, false);

        boolean relevant()
        {
            return trees || holds;
        }
    }

    /** A held piece's box (already widened by the config) and whose it is. */
    private record Held(BoundingBox box, ResourceLocation structure) {}

    /** The pieces around one chunk that matter: boxes that keep trees out, and (widened) boxes that keep other pieces out. */
    private static final class Zone
    {
        static final Zone EMPTY = new Zone();
        final List<BoundingBox> trees = new ArrayList<>();
        final List<Held> holds = new ArrayList<>();
    }

    private record Cached(StructureManager manager, long chunk, Zone zone) {}

    /** The last chunk's zone a placed feature's filter asked for on this thread (features of one chunk ask hundreds of times). */
    private record Filtered(WeakReference<WorldGenRegion> region, long chunk, Zone zone) {}

    /** The thread's forest scope: the region being decorated and, once asked for, the zone around its chunk. */
    private static final class Scope
    {
        final WorldGenRegion region;
        final ChunkPos chunk;
        Zone zone;

        Scope(WorldGenRegion region, ChunkPos chunk)
        {
            this.region = region;
            this.chunk = chunk;
        }

        Zone zone()
        {
            if (zone == null)
            {
                try
                {
                    zone = zoneAround(region, region.registryAccess(), chunk);
                }
                catch (RuntimeException e)
                {
                    warnOnce("forest zone", e);
                    zone = Zone.EMPTY;
                }
            }
            return zone;
        }
    }

    static void setConfig(KeepClearConfig next)
    {
        config = next;
        KINDS.clear();
    }

    public static KeepClearConfig config()
    {
        return config;
    }

    // ------------------------------------------------------------------------------------------------------------ zones

    private static Kind kind(Structure structure, RegistryAccess access)
    {
        final Kind known = KINDS.get(structure);
        if (known != null)
        {
            return known;
        }
        final ResourceLocation key = access.registryOrThrow(Registries.STRUCTURE).getKey(structure);
        if (key == null)
        {
            return Kind.NONE;
        }
        final KeepClearConfig c = config;
        final Kind made = new Kind(c.keepsTreesOut(key), c.holds(key), c.yields(key));
        KINDS.put(structure, made);
        return made;
    }

    private static BoundingBox widen(BoundingBox b, KeepClearConfig c)
    {
        return new BoundingBox(b.minX() - c.holdPad(), b.minY() - c.holdDepth(), b.minZ() - c.holdPad(),
            b.maxX() + c.holdPad(), b.maxY() + c.holdUp(), b.maxZ() + c.holdPad());
    }

    /**
     * The pieces of the structures that matter among the starts the 3 x 3 chunks around {@code center} reference. World generation only
     * promises a region the references of the chunks next to its centre and the starts within 8 chunks of it; asking for more throws
     * (and building the crash report that comes with it is slow), so the 3 x 3 is cut to what the region holds and starts further than
     * 8 chunks from its centre are skipped: a village reaches about 7 chunks from its start, so none of them touches these chunks.
     */
    private static Zone zoneAround(WorldGenRegion region, RegistryAccess access, ChunkPos center)
    {
        final long t0 = System.nanoTime();
        try
        {
            return zoneAroundTimed(region, access, center);
        }
        finally
        {
            ZONE_NANOS.add(System.nanoTime() - t0);
            ZONES.increment();
        }
    }

    private static int distance(ChunkPos from, int x, int z)
    {
        return Math.max(Math.abs(from.x - x), Math.abs(from.z - z));
    }

    private static Zone zoneAroundTimed(WorldGenRegion region, RegistryAccess access, ChunkPos center)
    {
        final KeepClearConfig c = config;
        if (c.isEmpty())
        {
            return Zone.EMPTY;
        }
        final ChunkPos mid = region.getCenter();
        // only pieces near enough to matter: the centre chunk plus 32 blocks all around
        final BoundingBox area = new BoundingBox(center.getMinBlockX() - 32, -64, center.getMinBlockZ() - 32, center.getMaxBlockX() + 32, 320, center.getMaxBlockZ() + 32);
        final Set<StructureStart> seen = Collections.newSetFromMap(new IdentityHashMap<>());
        final Registry<Structure> structures = access.registryOrThrow(Registries.STRUCTURE);
        Zone zone = null;
        for (int dx = -1; dx <= 1; dx++)
        {
            for (int dz = -1; dz <= 1; dz++)
            {
                final int cx = center.x + dx, cz = center.z + dz;
                if (distance(mid, cx, cz) > 1)
                {
                    continue;
                }
                for (Map.Entry<Structure, LongSet> reference : region.getChunk(cx, cz, ChunkStatus.STRUCTURE_REFERENCES).getAllReferences().entrySet())
                {
                    final Kind kind = kind(reference.getKey(), access);
                    if (!kind.relevant())
                    {
                        continue;
                    }
                    for (long startChunk : reference.getValue())
                    {
                        final int sx = ChunkPos.getX(startChunk), sz = ChunkPos.getZ(startChunk);
                        if (distance(mid, sx, sz) > 8)
                        {
                            continue;
                        }
                        final StructureStart start = region.getChunk(sx, sz, ChunkStatus.STRUCTURE_STARTS).getStartForStructure(reference.getKey());
                        if (start == null || !start.isValid() || !seen.add(start))
                        {
                            continue;
                        }
                        final ResourceLocation id = structures.getKey(start.getStructure());
                        for (StructurePiece piece : start.getPieces())
                        {
                            final BoundingBox b = piece.getBoundingBox();
                            if (!b.intersects(area))
                            {
                                continue;
                            }
                            if (zone == null)
                            {
                                zone = new Zone();
                            }
                            if (kind.trees)
                            {
                                zone.trees.add(b);
                            }
                            if (kind.holds)
                            {
                                zone.holds.add(new Held(widen(b, c), id));
                            }
                        }
                    }
                }
            }
        }
        return zone == null ? Zone.EMPTY : zone;
    }

    // ------------------------------------------------------------------------------------------------------------ forests

    /** Starts the forest scope: the level TFC's forest feature is about to place trees in, at its chunk's origin. */
    public static void begin(WorldGenLevel level, BlockPos origin)
    {
        SCOPE.remove();
        if (!config.isEmpty() && level instanceof WorldGenRegion region)
        {
            SCOPE.set(new Scope(region, new ChunkPos(origin)));
        }
    }

    public static void end()
    {
        SCOPE.remove();
    }

    /** Whether a tree (or bush) whose trunk would stand at {@code pos} is refused. */
    public static boolean treeBlocked(BlockPos pos)
    {
        final Scope scope = SCOPE.get();
        if (scope == null)
        {
            return false;
        }
        final long t0 = System.nanoTime();
        final boolean blocked = blockedByTrees(scope.zone(), pos.getX(), pos.getY(), pos.getZ());
        TEST_NANOS.add(System.nanoTime() - t0);
        TESTS.increment();
        if (blocked)
        {
            count("trees_blocked");
        }
        return blocked;
    }

    /** Whether a forest block write (a fallen log's) at {@code pos} lands in a piece's box. */
    public static boolean blockWriteBlocked(BlockPos pos)
    {
        final Scope scope = SCOPE.get();
        if (scope == null)
        {
            return false;
        }
        final Zone zone = scope.zone();
        for (BoundingBox b : zone.trees)
        {
            if (b.isInside(pos))
            {
                count("logs_blocked");
                return true;
            }
        }
        return false;
    }

    private static boolean blockedByTrees(Zone zone, int x, int y, int z)
    {
        if (zone.trees.isEmpty())
        {
            return false;
        }
        final KeepClearConfig c = config;
        double best = Double.MAX_VALUE;
        for (BoundingBox b : zone.trees)
        {
            if (y < b.minY() - c.below() || y > b.maxY() + c.above())
            {
                continue;
            }
            final int dx = Math.max(Math.max(b.minX() - x, x - b.maxX()), 0);
            final int dz = Math.max(Math.max(b.minZ() - z, z - b.maxZ()), 0);
            final double d = Math.sqrt((double) dx * dx + (double) dz * dz);
            if (d < best)
            {
                best = d;
                if (best == 0)
                {
                    break;
                }
            }
        }
        if (best <= c.solid())
        {
            return true;
        }
        if (best >= c.margin())
        {
            return false;
        }
        // thinning out: the share of trunks refused falls from 1 at the solid ring to 0 at the margin
        return hash01(x, z) < (c.margin() - best) / (c.margin() - c.solid());
    }

    private static float hash01(int x, int z)
    {
        long h = x * 0x9E3779B97F4A7C15L ^ (z * 0xC2B2AE3D27D4EB4FL + 0x165667B19E3779F9L);
        h ^= h >>> 32;
        h *= 0xD6E8FEB86659FD93L;
        h ^= h >>> 32;
        h *= 0xD6E8FEB86659FD93L;
        h ^= h >>> 32;
        return ((h >>> 40) & 0xFFFFFF) / (float) 0x1000000;
    }

    /** For placed features (boulders): whether {@code pos} lies within {@code margin} blocks of a piece of a structure that keeps trees out. */
    static boolean blockedNear(WorldGenLevel level, BlockPos pos, int margin)
    {
        if (config.isEmpty() || !(level instanceof WorldGenRegion region))
        {
            return false;
        }
        try
        {
            final ChunkPos chunk = new ChunkPos(pos);
            Filtered cached = FILTERED.get();
            if (cached == null || cached.region.get() != region || cached.chunk != chunk.toLong())
            {
                cached = new Filtered(new WeakReference<>(region), chunk.toLong(),
                    zoneAround(region, region.registryAccess(), chunk));
                FILTERED.set(cached);
            }
            final Zone zone = cached.zone;
            final KeepClearConfig c = config;
            for (BoundingBox b : zone.trees)
            {
                if (pos.getY() < b.minY() - c.below() || pos.getY() > b.maxY() + c.above())
                {
                    continue;
                }
                final long dx = Math.max(Math.max(b.minX() - pos.getX(), pos.getX() - b.maxX()), 0);
                final long dz = Math.max(Math.max(b.minZ() - pos.getZ(), pos.getZ() - b.maxZ()), 0);
                if (dx * dx + dz * dz <= (long) margin * margin)
                {
                    count("boulders_blocked");
                    return true;
                }
            }
        }
        catch (RuntimeException e)
        {
            warnOnce("filter zone", e);
        }
        return false;
    }

    // ------------------------------------------------------------------------------------------------------------ overlaps

    /**
     * Whether a piece of {@code start} must not be placed: its structure yields, and the piece overlaps a held piece. Called from the
     * {@code StructureStart.placeInChunk} loop for every piece in the chunk being placed.
     */
    public static boolean suppressed(StructureStart start, StructurePiece piece, WorldGenLevel level, StructureManager manager, ChunkPos chunkPos)
    {
        // only in world generation: /place and tests place pieces into a ServerLevel, whose structure manager would generate neighbouring chunks
        if (config.isEmpty() || !(level instanceof WorldGenRegion))
        {
            return false;
        }
        try
        {
            final RegistryAccess access = level.registryAccess();
            if (!kind(start.getStructure(), access).yields)
            {
                return false;
            }
            Cached cached = CACHE.get();
            if (cached == null || cached.manager != manager || cached.chunk != chunkPos.toLong())
            {
                cached = new Cached(manager, chunkPos.toLong(), zoneAround((WorldGenRegion) level, access, chunkPos));
                CACHE.set(cached);
            }
            if (cached.zone.holds.isEmpty())
            {
                return false;
            }
            final BoundingBox pb = piece.getBoundingBox();
            for (Held held : cached.zone.holds)
            {
                if (held.box.intersects(pb))
                {
                    note(start, access, pb, held);
                    return true;
                }
            }
        }
        catch (RuntimeException e)
        {
            warnOnce("suppress", e);
        }
        return false;
    }

    private static void note(StructureStart start, RegistryAccess access, BoundingBox box, Held held)
    {
        final ResourceLocation id = access.registryOrThrow(Registries.STRUCTURE).getKey(start.getStructure());
        // a piece is placed once per chunk it spans: count and log it once
        if (!SKIPPED.add(id + " " + box))
        {
            return;
        }
        count("suppressed:" + id);
        if (LOGGED.incrementAndGet() <= LOG_LIMIT)
        {
            PackWorld.LOGGER.info("pack_world keep-clear: a piece of {} at {} is not placed: it overlaps {}", id, box, held.structure);
        }
    }

    // ------------------------------------------------------------------------------------------------------------ counters

    private static void count(String key)
    {
        STATS.computeIfAbsent(key, k -> new LongAdder()).increment();
    }

    /**
     * trees_blocked, logs_blocked, boulders_blocked, suppressed:&lt;structure id&gt;; and what it all costs: zones built (the references of 3 x 3
     * chunks read) and nanoseconds spent on them, tree tests made (trunks, bushes) and nanoseconds spent on those (the zone built for the first
     * one counts under zones).
     */
    public static Map<String, Long> stats()
    {
        final Map<String, Long> out = new TreeMap<>();
        STATS.forEach((k, v) -> out.put(k, v.sum()));
        out.put("zones", ZONES.sum());
        out.put("zone_nanos", ZONE_NANOS.sum());
        out.put("tree_tests", TESTS.sum());
        out.put("tree_test_nanos", TEST_NANOS.sum());
        return out;
    }

    public static void resetStats()
    {
        STATS.clear();
        ZONES.reset();
        ZONE_NANOS.reset();
        TESTS.reset();
        TEST_NANOS.reset();
        SKIPPED.clear();
        LOGGED.set(0);
    }

    private static void warnOnce(String where, RuntimeException e)
    {
        if (WARNED.add(where + e.getClass().getName() + e.getMessage()))
        {
            PackWorld.LOGGER.error("pack_world keep-clear failed in {} (ignored, the land is left as generated): {}", where, e.toString(), e);
        }
    }

    /** For the tests: whether a structure id keeps trees out, holds, yields. */
    public static String describe(ResourceLocation structure)
    {
        final KeepClearConfig c = config;
        return "trees=" + c.keepsTreesOut(structure) + " holds=" + c.holds(structure) + " yields=" + c.yields(structure);
    }
}
