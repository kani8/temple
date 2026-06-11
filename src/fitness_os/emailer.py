from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from pathlib import Path


REQUIRED_ENV = ["SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "EMAIL_FROM", "EMAIL_TO"]


def missing_email_env() -> list[str]:
    return [name for name in REQUIRED_ENV if not os.getenv(name)]


def send_email(subject: str, body: str, attachment: Path | None = None) -> None:
    missing = missing_email_env()
    if missing:
        raise RuntimeError(f"Missing email environment variables: {', '.join(missing)}")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.environ["EMAIL_FROM"]
    msg["To"] = os.environ["EMAIL_TO"]
    msg.set_content(body)

    if attachment:
        msg.add_attachment(
            attachment.read_bytes(),
            maintype="text",
            subtype="markdown",
            filename=attachment.name,
        )

    host = os.environ["SMTP_HOST"]
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.environ["SMTP_USERNAME"]
    password = os.environ["SMTP_PASSWORD"]

    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(username, password)
        smtp.send_message(msg)

