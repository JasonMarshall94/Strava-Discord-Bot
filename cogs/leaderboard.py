import datetime

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config

GOAL_MILES = 100.0
RECAP_DAY = 0   # Monday (0=Mon … 6=Sun)
RECAP_HOUR = 8  # 8:00 UTC


def _weeks_remaining(year: int) -> int:
    today = datetime.date.today()
    year_end = datetime.date(year, 12, 31)
    return max(0, (year_end - today).days // 7)


def _build_embed() -> discord.Embed:
    year = datetime.datetime.now(tz=datetime.timezone.utc).year
    rows = config.store.get_yearly_miles(year)

    embed = discord.Embed(
        title=f"🏃 CGRC {year} Miles Tracker",
        description=f"Annual goal: **{int(GOAL_MILES)} miles** per member",
        color=discord.Color.orange(),
    )

    if not rows:
        embed.add_field(name="Leaderboard", value="No runs logged yet.", inline=False)
    else:
        # Fixed-width table in a code block
        lines = ["#    Name            Miles    Left"]
        lines.append("─" * 36)
        for i, row in enumerate(rows, 1):
            miles = row["total_miles"]
            left = "👑" if miles >= GOAL_MILES else f"{GOAL_MILES - miles:.1f}"
            name = row["display_name"]
            lines.append(f"{i:<4} {name:<15} {miles:>6.1f}   {left}")
        embed.add_field(
            name="Leaderboard (most → least)",
            value="```\n" + "\n".join(lines) + "\n```",
            inline=False,
        )

    weeks_left = _weeks_remaining(year)
    embed.set_footer(text=f"{weeks_left} weeks remaining in {year}")
    embed.timestamp = datetime.datetime.now(tz=datetime.timezone.utc)
    return embed


class Leaderboard(commands.Cog):
    """Miles leaderboard and weekly recap."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.weekly_recap.start()

    def cog_unload(self):
        self.weekly_recap.cancel()

    @app_commands.command(name="leaders", description="Show the CGRC annual miles leaderboard")
    async def miles(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await interaction.followup.send(embed=_build_embed())

    @app_commands.command(name="setmiles", description="Set a member's total miles for the year (admin only)")
    @app_commands.describe(display_name="Member's display name (e.g. Jason)", miles="Total miles to set")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setmiles(self, interaction: discord.Interaction, display_name: str, miles: float):
        members = config.store.get_all_members()
        member = next((m for m in members if m["display_name"].lower() == display_name.lower()), None)

        if not member:
            names = ", ".join(m["display_name"] for m in members)
            await interaction.response.send_message(
                f"Member `{display_name}` not found. Known members: {names}",
                ephemeral=True,
            )
            return

        if not member["strava_firstname"]:
            await interaction.response.send_message(
                f"No Strava name mapped for `{display_name}` yet. Update members.json first.",
                ephemeral=True,
            )
            return

        config.store.set_manual_miles(member["strava_firstname"], member["strava_lastname"], miles)

        strava_cog = self.bot.cogs.get("Strava")
        if strava_cog:
            strava_cog.request_silent_poll()

        await interaction.response.send_message(
            f"✅ Set **{member['display_name']}** to **{miles} mi**.",
            ephemeral=True,
        )

    @setmiles.error
    async def setmiles_error(self, interaction: discord.Interaction, error):
        msg = (
            "You need the **Manage Server** permission to use this command."
            if isinstance(error, app_commands.MissingPermissions)
            else f"An error occurred: {error}"
        )
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)

    @tasks.loop(
        time=datetime.time(hour=RECAP_HOUR, minute=0, tzinfo=datetime.timezone.utc)
    )
    async def weekly_recap(self):
        if datetime.datetime.now(tz=datetime.timezone.utc).weekday() != RECAP_DAY:
            return

        channel_id = config.store.get("NOTIFY_CHANNEL_ID")
        if not channel_id:
            return

        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            return

        embed = _build_embed()
        embed.title = f"📊 Weekly Recap — {embed.title}"
        await channel.send(embed=embed)

    @weekly_recap.before_loop
    async def before_recap(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Leaderboard(bot))
