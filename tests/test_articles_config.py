import os
import importlib
import builtins
import pytest

# We import the module under test.
# If your project structure differs, adjust the import accordingly:
from mtg_bot import tasks_articles

def test_load_news_channel_id_returns_int_when_valid(monkeypatch):
    """Should return int when MTG_NEWS_CHANNEL_ID is a valid integer string."""
    monkeypatch.setenv("MTG_NEWS_CHANNEL_ID", "123456789012345678")
    value = tasks_articles.load_news_channel_id()
    assert isinstance(value, int)
    assert value == 123456789012345678


def test_load_news_channel_id_exits_when_missing(monkeypatch):
    """Should sys.exit with a helpful message when env var is missing."""
    # Ensure the variable is not present
    monkeypatch.delenv("MTG_NEWS_CHANNEL_ID", raising=False)

    with pytest.raises(SystemExit) as excinfo:
        _ = tasks_articles.load_news_channel_id()

    # Validate exit message for clarity
    assert "Missing required env var: MTG_NEWS_CHANNEL_ID" in str(excinfo.value)


def test_load_news_channel_id_exits_when_not_int(monkeypatch):
    """Should sys.exit with a helpful message when env var is not an integer."""
    monkeypatch.setenv("MTG_NEWS_CHANNEL_ID", "not-an-integer")

    with pytest.raises(SystemExit) as excinfo:
        _ = tasks_articles.load_news_channel_id()

    msg = str(excinfo.value)
    assert "Invalid integer for MTG_NEWS_CHANNEL_ID" in msg
    assert "not-an-integer" in msg
