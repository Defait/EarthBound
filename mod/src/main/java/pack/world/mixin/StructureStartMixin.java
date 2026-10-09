package pack.world.mixin;

import com.llamalad7.mixinextras.injector.wrapoperation.Operation;
import com.llamalad7.mixinextras.injector.wrapoperation.WrapOperation;
import net.minecraft.core.BlockPos;
import net.minecraft.util.RandomSource;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.StructureManager;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.chunk.ChunkGenerator;
import net.minecraft.world.level.levelgen.structure.BoundingBox;
import net.minecraft.world.level.levelgen.structure.StructurePiece;
import net.minecraft.world.level.levelgen.structure.StructureStart;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import pack.world.keepclear.KeepClear;
import pack.world.skin.StructureSkin;

/**
 * The structure skin's only hook into Minecraft (docs/lived-in.md, "Structure skin"): around {@code StructureStart.placeInChunk},
 * which every structure goes through when it places its pieces in a chunk, whoever built it. The skin snapshots the pieces' area
 * before, and rewrites what the structure wrote after. Both injections do nothing unless the structure is in the skin's
 * configured list, and failures inside them are logged and swallowed (worldgen continues with the unskinned structure).
 * <p>
 * A third injection wraps the call that places each piece: {@link KeepClear#suppressed} skips pieces of structures that yield (other
 * mods') where they overlap a piece of a village (docs/lived-in.md, "Keeping the land clear").
 */
@Mixin(StructureStart.class)
public abstract class StructureStartMixin
{
    @Inject(method = "placeInChunk", at = @At("HEAD"))
    private void pack_world$beforePlace(WorldGenLevel level, StructureManager manager, ChunkGenerator generator, RandomSource random,
                                        BoundingBox box, ChunkPos chunkPos, CallbackInfo ci)
    {
        StructureSkin.begin((StructureStart) (Object) this, level, box);
    }

    @Inject(method = "placeInChunk", at = @At("RETURN"))
    private void pack_world$afterPlace(WorldGenLevel level, StructureManager manager, ChunkGenerator generator, RandomSource random,
                                       BoundingBox box, ChunkPos chunkPos, CallbackInfo ci)
    {
        StructureSkin.end((StructureStart) (Object) this, level, box);
    }

    @WrapOperation(method = "placeInChunk", at = @At(value = "INVOKE",
        target = "Lnet/minecraft/world/level/levelgen/structure/StructurePiece;postProcess(Lnet/minecraft/world/level/WorldGenLevel;Lnet/minecraft/world/level/StructureManager;Lnet/minecraft/world/level/chunk/ChunkGenerator;Lnet/minecraft/util/RandomSource;Lnet/minecraft/world/level/levelgen/structure/BoundingBox;Lnet/minecraft/world/level/ChunkPos;Lnet/minecraft/core/BlockPos;)V"))
    private void pack_world$piece(StructurePiece piece, WorldGenLevel level, StructureManager manager, ChunkGenerator generator, RandomSource random,
                                  BoundingBox box, ChunkPos chunkPos, BlockPos pivot, Operation<Void> original)
    {
        if (!KeepClear.suppressed((StructureStart) (Object) this, piece, level, manager, chunkPos))
        {
            original.call(piece, level, manager, generator, random, box, chunkPos, pivot);
        }
    }
}
