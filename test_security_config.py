import os
import unittest
from unittest.mock import patch

from geoquerybench.config import APP_VERSION, TEAM_MEMBERS
from geoquerybench.security import require_access


class SecurityConfigTests(unittest.TestCase):
    def test_expected_team_and_version_are_configured(self):
        self.assertEqual(APP_VERSION, "1.2.0")
        self.assertEqual(len(TEAM_MEMBERS), 5)
        self.assertIn("Chaitanya Neerukattu", TEAM_MEMBERS)

    def test_no_password_uses_local_demo_mode(self):
        with patch.dict(os.environ, {"GQB_APP_PASSWORD": ""}, clear=False):
            self.assertEqual(require_access(), "Local demo mode")


if __name__ == "__main__":
    unittest.main()
