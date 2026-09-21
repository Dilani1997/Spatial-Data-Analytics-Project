import unittest

import pandas as pd

from geoquerybench.data_loader import dataset_diagnostics, normalize_questions


class DataLoaderTests(unittest.TestCase):
    def valid_frame(self):
        return pd.DataFrame(
            {
                "qid": ["NS1-001", "NS1-002"],
                "question_en": ["Find gold samples", "Find copper samples"],
                "question_zh": ["查找金样本", "查找铜样本"],
                "gold_code": ["SELECT 1", "SELECT 2"],
            }
        )

    def test_normalization_preserves_bilingual_questions(self):
        result = normalize_questions(self.valid_frame())
        self.assertEqual(result["qid"].tolist(), ["NS1-001", "NS1-002"])
        self.assertTrue(result["question_en"].str.len().gt(0).all())
        self.assertTrue(result["question_zh"].str.len().gt(0).all())
        self.assertIn("commodity_tags", result.columns)

    def test_duplicate_qids_are_rejected(self):
        frame = self.valid_frame()
        frame.loc[1, "qid"] = "NS1-001"
        with self.assertRaisesRegex(ValueError, "Duplicate question IDs"):
            normalize_questions(frame)

    def test_rows_without_either_language_are_rejected(self):
        frame = self.valid_frame()
        frame.loc[0, ["question_en", "question_zh"]] = ""
        with self.assertRaisesRegex(ValueError, "neither English nor Chinese"):
            normalize_questions(frame)

    def test_diagnostics_report_expected_counts(self):
        result = normalize_questions(self.valid_frame())
        diagnostics = dataset_diagnostics(result)
        self.assertEqual(diagnostics["rows"], 2)
        self.assertEqual(diagnostics["duplicate_ids"], 0)
        self.assertEqual(diagnostics["bilingual_complete"], 2)


if __name__ == "__main__":
    unittest.main()
