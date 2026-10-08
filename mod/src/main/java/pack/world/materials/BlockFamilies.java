package pack.world.materials;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.Property;
import org.jetbrains.annotations.Nullable;

/**
 * TFC names every material variant by a fixed pattern, so one parser covers every shape:
 * <pre>
 *   rock  tfc:rock/&lt;variant&gt;/&lt;rock&gt;[_stairs|_slab|_wall]      ore  tfc:ore/&lt;ore&gt;/&lt;rock&gt;, tfc:deposit/&lt;mineral&gt;/&lt;rock&gt;
 *   wood  tfc:wood/&lt;variant&gt;[/&lt;metal&gt;]/&lt;wood&gt;[_stairs|_slab]
 *   soil  tfc:&lt;soil block&gt;/&lt;order&gt;[_stairs|_slab|_wall]          sand tfc:&lt;sand block&gt;/&lt;colour&gt;[...]
 * </pre>
 */
public final class BlockFamilies
{
    public static final List<String> ROCKS = List.of("granite", "diorite", "gabbro", "shale", "claystone", "limestone", "conglomerate",
        "dolomite", "chert", "chalk", "tuff", "rhyolite", "basalt", "andesite", "dacite", "quartzite", "slate", "phyllite", "schist",
        "gneiss", "marble");
    /** Rocks with a rock anvil. */
    public static final Set<String> IGNEOUS = Set.of("granite", "diorite", "gabbro", "rhyolite", "basalt", "andesite", "dacite");
    /** Raw or cobble of these is andesite alloy rock (#pack:andesite_alloy_rock, kubejs/server_scripts/create/entry.js). */
    public static final Set<String> ALLOY_ROCKS = Set.of("andesite", "basalt", "dacite", "rhyolite", "diorite");
    public static final List<String> WOODS = List.of("acacia", "ash", "aspen", "birch", "blackwood", "chestnut", "douglas_fir", "hickory",
        "kapok", "mangrove", "maple", "oak", "palm", "pine", "rosewood", "sequoia", "spruce", "sycamore", "white_cedar", "willow");
    public static final List<String> SOILS = List.of("entisol", "aridisol", "oxisol", "fluvisol", "andisol", "podzol", "alfisol", "mollisol");
    public static final List<String> SANDS = List.of("brown", "white", "black", "red", "yellow", "green", "pink");

    static final Set<String> SOIL_BLOCKS = Set.of("grass", "dirt", "coarse_dirt", "rooted_dirt", "mud", "clay", "clay_grass", "duff",
        "clay_duff", "farmland", "grass_path", "mud_bricks", "drying_bricks", "muddy_roots");
    static final Set<String> SAND_BLOCKS = Set.of("sand", "raw_sandstone", "smooth_sandstone", "cut_sandstone");
    static final List<String> SHAPES = List.of("_stairs", "_slab", "_wall");

    /**
     * What rough variants of an alloy rock become under the "work" policy: worked stone of the same rock, which keeps the
     * local look but can't feed Create's andesite alloy. {@code null} removes the block.
     */
    static final Map<String, Optional<String>> WORKED = Map.of(
        "raw", Optional.of("smooth"),
        "hardened", Optional.of("smooth"),
        "cobble", Optional.of("cracked_bricks"),
        "mossy_cobble", Optional.of("mossy_bricks"),
        "loose", Optional.empty(),
        "mossy_loose", Optional.empty()
    );
    /** When a rock lacks a variant (anvils exist for igneous rocks only, magma for a few). */
    static final Map<String, String> MISSING_VARIANT = Map.of("anvil", "smooth", "magma", "raw");

    public enum Kind { ROCK, ORE, WOOD, SOIL, SAND }

    /**
     * A block id split around its material: {@code namespace:prefix + joiner + material + shape}.
     *
     * @param namespace "tfc", or "rnr" (Roads and Roofs) for {@link #parseLocal}
     * @param prefix    the path before the last segment, e.g. "rock/cobble", "wood/hanging_sign/copper", "mud_bricks"
     * @param joiner    "/" between prefix and material; "_" for Roads and Roofs' {@code tamped_<soil>}
     * @param shape     "", "_stairs", "_slab" or "_wall" ("_mud" for tamped soil)
     */
    public record Parsed(Kind kind, String namespace, String prefix, String joiner, String material, String shape)
    {
        /** A TFC id: {@code tfc:prefix/material shape}. */
        public Parsed(Kind kind, String prefix, String material, String shape)
        {
            this(kind, "tfc", prefix, "/", material, shape);
        }

        /** The rock variant ("cobble", "bricks", ...) for rock ids, else the first path segment. */
        public String variant()
        {
            final int slash = prefix.indexOf('/');
            return slash < 0 ? prefix : prefix.substring(slash + 1);
        }

        public ResourceLocation with(String newMaterial)
        {
            return ResourceLocation.fromNamespaceAndPath(namespace, prefix + joiner + newMaterial + shape);
        }

        /** A rock id with another variant and material, e.g. rock/cobble/granite_stairs -> rock/cracked_bricks/basalt_stairs. */
        public ResourceLocation withRock(String variant, String rock)
        {
            return ResourceLocation.fromNamespaceAndPath(namespace, "rock/" + variant + "/" + rock + shape);
        }
    }

    private BlockFamilies() {}

    /** A stable hash of a block position (the same mix as vanilla's deprecated Mth.getSeed). */
    public static long positionSeed(int x, int y, int z)
    {
        long seed = (long) (x * 3129871) ^ (long) z * 116129781L ^ (long) y;
        seed = seed * seed * 42317861L + seed * 11L;
        return seed >> 16;
    }

    /** Roads and Roofs' rock families: {@code rnr:rock/<variant>/<rock>[_stairs|_slab]}. */
    static final Set<String> RNR_ROAD_VARIANTS = Set.of("cobbled_road", "flagstones", "gravel_road", "macadam_road", "sett_road", "over_height_gravel");

    /**
     * {@link #parse}, and Roads and Roofs blocks as well: shingles {@code rnr:wood/shingles/<wood>[_stairs|_slab]}, road rock
     * {@code rnr:rock/<variant>/<rock>[_stairs|_slab]} and tamped soil {@code rnr:tamped_<soil>[_mud]}. Kept apart from
     * {@link #parse} so that the structure skin's implicit rules (alloy rock and the like) stay about TFC's own blocks.
     */
    @Nullable
    public static Parsed parseLocal(ResourceLocation id)
    {
        if (!"rnr".equals(id.getNamespace()))
        {
            return parse(id);
        }
        final String path = id.getPath();
        if (path.startsWith("tamped_"))
        {
            String base = path.substring("tamped_".length());
            String shape = "";
            if (base.endsWith("_mud"))
            {
                shape = "_mud";
                base = base.substring(0, base.length() - 4);
            }
            return SOILS.contains(base) ? new Parsed(Kind.SOIL, "rnr", "tamped", "_", base, shape) : null;
        }
        final int last = path.lastIndexOf('/');
        if (last < 0)
        {
            return null;
        }
        final String prefix = path.substring(0, last);
        String base = path.substring(last + 1);
        String shape = "";
        for (String s : List.of("_stairs", "_slab"))
        {
            if (base.endsWith(s))
            {
                shape = s;
                base = base.substring(0, base.length() - s.length());
                break;
            }
        }
        if (prefix.equals("wood/shingles") && WOODS.contains(base))
        {
            return new Parsed(Kind.WOOD, "rnr", prefix, "/", base, shape);
        }
        if (prefix.startsWith("rock/") && prefix.indexOf('/', 5) < 0 && RNR_ROAD_VARIANTS.contains(prefix.substring(5)) && ROCKS.contains(base))
        {
            return new Parsed(Kind.ROCK, "rnr", prefix, "/", base, shape);
        }
        return null;
    }

    @Nullable
    public static Parsed parse(ResourceLocation id)
    {
        if (!"tfc".equals(id.getNamespace()))
        {
            return null;
        }
        final String path = id.getPath();
        final int last = path.lastIndexOf('/');
        if (last < 0)
        {
            return null;
        }
        final String prefix = path.substring(0, last);
        String base = path.substring(last + 1);
        String shape = "";
        for (String s : SHAPES)
        {
            if (base.endsWith(s))
            {
                shape = s;
                base = base.substring(0, base.length() - s.length());
                break;
            }
        }
        final String[] segments = path.split("/");
        final String head = segments[0];
        if (segments.length == 3 && head.equals("rock") && ROCKS.contains(base))
        {
            return new Parsed(Kind.ROCK, prefix, base, shape);
        }
        if (segments.length == 3 && (head.equals("ore") || head.equals("deposit")) && ROCKS.contains(base) && shape.isEmpty())
        {
            return new Parsed(Kind.ORE, prefix, base, shape);
        }
        if (segments.length >= 3 && head.equals("wood") && WOODS.contains(base))
        {
            return new Parsed(Kind.WOOD, prefix, base, shape);
        }
        if (segments.length == 2 && SOIL_BLOCKS.contains(head) && SOILS.contains(base))
        {
            return new Parsed(Kind.SOIL, prefix, base, shape);
        }
        if (segments.length == 2 && SAND_BLOCKS.contains(head) && SANDS.contains(base))
        {
            return new Parsed(Kind.SAND, prefix, base, shape);
        }
        return null;
    }

    /** The target's default state with every property of the source whose name and value it also has. */
    public static BlockState copyProperties(BlockState from, BlockState to)
    {
        BlockState out = to;
        for (Property<?> property : from.getProperties())
        {
            final Property<?> target = to.getBlock().getStateDefinition().getProperty(property.getName());
            if (target != null)
            {
                out = setByName(out, target, nameOf(from, property));
            }
        }
        return out;
    }

    private static <T extends Comparable<T>> String nameOf(BlockState state, Property<T> property)
    {
        return property.getName(state.getValue(property));
    }

    private static <T extends Comparable<T>> BlockState setByName(BlockState state, Property<T> property, String value)
    {
        return property.getValue(value).map(v -> state.setValue(property, v)).orElse(state);
    }
}
