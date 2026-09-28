import unittest

from geoquerybench.navigation_reporting import (
    next_pending_assigned,
    resume_pending,
    reviewer_statuses,
    visible_ids,
)


class ExpandedNavigationTests(unittest.TestCase):
    def setUp(self):
        self.ids = ["Q1", "Q2", "Q3", "Q4"]
        self.assignments = {"Q1": "A", "Q2": "A", "Q3": "B", "Q4": "A"}

    def test_next_pending_wraps_and_ignores_other_reviewers(self):
        statuses = {"Q1": "Pass", "Q2": "Needs clarification", "Q4": "Fail"}
        self.assertEqual(next_pending_assigned(self.ids, self.assignments, "A", statuses, "Q1"), "Q2")
        self.assertIsNone(next_pending_assigned(self.ids, self.assignments, "B", {"Q3": "Pass"}, "Q3"))

    def test_filters_and_resume_are_reviewer_specific(self):
        rows = [
            {"qid": "Q1", "reviewer": "A", "verdict": "Pass", "updated_at": "2026-01-01T00:00:00"},
            {"qid": "Q2", "reviewer": "A", "verdict": "Needs clarification", "updated_at": "2026-01-02T00:00:00"},
            {"qid": "Q3", "reviewer": "B", "verdict": "Fail", "updated_at": "2026-01-03T00:00:00"},
        ]
        statuses = reviewer_statuses(rows, "A")
        self.assertEqual(visible_ids(self.ids, statuses, "Pending"), ["Q2", "Q3", "Q4"])
        self.assertEqual(resume_pending(self.ids, self.assignments, "A", statuses, rows), "Q4")


if __name__ == "__main__":
    unittest.main()
