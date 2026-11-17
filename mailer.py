"""Email service. Uses SMTP when SMTP_HOST is set; otherwise stores mails in an in-memory outbox (dev/test)."""
import os, smtplib
from email.message import EmailMessage
from flask import current_app

def send_mail(to, subject, body):
    current_app.config.setdefault("OUTBOX", []).append({"to": to, "subject": subject, "body": body})
    host = os.environ.get("SMTP_HOST")
    if not host:
        current_app.logger.info("MAIL to=%s subject=%s\n%s", to, subject, body); return
    msg = EmailMessage(); msg["To"], msg["Subject"] = to, subject
    msg["From"] = os.environ.get("SMTP_FROM", "attendance@localhost"); msg.set_content(body)
    with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", 25))) as s: s.send_message(msg)
