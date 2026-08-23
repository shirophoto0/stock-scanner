# =============================================================
# # Import และ Setup
# =============================================================
import streamlit as st
import pandas as pd
import yfinance as yf
import altair as alt
import numpy as np
import plotly.graph_objects as go
import os
import google.generativeai as genai
import io
import json
import requests
import gspread
import seaborn as sns
import matplotlib.pyplot as plt
import plotly.express as px
import datetime
import plotly
from datetime import date, datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials
from google.oauth2.service_account import Credentials
from plotly.subplots import make_subplots
from PIL import Image
import time
from gspread.exceptions import APIError


# =============================================================
# ฟังก์ชันเบื้องหลังทั้งหมด (เชื่อม Google Sheets, คำนวณ, โหลด/บันทึกข้อมูล)
# ถูกย้ายไปอยู่ที่ backend_functions.py แล้ว (Phase 1 ของการแยกไฟล์)
# =============================================================
from backend_functions import *

# =============================================================
# แท็บต่างๆ ของแอป ถูกย้ายไปอยู่คนละไฟล์ (Phase 2 ของการแยกไฟล์)
# =============================================================
from tab_gold import render_tab_gold
from tab_risk import render_tab_risk
from tab_funds import render_tab_funds
from tab_real_estate import render_tab_real_estate
from tab_overview import render_tab_overview
from tab_pvd import render_tab_pvd
from tab_tech import render_tab_tech
from tab_tfex import render_tab_tfex
from tab_stock import render_tab_stock

# 🆕 ระบบ Login แยกผู้ใช้
from auth import check_login, show_user_bar

# 🆕 ระบบธีมสี (Dark/Light) ของแอป
from theme import apply_theme

# --- ตั้งค่าหน้าเว็บ: ต้องอยู่เป็นคำสั่ง Streamlit คำสั่งแรกสุดของแอปเสมอ ---
st.set_page_config(layout="wide")

# --- ฉีดธีมสีเข้าไปก่อนเลย (ให้หน้า Login ก็มีธีมด้วย) ---
apply_theme()

# --- ต้องล็อกอินก่อนถึงจะใช้งานแอปต่อได้ ---
# (ถ้ายังไม่ล็อกอิน check_login() จะแสดงฟอร์ม Login แล้วหยุดการทำงานไว้ตรงนี้)
check_login()

# --- แสดงชื่อผู้ใช้ที่ login อยู่ + สวิตช์สลับโหมดสี + ปุ่ม Logout ไว้ที่แถบด้านข้าง ---
show_user_bar()

# =============================================================
# ส่วนเร่ิมต้นของ file
# =============================================================
# 📌 ตรวจสอบและดึงข้อมูลจากแท็บ JournalData มาเก็บไว้ใน session_state
# 🔧 แก้บั๊ก: เดิมจุดนี้มีโค้ดโหลด JournalData ซ้ำกันหลายรอบ (ทั้งเขียนเองตรงนี้ และเรียก
# load_journal() ซ้ำอีกทีข้างล่าง) โดยจุดที่เขียนเองไม่มีระบบลองใหม่อัตโนมัติเลย พอเจอโควตา
# Google Sheets ชั่วคราว (429 - พบบ่อยตอนสลับผู้ใช้ที่มีหลายแท็บยิงขอข้อมูลพร้อมกัน) จะพังทันที
# ตอนนี้เรียกใช้ load_journal()/load_portfolio() ที่มีระบบลองใหม่อัตโนมัติแล้วแทน ไม่ซ้ำซ้อนอีกต่อไป
if 'journal_data' not in st.session_state or not st.session_state.journal_data:
    load_journal()

if "my_portfolio" not in st.session_state:
    load_portfolio()

if 'dividend_data' not in st.session_state:
    st.session_state.dividend_data = load_dividend_data()

# กำหนดค่าเริ่มต้นเงินสดในพอร์ต หากยังไม่มีใน session_state
# 🔧 แก้บั๊ก: เดิมมีโค้ดคำนวณเงินสดจริงซ่อนอยู่ใน backend_functions.py แต่รันแค่ครั้งเดียว
# ตอนเซิร์ฟเวอร์เริ่มทำงาน (เพราะเป็นโค้ดระดับบนสุดของไฟล์ที่ import ไปใช้ ไม่ใช่โค้ดในไฟล์หลัก)
# ทำให้คนที่เปิดแอปทีหลังไม่ได้รับการคำนวณจริง ไปเจอค่า 0.0 สำรองแทน
# ตอนนี้ให้คำนวณค่าจริงตรงนี้เลย เพราะ App.py จะรันโค้ดนี้ใหม่ทุกครั้งที่มีคนเปิดแอป (ถูกต้องตามที่ควรจะเป็น)
if 'cash_balance' not in st.session_state:
    st.session_state.cash_balance = load_total_cash_balance()

##### Header UI Application box - Start ######
_app_title = st.session_state.get("app_title", "NJ-Wealth")
st.markdown(f"""
    <style>
    .custom-box {{
        background: linear-gradient(135deg, #FFFFFF 0%, #F1EEE8 100%);
        border: 1px solid #E5E1D8;
        border-radius: 16px;       /* มุมโค้งมน */
        padding: 24px;             /* ระยะห่างขอบด้านใน */
        box-shadow: 0 4px 16px rgba(45, 49, 66, 0.08);
        margin-bottom: 20px;
        border-left: 4px solid #7C9885;
    }}
    </style>

    <div class="custom-box">
        <h1 style="margin:0; font-size: 28px; font-family: 'Prompt', sans-serif; color: #7C9885 !important;">📈 Application {_app_title}</h1>
        <p style="margin-top: 10px; margin-bottom: 0; color: #6B7280;">📊 ระบบบริหารจัดการความมั่งคั่งและพอร์ตการลงทุนอัจฉริยะ (All-in-One Wealth & Portfolio Dashboard)</p>
    </div>
""", unsafe_allow_html=True)
##### Header UI Application box - Start ######

# จัดการ Session State เพื่อเก็บชื่อหุ้นที่เลือกไว้กลางระบบ
if "selected_ticker" not in st.session_state:
    st.session_state.selected_ticker = "KBANK"

# =============================================================
# 3. ฟังก์ชันคำนวณทางเทคนิคและสแกนหุ้น
# =============================================================


# สารตั้งต้นข้อมูลหุ้นกลุ่ม SET100
from constants import SET100_TICKERS

# =============================================================
# 4. ดึงข้อมูลและคำนวณฐานข้อมูลกลุ่ม SET100 โค้ดส่วนสแกนหุ้น (load_and_calculate_stock_data) และการทำ Filter
# ============================================================

#####################################
# Def Main ส่วนครอบ code ทั้งหมด
######################################
        
# --- Initialize Session State ---

def main():
    import plotly.express as px
    import plotly.graph_objects as go
    from datetime import date
    from datetime import datetime
    import pandas as pd
    import os

    fig_donut = None
    # 0. ประกาศตัวแปรป้องกัน UnboundLocalError เบื้องต้นทั้งหมด
    df_sector_map = pd.DataFrame()
    filtered_df = None

    # 1. เชื่อมต่อ Google Sheets (ปลอดภัยขึ้นด้วย try-except)
    try:
        client = get_gsheet_client()
    except Exception:
        client = None

    # 🌟 โหลดชีท Sector_Mapping จาก Google Sheets ไว้ล่วงหน้า
    try:
        if 'conn' in globals() or 'conn' in locals():
            df_sector_map = conn.read(worksheet="Sector_Mapping", ttl=600)
    except Exception:
        df_sector_map = pd.DataFrame()

    # 2. โหมด GitHub (ทำงานจบในตัว)
    if 'GOOGLE_APPLICATION_CREDENTIALS' in os.environ:
        print("GitHub Mode: กำลังเริ่มสแกน...")
        try:
            df_new = load_and_calculate_stock_data_optimized()
            
            # 🟢 เติม Sector อัตโนมัติใน GitHub Mode
            if not df_new.empty and 'Sector' in df_new.columns and not df_sector_map.empty:
                df_new['Sector'] = df_new['หุ้น'].apply(lambda x: get_sector_from_mapping(x, df_sector_map))
                
            save_to_gsheet(df_new)
            print("GitHub Mode: บันทึกข้อมูลสำเร็จ")
        except Exception as e:
            print(f"GitHub Mode Error: {e}")
        return # จบการทำงานทันที

    # 3. จัดการสถานะข้อมูลหุ้นด้วย st.session_state
    if 'df_all_stocks' not in st.session_state:
        try:
            st.session_state.df_all_stocks = load_from_gsheet()
        except Exception:
            st.session_state.df_all_stocks = pd.DataFrame()

    df_all_stocks = st.session_state.df_all_stocks

    # 🟢 เติม Sector อัตโนมัติให้ df_all_stocks ทันทีที่โหลดข้อมูลเสร็จ
    if not df_all_stocks.empty and not df_sector_map.empty:
        target_col = 'หุ้น' if 'หุ้น' in df_all_stocks.columns else ('Ticker' if 'Ticker' in df_all_stocks.columns else None)
        if target_col:
            try:
                df_all_stocks['Sector'] = df_all_stocks[target_col].apply(lambda x: get_sector_from_mapping(x, df_sector_map))
            except Exception:
                pass

    # ตรวจสอบก่อนแสดงผล (นำข้อความ error สีแดงออก เพื่อไม่ให้แจ้งเตือนค้างหน้าจอ)
    if not df_all_stocks.empty:
        df_to_show = filtered_df if filtered_df is not None else df_all_stocks
        # st.dataframe(df_to_show, use_container_width=True)
    else:
        # ปล่อยว่างไว้ ให้แท็บหุ้นเป็นตัวแจ้งเตือนหรือแสดงปุ่มกดดึงข้อมูลแทน
        pass
    # ==========================================================
    # ปรับโครงสร้าง Tab ระดับบนสุดของแอป (แบ่งหมวดหมู่ชัดเจน)
    # ==========================================================
    main_tab_system, main_tab_wealth = st.tabs([
        "📊 ระบบเทรด & สแกนหุ้น (Trading System)", 
        "🌐 ภาพรวมความมั่งคั่ง (Total Wealth)"
    ])

    # ==========================================================
    # TAB ที่ 1: ระบบเทรด & สแกนหุ้น (ย้าย 4 แทบเดิมมาไว้ข้างในนี้)
    # ==========================================================
    with main_tab_system:
        ###### ส่วนการสร้าง TAB หลัก ##################
        tab_stock, tab_tfex, tab_gold, tab_tech, tab_risk = st.tabs([
            "📊 หุ้น (Stock)", 
            "📈 TFEX", 
            "🟡 ทองคำ (Gold)", 
            "📉 วิเคราะห์กราฟเทคนิคอล", 
            "🛡️ Risk Management"
        ])

        ## ส่วน tab Gold #######
        with tab_gold:
            render_tab_gold(client)
        ######################## ส่วนวิเคราะห์แสกนกราฟหุ้น####################
        with tab_tech:
            render_tab_tech(tab_risk, df_sector_map, df_all_stocks)
        with tab_stock:
                           
            render_tab_stock()
            
        ###################################################################
        # # --- ฟังก์ชัน Main tap stock Finish---
        ###################################################################
        # 2. ส่วน TFEX
        with tab_tfex:
            render_tab_tfex()
    # ==========================================================
    # TAB ที่ 2: ภาพรวมความมั่งคั่ง (เพิ่มใหม่สำหรับสินทรัพย์อื่นๆ)
    # ==========================================================
    with main_tab_wealth:
        st.subheader("📊 ระบบจัดการสินทรัพย์ระยะยาวและความมั่งคั่งรวม (Net Worth)")
        
        # 1. ประกาศสร้าง 4 Tabs หลัก
        wealth_tab_overview, wealth_tab_funds, wealth_tab_form_general, wealth_tab_real_estate = st.tabs([
            "📈 ภาพรวม Net Worth & สัดส่วนสินทรัพย์",
            "💰 กองทุนรวม",
            "📝 บันทึกข้อมูล (PVD / สหกรณ์ / ประกัน / ธนาคาร)",
            "🏡 บันทึกอสังหาริมทรัพย์ (บ้าน / คอนโด)"
        ])

  
        # ==========================================
        # TAB ย่อยที่ 1: ภาพรวม Net Worth & สัดส่วนสินทรัพย์
        # ==========================================
        with wealth_tab_overview:
            render_tab_overview()

        # --- ส่วน UI สำหรับจัดการกองทุน (นำไปวางในหน้า App ของคุณ) ---
        
        # 1. Tab ซื้อกองทุนใหม่
        with wealth_tab_funds:
            render_tab_funds()
        
        # ==========================================
        # TAB ย่อยที่ 2: บันทึกข้อมูล (PVD / สหกรณ์ / ประกัน)
        # ==========================================
        with wealth_tab_form_general:
            render_tab_pvd()
        with wealth_tab_real_estate:
            render_tab_real_estate()

# ------------------------------
if __name__ == "__main__":
    main()
