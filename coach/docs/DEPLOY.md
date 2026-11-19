# Deploy

The server is one Docker container and needs a persistent disk (`/data`). Notes, the database and session tokens live on that disk; if the disk is lost, everything is lost.

Two requirements:

1. **An HTTPS address.** Claude and ChatGPT connectors only accept HTTPS.
2. **A single replica.** SQLite and MCP sessions are designed for one process. Scale vertically first; see the scaling notes at the end.

## Option A: Railway (recommended, works from a phone)

Railway builds from the GitHub repo and gives you a volume and an HTTPS address. It needs the paid Hobby plan; check railway.com/pricing for the current price.

1. [railway.com](https://railway.com) → sign in with GitHub → **New Project** → **Deploy from GitHub repo** → `hfgunay/coach-brain`.
2. Service **Settings**:
   - **Root Directory**: leave empty (repo root). The image also contains the avenoxbeyin engine (`scripts/`, `template/`).
   - Nothing else: the root `railway.json` tells Railway the Dockerfile path (`coach/Dockerfile`) and the health check (`/health`). Don't set `RAILWAY_DOCKERFILE_PATH`.
3. Right-click the service (long-press on a phone) → **Attach Volume** → mount path `/data`.
4. **Settings → Networking → Generate Domain**. Copy the address, e.g. `https://coach-production.up.railway.app`.
5. **Variables**:

   | Variable | Value |
   | --- | --- |
   | `COACH_INVITE_CODES` | A long, unguessable code (comma-separate several) |
   | `RAILWAY_RUN_UID` | `0` (so the process can write to the root-owned volume; the image normally runs as a non-root user) |
   | `COACH_PUBLIC_URL` | Optional. Defaults to the Railway domain; set it when you use your own domain. `https://` is added if missing |

   Optional, for the reminder bot:

   | Variable | Value |
   | --- | --- |
   | `COACH_TELEGRAM_TOKEN` | Token from @BotFather → `/newbot`. **Never share it** or paste it anywhere but Railway Variables. |
   | `COACH_MORNING_TIME`, `COACH_EVENING_TIME`, `COACH_TIMEZONE` | Defaults for new links (`09:00`, `22:00`, `Europe/Istanbul`). Each student changes their own from the bot. |

   The server sets the Telegram webhook itself on startup (the address must be https). Only `COACH_*` names are read; the old `KOC_*` names are ignored.

6. After the redeploy, open `<address>/health` in a browser. You should see `{"status":"ok"}`.
7. Give the student the **connector address** (`<address>/mcp`) and the **invite code**, then the [Connect from a phone](CONNECT.md) guide ([Türkçe](CONNECT.tr.md)).

### Your own domain (optional)

E.g. `coach.example.com`: Railway → Networking → Custom Domain, add the CNAME record at your DNS provider, then set `COACH_PUBLIC_URL` to the new address.

> Changing the address changes the OAuth details. Connectors added earlier must be removed and added again with the new address. Attach the domain before users arrive.

## Option B: Your own server (VPS) with Docker

```bash
git clone https://github.com/hfgunay/coach-brain && cd coach-brain
docker build -f coach/Dockerfile -t coach .   # from the repo root, so the engine goes into the image
docker run -d --name coach --restart unless-stopped \
  -p 127.0.0.1:8000:8000 -v coach-data:/data \
  -e COACH_PUBLIC_URL=https://coach.example.com \
  -e COACH_INVITE_CODES=a-long-random-code \
  coach
```

Put Caddy in front for HTTPS (`/etc/caddy/Caddyfile`):

```
coach.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

## Backups

Everything is under `/data`: `coach.sqlite3` (accounts, tokens), `vaults/` (the students' avenoxbeyin vaults) and `state/` (the engine's rebuildable index). `vaults/` is what matters. Take a backup at least weekly:

```bash
sqlite3 /data/coach.sqlite3 ".backup /data/backup.sqlite3"
tar czf coach-backup-$(date +%F).tgz -C /data backup.sqlite3 vaults
```

Railway's Hobby plan has no volume backups, so an off-site nightly copy (e.g. to Cloudflare R2) is planned before real users arrive. Students with Obsidian sync also keep a copy of their notes on their iPad.

## Admin tasks

Password reset (there is no email flow):

```bash
python -c "
from coach.db import DB, hash_password; from pathlib import Path
db = DB(Path('/data/coach.sqlite3'))
db.x('UPDATE users SET pw_hash=? WHERE email=?', (hash_password('new-temporary-password'), 'student@example.com'))"
```

To revoke all of a user's connections: `DELETE FROM oauth_tokens WHERE user_id = '<id>'`.

## Upgrading from the first (Turkish-named) version

On startup the server renames `calisma_kocu.sqlite3` to `coach.sqlite3` and `oturum.key` to `session.key`, migrates Telegram links and replaces the vault's `.agents/skills/calisma-kocu` with `study-coach`. Routes changed: `/yukle` → `/upload`, `/hesap/...` → `/account/...`, `/saglik` → `/health`. Bot commands are now English (`/today`, `/time`, `/mute`, `/unmute`, `/unlink`). Connectors pick up the new tool names on their own.

## avenoxbeyin updates

Vaults are installed with the engine in the image on first use. After a redeploy new users get the new version; existing vaults upgrade with the engine's own path: `python3 beyin.py update` inside the vault (see SETUP-V3.md at the root). The coach skill is checked on every request and rewritten into the vault if it changed.

## Scaling notes

1. Grow the single instance vertically first.
2. Then add region cells (e.g. an EU cell for GDPR/KVKK), each its own copy of this container.
3. Only then a router plus Postgres for accounts. Vaults stay as files on each cell's disk.
