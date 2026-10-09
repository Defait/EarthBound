"""Draw structures as they came out of a generated world, with tools/structures/render.py (read-only use).

Usage (from the repo root):
    tools/.venv/Scripts/python tools/structure_mods/render_world.py WORLD_DIR OUT_DIR ID [ID ...] [--n 1] [--views sw,ne] [--margin 3] [--above 3] [--below 6]

ID is a structure id (towns_and_towers:village_grove, pack:village/norse_living) or a prefix followed by "*" (mvs:*, pack:village/*). For each, the first N starts found in
the world (in region order; the same seed gives the same starts in a `before` and an `after` world, so the same call on both
gives a before/after pair) are cut out of the world together with a margin and ground, and drawn from two corners. --margin is the ring of
terrain kept around the structure's boxes, --above and --below the blocks kept over and under them (a forest around a village needs a margin of 12
or so and --above 28 to show its trees whole).
"""
import argparse
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(TOOLS, "structures"))
import worldreader as L  # noqa: E402
import render as R  # noqa: E402


def cut_template(world, boxes, margin=3, below=6, above=3):
    a = np.array(boxes)
    x0, y0, z0 = int(a[:, 0].min()), int(a[:, 1].min()), int(a[:, 2].min())
    x1, y1, z1 = int(a[:, 3].max()), int(a[:, 4].max()), int(a[:, 5].max())
    bx0, bz0, bx1, bz1 = x0 - margin, z0 - margin, x1 + margin, z1 + margin
    by0, by1 = max(-64, y0 - below), min(319, y1 + above)
    arr, pal = world.box(bx0, by0, bz0, bx1, by1, bz1)
    palette = [{"Name": n, "Properties": p} for n, p in pal]
    xs, ys, zs = np.nonzero(arr)
    blocks = [{"pos": [int(x), int(y), int(z)], "state": int(arr[x, y, z])} for x, y, z in zip(xs, ys, zs)]
    root = {"size": list(arr.shape), "palette": palette, "blocks": blocks}
    return R.Template(root, "cut")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("world")
    ap.add_argument("out")
    ap.add_argument("ids", nargs="+")
    ap.add_argument("--n", type=int, default=1)
    ap.add_argument("--views", default="sw,ne")
    ap.add_argument("--max-size", type=int, default=140, help="skip structures wider than this (a mineshaft's box is huge)")
    ap.add_argument("--margin", type=int, default=3, help="blocks of terrain kept around the structure's boxes")
    ap.add_argument("--above", type=int, default=3, help="blocks kept over the highest box")
    ap.add_argument("--below", type=int, default=6, help="blocks kept under the lowest box")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    world = L.WorldReader(args.world)
    want = {}
    for cx, cz, root in world.iter_all():
        if not str(root.get("Status", "")).endswith("full"):      # border chunks keep structure starts but no terrain
            continue
        for name, sx, sz, boxes, _pids in L.structure_starts(root):
            if (sx, sz) != (cx, cz) or not boxes:
                continue
            for pattern in args.ids:
                if name == pattern or (pattern.endswith("*") and name.startswith(pattern[:-1])):
                    want.setdefault(pattern, []).append((name, (sx, sz), boxes))
    renderer = R.Renderer()
    for pattern in args.ids:
        done = 0
        for name, chunk, boxes in sorted(want.get(pattern, []), key=lambda t: t[1]):
            a = np.array(boxes)
            if max(a[:, 3].max() - a[:, 0].min(), a[:, 5].max() - a[:, 2].min()) > args.max_size:
                continue
            tpl = cut_template(world, boxes, args.margin, args.below, args.above)
            stats, imgs = renderer.render(tpl, tuple(args.views.split(",")), 900, None, False, R.guess_tint(name))
            for view, im in imgs.items():
                path = os.path.join(args.out, f"{os.path.basename(args.world)}_{name.replace(':', '_').replace('/', '_')}_{chunk[0]}_{chunk[1]}_{view}.png")
                with open(path, "wb") as f:
                    f.write(R.png_encode(im, 256))
                print(path)
            done += 1
            if done >= args.n:
                break
        if not done:
            print("no start found for", pattern)


if __name__ == "__main__":
    main()
