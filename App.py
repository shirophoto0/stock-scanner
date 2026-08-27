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
from tab_retirement import render_tab_retirement
from tab_sector_rotation import render_tab_sector_rotation
from tab_backtest import render_tab_backtest
from tab_correlation import render_tab_correlation
from tab_document_analysis import render_tab_document_analysis
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

def _inject_pwa_meta():
    """
    🆕 ฉีดแท็ก PWA (manifest.json + icon) เข้าไปใน <head> ของหน้าเว็บจริงๆ ผ่าน JavaScript
    เพราะ Streamlit ไม่มีช่องทางแก้ไข <head> ของหน้าตรงๆ ให้ (st.markdown() แทรกเนื้อหาลงใน
    ส่วน body เท่านั้น ไม่ใช่ head) ใช้ st.components.v1.html() แทน เพราะเนื้อหาข้างในรันอยู่บน
    origin เดียวกับหน้าเว็บหลัก จึงเข้าถึง window.parent.document ได้ ทำให้ฉีดแท็กเข้า head จริง
    ของหน้าเว็บได้สำเร็จ ผลลัพธ์: กด "เพิ่มลงในหน้าจอโฮม" จากมือถือได้ เหมือนเป็นแอปจริง
    """
    st.components.v1.html(
        """
        <script>
        (function() {
            var head = window.parent.document.head;

            var manifestLink = window.parent.document.createElement('link');
            manifestLink.rel = 'manifest';
            manifestLink.href = './app/static/manifest.json';
            head.appendChild(manifestLink);

            var themeColor = window.parent.document.createElement('meta');
            themeColor.name = 'theme-color';
            themeColor.content = '#7C9885';
            head.appendChild(themeColor);

            // แท็กเฉพาะของ iOS Safari (ไม่รองรับ manifest.json เต็มรูปแบบ ต้องใช้แท็กเหล่านี้แทน)
            var appleCapable = window.parent.document.createElement('meta');
            appleCapable.name = 'apple-mobile-web-app-capable';
            appleCapable.content = 'yes';
            head.appendChild(appleCapable);

            var appleStatusBar = window.parent.document.createElement('meta');
            appleStatusBar.name = 'apple-mobile-web-app-status-bar-style';
            appleStatusBar.content = 'default';
            head.appendChild(appleStatusBar);

            var appleTitle = window.parent.document.createElement('meta');
            appleTitle.name = 'apple-mobile-web-app-title';
            appleTitle.content = 'Wealth Tracker';
            head.appendChild(appleTitle);

            var appleIcon = window.parent.document.createElement('link');
            appleIcon.rel = 'apple-touch-icon';
            appleIcon.href = './app/static/icon-192.png';
            head.appendChild(appleIcon);
        })();
        </script>
        """,
        height=0,
        width=0,
    )


def main():
    _inject_pwa_meta()

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
    # 🔧 ปรับปรุง: สลับลำดับแท็บใหญ่ ให้ "ภาพรวมความมั่งคั่ง" อยู่ซ้ายสุด ตามด้วย "ระบบเทรด & สแกนหุ้น"
    # (สลับแค่ลำดับตอนประกาศตรงนี้ ไม่ต้องย้ายเนื้อหาข้างในแท็บทั้ง 2 ก้อนด้านล่างเลย เพราะโค้ด
    # อ้างอิงผ่านชื่อตัวแปรอยู่แล้ว ไม่ขึ้นกับตำแหน่งที่ประกาศ)
    # 🆕 เพิ่มแท็บใหญ่ที่ 3 "🎯 เกษียณอายุ" ต่อจาก "ระบบเทรด & สแกนหุ้น" ตามที่ขอ
    main_tab_wealth, main_tab_system, main_tab_retirement = st.tabs([
        "🌐 ภาพรวมความมั่งคั่ง (Total Wealth)",
        "📊 ระบบเทรด & สแกนหุ้น (Trading System)",
        "🎯 เกษียณอายุ"
    ])

    # ==========================================================
    # TAB ที่ 1: ระบบเทรด & สแกนหุ้น (ย้าย 4 แทบเดิมมาไว้ข้างในนี้)
    # ==========================================================
    with main_tab_system:
        ###### ส่วนการสร้าง TAB หลัก ##################
        tab_stock, tab_tfex, tab_gold, tab_tech, tab_sector, tab_backtest, tab_correlation, tab_docai, tab_risk = st.tabs([
            "📊 หุ้น (Stock)", 
            "📈 TFEX", 
            "🟡 ทองคำ (Gold)", 
            "📉 วิเคราะห์กราฟเทคนิคอล", 
            "🔄 Sector Rotation",
            "🔬 Backtest",
            "🔗 Correlation",
            "🤖 วิเคราะห์เอกสาร AI",
            "🛡️ Risk Management"
        ])

        ## ส่วน tab Gold #######
        with tab_gold:
            render_tab_gold(client)
        ######################## ส่วนวิเคราะห์แสกนกราฟหุ้น####################
        with tab_tech:
            render_tab_tech(tab_risk, df_sector_map, df_all_stocks)
        with tab_sector:
            render_tab_sector_rotation(df_sector_map)
        with tab_backtest:
            render_tab_backtest()
        with tab_correlation:
            render_tab_correlation()
        with tab_docai:
            render_tab_document_analysis()
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

    # ==========================================================
    # TAB ที่ 3: 🎯 เกษียณอายุ (เพิ่มใหม่)
    # ==========================================================
    with main_tab_retirement:
        render_tab_retirement()

# ------------------------------
if __name__ == "__main__":
    main()
