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

    def test_schedule_urls_include_multiple_seasons(self):
        urls = espn_api._schedule_urls()
        self.assertGreaterEqual(len(urls), 4)
        self.assertTrue(any("season=" in url for url in urls))


class TestScheduleAggregation(unittest.IsolatedAsyncioTestCase):
    async def test_get_schedule_merges_seasons_and_sorts(self):
        original_fetch = espn_api._fetch
        original_parse_match = espn_api._parse_match
        original_schedule_urls = espn_api._schedule_urls

        async def fake_fetch(_session, url):
            if "season=2024" in url:
                return {"events": [{"id": "1"}, {"id": "2"}]}
            if "season=2025" in url:
                return {"events": [{"id": "2"}, {"id": "3"}]}
            return {"events": []}

        def fake_parse_match(event):
            mapping = {
                "1": {"id": "1", "date": "2025-01-01T00:00Z"},
                "2": {"id": "2", "date": "2025-01-03T00:00Z"},
                "3": {"id": "3", "date": "2025-01-02T00:00Z"},
            }
            return mapping.get(str(event.get("id")))

        try:
            espn_api._fetch = fake_fetch
            espn_api._parse_match = fake_parse_match
            espn_api._schedule_urls = lambda: ["u?season=2024", "u?season=2025", "u"]
            matches = await espn_api.get_schedule(session=None)
        finally:
            espn_api._fetch = original_fetch
            espn_api._parse_match = original_parse_match
            espn_api._schedule_urls = original_schedule_urls

        self.assertEqual([m["id"] for m in matches], ["1", "3", "2"])


if __name__ == "__main__":
    unittest.main()
