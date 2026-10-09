package pack.world.mixin;

import com.llamalad7.mixinextras.injector.wrapoperation.Operation;
import com.llamalad7.mixinextras.injector.wrapoperation.WrapOperation;
import net.dries007.tfc.world.noise.Cellular2D;
import net.dries007.tfc.world.volcano.VolcanoVariant;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import pack.world.ocean.OceanDepths;

/**
 * Lets TFC's stratovolcanoes (the volcanic arc's, and those of the volcanic coasts and islands) stand on the deeper sea floor
 * (docs/design.md, "Oceans"). {@code modifyHeight} asks the volcano's variant for {@code max(profile, floor)}; the profile's
 * skirt ends in a constant foot (y -1 for the arc) that was always under the old floors, and over a trench would be a ledge.
 * {@link OceanDepths#stratovolcano} stretches the skirt down to the floor there and leaves it alone elsewhere.
 */
@Mixin(targets = "net.dries007.tfc.world.volcano.CenteredFeatureNoise$5")
public abstract class StratovolcanoFootMixin
{
    @WrapOperation(method = "modifyHeight", at = @At(value = "INVOKE",
        target = "Lnet/dries007/tfc/world/volcano/VolcanoVariant;getHeight(DIIDDDLnet/dries007/tfc/world/noise/Cellular2D$Cell;)D"))
    private double pack_world$foot(VolcanoVariant variant, double floor, int x, int z, double radius, double scale, double base,
                                   Cellular2D.Cell cell, Operation<Double> original)
    {
        return OceanDepths.stratovolcano(original.call(variant, floor, x, z, radius, scale, base, cell), floor, scale, base);
    }
}
