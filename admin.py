import streamlit as st
import pandas as pd
from database import get_connection

def admin_panel():

    conn = get_connection()

    nav = st.sidebar.radio("Admin Menu",
        ["Dashboard", "Specialties", "Doctors",
         "Patients", "Reports", "Manage Queries"])

    # Dashboard
    if nav == "Dashboard":
        patients = pd.read_sql_query("SELECT * FROM patients", conn)
        st.metric("Total Patients", len(patients))

    # Specialties
    if nav == "Specialties":
        with st.form("add_spec"):
            name = st.text_input("Specialty")
            if st.form_submit_button("Add"):
                try:
                    conn.execute("INSERT INTO specialties(name) VALUES(?)", (name,))
                    conn.commit()
                    st.success("Added")
                except:
                    st.error("Exists")

        st.dataframe(pd.read_sql_query("SELECT * FROM specialties", conn))

    # Doctors
    if nav == "Doctors":
        specialties = pd.read_sql_query("SELECT * FROM specialties", conn)

        with st.form("add_doc"):
            name = st.text_input("Doctor Name")
            email = st.text_input("Doctor Email")
            spec = st.selectbox("Specialty",
                                specialties["name"] if not specialties.empty else [])
            slots = st.number_input("Total Slots", 1, 50, 10)
            nurse = st.text_input("Nurse")
            shift = st.text_input("Shift (08:00 - 16:00)")

            if st.form_submit_button("Add Doctor"):
                spec_id = specialties[specialties["name"] == spec]["id"].iloc[0]
                conn.execute("""
                    INSERT INTO doctors
                    (name,email,specialty_id,total_slots,nurse_assigned,shift_timing)
                    VALUES(?,?,?,?,?,?)
                """, (name, email, spec_id, slots, nurse, shift))
                conn.commit()
                st.success("Doctor Added")

        st.dataframe(pd.read_sql_query("""
            SELECT d.name,d.email,s.name as specialty,
                   d.total_slots,d.nurse_assigned,d.shift_timing
            FROM doctors d
            LEFT JOIN specialties s ON d.specialty_id=s.id
        """, conn))

    conn.close()
