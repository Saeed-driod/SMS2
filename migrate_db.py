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
    
    # Insert 8 default campuses
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
        
    print("Campuses populated.")

    # Get the ID of the first campus (Al-Rehman Campus, Okara)
    cursor.execute("SELECT id FROM campuses WHERE code = 'campus_1'")
    default_campus_id = cursor.fetchone()[0]

    # 2. Alter students table to add campus_id
    try:
        cursor.execute("ALTER TABLE students ADD COLUMN campus_id INTEGER REFERENCES campuses(id)")
        print("Column campus_id added to students table.")
    except sqlite3.OperationalError:
        print("Column campus_id already exists in students table.")
        
    # Update students to default campus
    cursor.execute("UPDATE students SET campus_id = ? WHERE campus_id IS NULL", (default_campus_id,))
    
    # 3. Alter fees table to add campus_id
    try:
        cursor.execute("ALTER TABLE fees ADD COLUMN campus_id INTEGER REFERENCES campuses(id)")
        print("Column campus_id added to fees table.")
    except sqlite3.OperationalError:
        print("Column campus_id already exists in fees table.")
        
    # Update fees to default campus
    cursor.execute("UPDATE fees SET campus_id = ? WHERE campus_id IS NULL", (default_campus_id,))
    
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
        c_id = cursor.fetchone()[0]
        
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO users (username, password, campus_id, role) VALUES (?, ?, ?, 'operator')",
                           (username, password, c_id))
            print(f"Created user '{username}' (password: '{password}') for campus {i}")
            
    conn.commit()
    conn.close()
    print("Database migration completed successfully!")

if __name__ == '__main__':
    run_migration()
