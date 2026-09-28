import tempfile
import unittest
from pathlib import Path

from geoquerybench.storage import (
    assign_unassigned_evenly,
    expanded_evidence_path,
    load_expanded_assignments,
    load_expanded_reviews,
    persist_expanded_evidence,
    save_expanded_review,
)


class ExpandedStorageTests(unittest.TestCase):
    def test_save_review_and_content_addressed_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "reviews.sqlite3"
            name, digest, path = persist_expanded_evidence("out.csv", b"a\n1\n", database_file=db)
            self.assertTrue(path.is_file())
            self.assertEqual(expanded_evidence_path(digest, name, database_file=db), path)
            save_expanded_review("Q1", "A", "Fail", "different", name, digest, database_file=db)
            reviews = load_expanded_reviews(db)
            self.assertEqual(reviews.loc[0, "verdict"], "Fail")

    def test_even_assignment_preserves_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "reviews.sqlite3"
            added = assign_unassigned_evenly(["Q1", "Q2", "Q3"], ["A", "B"], database_file=db)
            self.assertEqual(added, 3)
            assignments = load_expanded_assignments(db)
            self.assertEqual(set(assignments), {"Q1", "Q2", "Q3"})
            self.assertLessEqual(abs(list(assignments.values()).count("A") - list(assignments.values()).count("B")), 1)
            self.assertEqual(assign_unassigned_evenly(["Q1", "Q2", "Q3"], ["A", "B"], database_file=db), 0)


if __name__ == "__main__":
    unittest.main()
