import unittest
from datetime import date
from unittest.mock import Mock, patch

from scraper import (
    extract_assessed_value,
    extract_property_address,
    extract_tender_closing_date,
    get_gazette_issue_urls,
    is_tender_active,
    normalize_parcel_geometry,
    scrape_tax_sales,
)


class GazetteIssueTests(unittest.TestCase):
    def test_discovers_distinct_issue_urls_from_search_results(self):
        response = Mock(content=b"""
            <a href="/document/ontario-gazette-volume-159-issue-45-november-7-2026">
              Gazette issue 45
            </a>
            <a href="/document/ontario-gazette-volume-159-issue-45-november-7-2026/sale-land-tax-arrears-public-tender">
              Tender notice
            </a>
            <a href="/document/ontario-gazette-volume-159-issue-44-october-31-2026">
              Gazette issue 44
            </a>
        """, raise_for_status=Mock())

        with patch("scraper.requests.get", return_value=response):
            issue_urls = get_gazette_issue_urls()

        self.assertEqual(issue_urls, [
            "https://www.ontario.ca/document/ontario-gazette-volume-159-issue-45-november-7-2026/sale-land-tax-arrears-public-tender",
            "https://www.ontario.ca/document/ontario-gazette-volume-159-issue-44-october-31-2026/sale-land-tax-arrears-public-tender",
        ])

    def test_keeps_tenders_closing_today_or_later(self):
        today = date(2026, 11, 6)

        self.assertTrue(is_tender_active("3:00 p.m. local time on November 6, 2026", today))
        self.assertTrue(is_tender_active("3:00 p.m. local time on November 25, 2026", today))
        self.assertFalse(is_tender_active("3:00 p.m. local time on November 5, 2026", today))
        self.assertFalse(is_tender_active("See Official Notice", today))

    def test_extracts_deadline_with_inconsistent_time_punctuation(self):
        self.assertEqual(
            extract_tender_closing_date(
                "Tenders will be received until 3:00 p.m local time on Tuesday November 25, 2026."
            ),
            "3:00 p.m local time on Tuesday November 25, 2026",
        )

    def test_scrapes_active_listings_across_multiple_issues(self):
        search_response = Mock(content=b"""
            <a href="/document/ontario-gazette-volume-159-issue-45-november-7-2026">Issue 45</a>
            <a href="/document/ontario-gazette-volume-159-issue-44-october-31-2026">Issue 44</a>
            <a href="/document/ontario-gazette-volume-159-issue-43-october-24-2026">Issue 43</a>
            <a href="/document/ontario-gazette-volume-159-issue-42-october-17-2026">Issue 42</a>
        """, raise_for_status=Mock())

        def issue_response(pin, deadline):
            return Mock(
                content=f"""
                    <main>
                      SALE OF LAND BY PUBLIC TENDER
                      The Corporation of the Municipality of Test Town
                      Take Notice that tenders are invited and will be received until
                      3:00 p.m. local time on {deadline}
                      Roll No. 12 34; 18 Forest Street; PIN {pin} (LT)
                      Minimum Tender Amount: $1,000.00
                    </main>
                """.encode(),
                raise_for_status=Mock(),
            )

        issue_responses = [
            issue_response("00001-0001", "November 5, 2026"),
            issue_response("00002-0002", "November 6, 2026"),
            issue_response("00003-0003", "November 25, 2026"),
            Mock(
                content=b"""
                    <main>
                      SALE OF LAND BY PUBLIC TENDER
                      The Corporation of the Municipality of Test Town
                      offered for sale by public auction on November 12, 2026
                      PIN 00004-0004 (LT)
                      Minimum Tender Amount: $1,000.00
                    </main>
                """,
                raise_for_status=Mock(),
            ),
        ]
        with patch(
            "scraper.requests.get",
            side_effect=[search_response, *issue_responses],
        ), patch("scraper.get_parcel_data_from_pin", return_value=(45.0, -80.0, None)):
            listings = scrape_tax_sales(today=date(2026, 11, 6))

        self.assertEqual(
            [listing["pin"] for listing in listings],
            ["00002-0002", "00003-0003"],
        )
        self.assertTrue(all("issue-44-" in listing["noticeUrl"] or "issue-43-" in listing["noticeUrl"]
                            for listing in listings))


class ExtractPropertyAddressTests(unittest.TestCase):
    def test_extracts_labeled_municipal_address(self):
        notice = (
            "Municipal Address 1326 Mayer Rd, Noelville, ON, P0M 2N0; "
            "PIN 73446-0001; Property Description PCL 3489 SEC SES"
        )

        self.assertEqual(
            extract_property_address(notice),
            "1326 Mayer Rd, Noelville, ON, P0M 2N0",
        )

    def test_extracts_address_after_roll_number(self):
        notice = (
            "According to the assessment roll, the assessed value is $90,000; "
            "Roll No. 25 18 010.094.55520; 23 Canada Street; "
            "PT LT 10 BLK 3 Range 1 James Mills Survey; PIN # 17140-0320 (LT)"
        )

        self.assertEqual(extract_property_address(notice), "23 Canada Street")

    def test_extracts_address_before_being_pin(self):
        notice = (
            "18 Forest Street, Parry Sound, Ontario P2A 2P9 "
            "being PIN 52116-0094"
        )

        self.assertEqual(
            extract_property_address(notice),
            "18 Forest Street, Parry Sound, Ontario P2A 2P9",
        )

    def test_address_extraction_ignores_tender_office_addresses(self):
        notice = (
            "Tenders will be received until 3:00 p.m. on January 20, 2027 at "
            "The Corporation of the Town of Parry Sound, Town Office, "
            "52 Seguin Street, Parry Sound, Ontario. The tenders will then be "
            "opened at the Town Offices. Description of Land(s): "
            "18 Forest Street, Parry Sound, Ontario P2A 2P9 being PIN 52116-0094"
        )

        self.assertEqual(
            extract_property_address(notice),
            "18 Forest Street, Parry Sound, Ontario P2A 2P9",
        )

    def test_returns_none_when_notice_has_only_legal_description(self):
        notice = "Roll No. 25 18 010.094.55520; PT LT 10 BLK 3; PIN # 17140-0320 (LT)"

        self.assertIsNone(extract_property_address(notice))

    def test_extracts_assessed_land_value(self):
        notice = (
            "According to the last returned assessment roll, the assessed value "
            "of the land is $260,000.00 Minimum Tender Amount: $28,493.25"
        )

        self.assertEqual(extract_assessed_value(notice), 260000.0)

    def test_returns_none_when_assessed_value_is_not_stated(self):
        self.assertIsNone(extract_assessed_value("Minimum Tender Amount: $28,493.25"))

    def test_accepts_valid_esri_parcel_polygon(self):
        geometry = {
            "rings": [[
                [-80.0, 45.0],
                [-79.9, 45.0],
                [-79.9, 45.1],
                [-80.0, 45.0],
            ]]
        }

        self.assertEqual(normalize_parcel_geometry(geometry), {
            "type": "esriGeometryPolygon",
            "rings": geometry["rings"],
        })

    def test_rejects_unclosed_or_out_of_range_rings(self):
        self.assertIsNone(normalize_parcel_geometry({
            "rings": [[[-80.0, 45.0], [-79.9, 45.0], [-79.9, 45.1], [-80.0, 45.1]]]
        }))
        self.assertIsNone(normalize_parcel_geometry({
            "rings": [[[-181.0, 45.0], [-79.9, 45.0], [-79.9, 45.1], [-181.0, 45.0]]]
        }))


if __name__ == "__main__":
    unittest.main()
