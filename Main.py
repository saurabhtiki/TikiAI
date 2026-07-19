
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
    if st.session_state.task_select == "":
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


def get_authorized_lists():
    authorized_users = st.secrets.get("authorized_users", [])
    authorized_admins = st.secrets.get("authorized_admins", [])

    return (
        [email.strip().lower() for email in authorized_users if isinstance(email, str)],
        [email.strip().lower() for email in authorized_admins if isinstance(email, str)],
    )


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
                    authorized_users, authorized_admins = get_authorized_lists()

                    if normalized_email in authorized_admins:
                        st.session_state.user_email = normalized_email
                        st.session_state.user_type = "admin"
                        st.session_state.is_authenticated = True
                        st.success("Login successful")
                    elif normalized_email in authorized_users:
                        st.session_state.user_email = normalized_email
                        st.session_state.user_type = "user"
                        st.session_state.is_authenticated = True
                        st.success("Login successful")
                    else:
                        st.error("Not Authorised to access")

    #st.rerun()

# Sidebar logout button after successful login if user is authenticated
if st.session_state.is_authenticated==True:
    st.sidebar.button(":red[⏻ Logout]", key="logout_btn", on_click=logout_user)
    st.sidebar.write(f"Logged in as: {st.session_state.user_email} ({st.session_state.user_type})")
    all_pages = {
        "2B-Purchase-Reco": "pages/reco2B.py",
        "Reconcile Any Data": "pages/reco_any.py"
    }

    task_select = st.sidebar.selectbox(
        "📋Choose a Task",
        list(all_pages.keys()),
        placeholder="Type to Search for a Task...",
        key="task_select",
        index=None
    )

    if task_select is not None:
        pg = st.navigation([st.Page(all_pages[task_select], title=task_select)])
        pg.run()
    else:
        with placeholder.container():
            st.subheader("Welcome to Tikitar")
            st.success("Please select a task from the sidebar to get started")