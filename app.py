import streamlit as st
from database import init_db
from auth import login_register
from admin import admin_panel
from receptionist import receptionist_panel
from doctor import doctor_panel
from patient import patient_panel
from staff import staff_panel

init_db()

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    login_register()
else:
    role = st.session_state.role

    if role == "Admin":
        admin_panel()
    elif role == "Receptionist":
        receptionist_panel()
    elif role == "Doctor":
        doctor_panel()
    elif role == "Hospital Staff":
        staff_panel()
    elif role == "Patient":
        patient_panel()

    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()
