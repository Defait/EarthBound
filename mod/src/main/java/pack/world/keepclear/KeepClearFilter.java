package pack.world.keepclear;

import com.mojang.serialization.Codec;
import com.mojang.serialization.MapCodec;
import com.mojang.serialization.codecs.RecordCodecBuilder;
import net.minecraft.core.BlockPos;
import net.minecraft.util.RandomSource;
import net.minecraft.world.level.levelgen.placement.PlacementContext;
import net.minecraft.world.level.levelgen.placement.PlacementFilter;
import net.minecraft.world.level.levelgen.placement.PlacementModifierType;
import pack.world.PackWorld;

/**
 * {@code pack_world:keep_clear}: a placement filter that refuses positions within {@code margin} blocks of a piece of a structure that
 * keeps trees out (the config's {@code trees}; see {@link KeepClear}). For features that write blocks without asking what is there:
 * TFC's boulders overwrite whatever stands in a blob up to nine blocks across. Added to those placed features by data overrides.
 * <pre>{"type": "pack_world:keep_clear", "margin": 10}</pre>
 */
public final class KeepClearFilter extends PlacementFilter
{
    public static final MapCodec<KeepClearFilter> CODEC = RecordCodecBuilder.mapCodec(i -> i.group(
        Codec.intRange(0, 15).optionalFieldOf("margin", 8).forGetter(f -> f.margin)
    ).apply(i, KeepClearFilter::new));

    private final int margin;

    public KeepClearFilter(int margin)
    {
        this.margin = margin;
    }

    @Override
    protected boolean shouldPlace(PlacementContext context, RandomSource random, BlockPos pos)
    {
        return !KeepClear.blockedNear(context.getLevel(), pos, margin);
    }

    @Override
    public PlacementModifierType<?> type()
    {
        return PackWorld.KEEP_CLEAR.get();
    }
}
