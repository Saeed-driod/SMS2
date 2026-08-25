import sqlite3

DB_PATH = 'sms.db'

def run_migration():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("Starting database migration for Multi-Campus setup...")
    
    # 1. Create campuses table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS campuses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            code TEXT UNIQUE NOT NULL
        )
    ''')
    
    # Check if campuses table is empty before inserting defaults
    cursor.execute("SELECT COUNT(*) FROM campuses")
    if cursor.fetchone()[0] == 0:
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
        print("Default sample campuses populated (table was empty).")
    else:
        print("Campuses already configured; skipping default population to preserve user deletions.")

    # Get the ID of the first existing campus
    cursor.execute("SELECT id FROM campuses LIMIT 1")
    first_campus_row = cursor.fetchone()
    default_campus_id = first_campus_row[0] if first_campus_row else None

    # 2. Alter students table to add campus_id and phone_number
    try:
        cursor.execute("ALTER TABLE students ADD COLUMN campus_id INTEGER REFERENCES campuses(id)")
        print("Column campus_id added to students table.")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE students ADD COLUMN phone_number TEXT")
        print("Column phone_number added to students table.")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE students ADD COLUMN opening_arrears REAL DEFAULT 0")
        print("Column opening_arrears added to students table.")
    except sqlite3.OperationalError:
        pass
        
    # Update students to default campus
    if default_campus_id:
        cursor.execute("UPDATE students SET campus_id = ? WHERE campus_id IS NULL", (default_campus_id,))
    cursor.execute("UPDATE students SET opening_arrears = 0 WHERE opening_arrears IS NULL")
    
    # 3. Alter fees table to add campus_id, payment_mode, reference_no, notes, collected_by
    try:
        cursor.execute("ALTER TABLE fees ADD COLUMN campus_id INTEGER REFERENCES campuses(id)")
        print("Column campus_id added to fees table.")
    except sqlite3.OperationalError:
        print("Column campus_id already exists in fees table.")
        
    for col, col_type in [('payment_mode', "TEXT DEFAULT 'Voucher'"), 
                          ('reference_no', 'TEXT'), 
                          ('notes', 'TEXT'), 
                          ('collected_by', 'TEXT')]:
        try:
            cursor.execute(f"ALTER TABLE fees ADD COLUMN {col} {col_type}")
            print(f"Column {col} added to fees table.")
        except sqlite3.OperationalError:
            pass

    # Create annual_charges_payments table if not exists
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS annual_charges_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            year INTEGER NOT NULL,
            paid_amount REAL NOT NULL,
            date_paid TEXT NOT NULL,
            payment_mode TEXT DEFAULT 'Voucher',
            reference_no TEXT,
            notes TEXT,
            collected_by TEXT,
            campus_id INTEGER REFERENCES campuses(id),
            FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE CASCADE
        )
    ''')
    for col, col_type in [('payment_mode', "TEXT DEFAULT 'Voucher'"), 
                          ('reference_no', 'TEXT'), 
                          ('notes', 'TEXT'), 
                          ('collected_by', 'TEXT')]:
        try:
            cursor.execute(f"ALTER TABLE annual_charges_payments ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass
        
    # Update fees to default campus
    cursor.execute("UPDATE fees SET campus_id = ? WHERE campus_id IS NULL", (default_campus_id,))
    cursor.execute("UPDATE fees SET payment_mode = 'Voucher' WHERE payment_mode IS NULL")
    
    # 4. Alter users table to add campus_id and role
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN campus_id INTEGER REFERENCES campuses(id)")
        print("Column campus_id added to users table.")
    except sqlite3.OperationalError:
        print("Column campus_id already exists in users table.")
        
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'operator'")
        print("Column role added to users table.")
    except sqlite3.OperationalError:
        print("Column role already exists in users table.")
        
    # Update default admin user
    cursor.execute("UPDATE users SET role = 'admin' WHERE username = 'admin'")
    
    # Create operator accounts for each campus for testing / ease of access
    # We create operators with username 'operator1', 'operator2', etc. with password same as username
    # Password hashed with pbkdf2:sha256
    # For operator1: 'pbkdf2:sha256:600000$operator1_salt$a59082ea9a0a0ffaa426df47545163c293798cf0f23554e2f5b5f5e2d01c0b' or fallback to plain
    for i in range(1, 9):
        username = f"operator{i}"
        password = f"operator{i}" # Plain fallback works in our app
        cursor.execute("SELECT id FROM campuses WHERE code = ?", (f"campus_{i}",))
        c_row = cursor.fetchone()
        if not c_row:
            continue
        c_id = c_row[0]
        
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO users (username, password, campus_id, role) VALUES (?, ?, ?, 'operator')",
                           (username, password, c_id))
            print(f"Created user '{username}' (password: '{password}') for campus {i}")
            
    # 5. Create student_delete_requests table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS student_delete_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            student_name TEXT NOT NULL,
            student_father_name TEXT,
            student_class TEXT NOT NULL,
            student_campus_id INTEGER NOT NULL,
            requested_by_user TEXT NOT NULL,
            requested_at TEXT NOT NULL,
            reason TEXT,
            status TEXT DEFAULT 'pending',
            actioned_by_user TEXT,
            actioned_at TEXT,
            FOREIGN KEY (student_campus_id) REFERENCES campuses(id)
        )
    ''')
    print("Table student_delete_requests verified/created.")

    # 6. Create promotion_history table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS promotion_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            student_name TEXT NOT NULL,
            from_class TEXT NOT NULL,
            to_class TEXT NOT NULL,
            previous_fee REAL NOT NULL,
            new_fee REAL NOT NULL,
            new_start_month INTEGER NOT NULL,
            new_start_year INTEGER NOT NULL,
            promoted_by_user TEXT NOT NULL,
            promoted_at TEXT NOT NULL,
            campus_id INTEGER REFERENCES campuses(id)
        )
    ''')
    print("Table promotion_history verified/created.")

    conn.commit()
    conn.close()
    print("Database migration completed successfully!")

if __name__ == '__main__':
    run_migration()
