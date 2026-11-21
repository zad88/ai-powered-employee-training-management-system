import logging
import smtplib
from unittest.mock import MagicMock

import pytest

from backend.app.services import invitation_email


@pytest.fixture
def smtp_config(monkeypatch):
    values = {
        "SMTP_HOST": "smtp.example.com",
        "SMTP_PORT": "587",
        "SMTP_FROM": "sender@example.com",
        "SMTP_USERNAME": "sender@example.com",
        "SMTP_PASSWORD": "fake-secret-password",
        "SMTP_SECURITY": "starttls",
        "INVITATION_BASE_URL": "http://localhost:3000",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_starttls_precedes_authentication_and_delivery(smtp_config, monkeypatch):
    client = MagicMock()
    client.__enter__.return_value = client
    smtp = MagicMock(return_value=client)
    monkeypatch.setattr(invitation_email.smtplib, "SMTP", smtp)

    invitation_email.send_invitation_email("recipient@example.com", "fake-secret-token")

    smtp.assert_called_once_with("smtp.example.com", 587, timeout=15)
    assert [call[0] for call in client.method_calls] == ["starttls", "login", "send_message"]
    client.login.assert_called_once_with("sender@example.com", "fake-secret-password")
    assert "fake-secret-token" in client.send_message.call_args.args[0].get_content()


@pytest.mark.parametrize(
    ("stage", "method", "error"),
    [
        ("tls", "starttls", smtplib.SMTPException("fake-secret-token")),
        ("authentication", "login", smtplib.SMTPAuthenticationError(535, b"fake-secret-password")),
        ("delivery", "send_message", smtplib.SMTPException("fake-secret-token")),
    ],
)
def test_smtp_failures_report_safe_stage(smtp_config, monkeypatch, caplog, stage, method, error):
    client = MagicMock()
    client.__enter__.return_value = client
    getattr(client, method).side_effect = error
    monkeypatch.setattr(invitation_email.smtplib, "SMTP", lambda *args, **kwargs: client)

    with caplog.at_level(logging.WARNING), pytest.raises(invitation_email.InvitationDeliveryError) as raised:
        invitation_email.send_invitation_email("recipient@example.com", "fake-secret-token")

    assert stage in caplog.text
    assert "fake-secret" not in caplog.text
    assert "recipient@example.com" not in caplog.text
    assert "fake-secret" not in str(raised.value)


def test_missing_configuration_reports_configuration_stage(smtp_config, monkeypatch, caplog):
    monkeypatch.delenv("SMTP_HOST")
    with caplog.at_level(logging.WARNING), pytest.raises(invitation_email.InvitationDeliveryError) as raised:
        invitation_email.send_invitation_email("recipient@example.com", "fake-secret-token")
    assert "configuration" in str(raised.value)
    assert "configuration" in caplog.text
    assert "fake-secret" not in caplog.text


def test_connection_error_does_not_expose_exception_details(smtp_config, monkeypatch, caplog):
    def fail(*args, **kwargs):
        raise OSError("fake-secret-token")

    monkeypatch.setattr(invitation_email.smtplib, "SMTP", fail)
    with caplog.at_level(logging.WARNING), pytest.raises(invitation_email.InvitationDeliveryError) as raised:
        invitation_email.send_invitation_email("recipient@example.com", "fake-secret-token")
    assert "connect" in str(raised.value)
    assert "connection" in caplog.text
    assert "fake-secret" not in caplog.text
