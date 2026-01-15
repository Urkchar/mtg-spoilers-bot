import asyncio, aiohttp
from datetime import datetime, timedelta
from .config import Config, safe_tz
from .scryfall import BulkScryfall, filter_recent_cards, is_ub
from .embeds import card_embed
from .state import load_state, save_state_atomic, has_been_posted, persist_posted

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
        is_owner = (message.guild is not None and message.guild.owner_id == message.author.id)
        if not is_owner:
            if testing_channel:
                await testing_channel.send(
                    f"⛔ Command '{content}' blocked. Only the server owner can run this command. "
                    f"(User: {message.author}, Guild: {message.guild and message.guild.name})"
                )
            return

        tz = safe_tz(cfg.tz_key)
        now_local  = datetime.now(tz)
        since_date = (now_local.date() - timedelta(days=cfg.window_days))

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
            bulk = BulkScryfall(session, cfg.bulk_meta_path, cfg.bulk_file_path)
            _, bulk_updated_at = await bulk.ensure_bulk_file()
            previews = filter_recent_cards(cfg.bulk_file_path, since_date)

        ub_previews = [c for c in previews if is_ub(c)]
        rg_previews = [c for c in previews if not is_ub(c)]

        if testing_channel:
            tag = "!check-now" if content == "!check-now" else "!post-all"
            await testing_channel.send(
                f"Debug ({tag}): since_date={since_date}, bulk_updated_at={bulk_updated_at}, "
                f"previews_total={len(previews)}, ub={len(ub_previews)}, regular={len(rg_previews)}"
            )

        if content == "!check-now":
            if not previews:
                if testing_channel:
                    await testing_channel.send(
                        f"No new spoilers/releases on/after {since_date} (Bulk updated: {bulk_updated_at})."
                    )
                return
            card = previews[0]
            embed = card_embed(card)
            if testing_channel:
                await testing_channel.send(embed=embed)
                await testing_channel.send(
                    f"✅ Posted 1 item (newest). since_date={since_date} (Bulk updated: {bulk_updated_at})."
                )
            return

        # !post-all
        ub_channel  = bot.get_channel(cfg.ub_spoilers_channel_id)
        reg_channel = bot.get_channel(cfg.mtg_spoilers_channel_id)

        if not previews:
            st = load_state(cfg.state_path)
            st["last_run_date"] = now_local.date().isoformat()
            save_state_atomic(cfg.state_path, st)
            if testing_channel:
                await testing_channel.send(
                    f"No new spoilers/releases on/after {since_date} (Bulk updated: {bulk_updated_at})."
                )
            return

        delay_s = max(0.0, cfg.post_delay_ms / 1000.0)
        posted_ub = posted_rg = 0
        st = load_state(cfg.state_path)

        if ub_channel:
            for card in ub_previews:
                if has_been_posted(st, card):
                    continue
                await ub_channel.send(embed=card_embed(card))
                posted_ub += 1
                st = persist_posted(cfg.state_path, st, card)
                if delay_s > 0:
                    await asyncio.sleep(delay_s)
        else:
            if testing_channel:
                await testing_channel.send("⚠️ UB spoilers channel not found; cannot post UB embeds.")

        if reg_channel:
            for card in rg_previews:
                if has_been_posted(st, card):
                    continue
                await reg_channel.send(embed=card_embed(card))
                posted_rg += 1
                st = persist_posted(cfg.state_path, st, card)
                if delay_s > 0:
                    await asyncio.sleep(delay_s)
        else:
            if testing_channel:
                await testing_channel.send("⚠️ Regular spoilers channel not found; cannot post regular embeds.")

        st["last_run_date"] = now_local.date().isoformat()
        save_state_atomic(cfg.state_path, st)

        if testing_channel:
            await testing_channel.send(
                f"✅ Posted UB={posted_ub}, Regular={posted_rg} item(s). "
                f"since_date={since_date} (Bulk updated: {bulk_updated_at})."
            )
