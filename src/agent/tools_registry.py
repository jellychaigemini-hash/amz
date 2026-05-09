# -*- coding: utf-8 -*-
"""
Tool Registry — 把底层 Skill 暴露给 LLM Agent
=============================================

每个 tool 三要素：
  · name:        LLM 引用的唯一名字（snake_case）
  · description: 告诉 LLM 什么时候该用它
  · parameters:  JSON Schema（LLM 按 schema 填参数）
  · handler:     Python 函数（接收 dict 参数，返回 dict 结果）

Agent 运行时用 `get_tool_schemas()` 把 schema 给 LLM，LLM 决定调哪个，
我们用 `run_tool(name, args)` 执行并把结果序列化回 LLM。
"""
from __future__ import annotations

import json
import traceback
from pathlib import Path
from typing import Any, Callable

# 工具执行结果的最大字节数（超出部分截断，避免 LLM context 被爆）
MAX_TOOL_OUTPUT_BYTES = 16000


# ═════════════════════════════════════════════════════════════════
# Tool 定义
# ═════════════════════════════════════════════════════════════════

def _tool_analyze_asin(args: dict) -> dict:
    """同步版：阻塞直到 pipeline 完成，返回 context + expert_data。"""
    import app
    asin = (args.get("asin") or "").strip()
    marketplace = (args.get("marketplace") or "US").strip()

    if not app._validate_asin(asin):
        return {"error": "ASIN 格式无效（应为 10 位大写字母数字）"}

    # 直接调 build_context + expert_suggestions，不走异步 job，立刻返回
    from expert_suggestions import (
        build_cosmo_title, build_cosmo_bullets, build_rufus_qa,
        extract_selling_points, build_data_insights,
    )
    context = app.build_context("agent_sync", asin, marketplace)
    expert = {
        "title_suggestion": build_cosmo_title(context),
        "bullets_analysis": build_cosmo_bullets(context),
        "qa_suggestions":   build_rufus_qa(context),
        "selling_points":   extract_selling_points(context),
        "data_insights":    build_data_insights(context),
    }
    # Persist context so downstream tools can reuse
    ctx_path = app.PROMPTS_DIR / f"{asin}_context.json"
    ctx_path.write_text(json.dumps(context, ensure_ascii=False, indent=2),
                         encoding="utf-8")

    return {
        "asin": asin,
        "marketplace": marketplace,
        "context_summary": {
            "title":         context.get("title", "")[:200],
            "brand":         context.get("brand"),
            "category":      context.get("category"),
            "price":         context.get("price"),
            "rating":        context.get("rating"),
            "review_count":  context.get("review_count"),
            "monthly_sales": context.get("monthly_sales"),
            "bullets_count": len(context.get("bullets") or []),
            "keywords_count": len(context.get("keywords") or []),
            "has_real_data": context.get("_has_real_data"),
            "data_quality":  context.get("_data_quality"),
            "traffic_breakdown": context.get("traffic_breakdown"),
        },
        "cosmo_title": {
            "score":        expert["title_suggestion"].get("cosmo_analysis", {}).get("title_score"),
            "grade":        expert["title_suggestion"].get("cosmo_analysis", {}).get("title_grade"),
            "keyword_gaps": expert["title_suggestion"].get("cosmo_analysis", {}).get("keyword_gaps", [])[:10],
            "suggestions":  expert["title_suggestion"].get("cosmo_analysis", {}).get("suggestions", [])[:5],
        },
        "geo_audit_static": expert["title_suggestion"].get("geo_audit", {}),
        "bullets_score":    expert["bullets_analysis"].get("overall_score"),
        "bullets_summary":  expert["bullets_analysis"].get("summary"),
        "top_3_selling_points": (expert["selling_points"] or {}).get("top_3", [])[:3],
        "data_insights_highlights": {
            "overview":        expert["data_insights"].get("overview"),
            "keyword_health":  expert["data_insights"].get("keyword_health"),
            "market_signals":  expert["data_insights"].get("market_signals"),
            "recommendations": expert["data_insights"].get("recommendations", [])[:5],
        },
        "_note": "完整数据已持久化到 prompts/<ASIN>_context.json，后续 Rufus 调研会自动复用",
    }


def _tool_generate_probe_questions(args: dict) -> dict:
    import app
    from expert_suggestions import _build_rufus_probe_strategy

    asin = (args.get("asin") or "").strip()
    ctx_path = app.PROMPTS_DIR / f"{asin}_context.json"
    if not ctx_path.exists():
        return {"error": f"未找到 {asin} 的 context，请先用 analyze_asin 工具采集"}

    ctx = json.loads(ctx_path.read_text("utf-8"))
    probe = _build_rufus_probe_strategy(ctx)

    # 扁平化 + 精简
    flat = []
    for qtype, qs in (probe.get("questions") or {}).items():
        for q in qs:
            flat.append({"type": qtype, "q": q.get("q"), "purpose": q.get("purpose")})

    return {
        "asin": asin,
        "priority": probe.get("priority"),
        "weakness_scores": probe.get("weakness_scores"),
        "allocation": probe.get("allocation"),
        "questions": flat,
        "total": len(flat),
    }


def _tool_rufus_paste_submit(args: dict) -> dict:
    """给 LLM 暴露手动提交入口。LLM 可以把用户粘贴的 Rufus 原文分发到这里。"""
    import app
    from tools.rufus.runner import accept_manual_answers, build_rufus_report

    asin = (args.get("asin") or "").strip()
    questions = args.get("questions") or []
    answers   = args.get("answers") or []
    if not app._validate_asin(asin):
        return {"error": "ASIN 无效"}
    if not questions or len(questions) != len(answers):
        return {"error": "questions 与 answers 数量必须一致"}

    session = accept_manual_answers(asin, questions, answers)
    ctx_path = app.PROMPTS_DIR / f"{asin}_context.json"
    ctx = json.loads(ctx_path.read_text("utf-8")) if ctx_path.exists() else None
    report_path = app.PROMPTS_DIR / f"{asin}_rufus_report.md"
    report = build_rufus_report(session, listing_context=ctx, save_to=report_path)

    return {
        "mode": "manual",
        "captured_count": session["captured_count"],
        "total_questions": session["total_questions"],
        "geo_audit": report["geo_audit"],
        "summary":   report["summary"],
        "report_path": str(report_path.relative_to(app.BASE_DIR)),
        "report_url": f"/api/rufus/report/{asin}",
    }


def _tool_rufus_check_chrome(args: dict) -> dict:
    from tools.rufus.chrome_session import probe_chrome_debug_port
    port = int(args.get("port") or 9222)
    return probe_chrome_debug_port(port)


def _tool_rufus_auto_run(args: dict) -> dict:
    import app
    from tools.rufus.runner import run_rufus_auto, build_rufus_report
    asin = (args.get("asin") or "").strip()
    questions = args.get("questions") or []
    if not app._validate_asin(asin):
        return {"error": "ASIN 无效"}
    if not questions or len(questions) > 12:
        return {"error": "questions 数量应在 1–12 之间"}

    port = int(args.get("port") or 9222)
    url  = args.get("amazon_url") or f"https://www.amazon.com/dp/{asin}"
    session = run_rufus_auto(asin=asin, questions=questions, port=port,
                              amazon_url=url,
                              min_interval=int(args.get("min_interval") or 15),
                              max_interval=int(args.get("max_interval") or 40))
    ctx_path = app.PROMPTS_DIR / f"{asin}_context.json"
    ctx = json.loads(ctx_path.read_text("utf-8")) if ctx_path.exists() else None
    report_path = app.PROMPTS_DIR / f"{asin}_rufus_report.md"
    report = build_rufus_report(session, listing_context=ctx, save_to=report_path)

    return {
        "mode": "auto",
        "captured_count": session["captured_count"],
        "total_questions": session["total_questions"],
        "should_fallback_to_manual": session["should_fallback_to_manual"],
        "captcha_detected": session["captcha_detected"],
        "aborted_at": session.get("aborted_at"),
        "abort_reason": session.get("abort_reason"),
        "reason": session["reason"],
        "geo_audit": report["geo_audit"],
        "summary":   report["summary"],
        "report_url": f"/api/rufus/report/{asin}",
    }


def _tool_sqp_analyze(args: dict) -> dict:
    """当用户提供 SQP CSV 路径时跑分析。文件必须已上传/存在在服务器 paths 里。"""
    import app
    from tools.sqp_report import run_sqp_pipeline

    paths_arg = args.get("csv_paths") or []
    if not paths_arg:
        return {"error": "csv_paths 必填（SQP CSV 文件的本地绝对路径或相对 BASE_DIR 的路径）"}
    resolved: list[Path] = []
    for raw in paths_arg:
        p = Path(raw)
        if not p.is_absolute():
            p = app.BASE_DIR / raw
        if p.exists() and p.suffix.lower() == ".csv":
            resolved.append(p)
    if not resolved:
        return {"error": "未找到有效 CSV", "attempted": paths_arg}

    from datetime import datetime as _dt
    import uuid as _uuid
    session_id = _dt.now().strftime("%Y%m%d_%H%M%S") + "_" + _uuid.uuid4().hex[:6]
    out_dir = app.SQP_DIR / session_id
    try:
        result = run_sqp_pipeline(resolved, out_dir, silent=True)
    except Exception as e:
        return {"error": f"SQP pipeline 失败: {e}"}

    result["session_id"] = session_id
    # rewrite outputs to URL form
    result["outputs"] = {
        name: f"/api/sqp/download/{session_id}/{name}"
        for name in result["outputs"].keys()
    }
    return result


def _tool_list_recent_reports(args: dict) -> dict:
    """列出 prompts/ 下已生成的 context 和 rufus 报告，方便 LLM 了解"哪些 ASIN 已分析过"。"""
    import app
    limit = int(args.get("limit") or 20)
    items = []
    if app.PROMPTS_DIR.exists():
        for f in sorted(app.PROMPTS_DIR.glob("*_context.json"),
                         key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
            asin = f.name.replace("_context.json", "")
            rufus_md = app.PROMPTS_DIR / f"{asin}_rufus_report.md"
            items.append({
                "asin": asin,
                "has_context": True,
                "has_rufus_report": rufus_md.exists(),
                "context_path": f"prompts/{f.name}",
                "context_updated_at": f.stat().st_mtime,
            })
    return {"items": items, "count": len(items)}


# ═════════════════════════════════════════════════════════════════
# TOOLS 表：name -> {description, parameters, handler}
# ═════════════════════════════════════════════════════════════════

TOOLS: dict[str, dict] = {
    # ── 单 ASIN 分析主入口 ──────────────────────────────────────
    "analyze_asin": {
        "description": (
            "对某个 Amazon ASIN 做完整的 Listing 分析：拉 SIF + Sorftime "
            "MCP 数据、跑 COSMO 标题 / 五点 / Q&A / 卖点 / 数据洞察、"
            "并输出 GEO 6 维度静态审计。结果自动持久化到 prompts/<ASIN>_context.json。"
            "这是**大多数分析任务的起点**。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "asin":        {"type": "string", "description": "10 位 Amazon ASIN"},
                "marketplace": {"type": "string",
                                "description": "站点代码：US / UK / DE / JP 等",
                                "default": "US"},
            },
            "required": ["asin"],
        },
        "handler": _tool_analyze_asin,
    },

    # ── Rufus probing 问题生成 ────────────────────────────────
    "generate_rufus_probe_questions": {
        "description": (
            "基于已采集的 Listing context（先跑 analyze_asin），识别 listing "
            "最弱的 3 个维度（场景 / 决策因素 / 对比 / 反馈 / 语言），按 3/3/2/2 "
            "分配生成最多 10 个 Rufus 探针问题。每题都带 purpose（为什么问）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "asin": {"type": "string", "description": "已分析过的 ASIN"},
            },
            "required": ["asin"],
        },
        "handler": _tool_generate_probe_questions,
    },

    # ── Rufus 采集：手动粘贴 ─────────────────────────────────
    "rufus_paste_submit": {
        "description": (
            "用户从 Amazon 网页上粘贴 Rufus 回答时使用。对每题回答做解析并出 "
            "Rufus-evidence-based 的 GEO 6 维度审计报告（有真实 Rufus 数据会比 "
            "analyze_asin 里的静态 geo_audit 精准得多）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "asin":      {"type": "string"},
                "questions": {"type": "array", "items": {"type": "string"}},
                "answers":   {"type": "array", "items": {"type": "string"},
                              "description": "和 questions 一一对应；空串表示跳过"},
            },
            "required": ["asin", "questions", "answers"],
        },
        "handler": _tool_rufus_paste_submit,
    },

    # ── Rufus 自动 CDP 探测 ──────────────────────────────────
    "rufus_check_chrome": {
        "description": (
            "检测用户本地 Chrome 是否在调试端口可接管（自动模式前置条件）。"
            "返回 available 为 false 时应推荐用户切换到 rufus_paste_submit 手动模式。"
        ),
        "parameters": {
            "type": "object",
            "properties": {"port": {"type": "integer", "default": 9222}},
        },
        "handler": _tool_rufus_check_chrome,
    },

    "rufus_auto_run": {
        "description": (
            "自动模式：CDP 接管已登录 Chrome，带 Stealth 注入 + 15-40s 随机间隔 + "
            "CAPTCHA 检测，跑完全部问题后生成 Rufus-evidence-based GEO 审计报告。"
            "失败时返回 should_fallback_to_manual=true，此时应提示用户切换手动。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "asin":      {"type": "string"},
                "questions": {"type": "array", "items": {"type": "string"}},
                "amazon_url": {"type": "string",
                                "description": "默认跳转 https://www.amazon.com/dp/<ASIN>"},
                "port":      {"type": "integer", "default": 9222},
                "min_interval": {"type": "integer", "default": 15},
                "max_interval": {"type": "integer", "default": 40},
            },
            "required": ["asin", "questions"],
        },
        "handler": _tool_rufus_auto_run,
    },

    # ── SQP 品牌分析 ─────────────────────────────────────────
    "sqp_brand_analyze": {
        "description": (
            "批量分析 Amazon SQP 周度 CSV（来自品牌后台导出）。需提供至少 1 "
            "个 CSV 路径；≥ 2 周才能出 WoW 对比。产出：品牌快照、高转化词、"
            "新入列/跌出列、自身比、大盘比、Top5 稳定词 + 趋势图 + Markdown 报告。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "csv_paths": {
                    "type": "array", "items": {"type": "string"},
                    "description": "SQP CSV 文件路径（绝对或相对 BASE_DIR）。文件名需含 Week_YYYY_MM_DD",
                },
            },
            "required": ["csv_paths"],
        },
        "handler": _tool_sqp_analyze,
    },

    # ── 辅助：查看已分析的 ASIN ─────────────────────────────
    "list_recent_reports": {
        "description": "列出最近分析过的 ASIN（有 context 的）以及是否已生成 Rufus 报告。",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 20},
            },
        },
        "handler": _tool_list_recent_reports,
    },
}


# ═════════════════════════════════════════════════════════════════
# 对外 API
# ═════════════════════════════════════════════════════════════════

def get_tool_schemas(for_type: str = "openai_compatible") -> list[dict]:
    """返回工具 schema 数组，格式按 provider 类型适配。"""
    schemas = []
    for name, t in TOOLS.items():
        schemas.append({
            "type": "function",
            "function": {
                "name": name,
                "description": t["description"],
                "parameters": t["parameters"],
            },
        })
    return schemas


def run_tool(name: str, arguments: dict) -> dict:
    """执行工具，返回 {ok, result|error, _truncated}。"""
    if name not in TOOLS:
        return {"ok": False, "error": f"未知工具: {name}"}
    try:
        out = TOOLS[name]["handler"](arguments or {})
    except Exception as e:
        return {
            "ok": False,
            "error": f"{type(e).__name__}: {e}",
            "trace": traceback.format_exc()[:800],
        }

    # 序列化 + 截断，避免把 LLM context 撑爆
    try:
        s = json.dumps(out, ensure_ascii=False, default=str)
    except Exception:
        s = str(out)
    truncated = False
    if len(s.encode("utf-8")) > MAX_TOOL_OUTPUT_BYTES:
        s = s.encode("utf-8")[:MAX_TOOL_OUTPUT_BYTES].decode("utf-8", errors="ignore")
        s += '\n…[TRUNCATED]'
        truncated = True
        try:
            out = json.loads(s)
        except Exception:
            # 截断后不一定还是合法 JSON，降级成 text
            return {"ok": True, "result_text": s, "_truncated": True}

    return {"ok": True, "result": out, "_truncated": truncated}
