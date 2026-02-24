from whitecaps_bot.config import Settings


def test_settings_reads_railway_discord_token(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "railway-token")
    monkeypatch.setenv("CHANNEL_ID", "123")
    monkeypatch.setenv("FORUM_CHANNEL_ID", "456")

    settings = Settings.from_env()

    assert settings.discord_token == "railway-token"
    assert settings.channel_id == 123
    assert settings.forum_channel_id == 456


def test_settings_falls_back_to_discord_bot_token(monkeypatch):
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "legacy-token")

    settings = Settings.from_env()

    assert settings.discord_token == "legacy-token"


def test_api_football_key_is_optional(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "railway-token")
    monkeypatch.delenv("API_FOOTBALL_KEY", raising=False)
    monkeypatch.delenv("APIFOOTBALL_KEY", raising=False)

    settings = Settings.from_env()

    assert settings.api_football_key is None


def test_espn_team_defaults_and_override(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "railway-token")
    default_settings = Settings.from_env()
    assert default_settings.espn_team_id == "9720"

    monkeypatch.setenv("ESPN_TEAM_ID", "9000")
    monkeypatch.setenv("ESPN_TEAM_NAME", "Custom Team")
    custom_settings = Settings.from_env()
    assert custom_settings.espn_team_id == "9000"
    assert custom_settings.espn_team_name == "Custom Team"
