import asyncio, aiohttp
from datetime import datetime, timedelta, time as timeobj
from discord.ext import tasks
from .config import Config, safe_tz
from .state import load_state, save_state_atomic, has_been_posted, persist_posted
from .scryfall import BulkScryfall, filter_recent_cards, is_ub
from .embeds import card_embed

def setup_daily_post(bot, cfg: Config):
    @tasks.loop(time=timeobj(hour=cfg.post_hour, minute=cfg.post_minute))
    async def daily_post():
        await bot.wait_until_ready()
        testing_channel = bot.get_channel(cfg.bot_testing_channel_id)
        ub_channel      = bot.get_channel(cfg.ub_spoilers_channel_id)
        reg_channel     = bot.get_channel(cfg.mtg_spoilers_channel_id)

        if testing_channel is None and ub_channel is None and reg_channel is None:
            print("[daily_post] No channels available; aborting run.")
            return

        tz = safe_tz(cfg.tz_key)
        now_local  = datetime.now(tz)
        since_date = (now_local.date() - timedelta(days=cfg.window_days))

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
            bulk = BulkScryfall(session, cfg.bulk_meta_path, cfg.bulk_file_path)
            _, bulk_updated_at = await bulk.ensure_bulk_file()
            recent_cards = filter_recent_cards(cfg.bulk_file_path, since_date)

        ub_cards = [c for c in recent_cards if is_ub(c)]
        rg_cards = [c for c in recent_cards if not is_ub(c)]

        # if testing_channel:
        #     await testing_channel.send(
        #         f"Debug: since_date={since_date}, bulk_updated_at={bulk_updated_at}, "
        #         f"recent_total={len(recent_cards)}, ub={len(ub_cards)}, regular={len(rg_cards)}"
        #     )

        if not recent_cards:
            if testing_channel:
                await testing_channel.send(
                    f"🔔 No new Scryfall cards or spoilers since {since_date} (Bulk updated: {bulk_updated_at})."
                )
            st = load_state(cfg.state_path)
            st["last_run_date"] = now_local.date().isoformat()
            save_state_atomic(cfg.state_path, st)
            return

        st = load_state(cfg.state_path)
        posted_ub = posted_rg = 0
        delay_s = max(0.0, cfg.post_delay_ms / 1000.0)

        # UB first
        if ub_channel:
            for card in ub_cards:
                if has_been_posted(st, card):
                    continue
                embed = card_embed(card)
                await ub_channel.send(embed=embed)
                posted_ub += 1
                st = persist_posted(cfg.state_path, st, card)
                if delay_s > 0:
                    await asyncio.sleep(delay_s)
        else:
            if testing_channel:
                await testing_channel.send("⚠️ UB spoilers channel not found; cannot post UB embeds.")

        # Regular
        if reg_channel:
            for card in rg_cards:
                if has_been_posted(st, card):
                    continue
                embed = card_embed(card)
                await reg_channel.send(embed=embed)
                posted_rg += 1
                st = persist_posted(cfg.state_path, st, card)
                if delay_s > 0:
                    await asyncio.sleep(delay_s)
        else:
            if testing_channel:
                await testing_channel.send("⚠️ Regular spoilers channel not found; cannot post regular embeds.")

        # Update last run date
        st["last_run_date"] = now_local.date().isoformat()
        save_state_atomic(cfg.state_path, st)

        if testing_channel:
            await testing_channel.send(
                f"✅ Posted UB={posted_ub}, Regular={posted_rg} item(s). "
                f"since_date={since_date} (Bulk updated: {bulk_updated_at})."
            )

    @daily_post.before_loop
    async def _before():
        await bot.wait_until_ready()

    # Expose so the caller can start it after bot login
    return daily_post
