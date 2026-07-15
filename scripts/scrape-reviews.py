"""
scrape-reviews.py
-----------------
Scrapes real product information for the 6 Electronics scenario items from:
  1. Apple.com  — official product descriptions and specs
  2. 9to5Mac    — editorial reviews
  3. MacRumors  — buyer's guide and community discussion

Saves one .txt file per item into data/product-docs/ELECTRONICS/

Usage:
    cd "DT Study"
    source venv/bin/activate
    python scripts/scrape-reviews.py
"""

import os
import time
import requests
from bs4 import BeautifulSoup

OUTPUT_DIR = "data/product-docs/ELECTRONICS"
os.makedirs(OUTPUT_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

PRODUCTS = [
    {
        "code": "AIRPODS2",
        "name": "Apple AirPods 2nd Generation",
        "apple_url": "https://www.apple.com/airpods-2nd-generation/",
        "ninemac_query": "AirPods 2nd generation review",
        "macrumors_url": "https://www.macrumors.com/guide/airpods/",
    },
    {
        "code": "AIRPODSPROMAX",
        "name": "Apple AirPods Max",
        "apple_url": "https://www.apple.com/airpods-max/",
        "ninemac_query": "AirPods Max review",
        "macrumors_url": "https://www.macrumors.com/guide/airpods-max/",
    },
    {
        "code": "IPAD9",
        "name": "Apple iPad 9th Generation",
        "apple_url": "https://www.apple.com/ipad-10.2/",
        "ninemac_query": "iPad 9th generation review",
        "macrumors_url": "https://www.macrumors.com/guide/ipad/",
    },
    {
        "code": "IPAD12",
        "name": "Apple iPad Air M2",
        "apple_url": "https://www.apple.com/ipad-air/",
        "ninemac_query": "iPad Air M2 review",
        "macrumors_url": "https://www.macrumors.com/guide/ipad-air/",
    },
    {
        "code": "APPLEPENCIL2",
        "name": "Apple Pencil 2nd Generation",
        "apple_url": "https://www.apple.com/apple-pencil/",
        "ninemac_query": "Apple Pencil 2nd generation review compatibility",
        "macrumors_url": "https://www.macrumors.com/guide/apple-pencil/",
    },
    {
        "code": "APPLEPENCILPRO",
        "name": "Apple Pencil Pro",
        "apple_url": "https://www.apple.com/apple-pencil/",
        "ninemac_query": "Apple Pencil Pro review",
        "macrumors_url": "https://www.macrumors.com/guide/apple-pencil/",
    },
]

# ── Scrapers ──────────────────────────────────────────────────────────────────

def scrape_page(url, label, text_tags=("p", "li"), min_len=40, max_chars=4000):
    """Generic scraper — fetches a URL and extracts paragraph/list text."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            print(f"    {label}: HTTP {r.status_code}")
            return None

        soup = BeautifulSoup(r.text, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "aside", "iframe", "head"]):
            tag.decompose()

        chunks = []
        for tag in text_tags:
            for el in soup.find_all(tag):
                t = el.get_text(separator=" ", strip=True)
                if len(t) >= min_len:
                    chunks.append(t)

        text = "\n".join(chunks)
        if not text:
            return None
        print(f"    {label}: {len(text)} chars")
        return text[:max_chars]

    except Exception as e:
        print(f"    {label} error: {e}")
        return None


def scrape_9to5mac(query):
    """Search 9to5Mac and scrape the first matching article."""
    try:
        search_url = f"https://9to5mac.com/?s={query.replace(' ', '+')}"
        r = requests.get(search_url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "lxml")

        # Find first article link from search results
        article_link = None
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "9to5mac.com/202" in href and "review" in href.lower():
                article_link = href
                break
        if not article_link:
            # fallback: first article in results
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "9to5mac.com/202" in href:
                    article_link = href
                    break

        if not article_link:
            print(f"    9to5Mac: no article found for '{query}'")
            return None

        print(f"    9to5Mac: found {article_link}")
        time.sleep(1.5)
        return scrape_page(article_link, "9to5Mac article", max_chars=3500)

    except Exception as e:
        print(f"    9to5Mac search error: {e}")
        return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Electronics Review Scraper")
    print("  Sources: Apple.com + 9to5Mac + MacRumors")
    print("=" * 60)

    for product in PRODUCTS:
        code = product["code"]
        name = product["name"]
        out_path = os.path.join(OUTPUT_DIR, f"{code}_reviews.txt")

        print(f"\n{'─'*60}")
        print(f"  {code}: {name}")
        print(f"{'─'*60}")

        sections = [f"PRODUCT: {name} ({code})\n{'='*50}\n"]

        # 1. Apple.com official page
        print(f"  Apple.com...")
        apple_text = scrape_page(product["apple_url"], "Apple.com",
                                 text_tags=("p", "li", "h2", "h3"), max_chars=3000)
        if apple_text:
            sections.append(f"── APPLE.COM (official) ──\n{apple_text}\n")
        time.sleep(1.5)

        # 2. 9to5Mac review
        print(f"  9to5Mac...")
        mac_text = scrape_9to5mac(product["ninemac_query"])
        if mac_text:
            sections.append(f"\n── 9TO5MAC REVIEW ──\n{mac_text}\n")
        time.sleep(1.5)

        # 3. MacRumors buyer's guide
        print(f"  MacRumors...")
        mr_text = scrape_page(product["macrumors_url"], "MacRumors",
                              text_tags=("p", "li"), max_chars=2500)
        if mr_text:
            sections.append(f"\n── MACRUMORS GUIDE ──\n{mr_text}\n")
        time.sleep(1.5)

        full_text = "\n".join(sections)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(full_text)

        word_count = len(full_text.split())
        print(f"  Saved → {out_path} ({word_count} words)")

    print(f"\n{'='*60}")
    print(f"  Done. Files saved to {OUTPUT_DIR}/")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
