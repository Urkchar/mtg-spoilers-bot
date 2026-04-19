import discord
from discord.ext import commands
from .config import load_config

from .tasks import setup_daily_post, setup_hourly_news

from .commands_spoilers import setup_commands


def main():
    cfg = load_config()

    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents)

    # Register commands and events
    setup_commands(bot, cfg)

    # Build and start the tasks once the bot is up
    daily_post = setup_daily_post(bot, cfg)
    hourly_news = setup_hourly_news(bot)

    @bot.event
    async def on_ready():
        print(f"Logged in as {bot.user} (ID: {bot.user.id})")
        # start scheduled task if not already running
        if not daily_post.is_running():
            daily_post.start()

        if not hourly_news.is_running():
            hourly_news.start()

    bot.run(cfg.discord_token)


if __name__ == "__main__":
    main()
