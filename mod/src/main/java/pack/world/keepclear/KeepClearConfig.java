package pack.world.keepclear;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.regex.Pattern;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import net.minecraft.resources.ResourceLocation;
import pack.world.PackWorld;

/**
 * The keep-clear data (docs/lived-in.md, "Keeping the land clear"), merged from every {@code data/<ns>/pack_world/keep_clear/*.json}
 * (files in id order; lists add up, numbers of later files win). Keys:
 * <pre>
 * "trees":         ["pack", "towns_and_towers", "mvs"]   structures (namespace, id, or id with * as a wildcard) whose pieces keep trees,
 *                                                           bushes, fallen logs and boulders out
 * "exclude_trees": ["mvs:*_tree"]                          ... except these (natural things some structure mods also place)
 * "holds":         ["pack:village/*"]                      structures whose pieces keep other structures' pieces out
 * "yields":        ["mvs", "betterdungeons"]               structures whose pieces are not placed where they overlap a held piece
 * "solid":         3                                       blocks around a piece's box where no tree trunk is allowed
 * "margin":        7                                       blocks around a piece's box where trunks thin out (to nothing at this distance)
 * "below": 16, "above": 12                                 how far under and over a piece's box a trunk's ground counts as that piece's
 * "hold_pad": 1, "hold_depth": 10, "hold_up": 3            a held piece keeps others out of its box plus this much sideways, below
 *                                                           (a village's foundations reach down 10 blocks) and above
 * "enabled":       true                                    false switches the whole thing off (a later file can: speed comparisons)
 * </pre>
 */
public final class KeepClearConfig
{
    public static final KeepClearConfig EMPTY = new KeepClearConfig(Matcher.NONE, Matcher.NONE, Matcher.NONE, Matcher.NONE, 3, 7, 16, 12, 1, 10, 3, true);

    /** Structure ids by namespace, exact id, or id with {@code *} wildcards. */
    public record Matcher(List<String> namespaces, List<ResourceLocation> ids, List<Pattern> globs)
    {
        static final Matcher NONE = new Matcher(List.of(), List.of(), List.of());

        public boolean isEmpty()
        {
            return namespaces.isEmpty() && ids.isEmpty() && globs.isEmpty();
        }

        public boolean matches(ResourceLocation id)
        {
            if (namespaces.contains(id.getNamespace()) || ids.contains(id))
            {
                return true;
            }
            final String full = id.toString();
            for (Pattern p : globs)
            {
                if (p.matcher(full).matches())
                {
                    return true;
                }
            }
            return false;
        }

        static Matcher of(List<String> entries)
        {
            final List<String> namespaces = new ArrayList<>();
            final List<ResourceLocation> ids = new ArrayList<>();
            final List<Pattern> globs = new ArrayList<>();
            for (String e : entries)
            {
                if (e.contains("*"))
                {
                    final StringBuilder regex = new StringBuilder();
                    for (String part : e.split("\\*", -1))
                    {
                        if (regex.length() > 0)
                        {
                            regex.append(".*");
                        }
                        regex.append(Pattern.quote(part));
                    }
                    globs.add(Pattern.compile(regex.toString()));
                }
                else if (e.contains(":"))
                {
                    ids.add(ResourceLocation.parse(e));
                }
                else
                {
                    namespaces.add(e);
                }
            }
            return new Matcher(List.copyOf(namespaces), List.copyOf(ids), List.copyOf(globs));
        }
    }

    private final Matcher trees;
    private final Matcher excludeTrees;
    private final Matcher holds;
    private final Matcher yields;
    private final int solid;
    private final int margin;
    private final int below;
    private final int above;
    private final int holdPad;
    private final int holdDepth;
    private final int holdUp;
    private final boolean enabled;

    KeepClearConfig(Matcher trees, Matcher excludeTrees, Matcher holds, Matcher yields, int solid, int margin, int below, int above,
                    int holdPad, int holdDepth, int holdUp, boolean enabled)
    {
        this.trees = trees;
        this.excludeTrees = excludeTrees;
        this.holds = holds;
        this.yields = yields;
        this.solid = solid;
        this.margin = Math.max(margin, solid);
        this.below = below;
        this.above = above;
        this.holdPad = holdPad;
        this.holdDepth = holdDepth;
        this.holdUp = holdUp;
        this.enabled = enabled;
    }

    public boolean keepsTreesOut(ResourceLocation structure)
    {
        return trees.matches(structure) && !excludeTrees.matches(structure);
    }

    public boolean holds(ResourceLocation structure)
    {
        return holds.matches(structure);
    }

    public boolean yields(ResourceLocation structure)
    {
        return yields.matches(structure) && !holds.matches(structure);
    }

    public boolean isEmpty()
    {
        return !enabled || (trees.isEmpty() && holds.isEmpty());
    }

    public int solid() { return solid; }

    public int margin() { return margin; }

    public int below() { return below; }

    public int above() { return above; }

    public int holdPad() { return holdPad; }

    public int holdDepth() { return holdDepth; }

    public int holdUp() { return holdUp; }

    @Override
    public String toString()
    {
        return (enabled ? "" : "DISABLED, ") + "trees " + trees + " (except " + excludeTrees + "), holds " + holds + ", yields " + yields + ", solid " + solid + ", margin " + margin;
    }

    static KeepClearConfig load(Map<ResourceLocation, JsonElement> files)
    {
        final List<String> trees = new ArrayList<>(), excludeTrees = new ArrayList<>(), holds = new ArrayList<>(), yields = new ArrayList<>();
        int solid = 3, margin = 7, below = 16, above = 12, holdPad = 1, holdDepth = 10, holdUp = 3;
        boolean enabled = true;
        for (Map.Entry<ResourceLocation, JsonElement> file : new TreeMap<>(files).entrySet())
        {
            if (!file.getValue().isJsonObject())
            {
                PackWorld.LOGGER.warn("keep_clear {}: not a JSON object", file.getKey());
                continue;
            }
            final JsonObject json = file.getValue().getAsJsonObject();
            strings(json, "trees", trees);
            strings(json, "exclude_trees", excludeTrees);
            strings(json, "holds", holds);
            strings(json, "yields", yields);
            solid = number(json, "solid", solid);
            margin = number(json, "margin", margin);
            below = number(json, "below", below);
            above = number(json, "above", above);
            holdPad = number(json, "hold_pad", holdPad);
            holdDepth = number(json, "hold_depth", holdDepth);
            holdUp = number(json, "hold_up", holdUp);
            if (json.has("enabled"))
            {
                enabled = json.get("enabled").getAsBoolean();
            }
        }
        return new KeepClearConfig(Matcher.of(trees), Matcher.of(excludeTrees), Matcher.of(holds), Matcher.of(yields), solid, margin, below, above,
            holdPad, holdDepth, holdUp, enabled);
    }

    private static int number(JsonObject json, String key, int fallback)
    {
        return json.has(key) ? json.get(key).getAsInt() : fallback;
    }

    private static void strings(JsonObject json, String key, List<String> into)
    {
        if (json.has(key) && json.get(key).isJsonArray())
        {
            for (JsonElement e : json.getAsJsonArray(key))
            {
                into.add(e.getAsString());
            }
        }
    }
}
