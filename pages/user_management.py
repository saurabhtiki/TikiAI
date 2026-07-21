"""
User Management Page - Admin only
Create, Alter, Delete, and View users
"""
import re
import sqlite3
from typing import List, Optional

import pandas as pd
import streamlit as st

from utils.auth_db import init_db, get_user_type

EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9._%+-]*[A-Za-z0-9])?@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
)


def get_all_users(db_path: Optional[str] = None) -> pd.DataFrame:
    """Fetch all users from the database."""
    db_path = init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql_query(
            "SELECT email, user_type, created_at FROM users ORDER BY created_at DESC",
            conn
        )
    return df


def add_user(email: str, user_type: str, db_path: Optional[str] = None) -> tuple[bool, str]:
    """Add a new user. Returns (success, message)."""
    if not EMAIL_PATTERN.fullmatch(email):
        return False, "Invalid email format"
    
    if user_type not in ("admin", "user"):
        return False, "User type must be 'admin' or 'user'"
    
    db_path = init_db(db_path)
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO users (email, user_type) VALUES (?, ?)",
                (email, user_type)
            )
            conn.commit()
        return True, f"User '{email}' added successfully"
    except sqlite3.IntegrityError:
        return False, f"User '{email}' already exists"


def update_user(email: str, new_user_type: str, db_path: Optional[str] = None) -> tuple[bool, str]:
    """Update a user's type. Returns (success, message)."""
    if new_user_type not in ("admin", "user"):
        return False, "User type must be 'admin' or 'user'"
    
    db_path = init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            "UPDATE users SET user_type = ? WHERE email = ?",
            (new_user_type, email)
        )
        conn.commit()
        
        if cursor.rowcount == 0:
            return False, f"User '{email}' not found"
    
    return True, f"User '{email}' updated successfully"


def delete_user(email: str, db_path: Optional[str] = None) -> tuple[bool, str]:
    """Delete a user. Returns (success, message)."""
    db_path = init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute("DELETE FROM users WHERE email = ?", (email,))
        conn.commit()
        
        if cursor.rowcount == 0:
            return False, f"User '{email}' not found"
    
    return True, f"User '{email}' deleted successfully"


@st.dialog("Add New User")
def show_add_user_dialog():
    """Modal dialog for adding a new user."""
    with st.form("add_user_form", clear_on_submit=True):
        email = st.text_input(
            "Email Address",
            placeholder="name@example.com",
            key="add_user_email"
        )
        user_type = st.selectbox(
            "User Type",
            options=["user", "admin"],
            key="add_user_type"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            submitted = st.form_submit_button("Add User", use_container_width=True)
        with col2:
            cancelled = st.form_submit_button("Cancel", use_container_width=True)
        
        if submitted:
            normalized_email = email.strip().lower()
            success, message = add_user(normalized_email, user_type)
            if success:
                st.success(message)
                st.rerun()
            else:
                st.error(message)
        
        if cancelled:
            st.rerun()


@st.dialog("Edit User")
def show_edit_user_dialog(email: str, current_type: str):
    """Modal dialog for editing an existing user."""
    st.info(f"Editing: **{email}**")
    
    with st.form("edit_user_form"):
        new_type = st.selectbox(
            "User Type",
            options=["user", "admin"],
            index=0 if current_type == "user" else 1,
            key="edit_user_type"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            submitted = st.form_submit_button("Update", use_container_width=True)
        with col2:
            cancelled = st.form_submit_button("Cancel", use_container_width=True)
        
        if submitted:
            if new_type != current_type:
                success, message = update_user(email, new_type)
                if success:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)
            else:
                st.info("No changes made")
                st.rerun()
        
        if cancelled:
            st.rerun()


@st.dialog("Confirm Delete")
def show_delete_confirmation(email: str):
    """Modal dialog for confirming user deletion."""
    st.warning(f"Are you sure you want to delete user **{email}**?")
    st.markdown("This action cannot be undone.")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Delete", use_container_width=True, type="primary"):
            success, message = delete_user(email)
            if success:
                st.success(message)
                st.rerun()
            else:
                st.error(message)
    
    with col2:
        if st.button("Cancel", use_container_width=True):
            st.rerun()


def render_user_management():
    """Main function to render the User Management page."""
    # Check if user is admin
    if st.session_state.get("user_type") != "admin":
        st.error("Access denied. Admin privileges required.")
        st.stop()
    
    st.header(":material/manage_accounts: User Management")
    
    # Top action button
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        if st.button(":material/person_add: Add New User", use_container_width=True):
            show_add_user_dialog()
    
    # Load users
    df = get_all_users()
    
    if df.empty:
        st.info("No users found. Add your first user!")
        return
    
    # Initialize selected row in session state
    if "selected_user_email" not in st.session_state:
        st.session_state.selected_user_email = None
    
    # Display editable dataframe with selection
    st.subheader("Users List")
    
    # Configure columns
    column_config = {
        "email": st.column_config.TextColumn(
            "Email",
            width="medium",
            disabled=True
        ),
        "user_type": st.column_config.SelectboxColumn(
            "User Type",
            options=["user", "admin"],
            width="small",
            disabled=True
        ),
        "created_at": st.column_config.TextColumn(
            "Created At",
            width="medium",
            disabled=True
        )
    }
    
    # Data editor with selection enabled
    edited_df = st.dataframe(
        df,
        column_config=column_config,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="user_table"
    )
    
    # Check if a row is selected
    selected_rows = edited_df.get("selection", {}).get("rows", [])
    
    if selected_rows:
        selected_idx = selected_rows[0]
        
        # Guard: selection index may be stale after delete + rerun
        try:
            selected_email = df.iloc[selected_idx]["email"]
            selected_type = df.iloc[selected_idx]["user_type"]
        except IndexError:
            #st.rerun()
            return
        
        # Show action buttons only when row is selected
        col1, col2, col3 = st.columns([1, 1, 3])
        with col1:
            if st.button(":material/edit: Alter User", use_container_width=True, key="alter_btn"):
                show_edit_user_dialog(selected_email, selected_type)
        
        with col2:
            if st.button(":material/delete: Delete User", use_container_width=True, key="delete_btn"):
                show_delete_confirmation(selected_email)
        
        with col3:
            st.info(f"Selected: {selected_email}")
    else:
        st.caption("Select a row to enable Alter/Delete options")


# Run the page
render_user_management()
