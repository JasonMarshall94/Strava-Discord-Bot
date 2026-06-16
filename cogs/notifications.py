import discord
from discord import app_commands
from discord.ext import commands

import config


class Notifications(commands.Cog):
    """Commands for managing run activity notifications."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    notify_group = app_commands.Group(
        name="notify", description="Notification settings"
    )

    @notify_group.command(
        name="setchannel",
        description="Set the channel where run notifications are posted (admin only)",
    )
    @app_commands.describe(channel="The channel to post notifications in")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setchannel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        config.store.set("NOTIFY_CHANNEL_ID", str(channel.id))
        await interaction.response.send_message(
            f"Run notifications will be posted in {channel.mention}.",
            ephemeral=True,
        )

    @setchannel.error
    async def setchannel_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "You need the **Manage Server** permission to change the notification channel.",
                ephemeral=True,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Notifications(bot))
