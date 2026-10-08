package pack.world;

import com.mojang.logging.LogUtils;
import net.minecraft.core.registries.Registries;
import net.minecraft.world.level.levelgen.structure.placement.StructurePlacementType;
import net.minecraft.world.level.levelgen.structure.templatesystem.StructureProcessorType;
import net.minecraft.world.level.storage.loot.predicates.LootItemConditionType;
import net.neoforged.bus.api.IEventBus;
import net.neoforged.fml.common.Mod;
import net.neoforged.neoforge.common.NeoForge;
import net.neoforged.neoforge.event.AddReloadListenerEvent;
import net.neoforged.neoforge.registries.DeferredHolder;
import net.neoforged.neoforge.registries.DeferredRegister;
import org.slf4j.Logger;
import pack.world.geo.GeographicPlacement;
import pack.world.geo.SiteGuard;
import pack.world.loot.ClimateCondition;
import pack.world.materials.LocalMaterialsProcessor;
import pack.world.npc.NpcFixupProcessor;
import pack.world.skin.SkinReloadListener;

/**
 * The pack's structure helpers (docs/lived-in.md):
 * <ul>
 *     <li>{@code pack_world:local_materials}: placeholder TFC blocks become the local rock, wood, soil and sand;</li>
 *     <li>{@code pack_world:npc_fixup}: Easy NPC data in templates loses the author's owner, home and UUIDs;</li>
 *     <li>{@code pack_world:geographic}: one structure at a real latitude and longitude (TFC: Real World);</li>
 *     <li>{@code pack_world:climate}: a loot condition on TFC's climate at the chest;</li>
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
    public static final DeferredRegister<LootItemConditionType> LOOT_CONDITIONS = DeferredRegister.create(Registries.LOOT_CONDITION_TYPE, MOD_ID);

    public static final DeferredHolder<StructureProcessorType<?>, StructureProcessorType<LocalMaterialsProcessor>> LOCAL_MATERIALS =
        PROCESSORS.register("local_materials", () -> () -> LocalMaterialsProcessor.CODEC);
    public static final DeferredHolder<StructureProcessorType<?>, StructureProcessorType<NpcFixupProcessor>> NPC_FIXUP =
        PROCESSORS.register("npc_fixup", () -> () -> NpcFixupProcessor.CODEC);
    public static final DeferredHolder<StructurePlacementType<?>, StructurePlacementType<GeographicPlacement>> GEOGRAPHIC =
        PLACEMENTS.register("geographic", () -> () -> GeographicPlacement.CODEC);
    public static final DeferredHolder<LootItemConditionType, LootItemConditionType> CLIMATE =
        LOOT_CONDITIONS.register("climate", () -> new LootItemConditionType(ClimateCondition.CODEC));

    public PackWorld(IEventBus modBus)
    {
        PROCESSORS.register(modBus);
        PLACEMENTS.register(modBus);
        LOOT_CONDITIONS.register(modBus);
        NeoForge.EVENT_BUS.addListener(SiteGuard::onLevelLoad);
        NeoForge.EVENT_BUS.addListener(SiteGuard::onLevelUnload);
        NeoForge.EVENT_BUS.addListener(SiteGuard::onRegisterCommands);
        NeoForge.EVENT_BUS.addListener((AddReloadListenerEvent event) -> event.addListener(new SkinReloadListener()));
    }
}
