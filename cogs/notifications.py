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
        msg = (
            "You need the **Manage Server** permission to change the notification channel."
            if isinstance(error, app_commands.MissingPermissions)
            else f"An error occurred: {error}"
        )
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)

    @notify_group.command(
        name="custommessages",
        description="Toggle custom per-member run messages on or off (admin only)",
    )
    @app_commands.describe(enabled="Turn custom messages on or off")
    @app_commands.choices(enabled=[
        app_commands.Choice(name="on", value="1"),
        app_commands.Choice(name="off", value="0"),
    ])
    @app_commands.checks.has_permissions(manage_guild=True)
    async def custommessages(self, interaction: discord.Interaction, enabled: str):
        config.store.set("CUSTOM_MESSAGES_ENABLED", enabled)
        state = "on" if enabled == "1" else "off"
        await interaction.response.send_message(
            f"Custom run messages turned **{state}**.", ephemeral=True
        )

    @custommessages.error
    async def custommessages_error(self, interaction: discord.Interaction, error):
        msg = (
            "You need the **Manage Server** permission to change this setting."
            if isinstance(error, app_commands.MissingPermissions)
            else f"An error occurred: {error}"
        )
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Notifications(bot))
