import requests
from bs4 import BeautifulSoup
import re
import json

GAZETTE_URL = "https://www.ontario.ca/document/ontario-gazette"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

def scrape_tax_sales():
    response = requests.get(GAZETTE_URL, headers=HEADERS)
    if response.status_code != 200:
        print(f"Failed to fetch Gazette. Status: {response.status_code}")
        return []

    soup = BeautifulSoup(response.content, 'html.parser')
    listings = []

    # Parse public tender sections
    for block in soup.find_all(['div', 'section', 'article']):
        text = block.get_text()
        if "SALE OF LAND BY PUBLIC TENDER" in text:
            pin_match = re.search(r'PIN\s*#?\s*([\d-]+)', text, re.IGNORECASE)
            bid_match = re.search(r'Minimum\s+Tender\s+Amount:\s*\$([\d,]+\.\d{2})', text, re.IGNORECASE)

            if bid_match:
                listings.append({
                    "pin": pin_match.group(1) if pin_match else "N/A",
                    "minBid": float(bid_match.group(1).replace(',', '')),
                    "noticeUrl": GAZETTE_URL,
                    "pdfUrl": "https://forms.mgcs.gov.on.ca/dataset/402ef9c5-2da6-4880-98be-e2e897627bcd/resource/31f730ca-c641-4645-8473-9ddd90bea745/download/2205e.pdf",
                    "description": text[:200].strip()
                })

    return listings

if __name__ == "__main__":
    data = scrape_tax_sales()
    # Save output to listings.json
    with open("listings.json", "w") as f:
        json.dump(data, f, indent=2)
    print(f"Scraped {len(data)} listings into listings.json")