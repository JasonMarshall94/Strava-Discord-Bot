# Strava Club Discord Bot

A Discord bot that monitors a Strava running club and posts notifications whenever a member logs a run. Includes an annual mileage leaderboard and weekly recap — built for clubs with a yearly distance goal.

## Features

- **Run notifications** — posts to a Discord channel whenever a club member logs a run on Strava
- **Custom messages** — optional per-member custom notification text
- **Mileage leaderboard** — `/leaders` command shows everyone's annual miles, sorted best to worst
- **Weekly recap** — automatic leaderboard post every Monday at 8:00 UTC
- **Progress tracking** — crown 👑 when a member hits the 100-mile goal; miles keep counting past 100
- **Encrypted storage** — all tokens and secrets stored in an encrypted local SQLite database

---

## Prerequisites

- Python 3.11+
- A Discord server where you have admin access
- A Strava account that is a member of the club you want to monitor
- A Strava API application

---

## Setup

### 1. Create a Discord Bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **New Application** and give it a name
3. Go to **Bot** → enable **Server Members Intent** and **Message Content Intent**
4. Copy the bot token — you'll need it in step 5
5. Go to **OAuth2 → URL Generator**, select scopes: `bot` and `applications.commands`
6. Select permissions: `Send Messages`, `Embed Links`, `Read Message History`
7. Open the generated URL in your browser to invite the bot to your server

### 2. Create a Strava API Application

1. Go to [strava.com/settings/api](https://www.strava.com/settings/api)
2. Create an application — set the **Authorization Callback Domain** to `localhost`
3. Note your **Client ID** and **Client Secret**
4. Find your **Club ID** — go to your club's page on Strava and copy the number from the URL (`strava.com/clubs/YOUR_CLUB_ID`)

### 3. Clone the Repo and Install Dependencies

```bash
git clone https://github.com/your-username/strava-club-bot.git
cd strava-club-bot
pip install -r requirements.txt
```

### 4. Configure Your Club Members

```bash
cp members.example.json members.json
```

Edit `members.json` with your club members. For each member you need:
- Their **Strava athlete ID** (found in the URL of their Strava profile: `strava.com/athletes/XXXXXXX`)
- A **display name** used in the leaderboard
- Their **Strava first and last name** as shown in the API (first name in full, last name as initial + period, e.g. `"Jason"` / `"M."`)
- A **custom message** template (used when custom messages are enabled)

Available template variables for messages:
| Variable | Description |
|---|---|
| `{display_name}` | Member's display name |
| `{activity_name}` | Strava activity title |
| `{distance}` | Distance in miles |
| `{time}` | Moving time (e.g. `28m 15s`) |
| `{pace}` | Average pace per mile (e.g. `8:42`) |
| `{strava_url}` | Link to the Strava club page |

> **Tip:** To find a member's Strava first/last name as the API sees it, start the bot and run `/strava debug` in Discord — it shows all unique athlete names from the recent club feed.

### 5. Run the Setup Script

```bash
python setup_db.py
```

This will prompt you for:
- Discord bot token
- Discord guild/server ID
- Strava Client ID and Client Secret
- Strava Club ID

It will also seed your club members from `members.json`.

### 6. Authorize the Bot with Strava

```bash
python authenticate.py
```

This opens your browser to authorize the bot's Strava account. After approving, tokens are stored automatically and refreshed by the bot at runtime.

### 7. Start the Bot

```bash
python main.py
```

### 8. Configure the Notification Channel

In Discord, run:
```
/notify setchannel #your-channel
```

### 9. Set Initial Mileage (Optional)

If your club year is already in progress, set each member's current mileage:
```
/setmiles Jason 24.5
/setmiles Brad 18.2
```

The bot tracks new runs on top of these baselines.

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
| `/strava status` | Check the bot's Strava connection status |
| `/strava test` | Send a test run notification |
| `/strava debug` | Show recent athlete names from the Strava club feed |

---

## Hosting

The bot needs to run 24/7. Some options:

| Option | Cost | Notes |
|---|---|---|
| DigitalOcean / Linode VPS | ~$4–6/mo | Most control |
| Railway | Free tier available | Simple git-based deploys |
| Fly.io | Free tier available | Good for persistent processes |
| Raspberry Pi | Free | Works well for small bots |

> **Note:** The bot uses outbound HTTP calls to Strava only — no inbound webhooks required. A public IP or domain is not needed.

To keep the bot running as a background service on a Linux VPS, create a systemd unit:

```ini
[Unit]
Description=Strava Club Discord Bot
After=network.target

[Service]
WorkingDirectory=/path/to/strava-club-bot
ExecStart=/usr/bin/python3 main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

---

## Moving to a Different Discord Server

To move the bot to a new server without losing any miles or member data, run:

```bash
python update_server.py
```

This updates only the Discord guild ID and clears the notification channel. All mileage, member records, and Strava config are untouched.

After running it, restart the bot and run `/notify setchannel` in the new server.

To invite the bot to the new server first:
1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Select your bot → OAuth2 → URL Generator
3. Select scopes: `bot` and `applications.commands`
4. Select permissions: `Send Messages`, `Embed Links`, `Read Message History`
5. Open the generated URL and select the new server

---

## Security Notes

- `cgrc.db` — encrypted SQLite database, never commit this
- `secret.key` — master encryption key, back this up securely and never commit it
- `members.json` — your club's member data, never commit this

All three are covered by `.gitignore`.

---

## License

MIT
