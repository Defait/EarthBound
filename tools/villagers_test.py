"""Check villager and wandering-trader trades (docs/design.md, "Villagers").

Usage (from the repo root):
    tools/.venv/Scripts/python tools/villagers_test.py [--static] [--no-sync] [--keep-world] [--timeout SECONDS]

Two parts, both exit code 1 on any failure:
  1. The trade file (kubejs/config/villager_trades.json), without a server (--static stops here): the structure; every item
     exists in the newest recipe dump; no result on the deny-list (tools/structures/catalogue.json, loot_caps) or above the
     era cap of its level (levels 1-2 stone, 3 copper, 4-5 bronze; the wandering trader's generic list copper, rare bronze) by
     the progression checker's step (tools/quests/pack_query.py); no emerald, no bronze-family metal before level 4; inputs on
     the same terms (reachable by that level); no item both bought and sold in a cycle (no way to trade in a loop for profit).
  2. The test server on a fresh world with a dev-only KubeJS script (villagers_test.js) that
       - records the trade lists NeoForge hands the event before the pack's startup script replaces them (vanilla's, plus any mod's) and
         asks them what they would have sold: shares on the deny-list, above the cap or unreachable, enchanted, maps, emeralds (reported);
       - checks that every price and result of the file fits its item's stack;
       - spawns villagers of every profession at every level (30 of each) and checks what they offer: two per level, only the file's
         trades, all of them come up, each within the rules again by the real item (deny-list, era cap by level, no enchantments, no
         emeralds); and wandering traders: five generic and one rare of the file's;
       - makes a villager and a wandering trader that hold emerald-for-iron offers join the world (they must get the pack's), and checks a
         villager with its own offers keeps them;
       - places every structure template of the pack's jars that holds a villager, wandering trader or zombie villager the way a jigsaw
         piece does, reads whether the baked offers load at all, and checks what the entities offer afterwards;
       - rolls the loot of the iron golem, the illagers, a witch, a zombie villager and every Hero of the Village gift 300 times; the
         golem and the gifts (overridden by the pack) are then judged here against the deny-list and the bronze cap, the rest reported.
Results: tools/.data/reports/villagers-<timestamp>.json. Uses the test server: not while another tool does.
"""
import argparse
import glob
import json
import os
import re
import shutil
import sys
import time
import zipfile

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(TOOLS, "structures"))
sys.path.insert(0, os.path.join(TOOLS, "recipes"))
sys.path.insert(0, os.path.join(TOOLS, "quests"))
from mclib.paths import DATA_DIR, REPO, utf8_console  # noqa: E402
from mclib.server import DONE_RE, TestServer  # noqa: E402

TABLE = os.path.join(REPO, "kubejs", "config", "villager_trades.json")
CATALOGUE = os.path.join(TOOLS, "structures", "catalogue.json")
WORLD = "world-villagers"
RESULT_RE = re.compile(r"\[villagers-test\] (PASS|FAIL|NOTE|STAT|done)(.*)")
LEVEL_ERA = {"1": "stone", "2": "stone", "3": "copper", "4": "bronze", "5": "bronze"}
EARLY_METAL = re.compile(r"^tfc:metal/.*(bronze|brass|steel|iron)|^tfc:metal/ingot/(bronze|brass|bismuth_bronze|black_bronze)$|bronze_bell|brass_bell")
ENTITY_KINDS = ("villager", "wandering_trader", "zombie_villager")


# --------------------------------------------------------------------------------------------- the file
def pack_facts():
    """Item ids of the newest recipe dump, and the progression checker's step per item (pack_query's cache)."""
    from model import latest_dump
    dump = latest_dump()
    items = set(json.load(open(os.path.join(dump, "items.json"), encoding="utf-8"))["ids"])
    import pack_query
    steps = {k: v["step"] for k, v in pack_query.load()["items"].items()}
    return os.path.basename(dump), items, steps


def all_trades(table):
    """(where, era, trade) for every trade of the file."""
    for prof, spec in table["professions"].items():
        for lvl in "12345":
            for i, tr in enumerate(spec.get(lvl, [])):
                yield f"{prof} level {lvl} #{i + 1}", LEVEL_ERA[lvl], tr
    for kind, era in table["wanderer_eras"].items():
        for i, tr in enumerate(table["wandering_trader"][kind]):
            yield f"wandering trader {kind} #{i + 1}", era, tr


def lint_table(table, caps, items_known, steps):
    """Problems (exit 1) and notes for the trade file."""
    problems, notes = [], []
    deny = [re.compile(p) for p in caps["deny"]]
    allow = [re.compile(p) for p in caps["allow_unreachable"]]

    def check_item(where, role, item_id, era):
        if not re.match(r"^[a-z0-9_.-]+:[a-z0-9_./-]+$", item_id):
            problems.append(f"{where}: {role} {item_id!r} isn't an item id")
            return
        if items_known is not None and item_id not in items_known:
            problems.append(f"{where}: {role} {item_id} doesn't exist")
            return
        if item_id == "minecraft:emerald" or item_id.endswith(":emerald"):
            problems.append(f"{where}: {role} {item_id}: no emeralds")
        if any(d.search(item_id) for d in deny):
            problems.append(f"{where}: {role} {item_id} is on the deny-list (skips an era)")
        if era != "bronze" and EARLY_METAL.search(item_id):
            problems.append(f"{where}: {role} {item_id} is bronze-age or later, but the trade is {era} age")
        if steps is None:
            return
        step = steps.get(item_id)
        cap = caps[era]
        if step is None:
            if not any(a.search(item_id) for a in allow):
                (problems if role == "sells" else notes).append(
                    f"{where}: {role} {item_id} is unreachable for the progression checker and not in allow_unreachable")
        elif step > cap:
            (problems if role == "sells" else notes).append(f"{where}: {role} {item_id} is step {step}, above the {era} cap {cap}")

    sells, edges = set(), {}
    seen = {}
    for where, era, tr in all_trades(table):
        keys = set(tr) - {"buy", "buy_b", "sell", "max_uses", "xp"}
        if keys:
            problems.append(f"{where}: unknown keys {sorted(keys)}")
        for k in ("buy", "sell"):
            if k not in tr:
                problems.append(f"{where}: no {k}")
        for k in ("buy", "buy_b", "sell"):
            if k in tr:
                v = tr[k]
                if not (isinstance(v, list) and len(v) == 2 and isinstance(v[0], str) and isinstance(v[1], int) and 1 <= v[1] <= 64):
                    problems.append(f"{where}: {k} should be [id, count 1-64], is {v}")
        if not (isinstance(tr.get("max_uses"), int) and 1 <= tr["max_uses"] <= 64):
            problems.append(f"{where}: max_uses {tr.get('max_uses')}")
        if "buy" not in tr or "sell" not in tr:
            continue
        for role, k in (("buys", "buy"), ("buys", "buy_b"), ("sells", "sell")):
            if k in tr and isinstance(tr[k], list) and tr[k]:
                check_item(where, role, tr[k][0], era)
        sells.add(tr["sell"][0])
        for k in ("buy", "buy_b"):
            if k in tr:
                edges.setdefault(tr[k][0], set()).add(tr["sell"][0])
        sig = (where.rsplit(" level ", 1)[0] if " level " in where else where.rsplit(" #", 1)[0], json.dumps(tr, sort_keys=True))
        if sig in seen:
            problems.append(f"{where}: the same trade as {seen[sig]}")
        seen[sig] = where
    # a loop of trades (A for B somewhere, B for A somewhere else) is a money machine
    state = {}
    path = []

    def visit(node):
        state[node] = 1
        path.append(node)
        for nxt in sorted(edges.get(node, ())):
            if state.get(nxt) == 1:
                problems.append("trades form a loop: " + " -> ".join(path[path.index(nxt):] + [nxt]))
            elif nxt not in state:
                visit(nxt)
        path.pop()
        state[node] = 2
    for n in sorted(edges):
        if n not in state:
            visit(n)
    return problems, notes, sorted(sells)


def find_templates():
    """Every structure template in the pack's jars that holds a villager, wandering trader or zombie villager:
    [{template, entities: [kind, ...]}]. A quick byte filter first, then the real parse."""
    import nbt as N
    out = []
    for jar in sorted(glob.glob(os.path.join(TOOLS, ".server", "mods", "*.jar"))):
        try:
            z = zipfile.ZipFile(jar)
        except zipfile.BadZipFile:
            continue
        for n in z.namelist():
            m = re.match(r"^data/([^/]+)/structure/(.+)\.nbt$", n)
            if not m:
                continue
            raw = z.read(n)
            try:
                import gzip
                body = gzip.decompress(raw)
            except OSError:
                body = raw
            if b"villager" not in body and b"wandering_trader" not in body:
                continue
            try:
                root = N.loads(raw)
            except Exception:  # noqa: BLE001 - an unreadable template is somebody else's problem
                continue
            kinds = []
            for e in root.get("entities") or []:
                eid = str(e.get("nbt", {}).get("id", ""))
                if eid.split(":")[-1] in ENTITY_KINDS:
                    kinds.append(eid.split(":")[-1])
            if kinds:
                out.append({"template": f"{m.group(1)}:{m.group(2)}", "entities": kinds, "jar": os.path.basename(jar)})
    return out


# --------------------------------------------------------------------------------------------- the server
def report_vanilla(results, caps, steps):
    """What vanilla (and any mod) offered before the file replaced it, judged by the pack's rules."""
    deny = [re.compile(p) for p in caps["deny"]]
    allow = [re.compile(p) for p in caps["allow_unreachable"]]
    total = bad_deny = bad_cap = emerald = enchanted = maps = 0
    worst = {}
    for key, recs in results.get("vanilla", {}).items():
        prof = key.split("|")[0]
        for rec in recs:
            total += 1
            over = [i for i in rec["sells"] if any(d.search(i) for d in deny)]
            if steps:
                for i in rec["sells"]:
                    st = steps.get(i)
                    if i in over:
                        continue
                    if (st is None and not any(a.search(i) for a in allow)) or (st is not None and st > caps["bronze"]):
                        over.append(i)
            bad_deny += 1 if rec["denied"] else 0
            bad_cap += 1 if over else 0
            emerald += 1 if rec["emerald"] else 0
            enchanted += 1 if rec["enchanted"] else 0
            maps += 1 if rec["map"] else 0
            if over or rec["enchanted"] or rec["map"]:
                worst[prof] = worst.get(prof, 0) + 1
    if total:
        pct = lambda n: f"{n} ({100 * n / total:.0f}%)"
        print(f"  STAT vanilla before: {total} listings; deny-listed result {pct(bad_deny)}; result on the deny-list, above the bronze cap or "
              f"unreachable {pct(bad_cap)}; enchanted {pct(enchanted)}; maps {maps}; paid or paying in emeralds {pct(emerald)}")


def report_loot(results, caps, steps):
    """The loot of the iron golem and the Hero of the Village gifts (overridden by the pack) must stay in era; the rest is reported.
    Returns the number of failures."""
    deny = [re.compile(p) for p in caps["deny"]]
    allow = [re.compile(p) for p in caps["allow_unreachable"]]
    failed = 0
    for table, seen in sorted(results.get("loot", {}).items()):
        own = table == "minecraft:entities/iron_golem" or "/hero_of_the_village/" in table
        problems = []
        for i in sorted(seen):
            if i == "minecraft:air":
                continue
            if any(d.search(i) for d in deny):
                problems.append(f"{i} is on the deny-list")
            elif steps is not None:
                st = steps.get(i)
                if st is None and not any(a.search(i) for a in allow):
                    problems.append(f"{i} is unreachable for the progression checker")
                elif st is not None and st > caps["bronze"]:
                    problems.append(f"{i} is step {st}, above the bronze cap {caps['bronze']}")
        items = ", ".join(i for i in sorted(seen) if i != "minecraft:air")
        short = table.replace("minecraft:", "")
        if own:
            ok = not problems and bool(items)
            failed += 0 if ok else 1
            print(f"  {'PASS' if ok else 'FAIL'} loot {short} stays in era: {len(items.split(', ')) if items else 0} items" + ("; " + "; ".join(problems[:6]) if problems else ""))
        else:
            print(f"  NOTE loot {short}: {items or 'nothing'}" + (f" (PROBLEM: {'; '.join(problems[:4])})" if problems else ""))
    return failed


def main():
    utf8_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--static", action="store_true", help="only check the trade file, without the server")
    ap.add_argument("--no-sync", action="store_true", help="skip packwiz-installer")
    ap.add_argument("--keep-world", action="store_true", help="keep the test world afterwards")
    ap.add_argument("--timeout", type=int, default=900, help="seconds to wait for the server checks")
    args = ap.parse_args()

    table = json.load(open(TABLE, encoding="utf-8"))
    cat = json.load(open(CATALOGUE, encoding="utf-8"))
    caps = cat["loot_caps"]
    failed = 0
    try:
        dump, items_known, steps = pack_facts()
        print(f"Checking {os.path.relpath(TABLE, REPO)} against recipe dump {dump}")
    except (SystemExit, ImportError, OSError) as e:
        print(f"(no recipe dump or progression steps: {e}) item existence and caps are only checked in game")
        items_known, steps = None, None
    problems, notes, sells = lint_table(table, caps, items_known, steps)
    n = sum(1 for _ in all_trades(table))
    for p in problems:
        print(f"  FAIL {p}")
    for p in notes:
        print(f"  NOTE {p}")
    print(f"{n} trades, {len(sells)} items sold, {len(problems)} problems, {len(notes)} notes")
    failed += len(problems)
    if args.static:
        return 1 if failed else 0

    templates = find_templates()
    all_ids = set()
    for _, _, tr in all_trades(table):
        for k in ("buy", "buy_b", "sell"):
            if k in tr:
                all_ids.add(tr[k][0])
    job = {"table": table, "deny": caps["deny"], "caps": {k: caps[k] for k in ("stone", "copper", "bronze")}, "allow": caps["allow_unreachable"],
           "steps": {i: (steps or {}).get(i) for i in sorted(all_ids)} if steps else None, "levelEra": LEVEL_ERA, "templates": templates,
           "earlyMetal": EARLY_METAL.pattern}
    src = open(os.path.join(TOOLS, "villagers_test.js"), encoding="utf-8").read()
    src = re.sub(r"/\*JOB\*/.*?/\*END\*/", lambda m: "/*JOB*/ " + json.dumps(job) + " /*END*/", src, flags=re.S)
    os.makedirs(os.path.join(DATA_DIR, "villagers"), exist_ok=True)
    script = os.path.join(DATA_DIR, "villagers", "villagers_test.js")
    with open(script, "w", encoding="utf-8") as f:
        f.write(src)

    srv = TestServer()
    srv.ensure_installed()
    if not args.no_sync:
        srv.sync_pack()
    srv.set_dev_scripts({"villagers_test.js": script})
    shutil.rmtree(srv.path(WORLD), ignore_errors=True)
    shutil.rmtree(srv.path("local", "villagers-test"), ignore_errors=True)
    srv.write_properties(WORLD, "villagers")
    print(f"Starting server ({len(templates)} templates with villagers, wandering traders or zombie villagers)...")
    srv.start()
    finished = srv.wait_for(r"\[villagers-test\] done|" + DONE_RE.pattern, args.timeout)
    if finished and "villagers-test" not in finished.group(0):
        finished = srv.wait_for(r"\[villagers-test\] done", args.timeout)
    srv.set_dev_scripts({})
    srv.stop()
    if not args.keep_world:
        shutil.rmtree(srv.path(WORLD), ignore_errors=True)

    ran = False
    for line in srv.lines:
        m = RESULT_RE.search(line)
        if not m:
            continue
        ran = True
        if m.group(1) == "FAIL":
            failed += 1
        print(f"  {m.group(1)}{m.group(2)}")
    for line in srv.lines:
        if "[villager-trades]" in line and ("ERROR" in line or "WARN" in line):
            print("  LOG " + line.split("] ", 1)[-1][:300])
    res = srv.path("local", "villagers-test", "results.json")
    if os.path.exists(res):
        loaded = json.load(open(res, encoding="utf-8"))
        report_vanilla(loaded, caps, steps)
        failed += report_loot(loaded, caps, steps)
        os.makedirs(os.path.join(DATA_DIR, "reports"), exist_ok=True)
        out = os.path.join(DATA_DIR, "reports", time.strftime("villagers-%Y%m%d-%H%M%S.json"))
        shutil.copy(res, out)
        print(f"Results: {out}")
    if not ran or not finished:
        print("The checks didn't run or didn't finish; see tools/.server/logs/latest.log")
        return 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
