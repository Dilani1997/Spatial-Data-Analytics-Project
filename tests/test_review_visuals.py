import unittest

import pandas as pd

from geoquerybench.review_visuals import (
    commodity_tags,
    coordinate_columns,
    detect_commodities,
    prepare_pie_data,
)


class ReviewVisualHelperTests(unittest.TestCase):
    def test_commodity_detection_avoids_substring_false_positives(self):
        self.assertEqual(detect_commodities("Gold and Cu samples"), ["Gold", "Copper"])
        self.assertNotIn("Iron", detect_commodities("profile"))

    def test_commodity_tags_has_stable_fallback(self):
        self.assertEqual(commodity_tags("lithology only"), "Other / non-commodity")

    def test_coordinate_columns_detects_common_names(self):
        frame = pd.DataFrame({"lat": [-31.9], "lon": [115.8], "value": [1]})
        self.assertEqual(coordinate_columns(frame), ("lat", "lon"))

    def test_pie_data_limits_categories_and_groups_other(self):
        frame = pd.DataFrame({"kind": list("AABBCCDD")})
        result = prepare_pie_data(frame, "kind", maximum_slices=2)
        self.assertEqual(result["Value"].sum(), len(frame))
        self.assertIn("Other", result["Category"].tolist())


if __name__ == "__main__":
    unittest.main()
