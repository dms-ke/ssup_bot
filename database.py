import sqlite3
from datetime import datetime, timedelta

DB_NAME = "saas_bot.db"

def init_db():
    """Initializes the database with the shops table if it doesn't exist."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Create table with phone_number as PK (Data Integrity)
    # Includes expiry_date for SaaS subscription management
    c.execute('''CREATE TABLE IF NOT EXISTS shops
                 (phone_number TEXT PRIMARY KEY,
                  shop_name TEXT,
                  catalog_link TEXT,
                  location_map TEXT,
                  payment_info TEXT,
                  operating_hours TEXT,
                  expiry_date TEXT)''')
    conn.commit()
    conn.close()

def add_shop(phone, name, catalog, location, payment, hours):
    """
    Registers a new shop with a 30-day free trial.
    Returns: (bool success, str expiry_date_or_error)
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Calculate expiry date (30 days from now)
    expiry = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
    
    try:
        # INSERT OR REPLACE allows a shop to update their details by registering again
        c.execute("INSERT OR REPLACE INTO shops VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (phone, name, catalog, location, payment, hours, expiry))
        conn.commit()
        return True, expiry
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def get_shop(phone_number):
    """Retrieves shop details by the owner's phone number."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM shops WHERE phone_number=?", (phone_number,))
    shop = c.fetchone()
    conn.close()
    return shop

def search_shop_by_name(query_name):
    """
    Allows customers to search for a shop by name.
    Case insensitive partial search.
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Adding wildcards % around the query for partial matching
    c.execute("SELECT * FROM shops WHERE shop_name LIKE ?", (f'%{query_name}%',))
    shop = c.fetchone()
    conn.close()
    return shop

def update_shop_field(phone_number, field, new_value):
    """
    Updates a specific field for a shop.
    Allowed fields: NAME, CATALOG, LOCATION, PAY, HOURS
    """
    # Map friendly names to actual Database Column names
    # This prevents SQL injection by whitelisting columns
    column_map = {
        'NAME': 'shop_name',
        'CATALOG': 'catalog_link',
        'LOCATION': 'location_map',
        'PAY': 'payment_info',
        'HOURS': 'operating_hours'
    }
    
    # 1. Validate the field
    db_column = column_map.get(field.upper())
    if not db_column:
        return False, "Invalid field name. Use: NAME, CATALOG, LOCATION, PAY, or HOURS"

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    try:
        # 2. Check if shop exists first
        c.execute("SELECT * FROM shops WHERE phone_number=?", (phone_number,))
        if not c.fetchone():
            conn.close()
            return False, "Shop not found. Please REGISTER first."

        # 3. Execute the Update
        # We use f-string for the column name (safe because we mapped it above)
        query = f"UPDATE shops SET {db_column} = ? WHERE phone_number = ?"
        c.execute(query, (new_value, phone_number))
        conn.commit()
        return True, f"Successfully updated {field}."
        
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def renew_subscription(phone_number, days=30):
    """
    Extends the subscription by X days from today.
    Returns: (bool success, str new_expiry_date)
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    new_expiry = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
    
    c.execute("UPDATE shops SET expiry_date = ? WHERE phone_number = ?", 
              (new_expiry, phone_number))
    
    # Check if a row was actually updated (meaning the user exists)
    success = c.rowcount > 0
    conn.commit()
    conn.close()
    return success, new_expiry