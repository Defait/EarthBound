package pack.world.skin;

import net.dries007.tfc.common.fluids.FluidProperty;
import net.dries007.tfc.common.fluids.IFluidLoggable;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.tags.FluidTags;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.LiquidBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.material.Fluid;
import org.jetbrains.annotations.Nullable;

/**
 * Salt water for the structure skin's sea structures (docs/design.md, "Deep sea"; {@code structures.json} key {@code sea_water}).
 * The skin's table turns vanilla water into TFC river water, which is right on land and wrong in a salt ocean. In a sea structure
 * every water cell a structure wrote is TFC salt water instead:
 * <ul>
 *     <li>{@code minecraft:water} (source or flowing) becomes {@code tfc:fluid/salt_water} with the same level;</li>
 *     <li>a block the table removes (kelp, seagrass, bubble columns, sea pickles ...) leaves salt water, not air, where it held water;</li>
 *     <li>a block that was waterlogged and is mapped to a TFC block that can hold salt water ({@link IFluidLoggable}, whose
 *     {@code fluid} property allows it) keeps its water as salt water; mapped to a full block it needs none; mapped to any other
 *     block (which would turn the cell into an air pocket) it is left as the structure wrote it.</li>
 * </ul>
 */
final class SeaWater
{
    private static final ResourceLocation SALT_FLUID = ResourceLocation.fromNamespaceAndPath("tfc", "salt_water");
    private static final ResourceLocation SALT_BLOCK = ResourceLocation.fromNamespaceAndPath("tfc", "fluid/salt_water");

    private SeaWater() {}

    /** Whether the cell holds water of any kind (a water block, kelp, a waterlogged block, a bubble column). */
    static boolean wet(BlockState state)
    {
        return state.getFluidState().is(FluidTags.WATER);
    }

    @Nullable
    private static Fluid saltFluid()
    {
        return BuiltInRegistries.FLUID.getOptional(SALT_FLUID).orElse(null);
    }

    /** A salt water source block, or null when TFC's salt water is not in this pack. */
    @Nullable
    static BlockState source()
    {
        return BuiltInRegistries.BLOCK.getOptional(SALT_BLOCK).map(Block::defaultBlockState).orElse(null);
    }

    /** The state holding salt water in place of whatever water it held, or null when it cannot. */
    @Nullable
    static BlockState salted(BlockState state)
    {
        final Block block = state.getBlock();
        if (block instanceof LiquidBlock && state.getFluidState().is(FluidTags.WATER))
        {
            final BlockState salt = source();
            return salt != null && salt.hasProperty(LiquidBlock.LEVEL) && state.hasProperty(LiquidBlock.LEVEL)
                ? salt.setValue(LiquidBlock.LEVEL, state.getValue(LiquidBlock.LEVEL)) : salt;
        }
        final Fluid salt = saltFluid();
        if (salt != null && block instanceof IFluidLoggable loggable)
        {
            final FluidProperty property = loggable.getFluidProperty();
            if (state.hasProperty(property) && property.canContain(salt))
            {
                return state.setValue(property, property.keyFor(salt));
            }
        }
        return null;
    }

    /**
     * What a replacement should be so the cell stays under water: {@code replacement} with salt water in it, the salt water
     * source for an emptied cell, the replacement itself when it needs no water (a full block) or keeps vanilla water of its own,
     * and null when the only way to keep the cell wet is to leave the block as the structure wrote it.
     */
    @Nullable
    static BlockState keepWet(BlockState replacement, net.minecraft.world.level.BlockGetter level, net.minecraft.core.BlockPos pos)
    {
        if (replacement.isAir())
        {
            return source();
        }
        final BlockState salted = salted(replacement);
        if (salted != null)
        {
            return salted;
        }
        if (wet(replacement) || replacement.isCollisionShapeFullBlock(level, pos))
        {
            return replacement;
        }
        return null;
    }
}
