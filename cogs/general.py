import discord
from discord import app_commands
from discord.ext import commands


class General(commands.Cog):
    """General bot commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Check bot latency")
    async def ping(self, interaction: discord.Interaction):
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"Pong! `{latency}ms`")

    @app_commands.command(name="help", description="Show available commands")
    async def help(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="CGRC Bot Commands",
            description="Connecting CGRC with Strava",
            color=discord.Color.orange(),
        )
        embed.add_field(
            name="General",
            value="`/ping` — Check bot latency\n`/help` — Show this message",
            inline=False,
        )
        embed.add_field(
            name="Strava",
            value="`/strava status` — Check the bot's Strava connection status",
            inline=False,
        )
        embed.add_field(
            name="Miles Tracker",
            value="`/leaders` — Show the annual miles leaderboard\n*(Auto-posts every Monday at 8:00 UTC)*",
            inline=False,
        )
        embed.add_field(
            name="Admin only",
            value=(
                "`/notify setchannel` — Set the channel for run notifications and weekly recaps\n"
                "`/notify custommessages` — Toggle custom per-member messages on or off\n"
                "`/setmiles [name] [miles]` — Set a member's total miles for the year\n"
                "`/strava status` — Check the bot's Strava connection\n"
                "`/strava test` — Send a test run notification"
            ),
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(General(bot))
