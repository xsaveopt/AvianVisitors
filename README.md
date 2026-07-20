# Avian Visitors

A live bird collage from a window microphone.
A small mic listens, BirdNET works out which bird is calling, and each species joins the collage as a cut-out photo, sized by how often it has been heard.

It all runs in one Docker container on a Raspberry Pi (or any Debian box).
The container records the audio, runs the detection, and serves the web page.

## Fork history

This is the far end of a fork chain:

- [BirdNET-Lite](https://github.com/birdnet-team/BirdNET-Lite), the original from the BirdNET team at the Cornell Lab of Ornithology. It is the TFLite sound recognition model and analyzer that identifies which of 6,000+ species is calling. Everything else is built on top of this.
- [BirdNET-Pi](https://github.com/mcguirepr89/BirdNET-Pi) by Patrick McGuire, which turned the model into a full realtime system for the Raspberry Pi. It adds 24/7 recording, automatic clip extraction, a SQLite database, a web interface, a live audio stream and spectrogram, notifications, and BirdWeather integration.
- [the BirdNET-Pi fork](https://github.com/Nachtzuster/BirdNET-Pi) by Nachtzuster, the maintained successor after McGuire's went dormant. It modernizes the stack with newer Raspberry Pi OS (Bookworm and Trixie) and tflite_runtime support, a reworked and more robust analysis pipeline, a more responsive web ui, backup and restore, more notification types, and the V2.4 range model.
- [AvianVisitors](https://github.com/Twarner491/AvianVisitors) by Twarner491, which this repo forked from. It keeps the recording, detection, clip extraction, live audio stream, charts, stats, and BirdWeather features, drops the admin tooling (web terminal, file manager, database admin, system info, FTP), and makes a bird collage the main page.

Most of the code comes from them, especially the recording and detection under `birdnet/`, which stays under their original license (see `birdnet/LICENSE`).

This repo packages the whole stack as one Docker container and rebuilds the surface on top of it.
The front end is a Vue 3 single-page app built around the collage, with a stats view and a full species atlas beside it and a small Slim backend underneath.
Each bird in the collage is a real Creative-Commons photo with the background matted away, produced by the cutout pipeline in webui/generate.
The Node, PHP, and Python toolchain is current, and the detection, backend, and front-end carry tests that run in CI.

## Contents

- [What you need](#what-you-need)
- [Install](#install)
- [The microphone](#the-microphone)
- [Container variables](#container-variables)
- [The admin login](#the-admin-login)
- [A public gallery](#a-public-gallery)
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

## Container variables

| Variable          | What it does                                                                        |
| ----------------- | ----------------------------------------------------------------------------------- |
| BIRDNET_REC_CARD  | ALSA card for the mic, like plughw:1,0 (default `default`)                          |
| BIRDNET_CHANNELS  | Mic channel count, 1 or 2 (default 2)                                               |
| BIRDNET_LATITUDE  | Your latitude for the range filter, guessed from your connection when empty         |
| BIRDNET_LONGITUDE | Your longitude                                                                      |
| AV_ADMIN_USER     | Admin username, must be set to enable the login                                     |
| AV_ADMIN_PASSWORD | Admin password, must be set to enable the login                                     |
| AV_PUBLIC_GALLERY | Set to `true` to serve the locked-down public gallery on port 8081 (off by default) |
| AV_PUBLIC_PATH    | Optional path to mount that gallery under, like /birds; empty serves it at the root |

Everything past these knobs is in /data/birdnet.conf and the settings page.

## The admin login

The collage, stats, and species pages are public to anyone who can reach them.
The tools behind the menu, the recordings, and the live audio stream sit behind a single admin login instead.
That login stays off until you set both AV_ADMIN_USER and AV_ADMIN_PASSWORD, and there is no default for either, so until you choose a username and a password those protected parts are open to everyone.

```yaml
environment:
  AV_ADMIN_USER: "your-name"
  AV_ADMIN_PASSWORD: "a-long-random-passphrase"
```

```sh
docker compose up -d
```

Open the menu on the page and enter that username and password to unlock the tools.
Setting only one of the two leaves the login off, so set both.

## A public gallery

The main page on port 80 is the whole app, with the menu, the stats, the atlas, and the admin tools behind it, so it is meant for you and your own network.
When you want to let the outside world watch your birds without handing them any of that, there is a second, stripped-down page for exactly this.

Set AV_PUBLIC_GALLERY to true and the container serves a hardened gallery on port 8081.
It shows only the collage of what has been heard in the last 24 hours and nothing else, with no menu, no stats, no atlas, and nothing to click through to.

This is a separate build, not the real app with things hidden.
The page a visitor downloads contains only the collage, so it carries none of the admin screens, none of the login code, and no list of the private api paths.
It talks to exactly one endpoint that returns just the species names and how many times each was heard, with no timestamps, no confidence scores and no recording filenames, and the pictures it can request are limited to the species actually in that 24 hour window.
Everything else on that port answers with a bare 404.

```yaml
environment:
  AV_PUBLIC_GALLERY: "true"
```

For reverse proxies:
Subdomain:

```caddy
gallery.example.com {
    reverse_proxy 127.0.0.1:8081
}
```

Subpath:
`AV_PUBLIC_PATH=/birds`

```caddy
example.com {
    reverse_proxy /birds* 127.0.0.1:8081
}
```

## Making more bird pictures

The pictures are real Creative-Commons photographs with the background cut away.
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

The whole set is kept as a single webui/assets/illustrations.tar so the repo holds one file instead of a folder of hundreds.
photos.py unpacks it before a run and repacks it after, build_masks.py reads from it, and the container build unpacks it into the image, so you never handle the archive by hand.
To show new pictures in the collage, rebuild the container:

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
