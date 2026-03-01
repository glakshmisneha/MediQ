import sqlite3

DB_NAME = "medivista.db"

def get_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS users(
        email TEXT PRIMARY KEY,
        password BLOB,
        role TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS specialties(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS doctors(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        email TEXT UNIQUE,
        specialty_id INTEGER,
        total_slots INTEGER,
        nurse_assigned TEXT,
        shift_timing TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS patients(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        age INTEGER,
        blood_group TEXT,
        reason TEXT,
        amount_paid REAL,
        visit_date TEXT,
        email TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS appointments(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER,
        doctor_id INTEGER,
        appointment_date TEXT,
        appointment_time TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS queries(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_email TEXT,
        doctor_name TEXT,
        query_text TEXT,
        query_type TEXT,
        status TEXT DEFAULT 'Pending',
        created_at TEXT
    )""")

    conn.commit()
    conn.close()
