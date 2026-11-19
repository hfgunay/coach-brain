# Obsidian sync (optional)

The coach doesn't need Obsidian. These steps are for students who want to see the coach's notes in **Obsidian** on an iPad, browse the link graph and add their own notes.

## How it works

- Each student has an avenoxbeyin vault on the server (a plain Markdown folder). The coach writes notes there.
- Obsidian keeps a copy of that folder on the iPad. The **Remotely Save** plugin syncs the two over WebDAV.
- Links like `[[Digoxin]]` are plain text in the file. Obsidian draws them as a graph; avenoxbeyin reads the same links.
- A note you write in Obsidian shows up in the coach's search after the next sync.

Obsidian doesn't run on the server. It is only the viewer and editor on the iPad.

## Setup (iPad or iPhone, once)

1. **Get a password.** In Safari open `<server address>/account/obsidian` and sign in with your coach account. The page shows a **Server Address**, **Username** and a one-time **Password**. Keep the page open or take a screenshot.
2. Install **Obsidian** from the App Store, open it, **Create new vault** → name: `Study` → location: **On my iPad** (not iCloud).
3. Obsidian → **Settings** → **Community plugins** → **Turn on community plugins** → **Browse** → search `Remotely Save` → **Install** → **Enable**.
4. **Settings → Remotely Save**:
   - **Remote Service**: `Webdav`
   - **Server Address**, **Username**, **Password**: the values from step 1
   - **Auth Type**: `basic`
   - **Depth Header Sent To Servers**: `auto detect`
   - **Check Connectivity** → you should see "connected".
   - **Schedule For Auto Run**: `every 5 minutes`, **Run Once On Start Up Automatically**: on.
5. Tap the sync icon on the left edge. `🔮 850-Companion/` (profile, rules, where you left off), `notes/`, `tasks/` and `Attachments/` (your uploaded question photos) arrive. The engine's working files (`beyin.py`, hidden folders) are left out on purpose.

## Good to know

- If you lose the password, repeat step 1; a new one is created and the old one stops working.
- If the coach and Obsidian edit the same note in the same minute, the last save wins. Sync after the coach session.
- Photos under `Attachments/` appear in notes as `![[Attachments/...]]`.
- Don't put large PDFs and images into the vault by hand; there is no per-user disk limit yet and sync slows down.
