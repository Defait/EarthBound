package pack.world.skin;

import java.util.Map;
import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonElement;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.packs.resources.ResourceManager;
import net.minecraft.server.packs.resources.SimpleJsonResourceReloadListener;
import net.minecraft.util.profiling.ProfilerFiller;
import pack.world.PackWorld;

/** Loads {@code data/<ns>/pack_world/structure_skin/*.json} on every data reload (see {@link SkinConfig}). */
public final class SkinReloadListener extends SimpleJsonResourceReloadListener
{
    private static final Gson GSON = new GsonBuilder().setLenient().create();

    public SkinReloadListener()
    {
        super(GSON, "pack_world/structure_skin");
    }

    @Override
    protected void apply(Map<ResourceLocation, JsonElement> files, ResourceManager resources, ProfilerFiller profiler)
    {
        final SkinConfig config = SkinConfig.load(files);
        StructureSkin.setConfig(config);
        PackWorld.LOGGER.info("pack_world structure skin: {} file(s), {} block rule(s), structures {}", files.size(), config.ruleCount(), config.namespaces());
        if (!config.unknownBlocks().isEmpty())
        {
            PackWorld.LOGGER.warn("pack_world structure skin: {} block id(s) in the table don't exist in this pack: {}", config.unknownBlocks().size(),
                config.unknownBlocks().stream().sorted().limit(20).toList());
        }
    }
}
