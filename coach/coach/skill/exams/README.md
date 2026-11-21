# Exam profiles

One Markdown file per exam. The coach uses a profile as its **starting point** so it never has to ask the
student basic facts about the exam (subjects, question counts, format). A profile is not the source of truth:
when the coach has web search it checks the official source first and tells the student what changed.

Adding an exam is adding a file here; no code changes. Copy an existing profile and keep the front matter keys:

| Key | Meaning |
| --- | --- |
| `id` | Short, lowercase, unique; the file name without `.md` |
| `name` | The name students use (e.g. `TUS`, `KPSS`, `USMLE Step 1`) |
| `full_name` | Official name, in the exam's own language |
| `country` | ISO country code, or `INT` for international exams |
| `group` | One of the groups below |
| `aliases` | Other names students type, comma separated, in brackets |
| `organizer` | Who runs the exam |
| `official_url` | Where the coach verifies facts |
| `sources` | The pages the numbers in this file come from (guide, calendar), comma separated in brackets; a URL must not contain a comma |
| `last_checked` | When someone last compared this file with its sources (YYYY-MM-DD) |

Order: health exams first (TUS now; DUS, YDUS, STS, then USMLE, PLAB, NEET-PG). Other groups wait until the
health exams work.

Groups: `medical` (medical and health licensing/specialty), `university-entrance`, `public-service`
(civil service, teaching, police), `language`, `graduate-admission`, `professional` (law, accounting,
engineering licences), `school` (course and term exams).

The body says what is stable about the exam: when it is held, its parts and their question counts, the
question format, scoring, and what the coach should search for to refresh the facts. Mark anything that changes
every year (dates, fees, quotas) as "verify". Never write a number you could not check; leave it out instead.

## Keeping profiles current

A profile older than `STALE_AFTER_DAYS` (coach/vault.py, 120 days) is served with `stale: true`, and the coach
then re-checks every number with web search before using it. That keeps students safe, but the file still has to
be refreshed:

1. Open each URL in `sources`, plus the exam's newest official guide (kılavuz).
2. Update what changed: parts, question counts, format, scoring. Never copy dates of a single sitting into the
   file; the coach looks those up.
3. Set `last_checked` to today and open a pull request.

Refresh right after the organizer publishes a new guide, and at least once per exam season.
