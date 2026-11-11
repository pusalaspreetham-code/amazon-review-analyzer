"""Typed data models + safe normalisation of the scraper's raw output.

Design rule: anything the scraper could not read becomes ``None`` - never 0 and never a
guess - so the scoring layer can tell "missing" apart from "genuinely zero".
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional

_BLANK = {"", "nan", "none", "null", "not available", "n/a"}


def _is_blank(value) -> bool:
    return value is None or str(value).strip().lower() in _BLANK


def to_float(value) -> Optional[float]:
    if _is_blank(value):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    match = re.search(r"\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(match.group()) if match else None


def to_int(value) -> Optional[int]:
    number = to_float(value)
    return int(round(number)) if number is not None else None


def to_text(value) -> Optional[str]:
    if _is_blank(value):
        return None
    return re.sub(r"\s+", " ", str(value)).strip()


def parse_age_days(age_text: Optional[str]) -> Optional[int]:
    """Convert the scraper's age strings ("3 months ago", "Today" ...) to approximate days."""
    if not age_text:
        return None
    text = age_text.strip().lower()
    if text == "today":
        return 0
    match = re.match(r"(\d+)\s+(day|month|year)s?\s+ago", text)
    if not match:
        return None  # e.g. an unparsed date string
    amount, unit = int(match.group(1)), match.group(2)
    return amount * {"day": 1, "month": 30, "year": 365}[unit]


@dataclass
class Review:
    review_id: str
    title: str
    text: str
    rating: float
    verified: Optional[bool]        # True only when Amazon showed the badge; None = not shown
    helpful_votes: int
    age_text: Optional[str]
    age_days: Optional[int]
    variant: Optional[str]

    @classmethod
    def from_row(cls, row: dict) -> Optional["Review"]:
        title, text = to_text(row.get("review_title")), to_text(row.get("review_text"))
        rating = to_float(row.get("review_rating"))
        if not title or not text or rating is None or not 1 <= rating <= 5:
            return None
        age_text = to_text(row.get("review_age"))
        return cls(
            review_id=to_text(row.get("review_id")) or "",
            title=title,
            text=text,
            rating=rating,
            verified=True if str(row.get("verified_purchase", "")).strip().lower() == "yes" else None,
            helpful_votes=to_int(row.get("helpful_votes")) or 0,
            age_text=age_text,
            age_days=parse_age_days(age_text),
            variant=to_text(row.get("variant")),
        )

    @property
    def word_count(self) -> int:
        return len(self.text.split())


@dataclass
class Product:
    asin: Optional[str]
    name: str
    category: Optional[str]
    url: str
    seller_name: Optional[str]
    seller_rating: Optional[float]
    price: Optional[float]
    original_price: Optional[float]
    discount_pct: Optional[float]
    fulfillment: Optional[str]
    rating: Optional[float]
    total_reviews: Optional[int]
    star_counts: Optional[Dict[int, int]]   # None when the distribution could not be read

    @classmethod
    def from_info(cls, info: dict) -> "Product":
        rating = to_float(info.get("product_rating"))
        seller_rating = to_float(info.get("seller_rating"))
        discount = to_float(info.get("discount_percentage"))
        total = to_int(info.get("total_product_reviews"))

        star_fields = {5: "five_star_review_count", 4: "four_star_review_count",
                       3: "three_star_review_count", 2: "two_star_review_count",
                       1: "one_star_review_count"}
        counts = {s: to_int(info.get(f)) or 0 for s, f in star_fields.items()}
        # The scraper writes 0 when it could not read a count, so an all-zero
        # distribution means "unavailable", not "no reviews at any level".
        star_counts = counts if sum(counts.values()) > 0 else None

        return cls(
            asin=to_text(info.get("product_id")),
            name=to_text(info.get("product_name")) or "Unknown product",
            category=to_text(info.get("category")),
            url=to_text(info.get("product_url")) or "",
            seller_name=to_text(info.get("seller_name")),
            seller_rating=seller_rating if seller_rating and 0 < seller_rating <= 5 else None,
            price=to_float(info.get("price")),
            original_price=to_float(info.get("original_price")),
            discount_pct=discount if discount is not None and 0 <= discount <= 100 else None,
            fulfillment=to_text(info.get("fulfillment")),
            rating=rating if rating and 0 < rating <= 5 else None,
            total_reviews=total if total and total > 0 else None,   # 0 from the scraper = unreadable
            star_counts=star_counts,
        )

    @property
    def effective_discount(self) -> Optional[float]:
        """Discount shown by Amazon, or derived from price/MRP when only those were read."""
        if self.discount_pct is not None:
            return self.discount_pct
        if self.price and self.original_price and self.original_price >= self.price:
            return round((self.original_price - self.price) / self.original_price * 100, 1)
        return None


def reviews_from_rows(rows: List[dict]) -> List[Review]:
    seen, reviews = set(), []
    for row in rows:
        review = Review.from_row(row)
        if review is None:
            continue
        key = review.review_id or (review.title, review.text)
        if key in seen:
            continue
        seen.add(key)
        reviews.append(review)
    return reviews
