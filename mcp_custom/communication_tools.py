import sys
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config
import sys, os; sys.path.insert(0, os.getcwd()) if os.getcwd() not in sys.path else None;
from mcp_custom.mcp_registry import mcp_custom_tool
from core.logger import log_event

def _send_raw_email(subject: str, body: str, recipient: str = None, attachments: list = None):
    to_email = recipient if recipient else config.SMTP_USER
    
    try:
        msg = MIMEMultipart()
        msg['From'] = f"{config.SMTP_SENDER_NAME} <{config.SMTP_USER}>"
        msg['To'] = to_email
        msg['Subject'] = subject

        # Detect HTML
        is_html = body.strip().startswith('<!DOCTYPE html>') or body.strip().startswith('<html>')
        subtype = 'html' if is_html else 'plain'
        msg.attach(MIMEText(body, subtype))

        # Handle Attachments (Robust parsing for AI errors)
        if attachments:
            if isinstance(attachments, str):
                # AI sometimes sends "['path']" or "'path'" instead of a list
                import ast
                try:
                    attachments = ast.literal_eval(attachments)
                except:
                    attachments = [attachments.strip("[]'\" ")]

            if not isinstance(attachments, list):
                attachments = [attachments]

            attached_count = 0
            from email.mime.base import MIMEBase
            from email import encoders
            for file_path in attachments:
                file_path = str(file_path).strip("[]'\" ")
                if not file_path or file_path == "\\": continue
                
                # Check absolute path first
                target_path = file_path
                if not os.path.exists(target_path):
                    # Fallback: Look in the known temp_media directory
                    fallback_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "channels", "temp_media")
                    potential_fallback = os.path.join(fallback_dir, os.path.basename(file_path))
                    if os.path.exists(potential_fallback):
                        target_path = potential_fallback
                    else:
                        log_event("SMTP_WARNING", f"Attachment not found at {file_path} or fallback.")
                        continue

                try:
                    part = MIMEBase('application', 'octet-stream')
                    with open(target_path, 'rb') as f:
                        part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header('Content-Disposition', f'attachment; filename="{os.path.basename(target_path)}"')
                    msg.attach(part)
                    attached_count += 1
                except Exception as e:
                    log_error("ATTACH_ERROR", f"Failed to attach {target_path}: {e}")

        server = smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT)
        server.starttls()
        server.login(config.SMTP_USER, config.SMTP_PASS)
        server.send_message(msg)
        server.quit()

        return f"✅ Successfully sent {subtype.upper()} email to {to_email} with {attached_count} file(s) attached."
    except Exception as e:
        return f"❌ SMTP Error: {str(e)}"

@mcp_custom_tool(
    name="communication_tools.send_templated_email", 
    description="Send a professional BANE-branded HTML email. INSTRUCTION: ALWAYS ASK the user if they need to attach files (e.g. PDF Medical Certificates) BEFORE calling this tool. If they say yes, tell them to upload the file first. Use 'attachments' parameter (list of paths) if files are provided."
)
def send_templated_email(recipient: str, subject: str, body: str, attachments: list = None):
    """
    Sends a high-quality HTML email using the BANE NLP Standard Template.
    Automatically replaces {{SUBJECT}} and {{MESSAGE}} in the template.
    """
    template_path = os.path.join(os.path.dirname(__file__), "templates", "email_standard.html")
    
    if not os.path.exists(template_path):
        return "❌ Error: Email template file not found."

    try:
        with open(template_path, "r", encoding="utf-8") as f:
            template_content = f.read()
        
        # Replace placeholders
        html_body = template_content.replace("{{SUBJECT}}", subject).replace("{{MESSAGE}}", body)
        
        # Use the existing raw email logic but with the template
        return _send_raw_email(subject=subject, body=html_body, recipient=recipient, attachments=attachments)
    except Exception as e:
        return f"❌ Error loading template: {str(e)}"

@mcp_custom_tool(name="communication_tools.send_telegram_message", description="Send a telegram message.")
def send_telegram_message(text: str, user_id: str = None):
    token = getattr(config, "TELEGRAM_TOKEN", None)
    users = getattr(config, "ALLOWED_TELEGRAM_USERS", [])
    chat_id = user_id if user_id else users
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        res = requests.post(url, json={'chat_id': chat_id, 'text': text, 'parse_mode': 'Markdown'})
        return f"✅ Message sent to Telegram."
    except Exception as e:
        return f"❌ Failed: {str(e)}"
