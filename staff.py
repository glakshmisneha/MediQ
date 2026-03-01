import streamlit as st
import pandas as pd
from database import get_connection

def staff_panel():
    conn = get_connection()
    st.dataframe(pd.read_sql_query("""
        SELECT d.name,s.name as specialty,
               d.nurse_assigned,d.shift_timing
        FROM doctors d
        LEFT JOIN specialties s ON d.specialty_id=s.id
    """, conn))
    conn.close()
