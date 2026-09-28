import unittest

from geoquerybench.visuals import validate_result_blob
from geoquerybench.review_visuals import csv_result_diagnostics


class ExpandedVisualSafetyTests(unittest.TestCase):
    def test_accepts_supported_nonempty_file(self):
        self.assertEqual(validate_result_blob("result.csv", b"x\n1\n"), ".csv")

    def test_rejects_unsupported_empty_and_large(self):
        with self.assertRaises(ValueError):
            validate_result_blob("result.exe", b"x")
        with self.assertRaises(ValueError):
            validate_result_blob("result.csv", b"")
        with self.assertRaises(ValueError):
            validate_result_blob("result.csv", b"1234", maximum_bytes=3)

    def test_csv_diagnostics_count_missing_duplicates_sentinels_and_negatives(self):
        csv = (
            "sample_id,assay_ppm,correlation,medium\n"
            "S1,-9999,-0.4,soil\n"
            "S2,12,0,rock\n"
            "S2,12,0,rock\n"
            "S3,,0.2,soil\n"
        ).encode("utf-8")

        result = csv_result_diagnostics(csv)

        self.assertEqual(result["rows"], 4)
        self.assertEqual(result["missing_cells"], 1)
        self.assertEqual(result["duplicate_rows"], 1)
        self.assertEqual(
            result["numeric_columns"]["assay_ppm"],
            {"sentinel_count": 1, "negative_count": 1, "other_negative_count": 0},
        )
        self.assertEqual(
            result["numeric_columns"]["correlation"],
            {"sentinel_count": 0, "negative_count": 1, "other_negative_count": 1},
        )


    def test_csv_diagnostics_scan_rows_beyond_preview_limit(self):
        csv = ("value\n" + "1\n" * 5000 + "-9999\n").encode("utf-8")

        result = csv_result_diagnostics(csv)

        self.assertEqual(result["rows"], 5001)
        self.assertEqual(result["numeric_columns"]["value"]["sentinel_count"], 1)


if __name__ == "__main__":
    unittest.main()
