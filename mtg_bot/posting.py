import asyncio
from datetime import datetime

from .config import Config
from .state import StateDict, save_state_atomic, has_been_posted, persist_posted
from .embeds import card_embed


async def post_cards_to_channel(
    cards: list[dict],
    post_channel,
    testing_channel,
    cfg: Config,
    st: StateDict,
    since_date,
    bulk_updated_at: str,
    no_cards_message: str = "No new spoilers/releases on/after {since_date} (Bulk updated: {bulk_updated_at})."
) -> tuple[int, StateDict]:
    """
    Post cards to the channel, skipping already posted ones.
    Returns (posted_count, updated_state)
    """
    if not cards:
        st["last_run_date"] = datetime.now().date().isoformat()
        save_state_atomic(cfg.state_path, st)
        if testing_channel:
            await testing_channel.send(
                no_cards_message.format(since_date=since_date, bulk_updated_at=bulk_updated_at)
            )
        return 0, st

    if not post_channel:
        if testing_channel:
            await testing_channel.send("⚠️ Spoilers channel not found; cannot post embeds.")
        return 0, st

    delay_s = max(0.0, cfg.post_delay_ms / 1000.0)
    posted_total = 0

    for card in cards:
        if has_been_posted(st, card):
            continue
        embed = card_embed(card)
        await post_channel.send(embed=embed)
        posted_total += 1
        st = persist_posted(cfg.state_path, st, card)
        if delay_s > 0:
            await asyncio.sleep(delay_s)

    # Update last run date
    st["last_run_date"] = datetime.now().date().isoformat()
    save_state_atomic(cfg.state_path, st)

    if testing_channel:
        await testing_channel.send(
            f"✅ Posted {posted_total} item(s). since_date={since_date} (Bulk updated: {bulk_updated_at})."
        )

    return posted_total, st


async def check_and_post_preview(
    previews: list[dict],
    testing_channel,
    since_date,
    bulk_updated_at: str
):
    """
    For !check-now: post the first preview to testing channel if available.
    """
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