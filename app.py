import streamlit as st
import sqlite3
import pandas as pd
import bcrypt
import re
from datetime import datetime
import plotly.express as px
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4

st.set_page_config(page_title="MediVista Hospital", layout="wide")

DB = "medivista.db"

# ---------------- DATABASE ---------------- #
def connect():
    return sqlite3.connect(DB, check_same_thread=False)

def init_db():
    conn = connect()
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS users(
        email TEXT PRIMARY KEY,
        password BLOB,
        role TEXT)""")

    c.execute("""CREATE TABLE IF NOT EXISTS specialties(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE)""")

    c.execute("""CREATE TABLE IF NOT EXISTS doctors(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        specialty_id INTEGER,
        total_slots INTEGER,
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
        email TEXT)""")

    c.execute("""CREATE TABLE IF NOT EXISTS appointments(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER,
        doctor_id INTEGER,
        appointment_date TEXT,
        appointment_time TEXT)""")

    c.execute("""CREATE TABLE IF NOT EXISTS queries(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_email TEXT,
        doctor_name TEXT,
        query_text TEXT,
        query_type TEXT,
        status TEXT DEFAULT 'Pending',
        created_at TEXT)""")

    conn.commit()
    conn.close()

init_db()

# ---------------- AUTH ---------------- #
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:

    st.title("🏥 MediVista Hospital Portal")
    mode = st.radio("Login / Register", ["Login", "Register"], horizontal=True)
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if mode == "Register":
        role = st.selectbox("Role", ["Admin","Receptionist","Doctor","Hospital Staff","Patient"])
        if st.button("Create Account"):
            if not re.match(r"^[\w\.-]+@gmail\.com$", email):
                st.error("Use valid Gmail")
            elif len(password) < 8:
                st.error("Password must be 8+ chars")
            else:
                conn = connect()
                hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
                try:
                    conn.execute("INSERT INTO users VALUES (?,?,?)",
                                 (email, hashed, role))
                    conn.commit()
                    st.success("Account Created")
                except:
                    st.error("User exists")
                conn.close()

    if mode == "Login":
        if st.button("Login"):
            conn = connect()
            user = conn.execute("SELECT password, role FROM users WHERE email=?",
                                (email,)).fetchone()
            conn.close()

            if user and bcrypt.checkpw(password.encode(), user[0]):
                st.session_state.logged_in = True
                st.session_state.role = user[1]
                st.session_state.email = email
                st.rerun()
            else:
                st.error("Invalid Credentials")

# ---------------- MAIN ---------------- #
else:

    role = st.session_state.role
    conn = connect()
    st.sidebar.title("MediVista")

    if role == "Admin":
        nav = st.sidebar.radio("Admin Menu",
            ["Dashboard","Patients","Specialties","Doctors",
             "Reports","Manage Queries"])
    elif role == "Receptionist":
        nav = st.sidebar.radio("Reception Menu",
            ["Register Patient","Book Appointment"])
    elif role == "Doctor":
        nav = st.sidebar.radio("Doctor Menu",
            ["My Schedule","Patient Queries"])
    elif role == "Hospital Staff":
        nav = st.sidebar.radio("Staff Menu",["Duty Board"])
    else:
        nav = st.sidebar.radio("Patient Menu",
            ["My Appointments","Submit Query"])

    # ---------------- ADMIN ---------------- #
    if role == "Admin":

        if nav == "Dashboard":
            st.title("📊 Hospital Dashboard")

            patients = pd.read_sql_query("SELECT * FROM patients", conn)
            appointments = pd.read_sql_query("SELECT * FROM appointments", conn)

            if not patients.empty:
                per_day = patients.groupby("visit_date").size().reset_index(name="Patients")
                fig1 = px.bar(per_day, x="visit_date", y="Patients",
                              title="Patients per Day")
                st.plotly_chart(fig1, use_container_width=True)

                revenue = patients.groupby("visit_date")["amount_paid"].sum().reset_index()
                fig2 = px.line(revenue, x="visit_date", y="amount_paid",
                               title="Revenue per Day")
                st.plotly_chart(fig2, use_container_width=True)

            if not appointments.empty:
                appt_day = appointments.groupby("appointment_date").size().reset_index(name="Appointments")
                fig3 = px.bar(appt_day, x="appointment_date", y="Appointments",
                              title="Appointments per Day")
                st.plotly_chart(fig3, use_container_width=True)

        if nav == "Patients":
            st.title("🧑 Patient Details")
            st.dataframe(pd.read_sql_query("SELECT * FROM patients", conn))

        if nav == "Specialties":
            st.title("🏷 Specialties")
            with st.form("spec"):
                name = st.text_input("Specialty")
                if st.form_submit_button("Add"):
                    try:
                        conn.execute("INSERT INTO specialties(name) VALUES(?)",(name,))
                        conn.commit()
                        st.success("Added")
                    except:
                        st.error("Exists")
            st.dataframe(pd.read_sql_query("SELECT * FROM specialties", conn))

        if nav == "Doctors":
            st.title("👨‍⚕️ Doctor Management")
            specialties = pd.read_sql_query("SELECT * FROM specialties", conn)

            with st.form("doc"):
                name = st.text_input("Name")
                email_doc = st.text_input("Email")
                spec = st.selectbox("Specialty",
                                    specialties["name"] if not specialties.empty else [])
                slots = st.number_input("Slots",1,50,10)
                nurse = st.text_input("Nurse")
                shift = st.text_input("Shift (08:00 - 16:00)")
                if st.form_submit_button("Add Doctor"):
                    if specialties.empty:
                        st.error("Add specialty first")
                    else:
                        spec_id = specialties[specialties["name"]==spec]["id"].iloc[0]
                        conn.execute("""INSERT INTO doctors
                            (name,email,specialty_id,total_slots,nurse_assigned,shift_timing)
                            VALUES(?,?,?,?,?,?)""",
                            (name,email_doc,spec_id,slots,nurse,shift))
                        conn.commit()
                        st.success("Doctor Added")

            st.dataframe(pd.read_sql_query("""
                SELECT d.name,d.email,s.name as specialty,
                       d.total_slots,d.nurse_assigned,d.shift_timing
                FROM doctors d
                LEFT JOIN specialties s ON d.specialty_id=s.id
            """,conn))

        if nav == "Reports":
            st.title("📄 Patient Report")
            if st.button("Generate PDF"):
                patients = pd.read_sql_query("SELECT * FROM patients", conn)
                doc = SimpleDocTemplate("report.pdf", pagesize=A4)
                styles = getSampleStyleSheet()
                elements = []
                for _, row in patients.iterrows():
                    elements.append(Paragraph(
                        f"{row['name']} - ₹{row['amount_paid']}",
                        styles["Normal"]))
                    elements.append(Spacer(1,12))
                doc.build(elements)
                with open("report.pdf","rb") as f:
                    st.download_button("Download Report", f, "report.pdf")

        if nav == "Manage Queries":
            st.title("📩 Manage Queries")
            queries = pd.read_sql_query("SELECT * FROM queries", conn)
            st.dataframe(queries)

            pending = queries[queries["status"]=="Pending"]
            if not pending.empty:
                qid = st.selectbox("Select ID to Resolve", pending["id"])
                if st.button("Resolve"):
                    conn.execute("UPDATE queries SET status='Resolved' WHERE id=?",(qid,))
                    conn.commit()
                    st.success("Resolved")

    # ---------------- RECEPTIONIST ---------------- #
    if role == "Receptionist":
        if nav == "Register Patient":
            st.title("Register Patient")
            with st.form("pat"):
                name = st.text_input("Name")
                age = st.number_input("Age",1,120)
                blood = st.selectbox("Blood Group",
                    ["A+","A-","B+","B-","O+","O-","AB+","AB-"])
                reason = st.text_input("Reason")
                pay = st.number_input("Amount Paid")
                if st.form_submit_button("Register"):
                    conn.execute("""INSERT INTO patients
                        (name,age,blood_group,reason,amount_paid,visit_date,email)
                        VALUES(?,?,?,?,?,?,?)""",
                        (name,age,blood,reason,pay,
                         datetime.now().strftime("%Y-%m-%d"),
                         name+"@gmail.com"))
                    conn.commit()
                    st.success("Registered")

        if nav == "Book Appointment":
            st.title("Book Appointment")
            patients = pd.read_sql_query("SELECT id,name FROM patients", conn)
            doctors = pd.read_sql_query("SELECT id,name FROM doctors", conn)
            if not patients.empty and not doctors.empty:
                p = st.selectbox("Patient", patients["name"])
                d = st.selectbox("Doctor", doctors["name"])
                time = st.text_input("Time (HH:MM)")
                if st.button("Book"):
                    pid = patients[patients["name"]==p]["id"].iloc[0]
                    did = doctors[doctors["name"]==d]["id"].iloc[0]
                    conn.execute("""INSERT INTO appointments
                        (patient_id,doctor_id,appointment_date,appointment_time)
                        VALUES(?,?,?,?)""",
                        (pid,did,
                         datetime.now().strftime("%Y-%m-%d"),
                         time))
                    conn.commit()
                    st.success("Booked")

    # ---------------- DOCTOR ---------------- #
    if role == "Doctor":
        if nav == "My Schedule":
            st.dataframe(pd.read_sql_query("""
                SELECT p.name,a.appointment_time
                FROM appointments a
                JOIN patients p ON a.patient_id=p.id
            """,conn))

        if nav == "Patient Queries":
            st.dataframe(pd.read_sql_query("""
                SELECT * FROM queries
                WHERE query_type IN ('Doctor Only','Hospital + Doctor')
            """,conn))

    # ---------------- PATIENT ---------------- #
    if role == "Patient":
        if nav == "My Appointments":
            st.dataframe(pd.read_sql_query("SELECT * FROM appointments",conn))

        if nav == "Submit Query":
            doctors = pd.read_sql_query("SELECT name FROM doctors",conn)
            doc = st.selectbox("Doctor", doctors["name"])
            qtype = st.radio("Type",["Doctor Only","Hospital + Doctor"])
            text = st.text_area("Query")
            if st.button("Submit"):
                conn.execute("""INSERT INTO queries
                    (patient_email,doctor_name,query_text,query_type,created_at)
                    VALUES(?,?,?,?,?)""",
                    (st.session_state.email,doc,text,qtype,
                     datetime.now().strftime("%Y-%m-%d %H:%M")))
                conn.commit()
                st.success("Submitted")

    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()

    conn.close()
