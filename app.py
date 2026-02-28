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

# 1. Page Configuration
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
    # Updated appointments table to include time_slot
    c.execute("""CREATE TABLE IF NOT EXISTS appointments(
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        patient_id INTEGER, doctor_id INTEGER, 
        appointment_date TEXT, appointment_time TEXT)""")
    c.execute("CREATE TABLE IF NOT EXISTS queries(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT, doctor_name TEXT, query TEXT, is_complaint INTEGER DEFAULT 0, status TEXT DEFAULT 'Open')")
    c.execute("CREATE TABLE IF NOT EXISTS rooms(room_no TEXT PRIMARY KEY, type TEXT, status TEXT DEFAULT 'Available')")
    
    conn.commit()
    conn.close()

init_db()

# ================= HELPERS & LOGIC ================= #
def get_available_slots(doctor_id, shift_str, date_str):
    """Generates 30-minute slots and filters out already booked ones"""
    try:
        start_str, end_str = shift_str.split(" - ")
        start_dt = datetime.strptime(start_str, "%H:%M")
        end_dt = datetime.strptime(end_str, "%H:%M")
    except: return []

    slots = []
    current = start_dt
    while current + timedelta(minutes=30) <= end_dt:
        slots.append(current.strftime("%H:%M"))
        current += timedelta(minutes=30)

    # Check database for existing bookings for this doctor on this date
    conn = sqlite3.connect(DB_NAME)
    booked = pd.read_sql_query("SELECT appointment_time FROM appointments WHERE doctor_id=? AND appointment_date=?", 
                               conn, params=(doctor_id, date_str))
    conn.close()
    
    booked_list = booked['appointment_time'].tolist()
    return [s for s in slots if s not in booked_list]

def check_password(password, hashed):
    if isinstance(hashed, str): hashed = hashed.encode('utf-8')
    elif isinstance(hashed, memoryview): hashed = hashed.tobytes()
    try: return bcrypt.checkpw(password.encode('utf-8'), hashed)
    except: return False

# ================= UI STYLING ================= #
st.markdown("""
    <style>
    div[data-testid="stMetricValue"] { color: #ffffff; font-size: 38px; font-weight: bold; }
    .stButton>button { background-color: #00acee; color: white; border-radius: 20px; border: none; font-weight: bold; }
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
            elif len(p_in) < 8: st.error("Password must be 8+ characters")
            else:
                conn = sqlite3.connect(DB_NAME)
                hashed = bcrypt.hashpw(p_in.encode(), bcrypt.gensalt())
                try:
                    conn.execute("INSERT INTO users VALUES (?,?,?)", (e_in, sqlite3.Binary(hashed), role))
                    conn.commit()
                    st.success("Registered successfully!")
                except: st.error("User exists.")
                conn.close()

    if mode == "Login":
        if st.button("Login"):
            conn = sqlite3.connect(DB_NAME)
            res = conn.execute("SELECT password, role FROM users WHERE email=?", (e_in,)).fetchone()
            conn.close()
            if res and check_password(p_in, res[0]):
                st.session_state.logged_in, st.session_state.role, st.session_state.user_email = True, res[1], e_in
                st.rerun()
            else: st.error("Invalid Credentials")

# ================= MAIN APPLICATION ================= #
else:
    with st.sidebar:
        st.title("MediVista Admin")
        if st.session_state.role == "Admin":
            nav = st.radio("Navigation", ["Dashboard", "Doctors Allotment", "Patient Details", "Room Management", "Reports"])
        elif st.session_state.role == "Receptionist":
            nav = st.radio("Navigation", ["Receptionist Area"])
        else: nav = st.radio("Navigation", ["Portal"])

        st.markdown('<div class="sidebar-logout">', unsafe_allow_html=True)
        if st.button("Logout", use_container_width=True):
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
            with g1:
                st.write("### Visits by Reason")
                if not p_df.empty:
                    fig1 = px.bar(p_df['reason'].value_counts().reset_index(), x='reason', y='count', color_discrete_sequence=['#87CEFA'])
                    fig1.update_layout(template="plotly_dark")
                    st.plotly_chart(fig1, width='stretch')
            with g2:
                st.write("### Revenue Trend")
                if not p_df.empty:
                    fig2 = px.line(p_df.groupby('visit_date')['amount_paid'].sum().reset_index(), x='visit_date', y='amount_paid', markers=True)
                    fig2.update_layout(template="plotly_dark")
                    st.plotly_chart(fig2, width='stretch')
            with g3:
                st.write("### Doctor Availability")
                doc_avail = pd.read_sql_query("SELECT name, shift_timing FROM doctors", conn)
                st.table(doc_avail)

        elif nav == "Doctors Allotment":
            st.title("Manage Staff & Shifts")
            tab_add, tab_edit = st.tabs(["➕ Add Doctor", "✏️ Edit Doctor"])
            with tab_add:
                with st.form("admin_add_doc"):
                    dn, ds = st.text_input("Doctor Name"), st.selectbox("Specialty", ["General", "Cardiology", "Neurology"])
                    nr = st.text_input("Nurse Name")
                    t_st, t_en = st.time_input("Start"), st.time_input("End")
                    if st.form_submit_button("Save Doctor"):
                        shft = f"{t_st.strftime('%H:%M')} - {t_en.strftime('%H:%M')}"
                        conn.execute("INSERT INTO doctors (name, specialty, total_slots, nurse_assigned, shift_timing) VALUES (?,?,?,?,?)", (dn, ds, 10, nr, shft))
                        conn.commit(); st.rerun()
            with tab_edit:
                docs = pd.read_sql_query("SELECT * FROM doctors", conn)
                if not docs.empty:
                    sel_doc = st.selectbox("Select Doctor", docs['name'])
                    with st.form("edit_doc"):
                        up_nr = st.text_input("New Nurse", docs[docs['name']==sel_doc].iloc[0]['nurse_assigned'])
                        if st.form_submit_button("Update"):
                            conn.execute("UPDATE doctors SET nurse_assigned=? WHERE name=?", (up_nr, sel_doc))
                            conn.commit(); st.rerun()

        elif nav == "Patient Details":
            st.title("📂 Patient Records")
            patients = pd.read_sql_query("SELECT * FROM patients", conn)
            st.dataframe(patients, width='stretch')
            sel_p = st.selectbox("Edit Patient", patients['name'])
            with st.form("edit_p"):
                new_reason = st.text_input("Update Reason", patients[patients['name']==sel_p].iloc[0]['reason'])
                if st.form_submit_button("Update Details"):
                    conn.execute("UPDATE patients SET reason=? WHERE name=?", (new_reason, sel_p))
                    conn.commit(); st.rerun()

    # ---------------- RECEPTIONIST INTERFACE (UPDATED SLOTS) ---------------- #
    elif st.session_state.role == "Receptionist":
        st.title("📞 Reception Management")
        t1, t2, t3 = st.tabs(["Register Patient", "Bookings", "Edit Records"])
        
        with t1:
            with st.form("rec_add_p"):
                p_n, p_a = st.text_input("Name"), st.number_input("Age", 1, 120, 25)
                p_b = st.selectbox("Blood", ["A+", "B+", "O+", "AB+", "A-", "B-", "O-", "AB-"])
                p_r, p_p = st.text_input("Reason"), st.number_input("Payment (₹)", 0.0)
                if st.form_submit_button("Register"):
                    conn.execute("INSERT INTO patients (name, age, blood_group, reason, amount_paid, visit_date) VALUES (?,?,?,?,?,?)", (p_n, p_a, p_b, p_r, p_p, today_str))
                    conn.commit(); st.success("Registered!")

        with t2:
            st.subheader("📅 Book 30-Min Slot")
            p_list = pd.read_sql_query("SELECT id, name FROM patients", conn)
            d_list = pd.read_sql_query("SELECT id, name, shift_timing FROM doctors", conn)
            
            if not p_list.empty and not d_list.empty:
                col_p, col_d = st.columns(2)
                pat_name = col_p.selectbox("Patient", p_list['name'])
                doc_name = col_d.selectbox("Doctor", d_list['name'])
                
                # Fetch available 30-min slots
                doc_row = d_list[d_list['name'] == doc_name].iloc[0]
                avail_slots = get_available_slots(doc_row['id'], doc_row['shift_timing'], today_str)
                
                if avail_slots:
                    sel_time = st.selectbox("Available Time Slots (30 mins each)", avail_slots)
                    if st.button("Confirm Booking"):
                        pid = p_list[p_list['name'] == pat_name]['id'].iloc[0]
                        conn.execute("INSERT INTO appointments (patient_id, doctor_id, appointment_date, appointment_time) VALUES (?,?,?,?)", 
                                     (int(pid), int(doc_row['id']), today_str, sel_time))
                        conn.commit(); st.success(f"Booked at {sel_time}!")
                else:
                    st.error("No slots available for this doctor today.")
            
            st.divider()
            st.write("### Today's Schedule")
            schedule = pd.read_sql_query(f"""
                SELECT p.name as Patient, d.name as Doctor, a.appointment_time 
                FROM appointments a JOIN patients p ON a.patient_id=p.id JOIN doctors d ON a.doctor_id=d.id 
                WHERE a.appointment_date='{today_str}' ORDER BY a.appointment_time ASC""", conn)
            st.dataframe(schedule, width='stretch')

        with t3:
            p_edit = pd.read_sql_query("SELECT name, age, reason FROM patients", conn)
            if not p_edit.empty:
                target = st.selectbox("Select Patient to Edit", p_edit['name'], key="rec_p_edit")
                with st.form("rec_p_edit_form"):
                    up_age = st.number_input("Age", 1, 120, int(p_edit[p_edit['name']==target].iloc[0]['age']))
                    if st.form_submit_button("Update"):
                        conn.execute("UPDATE patients SET age=? WHERE name=?", (up_age, target))
                        conn.commit(); st.rerun()

    conn.close()
