# Coach skill

The single source of coaching behaviour is [`coach/skill/SKILL.md`](../coach/skill/SKILL.md). It is an avenoxbeyin skill: it adds no new mechanism and applies the memory protocol from the vault's AGENTS.md and the beyin skill to exam and study work (getting to know the student, priorities, the plan as tasks, notes on missed questions with `review_at`).

It reaches the coach three ways:

1. **In the vault**: the server installs it as `.agents/skills/study-coach/SKILL.md` and rewrites it when the file changes. The coach reads AGENTS.md, the beyin skill and this skill with `read_instructions`.
2. **Server instructions**: the short text sent on connect (`INSTRUCTIONS` in `server.py`): "first `start_session`; if you don't know the protocol, `read_instructions`".
3. **MCP prompt**: `study_coach` returns the same text.

There is no need to paste text into a Claude Project; the project instruction "In every chat, first start_session, then read_instructions" is enough.

When changing the text:

- Keep tool names identical to the code and keep the mapping table to beyin commands.
- Don't describe a new structure for something the repo already has (a separate mistake log, a separate plan file). Check what the engine provides first.
- Keep the rule to talk in the student's language.
- Don't remove the factual accuracy rule.
