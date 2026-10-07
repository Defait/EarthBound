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
        Foundation.CODEC.optionalFieldOf("foundation").forGetter(p -> p.foundation)
    ).apply(i, LocalMaterialsProcessor::new));

    private static final int CACHE_LIMIT = 1024;
    private static final Set<String> WARNED = ConcurrentHashMap.newKeySet();

    private final Placeholders placeholders;
    private final Materials.Choice choice;
    private final String soil;
    private final Optional<Decay> decay;
    private final Optional<Foundation> foundation;
    private final Map<Long, Materials> cache = new ConcurrentHashMap<>();

    public LocalMaterialsProcessor(Placeholders placeholders, String rock, String wood, String soil, String sand, int woodVariety,
                                   AlloyPolicy policy, String substituteRock, Optional<Decay> decay, Optional<Foundation> foundation)
    {
        this.placeholders = placeholders;
        this.choice = new Materials.Choice(rock, wood, sand, woodVariety, policy, substituteRock);
        this.soil = soil;
        this.decay = decay;
        this.foundation = foundation;
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
        final Materials materials = materials(level.getLevel(), offset);
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
            final BlockFamilies.Parsed parsed = BlockFamilies.parse(id);
            if (parsed == null || !parsed.material().equals(placeholderFor(parsed.kind())))
            {
                out.add(info);
                continue;
            }
            final String soilHere = parsed.kind() == BlockFamilies.Kind.SOIL ? (soil.equals("local") ? soils.at(info.pos()) : soil) : null;
            final String variant = parsed.kind() == BlockFamilies.Kind.ROCK ? decayed(parsed.variant(), info.pos()) : null;
            final BlockState mapped = map(state, id, parsed, materials, soilHere, variant, choice.policy(), choice.substituteRock(), blocks);
            out.add(mapped == state ? info : new StructureBlockInfo(info.pos(), mapped, mapped.hasBlockEntity() ? info.nbt() : null));
        }
        if (foundation.isPresent() && box != null && minY != Integer.MAX_VALUE)
        {
            addFoundation(level, box, out, minY, offset.getY(), materials, soils, blocks);
        }
        return out;
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
            case WOOD -> target = parsed.with(m.wood());
            case SOIL -> target = parsed.with(soilHere == null ? parsed.material() : soilHere);
            case SAND -> target = parsed.with(m.sand());
            default -> throw new IllegalStateException();
        }
        final Optional<Block> block = block(target, blocks);
        if (block.isEmpty())
        {
            warnOnce("local_materials: " + target + " doesn't exist; kept " + id);
            return state;
        }
        return block.get() == state.getBlock() ? state : BlockFamilies.copyProperties(state, block.get().defaultBlockState());
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
