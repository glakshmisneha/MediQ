import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import re
import bcrypt
from datetime import datetime
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch

DB_NAME = "mediq.db"

# ================= DATABASE ================= #

def connect_db():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = connect_db()
    c = conn.cursor()

    # Check if users table exists
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    table_exists = c.fetchone()

    if not table_exists:
        c.execute("""
        CREATE TABLE users(
            email TEXT PRIMARY KEY,
            password BLOB,
            role TEXT
        )
        """)
    else:
        c.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in c.fetchall()]
        if "role" not in columns:
            c.execute("CREATE TABLE users_new(email TEXT PRIMARY KEY, password BLOB, role TEXT DEFAULT 'Receptionist')")
            c.execute("INSERT INTO users_new (email, password) SELECT email, password FROM users")
            c.execute("DROP TABLE users")
            c.execute("ALTER TABLE users_new RENAME TO users")

    c.execute("CREATE TABLE IF NOT EXISTS doctors(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, specialty TEXT, total_slots INTEGER, booked_slots INTEGER DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS patients(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, age INTEGER, blood_group TEXT, reason TEXT, amount_paid REAL, visit_date TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS appointments(id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER, doctor_id INTEGER, appointment_date TEXT)")
    
    conn.commit()
    conn.close()

init_db()

# ================= SECURITY ================= #

def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

def check_password(password, hashed):
    # Fix: Ensure hashed is bytes. SQLite 'BLOB' can return bytes or memoryview.
    if isinstance(hashed, memoryview):
        hashed = hashed.tobytes()
    elif isinstance(hashed, str):
        hashed = hashed.encode('utf-8')
    
    return bcrypt.checkpw(password.encode('utf-8'), hashed)

def strong_password(password):
    return (len(password) >= 8 and
            re.search(r"[A-Z]", password) and
            re.search(r"[a-z]", password) and
            re.search(r"[0-9]", password))

# ================= CONFIG ================= #

st.set_page_config(page_title="MediQ", layout="wide")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "role" not in st.session_state:
    st.session_state.role = None

# ================= AUTH ================= #

if not st.session_state.logged_in:
    st.title("🏥 MediQ")
    st.subheader("Smart Hospital Management System")

    mode = st.radio("Select Option", ["Login", "Register"], horizontal=True)
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    conn = connect_db()
    c = conn.cursor()

    if mode == "Register":
        role = st.selectbox("Select Role", ["Admin", "Receptionist"])
        if st.button("Create Account"):
            if not strong_password(password):
                st.error("Password must contain uppercase, lowercase & number (min 8 chars)")
            else:
                hashed = hash_password(password)
                try:
                    # Using sqlite3.Binary ensures the hashed bytes are stored correctly as BLOB
                    c.execute("INSERT INTO users (email,password,role) VALUES (?,?,?)",
                             (email, sqlite3.Binary(hashed), role))
                    conn.commit()
                    st.success("Account Created Successfully! Please switch to Login.")
                except sqlite3.IntegrityError:
                    st.error("User already exists")

    if mode == "Login":
        if st.button("Login"):
            c.execute("SELECT password, role FROM users WHERE email=?", (email,))
            result = c.fetchone()
            if result:
                stored_password, role = result
                try:
                    if check_password(password, stored_password):
                        st.session_state.logged_in = True
                        st.session_state.role = role
                        st.rerun()
                    else:
                        st.error("Invalid credentials")
                except Exception as e:
                    st.error(f"Authentication Error: {e}")
            else:
                st.error("User not found")
    conn.close()

# ================= MAIN APP ================= #
else:
    # Sidebar & Logic remains the same...
    st.sidebar.title("MediQ Panel")
    st.sidebar.write(f"Logged in as: **{st.session_state.role}**")
    
    page = st.sidebar.radio("Navigation", ["Dashboard", "Doctors", "Patients", "Appointments", "Reports"])

    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.role = None
        st.rerun()

    conn = connect_db()
    c = conn.cursor()

    if page == "Dashboard":
        patients_df = pd.read_sql_query("SELECT * FROM patients", conn)
        doctors_df = pd.read_sql_query("SELECT * FROM doctors", conn)
        col1, col2 = st.columns(2)
        col1.metric("Total Patients", len(patients_df))
        col2.metric("Total Doctors", len(doctors_df))
        if not doctors_df.empty:
            doctors_df["Available Slots"] = doctors_df["total_slots"] - doctors_df["booked_slots"]
            fig = px.bar(doctors_df, x="name", y="Available Slots", title="Doctor Availability")
            st.plotly_chart(fig, use_container_width=True)

    elif page == "Doctors":
        if st.session_state.role == "Admin":
            st.subheader("Add Doctor")
            d_name = st.text_input("Doctor Name")
            spec = st.text_input("Specialty")
            slots = st.number_input("Total Slots", 1, 100)
            if st.button("Add Doctor"):
                c.execute("INSERT INTO doctors (name,specialty,total_slots) VALUES (?,?,?)", (d_name, spec, slots))
                conn.commit()
                st.success("Doctor Added")
                st.rerun()
        st.dataframe(pd.read_sql_query("SELECT * FROM doctors", conn))

    elif page == "Patients":
        st.subheader("Add Patient")
        p_name = st.text_input("Patient Name")
        age = st.number_input("Age", 0, 120)
        blood = st.text_input("Blood Group")
        reason = st.text_input("Reason")
        payment = st.number_input("Payment", 0.0)
        if st.button("Add Patient"):
            c.execute("INSERT INTO patients (name,age,blood_group,reason,amount_paid,visit_date) VALUES (?,?,?,?,?,?)",
                     (p_name, age, blood, reason, payment, datetime.now().strftime("%Y-%m-%d")))
            conn.commit()
            st.success("Patient Added")
            st.rerun()
        st.dataframe(pd.read_sql_query("SELECT * FROM patients", conn))

    elif page == "Appointments":
        patients_df = pd.read_sql_query("SELECT id,name FROM patients", conn)
        doctors_df = pd.read_sql_query("SELECT * FROM doctors", conn)
        if not patients_df.empty and not doctors_df.empty:
            p_choice = st.selectbox("Patient", patients_df["name"])
            d_choice = st.selectbox("Doctor", doctors_df["name"])
            if st.button("Book Appointment"):
                doc = doctors_df[doctors_df["name"] == d_choice].iloc[0]
                if doc["booked_slots"] < doc["total_slots"]:
                    pid = patients_df[patients_df["name"] == p_choice]["id"].iloc[0]
                    c.execute("INSERT INTO appointments (patient_id,doctor_id,appointment_date) VALUES (?,?,?)",
                             (pid, doc["id"], datetime.now().strftime("%Y-%m-%d")))
                    c.execute("UPDATE doctors SET booked_slots = booked_slots + 1 WHERE id=?", (int(doc["id"]),))
                    conn.commit()
                    st.success("Appointment Booked")
                    st.rerun()
                else:
                    st.error("No Slots Available")

    elif page == "Reports":
        if st.button("Generate Revenue PDF"):
            patients_df = pd.read_sql_query("SELECT * FROM patients", conn)
            total = patients_df["amount_paid"].sum()
            file_name = "MediQ_Report.pdf"
            doc_pdf = SimpleDocTemplate(file_name, pagesize=A4)
            elements = []
            style = ParagraphStyle(name='Normal', fontSize=12)
            elements.append(Paragraph("MediQ Revenue Report", style))
            elements.append(Spacer(1, 0.5 * inch))
            elements.append(Paragraph(f"Total Revenue: ₹{total}", style))
            doc_pdf.build(elements)
            with open(file_name, "rb") as f:
                st.download_button("Download Report", f, file_name=file_name)
    
    conn.close()
