# Study Coach · a remote MCP server that makes avenoxbeyin usable from a phone

A second brain for exam and study work: any exam or course where you solve questions. Students use their own Claude subscription and add this server as a **custom connector**. The server never calls a language model API; its only cost is hosting.

**The memory engine is not in this folder. It is avenoxbeyin at the repo root.** For each user the server installs a real avenoxbeyin V3 vault with the official `scripts/install_v3.py` and maps the MCP tools onto that vault's own `beyin.py` commands. Search, note and task writes, revision and sha conflict checks, review dates (`review_at`), task due dates (`due_at`), Companion files, session receipts and learning candidates all come from the engine. There is no separate memory, plan or mistake-log logic here.

The user-facing text (sign-in pages, upload page, Telegram bot) is in English and Turkish (`coach/i18n.py`). The coach itself always answers in the student's language.

```
iPhone / iPad                         Server (single container)
┌──────────────┐  MCP + OAuth   ┌─────────────────────────────────────────────┐
│ Claude app   │ ─────────────► │ /mcp      tools ──► beyin.py --json <cmd>    │
└──────────────┘                │ /authorize, /token, /register (OAuth 2.1)   │
┌──────────────┐  HTTPS form    │ /upload   question photos ──► Attachments/  │
│ Safari       │ ─────────────► │ /account/ sign-in, Obsidian password        │
└──────────────┘                │                                             │
┌──────────────┐  WebDAV        │ /dav/     the user's own vault              │
│ Obsidian +   │ ◄────────────► │                                             │
│ Remotely Save│                │ /data/vaults/<id>/   avenoxbeyin vault      │
└──────────────┘                │ /data/state/<id>/    engine index and locks │
┌──────────────┐  webhook       │ /data/coach.sqlite3  accounts + OAuth       │
│ Telegram bot │ ◄────────────► │ /telegram/webhook                           │
└──────────────┘                └─────────────────────────────────────────────┘
```

## Where each need is met

| Need | Source |
| --- | --- |
| Profile, rules, where we left off, open threads | `🔮 850-Companion/` in the vault (Core, Kurallar, Last-Session, Threads) |
| Start-of-chat context, due reviews and tasks | The vault's SessionStart hook (`.claude/scripts/beyin_v3_hook.py`) |
| Lecture notes, textbook PDFs, Word files | The repo's Yakala capture inbox (`📥 000-Inbox/Yakala/`). The server writes the text page by page as plain Markdown under `sources/<document>/`, so the engine's own search finds it; the coach writes notes as topics are studied |
| A missed question, a topic note | `note-create`; new notes go under `notes/` or `knowledge/` per the repo rules, the coach picks the folder |
| When to review | The note's `review_at` field; the engine returns it as "Due reviews" |
| Study plan | Tasks via `task-create`, with `project` and `due_at` |
| Coaching behaviour | Only the coach skill: [coach/skill/SKILL.md](coach/skill/SKILL.md) (installed in the vault as `.agents/skills/study-coach/`) |

## Tools

| Tool | beyin command |
| --- | --- |
| `start_session` | SessionStart hook context + session id |
| `read_instructions` | The vault's AGENTS.md, the beyin skill and the study-coach skill |
| `search_vault` | `context` |
| `read_note`, `create_note`, `edit_note` | `note-read`, `note-create`, `note-edit` |
| `create_task`, `update_task` | `task-create`, `task-update` |
| `save_receipt` | `receipt` |
| `learning_candidate` | `learn` |
| `vault_status`, `recent_receipts` | `triage`, `recap` |
| `list_captures`, `read_capture`, `finish_capture` | `yakala liste`, `yakala isle` (PDF/Word text), `yakala bitti`: uploaded study material |
| `list_attachments`, `show_attachment` | Server-side: shows photos from `/upload` or Telegram (Claude can't pass images as tool arguments) |

The `study_coach` MCP prompt returns the coach skill text.

## Reminder bot (optional)

With `COACH_TELEGRAM_TOKEN` set the server runs a Telegram bot. The bot never calls a language model.

- **Morning** (default 09:00): due reviews (`review_at`) from the engine's `triage` and tasks under `tasks/` that are due (`due_at`).
- **Evening** (default 22:00): [✅ Done] [➡️ Tomorrow] for each due task. The button runs the engine's `task-update` with the revision check.
- **Inbox:** a photo sent to the bot lands in `Attachments/`; a PDF/Word file takes the same path as the upload page into Yakala and `sources/` (Bot API limit 20 MB).
- Commands: `/today`, `/time 09:00 22:00`, `/timezone Europe/Istanbul`, `/language en|tr`, `/mute`, `/unmute`, `/unlink`.
- Each student sets their own times and time zone; the env values are only defaults for new links.
- Linking: "Connect Telegram" on the upload page opens `t.me/<bot>?start=<code>` with a single-use code.

The core (`reminders.py`) is channel independent; Telegram is only the `telegram.py` adapter. Another channel (WhatsApp, our own app) implements the same `Channel` protocol; removing the env variable turns Telegram off.

## What belongs to the server

- OAuth 2.1 (DCR + PKCE), email and password accounts, invite codes, login rate limiting
- One vault per user, locked to that user (path traversal guarded)
- WebDAV (`/dav`) for Obsidian sync. Engine-managed files (`beyin.py`, `AGENTS.md`, `CLAUDE.md`, dot folders) are hidden and read-only.
- `/upload`: upload page for phones. Photos go to `Attachments/` (2000 px JPEG); PDF/Word/text (up to 100 MB) go through `beyin.py yakala ekle` into the inbox, with searchable page text.
- English and Turkish UI; the language comes from `?lang=`, then a cookie, then the browser's `Accept-Language`.

## Run locally

```bash
cd coach
python -m venv .venv && . .venv/bin/activate
pip install -e ".[test]"
python -m pytest -q                         # real vault install, OAuth, MCP, isolation, WebDAV, photos, Telegram
COACH_INVITE_CODES=test coach-server        # http://localhost:8000
```

The server finds the engine at the repo root (`coach/..`). If it lives elsewhere, point `COACH_ENGINE_DIR` at an avenoxbeyin checkout. Connecting Claude needs a public HTTPS address (e.g. `cloudflared tunnel --url http://localhost:8000`); pass it as `COACH_PUBLIC_URL`.

## Docs

- [Deploy](docs/DEPLOY.md): Railway (recommended) or Docker
- [Connect from a phone](docs/CONNECT.md) ([Türkçe](docs/CONNECT.tr.md)): the student's step-by-step guide
- [Obsidian sync](docs/OBSIDIAN.md): see the vault on an iPad (optional)
- [Coach skill](docs/COACH_SKILL.md): where the coach skill lives and how to change it

## Known limits

- Single container, single replica: SQLite, the login limiter and MCP sessions are local.
- An MCP chat can't start itself; proactive reminders come from the Telegram bot (optional).
- No password reset flow, payments or per-user disk quota.
- If Obsidian and the coach write the same note at once, the coach's write is protected by the engine's sha check; on the Obsidian side the last sync wins.
