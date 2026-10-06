"""Recipe explorer: look up how anything is made or used, check progression rules, compare dumps.

Usage (from the repo root):
    tools/.venv/Scripts/python tools/recipes/serve.py [--dump NAME] [--world NAME|PATH] [--port 8766]

Reads the newest dump from tools/.data/dumps (make one with tools/recipes/dump.py).
Progression seeds come from a scanned world: by default the most recently
played world in the Prism instance; --world picks another (a name in the
instance's saves, or a path such as tools/.server/world-pregen).
"""
import argparse
import glob
import json
import os
import sys
import threading
import webbrowser
from collections import Counter, defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, HERE)

from assets import GameAssets  # noqa: E402
from mclib.paths import DEFAULT_INSTANCE, PRISM, utf8_console  # noqa: E402
from model import DUMPS, Dump, latest_dump, list_dumps  # noqa: E402
from progression import Progression, world_seeds  # noqa: E402

UNIFY_PREFIXES = ("c:ingots/", "c:nuggets/", "c:dusts/", "c:plates/", "c:gems/", "c:storage_blocks/", "c:raw_materials/",
                  "c:rods/", "c:gears/", "c:wires/", "c:foils/", "c:sheets/", "c:double_sheets/")


def resolve_world(arg):
    saves = os.path.join(DEFAULT_INSTANCE, "saves")
    if arg and os.path.isdir(arg):
        return os.path.abspath(arg)
    if arg:
        return os.path.join(saves, arg)
    worlds = [p for p in glob.glob(os.path.join(saves, "*")) if os.path.exists(os.path.join(p, "level.dat"))]
    return max(worlds, key=lambda p: os.path.getmtime(os.path.join(p, "level.dat"))) if worlds else None


class App:
    def __init__(self, dump_name, world, use_world):
        self.state = "loading"
        self.error = None
        self.dump_name, self.world, self.use_world = dump_name, world, use_world
        self._other = {}
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        try:
            path = os.path.join(DUMPS, self.dump_name) if self.dump_name else latest_dump()
            self.state = "reading dump"
            self.d = Dump(path)
            self.state = "loading names and icons"
            version = self.d.meta.get("pack", {}).get("minecraft", "1.21.1")
            client = os.path.join(PRISM, "libraries", "com", "mojang", "minecraft", version, f"minecraft-{version}-client.jar")
            jars = ([client] if os.path.exists(client) else []) + sorted(glob.glob(os.path.join(DEFAULT_INSTANCE, "mods", "*.jar")))
            self.assets = GameAssets(jars)
            self.state = "computing progression"
            cfg = json.load(open(os.path.join(HERE, "progression.json"), encoding="utf-8"))
            seeds, info, nblocks = set(), {}, 0
            if self.use_world and self.world and os.path.isdir(self.world):
                seeds, info, nblocks = world_seeds(self.d, self.world, cfg)
            for p in cfg.get("seeds", {}).get("extra", []):
                seeds.add(p if p.startswith(("i:", "f:")) else "i:" + p)
            self.world_blocks = nblocks
            self.p = Progression(self.d, seeds=seeds, seed_info=info)
            self.rules = self.p.check_rules()
            self.ingredient_slots = {r["id"]: sum(1 for s in r["slots"] if s["set"] is not None) for r, _ in self.p.recipes}
            self.recipe_index = {r["id"]: ri for ri, (r, _) in enumerate(self.p.recipes)}
            self.search_index = sorted(
                [(n, self.assets.name(n)) for n in self.d.nodes()] +
                [("#i:" + t, "#" + t) for t in self.d.item_tags] + [("#f:" + t, "#" + t) for t in self.d.fluid_tags])
            self.state = "ready"
        except Exception as e:
            import traceback
            self.error = "".join(traceback.format_exception(e))
            self.state = "error"

    # ---------------------------------------------------------------- views
    def label(self, node):
        if node.startswith("#"):
            return {"id": node, "name": "#" + node[3:], "tag": True, "size": len(self.d.resolve(node))}
        return {"id": node, "name": self.assets.name(node) if not node[2:].startswith("world:") else node[8:],
                "depth": self.p.base.dist.get(node)}

    def recipe_summary(self, r):
        ri = self.recipe_index.get(r["id"])
        stations = []
        if ri is not None:
            slots = self.p.recipes[ri][1]
            for s in slots[self.ingredient_slots.get(r["id"], 0):]:
                stations.append({"label": getattr(s, "label", "?"), "met": any(n in self.p.base.dist for n in s)})
        return {
            "id": r["id"], "type": r["type"], "kind": r["kind"], "skip": r["skip"], "params": r["params"],
            "inputs": [{"refs": [self.label(x) if x.startswith(("i:", "f:", "#")) and " " not in x else {"id": x, "name": x}
                                 for x in s["refs"]],
                        "n": s["n"], "consumed": s["consumed"], "role": s["role"],
                        "met": s["set"] is None or any(n in self.p.base.dist for n in s["set"])} for s in r["slots"]],
            "outputs": [dict(self.label(o["node"]), n=o["n"], chance=o["chance"]) for o in r["outputs"]],
            "stations": stations, "reachable": ri is not None and all(o["node"] in self.p.base.dist for o in r["outputs"][:1]),
        }

    def node_view(self, node):
        d, p = self.d, self.p
        out = self.label(node)
        out["kind"] = "fluid" if node.startswith("f:") else "item"
        out["tags"] = sorted(d.node_tags.get(node, []))
        out["producers"] = [self.recipe_summary(d.by_id[i]) for i in d.producers.get(node, [])][:300]
        out["producers_total"] = len(d.producers.get(node, []))
        out["consumers"] = [self.recipe_summary(d.by_id[i]) for i in d.consumers.get(node, [])][:150]
        out["consumers_total"] = len(d.consumers.get(node, []))
        if node in p.base.dist:
            out["explain"] = self.annotate(p.explain(p.base, node))
        else:
            out["why_not"] = p.why_not(node)
            out["action_producers"] = [r["id"] for r, _ in p.recipes if r["type"] == "world action" and any(o["node"] == node for o in r["outputs"])]
        material = {t for t in out["tags"] if t.startswith("#i:") and t[3:].startswith(UNIFY_PREFIXES)}
        out["duplicates"] = [dict(self.label(m), via=t) for t in sorted(material) for m in sorted(d.resolve(t)) if m != node]
        out["seed"] = p.seed_info.get(node)
        return out

    def annotate(self, tree):
        tree["name"] = self.label(tree["node"])["name"]
        for c in tree.get("inputs", []):
            self.annotate(c)
        return tree

    def types_view(self):
        cov = self.d.coverage()
        rows = []
        for t, c in sorted(cov.items(), key=lambda kv: -kv[1]["total"]):
            rows.append(dict(c, type=t, unmapped=self.p.unmapped_types.get(t, 0), missing_machine=self.p.missing_machines.get(t, 0)))
        return {"rows": rows, "unknown_forms": dict(self.d.unknown_forms)}

    def dupes_view(self):
        rows = []
        for t, members in sorted(self.d.item_tags.items()):
            if t.startswith(UNIFY_PREFIXES) and len({m.split(":")[1] for m in members}) > 1:
                rows.append({"tag": "#i:" + t, "items": [self.label(m) for m in sorted(members)]})
        return {"rows": rows}

    def progression_view(self):
        rules = []
        for r in self.rules:
            e = dict(r)
            if "path" in e:
                e["path"] = self.annotate(json.loads(json.dumps(e["path"])))
            rules.append(e)
        ms = [dict(m, name=self.label(m["node"])["name"] if m["node"] else m["milestone"]) for m in self.p.milestones()]
        return {"summary": self.p.summary(), "rules": rules, "milestones": ms, "world": self.world if self.use_world else None,
                "world_blocks": self.world_blocks, "seeds": sorted(self.p.seeds)[:2000]}

    def diff_view(self, a, b):
        da = self._dump(a)
        db = self._dump(b)
        ha = {r["id"]: (r["type"], r["hash"]) for r in da.recipes}
        hb = {r["id"]: (r["type"], r["hash"]) for r in db.recipes}
        by_type = defaultdict(lambda: {"added": [], "removed": [], "changed": []})
        for rid in hb.keys() - ha.keys():
            by_type[hb[rid][0]]["added"].append(rid)
        for rid in ha.keys() - hb.keys():
            by_type[ha[rid][0]]["removed"].append(rid)
        for rid in ha.keys() & hb.keys():
            if ha[rid][1] != hb[rid][1]:
                by_type[hb[rid][0]]["changed"].append(rid)
        rows = [dict(type=t, **{k: sorted(v) for k, v in c.items()}) for t, c in sorted(by_type.items())]
        return {"a": a, "b": b, "rows": rows,
                "totals": {k: sum(len(r[k]) for r in rows) for k in ("added", "removed", "changed")}}

    def _dump(self, name):
        if name == self.d.name:
            return self.d
        if name not in self._other:
            self._other[name] = Dump(os.path.join(DUMPS, name))
        return self._other[name]

    def search(self, q):
        q = q.strip().lower()
        if not q:
            return []
        hits = []
        for node, name in self.search_index:
            key = node.lower()
            nm = name.lower()
            if q in key or q in nm:
                score = (0 if nm == q or key.endswith(":" + q) else 1 if nm.startswith(q) else 2, len(key))
                hits.append((score, node, name))
        hits.sort()
        out = []
        for _, node, name in hits[:60]:
            e = self.label(node)
            e["name"] = name if node.startswith("#") else e["name"]
            out.append(e)
        return out


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, code, body, ctype, cache=False):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "max-age=86400" if cache else "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj).encode(), "application/json")

        def do_GET(self):
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                if url.path in ("/", "/index.html"):
                    with open(os.path.join(HERE, "explorer.html"), "rb") as f:
                        return self._send(200, f.read(), "text/html; charset=utf-8")
                if url.path == "/api/status":
                    return self._json({"state": app.state, "error": app.error})
                if app.state != "ready":
                    return self._json({"error": app.state}, 503)
                if url.path == "/api/meta":
                    return self._json({"dump": app.d.name, "dumps": list_dumps(), "meta": app.d.meta,
                                       "recipes": len(app.d.recipes), "items": len(app.d.items), "fluids": len(app.d.fluids),
                                       "summary": app.p.summary(), "world": app.world if app.use_world else None,
                                       "rules": Counter(r["status"] for r in app.rules)})
                if url.path == "/api/search":
                    return self._json(app.search(q.get("q", "")))
                if url.path == "/api/node":
                    node = q["id"]
                    if node.startswith("#"):
                        return self._json({"id": node, "tag": True, "name": "#" + node[3:],
                                           "members": [app.label(m) for m in sorted(app.d.resolve(node))]})
                    return self._json(app.node_view(node))
                if url.path == "/api/recipe":
                    r = app.d.by_id.get(q["id"])
                    if not r:
                        return self._json({"error": "unknown recipe"}, 404)
                    return self._json(dict(app.recipe_summary(r), raw=app.d.raw_json(r["id"])))
                if url.path == "/api/types":
                    return self._json(app.types_view())
                if url.path == "/api/type":
                    rs = [r for r in app.d.recipes if r["type"] == q["t"]]
                    page = int(q.get("page", 0))
                    return self._json({"total": len(rs), "page": page,
                                       "recipes": [app.recipe_summary(r) for r in rs[page * 50:(page + 1) * 50]]})
                if url.path == "/api/dupes":
                    return self._json(app.dupes_view())
                if url.path == "/api/progression":
                    return self._json(app.progression_view())
                if url.path == "/api/diff":
                    return self._json(app.diff_view(q["a"], q["b"]))
                if url.path == "/api/icon":
                    png = app.assets.icon(q["id"])
                    if png is None:
                        return self._send(404, b"", "image/png")
                    return self._send(200, png, "image/png", cache=True)
                return self._json({"error": "not found"}, 404)
            except (KeyError, ValueError) as e:
                return self._json({"error": f"bad request: {e}"}, 400)
            except Exception as e:
                return self._json({"error": repr(e)}, 500)

    return Handler


def main():
    utf8_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dump", help="dump folder name in tools/.data/dumps (default: newest)")
    ap.add_argument("--world", help="world for progression seeds: a save name or a world folder path")
    ap.add_argument("--no-world", action="store_true", help="don't seed from a world; use progression.json's extra seeds only")
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    world = resolve_world(args.world)
    app = App(args.dump, world, not args.no_world)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(app))
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Recipe explorer: {url}  (seeds from {world if not args.no_world else 'config only'}; Ctrl+C to stop)", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
