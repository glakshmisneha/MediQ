import streamlit as st
import pandas as pd
from database import get_connection
from datetime import datetime

def receptionist_panel():

    conn = get_connection()

    nav = st.sidebar.radio("Reception Menu",
                           ["Register Patient", "Book Appointment"])

    # Register Patient
    if nav == "Register Patient":
        with st.form("patient"):
            name = st.text_input("Name")
            age = st.number_input("Age", 1, 120)
            blood = st.selectbox("Blood Group",
                                 ["A+","A-","B+","B-",
                                  "O+","O-","AB+","AB-"])
            reason = st.text_input("Reason")
            pay = st.number_input("Amount Paid")

            if st.form_submit_button("Register"):
                conn.execute("""
                    INSERT INTO patients
                    (name,age,blood_group,reason,amount_paid,visit_date,email)
                    VALUES(?,?,?,?,?,?,?)
                """, (name, age, blood, reason,
                      pay, datetime.now().strftime("%Y-%m-%d"),
                      name.lower()+"@gmail.com"))
                conn.commit()
                st.success("Patient Registered")

    # Book Appointment (FIXED)
    if nav == "Book Appointment":
        patients = pd.read_sql_query("SELECT id,name FROM patients", conn)
        doctors = pd.read_sql_query("SELECT id,name FROM doctors", conn)

        if not patients.empty and not doctors.empty:
            p = st.selectbox("Patient", patients["name"])
            d = st.selectbox("Doctor", doctors["name"])
            time = st.text_input("Time (HH:MM)")

            if st.button("Book"):
                pid = patients[patients["name"] == p]["id"].iloc[0]
                did = doctors[doctors["name"] == d]["id"].iloc[0]

                conn.execute("""
                    INSERT INTO appointments
                    (patient_id,doctor_id,appointment_date,appointment_time)
                    VALUES(?,?,?,?)
                """, (pid, did,
                      datetime.now().strftime("%Y-%m-%d"),
                      time))
                conn.commit()
                st.success("Appointment Booked")

    conn.close()
