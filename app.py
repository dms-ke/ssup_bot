import os
import logging
from datetime import datetime
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse

# Local imports
import database
import mpesa

app = Flask(__name__)

# Configure logging to see errors in Render Dashboard
logging.basicConfig(level=logging.INFO)

# Initialize DB on startup
database.init_db()

def is_expired(expiry_date_str):
    """Helper to check if the expiry date has passed."""
    if not expiry_date_str: 
        return False
    try:
        expiry = datetime.strptime(expiry_date_str, '%Y-%m-%d')
        return datetime.now() > expiry
    except ValueError:
        return False

@app.route('/bot', methods=['POST'])
def bot():
    """
    Main entry point for WhatsApp messages via Twilio.
    """
    # 1. Get incoming data
    incoming_msg = request.values.get('Body', '').strip()
    # Sender format from Twilio is usually 'whatsapp:+2547XXXXXXXX'
    sender_number = request.values.get('From', '') 
    
    resp = MessagingResponse()
    msg = resp.message()

    # --- LOGIC BRANCH 1: REGISTRATION (Shop Owner) ---
    # Format: REGISTER | Shop Name | Catalog Link | Map Link | Pay Info | Hours
    if incoming_msg.upper().startswith('REGISTER'):
        try:
            parts = incoming_msg.split('|')
            if len(parts) < 6:
                msg.body("⚠️ *Format Error!* \n\n"
                         "To Register, Send:\n"
                         "REGISTER | Shop Name | Catalog Link | Map Link | Payment Info | Operating Hours")
                return str(resp)

            _, shop_name, catalog, location, payment, hours = [p.strip() for p in parts]
            
            # Save to DB (Primary Key is the full 'whatsapp:+254...' string)
            success, result = database.add_shop(sender_number, shop_name, catalog, location, payment, hours)
            
            if success:
                msg.body(f"✅ *{shop_name}* is LIVE!\n\n"
                         f"📅 Trial valid until: {result}\n\n"
                         f"Tell your customers to text: *VIEW {shop_name}* to this number.")
            else:
                msg.body(f"❌ Error registering: {result}")
                
        except Exception as e:
            app.logger.error(f"Registration Error: {e}")
            msg.body("System Error during registration.")
        
        return str(resp)

    # --- LOGIC BRANCH 2: PAYMENT TRIGGER (Shop Owner) ---
    # User texts 'PAY' to initiate M-Pesa STK Push
    elif incoming_msg.upper() == 'PAY':
        # 1. Check if user exists first
        shop = database.get_shop(sender_number)
        if not shop:
            msg.body("❌ You are not registered. Send the REGISTER command first.")
            return str(resp)

        # 2. Format number for M-Pesa (Remove 'whatsapp:+' and ensure it starts with 254)
        # Example: 'whatsapp:+254712345678' -> '254712345678'
        mpesa_phone = sender_number.replace('whatsapp:', '').replace('+', '')
        
        try:
            # Trigger STK Push (Amount set to 1 KES for testing)
            # In production, change amount=500 or your subscription price
            app.logger.info(f"Triggering STK Push for {mpesa_phone}")
            response = mpesa.trigger_stk_push(mpesa_phone, amount=1)
            
            if response.get('ResponseCode') == '0':
                msg.body("📲 *Payment Initiated*\n\n"
                         "1. Check your phone for the M-Pesa prompt.\n"
                         "2. Enter your PIN.\n"
                         "3. Wait for the confirmation SMS.\n\n"
                         "Once paid, text *STATUS* to see your new expiry date.")
            else:
                error_desc = response.get('ResponseDescription', 'Unknown Error')
                msg.body(f"❌ Failed to initiate payment: {error_desc}")
                
        except Exception as e:
            app.logger.error(f"Payment Error: {e}")
            msg.body("❌ System Error initiating payment. Please try again later.")
            
        return str(resp)

    # --- LOGIC BRANCH 3: OWNER STATUS CHECK ---
    elif incoming_msg.upper() == 'STATUS':
        existing_shop = database.get_shop(sender_number)
        if existing_shop:
            expiry_date = existing_shop[6]
            is_active = not is_expired(expiry_date)
            status_icon = "✅ Active" if is_active else "❌ Suspended (Text PAY to renew)"
            
            msg.body(f"🏢 *{existing_shop[1]}*\n"
                     f"📅 Expiry: {expiry_date}\n"
                     f"Status: {status_icon}")
        else:
            msg.body("You are not registered.")
        return str(resp)

    # --- LOGIC BRANCH 4: CUSTOMER VIEW (End User) ---
    # Format: VIEW [Shop Name]
    elif incoming_msg.upper().startswith('VIEW'):
        search_query = incoming_msg[5:].strip() # Remove "VIEW "
        
        shop = database.search_shop_by_name(search_query)
        
        if shop:
            expiry_date = shop[6]
            
            # --- THE GATEKEEPER CHECK ---
            if is_expired(expiry_date):
                msg.body(f"⚠️ *Account Suspended*\n\n"
                         f"The shop '{shop[1]}' has an inactive subscription.\n"
                         f"Please tell the shop owner to renew their service.")
            else:
                # Active subscription: Show details
                response_text = (
                    f"🏪 *{shop[1]}*\n"
                    f"📍 Location: {shop[3]}\n"
                    f"🕒 Hours: {shop[5]}\n"
                    f"----------------\n"
                    f"📋 *Catalog*: {shop[2]}\n"
                    f"💳 *Pay*: {shop[4]}\n"
                    f"----------------\n"
                    f"Powered by YourSaaSName"
                )
                msg.body(response_text)
        else:
            msg.body(f"❌ Could not find a shop named '{search_query}'. Please check the spelling.")
            
        return str(resp)

    # --- DEFAULT HELP MESSAGE ---
    else:
        msg.body("🤖 *Welcome to ShopBot SaaS*\n\n"
                 "🛍️ **Customers:** Text 'VIEW [Shop Name]'\n\n"
                 "💼 **Shop Owners:**\n"
                 "1. Register: 'REGISTER | Name | Menu Link | Map | Pay Info | Hours'\n"
                 "2. Pay: Text 'PAY' to renew subscription\n"
                 "3. Status: Text 'STATUS'")

    return str(resp)


# --- ROUTE 2: M-PESA CALLBACK (The Listener) ---
@app.route('/mpesa_callback', methods=['POST'])
def mpesa_callback():
    """
    Safaricom hits this endpoint automatically when a user pays.
    We parse the JSON and update the database.
    """
    data = request.json
    app.logger.info(f"M-Pesa Callback Received: {data}")
    
    try:
        # Navigate the nested JSON structure
        stk_callback = data.get('Body', {}).get('stkCallback', {})
        result_code = stk_callback.get('ResultCode')
        
        # ResultCode 0 means Successful Payment
        if result_code == 0:
            meta_data = stk_callback.get('CallbackMetadata', {}).get('Item', [])
            phone_number = ""
            
            # Extract phone number from metadata
            for item in meta_data:
                if item.get('Name') == 'PhoneNumber':
                    phone_number = str(item.get('Value'))
                    break
            
            if phone_number:
                # M-Pesa returns '2547...', but our DB uses 'whatsapp:+2547...'
                # We need to format it back to match the Primary Key in SQLite
                db_phone_key = f"whatsapp:+{phone_number}"
                
                # Renew the subscription
                success, new_date = database.renew_subscription(db_phone_key)
                
                if success:
                    app.logger.info(f"✅ Subscription auto-renewed for {db_phone_key} until {new_date}")
                else:
                    app.logger.warning(f"❌ Payment received for {db_phone_key} but phone not found in DB.")
        else:
            app.logger.warning("❌ Payment Failed or Cancelled by user.")

    except Exception as e:
        app.logger.error(f"Error processing callback: {e}")

    # Always return a 200 OK to Safaricom/Render
    return "OK"

if __name__ == '__main__':
    app.run(debug=True)