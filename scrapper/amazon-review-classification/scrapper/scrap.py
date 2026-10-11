
import csv
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

OUTPUT_FILE = "amazon_reviews.csv"
USER_DATA_DIR = "amazon_browser_profile"
PRODUCT_URLS = [
    "https://www.amazon.in/dp/B0DGHZWBYB",
    "https://www.amazon.in/dp/B0DSC4YJRD",
    "https://www.amazon.in/dp/B0D9S87H53",
    "https://www.amazon.in/dp/B0FM38916Y",
    "https://www.amazon.in/dp/B0FNWNZZ1B",
    "https://www.amazon.in/dp/B0FZSWZZW2",
    "https://www.amazon.in/dp/B0GN1P5CSY",
    "https://www.amazon.in/dp/B0GYRKTVKB",
    "https://www.amazon.in/dp/B008FWZGSG",
    "https://www.amazon.in/dp/B0BJ72WZQ7",
    "https://www.amazon.in/dp/B0FDQK5KSZ",
    "https://www.amazon.in/dp/B0G2H4R5YB",
    "https://www.amazon.in/dp/B09ZPL5VYM",
    "https://www.amazon.in/dp/B0GS5Y6BD3",
    "https://www.amazon.in/dp/B0G81P4MPG",
    "https://www.amazon.in/dp/B0BTD4S4XF",
    "https://www.amazon.in/dp/B0DZHJT3JB",
    "https://www.amazon.in/dp/B071Z8M4KX",
    "https://www.amazon.in/dp/B0CV42PXQN",
    "https://www.amazon.in/dp/B0HBPNBC7B",
    "https://www.amazon.in/dp/B0GMQWZ6ZM",
    "https://www.amazon.in/dp/B0FCMPJQ1J",
    "https://www.amazon.in/dp/B0HCNHGQDD",
    "https://www.amazon.in/dp/B0CR7N9MD9",
    "https://www.amazon.in/dp/B0FN89KT94",
    "https://www.amazon.in/dp/B0GDTRYXYF",
    "https://www.amazon.in/dp/B0GW61YKQK",
    "https://www.amazon.in/dp/B0GRGY8GTV",
    "https://www.amazon.in/dp/B0CH3G9VR2",
    "https://www.amazon.in/dp/B0G4MZ85QG",
    "https://www.amazon.in/dp/B0DH3J6LB9",
    "https://www.amazon.in/dp/B0GX52LD7V",
    "https://www.amazon.in/dp/B0HBBTV4J4",
    "https://www.amazon.in/dp/B0CF1M3PF9",
    "https://www.amazon.in/dp/B0GR6J183B",
    "https://www.amazon.in/dp/B097JJ2CK6",
    "https://www.amazon.in/dp/B0FBRS76BR",
    "https://www.amazon.in/dp/B0FFTLRYRV",
    "https://www.amazon.in/dp/B0DNFSSF3F",
    "https://www.amazon.in/dp/B08ZJG6TVT",
    "https://www.amazon.in/dp/B0CQRNWJM2",
    "https://www.amazon.in/dp/B0GWQHQB4T",
    "https://www.amazon.in/dp/B0GVRZD89W",
    "https://www.amazon.in/dp/B0GPVVYKTQ",
    "https://www.amazon.in/dp/B08LHTJTBB",
    "https://www.amazon.in/dp/B0CXDN7V9N",
    "https://www.amazon.in/dp/B0G1C13SB3",
    "https://www.amazon.in/dp/B0G4QQ4FYB",
    "https://www.amazon.in/dp/B0GDPWLJMM",
    "https://www.amazon.in/dp/B0FMRLJ9LF",
    "https://www.amazon.in/dp/B097GNF52Q",
    "https://www.amazon.in/dp/B0CR6JQT6F",
    "https://www.amazon.in/dp/B09VTDMRY7",
    "https://www.amazon.in/dp/B0DV5C5FR2",
    "https://www.amazon.in/dp/B0DSHZLRQB",
    "https://www.amazon.in/dp/B0DXQFRQZP",
    "https://www.amazon.in/dp/B0G4VNYG5N",
    "https://www.amazon.in/dp/B09BFV96TS",
    "https://www.amazon.in/dp/B0GQVHBK9M",
    "https://www.amazon.in/dp/B01L8ZNWN2",
    "https://www.amazon.in/dp/B0BL6S8KHM",
    "https://www.amazon.in/dp/B01DGVKBC6",
    "https://www.amazon.in/dp/B0C4PVS224",
    "https://www.amazon.in/dp/B0BN1XT6TF",
    "https://www.amazon.in/dp/B0FJ2LY2JN",
    "https://www.amazon.in/dp/B0FFD2YSBY",
    "https://www.amazon.in/dp/B09QGZFBPM",
    "https://www.amazon.in/dp/B0CP9NSXYJ",
    "https://www.amazon.in/dp/B00A0VCJPI",
    "https://www.amazon.in/dp/B0GY8KNSFC",
    "https://www.amazon.in/dp/B07KNMHVQL",
    "https://www.amazon.in/dp/B094QZXZ8D",
    "https://www.amazon.in/dp/B0CL72GGSF",
    "https://www.amazon.in/dp/B0CSNKC44N",
    "https://www.amazon.in/dp/B0GMQLQGFW",
    "https://www.amazon.in/dp/B08GTYFC37",
]


START_PRODUCT = 1
END_PRODUCT = None
REVIEWS_PER_STAR = 20
MAX_PAGES_PER_STAR = 30

COLUMNS = [
    "review_id", "product_id", "source", "product_name", "category",
    "product_url", "seller_name", "seller_rating", "price", "original_price",
    "discount_percentage", "fulfillment", "product_rating",
    "total_product_reviews", "five_star_review_count", "four_star_review_count",
    "three_star_review_count", "two_star_review_count", "one_star_review_count",
    "review_title", "review_text", "review_rating", "verified_purchase",
    "variant", "helpful_votes", "review_age", "sentiment",
]
COUNT_FIELDS = {
    "total_product_reviews", "five_star_review_count", "four_star_review_count",
    "three_star_review_count", "two_star_review_count", "one_star_review_count",
    "helpful_votes",
}
REQUIRED = ["review_id", "product_id", "product_name", "review_title", "review_text", "review_rating"]
STAR_FILTERS = [(5, "five_star"), (4, "four_star"), (3, "three_star"), (2, "two_star"), (1, "one_star")]


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def missing(value):
    return value is None or clean(value).lower() in {"", "nan", "none", "null"}


def output_value(field, value):
    return clean(value) if not missing(value) else (0 if field in COUNT_FIELDS else "Not Available")


def get_text(locator):
    try:
        return clean(locator.first.text_content()) if locator.count() else ""
    except Exception:
        return ""


def get_attr(locator, name):
    try:
        return clean(locator.first.get_attribute(name)) if locator.count() else ""
    except Exception:
        return ""


def number(value):
    m = re.search(r"\d+(?:\.\d+)?", clean(value).replace(",", "").replace("₹", ""))
    if not m:
        return ""
    n = float(m.group())
    return int(n) if n.is_integer() else n


def rating(value):
    m = re.search(r"(\d+(?:\.\d+)?)\s+out\s+of\s+5", clean(value), re.I)
    if not m:
        return ""
    n = float(m.group(1))
    return n if 0 <= n <= 5 else ""


def wait_page(page):
    try:
        page.wait_for_load_state("domcontentloaded", timeout=15000)
    except Exception:
        pass
    try:
        page.locator('[data-hook="review"]').first.wait_for(state="attached", timeout=6000)
    except Exception:
        try:
            page.locator("#productTitle").first.wait_for(state="attached", timeout=2500)
        except Exception:
            pass


def captcha(page):
    body = get_text(page.locator("body")).lower()
    return any(s in body for s in ("robot check", "captcha", "enter the characters"))


def get_asin(page, url):
    for value in (page.url, url):
        m = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", value, re.I)
        if m:
            return m.group(1).upper()
    return ""


def get_category(page):
    for selector in ("#wayfinding-breadcrumbs_feature_div", "#wayfinding-breadcrumbs_container"):
        value = get_text(page.locator(selector))
        if value:
            parts = [clean(x) for x in re.split(r"\s*[>›]\s*", value) if clean(x)]
            if parts:
                return " > ".join(parts)
    return ""


def get_price(page, selectors):
    for selector in selectors:
        loc = page.locator(selector)
        for i in range(loc.count()):
            value = number(get_text(loc.nth(i)))
            if value != "":
                return value
    return ""


def review_age(value):
    m = re.search(r"\bon\s+(.+)", clean(value), re.I)
    if not m:
        return ""
    date_text = clean(m.group(1))
    parsed = None
    for fmt in ("%d %B %Y", "%d %b %Y"):
        try:
            parsed = datetime.strptime(date_text, fmt)
            break
        except ValueError:
            pass
    if parsed is None:
        return date_text
    days = (datetime.now() - parsed).days
    if days < 0:
        return date_text
    if days == 0:
        return "Today"
    if days == 1:
        return "1 day ago"
    if days < 30:
        return f"{days} days ago"
    months = days // 30
    if months < 12:
        return f"{months} month" + ("" if months == 1 else "s") + " ago"
    years = months // 12
    return f"{years} year" + ("" if years == 1 else "s") + " ago"


def valid_review(row):
    if any(missing(row.get(k)) for k in REQUIRED):
        return False
    try:
        return 1 <= float(row["review_rating"]) <= 5
    except (TypeError, ValueError):
        return False


def read_reviews(page, info):
    script = r'''() => {
      const clean = v => (v || "").toString().replace(/\s+/g, " ").trim();
      const get = (root, sels) => {
        for (const s of sels) {
          const e = root.querySelector(s);
          if (e && clean(e.textContent)) return clean(e.textContent);
        }
        return "";
      };
      return Array.from(document.querySelectorAll('[data-hook="review"]')).map(r => {
        const id = clean(r.getAttribute("id") || r.querySelector("[data-reviewid]")?.getAttribute("data-reviewid") || "");
        const rt = get(r, ['[data-hook="review-star-rating"]','[data-hook="cmps-review-star-rating"]','.review-star-rating']);
        const rm = rt.match(/(\d+(?:\.\d+)?)\s+out\s+of\s+5\s+stars?/i);
        let title = get(r, ['[data-hook="reviewTitle"]','[data-hook="review-title"]','[data-hook="review-title-content"]','.review-title']);
        title = clean(title.replace(/^\d+(?:\.\d+)?\s+out\s+of\s+5\s+stars?\s*/i, ""));
        let body = get(r, ['[data-hook="reviewRichContentContainer"]','[data-hook="reviewText"]','[data-hook="review-body"]','[data-hook="review-body-content"]','.review-text-content','.reviewText','.reviewTextContainer']);
        body = clean(body.replace(/Brief content visible, double tap to read full content\.?/gi, "").replace(/Full content visible, double tap to read brief content\.?/gi, ""));
        const all = clean(r.textContent);
        const hm = all.match(/([\d,]+)\s+people\s+found\s+this\s+helpful/i);
        const helpful = hm ? Number(hm[1].replace(/,/g, "")) : (/one\s+person\s+found\s+this\s+helpful/i.test(all) ? 1 : 0);
        const verified = /verified\s+purchase/i.test(get(r, ['[data-hook="avp-badge"]','[data-hook="review-verified-badge"]','.avp-badge'])) || /verified\s+purchase/i.test(all);
        return {review_id:id, review_title:title, review_text:body, review_rating:rm ? Number(rm[1]) : "",
          helpful_votes:helpful, verified_purchase:verified ? "Yes" : "Not Available",
          variant:get(r, ['[data-hook="format-strip"]','[data-hook="product-variation-attributes"]','.review-format-strip','.product-variation-attributes']),
          date:get(r, ['[data-hook="review-date"]'])};
      });
    }'''
    try:
        raw_rows = page.evaluate(script)
    except Exception:
        return []
    rows = []
    for raw in raw_rows:
        row = dict(info)
        row.update({
            "review_id": clean(raw.get("review_id")),
            "review_title": clean(raw.get("review_title")),
            "review_text": clean(raw.get("review_text")),
            "review_rating": raw.get("review_rating", ""),
            "helpful_votes": raw.get("helpful_votes", 0),
            "verified_purchase": raw.get("verified_purchase", "Not Available"),
            "variant": clean(raw.get("variant")),
            "review_age": review_age(raw.get("date", "")),
            "sentiment": "Not Available",
        })
        if valid_review(row):
            rows.append(row)
        else:
            print("Skipping incomplete review:", row.get("review_id") or "(missing ID)")
    return rows


def star_urls(page, asin):
    urls = {}
    for stars, label in STAR_FILTERS:
        found = ""
        for selector in (f'#histogramTable a[href*="filterByStar={label}"]', f'a[href*="filterByStar={label}"]'):
            loc = page.locator(selector)
            for i in range(loc.count()):
                href = loc.nth(i).get_attribute("href")
                if href:
                    found = urljoin(page.url, href)
                    break
            if found:
                break
        urls[stars] = found or f"https://www.amazon.in/portal/customer-reviews/{asin}/?ie=UTF8&reviewerType=all_reviews&filterByStar={label}"
    return urls


def exact_count(page):
    for selector in ('[data-hook="cr-filter-info-review-rating-count"]', '[data-hook="cr-filter-info-section"]'):
        m = re.search(r"([\d,]+)\s+matching\s+customer\s+reviews?", get_text(page.locator(selector)), re.I)
        if m:
            return int(m.group(1).replace(",", ""))
    return 0


def next_link(page):
    for selector in ('a[href*="cm_cr_getr_d_paging_btm_"]', 'a:has-text("Show 10 more reviews")', 'a[data-hook="next-button"]'):
        loc = page.locator(selector)
        for i in range(loc.count()):
            item = loc.nth(i)
            try:
                if not item.is_visible():
                    continue
            except Exception:
                pass
            href = item.get_attribute("href")
            label = clean(item.text_content()).lower()
            if href and ("cm_cr_getr_d_paging_btm_" in href or "show 10 more reviews" in label):
                return item
    return None


def collect_star(context, info, stars, label, url):
    page = context.new_page()
    rows, seen, count = [], set(), 0
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        wait_page(page)
        if captcha(page):
            print("CAPTCHA detected; skipping this star filter.")
            return [], 0
        if page.locator('[data-hook="review"]').count() == 0:
            print(f"No reviews visible for {stars}-star filter.")
            return [], 0
        count = exact_count(page)
        signatures = set()
        for _ in range(MAX_PAGES_PER_STAR + 1):
            if captcha(page):
                break
            current = read_reviews(page, info)
            for row in current:
                if row["review_id"] and row["review_id"] not in seen:
                    seen.add(row["review_id"])
                    rows.append(row)
            if len(rows) >= REVIEWS_PER_STAR:
                break
            signature = tuple(r["review_id"] for r in current)
            if signature in signatures:
                break
            signatures.add(signature)
            try:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(200)
            except Exception:
                pass
            link = next_link(page)
            if link is None:
                break
            href = link.get_attribute("href")
            if not href:
                break
            target = urljoin(page.url, href)
            parsed = urlparse(target)
            query = parse_qs(parsed.query, keep_blank_values=True)
            query["filterByStar"] = [label]
            target = urlunparse(parsed._replace(query=urlencode(query, doseq=True)))
            old_ids = set(seen)
            try:
                link.click(timeout=5000, force=True)
                page.wait_for_timeout(700)
                after = read_reviews(page, info)
                if not any(r["review_id"] not in old_ids for r in after):
                    page.goto(target, wait_until="domcontentloaded", timeout=45000)
                    wait_page(page)
            except Exception:
                try:
                    page.goto(target, wait_until="domcontentloaded", timeout=45000)
                    wait_page(page)
                except Exception:
                    break
        return rows, count
    except PlaywrightTimeoutError:
        print(f"{stars}-star page timed out.")
        return rows, count
    except Exception as exc:
        print(f"{stars}-star error:", exc)
        return rows, count
    finally:
        page.close()


def scrape_product(context, url):
    page = context.new_page()
    try:
        print("\nProcessing:", url)
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        wait_page(page)
        if captcha(page):
            print("CAPTCHA on product page; skipping.")
            return []
        asin = get_asin(page, url)
        name = get_text(page.locator("#productTitle")) or get_text(page.locator("#title"))
        if not asin or not name:
            print("Product ID/title unavailable; skipping URL.")
            return []
        seller = get_text(page.locator("#sellerProfileTriggerId")) or get_text(page.locator("#merchant-info"))
        seller_url = get_attr(page.locator("#sellerProfileTriggerId"), "href")
        if seller_url:
            seller_url = urljoin(page.url, seller_url)
        seller_rating = ""
        if seller_url:
            sp = context.new_page()
            try:
                sp.goto(seller_url, wait_until="domcontentloaded", timeout=30000)
                seller_rating = rating(get_text(sp.locator("#seller-info-feedback-summary .feedback-detail-stars .a-icon-alt")))
            except Exception:
                pass
            finally:
                sp.close()
        info = {
            "product_id": asin, "source": "Amazon", "product_name": name,
            "category": get_category(page), "product_url": url,
            "seller_name": re.sub(r"^Sold by\s*", "", seller, flags=re.I),
            "seller_rating": seller_rating,
            "price": get_price(page, ['#corePriceDisplay_desktop_feature_div .a-price .a-offscreen','#corePrice_feature_div .a-price .a-offscreen','#priceblock_ourprice','#priceblock_dealprice']),
            "original_price": get_price(page, ['.basisPrice .a-offscreen','span.a-price.a-text-price span.a-offscreen','#listPrice']),
            "discount_percentage": number(get_text(page.locator(".savingsPercentage")).replace("%", "")),
            "fulfillment": get_text(page.locator("#AMAZON_DELIVERED")),
            "product_rating": rating(get_attr(page.locator("#acrPopover"), "title")) or rating(get_text(page.locator("#averageCustomerReviews .a-icon-alt"))),
            "total_product_reviews": number(get_text(page.locator("#acrCustomerReviewText"))) or 0,
            "five_star_review_count": 0, "four_star_review_count": 0,
            "three_star_review_count": 0, "two_star_review_count": 0,
            "one_star_review_count": 0,
        }
        urls = star_urls(page, asin)
        page.close()
        page = None
        all_rows, ids, counts = [], set(), {}
        for stars, label in STAR_FILTERS:
            rows, count = collect_star(context, info, stars, label, urls[stars])
            counts[stars] = count or 0
            for row in rows:
                if row["review_id"] not in ids:
                    ids.add(row["review_id"])
                    all_rows.append(row)
        field_by_star = {5:"five_star_review_count",4:"four_star_review_count",3:"three_star_review_count",2:"two_star_review_count",1:"one_star_review_count"}
        for row in all_rows:
            for stars, field in field_by_star.items():
                row[field] = counts.get(stars, 0)
        print("Complete reviews collected:", len(all_rows))
        return all_rows
    except PlaywrightTimeoutError:
        print("Product timed out; moving to next URL.")
        return []
    except Exception as exc:
        print("Product failed; moving to next URL:", exc)
        return []
    finally:
        if page is not None:
            page.close()


def save_csv(rows):
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8-sig", newline="") as f:
            existing = list(csv.DictReader(f))
    except FileNotFoundError:
        existing = []
    ids = {clean(row.get("review_id")) for row in existing if clean(row.get("review_id"))}
    old_normalized = [{c: output_value(c, r.get(c, "")) for c in COLUMNS} for r in existing]
    new_normalized = []
    for row in rows:
        if not valid_review(row):
            continue
        rid = clean(row.get("review_id"))
        if not rid or rid in ids:
            continue
        ids.add(rid)
        new_normalized.append({c: output_value(c, row.get(c, "")) for c in COLUMNS})
    if not old_normalized and not new_normalized:
        print("No complete reviews to save.")
        return
    with open(OUTPUT_FILE, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(old_normalized + new_normalized)
    print(f"Saved {len(new_normalized)} new rows; {len(old_normalized) + len(new_normalized)} total rows.")


def validate_csv():
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        blanks = [(i + 2, c) for i, row in enumerate(rows) for c in COLUMNS if missing(row.get(c))]
        print(f"CSV validation: {len(rows)} rows; {len(blanks)} blank cells.")
        if blanks:
            print("First blank cells:", blanks[:10])
    except FileNotFoundError:
        print("CSV has not been created yet.")


def main():
    if not PRODUCT_URLS:
        print("Add Amazon.in URLs to PRODUCT_URLS before running.")
        return
    start = max(1, START_PRODUCT)
    end = len(PRODUCT_URLS) if END_PRODUCT is None else min(len(PRODUCT_URLS), END_PRODUCT)
    if start > end:
        print("Invalid product range.")
        return
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            USER_DATA_DIR, headless=False,
            viewport={"width": 1366, "height": 900},
            locale="en-IN", timezone_id="Asia/Kolkata"
        )
        def route_resources(route):
            if route.request.resource_type in {"image", "media", "font"}:
                route.abort()
            else:
                route.continue_()
        context.route("**/*", route_resources)
        try:
            for index in range(start - 1, end):
                url = PRODUCT_URLS[index]
                try:
                    reviews = scrape_product(context, url)
                    save_csv(reviews)
                    print(f"Finished product {index + 1}/{len(PRODUCT_URLS)}.")
                except Exception as exc:
                    print("Unexpected error; continuing:", exc)
        finally:
            context.close()
    validate_csv()


if __name__ == "__main__":
    main()
