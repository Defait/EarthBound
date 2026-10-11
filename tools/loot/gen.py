"""Generate the era-capped chest loot of the structure mods from tools/loot/loot.json.

Usage (from the repo root):
    tools/.venv/Scripts/python tools/loot/gen.py [--out DIR] [--check] [--no-lint] [--stats]

Every chest, barrel, pot and brushable loot table a structure mod (or vanilla, or GregTech's global loot modifiers) can put in
the world skips the pack's eras: wrought iron and steel, GregTech items, vanilla iron, diamonds and emeralds, totems, golden
apples. loot.json replaces each of them (same id, so the mod's own is overridden) with TFC loot under the era cap of its
structure (stone, copper or bronze: tools/structures/catalogue.json `loot_caps`). Written:

    kubejs/data/<namespace>/loot_table/<path>.json                   one per table in loot.json (the structure mods' ids)
    kubejs/data/pack_loot/loot_table/<theme>/<era>.json              shared pieces: a theme (stone_tools, ingots, larder ...) as
                                                                     one table the structure tables roll; the file is named for the
                                                                     lowest era whose items it holds (ingots/stone has copper and
                                                                     tin, ingots/copper adds bronze and the rest)
    kubejs/data/neoforge/loot_modifiers/global_loot_modifiers.json   replace: true, keeping only the modifiers loot.json lists (none);
                                                                     this switches off GregTech's nine, which add steel, damascus
                                                                     steel, silver, chromium, gems ... to vanilla tables

loot.json has themes (weighted TFC item lists), archetypes (pools of theme mixes with rolls, as the originals have pools) and the
tables (archetype, era, `stacks`, a `tilt` of the theme mix). A theme lists everything that fits some era and each table only
gets the items under its own cap: copper and bronze tools from the copper era (checker steps 7 and 8, cap 8), bronze-age rope,
paper and chainmail from the bronze era (cap 13), ingots and ore pieces from the start. Inside a pool the theme shares are
the odds that a roll comes from that theme; inside a theme the item weights say how common an item is. `stacks` is the mean
number of stacks the original table gave per opening; the archetype's rolls are scaled to it, so small and rich originals stay
small and rich. Every item is checked against the newest recipe dump (exists), the deny-list, the caps and allow_unreachable;
problems are listed and the exit code is 1. tools/loot/generated.json lists what was written, so files of tables that left
loot.json are removed on the next run. --check writes nothing and fails when the files on disk differ from what loot.json (and
the current dump's steps) produce. tools/loot/lint.py checks the result against every table the running pack knows.
"""
import argparse
import itertools
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import lib  # noqa: E402

MANIFEST = os.path.join(HERE, "generated.json")
GLM_PATH = "kubejs/data/neoforge/loot_modifiers/global_loot_modifiers.json"
KINDS = {"chest": "minecraft:chest", "archaeology": "minecraft:archaeology", "gift": "minecraft:gift", "equipment": "minecraft:equipment"}
RESERVED_NS = {"pack", "pack_loot"}  # tools/structures/build.py owns kubejs/data/pack/loot_table; pack_loot holds the shared theme tables
THEME_NS = "pack_loot"


def expand(pattern):
    """a/{b,c}/{d,e} -> a/b/d, a/b/e, a/c/d, a/c/e (in that order)."""
    parts = re.split(r"(\{[^{}]*\})", pattern)
    choices = [p[1:-1].split(",") if p.startswith("{") else [p] for p in parts]
    return ["".join(c) for c in itertools.product(*choices)]


def norm_entry(e):
    """[item, weight, count?] or {"item", "weight", "count", "rotten"} -> (item pattern, weight, count, rotten)."""
    if isinstance(e, list):
        item, weight = e[0], e[1]
        count = e[2] if len(e) > 2 else None
        return item, float(weight), count, False
    return e["item"], float(e.get("weight", 1)), e.get("count"), bool(e.get("rotten"))


def count_fn(count):
    if count is None:
        return []
    if isinstance(count, list):
        lo, hi = count
        if lo == hi:
            return [{"function": "minecraft:set_count", "count": lo}]
        return [{"function": "minecraft:set_count", "count": {"type": "minecraft:uniform", "min": lo, "max": hi}}]
    return [{"function": "minecraft:set_count", "count": count}]


def rolls_json(lo, hi):
    if lo == hi:
        return lo
    return {"type": "minecraft:uniform", "min": lo, "max": hi}


def scale_rolls(lo, hi, size):
    a = int(lo * size + 0.5)
    b = int(hi * size + 0.5)
    if hi > 0 and b < 1:
        b = 1
    return a, max(a, b)


class Generator:
    def __init__(self, spec, rules):
        self.spec = spec
        self.rules = rules
        self.problems = []
        self.cache = {}
        self.theme_tables = {}

    def problem(self, where, msg):
        self.problems.append(f"{where}: {msg}")

    # ---------------------------------------------------------------- themes
    def theme_entries(self, name):
        """Expanded theme: [(item, weight, count, rotten, era)] (era: the earliest cap that lets the item in)."""
        if name in self.cache:
            return self.cache[name]
        out = []
        for raw in self.spec["themes"][name]:
            pattern, weight, count, rotten = norm_entry(raw)
            items = expand(pattern)
            for item in items:
                era = self.rules.era_of(item)
                if era is None:
                    why = "; ".join(self.rules.problems(item, "bronze")) or "not allowed"
                    self.problem(f"theme {name}", why)
                    continue
                out.append((item, weight / len(items), count, rotten, era))
        self.cache[name] = out
        return out

    # ---------------------------------------------------------------- theme tables
    def theme_content(self, name, era):
        """Entries of a theme under an era cap: item entries with integer weights summing to about 100."""
        kept = [e for e in self.theme_entries(name) if lib.ERAS.index(e[4]) <= lib.ERAS.index(era)]
        merged = {}
        for item, w, count, rotten, _ in kept:
            key = (item, json.dumps(count), rotten)
            merged[key] = merged.get(key, 0.0) + w
        total = sum(merged.values())
        out = []
        for (item, count, rotten), w in sorted(merged.items(), key=lambda kv: (-kv[1], kv[0][0])):
            fns = count_fn(json.loads(count))
            if rotten:
                fns.append({"function": "tfc:rotten"})
            e = {"type": "minecraft:item", "name": item, "weight": max(1, int(round(100.0 * w / total)))}
            if fns:
                e["functions"] = fns
            out.append(e)
        return out

    def theme_ref(self, name, era):
        """The id of the shared table holding a theme under an era cap (named for the lowest era with the same content), or None."""
        contents = [self.theme_content(name, e) for e in lib.ERAS]
        mine = contents[lib.ERAS.index(era)]
        if not mine:
            return None
        label = lib.ERAS[contents.index(mine)]
        tid = f"{THEME_NS}:{name}/{label}"
        self.theme_tables[tid] = {"type": "minecraft:chest", "pools": [{"rolls": 1, "entries": contents[lib.ERAS.index(label)]}]}
        return tid

    # ---------------------------------------------------------------- tables
    @staticmethod
    def empty_share(pool):
        shares = dict(pool.get("themes", {}))
        empty = shares.pop("empty", pool.get("empty", 0))
        total = sum(shares.values()) + empty
        return empty / total if total else 0.0

    def build_pool(self, tid, pool, tilt, era, size):
        shares = dict(pool.get("themes", {}))
        empty = shares.pop("empty", 0)
        for k, v in (tilt or {}).items():
            if k == "empty":
                empty = v
            else:
                shares[k] = v
        out = []
        for theme, share in shares.items():
            if share <= 0:
                continue
            if theme not in self.spec["themes"]:
                self.problem(tid, f"unknown theme {theme}")
                continue
            ref = self.theme_ref(theme, era)
            if ref:
                out.append({"type": "minecraft:loot_table", "value": ref, "weight": max(1, int(round(share * 10)))})
        if not out:
            self.problem(tid, "a pool ended up without entries (era too low for its themes?)")
            return None
        out.sort(key=lambda e: (-e["weight"], e["value"]))
        if empty:
            out.append({"type": "minecraft:empty", "weight": max(1, int(round(empty * 10)))})
        lo, hi = scale_rolls(pool["rolls"][0], pool["rolls"][1], size)
        return {"rolls": rolls_json(lo, hi), "entries": out}

    def build_table(self, tid, t):
        kind = KINDS[t.get("type", "chest")]
        if t.get("empty"):
            return {"type": kind, "pools": []}
        arch = self.spec["archetypes"].get(t.get("arch"))
        if arch is None:
            self.problem(tid, f"unknown archetype {t.get('arch')}")
            return None
        era = t["era"]
        if era not in lib.ERAS:
            self.problem(tid, f"unknown era {era}")
            return None
        tilt = t.get("tilt") or {}
        if isinstance(tilt, dict):
            tilt = [tilt]
        size = t.get("size", 1.0)
        if "stacks" in t:  # scale the archetype's rolls to the original table's mean number of stacks
            base = sum((p["rolls"][0] + p["rolls"][1]) / 2 * (1 - self.empty_share(p)) for p in arch["pools"])
            size = max(0.3, min(3.0, t["stacks"] / base)) if base else 1.0
        pools = []
        specs = list(arch["pools"]) + list(t.get("plus", []))
        for i, pool in enumerate(specs):
            p = self.build_pool(tid, pool, tilt[i] if i < len(tilt) else None, era, size if i < len(arch["pools"]) else 1.0)
            if p is not None:
                pools.append(p)
        return {"type": kind, "pools": pools}

    def run(self):
        for name in self.spec["themes"]:
            self.theme_entries(name)
        tables, aliases = {}, {}
        for tid, t in self.spec["tables"].items():
            ns = tid.split(":")[0] if ":" in tid else ""
            if not re.match(r"^[a-z0-9_.\-]+:[a-z0-9_/.\-]+$", tid):
                self.problem(tid, "not a resource location")
                continue
            if ns in RESERVED_NS:
                self.problem(tid, f"namespace {ns} belongs to tools/structures/build.py")
                continue
            if "alias" in t:
                aliases[tid] = t["alias"]
                continue
            built = self.build_table(tid, t)
            if built is not None:
                tables[tid] = built
        for tid, target in aliases.items():
            if target not in tables:
                self.problem(tid, f"alias target {target} is not a generated table")
            else:
                tables[tid] = tables[target]
        tables.update(self.theme_tables)
        files = {lib.table_path(tid): lib.dump_json(tab) for tid, tab in tables.items()}
        glm = {"replace": True, "entries": list(self.spec.get("keep_global_loot_modifiers", []))}
        files[GLM_PATH] = lib.dump_json(glm)
        return files, tables


def main():
    lib.utf8()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=lib.REPO, help="root to write under (default: the repo); use a staging folder to review")
    ap.add_argument("--check", action="store_true", help="write nothing; exit 1 if the files on disk differ from the spec")
    ap.add_argument("--no-lint", action="store_true", help="skip the checks against the recipe dump (item ids, caps)")
    ap.add_argument("--stats", action="store_true", help="print rolls and entry counts per table")
    args = ap.parse_args()

    spec = lib.load_json(lib.SPEC)
    rules = lib.Rules(with_dump=not args.no_lint)
    gen = Generator(spec, rules)
    files, tables = gen.run()
    out = os.path.abspath(args.out)

    if gen.problems:
        for p in gen.problems:
            print("PROBLEM", p)
        print(f"{len(gen.problems)} problem(s) in loot.json")
        return 1

    old = lib.load_json(MANIFEST) if os.path.exists(MANIFEST) else []
    new = sorted(files)
    if args.check:
        bad = []
        for rel, content in sorted(files.items()):
            path = os.path.join(out, rel)
            if not os.path.exists(path):
                bad.append(f"missing {rel}")
            elif open(path, "rb").read().replace(b"\r\n", b"\n") != content:
                bad.append(f"differs {rel}")
        bad += [f"stale {rel}" for rel in old if rel not in files and os.path.exists(os.path.join(out, rel))]
        if old != new:
            bad.append("generated.json is out of date")
        for b in bad:
            print("CHECK", b)
        print(f"{len(files)} files; {len(bad)} differ from loot.json" + ("" if bad else " (up to date)"))
        return 1 if bad else 0

    for rel in old:
        if rel not in files:
            p = os.path.join(out, rel)
            if os.path.exists(p):
                os.remove(p)
    for rel, content in files.items():
        p = os.path.join(out, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(content)
    if out == lib.REPO:
        with open(MANIFEST, "w", encoding="utf-8", newline="\n") as f:
            json.dump(new, f, indent=1)
            f.write("\n")
    n_chest = sum(1 for tab in tables.values() if tab["pools"])
    print(f"wrote {len(tables)} loot tables ({len(tables) - n_chest} empty) and the global loot modifier override under {out}")
    if args.stats:
        for tid, tab in sorted(tables.items()):
            rolls = " ".join(str(p["rolls"]["min"]) + "-" + str(p["rolls"]["max"]) if isinstance(p["rolls"], dict) else str(p["rolls"]) for p in tab["pools"])
            print(f"  {tid:60s} {(spec['tables'].get(tid, {}).get('era') or ''):7s} rolls {rolls:12s} entries {sum(len(p['entries']) for p in tab['pools'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
