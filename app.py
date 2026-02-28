import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import re
import bcrypt
import os
from datetime import datetime
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch

# 1. MUST BE THE VERY FIRST STREAMLIT COMMAND
st.set_page_config(page_title="MediVista Admin", layout="wide")

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

def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

def check_password(password, hashed):
    """Verifies password against a stored hash with safety checks."""
    try:
        # Convert stored data to bytes if necessary
        if isinstance(hashed, str):
            hashed = hashed.encode('utf-8')
        elif isinstance(hashed, memoryview):
            hashed = hashed.tobytes()
        
        # Verify the hash
        return bcrypt.checkpw(password.encode('utf-8'), hashed)
    except Exception:
        # Catch "Invalid salt" errors without crashing the app
        return False

# ================= STYLING ================= #

st.markdown("""
    <style>
    div[data-testid="stMetricValue"] { color: #ffffff; font-size: 38px; font-weight: bold; }
    .stButton>button { background-color: #00acee; color: white; border-radius: 20px; border: none; font-weight: bold; width: 100%; }
    .logout-footer { padding-top: 50px; }
    </style>
    """, unsafe_allow_html=True)

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# ================= AUTH ================= #

if not st.session_state.logged_in:
    st.title("🏥 MediVista Login")
    mode = st.radio("Option", ["Login", "Register"], horizontal=True)
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if mode == "Register":
        role = st.selectbox("Role", ["Admin", "Receptionist"])
        if st.button("Create Account"):
            hashed = hash_password(password)
            conn = connect_db()
            try:
                # Store as Binary to ensure correct BLOB format
                conn.execute("INSERT INTO users (email, password, role) VALUES (?,?,?)", 
                             (email, sqlite3.Binary(hashed), role))
                conn.commit()
                st.success("Account Created! You can now switch to Login.")
            except: st.error("User already exists")
            conn.close()

    if mode == "Login":
        if st.button("Login"):
            conn = connect_db()
            res = conn.execute("SELECT password, role FROM users WHERE email=?", (email,)).fetchone()
            conn.close()
            
            if res and check_password(password, res[0]):
                st.session_state.logged_in = True
                st.session_state.role = res[1]
                st.rerun()
            else: 
                st.error("Invalid Credentials or Corrupted Account (Invalid Salt)")

# ================= MAIN APP ================= #
else:
    st.sidebar.title("MediVista Admin")
    st.sidebar.write(f"Logged in as: **{st.session_state.role}**")
    page = st.sidebar.radio("Navigation", ["Dashboard", "Doctors Allotment", "Patient Details", "Appointments", "Reports", "Settings"])

    if st.sidebar.button("Quick Logout"):
        st.session_state.logged_in = False
        st.rerun()

    conn = connect_db()

    # -------- DASHBOARD -------- #
    if page == "Dashboard":
        st.title("Hospital Dashboard")
        patients = pd.read_sql_query("SELECT * FROM patients", conn)
        apps = pd.read_sql_query("SELECT * FROM appointments", conn)
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Visits", len(patients))
        m2.metric("Total Revenue", f"₹ {patients['amount_paid'].sum() if not patients.empty else 0.0}")
        m3.metric("Total Appointments", len(apps))

        if not patients.empty:
            st.divider()
            st.write("### Visits by Reason")
            reasons = patients['reason'].value_counts().reset_index()
            reasons.columns = ['reason', 'count']
            fig_r = px.bar(reasons, x='reason', y='count', color_discrete_sequence=['#87CEFA'])
            fig_r.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_r, width='stretch')

    # -------- PATIENTS -------- #
    elif page == "Patient Details":
        st.title("Patient Details")
        with st.form("p_form"):
            c1, c2 = st.columns(2)
            name = c1.text_input("Name")
            age = c2.number_input("Age", 0)
            # Selection box for consistency
            blood = c1.selectbox("Blood Group", ["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"])
            reason = c2.text_input("Reason")
            pay = c1.number_input("Payment", 0.0)
            if st.form_submit_button("Register Patient"):
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

        st.write("### Recent Appointment History")
        history_df = pd.read_sql_query("SELECT * FROM appointments", conn)
        if not history_df.empty:
            # FIX: Convert IDs to strings to prevent Arrow Serialization Error
            history_df['patient_id'] = history_df['patient_id'].astype(str)
            history_df['doctor_id'] = history_df['doctor_id'].astype(str)
            st.dataframe(history_df, width='stretch')

    # -------- REPORTS -------- #
    elif page == "Reports":
        st.title("Hospital Analytics")
        report_df = pd.read_sql_query("SELECT name, reason, amount_paid, visit_date FROM patients", conn)
        if not report_df.empty:
            st.subheader("Report Content Preview")
            st.dataframe(report_df, width='stretch')
            if st.button("Generate & Download PDF"):
                fn = f"MediVista_Report_{datetime.now().strftime('%Y%m%d')}.pdf"
                doc = SimpleDocTemplate(fn, pagesize=A4)
                parts = [Paragraph("<b>MediVista Revenue Report</b>", ParagraphStyle('Title', fontSize=18, alignment=1)),
                         Spacer(1, 0.2 * inch),
                         Paragraph(f"Total Revenue: ₹{report_df['amount_paid'].sum():,.2f}", ParagraphStyle('Body', fontSize=12))]
                doc.build(parts)
                with open(fn, "rb") as f:
                    st.download_button("Download Now", f, file_name=fn)
        else: st.warning("No records found.")

    # -------- SETTINGS (CLEANER) -------- #
    elif page == "Settings":
        st.title("System Settings")
        if st.session_state.role == "Admin":
            st.subheader("Database Maintenance")
            st.warning("Warning: Clearing data will wipe all patient and appointment records.")
            if st.button("Clear All Data"):
                c = conn.cursor()
                c.execute("DELETE FROM patients")
                c.execute("DELETE FROM doctors")
                c.execute("DELETE FROM appointments")
                conn.commit()
                st.success("Database Reset Complete.")
                st.rerun()
        else:
            st.info("Settings are restricted to Admin users.")

    # Bottom Logout Section
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown('<div class="logout-footer">', unsafe_allow_html=True)
    st.markdown("---")
    if st.button("Logout Session"):
        st.session_state.logged_in = False
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    conn.close()
