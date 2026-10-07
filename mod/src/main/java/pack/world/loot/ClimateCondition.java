package pack.world.loot;

import java.util.Optional;
import com.mojang.serialization.Codec;
import com.mojang.serialization.MapCodec;
import com.mojang.serialization.codecs.RecordCodecBuilder;
import net.dries007.tfc.util.EnvironmentHelpers;
import net.dries007.tfc.world.chunkdata.ChunkData;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.storage.loot.LootContext;
import net.minecraft.world.level.storage.loot.parameters.LootContextParams;
import net.minecraft.world.level.storage.loot.predicates.LootItemCondition;
import net.minecraft.world.level.storage.loot.predicates.LootItemConditionType;
import net.minecraft.world.phys.Vec3;
import pack.world.PackWorld;

/**
 * {@code pack_world:climate}: true when TFC's climate at the loot origin (a chest, rolled when first opened) is inside the
 * given bounds: average temperature at that height (°C) and average groundwater (0-500). Outside a TFC level, or without an
 * origin, it passes. Lets one loot table hold the seeds and saplings that grow where the chest is.
 */
public record ClimateCondition(Optional<Float> minTemperature, Optional<Float> maxTemperature,
                               Optional<Float> minGroundwater, Optional<Float> maxGroundwater) implements LootItemCondition
{
    public static final MapCodec<ClimateCondition> CODEC = RecordCodecBuilder.mapCodec(i -> i.group(
        Codec.FLOAT.optionalFieldOf("min_temperature").forGetter(ClimateCondition::minTemperature),
        Codec.FLOAT.optionalFieldOf("max_temperature").forGetter(ClimateCondition::maxTemperature),
        Codec.FLOAT.optionalFieldOf("min_groundwater").forGetter(ClimateCondition::minGroundwater),
        Codec.FLOAT.optionalFieldOf("max_groundwater").forGetter(ClimateCondition::maxGroundwater)
    ).apply(i, ClimateCondition::new));

    @Override
    public LootItemConditionType getType()
    {
        return PackWorld.CLIMATE.get();
    }

    @Override
    public boolean test(LootContext context)
    {
        final Vec3 origin = context.getParamOrNull(LootContextParams.ORIGIN);
        if (origin == null)
        {
            return true;
        }
        final BlockPos pos = BlockPos.containing(origin);
        final ChunkData data = ChunkData.get(context.getLevel(), pos);
        if (data == ChunkData.EMPTY)
        {
            return true;
        }
        final float temperature = EnvironmentHelpers.adjustAvgTempForElev(pos.getY(), data.getAverageSeaLevelTemp(pos));
        final float groundwater = data.getAverageGroundwater(pos);
        return minTemperature.map(t -> temperature >= t).orElse(true) && maxTemperature.map(t -> temperature <= t).orElse(true)
            && minGroundwater.map(g -> groundwater >= g).orElse(true) && maxGroundwater.map(g -> groundwater <= g).orElse(true);
    }
}
