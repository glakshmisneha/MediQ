import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import bcrypt
import re
from datetime import datetime, timedelta

# 1. Page Configuration (2026 Streamlit Standards)
st.set_page_config(page_title="MediVista Management", layout="wide", initial_sidebar_state="expanded")

DB_NAME = "mediq.db"

# ================= DATABASE INITIALIZATION & MIGRATIONS ================= #
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Create tables with proper schema
    c.execute("CREATE TABLE IF NOT EXISTS users(email TEXT PRIMARY KEY, password BLOB, role TEXT)")
    
    c.execute("""CREATE TABLE IF NOT EXISTS doctors(
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        name TEXT, 
        specialty TEXT, 
        email TEXT, 
        nurse_assigned TEXT, 
        shift_timing TEXT)""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS patients(
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        name TEXT, 
        age INTEGER, 
        blood_group TEXT, 
        reason TEXT, 
        amount_paid REAL, 
        visit_date TEXT,
        email TEXT UNIQUE)""")  # Added email field
    
    c.execute("""CREATE TABLE IF NOT EXISTS appointments(
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        patient_id INTEGER, 
        doctor_id INTEGER, 
        appointment_date TEXT, 
        appointment_time TEXT,
        status TEXT DEFAULT 'Scheduled')""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS queries(
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        patient_email TEXT, 
        recipient_type TEXT, 
        doctor_id INTEGER, 
        query_text TEXT, 
        response TEXT DEFAULT '',
        status TEXT DEFAULT 'Pending',
        created_at TEXT)""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS rooms(
        room_no TEXT PRIMARY KEY, 
        status TEXT DEFAULT 'Available',
        assigned_to TEXT DEFAULT NULL)""")
    
    # --- SCHEMA MIGRATION ---
    try:
        c.execute("ALTER TABLE patients ADD COLUMN email TEXT UNIQUE")
    except:
        pass
    
    try:
        c.execute("ALTER TABLE appointments ADD COLUMN status TEXT DEFAULT 'Scheduled'")
    except:
        pass
    
    try:
        c.execute("ALTER TABLE queries ADD COLUMN response TEXT DEFAULT ''")
    except:
        pass
    
    try:
        c.execute("ALTER TABLE queries ADD COLUMN status TEXT DEFAULT 'Pending'")
    except:
        pass
    
    try:
        c.execute("ALTER TABLE rooms ADD COLUMN assigned_to TEXT DEFAULT NULL")
    except:
        pass
    
    # Add default admin if not exists
    admin_exists = c.execute("SELECT * FROM users WHERE email='admin@medivista.com'").fetchone()
    if not admin_exists:
        hashed = bcrypt.hashpw('admin123'.encode(), bcrypt.gensalt())
        c.execute("INSERT INTO users VALUES (?,?,?)", ('admin@medivista.com', hashed, 'Admin'))
    
    # Add default rooms if not exists
    rooms = c.execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
    if rooms == 0:
        for i in range(1, 11):
            c.execute("INSERT INTO rooms (room_no, status) VALUES (?, 'Available')", (f"Room {i:03d}",))
    
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
    except:
        return []
    
    slots = []
    current = start_dt
    while current + timedelta(minutes=20) <= end_dt:
        slots.append(current.strftime("%H:%M"))
        current += timedelta(minutes=20)
    
    conn = sqlite3.connect(DB_NAME)
    booked = pd.read_sql_query(
        "SELECT appointment_time FROM appointments WHERE doctor_id=? AND appointment_date=? AND status!='Cancelled'", 
        conn, params=(doctor_id, date_str))
    conn.close()
    
    return [s for s in slots if s not in booked['appointment_time'].tolist()]

def get_patient_id_by_email(email):
    conn = sqlite3.connect(DB_NAME)
    result = conn.execute("SELECT id FROM patients WHERE email=?", (email,)).fetchone()
    conn.close()
    return result[0] if result else None

def is_valid_email(email):
    return bool(re.match(r"^[a-zA-Z0-9._%+-]+@gmail\.com$", email))

# ================= UI STYLING ================= #
st.markdown("""
    <style>
    div[data-testid="stMetricValue"] { color: #00acee; font-size: 32px; font-weight: bold; }
    .stButton>button { background-color: #00acee; color: white; border-radius: 20px; width: 100%; font-weight: bold; }
    .sidebar-logout { position: fixed; bottom: 20px; left: 20px; width: 220px; }
    [data-testid="stForm"] { border-radius: 15px; background-color: #161b22; border: 1px solid #30363d !important; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { border-radius: 4px 4px 0px 0px; padding: 10px 16px; background-color: #262730; }
    </style>
    """, unsafe_allow_html=True)

# Initialize session state
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_email" not in st.session_state:
    st.session_state.user_email = ""
if "role" not in st.session_state:
    st.session_state.role = ""

# ================= AUTHENTICATION ================= #
if not st.session_state.logged_in:
    st.title("🏥 MediVista Management Portal")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        mode = st.radio("Option", ["Login", "Register"], horizontal=True)
        email = st.text_input("Email (must be @gmail.com)")
        password = st.text_input("Password", type="password")
        
        if mode == "Register":
            role = st.selectbox("Role", ["Admin", "Receptionist", "Hospital Staff", "Doctor", "Patient"])
            if st.button("Create Account", use_container_width=True):
                if not is_valid_email(email):
                    st.error("Email must be @gmail.com")
                elif len(password) < 6:
                    st.error("Password must be at least 6 characters")
                else:
                    conn = sqlite3.connect(DB_NAME)
                    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
                    try:
                        conn.execute("INSERT INTO users VALUES (?,?,?)", (email, hashed, role))
                        conn.commit()
                        st.success("Registration Successful! Please login.")
                    except sqlite3.IntegrityError:
                        st.error("User already exists.")
                    finally:
                        conn.close()
        
        if mode == "Login":
            if st.button("Login", use_container_width=True):
                if not email or not password:
                    st.error("Please fill all fields")
                else:
                    conn = sqlite3.connect(DB_NAME)
                    user = conn.execute("SELECT password, role FROM users WHERE email=?", (email,)).fetchone()
                    conn.close()
                    
                    if user and bcrypt.checkpw(password.encode(), user[0]):
                        st.session_state.logged_in = True
                        st.session_state.user_email = email
                        st.session_state.role = user[1]
                        st.rerun()
                    else:
                        st.error("Invalid Credentials")

# ================= MAIN APPLICATION ================= #
else:
    with st.sidebar:
        st.title(f"🏥 MediVista")
        st.caption(f"Logged in as: **{st.session_state.role}**")
        st.divider()
        
        # Navigation based on role
        if st.session_state.role == "Admin":
            nav = st.radio("Navigation", ["Dashboard", "Room Management", "Manage Queries", "User Management"])
        elif st.session_state.role == "Receptionist":
            nav = st.radio("Navigation", ["Reception Area", "View Appointments"])
        elif st.session_state.role == "Hospital Staff":
            nav = st.radio("Navigation", ["Duty Board", "Room Status"])
        elif st.session_state.role == "Doctor":
            nav = st.radio("Navigation", ["Patient Queries", "My Schedule", "My Patients"])
        else:  # Patient
            nav = st.radio("Navigation", ["Patient Portal", "My Appointments", "Ask Question"])
        
        st.divider()
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.user_email = ""
            st.session_state.role = ""
            st.rerun()

    conn = sqlite3.connect(DB_NAME)
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # ---------------- ADMIN DASHBOARD ---------------- #
    if st.session_state.role == "Admin":
        if nav == "Dashboard":
            st.title("📊 Strategic Admin Overview")
            
            # Fetch metrics
            patients_df = pd.read_sql_query("SELECT * FROM patients", conn)
            appointments_df = pd.read_sql_query("SELECT * FROM appointments WHERE appointment_date = ?", conn, params=(today_str,))
            rooms_df = pd.read_sql_query("SELECT COUNT(*) as available FROM rooms WHERE status='Available'", conn)
            doctors_df = pd.read_sql_query("SELECT COUNT(*) as total FROM doctors", conn)
            
            # Calculate metrics
            total_patients = len(patients_df)
            patients_today = len(patients_df[patients_df['visit_date'] == today_str]) if not patients_df.empty else 0
            appointments_today = len(appointments_df)
            revenue_today = patients_df[patients_df['visit_date'] == today_str]['amount_paid'].sum() if not patients_df.empty else 0
            rooms_available = rooms_df['available'].iloc[0] if not rooms_df.empty else 0
            total_doctors = doctors_df['total'].iloc[0] if not doctors_df.empty else 0
            
            # Display metrics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Patients", total_patients)
                st.metric("Patients Today", patients_today)
            with col2:
                st.metric("Appointments Today", appointments_today)
                st.metric("Total Doctors", total_doctors)
            with col3:
                st.metric("Revenue Today", f"₹{revenue_today:,.2f}")
                st.metric("Rooms Available", rooms_available)
            with col4:
                pending_queries = pd.read_sql_query("SELECT COUNT(*) as count FROM queries WHERE status='Pending'", conn)
                st.metric("Pending Queries", pending_queries['count'].iloc[0])
            
            st.divider()
            
            # Revenue chart
            if not patients_df.empty:
                st.subheader("📈 Revenue Overview")
                daily_rev = patients_df.groupby('visit_date')['amount_paid'].sum().reset_index()
                daily_rev = daily_rev.sort_values('visit_date')
                
                fig_rev = px.bar(daily_rev, x='visit_date', y='amount_paid', 
                               title="Daily Revenue Tracking",
                               labels={'visit_date': 'Date', 'amount_paid': 'Revenue (₹)'})
                fig_rev.update_layout(template="plotly_dark")
                st.plotly_chart(fig_rev, use_container_width=True)
            
            # Recent appointments
            st.subheader("📋 Recent Appointments")
            recent_appts = pd.read_sql_query("""
                SELECT p.name as Patient, d.name as Doctor, 
                       a.appointment_date as Date, a.appointment_time as Time, a.status
                FROM appointments a
                JOIN patients p ON a.patient_id = p.id
                JOIN doctors d ON a.doctor_id = d.id
                ORDER BY a.appointment_date DESC, a.appointment_time DESC
                LIMIT 10
            """, conn)
            st.dataframe(recent_appts, use_container_width=True)
        
        elif nav == "Room Management":
            st.title("🏥 Room Management")
            
            col1, col2 = st.columns([1, 2])
            with col1:
                st.subheader("Add New Room")
                with st.form("add_room"):
                    room_no = st.text_input("Room Number")
                    if st.form_submit_button("Add Room"):
                        if room_no:
                            try:
                                conn.execute("INSERT INTO rooms (room_no) VALUES (?)", (room_no,))
                                conn.commit()
                                st.success(f"Room {room_no} added!")
                                st.rerun()
                            except sqlite3.IntegrityError:
                                st.error("Room already exists!")
            
            with col2:
                st.subheader("Room Status")
                rooms_df = pd.read_sql_query("SELECT * FROM rooms ORDER BY room_no", conn)
                
                # Update room status
                for idx, row in rooms_df.iterrows():
                    col_a, col_b, col_c = st.columns([2, 2, 1])
                    with col_a:
                        st.text(f"🏥 {row['room_no']}")
                    with col_b:
                        st.text(f"Status: {row['status']}")
                    with col_c:
                        if row['status'] == 'Available':
                            if st.button("Occupy", key=f"occupy_{idx}"):
                                conn.execute("UPDATE rooms SET status='Occupied' WHERE room_no=?", (row['room_no'],))
                                conn.commit()
                                st.rerun()
                        else:
                            if st.button("Free", key=f"free_{idx}"):
                                conn.execute("UPDATE rooms SET status='Available', assigned_to=NULL WHERE room_no=?", (row['room_no'],))
                                conn.commit()
                                st.rerun()
        
        elif nav == "Manage Queries":
            st.title("📨 Manage Patient Queries")
            
            queries_df = pd.read_sql_query("""
                SELECT q.*, d.name as doctor_name 
                FROM queries q 
                LEFT JOIN doctors d ON q.doctor_id = d.id 
                WHERE q.status='Pending'
                ORDER BY q.created_at DESC
            """, conn)
            
            if not queries_df.empty:
                for idx, query in queries_df.iterrows():
                    with st.expander(f"Query from {query['patient_email']} - {query['created_at']}"):
                        st.write(f"**Question:** {query['query_text']}")
                        if query['recipient_type'] == 'Doctor' and query['doctor_name']:
                            st.write(f"**To:** Dr. {query['doctor_name']}")
                        
                        response = st.text_area("Your Response", key=f"resp_{idx}")
                        if st.button("Submit Response", key=f"btn_{idx}"):
                            conn.execute("""
                                UPDATE queries 
                                SET response=?, status='Answered' 
                                WHERE id=?
                            """, (response, query['id']))
                            conn.commit()
                            st.success("Response sent!")
                            st.rerun()
            else:
                st.info("No pending queries")
        
        elif nav == "User Management":
            st.title("👥 User Management")
            
            users_df = pd.read_sql_query("SELECT email, role FROM users ORDER BY role, email", conn)
            
            # Add new user
            with st.expander("Add New User"):
                with st.form("add_user"):
                    new_email = st.text_input("Email (@gmail.com)")
                    new_password = st.text_input("Password", type="password")
                    new_role = st.selectbox("Role", ["Admin", "Receptionist", "Hospital Staff", "Doctor", "Patient"])
                    
                    if st.form_submit_button("Create User"):
                        if is_valid_email(new_email) and len(new_password) >= 6:
                            hashed = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt())
                            try:
                                conn.execute("INSERT INTO users VALUES (?,?,?)", (new_email, hashed, new_role))
                                conn.commit()
                                st.success("User created!")
                                st.rerun()
                            except sqlite3.IntegrityError:
                                st.error("Email already exists!")
                        else:
                            st.error("Invalid email or password too short")
            
            # Display users
            st.subheader("Current Users")
            st.dataframe(users_df, use_container_width=True)
    
    # ---------------- RECEPTIONIST ---------------- #
    elif st.session_state.role == "Receptionist":
        if nav == "Reception Area":
            st.title("📞 Reception Desk")
            
            tab1, tab2, tab3 = st.tabs(["Register Patient", "Add Doctor", "Book Appointment"])
            
            with tab1:
                with st.form("register_patient"):
                    st.subheader("New Patient Registration")
                    p_name = st.text_input("Full Name")
                    p_age = st.number_input("Age", 1, 120, 25)
                    p_blood = st.selectbox("Blood Group", ["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"])
                    p_email = st.text_input("Email (@gmail.com)")
                    p_reason = st.text_input("Visit Reason")
                    p_payment = st.number_input("Payment Amount (₹)", 0.0, 100000.0, 0.0)
                    
                    if st.form_submit_button("Register Patient"):
                        if not is_valid_email(p_email):
                            st.error("Email must be @gmail.com")
                        elif not p_name:
                            st.error("Name is required")
                        else:
                            try:
                                conn.execute("""
                                    INSERT INTO patients (name, age, blood_group, email, reason, amount_paid, visit_date) 
                                    VALUES (?,?,?,?,?,?,?)
                                """, (p_name, p_age, p_blood, p_email, p_reason, p_payment, today_str))
                                conn.commit()
                                st.success("Patient Registered Successfully!")
                            except sqlite3.IntegrityError:
                                st.error("Email already exists!")
            
            with tab2:
                with st.form("add_doctor"):
                    st.subheader("Add New Doctor")
                    d_name = st.text_input("Doctor Name")
                    d_specialty = st.text_input("Specialty")
                    d_email = st.text_input("Email")
                    d_nurse = st.text_input("Assigned Nurse")
                    d_shift = st.text_input("Shift Timing (e.g., 09:00 - 17:00)")
                    
                    if st.form_submit_button("Add Doctor"):
                        if d_name and d_specialty and d_email:
                            conn.execute("""
                                INSERT INTO doctors (name, specialty, email, nurse_assigned, shift_timing) 
                                VALUES (?,?,?,?,?)
                            """, (d_name, d_specialty, d_email, d_nurse, d_shift))
                            conn.commit()
                            st.success("Doctor Added!")
            
            with tab3:
                st.subheader("Book 20-Minute Appointment")
                
                patients_df = pd.read_sql_query("SELECT id, name FROM patients", conn)
                doctors_df = pd.read_sql_query("SELECT id, name, shift_timing FROM doctors", conn)
                
                if patients_df.empty:
                    st.warning("No patients registered yet")
                elif doctors_df.empty:
                    st.warning("No doctors available")
                else:
                    col1, col2 = st.columns(2)
                    with col1:
                        patient_name = st.selectbox("Select Patient", patients_df['name'].tolist())
                    with col2:
                        doctor_name = st.selectbox("Select Doctor", doctors_df['name'].tolist())
                    
                    selected_doctor = doctors_df[doctors_df['name'] == doctor_name].iloc[0]
                    available_slots = get_available_slots(selected_doctor['id'], selected_doctor['shift_timing'], today_str)
                    
                    if available_slots:
                        selected_time = st.selectbox("Available Time Slots", available_slots)
                        
                        if st.button("Book Appointment", use_container_width=True):
                            patient_id = patients_df[patients_df['name'] == patient_name]['id'].iloc[0]
                            conn.execute("""
                                INSERT INTO appointments (patient_id, doctor_id, appointment_date, appointment_time) 
                                VALUES (?,?,?,?)
                            """, (int(patient_id), int(selected_doctor['id']), today_str, selected_time))
                            conn.commit()
                            st.success(f"Appointment booked for {selected_time}!")
                            st.balloons()
                    else:
                        st.warning("No slots available today")
        
        elif nav == "View Appointments":
            st.title("📅 Today's Appointments")
            
            appointments_df = pd.read_sql_query("""
                SELECT p.name as Patient, d.name as Doctor, 
                       a.appointment_time as Time, a.status
                FROM appointments a
                JOIN patients p ON a.patient_id = p.id
                JOIN doctors d ON a.doctor_id = d.id
                WHERE a.appointment_date = ?
                ORDER BY a.appointment_time
            """, conn, params=(today_str,))
            
            if not appointments_df.empty:
                st.dataframe(appointments_df, use_container_width=True)
                
                # Cancellation option
                st.subheader("Cancel Appointment")
                appointment_times = appointments_df['Time'].tolist()
                if appointment_times:
                    cancel_time = st.selectbox("Select time to cancel", appointment_times)
                    if st.button("Cancel Selected Appointment"):
                        conn.execute("""
                            UPDATE appointments 
                            SET status='Cancelled' 
                            WHERE appointment_date=? AND appointment_time=?
                        """, (today_str, cancel_time))
                        conn.commit()
                        st.success("Appointment cancelled!")
                        st.rerun()
            else:
                st.info("No appointments scheduled for today")
    
    # ---------------- HOSPITAL STAFF ---------------- #
    elif st.session_state.role == "Hospital Staff":
        if nav == "Duty Board":
            st.title("👨‍⚕️ Staff Duty Board")
            
            # Doctors schedule
            doctors_df = pd.read_sql_query("""
                SELECT name as Doctor, specialty, nurse_assigned as Nurse, shift_timing as Shift 
                FROM doctors
            """, conn)
            
            if not doctors_df.empty:
                st.subheader("Doctor Schedule")
                st.dataframe(doctors_df, use_container_width=True)
            
            # Today's appointments
            st.subheader("Today's Appointment Schedule")
            appointments_df = pd.read_sql_query("""
                SELECT p.name as Patient, d.name as Doctor, 
                       a.appointment_time as Time, a.status
                FROM appointments a
                JOIN patients p ON a.patient_id = p.id
                JOIN doctors d ON a.doctor_id = d.id
                WHERE a.appointment_date = ?
                ORDER BY a.appointment_time
            """, conn, params=(today_str,))
            
            if not appointments_df.empty:
                st.dataframe(appointments_df, use_container_width=True)
            else:
                st.info("No appointments today")
        
        elif nav == "Room Status":
            st.title("🏥 Room Status Dashboard")
            
            rooms_df = pd.read_sql_query("SELECT * FROM rooms ORDER BY room_no", conn)
            
            col1, col2, col3 = st.columns(3)
            with col1:
                available = len(rooms_df[rooms_df['status'] == 'Available'])
                st.metric("Available Rooms", available)
            with col2:
                occupied = len(rooms_df[rooms_df['status'] == 'Occupied'])
                st.metric("Occupied Rooms", occupied)
            with col3:
                maintenance = len(rooms_df[rooms_df['status'] == 'Maintenance'])
                st.metric("Under Maintenance", maintenance)
            
            st.divider()
            
            # Room grid
            cols = st.columns(3)
            for idx, row in rooms_df.iterrows():
                with cols[idx % 3]:
                    if row['status'] == 'Available':
                        st.success(f"🏥 {row['room_no']}\n\nAvailable")
                    elif row['status'] == 'Occupied':
                        st.error(f"🏥 {row['room_no']}\n\nOccupied")
                    else:
                        st.warning(f"🏥 {row['room_no']}\n\nMaintenance")
    
    # ---------------- DOCTOR ---------------- #
    elif st.session_state.role == "Doctor":
        if nav == "Patient Queries":
            st.title("📨 Patient Queries")
            
            # Get doctor ID from email
            doctor = conn.execute("SELECT id FROM doctors WHERE email=?", (st.session_state.user_email,)).fetchone()
            
            if doctor:
                doctor_id = doctor[0]
                queries_df = pd.read_sql_query("""
                    SELECT q.*, p.name as patient_name 
                    FROM queries q
                    JOIN patients p ON q.patient_email = p.email
                    WHERE (q.recipient_type='Doctor' AND q.doctor_id=?) 
                       OR q.recipient_type='Hospital Staff'
                       AND q.status='Pending'
                    ORDER BY q.created_at DESC
                """, conn, params=(doctor_id,))
                
                if not queries_df.empty:
                    for idx, query in queries_df.iterrows():
                        with st.expander(f"Query from {query['patient_name']} - {query['created_at']}"):
                            st.write(f"**Question:** {query['query_text']}")
                            response = st.text_area("Your Response", key=f"dr_resp_{idx}")
                            if st.button("Send Response", key=f"dr_btn_{idx}"):
                                conn.execute("""
                                    UPDATE queries 
                                    SET response=?, status='Answered' 
                                    WHERE id=?
                                """, (response, query['id']))
                                conn.commit()
                                st.success("Response sent!")
                                st.rerun()
                else:
                    st.info("No pending queries")
            else:
                st.warning("Your doctor profile is not fully set up. Please contact admin.")
        
        elif nav == "My Schedule":
            st.title("📅 My Schedule")
            
            doctor = conn.execute("SELECT id, name FROM doctors WHERE email=?", (st.session_state.user_email,)).fetchone()
            
            if doctor:
                doctor_id, doctor_name = doctor
                
                # Today's appointments
                st.subheader(f"Today's Appointments - Dr. {doctor_name}")
                today_appts = pd.read_sql_query("""
                    SELECT p.name as Patient, a.appointment_time as Time, a.status
                    FROM appointments a
                    JOIN patients p ON a.patient_id = p.id
                    WHERE a.doctor_id=? AND a.appointment_date=?
                    ORDER BY a.appointment_time
                """, conn, params=(doctor_id, today_str))
                
                if not today_appts.empty:
                    st.dataframe(today_appts, use_container_width=True)
                else:
                    st.info("No appointments today")
                
                # Upcoming appointments
                st.subheader("Upcoming Appointments")
                upcoming_appts = pd.read_sql_query("""
                    SELECT p.name as Patient, a.appointment_date as Date, 
                           a.appointment_time as Time, a.status
                    FROM appointments a
                    JOIN patients p ON a.patient_id = p.id
                    WHERE a.doctor_id=? AND a.appointment_date > ?
                    ORDER BY a.appointment_date, a.appointment_time
                    LIMIT 10
                """, conn, params=(doctor_id, today_str))
                
                if not upcoming_appts.empty:
                    st.dataframe(upcoming_appts, use_container_width=True)
                else:
                    st.info("No upcoming appointments")
        
        elif nav == "My Patients":
            st.title("👥 My Patients")
            
            doctor = conn.execute("SELECT id FROM doctors WHERE email=?", (st.session_state.user_email,)).fetchone()
            
            if doctor:
                doctor_id = doctor[0]
                patients_df = pd.read_sql_query("""
                    SELECT DISTINCT p.name, p.age, p.blood_group, p.reason, p.visit_date
                    FROM patients p
                    JOIN appointments a ON p.id = a.patient_id
                    WHERE a.doctor_id=?
                    ORDER BY a.appointment_date DESC
                """, conn, params=(doctor_id,))
                
                if not patients_df.empty:
                    st.dataframe(patients_df, use_container_width=True)
                else:
                    st.info("No patients yet")
    
    # ---------------- PATIENT ---------------- #
    else:  # Patient role
        patient_id = get_patient_id_by_email(st.session_state.user_email)
        
        if nav == "Patient Portal":
            st.title("👤 My Health Portal")
            
            if patient_id:
                # Patient info
                patient_info = conn.execute("""
                    SELECT * FROM patients WHERE id=?
                """, (patient_id,)).fetchone()
                
                if patient_info:
                    col1, col2 = st.columns(2)
                    with col1:
                        st.subheader("Personal Information")
                        st.write(f"**Name:** {patient_info[1]}")
                        st.write(f"**Age:** {patient_info[2]}")
                        st.write(f"**Blood Group:** {patient_info[3]}")
                        st.write(f"**Email:** {patient_info[7]}")
                    
                    with col2:
                        st.subheader("Recent Visit")
                        st.write(f"**Reason:** {patient_info[4]}")
                        st.write(f"**Amount Paid:** ₹{patient_info[5]:,.2f}")
                        st.write(f"**Visit Date:** {patient_info[6]}")
        
        elif nav == "My Appointments":
            st.title("📅 My Appointments")
            
            if patient_id:
                appointments_df = pd.read_sql_query("""
                    SELECT d.name as Doctor, a.appointment_date as Date, 
                           a.appointment_time as Time, a.status
                    FROM appointments a
                    JOIN doctors d ON a.doctor_id = d.id
                    WHERE a.patient_id=?
                    ORDER BY a.appointment_date DESC, a.appointment_time DESC
                """, conn, params=(patient_id,))
                
                if not appointments_df.empty:
                    st.dataframe(appointments_df, use_container_width=True)
                else:
                    st.info("No appointments found")
        
        elif nav == "Ask Question":
            st.title("❓ Ask a Question")
            
            if patient_id:
                with st.form("ask_query"):
                    st.subheader("Submit your query")
                    
                    recipient = st.radio("Ask to:", ["Doctor", "Hospital Staff"])
                    
                    doctor_id = None
                    if recipient == "Doctor":
                        doctors_df = pd.read_sql_query("SELECT id, name FROM doctors", conn)
                        if not doctors_df.empty:
                            doctor_name = st.selectbox("Select Doctor", doctors_df['name'].tolist())
                            doctor_id = doctors_df[doctors_df['name'] == doctor_name]['id'].iloc[0]
                        else:
                            st.warning("No doctors available")
                    
                    query_text = st.text_area("Your Question", height=150)
                    
                    if st.form_submit_button("Submit Question"):
                        if query_text:
                            conn.execute("""
                                INSERT INTO queries (patient_email, recipient_type, doctor_id, query_text, created_at) 
                                VALUES (?,?,?,?,?)
                            """, (st.session_state.user_email, recipient, doctor_id, query_text, today_str))
                            conn.commit()
                            st.success("Your question has been submitted!")
                            st.balloons()
                        else:
                            st.error("Please enter your question")
                
                # Show previous queries and responses
                st.divider()
                st.subheader("My Previous Queries")
                
                previous_queries = pd.read_sql_query("""
                    SELECT recipient_type, query_text, response, status, created_at
                    FROM queries
                    WHERE patient_email=?
                    ORDER BY created_at DESC
                """, conn, params=(st.session_state.user_email,))
                
                if not previous_queries.empty:
                    for _, q in previous_queries.iterrows():
                        with st.expander(f"{q['created_at']} - {q['status']}"):
                            st.write(f"**Question:** {q['query_text']}")
                            if q['response']:
                                st.write(f"**Response:** {q['response']}")
                            else:
                                st.info("Awaiting response")
                else:
                    st.info("No previous queries")
    
    conn.close()
