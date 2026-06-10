from app.config import Settings
from app.notify.email import FakeEmailSender, NullEmailSender, make_email_sender


def _settings(**over) -> Settings:
    base = dict(postgres_user="u", postgres_password="p", postgres_db="d",
                postgres_host="h", postgres_port=5432)
    base.update(over)
    return Settings(**base)


def test_fake_records_messages():
    sender = FakeEmailSender()
    assert sender.enabled is True
    sender.send(subject="hi", body="there")
    assert sender.sent == [("hi", "there")]


def test_null_is_disabled_and_noop():
    sender = NullEmailSender()
    assert sender.enabled is False
    sender.send(subject="x", body="y")  # no-op, must not raise


def test_smtp_configured_predicate():
    assert _settings().smtp_configured is False
    assert _settings(smtp_host="smtp.example.com", notify_email_to="me@example.com").smtp_configured is True


def test_make_email_sender_null_when_disabled():
    s = _settings(smtp_host="smtp.example.com", notify_email_to="me@example.com",
                  notifications_enabled=False)
    assert make_email_sender(s).enabled is False  # disabled -> Null


def test_make_email_sender_null_when_unconfigured():
    s = _settings(notifications_enabled=True)  # no smtp host
    assert make_email_sender(s).enabled is False
