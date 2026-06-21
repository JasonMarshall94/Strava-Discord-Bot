import time
import logging
import datetime

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

import config

logger = logging.getLogger(__name__)

DEFAULT_MESSAGE = (
    "🏃 **{display_name}** just logged a run! *{activity_name}* — "
    "**{distance} mi** in **{time}** ({pace} /mi)"
)


def _format_duration(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{h}h {m}m" if h else f"{m}m {s}s"


def _format_pace(distance_m: float, moving_time_s: int) -> str:
    if distance_m <= 0:
        return "—"
    pace_s = moving_time_s / (distance_m / 1609.344)
    m, s = divmod(int(pace_s), 60)
    return f"{m}:{s:02d}"


def _activity_key(activity: dict) -> tuple[str, str, int, int]:
    """Returns (firstname, lastname, moving_time, distance_m) for deduplication."""
    athlete = activity.get("athlete", {})
    return (
        athlete.get("firstname", ""),
        athlete.get("lastname", ""),
        int(activity.get("moving_time", 0)),
        int(activity.get("distance", 0)),
    )


class Strava(commands.Cog):
    """Polls the Strava club activity feed and posts run notifications."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._silent_poll_needed = True   # startup: log real miles, no notifications
        self._zero_miles_poll_needed = False  # post-setmiles: log 0 miles, no notifications
        self.poll_activities.start()

    def cog_unload(self):
        self.poll_activities.cancel()

    def request_silent_poll(self):
        """Call after wiping run_log: next poll deduplicates without adding miles or notifying."""
        self._zero_miles_poll_needed = True

    # ------------------------------------------------------------------
    # Polling task
    # ------------------------------------------------------------------

    @tasks.loop(minutes=5)
    async def poll_activities(self):
        if config.store.get("SILENT_POLL_REQUESTED") == "1":
            config.store.set("SILENT_POLL_REQUESTED", "0")
            self._zero_miles_poll_needed = True

        token = await self._get_valid_token()
        if not token:
            logger.warning("No valid Strava token — skipping poll. Run `python authenticate.py`.")
            return

        if not config.STRAVA_CLUB_ID:
            logger.warning("STRAVA_CLUB_ID not set — skipping poll.")
            return

        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {token['access_token']}"}
            async with session.get(
                f"{config.STRAVA_API_BASE}/clubs/{config.STRAVA_CLUB_ID}/activities",
                headers=headers,
                params={"per_page": 30},
            ) as resp:
                if resp.status != 200:
                    logger.error(f"Club activities fetch failed: {resp.status}")
                    return
                activities = await resp.json()

        silent = self._silent_poll_needed or self._zero_miles_poll_needed
        zero_miles = self._zero_miles_poll_needed
        self._silent_poll_needed = False
        self._zero_miles_poll_needed = False

        for activity in activities:
            if activity.get("type") != "Run":
                continue

            firstname, lastname, moving_time, distance_m = _activity_key(activity)
            if not firstname:
                continue

            if config.store.has_activity(firstname, lastname, moving_time, distance_m):
                continue

            distance_miles = round(distance_m / 1609.344, 2)
            # Post-setmiles poll: log 0 miles so runs are deduplicated but don't inflate the total
            config.store.log_activity(firstname, lastname, moving_time, distance_m, 0.0 if zero_miles else distance_miles)

            if not silent:
                await self._post_notification(activity, firstname, lastname, distance_m)

    @poll_activities.before_loop
    async def before_poll(self):
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    async def _get_valid_token(self) -> dict | None:
        token = config.store.get_bot_token()
        if not token:
            return None
        if token["expires_at"] < int(time.time()) + 60:
            token = await self._refresh_token(token["refresh_token"])
        return token

    async def _refresh_token(self, refresh_token: str) -> dict | None:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                config.STRAVA_TOKEN_URL,
                data={
                    "client_id": config.STRAVA_CLIENT_ID,
                    "client_secret": config.STRAVA_CLIENT_SECRET,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            ) as resp:
                if resp.status != 200:
                    logger.error("Strava token refresh failed.")
                    return None
                token_data = await resp.json()

        config.store.set_bot_token(
            access_token=token_data["access_token"],
            refresh_token=token_data["refresh_token"],
            expires_at=token_data["expires_at"],
        )
        logger.info("Strava token refreshed successfully.")
        return token_data

    # ------------------------------------------------------------------
    # Notification posting
    # ------------------------------------------------------------------

    async def _post_notification(
        self,
        activity: dict,
        firstname: str,
        lastname: str,
        distance_m: float,
    ):
        channel_id = config.store.get("NOTIFY_CHANNEL_ID")
        if not channel_id:
            logger.warning("NOTIFY_CHANNEL_ID not set — skipping notification.")
            return

        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            logger.warning(f"Channel {channel_id} not found.")
            return

        member = config.store.get_member_by_strava_name(firstname, lastname)
        custom_on = config.store.get("CUSTOM_MESSAGES_ENABLED", "0") == "1"

        if member:
            display_name = member["display_name"]
            message_template = member["message"] if custom_on else DEFAULT_MESSAGE
        else:
            display_name = f"{firstname} {lastname}".strip()
            message_template = DEFAULT_MESSAGE

        moving_time = activity.get("moving_time", 0)
        distance_miles = round(distance_m / 1609.344, 2)

        template_vars = {
            "display_name": display_name,
            "activity_name": activity.get("name", "Unnamed activity"),
            "distance": distance_miles,
            "time": _format_duration(moving_time),
            "pace": _format_pace(distance_m, moving_time),
            "strava_url": f"https://www.strava.com/clubs/{config.STRAVA_CLUB_ID}",
        }

        try:
            message_text = message_template.format_map(template_vars)
        except (KeyError, ValueError):
            message_text = DEFAULT_MESSAGE.format_map(template_vars)

        elevation = activity.get("total_elevation_gain", 0)
        stats = f"{distance_miles} mi · {template_vars['time']} · {template_vars['pace']} /mi"
        if elevation:
            stats += f" · ↑{int(elevation)} m"

        embed = discord.Embed(
            title=activity.get("name", "New Run"),
            url=template_vars["strava_url"],
            color=discord.Color.orange(),
        )
        embed.description = f"{message_text}\n\n{stats}"
        embed.set_footer(text="via Strava")

        await channel.send(embed=embed)
        logger.info(f"Posted run notification for {firstname} {lastname}")

    # ------------------------------------------------------------------
    # Slash commands
    # ------------------------------------------------------------------

    strava_group = app_commands.Group(name="strava", description="Strava commands")

    @strava_group.command(name="debug", description="Show recent club member names from Strava (admin only)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def debug(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        token = await self._get_valid_token()
        if not token or not config.STRAVA_CLUB_ID:
            await interaction.followup.send("No token or club ID set.", ephemeral=True)
            return

        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {token['access_token']}"}
            async with session.get(
                f"{config.STRAVA_API_BASE}/clubs/{config.STRAVA_CLUB_ID}/activities",
                headers=headers,
                params={"per_page": 30},
            ) as resp:
                activities = await resp.json()

        if not activities:
            await interaction.followup.send("No activities returned from Strava.", ephemeral=True)
            return

        seen = set()
        lines = []
        for a in activities:
            athlete = a.get("athlete", {})
            fn = athlete.get("firstname", "?")
            ln = athlete.get("lastname", "?")
            key = (fn, ln)
            if key not in seen:
                seen.add(key)
                lines.append(f"`firstname: {fn}` `lastname: {ln}`")

        await interaction.followup.send(
            f"**Unique athletes in recent club feed ({len(lines)} found):**\n" + "\n".join(lines),
            ephemeral=True,
        )

    @strava_group.command(name="test", description="Send a test run notification to the configured channel (admin only)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def test(self, interaction: discord.Interaction):
        channel_id = config.store.get("NOTIFY_CHANNEL_ID")
        if not channel_id:
            await interaction.response.send_message(
                "No notification channel set. Use `/notify setchannel` first.",
                ephemeral=True,
            )
            return

        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            await interaction.response.send_message(
                "Notification channel not found.", ephemeral=True
            )
            return

        fake_activity = {
            "name": "Test Run",
            "type": "Run",
            "distance": 8046.72,   # 5 miles in meters
            "moving_time": 2550,   # 42m 30s
            "total_elevation_gain": 42,
        }
        fake_athlete = {"firstname": "Test", "lastname": "Runner"}

        await self._post_notification(fake_activity, "Test", "Runner", fake_activity["distance"])
        await interaction.response.send_message(
            f"Test notification sent to {channel.mention}.", ephemeral=True
        )

    @strava_group.command(name="status", description="Check the bot's Strava connection status")
    async def status(self, interaction: discord.Interaction):
        token = config.store.get_bot_token()
        if not token:
            await interaction.response.send_message(
                "❌ No Strava token found. Run `python authenticate.py` to connect.",
                ephemeral=True,
            )
            return

        expires_at = token["expires_at"]
        if expires_at < int(time.time()):
            status_text = "⚠️ Token expired — will refresh on next poll."
        else:
            status_text = "✅ Connected"

        embed = discord.Embed(title="Strava Connection Status", color=discord.Color.orange())
        embed.add_field(name="Status", value=status_text, inline=False)
        embed.add_field(name="Club ID", value=config.STRAVA_CLUB_ID or "Not set", inline=True)
        embed.add_field(name="Token expires", value=f"<t:{expires_at}:R>", inline=True)
        embed.add_field(name="Poll interval", value="Every 5 minutes", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Strava(bot))
