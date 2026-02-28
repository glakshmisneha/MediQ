import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import bcrypt
import os
import re
from datetime import datetime, time
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
    c.execute("""CREATE TABLE IF NOT EXISTS doctors(
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        name TEXT, specialty TEXT, total_slots INTEGER, 
        booked_slots INTEGER DEFAULT 0, 
        nurse_assigned TEXT, shift_timing TEXT)""")
    c.execute("CREATE TABLE IF NOT EXISTS patients(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, age INTEGER, blood_group TEXT, reason TEXT, amount_paid REAL, visit_date TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS appointments(id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER, doctor_id INTEGER, appointment_date TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS queries(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT, doctor_name TEXT, query TEXT, is_complaint INTEGER DEFAULT 0, status TEXT DEFAULT 'Open')")
    c.execute("CREATE TABLE IF NOT EXISTS rooms(room_no TEXT PRIMARY KEY, type TEXT, status TEXT DEFAULT 'Available')")
    
    # Schema Migration for updated doctor and query fields
    c.execute("PRAGMA table_info(doctors)")
    existing_columns = [column[1] for column in c.fetchall()]
    if 'nurse_assigned' not in existing_columns:
        c.execute("ALTER TABLE doctors ADD COLUMN nurse_assigned TEXT DEFAULT 'Not Assigned'")
    if 'shift_timing' not in existing_columns:
        c.execute("ALTER TABLE doctors ADD COLUMN shift_timing TEXT DEFAULT '08:00 - 16:00'")
        
    conn.commit()
    conn.close()

init_db()

# ================= SECURITY & VALIDATION ================= #
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
    if len(password) < 8: return False, "Password must be at least 8 characters."
    if not any(c.isupper() for c in password): return False, "Missing an uppercase letter."
    if not any(c.isdigit() for c in password): return False, "Missing a number."
    if not any(c in "!@#$%^&*()-_=+[]{}|;:',.<>?/" for c in password): return False, "Missing a special character."
    return True, ""

# ================= UI STYLING ================= #
st.markdown("""
    <style>
    div[data-testid="stMetricValue"] { color: #ffffff; font-size: 38px; font-weight: bold; }
    .stButton>button { background-color: #00acee; color: white; border-radius: 20px; border: none; font-weight: bold; width: 100%; }
    .stSidebar { background-color: #0e1117; }
    [data-testid="stForm"] { border: 1px solid #30363d !important; border-radius: 15px; background-color: #161b22; }
    </style>
    """, unsafe_allow_html=True)

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# ================= AUTHENTICATION FLOW ================= #
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
                    st.success("Account Created Successfully!")
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

# ================= MAIN APPLICATION ================= #
else:
    st.sidebar.title(f"Role: {st.session_state.role}")
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()

    conn = sqlite3.connect(DB_NAME)
    today_str = datetime.now().strftime("%Y-%m-%d")

    # ---------------- PATIENT INTERFACE ---------------- #
    if st.session_state.role == "Patient":
        st.title("🏥 Patient Portal")
        st.subheader("Connect with your Healthcare Team")
        
        with st.form("patient_interaction_form"):
            st.write("### Submit a Query or Complaint")
            # Get list of doctors for the dropdown
            doctors_list = pd.read_sql_query("SELECT name FROM doctors", conn)
            
            if not doctors_list.empty:
                target_doctor = st.selectbox("Select Doctor", doctors_list['name'])
                message = st.text_area("Detail your concern or question")
                is_formal_complaint = st.checkbox("Check if this is a formal complaint")
                
                if st.form_submit_button("Send to Hospital"):
                    conn.execute("""INSERT INTO queries (name, email, doctor_name, query, is_complaint) 
                                 VALUES (?,?,?,?,?)""", 
                                 ("Patient", st.session_state.user_email, target_doctor, message, 1 if is_formal_complaint else 0))
                    conn.commit()
                    st.success("Your message has been successfully logged for review.")
            else:
                st.warning("No doctors are currently available in the system.")

    # ---------------- ADMIN INTERFACE ---------------- #
    elif st.session_state.role == "Admin":
        page = st.sidebar.radio("Navigation", ["Dashboard", "Doctors Allotment", "Room Management", "Reports"])
        
        if page == "Dashboard":
            st.title("Hospital Dashboard")
            patients = pd.read_sql_query("SELECT * FROM patients", conn)
            apps = pd.read_sql_query("SELECT * FROM appointments", conn)
            
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Visits", len(patients))
            m2.metric("Total Revenue", f"₹ {patients['amount_paid'].sum() if not patients.empty else 0.0}")
            daily_rev = patients[patients['visit_date'] == today_str]['amount_paid'].sum() if not patients.empty else 0.0
            m3.metric("Today's Revenue", f"₹ {daily_rev}")
            m4.metric("Total Appointments", len(apps))

            st.divider()
            
            if not patients.empty:
                g1, g2, g3 = st.columns(3)
                with g1:
                    st.write("### Visits by Reason")
                    fig1 = px.bar(patients['reason'].value_counts().reset_index(), x='reason', y='count', color_discrete_sequence=['#87CEFA'])
                    fig1.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig1, width='stretch')
                with g2:
                    st.write("### Revenue Trend")
                    daily_data = patients.groupby('visit_date')['amount_paid'].sum().reset_index()
                    fig2 = px.line(daily_data, x='visit_date', y='amount_paid', markers=True, color_discrete_sequence=['#00acee'])
                    fig2.update_layout(template="plotly_dark")
                    st.plotly_chart(fig2, width='stretch')
                with g3:
                    st.write("### Doctor Workload")
                    doc_w = pd.read_sql_query("SELECT name, booked_slots FROM doctors", conn)
                    if not doc_w.empty:
                        fig3 = px.bar(doc_w, x='name', y='booked_slots', color_discrete_sequence=['#87CEFA'])
                        fig3.update_layout(template="plotly_dark")
                        st.plotly_chart(fig3, width='stretch')

        elif page == "Doctors Allotment":
            st.title("Manage Staff & Shifts")
            with st.expander("➕ Add Doctor & Allocate Nurse/Shift"):
                with st.form("admin_doc_form"):
                    c1, c2 = st.columns(2)
                    dn, ds = c1.text_input("Doctor Name"), c2.selectbox("Specialty", ["General", "ICU", "Pediatrics"])
                    nurse, slots = c1.text_input("Allocate Nurse"), c2.number_input("Max Slots", 1, 50, 10)
                    t1, t2 = st.columns(2)
                    start_t, end_t = t1.time_input("Start", time(8, 0)), t2.time_input("End", time(16, 0))
                    if st.form_submit_button("Save Details"):
                        shift_str = f"{start_t.strftime('%H:%M')} - {end_t.strftime('%H:%M')}"
                        conn.execute("INSERT INTO doctors (name, specialty, total_slots, nurse_assigned, shift_timing) VALUES (?,?,?,?,?)", 
                                     (dn, ds, slots, nurse, shift_str))
                        conn.commit()
                        st.rerun()
            st.dataframe(pd.read_sql_query("SELECT * FROM doctors", conn), width='stretch')

        elif page == "Room Management":
            st.title("🛌 Room & Bed Management")
            with st.expander("➕ Add New Hospital Room"):
                with st.form("add_room_form"):
                    r_no = st.text_input("Room Number")
                    r_type = st.selectbox("Room Type", ["General", "ICU", "Private"])
                    if st.form_submit_button("Register Room"):
                        conn.execute("INSERT INTO rooms (room_no, type) VALUES (?,?)", (r_no, r_type))
                        conn.commit()
                        st.rerun()
            st.dataframe(pd.read_sql_query("SELECT * FROM rooms", conn), width='stretch')

        elif page == "Reports":
            st.title("📊 Financial Reports")
            report_df = pd.read_sql_query("SELECT name, reason, amount_paid, visit_date FROM patients", conn)
            st.dataframe(report_df, width='stretch')
            if st.button("Generate & Download PDF"):
                fn = f"MediVista_Report_{datetime.now().strftime('%Y%m%d')}.pdf"
                doc = SimpleDocTemplate(fn, pagesize=A4)
                parts = [Paragraph("<b>Hospital Revenue Report</b>", ParagraphStyle('Title', fontSize=22, alignment=1))]
                doc.build(parts)
                with open(fn, "rb") as f:
                    st.download_button("Download Now", f, file_name=fn)

    # ---------------- HOSPITAL STAFF ---------------- #
    elif st.session_state.role == "Hospital Staff":
        st.title("👨‍⚕️ Staff Duty Board")
        st.subheader(f"Shifts & Assignments ({today_str})")
        staff_df = pd.read_sql_query("SELECT name as Doctor, nurse_assigned as 'Nurse', shift_timing as 'Shift' FROM doctors", conn)
        st.table(staff_df)
        st.subheader("Today's Appointments")
        staff_appts = pd.read_sql_query(f"""
            SELECT p.name as Patient, d.name as Doctor, a.appointment_date 
            FROM appointments a 
            JOIN patients p ON a.patient_id = p.id 
            JOIN doctors d ON a.doctor_id = d.id 
            WHERE a.appointment_date = '{today_str}'""", conn)
        st.dataframe(staff_appts, width='stretch')

    # ---------------- RECEPTIONIST ---------------- #
    elif st.session_state.role == "Receptionist":
        st.title("📞 Reception Desk")
        t1, t2 = st.tabs(["Today's Booking List", "New Appointment"])
        with t1:
            st.dataframe(pd.read_sql_query(f"SELECT * FROM appointments WHERE appointment_date='{today_str}'", conn), width='stretch')
        with t2:
            with st.form("rec_book"):
                p_list, d_list = pd.read_sql_query("SELECT id, name FROM patients", conn), pd.read_sql_query("SELECT id, name FROM doctors", conn)
                if not p_list.empty and not d_list.empty:
                    sel_p, sel_d = st.selectbox("Patient", p_list['name']), st.selectbox("Doctor", d_list['name'])
                    if st.form_submit_button("Book Now"):
                        pid, did = p_list[p_list['name']==sel_p]['id'].iloc[0], d_list[d_list['name']==sel_d]['id'].iloc[0]
                        conn.execute("INSERT INTO appointments (patient_id, doctor_id, appointment_date) VALUES (?,?,?)", (int(pid), int(did), today_str))
                        conn.commit()
                        st.success("Confirmed!")

    # ---------------- DOCTOR ---------------- #
    elif st.session_state.role == "Doctor":
        st.title("🩺 Doctor Dashboard")
        feedback = pd.read_sql_query("SELECT name as Patient, query as Message, is_complaint FROM queries", conn)
        if not feedback.empty:
            st.error("🚨 Formal Complaints")
            st.dataframe(feedback[feedback['is_complaint'] == 1], width='stretch')
            st.info("❓ Patient Inquiries")
            st.dataframe(feedback[feedback['is_complaint'] == 0], width='stretch')
        else: st.write("No patient feedback found.")

    conn.close()
