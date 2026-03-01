import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import bcrypt
import re
from datetime import datetime, timedelta

# 1. Page Configuration (2026 Streamlit Standards)
st.set_page_config(
    page_title="MediVista Management", 
    layout="wide", 
    initial_sidebar_state="expanded",
    page_icon="🏥"
)

DB_NAME = "mediq.db"

# ================= DATABASE INITIALIZATION & MIGRATIONS ================= #
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Create tables with proper schema
    c.execute("CREATE TABLE IF NOT EXISTS users(email TEXT PRIMARY KEY, password BLOB, role TEXT)")
    
    c.execute("""CREATE TABLE IF NOT EXISTS doctors(
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        name TEXT, 
        specialty TEXT, 
        email TEXT, 
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
        email TEXT UNIQUE)""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS appointments(
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        patient_id INTEGER, 
        doctor_id INTEGER, 
        appointment_date TEXT, 
        appointment_time TEXT,
        status TEXT DEFAULT 'Scheduled')""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS queries(
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        patient_email TEXT, 
        recipient_type TEXT, 
        doctor_id INTEGER, 
        query_text TEXT, 
        response TEXT DEFAULT '',
        status TEXT DEFAULT 'Pending',
        created_at TEXT)""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS rooms(
        room_no TEXT PRIMARY KEY, 
        status TEXT DEFAULT 'Available',
        assigned_to TEXT DEFAULT NULL)""")
    
    # --- SCHEMA MIGRATIONS ---
    try:
        c.execute("ALTER TABLE patients ADD COLUMN email TEXT UNIQUE")
    except:
        pass
    
    try:
        c.execute("ALTER TABLE appointments ADD COLUMN status TEXT DEFAULT 'Scheduled'")
    except:
        pass
    
    try:
        c.execute("ALTER TABLE queries ADD COLUMN response TEXT DEFAULT ''")
    except:
        pass
    
    try:
        c.execute("ALTER TABLE queries ADD COLUMN status TEXT DEFAULT 'Pending'")
    except:
        pass
    
    try:
        c.execute("ALTER TABLE rooms ADD COLUMN assigned_to TEXT DEFAULT NULL")
    except:
        pass
    
    # Add default admin if not exists
    admin_exists = c.execute("SELECT * FROM users WHERE email='admin@medivista.com'").fetchone()
    if not admin_exists:
        hashed = bcrypt.hashpw('admin123'.encode(), bcrypt.gensalt())
        c.execute("INSERT INTO users VALUES (?,?,?)", ('admin@medivista.com', hashed, 'Admin'))
    
    # Add default rooms if not exists
    rooms = c.execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
    if rooms == 0:
        for i in range(1, 11):
            c.execute("INSERT INTO rooms (room_no, status) VALUES (?, 'Available')", (f"Room {i:03d}",))
    
    # Add sample doctors if none exist
    doctors_count = c.execute("SELECT COUNT(*) FROM doctors").fetchone()[0]
    if doctors_count == 0:
        sample_doctors = [
            ('Dr. Sarah Johnson', 'Cardiology', 'sarah.j@medivista.com', 'Nurse Emily', '09:00 - 17:00'),
            ('Dr. Michael Chen', 'Neurology', 'michael.c@medivista.com', 'Nurse James', '10:00 - 18:00'),
            ('Dr. Priya Sharma', 'Pediatrics', 'priya.s@medivista.com', 'Nurse Lisa', '08:00 - 16:00'),
            ('Dr. Robert Williams', 'Orthopedics', 'robert.w@medivista.com', 'Nurse David', '11:00 - 19:00'),
            ('Dr. Fatima Ahmed', 'Dermatology', 'fatima.a@medivista.com', 'Nurse Sarah', '09:00 - 17:00')
        ]
        for doctor in sample_doctors:
            c.execute("""INSERT INTO doctors (name, specialty, email, nurse_assigned, shift_timing) 
                        VALUES (?,?,?,?,?)""", doctor)
    
    conn.commit()
    conn.close()

init_db()

# ================= HELPER LOGIC ================= #
def get_available_slots(doctor_id, shift_str, date_str):
    """Generates sequential 20-minute intervals."""
    try:
        start_str, end_str = shift_str.split(" - ")
        start_dt = datetime.strptime(start_str, "%H:%M")
        end_dt = datetime.strptime(end_str, "%H:%M")
    except:
        return []
    
    slots = []
    current = start_dt
    while current + timedelta(minutes=20) <= end_dt:
        slots.append(current.strftime("%H:%M"))
        current += timedelta(minutes=20)
    
    conn = sqlite3.connect(DB_NAME)
    booked = pd.read_sql_query(
        "SELECT appointment_time FROM appointments WHERE doctor_id=? AND appointment_date=? AND status!='Cancelled'", 
        conn, params=(doctor_id, date_str))
    conn.close()
    
    return [s for s in slots if s not in booked['appointment_time'].tolist()]

def get_patient_id_by_email(email):
    conn = sqlite3.connect(DB_NAME)
    result = conn.execute("SELECT id FROM patients WHERE email=?", (email,)).fetchone()
    conn.close()
    return result[0] if result else None

def is_valid_email(email):
    return bool(re.match(r"^[a-zA-Z0-9._%+-]+@gmail\.com$", email))

def get_dashboard_metrics():
    """Get all metrics for admin dashboard"""
    conn = sqlite3.connect(DB_NAME)
    
    # Current date
    today = datetime.now().strftime("%Y-%m-%d")
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    
    # Metrics
    total_patients = pd.read_sql_query("SELECT COUNT(*) as count FROM patients", conn).iloc[0]['count']
    total_doctors = pd.read_sql_query("SELECT COUNT(*) as count FROM doctors", conn).iloc[0]['count']
    
    # Today's metrics
    today_patients = pd.read_sql_query(
        "SELECT COUNT(*) as count FROM patients WHERE visit_date=?", 
        conn, params=(today,)).iloc[0]['count']
    
    today_appointments = pd.read_sql_query(
        "SELECT COUNT(*) as count FROM appointments WHERE appointment_date=?", 
        conn, params=(today,)).iloc[0]['count']
    
    today_revenue = pd.read_sql_query(
        "SELECT SUM(amount_paid) as total FROM patients WHERE visit_date=?", 
        conn, params=(today,)).iloc[0]['total'] or 0
    
    # Room metrics
    rooms_df = pd.read_sql_query("SELECT status, COUNT(*) as count FROM rooms GROUP BY status", conn)
    available_rooms = rooms_df[rooms_df['status'] == 'Available']['count'].iloc[0] if not rooms_df[rooms_df['status'] == 'Available'].empty else 0
    
    # Query metrics
    pending_queries = pd.read_sql_query(
        "SELECT COUNT(*) as count FROM queries WHERE status='Pending'", 
        conn).iloc[0]['count']
    
    # Weekly data for charts
    weekly_appointments = pd.read_sql_query(
        """SELECT appointment_date as date, COUNT(*) as count 
           FROM appointments 
           WHERE appointment_date >= ? 
           GROUP BY appointment_date 
           ORDER BY appointment_date""", 
        conn, params=(week_ago,))
    
    weekly_revenue = pd.read_sql_query(
        """SELECT visit_date as date, SUM(amount_paid) as revenue 
           FROM patients 
           WHERE visit_date >= ? 
           GROUP BY visit_date 
           ORDER BY visit_date""", 
        conn, params=(week_ago,))
    
    # Doctor workload
    doctor_workload = pd.read_sql_query(
        """SELECT d.name, COUNT(a.id) as appointments 
           FROM doctors d 
           LEFT JOIN appointments a ON d.id = a.doctor_id AND a.appointment_date = ?
           GROUP BY d.id""", 
        conn, params=(today,))
    
    conn.close()
    
    return {
        'total_patients': total_patients,
        'total_doctors': total_doctors,
        'today_patients': today_patients,
        'today_appointments': today_appointments,
        'today_revenue': today_revenue,
        'available_rooms': available_rooms,
        'pending_queries': pending_queries,
        'weekly_appointments': weekly_appointments,
        'weekly_revenue': weekly_revenue,
        'doctor_workload': doctor_workload
    }

# ================= UI STYLING ================= #
st.markdown("""
    <style>
    /* Modern Healthcare Theme */
    .stApp {
        background-color: #0e1117;
    }
    
    div[data-testid="stMetricValue"] { 
        color: #00acee; 
        font-size: 32px; 
        font-weight: bold; 
    }
    
    div[data-testid="stMetricLabel"] { 
        font-size: 14px; 
        text-transform: uppercase; 
        letter-spacing: 1px; 
    }
    
    .stButton>button { 
        background-color: #00acee; 
        color: white; 
        border-radius: 20px; 
        width: 100%; 
        font-weight: bold; 
        border: none;
        padding: 10px 24px;
        transition: all 0.3s ease;
    }
    
    .stButton>button:hover {
        background-color: #0082b3;
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(0,172,238,0.3);
    }
    
    .sidebar-logout { 
        position: fixed; 
        bottom: 20px; 
        left: 20px; 
        width: 220px; 
    }
    
    [data-testid="stForm"] { 
        border-radius: 15px; 
        background-color: #161b22; 
        border: 1px solid #30363d !important; 
        padding: 20px;
    }
    
    .stTabs [data-baseweb="tab-list"] { 
        gap: 8px; 
        background-color: #161b22;
        padding: 10px;
        border-radius: 10px;
    }
    
    .stTabs [data-baseweb="tab"] { 
        border-radius: 8px; 
        padding: 10px 20px; 
        background-color: #262730; 
        color: #ffffff;
    }
    
    .stTabs [aria-selected="true"] {
        background-color: #00acee !important;
    }
    
    /* Cards for metrics */
    .metric-card {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 10px;
        padding: 20px;
        text-align: center;
    }
    
    /* Progress bars */
    .stProgress > div > div > div > div {
        background-color: #00acee;
    }
    
    /* Headers */
    h1, h2, h3 {
        color: #00acee !important;
    }
    
    /* Dataframes */
    .dataframe {
        background-color: #161b22;
        border-radius: 10px;
        border: 1px solid #30363d;
    }
    </style>
    """, unsafe_allow_html=True)

# Initialize session state
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_email" not in st.session_state:
    st.session_state.user_email = ""
if "role" not in st.session_state:
    st.session_state.role = ""

# ================= AUTHENTICATION ================= #
if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.image("https://img.icons8.com/color/96/000000/hospital.png", width=100)
        st.title("🏥 MediVista Management Portal")
        st.markdown("---")
        
        mode = st.radio("Option", ["Login", "Register"], horizontal=True)
        email = st.text_input("📧 Email (must be @gmail.com)")
        password = st.text_input("🔒 Password", type="password")
        
        if mode == "Register":
            role = st.selectbox("👤 Role", ["Admin", "Receptionist", "Hospital Staff", "Doctor", "Patient"])
            if st.button("📝 Create Account", use_container_width=True):
                if not is_valid_email(email):
                    st.error("❌ Email must be @gmail.com")
                elif len(password) < 6:
                    st.error("❌ Password must be at least 6 characters")
                else:
                    conn = sqlite3.connect(DB_NAME)
                    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
                    try:
                        conn.execute("INSERT INTO users VALUES (?,?,?)", (email, hashed, role))
                        conn.commit()
                        st.success("✅ Registration Successful! Please login.")
                        st.balloons()
                    except sqlite3.IntegrityError:
                        st.error("❌ User already exists.")
                    finally:
                        conn.close()
        
        if mode == "Login":
            if st.button("🚪 Login", use_container_width=True):
                if not email or not password:
                    st.error("❌ Please fill all fields")
                else:
                    conn = sqlite3.connect(DB_NAME)
                    user = conn.execute("SELECT password, role FROM users WHERE email=?", (email,)).fetchone()
                    conn.close()
                    
                    if user and bcrypt.checkpw(password.encode(), user[0]):
                        st.session_state.logged_in = True
                        st.session_state.user_email = email
                        st.session_state.role = user[1]
                        st.rerun()
                    else:
                        st.error("❌ Invalid Credentials")

# ================= MAIN APPLICATION ================= #
else:
    with st.sidebar:
        st.image("https://img.icons8.com/color/96/000000/hospital.png", width=80)
        st.title(f"MediVista")
        st.markdown(f"**Logged in as:** {st.session_state.role}")
        st.markdown(f"**Email:** {st.session_state.user_email[:15]}...")
        st.divider()
        
        # Navigation based on role
        if st.session_state.role == "Admin":
            nav = st.radio("📋 Navigation", ["Dashboard", "Room Management", "Manage Queries", "User Management"])
        elif st.session_state.role == "Receptionist":
            nav = st.radio("📋 Navigation", ["Reception Area", "View Appointments"])
        elif st.session_state.role == "Hospital Staff":
            nav = st.radio("📋 Navigation", ["Duty Board", "Room Status"])
        elif st.session_state.role == "Doctor":
            nav = st.radio("📋 Navigation", ["Patient Queries", "My Schedule", "My Patients"])
        else:  # Patient
            nav = st.radio("📋 Navigation", ["Patient Portal", "My Appointments", "Ask Question"])
        
        st.divider()
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.user_email = ""
            st.session_state.role = ""
            st.rerun()

    conn = sqlite3.connect(DB_NAME)
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # ---------------- ADMIN DASHBOARD ---------------- #
    if st.session_state.role == "Admin":
        if nav == "Dashboard":
            st.title("📊 Strategic Admin Overview")
            
            # Get metrics
            metrics = get_dashboard_metrics()
            
            # Top metrics row
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                with st.container():
                    st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                    st.metric("Total Patients", metrics['total_patients'], 
                             delta=f"+{metrics['today_patients']} today")
                    st.markdown('</div>', unsafe_allow_html=True)
            
            with col2:
                with st.container():
                    st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                    st.metric("Appointments Today", metrics['today_appointments'])
                    st.markdown('</div>', unsafe_allow_html=True)
            
            with col3:
                with st.container():
                    st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                    st.metric("Revenue Today", f"₹{metrics['today_revenue']:,.0f}")
                    st.markdown('</div>', unsafe_allow_html=True)
            
            with col4:
                with st.container():
                    st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                    st.metric("Available Rooms", metrics['available_rooms'])
                    st.markdown('</div>', unsafe_allow_html=True)
            
            st.markdown("---")
            
            # Charts Row 1
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("📈 Weekly Appointment Trend")
                if not metrics['weekly_appointments'].empty:
                    fig_appointments = px.line(
                        metrics['weekly_appointments'], 
                        x='date', 
                        y='count',
                        title="Appointments Over Last 7 Days",
                        labels={'date': 'Date', 'count': 'Number of Appointments'}
                    )
                    fig_appointments.update_layout(
                        template="plotly_dark",
                        hovermode='x',
                        plot_bgcolor='rgba(0,0,0,0)',
                        paper_bgcolor='rgba(0,0,0,0)'
                    )
                    fig_appointments.add_scatter(
                        x=metrics['weekly_appointments']['date'],
                        y=metrics['weekly_appointments']['count'],
                        mode='markers',
                        marker=dict(size=10, color='#00acee'),
                        name='Actual'
                    )
                    st.plotly_chart(fig_appointments, use_container_width=True)
                else:
                    st.info("No appointment data available")
            
            with col2:
                st.subheader("💰 Weekly Revenue Trend")
                if not metrics['weekly_revenue'].empty:
                    fig_revenue = px.bar(
                        metrics['weekly_revenue'], 
                        x='date', 
                        y='revenue',
                        title="Revenue Over Last 7 Days",
                        labels={'date': 'Date', 'revenue': 'Revenue (₹)'},
                        color='revenue',
                        color_continuous_scale='Blues'
                    )
                    fig_revenue.update_layout(
                        template="plotly_dark",
                        plot_bgcolor='rgba(0,0,0,0)',
                        paper_bgcolor='rgba(0,0,0,0)'
                    )
                    st.plotly_chart(fig_revenue, use_container_width=True)
                else:
                    st.info("No revenue data available")
            
            # Charts Row 2
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("👨‍⚕️ Doctor Workload Today")
                if not metrics['doctor_workload'].empty:
                    fig_workload = px.pie(
                        metrics['doctor_workload'],
                        values='appointments',
                        names='name',
                        title="Appointment Distribution",
                        color_discrete_sequence=px.colors.sequential.Blues_r
                    )
                    fig_workload.update_layout(
                        template="plotly_dark",
                        plot_bgcolor='rgba(0,0,0,0)',
                        paper_bgcolor='rgba(0,0,0,0)'
                    )
                    st.plotly_chart(fig_workload, use_container_width=True)
                else:
                    st.info("No workload data available")
            
            with col2:
                st.subheader("🏥 Room Status")
                rooms_df = pd.read_sql_query("SELECT status, COUNT(*) as count FROM rooms GROUP BY status", conn)
                if not rooms_df.empty:
                    fig_rooms = px.pie(
                        rooms_df,
                        values='count',
                        names='status',
                        title="Room Utilization",
                        color='status',
                        color_discrete_map={
                            'Available': '#00acee',
                            'Occupied': '#ff4b4b',
                            'Maintenance': '#ffa500'
                        }
                    )
                    fig_rooms.update_layout(
                        template="plotly_dark",
                        plot_bgcolor='rgba(0,0,0,0)',
                        paper_bgcolor='rgba(0,0,0,0)'
                    )
                    st.plotly_chart(fig_rooms, use_container_width=True)
                else:
                    st.info("No room data available")
            
            st.markdown("---")
            
            # Progress tracking
            st.subheader("📊 System Progress")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                # Patient registration progress
                target_patients = 1000  # Example target
                progress_patients = min(metrics['total_patients'] / target_patients, 1.0)
                st.markdown("**Patient Registration Goal**")
                st.progress(progress_patients)
                st.caption(f"{metrics['total_patients']}/{target_patients} patients ({(progress_patients*100):.1f}%)")
            
            with col2:
                # Daily appointment goal
                target_appointments = 50  # Example target
                progress_appointments = min(metrics['today_appointments'] / target_appointments, 1.0)
                st.markdown("**Today's Appointment Goal**")
                st.progress(progress_appointments)
                st.caption(f"{metrics['today_appointments']}/{target_appointments} appointments ({(progress_appointments*100):.1f}%)")
            
            with col3:
                # Revenue goal
                target_revenue = 100000  # Example target
                progress_revenue = min(metrics['today_revenue'] / target_revenue, 1.0)
                st.markdown("**Daily Revenue Goal**")
                st.progress(progress_revenue)
                st.caption(f"₹{metrics['today_revenue']:,.0f}/₹{target_revenue:,.0f} ({(progress_revenue*100):.1f}%)")
            
            # Recent activities
            st.markdown("---")
            st.subheader("📋 Recent Activities")
            
            recent_activities = pd.read_sql_query("""
                SELECT 'Appointment' as type, 
                       p.name as patient_name, 
                       d.name as doctor_name,
                       a.appointment_date as date,
                       a.appointment_time as time
                FROM appointments a
                JOIN patients p ON a.patient_id = p.id
                JOIN doctors d ON a.doctor_id = d.id
                WHERE a.appointment_date = ?
                UNION ALL
                SELECT 'Patient Registration' as type,
                       name as patient_name,
                       NULL as doctor_name,
                       visit_date as date,
                       NULL as time
                FROM patients
                WHERE visit_date = ?
                ORDER BY date DESC, time DESC
                LIMIT 10
            """, conn, params=(today_str, today_str))
            
            if not recent_activities.empty:
                st.dataframe(recent_activities, use_container_width=True)
            else:
                st.info("No activities today")
        
        elif nav == "Room Management":
            st.title("🏥 Room Management")
            
            col1, col2 = st.columns([1, 2])
            with col1:
                st.subheader("➕ Add New Room")
                with st.form("add_room"):
                    room_no = st.text_input("Room Number")
                    if st.form_submit_button("Add Room", use_container_width=True):
                        if room_no:
                            try:
                                conn.execute("INSERT INTO rooms (room_no) VALUES (?)", (room_no,))
                                conn.commit()
                                st.success(f"✅ Room {room_no} added!")
                                st.rerun()
                            except sqlite3.IntegrityError:
                                st.error("❌ Room already exists!")
            
            with col2:
                st.subheader("📊 Room Status Overview")
                rooms_df = pd.read_sql_query("SELECT * FROM rooms ORDER BY room_no", conn)
                
                # Status summary
                status_counts = rooms_df['status'].value_counts()
                cols = st.columns(3)
                with cols[0]:
                    st.metric("Available", status_counts.get('Available', 0))
                with cols[1]:
                    st.metric("Occupied", status_counts.get('Occupied', 0))
                with cols[2]:
                    st.metric("Maintenance", status_counts.get('Maintenance', 0))
                
                st.divider()
                
                # Room grid with status management
                st.subheader("Room Status Management")
                for i in range(0, len(rooms_df), 3):
                    cols = st.columns(3)
                    for j in range(3):
                        if i + j < len(rooms_df):
                            row = rooms_df.iloc[i + j]
                            with cols[j]:
                                with st.container():
                                    st.markdown(f"**{row['room_no']}**")
                                    current_status = row['status']
                                    
                                    # Color-coded status display
                                    if current_status == 'Available':
                                        st.success(f"🟢 {current_status}")
                                    elif current_status == 'Occupied':
                                        st.error(f"🔴 {current_status}")
                                    else:
                                        st.warning(f"🟡 {current_status}")
                                    
                                    # Status update buttons
                                    col_a, col_b, col_c = st.columns(3)
                                    with col_a:
                                        if st.button("🟢", key=f"avail_{i+j}"):
                                            conn.execute("UPDATE rooms SET status='Available', assigned_to=NULL WHERE room_no=?", (row['room_no'],))
                                            conn.commit()
                                            st.rerun()
                                    with col_b:
                                        if st.button("🔴", key=f"occ_{i+j}"):
                                            conn.execute("UPDATE rooms SET status='Occupied' WHERE room_no=?", (row['room_no'],))
                                            conn.commit()
                                            st.rerun()
                                    with col_c:
                                        if st.button("🟡", key=f"maint_{i+j}"):
                                            conn.execute("UPDATE rooms SET status='Maintenance', assigned_to=NULL WHERE room_no=?", (row['room_no'],))
                                            conn.commit()
                                            st.rerun()
        
        elif nav == "Manage Queries":
            st.title("📨 Manage Patient Queries")
            
            # Query statistics
            col1, col2, col3 = st.columns(3)
            query_stats = pd.read_sql_query("""
                SELECT status, COUNT(*) as count 
                FROM queries 
                GROUP BY status
            """, conn)
            
            pending = query_stats[query_stats['status'] == 'Pending']['count'].iloc[0] if not query_stats[query_stats['status'] == 'Pending'].empty else 0
            answered = query_stats[query_stats['status'] == 'Answered']['count'].iloc[0] if not query_stats[query_stats['status'] == 'Answered'].empty else 0
            
            with col1:
                st.metric("Total Queries", query_stats['count'].sum() if not query_stats.empty else 0)
            with col2:
                st.metric("Pending", pending)
            with col3:
                st.metric("Answered", answered)
            
            st.divider()
            
            # Pending queries
            st.subheader("⏳ Pending Queries")
            queries_df = pd.read_sql_query("""
                SELECT q.*, d.name as doctor_name, p.name as patient_name
                FROM queries q 
                LEFT JOIN doctors d ON q.doctor_id = d.id
                LEFT JOIN patients p ON q.patient_email = p.email
                WHERE q.status='Pending'
                ORDER BY q.created_at DESC
            """, conn)
            
            if not queries_df.empty:
                for idx, query in queries_df.iterrows():
                    with st.expander(f"📝 Query from {query['patient_name'] or query['patient_email']} - {query['created_at']}"):
                        st.write(f"**Question:** {query['query_text']}")
                        if query['recipient_type'] == 'Doctor' and query['doctor_name']:
                            st.write(f"**To:** Dr. {query['doctor_name']}")
                        else:
                            st.write(f"**To:** {query['recipient_type']}")
                        
                        response = st.text_area("Your Response", key=f"resp_{idx}", height=100)
                        if st.button("✅ Submit Response", key=f"btn_{idx}", use_container_width=True):
                            conn.execute("""
                                UPDATE queries 
                                SET response=?, status='Answered' 
                                WHERE id=?
                            """, (response, query['id']))
                            conn.commit()
                            st.success("✅ Response sent!")
                            st.rerun()
            else:
                st.info("✨ No pending queries")
            
            # Answered queries history
            st.divider()
            st.subheader("📜 Query History")
            answered_df = pd.read_sql_query("""
                SELECT q.*, p.name as patient_name
                FROM queries q
                LEFT JOIN patients p ON q.patient_email = p.email
                WHERE q.status='Answered'
                ORDER BY q.created_at DESC
                LIMIT 10
            """, conn)
            
            if not answered_df.empty:
                for _, query in answered_df.iterrows():
                    with st.expander(f"✅ {query['patient_name'] or query['patient_email']} - {query['created_at']}"):
                        st.write(f"**Question:** {query['query_text']}")
                        st.write(f"**Response:** {query['response']}")
        
        elif nav == "User Management":
            st.title("👥 User Management")
            
            users_df = pd.read_sql_query("SELECT email, role FROM users ORDER BY role, email", conn)
            
            # Statistics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Users", len(users_df))
            with col2:
                st.metric("Admins", len(users_df[users_df['role'] == 'Admin']))
            with col3:
                st.metric("Patients", len(users_df[users_df['role'] == 'Patient']))
            
            st.divider()
            
            # Add new user
            with st.expander("➕ Add New User"):
                with st.form("add_user"):
                    new_email = st.text_input("Email (@gmail.com)")
                    new_password = st.text_input("Password", type="password")
                    new_role = st.selectbox("Role", ["Admin", "Receptionist", "Hospital Staff", "Doctor", "Patient"])
                    
                    if st.form_submit_button("Create User", use_container_width=True):
                        if is_valid_email(new_email) and len(new_password) >= 6:
                            hashed = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt())
                            try:
                                conn.execute("INSERT INTO users VALUES (?,?,?)", (new_email, hashed, new_role))
                                conn.commit()
                                st.success("✅ User created successfully!")
                                st.rerun()
                            except sqlite3.IntegrityError:
                                st.error("❌ Email already exists!")
                        else:
                            st.error("❌ Invalid email or password too short")
            
            # Display users
            st.subheader("📋 Current Users")
            
            # Role filter
            role_filter = st.selectbox("Filter by Role", ["All"] + list(users_df['role'].unique()))
            if role_filter != "All":
                filtered_users = users_df[users_df['role'] == role_filter]
            else:
                filtered_users = users_df
            
            st.dataframe(filtered_users, use_container_width=True)
            
            # Delete user section
            st.divider()
            st.subheader("🗑️ Delete User")
            user_to_delete = st.selectbox("Select user to delete", users_df['email'].tolist())
            if st.button("Delete User", use_container_width=True, type="primary"):
                if user_to_delete != 'admin@medivista.com':  # Prevent deleting default admin
                    conn.execute("DELETE FROM users WHERE email=?", (user_to_delete,))
                    conn.commit()
                    st.success(f"✅ User {user_to_delete} deleted!")
                    st.rerun()
                else:
                    st.error("❌ Cannot delete default admin user!")
    
    # ---------------- RECEPTIONIST ---------------- #
    elif st.session_state.role == "Receptionist":
        if nav == "Reception Area":
            st.title("📞 Reception Desk")
            
            tab1, tab2, tab3 = st.tabs(["📝 Register Patient", "👨‍⚕️ Add Doctor", "📅 Book Appointment"])
            
            with tab1:
                with st.form("register_patient"):
                    st.subheader("New Patient Registration")
                    col1, col2 = st.columns(2)
                    with col1:
                        p_name = st.text_input("Full Name *")
                        p_age = st.number_input("Age", 1, 120, 25)
                        p_blood = st.selectbox("Blood Group", ["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"])
                    with col2:
                        p_email = st.text_input("Email (@gmail.com) *")
                        p_reason = st.text_input("Visit Reason")
                        p_payment = st.number_input("Payment Amount (₹)", 0.0, 100000.0, 0.0)
                    
                    st.caption("* Required fields")
                    
                    if st.form_submit_button("✅ Register Patient", use_container_width=True):
                        if not p_name or not p_email:
                            st.error("❌ Name and Email are required!")
                        elif not is_valid_email(p_email):
                            st.error("❌ Email must be @gmail.com")
                        else:
                            try:
                                conn.execute("""
                                    INSERT INTO patients (name, age, blood_group, email, reason, amount_paid, visit_date) 
                                    VALUES (?,?,?,?,?,?,?)
                                """, (p_name, p_age, p_blood, p_email, p_reason, p_payment, today_str))
                                conn.commit()
                                st.success(f"✅ Patient {p_name} Registered Successfully!")
                                st.balloons()
                            except sqlite3.IntegrityError:
                                st.error("❌ Email already exists!")
            
            with tab2:
                with st.form("add_doctor"):
                    st.subheader("Add New Doctor")
                    col1, col2 = st.columns(2)
                    with col1:
                        d_name = st.text_input("Doctor Name *")
                        d_specialty = st.text_input("Specialty *")
                        d_email = st.text_input("Email *")
                    with col2:
                        d_nurse = st.text_input("Assigned Nurse")
                        d_shift = st.text_input("Shift Timing (e.g., 09:00 - 17:00) *")
                    
                    st.caption("* Required fields")
                    
                    if st.form_submit_button("✅ Add Doctor", use_container_width=True):
                        if d_name and d_specialty and d_email and d_shift:
                            try:
                                conn.execute("""
                                    INSERT INTO doctors (name, specialty, email, nurse_assigned, shift_timing) 
                                    VALUES (?,?,?,?,?)
                                """, (d_name, d_specialty, d_email, d_nurse, d_shift))
                                conn.commit()
                                st.success(f"✅ Dr. {d_name} Added!")
                                st.balloons()
                            except sqlite3.IntegrityError:
                                st.error("❌ Doctor with this email already exists!")
                        else:
                            st.error("❌ Please fill all required fields!")
            
            with tab3:
                st.subheader("Book 20-Minute Appointment")
                
                patients_df = pd.read_sql_query("SELECT id, name FROM patients ORDER BY name", conn)
                doctors_df = pd.read_sql_query("SELECT id, name
