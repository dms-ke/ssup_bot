import requests
import json
import base64
from datetime import datetime

# --- CONFIGURATION ---
# Using keys from your uploaded file
CONSUMER_KEY = "rrGeUnVZaFrJHsKNdmiV8PAyjYJJ8St54Z96T7lb2Xp6qlTz"
CONSUMER_SECRET = "f1BTs1O6Yoz8MFiqxHGPGfbLAjFfk2dAWNtNpyN28zW12cUlUTfivcymXM143Ydy"
BUSINESS_SHORTCODE = "174379"           # Sandbox Paybill (C2B)
PASSKEY = "bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919" 
CALLBACK_URL = "https://ssup-bot.onrender.com/mpesa_callback"

# --- NEW: B2C CONFIGURATION (For Withdrawals) ---
B2C_SHORTCODE = "600996" # Sandbox B2C Shortcode
INITIATOR_NAME = "testapi"
# NOTE: In Production, you must generate this using your Certificate.
# For Sandbox, this is the credential for 'testapi'
SECURITY_CREDENTIAL = "ClU+... (You need to get the long Sandbox string from Safaricom Developer Portal > APIs > B2C > Simulate)"

def get_access_token():
    """Authenticates with Safaricom."""
    api_url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    r = requests.get(api_url, auth=(CONSUMER_KEY, CONSUMER_SECRET))
    return r.json().get('access_token')

def trigger_stk_push(phone_number, amount=1):
    """
    Initiates the payment prompt (Customer -> Business).
    """
    access_token = get_access_token()
    api_url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
    
    headers = { "Authorization": f"Bearer {access_token}" }
    
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    password_str = BUSINESS_SHORTCODE + PASSKEY + timestamp
    password = base64.b64encode(password_str.encode()).decode()
    
    payload = {
        "BusinessShortCode": BUSINESS_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(amount),
        "PartyA": phone_number,
        "PartyB": BUSINESS_SHORTCODE,
        "PhoneNumber": phone_number,
        "CallBackURL": CALLBACK_URL,
        "AccountReference": "SaaSBot",
        "TransactionDesc": "Payment"
    }
    
    response = requests.post(api_url, json=payload, headers=headers)
    return response.json()

def pay_shop_owner(phone_number, amount):
    """
    Sends money from Business -> Shop Owner (Withdrawal).
    """
    access_token = get_access_token()
    api_url = "https://sandbox.safaricom.co.ke/mpesa/b2c/v1/paymentrequest"
    headers = { "Authorization": f"Bearer {access_token}" }

    payload = {
        "InitiatorName": INITIATOR_NAME,
        "SecurityCredential": SECURITY_CREDENTIAL, # Ensure this is populated
        "CommandID": "BusinessPayment",
        "Amount": int(amount), 
        "PartyA": B2C_SHORTCODE,       # Sending FROM B2C Shortcode
        "PartyB": phone_number,        # Sending TO Shop Owner
        "Remarks": "Withdrawal",
        "QueueTimeOutURL": CALLBACK_URL, 
        "ResultURL": CALLBACK_URL,
        "Occasion": ""
    }
    
    response = requests.post(api_url, json=payload, headers=headers)
    return response.json()