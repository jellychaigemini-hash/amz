# -*- coding: utf-8 -*-
"""
Rufus 答案解析器
================
输入：Rufus 一次回答的原文（可能是 CDP 自动抓到的，也可能是用户手动粘贴的）
输出：结构化信号 —— follow-ups、品牌、价格区间、核心短语等。

参考 skill/rufus-research/scripts/rufus-research-runner.mjs 的解析逻辑，
但：
  1) 用更宽的 follow-up 特征词（避免漏抓）
  2) 品牌从预设词表改为"正则 + 大写词频"混合识别
  3) 价格区间覆盖更多表达方式
  4) 额外抽出"决策因素词"和"场景词"（直接喂给 GEO Audit）
"""
from __future__ import annotations
import re
from collections import Counter
from typing import Iterable


# ── Follow-up 识别 ──────────────────────────────────────────────
# Rufus 追问一般是短句，以下面动词/疑问词开头
_FOLLOWUP_STARTERS = (
    "Show ", "Best ", "How to ", "How much ", "How do ", "How does ",
    "What ", "Which ", "Why ", "When ", "Where ",
    "Can you ", "Can I ", "Should ",
    "Compare ", "Tips for ", "Find ", "Recommend ",
)


def _extract_followups(text: str) -> list[str]:
    """抽 Rufus 追问建议 / 买家搜索意图短句。"""
    seen: set = set()
    hits: list = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if len(line) < 8 or len(line) > 120:
            continue
        # 必须以已知动词/疑问词开头
        if not any(line.startswith(s) for s in _FOLLOWUP_STARTERS):
            continue
        # 去重（不区分大小写）
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        hits.append(line)
    return hits[:15]


# ── 品牌识别 ────────────────────────────────────────────────────
# 白名单 + 通用『1-3 连写词，开头大写，全长 2-24 字母』正则
_KNOWN_BRANDS = (
    "NICETOWN", "MIULEE", "Yakamok", "Melodieux", "MICROFA", "TG",
    "Apollo", "AmazonBasics", "Amazon Basics", "Levoit", "Dyson",
    "iRobot", "Shark", "Bissell", "Eufy", "Govee", "Anker",
    "SAMSUNG", "LG", "Bose", "Philips",
)
_BRAND_RE = re.compile(
    r"\b(?:[A-Z][a-zA-Z0-9]{1,14}|[A-Z]{2,8})\b"
)
_BRAND_STOPWORDS = {
    "YES", "NO", "THE", "USA", "US", "UK", "FAQ", "AI", "CEO",
    "DIY", "PDF", "USD", "NEW", "PRO", "XL", "PM",
    "Amazon", "Rufus", "Alexa", "When", "What", "How", "Why",
    "Here", "This", "That", "These", "Those", "You", "Your",
    "Our", "Their", "Show", "Best", "Find",
}


def _extract_brands(text: str, known_extra: Iterable[str] = ()) -> list[str]:
    """从 Rufus 回答里挖出产品品牌。"""
    found: dict[str, int] = {}
    # 1) 白名单直接匹配
    for b in list(_KNOWN_BRANDS) + list(known_extra):
        # 以完整单词边界查
        pat = re.compile(rf"\b{re.escape(b)}\b", re.IGNORECASE)
        count = len(pat.findall(text))
        if count:
            found[b] = count
    # 2) 正则全扫：Capitalize / ALLCAPS
    for m in _BRAND_RE.finditer(text):
        w = m.group(0)
        if w in _BRAND_STOPWORDS:
            continue
        # 过滤太常见的开头词
        if len(w) < 3:
            continue
        found[w] = found.get(w, 0) + 1
    # 只保留出现 ≥ 2 次的（降噪）
    return [b for b, cnt in sorted(found.items(), key=lambda x: -x[1]) if cnt >= 2][:15]


# ── 价格 ────────────────────────────────────────────────────────
_PRICE_PATTERNS = [
    re.compile(r"\$\d+(?:\.\d+)?\s*[-–]\s*\$?\d+(?:\.\d+)?"),          # $15-$80
    re.compile(r"\$\d+(?:\.\d+)?\s*(?:to|~)\s*\$?\d+(?:\.\d+)?"),       # $15 to $80
    re.compile(r"\$\d+(?:\.\d+)?\s*(?:per\s+\w+|each)"),                # $20 per pair
    re.compile(r"\$\d+(?:\.\d+)?\s*(?:and\s+(?:up|above))"),            # $20 and up
    re.compile(r"under\s+\$\d+(?:\.\d+)?"),                             # under $50
    re.compile(r"around\s+\$\d+(?:\.\d+)?"),                            # around $30
]


def _extract_prices(text: str) -> list[str]:
    seen: set = set()
    hits: list = []
    for pat in _PRICE_PATTERNS:
        for m in pat.finditer(text):
            s = m.group(0).lower().strip()
            if s not in seen:
                seen.add(s)
                hits.append(s)
    return hits[:10]


# ── 决策因素词 / 场景词（为 GEO Audit 提供证据） ─────────────────
# 这些词如果 Rufus 回答里频繁出现，说明它们是买家真正关心的因素
_DRIVER_VOCAB = {
    "size":         ["size", "dimension", "inches", "inch", "length", "width",
                    "height", "weight"],
    "material":     ["material", "fabric", "wood", "metal", "stainless",
                    "plastic", "rubber", "polyester"],
    "durability":   ["durable", "sturdy", "long-lasting", "heavy-duty",
                    "break-resistant", "wear-resistant"],
    "ease_of_use":  ["easy", "simple", "quick", "one-touch", "user-friendly",
                    "hassle-free"],
    "cleanability": ["washable", "dishwasher", "easy to clean", "machine-washable",
                    "wipe clean"],
    "safety":       ["safe", "bpa-free", "non-toxic", "certified", "food-grade",
                    "child-safe"],
    "versatility":  ["multi", "versatile", "3-in-1", "2-in-1", "all-in-one"],
    "price_value":  ["value", "affordable", "budget", "cheap", "cost-effective"],
    "noise":        ["quiet", "silent", "noise", "decibel", "db"],
    "energy":       ["energy-saving", "efficient", "battery", "eco-friendly"],
}

_SCENE_VOCAB = {
    "bedroom":   ["bedroom", "sleeping"],
    "living":    ["living room", "living-room", "family room"],
    "kitchen":   ["kitchen", "cooking", "dining"],
    "bathroom":  ["bathroom", "bath", "shower"],
    "office":    ["office", "workspace", "desk"],
    "outdoor":   ["outdoor", "garden", "patio", "yard"],
    "travel":    ["travel", "trip", "commute", "on the go", "on-the-go"],
    "small":     ["small space", "apartment", "dorm", "compact", "tiny"],
    "gift":      ["gift", "present", "holiday"],
    "kids":      ["kid", "children", "baby", "infant", "toddler"],
    "pets":      ["pet", "dog", "cat"],
    "gym":       ["gym", "workout", "fitness"],
}


def _match_vocab(text_lower: str, vocab: dict[str, list[str]]) -> dict[str, int]:
    """返回 {分类: 命中次数}。"""
    result: dict[str, int] = {}
    for cat, needles in vocab.items():
        cnt = 0
        for n in needles:
            cnt += text_lower.count(n.lower())
        if cnt > 0:
            result[cat] = cnt
    return result


# ── 主入口 ──────────────────────────────────────────────────────
def parse_rufus_answer(raw: str, question: str = "",
                      known_brands: Iterable[str] = ()) -> dict:
    """解析单条 Rufus 回答，返回结构化信号。

    Args:
        raw: Rufus 回答原文（可能含 follow-ups、品牌、表格、价格）
        question: 对应提的问题（帮助定位回答起点）
        known_brands: 额外品牌词表（比如已知竞品）

    Returns: dict with keys:
        raw_text, text_length, follow_ups, brands, prices,
        decision_drivers, scenes, sentence_count, word_count
    """
    text = (raw or "").strip()
    if not text:
        return {
            "raw_text": "", "text_length": 0,
            "follow_ups": [], "brands": [], "prices": [],
            "decision_drivers": {}, "scenes": {},
            "sentence_count": 0, "word_count": 0,
            "is_empty": True,
        }

    # 若传了 question，从 question 关键词后面的文字开始截（去掉之前的垃圾）
    if question and len(question) >= 10:
        marker = question[:40]
        pos = text.find(marker)
        if pos >= 0 and pos < len(text) - 100:
            text = text[pos:]

    text_lower = text.lower()

    return {
        "raw_text":         text[:5000],
        "text_length":      len(text),
        "follow_ups":       _extract_followups(text),
        "brands":           _extract_brands(text, known_extra=known_brands),
        "prices":           _extract_prices(text),
        "decision_drivers": _match_vocab(text_lower, _DRIVER_VOCAB),
        "scenes":           _match_vocab(text_lower, _SCENE_VOCAB),
        "sentence_count":   len(re.findall(r"[.!?]+", text)),
        "word_count":       len(re.findall(r"\b[\w']+\b", text)),
        "is_empty":         False,
    }


def summarize_answers(parsed_list: list[dict]) -> dict:
    """聚合多条 Rufus 答案的信号。

    输入：[parse_rufus_answer 的输出] ×N
    输出：跨 N 条答案的统计（follow-up 高频、品牌竞争、driver 热度、场景分布）
    """
    all_follow = Counter()
    all_brands = Counter()
    all_prices = Counter()
    all_drivers = Counter()
    all_scenes = Counter()
    total_words = 0
    total_text_len = 0
    non_empty = 0

    for a in parsed_list:
        if a.get("is_empty"):
            continue
        non_empty += 1
        total_words += a.get("word_count", 0)
        total_text_len += a.get("text_length", 0)
        for fu in a.get("follow_ups", []):
            all_follow[fu[:80]] += 1       # 截短避免键太长
        for b in a.get("brands", []):
            all_brands[b] += 1
        for p in a.get("prices", []):
            all_prices[p] += 1
        for k, v in (a.get("decision_drivers") or {}).items():
            all_drivers[k] += v
        for k, v in (a.get("scenes") or {}).items():
            all_scenes[k] += v

    return {
        "total_answers":       len(parsed_list),
        "non_empty_answers":   non_empty,
        "total_words":         total_words,
        "total_text_length":   total_text_len,
        "top_follow_ups":      all_follow.most_common(15),
        "top_brands":          all_brands.most_common(15),
        "top_prices":          all_prices.most_common(10),
        "driver_heatmap":      dict(all_drivers.most_common()),
        "scene_heatmap":       dict(all_scenes.most_common()),
    }
