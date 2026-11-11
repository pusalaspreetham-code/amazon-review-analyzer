"""Product Recommendation Score (0-100).

Six components, each scored 0-100 or ``None`` when the underlying data is unavailable:

    sentiment 30% | product rating 25% | review quantity 15% |
    review reliability 15% | seller reliability 10% | price/value 5%

Missing data policy: a component that cannot be computed is *excluded* and the remaining
weights are re-normalised, so missing data is neither rewarded nor punished. To stop a
verdict resting on too little evidence, the share of weight backed by real data
("coverage") is tracked: low coverage yields "Insufficient Information" and
medium coverage prevents the top verdict.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

from . import config
from .data import Product, Review
from .sentiment import SentimentSummary


@dataclass
class Component:
    key: str
    label: str
    weight: float
    score: Optional[float]          # 0-100, None when unavailable
    detail: str                     # factual explanation shown to the user

    @property
    def available(self) -> bool:
        return self.score is not None


@dataclass
class Recommendation:
    verdict: str
    score: Optional[float]          # shown score; None when the verdict is Insufficient Information
    raw_score: Optional[float]      # weighted score of whatever data existed
    coverage: float                 # 0-1, share of weight backed by real data
    components: List[Component]
    capped: bool = False
    caveats: List[str] = field(default_factory=list)


def _clip(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _star_to_score(rating: float) -> float:
    """Map a 1-5 star rating to 0-100 (1 star = 0, 3 = 50, 4 = 75, 5 = 100)."""
    return _clip((rating - 1.0) / 4.0 * 100.0)


# --------------------------------------------------------------------------- components
def sentiment_component(summary: SentimentSummary) -> Component:
    w = config.WEIGHTS["sentiment"]
    if summary.n == 0:
        return Component("sentiment", "Customer sentiment", w, None, "No customer reviews could be analysed.")
    pct = summary.estimated_pct
    raw = pct["Positive"] + config.NEUTRAL_VALUE * pct["Neutral"]
    k = config.SENTIMENT_PRIOR_STRENGTH
    score = _clip((summary.n * raw + k * 50.0) / (summary.n + k))
    basis = ("weighted by Amazon's star distribution" if summary.weighted else
             "unweighted sample, which over-represents low-star reviews, so this is likely understated")
    detail = (f"{pct['Positive']:.0f}% positive, {pct['Neutral']:.0f}% neutral and "
              f"{pct['Negative']:.0f}% negative across {summary.n} analysed reviews ({basis}).")
    return Component("sentiment", "Customer sentiment", w, score, detail)


def rating_component(product: Product) -> Component:
    w = config.WEIGHTS["rating"]
    if product.rating is not None:
        return Component("rating", "Product rating", w, _star_to_score(product.rating),
                         f"Amazon rating is {product.rating:.1f} out of 5.")
    if product.star_counts:
        total = sum(product.star_counts.values())
        mean = sum(s * c for s, c in product.star_counts.items()) / total
        return Component("rating", "Product rating", w, _star_to_score(mean),
                         f"Overall rating was not shown; estimated at {mean:.1f} out of 5 "
                         f"from the star distribution.")
    return Component("rating", "Product rating", w, None, "No product rating could be read.")


def quantity_component(product: Product) -> Component:
    w = config.WEIGHTS["quantity"]
    total, origin = product.total_reviews, ""
    if total is None and product.star_counts:
        total, origin = sum(product.star_counts.values()), " (counted from the star distribution)"
    if total is None:
        return Component("quantity", "Review quantity", w, None, "The number of reviews could not be read.")
    score = _clip(100.0 * math.log10(max(total, 1)) / math.log10(config.QUANTITY_FULL_SCORE_AT))
    if total >= 1000:
        size = "a large"
    elif total >= 100:
        size = "a moderate"
    else:
        size = "a small"
    return Component("quantity", "Review quantity", w, score,
                     f"{total:,} customer reviews/ratings{origin}: {size} evidence base.")


def reliability_component(reviews: List[Review]) -> Component:
    w = config.WEIGHTS["reliability"]
    if not reviews:
        return Component("reliability", "Review reliability", w, None, "No reviews available to assess reliability.")
    n = len(reviews)
    detailed = sum(r.word_count >= config.SUBSTANTIVE_REVIEW_WORDS for r in reviews) / n
    verified_seen = [r for r in reviews if r.verified]
    parts, bits = [], []
    # If *no* review carries a badge we cannot tell "none are verified" from "badge not
    # detected", so the verified signal is skipped instead of being scored as 0%.
    if verified_seen:
        share = len(verified_seen) / n
        parts.append((0.6, share * 100))
        bits.append(f"{share:.0%} are verified purchases")
    parts.append((0.4 if verified_seen else 1.0, detailed * 100))
    bits.append(f"{detailed:.0%} are detailed (at least {config.SUBSTANTIVE_REVIEW_WORDS} words)")
    score = _clip(sum(wt * s for wt, s in parts) / sum(wt for wt, _ in parts))
    if not verified_seen:
        bits.append("verified-purchase badges were not detected")
    return Component("reliability", "Review reliability", w, score,
                     f"Of {n} analysed reviews, " + "; ".join(bits) + ".")


def seller_component(product: Product) -> Component:
    w = config.WEIGHTS["seller"]
    parts, bits = [], []
    if product.seller_rating is not None:
        parts.append((0.7, _star_to_score(product.seller_rating)))
        bits.append(f"seller rating {product.seller_rating:.1f}/5")
    if product.fulfillment:
        by_amazon = "amazon" in product.fulfillment.lower()
        parts.append((0.3, 100.0 if by_amazon else 60.0))
        bits.append("fulfilled by Amazon" if by_amazon else f"fulfilment: {product.fulfillment}")
    if not parts:
        return Component("seller", "Seller reliability", w, None,
                         "Neither a seller rating nor fulfilment details could be read.")
    score = _clip(sum(wt * s for wt, s in parts) / sum(wt for wt, _ in parts))
    seller = f" ({product.seller_name})" if product.seller_name else ""
    return Component("seller", "Seller reliability", w, score, f"Seller{seller}: " + ", ".join(bits) + ".")


def value_component(product: Product) -> Component:
    w = config.WEIGHTS["value"]
    discount = product.effective_discount
    if product.price is None or discount is None:
        return Component("value", "Price / value", w, None,
                         "No list price or discount was available, so value was not assessed.")
    score = _clip(config.DISCOUNT_FLOOR_SCORE + discount * config.DISCOUNT_POINTS_PER_PERCENT, 0, 100)
    mrp = f" against a list price of ₹{product.original_price:,.0f}" if product.original_price else ""
    return Component("value", "Price / value", w, score,
                     f"Priced at ₹{product.price:,.0f} with a {discount:.0f}% discount{mrp}. "
                     f"Value is judged from the discount only, since comparable products are not checked.")


# --------------------------------------------------------------------------- final score
def compute_recommendation(product: Product, reviews: List[Review],
                           summary: SentimentSummary) -> Recommendation:
    components = [
        sentiment_component(summary),
        rating_component(product),
        quantity_component(product),
        reliability_component(reviews),
        seller_component(product),
        value_component(product),
    ]
    available = [c for c in components if c.available]
    coverage = round(sum(c.weight for c in available), 4)
    raw_score = (sum(c.weight * c.score for c in available) / coverage) if available else None

    caveats: List[str] = []
    by_key = {c.key: c for c in components}
    core_missing = not by_key["sentiment"].available and not by_key["rating"].available
    evidence = product.total_reviews or (sum(product.star_counts.values()) if product.star_counts else None) \
        or (len(reviews) or None)

    insufficient = False
    if raw_score is None or core_missing:
        insufficient = True
        caveats.append("Neither review sentiment nor a product rating was available.")
    elif coverage < config.MIN_COVERAGE:
        insufficient = True
        caveats.append(f"Only {coverage:.0%} of the score could be backed by real data "
                       f"(minimum {config.MIN_COVERAGE:.0%}).")
    elif evidence is not None and evidence < config.MIN_EVIDENCE_COUNT:
        insufficient = True
        caveats.append(f"Only {evidence} customer reviews/ratings exist; too few for a dependable verdict.")

    if insufficient:
        return Recommendation(config.VERDICT_INSUFFICIENT, None, raw_score, coverage, components,
                              caveats=caveats)

    if raw_score >= config.WORTH_CONSIDERING:
        verdict = config.VERDICT_WORTH
    elif raw_score >= config.CONSIDER_CAREFULLY:
        verdict = config.VERDICT_CAREFUL
    elif raw_score >= config.RISKY_PURCHASE:
        verdict = config.VERDICT_RISKY
    else:
        verdict = config.VERDICT_NOT

    capped = False
    if verdict == config.VERDICT_WORTH and coverage < config.FULL_VERDICT_COVERAGE:
        verdict, capped = config.VERDICT_CAREFUL, True
        caveats.append(f"The score alone would qualify as '{config.VERDICT_WORTH}', but only "
                       f"{coverage:.0%} of the data was available, so the verdict is capped.")
    return Recommendation(verdict, raw_score, raw_score, coverage, components, capped, caveats)
