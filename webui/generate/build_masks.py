#!/usr/bin/env python3
"""AvianVisitors - rebuild the collage silhouette masks from the cutouts.

Step 3 of the illustration pipeline (after pregen.py and cutout.py).

The collage packs birds by their actual silhouette, not bounding boxes,
so the app ships a tiny 1-bit mask per illustration. This reads every
cutout in webui/assets/illustrations/ and rewrites the data the collage
loads from webui/frontend/src/collage/data/:

    dims.json   slug -> [w, h]  aspect, scaled so the long side is 560
    masks.json  slug -> {w, h, bits}  silhouette downscaled to <=93px,
                1-bit packed MSB-first row-major, base64. A bit is 1 where
                the cutout is opaque (alpha > 127); loadMask() decodes it.

Run after changing the illustration set, then bump IMG_VERSION in the app
so browsers drop their cached copies.

Usage:
    python3 build_masks.py            # rewrite the data files in place
    python3 build_masks.py --check    # report only, don't write
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
from pathlib import Path

DIM_MAX = 560
MASK_MAX = 93
ALPHA_ON = 127


def build_tables(illus_dir: Path):
    from PIL import Image

    dims, masks = {}, {}
    pngs = sorted(p for p in illus_dir.glob("*.png") if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", p.stem))
    for p in pngs:
        slug = p.stem
        im = Image.open(p).convert("RGBA")
        w, h = im.size
        scale = DIM_MAX / max(w, h)
        dims[slug] = [round(w * scale), round(h * scale)]

        ms = MASK_MAX / max(w, h)
        mw, mh = max(1, round(w * ms)), max(1, round(h * ms))
        alpha = im.getchannel("A").resize((mw, mh), Image.LANCZOS)
        px = alpha.load()
        bits = bytearray((mw * mh + 7) // 8)
        for y in range(mh):
            for x in range(mw):
                if px[x, y] > ALPHA_ON:
                    i = y * mw + x
                    bits[i >> 3] |= 1 << (7 - (i & 7))
        masks[slug] = {"w": mw, "h": mh, "bits": base64.b64encode(bytes(bits)).decode()}
    return dims, masks


def main() -> int:
    here = Path(__file__).resolve().parents[1]
    data_dir = here / "frontend" / "src" / "collage" / "data"
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--illustrations", type=Path, default=here / "assets" / "illustrations", help="Cutout directory (default: webui/assets/illustrations/)")
    ap.add_argument("--data", type=Path, default=data_dir, help="Output directory (default: webui/frontend/src/collage/data/)")
    ap.add_argument("--check", action="store_true", help="Report counts and don't write")
    args = ap.parse_args()

    dims, masks = build_tables(args.illustrations)
    perched = sum(1 for k in dims if not k.endswith("-2"))
    flight = sum(1 for k in dims if k.endswith("-2"))
    print(f"built {len(dims)} masks ({perched} perched + {flight} flight) from {args.illustrations}")
    if not dims:
        print("error: no cutouts found", file=sys.stderr)
        return 1

    dims_path = args.data / "dims.json"
    masks_path = args.data / "masks.json"

    if args.check:
        cur = json.loads(dims_path.read_text()) if dims_path.is_file() else {}
        added = sorted(set(dims) - set(cur))
        removed = sorted(set(cur) - set(dims))
        print(f"data currently has {len(cur)} entries; +{len(added)} new, -{len(removed)} removed")
        if added:
            print("  new:", ", ".join(added[:8]) + (" ..." if len(added) > 8 else ""))
        if removed:
            print("  gone:", ", ".join(removed[:8]) + (" ..." if len(removed) > 8 else ""))
        return 0

    args.data.mkdir(parents=True, exist_ok=True)
    dims_path.write_text(json.dumps(dims, separators=(",", ":")))
    masks_path.write_text(json.dumps(masks, separators=(",", ":")))
    print(f"wrote {dims_path} and {masks_path}\nremember to bump IMG_VERSION in the app")
    return 0


if __name__ == "__main__":
    sys.exit(main())
