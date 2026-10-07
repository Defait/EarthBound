package pack.world.npc;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.UUID;
import com.mojang.serialization.Codec;
import com.mojang.serialization.MapCodec;
import com.mojang.serialization.codecs.RecordCodecBuilder;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.Tag;
import net.minecraft.world.level.LevelReader;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.levelgen.structure.templatesystem.StructurePlaceSettings;
import net.minecraft.world.level.levelgen.structure.templatesystem.StructureProcessor;
import net.minecraft.world.level.levelgen.structure.templatesystem.StructureProcessorType;
import net.minecraft.world.level.levelgen.structure.templatesystem.StructureTemplate;
import net.minecraft.world.level.levelgen.structure.templatesystem.StructureTemplate.StructureBlockInfo;
import net.minecraft.world.level.levelgen.structure.templatesystem.StructureTemplate.StructureEntityInfo;
import pack.world.PackWorld;

/**
 * {@code pack_world:npc_fixup}: Easy NPC data saved into a template still carries the author's world.
 * <ul>
 *     <li>Entities ({@code easy_npc:*}): {@code Owner} (whoever owns an NPC can edit it) and {@code Navigation.Home} (absolute
 *     coordinates of the build site; without it Easy NPC's finalizeSpawn sets home where the NPC is placed) are removed.
 *     Vanilla already drops the entity UUID and assigns a new one.</li>
 *     <li>Spawner block entities ({@code easy_npc:*} blocks): a "single" spawner keys on one entity UUID, so a verbatim copy
 *     would make every placed spawner share one NPC; a missing UUID makes it never spawn. Each placed spawner gets UUIDs
 *     derived from the world seed and its position (stable, unique), and the stored preset loses Owner and Home too.</li>
 * </ul>
 * NBT keys only: no compile dependency on Easy NPC; without it this does nothing (vanilla drops unknown entities and blocks).
 */
public final class NpcFixupProcessor extends StructureProcessor
{
    public static final List<String> DEFAULT_STRIP = List.of("Owner", "Navigation.Home");
    public static final MapCodec<NpcFixupProcessor> CODEC = RecordCodecBuilder.mapCodec(i -> i.group(
        Codec.STRING.listOf().optionalFieldOf("strip", DEFAULT_STRIP).forGetter(p -> p.strip),
        Codec.BOOL.optionalFieldOf("unique_spawner_uuid", true).forGetter(p -> p.uniqueSpawnerUuid)
    ).apply(i, NpcFixupProcessor::new));

    private static final String NAMESPACE = "easy_npc";

    private final List<String> strip;
    private final boolean uniqueSpawnerUuid;

    public NpcFixupProcessor(List<String> strip, boolean uniqueSpawnerUuid)
    {
        this.strip = strip;
        this.uniqueSpawnerUuid = uniqueSpawnerUuid;
    }

    @Override
    protected StructureProcessorType<?> getType()
    {
        return PackWorld.NPC_FIXUP.get();
    }

    @Override
    public StructureBlockInfo process(LevelReader level, BlockPos offset, BlockPos pos, StructureBlockInfo original, StructureBlockInfo current,
                                      StructurePlaceSettings settings, StructureTemplate template)
    {
        if (current.nbt() == null || !NAMESPACE.equals(BuiltInRegistries.BLOCK.getKey(current.state().getBlock()).getNamespace()))
        {
            return current;
        }
        final CompoundTag nbt = current.nbt().copy();
        final long seed = level instanceof WorldGenLevel worldGen ? worldGen.getSeed() : 0L;
        final UUID npc = derived(seed, current.pos(), "npc");
        if (uniqueSpawnerUuid)
        {
            nbt.putUUID("UUID", derived(seed, current.pos(), "spawner"));
        }
        if (nbt.contains("StoredPresetData", Tag.TAG_COMPOUND))
        {
            fix(nbt.getCompound("StoredPresetData"), npc);
        }
        if (nbt.contains("SpawnData", Tag.TAG_COMPOUND) && nbt.getCompound("SpawnData").contains("entity", Tag.TAG_COMPOUND))
        {
            fix(nbt.getCompound("SpawnData").getCompound("entity"), npc);
        }
        return new StructureBlockInfo(current.pos(), current.state(), nbt);
    }

    @Override
    public StructureEntityInfo processEntity(LevelReader level, BlockPos seedPos, StructureEntityInfo rawEntityInfo, StructureEntityInfo entityInfo,
                                             StructurePlaceSettings placementSettings, StructureTemplate template)
    {
        if (!entityInfo.nbt.getString("id").startsWith(NAMESPACE + ":"))
        {
            return entityInfo;
        }
        final CompoundTag nbt = entityInfo.nbt.copy();
        for (String path : strip)
        {
            remove(nbt, path);
        }
        return new StructureEntityInfo(entityInfo.pos, entityInfo.blockPos, nbt);
    }

    private void fix(CompoundTag entity, UUID npc)
    {
        for (String path : strip)
        {
            remove(entity, path);
        }
        if (uniqueSpawnerUuid)
        {
            entity.putUUID("UUID", npc);
        }
    }

    /** Removes a dotted path ("Navigation.Home") from a compound, if present. */
    static void remove(CompoundTag tag, String path)
    {
        final String[] parts = path.split("\\.");
        CompoundTag cursor = tag;
        for (int i = 0; i < parts.length - 1; i++)
        {
            if (!cursor.contains(parts[i], Tag.TAG_COMPOUND))
            {
                return;
            }
            cursor = cursor.getCompound(parts[i]);
        }
        cursor.remove(parts[parts.length - 1]);
    }

    static UUID derived(long seed, BlockPos pos, String kind)
    {
        return UUID.nameUUIDFromBytes(("pack_world:" + seed + ":" + pos.asLong() + ":" + kind).getBytes(StandardCharsets.UTF_8));
    }
}
