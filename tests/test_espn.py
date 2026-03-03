from whitecaps_bot.espn import EspnClient


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
