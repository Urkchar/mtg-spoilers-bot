import os
import sys
import json
import asyncio
import aiohttp
import tempfile
from datetime import datetime, timedelta, time as timeobj
from typing import Optional
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup
from discord.ext import tasks

from .config import Config, safe_tz
from .scryfall import BulkScryfall, filter_recent_cards
from .posting import post_cards_to_channel
from .state import load_state

# ----- News configuration -----
NEWS_ARCHIVE_URL = "https://magic.wizards.com/en/news/archive"
BASE_URL = "https://magic.wizards.com"
STORE_PATH = "articles.json"  # JSON store for seen links
NEWS_CHANNEL_ENV = "MTG_NEWS_CHANNEL_ID"


class BaseScheduledTask:
    """Base class for scheduled Discord bot tasks with common setup patterns."""

    def __init__(self, bot):
        self.bot = bot
        self.task = None

    def create_task(self, coro_func, **kwargs):
        """Create a task loop with common before_loop setup."""
        self.task = tasks.loop(**kwargs)(coro_func)

        @self.task.before_loop
        async def _before():
            await self.bot.wait_until_ready()

        return self.task

    def start(self):
        """Start the task if not already running."""
        if self.task and not self.task.is_running():
            self.task.start()

    def stop(self):
        """Stop the task if running."""
        if self.task and self.task.is_running():
            self.task.cancel()


class SpoilersTask(BaseScheduledTask):
    """Handles daily posting of MTG card spoilers."""

    def __init__(self, bot, cfg: Config):
        super().__init__(bot)
        self.cfg = cfg

    def setup(self):
        """Set up the daily spoilers posting task."""
        return self.create_task(
            self._daily_post,
            time=timeobj(hour=self.cfg.post_hour, minute=self.cfg.post_minute)
        )

    async def _daily_post(self):
        """Daily task to post new MTG card spoilers."""
        testing_channel = self.bot.get_channel(self.cfg.bot_testing_channel_id)
        post_channel = self.bot.get_channel(self.cfg.mtg_spoilers_channel_id)

        if testing_channel is None and post_channel is None:
            print("[daily_post] No channels available; aborting run.")
            return

        tz = safe_tz(self.cfg.tz_key)
        now_local = datetime.now(tz)
        since_date = (now_local.date() - timedelta(days=self.cfg.window_days))

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
            bulk = BulkScryfall(
                session, self.cfg.bulk_meta_path, self.cfg.bulk_file_path)
            _, bulk_updated_at = await bulk.ensure_bulk_file()
            recent_cards = filter_recent_cards(self.cfg.bulk_file_path, since_date)

            st = load_state(self.cfg.state_path)
            await post_cards_to_channel(
                recent_cards, post_channel, testing_channel, self.cfg, st, since_date, bulk_updated_at,
                no_cards_message="🔔 No new Scryfall cards or spoilers since {since_date} (Bulk updated: {bulk_updated_at})."
            )


class NewsTask(BaseScheduledTask):
    """Handles hourly posting of MTG news articles."""

    def __init__(self, bot):
        super().__init__(bot)

    def setup(self):
        """Set up the hourly news posting task."""
        return self.create_task(
            self._hourly_news,
            hours=1,
            reconnect=True
        )

    async def _hourly_news(self):
        """Hourly task to post new MTG news articles."""
        # Load seen set from JSON store
        store = self.load_store(STORE_PATH)
        seen = set(store["seen_links"])

        # Fetch archive links via a shared session
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15),
            headers={"User-Agent": "MTGNewsBot/1.0"},
        ) as session:
            links = await self.fetch_archive_links(session)
            posted_count = 0

            news_channel_id = self.load_news_channel_id()
            target_channel = self.bot.get_channel(news_channel_id)
            if target_channel is None:
                print(f"[hourly_news] Channel id {news_channel_id} not found")
                return

            for link in links:
                if link in seen:
                    continue  # already handled
                # We now send all /en/news/... links to the single channel
                if not link.startswith("/en/news/"):
                    continue
                # Defense-in-depth: also skip author-filtered archive links here
                if self._is_author_archive_link(link):
                    continue

                url = self.make_absolute(link)
                try:
                    await target_channel.send(url)
                    posted_count += 1
                    # Persist progress immediately (atomic, per-post)
                    self.persist_seen_link_atomic(STORE_PATH, link)
                    seen.add(link)  # keep in-memory set synced
                    # Optional: small delay to be gentle with rate limits
                    await asyncio.sleep(0.8)
                except Exception as e:
                    print(f"[hourly_news] send error for {url}: {e}")

        print(
            f"[hourly_news] posted={posted_count} at "
            f"{datetime.now().isoformat(timespec='seconds')}"
        )

    def load_news_channel_id(self) -> int:
        """Load news channel ID from environment."""
        raw = os.getenv(NEWS_CHANNEL_ENV)
        if raw is None:
            sys.exit(f"Missing required env var: {NEWS_CHANNEL_ENV}")
        try:
            return int(raw)
        except ValueError:
            sys.exit(f"Invalid integer for {NEWS_CHANNEL_ENV}: {raw!r}")

    def _default_store(self) -> dict:
        """Default store structure."""
        return {"seen_links": []}

    def load_store(self, path: str) -> dict:
        """Load JSON store safely; return default schema if file is missing/corrupt."""
        if not os.path.exists(path):
            return self._default_store()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return self._default_store()
            if "seen_links" not in data or not isinstance(data["seen_links"], list):
                data["seen_links"] = []
            return data
        except Exception:
            # corrupted or unreadable file: fall back to fresh store
            return self._default_store()

    def save_store_atomic(self, path: str, payload: dict) -> None:
        """
        Atomically write the whole JSON store:
        1) write to temp file in the same dir
        2) flush + fsync
        3) os.replace to target
        """
        dirpath = os.path.dirname(os.path.abspath(path)) or "."
        fd, tmpname = tempfile.mkstemp(
            dir=dirpath, prefix=".tmp_articles_", text=True)
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

    def persist_seen_link_atomic(self, path: str, link: str) -> None:
        """
        Per-post persistence: reload store, append link if new, save atomically.
        Keeps in-memory consistency simple; prioritizes robustness.
        """
        store = self.load_store(path)
        if link not in store["seen_links"]:
            store["seen_links"].append(link)
            self.save_store_atomic(path, store)

    def _is_author_archive_link(self, link: str) -> bool:
        """
        Return True for links that point to the archive page filtered by author,
        e.g., /en/news/archive?author=Mark+Rosewater
        """
        try:
            parsed = urlparse(link)
            path = (parsed.path or "").rstrip("/")
            if path == "/en/news/archive":
                qs = parse_qs(parsed.query or "")
                return "author" in qs
            return False
        except Exception:
            # If parsing fails, err on the side of posting (do not block).
            return False

    async def fetch_archive_links(self, session: aiohttp.ClientSession) -> list[str]:
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
        links = [a.get("href") for a in anchors if a.get("href")]
        # Filter out author-filtered archive pages
        links = [h for h in links if not self._is_author_archive_link(h)]
        return links

    def make_absolute(self, link: str) -> str:
        """Convert relative link to absolute URL."""
        return (BASE_URL + link) if link.startswith("/") else link


def setup_daily_post(bot, cfg: Config):
    """Legacy function for backward compatibility."""
    task = SpoilersTask(bot, cfg)
    return task.setup()


def setup_hourly_news(bot):
    """Legacy function for backward compatibility."""
    task = NewsTask(bot)
    return task.setup()