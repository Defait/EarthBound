"""Reachability over the recipe graph: what can be made from the world, in how many steps, and how.

Every recipe becomes a set of requirement slots (its ingredients plus the
station it needs, per progression.json); a slot is met by any one of its
nodes. Starting from the seeds, a Dijkstra-style sweep gives each node the
fewest recipe steps needed to obtain it ("depth") and the recipe that first
produced it, so any result can be explained as a chain of recipes.

Rules "A requires B" are checked by banning B (and everything matching it)
and re-running: if A is still reachable, the explanation is the shortcut.
"""
import fnmatch
import heapq
import json
import os
from collections import Counter, defaultdict

CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "progression.json")
VOLTAGES = [("ulv", 8), ("lv", 32), ("mv", 128), ("hv", 512), ("ev", 2048), ("iv", 8192), ("luv", 32768),
            ("zpm", 131072), ("uv", 524288), ("uhv", 2097152), ("uev", 8388608), ("uiv", 33554432),
            ("uxv", 134217728), ("opv", 536870912), ("max", 2147483647)]
TIER_INDEX = {name: i for i, (name, _) in enumerate(VOLTAGES)}


class Req(frozenset):
    """A requirement slot: the nodes that satisfy it, plus a human-readable label."""

    def __new__(cls, items, label):
        obj = super().__new__(cls, items)
        obj.label = label
        return obj


def voltage_tier(eut):
    for i, (_, v) in enumerate(VOLTAGES):
        if eut <= v:
            return i
    return len(VOLTAGES) - 1


class Result:
    def __init__(self, dist, via, banned):
        self.dist = dist          # node -> depth
        self.via = via            # node -> index into Progression.recipes
        self.banned = banned


class Progression:
    def __init__(self, dump, config_path=CONFIG, seeds=None, seed_info=None):
        self.d = dump
        with open(config_path, encoding="utf-8") as f:
            self.cfg = json.load(f)
        # In-world actions (building a firepit, lighting a pit kiln, ...) become pseudo-recipes;
        # their outputs may be pseudo nodes such as "i:world:pit_kiln" that stations can require.
        self.actions = list(self.cfg.get("actions", []))
        self.heat_nodes, self.kiln = self._build_heat()
        self.pseudo = {o if o.startswith(("i:", "f:")) else "i:" + o for a in self.actions for o in a["outputs"]
                       if (o.split(":", 1)[1] if o.startswith(("i:", "f:")) else o).startswith("world:")}
        self._kind_nodes = {"i": sorted({"i:" + i for i in dump.items} | {p for p in self.pseudo if p[0] == "i"}),
                            "f": sorted("f:" + f for f in dump.fluids)}
        self._match_cache = {}
        self.unmapped_types = Counter()
        self.missing_machines = Counter()
        self.unknown_patterns = Counter()
        self.recipes = []   # (recipe, [frozenset, ...] requirement slots)
        for r in dump.recipes:
            if r["skip"] or not r["outputs"]:
                continue
            slots = [Req(s["set"], "/".join(s["refs"]) or "?") for s in r["slots"] if s["set"] is not None]
            self.recipes.append((r, slots + self._station(r)))
        for a in self.actions:
            outs = [n for o in a["outputs"] for n in sorted(self.match(o))]
            r = {"id": "action:" + a["id"], "type": "world action", "kind": "world action", "slots": [], "params": {},
                 "outputs": [{"node": n, "n": 1, "chance": 1.0} for n in outs], "skip": None, "note": a.get("why", "")}
            self.recipes.append((r, [self._req(q) for q in a["inputs"]]))
        self.out_index = defaultdict(list)
        for ri, (r, _) in enumerate(self.recipes):
            for o in r["outputs"]:
                self.out_index[o["node"]].append(ri)
        self.index = defaultdict(list)
        for ri, (_, slots) in enumerate(self.recipes):
            for si, s in enumerate(slots):
                for n in s:
                    self.index[n].append((ri, si))
        self.seeds = frozenset(seeds or ())
        self.seed_info = seed_info or {}
        self.base = self.closure()

    # ---------------------------------------------------------------- patterns
    def match(self, pattern, quiet=False):
        """Nodes matching 'i:glob', 'f:glob', '#i:tag', '#f:tag', '@group', or a bare item glob."""
        if pattern in self._match_cache:
            return self._match_cache[pattern]
        key = pattern
        if pattern.startswith("@"):
            out = frozenset().union(*(self.match(p) for p in self.cfg.get("groups", {}).get(pattern[1:], [])))
        elif pattern.startswith("#"):
            out = self.d.resolve(pattern)
        else:
            if not pattern.startswith(("i:", "f:")):
                pattern = "i:" + pattern
            if any(c in pattern for c in "*?["):
                out = frozenset(n for n in self._kind_nodes[pattern[0]] if fnmatch.fnmatchcase(n, pattern))
            else:
                known = pattern in self.pseudo or pattern[2:] in (self.d.items if pattern[0] == "i" else self.d.fluids)
                out = frozenset([pattern]) if known else frozenset()
        if not out and not quiet and not key.startswith("@"):
            self.unknown_patterns[key] += 1
        self._match_cache[key] = out
        return out

    def _req(self, req, label=None):
        """A requirement: a pattern, or a list of patterns meaning any one of them."""
        pats = req if isinstance(req, list) else [req]
        nodes = frozenset().union(*(self.match(p) for p in pats))
        return Req(nodes, label or (pats[0] if len(pats) == 1 else "any of " + ", ".join(pats[:4]) + ("…" if len(pats) > 4 else "")))

    # ---------------------------------------------------------------- stations
    def _station(self, r):
        t = r["type"]
        if t.startswith("gtceu:"):
            return self._gt(r)
        spec = self.cfg["stations"].get(t)
        heat = self._heat_slot(r)
        if spec is None and heat is None:
            self.unmapped_types[t] += 1
            return []
        return (self._spec_slots(spec, r, t) if spec is not None else []) + ([heat] if heat is not None else [])

    # ---------------------------------------------------------------- heat (TFC)
    def _build_heat(self):
        """Pseudo-actions 'device + fuel -> world:heat/<device>/<temp>' from TFC fuel data in the server's jars."""
        hc = self.cfg.get("heat")
        if not hc:
            return [], None
        fuels = read_tfc_fuels(self.d)
        nodes = []
        for dev in hc.get("devices", []):
            allowed = self.d.resolve(dev["fuel"])
            by_temp = defaultdict(set)
            for ing, temp in fuels:
                usable = ing & allowed
                if usable:
                    by_temp[temp] |= usable
            for temp, items in sorted(by_temp.items()):
                node = f"world:heat/{dev['id']}/{int(temp)}"
                self.actions.append({"id": f"heat {dev['id']} {int(temp)}C", "inputs": [[dev["node"]], sorted(items)],
                                     "outputs": [node], "why": f"{dev['id']} burning fuel that reaches {int(temp)} °C"})
                nodes.append((dev, temp, "i:" + node))
            if dev.get("bellows") and by_temp:
                node = f"world:heat/{dev['id']}/bellows"
                self.actions.append({"id": f"heat {dev['id']} with bellows",
                                     "inputs": [[dev["node"]], sorted(allowed), [dev["bellows"]]], "outputs": [node],
                                     "why": f"{dev['id']} with a bellows (boost not modeled: treated as any temperature)"})
                nodes.append((dev, float("inf"), "i:" + node))
        kiln = hc.get("pit_kiln")
        if kiln:
            kiln = dict(kiln, max=read_pit_kiln_temperature())
        return nodes, kiln

    def _heat_slot(self, r):
        temp = r["params"].get("temperature")
        heat_types = {t for dev, _, _ in self.heat_nodes for t in dev.get("types", [])}
        if r["type"] not in heat_types or not isinstance(temp, (int, float)):
            return None
        opts = {node for dev, t, node in self.heat_nodes if r["type"] in dev.get("types", []) and t >= temp}
        if self.kiln and r["type"] == "tfc:heating" and temp <= self.kiln["max"]:
            pottery = self.d.resolve(self.kiln["only"])
            if any(s["set"] and s["set"] & pottery for s in r["slots"]):
                opts.add("i:" + self.kiln["node"])
        return Req(opts, f"heat source reaching {temp:g} °C")

    def _spec_slots(self, spec, r, t):
        if isinstance(spec, list):
            return [self._req(q) for q in spec]
        if "large_grid" in spec:
            grid = r["params"].get("grid", "")
            w, _, h = grid.partition("x")
            big = grid and (int(w or 0) > 2 or int(h or 0) > 2) or len(r["slots"]) > 4
            return [self._req(q) for q in spec["large_grid"]] if big else []
        if spec.get("steps"):
            out = []
            for step in filter(None, r["params"].get("steps", "").split(",")):
                sub = self.cfg["stations"].get(step)
                if sub is not None and step != t:
                    out += self._spec_slots(sub, r, step)
            return out
        if "param" in spec:
            tiers_spec = self.cfg["stations"][spec["same_as"]] if "same_as" in spec else spec
            tiers = tiers_spec["tiers"]
            value = r["params"].get(spec["param"], spec.get("default"))
            extra = [self._req(q) for q in spec.get("also", [])]
            if value is None:
                return extra
            numeric = all(k.lstrip("-").isdigit() for k in tiers)
            if numeric:
                ok = [k for k in tiers if int(k) >= int(value)]
            else:
                order = list(tiers)
                ok = order[order.index(str(value)):] if str(value) in order else order
            if any(not tiers[k] for k in ok):   # a qualifying tier needs nothing (e.g. heat_requirement "none")
                return extra
            reqs = [p for k in ok for p in tiers[k]]
            if not reqs:
                return extra
            return [self._req(reqs, f"{spec['param']} {value}+ station: " + ", ".join(reqs[:3]) + ("…" if len(reqs) > 3 else ""))] + extra
        return []

    def _gt(self, r):
        g = self.cfg.get("gregtech", {})
        path = r["type"].split(":", 1)[1]
        eut = r["params"].get("eut")
        if r["params"].get("generator"):
            eut = None
        need = voltage_tier(abs(eut)) if isinstance(eut, (int, float)) else 0
        names = [r["type"]] + g.get("machine_aliases", {}).get(r["type"], [])
        ok = set()
        for name in names:
            p = name.split(":", 1)[1]
            for tier, i in TIER_INDEX.items():
                if i >= need:
                    ok |= self.match(f"i:gtceu:{tier}_{p}", quiet=True)
            steam = g.get("steam_max_eut", {})
            for kind, max_eut in steam.items():
                if eut is None or abs(eut) <= max_eut:
                    ok |= self.match(f"i:gtceu:{kind}_steam_{p}", quiet=True)
            ok |= self.match(f"i:gtceu:{p}", quiet=True)
        slots = []
        tier_name = VOLTAGES[need][0].upper()
        if ok:
            slots.append(Req(ok, f"GregTech machine for {r['type']} ({tier_name} or better)"))
        else:
            self.missing_machines[r["type"]] += 1
        temp = r["params"].get("ebf_temp")
        if temp:
            coils = [f"i:gtceu:{c}_coil_block" for c, t in g.get("coils", {}).items() if t >= temp]
            slots.append(Req(frozenset().union(*(self.match(c) for c in coils)) if coils else frozenset(),
                             f"coil rated {temp} K or more"))
        return slots

    # ---------------------------------------------------------------- reachability
    def closure(self, banned=frozenset()):
        dist, via = {}, {}
        remaining = [len(slots) for _, slots in self.recipes]
        depth = [0] * len(self.recipes)
        done = [set() for _ in self.recipes]
        heap = [(0, n, -1) for n in self.seeds if n not in banned]
        for ri, (_, slots) in enumerate(self.recipes):
            if not slots:
                for o in self.recipes[ri][0]["outputs"]:
                    heap.append((1, o["node"], ri))
        heapq.heapify(heap)
        while heap:
            dpt, node, ri_from = heapq.heappop(heap)
            if node in dist or node in banned:
                continue
            dist[node] = dpt
            if ri_from >= 0:
                via[node] = ri_from
            for ri, si in self.index.get(node, ()):
                if si in done[ri]:
                    continue
                done[ri].add(si)
                depth[ri] = max(depth[ri], dpt)
                remaining[ri] -= 1
                if remaining[ri] == 0:
                    for o in self.recipes[ri][0]["outputs"]:
                        if o["node"] not in dist:
                            heapq.heappush(heap, (depth[ri] + 1, o["node"], ri))
        return Result(dist, via, banned)

    def explain(self, res, node, limit=14, _seen=None):
        """Nested derivation: how `node` was first obtained."""
        _seen = set() if _seen is None else _seen
        if node not in res.dist:
            return {"node": node, "reachable": False}
        out = {"node": node, "depth": res.dist[node]}
        ri = res.via.get(node)
        if ri is None:
            out["source"] = self.seed_info.get(node, "starting resource")
            return out
        r, slots = self.recipes[ri]
        out["recipe"] = r["id"]
        out["type"] = r["type"]
        if node in _seen or limit <= 0:
            out["truncated"] = True
            return out
        _seen.add(node)
        inputs = []
        for s in slots:
            best = min((n for n in s if n in res.dist), key=lambda n: (res.dist[n], n), default=None)
            if best is not None:
                inputs.append(self.explain(res, best, limit - 1, _seen))
        out["inputs"] = inputs
        return out

    # ---------------------------------------------------------------- reports
    def why_not(self, node, res=None, limit=15):
        """For each recipe producing `node`: which requirement slots have nothing reachable."""
        res = res or self.base
        out = []
        for ri in self.out_index.get(node, ()):
            r, slots = self.recipes[ri]
            missing = [getattr(s, "label", "?") for s in slots if not any(n in res.dist for n in s)]
            out.append({"recipe": r["id"], "type": r["type"], "missing": missing})
        out.sort(key=lambda x: (len(x["missing"]), x["recipe"]))
        return out[:limit]

    def check_rules(self):
        results = []
        for rule in self.cfg.get("rules", []):
            targets = self.match(rule["item"])
            banned = frozenset().union(*(self.match(p) for p in rule["requires"]))
            entry = {"rule": rule, "targets": len(targets), "banned": len(banned)}
            if not targets or not banned:
                entry["status"] = "invalid"
                entry["detail"] = "item pattern matches nothing" if not targets else "requires pattern matches nothing"
                results.append(entry)
                continue
            base_hit = sorted(n for n in targets if n in self.base.dist)
            if not base_hit:
                entry["status"] = "unreachable"
                entry["detail"] = "not reachable at all from the current seeds"
                results.append(entry)
                continue
            res = self.closure(banned)
            hits = sorted((n for n in targets if n in res.dist), key=lambda n: res.dist[n])
            if hits:
                entry["status"] = "violated"
                entry["detail"] = f"{hits[0]} is reachable without any of the required items"
                entry["path"] = self.explain(res, hits[0])
            else:
                entry["status"] = "ok"
            results.append(entry)
        return results

    def milestones(self):
        out = []
        for m in self.cfg.get("milestones", []):
            nodes = sorted(self.match(m), key=lambda n: self.base.dist.get(n, 1e9))
            n = nodes[0] if nodes else None
            out.append({"milestone": m, "node": n, "depth": self.base.dist.get(n) if n else None})
        return out

    def summary(self):
        reach = self.base.dist
        return {
            "seeds": len(self.seeds), "recipes": len(self.recipes), "reachable": len(reach),
            "items_total": len(self.d.items), "unmapped_types": dict(self.unmapped_types),
            "missing_machines": dict(self.missing_machines), "unknown_patterns": dict(self.unknown_patterns),
            "max_depth": max(reach.values()) if reach else 0,
        }


# -------------------------------------------------------------------- TFC data read from the server's jars
def read_tfc_fuels(dump):
    """[(node set, temperature)] from data/*/tfc/fuel/*.json in the test server's mod jars."""
    import glob
    import zipfile
    tools = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = []
    for jar in glob.glob(os.path.join(tools, ".server", "mods", "*.jar")):
        try:
            z = zipfile.ZipFile(jar)
        except zipfile.BadZipFile:
            continue
        for n in z.namelist():
            if "/tfc/fuel/" in n and n.startswith("data/") and n.endswith(".json"):
                j = json.loads(z.read(n))
                _, nodes = dump._ing(j.get("ingredient"))
                if nodes and j.get("temperature"):
                    out.append((nodes, float(j["temperature"])))
    return out


def read_pit_kiln_temperature(default=1400.0):
    import re
    tools = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        text = open(os.path.join(tools, ".server", "config", "tfc-server.toml"), encoding="utf-8").read()
        return float(re.search(r"pitKilnTemperature\s*=\s*([\d.]+)", text).group(1))
    except (OSError, AttributeError):
        return default


# -------------------------------------------------------------------- seeds from a world
def world_seeds(dump, world_dir, cfg):
    """Starting nodes: loot-table drops of blocks present in a scanned world, plus its fluids."""
    import sys
    tools = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if tools not in sys.path:
        sys.path.insert(0, tools)
    from worldview.index import World, cache_dir_for

    region_dir = os.path.join(world_dir, "region")
    w = World(region_dir, cache_dir_for(world_dir, region_dir))
    w.scan()
    if w.error:
        raise SystemExit(w.error)
    present = {n for n, t in zip(w.names, w.totals) if t > 0}
    loot_path = os.path.join(dump.path, "loot_blocks.json")
    loot = json.load(open(loot_path, encoding="utf-8")) if os.path.exists(loot_path) else {}
    exclude = set(cfg.get("seeds", {}).get("exclude", []))
    seeds, info = set(), {}

    def drops(table):
        found = []
        def walk(o):
            if isinstance(o, dict):
                t = o.get("type")
                if t == "minecraft:item" and isinstance(o.get("name"), str):
                    found.append("i:" + o["name"])
                elif t == "minecraft:tag" and isinstance(o.get("name"), str):
                    found.extend(dump.resolve("#i:" + o["name"]))
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(table)
        return found

    for block in sorted(present):
        if block in exclude:
            continue
        ns, path = block.split(":", 1)
        if path.startswith("fluid/") or block in ("minecraft:water", "minecraft:lava"):
            fid = f"{ns}:{path.split('/', 1)[1]}" if path.startswith("fluid/") else block
            if fid in dump.fluids:
                seeds.add("f:" + fid)
                info.setdefault("f:" + fid, f"fluid found in the world ({block})")
            continue
        for n in drops(loot.get(f"{ns}:blocks/{path}", {})):
            if n[2:] in dump.items:
                seeds.add(n)
                info.setdefault(n, f"dropped by {block}, found in the world")
    return seeds, info, len(present)
