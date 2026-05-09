"""
Rufus & COSMO Expert Suggestions Engine
========================================
Generates algorithm-optimized listing recommendations from product context:
- Title optimization with COSMO scene/persona embedding
- 5 Bullet Points with compliance scoring (COSMO节点符合度)
- 8 Q&A pairs following the Rufus-friendly framework
- Selling point extraction with cause-effect chains

Based on the Rufus Audit demo model and COSMO/Rufus algorithm playbook.
"""
# Reconstructed from expert_suggestions.pyc (Python 3.14).
# ~750 lines original. All user-facing strings (zh-CN + en), regex patterns,
# scoring thresholds, and bilingual mapping tables are preserved verbatim
# from the bytecode. Control flow is reconstructed from disassembly.

from __future__ import annotations

import re
import json
from pathlib import Path


# =============================================================================
# Title optimization
# =============================================================================

def build_cosmo_title(context: dict) -> dict:
    """Analyze the original product title against COSMO/Rufus best practices,
    using real MCP keyword data to identify gaps and suggest improvements.
    Does NOT hallucinate a new title — only suggests evidence-based changes.
    """
    title = context.get("title", "") or ""
    category = context.get("category", "") or ""
    keywords = context.get("keywords", []) or []
    bullets = context.get("bullets", []) or []
    brand = context.get("brand", "") or ""
    synthetic = context.get("bullets_synthetic", False)

    structure_checks: list[dict] = []
    present_count = 0
    total_checks = 0

    # Check 1: brand prefix
    total_checks += 1
    if brand:
        brand_lower = brand.lower()
        if brand_lower and brand_lower in title.lower():
            present_count += 1
            structure_checks.append({
                "element": "品牌前置",
                "detail": f"品牌「{brand}」已出现",
                "status": "present",
            })
        else:
            structure_checks.append({
                "element": "品牌前置",
                "detail": f"品牌「{brand}」未在标题中出现",
                "status": "missing",
            })

    # Check 2: quantified specs (numbers + units)
    total_checks += 1
    spec_pattern = r"\d+\s*(?:mg|g|kg|oz|lb|lbs|ml|l|inch|in|cm|mm|RPM|W|V|A|mAh|pack|count|ct|piece|pcs|set)"
    if re.search(spec_pattern, title, re.IGNORECASE):
        present_count += 1
        structure_checks.append({
            "element": "量化规格",
            "detail": "含具体数值参数",
            "status": "present",
        })
    else:
        structure_checks.append({
            "element": "量化规格",
            "detail": "缺少量化规格（如尺寸/容量/数量）",
            "status": "missing",
        })

    # Check 3: scene/persona
    total_checks += 1
    scene_words = ["for", "home", "office", "travel", "gym", "daily", "gift",
                   "适合", "家庭", "办公", "送礼", "旅行"]
    if any(w.lower() in title.lower() for w in scene_words):
        present_count += 1
        structure_checks.append({
            "element": "场景/人群",
            "detail": "含使用场景或目标人群",
            "status": "present",
        })
    else:
        structure_checks.append({
            "element": "场景/人群",
            "detail": "缺少使用场景或目标人群定位",
            "status": "missing",
        })

    # Check 4: material/quality
    total_checks += 1
    quality_words = ["premium", "certified", "stainless", "bamboo", "organic",
                     "professional", "优质", "认证", "专业", "不锈钢"]
    if any(w.lower() in title.lower() for w in quality_words):
        present_count += 1
        structure_checks.append({
            "element": "材质/品质",
            "detail": "含材质或品质标识",
            "status": "present",
        })
    else:
        structure_checks.append({
            "element": "材质/品质",
            "detail": "可考虑添加材质/品质关键词",
            "status": "missing",
        })

    # Check 5: keyword density
    total_checks += 1
    title_words = re.findall(r"\b[\w']+\b", title)
    unique_words = set(w.lower() for w in title_words if len(w) > 2)
    if len(unique_words) >= 8:
        present_count += 1
        structure_checks.append({
            "element": "关键词密度",
            "detail": f"约 {len(unique_words)} 个有效词，覆盖良好",
            "status": "present",
        })
    else:
        structure_checks.append({
            "element": "关键词密度",
            "detail": f"约 {len(unique_words)} 个有效词，可增加更多长尾词",
            "status": "missing",
        })

    # Score and grade
    score = int(100 * present_count / total_checks) if total_checks else 0
    if score >= 80:
        grade = "A — 标题结构优秀"
    elif score >= 60:
        grade = "B — 标题结构良好，有优化空间"
    elif score >= 40:
        grade = "C — 标题需要改进"
    else:
        grade = "D — 标题结构严重不足"

    # Suggestions
    suggestions: list[str] = []
    for chk in structure_checks:
        if chk["status"] != "missing":
            continue
        el = chk["element"]
        if el == "量化规格":
            suggestions.append("在标题中加入量化规格（如尺寸、容量、数量），提升搜索结果中的点击率")
        elif el == "场景/人群":
            suggestions.append("添加使用场景或目标人群（如 for Home, Gift for Adults），增强Rufus场景匹配")
        elif el == "品牌前置" and brand:
            suggestions.append(f"将品牌「{brand}」前置到标题开头，提高品牌搜索可见度")

    # MCP keyword gap analysis
    top_keywords = [kw for kw in keywords[:20] if isinstance(kw, dict)]
    keyword_gaps: list[str] = []
    for kw in top_keywords:
        kw_text = kw.get("keyword", "") if isinstance(kw, dict) else str(kw)
        if kw_text and kw_text.lower() not in title.lower():
            keyword_gaps.append(kw_text)
    if keyword_gaps:
        suggestions.append(
            f"标题可融入以下高流量词: {'、'.join(keyword_gaps[:5])}"
        )

    if len(title) < 100:
        suggestions.append("标题偏短，可扩展至150-200字符以覆盖更多长尾搜索词")
    elif not suggestions:
        suggestions.append("标题结构合理，持续监控关键词排名变化即可")

    # Suggested optimized ZH title (template-based)
    brand_part = brand if brand else "产品"
    scene_hint = ""
    for w in ["家庭", "办公", "旅行"]:
        if w in str(bullets) or w in title:
            scene_hint = w
            break
    optimized_zh = f"【{brand_part}】{title.strip()}"
    if scene_hint:
        optimized_zh += f" · 适用多场景({scene_hint})"
    else:
        optimized_zh += " · 适用多场景"
    if not brand:
        optimized_zh = "（需先识别品牌和类目后再生成中文标题建议）"

    # English optimized variant
    en_optimized = title
    if keyword_gaps:
        en_optimized = f"{title} — Perfect for {keyword_gaps[0]}"

    data_note = (
        "真实Amazon标题分析" if not synthetic
        else "基于关键词合成的参考分析"
    )

    # ─────────────────────────────────────────────────────────────────
    # GEO 6 维度审计（追加字段，不破坏现有返回结构）
    # 参考 skills/geo-listing-auditor 的 6 维度 100 分制：
    # 1) Scenario coverage    20 分
    # 2) Audience match       15 分
    # 3) Decision drivers     20 分
    # 4) Positioning / differentiation 15 分
    # 5) User language / GEO semantics 15 分
    # 6) AI-readable structure clarity 15 分
    # ─────────────────────────────────────────────────────────────────
    geo_audit = _build_geo_audit(context, title, bullets, keywords, brand)

    return {
        "original": title,
        "optimized": optimized_zh,
        "en_optimized": en_optimized,
        "cosmo_analysis": {
            "title_score": score,
            "title_grade": grade,
            "present_count": present_count,
            "total_checks": total_checks,
            "structure_checks": structure_checks,
            "keyword_gaps": keyword_gaps,
            "suggestions": suggestions,
            "mcp_keyword_count": len(keywords),
            "improvement": (
                f"基于真实产品标题 + {len(keywords)}个SIF流量词的结构化分析"
                if not synthetic else
                f"基于关键词合成的参考分析 — 专业级"
            ),
        },
        "geo_audit": geo_audit,                       # ← 新增：6 维度评分
        "mcp_validated": not synthetic,
        "mcp_sources": "SIF MCP 关键词信号",
        "mcp_top_keywords": [
            k.get("keyword") if isinstance(k, dict) else str(k)
            for k in keywords[:10]
        ],
        "data_note": data_note,
    }


# =============================================================================
# GEO 6-dimension audit
# =============================================================================

# 每维度的 Expected 点来源：
#   - 来自 Sorftime/SIF 的真实 keyword signals（declining / gaining / top）
#   - 来自 bullets 的语义片段
#   - 来自类目特征词词库
#
# 每维度返回：
#   {
#     "score": 0-20/15,
#     "max":   20/15,
#     "level": "excellent|adequate|weak",
#     "expected": [...],    # 应该出现的要点
#     "present":  [...],    # 标题 + 前置 bullets 中已出现的要点
#     "gap":      [...],    # 缺失或未展开的要点
#     "recommendation": "...",
#   }

def _build_geo_audit(context: dict, title: str, bullets: list,
                     keywords: list, brand: str) -> dict:
    title_lower = (title or "").lower()
    bullets_text = " ".join(str(b) for b in (bullets or [])).lower()
    merged_text  = title_lower + " | " + bullets_text

    # keyword list: 统一小写化
    kw_strs = []
    for kw in keywords or []:
        s = kw.get("keyword") if isinstance(kw, dict) else str(kw)
        if s:
            kw_strs.append(s.lower())

    # —— 6 维度各自一个评估器
    scenario    = _audit_scenario(merged_text, title_lower, kw_strs)
    audience    = _audit_audience(merged_text, title_lower, bullets)
    drivers     = _audit_decision_drivers(merged_text, title_lower, bullets, kw_strs)
    positioning = _audit_positioning(merged_text, title_lower, brand)
    user_lang   = _audit_user_language(title_lower, bullets)
    structure   = _audit_ai_readable(title, bullets)

    total_score = (scenario["score"] + audience["score"] + drivers["score"]
                   + positioning["score"] + user_lang["score"] + structure["score"])

    if total_score >= 80:
        overall_grade = "A — 标题 & 列表在 Rufus / AI 推荐层高度适配"
    elif total_score >= 65:
        overall_grade = "B — 基础结构合理，若干维度待补强"
    elif total_score >= 50:
        overall_grade = "C — 多维度存在明显缺口，需重点优化"
    else:
        overall_grade = "D — 结构与语义在 AI 推荐层极弱"

    # 汇总 / 排序 recommendations（按优先级）
    all_recs = []
    for dim_key, dim in (
        ("scenario", scenario), ("audience", audience),
        ("decision_drivers", drivers), ("positioning", positioning),
        ("user_language", user_lang), ("ai_readable", structure),
    ):
        if dim.get("recommendation"):
            all_recs.append({
                "dimension": dim_key,
                "priority": "high" if dim["level"] == "weak" else (
                    "medium" if dim["level"] == "adequate" else "low"),
                "where": dim.get("where", "title / bullets"),
                "what": dim["recommendation"],
                "why": dim.get("why", ""),
            })
    all_recs.sort(key=lambda r: {"high": 0, "medium": 1, "low": 2}[r["priority"]])

    return {
        "total_score": total_score,
        "max_score": 100,
        "overall_grade": overall_grade,
        "dimensions": {
            "scenario_coverage": scenario,
            "audience_match": audience,
            "decision_drivers": drivers,
            "positioning": positioning,
            "user_language": user_lang,
            "ai_readable_structure": structure,
        },
        "recommendations": all_recs,
        "audit_method": "geo-listing-auditor v1 · 6 维度 100 分制",
    }


def _audit_scenario(merged: str, title: str, kw_strs: list) -> dict:
    """场景覆盖（20 分）：产品被用在什么情况 / 环境 / 场合"""
    scenario_signals = {
        "家庭/日常": ["home", "house", "daily", "family", "everyday", "indoor"],
        "办公/工作": ["office", "work", "desk", "workspace", "professional use"],
        "旅行/便携": ["travel", "portable", "on-the-go", "commute", "trip"],
        "健身/户外": ["gym", "outdoor", "hiking", "camp", "sport"],
        "厨房/烹饪": ["kitchen", "cooking", "meal", "dining"],
        "浴室/清洁": ["bath", "shower", "cleaning", "laundry"],
        "送礼":       ["gift", "present", "holiday"],
        "车载":       ["car", "auto", "vehicle"],
        "婴儿/儿童":  ["baby", "infant", "toddler", "kid", "children"],
        "宠物":       ["pet", "dog", "cat"],
    }

    expected = []
    # 结合关键词信号：keyword 里频繁出现的"场景类"词
    for kw in kw_strs[:20]:
        for sc, needles in scenario_signals.items():
            if any(n in kw for n in needles):
                expected.append(sc)
                break
    expected = list(dict.fromkeys(expected))  # dedup, preserve order
    if not expected:
        # 没有从关键词里识别出具体场景 → 给一个通用期望
        expected = ["日常使用场景"]

    present = []
    for sc, needles in scenario_signals.items():
        if sc in expected and any(n in merged for n in needles):
            present.append(sc)

    gap = [x for x in expected if x not in present]

    ratio = len(present) / max(1, len(expected))
    score = int(round(ratio * 20))
    # 标题优先：场景出现在标题比出现在 bullets 权重更高
    title_hits = sum(1 for sc in present
                     if any(n in title for n in scenario_signals.get(sc, [])))
    if present and title_hits == 0:
        score = max(0, score - 3)  # 只在 bullets 里出现 → 扣 3 分

    level = "excellent" if ratio >= 0.75 else ("adequate" if ratio >= 0.4 else "weak")
    rec = ""
    why = ""
    if gap:
        rec = (f"将场景「{gap[0]}」加进标题（不在标题的场景，Rufus 更难识别为推荐候选）"
               if title_hits == 0 else
               f"标题已有场景，bullets 可进一步展开「{gap[0]}」的具体用法")
        why = "Rufus/COSMO 把场景视为 used_for 关系，场景缺失会让 AI 推荐系统难以将产品匹配到买家的真实 query"
    return {
        "score": score, "max": 20, "level": level,
        "expected": expected, "present": present, "gap": gap,
        "recommendation": rec, "why": why, "where": "title",
    }


def _audit_audience(merged: str, title: str, bullets: list) -> dict:
    """人群匹配（15 分）：目标人群 / 场景里的买家画像"""
    audience_map = {
        "初学者":       ["beginner", "novice", "first-time", "easy for new"],
        "专业人士":     ["professional", "pro", "commercial", "industrial", "studio"],
        "预算敏感":     ["budget", "affordable", "value", "cheap", "economical"],
        "高端 / 品质":  ["premium", "luxury", "high-end", "pro-grade"],
        "小空间居住者": ["apartment", "small space", "dorm", "compact living"],
        "年长者":       ["seniors", "elderly", "grandparent"],
        "儿童家庭":     ["family", "kids", "child-safe", "children"],
        "礼物场景":     ["gift", "present"],
        "通用成人":     ["adults", "men", "women"],
    }

    expected = []
    # 简单从关键词与标题推断 1-2 类画像
    if any(w in merged for w in ["for home", "household", "daily"]):
        expected.append("通用成人")
    if any(w in merged for w in ["professional", "heavy-duty", "commercial"]):
        expected.append("专业人士")
    if any(w in merged for w in ["gift"]):
        expected.append("礼物场景")
    if not expected:
        expected = ["通用成人"]
    expected = list(dict.fromkeys(expected))

    present = []
    for p, needles in audience_map.items():
        if p in expected and any(n in merged for n in needles):
            present.append(p)

    gap = [x for x in expected if x not in present]
    ratio = len(present) / max(1, len(expected))
    score = int(round(ratio * 15))
    level = "excellent" if ratio >= 0.75 else ("adequate" if ratio >= 0.4 else "weak")

    rec = ""
    why = ""
    if gap:
        rec = f"在 bullet 里明确目标人群「{gap[0]}」（"\
              f"例：Perfect for [gap] 或 Designed for [gap]）"
        why = "Rufus 的 used_for / isA 关系会把『谁来用』当作强匹配信号"
    return {
        "score": score, "max": 15, "level": level,
        "expected": expected, "present": present, "gap": gap,
        "recommendation": rec, "why": why, "where": "bullet",
    }


def _audit_decision_drivers(merged: str, title: str, bullets: list,
                            kw_strs: list) -> dict:
    """决策因素（20 分）：买家挑产品时看的核心因素"""
    drivers = {
        "尺寸/规格": ["size", "inch", "cm", "length", "width", "height",
                     "\"", "'", "dimension"],
        "材质":     ["material", "stainless", "steel", "aluminum", "rubber",
                     "silicone", "bamboo", "wood", "cotton", "leather"],
        "耐用/质量": ["durable", "sturdy", "heavy-duty", "long-lasting",
                     "built to last", "quality"],
        "易用":     ["easy", "simple", "one-touch", "quick", "effortless",
                     "user-friendly"],
        "清洁/护理": ["washable", "dishwasher-safe", "easy to clean",
                     "reusable"],
        "功能数量":  ["3-in-1", "2-in-1", "multi", "all-in-one", "combo"],
        "安全":     ["safe", "bpa-free", "non-toxic", "certified", "food-grade"],
        "价格/性价比": ["value", "affordable", "budget", "cost-effective"],
    }

    # 需要覆盖的 expected：关键词里出现的 driver 类词
    expected = []
    for d, needles in drivers.items():
        if any(any(n in kw for n in needles) for kw in kw_strs[:15]):
            expected.append(d)
        elif d in ("尺寸/规格", "材质", "耐用/质量"):  # 常识高优先
            expected.append(d)
    expected = list(dict.fromkeys(expected))[:6]

    present = []
    for d in expected:
        if any(n in merged for n in drivers[d]):
            present.append(d)

    gap = [x for x in expected if x not in present]
    ratio = len(present) / max(1, len(expected))
    score = int(round(ratio * 20))
    level = "excellent" if ratio >= 0.75 else ("adequate" if ratio >= 0.4 else "weak")

    rec = ""
    why = ""
    if gap:
        rec = (f"补上买家最关心的决策因素：{('、'.join(gap[:3]))} —— "
               "建议在 bullets 里给出『feature → user outcome』的因果链")
        why = "Rufus 的 cause 关系依赖『功能 → 结果』的明确连接，缺失会拿不到决策权重"
    return {
        "score": score, "max": 20, "level": level,
        "expected": expected, "present": present, "gap": gap,
        "recommendation": rec, "why": why, "where": "bullet",
    }


def _audit_positioning(merged: str, title: str, brand: str) -> dict:
    """定位差异化（15 分）：在同品类里占据什么『角色』"""
    positions = {
        "紧凑 / 省空间":  ["compact", "space-saving", "foldable", "small"],
        "初学者友好":     ["beginner-friendly", "easy for beginners",
                         "simple to use"],
        "专业级":         ["professional", "pro-grade", "heavy-duty",
                         "commercial"],
        "高端 / 高性价比": ["premium", "luxury", "best value", "top quality"],
        "多功能":         ["multi-function", "3-in-1", "2-in-1", "versatile",
                         "all-in-one"],
        "易维护":         ["low-maintenance", "easy-clean", "reusable",
                         "washable"],
    }

    present = []
    for p, needles in positions.items():
        if any(n in merged for n in needles):
            present.append(p)

    # 期望：至少 1 个明确定位
    expected = ["至少 1 个明确的品类定位"]
    ratio = 1.0 if present else 0.0
    score = 15 if present else 5
    level = "excellent" if len(present) >= 2 else ("adequate" if present else "weak")

    rec = ""
    why = ""
    if not present:
        rec = "标题 / bullets 缺乏明确『角色定位』—— 需要给买家一个『为什么选它』的一句话答案"
        why = "定位模糊的产品会被 Rufus 与同类合并推荐，拿不到『推荐 slot』"
    elif len(present) == 1:
        rec = f"已有定位「{present[0]}」，可再强化一个辅助定位（如多功能 / 易维护）"
        why = "双重定位能让产品在多个 Rufus 推荐候选槽里都有机会被命中"
    return {
        "score": score, "max": 15, "level": level,
        "expected": expected, "present": present, "gap": [] if present else expected,
        "recommendation": rec, "why": why, "where": "title",
    }


def _audit_user_language(title: str, bullets: list) -> dict:
    """用户语言 / GEO 语义（15 分）：是否用买家自然语言表达"""
    bullets_text = " ".join(str(b) for b in (bullets or [])).lower()

    # 信号：自然语言副词 / 问句 / 口语感
    natural_signals = [
        "perfect for", "ideal for", "great for", "designed for",
        "you can", "you'll", "so you", "never worry", "say goodbye",
        "no more", "without", "makes it easy", "easy to",
    ]
    natural_hits = sum(1 for s in natural_signals if s in bullets_text)

    # 反信号：纯参数堆砌 / 过度大写 / SEO-ish 短句
    caps_ratio = sum(1 for c in title if c.isupper()) / max(1, len(title))
    seo_stuffing = title.count("|") + title.count("&")

    score = 0
    if natural_hits >= 3:
        score += 10
    elif natural_hits >= 1:
        score += 6
    # 不滥用 caps 和分隔符
    if caps_ratio < 0.35:
        score += 3
    if seo_stuffing <= 2:
        score += 2

    level = "excellent" if score >= 12 else ("adequate" if score >= 7 else "weak")

    present = []
    if natural_hits >= 1:
        present.append(f"含 {natural_hits} 处自然语言表达")
    if caps_ratio < 0.35:
        present.append("大小写比例合理")
    gap = []
    rec = ""
    why = ""
    if natural_hits == 0:
        gap.append("bullets 缺乏『自然口语句式』")
        rec = "bullets 以 Perfect for… / No more… / Designed for… 开头重写 1-2 条"
        why = "Rufus 用的是买家自然语言做 intent 匹配，过硬的参数句式会降低语义命中率"
    elif seo_stuffing > 3:
        gap.append("标题分隔符过多，像 SEO 堆砌")
        rec = "标题精简到 1-2 个 | 或 : 分隔，让主信息更突出"
        why = "过度分隔会让 Rufus 把标题解析为碎片而非完整语义"
    return {
        "score": min(score, 15), "max": 15, "level": level,
        "expected": ["自然语言表达", "简洁不过度分隔"],
        "present": present, "gap": gap,
        "recommendation": rec, "why": why, "where": "bullet",
    }


def _audit_ai_readable(title: str, bullets: list) -> dict:
    """AI 可读结构（15 分）：AI 能否快速理解这是什么"""
    score = 0
    present = []
    gap = []

    # 标题长度：150-200 字符是甜区
    tlen = len(title)
    if 100 <= tlen <= 200:
        score += 4
        present.append(f"标题长度 {tlen} 字符，在可读区间")
    else:
        gap.append(f"标题 {tlen} 字符 —— 过短难覆盖长尾，过长易被 AI 截断")

    # bullets 完整性：应该有 5 条
    bullet_count = sum(1 for b in (bullets or []) if b and len(str(b).strip()) > 20)
    if bullet_count >= 5:
        score += 4
        present.append(f"bullet 数 {bullet_count}（推荐 5 条）")
    elif bullet_count >= 3:
        score += 2
        gap.append(f"bullet 只有 {bullet_count} 条，建议补齐到 5 条")
    else:
        gap.append(f"bullet 数严重不足（仅 {bullet_count} 条）")

    # bullet 开头一致性：如都用【】/ [] / 大写开头
    open_patterns = sum(
        1 for b in (bullets or [])
        if re.match(r"^\s*[\[【（(]", str(b)) or (str(b).strip()[:1].isupper())
    )
    if bullets and open_patterns / max(1, len(bullets)) >= 0.8:
        score += 3
        present.append("bullet 开头统一（结构易于 AI 解析）")
    elif bullets:
        gap.append("bullet 开头格式不统一")

    # bullet 长度：每条 150-300 字符左右最佳
    if bullets:
        avg = sum(len(str(b)) for b in bullets) / len(bullets)
        if 120 <= avg <= 400:
            score += 4
            present.append(f"bullet 平均长度 {int(avg)} 字符，适中")
        elif avg > 400:
            gap.append(f"bullet 平均 {int(avg)} 字符过长，AI 摘要会抓不住重点")
        else:
            gap.append(f"bullet 平均 {int(avg)} 字符过短，信息密度不足")

    level = "excellent" if score >= 12 else ("adequate" if score >= 8 else "weak")
    rec = ""
    why = ""
    if score < 12 and gap:
        rec = f"修正：{gap[0]}"
        why = "AI 可读结构是 Rufus 解析的地基，结构混乱会直接压低所有其他维度"
    return {
        "score": min(score, 15), "max": 15, "level": level,
        "expected": ["标题 100-200 字符", "5 条 bullet", "开头统一", "长度适中"],
        "present": present, "gap": gap,
        "recommendation": rec, "why": why, "where": "bullets",
    }


# =============================================================================
# Helpers: attribute / persona / scene extraction
# =============================================================================

def _extract_brand(context: dict) -> str:
    """Extract brand name from SIF keywords or title."""
    sif_kw = context.get("sif_keywords", []) or []
    title = context.get("title", "") or ""
    if sif_kw:
        top_kw = sif_kw[0].get("keyword", "") if isinstance(sif_kw[0], dict) else ""
        words = top_kw.split()
        if words and words[0].upper() not in ("MAGNESIUM", "CALCIUM", "VITAMIN", "ZINC", "IRON"):
            if words[0].upper() in title.upper():
                return words[0].title()

    # Check against known brand list (first capitalized word in title > 2 chars)
    known_brands: list[str] = []
    for b in known_brands:
        if b.upper() in title.upper():
            return b.title()

    parts = title.split()
    if parts and parts[0][0].isupper() and len(parts[0]) > 2:
        return parts[0]
    return ""


def _extract_core_function(context: dict, lang: str = "zh") -> str:
    """Extract core product function/type (ZH + EN)."""
    title = context.get("title", "") or ""
    bullets = context.get("bullets", []) or []
    combined = (title + " " + " ".join(str(b) for b in bullets)).lower()

    if re.search(r"magnesium|镁", combined):
        forms = re.search(r"(\d+)\s*(?:in\s*1|forms? of)", combined, re.IGNORECASE)
        dosage = re.search(r"(\d+)\s*mg", combined, re.IGNORECASE)
        if lang == "en":
            if forms:
                return f"{forms.group(1)}-in-1 Magnesium Complex Supplement"
            if dosage:
                return f"Magnesium Supplement {dosage.group(1)}mg"
            return "Magnesium Complex Supplement"
        # zh
        if forms:
            return f"{forms.group(1)}合1镁复合补充剂"
        if dosage:
            return f"高吸收镁补充剂 {dosage.group(1)}mg"
        return "镁复合补充剂"

    return "Product" if lang == "en" else "产品"


def _extract_persona_bilingual(context: dict) -> tuple[str, str]:
    """Extract target persona with ZH and EN versions."""
    title = context.get("title", "") or ""
    bullets = context.get("bullets", []) or []
    combined = (title + " " + " ".join(str(b) for b in bullets)).lower()

    persona_map = [
        (r"上班族|通勤|出差|商务|commut|business|office|worker", "上班族与商务人士", "Professionals & Commuters"),
        (r"运动员|健身|运动|athlete|fitness|gym|workout|active", "运动健身人群", "Active Adults & Athletes"),
        (r"老人|老年|senior|elderly|aging", "老年人", "Seniors"),
        (r"婴儿|宝宝|儿童|小孩|baby|kid|child|infant|toddler", "婴幼儿家庭", "Families with Children"),
        (r"宠物|pet|dog|cat", "宠物家庭", "Pet Owners"),
        (r"旅行|travel|trip|journey", "旅行者", "Travelers"),
        (r"学生|student|college|school", "学生群体", "Students"),
    ]
    for pat, zh, en in persona_map:
        if re.search(pat, combined):
            return zh, en
    return "男女成人", "Adult Men & Women"


def _extract_key_spec(context: dict) -> str:
    """Extract key spec/strength for Chinese title."""
    title = context.get("title", "") or ""
    bullets = context.get("bullets", []) or []
    combined = title + " " + " ".join(str(b) for b in bullets)
    specs: list[str] = []

    dosage = re.search(r"(\d+)\s*mg", combined, re.IGNORECASE)
    if dosage:
        specs.append(f"{dosage.group(1)}mg")
    forms = re.search(r"(\d+)\s*(?:in\s*1|forms? of|合\d+)", combined, re.IGNORECASE)
    if forms:
        specs.append(f"{forms.group(1)}合1")
    supply = re.search(r"(\d+)[-\s]*day\s*supply", combined, re.IGNORECASE)
    if supply:
        specs.append(f"{supply.group(1)}天供应")
    return " ".join(specs) if specs else ""


def _extract_key_spec_en(context: dict) -> str:
    """Extract key spec for English title."""
    title = context.get("title", "") or ""
    bullets = context.get("bullets", []) or []
    combined = title + " " + " ".join(str(b) for b in bullets)
    specs: list[str] = []

    dosage = re.search(r"(\d+)\s*mg", combined, re.IGNORECASE)
    if dosage:
        specs.append(f"{dosage.group(1)}mg")
    forms = re.search(r"(\d+)\s*(?:in\s*1|forms? of)", combined, re.IGNORECASE)
    if forms:
        specs.append(f"{forms.group(1)}-in-1")
    supply = re.search(r"(\d+)[-\s]*day\s*supply", combined, re.IGNORECASE)
    if supply:
        specs.append(f"{supply.group(1)}-Day Supply")
    return " ".join(specs) if specs else ""


def _extract_scenes_bilingual(context: dict) -> list[tuple[str, str]]:
    """Extract usage scenes (ZH + EN)."""
    title = context.get("title", "") or ""
    bullets = context.get("bullets", []) or []
    combined = (title + " " + " ".join(str(b) for b in bullets)).lower()

    scene_map = [
        (r"睡眠|失眠|sleep|insomnia|relaxation", "睡前放松", "Sleep & Relaxation"),
        (r"疲劳|肌肉|恢复|muscle|fatigue|recovery|sore", "运动恢复", "Post-Workout Recovery"),
        (r"精力|能量|energy|boost", "日常精力补充", "Daily Energy Support"),
        (r"旅行|出差|travel|trip|journey", "旅行便携", "Travel Friendly"),
        (r"家庭|家居|home|family|household", "家庭日常", "Home & Family"),
        (r"送礼|礼物|gift|present", "送礼佳品", "Gift Ready"),
        (r"全身|whole[- ]body|wellness", "全身健康", "Whole-Body Wellness"),
    ]
    out: list[tuple[str, str]] = []
    for pat, zh, en in scene_map:
        if re.search(pat, combined):
            out.append((zh, en))
    if not out:
        out.append(("日常保健", "Daily Wellness"))
    return out


def _extract_accessories(context: dict) -> str:
    """Extract meaningful accessories/included items."""
    title = context.get("title", "") or ""
    bullets = context.get("bullets", []) or []
    combined = title + " " + " ".join(str(b) for b in bullets)
    m = re.search(
        r"(?:with|include(?:s|d)?)\s+(?:a\s+)?"
        r"(magnetic\s+nozzle|carrying\s+case|travel\s+pouch|sleep\s+mask|"
        r"diffuser|storage\s+bag|free\s+\w+)",
        combined, re.IGNORECASE,
    )
    return m.group(1).strip() if m else ""


def _detect_problem_en(context: dict) -> str:
    """Detect the problem the product solves, in English."""
    title = context.get("title", "") or ""
    bullets = context.get("bullets", []) or []
    combined = (title + " " + " ".join(str(b) for b in bullets)).lower()
    problem_map = [
        (r"frizz|dry\s*hair|split\s*end", "frizzy & dry hair"),
        (r"muscle|fatigue|recovery|sore", "muscle fatigue & recovery"),
        (r"sleep|insomnia", "poor sleep quality"),
        (r"busy\s*morning|rush|quick", "rushed mornings"),
    ]
    for pat, en in problem_map:
        if re.search(pat, combined):
            return en
    return ""


# =============================================================================
# Bullet points
# =============================================================================

_BULLET_TEMPLATES = [
    {
        "type": "即时需求与痛点 (Scenario & Pain-points)",
        "cosmo_node": "场景(赶时间/需求紧迫) → 功能(核心能力) → 结果(量化时间/效果)",
        "format": "[量化结果 + 场景价值] → 告别传统痛点。采用[核心技术]...",
        "en_format": "[QUANTIFIED RESULT FOR SCENARIO] — Say goodbye to [pain point]. Powered by [core tech]...",
    },
    {
        "type": "效果与质感 (Effect & Quality)",
        "cosmo_node": "常识疑虑(会不会XX?) → 原理(技术支撑) → 效果(长期收益)",
        "format": "[效果承诺 + 原理支撑] → 担心[常识疑虑]？[技术]释放[量化指标]...",
        "en_format": "[EFFECT PROMISE] — Worried about [common concern]? The [tech] delivers [quantified result]...",
    },
    {
        "type": "便携与场景适配 (Portability & Scenarios)",
        "cosmo_node": "常识具象(类比日常物品) → 多场景覆盖 → 便携价值",
        "format": "[常识具象化 + 多场景覆盖] → 仅重[量化](约[日常类比])...适合[场景A]/[场景B]",
        "en_format": "[CONCRETE COMPARISON + MULTI-SCENE] — Weighing only [X] (about [daily item])... Perfect for [scene A]/[scene B]",
    },
    {
        "type": "常识性后顾之忧 (Common-Sense Concerns)",
        "cosmo_node": "安全排雷(怕不怕XX?) → 技术保障(监测频率) → 兼容人群(婴儿/宠物)",
        "format": "[安全排雷 + 兼容人群] → 害怕[安全疑虑]？[智能技术]每秒[X]次监测...适合[敏感人群]",
        "en_format": "[SAFETY ASSURANCE FOR VULNERABLE GROUPS] — Afraid of [safety concern]? [Smart tech] monitors [X] times/sec... Safe for [sensitive groups]",
    },
    {
        "type": "信任闭环 (Trust Loop)",
        "cosmo_node": "认证/背书 → 礼品属性 → 售后保障(时间+响应速度)",
        "format": "[认证背书 + 礼品场景 + 售后承诺] → 通过[认证]...精美包装适合[节日/场景]送礼...提供[X]天无忧[换新/退款]",
        "en_format": "[CERTIFIED SAFETY & GIFT READY] — [Certification] approved... Premium gift packaging for [occasion]... [X]-day worry-free [replacement/refund]",
    },
]


def build_cosmo_bullets(context: dict) -> dict:
    """Build 5 COSMO-compliant bullet points with compliance scores."""
    bullets = context.get("bullets", []) or []
    title = context.get("title", "") or ""
    category = (context.get("category", "") or "").lower()

    results: list[dict] = []
    for i, tpl in enumerate(_BULLET_TEMPLATES):
        original = bullets[i] if i < len(bullets) else "(缺失)"
        score = _score_bullet(str(original))
        suggestion_zh, suggestion_en = _generate_bullet_suggestion(i, context)
        results.append({
            "index": i + 1,
            "type": tpl["type"],
            "cosmo_node": tpl["cosmo_node"],
            "format": tpl["format"],
            "en_format": tpl["en_format"],
            "original": original,
            "cosmo_score": score,
            "suggestion_zh": suggestion_zh,
            "zh": suggestion_zh,
            "suggestion_en": suggestion_en,
            "en": suggestion_en,
        })

    overall_score = int(sum(r["cosmo_score"] for r in results) / len(results))
    summary = _bullet_summary(overall_score, results)

    return {
        "bullets": results,
        "overall_score": overall_score,
        "cosmo_score": overall_score,
        "summary": summary,
    }


def _score_bullet(bullet_text: str) -> int:
    """Score a bullet's COSMO compliance (0-100)."""
    if bullet_text == "(缺失)":
        return 0
    score = 15
    text_lower = bullet_text.lower()

    # Has quantified data
    if re.search(r"\d+", bullet_text):
        score += 25
    # Has cause-effect markers
    if re.search(
        r"因为|由于|采用|通过|配备|内置|because|powered by|with|featuring|equipped",
        text_lower,
    ):
        score += 20
    # Has result/benefit markers
    if re.search(
        r"可以|能够|确保|提供|帮助|改善|减少|增加|提升|delivers|provides|ensures|helps|improves|reduces|boosts",
        text_lower,
    ):
        score += 20
    # Has length sufficient
    if len(bullet_text) >= 80:
        score += 10
    # Has scene/persona
    if re.search(r"适合|for\s+(home|office|travel|gym|daily)", text_lower):
        score += 10
    return min(100, score)


def _generate_bullet_suggestion(index: int, context: dict) -> tuple[str, str]:
    """Generate a bullet suggestion following the COSMO template pattern."""
    title = context.get("title", "") or ""
    bullets = context.get("bullets", []) or []
    category = context.get("category", "") or ""
    combined = title + " " + " ".join(str(b) for b in bullets)

    # Check for quantified specs in original content
    has_qty = bool(re.search(
        r"\d+[\.\d]*\s*(?:mg|g|kg|oz|lb|lbs|ml|l|inch|in|cm|mm|RPM|m/s|dB|%|倍|x)",
        combined,
    ))
    is_supp = bool(re.search(r"supplement|vitamin|magnesium", combined, re.IGNORECASE))

    zh_templates = [
        "【核心卖点】高效解决用户的核心需求。采用" +
        ("先进专业技术" if has_qty else "先进技术") +
        "，" + ("显著提升使用体验(实测数据)" if has_qty else "显著提升使用体验") +
        "，让您告别传统产品的低效与不便，为您节省宝贵时间。",

        "【提升效果，看得见的改变】担心效果不明显？" +
        ("我们采用优质原料与精密工艺" if is_supp else "我们采用优质原料与精密工艺") +
        "，(实测)坚持使用可显著改善。" +
        ("经实验室验证，有效提升产品性能与用户体验" if has_qty
         else "从根源解决您的困扰") + "。",

        "【轻巧便捷，随时随地】精心设计的紧凑机身，轻松放入包中。"
        "无论居家、办公还是旅行，都是您的理想选择。人体工学设计让长时间使用也不会感到疲劳。",

        "【安全可靠，全家安心】配备智能保护系统，通过严格质量检测，"
        "多重安全防护。低噪音/低辐射设计，即使在安静环境中使用也不会打扰他人，"
        "对敏感人群同样友好，特别适合有儿童和宠物的家庭。",

        "【品质认证，无忧售后】通过国际安全认证（权威机构检测），"
        "精美包装使其成为节日送礼（自用送人）的绝佳选择。"
        "我们提供365天无忧换新服务，客服团队12小时内响应您的任何疑问，让您购买无忧。",
    ]

    en_templates = [
        "[FAST & EFFECTIVE FOR DAILY USE] — Say goodbye to inconvenience. "
        "Powered by advanced technology. Delivers premium performance, "
        "ensuring you get the best results every time.",

        "[VISIBLE IMPROVEMENT YOU CAN TRUST] — Worried about effectiveness? "
        + ("Our premium formula" if is_supp else "Our precision engineering")
        + " ensures "
        + ("optimal absorption and results" if is_supp else "consistent, reliable performance")
        + ". Lab-tested for quality assurance.",

        "[COMPACT & PORTABLE FOR ANY LIFESTYLE] — Designed with portability in mind, "
        "it fits effortlessly into your bag. Perfect for home, office, travel, or gym use. "
        "The ergonomic design ensures comfortable handling during extended use.",

        "[SAFE & RELIABLE FOR THE WHOLE FAMILY] — Equipped with intelligent safety features "
        "and rigorous quality testing. Low-noise operation won't disturb others, "
        "making it ideal for households with children and pets. Peace of mind in every use.",

        "[CERTIFIED QUALITY & WORRY-FREE WARRANTY] — Safety certified and premium packaged — "
        "an excellent gift choice. We offer a worry-free replacement service, "
        "with our support team responding within 12 hours to any concerns.",
    ]
    return zh_templates[index], en_templates[index]


def _bullet_summary(overall_score: int, results: list[dict]) -> str:
    """Generate summary analysis of bullet optimization."""
    if overall_score < 40:
        return ("严重缺乏因果推理(Cause-Effect)结构。当买家向Rufus提问复合查询时，"
                "AI不会将其作为首选答案。建议全面重构五点描述。")
    if overall_score < 60:
        return ("语义密度偏低。部分bullet有场景意识但缺乏完整的痛点→机制→结果→边界链路。"
                "建议重点优化得分最低的bullet。")
    if overall_score < 80:
        return ("整体结构良好。部分bullet可增强常识疑虑解答和信任闭环。"
                "建议补充量化数据和兼容人群信息。")
    return ("COSMO节点覆盖完整。五条bullet均具备完整的因果推理链路，"
            "Rufus可高效抓取并匹配复合查询意图。")


# =============================================================================
# Q&A
# =============================================================================

def build_rufus_qa(context: dict) -> dict:
    """Build 8 Rufus-optimized Q&A pairs covering core purchase concerns."""
    title = context.get("title", "this product")
    category = context.get("category", "general")
    bullets = context.get("bullets", []) or []
    price = context.get("price", "")

    qa_pairs: list[dict] = []

    # 1. Core functionality
    qa_pairs.append({
        "q_zh": f"关于{title}的核心功能与使用效果",
        "q_en": f"About the core functionality and effectiveness of this {category}",
        "a_zh": (
            f"结论是：{title}专为解决{category}核心需求而设计。"
            "具体来说：1) 采用优质原料与先进工艺，确保卓越的产品性能；"
            "2) 经过严格质量检测，每项功能均经过实测验证，使用效果显著；"
            "3) 适用于日常使用场景，能为用户带来切实的改善体验。"
            "我们建议按照产品说明坚持使用，以获得最佳效果。"
        ),
        "a_en": (
            f"Yes, {title} is specifically designed to address core {category} needs. "
            "Specifically: 1) It uses premium materials and advanced processes to ensure superior performance; "
            "2) Each feature has been tested and validated for real-world effectiveness; "
            "3) It's suitable for daily use scenarios, delivering tangible improvements. "
            "We recommend following product instructions consistently for optimal results."
        ),
    })

    # 2. Hidden costs
    has_accessories = "accessory" in str(bullets).lower() or "include" in str(bullets).lower()
    qa_pairs.append({
        "q_zh": f"关于{title}的隐藏费用与后续成本",
        "q_en": f"About hidden costs and ongoing expenses for this {category}",
        "a_zh": (
            f"结论是：购买{title}后无需额外支付隐藏费用。具体来说：1) "
            + ("产品包含所有必需配件，无需额外购买" if has_accessories
               else "包装内已包含完整配件套装")
            + "；2) 无需付费订阅或软件服务费即可使用全部功能；3) "
            + (f"产品定价${price}" if price else "产品定价透明")
            + "，长期使用成本极低。我们建议购买时确认包装清单，确保包含您需要的所有配件。"
        ),
        "a_en": (
            f"No, there are no hidden costs after purchasing {title}. "
            "Specifically: 1) The product includes all necessary accessories — no additional purchases required; "
            "2) No paid subscriptions or software fees needed to access all features; 3) "
            + (f"Priced at ${price}" if price else "Transparent pricing")
            + " with extremely low long-term ownership costs. "
            "We recommend checking the package contents upon purchase."
        ),
    })

    # 3. Compatibility and ease of use
    qa_pairs.append({
        "q_zh": f"关于{title}的兼容性与使用便捷性",
        "q_en": f"About compatibility and ease of use for this {category}",
        "a_zh": (
            f"{title}设计简洁，开箱即用。具体来说："
            "1) 无需复杂安装或专业工具，普通用户即可在几分钟内完成设置；"
            "2) 兼容主流使用环境和场景，适应性强；"
            "3) 附带详细的中英文使用说明书，以及在线客服支持。"
            "例如，首次使用的用户可参考快速入门指南，在3分钟内完成基本设置。"
        ),
        "a_en": (
            f"{title} is designed for plug-and-play simplicity. Specifically: "
            "1) No complex installation or professional tools required — setup takes just minutes; "
            "2) Compatible with mainstream environments and scenarios; "
            "3) Includes detailed user manual and online customer support. "
            "For instance, first-time users can complete basic setup within 3 minutes following the quick-start guide."
        ),
    })

    # 4. Durability
    qa_pairs.append({
        "q_zh": f"关于{title}的质量耐用性与使用极限",
        "q_en": f"About durability limits and quality for this {category}",
        "a_zh": (
            f"{title}采用高品质材料制造（严格品控标准），日常使用完全可靠，但也存在合理的使用边界。"
            "具体来说：1) 产品经过多项质量检测，确保在正常使用条件下的稳定表现"
            "（核心部件经过严格耐久性测试）；"
            "2) 请注意遵循使用说明中的注意事项（如避免极端温度/潮湿环境）；"
            "3) 外壳具有日常抗摔耐磨能力，但不可故意暴力破坏。"
            "如果需要更专业的使用场景，我们建议搭配相应的保护配件。"
        ),
        "a_en": (
            f"{title} is built with high-quality materials and rigorous quality standards "
            "and is fully reliable for daily use, though reasonable limits apply. Specifically: "
            "1) The product has passed multiple quality tests for stable performance under normal conditions "
            "(core components have undergone strict durability testing); "
            "2) Please follow usage guidelines (e.g., avoid extreme temperatures/moisture); "
            "3) The outer shell withstands daily drops and wear but cannot survive intentional abuse. "
            "We recommend protective accessories for more demanding scenarios."
        ),
    })

    # 5. Battery / endurance
    needs_recharge = any(k in str(bullets).lower() for k in ("recharge", "battery", "charge"))
    qa_pairs.append({
        "q_zh": f"关于{title}的续航/持续使用能力",
        "q_en": f"About battery life / continuous use capability",
        "a_zh": (
            f"{title}在正常使用条件下具有出色的续航表现。具体来说："
            "1) 单次充足准备可满足日常使用需求"
            "（根据实测数据，可持续工作满足全天候使用）；"
            "2) " + ("充电/补充" if needs_recharge else "准备工作") + "快速便捷；"
            "3) 支持在" + ("充电" if needs_recharge else "补充") +
            "的同时继续使用（边充边用），确保永不断档。"
            "对于高频使用场景，我们建议配备备用方案以确保连续运转。"
        ),
        "a_en": (
            f"{title} delivers excellent endurance under normal use conditions. Specifically: "
            "1) A single full charge/prep meets daily usage needs "
            "(tested data shows it can sustain all-day continuous use); "
            "2) " + ("Recharging/replenishment" if needs_recharge else "Preparation") +
            " is fast and convenient; "
            "3) It supports use while " + ("charging" if needs_recharge else "replenishing") +
            ", ensuring you never run out. "
            "We recommend keeping a backup for high-frequency usage scenarios."
        ),
    })

    # 6. Noisy environment performance
    qa_pairs.append({
        "q_zh": f"关于{title}在高噪音/复杂环境下的使用效果",
        "q_en": f"About performance in noisy/complex environments",
        "a_zh": (
            f"结论是：即使在复杂环境下，{title}依然表现可靠。具体来说："
            "1) 产品经过针对性优化，核心功能不受环境干扰"
            "（关键性能指标在多种环境下均保持稳定）；"
            "2) 具备足够的输出功率/音量/亮度，确保在嘈杂或复杂场景中依然清晰可用；"
            "3) 配备实体操作按键/界面，可随时快速调节。"
            "例如，在极端嘈杂的环境中，我们建议调至最大档位即可完美覆盖背景干扰。"
        ),
        "a_en": (
            f"{title} performs reliably even in complex environments. Specifically: "
            "1) The product is optimized to maintain core functionality regardless of environmental interference "
            "(key performance metrics remain stable across various environments); "
            "2) It delivers sufficient output power to remain clearly usable in noisy or complex scenarios; "
            "3) Physical controls allow quick adjustments anytime. "
            "For extremely noisy environments, we recommend using maximum settings to overpower background interference."
        ),
    })

    # 7. Additional features
    qa_pairs.append({
        "q_zh": f"关于{title}的附加实用功能",
        "q_en": f"About additional practical features of this {category}",
        "a_zh": (
            f"{title}除了核心功能外，还具备多项提升使用体验的附加功能。具体来说："
            "1) 产品内置智能芯片/模块，可自动适配不同使用场景"
            "（多项智能功能协同工作，提升整体使用体验）；"
            "2) 无需连接手机APP或其他设备即可独立工作；"
            "3) 这些功能旨在为用户提供更便捷、更安全的使用体验。"
            "我们建议在使用前浏览完整的功能列表，以充分利用产品的所有潜力。"
        ),
        "a_en": (
            f"Yes, beyond its core functionality, {title} includes several additional features "
            "that enhance the user experience. Specifically: "
            "1) Built-in smart modules automatically adapt to different usage scenarios "
            "(multiple intelligent features work together to elevate the overall experience); "
            "2) It works independently without needing a smartphone app connection; "
            "3) These features are designed for greater convenience and safety. "
            "We recommend reviewing the full feature list before use to fully leverage the product's potential."
        ),
    })

    # 8. Warranty and support
    qa_pairs.append({
        "q_zh": f"关于{title}的售后保修与技术支持",
        "q_en": f"About warranty and technical support for this {category}",
        "a_zh": (
            f"结论是：我们提供1年无忧官方保修及终身技术支持。具体来说："
            "1) 自购买之日起1年内，针对非人为损坏的硬件故障，我们提供免费维修或更换服务；"
            "2) 包装内附带详细的客服联系方式，专属团队会在24小时内响应您的排障需求；"
            "3) 质保不涵盖因私自拆卸或意外损坏导致的人为故障。"
            "我们建议妥善保留购买凭证，并在遇到任何使用问题时，优先联系客服进行排查。"
        ),
        "a_en": (
            f"Yes, we offer a 1-year worry-free official warranty and lifetime technical support. "
            "Specifically: 1) Within 1 year of purchase (the warranty period), we provide free repair or "
            "replacement for hardware failures not caused by human error; "
            "2) The package includes detailed customer service contacts, "
            "and our dedicated team responds within 24 hours; "
            "3) The warranty does not cover man-made damage from unauthorized disassembly or accidents. "
            "We recommend keeping your purchase receipt and contacting support first for any issues."
        ),
    })

    return {
        "qa_pairs": qa_pairs,
        "total": len(qa_pairs),
        # 新增：基于 rufus-listing-probe 方法论生成的"探针式"问题集
        # 这些问题不是给客户回答的 Q&A，而是用来"探测 Rufus / AI 推荐逻辑"的
        "probing_strategy": _build_rufus_probe_strategy(context),
    }


# =============================================================================
# Rufus Probing Strategy (rufus-listing-probe 方法论落地)
# =============================================================================
#
# 不做"8 个通用 FAQ 问答"的老套路，而是：
#   1) 先判断当前 listing 在 5 大问题类型（scenario / decision-drivers /
#      comparison / user-feedback / shopper-language）上最弱的 3 个；
#   2) 按 3/3/2/2 的比例分配问题，最多 10 条；
#   3) 每条问题都带 purpose（这个问题能帮 listing 做什么）；
#   4) 不生成通用废题（is this good / who is this for 这类被明令禁止）。

def _build_rufus_probe_strategy(context: dict) -> dict:
    title    = context.get("title", "") or ""
    bullets  = context.get("bullets", []) or []
    category = context.get("category", "") or ""
    brand    = context.get("brand", "") or ""
    keywords = context.get("keywords", []) or []

    # ── Step 1：识别 listing 的 5 类弱点分数（分数越低越弱，越优先做）
    weakness = _assess_probe_weakness(title, bullets, category, keywords)

    # 按弱度升序 → 最弱的在前
    sorted_types = sorted(weakness.items(), key=lambda kv: kv[1]["score"])
    top3 = [t for t, _ in sorted_types[:3]]

    # ── Step 2：按 3/3/2/2 分配（共 10 问）
    #   type[0]: 3, type[1]: 3, type[2]: 2, type[3]: 2
    order = [t for t, _ in sorted_types]
    alloc = {
        order[0]: 3,
        order[1]: 3,
        order[2]: 2,
        order[3]: 2 if len(order) > 3 else 0,
    }

    # ── Step 3：逐类型生成问题
    questions_by_type: dict = {}
    for qtype, count in alloc.items():
        if count <= 0:
            continue
        qs = _generate_probe_questions(qtype, count, context)
        if qs:
            questions_by_type[qtype] = qs

    total = sum(len(q) for q in questions_by_type.values())

    # ── 可选：LLM 重写问题为更口语化、更贴近买家自然语气 ──
    # 如果用户在 config.json 里配了 llm_providers（默认/enabled 的那个），
    # 调它一次把 10 题重写；失败或未配置时保留原模板。
    try:
        refined = _llm_refine_probe_questions(
            questions_by_type,
            category=_clean_category(context.get("category", "")),
            brand=(context.get("brand") or ""),
            keywords_top=[k.get("keyword") if isinstance(k, dict) else str(k)
                          for k in (context.get("keywords") or [])][:5],
        )
        if refined:
            questions_by_type = refined
            llm_refined = True
        else:
            llm_refined = False
    except Exception:
        llm_refined = False

    reason_bits = []
    for t in top3:
        info = weakness[t]
        reason_bits.append(f"{_TYPE_LABELS[t]}（弱点：{info['reason']}）")

    return {
        "priority": {
            "primary":    top3[0] if len(top3) > 0 else None,
            "secondary":  top3[1] if len(top3) > 1 else None,
            "tertiary":   top3[2] if len(top3) > 2 else None,
            "reason":     " / ".join(reason_bits),
        },
        "weakness_scores": {
            t: {"score": info["score"], "reason": info["reason"],
                "label": _TYPE_LABELS[t]}
            for t, info in weakness.items()
        },
        "allocation":  {t: c for t, c in alloc.items() if c > 0},
        "questions":   questions_by_type,
        "total":       total,
        "framework":   "rufus-listing-probe · 5 类型自适应分配（最多 10 题）",
        "llm_refined": llm_refined,
    }


# ── LLM 重写（可选增强）────────────────────────────────────────
# 只要用户在 config.json 里的 llm_providers 有一个 enabled/default 项，
# 这个函数就会自动启用。失败、超时、未配置都静默降级到原模板。
def _llm_refine_probe_questions(questions_by_type: dict, category: str,
                                 brand: str, keywords_top: list) -> dict | None:
    """用 LLM 把探针问题改写成更自然的 Amazon 买家口吻。返回新的 questions_by_type 或 None。"""
    try:
        from agent.providers import get_default_provider, chat_completion
    except Exception:
        return None

    provider = get_default_provider()
    if provider is None or not provider.api_key or "***" in provider.api_key:
        return None

    # 扁平化原问题 + 给每题一个 id
    flat: list = []
    for qtype, qs in questions_by_type.items():
        for q in qs:
            flat.append({
                "id": len(flat) + 1,
                "type": qtype,
                "q": q.get("q", ""),
                "purpose": q.get("purpose", ""),
            })
    if not flat:
        return None

    system = (
        "You are an Amazon shopper-voice copywriter. Rewrite probe questions to sound "
        "like a real Amazon shopper asking Rufus — concise, conversational, no analyst jargon. "
        "Keep each question under 25 words. Preserve the original intent & the *category* "
        "mentioned. Do NOT add a question mark unless the original had one. "
        "Never change 'purpose' text — only rewrite 'q'."
    )
    user_ctx = {
        "category": category or "",
        "brand": brand or "",
        "top_keywords": keywords_top,
        "questions": [{"id": x["id"], "q": x["q"]} for x in flat],
    }
    user = (
        "Context (for reference, not to repeat):\n"
        + json.dumps(user_ctx, ensure_ascii=False, indent=2)
        + "\n\nReturn ONLY a JSON array like:\n"
          '[{"id":1,"q":"..."}, {"id":2,"q":"..."}]\n'
          "Same id list, same length. No prose, no markdown fences."
    )

    try:
        resp = chat_completion(
            provider,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            temperature_override=0.4,
            max_tokens=1200,
        )
    except Exception:
        return None

    raw = (resp.get("content") or "").strip()
    # 清掉可能的 ```json 包裹
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            return None
    except Exception:
        return None

    # 建 id → 新 q 的映射
    id_to_q = {}
    for item in parsed:
        if isinstance(item, dict) and "id" in item and "q" in item:
            s = str(item["q"]).strip()
            if s:
                id_to_q[int(item["id"])] = s
    if not id_to_q:
        return None

    # 回填到原结构
    new_by_type: dict = {}
    for qtype, qs in questions_by_type.items():
        new_by_type[qtype] = []
        for q in qs:
            new_q = dict(q)
            # 用 flat 里对应的 id 找新问题
            for x in flat:
                if x["type"] == qtype and x["q"] == q.get("q"):
                    if x["id"] in id_to_q:
                        new_q["q"] = id_to_q[x["id"]]
                    break
            new_by_type[qtype].append(new_q)
    return new_by_type


_TYPE_LABELS = {
    "scenario_persona":        "场景与人群",
    "decision_drivers":        "决策因素",
    "comparison_substitution": "对比与替代",
    "user_feedback_friction":  "用户反馈 / 摩擦",
    "shopper_language":        "买家自然语言",
}


def _assess_probe_weakness(title: str, bullets: list,
                            category: str, keywords: list) -> dict:
    """对 5 类问题给出『当前 listing 在这里弱不弱』的分数（0-10，越高越强）。"""
    title_l = title.lower()
    joined  = (title_l + " " + " ".join(str(b) for b in bullets).lower())
    bullet_count = sum(1 for b in bullets if b and len(str(b).strip()) > 20)

    # 场景/人群：句子里是否有明确场景词或 for + 人群
    scenario_hits = sum(joined.count(s) for s in
                        ["for home", "for office", "for travel",
                         "perfect for", "designed for", "ideal for",
                         "bedroom", "bathroom", "kitchen"])
    scenario_score = min(scenario_hits * 2, 10)
    scenario_reason = ("场景词充足" if scenario_score >= 6
                       else "场景 / 人群定位偏弱，Rufus 匹配能力有限")

    # 决策因素：量化数据 + 因果连接
    numeric_hits = len(re.findall(r"\d+\s*(?:inch|cm|mm|lb|oz|ml|l|g|mah|"
                                  r"pcs|count|pack|rpm|w|v)", joined))
    cause_hits   = sum(1 for w in ["because", "powered by", "with",
                                    "featuring", "ensures", "delivers"]
                       if w in joined)
    drivers_score = min(numeric_hits * 2 + cause_hits, 10)
    drivers_reason = ("量化数据 & 因果连接充分" if drivers_score >= 7
                      else "缺少量化参数或功能→收益的因果表达")

    # 对比/替代：有无 vs / compared to / better than
    compare_hits = sum(1 for w in ["vs", "compared to", "better than",
                                    "unlike", "alternative", "replacement for"]
                       if w in joined)
    compare_score = min(compare_hits * 3, 10)
    compare_reason = ("有明显对比框架" if compare_score >= 6
                      else "缺少『与同类产品的差异化』表述")

    # 用户反馈/摩擦：是否处理了常见抱怨 / 期望管理
    friction_signals = ["no more", "say goodbye", "never worry",
                        "without", "streak-free", "easy to clean",
                        "leak-proof", "break-resistant"]
    friction_score = min(sum(2 for s in friction_signals if s in joined), 10)
    friction_reason = ("已处理常见摩擦点" if friction_score >= 6
                       else "未显性处理买家常见痛点 / 期望落差")

    # 买家语言：自然副词 + 简洁而不 SEO 堆砌
    natural_hits = sum(1 for s in ["you can", "you'll", "so you",
                                    "makes it easy", "perfect for",
                                    "easy to"] if s in joined)
    caps_ratio = sum(1 for c in title if c.isupper()) / max(1, len(title))
    lang_score = min(natural_hits * 2, 8) + (2 if caps_ratio < 0.35 else 0)
    lang_reason = ("语言自然" if lang_score >= 7
                   else "语言偏 SEO / 技术化，买家理解成本高")

    return {
        "scenario_persona":        {"score": scenario_score, "reason": scenario_reason},
        "decision_drivers":        {"score": drivers_score,  "reason": drivers_reason},
        "comparison_substitution": {"score": compare_score,  "reason": compare_reason},
        "user_feedback_friction":  {"score": friction_score, "reason": friction_reason},
        "shopper_language":        {"score": lang_score,     "reason": lang_reason},
    }


def _clean_category(raw: str) -> str:
    """清掉 Sorftime 分类里的『（排名:N）』/『(rank:N)』等尾部数据标注，只保留类目名。

    例：'Squeegees（排名:93）'  → 'Squeegees'
        'Health & Household（排名:47213）' → 'Health & Household'
        'Kitchen Tools (rank:15)'   → 'Kitchen Tools'
    """
    if not raw:
        return ""
    s = str(raw).strip()
    # 去中英文括号及里面的排名/rank/排名:N
    s = re.sub(r"\s*[（(][^）)]*[）)]\s*$", "", s)
    # 多余空白 & 尾部标点
    s = re.sub(r"\s+", " ", s).strip(" ·-,，。")
    return s


def _generate_probe_questions(qtype: str, count: int, context: dict) -> list:
    """按类型 + 数量生成探针问题。每题带 purpose。"""
    title    = context.get("title", "") or "this product"
    category = _clean_category(context.get("category", "")) or "product"
    brand    = context.get("brand", "") or ""
    keywords = [k.get("keyword") if isinstance(k, dict) else str(k)
                for k in (context.get("keywords") or [])]
    kw_top3 = keywords[:3]

    # 尝试从关键词里猜一个"典型使用场景"
    scene_guess = ""
    for kw in keywords[:10]:
        for s in ["kitchen", "bathroom", "bedroom", "outdoor", "office",
                  "home", "travel", "garage"]:
            if s in kw.lower():
                scene_guess = s
                break
        if scene_guess:
            break
    scene_guess = scene_guess or "home"

    # 对比词：从关键词里找疑似品类别名
    alt_guess = ""
    for kw in keywords[:10]:
        if " " in kw and kw.lower() != (title.lower()):
            alt_guess = kw
            break
    alt_guess = alt_guess or f"standard {category}"

    pool = {
        "scenario_persona": [
            {"q": f"In what specific situations would someone in a small {scene_guess} "
                  f"choose a {category} like this one?",
             "purpose": "identify the scene to emphasize in the title / first bullet"},
            {"q": f"Why would a first-time buyer need a {category} instead of just "
                  f"using what they already have?",
             "purpose": "surface the shopper's underlying pain → turn into bullet 1"},
            {"q": f"Is this {category} a good option for someone dealing with "
                  f"{kw_top3[0] if kw_top3 else 'limited space'}?",
             "purpose": "check whether the listing language matches niche buyer segments"},
        ],
        "decision_drivers": [
            {"q": f"What matters most when choosing a {category} for "
                  f"{kw_top3[0] if kw_top3 else 'daily use'}?",
             "purpose": "find out which claim should be promoted in bullet 1-2"},
            {"q": f"How important is durability vs. price when buyers pick a {category}?",
             "purpose": "decide whether to emphasize premium materials or value"},
            {"q": f"Which factor should buyers weigh more: ease of cleaning or "
                  f"multi-function versatility?",
             "purpose": "choose what to lead with in bullet ordering"},
        ],
        "comparison_substitution": [
            {"q": f"For a {scene_guess} user, how does this {category} compare with "
                  f"{alt_guess}?",
             "purpose": "position the product relative to its most-queried alternative"},
            {"q": f"What type of shopper should choose a {category} over a simpler "
                  f"single-purpose tool?",
             "purpose": "define the target recommendation slot"},
            {"q": f"When does buying this {category} make more sense than using "
                  f"{alt_guess}?",
             "purpose": "extract the concrete 'switch-to' trigger messaging"},
        ],
        "user_feedback_friction": [
            {"q": f"What do buyers most appreciate after using a {category} like this "
                  f"for a few weeks?",
             "purpose": "identify the most reinforced delight point → put in bullet 1"},
            {"q": f"What problems do people run into most often with {category} "
                  f"products?",
             "purpose": "pre-empt complaints in FAQ / expectation management bullet"},
            {"q": f"What confuses buyers right after purchase?",
             "purpose": "create a 'quick-start' bullet or pre-empt reviews about setup"},
        ],
        "shopper_language": [
            {"q": f"How would a non-expert shopper describe the need for a {category} "
                  f"in plain English?",
             "purpose": "rewrite the first bullet using that exact phrasing"},
            {"q": f"What natural phrases would a beginner use when searching for "
                  f"{kw_top3[0] if kw_top3 else 'this kind of product'}?",
             "purpose": "inject these phrases into bullets / backend search terms"},
            {"q": f"How do real users describe the problem this {category} solves "
                  f"without using technical terms?",
             "purpose": "make the title GEO-friendly for natural-language queries"},
        ],
    }
    return pool.get(qtype, [])[:count]


# =============================================================================
# Selling points
# =============================================================================

def extract_selling_points(context: dict) -> dict:
    """Extract and rank selling points with COSMO cause-effect chains."""
    title = context.get("title", "") or ""
    bullets = context.get("bullets", []) or []
    category = context.get("category", "") or ""

    cause_pat = re.compile(
        r"(因为|由于|采用|通过|配备|内置|because|powered by|with|featuring|equipped)",
        re.IGNORECASE,
    )
    effect_pat = re.compile(
        r"(可以|能够|确保|提供|帮助|改善|减少|增加|提升|delivers|provides|ensures|helps|improves|reduces|boosts)",
        re.IGNORECASE,
    )
    num_pat = re.compile(r"\d+")

    extracted: list[dict] = []
    for idx, bullet in enumerate(bullets[:5]):
        text = str(bullet or "").strip()
        if not text:
            continue
        has_cause = bool(cause_pat.search(text))
        has_effect = bool(effect_pat.search(text))
        has_qty = bool(num_pat.search(text))

        if has_cause and has_effect:
            strength = "high"
        elif has_cause or has_effect:
            strength = "medium"
        else:
            strength = "low"

        extracted.append({
            "source": f"Bullet {idx + 1}",
            "text": text,
            "cause_effect_complete": has_cause and has_effect,
            "has_quantified_data": has_qty,
            "cosmo_strength": strength,
        })

    # Sort by strength, desc
    strength_rank = {"high": 2, "medium": 1, "low": 0}
    extracted.sort(key=lambda p: strength_rank[p["cosmo_strength"]], reverse=True)

    # Build improvement suggestions
    improvement_suggestions: list[str] = []
    low_count = sum(1 for p in extracted if p["cosmo_strength"] == "low")
    if low_count >= 3:
        improvement_suggestions.append(
            "严重缺乏因果推理结构。建议每个卖点按'痛点→机制→结果→边界'公式重写。"
        )
    no_data = [p for p in extracted if not p["has_quantified_data"]]
    if len(no_data) >= 3:
        improvement_suggestions.append(
            "缺乏量化数据支撑。建议在卖点中嵌入具体的数量、时间、百分比等数字。"
        )
    if len(extracted) < 5:
        improvement_suggestions.append(
            "卖点数量不足。建议从产品属性、使用场景、用户评价中挖掘至少5个独立卖点。"
        )
    if not improvement_suggestions:
        improvement_suggestions.append(
            "卖点结构良好，建议在Q&A和A+内容中进一步展开每个卖点的因果关系。"
        )

    return {
        "extracted_points": extracted,
        "top_3": extracted[:3],
        "improvement_suggestions": improvement_suggestions,
        "cosmo_advice": _cosmo_selling_advice(extracted, category),
    }


def _cosmo_selling_advice(points: list[dict], category: str) -> str:
    """Generate COSMO-specific selling advice."""
    if not points:
        return (
            f"当前{category or '产品'}卖点的COSMO语义密度严重偏低。"
            "Rufus在面对买家'哪款" + (category or "产品") + "更适合XX场景？'的复合查询时，"
            "无法从您的Listing中提取有效的因果关系链来推荐您的产品。"
            "建议立即按照'场景→功能→量化结果→兼容人群'的链路重构所有卖点。"
        )
    strengths = [p["cosmo_strength"] for p in points]
    if strengths.count("high") >= 3:
        return (
            "卖点的COSMO语义结构完整。Rufus能够高效抓取并理解您的产品价值主张，"
            "在面对买家的场景化、对比型提问时具有较高的被推荐优先级。"
        )
    if strengths.count("low") >= 2:
        return (
            f"当前{category or '产品'}卖点的COSMO语义密度严重偏低。"
            "Rufus在面对买家'哪款" + (category or "产品") + "更适合XX场景？'的复合查询时，"
            "无法从您的Listing中提取有效的因果关系链来推荐您的产品。"
            "建议立即按照'场景→功能→量化结果→兼容人群'的链路重构所有卖点。"
        )
    return (
        "卖点具备基础的COSMO结构，但部分节点缺乏量化数据或常识疑虑解答。"
        "建议补充'解决什么顾虑'和'适合什么人群'的明确表述，"
        "以提升Rufus在复合查询中的抓取优先级。"
    )


# =============================================================================
# Attributes / persona / scenes (for insights dashboard)
# =============================================================================

def _extract_attributes(context: dict) -> dict:
    """Extract key product attributes from bullets and title."""
    title = context.get("title", "") or ""
    bullets = context.get("bullets", []) or []
    text = title + " " + " ".join(str(b) for b in bullets)
    attrs: dict[str, str] = {}

    if re.search(r"\d+[,\.\d]*\s*RPM|电机|motor|brushless", text, re.IGNORECASE):
        attrs["core_function"] = "高速无刷电机"
        attrs["core_function_en"] = "High-Speed Brushless Motor"
    elif re.search(r"supplement|vitamin|magnesium|mineral|nutrition", text, re.IGNORECASE):
        attrs["core_function"] = "高吸收率复合补充剂"
        attrs["core_function_en"] = "High-Absorption Complex Supplement"
    elif re.search(r"radio|对讲|PTT|POC|communication", text, re.IGNORECASE):
        attrs["core_function"] = "5G/4G POC公网对讲机"
        attrs["core_function_en"] = "5G/4G POC Push-to-Talk Radio"
    elif re.search(r"dryer|吹风|hair", text, re.IGNORECASE):
        attrs["core_function"] = "高速负离子吹风机"
        attrs["core_function_en"] = "High-Speed Ionic Hair Dryer"

    if re.search(r"便携|轻|compact|lightweight|portable|travel", text, re.IGNORECASE):
        attrs["differentiator"] = "轻巧便携"
    elif re.search(r"认证|NSF|GMP|FDA|certified|approved", text, re.IGNORECASE):
        attrs["differentiator"] = "权威认证"
    elif re.search(r"8\s*in\s*1|复合|complex|blend", text, re.IGNORECASE):
        attrs["differentiator"] = "8合1复合配方"

    if re.search(r"赠送|附送|包含|with.*nozzle|with.*accessory", text, re.IGNORECASE):
        m = re.search(r"(?:赠送|附送|包含|with)\s*([^,，.\n]+)", text, re.IGNORECASE)
        if m:
            attrs["extras"] = m.group(1).strip()[:30]

    return attrs


def _detect_persona(context: dict) -> str:
    """Detect target persona from product context."""
    title = context.get("title", "") or ""
    bullets = context.get("bullets", []) or []
    text = " ".join(str(b) for b in bullets) + " " + title

    persona_map = [
        (r"上班族|通勤|出差|商务|commut|business|office|worker", "上班族与商务人士"),
        (r"运动员|健身|运动|athlete|fitness|gym|workout|active", "运动健身人群"),
        (r"老人|老年|senior|elderly|aging", "老年人"),
        (r"婴儿|宝宝|儿童|小孩|baby|kid|child|infant|toddler", "婴幼儿家庭"),
        (r"宠物|pet|dog|cat", "宠物家庭"),
        (r"旅行|travel|trip|journey", "旅行者"),
        (r"学生|student|college|school", "学生群体"),
    ]
    for pat, label in persona_map:
        if re.search(pat, text, re.IGNORECASE):
            return label
    return "男女成人"


def _detect_problem(context: dict) -> str:
    """Detect the problem the product solves."""
    title = context.get("title", "") or ""
    bullets = context.get("bullets", []) or []
    text = (title + " " + " ".join(str(b) for b in bullets)).lower()
    problem_map = [
        (r"毛躁|干枯|分叉|frizz|dry\s*hair|split\s*end", "毛躁发质"),
        (r"疲劳|肌肉|恢复|muscle|fatigue|recovery|sore", "肌肉疲劳与恢复"),
        (r"睡眠|失眠|sleep|insomnia|relaxation", "睡眠质量"),
        (r"迟到|赶时间|busy\s*morning|rush|quick", "早晨匆忙"),
    ]
    for pat, label in problem_map:
        if re.search(pat, text):
            return label
    return ""


def _detect_scenes(context: dict) -> list[str]:
    """Detect usage scenes."""
    bullets = context.get("bullets", []) or []
    category = context.get("category", "") or ""
    text = " ".join(str(b) for b in bullets) + " " + category

    scene_map = [
        (r"送礼|礼物|gift|present|birthday|mother", "送礼佳品"),
        (r"户外|outdoor|camping|hiking", "户外活动"),
        (r"办公|office|desk|work", "办公场景"),
        (r"健身|运动|gym|workout|fitness", "健身房"),
        (r"家庭|家居|home|family|household", "家庭使用"),
        (r"旅行|出差|travel|trip|journey", "旅行便携"),
    ]
    scenes = []
    for pat, label in scene_map:
        if re.search(pat, text, re.IGNORECASE):
            scenes.append(label)
    if not scenes:
        scenes.append("日常使用")
    return scenes


# =============================================================================
# Data insights dashboard
# =============================================================================

def build_data_insights(context: dict) -> dict:
    """Build a comprehensive data insights dashboard from all available context."""
    title = context.get("title", "") or ""
    category = context.get("category", "") or ""
    keywords = context.get("keywords", []) or []
    bullets = context.get("bullets", []) or []
    brand = context.get("brand", "") or ""
    price = context.get("price", "")
    rating = context.get("rating", "")
    review_count = context.get("review_count", "")
    description = context.get("description", "") or ""
    mcp_status = context.get("mcp_status", "") or ""
    synthetic = bool(context.get("bullets_synthetic", False))
    visual_features = context.get("visual_features", {}) or {}
    cosmo_intents = context.get("cosmo_intents", []) or []

    # Overview panel
    overview = {
        "brand": brand or "未识别",
        "price": f"${price}" if price else "未知",
        "rating": f"{rating}/5" if rating else "暂无评分",
        "review_count": review_count if review_count else "暂无",
        "category": category or "未识别",
    }

    # Keyword health
    all_words: set[str] = set()
    for kw in keywords:
        text = kw.get("keyword", "") if isinstance(kw, dict) else str(kw)
        for w in text.split():
            if len(w) > 2:
                all_words.add(w.lower())
    total_kw = len(keywords)
    if total_kw >= 50:
        coverage_judgment = "关键词覆盖广泛，流量入口充足"
        coverage_level = "高"
    elif total_kw >= 20:
        coverage_judgment = "关键词覆盖中等"
        coverage_level = "中"
    else:
        coverage_judgment = "关键词覆盖不足，建议拓展长尾词"
        coverage_level = "低"
    keyword_health = {
        "total": total_kw,
        "top5": [
            (k.get("keyword") if isinstance(k, dict) else str(k)) for k in keywords[:5]
        ],
        "unique_words": len(all_words),
        "diversity": coverage_level,
        "coverage_judgment": coverage_judgment,
    }

    # Bullets health
    bullet_details: list[dict] = []
    for i, b in enumerate(bullets[:5]):
        text = str(b or "")
        bullet_details.append({
            "index": i + 1,
            "text": text[:120],
            "score": _score_bullet(text),
        })
    avg_score = (
        sum(b["score"] for b in bullet_details) // len(bullet_details)
        if bullet_details else 0
    )
    if avg_score >= 80:
        judgment = "五点描述COSMO语义密度优秀，Rufus可高效索引"
    elif avg_score >= 60:
        judgment = "五点描述结构良好，建议补充量化数据"
    elif avg_score >= 40:
        judgment = "五点描述缺乏因果链路，Rufus推荐优先级偏低"
    else:
        judgment = "五点描述严重不足，Rufus无法有效推荐该产品"
    bullets_health = {
        "count": len(bullet_details),
        "avg_score": avg_score,
        "synthetic": synthetic,
        "judgment": judgment,
        "details": bullet_details,
    }

    # Market signals
    has_sif = bool(context.get("sif_keywords"))
    has_sorftime = bool(context.get("sorftime_data"))
    if has_sif and has_sorftime:
        mcp_sources = "SIF + Sorftime"
    elif has_sif:
        mcp_sources = "sif"
    elif has_sorftime:
        mcp_sources = "sorftime"
    else:
        mcp_sources = mcp_status or "暂无"
    data_quality = (
        "高 — 真实Listing数据" if not synthetic
        else ("中 — 基于关键词合成的五点描述" if bullets
              else "低 — 数据不足，建议补充")
    )
    market_signals = {
        "mcp_sources": mcp_sources,
        "data_quality": data_quality,
        "category_hierarchy": category,
        "category_depth": len([p for p in category.split(">") if p.strip()]),
    }

    # Visual summary
    visual_summary = {
        "materials": visual_features.get("materials", []),
        "colors": {
            "primary_colors": visual_features.get("primary_colors", []),
        },
        "shape": visual_features.get("product_shape", ""),
    }

    # Recommendations
    recommendations: list[dict] = []
    if avg_score < 60:
        recommendations.append({
            "priority": "high",
            "area": "五点描述优化",
            "action": "为每个Bullet添加具体的量化数据和因果链条（痛点→机制→结果→边界）",
        })
    if total_kw < 20:
        recommendations.append({
            "priority": "high",
            "area": "关键词拓展",
            "action": f"当前仅{total_kw}个流量词，建议通过SIF MCP挖掘更多长尾关键词覆盖蓝海流量",
        })
    if not brand:
        recommendations.append({
            "priority": "medium",
            "area": "品牌识别",
            "action": "标题中品牌信息不明显，建议前置品牌名以提高品牌搜索可见度",
        })
    if synthetic:
        recommendations.append({
            "priority": "medium",
            "area": "数据质量",
            "action": "当前五点描述为AI合成。建议从Amazon实时采集真实Listing数据以获得更准确的COSMO评分",
        })
    if not rating or not review_count:
        recommendations.append({
            "priority": "medium",
            "area": "社会证明",
            "action": "缺少评分和评论数据，建议关注Review积累策略以提升转化率",
        })
    if avg_score >= 60:
        recommendations.append({
            "priority": "low",
            "area": "A+内容",
            "action": "五点描述质量良好，建议同步优化A+内容（品牌故事+场景图+对比模块）以最大化Rufus推荐权重",
        })
    recommendations.append({
        "priority": "low",
        "area": "持续监控",
        "action": "每周通过SIF MCP监控关键词排名变化，关注竞品动态，及时调整投放策略",
    })

    return {
        "overview": overview,
        "keyword_health": keyword_health,
        "bullets_health": bullets_health,
        "market_signals": market_signals,
        "visual_summary": visual_summary,
        "recommendations": recommendations,
        "data_quality_note": (
            "真实Amazon Listing数据 + COSMO/Rufus算法量化评估"
            if not synthetic
            else "基于关键词的AI合成数据 + COSMO/Rufus算法量化评估"
        ),
    }
