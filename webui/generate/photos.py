#!/usr/bin/env python3
"""AvianVisitors - fetch and cut out a real photo per bird species.

Fetches a Creative-Commons photo per species (Wikipedia's lead image first,
iNaturalist's curated photo as a fallback), mattes the bird off its background
with BiRefNet, crops to the bird, and writes a transparent AVIF to
assets/illustrations/. Every source is recorded in assets/credits.json with
its licence and attribution.

Run it with the built-in sample list to fill the sample set, or point it at a
whole region with --labels and --ebird-region.

Usage:
    python3 photos.py                                  # built-in NL sample
    python3 photos.py --species "Parus major|Great Tit"
    python3 photos.py --labels LABELS --ebird-region NL --ebird-key KEY
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from io import BytesIO
from pathlib import Path

USER_AGENT = "AvianVisitors/1.0 (https://github.com/Twarner491/AvianVisitors)"

VERBOSE = True


def step(msg: str) -> None:
    if VERBOSE:
        print(f"  - {msg}")


def substep(msg: str) -> None:
    if VERBOSE:
        print(f"    · {msg}")


def write_credits(path: Path, credits: dict) -> None:
    """Write credits atomically so the run can be stopped at any point and
    resumed without a half-written file: each species is flushed as it lands."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(credits, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)


def ingest_rejections(rejected_dir: Path, rejected_path: Path, rejected: dict, credits: dict) -> None:
    """Turn cutouts you dropped into `rejected_dir` into per-species source
    blocklists: each file's recorded source URLs are added to `rejected` so the
    next run picks a different image, and the file is moved into a processed/
    archive so it is only ingested once."""
    pending = sorted(rejected_dir.glob("*.avif")) if rejected_dir.exists() else []
    if not pending:
        return
    processed = rejected_dir / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    for p in pending:
        slug = p.stem
        cred = credits.get(slug)
        if cred:
            urls = {cred.get("image_url", ""), cred.get("url", "")} - {""}
            rejected[slug] = sorted(set(rejected.get(slug, [])) | urls)
            print(f"  [reject] {slug}: will avoid {cred.get('image_url') or cred.get('url')}")
        else:
            print(f"  [reject] {slug}: no credit on record, nothing to block")
        dest, i = processed / p.name, 1
        while dest.exists():
            dest, i = processed / f"{p.stem}-{i}.avif", i + 1
        p.replace(dest)
    rejected_path.write_text(json.dumps(rejected, indent=2, ensure_ascii=False) + "\n")


def slugify(sci: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", sci.lower()).strip("-")


def parse_species_line(line: str) -> tuple[str, str] | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    for sep in ("|", "_", ","):
        if sep in line:
            sci, com = line.split(sep, 1)
            sci, com = sci.strip(), com.strip()
            if sci and com:
                return (sci, com)
    if " " in line:
        return (line, line)
    return None


def parse_species_list(lines: list[str]) -> tuple[list[tuple[str, str]], int]:
    out, skipped = [], 0
    for line in lines:
        parsed = parse_species_line(line)
        if parsed:
            out.append(parsed)
        elif line.strip() and not line.lstrip().startswith("#"):
            skipped += 1
    return out, skipped


def ebird_filter(species, region: str, key: str, sci_to_com: dict | None = None):
    ebird_codes = set()
    for reg in (r.strip() for r in region.split(",") if r.strip()):
        url = f"https://api.ebird.org/v2/product/spplist/{reg}"
        req = urllib.request.Request(url, headers={"X-eBirdApiToken": key})
        with urllib.request.urlopen(req, timeout=30) as r:
            ebird_codes |= set(json.loads(r.read()))
    tax_url = "https://api.ebird.org/v2/ref/taxonomy/ebird?fmt=json"
    req2 = urllib.request.Request(tax_url, headers={"X-eBirdApiToken": key})
    with urllib.request.urlopen(req2, timeout=60) as r:
        taxonomy = json.loads(r.read())
    code_to = {t["speciesCode"]: (t["sciName"], t.get("comName", "")) for t in taxonomy}
    allowed = {}
    allowed_com = {}
    for c in ebird_codes:
        if c in code_to:
            sci_name, com_name = code_to[c]
            allowed[sci_name] = com_name
            if com_name:
                allowed_com[com_name.casefold()] = com_name
    sci_to_com = sci_to_com or {}
    out, recovered = [], []
    for s, c in species:
        if s in allowed:
            out.append((s, allowed[s] or c))
            continue
        com = sci_to_com.get(s) or (c if c != s else "")
        match = allowed_com.get(com.casefold()) if com else None
        if match:
            out.append((s, match))
            recovered.append(f"{s} ({match})")
    if recovered:
        print(f"[ebird] recovered {len(recovered)} by common name: {', '.join(recovered)}")
    return out


WIKI_THUMB_WIDTH = 1600
MIN_FRAME = 300
MULTI_BIRD_RATIO = 0.5
MIN_CUTOUT = 256
MATTE_CAP = 15
EDGE_COVER = 0.45
CORNER_COVER = 0.2

_NON_PHOTO = re.compile(
    r"range|distribution|locator|\bmap\b|logo|\bicon\b|iucn|"
    r"sonogram|spectrogram|\begg\b|nest|skull|skeleton|specimen|museum|"
    r"\bskin\b|holotype|mwnh|mnhn|nmnh|rmnh|naturalis|stamp|signature|diagram|"
    r"\.svg$|\.ogg$|\.oga$|\.wav$|\.webm$|\.ogv$|\.pdf$|\.gif$|\.tiff?$",
    re.IGNORECASE,
)


CC_URLS = {
    "cc0": "https://creativecommons.org/publicdomain/zero/1.0/",
    "cc-by": "https://creativecommons.org/licenses/by/4.0/",
    "cc-by-sa": "https://creativecommons.org/licenses/by-sa/4.0/",
    "cc-by-nc": "https://creativecommons.org/licenses/by-nc/4.0/",
    "cc-by-nc-sa": "https://creativecommons.org/licenses/by-nc-sa/4.0/",
    "cc-by-nd": "https://creativecommons.org/licenses/by-nd/4.0/",
    "cc-by-nc-nd": "https://creativecommons.org/licenses/by-nc-nd/4.0/",
}


def _strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()


def _wiki_credit(info: dict, src: str) -> dict:
    """Licence and author for one file, read from its imageinfo extmetadata so
    the credit describes the exact file downloaded."""
    ext = info.get("extmetadata") or {}
    license_name = _strip_html((ext.get("LicenseShortName") or {}).get("value", ""))
    author = _strip_html((ext.get("Artist") or {}).get("value", "")) or _strip_html((ext.get("Credit") or {}).get("value", ""))
    return {
        "license": license_name or "unknown",
        "license_url": (ext.get("LicenseUrl") or {}).get("value", ""),
        "attribution": author or "unknown",
        "url": info.get("descriptionurl", src),
        "image_url": info.get("url", src),
    }


def _norm(title: str) -> str:
    return title.replace("_", " ").strip().lower()


def _min_side(info: dict) -> int:
    return min(info.get("width", 0), info.get("height", 0))


def _page_images(title: str) -> dict:
    """Every file on the article, keyed by normalised title, each with its
    imageinfo (size, mime, capped thumb URL, licence metadata)."""
    q = urllib.parse.urlencode(
        {
            "action": "query",
            "format": "json",
            "redirects": "1",
            "generator": "images",
            "gimlimit": "100",
            "titles": title,
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
            "iiurlwidth": str(WIKI_THUMB_WIDTH),
        }
    )
    raw = _get(f"https://en.wikipedia.org/w/api.php?{q}", 30)
    if not raw:
        return {}
    try:
        pages = json.loads(raw).get("query", {}).get("pages", {})
    except json.JSONDecodeError:
        return {}
    out = {}
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        if info:
            out[_norm(page.get("title", ""))] = info
    return out


def _lead_title(title: str) -> str | None:
    """The article's representative image (PageImages' pick), normalised."""
    q = urllib.parse.urlencode(
        {
            "action": "query",
            "format": "json",
            "redirects": "1",
            "titles": title,
            "prop": "pageimages",
            "piprop": "name",
        }
    )
    raw = _get(f"https://en.wikipedia.org/w/api.php?{q}", 30)
    if not raw:
        return None
    try:
        pages = json.loads(raw).get("query", {}).get("pages", {})
    except json.JSONDecodeError:
        return None
    for page in pages.values():
        name = page.get("pageimage")
        if name:
            return _norm("File:" + name)
    return None


def _page_order(title: str) -> dict:
    """Map of normalised file title -> its position in the article, so the
    cover and the photos near the top of the page (the ones editors put first,
    usually the best) can be preferred over images buried lower down."""
    q = urllib.parse.urlencode(
        {
            "action": "parse",
            "format": "json",
            "redirects": "1",
            "page": title,
            "prop": "images",
        }
    )
    raw = _get(f"https://en.wikipedia.org/w/api.php?{q}", 30)
    if not raw:
        return {}
    try:
        names = json.loads(raw).get("parse", {}).get("images", [])
    except json.JSONDecodeError:
        return {}
    return {_norm("File:" + name): i for i, name in enumerate(names)}


def _cutout_side(data: bytes, session, frame_w: int, frame_h: int) -> tuple[int | None, str]:
    """Matte the image and return (min side of the cropped bird at source
    resolution, ""). We crop to the bird, so how much background surrounds it
    does not matter; we only reject a clear second bird (a comparable second
    blob) and a cutout that would be too small to be worth keeping. Returns
    (None, reason) when rejected."""
    import numpy as np
    from PIL import Image
    from rembg import remove
    from scipy import ndimage

    try:
        im = Image.open(BytesIO(data)).convert("RGB")
    except Exception:
        return None, "unreadable"
    im.thumbnail((512, 512), Image.LANCZOS)
    labels, n = ndimage.label(np.asarray(remove(im, session=session).getchannel("A")) > 127)
    if n == 0:
        return None, "no subject"
    areas = np.bincount(labels.ravel())
    areas[0] = 0
    ranked = np.argsort(areas)[::-1]
    largest = int(areas[ranked[0]])
    second = int(areas[ranked[1]]) if n > 1 else 0
    if second / largest > MULTI_BIRD_RATIO:
        return None, "multiple birds"
    mask = labels == ranked[0]
    top, bottom = mask[0].mean(), mask[-1].mean()
    left, right = mask[:, 0].mean(), mask[:, -1].mean()
    if max(top, bottom, left, right) > EDGE_COVER:
        return None, "bird runs off the frame"
    corners = (min(top, left), min(top, right), min(bottom, left), min(bottom, right))
    if max(corners) > CORNER_COVER:
        return None, "bird cut off at a corner"
    ys, xs = np.where(mask)
    bw = (xs.max() - xs.min() + 1) / im.width * frame_w
    bh = (ys.max() - ys.min() + 1) / im.height * frame_h
    side = int(min(bw, bh))
    if side < MIN_CUTOUT:
        return None, f"cutout only ~{side}px"
    return side, ""


def _evaluate(info: dict, session, name: str) -> dict | None:
    """The hit for a candidate that is a single-bird close-up, or None,
    logging why each candidate is kept or dropped."""
    src = info.get("thumburl") or info.get("url")
    data = _get(src, 40)
    ext = _sniff(data) if data else None
    if not ext:
        substep(f"{name} → download failed, skip")
        return None
    if not looks_like_bird(data):
        substep(f"{name} → not a bird, skip")
        return None
    side, reason = _cutout_side(data, session, info.get("width", 0), info.get("height", 0))
    if side is None:
        substep(f"{name} → {reason}, skip")
        return None
    substep(f"{name} → single bird, ~{side}px cutout")
    return {"data": data, "ext": ext, "source": "Wikimedia Commons", **_wiki_credit(info, src)}


def fetch_wiki(sci: str, com: str, session, blocked: set) -> dict | None:
    """The article's lead photo, falling back to the first usable photo in page
    order if the lead is missing or unusable. We trust the editors' ordering and
    take the first single-bird shot we find rather than hunting for the
    highest-resolution file: chasing resolution is what dragged in shared genus
    plates and other off-subject high-res images over the perfectly good lead.
    Images in `blocked` (rejected on an earlier run) are left out."""
    for title in (sci.replace(" ", "_"), com.replace(" ", "_")):
        images = _page_images(title)
        if not images:
            continue
        lead_key = _lead_title(title)
        order = _page_order(title)
        cands = {
            key: info
            for key, info in images.items()
            if info.get("mime") in ("image/jpeg", "image/png") and not _NON_PHOTO.search(key) and _min_side(info) >= MIN_FRAME
        }
        dropped = {k for k, v in cands.items() if blocked & {v.get("url"), v.get("descriptionurl")}}
        if dropped:
            step(f"skipping {len(dropped)} image(s) you rejected earlier")
            cands = {k: v for k, v in cands.items() if k not in dropped}

        def rank(item: tuple) -> tuple:
            key, _ = item
            if key == lead_key:
                return (0, 0)
            if key in order:
                return (1, order[key])
            return (2, 0)

        ordered = sorted(cands.items(), key=rank)
        step(f"Wikipedia page: {len(cands)} candidate photo(s), lead first")

        for i, (key, info) in enumerate(ordered):
            if i >= MATTE_CAP:
                substep(f"reached the {MATTE_CAP}-photo cap, stopping")
                break
            label = "lead" if key == lead_key else f"#{order.get(key, '?')}"
            name = f"[{label}] {key.split(':', 1)[-1]} ({info.get('width')}x{info.get('height')})"
            hit = _evaluate(info, session, name)
            if hit:
                step("using this one")
                return hit

        step("no single-bird photo found on the page")
    return None


SAMPLE = [
    ("Cyanistes caeruleus", "Eurasian Blue Tit"),
    ("Parus major", "Great Tit"),
    ("Erithacus rubecula", "European Robin"),
    ("Turdus merula", "Common Blackbird"),
    ("Carduelis carduelis", "European Goldfinch"),
    ("Fringilla coelebs", "Common Chaffinch"),
    ("Pica pica", "Eurasian Magpie"),
    ("Sturnus vulgaris", "Common Starling"),
    ("Passer domesticus", "House Sparrow"),
    ("Columba palumbus", "Common Wood Pigeon"),
]

DEFAULT_LICENSES = ["cc0", "cc-by", "cc-by-nc"]


def _get(url: str, timeout: int) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return None


def _sniff(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    return None


BIRD_MODEL_URL = "https://media.githubusercontent.com/media/onnx/models/main/validated/vision/classification/mobilenet/model/mobilenetv2-12.onnx"
_BIRD_CLASSES = frozenset(range(7, 25)) | frozenset(range(80, 101)) | frozenset(range(127, 147))
_bird_session = None


def _classifier():
    """Lazily build a MobileNetV2 ImageNet session, caching the model next to
    the rembg models. Returns None (once) if it can't be fetched, so the
    pipeline degrades to no bird check rather than failing."""
    global _bird_session
    if _bird_session is not None:
        return _bird_session or None
    try:
        import onnxruntime as ort

        cache = Path(os.environ.get("AVIAN_MODEL_DIR") or Path.home() / ".cache" / "avianvisitors")
        cache.mkdir(parents=True, exist_ok=True)
        model = cache / "mobilenetv2-12.onnx"
        if not model.exists():
            data = _get(BIRD_MODEL_URL, 120)
            if not data or not data.startswith(b"\x08"):
                raise OSError("classifier download failed")
            model.write_bytes(data)
        _bird_session = ort.InferenceSession(str(model), providers=["CPUExecutionProvider"])
    except Exception as e:
        print(f"  [warn] bird detector unavailable ({type(e).__name__}: {e}); skipping content check")
        _bird_session = False
        return None
    return _bird_session


def looks_like_bird(data: bytes) -> bool:
    """True if any of the image's top-5 ImageNet predictions is a bird class,
    which keeps egg, nest and habitat photos out of the result. Fails open."""
    sess = _classifier()
    if sess is None:
        return True
    import numpy as np
    from PIL import Image

    im = Image.open(BytesIO(data)).convert("RGB")
    scale = 256 / min(im.size)
    im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    x0, y0 = (im.width - 224) // 2, (im.height - 224) // 2
    im = im.crop((x0, y0, x0 + 224, y0 + 224))
    arr = np.asarray(im, dtype=np.float32) / 255.0
    arr = (arr - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]
    arr = arr.transpose(2, 0, 1)[None].astype(np.float32)
    out = sess.run(None, {sess.get_inputs()[0].name: arr})[0][0]
    top5 = out.argsort()[-5:]
    return any(int(i) in _BIRD_CLASSES for i in top5)


def _inat_photos(sci: str) -> tuple[int, list[dict]] | None:
    """Curated representative photos for a species: the default photo first,
    then the human-ranked taxon photo gallery (clean ID shots, not popular
    observations). Returns (taxon_id, [photo, ...])."""
    raw = _get("https://api.inaturalist.org/v1/taxa?" + urllib.parse.urlencode({"q": sci, "rank": "species", "per_page": "1"}), 30)
    if not raw:
        return None
    try:
        results = json.loads(raw).get("results", [])
    except json.JSONDecodeError:
        return None
    if not results:
        return None
    taxon = results[0]
    tid = taxon["id"]
    photos = []
    if taxon.get("default_photo"):
        photos.append(taxon["default_photo"])
    raw2 = _get(f"https://api.inaturalist.org/v1/taxa/{tid}", 30)
    if raw2:
        try:
            full = json.loads(raw2).get("results", [])
            if full:
                photos += [tp["photo"] for tp in full[0].get("taxon_photos", []) if tp.get("photo")]
        except json.JSONDecodeError:
            pass
    return tid, photos


def fetch_inat(sci: str, licenses: list[str], blocked: set) -> dict | None:
    """First curated iNaturalist photo for sci under an allowed licence, skipping
    any you rejected on an earlier run."""
    found = _inat_photos(sci)
    if not found:
        return None
    tid, photos = found
    allowed = set(licenses)
    for ph in photos:
        if (ph.get("license_code") or "").lower() not in allowed:
            continue
        src = ph.get("url", "")
        if "/square." not in src:
            continue
        large = src.replace("/square.", "/large.")
        page = f"https://www.inaturalist.org/photos/{ph.get('id', '')}"
        if blocked & {large, page}:
            continue
        data = _get(large, 30)
        ext = _sniff(data) if data else None
        if not ext:
            continue
        code = (ph.get("license_code") or "").lower()
        return {
            "data": data,
            "ext": ext,
            "source": "iNaturalist",
            "license": code,
            "license_url": CC_URLS.get(code, ""),
            "attribution": ph.get("attribution", ""),
            "url": page,
            "image_url": large,
        }
    return None


def fetch_photo(sci: str, com: str, licenses: list[str], session, blocked: set) -> dict | None:
    hit = fetch_wiki(sci, com, session, blocked)
    if hit:
        return hit
    step("falling back to iNaturalist")
    return fetch_inat(sci, licenses, blocked)


def make_session(model_name: str, threads: int):
    """A rembg session with onnxruntime's CPU memory arena and pre-planned
    memory pattern disabled, so each image's working set is freed instead of
    held and stacked into a multi-GB spike that the OOM killer trips on. Same
    model and input size as the default, so the cutout is identical."""
    import onnxruntime as ort
    from rembg.session_factory import sessions_class

    sc = next((s for s in sessions_class if s.name() == model_name), None)
    if sc is None:
        raise ValueError(f"unknown rembg model: {model_name}")
    opts = ort.SessionOptions()
    opts.enable_cpu_mem_arena = False
    opts.enable_mem_pattern = False
    if threads > 0:
        opts.intra_op_num_threads = threads
        opts.inter_op_num_threads = threads
    return sc(model_name, opts, providers=["CPUExecutionProvider"])


def cutout(data: bytes, session, margin: float, alpha_matting: bool, max_size: int):
    from PIL import Image
    from rembg import remove

    im = Image.open(BytesIO(data)).convert("RGB")
    if max(im.size) > max_size:
        im.thumbnail((max_size, max_size), Image.LANCZOS)
    kw = {}
    if alpha_matting:
        kw = dict(
            alpha_matting=True,
            alpha_matting_foreground_threshold=240,
            alpha_matting_background_threshold=15,
            alpha_matting_erode_size=10,
        )
    cut = remove(im, session=session, **kw)
    bbox = cut.getchannel("A").getbbox()
    if bbox:
        pad = round(margin * max(bbox[2] - bbox[0], bbox[3] - bbox[1]))
        x0, y0 = max(0, bbox[0] - pad), max(0, bbox[1] - pad)
        x1, y1 = min(cut.width, bbox[2] + pad), min(cut.height, bbox[3] + pad)
        cut = cut.crop((x0, y0, x1, y1))
    return cut


def avif_ok() -> bool:
    try:
        import pillow_avif  # noqa: F401

        return True
    except ImportError:
        try:
            from PIL import features

            return features.check("avif")
        except Exception:
            return False


def main() -> int:
    here = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--species", action="append", default=[], help="One 'Sci|Common' species; repeatable.")
    ap.add_argument("--labels", type=Path, help="Label file (one 'Sci|Common' per line).")
    ap.add_argument("--ebird-region", help="Filter the label file to these eBird regions, comma-separated and unioned (e.g. NL or US,CA,MX).")
    ap.add_argument("--ebird-key", help="eBird API key (or EBIRD_API_KEY env).")
    ap.add_argument("--licenses", default=",".join(DEFAULT_LICENSES), help="Allowed iNaturalist licences, comma-separated (default cc0,cc-by).")
    ap.add_argument("--out", type=Path, default=here / "assets" / "illustrations", help="Output directory.")
    ap.add_argument("--model", default="birefnet-general", help="rembg matting model.")
    ap.add_argument("--threads", type=int, default=0, help="onnxruntime thread cap (0 = auto). Lower it to shave peak memory further.")
    ap.add_argument("--margin", type=float, default=0.04, help="Crop margin as a fraction of the bird's long side.")
    ap.add_argument("--max-size", type=int, default=1024, help="Downscale the source to this long side before matting.")
    ap.add_argument("--alpha-matting", action="store_true", help="Refine edges with alpha matting (slower, heavier on RAM).")
    ap.add_argument("--avif-quality", type=int, default=55, help="AVIF quality 0-100.")
    ap.add_argument("--keep-raw", action="store_true", help="Also write the untouched source photo to raw/.")
    ap.add_argument("--rejected", type=Path, help="Folder you move bad cutouts into; next run blocklists their source and re-picks (default OUT/rejected).")
    ap.add_argument("--force", action="store_true", help="Re-do species that already have a cutout.")
    ap.add_argument("--limit", type=int, help="Stop after N species.")
    ap.add_argument("--quiet", action="store_true", help="Only print the per-species result and final summary, not each step.")
    args = ap.parse_args()

    global VERBOSE
    VERBOSE = not args.quiet

    if args.species:
        species, _ = parse_species_list(args.species)
    elif args.labels:
        species, skipped = parse_species_list(args.labels.read_text().splitlines())
        if skipped:
            print(f"[labels] skipped {skipped} malformed lines")
    else:
        species = SAMPLE

    if args.ebird_region:
        ek = args.ebird_key or os.environ.get("EBIRD_API_KEY", "")
        if not ek:
            print("error: --ebird-region needs --ebird-key or EBIRD_API_KEY", file=sys.stderr)
            return 2
        print(f"[ebird] filtering {len(species)} species against {args.ebird_region}...")
        sci_to_com = {}
        if args.labels:
            en_path = args.labels.parent / "l18n" / "labels_en.json"
            if en_path.exists():
                sci_to_com = json.loads(en_path.read_text())
        species = ebird_filter(species, args.ebird_region, ek, sci_to_com)

    if not species:
        print("error: no species to process", file=sys.stderr)
        return 1
    if args.limit:
        species = species[: args.limit]

    try:
        import rembg  # noqa: F401
    except ImportError:
        print("error: needs rembg + Pillow (run inside the generate container)", file=sys.stderr)
        return 2

    if not avif_ok():
        print("error: AVIF encoding unavailable (need pillow-avif-plugin; run inside the generate container)", file=sys.stderr)
        return 2

    licenses = [s.strip() for s in args.licenses.split(",") if s.strip()]
    args.out.mkdir(parents=True, exist_ok=True)
    raw_dir = args.out / "raw"

    credits_path = args.out.parent / "credits.json"
    credits = {}
    if credits_path.exists():
        credits = json.loads(credits_path.read_text())

    rejected_dir = args.rejected or args.out / "rejected"
    rejected_path = args.out / "rejected.json"
    rejected = json.loads(rejected_path.read_text()) if rejected_path.exists() else {}
    ingest_rejections(rejected_dir, rejected_path, rejected, credits)

    session = make_session(args.model, args.threads)
    done = skipped = missed = 0
    interrupted = False
    try:
        for sci, com in species:
            slug = slugify(sci)
            avif = args.out / f"{slug}.avif"
            if avif.exists() and not args.force:
                skipped += 1
                continue
            print(f"{slug}  ({sci})")
            hit = fetch_photo(sci, com, licenses, session, set(rejected.get(slug, [])))
            if not hit:
                step("no Creative-Commons photo found, skipping")
                missed += 1
                continue
            step(f"using {hit['source']} ({hit['license']})")
            try:
                if args.keep_raw:
                    raw_dir.mkdir(parents=True, exist_ok=True)
                    (raw_dir / f"{slug}{hit['ext']}").write_bytes(hit["data"])
                step("cutting out the bird")
                cut = cutout(hit["data"], session, args.margin, args.alpha_matting, args.max_size)
                tmp = avif.with_suffix(".avif.tmp")
                try:
                    cut.save(tmp, format="AVIF", quality=args.avif_quality)
                    tmp.replace(avif)
                finally:
                    tmp.unlink(missing_ok=True)
                step(f"saved {cut.width}x{cut.height}")
            except Exception as e:
                step(f"failed: {type(e).__name__}: {e}")
                missed += 1
                continue
            credits[slug] = {
                "scientific_name": sci,
                "common_name": com,
                "source": hit["source"],
                "license": hit["license"],
                "license_url": hit.get("license_url", ""),
                "attribution": hit["attribution"],
                "url": hit["url"],
                "image_url": hit.get("image_url", ""),
            }
            write_credits(credits_path, credits)
            done += 1
    except KeyboardInterrupt:
        interrupted = True
        print("\n[interrupted] stopping; cutouts and credits finished so far are kept")

    print(f"\ncut {done} · skipped {skipped} (already have) · missed {missed}")
    print(f"credits -> {credits_path}")
    print("loose cutouts left in assets/illustrations/; run `python archive.py pack` when you're happy with them")
    return 130 if interrupted else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[interrupted]", file=sys.stderr)
        sys.exit(130)
