import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import bcrypt
import os
import re 
from datetime import datetime
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch

# 1. Page Configuration
st.set_page_config(page_title="MediVista Admin", layout="wide")

DB_NAME = "mediq.db"

# ================= DATABASE INITIALIZATION ================= #
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users(email TEXT PRIMARY KEY, password BLOB, role TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS doctors(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, specialty TEXT, total_slots INTEGER, booked_slots INTEGER DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS patients(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, age INTEGER, blood_group TEXT, reason TEXT, amount_paid REAL, visit_date TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS appointments(id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER, doctor_id INTEGER, appointment_date TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS queries(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT, query TEXT, status TEXT DEFAULT 'Open')")
    c.execute("CREATE TABLE IF NOT EXISTS rooms(room_no TEXT PRIMARY KEY, type TEXT, status TEXT DEFAULT 'Available')")
    
    c.execute("SELECT COUNT(*) FROM rooms")
    if c.fetchone()[0] == 0:
        rooms_data = [('101', 'General', 'Available'), ('102', 'General', 'Available'), 
                      ('201', 'ICU', 'Available'), ('301', 'Private', 'Available')]
        c.executemany("INSERT INTO rooms VALUES (?,?,?)", rooms_data)
        
    conn.commit()
    conn.close()

init_db()

# ================= SECURITY HELPERS ================= #
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

def check_password(password, hashed):
    if isinstance(hashed, str): hashed = hashed.encode('utf-8')
    elif isinstance(hashed, memoryview): hashed = hashed.tobytes()
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed)
    except Exception:
        return False

# NEW: Strict Validation Logic
def is_valid_gmail(email):
    return bool(re.match(r"^[a-zA-Z0-9._%+-]+@gmail\.com$", email))

def is_strong_password(password):
    # Rules: Min 8 chars, 1 uppercase, 1 number, 1 special character
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not any(char.isupper() for char in password):
        return False, "Password must contain at least one uppercase letter."
    if not any(char.isdigit() for char in password):
        return False, "Password must contain at least one number."
    if not any(char in "!@#$%^&*()-_=+[]{}|;:',.<>?/" for char in password):
        return False, "Password must contain at least one special character."
    return True, ""

# ================= UI CUSTOM STYLING ================= #
st.markdown("""
    <style>
    div[data-testid="stMetricValue"] { color: #ffffff; font-size: 40px; font-weight: bold; }
    .stButton>button { background-color: #00acee; color: white; border-radius: 20px; border: none; font-weight: bold; width: 100%; }
    .stSidebar { background-color: #0e1117; }
    [data-testid="stForm"] { border: 1px solid #30363d !important; border-radius: 15px; background-color: #161b22; }
    </style>
    """, unsafe_allow_html=True)

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# ================= AUTHENTICATION FLOW ================= #
if not st.session_state.logged_in:
    st.title("🏥 MediVista Portal")
    mode = st.radio("Option", ["Login", "Register"], horizontal=True)
    email_input = st.text_input("Email (xxx@gmail.com)")
    password_input = st.text_input("Password", type="password")

    if mode == "Register":
        role = st.selectbox("Role", ["Patient", "Admin", "Receptionist", "Hospital Staff"])
        st.info("Password requirements: 8+ characters, 1 Uppercase, 1 Number, 1 Special Char")
        if st.button("Create Account"):
            # Validation Checks
            valid_pass, pass_msg = is_strong_password(password_input)
            
            if not is_valid_gmail(email_input):
                st.error("Invalid Email! Please use a valid @gmail.com address.")
            elif not valid_pass:
                st.error(pass_msg)
            else:
                hashed = hash_password(password_input)
                conn = sqlite3.connect(DB_NAME)
                try:
                    conn.execute("INSERT INTO users (email, password, role) VALUES (?,?,?)", (email_input, sqlite3.Binary(hashed), role))
                    conn.commit()
                    st.success("Account Created Successfully!")
                except: st.error("User already exists.")
                finally: conn.close()

    if mode == "Login":
        if st.button("Login"):
            conn = sqlite3.connect(DB_NAME)
            res = conn.execute("SELECT password, role FROM users WHERE email=?", (email_input,)).fetchone()
            conn.close()
            if res and check_password(password_input, res[0]):
                st.session_state.logged_in = True
                st.session_state.role = res[1]
                st.session_state.user_email = email_input
                st.rerun()
            else: st.error("Invalid Credentials.")

# ================= MAIN APPLICATION ================= #
else:
    # (Rest of the application code remains the same as previous version...)
    if st.session_state.role == "Patient":
        st.title("Patient Portal")
        # Patient logic...
    else:
        st.sidebar.title("MediVista Admin")
        page = st.sidebar.radio("Navigation", ["Dashboard", "Doctors Allotment", "Patient Details", "Appointments", "Patient Queries", "Room Management", "Reports"])
        
        # Admin logic...
        if st.sidebar.button("Logout"):
            st.session_state.logged_in = False
            st.rerun()
