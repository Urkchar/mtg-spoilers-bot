# MTG Spoilers Bot

A Discord bot that posts Scryfall spoilers/releases daily to a single channel. Includes owner-only manual commands for on-demand checks.

## Features
- Uses Scryfall **Bulk Data** with a local cache (no live scraping).
- **Date-based** detection (`released_at`, `preview.previewed_at`) to avoid time zone issues.
- Owner-only `!check-now` and `!post-all` commands.
- **Per-card** persistence: saves progress after each posted card so restarts don't duplicate posts.
- All status/debug messages go to a separate testing channel.

## Quick start
1. Python 3.10+ recommended  
2. Install deps:
```bash
pip install -r requirements.txt
```