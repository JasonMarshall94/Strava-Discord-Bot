# Strava Club Discord Bot

A Discord bot that monitors a Strava running club and posts notifications whenever a member logs a run. Includes an annual mileage leaderboard, weekly recap, and a local web admin dashboard.

Built for clubs with a yearly distance goal.

---

## Features

- Run notifications posted to a Discord channel when a member logs a run on Strava
- Optional per-member custom notification messages
- `/leaders` command with annual mileage leaderboard, sorted best to worst
- Crown 👑 when a member hits the 100-mile goal
- Automatic weekly recap every Monday at 8:00 UTC
- Web admin dashboard for managing members, messages, and settings
- All secrets stored in an encrypted local SQLite database

---

## Requirements

- Python 3.11+
- A Discord server where you have admin access
- A Strava account that is a member of the club you want to monitor
- A Strava API application
- A Raspberry Pi (or any Linux machine) for hosting

---

## Setup

### 1. Create a Discord Bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **New Application** → give it a name
3. Go to **Bot** → enable **Server Members Intent** and **Message Content Intent**
4. Copy the bot token — you'll need it in step 5
5. Go to **OAuth2 → URL Generator**, select scopes: `bot` and `applications.commands`
6. Select permissions: `Send Messages`, `Embed Links`, `Read Message History`
7. Open the generated URL to invite the bot to your server

### 2. Create a Strava API Application

1. Go to [strava.com/settings/api](https://www.strava.com/settings/api)
2. Create an application — set **Authorization Callback Domain** to `localhost`
3. Note your **Client ID** and **Client Secret**
4. Find your **Club ID** from the URL of your club's Strava page (`strava.com/clubs/YOUR_CLUB_ID`)

### 3. Install on Your Raspberry Pi

```bash
git clone https://github.com/your-username/strava-club-bot.git cgrc-bot
cd cgrc-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Configure Club Members

```bash
cp members.example.json members.json
```

Edit `members.json` with your club members. Each member needs:
- A **display name** for the leaderboard
- Their **Strava first and last name** as shown in the API (e.g. `"Jason"` / `"M."`)
- A **custom message** template for run notifications

> **Tip:** Run `/strava debug` in Discord after setup to see how Strava names appear in the API.

Available message template variables:

| Variable | Description |
|---|---|
| `{display_name}` | Member's display name |
| `{activity_name}` | Strava activity title |
| `{distance}` | Distance in miles |
| `{time}` | Moving time (e.g. `28m 15s`) |
| `{pace}` | Pace per mile (e.g. `8:42`) |
| `{strava_url}` | Link to the Strava club page |

### 5. Run the Setup Script

```bash
python3 setup_db.py
```

Prompts for your Discord token, guild ID, and Strava credentials. Also seeds members from `members.json`.

### 6. Authorize with Strava

```bash
python3 authenticate.py
```

Opens a browser to authorize the bot's Strava account. Tokens are stored and refreshed automatically.

### 7. Run the Bot

```bash
python3 main.py
```

Then in Discord, run `/notify setchannel #your-channel` to set where notifications are posted.

### 8. Set Initial Mileage (if your year is already in progress)

```bash
/setmiles Jason 24.5
/setmiles Brad 18.2
```

### 9. Keep It Running with systemd

Create `/etc/systemd/system/cgrc-bot.service`:

```ini
[Unit]
Description=CGRC Discord Bot
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=/home/pi/cgrc-bot
ExecStart=/home/pi/cgrc-bot/venv/bin/python3 main.py
Restart=always
RestartSec=10
User=pi

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable cgrc-bot
sudo systemctl start cgrc-bot
```

---

## Web Dashboard

A local admin dashboard runs on port 8000, accessible from any device on the same network:

```
http://your-pi.local:8000
```

### Setup

```bash
python3 setup_dashboard.py
```

Create `/etc/systemd/system/cgrc-dashboard.service`:

```ini
[Unit]
Description=CGRC Admin Dashboard
After=network.target

[Service]
WorkingDirectory=/home/pi/cgrc-bot
ExecStart=/home/pi/cgrc-bot/venv/bin/python3 run_dashboard.py
Restart=always
RestartSec=10
User=pi

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable cgrc-dashboard
sudo systemctl start cgrc-dashboard
```

The dashboard lets you manage members, update custom messages, set mileage, and toggle settings — all without touching the command line.

---

## Commands

### Everyone
| Command | Description |
|---|---|
| `/leaders` | Show the annual miles leaderboard |
| `/ping` | Check bot latency |
| `/help` | Show available commands |

### Admin Only
| Command | Description |
|---|---|
| `/notify setchannel` | Set the channel for run notifications and weekly recaps |
| `/notify custommessages on\|off` | Toggle custom per-member notification messages |
| `/setmiles [name] [miles]` | Set a member's total miles for the year |
| `/strava status` | Check the bot's Strava connection |
| `/strava test` | Send a test run notification |
| `/strava debug` | Show recent athlete names from the Strava club feed |

---

## Moving to a Different Discord Server

Run this to update the server without losing any member or mileage data:

```bash
python3 update_server.py
```

Then restart the bot and run `/notify setchannel` in the new server.

---

## Security Notes

- `cgrc.db` — encrypted SQLite database, never commit this
- `secret.key` — master encryption key, back this up and never commit it
- `members.json` — your club's member data, never commit this

All three are covered by `.gitignore`.

---

## License

MIT
