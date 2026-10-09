"""Reuse generated test worlds (and reports) while the pack's generation inputs are unchanged.

Usage (from the repo root):
    tools/.venv/Scripts/python tools/worldcache.py list
    tools/.venv/Scripts/python tools/worldcache.py key [--at REV]
    tools/.venv/Scripts/python tools/worldcache.py prune [--max-gb 20]

What a fresh test world holds depends on the pack's server-side files (mods/, config/, defaultconfigs/, kubejs/),
pack.toml's [versions] and the run's own settings (seed, place, radius ...). The pack key hashes exactly those with
git's blob ids, so the working tree and a commit give the same key for the same content: `--at HEAD` finds what was
generated before an uncommitted change. Left out, because a generated world can't depend on them: quests, client
assets and scripts, recipes, advancements, loot tables and loot modifiers (a chest keeps its table's id and rolls it
when opened). `pregen.py` and `structure_mods/measure.py` look here before booting the server and store what they
generate. Entries live in tools/.data/worlds/<tool>-<key>/, and the least recently used go once the cache passes
20 GB (WORLDCACHE_MAX_GB). A run is stored only when the test server held exactly the pack: synced, no jar or dev
script copied in by hand, and the pack unchanged while it ran.

`key` prints the pack key, for ad-hoc scripts that want to name their own before/after output by it.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import tomllib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mclib.paths import DATA_DIR, REPO, SERVER_DIR, utf8_console  # noqa: E402

CACHE_DIR = os.path.join(DATA_DIR, "worlds")
FORMAT = 1          # bump when the same inputs would make a tool write something different
INPUT_DIRS = ["mods", "config", "defaultconfigs", "kubejs"]
EXCLUDE = re.compile(r"^(?:config/ftbquests/|kubejs/(?:assets|client_scripts)/"
                     r"|kubejs/data/[^/]+/(?:loot_tables?|loot_modifiers|recipes?|advancements?)/)")
MAX_GB = float(os.environ.get("WORLDCACHE_MAX_GB", "20"))


def _git(*args, stdin=None):
    r = subprocess.run(["git", *args], cwd=REPO, input=stdin, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise SystemExit(f"git {' '.join(args[:3])} failed: {r.stderr.strip()}")
    return r.stdout


def pack_inputs(rev=None):
    """Sorted (path, git blob id) of the pack files a world can depend on, in the working tree or at a revision."""
    if rev:
        files = []
        for entry in _git("ls-tree", "-r", "-z", "--full-tree", rev, "--", *INPUT_DIRS).split("\0"):
            if entry:
                meta, path = entry.split("\t", 1)
                files.append((path, meta.split()[2]))
    else:
        paths = [p for p in _git("ls-files", "-co", "--exclude-standard", "-z", "--", *INPUT_DIRS).split("\0")
                 if p and not EXCLUDE.match(p) and os.path.isfile(os.path.join(REPO, p))]
        files = list(zip(paths, _git("hash-object", "--stdin-paths", stdin="\n".join(paths)).split()))
    return sorted((p, b) for p, b in files if not EXCLUDE.match(p))


def pack_versions(rev=None):
    text = _git("show", f"{rev}:pack.toml") if rev else open(os.path.join(REPO, "pack.toml"), encoding="utf-8").read()
    return tomllib.loads(text).get("versions", {})


def pack_key(rev=None):
    h = hashlib.sha256(json.dumps({"format": FORMAT, "versions": pack_versions(rev)}, sort_keys=True).encode())
    for path, blob in pack_inputs(rev):
        h.update(f"{path}\0{blob}\n".encode())
    return h.hexdigest()


def entry_name(tool, params, pkey):
    s = json.dumps({"tool": tool, "params": params, "pack": pkey}, sort_keys=True)
    return f"{tool}-{hashlib.sha256(s.encode()).hexdigest()[:16]}"


def _read_meta(d):
    with open(os.path.join(d, "meta.json"), encoding="utf-8") as f:
        return json.load(f)


def _write_meta(d, meta):
    with open(os.path.join(d, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)


def lookup(tool, params, pkey):
    """The cached entry (folder, meta) for these settings and pack key, or None."""
    d = os.path.join(CACHE_DIR, entry_name(tool, params, pkey))
    if not os.path.exists(os.path.join(d, "meta.json")):
        return None
    meta = _read_meta(d)
    meta["last_used"] = time.time()
    _write_meta(d, meta)
    return d, meta


def restore(entry, dest):
    """Copy a cached world folder or report to dest (replacing it)."""
    d, meta = entry
    src = os.path.join(d, meta["item"])
    if os.path.isdir(src):
        shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(src, dest)
    else:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(src, dest)


def describe(meta):
    rev = (meta.get("git_head") or "?")[:7] + (" + uncommitted changes" if meta.get("dirty") else "")
    return f"made {time.strftime('%Y-%m-%d %H:%M', time.localtime(meta['created']))} with the pack at {rev}"


def stray_server_files(server_dir=SERVER_DIR):
    """Jars and dev scripts on the test server that neither the pack sync nor a tool's per-run extras put there."""
    def tracked(name):
        p = os.path.join(server_dir, name)
        return set(json.load(open(p))) if os.path.exists(p) else set()
    expected = tracked(".extra-mods.json") | tracked(".dev-scripts.json")
    pw = os.path.join(server_dir, "packwiz.json")
    if os.path.exists(pw):
        for k, v in json.load(open(pw, encoding="utf-8")).get("cachedFiles", {}).items():
            expected.add(v.get("cachedLocation") or k)
    expected = {os.path.normpath(p) for p in expected}
    stray = []
    for sub, keep in (("mods", lambda f: f.endswith(".jar")),
                      (os.path.join("local", "kubejs", "local_server_scripts"), lambda f: True),
                      (os.path.join("local", "kubejs", "local_startup_scripts"), lambda f: True)):
        root = os.path.join(server_dir, sub)
        for dirpath, _, names in os.walk(root):
            for n in names:
                rel = os.path.normpath(os.path.relpath(os.path.join(dirpath, n), server_dir))
                if keep(n) and rel not in expected:
                    stray.append(rel.replace(os.sep, "/"))
    return sorted(stray)


def _size(path):
    if os.path.isfile(path):
        return os.path.getsize(path)
    return sum(os.path.getsize(os.path.join(dp, n)) for dp, _, ns in os.walk(path) for n in ns)


def store(tool, params, pkey, src, meta=None):
    """Keep src (a world folder or report file) under the pack key the run started with. Returns the entry or None."""
    stray = stray_server_files()
    if stray:
        print(f"Not cached: the test server holds files the pack doesn't ({', '.join(stray[:5])}); a sync without them fixes it.")
        return None
    if pack_key() != pkey:
        print("Not cached: the pack changed while the server ran.")
        return None
    d = os.path.join(CACHE_DIR, entry_name(tool, params, pkey))
    tmp = d + ".part"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    item = os.path.basename(os.path.normpath(src))
    if os.path.isdir(src):
        shutil.copytree(src, os.path.join(tmp, item), ignore=shutil.ignore_patterns("session.lock"))
    else:
        shutil.copy2(src, os.path.join(tmp, item))
    head = _git("rev-parse", "HEAD").strip()
    now = time.time()
    _write_meta(tmp, {**(meta or {}), "tool": tool, "params": params, "pack_key": pkey, "item": item,
                      "git_head": head, "dirty": pkey != pack_key(head), "created": now, "last_used": now,
                      "bytes": _size(os.path.join(tmp, item))})
    shutil.rmtree(d, ignore_errors=True)
    os.replace(tmp, d)
    print(f"Cached as {os.path.relpath(d, REPO)}")
    prune()
    return d


def entries():
    if not os.path.isdir(CACHE_DIR):
        return []
    out = []
    for name in os.listdir(CACHE_DIR):
        d = os.path.join(CACHE_DIR, name)
        if not name.endswith(".part") and os.path.exists(os.path.join(d, "meta.json")):
            out.append((d, _read_meta(d)))
    return sorted(out, key=lambda e: e[1]["last_used"], reverse=True)


def prune(max_gb=MAX_GB):
    """Remove the least recently used entries until the cache fits in max_gb."""
    budget, kept = max_gb * 1024 ** 3, 0
    for d, meta in entries():
        kept += meta.get("bytes", 0)
        if kept > budget:
            shutil.rmtree(d, ignore_errors=True)
            print(f"Pruned {os.path.basename(d)} ({describe(meta)})")


def main():
    utf8_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="cached entries, most recently used first")
    k = sub.add_parser("key", help="print the pack key")
    k.add_argument("--at", metavar="REV", help="the pack as committed at a git revision (default: the working tree)")
    p = sub.add_parser("prune", help="drop the least recently used entries")
    p.add_argument("--max-gb", type=float, default=MAX_GB)
    args = ap.parse_args()

    if args.cmd == "key":
        print(pack_key(args.at))
    elif args.cmd == "prune":
        prune(args.max_gb)
    else:
        now, head = pack_key(), pack_key("HEAD")
        total = 0
        for d, meta in entries():
            total += meta.get("bytes", 0)
            tag = "  [working tree]" if meta["pack_key"] == now else "  [HEAD]" if meta["pack_key"] == head else ""
            settings = ", ".join(f"{k}={v}" for k, v in meta["params"].items() if v is not None and k != "script")
            print(f"{os.path.basename(d)}  {meta.get('bytes', 0) / 1024 ** 2:7.0f} MB  {describe(meta)}{tag}\n    {settings}")
        print(f"{total / 1024 ** 3:.1f} GB in {CACHE_DIR} (cap {MAX_GB:g} GB)")


if __name__ == "__main__":
    main()
