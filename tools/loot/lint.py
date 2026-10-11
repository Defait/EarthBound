"""Lint every chest loot table the running pack knows against the pack's eras (docs/lived-in.md "Loot rules").

Usage (from the repo root):
    tools/.venv/Scripts/python tools/loot/lint.py [--rolls N] [--no-sync] [--keep-world] [--results FILE] [--static] [--verbose]

Exit code 1 on any problem; the last line is a single-line summary ("loot lint: PASS ..." or "loot lint: FAIL ...").
Importable: `import lint; ok, summary, problems = lint.run(rolls=300)`.

What it checks (the numbers come from tools/structures/catalogue.json `loot_caps` and the newest recipe dump, like the pack's own
structures; see tools/loot/gen.py):
  * On the test server (tools/loot/loot_test.js, a dev-only KubeJS script; uses the server, so not while another tool does):
    every table in the loot table registry whose type is a chest, archaeology or gift table (vanilla's, GregTech's, Lootr's and
    every mod's; the pack's own `pack:chests/*` and the generated `pack_loot:*` included) is read as loaded and rolled ROLLS times
    through the normal pipeline, so functions and NeoForge's global loot modifiers count. Every item named anywhere in it (also
    nested alternatives, tag entries expanded to their members, and loot-table references followed) and every item that comes out
    must exist, be off the deny-list, and sit under the cap of the table's era (loot.json says the era of the tables it generates,
    the catalogue that of the pack's own; anything else gets the bronze cap). Fishing, barter, shearing, equipment and vault
    tables are checked against the deny-list only.
  * The global loot modifiers the server has active: none may be left of GregTech's nine, and what is left must be what
    loot.json keeps. The jars' modifier lists are read too, so that the override cannot drop another mod's.
  * Tables that cannot generate in this pack (Nether, trial chambers, ancient cities, mods that are not installed ...) are not
    checked, but only when listed in ALLOWED below with a reason; the jars must show that no structure mod uses them, and no
    checked table may point at one.
  * The files tools/loot/gen.py writes are up to date with loot.json, and every table a structure mod names exists.
"""
import argparse
import json
import os
import re
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import lib  # noqa: E402

STRICT_KINDS = ["minecraft:chest", "minecraft:generic", "minecraft:archaeology", "minecraft:gift"]  # generic: tables without a type
LOOSE_KINDS = ["minecraft:fishing", "minecraft:barter", "minecraft:shearing", "minecraft:equipment", "minecraft:vault"]
WORLD = "world-loot"

# Tables that cannot generate in this pack. (regex, reason, mods that may name it anyway). Each reason is checked where it can be:
# the inventory (jars) must show no structure mod, other than the listed ones, naming the table.
ALLOWED = [
    (r"^minecraft:chests/(bastion_[a-z_]+|nether_bridge)$",
     "Nether bastions and fortresses: the Nether is closed (config/tfc-server.toml enableNetherPortals = false) and no TFC biome is in the vanilla structure tags", []),
    (r"^minecraft:chests/ancient_city(_ice_box)?$", "ancient cities are Deep Dark structures; the Deep Dark does not exist in TFC's biomes", []),
    (r"^minecraft:(chests|dispensers|pots)/trial_chambers/|^minecraft:spawners/(ominous/)?trial_chamber/",
     "trial chambers: not in TFC's biomes, and the pack has no trial keys or vaults", []),
    (r"^minecraft:gameplay/(cat_morning_gift|panda_sneeze|sniffer_digging)$",
     "mob behaviour (cats, pandas, sniffers): feathers, string, rabbit hides, seeds, slime; nothing that skips an era", []),
    (r"^minecraft:gameplay/piglin_bartering$", "Piglins only barter in the Nether, which is closed", []),
    (r"^minecraft:equipment/trial_chamber[a-z_]*$", "gear of trial chamber mobs; trial chambers do not generate", []),
    (r"^(betterfortresses|betterstrongholds|betteroceanmonuments):",
     "tfc_str_compat ships tables for YUNG's Better Nether Fortresses, Strongholds and Ocean Monuments; those mods are not in the pack", []),
    (r"^tfc_str_compat:shared/",
     "building blocks of tfc_str_compat's own tables (wrought iron, steel, GregTech-era metals via item tags); every table that used them is replaced here", []),
    (r"^lootr:chests/elytra$", "Lootr's End-ship elytra chest; there is no End", ["lootr"]),
    (r"^lootr:reward/trophy$", "Lootr's cosmetic trophy block (an advancement reward); not a resource", ["lootr"]),
    (r"^lootr:entity/item_frame_empty$", "an empty table (Lootr item frames)", ["lootr"]),
    (r"^sophisticatedbackpacks:inject/chests/",
     "Sophisticated Backpacks' chest injections (backpacks and upgrades in dungeon, mansion and shipwreck chests): tables its global loot modifiers "
     "add to vanilla chests, and the pack's global_loot_modifiers.json replaces that list and keeps none of them; chestLootEnabled is off as well "
     "(config/sophisticatedbackpacks-common.toml)", ["sophisticatedbackpacks"]),
    (r"^artifacts:inject/",
     "Artifacts' injections into vanilla chests, archaeology and cows (artifacts of every kind, vanilla iron and diamonds): tables its global loot modifiers "
     "add to vanilla tables, and the pack's global_loot_modifiers.json replaces that list and keeps none of them; its artifacts come from the campsite "
     "chest and mimics (loot.json)", ["artifacts"]),
    (r"^artifacts:items/",
     "the per-artifact tables artifacts:artifact is built from in the mod (with config conditions, and six artifacts the pack leaves out); the pack replaces "
     "artifacts:artifact with plain entries for the artifacts it allows (loot.json), so nothing points at these", ["artifacts"]),
]


# ------------------------------------------------------------------------------------------------ eras of tables
def table_eras(spec):
    """{table id: era} for the tables whose era is known: loot.json's, the shared theme tables', the pack's own."""
    eras = {}
    for tid, t in spec["tables"].items():
        if t.get("era"):
            eras[tid] = t["era"]
    for tid, t in spec["tables"].items():
        if "alias" in t and t["alias"] in eras:
            eras[tid] = eras[t["alias"]]
    cat = lib.load_json(lib.CATALOGUE)
    for sid, s in cat["structures"].items():
        if s.get("loot"):
            eras[f"pack:chests/{s.get('loot_table', sid)}"] = s["era"]
    for era in cat.get("site_loot", {}):
        eras[f"pack:chests/site_{era}"] = era
    return eras


def era_for(tid, eras):
    if tid in eras:
        return eras[tid]
    m = re.match(r"^pack_loot:[a-z0-9_/.\-]+/(stone|copper|bronze)$", tid)
    return m.group(1) if m else "bronze"


def allowed_reason(tid):
    for rx, reason, mods in ALLOWED:
        if re.search(rx, tid):
            return reason, set(mods)
    return None, set()


# ------------------------------------------------------------------------------------------------ the server run
def run_server(rolls, sync=True, keep_world=False, timeout=900, log=print):
    from mclib.paths import DATA_DIR
    from mclib.server import DONE_RE, TestServer
    job = {"rolls": rolls, "kinds": STRICT_KINDS + LOOSE_KINDS}
    src = open(os.path.join(HERE, "loot_test.js"), encoding="utf-8").read()
    src = re.sub(r"/\*JOB\*/.*?/\*END\*/", "/*JOB*/ " + json.dumps(job) + " /*END*/", src, flags=re.S)
    out = os.path.join(DATA_DIR, "loot")
    os.makedirs(out, exist_ok=True)
    script = os.path.join(out, "loot_test.js")
    with open(script, "w", encoding="utf-8") as f:
        f.write(src)

    srv = TestServer(log=log)
    srv.ensure_installed()
    if sync:
        srv.sync_pack()
    srv.set_extra_mods([])
    srv.set_dev_scripts({"loot_test.js": script})
    shutil.rmtree(srv.path(WORLD), ignore_errors=True)
    shutil.rmtree(srv.path("local", "loot-test"), ignore_errors=True)
    srv.write_properties(WORLD, "loot")
    log(f"Starting the test server to roll the loot tables ({rolls} rolls each)...")
    srv.start()
    fin = srv.wait_for(r"\[loot-test\] done|" + DONE_RE.pattern, timeout)
    if fin and "loot-test" not in fin.group(0):
        fin = srv.wait_for(r"\[loot-test\] done", timeout)
    if fin:
        srv.wait_for(r"\[loot-test\] lootr done", 180)  # the Lootr probe reads its containers back 300 ticks later
    srv.set_dev_scripts({})
    srv.stop()
    if not keep_world:
        shutil.rmtree(srv.path(WORLD), ignore_errors=True)
    res = srv.path("local", "loot-test", "results.json")
    if not fin or not os.path.exists(res):
        raise SystemExit("the loot test did not run or did not finish; see tools/.server/logs/latest.log")
    results = lib.load_json(res)
    probe = srv.path("local", "loot-test", "lootr.json")
    if os.path.exists(probe):
        results["lootr"] = lib.load_json(probe)
    os.makedirs(os.path.join(DATA_DIR, "reports"), exist_ok=True)
    saved = os.path.join(DATA_DIR, "reports", time.strftime("loot-%Y%m%d-%H%M%S.json"))
    results["_saved"] = saved
    with open(saved, "w", encoding="utf-8") as f:
        json.dump(results, f)
    return results


# ------------------------------------------------------------------------------------------------ analysis
class Report:
    def __init__(self):
        self.problems = []
        self.notes = []
        self.counts = {"tables": 0, "allowed": 0, "loose": 0, "rolled": 0, "denied_rolls": 0, "over_rolls": 0, "empty_tables": 0}
        self.per_table = {}

    def add(self, tid, msg):
        self.problems.append(f"{tid}: {msg}")


def closure(tid, tables, tags, seen=None, path=()):
    """All items a table can name, following loot-table references (value: the table id) and tag entries."""
    items, missing, refs_ = set(), set(), set()
    stack = [tid]
    seen = set()
    while stack:
        t = stack.pop()
        if t in seen:
            continue
        seen.add(t)
        rec = tables.get(t)
        if rec is None or rec.get("json") is None:
            if t != tid:
                missing.add(t)
            continue
        i, tg, tb = lib.refs(rec["json"])
        items |= i
        for name in tg:
            items |= set(tags.get(name, []))
        for r in tb:
            refs_.add(r)
            stack.append(r)
    return items, missing, refs_


def analyze(results, rules, spec, inv=None, keep_glm=()):
    dropped_glm = spec.get("dropped_global_loot_modifiers", {})  # prefix -> reason: modifiers the override drops on purpose
    rep = Report()
    eras = table_eras(spec)
    tables = results["tables"]
    tags = results.get("tags", {})
    known = set(tables) | set(results.get("skipped", {}))
    allowed = {}
    for tid in sorted(known):
        reason, mods = allowed_reason(tid)
        if reason:
            allowed[tid] = (reason, mods)
    rep.counts["allowed"] = len(allowed)

    for tid, rec in sorted(tables.items()):
        if tid in allowed:
            continue
        strict = rec.get("kind") in STRICT_KINDS
        era = era_for(tid, eras)
        rep.counts["tables" if strict else "loose"] += 1
        if rec.get("error") and strict:
            rep.add(tid, f"does not roll: {rec['error']}")
            continue
        if rec.get("json") is None:
            rep.add(tid, "could not be read back from the server")
            continue
        items, missing, refs_ = closure(tid, tables, tags)
        for r in sorted(missing):
            rep.add(tid, f"points at the loot table {r}, which does not exist")
        for r in sorted(refs_):
            if r in allowed:
                rep.add(tid, f"points at {r}, which the lint skips as impossible ({allowed[r][0]})")
            elif strict and lib.ERAS.index(era_for(r, eras)) > lib.ERAS.index(era) and r.startswith("pack_loot:"):
                rep.add(tid, f"points at {r}, above its own {era} era")
        bad = {}
        for item in sorted(items):
            probs = rules.problems(item, era) if strict else ([f"{item} is on the deny-list (skips an era)"] if rules.denied(item) else [])
            if probs:
                bad[item] = probs[0]
        for item, why in bad.items():
            rep.add(tid, f"{why} (named in the table)")
        # what really comes out
        rolled_bad = {}
        for item, n in rec["seen"].items():
            probs = rules.problems(item, era) if strict else ([f"{item} is on the deny-list (skips an era)"] if rules.denied(item) else [])
            if probs:
                rolled_bad[item] = (n, probs[0])
                if rules.denied(item):
                    rep.counts["denied_rolls"] += n
                else:
                    rep.counts["over_rolls"] += n
        for item, (n, why) in rolled_bad.items():
            if item not in bad:  # a function made it (not named in the JSON)
                rep.add(tid, f"{why} (rolled {n}x, made by a function)")
        if strict and rec["rolls"]:
            rep.counts["rolled"] += rec["rolls"]
            if not rec["seen"] and tid.startswith(("pack_loot:",)):
                rep.add(tid, "a shared theme table rolled nothing in all its rolls")
            if rec["empty"] == rec["rolls"]:
                if spec["tables"].get(tid, {}).get("empty"):
                    rep.counts["emptied"] = rep.counts.get("emptied", 0) + 1  # on purpose (GregTech's tables)
                else:
                    rep.counts["empty_tables"] += 1
                    rep.notes.append(f"{tid} is empty (all {rec['rolls']} rolls gave nothing)")
        rep.per_table[tid] = {"era": era, "listed_bad": sorted(bad), "rolled_bad": sorted(rolled_bad)}

    # global loot modifiers: the lists of every data pack in load order, folded the way NeoForge's LootModifierManager does it
    # ("replace" drops what came before), and the modifiers the manager actually holds when the script could read them
    effective = None
    if results.get("modifier_lists") is not None:
        effective = []
        for doc in results["modifier_lists"]:
            if doc["json"].get("replace"):
                effective.clear()
            for entry in doc["json"].get("entries", []):
                if entry in effective:
                    effective.remove(entry)
                effective.append(entry)
    held = results.get("modifiers")
    if effective is None and held is None:
        rep.add("global loot modifiers", "could not read the active global loot modifiers: " + "; ".join(results.get("errors", [])))
    if effective is not None and effective != list(keep_glm):
        rep.add("global loot modifiers", f"{len(effective)} listed after all data packs, loot.json keeps {len(keep_glm)}: " + ", ".join(effective[:12]))
    if held is not None and len(held) != len(keep_glm):
        rep.add("global loot modifiers", f"the manager holds {len(held)} active, loot.json keeps {len(keep_glm)}: " + "; ".join(held[:12]))
    rep.glm_active = len(held) if held is not None else (len(effective) if effective is not None else None)

    # allow-listed tables: the jars must agree that nothing uses them
    if inv is not None:
        for tid, (reason, ok_mods) in allowed.items():
            e = inv["tables"].get(tid)
            if not e:
                continue
            users = set(e["templates"]) | set(e["json"]) | set(e["classes"])
            users -= {"minecraft"} | ok_mods
            if users:
                rep.add(tid, f"is skipped as impossible ({reason}) but {', '.join(sorted(users))} name it")
        # every table a structure mod names exists
        for tid, e in inv["tables"].items():
            users = (set(e["templates"]) | set(e["json"]) | set(e["classes"])) - {"minecraft"}
            if users and tid not in known and not tid.startswith(("gtceu:",)):
                rep.add(tid, f"is named by {', '.join(sorted(users))} but no such table exists (those chests stay empty)")
        # global loot modifier lists in the jars: the override must not drop another mod's
        for label, doc in inv.get("global_loot_modifiers", {}).items():
            keep = [x for x in doc["entries"] if not x.startswith("gtceu:chests/extra/")]
            for x in keep:
                if x not in keep_glm and not any(x.startswith(pre) for pre in dropped_glm):
                    rep.add("global loot modifiers", f"{label} lists {x}, which loot.json's override would drop (add it to keep_global_loot_modifiers)")
    return rep


def static_checks(spec, rules):
    """The generated files match loot.json."""
    import gen
    problems = []
    g = gen.Generator(spec, rules)
    files, tables = g.run()
    problems += [f"loot.json: {p}" for p in g.problems]
    for rel, content in files.items():
        path = os.path.join(lib.REPO, rel)
        if not os.path.exists(path):
            problems.append(f"{rel} is missing (run tools/loot/gen.py)")
        elif open(path, "rb").read().replace(b"\r\n", b"\n") != content:
            problems.append(f"{rel} differs from what loot.json generates (run tools/loot/gen.py)")
    manifest = lib.load_json(gen.MANIFEST) if os.path.exists(gen.MANIFEST) else []
    for rel in manifest:
        if rel not in files and os.path.exists(os.path.join(lib.REPO, rel)):
            problems.append(f"{rel} is stale (run tools/loot/gen.py)")
    if sorted(files) != manifest:
        problems.append("tools/loot/generated.json is out of date (run tools/loot/gen.py)")
    return problems


def run(rolls=300, sync=True, keep_world=False, results=None, static_only=False, verbose=False, log=print):
    """Returns (ok, one-line summary, problems)."""
    spec = lib.load_json(lib.SPEC)
    rules = lib.Rules()
    problems = static_checks(spec, rules)
    inv = None
    try:
        import inventory
        inv = inventory.cached()
    except Exception as e:  # jars missing
        log(f"(no jar inventory: {e})")
    if static_only:
        ok = not problems
        return ok, f"loot lint (static only): {'PASS' if ok else 'FAIL'} - {len(problems)} problem(s) in the generated files", problems
    if results is None:
        results = run_server(rolls, sync=sync, keep_world=keep_world, log=log)
    elif isinstance(results, str):
        results = lib.load_json(results)
    rep = analyze(results, rules, spec, inv, spec.get("keep_global_loot_modifiers", []))
    problems += rep.problems
    c = rep.counts
    ok = not problems
    for n in rep.notes:
        log("note: " + n)
    lootr = results.get("lootr")
    if lootr and lootr.get("blocks"):
        conv = sorted(b for b, v in lootr["blocks"].items() if (v.get("after") or "").startswith("lootr:"))
        kept = sorted(b for b, v in lootr["blocks"].items() if v.get("after") == b and v.get("after"))
        log("note: Lootr turns these into its own containers once they hold a loot table: " + ", ".join(conv) + "; left alone: " + ", ".join(kept))
    glm = "?" if rep.glm_active is None else str(rep.glm_active)
    summary = (f"loot lint: {'PASS' if ok else 'FAIL'} - {c['tables']} chest/archaeology/gift tables checked (+{c['loose']} other kinds by deny-list, "
               f"{c['allowed']} impossible ones skipped), {results.get('rolls', 0)} rolls each ({c['rolled']} total): "
               f"{c['denied_rolls']} deny-listed and {c['over_rolls']} over-cap items rolled, {c['empty_tables']} empty tables ({c.get('emptied', 0)} emptied on purpose), "
               f"{glm} global loot modifiers active, {len(problems)} problem(s); dump {rules.dump}")
    return ok, summary, problems


def main():
    lib.utf8()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rolls", type=int, default=300, help="rolls per table on the server (default 300)")
    ap.add_argument("--no-sync", action="store_true", help="skip packwiz-installer (test what is already installed on the server)")
    ap.add_argument("--keep-world", action="store_true")
    ap.add_argument("--results", help="analyze a saved results.json (tools/.data/reports/loot-*.json) instead of starting the server")
    ap.add_argument("--static", action="store_true", help="only check that the generated files match loot.json (no server)")
    ap.add_argument("--verbose", action="store_true", help="list all problems (default: the first 60)")
    args = ap.parse_args()
    ok, summary, problems = run(args.rolls, not args.no_sync, args.keep_world, args.results, args.static, args.verbose)
    for p in problems[: (None if args.verbose else 60)]:
        print("PROBLEM", p)
    if len(problems) > 60 and not args.verbose:
        print(f"... {len(problems) - 60} more (--verbose)")
    print(summary)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
