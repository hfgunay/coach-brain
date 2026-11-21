# Coach skill

The single source of coaching behaviour is [`coach/skill/SKILL.md`](../coach/skill/SKILL.md). It is an avenoxbeyin skill: it adds no new mechanism and applies the memory protocol from the vault's AGENTS.md and the beyin skill to exam and study work (getting to know the student, priorities, the plan as tasks, notes on missed questions with `review_at`).

It reaches the coach three ways:

1. **In the vault**: the server installs it as `.agents/skills/study-coach/SKILL.md` and rewrites it when the file changes. The coach reads AGENTS.md, the beyin skill and this skill with `read_instructions`.
2. **Server instructions**: the short text sent on connect (`INSTRUCTIONS` in `server.py`): "first `start_session`; if you don't know the protocol, `read_instructions`".
3. **MCP prompt**: `study_coach` returns the same text.

## Exam profiles

[`coach/skill/exams/`](../coach/skill/exams/) holds one Markdown file per exam (TUS so far; health exams next) with a
small front matter (id, name, country, group, aliases, official_url, sources, last_checked). A profile not checked
for 120 days is served with `stale: true` and the coach re-checks it with web search. The server copies them into the
vault next to the skill and `read_instructions` lists them; the coach reads one with
`read_instructions(which="exam", exam="tus")`. They are a starting point so the coach never asks the student
what is on their exam; with web search the coach verifies them at the official source. Adding an exam is adding
a file; see the folder's README for the keys.

There is no need to paste text into a Claude Project; the project instruction "In every chat, first start_session, then read_instructions" is enough.

When changing the text:

- Keep tool names identical to the code and keep the mapping table to beyin commands.
- Don't describe a new structure for something the repo already has (a separate mistake log, a separate plan file). Check what the engine provides first.
- Keep the rule to talk in the student's language.
- Don't remove the factual accuracy rule.
- Keep the first session short: the student should be studying within three messages.
