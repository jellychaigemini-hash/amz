"""
Test the copywriting logic (expert_suggestions) against fake context,
to verify the generator itself works independently of MCP network calls.

Run from the repo root:
  python recovery/tools/test_copywriting.py
"""
import sys
import json
from pathlib import Path

# Make src importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from expert_suggestions import (
    build_cosmo_title, build_cosmo_bullets, build_rufus_qa,
    extract_selling_points, build_data_insights,
)


# A realistic fake product context, shaped the way the code expects.
FAKE_CONTEXT = {
    "asin": "B0DK3RXYY1",
    "marketplace": "US",
    "brand": "NutriFlow",
    "title": "NutriFlow 8-in-1 Magnesium Complex Supplement, 500mg High Absorption, 60-Day Supply, For Sleep Support & Muscle Recovery",
    "category": "Health & Household > Vitamins & Dietary Supplements > Minerals > Magnesium",
    "price": "24.99",
    "rating": "4.5",
    "review_count": "1823",
    "bullets": [
        "HIGH ABSORPTION 500MG MAGNESIUM COMPLEX — Combines 8 bioavailable forms (glycinate, citrate, malate, taurate, etc.) to maximize absorption by up to 90%.",
        "PROMOTES RESTFUL SLEEP — Magnesium glycinate helps regulate melatonin for faster sleep onset and deeper rest; clinically shown to improve sleep quality.",
        "MUSCLE RECOVERY SUPPORT — Magnesium malate reduces muscle soreness after workouts by up to 30%, based on 2023 sports-nutrition trial.",
        "SAFE FOR SENSITIVE GROUPS — Non-GMO, gluten-free, vegan, third-party tested for heavy metals; safe for adults, seniors, and pregnant women (consult physician).",
        "60-DAY SUPPLY, WORRY-FREE WARRANTY — 120 capsules per bottle, manufactured in GMP-certified US facility, with 365-day money-back guarantee.",
    ],
    "keywords": [
        {"keyword": "magnesium supplement", "volume": 50000},
        {"keyword": "magnesium glycinate 500mg", "volume": 30000},
        {"keyword": "sleep support supplement", "volume": 25000},
        {"keyword": "muscle recovery magnesium", "volume": 18000},
        {"keyword": "8 in 1 magnesium", "volume": 12000},
        {"keyword": "magnesium for cramps", "volume": 15000},
    ],
    "sif_keywords": [
        {"keyword": "magnesium supplement", "volume": 50000},
    ],
    "bullets_synthetic": False,
}


def test(name, fn):
    print(f"\n{'=' * 70}\n{name}\n{'=' * 70}")
    try:
        out = fn(FAKE_CONTEXT)
        print(json.dumps(out, ensure_ascii=False, indent=2)[:3000])
    except Exception as e:
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test("1. Title (build_cosmo_title)",      build_cosmo_title)
    test("2. Bullets (build_cosmo_bullets)",  build_cosmo_bullets)
    test("3. Q&A (build_rufus_qa)",           build_rufus_qa)
    test("4. Selling points (extract_selling_points)", extract_selling_points)
    test("5. Data insights (build_data_insights)",    build_data_insights)
    print("\nAll 5 copywriting modules ran without exception.")
