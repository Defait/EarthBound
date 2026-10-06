"""Check for (and optionally install) a newer GregTech CEu Modern nightly for this pack.

Usage (from the repo root):
    tools/.venv/Scripts/python tools/gt_update.py            # report only
    tools/.venv/Scripts/python tools/gt_update.py --apply    # swap the pack to the newest build
    tools/.venv/Scripts/python tools/gt_update.py --apply --build 101   # pin a specific build
    tools/.venv/Scripts/python tools/gt_update.py --apply --smoke       # then run the smoke test

The pack pins GregTech to a timestamped snapshot on maven.gtceu.com (GitHub
deletes each nightly when the next one lands, so its links don't last).
packwiz can't update a direct URL, so this does it: it lists the commits since
the pinned build, checks the new jar's declared dependencies against the pack,
and replaces mods/gregtechceu-modern.pw.toml via packwiz.
"""
import argparse
import datetime
import io
import json
import os
import re
import subprocess
import sys
import tomllib
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mclib.pack import load_pack  # noqa: E402
from mclib.paths import REPO, utf8_console  # noqa: E402

META = "gregtechceu-modern"
MAVEN = "https://maven.gtceu.com/com/gregtechceu/gtceu/gtceu-{mc}"
REPO_API = "https://api.github.com/repos/GregTechCEu/GregTech-Modern"
FILE_RE = re.compile(r"gtceu-(?P<mc>[\d.]+)-(?P<base>[\d.]+)-(?P<ts>\d{8}\.\d{6})-(?P<build>\d+)\.jar$")


def fetch(url, accept=None):
    req = urllib.request.Request(url, headers={"User-Agent": "mc-pack-tools", **({"Accept": accept} if accept else {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def snapshot_builds(mc, base):
    """All published builds of <base>-SNAPSHOT: [(timestamp, build, url)], oldest first."""
    url = f"{MAVEN.format(mc=mc)}/{base}-SNAPSHOT"
    root = ET.fromstring(fetch(f"{url}/maven-metadata.xml"))
    builds = []
    for sv in root.iter("snapshotVersion"):
        if sv.findtext("extension") == "jar" and not sv.findtext("classifier"):
            value = sv.findtext("value")
            m = re.match(r".*-(\d{8}\.\d{6})-(\d+)$", value)
            if m:
                builds.append((m[1], int(m[2]), f"{url}/gtceu-{mc}-{value}.jar"))
    # maven-metadata lists only the latest snapshotVersion per classifier; older builds come from the directory listing
    try:
        listing = fetch(url + "/").decode("utf-8", "replace")
        for m in re.finditer(rf"gtceu-{re.escape(mc)}-{re.escape(base)}-(\d{{8}}\.\d{{6}})-(\d+)\.jar\"", listing):
            builds.append((m[1], int(m[2]), f"{url}/gtceu-{mc}-{base}-{m[1]}-{m[2]}.jar"))
    except OSError:
        pass
    return sorted(set(builds), key=lambda b: b[1])


def artifact_versions(mc):
    root = ET.fromstring(fetch(f"{MAVEN.format(mc=mc)}/maven-metadata.xml"))
    return [v.text for v in root.iter("version")], root.findtext(".//release"), root.findtext(".//latest")


def ts_to_iso(ts):
    return datetime.datetime.strptime(ts, "%Y%m%d.%H%M%S").replace(tzinfo=datetime.timezone.utc).isoformat()


def commits_between(ts_from, ts_to, branch="1.21"):
    try:
        data = json.loads(fetch(f"{REPO_API}/commits?sha={branch}&since={ts_to_iso(ts_from)}&until={ts_to_iso(ts_to)}&per_page=100",
                                "application/vnd.github+json"))
        return [(c["commit"]["committer"]["date"][:10], c["commit"]["message"].splitlines()[0]) for c in data]
    except OSError as e:
        return [("?", f"(couldn't reach GitHub: {e})")]


def vkey(v):
    return [int(p) if p.isdigit() else p for p in re.split(r"[.\-+_]", str(v)) if p]


def in_range(version, rng):
    """Loose Maven version-range check for forms like [a,), [a,b), (a,b], or a bare version."""
    if not rng or version is None:
        return None
    m = re.match(r"^([\[(])\s*([^,]*)\s*,\s*([^\])]*)\s*([\])])$", rng.strip())
    if not m:
        return vkey(version) >= vkey(rng)
    lo_inc, lo, hi, hi_inc = m[1] == "[", m[2], m[3], m[4] == "]"
    try:
        if lo and (vkey(version) < vkey(lo) or (not lo_inc and vkey(version) == vkey(lo))):
            return False
        if hi and (vkey(version) > vkey(hi) or (not hi_inc and vkey(version) == vkey(hi))):
            return False
    except TypeError:
        return None
    return True


def installed_mod_versions():
    """modId -> version from the mod jars' own metadata (test server's mods, else the client instance's)."""
    import glob
    from mclib.paths import DEFAULT_INSTANCE, SERVER_DIR
    folder = os.path.join(SERVER_DIR, "mods")
    if not glob.glob(os.path.join(folder, "*.jar")):
        folder = os.path.join(DEFAULT_INSTANCE, "mods")
    out = {}

    def read(z):
        try:
            meta = tomllib.loads(z.read("META-INF/neoforge.mods.toml").decode("utf-8", "replace"))
        except (KeyError, tomllib.TOMLDecodeError):
            meta = {}
        manifest = ""
        try:
            manifest = z.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
        except KeyError:
            pass
        impl = re.search(r"^Implementation-Version:\s*(\S+)", manifest, re.M)
        for mod in meta.get("mods", []):
            v = str(mod.get("version", ""))
            if "${" in v:
                v = impl[1] if impl else None
            out.setdefault(mod.get("modId"), v)
        for n in z.namelist():
            if n.startswith("META-INF/jarjar/") and n.endswith(".jar"):
                try:
                    read(zipfile.ZipFile(io.BytesIO(z.read(n))))
                except zipfile.BadZipFile:
                    pass

    for jar in glob.glob(os.path.join(folder, "*.jar")):
        try:
            read(zipfile.ZipFile(jar))
        except zipfile.BadZipFile:
            continue
    return out


def check_jar(url, pack):
    jar = zipfile.ZipFile(io.BytesIO(fetch(url)))
    toml = tomllib.loads(jar.read("META-INF/neoforge.mods.toml").decode())
    deps = toml.get("dependencies", {}).get("gtceu", [])
    installed = installed_mod_versions()
    rows = []
    for dep in deps:
        mid, kind, rng = dep.get("modId"), dep.get("type", "required"), dep.get("versionRange", "")
        if mid == "neoforge":
            have = pack["versions"].get("neoforge")
        elif mid == "minecraft":
            have = pack["versions"].get("minecraft")
        else:
            have = installed.get(mid)
        ok = in_range(have, rng) if have else (None if kind != "required" else False)
        rows.append((mid, kind, rng, have, ok))
    return rows


def main():
    utf8_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="switch the pack to the chosen build")
    ap.add_argument("--build", type=int, help="pick a specific build number instead of the newest")
    ap.add_argument("--smoke", action="store_true", help="run tools/smoke.py after applying")
    args = ap.parse_args()

    pack = load_pack()
    meta_path = os.path.join(REPO, "mods", f"{META}.pw.toml")
    with open(meta_path, "rb") as f:
        current = tomllib.load(f)
    m = FILE_RE.search(current["filename"])
    if not m:
        raise SystemExit(f"Unrecognized GregTech filename in {meta_path}: {current['filename']}")
    mc, base, cur_ts, cur_build = m["mc"], m["base"], m["ts"], int(m["build"])
    print(f"Pack has GregTech {base} snapshot build {cur_build} ({cur_ts}) for Minecraft {mc}")

    versions, release, latest = artifact_versions(mc)
    newer_bases = [v for v in versions if v.endswith("-SNAPSHOT") and vkey(v[:-9]) > vkey(base)]
    releases = [v for v in versions if not v.endswith("-SNAPSHOT") and vkey(v) >= vkey(base)]
    if releases:
        print(f"Note: release build(s) {', '.join(releases)} exist at or above {base}; consider switching to a release.")
    if newer_bases:
        print(f"Note: newer snapshot line(s) {', '.join(newer_bases)} exist; this script stays on {base}-SNAPSHOT.")

    builds = snapshot_builds(mc, base)
    if not builds:
        raise SystemExit("No snapshot builds found on the maven")
    if args.build:
        target = next((b for b in builds if b[1] == args.build), None)
        if not target:
            raise SystemExit(f"Build {args.build} not found; available: {', '.join(str(b[1]) for b in builds[-10:])}")
    else:
        target = builds[-1]
    ts, build, url = target
    if build == cur_build:
        print(f"Already on the newest build ({build}).")
        return
    direction = "newer" if build > cur_build else "older"
    print(f"\n{'Newest' if not args.build else 'Chosen'} build: {build} ({ts}), {direction} than the pack's.\n{url}")

    lo, hi = sorted([cur_ts, ts])
    commits = commits_between(lo, hi)
    print(f"\nCommits on the 1.21 branch between the two builds ({len(commits)}{'+' if len(commits) == 100 else ''}):")
    for date, msg in commits[:60]:
        print(f"  {date}  {msg[:110]}")

    print("\nDependencies declared by the new jar:")
    rows = check_jar(url, pack)
    problems = 0
    for mid, kind, rng, have, ok in rows:
        if have is None and kind != "required":
            print(f"  --  {mid:14} {kind:9} needs {rng:28} not in the pack (optional)")
            continue
        mark = "ok " if ok else ("?? " if ok is None else "!! ")
        if ok is False and kind == "required":
            problems += 1
        print(f"  {mark} {mid:14} {kind:9} needs {rng:28} pack has {have or '-'}")
    if problems:
        print(f"\n{problems} required dependency problem(s); fix those before applying.")

    if not args.apply:
        print("\nReport only. Re-run with --apply to switch the pack to this build.")
        return
    if problems:
        raise SystemExit("Not applying because of dependency problems.")
    run = lambda *cmd: subprocess.run(cmd, cwd=REPO, check=True, capture_output=True, text=True)
    run("packwiz", "remove", META)
    run("packwiz", "url", "add", current.get("name", "GregTech CEu Modern"), url, "--meta-name", META, "--meta-folder", "mods")
    print(f"\nPack updated to build {build}. Review with `git diff mods/{META}.pw.toml`, then relaunch or run the smoke test.")
    if args.smoke:
        subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "smoke.py")], cwd=REPO)


if __name__ == "__main__":
    main()
