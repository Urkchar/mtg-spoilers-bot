import asyncio, aiohttp
from datetime import datetime, timedelta, time as timeobj
from discord.ext import tasks

from .config import Config, safe_tz
from .state import load_state, save_state_atomic, has_been_posted, persist_posted
from .scryfall import BulkScryfall, filter_recent_cards
from .embeds import card_embed


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
            bulk = BulkScryfall(session, cfg.bulk_meta_path, cfg.bulk_file_path)
            _, bulk_updated_at = await bulk.ensure_bulk_file()
            recent_cards = filter_recent_cards(cfg.bulk_file_path, since_date)

            if not recent_cards:
                if testing_channel:
                    await testing_channel.send(
                        f"🔔 No new Scryfall cards or spoilers since {since_date} (Bulk updated: {bulk_updated_at})."
                    )
                st = load_state(cfg.state_path)
                st["last_run_date"] = now_local.date().isoformat()
                save_state_atomic(cfg.state_path, st)
                return

            if not post_channel:
                if testing_channel:
                    await testing_channel.send("⚠️ Spoilers channel not found; cannot post embeds.")
                return

            st = load_state(cfg.state_path)
            posted_total = 0
            delay_s = max(0.0, cfg.post_delay_ms / 1000.0)

            for card in recent_cards:
                if has_been_posted(st, card):
                    continue
                embed = card_embed(card)
                await post_channel.send(embed=embed)
                posted_total += 1
                st = persist_posted(cfg.state_path, st, card)
                if delay_s > 0:
                    await asyncio.sleep(delay_s)

            # Update last run date
            st["last_run_date"] = now_local.date().isoformat()
            save_state_atomic(cfg.state_path, st)

            if testing_channel:
                await testing_channel.send(
                    f"✅ Posted {posted_total} item(s). since_date={since_date} (Bulk updated: {bulk_updated_at})."
                )

    @daily_post.before_loop
    async def _before():
        await bot.wait_until_ready()

    # Expose so the caller can start it after bot login
    return daily_post
