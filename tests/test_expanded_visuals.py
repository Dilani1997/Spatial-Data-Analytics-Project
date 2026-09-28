import unittest

from geoquerybench.visuals import validate_result_blob


class ExpandedVisualSafetyTests(unittest.TestCase):
    def test_accepts_supported_nonempty_file(self):
        self.assertEqual(validate_result_blob("result.csv", b"x\n1\n"), ".csv")

    def test_rejects_unsupported_empty_and_large(self):
        with self.assertRaises(ValueError):
            validate_result_blob("result.exe", b"x")
        with self.assertRaises(ValueError):
            validate_result_blob("result.csv", b"")
        with self.assertRaises(ValueError):
            validate_result_blob("result.csv", b"1234", maximum_bytes=3)


if __name__ == "__main__":
    unittest.main()
