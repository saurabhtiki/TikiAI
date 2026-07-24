"""
User Management Page - Super-admin only
Create, alter, delete, and view users.
"""
import re
import sqlite3
from typing import Optional

import pandas as pd
import streamlit as st

from utils.auth_db import MANAGED_USER_TYPES, hash_password, init_db


EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9._%+-]*[A-Za-z0-9])?@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
)


def get_all_users(db_path: Optional[str] = None) -> pd.DataFrame:
    """Fetch all users from the database."""
    db_path = init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query(
            """
            SELECT email, name, user_type, created_at
            FROM users
            ORDER BY created_at DESC
            """,
            conn,
        )


def get_existing_user_type(email: str, db_path: Optional[str] = None) -> Optional[str]:
    db_path = init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute("SELECT user_type FROM users WHERE email = ?", (email,))
        row = cur.fetchone()
    return row[0] if row else None


def add_user(
    email: str,
    name: str,
    user_type: str,
    password: str,
    db_path: Optional[str] = None,
) -> tuple[bool, str]:
    """Add a new managed user. Returns (success, message)."""
    if not EMAIL_PATTERN.fullmatch(email):
        return False, "Invalid email format"

    if not name.strip():
        return False, "Name cannot be blank"

    if user_type not in MANAGED_USER_TYPES:
        return False, "User type must be 'admin' or 'user'"

    if not password:
        return False, "Password cannot be blank"

    db_path = init_db(db_path)
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO users (email, name, user_type, password)
                VALUES (?, ?, ?, ?)
                """,
                (email, name.strip(), user_type, hash_password(password)),
            )
            conn.commit()
        return True, f"User '{email}' added successfully"
    except sqlite3.IntegrityError:
        return False, f"User '{email}' already exists"


def update_user(
    email: str,
    new_name: str,
    new_user_type: str,
    db_path: Optional[str] = None,
) -> tuple[bool, str]:
    """Update a managed user's name and type. Returns (success, message)."""
    current_user_type = get_existing_user_type(email, db_path)
    if current_user_type == "Super-admin":
        return False, "Super-admin cannot be updated"

    if not current_user_type:
        return False, f"User '{email}' not found"

    if not new_name.strip():
        return False, "Name cannot be blank"

    if new_user_type not in MANAGED_USER_TYPES:
        return False, "User type must be 'admin' or 'user'"

    db_path = init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            "UPDATE users SET name = ?, user_type = ? WHERE email = ?",
            (new_name.strip(), new_user_type, email),
        )
        rowcount = cursor.rowcount
        conn.commit()

    if rowcount == 0:
        return False, f"User '{email}' not found"

    return True, f"User '{email}' updated successfully"


def delete_user(email: str, db_path: Optional[str] = None) -> tuple[bool, str]:
    """Delete a managed user. Returns (success, message)."""
    current_user_type = get_existing_user_type(email, db_path)
    if current_user_type == "Super-admin":
        return False, "Super-admin cannot be deleted"

    if not current_user_type:
        return False, f"User '{email}' not found"

    db_path = init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute("DELETE FROM users WHERE email = ?", (email,))
        rowcount = cursor.rowcount
        conn.commit()

    if rowcount == 0:
        return False, f"User '{email}' not found"

    return True, f"User '{email}' deleted successfully"


@st.dialog("Add New User")
def show_add_user_dialog():
    """Modal dialog for adding a new user."""
    with st.form("add_user_form", clear_on_submit=True):
        email = st.text_input(
            "Email Address",
            placeholder="name@example.com",
            key="add_user_email",
        )
        name = st.text_input("Name", key="add_user_name")
        user_type = st.selectbox(
            "User Type",
            options=list(MANAGED_USER_TYPES),
            key="add_user_type",
        )
        password = st.text_input(
            "Password",
            type="password",
            key="add_user_password",
        )
        confirm_password = st.text_input(
            "Confirm Password",
            type="password",
            key="add_user_confirm_password",
        )

        col1, col2 = st.columns(2)
        with col1:
            submitted = st.form_submit_button("Add User", width="stretch")
        with col2:
            cancelled = st.form_submit_button("Cancel", width="stretch")

        if submitted:
            normalized_email = email.strip().lower()
            if password != confirm_password:
                st.error("Password and confirm password do not match")
            else:
                success, message = add_user(
                    normalized_email,
                    name,
                    user_type,
                    password,
                )
                if success:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)

        if cancelled:
            st.rerun()


@st.dialog("Edit User")
def show_edit_user_dialog(email: str, current_name: str, current_type: str):
    """Modal dialog for editing an existing user."""
    st.info(f"Editing: **{email}**")

    with st.form("edit_user_form"):
        name = st.text_input(
            "Name",
            value=current_name,
            key="edit_user_name",
        )
        new_type = st.selectbox(
            "User Type",
            options=list(MANAGED_USER_TYPES),
            index=list(MANAGED_USER_TYPES).index(current_type),
            key="edit_user_type",
        )

        col1, col2 = st.columns(2)
        with col1:
            submitted = st.form_submit_button("Update", width="stretch")
        with col2:
            cancelled = st.form_submit_button("Cancel", width="stretch")

        if submitted:
            success, message = update_user(email, name, new_type)
            if success:
                st.success(message)
                st.rerun()
            else:
                st.error(message)

        if cancelled:
            st.rerun()


@st.dialog("Confirm Delete")
def show_delete_confirmation(email: str):
    """Modal dialog for confirming user deletion."""
    st.warning(f"Are you sure you want to delete user **{email}**?")
    st.markdown("This action cannot be undone.")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Delete", width="stretch", type="primary"):
            success, message = delete_user(email)
            if success:
                st.success(message)
                st.rerun()
            else:
                st.error(message)

    with col2:
        if st.button("Cancel", width="stretch"):
            st.rerun()


def render_user_management():
    """Render the User Management page."""
    if st.session_state.get("user_type") != "Super-admin":
        st.error("Access denied. Super-admin privileges required.")
        st.stop()

    st.header(":material/manage_accounts: User Management")

    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        if st.button(":material/person_add: Add New User", width="stretch"):
            show_add_user_dialog()

    df = get_all_users()

    if df.empty:
        st.info("No users found.")
        return

    st.subheader("Users List")

    column_config = {
        "email": st.column_config.TextColumn(
            "Email",
            width="medium",
            disabled=True,
        ),
        "name": st.column_config.TextColumn(
            "Name",
            width="medium",
            disabled=True,
        ),
        "user_type": st.column_config.SelectboxColumn(
            "User Type",
            options=list(MANAGED_USER_TYPES) + ["Super-admin"],
            width="small",
            disabled=True,
        ),
        "created_at": st.column_config.TextColumn(
            "Created At",
            width="medium",
            disabled=True,
        ),
    }

    table_state = st.dataframe(
        df,
        column_config=column_config,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="user_table",
    )

    selected_rows = table_state.get("selection", {}).get("rows", [])

    if selected_rows:
        selected_idx = selected_rows[0]

        try:
            selected_email = df.iloc[selected_idx]["email"]
            selected_name = df.iloc[selected_idx]["name"]
            selected_type = df.iloc[selected_idx]["user_type"]
        except IndexError:
            return

        if selected_type == "Super-admin":
            st.info("Super-admin can be viewed but cannot be altered or deleted.")
            return

        col1, col2, col3 = st.columns([1, 1, 3])
        with col1:
            if st.button(":material/edit: Alter User", width="stretch", key="alter_btn"):
                show_edit_user_dialog(selected_email, selected_name, selected_type)

        with col2:
            if st.button(":material/delete: Delete User", width="stretch", key="delete_btn"):
                show_delete_confirmation(selected_email)

        with col3:
            st.info(f"Selected: {selected_email}")
    else:
        st.caption("Select a row to enable Alter/Delete options")


render_user_management()
