"""Triage a Minecraft log: real errors vs known-harmless noise vs new since last time.

Usage (from the repo root):
    tools/.venv/Scripts/python tools/logtriage.py            # client: the Prism instance's latest.log
    tools/.venv/Scripts/python tools/logtriage.py --server   # the headless test server's latest.log
    tools/.venv/Scripts/python tools/logtriage.py path/to/latest.log

Writes a Markdown report to tools/.data/reports/ and exits 1 when there is a
crash, a KubeJS script error, or an error that isn't on tools/known_issues.json.
"""
import argparse
import datetime
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mclib import logtriage  # noqa: E402
from mclib.paths import DATA_DIR, DEFAULT_INSTANCE, SERVER_DIR, utf8_console  # noqa: E402

REPORTS = os.path.join(DATA_DIR, "reports")


def log_start_time(log_path):
    """Epoch seconds of the first entry in a log, or the file's mtime minus a day."""
    for e in logtriage.parse_log(log_path)[:1]:
        try:
            return datetime.datetime.strptime(e["ts"], "%d%b%Y %H:%M:%S.%f").timestamp()
        except ValueError:
            break
    return os.path.getmtime(log_path) - 86400


def run(game_dir, context, log_path=None, title=None, quiet=False, reload_marker=None):
    """Triage a game directory's logs; returns (result, report_path)."""
    log_path = log_path or os.path.join(game_dir, "logs", "latest.log")
    if not os.path.exists(log_path):
        raise SystemExit(f"No log at {log_path}")
    os.makedirs(REPORTS, exist_ok=True)
    last = os.path.join(REPORTS, f"last-{context}.json")
    previous = json.load(open(last)) if os.path.exists(last) else None
    result = logtriage.triage(log_path, os.path.join(game_dir, "logs", "kubejs"), os.path.join(game_dir, "crash-reports"),
                              since=log_start_time(log_path), previous=previous,
                              reload_marker=reload_marker)
    with open(last, "w") as f:
        json.dump(logtriage.signatures(result), f, indent=0)
    md = logtriage.render(result, title or f"Log triage ({context})")
    report = os.path.join(REPORTS, f"{context}-{time.strftime('%Y%m%d-%H%M%S')}.md")
    with open(report, "w", encoding="utf-8") as f:
        f.write(md)
    if not quiet:
        print(md)
        print(f"Report saved to {report}")
    return result, report


def main():
    utf8_console()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("log", nargs="?", help="a specific latest.log (its folder's parent is treated as the game dir)")
    ap.add_argument("--server", action="store_true", help="triage the headless test server")
    ap.add_argument("--instance", default=DEFAULT_INSTANCE, help="client instance .minecraft folder")
    args = ap.parse_args()
    if args.log:
        game_dir, context = os.path.dirname(os.path.dirname(os.path.abspath(args.log))), "custom"
    elif args.server:
        game_dir, context = SERVER_DIR, "server"
    else:
        game_dir, context = args.instance, "client"
    result, _ = run(game_dir, context, args.log)
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
