import unittest

import pandas as pd

from geoquerybench.navigation_reporting import (
    build_balanced_assignment_plan,
    calculate_agreement_metrics,
    create_export,
    next_unreviewed_question,
)


class NavigationReportingTests(unittest.TestCase):
    def test_assignment_plan_covers_all_questions_and_balances_primaries(self):
        qids = [f"Q-{number:03d}" for number in range(1, 24)]
        members = ["A", "B", "C", "D", "E"]
        plan, settings = build_balanced_assignment_plan(qids, members, 10, 2)
        self.assertEqual(set(plan), set(qids))
        self.assertEqual(set(settings), set(qids))
        primary_counts = {
            member: sum(reviewers[0] == member for reviewers in plan.values())
            for member in members
        }
        self.assertLessEqual(max(primary_counts.values()) - min(primary_counts.values()), 1)

    def test_next_unreviewed_wraps_and_skips_completed_items(self):
        options = ["Q1", "Q2", "Q3"]
        self.assertEqual(next_unreviewed_question("Q2", options, {"Q3"}), "Q1")
        self.assertEqual(next_unreviewed_question("Q2", options, {"Q1", "Q3"}), "Q2")

    def test_agreement_metrics(self):
        completed = pd.DataFrame(
            {
                "qid": ["Q1", "Q1", "Q2", "Q2"],
                "reviewer": ["A", "B", "A", "B"],
                "verdict": ["Pass", "Pass", "Pass", "Fail"],
            }
        )
        metrics = calculate_agreement_metrics(completed)
        self.assertEqual(metrics["pair_count"], 2)
        self.assertEqual(metrics["exact_agreement"], 0.5)

    def test_export_preserves_question_and_reviewer_fields(self):
        questions = pd.DataFrame(
            [{
                "qid": "Q1", "scenario": "Near surface", "qtype": "SQL",
                "qtype_name": "SQL", "task": "sql", "difficulty": "easy",
                "question_en": "Question", "question_zh": "问题",
                "gold_code": "SELECT 1", "notes": "", "rewrite_source": "",
                "expected_output": "one row",
            }]
        )
        reviews = pd.DataFrame([{"qid": "Q1", "reviewer": "Thomas", "verdict": "Pass"}])
        empty = pd.DataFrame()
        result = create_export(questions, reviews, empty, empty, empty)
        self.assertEqual(result.iloc[0]["question_en"], "Question")
        self.assertEqual(result.iloc[0]["reviewer"], "Thomas")


if __name__ == "__main__":
    unittest.main()
