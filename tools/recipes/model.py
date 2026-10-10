"""Load a recipe dump and normalize every recipe into slots and outputs.

Node keys: "i:<item id>" for items, "f:<fluid id>" for fluids. Tag references
keep their own form ("#i:<tag>", "#f:<tag>") for display; each slot also
carries the resolved set of concrete nodes that satisfy it.

A normalized recipe:
    {"id", "type", "kind" (the JSON "type", e.g. crafting_shaped),
     "slots": [{"refs": [...], "set": frozenset or None (= anything), "n": count/amount,
                "consumed": bool, "role": json key}],
     "outputs": [{"node", "n", "chance"}],
     "params": {...},                        # temperature, tier, eut, duration, ...
     "skip": reason or None}                 # e.g. "special" for dynamic crafting
"""
import glob
import hashlib
import json
import os
import re
from collections import Counter, defaultdict

from mclib.paths import DATA_DIR

DUMPS = os.path.join(DATA_DIR, "dumps")

# Ingredient wrappers that constrain item state (freshness, traits), not identity.
STATE_ONLY = {"tfc:not_rotten", "tfc:lacks_trait", "tfc:has_trait", "tfc:heatable", "tfc:hot", "tfc:heat", "tfc:fluid_item"}
ITEM_INPUT_KEYS = ["ingredient", "ingredients", "input", "base", "template", "addition", "first_input", "second_input",
                   "input_item", "catalyst", "mold",
                   # block the recipe works on (ArborFirmaCraft tree tapping, Roads and Roofs block_mod) and Framed Blocks' extra parts
                   "input_block", "additives",
                   # ExtendedAE's crystal assembler (a list of {ingredient, amount}) and crystal fixer (the dust it burns)
                   "input_items", "fuel"]
FLUID_INPUT_KEYS = ["fluid", "input_fluid", "fluid_ingredient", "primary_fluid", "added_fluid", "contents"]
ITEM_OUTPUT_KEYS = ["result", "results", "output", "outputs", "item_output", "result_item", "output_item", "sealed_result", "unsealed_result",
                    "output_block"]
FLUID_OUTPUT_KEYS = ["result_fluid", "fluid_output", "output_fluid"]
NOT_CONSUMED_KEYS = {"mold", "catalyst"}
STRUCTURE_KEYS = {"type", "pattern", "key", "inputs", "outputs", "tickInputs", "tickOutputs", "sequence", "transitional_item",
                  "remainder", "primary_ingredient", "group", "category", "show_notification", "rules", "data", "recipeConditions"}
SKIP_TYPES = {"almostunified:client_recipe_tracker"}
WORLD_TYPES = {"tfc:collapse", "tfc:landslide"}
TOOL_TAG_RE = re.compile(r"^#i:c:tools/")


def latest_dump():
    dumps = sorted(d for d in glob.glob(os.path.join(DUMPS, "*")) if os.path.exists(os.path.join(d, "index.json")))
    if not dumps:
        raise SystemExit("No recipe dump found. Run: tools/.venv/Scripts/python tools/recipes/dump.py")
    return dumps[-1]


def list_dumps():
    return sorted(os.path.basename(d) for d in glob.glob(os.path.join(DUMPS, "*")) if os.path.exists(os.path.join(d, "index.json")))


class Dump:
    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        self.index = json.load(open(os.path.join(path, "index.json")))
        self.meta = json.load(open(os.path.join(path, "meta.json"))) if os.path.exists(os.path.join(path, "meta.json")) else {}
        items = json.load(open(os.path.join(path, "items.json")))
        fluids = json.load(open(os.path.join(path, "fluids.json")))
        blocks = json.load(open(os.path.join(path, "blocks.json")))
        self.items = set(items["ids"])
        self.fluids = set(fluids["ids"])
        self.blocks = set(blocks["ids"])
        self.item_tags = {t: frozenset("i:" + m for m in v) for t, v in items["tags"].items()}
        self.fluid_tags = {t: frozenset("f:" + m for m in v) for t, v in fluids["tags"].items()}
        self.block_tags = {t: frozenset("i:" + m for m in v if m in self.items) for t, v in blocks["tags"].items()}
        self.unknown_forms = Counter()
        self.recipes = []
        self._type_files = {}
        for f in sorted(glob.glob(os.path.join(path, "recipes", "*", "*.json"))):
            for raw in json.load(open(f, encoding="utf-8")):
                r = self._parse(raw)
                r["hash"] = hashlib.md5(json.dumps(raw.get("json"), sort_keys=True).encode()).hexdigest()
                self._type_files[r["type"]] = f
                self.recipes.append(r)
        self.by_id = {r["id"]: r for r in self.recipes}
        self._index()

    def raw_json(self, recipe_id):
        """The recipe as encoded by the game (read from the dump on demand)."""
        r = self.by_id.get(recipe_id)
        f = r and self._type_files.get(r["type"])
        if not f:
            return None
        for raw in json.load(open(f, encoding="utf-8")):
            if raw["id"] == recipe_id:
                return raw.get("json") or {"error": raw.get("error")}
        return None

    # ------------------------------------------------------------ indexing
    def _index(self):
        self.producers = defaultdict(list)   # node -> recipe ids
        self.consumers = defaultdict(list)
        self.node_tags = defaultdict(list)   # node -> tags containing it
        for t, members in self.item_tags.items():
            for m in members:
                self.node_tags[m].append("#i:" + t)
        for t, members in self.fluid_tags.items():
            for m in members:
                self.node_tags[m].append("#f:" + t)
        for r in self.recipes:
            for o in r["outputs"]:
                self.producers[o["node"]].append(r["id"])
            seen = set()
            for s in r["slots"]:
                for n in s["set"] or ():
                    if n not in seen:
                        seen.add(n)
                        self.consumers[n].append(r["id"])

    def nodes(self):
        return {"i:" + i for i in self.items} | {"f:" + f for f in self.fluids}

    # ------------------------------------------------------------ ingredients
    def resolve(self, ref):
        if ref.startswith("#i:"):
            return self.item_tags.get(ref[3:], frozenset())
        if ref.startswith("#f:"):
            return self.fluid_tags.get(ref[3:], frozenset())
        if ref.startswith("#b:"):
            return self.block_tags.get(ref[3:], frozenset())
        return frozenset([ref])

    def _ing(self, o, fluid=False):
        """Return (refs, set) for an ingredient; set None means 'anything' (no identity constraint)."""
        if isinstance(o, list):
            parts = [self._ing(x, fluid) for x in o]
            if any(p[1] is None for p in parts):
                return [], None
            refs = [r for p in parts for r in p[0]]
            return refs, frozenset().union(*(p[1] for p in parts)) if parts else frozenset()
        if isinstance(o, str):
            ref = ("#" if o.startswith("#") else "") + ("f:" if fluid else "i:") + o.lstrip("#")
            return [ref], self.resolve(ref)
        if not isinstance(o, dict):
            self.unknown_forms[type(o).__name__] += 1
            return [], None
        t = o.get("type")
        if t in STATE_ONLY and "ingredient" not in o:
            return [], None
        if t == "gtceu:circuit":
            ref = "i:gtceu:programmed_circuit"
            return [f"{ref} (config {o.get('configuration')})"], frozenset([ref])
        if t == "neoforge:compound" or ("children" in o and t not in ("neoforge:intersection", "tfc:and")):
            return self._ing(o.get("children", []), fluid)
        if t in ("neoforge:intersection", "tfc:and"):
            parts = [p for p in (self._ing(c, fluid) for c in o.get("children", [])) if p[1] is not None]
            if not parts:
                return [], None
            s = parts[0][1]
            for p in parts[1:]:
                s = s & p[1]
            return [" ∩ ".join("/".join(p[0]) for p in parts)], s
        if t == "neoforge:difference":
            b, sub = self._ing(o.get("base"), fluid), self._ing(o.get("subtracted"), fluid)
            return [f"{'/'.join(b[0])} minus {'/'.join(sub[0])}"], (b[1] or frozenset()) - (sub[1] or frozenset())
        if t == "neoforge:block_tag":
            ref = "#b:" + o["tag"]
            return [ref], self.resolve(ref)
        if t == "neoforge:components":
            ids = o.get("fluids") or o.get("items")
            is_fluid = "fluids" in o
            ids = ids if isinstance(ids, list) else [ids]
            refs = [("f:" if is_fluid else "i:") + i for i in ids]
            return refs, frozenset(refs)
        if "ingredient" in o:
            return self._ing(o["ingredient"], fluid)
        if isinstance(o.get("fluid"), dict):
            return self._ing(o["fluid"], True)
        if isinstance(o.get("fluid"), str):
            ref = "f:" + o["fluid"]
            return [ref], frozenset([ref])
        if isinstance(o.get("item"), str):
            ref = "i:" + o["item"]
            return [ref], frozenset([ref])
        if isinstance(o.get("tag"), str):
            is_fluid = fluid or t == "neoforge:tag" or "amount" in o
            ref = ("#f:" if is_fluid else "#i:") + o["tag"]
            return [ref], self.resolve(ref)
        if isinstance(o.get("id"), str):
            is_fluid = fluid or ("amount" in o and "count" not in o)
            ref = ("f:" if is_fluid else "i:") + o["id"]
            return [ref], frozenset([ref])
        if isinstance(o.get("items"), list):
            return self._ing(o["items"], fluid)
        if isinstance(o.get("block"), str):
            ref = "i:" + o["block"]
            return [ref], frozenset([ref])
        self.unknown_forms[t or ",".join(sorted(o))[:60]] += 1
        return [], None

    def _slot(self, o, role, fluid=False, consumed=True, n=None):
        refs, s = self._ing(o, fluid)
        if n is None and isinstance(o, dict):
            n = o.get("count", o.get("amount", 1))
        return {"refs": refs, "set": s, "n": n or 1, "consumed": consumed, "role": role}

    def _out(self, o, fluid=False, chance=1.0):
        """Normalize an output (item stack, fluid stack, provider, list, or bare id)."""
        if o is None:
            return []
        if isinstance(o, list):
            return [x for e in o for x in self._out(e, fluid, chance)]
        if isinstance(o, str):
            return [{"node": ("f:" if fluid else "i:") + o, "n": 1, "chance": chance}]
        if not isinstance(o, dict):
            return []
        if "stack" in o:
            return self._out(o["stack"], fluid, chance)
        c = o.get("chance", chance)
        if isinstance(o.get("items"), (str, list)) or isinstance(o.get("fluids"), (str, list)):
            is_fluid = fluid or "fluids" in o
            ids = o["fluids"] if "fluids" in o else o["items"]
            ids = ids if isinstance(ids, list) else [ids]
            return [{"node": ("f:" if is_fluid else "i:") + ids[0], "n": o.get("count", o.get("amount", 1)), "chance": c}]
        if isinstance(o.get("tag"), str):   # tag output: the tag's preferred member
            members = sorted(self.resolve(("#f:" if fluid else "#i:") + o["tag"]), key=lambda m: (":gtceu:" not in ":" + m, m))
            return [{"node": members[0], "n": o.get("count", o.get("amount", 1)), "chance": c}] if members else []
        if "Name" in o:
            return [{"node": "i:" + o["Name"], "n": 1, "chance": c}]
        for key in ("id", "item", "fluid"):
            if isinstance(o.get(key), str):
                is_fluid = fluid or key == "fluid" or ("amount" in o and "count" not in o)
                return [{"node": ("f:" if is_fluid else "i:") + o[key], "n": o.get("count", o.get("amount", 1)), "chance": c}]
        return []

    # ------------------------------------------------------------ recipes
    def _parse(self, raw):
        j = raw.get("json") or {}
        r = {"id": raw["id"], "type": raw["type"], "kind": j.get("type", raw["type"]), "slots": [], "outputs": [],
             "params": {}, "skip": None}
        if raw["type"] in SKIP_TYPES:
            r["skip"] = "bookkeeping"
            return r
        if "error" in raw:
            r["skip"] = "not encodable: " + raw["error"][:200]
            return r
        if raw["type"] in WORLD_TYPES:
            r["skip"] = "world physics"
        kind = r["kind"]
        if kind.startswith("minecraft:crafting_special") or kind in ("minecraft:crafting_decorated_pot",):
            r["skip"] = "special (dynamic) crafting"
            return r
        # GregTech's capability maps are dicts; other mods' "outputs" are plain lists (Complicated Bees' centrifuge)
        if isinstance(j.get("inputs"), dict) or isinstance(j.get("outputs"), dict) or "tickInputs" in j:
            self._parse_gt(j, r)
        else:
            self._parse_generic(j, r)
        for k, v in j.items():
            if k not in STRUCTURE_KEYS and k not in ITEM_INPUT_KEYS + FLUID_INPUT_KEYS + ITEM_OUTPUT_KEYS + FLUID_OUTPUT_KEYS \
                    and isinstance(v, (int, float, str, bool)):
                r["params"][k] = v
        if isinstance(j.get("data"), dict):
            r["params"].update({k: v for k, v in j["data"].items() if isinstance(v, (int, float, str))})
        if "pattern" in j:
            p = j["pattern"]
            r["params"]["grid"] = f"{max(map(len, p)) if p else 0}x{len(p)}"
        for s in r["slots"]:
            if any(TOOL_TAG_RE.match(ref) for ref in s["refs"]):
                s["consumed"] = False
        return r

    def _parse_generic(self, j, r):
        if "pattern" in j and "key" in j:
            counts = Counter(ch for row in j["pattern"] for ch in row if ch != " ")
            for ch, n in counts.items():
                if ch in j["key"]:
                    r["slots"].append(self._slot(j["key"][ch], f"key '{ch}'", n=n))
        if j.get("type") == "create:sequenced_assembly" or "sequence" in j:
            trans = set(self._ing(j.get("transitional_item", {}))[1] or ())
            seen = []
            for step in [{"ingredients": [j.get("ingredient")]}] + j.get("sequence", []):
                for ing in step.get("ingredients", []):
                    s = self._slot(ing, "sequence")
                    if s["set"] is not None and (s["set"] <= trans or s["set"] in seen):
                        continue
                    seen.append(s["set"])
                    r["slots"].append(s)
            r["params"]["loops"] = j.get("loops")
            r["params"]["steps"] = ",".join(step.get("type", "?") for step in j.get("sequence", []))
            r["outputs"] += self._out(j.get("results"))
            return
        primary = j.get("primary_ingredient")
        for key in ITEM_INPUT_KEYS:
            if key not in j or (key == "primary_ingredient"):
                continue
            v = j[key]
            if key == "ingredients" and isinstance(v, dict) and set(v) <= {"top", "middle", "bottom"}:
                # AE2's inscriber: top/bottom are presses that inscribing leaves in place, 'press' mode uses everything up
                for part, ing in v.items():
                    r["slots"].append(self._slot(ing, part, consumed=j.get("mode") == "press" or part == "middle"))
            elif key in ("ingredients", "additives", "input_items") and isinstance(v, list):
                for ing in v:
                    is_fluid = key != "input_items" and isinstance(ing, dict) and ("amount" in ing or ing.get("type") in ("neoforge:single", "neoforge:tag", "tfc:fluid_content"))
                    r["slots"].append(self._slot(ing, key, fluid=is_fluid))
            else:
                r["slots"].append(self._slot(v, key, consumed=key not in NOT_CONSUMED_KEYS))
        if primary is not None and not any(self._ing(primary)[0] == s["refs"] for s in r["slots"]):
            r["slots"].append(self._slot(primary, "primary_ingredient"))
        for key in FLUID_INPUT_KEYS:
            if key not in j:
                continue
            v = j[key]
            if key == "contents":   # tfc:alloy: fluid ratios
                for c in v:
                    r["slots"].append(self._slot(c, "alloy part", fluid=True, n=f"{c.get('min')}–{c.get('max')}"))
            else:
                r["slots"].append(self._slot(v, key, fluid=True))
        for key in ITEM_OUTPUT_KEYS:
            if key in j:
                fluid = r["type"] == "tfc:alloy" or (r["type"] in ("tfc:blast_furnace",) and key == "result")
                r["outputs"] += self._out(j[key], fluid=fluid)
        for key in FLUID_OUTPUT_KEYS:
            if key in j:
                r["outputs"] += self._out(j[key], fluid=True)
        if not r["outputs"] and "modifiers" in json.dumps([j.get(k) for k in ITEM_OUTPUT_KEYS]):
            r["params"]["output"] = "modifies the input item"

    def _parse_gt(self, j, r):
        for cap, entries in (j.get("inputs") or {}).items():
            fluid = cap.endswith("fluid")
            for e in entries:
                content = e.get("content", {})
                if not isinstance(content, dict):
                    r["params"][f"in:{cap}"] = content
                    continue
                consumed = e.get("chance", 1) != 0
                n = content.get("amount" if fluid else "count", 1)
                r["slots"].append(self._slot(content.get("ingredient", content), cap.split(":")[-1], fluid=fluid,
                                             consumed=consumed, n=n))
        for cap, entries in (j.get("outputs") or {}).items():
            fluid = cap.endswith("fluid")
            for e in entries:
                content = e.get("content", {})
                if not isinstance(content, dict):
                    r["params"][f"out:{cap}"] = content
                    continue
                chance = e.get("chance", e.get("maxChance", 10000)) / max(1, e.get("maxChance", 10000))
                for o in self._out(content.get("ingredient", content), fluid=fluid, chance=min(1.0, chance)):
                    o["n"] = content.get("amount" if fluid else "count", o["n"])
                    r["outputs"].append(o)
        for direction in ("tickInputs", "tickOutputs"):
            for cap, entries in (j.get(direction) or {}).items():
                for e in entries:
                    if cap == "gtceu:eu" and not isinstance(e.get("content"), dict):
                        r["params"]["eut" if direction == "tickInputs" else "eut_out"] = e.get("content")
                    else:
                        r["params"][f"{direction}:{cap}"] = e.get("content")
        if "eut_out" in r["params"]:
            r["params"]["generator"] = True
        if j.get("recipeConditions"):
            r["params"]["conditions"] = json.dumps(j["recipeConditions"])[:200]

    # ------------------------------------------------------------ reports
    def coverage(self):
        """Per recipe type: total, parsed with inputs+outputs, skipped."""
        out = defaultdict(lambda: {"total": 0, "ok": 0, "skipped": 0, "no_outputs": 0, "unconstrained_slots": 0})
        for r in self.recipes:
            c = out[r["type"]]
            c["total"] += 1
            if r["skip"]:
                c["skipped"] += 1
            elif not r["outputs"]:
                c["no_outputs"] += 1
            else:
                c["ok"] += 1
            c["unconstrained_slots"] += sum(1 for s in r["slots"] if s["set"] is None)
        return dict(out)
