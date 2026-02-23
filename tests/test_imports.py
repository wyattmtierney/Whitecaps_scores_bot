import os
import subprocess
import sys
import unittest


class TestModuleImports(unittest.TestCase):
    def test_espn_api_imports_in_clean_process(self):
        result = subprocess.run(
            [sys.executable, "-c", "import espn_api"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_bot_imports_in_clean_process_with_token(self):
        env = os.environ.copy()
        env["DISCORD_TOKEN"] = "test-token"
        result = subprocess.run(
            [sys.executable, "-c", "import bot"],
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)


if __name__ == "__main__":
    unittest.main()
