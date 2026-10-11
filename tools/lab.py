"""Worldgen feature lab: one test server that stays up, so worldgen features can be tried in seconds.

Usage (from the repo root; `lab.py` below is `tools/.venv/Scripts/python tools/lab.py`):
    lab.py start [--xmx 6G] [--idle-minutes 30] [--fresh] [--no-sync] [--keep-features] [--blank ID ...] [--seed-from-server]
    lab.py status | stop | restart
    lab.py check [PATH ...] [--data DIR]
    lab.py place FEATURE --biome BIOME (--place LAT,LON | --center X,Z) [--chunks N] [--radius R] [--no-rarity] [--seed S]
                 [--step 8] [--data DIR] [--neighbours N] [--first N] [--batch N] [--max-ring N] [--timeout S] [--json]
    lab.py where FEATURE [--biome BIOME] (--place LAT,LON | --center X,Z) [--chunks N] [--radius R] [--terrain]
                 [--bands 0-25,26-60,...] [--band-at middle|corner] [same options as place]
    lab.py structure STRUCTURE (--place LAT,LON | --center X,Z) [--count 3] [--spacing 160] [--seed S] [--json]
    lab.py ids KIND [PATTERN]          ids in the lab's registries (biome, structure, placed_feature, ...)
    lab.py log [-n 40]                 tail of the lab's console;  lab.py job KIND '{json}' / cmd 'command': development

What it is. Generating a window to find out whether a worldgen change loads, what it places and where costs a
server boot and minutes of chunk generation per attempt. The lab is one headless NeoForge server in tools/.lab (its own
folder and ports: 25588, and 8188 for the pack it is synced from; tools/.server and the other tools are untouched, and
both can be up at once) that boots once, stays up, and answers small jobs in seconds. It is a fixed-seed world like
pregen.py's (seed 'pregen', the pack's 20 m scale, so positions are the same as in the other tools' worlds); chunks are
generated as jobs ask for them (about 90 per second, in parallel) and kept on disk. Its numbers are ESTIMATES: one real
generation (pregen.py) still decides, but the lab tells in seconds whether an attempt is worth one.

How it works. `start` snapshots the working tree's pack files to tools/.lab/pack-src (so the packwiz serve that feeds the
installer never writes into the repo's index.toml), syncs the lab from it, boots the server detached (it outlives this
command and the shell; stdout goes to tools/.lab/lab-console.log) and waits until its dev-only KubeJS script (tools/lab.js,
in the lab's local/kubejs/local_server_scripts) is polling. Jobs travel as files: this command writes lab/job.json into
the lab's game folder, the script runs it on a server tick and writes lab/result-<id>.json, so nothing depends on the
process that started the server. Editing tools/lab.js needs no restart: every command first compares it with the copy
the lab runs and, when it differs, copies it over and has the script reload itself (a second; KubeJS does not allow
eval). The lab stops itself after --idle-minutes (30) without a job, `stop` is a job too, and only one lab runs at a time.
Commands that need the lab say so when it is down; they do not start it.

What needs `restart`, and what does not. The registries are built at boot from the mods, kubejs/startup_scripts (blocks
are registered there), the configs and the worldgen data other than features (biomes, tags, structures, pools, and the
pack_world jar). `status` records what the lab booted with and says when the working tree has moved on, `check` says
"needs lab.py restart" when an unknown block, feature type or placement type is mentioned by a boot-time file that
changed since. Placed and configured features are read from the disk for every job (the placed feature, the configured
features and placed features it names, recursively: the disk version wins, ids without a file resolve from the
registry), so editing those never needs a restart. --data DIR does the same for a staged build root (it holds kubejs/data).

Clean terrain. The pack's own placed features (kubejs/data/pack/worldgen/placed_feature) are swapped for no-ops in the
lab's data at boot (--keep-features leaves them, --blank ID adds more), so a fresh chunk holds none of what is being
tuned and every attempt starts from the same terrain; `status` says how many are blanked. Each attempt writes into the
live chunks with NeoForge's block-snapshot capture on (no neighbour updates, every write recorded), reads what changed,
and puts every block back in reverse order; the report says how many positions differ afterwards (it should be 0).
Anything already in the chunks that the feature also writes is reported separately ("already there"), never counted.

check: decodes worldgen JSON (configured and placed features, structures, structure sets, template pools, processor
  lists, biomes) with the game's own codecs against the lab's registries, a file together with every file it names, so
  an error is reported against the file that has it; exit code 1 on any. About a second for the whole pack.
place: finds the --chunks nearest chunks of the biome around the centre (--place LAT,LON on the pack's map or --center
  X,Z; --radius R limits it to the square of half-width R blocks and then, unless --chunks is given, takes every chunk
  of it), and runs the placed feature in each the way chunk decoration does (the placement modifiers pick the positions,
  one seeded random stream per chunk, --seed varies it). Reports: the chunks, how many positions passed each modifier,
  how many reached the feature and how many times it placed something, per block kind written (net of writes that put a
  block back as it was) the blocks, the chunks and columns it covers, its y range, what it replaced, vertical runs, the
  six neighbours of the blocks by block id with minecraft:air, cave_air and minecraft:water called out (and where they
  touch), the first positions, and the density per 1,000 chunks and per km2 (1 block = 1 m, and the 20 m-per-block map
  design.md's numbers use). --no-rarity drops the top-level rarity filters so a rare feature's shape can be looked at, and
  says by what factor that inflates the counts. A feature that places nothing says which modifier removed the positions.
  Big windows are processed in batches (--batch, default 500 chunks) so memory stays bounded.
where: only the placement modifiers: how many chunks and positions pass each, without placing. Chunkless by default: the
  modifiers that need terrain (heightmap, block predicates ...) are not evaluated and the report says where it stopped;
  TFC's ridge distance and the biome lookups do not need chunks, so tens of thousands of chunks take a second.
  --terrain generates the chunks and evaluates everything. --bands counts the chunks in tfc:ocean_ridge distance ranges.
structure: generates a structure of any mod (underwater_village:tower, hopo:underwater/underwater_small_ruins ...; the
  registry's, so after a change to structure data or the pack_world jar `restart`) at --count spots in a row, places it
  like /place does (the pack_world structure skin runs), and reads the pieces' boxes back: blocks by id, vanilla blocks
  left, vanilla water, TFC fluid and air cells, containers with their loot tables; then removes it and what it spawned.

What the lab cannot see (fidelity gaps; see also the README). It places on the live level, not inside a worldgen region
(WorldGenRegion): no write-radius limit, and the neighbours are fully generated. Features of later decoration steps
(vegetation, top-layer changes) already ran on the lab's terrain, real generation runs them after yours (a chimney can
replace turtle grass here, where there it is the grass that avoids the chimney). The _WG heightmaps become their live
twins (same test, kept up to date by the chunk) and the biome filter is dropped; both are listed in the report. Writes
that do not go through Level.setBlock (OreFeature writes into chunk sections) are neither seen nor restored. Lighting,
fluid ticks and block updates are not simulated. Random streams differ from real generation's, so counts are statistical:
a few hundred chunks give a few percent of noise on common features, and rare ones need --no-rarity or a bigger window.

Checked against the generated windows behind docs/design.md's *Deep sea* numbers (the lab's chunks of the same biome in
the same window, one run each; real numbers from the census of those worlds):
  nodule_field, 9,409 deep_ocean chunks at 12,-135:  columns topped by nodule beds 11.31% (real 11.32%), blocks 688,840 (715,354, -3.7%)
  crust_patch, 9,216 ridge chunks at 631600,-75200:  blocks 69,926 (70,061, -0.2%), columns 26,722 (26,642) = 0.63% of the window's
  vent_field: 0.95 fields expected per window (--no-rarity gives 286 for the rarity of 1/300; real 2); per field 62 chimney and
    78 mound blocks (real, from two fields: 58 and 55); next to the chimneys 0.02% air, never minecraft:water
  ridge distance bands 0-25, 26-60, 61-130, 131-300 in the 1,536 square: 242, 330, 672, 1,508 chunks (the markers of the real
    run counted 273, 368, 722, 1,570: chunks that held a marker, and a marker feature spills over chunk edges)
  arc_vent_field, 6,515 arc chunks: 15 to 21 fields (real 16), but 9.5 columns and 34 chimney blocks per field against the real
    7.1 and 22. Not explained for certain: in the real world the chimneys stand on bare mud among floors already covered by coral,
    which looks like tries that landed on coral failing there (a real-generation heightmap that does not see the reef), where the
    lab's live heightmaps put the chimney on top of the coral instead. Treat the size of a vent field on a reef as unknown.
The terrain itself is the real one: 296 of 300 random columns of the ridge window and 268 of 300 of the deep-ocean window have the
same top block and height as the generated worlds (of the 32 that differ in the deep-ocean window 31 hold nodule beds in the real
world; of the 4 in the ridge window 3 differ in a rock type or the height of a spike, about 1% of columns).
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

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
from mclib.paths import REPO, utf8_console  # noqa: E402
from mclib.server import DONE_RE, TestServer  # noqa: E402

LAB_DIR = os.path.join(TOOLS, ".lab")
WORLD = "world-lab"
SEED = "pregen"
PORT = 25588
PACKWIZ_PORT = 8188
JOB_DIR = os.path.join(LAB_DIR, "lab")                 # the game-folder-relative "lab/" the script reads and writes
STATE = os.path.join(LAB_DIR, "lab-state.json")
CONSOLE = os.path.join(LAB_DIR, "lab-console.log")
SNAPSHOT = os.path.join(LAB_DIR, "pack-src")
OVERLAY = os.path.join(LAB_DIR, "lab-overlay.json")
STUB = os.path.join(TOOLS, "lab.js")
SCRIPT_DEST = os.path.join(LAB_DIR, "local", "kubejs", "local_server_scripts", "lab.js")
JVM_MARK = "-Dpack.lab=1"                              # on the java command line, so a lab process can be told from the test server's
IDLE_MINUTES = 30


# ------------------------------------------------------------------ small helpers
def ints(v):
    """KubeJS writes whole numbers as 10527.0; turn them back into ints."""
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, list):
        return [ints(x) for x in v]
    if isinstance(v, dict):
        return {k: ints(x) for k, x in v.items()}
    return v


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    for attempt in range(40):          # the lab may have the old file open for a moment (Windows)
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.05)
    os.replace(tmp, path)


def file_digest(path):
    try:
        size = os.path.getsize(path)
        if size > 16 * 1024 * 1024:
            return f"{size}:{os.stat(path).st_mtime_ns}"
        with open(path, "rb") as f:
            return hashlib.sha1(f.read()).hexdigest()
    except OSError:
        return None


def pid_alive(pid):
    if not pid:
        return False
    if os.name == "nt":
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, int(pid))      # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
        k32.CloseHandle(h)
        return bool(ok) and code.value == 259             # STILL_ACTIVE
    try:
        os.kill(int(pid), 0)
    except OSError:
        return False
    return True


def lab_java_pids():
    """pids of java processes started by this tool (they carry -Dpack.lab=1)."""
    if os.name != "nt":
        r = subprocess.run(["pgrep", "-f", JVM_MARK], capture_output=True, text=True)
        return [int(x) for x in r.stdout.split()]
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='java.exe'\" | Where-Object { $_.CommandLine -like '*" + JVM_MARK +
          "*' } | ForEach-Object { $_.ProcessId }")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True)
    return [int(x) for x in r.stdout.split()]


def kill_tree(pid):
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        try:
            os.kill(int(pid), 9)
        except OSError:
            pass


def fmt_s(seconds):
    seconds = int(seconds)
    if seconds < 90:
        return f"{seconds} s"
    if seconds < 5400:
        return f"{seconds // 60} min {seconds % 60} s"
    return f"{seconds // 3600} h {seconds % 3600 // 60} min"


# ------------------------------------------------------------------ what the lab booted from
def _walk(root, rel_dir, exclude=None):
    out = {}
    base = os.path.join(root, *rel_dir.split("/"))
    for dp, dns, fns in os.walk(base):
        for fn in fns:
            full = os.path.join(dp, fn)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if exclude and exclude(rel):
                continue
            out[rel] = file_digest(full)
    return out


FEATURE_FILE = re.compile(r"^kubejs/data/[^/]+/worldgen/(?:configured_feature|placed_feature)/")
WORLDGEN_DATA = re.compile(r"^kubejs/data/[^/]+/(?:worldgen/|tags/worldgen/|structure/)")


def fingerprint(root=REPO):
    """{group: {path: digest}} of the files the lab's registries are built from (boot-time) plus two groups it reads as it goes.

    restart groups: mods, versions (pack.toml's [versions]), startup_scripts, kubejs_config, config, defaultconfigs.
    informational: data_features (read from the disk by every job, never needs a restart) and data_worldgen (biomes, tags,
    structures ...: the lab's world was generated with what it booted with).
    """
    g = {}
    g["mods"] = {rel: d for rel, d in _walk(root, "mods").items()}
    try:
        with open(os.path.join(root, "pack.toml"), "rb") as f:
            v = tomllib.load(f).get("versions", {})
    except OSError:
        v = {}
    g["versions"] = {f"pack.toml:{k}": str(x) for k, x in sorted(v.items())}
    g["startup_scripts"] = _walk(root, "kubejs/startup_scripts", lambda r: r.endswith("jsconfig.json"))
    g["kubejs_config"] = _walk(root, "kubejs/config", lambda r: r.endswith(("probe-settings.json", "villager_trades.json")))   # trades change often and shape no worldgen
    g["config"] = _walk(root, "config", lambda r: r.startswith("config/ftbquests/"))
    g["defaultconfigs"] = _walk(root, "defaultconfigs")
    data = _walk(root, "kubejs/data")
    g["data_features"] = {r: d for r, d in data.items() if FEATURE_FILE.match(r)}
    g["data_worldgen"] = {r: d for r, d in data.items() if WORLDGEN_DATA.match(r) and not FEATURE_FILE.match(r)}
    return g


RESTART_GROUPS = ["mods", "versions", "startup_scripts", "kubejs_config", "config", "defaultconfigs"]
GROUP_TEXT = {
    "mods": "mods", "versions": "pack versions", "startup_scripts": "kubejs/startup_scripts (blocks and items are registered there)",
    "kubejs_config": "kubejs/config", "config": "config", "defaultconfigs": "defaultconfigs",
    "data_features": "feature files (read from the disk by every job: no restart)",
    "data_worldgen": "worldgen data other than features (biomes, tags, structures, pools: the lab world was generated with the old ones)",
}


def diff_fingerprint(old, new):
    """{group: [changed paths]} (added, removed or different)."""
    out = {}
    for grp in set(old) | set(new):
        a, b = old.get(grp, {}), new.get(grp, {})
        ch = sorted(p for p in set(a) | set(b) if a.get(p) != b.get(p))
        if ch:
            out[grp] = ch
    return out


# ------------------------------------------------------------------ the lab's process and jobs
class Lab:
    def __init__(self):
        self.state = read_json(STATE)

    # -- liveness
    def pid(self):
        return (self.state or {}).get("pid")

    def alive(self):
        return pid_alive(self.pid())

    def status_file(self):
        return ints(read_json(os.path.join(JOB_DIR, "status.json")))

    def ready(self):
        st = self.status_file()
        return bool(self.alive() and st and st.get("boot_id") == self.state.get("boot_id") and st.get("state") in ("ready",)
                    and time.time() * 1000 - st.get("now", 0) < 60_000)

    # -- jobs
    def _lock(self, timeout=180):
        path = os.path.join(JOB_DIR, ".lock")
        os.makedirs(JOB_DIR, exist_ok=True)
        end = time.time() + timeout
        while True:
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return path
            except FileExistsError:
                other = None
                try:
                    other = int(open(path).read().strip() or 0)
                except (OSError, ValueError):
                    pass
                if (other and not pid_alive(other)) or time.time() - os.path.getmtime(path) > 900:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                    continue
                if time.time() > end:
                    raise SystemExit("Another lab.py command has been using the lab for more than 3 minutes (lab/.lock).")
                time.sleep(0.2)

    def send(self, kind, timeout=600, **payload):
        """Run a job in the lab and return its result dict. Raises SystemExit when the lab is down or dies."""
        if not self.alive():
            raise SystemExit("The lab is not running: start it with tools/.venv/Scripts/python tools/lab.py start")
        lock = self._lock()
        try:
            return self._send(kind, timeout, payload)
        finally:
            try:
                os.remove(lock)
            except OSError:
                pass

    def _send(self, kind, timeout, payload):
        job_id = int(time.time() * 1000)
        for old in os.listdir(JOB_DIR) if os.path.isdir(JOB_DIR) else []:
            if old.startswith("result-"):
                try:
                    os.remove(os.path.join(JOB_DIR, old))
                except OSError:
                    pass
        write_json(os.path.join(JOB_DIR, "job.json"), {"id": job_id, "kind": kind, **payload})
        res_path = os.path.join(JOB_DIR, f"result-{job_id}.json")
        end = time.time() + timeout
        while time.time() < end:
            if os.path.exists(res_path):
                res = read_json(res_path)
                if res is not None:
                    try:
                        os.remove(res_path)
                    except OSError:
                        pass
                    return ints(res)
            if not self.alive():
                raise SystemExit("The lab died while running the job. Last lines of its console:\n" + console_tail(30))
            st = self.status_file() or {}
            if st.get("last_id", 0) >= job_id and st.get("now", 0) > job_id + 3000 and not st.get("busy") and not os.path.exists(res_path):
                raise SystemExit(f"The lab took the {kind} job but wrote no result: its script failed in a way it cannot report. Console:\n" + console_tail(25))
            time.sleep(0.05)
        raise SystemExit(f"The lab did not answer the {kind} job in {timeout} s (it may still be busy: lab.py status, lab.py log).")

    def ensure_script(self):
        """Have the lab run the current tools/lab.js: copy it over the lab's copy and send a reload job when it differs from the loaded one."""
        with open(STUB, "rb") as f:
            h = hashlib.sha1(f.read()).hexdigest()
        if (self.state or {}).get("script_hash") == h:
            return
        check_syntax(STUB)
        before = (self.status_file() or {}).get("reloads", 0)
        os.makedirs(os.path.dirname(SCRIPT_DEST), exist_ok=True)
        shutil.copyfile(STUB, SCRIPT_DEST)
        self.send("reload", timeout=60)
        end = time.time() + 90
        while time.time() < end:
            st = self.status_file() or {}
            if st.get("reloads", 0) > before and st.get("state") == "ready":
                break
            if not self.alive():
                raise SystemExit("The lab died while reloading its script.")
            time.sleep(0.25)
        else:
            raise SystemExit("The lab's script did not come back after a reload (a script error? lab.py log); lab.py restart brings it back.")
        self.state["script_hash"] = h
        write_json(STATE, self.state)

    def run(self, kind, timeout=600, **payload):
        """ensure_script, then the job. Returns the result dict."""
        self.ensure_script()
        return self.send(kind, timeout=timeout, **payload)


def check_syntax(path):
    node = shutil.which("node")
    if not node:
        return
    r = subprocess.run([node, "--check", path], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"{path} has a syntax error (a reload would silence the lab):\n{r.stderr.strip()[:1500]}")


def console_since(offset):
    try:
        with open(CONSOLE, "rb") as f:
            f.seek(offset)
            return f.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def console_tail(n=30):
    try:
        with open(CONSOLE, encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-n:])
    except OSError:
        return "(no console log)"


# ------------------------------------------------------------------ start / stop / status
def snapshot_pack():
    """Copy the working tree's pack files (what packwiz would index) to tools/.lab/pack-src, so the packwiz serve that
    feeds the installer refreshes the index of the copy and never writes into the repo's pack.toml or index.toml."""
    skip = {".git", ".gitattributes", ".gitignore", "tools", "docs", "mod", ".claude", ".github", ".idea", ".vscode", "README.md", "CLAUDE.md",
            "Thumbs.db", "desktop.ini", "packwiz-installer-bootstrap.jar", "packwiz-installer.jar"}
    shutil.rmtree(SNAPSHOT, ignore_errors=True)
    os.makedirs(SNAPSHOT)
    for name in os.listdir(REPO):
        if name in skip or name.startswith("LICENSE") or name.endswith((".zip", ".mrpack")):
            continue
        src = os.path.join(REPO, name)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(SNAPSHOT, name), ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(src, os.path.join(SNAPSHOT, name))


def blank_features(keep, extra):
    """Placed features to swap for no-ops in the lab's world: every placed feature the pack defines in its own namespace
    (kubejs/data/pack/worldgen/placed_feature), so the terrain starts clean of the features being iterated on."""
    ids = set(extra or [])
    if not keep:
        base = os.path.join(REPO, "kubejs", "data", "pack", "worldgen", "placed_feature")
        for dp, dns, fns in os.walk(base):
            for fn in fns:
                if fn.endswith(".json"):
                    rel = os.path.relpath(os.path.join(dp, fn), base).replace(os.sep, "/")[:-5]
                    ids.add("pack:" + rel)
    return sorted(ids)


def write_overlay(blank):
    """Blank placed features (no-op) into the lab's own kubejs/data, over what the sync put there."""
    def rel(ns, path):
        return os.path.join("kubejs", "data", ns, "worldgen", "placed_feature", *path.split("/")) + ".json"

    for rid in read_json(OVERLAY, []):                 # blanked last time, not now: put the pack's file back (or drop the stale blank)
        if rid in blank:
            continue
        ns, path = rid.split(":", 1)
        lab_file, repo_file = os.path.join(LAB_DIR, rel(ns, path)), os.path.join(REPO, rel(ns, path))
        if os.path.exists(repo_file):
            os.makedirs(os.path.dirname(lab_file), exist_ok=True)
            shutil.copy2(repo_file, lab_file)
        elif os.path.exists(lab_file):
            os.remove(lab_file)
    # Each blank gets a configured feature of its own: PlacedFeature is a record, and the game's feature sorter treats equal
    # placed features as one node, so identical blanks in different orders in different biomes would be a "feature order cycle".
    for rid in blank:
        ns, path = rid.split(":", 1)
        cf = os.path.join(LAB_DIR, "kubejs", "data", "pack_lab", "worldgen", "configured_feature", "blank", ns, *path.split("/")) + ".json"
        os.makedirs(os.path.dirname(cf), exist_ok=True)
        with open(cf, "w", encoding="utf-8") as f:
            json.dump({"type": "minecraft:no_op", "config": {}}, f)
        p = os.path.join(LAB_DIR, rel(ns, path))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"feature": f"pack_lab:blank/{ns}/{path}", "placement": []}, f)
    write_json(OVERLAY, blank)


def seed_from_server():
    """A first start downloads NeoForge and the mods (about 500 MB). --seed-from-server copies them from tools/.server instead
    (read-only use of it; do it when no tool is running there), and the normal sync then brings the copy up to date."""
    from mclib.paths import SERVER_DIR
    if os.path.isdir(os.path.join(LAB_DIR, "libraries")) and os.path.isdir(os.path.join(LAB_DIR, "mods")):
        print("tools/.lab already holds NeoForge and the mods; --seed-from-server does nothing.")
        return
    if not os.path.isdir(os.path.join(SERVER_DIR, "libraries")):
        print("tools/.server holds no NeoForge install to copy; the lab downloads its own.")
        return
    print("Copying NeoForge, the mods and the installer state from tools/.server (nothing there is changed)...")
    os.makedirs(LAB_DIR, exist_ok=True)
    for name in ("libraries", ".cache", "mods", "config", "defaultconfigs", "kubejs", "licenses", "easy_npc", "patchouli_books"):
        src, dst = os.path.join(SERVER_DIR, name), os.path.join(LAB_DIR, name)
        if os.path.isdir(src) and not os.path.exists(dst):
            shutil.copytree(src, dst)
    for name in (".installed-neoforge", "eula.txt", "run.bat", "run.sh", "user_jvm_args.txt", "packwiz.json", "packwiz-installer.jar", "packwiz-installer-bootstrap.jar"):
        src, dst = os.path.join(SERVER_DIR, name), os.path.join(LAB_DIR, name)
        if os.path.isfile(src) and not os.path.exists(dst):
            shutil.copy2(src, dst)


def cmd_start(args):
    lab = Lab()
    if lab.alive():
        st = lab.status_file() or {}
        print(f"The lab is already up (pid {lab.pid()}, up {fmt_s(time.time() - lab.state['started'])}, {st.get('served', 0)} jobs served). "
              f"`lab.py status` says whether it needs a restart.")
        return 0
    stray = [p for p in lab_java_pids() if p != lab.pid()]
    if stray:
        print(f"A lab java process is running that lab-state.json does not know (pid {stray}); stop it first: taskkill /PID {stray[0]} /T /F")
        return 1
    t0 = time.time()
    if args.seed_from_server:
        seed_from_server()
    srv = TestServer(root=LAB_DIR, log=print)
    srv.ensure_installed()
    if not args.no_sync:
        snapshot_pack()
        srv.sync_pack(pack_root=SNAPSHOT, port=PACKWIZ_PORT)
    check_syntax(STUB)
    srv.set_extra_mods([])
    srv.set_dev_scripts({"lab.js": STUB})
    blank = blank_features(args.keep_features, args.blank)
    write_overlay(blank)
    world = os.path.join(LAB_DIR, WORLD)
    prev = lab.state or {}
    if args.fresh:
        shutil.rmtree(world, ignore_errors=True)
    elif os.path.isdir(world) and sorted(prev.get("blank", [])) != blank:
        print("Note: the lab world was generated with another set of blanked features than this start uses; "
              "its terrain may hold some of them (use --fresh to regenerate it).")
    srv.write_properties(WORLD, SEED, extra={"server-port": str(PORT), "motd": "worldgen feature lab"})
    fp = fingerprint()
    boot_id = time.strftime("%Y%m%d-%H%M%S")
    os.makedirs(JOB_DIR, exist_ok=True)
    for name in os.listdir(JOB_DIR):
        if name != ".lock":
            try:
                os.remove(os.path.join(JOB_DIR, name))
            except OSError:
                pass
    write_json(os.path.join(JOB_DIR, "config.json"), {"boot_id": boot_id, "idle_minutes": args.idle_minutes})
    offset = os.path.getsize(CONSOLE) if os.path.exists(CONSOLE) else 0
    pid = launch(srv, args.xmx)
    write_json(STATE, {"pid": pid, "started": time.time(), "boot_id": boot_id, "port": PORT, "xmx": args.xmx, "idle_minutes": args.idle_minutes,
                       "fingerprint": fp, "blank": blank, "world": WORLD, "seed": SEED,
                       "script_hash": hashlib.sha1(open(STUB, "rb").read()).hexdigest()})
    lab = Lab()
    print(f"Synced and launched after {time.time() - t0:.0f} s. Booting the lab (pid {pid}, port {PORT}, world {WORLD}, seed '{SEED}')...")
    boot_end = time.time() + args.boot_timeout
    t_boot = time.time()
    done_at = None
    while time.time() < boot_end:
        tail = console_since(offset)
        if not lab.alive():
            print("The lab exited while booting. Last lines of its console:\n" + console_tail(40))
            return 1
        if "Preparing crash report" in tail or "This crash report has been saved" in tail:
            print("The lab crashed while booting (see tools/.lab/crash-reports). Last lines of its console:\n" + console_tail(40))
            kill_tree(pid)
            return 1
        if done_at is None and DONE_RE.search(tail):
            done_at = time.time() - t_boot
        if lab.ready():
            break
        if done_at is not None and time.time() - t_boot - done_at > 45:
            kjs = console_since(offset)
            errs = [ln for ln in kjs.splitlines() if "KubeJS" in ln and ("ERROR" in ln or "lab.js" in ln)][-15:]
            print("The server is up but the lab's script is not polling (45 s). KubeJS said:\n" + "\n".join(errs))
            kill_tree(pid)
            return 1
        time.sleep(0.5)
    else:
        print(f"The lab did not become ready in {args.boot_timeout} s; last lines of its console:\n" + console_tail(40))
        return 1
    print(f"The lab is up: boot {time.time() - t_boot:.0f} s" + (f" (the server reported done after {done_at:.0f} s)." if done_at else "."))
    return 0


def launch(srv, xmx):
    """Start the server detached: it keeps running when this command and its shell are gone. stdout goes to the console log."""
    args_file = "win_args.txt" if os.name == "nt" else "unix_args.txt"
    cmd = [srv.java, f"-Xmx{xmx}", JVM_MARK, f"@libraries/net/neoforged/neoforge/{srv.loader_version}/{args_file}", "nogui"]
    log = open(CONSOLE, "ab")
    log.write(f"\n==== lab start {time.strftime('%Y-%m-%d %H:%M:%S')} ====\n".encode())
    log.flush()
    kwargs = {}
    if os.name == "nt":
        DETACHED_PROCESS, NEW_GROUP, BREAKAWAY = 0x00000008, 0x00000200, 0x01000000
        flags = DETACHED_PROCESS | NEW_GROUP
        try:
            p = subprocess.Popen(cmd, cwd=LAB_DIR, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, creationflags=flags | BREAKAWAY, close_fds=True)
            log.close()
            return p.pid
        except OSError:
            kwargs["creationflags"] = flags      # the shell's job object does not allow breakaway
    else:
        kwargs["start_new_session"] = True
    p = subprocess.Popen(cmd, cwd=LAB_DIR, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, close_fds=True, **kwargs)
    log.close()
    return p.pid


def cmd_stop(args, quiet=False):
    lab = Lab()
    if not lab.alive():
        stray = lab_java_pids()
        if stray:
            for p in stray:
                kill_tree(p)
            print(f"The lab was not in lab-state.json but java pid(s) {stray} carried its mark; killed.")
        elif not quiet:
            print("The lab is not running.")
        return 0
    pid = lab.pid()
    t0 = time.time()
    try:
        lab.send("stop", timeout=30)
    except SystemExit:
        pass
    for _ in range(int(args.timeout * 4)):
        if not pid_alive(pid):
            break
        time.sleep(0.25)
    if pid_alive(pid):
        print("The lab did not stop by itself; killing it.")
        kill_tree(pid)
        time.sleep(1)
    else:
        print(f"The lab stopped after {time.time() - t0:.0f} s.")
    leftover = lab_java_pids()
    if leftover:
        for p in leftover:
            kill_tree(p)
        print(f"Killed leftover lab java pid(s) {leftover}.")
    return 0


def cmd_status(args):
    lab = Lab()
    if not lab.state:
        print("The lab has never been started here (tools/.lab/lab-state.json missing): lab.py start")
        return 1
    if not lab.alive():
        print(f"The lab is down (last pid {lab.pid()}, started {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(lab.state['started']))}). lab.py start")
        stray = lab_java_pids()
        if stray:
            print(f"WARNING: java pid(s) {stray} carry the lab's mark")
        return 1
    st = lab.status_file() or {}
    up = time.time() - lab.state["started"]
    print(f"The lab is up: pid {lab.pid()}, port {lab.state['port']}, up {fmt_s(up)}, {st.get('served', 0)} jobs served"
          + (f", last: {st['last_job']['kind']} ({st['last_job']['ms']} ms)" if st.get("last_job") else ""))
    idle_limit = st.get("idle_limit_s") or lab.state["idle_minutes"] * 60
    print(f"  idle {fmt_s(st.get('idle_s', 0))}; stops itself after {fmt_s(idle_limit)} without a job (in {fmt_s(max(0, idle_limit - st.get('idle_s', 0)))})")
    if st.get("busy"):
        print(f"  busy with a {st['busy']} job")
    print(f"  world {lab.state['world']}, seed '{lab.state['seed']}', {len(lab.state.get('blank', []))} placed features blanked at boot")
    changed = diff_fingerprint(lab.state["fingerprint"], fingerprint())
    need = {g: ch for g, ch in changed.items() if g in RESTART_GROUPS}
    if need:
        print("  RESTART NEEDED (lab.py restart): the working tree changed what the lab loads at boot:")
        for g, ch in need.items():
            print(f"    {GROUP_TEXT[g]}: " + ", ".join(ch[:6]) + (f" ... (+{len(ch) - 6})" if len(ch) > 6 else ""))
    else:
        print("  restart needed: no")
    for g in ("data_worldgen", "data_features"):
        if g in changed:
            ch = changed[g]
            print(f"  changed since boot, {GROUP_TEXT[g]}: " + ", ".join(ch[:4]) + (f" ... (+{len(ch) - 4})" if len(ch) > 4 else ""))
    return 0


def cmd_restart(args):
    cmd_stop(argparse.Namespace(timeout=args.stop_timeout), quiet=True)
    return cmd_start(args)


# ------------------------------------------------------------------ feature files: the disk version wins
WORLDGEN_KINDS = ("configured_feature", "placed_feature", "structure", "structure_set", "template_pool", "processor_list", "biome")
LIVE_HEIGHTMAPS = {"OCEAN_FLOOR_WG": "OCEAN_FLOOR", "WORLD_SURFACE_WG": "WORLD_SURFACE"}


def norm_id(rid):
    return rid if ":" in rid else "minecraft:" + rid


def data_dir(root):
    return os.path.join(root, "kubejs", "data")


def data_path(root, kind, rid):
    ns, path = norm_id(rid).split(":", 1)
    return os.path.join(data_dir(root), ns, "worldgen", kind, *path.split("/")) + ".json"


def load_data(root, kind, rid):
    """The parsed file of a worldgen entry under the data root, or None when there is none."""
    p = data_path(root, kind, rid)
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def classify_path(path, root):
    """(kind, id) of a file under <root>/kubejs/data/<ns>/worldgen/<kind>/..., or None."""
    rel = os.path.relpath(os.path.abspath(path), data_dir(root)).replace(os.sep, "/")
    m = re.match(r"^([^/]+)/worldgen/([^/]+)/(.+)\.json$", rel)
    if not m or m.group(2) not in WORLDGEN_KINDS:
        return None
    return m.group(2), f"{m.group(1)}:{m.group(3)}"


class Inliner:
    """Replaces the ids of configured and placed features that exist as files with the files' JSON, recursively, so the lab tests
    what is on disk and not what the lab booted with. Ids without a file stay ids and resolve from the live registry."""

    def __init__(self, root):
        self.root = root
        self.deps = []                       # (kind, id) of every file inlined, in order

    def _note(self, kind, rid):
        if (kind, rid) not in self.deps:
            self.deps.append((kind, rid))

    def placed(self, doc, trail):
        out = dict(doc)
        f = doc.get("feature")
        if isinstance(f, str):
            rid = norm_id(f)
            cf = load_data(self.root, "configured_feature", rid)
            if cf is not None:
                if ("configured_feature", rid) in trail:
                    raise SystemExit(f"configured feature {rid} refers to itself: {' -> '.join(i for _, i in trail)}")
                self._note("configured_feature", rid)
                out["feature"] = self.configured(cf, trail + [("configured_feature", rid)])
        elif isinstance(f, dict):
            out["feature"] = self.configured(f, trail)
        return out

    def configured(self, doc, trail):
        out = dict(doc)
        if "config" in doc:
            out["config"] = self._walk(doc["config"], trail)
        return out

    def _walk(self, v, trail):
        if isinstance(v, str):
            if v.startswith("#"):
                return v
            rid = norm_id(v)
            pf = load_data(self.root, "placed_feature", rid)
            if pf is not None:
                if ("placed_feature", rid) in trail:
                    raise SystemExit(f"placed feature {rid} refers to itself: {' -> '.join(i for _, i in trail)}")
                self._note("placed_feature", rid)
                return self.placed(pf, trail + [("placed_feature", rid)])
            return v
        if isinstance(v, list):
            return [self._walk(x, trail) for x in v]
        if isinstance(v, dict):
            if "feature" in v and "placement" in v and isinstance(v["placement"], list):
                return self.placed(v, trail)
            return {k: self._walk(x, trail) for k, x in v.items()}
        return v


def rewrite_for_lab(doc, no_rarity):
    """Changes the lab makes to a placed feature before placing it (returned as notes):
    heightmaps OCEAN_FLOOR_WG and WORLD_SURFACE_WG become OCEAN_FLOOR and WORLD_SURFACE (same test, but a finished chunk keeps those two up to
    date while features write, and does not keep the _WG ones); the biome filter goes (the feature is not in any biome's list, the lab picks the
    chunks by biome itself); with no_rarity the top-level rarity filters go and their chances multiply into the inflation factor."""
    notes = []
    counts = {}

    def walk(v):
        if isinstance(v, dict):
            for k, x in list(v.items()):
                if k == "heightmap" and isinstance(x, str) and x in LIVE_HEIGHTMAPS:
                    v[k] = LIVE_HEIGHTMAPS[x]
                    counts[x] = counts.get(x, 0) + 1
                else:
                    walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    walk(doc)
    for k, c in counts.items():
        notes.append(f"heightmap {k} -> {LIVE_HEIGHTMAPS[k]} ({c}x)")
    factor = 1
    kept = []
    for m in doc.get("placement", []):
        t = m.get("type", "")
        if t == "minecraft:biome":
            notes.append("minecraft:biome filter dropped (the lab picks chunks by biome)")
            continue
        if no_rarity and t == "minecraft:rarity_filter":
            factor *= int(m.get("chance", 1))
            notes.append(f"minecraft:rarity_filter 1/{m.get('chance')} dropped")
            continue
        kept.append(m)
    doc["placement"] = kept
    return notes, factor


def resolve_feature(arg, root):
    """FEATURE_ID_OR_FILE -> dict(id, file, doc, deps) with doc the placed feature inlined from disk, or doc None for an id the disk does not hold."""
    path = None
    if os.path.isfile(arg):
        path = os.path.abspath(arg)
    else:
        cand = data_path(root, "placed_feature", arg)
        if os.path.isfile(cand):
            path = cand
        elif os.path.isfile(data_path(root, "configured_feature", arg)):
            raise SystemExit(f"{arg} is a configured feature; place and where need a placed feature (the modifiers decide the positions). "
                             f"Wrap it: a file under kubejs/data/<ns>/worldgen/placed_feature/ with its placement.")
    if path is None:
        return {"id": norm_id(arg), "file": None, "doc": None, "deps": []}
    kind_id = classify_path(path, root)
    if kind_id and kind_id[0] == "configured_feature":
        raise SystemExit(f"{path} is a configured feature; place and where need a placed feature.")
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    inl = Inliner(root)
    inlined = inl.placed(doc, [("placed_feature", kind_id[1])] if kind_id else [])
    return {"id": kind_id[1] if kind_id else os.path.basename(path), "file": path, "doc": inlined, "deps": inl.deps}


# ------------------------------------------------------------------ check
def collect_check_items(paths, root):
    """[(kind, id, file)] for the given files, folders and ids (default: every worldgen file under the data root)."""
    files = []
    if not paths:
        base = data_dir(root)
        for dp, _, fns in os.walk(base):
            for fn in sorted(fns):
                if fn.endswith(".json"):
                    files.append(os.path.join(dp, fn))
    for p in paths:
        if os.path.isdir(p):
            for dp, _, fns in os.walk(p):
                for fn in sorted(fns):
                    if fn.endswith(".json"):
                        files.append(os.path.join(dp, fn))
        elif os.path.isfile(p):
            files.append(p)
        else:
            found = None
            for kind in WORLDGEN_KINDS:
                cand = data_path(root, kind, p)
                if os.path.isfile(cand):
                    found = cand
                    break
            if not found:
                raise SystemExit(f"{p}: no such file, folder or worldgen id under {data_dir(root)}")
            files.append(found)
    items = []
    for f in files:
        ci = classify_path(f, root)
        if ci:
            items.append((ci[0], ci[1], os.path.abspath(f)))
    return items


UNKNOWN_RE = re.compile(r"(?:Unknown registry key in ResourceKey\[[^\]]*\]: |Unknown (?:registry )?element (?:in [^:]*: )?|No key |Unbound holder: )(\S+?)[\s,;\]\)]", re.I)
ID_RE = re.compile(r"\b([a-z0-9_.\-]+:[a-z0-9_./\-]+)\b")


def explain_unknown(msg, lab):
    """For an error about an id the lab does not know: is it a boot-time file that changed since the lab booted? Returns a note or None."""
    ids = set(UNKNOWN_RE.findall(msg + " ")) or set()
    if not ids:
        return None
    changed = diff_fingerprint(lab.state["fingerprint"], fingerprint()) if lab.state else {}
    boot = {g: ch for g, ch in changed.items() if g in RESTART_GROUPS or g == "data_worldgen"}
    if not boot:
        return None
    hits = []
    for g, files in boot.items():
        for rel in files:
            full = os.path.join(REPO, *rel.split("/"))
            try:
                text = open(full, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            for rid in ids:
                if rid in text or rid.split(":", 1)[-1] in text:
                    hits.append(f"{rel} (mentions {rid})")
                    break
    if hits:
        return "needs `lab.py restart`: " + "; ".join(hits[:4]) + " changed since the lab booted"
    listing = ", ".join(sorted({f for ch in boot.values() for f in ch})[:4])
    return f"unknown to the lab; boot-time files changed since it booted ({listing}) so `lab.py restart` may be what is missing"


def cmd_check(args):
    lab = Lab()
    root = os.path.abspath(args.data) if args.data else REPO
    items = collect_check_items(args.paths, root)
    if not items:
        raise SystemExit("nothing to check: no worldgen JSON under " + data_dir(root))
    t0 = time.time()
    jobs, deps_of, files_of = [], {}, {}
    problems = []

    def add(kind, rid, file, extra_trail=()):
        """Queue a file with everything it names that is on disk inlined; returns False when the file cannot even be read."""
        key = (kind, rid)
        if key in files_of:
            return True
        files_of[key] = file
        try:
            with open(file, encoding="utf-8") as f:
                doc = json.load(f)
        except ValueError as e:
            problems.append((file, f"not JSON: {e}"))
            return False
        inl = Inliner(root)
        try:
            if kind == "placed_feature":
                doc = inl.placed(doc, [key])
            elif kind == "configured_feature":
                doc = inl.configured(doc, [key])
        except SystemExit as e:
            problems.append((file, str(e)))
            return False
        deps_of[key] = list(inl.deps)
        jobs.append({"kind": kind, "id": rid, "file": file, "json": json.dumps(doc)})
        for dk, did in inl.deps:           # each nested file is also checked on its own, so an error is reported against the file that has it
            add(dk, did, data_path(root, dk, did))
        return True

    for kind, rid, file in items:
        add(kind, rid, file)
    res = lab.run("check", timeout=args.timeout, items=jobs)
    if not res.get("ok"):
        raise SystemExit("check failed in the lab: " + str(res.get("error")))
    by_key = {(r["kind"], r["id"]): r for r in res["results"]}

    def own_error(key):
        """The error of a file minus what its nested files' errors already say."""
        msg = by_key[key].get("error")
        if not msg:
            return None
        for d in deps_of.get(key, []):
            e = by_key.get(d, {}).get("error")
            if e:
                msg = msg.replace(e, "")
        msg = re.sub(r"\s*;\s*", "; ", msg).strip(" ;\n")
        return msg or None

    failed = skipped = 0
    for key, r in by_key.items():
        if r.get("skipped"):
            skipped += 1
            continue
        msg = own_error(key)
        if not msg:
            continue
        failed += 1
        file = files_of.get(key) or r["file"]
        rel = os.path.relpath(file, REPO) if os.path.abspath(file).startswith(REPO) else file
        print(f"ERROR {rel.replace(os.sep, '/')}: {msg[:1200]}")
        note = explain_unknown(msg, lab)
        if note:
            print(f"      -> {note}")
    for file, msg in problems:
        failed += 1
        rel = os.path.relpath(file, REPO) if os.path.abspath(file).startswith(REPO) else file
        print(f"ERROR {rel.replace(os.sep, '/')}: {msg}")
    print(f"checked {len(items)} files ({len(jobs)} decoded, the ones that name other files with those inlined; {skipped} skipped without a codec) in {time.time() - t0:.1f} s: "
          + (f"{failed} with errors" if failed else "no errors"))
    return 1 if failed else 0


# ------------------------------------------------------------------ place and where
def locate(args):
    """(x, z) block centre from --place LAT,LON or --center X,Z."""
    if args.place:
        lat, lon = (float(v) for v in args.place.split(","))
        x, z = project(lat, lon)
        return x, z, f"{lat},{lon} -> block {x},{z}"
    if args.center:
        x, z = (int(v) for v in args.center.split(","))
        return x, z, f"block {x},{z}"
    raise SystemExit("give --place LAT,LON or --center X,Z (the lab picks chunks of the biome around it)")


def window_box(x, z, radius):
    """Chunk box [cx0, cz0, cx1, cz1] of the square of half-width `radius` blocks around a block position, or None."""
    if not radius:
        return None
    return [(x - radius) // 16, (z - radius) // 16, (x + radius - 1) // 16, (z + radius - 1) // 16]


def prepare(args, lab):
    """Shared by place and where: the default chunk count, and a biome id the lab's registries know."""
    if args.chunks is None:
        args.chunks = 0 if args.radius else 300
    if args.biome:
        import difflib
        known = lab.run("ids", timeout=60, registry="BIOME")["ids"]
        if args.biome not in known:
            near = difflib.get_close_matches(args.biome, known, n=5, cutoff=0.5)
            raise SystemExit(f"unknown biome {args.biome}" + (f"; did you mean {', '.join(near)}?" if near else "") + " (lab.py ids biome lists them)")


def feature_job(args, root, no_rarity):
    feat = resolve_feature(args.feature, root)
    notes, factor = [], 1
    if feat["doc"] is not None:
        notes, factor = rewrite_for_lab(feat["doc"], no_rarity)
        payload = {"id": feat["id"], "json": json.dumps(feat["doc"])}
    else:
        raise SystemExit(f"{args.feature}: no placed feature file under {data_dir(root)} (the lab places what is on disk)")
    return feat, payload, notes, factor


def pct(a, b):
    return f"{100 * a / b:.1f}%" if b else "-"


def n_(x):
    return f"{int(round(x)):,}"


def print_modifiers(mods, terrain_free=None):
    for m in mods:
        extra = ""
        if terrain_free is not None and not terrain_free.get(m["type"], False):
            extra = "  (needs terrain)"
        blocked = f", {n_(m['blocked'])} not evaluated" if m.get("blocked") else ""
        print(f"    {m['type']:<44} {n_(m['in']):>9} in -> {n_(m['out']):>9} out{blocked}{extra}")


def cmd_place(args):
    lab = Lab()
    root = os.path.abspath(args.data) if args.data else REPO
    x, z, where_text = locate(args)
    prepare(args, lab)
    feat, payload, notes, factor = feature_job(args, root, args.no_rarity)
    box = window_box(x, z, args.radius)
    job = {"feature": payload, "biome": args.biome, "center": [x, z], "chunks": args.chunks, "box": box, "max_ring": args.max_ring, "seed": args.seed,
           "step": args.step, "neighbour_cap": args.neighbours, "first_n": args.first, "batch": args.batch, "timeout_ms": args.timeout * 1000}
    t0 = time.time()
    res = lab.run("place", timeout=args.timeout + 60, **job)
    wall = time.time() - t0
    if args.json:
        res["rewrites"] = notes
        res["inflation"] = factor
        print(json.dumps(res, indent=1))
        return 0 if res.get("ok") else 1
    if res.get("decode_error"):
        print(f"ERROR the lab's game cannot decode {feat['file'] or feat['id']}:\n  {res['decode_error'][:1500]}")
        return 1
    if not res.get("ok"):
        print("ERROR " + str(res.get("error")))
        return 1
    print_place(res, feat, args, where_text, notes, factor, wall)
    return 0


def print_place(res, feat, args, where_text, notes, factor, wall):
    nch = res["chunks_found"]
    tm = res["timing"]
    print(f"place {feat['id']} in {args.biome} around {where_text}" + (f", window +-{args.radius} blocks" if args.radius else ""))
    for note in notes:
        print(f"  note: {note}")
    if factor > 1:
        print(f"  --no-rarity: counts below are about {factor}x what real generation gives (divide by {factor}); shapes, neighbours and heights are real")
    print(f"  chunks: {n_(nch)} of {args.biome} (found with {n_(res['biome_lookups'])} biome lookups in {tm['select_ms']} ms), {n_(res['chunks_loaded'])} loaded with their neighbours in {tm['load_ms'] / 1000:.1f} s")
    print("  placement modifiers (positions in -> out, summed over the chunks):")
    print_modifiers(res["modifiers"])
    print(f"  positions that reached the feature: {n_(res['positions_reached'])}; the feature placed something at {n_(res['place_true'])}")
    written = res["written"]
    if not written:
        if not res["positions_reached"]:
            lost = next((m for m in res["modifiers"] if m["in"] and not m["out"]), None)
            why = (f"{lost['type']} removed the last {n_(lost['in'])} position(s)" if lost
                   else "every position was removed before the feature")
            print(f"  WRITTEN: nothing. No position reached the feature: {why} (counts above).")
        else:
            print("  WRITTEN: nothing. The feature ran but no block changed (it found nothing to replace, or only rewrote blocks with themselves).")
    else:
        print(f"  written (net change; {n_(res['identity_writes'])} writes put a block back as it was):")
    area_cols = nch * 256
    for name, w in sorted(written.items(), key=lambda kv: -kv[1]["blocks"]):
        print(f"    {name}: {n_(w['blocks'])} blocks in {n_(w['chunks_with'])} chunks ({pct(w['chunks_with'], nch)} of them), y {w['y'][0]} to {w['y'][1]}, "
              f"top of {n_(w['top_columns'])} columns ({pct(w['top_columns'], area_cols)} of the columns)")
        runs = w.get("runs") or {}
        if runs and max(int(k) for k in runs) > 1:
            cols = sum(runs.values())
            print(f"        {n_(cols)} columns, {sum(int(k) * v for k, v in runs.items()) / cols:.1f} blocks tall on average; columns of N blocks: "
                  + " ".join(f"{k}x{v}" for k, v in sorted(runs.items(), key=lambda kv: int(kv[0]))[:12]))
        rep = sorted(w["replaced"].items(), key=lambda kv: -kv[1])
        print("        replaced: " + ", ".join(f"{k} {n_(v)}" for k, v in rep[:6]) + (" ..." if len(rep) > 6 else ""))
        nb = w["neighbours"]
        faces = sum(nb.values())
        if faces:
            parts = sorted(nb.items(), key=lambda kv: -kv[1])
            callout = []
            for special in ("minecraft:air", "minecraft:cave_air", "minecraft:water"):
                callout.append(f"{special} {n_(nb.get(special, 0))}")
            print(f"        neighbours ({n_(faces)} faces{', sampled' if w['neighbours_sampled'] else ''}): " + ", ".join(f"{k} {n_(v)}" for k, v in parts[:8]) + (" ..." if len(parts) > 8 else ""))
            print("        called out: " + ", ".join(callout))
            for k, ex in sorted(w.get("touch_examples", {}).items()):
                print(f"        {k} touches the block at: " + " ".join(f"({a},{b},{c})" for a, b, c in ex))
        if w.get("preexisting"):
            print(f"        already there before: {n_(w['preexisting'])} blocks of {name} in these chunks (not counted above; the terrain held them anyway)")
        print(f"        first: " + " ".join(f"({a},{b},{c})" for a, b, c in w["first"]))
        per_chunk = w["blocks"] / nch
        cell_km2 = (16 * 20 / 1000) ** 2
        print(f"        density: {per_chunk:.1f} blocks per chunk = {n_(per_chunk * 1000)} per 1,000 chunks; per km2 (1 block = 1 m) {n_(w['blocks'] / (nch * 256) * 1e6)}"
              f"; per km2 of the 20 m map {n_(per_chunk / cell_km2)}" + (f"; divide by {factor} for real generation" if factor > 1 else ""))
    if res["place_true"]:
        per_chunk = res["place_true"] / nch
        cell_km2 = (16 * 20 / 1000) ** 2
        print(f"  placements: {n_(res['place_true'])} in {n_(nch)} chunks = {per_chunk * 1000:.1f} per 1,000 chunks; per km2 (1 block = 1 m) {per_chunk / 256 * 1e6:.1f}; "
              f"per km2 of the 20 m map {per_chunk / cell_km2:.2f}" + (f"; divide by {factor} for real generation" if factor > 1 else ""))
    rs = res["restore"]
    print(f"  terrain restored: {n_(rs['positions'])} positions, {rs['mismatches']} differ" + (f" (first {rs['first_mismatch']})" if rs["mismatches"] else "") +
          ("  <- the lab's terrain is no longer clean: lab.py restart --fresh" if rs["mismatches"] else ""))
    print(f"  time: select {tm['select_ms']} ms, load {tm['load_ms']} ms, place {tm['place_ms']} ms, scan {tm['scan_ms']} ms, restore {tm['restore_ms']} ms"
          + (f", already-there count {tm['preexisting_ms']} ms" if "preexisting_ms" in tm else "") + f"; {wall:.1f} s in all")
    print("  (estimate: placed on the live level, not inside a worldgen region; one real generation still decides)")


def cmd_where(args):
    lab = Lab()
    root = os.path.abspath(args.data) if args.data else REPO
    x, z, where_text = locate(args)
    prepare(args, lab)
    feat, payload, notes, factor = feature_job(args, root, False)
    box = window_box(x, z, args.radius)
    bands = None
    if args.bands:
        bands = [[float(v) for v in b.split("-")] for b in args.bands.split(",")]
    job = {"feature": payload, "biome": args.biome, "center": [x, z], "chunks": args.chunks, "box": box, "max_ring": args.max_ring, "seed": args.seed,
           "step": args.step, "terrain": args.terrain, "bands": bands, "band_at": args.band_at, "batch": args.batch, "timeout_ms": args.timeout * 1000}
    t0 = time.time()
    res = lab.run("where", timeout=args.timeout + 60, **job)
    wall = time.time() - t0
    if args.json:
        res["rewrites"] = notes
        print(json.dumps(res, indent=1))
        return 0 if res.get("ok") else 1
    if res.get("decode_error"):
        print(f"ERROR the lab's game cannot decode {feat['file'] or feat['id']}:\n  {res['decode_error'][:1500]}")
        return 1
    if not res.get("ok"):
        print("ERROR " + str(res.get("error")))
        return 1
    nch = res["chunks_found"]
    tm = res["timing"]
    print(f"where {feat['id']} in {args.biome or 'any biome'} around {where_text}" + (f", window +-{args.radius} blocks" if args.radius else ""))
    for note in notes:
        print(f"  note: {note}")
    print(f"  chunks: {n_(nch)} (found with {n_(res['biome_lookups'])} biome lookups in {tm['select_ms']} ms)")
    print("  placement modifiers (positions in -> out, summed over the chunks, from each chunk's origin as chunk decoration starts):")
    print_modifiers(res["modifiers"], res["terrain_free"] if res.get("stopped_before") else None)
    if res.get("stopped_before"):
        print(f"  stopped before {res['stopped_before']}: it needs terrain, which this run does not touch (--terrain generates the chunks and evaluates it too)")
    print(f"  positions that would reach the feature: {n_(res['positions_reached'])} in {n_(res['chunks_reached'])} chunks"
          + (" (counted up to the stop above)" if res.get("stopped_before") else ""))
    if res.get("bands"):
        b = res["bands"]
        d = b["distance"]
        print(f"  tfc:ocean_ridge distance (blocks from the axis) at the chunk {'corner' if b['at'] == 'corner' else 'middle'}: min {d['min']:.0f}, mean {d['mean']:.0f}, max {d['max']:.0f}")
        for (lo, hi), c in zip(b["ranges"], b["chunks"]):
            print(f"    {lo:g} to {hi:g}: {n_(c)} chunks ({pct(c, nch)})")
    print(f"  time: select {tm['select_ms']} ms" + (f", load {tm['load_ms']} ms" if "load_ms" in tm else "") + f", chain {tm['chain_ms']} ms; {wall:.1f} s in all")
    return 0


ID_KINDS = {"biome": "BIOME", "structure": "STRUCTURE", "structure_set": "STRUCTURE_SET", "placed_feature": "PLACED_FEATURE",
            "configured_feature": "CONFIGURED_FEATURE", "template_pool": "TEMPLATE_POOL", "processor_list": "PROCESSOR_LIST"}


def cmd_ids(args):
    lab = Lab()
    res = lab.run("ids", timeout=60, registry=ID_KINDS[args.kind])
    if not res.get("ok"):
        raise SystemExit(res.get("error"))
    for b in res["ids"]:
        if not args.pattern or args.pattern in b:
            print(b)
    return 0


def cmd_structure(args):
    lab = Lab()
    x, z, where_text = locate(args)
    spots = [[x + i * args.spacing, z] for i in range(args.count)]
    t0 = time.time()
    res = lab.run("structure", timeout=args.timeout + 60, structure=args.structure, spots=spots, seed=args.seed, top_n=args.top, timeout_ms=args.timeout * 1000)
    wall = time.time() - t0
    if args.json:
        print(json.dumps(res, indent=1))
        return 0 if res.get("ok") else 1
    if not res.get("ok"):
        print("ERROR " + str(res.get("error")))
        return 1
    tm = res["timing"]
    print(f"structure {args.structure} at {len(spots)} spots from {where_text}, {args.spacing} blocks apart")
    placed = [sp for sp in res["spots"] if sp.get("placed")]
    for sp in res["spots"]:
        if not sp.get("placed"):
            print(f"  ({sp['x']}, {sp['z']}): not placed: {sp.get('reason')}")
            continue
        box = sp["box"]
        print(f"  ({sp['x']}, {sp['z']}): {sp['pieces']} pieces, box {box[0]},{box[1]},{box[2]} to {box[3]},{box[4]},{box[5]} ({box[3] - box[0] + 1} x {box[4] - box[1] + 1} x {box[5] - box[2] + 1}), "
              f"{n_(sp['writes'])} block writes in {sp['place_ms']} ms")
        print(f"      cells in the pieces' boxes: {n_(sp['cells'])}: vanilla water (minecraft:water) {n_(sp['water_cells'])}, TFC fluid {n_(sp['fluid_cells'])}, air {n_(sp['air_cells'])} (the boxes also hold terrain)")
        print("      blocks: " + ", ".join(f"{k} {n_(v)}" for k, v in sp["blocks"].items()))
        van = sp["vanilla_left"]
        if van:
            print("      vanilla blocks left: " + ", ".join(f"{k} {n_(v)}" + (f" at {tuple(sp['vanilla_first'][k])}" if k in sp["vanilla_first"] else "") for k, v in sorted(van.items(), key=lambda kv: -kv[1])[:10]))
        else:
            print("      vanilla blocks left: none (besides air, water, lava, bedrock)")
        if sp["containers"]:
            print("      containers: " + ", ".join(f"{k} x{v}" for k, v in sorted(sp["containers"].items(), key=lambda kv: -kv[1])[:10]))
        if sp.get("entities_added"):
            print(f"      entities the structure spawned (removed again): {sp['entities_added']}")
        rs = sp["restore"]
        print(f"      terrain restored: {n_(rs['positions'])} positions, {rs['mismatches']} differ")
    if not placed:
        print("  nothing was placed: " + "; ".join(sorted({sp.get('reason', '?') for sp in res['spots']})[:3]))
    print(f"  time: generate {tm['generate_ms']} ms" + (f", load {tm['load_ms']} ms ({res['chunks_loaded']} chunks), place and read {tm['place_ms']} ms" if "load_ms" in tm else "") + f"; {wall:.1f} s in all")
    print("  (estimate: placed like /place does, on the live level: no terrain adaptation, and the booted structure data, not the disk's; the pack_world skin runs)")
    return 0


# ------------------------------------------------------------------ development helpers
def project(lat, lon):
    from worldview.geo import load_projection
    proj = load_projection(os.path.join(LAB_DIR, WORLD), [os.path.join(LAB_DIR, "mods")])
    if not proj:
        raise SystemExit("--place needs the lab's world (tools/.lab/world-lab/serverconfig/tfc_real_world/server.toml): start the lab once")
    x, z = proj.to_block(lon, lat)
    return round(x), round(z)


def cmd_job(args):
    """Development: send any job kind with a JSON payload and print the result."""
    lab = Lab()
    payload = json.loads(args.payload) if args.payload else {}
    t0 = time.time()
    res = lab.run(args.kind, timeout=args.timeout, **payload)
    print(json.dumps(res, indent=1))
    print(f"({time.time() - t0:.2f} s)")
    return 0 if res.get("ok", True) else 1


def cmd_cmd(args):
    """Development: run a console command in the lab and show what the console printed."""
    lab = Lab()
    offset = os.path.getsize(CONSOLE)
    res = lab.run("cmd", timeout=args.timeout, command=args.command)
    time.sleep(0.5)
    print(json.dumps(res))
    print(console_since(offset), end="")
    return 0 if res.get("ok") else 1


def cmd_log(args):
    print(console_tail(args.lines), end="")
    return 0


def main():
    utf8_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def start_args(p):
        p.add_argument("--xmx", default="6G", help="heap of the lab (default 6G: the pack alone holds 1.8 GB, and a window of chunks needs room; 4G ran out twice)")
        p.add_argument("--idle-minutes", type=float, default=IDLE_MINUTES, help="stop the lab after this long without a job (default 30)")
        p.add_argument("--fresh", action="store_true", help="delete the lab world first (it is regenerated chunk by chunk as jobs ask)")
        p.add_argument("--no-sync", action="store_true", help="do not sync the pack (the lab's folder is used as it is)")
        p.add_argument("--keep-features", action="store_true", help="do not blank the pack's own placed features (see below)")
        p.add_argument("--blank", action="append", default=[], metavar="ID", help="also blank this placed feature (repeatable)")
        p.add_argument("--boot-timeout", type=int, default=900)
        p.add_argument("--seed-from-server", action="store_true", help="first start only: copy NeoForge and the mods from tools/.server instead of downloading them")

    p = sub.add_parser("start", help="sync the pack, boot the lab detached and wait until it is ready")
    start_args(p)
    p.set_defaults(fn=cmd_start)
    p = sub.add_parser("status", help="up or down, uptime, jobs served, whether a restart is needed")
    p.set_defaults(fn=cmd_status)
    p = sub.add_parser("stop", help="stop the lab (a job; kills the process if it does not answer)")
    p.add_argument("--timeout", type=int, default=90)
    p.set_defaults(fn=cmd_stop)
    p = sub.add_parser("restart", help="stop, sync and start again")
    start_args(p)
    p.add_argument("--stop-timeout", type=int, default=90)
    p.set_defaults(fn=cmd_restart)
    def where_args(p, biome_required):
        p.add_argument("feature", help="placed feature id (pack:ocean/nodule_field) or the path of its file")
        p.add_argument("--biome", required=biome_required, help="biome id, e.g. tfc:deep_ocean (lab.py ids biome lists them)")
        g = p.add_mutually_exclusive_group()
        g.add_argument("--place", help="LAT,LON centre (TFC: Real World map), converted to blocks")
        g.add_argument("--center", help="X,Z block centre")
        p.add_argument("--chunks", type=int, default=None, help="use this many chunks of the biome, nearest to the centre first (default 300; with --radius: every chunk of the window; 0: no limit)")
        p.add_argument("--radius", type=int, default=0, help="only chunks inside the square of this half-width in blocks around the centre (768: a 1,536-block square)")
        p.add_argument("--max-ring", type=int, default=60, help="how far to look for chunks of the biome, in chunks from the centre (default 60)")
        p.add_argument("--seed", type=int, default=0, help="varies the random stream (default 0: the same chunks and rolls every attempt)")
        p.add_argument("--step", type=int, default=8, help="decoration step the feature seed uses (TFC's large features are step 8)")
        p.add_argument("--data", help="a staged build root (it holds kubejs/data) instead of the repo")
        p.add_argument("--batch", type=int, default=500, help="chunks loaded at a time (each batch is placed, read and restored before the next; memory)")
        p.add_argument("--timeout", type=int, default=900, help="seconds to allow, chunk generation included")
        p.add_argument("--json", action="store_true", help="print the lab's raw answer")

    p = sub.add_parser("check", help="decode worldgen JSON with the game's codecs against the lab's registries")
    p.add_argument("paths", nargs="*", help="files, folders or ids (default: every worldgen file under kubejs/data)")
    p.add_argument("--data", help="a staged build root (it holds kubejs/data) instead of the repo")
    p.add_argument("--timeout", type=int, default=120)
    p.set_defaults(fn=cmd_check)
    p = sub.add_parser("place", help="run a placed feature in chunks of a biome, as chunk decoration would, and report what landed")
    where_args(p, True)
    p.add_argument("--no-rarity", action="store_true", help="drop the rarity filters so a rare feature's shape can be inspected (counts inflate by their chances)")
    p.add_argument("--neighbours", type=int, default=20000, help="look at the neighbours of at most this many blocks of each kind (default 20000)")
    p.add_argument("--first", type=int, default=5, help="positions to list per block kind")
    p.set_defaults(fn=cmd_place)
    p = sub.add_parser("where", help="count the chunks and positions that pass the placement modifiers, without placing")
    where_args(p, False)
    p.add_argument("--terrain", action="store_true", help="also evaluate the modifiers that need terrain (generates the chunks)")
    p.add_argument("--bands", help="tfc:ocean_ridge distance bands to count chunks in, e.g. 0-25,26-60,61-130,131-300")
    p.add_argument("--band-at", choices=("middle", "corner"), default="middle", help="where in the chunk the ridge distance is read (default the middle)")
    p.set_defaults(fn=cmd_where)
    p = sub.add_parser("structure", help="place a structure of any mod at chosen spots and read its pieces back")
    p.add_argument("structure", help="structure id in the lab's registries, e.g. underwater_village:tower (lab.py ids structure)")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--place", help="LAT,LON of the first spot")
    g.add_argument("--center", help="X,Z block position of the first spot")
    p.add_argument("--count", type=int, default=3, help="spots, in a row along x (default 3)")
    p.add_argument("--spacing", type=int, default=160, help="blocks between spots (default 160)")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--top", type=int, default=12, help="block kinds to list per structure")
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_structure)
    p = sub.add_parser("ids", help="ids in one of the lab's registries (biome, structure, placed_feature ...)")
    p.add_argument("kind", choices=sorted(ID_KINDS))
    p.add_argument("pattern", nargs="?", help="only ids containing this")
    p.set_defaults(fn=cmd_ids)
    p = sub.add_parser("job", help="development: send any job to the lab's script")
    p.add_argument("kind")
    p.add_argument("payload", nargs="?", help="JSON object")
    p.add_argument("--timeout", type=int, default=600)
    p.set_defaults(fn=cmd_job)
    p = sub.add_parser("cmd", help="development: run a console command in the lab")
    p.add_argument("command")
    p.add_argument("--timeout", type=int, default=120)
    p.set_defaults(fn=cmd_cmd)
    p = sub.add_parser("log", help="tail of the lab's console log")
    p.add_argument("-n", "--lines", type=int, default=40)
    p.set_defaults(fn=cmd_log)

    # "--center -687286,-77142" would read the coordinates as an option: glue a negative value on to its flag
    argv, i = [], 1
    while i < len(sys.argv):
        a = sys.argv[i]
        if a in ("--center", "--place") and i + 1 < len(sys.argv) and re.match(r"^-\d", sys.argv[i + 1]):
            argv.append(f"{a}={sys.argv[i + 1]}")
            i += 2
        else:
            argv.append(a)
            i += 1
    args = ap.parse_args(argv)
    sys.exit(args.fn(args) or 0)


if __name__ == "__main__":
    main()
