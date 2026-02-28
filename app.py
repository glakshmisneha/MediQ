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
    div[data-testid="stMetricValue"] { color: #ffffff; font-size: 40px; font-weight: bold; }
    div[data-testid="stMetricLabel"] { color: #888888; font-size: 14px; }
    .stButton>button { background-color: #00acee; color: white; border-radius: 20px; border: none; font-weight: bold; }
    .stSidebar { background-color: #0e1117; }
    [data-testid="stForm"] { border: 1px solid #30363d !important; border-radius: 15px; background-color: #161b22; }
    .logout-container { padding: 40px 0px; text-align: center; }
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
    page = st.sidebar.radio("Navigation", ["Dashboard", "Doctors Allotment", "Patient Details", "Appointments", "Reports"])

    st.sidebar.markdown("---")
    if st.sidebar.button("Logout", key="sidebar_logout"):
        st.session_state.logged_in = False
        st.rerun()

    conn = sqlite3.connect(DB_NAME)

    # -------- DASHBOARD -------- #
    if page == "Dashboard":
        st.title("Hospital Dashboard")
        patients = pd.read_sql_query("SELECT * FROM patients", conn)
        apps = pd.read_sql_query("SELECT * FROM appointments", conn)
        
        # TOP ROW: 4 Metrics
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Visits", len(patients))
        m2.metric("Total Revenue", f"₹ {patients['amount_paid'].sum() if not patients.empty else 0.0}")
        m3.metric("Total Appointments", len(apps))
        
        today_str = datetime.now().strftime("%Y-%m-%d")
        daily_rev = patients[patients['visit_date'] == today_str]['amount_paid'].sum() if not patients.empty else 0.0
        m4.metric("Today's Revenue", f"₹ {daily_rev}")

        st.divider()

        # GRAPH ROW: All 3 graphs next to each other
        if not patients.empty:
            g1, g2, g3 = st.columns(3)

            with g1:
                st.write("### Visits by Reason")
                reasons = patients['reason'].value_counts().reset_index()
                reasons.columns = ['reason', 'count']
                fig1 = px.bar(reasons, x='reason', y='count', color_discrete_sequence=['#87CEFA'])
                fig1.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig1, width='stretch')

            with g2:
                st.write("### Revenue Trend")
                daily_data = patients.groupby('visit_date')['amount_paid'].sum().reset_index()
                fig2 = px.line(daily_data, x='visit_date', y='amount_paid', markers=True, color_discrete_sequence=['#00acee'])
                fig2.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig2, width='stretch')

            with g3:
                st.write("### Doctor Workload")
                doc_data = pd.read_sql_query("SELECT name, booked_slots FROM doctors", conn)
                if not doc_data.empty:
                    fig3 = px.bar(doc_data, x='name', y='booked_slots', color_discrete_sequence=['#87CEFA'])
                    fig3.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig3, width='stretch')

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
                parts = [Paragraph("<b>MediVista Hospital Revenue Report</b>", ParagraphStyle('Title', fontSize=22, alignment=1, spaceAfter=20)),
                         Paragraph(f"<b>Date Generated:</b> {datetime.now().strftime('%Y-%m-%d %H:%M')}", ParagraphStyle('Body', fontSize=12))]
                doc_pdf.build(parts)
                with open(fn, "rb") as f:
                    st.download_button("Download PDF", f, file_name=fn)

    # -------- FINAL LOGOUT SECTION -------- #
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown("---")
    st.markdown('<div class="logout-container">', unsafe_allow_html=True)
    st.write("### Exit System")
    if st.button("Final Logout", key="bottom_logout"):
        st.session_state.logged_in = False
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    conn.close()
