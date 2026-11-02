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
            print(f"Failed to fetch search page: {resp.status_code}")
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
        print(f"Error resolving Gazette URL: {e}")
    return None

def scrape_tax_sales():
    issue_url = get_latest_gazette_issue_url()
    if not issue_url:
        print("Could not resolve latest Gazette URL.")
        return []

    print(f"Fetching Gazette page: {issue_url}")
    resp = requests.get(issue_url, headers=HEADERS, timeout=15)
    if resp.status_code != 200:
        print(f"Failed page fetch with status: {resp.status_code}")
        return []

    soup = BeautifulSoup(resp.content, 'html.parser')
    
    # Extract clean text from the main body, discarding top site headers/footers
    main_area = soup.find('main') or soup.find('article') or soup.body
    full_text = main_area.get_text(" ", strip=True)

    # Split the document by legal notice headers
    chunks = re.split(r'(?=SALE OF LAND BY PUBLIC TENDER|Form 6|Municipal Act, 2001)', full_text, flags=re.IGNORECASE)

    listings = []
    seen_pins = set()

    for chunk in chunks:
        # Require a Minimum Tender Amount in the text block
        if "Minimum Tender Amount" in chunk:
            pin_match = re.search(r'PIN\s*#?\s*([\d-]+)', chunk, re.IGNORECASE)
            bid_match = re.search(r'Minimum\s+Tender\s+Amount:\s*\$([\d,]+\.\d{2})', chunk, re.IGNORECASE)
            muni_match = re.search(r'(Municipality|Township|City|Town|Board)\s+of\s+([A-Za-z\s]+)', chunk, re.IGNORECASE)
            roll_match = re.search(r'Roll\s*#?\s*([\d\s-]+)', chunk, re.IGNORECASE)
            closing_match = re.search(r'until\s+([\d:]+\s*(?:a\.m\.|p\.m\.)[^\n,]+,\s*\d{4})', chunk, re.IGNORECASE)

            pin = pin_match.group(1) if pin_match else None
            bid = float(bid_match.group(1).replace(',', '')) if bid_match else None

            # Deduplicate by PIN
            if pin and pin not in seen_pins and bid:
                seen_pins.add(pin)
                muni_name = muni_match.group(2).strip() if muni_match else "Ontario Municipality"
                
                clean_desc = re.sub(r'\s+', ' ', chunk).strip()
                if len(clean_desc) > 300:
                    clean_desc = clean_desc[:300] + "..."

                listings.append({
                    "pin": pin,
                    "roll": roll_match.group(1).strip() if roll_match else "N/A",
                    "township": muni_name,
                    "district": "Ontario District",
                    "minBid": bid,
                    "acres": 15.0,
                    "closingDate": closing_match.group(1) if closing_match else "See Official Notice",
                    "noticeUrl": issue_url,
                    "pdfUrl": "https://forms.mgcs.gov.on.ca/dataset/402ef9c5-2da6-4880-98be-e2e897627bcd/resource/31f730ca-c641-4645-8473-9ddd90bea745/download/2205e.pdf",
                    "description": clean_desc
                })

    return listings

if __name__ == "__main__":
    results = scrape_tax_sales()
    print(f"Successfully extracted {len(results)} clean listings.")
    with open("listings.json", "w") as f:
        json.dump(results, f, indent=2)