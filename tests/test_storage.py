import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from geoquerybench import storage


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.patchers = [
            patch.object(storage, "STORAGE_DIRECTORY", root),
            patch.object(storage, "DATABASE_FILE", root / "annotations.db"),
            patch.object(storage, "BACKUP_DIRECTORY", root / "backups"),
            patch.object(storage, "PERSISTENT_STORAGE", False),
        ]
        for patcher in self.patchers:
            patcher.start()
        storage.initialize_database()

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp_dir.cleanup()

    @staticmethod
    def review_values(verdict="Pass"):
        return {
            "candidate_output": "143 rows",
            "result_evidence": "Runtime output checked",
            "rewrite_applicable": False,
            "rewritten_query": "",
            "rewrite_equivalence": "Not assessed",
            "rewrite_comments": "",
            "translation_quality": "Pass",
            "executability": "Pass",
            "schema_use": "Pass",
            "logic": "Pass",
            "domain_correctness": "Pass",
            "output_compliance": "Pass",
            "verdict": verdict,
            "comments": "Verified independently",
            "needs_clarification": False,
            "review_seconds": 30,
        }

    def test_review_updates_preserve_history(self):
        storage.save_review("NS1-001", "Ziyue Xu", self.review_values(), None)
        storage.save_review("NS1-001", "Ziyue Xu", self.review_values("Fail"), None)
        current = storage.load_reviews()
        history = storage.load_history()
        self.assertEqual(len(current), 1)
        self.assertEqual(current.iloc[0]["verdict"], "Fail")
        self.assertEqual(len(history), 2)
        self.assertEqual(history["version"].tolist(), [2, 1])

    def test_storage_diagnostics_and_backup(self):
        diagnostics = storage.storage_diagnostics()
        self.assertTrue(diagnostics["writable"])
        self.assertTrue(diagnostics["database_exists"])
        backup = storage.backup_database()
        self.assertTrue(backup.exists())


if __name__ == "__main__":
    unittest.main()
