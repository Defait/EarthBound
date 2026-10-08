"""Shared bits of the loot tools: the pack's era caps and deny-list, item steps, and loot table JSON walking.

The caps live in tools/structures/catalogue.json (`loot_caps`, shared with the pack's own structures) and the progression
steps in the recipe dump's cache (tools/quests/pack_query.py): stone 6, copper 8, bronze 13 steps; deny regexes; items the
checker cannot reach are allowed only when they match `allow_unreachable`.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
REPO = os.path.dirname(TOOLS)
CATALOGUE = os.path.join(TOOLS, "structures", "catalogue.json")
SPEC = os.path.join(HERE, "loot.json")
ERAS = ["stone", "copper", "bronze"]


def utf8():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump_json(obj):
    """The format the pack's other generated loot tables use (tools/structures/build.py)."""
    return (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


class Rules:
    """Caps, deny-list and unreachable allow-list from the catalogue, with the item facts of the newest recipe dump."""

    def __init__(self, with_dump=True):
        caps = load_json(CATALOGUE)["loot_caps"]
        self.caps = {e: caps[e] for e in ERAS}
        self.deny = [re.compile(p) for p in caps["deny"]]
        self.allow_unreachable = [re.compile(p) for p in caps["allow_unreachable"]]
        self.items = None
        self.steps = None
        self.dump = None
        if with_dump:
            self._load_dump()

    def _load_dump(self):
        sys.path.insert(0, os.path.join(TOOLS, "recipes"))
        sys.path.insert(0, os.path.join(TOOLS, "quests"))
        sys.path.insert(0, TOOLS)
        try:
            import pack_query
            data = pack_query.load()
        except SystemExit as e:  # no dump at all
            raise SystemExit(f"loot tools need a recipe dump (tools/recipes/dump.py): {e}")
        self.dump = data["dump"]
        self.items = set(data["items"])
        self.steps = {k: v["step"] for k, v in data["items"].items()}

    def denied(self, item):
        return any(d.search(item) for d in self.deny)

    def era_of(self, item):
        """The earliest era whose cap lets the item in: 'stone' (also for items the checker cannot reach but allows), 'copper',
        'bronze'; None if it is denied, unknown, unreachable and not allowed, or above the bronze cap."""
        if self.denied(item):
            return None
        if self.items is not None and item not in self.items:
            return None
        s = (self.steps or {}).get(item)
        if s is None:
            return "stone" if any(a.search(item) for a in self.allow_unreachable) else None
        for e in ERAS:
            if s <= self.caps[e]:
                return e
        return None

    def problems(self, item, cap_era):
        """Why `item` does not fit under the cap of `cap_era` (a list of strings, empty when fine)."""
        out = []
        if self.items is not None and item not in self.items:
            return [f"unknown item {item}"]
        if self.denied(item):
            out.append(f"{item} is on the deny-list (skips an era)")
        s = (self.steps or {}).get(item)
        cap = self.caps.get(cap_era)
        if s is None:
            if not any(a.search(item) for a in self.allow_unreachable):
                out.append(f"{item} is unreachable for the progression checker and not in allow_unreachable")
        elif cap is not None and s > cap:
            out.append(f"{item} is step {s}, above the {cap_era} cap {cap}")
        return out


def refs(table):
    """What a loot table JSON names: (items, tags, tables). Deep: also catches set_contents and nested alternatives."""
    items, tags, tables = set(), set(), set()

    def walk(v):
        if isinstance(v, dict):
            t = v.get("type")
            if t == "minecraft:item" and isinstance(v.get("name"), str):
                items.add(v["name"])
            elif t == "minecraft:tag" and isinstance(v.get("name"), str):
                tags.add(v["name"])
            elif t == "minecraft:loot_table" and isinstance(v.get("value"), str):
                tables.add(v["value"])
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    walk(table)
    return items, tags, tables


def table_path(tid):
    """kubejs/data/<ns>/loot_table/<path>.json (relative, forward slashes) for a table id."""
    ns, path = tid.split(":", 1)
    return f"kubejs/data/{ns}/loot_table/{path}.json"
