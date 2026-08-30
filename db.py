import os
import re
import sqlite3
from datetime import datetime

def get_database_url():
    url = os.environ.get('DATABASE_URL')
    if not url:
        env_file = os.path.join(BASE_DIR, '.env')
        if os.path.exists(env_file):
            try:
                with open(env_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('DATABASE_URL='):
                            url = line.split('DATABASE_URL=', 1)[1].strip().strip("'\"")
                            break
            except Exception:
                pass
    if url:
        url = url.strip().strip("'\"")
        if url.startswith('postgres://'):
            url = url.replace('postgres://', 'postgresql://', 1)
    return url


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQLITE_DB_PATH = os.path.join(BASE_DIR, 'sms.db')

def is_postgres():
    return bool(get_database_url())

class PgRow:
    """Row object that supports both dict indexing (row['name']) and tuple indexing (row[0]), mirroring sqlite3.Row."""
    def __init__(self, description, values):
        self._description = description or []
        self._values = tuple(values)
        self._mapping = {d[0]: val for d, val in zip(self._description, self._values)}
        self._lower_mapping = {d[0].lower(): val for d, val in zip(self._description, self._values)}

    def __getitem__(self, item):
        if isinstance(item, int):
            return self._values[item]
        if item in self._mapping:
            return self._mapping[item]
        if isinstance(item, str) and item.lower() in self._lower_mapping:
            return self._lower_mapping[item.lower()]
        raise KeyError(item)

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def __contains__(self, key):
        if isinstance(key, str):
            return key in self._mapping or key.lower() in self._lower_mapping
        return key in self._values

    def keys(self):
        return [d[0] for d in self._description]

    def get(self, key, default=None):
        try:
            return self[key]
        except (KeyError, IndexError):
            return default

    def __repr__(self):
        return f"<PgRow {self._mapping}>"


class PgCursorWrapper:
    def __init__(self, real_cursor):
        self._cursor = real_cursor

    def _translate_sql(self, sql):
        s = sql.strip()
        # Handle PRAGMA (SQLite specific)
        if s.upper().startswith('PRAGMA'):
            return None
        # Handle DELETE FROM sqlite_sequence (SQLite specific)
        if 'SQLITE_SEQUENCE' in s.upper():
            return None

        # Replace 'INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)'
        if re.search(r'INSERT\s+OR\s+REPLACE\s+INTO\s+settings', s, re.IGNORECASE):
            s = re.sub(
                r'INSERT\s+OR\s+REPLACE\s+INTO\s+settings\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)',
                r'INSERT INTO settings (\1) VALUES (\2) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value',
                s, flags=re.IGNORECASE
            )

        # Replace 'INSERT OR IGNORE INTO' with 'INSERT INTO ... ON CONFLICT DO NOTHING'
        if re.search(r'INSERT\s+OR\s+IGNORE\s+INTO', s, re.IGNORECASE):
            s = re.sub(r'INSERT\s+OR\s+IGNORE\s+INTO', 'INSERT INTO', s, flags=re.IGNORECASE)
            if 'ON CONFLICT' not in s.upper():
                s = s.rstrip(';') + ' ON CONFLICT DO NOTHING'

        # Translate '?' placeholders to '%s'
        # Only replace '?' that are not part of string literals
        s = re.sub(r'\?', '%s', s)
        return s

    def execute(self, sql, params=None):
        tsql = self._translate_sql(sql)
        if tsql is None:
            return self
        if params is None:
            self._cursor.execute(tsql)
        else:
            # If params is a list or tuple, pass as tuple
            self._cursor.execute(tsql, tuple(params))
        return self

    def executemany(self, sql, seq_of_params):
        tsql = self._translate_sql(sql)
        if tsql is None:
            return self
        self._cursor.executemany(tsql, seq_of_params)
        return self

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        return PgRow(self._cursor.description, row)

    def fetchall(self):
        rows = self._cursor.fetchall()
        desc = self._cursor.description
        return [PgRow(desc, r) for r in rows]

    def fetchmany(self, size=None):
        rows = self._cursor.fetchmany(size) if size is not None else self._cursor.fetchmany()
        desc = self._cursor.description
        return [PgRow(desc, r) for r in rows]

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def lastrowid(self):
        # In PostgreSQL last inserted ID can be fetched via RETURNING or sequence
        return getattr(self._cursor, 'lastrowid', None)

    def close(self):
        self._cursor.close()

    def __iter__(self):
        for r in self.fetchall():
            yield r


class PgConnectionWrapper:
    def __init__(self, real_conn):
        self._conn = real_conn

    def cursor(self):
        return PgCursorWrapper(self._conn.cursor())

    def execute(self, sql, params=None):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def get_db_connection():
    """Returns an active database connection (PostgreSQL if DATABASE_URL is set, otherwise SQLite)."""
    db_url = get_database_url()
    if db_url:
        import psycopg2
        conn = psycopg2.connect(db_url)
        return PgConnectionWrapper(conn)
    else:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn


def init_db():
    """Initializes and migrates the database schema on both PostgreSQL and SQLite."""
    conn = get_db_connection()
    cur = conn.cursor()

    if is_postgres():
        # PostgreSQL Schema
        cur.execute('''
            CREATE TABLE IF NOT EXISTS campuses (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                code TEXT UNIQUE NOT NULL
            );
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS students (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                father_name TEXT,
                phone_number TEXT,
                class TEXT NOT NULL,
                monthly_fee REAL NOT NULL,
                annual_charges REAL DEFAULT 0,
                opening_arrears REAL DEFAULT 0,
                start_month INTEGER DEFAULT 3,
                start_year INTEGER DEFAULT 2026,
                campus_id INTEGER REFERENCES campuses(id),
                status TEXT DEFAULT 'active'
            );
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS fees (
                id SERIAL PRIMARY KEY,
                student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                month TEXT NOT NULL,
                year INTEGER NOT NULL,
                paid_amount REAL NOT NULL,
                date_paid TEXT NOT NULL,
                payment_mode TEXT DEFAULT 'Voucher',
                reference_no TEXT,
                notes TEXT,
                collected_by TEXT,
                campus_id INTEGER REFERENCES campuses(id)
            );
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS annual_charges_payments (
                id SERIAL PRIMARY KEY,
                student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                year INTEGER NOT NULL,
                paid_amount REAL NOT NULL,
                date_paid TEXT NOT NULL,
                payment_mode TEXT DEFAULT 'Voucher',
                reference_no TEXT,
                notes TEXT,
                collected_by TEXT,
                campus_id INTEGER REFERENCES campuses(id)
            );
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                campus_id INTEGER REFERENCES campuses(id),
                role TEXT DEFAULT 'operator'
            );
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS sos_materials (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                class_name TEXT NOT NULL,
                filename TEXT NOT NULL,
                filepath TEXT NOT NULL,
                date_uploaded TEXT NOT NULL
            );
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS student_delete_requests (
                id SERIAL PRIMARY KEY,
                student_id INTEGER NOT NULL,
                student_name TEXT NOT NULL,
                student_father_name TEXT,
                student_class TEXT NOT NULL,
                student_campus_id INTEGER NOT NULL REFERENCES campuses(id),
                requested_by_user TEXT NOT NULL,
                requested_at TEXT NOT NULL,
                reason TEXT,
                status TEXT DEFAULT 'pending',
                actioned_by_user TEXT,
                actioned_at TEXT
            );
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS promotion_history (
                id SERIAL PRIMARY KEY,
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
            );
        ''')

    else:
        # SQLite Schema
        cur.execute('''
            CREATE TABLE IF NOT EXISTS campuses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                code TEXT UNIQUE NOT NULL
            );
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                father_name TEXT,
                phone_number TEXT,
                class TEXT NOT NULL,
                monthly_fee REAL NOT NULL,
                annual_charges REAL DEFAULT 0,
                opening_arrears REAL DEFAULT 0,
                start_month INTEGER DEFAULT 3,
                start_year INTEGER DEFAULT 2026,
                campus_id INTEGER REFERENCES campuses(id),
                status TEXT DEFAULT 'active'
            );
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS fees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                month TEXT NOT NULL,
                year INTEGER NOT NULL,
                paid_amount REAL NOT NULL,
                date_paid TEXT NOT NULL,
                payment_mode TEXT DEFAULT 'Voucher',
                reference_no TEXT,
                notes TEXT,
                collected_by TEXT,
                campus_id INTEGER REFERENCES campuses(id),
                FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE CASCADE
            );
        ''')
        cur.execute('''
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
            );
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                campus_id INTEGER REFERENCES campuses(id),
                role TEXT DEFAULT 'operator'
            );
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS sos_materials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                class_name TEXT NOT NULL,
                filename TEXT NOT NULL,
                filepath TEXT NOT NULL,
                date_uploaded TEXT NOT NULL
            );
        ''')
        cur.execute('''
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
            );
        ''')
        cur.execute('''
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
            );
        ''')

    # Seed default campuses if empty
    campus_count_row = conn.execute("SELECT COUNT(*) FROM campuses").fetchone()
    campus_count = campus_count_row[0] if campus_count_row else 0
    if campus_count == 0:
        default_campuses = [
            ('28 Campus', '28_campus'),
            ('Main Campus Okara', 'main_campus'),
            ('44_2l campus', '44_2l'),
            ('Gobindpur Campus', 'gobindpur'),
            ('21_GD campus', '21_gd'),
            ('44_GD Campus', '44_gd'),
            ('Firdous Town Campus', 'firdous_town')
        ]
        for name, code in default_campuses:
            conn.execute("INSERT INTO campuses (name, code) VALUES (?, ?)", (name, code))

    # Seed default admin if empty
    user_count_row = conn.execute("SELECT COUNT(*) FROM users").fetchone()
    user_count = user_count_row[0] if user_count_row else 0
    if user_count == 0:
        conn.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                     ('admin', 'pbkdf2:sha256:600000$admin_salt$cb2422ba14a80696f8a846f5c88b89cfd0b2cb612a4f00dbccbf5be5d3c01c0b', 'admin'))

    # Seed default operator accounts for campuses
    campuses = conn.execute("SELECT id, code FROM campuses").fetchall()
    for c in campuses:
        c_code = c['code']
        c_id = c['id']
        u_row = conn.execute("SELECT id FROM users WHERE username = ?", (c_code,)).fetchone()
        if not u_row:
            conn.execute("INSERT INTO users (username, password, campus_id, role) VALUES (?, ?, ?, 'operator')",
                         (c_code, c_code, c_id))

    # Seed default settings if empty
    default_settings = [
        ('school_name', 'Alliedian School Al-Rehman Campus, Okara'),
        ('bank_name', 'MCB Bank Ltd (A/C: 1234-5678-9)'),
        ('due_day', '10'),
        ('late_fee', '100'),
        ('db_seeded', '1')
    ]
    for k, v in default_settings:
        s_row = conn.execute("SELECT key FROM settings WHERE key = ?", (k,)).fetchone()
        if not s_row:
            conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (k, v))

    # Run lightweight schema migrations and performance indices
    try:
        if is_postgres():
            conn.execute("ALTER TABLE students ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'active'")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_fees_student_id ON fees(student_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_student_id ON annual_charges_payments(student_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_students_class ON students(class)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_students_campus ON students(campus_id)")
        else:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(students)")
            cols = [c[1] for c in cur.fetchall()]
            if 'status' not in cols:
                conn.execute("ALTER TABLE students ADD COLUMN status TEXT DEFAULT 'active'")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_fees_student_id ON fees(student_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_student_id ON annual_charges_payments(student_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_students_class ON students(class)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_students_campus ON students(campus_id)")
    except Exception as e:
        print(f"Migration check warning: {e}")

    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("Database initialized successfully!")
