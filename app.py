import os
import logging
from datetime import datetime, timedelta # <--- Added timedelta
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client # <--- Added Client

# Local imports
import database
import mpesa

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
database.init_db()

# CONFIGURATION
MIN_WITHDRAWAL = 50 

# TWILIO CREDENTIALS (REQUIRED FOR REMINDERS)
# Get these from your Twilio Console Dashboard
TW_SID = os.environ.get("TWILIO_SID", "YOUR_TWILIO_ACCOUNT_SID")
TW_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "YOUR_TWILIO_AUTH_TOKEN")
TW_NUMBER = "whatsapp:+14155238886" # Your Twilio Sandbox Number

def is_expired(expiry_date_str):
    if not expiry_date_str: return False
    try:
        expiry = datetime.strptime(expiry_date_str, '%Y-%m-%d')
        return datetime.now() > expiry
    except ValueError:
        return False

# --- NEW: AUTOMATIC REMINDER ENDPOINT ---
# Set up a Cron Job to hit this URL (e.g., https://your-app.com/cron/send_reminders) daily
@app.route('/cron/send_reminders', methods=['GET'])
def send_reminders():
    try:
        # 1. Calculate "Tomorrow's Date"
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        
        # 2. Get shops expiring tomorrow
        expiring_shops = database.get_shops_expiring_on(tomorrow)
        
        if not expiring_shops:
            return f"No shops expiring on {tomorrow}."

        # 3. Initialize Twilio Client
        client = Client(TW_SID, TW_TOKEN)
        
        count = 0
        for phone, name in expiring_shops:
            try:
                # 4. Send the Active Message
                msg_body = (f"⚠️ *Urgent Reminder*\n\n"
                            f"Hello {name}, your shop subscription expires tomorrow ({tomorrow})!\n"
                            f"To keep your shop online, please text *PAY* to renew now.")
                
                # Phone comes from DB as 'whatsapp:+254...', which is what Twilio needs
                message = client.messages.create(
                    body=msg_body,
                    from_=TW_NUMBER,
                    to=phone 
                )
                app.logger.info(f"Reminder sent to {name}: {message.sid}")
                count += 1
            except Exception as e:
                app.logger.error(f"Failed to msg {name}: {e}")

        return f"✅ Cron Job Complete. Sent {count} reminders for {tomorrow}."
        
    except Exception as e:
        app.logger.error(f"Cron Error: {e}")
        return f"❌ Error: {e}"


@app.route('/bot', methods=['POST'])
def bot():
    # --- 1. DUAL INPUT HANDLING ---
    # raw_msg: Preserves case (e.g., "Mama's Cafe", "http://mylink.com")
    # command_msg: Uppercase for logic checks (e.g., "REGISTER", "HELP")
    raw_msg = request.values.get('Body', '').strip()
    command_msg = raw_msg.upper()
    sender_number = request.values.get('From', '') 
    
    resp = MessagingResponse()
    msg = resp.message()

    # --- 2. INTELLIGENT HELP SYSTEM ---
    if command_msg == 'HELP':
        shop = database.get_shop(sender_number)
        if shop:
            msg.body(f"👋 *Hello {shop[1]} Owner!*\n\n"
                     "Here is your menu:\n"
                     "--------------------------------\n"
                     "📊 *STATUS* - View Wallet & Expiry\n"
                     "💸 *WITHDRAW* - Cash out to M-Pesa\n"
                     "💰 *PAY* - Renew Subscription\n"
                     "📝 *UPDATE* - Edit Details\n"
                     "   Format: UPDATE | FIELD | VALUE\n"
                     "   (e.g., UPDATE | HOURS | 8am-8pm)\n"
                     "--------------------------------\n"
                     "Need support? Contact Admin at https://dms-23bq.vercel.app/ OR +254703903056")
        else:
            msg.body("🤖 *Welcome to Dtekk ShopBot Help*\n\n"
                     "🛍️ *Customers:*\n"
                     "• To Buy: *BUY | Shop Name | Amount*\n"
                     "• To View: *VIEW [Shop Name]*\n\n"
                     "💼 *Shop Owners:*\n"
                     "• To Join: *REGISTER | Name | Link | Map | Pay Info | Hours*")
        return str(resp)
    
     # --- 2. WELCOME HANDLER (Hi, Hello, Start) ---
    GREETINGS = ['HI', 'HELLO', 'START', 'JAMBO', 'HEY']
    if command_msg in GREETINGS:
        msg.body("👋 *Welcome to ShopBot!*\n\n"
                 "Are you a Customer or a Shop Owner?\n\n"
                 "👉 Text *HELP* to see what I can do.")
        return str(resp)

    # --- 3. REGISTRATION (ROBUST) ---
    if command_msg.startswith('REGISTER'):
        try:
            # FIX: Limit split to 5. This handles if user puts '|' inside the hours/desc
            parts = raw_msg.split('|', 5)
            
            if len(parts) < 6:
                msg.body("⚠️ *Format Error!* Use:\n"
                         "REGISTER | Name | Link | Map | Pay Info | Hours")
                return str(resp)

            # We slice [1:] effectively because the first part is the command 'REGISTER'
            # But safer to unpack manually:
            _, shop_name, catalog, location, payment, hours = [p.strip() for p in parts]
            
            success, result = database.add_shop(sender_number, shop_name, catalog, location, payment, hours)
            
            if success:
                msg.body(f"✅ *{shop_name}* is LIVE!\nTrial until: {result}\nText *STATUS* to see dashboard.")
            else:
                msg.body(f"❌ Error: {result}")
        except Exception as e:
            msg.body("System Error. Ensure you used the '|' separator.")
        return str(resp)

    # --- 4. CUSTOMER BUY (Money IN) ---
    elif command_msg.startswith('BUY'):
        try:
            # Use raw_msg so specific casing in shop names might be respected (depending on DB search)
            parts = raw_msg.split('|')
            if len(parts) < 3:
                msg.body("⚠️ Format: *BUY | Shop Name | Amount*")
                return str(resp)

            _, shop_query, amount_str = [p.strip() for p in parts]
            shop = database.search_shop_by_name(shop_query)
            
            if not shop:
                msg.body(f"❌ Shop '{shop_query}' not found.")
                return str(resp)
            
            amount = float(amount_str)
            customer_phone = sender_number.replace('whatsapp:', '').replace('+', '')
            
            # 1. Trigger STK Push
            res = mpesa.trigger_stk_push(customer_phone, int(amount))
            
            if res.get('ResponseCode') == '0':
                # 2. LOG PENDING TRANSACTION
                checkout_id = res.get('CheckoutRequestID')
                target_shop_phone = shop[0] 
                
                database.log_pending_transaction(checkout_id, sender_number, 'PURCHASE', target_shop_phone, amount)
                
                msg.body(f"📲 *Payment Initiated*\n"
                         f"Paying KES {amount} to {shop[1]}.\n"
                         f"Enter PIN to complete.")
            else:
                msg.body("❌ Payment Failed. Try again.")
                
        except ValueError:
            msg.body("❌ Amount must be a number.")
        except Exception as e:
            app.logger.error(f"Buy Error: {e}")
            msg.body("System Error.")
        return str(resp)

    # --- 5. SECURE WITHDRAWAL (Money OUT) ---
    elif command_msg == 'WITHDRAW':
        shop = database.get_shop(sender_number)
        if not shop:
            msg.body("❌ Not registered.")
            return str(resp)
            
        current_balance = shop[7]
        
        if current_balance < MIN_WITHDRAWAL:
            msg.body(f"❌ Balance too low (KES {current_balance}).\nMinimum withdrawal is KES {MIN_WITHDRAWAL}.")
            return str(resp)
        
        # INTEGRITY CHECK: Prevent double-withdrawals
        if database.check_pending_withdrawal(sender_number):
            msg.body("⚠️ Withdrawal already in progress. Please wait.")
            return str(resp)
            
        clean_phone = sender_number.replace('whatsapp:', '').replace('+', '')
        
        # 1. Trigger B2C (Do NOT debit yet)
        b2c_res = mpesa.pay_shop_owner(clean_phone, current_balance)
        
        # 2. Log Pending
        # B2C returns ConversationID or OriginatorConversationID
        req_id = b2c_res.get('ConversationID', f"W_{datetime.now().timestamp()}")
        
        database.log_pending_transaction(req_id, sender_number, 'WITHDRAWAL', amount=current_balance)
        
        msg.body(f"⏳ *Processing Withdrawal...*\n"
                 f"Requesting KES {current_balance}.\n"
                 f"You will receive an M-Pesa SMS shortly.")
        return str(resp)

    # --- 6. SUBSCRIPTION PAYMENT ---
    elif command_msg == 'PAY':
        shop = database.get_shop(sender_number)
        if not shop:
            msg.body("❌ Not registered.")
            return str(resp)

        mpesa_phone = sender_number.replace('whatsapp:', '').replace('+', '')
        res = mpesa.trigger_stk_push(mpesa_phone, amount=1)
        
        if res.get('ResponseCode') == '0':
            checkout_id = res.get('CheckoutRequestID')
            database.log_pending_transaction(checkout_id, sender_number, 'SUBSCRIPTION')
            msg.body("📲 Enter M-Pesa PIN to renew.")
        else:
            msg.body("❌ Payment Failed.")
        return str(resp)

    # --- 7. UPDATE DETAILS (Uses raw_msg) ---
    elif command_msg.startswith('UPDATE'):
        # raw_msg split preserves "8am-5pm" instead of "8AM-5PM"
        parts = raw_msg.split('|')
        if len(parts) < 3:
            msg.body("⚠️ Use: UPDATE | FIELD | VALUE")
            return str(resp)
        _, field, val = [p.strip() for p in parts]
        
        # database.py handles the field name capitalization (field.upper()),
        # so passing raw 'field' is safe. 'val' is passed raw to preserve case.
        success, res = database.update_shop_field(sender_number, field.upper(), val)
        msg.body(f"✅ {res}" if success else f"❌ {res}")
        return str(resp)

    # --- 8. STATUS ---
    elif command_msg == 'STATUS':
        existing_shop = database.get_shop(sender_number)
        if existing_shop:
            msg.body(f"🏢 *{existing_shop[1]} Dashboard*\n"
                     f"💰 *Wallet: KES {existing_shop[7]}*\n" 
                     f"📅 Expiry: {existing_shop[6]}\n"
                     f"----------------\n"
                     f"To cash out, text *WITHDRAW*")
        else:
            msg.body("❌ Not registered.")
        return str(resp)

    # --- 9. VIEW & FALLBACK ---
    elif command_msg.startswith('VIEW'):
        # Slice the raw message to keep the search query casing clean
        # e.g. "VIEW Mama Mboga" -> query = "Mama Mboga"
        query = raw_msg[5:].strip()
        shop = database.search_shop_by_name(query)
        if shop:
            if is_expired(shop[6]):
                msg.body(f"⚠️ {shop[1]} is currently unavailable.")
            else:
                msg.body(f"🏪 *{shop[1]}*\n📍 {shop[3]}\n🕒 {shop[5]}\n"
                         f"📋 Catalog: {shop[2]}\n"
                         f"💳 Pay: {shop[4]}\n\n"
                         f"👉 To buy, text: *BUY | {shop[1]} | Amount*")
        else:
            msg.body("❌ Shop not found.")
        return str(resp)
    
    else:
        msg.body("👋 Welcome! Text *HELP* to see menu.")
    
    return str(resp)

# --- CALLBACK LISTENER (The Ledger) ---
@app.route('/mpesa_callback', methods=['POST'])
def mpesa_callback():
    data = request.json
    try:
        # 1. HANDLE STK PUSH (Customer Buy / Sub Pay)
        if 'stkCallback' in data.get('Body', {}):
            stk = data['Body']['stkCallback']
            if stk.get('ResultCode') == 0:
                checkout_id = stk.get('CheckoutRequestID')
                tx = database.get_pending_transaction(checkout_id)
                
                if tx:
                    tx_type = tx[2]
                    
                    if tx_type == 'SUBSCRIPTION':
                        database.renew_subscription(tx[1]) 
                        app.logger.info(f"✅ Renewed Subscription for {tx[1]}")
                        
                    elif tx_type == 'PURCHASE':
                        target_shop = tx[3]
                        amount = tx[4]
                        database.credit_wallet(target_shop, amount)
                        app.logger.info(f"✅ Credited {amount} to Shop {target_shop}")
                else:
                    app.logger.warning(f"⚠️ Transaction {checkout_id} not found in pending list.")

        # 2. HANDLE B2C (Owner Withdrawal)
        # B2C results often come in a 'Result' object
        elif 'Result' in data:
            result = data['Result']
            conv_id = result.get('ConversationID')
            
            # Find the transaction using ConversationID
            tx = database.get_pending_transaction(conv_id)
            
            if tx and result.get('ResultCode') == 0:
                # SUCCESS: NOW we debit the wallet
                shop_phone = tx[1]
                database.debit_wallet_all(shop_phone)
                database.clear_pending_withdrawal(shop_phone)
                app.logger.info(f"✅ Withdrawal Confirmed for {shop_phone}")
                
            elif tx:
                # FAILURE: Just release lock
                database.clear_pending_withdrawal(tx[1])
                app.logger.info(f"❌ Withdrawal Failed for {tx[1]}")

    except Exception as e:
        app.logger.error(f"Callback Error: {e}")

    return "OK"

if __name__ == '__main__':
    app.run(debug=True)