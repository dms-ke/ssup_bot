import os
from datetime import datetime
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import database

app = Flask(__name__)

# Initialize DB on startup
database.init_db()

def is_expired(expiry_date_str):
    """Helper to check if the expiry date has passed."""
    if not expiry_date_str: 
        return False
    expiry = datetime.strptime(expiry_date_str, '%Y-%m-%d')
    return datetime.now() > expiry

@app.route('/bot', methods=['POST'])
def bot():
    # 1. Get incoming data
    incoming_msg = request.values.get('Body', '').strip()
    sender_number = request.values.get('From', '').replace('whatsapp:', '')
    
    resp = MessagingResponse()
    msg = resp.message()

    # --- LOGIC BRANCH 1: REGISTRATION (Shop Owner) ---
    # Format: REGISTER | Shop Name | Catalog Link | Map Link | Pay Info | Hours
    if incoming_msg.upper().startswith('REGISTER'):
        try:
            parts = incoming_msg.split('|')
            if len(parts) < 6:
                msg.body("⚠️ Format Error! \n\n"
                         "To Register, Send:\n"
                         "REGISTER | Shop Name | Catalog Link | Map Link | Payment Info | Operating Hours")
                return str(resp)

            _, shop_name, catalog, location, payment, hours = [p.strip() for p in parts]
            
            success, result = database.add_shop(sender_number, shop_name, catalog, location, payment, hours)
            
            if success:
                msg.body(f"✅ *{shop_name}* is LIVE!\n\n"
                         f"📅 Trial valid until: {result}\n\n"
                         f"Tell your customers to text: *VIEW {shop_name}* to this number.")
            else:
                msg.body(f"❌ Error registering: {result}")
                
        except Exception as e:
            msg.body(f"System Error: {str(e)}")
        
        return str(resp)

    # --- LOGIC BRANCH 2: RENEWAL (Shop Owner) ---
    # NOTE: In production, this should be triggered by a Payment Webhook (e.g., M-Pesa), not a manual text.
    elif incoming_msg.upper() == 'RENEW':
        success, new_date = database.renew_subscription(sender_number)
        if success:
            msg.body(f"✅ Subscription Renewed!\n\nNew Expiry: {new_date}")
        else:
            msg.body("❌ Account not found. Please REGISTER first.")
        return str(resp)

    # --- LOGIC BRANCH 3: OWNER STATUS CHECK ---
    elif incoming_msg.upper() == 'STATUS':
        existing_shop = database.get_shop(sender_number)
        if existing_shop:
            # Check if expired
            status_icon = "❌ Suspended" if is_expired(existing_shop[6]) else "✅ Active"
            msg.body(f"🏢 *{existing_shop[1]}*\n"
                     f"📅 Expiry: {existing_shop[6]}\n"
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
                 "2. Check Status: 'STATUS'")

    return str(resp)

if __name__ == '__main__':
    app.run(debug=True)