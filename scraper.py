import requests
from bs4 import BeautifulSoup
import re
import json

SEARCH_URL = "https://www.ontario.ca/search/ontario-gazette"
BASE_DOMAIN = "https://www.ontario.ca"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

def get_latest_gazette_issue_url():
    resp = requests.get(SEARCH_URL, headers=HEADERS)
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
    return None

def scrape_tax_sales():
    issue_url = get_latest_gazette_issue_url()
    if not issue_url:
        return []

    resp = requests.get(issue_url, headers=HEADERS)
    if resp.status_code != 200:
        return []

    soup = BeautifulSoup(resp.content, 'html.parser')
    listings = []
    seen_pins = set()

    # Locate main article content to avoid header/footer nav
    content_area = soup.find('main') or soup.find('article') or soup

    # Look for property tender notices
    blocks = content_area.find_all(['p', 'div', 'tr'])

    for block in blocks:
        text = block.get_text(" ", strip=True)
        
        # Must contain tender indicators
        if "Minimum Tender Amount" in text or "SALE OF LAND" in text:
            pin_match = re.search(r'PIN\s*#?\s*([\d-]+)', text, re.IGNORECASE)
            bid_match = re.search(r'Minimum\s+Tender\s+Amount:\s*\$([\d,]+\.\d{2})', text, re.IGNORECASE)
            township_match = re.search(r'(Municipality|Township|City|Board)\s+of\s+([A-Za-z\s]+)', text, re.IGNORECASE)
            closing_match = re.search(r'until\s+([\d:]+\s*(?:a\.m\.|p\.m\.)[^\n,]+,\s*\d{4})', text, re.IGNORECASE)

            pin = pin_match.group(1) if pin_match else None
            
            # Filter duplicates and non-listing blocks
            if pin and pin not in seen_pins and bid_match:
                seen_pins.add(pin)
                listings.append({
                    "pin": pin,
                    "township": township_match.group(2).strip() if township_match else "Ontario Township",
                    "district": "Northern District",
                    "minBid": float(bid_match.group(1).replace(',', '')),
                    "acres": 15.0,
                    "closingDate": closing_match.group(1) if closing_match else "See Official Notice",
                    "noticeUrl": issue_url,
                    "pdfUrl": "https://forms.mgcs.gov.on.ca/dataset/402ef9c5-2da6-4880-98be-e2e897627bcd/resource/31f730ca-c641-4645-8473-9ddd90bea745/download/2205e.pdf",
                    "description": text[:250].strip()
                })

    return listings

if __name__ == "__main__":
    data = scrape_tax_sales()
    print(f"Scraped {len(data)} clean property listings.")
    with open("listings.json", "w") as f:
        json.dump(data, f, indent=2)