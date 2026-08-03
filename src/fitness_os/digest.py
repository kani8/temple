"""digest.py — one morning email combining Fitness OS and Prep-U.

Fitness OS owns the SMTP credentials, so the combined send lives here. The
Prep-U half is pulled by shelling out to that repo's daily_brief.py, which
keeps the two projects decoupled: no shared imports, no sys.path surgery, and
the digest degrades to fitness-only if the prep repo is absent or errors.

Point it at the prep repo with PREPU_REPO, or let it try the conventional
sibling path.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

from .mdhtml import FONT, markdown_to_html

DEFAULT_PREPU_DIRS = [
    Path.home() / "projects" / "interview-prep-questions",
    Path.home() / "interview-prep-questions",
]


def find_prepu_repo() -> Path | None:
    env = os.getenv("PREPU_REPO")
    candidates = [Path(env)] if env else []
    candidates += DEFAULT_PREPU_DIRS
    for path in candidates:
        if (path / "platform" / "scripts" / "daily_brief.py").exists():
            return path
    return None


def _python() -> str | None:
    """Locate a usable interpreter for the Prep-U subprocess.

    sys.executable first: the interpreter already running this code is proven to
    work. Falling back to PATH is risky on Windows, where shutil.which("python3")
    happily returns the Microsoft Store alias stub in WindowsApps — a shim that
    exits non-zero with "Python was not found". That made fetch_prepu() fail
    silently and the digest quietly drop its study section.
    """
    exe = sys.executable
    if exe and os.path.isfile(exe):
        base = os.path.basename(exe).lower()
        if base.startswith("pythonw"):
            console = os.path.join(os.path.dirname(exe), base.replace("pythonw", "python", 1))
            if os.path.isfile(console):
                return console
        return exe

    for name in ("python3", "python", "py"):
        found = shutil.which(name)
        if found and "WindowsApps" not in found:
            return found
    return None


class PrepUError(RuntimeError):
    """Why the Prep-U section could not be built."""


def fetch_prepu_strict(target: date, repo: Path | None = None) -> dict:
    """Build the Prep-U section, raising PrepUError with a specific reason.

    Kept separate from fetch_prepu so the daily email can degrade gracefully
    while `--digest-debug` still gets the real diagnosis.
    """
    repo = repo or find_prepu_repo()
    if repo is None:
        tried = os.getenv("PREPU_REPO") or "(PREPU_REPO unset)"
        raise PrepUError(
            f"Prep-U repo not found. PREPU_REPO={tried}; also tried "
            + ", ".join(str(p) for p in DEFAULT_PREPU_DIRS)
        )

    script = repo / "platform" / "scripts" / "daily_brief.py"
    if not script.exists():
        raise PrepUError(f"{script} does not exist")

    py = _python()
    if py is None:
        raise PrepUError("no usable Python interpreter found for the subprocess")

    # Force UTF-8 in the child. Captured stdout on Windows otherwise defaults to
    # the ANSI codepage, and any non-ASCII the brief emits kills it mid-print.
    child_env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")

    data: dict = {}
    for fmt in ("json", "html"):
        cmd = [py, str(script), "--date", target.isoformat(), "--format", fmt]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=45, cwd=str(repo),
                env=child_env, encoding="utf-8", errors="replace",
            )
        except subprocess.TimeoutExpired as exc:
            raise PrepUError(f"daily_brief.py timed out after 45s: {' '.join(cmd)}") from exc
        except OSError as exc:
            raise PrepUError(f"could not execute {py}: {exc}") from exc

        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()[:600] or "(no output)"
            raise PrepUError(
                f"daily_brief.py exited {proc.returncode}\n  cmd: {' '.join(cmd)}\n  {err}"
            )

        if fmt == "json":
            try:
                data = json.loads(proc.stdout)
            except json.JSONDecodeError as exc:
                raise PrepUError(
                    f"daily_brief.py --format json returned unparseable output: "
                    f"{proc.stdout[:300]!r}"
                ) from exc
        else:
            data["html"] = proc.stdout.strip()

    return data


def fetch_prepu(target: date, repo: Path | None = None) -> dict | None:
    """Best-effort version. Returns None on failure, but prints the reason to
    stderr instead of failing silently -- an invisible failure here is what made
    the study section vanish from the digest with no explanation."""
    try:
        return fetch_prepu_strict(target, repo)
    except PrepUError as exc:
        print(f"prepu warning: {exc}", file=sys.stderr)
        return None


# ---------------------------------------------------------------- rendering

def _section(title: str, subtitle: str = "") -> str:
    sub = (
        f'<div style="font-family:{FONT};font-size:12px;color:#6b7280;'
        f'margin-top:2px">{subtitle}</div>' if subtitle else ""
    )
    return (
        f'<div style="margin:0 0 16px;padding:14px 16px;background:#111827;'
        f'border-radius:10px">'
        f'<div style="font-family:{FONT};font-size:16px;font-weight:700;'
        f'color:#ffffff">{title}</div>{sub}</div>'
    )


def build_html(
    target: date,
    plan_markdown: str,
    prepu: dict | None,
    session_name: str = "",
) -> str:
    parts = [
        f'<div style="font-family:{FONT};font-size:12px;color:#9ca3af;'
        f'text-transform:uppercase;letter-spacing:.08em;margin-bottom:2px">'
        f'{target.strftime("%A, %B %-d, %Y") if os.name != "nt" else target.strftime("%A, %B %d, %Y")}</div>',
        f'<h1 style="font-family:{FONT};font-size:24px;font-weight:700;'
        f'color:#111827;margin:0 0 22px">Morning brief</h1>',
    ]

    if prepu:
        if prepu.get("rest_day"):
            sub = f"Rest day &middot; {prepu['streak']} day streak"
        else:
            topics = ", ".join(prepu.get("topics") or [])
            sub = (
                f"Week {prepu.get('week')} &middot; {topics} &middot; "
                f"{prepu.get('total_minutes', 0)} min &middot; "
                f"{prepu.get('streak', 0)} day streak"
            )
        parts.append(_section("Prep-U", sub))
        parts.append(prepu.get("html", ""))
        parts.append('<hr style="border:0;border-top:1px solid #e5e7eb;margin:28px 0">')
    else:
        parts.append(_section("Prep-U", "unavailable this morning"))
        parts.append(
            f'<p style="font-family:{FONT};font-size:13px;color:#6b7280;'
            f'margin:0 0 8px">Could not read the prep schedule. Run '
            f'<code>fitness-os daily --digest-debug</code> to see the exact reason.</p>'
        )
        parts.append('<hr style="border:0;border-top:1px solid #e5e7eb;margin:28px 0">')

    parts.append(_section("Fitness OS", session_name or "Training &amp; nutrition"))
    parts.append(markdown_to_html(plan_markdown))
    return "".join(parts)


def build_text(target: date, plan_markdown: str, prepu: dict | None) -> str:
    lines = [f"Morning brief — {target.isoformat()}", "=" * 40, ""]
    if prepu:
        lines.append("PREP-U")
        lines.append("-" * 40)
        if prepu.get("rest_day"):
            lines.append(f"Rest day. Streak: {prepu.get('streak', 0)} days.")
        else:
            lines.append(
                f"Week {prepu.get('week')} — {', '.join(prepu.get('topics') or [])} "
                f"({prepu.get('total_minutes', 0)} min, "
                f"{prepu.get('streak', 0)} day streak)"
            )
            for q in prepu.get("questions", []):
                mark = "x" if q.get("status") == "solved" else " "
                lines.append(f"  [{mark}] {q.get('title')} — {q.get('url')}")
        lines += ["", ""]
    lines.append("FITNESS OS")
    lines.append("-" * 40)
    lines.append(plan_markdown)
    return "\n".join(lines)
