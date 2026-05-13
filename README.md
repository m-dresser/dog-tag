# DogTag

A tiny distributed bulletin board. Each running instance is one person's "wall." Post to your own wall, add teammates as friends by IP, and visit their walls. No database, no auth, no persistence — all state lives in memory and disappears on restart. Built as a hands-on target for installing the Datadog agent, log collection, and APM via `ddtrace`.

## Prerequisites

- Python 3.9+ (Amazon Linux 2023 ships this by default)
- Port 1337 open in the EC2 instance's security group (inbound, TCP, from your team's IPs)

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
python app.py
```

On startup the app prints the URL to share with teammates, e.g.:

```
🏷️  DogTag is running! Open your wall at: http://1.2.3.4:1337
```

Open that URL and click the wall header (it starts as `[ click to add your name ]`) to set your display name. Names are kept in memory only.

Set a different port with the `PORT` env var:

```bash
PORT=8080 python app.py
```

## Run with Datadog APM

After installing the Datadog agent on the instance:

```bash
DD_SERVICE=dogtag DD_ENV=learning DD_VERSION=1.0 ddtrace-run python app.py
```

## Logs

Structured JSON logs are written to `logs/app.log` (rotating, 5 MB × 3 backups) and also streamed to stdout.
