import unittest

import embeds


class TestScheduleEmbed(unittest.TestCase):
    def _make_match(self, match_id: str, date_value: str, state: str = "pre") -> dict:
        return {
            "id": match_id,
            "date": date_value,
            "status": {"state": state, "clock": "0'", "period": 0, "detail": ""},
            "home": {"name": "Vancouver Whitecaps FC", "abbreviation": "VAN", "score": "0"},
            "away": {"name": "Seattle Sounders", "abbreviation": "SEA", "score": "0"},
            "is_whitecaps_home": True,
        }

    def test_schedule_embed_handles_dates_with_offset_and_z(self):
        match = self._make_match("1", "2099-06-01T03:00:00+00:00Z", state="pre")
        embed = embeds.build_schedule_embed([match])

        self.assertEqual(len(embed.fields), 1)
        self.assertIn("Upcoming", embed.fields[0].name)

    def test_schedule_embed_shows_full_recent_list_when_no_upcoming(self):
        matches = [
            self._make_match(str(i), f"200{i % 10}-01-01T00:00:00Z", state="post")
            for i in range(10)
        ]

        embed = embeds.build_schedule_embed(matches, max_matches=8)
        self.assertEqual(len(embed.fields), 1)
        lines = embed.fields[0].value.split("\n")
        self.assertEqual(len(lines), 8)


if __name__ == "__main__":
    unittest.main()
