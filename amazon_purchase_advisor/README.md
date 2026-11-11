# Amazon Product Purchase Advisor

Paste an Amazon.in product link and get a 0-100 recommendation score built from ratings,
seller information and a sentiment analysis of customer reviews (your Playwright scraper +
your trained logistic-regression model).

## Setup

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
streamlit run app.py
```

## Layout

```
app.py                     Streamlit UI entry point
advisor/scrap.py           Your scraper (scrape_product refactored into scrape_product_data; CLI unchanged)
advisor/scrape_worker.py   Runs the scraper in a subprocess (avoids Streamlit/Playwright event-loop clashes)
advisor/scraper_service.py URL validation, subprocess handling, error classification
advisor/data.py            Typed models; unreadable values become None, never 0
advisor/sentiment.py       Model wrapper, confidence stats, star-distribution weighting
advisor/scoring.py         The 6-factor score, missing-data handling, verdict rules
advisor/insights.py        Key feedback + reasons
advisor/config.py          Weights, thresholds, paths: tune everything here
models/                    logistic_regression_model.pkl
```

## Notes

- **Sampling bias is corrected.** The scraper takes ~20 reviews from *each* star level, so raw
  sentiment would look far worse than reality. Sentiment is re-weighted by Amazon's real star
  distribution (the raw sample is still shown).
- **Missing data** is excluded and remaining weights re-normalised. If under 50% of the score is
  backed by data, or fewer than 10 reviews exist, the verdict is *Insufficient Information*.
- **CAPTCHA:** keep *Show browser window* on, solve it once; the persistent profile
  (`amazon_browser_profile/`, copy yours here if you have one) reduces repeats.
- **Model input:** title + review text are joined before prediction. If your model was trained on
  body text only, set `MODEL_INPUT_MODE = "text_only"` in `advisor/config.py`.
- Scraping Amazon may be restricted by its terms of service; use responsibly.
