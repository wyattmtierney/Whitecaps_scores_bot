import unittest

import aiohttp

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

    def test_parse_score_handles_unexpected_dict_shapes(self):
        self.assertEqual(espn_api._parse_score({"displayValue": "2"}), "2")
        self.assertEqual(espn_api._parse_score({"value": "1.0"}), "1")
        self.assertEqual(espn_api._parse_score({"value": "abc"}), "abc")
        self.assertEqual(espn_api._parse_score({}), "0")


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

    async def test_get_schedule_skips_malformed_event_and_continues(self):
        original_fetch = espn_api._fetch
        original_schedule_urls = espn_api._schedule_urls

        async def fake_fetch(_session, _url):
            return {
                "events": [
                    {
                        "id": "bad",
                        "competitions": [{"competitors": [{"homeAway": "home", "score": {"value": "bad"}}]}],
                    },
                    {
                        "id": "good",
                        "name": "Good Event",
                        "date": "2099-01-01T00:00:00Z",
                        "competitions": [
                            {
                                "status": {"type": {"state": "pre"}},
                                "competitors": [
                                    {
                                        "homeAway": "home",
                                        "team": {
                                            "id": espn_api.WHITECAPS_ID,
                                            "displayName": "Vancouver Whitecaps FC",
                                            "abbreviation": "VAN",
                                        },
                                        "score": "0",
                                    },
                                    {
                                        "homeAway": "away",
                                        "team": {
                                            "id": "2",
                                            "displayName": "Seattle Sounders",
                                            "abbreviation": "SEA",
                                        },
                                        "score": "0",
                                    },
                                ],
                            }
                        ],
                    },
                ]
            }

        try:
            espn_api._fetch = fake_fetch
            espn_api._schedule_urls = lambda: ["https://espn.test/schedule"]
            matches = await espn_api.get_schedule(session=None)
        finally:
            espn_api._fetch = original_fetch
            espn_api._schedule_urls = original_schedule_urls

        self.assertEqual([m["id"] for m in matches], ["good"])


class TestSelectionLogic(unittest.IsolatedAsyncioTestCase):
    async def test_next_match_returns_earliest_future_fixture(self):
        original_get_schedule = espn_api.get_schedule
        original_get_scoreboard = espn_api.get_scoreboard

        async def fake_schedule(_session):
            return [
                {"id": "a", "date": "2099-01-03T00:00:00Z", "status": {"state": "pre"}},
                {"id": "b", "date": "2099-01-01T00:00:00Z", "status": {"state": "pre"}},
                {"id": "c", "date": "2099-01-02T00:00:00Z", "status": {"state": "pre"}},
            ]

        async def fake_scoreboard(_session):
            return []

        try:
            espn_api.get_schedule = fake_schedule
            espn_api.get_scoreboard = fake_scoreboard
            match = await espn_api.get_next_match(session=None)
        finally:
            espn_api.get_schedule = original_get_schedule
            espn_api.get_scoreboard = original_get_scoreboard

        self.assertIsNotNone(match)
        self.assertEqual(match["id"], "b")

    async def test_schedule_fallback_uses_the_sports_db_when_espn_empty(self):
        original_fetch = espn_api._fetch
        original_schedule_urls = espn_api._schedule_urls

        async def fake_fetch(_session, url):
            if "thesportsdb" in url and "eventsnext" in url:
                return {
                    "events": [
                        {
                            "idEvent": "900",
                            "strHomeTeam": "Vancouver Whitecaps FC",
                            "strAwayTeam": "Seattle Sounders",
                            "dateEvent": "2099-01-05",
                            "strTime": "03:00:00",
                        }
                    ]
                }
            if "thesportsdb" in url and "eventslast" in url:
                return {"results": []}
            return {"events": []}

        try:
            espn_api._fetch = fake_fetch
            espn_api._schedule_urls = lambda: ["https://espn.test/schedule"]
            matches = await espn_api.get_schedule(session=None)
        finally:
            espn_api._fetch = original_fetch
            espn_api._schedule_urls = original_schedule_urls

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["id"], "900")

    async def test_schedule_merges_espn_with_the_sports_db_when_partial(self):
        original_fetch = espn_api._fetch
        original_schedule_urls = espn_api._schedule_urls

        async def fake_fetch(_session, url):
            if "espn.test/schedule" in url:
                return {
                    "events": [
                        {
                            "id": "100",
                            "name": "Caps vs Test",
                            "date": "2099-01-01T00:00:00Z",
                            "competitions": [
                                {
                                    "status": {"type": {"state": "pre"}},
                                    "competitors": [
                                        {
                                            "homeAway": "home",
                                            "team": {
                                                "id": espn_api.WHITECAPS_ID,
                                                "displayName": "Vancouver Whitecaps FC",
                                                "abbreviation": "VAN",
                                            },
                                            "score": "0",
                                        },
                                        {
                                            "homeAway": "away",
                                            "team": {
                                                "id": "2",
                                                "displayName": "Seattle Sounders",
                                                "abbreviation": "SEA",
                                            },
                                            "score": "0",
                                        },
                                    ],
                                }
                            ],
                        }
                    ]
                }
            if "thesportsdb" in url and "eventsnext" in url:
                return {
                    "events": [
                        {
                            "idEvent": "900",
                            "strHomeTeam": "Vancouver Whitecaps FC",
                            "strAwayTeam": "Portland Timbers",
                            "dateEvent": "2099-01-05",
                            "strTime": "03:00:00",
                        }
                    ]
                }
            if "thesportsdb" in url and "eventslast" in url:
                return {"results": []}
            return {"events": []}

        try:
            espn_api._fetch = fake_fetch
            espn_api._schedule_urls = lambda: ["https://espn.test/schedule"]
            matches = await espn_api.get_schedule(session=None)
        finally:
            espn_api._fetch = original_fetch
            espn_api._schedule_urls = original_schedule_urls

        self.assertEqual([m["id"] for m in matches], ["100", "900"])


class TestDebugEndpoints(unittest.IsolatedAsyncioTestCase):
    async def test_debug_endpoints_marks_empty_payloads(self):
        original_session_get = aiohttp.ClientSession.get

        class FakeResponse:
            def __init__(self, status, payload):
                self.status = status
                self._payload = payload

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return None

            async def json(self, content_type=None):
                return self._payload

            async def text(self):
                return str(self._payload)

        def fake_get(_self, url, **_kwargs):
            if "schedule?season" in url:
                return FakeResponse(200, {"events": []})
            if "eventslast" in url:
                return FakeResponse(200, {"results": []})
            if "eventsnext" in url:
                return FakeResponse(200, {"events": [{"idEvent": "1"}]})
            if "standings" in url:
                return FakeResponse(200, {"children": []})
            return FakeResponse(200, {"events": [{"id": "1"}]})

        try:
            aiohttp.ClientSession.get = fake_get
            async with aiohttp.ClientSession() as session:
                result = await espn_api.debug_endpoints(session)
        finally:
            aiohttp.ClientSession.get = original_session_get

        self.assertIn("200 EMPTY", result[f"schedule season={espn_api.datetime.now(espn_api.timezone.utc).year - 1}"])
        self.assertIn("200 OK", result["TheSportsDB next"])


class TestStandingsSort(unittest.IsolatedAsyncioTestCase):
    async def test_standings_sorted_by_points_desc(self):
        original_fetch = espn_api._fetch
        payload = {
            "children": [
                {
                    "name": "Western Conference",
                    "standings": {
                        "entries": [
                            {"team": {"id": "1", "displayName": "Team A", "abbreviation": "A"}, "stats": [{"name": "points", "displayValue": "30"}, {"name": "wins", "displayValue": "9"}]},
                            {"team": {"id": "2", "displayName": "Team B", "abbreviation": "B"}, "stats": [{"name": "points", "displayValue": "35"}, {"name": "wins", "displayValue": "10"}]},
                            {"team": {"id": "3", "displayName": "Team C", "abbreviation": "C"}, "stats": [{"name": "points", "displayValue": "32"}, {"name": "wins", "displayValue": "9"}]},
                        ]
                    },
                }
            ]
        }

        async def fake_fetch(_session, _url):
            return payload

        try:
            espn_api._fetch = fake_fetch
            standings = await espn_api.get_standings(session=None)
        finally:
            espn_api._fetch = original_fetch

        entries = standings["Western Conference"]
        self.assertEqual([e["abbreviation"] for e in entries], ["B", "C", "A"])


if __name__ == "__main__":
    unittest.main()
