from mcp.mcp_registry import mcp_tool

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import os
from mcp.server.fastmcp import FastMCP

@mcp_tool()
def send_templated_email_fixed(recipient: str, subject: str, body: str, attachments: list = None) -> str:
    """Sends a professional email with fixes for syntax and variable errors."""
    smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
    smtp_port = int(os.getenv('SMTP_PORT', 587))
    sender_email = os.getenv('SENDER_EMAIL')
    sender_password = os.getenv('SENDER_PASSWORD')

    if not sender_email or not sender_password:
        return "Error: SMTP credentials not configured in environment."

    msg = MIMEMultipart()
    msg['From'] = f"BANE NLP <{sender_email}>"
    msg['To'] = recipient
    msg['Subject'] = subject

    # Use .replace outside the f-string to avoid backslash issues
    formatted_body = body.replace('\n', '<br>')
    
    html_body = f"""
    <html>
        <body style='font-family: Arial, sans-serif; line-height: 1.6; color: #333;'>
            <div style='max-width: 600px; margin: auto; border: 1px solid #ddd; padding: 20px; border-radius: 10px;'>
                <h2 style='color: #2c3e50;'>BANE NLP System Dispatch</h2>
                <p>{formatted_body}</p>
                <hr style='border: 0; border-top: 1px solid #eee;'>
                <footer style='font-size: 0.8em; color: #777;'>
                    This is an automated message from the BANE NLP Bridge Framework.
                </footer>
            </div>
        </body>
    </html>
    """
    msg.attach(MIMEText(html_body, 'html'))

    attached_count = 0
    safe_attachments = attachments if attachments is not None else []

    for file_path in safe_attachments:
        if os.path.exists(file_path):
            try:
                with open(file_path, "rb") as attachment:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(attachment.read())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f"attachment; filename={os.path.basename(file_path)}",
                )
                msg.attach(part)
                attached_count += 1
            except Exception as e:
                print(f"Failed to attach {file_path}: {e}")

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
        return f"Email successfully sent to {recipient} with {attached_count} attachments."
    except Exception as e:
        return f"SMTP Error: {str(e)}"
