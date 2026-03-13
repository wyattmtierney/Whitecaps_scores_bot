from whitecaps_bot.espn import EspnClient, _CA_BROADCAST_REPLACEMENTS, _clock_elapsed, _sub_players


def test_classify_play_goal():
    assert EspnClient._classify_play({"text": "Goal - Brian White"}) == "goal"


def test_classify_play_goal_from_type():
    assert EspnClient._classify_play({"type": {"text": "Goal"}, "text": ""}) == "goal"


def test_classify_play_own_goal():
    assert EspnClient._classify_play({"text": "Own Goal - Jordan Morris"}) == "own_goal"


def test_classify_play_penalty_goal():
    assert EspnClient._classify_play({"text": "Penalty Goal - Ryan Gauld"}) == "penalty_goal"
    assert EspnClient._classify_play({"text": "Goal! Ryan Gauld (Penalty) scored"}) == "penalty_goal"


def test_classify_play_penalty_miss():
    assert EspnClient._classify_play({"text": "Penalty missed by Raul Ruidiaz"}) == "penalty_miss"
    assert EspnClient._classify_play({"text": "Penalty saved! Raul Ruidiaz"}) == "penalty_miss"


def test_classify_play_yellow_card():
    assert EspnClient._classify_play({"text": "Yellow Card - Ranko Veselinovic"}) == "yellow_card"
    assert EspnClient._classify_play({"text": "Booking - Someone"}) == "yellow_card"


def test_classify_play_red_card():
    assert EspnClient._classify_play({"text": "Red Card - Jordan Morris"}) == "red_card"


def test_classify_play_substitution():
    assert EspnClient._classify_play({"text": "Substitution, Vancouver Whitecaps"}) == "substitution"


def test_classify_play_var():
    assert EspnClient._classify_play({"text": "VAR Decision - Goal confirmed"}) == "var"
    assert EspnClient._classify_play({"text": "Video Review in progress"}) == "var"


def test_classify_play_irrelevant():
    assert EspnClient._classify_play({"text": "Corner kick awarded"}) is None
    assert EspnClient._classify_play({"text": "Free kick taken"}) is None
    assert EspnClient._classify_play({"text": ""}) is None


def test_classify_play_no_goal():
    # "No Goal - VAR overturned" is a VAR event (contains "VAR")
    assert EspnClient._classify_play({"text": "No Goal - VAR overturned"}) == "var"
    # Plain "No Goal" with no VAR mention is skipped
    assert EspnClient._classify_play({"text": "No Goal"}) is None


def test_extract_goal_info_with_participants():
    play = {
        "text": "Goal - Brian White. Assisted by Ryan Gauld.",
        "participants": [{"athlete": {"displayName": "Brian White"}}],
    }
    scorer, assist = EspnClient._extract_goal_info(play)
    assert scorer == "Brian White"
    assert assist == "Ryan Gauld"


def test_extract_goal_info_from_text_only():
    play = {"text": "Goal - Brian White (Ryan Gauld)", "participants": []}
    scorer, assist = EspnClient._extract_goal_info(play)
    assert scorer == "Brian White"
    assert assist == "Ryan Gauld"


def test_extract_goal_info_penalty_no_assist():
    play = {"text": "Goal - Ryan Gauld (Penalty)", "participants": []}
    scorer, assist = EspnClient._extract_goal_info(play)
    assert scorer == "Ryan Gauld"
    assert assist == ""


# --- _clock_elapsed tests ---

def test_clock_elapsed_from_display_value():
    # displayValue "54:32" → minute 54
    assert _clock_elapsed({"displayValue": "54:32", "value": 9999}) == 54


def test_clock_elapsed_from_value_seconds():
    # No displayValue → fall back to value // 60
    assert _clock_elapsed({"value": 3229}) == 53   # 3229 // 60


def test_clock_elapsed_value_zero():
    assert _clock_elapsed({"value": 0}) is None


def test_clock_elapsed_empty():
    assert _clock_elapsed({}) is None


# --- _sub_players tests ---

def test_sub_players_type_based():
    play = {
        "participants": [
            {"athlete": {"displayName": "Player Off"}, "type": {"text": "Off"}},
            {"athlete": {"displayName": "Player On"}, "type": {"text": "On"}},
        ]
    }
    player_in, player_out = _sub_players(play)
    assert player_in == "Player On"
    assert player_out == "Player Off"


def test_sub_players_positional_fallback():
    # No type field → ESPN order is [off, on]
    play = {
        "participants": [
            {"athlete": {"displayName": "Going Off"}},
            {"athlete": {"displayName": "Coming On"}},
        ]
    }
    player_in, player_out = _sub_players(play)
    assert player_in == "Coming On"
    assert player_out == "Going Off"


def test_sub_players_no_participants():
    play = {"participants": []}
    player_in, player_out = _sub_players(play)
    assert player_in == "Unknown"
    assert player_out == "Unknown"


# --- Canadian broadcast replacement tests ---

def test_ca_broadcast_replacements_covers_fs2_and_tudn():
    assert "FS2" in _CA_BROADCAST_REPLACEMENTS
    assert "TUDN" in _CA_BROADCAST_REPLACEMENTS
    assert "OneSoccer" in _CA_BROADCAST_REPLACEMENTS["FS2"]
    assert "FuboTV" in _CA_BROADCAST_REPLACEMENTS["FS2"]


def test_extract_match_replaces_fs2_with_canadian(monkeypatch):
    """FS2 in ESPN broadcasts should appear as OneSoccer / FuboTV, not FS2."""
    import asyncio
    from datetime import datetime, timezone
    from unittest.mock import AsyncMock

    client = EspnClient()
    payload = {
        "events": [
            {
                "id": "12345",
                "date": "2026-03-12T03:00Z",
                "status": {"type": {"name": "STATUS_SCHEDULED", "shortDetail": "7:00 PM ET", "completed": False}},
                "competitions": [
                    {
                        "competitors": [
                            {"homeAway": "home", "team": {"id": "9727", "displayName": "Vancouver Whitecaps", "shortDisplayName": "Vancouver"}, "score": "0"},
                            {"homeAway": "away", "team": {"id": "1234", "displayName": "Seattle Sounders FC", "shortDisplayName": "Seattle"}, "score": "0"},
                        ],
                        "broadcasts": [{"names": ["FS2"]}, {"names": ["TUDN"]}],
                        "geoBroadcasts": [],
                        "venue": {"fullName": "BC Place"},
                    }
                ],
            }
        ]
    }
    monkeypatch.setattr(client, "_get", AsyncMock(return_value=payload))
    result = asyncio.get_event_loop().run_until_complete(client.get_upcoming_fixtures())
    assert result
    match = result[0]
    # Neither FS2 nor TUDN should appear
    combined = " ".join(match.broadcasts)
    assert "FS2" not in combined
    assert "TUDN" not in combined
    # Canadian replacement should appear exactly once
    assert combined.count("OneSoccer") == 1
