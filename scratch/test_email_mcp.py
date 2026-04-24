import sys
import os
import asyncio

# Setup path to include project root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import the tool
from mcp.communication_tools import send_templated_email

def main():
    recipient = "jaysonc864@gmail.com"
    subject = "BANE NLP Template Verification"
    message = "Hello Jayson! This is a test email sent from BANE NLP using your new personalized template. The integration is successful and the signature is now active."
    
    print(f"Sending test email to {recipient}...")
    result = send_templated_email(recipient, subject, message)
    print(result)

if __name__ == "__main__":
    main()
