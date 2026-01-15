import os, sys
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Config:
    discord_token: str
    mtg_spoilers_channel_id: int
    ub_spoilers_channel_id: int
    bot_testing_channel_id: int
    post_hour: int
    post_minute: int
    tz_key: str
    bulk_dir: str
    bulk_meta_path: str
    bulk_file_path: str
    window_days: int
    state_path: str
    post_delay_ms: int

def _require_int(name: str, default: str | None = None) -> int:
    raw = os.getenv(name, default)
    if raw is None:
        sys.exit(f"Missing required env var: {name}")
    try:
        val = int(raw)
    except ValueError:
        sys.exit(f"Invalid integer for {name}: {raw!r}")
    return val

def load_config() -> Config:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        sys.exit("Missing required env var: DISCORD_TOKEN")

    mtg_id = _require_int("MTG_SPOILERS_CHANNEL_ID", os.getenv("MTG_SPOILERS_CHANNEL_ID", "1255377756129071178"))
    ub_id  = _require_int("UB_SPOILERS_CHANNEL_ID",  os.getenv("UB_SPOILERS_CHANNEL_ID",  "1458709510708396285"))
    test_id= _require_int("BOT_TESTING_CHANNEL_ID")

    post_hour   = _require_int("POST_HOUR", "9")
    post_minute = _require_int("POST_MINUTE", "0")
    tz_key      = os.getenv("TZ", "America/Chicago")
    bulk_dir    = os.getenv("BULK_DIR", "bulk_cache")
    os.makedirs(bulk_dir, exist_ok=True)
    bulk_meta   = os.path.join(bulk_dir, "bulk_default_meta.json")
    bulk_file   = os.path.join(bulk_dir, "bulk_default_cards.json")
    window_days = _require_int("WINDOW_DAYS", "1")
    state_path  = os.getenv("STATE_PATH", "state.json")
    post_delay  = _require_int("POST_DELAY_MS", "700")

    return Config(
        discord_token=token,
        mtg_spoilers_channel_id=mtg_id,
        ub_spoilers_channel_id=ub_id,
        bot_testing_channel_id=test_id,
        post_hour=post_hour,
        post_minute=post_minute,
        tz_key=tz_key,
        bulk_dir=bulk_dir,
        bulk_meta_path=bulk_meta,
        bulk_file_path=bulk_file,
        window_days=window_days,
        state_path=state_path,
        post_delay_ms=post_delay
    )

def safe_tz(tz_key: str) -> timezone:
    try:
        return ZoneInfo(tz_key)
    except ZoneInfoNotFoundError:
        return datetime.now().astimezone().tzinfo or timezone.utc
