import requests
import json
import base64
from datetime import datetime

# --- CONFIGURATION (Get these from developer.safaricom.co.ke) ---
# For Sandbox, use these defaults or create your own app
CONSUMER_KEY = "YOUR_CONSUMER_KEY"      # REPLACE THIS
CONSUMER_SECRET = "YOUR_CONSUMER_SECRET" # REPLACE THIS
BUSINESS_SHORTCODE = "174379"           # Sandbox Paybill
PASSKEY = "bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919" 
CALLBACK_URL = "https://your-app-name.onrender.com/mpesa_callback" # UPDATE THIS AFTER DEPLOY

def get_access_token():
    """Authenticates with Safaricom to get a temporary token."""
    api_url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    r = requests.get(api_url, auth=(CONSUMER_KEY, CONSUMER_SECRET))
    return r.json().get('access_token')

def trigger_stk_push(phone_number, amount=1):
    """
    Initiates the payment prompt on the user's phone.
    Note: Phone must be in format 2547XXXXXXXX
    """
    access_token = get_access_token()
    api_url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
    
    headers = { "Authorization": f"Bearer {access_token}" }
    
    # Generate Timestamp and Password required by Daraja
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    password_str = BUSINESS_SHORTCODE + PASSKEY + timestamp
    password = base64.b64encode(password_str.encode()).decode()
    
    payload = {
        "BusinessShortCode": BUSINESS_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": amount,
        "PartyA": phone_number,             # The phone sending money
        "PartyB": BUSINESS_SHORTCODE,       # The Paybill receiving money
        "PhoneNumber": phone_number,
        "CallBackURL": CALLBACK_URL,        # Safaricom sends the receipt here
        "AccountReference": "SaaSBot",
        "TransactionDesc": "Subscription Renewal"
    }
    
    response = requests.post(api_url, json=payload, headers=headers)
    return response.json()