#!/usr/bin/env python3
"""Sea-floor deposit textures, models and a review sheet (docs/design.md, "Deep sea").

Generates, deterministically (fixed seeds, no numpy), the 16x16 block textures of the five deposits and the loose nodule,
the two model files that are not vanilla cubes, and a preview sheet:

    python tools/sea_textures.py                      # write PNGs and models under kubejs/assets/pack/
    python tools/sea_textures.py --preview PATH       # also render the review sheet (needs the TFC jar for the floor swatches)
    python tools/sea_textures.py --out DIR            # another assets root (default: <repo>/kubejs/assets/pack)

Every colour is in the PALETTES table below; tweak there and run again. Textures are drawn procedurally from small
palettes (4 to 6 shades per material, like TFC's rock textures), with torus-wrapped bump maps for the lumps (lit from the
upper left) so each tile repeats without a seam. Nothing is copied from another mod: TFC's textures are only read, for
their palette and for the floor in the preview.
"""
import argparse, json, math, os, random, sys, zipfile, io, glob
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W = 16


def hexc(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


PALETTES = {
    # black smoker: dark iron-copper-zinc sulfide, rust oxide, sulfur, brass flecks
    'sulf': ['#14110f', '#1d1917', '#282320', '#342e2a', '#443c36', '#574d44'],
    'rust': ['#5a2c15', '#703819', '#85441e', '#9a5326'],
    'sulfur': ['#b9a232', '#d3bd47', '#e6d36a'],
    'brass': ['#6f6232', '#8d7d3c', '#b09c52'],
    'glow': ['#a8421a', '#cf6a2a', '#ec8d3d', '#f6b25a'],
    'hole_b': ['#050404', '#0d0907', '#1a0f0a', '#2e140a'],
    # mound: rubble of sulfide and anhydrite
    'rubble': ['#1c1a19', '#292624', '#37322f', '#48413c', '#5a514a'],
    'anh_patch': ['#58554e', '#68645b', '#7b766b', '#8d887b'],
    # white smoker: anhydrite and barite
    'anh': ['#9d9b95', '#b1afa9', '#c4c2bb', '#d4d2cb', '#e3e1da', '#efede6'],
    'anh_speck': ['#2e2d2d', '#403e3d', '#58544f'],
    'tan': ['#b9aa88', '#a99a78'],
    'hole_w': ['#1c1d20', '#2b2d31', '#3d4045'],
    'milk': ['#dfe9ec', '#eef5f6', '#f8fcfc', '#c9d8dc'],
    # nodule field: pale brown-grey mud, black-brown nodules
    'mud': ['#5d564c', '#686054', '#756c5f', '#827868', '#8d8374'],
    'mud_shadow': ['#4a443b', '#554e44'],
    'nod': ['#130f0c', '#1e1611', '#2c2018', '#3d2d21', '#51402f', '#665240'],
    # crust: basalt-grey rock under a black botryoidal coating
    'rock': ['#1c1f21', '#25282a', '#2e3235', '#383d40'],
    'crust': ['#0b0a0a', '#131110', '#1c1918', '#272220', '#352e2a', '#473e37'],
    'crust_blue': ['#26303a', '#33404c'],
    'crust_brown': ['#2a1d15', '#38271b'],
}
P = {k: [hexc(c) for c in v] for k, v in PALETTES.items()}


# ---------------------------------------------------------------- helpers
def ramp(pal, v):
    i = int(v * len(pal))
    return pal[max(0, min(len(pal) - 1, i))]


def dart_points(rng, n, rmin, rmax, sep, torus_y=True, ymin=0.0, ymax=16.0, tries=400):
    pts = []
    for _ in range(tries):
        if len(pts) >= n:
            break
        x, y = rng.uniform(0, W), rng.uniform(ymin, ymax)
        r = rng.uniform(rmin, rmax)
        ok = True
        for (px, py, pr) in pts:
            dx = abs(x - px); dx = min(dx, W - dx)
            dy = abs(y - py)
            if torus_y:
                dy = min(dy, W - dy)
            if math.hypot(dx, dy) < sep * (r + pr) / 2:
                ok = False
                break
        if ok:
            pts.append((x, y, r))
    return pts


def heightmap(pts, sy=1.0, torus_y=True):
    """Dome height of the tallest lump at every texel centre (0 where none), torus in x (and y)."""
    h = [[0.0] * W for _ in range(W)]
    for y in range(W):
        for x in range(W):
            best = 0.0
            for (px, py, r) in pts:
                dx = abs(x + .5 - px); dx = min(dx, W - dx)
                dy = abs(y + .5 - py)
                if torus_y:
                    dy = min(dy, W - dy)
                d = math.hypot(dx, dy * sy)
                if d < r:
                    # a dome: sqrt profile, so the lump has a rounded top and a steep edge
                    v = math.sqrt(max(0.0, 1 - (d / r) ** 2)) * r
                    best = max(best, v)
            h[y][x] = best
    return h


def lit(h, x, y, torus_y=True):
    def g(xx, yy):
        if not torus_y and not (0 <= yy < W):
            return h[max(0, min(W - 1, yy))][xx % W]
        return h[yy % W][xx % W]
    return (g(x + 1, y) - g(x - 1, y)) + (g(x, y + 1) - g(x, y - 1))


def noise(rng, blur=1):
    f = [[rng.random() for _ in range(W)] for _ in range(W)]
    for _ in range(blur):
        g = [[0.0] * W for _ in range(W)]
        for y in range(W):
            for x in range(W):
                s = 0.0
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        s += f[(y + dy) % W][(x + dx) % W] * (2 if (dx == 0 and dy == 0) else 1)
                g[y][x] = s / 10
        f = g
    lo = min(min(r) for r in f); hi = max(max(r) for r in f)
    return [[(v - lo) / (hi - lo + 1e-9) for v in r] for r in f]


def new():
    return Image.new('RGBA', (W, W), (0, 0, 0, 255))


def put(im, x, y, c):
    im.putpixel((x % W, y % W), c + (255,))


def streaks(im, rng, pal, count, lmin, lmax, torus_y=True, p=0.8):
    for _ in range(count):
        x = rng.randrange(W); y0 = rng.randrange(W); n = rng.randint(lmin, lmax)
        for i in range(n):
            if rng.random() < p:
                yy = y0 + i
                if not torus_y and yy >= W:
                    break
                put(im, x, yy, pal[min(len(pal) - 1, int(i / max(1, n) * len(pal)))] if rng.random() < .7 else rng.choice(pal))


def flecks(im, rng, pal, count):
    for _ in range(count):
        put(im, rng.randrange(W), rng.randrange(W), rng.choice(pal))


# ---------------------------------------------------------------- textures
def sulfide_chimney():
    rng = random.Random(1101)
    im = new()
    pts = dart_points(rng, 11, 2.0, 3.4, 1.0)
    h = heightmap(pts, sy=0.62)  # taller than wide: knobbly columns
    n = noise(rng, 1)
    for y in range(W):
        for x in range(W):
            v = 0.34 + 0.1 * (h[y][x] / 3.4) + 0.075 * lit(h, x, y) + (n[y][x] - .5) * .28
            if h[y][x] <= 0:
                v -= 0.16  # crevice
            put(im, x, y, ramp(P['sulf'], v))
    # rusty oxide: three short runs in different columns and rows (no stripe lines up across a tile), plus a few lone pixels
    cols = rng.sample(range(W), 3)
    for k, cx_ in enumerate(cols):
        y0 = (k * 5 + rng.randrange(3)) % W
        for i in range(rng.randint(2, 4)):
            if rng.random() < .8:
                put(im, cx_, y0 + i, ramp(P['rust'], .25 + i * .2))
    for _ in range(4):
        put(im, rng.randrange(W), rng.randrange(W), P['rust'][0])
    flecks(im, rng, P['sulfur'], 2)                   # native sulfur
    flecks(im, rng, P['brass'], 6)                    # chalcopyrite and pyrite glints
    return im


def chimney_top(kind):
    rng = random.Random(1102 if kind == 'b' else 1202)
    im = new()
    base = sulfide_chimney() if kind == 'b' else anhydrite_chimney()
    cx = cy = 7.5
    # ragged radii: a different radius in each of 16 angular buckets
    jit = [rng.uniform(-.55, .55) for _ in range(16)]
    jit_in = [rng.uniform(-.35, .35) for _ in range(16)]
    for y in range(W):
        for x in range(W):
            dx, dy = x + .5 - 8, y + .5 - 8
            d = math.hypot(dx, dy)
            a = int(((math.atan2(dy, dx) + math.pi) / (2 * math.pi)) * 16) % 16
            hole, ring, rim = 2.1 + jit_in[a], 3.5 + jit[a], 5.4 + jit[(a + 5) % 16] * 1.3
            c = base.getpixel((x, y))[:3]
            if kind == 'b':
                if d < hole:
                    c = P['hole_b'][min(3, int(rng.random() * 2.2 + (1 if d < 1.0 else 0) * 1.6))]
                elif d < ring:
                    c = ramp(P['glow'], rng.random() * .75 + (ring - d) / 4 * .0 + .1)
                elif d < rim:
                    c = ramp(P['rust'], rng.random() * .8 + .1) if rng.random() < .8 else P['sulf'][2]
            else:
                if d < hole:
                    c = rng.choice(P['hole_w'])
                elif d < ring:
                    c = ramp(P['milk'], rng.random())
                elif d < rim:
                    c = ramp(P['anh'], .55 + rng.random() * .45)
            put(im, x, y, c)
    return im


def sulfide_mound():
    rng = random.Random(1103)
    im = new()
    pts = dart_points(rng, 9, 2.4, 4.0, 1.05)
    h = heightmap(pts, sy=1.0)
    n = noise(rng, 1)
    # which lump is a pale anhydrite cobble or a rusty one: by nearest-centre hash
    kind = {}
    for i, p in enumerate(pts):
        r = rng.random()
        kind[i] = 'anh_patch' if r < .12 else ('rust' if r < .17 else 'rubble')
    for y in range(W):
        for x in range(W):
            best, bi = -1, -1
            for i, (px, py, r) in enumerate(pts):
                dx = abs(x + .5 - px); dx = min(dx, W - dx); dy = abs(y + .5 - py); dy = min(dy, W - dy)
                v = r - math.hypot(dx, dy)
                if v > best:
                    best, bi = v, i
            v = 0.36 + 0.05 * (h[y][x] / 4) + 0.05 * lit(h, x, y) + (n[y][x] - .5) * .2
            if best < 0.5:
                v -= .14  # joint between cobbles
            k = kind.get(bi, 'rubble')
            put(im, x, y, ramp(P[k], v))
    flecks(im, rng, P['brass'][:2], 3)
    return im


def anhydrite_chimney():
    rng = random.Random(1201)
    im = new()
    pts = dart_points(rng, 12, 1.8, 3.0, 1.0)
    h = heightmap(pts, sy=0.7)
    n = noise(rng, 2)
    for y in range(W):
        for x in range(W):
            v = 0.52 + 0.06 * (h[y][x] / 3) + 0.055 * lit(h, x, y) + (n[y][x] - .5) * .3
            put(im, x, y, ramp(P['anh'], v))
    # bladed barite: short vertical light and dark strokes
    streaks(im, rng, [P['anh'][5], P['anh'][4]], 6, 2, 4, p=1)
    streaks(im, rng, [P['anh'][1], P['anh'][0]], 4, 2, 4, p=1)
    flecks(im, rng, P['anh_speck'], 10)               # sphalerite and sulfide specks
    streaks(im, rng, P['tan'], 2, 3, 6, p=.8)         # faint iron stain
    return im


def nodule_bed_top():
    rng = random.Random(1301)
    im = new()
    n = noise(rng, 1)
    for y in range(W):
        for x in range(W):
            put(im, x, y, ramp(P['mud'], .42 + (n[y][x] - .5) * .85))
    pts = dart_points(rng, 7, 1.5, 2.4, 1.5)
    h = heightmap(pts)
    for y in range(W):
        for x in range(W):
            if h[y][x] > 0.15:
                v = .30 + .1 * (h[y][x] / 2.8) + .09 * lit(h, x, y)
                put(im, x, y, ramp(P['nod'], v))
            else:
                # a lump half buried: shadow on its lower right, mud pushed up on the other side
                for (px, py, r) in pts:
                    dx = (x + .5 - px + 8) % W - 8; dy = (y + .5 - py + 8) % W - 8
                    d = math.hypot(dx, dy)
                    if r <= d < r + 1.15 and dx + dy > -0.5:
                        put(im, x, y, rng.choice(P['mud_shadow']))
                        break
    flecks(im, rng, [P['nod'][1], P['nod'][2]], 5)    # pebbles and fragments
    return im


def nodule_bed_side():
    rng = random.Random(1302)
    im = new()
    n = noise(rng, 1)
    for y in range(W):
        for x in range(W):
            put(im, x, y, ramp(P['mud'], .40 + (n[y][x] - .5) * .75 - .05 * (y / 15)))
    # strata: two faint darker rows
    for y in (7, 12):
        for x in range(W):
            if rng.random() < .55:
                put(im, x, y, ramp(P['mud'], .18 + rng.random() * .15))
    pts = dart_points(rng, 6, 1.8, 2.7, 1.2, torus_y=False, ymin=0.0, ymax=3.0)
    h = heightmap(pts, torus_y=False)
    for y in range(6):
        for x in range(W):
            if h[y][x] > 0.15:
                put(im, x, y, ramp(P['nod'], .30 + .1 * (h[y][x] / 2.7) + .09 * lit(h, x, y, torus_y=False)))
    return im


def nodule_bed_bottom():
    rng = random.Random(1303)
    im = new()
    n = noise(rng, 1)
    for y in range(W):
        for x in range(W):
            put(im, x, y, ramp(P['mud'], .32 + (n[y][x] - .5) * .7))
    return im


def mn_crust():
    rng = random.Random(1401)
    im = new()
    n = noise(rng, 1)
    for y in range(W):
        for x in range(W):
            put(im, x, y, ramp(P['rock'], .45 + (n[y][x] - .5) * .9))
    pts = dart_points(rng, 24, 1.3, 2.4, 0.95)
    h = heightmap(pts)
    for y in range(W):
        for x in range(W):
            if h[y][x] > 0.12:
                put(im, x, y, ramp(P['crust'], .27 + .17 * (h[y][x] / 2.1) + .11 * lit(h, x, y) + rng.uniform(-.04, .04)))
    # a few bare patches where the coating is thin, a bluish sheen and a brown oxide tint on some tops
    for _ in range(4):
        put(im, rng.randrange(W), rng.randrange(W), rng.choice(P['rock']))
    for (px, py, r) in pts:
        if rng.random() < .22:
            put(im, int(px), int(py), rng.choice(P['crust_blue']))
        elif rng.random() < .14:
            put(im, int(px), int(py), rng.choice(P['crust_brown']))
    return im


def nodule_skin():
    """The loose nodule's own texture: dense small botryoidal bumps, a little mud clinging."""
    rng = random.Random(1501)
    im = new()
    pts = dart_points(rng, 30, 1.0, 1.7, 1.05)
    h = heightmap(pts)
    n = noise(rng, 1)
    for y in range(W):
        for x in range(W):
            v = .32 + .16 * (h[y][x] / 1.7) + .1 * lit(h, x, y) + (n[y][x] - .5) * .12
            if h[y][x] <= 0:
                v -= .12
            put(im, x, y, ramp(P['nod'], v))
    flecks(im, rng, [P['mud'][2], P['mud'][3], P['mud'][1]], 9)
    return im


TEXTURES = {
    'sulfide_chimney': sulfide_chimney,
    'sulfide_chimney_top': lambda: chimney_top('b'),
    'sulfide_mound': sulfide_mound,
    'anhydrite_chimney': anhydrite_chimney,
    'anhydrite_chimney_top': lambda: chimney_top('w'),
    'nodule_bed': nodule_bed_top,
    'nodule_bed_side': nodule_bed_side,
    'nodule_bed_bottom': nodule_bed_bottom,
    'mn_crust': mn_crust,
    'nodule': nodule_skin,
}


# ---------------------------------------------------------------- models
def cube_model(side, top, bottom=None, glow_top=None):
    """A full cube whose up face may be fullbright (NeoForge's per-face `neoforge_data`)."""
    def face(tex, cull, extra=None):
        f = {'uv': [0, 0, 16, 16], 'texture': tex, 'cullface': cull}
        if extra:
            f['neoforge_data'] = extra
        return f
    faces = {
        'down': face('#bottom', 'down'),
        'up': face('#top', 'up', {'block_light': glow_top, 'ambient_occlusion': False} if glow_top else None),
        'north': face('#side', 'north'), 'south': face('#side', 'south'),
        'west': face('#side', 'west'), 'east': face('#side', 'east'),
    }
    return {'textures': {'particle': '#side'},
            'elements': [{'from': [0, 0, 0], 'to': [16, 16, 16], 'faces': faces}]}


def nodule_shape():
    """Five potato-sized lumps, 2-4 texels across, lying on the floor (TFC's loose ores are the same idea)."""
    lumps = [  # from, to, y-rotation about the lump's own centre
        ((2.5, 0, 3.0), (7.0, 3.0, 7.0), 22.5),
        ((8.5, 0, 2.0), (11.5, 2.0, 5.5), -22.5),
        ((9.0, 0, 7.5), (13.5, 3.5, 11.5), 0),
        ((3.5, 0, 9.5), (6.5, 2.0, 13.0), 22.5),
        ((6.8, 0, 11.0), (9.0, 1.5, 13.4), -22.5),
    ]
    els = []
    for (a, b, rot) in lumps:
        dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        e = {'from': list(a), 'to': list(b), 'faces': {}}
        if rot:
            e['rotation'] = {'angle': rot, 'axis': 'y', 'origin': [(a[0] + b[0]) / 2, 0, (a[2] + b[2]) / 2]}
        # each face samples a different part of the 16x16 skin so the lumps do not look cloned
        ox, oz = (a[0] * 3 + a[2]) % 8, (a[2] * 3 + a[0]) % 8
        e['faces'] = {
            'up': {'uv': [ox, oz, ox + dx, oz + dz], 'texture': '#all'},
            'north': {'uv': [ox, 8 + dy * 0, ox + dx, 8 + dy], 'texture': '#all'},
            'south': {'uv': [ox, 8, ox + dx, 8 + dy], 'texture': '#all'},
            'east': {'uv': [oz, 8, oz + dz, 8 + dy], 'texture': '#all'},
            'west': {'uv': [oz, 8, oz + dz, 8 + dy], 'texture': '#all'},
        }
        els.append(e)
    return {'textures': {'particle': '#all'}, 'elements': els}


MODELS = {
    'sulfide_chimney_shape': lambda: cube_model('#side', '#top', glow_top=15),
    'anhydrite_chimney_shape': lambda: cube_model('#side', '#top', glow_top=15),
    'nodule_shape': nodule_shape,
}


def write_all(out):
    tdir = os.path.join(out, 'textures', 'block'); mdir = os.path.join(out, 'models', 'block')
    os.makedirs(tdir, exist_ok=True); os.makedirs(mdir, exist_ok=True)
    tex = {}
    for name, fn in TEXTURES.items():
        im = fn()
        im.save(os.path.join(tdir, name + '.png'))
        tex[name] = im
    for name, fn in MODELS.items():
        with open(os.path.join(mdir, name + '.json'), 'w') as f:
            json.dump(fn(), f, indent=2)
            f.write('\n')
    return tex


# ---------------------------------------------------------------- preview
def tfc_tex(path):
    jars = glob.glob(os.path.join(ROOT, 'tools', '.server', 'mods', 'TerraFirmaCraft-NeoForge-*.jar'))
    if os.environ.get('TFC_JAR'):
        jars.insert(0, os.environ['TFC_JAR'])
    for jar in jars:
        try:
            with zipfile.ZipFile(jar) as z:
                return Image.open(io.BytesIO(z.read('assets/tfc/textures/block/' + path + '.png'))).convert('RGBA')
        except Exception:
            pass
    return None


def font(size):
    for f in ('arial.ttf', 'DejaVuSans.ttf'):
        try:
            return ImageFont.truetype(f, size)
        except Exception:
            pass
    return ImageFont.load_default()


class Iso:
    """Painter's-algorithm isometric renderer for boxes textured per face from 16x16 images (2:1, 3 faces)."""
    SHADE = {'up': 1.0, 'south': .78, 'east': .6}

    def __init__(self, w, h, ox, oy, s):
        self.s = s  # screen pixels per block unit along one axis
        self.ox, self.oy = ox, oy
        self.im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)

    def pt(self, x, y, z):
        s = self.s
        return (self.ox + (x - y) * s, self.oy + (x + y) * s / 2 - z * s)

    def face(self, kind, box, tex, light=1.0, glow=False, step=1 / 16):
        (x0, y0, z0), (x1, y1, z1) = box
        sh = 1.0 if glow else self.SHADE[kind] * light
        nx = 16
        if kind == 'up':
            n1, n2 = max(1, round((x1 - x0) * 16)), max(1, round((y1 - y0) * 16))
            for i in range(n1):
                for j in range(n2):
                    c = tex.getpixel((int(((x0 + i / 16) * 16)) % 16, int(((y0 + j / 16) * 16)) % 16))
                    xa, xb = x0 + i / 16, x0 + (i + 1) / 16; ya, yb = y0 + j / 16, y0 + (j + 1) / 16
                    self._quad([self.pt(xa, ya, z1), self.pt(xb, ya, z1), self.pt(xb, yb, z1), self.pt(xa, yb, z1)], c, sh)
        elif kind == 'south':  # the face at y1, spanning x and z
            n1, n2 = max(1, round((x1 - x0) * 16)), max(1, round((z1 - z0) * 16))
            for i in range(n1):
                for j in range(n2):
                    c = tex.getpixel((int((x0 * 16 + i)) % 16, 15 - int((z0 * 16 + j)) % 16))
                    xa, xb = x0 + i / 16, x0 + (i + 1) / 16; za, zb = z0 + j / 16, z0 + (j + 1) / 16
                    self._quad([self.pt(xa, y1, za), self.pt(xb, y1, za), self.pt(xb, y1, zb), self.pt(xa, y1, zb)], c, sh)
        else:  # east: the face at x1, spanning y and z
            n1, n2 = max(1, round((y1 - y0) * 16)), max(1, round((z1 - z0) * 16))
            for i in range(n1):
                for j in range(n2):
                    c = tex.getpixel((int((y0 * 16 + i)) % 16, 15 - int((z0 * 16 + j)) % 16))
                    ya, yb = y0 + i / 16, y0 + (i + 1) / 16; za, zb = z0 + j / 16, z0 + (j + 1) / 16
                    self._quad([self.pt(x1, ya, za), self.pt(x1, yb, za), self.pt(x1, yb, zb), self.pt(x1, ya, zb)], c, sh)

    def _quad(self, pts, c, sh):
        col = tuple(max(0, min(255, int(v * sh))) for v in c[:3]) + (255,)
        self.d.polygon(pts, fill=col, outline=col)

    def box(self, box, top, south, east, light=1.0, glow_top=False):
        self.face('south', box, south, light)
        self.face('east', box, east, light)
        self.face('up', box, top, light, glow=glow_top)


def tint(im, light, fog, glowmask=None):
    """Dim a rendered scene toward deep-water blue by `light`, keeping fully-lit pixels as they are."""
    return im


def scene(kind, tex, floor_tex, rock_tex, deep=False):
    rng = random.Random(77)
    N = 15
    S = 20  # px per block axis; texel = 20/16 px (rendered at 1x then upscaled by the caller)
    img = Iso(2 * N * S + 40, N * S + 7 * S, N * S + 20, 7 * S, S)
    light = .28 if deep else 1.0
    cells = {}
    cx, cy = N / 2, N / 2

    def ground(x, y):
        return floor_tex
    chim = []
    if kind in ('black', 'white'):
        mound = 'sulfide_mound' if kind == 'black' else None
        for x in range(N):
            for y in range(N):
                d = math.hypot(x + .5 - cx, y + .5 - cy)
                cells[(x, y)] = (mound if (mound and d < 4.6 + rng.uniform(-.7, .7)) else None)
        cands = [(x, y) for x in range(N) for y in range(N) if math.hypot(x + .5 - cx, y + .5 - cy) < 4.6]
        rng.shuffle(cands)
        for (x, y) in cands[:11 if kind == 'black' else 8]:
            d = math.hypot(x + .5 - cx, y + .5 - cy)
            chim.append((x, y, rng.randint(2, 7) if kind == 'black' else rng.randint(2, 5)))
    elif kind == 'nodule':
        for x in range(N):
            for y in range(N):
                d = math.hypot(x + .5 - cx, y + .5 - cy)
                cells[(x, y)] = 'nodule_bed' if d < 4.8 + rng.uniform(-.8, .8) else None
    elif kind == 'crust':
        for x in range(N):
            for y in range(N):
                d = math.hypot(x + .5 - cx, y + .5 - cy)
                cells[(x, y)] = 'mn_crust' if d < 3.2 + rng.uniform(-1.3, 1.3) else None
    # draw order: back to front (small x+y first), floor then stacks
    order = sorted([(x, y) for x in range(N) for y in range(N)], key=lambda p: p[0] + p[1])
    chim_by = {(x, y): h for (x, y, h) in chim}
    lumps = []
    if kind == 'nodule':
        for (x, y), v in cells.items():
            if v:
                for _ in range(2):
                    if rng.random() < .8:
                        lumps.append((x + rng.uniform(.15, .55), y + rng.uniform(.15, .55)))
        for _ in range(26):  # a halo of loose ones beyond the bed
            a = rng.uniform(0, 6.283); r = rng.uniform(4.8, 7.0)
            lumps.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
        lumps = [(a, b) for (a, b) in lumps if 0.3 < a < N - 0.7 and 0.3 < b < N - 0.7]
    nod_by = {}
    for (a, b) in lumps:
        nod_by.setdefault((int(a), int(b)), []).append((a, b))
    for (x, y) in order:
        v = cells.get((x, y))
        floor_box = ((x, y, -1), (x + 1, y + 1, 0))
        if v == 'sulfide_mound':
            t_top = t_s = t_e = tex['sulfide_mound']
        elif v == 'nodule_bed':
            t_top, t_s, t_e = tex['nodule_bed'], tex['nodule_bed_side'], tex['nodule_bed_side']
        elif v == 'mn_crust':
            t_top = t_s = t_e = tex['mn_crust']
        else:
            t_top = t_s = t_e = floor_tex if kind != 'crust' else rock_tex
        img.box(floor_box, t_top, t_s, t_e, light)
        if (x, y) in chim_by:
            h = chim_by[(x, y)]
            name = 'sulfide_chimney' if kind == 'black' else 'anhydrite_chimney'
            for k in range(h):
                tip = (k == h - 1)
                img.box(((x, y, k), (x + 1, y + 1, k + 1)), tex[name + '_top'] if tip else tex[name], tex[name], tex[name],
                        light, glow_top=tip and deep)
        for (a, b) in nod_by.get((x, y), []):
            s = 0.26
            img.box(((a, b, 0), (a + s, b + s * .9, .17)), tex['nodule'], tex['nodule'], tex['nodule'], light)
    return img.im


def make_preview(tex, path):
    mud = tfc_tex('mud/fluvisol'); rhy = tfc_tex('rock/raw/rhyolite'); bas = tfc_tex('rock/raw/basalt')
    if mud is None:
        mud = tex['nodule_bed_bottom']; rhy = bas = tex['mn_crust']
    big = 8
    f1, f2 = font(15), font(12)
    names = [('sulfide_chimney', 'chimney side'), ('sulfide_chimney_top', 'chimney tip'), ('sulfide_mound', 'mound'),
             ('anhydrite_chimney', 'white side'), ('anhydrite_chimney_top', 'white tip'),
             ('nodule_bed', 'bed top'), ('nodule_bed_side', 'bed side'), ('nodule_bed_bottom', 'bed bottom'),
             ('mn_crust', 'crust'), ('nodule', 'loose nodule skin')]
    ref = [('TFC mud (fluvisol)', mud), ('TFC raw basalt', bas), ('TFC raw rhyolite', rhy)]
    cell = 16 * big + 16
    cols = 5
    rows = 2
    pad = 14
    top_h = rows * (cell + 22) + 30
    tile = 16 * 4 * 3  # a 4x4 tiling shown at 3x
    tile_cell = tile + 14
    tiles_h = 2 * (tile_cell + 22) + 30 + 80
    scenes = [('black smoker field on sulfide mound (lit)', 'black', False), ('same, deep water: only the tips glow', 'black', True),
              ('white smoker field, volcanic arc', 'white', True), ('nodule bed with loose nodules on and around it', 'nodule', False),
              ('ferromanganese crust patch on rhyolite', 'crust', False)]
    SW, SH = 2 * 15 * 20 + 40, 15 * 20 + 7 * 20
    sheet_w = max(cols * cell + 2 * pad, 2 * (SW + pad) + pad)
    sheet_h = top_h + tiles_h + 3 * (SH + 40) + 20
    sheet = Image.new('RGB', (sheet_w, sheet_h), (24, 28, 32))
    d = ImageDraw.Draw(sheet)
    d.text((pad, 6), 'Sea-floor deposits: 16x16 textures at 8x (nearest), TFC reference textures in the last row of the strip', fill=(220, 220, 220), font=f1)
    y0 = 30
    for i, (n, label) in enumerate(names):
        r, c = divmod(i, cols)
        x = pad + c * cell; y = y0 + r * (cell + 22)
        sheet.paste(tex[n].resize((16 * big, 16 * big), Image.NEAREST).convert('RGB'), (x, y))
        d.text((x, y + 16 * big + 3), label, fill=(200, 200, 200), font=f2)
    # TFC reference row appended under the grid
    yref = y0 + rows * (cell + 22)
    d.text((pad, yref - 4), 'reference (TFC, for palette and grain only):', fill=(170, 170, 170), font=f2)
    for i, (label, im) in enumerate(ref):
        x = pad + i * 130
        sheet.paste(im.resize((64, 64), Image.NEAREST).convert('RGB'), (x, yref + 12))
        d.text((x, yref + 78), label, fill=(170, 170, 170), font=f2)
    y1 = yref + 120
    d.text((pad, y1 - 16), 'tiled 4x4 (3x) - seams and repetition', fill=(220, 220, 220), font=f1)
    tiles = [('sulfide_chimney', 'sulfide_chimney'), ('anhydrite_chimney', 'anhydrite_chimney'), ('sulfide_mound', 'mound'),
             ('nodule_bed', 'nodule bed top'), ('mn_crust', 'crust')]
    for i, (n, label) in enumerate(tiles):
        t = Image.new('RGB', (64, 64))
        for a in range(4):
            for b in range(4):
                t.paste(tex[n].convert('RGB'), (a * 16, b * 16))
        t = t.resize((tile // 1 // 1 if False else 64 * 2, 64 * 2), Image.NEAREST)
        sheet.paste(t, (pad + i * (128 + 14), y1 + 4))
        d.text((pad + i * (128 + 14), y1 + 4 + 130), label, fill=(190, 190, 190), font=f2)
    yscene = y1 + 4 + 150
    for i, (label, kind, deep) in enumerate(scenes):
        r, c = divmod(i, 2)
        x = pad + c * (SW + pad); y = yscene + r * (SH + 40)
        im = scene(kind, tex, mud, rhy if kind in ('white', 'crust') else bas, deep)
        bg = Image.new('RGB', im.size, (20, 44, 66) if deep else (62, 112, 150))
        if deep:  # a darker abyss behind, so the lit and glowing faces stand out
            bg = Image.new('RGB', im.size, (6, 14, 26))
        bg.paste(im, (0, 0), im)
        sheet.paste(bg, (x, y + 20))
        d.text((x, y), label, fill=(220, 220, 220), font=f1)
    sheet.save(path)
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default=os.path.join(ROOT, 'kubejs', 'assets', 'pack'))
    ap.add_argument('--preview', default=None, help='write the review sheet (PNG) here')
    a = ap.parse_args()
    tex = write_all(a.out)
    print('wrote', len(tex), 'textures and', len(MODELS), 'models under', a.out)
    if a.preview:
        print('preview', make_preview(tex, a.preview))


if __name__ == '__main__':
    main()
