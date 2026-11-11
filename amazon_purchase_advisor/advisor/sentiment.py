"""Sentiment classification with the user's trained scikit-learn pipeline."""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from . import config
from .data import Review

LABELS = ("Positive", "Neutral", "Negative")


@dataclass
class Prediction:
    label: str                       # Positive | Neutral | Negative
    confidence: float                # probability of the predicted class (0-1)
    probabilities: Dict[str, float]  # all three class probabilities


@dataclass
class SentimentSummary:
    n: int = 0
    sample_counts: Dict[str, int] = field(default_factory=lambda: {l: 0 for l in LABELS})
    sample_pct: Dict[str, float] = field(default_factory=lambda: {l: 0.0 for l in LABELS})
    # Best estimate for *all* reviews of the product. Equals sample_pct unless the
    # star distribution was available and `weighted` is True.
    estimated_pct: Dict[str, float] = field(default_factory=lambda: {l: 0.0 for l in LABELS})
    weighted: bool = False
    population_covered: Optional[float] = None   # share of reviews (by star counts) the sample can speak for
    avg_confidence: Optional[float] = None
    high_confidence_share: Optional[float] = None
    confidence_bins: List[tuple] = field(default_factory=list)   # (label, count)
    notes: List[str] = field(default_factory=list)


def model_text(review: Review) -> str:
    if config.MODEL_INPUT_MODE == "text_only":
        return review.text
    return f"{review.title}. {review.text}"


class SentimentAnalyzer:
    """Loads the saved sklearn Pipeline (TF-IDF + LogisticRegression) once."""

    def __init__(self, model_path: Path = config.MODEL_PATH):
        self.model_path = Path(model_path)
        self.model = self._load(self.model_path)
        classes = getattr(self.model, "classes_", None)
        if classes is None:
            raise ValueError("The model has no `classes_`; expected a classifier or Pipeline.")
        self.class_labels = [self._normalise(c) for c in classes]
        if not set(self.class_labels) <= set(LABELS):
            raise ValueError(f"Unexpected sentiment classes in model: {list(classes)}")
        if not hasattr(self.model, "predict_proba"):
            raise ValueError("The model must support predict_proba to report confidence.")

    @staticmethod
    def _load(path: Path):
        if not path.exists():
            raise FileNotFoundError(f"Sentiment model not found at {path}")
        with warnings.catch_warnings():
            # The model may have been trained with a different scikit-learn patch version.
            warnings.simplefilter("ignore")
            try:
                import joblib
                return joblib.load(path)
            except Exception:
                import pickle
                with open(path, "rb") as handle:
                    return pickle.load(handle)

    @staticmethod
    def _normalise(label) -> str:
        text = str(label).strip().lower()
        mapping = {"positive": "Positive", "pos": "Positive", "2": "Positive",
                   "neutral": "Neutral", "neu": "Neutral", "1": "Neutral",
                   "negative": "Negative", "neg": "Negative", "0": "Negative"}
        return mapping.get(text, str(label).title())

    def predict(self, reviews: List[Review]) -> List[Prediction]:
        if not reviews:
            return []
        texts = [model_text(r) for r in reviews]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            probabilities = self.model.predict_proba(texts)
        predictions = []
        for row in probabilities:
            by_label = {label: float(p) for label, p in zip(self.class_labels, row)}
            for label in LABELS:
                by_label.setdefault(label, 0.0)
            best = max(by_label, key=by_label.get)
            predictions.append(Prediction(best, by_label[best], by_label))
        return predictions


def summarise(reviews: List[Review], predictions: List[Prediction],
              star_counts: Optional[Dict[int, int]]) -> SentimentSummary:
    """Aggregate predictions.

    The scraper collects up to N reviews from *each* star level, so the sample has roughly
    equal numbers of 1-star and 5-star reviews even if 90% of real reviews are 5-star.
    When Amazon's star distribution is known, each star level's sentiment mix is weighted
    by how common that star level really is (post-stratification) to correct this skew.
    """
    summary = SentimentSummary()
    n = len(reviews)
    summary.n = n
    if n == 0:
        return summary

    for p in predictions:
        summary.sample_counts[p.label] += 1
    summary.sample_pct = {l: 100.0 * summary.sample_counts[l] / n for l in LABELS}
    summary.estimated_pct = dict(summary.sample_pct)

    # ---- confidence statistics (about the model, so computed on the raw sample)
    confidences = [p.confidence for p in predictions]
    summary.avg_confidence = sum(confidences) / n
    summary.high_confidence_share = sum(c >= config.HIGH_CONFIDENCE for c in confidences) / n
    summary.confidence_bins = [
        (name, sum(low <= c < high for c in confidences)) for name, low, high in config.CONFIDENCE_BINS
    ]

    # ---- star-distribution weighting
    if star_counts:
        by_star = {s: {l: 0 for l in LABELS} for s in range(1, 6)}
        for review, p in zip(reviews, predictions):
            star = int(round(review.rating))
            if 1 <= star <= 5:
                by_star[star][p.label] += 1
        usable = [s for s in range(1, 6) if star_counts.get(s, 0) > 0 and sum(by_star[s].values()) > 0]
        if usable:
            total_weight = sum(star_counts[s] for s in usable)
            summary.estimated_pct = {
                l: 100.0 * sum(star_counts[s] * by_star[s][l] / sum(by_star[s].values()) for s in usable) / total_weight
                for l in LABELS
            }
            summary.weighted = True
            summary.population_covered = total_weight / sum(star_counts.values())
            lost = [s for s in range(1, 6) if star_counts.get(s, 0) > 0 and s not in usable]
            if lost:
                stars = ", ".join(f"{s}-star" for s in lost)
                summary.notes.append(
                    f"No {stars} reviews could be collected, so the estimate covers "
                    f"{summary.population_covered:.0%} of reviews by volume."
                )
    if not summary.weighted:
        summary.notes.append(
            "Star distribution unavailable: percentages describe the collected sample only, "
            "which over-represents low-star reviews."
        )
    return summary
