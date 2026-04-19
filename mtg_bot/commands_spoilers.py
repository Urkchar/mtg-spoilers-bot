import aiohttp
from datetime import datetime, timedelta
from discord.ext import commands

from mtg_bot.posting import check_and_post_preview, post_cards_to_channel

from .config import Config, safe_tz
from .scryfall import BulkScryfall, filter_recent_cards
from .state import load_state


def setup_commands(bot: commands.Bot, cfg: Config):
    @bot.event
    async def on_ready():
        print(f"Logged in as {bot.user} (ID: {bot.user.id})")

    @bot.command(name="check-now")
    @commands.is_owner()
    async def check_now(ctx):
        """Check for new spoilers and post the newest one to testing channel."""
        testing_channel = bot.get_channel(cfg.bot_testing_channel_id)

        tz = safe_tz(cfg.tz_key)
        now_local = datetime.now(tz)
        since_date = (now_local.date() - timedelta(days=cfg.window_days))

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
            bulk = BulkScryfall(
                session, cfg.bulk_meta_path, cfg.bulk_file_path)
            _, bulk_updated_at = await bulk.ensure_bulk_file()
            previews = filter_recent_cards(cfg.bulk_file_path, since_date)

            if testing_channel:
                await testing_channel.send(
                    f"Debug (!check-now): since_date={since_date}, bulk_updated_at={bulk_updated_at}, "
                    f"previews_total={len(previews)}"
                )

            await check_and_post_preview(previews, testing_channel, since_date, bulk_updated_at)

    @bot.command(name="post-all")
    @commands.is_owner()
    async def post_all(ctx):
        """Post all new spoilers to the spoilers channel."""
        testing_channel = bot.get_channel(cfg.bot_testing_channel_id)

        tz = safe_tz(cfg.tz_key)
        now_local = datetime.now(tz)
        since_date = (now_local.date() - timedelta(days=cfg.window_days))

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
            bulk = BulkScryfall(
                session, cfg.bulk_meta_path, cfg.bulk_file_path)
            _, bulk_updated_at = await bulk.ensure_bulk_file()
            previews = filter_recent_cards(cfg.bulk_file_path, since_date)

            if testing_channel:
                await testing_channel.send(
                    f"Debug (!post-all): since_date={since_date}, bulk_updated_at={bulk_updated_at}, "
                    f"previews_total={len(previews)}"
                )

            post_channel = bot.get_channel(cfg.mtg_spoilers_channel_id)
            st = load_state(cfg.state_path)
            await post_cards_to_channel(
                previews, post_channel, testing_channel, cfg, st, since_date, bulk_updated_at
            )
