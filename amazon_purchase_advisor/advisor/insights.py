"""Human-readable insights: important feedback and the reasons behind a verdict."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple

from . import config
from .data import Product, Review
from .scoring import Recommendation
from .sentiment import Prediction, SentimentSummary


@dataclass
class Reason:
    tone: str      # "good" | "mixed" | "bad" | "info"
    text: str


def important_feedback(reviews: List[Review], predictions: List[Prediction],
                       label: str, limit: int = 3) -> List[Tuple[Review, Prediction]]:
    """Most informative reviews of one sentiment: helpful votes, model confidence, substance."""
    candidates = [(r, p) for r, p in zip(reviews, predictions) if p.label == label and p.confidence >= 0.5]

    def importance(item):
        review, pred = item
        return math.log1p(review.helpful_votes) + pred.confidence + min(review.word_count, 80) / 80

    return sorted(candidates, key=importance, reverse=True)[:limit]


def _tone(score: float) -> str:
    return "good" if score >= 70 else "mixed" if score >= 50 else "bad"


def build_reasons(product: Product, reviews: List[Review], summary: SentimentSummary,
                  rec: Recommendation) -> List[Reason]:
    reasons: List[Reason] = []
    for comp in sorted(rec.components, key=lambda c: -c.weight):
        if comp.available:
            reasons.append(Reason(_tone(comp.score), f"**{comp.label}** ({comp.weight:.0%} of score): {comp.detail}"))

    missing = [c.label.lower() for c in rec.components if not c.available]
    if missing:
        reasons.append(Reason(
            "info",
            "Not available and left out of the score (remaining factors re-weighted, nothing counted as zero): "
            + ", ".join(missing) + "."))

    recent = [r for r in reviews if r.age_days is not None]
    if len(recent) >= 5:
        share = sum(r.age_days <= 365 for r in recent) / len(recent)
        reasons.append(Reason("info", f"{share:.0%} of analysed reviews with a known age are under a year old."))

    if summary.n and summary.n < 20:
        reasons.append(Reason("info", f"Only {summary.n} reviews were analysed, so sentiment is less precise."))
    reasons.extend(Reason("info", note) for note in summary.notes)
    reasons.extend(Reason("info", caveat) for caveat in rec.caveats)
    return reasons


def headline(rec: Recommendation) -> str:
    return {
        config.VERDICT_WORTH: "Strong signals across the available data.",
        config.VERDICT_CAREFUL: "Generally positive, but check the details below before buying.",
        config.VERDICT_RISKY: "Mixed or weak signals. Read the negative feedback carefully.",
        config.VERDICT_NOT: "Customer feedback and ratings point to significant problems.",
        config.VERDICT_INSUFFICIENT: "There is not enough reliable data to judge this product.",
    }[rec.verdict]
