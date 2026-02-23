import importlib
import os
import unittest


class TestIntEnv(unittest.TestCase):
    def _load_bot(self):
        os.environ.setdefault("DISCORD_TOKEN", "test-token")
        import bot

        return importlib.reload(bot)

    def test_int_env_returns_default_for_missing(self):
        bot = self._load_bot()
        os.environ.pop("TEST_INT", None)
        self.assertEqual(bot._int_env("TEST_INT", 42), 42)

    def test_int_env_returns_default_for_empty_or_invalid(self):
        bot = self._load_bot()

        os.environ["TEST_INT"] = "   "
        self.assertEqual(bot._int_env("TEST_INT", 7), 7)

        os.environ["TEST_INT"] = "not-a-number"
        self.assertEqual(bot._int_env("TEST_INT", 7), 7)

    def test_int_env_parses_integer_values(self):
        bot = self._load_bot()

        os.environ["TEST_INT"] = "123"
        self.assertEqual(bot._int_env("TEST_INT", 0), 123)


if __name__ == "__main__":
    unittest.main()
