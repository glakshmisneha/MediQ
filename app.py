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

# 1. Page Configuration
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
    c.execute("CREATE TABLE IF NOT EXISTS appointments(id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER, doctor_id INTEGER, appointment_date TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS queries(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT, doctor_name TEXT, query TEXT, is_complaint INTEGER DEFAULT 0, status TEXT DEFAULT 'Open')")
    c.execute("CREATE TABLE IF NOT EXISTS rooms(room_no TEXT PRIMARY KEY, type TEXT, status TEXT DEFAULT 'Available')")
    
    # Schema Migration for shift timing and nurse assignment
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
    # Rules: 8+ chars, 1 Capital, 1 Number
    if len(password) < 8: return False, "Password must be at least 8 characters."
    if not any(c.isupper() for c in password): return False, "Missing an uppercase letter."
    if not any(c.isdigit() for c in password): return False, "Missing a number."
    return True, ""

# ================= UI STYLING ================= #
st.markdown("""
    <style>
    div[data-testid="stMetricValue"] { color: #ffffff; font-size: 38px; font-weight: bold; }
    .stButton>button { background-color: #00acee; color: white; border-radius: 20px; border: none; font-weight: bold; }
    .stSidebar { background-color: #0e1117; }
    /* Repositions Logout to the bottom-left corner */
    .sidebar-logout { position: fixed; bottom: 20px; left: 20px; width: 220px; z-index: 999; }
    [data-testid="stForm"] { border: 1px solid #30363d !important; border-radius: 15px; background-color: #161b22; }
    </style>
    """, unsafe_allow_html=True)

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# ================= AUTHENTICATION FLOW ================= #
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
                    st.success("Registered Successfully!")
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
    # --- Sidebar and Navigation ---
    with st.sidebar:
        st.title("MediVista Admin")
        st.write(f"**Current Role:** {st.session_state.role}")
        
        # Navigation logic based on role
        if st.session_state.role == "Admin":
            nav = st.radio("Navigation", ["Dashboard", "Doctors Allotment", "Room Management", "Reports"])
        elif st.session_state.role == "Hospital Staff":
            nav = st.radio("Navigation", ["Duty Board"])
        elif st.session_state.role == "Receptionist":
            nav = st.radio("Navigation", ["Bookings"])
        else:
            nav = st.radio("Navigation", ["Portal"])

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
            a_df = pd.read_sql_query("SELECT * FROM appointments", conn)
            
            # Metrics
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Visits", len(p_df))
            m2.metric("Total Revenue", f"₹ {p_df['amount_paid'].sum() if not p_df.empty else 0.0}")
            daily_rev = p_df[p_df['visit_date'] == today_str]['amount_paid'].sum() if not p_df.empty else 0.0
            m3.metric("Today's Revenue", f"₹ {daily_rev}")
            m4.metric("Appointments", len(a_df))
            
            st.divider()
            
            # Graphs
            if not p_df.empty:
                g1, g2 = st.columns(2)
                fig1 = px.bar(p_df['reason'].value_counts().reset_index(), x='reason', y='count', color_discrete_sequence=['#87CEFA'])
                fig1.update_layout(template="plotly_dark")
                g1.plotly_chart(fig1, width='stretch')
                
                fig2 = px.line(p_df.groupby('visit_date')['amount_paid'].sum().reset_index(), x='visit_date', y='amount_paid', markers=True)
                fig2.update_layout(template="plotly_dark")
                g2.plotly_chart(fig2, width='stretch')

        elif nav == "Doctors Allotment":
            st.title("Manage Staff & Shifts")
            tab_add, tab_edit = st.tabs(["➕ Add Doctor", "✏️ Edit Doctor"])
            
            with tab_add:
                with st.form("admin_add_doc"):
                    c1, c2 = st.columns(2)
                    dn, ds = c1.text_input("Name"), c2.selectbox("Specialty", ["General", "Cardiology", "Neurology"])
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
                        if st.form_submit_button("Update Details"):
                            conn.execute("UPDATE doctors SET specialty=?, nurse_assigned=? WHERE name=?", (up_spec, up_nurse, sel_doc))
                            conn.commit(); st.rerun()
                st.dataframe(docs, width='stretch')

        elif nav == "Room Management":
            st.title("🛌 Room & Bed Management")
            tab_v, tab_e = st.tabs(["View Rooms", "Edit Status"])
            
            with tab_v:
                rooms = pd.read_sql_query("SELECT * FROM rooms", conn)
                st.dataframe(rooms, width='stretch')
                with st.expander("➕ Add New Hospital Room"):
                    with st.form("add_new_room"):
                        r_no, r_ty = st.text_input("Room No"), st.selectbox("Type", ["General", "ICU", "Private"])
                        if st.form_submit_button("Register Room"):
                            conn.execute("INSERT INTO rooms (room_no, type) VALUES (?,?)", (r_no, r_ty))
                            conn.commit(); st.rerun()

            with tab_e:
                rooms = pd.read_sql_query("SELECT * FROM rooms", conn)
                if not rooms.empty:
                    sel_rm = st.selectbox("Room Number", rooms['room_no'])
                    with st.form("edit_room_status"):
                        new_status = st.selectbox("New Status", ["Available", "Occupied", "Cleaning"])
                        if st.form_submit_button("Update Room"):
                            conn.execute("UPDATE rooms SET status=? WHERE room_no=?", (new_status, sel_rm))
                            conn.commit(); st.rerun()

        elif nav == "Reports":
            st.title("📊 Hospital Reports")
            r_df = pd.read_sql_query("SELECT name, reason, amount_paid, visit_date FROM patients", conn)
            st.dataframe(r_df, width='stretch')
            if st.button("Download PDF"):
                fn = f"MediVista_Report_{datetime.now().strftime('%Y%m%d')}.pdf"
                doc = SimpleDocTemplate(fn, pagesize=A4)
                parts = [Paragraph("<b>MediVista Revenue Report</b>", ParagraphStyle('Title', fontSize=22, alignment=1))]
                doc.build(parts)
                with open(fn, "rb") as f:
                    st.download_button("Download Now", f, file_name=fn)

    # ---------------- PATIENT INTERFACE ---------------- #
    elif st.session_state.role == "Patient":
        st.title("🏥 Patient Portal")
        with st.form("patient_query"):
            st.write("### Submit Query or Complaint")
            d_list = pd.read_sql_query("SELECT name FROM doctors", conn)
            target = st.selectbox("Select Doctor", d_list['name'])
            msg = st.text_area("Your message")
            is_c = st.checkbox("Is this a complaint?")
            if st.form_submit_button("Submit"):
                conn.execute("INSERT INTO queries (name, email, doctor_name, query, is_complaint) VALUES (?,?,?,?,?)",
                             ("Patient", st.session_state.user_email, target, msg, 1 if is_c else 0))
                conn.commit(); st.success("Logged!")

    conn.close()
