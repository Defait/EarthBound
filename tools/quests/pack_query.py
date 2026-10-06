"""Look things up in the pack for quest writing: names, progression steps, recipes, tags.

Usage (from the repo root):
    tools/.venv/Scripts/python tools/quests/pack_query.py item ID [ID ...]     name, step, how it's made
    tools/.venv/Scripts/python tools/quests/pack_query.py search TEXT          items whose id or name contains TEXT
    tools/.venv/Scripts/python tools/quests/pack_query.py tag TAG              a tag's items ('#' optional)
    tools/.venv/Scripts/python tools/quests/pack_query.py uses ID              recipes that take the item

Built from the newest recipe dump and the progression checker (step = how many crafting steps from a
fresh world the checker needs; 'unreachable' means it can't find a route). The first run builds a
cache in tools/.data/quests/pack_items.json (a minute); later runs are instant until the dump changes.
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(TOOLS, "recipes"))
CACHE = os.path.join(TOOLS, ".data", "quests", "pack_items.json")


def fmt_recipe(r, name):
    ins = []
    for s in r["slots"]:
        refs = s["refs"][:3]
        label = " | ".join(name(x) if x.startswith("i:") or x.startswith("f:") else x for x in refs)
        if len(s["refs"]) > 3:
            label += " | ..."
        ins.append(f"{s['n']}x {label}")
    outs = ", ".join(f"{o['n']}x {name(o['node'])}" + (f" ({o['chance']:.0%})" if o["chance"] < 1 else "") for o in r["outputs"][:4])
    params = {k: v for k, v in r["params"].items() if k in ("eut", "duration", "heat_requirement", "temperature", "tier", "ebf_temp", "grid")}
    return f"{r['id']} [{r['type']}]{' ' + json.dumps(params) if params else ''}: {' + '.join(ins)} -> {outs}"


def build():
    from assets import GameAssets  # noqa: E402
    from mclib.paths import DEFAULT_INSTANCE, PRISM  # noqa: E402
    from model import Dump, latest_dump  # noqa: E402
    from progression import Progression, world_seeds  # noqa: E402

    path = latest_dump()
    d = Dump(path)
    cfg = json.load(open(os.path.join(TOOLS, "recipes", "progression.json"), encoding="utf-8"))
    seeds, info, _ = world_seeds(d, os.path.join(TOOLS, ".server", "world-pregen"), cfg)
    for p in cfg.get("seeds", {}).get("extra", []):
        seeds.add(p if p.startswith(("i:", "f:")) else "i:" + p)
    p = Progression(d, seeds=seeds, seed_info=info)
    client = os.path.join(PRISM, "libraries", "com", "mojang", "minecraft", "1.21.1", "minecraft-1.21.1-client.jar")
    jars = ([client] if os.path.exists(client) else []) + sorted(glob.glob(os.path.join(DEFAULT_INSTANCE, "mods", "*.jar")))
    assets = GameAssets(jars)
    names = {}

    def name(node):
        if node not in names:
            names[node] = assets.name(node) if node.startswith(("i:", "f:")) else node
        return names[node]

    made_by, used_in = {}, {}
    for r in d.recipes:
        for o in r["outputs"]:
            made_by.setdefault(o["node"], []).append(r)
        for s in r["slots"]:
            for n in (s["set"] or ()):
                used_in.setdefault(n, []).append(r["id"])
    out = {"dump": d.name, "items": {}, "tags": {t: sorted(x[2:] for x in v) for t, v in d.item_tags.items()}}
    for item in sorted(d.items):
        node = "i:" + item
        rs = sorted(made_by.get(node, []), key=lambda r: max([p.base.dist.get(n, 999) for s in r["slots"] for n in (s["set"] or ())] or [0]))
        out["items"][item] = {
            "name": name(node), "step": p.base.dist.get(node),
            "made_by": [fmt_recipe(r, name) for r in rs[:4]] + ([f"... {len(rs) - 4} more"] if len(rs) > 4 else []),
            "used_in": len(used_in.get(node, [])), "uses": used_in.get(node, [])[:40],
        }
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    return out


def load():
    from model import latest_dump  # noqa: E402
    want = os.path.basename(latest_dump())
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("dump") == want:
            return data
    print("(building the item cache from the newest dump, about a minute)", file=sys.stderr)
    return build()


def show(data, item):
    e = data["items"].get(item)
    if not e:
        print(f"{item}: NOT IN THE PACK")
        return
    step = "unreachable" if e["step"] is None else f"step {e['step']}"
    print(f"{item}: \"{e['name']}\", {step}, used in {e['used_in']} recipes")
    for r in e["made_by"] or ["(no recipe: found in the world, dropped, or made in-world)"]:
        print(f"    made by {r}")


def main():
    from mclib.paths import utf8_console  # noqa: E402
    utf8_console()
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    cmd, args = sys.argv[1], sys.argv[2:]
    data = load()
    if cmd == "item":
        for a in args:
            show(data, a)
    elif cmd == "search":
        text = " ".join(args).lower()
        hits = [(i, e) for i, e in data["items"].items() if text in i.lower() or text in e["name"].lower()]
        for i, e in hits[:60]:
            print(f"{i}: \"{e['name']}\", {'unreachable' if e['step'] is None else 'step ' + str(e['step'])}")
        if len(hits) > 60:
            print(f"... {len(hits) - 60} more")
    elif cmd == "tag":
        for a in args:
            t = a.lstrip("#")
            members = data["tags"].get(t)
            print(f"#{t}: " + (", ".join(members[:40]) + (f" ... ({len(members)})" if len(members) > 40 else "") if members else "NOT IN THE PACK (no such tag)"))
    elif cmd == "uses":
        for a in args:
            e = data["items"].get(a)
            print(f"{a}: " + (", ".join(e["uses"]) if e else "NOT IN THE PACK"))
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
