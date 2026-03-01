import streamlit as st
import sqlite3
import pandas as pd
import bcrypt
import re
import os
from datetime import datetime
import plotly.express as px
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4

# 1. Page Configuration & Styling
st.set_page_config(page_title="MediVista Hospital", layout="wide", page_icon="🏥")

st.markdown("""
    <style>
    .stMetric { background-color: #1e2130; padding: 15px; border-radius: 10px; border: 1px solid #3d4455; }
    div[data-testid="stSidebarNav"] { padding-top: 20px; }
    .stButton>button { width: 100%; border-radius: 5px; }
    [data-testid="stSidebar"] { background-color: #0e1117; }
    </style>
    """, unsafe_allow_html=True)

DB = "medivista.db"

# ---------------- DATABASE ---------------- #
def connect():
    return sqlite3.connect(DB, check_same_thread=False)

def init_db():
    conn = connect()
    c = conn.cursor()
    # Users Table
    c.execute("CREATE TABLE IF NOT EXISTS users(email TEXT PRIMARY KEY, password BLOB, role TEXT)")
    # Specialties
    c.execute("CREATE TABLE IF NOT EXISTS specialties(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE)")
    # Doctors
    c.execute("""CREATE TABLE IF NOT EXISTS doctors(
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT UNIQUE, 
        specialty_id INTEGER, total_slots INTEGER, nurse_assigned TEXT, shift_timing TEXT)""")
    # Patients
    c.execute("""CREATE TABLE IF NOT EXISTS patients(
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, age INTEGER, blood_group TEXT, 
        reason TEXT, amount_paid REAL, visit_date TEXT, email TEXT)""")
    # Appointments
    c.execute("""CREATE TABLE IF NOT EXISTS appointments(
        id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER, doctor_id INTEGER, 
        appointment_date TEXT, appointment_time TEXT)""")
    # Queries
    c.execute("""CREATE TABLE IF NOT EXISTS queries(
        id INTEGER PRIMARY KEY AUTOINCREMENT, patient_email TEXT, doctor_name TEXT, 
        query_text TEXT, query_type TEXT, status TEXT DEFAULT 'Pending', created_at TEXT)""")
    conn.commit()
    conn.close()

init_db()

# ---------------- AUTHENTICATION ---------------- #
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🏥 MediVista Hospital Management System")
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("Welcome Back")
        mode = st.radio("Select Action", ["Login", "Register"], horizontal=True)
        email = st.text_input("Gmail Address")
        password = st.text_input("Password", type="password")
        
        if mode == "Register":
            role = st.selectbox("Register As", ["Admin", "Receptionist", "Doctor", "Hospital Staff", "Patient"])
            if st.button("Create Account"):
                if not re.match(r"^[\w\.-]+@gmail\.com$", email):
                    st.error("Please use a valid @gmail.com address.")
                elif len(password) < 8:
                    st.error("Security requirement: Password must be at least 8 characters.")
                else:
                    conn = connect()
                    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
                    try:
                        conn.execute("INSERT INTO users VALUES (?,?,?)", (email, hashed, role))
                        conn.commit()
                        st.success("Registration successful! Please switch to Login.")
                    except:
                        st.error("User with this email already exists.")
                    conn.close()

        if mode == "Login":
            if st.button("Login"):
                conn = connect()
                user = conn.execute("SELECT password, role FROM users WHERE email=?", (email,)).fetchone()
                conn.close()
                if user and bcrypt.checkpw(password.encode(), user[0]):
                    st.session_state.logged_in = True
                    st.session_state.role = user[1]
                    st.session_state.email = email
                    st.rerun()
                else:
                    st.error("Invalid email or password.")
    
    with col2:
        st.info("""
        ### Portal Access Guide
        - **Admins**: Manage staff, view revenue analytics, and resolve system-wide queries.
        - **Doctors**: View schedules and respond to direct patient medical inquiries.
        - **Receptionists**: Handle patient intake and real-time appointment booking.
        - **Patients**: Access appointment history and contact medical staff.
        """)

# ---------------- MAIN DASHBOARD ---------------- #
else:
    role = st.session_state.role
    conn = connect()
    st.sidebar.image("https://cdn-icons-png.flaticon.com/512/3308/3308571.png", width=80)
    st.sidebar.title(f"Portal: {role}")
    st.sidebar.caption(f"Logged in: {st.session_state.email}")

    # Navigation Logic
    if role == "Admin":
        nav = st.sidebar.radio("Navigation", ["Dashboard", "Patient Records", "Doctor Management", "Finance & Reports", "System Queries"])
    elif role == "Receptionist":
        nav = st.sidebar.radio("Navigation", ["Register Patient", "Live Booking", "View All Patients"])
    elif role == "Doctor":
        nav = st.sidebar.radio("Navigation", ["Today's Schedule", "Direct Patient Queries"])
    elif role == "Hospital Staff":
        nav = st.sidebar.radio("Navigation", ["Staff Duty Board"])
    else:
        nav = st.sidebar.radio("Navigation", ["My Health Dashboard", "Submit New Query"])

    # --- ADMIN FEATURES ---
    if role == "Admin":
        if nav == "Dashboard":
            st.title("🏥 Administrative Dashboard")
            p_df = pd.read_sql_query("SELECT * FROM patients", conn)
            a_df = pd.read_sql_query("SELECT * FROM appointments", conn)
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Patients", len(p_df))
            c2.metric("Today's Revenue", f"₹{p_df[p_df['visit_date'] == datetime.now().strftime('%Y-%m-%d')]['amount_paid'].sum():,.2f}")
            c3.metric("Total Appointments", len(a_df))

            st.markdown("---")
            col_a, col_b = st.columns(2)
            with col_a:
                if not p_df.empty:
                    fig_p = px.bar(p_df.groupby("visit_date").size().reset_index(name="Count"), x="visit_date", y="Count", title="Patient Intake Trend", color_discrete_sequence=['#00CC96'])
                    st.plotly_chart(fig_p, use_container_width=True)
            with col_b:
                if not p_df.empty:
                    fig_r = px.line(p_df.groupby("visit_date")["amount_paid"].sum().reset_index(), x="visit_date", y="amount_paid", title="Daily Revenue (INR)", markers=True)
                    st.plotly_chart(fig_r, use_container_width=True)

        elif nav == "Doctor Management":
            st.subheader("👨‍⚕️ Manage Medical Staff")
            # Specialty Management First
            with st.expander("Manage Specialties"):
                with st.form("spec_form"):
                    new_spec = st.text_input("New Specialty Name")
                    if st.form_submit_button("Add Specialty"):
                        try:
                            conn.execute("INSERT INTO specialties(name) VALUES(?)", (new_spec,))
                            conn.commit()
                            st.success("Specialty added.")
                        except: st.error("Already exists.")
            
            # Doctor Addition
            specs = pd.read_sql_query("SELECT * FROM specialties", conn)
            with st.form("doc_form"):
                d_name = st.text_input("Doctor Name")
                d_email = st.text_input("Email")
                d_spec = st.selectbox("Specialty", specs["name"] if not specs.empty else ["None"])
                d_slots = st.number_input("Daily Capacity Slots", 5, 50, 20)
                d_nurse = st.text_input("Assigned Nurse")
                d_shift = st.text_input("Shift Hours (e.g. 09:00 - 17:00)")
                if st.form_submit_button("Hire Doctor"):
                    s_id = specs[specs["name"]==d_spec]["id"].iloc[0]
                    conn.execute("INSERT INTO doctors (name,email,specialty_id,total_slots,nurse_assigned,shift_timing) VALUES(?,?,?,?,?,?)",
                                 (d_name, d_email, s_id, d_slots, d_nurse, d_shift))
                    conn.commit()
                    st.success("Doctor record created.")
            st.dataframe(pd.read_sql_query("SELECT d.name, d.email, s.name as specialty, d.nurse_assigned, d.shift_timing FROM doctors d JOIN specialties s ON d.specialty_id = s.id", conn), width=1000)

        elif nav == "Finance & Reports":
            st.title("📄 Hospital Financial Reporting")
            p_df = pd.read_sql_query("SELECT name, visit_date, amount_paid FROM patients", conn)
            st.dataframe(p_df, use_container_width=True)
            if st.button("Download PDF Financial Report"):
                doc = SimpleDocTemplate("Hospital_Report.pdf", pagesize=A4)
                elements = [Paragraph("MediVista Hospital - Financial Summary", getSampleStyleSheet()["Title"]), Spacer(1, 20)]
                for _, row in p_df.iterrows():
                    elements.append(Paragraph(f"Date: {row['visit_date']} | Patient: {row['name']} | Paid: ₹{row['amount_paid']}", getSampleStyleSheet()["Normal"]))
                doc.build(elements)
                with open("Hospital_Report.pdf", "rb") as f:
                    st.download_button("Download Now", f, file_name="Hospital_Report.pdf")

    # --- RECEPTIONIST FEATURES ---
    elif role == "Receptionist":
        if nav == "Register Patient":
            st.title("New Patient Intake")
            with st.form("intake_form"):
                name = st.text_input("Full Name")
                age = st.number_input("Age", 0, 120)
                blood = st.selectbox("Blood Group", ["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"])
                reason = st.text_input("Medical Concern")
                pay = st.number_input("Consultation Fee (INR)", value=500.0)
                if st.form_submit_button("Finalize Intake"):
                    conn.execute("INSERT INTO patients (name, age, blood_group, reason, amount_paid, visit_date, email) VALUES(?,?,?,?,?,?,?)",
                                 (name, age, blood, reason, pay, datetime.now().strftime("%Y-%m-%d"), name.lower().replace(" ","")+"@gmail.com"))
                    conn.commit()
                    st.success(f"Inpatient record created for {name}.")

        elif nav == "Live Booking":
            st.title("Book Medical Appointment")
            patients = pd.read_sql_query("SELECT id, name FROM patients", conn)
            doctors = pd.read_sql_query("SELECT id, name FROM doctors", conn)
            if not patients.empty and not doctors.empty:
                with st.form("book_form"):
                    p_sel = st.selectbox("Patient Name", patients["name"])
                    d_sel = st.selectbox("Doctor Name", doctors["name"])
                    a_time = st.text_input("Time Slot (e.g., 10:30 AM)")
                    if st.form_submit_button("Confirm Booking"):
                        pid = patients[patients["name"]==p_sel]["id"].iloc[0]
                        did = doctors[doctors["name"]==d_sel]["id"].iloc[0]
                        conn.execute("INSERT INTO appointments (patient_id, doctor_id, appointment_date, appointment_time) VALUES(?,?,?,?)",
                                     (pid, did, datetime.now().strftime("%Y-%m-%d"), a_time))
                        conn.commit()
                        st.success("Appointment successfully scheduled.")

    # --- DOCTOR FEATURES ---
    elif role == "Doctor":
        if nav == "Today's Schedule":
            st.title("📅 My Appointments")
            st.dataframe(pd.read_sql_query("""
                SELECT p.name as Patient, a.appointment_time as Slot, p.reason as Medical_Concern
                FROM appointments a JOIN patients p ON a.patient_id = p.id
                JOIN doctors d ON a.doctor_id = d.id
                WHERE d.email = ? AND a.appointment_date = ?
            """, conn, params=(st.session_state.email, datetime.now().strftime("%Y-%m-%d"))), use_container_width=True)

        elif nav == "Direct Patient Queries":
            st.subheader("📬 Patient Inquiries")
            st.dataframe(pd.read_sql_query("SELECT patient_email, query_text, status FROM queries WHERE status = 'Pending'", conn))

    # --- STAFF FEATURES ---
    elif role == "Hospital Staff":
        st.title("📋 Staff Duty Board")
        # Image tag for organizational hierarchy
        st.write("Current Nurse and Shift Assignments:")
        st.dataframe(pd.read_sql_query("SELECT name as Doctor, nurse_assigned as Nurse, shift_timing as Shift FROM doctors", conn), use_container_width=True)
        

[Image of a hospital administration organizational chart]


    # --- PATIENT FEATURES ---
    elif role == "Patient":
        if nav == "My Health Dashboard":
            st.title("🩺 My Medical History")
            st.dataframe(pd.read_sql_query("SELECT visit_date, reason, amount_paid FROM patients WHERE name LIKE ?", conn, params=(f"%{st.session_state.email.split('@')[0]}%",)))
        
        elif nav == "Submit New Query":
            st.title("Contact Medical Staff")
            docs = pd.read_sql_query("SELECT name FROM doctors", conn)
            with st.form("query_form"):
                d_target = st.selectbox("Target Doctor", docs["name"] if not docs.empty else ["No Doctors Available"])
                q_type = st.radio("Query Confidentiality", ["Doctor Only", "Hospital + Doctor"])
                q_text = st.text_area("Detail your query/complaint")
                if st.form_submit_button("Send Query"):
                    conn.execute("INSERT INTO queries (patient_email, doctor_name, query_text, query_type, created_at) VALUES(?,?,?,?,?)",
                                 (st.session_state.email, d_target, q_text, q_type, datetime.now().strftime("%Y-%m-%d %H:%M")))
                    conn.commit()
                    st.success("Query sent to medical staff.")

    # ---------------- GLOBAL LOGOUT ---------------- #
    st.sidebar.markdown("---")
    if st.sidebar.button("🔒 Secure Logout"):
        st.session_state.logged_in = False
        st.session_state.role = None
        st.session_state.email = None
        st.rerun()

    conn.close()
