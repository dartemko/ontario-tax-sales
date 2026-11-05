import requests
from bs4 import BeautifulSoup
import re
import json
import math
import os

SEARCH_URL = "https://www.ontario.ca/search/ontario-gazette"
BASE_DOMAIN = "https://www.ontario.ca"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
LIO_PARCEL_QUERY_URL = os.environ.get("LIO_PARCEL_QUERY_URL")
LIO_PARCEL_PIN_FIELD = os.environ.get("LIO_PARCEL_PIN_FIELD") or "PIN"
if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", LIO_PARCEL_PIN_FIELD):
    raise ValueError("LIO_PARCEL_PIN_FIELD must be a simple field name.")


def normalize_parcel_geometry(geometry):
    if not isinstance(geometry, dict):
        return None

    rings = geometry.get("rings")
    if not isinstance(rings, list) or not rings:
        return None

    for ring in rings:
        if not isinstance(ring, list) or len(ring) < 4:
            return None
        for point in ring:
            if (
                not isinstance(point, list)
                or len(point) < 2
                or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in point[:2])
                or not -180 <= point[0] <= 180
                or not -90 <= point[1] <= 90
            ):
                return None
        if ring[0][:2] != ring[-1][:2]:
            return None

    return {"type": "esriGeometryPolygon", "rings": rings}

def get_parcel_data_from_pin(pin, township):
    geometry = None
    coordinates = None
    if LIO_PARCEL_QUERY_URL:
        try:
            safe_pin = pin.replace("'", "''")
            response = requests.get(
                LIO_PARCEL_QUERY_URL,
                params={
                    "where": f"{LIO_PARCEL_PIN_FIELD} = '{safe_pin}'",
                    "outFields": LIO_PARCEL_PIN_FIELD,
                    "returnGeometry": "true",
                    "returnCentroid": "true",
                    "outSR": "4326",
                    "f": "json",
                },
                headers=HEADERS,
                timeout=15,
            )
            response.raise_for_status()
            result = response.json()
            if "error" in result:
                raise ValueError(result["error"])
            features = result.get("features", [])
            if features:
                parcel_geometry = features[0].get("geometry")
                geometry = normalize_parcel_geometry(parcel_geometry)
                point = parcel_geometry.get("centroid", {}) if isinstance(parcel_geometry, dict) else {}
                if "x" in point and "y" in point:
                    coordinates = (float(point["y"]), float(point["x"]))
            else:
                print(f"No parcel geometry found for PIN {pin}.")
        except (requests.RequestException, ValueError, TypeError, KeyError) as error:
            print(f"Parcel lookup failed for PIN {pin}: {error}")

    if coordinates is None:
        try:
            response = requests.get(
                "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates",
                params={
                    "SingleLine": f"{township}, Ontario, Canada",
                    "f": "json",
                    "outFields": "*",
                    "maxLocations": 1,
                },
                headers=HEADERS,
                timeout=15,
            )
            response.raise_for_status()
            candidates = response.json().get("candidates", [])
            if candidates:
                location = candidates[0]["location"]
                coordinates = (float(location["y"]), float(location["x"]))
        except (requests.RequestException, ValueError, TypeError, KeyError) as error:
            print(f"Township coordinate lookup failed for {township}: {error}")

    lat, lng = coordinates if coordinates else (None, None)
    return lat, lng, geometry

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

def extract_property_address(text):
    municipal_match = re.search(
        r'\bMunicipal\s+Address\s*:?\s*(.+?)(?=\s*;\s*(?:PIN\b|Property\s+Description\b|Roll\b)|$)',
        text,
        re.IGNORECASE,
    )
    if municipal_match:
        return re.sub(r'\s+', ' ', municipal_match.group(1)).strip(' ;,')

    roll_address_match = re.search(
        r'\bRoll\s*(?:(?:No\.?|number|#)\s*)?\d[\d\s.-]*;\s*([^;]+)',
        text,
        re.IGNORECASE,
    )
    if not roll_address_match:
        return None

    address = re.sub(r'\s+', ' ', roll_address_match.group(1)).strip(' ;,')
    street_type = (
        r'(?:street|st\.?|road|rd\.?|avenue|ave\.?|boulevard|blvd\.?|drive|dr\.?|'
        r'lane|ln\.?|court|ct\.?|crescent|cres\.?|circle|cir\.?|highway|hwy\.?|'
        r'trail|trl\.?|way|parkway|pkwy\.?|place|pl\.?|terrace|terr\.?)'
    )
    if re.match(rf'^\d+[A-Za-z]?(?:-\d+[A-Za-z]?)?\s+.+\b{street_type}\b', address, re.IGNORECASE):
        return address
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
        bid_matches = list(re.finditer(
            r'Minimum\s+Tender\s+Amount\s*:?\s*\$([\d,]+\.\d{2})',
            chunk,
            re.IGNORECASE,
        ))
        previous_bid_end = 0
        muni_match = re.search(r'(Municipality|Township|City|Town|Board)\s+of\s+([A-Za-z\s]+)', chunk, re.IGNORECASE)
        closing_match = re.search(r'until\s+([\d:]+\s*(?:a\.m\.|p\.m\.)[^\n,]+,\s*\d{4})', chunk, re.IGNORECASE)

        for bid_match in bid_matches:
            listing_text = chunk[previous_bid_end:bid_match.end()]
            previous_bid_end = bid_match.end()
            pin_match = re.search(r'PIN\s*#?\s*([\d-]+)', listing_text, re.IGNORECASE)
            roll_match = re.search(
                r'Roll\s*(?:(?:#|No\.?|number)\s*)?(\d[\d\s.-]*)',
                listing_text,
                re.IGNORECASE,
            )
            pin = pin_match.group(1) if pin_match else None
            bid = float(bid_match.group(1).replace(',', ''))

            if not pin or pin in seen_pins:
                continue

            seen_pins.add(pin)
            muni_name = muni_match.group(2).strip() if muni_match else "Ontario Municipality"
            muni_name = re.split(r"\s+Take Notice\b", muni_name, maxsplit=1, flags=re.IGNORECASE)[0].strip()
            lat, lng, geometry = get_parcel_data_from_pin(pin, muni_name)

            clean_desc = re.sub(r'\s+', ' ', listing_text).strip()
            if len(clean_desc) > 300:
                clean_desc = clean_desc[:300] + "..."

            listings.append({
                "pin": pin,
                "address": extract_property_address(listing_text),
                "geometry": geometry,
                "lat": lat,
                "lng": lng,
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