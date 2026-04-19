import aiohttp
from datetime import datetime, timedelta, time as timeobj
from discord.ext import tasks

from mtg_bot.state import load_state
from .config import Config, safe_tz
from .scryfall import BulkScryfall, filter_recent_cards
from .posting import post_cards_to_channel


def setup_daily_post(bot, cfg: Config):
    @tasks.loop(time=timeobj(hour=cfg.post_hour, minute=cfg.post_minute))
    async def daily_post():
        await bot.wait_until_ready()

        testing_channel = bot.get_channel(cfg.bot_testing_channel_id)
        post_channel = bot.get_channel(cfg.mtg_spoilers_channel_id)

        if testing_channel is None and post_channel is None:
            print("[daily_post] No channels available; aborting run.")
            return

        tz = safe_tz(cfg.tz_key)
        now_local = datetime.now(tz)
        since_date = (now_local.date() - timedelta(days=cfg.window_days))

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
            bulk = BulkScryfall(
                session, cfg.bulk_meta_path, cfg.bulk_file_path)
            _, bulk_updated_at = await bulk.ensure_bulk_file()
            recent_cards = filter_recent_cards(cfg.bulk_file_path, since_date)

            st = load_state(cfg.state_path)
            await post_cards_to_channel(
                recent_cards, post_channel, testing_channel, cfg, st, since_date, bulk_updated_at,
                no_cards_message="🔔 No new Scryfall cards or spoilers since {since_date} (Bulk updated: {bulk_updated_at})."
            )

    @daily_post.before_loop
    async def _before():
        await bot.wait_until_ready()

    # Expose so the caller can start it after bot login
    return daily_post
