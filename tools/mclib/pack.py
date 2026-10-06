"""Read the packwiz pack in the repo root."""
import glob
import os
import tomllib

from .paths import REPO


def load_pack(repo=REPO):
    with open(os.path.join(repo, "pack.toml"), "rb") as f:
        return tomllib.load(f)


def loader(pack):
    """Return (loader_name, loader_version) from pack.toml's [versions]."""
    for name in ("neoforge", "forge", "fabric", "quilt"):
        if name in pack["versions"]:
            return name, pack["versions"][name]
    raise SystemExit("pack.toml has no mod loader version")


def mods(repo=REPO):
    """Yield (meta_path, data) for every mods/*.pw.toml."""
    for path in sorted(glob.glob(os.path.join(repo, "mods", "*.pw.toml"))):
        with open(path, "rb") as f:
            yield path, tomllib.load(f)
