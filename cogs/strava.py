import logging
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
import config

logger = logging.getLogger(__name__)


class Strava(commands.Cog):
    """Strava integration commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _store(self):
        return config.store

    strava_group = app_commands.Group(name="strava", description="Strava commands")

    @strava_group.command(name="connect", description="Link your Strava account")
    async def connect(self, interaction: discord.Interaction):
        auth_url = (
            f"{config.STRAVA_AUTH_URL}"
            f"?client_id={config.STRAVA_CLIENT_ID}"
            f"&redirect_uri={config.STRAVA_REDIRECT_URI}"
            f"&response_type=code"
            f"&scope=read,activity:read_all"
            f"&state={interaction.user.id}"
        )
        embed = discord.Embed(
            title="Connect Strava",
            description="Click the link below to authorize CGRC Bot to access your Strava data.",
            color=discord.Color.orange(),
        )
        embed.add_field(name="Authorization URL", value=f"[Click here to connect]({auth_url})", inline=False)
        embed.set_footer(text="Your data is only used within this server.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @strava_group.command(name="profile", description="View your Strava profile")
    async def profile(self, interaction: discord.Interaction):
        token = self._store().get_strava_token(interaction.user.id)
        if not token:
            await interaction.response.send_message(
                "You haven't connected your Strava account yet. Use `/strava connect` first.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {token['access_token']}"}
            async with session.get(f"{config.STRAVA_API_BASE}/athlete", headers=headers) as resp:
                if resp.status != 200:
                    await interaction.followup.send("Failed to fetch Strava profile.", ephemeral=True)
                    return
                athlete = await resp.json()

        embed = discord.Embed(
            title=f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}",
            url=f"https://www.strava.com/athletes/{athlete['id']}",
            color=discord.Color.orange(),
        )
        if athlete.get("profile"):
            embed.set_thumbnail(url=athlete["profile"])
        embed.add_field(name="Location", value=athlete.get("city") or "N/A", inline=True)
        embed.add_field(name="Followers", value=athlete.get("follower_count", 0), inline=True)
        embed.add_field(name="Following", value=athlete.get("friend_count", 0), inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @strava_group.command(name="activities", description="List your recent Strava activities")
    @app_commands.describe(count="Number of activities to show (max 10)")
    async def activities(self, interaction: discord.Interaction, count: int = 5):
        token = self._store().get_strava_token(interaction.user.id)
        if not token:
            await interaction.response.send_message(
                "You haven't connected your Strava account yet. Use `/strava connect` first.",
                ephemeral=True,
            )
            return

        count = max(1, min(count, 10))
        await interaction.response.defer(ephemeral=True)

        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {token['access_token']}"}
            params = {"per_page": count}
            async with session.get(
                f"{config.STRAVA_API_BASE}/athlete/activities",
                headers=headers,
                params=params,
            ) as resp:
                if resp.status != 200:
                    await interaction.followup.send("Failed to fetch activities.", ephemeral=True)
                    return
                activities = await resp.json()

        if not activities:
            await interaction.followup.send("No recent activities found.", ephemeral=True)
            return

        embed = discord.Embed(title="Recent Strava Activities", color=discord.Color.orange())
        for act in activities:
            distance_mi = round(act.get("distance", 0) / 1609.344, 2)
            moving_time = act.get("moving_time", 0)
            minutes, seconds = divmod(moving_time, 60)
            hours, minutes = divmod(minutes, 60)
            time_str = f"{hours}h {minutes}m" if hours else f"{minutes}m {seconds}s"
            embed.add_field(
                name=act.get("name", "Unnamed activity"),
                value=f"{act.get('type', 'Activity')} · {distance_mi} mi · {time_str}",
                inline=False,
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

    def store_token(self, user_id: int, token_data: dict):
        """Persist Strava OAuth token and athlete ID mapping."""
        self._store().set_strava_token(
            discord_user_id=user_id,
            access_token=token_data["access_token"],
            refresh_token=token_data["refresh_token"],
            expires_at=token_data.get("expires_at", 0),
        )
        athlete_id = token_data.get("athlete", {}).get("id")
        if athlete_id:
            self._store().set_athlete_map(athlete_id, user_id)
        logger.info(f"Stored Strava token for user {user_id}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Strava(bot))
