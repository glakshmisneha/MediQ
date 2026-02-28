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
    try:
        if isinstance(hashed, str):
            hashed = hashed.encode('utf-8')
        elif isinstance(hashed, memoryview):
            hashed = hashed.tobytes()
        return bcrypt.checkpw(password.encode('utf-8'), hashed)
    except Exception:
        return False

# ================= UI STYLING ================= #

st.markdown("""
    <style>
    /* Main background */
    .stApp {
        background-color: #0e1117;
    }
    
    /* Metric Cards Styling */
    div[data-testid="stMetricValue"] {
        color: #00acee;
        font-size: 42px;
        font-weight: 800;
    }
    
    /* Button Styling */
    .stButton>button {
        background: linear-gradient(45deg, #00acee, #0072ff);
        color: white;
        border-radius: 12px;
        border: none;
        padding: 10px 24px;
        font-weight: 600;
        transition: 0.3s;
        width: 100%;
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 15px rgba(0, 172, 238, 0.4);
    }

    /* Red Logout Button */
    .logout-btn button {
        background: linear-gradient(45deg, #ff4b4b, #ff2b2b) !important;
    }

    /* Sidebar Styling */
    [data-testid="stSidebar"] {
        background-color: #161b22;
        border-right: 1px solid #30363d;
    }

    /* Form and Dataframe container */
    .stForm, .stDataFrame {
        border: 1px solid #30363d !important;
        border-radius: 15px !important;
        background-color: #161b22;
    }
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
                conn.execute("INSERT INTO users (email, password, role) VALUES (?,?,?)", 
                             (email, sqlite3.Binary(hashed), role))
                conn.commit()
                st.success("Account Created! You can now switch to Login.")
            except: 
                st.error("User already exists")
            finally:
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
                st.error("Invalid Credentials. If this is an old account, please re-register.")

# ================= MAIN APP ================= #
else:
    st.sidebar.title("MediVista Admin")
    st.sidebar.info(f"Access Level: **{st.session_state.role}**")
    page = st.sidebar.radio("Navigation", ["Dashboard", "Doctors Allotment", "Patient Details", "Appointments", "Reports", "Settings"])

    st.sidebar.markdown("---")
    if st.sidebar.button("Logout", key="sidebar_logout"):
        st.session_state.logged_in = False
        st.rerun()

    conn = connect_db()

    # -------- DASHBOARD -------- #
    if page == "Dashboard":
        st.title("📊 Hospital Dashboard")
        patients = pd.read_sql_query("SELECT * FROM patients", conn)
        apps = pd.read_sql_query("SELECT * FROM appointments", conn)
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Visits", len(patients))
        col2.metric("Total Revenue", f"₹ {patients['amount_paid'].sum():,.0f}" if not patients.empty else "₹ 0")
        col3.metric("Appointments", len(apps))

        st.divider()

        if not patients.empty:
            st.subheader("Visits by Reason")
            reasons = patients['reason'].value_counts().reset_index()
            reasons.columns = ['reason', 'count']
            fig_r = px.bar(reasons, x='reason', y='count', color_discrete_sequence=['#00acee'])
            fig_r.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_r, width='stretch')

    # -------- PATIENTS -------- #
    elif page == "Patient Details":
        st.title("👥 Patient Records")
        with st.form("p_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            name = c1.text_input("Full Name")
            age = c2.number_input("Age", 0, 120)
            blood = c1.selectbox("Blood Group", ["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"])
            reason = c2.text_input("Reason for Visit")
            pay = c1.number_input("Payment Amount (₹)", 0.0)
            if st.form_submit_button("Register Patient"):
                conn.execute("INSERT INTO patients (name, age, blood_group, reason, amount_paid, visit_date) VALUES (?,?,?,?,?,?)",
                            (name, age, blood, reason, pay, datetime.now().strftime("%Y-%m-%d")))
                conn.commit()
                st.rerun()
        
        st.dataframe(pd.read_sql_query("SELECT * FROM patients", conn), width='stretch')

    # -------- APPOINTMENTS -------- #
    elif page == "Appointments":
        st.title("📅 Appointment Booking")
        p_df = pd.read_sql_query("SELECT id, name FROM patients", conn)
        d_df = pd.read_sql_query("SELECT id, name, total_slots, booked_slots FROM doctors", conn)
        
        if not p_df.empty and not d_df.empty:
            c1, c2 = st.columns(2)
            p_sel = c1.selectbox("Select Patient", p_df["name"])
            d_sel = c2.selectbox("Select Doctor", d_df["name"])
            if st.button("Confirm Booking"):
                doc = d_df[d_df["name"] == d_sel].iloc[0]
                if doc["booked_slots"] < doc["total_slots"]:
                    pid = p_df[p_df["name"] == p_sel]["id"].iloc[0]
                    conn.execute("INSERT INTO appointments (patient_id, doctor_id, appointment_date) VALUES (?,?,?)",
                                (int(pid), int(doc["id"]), datetime.now().strftime("%Y-%m-%d")))
                    conn.execute("UPDATE doctors SET booked_slots = booked_slots + 1 WHERE id=?", (int(doc["id"]),))
                    conn.commit()
                    st.success("Appointment Scheduled!")
                    st.rerun()

        st.subheader("Appointment History")
        history_df = pd.read_sql_query("SELECT * FROM appointments", conn)
        if not history_df.empty:
            history_df['patient_id'] = history_df['patient_id'].astype(str)
            history_df['doctor_id'] = history_df['doctor_id'].astype(str)
            st.dataframe(history_df, width='stretch')

    # -------- REPORTS -------- #
    elif page == "Reports":
        st.title("📄 Financial Reports")
        report_df = pd.read_sql_query("SELECT name, reason, amount_paid, visit_date FROM patients", conn)
        if not report_df.empty:
            st.subheader("Report Preview")
            st.dataframe(report_df, width='stretch')
            if st.button("Export as PDF"):
                fn = f"MediVista_Report_{datetime.now().strftime('%Y%m%d')}.pdf"
                doc = SimpleDocTemplate(fn, pagesize=A4)
                parts = [Paragraph("<b>MediVista Revenue Report</b>", ParagraphStyle('Title', fontSize=18, alignment=1)),
                         Spacer(1, 0.2 * inch),
                         Paragraph(f"Total Revenue: ₹{report_df['amount_paid'].sum():,.2f}", ParagraphStyle('Body', fontSize=12))]
                doc.build(parts)
                with open(fn, "rb") as f:
                    st.download_button("Download Document", f, file_name=fn)
        else: st.warning("No data found to generate report.")

    # -------- SETTINGS -------- #
    elif page == "Settings":
        st.title("⚙️ System Settings")
        if st.session_state.role == "Admin":
            st.subheader("Database Cleanup")
            st.error("Clearing data will remove all patients, doctors, and appointment history.")
            if st.button("Clear All Records"):
                c = conn.cursor()
                c.execute("DELETE FROM patients")
                c.execute("DELETE FROM doctors")
                c.execute("DELETE FROM appointments")
                conn.commit()
                st.success("System reset successful.")
                st.rerun()
        else:
            st.info("Settings are locked for your user role.")

    # BOTTOM LOGOUT
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown('<div class="logout-btn">', unsafe_allow_html=True)
    if st.button("Exit System", key="main_logout"):
        st.session_state.logged_in = False
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    conn.close()
