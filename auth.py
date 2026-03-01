import streamlit as st
import bcrypt
import re
from database import get_connection

def login_register():

    st.title("🏥 MediVista Hospital Portal")

    mode = st.radio("Select Option", ["Login", "Register"], horizontal=True)
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if mode == "Register":
        role = st.selectbox("Role",
                            ["Admin", "Receptionist", "Hospital Staff",
                             "Doctor", "Patient"])

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
                                 (email, hashed, role))
                    conn.commit()
                    st.success("Account Created")
                except:
                    st.error("User exists")
                conn.close()

    if mode == "Login":
        if st.button("Login"):
            conn = get_connection()
            user = conn.execute(
                "SELECT password, role FROM users WHERE email=?",
                (email,)
            ).fetchone()
            conn.close()

            if user and bcrypt.checkpw(password.encode(), user[0]):
                st.session_state.logged_in = True
                st.session_state.role = user[1]
                st.session_state.email = email
                st.rerun()
            else:
                st.error("Invalid Credentials")
