"""Build the FTB Quests book from tools/quests/route.json, and check it against the progression checker.

Usage (from the repo root):
    tools/.venv/Scripts/python tools/quests/build.py [--no-check] [--dump NAME] [--world PATH]

Writes config/ftbquests/quests/ (data.snbt, chapters/*.snbt, lang/en_us.snbt); that folder is
generated, so edit route.json and rebuild instead of editing it (or the in-game editor's changes
are lost on the next build). Quest and chapter ids are hashes of their keys, so they stay stable
and players keep their progress across rebuilds.

The check loads the newest recipe dump and the pre-generated test world (as the explorer does)
and reports, per quest, the checker's step for its item. It warns when an item doesn't exist or
can't be reached, and when a quest comes earlier on the route than one of its prerequisites.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
REPO = os.path.dirname(TOOLS)
OUT = os.path.join(REPO, "config", "ftbquests", "quests")
FILE_ID = "0000000000000001"
QUEST_FILE_VERSION = 13  # FTB Quests 2101's BaseQuestFile.VERSION


def code(kind, key):
    """A stable 16-hex-digit FTB Quests id."""
    h = int(hashlib.sha1(f"{kind}:{key}".encode()).hexdigest()[:16], 16) & 0x7FFFFFFFFFFFFFFF
    return f"{max(h, 2):016X}"


# ------------------------------------------------------------------ SNBT
BARE_KEY = re.compile(r"[A-Za-z0-9_\-.+]+")


def snbt_key(key):
    """FTB's SNBT allows bare keys of letters, digits and _-.+ only; others (e.g. with ':') are quoted."""
    return key if BARE_KEY.fullmatch(key) else snbt(key)


def snbt(value, indent=0):
    pad = "\t" * indent
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value}d"
    if isinstance(value, str):
        if "\n" in value:
            raise ValueError(f"SNBT strings can't hold line breaks: {value[:60]!r}")
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(value, list):
        if not value:
            return "[ ]"
        if all(not isinstance(v, (dict, list)) for v in value) and not any(isinstance(v, str) for v in value):
            return "[" + ", ".join(snbt(v) for v in value) + "]"
        inner = "\n".join(pad + "\t" + snbt(v, indent + 1) for v in value)
        return "[\n" + inner + "\n" + pad + "]"
    if isinstance(value, dict):
        if not value:
            return "{ }"
        inner = "\n".join(f"{pad}\t{snbt_key(k)}: {snbt(v, indent + 1)}" for k, v in sorted(value.items()))
        return "{\n" + inner + "\n" + pad + "}"
    raise TypeError(type(value))


def stack(item):
    return {"count": 1, "id": item}


def filter_stack(expr):
    """An FTB Filter System smart filter: the item task matches whatever the expression matches."""
    return {"count": 1, "id": "ftbfiltersystem:smart_filter", "components": {"ftbfiltersystem:filter": expr}}


def quest_tasks(q):
    """(id suffix, task) pairs from route.json's forms: the item/extra_items/checkmark shorthands and a
    full 'tasks' list. The suffixes keep task ids, and so players' progress, stable across rebuilds."""
    tasks = [("check", {"checkmark": True})] if q.get("checkmark") else []
    tasks += [(str(i), {"item": it}) for i, it in enumerate(([q["item"]] if q.get("item") else []) + q.get("extra_items", []))]
    return tasks + [(f"t{i}", t) for i, t in enumerate(q.get("tasks", []))]


def task_items(t):
    """Item/tag patterns a task accepts (for the checker), or [] for tasks that aren't about items."""
    if t.get("item"):
        return [t["item"]]
    return list(t.get("any", []))


def emit_task(q, suffix, t):
    entry = {"id": code("task", f"{q['key']}:{suffix}")}
    kind = t.get("type") or ("checkmark" if t.get("checkmark") else "item")
    entry["type"] = kind
    if kind == "item":
        entry["item"] = filter_stack(t["filter"]) if t.get("filter") else stack(t["item"])
        entry["count"] = t.get("count", 1)
    elif kind == "observation":
        entry.update({"observe_type": t.get("observe_type", 0), "to_observe": t["to_observe"], "timer": t.get("timer", 0)})
    elif kind == "kill":
        entry.update({"entity": t["entity"], "value": t.get("value", 1)})
    elif kind == "dimension":
        entry["dimension"] = t["dimension"]
    elif kind == "biome":
        entry["biome"] = t["biome"]
    elif kind != "checkmark":
        raise SystemExit(f"quest {q['key']}: unknown task type {kind}")
    if t.get("optional"):
        entry["optional_task"] = True
    return entry


# ------------------------------------------------------------------ layout
def layout(quests):
    """Columns by longest chain of same-chapter prerequisites; within a column, quests sit near the
    average row of their prerequisites (then route order), so dependency lines stay short."""
    keys = {q["key"] for q in quests}
    by_key = {x["key"]: x for x in quests}
    col = {}

    def depth(q, seen=()):
        if q["key"] in col:
            return col[q["key"]]
        local = [d for d in q.get("deps", []) if d in keys and d not in seen]
        col[q["key"]] = 0 if not local else 1 + max(depth(by_key[d], seen + (q["key"],)) for d in local)
        return col[q["key"]]

    for q in quests:
        depth(q)
    order = {q["key"]: i for i, q in enumerate(quests)}
    columns = {}
    for q in quests:
        columns.setdefault(col[q["key"]], []).append(q["key"])
    y = {}
    for c in sorted(columns):
        members = columns[c]

        def want(k):
            parents = [y[d] for d in by_key[k].get("deps", []) if d in y]
            return (sum(parents) / len(parents) if parents else order[k], order[k])

        members.sort(key=want)
        n = len(members)
        for r, k in enumerate(members):
            y[k] = (r - (n - 1) / 2.0) * 1.75
    return {k: (col[k] * 2.0, y[k]) for k in keys}


# ------------------------------------------------------------------ build
def build(route):
    lang = {f"file.{FILE_ID}.title": route.get("title", "Quests")}
    files = {}
    all_keys = {q["key"]: ch["key"] for ch in route["chapters"] for q in ch["quests"]}
    groups = route.get("groups", [])
    for g in groups:
        lang[f"chapter_group.{code('group', g['key'])}.title"] = g["title"]
    if groups:
        files["chapter_groups.snbt"] = {"chapter_groups": [{"id": code("group", g["key"])} for g in groups]}
    for order, ch in enumerate(route["chapters"]):
        cid = code("chapter", ch["key"])
        lang[f"chapter.{cid}.title"] = ch["title"]
        if ch.get("subtitle"):
            lang[f"chapter.{cid}.chapter_subtitle"] = [ch["subtitle"]]
        # Chapters ported with their source's hand-made layout keep it; the others are laid out from
        # their dependencies.
        manual = ch.get("layout") == "manual"
        pos = {q["key"]: tuple(q["pos"]) for q in ch["quests"]} if manual else layout(ch["quests"])
        quests = []
        for q in ch["quests"]:
            qid = code("quest", q["key"])
            missing = [d for d in q.get("deps", []) if d not in all_keys]
            if missing:
                raise SystemExit(f"quest {q['key']}: unknown dependencies {missing}")
            tasks = [emit_task(q, suffix, t) for suffix, t in quest_tasks(q)]
            if not tasks:
                raise SystemExit(f"quest {q['key']}: no tasks")
            x, y = pos[q["key"]]
            entry = {"id": qid, "x": x, "y": y, "tasks": tasks,
                     "dependencies": [code("quest", d) for d in q.get("deps", [])]}
            first_item = next((i for _, t in quest_tasks(q) for i in task_items(t) if not i.startswith(("#", "@"))), None)
            icon = q.get("icon") or first_item
            if icon:
                entry["icon"] = stack(icon)
            if q.get("big"):
                entry["size"] = 1.5
            elif q.get("size"):
                entry["size"] = float(q["size"])
            for k in ("optional", "shape", "dependency_requirement", "hide_dependency_lines", "min_required_dependencies"):
                if q.get(k) not in (None, "", False):
                    entry[k] = q[k]
            quests.append(entry)
            lang[f"quest.{qid}.title"] = " ".join(q["title"].split("\n"))
            if q.get("subtitle"):
                lang[f"quest.{qid}.quest_subtitle"] = " ".join(q["subtitle"].split("\n"))
            if q.get("desc"):
                # One list entry per line: FTB's SNBT strings can't hold line breaks.
                lang[f"quest.{qid}.quest_desc"] = [line for entry in q["desc"] for line in entry.split("\n")]
        files[os.path.join("chapters", ch["key"] + ".snbt")] = {
            "id": cid, "filename": ch["key"], "group": code("group", ch["group"]) if ch.get("group") else "",
            "order_index": order, "icon": stack(ch["icon"]), "default_quest_shape": "",
            "default_hide_dependency_lines": False, "quest_links": [], "quests": quests,
        }
    files["data.snbt"] = {
        "id": FILE_ID, "version": QUEST_FILE_VERSION, "default_quest_shape": "circle", "default_reward_team": False,
        "default_consume_items": False, "default_autoclaim_rewards": "disabled", "default_quest_disable_jei": False,
        "disable_gui": False, "grid_scale": 0.5, "pause_game": False, "lock_message": "",
        "detection_delay": 20, "drop_book_on_death": False,
    }
    files[os.path.join("lang", "en_us.snbt")] = lang
    return files


def write(files):
    shutil.rmtree(OUT, ignore_errors=True)
    for rel, data in files.items():
        path = os.path.join(OUT, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(snbt(data) + "\n")


# ------------------------------------------------------------------ check
def check(route, dump_name, world):
    sys.path.insert(0, TOOLS)
    sys.path.insert(0, os.path.join(TOOLS, "recipes"))
    from model import DUMPS, Dump, latest_dump  # noqa: E402
    from progression import Progression, world_seeds  # noqa: E402

    d = Dump(os.path.join(DUMPS, dump_name) if dump_name else latest_dump())
    cfg = json.load(open(os.path.join(TOOLS, "recipes", "progression.json"), encoding="utf-8"))
    seeds, info = set(), {}
    if world and os.path.isdir(world):
        seeds, info, _ = world_seeds(d, world, cfg)
    for p in cfg.get("seeds", {}).get("extra", []):
        seeds.add(p if p.startswith(("i:", "f:")) else "i:" + p)
    p = Progression(d, seeds=seeds, seed_info=info)

    quests = {q["key"]: q for ch in route["chapters"] for q in ch["quests"]}
    step = {}
    problems = 0
    unchecked = 0
    pacing = 0
    for key, q in quests.items():
        depths = []
        for _, t in quest_tasks(q):
            pats = task_items(t)
            if not pats:
                continue
            nodes = set()
            for pat in pats:
                if pat.startswith("@"):
                    continue
                found = d.resolve("#i:" + pat[1:]) if pat.startswith("#") else ({"i:" + pat} if pat in d.items else set())
                if not found:
                    print(f"  ! {key}: {pat} doesn't exist")
                    problems += 1
                nodes |= found
            reach = [p.base.dist[n] for n in nodes if n in p.base.dist]
            if t.get("optional"):
                continue
            if reach:
                depths.append(min(reach))
            elif nodes and not q.get("unchecked"):
                print(f"  ! {key}: {' / '.join(pats[:3])} is unreachable")
                problems += 1
            elif nodes:
                unchecked += 1
        step[key] = max(depths) if depths else None

    def effective(key, seen=()):
        """Checkmark quests take the latest step among their prerequisites."""
        if step.get(key) is not None or key in seen:
            return step.get(key)
        deps = [effective(x, seen + (key,)) for x in quests[key].get("deps", [])]
        deps = [x for x in deps if x is not None]
        return max(deps) if deps else 0

    for ch in route["chapters"]:
        print(f"{ch['title']}")
        for q in ch["quests"]:
            s = effective(q["key"])
            late = [x for x in q.get("deps", []) if (effective(x) or 0) > (s or 0)]
            mark = "" if step.get(q["key"]) is not None else " (checkmark)"
            print(f"  {str(s):>4}  {q['title']}{mark}")
            for x in late:
                # Ported quests keep their source's tutorial order (a hub quest before the machines
                # it introduces), which may ask for something before it's strictly needed: a pacing
                # note, not a problem. The pack's own quests must follow the checker's order.
                if q.get("source"):
                    print(f"        ~ pacing: prerequisite '{quests[x]['title']}' is reachable later (step {effective(x)})")
                    pacing += 1
                else:
                    print(f"        ! prerequisite '{quests[x]['title']}' comes later (step {effective(x)})")
                    problems += 1
    if unchecked:
        print(f"({unchecked} task(s) on quests marked 'unchecked': items the checker can't reach, e.g. beyond what it models)")
    if pacing:
        print(f"({pacing} pacing note(s) on ported quests)")
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-check", action="store_true", help="don't check the route against the progression checker")
    ap.add_argument("--dump", help="dump folder name (default: newest)")
    ap.add_argument("--world", default=os.path.join(TOOLS, ".server", "world-pregen"),
                    help="world whose blocks seed the checker (default: the pregen test world)")
    args = ap.parse_args()
    sys.path.insert(0, TOOLS)
    from mclib.paths import utf8_console  # noqa: E402
    utf8_console()

    route = json.load(open(os.path.join(HERE, "route.json"), encoding="utf-8"))
    files = build(route)
    write(files)
    n = sum(len(ch["quests"]) for ch in route["chapters"])
    print(f"Wrote {len(route['chapters'])} chapters, {n} quests to {os.path.relpath(OUT, REPO)}")
    if not args.no_check:
        problems = check(route, args.dump, args.world)
        print(f"{problems} problem(s)")
        sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
