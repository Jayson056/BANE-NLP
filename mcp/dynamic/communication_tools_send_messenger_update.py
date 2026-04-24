from mcp.mcp_registry import mcp_tool

@mcp_tool(name='communication_tools.send_messenger_update', description='Direct SMTP email sender.')
def send_messenger_update(recipient: str, subject: str, body: str):
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    import os

    sender_email = os.environ.get('GMAIL_USER')
    sender_password = os.environ.get('GMAIL_APP_PASSWORD')

    if not sender_email or not sender_password:
        return '❌ Error: Email credentials not found in environment.'

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
        return f'✅ Success: Email sent to {recipient}'
    except Exception as e:
        return f'❌ SMTP Error: {str(e)}'