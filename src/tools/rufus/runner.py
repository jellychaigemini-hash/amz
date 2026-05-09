# -*- coding: utf-8 -*-
"""
Rufus 编排器
============
负责串起：
  · 问题清单（通常来自 expert_suggestions._build_rufus_probe_strategy）
  · 自动采集（CDP 连 Chrome）
  · 手动采集（用户粘贴）
  · 解析（parser.py）
  · 评估 + 报告生成（GEO 6 维度 + Rufus 证据）
  · 落盘：prompts/<asin>_rufus.json + prompts/<asin>_rufus_report.md

两种模式共享同一套解析 + 评分 + 报告管线，只是"答案从哪里来"不同。
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

from .parser import parse_rufus_answer, summarize_answers
from .chrome_session import run_auto_session, RufusProgress, RufusRunResult


# ── 模式 1：自动 ────────────────────────────────────────────────
def run_rufus_auto(
    asin: str,
    questions: list[str],
    port: int = 9222,
    amazon_url: str = "https://www.amazon.com/",
    min_interval: int = 15,
    max_interval: int = 40,
    answer_max_wait: int = 25,
    progress_cb: Optional[Callable[[RufusProgress], None]] = None,
) -> dict:
    """同步接口（内部开 asyncio loop）。供 Flask 直接调用。

    返回 dict：{
        "mode": "auto",
        "success": bool,
        "should_fallback_to_manual": bool,
        "reason": str,
        "asin": str,
        "questions": [...],
        "raw_results": [{index, question, answer, stage, error}, ...],
        "captcha_detected": bool,
        "aborted_at": int | None,
    }
    """
    loop = asyncio.new_event_loop()
    try:
        result: RufusRunResult = loop.run_until_complete(
            run_auto_session(
                questions=questions,
                amazon_url=amazon_url,
                port=port,
                min_interval=min_interval,
                max_interval=max_interval,
                answer_max_wait=answer_max_wait,
                progress_cb=progress_cb,
            )
        )
    finally:
        loop.close()

    # 决定是否降级
    captured = sum(1 for r in result.question_results if r["stage"] == "captured")
    should_fallback = (
        not result.success or
        result.captcha_detected or
        (captured < len(questions) // 2)      # 成功率 < 50% 建议降级
    )

    return {
        "mode": "auto",
        "asin": asin,
        "success": result.success,
        "captured_count": captured,
        "total_questions": len(questions),
        "should_fallback_to_manual": should_fallback,
        "reason": result.reason,
        "captcha_detected": result.captcha_detected,
        "aborted_at": result.aborted_at,
        "abort_reason": result.abort_reason,
        "questions": questions,
        "raw_results": result.question_results,
    }


# ── 模式 2：手动（粘贴） ────────────────────────────────────────
def accept_manual_answers(
    asin: str,
    questions: list[str],
    answers: list[str],
) -> dict:
    """用户手动把从 Amazon 网页上复制的 Rufus 回答粘贴进来。

    Args:
        questions: 10 个问题
        answers: 对应的 10 个回答原文（可能有缺漏，空串表示跳过）
    """
    raw_results = []
    for i, (q, a) in enumerate(zip(questions, answers)):
        raw_results.append({
            "index":   i + 1,
            "question": q,
            "answer":   (a or "").strip(),
            "stage":    "manual" if (a or "").strip() else "skipped",
            "elapsed_sec": 0,
            "error":    "" if a else "用户未提供答案",
        })
    return {
        "mode": "manual",
        "asin": asin,
        "success": any(r["stage"] == "manual" for r in raw_results),
        "captured_count": sum(1 for r in raw_results if r["stage"] == "manual"),
        "total_questions": len(questions),
        "should_fallback_to_manual": False,
        "reason": "手动粘贴模式",
        "questions": questions,
        "raw_results": raw_results,
    }


# ── 报告生成（两种模式共用） ────────────────────────────────────
def build_rufus_report(
    session: dict,
    listing_context: Optional[dict] = None,
    save_to: Optional[Path] = None,
) -> dict:
    """
    用采集到的 Rufus 答案 + 现有 listing context，生成结构化审计报告。

    Args:
        session: run_rufus_auto / accept_manual_answers 的返回值
        listing_context: 当前 ASIN 的 context（title/bullets/keywords/...）
                          用于和 Rufus 答案做对照审计
        save_to: 如果给了路径，把 Markdown 报告写到这里

    Returns: {
        "summary": {...},      # summarize_answers 的输出
        "per_question": [...], # 每题的结构化解析
        "geo_audit": {...},    # 基于 Rufus 证据 × listing 现状的 6 维度打分
        "markdown": "..."      # 完整 Markdown 报告
    }
    """
    parsed_list = []
    known_brands = []
    if listing_context:
        # 给 brand 识别一个 hint（避免把自己的品牌识别成"竞品"）
        if listing_context.get("brand"):
            known_brands.append(listing_context["brand"])

    for r in session.get("raw_results", []):
        parsed = parse_rufus_answer(
            r.get("answer", ""), r.get("question", ""),
            known_brands=known_brands,
        )
        parsed["index"]    = r["index"]
        parsed["question"] = r["question"]
        parsed["stage"]    = r["stage"]
        parsed_list.append(parsed)

    summary = summarize_answers(parsed_list)

    # ── GEO Audit：把 Rufus 的『driver_heatmap / scene_heatmap』和 listing 对照 ──
    geo_audit = _geo_audit_with_rufus(
        rufus_summary=summary,
        listing_context=listing_context or {},
    )

    # ── Markdown ─────────────────────────────────────────────────
    md = _build_markdown(session, parsed_list, summary, geo_audit, listing_context)

    report = {
        "summary":      summary,
        "per_question": parsed_list,
        "geo_audit":    geo_audit,
        "markdown":     md,
        "generated_at": datetime.now().isoformat(),
        "mode":         session.get("mode"),
        "captured_count": session.get("captured_count", 0),
        "total_questions": session.get("total_questions", 0),
    }

    if save_to:
        save_to = Path(save_to)
        save_to.parent.mkdir(parents=True, exist_ok=True)
        save_to.write_text(md, encoding="utf-8")
        # 同时落 JSON（方便前端二次读取）
        json_path = save_to.with_suffix(".json")
        json_path.write_text(
            json.dumps({
                "summary": summary,
                "per_question": parsed_list,
                "geo_audit": geo_audit,
                "captured_count": report["captured_count"],
                "total_questions": report["total_questions"],
                "mode": report["mode"],
                "generated_at": report["generated_at"],
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return report


# ── 内部：GEO Audit with Rufus 证据 ─────────────────────────────
# 和 expert_suggestions 里静态的 GEO Audit 不同，这一版拿 Rufus 的
# driver_heatmap / scene_heatmap 作为"买家真正在乎什么"的外部证据。
def _geo_audit_with_rufus(rufus_summary: dict, listing_context: dict) -> dict:
    title    = (listing_context.get("title") or "").lower()
    bullets  = " ".join(str(b) for b in (listing_context.get("bullets") or [])).lower()
    merged   = title + " | " + bullets

    driver_heat = rufus_summary.get("driver_heatmap", {}) or {}
    scene_heat  = rufus_summary.get("scene_heatmap", {}) or {}
    top_followups = rufus_summary.get("top_follow_ups", []) or []
    top_brands    = rufus_summary.get("top_brands", []) or []

    # 场景覆盖（20）：Rufus 高频场景 vs listing 是否提了
    scene_hit_keys = [
        ("bedroom",  ["bedroom"]), ("living", ["living"]),
        ("kitchen",  ["kitchen"]), ("bathroom", ["bathroom"]),
        ("office",   ["office"]),  ("outdoor",  ["outdoor", "outside"]),
        ("travel",   ["travel", "on-the-go"]),
        ("small",    ["apartment", "small space", "compact"]),
        ("gift",     ["gift"]),    ("kids", ["kid", "children"]),
        ("pets",     ["pet"]),     ("gym",  ["gym"]),
    ]
    scene_top = [k for k, _ in sorted(scene_heat.items(), key=lambda x: -x[1])[:5]]
    scene_present = []
    for k in scene_top:
        needles = dict(scene_hit_keys).get(k, [k])
        if any(n in merged for n in needles):
            scene_present.append(k)
    scene_gap = [k for k in scene_top if k not in scene_present]
    if scene_top:
        scene_score = int(round(len(scene_present) / len(scene_top) * 20))
    else:
        scene_score = 10

    # 决策因素（20）：Rufus 高频因素 vs listing 提及
    driver_hit_keys = {
        "size":         ["size", "inch", "cm", "mm", "dimension"],
        "material":     ["material", "stainless", "wood", "metal", "silicone",
                         "polyester", "rubber", "fabric"],
        "durability":   ["durable", "sturdy", "heavy-duty", "long-lasting"],
        "ease_of_use":  ["easy", "simple", "quick", "hassle-free"],
        "cleanability": ["washable", "clean", "reusable"],
        "safety":       ["safe", "bpa-free", "certified"],
        "versatility":  ["multi", "versatile", "3-in-1", "2-in-1", "all-in-one"],
        "price_value":  ["value", "affordable", "budget"],
        "noise":        ["quiet", "silent"],
        "energy":       ["energy", "battery"],
    }
    driver_top = [k for k, _ in sorted(driver_heat.items(), key=lambda x: -x[1])[:5]]
    driver_present = []
    for k in driver_top:
        needles = driver_hit_keys.get(k, [k])
        if any(n in merged for n in needles):
            driver_present.append(k)
    driver_gap = [k for k in driver_top if k not in driver_present]
    if driver_top:
        driver_score = int(round(len(driver_present) / len(driver_top) * 20))
    else:
        driver_score = 10

    # 用户语言（15）：Rufus follow-ups 里的高频短语 → listing 是否用了同类表达
    # 简单启发：若 top5 follow-up 里至少 1 条的核心词在 bullets 里出现，给高分
    lang_score = 5
    followup_lang_hits = 0
    for fu, _cnt in top_followups[:5]:
        tokens = [w for w in fu.lower().split() if len(w) > 4]
        if any(t in merged for t in tokens):
            followup_lang_hits += 1
    if followup_lang_hits >= 3:
        lang_score = 15
    elif followup_lang_hits >= 2:
        lang_score = 12
    elif followup_lang_hits >= 1:
        lang_score = 8

    # 竞品定位（15）：Rufus 提到的其他品牌数越多，说明这个类目竞争越激烈
    #   我们的 listing 如果不能明显区分 → 扣分
    lc_brand = (listing_context.get("brand") or "").lower()
    positioning_score = 10
    positioning_rec = ""
    if top_brands:
        # 去除自身
        competitors = [b for b, _ in top_brands
                       if b.lower() != lc_brand and b.lower() not in title][:5]
        if len(competitors) >= 4:
            # 类目很拥挤，需要明确差异化
            if any(w in merged for w in [
                "premium", "professional", "best", "unique", "patented",
                "exclusive", "top-rated",
            ]):
                positioning_score = 12
                positioning_rec = (
                    f"竞争激烈（Rufus 提到 {len(competitors)} 个对手），"
                    "已有差异化表述，可进一步量化『和谁比，差在哪』"
                )
            else:
                positioning_score = 5
                positioning_rec = (
                    f"Rufus 提到 {len(competitors)} 个对手品牌："
                    f"{', '.join(competitors[:3])}，"
                    "你的 listing 缺乏明确的差异化语言"
                )
        else:
            positioning_score = 15
            positioning_rec = "类目竞争不算拥挤，当前定位可保持"

    # 结构 / 受众 暂时沿用 expert_suggestions 里的静态审计（给默认分）
    audience_score  = 12       # placeholder, 15 满分
    structure_score = 12       # placeholder, 15 满分

    total = (scene_score + driver_score + audience_score
             + positioning_score + lang_score + structure_score)

    if total >= 80:
        grade = "A — 高度匹配 Rufus / AI 推荐层"
    elif total >= 65:
        grade = "B — 大体匹配，若干维度待补强"
    elif total >= 50:
        grade = "C — 多维度存在明显缺口"
    else:
        grade = "D — 结构与语义在 AI 推荐层极弱"

    recommendations = []
    if scene_gap:
        recommendations.append({
            "priority": "high", "area": "场景覆盖",
            "action": f"把 Rufus 高频场景「{'、'.join(scene_gap[:3])}」加进 title 或 bullet 1",
            "evidence": f"Rufus scene_heatmap 前 5：{scene_top}",
        })
    if driver_gap:
        recommendations.append({
            "priority": "high", "area": "决策因素",
            "action": f"补充 Rufus 高频因素「{'、'.join(driver_gap[:3])}」的 feature → outcome 因果链",
            "evidence": f"Rufus driver_heatmap 前 5：{driver_top}",
        })
    if lang_score < 10:
        recommendations.append({
            "priority": "medium", "area": "买家语言",
            "action": "bullets 融入 Rufus 追问里的自然语言短语，降低语义距离",
            "evidence": f"Rufus top follow-ups: {[fu for fu, _ in top_followups[:3]]}",
        })
    if positioning_rec and positioning_score <= 10:
        recommendations.append({
            "priority": "medium", "area": "竞品定位",
            "action": positioning_rec, "evidence": "见 Rufus top_brands",
        })

    return {
        "total_score": total,
        "max_score": 100,
        "overall_grade": grade,
        "dimensions": {
            "scenario_coverage": {
                "score": scene_score, "max": 20,
                "expected": scene_top, "present": scene_present,
                "gap": scene_gap,
            },
            "decision_drivers": {
                "score": driver_score, "max": 20,
                "expected": driver_top, "present": driver_present,
                "gap": driver_gap,
            },
            "user_language": {
                "score": lang_score, "max": 15,
                "followup_hits": followup_lang_hits,
            },
            "positioning": {
                "score": positioning_score, "max": 15,
                "note": positioning_rec,
            },
            "audience_match":  {"score": audience_score,  "max": 15},
            "ai_readable_structure": {"score": structure_score, "max": 15},
        },
        "recommendations": recommendations,
        "audit_method": "geo-listing-auditor v2 · Rufus evidence-based",
    }


# ── Markdown 报告 ───────────────────────────────────────────────
def _build_markdown(session: dict, parsed_list: list, summary: dict,
                    geo_audit: dict, listing_context: Optional[dict]) -> str:
    asin = session.get("asin", "")
    mode_label = "自动 (CDP)" if session.get("mode") == "auto" else "手动粘贴"
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    captured = session.get("captured_count", 0)
    total    = session.get("total_questions", 0)

    lines = []
    lines += [
        f"# Rufus 调研 + GEO 审计报告 · {asin}",
        "",
        f"> **生成时间**：{now}",
        f"> **采集模式**：{mode_label}",
        f"> **采集覆盖**：{captured} / {total} 个问题",
        f"> **采集原因**：{session.get('reason', '')}",
        "",
    ]

    if listing_context:
        lines += [
            "## 〇、当前 Listing 概览",
            "",
            f"- 标题：{listing_context.get('title', '')[:120]}",
            f"- 品牌：{listing_context.get('brand', '—')}",
            f"- 分类：{listing_context.get('category', '—')}",
            f"- 价格 / 星级：{listing_context.get('price', '—')} / "
            f"{listing_context.get('rating', '—')}",
            "",
        ]

    # GEO 评分
    ga = geo_audit or {}
    dims = ga.get("dimensions", {})
    lines += [
        "## 一、GEO 6 维度评分（基于 Rufus 证据）",
        "",
        f"**总分：{ga.get('total_score', 0)} / 100** — {ga.get('overall_grade', '')}",
        "",
        "| 维度 | 得分 | 备注 |",
        "|---|---|---|",
    ]
    dim_names = {
        "scenario_coverage":     "场景覆盖",
        "decision_drivers":      "决策因素",
        "audience_match":        "人群匹配",
        "positioning":           "竞品定位",
        "user_language":         "买家语言",
        "ai_readable_structure": "结构可读性",
    }
    for key, label in dim_names.items():
        d = dims.get(key, {})
        note = ""
        if d.get("gap"):
            note = f"缺：{', '.join(d['gap'][:3])}"
        elif d.get("note"):
            note = d["note"][:60]
        lines.append(f"| {label} | {d.get('score', 0)}/{d.get('max', '?')} | {note} |")
    lines += [""]

    # 建议
    recs = ga.get("recommendations", [])
    if recs:
        lines += ["## 二、基于 Rufus 证据的优化建议（按优先级）", ""]
        for i, r in enumerate(recs, 1):
            lines += [
                f"### [{r['priority'].upper()}] {i}. {r['area']}",
                "",
                f"- **建议**：{r['action']}",
                f"- **证据**：{r.get('evidence', '')}",
                "",
            ]

    # Rufus 信号汇总
    lines += [
        "## 三、Rufus 数据摘要",
        "",
        f"- 总回答数：{summary.get('non_empty_answers', 0)} / {summary.get('total_answers', 0)}",
        f"- 总字数：{summary.get('total_words', 0)}",
        "",
        "### 高频追问（买家真实搜索意图）",
        "",
    ]
    top_fu = summary.get("top_follow_ups") or []
    if top_fu:
        for fu, cnt in top_fu[:10]:
            lines.append(f"- `{fu}` ×{cnt}")
    else:
        lines.append("_（未采集到 follow-ups）_")
    lines += ["", "### 提及品牌（潜在竞品）", ""]
    top_b = summary.get("top_brands") or []
    if top_b:
        for b, cnt in top_b[:10]:
            lines.append(f"- {b} ×{cnt}")
    else:
        lines.append("_（无）_")
    lines += ["", "### 价格区间", ""]
    top_p = summary.get("top_prices") or []
    if top_p:
        for p, cnt in top_p[:5]:
            lines.append(f"- {p} ×{cnt}")
    else:
        lines.append("_（无）_")
    lines += ["", "### 决策因素热度", ""]
    dh = summary.get("driver_heatmap") or {}
    if dh:
        for k, v in list(dh.items())[:10]:
            lines.append(f"- `{k}` ×{v}")
    else:
        lines.append("_（无）_")
    lines += ["", "### 场景热度", ""]
    sh = summary.get("scene_heatmap") or {}
    if sh:
        for k, v in list(sh.items())[:10]:
            lines.append(f"- `{k}` ×{v}")
    else:
        lines.append("_（无）_")

    lines += ["", "## 四、逐题 Rufus 答案 + 解析", ""]
    for p in parsed_list:
        lines += [
            f"### Q{p['index']}: {p['question']}",
            "",
            f"_Stage: {p.get('stage')}_",
            "",
            "**Rufus 回答原文：**",
            "",
            "```",
            (p.get("raw_text") or "(空)")[:2000],
            "```",
            "",
            f"- 字数：{p.get('word_count', 0)}  ·  句数：{p.get('sentence_count', 0)}",
            f"- Follow-ups：{p.get('follow_ups', [])[:3]}",
            f"- 品牌：{p.get('brands', [])[:5]}",
            f"- 价格：{p.get('prices', [])[:3]}",
            "",
        ]
    lines += [f"_报告生成：{now}_"]
    return "\n".join(lines)
