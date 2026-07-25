# Running in Docker

The whole thing runs in one container on plain Debian.
It captures the mic over ALSA, runs the bird detection, and serves the web page on port 80.
There's no systemd inside the container, so supervisord runs the services instead.

## Contents

- [What runs inside](#what-runs-inside)
- [Start it](#start-it)
- [Microphone](#microphone)
- [Config](#config)
- [Live audio stream](#live-audio-stream)
- [Logs and control](#logs-and-control)
- [Prometheus metrics](#prometheus-metrics)
- [What doesn't work in a container](#what-doesnt-work-in-a-container)
- [How it's built](#how-its-built)

## What runs inside

Supervisord keeps these running:

| Service    | What it does                     | Default |
| ---------- | -------------------------------- | ------- |
| caddy      | Web server / proxy on port 80    | on      |
| php-fpm    | The PHP api for the collage      | on      |
| recording  | arecord, captures the mic to wav | on      |
| analysis   | The TFLite detection             | on      |
| charts     | Daily plots                      | on      |
| stats      | The Streamlit page at /stats     | on      |
| icecast    | Live audio stream backend        | off     |
| livestream | ffmpeg feeding icecast (/stream) | off     |

The collage is the web page (a Vue app); its api is the Slim backend under /api/.

## Start it

```sh
docker compose up -d --build
```

Open http://your-pi/.
Recordings, the database and the config file live in two named volumes (birdsongs and data), so they survive rebuilds.

## Microphone

The container already gets the host sound device and the audio group, both set in docker-compose.yml:

```yaml
devices:
  - "/dev/snd:/dev/snd"
group_add:
  - audio
```

BIRDNET_REC_CARD defaults to default.
If capture fails (cannot find card), list the cards and pin one:

```sh
docker compose exec avianvisitors arecord -l
```

Then set, e.g. BIRDNET_REC_CARD=plughw:1,0 in docker-compose.yml and run docker compose up -d again.

If the /dev/snd nodes on your host are owned by a group whose id differs from the container's audio group, add the host group id instead of the name:

```yaml
group_add:
  - "29"
```

## Config

First boot writes /data/birdnet.conf (latitude and longitude are guessed from your ip).
Edit that file for anything the env vars below don't cover, then docker compose restart.
The settings page in the web interface writes to it too.

The env vars in docker-compose.yml are applied to the config on every start:

| Variable          | What it does        |
| ----------------- | ------------------- |
| BIRDNET_REC_CARD  | ALSA capture device |
| BIRDNET_CHANNELS  | Number of channels  |
| BIRDNET_LATITUDE  | Set your latitude   |
| BIRDNET_LONGITUDE | Set your longitude  |
| AV_ADMIN_USER     | Admin username (default admin) |
| AV_ADMIN_PASSWORD | Admin password; gates recordings, livestream, stats, file browse and the admin tools |

## Admin auth

The public page shows the collage, stats, atlas, illustrations and species data to anyone.
Listening back to recordings, the live stream, the `/stats` dashboard, raw recording/chart browsing and the admin tools (settings, system, logs) are gated behind a single admin login.

Set `AV_ADMIN_PASSWORD` in docker-compose.yml to enable it; enforcement is at the Caddy edge plus a PHP guard.
With the password set, unauthenticated visitors see the listen-back controls greyed out.
Leave `AV_ADMIN_PASSWORD` empty to disable auth entirely and serve everything publicly (the original behaviour).

## Live audio stream

Icecast and livestream are off by default.
To turn them on, set autostart=true for both in docker/supervisord.conf and rebuild.
On a single mic this fights the recorder (both open the device), so you need an rtsp source or a shareable ALSA dsnoop device to run both at once.

## Logs and control

Everything logs to the container:

```sh
docker compose logs -f
docker exec avianvisitors supervisorctl status
docker exec avianvisitors supervisorctl restart analysis
```

## Prometheus metrics

The container exposes `/metrics` on the main port in the Prometheus text format.
It is a plain scrape endpoint with no state of its own: every value is read fresh out of the detections database, the recordings folder, `/proc` and the container's own cgroup when you ask for it.

It sits behind the admin login, so point Prometheus at it with the same credentials you set in `AV_ADMIN_USER` and `AV_ADMIN_PASSWORD`:

```yaml
scrape_configs:
  - job_name: avianvisitors
    static_configs:
      - targets: ["birdpi:80"]
    basic_auth:
      username: your-admin-user
      password: your-admin-password
```

Leaving the admin variables empty serves `/metrics` to anyone who can reach the port, exactly like the rest of the admin surface.
The public gallery on port 8081 never exposes it, whether auth is on or off.

The interesting families are the ones that tell you the listening pipeline is healthy rather than the ones that count birds.
`avianvisitors_segments_pending` is the recorded audio waiting for the analyser, and a number that climbs and never drains means the Pi cannot keep up with the mic.
`avianvisitors_analysis_lag_seconds` is the age of the newest detection, which is the fastest way to notice that detection stopped without anything crashing.
`avianvisitors_alsa_capture_running` drops to zero the moment the capture device stops, which catches an unplugged usb mic long before the lag metric notices.
`avianvisitors_container_cpu_throttled_seconds_total` rising is the container being starved of cpu, usually the real cause behind a growing backlog.
Alongside those are the bird ones: `avianvisitors_detections_total` per species, the life list, the 24 hour counts, and a histogram of detection confidence.

Anything that only the python side can measure, such as how long the model takes per file, can be dropped into `/data/metrics` as a `.prom` file.
The endpoint appends every such file to its own output, so a producer needs nothing but a text file and a unique metric name.

There is a ready made Grafana dashboard at [grafana-dashboard.json](grafana-dashboard.json) that plots every metric the endpoint exports.
Import it from Dashboards, New, Import, upload the file, and pick your Prometheus data source when it asks.
It has no hardcoded data source or job name, so nothing needs editing first, and the instance picker at the top lets one dashboard cover several boxes.

The top row is the one to look at when something feels wrong: detection lag, microphone state, backlog, services down, database and data volume, each coloured green until it isn't.
Below that sit the birds (calls per hour by species, the top species table, the confidence heatmap), then the pipeline ages, the microphone details, the supervised services, the container's own memory and cpu throttling, and finally disk, database growth and the exporter's own scrape time.

## What doesn't work in a container

The collage has an admin overlay.
The settings page works and writes the config, but it can't restart services or tail logs the way the original did, because that needed systemd and journald, which aren't in the container.
So:

- After changing settings, restart the container: docker compose restart
- For logs, use docker compose logs -f
- For service control, use docker exec avianvisitors supervisorctl ...

## How it's built

- The base image is Debian bookworm-slim with Python 3.11 (the tflite wheel is built for cp311).
- The Python deps come from birdnet/ and are installed with uv into the venv at /home/birdnet/BirdNET-Pi/.venv, which is where supervisord looks for them.
- The tflite runtime wheel is downloaded in the Dockerfile, picked by arch.
- It builds for both amd64 and arm64; the pi uses arm64.
