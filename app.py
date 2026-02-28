import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import bcrypt
import re
from datetime import datetime, time, timedelta
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch

# 1. Page Configuration (Must be first)
st.set_page_config(page_title="MediVista Admin", layout="wide")

DB_NAME = "mediq.db"

# ================= DATABASE INITIALIZATION & MIGRATIONS ================= #
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
    c.execute("""CREATE TABLE IF NOT EXISTS appointments(
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        patient_id INTEGER, doctor_id INTEGER, 
        appointment_date TEXT, appointment_time TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS queries(
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        name TEXT, email TEXT, doctor_name TEXT, 
        query TEXT, is_complaint INTEGER DEFAULT 0, status TEXT DEFAULT 'Open')""")
    c.execute("CREATE TABLE IF NOT EXISTS rooms(room_no TEXT PRIMARY KEY, type TEXT, status TEXT DEFAULT 'Available')")
    
    # --- AUTOMATIC SCHEMA MIGRATION ---
    c.execute("PRAGMA table_info(appointments)")
    if 'appointment_time' not in [col[1] for col in c.fetchall()]:
        c.execute("ALTER TABLE appointments ADD COLUMN appointment_time TEXT DEFAULT '00:00'")
    
    c.execute("PRAGMA table_info(doctors)")
    doc_cols = [col[1] for col in c.fetchall()]
    if 'nurse_assigned' not in doc_cols:
        c.execute("ALTER TABLE doctors ADD COLUMN nurse_assigned TEXT DEFAULT 'Not Assigned'")
    if 'shift_timing' not in doc_cols:
        c.execute("ALTER TABLE doctors ADD COLUMN shift_timing TEXT DEFAULT '08:00 - 16:00'")
        
    conn.commit()
    conn.close()

init_db()

# ================= HELPER LOGIC ================= #
def get_available_slots(doctor_id, shift_str, date_str):
    """Generates sequential 20-minute intervals."""
    try:
        start_str, end_str = shift_str.split(" - ")
        start_dt = datetime.strptime(start_str, "%H:%M")
        end_dt = datetime.strptime(end_str, "%H:%M")
    except: return []
    slots = []
    current = start_dt
    while current + timedelta(minutes=20) <= end_dt:
        slots.append(current.strftime("%H:%M"))
        current += timedelta(minutes=20)
    conn = sqlite3.connect(DB_NAME)
    booked = pd.read_sql_query("SELECT appointment_time FROM appointments WHERE doctor_id=? AND appointment_date=?", 
                               conn, params=(doctor_id, date_str))
    conn.close()
    return [s for s in slots if s not in booked['appointment_time'].tolist()]

# ================= UI STYLING ================= #
st.markdown("""
    <style>
    div[data-testid="stMetricValue"] { color: #ffffff; font-size: 38px; font-weight: bold; }
    .stButton>button { background-color: #00acee; color: white; border-radius: 20px; border: none; font-weight: bold; width: 100%; }
    .stSidebar { background-color: #0e1117; }
    .sidebar-logout { position: fixed; bottom: 20px; left: 20px; width: 220px; z-index: 999; }
    [data-testid="stForm"] { border: 1px solid #30363d !important; border-radius: 15px; background-color: #161b22; }
    </style>
    """, unsafe_allow_html=True)

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# ================= AUTHENTICATION ================= #
if not st.session_state.logged_in:
    st.title("🏥 MediVista Management Portal")
    mode = st.radio("Option", ["Login", "Register"], horizontal=True)
    e_in = st.text_input("Email (xxx@gmail.com)")
    p_in = st.text_input("Password", type="password")

    if mode == "Register":
        role = st.selectbox("Role", ["Admin", "Receptionist", "Hospital Staff", "Doctor", "Patient"])
        if st.button("Create Account"):
            if not bool(re.match(r"^[a-zA-Z0-9._%+-]+@gmail\.com$", e_in)): st.error("Email must be @gmail.com")
            elif len(p_in) < 8 or not any(c.isupper() for c in p_in): st.error("8+ chars & 1 Uppercase")
            else:
                conn = sqlite3.connect(DB_NAME)
                hashed = bcrypt.hashpw(p_in.encode(), bcrypt.gensalt())
                try:
                    conn.execute("INSERT INTO users VALUES (?,?,?)", (e_in, sqlite3.Binary(hashed), role))
                    conn.commit()
                    st.success("Registration Successful!")
                except: st.error("User already exists.")
                conn.close()

    if mode == "Login":
        if st.button("Login"):
            conn = sqlite3.connect(DB_NAME)
            res = conn.execute("SELECT password, role FROM users WHERE email=?", (e_in,)).fetchone()
            conn.close()
            if res and bcrypt.checkpw(p_in.encode(), res[0] if isinstance(res[0], bytes) else res[0].tobytes()):
                st.session_state.logged_in, st.session_state.role, st.session_state.user_email = True, res[1], e_in
                st.rerun()
            else: st.error("Invalid Credentials")

# ================= MAIN APPLICATION ================= #
else:
    with st.sidebar:
        st.title("MediVista")
        if st.session_state.role == "Admin":
            nav = st.radio("Navigation", ["Dashboard", "Doctors Allotment", "Patient Details", "Room Management", "Reports"])
        elif st.session_state.role == "Receptionist":
            nav = st.radio("Navigation", ["Reception Area"])
        elif st.session_state.role == "Hospital Staff":
            nav = st.radio("Navigation", ["Duty Board"])
        elif st.session_state.role == "Doctor":
            nav = st.radio("Navigation", ["Doctor Room"])
        else: nav = st.radio("Navigation", ["Patient Portal"])

        st.markdown('<div class="sidebar-logout">', unsafe_allow_html=True)
        if st.button("Logout"):
            st.session_state.logged_in = False
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    conn = sqlite3.connect(DB_NAME)
    today_str = datetime.now().strftime("%Y-%m-%d")

    # ---------------- ADMIN INTERFACE ---------------- #
    if st.session_state.role == "Admin":
        if nav == "Dashboard":
            st.title("Hospital Dashboard")
            p_df = pd.read_sql_query("SELECT * FROM patients", conn)
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Visits", len(p_df))
            m2.metric("Total Revenue", f"₹ {p_df['amount_paid'].sum() if not p_df.empty else 0.0}")
            m3.metric("Today's Revenue", f"₹ {p_df[p_df['visit_date'] == today_str]['amount_paid'].sum() if not p_df.empty else 0.0}")
            m4.metric("Appointments", pd.read_sql_query("SELECT COUNT(*) FROM appointments", conn).iloc[0,0])
            st.divider()
            g1, g2, g3 = st.columns(3)
            if not p_df.empty:
                with g1:
                    fig1 = px.bar(p_df['reason'].value_counts().reset_index(), x='reason', y='count', color_discrete_sequence=['#87CEFA'])
                    fig1.update_layout(template="plotly_dark")
                    st.plotly_chart(fig1, use_container_width=True)
                with g2:
                    fig2 = px.line(p_df.groupby('visit_date')['amount_paid'].sum().reset_index(), x='visit_date', y='amount_paid', markers=True)
                    fig2.update_layout(template="plotly_dark")
                    st.plotly_chart(fig2, use_container_width=True)
                with g3:
                    doc_w = pd.read_sql_query("SELECT name, booked_slots FROM doctors", conn)
                    fig3 = px.bar(doc_w, x='name', y='booked_slots', color_discrete_sequence=['#87CEFA'])
                    fig3.update_layout(template="plotly_dark")
                    st.plotly_chart(fig3, use_container_width=True)

        elif nav == "Doctors Allotment":
            st.title("Staff & Shift Management")
            t1, t2 = st.tabs(["Add Doctor", "Edit Records"])
            with t1:
                with st.form("admin_add_doc"):
                    dn, ds = st.text_input("Doctor Name"), st.selectbox("Specialty", ["General Medicine", "Cardiology", "Neurology"])
                    nr = st.text_input("Allocate Nurse")
                    t_st, t_en = st.time_input("Shift Start"), st.time_input("Shift End")
                    if st.form_submit_button("Save Details"):
                        shft = f"{t_st.strftime('%H:%M')} - {t_en.strftime('%H:%M')}"
                        conn.execute("INSERT INTO doctors (name, specialty, total_slots, nurse_assigned, shift_timing) VALUES (?,?,?,?,?)", (dn, ds, 10, nr, shft))
                        conn.commit(); st.rerun()

        elif nav == "Room Management":
            st.title("🛌 Room & Bed Management")
            with st.expander("➕ Add New Hospital Room"):
                with st.form("add_room"):
                    r_no, r_ty = st.text_input("Room No"), st.selectbox("Type", ["General", "ICU", "Private"])
                    if st.form_submit_button("Register"):
                        conn.execute("INSERT INTO rooms (room_no, type) VALUES (?,?)", (r_no, r_ty))
                        conn.commit(); st.rerun()
            rooms = pd.read_sql_query("SELECT * FROM rooms", conn)
            st.dataframe(rooms, use_container_width=True)

    # ---------------- RECEPTIONIST INTERFACE (20-MIN SLOTS) ---------------- #
    elif st.session_state.role == "Receptionist":
        st.title("📞 Reception Management")
        t1, t2, t3 = st.tabs(["Register Patient", "Book 20-Min Slot", "Edit Info"])
        with t1:
            with st.form("rec_reg_p"):
                pn, pa = st.text_input("Full Name"), st.number_input("Age", 1, 120, 25)
                pb, pr = st.selectbox("Blood Group", ["A+", "B+", "O+", "AB+", "A-", "B-", "O-", "AB-"]), st.text_input("Reason")
                pp = st.number_input("Payment (₹)", 0.0)
                if st.form_submit_button("Register"):
                    conn.execute("INSERT INTO patients (name, age, blood_group, reason, amount_paid, visit_date) VALUES (?,?,?,?,?,?)", (pn, pa, pb, pr, pp, today_str))
                    conn.commit(); st.success(f"{pn} Registered!")
        with t2:
            st.subheader("Book 20-Minute Slot")
            p_l, d_l = pd.read_sql_query("SELECT id, name FROM patients", conn), pd.read_sql_query("SELECT id, name, shift_timing FROM doctors", conn)
            if not p_l.empty and not d_l.empty:
                c1, c2 = st.columns(2)
                p_s, d_s = c1.selectbox("Patient", p_l['name']), c2.selectbox("Doctor", d_l['name'])
                dr = d_l[d_l['name'] == d_s].iloc[0]
                avail = get_available_slots(dr['id'], dr['shift_timing'], today_str)
                if avail:
                    tm = st.selectbox("Select 20-Min Slot", avail)
                    if st.button("Confirm Slot"):
                        pid = p_l[p_l['name'] == p_s]['id'].iloc[0]
                        conn.execute("INSERT INTO appointments (patient_id, doctor_id, appointment_date, appointment_time) VALUES (?,?,?,?)", (int(pid), int(dr['id']), today_str, tm))
                        conn.commit(); st.success(f"Booked for {tm}!"); st.rerun()

    # ---------------- HOSPITAL STAFF ---------------- #
    elif st.session_state.role == "Hospital Staff":
        st.title("👨‍⚕️ Staff Duty Board")
        staff_df = pd.read_sql_query("SELECT name as Doctor, nurse_assigned as Nurse, shift_timing as Shift FROM doctors", conn)
        st.table(staff_df)
        st.subheader("Today's Appointments")
        staff_appts = pd.read_sql_query(f"""
            SELECT p.name as Patient, d.name as Doctor, a.appointment_time as Time 
            FROM appointments a JOIN patients p ON a.patient_id = p.id 
            JOIN doctors d ON a.doctor_id = d.id WHERE a.appointment_date = '{today_str}' 
            ORDER BY Time ASC""", conn)
        st.dataframe(staff_appts, use_container_width=True)

    # ---------------- DOCTOR ---------------- #
    elif st.session_state.role == "Doctor":
        st.title("🩺 Doctor Room")
        feedback = pd.read_sql_query("SELECT name as Patient, query as Message, is_complaint FROM queries", conn)
        if not feedback.empty:
            st.error("🚨 Complaints")
            st.dataframe(feedback[feedback['is_complaint'] == 1], use_container_width=True)
            st.info("❓ Patient Inquiries")
            st.dataframe(feedback[feedback['is_complaint'] == 0], use_container_width=True)
        else: st.write("No patient feedback found.")

    # ---------------- PATIENT ---------------- #
    elif st.session_state.role == "Patient":
        st.title("🏥 Patient Portal")
        with st.form("p_query"):
            st.subheader("Submit Query or Complaint")
            docs = pd.read_sql_query("SELECT name FROM doctors", conn)
            t_doc = st.selectbox("Select Doctor", docs['name'])
            msg = st.text_area("Your message")
            comp = st.checkbox("Check if this is a formal complaint")
            if st.form_submit_button("Submit"):
                conn.execute("INSERT INTO queries (name, email, doctor_name, query, is_complaint) VALUES (?,?,?,?,?)", 
                             ("Patient", st.session_state.user_email, t_doc, msg, 1 if comp else 0))
                conn.commit(); st.success("Logged Successfully!")

    conn.close()
