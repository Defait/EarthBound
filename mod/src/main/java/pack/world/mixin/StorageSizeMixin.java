package pack.world.mixin;

import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.ItemStack;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Pseudo;
import org.spongepowered.asm.mixin.Unique;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;
import pack.world.storage.StorageSize;

/**
 * Makes Sophisticated Core's storage inventory refuse what a TFC chest refuses ({@link StorageSize}). {@code InventoryHandler} is the item
 * handler under every Sophisticated Storage block (chests, barrels, limited barrels, shulker boxes, their item form and the Create
 * integration's moving storage) and under Sophisticated Backpacks, so one mixin covers them all, and every insertion path goes through one of
 * the two methods wrapped here: {@code isItemValid} (slots, shift-click, hoppers, funnels, AE2 and every {@code ItemStackHandler.insertItem}
 * caller) and the private {@code insertItemInternal} (the handler's own insert, which upgrades such as pickup and magnet use). Taking items out,
 * sorting and loading a saved inventory do not go through either, so what a storage already holds stays there and can be taken out.
 *
 * <p>Backpacks (handlers whose class is in Sophisticated Backpacks' package, matched by name) also take tools: {@link StorageSize}.
 *
 * <p>The mod is not required: {@code @Pseudo} makes the mixin a no-op when Sophisticated Core is not installed, and {@code require = 0}
 * does the same if an update renames either method (the rule is then simply off, which the pack's check in tools/smoke_checks.js reports).
 */
@Pseudo
@Mixin(targets = "net.p3pp3rf1y.sophisticatedcore.inventory.InventoryHandler", remap = false)
public abstract class StorageSizeMixin
{
    /** Sophisticated Backpacks' handler classes live in this package; matched by name so nothing here refers to that mod. */
    @Unique
    private Boolean pack_world$backpack;

    @Unique
    private boolean pack_world$accepts(ItemStack stack)
    {
        if (pack_world$backpack == null)
        {
            pack_world$backpack = getClass().getName().startsWith("net.p3pp3rf1y.sophisticatedbackpacks.");
        }
        return StorageSize.accepts(stack, pack_world$backpack);
    }

    @Inject(method = "isItemValid(ILnet/minecraft/world/item/ItemStack;Lnet/minecraft/world/entity/player/Player;)Z",
        at = @At("HEAD"), cancellable = true, require = 0)
    private void pack_world$valid(int slot, ItemStack stack, Player player, CallbackInfoReturnable<Boolean> cir)
    {
        if (!pack_world$accepts(stack))
        {
            cir.setReturnValue(false);
        }
    }

    @Inject(method = "insertItemInternal(ILnet/minecraft/world/item/ItemStack;Z)Lnet/minecraft/world/item/ItemStack;",
        at = @At("HEAD"), cancellable = true, require = 0)
    private void pack_world$insert(int slot, ItemStack stack, boolean simulate, CallbackInfoReturnable<ItemStack> cir)
    {
        if (!pack_world$accepts(stack))
        {
            cir.setReturnValue(stack);
        }
    }
}
