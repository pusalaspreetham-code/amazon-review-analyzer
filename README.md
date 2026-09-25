# Amazon Review Analyzer

Amazon Review Analyzer is a machine learning project that collects product reviews from Amazon and prepares them for sentiment analysis and review-based product insights.

## Current Status

The Amazon review scraper is currently implemented.

The scraper can:

- Accept Amazon product URLs
- Extract product information
- Extract seller information and seller rating
- Extract product rating and total review count
- Extract exact 5★, 4★, 3★, 2★ and 1★ review counts
- Collect reviews from different star filters
- Extract review title and review text
- Extract review rating
- Extract verified-purchase information
- Extract product variant
- Extract helpful votes
- Extract review age
- Save collected data into a CSV file

## Tech Stack

- Python
- Playwright
- BeautifulSoup
- Pandas
- Regular Expressions

## Dataset

Each review is stored as a separate row.

The current dataset contains product-level and review-level information such as:

- Product ID
- Product Name
- Category
- Seller
- Seller Rating
- Price
- Original Price
- Discount
- Product Rating
- Total Product Reviews
- 5★–1★ Review Counts
- Review Title
- Review Text
- Review Rating
- Verified Purchase
- Variant
- Helpful Votes
- Review Age
- Sentiment

## Project Structure

```text
amazon-review-analyzer/
│
├── scraper/
│   └── test_scraper.py
│
├── data/
│
├── ml/
│
├── app/
│
├── .gitignore
├── requirements.txt
└── README.md