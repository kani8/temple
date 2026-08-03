"""mdhtml.py — minimal Markdown -> email-safe HTML. Zero dependencies.

The daily plan is mostly tables. Sent as text/plain those arrive as unreadable
pipe-soup in Gmail, which is why the plan needs a real HTML alternative part.

Deliberately narrow: it handles exactly the subset render.py emits — ATX
headings, GFM tables, bullet lists, bold/italic/code spans, blockquotes, rules
and paragraphs. Everything is inline-styled because Gmail strips <style> blocks.
"""
from __future__ import annotations

import html
import re

FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"

CSS = {
    "h1": f"font-family:{FONT};font-size:22px;font-weight:700;color:#111827;margin:0 0 4px",
    "h2": f"font-family:{FONT};font-size:17px;font-weight:700;color:#111827;"
          "margin:26px 0 10px;padding-bottom:6px;border-bottom:2px solid #e5e7eb",
    "h3": f"font-family:{FONT};font-size:14px;font-weight:700;color:#374151;margin:18px 0 8px",
    "p":  f"font-family:{FONT};font-size:14px;line-height:1.6;color:#374151;margin:0 0 12px",
    "li": f"font-family:{FONT};font-size:14px;line-height:1.6;color:#374151;margin:0 0 5px",
    "table": "border-collapse:collapse;width:100%;margin:0 0 16px;"
             f"font-family:{FONT};font-size:13px",
    "th": "text-align:left;background:#f3f4f6;color:#111827;font-weight:600;"
          "padding:8px 10px;border:1px solid #e5e7eb;white-space:nowrap",
    "td": "padding:8px 10px;border:1px solid #e5e7eb;color:#374151;vertical-align:top",
    "quote": f"font-family:{FONT};font-size:14px;line-height:1.6;color:#4b5563;"
             "margin:0 0 12px;padding:8px 14px;border-left:3px solid #d1d5db;background:#f9fafb",
    "code": "background:#f3f4f6;border-radius:3px;padding:1px 5px;"
            "font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12px;color:#b91c1c",
}


def _inline(text: str) -> str:
    """Escape, then re-introduce the handful of inline spans we support."""
    out = html.escape(text, quote=False)
    out = re.sub(r"`([^`]+)`", lambda m: f'<code style="{CSS["code"]}">{m.group(1)}</code>', out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", out)
    out = re.sub(
        r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
        r'<a href="\2" style="color:#2563eb;text-decoration:none">\1</a>',
        out,
    )
    # bare URLs that weren't already linkified
    out = re.sub(
        r'(?<!["\'>=])(https?://[^\s<)]+)',
        r'<a href="\1" style="color:#2563eb;text-decoration:none">\1</a>',
        out,
    )
    return out


def _is_table_sep(line: str) -> bool:
    return bool(re.fullmatch(r"\s*\|?[\s:|-]+\|[\s:|-]*", line)) and "-" in line


def _split_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def _aligns(sep: str) -> list[str]:
    out = []
    for cell in _split_row(sep):
        left, right = cell.startswith(":"), cell.endswith(":")
        out.append("center" if left and right else "right" if right else "left")
    return out


def markdown_to_html(md: str) -> str:
    lines = md.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # horizontal rule
        if re.fullmatch(r"(\*\s*){3,}|(-\s*){3,}|(_\s*){3,}", stripped):
            out.append('<hr style="border:0;border-top:1px solid #e5e7eb;margin:22px 0">')
            i += 1
            continue

        # heading
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            lvl = min(len(m.group(1)), 3)
            out.append(f'<h{lvl} style="{CSS[f"h{lvl}"]}">{_inline(m.group(2))}</h{lvl}>')
            i += 1
            continue

        # table: header row followed by a separator row
        if "|" in stripped and i + 1 < n and _is_table_sep(lines[i + 1]):
            header = _split_row(stripped)
            aligns = _aligns(lines[i + 1])
            aligns += ["left"] * (len(header) - len(aligns))
            i += 2
            body: list[list[str]] = []
            while i < n and "|" in lines[i] and lines[i].strip():
                body.append(_split_row(lines[i]))
                i += 1

            out.append(f'<table role="presentation" style="{CSS["table"]}"><thead><tr>')
            for idx, cell in enumerate(header):
                out.append(f'<th style="{CSS["th"]};text-align:{aligns[idx]}">{_inline(cell)}</th>')
            out.append("</tr></thead><tbody>")
            for rnum, row in enumerate(body):
                bg = "#ffffff" if rnum % 2 == 0 else "#fafafa"
                out.append(f'<tr style="background:{bg}">')
                for idx, cell in enumerate(row):
                    al = aligns[idx] if idx < len(aligns) else "left"
                    out.append(f'<td style="{CSS["td"]};text-align:{al}">{_inline(cell)}</td>')
                out.append("</tr>")
            out.append("</tbody></table>")
            continue

        # blockquote
        if stripped.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append(f'<div style="{CSS["quote"]}">{_inline(" ".join(buf))}</div>')
            continue

        # list (bullet or ordered)
        if re.match(r"^[-*+]\s+", stripped) or re.match(r"^\d+[.)]\s+", stripped):
            ordered = bool(re.match(r"^\d+[.)]\s+", stripped))
            tag = "ol" if ordered else "ul"
            out.append(f'<{tag} style="margin:0 0 14px;padding-left:22px">')
            while i < n:
                s = lines[i].strip()
                m2 = re.match(r"^(?:[-*+]|\d+[.)])\s+(.*)$", s)
                if not m2:
                    break
                out.append(f'<li style="{CSS["li"]}">{_inline(m2.group(1))}</li>')
                i += 1
            out.append(f"</{tag}>")
            continue

        # paragraph — greedily absorb following non-structural lines
        buf = [stripped]
        i += 1
        while i < n:
            s = lines[i].strip()
            if (not s or s.startswith("#") or s.startswith(">") or "|" in s
                    or re.match(r"^(?:[-*+]|\d+[.)])\s+", s)):
                break
            buf.append(s)
            i += 1
        out.append(f'<p style="{CSS["p"]}">{_inline(" ".join(buf))}</p>')

    return "\n".join(out)


def wrap_document(body_html: str, title: str = "", preheader: str = "") -> str:
    """Wrap fragments in a centred, email-client-safe shell."""
    pre = ""
    if preheader:
        pre = (
            '<div style="display:none;max-height:0;overflow:hidden;opacity:0">'
            f"{html.escape(preheader)}</div>"
        )
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(title)}</title></head>"
        '<body style="margin:0;padding:0;background:#f3f4f6">'
        f"{pre}"
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background:#f3f4f6;padding:24px 12px"><tr><td align="center">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="max-width:680px;background:#ffffff;border-radius:12px;'
        'box-shadow:0 1px 3px rgba(0,0,0,.08)"><tr><td style="padding:28px 30px">'
        f"{body_html}"
        "</td></tr></table>"
        f'<div style="font-family:{FONT};font-size:11px;color:#9ca3af;margin-top:14px">'
        "Fitness OS &middot; generated locally</div>"
        "</td></tr></table></body></html>"
    )
