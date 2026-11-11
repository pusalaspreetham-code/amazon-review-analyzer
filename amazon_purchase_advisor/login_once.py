
from playwright.sync_api import sync_playwright
from advisor import config

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        str(config.BROWSER_PROFILE_DIR),
        headless=False,
        viewport={"width": 1366, "height": 900},
        locale="en-IN",
        timezone_id="Asia/Kolkata"
    )

    page = context.new_page()
    page.goto("https://www.amazon.in/", wait_until="domcontentloaded")

    input("Complete your login manually, then press ENTER here...")

    context.close()
