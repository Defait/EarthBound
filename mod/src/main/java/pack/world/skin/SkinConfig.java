package pack.world.skin;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.level.block.Block;
import org.jetbrains.annotations.Nullable;
import pack.world.PackWorld;
import pack.world.materials.BlockFamilies;

/**
 * The structure skin's data (docs/lived-in.md, "Structure skin"): which structures it rewrites and the block table, merged from
 * every {@code data/<ns>/pack_world/structure_skin/*.json} (files in id order, later files win on the same block). Keys:
 * <pre>
 * "structures":     ["towns_and_towers", "mvs:barn"]    namespaces or structure ids the skin applies to
 * "exclude":        ["mvs:floating_islands"]            structure ids it leaves alone
 * "placeholders":   ["tfchuts"]                         namespaces whose own placeholder TFC blocks (granite, oak, alfisol, yellow)
 *                                                       are made local too
 * "woods":          ["oak", "spruce", "acacia"]         wood placeholders in rank order: rank 0 is the climate's best-fitting tree
 * "dry_run":        false                               true: count what structures write, rewrite nothing (tests)
 * "sea_water":      ["hopo", "underwater_village:ruins"] namespaces or structure ids whose water is TFC salt water (see {@link SeaWater}),
 *                                                       when the structure stands in a biome of {@code #tfc:is_ocean}; elsewhere river water
 * "sea_water_fill_air": true                            in those, air a structure wrote where the sea was becomes sea again
 * "foundation":     {"max_depth": 8, "variant": "raw", "steps": ["surface_structures"], "exclude": ["mvs:floating_islands"]}
 * "items":          {"minecraft:iron_helmet": "tfc:metal/helmet/copper"}   item ids on armor stands, mobs, frames, dropped items
 * "blocks":         {"minecraft:cobblestone": "tfc:rock/cobble/granite", "minecraft:snow": "@keep", "minecraft:wheat": "@air"}
 * </pre>
 * A block's value is a block id, "@air" (removed) or "@keep" (left alone). A TFC id whose material is a placeholder (granite,
 * the ranked woods, alfisol, yellow) is made local; any other id is placed as it is. Properties with the same name and value are
 * copied (facing, half, shape, axis, waterlogged ...).
 */
public final class SkinConfig
{
    public static final SkinConfig EMPTY = new SkinConfig(Set.of(), Set.of(), Set.of(), Set.of(), List.of("oak"), Map.of(), null, Set.of(), false, Map.of(), Set.of(), Set.of(), true);

    public enum Action { KEEP, REMOVE, MAP, ALLOY }

    /**
     * @param parsed non-null when the target is a placeholder that must be made local (rock, wood, soil or sand)
     * @param woodRank rank of the wood placeholder (0 = best fit)
     */
    public record Rule(Action action, @Nullable Block target, @Nullable ResourceLocation targetId, @Nullable BlockFamilies.Parsed parsed, int woodRank) {}

    public record Foundation(int maxDepth, String variant, Set<String> steps, Set<ResourceLocation> exclude) {}

    private final Set<String> namespaces;
    private final Set<ResourceLocation> ids;
    private final Set<ResourceLocation> exclude;
    private final Set<String> placeholderNamespaces;
    private final List<String> woods;
    private final Map<Block, Rule> rules;
    @Nullable private final Foundation foundation;
    private final Set<String> unknownBlocks;
    private final boolean dryRun;
    private final Map<String, String> items;
    private final Set<String> seaNamespaces;
    private final Set<ResourceLocation> seaIds;
    private final boolean seaFillAir;

    SkinConfig(Set<String> namespaces, Set<ResourceLocation> ids, Set<ResourceLocation> exclude, Set<String> placeholderNamespaces,
               List<String> woods, Map<Block, Rule> rules, @Nullable Foundation foundation, Set<String> unknownBlocks, boolean dryRun,
               Map<String, String> items, Set<String> seaNamespaces, Set<ResourceLocation> seaIds, boolean seaFillAir)
    {
        this.namespaces = namespaces;
        this.ids = ids;
        this.exclude = exclude;
        this.placeholderNamespaces = placeholderNamespaces;
        this.woods = woods;
        this.rules = rules;
        this.foundation = foundation;
        this.unknownBlocks = unknownBlocks;
        this.dryRun = dryRun;
        this.items = items;
        this.seaNamespaces = seaNamespaces;
        this.seaIds = seaIds;
        this.seaFillAir = seaFillAir;
    }

    /** Whether this structure's water is salt water (when it stands in an ocean biome: the caller checks that). */
    public boolean seaWater(ResourceLocation structure)
    {
        return seaIds.contains(structure) || seaNamespaces.contains(structure.getNamespace());
    }

    /** Whether air a sea structure wrote over sea water is turned back into sea water. */
    public boolean seaFillAir()
    {
        return seaFillAir;
    }

    /** Item id -> item id for what structures put on armor stands, mobs, in frames and on the ground (iron gear becomes copper ...). */
    public Map<String, String> items()
    {
        return items;
    }

    /** Measure only: count what structures write but rewrite nothing (the tests' 'before'). */
    public boolean dryRun()
    {
        return dryRun;
    }

    public boolean isEmpty()
    {
        return namespaces.isEmpty() && ids.isEmpty();
    }

    public boolean applies(ResourceLocation structure)
    {
        return !exclude.contains(structure) && (ids.contains(structure) || namespaces.contains(structure.getNamespace()));
    }

    public boolean localizesPlaceholders(ResourceLocation structure)
    {
        return placeholderNamespaces.contains(structure.getNamespace());
    }

    public List<String> woods()
    {
        return woods;
    }

    /**
     * The rule for a block: the table's, else an implicit one for TFC blocks the structure already holds (its own placeholders,
     * when the namespace asks for that, and rough rock of the andesite-alloy rocks); null when the block is left alone.
     */
    @Nullable
    public Rule rule(Block block, boolean placeholders)
    {
        final Rule explicit = rules.get(block);
        if (explicit != null)
        {
            return explicit;
        }
        final Rule implicit = (placeholders ? implicitPlaceholders : implicitPlain).computeIfAbsent(block, b -> implicit(b, placeholders));
        return implicit == NONE ? null : implicit;
    }

    private static final Rule NONE = new Rule(Action.KEEP, null, null, null, 0);
    private final Map<Block, Rule> implicitPlain = new java.util.concurrent.ConcurrentHashMap<>();
    private final Map<Block, Rule> implicitPlaceholders = new java.util.concurrent.ConcurrentHashMap<>();

    private Rule implicit(Block block, boolean placeholders)
    {
        final ResourceLocation id = BuiltInRegistries.BLOCK.getKey(block);
        final BlockFamilies.Parsed parsed = BlockFamilies.parse(id);
        if (parsed == null)
        {
            return NONE;
        }
        if (placeholders && placeholderParse(id, woods) != null)
        {
            return new Rule(Action.MAP, block, id, parsed, woodRank(id, woods));
        }
        if (parsed.kind() == BlockFamilies.Kind.ROCK && BlockFamilies.ALLOY_ROCKS.contains(parsed.material()))
        {
            return new Rule(Action.ALLOY, block, id, parsed, 0);
        }
        return NONE;
    }

    @Nullable
    public Foundation foundation()
    {
        return foundation;
    }

    public int ruleCount()
    {
        return rules.size();
    }

    /** Block ids the table names that don't exist in this pack (reported once at load). */
    public Set<String> unknownBlocks()
    {
        return unknownBlocks;
    }

    public Set<String> namespaces()
    {
        return namespaces;
    }

    /** Merges the parsed files (in the order given). */
    static SkinConfig load(Map<ResourceLocation, JsonElement> files)
    {
        final Set<String> namespaces = new HashSet<>();
        final Set<ResourceLocation> ids = new HashSet<>();
        final Set<ResourceLocation> exclude = new HashSet<>();
        final Set<String> placeholders = new HashSet<>();
        final Map<String, String> rawBlocks = new HashMap<>();
        final Map<String, String> items = new HashMap<>();
        List<String> woods = List.of("oak", "spruce", "acacia");
        Foundation foundation = null;
        boolean dryRun = false;
        final Set<String> seaNamespaces = new HashSet<>();
        final Set<ResourceLocation> seaIds = new HashSet<>();
        boolean seaFillAir = true;

        for (Map.Entry<ResourceLocation, JsonElement> file : new java.util.TreeMap<>(files).entrySet())
        {
            if (!file.getValue().isJsonObject())
            {
                PackWorld.LOGGER.warn("structure_skin {}: not a JSON object", file.getKey());
                continue;
            }
            final JsonObject json = file.getValue().getAsJsonObject();
            for (String s : strings(json, "structures"))
            {
                if (s.contains(":"))
                {
                    ids.add(ResourceLocation.parse(s));
                }
                else
                {
                    namespaces.add(s);
                }
            }
            for (String s : strings(json, "exclude"))
            {
                exclude.add(ResourceLocation.parse(s));
            }
            placeholders.addAll(strings(json, "placeholders"));
            for (String s : strings(json, "sea_water"))
            {
                if (s.contains(":"))
                {
                    seaIds.add(ResourceLocation.parse(s));
                }
                else
                {
                    seaNamespaces.add(s);
                }
            }
            if (json.has("sea_water_fill_air"))
            {
                seaFillAir = json.get("sea_water_fill_air").getAsBoolean();
            }
            if (json.has("dry_run"))
            {
                dryRun = json.get("dry_run").getAsBoolean();
            }
            if (json.has("woods"))
            {
                woods = strings(json, "woods");
            }
            if (json.has("blocks") && json.get("blocks").isJsonObject())
            {
                for (Map.Entry<String, JsonElement> e : json.getAsJsonObject("blocks").entrySet())
                {
                    rawBlocks.put(e.getKey(), e.getValue().getAsString());
                }
            }
            if (json.has("items") && json.get("items").isJsonObject())
            {
                for (Map.Entry<String, JsonElement> e : json.getAsJsonObject("items").entrySet())
                {
                    items.put(e.getKey(), e.getValue().getAsString());
                }
            }
            if (json.has("foundation") && json.get("foundation").isJsonObject())
            {
                final JsonObject f = json.getAsJsonObject("foundation");
                final Set<ResourceLocation> noFoundation = new HashSet<>();
                for (String s : strings(f, "exclude"))
                {
                    noFoundation.add(ResourceLocation.parse(s));
                }
                final List<String> steps = f.has("steps") ? strings(f, "steps") : List.of("surface_structures");
                foundation = new Foundation(f.has("max_depth") ? f.get("max_depth").getAsInt() : 8,
                    f.has("variant") ? f.get("variant").getAsString() : "raw", Set.copyOf(steps), noFoundation);
            }
        }

        final Map<Block, Rule> rules = new HashMap<>();
        final Set<String> unknown = new HashSet<>();
        for (Map.Entry<String, String> e : rawBlocks.entrySet())
        {
            final Optional<Block> from = BuiltInRegistries.BLOCK.getOptional(ResourceLocation.parse(e.getKey()));
            if (from.isEmpty())
            {
                unknown.add(e.getKey());
                continue;
            }
            final String value = e.getValue();
            if (value.equals("@keep"))
            {
                rules.put(from.get(), new Rule(Action.KEEP, null, null, null, 0));
            }
            else if (value.equals("@air"))
            {
                rules.put(from.get(), new Rule(Action.REMOVE, null, null, null, 0));
            }
            else
            {
                final ResourceLocation id = ResourceLocation.parse(value);
                final Optional<Block> to = BuiltInRegistries.BLOCK.getOptional(id);
                if (to.isEmpty())
                {
                    unknown.add(value);
                    continue;
                }
                rules.put(from.get(), new Rule(Action.MAP, to.get(), id, placeholderParse(id, woods), woodRank(id, woods)));
            }
        }
        return new SkinConfig(namespaces, ids, exclude, placeholders, woods, rules, foundation, unknown, dryRun, Map.copyOf(items), seaNamespaces, seaIds, seaFillAir);
    }

    /** The parse of a table target when its material is a placeholder, else null (placed as is). */
    @Nullable
    static BlockFamilies.Parsed placeholderParse(ResourceLocation id, List<String> woods)
    {
        final BlockFamilies.Parsed parsed = BlockFamilies.parse(id);
        if (parsed == null)
        {
            return null;
        }
        final boolean placeholder = switch (parsed.kind())
        {
            case ROCK, ORE -> parsed.material().equals("granite");
            case WOOD -> woods.contains(parsed.material());
            case SOIL -> parsed.material().equals("alfisol");
            case SAND -> parsed.material().equals("yellow");
        };
        return placeholder ? parsed : null;
    }

    static int woodRank(ResourceLocation id, List<String> woods)
    {
        final BlockFamilies.Parsed parsed = BlockFamilies.parse(id);
        return parsed != null && parsed.kind() == BlockFamilies.Kind.WOOD ? Math.max(0, woods.indexOf(parsed.material())) : 0;
    }

    private static List<String> strings(JsonObject json, String key)
    {
        final List<String> out = new ArrayList<>();
        if (json.has(key) && json.get(key).isJsonArray())
        {
            final JsonArray array = json.getAsJsonArray(key);
            for (JsonElement e : array)
            {
                out.add(e.getAsString());
            }
        }
        return out;
    }
}
