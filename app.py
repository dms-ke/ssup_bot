import os
import logging
from datetime import datetime
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse

# Local imports
import database
import mpesa

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize DB
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
    Main entry point for WhatsApp messages.
    """
    incoming_msg = request.values.get('Body', '').strip().upper()
    sender_number = request.values.get('From', '') 
    
    resp = MessagingResponse()
    msg = resp.message()

    # --- 1. INTELLIGENT HELP SYSTEM ---
    if incoming_msg == 'HELP':
        # Check if this user is a shop owner
        shop = database.get_shop(sender_number)
        
        if shop:
            # === OWNER MENU ===
            msg.body(f"👋 *Hello {shop[1]} Owner!*\n\n"
                     "Here are your management commands:\n"
                     "--------------------------------\n"
                     "📊 *STATUS* - Check subscription & details\n"
                     "💰 *PAY* - Renew your subscription\n"
                     "📝 *UPDATE* - Change details\n"
                     "   Format: UPDATE | FIELD | VALUE\n"
                     "   (e.g., UPDATE | HOURS | 8am-8pm)\n"
                     "--------------------------------\n"
                     "Need support? Contact Admin at https://dms-23bq.vercel.app/")
        else:
            # === CUSTOMER / NEW USER MENU ===
            msg.body("🤖 *Welcome to Dtekk ShopBot Help*\n\n"
                     "🛍️ *I want to find a shop:*\n"
                     "Text: *VIEW [Shop Name]*\n"
                     "(Example: VIEW Mama Mboga)\n\n"
                     "💼 *I am a Shop Owner:*\n"
                     "To put your business online, text:\n"
                     "*REGISTER | Name | Menu Link | Map | Pay Info | Hours*")
        
        return str(resp)

    # --- 2. WELCOME HANDLER (Hi, Hello, Start) ---
    GREETINGS = ['HI', 'HELLO', 'START', 'JAMBO', 'HEY']
    if incoming_msg in GREETINGS:
        msg.body("👋 *Welcome to ShopBot!*\n\n"
                 "Are you a Customer or a Shop Owner?\n\n"
                 "👉 Text *HELP* to see what I can do.")
        return str(resp)


    # --- 3. REGISTRATION (Shop Owner) ---
    if incoming_msg.startswith('REGISTER'):
        try:
            parts = incoming_msg.split('|')
            if len(parts) < 6:
                msg.body("⚠️ *Format Error!* \n\n"
                         "Please copy, paste and edit this format:\n\n"
                         "REGISTER | My Shop | www.link.com | Nairobi | Mpesa 07XX | 8am-5pm")
                return str(resp)

            _, shop_name, catalog, location, payment, hours = [p.strip() for p in parts]
            
            success, result = database.add_shop(sender_number, shop_name, catalog, location, payment, hours)
            
            if success:
                msg.body(f"✅ *{shop_name}* is LIVE!\n\n"
                         f"📅 Trial valid until: {result}\n\n"
                         f"👉 Text *STATUS* to see your dashboard.")
            else:
                msg.body(f"❌ Error registering: {result}")
                
        except Exception as e:
            app.logger.error(f"Registration Error: {e}")
            msg.body("System Error.")
        
        return str(resp)

    # --- 4. PAYMENT (Shop Owner) ---
    elif incoming_msg == 'PAY':
        shop = database.get_shop(sender_number)
        if not shop:
            msg.body("❌ You are not registered. Text *HELP* for instructions.")
            return str(resp)

        mpesa_phone = sender_number.replace('whatsapp:', '').replace('+', '')
        
        try:
            # Trigger STK Push (1 KES)
            response = mpesa.trigger_stk_push(mpesa_phone, amount=1)
            
            if response.get('ResponseCode') == '0':
                msg.body("📲 *Payment Initiated*\n\n"
                         "Please enter your M-Pesa PIN when prompted.")
            else:
                msg.body(f"❌ M-Pesa Error: {response.get('ResponseDescription')}")
                
        except Exception as e:
            app.logger.error(f"Payment Error: {e}")
            msg.body("❌ System Error. Try again later.")
            
        return str(resp)
        
    # --- 4.5 UPDATE DETAILS (New Feature) ---
    # Format: UPDATE | FIELD | NEW VALUE
    elif incoming_msg.startswith('UPDATE'):
        # 1. Parse the command
        parts = incoming_msg.split('|')
        
        # We need exactly 3 parts: Command, Field, Value
        if len(parts) < 3:
            msg.body("⚠️ *Update Format Error*\n\n"
                     "To update, use this format:\n"
                     "*UPDATE | FIELD | NEW VALUE*\n\n"
                     "Examples:\n"
                     "• UPDATE | HOURS | 9am - 9pm\n"
                     "• UPDATE | PAY | Till 123456\n"
                     "• UPDATE | CATALOG | www.newmenu.com")
            return str(resp)
        
        _, field_name, new_value = [p.strip() for p in parts]
        
        # 2. Call Database
        success, response_message = database.update_shop_field(sender_number, field_name, new_value)
        
        if success:
            msg.body(f"✅ {response_message}\n\n"
                     f"Text *STATUS* to see your changes.")
        else:
            msg.body(f"❌ Error: {response_message}")
            
        return str(resp)

    # --- 5. STATUS (Shop Owner) ---
    elif incoming_msg == 'STATUS':
        existing_shop = database.get_shop(sender_number)
        if existing_shop:
            expiry_date = existing_shop[6]
            is_active = not is_expired(expiry_date)
            status_txt = "✅ Active" if is_active else "❌ Suspended (Text PAY)"
            
            msg.body(f"🏢 *{existing_shop[1]}*\n"
                     f"📅 Expiry: {expiry_date}\n"
                     f"----------------\n"
                     f"Status: {status_txt}")
        else:
            msg.body("❌ You are not registered.\nText *HELP* to get started.")
        return str(resp)

    # --- 6. CUSTOMER VIEW (End User) ---
    elif incoming_msg.startswith('VIEW'):
        search_query = incoming_msg[5:].strip()
        
        shop = database.search_shop_by_name(search_query)
        
        if shop:
            expiry_date = shop[6]
            
            if is_expired(expiry_date):
                msg.body(f"⚠️ *Account Suspended*\n\n"
                         f"The shop '{shop[1]}' is currently inactive.\n"
                         f"Please notify the owner.")
            else:
                response_text = (
                    f"🏪 *{shop[1]}*\n"
                    f"📍 {shop[3]}\n"
                    f"🕒 {shop[5]}\n"
                    f"----------------\n"
                    f"📋 *Catalog*: {shop[2]}\n"
                    f"💳 *Pay*: {shop[4]}\n"
                    f"----------------\n"
                    f"Powered by Dtekk ShopBot"
                )
                msg.body(response_text)
        else:
            msg.body(f"❌ Could not find '{search_query}'.\n"
                     f"Text *HELP* if you are stuck.")
            
        return str(resp)

    # --- 7. FALLBACK / CATCH-ALL ---
    # If the user sends gibberish or a wrong command
    else:
        msg.body("🤔 I didn't understand that.\n\n"
                 "👉 Text *HELP* to see the menu.")

    return str(resp)

# --- M-PESA LISTENER (Unchanged) ---
@app.route('/mpesa_callback', methods=['POST'])
def mpesa_callback():
    data = request.json
    try:
        stk_callback = data.get('Body', {}).get('stkCallback', {})
        if stk_callback.get('ResultCode') == 0:
            meta_data = stk_callback.get('CallbackMetadata', {}).get('Item', [])
            phone_number = ""
            for item in meta_data:
                if item.get('Name') == 'PhoneNumber':
                    phone_number = str(item.get('Value'))
                    break
            
            if phone_number:
                db_phone_key = f"whatsapp:+{phone_number}"
                database.renew_subscription(db_phone_key)
                app.logger.info(f"✅ Renewed: {db_phone_key}")
    except Exception as e:
        app.logger.error(f"Callback Error: {e}")

    return "OK"

if __name__ == '__main__':
    app.run(debug=True)