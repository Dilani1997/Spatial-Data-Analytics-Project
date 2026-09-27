import tempfile
import unittest
from pathlib import Path

import pandas as pd

from geoquerybench.data_loader import (
    expanded_dataset_diagnostics,
    expected_result_file,
    load_expanded_questions,
    load_gold_manifest,
)


class ExpandedDataLoaderTests(unittest.TestCase):
    def test_aliases_and_bilingual_requirement(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "questions.csv"
            pd.DataFrame([
                {"id": "Q1", "english_question": "Gold?", "question_cn": "黄金？", "gold_query": "SELECT 1"}
            ]).to_csv(path, index=False)
            frame = load_expanded_questions(path)
            self.assertEqual(frame.loc[0, "qid"], "Q1")
            self.assertEqual(expanded_dataset_diagnostics(frame)["rows"], 1)

    def test_manifest_resolution_blocks_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Q1.csv").write_text("x\n1\n", encoding="utf-8")
            pd.DataFrame([
                {"qid": "Q1", "filename": "Q1.csv"},
                {"qid": "Q2", "filename": "../secret.csv"},
            ]).to_csv(root / "_manifest.csv", index=False)
            manifest = load_gold_manifest(root)
            self.assertEqual(expected_result_file("Q1", root, manifest).name, "Q1.csv")
            self.assertIsNone(expected_result_file("Q2", root, manifest))


if __name__ == "__main__":
    unittest.main()
