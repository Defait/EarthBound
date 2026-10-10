package pack.world.storage;

import net.dries007.tfc.common.blockentities.TFCChestBlockEntity;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.tags.TagKey;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;

/**
 * TFC's rule for what a chest holds, asked of other mods' storage (docs/design.md, "Sophisticated Backpacks"): an item goes in if TFC's own
 * chest would take it, that is if its TFC size (the item size data, {@code ItemSizeManager}) is no larger than the server config's
 * {@code chestMaximumItemSize}. Nothing here lists items, so the rule follows TFC's config and every item TFC sizes, those of other mods too.
 * One exception, for backpacks only: tools and weapons (the {@code c:tools} item tag, which holds TFC's, GregTech's, vanilla-style and AE2's
 * picks, axes, shovels, hoes, hammers, saws, scythes, swords, maces, knives, spears, shields, bows and the like) are taken, since a backpack is
 * where a player carries spares and its tool swapper upgrade swaps from them. TFC sizes them "very large", so a chest refuses them.
 */
public final class StorageSize
{
    private static final TagKey<Item> TOOLS = TagKey.create(Registries.ITEM, ResourceLocation.fromNamespaceAndPath("c", "tools"));

    private StorageSize() {}

    /**
     * Whether TFC's chest would accept the stack. Fails open: if TFC's config or size data are not there yet (a client before it has joined, a
     * data reload in progress) the stack is accepted, since refusing everything would be worse than refusing nothing for a moment.
     */
    public static boolean accepts(ItemStack stack, boolean backpack)
    {
        if (stack.isEmpty() || (backpack && stack.is(TOOLS)))
        {
            return true;
        }
        try
        {
            return TFCChestBlockEntity.isValid(stack);
        }
        catch (RuntimeException | LinkageError e)
        {
            return true;
        }
    }
}
