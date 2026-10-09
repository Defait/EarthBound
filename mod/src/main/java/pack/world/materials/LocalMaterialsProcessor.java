package pack.world.materials;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import com.mojang.serialization.Codec;
import com.mojang.serialization.DataResult;
import com.mojang.serialization.MapCodec;
import com.mojang.serialization.codecs.RecordCodecBuilder;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.NbtUtils;
import net.minecraft.nbt.Tag;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.LevelReader;
import net.minecraft.world.level.ServerLevelAccessor;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.levelgen.structure.BoundingBox;
import net.minecraft.world.level.levelgen.structure.templatesystem.StructurePlaceSettings;
import net.minecraft.world.level.levelgen.structure.templatesystem.StructureProcessor;
import net.minecraft.world.level.levelgen.structure.templatesystem.StructureProcessorType;
import net.minecraft.world.level.levelgen.structure.templatesystem.StructureTemplate.StructureBlockInfo;
import org.jetbrains.annotations.Nullable;
import pack.world.PackWorld;

/**
 * {@code pack_world:local_materials}: templates are built from TFC blocks of one placeholder rock, wood, soil and sand colour;
 * this rewrites the material part of each block id to the local one and copies the block state property by property, so
 * stairs, slabs, walls, log axes and TFC's {@code fluid} property survive (rotation is applied by vanilla after processing).
 * <p>
 * Everything happens in {@link #finalizeProcessing}, once per template per chunk being placed, after every processor's
 * {@code processBlock} (so vanilla {@code block_rot} or {@code rule} decay runs first, on placeholders).
 * <p>
 * Besides TFC's blocks it maps Roads and Roofs' ({@code rnr:}): shingles to the wood, road rock to the rock, tamped soil to the soil;
 * and the camouflage of Framed Blocks (the {@code camo} and {@code camo_two} of their block entities), so a framed wall looks like the
 * local wood or rock. With {@code wood_ranks} a structure uses several woods at once: the placeholder woods are the climate's
 * best-fitting tree, its second and its third (a village of one oak and two stand-ins), see {@link Materials.Ranked}.
 */
public final class LocalMaterialsProcessor extends StructureProcessor
{
    public record Placeholders(String rock, String wood, String soil, String sand)
    {
        public static final Placeholders DEFAULT = new Placeholders("granite", "oak", "alfisol", "yellow");
        public static final Codec<Placeholders> CODEC = RecordCodecBuilder.create(i -> i.group(
            name(BlockFamilies.ROCKS, false).optionalFieldOf("rock", "granite").forGetter(Placeholders::rock),
            name(BlockFamilies.WOODS, false).optionalFieldOf("wood", "oak").forGetter(Placeholders::wood),
            name(BlockFamilies.SOILS, false).optionalFieldOf("soil", "alfisol").forGetter(Placeholders::soil),
            name(BlockFamilies.SANDS, false).optionalFieldOf("sand", "yellow").forGetter(Placeholders::sand)
        ).apply(i, Placeholders::new));
    }

    /** Per-block weathering of rock bricks and cobble, seeded by position. */
    public record Decay(float cracked, float mossy, float missing)
    {
        public static final Codec<Decay> CODEC = RecordCodecBuilder.create(i -> i.group(
            Codec.floatRange(0, 1).optionalFieldOf("cracked", 0f).forGetter(Decay::cracked),
            Codec.floatRange(0, 1).optionalFieldOf("mossy", 0f).forGetter(Decay::mossy),
            Codec.floatRange(0, 1).optionalFieldOf("missing", 0f).forGetter(Decay::missing)
        ).apply(i, Decay::new));
    }

    /**
     * Fill under a piece down to the natural ground, so pieces on slopes don't float (TFC's beard fills only ~2 blocks).
     * With {@code ground} (the template layer that replaces the topsoil), every column whose lowest solid block is at or below
     * that layer is filled; without it, only blocks in the template's lowest layer are.
     */
    public record Foundation(int maxDepth, String variant, int ground)
    {
        public static final Codec<Foundation> CODEC = RecordCodecBuilder.create(i -> i.group(
            Codec.intRange(1, 32).optionalFieldOf("max_depth", 8).forGetter(Foundation::maxDepth),
            Codec.STRING.validate(v -> Set.of("raw", "cobble", "smooth", "bricks", "mossy_cobble", "dirt").contains(v) ? DataResult.success(v) :
                DataResult.error(() -> "foundation variant must be raw, cobble, smooth, bricks, mossy_cobble or dirt (the column's soil): " + v))
                .optionalFieldOf("variant", "raw").forGetter(Foundation::variant),
            Codec.intRange(-1, 64).optionalFieldOf("ground", -1).forGetter(Foundation::ground)
        ).apply(i, Foundation::new));
    }

    public static final MapCodec<LocalMaterialsProcessor> CODEC = RecordCodecBuilder.mapCodec(i -> i.group(
        Placeholders.CODEC.optionalFieldOf("placeholders", Placeholders.DEFAULT).forGetter(p -> p.placeholders),
        name(BlockFamilies.ROCKS, true).optionalFieldOf("rock", "local").forGetter(p -> p.choice.rock()),
        name(BlockFamilies.WOODS, true).optionalFieldOf("wood", "local").forGetter(p -> p.choice.wood()),
        name(BlockFamilies.SOILS, true).optionalFieldOf("soil", "local").forGetter(p -> p.soil),
        name(BlockFamilies.SANDS, true).optionalFieldOf("sand", "local").forGetter(p -> p.choice.sand()),
        Codec.intRange(1, 8).optionalFieldOf("wood_variety", 2).forGetter(p -> p.choice.woodVariety()),
        AlloyPolicy.CODEC.optionalFieldOf("alloy_rock", AlloyPolicy.WORK).forGetter(p -> p.choice.policy()),
        name(BlockFamilies.ROCKS, false).optionalFieldOf("substitute_rock", "granite").forGetter(p -> p.choice.substituteRock()),
        Decay.CODEC.optionalFieldOf("decay").forGetter(p -> p.decay),
        Foundation.CODEC.optionalFieldOf("foundation").forGetter(p -> p.foundation),
        name(BlockFamilies.WOODS, false).listOf().validate(LocalMaterialsProcessor::checkRanks).optionalFieldOf("wood_ranks", List.of()).forGetter(p -> p.woodRanks),
        Codec.STRING.listOf().validate(LocalMaterialsProcessor::checkModded).optionalFieldOf("modded_woods").forGetter(p -> p.moddedWoods)
    ).apply(i, LocalMaterialsProcessor::new));

    private static final int CACHE_LIMIT = 1024;
    private static final Set<String> WARNED = ConcurrentHashMap.newKeySet();

    private final Placeholders placeholders;
    private final Materials.Choice choice;
    private final String soil;
    private final Optional<Decay> decay;
    private final Optional<Foundation> foundation;
    private final List<String> woodRanks;
    private final Optional<List<String>> moddedWoods;
    private final boolean modded;
    private final Map<Long, Materials> cache = new ConcurrentHashMap<>();
    private final Map<Long, Materials.Ranked> rankCache = new ConcurrentHashMap<>();

    public LocalMaterialsProcessor(Placeholders placeholders, String rock, String wood, String soil, String sand, int woodVariety,
                                   AlloyPolicy policy, String substituteRock, Optional<Decay> decay, Optional<Foundation> foundation,
                                   List<String> woodRanks, Optional<List<String>> moddedWoods)
    {
        this.placeholders = placeholders;
        this.choice = new Materials.Choice(rock, wood, sand, woodVariety, policy, substituteRock);
        this.soil = soil;
        this.decay = decay;
        this.foundation = foundation;
        this.woodRanks = List.copyOf(woodRanks);
        this.moddedWoods = moddedWoods;
        // ArborFirmaCraft's trees count for ranked woods unless the processor says otherwise (the wood of one tree is TFC's either way)
        this.modded = !woodRanks.isEmpty() && moddedWoods.map(l -> l.contains("afc")).orElse(true);
    }

    private static DataResult<List<String>> checkRanks(List<String> ranks)
    {
        if (ranks.size() > 8 || ranks.stream().distinct().count() != ranks.size())
        {
            return DataResult.error(() -> "wood_ranks: up to 8 distinct woods: " + ranks);
        }
        return DataResult.success(ranks);
    }

    private static DataResult<List<String>> checkModded(List<String> mods)
    {
        return mods.stream().allMatch("afc"::equals) ? DataResult.success(mods) : DataResult.error(() -> "modded_woods: only afc is known: " + mods);
    }

    @Override
    protected StructureProcessorType<?> getType()
    {
        return PackWorld.LOCAL_MATERIALS.get();
    }

    @Override
    public List<StructureBlockInfo> finalizeProcessing(ServerLevelAccessor level, BlockPos offset, BlockPos pos, List<StructureBlockInfo> originals,
                                                       List<StructureBlockInfo> processed, StructurePlaceSettings settings)
    {
        // One choice per structure: the anchor is the pivot (pos), which StructureStart.placeInChunk passes to every piece of a jigsaw
        // structure as the centre of the start piece at its lowest y, so all pieces (and every chunk they are placed in) agree.
        final Materials.Ranked ranked = woodRanks.isEmpty() ? null : ranked(level.getLevel(), pos);
        final Materials materials = ranked != null ? ranked.at(0) : materials(level.getLevel(), pos);
        final BoundingBox box = settings.getBoundingBox();
        final SoilSampler soils = new SoilSampler(level, box, soil.equals("local") ? placeholders.soil() : soil);
        final Map<ResourceLocation, Optional<Block>> blocks = new HashMap<>();
        final List<StructureBlockInfo> out = new ArrayList<>(processed.size() + 32);
        int minY = Integer.MAX_VALUE;
        for (StructureBlockInfo info : processed)
        {
            if (!info.state().isAir())
            {
                minY = Math.min(minY, info.pos().getY());
            }
        }
        for (StructureBlockInfo info : processed)
        {
            final BlockState state = info.state();
            final ResourceLocation id = BuiltInRegistries.BLOCK.getKey(state.getBlock());
            final BlockFamilies.Parsed parsed = BlockFamilies.parseLocal(id);
            if (parsed == null || !isPlaceholder(parsed))
            {
                out.add("framedblocks".equals(id.getNamespace()) && info.nbt() != null ? camo(info, ranked, materials, soils, blocks) : info);
                continue;
            }
            final String soilHere = parsed.kind() == BlockFamilies.Kind.SOIL ? (soil.equals("local") ? soils.at(info.pos()) : soil) : null;
            final String variant = parsed.kind() == BlockFamilies.Kind.ROCK ? decayed(parsed.variant(), info.pos()) : null;
            final BlockState mapped = map(state, id, parsed, materialsFor(parsed, ranked, materials), soilHere, variant, choice.policy(), choice.substituteRock(), blocks);
            out.add(mapped == state ? info : new StructureBlockInfo(info.pos(), mapped, mapped.hasBlockEntity() ? info.nbt() : null));
        }
        if (foundation.isPresent() && box != null && minY != Integer.MAX_VALUE)
        {
            addFoundation(level, box, out, minY, offset.getY(), materials, soils, blocks);
        }
        return out;
    }

    /** With wood ranks, a wood block is a placeholder when its wood is one of the ranks; else when it is the placeholder wood. */
    private boolean isPlaceholder(BlockFamilies.Parsed parsed)
    {
        if (parsed.kind() == BlockFamilies.Kind.WOOD && !woodRanks.isEmpty())
        {
            return woodRanks.contains(parsed.material());
        }
        return parsed.material().equals(placeholderFor(parsed.kind()));
    }

    /** The materials for one block: its rank's wood with wood ranks, else the structure's. */
    private Materials materialsFor(BlockFamilies.Parsed parsed, @Nullable Materials.Ranked ranked, Materials materials)
    {
        return ranked != null && parsed.kind() == BlockFamilies.Kind.WOOD ? ranked.at(woodRanks.indexOf(parsed.material())) : materials;
    }

    private static final String[] CAMO_KEYS = {"camo", "camo_two"};

    /**
     * Framed Blocks keep their camouflage block in the block entity ({@code camo}, and {@code camo_two} for double blocks) as a block
     * state: when that block is a placeholder it becomes the local one, by the same mapping as a placed block. The template's own tag is
     * shared between placements, so it is copied before it is changed.
     */
    private StructureBlockInfo camo(StructureBlockInfo info, @Nullable Materials.Ranked ranked, Materials materials, SoilSampler soils,
                                    Map<ResourceLocation, Optional<Block>> blocks)
    {
        final CompoundTag tag = info.nbt();
        CompoundTag copy = null;
        for (String key : CAMO_KEYS)
        {
            if (!tag.contains(key, Tag.TAG_COMPOUND))
            {
                continue;
            }
            final CompoundTag camo = tag.getCompound(key);
            if (!"framedblocks:block".equals(camo.getString("type")) || !camo.contains("state", Tag.TAG_COMPOUND))
            {
                continue;
            }
            final BlockState before = NbtUtils.readBlockState(BuiltInRegistries.BLOCK.asLookup(), camo.getCompound("state"));
            if (before.isAir())
            {
                continue;
            }
            final ResourceLocation id = BuiltInRegistries.BLOCK.getKey(before.getBlock());
            final BlockFamilies.Parsed parsed = BlockFamilies.parseLocal(id);
            if (parsed == null || !isPlaceholder(parsed))
            {
                continue;
            }
            final String soilHere = parsed.kind() == BlockFamilies.Kind.SOIL ? (soil.equals("local") ? soils.at(info.pos()) : soil) : null;
            BlockState after = map(before, id, parsed, materialsFor(parsed, ranked, materials), soilHere, null, choice.policy(), choice.substituteRock(), blocks);
            if (after.isAir())
            {
                after = block(ResourceLocation.fromNamespaceAndPath("tfc", "rock/smooth/" + materials.rock()), blocks).map(Block::defaultBlockState).orElse(before);
            }
            if (after != before)
            {
                if (copy == null)
                {
                    copy = tag.copy();
                }
                copy.getCompound(key).put("state", NbtUtils.writeBlockState(after));
            }
        }
        return copy == null ? info : new StructureBlockInfo(info.pos(), info.state(), copy);
    }

    private String placeholderFor(BlockFamilies.Kind kind)
    {
        return switch (kind)
        {
            case ROCK, ORE -> placeholders.rock();
            case WOOD -> placeholders.wood();
            case SOIL -> placeholders.soil();
            case SAND -> placeholders.sand();
        };
    }

    Materials materials(ServerLevel level, BlockPos anchor)
    {
        if (cache.size() > CACHE_LIMIT)
        {
            cache.clear();
        }
        final long key = anchor.asLong() * 31 + level.dimension().location().hashCode();
        return cache.computeIfAbsent(key, k -> {
            final Materials m = Materials.resolve(level, anchor, choice);
            if (!m.fromTfc())
            {
                warnOnce("no TFC generator in " + level.dimension().location() + ": local_materials uses its fallbacks there");
            }
            return m;
        });
    }

    /**
     * The structure's materials with wood ranks: the surface rock and sand at the anchor, the climate's trees best first, and the
     * processor's own fixed choices and alloy policy applied.
     */
    Materials.Ranked ranked(ServerLevel level, BlockPos anchor)
    {
        if (rankCache.size() > CACHE_LIMIT)
        {
            rankCache.clear();
        }
        final long key = anchor.asLong() * 31 + level.dimension().location().hashCode();
        return rankCache.computeIfAbsent(key, k -> {
            final Materials.Ranked r = Materials.resolveRanked(level, anchor, woodRanks.size(), modded);
            if (!r.fromTfc())
            {
                warnOnce("no TFC generator in " + level.dimension().location() + ": local_materials uses its fallbacks there");
            }
            String rock = choice.localRock() ? (r.fromTfc() ? r.rock() : choice.substituteRock()) : choice.rock();
            if (choice.policy() == AlloyPolicy.SUBSTITUTE && BlockFamilies.ALLOY_ROCKS.contains(rock))
            {
                rock = choice.substituteRock();
            }
            return new Materials.Ranked(rock, choice.localSand() ? r.sand() : choice.sand(), choice.localWood() ? r.woods() : List.of(choice.wood()), r.fromTfc());
        });
    }

    /** Bricks may crack, grow moss or go missing; cobble may grow moss or go missing. "air" removes the block. */
    @Nullable
    private String decayed(String variant, BlockPos pos)
    {
        if (decay.isEmpty())
        {
            return variant;
        }
        final Decay d = decay.get();
        final boolean bricks = variant.equals("bricks");
        final boolean cobble = variant.equals("cobble");
        if (!bricks && !cobble)
        {
            return variant;
        }
        final long seed = BlockFamilies.positionSeed(pos.getX(), pos.getY(), pos.getZ());
        final float r = ((seed >>> 11) & 0xFFFFFF) / (float) 0x1000000;
        if (r < d.missing())
        {
            return "air";
        }
        if (r < d.missing() + d.mossy())
        {
            return bricks ? "mossy_bricks" : "mossy_cobble";
        }
        if (bricks && r < d.missing() + d.mossy() + d.cracked())
        {
            return "cracked_bricks";
        }
        return variant;
    }

    /**
     * The mapped state for one placeholder block. Shared with {@link pack.world.api.PackWorldApi#mapId} so the palette test
     * checks exactly what world generation does.
     *
     * @param soilHere the soil order for soil blocks
     * @param variant  the (possibly decayed) rock variant for rock blocks; "air" removes the block
     */
    public static BlockState map(BlockState state, ResourceLocation id, BlockFamilies.Parsed parsed, Materials m, @Nullable String soilHere,
                                 @Nullable String variant, AlloyPolicy policy, String substituteRock, Map<ResourceLocation, Optional<Block>> blocks)
    {
        final ResourceLocation target;
        switch (parsed.kind())
        {
            case ROCK ->
            {
                String v = variant == null ? parsed.variant() : variant;
                String rock = m.rock();
                if (v.equals("air"))
                {
                    return Blocks.AIR.defaultBlockState();
                }
                if (policy == AlloyPolicy.WORK && BlockFamilies.ALLOY_ROCKS.contains(rock))
                {
                    if (v.equals("anvil"))
                    {
                        rock = BlockFamilies.IGNEOUS.contains(substituteRock) && !BlockFamilies.ALLOY_ROCKS.contains(substituteRock) ? substituteRock : "gabbro";
                    }
                    else if (BlockFamilies.WORKED.containsKey(v))
                    {
                        final Optional<String> worked = BlockFamilies.WORKED.get(v);
                        if (worked.isEmpty())
                        {
                            return Blocks.AIR.defaultBlockState();
                        }
                        v = worked.get();
                    }
                }
                ResourceLocation candidate = parsed.withRock(v, rock);
                if (block(candidate, blocks).isEmpty() && BlockFamilies.MISSING_VARIANT.containsKey(v))
                {
                    candidate = parsed.withRock(BlockFamilies.MISSING_VARIANT.get(v), rock);
                }
                target = candidate;
            }
            case ORE -> target = parsed.with(m.rock());
            case WOOD -> target = woodTarget(parsed, m.wood());
            case SOIL -> target = parsed.with(soilHere == null ? parsed.material() : soilHere);
            case SAND -> target = parsed.with(m.sand());
            default -> throw new IllegalStateException();
        }
        Optional<Block> block = block(target, blocks);
        if (block.isEmpty() && parsed.kind() == BlockFamilies.Kind.WOOD && m.wood().indexOf(':') >= 0)
        {
            // a modded wood lacking this block: the TFC wood of about the same climate
            final String bare = m.wood().substring(m.wood().indexOf(':') + 1);
            final ResourceLocation fallback = parsed.with(AFC_TO_TFC.getOrDefault(bare, "oak"));
            warnOnce("local_materials: " + target + " doesn't exist; using " + fallback);
            block = block(fallback, blocks);
        }
        if (block.isEmpty())
        {
            warnOnce("local_materials: " + target + " doesn't exist; kept " + id);
            return state;
        }
        return block.get() == state.getBlock() ? state : BlockFamilies.copyProperties(state, block.get().defaultBlockState());
    }

    /** What a modded wood falls back to where one of its blocks is missing (the TFC wood of about the same climate window). */
    static final Map<String, String> AFC_TO_TFC = Map.ofEntries(Map.entry("araucaria", "pine"), Map.entry("baobab", "acacia"), Map.entry("beech", "hickory"),
        Map.entry("cypress", "willow"), Map.entry("eucalyptus", "ash"), Map.entry("fig", "kapok"), Map.entry("ginkgo", "maple"), Map.entry("hevea", "kapok"),
        Map.entry("ipe", "rosewood"), Map.entry("ironwood", "blackwood"), Map.entry("mahoe", "kapok"), Map.entry("mahogany", "rosewood"),
        Map.entry("teak", "rosewood"), Map.entry("tualang", "kapok"));

    /**
     * The block id of a wood family block for a wood string: {@code "oak"} is TFC's; {@code "afc:mahogany"} swaps TFC's namespace for
     * ArborFirmaCraft's (the same path with the wood replaced), and Roads and Roofs' shingles stay in {@code rnr} with the bare name.
     */
    static ResourceLocation woodTarget(BlockFamilies.Parsed parsed, String wood)
    {
        final int colon = wood.indexOf(':');
        if (colon < 0)
        {
            return parsed.with(wood);
        }
        final String bare = wood.substring(colon + 1);
        return "tfc".equals(parsed.namespace())
            ? ResourceLocation.fromNamespaceAndPath(wood.substring(0, colon), parsed.prefix() + parsed.joiner() + bare + parsed.shape())
            : parsed.with(bare);
    }

    private void addFoundation(LevelReader level, BoundingBox box, List<StructureBlockInfo> out, int minY, int originY, Materials m, SoilSampler soils,
                               Map<ResourceLocation, Optional<Block>> blocks)
    {
        final Foundation f = foundation.orElseThrow();
        final boolean dirt = f.variant().equals("dirt");
        final BlockState rockFill = dirt ? null : foundationState(f.variant(), m, blocks);
        if (!dirt && rockFill == null)
        {
            return;
        }
        // The lowest solid block of each column (all of them with a ground layer, else only the template's lowest layer).
        final Map<Long, StructureBlockInfo> lowest = new HashMap<>();
        final int top = f.ground() >= 0 ? originY + f.ground() : minY;
        for (StructureBlockInfo info : out)
        {
            final BlockPos p = info.pos();
            if (info.state().isAir() || p.getY() > top || !box.isInside(p))
            {
                continue;
            }
            final long key = BlockPos.asLong(p.getX(), 0, p.getZ());
            final StructureBlockInfo was = lowest.get(key);
            if (was == null || p.getY() < was.pos().getY())
            {
                lowest.put(key, info);
            }
        }
        final List<StructureBlockInfo> added = new ArrayList<>();
        final BlockPos.MutableBlockPos cursor = new BlockPos.MutableBlockPos();
        for (StructureBlockInfo info : lowest.values())
        {
            final BlockPos p = info.pos();
            if ((f.ground() < 0 && p.getY() != minY) || !info.state().isCollisionShapeFullBlock(level, p))
            {
                continue;
            }
            final BlockState fill = dirt
                ? block(ResourceLocation.fromNamespaceAndPath("tfc", "dirt/" + (soil.equals("local") ? soils.at(p) : soil)), blocks).map(Block::defaultBlockState).orElse(null)
                : rockFill;
            if (fill == null)
            {
                continue;
            }
            cursor.set(p).move(Direction.DOWN);
            for (int depth = 0; depth < f.maxDepth() && box.isInside(cursor); depth++)
            {
                final BlockState there = level.getBlockState(cursor);
                if (!there.getFluidState().isEmpty() || !(there.isAir() || there.canBeReplaced()))
                {
                    break;
                }
                added.add(new StructureBlockInfo(cursor.immutable(), fill, null));
                cursor.move(Direction.DOWN);
            }
        }
        out.addAll(added);
    }

    @Nullable
    private BlockState foundationState(String variant, Materials m, Map<ResourceLocation, Optional<Block>> blocks)
    {
        String v = variant;
        if (choice.policy() == AlloyPolicy.WORK && BlockFamilies.ALLOY_ROCKS.contains(m.rock()))
        {
            v = BlockFamilies.WORKED.getOrDefault(v, Optional.of(v)).orElse("smooth");
        }
        return block(ResourceLocation.fromNamespaceAndPath("tfc", "rock/" + v + "/" + m.rock()), blocks).map(Block::defaultBlockState).orElse(null);
    }

    private static Optional<Block> block(ResourceLocation id, Map<ResourceLocation, Optional<Block>> blocks)
    {
        return blocks.computeIfAbsent(id, BuiltInRegistries.BLOCK::getOptional);
    }

    static void warnOnce(String message)
    {
        if (WARNED.add(message))
        {
            PackWorld.LOGGER.warn(message);
        }
    }

    private static Codec<String> name(List<String> allowed, boolean local)
    {
        return Codec.STRING.validate(s -> (local && s.equals("local")) || allowed.contains(s) ? DataResult.success(s)
            : DataResult.error(() -> "expected " + (local ? "\"local\" or " : "") + "one of " + allowed + ": " + s));
    }

    public Placeholders placeholders()
    {
        return placeholders;
    }

    public Materials.Choice choice()
    {
        return choice;
    }
}
