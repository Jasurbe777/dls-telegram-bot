# Dream League Signup Telegram Bot

This repository contains a Telegram bot implementing the user and admin flows you described.

Quick setup (Ubuntu, VS Code):

1. Open the workspace in VS Code.
2. Edit `config.json` and set `bot_token` and `admin_id` (your Telegram id) and adjust links/teams.

3. Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

4. Run the bot:

```bash
python3 main.py
```

Notes and important details:
- For automatic Telegram channel membership checks the bot must be added as an administrator to the Telegram channel.
- YouTube and Instagram subscriptions cannot be reliably checked via the Telegram Bot API; the bot asks for a screenshot as proof.
- Admin receives submissions (profile screenshot, username, team) at `admin_id` from `config.json`.

If you want, I can:
- Add an admin command to manage teams from chat.
- Add Dockerfile / systemd unit to run this as a service.
- Harden validations or persist more fields in the DB.
