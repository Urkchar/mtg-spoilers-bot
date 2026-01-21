import os
import sys
import json
import asyncio
import aiohttp
import tempfile
from datetime import datetime
from typing import Optional
from bs4 import BeautifulSoup
from discord.ext import tasks

# ----- configuration -----
NEWS_ARCHIVE_URL = "https://magic.wizards.com/en/news/archive"
BASE_URL = "https://magic.wizards.com"
STORE_PATH = "articles.json"  # JSON store for seen links

# Single target Discord channel for all articles
NEWS_CHANNEL_ENV = "MTG_NEWS_CHANNEL_ID"

def load_news_channel_id() -> int:
    raw = os.getenv(NEWS_CHANNEL_ENV)
    if raw is None:
        sys.exit(f"Missing required env var: {NEWS_CHANNEL_ENV}")
    try:
        return int(raw)
    except ValueError:
        sys.exit(f"Invalid integer for {NEWS_CHANNEL_ENV}: {raw!r}")

# ----- JSON store helpers (crash-safe, atomic writes) -----
def _default_store() -> dict:
    return {"seen_links": []}

def load_store(path: str) -> dict:
    """Load JSON store safely; return default schema if file is missing/corrupt."""
    if not os.path.exists(path):
        return _default_store()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _default_store()
        if "seen_links" not in data or not isinstance(data["seen_links"], list):
            data["seen_links"] = []
        return data
    except Exception:
        # corrupted or unreadable file: fall back to fresh store
        return _default_store()

def save_store_atomic(path: str, payload: dict) -> None:
    """
    Atomically write the whole JSON store:
    1) write to temp file in the same dir
    2) flush + fsync
    3) os.replace to target
    """
    dirpath = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmpname = tempfile.mkstemp(dir=dirpath, prefix=".tmp_articles_", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as wf:
            json.dump(payload, wf, ensure_ascii=False, indent=2)
            wf.flush()
            os.fsync(wf.fileno())
        os.replace(tmpname, path)
    finally:
        try:
            if os.path.exists(tmpname):
                os.remove(tmpname)
        except Exception:
            pass

def persist_seen_link_atomic(path: str, link: str) -> None:
    """
    Per-post persistence: reload store, append link if new, save atomically.
    Keeps in-memory consistency simple; prioritizes robustness.
    """
    store = load_store(path)
    if link not in store["seen_links"]:
        store["seen_links"].append(link)
        save_store_atomic(path, store)

# ----- scraping & routing -----
async def fetch_archive_links(session: aiohttp.ClientSession) -> list[str]:
    """
    Return a list of relative hrefs anchored under /en/news/... from the archive page.
    Uses CSS selectors for precision.
    """
    timeout = aiohttp.ClientTimeout(total=15)
    try:
        async with session.get(NEWS_ARCHIVE_URL, timeout=timeout) as resp:
            resp.raise_for_status()
            html = await resp.text()
    except Exception as e:
        print(f"[hourly_news] fetch error: {e}")
        return []
    soup = BeautifulSoup(html, "html.parser")
    # CSS selector: only anchors whose href starts with /en/news/
    anchors = soup.select('a[href^="/en/news/"]')
    return [a.get("href") for a in anchors if a.get("href")]

def make_absolute(link: str) -> str:
    return (BASE_URL + link) if link.startswith("/") else link

# ----- the hourly task (closure-based setup, mirrors tasks_spoilers.py) -----
def setup_hourly_news(bot):
    """
    Build and return the hourly news loop bound to `bot`.
    Call .start() on the returned task from app.py (e.g., in on_ready/setup_hook).
    """
    @tasks.loop(hours=1, reconnect=True)
    async def hourly_news():
        # Ensure the bot is ready
        await bot.wait_until_ready()

        # Load seen set from JSON store
        store = load_store(STORE_PATH)
        seen = set(store["seen_links"])

        # Fetch archive links via a shared session
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15),
            headers={"User-Agent": "MTGNewsBot/1.0"},
        ) as session:
            links = await fetch_archive_links(session)
            posted_count = 0

            news_channel_id = load_news_channel_id()
            target_channel = bot.get_channel(news_channel_id)
            if target_channel is None:
                print(f"[hourly_news] Channel id {news_channel_id} not found")
                return

            for link in links:
                if link in seen:
                    continue  # already handled
                # We now send all /en/news/... links to the single channel
                if not link.startswith("/en/news/"):
                    continue

                url = make_absolute(link)
                try:
                    await target_channel.send(url)
                    posted_count += 1
                    # Persist progress immediately (atomic, per-post)
                    persist_seen_link_atomic(STORE_PATH, link)
                    seen.add(link)  # keep in-memory set synced
                    # Optional: small delay to be gentle with rate limits
                    await asyncio.sleep(0.8)
                except Exception as e:
                    print(f"[hourly_news] send error for {url}: {e}")

        print(
            f"[hourly_news] posted={posted_count} at "
            f"{datetime.now().isoformat(timespec='seconds')}"
        )

    @hourly_news.before_loop
    async def _before_hourly_news():
        # In case the loop is started very early, ensure client is ready
        await bot.wait_until_ready()

    return hourly_news
