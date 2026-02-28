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

# 1. Page Configuration (Must be the very first Streamlit command)
st.set_page_config(page_title="MediVista Admin", layout="wide")

DB_NAME = "mediq.db"

# ================= DATABASE INITIALIZATION ================= #
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Users, Doctors, Patients, Appointments
    c.execute("CREATE TABLE IF NOT EXISTS users(email TEXT PRIMARY KEY, password BLOB, role TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS doctors(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, specialty TEXT, total_slots INTEGER, booked_slots INTEGER DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS patients(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, age INTEGER, blood_group TEXT, reason TEXT, amount_paid REAL, visit_date TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS appointments(id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER, doctor_id INTEGER, appointment_date TEXT)")
    
    # Patient Queries Table
    c.execute("CREATE TABLE IF NOT EXISTS queries(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT, query TEXT, status TEXT DEFAULT 'Open')")
    
    # Rooms Table
    c.execute("CREATE TABLE IF NOT EXISTS rooms(room_no TEXT PRIMARY KEY, type TEXT, status TEXT DEFAULT 'Available')")
    
    # Initialize rooms if empty
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

# ================= UI CUSTOM STYLING ================= #
st.markdown("""
    <style>
    div[data-testid="stMetricValue"] { color: #ffffff; font-size: 40px; font-weight: bold; }
    div[data-testid="stMetricLabel"] { color: #888888; font-size: 14px; }
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
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if mode == "Register":
        role = st.selectbox("Role", ["Patient", "Admin", "Receptionist", "Hospital Staff"])
        if st.button("Create Account"):
            hashed = hash_password(password)
            conn = sqlite3.connect(DB_NAME)
            try:
                conn.execute("INSERT INTO users (email, password, role) VALUES (?,?,?)", (email, sqlite3.Binary(hashed), role))
                conn.commit()
                st.success("Account Created! You can now Login.")
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
                st.session_state.user_email = email
                st.rerun()
            else: st.error("Invalid Credentials.")

# ================= MAIN APPLICATION ================= #
else:
    # ---------------- PATIENT INTERFACE ---------------- #
    if st.session_state.role == "Patient":
        st.title("Welcome to Patient Portal")
        st.sidebar.title("MediVista")
        if st.sidebar.button("Logout"):
            st.session_state.logged_in = False
            st.rerun()

        st.subheader("Submit a Query to Hospital Admin")
        with st.form("patient_query_form"):
            p_name = st.text_input("Your Name")
            p_query = st.text_area("How can we help you today?")
            if st.form_submit_button("Submit Query"):
                conn = sqlite3.connect(DB_NAME)
                conn.execute("INSERT INTO queries (name, email, query) VALUES (?,?,?)", 
                             (p_name, st.session_state.user_email, p_query))
                conn.commit()
                conn.close()
                st.success("Your query has been sent to the Admin team.")

    # ---------------- ADMIN / STAFF INTERFACE ---------------- #
    else:
        st.sidebar.title("MediVista Admin")
        page = st.sidebar.radio("Navigation", ["Dashboard", "Doctors Allotment", "Patient Details", "Appointments", "Patient Queries", "Room Management", "Reports"])

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
            rooms_df = pd.read_sql_query("SELECT * FROM rooms", conn)
            open_queries = pd.read_sql_query("SELECT COUNT(*) FROM queries WHERE status='Open'", conn).iloc[0,0]
            avail_rooms = len(rooms_df[rooms_df['status'] == 'Available'])
            
            # TOP ROW: 4 Metrics
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Visits", len(patients))
            m2.metric("Total Revenue", f"₹ {patients['amount_paid'].sum() if not patients.empty else 0.0}")
            m3.metric("Available Rooms", avail_rooms)
            m4.metric("Pending Queries", open_queries)

            st.divider()
            
            # GRAPH ROW: Side-by-Side graphs
            g1, g2, g3 = st.columns(3)
            with g1:
                st.write("### Visits by Reason")
                if not patients.empty:
                    fig1 = px.bar(patients['reason'].value_counts().reset_index(), x='reason', y='count', color_discrete_sequence=['#87CEFA'])
                    fig1.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig1, width='stretch')
            with g2:
                st.write("### Revenue Trend")
                if not patients.empty:
                    daily_data = patients.groupby('visit_date')['amount_paid'].sum().reset_index()
                    fig2 = px.line(daily_data, x='visit_date', y='amount_paid', markers=True, color_discrete_sequence=['#00acee'])
                    fig2.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig2, width='stretch')
            with g3:
                st.write("### Room Distribution")
                fig3 = px.pie(rooms_df, names='status', hole=0.4, color_discrete_map={'Available':'#00acee', 'Occupied':'#ff4b4b'})
                fig3.update_layout(template="plotly_dark")
                st.plotly_chart(fig3, width='stretch')

        # -------- ROOM MANAGEMENT -------- #
        elif page == "Room Management":
            st.title("🛌 Room Management & Availability")
            rooms_df = pd.read_sql_query("SELECT * FROM rooms", conn)
            st.dataframe(rooms_df, width='stretch')
            
            st.divider()
            st.subheader("Edit Room Status")
            with st.form("edit_room_form"):
                room_to_edit = st.selectbox("Select Room Number", rooms_df['room_no'])
                new_status = st.selectbox("New Status", ["Available", "Occupied", "Cleaning", "Maintenance"])
                if st.form_submit_button("Update Room Status"):
                    conn.execute("UPDATE rooms SET status = ? WHERE room_no = ?", (new_status, room_to_edit))
                    conn.commit()
                    st.success(f"Room {room_to_edit} updated!")
                    st.rerun()

        # -------- PATIENT QUERIES -------- #
        elif page == "Patient Queries":
            st.title("📩 Manage Patient Queries")
            queries_df = pd.read_sql_query("SELECT * FROM queries WHERE status='Open'", conn)
            
            if not queries_df.empty:
                st.dataframe(queries_df, width='stretch')
                q_id = st.selectbox("Select Query ID to Clear", queries_df['id'])
                if st.button("Mark as Cleared"):
                    conn.execute("UPDATE queries SET status='Cleared' WHERE id=?", (int(q_id),))
                    conn.commit()
                    st.success(f"Query {q_id} cleared.")
                    st.rerun()
            else:
                st.success("All queries are currently cleared.")

        # -------- DOCTORS ALLOTMENT -------- #
        elif page == "Doctors Allotment":
            st.title("Doctors Allotment")
            specialties = ["Cardiology", "Dermatology", "Neurology", "Pediatrics", "Orthopedics", "General Medicine"]
            with st.expander("➕ Add Doctor Details"):
                with st.form("add_doc"):
                    name = st.text_input("Name")
                    spec = st.selectbox("Specialty", specialties)
                    slots = st.number_input("Daily Slots", 1, 50)
                    if st.form_submit_button("Save"):
                        conn.execute("INSERT INTO doctors (name, specialty, total_slots) VALUES (?,?,?)", (name, spec, slots))
                        conn.commit()
                        st.rerun()
            st.dataframe(pd.read_sql_query("SELECT * FROM doctors", conn), width='stretch')

        # -------- PATIENT DETAILS -------- #
        elif page == "Patient Details":
            st.title("Patient Details")
            with st.expander("➕ Register New Patient"):
                with st.form("add_p"):
                    c1, c2 = st.columns(2)
                    name = c1.text_input("Name")
                    age = c2.number_input("Age", 0, 120)
                    blood = c1.selectbox("Blood Group", ["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"])
                    reason = c2.text_input("Reason")
                    pay = c1.number_input("Payment", 0.0)
                    if st.form_submit_button("Register"):
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
                        st.success("Booked!")
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
                st.warning("No records available.")

        conn.close()
