import aiohttp
from datetime import datetime, timedelta

from mtg_bot.state import load_state
from .config import Config, safe_tz
from .scryfall import BulkScryfall, filter_recent_cards
from .posting import post_cards_to_channel, check_and_post_preview


def register_handlers(bot, cfg: Config):
    @bot.event
    async def on_ready():
        print(f"Logged in as {bot.user} (ID: {bot.user.id})")

    @bot.event
    async def on_message(message):
        if message.author.bot:
            return
        content = message.content.strip().lower()
        if content not in ("!check-now", "!post-all"):
            return

        testing_channel = bot.get_channel(cfg.bot_testing_channel_id)

        # Owner-only gate
        is_owner = (
            message.guild is not None and message.guild.owner_id == message.author.id)
        if not is_owner:
            if testing_channel:
                await testing_channel.send(
                    f"⛔ Command '{content}' blocked. Only the server owner can run this command. "
                    f"(User: {message.author}, Guild: {message.guild and message.guild.name})"
                )
            return

        tz = safe_tz(cfg.tz_key)
        now_local = datetime.now(tz)
        since_date = (now_local.date() - timedelta(days=cfg.window_days))

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
            bulk = BulkScryfall(
                session, cfg.bulk_meta_path, cfg.bulk_file_path)
            _, bulk_updated_at = await bulk.ensure_bulk_file()
            previews = filter_recent_cards(cfg.bulk_file_path, since_date)

            if testing_channel:
                tag = "!check-now" if content == "!check-now" else "!post-all"
                await testing_channel.send(
                    f"Debug ({tag}): since_date={since_date}, bulk_updated_at={bulk_updated_at}, "
                    f"previews_total={len(previews)}"
                )

            if content == "!check-now":
                await check_and_post_preview(previews, testing_channel, since_date, bulk_updated_at)
                return

            # !post-all -> post every new preview to ONE channel
            post_channel = bot.get_channel(cfg.mtg_spoilers_channel_id)
            st = load_state(cfg.state_path)
            await post_cards_to_channel(
                previews, post_channel, testing_channel, cfg, st, since_date, bulk_updated_at
            )
