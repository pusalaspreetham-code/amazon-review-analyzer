"""
Collect 100 NEW Amazon.in product URLs from bestseller pages.

Install:
    pip install playwright
    playwright install chromium

Put previously used product URLs, one per line, in existing_urls.txt.
Run:
    python collect_100_more_amazon_links.py

Creates:
    amazon_100_more_links.txt
    amazon_100_more_links.py  (PRODUCT_URLS list)

Amazon may rate-limit automated browsing. This script only records URLs whose
ASIN is actually present in a product-detail URL; it does not invent ASINs.
"""
import re, time, random
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

TARGET = 100
EXISTING_FILE = Path("existing_urls.txt")
OUT_TXT = Path("amazon_100_more_links.txt")
OUT_PY = Path("amazon_100_more_links.py")

CATEGORIES = [
    "https://www.amazon.in/gp/bestsellers/electronics",
    "https://www.amazon.in/gp/bestsellers/computers",
    "https://www.amazon.in/gp/bestsellers/phones",
    "https://www.amazon.in/gp/bestsellers/home",
    "https://www.amazon.in/gp/bestsellers/kitchen",
    "https://www.amazon.in/gp/bestsellers/books",
    "https://www.amazon.in/gp/bestsellers/beauty",
    "https://www.amazon.in/gp/bestsellers/toys",
    "https://www.amazon.in/gp/bestsellers/sports",
    "https://www.amazon.in/gp/bestsellers/fashion",
]

# Additional ASINs already mentioned in recent lists; always skip these.
KNOWN_OLD = set("""
B0DGJ7X1DX B0F3XP9GRT B0CP7W9ZDZ B07WHR9QZH B0CWTYGPH8
B0DG1XGV2L B0CRDVFK6B B0CNK1VTZW B0CCKPTMYX B0C5Y3JBC4
B093Q3R1VV B0F4XHB911 B0D32TY16C B0D2Y1BLDT B0D262YX9D
B0C3RF3HT3 B0CH1L1YLC B0DBGP48NW B09QL2WWC4 B09MTQ23X4
B0CQJWMMG7 B0CRH561RC B08XY16Y6J B0DNJXJS35 B0DFWL8F5C
B0DGV6TB8D B0CY2377YW B07PR1CL3S B0CX1YQ764 B0DH88LZ11
B0DBZTBVXQ B0DT49VKFD B08XC5LQ7B B0BRY7YPFK B00CLIV89Q
B07HRDTJ8W B0CZXSSHM7 B0CQ4KTCH1 B0CF1NTL6M B0CGDZC2FK
B0BC1JPSDR B016M91SS0 B09PBRTVY4 B01GZSQJPA B00EDJJ7FS
B0D6VFV3ZP B08X9YSV2D 9384761540 9334262001 B08FX1R6WY
B0DPS7FB4J B0D2D54Q5M B0CP7VP1VV B0C3ZYFZ77 B0CBTTCJL6
B0C7QS9M38 B09N3ZLB3T B0F5BGTXGG B0856HNLDK B08667772G
B0DGTSRX3R B0D5HJNQD9 B0CC2G8L22 B0DGTSTQWL B0D812G7FL
B0D8134JH8 B0D813HQFN B0CP7TH3YB B0BY8MCQ9S B0DZ78F2CT
B0BJLDFNVL B0CHX5R7C2 B09V4FNFHN
B0D9H338J9 B0DFWVTQQ7 B0CKLWMKYX B0D7PSYS6B B006YG8X9Y
B09MM58Y7Q B08C4Z69LN B0CCVZP835 B0CZ3ZPD8B B0DPFTYQN7
B0DPFST37Y B0CNRFYLV8
""".split())

def asin_from(url):
    m = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})(?:[/?]|$)", url, re.I)
    return m.group(1).upper() if m else None

def main():
    old = set(KNOWN_OLD)
    if EXISTING_FILE.exists():
        for line in EXISTING_FILE.read_text(encoding="utf-8").splitlines():
            a = asin_from(line.strip())
            if a:
                old.add(a)

    results, seen = [], set(old)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(locale="en-IN", viewport={"width": 1365, "height": 900})
        page = context.new_page()

        for category in CATEGORIES:
            if len(results) >= TARGET:
                break
            for pg in range(1, 6):
                if len(results) >= TARGET:
                    break
                url = category if pg == 1 else f"{category}?pg={pg}"
                print("Opening:", url)
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_timeout(random.randint(1800, 3000))
                except PlaywrightTimeoutError:
                    print("Timed out; checking links that loaded.")

                text = (page.locator("body").inner_text(timeout=5000) or "").lower()
                if "robot check" in text or "enter the characters you see below" in text:
                    input("Solve the Amazon check in the browser, then press Enter here...")

                hrefs = page.locator('a[href*="/dp/"], a[href*="/gp/product/"]').evaluate_all(
                    "(els) => els.map(a => a.href)"
                )
                for href in hrefs:
                    a = asin_from(href)
                    if not a or a in seen:
                        continue
                    seen.add(a)
                    results.append(f"https://www.amazon.in/dp/{a}")
                    print(f"{len(results):3}/{TARGET}  {results[-1]}")
                    if len(results) >= TARGET:
                        break
                time.sleep(random.uniform(1.5, 2.7))
        browser.close()

    OUT_TXT.write_text("\n".join(results) + ("\n" if results else ""), encoding="utf-8")
    py = ["PRODUCT_URLS = ["] + [f'    "{u}",' for u in results] + ["]"]
    OUT_PY.write_text("\n".join(py) + "\n", encoding="utf-8")
    print(f"Collected {len(results)} unique URLs.")
    print("Saved:", OUT_TXT.resolve())
    print("Saved:", OUT_PY.resolve())
    if len(results) < TARGET:
        print("Fewer than 100 were available in this run; Amazon may have blocked or limited results.")

if __name__ == "__main__":
    main()
