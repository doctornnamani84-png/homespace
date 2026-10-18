"""Email notifications for booking lifecycle updates."""
import smtplib
from email.message import EmailMessage

from flask import current_app

from app.models import Booking


BOOKING_MESSAGES = {
    "pending": (
        "Booking request received",
        "A booking request has been created and is awaiting payment.",
    ),
    "confirmed": (
        "Booking confirmed",
        "Payment has been verified and this booking is confirmed.",
    ),
    "cancelled": (
        "Booking cancelled",
        "This booking has been cancelled.",
    ),
}


def send_booking_update(booking: Booking, event: str) -> bool:
    """Email both booking parties; log delivery failures without undoing a booking."""
    mail_server = current_app.config.get("MAIL_SERVER")
    mail_sender = current_app.config.get("MAIL_DEFAULT_SENDER")
    if not mail_server or not mail_sender:
        current_app.logger.warning(
            "Booking %s %s email was not sent because SMTP is not configured",
            booking.id,
            event,
        )
        return False

    subject, message_text = BOOKING_MESSAGES[event]
    recipients = {
        user.email: user.name
        for user in (booking.tenant, booking.property.landlord)
        if user is not None and user.email
    }
    body_template = (
        "Hello {name},\n\n{message}\n\n"
        "Property: {property_title}\n"
        "Dates: {start_date} to {end_date}\n"
        "Total: NGN {total_price:,.2f}\n\n"
        "Visit HomeSpace to view your booking.\n".format(
            name="{name}",
            message=message_text,
            property_title=booking.property.title,
            start_date=booking.start_date.isoformat(),
            end_date=booking.end_date.isoformat(),
            total_price=float(booking.total_price),
        )
    )

    try:
        with smtplib.SMTP(
            mail_server, current_app.config["MAIL_PORT"], timeout=15
        ) as smtp:
            if current_app.config["MAIL_USE_TLS"]:
                smtp.starttls()
            username = current_app.config.get("MAIL_USERNAME")
            if username:
                smtp.login(username, current_app.config.get("MAIL_PASSWORD", ""))
            for recipient, name in recipients.items():
                recipient_message = EmailMessage()
                recipient_message["Subject"] = f"{subject} — HomeSpace"
                recipient_message["From"] = mail_sender
                recipient_message["To"] = recipient
                recipient_message.set_content(body_template.format(name=name))
                smtp.send_message(recipient_message)
    except (OSError, smtplib.SMTPException, RuntimeError) as exc:
        current_app.logger.warning(
            "Booking %s %s email delivery failed (%s)",
            booking.id,
            event,
            type(exc).__name__,
        )
        return False
    return True
