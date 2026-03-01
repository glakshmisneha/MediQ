import streamlit as st
import sqlite3
import pandas as pd
import bcrypt
import re
from datetime import datetime, timedelta
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4

st.set_page_config(page_title="MediVista Hospital", layout="wide")

DB_NAME = "medivista.db"

# ---------------- DATABASE ---------------- #
def get_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS users(
        email TEXT PRIMARY KEY,
        password BLOB,
        role TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS specialties(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS doctors(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        specialty_id INTEGER,
        total_slots INTEGER,
        nurse_assigned TEXT,
        shift_timing TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS patients(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        age INTEGER,
        blood_group TEXT,
        reason TEXT,
        amount_paid REAL,
        visit_date TEXT,
        email TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS appointments(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER,
        doctor_id INTEGER,
        appointment_date TEXT,
        appointment_time TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS rooms(
        room_no TEXT PRIMARY KEY,
        type TEXT,
        status TEXT DEFAULT 'Available'
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS queries(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_email TEXT,
        doctor_name TEXT,
        query_text TEXT,
        query_type TEXT,
        status TEXT DEFAULT 'Pending',
        created_at TEXT
    )""")

    conn.commit()
    conn.close()

init_db()

# ---------------- HELPERS ---------------- #
def check_password(password, hashed):
    if isinstance(hashed, memoryview):
        hashed = hashed.tobytes()
    return bcrypt.checkpw(password.encode(), hashed)

def get_available_slots(doctor_id, shift_str, date_str):
    try:
        start, end = shift_str.split(" - ")
        start_dt = datetime.strptime(start, "%H:%M")
        end_dt = datetime.strptime(end, "%H:%M")
    except:
        return []

    slots = []
    current = start_dt
    while current + timedelta(minutes=20) <= end_dt:
        slots.append(current.strftime("%H:%M"))
        current += timedelta(minutes=20)

    conn = get_connection()
    booked = pd.read_sql_query(
        "SELECT appointment_time FROM appointments WHERE doctor_id=? AND appointment_date=?",
        conn,
        params=(doctor_id, date_str)
    )
    conn.close()

    return [s for s in slots if s not in booked["appointment_time"].tolist()]

# ---------------- SESSION ---------------- #
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# ---------------- AUTH ---------------- #
if not st.session_state.logged_in:

    st.title("🏥 MediVista Hospital Portal")

    mode = st.radio("Select Option", ["Login", "Register"], horizontal=True)
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if mode == "Register":
        role = st.selectbox("Role", ["Admin", "Receptionist", "Hospital Staff", "Doctor", "Patient"])
        if st.button("Create Account"):
            if not re.match(r"^[a-zA-Z0-9._%+-]+@gmail\.com$", email):
                st.error("Use valid Gmail")
            elif len(password) < 8:
                st.error("Password must be 8+ characters")
            else:
                conn = get_connection()
                hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
                try:
                    conn.execute("INSERT INTO users VALUES (?,?,?)",
                                 (email, sqlite3.Binary(hashed), role))
                    conn.commit()
                    st.success("Account Created")
                except:
                    st.error("User already exists")
                conn.close()

    if mode == "Login":
        if st.button("Login"):
            conn = get_connection()
            user = conn.execute(
                "SELECT password, role FROM users WHERE email=?",
                (email,)
            ).fetchone()
            conn.close()

            if user and check_password(password, user[0]):
                st.session_state.logged_in = True
                st.session_state.role = user[1]
                st.session_state.email = email
                st.rerun()
            else:
                st.error("Invalid Credentials")

# ---------------- MAIN APP ---------------- #
else:

    conn = get_connection()
    role = st.session_state.role
    today = datetime.now().strftime("%Y-%m-%d")

    st.sidebar.title("MediVista")

    if role == "Admin":
        nav = st.sidebar.radio("Menu",
            ["Dashboard","Patient Details","Specialties","Doctors",
             "Rooms","Reports","Manage Queries"])
    elif role == "Receptionist":
        nav = st.sidebar.radio("Menu",
            ["Register Patient","Book Appointment"])
    elif role == "Doctor":
        nav = st.sidebar.radio("Menu",
            ["My Schedule","Patient Queries"])
    elif role == "Hospital Staff":
        nav = st.sidebar.radio("Menu",["Duty Board"])
    else:
        nav = st.sidebar.radio("Menu",
            ["My Appointments","Submit Query"])

    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()

    # ---------------- ADMIN ---------------- #
    if role == "Admin":

        if nav == "Dashboard":
            st.title("📊 Dashboard")
            patients = pd.read_sql_query("SELECT * FROM patients", conn)
            appointments = pd.read_sql_query("SELECT * FROM appointments", conn)
            col1,col2,col3 = st.columns(3)
            col1.metric("Total Patients", len(patients))
            col2.metric("Total Revenue",
                        f"₹ {patients['amount_paid'].sum() if not patients.empty else 0}")
            col3.metric("Total Appointments", len(appointments))

        if nav == "Patient Details":
            st.title("🧑 Patient Details")
            st.dataframe(pd.read_sql_query(
                "SELECT * FROM patients ORDER BY visit_date DESC", conn),
                use_container_width=True)

        if nav == "Specialties":
            st.title("🏷 Manage Specialties")
            with st.form("add_specialty"):
                spec = st.text_input("New Specialty")
                if st.form_submit_button("Add"):
                    try:
                        conn.execute("INSERT INTO specialties(name) VALUES(?)",(spec,))
                        conn.commit()
                        st.success("Specialty Added")
                        st.rerun()
                    except:
                        st.error("Specialty exists")
            st.dataframe(pd.read_sql_query("SELECT * FROM specialties",conn),
                         use_container_width=True)

        if nav == "Doctors":
            st.title("👨‍⚕️ Doctor Management")
            specialties = pd.read_sql_query("SELECT * FROM specialties", conn)

            with st.form("add_doc"):
                name = st.text_input("Doctor Name")
                spec = st.selectbox("Specialty",
                                    specialties["name"] if not specialties.empty else [])
                slots = st.number_input("Total Slots",1,50,10)
                nurse = st.text_input("Assigned Nurse")
                start = st.time_input("Shift Start")
                end = st.time_input("Shift End")

                if st.form_submit_button("Add Doctor"):
                    if start >= end:
                        st.warning("Invalid shift timing")
                    else:
                        shift = f"{start.strftime('%H:%M')} - {end.strftime('%H:%M')}"
                        spec_id = specialties[specialties["name"]==spec]["id"].iloc[0]
                        try:
                            conn.execute("""
                                INSERT INTO doctors
                                (name,specialty_id,total_slots,nurse_assigned,shift_timing)
                                VALUES(?,?,?,?,?)
                            """,(name,spec_id,slots,nurse,shift))
                            conn.commit()
                            st.success("Doctor Added")
                            st.rerun()
                        except:
                            st.error("Doctor exists")

            st.dataframe(pd.read_sql_query("""
                SELECT d.id,d.name,s.name as specialty,
                       d.total_slots,d.nurse_assigned,d.shift_timing
                FROM doctors d
                JOIN specialties s ON d.specialty_id=s.id
            """,conn),use_container_width=True)

        if nav == "Rooms":
            st.title("🛏 Room Management")
            with st.form("room_form"):
                room_no = st.text_input("Room No")
                rtype = st.selectbox("Type",["General","ICU","Private"])
                if st.form_submit_button("Add Room"):
                    try:
                        conn.execute("INSERT INTO rooms(room_no,type) VALUES(?,?)",
                                     (room_no,rtype))
                        conn.commit()
                        st.success("Room Added")
                    except:
                        st.error("Room exists")
            st.dataframe(pd.read_sql_query("SELECT * FROM rooms",conn))

        if nav == "Reports":
            st.title("📄 Patient Report")
            if st.button("Generate PDF"):
                patients = pd.read_sql_query("SELECT * FROM patients", conn)
                doc = SimpleDocTemplate("patient_report.pdf", pagesize=A4)
                styles = getSampleStyleSheet()
                elements = []
                for _,row in patients.iterrows():
                    elements.append(Paragraph(
                        f"{row['name']} | ₹{row['amount_paid']}",
                        styles["Normal"]))
                    elements.append(Spacer(1,12))
                doc.build(elements)
                with open("patient_report.pdf","rb") as f:
                    st.download_button("Download Report",f,"patient_report.pdf")

        if nav == "Manage Queries":
            st.title("📩 Query Management")
            filter_status = st.selectbox("Filter",["All","Pending","Resolved"])
            if filter_status=="All":
                queries = pd.read_sql_query("SELECT * FROM queries",conn)
            else:
                queries = pd.read_sql_query(
                    "SELECT * FROM queries WHERE status=?",
                    conn,params=(filter_status,))
            st.dataframe(queries,use_container_width=True)

            pending = pd.read_sql_query(
                "SELECT id FROM queries WHERE status='Pending'",conn)
            if not pending.empty:
                qid = st.selectbox("Select Query ID",pending["id"])
                if st.button("Mark as Resolved"):
                    conn.execute("UPDATE queries SET status='Resolved' WHERE id=?",
                                 (qid,))
                    conn.commit()
                    st.success("Resolved")
                    st.rerun()

    # ---------------- RECEPTIONIST ---------------- #
    if role=="Receptionist":

        if nav=="Register Patient":
            st.title("Register Patient")
            with st.form("patient_form"):
                name=st.text_input("Name")
                age=st.number_input("Age",1,120)
                blood=st.text_input("Blood Group")
                reason=st.text_input("Reason")
                pay=st.number_input("Amount Paid")
                if st.form_submit_button("Register"):
                    conn.execute("""
                        INSERT INTO patients
                        (name,age,blood_group,reason,amount_paid,visit_date,email)
                        VALUES(?,?,?,?,?,?,?)
                    """,(name,age,blood,reason,pay,today,
                         name.lower().replace(" ","")+"@gmail.com"))
                    conn.commit()
                    st.success("Patient Registered")

        if nav=="Book Appointment":
            st.title("Book Appointment")
            patients=pd.read_sql_query("SELECT id,name FROM patients",conn)
            doctors=pd.read_sql_query("SELECT * FROM doctors",conn)
            if not patients.empty and not doctors.empty:
                pname=st.selectbox("Patient",patients["name"])
                dname=st.selectbox("Doctor",doctors["name"])
                doctor=doctors[doctors["name"]==dname].iloc[0]
                slots=get_available_slots(doctor["id"],
                                          doctor["shift_timing"],
                                          today)
                if slots:
                    selected=st.selectbox("Available Slots",slots)
                    if st.button("Confirm Appointment"):
                        pid=patients[patients["name"]==pname]["id"].iloc[0]
                        conn.execute("""
                            INSERT INTO appointments
                            (patient_id,doctor_id,appointment_date,appointment_time)
                            VALUES(?,?,?,?)
                        """,(pid,doctor["id"],today,selected))
                        conn.commit()
                        st.success("Appointment Booked")
                else:
                    st.warning("No Slots Available")

    # ---------------- DOCTOR ---------------- #
    if role=="Doctor":

        if nav=="My Schedule":
            st.title("📅 My Schedule")
            st.dataframe(pd.read_sql_query("""
                SELECT p.name,a.appointment_time,a.appointment_date
                FROM appointments a
                JOIN patients p ON a.patient_id=p.id
            """,conn),use_container_width=True)

        if nav=="Patient Queries":
            st.title("📩 Patient Queries")
            st.dataframe(pd.read_sql_query("""
                SELECT patient_email,query_text,query_type,status,created_at
                FROM queries
                WHERE query_type IN ('Doctor Only','Hospital + Doctor')
            """,conn),use_container_width=True)

    # ---------------- STAFF ---------------- #
    if role=="Hospital Staff":
        st.title("🏥 Duty Board")
        st.dataframe(pd.read_sql_query("""
            SELECT d.name,s.name as specialty,
                   d.nurse_assigned,d.shift_timing
            FROM doctors d
            JOIN specialties s ON d.specialty_id=s.id
        """,conn),use_container_width=True)

    # ---------------- PATIENT ---------------- #
    if role=="Patient":

        if nav=="My Appointments":
            st.title("My Appointments")
            st.dataframe(pd.read_sql_query("""
                SELECT d.name,a.appointment_time,a.appointment_date
                FROM appointments a
                JOIN doctors d ON a.doctor_id=d.id
            """,conn),use_container_width=True)

        if nav=="Submit Query":
            st.title("Submit Query")
            doctors=pd.read_sql_query("SELECT name FROM doctors",conn)
            qtype=st.radio("Query For",
                           ["Doctor Only","Hospital + Doctor"])
            selected_doc=st.selectbox("Doctor",
                                      doctors["name"] if not doctors.empty else [])
            qtext=st.text_area("Enter Query")
            if st.button("Submit"):
                conn.execute("""
                    INSERT INTO queries
                    (patient_email,doctor_name,query_text,query_type,created_at)
                    VALUES(?,?,?,?,?)
                """,(st.session_state.email,
                     selected_doc,qtext,qtype,
                     datetime.now().strftime("%Y-%m-%d %H:%M")))
                conn.commit()
                st.success("Query Submitted")

            st.subheader("My Queries")
            st.dataframe(pd.read_sql_query("""
                SELECT doctor_name,query_text,status,created_at
                FROM queries
                WHERE patient_email=?
            """,conn,params=(st.session_state.email,)),
            use_container_width=True)

    conn.close()
