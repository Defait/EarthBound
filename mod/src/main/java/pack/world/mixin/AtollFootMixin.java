package pack.world.mixin;

import com.llamalad7.mixinextras.injector.wrapoperation.Operation;
import com.llamalad7.mixinextras.injector.wrapoperation.WrapOperation;
import com.llamalad7.mixinextras.sugar.Local;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import pack.world.ocean.OceanDepths;

/**
 * Lets TFC's atolls rise from the deeper sea floor (docs/design.md, "Oceans"). An atoll is a mound whose profile runs from y 3 at the
 * edge of its cell to the rim at sea level, laid over the floor as {@code max(floor, profile)}; with the deep ocean's floor at y 17
 * to 33 that edge was always under the floor, with it at y -32 to -2 the edge would be a cliff all round the cell.
 * {@link OceanDepths#atollFoot} lowers the profile's foot to stay under the floor.
 */
@Mixin(targets = "net.dries007.tfc.world.volcano.CenteredFeatureNoise$3")
public abstract class AtollFootMixin
{
    /** {@code modifyHeight}'s second {@code Mth.map} turns the reef shape (0 to 1) into a height, from y 3 up to the rim. */
    @WrapOperation(method = "modifyHeight", at = @At(value = "INVOKE",
        target = "Lnet/minecraft/util/Mth;map(DDDDD)D", ordinal = 1))
    private double pack_world$foot(double shape, double fromMin, double fromMax, double toMin, double toMax, Operation<Double> original,
                                   @Local(argsOnly = true) double floor)
    {
        return original.call(shape, fromMin, fromMax, OceanDepths.atollFoot(toMin, floor), toMax);
    }
}
