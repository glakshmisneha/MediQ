import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import re
import bcrypt
from datetime import datetime
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
import os

# ================= DATABASE ================= #

DB_NAME = "mediq.db"

def connect_db():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = connect_db()
    c = conn.cursor()

    # Create users table if not exists (without assuming role column)
    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        email TEXT PRIMARY KEY,
        password BLOB
    )
    """)

    # Check if 'role' column exists
    c.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in c.fetchall()]

    if "role" not in columns:
        c.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'Receptionist'")

    # Doctors table
    c.execute("""
    CREATE TABLE IF NOT EXISTS doctors(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        specialty TEXT,
        total_slots INTEGER,
        booked_slots INTEGER DEFAULT 0
    )
    """)

    # Patients table
    c.execute("""
    CREATE TABLE IF NOT EXISTS patients(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        age INTEGER,
        blood_group TEXT,
        reason TEXT,
        amount_paid REAL,
        visit_date TEXT
    )
    """)

    # Appointments table
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

# ================= SECURITY ================= #

def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt())

def check_password(password, hashed):
    return bcrypt.checkpw(password.encode(), hashed)

def strong_password(password):
    return (len(password) >= 8 and
            re.search(r"[A-Z]", password) and
            re.search(r"[a-z]", password) and
            re.search(r"[0-9]", password))

# ================= CONFIG ================= #

st.set_page_config(page_title="MediQ", layout="wide")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "role" not in st.session_state:
    st.session_state.role = None

# ================= AUTH ================= #

if not st.session_state.logged_in:

    st.title("🏥 MediQ")
    st.subheader("Smart Hospital Management System")

    mode = st.radio("Select Option", ["Login", "Register"], horizontal=True)

    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    conn = connect_db()
    c = conn.cursor()

    if mode == "Register":
        role = st.selectbox("Select Role", ["Admin", "Receptionist"])

        if st.button("Create Account"):
            if not strong_password(password):
                st.error("Password must contain uppercase, lowercase & number (min 8 chars)")
            else:
                hashed = hash_password(password)
                try:
                    c.execute("INSERT INTO users (email,password,role) VALUES (?,?,?)",
                              (email, sqlite3.Binary(hashed), role))
                    conn.commit()
                    st.success("Account Created Successfully")
                except:
                    st.error("User already exists")

    if mode == "Login":
        if st.button("Login"):
            c.execute("SELECT password, role FROM users WHERE email=?", (email,))
            result = c.fetchone()

            if result:
                stored_password, role = result
                if check_password(password, stored_password):
                    st.session_state.logged_in = True
                    st.session_state.role = role
                    st.rerun()
                else:
                    st.error("Invalid Credentials")
            else:
                st.error("User Not Found")

    conn.close()

# ================= MAIN APP ================= #

else:

    st.sidebar.title("MediQ Panel")
    st.sidebar.write(f"Logged in as: **{st.session_state.role}**")

    page = st.sidebar.radio(
        "Navigation",
        ["Dashboard", "Doctors", "Patients", "Appointments", "Reports"]
    )

    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.role = None
        st.rerun()

    conn = connect_db()
    c = conn.cursor()

    # ---------------- DASHBOARD ---------------- #

    if page == "Dashboard":

        patients = pd.read_sql_query("SELECT * FROM patients", conn)
        doctors = pd.read_sql_query("SELECT * FROM doctors", conn)

        col1, col2 = st.columns(2)
        col1.metric("Total Patients", len(patients))
        col2.metric("Total Doctors", len(doctors))

        if not doctors.empty:
            doctors["Available Slots"] = doctors["total_slots"] - doctors["booked_slots"]
            fig = px.bar(doctors, x="name", y="Available Slots",
                         title="Doctor Availability")
            st.plotly_chart(fig, use_container_width=True)

    # ---------------- DOCTORS ---------------- #

    elif page == "Doctors":

        if st.session_state.role == "Admin":
            st.subheader("Add Doctor")
            name = st.text_input("Name")
            specialty = st.text_input("Specialty")
            slots = st.number_input("Total Slots", 1, 100)

            if st.button("Add Doctor"):
                c.execute("INSERT INTO doctors (name,specialty,total_slots) VALUES (?,?,?)",
                          (name, specialty, slots))
                conn.commit()
                st.success("Doctor Added")
                st.rerun()

        st.subheader("Doctor List")
        doctors = pd.read_sql_query("SELECT * FROM doctors", conn)

        for _, row in doctors.iterrows():
            st.write(f"**{row['name']}** - {row['specialty']}")

            if st.session_state.role == "Admin":
                if st.button(f"Delete Doctor {row['id']}"):
                    c.execute("DELETE FROM doctors WHERE id=?", (row["id"],))
                    conn.commit()
                    st.rerun()

    # ---------------- PATIENTS ---------------- #

    elif page == "Patients":

        st.subheader("Add Patient")

        name = st.text_input("Name")
        age = st.number_input("Age", 0, 120)
        blood = st.text_input("Blood Group")
        reason = st.text_input("Reason")
        payment = st.number_input("Payment", 0.0)

        if st.button("Add Patient"):
            c.execute("""
                INSERT INTO patients (name,age,blood_group,reason,amount_paid,visit_date)
                VALUES (?,?,?,?,?,?)
            """, (name, age, blood, reason, payment,
                  datetime.now().strftime("%Y-%m-%d")))
            conn.commit()
            st.success("Patient Added")
            st.rerun()

        patients = pd.read_sql_query("SELECT * FROM patients", conn)
        st.dataframe(patients)

    # ---------------- APPOINTMENTS ---------------- #

    elif page == "Appointments":

        patients = pd.read_sql_query("SELECT id,name FROM patients", conn)
        doctors = pd.read_sql_query("SELECT * FROM doctors", conn)

        if not patients.empty and not doctors.empty:

            patient = st.selectbox("Patient", patients["name"])
            doctor = st.selectbox("Doctor", doctors["name"])

            if st.button("Book Appointment"):

                doc = doctors[doctors["name"] == doctor].iloc[0]

                if doc["booked_slots"] < doc["total_slots"]:

                    pid = patients[patients["name"] == patient]["id"].iloc[0]

                    c.execute("INSERT INTO appointments (patient_id,doctor_id,appointment_date) VALUES (?,?,?)",
                              (pid, doc["id"], datetime.now().strftime("%Y-%m-%d")))

                    c.execute("UPDATE doctors SET booked_slots = booked_slots + 1 WHERE id=?",
                              (doc["id"],))

                    conn.commit()
                    st.success("Appointment Booked")
                    st.rerun()
                else:
                    st.error("No Slots Available")

    # ---------------- REPORTS ---------------- #

    elif page == "Reports":

        if st.button("Generate Revenue PDF"):

            patients = pd.read_sql_query("SELECT * FROM patients", conn)
            total = patients["amount_paid"].sum()

            file_name = "MediQ_Report.pdf"
            doc = SimpleDocTemplate(file_name, pagesize=A4)
            elements = []

            style = ParagraphStyle(name='Normal', fontSize=12)

            elements.append(Paragraph("MediQ Revenue Report", style))
            elements.append(Spacer(1, 0.5 * inch))
            elements.append(Paragraph(f"Total Revenue: ₹{total}", style))

            doc.build(elements)

            with open(file_name, "rb") as f:
                st.download_button("Download Report", f, file_name=file_name)

    conn.close()
