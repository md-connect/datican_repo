# test_gmail_final.py
import smtplib
import ssl
import certifi

print("=== Testing Gmail Connection with Certifi ===")
print(f"Using certifi certificates from: {certifi.where()}")

# Test configuration
test_configs = [
    {
        'method': 'TLS (port 587)',
        'port': 587,
        'use_tls': True,
        'use_ssl': False,
        'function': lambda: smtplib.SMTP('smtp.gmail.com', 587)
    },
    {
        'method': 'SSL (port 465)', 
        'port': 465,
        'use_tls': False,
        'use_ssl': True,
        'function': lambda: smtplib.SMTP_SSL('smtp.gmail.com', 465)
    }
]

for config in test_configs:
    print(f"\n--- Testing {config['method']} ---")
    try:
        # Create SSL context with certifi
        context = ssl.create_default_context(cafile=certifi.where())
        
        if config['use_ssl']:
            # SSL connection
            server = smtplib.SMTP_SSL('smtp.gmail.com', config['port'], context=context)
        else:
            # TLS connection  
            server = smtplib.SMTP('smtp.gmail.com', config['port'])
            server.starttls(context=context)
        
        # Try login with password WITHOUT spaces
        password = 'hoowicpekknteogn'  # No spaces
        server.login('info.datican@gmail.com', password)
        
        print(f"✅ {config['method']}: SUCCESS!")
        server.quit()
        
        # If successful, this is your working config
        print(f"\n✅ Use this configuration in settings.py:")
        print(f"   EMAIL_PORT = {config['port']}")
        print(f"   EMAIL_USE_TLS = {config['use_tls']}")
        print(f"   EMAIL_USE_SSL = {config['use_ssl']}")
        break
        
    except Exception as e:
        print(f"❌ {config['method']}: FAILED - {e}")