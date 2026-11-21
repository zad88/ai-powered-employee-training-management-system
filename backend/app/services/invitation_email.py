import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlparse


logger = logging.getLogger(__name__)

_ERROR_MESSAGES = {
    "configuration": "Invitation email configuration is incomplete or invalid.",
    "connection": "Could not connect to the invitation email server.",
    "tls": "Could not establish a secure connection to the invitation email server.",
    "authentication": "The invitation email server rejected authentication. Check the email credentials.",
    "delivery": "The invitation email server could not accept the message. Check the sender, recipient and server status.",
}


class InvitationDeliveryError(Exception):
    def __init__(self, stage: str):
        super().__init__(_ERROR_MESSAGES.get(stage, _ERROR_MESSAGES["delivery"]))


def send_invitation_email(email: str, token: str) -> None:
    host = os.getenv("SMTP_HOST", "").strip()
    sender = os.getenv("SMTP_FROM", "").strip()
    base = os.getenv("INVITATION_BASE_URL", "").strip().rstrip("/")
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    security = os.getenv("SMTP_SECURITY", "starttls").strip().lower()
    stage = "configuration"
    try:
        port = int(os.getenv("SMTP_PORT", "587"))
        parsed = urlparse(base)
        if (
            not host or not sender or not base or not 1 <= port <= 65535
            or security not in {"starttls", "ssl"}
            or bool(username) != bool(password)
            or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
            or parsed.scheme not in {"http", "https"}
            or (parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"})
        ):
            raise ValueError("Invalid invitation email configuration.")
        message = EmailMessage()
        message["From"] = sender
        message["To"] = email
        message["Subject"] = "Your training workspace invitation"
        message.set_content(
            "You have been invited to the training workspace. "
            "Use the link below to create your password. "
            "The link expires and can only be used once.\n\n"
            f"{base}/accept-invitation#token={token}\n"
        )
        context = ssl.create_default_context()
        stage = "connection"
        if security == "ssl":
            client = smtplib.SMTP_SSL(host, port, timeout=15, context=context)
        else:
            client = smtplib.SMTP(host, port, timeout=15)
        with client:
            if security == "starttls":
                stage = "tls"
                client.starttls(context=context)
            if username:
                stage = "authentication"
                client.login(username, password)
            stage = "delivery"
            client.send_message(message)
    except (ValueError, OSError, smtplib.SMTPException) as exc:
        logger.warning("Invitation email failed during %s (%s).", stage, type(exc).__name__)
        raise InvitationDeliveryError(stage) from None
