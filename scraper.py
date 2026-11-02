import requests
from bs4 import BeautifulSoup
import re
import json

SEARCH_URL = "https://www.ontario.ca/search/ontario-gazette"
BASE_DOMAIN = "https://www.ontario.ca"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

def get_latest_gazette_issue_url():
    """Dynamically locates the URL of the most recent Ontario Gazette issue."""
    print("Searching for latest Ontario Gazette issue...")
    resp = requests.get(SEARCH_URL, headers=HEADERS)
    if resp.status_code != 200:
        print(f"Failed to load search page. Status code: {resp.status_code}")
        return None

    soup = BeautifulSoup(resp.content, 'html.parser')
    # Locate links matching /document/ontario-gazette-volume-...
    for link in soup.find_all('a', href=True):
        href = link['href']
        if '/document/ontario-gazette-volume-' in href:
            full_url = href if href.startswith('http') else BASE_DOMAIN + href
            # Append the dedicated tax sale section slug if not present
            if not full_url.endswith('/sale-land-tax-arrears-public-tender'):
                full_url = full_url.rstrip('/') + '/sale-land-tax-arrears-public-tender'
            print(f"Found latest issue tax sale page: {full_url}")
            return full_url

    print("Could not locate a valid issue URL from search page.")
    return None

def scrape_tax_sales():
    issue_url = get_latest_gazette_issue_url()
    if not issue_url:
        return []

    resp = requests.get(issue_url, headers=HEADERS)
    if resp.status_code != 200:
        print(f"Failed to fetch issue page ({issue_url}). Status: {resp.status_code}")
        return []

    soup = BeautifulSoup(resp.content, 'html.parser')
    listings = []

    # Find tax tender content blocks
    tender_blocks = soup.find_all(['div', 'section', 'article'])

    for block in tender_blocks:
        text = block.get_text()
        if "SALE OF LAND BY PUBLIC TENDER" in text or "Municipal Act, 2001" in text:
            pin_match = re.search(r'PIN\s*#?\s*([\d-]+)', text, re.IGNORECASE)
            bid_match = re.search(r'Minimum\s+Tender\s+Amount:\s*\$([\d,]+\.\d{2})', text, re.IGNORECASE)
            roll_match = re.search(r'Roll\s*#?\s*([\d\s-]+)', text, re.IGNORECASE)

            if bid_match or pin_match:
                listing = {
                    "pin": pin_match.group(1) if pin_match else "N/A",
                    "roll": roll_match.group(1).strip() if roll_match else "N/A",
                    "minBid": float(bid_match.group(1).replace(',', '')) if bid_match else 0.0,
                    "noticeUrl": issue_url,
                    "pdfUrl": "https://forms.mgcs.gov.on.ca/dataset/402ef9c5-2da6-4880-98be-e2e897627bcd/resource/31f730ca-c641-4645-8473-9ddd90bea745/download/2205e.pdf",
                    "description": text[:200].strip().replace('\n', ' ')
                }
                listings.append(listing)

    return listings

if __name__ == "__main__":
    results = scrape_tax_sales()
    print(f"Successfully scraped {len(results)} tax sale listings.")
    with open("listings.json", "w") as f:
        json.dump(results, f, indent=2)