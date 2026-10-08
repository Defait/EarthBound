package pack.world.geo;

import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;
import com.mojang.brigadier.arguments.StringArgumentType;
import com.mojang.brigadier.context.CommandContext;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.commands.SharedSuggestionProvider;
import net.minecraft.core.HolderLookup;
import net.minecraft.core.registries.Registries;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.ListTag;
import net.minecraft.nbt.StringTag;
import net.minecraft.nbt.Tag;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.levelgen.structure.StructureSet;
import net.minecraft.world.level.saveddata.SavedData;
import net.neoforged.neoforge.event.RegisterCommandsEvent;
import net.neoforged.neoforge.event.level.LevelEvent;
import org.jetbrains.annotations.Nullable;
import pack.world.PackWorld;
import pack.world.structure.GuardedJigsawStructure;

/**
 * Fixed sites land on their coordinates whether that land was explored or not: an explored start chunk means no site, an
 * explored part of the footprint means half a site. So each world records which sites it may generate: a new world (game
 * time 0 when the overworld loads) gets every site it has; a world that existed before this mod, or before a site was added,
 * gets none of the missing ones. Operators can enable a site after checking its area is unexplored:
 * {@code /pack_world sites [enable|disable <site>]}.
 */
public final class SiteGuard extends SavedData
{
    static final String NAME = "pack_world_sites";
    private static final SavedData.Factory<SiteGuard> FACTORY = new SavedData.Factory<>(SiteGuard::new, SiteGuard::load);

    @Nullable private static volatile SiteGuard current;

    private final Set<String> enabled = new TreeSet<>();
    private String origin = "";

    public static boolean allowed(String site)
    {
        final SiteGuard guard = current;
        return guard != null && guard.enabled.contains(site);
    }

    public static Set<String> enabledSites()
    {
        final SiteGuard guard = current;
        return guard == null ? Set.of() : Set.copyOf(guard.enabled);
    }

    /** Every geographic placement in the level's structure sets, by site name. */
    public static Map<String, GeographicPlacement> sites(ServerLevel level)
    {
        final Map<String, GeographicPlacement> out = new TreeMap<>();
        for (StructureSet set : level.registryAccess().registryOrThrow(Registries.STRUCTURE_SET))
        {
            if (set.placement() instanceof GeographicPlacement placement)
            {
                out.put(placement.site().name(), placement);
            }
        }
        return out;
    }

    public static void onLevelLoad(LevelEvent.Load event)
    {
        if (!(event.getLevel() instanceof ServerLevel level) || level.dimension() != Level.OVERWORLD)
        {
            return;
        }
        SiteGuard guard = level.getDataStorage().get(FACTORY, NAME);
        if (guard == null)
        {
            guard = new SiteGuard();
            final boolean fresh = level.getGameTime() == 0;
            guard.origin = fresh ? "new world" : "existing world";
            if (fresh)
            {
                guard.enabled.addAll(sites(level).keySet());
            }
            level.getDataStorage().set(NAME, guard);
            guard.setDirty();
            PackWorld.LOGGER.info("pack_world: {} sites enabled in this {} ({} defined){}", guard.enabled.size(), guard.origin,
                sites(level).size(), fresh ? "" : "; operators can enable them with /pack_world sites enable <site>");
        }
        current = guard;
    }

    public static void onLevelUnload(LevelEvent.Unload event)
    {
        if (event.getLevel() instanceof ServerLevel level && level.dimension() == Level.OVERWORLD)
        {
            current = null;
        }
    }

    public static void onRegisterCommands(RegisterCommandsEvent event)
    {
        event.getDispatcher().register(Commands.literal("pack_world")
            .requires(source -> source.hasPermission(2))
            .then(Commands.literal("sites")
                .executes(SiteGuard::list)
                .then(Commands.literal("enable").then(Commands.argument("site", StringArgumentType.word())
                    .suggests((ctx, builder) -> SharedSuggestionProvider.suggest(sites(ctx.getSource().getServer().overworld()).keySet(), builder))
                    .executes(ctx -> toggle(ctx, true))))
                .then(Commands.literal("disable").then(Commands.argument("site", StringArgumentType.word())
                    .suggests((ctx, builder) -> SharedSuggestionProvider.suggest(enabledSites(), builder))
                    .executes(ctx -> toggle(ctx, false)))))
            .then(Commands.literal("guard")
                .executes(ctx -> guard(ctx, null))
                .then(Commands.literal("on").executes(ctx -> guard(ctx, true)))
                .then(Commands.literal("off").executes(ctx -> guard(ctx, false)))));
    }

    /**
     * {@code /pack_world guard [on|off]}: the slope and water guard of {@code pack_world:guarded_jigsaw} (villages). Off, a village can be
     * placed anywhere with {@code /place structure}; it is not saved, so it is on again after a restart.
     */
    private static int guard(CommandContext<CommandSourceStack> ctx, Boolean state)
    {
        if (state != null)
        {
            GuardedJigsawStructure.enabled = state;
        }
        final boolean on = GuardedJigsawStructure.enabled;
        ctx.getSource().sendSuccess(() -> Component.literal("The village guard (slope and water) is " + (on ? "on" : "off") + (state == null ? "." : " now.")), state != null);
        return on ? 1 : 0;
    }

    private static int list(CommandContext<CommandSourceStack> ctx)
    {
        final ServerLevel level = ctx.getSource().getServer().overworld();
        final Map<String, GeographicPlacement> sites = sites(level);
        if (sites.isEmpty())
        {
            ctx.getSource().sendSuccess(() -> Component.literal("No geographic sites are defined."), false);
            return 0;
        }
        for (Map.Entry<String, GeographicPlacement> e : sites.entrySet())
        {
            final GeographicPlacement p = e.getValue();
            final ChunkPos chunk = p.siteChunk();
            final int[] xz = p.siteBlock();
            final String where = chunk == null ? "no TFC: Real World" : "x " + xz[0] + ", z " + xz[1] + " (chunk " + chunk.x + ", " + chunk.z + ")";
            final String state = allowed(e.getKey()) ? "enabled" : "disabled";
            ctx.getSource().sendSuccess(() -> Component.literal(e.getKey() + " " + p.site().latitude() + ", " + p.site().longitude() + ": " + where + ", " + state), false);
        }
        return sites.size();
    }

    private static int toggle(CommandContext<CommandSourceStack> ctx, boolean enable)
    {
        final String site = StringArgumentType.getString(ctx, "site");
        final ServerLevel level = ctx.getSource().getServer().overworld();
        if (enable && !sites(level).containsKey(site))
        {
            ctx.getSource().sendFailure(Component.literal("No such site: " + site));
            return 0;
        }
        final SiteGuard guard = current;
        if (guard == null)
        {
            ctx.getSource().sendFailure(Component.literal("The overworld isn't loaded."));
            return 0;
        }
        final boolean changed = enable ? guard.enabled.add(site) : guard.enabled.remove(site);
        guard.setDirty();
        ctx.getSource().sendSuccess(() -> Component.literal(site + (enable ? " enabled" : " disabled")
            + (changed ? "" : " (no change)") + (enable ? ". It generates if its start chunk hasn't been generated yet." : ".")), true);
        return 1;
    }

    private static SiteGuard load(CompoundTag tag, HolderLookup.Provider provider)
    {
        final SiteGuard guard = new SiteGuard();
        guard.origin = tag.getString("origin");
        final ListTag list = tag.getList("enabled", Tag.TAG_STRING);
        for (int i = 0; i < list.size(); i++)
        {
            guard.enabled.add(list.getString(i));
        }
        return guard;
    }

    @Override
    public CompoundTag save(CompoundTag tag, HolderLookup.Provider provider)
    {
        final ListTag list = new ListTag();
        enabled.forEach(s -> list.add(StringTag.valueOf(s)));
        tag.put("enabled", list);
        tag.putString("origin", origin);
        return tag;
    }
}
