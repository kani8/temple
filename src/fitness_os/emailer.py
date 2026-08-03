from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path

from .mdhtml import markdown_to_html, wrap_document

REQUIRED_ENV = ["SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "EMAIL_FROM", "EMAIL_TO"]

# Providers that speak implicit TLS on 465 rather than STARTTLS on 587.
IMPLICIT_TLS_PORTS = {465}


def missing_email_env() -> list[str]:
    return [name for name in REQUIRED_ENV if not os.getenv(name)]


def _recipients() -> list[str]:
    """EMAIL_TO may be a comma- or semicolon-separated list."""
    raw = os.environ["EMAIL_TO"]
    parts = [p.strip() for p in raw.replace(";", ",").split(",")]
    return [p for p in parts if p]


def _preheader(markdown: str) -> str:
    """First meaningful line, used as the inbox preview snippet."""
    for line in markdown.splitlines():
        s = line.strip().lstrip("#").strip()
        if s and not s.startswith("|") and not s.startswith("-"):
            return s[:140]
    return ""


def send_email(
    subject: str,
    body: str,
    attachment: Path | None = None,
    *,
    html_body: str | None = None,
    from_name: str = "Fitness OS",
) -> None:
    """Send a multipart/alternative email.

    `body` is Markdown. It goes out as-is in the text/plain part and, unless
    `html_body` is supplied, is converted to styled HTML for the text/html part.
    Markdown tables are unreadable as plain text in most clients, so the HTML
    alternative is what actually gets read.
    """
    missing = missing_email_env()
    if missing:
        raise RuntimeError(
            "Missing email environment variables: "
            + ", ".join(missing)
            + ". Set them locally or as GitHub Actions repository secrets."
        )

    sender = os.environ["EMAIL_FROM"]
    to_addrs = _recipients()
    if not to_addrs:
        raise RuntimeError("EMAIL_TO is set but contains no usable address.")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name, sender))
    msg["To"] = ", ".join(to_addrs)
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=sender.split("@")[-1])
    msg["X-Fitness-OS"] = "daily-plan"

    msg.set_content(body)
    rendered = html_body if html_body is not None else markdown_to_html(body)
    msg.add_alternative(
        wrap_document(rendered, title=subject, preheader=_preheader(body)),
        subtype="html",
    )

    if attachment and attachment.exists():
        # application/octet-stream, not text/markdown. Mail clients are entitled
        # to render text/* parts inline, and several do — which surfaces the raw
        # Markdown (hashes, pipes, asterisks) underneath the styled HTML body and
        # looks exactly like the formatting failed.
        msg.add_attachment(
            attachment.read_bytes(),
            maintype="application",
            subtype="octet-stream",
            filename=attachment.name,
        )

    host = os.environ["SMTP_HOST"]
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.environ["SMTP_USERNAME"]
    password = os.environ["SMTP_PASSWORD"]
    context = ssl.create_default_context()

    try:
        if port in IMPLICIT_TLS_PORTS:
            with smtplib.SMTP_SSL(host, port, timeout=30, context=context) as smtp:
                smtp.login(username, password)
                smtp.send_message(msg, from_addr=sender, to_addrs=to_addrs)
        else:
            with smtplib.SMTP(host, port, timeout=30) as smtp:
                smtp.ehlo()
                if smtp.has_extn("starttls"):
                    smtp.starttls(context=context)
                    smtp.ehlo()
                smtp.login(username, password)
                smtp.send_message(msg, from_addr=sender, to_addrs=to_addrs)
    except smtplib.SMTPAuthenticationError as exc:
        raise RuntimeError(
            f"SMTP auth rejected by {host}:{port} for {username}. "
            "For Gmail this must be a 16-character App Password (not your normal "
            "password), with 2-Step Verification enabled on the account."
        ) from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise RuntimeError(f"SMTP send failed via {host}:{port}: {exc}") from exc


def preview_html(subject: str, body: str, out_path: Path) -> Path:
    """Render what the email will look like, without sending. Useful for
    iterating on formatting when SMTP creds aren't configured."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        wrap_document(markdown_to_html(body), title=subject, preheader=_preheader(body)),
        encoding="utf-8",
    )
    return out_path
