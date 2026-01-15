import os, json, aiohttp
from datetime import date

USER_AGENT = "RileysScryfallDiscordBot/1.0 (bulk default cards)"

class BulkScryfall:
    BULK_INDEX = "https://api.scryfall.com/bulk-data"

    def __init__(self, session: aiohttp.ClientSession, bulk_meta_path: str, bulk_file_path: str):
        self.session = session
        self.bulk_meta_path = bulk_meta_path
        self.bulk_file_path = bulk_file_path

    async def _get_bulk_default_meta(self) -> dict:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        async with self.session.get(self.BULK_INDEX, headers=headers) as resp:
            resp.raise_for_status()
            data = await resp.json()
        for entry in data.get("data", []):
            if entry.get("type") == "default_cards":
                return entry
        raise RuntimeError("Default Cards bulk entry not found")

    async def ensure_bulk_file(self) -> tuple[str, str]:
        meta = await self._get_bulk_default_meta()
        download_uri = meta["download_uri"]
        updated_at   = meta["updated_at"]
        prior_meta = {}
        if os.path.exists(self.bulk_meta_path):
            with open(self.bulk_meta_path, "r", encoding="utf-8") as f:
                prior_meta = json.load(f)
        need_download = (not os.path.exists(self.bulk_file_path) or prior_meta.get("updated_at") != updated_at)
        if need_download:
            await self._download_bulk(download_uri, self.bulk_file_path)
            with open(self.bulk_meta_path, "w", encoding="utf-8") as f:
                json.dump({"download_uri": download_uri, "updated_at": updated_at}, f, indent=2)
        return download_uri, updated_at

    async def _download_bulk(self, url: str, dest: str):
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        async with self.session.get(url, headers=headers) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as f:
                async for chunk in resp.content.iter_chunked(1 << 16):
                    f.write(chunk)

def card_image(card: dict) -> str | None:
    if "image_uris" in card and card["image_uris"]:
        return (card["image_uris"].get("normal")
                or card["image_uris"].get("large")
                or card["image_uris"].get("png"))
    faces = card.get("card_faces") or []
    if faces and "image_uris" in faces[0]:
        return (faces[0]["image_uris"].get("normal")
                or faces[0]["image_uris"].get("large")
                or faces[0]["image_uris"].get("png"))
    return None

def is_recent(card: dict, since_date: date) -> bool:
    ra_str = card.get("released_at")
    pv_str = (card.get("preview") or {}).get("previewed_at")
    recent_release = False
    recent_preview = False
    if ra_str:
        try:
            recent_release = date.fromisoformat(ra_str) >= since_date
        except Exception:
            pass
    if pv_str:
        try:
            recent_preview = date.fromisoformat(pv_str) >= since_date
        except Exception:
            pass
    return recent_release or recent_preview

def is_ub(card: dict) -> bool:
    promo = card.get("promo_types") or []
    if "universesbeyond" in promo:
        return True
    return (card.get("set_type") == "universes_beyond")

def filter_recent_cards(bulk_json_path: str, since_date: date) -> list[dict]:
    with open(bulk_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)  # array of cards
    recent = [c for c in data if is_recent(c, since_date)]
    def sort_key(c):
        pv = (c.get("preview") or {}).get("previewed_at")
        ra = c.get("released_at")
        return (pv or ra or "0000-01-01")
    recent.sort(key=sort_key, reverse=True)
    return recent
