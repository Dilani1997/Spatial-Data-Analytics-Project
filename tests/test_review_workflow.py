import unittest

from geoquerybench.review_workflow import option_index, verdict_style, widget_key


class ReviewWorkflowTests(unittest.TestCase):
    def test_option_index_uses_safe_default(self):
        options = ["Not assessed", "Pass", "Fail"]
        self.assertEqual(option_index(options, "Pass"), 1)
        self.assertEqual(option_index(options, "Unknown"), 0)

    def test_verdict_style_maps_pass_and_fail(self):
        self.assertEqual(verdict_style("Pass"), ("correct", "🟢"))
        self.assertEqual(verdict_style("Fail"), ("incorrect", "🔴"))
        self.assertEqual(verdict_style("Not assessed"), ("pending", "⚪"))

    def test_widget_keys_separate_reviewer_names(self):
        key = widget_key("logic", "NS1-001", "Dilani Gunathilaka Mapitigamage")
        self.assertEqual(key, "logic_NS1-001_Dilani_Gunathilaka_Mapitigamage")


if __name__ == "__main__":
    unittest.main()
