# DogTag — App Specification

## Overview

DogTag is a lightweight distributed social message board built for a team learning exercise. Each running instance represents one person's "wall" — they can receive posts from others, post to their own wall, and visit/post to teammates' walls. Instances discover each other manually via IP address (shared out-of-band). There is no central server; every instance is both a server and a client.

The primary goals of this app from a learning perspective are:
- Provide a realistic target for Datadog log collection (structured file logging)
- Provide a realistic target for Datadog APM instrumentation via `ddtrace`
- Be fun and interactive during a team exercise

The app should be dead simple to install and run. All complexity lives in the Datadog instrumentation step, not in the app itself.

---

## Tech Stack

- **Language**: Python 3.8+
- **Web framework**: Flask
- **CORS**: `flask-cors`, applied globally so browsers can make cross-origin requests directly to other instances
- **Frontend**: Single HTML file served by Flask, vanilla JS (no build step, no npm)
- **State**: In-memory only (a dict, no database). Data does not persist across restarts.
- **Logging**: Python `logging` module, writing JSON lines to `logs/app.log` via a rotating file handler. Also log to stdout.
- **Dependencies**: Flask, flask-cors, requests, ddtrace (listed in `requirements.txt` but instrumentation is opt-in at run time)

---

## Running the App

### Without instrumentation
```bash
pip install -r requirements.txt
WALL_OWNER="Your Name" python app.py
```

### With Datadog APM instrumentation
```bash
WALL_OWNER="Your Name" DD_SERVICE=dogtag DD_ENV=learning DD_VERSION=1.0 ddtrace-run python app.py
```

The app listens on `0.0.0.0:1337` by default. Port should be configurable via a `PORT` environment variable.

---

## Startup URL Discovery

On startup, the app should attempt to determine its public IP by making a request to the EC2 instance metadata service:

```
http://169.254.169.254/latest/meta-data/public-ipv4
```

Use a short timeout (2 seconds) on this request. If it succeeds, print the following to stdout (in addition to writing it to the log):

```
🏷️  DogTag is running! Open your wall at: http://<public-ip>:1337
```

If the metadata request fails (e.g. running outside EC2), fall back to `localhost`:

```
🏷️  DogTag is running! Open your wall at: http://localhost:1337
```

This line should be printed after Flask's own startup output so it's easy to spot.

---

## Data Model

All state is in-memory. On startup, initialize:

```python
state = {
    "owner": os.environ.get("WALL_OWNER", "anonymous"),  # display name for this instance
    "wall": [],        # list of post dicts
    "friends": []      # list of friend dicts
}
```

**Post object:**
```json
{
    "id": "uuid4 string",
    "author": "string",
    "body": "string",
    "timestamp": "ISO 8601 string"
}
```

**Friend object:**
```json
{
    "name": "string",
    "url": "http://<ip>:1337"
}
```

---

## API Endpoints

All API responses are JSON. All request bodies are JSON. CORS is enabled on all endpoints.

### `GET /api/wall`
Returns this instance's wall posts in reverse chronological order.

Response:
```json
{
    "owner": "string",
    "posts": [ ...post objects... ]
}
```

### `POST /api/wall`
Adds a new post to this instance's wall.

Request body:
```json
{
    "author": "string",
    "body": "string"
}
```

Response: the created post object, HTTP 201.

Validation: both `author` and `body` are required. Return HTTP 400 with an error message if missing.

### `GET /api/friends`
Returns the current friends list.

Response:
```json
{
    "friends": [ ...friend objects... ]
}
```

### `POST /api/friends`
Adds a new friend (another instance).

Request body:
```json
{
    "name": "string",
    "url": "http://<ip>:<port>"
}
```

Response: the created friend object, HTTP 201. Return HTTP 400 if `name` or `url` is missing, HTTP 409 if a friend with the same URL already exists.

### `DELETE /api/friends/<url_encoded_url>`
Removes a friend by their base URL.

Response: HTTP 204 on success, HTTP 404 if not found.

---

## Logging

On startup, create a `logs/` directory if it does not exist.

Configure two handlers:
1. A `RotatingFileHandler` writing to `logs/app.log`, max 5MB, 3 backups
2. A `StreamHandler` for stdout

Every log record should be emitted as a single JSON line with these fields:

```json
{
    "timestamp": "ISO 8601",
    "level": "INFO",
    "logger": "dogtag",
    "message": "human readable string",
    "...": "any additional context fields"
}
```

Use a custom JSON formatter. Do not use any third-party logging libraries.

**Events to log** (at minimum):

| Event | Level | Extra fields |
|---|---|---|
| App startup | INFO | `owner`, `port`, `public_url` |
| Post received on own wall | INFO | `author`, `body_length` |
| Friend added | INFO | `friend_name`, `friend_url` |
| Friend removed | INFO | `friend_url` |
| Bad request (validation failure) | WARNING | `endpoint`, `reason` |

---

## Frontend (GUI)

Served at `GET /` as a single HTML page. All interaction is via `fetch()` calls — to the local instance's API for local actions, and directly to remote instances' APIs for cross-instance actions (possible because CORS is enabled on all instances).

### Layout

Two-column layout on desktop, stacked on mobile.

**Left column — My Wall**
- Displays the owner's name at the top (from `WALL_OWNER` env var)
- Shows all posts on this instance's wall, newest first
- Each post shows: author name, body, timestamp
- "Post to my wall" form: text input for author name, textarea for message body, submit button
- Wall auto-refreshes every 10 seconds (simple `setInterval` + fetch)

**Right column — Friends**
- "Add friend" form: name input, URL input (e.g. `http://1.2.3.4:1337`), submit button
- List of added friends, each with:
  - Friend's name and URL
  - "Visit" button
  - "Remove" button

**Friend wall view**
When a user clicks "Visit" on a friend, the right column transitions to show that friend's wall, fetched directly from the friend's instance via `fetch()`. Includes a "Post to [friend]'s wall" form and a "Back to friends" button. Handle fetch errors gracefully — if the friend's instance is unreachable, display a clear error message rather than failing silently.

---

## Repository Structure

```
dogtag/
├── app.py                  # Flask app, all routes, logging setup
├── requirements.txt
├── README.md
├── templates/
│   └── index.html          # Single-page GUI
└── logs/                   # Created at runtime, gitignored
```

---

## README

The README should be concise and cover exactly:

1. Prerequisites (Python 3.8+)
2. Install: `pip install -r requirements.txt`
3. Run: `WALL_OWNER="Your Name" python app.py`
4. How to set port via `PORT` env var (default: 1337)
5. How to run with Datadog APM (`ddtrace-run` invocation with env vars)
6. Where logs are written (`logs/app.log`)
7. EC2 requirement: port 1337 must be open in the instance's security group
8. A one-paragraph description of what the app does

No other content. Keep it short.

---

## Design Notes for the Frontend

The GUI should evoke a classic BBS (Bulletin Board System) terminal aesthetic — think DOS-era ANSI art boards, but rendered cleanly in a modern browser. This is the primary visual direction; commit to it fully.

**Color palette:**
- Background: near-black, e.g. `#0D0D0D` or `#111111`
- Primary accent / interactive elements: Datadog purple `#632CA6`
- Lighter accent for hover states, borders, and highlights: `#9B59D0` or similar
- Text: off-white or light grey, e.g. `#E0E0E0`
- Muted/secondary text (timestamps, labels): `#888888`
- Post cards: very dark grey background, e.g. `#1A1A1A`, with a `#632CA6` left border or top border

**Typography:**
- Everything monospace. Use a web-safe monospace stack or load a single Google Font like `Share Tech Mono`, `VT323`, or `Courier Prime`. No sans-serif anywhere.
- The app title "DogTag" should be rendered as ASCII art in a `<pre>` block at the top of the page. Keep it compact — no wider than ~60 characters. Something like:

```
██████╗  ██████╗  ██████╗ ████████╗ █████╗  ██████╗ 
██╔══██╗██╔═══██╗██╔════╝ ╚══██╔══╝██╔══██╗██╔════╝ 
██║  ██║██║   ██║██║  ███╗   ██║   ███████║██║  ███╗
██║  ██║██║   ██║██║   ██║   ██║   ██╔══██║██║   ██║
██████╔╝╚██████╔╝╚██████╔╝   ██║   ██║  ██║╚██████╔╝
╚═════╝  ╚═════╝  ╚═════╝    ╚═╝   ╚═╝  ╚═╝ ╚═════╝ 
```

The ASCII art title should be rendered in `#632CA6` or the lighter accent purple.

**UI elements:**
- Borders everywhere: use box-drawing characters (`─`, `│`, `┌`, `┐`, `└`, `┘`) as decorative section dividers and panel borders where feasible in HTML, or simulate them with CSS borders styled to match
- Buttons should look like BBS-style selections: e.g. `[ POST ]`, `[ VISIT ]`, `[ REMOVE ]` — uppercase, bracketed, monospace
- Form inputs: dark background, purple border, no rounded corners
- Section headers styled like BBS menu headers: e.g. `=== MY WALL ===` or `--- FRIENDS ---` in purple or light accent
- Scrollbars styled if possible (webkit) to match the dark theme
- Blinking cursor effect on the page title or a tagline beneath the ASCII art (CSS animation, subtle)

**Posts:**
- Each post rendered as a "message" block with a top line showing author and timestamp in the style of a BBS message header:
```
┌─[ mikej ]──────────────────────[ 2025-05-01 14:32 ]─┐
│ Hey, tagging your wall!                               │
└───────────────────────────────────────────────────────┘
```
- Use `<pre>` or careful monospace CSS to achieve this — do not use an image

**Atmosphere:**
- A subtle scanline or noise texture overlay on the background is encouraged (CSS only, no images)
- No gradients except very subtle dark-to-darker on the background
- No rounded corners anywhere
- No shadows (or use purple-tinted glow instead of drop shadows)

The result should feel like a purple-tinted ANSI BBS that someone ported to the web — functional, readable, and unmistakably retro. A support engineer opening this for the first time should smile.

---

## Constraints and Non-Goals

- No authentication. Anyone who can reach the port can post to your wall.
- No persistence. Restarting the app clears all data.
- No rate limiting.
- No HTTPS (HTTP only — this runs inside a controlled AWS test environment).
- No database dependency of any kind.
- The app must run with a single `python app.py` command after `pip install`.
