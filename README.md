# MTG Spoilers Bot

A Discord bot that posts Scryfall spoilers/releases daily, auto-routing **Universes Beyond** to a dedicated channel and regular spoilers elsewhere. Includes owner-only manual commands.

## Features
- Scryfall **Bulk Data** (no blank searches), with local cache.
- **Date-based** detection (`released_at`, `preview.previewed_at`) to avoid tz issues.
- Universes Beyond detection via `promo_types: ["universesbeyond"]`
- Owner-only `!check-now` and `!post-all`.
- **Per-card** persistence: saves progress after each posted card to survive restarts.
- All status/debug messages go to a testing channel.

## Quick start

1. Python 3.10+ recommended  
2. Install deps:
   ```bash
   pip install -r requirements.txt
   ```
