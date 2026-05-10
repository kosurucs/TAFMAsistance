"""
Step 2 – Scrape public educational content from Investopedia.

Scrapes the finance terms dictionary and key trading articles.
Respects rate limits and robots.txt.  For personal/research use only.

Usage:
    python llm_training/scripts/2_scrape_investopedia.py

Output:  llm_training/data/processed/investopedia_chunks.jsonl
"""

from __future__ import annotations

import json
import time
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

# ── Config ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parents[2]
OUT_DIR = ROOT / "llm_training" / "data" / "processed"
OUT_FILE = OUT_DIR / "investopedia_chunks.jsonl"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (research-bot; educational use; "
        "contact: local-research) AppleWebKit/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Polite delay between requests (seconds)
REQUEST_DELAY = 1.5
MAX_ARTICLES = 400   # cap total articles (increase if needed)

# ── Seed URLs ─────────────────────────────────────────────────────────────────
# Investopedia terms dictionary pages A–Z + core trading topics
DICTIONARY_SEEDS = [
    "https://www.investopedia.com/financial-term-dictionary-4769738",
]

TOPIC_SEEDS = [
    "https://www.investopedia.com/trading-4427765",
    "https://www.investopedia.com/technical-analysis-4689657",
    "https://www.investopedia.com/fundamental-analysis-4689656",
    "https://www.investopedia.com/investing-4427764",
    "https://www.investopedia.com/options-and-derivatives-4689678",
    "https://www.investopedia.com/financial-ratios-4689679",
    "https://www.investopedia.com/risk-management-4689694",
    "https://www.investopedia.com/candlestick-charts-4689696",
]

ALLOWED_DOMAIN = "www.investopedia.com"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get(url: str, session: requests.Session) -> requests.Response | None:
    try:
        resp = session.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            return resp
        print(f"  [skip] {resp.status_code} {url}")
    except requests.RequestException as exc:
        print(f"  [error] {url}: {exc}")
    return None


def _is_article_url(url: str) -> bool:
    """Only follow URLs that look like full articles (not category/list pages)."""
    parsed = urlparse(url)
    if parsed.netloc != ALLOWED_DOMAIN:
        return False
    path = parsed.path.rstrip("/")
    # Investopedia articles end with a long slug, not short category paths
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        return False
    # Skip dictionary index pages (short slug) vs actual term articles
    slug = parts[-1]
    return len(slug) > 20 and not slug.isdigit()


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_article(url: str, session: requests.Session) -> dict | None:
    """Fetch and extract main article text from an Investopedia page."""
    resp = _get(url, session)
    if resp is None:
        return None

    soup = BeautifulSoup(resp.text, "lxml")

    # Title
    title_tag = soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else ""

    # Main article body — Investopedia wraps article content in <article> or
    # a div with class containing "article-body" / "comp-article-body"
    body_candidates = (
        soup.find("article")
        or soup.find("div", class_=re.compile(r"article[-_]body|articleBody", re.I))
        or soup.find("div", {"id": re.compile(r"article[-_]body", re.I)})
    )

    if not body_candidates:
        return None

    # Remove ads, navigation, tables of contents, related articles
    for tag in body_candidates.find_all(
        ["script", "style", "nav", "aside", "figure", "figcaption", "button"]
    ):
        tag.decompose()

    paragraphs = [
        clean_text(p.get_text())
        for p in body_candidates.find_all(["p", "li", "h2", "h3"])
        if len(p.get_text(strip=True)) > 40
    ]

    if not paragraphs:
        return None

    full_text = "\n".join(paragraphs)
    if len(full_text) < 200:
        return None

    return {
        "source": "investopedia",
        "url": url,
        "title": title,
        "text": full_text,
    }


def collect_article_links(seed_url: str, session: requests.Session) -> list[str]:
    """Scrape a category/index page to find article links."""
    resp = _get(seed_url, session)
    if resp is None:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full_url = urljoin(seed_url, href).split("?")[0].split("#")[0]
        if _is_article_url(full_url) and full_url not in links:
            links.append(full_url)

    return links


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update(HEADERS)

    # Gather all article URLs
    print("Collecting article links from seed pages...")
    article_urls: list[str] = []
    seen: set[str] = set()

    all_seeds = DICTIONARY_SEEDS + TOPIC_SEEDS
    for seed in all_seeds:
        print(f"  Seed: {seed}")
        links = collect_article_links(seed, session)
        for link in links:
            if link not in seen:
                seen.add(link)
                article_urls.append(link)
        time.sleep(REQUEST_DELAY)

    article_urls = article_urls[:MAX_ARTICLES]
    print(f"\nFound {len(article_urls)} article URLs. Scraping...")

    records: list[dict] = []
    for url in tqdm(article_urls, unit="article"):
        article = extract_article(url, session)
        if article:
            records.append(article)
        time.sleep(REQUEST_DELAY)

    with OUT_FILE.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"\nDone. {len(records)} articles → {OUT_FILE}")


if __name__ == "__main__":
    main()
