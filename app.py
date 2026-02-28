import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import re
import hashlib
from datetime import datetime

# ================= DATABASE ================= #

def connect_db():
    return sqlite3.connect("mediq.db", check_same_thread=False)

def init_db():
    conn = connect_db()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        email TEXT PRIMARY KEY,
        password TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS doctors(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        specialty TEXT,
        total_slots INTEGER DEFAULT 0,
        booked_slots INTEGER DEFAULT 0
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS patients(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        age INTEGER,
        blood_group TEXT,
        reason TEXT,
        amount_paid REAL DEFAULT 0,
        visit_date TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS appointments(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER,
        doctor_id INTEGER,
        appointment_date TEXT
    )
    """)

    conn.commit()
    conn.close()

init_db()

# ================= VALIDATION ================= #

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def strong_password(password):
    return (len(password) >= 8 and
            re.search(r"[A-Z]", password) and
            re.search(r"[a-z]", password) and
            re.search(r"[0-9]", password) and
            re.search(r"[!@#$%^&*]", password))

def valid_gmail(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@gmail\.com$'
    return re.match(pattern, email)

# ================= PAGE CONFIG ================= #

st.set_page_config(page_title="MediQ", layout="wide")

st.markdown("""
<style>
.stApp {
    background: linear-gradient(135deg,#0f2027,#203a43,#2c5364);
    color: white;
}
div.stButton > button {
    background: #00c6ff;
    color: white;
    border-radius: 20px;
    font-weight: bold;
}
section[data-testid="stSidebar"] {
    background-color: #111;
}
</style>
""", unsafe_allow_html=True)

# ================= SESSION ================= #

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# ================= AUTH ================= #

if not st.session_state.logged_in:

    st.title("MediQ")
    st.subheader("Smart Hospital Management & Analytics Portal")

    mode = st.radio("Select Option", ["Login", "Register"], horizontal=True)

    email = st.text_input("Gmail Address")
    password = st.text_input("Password", type="password")

    conn = connect_db()
    c = conn.cursor()

    if mode == "Register":
        if st.button("Create Account"):

            if not valid_gmail(email):
                st.error("Enter valid Gmail (example@gmail.com)")
            
            elif not strong_password(password):
                st.error(
                    "Password must contain:\n"
                    "• Minimum 8 characters\n"
                    "• One uppercase letter\n"
                    "• One lowercase letter\n"
                    "• One number\n"
                    "• One special character (!@#$%^&*)"
                )
            else:
                try:
                    c.execute("INSERT INTO users VALUES (?,?)",
                              (email, hash_password(password)))
                    conn.commit()
                    st.success("Account created successfully. Please Login.")
                except:
                    st.error("Email already registered.")

    if mode == "Login":
        if st.button("Login"):

            if not valid_gmail(email):
                st.error("Enter valid Gmail format")
            else:
                c.execute("SELECT * FROM users WHERE email=? AND password=?",
                          (email, hash_password(password)))
                if c.fetchone():
                    st.session_state.logged_in = True
                    st.rerun()
                else:
                    st.error("Invalid credentials")

    conn.close()

# ================= MAIN APP ================= #

else:

    st.sidebar.title("MediQ Admin Panel")
    page = st.sidebar.radio(
        "Navigation",
        ["Dashboard", "Doctors", "Patients", "Appointments"]
    )

    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()

    conn = connect_db()
    c = conn.cursor()

    # ---------------- DASHBOARD ---------------- #

    if page == "Dashboard":

        st.title("Hospital Dashboard")

        patients = pd.read_sql_query("SELECT * FROM patients", conn)
        doctors = pd.read_sql_query("SELECT * FROM doctors", conn)
        appointments = pd.read_sql_query("SELECT * FROM appointments", conn)

        total_visits = len(patients)
        total_revenue = patients["amount_paid"].sum() if not patients.empty else 0
        total_appointments = len(appointments)

        col1, col2, col3 = st.columns(3)
        col1.metric("Total Visits", total_visits)
        col2.metric("Total Revenue", f"₹ {total_revenue}")
        col3.metric("Total Appointments", total_appointments)

        if not patients.empty:
            fig = px.histogram(patients, x="reason",
                               title="Visits by Reason")
            st.plotly_chart(fig, use_container_width=True)

        if not doctors.empty:
            doctors["vacancies"] = doctors["total_slots"] - doctors["booked_slots"]
            fig2 = px.bar(doctors,
                          x="name",
                          y="booked_slots",
                          title="Doctor Workload Distribution")
            st.plotly_chart(fig2, use_container_width=True)

    # ---------------- DOCTORS ---------------- #

    elif page == "Doctors":

        st.title("Doctors Management")

        with st.form("add_doc"):
            name = st.text_input("Doctor Name")
            specialty = st.text_input("Specialty")
            slots = st.number_input("Total Slots", 0, 100)
            if st.form_submit_button("Add Doctor"):
                c.execute("INSERT INTO doctors (name,specialty,total_slots,booked_slots) VALUES (?,?,?,0)",
                          (name, specialty, slots))
                conn.commit()
                st.success("Doctor Added")
                st.rerun()

        st.dataframe(pd.read_sql_query("SELECT * FROM doctors", conn))

    # ---------------- PATIENTS ---------------- #

    elif page == "Patients":

        st.title("Patient Management")

        with st.form("add_patient"):
            name = st.text_input("Name")
            age = st.number_input("Age", 0, 120)
            blood = st.selectbox("Blood Group",
                                 ["A+","A-","B+","B-","O+","O-","AB+","AB-"])
            reason = st.text_input("Reason for Visit")
            payment = st.number_input("Payment Paid", 0.0)
            if st.form_submit_button("Add Patient"):
                c.execute("""
                    INSERT INTO patients
                    (name,age,blood_group,reason,amount_paid,visit_date)
                    VALUES (?,?,?,?,?,?)
                """, (name, age, blood, reason,
                      payment, datetime.now().strftime("%Y-%m-%d")))
                conn.commit()
                st.success("Patient Added")
                st.rerun()

        st.dataframe(pd.read_sql_query("SELECT * FROM patients", conn))

    # ---------------- APPOINTMENTS ---------------- #

    elif page == "Appointments":

        st.title("Appointment Booking")

        patients = pd.read_sql_query("SELECT id,name FROM patients", conn)
        doctors = pd.read_sql_query("SELECT id,name,total_slots,booked_slots FROM doctors", conn)

        if not patients.empty and not doctors.empty:

            patient = st.selectbox("Select Patient", patients["name"])
            doctor = st.selectbox("Select Doctor", doctors["name"])

            if st.button("Book Appointment"):

                doc = doctors[doctors["name"] == doctor].iloc[0]

                if doc["booked_slots"] < doc["total_slots"]:

                    pid = patients[patients["name"] == patient]["id"].iloc[0]
                    did = doc["id"]

                    c.execute("INSERT INTO appointments (patient_id,doctor_id,appointment_date) VALUES (?,?,?)",
                              (pid, did, datetime.now().strftime("%Y-%m-%d")))

                    c.execute("UPDATE doctors SET booked_slots = booked_slots + 1 WHERE id=?",
                              (did,))

                    conn.commit()
                    st.success("Appointment Booked")
                    st.rerun()
                else:
                    st.error("No slots available")

        st.dataframe(pd.read_sql_query("SELECT * FROM appointments", conn))

    conn.close()
