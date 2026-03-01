import streamlit as st
import pandas as pd
from database import get_connection

def doctor_panel():

    conn = get_connection()

    nav = st.sidebar.radio("Doctor Menu",
                           ["My Schedule", "Patient Queries"])

    if nav == "My Schedule":
        schedule = pd.read_sql_query("""
            SELECT p.name,a.appointment_time
            FROM appointments a
            JOIN patients p ON a.patient_id=p.id
        """, conn)
        st.dataframe(schedule)

    if nav == "Patient Queries":
        queries = pd.read_sql_query("""
            SELECT * FROM queries
            WHERE query_type IN ('Doctor Only','Hospital + Doctor')
        """, conn)
        st.dataframe(queries)

    conn.close()
