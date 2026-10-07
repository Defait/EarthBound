"""Static scan of mod jars for what can change world generation, without starting anything.

Two things per mod (and per jar nested inside it with JarJar): a hash of its worldgen-relevant data entries, and
the mixin classes that target world generation code. Used by tools/worldgen_check.py.
"""
import hashlib
import io
import json
import os
import re
import struct
import tomllib
import zipfile

# data/<ns>/<rest> entries that shape generation: worldgen registries, biome and structure modifiers, worldgen tags,
# dimensions, TFC's own data and TFC: Real World's map profiles, structure templates, and the block tags worldgen predicates read.
DATA_RE = re.compile(
    r"^data/(?P<ns>[^/]+)/(?P<rest>"
    r"worldgen/.+|(?:neoforge|forge)/(?:biome_modifier|structure_modifier)/.+|tags/worldgen/.+|dimension/.+|dimension_type/.+"
    r"|tfc/.+|profiles/.+|structure/.+\.nbt|tags/block/(?P<tag>[^/]+)\.json)$")
# Only these data/minecraft/tags/block files matter to worldgen (what carvers and placement predicates read).
WORLDGEN_BLOCK_TAGS = {
    "base_stone_overworld", "base_stone_nether", "overworld_carver_replaceables", "nether_carver_replaceables", "replaceable",
    "replaceable_by_trees", "replaceable_by_mushrooms", "features_cannot_replace", "lush_ground_replaceable",
    "azalea_root_replaceable", "azalea_grows_on", "moss_replaceable", "dripstone_replaceable_blocks", "geode_invalid_blocks",
    "dirt", "sand", "terracotta", "snow_layer_can_survive_on", "snow_layer_cannot_survive_on", "substrate_overworld",
    "leaves", "logs", "saplings", "flowers", "small_flowers", "tall_flowers", "infiniburn_overworld", "underwater_bonemeals",
    "bamboo_plantable_on", "big_dripleaf_placeable_on", "cave_vines", "coral_blocks", "corals", "wall_corals",
    "convertable_to_mud", "mushroom_grow_block", "mineable/pickaxe",
}
# TFC and TFC: Real World are the terrain code: all of their data counts; from any other mod only these data/<ns>/tfc folders do.
TERRAIN_MODS = {"tfc", "tfc_real_world"}
# The pack's own structure code (mod/, docs/lived-in.md): its classes shape what its structures place, so a change to them is a
# new-chunks-only change even when no data changed. Their class bytes are hashed.
STRUCTURE_CODE_MODS = {"pack_world"}
TFC_DATA_DIRS = {"worldgen", "fauna", "climate_range", "deposit"}

# Mixin targets: generation proper vs chunk containers and storage (loading and saving, which don't change what is generated).
GEN_TARGET = re.compile(
    r"^(net\.minecraft\.world\.level\.(levelgen|biome|dimension)\.|net\.minecraft\.world\.level\.chunk\.(ChunkGenerator|ChunkGeneratorStructureState|status\.)"
    r"|net\.minecraft\.server\.level\.WorldGenRegion$|net\.minecraft\.world\.level\.(WorldGenLevel|NoiseColumn|StructureManager)$"
    r"|net\.dries007\.tfc\.world\.|net\.neoforged\.neoforge\.common\.world\.|net\.minecraft\.util\.random\.|net\.minecraft\.util\.RandomSource$"
    r"|com\.gregtechceu\.gtceu\.(api\.data\.worldgen|common\.worldgen|data\.worldgen))")
CHUNK_TARGET = re.compile(r"^net\.minecraft\.(world\.level\.chunk\.|server\.level\.(ChunkMap|ChunkHolder|ServerChunkCache))")


def short_hash(data, n=6):
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha1(data).hexdigest()[:n]


def walk_jar(zf, label, via=None):
    """Yield (label, zipfile, via) for a jar and every JarJar jar nested in it."""
    yield label, zf, via
    for n in zf.namelist():
        if n.startswith("META-INF/jarjar/") and n.endswith(".jar"):
            yield from walk_jar(zipfile.ZipFile(io.BytesIO(zf.read(n))), os.path.basename(n), label)


def mod_identity(zf, label):
    """(modId, version) from the jar's neoforge.mods.toml, or (None, None) for plain libraries."""
    for name in ("META-INF/neoforge.mods.toml", "META-INF/mods.toml"):
        if name not in zf.namelist():
            continue
        try:
            mods = tomllib.loads(zf.read(name).decode("utf-8", "replace")).get("mods", [])
        except tomllib.TOMLDecodeError:
            continue
        if mods and mods[0].get("modId"):
            version = str(mods[0].get("version", ""))
            if version.startswith("${") and "META-INF/MANIFEST.MF" in zf.namelist():
                m = re.search(r"Implementation-Version: (\S+)", zf.read("META-INF/MANIFEST.MF").decode("utf-8", "replace"))
                version = m.group(1) if m else ""
            return mods[0]["modId"], version
    return None, None


def data_category(m):
    """Category label for a matched data entry: '<ns>:<kind>' with the kind trimmed to the registry or folder."""
    ns, rest = m.group("ns"), m.group("rest")
    parts = rest.split("/")
    if parts[0] == "worldgen":
        return f"{ns}:worldgen/{parts[1]}"
    if parts[0] in ("neoforge", "forge"):
        return f"{ns}:{parts[0]}/{parts[1]}"
    if parts[0] == "tags":
        return f"{ns}:tags/worldgen/{parts[2]}" if parts[1] == "worldgen" else f"{ns}:tags/block"
    if parts[0] == "tfc":
        return f"{ns}:tfc/{parts[1]}"
    return f"{ns}:{parts[0]}"


def scan_data(names, read, terrain=False, own=False):
    """{category: [count, hash]} and {path: hash} for the worldgen-relevant data entries among names (read(name) gives the bytes).

    terrain: the jar is TFC or TFC: Real World, where all of data/<ns>/tfc counts, not just the worldgen-related folders.
    own: the pack's own data (kubejs/data), whose block tags (e.g. the ones its structure processors read) count too.
    """
    cats, files = {}, {}
    for name in sorted(names):
        m = DATA_RE.match(name)
        if not m or name.endswith("/"):
            continue
        ns = m.group("ns")
        parts = m.group("rest").split("/")
        if m.group("tag") is not None and not (ns == "minecraft" and m.group("tag") in WORLDGEN_BLOCK_TAGS) and not (own and ns != "minecraft"):
            continue
        if parts[0] == "tfc" and not terrain and (len(parts) < 2 or parts[1] not in TFC_DATA_DIRS):
            continue
        if parts[0] == "structure" and terrain:
            continue    # TFC's templates are its trees (decoration); its worldgen data already covers how they're used
        if parts[0] == "profiles" and ns != "tfc_real_world":
            continue
        h = short_hash(read(name), 8)
        cats.setdefault(data_category(m), []).append((name, h))
        files[name] = h
    out = {cat: [len(items), short_hash("".join(f"{n}={h};" for n, h in items), 10)] for cat, items in sorted(cats.items())}
    return out, files


# ------------------------------------------------------------------ mixins
def _class_targets(data):
    """Targets of the @Mixin annotation in a class file (a small constant-pool and annotation reader)."""
    cp = [None]
    pos = 10
    (count,) = struct.unpack_from(">H", data, 8)
    i = 1
    while i < count:
        tag = data[pos]
        pos += 1
        if tag == 1:
            (n,) = struct.unpack_from(">H", data, pos)
            cp.append(data[pos + 2:pos + 2 + n].decode("utf-8", "replace"))
            pos += 2 + n
        elif tag in (3, 4, 9, 10, 11, 12, 17, 18):
            cp.append(None)
            pos += 4
        elif tag in (5, 6):
            cp.extend([None, None])
            pos += 8
            i += 1
        elif tag in (7, 8, 16, 19, 20):
            cp.append(None)
            pos += 2
        elif tag == 15:
            cp.append(None)
            pos += 3
        else:
            raise ValueError(f"constant pool tag {tag}")
        i += 1
    pos += 6
    (n,) = struct.unpack_from(">H", data, pos)
    pos += 2 + 2 * n

    def attrs(pos):
        (n,) = struct.unpack_from(">H", data, pos)
        pos += 2
        out = []
        for _ in range(n):
            nm, ln = struct.unpack_from(">HI", data, pos)
            out.append((cp[nm], pos + 6, ln))
            pos += 6 + ln
        return out, pos

    def skip_members(pos):
        (n,) = struct.unpack_from(">H", data, pos)
        pos += 2
        for _ in range(n):
            pos += 6
            _, pos = attrs(pos)
        return pos

    def value(pos):
        tag = chr(data[pos])
        pos += 1
        if tag in "BCDFIJSZs":
            (ci,) = struct.unpack_from(">H", data, pos)
            return (cp[ci] if tag == "s" else None), pos + 2
        if tag == "e":
            return None, pos + 4
        if tag == "c":
            (ci,) = struct.unpack_from(">H", data, pos)
            return cp[ci], pos + 2
        if tag == "@":
            _, vals, pos = annotation(pos)
            return vals, pos
        out = []
        (n,) = struct.unpack_from(">H", data, pos)
        pos += 2
        for _ in range(n):
            v, pos = value(pos)
            out.append(v)
        return out, pos

    def annotation(pos):
        ti, np_ = struct.unpack_from(">HH", data, pos)
        pos += 4
        vals = {}
        for _ in range(np_):
            (nm,) = struct.unpack_from(">H", data, pos)
            v, pos = value(pos + 2)
            vals[cp[nm]] = v
        return cp[ti], vals, pos

    pos = skip_members(pos)  # fields
    pos = skip_members(pos)  # methods
    class_attrs, _ = attrs(pos)
    targets = []
    for name, apos, _ in class_attrs:
        if name not in ("RuntimeInvisibleAnnotations", "RuntimeVisibleAnnotations"):
            continue
        (n,) = struct.unpack_from(">H", data, apos)
        apos += 2
        for _ in range(n):
            type_, vals, apos = annotation(apos)
            if type_ == "Lorg/spongepowered/asm/mixin/Mixin;":
                for key in ("value", "targets"):
                    for t in vals.get(key) or []:
                        if isinstance(t, str):
                            targets.append(t[1:-1].replace("/", ".") if t.startswith("L") and t.endswith(";") else t)
    return targets


def scan_mixins(zf):
    """{"gen": {class: "targets#hash"}, "chunk": [count, hash]} for the server-side mixins of a jar."""
    names = set(zf.namelist())
    configs = {n for n in names if n.endswith(".json") and "/" not in n and not n.startswith("pack.")}
    if "META-INF/neoforge.mods.toml" in names:
        text = zf.read("META-INF/neoforge.mods.toml").decode("utf-8", "replace")
        configs |= {c for c in re.findall(r'\[\[mixins\]\]\s*config\s*=\s*"([^"]+)"', text) if c in names}
    gen, chunk = {}, []
    for cfg in sorted(configs):
        try:
            conf = json.loads(re.sub(r",(\s*[\]}])", r"\1", zf.read(cfg).decode("utf-8", "replace")))
        except ValueError:
            continue
        if not isinstance(conf, dict) or "package" not in conf:
            continue
        # "client" mixins never load on a server or in world generation
        for cls in [f"{conf['package']}.{m}" for side in ("mixins", "server") for m in conf.get(side, [])]:
            path = cls.replace(".", "/") + ".class"
            if path not in names:
                continue
            data = zf.read(path)
            try:
                targets = _class_targets(data)
            except (ValueError, struct.error):
                continue
            h = short_hash(data)
            if any(GEN_TARGET.match(t) for t in targets):
                gen[cls] = ",".join(sorted(set(targets))) + "#" + h
            elif any(CHUNK_TARGET.match(t) for t in targets):
                chunk.append(f"{cls}#{h}")
    out = {}
    if gen:
        out["gen"] = dict(sorted(gen.items()))
    if chunk:
        out["chunk"] = [len(chunk), short_hash("".join(sorted(chunk)), 10)]
    return out


def scan_jars(mods_dir, skip=(), detail_limit=60):
    """Scan every jar in mods_dir (minus the file names in skip) and the jars nested in them.

    Returns {key: record}; key is the modId (or the jar's name for libraries). A record holds the jar's file name,
    version, parent jar for nested ones, and, only when it has any, "data" ({category: [count, hash]}), "files" (a
    hash per data file, for jars with at most detail_limit of them) and "mixins" ({"gen": ..., "chunk": ...}).
    """
    out = {}
    for fname in sorted(os.listdir(mods_dir)):
        if not fname.endswith(".jar") or fname in skip:
            continue
        with zipfile.ZipFile(os.path.join(mods_dir, fname)) as top:
            for label, zf, via in walk_jar(top, fname):
                mod_id, version = mod_identity(zf, label)
                key = mod_id or os.path.splitext(label)[0]
                if key in out:
                    key = f"{key} (in {via or fname})"
                rec = {"file": label}
                if version:
                    rec["version"] = version
                if via:
                    rec["via"] = via
                data, files = scan_data(zf.namelist(), zf.read, mod_id in TERRAIN_MODS)
                if data:
                    rec["data"] = data
                    if len(files) <= detail_limit:
                        rec["files"] = {n: h[:6] for n, h in files.items()}
                mixins = scan_mixins(zf)
                if mixins:
                    rec["mixins"] = mixins
                if mod_id in STRUCTURE_CODE_MODS:
                    classes = sorted(n for n in zf.namelist() if n.endswith(".class"))
                    rec["classes"] = short_hash(b"".join(n.encode() + zf.read(n) for n in classes), 10)
                out[key] = rec
    return out
