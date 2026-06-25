# Making the bird pictures

This folder turns a list of species into the cutout images the collage is built from.

AvianVisitors used to draw every bird with an image model, but local generation was slow and the results were unreliable.
It now uses real photographs instead: a Creative-Commons photo per species, with the background matted away so only the bird is left on transparency.
A full set already ships with the repo, so you only need anything here to add birds for your own region or to redo a cutout you don't like.

## Pipeline

- photos.py fetches a photo per species, cuts the bird out with BiRefNet, and writes a transparent AVIF to assets/illustrations/.
- build_masks.py rebuilds the collage silhouette masks in frontend/src/collage/data/ from the finished cutouts.

photos.py takes the photo from Wikipedia's lead image first, since that is usually the cleanest portrait, and falls back to iNaturalist's curated species photo when Wikipedia has none.
Every source is written to assets/credits.json with its licence and attribution, so the photos stay properly credited.

The cutouts themselves live in git as a single assets/illustrations.tar rather than hundreds of loose files.
archive.py is the only thing that touches it: run `python archive.py unpack` to restore the loose assets/illustrations/ folder from the tar, and `python archive.py pack` once at the end to write it back for committing.
photos.py and build_masks.py work purely on the loose folder and never touch the tar, so a run leaves you with the full assets/illustrations/ (and assets/illustrations/rejected/) tree to browse and pick what to redo.
Only the tar and assets/credits.json are committed; the loose folder is working state.

## Running it

Everything runs in Docker, on the CPU, so no GPU is needed.
The first run downloads the BiRefNet matting model (about 1GB) into the models volume, where it stays cached.

```sh
cd webui/generate
docker compose build generate
docker compose run --rm generate python archive.py unpack
docker compose run --rm generate python photos.py
```

With no arguments photos.py works through a built-in sample of common Netherlands birds and writes the cutouts to assets/illustrations/, so you can look at them before committing to a full run.
Pass --keep-raw to also drop the untouched source photos under raw/ for comparison.

To do a real set, pass a label file with one `scientific name|common name` per line (BirdNET's labels.txt works directly), and optionally filter it to the birds actually seen in your region with an eBird api key:

```sh
export EBIRD_API_KEY=your-key
docker compose run --rm generate python photos.py --labels /repo/birdnet/model/BirdNET_GLOBAL_6K_V2.4_Model_FP16_Labels.txt --ebird-region NL
docker compose run --rm generate python build_masks.py
```

Re-running skips species that already have a cutout, so deleting a few bad ones and running again only redoes those.
Add --force to redo everything.
Move cutouts you don't like into assets/illustrations/rejected/ and the next run blocklists their source and re-picks a different photo.

When you're happy with the set, pack the tar and commit it:

```sh
docker compose run --rm generate python archive.py pack
```

## Knobs

- --licenses sets which iNaturalist licences are allowed, default cc0,cc-by,cc-by-nc. Narrow it to cc0,cc-by if you only want images that are free for any use.
- --model picks the rembg matting model, default birefnet-general. The lighter isnet-general-use uses far less memory if a run gets killed.
- --max-size downscales the source before matting, default 1024. Lower it to save memory, raise it for a sharper cutout.
- --alpha-matting refines the edges further, but is slow and memory-heavy.
- --margin sets the crop padding around the bird, and --avif-quality the AVIF size-versus-quality trade.

## Apple Silicon

onnxruntime prints a harmless "Unknown CPU vendor" line inside the Docker VM; ignore it.
For full speed, build and run the image natively as arm64 rather than letting it fall back to emulation:

```sh
DOCKER_DEFAULT_PLATFORM=linux/arm64 docker compose build generate
DOCKER_DEFAULT_PLATFORM=linux/arm64 docker compose run --rm generate python photos.py
```
