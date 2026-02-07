import sqlite3
from datetime import datetime, timedelta

DB_NAME = "saas_bot.db"

def init_db():
    """Initializes the database with shops and transaction tables."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # 1. SHOPS TABLE (Updated with Wallet & Commission)
    # wallet_balance: The money the shop owner has earned but not withdrawn
    # commission_rate: Your cut (e.g., 0.05 for 5%)
    c.execute('''CREATE TABLE IF NOT EXISTS shops
                 (phone_number TEXT PRIMARY KEY,
                  shop_name TEXT,
                  catalog_link TEXT,
                  location_map TEXT,
                  payment_info TEXT,
                  operating_hours TEXT,
                  expiry_date TEXT,
                  wallet_balance REAL DEFAULT 0.0,
                  commission_rate REAL DEFAULT 0.05)''')

    # 2. PENDING TRANSACTIONS TABLE (State Management)
    # Links a CheckoutRequestID to a specific Shop Owner so we know who to credit
    c.execute('''CREATE TABLE IF NOT EXISTS pending_transactions
                 (checkout_request_id TEXT PRIMARY KEY,
                  user_phone TEXT,
                  transaction_type TEXT, 
                  target_shop_phone TEXT,
                  amount REAL,
                  timestamp TEXT)''')
                  
    conn.commit()
    conn.close()

def add_shop(phone, name, catalog, location, payment, hours):
    """Registers a new shop with default wallet settings."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    expiry = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
    
    try:
        # Insert with default wallet=0.0 and commission=5%
        c.execute("INSERT OR REPLACE INTO shops VALUES (?, ?, ?, ?, ?, ?, ?, 0.0, 0.05)",
                  (phone, name, catalog, location, payment, hours, expiry))
        conn.commit()
        return True, expiry
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def get_shop(phone_number):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM shops WHERE phone_number=?", (phone_number,))
    shop = c.fetchone()
    conn.close()
    return shop

def search_shop_by_name(query_name):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM shops WHERE shop_name LIKE ?", (f'%{query_name}%',))
    shop = c.fetchone()
    conn.close()
    return shop

def update_shop_field(phone_number, field, new_value):
    column_map = {'NAME': 'shop_name', 'CATALOG': 'catalog_link', 
                  'LOCATION': 'location_map', 'PAY': 'payment_info', 'HOURS': 'operating_hours'}
    db_column = column_map.get(field.upper())
    if not db_column: return False, "Invalid field name."

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        query = f"UPDATE shops SET {db_column} = ? WHERE phone_number = ?"
        c.execute(query, (new_value, phone_number))
        conn.commit()
        return True, f"Successfully updated {field}."
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def renew_subscription(phone_number, days=30):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    new_expiry = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
    c.execute("UPDATE shops SET expiry_date = ? WHERE phone_number = ?", (new_expiry, phone_number))
    success = c.rowcount > 0
    conn.commit()
    conn.close()
    return success, new_expiry

# --- NEW: WALLET & TRANSACTION LOGIC ---

def check_pending_withdrawal(shop_phone):
    """
    Checks if this shop already has a withdrawal in progress.
    Returns: Boolean (True if pending exists)
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM pending_transactions WHERE user_phone=? AND transaction_type='WITHDRAWAL'", (shop_phone,))
    row = c.fetchone()
    conn.close()
    return row is not None

def clear_pending_withdrawal(shop_phone):
    """Removes the pending lock after success/failure."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM pending_transactions WHERE user_phone=? AND transaction_type='WITHDRAWAL'", (shop_phone,))
    conn.commit()
    conn.close()

def log_pending_transaction(checkout_id, user_phone, tx_type, target_shop=None, amount=0):
    """
    Saves a transaction as 'Pending' while we wait for M-Pesa PIN entry.
    tx_type: 'SUBSCRIPTION' or 'PURCHASE' or 'WITHDRAWAL'
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO pending_transactions VALUES (?, ?, ?, ?, ?, ?)",
                  (checkout_id, user_phone, tx_type, target_shop, amount, datetime.now()))
        conn.commit()
        return True
    except Exception as e:
        print(f"DB Error: {e}")
        return False
    finally:
        conn.close()

def get_pending_transaction(checkout_id):
    """Retrieves transaction details using the ID from the Callback."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM pending_transactions WHERE checkout_request_id=?", (checkout_id,))
    tx = c.fetchone()
    conn.close()
    return tx

def credit_wallet(shop_phone, amount):
    """
    Calculates commission and credits the Shop Owner's wallet.
    Logic: Net = Amount - (Amount * CommissionRate)
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Get current balance & rate
    c.execute("SELECT wallet_balance, commission_rate FROM shops WHERE phone_number=?", (shop_phone,))
    row = c.fetchone()
    if not row:
        conn.close()
        return False
    
    current_balance, rate = row
    
    # Calculate Commission
    commission = amount * rate
    net_amount = amount - commission
    new_balance = current_balance + net_amount
    
    c.execute("UPDATE shops SET wallet_balance = ? WHERE phone_number = ?", (new_balance, shop_phone))
    conn.commit()
    conn.close()
    return True

def debit_wallet_all(shop_phone):
    """
    Empties the shop's wallet for withdrawal.
    NOW: Only called AFTER success callback.
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    c.execute("SELECT wallet_balance FROM shops WHERE phone_number=?", (shop_phone,))
    row = c.fetchone()
    if not row: return 0
    
    balance = row[0]
    if balance <= 0: return 0
    
    # Reset balance to 0 (Optimistic Locking strategy for MVP)
    c.execute("UPDATE shops SET wallet_balance = 0 WHERE phone_number = ?", (shop_phone,))
    conn.commit()
    conn.close()
    
    return balance

# --- NEW: EXPIRY CHECK LOGIC ---
def get_shops_expiring_on(date_str):
    """
    Finds all shops expiring on a specific date (YYYY-MM-DD).
    Returns a list of tuples: [(phone, name), (phone, name)...]
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT phone_number, shop_name FROM shops WHERE expiry_date = ?", (date_str,))
    results = c.fetchall()
    conn.close()
    return results