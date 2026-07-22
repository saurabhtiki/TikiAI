
from PIL import Image
import json
import re
from collections import Counter
from datetime import datetime, date
from io import BytesIO
from pathlib import Path
import pandas as pd
import streamlit as st
from openpyxl import load_workbook
import zipfile

from utils.auth_db import init_db, seed_from_streamlit_secrets_if_empty, get_user_type

# Ensure DB exists and seed it once from current Streamlit secrets.
# After this migration, SQLite becomes the source of truth.
init_db()
seed_from_streamlit_secrets_if_empty()


st.set_page_config(
    page_title="Tikitar",
    page_icon=Image.open("static/tikitar-logo.webp"),
    layout="wide"
)
st.html(Path("style.css"))

EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9._%+-]*[A-Za-z0-9])?@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
)

# Initialize session state
if "show_user_mgnt" not in st.session_state:
    st.session_state.show_user_mgnt = False

if "show_schema_mgnt" not in st.session_state:
    st.session_state.show_schema_mgnt = False

if "task_select" not in st.session_state:
    st.session_state.task_select = ""

if "user_email" not in st.session_state:
    st.session_state.user_email = ""

if "user_type" not in st.session_state:
    st.session_state.user_type = ""

if "is_authenticated" not in st.session_state:
    st.session_state.is_authenticated = False

# Header
with st.container(horizontal=True):
    st.image(Image.open("static/tikitar-logo.webp"), width=80)
    if st.session_state.task_select == "" or st.session_state.task_select is None:
        st.header(":blue[Tikitar-Task Automation]")
    else:
        st.header(f":blue[Tikitar-Task Automation : {st.session_state.task_select}]")

#empty container to toggal login form & welcom heaider

placeholder = st.empty()

def logout_user():
    st.session_state.user_email = ""
    st.session_state.user_type = ""
    st.session_state.is_authenticated = False
    st.session_state.task_select = ""
    st.session_state.show_user_mgnt = False
    st.session_state.show_schema_mgnt = False
    st.session_state.backup_zip = None
    st.session_state.backup_ready = False

if "backup_zip" not in st.session_state:
    st.session_state.backup_zip = None

if "backup_ready" not in st.session_state:
    st.session_state.backup_ready = False

def create_backup_zip():
    settings_path = Path("data/settings.json")
    with open(settings_path, "r", encoding="utf-8") as f:
        settings = json.load(f)

    backup_list = settings.get("tasks", {}).get("backup", {}).get("backupList", [])
    if not backup_list:
        raise ValueError("No backup paths configured in settings.json")

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for entry in backup_list:
            path = Path(entry)
            if not path.exists():
                raise FileNotFoundError(f"Backup path not found: {entry}")

            if path.is_file():
                zf.write(path, path.name)
            elif path.is_dir():
                for file_path in sorted(path.rglob("*")):
                    if file_path.is_file():
                        arcname = str(file_path.relative_to(path.parent))
                        zf.write(file_path, arcname)

    buffer.seek(0)
    return buffer
# Login screen first

if not st.session_state.is_authenticated:
    with placeholder.container():
        st.subheader("Login")
        with st.form("🔑login_form", clear_on_submit=False):
            email_input = st.text_input(
                "Enter your email",
                key="login_email_input",
                placeholder="name@example.com"
            )
            submitted = st.form_submit_button("Submit", key="login_submit_btn")

            if submitted:
                normalized_email = email_input.strip().lower()

                if not EMAIL_PATTERN.fullmatch(normalized_email):
                    st.error("Please enter a valid email address.")
                else:
                    user_type = get_user_type(normalized_email)
                    if user_type is not None:
                        st.session_state.user_email = normalized_email
                        st.session_state.user_type = user_type
                        st.session_state.is_authenticated = True
                        st.success("Login successful")
                    else:
                        st.error("Not Authorised to access")

# Sidebar logout button after successful login if user is authenticated
if st.session_state.is_authenticated==True:
    st.sidebar.button(":red[⏻ Logout]", key="logout_btn", on_click=logout_user)
    st.sidebar.write(f"Logged in as: {st.session_state.user_email}")
    
    # Admin-only: User Management button
    if st.session_state.user_type == "admin":
        #st.sidebar.divider()
        if st.sidebar.button(":material/manage_accounts: User Management", width="stretch", key="user_mgmt_btn"):
            st.session_state.show_user_mgnt = True
            st.session_state.show_schema_mgnt = False

        if st.sidebar.button(":material/settings: Schema Management", width="stretch", key="schema_mgmt_btn"):
            st.session_state.show_schema_mgnt = True
            st.session_state.show_user_mgnt = False
            
         #button for backup on click download backup files
        if st.sidebar.button(":material/backup: Backup", width="stretch", key="backup_btn"):
            try:
                zip_buffer = create_backup_zip()
                st.session_state.backup_zip = zip_buffer.getvalue()
                st.session_state.backup_ready = True
                st.toast("Backup created successfully!", icon="✅")
            except Exception as e:
                st.toast(f"Backup failed: {str(e)}", icon="❌")

            if st.session_state.get("backup_ready"):
                if st.sidebar.download_button(
                    "📥 Download Backup",
                    data=st.session_state.backup_zip,
                    file_name=f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                    mime="application/zip",
                    key="download_backup_btn"
                ):
                    st.toast("Backup downloaded successfully!", icon="✅")
                    st.session_state.backup_ready = False
                    st.session_state.backup_zip = None
                    
        
    
    all_pages = {
        "2B-Purchase-Reco": "pages/reco2B.py",
        "Reconcile Any Data": "pages/reco_any.py",
        "Add Files": "pages/add_files.py",
        "PDF Extractor": "pages/PdfExtracter.py",
        "User Management": "pages/user_management.py",
        "Schema Management": "pages/schema_management.py"
    }

    user_pages = {
        "2B-Purchase-Reco": "pages/reco2B.py",
        "Reconcile Any Data": "pages/reco_any.py",
        "Add Files": "pages/add_files.py",
        "PDF Extractor": "pages/PdfExtracter.py"
        #"User Management": "pages/user_management.py"
    }
    if st.session_state.user_type == "user":
        all_pages = user_pages
    st.sidebar.divider()
    task_select = st.sidebar.selectbox(
        "🛠️ Tools & Utilities",
        list(user_pages.keys()),
        placeholder="Type to Search for a Task...",
        key="task_select",
        index=None,
        on_change=lambda: st.session_state.update({"show_user_mgnt": False, "show_schema_mgnt": False})
    )

    # Handle User Management navigation from button click
    if st.session_state.show_schema_mgnt==True:
        placeholder.empty()
        pg = st.navigation([st.Page(all_pages["Schema Management"], title="Schema Management")])
        pg.run()
    elif st.session_state.show_user_mgnt==True:
        placeholder.empty()
        pg = st.navigation([st.Page(all_pages["User Management"], title="User Management")])
        pg.run()
    elif task_select is not None:

        placeholder.empty()
        pg = st.navigation([st.Page(all_pages[task_select], title=task_select)])
        pg.run()
    else:
        with placeholder.container():
            st.subheader("Welcome to Tikitar")
            st.success("Please select a task from the sidebar to get started")
