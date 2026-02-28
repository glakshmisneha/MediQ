import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import bcrypt
import re
import os
from datetime import datetime, time, timedelta
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
    c.execute("CREATE TABLE IF NOT EXISTS users(email TEXT PRIMARY KEY, password BLOB, role TEXT)")
    c.execute("""CREATE TABLE IF NOT EXISTS doctors(
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        name TEXT, specialty TEXT, total_slots INTEGER, 
        booked_slots INTEGER DEFAULT 0, 
        nurse_assigned TEXT, shift_timing TEXT)""")
    c.execute("CREATE TABLE IF NOT EXISTS patients(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, age INTEGER, blood_group TEXT, reason TEXT, amount_paid REAL, visit_date TEXT)")
    # Includes appointment_time for 20-min slot management
    c.execute("""CREATE TABLE IF NOT EXISTS appointments(
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        patient_id INTEGER, doctor_id INTEGER, 
        appointment_date TEXT, appointment_time TEXT)""")
    c.execute("CREATE TABLE IF NOT EXISTS queries(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT, doctor_name TEXT, query TEXT, is_complaint INTEGER DEFAULT 0, status TEXT DEFAULT 'Open')")
    c.execute("CREATE TABLE IF NOT EXISTS rooms(room_no TEXT PRIMARY KEY, type TEXT, status TEXT DEFAULT 'Available')")
    
    # Ensure schema is up to date
    c.execute("PRAGMA table_info(doctors)")
    existing_columns = [column[1] for column in c.fetchall()]
    if 'nurse_assigned' not in existing_columns:
        c.execute("ALTER TABLE doctors ADD COLUMN nurse_assigned TEXT DEFAULT 'Not Assigned'")
    if 'shift_timing' not in existing_columns:
        c.execute("ALTER TABLE doctors ADD COLUMN shift_timing TEXT DEFAULT '08:00 - 16:00'")
        
    conn.commit()
    conn.close()

init_db()

# ================= HELPER LOGIC ================= #
def get_available_slots(doctor_id, shift_str, date_str):
    """Calculates available 20-minute intervals based on shift"""
    try:
        start_str, end_str = shift_str.split(" - ")
        start_dt = datetime.strptime(start_str, "%H:%M")
        end_dt = datetime.strptime(end_str, "%H:%M")
    except: return []

    slots = []
    current = start_dt
    # Loop generates slots every 20 minutes
    while current + timedelta(minutes=20) <= end_dt:
        slots.append(current.strftime("%H:%M"))
        current += timedelta(minutes=20)

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
    /* Position Logout to bottom-left corner */
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
            elif len(p_in) < 8 or not any(c.isupper() for c in p_in): st.error("Password: 8+ chars & 1 Uppercase")
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
            if res and check_password(p_in, res[0]):
                st.session_state.logged_in, st.session_state.role, st.session_state.user_email = True, res[1], e_in
                st.rerun()
            else: st.error("Invalid Credentials")

# ================= MAIN APPLICATION ================= #
else:
    with st.sidebar:
        st.title("MediVista")
        st.write(f"**Current Role:** {st.session_state.role}")
        
        # Navigation logic based on role
        if st.session_state.role == "Admin":
            nav = st.radio("Navigation", ["Dashboard", "Doctors Allotment", "Patient Details", "Room Management", "Reports"])
        elif st.session_state.role == "Receptionist":
            nav = st.radio("Navigation", ["Reception Area"])
        else: nav = "Portal"

        # Logout button anchored to the bottom-left
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
            
            # Metrics Row
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Visits", len(p_df))
            m2.metric("Total Revenue", f"₹ {p_df['amount_paid'].sum() if not p_df.empty else 0.0}")
            m3.metric("Today's Revenue", f"₹ {p_df[p_df['visit_date'] == today_str]['amount_paid'].sum() if not p_df.empty else 0.0}")
            m4.metric("Appointments", pd.read_sql_query("SELECT COUNT(*) FROM appointments", conn).iloc[0,0])

            st.divider()
            
            # Graphs
            if not p_df.empty:
                g1, g2, g3 = st.columns(3)
                with g1:
                    fig1 = px.bar(p_df['reason'].value_counts().reset_index(), x='reason', y='count', color_discrete_sequence=['#87CEFA'])
                    fig1.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig1, width='stretch')
                with g2:
                    fig2 = px.line(p_df.groupby('visit_date')['amount_paid'].sum().reset_index(), x='visit_date', y='amount_paid', markers=True)
                    fig2.update_layout(template="plotly_dark")
                    st.plotly_chart(fig2, width='stretch')
                with g3:
                    doc_w = pd.read_sql_query("SELECT name, booked_slots FROM doctors", conn)
                    fig3 = px.bar(doc_w, x='name', y='booked_slots', color_discrete_sequence=['#87CEFA'])
                    fig3.update_layout(template="plotly_dark")
                    st.plotly_chart(fig3, width='stretch')

        elif nav == "Doctors Allotment":
            st.title("Staff & Shift Allotment")
            tab_add, tab_edit = st.tabs(["➕ Add Doctor", "✏️ Edit Records"])
            with tab_add:
                with st.form("admin_add_doc"):
                    dn, ds = st.text_input("Doctor Name"), st.selectbox("Specialty", ["General", "Pediatrics", "ICU"])
                    nr = st.text_input("Allocate Nurse")
                    t_st, t_en = st.time_input("Shift Start"), st.time_input("Shift End")
                    if st.form_submit_button("Save Details"):
                        shft = f"{t_st.strftime('%H:%M')} - {t_en.strftime('%H:%M')}"
                        conn.execute("INSERT INTO doctors (name, specialty, total_slots, nurse_assigned, shift_timing) VALUES (?,?,?,?,?)", (dn, ds, 10, nr, shft))
                        conn.commit(); st.rerun()
            with tab_edit:
                docs = pd.read_sql_query("SELECT * FROM doctors", conn)
                st.dataframe(docs, width='stretch')

        elif nav == "Patient Details":
            st.title("📂 Patient Information")
            patients = pd.read_sql_query("SELECT * FROM patients", conn)
            st.dataframe(patients, width='stretch')
            # Edit Option for Admin
            if not patients.empty:
                sel_p = st.selectbox("Select Patient to Edit", patients['name'])
                with st.form("edit_patient"):
                    new_r = st.text_input("Update Reason", patients[patients['name']==sel_p].iloc[0]['reason'])
                    if st.form_submit_button("Update Info"):
                        conn.execute("UPDATE patients SET reason=? WHERE name=?", (new_r, sel_p))
                        conn.commit(); st.rerun()

        elif nav == "Room Management":
            st.title("🛌 Hospital Room Management")
            rooms = pd.read_sql_query("SELECT * FROM rooms", conn)
            st.dataframe(rooms, width='stretch')
            with st.expander("➕ Add New Room"):
                with st.form("add_room"):
                    r_no, r_ty = st.text_input("Room No"), st.selectbox("Type", ["General", "Private", "ICU"])
                    if st.form_submit_button("Register"):
                        conn.execute("INSERT INTO rooms (room_no, type) VALUES (?,?)", (r_no, r_ty))
                        conn.commit(); st.rerun()

        elif nav == "Reports":
            st.title("📊 Hospital Reports")
            report_df = pd.read_sql_query("SELECT name, reason, amount_paid, visit_date FROM patients", conn)
            if not report_df.empty:
                st.metric("Gross Revenue Preview", f"₹ {report_df['amount_paid'].sum():,.2f}")
                st.dataframe(report_df, width='stretch')
                if st.button("Generate PDF Report"):
                    fn = f"Report_{datetime.now().strftime('%Y%m%d')}.pdf"
                    doc = SimpleDocTemplate(fn, pagesize=A4)
                    parts = [Paragraph("<b>MediVista Hospital Revenue Report</b>", ParagraphStyle('Title', fontSize=22, alignment=1))]
                    doc.build(parts)
                    with open(fn, "rb") as f:
                        st.download_button("Download Now", f, file_name=fn)

    # ---------------- RECEPTIONIST INTERFACE (20-MIN SLOTS) ---------------- #
    elif st.session_state.role == "Receptionist":
        st.title("📞 Receptionist Area")
        t1, t2, t3 = st.tabs(["Register Patient", "20-Min Slot Booking", "Edit Records"])
        
        with t1:
            with st.form("rec_reg_patient"):
                st.subheader("Add New Patient")
                pn = st.text_input("Patient Full Name")
                pa = st.number_input("Age", 1, 120, 25)
                pb = st.selectbox("Blood Group", ["A+", "B+", "O+", "AB+", "A-", "B-", "O-", "AB-"])
                pr = st.text_input("Reason")
                if st.form_submit_button("Register"):
                    conn.execute("INSERT INTO patients (name, age, blood_group, reason, visit_date) VALUES (?,?,?,?,?)", (pn, pa, pb, pr, today_str))
                    conn.commit(); st.success(f"Patient {pn} Added!")

        with t2:
            st.subheader("📅 Book 20-Minute Time Slot")
            p_list = pd.read_sql_query("SELECT id, name FROM patients", conn)
            d_list = pd.read_sql_query("SELECT id, name, shift_timing FROM doctors", conn)
            
            if not p_list.empty and not d_list.empty:
                col_p, col_d = st.columns(2)
                pat_sel = col_p.selectbox("Patient", p_list['name'])
                doc_sel = col_d.selectbox("Doctor", d_list['name'])
                
                # Fetching 20-min intervals
                dr_data = d_list[d_list['name'] == doc_sel].iloc[0]
                avail_slots = get_available_slots(dr_data['id'], dr_data['shift_timing'], today_str)
                
                if avail_slots:
                    sel_time = st.selectbox("Select Available 20-Min Slot", avail_slots)
                    if st.button("Confirm Appointment"):
                        pid = p_list[p_list['name'] == pat_sel]['id'].iloc[0]
                        conn.execute("INSERT INTO appointments (patient_id, doctor_id, appointment_date, appointment_time) VALUES (?,?,?,?)", 
                                     (int(pid), int(dr_data['id']), today_str, sel_time))
                        conn.commit(); st.success(f"Appointment set for {sel_time}!")
                        st.rerun()
                else: st.error("No 20-minute slots left for this shift.")
            
            st.divider()
            st.write("### Today's Schedule")
            schedule = pd.read_sql_query(f"""
                SELECT p.name as Patient, d.name as Doctor, a.appointment_time as 'Time'
                FROM appointments a JOIN patients p ON a.patient_id=p.id JOIN doctors d ON a.doctor_id=d.id 
                WHERE a.appointment_date='{today_str}' ORDER BY Time ASC""", conn)
            st.dataframe(schedule, width='stretch')

    conn.close()
