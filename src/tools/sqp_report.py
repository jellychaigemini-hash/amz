#!/usr/bin/env python3
"""
SQP Brand Analysis Report Generator
=====================================
Reads Amazon Search Query Performance (SQP) Brand View weekly CSV exports
and generates:
  - 6 CSV files (structured data for each analysis module)
  - 1 PNG chart   (Top-5 stable terms trend)
  - 1 Markdown report (sqp_report.md, all data tables embedded)

Usage
-----
  python sqp_report.py --input "path/to/SQP/*.csv" --output "./sqp_output/"
  python sqp_report.py --input file_wk1.csv file_wk2.csv --output "./sqp_output/"

Requirements
------------
  pip install pandas matplotlib
"""

import re
import sys
import math
import glob
import argparse
from pathlib import Path
from typing import Optional, List, Tuple
from datetime import datetime

import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.font_manager as fm

# ══════════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════════

COL_Q       = "Search Query"
COL_IMP_B   = "Impressions: Brand Count"
COL_CLK_B   = "Clicks: Brand Count"
COL_CART_B  = "Cart Adds: Brand Count"
COL_PUR_B   = "Purchases: Brand Count"
COL_IMP_T   = "Impressions: Total Count"
COL_CLK_T   = "Clicks: Total Count"
COL_CART_T  = "Cart Adds: Total Count"
COL_PUR_T   = "Purchases: Total Count"
COL_PUR_RATE   = "Purchases: Purchase Rate %"
COL_IMP_BSHARE = "Impressions: Brand Share %"
COL_PUR_BSHARE = "Purchases: Brand Share %"

# ──────────────────────────────────────────────────────────────────
# 列名兼容映射（中文 / ASIN View / 无冒号 / 大小写等变体 → 标准列名）
# 语义等价：ASIN Count ≡ Brand Count（都代表"属于你这一组的部分"）
# ──────────────────────────────────────────────────────────────────
COLUMN_ALIASES = {
    # Search Query
    "搜索查询":                       COL_Q,
    "Search Query":                   COL_Q,

    # Impressions
    "曝光量：总数":                   COL_IMP_T,
    "曝光量:总数":                    COL_IMP_T,
    "Impressions: Total Count":       COL_IMP_T,
    "曝光量：ASIN 数量":              COL_IMP_B,
    "曝光量:ASIN 数量":               COL_IMP_B,
    "曝光量：品牌数量":               COL_IMP_B,
    "Impressions: ASIN Count":        COL_IMP_B,
    "Impressions: Brand Count":       COL_IMP_B,
    "曝光量：ASIN 占比%":             COL_IMP_BSHARE,
    "曝光量:ASIN 占比%":              COL_IMP_BSHARE,
    "曝光量：品牌占比%":              COL_IMP_BSHARE,
    "Impressions: ASIN Share %":      COL_IMP_BSHARE,
    "Impressions: Brand Share %":     COL_IMP_BSHARE,

    # Clicks
    "点击量：总数":                   COL_CLK_T,
    "点击量:总数":                    COL_CLK_T,
    "Clicks: Total Count":            COL_CLK_T,
    "点击量：ASIN 数量":              COL_CLK_B,
    "点击量:ASIN 数量":               COL_CLK_B,
    "点击量：品牌数量":               COL_CLK_B,
    "Clicks: ASIN Count":             COL_CLK_B,
    "Clicks: Brand Count":            COL_CLK_B,
    "点击量:ASIN 占比%":              "Clicks: Brand Share %",
    "点击量：ASIN 占比%":             "Clicks: Brand Share %",
    "Clicks: ASIN Share %":           "Clicks: Brand Share %",
    "Clicks: Brand Share %":          "Clicks: Brand Share %",

    # Cart Adds
    "购物车加入：总数":               COL_CART_T,
    "购物车加入:总数":                COL_CART_T,
    "Cart Adds: Total Count":         COL_CART_T,
    "购物车加入：ASIN 数量":          COL_CART_B,
    "购物车加入:ASIN 数量":           COL_CART_B,
    "购物车加入：品牌数量":           COL_CART_B,
    "Cart Adds: ASIN Count":          COL_CART_B,
    "Cart Adds: Brand Count":         COL_CART_B,
    "购物车加入：ASIN 占比%":         "Cart Adds: Brand Share %",
    "购物车加入:ASIN 占比%":          "Cart Adds: Brand Share %",

    # Purchases
    "购买量：总数":                   COL_PUR_T,
    "购买量:总数":                    COL_PUR_T,
    "Purchases: Total Count":         COL_PUR_T,
    "购买量：ASIN 数量":              COL_PUR_B,
    "购买量:ASIN 数量":               COL_PUR_B,
    "购买量：品牌数量":               COL_PUR_B,
    "Purchases: ASIN Count":          COL_PUR_B,
    "Purchases: Brand Count":         COL_PUR_B,
    "购买量：ASIN 占比%":             COL_PUR_BSHARE,
    "购买量:ASIN 占比%":              COL_PUR_BSHARE,
    "Purchases: ASIN Share %":        COL_PUR_BSHARE,
    "Purchases: Brand Share %":       COL_PUR_BSHARE,
    "购买量：购买率%":                COL_PUR_RATE,
    "购买量:购买率%":                 COL_PUR_RATE,
    "Purchases: Purchase Rate %":     COL_PUR_RATE,
}

ALL_BRAND  = [COL_IMP_B, COL_CLK_B, COL_CART_B, COL_PUR_B]
ALL_TOTAL  = [COL_IMP_T, COL_CLK_T, COL_CART_T, COL_PUR_T]
EXTRA_COLS = [COL_PUR_RATE, COL_IMP_BSHARE, COL_PUR_BSHARE]

PCT_COLS = {
    COL_IMP_B:  "pct_brand_imp",
    COL_CLK_B:  "pct_brand_clk",
    COL_CART_B: "pct_brand_cart",
    COL_PUR_B:  "pct_brand_pur",
}

METRICS = [
    ("曝光", COL_IMP_B,  COL_IMP_T),
    ("点击", COL_CLK_B,  COL_CLK_T),
    ("加购", COL_CART_B, COL_CART_T),
    ("购买", COL_PUR_B,  COL_PUR_T),
]

WEEK_PATTERN = re.compile(r"Week_(\d{4})_(\d{2})_(\d{2})\.csv$", re.I)
TOP_N        = 10
TOP_N_WEEKLY = 25


# ══════════════════════════════════════════════════════════════════════════
# Data Loading & Enrichment
# ══════════════════════════════════════════════════════════════════════════

def week_end_from_path(path: Path) -> Optional[str]:
    m = WEEK_PATTERN.search(path.name)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def _rename_columns_to_standard(df: pd.DataFrame) -> pd.DataFrame:
    """把 CSV 里的中文 / ASIN View 列名改写成脚本内部使用的标准英文列名。
    不识别的列原样保留。"""
    # 优先处理完全匹配；去掉两端空白做次级匹配
    rename_map = {}
    for col in list(df.columns):
        stripped = col.strip() if isinstance(col, str) else col
        if col in COLUMN_ALIASES:
            rename_map[col] = COLUMN_ALIASES[col]
        elif stripped in COLUMN_ALIASES:
            rename_map[col] = COLUMN_ALIASES[stripped]
    if rename_map:
        df = df.rename(columns=rename_map)
    return df


def _derive_week_from_report_date(df: pd.DataFrame) -> Optional[str]:
    """若 CSV 里有"报告日期" / "Report Date"列，取其最后一个值作为 week_end。
    值形如 '2026-05-03' 或 '2026/5/3' 或 '2026-05-03 to 2026-05-09'。"""
    for col in ["报告日期", "Report Date", "报表日期", "Reporting Date"]:
        if col in df.columns:
            vals = df[col].dropna().astype(str).tolist()
            if not vals:
                continue
            raw = vals[0].strip()
            # 抓第一个 YYYY-MM-DD / YYYY/MM/DD / YYYY_MM_DD
            import re as _re
            m = _re.search(r"(\d{4})[-/_](\d{1,2})[-/_](\d{1,2})", raw)
            if m:
                return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return None


def _load_csv_smart_header(path: Path) -> pd.DataFrame:
    """自动判断 CSV 的表头行位置。
    - Amazon 官方导出：第 1 行是元数据（如 "Search Query Performance..."），第 2 行才是表头
    - 前台复制 / 其它工具导出：第 1 行就是表头
    用两次读取对比列数决定：若 skiprows=0 的列数 < skiprows=1 的列数，说明需要跳过首行。
    """
    import pandas as _pd
    try:
        df0 = _pd.read_csv(path, nrows=0, low_memory=False)
        try:
            df1 = _pd.read_csv(path, skiprows=1, nrows=0, low_memory=False)
        except Exception:
            df1 = None
    except Exception:
        # 读不出来就试常规方案
        return _pd.read_csv(path, skiprows=1, low_memory=False)

    cols0 = len(df0.columns) if df0 is not None else 0
    cols1 = len(df1.columns) if df1 is not None else 0

    # 启发式：
    # 1) 如果 skiprows=0 只有 1 列（典型的 Amazon 元数据行），明确走 skiprows=1
    # 2) 如果 skiprows=0 的列数 >= skiprows=1 的列数，且都 > 3，说明首行已经是表头
    # 3) 否则默认 skiprows=1（保持兼容 Amazon 官方导出）
    if cols0 == 1 and cols1 > 1:
        return _pd.read_csv(path, skiprows=1, low_memory=False)
    if cols0 >= cols1 and cols0 > 3:
        # 首行就是表头
        return _pd.read_csv(path, low_memory=False)
    return _pd.read_csv(path, skiprows=1, low_memory=False)


def load_sq_csv(path: Path) -> pd.DataFrame:
    """Load one SQP CSV, 自适应表头位置 + 中英文列名。"""
    df = _load_csv_smart_header(path)
    df = _rename_columns_to_standard(df)

    # 解析周次：文件名 > 报告日期列 > mtime
    wk = week_end_from_path(path)
    source = "filename"
    if wk is None:
        wk = _derive_week_from_report_date(df)
        source = "report_date_col"
    if wk is None:
        from datetime import datetime as _dt
        wk = _dt.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")
        source = "file_mtime"
        print(f"  ⚠ {path.name}: 文件名与报告日期列均无周次信息，使用文件修改时间 {wk}", file=sys.stderr)

    df["week_end_label"] = wk
    df["source_file"]    = path.name
    df["_week_source"]   = source

    for c in ALL_BRAND + ALL_TOTAL:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    for c in EXTRA_COLS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """Add per-week brand portfolio share columns (% of brand weekly total)."""
    parts = []
    for _, chunk in df.groupby("week_end_label", sort=True):
        out = chunk.copy()
        for b_col, pct_col in PCT_COLS.items():
            total = out[b_col].sum()
            out[pct_col] = (out[b_col] / total * 100).round(3) if total > 0 else 0.0
        parts.append(out)
    return pd.concat(parts, ignore_index=True)


# ══════════════════════════════════════════════════════════════════════════
# WoW Helpers
# ══════════════════════════════════════════════════════════════════════════

def wow_rate(curr: float, prev: float) -> Optional[float]:
    return (curr - prev) / prev if prev != 0 else None


def judgment(b_rate: Optional[float], m_rate: Optional[float]) -> str:
    """Return Chinese direction label comparing brand WoW vs market WoW."""
    def _na(x): return x is None or (isinstance(x, float) and math.isnan(x))
    if _na(b_rate): return "品牌上周无数据"
    if _na(m_rate):
        if b_rate > 0.01:  return "大盘上周为零；品牌上涨"
        if b_rate < -0.01: return "大盘上周为零；品牌下跌"
        return "大盘上周为零；品牌持平"
    b_up, m_up = b_rate >= 0, m_rate >= 0
    if b_up and m_up:
        if abs(m_rate) < 0.005: return "大盘近乎持平，品牌上涨"
        r = b_rate / m_rate
        return "↑↑ 比大盘涨得快" if r > 1.5 else ("↑ 与大盘同步上涨" if r >= 0.7 else "↑↓ 比大盘涨得慢")
    if not b_up and not m_up:
        if abs(m_rate) < 0.005: return "大盘近乎持平，品牌下跌"
        r = b_rate / m_rate
        return "↓↓ 比大盘跌得快" if r > 1.5 else ("↓ 与大盘同步下跌" if r >= 0.7 else "↓↑ 比大盘跌得慢")
    if b_up and not m_up: return "⚡ 逆势上涨（大盘跌，品牌涨）"
    return "⚠ 逆势下跌（大盘涨，品牌跌）"


def merge_wow(
    prev: pd.DataFrame, curr: pd.DataFrame, b_col: str, t_col: str
) -> pd.DataFrame:
    p = prev.set_index(COL_Q)[[b_col, t_col]].rename(
        columns={b_col: "b_prev", t_col: "t_prev"})
    c = curr.set_index(COL_Q)[[b_col, t_col]].rename(
        columns={b_col: "b_curr", t_col: "t_curr"})
    m = c.join(p, how="inner").reset_index()
    m["b_wow_abs"]  = m["b_curr"] - m["b_prev"]
    m["b_wow_rate"] = m.apply(lambda r: wow_rate(r["b_curr"], r["b_prev"]), axis=1)
    m["t_wow_rate"] = m.apply(lambda r: wow_rate(r["t_curr"], r["t_prev"]), axis=1)
    def _rel(r):
        bw, tw = r["b_wow_rate"], r["t_wow_rate"]
        if bw is None or tw is None or tw == 0: return None
        if isinstance(bw, float) and math.isnan(bw): return None
        if isinstance(tw, float) and math.isnan(tw): return None
        return bw / tw
    m["relative"] = m.apply(_rel, axis=1)
    m["判断"]      = m.apply(lambda r: judgment(r["b_wow_rate"], r["t_wow_rate"]), axis=1)
    return m


# ══════════════════════════════════════════════════════════════════════════
# Analysis Modules  →  each returns a DataFrame
# ══════════════════════════════════════════════════════════════════════════

def compute_portfolio(df: pd.DataFrame) -> pd.DataFrame:
    keep = (
        ["week_end_label", COL_Q]
        + ALL_BRAND
        + list(PCT_COLS.values())
        + ALL_TOTAL
    )
    return df[[c for c in keep if c in df.columns]].copy()


def compute_high_conv(df: pd.DataFrame) -> pd.DataFrame:
    """Terms where Purchase Rate % / Brand Impression Share % >= 1."""
    results = []
    for wk, chunk in df.groupby("week_end_label", sort=True):
        c = chunk.copy()
        valid = c[COL_IMP_BSHARE].notna() & (c[COL_IMP_BSHARE] > 0)
        c["conv_ratio"] = None
        c.loc[valid, "conv_ratio"] = (
            c.loc[valid, COL_PUR_RATE] / c.loc[valid, COL_IMP_BSHARE]
        ).round(3)
        results.append(c[c["conv_ratio"] >= 1].copy())
    if not results:
        return pd.DataFrame()
    out = pd.concat(results, ignore_index=True)
    keep = ["week_end_label", COL_Q, "conv_ratio",
            COL_PUR_RATE, COL_IMP_BSHARE, COL_PUR_BSHARE] + ALL_BRAND
    return out[[c for c in keep if c in out.columns]]


def compute_wow_new_dropped(df: pd.DataFrame) -> pd.DataFrame:
    weeks = sorted(df["week_end_label"].unique())
    rows = []
    for i in range(len(weeks) - 1):
        pw, cw = weeks[i], weeks[i + 1]
        prev_t = set(df[df["week_end_label"] == pw][COL_Q])
        curr_t = set(df[df["week_end_label"] == cw][COL_Q])
        for t in sorted(curr_t - prev_t):
            rows.append({"prev_week": pw, "curr_week": cw, "status": "新入列", COL_Q: t})
        for t in sorted(prev_t - curr_t):
            rows.append({"prev_week": pw, "curr_week": cw, "status": "跌出列", COL_Q: t})
    return pd.DataFrame(rows)


def compute_wow_self_drops(df: pd.DataFrame) -> pd.DataFrame:
    weeks = sorted(df["week_end_label"].unique())
    rows = []
    for i in range(len(weeks) - 1):
        pw, cw = weeks[i], weeks[i + 1]
        prev = df[df["week_end_label"] == pw]
        curr = df[df["week_end_label"] == cw]
        for label, b_col, t_col in METRICS:
            m = merge_wow(prev, curr, b_col, t_col)
            # 强制转数值 + 去掉无效行
            m["b_wow_abs"] = pd.to_numeric(m["b_wow_abs"], errors="coerce")
            m = m.dropna(subset=["b_wow_abs"])
            if m.empty:
                continue
            for _, row in m.nsmallest(TOP_N, "b_wow_abs").iterrows():
                rows.append({
                    "prev_week": pw, "curr_week": cw, "metric": label,
                    COL_Q: row[COL_Q],
                    "b_prev": row["b_prev"], "b_curr": row["b_curr"],
                    "b_wow_abs": row["b_wow_abs"],
                    "b_wow_rate": row["b_wow_rate"],
                })
    return pd.DataFrame(rows)


def compute_wow_market_dev(df: pd.DataFrame) -> pd.DataFrame:
    weeks = sorted(df["week_end_label"].unique())
    rows = []
    for i in range(len(weeks) - 1):
        pw, cw = weeks[i], weeks[i + 1]
        prev = df[df["week_end_label"] == pw]
        curr = df[df["week_end_label"] == cw]
        for label, b_col, t_col in METRICS:
            m = merge_wow(prev, curr, b_col, t_col)
            valid = m.dropna(subset=["b_wow_rate", "t_wow_rate"]).copy()
            # 强制转数值 (None/str 混入时需要)
            valid["b_wow_rate"] = pd.to_numeric(valid["b_wow_rate"], errors="coerce")
            valid["t_wow_rate"] = pd.to_numeric(valid["t_wow_rate"], errors="coerce")
            valid = valid.dropna(subset=["b_wow_rate", "t_wow_rate"])
            valid["deviation"] = (valid["b_wow_rate"] - valid["t_wow_rate"]).abs()
            if valid.empty:
                continue
            for _, row in valid.nlargest(TOP_N, "deviation").iterrows():
                rows.append({
                    "prev_week": pw, "curr_week": cw, "metric": label,
                    COL_Q: row[COL_Q],
                    "b_curr": row["b_curr"], "b_prev": row["b_prev"],
                    "b_wow_rate": row["b_wow_rate"],
                    "t_wow_rate": row["t_wow_rate"],
                    "relative": row["relative"],
                    "判断": row["判断"],
                })
    return pd.DataFrame(rows)


def compute_top5(df: pd.DataFrame):
    """Top 5 terms: most weeks + highest avg brand impression share."""
    def _bshare(g):
        safe = g[COL_IMP_T].replace(0, float("nan"))
        return (g[COL_IMP_B] / safe * 100).mean()

    try:
        stats = (
            df.groupby(COL_Q, sort=False)
            .apply(
                lambda g: pd.Series({
                    "week_count":      g["week_end_label"].nunique(),
                    "avg_brand_share": _bshare(g),
                    "avg_imp_b":       g[COL_IMP_B].mean(),
                }),
                include_groups=False,
            )
            .reset_index()
        )
    except TypeError:
        stats = (
            df.groupby(COL_Q, sort=False)
            .apply(lambda g: pd.Series({
                "week_count":      g["week_end_label"].nunique(),
                "avg_brand_share": _bshare(g),
                "avg_imp_b":       g[COL_IMP_B].mean(),
            }))
            .reset_index()
        )
        if COL_Q in stats.columns[1:]:
            stats = stats.loc[:, ~stats.columns.duplicated()]

    max_wks  = int(stats["week_count"].max())
    top5     = (
        stats[stats["week_count"] == max_wks]
        .nlargest(5, "avg_brand_share")
        .reset_index(drop=True)
    )
    top5_terms = top5[COL_Q].tolist()

    detail_cols = (
        [COL_Q, "week_end_label"]
        + ALL_TOTAL + ALL_BRAND
    )
    detail = (
        df[df[COL_Q].isin(top5_terms)]
        [[c for c in detail_cols if c in df.columns]]
        .sort_values([COL_Q, "week_end_label"])
        .copy()
    )
    safe = detail[COL_IMP_T].replace(0, float("nan"))
    detail["brand_imp_share_%"] = (detail[COL_IMP_B] / safe * 100).round(3)

    return top5_terms, detail, top5


# ══════════════════════════════════════════════════════════════════════════
# Chart
# ══════════════════════════════════════════════════════════════════════════

def setup_font():
    available = {f.name for f in fm.fontManager.ttflist}
    for fn in ["PingFang HK", "STHeiti", "Heiti TC", "Arial Unicode MS", "SimHei"]:
        if fn in available:
            matplotlib.rcParams["font.family"] = fn
            break
    matplotlib.rcParams["axes.unicode_minus"] = False


def make_top5_chart(df: pd.DataFrame, top5_terms: List[str], out_path: Path):
    if not top5_terms:
        return
    setup_font()
    COLORS = ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B2"]
    n = len(top5_terms)
    fig, axes = plt.subplots(n, 2, figsize=(15, 4.5 * n))
    if n == 1:
        axes = [axes]
    fig.suptitle(
        f"Top {n} 高频 & 高品牌占比搜索词 ｜ 趋势分析\n"
        "左：大盘总曝光量（柱+线）  右：品牌曝光占比 % = 品牌曝光 ÷ 大盘曝光",
        fontsize=13, y=1.01,
    )
    for i, term in enumerate(top5_terms):
        t = df[df[COL_Q] == term].sort_values("week_end_label").reset_index(drop=True)
        x_lbl  = t["week_end_label"].tolist()
        x_pos  = list(range(len(x_lbl)))
        y_mkt  = t[COL_IMP_T]
        safe   = t[COL_IMP_T].replace(0, float("nan"))
        y_bsh  = (t[COL_IMP_B] / safe * 100).round(3)
        color  = COLORS[i % len(COLORS)]

        ax_l = axes[i][0]
        ax_l.bar(x_pos, y_mkt, color=color, alpha=0.65, width=0.55)
        ax_l.plot(x_pos, y_mkt, color=color, marker="o", linewidth=2)
        for xi, yi in zip(x_pos, y_mkt):
            ax_l.annotate(f"{int(yi):,}", (xi, yi),
                          textcoords="offset points", xytext=(0, 6),
                          ha="center", fontsize=8)
        ax_l.set_title(f"[{i+1}] {term[:48]}\n大盘总曝光量", fontsize=9)
        ax_l.set_xticks(x_pos)
        ax_l.set_xticklabels(x_lbl, rotation=25, ha="right", fontsize=8)
        ax_l.set_ylabel("大盘曝光量", fontsize=9)
        ax_l.yaxis.set_major_formatter(
            mticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
        ax_l.set_ylim(0, y_mkt.max() * 1.25)
        ax_l.grid(axis="y", linestyle="--", alpha=0.4)

        ax_r = axes[i][1]
        ax_r.plot(x_pos, y_bsh, color=color, marker="o", linewidth=2.5)
        ax_r.fill_between(x_pos, y_bsh, alpha=0.15, color=color)
        for xi, yi in zip(x_pos, y_bsh):
            if not (isinstance(yi, float) and math.isnan(yi)):
                ax_r.annotate(f"{yi:.2f}%", (xi, yi),
                              textcoords="offset points", xytext=(0, 7),
                              ha="center", fontsize=9, fontweight="bold", color=color)
        ax_r.set_title(f"[{i+1}] {term[:48]}\n品牌曝光占比 %", fontsize=9)
        ax_r.set_xticks(x_pos)
        ax_r.set_xticklabels(x_lbl, rotation=25, ha="right", fontsize=8)
        ax_r.set_ylabel("品牌曝光占比 %", fontsize=9)
        ax_r.yaxis.set_major_formatter(
            mticker.FuncFormatter(lambda v, _: f"{v:.1f}%"))
        y_max = y_bsh.dropna().max() if not y_bsh.dropna().empty else 1
        ax_r.set_ylim(0, max(y_max * 1.35, 1))
        ax_r.grid(axis="y", linestyle="--", alpha=0.4)

    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ✓ Chart → {out_path.name}")


# ══════════════════════════════════════════════════════════════════════════
# Markdown Report
# ══════════════════════════════════════════════════════════════════════════

def _df_to_md(df: pd.DataFrame, max_rows: int = 60) -> str:
    """Render DataFrame as a plain markdown table (no tabulate dependency)."""
    if df is None or df.empty:
        return "_（无数据）_"
    d = df.head(max_rows).copy().reset_index(drop=True)
    for col in d.select_dtypes(include="float").columns:
        d[col] = d[col].apply(
            lambda x: f"{x:.3f}" if pd.notna(x) else "—"
        )
    d = d.infer_objects(copy=False).fillna("—").astype(str)
    cols = list(d.columns)
    sep  = "| " + " | ".join("---" for _ in cols) + " |"
    hdr  = "| " + " | ".join(cols) + " |"
    body = "\n".join(
        "| " + " | ".join(str(v) for v in row) + " |"
        for _, row in d.iterrows()
    )
    return "\n".join([hdr, sep, body])


def _fmt_rate(x) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    return f"{x * 100:+.1f}%"


def _fmt_rel(x) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    return f"{x:.2f}x"


def build_markdown(
    df, weeks, portfolio, high_conv, wow_nd, wow_self, wow_mkt,
    top5_terms, top5_detail, top5_stats, source_files,
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = []

    # ── Cover ─────────────────────────────────────────────────────────────
    lines += [
        "# SQP 品牌搜索词分析报告",
        "",
        f"> **生成时间**：{now}",
        f"> **分析周次**：{weeks[0]} → {weeks[-1]}（共 {len(weeks)} 周）",
        f"> **数据来源**：{chr(10).join('> - ' + f for f in source_files)}",
        "",
        "## 目录",
        "1. [每周品牌数据快照](#一每周品牌数据快照)",
        "2. [每周转化能力高于类目的词](#二每周转化能力高于类目的词)",
        "3. [周对周：新入列 & 跌出列](#三周对周新入列--跌出列)",
        "4. [周对周：和自己比（品牌减少最多）](#四周对周和自己比品牌减少最多)",
        "5. [周对周：和大盘比（偏离最大）](#五周对周和大盘比偏离最大)",
        "6. [全周期 Top 5 高价值词](#六全周期-top-5-高价值词)",
        "",
        "---",
        "",
    ]

    # ── Section 1: Weekly Portfolio ───────────────────────────────────────
    lines += [
        "## 一、每周品牌数据快照",
        "",
        "| 列名 | 含义 |",
        "|---|---|",
        "| `pct_brand_imp` | 该词品牌曝光 ÷ 当周品牌总曝光 × 100% |",
        "| `pct_brand_clk` | 该词品牌点击 ÷ 当周品牌总点击 × 100% |",
        "| `pct_brand_cart` | 该词品牌加购 ÷ 当周品牌总加购 × 100% |",
        "| `pct_brand_pur` | 该词品牌购买 ÷ 当周品牌总购买 × 100% |",
        "",
    ]
    for wk in weeks:
        chunk = df[df["week_end_label"] == wk]
        tot   = "  ".join(
            f"**{lbl}**={int(chunk[b].sum()):,}" for lbl, b, _ in METRICS
        )
        lines += [f"### 周结束 {wk}", "", f"品牌总量：{tot}", ""]
        sub = portfolio[portfolio["week_end_label"] == wk]
        sub = sub.nlargest(TOP_N_WEEKLY, COL_IMP_B)
        cols_show = [COL_Q, COL_IMP_B, "pct_brand_imp",
                     COL_CLK_B, "pct_brand_clk",
                     COL_CART_B, "pct_brand_cart",
                     COL_PUR_B,  "pct_brand_pur"]
        sub = sub[[c for c in cols_show if c in sub.columns]].copy()
        sub.columns = (
            ["搜索词", "品牌曝光", "曝光占比%",
             "品牌点击", "点击占比%",
             "品牌加购", "加购占比%",
             "品牌购买", "购买占比%"][:len(sub.columns)]
        )
        lines += [_df_to_md(sub, max_rows=TOP_N_WEEKLY), "", ""]

    lines += ["---", ""]

    # ── Section 2: High Conversion ────────────────────────────────────────
    lines += [
        "## 二、每周转化能力高于类目的词",
        "",
        "> **筛选**：`Purchases: Purchase Rate %` ÷ `Impressions: Brand Share %` ≥ 1  ",
        "> 表示该词在类目层面购买转化率 ≥ 品牌在该词的曝光占比 → **高潜力、值得加大投放的词**",
        "",
    ]
    for wk in weeks:
        sub = (
            high_conv[high_conv["week_end_label"] == wk]
            if not high_conv.empty else pd.DataFrame()
        )
        lines += [f"### 周结束 {wk}（{len(sub)} 个词）", ""]
        if sub.empty:
            lines += ["_（无符合条件的词）_", ""]
        else:
            d = sub.drop(columns=["week_end_label"], errors="ignore").copy()
            d = d.rename(columns={
                COL_Q: "搜索词", "conv_ratio": "购买率/曝光占比",
                COL_PUR_RATE: "类目购买率%", COL_IMP_BSHARE: "品牌曝光占比%",
                COL_PUR_BSHARE: "品牌购买占比%",
                COL_IMP_B: "品牌曝光", COL_CLK_B: "品牌点击",
                COL_CART_B: "品牌加购", COL_PUR_B: "品牌购买",
            })
            lines += [_df_to_md(d.reset_index(drop=True), max_rows=50), ""]

    lines += ["---", ""]

    # ── Section 3: WoW New / Dropped ──────────────────────────────────────
    lines += ["## 三、周对周：新入列 & 跌出列", ""]
    for i in range(len(weeks) - 1):
        pw, cw = weeks[i], weeks[i + 1]
        lines += [f"### {pw} → {cw}", ""]
        for status in ["新入列", "跌出列"]:
            sub = (
                wow_nd[
                    (wow_nd["prev_week"] == pw) &
                    (wow_nd["curr_week"] == cw) &
                    (wow_nd["status"] == status)
                ] if not wow_nd.empty else pd.DataFrame()
            )
            lines += [f"#### {status}（{len(sub)} 个词）", ""]
            if sub.empty:
                lines += ["_（无）_", ""]
            else:
                lines += [_df_to_md(sub[[COL_Q]].rename(columns={COL_Q: "搜索词"})
                                    .reset_index(drop=True), max_rows=30), ""]

    lines += ["---", ""]

    # ── Section 4: WoW Self Comparison ───────────────────────────────────
    lines += [
        "## 四、周对周：【和自己比】品牌各指标减少最多 Top 10",
        "",
    ]
    for i in range(len(weeks) - 1):
        pw, cw = weeks[i], weeks[i + 1]
        lines += [f"### {pw} → {cw}", ""]
        for label, _, _ in METRICS:
            sub = (
                wow_self[
                    (wow_self["prev_week"] == pw) &
                    (wow_self["curr_week"] == cw) &
                    (wow_self["metric"] == label)
                ] if not wow_self.empty else pd.DataFrame()
            )
            lines += [f"#### 品牌{label}减少最多 Top {TOP_N}", ""]
            if sub.empty:
                lines += ["_（无数据）_", ""]
            else:
                d = sub[[COL_Q, "b_prev", "b_curr", "b_wow_abs", "b_wow_rate"]].copy()
                d["b_wow_rate"] = d["b_wow_rate"].apply(_fmt_rate)
                d.columns = ["搜索词", f"上周品牌{label}",
                             f"本周品牌{label}", f"{label}绝对变化", f"{label}变化率"]
                lines += [_df_to_md(d.reset_index(drop=True)), ""]

    lines += ["---", ""]

    # ── Section 5: WoW Market Comparison ────────────────────────────────
    lines += [
        "## 五、周对周：【和大盘比】品牌波动偏离大盘最大 Top 10",
        "",
        "> **排序依据**：`|品牌WoW率 - 大盘WoW率|` 最大  ",
        "> **相对变化比** = 品牌WoW率 ÷ 大盘WoW率",
        "",
    ]
    for i in range(len(weeks) - 1):
        pw, cw = weeks[i], weeks[i + 1]
        lines += [f"### {pw} → {cw}", ""]
        for label, _, _ in METRICS:
            sub = (
                wow_mkt[
                    (wow_mkt["prev_week"] == pw) &
                    (wow_mkt["curr_week"] == cw) &
                    (wow_mkt["metric"] == label)
                ] if not wow_mkt.empty else pd.DataFrame()
            )
            lines += [f"#### {label}：偏离大盘 Top {TOP_N}", ""]
            if sub.empty:
                lines += ["_（无数据）_", ""]
            else:
                d = sub[
                    [COL_Q, "b_curr", "b_prev", "b_wow_rate", "t_wow_rate", "relative", "判断"]
                ].copy()
                d["b_wow_rate"] = d["b_wow_rate"].apply(_fmt_rate)
                d["t_wow_rate"] = d["t_wow_rate"].apply(_fmt_rate)
                d["relative"]   = d["relative"].apply(_fmt_rel)
                d.columns = ["搜索词", f"本周品牌{label}", f"上周品牌{label}",
                             f"品牌{label}WoW", f"大盘{label}WoW",
                             "品牌/大盘变化比", "判断"]
                lines += [_df_to_md(d.reset_index(drop=True)), ""]

    lines += ["---", ""]

    # ── Section 6: Top 5 Stable Terms ────────────────────────────────────
    lines += [
        "## 六、全周期 Top 5 高价值词",
        "",
        "**筛选**：出现周数最多 → 平均品牌曝光占比最高 → 取 Top 5",
        "",
    ]
    if top5_stats is not None and not top5_stats.empty:
        st = top5_stats[[COL_Q, "week_count", "avg_brand_share", "avg_imp_b"]].copy()
        st.columns = ["搜索词", "出现周数", "平均品牌曝光占比%", "平均品牌曝光量"]
        lines += ["### 词汇总览", "", _df_to_md(st), ""]

    lines += ["### 逐周明细", ""]
    if top5_detail is not None and not top5_detail.empty:
        d = top5_detail.rename(columns={
            COL_Q: "搜索词", "week_end_label": "周",
            COL_IMP_T: "大盘曝光", COL_IMP_B: "品牌曝光",
            "brand_imp_share_%": "品牌曝光占比%",
            COL_CLK_T: "大盘点击", COL_CLK_B: "品牌点击",
            COL_CART_T: "大盘加购", COL_CART_B: "品牌加购",
            COL_PUR_T: "大盘购买", COL_PUR_B: "品牌购买",
        })
        lines += [_df_to_md(d, max_rows=100), ""]

    lines += [
        "---",
        "",
        f"_报告由 `sqp_report.py` 自动生成 @ {now}_",
    ]
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════

def resolve_inputs(raw: List[str]) -> List[Path]:
    """Expand globs, accept directories, single files, or lists."""
    paths = []
    for r in raw:
        expanded = glob.glob(r)
        if expanded:
            paths.extend(Path(p) for p in expanded)
        elif Path(r).is_dir():
            paths.extend(sorted(Path(r).glob("*.csv")))
        elif Path(r).is_file():
            paths.append(Path(r))
        else:
            print(f"  ⚠ No match for: {r}", file=sys.stderr)
    return sorted(set(paths))


def run_sqp_pipeline(input_paths: List[Path], out_dir: Path,
                     silent: bool = False) -> dict:
    """程序化入口：供 Flask 调用。

    Args:
        input_paths: SQP CSV 文件路径列表（必须已经是具体文件）
        out_dir: 输出目录（会自动创建）
        silent: True 时抑制 stdout 输出

    Returns:
        {
          "weeks": [...],                     # 所有检测到的周
          "source_files": [...],              # 源文件名
          "outputs": {                        # 生成文件名 -> 相对路径
             "sqp_report.md": "sqp_report.md",
             "sqp_top5_trend.png": "...",
             ...
          },
          "summary": {
             "total_weeks": N,
             "total_terms_weekly_portfolio": int,
             "high_conv_terms_count": int,
             "wow_new_count": int,
             "wow_dropped_count": int,
             "top5_terms": [...],
             "brand_totals": {"曝光": ..., "点击": ..., ...}  # 最新一周
          }
        }
    """
    def _say(msg):
        if not silent:
            print(msg)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not input_paths:
        raise ValueError("input_paths 为空")

    _say(f"Loading {len(input_paths)} file(s)…")
    for p in input_paths:
        _say(f"  {p.name}")

    df = enrich(pd.concat([load_sq_csv(p) for p in input_paths],
                          ignore_index=True))
    weeks = sorted(df["week_end_label"].unique())
    _say(f"Weeks found: {weeks}")

    portfolio = compute_portfolio(df)
    high_conv = compute_high_conv(df)
    wow_nd    = compute_wow_new_dropped(df)
    wow_self  = compute_wow_self_drops(df)
    wow_mkt   = compute_wow_market_dev(df)
    top5_terms, top5_detail, top5_stats = compute_top5(df)

    # 保存 6 个 CSV
    saves = {
        "weekly_brand_portfolio.csv": portfolio,
        "high_conv_terms.csv":        high_conv,
        "wow_new_dropped.csv":        wow_nd,
        "wow_self_drops.csv":         wow_self,
        "wow_market_deviation.csv":   wow_mkt,
        "top5_stable_terms.csv":      top5_detail,
    }
    for fname, data in saves.items():
        (out_dir / fname).parent.mkdir(parents=True, exist_ok=True)
        data.to_csv(out_dir / fname, index=False, encoding="utf-8-sig")
        _say(f"  ✓ {fname} ({len(data)} rows)")

    # 图表
    chart_path = out_dir / "sqp_top5_trend.png"
    try:
        make_top5_chart(df, top5_terms, chart_path)
    except Exception as e:
        _say(f"  ⚠ chart generation failed: {e}")

    # Markdown
    md = build_markdown(
        df=df, weeks=weeks,
        portfolio=portfolio, high_conv=high_conv,
        wow_nd=wow_nd, wow_self=wow_self, wow_mkt=wow_mkt,
        top5_terms=top5_terms, top5_detail=top5_detail, top5_stats=top5_stats,
        source_files=[p.name for p in input_paths],
    )
    md_path = out_dir / "sqp_report.md"
    md_path.write_text(md, encoding="utf-8")
    _say(f"  ✓ sqp_report.md ({len(md.splitlines())} lines)")

    # 摘要（给 API 用）
    wow_new_count = 0
    wow_dropped_count = 0
    if not wow_nd.empty:
        wow_new_count     = int((wow_nd["status"] == "新入列").sum())
        wow_dropped_count = int((wow_nd["status"] == "跌出列").sum())

    brand_totals = {}
    if weeks:
        latest = df[df["week_end_label"] == weeks[-1]]
        for label, b_col, _ in METRICS:
            if b_col in latest.columns:
                brand_totals[label] = int(latest[b_col].sum())

    outputs = {name: name for name in list(saves.keys())
               + ["sqp_top5_trend.png", "sqp_report.md"]
               if (out_dir / name).exists()}

    return {
        "weeks": weeks,
        "source_files": [p.name for p in input_paths],
        "outputs": outputs,
        "summary": {
            "total_weeks": len(weeks),
            "total_terms_weekly_portfolio": int(len(portfolio)),
            "high_conv_terms_count": int(len(high_conv)),
            "wow_new_count": wow_new_count,
            "wow_dropped_count": wow_dropped_count,
            "top5_terms": list(top5_terms),
            "brand_totals_latest_week": brand_totals,
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description="SQP Brand Analysis Report Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--input", nargs="+", required=True,
        help='CSV files, glob pattern, or directory. '
             'E.g. --input "sqp/*.csv"  or  --input wk1.csv wk2.csv',
    )
    parser.add_argument(
        "--output", default="./sqp_output",
        help="Output directory (default: ./sqp_output)",
    )
    args = parser.parse_args()

    input_paths = resolve_inputs(args.input)
    if not input_paths:
        print("Error: no CSV files found. Check --input path.", file=sys.stderr)
        sys.exit(1)

    result = run_sqp_pipeline(input_paths, Path(args.output))
    print(f"\n{'='*50}")
    print(f"✅  Done!  Weeks: {result['weeks']}")
    print(f"   High conv terms: {result['summary']['high_conv_terms_count']}")
    print(f"   Top5: {result['summary']['top5_terms']}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
