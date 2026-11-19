# Connect from a phone (for students)

The easiest way: open the `/start` link you were given. That page creates your account and shows each step below, ticking them off as you go. This guide is the same steps in more detail.

You only do this once; it takes about 5 minutes. You'll be given two things:

- The **connector address**, e.g. `https://coach-production.up.railway.app/mcp`
- An **invite code**

The pages are in English or Turkish; use the switcher at the top of each page.

## With Claude (recommended)

Claude's free plan allows one custom connector. If you study long hours every day, a Pro plan hits the message limit later.

### 1. Add the connector

The easiest way is **Safari** on an iPhone or iPad. The connector then shows up in the Claude app by itself.

1. Open [claude.ai](https://claude.ai) in Safari and sign in.
2. Side menu → **Customize** → **Connectors** → **Add custom connector**.
3. **Name**: `Study Coach`. **URL**: the connector address you were given.
4. If it asks about authentication or OAuth: **Sign in now**, and **Register automatically** for the OAuth client.
5. **Add**, then **Connect**.
6. The Study Coach sign-in page opens. The first time, pick the **New account** tab: email, a password of at least 8 characters and the invite code. Tap **Create account and connect**.
7. You return to Claude and the connector shows "Connected".

> This email and password are not your Claude account; they are the account for your coach's memory. Write them down; you'll need them for the upload page and Obsidian too.

### 2. Set up a coach project (once)

1. In Claude: **Projects** → **New project** → name: `Study Coach`.
2. In the project **Instructions**, write: `In every chat, first run start_session from the Study Coach connector, then read_instructions.` The full coaching instructions live on the server, inside your vault.
3. If your plan has no Projects, that's fine: the server already sends the short instruction. Just write "start as my coach" in each new chat.

### 3. Upload page (once)

Claude can't pass files you drop into the chat to the connector. For question photos and study material (PDF, Word, text) you want to keep:

1. In Safari open `<server address>/upload` and sign in with your coach account (remembered for 90 days).
2. Share → **Add to Home Screen**. You now have an "Upload" icon on your phone.
3. Upload a photo of a question you missed or your lecture notes, then tell the coach "let's look at what I uploaded". The coach sees the photo and reads the PDF into your notes.

### 4. Telegram reminders (optional)

1. Tap **Connect Telegram** at the bottom of the upload page. Telegram opens; tap **Start**.
2. Every morning the bot sends the day's reviews and tasks; in the evening it asks with buttons whether each task is done.
3. You can also send a question photo or a PDF up to 20 MB straight to the bot.
4. Commands: `/time 08:00 22:00` changes the times, `/timezone Europe/Berlin` your time zone, `/language en` the language, `/mute` pauses it, `/unmute` resumes, `/today` shows today now.

### 5. Every day

1. Open a new chat in the **Study Coach** project in the Claude app.
2. In the message box, **+** → **Connectors** → make sure **Study Coach** is on.
3. Write "Hi, let's start". The coach reads where you left off, then suggests what to do today.
4. The first few times Claude asks permission to use a tool. **Always allow** stops it asking again.

Things you can say to the coach:

- "My exam is on 2027-03-21 and I can study 6 hours a day."
- "I studied autonomic pharmacology: 13 of 20 questions right."
- "Make this week's plan; I'm on call on Sunday." (it shows a draft first and turns it into tasks once you agree)
- "Let's solve the question I uploaded together, then take a note."
- "Quiz me from the questions I got wrong."
- "Explain heart failure, then ask me 5 questions. Note the important parts."
- "Don't write so long." (saved as a lasting rule)
- "That's it for today." (saves the session; tomorrow continues from there)

## With ChatGPT

Custom MCP connectors are **not available on ChatGPT's free plan**. On Plus and above they are added with **Developer mode**, from a desktop browser. As of November 2026 OpenAI's own docs say some plans only allow read-only tools; then the coach can't write notes or save the session. That's why Claude is recommended.

To try it: chatgpt.com → **Settings** → **Apps & Connectors** → **Advanced settings** → **Developer mode** on → **Create** → name `Study Coach`, URL the connector address, authentication **OAuth**. Then the same as step 6 for Claude.

## If something goes wrong

| What happened | What to do |
| --- | --- |
| "Connection request not found" page | More than 15 minutes passed. Go back to Claude and tap **Connect** again. |
| "Invalid invite code" | Type the code without spaces; if it still fails, ask for a new one. |
| The coach doesn't remember you | Check **+ → Connectors → Study Coach** is on in the chat. If it is, write "get where I left off". |
| You forgot your password | Ask whoever set up the server to reset it. |
