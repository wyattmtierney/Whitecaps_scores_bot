from whitecaps_bot.config import Settings


def test_settings_reads_railway_discord_token(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "railway-token")
    monkeypatch.setenv("API_FOOTBALL_KEY", "api-key")
    monkeypatch.setenv("CHANNEL_ID", "123")
    monkeypatch.setenv("FORUM_CHANNEL_ID", "456")

    settings = Settings.from_env()

    assert settings.discord_token == "railway-token"
    assert settings.channel_id == 123
    assert settings.forum_channel_id == 456


def test_settings_falls_back_to_discord_bot_token(monkeypatch):
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "legacy-token")
    monkeypatch.setenv("API_FOOTBALL_KEY", "api-key")

    settings = Settings.from_env()

    assert settings.discord_token == "legacy-token"
