"""Has anything changed what the overworld generates? Fingerprints it on a fresh world and compares with a baseline.

Usage (from the repo root):
    tools/.venv/Scripts/python tools/worldgen_check.py [--golden] [--static] [--update | --accept REASON]
                                                       [--force-terrain REASON] [--no-sync] [--keep-world]
                                                       [--baseline PATH] [--seed worldgen] [--xmx 6G]

The pack wants the overworld's generation frozen: players are spread over a huge map, so new chunks are always being
generated, and any change to generation shows up in them. Mods can then be added or updated without a world wipe, as long
as they don't touch what TFC and TFC: Real World generate. One run boots the test server on a fresh world (fixed seed, at
the pack's 20 m per block scale; any other scale fails), fingerprints generation and compares it with the committed
tools/worldgen_baseline.json. Findings come in three groups:
  continuity-breaking  existing worlds would show seams: terrain, biomes, rock, carvers, veins, sea level, map and scale,
                       or code that can change them (TFC and TFC: Real World are the terrain code: any change is one)
  new-chunks-only      only chunks generated from now on differ: new features, structures, decoration, fauna (strip them, or
                       accept one on purpose with --accept; each finding says how to strip it, a data override under kubejs/data)
  info                 not a generation change (jar versions, inert modifiers, latent tag members)
Exit code 1 on any continuity-breaking or new-chunks-only finding; info alone passes.

Tiers:
  0 static     per jar (and the jars nested in it) a hash of its worldgen data entries (structure templates included), and its
               mixins into worldgen code (hash of each class), plus the pack's own data overrides; for the pack's own structure
               mod (pack_world) also a hash of its classes. Needs no server (--static runs just this, in
               seconds; its data findings are then classified by what the data is, as nothing says if it takes effect).
  1 effective  what the running server uses: the generator and its settings, dimension type, sea level, possible biomes
               (exactly the 125 tfc ones), per biome the ordered feature ids per decoration slot, carvers and mob spawns
               (grouped by signature; only non-TFC ids are listed, the rest is hashed per slot), every biome and structure
               modifier and how many TFC biomes it reaches, structures that can start in a TFC biome and a signature of each
               (its JSON, structure set, pools, processor lists and template files), the real-world sites' start chunks
               (pack_world:geographic), biome tags holding TFC biomes, content hashes of the worldgen registries, GregTech ore veins that can still generate, the config
               values that gate worldgen, and the world's TFC: Real World server.toml.
  2 points     ~2,000 fixed points over land and ocean (clusters around rocksample.py's 43 places and around random land and
               sea anchors) and no chunk generation: TFC's own base height, biome, surface rock, rock at three depths and
               climate. Compared exactly.
  3 golden     (--golden) ~8 small areas (81 chunks each: swamp, coast, volcanic, mountain, desert, tundra, karst, plains)
               generated with Chunky (added to the test server for the run only): per chunk the biomes and tfc:chunk_data
               exactly, an underground census (below the lowest surface - 6) grouped per host rock (all its variants and ores),
               ore mineral, air and fluid with tolerances well above what same-seed runs differ by, and checks that no block,
               structure or entity outside TFC's own appears (the baseline records what was accepted). Chunks that a structure
               reaches in either run (its references, which include its terrain adaptation's margin) are left out of the census,
               since a structure's blocks and beard aren't terrain drift; their biomes and tfc:chunk_data are still compared. This is the only tier
               that sees code-level changes. Surface decoration is never compared: trees, grass and cave decoration differ
               run to run. A golden run keeps its census in tools/.data/worldgen/last-golden.json.

Policy: continuity-breaking changes are always refused; new-chunks-only additions (a new plant, a small structure, fauna)
can be accepted case by case, or stripped. So the baseline only moves through these:
  --update                     first baseline, or a refresh that differs only in info (e.g. jar versions). Refuses anything else.
  --accept "<reason>"          folds the current new-chunks-only differences into the baseline, recording what, which mod,
                               the date and the reason under "accepted". Refuses while anything continuity-breaking remains.
  --update --force-terrain "<reason>"  folds everything in, continuity-breaking too, recorded as terrain. Loud, for the rare
                               change the author has confirmed only touches new terrain far from players.
Without --golden, --update and --accept keep the baseline's golden section. Commit the baseline with a message saying why.
Reports go to tools/.data/reports/worldgen-<timestamp>.json. Uses the test server (fixed port): not while another tool does.
"""
import argparse
import hashlib
import json
import os
import random
import re
import shutil
import sys
import time
import tomllib

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
from mclib import jarscan  # noqa: E402
from mclib.paths import DATA_DIR, REPO, utf8_console  # noqa: E402
from mclib.server import TestServer  # noqa: E402
from pregen import FINISHED_RE, chunky_jar  # noqa: E402
from rocksample import DEFAULT_PLACES  # noqa: E402

WORLD = "world-worldgen"
BASELINE = os.path.join(TOOLS, "worldgen_baseline.json")
# The pack's 20 m per block map radius (kubejs/startup_scripts/world_scale.js); anything else fails the check.
H, V = 862198, 419647
SCHEMA = 1
POINT_SEED = 20261007
SLOTS = ["raw_generation", "lakes", "local_modifications", "underground_structures", "surface_structures", "strongholds",
         "underground_ores", "underground_decoration", "fluid_springs", "vegetal_decoration", "top_layer_modification"]
# Slots where TFC itself generates terrain-shaping content and veins (not decoration): a change there is a seam.
TERRAIN_SLOTS = {"raw_generation", "lakes", "local_modifications", "underground_ores"}
TERRAIN_MODS = jarscan.TERRAIN_MODS
OPTION_FILES = ["lithium.properties", "modernfix-mixins.properties"]

# Areas for --golden: block coordinates found by scanning for spots where several biome types of the theme meet within
# an 81-chunk square (the baseline's tier3 "areas" list the biomes each one holds).
GOLDEN = [
    ("swamp", -418125, -164110, "Florida: salt marsh behind the shore (c:is_swamp, so the rubber tree feature applies), plains"),
    ("coast", 29662, -240894, "Italian coast: rolling hills, terraces, oceanic mountains, the sea"),
    ("volcanic", -100457, -362585, "Iceland: ancient shield volcano, its shore, ice sheet edge"),
    ("mountain", 5409, -268451, "Alps: old mountains, mountain lakes, a plateau"),
    ("desert", 190654, -154629, "Arabian coast: dunes, salt flats, dune sea, a coral reef"),
    ("tundra", -494088, -354145, "Alaska: drumlins, lakes, ice sheet edge"),
    ("karst", 491267, -190455, "Guangxi: plains with tower karst highlands and lakes"),
    ("plains", -474734, -251538, "Great Plains: hills with canyon and badland edges"),
]
GOLDEN_RADIUS = 64              # blocks: a square of 9 x 9 chunks
# The underground census (below the area's lowest surface - 6) is compared in groups, because cave decoration, hot springs and
# fluid springs differ from run to run: they swap blocks of one host rock for hardened, mossy or spiked variants of it. All
# variants of a host rock and the ores and deposits in it count as that rock; ores also count per mineral; then air and
# fluids. Between same-seed runs the groups moved by at most 0.02% of the cells between host rocks, 0.1% in air, 60 cells per
# ore mineral (hot spring gems) and a few tens in fluids; these limits are several times that.
CENSUS_HOST = 0.0004            # share of the area's cells that may move between host rocks
CENSUS_REL, CENSUS_FLOOR = 0.03, 300   # per ore mineral, air and fluid: relative change allowed, plus this many cells
ALLOWED_FOREIGN_BLOCKS = {"gtceu:rubber_log", "gtceu:rubber_leaves"}   # the accepted baseline: GregTech's rubber trees
# The audit of 83,000 chunks saw eight vanilla blocks; the golden areas add TFC's own glacier ice and snow and its reef coral.
ALLOWED_MINECRAFT_BLOCKS = {"minecraft:air", "minecraft:cave_air", "minecraft:bedrock", "minecraft:water", "minecraft:lava",
                            "minecraft:cobweb", "minecraft:hanging_roots", "minecraft:obsidian",
                            "minecraft:ice", "minecraft:packed_ice", "minecraft:blue_ice", "minecraft:snow_block",
                            "minecraft:brain_coral_block", "minecraft:bubble_coral_block", "minecraft:fire_coral_block",
                            "minecraft:horn_coral_block", "minecraft:tube_coral_block"}
CENSUS_DEPTH = 6                # blocks below the area's lowest surface column
VOLATILE_CHUNK_DATA = {"lastRandomTick", "nextSnowPosition"}


# ------------------------------------------------------------------ small helpers
def h(obj, n=8):
    """Short hash of any JSON-able value (keys sorted, whole floats as ints, so KubeJS's 1.0 and 1 agree)."""
    return hashlib.sha1(json.dumps(ints(obj), sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:n]


def ints(v):
    """KubeJS writes whole numbers as 10527.0; turn them back into ints, recursively."""
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, list):
        return [ints(x) for x in v]
    if isinstance(v, dict):
        return {k: ints(x) for k, x in v.items()}
    return v


def flatten(d, prefix=""):
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(flatten(v, f"{prefix}{k}."))
        else:
            out[f"{prefix}{k}"] = v
    return out


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return ints(json.load(f))


def ns_of(ident):
    return ident.split(":", 1)[0] if ":" in ident else "minecraft"


def plural(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


def short(items, n=6, sep=", "):
    items = list(items)
    return sep.join(items[:n]) + (f" and {len(items) - n} more" if len(items) > n else "")


def read_yaml_section(path, section):
    """Flatten one top-level section of a simple YAML file (nested keys and scalars only, like GregTech's gtceu.yaml)."""
    out, stack, inside = {}, [], False
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            indent = len(line) - len(line.lstrip())
            m = re.match(r"^\s*([\w.\-]+):\s*(.*?)\s*$", line)
            if not m:
                continue
            if indent == 0:
                inside = m.group(1) == section
                stack = []
                continue
            if not inside:
                continue
            while stack and stack[-1][0] >= indent:
                stack.pop()
            key, val = m.groups()
            if val == "":
                stack.append((indent, key))
                continue
            if val in ("true", "false"):
                val = val == "true"
            else:
                try:
                    val = int(val)
                except ValueError:
                    try:
                        val = float(val)
                    except ValueError:
                        val = val.strip("'\"")
            out[".".join([s[1] for s in stack] + [key])] = val
    return out


def read_config(server_dir):
    """The config values that gate worldgen, read from the server's config folder (defaults are written there on first start)."""
    out = {}
    path = os.path.join(server_dir, "config", "gtceu.yaml")
    if os.path.exists(path):
        out.update({f"gtceu.{k}": v for k, v in read_yaml_section(path, "worldgen").items()})
    path = os.path.join(server_dir, "config", "create-common.toml")
    if os.path.exists(path):
        with open(path, "rb") as f:
            out.update({f"create.{k}": v for k, v in flatten(tomllib.load(f).get("worldgen", {})).items()})
    path = os.path.join(server_dir, "config", "almostunified", "startup.json")
    if os.path.exists(path):
        out.update({f"almostunified.{k}": v for k, v in read_json(path).items() if "world" in k})
    return out


def read_options(server_dir):
    """Hash of the non-comment lines of the config files that switch mixin rules on and off (a missing file has none)."""
    out = {}
    for name in OPTION_FILES:
        path = os.path.join(server_dir, "config", name)
        lines = []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                lines = sorted(line.strip() for line in f if line.strip() and not line.lstrip().startswith("#"))
        out[name] = h(lines, 6)
    return out


# ------------------------------------------------------------------ the job for the sampling script
def build_job():
    """Fixed sample points: offsets around each place and around random anchors, from one seeded RNG."""
    rng = random.Random(POINT_SEED)

    def offsets(n, r):
        return [[round(rng.uniform(-r, r)), round(rng.uniform(-r, r))] for _ in range(n)]

    return {
        "expectH": H, "expectV": V, "named": [[n, la, lo] for n, la, lo in DEFAULT_PLACES], "offsets": offsets(19, 2500),
        "anchors": [[round(rng.uniform(-H + 3000, H - 3000)), round(rng.uniform(-V + 3000, V - 3000))] for _ in range(600)],
        "land": 28, "sea": 12, "anchorOffsets": offsets(27, 2500), "depths": [25, 50, 100],
    }


def write_job_script(job):
    with open(os.path.join(TOOLS, "worldgen_check.js"), encoding="utf-8") as f:
        src = f.read()
    m = re.search(r"/\*JOB\*/.*?/\*END\*/", src, re.S)
    if not m:
        raise SystemExit("tools/worldgen_check.js lost its /*JOB*/ ... /*END*/ placeholder")
    out = src[:m.start()] + "/*JOB*/ " + json.dumps(job, separators=(",", ":")) + " /*END*/" + src[m.end():]
    dest = os.path.join(DATA_DIR, "worldgen", "worldgen_check.js")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(out)
    return dest


# ------------------------------------------------------------------ tier 0: jars and pack data
def tier0(srv, extra_jars):
    """Static scan of the pack's jars (not the extra ones a tool put in for a run: Chunky) and its own data overrides."""
    skip = {os.path.basename(j) for j in extra_jars}
    tracked = srv.path(".extra-mods.json")
    if os.path.exists(tracked):
        with open(tracked) as f:
            skip |= {os.path.basename(j.replace("\\", "/")) for j in json.load(f)}
    mods = jarscan.scan_jars(srv.path("mods"), skip=skip)
    data = {}
    kubejs = os.path.join(REPO, "kubejs")
    names = []
    for root, _, files in os.walk(os.path.join(kubejs, "data")):
        names += [os.path.relpath(os.path.join(root, f), kubejs).replace(os.sep, "/") for f in files]

    def read(name):
        with open(os.path.join(kubejs, name), "rb") as f:
            return f.read()

    cats, files = jarscan.scan_data(names, read, own=True)
    if cats:
        data = {"data": cats, "files": {n: v[:6] for n, v in files.items()}}
    return {"engine": {"minecraft": srv.pack["versions"]["minecraft"], "neoforge": srv.loader_version}, "mods": mods,
            "pack": data, "mixinOptions": read_options(srv.root)}


# ------------------------------------------------------------------ tier 1: effective registries
def canonical(v):
    """TFC encodes some maps (rock to ore block, soil to soil) as lists in hash-map order, which differs from run to run
    although the content doesn't; sort those lists, which are sets, so only a real change moves a hash."""
    if isinstance(v, dict):
        out = {k: canonical(x) for k, x in v.items()}
        for k in ("replace", "blocks"):
            if isinstance(out.get(k), list) and all(isinstance(x, str) for x in out[k]):
                out[k] = sorted(out[k])
        for k in ("blocks", "states", "replaces_on_fluid_contact"):
            if isinstance(out.get(k), list) and all(isinstance(x, dict) for x in out[k]):
                out[k] = sorted(out[k], key=lambda e: json.dumps(e, sort_keys=True))
        return out
    if isinstance(v, list):
        return [canonical(x) for x in v]
    return v


def registry_fp(entries):
    """One registry's content: a hash per TFC bucket, per entry for other mods, vanilla as one hash."""
    per = {i: h(canonical(j)) for i, j in entries.items()}
    out = {"n": len(per), "hash": h(sorted(per.items()), 10)}
    tfc, vanilla, entries_out = {}, {}, {}
    for i, v in per.items():
        ns = ns_of(i)
        if ns == "tfc":
            tfc.setdefault(i.split(":", 1)[1].split("/")[0] if "/" in i else "(root)", {})[i] = v
        elif ns == "minecraft":
            vanilla[i] = v
        else:
            entries_out[i] = v[:6]
    if tfc:
        out["tfc"] = {b: [len(m), h(sorted(m.items()), 6)] for b, m in sorted(tfc.items())}
    if vanilla:
        out["minecraft"] = [len(vanilla), h(sorted(vanilla.items()), 8)]
    if entries_out:
        out["entries"] = dict(sorted(entries_out.items()))
    return out


def slot_name(i):
    """Name of decoration list i. TFC's biomes carry 11 to 13 lists, so a mod's features can sit at an index past the 11 named steps."""
    return SLOTS[i] if i < len(SLOTS) else f"extra_{i}"


def feature_sig(slots):
    """Signature of a biome's feature lists: a hash per slot of the TFC ids, and the other ids spelled out."""
    foreign = {slot_name(i): [f for f in s if ns_of(f) != "tfc"] for i, s in enumerate(slots) if any(ns_of(f) != "tfc" for f in s)}
    return {"n": [len(s) for s in slots], "tfc": [h([f for f in s if ns_of(f) == "tfc"], 6) for s in slots], "foreign": foreign}


def spawn_sig(spawns):
    foreign = {c: [e for e in es if ns_of(e) != "tfc"] for c, es in spawns.items() if any(ns_of(e) != "tfc" for e in es)}
    return {"n": {c: len(es) for c, es in sorted(spawns.items())},
            "tfc": {c: h([e for e in es if ns_of(e) == "tfc"], 6) for c, es in sorted(spawns.items())}, "foreign": foreign}


def tier1(raw):
    info = raw["info"]
    biomes = raw["biomes"]
    reg = raw["registries"]
    gen = info["generator"]
    settings_id = gen.get("settings")
    noise = reg.get("minecraft:worldgen/noise_settings", {}).get(settings_id)
    fsigs, ssigs, csigs, per_biome = {}, {}, {}, {}
    for b, d in sorted(biomes.items()):
        fs, ss = feature_sig(d["features"]), spawn_sig(d["spawns"])
        carvers = [f"{k}:{c}" for k, cs in sorted(d["carvers"].items()) for c in cs]
        fid, sid, cid = h(d["features"]), h(d["spawns"]), h(carvers)
        fsigs[fid], ssigs[sid], csigs[cid] = fs, ss, carvers
        per_biome[b] = {"f": fid, "s": sid, "c": cid}
    structures = info["structures"]
    mods = {i: {"json": m["json"], "hits": len(m["hits"])} for i, m in sorted(info["modifiers"].items())}
    tags = {}
    for tag, t in sorted(info["biomeTags"].items()):
        members = [m.split(":", 1)[1] for m in t["tfc"]]
        tags[tag] = {"total": t["total"], "tfc": members}
    out = {
        "world": raw["world_config"], "scale": info["scale"], "generatorClass": info["generatorClass"], "biomeSourceClass": info["biomeSourceClass"],
        "generator": gen, "dimensionType": info["dimensionType"], "seaLevel": info["seaLevel"], "minY": info["minY"],
        "height": info["dimensionTypeHeight"], "noiseSettings": {"id": settings_id, "hash": h(noise) if noise else None},
        "possibleBiomes": info["possibleBiomes"], "biomes": per_biome,
        "featureSigs": fsigs, "carverSigs": csigs, "spawnSigs": ssigs, "modifiers": mods, "structures": structures,
        "biomeTags": tags, "registries": {name: registry_fp(entries) for name, entries in sorted(reg.items())},
        "oreVeins": info.get("oreVeins"), "config": dict(sorted({**raw["config"], **{f"runtime.{k}": v for k, v in info["config"].items()}}.items())),
    }
    return out


def walk_strings(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, list):
        for x in v:
            yield from walk_strings(x)
    elif isinstance(v, dict):
        for x in v.values():
            yield from walk_strings(x)


def structure_sigs(raw, t0):
    """Per structure that can start in a TFC biome: a signature of everything that decides what it places (its JSON, the
    structure sets naming it, the template pools it reaches, their processor lists, and the template files' hashes from tier 0),
    with a hash per part so a change says which part moved."""
    reg = raw["registries"]
    structs, sets = reg.get("minecraft:worldgen/structure", {}), reg.get("minecraft:worldgen/structure_set", {})
    pools, plists = reg.get("minecraft:worldgen/template_pool", {}), reg.get("minecraft:worldgen/processor_list", {})
    files = dict((t0.get("pack") or {}).get("files", {}))
    for rec in t0["mods"].values():
        files.update(rec.get("files", {}))
    out = {}
    for sid in sorted(raw["info"]["structures"]["hits"]):
        doc = structs.get(sid) or {}
        parts = {"structure": doc, "sets": {k: v.get("placement") for k, v in sorted(sets.items())
                                             if any(e.get("structure") == sid for e in v.get("structures", []))}}
        todo, seen, lists, templates = [doc.get("start_pool")], {}, {}, {}
        while todo:
            p = todo.pop()
            if not isinstance(p, str) or p in seen or p not in pools:
                continue
            seen[p] = pools[p]
            for x in walk_strings(pools[p]):
                if x in pools:
                    todo.append(x)
                if x in plists:
                    lists[x] = plists[x]
                ns, _, path = x.partition(":")
                f = f"data/{ns}/structure/{path}.nbt"
                if f in files:
                    templates[x] = files[f]
        parts.update(pools=seen, processors=lists, templates=templates)
        out[sid] = {"sig": h(parts), "parts": {k: h(v, 6) for k, v in parts.items()}}
    return out


def reachable(raw):
    """Registry entries the overworld can reach: placed features of TFC biomes, what they place, carvers and noise settings."""
    reg = raw["registries"]
    placed, configured = reg.get("minecraft:worldgen/placed_feature", {}), reg.get("minecraft:worldgen/configured_feature", {})
    noise_settings, dens = reg.get("minecraft:worldgen/noise_settings", {}), reg.get("minecraft:worldgen/density_function", {})
    noise = reg.get("minecraft:worldgen/noise", {})

    def strings(v):
        if isinstance(v, str):
            yield v
        elif isinstance(v, list):
            for x in v:
                yield from strings(x)
        elif isinstance(v, dict):
            for x in v.values():
                yield from strings(x)

    seen = set()
    todo = [("placed", f) for d in raw["biomes"].values() for slot in d["features"] for f in slot]
    todo += [("noise_settings", s) for s in strings(raw["info"]["generator"]) if s in noise_settings]
    todo += [("carver", c) for d in raw["biomes"].values() for cs in d["carvers"].values() for c in cs]
    while todo:
        kind, i = todo.pop()
        if (kind, i) in seen:
            continue
        seen.add((kind, i))
        if kind == "placed" and i in placed:
            todo += [("configured", s) for s in strings(placed[i]) if s in configured]
        elif kind == "configured" and i in configured:
            todo += [("placed", s) for s in strings(configured[i]) if s in placed]
        elif kind in ("noise_settings", "density"):
            doc = noise_settings.get(i) if kind == "noise_settings" else dens.get(i)
            for s in strings(doc):
                if s in dens:
                    todo.append(("density", s))
                if s in noise:
                    todo.append(("noise", s))
    return seen


# ------------------------------------------------------------------ tier 2: points
def tier2(raw):
    clusters = raw["points"]["clusters"]
    names = sorted({p[3] for c in clusters for p in c["points"]})
    index = {n: i for i, n in enumerate(names)}
    out, places = {}, {}
    for c in clusters:
        pts = []
        for p in c["points"]:
            top, biome, rocks, climate = p[2], p[3], p[4:8], p[8:]
            pts.append(f"{top}.{index[biome]}.{h(rocks, 4)}.{h(climate, 3)}")
        out[c["name"]] = {"kind": c["kind"], "at": [c["x"], c["z"]], "points": pts}
        if c["kind"] == "place":
            p = c["points"][0]
            places[c["name"]] = {"at": [p[0], p[1]], "height": p[2], "biome": p[3], "rock": p[4:8], "climate": p[8:]}
    return {"n": sum(len(c["points"]) for c in clusters), "biomeNames": names, "places": places, "clusters": out}


# ------------------------------------------------------------------ tier 3: golden chunks
def golden_boxes():
    return {name: (x >> 4, z >> 4) for name, x, z, _ in GOLDEN}


def golden_fingerprint(world_dir):
    """Read the generated areas back from the world's region files."""
    import numpy as np
    from worldview import region as R

    half = GOLDEN_RADIUS // 16
    wanted = {}
    for name, (cx, cz) in golden_boxes().items():
        for dx in range(-half, half + 1):
            for dz in range(-half, half + 1):
                wanted[(cx + dx, cz + dz)] = name
    areas = {name: {"chunks": {}, "census": {}, "cells": 0, "blocks": {}, "starts": {}, "entities": {}, "biomes": {}, "blockEntities": {}, "partial": 0,
                    "chunkCensus": {}, "touched": {}}
             for name, *_ in GOLDEN}

    def unpack(packed, n, bits_min):
        bits = max(bits_min, int(n - 1).bit_length())
        shifts = np.arange(64 // bits, dtype=np.uint64) * np.uint64(bits)
        return ((packed[:, None] >> shifts[None, :]) & np.uint64((1 << bits) - 1)).reshape(-1)

    def indices(container, count, bits_min):
        pal = container["palette"]
        if container.get("data") is None:
            return pal, np.zeros(count, dtype=np.int64)
        packed = np.asarray(container["data"], dtype=np.int64).view(np.uint64)
        return pal, unpack(packed, len(pal), bits_min)[:count].astype(np.int64)

    for rx, rz, path in R.list_regions(os.path.join(world_dir, "region")):
        for _, _, root in R.iter_chunks(path):
            pos = (root["xPos"], root["zPos"])
            name = wanted.get(pos)
            if name is None:
                continue
            area = areas[name]
            if root.get("Status") != "minecraft:full":
                area["partial"] += 1
                continue
            data = root["neoforge:attachments"]["tfc:chunk_data"]
            surface = data["surfaceHeight"]
            limit = int(surface.min()) - CENSUS_DEPTH
            biome_names, cells, chunk_census = [], 0, {}
            for sec in root["sections"]:
                pal, idx = indices(sec["block_states"], 4096, 4)
                names = [p["Name"] for p in pal]
                counts = np.bincount(idx, minlength=len(names))
                ys = sec["Y"] * 16 + (np.arange(4096) >> 8)
                under = np.bincount(idx[ys < limit], minlength=len(names))
                for i, n in enumerate(counts):
                    if n:
                        area["blocks"][names[i]] = area["blocks"].get(names[i], 0) + int(n)
                for i, n in enumerate(under):
                    if n:
                        area["census"][names[i]] = area["census"].get(names[i], 0) + int(n)
                        chunk_census[names[i]] = chunk_census.get(names[i], 0) + int(n)
                cells += int(under.sum())
                bpal, bidx = indices(sec["biomes"], 64, 1)
                biome_names += [bpal[i] for i in bidx]
            area["cells"] += cells
            for b in set(biome_names):
                area["biomes"][b] = area["biomes"].get(b, 0) + biome_names.count(b)
            clean = {k: v for k, v in sorted(data.items()) if k not in VOLATILE_CHUNK_DATA}
            clean = {k: (v.tolist() if hasattr(v, "tolist") else v) for k, v in clean.items()}
            key = f"{pos[0]},{pos[1]}"
            area["chunks"][key] = [h(biome_names, 6), h(clean, 6)]
            area["chunkCensus"][key] = dict(sorted(census_groups(chunk_census).items()), _cells=cells)
            structs = root.get("structures", {})
            reached = set((structs.get("References") or {}).keys())
            reached |= {sid for sid, st in (structs.get("starts") or {}).items() if st.get("id") != "INVALID"}
            if reached:
                area["touched"][key] = sorted(reached)
            for sid, s in (root.get("structures", {}).get("starts") or {}).items():
                if s.get("id") != "INVALID":
                    area["starts"][sid] = area["starts"].get(sid, 0) + 1
            for be in root.get("block_entities") or []:
                area["blockEntities"][be["id"]] = area["blockEntities"].get(be["id"], 0) + 1
    entities = os.path.join(world_dir, "entities")
    if os.path.isdir(entities):
        for rx, rz, path in R.list_regions(entities):
            for _, _, root in R.iter_chunks(path):
                if root.get("Position") is None:
                    continue
                name = wanted.get((int(root["Position"][0]), int(root["Position"][1])))
                if name is None:
                    continue
                for e in root.get("Entities") or []:
                    eid = e.get("id", "?")
                    areas[name]["entities"][eid] = areas[name]["entities"].get(eid, 0) + 1
    return areas


def golden_record(areas):
    """What the baseline keeps of each area: hashes per chunk, the census, and what a policy check needs."""
    out = {}
    for name, a in areas.items():
        full = len(a["chunks"])
        out[name] = {
            "chunks": a["chunks"], "cells": a["cells"], "biomes": dict(sorted(a["biomes"].items(), key=lambda kv: -kv[1])),
            "census": dict(sorted(a["census"].items(), key=lambda kv: -kv[1])),
            "foreignBlocks": sorted([b for b in a["blocks"] if ns_of(b) not in ("tfc", "minecraft")]
                                    + [f"block entity {b}" for b in a["blockEntities"] if ns_of(b) not in ("tfc", "minecraft")]),
            "minecraftBlocks": sorted(b for b in a["blocks"] if b.startswith("minecraft:")),
            "structureStarts": a["starts"], "entities": dict(sorted(a["entities"].items())), "full": full,
            "touched": dict(sorted(a["touched"].items())), "chunkCensus": dict(sorted(a["chunkCensus"].items())),
        }
    return out


# ------------------------------------------------------------------ the baseline file
def dump_json(v, indent=0, width=118):
    """JSON for a committed file: one key per line, short lists and dicts of plain values on one line."""
    pad = " " * (indent + 1)
    scalar = lambda x: not isinstance(x, (dict, list))  # noqa: E731
    if isinstance(v, dict):
        if not v:
            return "{}"
        flat = "{" + ", ".join(f"{json.dumps(k)}: {json.dumps(x)}" for k, x in v.items()) + "}" if all(scalar(x) for x in v.values()) else None
        if flat is not None and len(flat) + indent <= width:
            return flat
        return "{\n" + ",\n".join(f"{pad}{json.dumps(k)}: {dump_json(x, indent + 1, width)}" for k, x in v.items()) + "\n" + " " * indent + "}"
    if isinstance(v, list):
        if not v:
            return "[]"
        if all(scalar(x) for x in v):
            flat = "[" + ", ".join(json.dumps(x) for x in v) + "]"
            if len(flat) + indent <= width:
                return flat
            lines, cur = [], ""
            for x in v:
                piece = json.dumps(x) + ","
                if cur and len(cur) + len(piece) + 1 + indent + 1 > width:
                    lines.append(cur)
                    cur = ""
                cur = f"{cur} {piece}" if cur else piece
            lines.append(cur.rstrip(","))
            return "[\n" + "\n".join(pad + ln for ln in lines) + "\n" + " " * indent + "]"
        return "[\n" + ",\n".join(pad + dump_json(x, indent + 1, width) for x in v) + "\n" + " " * indent + "]"
    return json.dumps(v)


def load_baseline(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------ diff
class Findings:
    GROUPS = ("continuity", "new", "info")

    def __init__(self):
        self.items = []
        self.stats = []     # lines of context printed with the verdict (e.g. how far the golden census drifted)

    def add(self, group, title, lines=(), fix=None, unverified=False, tier=None, culprit=None, meta=None):
        """meta: machine-readable fields (kind, id, sig, ...) that --accept records with the finding."""
        self.items.append({"group": group, "title": title, "lines": list(lines), "fix": fix, "unverified": unverified, "tier": tier,
                           "culprit": culprit, "meta": meta or {}})

    def of(self, group):
        return [i for i in self.items if i["group"] == group]


def mod_label(mods, key):
    rec = mods.get(key)
    if rec is None:
        return key
    return f"{key} ({rec['file']})"


def mod_of_namespace(mods, ns):
    """The mod that ships data in a namespace, for naming a culprit."""
    if ns == "minecraft":
        return "vanilla"
    if ns in mods:
        return mod_label(mods, ns)
    for key, rec in mods.items():
        if any(c.split(":", 1)[0] == ns for c in rec.get("data", {})):
            return mod_label(mods, key)
    return f"namespace '{ns}'"


DATA_GROUP_BY_KIND = {
    "worldgen/noise_settings": "continuity", "worldgen/noise": "continuity", "worldgen/density_function": "continuity",
    "worldgen/configured_carver": "continuity", "worldgen/world_preset": "continuity", "dimension": "continuity",
    "dimension_type": "continuity", "worldgen/biome": "continuity", "tfc/worldgen": "continuity", "tags/block": "continuity",
    "worldgen/multi_noise_biome_source_parameter_list": "continuity", "tfc/climate_range": "new", "tfc/fauna": "new",
}


def data_group(cat):
    """Without the server tiers a data change can only be judged by what kind of data it is."""
    ns, kind = cat.split(":", 1)
    if ns in TERRAIN_MODS:
        return "continuity"
    return DATA_GROUP_BY_KIND.get(kind, "new")


def diff_dict(cur, base):
    added = sorted(set(cur) - set(base))
    removed = sorted(set(base) - set(cur))
    changed = sorted(k for k in set(cur) & set(base) if cur[k] != base[k])
    return added, removed, changed


def diff_static(cur, base, f, static_only):
    ce, be = cur["engine"], base["engine"]
    if ce["minecraft"] != be["minecraft"]:
        f.add("continuity", f"Minecraft {be['minecraft']} -> {ce['minecraft']}: vanilla's generation code and data changed", tier=0)
    if ce["neoforge"] != be["neoforge"]:
        f.add("continuity", f"NeoForge {be['neoforge']} -> {ce['neoforge']}: the loader's worldgen code and c: tags can change",
              ["run --golden to see whether chunks actually differ"], unverified=True, tier=0)
    cm, bm = cur["mods"], base["mods"]
    for key in sorted(set(cm) | set(bm)):
        c, b = cm.get(key), bm.get(key)
        label = mod_label(cm if c else bm, key)
        if b is None:
            kind = "terrain mod" if key in TERRAIN_MODS else "mod"
            group = "continuity" if key in TERRAIN_MODS else "info"
            f.add(group, f"{kind} added: {label}", tier=0)
            b = {}
        if c is None:
            gen = len(b.get("mixins", {}).get("gen", {}))
            f.add("continuity" if key in TERRAIN_MODS or gen else "info", f"mod removed: {label}" + (f" ({gen} worldgen mixins gone)" if gen else ""),
                  ["only --golden (tier 3) shows whether chunks generate differently"] if gen and key not in TERRAIN_MODS else [],
                  unverified=bool(gen) and key not in TERRAIN_MODS, tier=0)
            continue
        version_changed = b.get("file") not in (None, c["file"])
        data_changes = []
        cd, bd = c.get("data", {}), b.get("data", {})
        for cat in sorted(set(cd) | set(bd)):
            if cd.get(cat) != bd.get(cat):
                data_changes.append((cat, bd.get(cat), cd.get(cat)))
        file_notes = []
        if "files" in c or "files" in b:
            added, removed, changed = diff_dict(c.get("files", {}), b.get("files", {}))
            file_notes = [f"+ {n}" for n in added] + [f"- {n}" for n in removed] + [f"~ {n}" for n in changed]
        cmx, bmx = c.get("mixins", {}), b.get("mixins", {})
        gen_added, gen_removed, gen_changed = diff_dict(cmx.get("gen", {}), bmx.get("gen", {}))
        if key in TERRAIN_MODS:
            if version_changed or data_changes or gen_added or gen_removed or gen_changed:
                lines = [f"{b.get('file')} -> {c['file']}"] if version_changed else []
                lines += [f"data changed: {cat}" for cat, _, _ in data_changes[:8]]
                f.add("continuity", f"terrain code changed: {key}", lines + ["TFC and TFC: Real World are the terrain code: any change to them is a seam by definition"], tier=0)
            continue
        if data_changes:
            groups = {data_group(cat) for cat, _, _ in data_changes}
            group = "info" if not static_only else ("continuity" if "continuity" in groups else "new")
            lines = [f"{cat}: {o[0] if o else 0} -> {n[0] if n else 0} files" + (" (content changed)" if o and n and o[0] == n[0] else "")
                     for cat, o, n in data_changes[:8]] + file_notes[:10]
            note = ("the effective registries (tier 1) say whether this reaches TFC" if not static_only
                    else "static scan only: run without --static to see whether it takes effect in TFC's biomes")
            f.add(group, f"worldgen data changed in {label}", lines + [note], tier=0)
        if gen_added or gen_removed or gen_changed:
            lines = [f"+ {k.rsplit('.', 1)[-1]} -> {cmx['gen'][k].split('#')[0]}" for k in gen_added[:6]]
            lines += [f"- {k.rsplit('.', 1)[-1]}" for k in gen_removed[:6]]
            lines += [f"~ {k.rsplit('.', 1)[-1]} (class changed)" for k in gen_changed[:6]]
            f.add("continuity", f"mixins into world generation code changed in {label}",
                  lines + ["only --golden (tier 3) shows whether chunks generate differently"], unverified=True, tier=0)
        elif version_changed:
            n = len(cmx.get("gen", {}))
            f.add("info", f"{key} updated: {b.get('file')} -> {c['file']}" + (f" ({n} worldgen mixins, unchanged)" if n else ""), tier=0)
        if cmx.get("chunk") != bmx.get("chunk") and not version_changed:
            f.add("info", f"chunk storage mixins changed in {label} (they load and save chunks; they don't generate)", tier=0)
        if key in jarscan.STRUCTURE_CODE_MODS and b and c.get("classes") != b.get("classes"):
            f.add("new", f"the pack's structure code changed: {label}",
                  ["its processors and placements decide what its structures place: chunks generated from now on may differ",
                   "check with tools/structures_test.py, then accept on purpose"], tier=0, culprit=label,
                  meta={"kind": "structure_code", "id": key, "classes": c.get("classes")})
    cp, bp = cur.get("pack", {}), base.get("pack", {})
    added, removed, changed = diff_dict(cp.get("files", {}), bp.get("files", {}))
    if added or removed or changed:
        groups = {data_group(jarscan.data_category(jarscan.DATA_RE.match(n))) for n in added + changed + removed if jarscan.DATA_RE.match(n)}
        group = "info" if not static_only else ("continuity" if "continuity" in groups else "new")
        f.add(group, "the pack's own worldgen data (kubejs/data) changed",
              [f"+ {n}" for n in added] + [f"- {n}" for n in removed] + [f"~ {n}" for n in changed], tier=0)
    added, removed, changed = diff_dict(cur.get("mixinOptions", {}), base.get("mixinOptions", {}))
    for n in added + removed + changed:
        f.add("continuity", f"mixin rule options changed: config/{n} (Lithium and ModernFix switch mixins on and off there)", unverified=True, tier=0)


def neutralize_fix(mod_id):
    ns, path = mod_id.split(":", 1)
    return (f"neutralize it with a data override: kubejs/data/{ns}/neoforge/biome_modifier/{path}.json containing "
            '{"type": "neoforge:none"}')


def remove_features_fix(features, biomes, step):
    return ("strip it with kubejs/data/<pack>/neoforge/biome_modifier/strip_<name>.json: "
            + json.dumps({"type": "neoforge:remove_features", "biomes": biomes, "features": features, "steps": step}))


def modifiers_adding(ctx_mods, feature):
    out = []
    for i, m in ctx_mods.items():
        j = m["json"]
        fs = j.get("features")
        if fs is not None and (fs == feature or (isinstance(fs, list) and feature in fs)):
            out.append(i)
    return out


def diff_runtime(cur, base, f, ctx):
    mods = ctx["mods"]
    terrain_changed = ctx["terrain_changed"]
    # --- the world and its generator
    added, removed, changed = diff_dict(cur["world"], base["world"])
    spawn = [k for k in changed + added + removed if k.startswith(("spawn_settings.", "tfc_spawn_settings."))]
    if len(spawn) < len(changed + added + removed):
        f.add("continuity", "TFC: Real World's server.toml in the new world differs (map, scale, climate and generation modes)",
              [f"{k}: {base['world'].get(k)} -> {cur['world'].get(k)}" for k in changed + added + removed if k not in spawn], tier=1,
              culprit="tfc_real_world (config/tfc_real_world/common.toml, kubejs/startup_scripts/world_scale.js)")
    if spawn:
        f.add("info", "the world spawn settings in TFC: Real World's server.toml differ (they move the spawn point, not the terrain)",
              [f"{k}: {base['world'].get(k)} -> {cur['world'].get(k)}" for k in spawn], tier=1)
    for key, what in (("generatorClass", "generator class"), ("biomeSourceClass", "biome source class"), ("seaLevel", "sea level"), ("minY", "minimum Y"),
                      ("height", "world height")):
        if cur[key] != base[key]:
            f.add("continuity", f"{what} changed: {base[key]} -> {cur[key]}", tier=1)
    if cur["generator"] != base["generator"]:
        added, removed, changed = diff_dict(flatten(cur["generator"]), flatten(base["generator"]))
        f.add("continuity", "the overworld generator's settings changed (TFC's settings, rock layers, biome source)",
              [f"{k}: {flatten(base['generator']).get(k)} -> {flatten(cur['generator']).get(k)}" for k in (changed + added + removed)[:10]], tier=1)
    if cur["dimensionType"] != base["dimensionType"]:
        f.add("continuity", "the overworld dimension type changed (height, light, effects)",
              [f"{k}: {flatten(base['dimensionType']).get(k)} -> {flatten(cur['dimensionType']).get(k)}" for k in diff_dict(flatten(cur["dimensionType"]), flatten(base["dimensionType"]))[2]], tier=1)
    if cur["noiseSettings"] != base["noiseSettings"]:
        f.add("continuity", f"noise settings {cur['noiseSettings']['id']} changed (hash {base['noiseSettings']['hash']} -> {cur['noiseSettings']['hash']})", tier=1)
    ab, rb, _ = diff_dict(dict.fromkeys(cur["possibleBiomes"]), dict.fromkeys(base["possibleBiomes"]))
    if ab or rb:
        f.add("continuity", "the biome source's possible biomes changed",
              [f"+ {b}" for b in ab[:10]] + [f"- {b}" for b in rb[:10]] + ["the pack expects exactly the 125 tfc:* biomes"], tier=1)
    foreign_biomes = [b for b in cur["possibleBiomes"] if ns_of(b) != "tfc"]
    if foreign_biomes:
        f.add("continuity", f"{len(foreign_biomes)} non-TFC biomes in the biome source: {short(foreign_biomes)}", tier=1)

    # --- features, carvers and spawns of each biome
    notes = ctx["notes"]
    feature_findings = {}   # (kind, id, slot) -> biomes
    tfc_findings = {}       # (slot) -> biomes
    for b in cur["possibleBiomes"]:
        cb, bb = cur["biomes"].get(b), base["biomes"].get(b)
        if cb is None or bb is None:
            continue
        if cb["f"] != bb["f"]:
            cs, bs = cur["featureSigs"][cb["f"]], base["featureSigs"].get(bb["f"])
            if bs is None:
                continue
            for slot in sorted(set(cs["foreign"]) | set(bs["foreign"])):
                cf, bf = set(cs["foreign"].get(slot, [])), set(bs["foreign"].get(slot, []))
                for feat in sorted(cf - bf):
                    feature_findings.setdefault(("added", feat, slot), []).append(b)
                for feat in sorted(bf - cf):
                    feature_findings.setdefault(("removed", feat, slot), []).append(b)
            for i in range(max(len(cs["tfc"]), len(bs["tfc"]))):
                if i >= len(cs["tfc"]) or i >= len(bs["tfc"]):    # one side has more decoration lists: that is a difference too
                    tfc_findings.setdefault(slot_name(i), []).append(b)
                    continue
                slot = slot_name(i)
                if cs["tfc"][i] != bs["tfc"][i] or cs["n"][i] - len(cs["foreign"].get(slot, [])) != bs["n"][i] - len(bs["foreign"].get(slot, [])):
                    tfc_findings.setdefault(slot, []).append(b)
        if cb["c"] != bb["c"]:
            notes.setdefault("carvers", []).append(b)
        if cb["s"] != bb["s"]:
            ss, bs = cur["spawnSigs"][cb["s"]], base["spawnSigs"].get(bb["s"])
            if bs is None:
                continue
            for cat in sorted(set(ss["n"]) | set(bs["n"])):
                cf, bf = set(ss["foreign"].get(cat, [])), set(bs["foreign"].get(cat, []))
                for e in sorted(cf - bf):
                    feature_findings.setdefault(("spawn+", e, cat), []).append(b)
                for e in sorted(bf - cf):
                    feature_findings.setdefault(("spawn-", e, cat), []).append(b)
                if ss["tfc"].get(cat) != bs["tfc"].get(cat):
                    tfc_findings.setdefault("spawns:" + cat, []).append(b)
    for (kind, ident, slot), biomes in sorted(feature_findings.items()):
        culprit = ", ".join(modifiers_adding(ctx["cur_modifiers"], ident)) or "no biome modifier names it: it comes through a tag or another datapack entry"
        where = f"{plural(len(biomes), 'biome')} ({short(biomes, 4)})"
        if kind == "added":
            mods_adding = modifiers_adding(ctx["cur_modifiers"], ident)
            strip = remove_features_fix(ident, biomes if len(biomes) <= 8 else "#c:is_overworld", slot)
            fix = (neutralize_fix(mods_adding[0]) + "; or " + strip) if mods_adding else strip
            who = mod_of_namespace(mods, ns_of(mods_adding[0] if mods_adding else ident))
            f.add("new", f"feature {ident} now generates in {where}, decoration slot {slot}",
                  [f"feature from {mod_of_namespace(mods, ns_of(ident))}; added by modifier: {culprit}"], fix=fix, tier=1, culprit=who)
        elif kind == "removed":
            f.add("new", f"feature {ident} no longer generates in {where}, decoration slot {slot}",
                  [f"it belonged to {mod_of_namespace(mods, ns_of(ident))}; new chunks lose it, old ones keep it"], tier=1,
                  culprit=mod_of_namespace(mods, ns_of(ident)))
        elif kind == "spawn+":
            f.add("new", f"{ident.split('*')[0]} now spawns ({slot.lower()}, {ident.split('*')[1]}) in {where}", [f"from: {mod_of_namespace(mods, ns_of(ident))}"],
                  fix="strip it with a neoforge:remove_spawns biome modifier: " + json.dumps({"type": "neoforge:remove_spawns", "biomes": biomes if len(biomes) <= 8 else "#c:is_overworld", "entity_types": ident.split("*")[0]}),
                  tier=1, culprit=mod_of_namespace(mods, ns_of(ident)))
        else:
            f.add("new", f"{ident.split('*')[0]} no longer spawns ({slot.lower()}) in {where}", tier=1, culprit=mod_of_namespace(mods, ns_of(ident)))
    for slot, biomes in sorted(tfc_findings.items()):
        if slot.startswith("spawns:"):
            group, what = "new", f"TFC's own mob spawns ({slot[7:]})"
        else:
            group, what = ("continuity" if slot in TERRAIN_SLOTS else "new"), f"TFC's own features in decoration slot {slot}"
        if terrain_changed:
            group = "info"
        f.add(group, f"{what} differ in {plural(len(biomes), 'biome')} ({short(biomes, 4)})",
              ["TFC's data changed (see the terrain code finding)"] if terrain_changed else
              ["TFC's jar is unchanged, so another mod's data or a tag edit changed what TFC's biomes generate"], tier=1)
    if notes.get("carvers"):
        f.add("continuity", f"carvers changed in {plural(len(notes['carvers']), 'biome')} ({short(notes['carvers'], 4)})", tier=1)

    # --- modifiers, structures, tags
    cm, bm = cur["modifiers"], base["modifiers"]
    for i in sorted(set(cm) | set(bm)):
        c, b = cm.get(i), bm.get(i)
        ns = ns_of(i)
        if b is None:
            live = c["hits"] > 0
            f.add("new" if live else "info", f"biome/structure modifier added: {i} ({mod_of_namespace(mods, ns)})",
                  [json.dumps(c["json"]), f"reaches {c['hits']} TFC biomes" + ("" if live else " (inert: its target holds no TFC biome; it goes live if a tag it targets gains one)")],
                  fix=neutralize_fix(i) if live else None, tier=1, culprit=mod_of_namespace(mods, ns))
        elif c is None:
            f.add("info", f"modifier removed: {i}" + (f" (it reached {b['hits']} TFC biomes)" if b["hits"] else ""), tier=1)
        elif c["json"] != b["json"] or c["hits"] != b["hits"]:
            live = c["hits"] > 0 or b["hits"] > 0
            f.add("new" if live else "info", f"modifier {i} changed ({mod_of_namespace(mods, ns)})",
                  [f"was: {json.dumps(b['json'])} (reached {b['hits']} TFC biomes)", f"now: {json.dumps(c['json'])} (reaches {c['hits']})"],
                  fix=neutralize_fix(i) if c["hits"] else None, tier=1, culprit=mod_of_namespace(mods, ns))
    for s, biomes in sorted(cur["structures"]["hits"].items()):
        if s in base["structures"]["hits"]:
            continue
        doc = ctx["raw_registries"].get("minecraft:worldgen/structure", {}).get(s, {})
        spec = doc.get("biomes")
        tag = spec[1:] if isinstance(spec, str) and spec.startswith("#") else None
        fix = (f"empty its biome tag: kubejs/data/{tag.split(':')[0]}/tags/worldgen/biome/{tag.split(':')[1]}.json containing "
               '{"replace": true, "values": []}') if tag else "override the structure's JSON under kubejs/data with an empty \"biomes\" list"
        f.add("new", f"structure {s} can start in {len(biomes)} TFC biomes ({short(biomes, 4)})",
              [f"from: {mod_of_namespace(mods, ns_of(s))}"], fix=fix, tier=1, culprit=mod_of_namespace(mods, ns_of(s)),
              meta={"kind": "structure", "id": s, "sig": (cur.get("structureSigs") or {}).get(s, {}).get("sig")})
    cs, bs = cur.get("structureSigs") or {}, base.get("structureSigs") or {}
    for s in sorted(set(cs) & set(bs)):
        if cs[s]["sig"] != bs[s]["sig"]:
            parts = [k for k in cs[s]["parts"] if cs[s]["parts"][k] != bs[s]["parts"].get(k)]
            f.add("new", f"structure {s} changed ({', '.join(parts) or 'definition'})",
                  ["chunks generated from now on build it differently; one cut by the edge of explored land would join old and new halves"],
                  fix="revert the change, or accept it on purpose", tier=1, culprit=mod_of_namespace(mods, ns_of(s)),
                  meta={"kind": "structure", "id": s, "sig": cs[s]["sig"]})
    csites, bsites = cur.get("sites") or {}, base.get("sites") or {}
    for site in sorted(set(csites) | set(bsites)):
        c, b = csites.get(site), bsites.get(site)
        if b is None and c:
            f.add("new", f"real-world site {site} added at chunk {c[0]}, {c[1]} (block {c[2]}, {c[3]})",
                  ["new worlds generate it; worlds that existed before keep it off until an operator runs "
                   f"/pack_world sites enable {site} (after checking the area is unexplored)"], tier=1, culprit="pack_world",
                  meta={"kind": "site", "id": site, "chunk": c[:2]})
        elif c is None:
            f.add("info", f"real-world site {site} removed (worlds that generated it keep what was built)", tier=1)
        elif c[:2] != b[:2]:
            f.add("new", f"real-world site {site} moved: chunk {b[0]}, {b[1]} -> {c[0]}, {c[1]}",
                  ["worlds that already generated it get a second copy where it now lands, or half of one; keep a site's coordinates "
                   "and offset fixed once it has shipped"], tier=1, culprit="pack_world", meta={"kind": "site", "id": site, "chunk": c[:2]})
    for tag in sorted(set(cur["biomeTags"]) | set(base["biomeTags"])):
        c, b = cur["biomeTags"].get(tag), base["biomeTags"].get(tag)
        cs, bs = set(c["tfc"]) if c else set(), set(b["tfc"]) if b else set()
        if cs != bs:
            f.add("info", f"biome tag {tag} now holds {len(cs)} TFC biomes (was {len(bs)}): any modifier or structure aimed at it lands in TFC",
                  [f"+ {m}" for m in sorted(cs - bs)[:8]] + [f"- {m}" for m in sorted(bs - cs)[:8]], tier=1)

    # --- registries
    classify_registries(cur, base, f, ctx)

    # --- veins and config
    cv, bv = cur.get("oreVeins") or {}, base.get("oreVeins") or {}
    if cv.get("generating"):
        f.add("new", f"{len(cv['generating'])} GregTech ore veins can generate: {short(cv['generating'], 5)}",
              ["they can't run in TFC's generator today (and the pack switches them off in kubejs/server_scripts/gregtech/ore_processing.js)"],
              fix="add the new vein ids to the removal list in kubejs/server_scripts/gregtech/ore_processing.js", tier=1, culprit="gtceu")
    elif cv.get("registered") != bv.get("registered"):
        f.add("info", f"GregTech ore veins registered: {bv.get('registered')} -> {cv.get('registered')} (none generate)", tier=1)
    added, removed, changed = diff_dict(cur["config"], base["config"])
    for k in added + removed + changed:
        gt_tree = k == "gtceu.worldgen.rubberTreeSpawnChance" or k == "runtime.gtRubberTreeSpawnChance"
        group = "new" if gt_tree else "info"
        f.add(group, f"config {k}: {base['config'].get(k)} -> {cur['config'].get(k)}",
              ["GregTech's rubber trees are the accepted baseline; their spawn chance only affects new chunks"] if gt_tree else
              ["inert in TFC's generator (the config gates content that doesn't reach TFC biomes)"], tier=1, culprit=k.split(".")[0])


REGISTRY_KINDS = {
    "minecraft:worldgen/placed_feature": ("placed", "new"), "minecraft:worldgen/configured_feature": ("configured", "new"),
    "minecraft:worldgen/configured_carver": ("carver", "continuity"), "minecraft:worldgen/density_function": ("density", "continuity"),
    "minecraft:worldgen/noise": ("noise", "continuity"), "minecraft:worldgen/noise_settings": ("noise_settings", "continuity"),
    "minecraft:dimension_type": (None, "continuity"), "minecraft:dimension": (None, "continuity"), "minecraft:worldgen/world_preset": (None, "continuity"),
    "tfc:worldgen/rock_settings": (None, "continuity"),
}


def classify_registries(cur, base, f, ctx):
    mods, reach = ctx["mods"], ctx["reach"]
    for name in sorted(set(cur["registries"]) | set(base["registries"])):
        c, b = cur["registries"].get(name), base["registries"].get(name)
        if c is None or b is None:
            f.add("info", f"registry {name} {'appeared' if b is None else 'disappeared'}", tier=1)
            continue
        if c["hash"] == b["hash"]:
            continue
        kind, default = REGISTRY_KINDS.get(name, (None, "info"))
        short_name = name.split(":", 1)[1] if name.startswith("minecraft:") else name
        # TFC's own entries, by bucket
        ct, bt = c.get("tfc", {}), b.get("tfc", {})
        added, removed, changed = diff_dict(ct, bt)
        if added or removed or changed:
            f.add("info" if ctx["terrain_changed"] else "continuity", f"TFC's {short_name} changed in {len(added) + len(removed) + len(changed)} groups",
                  [f"tfc:{g}/*: {bt.get(g, [0])[0]} -> {ct.get(g, [0])[0]} entries" for g in (changed + added + removed)[:8]]
                  + (["part of the TFC update (terrain code finding)"] if ctx["terrain_changed"] else ["TFC's jar is unchanged: a datapack or another mod rewrote TFC's entries"]), tier=1)
        # vanilla entries
        if c.get("minecraft") != b.get("minecraft"):
            f.add(default if default == "continuity" else "info", f"vanilla {short_name} entries changed ({b.get('minecraft', [0])[0]} -> {c.get('minecraft', [0])[0]})",
                  ["a mod or datapack overrides a minecraft: entry; the tier 0 file lists name it"], tier=1)
        # other mods' entries, by id
        added, removed, changed = diff_dict(c.get("entries", {}), b.get("entries", {}))
        for i in added + removed + changed:
            verb = "added" if i in added else "removed" if i in removed else "changed"
            ns = ns_of(i)
            where = mod_of_namespace(mods, ns)
            if name in ("neoforge:biome_modifier", "neoforge:structure_modifier"):
                continue   # reported with its reach
            if name.startswith("gtceu:") or kind is None and default == "info":
                f.add("info", f"{short_name} {i} {verb} ({where})", tier=1)
                continue
            if verb == "removed":
                f.add("info", f"{short_name} {i} removed ({where})", tier=1)
                continue
            if verb == "added" and name in ("minecraft:dimension_type", "minecraft:worldgen/world_preset") and ns != "minecraft" and ns not in TERRAIN_MODS:
                # a new dimension type (AE2's spatial storage) or world preset (Bits 'n' Bobs') alters no dimension that exists
                f.add("info", f"{short_name} {i} {verb} ({where}); a new entry changes no existing dimension or preset", tier=1)
                continue
            live = (kind, i) in reach
            if default == "continuity" and (live or kind is None):
                f.add("continuity", f"{short_name} {i} {verb} ({where})", ["it is part of what the overworld generates with"] if live else [], tier=1, culprit=where)
            elif default == "new" and live:
                f.add("new", f"{short_name} {i} {verb} ({where})", ["a TFC biome generates it (through its feature lists)"], tier=1, culprit=where)
            else:
                f.add("info", f"{short_name} {i} {verb} ({where}); no TFC biome reaches it", tier=1)


def diff_points(cur, base, f):
    cc, bc = cur["clusters"], base["clusters"]
    if cur["n"] != base["n"] or set(cc) != set(bc) or any(cc[k]["at"] != bc[k]["at"] for k in set(cc) & set(bc)):
        f.add("continuity", f"the sample points moved: {base['n']} -> {cur['n']} points, clusters {len(bc)} -> {len(cc)}",
              ["the random land and sea clusters are picked from the continent map, so the map changed"], tier=2)
    stats = {"height": 0, "biome": 0, "rock": 0, "climate": 0}
    total = 0
    worst = 0
    bad = {}
    for k in sorted(set(cc) & set(bc)):
        cp, bp = cc[k]["points"], bc[k]["points"]
        for i, (a, b) in enumerate(zip(cp, bp)):
            total += 1
            if a == b:
                continue
            ah, ab_, ar, ac = a.split(".")
            bh, bb_, br, bcl = b.split(".")
            stats["height"] += ah != bh
            stats["biome"] += ab_ != bb_
            stats["rock"] += ar != br
            stats["climate"] += ac != bcl
            worst = max(worst, abs(int(ah) - int(bh)))
            bad.setdefault(k, []).append(i)
    if not bad:
        return
    lines = [f"{total} compared points: {stats['height']} differ in height (up to {worst} blocks), {stats['biome']} in biome, "
             f"{stats['rock']} in rock, {stats['climate']} in climate"]
    for k, pts in sorted(bad.items(), key=lambda kv: -len(kv[1]))[:8]:
        lines.append(f"{k} (around {cc[k]['at'][0]},{cc[k]['at'][1]}): {len(pts)} of {len(cc[k]['points'])} points")
    for name, p in sorted(cur["places"].items()):
        b = base["places"].get(name)
        if not b:
            continue
        diffs = [f"{what} {b[key] if not isinstance(b[key], list) else ','.join(map(str, b[key]))} -> {p[key] if not isinstance(p[key], list) else ','.join(map(str, p[key]))}"
                 for what, key in (("height", "height"), ("biome", "biome"), ("rock", "rock"), ("climate", "climate")) if b[key] != p[key]]
        if diffs:
            lines.append(f"{name}: " + "; ".join(diffs))
            if len(lines) > 16:
                break
    f.add("continuity", "terrain, biomes or rock differ at the sampled points", lines, tier=2)


def census_groups(census):
    """Group a block census: rock:<host> (every variant, ore and deposit in that rock), ore:<mineral>, air, fluids, the rest."""
    out = {}

    def add(key, n):
        out[key] = out.get(key, 0) + n

    for blk, n in census.items():
        ns, _, path = blk.partition(":")
        parts = path.split("/")
        if ns == "tfc" and parts[0] in ("rock", "ore", "deposit") and len(parts) >= 3:
            add("rock:" + parts[-1], n)
            if parts[0] == "ore":
                add("ore:" + re.sub(r"^(poor|normal|rich)_", "", parts[1]), n)
            elif parts[0] == "deposit":
                add("ore:" + parts[1], n)
        elif blk in ("minecraft:air", "minecraft:cave_air"):
            add("air", n)
        elif blk in ("minecraft:water", "minecraft:lava", "minecraft:bedrock") or path.startswith("fluid/"):
            add(blk if blk.startswith("minecraft:") else "fluid:" + path.split("/", 1)[1], n)
        else:
            add("other", n)
    return out


def census_drift(cur, base, cells):
    """(share of cells moved between host rocks, what moved beyond the limits as 'group: old -> new') for two censuses."""
    return census_drift_grouped(census_groups(cur), census_groups(base), cells)


def sum_groups(chunk_census, keys):
    out = {}
    for k in keys:
        for g, n in chunk_census[k].items():
            if g != "_cells":
                out[g] = out.get(g, 0) + n
    return out


def census_drift_grouped(cg, bg, cells):
    hosts = [k for k in set(cg) | set(bg) if k.startswith("rock:")]
    moved = sum(abs(cg.get(k, 0) - bg.get(k, 0)) for k in hosts) / 2 / max(cells, 1)
    issues = []
    for k in sorted(set(cg) | set(bg)):
        if k.startswith("rock:") or k == "other":
            continue
        old, new = bg.get(k, 0), cg.get(k, 0)
        if abs(new - old) > CENSUS_FLOOR + CENSUS_REL * old:
            issues.append(f"{k}: {old:,} -> {new:,}")
    if moved > CENSUS_HOST:
        top = sorted(hosts, key=lambda k: -abs(cg.get(k, 0) - bg.get(k, 0)))[:6]
        issues = [f"{k}: {bg.get(k, 0):,} -> {cg.get(k, 0):,}" for k in top] + issues
    return moved, issues


def golden_known(base):
    """What the baseline's golden areas already held (what was accepted): foreign blocks, vanilla blocks, entities, structure starts."""
    known = {"foreign": set(ALLOWED_FOREIGN_BLOCKS), "minecraft": set(ALLOWED_MINECRAFT_BLOCKS), "entities": set(), "starts": set()}
    for a in (base or {}).values():
        known["foreign"] |= set(a["foreignBlocks"])
        known["minecraft"] |= set(a["minecraftBlocks"])
        known["entities"] |= {e for e in a["entities"] if ns_of(e) != "tfc"}
        known["starts"] |= set(a["structureStarts"])
    return known


def golden_violations(area, known):
    """What an area holds beyond the allow-lists and what the baseline accepted: (blocks, vanilla blocks, structure starts, entities)."""
    return ([x for x in area["foreignBlocks"] if x not in known["foreign"]], [x for x in area["minecraftBlocks"] if x not in known["minecraft"]],
            [s for s in area["structureStarts"] if s not in known["starts"]], [e for e in area["entities"] if ns_of(e) != "tfc" and e not in known["entities"]])


def diff_golden(cur, base, f, ctx):
    mods = ctx["mods"]
    known = golden_known(base)
    for name in cur:
        c, b = cur[name], (base or {}).get(name)
        # nothing outside TFC's own may generate, except what the baseline accepted
        bad_blocks, bad_mc, bad_starts, bad_e = golden_violations(c, known)
        if bad_blocks:
            f.add("new", f"{name}: blocks from another mod generated: {short(bad_blocks)}",
                  [f"from: {short((mod_of_namespace(mods, ns_of(x)) for x in bad_blocks), 3)}"],
                  fix="find the feature that places it (tier 1 lists new features) and strip it with a neoforge:remove_features biome modifier",
                  tier=3, culprit=short((mod_of_namespace(mods, ns_of(x)) for x in bad_blocks), 3))
        if bad_mc:
            f.add("new", f"{name}: vanilla blocks TFC doesn't generate in the baseline: {short(bad_mc)}",
                  ["a vanilla feature or structure now runs in a TFC biome"], tier=3, culprit="minecraft")
        if bad_starts:
            f.add("new", f"{name}: structure starts generated: {', '.join(bad_starts)}", ["a structure not yet accepted starts in this golden area"], tier=3,
                  culprit=short((mod_of_namespace(mods, ns_of(s)) for s in bad_starts), 3),
                  meta={"kind": "structure_start", "id": bad_starts if len(bad_starts) > 1 else bad_starts[0], "area": name})
        if bad_e:
            f.add("new", f"{name}: entities outside tfc: generated: {short(bad_e)}", tier=3,
                  culprit=short((mod_of_namespace(mods, ns_of(e)) for e in bad_e), 3))
        if b is None:
            f.add("info", f"golden area {name} is not in the baseline (run --update --golden)", tier=3)
            continue
        if set(c["chunks"]) != set(b["chunks"]):
            f.add("info", f"golden area {name}: {len(c['chunks'])} chunks generated, the baseline has {len(b['chunks'])}", tier=3)
        diff_biome = [k for k in c["chunks"] if k in b["chunks"] and c["chunks"][k][0] != b["chunks"][k][0]]
        diff_data = [k for k in c["chunks"] if k in b["chunks"] and c["chunks"][k][1] != b["chunks"][k][1]]
        if diff_biome:
            f.add("continuity", f"{name}: biomes differ in {len(diff_biome)} of {len(c['chunks'])} chunks ({short(diff_biome, 4, '; ')})",
                  [f"biomes now {dict(list(c['biomes'].items())[:6])}", f"baseline {dict(list(b['biomes'].items())[:6])}"], tier=3)
        if diff_data:
            f.add("continuity", f"{name}: tfc:chunk_data (surface heights, climate, forest type) differs in {len(diff_data)} of {len(c['chunks'])} chunks ({short(diff_data, 4, '; ')})", tier=3)
        if c.get("chunkCensus") and b.get("chunkCensus"):
            # Chunks a structure reaches in either run are left out: its blocks and terrain adaptation aren't terrain drift.
            ct, bt = c.get("touched", {}), b.get("touched", {})
            skip = set(ct) | set(bt)
            keys = (set(c["chunkCensus"]) & set(b["chunkCensus"])) - skip
            cells = sum(c["chunkCensus"][k].get("_cells", 0) for k in keys)
            moved, issues = census_drift_grouped(sum_groups(c["chunkCensus"], keys), sum_groups(b["chunkCensus"], keys), cells)
            if skip:
                under = sorted({x for k in skip for x in ct.get(k, []) + bt.get(k, [])})
                f.stats.append(f"golden {name}: {len(skip)} chunks reached by structures left out of the census ({short(under, 4)})")
        else:
            moved, issues = census_drift(c["census"], b["census"], c["cells"])
            if c.get("touched"):
                f.add("info", f"golden area {name}: the baseline has no per-chunk census, so chunks under structures can't be left out "
                              "(run --update --golden once to record it)", tier=3)
        f.stats.append(f"golden {name}: {len(c['chunks'])} chunks, {c['cells']:,} underground cells, {moved:.4%} moved between host rocks (limit {CENSUS_HOST:.2%}), "
                       f"biomes {'same' if not diff_biome else 'DIFFER'}, chunk data {'same' if not diff_data else 'DIFFER'}")
        if issues:
            f.add("continuity", f"{name}: the underground rock, ore, cave or fluid census moved ({moved:.3%} of cells between host rocks)", issues[:10], tier=3)


# ------------------------------------------------------------------ the run
def wait_lines(srv, pattern, timeout, start=0):
    """Poll srv.lines from index start for a match. Returns (match, next_index); match is None on timeout/exit."""
    rx = re.compile(pattern)
    end = time.time() + timeout
    i = start
    while time.time() < end:
        while i < len(srv.lines):
            line = srv.lines[i]
            i += 1
            m = rx.search(line)
            if m:
                return m, i
        if srv.proc.poll() is not None:
            return None, i
        time.sleep(0.5)
    return None, i


def find_chunky(srv):
    try:
        return chunky_jar(srv, srv.pack["versions"]["minecraft"], srv.loader)
    except OSError as e:
        cached = sorted(f for f in os.listdir(srv.path(".cache")) if f.lower().startswith("chunky") and f.endswith(".jar")) if os.path.isdir(srv.path(".cache")) else []
        if not cached:
            raise SystemExit(f"Chunky isn't cached and Modrinth is unreachable ({e})")
        print(f"Modrinth unreachable ({e}); using the cached {cached[-1]}")
        return srv.path(".cache", cached[-1])


def run_server(args, job, timings):
    """Boot the test server on a fresh world, let the script fingerprint it, and (--golden) generate the golden areas."""
    srv = TestServer()
    srv.ensure_installed()
    t = time.time()
    if not args.no_sync:
        srv.sync_pack()
    timings["sync"] = time.time() - t
    extra = [find_chunky(srv)] if args.golden else []
    srv.set_extra_mods(extra)
    srv.set_dev_scripts({"worldgen_check.js": write_job_script(job)})
    shutil.rmtree(srv.path("local", "worldgen-check"), ignore_errors=True)
    shutil.rmtree(srv.path(WORLD), ignore_errors=True)
    srv.write_properties(WORLD, args.seed)
    print(f"Starting server for a fresh {WORLD} (seed '{args.seed}')...")
    started = time.time()
    srv.start(args.xmx)
    done, fatal, golden = None, [], False
    try:
        ready, pos = wait_lines(srv, r"\[worldgen-check\] start", 1200)
        if not ready:
            tail = "\n".join(srv.lines[-30:])
            raise SystemExit("The fingerprint script never started (server crashed, or the script didn't load):\n" + tail)
        timings["boot"] = time.time() - started
        print(f"Server up after {timings['boot']:.0f} s; fingerprinting registries and sampling points...")
        t = time.time()
        done, pos = wait_lines(srv, r"\[worldgen-check\] done", args.timeout, pos)
        timings["tiers12"] = time.time() - t
        fatal = [ln[ln.index("[worldgen-check] FATAL"):] for ln in srv.lines if "[worldgen-check] FATAL" in ln]
        if done and not fatal:
            for ln in srv.lines:
                if "[worldgen-check]" in ln and "FATAL" not in ln:
                    print("  " + ln[ln.index("[worldgen-check]"):])
        if done and not fatal and args.golden:
            golden = run_golden(srv, timings)
    finally:
        srv.set_dev_scripts({})
        srv.set_extra_mods([])
        srv.stop()
    if not done:
        raise SystemExit("The fingerprint script didn't finish (timed out or the server stopped); see tools/.server/logs/latest.log")
    return srv, extra, fatal, golden


def run_golden(srv, timings):
    """Generate the golden areas with Chunky, one after another, and save the world."""
    t = time.time()
    print(f"Generating {len(GOLDEN)} golden areas with Chunky...")
    srv.command("chunky world minecraft:overworld")
    srv.command("chunky shape square")
    pos = len(srv.lines)
    for name, x, z, _ in GOLDEN:
        srv.command(f"chunky center {x} {z}")
        srv.command(f"chunky radius {GOLDEN_RADIUS}")
        srv.command("chunky start")
        m, pos = wait_lines(srv, FINISHED_RE, 600, pos)
        if not m:
            raise SystemExit(f"Chunky didn't finish the {name} area; see tools/.server/logs/latest.log")
        print(f"  {name}: {srv.lines[pos - 1].split('Processed: ', 1)[-1]}")
    srv.command("save-all flush")
    wait_lines(srv, r"Saved the game", 300, pos)
    timings["golden_generate"] = time.time() - t
    return True


def collect(out_dir, world_dir, server_dir):
    """Read the script's output, the new world's TFC: Real World config and the server's config files into the raw dict."""
    for name in ("info", "biomes", "points"):
        if not os.path.exists(os.path.join(out_dir, name + ".json")):
            raise SystemExit(f"The fingerprint script wrote no {name}.json; see tools/.server/logs/latest.log")
    raw = {"info": read_json(os.path.join(out_dir, "info.json")), "biomes": read_json(os.path.join(out_dir, "biomes.json")),
           "points": read_json(os.path.join(out_dir, "points.json")), "registries": {}}
    for name in raw["info"]["registries"]:
        raw["registries"][name] = read_json(os.path.join(out_dir, "registry-" + re.sub(r"[:/]", "_", name) + ".json"))
    toml = os.path.join(world_dir, "serverconfig", "tfc_real_world", "server.toml")
    if not os.path.exists(toml):
        raise SystemExit("The new world has no serverconfig/tfc_real_world/server.toml (is TFC: Real World loaded?)")
    with open(toml, "rb") as f:
        raw["world_config"] = flatten(tomllib.load(f))
    raw["config"] = read_config(server_dir)
    return raw


def fingerprint(seed, t0, raw, golden_areas):
    ctx = {"raw_registries": raw["registries"]}
    fp = {"schema": SCHEMA, "seed": seed, "tier0": t0, "tier1": tier1(raw), "tier2": tier2(raw)}
    fp["tier1"]["structureSigs"] = structure_sigs(raw, t0)
    fp["tier1"]["sites"] = raw["info"].get("sites") or {}
    ctx["reach"] = reachable(raw)
    ctx["cur_modifiers"] = fp["tier1"]["modifiers"]
    if golden_areas is not None:
        fp["tier3"] = {"areas": golden_record(golden_areas),
                       "where": {name: {"at": [x, z], "what": what} for name, x, z, what in GOLDEN}}
    return fp, ctx


def compare(fp, base, ctx):
    f = Findings()
    ctx = dict(ctx)
    ctx["mods"] = fp["tier0"]["mods"]
    ctx["notes"] = {}
    diff_static(fp["tier0"], base["tier0"], f, False)
    ctx["terrain_changed"] = any(i["group"] == "continuity" and i["title"].startswith("terrain code changed") for i in f.items)
    diff_runtime(fp["tier1"], base["tier1"], f, ctx)
    diff_points(fp["tier2"], base["tier2"], f)
    if "tier3" in fp and "tier3" in base:
        diff_golden(fp["tier3"]["areas"], base["tier3"]["areas"], f, ctx)
        # Code-level suspicions are settled by the golden chunks: identical points and chunks mean the code didn't change output.
        if not any(i["group"] == "continuity" and i["tier"] in (2, 3) for i in f.items):
            for i in f.items:
                if i["unverified"]:
                    i.update(group="info", unverified=False, lines=i["lines"] + ["verified: the sampled points and golden chunks are identical to the baseline's"])
    elif "tier3" in fp:
        diff_golden(fp["tier3"]["areas"], None, f, ctx)
    return f


ACCEPT_HINT = 'or accept it as a deliberate addition (recorded in the baseline): tools/.venv/Scripts/python tools/worldgen_check.py --accept "<why>"'
GROUP_TITLES = {
    "continuity": "CONTINUITY-BREAKING: existing worlds would show seams (terrain, biomes, rock, carvers, veins, sea level, map); always refused",
    "new": "NEW-CHUNKS-ONLY: only chunks generated from now on differ; strip them (fix lines), " + ACCEPT_HINT,
    "info": "INFO: not a generation change",
}


def print_findings(f, groups=Findings.GROUPS, accepting=False):
    for g in groups:
        items = f.of(g)
        if not items:
            continue
        title = GROUP_TITLES[g].split(":")[0] + " (taken into the baseline)" if accepting and g != "info" else GROUP_TITLES[g]
        print(f"\n{title}")
        for it in items:
            tag = " [unverified: needs --golden]" if it["unverified"] else ""
            print(f"  * {it['title']}{tag}")
            for ln in it["lines"]:
                print(f"      {ln}")
            if it["fix"]:
                print(f"      fix: {it['fix']}")


# ------------------------------------------------------------------ the baseline moves only on purpose
ABOUT = [
    "Fingerprint of the overworld's generation, made by tools/worldgen_check.py on a fresh world (seed 'worldgen', 20 m per block).",
    "Compare with that tool; it moves only through its --update (first baseline, info-only changes), --accept \"<reason>\" (new-chunks-only",
    "additions, recorded under 'accepted') and --update --force-terrain \"<reason>\" (continuity-breaking, recorded as terrain).",
    "Add --golden to refresh the golden chunk areas. Commit the result with a message saying why generation was allowed to change.",
]


def initial_accepted(fp):
    """The first baseline records what already generates from outside TFC, so the accepted state is written down."""
    out = []
    known = golden_known(None)
    for name, a in (fp.get("tier3") or {}).get("areas", {}).items():
        for kind, found in zip(("block", "vanilla block", "structure start", "entity"), golden_violations(a, known)):
            out += [{"what": f"{kind} {x} generates in the golden area {name}", "mod": mod_of_namespace(fp["tier0"]["mods"], ns_of(x)), "tier": 3} for x in found]
    t1, mods = fp["tier1"], fp["tier0"]["mods"]
    found = set()
    for sig in t1["featureSigs"].values():
        for slot, feats in sig["foreign"].items():
            found.update((ft, slot) for ft in feats)
    for ft, slot in sorted(found):
        biomes = [b for b, d in t1["biomes"].items() if ft in t1["featureSigs"][d["f"]]["foreign"].get(slot, [])]
        out.append({"what": f"feature {ft} generates in {len(biomes)} TFC biomes, decoration slot {slot}", "mod": mod_of_namespace(mods, ns_of(ft)), "tier": 1})
    for mid, m in sorted(t1["modifiers"].items()):
        if m["hits"]:
            out.append({"what": f"modifier {mid} reaches {m['hits']} TFC biomes", "mod": mod_of_namespace(mods, ns_of(mid)), "tier": 1})
    return out


def update(fp, base, ctx, args, timings, total):
    """Write the baseline, refusing what the policy refuses. Returns the exit code."""
    reason = args.force_terrain or args.accept
    entries = []
    if base is None:
        if args.accept or args.force_terrain:
            raise SystemExit("There is no baseline yet: make the first one with plain --update (and --golden)")
        print("First baseline: recording what already generates from outside TFC as the accepted state.")
        entries = [{"date": time.strftime("%Y-%m-%d"), "reason": "initial baseline", "terrain": False, "findings": initial_accepted(fp)}]
    else:
        f = compare(fp, base, ctx)
        cont, new = f.of("continuity"), f.of("new")
        if cont and not args.force_terrain:
            print_findings(f, ("continuity", "new"))
            print(f"\nRefused: {len(cont)} continuity-breaking finding(s). The baseline doesn't take terrain changes"
                  + (" (and --accept can't either)" if args.accept else "") + "; revert the change, or confirm it with --update --force-terrain \"<reason>\".")
            return 1
        if new and not reason:
            print_findings(f, ("new",))
            print(f"\nRefused: {len(new)} new-chunks-only finding(s) can't go into the baseline with a plain --update. Strip them (the fix lines), "
                  'or accept them on purpose with --accept "<reason>".')
            return 1
        if args.force_terrain and cont:
            bar = "!" * 100
            print(f"\n{bar}\n!!! FORCING {len(cont)} CONTINUITY-BREAKING CHANGE(S) INTO THE BASELINE: {args.force_terrain}\n"
                  "!!! Chunks generated from now on will not match the ones players already explored; expect seams.\n"
                  f"{bar}")
        print("Taking these differences into the baseline:")
        print_findings(f, accepting=True)
        taken = (cont if args.force_terrain else []) + (new if reason else [])
        if taken:
            entries = [{"date": time.strftime("%Y-%m-%d"), "reason": reason, "terrain": bool(args.force_terrain and cont),
                        "findings": [dict({"what": i["title"], "mod": i["culprit"] or "terrain code", "tier": i["tier"]}, **i.get("meta", {}))
                                     for i in taken]}]
        elif reason:
            print("(nothing to accept: the differences are info only)")
    if base is not None and "tier3" not in fp and "tier3" in base:
        fp["tier3"] = base["tier3"]
        print("Kept the baseline's golden section (add --golden to refresh it).")
    accepted = (base or {}).get("accepted", []) + entries
    out = {"schema": SCHEMA, "about": ABOUT, "seed": fp["seed"], "accepted": accepted, **{k: v for k, v in fp.items() if k not in ("schema", "seed")}}
    with open(args.baseline, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(dump_json(out) + "\n")
    print(f"\nBaseline written: {args.baseline} ({os.path.getsize(args.baseline) / 1024:.0f} KB), {len(accepted)} accepted entries. "
          "Commit it with a message saying why.")
    t = ", ".join(f"{k} {v:.0f} s" for k, v in timings.items())
    print(f"Total time {total:.0f} s ({t}). Verdict: UPDATED")
    return 0


def finish(f, args, timings, total):
    print_findings(f)
    cont, new, info = len(f.of("continuity")), len(f.of("new")), len(f.of("info"))
    for line in f.stats:
        print(line)
    report = {"generated": time.strftime("%Y-%m-%d %H:%M:%S"), "seconds": round(total), "timings": {k: round(v, 1) for k, v in timings.items()},
              "static": bool(args.static), "golden": bool(args.golden), "stats": f.stats, "findings": f.items}
    out = args.out or os.path.join(DATA_DIR, "reports", f"worldgen-{time.strftime('%Y%m%d-%H%M%S')}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)
    t = ", ".join(f"{k} {v:.0f} s" for k, v in timings.items())
    print(f"\nReport: {out}" + (f"  ({t})" if t else ""))
    ok = cont == 0 and new == 0
    unverified = sum(1 for i in f.items if i["unverified"])
    print(f"Total time {total:.0f} s. Verdict: {'PASS' if ok else 'FAIL'} ({cont} continuity-breaking" + (f", {unverified} unverified" if unverified else "")
          + f", {new} new-chunks-only, {info} info)")
    return 0 if ok else 1


def main():
    utf8_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--update", action="store_true", help="first baseline, or refresh one that differs only in info")
    ap.add_argument("--accept", metavar="REASON", help="fold the current new-chunks-only differences into the baseline, with this reason")
    ap.add_argument("--force-terrain", metavar="REASON", help="with --update: also fold in continuity-breaking differences (loud; recorded as terrain)")
    ap.add_argument("--golden", action="store_true", help="also generate and compare the golden areas (tier 3, uses Chunky)")
    ap.add_argument("--static", action="store_true", help="only tier 0: no server, seconds (data findings judged by kind)")
    ap.add_argument("--baseline", default=BASELINE, help="baseline file (default tools/worldgen_baseline.json)")
    ap.add_argument("--seed", default="worldgen", help="world seed (the baseline was made with 'worldgen')")
    ap.add_argument("--keep-world", action="store_true")
    ap.add_argument("--no-sync", action="store_true", help="skip packwiz-installer (check what's already installed)")
    ap.add_argument("--xmx", default="6G")
    ap.add_argument("--timeout", type=int, default=1800, help="seconds to allow for the fingerprinting itself")
    ap.add_argument("--out", help="JSON report path (default tools/.data/reports/worldgen-<timestamp>.json)")
    args = ap.parse_args()
    for flag in ("accept", "force_terrain"):
        if getattr(args, flag) is not None and not getattr(args, flag).strip():
            raise SystemExit(f"--{flag.replace('_', '-')} needs a reason")
    if args.force_terrain and not args.update:
        raise SystemExit('--force-terrain only goes with --update: tools/.venv/Scripts/python tools/worldgen_check.py --update --force-terrain "<reason>"')
    if args.accept and args.update:
        raise SystemExit("--accept and --update are separate: --accept takes new-chunks-only additions, --update the rest")
    if args.static and (args.update or args.accept or args.golden):
        raise SystemExit("--static runs tier 0 only: it can't --update, --accept or --golden")
    writing = args.update or args.accept

    t_start = time.time()
    timings = {}
    base = load_baseline(args.baseline)
    if base is None and not writing:
        raise SystemExit(f"No baseline at {args.baseline}: run with --update --golden to make one")
    if base is not None and base.get("schema") != SCHEMA:
        raise SystemExit(f"{args.baseline} has schema {base.get('schema')}, this tool writes {SCHEMA}")
    if base is not None and base.get("seed") != args.seed:
        raise SystemExit(f"The baseline was made with seed '{base.get('seed')}', not '{args.seed}'")

    if args.static:
        srv = TestServer()
        srv.ensure_installed()
        if not args.no_sync:
            srv.sync_pack()
        f = Findings()
        diff_static(tier0(srv, []), base["tier0"], f, True)
        return finish(f, args, {}, time.time() - t_start)

    job = build_job()
    srv, extra, fatal, golden = run_server(args, job, timings)
    for line in fatal:
        print("  " + line)
    if fatal:
        raise SystemExit("The fingerprint script failed (see above)")
    world_dir = srv.path(WORLD)
    raw = collect(srv.path("local", "worldgen-check"), world_dir, srv.root)
    scale = raw["world_config"]
    if scale.get("generation_modes.horizontal_scale") != H or scale.get("generation_modes.vertical_scale") != V:
        raise SystemExit(f"The world's server.toml has a map radius of {scale.get('generation_modes.horizontal_scale')} x "
                         f"{scale.get('generation_modes.vertical_scale')}, not the 20 m scale {H} x {V}")
    t = time.time()
    golden_areas = golden_fingerprint(world_dir) if golden else None
    if golden:
        timings["golden_read"] = time.time() - t
        os.makedirs(os.path.join(DATA_DIR, "worldgen"), exist_ok=True)
        with open(os.path.join(DATA_DIR, "worldgen", "last-golden.json"), "w", encoding="utf-8") as fh:
            json.dump(golden_record(golden_areas), fh)
    if not args.keep_world:
        shutil.rmtree(world_dir, ignore_errors=True)
    fp, ctx = fingerprint(args.seed, tier0(srv, extra), raw, golden_areas)
    if writing:
        return update(fp, base, ctx, args, timings, time.time() - t_start)
    f = compare(fp, base, ctx)
    return finish(f, args, timings, time.time() - t_start)


if __name__ == "__main__":
    sys.exit(main())
