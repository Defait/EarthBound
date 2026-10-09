package pack.world;

import com.mojang.logging.LogUtils;
import net.minecraft.core.registries.Registries;
import net.minecraft.world.level.levelgen.placement.PlacementModifierType;
import net.minecraft.world.level.levelgen.structure.StructureType;
import net.minecraft.world.level.levelgen.structure.placement.StructurePlacementType;
import net.minecraft.world.level.levelgen.structure.templatesystem.StructureProcessorType;
import net.minecraft.world.level.storage.loot.predicates.LootItemConditionType;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.fml.common.Mod;
import net.neoforged.neoforge.common.NeoForge;
import net.neoforged.neoforge.event.AddReloadListenerEvent;
import net.neoforged.neoforge.event.server.ServerStoppingEvent;
import net.neoforged.neoforge.registries.DeferredHolder;
import net.neoforged.neoforge.registries.DeferredRegister;
import org.slf4j.Logger;
import pack.world.geo.GeographicPlacement;
import pack.world.geo.RegionPlacement;
import pack.world.geo.SiteGuard;
import pack.world.keepclear.KeepClear;
import pack.world.keepclear.KeepClearFilter;
import pack.world.keepclear.KeepClearReloadListener;
import pack.world.loot.ClimateCondition;
import pack.world.materials.LocalMaterialsProcessor;
import pack.world.npc.NpcFixupProcessor;
import pack.world.structure.GuardedJigsawStructure;
import pack.world.skin.SkinReloadListener;

/**
 * The pack's structure helpers (docs/lived-in.md):
 * <ul>
 *     <li>{@code pack_world:local_materials}: placeholder TFC blocks become the local rock, wood, soil and sand;</li>
 *     <li>{@code pack_world:npc_fixup}: Easy NPC data in templates loses the author's owner, home and UUIDs;</li>
 *     <li>{@code pack_world:geographic}: one structure at a real latitude and longitude (TFC: Real World);</li>
 *     <li>{@code pack_world:region}: structures that start inside real-world regions (polygons of latitude and longitude) where TFC's climate allows;</li>
 *     <li>{@code pack_world:guarded_jigsaw}: a jigsaw structure that refuses steep or wet ground;</li>
 *     <li>{@code pack_world:climate}: a loot condition on TFC's climate at the chest;</li>
 *     <li>{@code pack_world:keep_clear} and the keep-clear data ({@code data/NAMESPACE/pack_world/keep_clear}): TFC's forests and boulders
 *     stay out of structures, and other mods' structure pieces out of the pack's villages (two more mixins: TFC's {@code ForestFeature},
 *     and a wrap in {@code StructureStart.placeInChunk});</li>
 *     <li>the structure skin ({@code data/NAMESPACE/pack_world/structure_skin}): other mods' structures, rewritten to local TFC materials
 *     after they are placed (one mixin, into {@code StructureStart.placeInChunk}).</li>
 * </ul>
 * Code only: every structure, pool, processor list and loot table is data in kubejs/data/pack.
 */
@Mod(PackWorld.MOD_ID)
public final class PackWorld
{
    public static final String MOD_ID = "pack_world";
    public static final Logger LOGGER = LogUtils.getLogger();

    public static final DeferredRegister<StructureProcessorType<?>> PROCESSORS = DeferredRegister.create(Registries.STRUCTURE_PROCESSOR, MOD_ID);
    public static final DeferredRegister<StructurePlacementType<?>> PLACEMENTS = DeferredRegister.create(Registries.STRUCTURE_PLACEMENT, MOD_ID);
    public static final DeferredRegister<StructureType<?>> STRUCTURE_TYPES = DeferredRegister.create(Registries.STRUCTURE_TYPE, MOD_ID);
    public static final DeferredRegister<LootItemConditionType> LOOT_CONDITIONS = DeferredRegister.create(Registries.LOOT_CONDITION_TYPE, MOD_ID);
    public static final DeferredRegister<PlacementModifierType<?>> PLACEMENT_MODIFIERS = DeferredRegister.create(Registries.PLACEMENT_MODIFIER_TYPE, MOD_ID);

    public static final DeferredHolder<StructureProcessorType<?>, StructureProcessorType<LocalMaterialsProcessor>> LOCAL_MATERIALS =
        PROCESSORS.register("local_materials", () -> () -> LocalMaterialsProcessor.CODEC);
    public static final DeferredHolder<StructureProcessorType<?>, StructureProcessorType<NpcFixupProcessor>> NPC_FIXUP =
        PROCESSORS.register("npc_fixup", () -> () -> NpcFixupProcessor.CODEC);
    public static final DeferredHolder<StructurePlacementType<?>, StructurePlacementType<GeographicPlacement>> GEOGRAPHIC =
        PLACEMENTS.register("geographic", () -> () -> GeographicPlacement.CODEC);
    public static final DeferredHolder<StructurePlacementType<?>, StructurePlacementType<RegionPlacement>> REGION =
        PLACEMENTS.register("region", () -> () -> RegionPlacement.CODEC);
    public static final DeferredHolder<StructureType<?>, StructureType<GuardedJigsawStructure>> GUARDED_JIGSAW =
        STRUCTURE_TYPES.register("guarded_jigsaw", () -> () -> GuardedJigsawStructure.CODEC);
    public static final DeferredHolder<PlacementModifierType<?>, PlacementModifierType<KeepClearFilter>> KEEP_CLEAR =
        PLACEMENT_MODIFIERS.register("keep_clear", () -> () -> KeepClearFilter.CODEC);
    public static final DeferredHolder<LootItemConditionType, LootItemConditionType> CLIMATE =
        LOOT_CONDITIONS.register("climate", () -> new LootItemConditionType(ClimateCondition.CODEC));

    public PackWorld(IEventBus modBus)
    {
        PROCESSORS.register(modBus);
        PLACEMENTS.register(modBus);
        STRUCTURE_TYPES.register(modBus);
        LOOT_CONDITIONS.register(modBus);
        PLACEMENT_MODIFIERS.register(modBus);
        NeoForge.EVENT_BUS.addListener(SiteGuard::onLevelLoad);
        NeoForge.EVENT_BUS.addListener(SiteGuard::onLevelUnload);
        NeoForge.EVENT_BUS.addListener(SiteGuard::onRegisterCommands);
        // what keep-clear did and cost this run (the pregen and test logs keep it)
        NeoForge.EVENT_BUS.addListener((ServerStoppingEvent event) -> {
            final var stats = KeepClear.stats();
            if (stats.values().stream().anyMatch(v -> v > 0))
            {
                LOGGER.info("pack_world keep-clear stats: {}", stats);
            }
        });
        NeoForge.EVENT_BUS.addListener((AddReloadListenerEvent event) -> {
            event.addListener(new SkinReloadListener());
            event.addListener(new KeepClearReloadListener());
        });
    }
}
