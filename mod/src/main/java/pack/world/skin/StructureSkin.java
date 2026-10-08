package pack.world.skin;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.core.registries.Registries;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.ListTag;
import net.minecraft.nbt.Tag;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.tags.BlockTags;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.Container;
import net.minecraft.world.RandomizableContainer;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.entity.SignBlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.chunk.ChunkAccess;
import net.minecraft.world.level.chunk.ProtoChunk;
import net.minecraft.world.level.levelgen.GenerationStep;
import net.minecraft.world.level.levelgen.Heightmap;
import net.minecraft.world.level.levelgen.structure.BoundingBox;
import net.minecraft.world.level.levelgen.structure.Structure;
import net.minecraft.world.level.levelgen.structure.StructurePiece;
import net.minecraft.world.level.levelgen.structure.StructureStart;
import org.jetbrains.annotations.Nullable;
import pack.world.PackWorld;
import pack.world.materials.AlloyPolicy;
import pack.world.materials.BlockFamilies;
import pack.world.materials.LocalMaterialsProcessor;
import pack.world.materials.Materials;
import pack.world.materials.SoilSampler;

/**
 * The structure skin: after a configured structure has placed its pieces in a chunk, the blocks it wrote there are rewritten so
 * they come out as the local TFC materials, whoever built them (template, code, another mod's processor). Which blocks the
 * structure wrote is found by comparing the pieces' area before and after {@code StructureStart.placeInChunk}; natural terrain
 * never changes. Entered through {@link pack.world.mixin.StructureStartMixin}; configured by {@link SkinConfig}.
 * <ul>
 *     <li>Blocks in the config's table become their TFC target; placeholder targets (granite, the ranked woods, alfisol, yellow)
 *     become the surface rock, the climate's trees and sand at the structure's start, and the column's soil, through the same
 *     code as {@code pack_world:local_materials} (so the andesite-alloy rule applies: no raw or cobble andesite, basalt, dacite,
 *     rhyolite or diorite).</li>
 *     <li>Rough alloy rock the structure (or another mod's processor) already placed is made worked stone.</li>
 *     <li>Surface structures get a foundation under columns that hang above the ground.</li>
 * </ul>
 * A pure function of the structure start and the chunk, so any generation order gives the same blocks.
 */
public final class StructureSkin
{
    private static volatile SkinConfig config = SkinConfig.EMPTY;
    private static final ThreadLocal<Snapshot> PENDING = new ThreadLocal<>();
    private static final Map<Long, Materials.Ranked> MATERIALS = new ConcurrentHashMap<>();
    private static final Map<Structure, Optional<ResourceLocation>> APPLIES = new ConcurrentHashMap<>();
    private static final Map<String, LongAdder> STATS = new ConcurrentHashMap<>();
    private static final Map<Block, LongAdder> UNMAPPED = new ConcurrentHashMap<>();
    private static final Map<ResourceLocation, Metrics> METRICS = new ConcurrentHashMap<>();
    private static final Set<String> WARNED = ConcurrentHashMap.newKeySet();
    private static final int MAX_VOLUME = 3_000_000;
    private static volatile boolean census = false;

    private StructureSkin() {}

    /** What the tests measure per structure: blocks written, ground columns and how many hang in the air, block census before and after. */
    private static final class Metrics
    {
        final LongAdder chunks = new LongAdder(), changed = new LongAdder(), rewritten = new LongAdder(), columns = new LongAdder();
        final LongAdder floatingBefore = new LongAdder(), floatingAfter = new LongAdder(), foundation = new LongAdder();
        final Map<Block, LongAdder> before = new ConcurrentHashMap<>(), after = new ConcurrentHashMap<>();
    }

    static void setConfig(SkinConfig next)
    {
        config = next;
        APPLIES.clear();
        MATERIALS.clear();
    }

    public static SkinConfig config()
    {
        return config;
    }

    /** Turns the per-structure measurements on (they cost a heightmap read per column and a map update per block written). */
    public static void setCensus(boolean on)
    {
        census = on;
    }

    /** Counters for the tests: changed, rewritten, mapped, removed, alloy, foundation blocks and per-namespace chunks. */
    public static Map<String, Long> stats()
    {
        final Map<String, Long> out = new TreeMap<>();
        STATS.forEach((k, v) -> out.put(k, v.sum()));
        return out;
    }

    /** Blocks the structures wrote that the table has no rule for (vanilla ones are table gaps), with counts. */
    public static Map<String, Long> unmapped()
    {
        final Map<String, Long> out = new TreeMap<>();
        UNMAPPED.forEach((k, v) -> out.put(BuiltInRegistries.BLOCK.getKey(k).toString(), v.sum()));
        return out;
    }

    /**
     * The measurements per structure id: {id: {chunks, changed, rewritten, columns, floating_before, floating_after, foundation,
     * before: {block id: n}, after: {block id: n}}}. 'before' is what the structure and other mods' processors wrote, 'after' what
     * the skin left. Plain collections, for the tests' scripts.
     */
    public static Map<String, Map<String, Object>> metrics()
    {
        final Map<String, Map<String, Object>> out = new TreeMap<>();
        METRICS.forEach((id, m) -> {
            final Map<String, Object> e = new LinkedHashMap<>();
            e.put("chunks", m.chunks.sum());
            e.put("changed", m.changed.sum());
            e.put("rewritten", m.rewritten.sum());
            e.put("columns", m.columns.sum());
            e.put("floating_before", m.floatingBefore.sum());
            e.put("floating_after", m.floatingAfter.sum());
            e.put("foundation", m.foundation.sum());
            e.put("before", census(m.before));
            e.put("after", census(m.after));
            out.put(id.toString(), e);
        });
        return out;
    }

    private static Map<String, Long> census(Map<Block, LongAdder> in)
    {
        final Map<String, Long> out = new TreeMap<>();
        in.forEach((b, n) -> out.put(BuiltInRegistries.BLOCK.getKey(b).toString(), n.sum()));
        return out;
    }

    public static void resetStats()
    {
        STATS.clear();
        UNMAPPED.clear();
        METRICS.clear();
    }

    private static void count(String key, long n)
    {
        STATS.computeIfAbsent(key, k -> new LongAdder()).add(n);
    }

    private record Snapshot(StructureStart start, SkinConfig cfg, ResourceLocation id, int minX, int minY, int minZ, int dx, int dy, int dz,
                            BlockState[] before, @Nullable int[] surface, int[] pieceMinY) {}

    /** Called when a structure is about to place its pieces in a chunk. */
    public static void begin(StructureStart start, WorldGenLevel level, BoundingBox box)
    {
        PENDING.remove();
        final SkinConfig cfg = config;
        if (cfg.isEmpty())
        {
            return;
        }
        try
        {
            final Optional<ResourceLocation> id = APPLIES.computeIfAbsent(start.getStructure(), s -> {
                final ResourceLocation key = level.registryAccess().registryOrThrow(Registries.STRUCTURE).getKey(s);
                return key != null && cfg.applies(key) ? Optional.of(key) : Optional.empty();
            });
            if (id.isEmpty())
            {
                return;
            }
            int minX = Integer.MAX_VALUE, minY = Integer.MAX_VALUE, minZ = Integer.MAX_VALUE;
            int maxX = Integer.MIN_VALUE, maxY = Integer.MIN_VALUE, maxZ = Integer.MIN_VALUE;
            for (StructurePiece piece : start.getPieces())
            {
                final BoundingBox pb = piece.getBoundingBox();
                if (!pb.intersects(box))
                {
                    continue;
                }
                minX = Math.min(minX, Math.max(pb.minX(), box.minX()));
                minY = Math.min(minY, Math.max(pb.minY(), box.minY()));
                minZ = Math.min(minZ, Math.max(pb.minZ(), box.minZ()));
                maxX = Math.max(maxX, Math.min(pb.maxX(), box.maxX()));
                maxY = Math.max(maxY, Math.min(pb.maxY(), box.maxY()));
                maxZ = Math.max(maxZ, Math.min(pb.maxZ(), box.maxZ()));
            }
            if (minX > maxX)
            {
                return;
            }
            minY = Math.max(minY, level.getMinBuildHeight());
            maxY = Math.min(maxY, level.getMaxBuildHeight() - 1);
            final int dx = maxX - minX + 1, dy = maxY - minY + 1, dz = maxZ - minZ + 1;
            if (dy <= 0 || (long) dx * dy * dz > MAX_VOLUME)
            {
                count("skipped_volume", 1);
                return;
            }
            final BlockState[] before = new BlockState[dx * dy * dz];
            final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
            int i = 0;
            for (int x = 0; x < dx; x++)
            {
                for (int z = 0; z < dz; z++)
                {
                    for (int y = 0; y < dy; y++)
                    {
                        before[i++] = level.getBlockState(pos.set(minX + x, minY + y, minZ + z));
                    }
                }
            }
            int[] surface = null;
            if (census)
            {
                surface = new int[dx * dz];
                for (int x = 0; x < dx; x++)
                {
                    for (int z = 0; z < dz; z++)
                    {
                        surface[x * dz + z] = level.getHeight(Heightmap.Types.WORLD_SURFACE_WG, minX + x, minZ + z);
                    }
                }
            }
            // the lowest y of the pieces over each column: a column is part of a structure's footprint when its lowest solid block is
            // within three blocks of its piece's bottom (roofs, eaves and balconies sit higher and are not what a foundation is for)
            final int[] pieceMinY = new int[dx * dz];
            Arrays.fill(pieceMinY, Integer.MAX_VALUE);
            for (StructurePiece piece : start.getPieces())
            {
                final BoundingBox pb = piece.getBoundingBox();
                if (!pb.intersects(box))
                {
                    continue;
                }
                for (int x = Math.max(pb.minX(), minX); x <= Math.min(pb.maxX(), minX + dx - 1); x++)
                {
                    for (int z = Math.max(pb.minZ(), minZ); z <= Math.min(pb.maxZ(), minZ + dz - 1); z++)
                    {
                        final int column = (x - minX) * dz + (z - minZ);
                        pieceMinY[column] = Math.min(pieceMinY[column], pb.minY());
                    }
                }
            }
            PENDING.set(new Snapshot(start, cfg, id.get(), minX, minY, minZ, dx, dy, dz, before, surface, pieceMinY));
        }
        catch (RuntimeException e)
        {
            warnOnce("begin", e);
        }
    }

    /** Called after the structure has placed its pieces in the chunk. */
    public static void end(StructureStart start, WorldGenLevel level, BoundingBox box)
    {
        final Snapshot snap = PENDING.get();
        PENDING.remove();
        if (snap == null || snap.start != start)
        {
            return;
        }
        try
        {
            rewrite(snap, start, level, box);
        }
        catch (RuntimeException e)
        {
            warnOnce("end", e);
        }
    }

    private static void rewrite(Snapshot snap, StructureStart start, WorldGenLevel level, BoundingBox box)
    {
        final SkinConfig cfg = snap.cfg;
        final boolean dry = cfg.dryRun();
        final ServerLevel serverLevel = level.getLevel();
        final boolean placeholders = cfg.localizesPlaceholders(snap.id);
        final Materials.Ranked ranked = dry ? null : materials(serverLevel, start, cfg);
        final SoilSampler soils = new SoilSampler(level, box, "alfisol");
        final Map<ResourceLocation, Optional<Block>> blockCache = new HashMap<>();
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
        final Metrics metrics = census ? METRICS.computeIfAbsent(snap.id, k -> new Metrics()) : null;
        final boolean foundationWanted = !dry && cfg.foundation() != null && foundationApplies(cfg, start, snap.id);
        final long[] lowest = foundationWanted || metrics != null ? new long[snap.dx * snap.dz] : null;
        if (lowest != null)
        {
            Arrays.fill(lowest, Long.MAX_VALUE);
        }
        long changed = 0, rewritten = 0;
        int i = 0;
        for (int x = 0; x < snap.dx; x++)
        {
            for (int z = 0; z < snap.dz; z++)
            {
                for (int y = 0; y < snap.dy; y++, i++)
                {
                    final BlockState was = snap.before[i];
                    pos.set(snap.minX + x, snap.minY + y, snap.minZ + z);
                    BlockState now = level.getBlockState(pos);
                    if (now == was || now.isAir())
                    {
                        continue;
                    }
                    changed++;
                    if (metrics != null)
                    {
                        metrics.before.computeIfAbsent(now.getBlock(), k -> new LongAdder()).increment();
                    }
                    final SkinConfig.Rule rule = cfg.rule(now.getBlock(), placeholders);
                    if (rule == null)
                    {
                        noteUnmapped(now.getBlock());
                    }
                    else if (rule.action() != SkinConfig.Action.KEEP && !dry)
                    {
                        final BlockState replacement = replacement(rule, now, pos, ranked, soils, blockCache);
                        if (replacement != null && replacement != now)
                        {
                            replace(level, pos.immutable(), now, replacement);
                            rewritten++;
                            count(rule.action() == SkinConfig.Action.REMOVE ? "removed" : rule.action() == SkinConfig.Action.ALLOY ? "alloy" : "mapped", 1);
                            now = replacement;
                        }
                    }
                    if (metrics != null && !now.isAir())
                    {
                        metrics.after.computeIfAbsent(now.getBlock(), k -> new LongAdder()).increment();
                    }
                    if (lowest != null && !now.isAir() && now.getFluidState().isEmpty() && !now.is(BlockTags.LEAVES) && !now.is(BlockTags.LOGS) && now.isCollisionShapeFullBlock(level, pos))
                    {
                        final int column = x * snap.dz + z;
                        if (pos.getY() < lowest[column])
                        {
                            lowest[column] = pos.getY();
                        }
                    }
                }
            }
        }
        count("changed", changed);
        count("rewritten", rewritten);
        count("chunks:" + snap.id.getNamespace(), 1);
        long columns = 0, floatingBefore = 0, floatingAfter = 0, filled = 0;
        if (metrics != null && snap.surface != null)
        {
            for (int c = 0; c < lowest.length; c++)
            {
                if (footprint(snap, lowest, c))
                {
                    columns++;
                    if (lowest[c] - snap.surface[c] >= 2)
                    {
                        floatingBefore++;
                    }
                }
            }
        }
        if (foundationWanted)
        {
            filled = foundation(snap, cfg, level, ranked, soils, blockCache, lowest);
        }
        if (metrics != null && snap.surface != null)
        {
            for (int c = 0; c < lowest.length; c++)
            {
                if (footprint(snap, lowest, c) && lowest[c] - snap.surface[c] >= 2)
                {
                    floatingAfter++;
                }
            }
        }
        if (!dry && !cfg.items().isEmpty())
        {
            rewriteEntities(snap, cfg, level, box);
            rewriteContainers(snap, cfg, level, box);
        }
        if (metrics != null)
        {
            metrics.chunks.increment();
            metrics.changed.add(changed);
            metrics.rewritten.add(rewritten);
            metrics.columns.add(columns);
            metrics.floatingBefore.add(floatingBefore);
            metrics.floatingAfter.add(floatingAfter);
            metrics.foundation.add(filled);
        }
    }

    /**
     * Items baked into containers (chests, barrels, hoppers ...) that structures placed: diamonds in a treasure chest, iron tools in a
     * smithy. Containers with a loot table are skipped (their contents don't exist yet; reading them would roll the table now).
     */
    private static void rewriteContainers(Snapshot snap, SkinConfig cfg, WorldGenLevel level, BoundingBox box)
    {
        final ChunkPos chunkPos = new ChunkPos(box.minX() >> 4, box.minZ() >> 4);
        final ChunkAccess chunk = level.getChunk(chunkPos.x, chunkPos.z);
        if (!(chunk instanceof ProtoChunk proto))
        {
            return;
        }
        long changed = 0;
        for (BlockEntity entity : new ArrayList<>(proto.getBlockEntities().values()))
        {
            final BlockPos p = entity.getBlockPos();
            if (p.getX() < snap.minX || p.getX() >= snap.minX + snap.dx || p.getY() < snap.minY || p.getY() >= snap.minY + snap.dy
                || p.getZ() < snap.minZ || p.getZ() >= snap.minZ + snap.dz || !(entity instanceof Container container))
            {
                continue;
            }
            if (entity instanceof RandomizableContainer random && random.getLootTable() != null)
            {
                continue;
            }
            for (int slot = 0; slot < container.getContainerSize(); slot++)
            {
                final ItemStack stack = container.getItem(slot);
                if (stack.isEmpty())
                {
                    continue;
                }
                final String target = cfg.items().get(BuiltInRegistries.ITEM.getKey(stack.getItem()).toString());
                if (target != null)
                {
                    final Item item = BuiltInRegistries.ITEM.get(ResourceLocation.parse(target));
                    container.setItem(slot, new ItemStack(item, stack.getCount()));
                    changed++;
                }
            }
        }
        if (changed > 0)
        {
            count("container_items", changed);
        }
    }

    private static final String[] ITEM_LISTS = {"ArmorItems", "HandItems", "Items", "Inventory"};
    private static final String[] ITEM_SINGLES = {"Item", "SaddleItem", "body_armor_item"};

    /**
     * Iron, gold, diamond and chainmail gear that structures hand to armor stands, mobs and item frames (or leave lying about) is
     * lootable, so it would skip the bloomery and the bronze age: item ids are mapped through the config's table.
     */
    private static void rewriteEntities(Snapshot snap, SkinConfig cfg, WorldGenLevel level, BoundingBox box)
    {
        final ChunkPos chunkPos = new ChunkPos(box.minX() >> 4, box.minZ() >> 4);
        final ChunkAccess chunk = level.getChunk(chunkPos.x, chunkPos.z);
        if (!(chunk instanceof ProtoChunk proto))
        {
            return;
        }
        long changed = 0;
        for (CompoundTag entity : proto.getEntities())
        {
            if (entity.contains("Pos", Tag.TAG_LIST))
            {
                final ListTag pos = entity.getList("Pos", Tag.TAG_DOUBLE);
                if (pos.size() == 3)
                {
                    final int x = (int) Math.floor(pos.getDouble(0)), y = (int) Math.floor(pos.getDouble(1)), z = (int) Math.floor(pos.getDouble(2));
                    if (x < snap.minX - 3 || x > snap.minX + snap.dx + 3 || y < snap.minY - 3 || y > snap.minY + snap.dy + 3 || z < snap.minZ - 3 || z > snap.minZ + snap.dz + 3)
                    {
                        continue;
                    }
                }
            }
            changed += mapItems(entity, cfg.items());
        }
        if (changed > 0)
        {
            count("items", changed);
        }
    }

    private static long mapItems(CompoundTag entity, Map<String, String> table)
    {
        long changed = 0;
        for (String key : ITEM_LISTS)
        {
            if (entity.contains(key, Tag.TAG_LIST))
            {
                for (Tag tag : entity.getList(key, Tag.TAG_COMPOUND))
                {
                    changed += mapItem((CompoundTag) tag, table);
                }
            }
        }
        for (String key : ITEM_SINGLES)
        {
            if (entity.contains(key, Tag.TAG_COMPOUND))
            {
                changed += mapItem(entity.getCompound(key), table);
            }
        }
        if (entity.contains("Passengers", Tag.TAG_LIST))
        {
            for (Tag tag : entity.getList("Passengers", Tag.TAG_COMPOUND))
            {
                changed += mapItems((CompoundTag) tag, table);
            }
        }
        return changed;
    }

    private static long mapItem(CompoundTag item, Map<String, String> table)
    {
        final String target = table.get(item.getString("id"));
        if (target == null)
        {
            return 0;
        }
        item.putString("id", target);
        item.remove("components");
        return 1;
    }

    @Nullable
    private static BlockState replacement(SkinConfig.Rule rule, BlockState now, BlockPos pos, Materials.Ranked ranked, SoilSampler soils,
                                          Map<ResourceLocation, Optional<Block>> blockCache)
    {
        switch (rule.action())
        {
            case REMOVE:
                return Blocks.AIR.defaultBlockState();
            case ALLOY:
            {
                final BlockFamilies.Parsed parsed = rule.parsed();
                final Materials same = new Materials(parsed.material(), ranked.wood(0), ranked.sand(), ranked.fromTfc());
                return LocalMaterialsProcessor.map(now, rule.targetId(), parsed, same, null, null, AlloyPolicy.WORK, "granite", blockCache);
            }
            case MAP:
            {
                final Block target = rule.target();
                final BlockFamilies.Parsed parsed = rule.parsed();
                final BlockState carried = target == now.getBlock() ? now : BlockFamilies.copyProperties(now, target.defaultBlockState());
                if (parsed == null)
                {
                    return carried;
                }
                final String soil = parsed.kind() == BlockFamilies.Kind.SOIL ? soils.at(pos) : null;
                return LocalMaterialsProcessor.map(carried, rule.targetId(), parsed, ranked.at(rule.woodRank()), soil, null, AlloyPolicy.WORK, "granite", blockCache);
            }
            default:
                return null;
        }
    }

    private static void replace(WorldGenLevel level, BlockPos pos, BlockState old, BlockState next)
    {
        CompoundTag saved = null;
        if (old.hasBlockEntity())
        {
            final BlockEntity oldEntity = level.getBlockEntity(pos);
            if (oldEntity != null && next.hasBlockEntity() && (oldEntity instanceof RandomizableContainer || oldEntity instanceof SignBlockEntity))
            {
                saved = oldEntity.saveWithFullMetadata(level.registryAccess());
            }
            // a stale block entity object would outlive the block it belonged to
            final ChunkAccess chunk = level.getChunk(pos);
            chunk.removeBlockEntity(pos);
        }
        level.setBlock(pos, next, 2 | 16);
        if (saved != null)
        {
            final BlockEntity entity = level.getBlockEntity(pos);
            if (entity instanceof RandomizableContainer || entity instanceof SignBlockEntity)
            {
                saved.remove("id");
                saved.remove("x");
                saved.remove("y");
                saved.remove("z");
                entity.loadWithComponents(saved, level.registryAccess());
            }
        }
    }

    /** Whether a column's lowest solid block is the structure's footprint (within three blocks of its piece's bottom), not a roof or a balcony. */
    private static boolean footprint(Snapshot snap, long[] lowest, int column)
    {
        return lowest[column] != Long.MAX_VALUE && lowest[column] <= (long) snap.pieceMinY[column] + 3;
    }

    private static boolean foundationApplies(SkinConfig cfg, StructureStart start, ResourceLocation id)
    {
        final SkinConfig.Foundation f = cfg.foundation();
        if (f == null || f.exclude().contains(id))
        {
            return false;
        }
        final GenerationStep.Decoration step = start.getStructure().step();
        return f.steps().contains(step.getName());
    }

    /**
     * Fills under columns whose lowest solid block hangs above the ground (leaves and logs don't count: a canopy and its branches aren't a floor), up to the
     * configured depth, inside this chunk.
     * {@code lowest} (per column, the y of the lowest solid block written) is updated to where the fill ended.
     *
     * @return blocks placed
     */
    private static long foundation(Snapshot snap, SkinConfig cfg, WorldGenLevel level, Materials.Ranked ranked, SoilSampler soils,
                                   Map<ResourceLocation, Optional<Block>> blockCache, long[] lowest)
    {
        final SkinConfig.Foundation f = cfg.foundation();
        final boolean dirt = f.variant().equals("dirt");
        final ResourceLocation placeholder = ResourceLocation.fromNamespaceAndPath("tfc", "rock/raw/granite");
        final BlockState rockFill = dirt ? null : LocalMaterialsProcessor.map(BuiltInRegistries.BLOCK.get(placeholder).defaultBlockState(),
            placeholder, BlockFamilies.parse(placeholder), ranked.at(0), null, f.variant(), AlloyPolicy.WORK, "granite", blockCache);
        final BlockPos.MutableBlockPos cursor = new BlockPos.MutableBlockPos();
        long filled = 0;
        for (int x = 0; x < snap.dx; x++)
        {
            for (int z = 0; z < snap.dz; z++)
            {
                final int column = x * snap.dz + z;
                final long low = lowest[column];
                if (!footprint(snap, lowest, column))
                {
                    continue;
                }
                final int wx = snap.minX + x, wz = snap.minZ + z;
                BlockState fill = rockFill;
                if (dirt)
                {
                    fill = BuiltInRegistries.BLOCK.getOptional(ResourceLocation.fromNamespaceAndPath("tfc", "dirt/" + soils.at(cursor.set(wx, (int) low, wz))))
                        .map(Block::defaultBlockState).orElse(null);
                }
                if (fill == null)
                {
                    continue;
                }
                cursor.set(wx, (int) low - 1, wz);
                for (int depth = 0; depth < f.maxDepth() && cursor.getY() >= level.getMinBuildHeight(); depth++)
                {
                    final BlockState there = level.getBlockState(cursor);
                    if (!there.getFluidState().isEmpty() || !(there.isAir() || there.canBeReplaced()))
                    {
                        break;
                    }
                    level.setBlock(cursor, fill, 2 | 16);
                    filled++;
                    lowest[column] = cursor.getY();
                    cursor.move(0, -1, 0);
                }
            }
        }
        if (filled > 0)
        {
            count("foundation", filled);
        }
        return filled;
    }

    private static Materials.Ranked materials(ServerLevel level, StructureStart start, SkinConfig cfg)
    {
        final BoundingBox bb = start.getBoundingBox();
        final GenerationStep.Decoration step = start.getStructure().step();
        final boolean underground = step == GenerationStep.Decoration.UNDERGROUND_STRUCTURES || step == GenerationStep.Decoration.UNDERGROUND_DECORATION
            || step == GenerationStep.Decoration.UNDERGROUND_ORES;
        final int y = underground ? 72 : Math.max(bb.minY(), 63);
        final BlockPos anchor = new BlockPos(start.getChunkPos().getMiddleBlockX(), y, start.getChunkPos().getMiddleBlockZ());
        if (MATERIALS.size() > 512)
        {
            MATERIALS.clear();
        }
        final long key = start.getChunkPos().toLong() * 31 + level.dimension().location().hashCode() + 7L * y;
        return MATERIALS.computeIfAbsent(key, k -> Materials.resolveRanked(level, anchor, cfg.woods().size()));
    }

    private static void noteUnmapped(Block block)
    {
        UNMAPPED.computeIfAbsent(block, k -> new LongAdder()).increment();
    }

    private static void warnOnce(String where, RuntimeException e)
    {
        if (WARNED.add(where + e.getClass().getName() + e.getMessage()))
        {
            PackWorld.LOGGER.error("pack_world structure skin failed in {} (structures are left as they were generated): {}", where, e.toString(), e);
        }
    }
}
