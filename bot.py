import asyncio
import logging

import discord
from discord.ext import commands

import config

logger = logging.getLogger(__name__)

INITIAL_COGS = [
    "cogs.general",
    "cogs.strava",
    "cogs.notifications",
]


class CGRCBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            description="CGRC Strava Connection Bot",
        )
        self._webhook_server = None

    async def setup_hook(self):
        for cog in INITIAL_COGS:
            try:
                await self.load_extension(cog)
                logger.info(f"Loaded cog: {cog}")
            except Exception as e:
                logger.error(f"Failed to load cog {cog}: {e}")

        if config.DISCORD_GUILD_ID:
            guild = discord.Object(id=config.DISCORD_GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info(f"Synced slash commands to guild {config.DISCORD_GUILD_ID}")
        else:
            await self.tree.sync()
            logger.info("Synced slash commands globally")

        # Start the webhook/OAuth callback server
        from webhook_server import WebhookServer

        self._webhook_server = WebhookServer(self)
        asyncio.create_task(
            self._webhook_server.start(config.WEBHOOK_HOST, config.WEBHOOK_PORT)
        )

    async def close(self):
        if self._webhook_server:
            await self._webhook_server.stop()
        await super().close()

    async def on_ready(self):
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="CGRC Strava activities",
            )
        )
