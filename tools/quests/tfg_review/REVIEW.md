# Porting TerraFirmaGreg quests into this pack's quest book: review brief

You are reviewing quests from TerraFirmaGreg (TFG), a TerraFirmaCraft + GregTech modpack for Minecraft
1.20.1 (LGPL-3.0), to merge them into this pack's FTB Quests book, "The Route". This pack is a
different pack: Minecraft 1.21.1, NeoForge, TerraFirmaCraft 4 (TFG has TFC 3), TFC: Real World,
GregTech CEu Modern 8.0, Create 6, Create Aeronautics, and a KubeJS integration layer with its own
progression gates. Many TFG quests fit as they are; some need their text or tasks corrected for this
pack; some don't fit at all. Your job is a decision for every quest in your chapter(s).

Work only in the files named below; do not edit anything in the repository. Repo root:
C:\Users\jdreise\Documents\MC (Windows; use the Bash tool with POSIX paths like /c/Users/jdreise/Documents/MC).

## Inputs

- Your chapter extract(s): `tools/.data/tfg/extract/<chapter>.json`. Each quest has `key` (keep it),
  `title`, `subtitle`, `desc` (lines; FTB Quests formatting such as `&l`/`&r`, `\n`, `{@pagebreak}`,
  `{image:...}`), `tasks`, `deps` (keys of other TFG quests, possibly in other chapters),
  `deps_outside_ported_chapters` (TFG quests in chapters that are not being ported; ignore those deps),
  and `notes` from the converter (items/tags missing from this pack, dropped images, TFG field guide
  pages, gamestage tasks turned into checkmarks).
- Task forms: `{"item": "ns:id", "count": n}`; `{"filter": "or(item_tag(c:x)item(ns:y))", "any": [...]}`
  (an FTB Filter System expression; `any` lists its items/tags for checking); `{"type": "checkmark"}`;
  `{"type": "observation", ...}`, `{"type": "kill", ...}`, `{"type": "dimension", ...}`, `{"type": "biome", ...}`;
  `"optional": true` on a task.
- The pack's design: `docs/design.md` (read the Decisions table, Known gaps, Create addons). It is the
  authority on how progression works here.
- The pack's current book: `tools/quests/route.json` (chapters welcome, stone, bronze, create, iron,
  steam, lv, airships). Its quests carry pack-specific notes about the gates.
- Mods in the pack: `tools/quests/tfg_review/pack_mods.txt`. Not in the pack (examples TFG has): Greate
  (TFG's GregTech-tiered Create machines), Firmalife, Firmaciv, Alekiships, AE2, ComputerCraft,
  Ad Astra (space, Moon, Mars), TACZ (guns), Sophisticated Backpacks, Vintage Improvements, Steam Powered,
  Create Crafts & Additions, TFC Lunchbox, Exposure, Waterflasks, TFC Textile, rnr (roads), tfg:* items.
- Pack lookup tool (fast; use it a lot):
  `tools/.venv/Scripts/python tools/quests/pack_query.py item ID [ID ...]` (name, progression step,
  recipes that make it), `search TEXT`, `tag TAG`, `uses ID`. "step" is the progression checker's
  distance from a fresh world; "unreachable" means the checker found no route (a strong hint the thing
  isn't obtainable here, e.g. GregTech-only ores, Nether/End/space items; but the checker doesn't model
  everything, so look at `made_by` before concluding).

## Key differences from TFG (from docs/design.md; check there for detail)

- GregTech's ore veins are off. GregTech materials come from TFC ores: the macerator turns TFC ore
  pieces into GregTech crushed ore (double TFC's yield), and from crushed ore GregTech's usual chain
  applies. GregTech-only minerals (bauxite, ilmenite, ...) have no veins here; quests about mining them
  don't apply.
- Create opens in the bronze age: andesite alloy from TFC igneous extrusive rock + zinc or bronze
  nuggets; Create uses TFC sheets for plates; the mechanical press takes a wrought iron double sheet;
  heavy machines (press, mixer, deployer, saw) need wrought iron sheets; belts take leather or burlap.
  Plain Create machines, no Greate tiers.
- Woodencog: a basin on a TFC charcoal forge is Create's heat source (750 °C heated, 2000 °C with bellows
  superheated); fans heat/cool TFC items; basins alloy TFC metals. Blaze burners need the Nether.
- GregTech steam: every boiler needs a Create mechanical pump; GregTech's vanilla-furnace ingredient is
  TFC fire bricks. High-pressure steam and LV need TFC steel.
- Iron and steel stay TFC milestones: wrought iron only from the bloomery (smelted/melted iron becomes
  cast iron); steel only from TFC pig iron (TFC blast furnace); GregTech's primitive blast furnace refines
  pig iron into steel. The electric blast furnace is built from TFC's blast furnace.
- GregTech's LV components are built from Create parts: motors around Create shafts, pumps around a
  Create mechanical pump, pistons with a Create cogwheel. Create's press makes GregTech plates, the saw
  makes wires, crushing wheels/millstone make GregTech crushed ore.
- All GregTech power comes from boilers/steam turbines and GregTech generators (no Create electricity mods).
- Airships (Create Aeronautics) unlock with brass. The world is a 20 m/block real Earth (TFC: Real World).
- TFC 4 renamed some things (soils are now alfisol, andisol, aridisol, entisol, fluvisol, mollisol,
  oxisol, podzol; 1.20 `forge:` tags are `c:` tags). Always check ids with the lookup tool.

## Decide, for every quest

- `keep`: fits as is (text and tasks correct here). Minor wording fixes are fine via `edit`.
- `edit`: fits, but text and/or tasks need changes for this pack. Give the full corrected `title`,
  `subtitle`, `desc` (and `tasks`/`deps` if they change).
- `merge`: the same milestone as a quest already in route.json (e.g. TFG's bloomery quest vs route's
  `bloomery`). Give `merge_into` (the route key) and a combined `desc` for that route quest that keeps the
  route quest's pack-specific facts and adds TFG's useful detail. The route quest keeps its key, title
  and task unless you give replacements.
- `drop`: doesn't fit (needs mods/items/dimensions not in the pack, describes TFG-only mechanics,
  contradicts the design, pure TFG meta such as its field guide/Discord/wiki, or redundant). Give a reason.

Rules for kept/edited text:
- Verify concrete claims (what a recipe needs, which machine makes what, tiers, numbers) with the lookup
  tool; correct them or cut them. General TFC/GregTech advice that's true in both packs can stay. Don't
  invent mechanics.
- No "TerraFirmaGreg"/"TFG"; say "this pack" or rephrase. No references to TFG's field guide pages,
  Discord or wiki; TFC's own field guide exists, so "see the field guide" in general terms is fine.
- Keep TFG's tone and humour where harmless; keep it concise. Keep FTB Quests formatting codes.
- Item tasks: every item id and tag must exist here (lookup tool). Replace missing ids with the pack's
  equivalent, or drop the task/quest. Filters may only use `item(...)`, `item_tag(...)`, `or(...)`,
  `and(...)`, `not(...)`; drop ids that don't exist from a filter (one unknown id can break it).
- Prefer item tasks the player can actually complete in this pack; a checkmark is fine for "read this"
  or in-world actions.

Also give, for keep/edit: `chapter`: the book chapter the quest goes into. Chapters, in book order:
welcome, stone (Stone and Copper: survival, food, water, knapping, pottery, fire, copper),
bronze (Bronze and Brass: anvils, alloys, bronze tools/armour, brass), create (Create machines),
iron (Iron and Steel: bloomery to steel, blast furnace), steam (GregTech Steam), ore_processing
(GregTech ore processing), lv (Electricity / LV), power (GregTech power: generators, cables, batteries,
transformers across tiers), airships, mv, hv, ev, tools_tips (tips: tools, storage, quality of life),
combat_tips (tips: combat, armour, mobs), elements (chemical elements collection). TFG's own chapter
usually maps straight across (TFG Stone Age -> stone, Metal Age -> bronze/iron by era, Steam Age ->
steam, ore processing -> ore_processing, LV -> lv, GregTech Energy -> power, MV/HV/EV -> mv/hv/ev,
tips -> tools_tips/combat_tips, elements -> elements); split by era where TFG's chapter spans two of ours.

Dependencies: keep TFG's `deps` (keys) unless wrong; you may add route.json keys as deps (e.g. a TFG LV
quest that needs the route's `lv_motor`). Dependencies on quests you drop are re-linked automatically
to their own prerequisites, so you don't need to fix those.

## Output

Write `tools/quests/tfg_review/<chapter>.json` for each of your chapters:

```json
{
  "chapter": "<chapter>",
  "decisions": [
    {"key": "stone_age.find_rock", "action": "keep", "chapter": "stone"},
    {"key": "...", "action": "edit", "chapter": "stone", "reason": "...", "title": "...", "subtitle": "...",
     "desc": ["...", "..."], "tasks": [ ... ], "deps": [ ... ]},
    {"key": "...", "action": "merge", "merge_into": "bloomery", "reason": "...", "desc": ["..."]},
    {"key": "...", "action": "drop", "reason": "..."}
  ]
}
```

Every quest in the extract needs exactly one decision. `title`/`subtitle`/`desc`/`tasks`/`deps` in an
`edit` are full replacements (omit the ones that stay as in the extract). Validate the file with
`tools/.venv/Scripts/python -c "import json; json.load(open('tools/quests/tfg_review/<chapter>.json', encoding='utf-8'))"`.
Finish with a short summary: counts per action, notable drops, anything you were unsure about.
