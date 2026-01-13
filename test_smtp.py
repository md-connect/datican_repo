# test_smtp.py
import smtplib
from email.mime.text import MIMEText

def test_smtp_connection():
    try:
        # Test connection
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login('info.datican@gmail.com', 'hoow icpe kknt eogn')
        print("✅ SMTP Connection successful!")
        
        # Test sending
        msg = MIMEText('Test email from DATICAN')
        msg['Subject'] = 'SMTP Test'
        msg['From'] = 'noreply@repo.datican.org'
        msg['To'] = 'mondayoke93@gmail.com'
        
        server.send_message(msg)
        print("✅ Test email sent successfully!")
        
        server.quit()
        return True
    except Exception as e:
        print(f"❌ SMTP Error: {e}")
        return False

if __name__ == "__main__":
    test_smtp_connection()