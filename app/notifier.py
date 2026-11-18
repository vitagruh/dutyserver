"""Очередь уведомлений: email (SMTP) и Rocket.Chat (webhook)."""

from __future__ import annotations

import json
import smtplib
import threading
import urllib.error
import urllib.request
from email.message import EmailMessage
from typing import Any

from . import db

EVENT_FLAGS = {
    "request_created": "notify_on_request",
    "request_decided": "notify_on_decision",
    "coverage_gap": "notify_on_coverage",
    "coverage_override": "notify_on_decision",
    "test": "notifications_enabled",
}

_flush_lock = threading.Lock()


def _contacts(
    conn,
    *,
    teamlead: bool = False,
    person_id: int | None = None,
) -> list[tuple[str, str]]:
    recipients: list[tuple[str, str]] = []
    if teamlead:
        rows = conn.execute(
            "SELECT email, rocketchat FROM users "
            "WHERE active = 1 AND role IN ('admin','teamlead')"
        ).fetchall()
        for row in rows:
            if row["email"]:
                recipients.append(("email", row["email"]))
            if row["rocketchat"]:
                recipients.append(("rocketchat", row["rocketchat"]))
    if person_id is not None:
        person = conn.execute(
            "SELECT email, rocketchat FROM people WHERE id = ?", (person_id,)
        ).fetchone()
        user = conn.execute(
            "SELECT email, rocketchat FROM users "
            "WHERE active = 1 AND person_id = ?",
            (person_id,),
        ).fetchone()
        email = (user["email"] if user and user["email"] else "") or (
            person["email"] if person else ""
        )
        chat = (user["rocketchat"] if user and user["rocketchat"] else "") or (
            person["rocketchat"] if person else ""
        )
        if email:
            recipients.append(("email", email))
        if chat:
            recipients.append(("rocketchat", chat))
    seen: set[tuple[str, str]] = set()
    unique: list[tuple[str, str]] = []
    for item in recipients:
        if item[0] and item[1] and item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def enqueue(
    event: str,
    subject: str,
    body: str,
    *,
    teamlead: bool = False,
    person_id: int | None = None,
    force: bool = False,
) -> int:
    with db.db() as conn:
        settings = db.load_settings(conn)
        if not force:
            if settings.get("notifications_enabled", "0") != "1":
                return 0
            flag = EVENT_FLAGS.get(event)
            if flag and settings.get(flag, "1") != "1":
                return 0
        recipients = _contacts(conn, teamlead=teamlead, person_id=person_id)
        if not recipients:
            return 0
        with db.transaction(conn):
            for channel, recipient in recipients:
                conn.execute(
                    "INSERT INTO notification_outbox"
                    "(channel, recipient, subject, body, event) "
                    "VALUES(?, ?, ?, ?, ?)",
                    (channel, recipient, subject[:200], body, event),
                )
    _spawn_flush()
    return len(recipients)


def _spawn_flush() -> None:
    threading.Thread(target=flush, daemon=True).start()


def send_test(channel: str, recipient: str, subject: str, body: str) -> dict[str, Any]:
    """Немедленная отправка одного сообщения с записью в журнал."""
    with db.db() as conn:
        settings = db.load_settings(conn)
        cursor = conn.execute(
            "INSERT INTO notification_outbox"
            "(channel, recipient, subject, body, event) VALUES(?, ?, ?, ?, 'test')",
            (channel, recipient, subject[:200], body),
        )
        row_id = int(cursor.lastrowid)
    row = {
        "channel": channel,
        "recipient": recipient,
        "subject": subject,
        "body": body,
    }
    try:
        _deliver(row, settings)
    except (OSError, RuntimeError, smtplib.SMTPException, urllib.error.URLError) as error:
        message = str(error)[:300]
        with db.db() as conn:
            conn.execute(
                "UPDATE notification_outbox SET status = 'error', "
                "attempts = attempts + 1, last_error = ? WHERE id = ?",
                (message, row_id),
            )
        return {"id": row_id, "status": "error", "error": message}
    with db.db() as conn:
        conn.execute(
            "UPDATE notification_outbox SET status = 'sent', attempts = attempts + 1, "
            "sent_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id = ?",
            (row_id,),
        )
    return {"id": row_id, "status": "sent", "error": ""}


def _deliver_email(settings: dict[str, str], recipient: str, subject: str, body: str) -> None:
    host = settings.get("smtp_host", "").strip()
    if not host:
        raise RuntimeError("SMTP не настроен: укажите сервер")
    sender = settings.get("smtp_from", "").strip() or settings.get("smtp_user", "").strip()
    if not sender:
        raise RuntimeError("SMTP не настроен: укажите адрес отправителя")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message.set_content(body)
    port = int(settings.get("smtp_port", "587"))
    with smtplib.SMTP(host, port, timeout=10) as client:
        client.ehlo()
        if settings.get("smtp_tls", "1") == "1":
            client.starttls()
            client.ehlo()
        user = settings.get("smtp_user", "").strip()
        if user:
            client.login(user, settings.get("smtp_password", ""))
        client.send_message(message)


def _deliver_rocketchat(settings: dict[str, str], recipient: str, subject: str, body: str) -> None:
    webhook = settings.get("rocketchat_webhook", "").strip()
    if not webhook:
        raise RuntimeError("Rocket.Chat не настроен: укажите webhook")
    text = f"*{subject}*\n{body}"
    payload: dict[str, Any] = {"text": text, "channel": recipient}
    request = urllib.request.Request(
        webhook,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        response.read(200)


def _deliver(row: dict[str, Any], settings: dict[str, str]) -> None:
    if row["channel"] == "email":
        _deliver_email(settings, row["recipient"], row["subject"], row["body"])
    else:
        _deliver_rocketchat(settings, row["recipient"], row["subject"], row["body"])


def flush(limit: int = 50) -> int:
    if not _flush_lock.acquire(blocking=False):
        return 0
    sent = 0
    try:
        with db.db() as conn:
            settings = db.load_settings(conn)
            rows = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM notification_outbox WHERE status = 'pending' "
                    "ORDER BY id LIMIT ?",
                    (limit,),
                )
            ]
        for row in rows:
            try:
                _deliver(row, settings)
            except (OSError, RuntimeError, smtplib.SMTPException, urllib.error.URLError) as error:
                with db.db() as conn:
                    conn.execute(
                        "UPDATE notification_outbox SET status = 'error', "
                        "attempts = attempts + 1, last_error = ? WHERE id = ?",
                        (str(error)[:300], row["id"]),
                    )
            else:
                with db.db() as conn:
                    conn.execute(
                        "UPDATE notification_outbox SET status = 'sent', "
                        "attempts = attempts + 1, "
                        "sent_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id = ?",
                        (row["id"],),
                    )
                sent += 1
    finally:
        _flush_lock.release()
    return sent


def retry_failed() -> int:
    with db.db() as conn:
        conn.execute(
            "UPDATE notification_outbox SET status = 'pending' WHERE status = 'error'"
        )
    return flush()
