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

# 1. Page Configuration (Must be first)
st.set_page_config(page_title="MediVista Admin", layout="wide")

DB_NAME = "mediq.db"

# ================= DATABASE INITIALIZATION ================= #
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Core Tables
    c.execute("CREATE TABLE IF NOT EXISTS users(email TEXT PRIMARY KEY, password BLOB, role TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS patients(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, age INTEGER, blood_group TEXT, reason TEXT, amount_paid REAL, visit_date TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS appointments(id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER, doctor_id INTEGER, appointment_date TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS queries(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT, doctor_name TEXT, query TEXT, is_complaint INTEGER DEFAULT 0, status TEXT DEFAULT 'Open')")
    c.execute("CREATE TABLE IF NOT EXISTS rooms(room_no TEXT PRIMARY KEY, type TEXT, status TEXT DEFAULT 'Available')")
    
    # Doctors Table with new columns
    c.execute("""CREATE TABLE IF NOT EXISTS doctors(
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        name TEXT, specialty TEXT, total_slots INTEGER, 
        booked_slots INTEGER DEFAULT 0, 
        nurse_assigned TEXT, shift_timing TEXT)""")

    # --- MIGRATION: Add missing columns if they don't exist in old DB ---
    c.execute("PRAGMA table_info(doctors)")
    columns = [column[1] for column in c.fetchall()]
    if 'nurse_assigned' not in columns:
        c.execute("ALTER TABLE doctors ADD COLUMN nurse_assigned TEXT DEFAULT 'Not Assigned'")
    if 'shift_timing' not in columns:
        c.execute("ALTER TABLE doctors ADD COLUMN shift_timing TEXT DEFAULT '08:00 - 16:00'")
    
    conn.commit()
    conn.close()

init_db()

# ================= SECURITY HELPERS ================= #
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

def check_password(password, hashed):
    if isinstance(hashed, str): hashed = hashed.encode('utf-8')
    elif isinstance(hashed, memoryview): hashed = hashed.tobytes()
    try: return bcrypt.checkpw(password.encode('utf-8'), hashed)
    except: return False

def is_valid_gmail(email):
    return bool(re.match(r"^[a-zA-Z0-9._%+-]+@gmail\.com$", email))

def is_strong_password(password):
    if len(password) < 8: return False, "Min 8 characters required."
    if not any(c.isupper() for c in password): return False, "Need 1 uppercase letter."
    if not any(c.isdigit() for c in password): return False, "Need 1 number."
    if not any(c in "!@#$%^&*()" for c in password): return False, "Need 1 special character."
    return True, ""

# ================= UI STYLING ================= #
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

# ================= AUTHENTICATION ================= #
if not st.session_state.logged_in:
    st.title("🏥 MediVista Management Portal")
    mode = st.radio("Option", ["Login", "Register"], horizontal=True)
    email_in = st.text_input("Email (xxx@gmail.com)")
    pass_in = st.text_input("Password", type="password")

    if mode == "Register":
        role = st.selectbox("Role", ["Patient", "Admin", "Receptionist", "Hospital Staff", "Doctor"])
        if st.button("Create Account"):
            is_strong, msg = is_strong_password(pass_in)
            if not is_valid_gmail(email_in): st.error("Email must be @gmail.com")
            elif not is_strong: st.error(msg)
            else:
                conn = sqlite3.connect(DB_NAME)
                try:
                    conn.execute("INSERT INTO users VALUES (?,?,?)", (email_in, sqlite3.Binary(hash_password(pass_in)), role))
                    conn.commit()
                    st.success("Account Created! Login now.")
                except: st.error("User already exists.")
                conn.close()

    if mode == "Login":
        if st.button("Login"):
            conn = sqlite3.connect(DB_NAME)
            res = conn.execute("SELECT password, role FROM users WHERE email=?", (email_in,)).fetchone()
            conn.close()
            if res and check_password(pass_in, res[0]):
                st.session_state.logged_in = True
                st.session_state.role = res[1]
                st.session_state.user_email = email_in
                st.rerun()
            else: st.error("Invalid Credentials.")

# ================= MAIN APP ================= #
else:
    st.sidebar.title(f"Role: {st.session_state.role}")
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()

    conn = sqlite3.connect(DB_NAME)
    today = datetime.now().strftime("%Y-%m-%d")

    # ---------------- HOSPITAL STAFF ---------------- #
    if st.session_state.role == "Hospital Staff":
        st.title("👨‍⚕️ Staff Duty Board")
        st.subheader(f"Shifts & Assignments ({today})")
        # Fixed query
        staff_df = pd.read_sql_query("SELECT name as Doctor, nurse_assigned as 'Allocated Nurse', shift_timing as 'Shift' FROM doctors", conn)
        st.table(staff_df)

        st.subheader("Today's Appointments")
        staff_appts = pd.read_sql_query(f"""
            SELECT p.name as Patient, d.name as Doctor, a.appointment_date 
            FROM appointments a 
            JOIN patients p ON a.patient_id = p.id 
            JOIN doctors d ON a.doctor_id = d.id 
            WHERE a.appointment_date = '{today}'""", conn)
        st.dataframe(staff_appts, width='stretch')

    # ---------------- RECEPTIONIST ---------------- #
    elif st.session_state.role == "Receptionist":
        st.title("📞 Reception Desk")
        t1, t2 = st.tabs(["Today's Bookings", "New Appointment"])
        with t1:
            st.dataframe(pd.read_sql_query(f"SELECT * FROM appointments WHERE appointment_date='{today}'", conn), width='stretch')
        with t2:
            with st.form("rec_book"):
                p_list = pd.read_sql_query("SELECT id, name FROM patients", conn)
                d_list = pd.read_sql_query("SELECT id, name FROM doctors", conn)
                if not p_list.empty and not d_list.empty:
                    sel_p = st.selectbox("Patient", p_list['name'])
                    sel_d = st.selectbox("Doctor", d_list['name'])
                    if st.form_submit_button("Book Now"):
                        pid = p_list[p_list['name']==sel_p]['id'].iloc[0]
                        did = d_list[d_list['name']==sel_d]['id'].iloc[0]
                        conn.execute("INSERT INTO appointments (patient_id, doctor_id, appointment_date) VALUES (?,?,?)", (int(pid), int(did), today))
                        conn.commit()
                        st.success("Booked!")

    # ---------------- DOCTOR ---------------- #
    elif st.session_state.role == "Doctor":
        st.title("🩺 Doctor Dashboard")
        feedback = pd.read_sql_query("SELECT name as Patient, query as Message, is_complaint FROM queries", conn)
        if not feedback.empty:
            st.error("🚨 Complaints")
            st.dataframe(feedback[feedback['is_complaint'] == 1], width='stretch')
            st.info("❓ Inquiries")
            st.dataframe(feedback[feedback['is_complaint'] == 0], width='stretch')
        else: st.write("No feedback yet.")

    # ---------------- ADMIN ---------------- #
    elif st.session_state.role == "Admin":
        page = st.sidebar.radio("Nav", ["Dashboard", "Doctors Allotment", "Reports"])
        if page == "Dashboard":
            st.title("Hospital Dashboard")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Visits", pd.read_sql_query("SELECT COUNT(*) FROM patients", conn).iloc[0,0])
            m2.metric("Doctors", pd.read_sql_query("SELECT COUNT(*) FROM doctors", conn).iloc[0,0])
            m3.metric("Rooms", pd.read_sql_query("SELECT COUNT(*) FROM rooms WHERE status='Available'", conn).iloc[0,0])
            m4.metric("Queries", pd.read_sql_query("SELECT COUNT(*) FROM queries WHERE status='Open'", conn).iloc[0,0])
            
            # Graphs
            g1, g2 = st.columns(2)
            with g1:
                fig = px.pie(pd.read_sql_query("SELECT role, COUNT(*) as count FROM users GROUP BY role", conn), names='role', values='count', hole=0.4)
                fig.update_layout(template="plotly_dark")
                st.plotly_chart(fig, width='stretch')
            with g2:
                fig2 = px.bar(pd.read_sql_query("SELECT name, booked_slots FROM doctors", conn), x='name', y='booked_slots', color_discrete_sequence=['#87CEFA'])
                fig2.update_layout(template="plotly_dark")
                st.plotly_chart(fig2, width='stretch')

        elif page == "Doctors Allotment":
            st.title("Manage Staff & Duty")
            with st.expander("Add Doctor & Assign Nurse"):
                with st.form("add_doc"):
                    n = st.text_input("Doctor Name")
                    s = st.selectbox("Specialty", ["Cardiology", "Neurology", "Pediatrics", "Orthopedics"])
                    nurse = st.text_input("Allocate Nurse")
                    shift = st.selectbox("Shift", ["08:00 - 16:00", "16:00 - 00:00", "00:00 - 08:00"])
                    if st.form_submit_button("Save"):
                        conn.execute("INSERT INTO doctors (name, specialty, total_slots, nurse_assigned, shift_timing) VALUES (?,?,?,?,?)", (n, s, 10, nurse, shift))
                        conn.commit()
                        st.rerun()
            st.dataframe(pd.read_sql_query("SELECT * FROM doctors", conn), width='stretch')

    conn.close()
