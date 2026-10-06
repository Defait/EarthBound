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
def snbt(value, indent=0):
    pad = "\t" * indent
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value}d"
    if isinstance(value, str):
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
        inner = "\n".join(f"{pad}\t{k}: {snbt(v, indent + 1)}" for k, v in sorted(value.items()))
        return "{\n" + inner + "\n" + pad + "}"
    raise TypeError(type(value))


def stack(item):
    return {"count": 1, "id": item}


# ------------------------------------------------------------------ layout
def layout(quests):
    """Columns by longest chain of same-chapter prerequisites; rows in route order."""
    keys = {q["key"] for q in quests}
    col = {}

    def depth(q, seen=()):
        if q["key"] in col:
            return col[q["key"]]
        local = [d for d in q.get("deps", []) if d in keys and d not in seen]
        by_key = {x["key"]: x for x in quests}
        col[q["key"]] = 0 if not local else 1 + max(depth(by_key[d], seen + (q["key"],)) for d in local)
        return col[q["key"]]

    for q in quests:
        depth(q)
    rows = {}
    pos = {}
    for q in quests:
        c = col[q["key"]]
        r = rows.get(c, 0)
        rows[c] = r + 1
        pos[q["key"]] = (c, r)
    out = {}
    for key, (c, r) in pos.items():
        n = rows[c]
        out[key] = (c * 2.0, (r - (n - 1) / 2.0) * 1.75)
    return out


# ------------------------------------------------------------------ build
def build(route):
    lang = {f"file.{FILE_ID}.title": route.get("title", "Quests")}
    files = {}
    all_keys = {q["key"]: ch["key"] for ch in route["chapters"] for q in ch["quests"]}
    for order, ch in enumerate(route["chapters"]):
        cid = code("chapter", ch["key"])
        lang[f"chapter.{cid}.title"] = ch["title"]
        pos = layout(ch["quests"])
        quests = []
        for q in ch["quests"]:
            qid = code("quest", q["key"])
            missing = [d for d in q.get("deps", []) if d not in all_keys]
            if missing:
                raise SystemExit(f"quest {q['key']}: unknown dependencies {missing}")
            tasks = []
            if q.get("checkmark"):
                tasks.append({"id": code("task", q["key"] + ":check"), "type": "checkmark"})
            for i, item in enumerate(([q["item"]] if q.get("item") else []) + q.get("extra_items", [])):
                tasks.append({"id": code("task", f"{q['key']}:{i}"), "type": "item", "item": stack(item), "count": 1})
            if not tasks:
                raise SystemExit(f"quest {q['key']}: no item and not a checkmark")
            x, y = pos[q["key"]]
            entry = {"id": qid, "x": x, "y": y, "tasks": tasks,
                     "dependencies": [code("quest", d) for d in q.get("deps", [])]}
            icon = q.get("icon") or q.get("item")
            if icon:
                entry["icon"] = stack(icon)
            if q.get("big"):
                entry["size"] = 1.5
            if q.get("optional"):
                entry["optional"] = True
            quests.append(entry)
            lang[f"quest.{qid}.title"] = q["title"]
            if q.get("subtitle"):
                lang[f"quest.{qid}.quest_subtitle"] = q["subtitle"]
            if q.get("desc"):
                lang[f"quest.{qid}.quest_desc"] = q["desc"]
        files[os.path.join("chapters", ch["key"] + ".snbt")] = {
            "id": cid, "filename": ch["key"], "group": "", "order_index": order,
            "icon": stack(ch["icon"]), "default_quest_shape": "", "default_hide_dependency_lines": False,
            "quest_links": [], "quests": quests,
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
    for key, q in quests.items():
        items = ([q["item"]] if q.get("item") else []) + q.get("extra_items", [])
        depths = []
        for item in items:
            if item not in d.items:
                print(f"  ! {key}: {item} doesn't exist")
                problems += 1
            elif "i:" + item not in p.base.dist:
                print(f"  ! {key}: {item} is unreachable")
                problems += 1
            else:
                depths.append(p.base.dist["i:" + item])
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
                print(f"        ! prerequisite '{quests[x]['title']}' comes later (step {effective(x)})")
                problems += 1
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
