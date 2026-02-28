import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import bcrypt
import re
from datetime import datetime, time
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
    c.execute("CREATE TABLE IF NOT EXISTS appointments(id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER, doctor_id INTEGER, appointment_date TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS queries(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT, doctor_name TEXT, query TEXT, is_complaint INTEGER DEFAULT 0, status TEXT DEFAULT 'Open')")
    c.execute("CREATE TABLE IF NOT EXISTS rooms(room_no TEXT PRIMARY KEY, type TEXT, status TEXT DEFAULT 'Available')")
    
    # Schema Migration for updated fields
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
def check_password(password, hashed):
    if isinstance(hashed, str): hashed = hashed.encode('utf-8')
    elif isinstance(hashed, memoryview): hashed = hashed.tobytes()
    try: return bcrypt.checkpw(password.encode('utf-8'), hashed)
    except: return False

def is_valid_gmail(email):
    return bool(re.match(r"^[a-zA-Z0-9._%+-]+@gmail\.com$", email))

def is_strong_password(password):
    if len(password) < 8 or not any(c.isupper() for c in password) or not any(c.isdigit() for c in password):
        return False, "8+ chars, 1 Upper, 1 Number"
    return True, ""

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
            is_s, msg = is_strong_password(p_in)
            if not is_valid_gmail(e_in): st.error("Email must be @gmail.com")
            elif not is_s: st.error(msg)
            else:
                conn = sqlite3.connect(DB_NAME)
                hashed = bcrypt.hashpw(p_in.encode(), bcrypt.gensalt())
                try:
                    conn.execute("INSERT INTO users VALUES (?,?,?)", (e_in, sqlite3.Binary(hashed), role))
                    conn.commit()
                    st.success("Registered successfully!")
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
        st.title("MediVista Admin")
        if st.session_state.role == "Admin":
            nav = st.radio("Navigation", ["Dashboard", "Doctors Allotment", "Patient Details", "Room Management", "Reports"])
        elif st.session_state.role == "Receptionist":
            nav = st.radio("Navigation", ["Receptionist Area"])
        else:
            nav = st.radio("Navigation", ["Portal"])

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
                    fig1.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig1, width='stretch')
            with g2:
                st.write("### Revenue Trend")
                if not p_df.empty:
                    fig2 = px.line(p_df.groupby('visit_date')['amount_paid'].sum().reset_index(), x='visit_date', y='amount_paid', markers=True)
                    fig2.update_layout(template="plotly_dark")
                    st.plotly_chart(fig2, width='stretch')
            with g3:
                st.write("### Doctor Workload")
                doc_w = pd.read_sql_query("SELECT name, booked_slots FROM doctors", conn)
                fig3 = px.bar(doc_w, x='name', y='booked_slots', color_discrete_sequence=['#87CEFA'])
                fig3.update_layout(template="plotly_dark")
                st.plotly_chart(fig3, width='stretch')

        elif nav == "Doctors Allotment":
            st.title("Manage Staff & Shifts")
            tab_add, tab_edit = st.tabs(["➕ Add Doctor", "✏️ Edit Doctor"])
            with tab_add:
                with st.form("admin_add_doc"):
                    c1, c2 = st.columns(2)
                    dn, ds = c1.text_input("Name"), c2.selectbox("Specialty", ["General Medicine", "Cardiology", "Neurology"])
                    nr, sl = c1.text_input("Nurse"), c2.number_input("Slots", 1, 50)
                    t_st, t_en = st.time_input("Shift Start"), st.time_input("Shift End")
                    if st.form_submit_button("Save Doctor"):
                        shft = f"{t_st.strftime('%H:%M')} - {t_en.strftime('%H:%M')}"
                        conn.execute("INSERT INTO doctors (name, specialty, total_slots, nurse_assigned, shift_timing) VALUES (?,?,?,?,?)", (dn, ds, sl, nr, shft))
                        conn.commit(); st.rerun()
            with tab_edit:
                docs = pd.read_sql_query("SELECT * FROM doctors", conn)
                if not docs.empty:
                    sel_doc = st.selectbox("Select Doctor to Update", docs['name'])
                    d_info = docs[docs['name'] == sel_doc].iloc[0]
                    with st.form("edit_doc_form"):
                        up_spec = st.text_input("Update Specialty", d_info['specialty'])
                        up_nurse = st.text_input("Update Nurse", d_info['nurse_assigned'])
                        if st.form_submit_button("Update Doctor Details"):
                            conn.execute("UPDATE doctors SET specialty=?, nurse_assigned=? WHERE name=?", (up_spec, up_nurse, sel_doc))
                            conn.commit(); st.rerun()

        elif nav == "Patient Details":
            st.title("📂 Patient Management")
            p_df = pd.read_sql_query("SELECT * FROM patients", conn)
            st.dataframe(p_df, width='stretch')
            
            st.divider()
            st.subheader("✏️ Edit Patient Information")
            if not p_df.empty:
                sel_p = st.selectbox("Select Patient to Edit", p_df['name'])
                p_data = p_df[p_df['name'] == sel_p].iloc[0]
                with st.form("edit_patient_form"):
                    e_age = st.number_input("Age", 1, 120, int(p_data['age']))
                    e_blood = st.selectbox("Blood Group", ["A+", "B+", "O+", "AB+", "A-", "B-", "O-", "AB-"], index=["A+", "B+", "O+", "AB+", "A-", "B-", "O-", "AB-"].index(p_data['blood_group']))
                    e_reason = st.text_input("Reason", p_data['reason'])
                    if st.form_submit_button("Update Patient Details"):
                        conn.execute("UPDATE patients SET age=?, blood_group=?, reason=? WHERE name=?", (e_age, e_blood, e_reason, sel_p))
                        conn.commit(); st.rerun()

    # ---------------- RECEPTIONIST INTERFACE ---------------- #
    elif st.session_state.role == "Receptionist":
        st.title("📞 Reception Management")
        t1, t2, t3 = st.tabs(["Register Patient", "Bookings", "Edit Records"])
        with t1:
            with st.form("rec_add_p"):
                p_n = st.text_input("Patient Name")
                p_a = st.number_input("Age", 1, 120, 25)
                p_b = st.selectbox("Blood Group", ["A+", "B+", "O+", "AB+", "A-", "B-", "O-", "AB-"])
                p_r = st.text_input("Reason")
                p_p = st.number_input("Payment (₹)", 0.0)
                if st.form_submit_button("Register"):
                    conn.execute("INSERT INTO patients (name, age, blood_group, reason, amount_paid, visit_date) VALUES (?,?,?,?,?,?)", (p_n, p_a, p_b, p_r, p_p, today_str))
                    conn.commit(); st.success(f"{p_n} Registered!")
        with t2:
            st.dataframe(pd.read_sql_query(f"SELECT * FROM appointments WHERE appointment_date='{today_str}'", conn), width='stretch')
        with t3:
            st.subheader("✏️ Edit Patient Details")
            p_list = pd.read_sql_query("SELECT * FROM patients", conn)
            if not p_list.empty:
                sel_p_rec = st.selectbox("Patient", p_list['name'], key="rec_edit_p")
                p_rec_data = p_list[p_list['name'] == sel_p_rec].iloc[0]
                with st.form("rec_edit_p_form"):
                    re_age = st.number_input("Age", 1, 120, int(p_rec_data['age']))
                    re_reason = st.text_input("Reason", p_rec_data['reason'])
                    if st.form_submit_button("Update"):
                        conn.execute("UPDATE patients SET age=?, reason=? WHERE name=?", (re_age, re_reason, sel_p_rec))
                        conn.commit(); st.rerun()

    conn.close()
