"""Smoke test: boot the pack on a headless server with a fresh world, then triage the logs.

Usage (from the repo root):
    tools/.venv/Scripts/python tools/smoke.py [--keep-world] [--no-sync] [--timeout 900]

Steps: install/refresh NeoForge for the pack's loader version, sync the pack's
server-side files with packwiz-installer, start the server on a new world,
wait for it to finish loading (or crash), run /reload once to exercise
script reloading, stop it, and report. tools/smoke_checks.js runs extra checks on
the server (e.g. that recipe-viewer mixins apply). Exits 1 on a crash, a KubeJS script
error, or an error that isn't on tools/known_issues.json.
"""
import argparse
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logtriage  # noqa: E402
from mclib.paths import utf8_console  # noqa: E402
from mclib.server import DONE_RE, TestServer  # noqa: E402

WORLD = "world-smoke"


def main():
    utf8_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--keep-world", action="store_true", help="reuse the previous smoke world instead of a fresh one")
    ap.add_argument("--no-sync", action="store_true", help="skip packwiz-installer (test what's already installed)")
    ap.add_argument("--timeout", type=int, default=900, help="seconds to wait for startup")
    ap.add_argument("--seed", default="smoke", help="world seed")
    ap.add_argument("--xmx", default="6G")
    args = ap.parse_args()

    t0 = time.time()
    srv = TestServer()
    print(f"Pack: {srv.pack['name']} {srv.pack.get('version', '')} · Minecraft {srv.pack['versions']['minecraft']} · NeoForge {srv.loader_version}")
    srv.ensure_installed()
    if not args.no_sync:
        srv.sync_pack()
    srv.set_extra_mods([])
    srv.set_dev_scripts({"smoke_checks.js": os.path.join(os.path.dirname(os.path.abspath(__file__)), "smoke_checks.js")})
    if not args.keep_world:
        shutil.rmtree(srv.path(WORLD), ignore_errors=True)
    srv.write_properties(WORLD, args.seed)

    print("Starting server...")
    started = time.time()
    srv.start(args.xmx)
    done = srv.wait_for(DONE_RE.pattern, args.timeout)
    if done:
        print(f"Server ready in {done[1]}s (wall clock {time.time() - started:.0f}s).")
        # smoke_checks.js runs some checks a second after startup (once FTB Quests has loaded its book).
        if not srv.wait_for(r"\[smoke-checks\] done", 60):
            print("  smoke_checks.js did not finish within a minute")
        print("Testing /reload...")
        srv.command("reload")
        if not srv.wait_for(r"Reloaded with .*KubeJS|Failed to reload|reload failed", 300):
            print("  /reload did not report completion within 5 minutes")
    else:
        print("Server did not reach 'Done' (crashed, exited, or timed out).")
    code = srv.stop()
    print(f"Server exited with code {code}.")

    result, report = logtriage.run(srv.root, "server", title="Smoke test", quiet=True, reload_marker=r"^Reloading!$")
    if not done:
        result["ok"] = False
    print(open(report, encoding="utf-8").read())
    print(f"Report saved to {report}")
    print(f"Total time {time.time() - t0:.0f}s. Verdict: {'PASS' if result['ok'] else 'FAIL'}")
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
