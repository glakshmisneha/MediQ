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
    
    # NEW: Patient Queries Table
    c.execute("CREATE TABLE IF NOT EXISTS queries(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT, query TEXT, status TEXT DEFAULT 'Open')")
    
    # NEW: Rooms Table
    c.execute("CREATE TABLE IF NOT EXISTS rooms(room_no TEXT PRIMARY KEY, type TEXT, status TEXT DEFAULT 'Available')")
    
    # Initialize some rooms if the table is empty
    c.execute("SELECT COUNT(*) FROM rooms")
    if c.fetchone()[0] == 0:
        rooms = [('101', 'General', 'Available'), ('102', 'General', 'Available'), 
                 ('201', 'ICU', 'Available'), ('301', 'Private', 'Occupied')]
        c.executemany("INSERT INTO rooms VALUES (?,?,?)", rooms)
        
    conn.commit()
    conn.close()

init_db()

# ================= SECURITY HELPERS ================= #
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
    </style>
    """, unsafe_allow_html=True)

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# ================= AUTHENTICATION FLOW ================= #
if not st.session_state.logged_in:
    st.title("🏥 MediVista Login")
    # (Login logic remains the same...)
    if st.button("Enter System (Debug)"): st.session_state.logged_in = True; st.rerun()

# ================= MAIN APPLICATION ================= #
else:
    # Sidebar Navigation
    st.sidebar.title("MediVista Admin")
    page = st.sidebar.radio("Navigation", ["Dashboard", "Doctors Allotment", "Patient Details", "Appointments", "Patient Queries", "Reports"])

    # FEATURE: Logout at the very end of the sidebar
    st.sidebar.container() # Spacer
    st.sidebar.write("") 
    st.sidebar.write("")
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
        
        # FEATURE: Room Availability Logic
        rooms_df = pd.read_sql_query("SELECT * FROM rooms", conn)
        avail_rooms = len(rooms_df[rooms_df['status'] == 'Available'])
        
        # TOP ROW: 4 Metrics
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Visits", len(patients))
        m2.metric("Total Revenue", f"₹ {patients['amount_paid'].sum() if not patients.empty else 0.0}")
        m3.metric("Total Appointments", len(apps))
        m4.metric("Available Rooms", avail_rooms) # NEW METRIC

        st.divider()

        # GRAPH ROW: Side-by-Side
        g1, g2, g3 = st.columns(3)
        with g1:
            st.write("### Visits by Reason")
            if not patients.empty:
                fig1 = px.bar(patients['reason'].value_counts().reset_index(), x='reason', y='count', color_discrete_sequence=['#87CEFA'])
                fig1.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig1, width='stretch')
        
        with g2:
            st.write("### Room Distribution")
            fig2 = px.pie(rooms_df, names='status', color='status', color_discrete_map={'Available':'#00acee', 'Occupied':'#ff4b4b'})
            fig2.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig2, width='stretch')

        with g3:
            st.write("### Doctor Workload")
            doc_data = pd.read_sql_query("SELECT name, booked_slots FROM doctors", conn)
            if not doc_data.empty:
                fig3 = px.bar(doc_data, x='name', y='booked_slots', color_discrete_sequence=['#87CEFA'])
                fig3.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig3, width='stretch')

    # -------- PATIENT QUERIES -------- #
    elif page == "Patient Queries":
        st.title("📩 Patient Queries")
        with st.expander("➕ Log New Query"):
            with st.form("query_form"):
                q_name = st.text_input("Patient Name")
                q_email = st.text_input("Email")
                q_text = st.text_area("Query Details")
                if st.form_submit_button("Submit Query"):
                    conn.execute("INSERT INTO queries (name, email, query) VALUES (?,?,?)", (q_name, q_email, q_text))
                    conn.commit()
                    st.success("Query Logged")
                    st.rerun()
        
        queries_df = pd.read_sql_query("SELECT * FROM queries", conn)
        st.dataframe(queries_df, width='stretch')

    # (Other pages: Doctors Allotment, Patient Details, Appointments, Reports remain the same...)
    
    conn.close()
