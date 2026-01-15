import discord
from .scryfall import card_image, is_ub

UB_COLOR = 0x6A0DAD
REGULAR_COLOR = 0x2B6CB0

def card_embed(card: dict) -> discord.Embed:
    ub = is_ub(card)
    color = UB_COLOR if ub else REGULAR_COLOR
    embed = discord.Embed(
        title=card.get("name", "Unknown"),
        url=card.get("scryfall_uri"),
        description=card.get("type_line", ""),
        color=color
    )
    rules = card.get("oracle_text")
    if rules:
        embed.add_field(
            name="Text",
            value=(rules if len(rules) < 1024 else rules[:1000] + "…"),
            inline=False
        )
    ra = card.get("released_at")
    pv = (card.get("preview") or {}).get("previewed_at")
    dates = []
    if ra: dates.append(f"Release: {ra}")
    if pv: dates.append(f"Preview: {pv}")
    if dates:
        embed.add_field(name="Dates", value=" | ".join(dates), inline=True)
    img = card_image(card)
    if img:
        embed.set_image(url=img)
    set_name = card.get("set_name")
    collector = card.get("collector_number")
    if set_name or collector:
        embed.set_footer(text=f"{set_name or ''} #{collector or ''}".strip())
    return embed
