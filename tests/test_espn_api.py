import unittest

import espn_api


class TestCommentaryParsing(unittest.TestCase):
    def test_infer_event_types(self):
        self.assertEqual(
            espn_api._infer_commentary_event_type(
                "Goal! Vancouver Whitecaps FC 1, LA Galaxy 0. Ryan Gauld scores."
            ),
            "Goal",
        )
        self.assertEqual(
            espn_api._infer_commentary_event_type(
                "Substitution, Vancouver Whitecaps FC. Brian White replaces Ali Ahmed."
            ),
            "Substitution",
        )
        self.assertEqual(
            espn_api._infer_commentary_event_type("Yellow card for Mathias Laborda."),
            "Yellow Card",
        )

    def test_extract_names(self):
        names = espn_api._extract_names_from_commentary(
            "Substitution, Vancouver Whitecaps FC. Brian White replaces Ali Ahmed."
        )
        self.assertIn("Brian White", names)
        self.assertIn("Ali Ahmed", names)

    def test_scoreboard_urls_include_nearby_dates(self):
        urls = espn_api._scoreboard_urls()
        self.assertGreaterEqual(len(urls), 4)
        self.assertIn(f"{espn_api.BASE_URL}/scoreboard", urls)
        self.assertTrue(any("dates=" in url for url in urls))


if __name__ == "__main__":
    unittest.main()
