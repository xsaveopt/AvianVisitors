#!/usr/bin/env python3
"""AvianVisitors - generate kachō-e bird illustrations for a region.

Step 1 of the illustration pipeline:
    1. pregen.py       render each bird on a uniform cream ground
    2. cutout.py       remove the ground (BiRefNet) and crop to the bird
    3. build_masks.py  refresh the collage silhouette masks (dims/masks.json)

Reads a species list (BirdNET-Pi's labels.txt, eBird, or stdin), fetches a
Wikipedia reference photo for each species, and renders an illustration
locally with FLUX.1-dev on an NVIDIA GPU. The target-species photo and a
kachō-e style plate steer the output through FLUX.1 Redux image
conditioning; the text prompt carries the style, pose, and anti-lookalike
instructions. Saves PNGs into webui/assets/illustrations/.

The prompt renders each bird on a CREAM ground, not a transparent one: the
model can't cut transparency cleanly, but a flat known ground removes
cleanly in step 2. Each species gets two poses: <slug>.png (perched) and
<slug>-2.png (flight). Edit webui/generate/prompt.template.md to change the
visual style - the prompt body is re-used verbatim per render with
{sci_name}, {com_name}, and {pose} substituted.

Reference photos:
    Cached in webui/assets/references/. The auto-fetch hits the Wikipedia
    article's first image. To use a hand-picked reference, drop it in
    references/ named <slug>.jpg or <slug>.png BEFORE running.

Contrastive anti-reference:
    For genera that drift toward a more famous lookalike, the prompt body
    is rewritten to tell the model NOT to copy that lookalike's diagnostic
    features. The registry (ANTI_REFS, ANTI_REF_TRIGGERS) is keyed so
    adding a new one is one entry per table. FLUX Redux conditions
    additively, so the lookalike steers the prompt text, not an image.

Usage:
    python3 pregen.py --labels ~/BirdNET-Pi/model/labels.txt
    python3 pregen.py --labels labels.txt --ebird-region US-CA --ebird-key KEY
    python3 pregen.py --species "Calypte anna|Anna's Hummingbird" --force

FLUX.1-dev and FLUX.1-Redux-dev are gated on Hugging Face: accept both
licenses, then set HF_TOKEN in the environment (or pass --hf-token).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from io import BytesIO
from pathlib import Path

POSES = {1: "perched", 2: "in flight with wings spread"}

BASE_MODEL = "black-forest-labs/FLUX.1-dev"
REDUX_MODEL = "black-forest-labs/FLUX.1-Redux-dev"


JAY_GENERA = {
    "Cyanocitta",
    "Aphelocoma",
    "Cyanolyca",
    "Calocitta",
    "Cyanopica",
    "Garrulus",
    "Cyanocorax",
    "Gymnorhinus",
}


SWALLOW_GENERA = {
    "Tachycineta",
    "Riparia",
    "Progne",
    "Petrochelidon",
    "Stelgidopteryx",
}


ROBIN_GENERA = set()


STYLE_REFS = {
    "small_songbird_perched": "01-sparrows-on-bamboo-Koson.jpg",
    "dark_bird_perched": "02-cawing-crow-Koson.jpg",
    "vivid_perched": "03-jays-on-berry-tree-Koson.jpg",
    "vibrant_perched": "04-kingfisher-Koson.jpg",
    "owl": "05-owl-on-ginkgo-Koson.jpg",
    "large_flight": "06-goose-flying-in-moonlight-Koson.jpg",
    "small_flight": "07-swallows-in-flight-Koson.jpg",
    "wader": "08-crane-in-small-water-Koson.jpg",
    "pale_perched": "09-cockatoo-Yoshida.jpg",
    "waterfowl_perched": "10-mandarin-ducks-Yoshida.jpg",
}


GENUS_STYLE_PERCHED = {
    "Tyto": "owl",
    "Bubo": "owl",
    "Asio": "owl",
    "Megascops": "owl",
    "Athene": "owl",
    "Strix": "owl",
    "Glaucidium": "owl",
    "Aegolius": "owl",
    "Calypte": "vibrant_perched",
    "Archilochus": "vibrant_perched",
    "Selasphorus": "vibrant_perched",
    "Calothorax": "vibrant_perched",
    "Cyanocitta": "vibrant_perched",
    "Aphelocoma": "vibrant_perched",
    "Pica": "vibrant_perched",
    "Nucifraga": "vibrant_perched",
    "Perisoreus": "vibrant_perched",
    "Bombycilla": "vivid_perched",
    "Icterus": "vivid_perched",
    "Piranga": "vivid_perched",
    "Pheucticus": "vivid_perched",
    "Passerina": "vivid_perched",
    "Cardellina": "vivid_perched",
    "Setophaga": "vivid_perched",
    "Icteria": "vivid_perched",
    "Corvus": "dark_bird_perched",
    "Coragyps": "dark_bird_perched",
    "Cathartes": "dark_bird_perched",
    "Gymnogyps": "dark_bird_perched",
    "Anas": "waterfowl_perched",
    "Aix": "waterfowl_perched",
    "Mareca": "waterfowl_perched",
    "Spatula": "waterfowl_perched",
    "Branta": "waterfowl_perched",
    "Anser": "waterfowl_perched",
    "Cygnus": "waterfowl_perched",
    "Aythya": "waterfowl_perched",
    "Bucephala": "waterfowl_perched",
    "Lophodytes": "waterfowl_perched",
    "Mergus": "waterfowl_perched",
    "Oxyura": "waterfowl_perched",
    "Podiceps": "waterfowl_perched",
    "Podilymbus": "waterfowl_perched",
    "Aechmophorus": "waterfowl_perched",
    "Gavia": "waterfowl_perched",
    "Pelecanus": "waterfowl_perched",
    "Phalacrocorax": "waterfowl_perched",
    "Urile": "waterfowl_perched",
    "Ardea": "wader",
    "Egretta": "wader",
    "Bubulcus": "wader",
    "Butorides": "wader",
    "Nycticorax": "wader",
    "Plegadis": "wader",
    "Limosa": "wader",
    "Numenius": "wader",
    "Himantopus": "wader",
    "Recurvirostra": "wader",
    "Charadrius": "wader",
    "Actitis": "wader",
    "Calidris": "wader",
    "Tringa": "wader",
    "Larus": "pale_perched",
    "Leucophaeus": "pale_perched",
    "Sterna": "pale_perched",
    "Thalasseus": "pale_perched",
    "Hydroprogne": "pale_perched",
    "Rynchops": "pale_perched",
}


LARGE_FLIGHT_GENERA = {
    "Tyto",
    "Bubo",
    "Asio",
    "Megascops",
    "Athene",
    "Strix",
    "Glaucidium",
    "Aegolius",
    "Anas",
    "Aix",
    "Mareca",
    "Spatula",
    "Branta",
    "Anser",
    "Cygnus",
    "Aythya",
    "Bucephala",
    "Lophodytes",
    "Mergus",
    "Oxyura",
    "Pelecanus",
    "Phalacrocorax",
    "Urile",
    "Ardea",
    "Egretta",
    "Bubulcus",
    "Butorides",
    "Nycticorax",
    "Plegadis",
    "Limosa",
    "Numenius",
    "Himantopus",
    "Recurvirostra",
    "Buteo",
    "Accipiter",
    "Aquila",
    "Circus",
    "Falco",
    "Cathartes",
    "Coragyps",
    "Haliaeetus",
    "Pandion",
    "Elanus",
    "Gymnogyps",
    "Corvus",
}


def select_style_ref(sci: str, pose: int) -> str:
    """Pick the style reference filename for a (sci, pose) pair."""
    genus = sci.split()[0]

    if sci == "Aeronautes saxatalis":
        return STYLE_REFS["vibrant_perched"]
    if pose == 2:
        return STYLE_REFS["large_flight" if genus in LARGE_FLIGHT_GENERA else "small_flight"]
    return STYLE_REFS[GENUS_STYLE_PERCHED.get(genus, "small_songbird_perched")]


ANTI_REFS = {
    "bluejay": {
        "common_name": "Blue Jay",
        "sci_name": "Cyanocitta cristata",
        "do_not_copy": ("its facial mask, its white wingbars, its black necklace, its crest pattern, or its white-tipped tail"),
    },
    "barnswallow": {
        "common_name": "Barn Swallow",
        "sci_name": "Hirundo rustica",
        "do_not_copy": ("its deep rufous throat, its long deeply forked outer tail streamers, or its blue-black back"),
    },
}


ANTI_REF_TRIGGERS = (
    (JAY_GENERA, "bluejay", "Cyanocitta cristata"),
    (SWALLOW_GENERA, "barnswallow", "Hirundo rustica"),
)

USER_AGENT = "AvianVisitors/1.0 (https://github.com/Twarner491/AvianVisitors)"


def slugify(sci: str) -> str:
    """Match the app's collage slugify() exactly."""
    return re.sub(r"[^a-z0-9]+", "-", sci.lower()).strip("-")


def parse_species_line(line: str) -> tuple[str, str] | None:
    """Accept any of: 'Sci|Com', 'Sci_Com', 'Sci,Com'. Skip blanks + #."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    for sep in ("|", "_", ","):
        if sep in line:
            sci, com = line.split(sep, 1)
            sci, com = sci.strip(), com.strip()
            if sci and com:
                return (sci, com)
    return None


def parse_species_list(lines: list[str]) -> tuple[list[tuple[str, str]], int]:
    """Returns (parsed, skipped_count)."""
    out, skipped = [], 0
    for line in lines:
        parsed = parse_species_line(line)
        if parsed:
            out.append(parsed)
        elif line.strip() and not line.lstrip().startswith("#"):
            skipped += 1
    return out, skipped


def load_prompt(path: Path) -> str:
    """Return everything after the `## Prompt` heading, stripped to the
    next `##` heading (so doc preamble or trailing sections don't bleed
    into the render)."""
    text = path.read_text()
    m = re.search(r"##\s*Prompt\s*\n(.+?)(?=\n##\s|\Z)", text, flags=re.DOTALL)
    return (m.group(1) if m else text).strip()


def ebird_filter(species, region: str, key: str):
    """Intersect a label set with the eBird species list for a region.
    Region codes: US-CA (state), US-CA-085 (county)."""
    url = f"https://api.ebird.org/v2/product/spplist/{region}"
    req = urllib.request.Request(url, headers={"X-eBirdApiToken": key})
    with urllib.request.urlopen(req, timeout=30) as r:
        ebird_codes = set(json.loads(r.read()))
    tax_url = "https://api.ebird.org/v2/ref/taxonomy/ebird?fmt=json"
    req2 = urllib.request.Request(tax_url, headers={"X-eBirdApiToken": key})
    with urllib.request.urlopen(req2, timeout=60) as r:
        taxonomy = json.loads(r.read())
    code_to_sci = {t["speciesCode"]: t["sciName"] for t in taxonomy}
    allowed = {code_to_sci[c] for c in ebird_codes if c in code_to_sci}
    return [(s, c) for s, c in species if s in allowed]


REF_EXTS = (".jpg", ".png")


def fetch_wikipedia_thumb(sci: str, com: str) -> tuple[bytes, str] | None:
    """Fetch the Wikipedia article's lead/infobox image bytes.

    Returns (bytes, ext) where ext is '.jpg' or '.png' sniffed from the
    magic bytes. Returns None if no usable image. Pulls a 1024-wide
    thumbnail via the REST summary endpoint.
    """
    titles = [sci.replace(" ", "_"), com.replace(" ", "_"), com.split()[0]]
    for title in titles:
        url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(title)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=20) as r:
                meta = json.loads(r.read())
        except (urllib.error.HTTPError, urllib.error.URLError):
            continue

        for k in ("originalimage", "thumbnail"):
            src = (meta.get(k) or {}).get("source")
            if not src or not src.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            try:
                req2 = urllib.request.Request(src, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req2, timeout=30) as r:
                    data = r.read()
            except (urllib.error.HTTPError, urllib.error.URLError):
                continue

            if data.startswith(b"\x89PNG\r\n\x1a\n"):
                return data, ".png"
            if data.startswith(b"\xff\xd8\xff"):
                return data, ".jpg"
    return None


def ensure_reference(refs_dir: Path, slug: str, sci: str, com: str) -> Path | None:
    """Cache-or-fetch a reference photo. Returns the path if we have one,
    None if Wikipedia had no usable image. Pre-existing references
    (<slug>.jpg or <slug>.png) are respected."""
    refs_dir.mkdir(parents=True, exist_ok=True)
    for ext in REF_EXTS:
        cached = refs_dir / f"{slug}{ext}"
        if cached.exists() and cached.stat().st_size > 1024:
            return cached
    fetched = fetch_wikipedia_thumb(sci, com)
    if not fetched:
        return None
    data, ext = fetched
    path = refs_dir / f"{slug}{ext}"
    path.write_bytes(data)
    return path


def select_anti_ref_key(sci: str) -> str | None:
    """Return the ANTI_REFS key for the lookalike that this species drifts
    toward, or None if no anti-ref is needed."""
    genus = sci.split()[0]
    for genera, key, exclude in ANTI_REF_TRIGGERS:
        if genus in genera and sci != exclude:
            return key
    return None


def load_species_notes(notes_path: Path) -> dict[str, str]:
    """Load per-species prompt addenda keyed by scientific name. Returns
    {} if the notes file doesn't exist."""
    if not notes_path.exists():
        return {}
    raw = json.loads(notes_path.read_text())
    return {k: v for k, v in raw.items() if not k.startswith("_") and isinstance(v, str)}


def _anti_ref_line(anti_ref_key: str | None) -> str:
    """Render the `{anti_ref_line}` substitution for the prompt body."""
    info = ANTI_REFS.get(anti_ref_key or "")
    if not info:
        return ""
    return (
        f"- The species must NOT resemble a {info['common_name']} "
        f"({info['sci_name']}). Do NOT give it {info['do_not_copy']}. "
        f"If the output looks more like a {info['common_name']} than the "
        f"target species, the output is wrong."
    )


def build_prompt_body(prompt: str, sci: str, com: str, pose: int, anti_ref_key: str | None, species_note: str | None) -> str:
    """Substitute the per-species fields into the prompt template body."""
    body = prompt.replace("{sci_name}", sci).replace("{com_name}", com).replace("{pose}", POSES[pose]).replace("{anti_ref_line}", _anti_ref_line(anti_ref_key))
    if species_note:
        body = body + "\n\nSpecies-specific note: " + species_note
    return body


class FluxGenerator:
    """Local FLUX.1-dev text-to-image renderer.

    The transformer and T5 text encoder load in 4-bit (bitsandbytes nf4)
    and the pipeline uses model CPU offload, so it fits a 12-16GB card. The
    kachō-e style comes entirely from the text prompt; no reference images
    are used, which is what keeps the output flat and drawn rather than
    photographic.
    """

    def __init__(
        self,
        base_id: str = BASE_MODEL,
        height: int = 1024,
        width: int = 1024,
        steps: int = 28,
        guidance: float = 3.5,
        seed: int | None = None,
    ) -> None:
        import torch
        from diffusers import (
            BitsAndBytesConfig as DiffusersBnb,
        )
        from diffusers import (
            FluxPipeline,
            FluxTransformer2DModel,
        )
        from transformers import (
            BitsAndBytesConfig as TransformersBnb,
        )
        from transformers import (
            T5EncoderModel,
        )

        self.torch = torch
        self.height = height
        self.width = width
        self.steps = steps
        self.guidance = guidance
        self.seed = seed
        dtype = torch.bfloat16

        transformer = FluxTransformer2DModel.from_pretrained(
            base_id,
            subfolder="transformer",
            quantization_config=DiffusersBnb(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=dtype),
            torch_dtype=dtype,
        )
        text_encoder_2 = T5EncoderModel.from_pretrained(
            base_id,
            subfolder="text_encoder_2",
            quantization_config=TransformersBnb(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=dtype),
            torch_dtype=dtype,
        )
        self.pipe = FluxPipeline.from_pretrained(
            base_id,
            transformer=transformer,
            text_encoder_2=text_encoder_2,
            torch_dtype=dtype,
        )
        self.pipe.enable_model_cpu_offload()

    def generate(
        self,
        prompt: str,
        sci: str,
        com: str,
        pose: int,
        anti_ref_key: str | None = None,
        species_note: str | None = None,
    ) -> bytes:
        """Render one (species, pose) from the text prompt. Returns PNG bytes."""
        body = build_prompt_body(prompt, sci, com, pose, anti_ref_key, species_note)

        generator = None
        if self.seed is not None:
            generator = self.torch.Generator(device="cpu").manual_seed(self.seed)

        result = self.pipe(
            prompt=body,
            guidance_scale=self.guidance,
            num_inference_steps=self.steps,
            height=self.height,
            width=self.width,
            max_sequence_length=512,
            generator=generator,
        )

        buf = BytesIO()
        result.images[0].save(buf, format="PNG")
        return buf.getvalue()


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--labels", type=Path, help="Path to BirdNET-Pi labels.txt (or any file of Sci|Com lines)")
    src.add_argument("--species", action="append", default=[], help="Manual 'Sci|Com' (repeatable)")
    src.add_argument("--stdin", action="store_true", help="Read Sci|Com lines from stdin")
    ap.add_argument("--ebird-region", help="eBird region code (e.g. US-CA, US-CA-085) to filter labels")
    ap.add_argument("--ebird-key", help="eBird API key (or EBIRD_API_KEY env)")
    ap.add_argument("--hf-token", help="Hugging Face token for gated FLUX models (or HF_TOKEN env)")
    ap.add_argument("--base-model", default=BASE_MODEL, help=f"FLUX base model id (default: {BASE_MODEL})")
    ap.add_argument("--steps", type=int, default=28, help="Denoising steps (default: 28)")
    ap.add_argument("--guidance", type=float, default=3.5, help="Guidance scale (default: 3.5)")
    ap.add_argument("--size", type=int, default=1024, help="Output edge length in px (default: 1024)")
    ap.add_argument("--seed", type=int, default=0, help="Seed for reproducible output (0 = random per render)")
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "assets" / "illustrations",
        help="Output directory (default: webui/assets/illustrations/)",
    )
    ap.add_argument("--prompt", type=Path, default=Path(__file__).resolve().parent / "prompt.template.md", help="Prompt template path")
    ap.add_argument(
        "--notes",
        type=Path,
        default=Path(__file__).resolve().parent / "species-notes.json",
        help="Per-species prompt addenda for difficult cases (e.g. similar-species drift)",
    )
    ap.add_argument(
        "--poses", nargs="+", type=int, default=[1, 2], choices=list(POSES.keys()), help="Which poses to render. 1=perched, 2=flight. Default: both."
    )
    ap.add_argument("--force", action="store_true", help="Re-render even if file exists")
    ap.add_argument("--limit", type=int, default=0, help="Cap species count for testing")
    args = ap.parse_args()

    hf_token = args.hf_token or os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN", "")
    if not hf_token:
        print(
            "error: HF_TOKEN is empty. FLUX.1-dev is gated, so pregen needs a token with both "
            "model licenses accepted. If you ran with sudo, the env was stripped: use `sudo -E` "
            "or `sudo env HF_TOKEN=... docker compose ...`.",
            file=sys.stderr,
        )
        return 2
    os.environ["HF_TOKEN"] = hf_token

    if args.labels:
        species, skipped = parse_species_list(args.labels.read_text().splitlines())
    elif args.stdin:
        species, skipped = parse_species_list(sys.stdin.read().splitlines())
    else:
        species, skipped = parse_species_list(args.species)
    if skipped:
        print(f"[parse] skipped {skipped} malformed line(s)", file=sys.stderr)
    if not species:
        print("error: no species resolved", file=sys.stderr)
        return 2

    if args.ebird_region:
        ek = args.ebird_key or os.environ.get("EBIRD_API_KEY", "")
        if not ek:
            print("error: --ebird-region requires --ebird-key or EBIRD_API_KEY", file=sys.stderr)
            return 2
        print(f"[ebird] filtering {len(species)} species against {args.ebird_region}...")
        species = ebird_filter(species, args.ebird_region, ek)

    if args.limit:
        species = species[: args.limit]

    prompt = load_prompt(args.prompt)
    args.out.mkdir(parents=True, exist_ok=True)
    notes = load_species_notes(args.notes)
    if notes:
        print(f"[notes] loaded per-species addenda for {len(notes)} species")

    total = len(species) * len(args.poses)
    print(f"loading FLUX ({args.base_model}), this takes a minute on first run...")
    try:
        generator = FluxGenerator(
            base_id=args.base_model,
            height=args.size,
            width=args.size,
            steps=args.steps,
            guidance=args.guidance,
            seed=args.seed or None,
        )
    except ImportError as e:
        print(f"error: FLUX dependencies missing ({e}). Run on the generate-cuda image.", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"error: failed to load FLUX ({e}). Check HF_TOKEN and that both model licenses are accepted.", file=sys.stderr)
        return 2

    print(f"generating up to {total} illustrations into {args.out}/")

    done = skipped_existing = failed = 0
    first_fail = None
    for sci, com in species:
        slug = slugify(sci)
        anti_key = select_anti_ref_key(sci)

        for pose in args.poses:
            fname = f"{slug}.png" if pose == 1 else f"{slug}-{pose}.png"
            path = args.out / fname
            if path.exists() and not args.force:
                skipped_existing += 1
                continue
            try:
                started = time.monotonic()
                data = generator.generate(
                    prompt,
                    sci,
                    com,
                    pose,
                    anti_ref_key=anti_key,
                    species_note=notes.get(sci),
                )
                path.write_bytes(data)
                done += 1
                anti_tag = "+anti" if anti_key else ""
                note_tag = "+note" if notes.get(sci) else ""
                elapsed = time.monotonic() - started
                print(f"  [ok]   {fname} ({len(data) // 1024} KB, {elapsed:.0f}s){anti_tag}{note_tag}")
            except Exception as e:
                failed += 1
                first_fail = first_fail or fname
                print(f"  [fail] {fname}: {e}", file=sys.stderr)

    print(f"\ngenerated {done} · skipped {skipped_existing} · failed {failed}")
    if first_fail:
        print(f"first failure: {first_fail} (re-run without --force to retry only the misses)", file=sys.stderr)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
