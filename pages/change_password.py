import streamlit as st

from utils.auth_db import change_password


if not st.session_state.get("is_authenticated"):
    st.error("Please log in to change your password.")
    st.stop()


st.header(":material/lock_reset: Change Password")

with st.form("change_password_form", clear_on_submit=True):
    new_password = st.text_input(
        "New password",
        type="password",
        key="change_password_new",
    )
    confirm_password = st.text_input(
        "Confirm new password",
        type="password",
        key="change_password_confirm",
    )
    submitted = st.form_submit_button("Submit")

    if submitted:
        if not new_password:
            st.error("Password cannot be blank.")
        elif new_password != confirm_password:
            st.error("New password and confirm password do not match.")
        else:
            success, message = change_password(
                st.session_state.user_email,
                new_password,
            )
            if success:
                st.success(message)
            else:
                st.error(message)
