package pack.world.mixin;

import com.llamalad7.mixinextras.injector.wrapmethod.WrapMethod;
import com.llamalad7.mixinextras.injector.wrapoperation.Operation;
import net.dries007.tfc.world.biome.BiomeNoise;
import net.dries007.tfc.world.noise.Noise2D;
import org.spongepowered.asm.mixin.Mixin;
import pack.world.ocean.OceanDepths;

/**
 * Deepens TFC's oceans (docs/design.md, "Oceans"): the depth pair every ocean biome gives {@code BiomeNoise.ocean} and
 * {@code oceanTrench} is replaced on the way in, and {@code oceanRidge} is rebuilt on the new deep floor ({@link OceanDepths} has the
 * table and the reasons). TFC: Real World is untouched: it picks the biomes, TFC still gives them their shapes.
 */
@Mixin(BiomeNoise.class)
public abstract class OceanDepthMixin
{
    @WrapMethod(method = "ocean(JII)Lnet/dries007/tfc/world/noise/Noise2D;")
    private static Noise2D pack_world$ocean(long seed, int depthMin, int depthMax, Operation<Noise2D> original)
    {
        int[] pair = OceanDepths.ocean(depthMin, depthMax);
        return original.call(seed, pair[0], pair[1]);
    }

    @WrapMethod(method = "oceanTrench(JII)Lnet/dries007/tfc/world/noise/Noise2D;")
    private static Noise2D pack_world$trench(long seed, int depthMin, int depthMax, Operation<Noise2D> original)
    {
        int[] pair = OceanDepths.trench(depthMin, depthMax);
        return original.call(seed, pair[0], pair[1]);
    }

    @WrapMethod(method = "oceanRidge(J)Lnet/dries007/tfc/world/noise/Noise2D;")
    private static Noise2D pack_world$ridge(long seed, Operation<Noise2D> original)
    {
        return OceanDepths.ridge(seed, original::call);
    }
}
