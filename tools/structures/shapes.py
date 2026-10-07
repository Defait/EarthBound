"""Procedural structure templates, built from the placeholder materials local_materials rewrites
(rock granite, wood oak, soil alfisol, sand yellow; see docs/lived-in.md).

Every builder takes a seed and returns a Template. Coordinates: x east, y up, z south; `ground` is the template layer that
replaces the topsoil (the structure's start_height is -ground), things stand on ground + 1. Positions never set are
structure void (the world keeps what is there); "minecraft:air" carves.
"""
import math
import random

from nbt import Byte, Double, Int, List, COMPOUND

DATA_VERSION = 3955  # Minecraft 1.21.1

R = "granite"   # placeholder rock
W = "oak"       # placeholder wood
S = "alfisol"   # placeholder soil
AIR = "minecraft:air"


def rock(variant, shape=""):
    return f"tfc:rock/{variant}/{R}{shape}"


def wood(variant, shape=""):
    return f"tfc:wood/{variant}/{W}{shape}"


def soil(kind):
    return f"tfc:{kind}/{S}"


class Template:
    def __init__(self, ground=0):
        self.ground = ground
        self.blocks = {}
        self.entities = []

    def set(self, x, y, z, name, nbt=None, **props):
        self.blocks[(x, y, z)] = (name, {k: (str(v).lower() if isinstance(v, bool) else str(v)) for k, v in props.items()}, nbt)

    def get(self, x, y, z):
        b = self.blocks.get((x, y, z))
        return b[0] if b else None

    def fill(self, x0, y0, z0, x1, y1, z1, name, **props):
        for x in range(min(x0, x1), max(x0, x1) + 1):
            for y in range(min(y0, y1), max(y0, y1) + 1):
                for z in range(min(z0, z1), max(z0, z1) + 1):
                    self.set(x, y, z, name, **props)

    def chest(self, x, y, z, loot, facing="north"):
        self.set(x, y, z, wood("chest"), {"id": "tfc:chest", "LootTable": loot}, facing=facing, type="single")

    def to_nbt(self):
        if not self.blocks:
            raise ValueError("empty template")
        _shift_to_origin(self)
        xs, ys, zs = zip(*self.blocks)
        size = [max(xs) + 1, max(ys) + 1, max(zs) + 1]
        palette, index, blocks = [], {}, []
        for pos in sorted(self.blocks, key=lambda p: (p[1], p[2], p[0])):
            name, props, nbt = self.blocks[pos]
            key = (name, tuple(sorted(props.items())))
            if key not in index:
                index[key] = len(palette)
                entry = {"Name": name}
                if props:
                    entry["Properties"] = dict(sorted(props.items()))
                palette.append(entry)
            b = {"pos": List([Int(c) for c in pos]), "state": Int(index[key])}
            if nbt is not None:
                b["nbt"] = nbt
            blocks.append(b)
        entities = List([{"pos": List([Double(c) for c in e["pos"]]), "blockPos": List([Int(math.floor(c)) for c in e["pos"]]), "nbt": e["nbt"]}
                         for e in self.entities], kind=COMPOUND)
        return {"DataVersion": Int(DATA_VERSION), "size": List([Int(s) for s in size]), "palette": List(palette, kind=COMPOUND),
                "blocks": List(blocks, kind=COMPOUND), "entities": entities}

    def stats(self):
        xs, ys, zs = zip(*self.blocks)
        return f"{max(xs) + 1}x{max(ys) + 1}x{max(zs) + 1}, {len(self.blocks)} blocks"


def disk(cx, cz, r):
    for x in range(math.floor(cx - r), math.ceil(cx + r) + 1):
        for z in range(math.floor(cz - r), math.ceil(cz + r) + 1):
            if (x - cx) ** 2 + (z - cz) ** 2 <= r * r + 0.01:
                yield x, z


def loose(t, rng, x, y, z):
    t.set(x, y, z, rock("loose"), count=rng.randint(1, 3))


# ------------------------------------------------------------------ cairn
def cairn(seed, cist=False, loot="pack:chests/cairn"):
    """A cone of stones on high ground; with a cist, a stone box holding grave goods at its heart."""
    rng = random.Random(seed)
    t = Template(ground=0)
    c = 4
    height = rng.randint(4, 5) if not cist else 4
    base = rng.uniform(2.3, 2.8)
    for y in range(0, height + 1):
        r = base * (1 - y / (height + 1)) + 0.35
        for x, z in disk(c, c, r):
            edge = (x - c) ** 2 + (z - c) ** 2 > (r - 0.9) ** 2
            if edge and y > 0 and rng.random() < 0.25:
                continue
            if y == 0:
                t.set(x, 0, z, rock("raw"))
            elif y == 1 and edge:
                t.set(x, y, z, rock("mossy_cobble"))
            else:
                t.set(x, y, z, rock("raw"))
    top = max(y for (x, y, z) in t.blocks if (x, z) == (c, c))
    t.set(c, top + 1, c, rock("raw", "_slab"), type="bottom")
    for x, z in disk(c, c, 4.2):
        if (x, 1, z) not in t.blocks and rng.random() < 0.3:
            t.set(x, 0, z, soil("coarse_dirt"))
            t.set(x, 1, z, rock("mossy_loose" if rng.random() < 0.4 else "loose"), count=rng.randint(1, 3))
    if cist:
        t.set(c, 1, c, AIR)
        t.chest(c, 1, c, loot, facing=rng.choice(["north", "south", "east", "west"]))
        t.set(c, 2, c, rock("smooth", "_slab"), type="top")
    return t


# ------------------------------------------------------------------ standing stones
def _menhir(t, rng, x, z, height, thick=False):
    t.set(x, -1, z, rock("raw"))
    t.set(x, 0, z, rock("raw"))
    for y in range(1, height + 1):
        t.set(x, y, z, rock("raw"))
        if thick and y < height:
            t.set(x + 1, y, z, rock("raw"))
            t.set(x + 1, 0, z, rock("raw"))
    if rng.random() < 0.5:
        t.set(x, height + 1, z, rock("raw", "_slab"), type="bottom")
    for dx, dz in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        if (x + dx, 1, z + dz) not in t.blocks and rng.random() < 0.35:
            t.set(x + dx, 0, z + dz, soil("coarse_dirt"))
            t.set(x + dx, 1, z + dz, rock("mossy_loose"), count=rng.randint(1, 2))


def standing_stones(seed, kind, offering=False, loot="pack:chests/standing_stones_offering"):
    """A lone menhir, a pair, a short row or a ring; an offering variant hides a chest under the middle."""
    rng = random.Random(seed)
    t = Template(ground=0)
    if kind == "single":
        _menhir(t, rng, 2, 2, rng.randint(3, 5), thick=rng.random() < 0.5)
        mid = (2, 3)
    elif kind == "pair":
        _menhir(t, rng, 1, 2, rng.randint(3, 4))
        _menhir(t, rng, 5, 2, rng.randint(3, 4))
        mid = (3, 2)
    elif kind == "row":
        n = rng.randint(4, 5)
        for i in range(n):
            _menhir(t, rng, 1 + i * 3, 2 + rng.choice([0, 0, 1]), rng.randint(2, 4))
        mid = (1 + (n // 2) * 3, 4)
    else:
        n, r = rng.randint(8, 11), rng.uniform(5.5, 7.0)
        c = 8
        for i in range(n):
            if rng.random() < 0.15:
                continue
            a = 2 * math.pi * i / n + rng.uniform(-0.1, 0.1)
            _menhir(t, rng, round(c + r * math.cos(a)), round(c + r * math.sin(a)), rng.randint(2, 4))
        t.set(c, 0, c, rock("smooth"))
        t.set(c, 1, c, rock("smooth", "_slab"), type="bottom")
        mid = (c, c)
    if offering:
        x, z = mid
        t.chest(x, -1, z, loot)
        t.set(x, 0, z, soil("dirt"))
    t.ground = 0
    return _shift_to_origin(t)


# ------------------------------------------------------------------ hunters' camp
def hunters_camp(seed, shelters=1, loot="pack:chests/hunters_camp"):
    """A season's camp: a firepit ringed with stones, lean-tos of logs and thatch, a drying frame, bones and flint."""
    rng = random.Random(seed)
    t = Template(ground=0)
    fx, fz = 6, 6
    for x, z in disk(fx, fz, 3.2):
        t.set(x, 0, z, soil("coarse_dirt" if rng.random() < 0.6 else "grass_path"))
    t.set(fx, 0, fz, soil("coarse_dirt"))
    t.set(fx, 1, fz, "tfc:firepit", lit=False, axis=rng.choice(["x", "z"]))
    for dx in (-1, 0, 1):
        for dz in (-1, 0, 1):
            if (dx, dz) != (0, 0) and rng.random() < 0.8:
                t.set(fx + dx, 0, fz + dz, soil("coarse_dirt"))
                t.set(fx + dx, 1, fz + dz, rock("loose"), count=rng.randint(1, 3))
    spots = [(1, 1), (8, 1)][:shelters]
    for i, (sx, sz) in enumerate(spots):
        for x in range(sx, sx + 4):
            for z in range(sz, sz + 3):
                t.set(x, 0, z, soil("coarse_dirt"))
        for x in (sx, sx + 3):
            t.set(x, 1, sz, wood("log"), axis="y")
            t.set(x, 2, sz, wood("log"), axis="y")
            t.set(x, 1, sz + 2, wood("log_fence"))
        for x in range(sx, sx + 4):
            t.set(x, 3, sz, "tfc:thatch")
            t.set(x, 2, sz + 1, "tfc:thatch")
            t.set(x, 2, sz + 2, wood("log"), axis="x")
        if i == 0:
            t.chest(sx + 1, 1, sz, loot, facing="south")
    # drying frame
    dx0 = 9 if shelters == 1 else 2
    t.set(dx0, 1, 10, wood("log_fence"))
    t.set(dx0 + 2, 1, 10, wood("log_fence"))
    t.set(dx0, 2, 10, wood("log_fence"))
    t.set(dx0 + 2, 2, 10, wood("log_fence"))
    t.fill(dx0, 3, 10, dx0 + 2, 3, 10, wood("log"), axis="x")
    for x in range(dx0, dx0 + 3):
        t.set(x, 0, 10, soil("coarse_dirt"))
    for _ in range(9):
        x, z = rng.randint(2, 11), rng.randint(4, 11)
        if (x, 1, z) not in t.blocks:
            t.set(x, 0, z, soil("coarse_dirt"))
            t.set(x, 1, z, rng.choice(["tfc:groundcover/bone", "tfc:groundcover/flint", "tfc:groundcover/stick", "tfc:groundcover/feather"]))
    for x in range(1, 4):
        t.set(x + 7, 1, 12, wood("log"), axis="x")
        t.set(x + 7, 0, 12, soil("coarse_dirt"))
    return t


# ------------------------------------------------------------------ wayside shrine
def wayside_shrine(seed, with_chest=False, loot="pack:chests/wayside_shrine"):
    """A knee-high stone niche under a slab roof, a candle, a path in front; sometimes an offering box."""
    rng = random.Random(seed)
    t = Template(ground=0)
    t.fill(0, 0, 0, 2, 0, 2, rock("bricks"))
    t.fill(0, 1, 0, 2, 2, 0, rock("bricks"))
    for y in (1, 2):
        t.set(0, y, 1, rock("bricks"))
        t.set(2, y, 1, rock("bricks"))
    t.set(1, 1, 1, AIR)
    t.set(1, 2, 1, AIR)
    t.fill(0, 3, 0, 2, 3, 1, rock("smooth", "_slab"), type="bottom")
    t.set(1, 3, 2, rock("bricks", "_stairs"), facing="north", half="top", shape="straight")
    if with_chest:
        t.chest(1, 1, 1, loot, facing="south")
        t.set(0, 3, 2, "tfc:candle", candles=rng.randint(1, 3), lit=False)
        t.set(0, 2, 2, rock("bricks"))
        t.set(0, 0, 2, rock("bricks"))
        t.set(0, 1, 2, rock("bricks"))
    else:
        t.set(1, 1, 1, "tfc:candle", candles=rng.randint(1, 4), lit=False)
    for z in range(3, 3 + rng.randint(2, 4)):
        t.set(1, 0, z, soil("grass_path"))
    t.set(0, 0, 3, soil("grass_path"))
    t.set(2, 0, 3, soil("grass_path"))
    return t


# ------------------------------------------------------------------ barrow and graveyard
def barrow(seed, loot="pack:chests/barrow"):
    """A long earthen mound with a stone-lined passage to a chamber of grave goods."""
    rng = random.Random(seed)
    g = 1
    t = Template(ground=g)
    a, b, cx, cz = 4.6, 8.0, 5, 9
    hmax = 4
    for x in range(0, 11):
        for z in range(0, 19):
            q = 1 - ((x - cx) / a) ** 2 - ((z - cz) / b) ** 2
            if q <= 0:
                continue
            h = max(1, round(hmax * math.sqrt(q)))
            t.set(x, g, z, soil("dirt"))
            for y in range(g + 1, g + h):
                t.set(x, y, z, soil("dirt"))
            t.set(x, g + h, z, soil("grass"))
    # passage from the south-facing front (low z) to the chamber
    px = cx
    for z in range(1, 11):
        t.set(px, g, z, rock("smooth"))
        for y in (g + 1, g + 2):
            t.set(px, y, z, AIR)
            t.set(px - 1, y, z, rock("raw"))
            t.set(px + 1, y, z, rock("raw"))
        t.set(px, g + 3, z, rock("raw", "_slab"), type="top")
        t.set(px - 1, g + 3, z, rock("raw"))
        t.set(px + 1, g + 3, z, rock("raw"))
    # chamber 3x3 interior
    for x in range(px - 1, px + 2):
        for z in range(11, 14):
            t.set(x, g, z, rock("smooth"))
            for y in (g + 1, g + 2):
                t.set(x, y, z, AIR)
            t.set(x, g + 3, z, rock("raw"))
    for y in (g + 1, g + 2):
        for z in range(11, 14):
            t.set(px - 2, y, z, rock("raw"))
            t.set(px + 2, y, z, rock("raw"))
        for x in range(px - 2, px + 3):
            t.set(x, y, 14, rock("raw"))
        t.set(px - 1, y, 10, rock("raw"))
        t.set(px + 1, y, 10, rock("raw"))
    for z in range(0, 15):
        for x in range(px - 2, px + 3):
            if t.get(x, g, z) in (rock("smooth"), rock("raw")) or (abs(x - px) <= 1 and z <= 14):
                t.set(x, g - 1, z, rock("raw"))
    t.chest(px, g + 1, 13, loot, facing="north")
    t.set(px - 1, g + 1, 13, "tfc:groundcover/bone")
    t.set(px + 1, g + 1, 12, rock("smooth", "_slab"), type="bottom")
    # portal stones and capstone at the entrance
    for x in (px - 1, px + 1):
        for y in range(g + 1, g + 4):
            t.set(x, y, 0, rock("raw"))
    t.set(px, g + 3, 0, rock("raw"))
    t.set(px, g + 1, 0, AIR)
    t.set(px, g + 2, 0, AIR)
    t.set(px, g, 0, rock("smooth"))
    # the ground under everything stays: ensure no dirt fills the passage mouth
    for y in range(g + 1, g + 3):
        t.set(px, y, 1, AIR)
    if rng.random() < 0.5:
        t.set(px + 2, g + 1, 0, rock("mossy_loose"), count=2)
        t.set(px + 2, g, 0, soil("coarse_dirt"))
    return _shift_to_origin(t)


def graveyard(seed, loot="pack:chests/barrow"):
    """A small fenced plot of slab headstones over low grave mounds; grave goods under one of them."""
    rng = random.Random(seed)
    g = 1
    t = Template(ground=g)
    w, d = 9, 9
    for x in range(w):
        for z in range(d):
            edge = x in (0, w - 1) or z in (0, d - 1)
            if edge:
                if not (z == d - 1 and x == w // 2):
                    if rng.random() < 0.85:
                        t.set(x, g + 1, z, wood("fence"))
            t.set(x, g, z, soil("grass"))
    t.set(w // 2, g + 1, d - 1, wood("fence_gate"), facing="south", open=False)
    graves = [(2, 2), (4, 2), (6, 2), (2, 5), (4, 5), (6, 5)]
    rng.shuffle(graves)
    for i, (x, z) in enumerate(graves[:rng.randint(4, 6)]):
        if rng.random() < 0.5:
            t.set(x, g + 1, z, rock("raw", "_wall"), up=True)
        else:
            t.set(x, g + 1, z, rock("smooth", "_slab"), type="bottom")
        t.set(x, g + 1, z + 1, soil("coarse_dirt"))
        t.set(x, g, z + 1, soil("dirt"))
        if i == 0:
            t.chest(x, g - 1, z + 1, loot)
    return t


def _shift_to_origin(t):
    xs, ys, zs = zip(*t.blocks)
    mx, my, mz = min(xs), min(ys), min(zs)
    if (mx, my, mz) != (0, 0, 0):
        t.blocks = {(x - mx, y - my, z - mz): v for (x, y, z), v in t.blocks.items()}
        t.ground -= my
    return t


# ------------------------------------------------------------------ mine adit
def mine_adit(seed, loot="pack:chests/mine_adit"):
    """An inclined drift: a timbered portal, an open cut that turns into a tunnel, steps down ~10 blocks, a short gallery
    with ore left in the walls, a cave-in at the end, and a crate of gear. Below ground the walls and roof are a shell of
    raw rock, so the drift holds whatever it cuts through."""
    rng = random.Random(seed)
    steps, gallery = 10, 7
    g = steps + 1
    t = Template(ground=g)
    x0, x1 = 2, 4                       # interior x; walls at x0 - 1 and x1 + 1

    def section(z, floor, stairs):
        for x in range(x0 - 1, x1 + 2):
            t.set(x, floor, z, rock("raw"))
        for y in range(floor + 1, floor + 4):
            for x in range(x0, x1 + 1):
                t.set(x, y, z, AIR)
            if y <= g:
                t.set(x0 - 1, y, z, rock("raw"))
                t.set(x1 + 1, y, z, rock("raw"))
        if floor + 4 <= g:
            for x in range(x0 - 1, x1 + 2):
                t.set(x, floor + 4, z, rock("raw"))
        if stairs:
            for x in range(x0, x1 + 1):
                t.set(x, floor + 1, z, rock("raw", "_stairs"), facing="north", half="bottom", shape="straight")

    def frame(z, floor):
        for y in (floor + 1, floor + 2):
            t.set(x0, y, z, wood("vertical_support"))
            t.set(x1, y, z, wood("vertical_support"))
        t.set(x0, floor + 3, z, wood("horizontal_support"), east=True)
        t.set(x0 + 1, floor + 3, z, wood("horizontal_support"), east=True, west=True)
        t.set(x1, floor + 3, z, wood("horizontal_support"), west=True)

    # portal on the ground at the head of the cut
    for x in range(x0 - 1, x1 + 2):
        t.set(x, g, 0, rock("raw"))
    frame(0, g)
    for i in range(1, steps + 1):
        section(i, g - i, stairs=True)
    gfloor = g - steps - 1
    for j in range(gallery):
        z = steps + 1 + j
        section(z, gfloor, stairs=False)
        if j % 3 == 1:
            frame(z, gfloor)
        elif j % 3 == 0:
            t.set(x0, gfloor + 2, z, "tfc:dead_wall_torch", facing="east")
        for side in (x0 - 1, x1 + 1):
            for y in range(gfloor + 1, gfloor + 4):
                if rng.random() < 0.14:
                    t.set(side, y, z, rng.choice(["tfc:ore/poor_native_copper/granite", "tfc:ore/poor_malachite/granite",
                                                  "tfc:ore/poor_tetrahedrite/granite"]))
    zc = steps + gallery
    for x in range(x0, x1 + 1):
        for y in range(gfloor + 1, gfloor + 4):
            if y == gfloor + 1 or rng.random() < 0.7:
                t.set(x, y, zc, rock("gravel") if rng.random() < 0.5 else rock("cobble"))
    t.chest(x1, gfloor + 1, zc - 1, loot, facing="west")
    for (x, z) in [(6, 0), (6, 1), (7, 0), (6, 2)]:
        t.set(x, g, z, rock("gravel"))
        if rng.random() < 0.6:
            t.set(x, g + 1, z, rock("gravel"))
    return t


# ------------------------------------------------------------------ collapsed bloomery smithy
def bloomery_ruin(seed, loot="pack:chests/bloomery_ruin"):
    """A roofless stone smithy: its chimney fallen into a heap of bricks, charcoal in the corner, a stone anvil, a chest."""
    rng = random.Random(seed)
    t = Template(ground=0)
    w, d = 11, 9
    door = rng.randint(3, 7)
    for x in range(w):
        for z in range(d):
            t.set(x, 0, z, rock("smooth") if rng.random() < 0.7 else rock("gravel"))
    for x in range(w):
        for z in range(d):
            if x in (0, w - 1) or z in (0, d - 1):
                if z == d - 1 and x in (door, door + 1):
                    continue
                h = rng.choice([1, 1, 2, 2, 3])
                for y in range(1, h + 1):
                    t.set(x, y, z, rock("bricks"))
                if rng.random() < 0.3:
                    t.set(x, h + 1, z, rock("bricks", "_slab"), type="bottom")
    # collapsed chimney heap in the back corner
    for x in range(1, 4):
        for z in range(1, 4):
            hh = 3 - max(abs(x - 1), abs(z - 1))
            for y in range(1, hh + 1):
                t.set(x, y, z, rock("cracked_bricks") if rng.random() < 0.5 else rock("bricks"))
    t.set(2, 1, 2, "tfc:charcoal_pile", layers=rng.randint(2, 6))
    for (x, z) in [(4, 1), (4, 2), (1, 4)]:
        t.set(x, 1, z, "tfc:charcoal_pile", layers=rng.randint(1, 4))
    t.set(7, 1, 3, rock("anvil"))
    t.chest(w - 2, 1, d - 3, loot, facing="west")
    for x in range(5, 9):
        if rng.random() < 0.7:
            t.set(x, 1, 5, wood("log"), axis="x")
    for _ in range(6):
        x, z = rng.randint(-2, w + 1), rng.choice([-1, -2, d, d + 1])
        if (x, 1, z) not in t.blocks:
            t.set(x, 1, z, rock("bricks", "_slab"), type="bottom")
    return _shift_to_origin(t)


# ------------------------------------------------------------------ coastal wreck
def wreck(seed, loot="pack:chests/wreck"):
    """A plank-built hull settled into the beach sand, ribs showing, a broken mast stump, cargo in the hold."""
    rng = random.Random(seed)
    g = 2
    t = Template(ground=g)
    length, cx = 17, 4
    for z in range(length):
        u = (z - (length - 1) / 2) / ((length - 1) / 2)
        half = max(1, round(3.2 * math.sqrt(max(0.0, 1 - u * u))))
        t.set(cx, 0, z, wood("log"), axis="z")
        for x in range(cx - half, cx + half + 1):
            if x != cx:
                t.set(x, 0, z, wood("planks"))
        for y in range(1, 4 if abs(u) < 0.8 else 3):
            for x in (cx - half, cx + half):
                if rng.random() < 0.78:
                    t.set(x, y, z, wood("planks"))
            for x in range(cx - half + 1, cx + half):
                if y == 1:
                    t.set(x, y, z, "tfc:sand/yellow")
                else:
                    t.set(x, y, z, AIR)
        if z % 3 == 1 and abs(u) < 0.85:
            for x in (cx - half, cx + half):
                for y in range(1, 5):
                    t.set(x, y, z, wood("stripped_log"), axis="y")
    for y in range(1, 4 + rng.randint(0, 2)):
        t.set(cx, y, length // 2, wood("log"), axis="y")
    t.chest(cx - 1, 2, 6, loot, facing="east")
    t.chest(cx + 1, 2, 11, loot, facing="west")
    for _ in range(10):
        x, z = rng.randint(-2, 10), rng.randint(-2, length + 1)
        if (x, g, z) not in t.blocks and (x, g + 1, z) not in t.blocks:
            t.set(x, g, z, "tfc:sand/yellow")
            t.set(x, g + 1, z, "tfc:groundcover/driftwood")
    return _shift_to_origin(t)


# ------------------------------------------------------------------ prospector's camp
def prospector_camp(seed, loot="pack:chests/prospector_camp"):
    """An A-frame tent, a plank table with ore samples laid out, a fire ring, a woodpile."""
    rng = random.Random(seed)
    t = Template(ground=0)
    for x in range(0, 12):
        for z in range(0, 10):
            if rng.random() < 0.55:
                t.set(x, 0, z, soil("coarse_dirt"))
    tz0, tz1 = 1, 4
    for z in range(tz0, tz1 + 1):
        t.set(1, 1, z, wood("planks", "_stairs"), facing="east", half="bottom", shape="straight")
        t.set(2, 2, z, wood("planks", "_stairs"), facing="east", half="bottom", shape="straight")
        t.set(3, 3, z, wood("planks", "_slab"), type="bottom")
        t.set(4, 2, z, wood("planks", "_stairs"), facing="west", half="bottom", shape="straight")
        t.set(5, 1, z, wood("planks", "_stairs"), facing="west", half="bottom", shape="straight")
        for x in range(1, 6):
            t.set(x, 0, z, soil("coarse_dirt"))
    for x in range(2, 5):
        t.set(x, 1, tz0, "tfc:thatch")
    t.set(3, 2, tz0, "tfc:thatch")
    t.chest(3, 1, tz0 + 1, loot, facing="south")
    # sample table
    for x in range(7, 10):
        t.set(x, 0, 2, soil("coarse_dirt"))
        t.set(x, 1, 2, wood("planks"))
        t.set(x, 2, 2, rng.choice(["tfc:ore/small_malachite", "tfc:ore/small_native_copper", "tfc:ore/small_cassiterite",
                                   "tfc:ore/small_tetrahedrite", "tfc:ore/small_hematite"]))
    # fire ring
    fx, fz = 8, 6
    for dx in (-1, 0, 1):
        for dz in (-1, 0, 1):
            t.set(fx + dx, 0, fz + dz, soil("coarse_dirt"))
            if (dx, dz) != (0, 0):
                t.set(fx + dx, 1, fz + dz, rock("cobble"))
    t.set(fx, 1, fz, "tfc:firepit", lit=False, axis="x")
    for x in range(1, 4):
        t.set(x, 1, 7, wood("log"), axis="x")
        t.set(x, 0, 7, soil("coarse_dirt"))
    t.set(2, 2, 7, wood("log"), axis="x")
    return t


BUILDERS = {
    "cairn": cairn, "standing_stones": standing_stones, "hunters_camp": hunters_camp, "wayside_shrine": wayside_shrine,
    "barrow": barrow, "graveyard": graveyard, "mine_adit": mine_adit, "bloomery_ruin": bloomery_ruin, "wreck": wreck,
    "prospector_camp": prospector_camp,
}
