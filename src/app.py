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
SQP_DIR = BASE_DIR / "output" / "sqp"
PROMPTS_DIR = BASE_DIR / "prompts"
LOGS_DIR = BASE_DIR / "logs"
WIKI_DIR = BASE_DIR / "Wiki"

for d in (INPUT_DIR, OUTPUT_DIR, PROMPTS_DIR, LOGS_DIR, SQP_DIR):
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

        # Honesty flag: tell the UI whether the copy it's about to show is
        # grounded in real MCP data or is just template fallback.
        expert_data["is_template_fallback"] = not context.get("_has_real_data", False)
        expert_data["data_quality"] = context.get("_data_quality", {})

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
    """Gather product context by calling the real SIF + Sorftime MCP tools.

    Each section is best-effort: a failure in one source (e.g. Sorftime quota
    exhausted) does not break the others. The set of successful / failed
    sources is recorded in `_data_quality` so the expert-suggestion layer and
    the UI can honestly flag "this output is template fallback, not real data".
    """
    import re as _re
    from datetime import datetime as _dt, timedelta as _td

    context: dict = {
        "asin": asin,
        "marketplace": marketplace,
        "_data_quality": {
            "sif_ok": [],
            "sif_fail": [],
            "sorftime_ok": [],
            "sorftime_fail": [],
        },
    }
    dq = context["_data_quality"]

    # ------------------------------------------------------------------
    # SIF — listing traffic overview (title / brand / category / bullets)
    # ------------------------------------------------------------------
    try:
        overview = _call_sif_tool(
            "ops_get_listing_traffic_overview",
            {"asin": asin, "marketplace": marketplace},
        )
        if overview and isinstance(overview, dict):
            _apply_sif_overview(context, overview)
            dq["sif_ok"].append("listing_traffic_overview")
        else:
            dq["sif_fail"].append("listing_traffic_overview (empty)")
    except Exception as e:
        dq["sif_fail"].append(f"listing_traffic_overview ({e})")

    # ------------------------------------------------------------------
    # SIF — ASIN sales / ranking list
    # ------------------------------------------------------------------
    try:
        sales = _call_sif_tool(
            "ops_get_asin_sales_list",
            {"asins": [asin], "marketplace": marketplace},
        )
        if sales and isinstance(sales, dict):
            _apply_sif_sales(context, sales)
            dq["sif_ok"].append("asin_sales_list")
        else:
            dq["sif_fail"].append("asin_sales_list (empty)")
    except Exception as e:
        dq["sif_fail"].append(f"asin_sales_list ({e})")

    # ------------------------------------------------------------------
    # SIF — keyword traffic signals.
    #
    # Schema says only `asin` is required but the server has a null-safety
    # bug in its time-range handler: omitting time_type/time_value throws
    # `Cannot invoke "String.length()" because "s" is null`. So we always
    # pass the full set. Note: the field is `country`, NOT `marketplace`,
    # and `time_value` is a string, not a number.
    # ------------------------------------------------------------------
    try:
        kw = _call_sif_tool(
            "market_get_asin_keyword_signals",
            {
                "asin": asin,
                "country": marketplace,
                "time_type": "lately",
                "time_value": "7",
                "topN": 30,
            },
        )
        if kw and isinstance(kw, (dict, list)):
            _apply_sif_keywords(context, kw)
            dq["sif_ok"].append("asin_keyword_signals")
        else:
            dq["sif_fail"].append("asin_keyword_signals (empty)")
    except Exception as e:
        dq["sif_fail"].append(f"asin_keyword_signals ({e})")

    # ------------------------------------------------------------------
    # Sorftime — product detail
    # Sorftime 使用 `amzSite`（不是 `marketplace`）区分站点。
    # ------------------------------------------------------------------
    try:
        detail = _call_sorftime_tool(
            "product_detail",
            {"asin": asin, "amzSite": marketplace},
        )
        if detail and isinstance(detail, (dict, str)):
            _apply_sorftime_detail(context, detail)
            dq["sorftime_ok"].append("product_detail")
        else:
            dq["sorftime_fail"].append("product_detail (empty)")
    except Exception as e:
        dq["sorftime_fail"].append(f"product_detail ({e})")

    # ------------------------------------------------------------------
    # Sorftime — traffic terms / keywords
    # ------------------------------------------------------------------
    try:
        traffic = _call_sorftime_tool(
            "product_traffic_terms",
            {"asin": asin, "amzSite": marketplace},
        )
        if traffic and isinstance(traffic, (dict, list, str)):
            _apply_sorftime_traffic(context, traffic)
            dq["sorftime_ok"].append("product_traffic_terms")
        else:
            dq["sorftime_fail"].append("product_traffic_terms (empty)")
    except Exception as e:
        dq["sorftime_fail"].append(f"product_traffic_terms ({e})")

    # ------------------------------------------------------------------
    # Finalise
    # ------------------------------------------------------------------
    # Trim long lists
    if isinstance(context.get("reviews"), list):
        context["reviews"] = context["reviews"][:20]
    if isinstance(context.get("keywords"), list):
        context["keywords"] = context["keywords"][:30]

    # Flag: did we get any real data at all?
    has_real_title = bool((context.get("title") or "").strip())
    has_real_bullets = bool(context.get("bullets"))
    has_real_keywords = bool(context.get("keywords"))
    context["_has_real_data"] = has_real_title or has_real_bullets or has_real_keywords
    context["bullets_synthetic"] = not has_real_bullets

    if not context["_has_real_data"]:
        logging.warning(
            f"build_context: no real MCP data for {asin}. "
            f"SIF fails: {dq['sif_fail']}. Sorftime fails: {dq['sorftime_fail']}."
        )

    return context


# --- MCP result adapters --------------------------------------------------
#
# Each adapter takes the raw JSON payload returned by a specific MCP tool
# and writes the relevant fields into `context` using the keys that
# expert_suggestions.py expects (title/brand/category/bullets/keywords/...).
# Keys that aren't present in the response are left alone so a later call
# can fill them in.

def _first_nonempty(d: dict, *keys):
    for k in keys:
        v = d.get(k)
        if v:
            return v
    return None


def _apply_sif_overview(ctx: dict, data: dict) -> None:
    """Map a SIF listing_traffic_overview payload into context.

    实测返回结构：
        {"overview":{"ad":{"name":"广告流量","ratio":0.049,"score":411.6},
                     "nf":{"name":"自然流量","ratio":0.950,"score":7961.4}},
         "ad":{"sbv":{...}}, "recommend":{...}, "total":8373.1}
    本接口不包含 title / brand / bullets —— 这些来自 Sorftime。
    """
    d = data.get("data") if isinstance(data.get("data"), dict) else data
    if not isinstance(d, dict):
        return

    overview = d.get("overview") or {}
    breakdown: dict = {}
    if isinstance(overview, dict):
        nf = overview.get("nf") or {}
        ad = overview.get("ad") or {}
        if isinstance(nf, dict) and nf.get("ratio") is not None:
            breakdown["natural_ratio"] = nf.get("ratio")
            breakdown["natural_score"] = nf.get("score")
        if isinstance(ad, dict) and ad.get("ratio") is not None:
            breakdown["ad_ratio"] = ad.get("ratio")
            breakdown["ad_score"] = ad.get("score")
    total = d.get("total")
    if total is not None:
        breakdown["total_score"] = total
    ad_detail = d.get("ad") or {}
    if isinstance(ad_detail, dict) and ad_detail:
        breakdown["ad_types"] = {
            k: (v.get("ratio") if isinstance(v, dict) else None)
            for k, v in ad_detail.items()
        }
    if breakdown:
        ctx["traffic_breakdown"] = breakdown


def _apply_sif_sales(ctx: dict, data: dict) -> None:
    """Pull title / price / rating / monthly sales from SIF ops_get_asin_sales_list.

    实测返回结构：
        {"total":1,"asins":[{"asin":"B0...","title":"...","img":"...",
          "price":18.59,"score":4.1,"ratingNum":170,"boughtInPastMonth":"300+",
          "boughtHistoryDates":[...],"boughtHistory":[...]}], ...}
    """
    d = data if isinstance(data, dict) else {}
    asins = d.get("asins")
    if not isinstance(asins, list) or not asins:
        return
    first = asins[0] if isinstance(asins[0], dict) else {}

    if not ctx.get("title") and first.get("title"):
        ctx["title"] = str(first["title"]).strip()
    if not ctx.get("price") and first.get("price") is not None:
        ctx["price"] = str(first["price"])
    if not ctx.get("rating") and first.get("score") is not None:
        ctx["rating"] = str(first["score"])
    if not ctx.get("review_count") and first.get("ratingNum") is not None:
        ctx["review_count"] = str(first["ratingNum"])

    # Monthly sales / bought-in-past-month
    bpm = first.get("boughtInPastMonth")
    if bpm and not ctx.get("monthly_sales"):
        ctx["monthly_sales"] = str(bpm)

    # Trend: last 12 months of bought history
    hist = first.get("boughtHistory") or []
    dates = first.get("boughtHistoryDates") or []
    if hist and dates and not ctx.get("sales_trend"):
        ctx["sales_trend"] = [
            {"month": m, "units": n} for m, n in zip(dates, hist)
        ]

    # Image fallback (Sorftime 主图如缺失时使用)
    if first.get("img") and not ctx.get("image_urls"):
        ctx["image_urls"] = [first["img"]]


def _apply_sif_keywords(ctx: dict, data) -> None:
    """Normalise SIF market_get_asin_keyword_signals output.

    实测返回结构：
        {"query_context":{...}, "summary":{...},
         "primary_signals":{"declining":[{keyword,traffic_share,...}],
                            "gaining":[...], "rank_gaps":[...]},
         "secondary_signals":{...},
         "top_keywords":[...]}  # 如果 topN 请求了，会在这里
    """
    d = data if isinstance(data, dict) else {}

    out: list[dict] = []
    seen: set = set()

    def _add(item, bucket: str):
        if not isinstance(item, dict):
            return
        kw = item.get("keyword") or item.get("query") or item.get("term")
        if not kw or kw in seen:
            return
        seen.add(kw)
        entry = {
            "keyword": str(kw),
            "source": "sif",
            "signal": bucket,
        }
        if item.get("traffic_share") is not None:
            entry["traffic_share"] = item["traffic_share"]
        if item.get("contri_change") is not None:
            entry["contri_change"] = item["contri_change"]
        if item.get("contri_severity"):
            entry["severity"] = item["contri_severity"]
        if item.get("organic_rank"):
            entry["organic_rank"] = item["organic_rank"]
        if item.get("volume") is not None or item.get("search_volume") is not None:
            entry["volume"] = item.get("volume") or item.get("search_volume")
        out.append(entry)

    primary = d.get("primary_signals") or {}
    if isinstance(primary, dict):
        for bucket in ("declining", "gaining", "rank_gaps"):
            for item in primary.get(bucket) or []:
                _add(item, bucket)

    secondary = d.get("secondary_signals") or {}
    if isinstance(secondary, dict):
        for bucket, items in secondary.items():
            if isinstance(items, list):
                for item in items:
                    _add(item, f"secondary_{bucket}")

    for item in d.get("top_keywords") or []:
        if isinstance(item, dict):
            _add(item, "top")
        elif isinstance(item, str):
            if item not in seen:
                seen.add(item)
                out.append({"keyword": item, "source": "sif", "signal": "top"})

    if out:
        existing = ctx.get("keywords") or []
        ctx["keywords"] = existing + out
        ctx["sif_keywords"] = out

    # Keep raw signals for data_insights
    if primary or secondary:
        ctx["keyword_signals"] = {
            "primary": primary,
            "secondary": secondary,
            "summary": d.get("summary"),
        }


def _apply_sorftime_detail(ctx: dict, data) -> None:
    """Sorftime product_detail 返回的是中文标签文本（不是结构化 dict）。

    真实返回示例：
        "产品ASIN码：B0F7QJC249\n标题：CTIME 80\"...\n主图：https://...\n
         价格：18.59\n优惠券：2.79\n星级：4.10\n评论数：170\n品牌：CTIME\n
         所属nodeid：2245500011\n卖家名称：CTIMEDY\n卖家来源：CN\n
         分类：SQUEEGEE\n属性：{\"Brand\":\"CTIME\",...}；\n
         上架时间：2025-05-15\n已上架天数：359\n子体数：1\nFBA费用：6.23\n
         所属大类：Health & Household（排名:47213）\n所属细分类目：Squeegees（排名:93）\n
         月销量：月销量：340\n月销额：月销额：6320.60\n
         产品描述：【3-in-1 ...】This multi-functional ...<br>[Adjustable ...]..."
    """
    text = data if isinstance(data, str) else ""
    if isinstance(data, dict):
        # fallback: 若服务端某天返回结构化 dict，这里也兼容
        for field, keys in [
            ("title", ("title", "product_title")),
            ("brand", ("brand", "brand_name")),
            ("price", ("price", "sale_price")),
            ("rating", ("rating", "star_rating")),
            ("review_count", ("review_count", "reviews")),
            ("category", ("category", "category_path")),
        ]:
            if not ctx.get(field):
                v = _first_nonempty(data, *keys)
                if v:
                    ctx[field] = str(v)
        if not text:
            return

    if not text:
        return

    def _grab(label: str) -> str:
        """匹配 `label：value`（中英文冒号都支持），直到下一行或换行。"""
        import re as _re
        m = _re.search(rf"{_re.escape(label)}\s*[：:]\s*(.+?)(?=\n|$)", text)
        return m.group(1).strip() if m else ""

    title = _grab("标题")
    if title and not ctx.get("title"):
        ctx["title"] = title
    brand = _grab("品牌")
    if brand and not ctx.get("brand"):
        ctx["brand"] = brand
    category = _grab("所属细分类目") or _grab("分类")
    if category and not ctx.get("category"):
        ctx["category"] = category
    price = _grab("价格")
    if price and not ctx.get("price"):
        ctx["price"] = price
    rating = _grab("星级")
    if rating and not ctx.get("rating"):
        ctx["rating"] = rating
    review_count = _grab("评论数")
    if review_count and not ctx.get("review_count"):
        ctx["review_count"] = review_count
    main_img = _grab("主图")
    if main_img and not ctx.get("image_urls"):
        ctx["image_urls"] = [main_img]
    seller = _grab("卖家名称")
    if seller:
        ctx["seller"] = seller
    bsr = _grab("所属细分类目")  # 含「排名」
    if bsr:
        ctx["bsr"] = bsr
    fba = _grab("FBA费用")
    if fba:
        ctx["fba_fee"] = fba
    launch = _grab("上架时间")
    if launch:
        ctx["launch_date"] = launch

    # 月销量字段值本身可能含冒号（原文：「月销量：月销量：340」）—— 取最后一段
    for lbl in ("月销量", "月销额"):
        raw = _grab(lbl)
        if raw:
            # 清掉重复前缀
            val = raw.split("：")[-1].split(":")[-1].strip()
            ctx_key = "monthly_sales" if lbl == "月销量" else "monthly_revenue"
            if not ctx.get(ctx_key):
                ctx[ctx_key] = val

    # 产品描述 -> bullets
    import re as _re
    desc = _grab("产品描述")
    if not desc:
        m = _re.search(r"产品描述\s*[：:]\s*(.+)$", text, flags=_re.DOTALL)
        if m:
            desc = m.group(1).strip()
    if desc and not ctx.get("bullets"):
        # 亚马逊 bullet 在原文里用 [xxx] 或【xxx】标题开头，<br> 作为分隔
        parts = [p.strip() for p in _re.split(r"<br\s*/?>\s*", desc) if p.strip()]
        # 只保留长度足够的正文段
        bullets = [p for p in parts if len(p) > 40]
        if bullets:
            ctx["bullets"] = bullets[:10]

    # 属性 dict
    attrs_raw = _grab("属性")
    if attrs_raw:
        try:
            attrs_raw = attrs_raw.rstrip("；;").strip()
            ctx["attributes"] = json.loads(attrs_raw)
        except Exception:
            ctx["attributes_raw"] = attrs_raw


def _apply_sorftime_traffic(ctx: dict, data) -> None:
    """Sorftime product_traffic_terms -> append to ctx.keywords.

    真实返回样例（字符串，前面带一段中文引导语，后面跟 JSON 数组，中文 key）：
        "直接罗列数据，然后依据这些数据进行总结，...\n
         [{\"关键词\":\"window cleaner\",\"月搜索量\":161842,\"推荐竞价\":\"2.20\",...}]"
    """
    items = None
    if isinstance(data, str):
        # 抽取第一个 JSON 数组
        import re as _re
        m = _re.search(r"\[\s*\{.*\}\s*\]", data, flags=_re.DOTALL)
        if m:
            try:
                items = json.loads(m.group(0))
            except Exception:
                items = None
    elif isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("data") or data.get("terms") or data.get("items") or []

    if not isinstance(items, list):
        return

    out: list[dict] = []
    seen = {(k.get("keyword") if isinstance(k, dict) else None)
            for k in (ctx.get("keywords") or [])}
    for item in items:
        if not isinstance(item, dict):
            continue
        kw = item.get("关键词") or item.get("keyword") or item.get("term") or item.get("query")
        if not kw or kw in seen:
            continue
        seen.add(kw)
        entry = {
            "keyword": str(kw),
            "source": "sorftime",
        }
        volume = item.get("月搜索量") or item.get("volume") or item.get("search_volume")
        if volume is not None:
            entry["volume"] = volume
        bid = item.get("推荐竞价") or item.get("cpc") or item.get("suggested_bid")
        if bid:
            entry["suggested_bid"] = bid
        bid_range = item.get("推荐竞价范围")
        if bid_range:
            entry["bid_range"] = bid_range
        position = item.get("最近自然曝光位置") or item.get("organic_position")
        if position:
            entry["organic_position"] = position
        out.append(entry)

    if out:
        existing = ctx.get("keywords") or []
        ctx["keywords"] = existing + out
        ctx["sorftime_keywords"] = out


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
#
# The original app shipped a skeleton client that skipped the MCP handshake
# and used placeholder tool names (`product_info`, `keyword_insights`). Both
# SIF and Sorftime implement the full MCP Streamable-HTTP spec and reject
# such requests — so every call silently returned -32601 and the downstream
# context stayed empty. This rewrite:
#
#   1. Always does initialize -> notifications/initialized -> tools/call
#      (the three-message handshake the spec mandates).
#   2. Sends `Accept: application/json, text/event-stream` so servers that
#      only speak SSE don't 415/406 us.
#   3. Reuses `mcp-session-id` across calls per endpoint (keyed on (host,
#      query-auth) so key rotations reset the session).
#   4. Parses BOTH plain JSON and SSE-framed `data: {...}` response bodies.
#   5. Extracts structured content from the MCP `tools/call` result envelope
#      (result.content[].text usually contains a JSON blob or plain text).
#
# None of this is Amazon-specific — it's just a correct MCP 2025-03-26
# client implementation.

import ssl as _ssl

# Cache: endpoint-key -> {"session_id": str, "initialized": bool}
_mcp_sessions: dict[str, dict] = {}
_mcp_sessions_lock = threading.Lock()


def _mcp_build_url(endpoint: str, api_key: str) -> str:
    """Return the HTTP URL to POST to.

    Sorftime-style servers carry the auth key in the URL query string
    (`?key=...` — the NEW param name; `?secret-key=` is the old one and
    makes the server silently refuse requests). In that case we leave the
    endpoint untouched.

    SIF-style servers authenticate via `Authorization: Bearer <token>`
    header, so the URL stays clean.
    """
    if not endpoint:
        return ""
    return endpoint


def _is_sorftime_style(endpoint: str) -> bool:
    """Sorftime puts the auth key directly in the URL (`?key=...`).
    We key off the URL pattern rather than hostname so custom deploys work."""
    if not endpoint:
        return False
    low = endpoint.lower()
    return "?key=" in low or "&key=" in low or "sorftime" in low


def _mcp_open_conn(parsed, timeout: int) -> http.client.HTTPConnection:
    if parsed.scheme == "https":
        return http.client.HTTPSConnection(
            parsed.hostname, parsed.port or 443,
            timeout=timeout, context=_ssl.create_default_context(),
        )
    return http.client.HTTPConnection(
        parsed.hostname, parsed.port or 80, timeout=timeout,
    )


def _mcp_parse_body(raw: str) -> dict:
    """Accept either a plain JSON-RPC response or an SSE `data: {...}` stream."""
    if not raw:
        return {}
    raw = raw.strip()

    # SSE frame — grab the last `data:` line (servers may emit keepalive
    # `: ping` comments before the actual payload).
    if raw.startswith("data:") or "\ndata:" in raw:
        last_data = None
        for line in raw.splitlines():
            if line.startswith("data:"):
                last_data = line[5:].strip()
        if last_data:
            raw = last_data

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw}


def _mcp_post(endpoint: str, api_key: str, payload: dict,
              session_id: str | None, timeout: int) -> tuple[dict, dict]:
    """POST one JSON-RPC message to an MCP endpoint.

    Returns (parsed_response_body, response_headers_lowercase).

    Auth strategy:
      - Sorftime-style (key in URL): no Authorization header needed.
      - SIF-style: send `Authorization: Bearer <api_key>`.
    """
    url = _mcp_build_url(endpoint, api_key)
    parsed = urllib.parse.urlparse(url)
    # Path 必须以 `/` 开头，否则 nginx 会返回 400。
    # 对 `https://mcp.sorftime.com?key=...` 这种 URL，urlparse 出来的
    # path 是空字符串，拼出的 "?key=..." 是非法请求行。
    raw_path = parsed.path or "/"
    path = raw_path + (f"?{parsed.query}" if parsed.query else "")

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        headers["mcp-session-id"] = session_id
    if api_key and not _is_sorftime_style(endpoint):
        headers["Authorization"] = f"Bearer {api_key}"

    conn = _mcp_open_conn(parsed, timeout)
    try:
        conn.request("POST", path, body=json.dumps(payload).encode("utf-8"),
                     headers=headers)
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8", errors="replace")
        resp_headers = {k.lower(): v for k, v in resp.getheaders()}
        if resp.status >= 400:
            raise RuntimeError(
                f"HTTP {resp.status}: {raw[:300]}"
            )
        return _mcp_parse_body(raw), resp_headers
    finally:
        conn.close()


def _mcp_handshake(endpoint: str, api_key: str, timeout: int) -> str | None:
    """Run initialize + notifications/initialized. Returns the session id.

    Result is cached per (endpoint, api_key) so we only pay the handshake
    cost once per process.

    IMPORTANT: Sorftime-style servers (key-in-URL) reject `initialize`
    with HTTP 400 ("not implemented") — tools/call works directly. We
    detect that family by URL shape and skip the handshake.
    """
    # Sorftime: no handshake, no session id.
    if _is_sorftime_style(endpoint):
        return None

    cache_key = f"{endpoint}|{api_key[-8:] if api_key else ''}"
    with _mcp_sessions_lock:
        cached = _mcp_sessions.get(cache_key)
        if cached and cached.get("initialized"):
            return cached.get("session_id")

    # Advertise the latest spec version we support. If the server talks an
    # older or newer one, MCP's handshake rules say it echoes whatever it
    # actually implements in result.protocolVersion — we just log that and
    # move on; tools/call works regardless.
    init_payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {
                "name": "BSC-OPC-Agent",
                "version": "1.0.0",
            },
        },
    }
    body, headers = _mcp_post(endpoint, api_key, init_payload, None, timeout)
    if body.get("error"):
        raise RuntimeError(f"initialize failed: {body['error']}")
    session_id = headers.get("mcp-session-id")
    server_version = (body.get("result") or {}).get("protocolVersion")
    if server_version:
        logging.debug(f"MCP server negotiated protocolVersion={server_version}")

    # Second step: notifications/initialized (fire-and-forget, no response body)
    notif = {"jsonrpc": "2.0",
             "method": "notifications/initialized",
             "params": {}}
    try:
        _mcp_post(endpoint, api_key, notif, session_id, timeout)
    except Exception as e:
        # Some servers return 202 with empty body; treat any non-5xx as OK.
        logging.debug(f"notifications/initialized returned: {e}")

    with _mcp_sessions_lock:
        _mcp_sessions[cache_key] = {
            "session_id": session_id,
            "initialized": True,
        }
    return session_id


def _mcp_extract_content(result: dict):
    """Pull the real payload out of an MCP tools/call result envelope.

    MCP returns:
        {"content": [{"type": "text", "text": "<json or plain>"}], ...}
    We try to parse each text item as JSON; if everything is plain text,
    we concatenate and return the string.
    """
    if not isinstance(result, dict):
        return result
    content = result.get("content")
    if not isinstance(content, list):
        return result

    parsed_items: list = []
    text_chunks: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        txt = item.get("text", "")
        if not txt:
            continue
        text_chunks.append(txt)
        try:
            parsed_items.append(json.loads(txt))
        except json.JSONDecodeError:
            pass

    if len(parsed_items) == 1:
        return parsed_items[0]
    if parsed_items:
        return parsed_items
    return "\n".join(text_chunks) if text_chunks else result


def _mcp_call_tool(endpoint: str, api_key: str, tool: str,
                   arguments: dict, timeout: int = 60) -> dict:
    """Full MCP tools/call with handshake + session reuse."""
    if not endpoint:
        raise RuntimeError("endpoint not configured")

    session_id = _mcp_handshake(endpoint, api_key, timeout)

    call_payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "tools/call",
        "params": {"name": tool, "arguments": arguments},
    }
    body, _ = _mcp_post(endpoint, api_key, call_payload, session_id, timeout)

    if body.get("error"):
        err = body["error"]
        # On -32001 / "invalid session", drop cache and retry once
        cache_key = f"{endpoint}|{api_key[-8:] if api_key else ''}"
        code = err.get("code") if isinstance(err, dict) else None
        if code in (-32001, -32002):
            with _mcp_sessions_lock:
                _mcp_sessions.pop(cache_key, None)
            session_id = _mcp_handshake(endpoint, api_key, timeout)
            body, _ = _mcp_post(endpoint, api_key, call_payload, session_id, timeout)
            if body.get("error"):
                raise RuntimeError(f"{tool}: {body['error']}")
        else:
            raise RuntimeError(f"{tool}: {err}")

    result = body.get("result", {})
    if isinstance(result, dict) and result.get("isError"):
        # Server-side tool error (quota exhausted, bad args, etc.)
        content = _mcp_extract_content(result)
        raise RuntimeError(f"{tool} returned isError: {content}")

    return _mcp_extract_content(result)


def _call_sif_tool(tool: str, arguments: dict) -> dict | None:
    """Call a SIF MCP tool. Returns None on failure (logged)."""
    cfg = load_config()
    sif = cfg.get("sif_mcp", {})
    endpoint = sif.get("endpoint", "")
    api_key = sif.get("api_key", "")
    if not endpoint or not api_key:
        return None
    try:
        return _mcp_call_tool(endpoint, api_key, tool, arguments, timeout=60)
    except Exception as e:
        logging.warning(f"SIF tool '{tool}' failed: {e}")
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
        # Surface the last error via a module-global so caller/debugger can inspect.
        import traceback as _tb
        _LAST_SORFTIME_ERR["err"] = f"{type(e).__name__}: {e}"
        _LAST_SORFTIME_ERR["trace"] = _tb.format_exc()
        logging.warning(f"Sorftime tool '{tool}' failed: {e}")
        return None


_LAST_SORFTIME_ERR: dict = {"err": None, "trace": None}


@app.route('/_debug/last-sorftime-error')
def _debug_last_sorftime_err():
    return jsonify(_LAST_SORFTIME_ERR)


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
            "is_template_fallback": not context.get("_has_real_data", False),
            "data_quality": context.get("_data_quality", {}),
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
    """Test connectivity for apimart / sif / sorftime.

    每个服务都发一次**真实业务调用**，而不是仅测 TCP 可达，否则随便填
    API Key 都会通过（原实现只判断 HTTP status < 500）。
    """
    incoming = request.get_json(silent=True) or {}

    # ------------------------------------------------------------------
    # APIMart：通过 /v1/models 或类似鉴权接口验证 key
    # ------------------------------------------------------------------
    if service == "apimart":
        am = incoming.get("apimart", incoming) if isinstance(incoming.get("apimart"), dict) else incoming
        key = _resolve_key(am.get("api_key", ""), "apimart", "api_key")
        base = am.get("base_url") or load_config().get("apimart", {}).get("base_url", "https://api.apimart.ai")
        if not key or "***" in key:
            return jsonify({"status": "error", "message": "API Key 未填写"})
        try:
            import ssl
            ctx = ssl.create_default_context()
            parsed = urllib.parse.urlparse(base.rstrip("/") + "/v1/models")
            conn = http.client.HTTPSConnection(
                parsed.hostname, parsed.port or 443, timeout=10, context=ctx
            )
            try:
                conn.request("GET", parsed.path or "/v1/models",
                             headers={"Authorization": f"Bearer {key}"})
                resp = conn.getresponse()
                raw = resp.read().decode("utf-8", errors="replace")
                if resp.status == 200:
                    return jsonify({"status": "ok", "message": "APIMart 鉴权通过"})
                if resp.status in (401, 403):
                    return jsonify({"status": "error",
                                    "message": f"API Key 无效（HTTP {resp.status}）"})
                if resp.status == 404:
                    # /v1/models 可能不存在；退回到提交一个假任务探测鉴权
                    return _apimart_fallback_auth_check(base, key)
                return jsonify({"status": "error",
                                "message": f"HTTP {resp.status}: {raw[:200]}"})
            finally:
                conn.close()
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)})

    # ------------------------------------------------------------------
    # SIF：真调一次 tools/list（含 initialize 握手 + Bearer 鉴权）
    # ------------------------------------------------------------------
    if service == "sif":
        sf = incoming.get("sif_mcp", incoming) if isinstance(incoming.get("sif_mcp"), dict) else incoming
        submitted = sf.get("api_key", "")
        key = _resolve_key(submitted, "sif_mcp", "api_key")
        ep = sf.get("endpoint") or load_config().get("sif_mcp", {}).get("endpoint", "")
        used_saved_key = (not submitted) or ("***" in submitted)
        if not ep:
            return jsonify({"status": "error", "message": "Endpoint 未填写"})
        if not key:
            return jsonify({"status": "error", "message": "API Key 未填写"})
        try:
            # 强制走新 MCP 握手；握手成功才算 key 有效
            sid = _mcp_handshake(ep, key, timeout=10)
            body, _ = _mcp_post(ep, key,
                {"jsonrpc": "2.0", "id": "probe", "method": "tools/list"},
                sid, timeout=10)
            if body.get("error"):
                err = body["error"]
                msg = err.get("message") if isinstance(err, dict) else str(err)
                return jsonify({"status": "error",
                                "message": f"SIF 拒绝: {msg}"})
            tools = (body.get("result") or {}).get("tools") or []
            if not tools:
                return jsonify({"status": "error",
                                "message": "SIF 返回空工具列表，API Key 可能受限"})
            msg = f"SIF MCP 鉴权通过（{len(tools)} 个工具可用）"
            if used_saved_key:
                msg += " · 使用已保存的 Key"
            return jsonify({"status": "ok", "message": msg})
        except Exception as e:
            msg = str(e)
            # HTTP 4xx / 401 通常是 key 错误；区分一下
            if "401" in msg or "403" in msg or "unauthori" in msg.lower():
                return jsonify({"status": "error", "message": "API Key 无效"})
            return jsonify({"status": "error", "message": f"连接失败: {msg[:200]}"})

    # ------------------------------------------------------------------
    # Sorftime：真调一次 tools/list（URL 带 key，无握手）
    # ------------------------------------------------------------------
    if service == "sorftime":
        st = incoming.get("sorftime_mcp", incoming) if isinstance(incoming.get("sorftime_mcp"), dict) else incoming
        submitted = st.get("api_key", "")
        key = _resolve_key(submitted, "sorftime_mcp", "api_key")
        ep = st.get("endpoint") or load_config().get("sorftime_mcp", {}).get("endpoint", "")
        used_saved_key = (not submitted) or ("***" in submitted)
        if not ep:
            return jsonify({"status": "error", "message": "Endpoint 未填写"})
        # endpoint 里没带 ?key= 时，追加上
        if ("?key=" not in ep and "&key=" not in ep
                and key and "***" not in key):
            ep = ep + ("&" if "?" in ep else "?") + "key=" + key
        try:
            body, _ = _mcp_post(ep, key,
                {"jsonrpc": "2.0", "id": "probe", "method": "tools/list"},
                None, timeout=10)
            if body.get("error"):
                err = body["error"]
                msg = err.get("message") if isinstance(err, dict) else str(err)
                return jsonify({"status": "error",
                                "message": f"Sorftime 拒绝: {msg}"})
            tools = (body.get("result") or {}).get("tools") or []
            if not tools:
                return jsonify({"status": "error",
                                "message": "Sorftime 返回空工具列表，Key 可能受限"})
            # 若只返回 1 个 "NotAuthorization" 假工具，就判 key 无效
            names = [t.get("name", "") for t in tools if isinstance(t, dict)]
            if len(names) == 1 and "NotAuthorization" in names[0]:
                return jsonify({"status": "error",
                                "message": "API Key 无效（服务端仅返回 NotAuthorization 占位工具）"})
            msg = f"Sorftime MCP 鉴权通过（{len(tools)} 个工具可用）"
            if used_saved_key:
                msg += " · 使用已保存的 Key"
            return jsonify({"status": "ok", "message": msg})
        except Exception as e:
            msg = str(e)
            if "401" in msg or "403" in msg:
                return jsonify({"status": "error", "message": "API Key 无效"})
            return jsonify({"status": "error", "message": f"连接失败: {msg[:200]}"})

    return jsonify({"status": "error", "message": f"Unknown service: {service}"}), 400


def _apimart_fallback_auth_check(base: str, key: str):
    """当 /v1/models 不存在时，通过一次最小化的 /v1/images/generations 探测鉴权。
    错 key -> 401/403，正确 key -> 400（参数不完整）或 200。
    """
    import ssl
    try:
        ctx = ssl.create_default_context()
        parsed = urllib.parse.urlparse(base.rstrip("/") + "/v1/images/generations")
        conn = http.client.HTTPSConnection(
            parsed.hostname, parsed.port or 443, timeout=10, context=ctx
        )
        try:
            conn.request("POST", parsed.path, body=b"{}",
                         headers={
                             "Authorization": f"Bearer {key}",
                             "Content-Type": "application/json",
                         })
            resp = conn.getresponse()
            raw = resp.read().decode("utf-8", errors="replace")
            if resp.status in (401, 403):
                return jsonify({"status": "error",
                                "message": f"API Key 无效（HTTP {resp.status}）"})
            if resp.status == 400:
                # 参数错但鉴权通过了
                return jsonify({"status": "ok",
                                "message": "APIMart 鉴权通过（参数验证返回 400 是预期）"})
            if resp.status == 200:
                return jsonify({"status": "ok", "message": "APIMart 鉴权通过"})
            return jsonify({"status": "error",
                            "message": f"HTTP {resp.status}: {raw[:200]}"})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


# ---------------------------------------------------------------------------
# Licensing (offline AES-256-GCM via license_crypto)
# ---------------------------------------------------------------------------

@app.route('/api/activate', methods=['POST'])
def api_activate():
    """Verify a license key locally (no network call).

    The key is an AES-256-GCM encrypted payload bound to this machine's
    fingerprint. Generate one with recovery/tools/generate_license.py.
    """
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or data.get("key") or "").strip()
    if not code:
        return jsonify({"status": "error", "message": "激活码必填"}), 400
    try:
        from license_crypto import verify_and_save_license
        result = verify_and_save_license(code)
        return jsonify({
            "status": "ok",
            "valid": True,
            "exp_date": result.get("exp_date", ""),
            "days_left": result.get("days_left", 0),
            "mid": result.get("mid", ""),
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route('/api/trial-start', methods=['POST'])
def api_trial_start():
    """Start the 3-day trial (writes trial_start.key)."""
    try:
        from license_crypto import start_trial
        remaining = start_trial()
        return jsonify({
            "status": "ok",
            "trial_started": True,
            "days_left": remaining,
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/license-status')
def api_license_status():
    """Return full license info: active / trial / expired / none."""
    try:
        from license_crypto import get_license_info, get_machine_id
        info = get_license_info()
        # Always include mid so the activation dialog can show it
        if "mid" not in info or not info.get("mid"):
            info["mid"] = get_machine_id()
        return jsonify(info)
    except Exception as e:
        return jsonify({"status": "none", "message": str(e), "mid": ""})


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


# Kept for backward compat; the offline verifier above handles everything.
def _license_bootstrap(code: str, email: str) -> dict:
    from license_crypto import verify_and_save_license
    return verify_and_save_license(code)


# ---------------------------------------------------------------------------
# SQP Brand Analysis (独立功能)
# 接收 Amazon Search Query Performance 周度 CSV，输出结构化分析报告。
# ---------------------------------------------------------------------------

@app.route('/api/sqp/upload', methods=['POST'])
def api_sqp_upload():
    """
    上传一批 SQP CSV 文件（至少 1 个；≥ 2 周才出 WoW 分析）。
    表单字段：`files` (multi-file input)
    返回：{session_id, outputs, summary}
    """
    files = request.files.getlist("files")
    files = [f for f in files if f and f.filename]
    if not files:
        return jsonify({"error": "未上传文件，表单字段名应为 'files'"}), 400

    # Session dir：按时间戳 + 短 uuid 组织
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    sess_dir = SQP_DIR / session_id
    sess_dir.mkdir(parents=True, exist_ok=True)
    uploads_dir = sess_dir / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    saved: list = []
    for f in files:
        name = secure_filename(f.filename)
        if not name.lower().endswith(".csv"):
            continue
        dest = uploads_dir / name
        f.save(str(dest))
        saved.append(dest)

    if not saved:
        return jsonify({"error": "没有有效的 CSV 文件"}), 400

    # 调管道
    try:
        from tools.sqp_report import run_sqp_pipeline
        result = run_sqp_pipeline(saved, sess_dir, silent=True)
    except ValueError as e:
        return jsonify({"error": f"SQP 文件名必须包含 Week_YYYY_MM_DD：{e}"}), 400
    except Exception as e:
        logging.exception("SQP pipeline failed")
        return jsonify({"error": str(e)}), 500

    result["session_id"] = session_id
    # 给前端更友好的下载地址
    result["outputs"] = {
        name: f"/api/sqp/download/{session_id}/{name}"
        for name in result["outputs"].keys()
    }
    return jsonify(result)


@app.route('/api/sqp/report/<session_id>', methods=['GET'])
def api_sqp_report(session_id: str):
    """返回指定 session 的 Markdown 报告原文（text/plain；前端自己渲染）。"""
    sess_dir = SQP_DIR / secure_filename(session_id)
    md = sess_dir / "sqp_report.md"
    if not md.exists():
        return jsonify({"error": "报告未找到或已过期"}), 404
    return Response(md.read_text(encoding="utf-8"),
                    mimetype="text/markdown; charset=utf-8")


@app.route('/api/sqp/download/<session_id>/<path:filename>', methods=['GET'])
def api_sqp_download(session_id: str, filename: str):
    """下载 SQP 产出（CSV / PNG / MD）。"""
    sess_dir = SQP_DIR / secure_filename(session_id)
    if not sess_dir.exists():
        return jsonify({"error": "session 不存在"}), 404
    # 防越权
    safe_name = Path(filename).name
    target = sess_dir / safe_name
    if not target.exists():
        return jsonify({"error": "文件不存在"}), 404
    return send_from_directory(str(sess_dir), safe_name, as_attachment=False)


@app.route('/api/sqp/sessions', methods=['GET'])
def api_sqp_sessions():
    """列出最近的 SQP 分析 session（最多 20 个）。"""
    if not SQP_DIR.exists():
        return jsonify({"sessions": []})
    sessions = []
    for d in sorted(SQP_DIR.iterdir(), reverse=True)[:20]:
        if not d.is_dir():
            continue
        md = d / "sqp_report.md"
        uploads = d / "uploads"
        sessions.append({
            "session_id": d.name,
            "created_at": datetime.fromtimestamp(d.stat().st_mtime).isoformat(),
            "has_report": md.exists(),
            "upload_count": sum(1 for _ in uploads.glob("*.csv")) if uploads.exists() else 0,
        })
    return jsonify({"sessions": sessions})


# ---------------------------------------------------------------------------
# Rufus Research（自动 / 手动 双模式）
#
# 流程：
#   1) POST /api/rufus/probe-questions  →  生成 10 个探针问题
#   2) GET  /api/rufus/chrome-check     →  检测 9222 端口是否可用
#   3) POST /api/rufus/auto-run         →  自动模式（CDP 接管已登录的 Chrome）
#   4) POST /api/rufus/paste-submit     →  手动粘贴模式（auto 失败时兜底）
#   5) GET  /api/rufus/report/<asin>    →  下载最终 Markdown 报告
# ---------------------------------------------------------------------------

@app.route('/api/rufus/probe-questions', methods=['POST'])
def api_rufus_probe_questions():
    """从已运行过的 job 或直接传入的 context 生成 10 个 Rufus 探针问题。"""
    data = request.get_json(silent=True) or {}
    job_id = data.get("job_id")
    asin   = data.get("asin")

    ctx = None
    # 1) 优先从 job 读 context
    if job_id:
        with job_lock:
            j = jobs.get(job_id)
        if j and j.get("asin"):
            p = PROMPTS_DIR / f"{j['asin']}_context.json"
            if p.exists():
                ctx = json.loads(p.read_text("utf-8"))
    # 2) 退回到 asin
    if not ctx and asin:
        p = PROMPTS_DIR / f"{asin}_context.json"
        if p.exists():
            ctx = json.loads(p.read_text("utf-8"))

    if not ctx:
        return jsonify({"error": "找不到 context，请先提交 ASIN 并等分析完成"}), 404

    from expert_suggestions import _build_rufus_probe_strategy
    probe = _build_rufus_probe_strategy(ctx)

    # 扁平成 1 维问题列表，方便前端渲染 + 后端调用
    flat: list = []
    for qtype, qs in (probe.get("questions") or {}).items():
        for q in qs:
            flat.append({"type": qtype, "q": q.get("q"), "purpose": q.get("purpose")})

    return jsonify({
        "asin":      ctx.get("asin"),
        "category":  ctx.get("category"),
        "brand":     ctx.get("brand"),
        "probe":     probe,
        "questions": flat,
    })


@app.route('/api/rufus/chrome-check', methods=['GET'])
def api_rufus_chrome_check():
    """检测用户是否启动了带调试端口的 Chrome（自动模式前置条件）。"""
    try:
        from tools.rufus.chrome_session import probe_chrome_debug_port
    except Exception as e:
        return jsonify({"available": False, "message": f"依赖未就绪: {e}"}), 200
    port = int(request.args.get("port", 9222))
    return jsonify(probe_chrome_debug_port(port))


@app.route('/api/rufus/auto-run', methods=['POST'])
def api_rufus_auto_run():
    """自动模式：CDP 接管 Chrome 跑 10 题。

    Body: {
        "asin": "...",
        "questions": ["...", ...],
        "amazon_url": "https://www.amazon.com/s?k=...",  (可选)
        "port": 9222,
        "min_interval": 15,
        "max_interval": 40
    }
    """
    data = request.get_json(silent=True) or {}
    asin = (data.get("asin") or "").strip()
    questions = data.get("questions") or []
    if not asin or not _validate_asin(asin):
        return jsonify({"error": "ASIN 无效"}), 400
    if not questions or len(questions) > 12:
        return jsonify({"error": "questions 数量需在 1-12 之间"}), 400

    port = int(data.get("port", 9222))
    amazon_url = data.get("amazon_url") or f"https://www.amazon.com/dp/{asin}"
    min_interval = int(data.get("min_interval", 15))
    max_interval = int(data.get("max_interval", 40))

    try:
        from tools.rufus.runner import run_rufus_auto, build_rufus_report
    except Exception as e:
        return jsonify({"error": f"Rufus 模块加载失败: {e}"}), 500

    session = run_rufus_auto(
        asin=asin, questions=questions, port=port,
        amazon_url=amazon_url,
        min_interval=min_interval, max_interval=max_interval,
    )

    # 拉对应 context 用于 GEO 审计
    ctx_path = PROMPTS_DIR / f"{asin}_context.json"
    ctx = json.loads(ctx_path.read_text("utf-8")) if ctx_path.exists() else None

    report_path = PROMPTS_DIR / f"{asin}_rufus_report.md"
    report = build_rufus_report(
        session=session,
        listing_context=ctx,
        save_to=report_path,
    )

    return jsonify({
        "mode": session["mode"],
        "success": session["success"],
        "captured_count": session["captured_count"],
        "total_questions": session["total_questions"],
        "should_fallback_to_manual": session["should_fallback_to_manual"],
        "captcha_detected": session["captcha_detected"],
        "reason": session["reason"],
        "aborted_at": session.get("aborted_at"),
        "abort_reason": session.get("abort_reason"),
        "report_url": f"/api/rufus/report/{asin}",
        "geo_audit": report["geo_audit"],
        "summary": report["summary"],
        "raw_results": session["raw_results"],
    })


@app.route('/api/rufus/paste-submit', methods=['POST'])
def api_rufus_paste_submit():
    """手动模式：用户粘贴 Rufus 答案。

    Body: {
        "asin": "...",
        "questions": [...],
        "answers":   [...]     # 和 questions 一一对应；空串视为未回答
    }
    """
    data = request.get_json(silent=True) or {}
    asin = (data.get("asin") or "").strip()
    questions = data.get("questions") or []
    answers   = data.get("answers")   or []

    if not asin or not _validate_asin(asin):
        return jsonify({"error": "ASIN 无效"}), 400
    if len(questions) == 0 or len(questions) != len(answers):
        return jsonify({"error": "questions / answers 长度不一致或为空"}), 400

    try:
        from tools.rufus.runner import accept_manual_answers, build_rufus_report
    except Exception as e:
        return jsonify({"error": f"Rufus 模块加载失败: {e}"}), 500

    session = accept_manual_answers(asin, questions, answers)

    ctx_path = PROMPTS_DIR / f"{asin}_context.json"
    ctx = json.loads(ctx_path.read_text("utf-8")) if ctx_path.exists() else None

    report_path = PROMPTS_DIR / f"{asin}_rufus_report.md"
    report = build_rufus_report(
        session=session, listing_context=ctx, save_to=report_path,
    )

    return jsonify({
        "mode": session["mode"],
        "success": session["success"],
        "captured_count": session["captured_count"],
        "total_questions": session["total_questions"],
        "report_url": f"/api/rufus/report/{asin}",
        "geo_audit": report["geo_audit"],
        "summary": report["summary"],
    })


@app.route('/api/rufus/report/<asin>', methods=['GET'])
def api_rufus_report(asin: str):
    """拉 Rufus 报告 Markdown。"""
    asin = secure_filename(asin)
    md = PROMPTS_DIR / f"{asin}_rufus_report.md"
    if not md.exists():
        return jsonify({"error": "报告不存在，请先跑 auto-run 或 paste-submit"}), 404
    return Response(md.read_text(encoding="utf-8"),
                    mimetype="text/markdown; charset=utf-8")


@app.route('/api/rufus/report-json/<asin>', methods=['GET'])
def api_rufus_report_json(asin: str):
    """拉 Rufus 报告的结构化 JSON（前端渲染用）。"""
    asin = secure_filename(asin)
    j = PROMPTS_DIR / f"{asin}_rufus_report.json"
    if not j.exists():
        return jsonify({"error": "JSON 报告不存在"}), 404
    return jsonify(json.loads(j.read_text(encoding="utf-8")))


# ---------------------------------------------------------------------------
# Agent Layer
# Multi-Provider LLM 接入 + Skill Tool Registry + ReAct Runtime
# ---------------------------------------------------------------------------

@app.route('/api/agent/providers', methods=['GET'])
def api_agent_providers():
    """列出已配置的 LLM Provider（掩码 key）"""
    from agent import list_providers
    ps = [p.to_public_dict() for p in list_providers()]
    return jsonify({"providers": ps})


@app.route('/api/agent/providers', methods=['POST'])
def api_agent_save_providers():
    """保存完整的 llm_providers 列表。前端传 [{name, type, base_url, api_key, ...}]
    加密落盘（api_key 会走现有的 _encrypt_dict）。空 api_key 或含 *** 的会保留原值。
    """
    data = request.get_json(silent=True) or {}
    incoming = data.get("providers")
    if not isinstance(incoming, list):
        return jsonify({"error": "providers 必须是数组"}), 400

    cfg = load_config()
    existing = cfg.get("llm_providers") or []
    # 用 name 对齐，处理 key 掩码
    existing_by_name = {p.get("name"): p for p in existing if isinstance(p, dict)}

    sanitized: list[dict] = []
    seen_names: set = set()
    for item in incoming:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        if not name or name in seen_names:
            continue
        seen_names.add(name)

        # 如果提交的 api_key 含 ***（掩码），用已保存的真值
        submitted_key = item.get("api_key") or ""
        if "***" in submitted_key:
            existing_key = (existing_by_name.get(name) or {}).get("api_key", "")
            submitted_key = existing_key

        sanitized.append({
            "name":        name,
            "type":        (item.get("type") or "openai_compatible").lower(),
            "base_url":    (item.get("base_url") or "").rstrip("/"),
            "api_key":     submitted_key,
            "model":       item.get("model") or "",
            "is_default":  bool(item.get("is_default")),
            "enabled":     bool(item.get("enabled", True)),
            "temperature": float(item.get("temperature", 0.2)),
            "timeout":     int(item.get("timeout", 90)),
            "extra_headers": item.get("extra_headers") or {},
            "max_iterations": int(item.get("max_iterations", 6)),
        })

    # 保证最多 1 个 is_default（如果有多个都是 true，只保留第一个）
    seen_default = False
    for p in sanitized:
        if p["is_default"]:
            if seen_default:
                p["is_default"] = False
            else:
                seen_default = True

    cfg["llm_providers"] = sanitized
    save_config(cfg)
    return jsonify({"ok": True, "count": len(sanitized)})


@app.route('/api/agent/test-provider', methods=['POST'])
def api_agent_test_provider():
    """测单个 Provider 的连通性 + key 有效性。
    Body: {provider: {name, type, base_url, api_key, model, ...}}
          或 {name: "existing-name"}
    """
    from agent import LLMProvider, get_provider, probe_provider
    data = request.get_json(silent=True) or {}
    p: LLMProvider
    if data.get("name") and not data.get("provider"):
        p = get_provider(data["name"])
        if p is None:
            return jsonify({"ok": False, "message": "未找到已保存的 Provider"}), 404
    else:
        raw = data.get("provider") or {}
        # 若 api_key 掩码，取真值
        if "***" in (raw.get("api_key") or ""):
            existing = get_provider(raw.get("name", ""))
            if existing:
                raw["api_key"] = existing.api_key
        p = LLMProvider.from_dict(raw)

    result = probe_provider(p)
    return jsonify(result)


@app.route('/api/agent/tools', methods=['GET'])
def api_agent_tools():
    """列出所有已注册的 Skill 工具及 schema（前端可预览给用户看 agent 能调哪些）。"""
    from agent import get_tool_schemas
    return jsonify({"tools": get_tool_schemas()})


@app.route('/api/agent/chat', methods=['POST'])
def api_agent_chat():
    """单轮 agent 对话（内部可能跑多次 ReAct 循环直到 LLM 不再调工具）。

    Body:
      {
        "message": "分析 B0F7QJC249 的 listing，并告诉我哪些 bullet 最差",
        "provider_name": "openai-main",  // 可选
        "history": [{role, content}],    // 可选 - 多轮上下文
      }
    """
    data = request.get_json(silent=True) or {}
    msg = (data.get("message") or "").strip()
    if not msg:
        return jsonify({"error": "message 不能为空"}), 400

    from agent import run_agent_turn
    try:
        result = run_agent_turn(
            user_message=msg,
            provider_name=data.get("provider_name"),
            history=data.get("history") or [],
            system_prompt=data.get("system_prompt"),
        )
    except Exception as e:
        logging.exception("Agent chat failed")
        return jsonify({"error": str(e)}), 500

    # 裁剪一下返回内容，不把完整 tool results 再塞回去（前端不需要）
    if "messages" in result:
        compact = []
        for m in result["messages"]:
            if m.get("role") == "tool":
                compact.append({
                    "role": "tool",
                    "name": m.get("name"),
                    "content": (m.get("content") or "")[:500],
                })
            else:
                mm = {"role": m.get("role"),
                      "content": (m.get("content") or "")[:2000]}
                if m.get("tool_calls"):
                    mm["tool_calls"] = [
                        {"name": tc["function"]["name"],
                         "arguments_preview": tc["function"]["arguments"][:300]}
                        for tc in m["tool_calls"]
                    ]
                compact.append(mm)
        result["messages_compact"] = compact
        del result["messages"]

    return jsonify(result)


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
