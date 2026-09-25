import re
import csv
import time
from datetime import datetime
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse

from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError,
)


# ============================================================
# CONFIG
# ============================================================

OUTPUT_FILE = "amazon_reviews.csv"

# Keep Amazon login/session in this folder.
# First run may require normal manual sign-in in the opened browser.
USER_DATA_DIR = "amazon_browser_profile"

# Star filters to visit.
STAR_FILTERS = [
    (5, "five_star"),
    (4, "four_star"),
    (3, "three_star"),
    (2, "two_star"),
    (1, "one_star"),
]

# Number of reviews wanted from EACH star rating.
# 20 x 5 = about 100 reviews per product.
REVIEWS_PER_STAR = 20

# Safety limit. Amazon normally exposes 10 more reviews per click.
MAX_SHOW_MORE_CLICKS_PER_STAR = 30

# How much to scroll while looking for "Show 10 more reviews".
SCROLL_STEP = 2500
MAX_SCROLL_ROUNDS = 2

# Waits in milliseconds.
PAGE_LOAD_WAIT = 900
AFTER_CLICK_WAIT = 500

# Set False when you do not want browser auto-scroll.
ENABLE_SCROLLING = True

# Short waits used only when Amazon has not rendered the target element yet.
REVIEW_SELECTOR_TIMEOUT = 7000
SELLER_SELECTOR_TIMEOUT = 7000
POLL_INTERVAL_MS = 150


# ============================================================
# 22-COLUMN DATASET
# ============================================================

COLUMNS = [
    "review_id",
    "product_id",
    "source",
    "product_name",
    "category",
    "product_url",
    "seller_name",
    "seller_rating",
    "price",
    "original_price",
    "discount_percentage",
    "fulfillment",
    "product_rating",
    "total_product_reviews",
    "five_star_review_count",
    "four_star_review_count",
    "three_star_review_count",
    "two_star_review_count",
    "one_star_review_count",
    "review_title",
    "review_text",
    "review_rating",
    "verified_purchase",
    "variant",
    "helpful_votes",
    "review_age",
    "sentiment",
]


# ============================================================
# GENERAL HELPERS
# ============================================================

def clean_text(text):
    if not text:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(text)
    ).strip()


def safe_text(locator):
    try:
        if locator.count() == 0:
            return ""

        return clean_text(
            locator.first.text_content()
        )

    except Exception:
        return ""


def safe_attribute(locator, attribute):
    try:
        if locator.count() == 0:
            return ""

        value = locator.first.get_attribute(
            attribute
        )

        return value.strip() if value else ""

    except Exception:
        return ""


def number_from_text(text):
    if not text:
        return ""

    text = str(text).replace(",", "")
    text = text.replace("₹", "")

    match = re.search(
        r"\d+(?:\.\d+)?",
        text
    )

    if not match:
        return ""

    try:
        value = float(match.group())

        if value.is_integer():
            return int(value)

        return value

    except ValueError:
        return ""


def wait_for_page(page):
    """Wait only for useful page content instead of sleeping a fixed time."""
    try:
        page.wait_for_load_state(
            "domcontentloaded",
            timeout=15000
        )
    except Exception:
        pass

    # Prefer an actual Amazon review container when on a review page.
    try:
        page.locator('[data-hook="review"]').first.wait_for(
            state="attached",
            timeout=REVIEW_SELECTOR_TIMEOUT
        )
        return
    except Exception:
        pass

    # Product pages do not always contain review containers immediately.
    try:
        page.locator("#productTitle").first.wait_for(
            state="attached",
            timeout=2500
        )
    except Exception:
        pass

    # Tiny fallback only for Amazon's late-rendered content.
    page.wait_for_timeout(200)


def amazon_has_captcha(page):
    try:
        body = clean_text(
            page.locator("body").inner_text()
        ).lower()

        indicators = [
            "enter the characters",
            "robot check",
            "captcha",
        ]

        return any(
            indicator in body
            for indicator in indicators
        )

    except Exception:
        return False


def looks_like_signin(page):
    try:
        review_count = page.locator(
            '[data-hook="review"]'
        ).count()

        if review_count > 0:
            return False

        body = clean_text(
            page.locator("body").inner_text()
        ).lower()

        indicators = [
            "sign in",
            "sign-in",
            "enter your password",
            "email or mobile phone number",
        ]

        return any(
            indicator in body
            for indicator in indicators
        )

    except Exception:
        return False


# ============================================================
# PRODUCT INFORMATION
# ============================================================

def extract_product_id(page, product_url):
    for value in [page.url, product_url]:
        match = re.search(
            r"/dp/([A-Z0-9]{10})",
            value,
            re.IGNORECASE
        )

        if match:
            return match.group(1).upper()

    try:
        elements = page.locator(
            "[data-asin]"
        )

        for i in range(elements.count()):
            asin = elements.nth(i).get_attribute(
                "data-asin"
            )

            if asin and re.fullmatch(
                r"[A-Z0-9]{10}",
                asin
            ):
                return asin.upper()

    except Exception:
        pass

    return ""


def extract_product_name(page):
    for selector in [
        "#productTitle",
        "#title",
    ]:
        try:
            locator = page.locator(selector)

            if locator.count():
                text = safe_text(locator)

                if text:
                    return text

        except Exception:
            pass

    return ""


def extract_category(page):
    for selector in [
        "#wayfinding-breadcrumbs_feature_div",
        "#wayfinding-breadcrumbs_container",
    ]:
        try:
            locator = page.locator(selector)

            if locator.count() == 0:
                continue

            text = safe_text(locator)

            if not text:
                continue

            parts = re.split(
                r"\s*[>›]\s*",
                text
            )

            parts = [
                clean_text(part)
                for part in parts
                if clean_text(part)
            ]

            if parts:
                return " > ".join(parts)

        except Exception:
            pass

    return ""


def extract_price(page):
    try:
        locator = page.locator(
            '[data-csa-c-price-to-pay]'
        )

        if locator.count():
            value = safe_attribute(
                locator,
                "data-csa-c-price-to-pay"
            )

            number = number_from_text(value)

            if number != "":
                return number

    except Exception:
        pass

    selectors = [
        "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen",
        "#corePrice_feature_div .a-price .a-offscreen",
        "#priceblock_ourprice",
        "#priceblock_dealprice",
        "span.a-price-whole",
    ]

    for selector in selectors:
        try:
            locator = page.locator(selector)

            if locator.count():
                value = number_from_text(
                    safe_text(locator)
                )

                if value != "":
                    return value

        except Exception:
            pass

    return ""


def extract_original_price(page):
    selectors = [
        ".basisPrice .a-offscreen",
        "span.a-price.a-text-price span.a-offscreen",
        "#listPrice",
        "#priceblock_listprice",
    ]

    for selector in selectors:
        try:
            locator = page.locator(selector)

            for i in range(locator.count()):
                value = number_from_text(
                    safe_text(locator.nth(i))
                )

                if value != "":
                    return value

        except Exception:
            pass

    return ""


def extract_discount(page):
    selectors = [
        ".savingsPercentage",
        "#dealprice_savings",
        "#regularprice_savings",
        "span.a-size-large.a-color-price.savingsPrice",
    ]

    for selector in selectors:
        try:
            locator = page.locator(selector)

            if locator.count():
                text = safe_text(locator)

                match = re.search(
                    r"(\d+(?:\.\d+)?)\s*%",
                    text
                )

                if match:
                    return float(match.group(1))

        except Exception:
            pass

    return ""


def extract_seller_name(page):
    for selector in [
        "#sellerProfileTriggerId",
        "#merchant-info",
    ]:
        try:
            locator = page.locator(selector)

            if locator.count() == 0:
                continue

            text = safe_text(locator)

            if not text:
                continue

            text = re.sub(
                r"^Sold by\s*",
                "",
                text,
                flags=re.IGNORECASE
            )

            text = re.sub(
                r"Ships from.*",
                "",
                text,
                flags=re.IGNORECASE
            )

            text = clean_text(text)

            if text:
                return text

        except Exception:
            pass

    return ""


def extract_seller_profile_url(page):
    selectors = [
        "#sellerProfileTriggerId",
        'a[href*="seller="]',
        'a[href*="/sp?"]',
        'a[href*="/gp/help/seller"]',
    ]

    for selector in selectors:
        try:
            locator = page.locator(selector)

            for i in range(locator.count()):
                href = locator.nth(i).get_attribute(
                    "href"
                )

                if not href:
                    continue

                if (
                    "seller=" in href
                    or "/sp?" in href
                    or "/gp/help/seller" in href
                ):
                    return urljoin(
                        page.url,
                        href
                    )

        except Exception:
            pass

    return ""


def extract_fulfillment(page):
    try:
        locator = page.locator(
            "#AMAZON_DELIVERED"
        )

        if locator.count():
            text = safe_text(locator)

            if text:
                return text

    except Exception:
        pass

    try:
        seller_link = page.locator(
            "#sellerProfileTriggerId"
        )

        href = safe_attribute(
            seller_link,
            "href"
        )

        if "isAmazonFulfilled=1" in href:
            return "Amazon Delivered"

    except Exception:
        pass

    return ""


def extract_product_rating(page):
    try:
        locator = page.locator(
            "#acrPopover"
        )

        if locator.count():
            title = safe_attribute(
                locator,
                "title"
            )

            match = re.search(
                r"(\d+(?:\.\d+)?)\s+out\s+of\s+5",
                title,
                re.IGNORECASE
            )

            if match:
                return float(match.group(1))

    except Exception:
        pass

    try:
        locator = page.locator(
            '#averageCustomerReviews .a-icon-alt'
        )

        if locator.count():
            text = safe_text(locator)

            match = re.search(
                r"(\d+(?:\.\d+)?)\s+out\s+of\s+5",
                text,
                re.IGNORECASE
            )

            if match:
                return float(match.group(1))

    except Exception:
        pass

    return ""


def extract_total_reviews(page):
    try:
        locator = page.locator(
            "#acrCustomerReviewText"
        )

        if locator.count():
            text = safe_text(locator)

            match = re.search(
                r"([\d,]+)",
                text
            )

            if match:
                return int(
                    match.group(1).replace(",", "")
                )

    except Exception:
        pass

    return ""


# ============================================================
# SELLER RATING
# ============================================================

def extract_seller_rating_from_page(seller_page):
    try:
        locator = seller_page.locator(
            "#seller-info-feedback-summary "
            ".feedback-detail-stars "
            ".a-icon-alt"
        )

        if locator.count():
            text = safe_text(locator)

            match = re.search(
                r"(\d+(?:\.\d+)?)\s+out\s+of\s+5\s+stars?",
                text,
                re.IGNORECASE
            )

            if match:
                rating = float(match.group(1))

                if 0 <= rating <= 5:
                    return rating

    except Exception:
        pass

    try:
        star = seller_page.locator(
            "#seller-info-feedback-summary i.feedback-detail-stars"
        )

        if star.count():
            class_name = (
                star.first.get_attribute("class")
                or ""
            )

            match = re.search(
                r"a-star-(\d)-(\d)",
                class_name
            )

            if match:
                rating = float(
                    f"{match.group(1)}.{match.group(2)}"
                )

                if 0 <= rating <= 5:
                    return rating

    except Exception:
        pass

    return ""


# Seller-rating cache for repeated products/sellers in the same run.
_SELLER_RATING_CACHE = {}


def extract_seller_rating(browser, seller_url):
    if not seller_url:
        return ""

    cache_key = seller_url.split("&asin=")[0]
    if cache_key in _SELLER_RATING_CACHE:
        return _SELLER_RATING_CACHE[cache_key]

    seller_page = browser.new_page()

    try:
        print()
        print("Opening seller profile:")
        print(seller_url)

        seller_page.goto(
            seller_url,
            wait_until="domcontentloaded",
            timeout=45000
        )

        try:
            seller_page.locator(
                "#seller-info-feedback-summary"
            ).first.wait_for(
                state="attached",
                timeout=SELLER_SELECTOR_TIMEOUT
            )
        except Exception:
            pass

        rating = extract_seller_rating_from_page(
            seller_page
        )

        print("Final seller rating:", rating)

        _SELLER_RATING_CACHE[cache_key] = rating
        return rating

    except Exception as e:
        print("Seller rating error:", e)
        return ""

    finally:
        seller_page.close()


def extract_review_id(review):
    try:
        value = review.get_attribute("id")

        if value:
            return value.strip()

    except Exception:
        pass

    try:
        locator = review.locator(
            "[data-reviewid]"
        )

        if locator.count():
            value = locator.first.get_attribute(
                "data-reviewid"
            )

            if value:
                return value.strip()

    except Exception:
        pass

    return ""


def extract_review_rating(review):
    selectors = [
        '[data-hook="review-star-rating"]',
        '[data-hook="cmps-review-star-rating"]',
        ".review-star-rating",
    ]

    for selector in selectors:
        try:
            locator = review.locator(selector)

            if locator.count():
                text = safe_text(locator)

                match = re.search(
                    r"(\d+(?:\.\d+)?)\s+out\s+of\s+5\s+stars?",
                    text,
                    re.IGNORECASE
                )

                if match:
                    return float(match.group(1))

        except Exception:
            pass

    try:
        html = review.inner_html()

        match = re.search(
            r"(\d+(?:\.\d+)?)\s+out\s+of\s+5\s+stars?",
            html,
            re.IGNORECASE
        )

        if match:
            return float(match.group(1))

    except Exception:
        pass

    return ""


def extract_review_title(review):
    # Your actual Amazon HTML uses data-hook="reviewTitle".
    selectors = [
        '[data-hook="reviewTitle"]',
        '[data-hook="review-title"]',
        '[data-hook="review-title-content"]',
        ".review-title",
    ]

    for selector in selectors:
        try:
            locator = review.locator(selector)

            if locator.count():
                text = safe_text(locator)

                if text:
                    text = re.sub(
                        r"^\d+(?:\.\d+)?\s+out\s+of\s+5\s+stars?\s*",
                        "",
                        text,
                        flags=re.IGNORECASE
                    )

                    return clean_text(text)

        except Exception:
            pass

    return ""


def extract_review_text(review):
    # Your actual Amazon HTML puts the body inside
    # data-hook="reviewRichContentContainer".
    selectors = [
        '[data-hook="reviewRichContentContainer"]',
        '[data-hook="reviewText"]',
        '[data-hook="review-body"]',
        '[data-hook="review-body-content"]',
        ".review-text-content",
        ".reviewText",
        ".reviewTextContainer",
    ]

    for selector in selectors:
        try:
            locator = review.locator(selector)
            count = locator.count()

            if count == 0:
                continue

            texts = []

            for i in range(count):
                text = safe_text(
                    locator.nth(i)
                )

                # Remove the accessibility teaser if it appears
                # together with the actual body.
                text = re.sub(
                    r"Brief content visible, double tap to read full content\.?",
                    "",
                    text,
                    flags=re.IGNORECASE
                )

                text = re.sub(
                    r"Full content visible, double tap to read brief content\.?",
                    "",
                    text,
                    flags=re.IGNORECASE
                )

                text = clean_text(text)

                if text and text not in texts:
                    texts.append(text)

            if texts:
                return " ".join(texts)

        except Exception:
            pass

    return ""


def extract_verified_purchase(review):
    selectors = [
        '[data-hook="avp-badge"]',
        '[data-hook="review-verified-badge"]',
        ".avp-badge",
    ]

    for selector in selectors:
        try:
            locator = review.locator(selector)

            if locator.count():
                text = safe_text(locator)

                if "verified" in text.lower():
                    return "Yes"

        except Exception:
            pass

    try:
        text = clean_text(
            review.text_content()
        )

        if "Verified Purchase" in text:
            return "Yes"

    except Exception:
        pass

    return ""


def extract_variant(review):
    selectors = [
        '[data-hook="format-strip"]',
        '[data-hook="product-variation-attributes"]',
        ".review-format-strip",
        ".product-variation-attributes",
    ]

    for selector in selectors:
        try:
            locator = review.locator(selector)

            if locator.count():
                text = safe_text(locator)

                if text:
                    return clean_text(text)

        except Exception:
            pass

    return ""


def extract_helpful_votes(review):
    selectors = [
        '[data-hook="helpful-vote-statement"]',
        '[data-hook="helpfulVoteWidget"]',
        '[data-hook="helpfulVoteButton"]',
        ".cr-vote-text",
        "#helpfulVoteWidget",
    ]

    for selector in selectors:
        try:
            locator = review.locator(selector)
            count = locator.count()

            if count == 0:
                continue

            for i in range(count):
                text = safe_text(
                    locator.nth(i)
                )

                if not text:
                    continue

                match = re.search(
                    r"([\d,]+)\s+people\s+found\s+this\s+helpful",
                    text,
                    re.IGNORECASE
                )

                if match:
                    return int(
                        match.group(1).replace(",", "")
                    )

                if re.search(
                    r"one\s+person\s+found\s+this\s+helpful",
                    text,
                    re.IGNORECASE
                ):
                    return 1

        except Exception:
            pass

    # Fallback using entire review text.
    try:
        text = clean_text(
            review.text_content()
        )

        match = re.search(
            r"([\d,]+)\s+people\s+found\s+this\s+helpful",
            text,
            re.IGNORECASE
        )

        if match:
            return int(
                match.group(1).replace(",", "")
            )

        if re.search(
            r"one\s+person\s+found\s+this\s+helpful",
            text,
            re.IGNORECASE
        ):
            return 1

    except Exception:
        pass

    return ""


def extract_review_age(review):
    try:
        locator = review.locator(
            '[data-hook="review-date"]'
        )

        if locator.count():
            text = safe_text(locator)

            if text:
                return calculate_review_age(text)

    except Exception:
        pass

    return ""


def calculate_review_age(text):
    match = re.search(
        r"on\s+(.+)",
        text,
        re.IGNORECASE
    )

    if not match:
        return text

    date_text = clean_text(
        match.group(1)
    )

    review_date = None

    for fmt in [
        "%d %B %Y",
        "%d %b %Y",
    ]:
        try:
            review_date = datetime.strptime(
                date_text,
                fmt
            )
            break
        except ValueError:
            pass

    if review_date is None:
        return date_text

    days = (
        datetime.now() - review_date
    ).days

    if days < 0:
        return date_text

    if days == 0:
        return "Today"

    if days == 1:
        return "1 day ago"

    if days < 30:
        return f"{days} days ago"

    months = days // 30

    if months == 1:
        return "1 month ago"

    if months < 12:
        return f"{months} months ago"

    years = months // 12

    if years == 1:
        return "1 year ago"

    return f"{years} years ago"


# ============================================================
# ONE REVIEW -> DATASET ROW
# ============================================================

def extract_one_review(review, product_info):
    return {
        "review_id": extract_review_id(review),
        "product_id": product_info["product_id"],
        "source": "Amazon",
        "product_name": product_info["product_name"],
        "category": product_info["category"],
        "product_url": product_info["product_url"],
        "seller_name": product_info["seller_name"],
        "seller_rating": product_info["seller_rating"],
        "price": product_info["price"],
        "original_price": product_info["original_price"],
        "discount_percentage": product_info["discount_percentage"],
        "fulfillment": product_info["fulfillment"],
        "product_rating": product_info["product_rating"],
        "total_product_reviews": product_info["total_product_reviews"],
        "five_star_review_count": product_info.get("five_star_review_count", ""),
        "four_star_review_count": product_info.get("four_star_review_count", ""),
        "three_star_review_count": product_info.get("three_star_review_count", ""),
        "two_star_review_count": product_info.get("two_star_review_count", ""),
        "one_star_review_count": product_info.get("one_star_review_count", ""),
        "review_title": extract_review_title(review),
        "review_text": extract_review_text(review),
        "review_rating": extract_review_rating(review),
        "verified_purchase": extract_verified_purchase(review),
        "variant": extract_variant(review),
        "helpful_votes": extract_helpful_votes(review),
        "review_age": extract_review_age(review),
        "sentiment": "",
    }


# ============================================================
# REVIEW CONTAINER EXTRACTION
# ============================================================

def extract_reviews_from_page(page, product_info):
    """
    Fast review extraction: one browser-side JavaScript call extracts
    the whole visible review list instead of many Playwright calls per field.
    """
    script = r'''
    () => {
        const clean = (value) => {
            if (!value) return "";
            return String(value).replace(/\s+/g, " ").trim();
        };

        const firstText = (root, selectors) => {
            for (const selector of selectors) {
                const el = root.querySelector(selector);
                if (el) {
                    const text = clean(el.textContent);
                    if (text) return text;
                }
            }
            return "";
        };

        const reviews = Array.from(
            document.querySelectorAll('[data-hook="review"]')
        );

        return reviews.map((review) => {
            const id = clean(
                review.getAttribute("id") ||
                review.querySelector("[data-reviewid]")?.getAttribute("data-reviewid") ||
                ""
            );

            const ratingText = firstText(review, [
                '[data-hook="review-star-rating"]',
                '[data-hook="cmps-review-star-rating"]',
                ".review-star-rating"
            ]);
            const ratingMatch = ratingText.match(/(\d+(?:\.\d+)?)\s+out\s+of\s+5\s+stars?/i);

            const titleRaw = firstText(review, [
                '[data-hook="reviewTitle"]',
                '[data-hook="review-title"]',
                '[data-hook="review-title-content"]',
                ".review-title"
            ]);
            const title = clean(
                titleRaw.replace(/^\d+(?:\.\d+)?\s+out\s+of\s+5\s+stars?\s*/i, "")
            );

            let reviewText = firstText(review, [
                '[data-hook="reviewRichContentContainer"]',
                '[data-hook="reviewText"]',
                '[data-hook="review-body"]',
                '[data-hook="review-body-content"]',
                ".review-text-content",
                ".reviewText",
                ".reviewTextContainer"
            ]);
            reviewText = clean(
                reviewText
                    .replace(/Brief content visible, double tap to read full content\.?/gi, "")
                    .replace(/Full content visible, double tap to read brief content\.?/gi, "")
            );

            const verifiedText = firstText(review, [
                '[data-hook="avp-badge"]',
                '[data-hook="review-verified-badge"]',
                ".avp-badge"
            ]);

            const variant = firstText(review, [
                '[data-hook="format-strip"]',
                '[data-hook="product-variation-attributes"]',
                ".review-format-strip",
                ".product-variation-attributes"
            ]);

            const dateText = firstText(review, [
                '[data-hook="review-date"]'
            ]);

            const helpfulText = clean(review.textContent);
            let helpfulVotes = "";
            let helpfulMatch = helpfulText.match(/([\d,]+)\s+people\s+found\s+this\s+helpful/i);
            if (helpfulMatch) {
                helpfulVotes = Number(helpfulMatch[1].replace(/,/g, ""));
            } else if (/one\s+person\s+found\s+this\s+helpful/i.test(helpfulText)) {
                helpfulVotes = 1;
            }

            return {
                review_id: id,
                review_title: title,
                review_text: reviewText,
                review_rating: ratingMatch ? Number(ratingMatch[1]) : "",
                verified_purchase: /verified\s+purchase/i.test(verifiedText) || /verified\s+purchase/i.test(helpfulText) ? "Yes" : "",
                variant: variant,
                helpful_votes: helpfulVotes,
                review_date_text: dateText
            };
        });
    }
    '''

    try:
        raw_rows = page.evaluate(script)
    except Exception:
        raw_rows = []

    print(
        f"Reviews currently visible: {len(raw_rows)}"
    )

    rows = []

    for raw in raw_rows:
        try:
            row = {
                "review_id": raw.get("review_id", ""),
                "product_id": product_info["product_id"],
                "source": "Amazon",
                "product_name": product_info["product_name"],
                "category": product_info["category"],
                "product_url": product_info["product_url"],
                "seller_name": product_info["seller_name"],
                "seller_rating": product_info["seller_rating"],
                "price": product_info["price"],
                "original_price": product_info["original_price"],
                "discount_percentage": product_info["discount_percentage"],
                "fulfillment": product_info["fulfillment"],
                "product_rating": product_info["product_rating"],
                "total_product_reviews": product_info["total_product_reviews"],
                "five_star_review_count": product_info.get("five_star_review_count", ""),
                "four_star_review_count": product_info.get("four_star_review_count", ""),
                "three_star_review_count": product_info.get("three_star_review_count", ""),
                "two_star_review_count": product_info.get("two_star_review_count", ""),
                "one_star_review_count": product_info.get("one_star_review_count", ""),
                "review_title": raw.get("review_title", ""),
                "review_text": raw.get("review_text", ""),
                "review_rating": raw.get("review_rating", ""),
                "verified_purchase": raw.get("verified_purchase", ""),
                "variant": raw.get("variant", ""),
                "helpful_votes": raw.get("helpful_votes", ""),
                "review_age": calculate_review_age(raw.get("review_date_text", "")),
                "sentiment": "",
            }

            if (
                row["review_id"]
                or row["review_text"]
                or row["review_rating"] != ""
            ):
                rows.append(row)

        except Exception as e:
            print("Review extraction error:", e)

    print(
        f"Reviews extracted this time: {len(rows)}"
    )
    return rows


def scroll_to_bottom(page):
    """Jump to the bottom once/twice; avoid slow 700 ms scroll loops."""
    if not ENABLE_SCROLLING:
        return

    try:
        page.evaluate(
            "window.scrollTo(0, document.body.scrollHeight)"
        )
        page.wait_for_timeout(250)
    except Exception:
        pass

    # One retry handles Amazon's lazy-rendered review footer.
    try:
        page.evaluate(
            "window.scrollTo(0, document.body.scrollHeight)"
        )
        page.wait_for_timeout(150)
    except Exception:
        pass


def find_show_more_link(page):
    """
    Find the real Amazon pagination link.

    The user-provided URL pattern is:

    /portal/customer-reviews/ASIN/
    ref=cm_cr_getr_d_paging_btm_2

    then _3, _4, ...

    We DO NOT hard-code the next number. We read Amazon's actual
    href every time, so the current Amazon page decides the next URL.
    """

    candidate_selectors = [
        'a[href*="cm_cr_getr_d_paging_btm_"]',
        'a:has-text("Show 10 more reviews")',
        'a[data-hook="next-button"]',
    ]

    for selector in candidate_selectors:
        try:
            locator = page.locator(selector)
            count = locator.count()

            for i in range(count):
                item = locator.nth(i)

                try:
                    if not item.is_visible():
                        continue
                except Exception:
                    pass

                href = item.get_attribute("href")
                text = clean_text(
                    item.text_content()
                )

                if (
                    href
                    and (
                        "cm_cr_getr_d_paging_btm_" in href
                        or "show 10 more reviews" in text.lower()
                    )
                ):
                    return item

        except Exception:
            pass

    return None


# ============================================================
# GET NEXT "SHOW 10 MORE" URL
# ============================================================

def get_next_load_more_url(
    link,
    page,
    star_filter
):
    try:
        href = link.get_attribute("href")

        if not href:
            return ""

        url = urljoin(
            page.url,
            href
        )

        # Make sure the star filter remains active.
        parsed = urlparse(url)
        query = parse_qs(
            parsed.query,
            keep_blank_values=True
        )

        query["filterByStar"] = [
            star_filter
        ]

        rebuilt = parsed._replace(
            query=urlencode(
                query,
                doseq=True
            )
        )

        return urlunparse(rebuilt)

    except Exception:
        return ""


# ============================================================
# EXTRACT NUMBER FROM PAGING URL
# ============================================================

def paging_number_from_url(url):
    if not url:
        return ""

    match = re.search(
        r"cm_cr_getr_d_paging_btm_(\d+)",
        url
    )

    if match:
        return int(match.group(1))

    return ""



# ============================================================
# FIND ACTUAL AMAZON STAR FILTER LINKS
# ============================================================

def get_actual_star_filter_urls(page, product_id):
    """
    Read Amazon's own five histogram links from the product page.

    Amazon's current HTML exposes links containing:
        filterByStar=five_star
        filterByStar=four_star
        filterByStar=three_star
        filterByStar=two_star
        filterByStar=one_star

    We prefer these real hrefs over constructing URLs ourselves.
    """

    urls = {}

    for star_number, star_filter in STAR_FILTERS:

        selectors = [
            f'#histogramTable a[href*="filterByStar={star_filter}"]',
            f'a[href*="filterByStar={star_filter}"]',
        ]

        found = ""

        for selector in selectors:

            try:

                locator = page.locator(selector)

                count = locator.count()

                for i in range(count):

                    href = locator.nth(i).get_attribute("href")

                    if href:

                        found = urljoin(page.url, href)
                        break

                if found:
                    break

            except Exception:
                pass

        # Fallback if Amazon did not expose the histogram link.
        if not found and product_id:
            found = build_star_filter_url(
                product_id,
                star_filter
            )

        urls[star_number] = found

    return urls


# ============================================================
# EXTRACT AMAZON STAR DISTRIBUTION
# ============================================================

def extract_star_distribution(page, total_reviews):
    """
    Extract the star distribution shown by Amazon's histogram.

    The supplied Amazon HTML exposes percentages such as:
        62 percent of reviews have 5 stars
        24 percent of reviews have 4 stars
        ...

    Amazon's supplied HTML does not expose an exact absolute count
    for each star bucket, so we calculate an estimated count from:

        total global ratings * percentage / 100

    The scraper also reports the exact number of reviews it actually
    collected from each filter separately.
    """

    distribution = {}

    try:
        total = float(total_reviews)
    except (TypeError, ValueError):
        total = 0

    for star_number, star_filter in STAR_FILTERS:

        percentage = ""
        estimated_count = ""

        selectors = [
            f'#histogramTable a[href*="filterByStar={star_filter}"]',
            f'a[href*="filterByStar={star_filter}"]',
        ]

        for selector in selectors:

            try:

                locator = page.locator(selector)

                if locator.count() == 0:
                    continue

                link = locator.first

                aria = link.get_attribute("aria-label") or ""
                text = clean_text(link.text_content())

                # Example:
                # 62 percent of reviews have 5 stars
                match = re.search(
                    r'(\d+(?:\.\d+)?)\s*percent',
                    aria,
                    re.IGNORECASE
                )

                if not match:
                    match = re.search(
                        r'(\d+(?:\.\d+)?)\s*%',
                        aria,
                        re.IGNORECASE
                    )

                if not match:
                    match = re.search(
                        r'(\d+(?:\.\d+)?)\s*%',
                        text,
                        re.IGNORECASE
                    )

                if match:
                    percentage = float(match.group(1))

                    if total > 0:
                        estimated_count = round(
                            total * percentage / 100
                        )

                break

            except Exception:
                pass

        distribution[star_number] = {
            "percentage": percentage,
            "estimated_count": estimated_count,
        }

    return distribution


# ============================================================
# PRINT AMAZON STAR DISTRIBUTION
# ============================================================

def print_star_distribution(distribution):

    print()
    print("AMAZON STAR DISTRIBUTION")
    print("-" * 70)
    print("This is Amazon's histogram breakdown.")
    print("Absolute counts are estimates from the displayed percentages.")
    print()

    for star_number in [5, 4, 3, 2, 1]:

        data = distribution.get(
            star_number,
            {}
        )

        percentage = data.get(
            "percentage",
            ""
        )

        estimated_count = data.get(
            "estimated_count",
            ""
        )

        if percentage != "":

            print(
                f"{star_number}★ : "
                f"{percentage}%  "
                f"(~{estimated_count} ratings)"
            )

        else:

            print(
                f"{star_number}★ : "
                "not exposed by Amazon"
            )

    print("-" * 70)


# ============================================================
# CLICK / OPEN NEXT SHOW-10 PAGE
# ============================================================

# ============================================================
# EXTRACT EXACT STAR COUNT FROM ALL-REVIEWS PAGE
# ============================================================

def extract_filtered_review_count(page):
    """
    Read Amazon's exact count for the currently selected star filter.

    Amazon's all-reviews HTML exposes this as:
        data-hook="cr-filter-info-review-rating-count"

    Example:
        214 matching customer reviews

    This is the exact count Amazon reports for the currently
    selected filter, unlike the rounded histogram percentages.
    """

    selectors = [
        '[data-hook="cr-filter-info-review-rating-count"]',
        '#reviews-filter-info-segment + .a-letter-space + '
        'span[data-hook="cr-filter-info-review-rating-count"]',
    ]

    for selector in selectors:

        try:

            locator = page.locator(selector)

            count = locator.count()

            for i in range(count):

                text = clean_text(
                    locator.nth(i).text_content()
                )

                if not text:
                    continue

                match = re.search(
                    r'([\d,]+)\s+matching\s+customer\s+reviews?',
                    text,
                    re.IGNORECASE
                )

                if match:

                    return int(
                        match.group(1).replace(
                            ",",
                            ""
                        )
                    )

        except Exception:
            pass

    # Fallback: search the filtered-info section.
    try:

        section = page.locator(
            '[data-hook="cr-filter-info-section"]'
        )

        if section.count():

            text = clean_text(
                section.first.text_content()
            )

            match = re.search(
                r'([\d,]+)\s+matching\s+customer\s+reviews?',
                text,
                re.IGNORECASE
            )

            if match:

                return int(
                    match.group(1).replace(
                        ",",
                        ""
                    )
                )

    except Exception:
        pass

    return ""

def click_show_more_reviews(
    page,
    star_filter,
    previous_count
):
    """Use Amazon's real Show-10 link with minimal waiting."""
    scroll_to_bottom(page)

    link = find_show_more_link(page)

    if link is None:
        print("'Show 10 more reviews' link not found.")
        return False

    next_url = get_next_load_more_url(
        link,
        page,
        star_filter
    )

    if not next_url:
        return False

    print()
    print("SHOW 10 MORE REVIEWS")
    print("-" * 70)
    print("Amazon next URL:")
    print(next_url)

    # First choice: normal browser click.
    try:
        link.scroll_into_view_if_needed(timeout=3000)
    except Exception:
        pass

    try:
        link.click(timeout=6000, force=True)

        # Poll for the extra review containers instead of sleeping 2.5s.
        deadline = time.time() + 6.0
        while time.time() < deadline:
            new_count = page.locator(
                '[data-hook="review"]'
            ).count()

            if new_count > previous_count:
                print("Review containers after click:", new_count)
                print("Successfully loaded more reviews by click.")
                return True

            page.wait_for_timeout(POLL_INTERVAL_MS)

    except Exception as e:
        print("Browser click failed:", e)

    # Fallback: Amazon's own href, without constructing a fake page.
    print("Opening Amazon's exact next paging URL directly...")

    try:
        page.goto(
            next_url,
            wait_until="domcontentloaded",
            timeout=45000
        )

        try:
            page.locator('[data-hook="review"]').first.wait_for(
                state="attached",
                timeout=REVIEW_SELECTOR_TIMEOUT
            )
        except Exception:
            pass

        new_count = page.locator(
            '[data-hook="review"]'
        ).count()

        print("Review containers after direct URL:", new_count)

        if new_count > 0:
            print("Next review page opened successfully.")
            return True

    except Exception as e:
        print("Opening next URL failed:", e)

    return False


def build_star_filter_url(
    product_id,
    star_filter
):
    return (
        "https://www.amazon.in/portal/customer-reviews/"
        f"{product_id}/"
        "ref=cm_cr_arp_d_viewopt_sr?"
        "_encoding=UTF8"
        "&ie=UTF8"
        "&reviewerType=all_reviews"
        f"&filterByStar={star_filter}"
    )


# ============================================================
# NORMAL MANUAL SIGN-IN HANDLING
# ============================================================

def wait_for_manual_signin_if_needed(page):
    try:
        review_count = page.locator(
            '[data-hook="review"]'
        ).count()

        if review_count > 0:
            return True

    except Exception:
        pass

    if not looks_like_signin(page):
        return False

    print()
    print("=" * 70)
    print("AMAZON SIGN-IN REQUIRED")
    print("=" * 70)
    print(
        "Please sign in normally in the Amazon browser window."
    )
    print(
        "After the review page is visible, return here and press ENTER."
    )

    input()

    page.wait_for_timeout(2000)

    try:
        return (
            page.locator(
                '[data-hook="review"]'
            ).count()
            > 0
        )
    except Exception:
        return False


# ============================================================
# COLLECT ONE STAR FILTER
# ============================================================

# ============================================================
# COLLECT ONE STAR FILTER
# ============================================================

def collect_star_reviews(
    browser,
    product_info,
    star_number,
    star_filter,
    review_url_override=""
):
    """
    Collect one rating at a time.

    Returns:
        (rows, amazon_exact_count)

    amazon_exact_count is the exact number displayed by Amazon
    for the currently selected star filter.
    """

    page = browser.new_page()

    rows = []
    seen_ids = set()

    exact_count = ""

    try:

        review_url = (
            review_url_override
            or build_star_filter_url(
                product_info["product_id"],
                star_filter
            )
        )

        print()
        print("=" * 70)
        print(
            f"STARTING {star_number}-STAR REVIEWS"
        )
        print("=" * 70)
        print(
            "Opening filter URL:"
        )
        print(review_url)

        page.goto(
            review_url,
            wait_until="domcontentloaded",
            timeout=60000
        )

        wait_for_page(page)

        if amazon_has_captcha(page):

            print(
                "CAPTCHA detected. "
                "Stopping this star filter."
            )

            return [], ""

        # ----------------------------------------------------
        # Allow normal one-time manual sign-in.
        # ----------------------------------------------------

        review_count = page.locator(
            '[data-hook="review"]'
        ).count()

        if review_count == 0:

            if wait_for_manual_signin_if_needed(
                page
            ):

                print(
                    "Review page available after sign-in."
                )

            else:

                print(
                    "No reviews visible "
                    "for this star filter."
                )

                return [], ""

        # ----------------------------------------------------
        # EXACT AMAZON COUNT
        # ----------------------------------------------------

        exact_count = extract_filtered_review_count(
            page
        )

        print()
        print(
            f"AMAZON {star_number}-STAR COUNT:"
        )

        if exact_count != "":

            print(
                f"{exact_count:,} matching "
                f"{star_number}-star customer reviews"
            )

        else:

            print(
                "Exact count not exposed "
                "on this page."
            )

        # ----------------------------------------------------
        # Repeatedly collect and follow
        # "Show 10 more reviews".
        # ----------------------------------------------------

        for click_number in range(
            MAX_SHOW_MORE_CLICKS_PER_STAR + 1
        ):

            if amazon_has_captcha(page):

                print(
                    "CAPTCHA detected. "
                    "Stopping this filter."
                )

                break

            review_locator = page.locator(
                '[data-hook="review"]'
            )

            current_count = (
                review_locator.count()
            )

            print()
            print(
                f"{star_number}-STAR PAGE STATE"
            )

            print(
                f"Current review containers: "
                f"{current_count}"
            )

            print(
                f"Unique collected so far: "
                f"{len(rows)}"
            )

            # ------------------------------------------------
            # Extract current reviews.
            # ------------------------------------------------

            current_rows = (
                extract_reviews_from_page(
                    page,
                    product_info
                )
            )

            added = 0

            for row in current_rows:

                review_id = row.get(
                    "review_id",
                    ""
                )

                if review_id:

                    if review_id in seen_ids:
                        continue

                    seen_ids.add(
                        review_id
                    )

                    rows.append(
                        row
                    )

                    added += 1

                else:

                    if row.get(
                        "review_text"
                    ):

                        rows.append(
                            row
                        )

                        added += 1

            print(
                f"New unique reviews added: "
                f"{added}"
            )

            # ------------------------------------------------
            # Target reached.
            # ------------------------------------------------

            if (
                len(rows)
                >= REVIEWS_PER_STAR
            ):

                print()
                print(
                    f"Collected target of "
                    f"{REVIEWS_PER_STAR} "
                    f"{star_number}-star reviews."
                )

                break

            # ------------------------------------------------
            # Maximum page limit.
            # ------------------------------------------------

            if (
                click_number
                >= MAX_SHOW_MORE_CLICKS_PER_STAR
            ):

                print(
                    "Maximum Show-10 click "
                    "limit reached."
                )

                break

            # ------------------------------------------------
            # Follow the next Show-10 page.
            # ------------------------------------------------

            previous_count = current_count

            success = click_show_more_reviews(
                page,
                star_filter,
                previous_count
            )

            if not success:

                print(
                    f"No more publicly available "
                    f"{star_number}★ reviews."
                )

                break

        print()
        print(
            "-" * 70
        )

        print(
            f"FINISHED {star_number}-STAR FILTER"
        )

        if exact_count != "":

            print(
                f"Amazon says: "
                f"{exact_count:,} total {star_number}★ reviews"
            )

        print(
            f"Scraper collected: "
            f"{len(rows)} {star_number}★ reviews"
        )

        print(
            "-" * 70
        )

        return rows, exact_count

    except PlaywrightTimeoutError:

        print(
            f"{star_number}★ page timed out."
        )

        return rows, exact_count

    except Exception as e:

        print(
            f"{star_number}★ collection error:",
            e
        )

        return rows, exact_count

    finally:

        page.close()


# ============================================================
# COLLECT ALL FIVE STAR FILTERS
# ============================================================



# ============================================================
# COLLECT ALL FIVE STAR FILTERS
# ============================================================

def collect_all_star_filters(
    browser,
    product_info,
    star_filter_urls=None
):
    all_reviews = []
    seen_ids = set()
    exact_star_counts = {}

    if star_filter_urls is None:
        star_filter_urls = {}

    for star_number, star_filter in STAR_FILTERS:

        actual_url = star_filter_urls.get(
            star_number,
            ""
        )

        # collect_star_reviews() returns:
        # (review_rows, exact_amazon_count)
        star_reviews, exact_count = collect_star_reviews(
            browser,
            product_info,
            star_number,
            star_filter,
            actual_url
        )

        exact_star_counts[star_number] = exact_count

        for review in star_reviews:

            review_id = review.get(
                "review_id",
                ""
            )

            if review_id:

                if review_id in seen_ids:
                    continue

                seen_ids.add(review_id)
                all_reviews.append(review)

            else:

                all_reviews.append(review)

        print()
        print(
            f"TOTAL REVIEWS AFTER {star_number}★ FILTER:",
            len(all_reviews)
        )

    import random
    random.shuffle(all_reviews)

    # Return BOTH the collected review rows and Amazon's exact
    # star-filter counts. scrape_amazon() expects two values.
    return all_reviews, exact_star_counts


# ============================================================
# PRODUCT SCRAPER
# ============================================================

def scrape_amazon(
    browser,
    product_url
):
    page = browser.new_page()

    try:
        print()
        print("=" * 70)
        print("AMAZON REVIEW SCRAPER")
        print("=" * 70)
        print(
            "Opening product:"
        )
        print(product_url)

        page.goto(
            product_url,
            wait_until="domcontentloaded",
            timeout=60000
        )

        try:
            page.locator("#productTitle").first.wait_for(
                state="attached",
                timeout=REVIEW_SELECTOR_TIMEOUT
            )
        except Exception:
            page.wait_for_timeout(PAGE_LOAD_WAIT)

        if amazon_has_captcha(page):
            print(
                "CAPTCHA detected on product page."
            )
            return []

        # ----------------------------------------------------
        # Product data
        # ----------------------------------------------------

        product_id = extract_product_id(
            page,
            product_url
        )

        if not product_id:
            print(
                "Could not extract product ID."
            )
            return []

        product_name = extract_product_name(
            page
        )

        category = extract_category(
            page
        )

        seller_name = extract_seller_name(
            page
        )

        seller_profile_url = (
            extract_seller_profile_url(
                page
            )
        )

        seller_rating = extract_seller_rating(
            browser,
            seller_profile_url
        )

        price = extract_price(
            page
        )

        original_price = extract_original_price(
            page
        )

        discount_percentage = extract_discount(
            page
        )

        fulfillment = extract_fulfillment(
            page
        )

        product_rating = extract_product_rating(
            page
        )

        total_product_reviews = extract_total_reviews(
            page
        )

        product_info = {
            "product_id": product_id,
            "product_name": product_name,
            "category": category,
            "product_url": product_url,
            "seller_name": seller_name,
            "seller_rating": seller_rating,
            "price": price,
            "original_price": original_price,
            "discount_percentage": discount_percentage,
            "fulfillment": fulfillment,
            "product_rating": product_rating,
            "total_product_reviews": total_product_reviews,
        }

        # ----------------------------------------------------
        # Display product information
        # ----------------------------------------------------

        print()
        print("PRODUCT INFORMATION")
        print("-" * 50)
        print("Product:", product_name)
        print("Product ID:", product_id)
        print("Category:", category)
        print("Seller:", seller_name)
        print("Seller Profile:", seller_profile_url)
        print("Seller Rating:", seller_rating)
        print("Price:", price)
        print("Original Price:", original_price)
        print("Discount:", discount_percentage)
        print("Fulfillment:", fulfillment)
        print("Product Rating:", product_rating)
        print("Total Product Reviews:", total_product_reviews)

        # ----------------------------------------------------
        # Amazon's actual star distribution
        # ----------------------------------------------------

        star_distribution = extract_star_distribution(
            page,
            total_product_reviews
        )

        print_star_distribution(
            star_distribution
        )

        # ----------------------------------------------------
        # Read Amazon's ACTUAL five star-filter URLs.
        # ----------------------------------------------------

        star_filter_urls = get_actual_star_filter_urls(
            page,
            product_id
        )

        print()
        print("AMAZON STAR FILTER LINKS")
        print("-" * 70)

        for star_number, star_filter in STAR_FILTERS:

            print(
                f"{star_number}★ ({star_filter}):"
            )

            print(
                star_filter_urls.get(
                    star_number,
                    "NOT FOUND"
                )
            )

        # ----------------------------------------------------
        # Collect from all FIVE star filters.
        # ----------------------------------------------------

        reviews, exact_star_counts = collect_all_star_filters(
            browser,
            product_info,
            star_filter_urls
        )

        # Store Amazon's exact star-bucket counts on every review row
        # so the CSV contains the complete product-level distribution.
        product_info["five_star_review_count"] = exact_star_counts.get(5, "")
        product_info["four_star_review_count"] = exact_star_counts.get(4, "")
        product_info["three_star_review_count"] = exact_star_counts.get(3, "")
        product_info["two_star_review_count"] = exact_star_counts.get(2, "")
        product_info["one_star_review_count"] = exact_star_counts.get(1, "")

        for review in reviews:
            review["five_star_review_count"] = product_info["five_star_review_count"]
            review["four_star_review_count"] = product_info["four_star_review_count"]
            review["three_star_review_count"] = product_info["three_star_review_count"]
            review["two_star_review_count"] = product_info["two_star_review_count"]
            review["one_star_review_count"] = product_info["one_star_review_count"]

        print()
        print("=" * 70)
        print("AMAZON EXACT STAR REVIEW COUNTS")
        print("=" * 70)

        for rating in [5, 4, 3, 2, 1]:

            exact_count = exact_star_counts.get(
                rating,
                ""
            )

            if exact_count != "":

                print(
                    f"{rating}★ : "
                    f"{exact_count:,} reviews"
                )

            else:

                print(
                    f"{rating}★ : "
                    "count not exposed"
                )

        print("=" * 70)

        print()
        print("=" * 70)
        print("FINAL REVIEW COLLECTION")
        print("=" * 70)
        print(
            "TOTAL UNIQUE REVIEWS:",
            len(reviews)
        )

        # ----------------------------------------------------
        # Show distribution
        # ----------------------------------------------------

        distribution = {
            1: 0,
            2: 0,
            3: 0,
            4: 0,
            5: 0,
        }

        for review in reviews:
            try:
                rating = int(
                    float(
                        review.get(
                            "review_rating",
                            ""
                        )
                    )
                )

                if rating in distribution:
                    distribution[rating] += 1

            except (
                TypeError,
                ValueError
            ):
                pass

        print()
        print("SCRAPER-COLLECTED STAR DISTRIBUTION")
        print("-" * 50)

        for rating in [
            5,
            4,
            3,
            2,
            1
        ]:
            print(
                f"{rating}★ : {distribution[rating]} collected"
            )

        return reviews

    except PlaywrightTimeoutError:
        print(
            "Product page timed out."
        )
        return []

    except Exception as e:
        print(
            "Amazon scraper error:",
            e
        )
        return []

    finally:
        page.close()


# ============================================================
# SAVE CSV
# ============================================================

def save_to_csv(
    reviews,
    filename=OUTPUT_FILE
):
    if not reviews:
        print(
            "No reviews to save."
        )
        return

    existing_rows = []
    existing_ids = set()
    file_exists = False
    existing_fieldnames = []

    try:
        with open(
            filename,
            "r",
            encoding="utf-8-sig",
            newline=""
        ) as file:
            reader = csv.DictReader(file)
            existing_fieldnames = reader.fieldnames or []
            existing_rows = list(reader)
            file_exists = True

            for row in existing_rows:
                review_id = row.get(
                    "review_id",
                    ""
                )

                if review_id:
                    existing_ids.add(review_id)

    except FileNotFoundError:
        pass

    new_reviews = []

    for review in reviews:
        review_id = review.get(
            "review_id",
            ""
        )

        if review_id:
            if review_id in existing_ids:
                continue

            existing_ids.add(review_id)

        new_reviews.append(review)

    if not new_reviews:
        print(
            "No new reviews to add."
        )
        return

    # If the CSV was created by an older version, rewrite it with the
    # new 27-column header. Existing historical rows receive blanks for
    # the five new product-level star-count columns.
    needs_upgrade = (
        file_exists
        and existing_fieldnames != COLUMNS
    )

    if needs_upgrade:
        print()
        print("Existing CSV uses an older header.")
        print("Upgrading it to the new 27-column format...")

        with open(
            filename,
            "w",
            encoding="utf-8-sig",
            newline=""
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=COLUMNS,
                extrasaction="ignore"
            )

            writer.writeheader()

            for row in existing_rows:
                upgraded_row = {
                    column: row.get(column, "")
                    for column in COLUMNS
                }
                writer.writerow(upgraded_row)

            writer.writerows(new_reviews)

    else:
        mode = "a" if file_exists else "w"

        with open(
            filename,
            mode,
            encoding="utf-8-sig",
            newline=""
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=COLUMNS,
                extrasaction="ignore"
            )

            if not file_exists:
                writer.writeheader()

            writer.writerows(new_reviews)

    print()
    print("=" * 70)
    print(
        f"Saved {len(new_reviews)} new reviews"
    )
    print(
        f"Output file: {filename}"
    )
    print("CSV columns:", len(COLUMNS))
    print("=" * 70)


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 70)
    print("AMAZON REVIEW SCRAPER")
    print("=" * 70)
    print()
    print(
        "This version collects reviews through all five Amazon"
    )
    print(
        "star filters and repeatedly uses 'Show 10 more reviews'."
    )
    print()
    print(
        f"Reviews target per star: {REVIEWS_PER_STAR}"
    )
    print(
        f"Maximum Show-10 clicks per star: "
        f"{MAX_SHOW_MORE_CLICKS_PER_STAR}"
    )
    print()

    product_url = input(
        "Enter Amazon product URL: "
    ).strip()

    if not product_url:
        print(
            "No URL provided."
        )
        return

    with sync_playwright() as p:
        # Persistent context keeps Amazon login/session cookies.
        browser = p.chromium.launch_persistent_context(
            USER_DATA_DIR,
            headless=False,
            viewport={
                "width": 1366,
                "height": 900,
            },
            locale="en-IN",
            timezone_id="Asia/Kolkata",
        )

        # Performance: reviews do not require images, media or web fonts.
        # Keep HTML/JS/CSS requests because they can affect Amazon's rendering.
        def block_heavy_resources(route):
            resource_type = route.request.resource_type
            if resource_type in {"image", "media", "font"}:
                route.abort()
            else:
                route.continue_()

        browser.route("**/*", block_heavy_resources)

        try:
            reviews = scrape_amazon(
                browser,
                product_url
            )

            save_to_csv(
                reviews,
                OUTPUT_FILE
            )

            print()
            print("=" * 70)
            print("SCRAPING COMPLETED")
            print("=" * 70)
            print(
                "Total reviews collected:",
                len(reviews)
            )
            print(
                "Output:",
                OUTPUT_FILE
            )
            print("=" * 70)

        finally:
            browser.close()


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
