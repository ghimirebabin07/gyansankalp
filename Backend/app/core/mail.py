"""Outgoing mail: SMTP when it is configured, the log when it is not.

A failed send never fails the request that triggered it for a verification link -
the account is already committed, so the student presses "send again" instead of
losing it to a mail server that was down for ninety seconds.

A staff sign-in code is the opposite: if the code cannot be delivered there is
nothing to type, and pretending otherwise would leave a login half-done.
"""

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

log = logging.getLogger(__name__)

SMTP_TIMEOUT_SECONDS = 10

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


def send_verification(to_email: str, verify_url: str) -> bool:
    """Returns whether the message actually left this process."""
    if not settings.smtp_host:
        # APP_ENV=production refuses to boot without SMTP_HOST, so this branch is
        # development only: the link appears in the terminal for local testing.
        log.info(
            "verification link for %s (SMTP_HOST is not set, nothing was sent): %s",
            to_email,
            verify_url,
        )
        return False
    if not settings.mail_from:
        log.error("SMTP_HOST is set but MAIL_FROM is not; no verification email sent")
        return False

    message = EmailMessage()
    message["Subject"] = "Confirm your GyanSankalp email address"
    message["From"] = settings.mail_from
    message["To"] = to_email
    message.set_content(
        INTRO.format(url=verify_url, hours=settings.email_verify_hours)
    )
    return _deliver(message, to_email, "verification link")


def send_otp(to_email: str, code: str) -> bool:
    """Returns whether the staff member has any way to read the code.

    A code is the second lock on the admin panel, so it never reaches a log while
    the app believes it is production - the config guard already demands SMTP
    there, and this is the belt on top of those braces. Development prints it so
    the flow can be tested without a mail account.
    """
    if not settings.smtp_host:
        if settings.app_env == "production":
            log.error("staff code for %s was not sent: SMTP_HOST is not set", to_email)
            return False
        log.info(
            "staff sign-in code for %s (SMTP_HOST is not set, nothing was sent): %s",
            to_email,
            code,
        )
        return True
    if not settings.mail_from:
        log.error("SMTP_HOST is set but MAIL_FROM is not; no staff code sent")
        return False

    message = EmailMessage()
    message["Subject"] = "GyanSankalp staff sign-in code"
    message["From"] = settings.mail_from
    message["To"] = to_email
    message.set_content(OTP_BODY.format(code=code, minutes=settings.admin_otp_minutes))
    return _deliver(message, to_email, "staff sign-in code")
