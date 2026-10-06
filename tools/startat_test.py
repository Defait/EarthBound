"""Check the /startat command on a fresh headless world.

Usage (from the repo root):
    tools/.venv/Scripts/python tools/startat_test.py [--no-sync] [--keep-world]

Boots the test server on a new world with a dev-only KubeJS script (tools/startat_test.js)
that runs the start-point finder for a few real places and then /startat itself as a
NeoForge fake player (not an operator): open water, a first use, a second use, a bad
latitude. Exits 1 if any check fails or the checks don't run.
"""
import argparse
import os
import re
import shutil
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
from mclib.paths import utf8_console  # noqa: E402
from mclib.server import DONE_RE, TestServer  # noqa: E402

WORLD = "world-startat"
RESULT_RE = re.compile(r"\[startat-test\] (PASS|FAIL|done)(.*)")


def main():
    utf8_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-sync", action="store_true", help="skip packwiz-installer")
    ap.add_argument("--keep-world", action="store_true", help="keep the test world afterwards")
    ap.add_argument("--timeout", type=int, default=900, help="seconds to wait for startup")
    args = ap.parse_args()

    srv = TestServer()
    srv.ensure_installed()
    if not args.no_sync:
        srv.sync_pack()
    srv.set_extra_mods([])
    srv.set_dev_scripts({"startat_test.js": os.path.join(TOOLS, "startat_test.js")})
    shutil.rmtree(srv.path(WORLD), ignore_errors=True)
    srv.write_properties(WORLD, "startat")
    print("Starting server...")
    srv.start()
    finished = srv.wait_for(r"\[startat-test\] done|" + DONE_RE.pattern, args.timeout)
    if finished and "startat-test" not in finished.group(0):
        finished = srv.wait_for(r"\[startat-test\] done", 120)
    srv.set_dev_scripts({})
    srv.stop()
    if not args.keep_world:
        shutil.rmtree(srv.path(WORLD), ignore_errors=True)

    failed, ran = 0, False
    for line in srv.lines:
        m = RESULT_RE.search(line)
        if not m:
            continue
        ran = True
        if m.group(1) == "FAIL":
            failed += 1
        print(f"  {m.group(1)}{m.group(2)}")
    for line in srv.lines:
        if "startat" in line and ("ERROR" in line or "unexpected error" in line):
            failed += 1
            print("  ERROR " + line[-200:])
    ok = ran and failed == 0
    print("Verdict: " + ("PASS" if ok else "FAIL" if ran else "FAIL (checks did not run)"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
