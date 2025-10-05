import streamlit as st
import pandas as pd
import sqlite3
import hashlib
from datetime import datetime
import os
import re

# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------
DB_PATH = "queries_database.db"
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ------------------------------------------------------------
# Database Setup
# ------------------------------------------------------------
def create_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def create_tables():
    conn = create_connection()
    cursor = conn.cursor()

    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            hashed_password TEXT NOT NULL,
            role TEXT NOT NULL
        )
    ''')

    # Queries table (initial columns)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS queries (
            query_id TEXT PRIMARY KEY,
            client_email TEXT,
            client_mobile TEXT,
            query_heading TEXT,
            query_description TEXT,
            status TEXT DEFAULT 'Open',
            date_raised TEXT,
            date_closed TEXT
        )
    ''')

    # Add screenshot_path column if it doesn't exist
    try:
        cursor.execute("ALTER TABLE queries ADD COLUMN screenshot_path TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists

    conn.commit()
    conn.close()

create_tables()

# ------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_user(username, password, role):
    conn = create_connection()
    cursor = conn.cursor()
    hashed = hash_password(password)
    cursor.execute("SELECT * FROM users WHERE username=? AND hashed_password=? AND role=?",
                   (username, hashed, role))
    user = cursor.fetchone()
    conn.close()
    return user

def insert_user(username, password, role):
    conn = create_connection()
    cursor = conn.cursor()
    hashed = hash_password(password)
    cursor.execute("INSERT OR IGNORE INTO users (username, hashed_password, role) VALUES (?, ?, ?)",
                   (username, hashed, role))
    conn.commit()
    conn.close()

def get_next_query_id():
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT query_id FROM queries ORDER BY query_id DESC LIMIT 1")
    last = cursor.fetchone()
    conn.close()
    if last:
        match = re.match(r"Q(\d+)", last[0])
        if match:
            return f"Q{int(match.group(1)) + 1}"
    return "Q5201"

def insert_query(query_id, email, mobile, heading, description, screenshot_path=None):
    conn = create_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('''
        INSERT INTO queries (
            query_id, client_email, client_mobile, query_heading,
            query_description, screenshot_path, status, date_raised
        ) VALUES (?, ?, ?, ?, ?, ?, 'Open', ?)
    ''', (query_id, email, mobile, heading, description, screenshot_path, now))
    conn.commit()
    conn.close()

def fetch_queries(status=None):
    conn = create_connection()
    query = "SELECT * FROM queries"
    if status:
        query += f" WHERE status='{status}'"
    df = pd.read_sql(query, conn)
    conn.close()
    return df

def close_query(query_id):
    conn = create_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("UPDATE queries SET status='Closed', date_closed=? WHERE query_id=?",
                   (now, query_id))
    conn.commit()
    conn.close()

# ------------------------------------------------------------
# Default Users
# ------------------------------------------------------------
default_users = [
    ("Alice", "Alice@123", "Client"),
    ("Sasi", "Sasi@123", "support"),
    ("Eddy", "Eddy@123", "support"),
    ("Mohan", "Mohan@123", "support")
]

for u, p, r in default_users:
    insert_user(u, p, r)

# ------------------------------------------------------------
# Streamlit UI
# ------------------------------------------------------------
st.set_page_config(page_title="Query Management System", layout="wide")
st.title("💼 Client & Support Query Management System")

# -----------------------------
# Login Section
# -----------------------------
st.sidebar.header("🔐 Login")
username = st.sidebar.text_input("Username")
password = st.sidebar.text_input("Password", type="password")
role = st.sidebar.selectbox("Role", ["Client", "support"])

if st.sidebar.button("Login"):
    user = verify_user(username, password, role)
    if user:
        st.session_state.authenticated = True
        st.session_state.username = username
        st.session_state.role = role
        st.success(f"✅ Welcome, {username} ({role})")
    else:
        st.error("❌ Invalid login credentials")

# -----------------------------
# Client Interface
# -----------------------------
if st.session_state.get("authenticated") and st.session_state.get("role") == "Client":
    st.subheader(f"👤 Client Dashboard: {st.session_state.username}")
    st.markdown("### 📝 Submit a New Query")

    next_query_id = get_next_query_id()

    with st.form("query_form"):
        st.text_input("Query ID (auto-generated)", value=next_query_id, disabled=True)
        email = st.text_input("Email")
        mobile = st.text_input("Mobile Number")
        heading = st.text_input("Query Heading")
        description = st.text_area("Query Description")
        screenshot = st.file_uploader("📎 Optional Screenshot", type=["jpg", "jpeg", "png"])

        submit = st.form_submit_button("Submit Query")
        if submit:
            if email and mobile and heading and description:
                screenshot_path = None
                if screenshot:
                    ext = os.path.splitext(screenshot.name)[-1]
                    filename = f"{next_query_id}_screenshot{ext}"
                    screenshot_path = os.path.join(UPLOAD_DIR, filename)
                    with open(screenshot_path, "wb") as f:
                        f.write(screenshot.read())
                insert_query(next_query_id, email, mobile, heading, description, screenshot_path)
                st.success(f"✅ Query {next_query_id} submitted successfully.")
            else:
                st.warning("⚠️ Please fill all required fields.")

    # Display user's past queries
    st.markdown("### 📋 Your Queries")
    if email:
        conn = create_connection()
        df = pd.read_sql("SELECT * FROM queries WHERE client_email=? ORDER BY date_raised DESC", conn, params=(email,))
        conn.close()
        if df.empty:
            st.info("No queries found for your email.")
        else:
            for _, row in df.iterrows():
                st.write(f"**Query ID:** {row['query_id']}")
                st.write(f"**Heading:** {row['query_heading']}")
                st.write(f"**Description:** {row['query_description']}")
                st.write(f"**Status:** {row['status']}")
                screenshot_status = "Yes" if row["screenshot_path"] else "No"
                st.write(f"**Screenshot Uploaded:** {screenshot_status}")
                st.markdown("---")

# -----------------------------
# Support Interface
# -----------------------------
elif st.session_state.get("authenticated") and st.session_state.get("role") == "support":
    st.subheader(f"🧑‍💼 Support Dashboard: {st.session_state.username}")

    status_filter = st.selectbox("Filter Queries by Status", ["All", "Open", "Closed"])
    if status_filter == "All":
        df = fetch_queries()
    else:
        df = fetch_queries(status_filter)

    if df.empty:
        st.info("No queries available.")
    else:
        # Create a column for screenshot status (Yes/No)
        df["Screenshot Uploaded"] = df["screenshot_path"].apply(lambda x: "Yes" if x else "No")

        # Show table without screenshot_path and date_closed
        display_df = df.drop(columns=["screenshot_path", "date_closed"])
        st.dataframe(display_df.style.set_properties(**{'text-align': 'left'}))

        # Close Query Section
        open_df = df[df["status"] == "Open"]
        if not open_df.empty:
            query_to_close = st.selectbox("Select Query to Close", open_df["query_id"], key="close_query_select")
            if st.button("Close Query"):
                close_query(query_to_close)
                st.success(f"✅ Query {query_to_close} closed successfully.")
                st.rerun()
        else:
            st.info("✅ No open queries left.")

# -----------------------------
# Logout
# -----------------------------
if st.sidebar.button("Logout"):
    st.session_state.clear()
    st.sidebar.success("👋 Logged out successfully.")
