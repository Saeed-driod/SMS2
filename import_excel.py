import sqlite3
import pandas as pd
import numpy as np
import re
import os

DB_PATH = 'sms.db'
EXCEL_PATH = 'Fee record 2026.xlsx'

MONTH_MAP = {
    'jan': ('January', 1),
    'feb': ('February', 2),
    'fe': ('February', 2),
    'mar': ('March', 3),
    'apr': ('April', 4),
    'may': ('May', 5),
    'jun': ('June', 6),
    'jul': ('July', 7),
    'aug': ('August', 8),
    'sep': ('September', 9),
    'oct': ('October', 10),
    'nov': ('November', 11),
    'dec': ('December', 12)
}

def clean_amount(val, default_fee=0):
    if pd.isna(val) or val == '':
        return 0
    if isinstance(val, (int, float)):
        return int(val)
    val_str = str(val).strip().lower()
    if not val_str or val_str == 'nan':
        return 0
    if val_str in ('done', 'paid', 'ok', 'yes'):
        return default_fee
    # extract first sequence of digits
    match = re.search(r'\d+', val_str)
    if match:
        return int(match.group())
    return 0

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create campuses table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS campuses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            code TEXT UNIQUE NOT NULL
        )
    ''')
    
    # Create students table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            father_name TEXT,
            class TEXT NOT NULL,
            monthly_fee REAL NOT NULL,
            start_month INTEGER DEFAULT 3,
            start_year INTEGER DEFAULT 2026,
            campus_id INTEGER REFERENCES campuses(id)
        )
    ''')
    
    # Create fees table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            month TEXT NOT NULL,
            year INTEGER NOT NULL,
            paid_amount REAL NOT NULL,
            date_paid TEXT NOT NULL,
            campus_id INTEGER REFERENCES campuses(id),
            FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE CASCADE
        )
    ''')
    
    # Create users table for login
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            campus_id INTEGER REFERENCES campuses(id),
            role TEXT DEFAULT 'operator'
        )
    ''')
    
    # Create settings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')
    
    # Insert default campuses
    default_campuses = [
        ('Al-Rehman Campus, Okara', 'campus_1'),
        ('Main Campus, Lahore', 'campus_2'),
        ('Model Town Campus, Okara', 'campus_3'),
        ('Sahiwal Campus', 'campus_4'),
        ('Faisalabad Campus', 'campus_5'),
        ('Multan Campus', 'campus_6'),
        ('Gujranwala Campus', 'campus_7'),
        ('Sialkot Campus', 'campus_8')
    ]
    for name, code in default_campuses:
        cursor.execute("INSERT OR IGNORE INTO campuses (name, code) VALUES (?, ?)", (name, code))
        
    # Get default campus ID
    cursor.execute("SELECT id FROM campuses WHERE code = 'campus_1'")
    default_campus_id = cursor.fetchone()[0]
    
    # Insert default admin user if not exists (Head office admin has NULL campus_id)
    cursor.execute("INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, ?)", 
                   ('admin', 'pbkdf2:sha256:600000$admin_salt$cb2422ba14a80696f8a846f5c88b89cfd0b2cb612a4f00dbccbf5be5d3c01c0b', 'admin'))
    
    # Insert operators for each campus
    for i in range(1, 9):
        username = f"operator{i}"
        password = f"operator{i}"
        cursor.execute("SELECT id FROM campuses WHERE code = ?", (f"campus_{i}",))
        c_id = cursor.fetchone()[0]
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO users (username, password, campus_id, role) VALUES (?, ?, ?, 'operator')",
                           (username, password, c_id))
            
    # Insert default settings
    default_settings = [
        ('school_name', 'Allied School Al-Rehman Campus, Okara'),
        ('bank_name', 'MCB Bank Ltd (A/C: 1234-5678-9)'),
        ('due_day', '10'),
        ('late_fee', '100')
    ]
    for key, val in default_settings:
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, val))
        
    conn.commit()
    conn.close()

def import_data():
    if not os.path.exists(EXCEL_PATH):
        print(f"Error: {EXCEL_PATH} not found!")
        return
        
    print(f"Loading {EXCEL_PATH}...")
    xls = pd.ExcelFile(EXCEL_PATH)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Clear existing data before import to avoid duplicates
    cursor.execute("DELETE FROM fees")
    cursor.execute("DELETE FROM students")
    cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('students', 'fees')")
    conn.commit()
    
    # Get default campus ID (we assign all imported students to the first campus by default)
    cursor.execute("SELECT id FROM campuses WHERE code = 'campus_1'")
    default_campus_id = cursor.fetchone()[0]
    
    student_count = 0
    payment_count = 0
    
    for sheet in xls.sheet_names:
        if sheet == 'van Charges':
            continue
            
        print(f"Processing sheet: {sheet}...")
        df = pd.read_excel(xls, sheet, header=None)
        if len(df) < 3:
            continue
            
        headers = [str(x).strip() for x in df.iloc[2].tolist()]
        
        # Identify columns
        name_col = 1
        father_col = 2
        
        # Monthly fee columns (columns containing 'month' or 'monthly' and not matching month names)
        fee_cols = []
        for i, h in enumerate(headers):
            hl = h.lower()
            if ('month' in hl or 'monthly' in hl) and not any(hl.startswith(m) for m in MONTH_MAP):
                fee_cols.append(i)
                
        # Month payment columns
        month_cols = []
        for i, h in enumerate(headers):
            hl = h.lower()
            for m_key in MONTH_MAP:
                if hl.startswith(m_key):
                    month_cols.append((i, MONTH_MAP[m_key][0], MONTH_MAP[m_key][1]))
                    break
                    
        # Iterate over student rows
        for r_idx in range(3, len(df)):
            row = df.iloc[r_idx].tolist()
            if len(row) <= 1:
                continue
                
            name = str(row[name_col]).strip() if pd.notna(row[name_col]) else ''
            if not name or name.lower() == 'nan' or name == 'SR. #' or name.startswith('Name'):
                continue
                
            father = str(row[father_col]).strip() if (father_col < len(row) and pd.notna(row[father_col])) else ''
            if father.lower() == 'nan':
                father = ''
                
            # Determine monthly fee for this student
            monthly_fee = 0
            for f_col in fee_cols:
                if f_col < len(row):
                    val = row[f_col]
                    fee_val = clean_amount(val)
                    if fee_val > 0:
                        monthly_fee = fee_val
                        
            if monthly_fee == 0:
                # Set a default monthly fee if not found
                monthly_fee = 2400
                
            # Determine start month and year based on earliest recorded payment or default to March 2026
            start_month = 3
            start_year = 2026
            
            # Find the earliest month column with a payment or a value
            earliest_payment_found = False
            for f_idx, m_name, m_val in month_cols:
                if f_idx < len(row) and pd.notna(row[f_idx]):
                    val = row[f_idx]
                    amt = clean_amount(val, monthly_fee)
                    if amt > 0:
                        # Determine year of payment
                        year = 2025 if (m_name in ('November', 'December') and f_idx < 8) else 2026
                        if not earliest_payment_found or (year < start_year) or (year == start_year and m_val < start_month):
                            start_month = m_val
                            start_year = year
                            earliest_payment_found = True
                            
            # Insert student
            cursor.execute('''
                INSERT INTO students (name, father_name, class, monthly_fee, start_month, start_year, campus_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (name, father, sheet, monthly_fee, start_month, start_year, default_campus_id))
            student_id = cursor.lastrowid
            student_count += 1
            
            # Insert payments
            for f_idx, m_name, m_val in month_cols:
                if f_idx < len(row) and pd.notna(row[f_idx]):
                    val = row[f_idx]
                    amt = clean_amount(val, monthly_fee)
                    if amt > 0:
                        year = 2025 if (m_name in ('November', 'December') and f_idx < 8) else 2026
                        date_paid = f"{year}-{m_val:02d}-01" # Default to first of month
                        cursor.execute('''
                            INSERT INTO fees (student_id, month, year, paid_amount, date_paid, campus_id)
                            VALUES (?, ?, ?, ?, ?, ?)
                        ''', (student_id, m_name, year, amt, date_paid, default_campus_id))
                        payment_count += 1
                        
    conn.commit()
    conn.close()
    print(f"Import complete! Imported {student_count} students and {payment_count} payments.")

if __name__ == '__main__':
    init_db()
    import_data()
