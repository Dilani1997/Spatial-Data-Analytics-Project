import unittest

from geoquerybench.review_workflow import (
    EXPANDED_VERDICTS,
    evidence_required,
    review_errors,
    upload_visible,
    verdict_is_complete,
)


class ExpandedReviewPolicyTests(unittest.TestCase):
    def test_supported_verdicts(self):
        self.assertEqual(
            EXPANDED_VERDICTS,
            ("Not assessed", "Pass", "Fail", "Needs clarification"),
        )

    def test_pass_and_fail_are_terminal(self):
        for verdict in ("Pass", "Fail"):
            with self.subTest(verdict=verdict):
                self.assertTrue(verdict_is_complete(verdict))

    def test_pending_and_unknown_verdicts_are_not_complete(self):
        for verdict in ("Not assessed", "Needs clarification", "", None, "Unknown"):
            with self.subTest(verdict=verdict):
                self.assertFalse(verdict_is_complete(verdict))

    def test_evidence_required_only_for_fail(self):
        cases = (
            ("Not assessed", False),
            ("Pass", False),
            ("Fail", True),
            ("Needs clarification", False),
            ("Unknown", False),
            (None, False),
        )
        for verdict, expected in cases:
            with self.subTest(verdict=verdict):
                self.assertEqual(evidence_required(verdict), expected)

    def test_upload_visibility_by_verdict(self):
        cases = (
            ("Not assessed", False),
            ("Pass", False),
            ("Fail", True),
            ("Needs clarification", True),
            ("Unknown", False),
            (None, False),
        )
        for verdict, expected in cases:
            with self.subTest(verdict=verdict):
                self.assertEqual(upload_visible(verdict), expected)

    def test_pass_requires_official_result_and_confirmation(self):
        self.assertEqual(
            review_errors("Pass", "", True, False, True),
            [],
        )
        self.assertTrue(
            review_errors("Pass", "", False, False, True)
        )
        self.assertTrue(
            review_errors("Pass", "", True, False, False)
        )

    def test_fail_requires_official_result_upload_and_notes(self):
        self.assertEqual(
            review_errors("Fail", "Returned rows differ.", True, True),
            [],
        )
        self.assertTrue(
            review_errors("Fail", "Returned rows differ.", False, True)
        )
        self.assertTrue(
            review_errors("Fail", "Returned rows differ.", True, False)
        )

        for notes in ("", "   ", None):
            with self.subTest(notes=notes):
                self.assertIn(
                    "Describe the mismatch before saving Fail.",
                    review_errors("Fail", notes, True, True),
                )

    def test_clarification_requires_notes_but_not_upload(self):
        self.assertEqual(
            review_errors(
                "Needs clarification",
                "The official output is missing.",
                False,
                False,
            ),
            [],
        )

        for notes in ("", "   ", None):
            with self.subTest(notes=notes):
                self.assertIn(
                    "Describe what needs clarification.",
                    review_errors(
                        "Needs clarification", notes, False, False
                    ),
                )

    def test_unknown_verdict_is_rejected(self):
        for verdict in ("Unknown", "", None):
            with self.subTest(verdict=verdict):
                self.assertEqual(
                    review_errors(verdict, "", True, True),
                    ["Choose a valid verification decision."],
                )

    def test_not_assessed_can_remain_pending(self):
        self.assertEqual(
            review_errors("Not assessed", "", False, False),
            [],
        )
        self.assertFalse(verdict_is_complete("Not assessed"))


if __name__ == "__main__":
    unittest.main()