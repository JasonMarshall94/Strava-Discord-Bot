"""
Aiohttp web server that runs alongside the Discord bot.

Routes
------
GET  /callback  — Strava OAuth callback: exchanges auth code for tokens,
                  stores them in the DB, and maps the Strava athlete ID to
                  the Discord user ID passed as the OAuth `state` parameter.

GET  /webhook   — Strava webhook subscription verification (hub.challenge).

POST /webhook   — Incoming Strava activity events. When a connected member
                  creates a Run activity it fetches the full activity from
                  the Strava API and posts a formatted notification embed to
                  the configured Discord channel.
"""

import logging
import time
import aiohttp
from aiohttp import web
import discord
import config
from member_messages import MEMBER_MESSAGES, DEFAULT_MESSAGE

logger = logging.getLogger(__name__)


def _format_duration(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{h}h {m}m" if h else f"{m}m {s}s"


def _format_pace(distance_m: float, moving_time_s: int) -> str:
    """Returns pace as M:SS /mi string, or '—' if distance is zero."""
    if distance_m <= 0:
        return "—"
    pace_s = moving_time_s / (distance_m / 1609.344)
    m, s = divmod(int(pace_s), 60)
    return f"{m}:{s:02d}"


class WebhookServer:
    def __init__(self, bot: discord.Client):
        self._bot = bot
        self._app = web.Application()
        self._app.router.add_get("/callback", self._handle_oauth_callback)
        self._app.router.add_get("/webhook", self._handle_webhook_verify)
        self._app.router.add_post("/webhook", self._handle_webhook_event)
        self._runner: web.AppRunner | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self, host: str = "0.0.0.0", port: int = 8080):
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, host, port)
        await site.start()
        logger.info(f"Webhook server listening on {host}:{port}")

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()

    # ------------------------------------------------------------------
    # OAuth callback  GET /callback?code=...&state=<discord_user_id>
    # ------------------------------------------------------------------

    async def _handle_oauth_callback(self, request: web.Request) -> web.Response:
        code = request.rel_url.query.get("code")
        state = request.rel_url.query.get("state")  # Discord user ID

        if not code or not state:
            return web.Response(status=400, text="Missing code or state parameter.")

        try:
            discord_user_id = int(state)
        except ValueError:
            return web.Response(status=400, text="Invalid state parameter.")

        async with aiohttp.ClientSession() as session:
            async with session.post(
                config.STRAVA_TOKEN_URL,
                data={
                    "client_id": config.STRAVA_CLIENT_ID,
                    "client_secret": config.STRAVA_CLIENT_SECRET,
                    "code": code,
                    "grant_type": "authorization_code",
                },
            ) as resp:
                if resp.status != 200:
                    logger.error(f"Strava token exchange failed: {resp.status}")
                    return web.Response(status=502, text="Strava token exchange failed.")
                token_data = await resp.json()

        athlete = token_data.get("athlete", {})
        strava_athlete_id = athlete.get("id")

        config.store.set_strava_token(
            discord_user_id=discord_user_id,
            access_token=token_data["access_token"],
            refresh_token=token_data["refresh_token"],
            expires_at=token_data["expires_at"],
        )

        if strava_athlete_id:
            config.store.set_athlete_map(strava_athlete_id, discord_user_id)
            logger.info(
                f"Linked Strava athlete {strava_athlete_id} → Discord user {discord_user_id}"
            )

        return web.Response(
            text="✅ Strava connected! You can close this tab and return to Discord.",
            content_type="text/plain",
        )

    # ------------------------------------------------------------------
    # Webhook verification  GET /webhook?hub.mode=subscribe&...
    # ------------------------------------------------------------------

    async def _handle_webhook_verify(self, request: web.Request) -> web.Response:
        mode = request.rel_url.query.get("hub.mode")
        token = request.rel_url.query.get("hub.verify_token")
        challenge = request.rel_url.query.get("hub.challenge")

        if mode == "subscribe" and token == config.STRAVA_WEBHOOK_VERIFY_TOKEN:
            logger.info("Strava webhook subscription verified.")
            return web.json_response({"hub.challenge": challenge})

        logger.warning("Webhook verification failed — token mismatch or wrong mode.")
        return web.Response(status=403, text="Forbidden")

    # ------------------------------------------------------------------
    # Webhook events  POST /webhook
    # ------------------------------------------------------------------

    async def _handle_webhook_event(self, request: web.Request) -> web.Response:
        # Always respond 200 immediately so Strava doesn't retry
        try:
            event = await request.json()
        except Exception:
            return web.Response(status=200)

        if (
            event.get("object_type") == "activity"
            and event.get("aspect_type") == "create"
        ):
            strava_athlete_id = event.get("owner_id")
            activity_id = event.get("object_id")
            if strava_athlete_id and activity_id:
                self._bot.loop.create_task(
                    self._process_activity(strava_athlete_id, activity_id)
                )

        return web.Response(status=200)

    # ------------------------------------------------------------------
    # Activity processing
    # ------------------------------------------------------------------

    async def _process_activity(self, strava_athlete_id: int, activity_id: int):
        discord_user_id = config.store.get_discord_user_for_athlete(strava_athlete_id)
        if discord_user_id is None:
            logger.debug(f"No Discord user mapped to Strava athlete {strava_athlete_id}")
            return

        token = config.store.get_strava_token(discord_user_id)
        if not token:
            logger.warning(f"No token for Discord user {discord_user_id}")
            return

        # Refresh token if expired
        if token["expires_at"] < int(time.time()):
            token = await self._refresh_token(discord_user_id, token["refresh_token"])
            if not token:
                return

        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {token['access_token']}"}
            async with session.get(
                f"{config.STRAVA_API_BASE}/activities/{activity_id}",
                headers=headers,
            ) as resp:
                if resp.status != 200:
                    logger.error(f"Failed to fetch activity {activity_id}: {resp.status}")
                    return
                activity = await resp.json()

        if activity.get("type") != "Run":
            return

        await self._post_notification(discord_user_id, activity)

    async def _refresh_token(self, discord_user_id: int, refresh_token: str) -> dict | None:
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
                    logger.error(f"Token refresh failed for user {discord_user_id}")
                    return None
                token_data = await resp.json()

        config.store.set_strava_token(
            discord_user_id=discord_user_id,
            access_token=token_data["access_token"],
            refresh_token=token_data["refresh_token"],
            expires_at=token_data["expires_at"],
        )
        return token_data

    async def _post_notification(self, discord_user_id: int, activity: dict):
        channel_id = config.store.get("NOTIFY_CHANNEL_ID")
        if not channel_id:
            logger.warning("NOTIFY_CHANNEL_ID not set — skipping notification.")
            return

        channel = self._bot.get_channel(int(channel_id))
        if channel is None:
            logger.warning(f"Channel {channel_id} not found.")
            return

        # Resolve display name
        member = channel.guild.get_member(discord_user_id)
        display_name = member.display_name if member else f"<@{discord_user_id}>"

        distance_m = activity.get("distance", 0)
        moving_time = activity.get("moving_time", 0)
        distance_mi = round(distance_m / 1609.344, 2)
        elevation = activity.get("total_elevation_gain", 0)

        template_vars = {
            "display_name": display_name,
            "activity_name": activity.get("name", "Unnamed activity"),
            "distance": distance_mi,
            "time": _format_duration(moving_time),
            "pace": _format_pace(distance_m, moving_time),
            "strava_url": f"https://www.strava.com/activities/{activity['id']}",
        }

        strava_athlete_id = config.store.get_athlete_id_for_discord_user(discord_user_id)
        template = MEMBER_MESSAGES.get(strava_athlete_id, DEFAULT_MESSAGE)
        try:
            message_text = template.format_map(template_vars)
        except (KeyError, ValueError):
            message_text = DEFAULT_MESSAGE.format_map(template_vars)

        embed = discord.Embed(
            title=activity.get("name", "New Run"),
            url=template_vars["strava_url"],
            color=discord.Color.orange(),
        )
        embed.description = message_text
        embed.add_field(name="Distance", value=f"{distance_mi} mi", inline=True)
        embed.add_field(name="Time", value=_format_duration(moving_time), inline=True)
        embed.add_field(name="Pace", value=f"{template_vars['pace']} /mi", inline=True)
        if elevation:
            embed.add_field(name="Elevation", value=f"{int(elevation)} m", inline=True)
        embed.set_footer(text="via Strava")

        if activity.get("start_date"):
            from datetime import datetime, timezone
            embed.timestamp = datetime.fromisoformat(
                activity["start_date"].replace("Z", "+00:00")
            )

        await channel.send(embed=embed)
        logger.info(f"Posted run notification for user {discord_user_id} in channel {channel_id}")
