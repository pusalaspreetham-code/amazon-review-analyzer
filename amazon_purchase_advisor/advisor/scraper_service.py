"""URL validation + running the scraper worker + normalising its output."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple
from urllib.parse import urlparse

from . import config
from .data import Product, Review, reviews_from_rows

AMAZON_HOSTS = {"amazon.in", "www.amazon.in", "m.amazon.in"}
SHORT_HOSTS = {"amzn.in", "www.amzn.in", "amzn.to", "a.co"}
_ASIN = re.compile(r"/(?:dp|gp/product|gp/aw/d|product-reviews)/([A-Za-z0-9]{10})(?:[/?]|$)")

# One browser profile = one scrape at a time (Chromium locks the profile directory).
_SCRAPE_LOCK = threading.Lock()


def parse_amazon_url(raw: str) -> Tuple[Optional[str], Optional[str]]:
    """Return (clean_url, error_message). Exactly one of them is None."""
    raw = (raw or "").strip()
    if not raw:
        return None, "Please paste an Amazon.in product link."
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if host in SHORT_HOSTS:
        return raw, None  # redirects to the product page; the scraper reads the final URL
    if host not in AMAZON_HOSTS:
        return None, "This tool only supports Amazon.in product links (for example https://www.amazon.in/dp/B0XXXXXXXX)."
    match = _ASIN.search(parsed.path + "/")
    if not match:
        return None, "Couldn't find a product ID in that link. Use a product page link that contains /dp/ followed by 10 characters."
    return f"https://www.amazon.in/dp/{match.group(1).upper()}", None


@dataclass
class ScrapeOutcome:
    status: str                      # ok | no_reviews | captcha | unavailable | timeout | error | browser_error | worker_timeout
    message: str = ""
    product: Optional[Product] = None
    reviews: List[Review] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    log: List[str] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        """True when at least the product page was read."""
        return self.product is not None


def friendly_error(outcome: ScrapeOutcome) -> str:
    text = outcome.message or ""
    if outcome.status == "captcha":
        return ("Amazon showed a CAPTCHA. Turn on **Show browser window** in the sidebar, run again, "
                "solve the CAPTCHA once in the browser that opens, then retry.")
    if outcome.status == "unavailable":
        return "The product page could not be read (no title or ID found). Check that the link opens a live product page."
    if outcome.status in ("timeout", "worker_timeout"):
        return "Amazon took too long to respond. Please try again in a moment."
    if outcome.status == "browser_error":
        if "Executable doesn't exist" in text or "playwright install" in text:
            return "The Playwright browser isn't installed. Run `playwright install chromium` in your terminal, then retry."
        if "Missing X server" in text or "headless" in text.lower():
            return "No display is available for the browser window. Turn off **Show browser window** and retry."
        if "profile" in text.lower() or "user data directory" in text.lower():
            return "The browser profile is in use by another window. Close other scraper browsers and retry."
        return f"The browser could not be started: {text[:300]}"
    if "net::ERR_" in text:
        return "Couldn't reach Amazon.in. Check your internet connection and try again."
    return f"Scraping failed: {text.splitlines()[0][:300]}" if text else "Scraping failed for an unknown reason."


def _warnings_from_log(lines: List[str]) -> List[str]:
    warnings = []
    log = "\n".join(lines)
    if "CAPTCHA detected; skipping this star filter" in log:
        warnings.append("Amazon showed a CAPTCHA while loading some review pages; those reviews were skipped.")
    if "star page timed out" in log:
        warnings.append("Some review pages timed out, so fewer reviews were collected.")
    return warnings


def scrape(url: str, reviews_per_star: int = config.DEFAULT_REVIEWS_PER_STAR, headless: bool = False,
           on_log: Optional[Callable[[str], None]] = None,
           timeout: int = config.SCRAPE_TIMEOUT_SECONDS) -> ScrapeOutcome:
    """Run the scraper in a subprocess and return a normalised outcome. Never raises."""
    log: List[str] = []

    def emit(line: str) -> None:
        line = line.rstrip()
        if line:
            log.append(line)
            if on_log:
                on_log(line)

    if not _SCRAPE_LOCK.acquire(blocking=False):
        return ScrapeOutcome("error", "Another analysis is already running. Please wait for it to finish.")
    out_path = None
    try:
        fd, out_path = tempfile.mkstemp(suffix=".json", prefix="advisor_scrape_")
        os.close(fd)
        cmd = [sys.executable, "-u", "-m", "advisor.scrape_worker",
               "--url", url, "--out", out_path, "--reviews-per-star", str(reviews_per_star)]
        if headless:
            cmd.append("--headless")
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}

        proc = subprocess.Popen(cmd, cwd=str(config.PROJECT_ROOT), env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        timed_out = threading.Event()

        def kill() -> None:
            timed_out.set()
            proc.kill()

        timer = threading.Timer(timeout, kill)
        timer.start()
        try:
            for line in proc.stdout:
                emit(line)
            proc.wait()
        finally:
            timer.cancel()

        if timed_out.is_set():
            return ScrapeOutcome("worker_timeout", f"Scraping exceeded {timeout} seconds.", log=log)

        try:
            with open(out_path, encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, ValueError):
            tail = " | ".join(log[-3:])
            return ScrapeOutcome("error", f"The scraper stopped unexpectedly. {tail}", log=log)

        product = Product.from_info(raw["info"]) if raw.get("info") else None
        reviews = reviews_from_rows(raw.get("reviews") or [])
        status = raw.get("status", "error")
        if status == "ok" and not reviews:
            status = "no_reviews"
        return ScrapeOutcome(status, raw.get("message", ""), product, reviews,
                             _warnings_from_log(log), log)
    except Exception as exc:  # e.g. cannot spawn Python
        return ScrapeOutcome("error", str(exc), log=log)
    finally:
        _SCRAPE_LOCK.release()
        if out_path and os.path.exists(out_path):
            try:
                os.remove(out_path)
            except OSError:
                pass
