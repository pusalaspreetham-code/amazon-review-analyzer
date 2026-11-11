"""Central configuration for the Amazon Product Purchase Advisor."""
from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# --- Files ------------------------------------------------------------------
MODEL_PATH = PROJECT_ROOT / "models" / "logistic_regression_model.pkl"
# Persistent Chromium profile (same idea as USER_DATA_DIR in scrap.py). Keeping cookies
# between runs makes Amazon far less likely to show a CAPTCHA. If you already have an
# `amazon_browser_profile` folder from running scrap.py, copy it into the project root.
BROWSER_PROFILE_DIR = PROJECT_ROOT / "amazon_browser_profile"

# --- Scraping ---------------------------------------------------------------
DEFAULT_REVIEWS_PER_STAR = 20        # same default as scrap.REVIEWS_PER_STAR
MIN_REVIEWS_PER_STAR = 5
MAX_REVIEWS_PER_STAR = 30
SCRAPE_TIMEOUT_SECONDS = 600         # hard limit for one scrape (worker is killed after this)

# --- Sentiment model --------------------------------------------------------
# What text is sent to the model. "title_and_text" joins review title and body;
# use "text_only" if your model was trained on the body alone.
MODEL_INPUT_MODE = "title_and_text"
HIGH_CONFIDENCE = 0.70               # a prediction at/above this counts as "high confidence"
# Edges for the confidence histogram (max class probability of each review).
CONFIDENCE_BINS = [
    ("Low (<50%)", 0.0, 0.5),
    ("Medium (50-70%)", 0.5, 0.7),
    ("High (70-90%)", 0.7, 0.9),
    ("Very high (90%+)", 0.9, 1.0001),
]

# --- Recommendation score ---------------------------------------------------
WEIGHTS = {
    "sentiment": 0.30,
    "rating": 0.25,
    "quantity": 0.15,
    "reliability": 0.15,
    "seller": 0.10,
    "value": 0.05,
}

# Sentiment: a neutral review counts half a positive one.
NEUTRAL_VALUE = 0.5
# Small-sample protection: sentiment is pulled toward 50 as if this many
# "average" reviews were added. Negligible at 100 reviews, meaningful at 3.
SENTIMENT_PRIOR_STRENGTH = 5

QUANTITY_FULL_SCORE_AT = 2000        # ratings needed for a full quantity score (log scale)
SUBSTANTIVE_REVIEW_WORDS = 15        # a review with this many words counts as "detailed"
DISCOUNT_FLOOR_SCORE = 40            # value score for a 0% discount
DISCOUNT_POINTS_PER_PERCENT = 1.5    # +1.5 value points per 1% discount (caps at 100)

# --- Verdict thresholds -----------------------------------------------------
WORTH_CONSIDERING = 75
CONSIDER_CAREFULLY = 60
RISKY_PURCHASE = 45                  # below this -> Not Recommended

MIN_COVERAGE = 0.50                  # share of score weight that must be backed by real data
FULL_VERDICT_COVERAGE = 0.70         # below this, "Worth Considering" is capped
MIN_EVIDENCE_COUNT = 10              # fewer ratings/reviews than this -> Insufficient Information

VERDICT_WORTH = "Worth Considering"
VERDICT_CAREFUL = "Consider Carefully"
VERDICT_RISKY = "Risky Purchase"
VERDICT_NOT = "Not Recommended"
VERDICT_INSUFFICIENT = "Insufficient Information"

VERDICT_COLORS = {
    VERDICT_WORTH: "#1b8a5a",
    VERDICT_CAREFUL: "#2f6fdb",
    VERDICT_RISKY: "#d97a00",
    VERDICT_NOT: "#c9362c",
    VERDICT_INSUFFICIENT: "#6b7280",
}
