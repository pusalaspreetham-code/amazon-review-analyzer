"""End-to-end analysis: scrape outcome -> sentiment -> score -> insights."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Tuple

from . import config
from .data import Product, Review
from .insights import Reason, build_reasons, important_feedback
from .scoring import Recommendation, compute_recommendation
from .scraper_service import ScrapeOutcome
from .sentiment import Prediction, SentimentAnalyzer, SentimentSummary, summarise


@dataclass
class Analysis:
    product: Product
    reviews: List[Review]
    predictions: List[Prediction]
    summary: SentimentSummary
    recommendation: Recommendation
    reasons: List[Reason]
    top_positive: List[Tuple[Review, Prediction]]
    top_negative: List[Tuple[Review, Prediction]]
    warnings: List[str] = field(default_factory=list)
    analysed_at: datetime = field(default_factory=datetime.now)


def analyse(outcome: ScrapeOutcome, analyzer: SentimentAnalyzer) -> Analysis:
    """Build the full analysis. Requires ``outcome.product`` (callers check ``outcome.usable``)."""
    product, reviews = outcome.product, outcome.reviews
    predictions = analyzer.predict(reviews)
    summary = summarise(reviews, predictions, product.star_counts)
    recommendation = compute_recommendation(product, reviews, summary)
    reasons = build_reasons(product, reviews, summary, recommendation)

    warnings = list(outcome.warnings)
    if outcome.status == "no_reviews":
        warnings.append("No customer reviews could be collected for this product.")
    return Analysis(
        product=product, reviews=reviews, predictions=predictions, summary=summary,
        recommendation=recommendation, reasons=reasons,
        top_positive=important_feedback(reviews, predictions, "Positive"),
        top_negative=important_feedback(reviews, predictions, "Negative"),
        warnings=warnings,
    )
