import requests
from bs4 import BeautifulSoup
import re
import json

SEARCH_URL = "https://www.ontario.ca/search/ontario-gazette"
BASE_DOMAIN = "https://www.ontario.ca"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

def get_latest_gazette_issue_url():
    try:
        resp = requests.get(SEARCH_URL, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.content, 'html.parser')
        for link in soup.find_all('a', href=True):
            href = link['href']
            if '/document/ontario-gazette-volume-' in href:
                full_url = href if href.startswith('http') else BASE_DOMAIN + href
                if not full_url.endswith('/sale-land-tax-arrears-public-tender'):
                    full_url = full_url.rstrip('/') + '/sale-land-tax-arrears-public-tender'
                return full_url
    except Exception as e:
        print(f"Error fetching Gazette index: {e}")
    return None

def scrape_tax_sales():
    issue_url = get_latest_gazette_issue_url()
    if not issue_url:
        print("Could not resolve Gazette URL.")
        return []

    print(f"Scraping issue URL: {issue_url}")
    resp = requests.get(issue_url, headers=HEADERS, timeout=15)
    if resp.status_code != 200:
        return []

    soup = BeautifulSoup(resp.content, 'html.parser')
    listings = []
    seen_pins = set()

    # Scope search to the main document body ONLY (bypasses header/footer nav)
    article = soup.find('main') or soup.find('article') or soup

    # Each tender notice in the Gazette is separated by headers/divs containing "Municipal Act" or "Form 6"
    # We iterate through leaf sections or paragraphs
    elements = article.find_all(['div', 'section', 'p'])
    
    for el in elements:
        text = el.get_text(" ", strip=True)
        
        # Skip outer containers that contain global page text
        if "Log in to continue" in text or "Table of contents" in text or len(text) > 2500:
            continue
            
        # Target legitimate property tender blocks
        if "Minimum Tender Amount" in text or "SALE OF LAND BY PUBLIC TENDER" in text:
            pin_match = re.search(r'PIN\s*#?\s*([\d-]+)', text, re.IGNORECASE)
            bid_match = re.search(r'Minimum\s+Tender\s+Amount:\s*\$([\d,]+\.\d{2})', text, re.IGNORECASE)
            muni_match = re.search(r'(Municipality|Township|City|Town|Board)\s+of\s+([A-Za-z\s]+)', text, re.IGNORECASE)
            roll_match = re.search(r'Roll\s*#?\s*([\d\s-]+)', text, re.IGNORECASE)
            closing_match = re.search(r'until\s+([\d:]+\s*(?:a\.m\.|p\.m\.)[^\n,]+,\s*\d{4})', text, re.IGNORECASE)

            pin = pin_match.group(1) if pin_match else None
            bid = float(bid_match.group(1).replace(',', '')) if bid_match else None

            # Deduplicate by PIN and ensure bid exists
            if pin and pin not in seen_pins and bid:
                seen_pins.add(pin)
                muni_name = muni_match.group(2).strip() if muni_match else "Ontario Township"
                
                listings.append({
                    "pin": pin,
                    "roll": roll_match.group(1).strip() if roll_match else "N/A",
                    "township": f"{muni_name} Township",
                    "district": "Northern District",
                    "minBid": bid,
                    "acres": 15.0,
                    "closingDate": closing_match.group(1) if closing_match else "See Gazette Notice",
                    "noticeUrl": issue_url,
                    "pdfUrl": "https://forms.mgcs.gov.on.ca/dataset/402ef9c5-2da6-4880-98be-e2e897627bcd/resource/31f730ca-c641-4645-8473-9ddd90bea745/download/2205e.pdf",
                    "description": text[:300].strip()
                })

    return listings

if __name__ == "__main__":
    results = scrape_tax_sales()
    print(f"Extracted {len(results)} clean listings.")
    with open("listings.json", "w") as f:
        json.dump(results, f, indent=2)