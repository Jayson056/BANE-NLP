import sys
import os

# Setup path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from mcp.communication_tools import send_templated_email

def main():
    recipient = "jaysonc864@gmail.com"
    subject = "Formal Excuse Letter for Midterm Examination - JAYSON A. COMBATE"
    
    # Ang content ng letter
    message = """April 21, 2026

DEAN JOHN DUSTIN D. SANTOS
Dean, College of Computer and Information Sciences (CCIS)
Polytechnic University of the Philippines

Dear Dean Santos,

I am writing to formally request to be excused from my classes and the scheduled midterm examination for COMP 010 (Information Management) today, April 21, 2026.

I am currently unable to attend due to health reasons. Based on my medical consultation today with Dr. Ann Jelika A. Dionela, I have been diagnosed with Migraine and Acute Viral Illness. My physician has strictly recommended 1 to 2 days of rest for my recovery.

Attached to this letter is my Medical Certificate as official documentation of my condition.

I would also like to inform your office that I have already sent a formal email to my subject professor, Ma’am Lanie, to notify her of my absence and the situation. I remain fully committed to taking a special examination or completing any missed academic requirements as soon as my health permits.

Thank you for your kind consideration and understanding regarding this matter.

Respectfully yours,

JAYSON A. COMBATE
Student, BSIT 2-3
Polytechnic University of the Philippines"""
    
    print(f"Sending formal excuse letter to {recipient}...")
    result = send_templated_email(recipient, subject, message)
    print("SUCCESS: Result returned from tool.")

if __name__ == "__main__":
    main()
