"""Runs the existing Playwright scraper (advisor/scrap.py) for ONE product URL.

Executed as a subprocess by scraper_service.py:

    python -m advisor.scrape_worker --url URL --out result.json [--headless] [--reviews-per-star N]

A separate process is used because Playwright's sync API does not coexist well with
Streamlit's script threads / asyncio loop (notably on Windows). Progress is printed to
stdout; the structured result is written to the JSON file given by --out.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback

from . import config, scrap


def _write(path: str, payload: dict) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, default=str)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--reviews-per-star", type=int, default=config.DEFAULT_REVIEWS_PER_STAR)
    args = parser.parse_args()

    scrap.REVIEWS_PER_STAR = args.reviews_per_star
    result = {"status": "error", "message": "", "info": None, "reviews": []}

    try:
        from playwright.sync_api import sync_playwright

        print("Starting browser...", flush=True)
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(config.BROWSER_PROFILE_DIR),
                headless=args.headless,
                viewport={"width": 1366, "height": 900},
                locale="en-IN",
                timezone_id="Asia/Kolkata",
            )

            def route_resources(route):
                # Same optimisation as scrap.main(): skip images, media and fonts.
                if route.request.resource_type in {"image", "media", "font"}:
                    route.abort()
                else:
                    route.continue_()

            context.route("**/*", route_resources)
            try:
                result = scrap.scrape_product_data(context, args.url)
            finally:
                context.close()
    except Exception as exc:  # browser could not start, playwright missing, profile locked ...
        text = str(exc)
        print("Worker error:", text, flush=True)
        traceback.print_exc()
        result = {"status": "browser_error", "message": text, "info": None, "reviews": []}

    _write(args.out, result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
