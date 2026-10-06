"""A headless NeoForge test server built from the pack.

The server lives in tools/.server. NeoForge is (re)installed when the pack's
loader version changes, mods and config are synced with packwiz-installer
(server side) from a local `packwiz serve`, and tools can add extra mods or
dev-only KubeJS scripts for a single run without touching the pack.
"""
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import urllib.request

from .pack import load_pack, loader
from .paths import REPO, SERVER_DIR, find_java

NEOFORGE_INSTALLER = "https://maven.neoforged.net/releases/net/neoforged/neoforge/{v}/neoforge-{v}-installer.jar"
BOOTSTRAP_URL = "https://github.com/packwiz/packwiz-installer-bootstrap/releases/latest/download/packwiz-installer-bootstrap.jar"
DONE_RE = re.compile(r"Done \((\d+(?:\.\d+)?)s\)! For help")
USER_PACKWIZ_PORT = 8080
OWN_PACKWIZ_PORT = 8199


def download(url, dest, log=print):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    log(f"Downloading {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "mc-pack-tools"})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest + ".part", "wb") as f:
        shutil.copyfileobj(r, f)
    os.replace(dest + ".part", dest)
    return dest


class PackServer:
    """Serve the repo's pack over HTTP for packwiz-installer.

    Reuses a `packwiz serve` already running on :8080 when it serves this
    repo's pack.toml; otherwise starts one on :8199 for the duration.
    """

    def __init__(self, log=print):
        self.log = log
        self.proc = None
        self.url = None

    def _get(self, url):
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                return r.read()
        except OSError:
            return None

    def __enter__(self):
        with open(os.path.join(REPO, "pack.toml"), "rb") as f:
            ours = f.read().replace(b"\r\n", b"\n")
        existing = self._get(f"http://127.0.0.1:{USER_PACKWIZ_PORT}/pack.toml")
        # The served pack.toml may have a fresher index hash than the file on disk,
        # so compare everything except the hash line.
        strip = lambda b: re.sub(rb"(?m)^hash = .*$", b"", b.replace(b"\r\n", b"\n"))
        if existing is not None and strip(existing) == strip(ours):
            self.url = f"http://127.0.0.1:{USER_PACKWIZ_PORT}/pack.toml"
            self.log(f"Using the running packwiz serve at {self.url}")
            return self.url
        self.proc = subprocess.Popen(["packwiz", "serve", "--port", str(OWN_PACKWIZ_PORT)], cwd=REPO,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.url = f"http://127.0.0.1:{OWN_PACKWIZ_PORT}/pack.toml"
        for _ in range(100):
            if self._get(self.url):
                self.log(f"Started packwiz serve at {self.url}")
                return self.url
            time.sleep(0.2)
        self.proc.kill()
        raise SystemExit("packwiz serve did not start")

    def __exit__(self, *exc):
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()


class TestServer:
    def __init__(self, root=SERVER_DIR, java=None, log=print):
        self.root = root
        self.log = log
        self.java = java or find_java(21)
        self.pack = load_pack()
        self.loader, self.loader_version = loader(self.pack)
        if self.loader != "neoforge":
            raise SystemExit(f"Test server only supports NeoForge packs (pack uses {self.loader})")
        self.proc = None
        self.lines = []
        self._q = queue.Queue()
        os.makedirs(root, exist_ok=True)

    def path(self, *parts):
        return os.path.join(self.root, *parts)

    # ------------------------------------------------------------- install
    def ensure_installed(self):
        marker = self.path(".installed-neoforge")
        v = self.loader_version
        args = self.path("libraries", "net", "neoforged", "neoforge", v, "win_args.txt" if os.name == "nt" else "unix_args.txt")
        if os.path.exists(marker) and open(marker).read().strip() == v and os.path.exists(args):
            return
        inst = self.path(".cache", f"neoforge-{v}-installer.jar")
        if not os.path.exists(inst):
            download(NEOFORGE_INSTALLER.format(v=v), inst, self.log)
        self.log(f"Installing NeoForge {v} server (downloads the vanilla server and libraries)...")
        r = subprocess.run([self.java, "-jar", inst, "--install-server", self.root], cwd=self.root,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0 or not os.path.exists(args):
            raise SystemExit("NeoForge installer failed:\n" + (r.stdout + r.stderr)[-4000:])
        with open(marker, "w") as f:
            f.write(v)
        # The pack owner accepted the Minecraft EULA (https://aka.ms/MinecraftEULA) for this local test server.
        with open(self.path("eula.txt"), "w") as f:
            f.write("# Accepted by the pack owner for the local test server: https://aka.ms/MinecraftEULA\neula=true\n")

    def sync_pack(self):
        boot = self.path("packwiz-installer-bootstrap.jar")
        if not os.path.exists(boot):
            local = os.path.join(REPO, "packwiz-installer-bootstrap.jar")
            if os.path.exists(local):
                shutil.copy2(local, boot)
            else:
                download(BOOTSTRAP_URL, boot, self.log)
        with PackServer(self.log) as url:
            self.log("Syncing pack (server side)...")
            r = subprocess.run([self.java, "-jar", boot, "-g", "-s", "server", url], cwd=self.root,
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            raise SystemExit("packwiz-installer failed:\n" + (r.stdout + r.stderr)[-4000:])

    # ------------------------------------------------- per-run extras
    def _managed(self, kind, wanted):
        """Copy files in for this run and remove ones a previous run added.

        kind names the tracking file; wanted maps server-relative paths to source files.
        """
        track = self.path(f".{kind}.json")
        previous = json.load(open(track)) if os.path.exists(track) else []
        for rel in previous:
            if rel not in wanted and os.path.exists(self.path(rel)):
                os.remove(self.path(rel))
        for rel, src in wanted.items():
            os.makedirs(os.path.dirname(self.path(rel)), exist_ok=True)
            shutil.copy2(src, self.path(rel))
        with open(track, "w") as f:
            json.dump(sorted(wanted), f)

    def set_extra_mods(self, jars):
        """jars: list of jar paths to put in mods/ for this run only."""
        self._managed("extra-mods", {os.path.join("mods", os.path.basename(j)): j for j in jars})

    def set_dev_scripts(self, scripts):
        """scripts: {"name.js": source_path} placed in local/kubejs/local_server_scripts for this run only.

        KubeJS loads that folder alongside kubejs/server_scripts, and it is never part of the pack.
        """
        self._managed("dev-scripts", {os.path.join("local", "kubejs", "local_server_scripts", rel): src
                                      for rel, src in scripts.items()})

    def write_properties(self, level_name, seed="", extra=None):
        props = {
            "level-name": level_name, "level-seed": str(seed), "level-type": "tfc\\:overworld",
            "online-mode": "false", "server-ip": "127.0.0.1", "server-port": "25599",
            "max-tick-time": "-1", "view-distance": "6", "simulation-distance": "4", "spawn-protection": "0",
            "enable-rcon": "false", "enable-query": "false", "motd": "pack test server",
        }
        props.update(extra or {})
        with open(self.path("server.properties"), "w") as f:
            f.write("".join(f"{k}={v}\n" for k, v in props.items()))

    # --------------------------------------------------------- running
    def start(self, xmx="6G"):
        args_file = "win_args.txt" if os.name == "nt" else "unix_args.txt"
        cmd = [self.java, f"-Xmx{xmx}", f"@libraries/net/neoforged/neoforge/{self.loader_version}/{args_file}", "nogui"]
        self.lines = []
        self.proc = subprocess.Popen(cmd, cwd=self.root, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1)
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        for line in self.proc.stdout:
            line = line.rstrip("\n")
            self.lines.append(line)
            self._q.put(line)
        self._q.put(None)

    def wait_for(self, pattern, timeout, echo=None):
        """Wait for a console line matching pattern. Returns the match, or None on exit/timeout."""
        rx = re.compile(pattern)
        end = time.time() + timeout
        while time.time() < end:
            try:
                line = self._q.get(timeout=1)
            except queue.Empty:
                continue
            if line is None:
                return None
            if echo and echo.search(line):
                self.log("  " + line)
            m = rx.search(line)
            if m:
                return m
        return None

    def command(self, cmd):
        if self.proc and self.proc.poll() is None:
            self.proc.stdin.write(cmd + "\n")
            self.proc.stdin.flush()

    def stop(self, timeout=240):
        if not self.proc:
            return None
        if self.proc.poll() is None:
            self.command("stop")
            try:
                self.proc.wait(timeout)
            except subprocess.TimeoutExpired:
                self.log("Server did not stop in time; killing it")
                self.proc.kill()
                self.proc.wait()
        return self.proc.returncode
