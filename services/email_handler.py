import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import config
from core.logger import log_event, log_error

def send_email(subject, body, to_email=None, is_html=False):
    """
    Sends an automated email using the configured SMTP settings.
    Supports both plain text and HTML content.
    """
    if not to_email:
        to_email = config.SMTP_USER  # Default to self

    try:
        msg = MIMEMultipart()
        msg['From'] = f"{config.SMTP_SENDER_NAME} <{config.SMTP_USER}>"
        msg['To'] = to_email
        msg['Subject'] = subject

        # Determine subtype based on is_html flag
        subtype = 'html' if is_html or body.strip().startswith('<!DOCTYPE html>') or body.strip().startswith('<html>') else 'plain'
        msg.attach(MIMEText(body, subtype))

        # Initialize connection
        server = smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT)
        server.starttls()
        server.login(config.SMTP_USER, config.SMTP_PASS)
        
        server.send_message(msg)
        server.quit()

        log_event("SMTP", f"Email sent successfully to {to_email} (Type: {subtype}): {subject}")
        return True

    except Exception as e:
        log_error("SMTP", f"Failed to send email: {e}")
        return False
