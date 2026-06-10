import logging
import smtplib
from email.message import EmailMessage
from typing import Protocol

from app.config import Settings

logger = logging.getLogger(__name__)


class EmailSender(Protocol):
    enabled: bool

    def send(self, *, subject: str, body: str) -> None: ...


class NullEmailSender:
    """No-op sender used when notifications are disabled or SMTP is unconfigured."""

    enabled = False

    def send(self, *, subject: str, body: str) -> None:
        return None


class FakeEmailSender:
    """Test double recording sent messages in memory."""

    enabled = True

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send(self, *, subject: str, body: str) -> None:
        self.sent.append((subject, body))


class SmtpEmailSender:
    enabled = True

    def __init__(self, *, host: str, port: int, user: str, password: str,
                 sender: str, to: str) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._from = sender or user
        self._to = to

    def send(self, *, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self._from
        msg["To"] = self._to
        msg.set_content(body)
        with smtplib.SMTP(self._host, self._port) as smtp:
            smtp.starttls()
            if self._user:
                smtp.login(self._user, self._password)
            smtp.send_message(msg)
        logger.info("notifier: sent email '%s' to %s", subject, self._to)


def make_email_sender(settings: Settings) -> EmailSender:
    if not (settings.notifications_enabled and settings.smtp_configured):
        return NullEmailSender()
    return SmtpEmailSender(
        host=settings.smtp_host, port=settings.smtp_port, user=settings.smtp_user,
        password=settings.smtp_password, sender=settings.smtp_from, to=settings.notify_email_to,
    )
