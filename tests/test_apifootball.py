from whitecaps_bot.apifootball import SubstitutionEvent


def test_substitution_dedupe_key_is_stable():
    event = SubstitutionEvent(
        fixture_id=123,
        elapsed=54,
        team_name="Vancouver Whitecaps",
        player_in="Ali Ahmed",
        player_out="Ryan Gauld",
    )

    assert event.dedupe_key == "123:54:Vancouver Whitecaps:Ali Ahmed:Ryan Gauld"
