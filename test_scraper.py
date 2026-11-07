import unittest

from scraper import (
    extract_assessed_value,
    extract_property_address,
    normalize_parcel_geometry,
)


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
