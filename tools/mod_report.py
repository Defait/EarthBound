"""Mod report: available updates (with changelogs), client/server side audit, and licenses.

Usage (from the repo root):
    tools/.venv/Scripts/python tools/mod_report.py [--changelog-lines 6]

Reads every mods/*.pw.toml. Modrinth-sourced mods are checked against
Modrinth for newer builds for this Minecraft version and loader, for the
sides Modrinth says they need, and for their license. Direct-URL mods
(GregTech) are listed with a pointer to tools/gt_update.py.

Nothing is changed; `packwiz update <mod>` applies an update.
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mclib.pack import load_pack, loader, mods  # noqa: E402
from mclib.paths import utf8_console  # noqa: E402

API = "https://api.modrinth.com/v2"
OPEN_SOURCE = {"EUPL-1.2", "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "Zlib", "Unlicense", "CC0-1.0",
              "LGPL-2.1-only", "LGPL-3.0-only", "LGPL-2.1-or-later", "LGPL-3.0-or-later", "MPL-2.0",
              "GPL-3.0-only", "GPL-3.0-or-later", "GPL-2.0-only", "GPL-2.0-or-later", "AGPL-3.0-only", "OSL-3.0"}


def get(path, **params):
    url = f"{API}/{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
    req = urllib.request.Request(url, headers={"User-Agent": "mc-pack-tools"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def side_note(pack_side, client, server):
    """Compare packwiz's side with Modrinth's client_side/server_side."""
    if pack_side == "both" and server == "unsupported":
        return "client-only on Modrinth but installed on servers too"
    if pack_side == "both" and client == "unsupported":
        return "server-only on Modrinth but installed on clients too"
    if pack_side == "client" and server == "required":
        return "Modrinth says servers need it, but it's client-only here"
    if pack_side == "server" and client == "required":
        return "Modrinth says clients need it, but it's server-only here"
    return ""


def main():
    utf8_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--changelog-lines", type=int, default=6)
    ap.add_argument("--prerelease", action="store_true", help="also list beta/alpha builds newer than a release you're on")
    args = ap.parse_args()
    rank = {"release": 2, "beta": 1, "alpha": 0}
    pack = load_pack()
    mc = pack["versions"]["minecraft"]
    ldr, _ = loader(pack)

    rows, updates, url_mods = [], [], []
    entries = list(mods())
    ids = [d["update"]["modrinth"]["mod-id"] for _, d in entries if "modrinth" in d.get("update", {})]
    projects = {p["id"]: p for p in get("projects", ids=json.dumps(ids))} if ids else {}
    for path, d in entries:
        name = d.get("name", os.path.basename(path))
        mr = d.get("update", {}).get("modrinth")
        if not mr:
            url_mods.append((name, d.get("download", {}).get("url", "")))
            continue
        proj = projects.get(mr["mod-id"], {})
        versions = get(f"project/{mr['mod-id']}/version", loaders=json.dumps([ldr]), game_versions=json.dumps([mc]))
        current = next((v for v in versions if v["id"] == mr["version"]), None)
        cur_date = current["date_published"] if current else ""
        floor = 0 if args.prerelease or not current else rank.get(current["version_type"], 0)
        newer = [v for v in versions if v["date_published"] > cur_date and v["id"] != mr["version"]
                 and rank.get(v["version_type"], 0) >= floor] if current else versions[:1]
        lic = (proj.get("license") or {}).get("id", "?")
        rows.append({
            "name": name, "version": current["version_number"] if current else f"? ({d.get('filename')})",
            "type": current["version_type"] if current else "?", "side": d.get("side", "both"),
            "client": proj.get("client_side", "?"), "server": proj.get("server_side", "?"), "license": lic,
            "newer": newer, "slug": proj.get("slug", mr["mod-id"]),
        })
        if newer:
            updates.append(rows[-1])

    print(f"Pack: {pack.get('name')} · Minecraft {mc} · {ldr}\n")
    print(f"{'Mod':28} {'Version':34} {'Type':7} {'Side':6} {'Modrinth client/server':24} {'License':24} Notes")
    for r in rows:
        notes = side_note(r["side"], r["client"], r["server"])
        if r["license"] not in OPEN_SOURCE:
            notes = (notes + "; " if notes else "") + "check the license before redistributing"
        if r["newer"]:
            notes = (notes + "; " if notes else "") + f"{len(r['newer'])} newer build(s)"
        print(f"{r['name'][:28]:28} {r['version'][:34]:34} {r['type']:7} {r['side']:6} {r['client'] + '/' + r['server']:24} {r['license'][:24]:24} {notes}")
    for name, url in url_mods:
        print(f"{name[:28]:28} {'(direct URL)':34} {'':7} {'':6} {'':24} {'':24} update with tools/gt_update.py" if "gtceu" in url else f"{name[:28]:28} (direct URL) {url}")

    if updates:
        print("\nAvailable updates (newest first):")
        for r in updates:
            print(f"\n{r['name']} {r['version']} -> {r['newer'][0]['version_number']} ({r['newer'][0]['version_type']}, {r['newer'][0]['date_published'][:10]})"
                  f"   packwiz update {r['slug']}")
            for v in r["newer"][:3]:
                lines = [ln.strip() for ln in (v.get("changelog") or "").splitlines() if ln.strip()][:args.changelog_lines]
                print(f"  {v['version_number']}:")
                for ln in lines:
                    print(f"    {ln[:120]}")
    else:
        print("\nEverything from Modrinth is on its newest build for this Minecraft version and loader"
              + ("." if args.prerelease else " (counting only builds as stable as the one installed; --prerelease lists betas too)."))
    print("\nLicense column: anything not on the open-source list is flagged; mods marked All Rights Reserved (or with a custom"
          "\nlicense) usually can't be bundled into a pack file without the author's permission. Modrinth packs (.mrpack)"
          "\nlink downloads instead of bundling, so this mostly matters for CurseForge-style exports with overrides.")


if __name__ == "__main__":
    main()
