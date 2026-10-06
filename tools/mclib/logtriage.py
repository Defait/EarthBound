"""Group a Minecraft log's warnings and errors and separate real problems from known noise.

Each WARN/ERROR/FATAL entry (with its stack trace) gets a signature: the
logger plus the message with numbers, hashes, paths and coordinates masked.
Signatures are matched against tools/known_issues.json (noise we've judged
harmless, with the reason) and compared with the previous run, so a report
shows what is new rather than everything at once.
"""
import glob
import json
import os
import re
import time
from collections import OrderedDict

from .paths import TOOLS

# "[ts] [thread/LEVEL] [logger/MARKER]: message" (the marker is often empty)
LINE_RE = re.compile(r"^\[(?P<ts>[^\]]+)\] \[(?P<thread>[^\]]*?)/(?P<level>[A-Z]+)\] "
                     r"\[(?P<logger>[^\]/]*)(?:/(?P<marker>[^\]]*))?\]: (?P<msg>.*)$")
KJS_RE = re.compile(r"^\[(?P<ts>[\d:]+)\] \[(?P<level>[A-Z]+)\] (?P<msg>.*)$")
KJS_SUMMARY_RE = re.compile(r"Loaded (\d+)/(\d+) KubeJS (\w+) scripts in [\d.]+ s with (\d+) errors and (\d+) warnings")
KNOWN_FILE = os.path.join(TOOLS, "known_issues.json")
PROBLEM_LEVELS = ("WARN", "ERROR", "FATAL")

_MASKS = [
    (re.compile(r"[A-Za-z]:[\\/][^\s'\"\]]+|(?:/[\w.\-+%#!]+){2,}"), "<path>"),
    (re.compile(r"\b0x[0-9a-fA-F]+\b|\b[0-9a-f]{7,}\b"), "<hex>"),
    (re.compile(r"\b\d+(?:\.\d+)*\b"), "#"),
    (re.compile(r"\[id: [^\]]*\]"), "[id]"),
]


def signature(logger, msg):
    s = msg
    for rx, rep in _MASKS:
        s = rx.sub(rep, s)
    return f"{logger}: {s.strip()}"[:300]


def parse_log(path):
    """Return a list of entries: dict(ts, thread, level, logger, msg, extra[list])."""
    entries = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\n")
            m = LINE_RE.match(line)
            if m:
                e = m.groupdict()
                e["extra"] = []
                entries.append(e)
            elif entries and line.strip():
                entries[-1]["extra"].append(line)
    return entries


def load_known(path=KNOWN_FILE):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        items = json.load(f)["known"]
    for k in items:
        k["rx"] = re.compile(k["pattern"])
    return items


def _known_match(known, entry):
    text = f"{entry['logger']}: {entry['msg']}"
    for k in known:
        if k.get("level") and k["level"] != entry["level"]:
            continue
        if k["rx"].search(text):
            return k
    return None


def triage(log_path, kubejs_dir=None, crash_dir=None, since=None, previous=None, known=None, reload_marker=None):
    """Analyze one log (plus optional KubeJS logs and crash reports newer than `since`).

    Entries after the first line matching reload_marker (e.g. the server's
    "Reloading!") are reported separately as reload-only problems and don't
    affect the verdict, which is about startup health.
    """
    known = load_known() if known is None else known
    previous = set(previous or [])
    groups = OrderedDict()
    marker = re.compile(reload_marker) if reload_marker else None
    phase = "startup"
    for e in parse_log(log_path):
        if marker and phase == "startup" and marker.search(e["msg"]):
            phase = "reload"
        if e["level"] not in PROBLEM_LEVELS:
            continue
        sig = signature(e["logger"], e["msg"])
        g = groups.get((phase, sig))
        if g is None:
            k = _known_match(known, e)
            g = groups[(phase, sig)] = {
                "signature": sig, "level": e["level"], "logger": e["logger"], "count": 0,
                "first": e["msg"], "extra": e["extra"][:12], "time": e["ts"], "phase": phase,
                "known": k["note"] if k else None, "new": sig not in previous,
            }
        g["count"] += 1
        if e["level"] == "FATAL" or (e["level"] == "ERROR" and g["level"] == "WARN"):
            g["level"] = e["level"]

    kubejs = []
    for p in sorted(glob.glob(os.path.join(kubejs_dir, "*.log"))) if kubejs_dir else []:
        if since and os.path.getmtime(p) < since:
            continue
        summary, issues = [], []
        with open(p, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = KJS_RE.match(line.rstrip("\n"))
                if not m:
                    continue
                s = KJS_SUMMARY_RE.search(m["msg"])
                if s:
                    summary.append({"type": s[3], "loaded": int(s[1]), "total": int(s[2]), "errors": int(s[4]), "warnings": int(s[5])})
                elif m["level"] in ("WARN", "ERROR") and "server.log may not contain everything" not in m["msg"] \
                        and "You can still see the full log" not in m["msg"]:
                    issues.append({"level": m["level"], "msg": m["msg"]})
        kubejs.append({"file": os.path.basename(p), "summary": summary, "issues": issues})

    crashes = []
    for p in sorted(glob.glob(os.path.join(crash_dir, "*.txt"))) if crash_dir else []:
        if since and os.path.getmtime(p) < since:
            continue
        with open(p, encoding="utf-8", errors="replace") as f:
            text = f.read()
        desc = re.search(r"^Description: (.*)$", text, re.M)
        trace = text.split("\n\n", 2)[1].splitlines()[:15] if "\n\n" in text else []
        crashes.append({"file": os.path.basename(p), "description": desc[1] if desc else "?", "trace": trace})

    items = list(groups.values())
    real = [g for g in items if not g["known"] and g["phase"] == "startup"]
    return {
        "log": log_path, "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "groups": items,
        "counts": {lvl: sum(g["count"] for g in items if g["level"] == lvl) for lvl in PROBLEM_LEVELS},
        "real_errors": [g for g in real if g["level"] in ("ERROR", "FATAL")],
        "real_warnings": [g for g in real if g["level"] == "WARN"],
        "reload": [g for g in items if not g["known"] and g["phase"] == "reload"],
        "known": [g for g in items if g["known"]],
        "new": [g for g in items if g["new"]] if previous else [],
        "kubejs": kubejs, "crashes": crashes,
        "kubejs_errors": sum(s["errors"] for k in kubejs for s in k["summary"]),
        "ok": not crashes and not [g for g in real if g["level"] in ("ERROR", "FATAL")]
              and not sum(s["errors"] for k in kubejs for s in k["summary"]),
    }


def signatures(result):
    return sorted({g["signature"] for g in result["groups"]})


def render(result, title="Log triage"):
    """Markdown report."""
    out = [f"# {title}", "", f"- Log: `{result['log']}`", f"- Generated: {result['generated']}"]
    c = result["counts"]
    known_n = sum(g["count"] for g in result["known"])
    out.append(f"- Entries: {c['FATAL']} fatal, {c['ERROR']} error, {c['WARN']} warning "
               f"({known_n} of them known-harmless, summarized at the end)")
    out.append(f"- Verdict: **{'OK' if result['ok'] else 'PROBLEMS FOUND'}**")

    def block(g):
        lines = [f"- **{g['level']}** ×{g['count']} `[{g['logger']}]` {g['first'][:240]}" + ("  _(new since last run)_" if g["new"] and result["new"] else "")]
        if g["extra"]:
            lines.append("  ```")
            lines += ["  " + x[:200] for x in g["extra"][:8]]
            lines.append("  ```")
        return lines

    if result["crashes"]:
        out += ["", "## Crash reports"]
        for cr in result["crashes"]:
            out += [f"- `{cr['file']}`: {cr['description']}", "  ```"] + ["  " + t for t in cr["trace"]] + ["  ```"]
    out += ["", "## Errors needing attention"]
    out += sum((block(g) for g in result["real_errors"]), []) or ["- none"]
    out += ["", "## Warnings not on the known list"]
    out += sum((block(g) for g in result["real_warnings"]), []) or ["- none"]
    if result.get("reload") is not None and any(g["phase"] == "reload" for g in result["groups"]):
        out += ["", "## Only after /reload (doesn't affect the verdict)"]
        out += sum((block(g) for g in result["reload"]), []) or ["- none"]
    if result["new"]:
        out += ["", "## New since the previous run"]
        out += [f"- {g['level']} ×{g['count']} `{g['signature'][:200]}`" for g in result["new"]]
    out += ["", "## KubeJS"]
    if not result["kubejs"]:
        out.append("- no KubeJS logs from this run")
    for k in result["kubejs"]:
        for s in k["summary"]:
            out.append(f"- {k['file']}: {s['loaded']}/{s['total']} {s['type']} scripts, {s['errors']} errors, {s['warnings']} warnings")
        for i in k["issues"][:20]:
            out.append(f"  - {i['level']}: {i['msg'][:240]}")
    out += ["", "## Known-harmless"]
    by_note = OrderedDict()
    for g in result["known"]:
        n = by_note.setdefault(g["known"], {"groups": 0, "count": 0, "example": g["first"]})
        n["groups"] += 1
        n["count"] += g["count"]
    out += [f"- ×{n['count']} — {note}  \n  e.g. {n['example'][:140]}" for note, n in by_note.items()] or ["- none"]
    return "\n".join(out) + "\n"
