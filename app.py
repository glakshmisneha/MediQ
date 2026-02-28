import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import bcrypt
import os
import re
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
    # Core User and Medical Tables
    c.execute("CREATE TABLE IF NOT EXISTS users(email TEXT PRIMARY KEY, password BLOB, role TEXT)")
    # Added nurse_assigned and shift_timing columns
    c.execute("""CREATE TABLE IF NOT EXISTS doctors(
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        name TEXT, specialty TEXT, total_slots INTEGER, 
        booked_slots INTEGER DEFAULT 0, 
        nurse_assigned TEXT, shift_timing TEXT)""")
    c.execute("CREATE TABLE IF NOT EXISTS patients(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, age INTEGER, blood_group TEXT, reason TEXT, amount_paid REAL, visit_date TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS appointments(id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER, doctor_id INTEGER, appointment_date TEXT)")
    
    # Updated: Added doctor_name and is_complaint
    c.execute("CREATE TABLE IF NOT EXISTS queries(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT, doctor_name TEXT, query TEXT, is_complaint INTEGER DEFAULT 0, status TEXT DEFAULT 'Open')")
    
    c.execute("CREATE TABLE IF NOT EXISTS rooms(room_no TEXT PRIMARY KEY, type TEXT, status TEXT DEFAULT 'Available')")
    
    # Initialize Demo Doctor for Staff/Receptionist visibility
    c.execute("SELECT COUNT(*) FROM doctors")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO doctors (name, specialty, total_slots, nurse_assigned, shift_timing) VALUES ('Dr. Sneha', 'Cardiology', 10, 'Nurse Joy', '08:00 - 16:00')")
    
    # Initialize Rooms if empty
    c.execute("SELECT COUNT(*) FROM rooms")
    if c.fetchone()[0] == 0:
        rooms_data = [('101', 'General', 'Available'), ('201', 'ICU', 'Available'), ('301', 'Private', 'Occupied')]
        c.executemany("INSERT INTO rooms VALUES (?,?,?)", rooms_data)
        
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
    # Rules: 8+ chars, 1 Capital, 1 Special, 1 Number
    if len(password) < 8: return False, "Password must be at least 8 characters."
    if not any(c.isupper() for c in password): return False, "Missing an uppercase letter."
    if not any(c.isdigit() for c in password): return False, "Missing a number."
    if not any(c in "!@#$%^&*()-_=+[]{}|;:',.<>?/" for c in password): return False, "Missing a special character."
    return True, ""

# ================= UI STYLING ================= #
st.markdown("""
    <style>
    div[data-testid="stMetricValue"] { color: #ffffff; font-size: 40px; font-weight: bold; }
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
        role = st.selectbox("Role", ["Admin", "Receptionist", "Hospital Staff", "Doctor", "Patient"])
        if st.button("Create Account"):
            is_strong, msg = is_strong_password(pass_in)
            if not is_valid_gmail(email_in): st.error("Email must be @gmail.com")
            elif not is_strong: st.error(msg)
            else:
                conn = sqlite3.connect(DB_NAME)
                try:
                    conn.execute("INSERT INTO users VALUES (?,?,?)", (email_in, sqlite3.Binary(hash_password(pass_in)), role))
                    conn.commit()
                    st.success("Account Created! You can now Login.")
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
    # Logout button in sidebar
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()

    conn = sqlite3.connect(DB_NAME)
    today = datetime.now().strftime("%Y-%m-%d")

    # ---------------- HOSPITAL STAFF ---------------- #
    if st.session_state.role == "Hospital Staff":
        st.title("👨‍⚕️ Staff Duty Board")
        
        # Display Allocated Nurse and Shift Timings
        st.subheader(f"Medical Staff Shifts ({today})")
        staff_df = pd.read_sql_query("SELECT name as Doctor, nurse_assigned as 'Allocated Nurse', shift_timing as 'Shift' FROM doctors", conn)
        st.table(staff_df)

        st.subheader("Today's Appointments List")
        # Appointments show specifically for today
        staff_appts = pd.read_sql_query(f"""
            SELECT p.name as Patient, d.name as Doctor, a.appointment_date 
            FROM appointments a 
            JOIN patients p ON a.patient_id = p.id 
            JOIN doctors d ON a.doctor_id = d.id 
            WHERE a.appointment_date = '{today}'""", conn)
        st.dataframe(staff_appts, width='stretch')

    # ---------------- RECEPTIONIST ---------------- #
    elif st.session_state.role == "Receptionist":
        st.title("📞 Reception Desk")
        
        t1, t2 = st.tabs(["Today's Booking List", "New Appointment"])
        
        with t1:
            st.subheader(f"Current Bookings for {today}")
            bookings = pd.read_sql_query(f"SELECT * FROM appointments WHERE appointment_date='{today}'", conn)
            st.dataframe(bookings, width='stretch')

        with t2:
            st.subheader("Book New Appointment")
            with st.form("rec_form"):
                p_list = pd.read_sql_query("SELECT id, name FROM patients", conn)
                d_list = pd.read_sql_query("SELECT id, name FROM doctors", conn)
                
                sel_p = st.selectbox("Select Patient", p_list['name'])
                sel_d = st.selectbox("Select Doctor", d_list['name'])
                if st.form_submit_button("Confirm Booking"):
                    pid = p_list[p_list['name']==sel_p]['id'].iloc[0]
                    did = d_list[d_list['name']==sel_d]['id'].iloc[0]
                    conn.execute("INSERT INTO appointments (patient_id, doctor_id, appointment_date) VALUES (?,?,?)", (int(pid), int(did), today))
                    conn.commit()
                    st.success("Appointment Successfully Booked!")

    # ---------------- DOCTOR ---------------- #
    elif st.session_state.role == "Doctor":
        st.title("🩺 Doctor's Consultation Dashboard")
        
        # Show specific patient queries and complaints about the doctor
        st.subheader("Patient Feedback & Concerns")
        feedback = pd.read_sql_query("SELECT name as Patient, query as Message, is_complaint FROM queries", conn)
        
        if not feedback.empty:
            c_view = feedback[feedback['is_complaint'] == 1]
            q_view = feedback[feedback['is_complaint'] == 0]
            
            st.error("⚠️ Formal Complaints")
            st.dataframe(c_view, width='stretch')
            st.info("❓ General Inquiries")
            st.dataframe(q_view, width='stretch')
        else:
            st.success("No negative feedback or pending queries found.")

    # ---------------- PATIENT ---------------- #
    elif st.session_state.role == "Patient":
        st.title("🏥 Patient Portal")
        
        with st.form("p_feedback"):
            st.subheader("Submit Query or Complaint")
            docs = pd.read_sql_query("SELECT name FROM doctors", conn)
            target_doc = st.selectbox("Select Doctor", docs['name'])
            msg = st.text_area("What is your query or complaint?")
            comp_flag = st.checkbox("Is this a formal complaint?")
            if st.form_submit_button("Submit"):
                conn.execute("INSERT INTO queries (name, email, doctor_name, query, is_complaint) VALUES (?,?,?,?,?)",
                             ("Patient", st.session_state.user_email, target_doc, msg, 1 if comp_flag else 0))
                conn.commit()
                st.success("Your message has been logged for the doctor's review.")

    # ---------------- ADMIN ---------------- #
    elif st.session_state.role == "Admin":
        st.sidebar.markdown("---")
        page = st.sidebar.radio("Navigation", ["Dashboard", "Doctors Allotment", "Room Management", "Reports"])
        
        if page == "Dashboard":
            st.title("Hospital Dashboard")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Patients", pd.read_sql_query("SELECT COUNT(*) FROM patients", conn).iloc[0,0])
            m2.metric("Total Doctors", pd.read_sql_query("SELECT COUNT(*) FROM doctors", conn).iloc[0,0])
            m3.metric("Rooms Avail.", pd.read_sql_query("SELECT COUNT(*) FROM rooms WHERE status='Available'", conn).iloc[0,0])
            m4.metric("Pending Queries", pd.read_sql_query("SELECT COUNT(*) FROM queries WHERE status='Open'", conn).iloc[0,0])
            
            st.divider()
            st.write("### Visits & Staff Workload")
            g1, g2 = st.columns(2)
            # Pie chart for staff roles
            fig = px.pie(pd.read_sql_query("SELECT role, COUNT(*) as count FROM users GROUP BY role", conn), names='role', values='count', hole=0.4)
            fig.update_layout(template="plotly_dark")
            g1.plotly_chart(fig, width='stretch')
            
            # Workload Chart
            doc_w = pd.read_sql_query("SELECT name, booked_slots FROM doctors", conn)
            fig2 = px.bar(doc_w, x='name', y='booked_slots', color_discrete_sequence=['#87CEFA'])
            fig2.update_layout(template="plotly_dark")
            g2.plotly_chart(fig2, width='stretch')

        elif page == "Doctors Allotment":
            st.title("Manage Doctors & Staff Assignments")
            with st.expander("Add New Doctor & Duty"):
                with st.form("add_doc_staff"):
                    dn = st.text_input("Doctor Name")
                    ds = st.text_input("Specialty")
                    n_assigned = st.text_input("Allocate Nurse")
                    shift = st.selectbox("Shift Timing", ["08:00 - 16:00", "16:00 - 00:00", "00:00 - 08:00"])
                    if st.form_submit_button("Save Details"):
                        conn.execute("INSERT INTO doctors (name, specialty, total_slots, nurse_assigned, shift_timing) VALUES (?,?,?,?,?)", 
                                     (dn, ds, 10, n_assigned, shift))
                        conn.commit()
                        st.rerun()
            st.dataframe(pd.read_sql_query("SELECT * FROM doctors", conn), width='stretch')

        elif page == "Room Management":
            st.title("🛌 Room & Bed Management")
            rooms = pd.read_sql_query("SELECT * FROM rooms", conn)
            st.dataframe(rooms, width='stretch')
            with st.form("edit_room"):
                r_no = st.selectbox("Select Room", rooms['room_no'])
                r_st = st.selectbox("Update Status", ["Available", "Occupied", "Cleaning"])
                if st.form_submit_button("Update Room"):
                    conn.execute("UPDATE rooms SET status=? WHERE room_no=?", (r_st, r_no))
                    conn.commit()
                    st.rerun()

        elif page == "Reports":
            st.title("📊 Financial & Activity Reports")
            report_df = pd.read_sql_query("SELECT * FROM patients", conn)
            st.dataframe(report_df, width='stretch')
            if st.button("Generate & Download PDF"):
                fn = f"MediVista_Report_{datetime.now().strftime('%Y%m%d')}.pdf"
                doc = SimpleDocTemplate(fn, pagesize=A4)
                parts = [Paragraph("<b>MediVista Hospital Revenue Summary</b>", ParagraphStyle('Title', fontSize=22, alignment=1))]
                doc.build(parts)
                with open(fn, "rb") as f:
                    st.download_button("Download Now", f, file_name=fn)

    conn.close()
