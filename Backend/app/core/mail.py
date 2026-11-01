"""Outgoing mail: an HTTPS API when the host blocks SMTP, SMTP when it doesn't.

Render refuses outbound traffic on ports 25, 465 and 587 for every free service, so
a deployed API can open no socket to smtp.gmail.com at all - the failure is
"Network is unreachable" before any login is attempted, which no credential can
fix. BREVO_API_KEY sends the same two messages over HTTPS on port 443 instead.
Without it the SMTP path runs, which is how this project mails from a laptop.

A failed send never fails the request that triggered it for a verification link -
the account is already committed, so the student presses "send again" instead of
losing it to a mail server that was down for ninety seconds.

A staff sign-in code is the opposite: if the code cannot be delivered there is
nothing to type, and pretending otherwise would leave a login half-done.
"""

import logging
import smtplib
from email.message import EmailMessage
from email.utils import parseaddr

import httpx

from app.core.config import settings

log = logging.getLogger(__name__)

SMTP_TIMEOUT_SECONDS = 10
HTTP_TIMEOUT_SECONDS = 15
BREVO_URL = "https://api.brevo.com/v3/smtp/email"

INTRO = (
    "Confirm this address to finish setting up your GyanSankalp account.\n"
    "Until it is confirmed you can sign in, but you cannot enroll in a course.\n\n"
    "Open this link within {hours} hours:\n\n    {url}\n\n"
    "If you did not ask for a GyanSankalp account, ignore this message."
)

OTP_BODY = (
    "Your GyanSankalp staff sign-in code is:\n\n    {code}\n\n"
    "It works once and stops working in {minutes} minutes.\n"
    "If you did not just try to sign in, tell the other staff - someone else "
    "reached the login page with your address."
)


def _has_sender() -> bool:
    return bool(settings.brevo_api_key or settings.smtp_host)


def _deliver(message: EmailMessage, to_email: str, label: str) -> bool:
    try:
        with smtplib.SMTP(
            settings.smtp_host, settings.smtp_port, timeout=SMTP_TIMEOUT_SECONDS
        ) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
    except Exception:
        log.exception("%s could not be sent to %s", label, to_email)
        return False
    return True


def _post(to_email: str, subject: str, body: str, label: str) -> bool:
    """Brevo's transactional API. The sender address is one you verified there."""
    name, address = parseaddr(settings.mail_from or "")
    try:
        response = httpx.post(
            BREVO_URL,
            headers={"api-key": settings.brevo_api_key or ""},
            json={
                "sender": {"name": name or "GyanSankalp", "email": address},
                "to": [{"email": to_email}],
                "subject": subject,
                "textContent": body,
            },
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except Exception:
        log.exception("%s could not be sent to %s", label, to_email)
        return False
    return True


def _send(to_email: str, subject: str, body: str, label: str) -> bool:
    """Hand the message to whichever of the two transports this server can reach."""
    if settings.brevo_api_key:
        return _post(to_email, subject, body, label)
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.mail_from or ""
    message["To"] = to_email
    message.set_content(body)
    return _deliver(message, to_email, label)


def send_verification(to_email: str, verify_url: str) -> bool:
    """Returns whether the message actually left this process."""
    if not _has_sender():
        # Development only: production refuses to boot without a sender, so the
        # link appears in the terminal for local testing.
        log.info(
            "verification link for %s (no mail sender configured, nothing was sent): %s",
            to_email,
            verify_url,
        )
        return False
    if not settings.mail_from:
        log.error("no sender address configured; no verification email sent")
        return False

    return _send(
        to_email,
        "Confirm your GyanSankalp email address",
        INTRO.format(url=verify_url, hours=settings.email_verify_hours),
        "verification link",
    )


def send_otp(to_email: str, code: str) -> bool:
    """Returns whether the staff member has any way to read the code.

    A code is the second lock on the admin panel, so it never reaches a log while
    the app believes it is production - the config guard already demands a sender
    there, and this is the belt on top of those braces. Development prints it so
    the flow can be tested without a mail account.
    """
    if not _has_sender():
        if settings.app_env == "production":
            log.error("staff code for %s was not sent: no mail sender is configured", to_email)
            return False
        log.info(
            "staff sign-in code for %s (no mail sender configured, nothing was sent): %s",
            to_email,
            code,
        )
        return True
    if not settings.mail_from:
        log.error("no sender address configured; no staff code sent")
        return False

    return _send(
        to_email,
        "GyanSankalp staff sign-in code",
        OTP_BODY.format(code=code, minutes=settings.admin_otp_minutes),
        "staff sign-in code",
    )
