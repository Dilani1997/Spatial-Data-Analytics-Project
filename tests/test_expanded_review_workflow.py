import unittest

from geoquerybench.review_workflow import (
    EXPANDED_VERDICTS,
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


if __name__ == "__main__":
    unittest.main()