"""A per-user avenoxbeyin vault and a thin bridge to its CLI.

This module contains NO memory logic. For each user it sets up a real avenoxbeyin V3 vault with the
official `scripts/install_v3.py` and runs the vault's own `beyin.py` commands and SessionStart hook.
Search, note/task writes, revision checks, review dates (`review_at`), task due dates (`due_at`),
Companion files and session receipts all come from the engine in this repository.

The server only owns: setting the vault up, locking each user into their own vault, and placing
the coach skill in the vault.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

# Repository root: coach/coach/vault.py -> ../../ ; in Docker it comes from COACH_ENGINE_DIR.
ENGINE_DIR = Path(os.environ.get("COACH_ENGINE_DIR") or Path(__file__).resolve().parents[2])
SKILL_DIR = Path(__file__).resolve().parent / "skill"
COACH_SKILL = SKILL_DIR / "SKILL.md"
EXAMS_DIR = SKILL_DIR / "exams"  # one Markdown profile per exam; adding an exam is adding a file
STALE_AFTER_DAYS = 120  # a profile not checked against its sources for this long is served as stale
SKILL_TARGET_DIR = ".agents/skills/study-coach"
COACH_SKILL_TARGET = SKILL_TARGET_DIR + "/SKILL.md"
EXAMS_TARGET_DIR = SKILL_TARGET_DIR + "/exams"
OLD_SKILL_DIRS = (".agents/skills/calisma-kocu",)  # written by the first version
# The server only needs the Claude/Codex hooks and the core skills; desktop launchers and other client
# adapters are kept out of the vault (and so out of the folder synced to the student's iPad).
EXCLUDED_COMPONENTS = ("adapters", "launchers")
HARNESS = "claude"

_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()


class VaultError(ToolError):
    """A vault error returned to the coach as a tool error (not a server error)."""


def _lock(user_id: str) -> threading.Lock:
    with _locks_lock:
        return _locks.setdefault(user_id, threading.Lock())


class Vault:
    def __init__(self, vault_root: Path, state_root: Path, user_id: str):
        if not re.fullmatch(r"[0-9a-f]{32}", user_id):
            raise VaultError("Invalid user.")
        self.user_id = user_id
        self.vault = (vault_root / user_id).resolve()
        self.state = (state_root / user_id).resolve()
        self.tmp = self.state / "coach-tmp"

    # --- setup -------------------------------------------------------------
    def is_installed(self) -> bool:
        return (self.vault / ".beyin-version").is_file() and (self.vault / "beyin.py").is_file()

    def prepare(self) -> None:
        """Installs the vault with the official installer on first use and keeps the coach skill current."""
        with _lock(self.user_id):
            if not self.is_installed():
                self.vault.mkdir(parents=True, exist_ok=True)
                self.state.mkdir(parents=True, exist_ok=True)
                cmd = [sys.executable, str(ENGINE_DIR / "scripts" / "install_v3.py"),
                       "--vault", str(self.vault), "--state", str(self.state)]
                for component in EXCLUDED_COMPONENTS:
                    cmd += ["--exclude-component", component]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=180,
                                        env=self._env(), cwd=str(self.vault))
                if result.returncode != 0 or not self.is_installed():
                    raise VaultError("Could not set up the vault: " + (result.stdout + result.stderr)[-800:])
                # A daily GitHub release check per vault is pointless on a server; turn it off with the engine's own setting.
                self._run(["--vault", str(self.vault), "--state", str(self.state),
                           "preferences", "--update-notifications", "off"], None, 60)
            self._place_skill()
            self.tmp.mkdir(parents=True, exist_ok=True)

    def _place_skill(self) -> None:
        """Mirrors the coach skill (SKILL.md and its exam profiles) into the vault, like any vault skill."""
        files = {COACH_SKILL_TARGET: COACH_SKILL}
        files.update({f"{EXAMS_TARGET_DIR}/{p.name}": p for p in EXAMS_DIR.glob("*.md")})
        for rel, source in files.items():
            target = self.vault / rel
            content = source.read_bytes()
            if not target.is_file() or target.read_bytes() != content:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
        exams = self.vault / EXAMS_TARGET_DIR
        for stale in exams.glob("*.md") if exams.is_dir() else ():
            if f"{EXAMS_TARGET_DIR}/{stale.name}" not in files:  # a profile we no longer ship
                stale.unlink()
        for old in OLD_SKILL_DIRS:
            shutil.rmtree(self.vault / old, ignore_errors=True)

    def _env(self) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items() if k in ("PATH", "LANG", "LC_ALL", "TZ", "SYSTEMROOT")}
        env["HOME"] = str(self.state)  # installer and runtime must not touch another user's directory
        env["PYTHONIOENCODING"] = "utf-8"
        env.setdefault("TZ", os.environ.get("TZ", "UTC"))
        return env

    # --- CLI ---------------------------------------------------------------
    def cli(self, *args: str, payload: dict | None = None, timeout: int = 60) -> dict[str, Any]:
        """Runs `beyin.py --json <args>`. With `payload`, a temporary JSON file is passed as `--file`.

        Conflicts (revision, sha) and validation errors come back as results, not exceptions; the coach
        re-reads and retries following the repository's rule.
        """
        self.prepare()
        return self._run(["--vault", str(self.vault), "--state", str(self.state), *args], payload, timeout)

    def capture(self, *args: str, timeout: int = 180) -> dict[str, Any]:
        """The repository's Yakala inbox: `beyin.py yakala <args>` (ekle, liste, isle, bitti).
        Yakala is its own small CLI; it reads the vault and state paths from the install's .beyin-runtime.json."""
        self.prepare()
        return self._run(["yakala", *args], None, timeout)

    def _run(self, args: list[str], payload: dict | None, timeout: int) -> dict[str, Any]:
        cmd = [sys.executable, str(self.vault / "beyin.py"), "--json", *args]
        file = None
        if payload is not None:
            file = self.tmp / f"{uuid.uuid4().hex}.json"
            file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            cmd += ["--file", str(file)]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=self._env(),
                                    cwd=str(self.vault))
        except subprocess.TimeoutExpired:
            raise VaultError("The vault command timed out.") from None
        finally:
            if file is not None:
                file.unlink(missing_ok=True)
        out = result.stdout.strip()
        try:
            data = json.loads(out) if out else {}
        except json.JSONDecodeError:
            data = {"output": out[-4000:]}
        if not isinstance(data, dict):
            data = {"result": data}
        data["exit_code"] = result.returncode
        if result.returncode not in (0, 2) and "error" not in data:
            error = (result.stderr.strip() or out)[-1500:] or "unknown error"
            try:  # the engine writes errors to stderr as {"error": "RevisionConflict", "message": ...}
                detail = json.loads(error)
            except json.JSONDecodeError:
                detail = None
            if isinstance(detail, dict) and "error" in detail:
                data.update(detail)
            else:
                data["error"] = error
        return self._hide_paths(data)

    def _hide_paths(self, data: Any) -> Any:
        """Never leak the server's absolute paths (where other users' folders live)."""
        text = json.dumps(data, ensure_ascii=False)
        for path, placeholder in ((str(self.vault), "<vault>"), (str(self.state), "<state>")):
            text = text.replace(json.dumps(path)[1:-1], placeholder)
        return json.loads(text)

    # --- session start -------------------------------------------------------
    def session_start(self, session: str) -> str:
        """The same context the repository's SessionStart hook builds (Companion, due reviews and tasks,
        the Receipt session line)."""
        self.prepare()
        hook = self.vault / ".claude" / "scripts" / "beyin_v3_hook.py"
        payload = json.dumps({"hook_event_name": "SessionStart", "session_id": session, "cwd": str(self.vault),
                              "source": "startup"})
        try:
            result = subprocess.run([sys.executable, str(hook), "--vault", str(self.vault), "--state", str(self.state),
                                     "--harness", HARNESS], input=payload, capture_output=True, text=True, timeout=60,
                                    env=self._env(), cwd=str(self.vault))
        except subprocess.TimeoutExpired:
            raise VaultError("The session start context timed out.") from None
        try:
            data = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            data = {}
        text = (data.get("hookSpecificOutput") or {}).get("additionalContext") or data.get("additionalContext") or ""
        if not text:
            raise VaultError("Could not get the session start context: " + (result.stderr or result.stdout)[-500:])
        return self._hide_paths(text)

    # --- files ---------------------------------------------------------------
    def file_path(self, rel: str) -> Path:
        rel = str(rel).replace("\\", "/").strip().lstrip("/")
        parts = [p for p in rel.split("/") if p]
        if not parts or any(p in (".", "..") or p.startswith(".") for p in parts):
            raise VaultError("This path can't be used.")
        path = (self.vault / Path(*parts)).resolve()
        if self.vault not in path.parents:
            raise VaultError("This path can't be used.")
        return path


def _front_matter(text: str) -> dict[str, Any]:
    """The flat `key: value` / `key: [a, b]` front matter used by exam profiles (no nesting needed)."""
    if not text.startswith("---\n"):
        return {}
    meta: dict[str, Any] = {}
    for line in text[4:].split("\n---", 1)[0].splitlines():
        key, sep, value = line.partition(":")
        if not sep or not key.strip():
            continue
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            meta[key.strip()] = [v.strip() for v in value[1:-1].split(",") if v.strip()]
        else:
            meta[key.strip()] = value
    return meta


def is_stale(last_checked: Any, today: date | None = None) -> bool:
    try:
        checked = date.fromisoformat(str(last_checked))
    except ValueError:
        return True  # never checked, or an unreadable date
    return ((today or date.today()) - checked).days > STALE_AFTER_DAYS


def exam_profiles() -> list[dict[str, Any]]:
    """Index of the built-in exam profiles, from each file's front matter."""
    index = []
    for path in sorted(EXAMS_DIR.glob("*.md")):
        meta = _front_matter(path.read_text(encoding="utf-8"))
        if meta.get("id") == path.stem:  # README.md and half-written files have no matching id
            entry = {k: meta.get(k) for k in ("id", "name", "full_name", "country", "group", "aliases",
                                              "official_url", "sources", "last_checked")}
            entry["stale"] = is_stale(entry["last_checked"])
            index.append(entry)
    return index


def exam_profile(exam_id: str) -> str:
    exam_id = str(exam_id or "").strip().lower()
    known = {p["id"] for p in exam_profiles()}
    if exam_id not in known:
        raise VaultError(f"No built-in profile for '{exam_id}'. Known: {', '.join(sorted(known)) or 'none'}. "
                         "Without a profile, look the exam up with web search; ask the student only as a last resort.")
    return (EXAMS_DIR / f"{exam_id}.md").read_text(encoding="utf-8")


def engine_available() -> bool:
    return (ENGINE_DIR / "scripts" / "install_v3.py").is_file() and (ENGINE_DIR / "template").is_dir()
