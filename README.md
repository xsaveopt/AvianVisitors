# Avian Visitors

A live bird collage from a window microphone.
A small mic listens, BirdNET figures out which bird is calling, and each species shows up as an illustration in the collage, sized by how often it's been heard.

It all runs in one Docker container on a Raspberry Pi (or any Debian box).
The container records the audio, runs the detection, and serves the web page.

## Fork history

This is the far end of a fork chain:

- [BirdNET-Lite](https://github.com/birdnet-team/BirdNET-Lite), the original from the BirdNET team at the Cornell Lab of Ornithology. It is the TFLite sound recognition model and analyzer that identifies which of 6,000+ species is calling. Everything else is built on top of this.
- [BirdNET-Pi](https://github.com/mcguirepr89/BirdNET-Pi) by Patrick McGuire, which turned the model into a full realtime system for the Raspberry Pi. It adds 24/7 recording, automatic clip extraction, a SQLite database, a web interface, a live audio stream and spectrogram, notifications, and BirdWeather integration.
- [the BirdNET-Pi fork](https://github.com/Nachtzuster/BirdNET-Pi) by Nachtzuster, the maintained successor after McGuire's went dormant. It modernizes the stack with newer Raspberry Pi OS (Bookworm and Trixie) and tflite_runtime support, a reworked and more robust analysis pipeline, a more responsive web ui, backup and restore, more notification types, and the V2.4 range model.
- [AvianVisitors](https://github.com/Twarner491/AvianVisitors) by Twarner491, which this repo forked from. It keeps the recording, detection, clip extraction, live audio stream, charts, stats, and BirdWeather features, drops the admin tooling (web terminal, file manager, database admin, system info, FTP), and replaces the old dashboard with the illustrated bird collage as the main page.

Most of the code comes from them, especially the recording and detection under `birdnet/`, which stays under their original license (see `birdnet/LICENSE`).

What this repo adds is the packaging, and a fair amount of rebuilding on top of it.
Instead of a hand-managed install on the pi, the whole stack (recording, detection, the web interface, and the live audio) now comes up as a single Docker container.
The front end has been rewritten as a Vue 3 single-page app built around the collage, with a stats view and a full species atlas beside it and a small Slim backend underneath, and the illustrations it shows are generated rather than drawn, by a pipeline in webui/generate that runs on an NVIDIA GPU or falls back to the CPU.
Under all of that the toolchain has been brought up to current Node, PHP, and Python with fresh dependencies, the detection, backend, and front-end code now carry tests that run in CI, and everything else got tidied up along the way through mago, oxlint, and ruff.

## Contents

- [What you need](#what-you-need)
- [Install](#install)
- [Opening it](#opening-it)
- [The microphone](#the-microphone)
- [Location and settings](#location-and-settings)
- [Making more bird pictures](#making-more-bird-pictures)
- [Updating](#updating)
- [Where your data lives](#where-your-data-lives)

## What you need

- Any Linux box, preferably a Raspberry Pi (64-bit / arm64)
- A USB microphone plugged in
- Docker and Docker Compose installed

## Install

Clone the repo and bring it up:

```sh
git clone https://github.com/Twarner491/AvianVisitors.git
cd AvianVisitors
docker compose up -d --build
```

That builds the image and starts everything.
The first build takes a while on a pi because it installs the audio and detection bits.
After that it comes back up fast.

To see what it's doing:

```sh
docker compose logs -f
```

## Opening it

Open http://your-pi/ in a browser.
The collage is the main page.
There's also a small stats page at http://your-pi/stats.

It starts empty.
Birds appear as they get heard, so give it some time near a window with the mic.

## The microphone

The container already gets access to the mic through Docker Compose, so usually it just works.
If it can't record, list the sound cards it can see:

```sh
docker compose exec avianvisitors arecord -l
```

Pick your mic from that list and set it in docker-compose.yml, for example:

```yaml
environment:
  BIRDNET_REC_CARD: "plughw:1,0"
```

Then bring it back up:

```sh
docker compose up -d
```

## Location and settings

On the first run it guesses your latitude and longitude from your internet connection, which it uses to know which birds are likely in your area.
To set it yourself, put your coordinates in docker-compose.yml and restart:

```yaml
environment:
  BIRDNET_LATITUDE: "52.3759"
  BIRDNET_LONGITUDE: "4.8975"
```

```sh
docker compose up -d
```

Everything else lives in the config file at /data/birdnet.conf inside the data volume (see below), and the settings page in the web interface can change most of it too.

## Making more bird pictures

The pictures are real Creative-Commons photographs with the background cut away, not drawn by hand.
The repo already ships a full set, but you can make your own for your region.
This part downloads a big cutout model, so do it on your computer, not the pi.

It runs in Docker and the two steps are:

- photos.py fetches a photo per species, cuts the bird out, and credits the source
- build_masks.py rebuilds the collage shapes from the finished pictures

Look at a sample set first:

```sh
cd webui/generate
docker compose build generate
docker compose run --rm generate python photos.py --keep-raw
docker compose run --rm generate python build_masks.py
```

To do a whole set, make a text file with one `scientific name|common name` per line (commas or underscores work too) and point --labels at it.
With an eBird api key you can filter that list down to the birds actually seen in your area:

```sh
export EBIRD_API_KEY=your-key
docker compose run --rm generate python photos.py --labels my-birds.txt --ebird-region US-CA
docker compose run --rm generate python build_masks.py
```

Re-running only fetches birds you don't already have; add --force to redo one.

The new pictures land in webui/assets/.
To show them in the collage, rebuild the container:

```sh
docker compose up -d --build
```

## Updating

```sh
git pull
docker compose up -d --build
```

## Where your data lives

Two Docker volumes keep your stuff so it survives rebuilds and updates:

- the recordings and detection clips
- a /data volume with the database and the config file

Removing the containers does not touch these.
If you want a clean slate, delete the volumes with docker compose down -v.
