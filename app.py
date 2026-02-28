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
    c.execute("CREATE TABLE IF NOT EXISTS users(email TEXT PRIMARY KEY, password BLOB, role TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS doctors(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, specialty TEXT, total_slots INTEGER, booked_slots INTEGER DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS patients(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, age INTEGER, blood_group TEXT, reason TEXT, amount_paid REAL, visit_date TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS appointments(id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER, doctor_id INTEGER, appointment_date TEXT)")
    conn.commit()
    conn.close()

init_db()

# ================= SECURITY ================= #

def check_password(password, hashed):
    if isinstance(hashed, str): hashed = hashed.encode('utf-8')
    elif isinstance(hashed, memoryview): hashed = hashed.tobytes()
    return bcrypt.checkpw(password.encode('utf-8'), hashed)

# ================= CONFIG ================= #

st.set_page_config(page_title="MediVista Admin", layout="wide")

# Custom CSS for the MediVista look
st.markdown("""
    <style>
    div[data-testid="stMetricValue"] { color: #ffffff; font-size: 36px; font-weight: bold; }
    .stButton>button { background-color: #00acee; color: white; border-radius: 20px; border: none; }
    .stDataFrame { border: 1px solid #333; }
    </style>
    """, unsafe_allow_html=True)

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# ================= AUTH ================= #

if not st.session_state.logged_in:
    st.title("🏥 MediVista Admin Login")
    # Simplified login for demonstration; use your full registration/login logic here
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        conn = connect_db()
        c = conn.cursor()
        c.execute("SELECT password, role FROM users WHERE email=?", (email,))
        result = c.fetchone()
        if result and check_password(password, result[0]):
            st.session_state.logged_in = True
            st.session_state.role = result[1]
            st.rerun()
        else:
            st.error("Invalid Credentials")
        conn.close()

# ================= MAIN APP ================= #
else:
    st.sidebar.title("MediVista Admin")
    st.sidebar.write(f"Logged in as: **{st.session_state.get('role', 'Admin')}**")
    
    page = st.sidebar.radio("Navigation", ["Dashboard", "Doctors Allotment", "Patient Details", "Appointments", "Reports"])

    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()

    conn = connect_db()

    # -------- DASHBOARD -------- #
    if page == "Dashboard":
        st.title("Hospital Dashboard")
        
        patients_df = pd.read_sql_query("SELECT * FROM patients", conn)
        appointments_df = pd.read_sql_query("SELECT * FROM appointments", conn)
        total_rev = patients_df["amount_paid"].sum() if not patients_df.empty else 0.0

        # Metrics Row (Matching Screenshot 1)
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Visits", len(patients_df))
        m2.metric("Total Revenue", f"₹ {total_rev}")
        m3.metric("Total Appointments", len(appointments_df))

        st.divider()

        # Visits by Reason Chart (Matching Screenshot 1)
        if not patients_df.empty:
            st.subheader("Visits by Reason")
            reason_counts = patients_df['reason'].value_counts().reset_index()
            reason_counts.columns = ['reason', 'count']
            fig_reason = px.bar(reason_counts, x='reason', y='count', color_discrete_sequence=['#87CEFA'])
            fig_reason.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_reason, width='stretch')

        # Workload Distribution (Matching Screenshot 2)
        st.subheader("Doctor Workload Distribution")
        doctors_df = pd.read_sql_query("SELECT name, booked_slots FROM doctors", conn)
        if not doctors_df.empty:
            fig_work = px.bar(doctors_df, x='name', y='booked_slots', color_discrete_sequence=['#1f77b4'])
            fig_work.update_layout(template="plotly_dark")
            st.plotly_chart(fig_work, width='stretch')

    # -------- DOCTORS -------- #
    elif page == "Doctors Allotment":
        st.title("Doctors Allotment")
        if st.session_state.get('role') == "Admin":
            with st.expander("Add New Doctor"):
                d_name = st.text_input("Name")
                d_spec = st.text_input("Specialty")
                d_slots = st.number_input("Total Slots", 1, 100)
                if st.button("Save Doctor"):
                    c = conn.cursor()
                    c.execute("INSERT INTO doctors (name, specialty, total_slots) VALUES (?,?,?)", (d_name, d_spec, d_slots))
                    conn.commit()
                    st.success("Doctor Added")
                    st.rerun()
        
        st.dataframe(pd.read_sql_query("SELECT * FROM doctors", conn), width='stretch')

    # -------- PATIENTS -------- #
    elif page == "Patient Details":
        st.title("Patient Details")
        with st.form("patient_form"):
            col1, col2 = st.columns(2)
            p_name = col1.text_input("Name")
            p_age = col2.number_input("Age", 0, 120)
            
            # CHANGE: Selectbox for Blood Group
            p_blood = col1.selectbox("Blood Group", ["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"])
            p_reason = col2.text_input("Reason")
            p_payment = col1.number_input("Amount Paid", 0.0)
            
            if st.form_submit_button("Add Patient"):
                c = conn.cursor()
                c.execute("INSERT INTO patients (name, age, blood_group, reason, amount_paid, visit_date) VALUES (?,?,?,?,?,?)",
                         (p_name, p_age, p_blood, p_reason, p_payment, datetime.now().strftime("%Y-%m-%d")))
                conn.commit()
                st.success("Patient Registered")
                st.rerun()
        
        st.dataframe(pd.read_sql_query("SELECT * FROM patients", conn), width='stretch')

    # -------- APPOINTMENTS -------- #
    elif page == "Appointments":
        st.title("Appointment Booking")
        
        patients_df = pd.read_sql_query("SELECT id, name FROM patients", conn)
        doctors_df = pd.read_sql_query("SELECT id, name, total_slots, booked_slots FROM doctors", conn)
        
        # Booking Logic
        p_choice = st.selectbox("Select Patient", patients_df["name"]) if not patients_df.empty else None
        d_choice = st.selectbox("Select Doctor", doctors_df["name"]) if not doctors_df.empty else None
        
        if st.button("Book Appointment"):
            if p_choice and d_choice:
                doc = doctors_df[doctors_df["name"] == d_choice].iloc[0]
                if doc["booked_slots"] < doc["total_slots"]:
                    pid = patients_df[patients_df["name"] == p_choice]["id"].iloc[0]
                    c = conn.cursor()
                    c.execute("INSERT INTO appointments (patient_id, doctor_id, appointment_date) VALUES (?,?,?)",
                             (int(pid), int(doc["id"]), datetime.now().strftime("%Y-%m-%d")))
                    c.execute("UPDATE doctors SET booked_slots = booked_slots + 1 WHERE id=?", (int(doc["id"]),))
                    conn.commit()
                    st.success("Booking Successful")
                    st.rerun()
                else:
                    st.error("No Slots Available")

        # Table showing current appointments (Matching Screenshot 3)
        st.subheader("Appointment List")
        history_df = pd.read_sql_query("SELECT * FROM appointments", conn)
        st.dataframe(history_df, width='stretch')

    # -------- REPORTS -------- #
    elif page == "Reports":
        st.title("Generate Reports")
        if st.button("Generate Revenue PDF Report"):
            patients_df = pd.read_sql_query("SELECT * FROM patients", conn)
            total = patients_df["amount_paid"].sum()
            file_name = "MediVista_Revenue_Report.pdf"
            
            doc_pdf = SimpleDocTemplate(file_name, pagesize=A4)
            elements = []
            style = ParagraphStyle(name='Normal', fontSize=12, textColor='#000000')
            header_style = ParagraphStyle(name='Header', fontSize=18, spaceAfter=20)

            elements.append(Paragraph("MediVista Hospital Revenue Report", header_style))
            elements.append(Paragraph(f"Date: {datetime.now().strftime('%Y-%m-%d')}", style))
            elements.append(Spacer(1, 0.2 * inch))
            elements.append(Paragraph(f"Total Patients: {len(patients_df)}", style))
            elements.append(Paragraph(f"Total Revenue Collected: ₹{total}", style))
            
            doc_pdf.build(elements)
            
            with open(file_name, "rb") as f:
                st.download_button("Download PDF", f, file_name=file_name)

    conn.close()
