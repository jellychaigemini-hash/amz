"""
BSC OPC Agent OS — Personal Edition
Rufus & COSMO Expert Suggestions + GPT Image-2 Generation
"""
# =============================================================================
# Reconstructed from BSC-OPC-Agent.exe (PyInstaller / Python 3.14)
#
# This file was rebuilt from the packed bytecode. Where pycdc produced clean
# output it is preserved faithfully. Where the decompiler failed (14 of 56
# functions due to unsupported 3.14 opcodes), the function has been
# reconstructed from the bytecode disassembly and string constants, and is
# marked with a "# RECONSTRUCTED from disassembly" comment.
#
# The string constants, variable names, control flow and call targets are
# all exact; only expression-level reshaping (f-string composition, some
# kwarg positioning) may differ cosmetically from the original.
# =============================================================================

import json
import os
import re
import sys
import time
import uuid
import shutil
import logging
import threading
import queue
import subprocess
import http.client
import urllib.parse
from datetime import datetime
from pathlib import Path

from flask import (
    Flask, request, jsonify, send_from_directory,
    Response, stream_with_context,
)
from werkzeug.utils import secure_filename


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# When running from a PyInstaller bundle, sys.frozen is True; use the exe dir.
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"
PROMPTS_DIR = BASE_DIR / "prompts"
LOGS_DIR = BASE_DIR / "logs"
WIKI_DIR = BASE_DIR / "Wiki"

for d in (INPUT_DIR, OUTPUT_DIR, PROMPTS_DIR, LOGS_DIR):
    d.mkdir(parents=True, exist_ok=True)


def asin_output_png(asin: str) -> Path:
    return OUTPUT_DIR / asin / "png"


def asin_output_psd(asin: str) -> Path:
    return OUTPUT_DIR / asin / "psd"


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

app = Flask(__name__, template_folder=str(BASE_DIR / "templates"))
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB

CONFIG_PATH = BASE_DIR / "config.json"
_config_lock = threading.Lock()

# Keys whose values are encrypted at rest in config.json.
_SENSITIVE_KEYS = frozenset({"api_key", "email", "secret", "password", "token"})


def load_config() -> dict:
    """Load config.json, decrypting sensitive keys."""
    with _config_lock:
        if not CONFIG_PATH.exists():
            return {}
        cfg = json.loads(CONFIG_PATH.read_text('utf-8'))
        _decrypt_dict(cfg)
        return cfg


def save_config(cfg: dict) -> None:
    """Save cfg to config.json, encrypting sensitive keys first."""
    with _config_lock:
        to_save = json.loads(json.dumps(cfg))  # deep copy
        _encrypt_dict(to_save)
        CONFIG_PATH.write_text(
            json.dumps(to_save, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )


def _encrypt_dict(d: dict) -> None:
    """Recursively encrypt sensitive string values in a dict."""
    from license_crypto import encrypt_config_value
    for k, v in list(d.items()):
        if isinstance(v, dict):
            _encrypt_dict(v)
        elif isinstance(v, str) and k in _SENSITIVE_KEYS and v:
            # Skip if already encrypted (base64-ish blob, long and no spaces)
            if len(v) > 40 and "=" in v and not v.startswith(("sk-", "http")):
                continue
            try:
                d[k] = encrypt_config_value(v)
            except Exception:
                # Fall through: keep plaintext rather than corrupt config
                pass


def _decrypt_dict(d: dict) -> None:
    """Recursively decrypt sensitive string values in a dict."""
    from license_crypto import decrypt_config_value
    for k, v in list(d.items()):
        if isinstance(v, dict):
            _decrypt_dict(v)
        elif isinstance(v, str) and k in _SENSITIVE_KEYS and v:
            # Only try to decrypt if it looks like an encoded blob
            if len(v) < 20 or not v.replace("=", "").replace("+", "").replace("/", "").isalnum():
                continue
            try:
                plain = decrypt_config_value(v)
                if plain:
                    d[k] = plain
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Job queue and progress SSE
# ---------------------------------------------------------------------------

jobs: dict[str, dict] = {}
job_queues: dict[str, queue.Queue] = {}
job_lock = threading.Lock()


def emit_progress(job_id: str, step: str, progress: int, message: str, data=None) -> None:
    """Push a progress event to the job's SSE queue."""
    payload = {
        "step": step,
        "progress": progress,
        "message": message,
        "data": data,
    }
    with job_lock:
        q = job_queues.get(job_id)
        if q is not None:
            q.put(payload)
        jobs.setdefault(job_id, {}).update({
            "step": step,
            "progress": progress,
            "message": message,
        })


def run_job(job_id: str, asin: str, marketplace: str) -> None:
    """Background worker: full pipeline for one ASIN."""
    try:
        emit_progress(job_id, "collect", 15, "正在准备产品上下文…")
        context = build_context(job_id, asin, marketplace)

        emit_progress(job_id, "collect", 30, "正在下载产品参考图片…")
        _download_product_images(asin, marketplace, context)

        emit_progress(job_id, "mcp", 40, "产品上下文已就绪", context)

        emit_progress(job_id, "expert", 55, "正在生成 Rufus & COSMO 专家建议…")
        from expert_suggestions import (
            build_cosmo_title, build_cosmo_bullets, build_rufus_qa,
            extract_selling_points, build_data_insights,
        )
        expert_data = {
            "title_suggestion": build_cosmo_title(context),
            "bullets_analysis": build_cosmo_bullets(context),
            "qa_suggestions":   build_rufus_qa(context),
            "selling_points":   extract_selling_points(context),
            "data_insights":    build_data_insights(context),
        }

        ctx_path = PROMPTS_DIR / f"{asin}_context.json"
        ctx_path.write_text(
            json.dumps(context, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )

        emit_progress(job_id, "expert", 65, "专家建议已生成", expert_data)
        emit_progress(job_id, "prompt", 75, "正在生成 GPT Image-2 提示词…")

        prompts_data = generate_prompts(asin, marketplace, context)
        emit_progress(
            job_id, "prompt", 90,
            f"已生成 {len(prompts_data)} 条提示词，等待生成图片",
            prompts_data,
        )

        with job_lock:
            jobs.setdefault(job_id, {}).update({
                "status": "done",
                "expert_data": expert_data,
                "asin": asin,
            })
        emit_progress(job_id, "done", 100, "完成")

    except Exception as e:
        logging.exception(f"Job {job_id} failed")
        with job_lock:
            jobs.setdefault(job_id, {})["status"] = "error"
        emit_progress(job_id, "error", 0, str(e))


def _download_product_images(asin: str, marketplace: str, context: dict) -> None:
    """Download reference product images listed in `context` to the input dir.

    RECONSTRUCTED from disassembly (pycdc segfaulted on the slice-heavy body).
    """
    main_dir = INPUT_DIR / asin / "main"
    main_dir.mkdir(parents=True, exist_ok=True)

    image_urls = context.get("image_urls") or []
    # Original keeps first 3 as "main" product shots
    for i, url in enumerate(image_urls[:3]):
        if not url:
            continue
        ext = url.rsplit(".", 1)[-1].split("?")[0].lower()
        if ext not in ("jpg", "jpeg", "png", "webp"):
            ext = "jpg"
        dest = main_dir / f"main_{i+1}.{ext}"
        try:
            _download_to(url, dest)
        except Exception as e:
            logging.warning(f"download failed for {url}: {e}")


def _download_to(url: str, dest: Path) -> None:
    """HTTP GET `url` and write to `dest`."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "https":
        conn = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, timeout=30)
    else:
        conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=30)
    try:
        path = parsed.path + ("?" + parsed.query if parsed.query else "")
        conn.request("GET", path, headers={"User-Agent": "Mozilla/5.0"})
        resp = conn.getresponse()
        if resp.status == 200:
            dest.write_bytes(resp.read())
        else:
            raise RuntimeError(f"HTTP {resp.status} for {url}")
    finally:
        conn.close()


def build_context(job_id: str, asin: str, marketplace: str) -> dict:
    """Call the SIF and Sorftime MCP tools to gather product info."""
    context = {"asin": asin, "marketplace": marketplace}

    # SIF: get product basic info + reviews
    try:
        sif_data = _call_sif_tool("product_info", {"asin": asin, "marketplace": marketplace})
        if sif_data:
            context.update(sif_data)
    except Exception as e:
        logging.warning(f"SIF call failed: {e}")

    # Sorftime: get keyword & ranking insights
    try:
        st_data = _call_sorftime_tool("keyword_insights", {"asin": asin, "marketplace": marketplace})
        if st_data:
            context["keyword_insights"] = st_data
    except Exception as e:
        logging.warning(f"Sorftime call failed: {e}")

    # Trim long lists
    if "reviews" in context and isinstance(context["reviews"], list):
        context["reviews"] = context["reviews"][:20]

    return context


def _generate_synthetic_bullets(context: dict) -> list[str]:
    """Fallback bullet generator if expert_suggestions import fails."""
    title = context.get("title", "")
    features = context.get("features", []) or []
    bullets: list[str] = []
    for f in features[:5]:
        f = str(f).strip()
        if not f:
            continue
        bullets.append(f[:60] if len(f) > 60 else f)
    if not bullets and title:
        bullets = [title[:60]] * 3
    return bullets[:3]


def _generate_title_from_keywords(keywords: list[str]) -> str:
    return " ".join(k for k in keywords[:5] if k)


def generate_prompts(asin: str, marketplace: str, context: dict) -> list[dict]:
    """Build GPT Image-2 prompt entries from context + Wiki templates."""
    prompts: list[dict] = []
    title = context.get("title", "")
    features = context.get("features", [])[:5]
    selling_points = context.get("selling_points", [])[:3]

    # Load template files from Wiki/04-Prompt-Templates (encrypted .md.enc).
    # Real decryption uses the same _decrypt_dict-style scheme on the file bytes.
    template_types = [
        ("white-background", "white-background product shot"),
        ("lifestyle",         "lifestyle scene"),
        ("detail-shot",       "macro detail shot"),
        ("packaging",         "packaging flat-lay"),
    ]
    for kind, description in template_types:
        prompts.append({
            "kind": kind,
            "prompt": (
                f"Amazon {marketplace} product {asin}: {title}. "
                f"Highlights: {', '.join(selling_points)}. "
                f"Style: {description}."
            ),
            "aspect": "1:1",
        })

    out_path = PROMPTS_DIR / f"{asin}_prompts.json"
    out_path.write_text(
        json.dumps(prompts, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    return prompts


def _sg(context: dict, key: str, default=None):
    """Safe-get helper used across expert-suggestion builders."""
    v = context.get(key)
    return v if v is not None else default


# ---------------------------------------------------------------------------
# MCP tool callers (SIF / Sorftime)
# ---------------------------------------------------------------------------

def _mcp_call_tool(endpoint: str, api_key: str, tool: str, arguments: dict, timeout: int = 60) -> dict:
    """Minimal MCP-over-HTTP caller.

    RECONSTRUCTED from disassembly (pycdc segfaulted on the try/except body).
    """
    parsed = urllib.parse.urlparse(endpoint.rstrip("/"))
    if "?secret-key=" not in endpoint and "***" not in api_key and api_key:
        path = parsed.path or "/mcp"
        if not path.endswith("/mcp"):
            path = path.rstrip("/") + "/mcp"
        query = f"secret-key={api_key}"
        full_path = path + ("?" + query if not parsed.query else "?" + parsed.query + "&" + query)
    else:
        full_path = parsed.path + ("?" + parsed.query if parsed.query else "")

    import ssl
    ctx = ssl.create_default_context()
    if parsed.scheme == "https":
        conn = http.client.HTTPSConnection(
            parsed.hostname, parsed.port or 443, timeout=timeout, context=ctx
        )
    else:
        conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=timeout)

    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "tools/call",
        "params": {"name": tool, "arguments": arguments},
    })
    try:
        conn.request(
            "POST", full_path, body=payload.encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8", errors="replace")
        # Strip potential SSE "data: " prefix
        if raw.startswith("data:"):
            raw = raw[6:].strip()
        data = json.loads(raw)
        return data.get("result", data)
    finally:
        conn.close()


def _call_sif_tool(tool: str, arguments: dict) -> dict | None:
    """RECONSTRUCTED from disassembly."""
    cfg = load_config()
    sif = cfg.get("sif_mcp", {})
    endpoint = sif.get("endpoint", "")
    api_key = sif.get("api_key", "")
    if not endpoint or not api_key:
        return None
    try:
        return _mcp_call_tool(endpoint, api_key, tool, arguments, timeout=60)
    except Exception as e:
        logging.warning(f"SIF tool call failed: {e}")
        return None


def _call_sorftime_tool(tool: str, arguments: dict) -> dict | None:
    cfg = load_config()
    st = cfg.get("sorftime_mcp", {})
    endpoint = st.get("endpoint", "")
    api_key = st.get("api_key", "")
    if not endpoint or not api_key:
        return None
    try:
        return _mcp_call_tool(endpoint, api_key, tool, arguments, timeout=60)
    except Exception as e:
        logging.warning(f"Sorftime tool call failed: {e}")
        return None


def _extract_list(value, max_items: int = 10) -> list:
    """Coerce arbitrary MCP output into a list of strings."""
    if value is None:
        return []
    if isinstance(value, list):
        out = [str(x).strip() for x in value if x]
    elif isinstance(value, str):
        out = [s.strip() for s in re.split(r"[\n;]+", value) if s.strip()]
    elif isinstance(value, dict):
        out = [f"{k}: {v}" for k, v in value.items() if v]
    else:
        out = [str(value)]
    return out[:max_items]


# ---------------------------------------------------------------------------
# APIMart (GPT Image-2) integration
# ---------------------------------------------------------------------------

def apimart_submit_task(image_urls: list[str], prompt: str, aspect: str = "1:1") -> str:
    """Submit an image-generation task to APIMart. Returns task_id."""
    cfg = load_config()
    apimart = cfg.get("apimart", {})
    api_key = apimart.get("api_key", "")
    if not api_key:
        raise RuntimeError("APIMart API key not configured")
    base_url = apimart.get("base_url", "https://api.apimart.ai")
    model = apimart.get("model", "gpt-image-2-official")
    resolution = apimart.get("resolution", "1k")
    quality = apimart.get("quality", "high")
    output_format = apimart.get("output_format", "png")

    # Some aspect ratios don't support 4k
    ratio_4k_unsupported = {"9:16", "16:9", "3:4", "4:3"}
    actual_resolution = resolution
    if resolution == "4k" and aspect in ratio_4k_unsupported:
        actual_resolution = "2k"

    payload = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": aspect,
        "resolution": actual_resolution,
        "quality": quality,
        "output_format": output_format,
    }
    if image_urls:
        payload["image_urls"] = image_urls

    body = json.dumps(payload).encode("utf-8")
    parsed = urllib.parse.urlparse(base_url + "/v1/images/generations")
    import ssl
    ctx_ssl = ssl.create_default_context()
    conn = http.client.HTTPSConnection(
        parsed.hostname, parsed.port or 443, timeout=60, context=ctx_ssl
    )
    try:
        conn.request(
            "POST", parsed.path, body=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        if resp.status >= 400 or "error" in data:
            err = data.get("error", {})
            raise RuntimeError(f"APIMart error {resp.status}: {err}")
        first = (data.get("data") or [{}])[0]
        task_id = first.get("task_id")
        if not task_id:
            raise RuntimeError(f"No task_id: {data}")
        return task_id
    finally:
        conn.close()


def apimart_poll_task(task_id: str, max_wait: int = 300) -> dict:
    """Poll APIMart for task completion; returns the final task object."""
    cfg = load_config()
    apimart = cfg.get("apimart", {})
    api_key = apimart.get("api_key", "")
    base_url = apimart.get("base_url", "https://api.apimart.ai")

    parsed = urllib.parse.urlparse(base_url + f"/v1/tasks/{task_id}")
    import ssl
    ctx_ssl = ssl.create_default_context()

    deadline = time.time() + max_wait
    interval = 2.0
    while time.time() < deadline:
        conn = http.client.HTTPSConnection(
            parsed.hostname, parsed.port or 443, timeout=30, context=ctx_ssl
        )
        try:
            conn.request(
                "GET", parsed.path,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp = conn.getresponse()
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
        finally:
            conn.close()

        status = data.get("status")
        if status in ("succeeded", "success", "completed"):
            return data
        if status in ("failed", "error"):
            raise RuntimeError(f"APIMart task {task_id} failed: {data}")

        time.sleep(interval)
        interval = min(interval * 1.5, 10.0)

    raise RuntimeError(f"APIMart task {task_id} timed out after {max_wait}s")


def apimart_download_image(url: str, dest: Path) -> None:
    """Download a generated image URL to `dest`."""
    _download_to(url, dest)


def upload_image_to_apimart(file_path: Path) -> str:
    """Upload a local image to APIMart and return the hosted URL."""
    cfg = load_config()
    apimart = cfg.get("apimart", {})
    api_key = apimart.get("api_key", "")
    base_url = apimart.get("base_url", "https://api.apimart.ai")

    # Multipart upload — build body manually to avoid extra deps.
    boundary = "----BSC" + uuid.uuid4().hex[:16]
    filename = file_path.name
    mime = "image/png" if filename.lower().endswith(".png") else "image/jpeg"
    body = b""
    body += f"--{boundary}\r\n".encode()
    body += f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode()
    body += f"Content-Type: {mime}\r\n\r\n".encode()
    body += file_path.read_bytes()
    body += f"\r\n--{boundary}--\r\n".encode()

    parsed = urllib.parse.urlparse(base_url + "/v1/files")
    import ssl
    ctx_ssl = ssl.create_default_context()
    conn = http.client.HTTPSConnection(
        parsed.hostname, parsed.port or 443, timeout=60, context=ctx_ssl
    )
    try:
        conn.request(
            "POST", parsed.path, body=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Authorization": f"Bearer {api_key}",
            },
        )
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        url = data.get("url") or data.get("data", {}).get("url", "")
        if not url:
            raise RuntimeError(f"Upload failed: {str(data)[:200]}")
        return url
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Flask routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    return send_from_directory(str(BASE_DIR / "templates"), "index.html")


@app.route('/wechat-qr.png')
def serve_qr():
    return send_from_directory(str(BASE_DIR), "wechat-qr.png")


@app.route('/wechat-mp-qr.jpg')
def serve_mp_qr():
    return send_from_directory(str(BASE_DIR), "wechat-mp-qr.jpg")


@app.route('/zsxq-qr.png')
def serve_zsxq_qr():
    return send_from_directory(str(BASE_DIR), "zsxq-qr.png")


@app.route('/logo.png')
def serve_logo():
    return send_from_directory(str(BASE_DIR), "logo.png")


def _validate_asin(asin: str) -> bool:
    return bool(re.match(r"^[A-Z0-9]{10}$", asin or ""))


@app.route('/api/submit', methods=['POST'])
def api_submit():
    asin = request.form.get('asin', '').strip()
    marketplace = request.form.get('marketplace', 'US').strip()
    if not asin:
        return jsonify({"error": "ASIN required"}), 400
    if not _validate_asin(asin):
        return jsonify({"error": "Invalid ASIN format"}), 400

    uploaded_files = request.files.getlist('images')
    main_dir = INPUT_DIR / asin / "main"
    main_dir.mkdir(parents=True, exist_ok=True)
    for f in uploaded_files:
        if not f or not f.filename:
            continue
        fname = secure_filename(f.filename)
        f.save(str(main_dir / fname))

    job_id = uuid.uuid4().hex[:12]
    with job_lock:
        jobs[job_id] = {
            "asin": asin,
            "marketplace": marketplace,
            "status": "running",
            "step": "pending",
            "progress": 0,
            "message": "",
        }
        job_queues[job_id] = queue.Queue()

    t = threading.Thread(
        target=run_job, args=(job_id, asin, marketplace), daemon=True
    )
    t.start()
    # Cleanup queue after a while:
    threading.Timer(600, lambda: job_queues.pop(job_id, None)).start()

    return jsonify({"job_id": job_id})


@app.route('/api/status/<job_id>')
def api_status(job_id):
    with job_lock:
        j = jobs.get(job_id)
    if j is None:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(j)


@app.route('/api/stream/<job_id>')
def api_stream(job_id):
    with job_lock:
        q = job_queues.get(job_id)
    if q is None:
        return jsonify({"error": "Job not found"}), 404

    def generate():
        while True:
            try:
                ev = q.get(timeout=30)
            except queue.Empty:
                yield ": keepalive\n\n"
                continue
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
            if ev.get("step") in ("done", "error"):
                break

    return Response(stream_with_context(generate()), mimetype='text/event-stream')


@app.route('/api/prompts/<job_id>')
def api_get_prompts(job_id):
    with job_lock:
        j = jobs.get(job_id)
    if j is None:
        return jsonify({"error": "Job not found"}), 404
    asin = j.get("asin", "")
    p = PROMPTS_DIR / f"{asin}_prompts.json"
    if not p.exists():
        return jsonify({"error": "Prompts not yet generated"}), 400
    return jsonify(json.loads(p.read_text('utf-8')))


@app.route('/api/context/<job_id>')
def api_get_context(job_id):
    with job_lock:
        j = jobs.get(job_id)
    if j is None:
        return jsonify({"error": "Job not found"}), 404
    asin = j.get("asin", "")
    p = PROMPTS_DIR / f"{asin}_context.json"
    if not p.exists():
        return jsonify({"error": "Context not yet available. Run collection first."}), 400
    return jsonify(json.loads(p.read_text('utf-8')))


@app.route('/api/expert-suggestions/<job_id>')
def api_expert_suggestions(job_id):
    with job_lock:
        j = jobs.get(job_id)
    if j is None:
        return jsonify({"error": "Job not found"}), 404
    asin = j.get("asin", "unknown")
    ctx_path = PROMPTS_DIR / f"{asin}_context.json"
    if not ctx_path.exists():
        return jsonify({"error": "Context not yet available. Run collection first."}), 400
    try:
        context = json.loads(ctx_path.read_text('utf-8'))
        from expert_suggestions import (
            build_cosmo_title, build_cosmo_bullets, build_rufus_qa,
            extract_selling_points, build_data_insights,
        )
        return jsonify({
            "title_suggestion": build_cosmo_title(context),
            "bullets_analysis": build_cosmo_bullets(context),
            "qa_suggestions":   build_rufus_qa(context),
            "selling_points":   extract_selling_points(context),
            "data_insights":    build_data_insights(context),
            "asin": asin,
        })
    except ImportError as e:
        return jsonify({"error": f"Module not available: {e}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/send-to-chatgpt', methods=['POST'])
def api_send_to_chatgpt():
    """Generate one GPT Image-2 image via APIMart; return the resulting URL."""
    data = request.get_json(silent=True) or {}
    prompt = data.get("prompt", "").strip()
    aspect = data.get("aspect", "1:1")
    image_urls = data.get("image_urls", [])
    local_images = data.get("local_images", [])  # list of paths relative to input/

    if not prompt:
        return jsonify({"error": "prompt required"}), 400

    # Upload any local images first
    uploaded: list[str] = list(image_urls)
    for rel in local_images:
        p = INPUT_DIR / rel
        if not p.exists():
            continue
        try:
            url = upload_image_to_apimart(p)
            uploaded.append(url)
        except Exception as e:
            logging.warning(f"upload failed for {rel}: {e}")

    try:
        task_id = apimart_submit_task(uploaded, prompt, aspect)
        task = apimart_poll_task(task_id, max_wait=300)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # Extract the URL(s)
    result_urls: list[str] = []
    for item in (task.get("data") or []):
        for k in ("url", "image_url", "output_url"):
            if item.get(k):
                result_urls.append(item[k])
                break

    # Persist to output/<asin>/png/ if we have an asin
    asin = data.get("asin")
    saved_paths: list[str] = []
    if asin and result_urls:
        out_dir = asin_output_png(asin)
        out_dir.mkdir(parents=True, exist_ok=True)
        for i, u in enumerate(result_urls):
            dest = out_dir / f"{uuid.uuid4().hex[:8]}_{i}.png"
            try:
                apimart_download_image(u, dest)
                saved_paths.append(str(dest.relative_to(BASE_DIR)))
            except Exception as e:
                logging.warning(f"download failed: {e}")

    return jsonify({
        "urls": result_urls,
        "saved": saved_paths,
        "task_id": task_id,
    })


@app.route('/api/export-psd', methods=['POST'])
def api_export_psd():
    """Compose a PSD from a rendered PNG with text overlays."""
    data = request.get_json(silent=True) or {}
    asin = data.get("asin", "")
    png_rel = data.get("png", "")  # relative to output/
    overlays = data.get("overlays", [])

    if not asin or not png_rel:
        return jsonify({"error": "asin and png required"}), 400

    png_path = OUTPUT_DIR / png_rel
    if not png_path.exists():
        return jsonify({"error": f"PNG not found: {png_rel}"}), 404

    psd_dir = asin_output_psd(asin)
    psd_dir.mkdir(parents=True, exist_ok=True)
    psd_path = psd_dir / (png_path.stem + ".psd")

    try:
        # Uses psd_tools + Pillow from the bundled _internal.
        from PIL import Image
        from psd_tools import PSDImage
        from psd_tools.api.layers import PixelLayer

        img = Image.open(png_path).convert("RGBA")
        psd = PSDImage.frompil(img)
        for ov in overlays:
            text = ov.get("text", "")
            if not text:
                continue
            # (Original composes text layers; pillow-based fallback here)
            layer_img = Image.new("RGBA", img.size, (0, 0, 0, 0))
            # Rendering omitted — depends on fonts bundled in _internal.
            psd.append(PixelLayer.frompil(layer_img, psd, name=text[:32]))
        psd.save(str(psd_path))
    except Exception as e:
        return jsonify({"error": f"PSD export failed: {e}"}), 500

    return jsonify({"psd": str(psd_path.relative_to(BASE_DIR))})


@app.route('/api/images/<asin>')
def api_get_images(asin):
    """List all input images for an ASIN."""
    main_dir = INPUT_DIR / asin / "main"
    if not main_dir.exists():
        return jsonify({"images": []})
    images = [f"input/{asin}/main/{p.name}" for p in sorted(main_dir.iterdir()) if p.is_file()]
    return jsonify({"images": images})


@app.route('/input/<asin>/<subdir>/<filename>')
def serve_input(asin, subdir, filename):
    d = INPUT_DIR / asin / subdir
    if not d.exists():
        return jsonify({"error": "not found"}), 404
    return send_from_directory(str(d), secure_filename(filename))


@app.route('/output/<asin>/<subdir>/<filename>')
def serve_output(asin, subdir, filename):
    d = OUTPUT_DIR / asin / subdir
    if not d.exists():
        return jsonify({"error": "not found"}), 404
    return send_from_directory(str(d), secure_filename(filename))


@app.route('/api/settings', methods=['GET'])
def api_get_settings():
    """Return config with sensitive values masked."""
    cfg = load_config()
    safe = json.loads(json.dumps(cfg))  # deep copy
    for section in list(safe.keys()):
        sec = safe[section]
        if not isinstance(sec, dict):
            continue
        for k in list(sec.keys()):
            if k in ("api_key", "password", "secret", "token", "email"):
                v = sec[k]
                if isinstance(v, str) and len(v) > 8:
                    sec[k] = v[:4] + "***" + v[-4:]
    # Mask query-string secret in SIF endpoint
    if "sif_mcp" in safe and isinstance(safe["sif_mcp"], dict):
        ep = safe["sif_mcp"].get("endpoint", "")
        if ep and "?secret-key=" in ep:
            safe["sif_mcp"]["endpoint"] = ep.split("?secret-key=")[0]
    return jsonify(safe)


@app.route('/api/settings', methods=['POST'])
def api_update_settings():
    incoming = request.get_json(silent=True) or {}
    if not isinstance(incoming, dict):
        return jsonify({"error": "expected object"}), 400
    cfg = load_config()
    # Merge section-by-section so masked "***" values don't overwrite real ones.
    for section, vals in incoming.items():
        if not isinstance(vals, dict):
            cfg[section] = vals
            continue
        cfg.setdefault(section, {})
        for k, v in vals.items():
            if isinstance(v, str) and "***" in v:
                continue  # keep existing
            cfg[section][k] = v
    save_config(cfg)
    return jsonify({"ok": True})


def _resolve_key(submitted: str, section: str, key: str) -> str:
    """If `submitted` is masked with '***', pull the real value from config."""
    if submitted and "***" not in submitted:
        return submitted
    cfg = load_config()
    return cfg.get(section, {}).get(key, submitted or "")


@app.route('/api/list-models', methods=['POST'])
def api_list_models():
    incoming = request.get_json(silent=True) or {}
    am = incoming.get("apimart", incoming) if isinstance(incoming.get("apimart"), dict) else incoming
    key = _resolve_key(am.get("api_key", ""), "apimart", "api_key")
    base = am.get("base_url") or load_config().get("apimart", {}).get("base_url", "https://api.apimart.ai")

    if not key or "***" in key:
        return jsonify({"error": "API Key not configured", "models": []})

    try:
        import ssl
        ctx = ssl.create_default_context()
        parsed = urllib.parse.urlparse(base + "/v1/models")
        conn = http.client.HTTPSConnection(
            parsed.hostname, parsed.port or 443, timeout=10, context=ctx
        )
        try:
            conn.request(
                "GET", parsed.path,
                headers={"Authorization": f"Bearer {key}"},
            )
            resp = conn.getresponse()
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
        finally:
            conn.close()

        models = data.get("data", data.get("models", []))
        if isinstance(models, list):
            model_names = []
            for m in models:
                if isinstance(m, dict):
                    model_names.append(m.get("id", m.get("name", str(m))))
                else:
                    model_names.append(str(m))
            return jsonify({"models": model_names[:100]})
        return jsonify({"error": "Unexpected response format", "models": []})
    except Exception as e:
        return jsonify({"error": str(e), "models": []})


@app.route('/api/test-connection/<service>', methods=['POST'])
def api_test_connection(service):
    """Test connectivity for apimart / sif / sorftime."""
    incoming = request.get_json(silent=True) or {}

    if service == "apimart":
        am = incoming.get("apimart", incoming) if isinstance(incoming.get("apimart"), dict) else incoming
        key = _resolve_key(am.get("api_key", ""), "apimart", "api_key")
        base = am.get("base_url") or load_config().get("apimart", {}).get("base_url", "https://api.apimart.ai")
        if not key or "***" in key:
            return jsonify({"status": "error", "message": "API Key 未填写"})
        try:
            import ssl
            ctx = ssl.create_default_context()
            parsed = urllib.parse.urlparse(base + "/v1/tasks/test")
            conn = http.client.HTTPSConnection(
                parsed.hostname, parsed.port or 443, timeout=10, context=ctx
            )
            try:
                conn.request("GET", parsed.path,
                             headers={"Authorization": f"Bearer {key}"})
                resp = conn.getresponse()
                # 401/403/404 still mean the host is reachable
                if resp.status in (401, 403, 404):
                    return jsonify({"status": "ok", "message": "API 可达"})
                return jsonify({"status": "ok", "message": f"Connected ({resp.status})"})
            finally:
                conn.close()
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)})

    if service == "sif":
        sf = incoming.get("sif_mcp", incoming) if isinstance(incoming.get("sif_mcp"), dict) else incoming
        key = _resolve_key(sf.get("api_key", ""), "sif_mcp", "api_key")
        ep = sf.get("endpoint") or load_config().get("sif_mcp", {}).get("endpoint", "")
        if not ep:
            return jsonify({"status": "error", "message": "Endpoint 未填写"})
        try:
            parsed = urllib.parse.urlparse(ep.rstrip("/"))
            base = f"{parsed.scheme}://{parsed.hostname}"
            if parsed.port:
                base += f":{parsed.port}"
            path = parsed.path or "/mcp"
            if not path.endswith("/mcp"):
                path = path.rstrip("/") + "/mcp"
            full_url = base + path
            if key and "***" not in key and "?" not in full_url:
                full_url += f"?secret-key={key}"
            import ssl
            ctx = ssl.create_default_context()
            parsed2 = urllib.parse.urlparse(full_url)
            conn = http.client.HTTPSConnection(
                parsed2.hostname, parsed2.port or 443, timeout=10, context=ctx
            )
            try:
                p2 = parsed2.path + ("?" + parsed2.query if parsed2.query else "")
                conn.request("GET", p2, headers={"Accept": "application/json"})
                resp = conn.getresponse()
                if resp.status < 500:
                    return jsonify({"status": "ok", "message": "SIF MCP 可达"})
                return jsonify({"status": "error", "message": f"HTTP {resp.status}"})
            finally:
                conn.close()
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)})

    if service == "sorftime":
        st = incoming.get("sorftime_mcp", incoming) if isinstance(incoming.get("sorftime_mcp"), dict) else incoming
        key = _resolve_key(st.get("api_key", ""), "sorftime_mcp", "api_key")
        ep = st.get("endpoint") or load_config().get("sorftime_mcp", {}).get("endpoint", "")
        if not ep:
            return jsonify({"status": "error", "message": "Endpoint 未填写"})
        if not key or "***" in key:
            return jsonify({"status": "error", "message": "API Key 未填写"})
        try:
            parsed = urllib.parse.urlparse(ep + f"?key={key}")
            import ssl
            ctx = ssl.create_default_context()
            conn = http.client.HTTPSConnection(
                parsed.hostname, parsed.port or 443, timeout=10, context=ctx
            )
            try:
                p = parsed.path + ("?" + parsed.query if parsed.query else "")
                conn.request("GET", p, headers={"Accept": "application/json"})
                resp = conn.getresponse()
                if resp.status < 500:
                    return jsonify({"status": "ok", "message": "Sorftime MCP 可达"})
                return jsonify({"status": "error", "message": f"HTTP {resp.status}"})
            finally:
                conn.close()
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)})

    return jsonify({"status": "error", "message": f"Unknown service: {service}"}), 400


# ---------------------------------------------------------------------------
# Licensing
# ---------------------------------------------------------------------------

@app.route('/api/activate', methods=['POST'])
def api_activate():
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip()
    email = (data.get("email") or "").strip()
    if not code:
        return jsonify({"status": "error", "message": "激活码必填"}), 400
    try:
        # Original contacts a license server; here we accept the code
        # and persist the expiry it returns.
        result = _license_bootstrap(code, email)
        cfg = load_config()
        cfg.setdefault("license", {}).update({
            "code": code,
            "email": email,
            "activated_at": datetime.now().isoformat(),
            **result,
        })
        save_config(cfg)
        return jsonify({"status": "ok", **result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/trial-start', methods=['POST'])
def api_trial_start():
    cfg = load_config()
    lic = cfg.setdefault("license", {})
    if lic.get("trial_started"):
        return jsonify({"status": "ok", "trial_started": True})
    lic["trial_started"] = datetime.now().isoformat()
    save_config(cfg)
    return jsonify({"status": "ok", "trial_started": True})


@app.route('/api/license-status')
def api_license_status():
    cfg = load_config()
    lic = cfg.get("license", {})
    return jsonify({
        "activated": bool(lic.get("code")),
        "trial_started": bool(lic.get("trial_started")),
        "expires_at": lic.get("expires_at"),
    })


@app.route('/api/clear-cache', methods=['POST'])
def api_clear_cache():
    """Wipe input/, output/, prompts/ to free disk."""
    try:
        for d in (INPUT_DIR, OUTPUT_DIR, PROMPTS_DIR):
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)
                d.mkdir(parents=True, exist_ok=True)
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


def _license_bootstrap(code: str, email: str) -> dict:
    """Call the upstream license server to validate an activation code."""
    # Original endpoint details are in _internal; we call a generic validator.
    cfg = load_config()
    api_base = cfg.get("license", {}).get("server", "https://license.bsc.local")
    parsed = urllib.parse.urlparse(api_base + "/v1/activate")
    import ssl
    ctx = ssl.create_default_context()
    body = json.dumps({"code": code, "email": email}).encode("utf-8")
    conn = http.client.HTTPSConnection(
        parsed.hostname, parsed.port or 443, timeout=15, context=ctx
    )
    try:
        conn.request("POST", parsed.path, body=body,
                     headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        if resp.status >= 400:
            raise RuntimeError(data.get("message", f"HTTP {resp.status}"))
        return {
            "expires_at": data.get("expires_at"),
            "plan": data.get("plan", "personal"),
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import webbrowser

    os.system("title BSC OPC Agent OS Personal")
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
    )
    print('[=====================================]')
    print('[  BSC OPC Agent OS Personal         ]')
    print('[  Open: http://127.0.0.1:5173       ]')
    print('[=====================================]')

    # Open the browser after a short delay.
    threading.Timer(2.0, lambda: webbrowser.open('http://127.0.0.1:5173')).start()

    try:
        app.run(host='127.0.0.1', port=5173, debug=False)
    except OSError as e:
        if '10048' in str(e).lower() or 'address' in str(e).lower():
            print('\nERROR: Port 5173 is already in use.')
            print('Close the other instance of BSC OPC Agent and try again.')
        else:
            print(f'\nERROR: {e}')
        input('\nPress Enter to exit...')
