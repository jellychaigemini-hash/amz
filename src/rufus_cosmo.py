"""
Rufus & COSMO Algorithm Integration Module
============================================
Integrates Rufus/COSMO/GEO algorithmic principles into the GPT Image-2 prompt generation pipeline.
Loaded from local Wiki/06-Rufus-Cosmo/ — no external F: drive dependency.

Usage:
    from rufus_cosmo import RufusCosmoEngine
    engine = RufusCosmoEngine()
    context = engine.enrich_context(base_context)
    prompt_hints = engine.get_prompt_hints(category, style)
"""
# Reconstructed from rufus_cosmo.pyc (Python 3.14).
# All string constants, category mappings, and COSMO relation dicts are
# preserved verbatim from the bytecode.

from __future__ import annotations

from pathlib import Path


KNOWLEDGE_DIR = Path("Wiki") / "06-Rufus-Cosmo"


# COSMO algorithm's 6 semantic relations. Keys map to bilingual labels and
# guidance pulled from the Wiki algorithms.md.
COSMO_RELATIONS = {
    "used_for": {
        "zh": "用途/使用场景",
        "prompt_guide": "Describe what scenario/purpose the product serves — naturally, not as a label.",
    },
    "capable_of": {
        "zh": "功能/能力",
        "prompt_guide": "Describe what the product can do — show capability through scene, not list.",
    },
    "isA": {
        "zh": "属性/类别归属",
        "prompt_guide": "Ensure the product category and key attributes are clear from context.",
    },
    "cause": {
        "zh": "因果/优势",
        "prompt_guide": "Show cause-and-effect: this material/design choice → this benefit for the user.",
    },
}

# GEO (Generative Engine Optimization) factors.
GEO_FACTORS = {
    "statistics": {
        "weight": "high",
        "guide": "Include specific quantitative data rather than qualitative descriptions.",
    },
    "citations": {
        "weight": "high",
        "guide": "Reference trusted sources, certifications, or authority endorsements.",
    },
    "source_quoting": {
        "guide": "Cite reliable sources for claims. E.g., 'As tested by...' or 'Certified by...'",
    },
    "fluency": {
        "guide": "Ensure natural, fluent language — avoid keyword stuffing.",
    },
    "authority": {
        "weight": "baseline",
        "guide": "Establish brand authority through consistent professional presentation.",
    },
}

# Rufus-relevant product catalog sources and how much weight each carries.
RUFUS_SOURCES = {
    "product_catalog": {
        "zh": "商品目录信息",
        "fields": ["title", "bullets", "description"],
    },
    "reviews": {"zh": "买家评论"},
    "qa": {"zh": "社区问答"},
    "aplus": {"zh": "A+内容/品牌故事"},
    "external": {"zh": "外部网络信息"},
}

# Listing formula from methodology.md
LISTING_FORMULA = {
    "formula": "[品牌] + [ABA核心大词] + [针对竞品痛点改进] + [COSMO场景] + [属性]",
    "rule": "前50字符必须包含最高权重关键词，硬条件前置",
    "structure": "痛点 → 机制/原理 → 结果 → 边界条件",
    "must_have": ["backend_attributes", "images"],
}


class RufusCosmoEngine:
    """Engine that enriches product context and prompt generation with Rufus/COSMO algorithms."""

    def __init__(self):
        self.kb_dir = KNOWLEDGE_DIR
        self._algorithms: str | None = None
        self._methodology: str | None = None

    def load_algorithms(self) -> str:
        if self._algorithms is not None:
            return self._algorithms
        try:
            from wiki_crypto import wiki_read
            self._algorithms = wiki_read("06-Rufus-Cosmo/algorithms.md")
        except Exception:
            path = self.kb_dir / "algorithms.md"
            if path.exists():
                self._algorithms = path.read_text("utf-8")
            else:
                self._algorithms = ""
        return self._algorithms

    def load_methodology(self) -> str:
        if self._methodology is not None:
            return self._methodology
        try:
            from wiki_crypto import wiki_read
            self._methodology = wiki_read("06-Rufus-Cosmo/methodology.md")
        except Exception:
            path = self.kb_dir / "methodology.md"
            if path.exists():
                self._methodology = path.read_text("utf-8")
            else:
                self._methodology = ""
        return self._methodology

    def enrich_context(self, context: dict) -> dict:
        """Enrich a product context dict with Rufus/COSMO algorithmic insights.

        This fills gaps that MCP services leave empty.
        """
        enriched = dict(context)
        if not enriched.get("visual_features"):
            enriched["visual_features"] = self._infer_visual_features(enriched)
        enriched["cosmo_intents"] = self._generate_cosmo_intents(enriched)
        enriched["geo_hints"] = self._generate_geo_hints(enriched)
        enriched["rufus_qa_suggestions"] = self._generate_rufus_qa(enriched)
        enriched["rufus_cosmo_enriched"] = True
        return enriched

    def get_prompt_hints(self, category: str, style: str) -> dict:
        """Get algorithm-driven prompt enhancement hints for a given category and style.

        Returns a dict with:
        - cosmo_relations: which COSMO relations to naturally embed
        - geo_additions: GEO factors to include
        - scene_suggestions: usage scenes that resonate with Rufus
        - constraint_reminders: compliance and quality reminders
        """
        cat = (category or "").lower()
        sty = (style or "").lower()

        cosmo_relations: list[str] = []
        scene_suggestions: list[str] = []

        if sty == "main":
            cosmo_relations.extend([
                "isA: clearly establish product category and type",
                "capable_of: show key features/functionality visually",
                "used_for: show the product in its natural use context",
                "cause: demonstrate how product features create user benefits",
            ])
        elif sty == "detail":
            cosmo_relations.extend([
                "capable_of: highlight material quality and build precision",
                "isA: reinforce premium/quality attributes",
            ])

        # Category-driven scene suggestions
        category_scenes = {
            "health":  ["morning routine", "wellness space", "gym/outdoor workout"],
            "home":    ["living room", "kitchen counter", "bedroom nightstand"],
            "tech":    ["clean desk setup", "modern office", "travel/commute"],
            "fashion": ["urban street", "casual indoor", "professional setting"],
            "beauty":  ["bathroom vanity", "dresser with natural light", "travel bag"],
            "food":    ["dining table", "kitchen workspace", "picnic outdoors"],
            "sports":  ["gym floor", "outdoor trail", "training session"],
        }
        for key, scenes in category_scenes.items():
            if key in cat:
                scene_suggestions.extend(scenes)
                break

        return {
            "cosmo_relations": cosmo_relations,
            "geo_additions": [
                "statistics: include quantifiable product details",
                "authority: consistent professional presentation",
            ],
            "scene_suggestions": scene_suggestions,
            "constraint_reminders": [
                "Avoid keyword stuffing — natural language only (GEO fluency)",
                "Visual details must match product specs (Rufus consistency)",
            ],
        }

    def enhance_prompt(self, prompt_text: str, category: str, style: str) -> str:
        """Add algorithmic enhancement notes to an existing prompt.

        These are appended as natural language hints that guide the image generation
        toward COSMO/Rufus-optimized visual content.
        """
        hints = self.get_prompt_hints(category, style)
        lines = [prompt_text]

        if hints["cosmo_relations"]:
            lines.append(
                "Visual storytelling should convey: "
                + "; ".join(hints["cosmo_relations"])
            )
        if hints["scene_suggestions"] and "scene" not in prompt_text.lower():
            lines.append(
                f"The product should feel at home in contexts like: "
                f"{', '.join(hints['scene_suggestions'])}"
            )
        lines.append("Include specific, quantifiable product details visible in the image.")
        return "\n".join(lines)

    def _infer_visual_features(self, context: dict) -> dict:
        """Infer basic visual features from available context data."""
        vf = {
            "product_shape": "",
            "primary_colors": [],
            "accent_colors": [],
            "materials": [],
            "key_visual_elements": [],
        }

        title = (context.get("title") or "").lower()
        bullets = str(context.get("bullets") or []).lower()
        category = (context.get("category") or "").lower()
        combined = f"{title} {bullets} {category}"

        materials_map = {
            "stainless steel": "stainless steel",
            "wood": "wood",
            "bamboo": "bamboo",
            "glass": "glass",
            "ceramic": "ceramic",
            "silicone": "silicone",
            "plastic": "plastic",
            "aluminum": "aluminum",
            "cotton": "cotton",
            "leather": "leather",
            "metal": "metal",
            "rubber": "rubber",
            "memory foam": "memory foam",
            "fabric": "fabric",
            "mesh": "mesh",
        }
        for needle, label in materials_map.items():
            if needle in combined:
                vf["materials"].append(label)

        return vf

    def _generate_cosmo_intents(self, context: dict) -> list[str]:
        """Generate COSMO intent tags from product context."""
        title = (context.get("title") or "").lower()
        bullets = str(context.get("bullets") or []).lower()
        category = (context.get("category") or "").lower()
        combined = f"{title} {bullets} {category}"

        intent_map = {
            "space_saving": ["space", "compact", "foldable", "stackable", "small", "apartment"],
            "eco":          ["eco-friendly", "sustainable", "recycl", "bamboo", "natural", "organic", "green"],
            "professional": ["professional", "commercial", "studio", "heavy-duty", "industrial"],
            "gift":         ["gift", "present", "holiday", "birthday", "christmas", "valentine", "mother's day"],
            "safe":         ["safe", "bpa-free", "non-toxic", "child-proof", "secure", "food-grade"],
            "easy_use":     ["easy", "simple", "quick", "effortless", "intuitive", "one-touch", "automatic"],
            "durable":      ["durable", "sturdy", "heavy-duty", "long-lasting", "premium", "quality", "built"],
            "portable":     ["travel", "compact", "portable", "lightweight", "carry", "on-the-go", "bag"],
        }
        intents = []
        for key, keywords in intent_map.items():
            if any(k in combined for k in keywords):
                intents.append(key)
        return intents

    def _generate_geo_hints(self, context: dict) -> list[str]:
        """Generate GEO optimization hints based on available data."""
        hints: list[str] = []
        bullets = context.get("bullets") or []
        if len(bullets) >= 3:
            hints.append(
                "Include specific quantitative data in visual presentation (GEO statistics factor)"
            )
        if context.get("review_summary", {}).get("positive"):
            hints.append("Visualize user-validated benefits (GEO citations factor)")
        if context.get("keywords"):
            hints.append(
                "Ensure visual elements reflect key product attributes naturally (not keyword-stuffed)"
            )
        return hints

    def _generate_rufus_qa(self, context: dict) -> list[dict]:
        """Generate suggested Rufus Q&A pairs based on product context."""
        title = context.get("title", "")
        bullets = context.get("bullets", [])
        category = context.get("category", "")

        qa_pairs: list[dict] = [{
            "q": f"Is this {category or 'product'} suitable for daily use?",
            "a": "Yes, designed with practical daily use in mind — built with quality materials for everyday reliability.",
        }]
        if "gift" in str(bullets).lower() or "gift" in title.lower():
            qa_pairs.append({
                "q": "Would this make a good gift?",
                "a": "Absolutely — the elegant presentation and practical functionality make it an excellent gift choice.",
            })
        return qa_pairs


_engine_singleton: RufusCosmoEngine | None = None


def get_engine() -> RufusCosmoEngine:
    """Get or create the singleton RufusCosmoEngine."""
    global _engine_singleton
    if _engine_singleton is None:
        _engine_singleton = RufusCosmoEngine()
    return _engine_singleton
