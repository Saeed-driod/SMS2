import os
from db import get_db_connection, init_db, is_postgres

def run_migration():
    print("Initializing database tables and schema...")
    init_db()
    print("Database migration completed successfully!")

if __name__ == '__main__':
    run_migration()
