package pack.world.keepclear;

import java.util.Map;
import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonElement;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.packs.resources.ResourceManager;
import net.minecraft.server.packs.resources.SimpleJsonResourceReloadListener;
import net.minecraft.util.profiling.ProfilerFiller;
import pack.world.PackWorld;

/** Loads {@code data/<ns>/pack_world/keep_clear/*.json} on every data reload (see {@link KeepClearConfig}). */
public final class KeepClearReloadListener extends SimpleJsonResourceReloadListener
{
    private static final Gson GSON = new GsonBuilder().setLenient().create();

    public KeepClearReloadListener()
    {
        super(GSON, "pack_world/keep_clear");
    }

    @Override
    protected void apply(Map<ResourceLocation, JsonElement> files, ResourceManager resources, ProfilerFiller profiler)
    {
        final KeepClearConfig config = KeepClearConfig.load(files);
        KeepClear.setConfig(config);
        PackWorld.LOGGER.info("pack_world keep-clear: {} file(s), {}", files.size(), config);
    }
}
