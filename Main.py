from PIL import Image
import json
import re
from collections import Counter
from datetime import datetime, date
from io import BytesIO
from pathlib import Path
#import tasks
import pandas as pd
import streamlit as st
from openpyxl import load_workbook

st.set_page_config(
    page_title="Tikitar",
    page_icon=Image.open("static/tikitar-logo.webp"),
    layout="wide"
)
st.html(Path("style.css"))
#st.logo(
#    Image.open("static/CoinLogoTrans.PNG"),
#    size="large",
#    icon_image=None,
#)
# Initialize session state
if "task_select" not in st.session_state:
    st.session_state.task_select = ""
with st.container(horizontal=True):
    st.image(Image.open("static/tikitar-logo.webp"), width=80)
    st.header(f":blue[Tikitar-Task Automation : {st.session_state.task_select}]")
#link to all pages map with select box
all_pages = {
    "2B-Purchase-Reco":"pages/reco2B.py",
    "Reconcile Any Data": "pages/reco_any.py"
}

task_select = st.sidebar.selectbox("📋Choose a Task", list(all_pages.keys())
,placeholder="Type to Search for a Task...",key="task_select",index=None)
if task_select is not None:
    pg = st.navigation([st.Page(all_pages[task_select], title=task_select)])
    pg.run()
else:
    st.subheader("Welcome to Tikitar")
    st.success("Please select a task from the sidebar to get started")
    #st.image(Image.open("static/tikitar-logo.webp"), width=400)
