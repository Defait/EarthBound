package pack.world.mixin;

import com.llamalad7.mixinextras.injector.wrapmethod.WrapMethod;
import com.llamalad7.mixinextras.injector.wrapoperation.Operation;
import com.llamalad7.mixinextras.injector.wrapoperation.WrapOperation;
import net.dries007.tfc.world.feature.tree.ForestFeature;
import net.minecraft.core.BlockPos;
import net.minecraft.util.RandomSource;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.ChunkGenerator;
import net.minecraft.world.level.levelgen.feature.ConfiguredFeature;
import net.minecraft.world.level.levelgen.feature.FeaturePlaceContext;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import pack.world.keepclear.KeepClear;

/**
 * Keeps TFC's forests (and so ArborFirmaCraft's, which only adds tree entries to the same feature) out of structures
 * (docs/lived-in.md, "Keeping the land clear"). {@code ForestFeature} picks every tree position itself, so a placement filter can only
 * refuse a whole chunk; three small wraps ask {@link KeepClear} instead: the whole {@code place} (opens the scope for the chunk being
 * decorated), the call that places a tree at its trunk, the call that asks whether a bush can stand, and the block writes of a fallen
 * log (TFC checks the first few cells it covers and then writes all of them). A refused tree is simply not placed.
 */
@Mixin(ForestFeature.class)
public abstract class ForestFeatureMixin
{
    @WrapMethod(method = "place(Lnet/minecraft/world/level/levelgen/feature/FeaturePlaceContext;)Z")
    private boolean pack_world$scope(FeaturePlaceContext<?> context, Operation<Boolean> original)
    {
        KeepClear.begin(context.level(), context.origin());
        try
        {
            return original.call(context);
        }
        finally
        {
            KeepClear.end();
        }
    }

    @WrapOperation(method = "placeTree", at = @At(value = "INVOKE",
        target = "Lnet/minecraft/world/level/levelgen/feature/ConfiguredFeature;place(Lnet/minecraft/world/level/WorldGenLevel;Lnet/minecraft/world/level/chunk/ChunkGenerator;Lnet/minecraft/util/RandomSource;Lnet/minecraft/core/BlockPos;)Z"))
    private boolean pack_world$tree(ConfiguredFeature<?, ?> feature, WorldGenLevel level, ChunkGenerator generator, RandomSource random, BlockPos pos,
                                    Operation<Boolean> original)
    {
        return !KeepClear.treeBlocked(pos) && original.call(feature, level, generator, random, pos);
    }

    @WrapOperation(method = "placeBush", at = @At(value = "INVOKE",
        target = "Lnet/dries007/tfc/util/EnvironmentHelpers;canPlaceBushOn(Lnet/minecraft/world/level/WorldGenLevel;Lnet/minecraft/core/BlockPos;)Z"))
    private boolean pack_world$bush(WorldGenLevel level, BlockPos pos, Operation<Boolean> original)
    {
        return !KeepClear.treeBlocked(pos) && original.call(level, pos);
    }

    @WrapOperation(method = "placeFallenTree", at = @At(value = "INVOKE",
        target = "Lnet/minecraft/world/level/WorldGenLevel;setBlock(Lnet/minecraft/core/BlockPos;Lnet/minecraft/world/level/block/state/BlockState;I)Z"))
    private boolean pack_world$log(WorldGenLevel level, BlockPos pos, BlockState state, int flags, Operation<Boolean> original)
    {
        return !KeepClear.blockWriteBlocked(pos) && original.call(level, pos, state, flags);
    }
}
