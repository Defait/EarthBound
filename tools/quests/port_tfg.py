"""Extract TerraFirmaGreg's quests in route.json's quest format, for porting into the pack's book.

Usage (from the repo root):
    tools/.venv/Scripts/python tools/quests/port_tfg.py fetch [--ref dev]
    tools/.venv/Scripts/python tools/quests/port_tfg.py extract [CHAPTER ...]
    tools/.venv/Scripts/python tools/quests/port_tfg.py merge

TerraFirmaGreg (https://github.com/TerraFirmaGreg-Team/Modpack-Modern, LGPL-3.0) is a TFC + GregTech
pack for 1.20.1. `fetch` downloads its quest chapters and English quest text at one commit into
tools/.data/tfg/<commit>/. `extract` converts each chapter into tools/.data/tfg/extract/<chapter>.json:
quests with their text resolved from the lang files, tasks in route.json's form, dependencies as
quest keys, and notes on what doesn't carry over (items this pack doesn't have, TerraFirmaGreg-only
task types). A review then decides per quest (tools/quests/tfg_review/<chapter>.json: keep, edit with
corrected text/tasks, merge into a route quest, or drop; the brief is tfg_review/REVIEW.md), and `merge`
applies the decisions to route.json: kept quests join the book chapter the review chose, merged ones
lend their text to the route quest, dependencies on dropped quests pass through to those quests' own
prerequisites, and filter tasks lose ids this pack doesn't have. Each ported quest records its source.

After the port, route.json is the book's source and can be edited directly; `merge` rebuilds it from the
pre-port snapshot (tools/.data/tfg/route_before_port.json) plus the reviews, so re-run it only for a
re-port, and carry later hand edits over (or make them in the reviews).

Quest keys are TerraFirmaGreg's lang keys without the "quests." prefix and ".title" suffix (for
example stone_age.find_rock), so a quest keeps its key, and players their progress, across re-ports.
"""
import argparse
import glob
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(TOOLS, "recipes"))

import snbt  # noqa: E402

REPO = "TerraFirmaGreg-Team/Modpack-Modern"
DATA = os.path.join(TOOLS, ".data", "tfg")
CHAPTERS = {
    "questsstoneage": "stone_age", "questsmetallurgy": "metal_age", "questssteam_age": "steam_age",
    "ore_processing": "ore_proc", "gregtech_energy": "gregtech_energy", "lv__low_voltage": "low_voltage",
    "mv__medium_voltage": "medium_voltage", "hv__high_voltage": "high_voltage", "ev__extreme_voltage": "extreme_voltage",
    "tips__tools": "tools_tips", "tips__combat": "combat_tips", "chemical_elements": "chemical_elements",
}
LANG_REF = re.compile(r"\{([A-Za-z0-9_.\-]+)\}")
IMAGE = re.compile(r"\{image:([a-z0-9_]+):([^ }]+)[^}]*\}")
FILTER_TOKEN = re.compile(r"\b(item|item_tag|mod)\(([^()]*)\)")


def get(url, raw=False):
    req = urllib.request.Request(url, headers={"User-Agent": "mc-pack-tools", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    return data if raw else json.loads(data.decode("utf-8"))


def fetch(ref):
    sha = get(f"https://api.github.com/repos/{REPO}/commits/{ref}")["sha"]
    tree = get(f"https://api.github.com/repos/{REPO}/git/trees/{sha}?recursive=1")["tree"]
    want = [x["path"] for x in tree if x["type"] == "blob" and (
        x["path"].startswith("config/ftbquests/quests/")
        or x["path"].startswith("kubejs/assets/tfg/lang/en_us/quests/")
        or x["path"] in ("kubejs/assets/ftbquests/lang/en_us.json", "LICENSE"))]
    out = os.path.join(DATA, sha)
    for p in want:
        dest = os.path.join(out, p)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(get(f"https://raw.githubusercontent.com/{REPO}/{sha}/{p}", raw=True))
    with open(os.path.join(DATA, "CURRENT"), "w") as f:
        f.write(sha)
    print(f"Fetched {len(want)} files at {sha} into {os.path.relpath(out)}")


def source_dir():
    with open(os.path.join(DATA, "CURRENT")) as f:
        sha = f.read().strip()
    return sha, os.path.join(DATA, sha)


def load_lang(root):
    """TerraFirmaGreg's quest text, plus GregTech's material names (chemical element titles use them)."""
    import zipfile
    lang = {}
    for jar in glob.glob(os.path.join(TOOLS, ".server", "mods", "gtceu-*.jar")):
        with zipfile.ZipFile(jar) as z:
            gt = json.loads(z.read("assets/gtceu/lang/en_us.json").decode("utf-8"))
        lang.update({k: v for k, v in gt.items() if k.startswith("material.")})
    files = sorted(glob.glob(os.path.join(root, "kubejs/assets/tfg/lang/en_us/quests/*.json")))
    files.append(os.path.join(root, "kubejs/assets/ftbquests/lang/en_us.json"))
    for f in files:
        if os.path.exists(f):
            with open(f, encoding="utf-8") as fh:
                lang.update(json.load(fh))
    return lang


def resolve(text, lang):
    if not isinstance(text, str):
        return ""
    return LANG_REF.sub(lambda m: lang.get(m.group(1), m.group(0)), text)


def quest_key(q, chapter):
    m = LANG_REF.fullmatch(q.get("title", "") or "")
    if m and m.group(1).startswith("quests.") and m.group(1).endswith(".title"):
        return m.group(1)[len("quests."):-len(".title")]
    return f"{chapter}.q{q['id'].lower()}"


def modern_filter(expr):
    """1.21 spelling of a 1.20 FTB Filter System expression: no namespace on filter names, c: for forge: tags."""
    expr = re.sub(r"\bftbfiltersystem:", "", expr)
    return re.sub(r"item_tag\(forge:", "item_tag(c:", expr)


def strip_images(lines, assets, notes):
    """Drop images whose texture isn't in the pack (TerraFirmaGreg's own); keep TFC's."""
    out = []
    for line in lines:
        missing = [f"{ns}:{path}" for ns, path in IMAGE.findall(line) if f"assets/{ns}/{path}" not in assets]
        if missing:
            notes.append("dropped images: " + ", ".join(missing))
            line = IMAGE.sub(lambda m: "" if f"assets/{m.group(1)}/{m.group(2)}" not in assets else m.group(0), line).strip()
            if not line:
                continue
        out.append(line)
    while out and out[-1] in ("", "{@pagebreak}"):
        out.pop()
    return out


def item_of(it):
    """(item id, count, filter expression or None) from a 1.20 FTB Quests item."""
    if isinstance(it, str):
        return it, 1, None
    if not isinstance(it, dict):
        return None, 1, None
    count = it.get("Count", it.get("count", 1))
    tag = it.get("tag") or {}
    if it.get("id", "").startswith("ftbfiltersystem:"):
        return None, count, tag.get("ftbfiltersystem:filter")
    return it.get("id"), count, None


def convert_task(t, items, tags, notes):
    kind = t.get("type")
    out = {}
    if t.get("optional_task"):
        out["optional"] = True
    if kind == "item":
        item, count, flt = item_of(t.get("item"))
        n = t.get("count", count)
        if flt:
            flt = modern_filter(flt)
            out["filter"] = flt
            refs = FILTER_TOKEN.findall(flt)
            out["any"] = [("#" + v if k == "item_tag" else ("@" + v if k == "mod" else v)) for k, v in refs]
            rest = FILTER_TOKEN.sub("", flt)
            if re.search(r"[a-z_]+\(", rest.replace("or(", "").replace("and(", "")):
                notes.append(f"filter with more than items/tags: {flt}")
            for k, v in refs:
                if k == "item" and v not in items:
                    notes.append(f"filter item not in pack: {v}")
                if k == "item_tag" and v not in tags:
                    notes.append(f"filter tag not in pack: #{v}")
        elif item:
            out["item"] = item
            if item not in items:
                notes.append(f"item not in pack: {item}")
        else:
            notes.append(f"unreadable item task: {t.get('item')}")
            return None
        if n and n != 1:
            out["count"] = n
    elif kind == "checkmark":
        out["type"] = "checkmark"
    elif kind == "gamestage":
        out["type"] = "checkmark"
        notes.append(f"gamestage task {t.get('stage')} (set by TerraFirmaGreg scripts) became a checkmark")
    elif kind == "observation":
        out.update({"type": "observation", "observe_type": t.get("observe_type", 0), "to_observe": t.get("to_observe"),
                    "timer": t.get("timer", 0)})
    elif kind == "kill":
        out.update({"type": "kill", "entity": t.get("entity"), "value": t.get("value", 1)})
    elif kind == "dimension":
        out.update({"type": "dimension", "dimension": t.get("dimension")})
        if not str(t.get("dimension", "")).startswith("minecraft:"):
            notes.append(f"dimension not in pack: {t.get('dimension')}")
    elif kind == "biome":
        out.update({"type": "biome", "biome": t.get("biome")})
    else:
        notes.append(f"task type {kind} not ported")
        return None
    return out


def extract(names):
    sys.path.insert(0, TOOLS)
    from model import Dump, latest_dump  # noqa: E402
    import zipfile
    d = Dump(latest_dump())
    items = set(d.items)
    tags = set(d.item_tags)
    assets = set()
    for jar in glob.glob(os.path.join(TOOLS, ".server", "mods", "*.jar")):
        with zipfile.ZipFile(jar) as z:
            assets.update(n for n in z.namelist() if n.startswith("assets/") and n.endswith(".png"))
    sha, root = source_dir()
    lang = load_lang(root)
    chapters = {}
    for fname, short in CHAPTERS.items():
        with open(os.path.join(root, "config/ftbquests/quests/chapters", fname + ".snbt"), encoding="utf-8") as f:
            chapters[short] = snbt.loads(f.read())
    keys = {}
    for short, ch in chapters.items():
        for q in ch.get("quests", []):
            keys[q["id"]] = quest_key(q, short)
    # Quests in chapters not ported are kept as names, so a dependency on them can be judged.
    others = {}
    for path in glob.glob(os.path.join(root, "config/ftbquests/quests/chapters/*.snbt")):
        name = os.path.basename(path)[:-5]
        if name in CHAPTERS:
            continue
        with open(path, encoding="utf-8") as f:
            ch = snbt.loads(f.read())
        for q in ch.get("quests", []):
            others[q["id"]] = f"{name}: {resolve(q.get('title'), lang)}"
    out_dir = os.path.join(DATA, "extract")
    os.makedirs(out_dir, exist_ok=True)
    for short, ch in chapters.items():
        if names and short not in names:
            continue
        quests = []
        for q in ch.get("quests", []):
            notes = []
            tasks = [t for t in (convert_task(t, items, tags, notes) for t in q.get("tasks", [])) if t]
            deps, ext = [], []
            for dep in q.get("dependencies", []):
                if dep in keys:
                    deps.append(keys[dep])
                else:
                    ext.append(others.get(dep, dep))
            icon_item, _, _ = item_of(q.get("icon"))
            entry = {
                "key": keys[q["id"]],
                "tfg_id": q["id"],
                "title": resolve(q.get("title"), lang),
                "subtitle": resolve(q.get("subtitle"), lang),
                "desc": strip_images([resolve(x, lang) for x in q.get("description", [])], assets, notes),
                "tasks": tasks,
                "deps": deps,
                "pos": [q.get("x", 0.0), q.get("y", 0.0)],
            }
            for k in ("optional", "shape", "size", "dependency_requirement", "hide_dependency_lines", "min_required_dependencies"):
                if k in q:
                    entry[k] = q[k]
            if icon_item:
                entry["icon"] = icon_item
            if ext:
                entry["deps_outside_ported_chapters"] = ext
            if q.get("guide_page"):
                notes.append(f"TerraFirmaGreg field guide page: {q['guide_page']}")
            if notes:
                entry["notes"] = notes
            quests.append(entry)
        result = {"source": f"https://github.com/{REPO}/blob/{sha}/config/ftbquests/quests/chapters/",
                  "commit": sha, "chapter": short, "title": resolve(ch.get("title"), lang),
                  "subtitle": resolve(" ".join(ch.get("subtitle", [])) if isinstance(ch.get("subtitle"), list) else ch.get("subtitle"), lang),
                  "icon": item_of(ch.get("icon"))[0], "quests": quests}
        with open(os.path.join(out_dir, short + ".json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(result, f, indent=1, ensure_ascii=False)
            f.write("\n")
        flagged = sum(1 for q in quests if q.get("notes"))
        print(f"{short:18} {len(quests):3} quests, {flagged:3} with notes -> {os.path.relpath(os.path.join(out_dir, short + '.json'))}")


# ------------------------------------------------------------------ merge
ROUTE = os.path.join(HERE, "route.json")
REVIEW = os.path.join(HERE, "tfg_review")   # the per-quest decisions, kept with the book
TFG_TOKEN = re.compile(r"(item|item_tag)\(([^()]*)\)")
NEW_CHAPTERS = {
    # key: (title, icon, group)
    "ore_processing": ("Ore Processing", "gtceu:purified_copper_ore", None),
    "power": ("GregTech Power", "gtceu:tin_single_cable", None),
    "mv": ("MV: Medium Voltage", "gtceu:mv_machine_hull", None),
    "hv": ("HV: High Voltage", "gtceu:hv_machine_hull", None),
    "ev": ("EV: Extreme Voltage", "gtceu:ev_machine_hull", None),
    "tools_tips": ("Tips: Tools", "tfc:metal/pickaxe/bronze", "tips"),
    "combat_tips": ("Tips: Combat", "tfc:metal/sword/bronze", "tips"),
    "elements": ("Chemical Elements", "gtceu:hydrogen_bucket", "collections"),
}
# The book chapter each TerraFirmaGreg chapter mostly feeds.
NATURAL = {"stone_age": "stone", "metal_age": "iron", "steam_age": "steam", "ore_proc": "ore_processing",
           "gregtech_energy": "power", "low_voltage": "lv", "medium_voltage": "mv", "high_voltage": "hv",
           "extreme_voltage": "ev", "tools_tips": "tools_tips", "combat_tips": "combat_tips", "chemical_elements": "elements"}
BOOK_ORDER = ["welcome", "stone", "bronze", "create", "iron", "steam", "ore_processing", "lv", "power", "airships",
              "mv", "hv", "ev", "tools_tips", "combat_tips", "elements"]
GROUPS = [{"key": "tips", "title": "Tips"}, {"key": "collections", "title": "Collections"}]


def sanitize_task(t, items, tags):
    """Drop ids/tags this pack lacks from a filter; a filter left with one item becomes an item task."""
    if not t.get("filter"):
        return t if not t.get("item") or t["item"] in items else None
    expr = modern_filter(t["filter"])
    refs = TFG_TOKEN.findall(expr)
    ok = [(k, v) for k, v in refs if (v in items if k == "item" else v in tags)]
    if not ok:
        return None
    if len(ok) == 1 and ok[0][0] == "item" and re.fullmatch(r"(or\()?\s*item\([^()]*\)\s*\)?", expr.strip()):
        out = {k: v for k, v in t.items() if k not in ("filter", "any")}
        out["item"] = ok[0][1]
        return out
    if len(ok) != len(refs):
        if re.search(r"\b(and|not)\(", expr):
            return None   # dropping a term from and()/not() would change the meaning
        expr = "or(" + "".join(f"{k}({v})" for k, v in ok) + ")"
    return dict(t, filter=expr, any=[("#" + v if k == "item_tag" else v) for k, v in ok])


def write_route(route):
    """route.json's layout: one chapter header per line, one quest per line."""
    lines = ["{"]
    for k in ("_comment", "title"):
        lines.append(f"  {json.dumps(k)}: {json.dumps(route[k], ensure_ascii=False)},")
    if route.get("groups"):
        lines.append(f'  "groups": {json.dumps(route["groups"], ensure_ascii=False)},')
    lines.append('  "chapters": [')
    for ci, ch in enumerate(route["chapters"]):
        head = {k: v for k, v in ch.items() if k != "quests"}
        lines.append("    {")
        lines.append("      " + json.dumps(head, ensure_ascii=False)[1:-1] + ",")
        lines.append('      "quests": [')
        for qi, q in enumerate(ch["quests"]):
            lines.append("        " + json.dumps(q, ensure_ascii=False) + ("," if qi < len(ch["quests"]) - 1 else ""))
        lines.append("      ]")
        lines.append("    }" + ("," if ci < len(route["chapters"]) - 1 else ""))
    lines.append("  ]")
    lines.append("}")
    with open(ROUTE, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def merge(only=None):
    from model import Dump, latest_dump  # noqa: E402
    d = Dump(latest_dump())
    items, tags = set(d.items), set(d.item_tags)
    # Merge onto the book as it was before the first port, so re-running after review changes
    # doesn't stack ports (the snapshot lives in tools/.data/tfg/).
    base = os.path.join(DATA, "route_before_port.json")
    if not os.path.exists(base):
        with open(ROUTE, encoding="utf-8") as f:
            if "Ported from TerraFirmaGreg" in f.read():
                raise SystemExit("route.json already has ported quests and there's no pre-port snapshot")
        import shutil
        shutil.copy2(ROUTE, base)
    with open(base, encoding="utf-8") as f:
        route = json.load(f)
    sha, _ = source_dir()
    route_keys = {q["key"]: q for ch in route["chapters"] for q in ch["quests"]}
    extracts, reviewed = {}, {}
    for short in CHAPTERS.values():
        if only and short not in only:
            continue
        with open(os.path.join(DATA, "extract", short + ".json"), encoding="utf-8") as f:
            extracts[short] = json.load(f)
        with open(os.path.join(REVIEW, short + ".json"), encoding="utf-8") as f:
            for dec in json.load(f)["decisions"]:
                reviewed.setdefault(dec["key"], []).append((short, dec))
    sources = {}
    for short, ex in extracts.items():
        for q in ex["quests"]:
            sources.setdefault(q["key"], []).append((short, q))
    missing = [k for k in sources if k not in reviewed]
    extra = [k for k in reviewed if k not in sources]
    if missing or extra:
        raise SystemExit(f"review incomplete: no decision for {missing[:10]}; unknown keys {extra[:10]}")

    # TerraFirmaGreg copies a few quests into a second chapter (same key). One decision wins: the one
    # from the chapter the key belongs to, unless it drops a quest that another review keeps.
    rank = {"merge": 3, "edit": 2, "keep": 1, "drop": 0}
    decisions, source = {}, {}
    for key, decs in reviewed.items():
        home = [x for x in decs if x[0] == key.split(".")[0]]
        best = max(decs, key=lambda x: rank[x[1]["action"]])
        short, dec = home[0] if home and (home[0][1]["action"] != "drop" or best[1]["action"] == "drop") else best
        decisions[key] = dec
        # Take the copy from the TerraFirmaGreg chapter that matches where the quest goes, so its
        # position fits that chapter's layout.
        natural = [x for x in sources[key] if NATURAL.get(x[0]) == dec.get("chapter")]
        source[key] = natural[0] if natural else next((x for x in sources[key] if x[0] == short), sources[key][0])

    # Where each TerraFirmaGreg key ends up: itself (kept), a route quest (merged), or nowhere (dropped).
    alias = {}
    for key, dec in decisions.items():
        if dec["action"] in ("keep", "edit"):
            alias[key] = key
        elif dec["action"] == "merge":
            if dec["merge_into"] not in route_keys:
                raise SystemExit(f"{key}: merge_into {dec['merge_into']} isn't a route quest")
            alias[key] = dec["merge_into"]

    def resolve_deps(raw, owner, seen=()):
        """Prerequisites as book keys: route keys stay, merged keys become their route quest, and a
        dropped quest is replaced by its own prerequisites."""
        out = []
        for dep in raw:
            if dep in seen or dep == owner:
                continue
            if dep in route_keys:
                target = dep
            elif dep in alias:
                target = alias[dep]
            elif dep in source:
                dec = decisions[dep]
                out += [x for x in resolve_deps(dec.get("deps", source[dep][1]["deps"]), owner, seen + (dep,)) if x not in out]
                continue
            else:
                continue
            if target != owner and target not in out:
                out.append(target)
        return out

    def title_of(key, dec, src):
        t = dec.get("title") or src.get("title") or dec.get("subtitle") or src.get("subtitle")
        return t or key.split(".")[-1].replace("_", " ").capitalize()

    def sane_tasks(tasks):
        out = [t for t in (sanitize_task(t, items, tags) for t in tasks) if t]
        return out or [{"type": "checkmark"}]

    import pack_query
    known = pack_query.load()

    def reachable(tasks):
        """False when some required item task has nothing the progression checker can reach."""
        for t in tasks:
            pats = [t["item"]] if t.get("item") else t.get("any", [])
            if not pats or t.get("optional"):
                continue
            nodes = []
            for pat in pats:
                nodes += known["tags"].get(pat[1:], []) if pat.startswith("#") else [pat]
            if not any(known["items"].get(n, {}).get("step") is not None for n in nodes):
                return False
        return True

    credit = f"Ported from TerraFirmaGreg (LGPL-3.0), commit {sha[:10]}"
    chapters = {ch["key"]: ch for ch in route["chapters"]}
    from_tfg = {}
    for key, dec in decisions.items():
        short, src = source[key]
        if dec["action"] == "merge":
            q = route_keys[dec["merge_into"]]
            for k in ("title", "subtitle", "desc"):
                if dec.get(k):
                    q[k] = dec[k]
            if dec.get("tasks"):
                for k in ("item", "checkmark", "extra_items"):
                    q.pop(k, None)
                q["tasks"] = sane_tasks(dec["tasks"])
            if dec.get("deps"):
                q["deps"] = list(dict.fromkeys(q.get("deps", []) + resolve_deps(dec["deps"], q["key"])))
            if dec.get("icon") in items:
                q["icon"] = dec["icon"]
            q.setdefault("source", credit)
            continue
        if dec["action"] not in ("keep", "edit"):
            continue
        q = {"key": key, "title": title_of(key, dec, src)}
        for k in ("subtitle", "desc"):
            v = dec.get(k, src.get(k))
            if v:
                q[k] = v
        q["tasks"] = sane_tasks(dec.get("tasks", src["tasks"]))
        deps = resolve_deps(dec.get("deps", src["deps"]), key)
        if deps:
            q["deps"] = deps
        icon = dec.get("icon") or src.get("icon")
        if icon and icon in items:
            q["icon"] = icon
        for k in ("optional", "shape", "size", "dependency_requirement", "hide_dependency_lines", "min_required_dependencies"):
            v = dec.get(k, src.get(k))   # a review can override the source's flags
            if v not in (None, "", False) and not (k == "size" and v == 1.0):
                q[k] = v
        if dec.get("unchecked") or not reachable(q["tasks"]):
            q["unchecked"] = True
        q["pos"] = src["pos"]
        q["source"] = f"{credit}, chapter {extracts[short]['chapter']}"
        target = dec["chapter"]
        if target not in chapters:
            if target not in NEW_CHAPTERS:
                raise SystemExit(f"{key}: unknown chapter {target}")
            title, icon_, group = NEW_CHAPTERS[target]
            chapters[target] = {"key": target, "title": title, "icon": icon_, "quests": []}
            if group:
                chapters[target]["group"] = group
        chapters[target]["quests"].append(q)
        from_tfg.setdefault(target, []).append((short, q))

    # Merged route quests can now depend on ported quests; make sure that didn't close a loop.
    book = {q["key"]: q for ch in chapters.values() for q in ch["quests"]}
    state = {}

    def visit(k, path):
        if state.get(k) == 1:
            raise SystemExit("dependency loop: " + " -> ".join(path + [k]))
        if state.get(k) == 2:
            return
        state[k] = 1
        for dep in book.get(k, {}).get("deps", []):
            visit(dep, path + [k])
        state[k] = 2

    for k in book:
        visit(k, [])
    # Route quests that pointed at a merged TerraFirmaGreg key don't exist; only fix ported deps above.
    for key, ch in chapters.items():
        placed = from_tfg.get(key, [])
        native = [q for q in ch["quests"] if not q.get("source", "").startswith("Ported")]
        counts = {}
        for short, _ in placed:
            counts[short] = counts.get(short, 0) + 1
        main = max(counts, key=counts.get) if counts else None
        # A new chapter fed (almost) only by one TerraFirmaGreg chapter keeps that chapter's layout;
        # the few quests from elsewhere line up in a column to its right.
        if key in NEW_CHAPTERS and not native and main and counts[main] >= 0.8 * len(placed):
            ch["layout"] = "manual"
            right = max(q["pos"][0] for short, q in placed if short == main) + 2.0
            top = min(q["pos"][1] for short, q in placed if short == main)
            others = [q for short, q in placed if short != main]
            for i, q in enumerate(others):
                q["pos"] = [right, top + 1.5 * i]
        else:
            ch.pop("layout", None)
            for q in ch["quests"]:
                q.pop("pos", None)
    route["chapters"] = [chapters[k] for k in BOOK_ORDER if k in chapters]
    route["groups"] = [g for g in GROUPS if any(ch.get("group") == g["key"] for ch in route["chapters"])]
    write_route(route)
    counts = {}
    for dec in decisions.values():
        counts[dec["action"]] = counts.get(dec["action"], 0) + 1
    print(f"Merged {len(decisions)} TerraFirmaGreg quests into {os.path.relpath(ROUTE)}: {counts}")
    for ch in route["chapters"]:
        unchecked = sum(1 for q in ch["quests"] if q.get("unchecked"))
        print(f"  {ch['key']:15} {len(ch['quests']):4} quests{'  (TerraFirmaGreg layout)' if ch.get('layout') else ''}"
              + (f", {unchecked} with items the checker can't reach" if unchecked else ""))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--ref", default="dev")
    e = sub.add_parser("extract")
    e.add_argument("chapters", nargs="*")
    m = sub.add_parser("merge")
    m.add_argument("chapters", nargs="*", help="only these chapters (default: all)")
    args = ap.parse_args()
    from mclib.paths import utf8_console  # noqa: E402
    utf8_console()
    if args.cmd == "fetch":
        fetch(args.ref)
    elif args.cmd == "extract":
        extract(args.chapters)
    else:
        merge(args.chapters)


if __name__ == "__main__":
    main()
