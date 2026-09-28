"""Application access control. Owner: Chaitanya."""

import hmac
import os

import streamlit as st


def require_access():
    required_password = os.getenv("GQB_APP_PASSWORD", "").strip()
    if not required_password:
        return "Local demo mode"
    if st.session_state.get("gqb_authenticated"):
        return "Protected access"

    st.markdown("## 🔐 GeoQueryBench protected workspace")
    st.write("Enter the project passcode to open the annotation workspace.")
    supplied = st.text_input("Passcode", type="password")
    if st.button("🔓 Open workspace", type="primary"):
        if hmac.compare_digest(supplied, required_password):
            st.session_state["gqb_authenticated"] = True
            st.rerun()
        else:
            st.error("The passcode is incorrect.")
    st.stop()
