import discord
from .config import load_config

from .tasks_spoilers import setup_daily_post
from .tasks_articles import setup_hourly_news

from .commands_spoilers import register_handlers

def main():
    cfg = load_config()

    intents = discord.Intents.default()
    intents.message_content = True
    bot = discord.Client(intents=intents)

    # Register commands and events
    register_handlers(bot, cfg)

    # Build and start the daily task once the bot is up
    daily_post = setup_daily_post(bot, cfg)

    hourly_news = setup_hourly_news(bot)

    @bot.event
    async def on_ready():
        # start scheduled task if not already running
        if not daily_post.is_running():
            daily_post.start()

        if not hourly_news.is_running():
            hourly_news.start()

    bot.run(cfg.discord_token)

if __name__ == "__main__":
    main()
