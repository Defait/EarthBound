"""Latitude/longitude for TFC: Real World worlds (Equal Earth projection).

Mirrors the mod's EqualEarthProjectionStrategy: the world spans
[-horizontal_scale, horizontal_scale] in x and [-vertical_scale, vertical_scale]
in z, mapped onto the map profile's longitude/latitude edges.
"""
import glob
import json
import math
import os
import re
import tomllib
import zipfile

A1, A2, A3, A4 = 1.340264, -0.081106, 0.000893, 0.003796
M = math.sqrt(3) / 2


def forward(phi, dlam):
    """Equal Earth forward projection (radians in, projected units out)."""
    theta = math.asin(M * math.sin(phi))
    t2 = theta * theta
    t6 = t2 * t2 * t2
    den = 3 * (9 * A4 * t6 * t2 + 7 * A3 * t6 + 3 * A2 * t2 + A1)
    x = 2 * math.sqrt(3) * dlam * math.cos(theta) / den
    y = theta * (A1 + A2 * t2 + t6 * (A3 + A4 * t2))
    return x, y


def _theta_from_y(y):
    theta = y / A1
    for _ in range(20):
        t2 = theta * theta
        t6 = t2 * t2 * t2
        f = theta * (A1 + A2 * t2 + t6 * (A3 + A4 * t2)) - y
        fp = A1 + 3 * A2 * t2 + t6 * (7 * A3 + 9 * A4 * t2)
        step = f / fp
        theta -= step
        if abs(step) < 1e-12:
            break
    return theta


class Projection:
    def __init__(self, h, v, west, east, south, north):
        self.h, self.v = h, v
        self.west, self.east, self.south, self.north = west, east, south, north
        self.lam0 = math.radians((west + east) / 2)
        if (east - west) % 360 == 0:
            self.wx, self.ex = forward(0.0, -math.pi)[0], forward(0.0, math.pi)[0]
        else:
            self.wx = forward(0.0, math.radians(west) - self.lam0)[0]
            self.ex = forward(0.0, math.radians(east) - self.lam0)[0]
        self.sy = forward(math.radians(south), 0.0)[1]
        self.ny = forward(math.radians(north), 0.0)[1]

    def to_block(self, lon, lat):
        dlam = math.radians(lon) - self.lam0
        dlam = (dlam + math.pi) % (2 * math.pi) - math.pi
        px, py = forward(math.radians(lat), dlam)
        nx = (px - self.wx) / (self.ex - self.wx)
        ny = 1 - (py - self.sy) / (self.ny - self.sy)
        return nx * 2 * self.h - self.h, ny * 2 * self.v - self.v

    def to_geo(self, x, z):
        nx = (x + self.h) / (2 * self.h)
        ny = 1 - (z + self.v) / (2 * self.v)
        px = self.wx + nx * (self.ex - self.wx)
        py = self.sy + ny * (self.ny - self.sy)
        theta = _theta_from_y(py)
        t2 = theta * theta
        t6 = t2 * t2 * t2
        den = 3 * (9 * A4 * t6 * t2 + 7 * A3 * t6 + 3 * A2 * t2 + A1)
        lat = math.degrees(math.asin(max(-1.0, min(1.0, math.sin(theta) / M))))
        lam = px * den / (2 * math.sqrt(3) * math.cos(theta)) + self.lam0
        lon = (math.degrees(lam) + 180) % 360 - 180
        return lon, lat

    def params(self):
        return {"projection": "EQUAL_EARTH", "h": self.h, "v": self.v, "west": self.west, "east": self.east,
                "south": self.south, "north": self.north}


def load_projection(world_dir, mod_dirs):
    """Projection for a TFC: Real World world, or None if the world doesn't use the mod."""
    conf = os.path.join(world_dir, "serverconfig", "tfc_real_world", "server.toml")
    if not os.path.exists(conf):
        return None
    with open(conf, "rb") as f:
        cfg = tomllib.load(f)
    profile = cfg.get("map_settings", {}).get("map_profile", "DEFAULT:FULL_EQUAL_EARTH")
    gen = cfg.get("generation_modes", {})
    ns, name = profile.lower().split(":", 1) if ":" in profile else ("default", profile.lower())
    settings = None
    for d in mod_dirs:
        for jar in glob.glob(os.path.join(d, "*.jar")):
            try:
                z = zipfile.ZipFile(jar)
                settings = json.loads(z.read(f"data/tfc_real_world/profiles/{ns}/{name}/settings.json"))
                break
            except (KeyError, zipfile.BadZipFile):
                continue
        if settings:
            break
    if not settings or settings.get("map_projection", "EQUAL_EARTH") != "EQUAL_EARTH":
        return None
    return Projection(int(gen.get("horizontal_scale", settings["horizontal_scale"])),
                      int(gen.get("vertical_scale", settings["vertical_scale"])),
                      settings["west_edge_longitude"], settings["east_edge_longitude"],
                      settings["south_edge_latitude"], settings["north_edge_latitude"])
