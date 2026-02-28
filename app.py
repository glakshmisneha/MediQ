import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import bcrypt
import os
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
    c.execute("CREATE TABLE IF NOT EXISTS users(email TEXT PRIMARY KEY, password BLOB, role TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS doctors(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, specialty TEXT, total_slots INTEGER, booked_slots INTEGER DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS patients(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, age INTEGER, blood_group TEXT, reason TEXT, amount_paid REAL, visit_date TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS appointments(id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER, doctor_id INTEGER, appointment_date TEXT)")
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

# ================= UI STYLING ================= #
st.markdown("""
    <style>
    /* Dashboard Metric Styling */
    div[data-testid="stMetricValue"] { color: #ffffff; font-size: 42px; font-weight: bold; }
    div[data-testid="stMetricLabel"] { color: #888888; font-size: 16px; }
    
    /* Button Styling */
    .stButton>button { background-color: #00acee; color: white; border-radius: 20px; border: none; font-weight: bold; width: 100px; }
    
    /* Sidebar Styling */
    .stSidebar { background-color: #0e1117; }
    
    /* Form and Dataframe Styling */
    [data-testid="stForm"] { border: 1px solid #30363d !important; border-radius: 15px; background-color: #161b22; }
    </style>
    """, unsafe_allow_html=True)

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# ================= AUTHENTICATION FLOW ================= #
if not st.session_state.logged_in:
    st.title("🏥 MediVista Login")
    mode = st.radio("Option", ["Login", "Register"], horizontal=True)
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if mode == "Register":
        role = st.selectbox("Role", ["Admin", "Receptionist", "Hospital Staff"])
        if st.button("Create Account"):
            hashed = hash_password(password)
            conn = sqlite3.connect(DB_NAME)
            try:
                conn.execute("INSERT INTO users (email, password, role) VALUES (?,?,?)", (email, sqlite3.Binary(hashed), role))
                conn.commit()
                st.success("Account Created Successfully!")
            except: st.error("User already exists.")
            conn.close()

    if mode == "Login":
        if st.button("Login"):
            conn = sqlite3.connect(DB_NAME)
            res = conn.execute("SELECT password, role FROM users WHERE email=?", (email,)).fetchone()
            conn.close()
            if res and check_password(password, res[0]):
                st.session_state.logged_in = True
                st.session_state.role = res[1]
                st.rerun()
            else: st.error("Invalid Credentials.")

# ================= MAIN APPLICATION ================= #
else:
    st.sidebar.title("MediVista Admin")
    st.sidebar.info(f"Access Level: **{st.session_state.role}**")
    page = st.sidebar.radio("Navigation", ["Dashboard", "Doctors Allotment", "Patient Details", "Appointments", "Reports"])

    st.sidebar.markdown("---")
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()

    conn = sqlite3.connect(DB_NAME)

    # -------- DASHBOARD (MATCHING YOUR SCREENSHOTS) -------- #
    if page == "Dashboard":
        st.title("Hospital Dashboard")
        patients = pd.read_sql_query("SELECT * FROM patients", conn)
        apps = pd.read_sql_query("SELECT * FROM appointments", conn)
        
        # Metric Row
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Visits", len(patients))
        m2.metric("Total Revenue", f"₹ {patients['amount_paid'].sum() if not patients.empty else 0.0}")
        m3.metric("Total Appointments", len(apps))

        st.divider()
        
        if not patients.empty:
            # Bar Chart: Visits by Reason
            st.subheader("Visits by Reason")
            reasons = patients['reason'].value_counts().reset_index()
            reasons.columns = ['reason', 'count']
            fig_reason = px.bar(reasons, x='reason', y='count', color_discrete_sequence=['#87CEFA'])
            fig_reason.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_reason, width='stretch')

            # Bar Chart: Doctor Workload Distribution
            st.subheader("Doctor Workload Distribution")
            doc_data = pd.read_sql_query("SELECT name, booked_slots FROM doctors", conn)
            if not doc_data.empty:
                fig_doc = px.bar(doc_data, x='name', y='booked_slots', color_discrete_sequence=['#87CEFA'])
                fig_doc.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig_doc, width='stretch')

    # -------- DOCTORS ALLOTMENT -------- #
    elif page == "Doctors Allotment":
        st.title("Doctors Allotment")
        specialties = ["Cardiology", "Dermatology", "Neurology", "Pediatrics", "Orthopedics", "General Medicine"]
        with st.expander("➕ Add Doctor Details"):
            with st.form("doc_form"):
                n = st.text_input("Doctor Name")
                s = st.selectbox("Specialty", specialties)
                sl = st.number_input("Daily Slots", 1, 100)
                if st.form_submit_button("Save Doctor"):
                    conn.execute("INSERT INTO doctors (name, specialty, total_slots) VALUES (?,?,?)", (n, s, sl))
                    conn.commit()
                    st.rerun()
        st.dataframe(pd.read_sql_query("SELECT * FROM doctors", conn), width='stretch')

    # -------- PATIENT DETAILS -------- #
    elif page == "Patient Details":
        st.title("Patient Details")
        with st.expander("➕ Register New Patient"):
            with st.form("p_form"):
                c1, c2 = st.columns(2)
                name = c1.text_input("Name")
                age = c2.number_input("Age", 0, 120)
                blood = c1.selectbox("Blood Group", ["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"])
                reason = c2.text_input("Reason")
                pay = c1.number_input("Payment", 0.0)
                if st.form_submit_button("Add Patient"):
                    conn.execute("INSERT INTO patients (name, age, blood_group, reason, amount_paid, visit_date) VALUES (?,?,?,?,?,?)",
                                (name, age, blood, reason, pay, datetime.now().strftime("%Y-%m-%d")))
                    conn.commit()
                    st.rerun()
        st.dataframe(pd.read_sql_query("SELECT * FROM patients", conn), width='stretch')

    # -------- APPOINTMENTS -------- #
    elif page == "Appointments":
        st.title("Appointment Booking")
        p_df = pd.read_sql_query("SELECT id, name FROM patients", conn)
        d_df = pd.read_sql_query("SELECT id, name, total_slots, booked_slots FROM doctors", conn)
        
        if not p_df.empty and not d_df.empty:
            p_sel = st.selectbox("Select Patient", p_df["name"])
            d_sel = st.selectbox("Select Doctor", d_df["name"])
            if st.button("Confirm Appointment"):
                doc = d_df[d_df["name"] == d_sel].iloc[0]
                if doc["booked_slots"] < doc["total_slots"]:
                    pid = p_df[p_df["name"] == p_sel]["id"].iloc[0]
                    conn.execute("INSERT INTO appointments (patient_id, doctor_id, appointment_date) VALUES (?,?,?)",
                                (int(pid), int(doc["id"]), datetime.now().strftime("%Y-%m-%d")))
                    conn.execute("UPDATE doctors SET booked_slots = booked_slots + 1 WHERE id=?", (int(doc["id"]),))
                    conn.commit()
                    st.rerun()
        
        st.write("### Recent History")
        history = pd.read_sql_query("SELECT * FROM appointments", conn)
        if not history.empty:
            history['patient_id'] = history['patient_id'].astype(str)
            history['doctor_id'] = history['doctor_id'].astype(str)
        st.dataframe(history, width='stretch')

    # -------- REPORTS -------- #
    elif page == "Reports":
        st.title("📊 Hospital Reports")
        report_df = pd.read_sql_query("SELECT name, blood_group, reason, amount_paid, visit_date FROM patients", conn)
        
        if not report_df.empty:
            st.subheader("Report Content Preview")
            st.metric("Total Revenue Preview", f"₹ {report_df['amount_paid'].sum():,.2f}")
            st.dataframe(report_df, width='stretch')
            
            if st.button("Generate & Download PDF"):
                fn = f"MediVista_Report_{datetime.now().strftime('%Y%m%d')}.pdf"
                doc_pdf = SimpleDocTemplate(fn, pagesize=A4)
                parts = []
                title_style = ParagraphStyle('Title', fontSize=22, alignment=1, spaceAfter=20)
                body_style = ParagraphStyle('Normal', fontSize=12, spaceAfter=10)
                parts.append(Paragraph("<b>MediVista Hospital Revenue Report</b>", title_style))
                parts.append(Paragraph(f"<b>Date Generated:</b> {datetime.now().strftime('%Y-%m-%d %H:%M')}", body_style))
                parts.append(Spacer(1, 0.2 * inch))
                parts.append(Paragraph(f"<b>Total Gross Revenue:</b> ₹{report_df['amount_paid'].sum():,.2f}", body_style))
                doc_pdf.build(parts)
                with open(fn, "rb") as f:
                    st.download_button("Download PDF", f, file_name=fn)
        else:
            st.warning("No data found to generate a report.")

    conn.close()
