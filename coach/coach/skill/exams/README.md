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
| `last_checked` | When someone last compared this file with the official source (YYYY-MM-DD) |

Groups: `medical` (medical and health licensing/specialty), `university-entrance`, `public-service`
(civil service, teaching, police), `language`, `graduate-admission`, `professional` (law, accounting,
engineering licences), `school` (course and term exams).

The body says what is stable about the exam: when it is held, its parts and their question counts, the
question format, scoring, and what the coach should search for to refresh the facts. Mark anything that changes
every year (dates, fees, quotas) as "verify". Never write a number you could not check; leave it out instead.
