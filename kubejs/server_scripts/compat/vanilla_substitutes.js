// Recipes that ask for vanilla items TFC replaces with its own.
//
// - Crafting table: TFC players craft per-wood workbenches instead (tagged
//   c:player_workstations/crafting_tables). Create's mechanical crafter and blueprint, the
//   vanilla crafter and the smithing table asked for minecraft:crafting_table specifically.

ServerEvents.recipes(event => {
  event.replaceInput({}, 'minecraft:crafting_table', '#c:player_workstations/crafting_tables')
})
