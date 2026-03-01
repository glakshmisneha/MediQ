import streamlit as st
import pandas as pd
from database import get_connection
from datetime import datetime

def patient_panel():

    conn = get_connection()

    nav = st.sidebar.radio("Patient Menu",
                           ["My Appointments", "Submit Query"])

    if nav == "My Appointments":
        st.dataframe(pd.read_sql_query("""
            SELECT * FROM appointments
        """, conn))

    if nav == "Submit Query":
        doctors = pd.read_sql_query("SELECT name FROM doctors", conn)
        doc = st.selectbox("Doctor", doctors["name"])
        qtype = st.radio("Query Type",
                         ["Doctor Only", "Hospital + Doctor"])
        text = st.text_area("Query")

        if st.button("Submit"):
            conn.execute("""
                INSERT INTO queries
                (patient_email,doctor_name,query_text,query_type,created_at)
                VALUES(?,?,?,?,?)
            """, (st.session_state.email,
                  doc, text, qtype,
                  datetime.now().strftime("%Y-%m-%d %H:%M")))
            conn.commit()
            st.success("Query Submitted")

    conn.close()
