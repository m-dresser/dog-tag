import json
import logging
import logging.handlers
import os
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import unquote

import requests
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS


state = {
    "owner": None,
    "wall": [],
    "friends": [],
}
state_lock = threading.Lock()


LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "app.log")
LOGGER_NAME = "dogtag"


class JsonFormatter(logging.Formatter):
    RESERVED = {
        "name", "msg", "args", "levelname", "levelno", "pathname",
        "filename", "module", "exc_info", "exc_text", "stack_info",
        "lineno", "funcName", "created", "msecs", "relativeCreated",
        "thread", "threadName", "processName", "process", "message",
        "asctime", "taskName",
    }

    def format(self, record):
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in self.RESERVED or key.startswith("_"):
                continue
            payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    formatter = JsonFormatter()

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return logger


log = setup_logging()


IMDS_BASE = "http://169.254.169.254"
IMDS_TIMEOUT = 2.0


def fetch_public_ip():
    try:
        token_resp = requests.put(
            f"{IMDS_BASE}/latest/api/token",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"},
            timeout=IMDS_TIMEOUT,
        )
        if token_resp.status_code == 200 and token_resp.text:
            ip_resp = requests.get(
                f"{IMDS_BASE}/latest/meta-data/public-ipv4",
                headers={"X-aws-ec2-metadata-token": token_resp.text},
                timeout=IMDS_TIMEOUT,
            )
            if ip_resp.status_code == 200 and ip_resp.text.strip():
                return ip_resp.text.strip()
    except requests.RequestException:
        pass

    try:
        ip_resp = requests.get(
            f"{IMDS_BASE}/latest/meta-data/public-ipv4",
            timeout=IMDS_TIMEOUT,
        )
        if ip_resp.status_code == 200 and ip_resp.text.strip():
            return ip_resp.text.strip()
    except requests.RequestException:
        pass

    return None


def normalize_url(value):
    if not isinstance(value, str):
        return ""
    return value.strip().rstrip("/")


def now_iso():
    return datetime.now(tz=timezone.utc).isoformat()


app = Flask(__name__)
CORS(app)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/owner", methods=["GET"])
def get_owner():
    with state_lock:
        return jsonify({"owner": state["owner"]})


@app.route("/api/owner", methods=["PUT"])
def set_owner():
    data = request.get_json(silent=True) or {}
    raw = data.get("name")
    name = raw.strip() if isinstance(raw, str) else ""
    if not name:
        log.warning(
            "validation failed",
            extra={"endpoint": "PUT /api/owner", "reason": "name is required"},
        )
        return jsonify({"error": "name is required"}), 400
    with state_lock:
        state["owner"] = name
    log.info("owner set", extra={"owner": name})
    return jsonify({"owner": name}), 200


@app.route("/api/wall", methods=["GET"])
def get_wall():
    with state_lock:
        posts = list(reversed(state["wall"]))
        owner = state["owner"]
    return jsonify({"owner": owner, "posts": posts})


@app.route("/api/wall", methods=["POST"])
def post_wall():
    data = request.get_json(silent=True) or {}
    author = (data.get("author") or "").strip() if isinstance(data.get("author"), str) else ""
    body = (data.get("body") or "").strip() if isinstance(data.get("body"), str) else ""
    if not author or not body:
        log.warning(
            "validation failed",
            extra={"endpoint": "POST /api/wall", "reason": "author and body are required"},
        )
        return jsonify({"error": "author and body are required"}), 400

    post = {
        "id": str(uuid.uuid4()),
        "author": author,
        "body": body,
        "timestamp": now_iso(),
    }
    with state_lock:
        state["wall"].append(post)
    log.info("post received", extra={"author": author, "body_length": len(body)})
    return jsonify(post), 201


@app.route("/api/friends", methods=["GET"])
def get_friends():
    with state_lock:
        friends = list(state["friends"])
    return jsonify({"friends": friends})


@app.route("/api/friends", methods=["POST"])
def add_friend():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip() if isinstance(data.get("name"), str) else ""
    url = normalize_url(data.get("url"))
    if not name or not url:
        log.warning(
            "validation failed",
            extra={"endpoint": "POST /api/friends", "reason": "name and url are required"},
        )
        return jsonify({"error": "name and url are required"}), 400

    with state_lock:
        if any(f["url"] == url for f in state["friends"]):
            log.warning(
                "validation failed",
                extra={"endpoint": "POST /api/friends", "reason": "duplicate friend url"},
            )
            return jsonify({"error": "friend with that url already exists"}), 409
        friend = {"name": name, "url": url}
        state["friends"].append(friend)
    log.info("friend added", extra={"friend_name": name, "friend_url": url})
    return jsonify(friend), 201


@app.route("/api/friends/<path:encoded_url>", methods=["DELETE"])
def remove_friend(encoded_url):
    url = normalize_url(unquote(encoded_url))
    with state_lock:
        for i, friend in enumerate(state["friends"]):
            if friend["url"] == url:
                state["friends"].pop(i)
                log.info("friend removed", extra={"friend_url": url})
                return "", 204
    return jsonify({"error": "friend not found"}), 404


def _format_public_url(host, public_port):
    if public_port == 80:
        return f"http://{host}"
    return f"http://{host}:{public_port}"


def _print_startup_banner(bind_port, public_port):
    time.sleep(0.4)
    ip = fetch_public_ip()
    host = ip if ip else "localhost"
    public_url = _format_public_url(host, public_port)
    print(f"\n🏷️  DogTag is running! Open your wall at: {public_url}\n", flush=True)
    log.info(
        "startup",
        extra={
            "owner": state["owner"],
            "port": bind_port,
            "public_port": public_port,
            "public_url": public_url,
        },
    )


if __name__ == "__main__":
    bind_port = int(os.environ.get("PORT", 1337))
    public_port = int(os.environ.get("PUBLIC_PORT", bind_port))
    threading.Thread(
        target=_print_startup_banner, args=(bind_port, public_port), daemon=True
    ).start()
    app.run(host="0.0.0.0", port=bind_port, debug=False, use_reloader=False)
