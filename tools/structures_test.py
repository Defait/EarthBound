"""Check the pack's structures (docs/lived-in.md) on a fresh headless world.

Usage (from the repo root):
    tools/.venv/Scripts/python tools/structures_test.py [--data DIR] [--jar PATH] [--places Rome,Stockholm,...]
                                                       [--only cairn,barrow,...] [--natural-only] [--no-sync] [--keep-world]

Boots the test server on a new world with a dev-only KubeJS script (tools/structures_test.js) that:
  - maps every placeholder block of every template through the mod's own code (pack_world's PackWorldApi.mapId) for every
    TFC rock, wood, soil and sand: every result exists, nothing stays a placeholder, no andesite alloy rock appears;
  - generates every structure the way /place does at a few real places with different rock and climate, and reads its box
    back: leaked placeholders, vanilla blocks, rough alloy rock, rock and wood other than the local ones, floating
    (ground-layer columns over 2+ blocks of air; without terrain adaptation, which only applies to new chunks);
  - finds natural starts of each structure near the places and generates their chunks normally (terrain adaptation,
    decoration, processors as in play), with the same checks;
  - rolls every pack loot table 200 times (loads, gives items, nothing on the deny-list);
  - places a test-only structure (pack_test:npc, a world datapack) holding the trader as an entity and the smith as a
    single spawner, twice: each copy gets its own NPC UUID, no owner and a home where it stands, and keeps its trades and
    dialog;
  - checks each real-world site's start chunk and that it is dry land;
  - estimates each structure's density around the places, without generating anything.
Exit code 1 on any failure. Results: tools/.data/reports/structures-<timestamp>.json.

--data DIR tests a staged build (tools/structures/build.py --out DIR) as a world datapack instead of kubejs/data;
--jar PATH adds a pack_world jar for this run only (before it is in the pack). Uses the test server: not while another
tool does.
"""
import argparse
import glob
import json
import os
import re
import shutil
import sys
import time

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(TOOLS, "structures"))
from mclib.paths import DATA_DIR, REPO, utf8_console  # noqa: E402
from mclib.server import DONE_RE, TestServer  # noqa: E402

import nbt as N  # noqa: E402

WORLD = "world-structures"
RESULT_RE = re.compile(r"\[structures-test\] (PASS|FAIL|NOTE|done|density)(.*)")
DEFAULT_PLACES = [("Rome", 41.89, 12.51), ("Stockholm", 59.33, 18.07), ("Lhasa", 29.65, 91.17), ("Manaus", -3.12, -60.02),
                  ("Cairo", 30.04, 31.24), ("Kansas", 38.5, -98.0)]
PLACEHOLDER = {"rock": re.compile(r"^tfc:(rock|ore|deposit)/.*/granite(_stairs|_slab|_wall)?$"),
               "wood": re.compile(r"^tfc:wood/.*/oak(_stairs|_slab)?$"),
               "soil": re.compile(r"^tfc:[a-z_]+/alfisol(_stairs|_slab|_wall)?$"),
               "sand": re.compile(r"^tfc:(sand|raw_sandstone|smooth_sandstone|cut_sandstone)/yellow(_stairs|_slab|_wall)?$")}


def job(data_root, places):
    cat = json.load(open(os.path.join(TOOLS, "structures", "catalogue.json"), encoding="utf-8"))
    sdir = os.path.join(data_root, "kubejs", "data", "pack", "structure")
    structures, ids, templates = [], set(), {}
    for sid in sorted(os.listdir(sdir)) if os.path.isdir(sdir) else []:
        if sid == "site":
            continue
        doc = json.load(open(os.path.join(data_root, "kubejs", "data", "pack", "worldgen", "structure", sid + ".json"), encoding="utf-8"))
        structures.append({"id": sid, "ground": -int(doc["start_height"]["absolute"])})
        for f in glob.glob(os.path.join(sdir, sid, "*.nbt")):
            root = N.read(f)
            ids |= {p["Name"] for p in root["palette"]}
            # every non-air block the template places, relative to its origin, for checking the world at exactly those spots
            # (and whether the template itself fills the spot below: then it isn't resting on terrain, e.g. a tunnel roof)
            filled = {(int(b["pos"][0]), int(b["pos"][1]), int(b["pos"][2])) for b in root["blocks"]}
            templates[f"pack:{sid}/{os.path.basename(f)[:-4]}"] = [
                [int(b["pos"][0]), int(b["pos"][1]), int(b["pos"][2]), root["palette"][b["state"]]["Name"],
                 1 if (int(b["pos"][0]), int(b["pos"][1]) - 1, int(b["pos"][2])) in filled else 0]
                for b in root["blocks"] if root["palette"][b["state"]]["Name"] != "minecraft:air"]
    placeholders = {k: sorted(i for i in ids if rx.match(i)) for k, rx in PLACEHOLDER.items()}
    loot_dir = os.path.join(data_root, "kubejs", "data", "pack", "loot_table", "chests")
    tables = sorted("pack:chests/" + f[:-5] for f in os.listdir(loot_dir)) if os.path.isdir(loot_dir) else []
    return {"structures": structures, "places": [list(p) for p in places], "placeholders": placeholders,
            "deny": cat["loot_caps"]["deny"], "lootTables": tables, "densityRadius": 8000, "templates": templates,
            "naturalPerStructure": 3}


def install_datapack(srv, data_root):
    """The staged kubejs/data/pack as a datapack of the new world (enabled when the world is created)."""
    dp = srv.path(WORLD, "datapacks", "pack-structures")
    shutil.rmtree(dp, ignore_errors=True)
    shutil.copytree(os.path.join(data_root, "kubejs", "data"), os.path.join(dp, "data"))
    with open(os.path.join(dp, "pack.mcmeta"), "w", encoding="utf-8") as f:
        json.dump({"pack": {"pack_format": 48, "description": "staged pack structures (tools/structures_test.py)"}}, f)


def install_npc_fixture(srv):
    """A test-only structure, pack_test:npc: a floor, a chest, the trader as an entity (an npc:trader marker) and the smith as a
    single spawner (npc:smith:spawner), built and post-processed by tools/structures exactly like a hand-built template."""
    import build as B
    import shapes as SH
    t = SH.Template(ground=0)
    t.fill(0, 0, 0, 6, 0, 6, SH.rock("smooth"))
    t.set(1, 1, 1, SH.wood("chest"), facing="north", type="single")
    t.set(3, 1, 3, "minecraft:structure_block", {"metadata": "npc:trader", "mode": "DATA"}, mode="data")
    t.set(5, 1, 5, "minecraft:structure_block", {"metadata": "npc:smith:spawner", "mode": "DATA"}, mode="data")
    cat = json.load(open(B.CATALOGUE, encoding="utf-8"))
    npcs = {k: B.npc_data(k, v)[1] for k, v in cat["npcs"].items() if not k.startswith("_")}
    problems = B.Problems()
    root = B.post_pass("test/npc", t.to_nbt(), "pack:chests/trading_post", npcs, problems)
    if problems:
        raise SystemExit("NPC fixture: " + "; ".join(problems))
    dp = srv.path(WORLD, "datapacks", "pack-test")
    shutil.rmtree(dp, ignore_errors=True)
    base = os.path.join(dp, "data", "pack_test")
    os.makedirs(os.path.join(base, "structure"))
    N.write(os.path.join(base, "structure", "npc.nbt"), root)
    for rel, doc in {
        "worldgen/processor_list/npc.json": {"processors": [{"processor_type": "pack_world:local_materials"}, {"processor_type": "pack_world:npc_fixup"}]},
        "worldgen/template_pool/npc.json": {"fallback": "minecraft:empty", "elements": [{"weight": 1, "element": {
            "element_type": "minecraft:single_pool_element", "location": "pack_test:npc", "processors": "pack_test:npc", "projection": "rigid"}}]},
        "worldgen/structure/npc.json": {"type": "minecraft:jigsaw", "biomes": "#pack:overworld", "step": "surface_structures", "spawn_overrides": {},
                                        "terrain_adaptation": "none", "start_pool": "pack_test:npc", "size": 1, "start_height": {"absolute": 0},
                                        "project_start_to_heightmap": "WORLD_SURFACE_WG", "max_distance_from_center": 16, "use_expansion_hack": False},
    }.items():
        path = os.path.join(base, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        json.dump(doc, open(path, "w", encoding="utf-8"))
    with open(os.path.join(dp, "pack.mcmeta"), "w", encoding="utf-8") as f:
        json.dump({"pack": {"pack_format": 48, "description": "NPC fixture (tools/structures_test.py)"}}, f)


def main():
    utf8_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", help="a staged build root (tools/structures/build.py --out DIR); default: the pack's kubejs/data")
    ap.add_argument("--jar", help="a pack_world jar to add for this run only")
    ap.add_argument("--places", help="comma-separated names from the default list (Rome, Stockholm, Lhasa, Manaus, Cairo, Kansas)")
    ap.add_argument("--only", help="comma-separated structure ids to check (default: all)")
    ap.add_argument("--natural-only", action="store_true", help="skip the /place-style copies")
    ap.add_argument("--no-sync", action="store_true", help="skip packwiz-installer")
    ap.add_argument("--keep-world", action="store_true", help="keep the test world afterwards")
    ap.add_argument("--timeout", type=int, default=1800, help="seconds to wait")
    args = ap.parse_args()

    places = DEFAULT_PLACES
    if args.places:
        want = {p.strip().lower() for p in args.places.split(",")}
        places = [p for p in DEFAULT_PLACES if p[0].lower() in want]
    data_root = os.path.abspath(args.data) if args.data else REPO
    j = job(data_root, places)
    if args.only:
        keep = {x.strip() for x in args.only.split(",")}
        j["structures"] = [x for x in j["structures"] if x["id"] in keep]
    j["naturalOnly"] = args.natural_only
    if not j["structures"] and not args.only:
        raise SystemExit(f"No structures under {data_root}/kubejs/data/pack: run tools/structures/build.py first")
    src = open(os.path.join(TOOLS, "structures_test.js"), encoding="utf-8").read()
    src = re.sub(r"/\*JOB\*/.*?/\*END\*/", "/*JOB*/ " + json.dumps(j) + " /*END*/", src, flags=re.S)
    os.makedirs(os.path.join(DATA_DIR, "structures"), exist_ok=True)
    script = os.path.join(DATA_DIR, "structures", "structures_test.js")
    with open(script, "w", encoding="utf-8") as f:
        f.write(src)

    srv = TestServer()
    srv.ensure_installed()
    if not args.no_sync:
        srv.sync_pack()
    srv.set_extra_mods([os.path.abspath(args.jar)] if args.jar else [])
    srv.set_dev_scripts({"structures_test.js": script})
    shutil.rmtree(srv.path(WORLD), ignore_errors=True)
    if args.data:
        install_datapack(srv, data_root)
    install_npc_fixture(srv)
    shutil.rmtree(srv.path("local", "structures-test"), ignore_errors=True)
    srv.write_properties(WORLD, "structures")
    print(f"Starting server ({len(j['structures'])} structures, {len(places)} places)...")
    srv.start()
    finished = srv.wait_for(r"\[structures-test\] done|" + DONE_RE.pattern, args.timeout)
    if finished and "structures-test" not in finished.group(0):
        finished = srv.wait_for(r"\[structures-test\] done", args.timeout)
    srv.set_dev_scripts({})
    srv.set_extra_mods([])
    srv.stop()
    if not args.keep_world:
        shutil.rmtree(srv.path(WORLD), ignore_errors=True)

    failed, ran = 0, False
    for line in srv.lines:
        m = RESULT_RE.search(line)
        if not m:
            continue
        ran = True
        if m.group(1) == "FAIL":
            failed += 1
        print(f"  {m.group(1)}{m.group(2)}")
    res = os.path.join(srv.root, "local", "structures-test", "results.json")
    if os.path.exists(res):
        os.makedirs(os.path.join(DATA_DIR, "reports"), exist_ok=True)
        out = os.path.join(DATA_DIR, "reports", time.strftime("structures-%Y%m%d-%H%M%S.json"))
        shutil.copy(res, out)
        print(f"Results: {out}")
    if not ran or not finished:
        print("The checks didn't run or didn't finish; see tools/.server/logs/latest.log")
        return 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
