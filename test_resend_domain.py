# test_resend_domain.py
import requests
import os

API_KEY = "re_gC4Zo81u_bC9o5HsdsycxjWrU7CF1jhKb"
headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# Test 1: Check domain status
response = requests.get("https://api.resend.com/domains", headers=headers)
print("=== Domain Status ===")
if response.status_code == 200:
    domains = response.json()['data']
    for domain in domains:
        print(f"Domain: {domain['name']}")
        print(f"Status: {domain['status']}")
        print(f"Region: {domain['region']}")
        print(f"Created: {domain['created_at']}")
        print("---")
else:
    print(f"Error checking domains: {response.text}")

# Test 2: Send test email with your domain
print("\n=== Sending Test Email ===")
data = {
    "from": "no-reply@datican.org",  # Your verified domain
    "to": ["mondayoke93@gmail.com"],  # Your email
    "subject": "Domain Verification Test",
    "text": f"This is a test email from your verified domain datican.org",
    "headers": {
        "X-Entity-Ref-ID": "test-123"
    }
}

response = requests.post("https://api.resend.com/emails", headers=headers, json=data)
if response.status_code == 200:
    print(f"✅ Email sent successfully!")
    print(f"Email ID: {response.json()['id']}")
else:
    print(f"❌ Failed to send email: {response.status_code}")
    print(f"Error: {response.text}")