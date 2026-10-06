"""Well-known locations and Java discovery."""
import glob
import os
import re
import shutil
import subprocess
import sys

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TOOLS)
SERVER_DIR = os.path.join(TOOLS, ".server")
DATA_DIR = os.path.join(TOOLS, ".data")
PRISM = os.path.join(os.environ.get("APPDATA", ""), "PrismLauncher")
DEFAULT_INSTANCE = os.environ.get("WORLDVIEW_INSTANCE") or os.path.join(PRISM, "instances", "GregWorld", "minecraft")


def utf8_console():
    """Make print() safe for non-ASCII output on Windows consoles and pipes."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def java_major(java):
    try:
        out = subprocess.run([java, "-version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r'version "(\d+)(?:\.(\d+))?', out.stderr + out.stdout)
    if not m:
        return None
    major = int(m.group(1))
    return int(m.group(2)) if major == 1 else major


def find_java(major=21):
    """Return a java executable of the given major version.

    Checks $MC_JAVA, $JAVA_HOME, Prism's managed runtimes, then PATH.
    """
    exe = "java.exe" if os.name == "nt" else "java"
    candidates = []
    if os.environ.get("MC_JAVA"):
        candidates.append(os.environ["MC_JAVA"])
    if os.environ.get("JAVA_HOME"):
        candidates.append(os.path.join(os.environ["JAVA_HOME"], "bin", exe))
    candidates += sorted(glob.glob(os.path.join(PRISM, "java", "*", "bin", exe)))
    if shutil.which("java"):
        candidates.append(shutil.which("java"))
    for c in candidates:
        if os.path.exists(c) and java_major(c) == major:
            return c
    raise SystemExit(f"No Java {major} found. Set MC_JAVA to a Java {major} java executable.")
