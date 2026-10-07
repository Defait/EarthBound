package pack.world.materials;

import com.mojang.serialization.Codec;
import net.minecraft.util.StringRepresentable;

/**
 * What a structure does when its rock is andesite alloy rock (andesite, basalt, dacite, rhyolite, diorite: raw or cobble of
 * them makes Create's andesite alloy, docs/design.md "Create opens").
 */
public enum AlloyPolicy implements StringRepresentable
{
    /** Rough variants become worked stone of the same rock (raw -> smooth, cobble -> cracked bricks, loose rocks removed). */
    WORK("work"),
    /** The whole structure uses the substitute rock instead. */
    SUBSTITUTE("substitute"),
    /** No change. */
    ALLOW("allow");

    public static final Codec<AlloyPolicy> CODEC = StringRepresentable.fromEnum(AlloyPolicy::values);

    private final String name;

    AlloyPolicy(String name)
    {
        this.name = name;
    }

    @Override
    public String getSerializedName()
    {
        return name;
    }
}
