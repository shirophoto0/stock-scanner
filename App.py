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

# =============================================================
# ส่วนเร่ิมต้นของ file
# =============================================================
# 📌 ตรวจสอบและดึงข้อมูลจากแท็บ JournalData มาเก็บไว้ใน session_state
# 🔧 แก้บั๊ก: ย้ายบล็อกนี้ออกมาจากใน calculate_rsi() (เดิมเยื้องผิดจนไปติดอยู่ในฟังก์ชันนั้น
# ทำให้โค้ดนี้ถูกเรียกซ้ำทุกครั้งที่คำนวณ RSI ของหุ้นแต่ละตัว แทนที่จะรันแค่ครั้งเดียวตอนเปิดแอป
# ซึ่งอาจเป็นสาเหตุที่ทำให้ยิง Google Sheets ซ้ำๆ จนโควตาเกินได้)
if 'journal_data' not in st.session_state or not st.session_state.journal_data:
    try:
        client = get_gsheet_client()
        # ดึงข้อมูลจากชีท JournalData ที่คุณใช้งานอยู่
        sheet_journal = get_cached_spreadsheet(client, 'MyStockData').worksheet('JournalData') 
        st.session_state.journal_data = sheet_journal.get_all_records()
    except Exception as e:
        st.session_state.journal_data = []
            
if "journal_data" not in st.session_state:
    load_journal()   # <--- ใส่บรรทัดนี้ลงไปครับ! มันจะช่วยดึงข้อมูลจากไฟล์มาโชว์ตอนเปิดแอป

if "my_portfolio" not in st.session_state:
    load_portfolio()

# เรียกโหลดข้อมูลทุกครั้งที่รันแอปฯ
if "my_portfolio" not in st.session_state:
    load_portfolio()

if "journal_data" not in st.session_state:
    load_journal()

if 'dividend_data' not in st.session_state:
    st.session_state.dividend_data = load_dividend_data()

# กำหนดค่าเริ่มต้นเงินสดในพอร์ต หากยังไม่มีใน session_state
if 'cash_balance' not in st.session_state:
    st.session_state.cash_balance = 0.0  # หรือใส่จำนวนเงินสดเริ่มต้นของคุณ เช่น 100000.0

##### Header UI Application box - Start ######
st.markdown("""
    <style>
    .custom-box {
        background-color: #fafbfc; /* เปลี่ยนสีพื้นหลังเบาๆ */
        border: 1px solid #e1e4e8; /* เส้นขอบ */
        border-radius: 16px;       /* มุมโค้งมน */
        padding: 20px;             /* ระยะห่างขอบด้านใน */
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05); /* เงาให้ดูลอยนูนขึ้นมา */
        margin-bottom: 20px;
    }
    </style>

    <div class="custom-box">
        <h1 style="margin:0; font-size: 28px;">📈 Application NJ-Wealth</h1>
        <p style="margin-top: 10px; margin-bottom: 0; color: #555;">📊 ระบบบริหารจัดการความมั่งคั่งและพอร์ตการลงทุนอัจฉริยะ (All-in-One Wealth & Portfolio Dashboard)</p>
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

# 1. ตั้งค่าหน้าเว็บต้องอยู่บรรทัดบนสุดเสมอ
st.set_page_config(layout="wide")

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
        ################################
            # 1. Slidebar (ตัวกรอง)
            with st.sidebar.expander("⚙️ เมนูตัวกรองหุ้น", expanded=True):
                max_pe = st.slider("1. ค่า P/E สูงสุด:", 5.0, 100.0, 100.0)
                min_dividend = st.slider("2. ปันผลขั้นต่ำ (%):", 0.0, 10.0, 0.0)
                rsi_range = st.slider("3. ช่วงค่า RSI:", 10.0, 90.0, (10.0, 90.0))
                
                strategy_option = st.selectbox(
                    "เลือกหน้าเทรด:",
                    options=[
                        "ไม่กรองเงื่อนไขนี้", 
                        "--- กลุ่ม RS Line ---",
                        "⭐ RS Line ตัดเส้น 0 ขึ้นมาแล้ว", 
                        "📈 RS Line ทำจุดสูงสุดใหม่ (RS New High)",
                        "🔥 RS Line ใกล้จะตัด 0 (จ่อระเบิด)", 
                        "--- กลุ่ม New High ---",
                        "3 Month High", 
                        "6 Month High", 
                        "52 Week High"
                    ]
                )
            
                # ตรวจสอบข้อมูลก่อนโชว์
                if df_all_stocks is not None and not df_all_stocks.empty:
                    # 1. เตรียมข้อมูลและทำความสะอาด
                    filtered_df = df_all_stocks.copy()
                    filtered_df.columns = filtered_df.columns.str.strip()
                    
                    # แปลงคอลัมน์ตัวเลข
                    numeric_cols = ['PE_Ratio', 'ปันผล_%', 'RSI_14', 'RS_Line']
                    for col in numeric_cols:
                        if col in filtered_df.columns:
                            filtered_df[col] = pd.to_numeric(filtered_df[col], errors='coerce').fillna(0)
                    
                    # แปลงคอลัมน์ Boolean (สำคัญมากสำหรับการกรองเงื่อนไข)
                    bool_cols = ['Is_RS_Above_0', 'Is_3M_High', 'Is_6M_High', 'Is_52W_High']
                    for col in bool_cols:
                        if col in filtered_df.columns:
                            filtered_df[col] = filtered_df[col].astype(str).str.lower().str.strip() == 'true'
            
                    # 2. กรองพื้นฐานด้วย Slider (จะกรองทับกันไปเรื่อยๆ)
                    if max_pe < 100:
                        filtered_df = filtered_df[filtered_df['PE_Ratio'] <= max_pe]
                    filtered_df = filtered_df[filtered_df['ปันผล_%'] >= min_dividend]
                    filtered_df = filtered_df[(filtered_df['RSI_14'] >= rsi_range[0]) & (filtered_df['RSI_14'] <= rsi_range[1])]
            
                    # 3. กำหนดคอลัมน์พื้นฐานและ Sort
                    show_columns = ['Ticker', 'ราคาล่าสุด', 'RSI_14', 'RS_Line', 'PE_Ratio', 'ปันผล_%']
                    sort_by_col = 'Ticker'
                    ascending_sort = True
            
                    # 4. กรองตามหน้าเทรด (Strategy)
                    if strategy_option == "⭐ RS Line ตัดเส้น 0 ขึ้นมาแล้ว":
                        filtered_df = filtered_df[filtered_df['Is_RS_Above_0'] == True]
                        show_columns.append('ตัดเส้น0ขึ้นมาแล้ว(วัน)')
                        sort_by_col, ascending_sort = 'ตัดเส้น0ขึ้นมาแล้ว(วัน)', True
                    
                    elif strategy_option == "📈 RS Line ทำจุดสูงสุดใหม่ (RS New High)":
                        filtered_df = filtered_df[filtered_df['RS_Line'] >= filtered_df['RS_Line_50D_Max']]
                        sort_by_col, ascending_sort = 'RS_Line', False
                    
                    elif strategy_option == "🔥 RS Line ใกล้จะตัด 0 (จ่อระเบิด)":
                        time_map = {"3 เดือน (60 วัน)": 60, "6 เดือน (120 วัน)": 120, "1 ปี (240 วัน)": 240}
                        time_choice = st.sidebar.selectbox("เลือกระยะเวลาจมใต้เส้น 0:", list(time_map.keys()), index=1)
                        min_days = time_map[time_choice]
                        filtered_df = filtered_df[(filtered_df['RS_Line'] <= 0.0) & (filtered_df['อยู่ใต้เส้น0มาแล้ว(วัน)'] >= min_days)]
                        show_columns.append('อยู่ใต้เส้น0มาแล้ว(วัน)')
                        sort_by_col, ascending_sort = 'RS_Line', False
                    
                    elif strategy_option == "3 Month High":
                        filtered_df = filtered_df[filtered_df['Is_3M_High'] == True]
                        show_columns.append('New_High_3M_มาแล้ว(วัน)')
                        sort_by_col, ascending_sort = 'New_High_3M_มาแล้ว(วัน)', True
                    
                    elif strategy_option == "6 Month High":
                        filtered_df = filtered_df[filtered_df['Is_6M_High'] == True]
                        show_columns.append('New_High_6M_มาแล้ว(วัน)')
                        sort_by_col, ascending_sort = 'New_High_6M_มาแล้ว(วัน)', True
                    
                    elif strategy_option == "52 Week High":
                        filtered_df = filtered_df[filtered_df['Is_52W_High'] == True]
                        show_columns.append('New_High_52W_มาแล้ว(วัน)')
                        sort_by_col, ascending_sort = 'New_High_52W_มาแล้ว(วัน)', True
            
                    # 5. แสดงผล
                    results_container = st.empty() 
                
                
                    # กรองคอลัมน์ที่เลือกให้โชว์
                    valid_cols = [c for c in show_columns if c in filtered_df.columns]
                    
            ##########################
            # 4. ส่วนการเลือกหุ้น (เป็นตัวกลางส่งค่าไป Fundamental และ กราฟ)
            
            st.subheader("🔍 1. วิเคราะห์กราฟเทคนิคัลอัจฉริยะ (Multi-Timeframe & RS vs SET Index)")

            # ส่วนจัดการการโหลดข้อมูล (ปรับแก้ให้เข้ากับ Session State)
            if st.button("🔄 อัปเดตข้อมูลใหม่ (ดึงจาก Yahoo)"):
                with st.spinner("กำลังดึงข้อมูล..."):
                    df_new = load_and_calculate_stock_data()
                    
                    # 🟢 เติม Sector อัตโนมัติหลังกดอัปเดตจาก Yahoo
                    if not df_new.empty and 'df_sector_map' in locals() and not df_sector_map.empty:
                        target_col = 'หุ้น' if 'หุ้น' in df_new.columns else 'Ticker'
                        if target_col in df_new.columns:
                            df_new['Sector'] = df_new[target_col].apply(lambda x: get_sector_from_mapping(x, df_sector_map))
                    
                    save_to_gsheet(df_new)
                    
                    # 📌 อัปเดตข้อมูลลง Session State เพื่อให้หน้าเว็บรับข้อมูลชุดใหม่ทันที
                    st.session_state.df_all_stocks = df_new 
                    st.success("อัปเดตข้อมูลจาก Yahoo สำเร็จ!")
                    st.rerun()  # 📌 สั่งรีเฟรชหน้าเบาๆ ให้กราฟและ Selectbox ด้านล่างเปลี่ยนตาม
            else:
                # 📌 ดึงข้อมูลจาก Session State ที่โหลดไว้แล้วจาก def main() แทนการโหลดซ้ำจาก Google Sheets
                df_all_stocks = st.session_state.get('df_all_stocks', pd.DataFrame())
                
                # ถ้าใน Session State ยังว่างเปล่า ค่อยดึงจาก Sheet อีกรอบ
                if df_all_stocks.empty:
                    df_all_stocks = load_from_gsheet()
                    st.session_state.df_all_stocks = df_all_stocks
            
            col_input, col_metrics = st.columns([1, 3])
            
            with col_input:
                all_tickers = [t.replace('.BK', '') for t in SET100_TICKERS]
                
                # 1. กำหนดค่าเริ่มต้นจาก Session State กลาง
                current_selected = st.session_state.get("selected_ticker", "KBANK")
                
                # 2. สร้าง Selectbox สำหรับเลือกหุ้น
                # 🔧 แก้บั๊ก: ใช้ Key แบบ Dynamic (เปลี่ยนตามหุ้นที่เลือกอยู่) เหมือนแท็บ Risk Management
                # เพื่อไม่ให้ dropdown "จำค่าเก่าของตัวเอง" ค้างไว้ ไม่ว่าหุ้นจะถูกเปลี่ยนมาจากทางไหนก็ตาม
                # (จากการพิมพ์ในนี้เอง, จากการกดตาราง, หรือจากแท็บ Risk Management)
                ticker_input = st.selectbox(
                    "เลือกหรือพิมพ์ชื่อหุ้นที่ต้องการดูราคากราฟรายละเอียด:", 
                    options=all_tickers, 
                    index=all_tickers.index(current_selected) if current_selected in all_tickers else 0,
                    key=f"tech_stock_selectbox_{current_selected}"
                )
                
                # 3. ถ้าค่าที่เลือกเปลี่ยน ให้บันทึกเข้า session_state แล้ว Rerun ทันที
                if ticker_input != current_selected:
                    st.session_state.selected_ticker = ticker_input
                    st.rerun() 
            
            # ใช้ค่ากลางจาก session_state
            selected_ticker = st.session_state.selected_ticker 
            ticker = f"{selected_ticker}.BK"
            
            # ใช้ฟังก์ชัน Cache ดึงข้อมูล
            info = get_cached_stock_info(ticker) 
            stock_data = yf.Ticker(ticker) 
                
            ##### link web set and trading view ########
            col1, col2 = st.columns(2)
            
            with col1:
                set_url = f"https://www.set.or.th/th/market/product/stock/quote/{st.session_state.selected_ticker}/company-profile/information"
                st.link_button("🌐 ข้อมูล SET", set_url, use_container_width=True)
            
            with col2:
                tv_url = f"https://www.tradingview.com/chart/?symbol=SET%3A{st.session_state.selected_ticker}"
                st.link_button("📈 กราฟ TradingView", tv_url, use_container_width=True)
            
            st.markdown("---")
            
            # ==========================================
            # 5. Fundamental Dashboard (ให้อยู่ระดับชิดซ้ายปกติ)
            # ==========================================
            # 5. Fundamental Dashboard (พร้อมระบบ Try-Catch และ Fallback ป้องกันเว็บพัง)
            st.markdown("#### 📊 Fundamental Growth Dashboard (คัดกรองพลังขับเคลื่อนตามสูตร SEPA)")
            
            # ฟังก์ชันดึงข้อมูลแบบปลอดภัยด้วย Try-Catch
            def safe_get_stock_fundamentals(ticker_symbol):
                try:
                    # ดึงข้อมูลจากฟังก์ชันแคชเดิมของคุณ
                    stock_info = get_cached_stock_info(ticker_symbol)
                    if stock_info and isinstance(stock_info, dict) and len(stock_info) > 0:
                        return stock_info, True
                except Exception as e:
                    pass
                
                # Fallback: ถ้าดึงไม่ได้ ให้ส่งค่าว่างและบอกสถานะว่าดึงไม่สำเร็จ
                return {}, False

            # เรียกใช้งานฟังก์ชัน
            info, is_success = safe_get_stock_fundamentals(ticker)
            
            if is_success and info:
                # ดึงงบอย่างปลอดภัย
                m_cap = info.get('marketCap', None)
                rev_growth = info.get('quarterlyRevenueGrowth', info.get('revenueGrowth', None))
                eps_growth = info.get('quarterlyEarningsGrowth', info.get('earningsGrowth', None))
                gross_margins = info.get('grossMargins', None)
                profit_margins = info.get('profitMargins', None)
                roe = info.get('returnOnEquity', None)
                pb_ratio = info.get('priceToBook', None)
            
                f_col1, f_col2 = st.columns(2)
                with f_col1:
                    st.write("##### 📈 ตัวเลขการเจริญเติบโต (Growth Metrics)")
                    if rev_growth is not None:
                        st.metric("อัตราเติบโตของรายได้ (Revenue Growth YoY)", f"{rev_growth * 100:.2f} %")
                    else:
                        st.write("• **Revenue Growth YoY:** ไม่มีข้อมูลระบบส่งตรง")
                        
                    if eps_growth is not None:
                        is_sepa_growth = "🔥 ผ่านเกณฑ์หุ้นเติบโตแรง (>20%)" if eps_growth >= 0.20 else "ปกติ"
                        st.metric("อัตราเติบโตของกำไรต่อหุ้น (EPS Growth YoY)", f"{eps_growth * 100:.2f} %", delta=is_sepa_growth)
                    else:
                        st.write("• **EPS Growth YoY:** ไม่มีข้อมูลระบบส่งตรง")
                        
                    if m_cap is not None:
                        st.write(f"🏢 **มูลค่าบริษัท (Market Cap):** {m_cap / 1_000_000_000:,.2f} พันล้านบาท")
            
                with f_col2:
                    st.write("##### 💰 อัตราการทำกำไรและมูลค่า (Profitability & Valuation)")
                    if gross_margins is not None:
                        st.write(f"• **อัตรากำไรขั้นต้น (Gross Margin):** {gross_margins * 100:.2f} %")
                    if profit_margins is not None:
                        st.write(f"• **อัตรากำไรสุทธิ (Net Profit Margin):** {profit_margins * 100:.2f} %")
                    if roe is not None:
                        st.write(f"• **ผลตอบแทนต่อส่วนผู้ถือหุ้น (ROE):** {roe * 100:.2f} %")
                    if pb_ratio is not None:
                        st.write(f"• **ราคาต่อมูลค่าทางบัญชี (P/B Ratio):** {pb_ratio:.2f} เท่า")
                        
                    pe_value = info.get('trailingPE')
                    if pe_value is not None:
                        st.write(f"• **ราคาต่อกำไรสุทธิ (P/E Ratio ยืนยัน):** {pe_value:.2f} เท่า")
                    else:
                        st.write("• **ราคาต่อกำไรสุทธิ (P/E Ratio ยืนยัน):** ไม่มีข้อมูล")
                
                st.info("💡 **ข้อแนะนำจากระบบ:** หุ้นซุปเปอร์สต็อกตามสไตล์ Mark Minervini มักจะมี EPS Growth ขยายตัวมากกว่า 20%-25% ขึ้นไป ควบคู่กับราคาหุ้นที่ยกฐานยืนเหนือเส้น EMA ขาขึ้น")
            
            else:
                # กรณีดึงข้อมูลไม่สำเร็จ แสดงกล่องแจ้งเตือนแบบนุ่มนวล พร้อมปุ่มให้ลองกดโหลดใหม่เฉพาะจุด
                st.warning(f"⚠️ ขณะนี้ Yahoo Finance ไม่ตอบสนองต่อการดึงข้อมูลพื้นฐานของหุ้น `{selected_ticker}` (อาจติดปัญหา Rate Limit หรือการเชื่อมต่อ)")
                
                if st.button(f"🔄 ลองดึงข้อมูล {selected_ticker} อีกครั้ง"):
                    # เคลียร์ Cache เฉพาะตัวหรือสั่ง Rerun ให้ลองใหม่
                    if 'get_cached_stock_info' in globals() and hasattr(get_cached_stock_info, 'clear'):
                        get_cached_stock_info.clear()
                    st.rerun()
                    
            # 3. แสดงผลตารางและกราฟ
            # ... (เอาโค้ดส่วนแสดงผล st.dataframe และ st.plotly_chart มาใส่ตรงนี้) ...
            #####################################
        
            with st.expander ("⚙️ ตั้งค่าการแสดงผลกราฟ"):
                col_tf, col_period = st.columns([1, 1])
                
                tf_mapping = {
                    "1 วัน (Day)": "1d",
                    "1 สัปดาห์ (Week)": "1wk",
                    "1 เดือน (Month)": "1mo"
                }
                # 🔧 ตัดตัวเลือก 1hr/4hr ออก เพราะ Yahoo Finance ไม่มีข้อมูลราคารายชั่วโมงสำหรับหุ้นไทย (.BK)
                # ทำให้กราฟไม่ขึ้น — มีลิงก์ TradingView ไว้สำหรับดูกราฟช่วงเวลาสั้นแทนอยู่แล้ว
                # เพิ่ม Mapping นี้ไว้ก่อนส่วนที่เรียก stock_data.history
                p_map = {
                    "6 เดือน (6m)": "6mo", 
                    "1 ปี (1y)": "1y", 
                    "5 ปี (5y)": "5y", 
                    "ตั้งแต่เข้าตลาด (All Time)": "max"
                }
                
                
                with col_tf:
                    tf_select = st.pills("เลือกความถี่แท่งเทียน (Timeframe):", options=list(tf_mapping.keys()), default="1 วัน (Day)")
                    if not tf_select:
                        tf_select = "1 วัน (Day)"
                    selected_tf = tf_mapping[tf_select]
                
                with col_period:
                    period_options = ["6 เดือน (6m)", "1 ปี (1y)", "5 ปี (5y)", "ตั้งแต่เข้าตลาด (All Time)"]
                    chart_period = st.pills("เลือกช่วงเวลากราฟ (ทั้งหมด):", options=period_options, default="6 เดือน (6m)")
                    if not chart_period:
                        chart_period = "6 เดือน (6m)"
                
                # =============================================================
                # 6. กราฟเทคนิคัล
                # =============================================================
                try:
                    ticker = f"{st.session_state.selected_ticker}.BK"
                    stock_data = yf.Ticker(ticker)
                    set_market = yf.Ticker("^SET.BK")
                    info = get_cached_stock_info(ticker)
                    
                    
                    # 3.1 กำหนดช่วงเวลา 
                    p_map = {"6 เดือน (6m)": "6mo", "1 ปี (1y)": "1y", "5 ปี (5y)": "5y", "ตั้งแต่เข้าตลาด (All Time)": "max"}
                    selected_period = p_map.get(chart_period, "1y")
                    actual_interval = selected_tf
                
                    # 3.2 ดึงข้อมูล
                    hist_chart = stock_data.history(period=selected_period, interval=actual_interval)
                    hist_market = set_market.history(period=selected_period, interval=actual_interval)
                    
                    # กรณีดึงข้อมูลมาแล้วว่าง ให้ลองถอยกลับไปดึง period ที่สั้นลง (Fallback)
                    if hist_chart.empty:
                        hist_chart = stock_data.history(period="6mo", interval=actual_interval)
                        hist_market = set_market.history(period="6mo", interval=actual_interval)
                
                    if not hist_chart.empty:
                        # ปรับ Timezone และรวมข้อมูล
                        if hist_chart.index.tz is not None: hist_chart.index = hist_chart.index.tz_localize(None)
                        if not hist_market.empty and hist_market.index.tz is not None: hist_market.index = hist_market.index.tz_localize(None)
                
                        hist_market_close = hist_market['Close'].to_frame(name='Market_Close')
                        chart_combined = hist_chart[['Open', 'High', 'Low', 'Close']].join(hist_market_close, how='inner')
                        
                        if len(chart_combined) >= 5:  # 🔧 กันเหนียว: ถ้าข้อมูลน้อยเกินไป (เช่น Timeframe 1ชม./4ชม. ไม่มีข้อมูล) ให้แจ้งเตือนแทนการวาดกราฟเปล่า
                            # คำนวณค่าเทคนิคัล
                            base_stock = chart_combined['Close'].iloc[0]
                            chart_combined['Stock_Perf'] = ((chart_combined['Close'] - base_stock) / base_stock) * 100
                            
                            base_market = chart_combined['Market_Close'].iloc[0]
                            market_perf = ((chart_combined['Market_Close'] - base_market) / base_market) * 100
                            chart_combined['RS_Line'] = chart_combined['Stock_Perf'] - market_perf
                            chart_combined['RS_EMA20'] = chart_combined['RS_Line'].ewm(span=20, adjust=False).mean()
                            chart_combined['Is_Above_0'] = chart_combined['RS_Line'] > 0
                            chart_combined['Days_Above_0'] = chart_combined['Is_Above_0'].groupby((~chart_combined['Is_Above_0']).cumsum()).cumsum()
                            chart_combined['EMA10'] = chart_combined['Close'].ewm(span=10, adjust=False).mean()
                            chart_combined['EMA20'] = chart_combined['Close'].ewm(span=20, adjust=False).mean()
                            chart_combined['EMA50'] = chart_combined['Close'].ewm(span=50, adjust=False).mean()
                            chart_combined['EMA100'] = chart_combined['Close'].ewm(span=100, adjust=False).mean()
                            chart_combined['EMA200'] = chart_combined['Close'].ewm(span=200, adjust=False).mean()
                
                            # สร้างตารางวันหยุด
                            missing_dates = pd.date_range(start=chart_combined.index.min(), end=chart_combined.index.max(), freq='D').difference(pd.to_datetime(chart_combined.index.date))
                
                            # 3.5 แสดง Metrics
                            latest_price_single = info.get('currentPrice', chart_combined['Close'].iloc[-1])
                            latest_rs_status = "แข็งแกร่งกว่าตลาด (Outperform)" if chart_combined['RS_Line'].iloc[-1] > chart_combined['RS_EMA20'].iloc[-1] else "อ่อนแอกว่าตลาด (Underperform)"
                            with col_metrics:
                                m1, m2, m3, m4 = st.columns([2, 1, 1.5, 1]) 
                            
                                # ปรับส่วนดึงข้อมูลปันผล
                                raw_div = info.get('dividendYield') or info.get('trailingAnnualDividendYield', 0)
                            
                                if raw_div:
                                    if raw_div > 1:
                                        div_display = f"{raw_div:.2f}%"
                                    else:
                                        div_display = f"{raw_div * 100:.2f}%"
                                else:
                                    div_display = "N/A"
            
                                # --- m1: ชื่อบริษัท ---
                                m1.caption("ชื่อบริษัท")
                                m1.write(f"**{info.get('longName', 'N/A')}**")
                            
                                # --- m2: ราคาล่าสุด ---
                                m2.caption("ราคาล่าสุด")
                                m2.write(f"**{latest_price_single:.2f} บ.**")
                            
                                # --- m3: สถานะ RS ---
                                m3.caption("สถานะ RS")
                                m3.write(f"**{'แข็งแกร่งกว่าตลาด' if chart_combined['RS_Line'].iloc[-1] > chart_combined['RS_EMA20'].iloc[-1] else 'อ่อนแอกว่าตลาด'}**")
                            
                                # --- m4: ปันผล (Yield) ---
                                m4.caption("ปันผล (Yield)")
                                m4.write(f"**{div_display}**")
                                    
                            # 3.4 วาดกราฟ
                            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_width=[0.3, 0.7])
                            fig.add_trace(go.Candlestick(x=chart_combined.index, open=chart_combined['Open'], high=chart_combined['High'], low=chart_combined['Low'], close=chart_combined['Close'], name='Price'), row=1, col=1)
                        
                            ema_hover_config = dict(bgcolor='rgba(255, 255, 255, 0.20)', bordercolor='rgba(0,0,0,0)')
                            fig.add_trace(go.Scatter(x=chart_combined.index, y=chart_combined['EMA10'], line=dict(color='orange', width=1.5), name='EMA 10', hovertemplate="EMA10: %{y:.2f}<extra></extra>", hoverlabel=ema_hover_config), row=1, col=1)
                            fig.add_trace(go.Scatter(x=chart_combined.index, y=chart_combined['EMA20'], line=dict(color='magenta', width=1.5), name='EMA 20', hovertemplate="EMA20: %{y:.2f}<extra></extra>", hoverlabel=ema_hover_config), row=1, col=1)
                            fig.add_trace(go.Scatter(x=chart_combined.index, y=chart_combined['EMA50'], line=dict(color='blue', width=1.5), name='EMA 50', hovertemplate="EMA50: %{y:.2f}<extra></extra>", hoverlabel=ema_hover_config), row=1, col=1)
                            fig.add_trace(go.Scatter(x=chart_combined.index, y=chart_combined['EMA100'], line=dict(color='brown', width=1.5), name='EMA 100', hovertemplate="EMA100: %{y:.2f}<extra></extra>", hoverlabel=ema_hover_config), row=1, col=1)
                            fig.add_trace(go.Scatter(x=chart_combined.index, y=chart_combined['EMA200'], line=dict(color='black', width=2.0), name='EMA 200', hovertemplate="EMA200: %{y:.2f}<extra></extra>", hoverlabel=ema_hover_config), row=1, col=1)
                        
                            # กราฟ RS Line (Purple)
                            fig.add_trace(go.Scatter(
                                x=chart_combined.index, 
                                y=chart_combined['RS_Line'], 
                                line=dict(color='#9c27b0', width=2), 
                                name='RS Line',
                                hovertemplate="RS Line: %{y:.2f}%<extra></extra>"
                            ), row=2, col=1)
                        
                            # กราฟ RS EMA 20 (Orange Dash)
                            fig.add_trace(go.Scatter(
                                x=chart_combined.index, 
                                y=chart_combined['RS_EMA20'], 
                                line=dict(color='#ff9800', width=1.5, dash='dot'), 
                                name='RS EMA20',
                                hovertemplate="RS EMA20: %{y:.2f}%<extra></extra>"
                            ), row=2, col=1)
                
                            # เส้นอ้างอิงแนวนอน (Hline)
                            fig.add_hline(y=0, line_dash="solid", line_color="grey", line_width=1, row=2, col=1)
                            fig.add_hline(y=20, line_dash="dot", line_color="rgba(255, 0, 0, 0.3)", row=2, col=1)
                            fig.add_hline(y=-20, line_dash="dot", line_color="rgba(0, 0, 255, 0.3)", row=2, col=1)
                
                            # 1. ตั้งค่า Candlestick ให้แสดงข้อมูลพื้นฐาน
                            fig.update_xaxes(
                                    rangebreaks=[dict(values=missing_dates)],
                                    showgrid=True,
                                    gridcolor='rgba(150,150,150,0.08)',
                                    showspikes=True,
                                    spikecolor='#888',
                                    spikethickness=1,
                                    spikesnap='cursor',
                                    spikemode='across'
                                )
                            fig.update_yaxes(
                                    showgrid=True,
                                    gridcolor='rgba(150,150,150,0.08)',
                                    showspikes=True,
                                    spikecolor='#888',
                                    spikethickness=1,
                                    spikesnap='cursor',
                                    spikemode='across'
                                )
                        
                            fig.update_layout(
                        height=800,
                        margin=dict(l=40, r=60, t=50, b=40), # เพิ่มขอบขวา (r=60) เพื่อให้มีที่ว่างสำหรับป้ายราคา
                        hovermode='x unified',
                        xaxis_rangeslider_visible=False,
                        # ปรับแกน Y ให้แสดงป้ายราคาที่ "ชี้" ไปที่ราคาล่าสุด
                        yaxis=dict(
                            showspikes=False, # ปิด spike แกน Y เพื่อไม่ให้บังป้ายราคา
                            side='right',     # ย้ายแกนราคาไปไว้ขวาเหมือน TradingView
                            showgrid=True,
                        )
                    )
                            st.plotly_chart(fig, use_container_width=True)
                        else:
                            st.warning(f"⚠️ ไม่มีข้อมูลกราฟเพียงพอสำหรับ Timeframe นี้ (พบแค่ {len(chart_combined)} แท่งเทียน) "
                                             f"อาจเป็นเพราะ Yahoo Finance ไม่มีข้อมูลรายชั่วโมง/4ชั่วโมงของหุ้นไทยตัวนี้ "
                                             f"ลองเปลี่ยนเป็น Timeframe รายวัน (Day) แทนครับ")
                    # (แนะนำให้พี่อ้ำใช้โค้ดเดิมในส่วนนี้ได้เลยครับ ผมตัดมาให้สั้นลงเพื่อดูโครงสร้าง)
                    # ...
                
                
                except Exception as e:
                    st.error(f"⚠️ เกิดข้อผิดพลาดในการวาดกราฟ: {str(e)}")
            # ==========================================
            # เริ่ม Tab ถัดไป (เช่น tab_risk) ตรงนี้
            # ==========================================
            with tab_risk:
                render_tab_risk()
            # =============================================================
            # 7. ผลลัพธ์การสแกน (ใช้ filtered_df ที่กรองผ่าน Sidebar มาแล้ว)
            # =============================================================
            with st.expander("📊 ผลลัพธ์การสแกน"):
                # 1. เช็คข้อมูลจาก Sidebar (ถ้าไม่มีให้ใช้ df_all_stocks)
                # แก้ไขบรรทัดที่ 1152 เป็นแบบนี้ครับ
                try:
                    # พยายามใช้ filtered_df ถ้ามี และมีค่า
                    if 'filtered_df' in locals() and filtered_df is not None:
                        df_scan = filtered_df.copy()
                    # ถ้าไม่มี ให้ใช้ df_all_stocks แต่ต้องเช็คว่ามีอยู่จริงด้วย
                    elif 'df_all_stocks' in locals() and df_all_stocks is not None:
                        df_scan = df_all_stocks.copy()
                    else:
                        # กรณีแย่ที่สุด คือไม่มีข้อมูลเลย ให้สร้าง DataFrame เปล่าขึ้นมา
                        df_scan = pd.DataFrame()
                        st.error("ไม่พบข้อมูลหุ้นในระบบ กรุณาตรวจสอบการโหลดข้อมูล")
                except Exception as e:
                    df_scan = pd.DataFrame()
                    st.error(f"เกิดข้อผิดพลาดในการเตรียมตาราง: {e}")
            
                df_scan = filtered_df.copy() if filtered_df is not None else df_all_stocks.copy()
                
                # 2. กรองตาม Strategy ที่เลือก (ถ้ามี)
                if strategy_option == "3 Month High":
                    final_sorted_df = df_scan[df_scan['Is_3M_High'] == True]
                elif strategy_option == "6 Month High":
                    final_sorted_df = df_scan[df_scan['Is_6M_High'] == True]
                elif strategy_option == "52 Week High":
                    final_sorted_df = df_scan[df_scan['Is_52W_High'] == True]
                elif strategy_option == "⭐ RS Line ตัดเส้น 0 ขึ้นมาแล้ว":
                    final_sorted_df = df_scan[df_scan['Is_RS_Above_0'] == True]
                elif strategy_option == "📈 RS Line ทำจุดสูงสุดใหม่ (RS New High)":
                    final_sorted_df = df_scan[df_scan['RS_Line'] >= df_scan['RS_Line_50D_Max']]
                else:
                    final_sorted_df = df_scan
            
                # 3. แสดงผลหัวข้อ
                st.subheader(f"📊 ผลลัพธ์การสแกน ({strategy_option}): พบทั้งหมด {len(final_sorted_df)} ตัว")
                
                # 4. เลือกคอลัมน์ที่จะแสดง (Whitelist)
                fixed_cols = ['Ticker', 'ราคาล่าสุด', 'RSI_14', 'RS_Line', 'PE_Ratio', 'ปันผล_%']
                strategy_cols_map = {
                    "3 Month High": ['New_High_3M_มาแล้ว(วัน)'], 
                    "6 Month High": ['New_High_6M_มาแล้ว(วัน)'],
                    "52 Week High": ['New_High_52W_มาแล้ว(วัน)'],
                    "⭐ RS Line ตัดเส้น 0 ขึ้นมาแล้ว": ['ตัดเส้น0ขึ้นมาแล้ว(วัน)'],
                    "🔥 RS Line ใกล้จะตัด 0 (จ่อระเบิด)": ['อยู่ใต้เส้น0มาแล้ว(วัน)']
                }
                
                cols_to_show = fixed_cols + strategy_cols_map.get(strategy_option, [])
                existing_cols = [c for c in cols_to_show if c in final_sorted_df.columns]
                df_display = final_sorted_df[existing_cols].copy()
            
                # 5. บังคับแปลงตัวเลขเพื่อจัดรูปแบบ
                numeric_cols = ['PE_Ratio', 'ปันผล_%', 'ราคาล่าสุด', 'RSI_14', 'RS_Line']
                for col in numeric_cols:
                    if col in df_display.columns:
                        df_display[col] = pd.to_numeric(df_display[col], errors='coerce')
                
                # 6. จัดรูปแบบตาราง
                styled_df = df_display.style.format({
                    'ราคาล่าสุด': '{:.2f}', 'RSI_14': '{:.2f}', 'RS_Line': '{:.2f}', 
                    'PE_Ratio': '{:.2f}', 'ปันผล_%': '{:.2f}'
                }, na_rep='-').apply(highlight_rsi_zones, axis=1)
            
                # 7. แสดงตารางและดึง Event
                event = st.dataframe(
                    styled_df,
                    use_container_width=True,
                    selection_mode="single-row",
                    on_select="rerun",
                    key="stock_table"
                )
                
                # 8. ดึงข้อมูลการเลือกหุ้น (สรุปรวมเหลือบล็อกเดียว)
                if event.selection and "rows" in event.selection and event.selection["rows"]:
                    selected_index = event.selection["rows"][0]
                    
                    # ตรวจสอบว่า Index อยู่ในขอบเขตข้อมูลปัจจุบันหรือไม่
                    if selected_index < len(final_sorted_df):
                        clicked_ticker = final_sorted_df.iloc[selected_index]['Ticker']
                        
                        # ถ้าหุ้นที่เลือกเปลี่ยนไปจากเดิม ถึงจะสั่ง Rerun
                        if st.session_state.get("selected_ticker") != clicked_ticker:
                            st.session_state.selected_ticker = clicked_ticker
                            st.rerun()
                    else:
                        # กรณีตารางถูกกรองจน Index เดิมหายไป (เช่น สลับหน้าเทรด) 
                        # ล้างค่า Selection เก่าออกเพื่อความปลอดภัย
                        if st.session_state.get("selected_ticker"):
                            del st.session_state.selected_ticker
                            st.rerun()
                            
        st.markdown("---") # เส้นคั่น เพื่อแยกส่วนกับตารางด้านบนให้ชัด
            
        # 1. ส่วนหุ้น
        with tab_stock:
                           
                ##########################
                # 8.แท็บข้อมูล
                ##############################  
                st.markdown("---") # เส้นคั่น เพื่อแยกส่วนกับตารางด้านบนให้ชัด
                st.subheader("🛠 ระบบจัดการข้อมูลและวิเคราะห์พอร์ต")
                
                # 1. สร้าง Tabs (จัดรวม แผนและ Alert ไว้ใน tab เดียวกัน)
                tab_dashboard, tab_portfolio, tab_dividend, tab_journal, tab_plan = st.tabs([
                    "📈 Dashboard", "📊 พอร์ตโฟลิโอ", "💰 ข้อมูลปันผล", "📖 สมุดบันทึก", "📝 แผนและ Alert"
                ])
                
                ##############################
                with tab_dashboard:
                    st.markdown("### 📊 Trading Performance Dashboard")
                    
                    # 1. ตรวจสอบและดึงข้อมูลจาก Google Sheets ชีต 'JournalData' ถ้า session_state ยังไม่มี
                    if 'journal_data' not in st.session_state or not st.session_state['journal_data']:
                        try:
                            client = get_gsheet_client()
                            sheet_journal = get_cached_spreadsheet(client, 'MyStockData').worksheet('JournalData') 
                            raw_journal_data = sheet_journal.get_all_records()
                            if raw_journal_data:
                                st.session_state['journal_data'] = raw_journal_data
                        except Exception as e:
                            st.error(f"❌ ไม่สามารถดึงข้อมูลประวัติการเทรดจาก Google Sheets ได้: {e}")
                
                    # 2. ตรวจสอบข้อมูลใน session_state เพื่อนำมาแสดงผล
                    if not st.session_state.get('journal_data'):
                        st.info("ยังไม่มีข้อมูลรายการเทรดครับ กรุณาตรวจสอบการเชื่อมต่อ Google Sheets หรือเพิ่มข้อมูลรายการเทรดก่อน")
                    else:
                        df_journal = pd.DataFrame(st.session_state['journal_data'])
                        
                        # ป้องกันกรณีชื่อคอลัมน์มีช่องว่างติดมา
                        df_journal.columns = [str(c).strip() for c in df_journal.columns]
                        
                        if 'วันที่' in df_journal.columns:
                            df_journal['วันที่'] = pd.to_datetime(df_journal['วันที่'], errors='coerce')
                        
                        if 'สถานะ' in df_journal.columns:
                            df_closed = df_journal[df_journal['สถานะ'] == 'Closed (ขายแล้ว)'].copy()
                        else:
                            df_closed = pd.DataFrame()
                            
                        if df_closed.empty:
                            st.info("ยังไม่มีข้อมูลรายการที่ปิดสถานะ (Closed) เพื่อสรุปผลงานครับ")
                        else:
                            # ทำความสะอาดข้อมูลตัวเลข
                            df_closed['กำไร/ขาดทุน (บาท)'] = pd.to_numeric(df_closed['กำไร/ขาดทุน (บาท)'].astype(str).str.replace(',', ''), errors='coerce')
                            df_closed['ต้นทุน (บาท)'] = pd.to_numeric(df_closed['ต้นทุน (บาท)'].astype(str).str.replace(',', ''), errors='coerce')
                            
                            df_clean = df_closed.dropna(subset=['กำไร/ขาดทุน (บาท)', 'ต้นทุน (บาท)'])
                            df_clean = df_clean[df_clean['ต้นทุน (บาท)'] > 100]
                            df_clean['% ROI'] = (df_clean['กำไร/ขาดทุน (บาท)'] / df_clean['ต้นทุน (บาท)']) * 100
                
                            # ตัวกรองข้อมูล (Filter)
                            col_f1, col_f2 = st.columns([1, 3])
                            filter_type = col_f1.selectbox("แสดงผลตาม:", ["ทั้งหมด", "รายปี", "รายเดือน"], key="dash_filter_type")
                            
                            df_filtered = df_clean.copy()
                            available_years = sorted(df_clean['วันที่'].dt.year.dropna().unique(), reverse=True)
                            
                            if filter_type == "รายปี" and available_years:
                                year = col_f2.selectbox("เลือกปี:", available_years, key="dash_year")
                                df_filtered = df_clean[df_clean['วันที่'].dt.year == year]
                            elif filter_type == "รายเดือน" and available_years:
                                col_y, col_m = col_f2.columns(2)
                                year = col_y.selectbox("เลือกปี:", available_years, key="dash_year_m")
                                month = col_m.selectbox("เลือกเดือน:", range(1, 13), key="dash_month")
                                df_filtered = df_clean[(df_clean['วันที่'].dt.year == year) & (df_clean['วันที่'].dt.month == month)]
                
                            # คำนวณตัวชี้วัด (Metrics)
                            wins = df_filtered[df_filtered['กำไร/ขาดทุน (บาท)'] > 0]
                            losses = df_filtered[df_filtered['กำไร/ขาดทุน (บาท)'] < 0]
                            avg_win = wins['กำไร/ขาดทุน (บาท)'].mean() if not wins.empty else 0
                            avg_loss = abs(losses['กำไร/ขาดทุน (บาท)'].mean()) if not losses.empty else 1
                            rr_ratio_actual = avg_win / avg_loss
                            
                            col1, col2, col3, col4, col5 = st.columns(5)
                            
                            # กำหนดยอดกำไรในอดีตที่ต้องการบวกเพิ่ม
                            historical_profit = 77420.5
                            total_net_profit = df_filtered['กำไร/ขาดทุน (บาท)'].sum() + historical_profit
                            
                            # แสดง Metric กำไร/ขาดทุนสุทธิ
                            col1.metric("กำไร/ขาดทุนสุทธิ", f"{total_net_profit:,.2f} ฿")
                            
                            # ใส่ Note สีเทาอ่อนไว้ใต้ Metric ของ col1
                            col1.markdown(
                                "<span style='color: #888888; font-size: 0.8em;'>historical profit 2018-2025 = 77,420.50</span>", 
                                unsafe_allow_html=True
                            )
                            col2.metric("ค่าเฉลี่ยต่อไม้ (%):", f"{df_clean['% ROI'].mean():.2f} %")
                            col3.metric("Win Rate", f"{(len(wins)/len(df_filtered)*100):.1f}%" if not df_filtered.empty else "0%")
                            col4.metric("Profit Factor", f"{(wins['กำไร/ขาดทุน (บาท)'].sum() / abs(losses['กำไร/ขาดทุน (บาท)'].sum())):.2f}" if not losses.empty and losses['กำไร/ขาดทุน (บาท)'].sum() != 0 else "N/A")
                            col5.metric("Realized R:R", f"{rr_ratio_actual:.2f} : 1")
                            
                            st.markdown("---")
                            st.markdown("##### 🔍 สถิติการเทรดเชิงลึก")
                            col_s1, col_s2, col_s3 = st.columns(3)
                            
                            if not df_filtered.empty:  # 🔧 กันเหนียว: ถ้าเดือน/ปีที่เลือกไม่มีข้อมูลการเทรด ให้แจ้งเตือนแทนการ error
                                # 1. คำนวณกำไร/ขาดทุนต่อไม้ (เพื่อหา Best/Worst)
                                df_filtered['Profit_Pct'] = (df_filtered['กำไร/ขาดทุน (บาท)'] / df_filtered['ต้นทุน (บาท)']) * 100
                                idx_best = df_filtered['กำไร/ขาดทุน (บาท)'].idxmax()
                                idx_worst = df_filtered['กำไร/ขาดทุน (บาท)'].idxmin()
                            
                                # 2. คำนวณ Max Drawdown จากประวัติมูลค่าพอร์ตสะสม (สมมติว่าคุณมี df_history หรือคำนวณจากยอดสะสม)
                                # กรณีนี้ผมใช้ logic หาค่า Drawdown สูงสุดจากยอดสะสมใน df_filtered
                                cumulative_profit = df_filtered['กำไร/ขาดทุน (บาท)'].cumsum()
                                running_max = cumulative_profit.cummax()
                                drawdown = (cumulative_profit - running_max) / (running_max + abs(df_filtered['ต้นทุน (บาท)'].sum())) # ประมาณการ MDD
                                max_drawdown = drawdown.min() * 100
                            
                                # 3. ดึงค่า Best/Worst
                                best_val = df_filtered.loc[idx_best, 'กำไร/ขาดทุน (บาท)']
                                best_pct = df_filtered.loc[idx_best, 'Profit_Pct']
                                worst_val = df_filtered.loc[idx_worst, 'กำไร/ขาดทุน (บาท)']
                                worst_pct = df_filtered.loc[idx_worst, 'Profit_Pct']
                            
                                # 4. แสดงผล 3 ช่อง
                                col_s1.metric("Max Drawdown", f"{max_drawdown:.1f}%")
                                col_s2.metric("กำไรสูงสุดต่อไม้", f"{best_val:,.0f} ฿", f"{best_pct:.1f}%")
                                col_s3.metric("ขาดทุนหนักสุดต่อไม้", f"{worst_val:,.0f} ฿", f"{worst_pct:.1f}%")
                            else:
                                st.info(f"ℹ️ ไม่มีข้อมูลการเทรดในช่วงเวลาที่เลือก")
                            
                            ######### กราฟรายเดือน vs พร์อตสะสม ###################
                            st.markdown("##### 📈 ผลงานรายเดือน vs พอร์ตสะสม")
                            # --- 0. เตรียมข้อมูลรายการที่ขายแล้ว (Closed) และยึด "วันที่ขาย" เป็นหลัก ---
                            if 'journal_data' in st.session_state and st.session_state.journal_data:
                                df_j_all = pd.DataFrame(st.session_state.journal_data)
                                df_closed_perf = df_j_all[df_j_all['สถานะ'] == 'Closed (ขายแล้ว)'].copy()
                            else:
                                df_closed_perf = df_filtered.copy()
                            
                            df_closed_perf['Sell_Date'] = pd.to_datetime(df_closed_perf['วันที่ขาย'], errors='coerce')
                            df_closed_perf['กำไร/ขาดทุน (บาท)'] = pd.to_numeric(df_closed_perf['กำไร/ขาดทุน (บาท)'], errors='coerce').fillna(0)
                            df_closed_perf['ต้นทุน (บาท)'] = pd.to_numeric(df_closed_perf['ต้นทุน (บาท)'], errors='coerce').fillna(0)
                            
                            # ==========================================
                            # ส่วนที่ 1: สำหรับกราฟแท่งและตาราง (รายเดือน มี Dropdown เลือกปี)
                            # ==========================================
                            available_years = sorted(df_closed_perf['Sell_Date'].dt.year.dropna().unique(), reverse=True)
                            if not available_years:
                                available_years = [2026]
                            
                            df_closed_perf_sorted = df_closed_perf.sort_values('Sell_Date')
                            
                            # --- 3. ตัวเลือกสลับดูเป็น กราฟ หรือ ตาราง ---
                            view_mode = st.radio("เลือกรูปแบบการแสดงผล:", ["📊 แสดงกราฟ", "📋 แสดงตารางข้อมูล"], horizontal=True, label_visibility="collapsed", key="view_mode_perf")
                            
                            if view_mode == "📊 แสดงกราฟ":
                                c1, c2 = st.columns(2)
                            
                                with c1:
                                    with st.container(border=True):
                                        # ย้าย Dropdown เลือกปีเข้ามาไว้ด้านในฝั่งซ้าย (ให้ขนานกับ Dropdown ช่วงเวลากราฟเส้นฝั่งขวา)
                                        selected_year = st.selectbox("📅 เลือกปีที่ต้องการดูผลงานกราฟแท่ง:", available_years, key="select_year_perf")
                                        
                                        df_filtered_year = df_closed_perf_sorted[df_closed_perf_sorted['Sell_Date'].dt.year == selected_year].copy()
                                        
                                        months_range = pd.date_range(start=f"{selected_year}-01-01", end=f"{selected_year}-12-01", freq='MS')
                                        df_full_year = pd.DataFrame({
                                            'Date': months_range,
                                            'Month_Label': months_range.strftime('%b %Y')
                                        })
                                        
                                        if not df_filtered_year.empty:
                                            df_filtered_year['Month_Label'] = df_filtered_year['Sell_Date'].dt.strftime('%b %Y')
                                            df_grouped = df_filtered_year.groupby('Month_Label', sort=False).agg({
                                                'กำไร/ขาดทุน (บาท)': 'sum',
                                                'ต้นทุน (บาท)': 'sum'
                                            }).reset_index()
                                            
                                            df_monthly = pd.merge(df_full_year, df_grouped, on='Month_Label', how='left').fillna({
                                                'กำไร/ขาดทุน (บาท)': 0,
                                                'ต้นทุน (บาท)': 0
                                            })
                                        else:
                                            df_monthly = df_full_year.copy()
                                            df_monthly['กำไร/ขาดทุน (บาท)'] = 0
                                            df_monthly['ต้นทุน (บาท)'] = 0
                                
                                        df_monthly = df_monthly.sort_values('Date').reset_index(drop=True)
                                        df_monthly.columns = ['Date', 'Month_Label', 'Profit_Sum', 'Cost_Sum']
                                        df_monthly['Color'] = df_monthly['Profit_Sum'].apply(lambda x: 'Profit' if x >= 0 else 'Loss')
                                        df_monthly['Monthly_ROI'] = df_monthly.apply(
                                            lambda row: (row['Profit_Sum'] / row['Cost_Sum'] * 100) if row['Cost_Sum'] > 0 else 0, 
                                            axis=1
                                        )
                                        df_monthly['ROI_Text'] = df_monthly['Monthly_ROI'].apply(lambda x: f"{x:+.2f}%")
                                
                                        st.markdown(f"**📊 ผลงานรายเดือน ประจำปี {selected_year}**")
                                        
                                        chart_bar = alt.Chart(df_monthly).mark_bar(width=25).encode(
                                            x=alt.X('Month_Label:O', title='เดือน (ตามวันที่ขาย)', sort=None), 
                                            y=alt.Y('Profit_Sum:Q', title='กำไร/ขาดทุน (บาท)'),
                                            color=alt.Color('Color', scale=alt.Scale(domain=['Profit', 'Loss'], range=['#2ecc71', '#e74c3c']), legend=None),
                                            tooltip=['Month_Label', 'Profit_Sum', alt.Tooltip('Monthly_ROI:Q', format='.2f', title='% ROI เดือน')]
                                        )
                                        
                                        text_labels = alt.Chart(df_monthly).mark_text(
                                            align='center',
                                            baseline='bottom', 
                                            dy=-5, 
                                            color='#888888', 
                                            fontSize=10
                                        ).encode(
                                            x=alt.X('Month_Label:O', sort=None),
                                            y=alt.Y('Profit_Sum:Q'),
                                            text='ROI_Text:N'
                                        )
                                
                                        rule = alt.Chart(pd.DataFrame({'y': [0]})).mark_rule(color='#666666', strokeDash=[3,3]).encode(y='y')
                                        
                                        st.altair_chart((chart_bar + text_labels + rule).properties(height=350), use_container_width=True)
                            
                                with c2:
                                    with st.container(border=True):
                                        # ==========================================
                                        # ส่วนที่ 2: สำหรับกราฟเส้น (รองรับหลายปี + ตัวเลือกช่วงเวลา + Dynamic Aggregation + Zoom)
                                        # ==========================================
                                        initial_past_profit = 77420.5 # กำไรตั้งต้น
                                        
                                        st.markdown("##### 📈 กราฟเส้นกำไรสะสมพอร์ตระยะยาว")
        
                                        if not df_closed_perf_sorted.empty:
                                            # 1. ทำตัวเลือกช่วงเวลา (Quick Filter) สำหรับกราฟเส้นโดยเฉพาะ
                                            c_f1, c_f2 = st.columns([2, 2])
                                            with c_f1:
                                                line_view_range = st.selectbox(
                                                    "⏳ เลือกช่วงเวลาแสดงผล (กราฟเส้น):",
                                                    ["ทั้งหมด (All Time)", "3 เดือนล่าสุด", "6 เดือนล่าสุด", "1 ปีล่าสุด (YTD / 12M)"],
                                                    key="line_view_range"
                                                )
                                            
                                            # กรองข้อมูลตามช่วงเวลาที่เลือก
                                            df_line_filtered = df_closed_perf_sorted.copy()
                                            max_date = df_line_filtered['Sell_Date'].max()
                                            
                                            if line_view_range == "3 เดือนล่าสุด":
                                                start_date = max_date - pd.DateOffset(months=3)
                                                past_slice = df_line_filtered[df_line_filtered['Sell_Date'] < start_date]
                                                initial_past_profit_adjusted = initial_past_profit + past_slice['กำไร/ขาดทุน (บาท)'].sum()
                                                df_line_filtered = df_line_filtered[df_line_filtered['Sell_Date'] >= start_date]
                                            elif line_view_range == "6 เดือนล่าสุด":
                                                start_date = max_date - pd.DateOffset(months=6)
                                                past_slice = df_line_filtered[df_line_filtered['Sell_Date'] < start_date]
                                                initial_past_profit_adjusted = initial_past_profit + past_slice['กำไร/ขาดทุน (บาท)'].sum()
                                                df_line_filtered = df_line_filtered[df_line_filtered['Sell_Date'] >= start_date]
                                            elif line_view_range == "1 ปีล่าสุด (YTD / 12M)":
                                                start_date = max_date - pd.DateOffset(years=1)
                                                past_slice = df_line_filtered[df_line_filtered['Sell_Date'] < start_date]
                                                initial_past_profit_adjusted = initial_past_profit + past_slice['กำไร/ขาดทุน (บาท)'].sum()
                                                df_line_filtered = df_line_filtered[df_line_filtered['Sell_Date'] >= start_date]
                                            else:
                                                initial_past_profit_adjusted = initial_past_profit
                                        
                                            if not df_line_filtered.empty:
                                                # 2. Dynamic Aggregation: ตรวจสอบช่วงเวลา ถ้าระยะเวลามากกว่า 1 ปี ให้ยุบเป็น "รายเดือน" อัตโนมัติเพื่อกันกราฟแน่น
                                                date_span_days = (df_line_filtered['Sell_Date'].max() - df_line_filtered['Sell_Date'].min()).days
                                                
                                                if date_span_days > 365 and line_view_range == "ทั้งหมด (All Time)":
                                                    df_line_filtered['Period_Key'] = df_line_filtered['Sell_Date'].dt.to_period('M')
                                                    df_line_filtered['Time_Label'] = df_line_filtered['Period_Key'].apply(lambda r: r.strftime('%b %Y'))
                                                    df_line_filtered['Sort_Time'] = df_line_filtered['Period_Key'].dt.start_time
                                                    agg_freq_text = "รายเดือน (มุมมองระยะยาว)"
                                                else:
                                                    df_line_filtered['Period_Key'] = df_line_filtered['Sell_Date'].dt.to_period('W-MON')
                                                    df_line_filtered['Time_Label'] = df_line_filtered['Period_Key'].apply(lambda r: f"W{r.week} {r.start_time.strftime('%b %Y')}")
                                                    df_line_filtered['Sort_Time'] = df_line_filtered['Period_Key'].dt.start_time
                                                    agg_freq_text = "รายสัปดาห์ (เจาะลึก)"
                                        
                                                with c_f2:
                                                    st.markdown(f"<p style='padding-top:28px; color:gray; font-size:13px;'>ℹ️ ความละเอียด: <b>{agg_freq_text}</b></p>", unsafe_allow_html=True)
                                        
                                                # รวมกำไรตามช่วงเวลาที่จัดกลุ่ม
                                                df_line_grouped = df_line_filtered.groupby(['Sort_Time', 'Time_Label'], as_index=False).agg({
                                                    'กำไร/ขาดทุน (บาท)': 'sum'
                                                }).sort_values('Sort_Time')
                                                
                                                # คำนวณกำไรสะสมต่อเนื่อง
                                                df_line_grouped['Cumulative_Profit'] = initial_past_profit_adjusted + df_line_grouped['กำไร/ขาดทุน (บาท)'].cumsum()
                                        
                                                # 3. คำนวณขอบเขตแกน Y ให้เผื่อพื้นที่ด้านบนเพิ่ม 15% (แก้ปัญหาเส้นชนขอบบน)
                                                y_max = df_line_grouped['Cumulative_Profit'].max()
                                                y_min = df_line_grouped['Cumulative_Profit'].min()
                                                y_upper_limit = y_max * 1.15 if y_max > 0 else y_max * 0.85
                                        
                                                # สร้างกราฟเส้นพร้อมกำหนด Scale แกน Y และเปิด Interactive Zoom & Pan
                                                chart_line = alt.Chart(df_line_grouped).mark_line(point=True, color='#3498db', strokeWidth=3).encode(
                                                    x=alt.X('Time_Label:O', title='ช่วงเวลาที่มีการเคลื่อนไหว', sort=list(df_line_grouped['Time_Label'])),
                                                    y=alt.Y('Cumulative_Profit:Q', title='กำไรสะสม (บาท)', scale=alt.Scale(domain=[y_min, y_upper_limit], nice=True)),
                                                    tooltip=['Time_Label', 'Cumulative_Profit']
                                                ).properties(
                                                    height=350
                                                ).interactive()
                                                
                                                st.altair_chart(chart_line, use_container_width=True)
                                            else:
                                                st.info("ไม่มีข้อมูลในช่วงเวลาที่เลือก")
                                        else:
                                            st.info("ยังไม่มีข้อมูลประวัติการเทรดที่ปิดสถานะ")
                                                            
                            else:
                                # สำหรับโหมดตาราง (ใช้ปีที่เลือกจากฝั่งซ้ายมาแสดงผล)
                                selected_year = st.session_state.get('select_year_perf', available_years[0])
                                df_filtered_year = df_closed_perf_sorted[df_closed_perf_sorted['Sell_Date'].dt.year == selected_year].copy()
                                
                                months_range = pd.date_range(start=f"{selected_year}-01-01", end=f"{selected_year}-12-01", freq='MS')
                                df_full_year = pd.DataFrame({
                                    'Date': months_range,
                                    'Month_Label': months_range.strftime('%b %Y')
                                })
                                
                                if not df_filtered_year.empty:
                                    df_filtered_year['Month_Label'] = df_filtered_year['Sell_Date'].dt.strftime('%b %Y')
                                    df_grouped = df_filtered_year.groupby('Month_Label', sort=False).agg({
                                        'กำไร/ขาดทุน (บาท)': 'sum',
                                        'ต้นทุน (บาท)': 'sum'
                                    }).reset_index()
                                    df_monthly = pd.merge(df_full_year, df_grouped, on='Month_Label', how='left').fillna({
                                        'กำไร/ขาดทุน (บาท)': 0,
                                        'ต้นทุน (บาท)': 0
                                    })
                                else:
                                    df_monthly = df_full_year.copy()
                                    df_monthly['กำไร/ขาดทุน (บาท)'] = 0
                                    df_monthly['ต้นทุน (บาท)'] = 0
                            
                                df_monthly = df_monthly.sort_values('Date').reset_index(drop=True)
                                df_monthly.columns = ['Date', 'Month_Label', 'Profit_Sum', 'Cost_Sum']
                                df_monthly['Monthly_ROI'] = df_monthly.apply(
                                    lambda row: (row['Profit_Sum'] / row['Cost_Sum'] * 100) if row['Cost_Sum'] > 0 else 0, 
                                    axis=1
                                )
                            
                                st.markdown(f"##### 📋 ตารางสรุปผลงานรายเดือน (อิงวันที่ขาย) ประจำปี {selected_year}")
                                df_display = df_monthly[['Month_Label', 'Profit_Sum', 'Cost_Sum', 'Monthly_ROI']].copy()
                                df_display.columns = ['เดือน', 'กำไร/ขาดทุน (บาท)', 'ต้นทุนประจำเดือน (บาท)', '% กำไร/ขาดทุน (ROI)']
                                
                                st.dataframe(
                                    df_display.style.format({
                                        'กำไร/ขาดทุน (บาท)': '{:,.2f}',
                                        'ต้นทุนประจำเดือน (บาท)': '{:,.2f}',
                                        '% กำไร/ขาดทุน (ROI)': '{:.2f}%'
                                    }),
                                    use_container_width=True
                                )
                                                                                                        
                            ##### กราฟกระจายตัว (Histogram) ###########
                            with st.container(border=True):
                                st.markdown("##### 🔔 การกระจายตัวกำไร/ขาดทุน (%)")
                                
                                # 1. จัดการข้อมูลให้พร้อมก่อนแสดงผล
                                if not df_filtered.empty:
                                    df_filtered = df_filtered.copy()
                                    df_filtered['Profit_Pct'] = (df_filtered['กำไร/ขาดทุน (บาท)'] / df_filtered['ต้นทุน (บาท)'].replace(0, 1)) * 100
                                    wins = df_filtered[df_filtered['กำไร/ขาดทุน (บาท)'] > 0]
                                    losses = df_filtered[df_filtered['กำไร/ขาดทุน (บาท)'] < 0]
                                    
                                    mean_val = df_filtered['Profit_Pct'].mean()
                                    avg_loss_pct = losses['Profit_Pct'].mean() if not losses.empty else 0
                                    optimal_cutloss_pct = -(wins['Profit_Pct'].mean() / 2.0) if not wins.empty else None
                                
                                    # 2. แสดง Metric ด้วย HTML เพื่อคุมสีให้ตรงกับสีเส้นในกราฟ
                                    col_m1, col_m2, col_m3 = st.columns(3)
                                    col_m1.markdown(f"<div style='text-align: center; color: #12da58; font-size: 20px; font-weight: bold;'>Mean</div><div style='text-align: center; font-size: 24px;'>{mean_val:.1f}%</div>", unsafe_allow_html=True)
                                    col_m2.markdown(f"<div style='text-align: center; color: #9b59b6; font-size: 20px; font-weight: bold;'>Avg Loss</div><div style='text-align: center; font-size: 24px;'>{avg_loss_pct:.1f}%</div>", unsafe_allow_html=True)
                                    if optimal_cutloss_pct is not None:
                                        col_m3.markdown(f"<div style='text-align: center; color: #f21d2b; font-size: 20px; font-weight: bold;'>Target Cut</div><div style='text-align: center; font-size: 24px;'>{optimal_cutloss_pct:.1f}%</div>", unsafe_allow_html=True)
                                    
                                    # 3. วาดกราฟ (เรียกผ่าน plotly.express โดยตรง ป้องกัน Error ซ้ำซ้อน)
                                    fig = plotly.express.histogram(df_filtered, x='Profit_Pct', nbins=20, opacity=0.6, color_discrete_sequence=['#3498db'])
                                    
                                    # เพิ่ม annotation_yshift ให้ต่ำลงเล็กน้อย และลดระยะห่าง
                                    fig.add_vline(x=mean_val, line_dash="dash", line_color="#12da58", 
                                                  annotation_text=f"Mean ({mean_val:.1f}%)", annotation_position="top right", annotation_yshift=20)
                                    fig.add_vline(x=avg_loss_pct, line_dash="dot", line_color="#9b59b6", 
                                                  annotation_text=f"Avg Loss ({avg_loss_pct:.1f}%)", annotation_position="top right", annotation_yshift=-10)
                                    if optimal_cutloss_pct is not None:
                                        fig.add_vline(x=optimal_cutloss_pct, line_dash="dashdot", line_color="#f21d2b", 
                                                      annotation_text=f"Target ({optimal_cutloss_pct:.1f}%)", annotation_position="top right", annotation_yshift=-40)
                                    
                                    # เพิ่ม margin top เพื่อให้มีพื้นที่เหลือให้ป้ายข้อความด้านบนไม่ถูกตัด
                                    fig.update_layout(margin=dict(t=50, b=20, l=20, r=20), height=350, plot_bgcolor='rgba(0,0,0,0)')
                                    st.plotly_chart(fig, use_container_width=True)
                                    
                                else:
                                    st.info("ยังไม่มีข้อมูลเพียงพอที่จะแสดงกราฟการกระจายตัวครับ")
    
                            ####################
                            if st.button("🔄 อัปเดตข้อมูลย้อนหลัง (Backfill)"):
                                with st.spinner('กำลังคำนวณข้อมูลย้อนหลัง (อาจใช้เวลาสักครู่)...'):
                                    # เรียกใช้ฟังก์ชันที่เขียนไว้
                                    backfill_portfolio_history()
                                    st.success("อัปเดตเรียบร้อย! กราฟของคุณพร้อมใช้งานแล้ว")
                            # Equity Curve 
                            st.markdown("---")
                            with st.container(border=True):
                                st.markdown("##### 📈 Equity Curve")
                                
                                # เรียกใช้งานฟังก์ชันที่ย้ายไปด้านบน
                                try:
                                    display_performance_dashboard()
                                except Exception as e:
                                    st.warning(f"ยังไม่พบข้อมูล Portfolio_History หรือเกิดข้อผิดพลาดในการโหลด: {e}")
        
                                # --- 2. ส่วนวิเคราะห์ Sector Performance (แก้ไขป้องกัน Error ประเภทข้อมูล) ---
                                journal_df = pd.DataFrame(st.session_state.get('journal_data', []))
                                closed_trades = journal_df[journal_df['สถานะ'] == 'Closed (ขายแล้ว)'] if not journal_df.empty else pd.DataFrame()
                            
                                if not journal_df.empty:
                                    sector_data_list = []
                                    for idx, row in journal_df.iterrows():
                                        ticker = row.get('หุ้น', 'UNKNOWN')
                                        
                                        # ป้องกันค่าที่เป็น String หรือค่าว่าง ให้แปลงเป็น float ทันที
                                        try:
                                            profit = float(row.get('กำไร/ขาดทุน (บาท)', 0))
                                        except (ValueError, TypeError):
                                            profit = 0.0
                                            
                                        try:
                                            cost = float(row.get('ต้นทุน (บาท)', 0))
                                        except (ValueError, TypeError):
                                            cost = 0.0
                                            
                                        sector = row.get('Sector', 'General / Unspecified')
                                        if pd.isna(sector) or str(sector).strip() == '': 
                                            sector = 'General / Unspecified'
                                            
                                        sector_data_list.append({
                                            'Sector': str(sector).strip(),
                                            'Ticker': str(ticker).strip(),
                                            'Net_Profit': profit,
                                            'Invested_Cost': cost
                                        })
                                        
                                    if len(sector_data_list) > 0:
                                        df_sector_source = pd.DataFrame(sector_data_list)
                                        
                                        # บังคับแปลงชนิดข้อมูลให้เป็นตัวเลขชัวร์ๆ อีกรอบก่อน Groupby
                                        df_sector_source['Net_Profit'] = pd.to_numeric(df_sector_source['Net_Profit'], errors='coerce').fillna(0)
                                        df_sector_source['Invested_Cost'] = pd.to_numeric(df_sector_source['Invested_Cost'], errors='coerce').fillna(0)
                                        
                                        df_sector_summary = df_sector_source.groupby('Sector', as_index=False).agg({
                                            'Net_Profit': 'sum',
                                            'Invested_Cost': 'sum',
                                            'Ticker': lambda x: ', '.join(x.unique())
                                        })
                                        
                                        df_sector_summary['Return_Pct'] = df_sector_summary.apply(
                                            lambda r: (r['Net_Profit'] / r['Invested_Cost'] * 100) if r['Invested_Cost'] > 0 else 0, 
                                            axis=1
                                        )
                                        df_sector_summary = df_sector_summary.sort_values(by='Net_Profit', ascending=False)
                            
                                        # 📊 ส่วน กราฟแท่ง (Bar Chart)
                                        st.markdown("##### 📊 กำไร/ขาดทุนสะสมแยกตามกลุ่มอุตสาหกรรม")
                                        fig_bar = px.bar(
                                            df_sector_summary, 
                                            x='Sector', 
                                            y='Net_Profit', 
                                            text=df_sector_summary['Net_Profit'].apply(lambda x: f"{x:,.2f} ฿"), 
                                            color='Net_Profit', 
                                            color_continuous_scale=['#EF5350', '#26A69A']
                                        )
                                        fig_bar.update_traces(textposition='outside')
                                        fig_bar.update_layout(
                                            xaxis_title="กลุ่มอุตสาหกรรม (Sector)", 
                                            yaxis_title="กำไร/ขาดทุนสุทธิ (บาท)", 
                                            height=400, 
                                            margin=dict(l=20, r=20, t=30, b=20), 
                                            coloraxis_showscale=False
                                        )
                                        st.plotly_chart(fig_bar, use_container_width=True)
                            
                                        # 🗺️ ส่วน Treemap
                                        st.markdown("##### 🗺️ แผนผังแสดงสัดส่วนและผลงานพอร์ตตาม Sector (Treemap)")
                                        fig_tree = px.treemap(
                                            df_sector_summary, 
                                            path=['Sector'], 
                                            values='Invested_Cost', 
                                            color='Return_Pct', 
                                            color_continuous_scale='Tealrose', 
                                            color_continuous_midpoint=0, 
                                            custom_data=['Net_Profit', 'Return_Pct', 'Ticker']
                                        )
                                        fig_tree.update_traces(
                                            hovertemplate='<b>Sector:</b> %{label}<br><b>เงินลงทุนรวม:</b> %{value:,.2f} ฿<br><b>กำไร/ขาดทุน:</b> %{customdata[0]:,.2f} ฿<br><b>ผลตอบแทน:</b> %{customdata[1]:+.2f}%<br><b>หุ้นในกลุ่ม:</b> %{customdata[2]}'
                                        )
                                        fig_tree.update_layout(height=400, margin=dict(l=10, r=10, t=10, b=10))
                                        st.plotly_chart(fig_tree, use_container_width=True)
                                        
                                        # 📋 ตารางสรุปข้อมูล Sector (ปัดเศษทศนิยม 2 ตำแหน่งจริง ๆ ก่อนแสดงผล)
                                        st.markdown("##### 📋 ตารางสรุปข้อมูลแยกตาม Sector")
                                        display_sector_df = df_sector_summary[['Sector', 'Invested_Cost', 'Net_Profit', 'Return_Pct', 'Ticker']].copy()
                                        
                                        # ปัดเศษทศนิยม 2 ตำแหน่งให้คอลัมน์ Return_Pct ตรงนี้เลย
                                        display_sector_df['Return_Pct'] = display_sector_df['Return_Pct'].round(2)
                                        
                                        display_sector_df.columns = ['กลุ่มอุตสาหกรรม (Sector)', 'เงินลงทุนรวม (บาท)', 'กำไร/ขาดทุนสุทธิ (บาท)', '% ผลตอบแทน', 'รายชื่อหุ้นที่เกี่ยวข้อง']
                                        
                                        st.dataframe(
                                            display_sector_df.style.format({
                                                'เงินลงทุนรวม (บาท)': '{:,.2f}',
                                                'กำไร/ขาดทุนสุทธิ (บาท)': '{:,.2f}',
                                                '% ผลตอบแทน': '{:+.2f}%'
                                            }).set_properties(**{'text-align': 'right'}), 
                                            use_container_width=True
                                        )
                                    else:
                                        st.info("ยังไม่มีข้อมูลเพียงพอสำหรับการวิเคราะห์ Sector")
                                else:
                                    st.info("ยังไม่มีข้อมูลรายการเทรดในระบบครับ")
                                                                        
                            #######################################
                            # 1. จัดการข้อมูล (ยังคงตรรกะเดิมไว้)
                            df_summary = df_filtered.groupby('หุ้น')['กำไร/ขาดทุน (บาท)'].sum().reset_index()
                            df_summary = df_summary.sort_values(by='กำไร/ขาดทุน (บาท)', ascending=False)
                            top_ticker = df_summary.iloc[0]['หุ้น']
    
                            # แสดงข้อมูลหุ้นตัวเก่งแบบสรุปที่เปิดตลอดเวลา
                            st.info(f"หุ้นที่ทำกำไรให้คุณมากที่สุดในปัจจุบันคือ: **{top_ticker}**")
                            
                            # --- ส่วนตารางสรุปรายหุ้น (ซ่อนได้) ---
                            with st.expander("🏆 ดูตารางสรุปผลงานรายหุ้น"):
                                # แปลงคอลัมน์วันที่ให้เป็น datetime
                                df_filtered['วันที่ซื้อ'] = pd.to_datetime(df_filtered['วันที่ซื้อ'])
                                df_filtered['วันที่ขาย'] = pd.to_datetime(df_filtered['วันที่ขาย'])
                                
                                # 1. คำนวณ Holding Time ทีละแถว
                                # ถ้าวันที่ขายเป็น NaT (คือยังไม่ขาย) ให้ใช้วันปัจจุบัน
                                now = pd.Timestamp.now()
                                df_filtered['Hold_Days'] = df_filtered.apply(
                                    lambda row: (row['วันที่ขาย'] - row['วันที่ซื้อ']).days 
                                    if pd.notnull(row['วันที่ขาย']) 
                                    else (now - row['วันที่ซื้อ']).days, 
                                    axis=1
                                )
                                # คำนวณข้อมูลตามเดิม
                                summary = df_filtered.groupby('หุ้น').agg({
                                    'กำไร/ขาดทุน (บาท)': 'sum',
                                    'ต้นทุน (บาท)': 'sum'
                                })
                                summary['% Return'] = (summary['กำไร/ขาดทุน (บาท)'] / summary['ต้นทุน (บาท)']) * 100
                                
                                df_filtered['วันที่'] = pd.to_datetime(df_filtered['วันที่'])
                                hold_time = df_filtered.groupby('หุ้น')['วันที่'].min()
                                summary['Holding Time'] = (pd.Timestamp.now() - hold_time).dt.days
                                
                                # ปรับชื่อคอลัมน์และเลือกเฉพาะที่ต้องการ
                                display_df = summary.reset_index()
                                display_df = display_df[['หุ้น', 'กำไร/ขาดทุน (บาท)', '% Return', 'Holding Time']]
                                display_df.columns = ['Ticker', 'Total Profit/Loss', '% Return', 'Holding Time']
                                
                                # แสดงตารางแบบไม่ต้องใช้ column_config ก่อน เพื่อเช็คว่าข้อมูลมาครบไหม
                                # ถ้าวิธีนี้เห็นตัวเลข แสดงว่าปัญหาอยู่ที่ column_config ที่คุณใช้
                                st.dataframe(display_df, use_container_width=True)
                                
                                # ถ้าข้อมูลในตารางนี้แสดงผลครบถ้วน ให้ค่อยๆ เพิ่ม column_config ทีละส่วนครับ
                            with st.expander("🎯 Win Rate รายหุ้น (หุ้นตัวไหนแม่นที่สุด)"):
                                # 1. เตรียมข้อมูลสำหรับคำนวณ Win Rate
                                # แยกกำไร (>0) และ ขาดทุน (<=0)
                                df_filtered['is_win'] = df_filtered['กำไร/ขาดทุน (บาท)'] > 0
                                
                                # 2. Group ข้อมูลรายหุ้น
                                win_rate_df = df_filtered.groupby('หุ้น').agg(
                                    Total_Trades=('หุ้น', 'count'),
                                    Wins=('is_win', 'sum')
                                )
                                
                                # คำนวณ % Win Rate
                                win_rate_df['Win Rate (%)'] = (win_rate_df['Wins'] / win_rate_df['Total_Trades']) * 100
                                
                                # 3. จัดระเบียบตาราง
                                win_rate_df = win_rate_df.sort_values(by='Win Rate (%)', ascending=False).reset_index()
                                win_rate_df = win_rate_df.rename(columns={'หุ้น': 'Ticker'})
                                
                                # 4. แสดงตารางแบบ Basic ที่ดูง่าย
                                st.dataframe(
                                    win_rate_df[['Ticker', 'Win Rate (%)', 'Total_Trades']],
                                    use_container_width=True,
                                    hide_index=True,
                                    column_config={
                                        "Win Rate (%)": st.column_config.ProgressColumn(
                                            "Win Rate (%)",
                                            format="%.1f%%",
                                            min_value=0,
                                            max_value=100,
                                        ),
                                        "Total_Trades": "จำนวนครั้งที่เทรด"
                                    }
                                )
                                
                                # 5. สรุปสั้นๆ ให้
                                best_stock = win_rate_df.iloc[0]['Ticker']
                                worst_stock = win_rate_df.iloc[-1]['Ticker']
                                st.write(f"✅ หุ้นที่วินเรทสูงที่สุด: **{best_stock}**")
                                st.write(f"⚠️ หุ้นที่วินเรทต่ำที่สุด: **{worst_stock}**")
                            #########
                            with st.expander("🏆 ตารางสรุปผลงานรายหุ้น (Annualized Return)"):
                                # 1. จัดเตรียมข้อมูล: แปลงวันที่และจัดการค่าว่าง
                                df_filtered['วันที่ซื้อ'] = pd.to_datetime(df_filtered['วันที่ซื้อ'])
                                df_filtered['วันที่ขาย'] = pd.to_datetime(df_filtered['วันที่ขาย'])
                                now = pd.Timestamp.now()
                                
                                # 2. คำนวณ Holding Time อย่างปลอดภัย
                                df_filtered['Hold_Days'] = df_filtered.apply(
                                    lambda row: (row['วันที่ขาย'] - row['วันที่ซื้อ']).days if pd.notnull(row['วันที่ขาย']) 
                                    else (now - row['วันที่ซื้อ']).days, axis=1
                                )
                                df_filtered['Hold_Days'] = df_filtered['Hold_Days'].clip(lower=1)
                                
                                # 3. คำนวณสรุปรายหุ้น
                                summary = df_filtered.groupby('หุ้น').agg({
                                    'กำไร/ขาดทุน (บาท)': 'sum',
                                    'ต้นทุน (บาท)': 'sum',
                                    'Hold_Days': 'mean'
                                })
                                
                                # 4. คำนวณตัวเลข
                                summary['% Return'] = (summary['กำไร/ขาดทุน (บาท)'] / summary['ต้นทุน (บาท)']) * 100
                                summary['Annualized Return'] = (((1 + (summary['% Return'] / 100)) ** (365 / summary['Hold_Days'])) - 1) * 100
                                summary = summary.replace([float('inf'), -float('inf')], 0).fillna(0)
                                
                                # 5. เตรียม DataFrame สำหรับแสดงผล
                                display_df = summary.reset_index()
                                
                                # 6. แปลงข้อมูลเป็น String ที่จัดรูปแบบตามต้องการ (วิธีนี้แก้ปัญหาช่องว่างได้ถาวร)
                                final_df = pd.DataFrame({
                                    "Ticker": display_df['หุ้น'],
                                    "Profit/Loss (บาท)": display_df['กำไร/ขาดทุน (บาท)'].apply(lambda x: f"{x:,.2f} ฿"),
                                    "Return (%)": display_df['% Return'].apply(lambda x: f"{x:.2f} %"),
                                    "Annualized Return (%)": display_df['Annualized Return'].apply(lambda x: f"{x:,.2f} %"),
                                    "Holding Time (วัน)": display_df['Hold_Days'].apply(lambda x: f"{int(x)} วัน")
                                })
                                
                                # 7. แสดงผล
                                st.dataframe(
                                    final_df,
                                    use_container_width=True,
                                    hide_index=True
                                )
                            ########
                            with st.expander("📊 วิเคราะห์ประสิทธิภาพเชิงลึก (Efficiency & Time-to-Profit)"):
                                # คำนวณเบื้องต้น (ต่อจากของเดิม)
                                # ... (สมมติว่ามี df_filtered อยู่แล้ว)
                                
                                # 1. แยกกลุ่มหุ้นทำกำไร และหุ้นขาดทุน เพื่อหา Time-to-Profit
                                winners = df_filtered[df_filtered['กำไร/ขาดทุน (บาท)'] > 0]
                                losers = df_filtered[df_filtered['กำไร/ขาดทุน (บาท)'] <= 0]
                                
                                avg_win_time = winners['Hold_Days'].mean() if not winners.empty else 0
                                avg_loss_time = losers['Hold_Days'].mean() if not losers.empty else 0
                                
                                # 2. คำนวณ Efficiency Ratio รายหุ้น (กำไรต่อวัน)
                                summary['Profit Per Day'] = summary['กำไร/ขาดทุน (บาท)'] / summary['Hold_Days']
                                
                                # 3. เตรียมข้อมูลแสดงผลเป็นข้อความ (ป้องกัน error)
                                analytics_df = pd.DataFrame({
                                    "Ticker": summary.index,
                                    "Profit/Loss (บาท)": summary['กำไร/ขาดทุน (บาท)'].apply(lambda x: f"{x:,.2f} ฿"),
                                    "Profit Per Day (บาท/วัน)": summary['Profit Per Day'].apply(lambda x: f"{x:,.2f} ฿"),
                                    "Avg Hold Days (วัน)": summary['Hold_Days'].apply(lambda x: f"{x:.1f} วัน")
                                })
                                
                                # แสดงตารางวิเคราะห์
                                st.dataframe(analytics_df, use_container_width=True, hide_index=True)
                                
                                # 4. แสดงสรุปเชิงกลยุทธ์ (Time-to-Profit Insights)
                                st.divider()
                                st.subheader("💡 วิเคราะห์นิสัยการเทรด (Insights)")
                                
                                col1, col2 = st.columns(2)
                                col1.metric("ถือหุ้นกำไรเฉลี่ย", f"{avg_win_time:.1f} วัน")
                                col2.metric("ถือหุ้นขาดทุนเฉลี่ย", f"{avg_loss_time:.1f} วัน")
                                
                                if avg_win_time < avg_loss_time:
                                    st.success("✅ ระบบของคุณ: ทำกำไรได้รวดเร็ว (ถือหุ้นกำไรสั้นกว่าหุ้นที่ขาดทุน)")
                                else:
                                    st.warning("⚠️ ข้อสังเกต: คุณอาจจะทนถือหุ้นที่ขาดทุนนานกว่าหุ้นที่ทำกำไร (Loss Aversion)")
    
                            #####
                            with st.expander("📈 Opportunity Cost Matrix (หุ้นไหนควรเก็บ หุ้นไหนควรทิ้ง)"):
                                # 1. เตรียมข้อมูลสำหรับทำกราฟ
                                plot_df = summary.reset_index()
                                plot_df['% Return'] = (plot_df['กำไร/ขาดทุน (บาท)'] / plot_df['ต้นทุน (บาท)']) * 100
                                
                                # 2. สร้างกราฟ Scatter Plot
                                fig = px.scatter(
                                    plot_df, 
                                    x='Hold_Days', 
                                    y='% Return', 
                                    text='หุ้น',
                                    title="Holding Time vs % Return",
                                    labels={'Hold_Days': 'ระยะเวลาการถือครอง (วัน)', '% Return': 'ผลตอบแทน (%)'},
                                    size_max=60
                                )
                                
                                # 3. เพิ่มเส้นแบ่ง (Quadrants) เพื่อให้ดูง่ายขึ้น
                                fig.add_hline(y=0, line_dash="dash", line_color="red") # เส้นแบ่ง กำไร/ขาดทุน
                                fig.add_vline(x=plot_df['Hold_Days'].mean(), line_dash="dash", line_color="gray") # เส้นแบ่ง ถือสั้น/ถือนาน
                                
                                fig.update_traces(textposition='top center')
                                
                                # 4. แสดงผล
                                st.plotly_chart(fig, use_container_width=True)
                                
                                # 5. สรุปคำแนะนำจากกราฟ
                                st.markdown("""
                                **วิธีอ่านกราฟ Opportunity Cost:**
                                *   **บน-ซ้าย (High Return, Low Holding Time):** ✅ **Super Stock** ของคุณ! ทำเงินได้เร็วและคุ้มค่าที่สุด
                                *   **ล่าง-ขวา (Low Return, High Holding Time):** ⚠️ **Dead Money** หุ้นตัวที่กินเวลาชีวิตคุณไปนานแต่ไม่ทำกำไร (พิจารณาขายทิ้งเพื่อนำเงินไปหาโอกาสใหม่)
                                *   **บน-ขวา (High Return, High Holding Time):** 🐢 **Value/Trend Stock** เป็นหุ้นที่ต้องถือยาวถึงจะกำไร ถ้าคุณชอบสไตล์นี้ถือว่าโอเคครับ
                                """)
                            # --- ส่วนกราฟเปรียบเทียบ (ซ่อนได้) ---
                            with st.expander("📈 ดูพอร์ตภาพรวม vs พอร์ตหักหุ้นตัวเก่งออก"):
                                # แยกข้อมูลพอร์ต
                                df_rest = df_filtered[df_filtered['หุ้น'] != top_ticker]
                                
                                # คำนวณกราฟ
                                df_filtered_sorted = df_filtered.sort_values('วันที่')
                                df_rest_sorted = df_rest.sort_values('วันที่')
                                
                                all_portfolio = df_filtered_sorted.set_index('วันที่')['กำไร/ขาดทุน (บาท)'].cumsum().groupby('วันที่').last()
                                core_portfolio = df_rest_sorted.set_index('วันที่')['กำไร/ขาดทุน (บาท)'].cumsum().groupby('วันที่').last()
                                
                                # สร้าง DataFrame
                                chart_data = pd.concat([all_portfolio, core_portfolio], axis=1)
                                chart_data.columns = ['พอร์ตทั้งหมด', 'พอร์ตหักหุ้นตัวเก่ง']
                                
                                # วิธีที่ชัวร์ที่สุดสำหรับ Pandas ทุกเวอร์ชัน
                                chart_data = chart_data.ffill() 
                                chart_data = chart_data.fillna(0)
                                
                                st.line_chart(chart_data)
                                
                #########################            
                with tab_portfolio:
                    st.markdown("#### 💼 ระบบบันทึกพอร์ตโฟลิโอส่วนตัว")
                    
                    # 1. จัดการเงินสด (แก้ไขด้วยตัวเองได้ตลอดเวลา)
                    if "cash_balance" not in st.session_state:
                        st.session_state.cash_balance = load_total_cash_balance()
                        
                    # ส่วนแสดงปุ่มเข้าออกเงินสด 
                    with st.expander("💰 บันทึกรายการเงินสดเข้า-ออก"):
                        with st.form("cash_flow_form", clear_on_submit=True):
                            c1, c2, c3 = st.columns(3)
                            with c1:
                                log_date = st.date_input("วันที่:")
                            with c2:
                                log_type = st.selectbox("ประเภท:", ["เติมเงินสด", "เงินปันผล", "เงินรายได้อื่นๆ", "ถอนเงินสด"])
                            with c3:
                                log_amount = st.number_input("จำนวนเงิน:", step=100.0)
                            
                            log_note = st.text_input("หมายเหตุ:")
                            submitted_cash = st.form_submit_button("บันทึกรายการเงินสด")
                    
                            if submitted_cash:
                                # คำนวณค่าบวก/ลบ ตามประเภท
                                actual_amount = log_amount if log_type in ["เติมเงินสด", "เงินปันผล", "เงินรายได้อื่นๆ"] else -log_amount
                                
                                # บันทึกผ่านฟังก์ชันที่เราทำไว้
                                log_cash_transaction(
                                    date=str(log_date),
                                    trans_type=log_type,
                                    amount=actual_amount,
                                    note=log_note
                                )
                                # อัปเดต Session เพื่อให้ยอดเงินโชว์ทันที
                                st.session_state.cash_balance += actual_amount
                                st.success(f"บันทึก {log_type} สำเร็จ!")
                                st.rerun()
                    
                    # 2. ฟอร์มเพิ่ม/ลดหุ้น
                    with st.expander("🔄 บันทึกการซื้อขายหุ้น (อัปเดต Portfolio & Journal)"):
                        col1, col2 = st.columns(2)
                        
                        portfolio_stocks = [item['หุ้น'] for item in st.session_state.my_portfolio] if "my_portfolio" in st.session_state else []
                        
                        with col1:
                            options = ["  "] + portfolio_stocks
                            
                            # 🌟 สร้างฟังก์ชัน Callback สำหรับอัปเดต Sector อัตโนมัติเมื่อเปลี่ยนตัวเลือกหุ้น
                            def update_sector_on_select():
                                # ใช้ .get() เพื่อป้องกัน AttributeError ถ้าคีย์ยังไม่ถูกสร้างใน session_state
                                selected = st.session_state.get("journal_select_ticker", "  ")
                                if selected != "  ":
                                    # 1. เช็คจากพอร์ตก่อน
                                    matched_item = next((item for item in st.session_state.get('my_portfolio', []) if item.get('หุ้น', item.get('Ticker', '')) == selected), None)
                                    if matched_item and matched_item.get('Sector') and matched_item.get('Sector') != "General / Unspecified":
                                        st.session_state.journal_p_sector = matched_item['Sector']
                                    else:
                                        # 2. ถ้าไม่มีในพอร์ต ดึงจาก Dictionary A-Z
                                        st.session_state.journal_p_sector = get_sector_from_mapping(selected)
                                else:
                                    st.session_state.journal_p_sector = "General / Unspecified"
    
                            select_ticker = st.selectbox(
                                "เลือกหุ้นจากพอร์ต:", 
                                options, 
                                key="journal_select_ticker",
                                on_change=update_sector_on_select
                            )
                            
                            # กำหนดค่าเริ่มต้นของ Sector ตอนโหลดครั้งแรก
                            if "journal_p_sector" not in st.session_state:
                                st.session_state.journal_p_sector = "General / Unspecified"
    
                            if select_ticker != "  ":
                                p_ticker = select_ticker
                            else:
                                p_ticker = st.text_input("ชื่อหุ้น:", key="journal_p_ticker")
                                # ถ้าพิมพ์ชื่อหุ้นใหม่เอง ให้เช็คจาก Dictionary แล้วอัปเดตลงช่อง Sector ทันที
                                if p_ticker:
                                    st.session_state.journal_p_sector = get_sector_from_mapping(p_ticker)
    
                            # ช่องกรอก Sector ที่ผูกกับ st.session_state.journal_p_sector โดยตรง
                            p_sector = st.text_input("กลุ่มอุตสาหกรรม (Sector):", key="journal_p_sector")
                            
                            p_status = st.selectbox("สถานะรายการ:", ["Open (กำลังถือ)", "Closed (ขายแล้ว)"], key="journal_p_status")
                            
                            if p_status == "Closed (ขายแล้ว)":
                                p_buy_date = st.date_input("📅 วันที่ซื้อหุ้น (ต้นทุนเดิม):", key="journal_p_buy_date")
                                p_sell_date = st.date_input("📅 วันที่ขายจริง (วันที่ทำรายการ):", key="journal_p_sell_date")
                            else:
                                p_buy_date = st.date_input("📅 วันที่ทำรายการซื้อ:", key="journal_open_date")
                                p_sell_date = None
                            
                        with col2:
                            p_type = st.selectbox("ประเภท:", ["ซื้อ (Buy)", "ขายทำกำไร (Take Profit)", "ขายตัดขาดทุน (Stop Loss)"], key="journal_p_type")
                            p_result = st.number_input("กำไร/ขาดทุน (บาท):", step=100.0, format="%.2f", help="กรอกแค่ตัวเลข ระบบจะใส่เครื่องหมายให้เอง", key="journal_p_result")
                            p_price = st.number_input("ราคาต่อหุ้น:", min_value=0.01, step=0.05, format="%.2f", key="journal_p_price")
                            p_qty = st.number_input("จำนวนหุ้น:", min_value=1, step=100, key="journal_p_qty")
                            p_comm = st.number_input("ค่าธรรมเนียม:", min_value=0.0, step=1.0, key="journal_p_comm")
                            
                        p_reason = st.text_area("เหตุผล/กลยุทธ์:", key="journal_p_reason")
                        submitted = st.button("ยืนยันรายการบันทึก", type="primary")
                        
                        if submitted:
                            if not p_ticker or p_ticker.strip() == "":
                                st.error("กรุณาระบุชื่อหุ้นให้เรียบร้อยครับ")
                            else:
                                total_val = (p_qty * p_price)
                                ticker_upper = p_ticker.upper()
                                
                                # Logic อัตโนมัติ: ถ้าเป็น Stop Loss หรือ ขาดทุน ให้บังคับเป็นค่าลบ
                                final_result = float(p_result)
                                if "Stop Loss" in p_type or "ขาดทุน" in p_status:
                                    final_result = -abs(final_result) 
                                else:
                                    final_result = abs(final_result)  
                                
                                transaction_date_str = str(p_sell_date) if p_status == "Closed (ขายแล้ว)" else str(p_buy_date)
                                
                                # 1. จัดการข้อมูล Portfolio (ใช้ .get ป้องกัน KeyError 100%)
                                found_idx = next((i for i, item in enumerate(st.session_state.my_portfolio) if item.get('หุ้น', item.get('Ticker', '')) == ticker_upper), -1)
                                
                                if "ซื้อ" in p_type and p_status != "Closed (ขายแล้ว)":
                                    log_cash_transaction(date=transaction_date_str, trans_type="ซื้อหุ้น " + ticker_upper, amount=-(total_val + p_comm), note=f"ซื้อ {p_qty} หุ้น ที่ราคา {p_price}")
                                    st.session_state.cash_balance -= (total_val + p_comm)
                                    
                                    if found_idx != -1:
                                        old = st.session_state.my_portfolio[found_idx]
                                        old_shares = float(old.get('shares', old.get('จำนวน', 0)))
                                        old_avg_price = float(old.get('avg_price', old.get('ต้นทุนเฉลี่ย', 0)))
                                        
                                        new_shares = old_shares + p_qty
                                        # คำนวณต้นทุนเฉลี่ยใหม่ (Average Cost) อย่างถูกต้องแม่นยำ
                                        new_cost = ((old_shares * old_avg_price) + total_val) / new_shares if new_shares > 0 else p_price
                                        
                                        st.session_state.my_portfolio[found_idx] = {
                                            'หุ้น': ticker_upper, 
                                            'shares': new_shares, 
                                            'avg_price': new_cost, 
                                            'Sector': p_sector
                                        }
                                    else:
                                        st.session_state.my_portfolio.append({
                                            'หุ้น': ticker_upper, 
                                            'shares': p_qty, 
                                            'avg_price': p_price, 
                                            'Sector': p_sector
                                        })
                                
                                else: # กรณีขาย (รองรับทั้งขายหมดและทยอยขาย)
                                    log_cash_transaction(date=transaction_date_str, trans_type="ขายหุ้น " + ticker_upper, amount=(total_val - p_comm), note=f"ขาย {p_qty} หุ้น ที่ราคา {p_price}")
                                    st.session_state.cash_balance += (total_val - p_comm)
                                    
                                    if found_idx != -1:
                                        old = st.session_state.my_portfolio[found_idx]
                                        old_shares = float(old.get('shares', old.get('จำนวน', 0)))
                                        
                                        new_shares = old_shares - p_qty
                                        
                                        if new_shares > 0:
                                            # อัปเดตจำนวนหุ้นที่เหลือ (ต้นทุนเฉลี่ยตัวเดิมไม่ต้องเปลี่ยน)
                                            st.session_state.my_portfolio[found_idx]['shares'] = new_shares
                                        else:
                                            # ถ้าขายหมดพอร์ต ลบรายการออก
                                            st.session_state.my_portfolio.pop(found_idx)
                                
                                # 2. เพิ่มข้อมูลเข้า Journal (รวม Sector)
                                if "journal_data" not in st.session_state:
                                    st.session_state.journal_data = []
                                    
                                new_entry = {
                                    "วันที่": transaction_date_str, 
                                    "วันที่ซื้อ": str(p_buy_date),
                                    "วันที่ขาย": str(p_sell_date) if p_status == "Closed (ขายแล้ว)" else "",
                                    "หุ้น": ticker_upper,
                                    "Sector": p_sector,
                                    "สถานะ": p_status,
                                    "ประเภท": p_type,
                                    "กำไร/ขาดทุน (บาท)": final_result,
                                    "ต้นทุน (บาท)": total_val,
                                    "ราคาหุ้นที่ซื้อ (บาท/หุ้น)": p_price,
                                    "จำนวนหุ้นที่ซื้อ": p_qty,
                                    "เหตุผล": p_reason
                                }
                                st.session_state.journal_data.append(new_entry)
                                
                                # 3. บันทึกข้อมูลลง Google Sheets
                                save_portfolio()
                                save_journal()
                                save_cash_balance(st.session_state.cash_balance)
                                save_portfolio_snapshot()
                                
                                st.success(f"บันทึก {ticker_upper} สำเร็จ! (กำไร/ขาดทุน: {final_result:,.2f} ฿)")
                                st.rerun()
                                
                    # 3. ตารางแสดงพอร์ต (เชื่อมต่อ Google Sheets)
                    st.divider()
                    st.subheader("📊 สรุปพอร์ตการลงทุน")

                    # 1. ตรวจสอบและโหลดข้อมูลพอร์ตจาก Google Sheets (ชีต PortfolioData) ถ้ายังไม่มีใน session_state
                    if "my_portfolio" not in st.session_state or not st.session_state["my_portfolio"]:
                        try:
                            client = get_gsheet_client()
                            sheet_portfolio = get_cached_spreadsheet(client, 'MyStockData').worksheet('PortfolioData')
                            raw_portfolio_data = sheet_portfolio.get_all_records()
                            
                            if raw_portfolio_data:
                                # แปลงชื่อคอลัมน์ให้สะอาด ป้องกันปัญหาช่องว่าง
                                cleaned_portfolio = []
                                for row in raw_portfolio_data:
                                    cleaned_row = {str(k).strip(): v for k, v in row.items()}
                                    cleaned_portfolio.append(cleaned_row)
                                st.session_state["my_portfolio"] = cleaned_portfolio
                        except Exception as e:
                            st.error(f"❌ ไม่สามารถดึงข้อมูลพอร์ตจาก Google Sheets (PortfolioData) ได้: {e}")
                    
                    # 2. ตรวจสอบว่ามีข้อมูลในพอร์ตหรือไม่
                    if "my_portfolio" in st.session_state and st.session_state["my_portfolio"]:
                        portfolio_list = []
                        total_invest = 0
                        total_value = 0
                        
                        # ฟังก์ชันกำหนดสีสำหรับตารางพอร์ต
                        def color_portfolio(val):
                            if isinstance(val, (int, float)):
                                color = '#26A69A' if val > 0 else '#EF5350' if val < 0 else 'black'
                                return f'color: {color}'
                            return None
                    
                        for row in st.session_state["my_portfolio"]:
                            # รองรับชื่อคอลัมน์ได้ทั้งภาษาไทยและอังกฤษ (กันเหนียว)
                            ticker = str(row.get('หุ้น', row.get('Ticker', ''))).strip()
                            
                            try:
                                shares = float(str(row.get('จำนวน', row.get('shares', 0))).replace(',', ''))
                            except:
                                shares = 0.0
                                
                            try:
                                avg_price = float(str(row.get('ต้นทุนเฉลี่ย', row.get('avg_price', 0.0))).replace(',', ''))
                            except:
                                avg_price = 0.0
                                
                            sector_val = row.get('Sector', 'General / Unspecified')
                            
                            if ticker:
                                try:
                                    # ดึงราคาตลาดล่าสุดผ่าน yfinance
                                    m_price = yf.Ticker(f"{ticker}.BK").history(period="1d")['Close'].iloc[-1]
                                except:
                                    m_price = avg_price
                                
                                cost_value = shares * avg_price
                                market_value = shares * m_price
                                profit = market_value - cost_value
                                profit_pct = (profit / cost_value * 100) if cost_value > 0 else 0
                                
                                portfolio_list.append({
                                    "หุ้น": ticker,
                                    "Sector": sector_val,
                                    "จำนวน": shares,
                                    "ต้นทุนเฉลี่ย": avg_price,
                                    "มูลค่าต้นทุน": cost_value,
                                    "ราคาตลาด": m_price,
                                    "มูลค่าตลาด": market_value,
                                    "กำไร/ขาดทุน": profit,
                                    "% กำไร/ขาดทุน": profit_pct
                                })
                                total_invest += cost_value
                                total_value += market_value
                        
                        if portfolio_list:
                            # ดึงยอดเงินสดคงเหลือจาก session_state (ถ้ามี ถ้าไม่มีให้เป็น 0)
                            cash_bal = st.session_state.get('cash_balance', 0.0)
                            
                            # สรุปยอดรวม Metrics ด้านบน
                            col_s1, col_s2, col_s3, col_s4 = st.columns(4)
                            col_s1.metric("เงินสดคงเหลือ", f"{cash_bal:,.0f} ฿")
                            col_s2.metric("เงินลงทุนรวม", f"{total_invest:,.0f} ฿")
                            col_s3.metric("มูลค่าปัจจุบัน", f"{total_value:,.0f} ฿")
                            diff = total_value - total_invest
                            col_s4.metric("กำไร/ขาดทุนรวม", f"{diff:,.0f} ฿", delta=f"{((diff)/total_invest)*100:.2f}%" if total_invest > 0 else "0%")
                    
                            # แสดงตารางพอร์ตหลัก
                            df_p = pd.DataFrame(portfolio_list)
                            df_display_p = df_p.drop(columns=['Sector']) if 'Sector' in df_p.columns else df_p
                            
                            st.dataframe(
                                df_display_p.style.format({
                                    "จำนวน": "{:,.0f}", "ต้นทุนเฉลี่ย": "{:.2f}", "มูลค่าต้นทุน": "{:,.0f}",
                                    "ราคาตลาด": "{:.2f}", "มูลค่าตลาด": "{:,.0f}", "กำไร/ขาดทุน": "{:,.0f}",
                                    "% กำไร/ขาดทุน": "{:.2f}%"
                                })
                                .map(color_portfolio, subset=["กำไร/ขาดทุน", "% กำไร/ขาดทุน"])
                                .set_properties(**{'text-align': 'right'})
                                .set_table_styles([{'selector': 'th', 'props': [('text-align', 'right')]}])
                                , use_container_width=True
                            )
                            
                            if st.button("✏️ แก้ไขข้อมูลหุ้นในพอร์ต"):
                                st.session_state.edit_mode = True
                        else:
                            st.info("ยังไม่มีข้อมูลหุ้นในพอร์ตการลงทุนครับ")
                    else:
                        st.info("ยังไม่มีข้อมูลในชีต PortfolioData กรุณาตรวจสอบ Google Sheets อีกครั้งครับ")
                    
                    # --- ส่วนแสดงกราฟสรุปพอร์ต ---
                    st.divider()
                    
                    # แบ่งคอลัมน์สัดส่วน 25% : 25% : 50%
                    col_p1, col_p2, col_p3 = st.columns([1, 1, 2])
                    
                    # 1. Pie Chart: มูลค่าตลาด (25%)
                    with col_p1:
                        st.subheader("🥧 มูลค่าตลาด")
                        fig_pie1 = px.pie(df_p, values='มูลค่าตลาด', names='หุ้น', hole=0.4)
                        fig_pie1.update_traces(
                            textposition='outside', 
                            textinfo='label+percent',
                            textfont=dict(size=9),
                            automargin=True
                        )
                        fig_pie1.update_layout(height=300, margin=dict(l=0, r=0, t=20, b=20), showlegend=False)
                        st.plotly_chart(fig_pie1, use_container_width=True)
                        st.markdown("<p style='text-align: center; font-size: 13px;'>สัดส่วนมูลค่าตลาดปัจจุบัน</p>", unsafe_allow_html=True)
                
                    # 2. Pie Chart: มูลค่าต้นทุน (25%)
                    with col_p2:
                        st.subheader("🥧 มูลค่าต้นทุน")
                        fig_pie2 = px.pie(df_p, values='มูลค่าต้นทุน', names='หุ้น', hole=0.4)
                        fig_pie2.update_traces(
                            textposition='outside', 
                            textinfo='label+percent',
                            textfont=dict(size=9),
                            automargin=True
                        )
                        fig_pie2.update_layout(height=300, margin=dict(l=0, r=0, t=20, b=20), showlegend=False)
                        st.plotly_chart(fig_pie2, use_container_width=True)
                        st.markdown("<p style='text-align: center; font-size: 13px;'>สัดส่วนเงินลงทุนต้นทุน</p>", unsafe_allow_html=True)
                    
                    # 3. Bar Chart: กำไร/ขาดทุน (50%)
                    with col_p3:
                        st.subheader("📈 กำไร/ขาดทุนรายตัว")
                        text_labels = [f"{row['กำไร/ขาดทุน']:,.0f} / {row['% กำไร/ขาดทุน']:.1f}%" for _, row in df_p.iterrows()]
                        bar_colors = ['#26A69A' if val >= 0 else '#EF5350' for val in df_p['กำไร/ขาดทุน']]
                        
                        fig_bar = go.Figure(data=[go.Bar(
                            x=df_p['หุ้น'], y=df_p['กำไร/ขาดทุน'],
                            marker_color=bar_colors, text=text_labels, textposition='auto'
                        )])
                        fig_bar.update_traces(textfont_size=10)
                        fig_bar.update_layout(height=300, margin=dict(l=10, r=10, t=30, b=10))
                        st.plotly_chart(fig_bar, use_container_width=True)
                        st.markdown("<p style='text-align: center; font-size: 13px;'>กำไร/ขาดทุน เป็น THB และ %</p>", unsafe_allow_html=True)
                
                    # --- ส่วนแดชบอร์ดวิเคราะห์ Sector Allocation ใน Tab Portfolio ---
                    # --- ส่วนแดชบอร์ดวิเคราะห์ Sector Allocation ใน Tab Portfolio ---
                    st.divider()
                    st.subheader("🥧 การกระจายตัวของพอร์ตตามกลุ่มอุตสาหกรรม (Sector Allocation)")
                
                    if not df_p.empty:
                        # จัดกลุ่มรวมตาม Sector ของหุ้นในพอร์ตปัจจุบัน (ใช้ as_index=False และ reset_index เพื่อความชัวร์)
                        df_port_sector = df_p.groupby('Sector', as_index=False).agg({
                            'มูลค่าตลาด': 'sum',
                            'มูลค่าต้นทุน': 'sum',
                            'หุ้น': lambda x: ', '.join(x.unique())
                        }).reset_index(drop=True)
                        
                        # 1. คำนวณสัดส่วน % ตาม "มูลค่าตลาด"
                        total_market_val = df_port_sector['มูลค่าตลาด'].sum()
                        if total_market_val > 0:
                            df_port_sector['Market_Weight_Pct'] = (df_port_sector['มูลค่าตลาด'] / total_market_val) * 100
                        else:
                            df_port_sector['Market_Weight_Pct'] = 0.0
                
                        # 2. คำนวณสัดส่วน % ตาม "เงินลงทุน (ต้นทุน)"
                        total_cost_val = df_port_sector['มูลค่าต้นทุน'].sum()
                        if total_cost_val > 0:
                            df_port_sector['Cost_Weight_Pct'] = (df_port_sector['มูลค่าต้นทุน'] / total_cost_val) * 100
                        else:
                            df_port_sector['Cost_Weight_Pct'] = 0.0
                            
                        # เรียงลำดับตามเงินลงทุนต้นทุนจากมากไปน้อย
                        df_port_sector = df_port_sector.sort_values(by='มูลค่าต้นทุน', ascending=False).reset_index(drop=True)
                
                        # 📊 แบ่ง 2 คอลัมน์สำหรับกราฟโดนัท (เงินลงทุนต้นทุน VS มูลค่าตลาด)
                        col_sec1, col_sec2 = st.columns(2)
                
                        with col_sec1:
                            st.markdown("###### 🥧 สัดส่วนตามเงินลงทุน (Cost Weight)")
                            fig_donut_cost = px.pie(
                                df_port_sector,
                                names='Sector',
                                values='มูลค่าต้นทุน',
                                hole=0.4,
                                color_discrete_sequence=px.colors.qualitative.Pastel
                            )
                            fig_donut_cost.update_traces(
                                textinfo='percent+label',
                                hovertemplate='<b>Sector:</b> %{label}<br><b>เงินลงทุนต้นทุน:</b> %{value:,.2f} ฿<br><b>สัดส่วนต้นทุน:</b> %{percent}'
                            )
                            fig_donut_cost.update_layout(
                                height=380,
                                margin=dict(l=10, r=10, t=40, b=40),
                                showlegend=False
                            )
                            if 'fig_donut_cost' in locals() and fig_donut_cost is not None:
                                st.plotly_chart(fig_donut_cost, use_container_width=True, key="donut_cost_chart")
                            else:
                                st.warning("ไม่มีข้อมูลสำหรับกราฟ Cost Weight")
                
                        with col_sec2:
                            st.markdown("###### 🥧 สัดส่วนตามมูลค่าตลาด (Market Weight)")
                            fig_donut_market = px.pie(
                                df_port_sector,
                                names='Sector',
                                values='มูลค่าตลาด',
                                hole=0.4,
                                color_discrete_sequence=px.colors.qualitative.Set3
                            )
                            fig_donut_market.update_traces(
                                textinfo='percent+label',
                                hovertemplate='<b>Sector:</b> %{label}<br><b>มูลค่าตลาด:</b> %{value:,.2f} ฿<br><b>สัดส่วนตลาด:</b> %{percent}'
                            )
                            fig_donut_market.update_layout(
                                height=380,
                                margin=dict(l=10, r=10, t=40, b=40),
                                showlegend=True
                            )
                            if 'fig_donut_market' in locals() and fig_donut_market is not None:
                                st.plotly_chart(fig_donut_market, use_container_width=True, key="donut_market_chart")
                            else:
                                st.warning("ไม่มีข้อมูลสำหรับกราฟ Market Weight")
                
                        # 📋 ตารางสรุปน้ำหนักการลงทุนแต่ละกลุ่ม
                        st.markdown("##### 📋 ตารางสรุปน้ำหนักการลงทุนแต่ละกลุ่มในพอร์ต")
                        display_port_sector = df_port_sector[[
                            'Sector', 'มูลค่าต้นทุน', 'Cost_Weight_Pct', 'มูลค่าตลาด', 'Market_Weight_Pct', 'หุ้น'
                        ]].copy()
                        
                        display_port_sector.columns = [
                            'กลุ่มอุตสาหกรรม (Sector)', 
                            'เงินลงทุนต้นทุน (บาท)', 
                            'สัดส่วนต้นทุน (%)', 
                            'มูลค่าตลาดรวม (บาท)', 
                            'สัดส่วนตลาด (%)', 
                            'รายชื่อหุ้นในกลุ่ม'
                        ]
                        
                        st.dataframe(
                            display_port_sector.style.format({
                                'เงินลงทุนต้นทุน (บาท)': '{:,.2f}',
                                'สัดส่วนต้นทุน (%)': '{:.2f} %',
                                'มูลค่าตลาดรวม (บาท)': '{:,.2f}',
                                'สัดส่วนตลาด (%)': '{:.2f} %'
                            }).set_properties(**{'text-align': 'right'}),
                            use_container_width=True,
                            hide_index=True  # เพิ่มคำสั่งนี้เพื่อซ่อนคอลัมน์ Index ที่เกินมาครับ
                        )
                                
                    else:
                        st.info("ยังไม่มีข้อมูลหุ้นในพอร์ตปัจจุบันครับ")
                        
                #########################
                with tab_dividend:
                    DATA_FILE = "dividend_database.csv"
                    
                    # โหลดข้อมูลจากไฟล์ CSV เข้า session_state ทุกครั้งที่เปิดหรือรีเฟรชแอป
                    if "dividend_data" not in st.session_state:
                        if os.path.exists(DATA_FILE):
                            try:
                                df_saved = pd.read_csv(DATA_FILE)
                                if not df_saved.empty:
                                    st.session_state.dividend_data = df_saved.to_dict('records')
                                else:
                                    st.session_state.dividend_data = []
                            except Exception:
                                st.session_state.dividend_data = []
                        else:
                            st.session_state.dividend_data = []
                            
                    st.markdown("#### 💰 บันทึกและจัดการข้อมูลเงินปันผล (Dividend Tracker)")
                    
                    # --- ส่วนที่ 1: อัปโหลดไฟล์ TSD Portal หรือ CSV ---
                    with st.expander("📤 อัปโหลดประวัติเงินปันผลจากรายงาน TSD หรือไฟล์ Excel/CSV"):
                        uploaded_div_file = st.file_uploader("เลือกไฟล์รายงานปันผล", type=['csv', 'xlsx', 'xls'], key="div_file")
                        if uploaded_div_file:
                            if st.button("ยืนยันการนำเข้าไฟล์ปันผล"):
                                try:
                                    if uploaded_div_file.name.endswith('.csv'):
                                        df_upload = pd.read_csv(uploaded_div_file)
                                    else:
                                        df_upload = pd.read_excel(uploaded_div_file)
                                    
                                    processed_rows = []
                                    
                                    if 'ชื่อย่อหลักทรัพย์' in df_upload.columns and 'วันที่จ่าย' in df_upload.columns:
                                        for idx, row in df_upload.iterrows():
                                            ticker = str(row.get('ชื่อย่อหลักทรัพย์', '')).strip().upper()
                                            if not ticker or ticker == 'NAN':
                                                continue
                                            if not ticker.endswith('.BK'):
                                                ticker = f"{ticker}.BK"
                                                
                                            pay_date = str(row.get('วันที่จ่าย', ''))[:10]
                                            total_div_before_tax = 0.0
                                            total_tax = 0.0
                                            
                                            for col in df_upload.columns:
                                                col_str = str(col)
                                                val = row.get(col, 0)
                                                try:
                                                    val_num = float(val) if pd.notna(val) else 0.0
                                                except:
                                                    val_num = 0.0
                                                    
                                                if 'จำนวนเงินปันผล' in col_str or 'ดอกเบี้ยหุ้นกู้' in col_str or 'เงินเทียบเท่าเงินปันผล' in col_str:
                                                    total_div_before_tax += val_num
                                                elif 'ภาษีของเงินปันผล' in col_str or 'ภาษีของดอกเบี้ย' in col_str:
                                                    total_tax += val_num
                                            
                                            net_receive = total_div_before_tax - total_tax
                                            
                                            cost_val = 0.0
                                            for cost_col in ['ต้นทุน', 'Cost', 'ทุนรวม', 'มูลค่าลงทุน']:
                                                if cost_col in df_upload.columns:
                                                    try:
                                                        cost_val = float(row.get(cost_col, 0))
                                                    except:
                                                        pass
                                            
                                            processed_rows.append({
                                                "วันที่ได้รับ": pay_date,
                                                "Ticker": ticker,
                                                "จำนวนหุ้น": 0.0,
                                                "ปันผลต่อหุ้น": 0.0,
                                                "ยอดรวมก่อนภาษี": total_div_before_tax,
                                                "ภาษีหัก ณ ที่จ่าย": total_tax,
                                                "ยอดรับสุทธิ": net_receive,
                                                "ต้นทุนหุ้น": cost_val,
                                                "หมายเหตุ": "นำเข้าจาก TSD Portal"
                                            })
                                    else:
                                        if 'ต้นทุนหุ้น' not in df_upload.columns:
                                            df_upload['ต้นทุนหุ้น'] = 0.0
                                        processed_rows = df_upload.to_dict('records')
                                    
                                    existing_df = pd.DataFrame(st.session_state.dividend_data)
                                    new_df = pd.DataFrame(processed_rows)
                                    
                                    if not existing_df.empty:
                                        combined_df = pd.concat([existing_df, new_df]).drop_duplicates(
                                            subset=['วันที่ได้รับ', 'Ticker', 'ยอดรับสุทธิ'], 
                                            keep='first'
                                        )
                                        added_count = len(combined_df) - len(existing_df)
                                    else:
                                        combined_df = new_df.drop_duplicates(subset=['วันที่ได้รับ', 'Ticker', 'ยอดรับสุทธิ'], keep='first')
                                        added_count = len(combined_df)
                                    
                                    st.session_state.dividend_data = combined_df.to_dict('records')
                                    
                                    # 🟢 ส่ง combined_df เข้าไปในฟังก์ชันบันทึกเพื่อป้องกัน Error missing positional argument
                                    save_dividend_data(combined_df)
                                    
                                    if added_count > 0:
                                        st.success(f"✅ นำเข้าข้อมูลสำเร็จ! (เพิ่มรายการใหม่ {added_count} รายการ, ข้ามรายการซ้ำ)")
                                    else:
                                        st.info("ℹ️ ข้อมูลในไฟล์นี้มีอยู่แล้วในระบบทั้งหมด จึงไม่มีการเพิ่มรายการซ้ำ")
                                    st.rerun()
                                    
                                except Exception as e:
                                    st.error(f"❌ เกิดข้อผิดพลาดในการอ่านไฟล์: {e}")
                                    
                    # --- ส่วนที่ 2: ฟอร์มกรอกข้อมูลแบบ Manual ---
                    with st.expander("➕ เพิ่มรายการรับเงินปันผล (Manual Input)", expanded=True):
                        with st.form("dividend_form", clear_on_submit=True):
                            col1, col2 = st.columns(2)
                            with col1:
                                div_date = st.date_input("วันที่ได้รับเงินปันผล", value=date.today())
                                ticker = st.text_input("ชื่อหุ้น (Ticker)").upper()
                                shares = st.number_input("จำนวนหุ้นที่ได้รับสิทธิ์", min_value=0.0, step=1.0)
                                total_cost = st.number_input("ต้นทุนหุ้นรวม (บาท)", min_value=0.0, step=100.0, format="%.2f", help="มูลค่าเงินลงทุนหรือต้นทุนรวมของหุ้นตัวนี้")
                            
                            with col2:
                                dps = st.number_input("เงินปันผลต่อหุ้น (บาท/หุ้น)", min_value=0.0000, format="%.4f", step=0.01)
                                auto_gross = shares * dps
                                gross_div = st.number_input("เงินปันผลรวมก่อนภาษี (บาท)", value=auto_gross, format="%.2f", step=1.0)
                                
                                tax_wht = gross_div * 0.10
                                net_div = gross_div - tax_wht
                                
                                st.caption(f"💡 คำนวณอัตโนมัติ: ภาษีหัก ณ ที่จ่าย 10% = {tax_wht:,.2f} ฿ | รับสุทธิ = {net_div:,.2f} ฿")
                            
                            notes = st.text_input("หมายเหตุ (เช่น ปันผล Q2/2026)")
                            submitted = st.form_submit_button("💾 บันทึกเงินปันผล")
                            
                            if submitted:
                                if ticker:
                                    formatted_ticker = ticker if ticker.endswith('.BK') else f"{ticker}.BK"
                                    new_entry = {
                                        "วันที่ได้รับ": str(div_date),
                                        "Ticker": formatted_ticker,
                                        "จำนวนหุ้น": shares,
                                        "ปันผลต่อหุ้น": dps,
                                        "ยอดรวมก่อนภาษี": gross_div,
                                        "ภาษีหัก ณ ที่จ่าย": tax_wht,
                                        "ยอดรับสุทธิ": net_div,
                                        "ต้นทุนหุ้น": total_cost,
                                        "หมายเหตุ": notes
                                    }
                                    st.session_state.dividend_data.append(new_entry)
                                    
                                    # แปลง session_state ทั้งหมดเป็น DataFrame แล้วส่งให้ save_dividend_data() บันทึก
                                    final_df = pd.DataFrame(st.session_state.dividend_data)
                                    save_dividend_data(final_df)
                                    
                                    st.success(f"✅ บันทึกเงินปันผลของหุ้น {formatted_ticker} เรียบร้อยแล้วครับ!")
                                    st.rerun()
                                else:
                                    st.warning("⚠️ กรุณากรอกชื่อหุ้น (Ticker)")
                                                        
                    # --- ส่วนที่ 3: สรุปภาพรวมและประวัติเงินปันผลรับ ---
                    st.markdown("---")
                    st.markdown("##### 📊 สรุปภาพรวมและประวัติเงินปันผลรับ")

                    # 🛠️ [เพิ่มส่วนนี้] เช็คและดึงข้อมูลจาก Google Sheets เสมอ หากใน session_state ยังไม่มีข้อมูล
                    if 'dividend_data' not in st.session_state or not st.session_state.dividend_data:
                        try:
                            client = get_gsheet_client()
                            # ดึงข้อมูลจาก worksheet ชื่อ 'Dividend' (ปรับชื่อให้ตรงกับชีตจริงของคุณ เช่น 'Dividend' หรือ 'Dividend_History')
                            div_records = get_cached_spreadsheet(client, 'MyStockData').worksheet('Dividend').get_all_records()
                            st.session_state.dividend_data = div_records
                        except Exception as e:
                            # ถ้าดึงไม่สำเร็จหรือยังไม่มีชีต ให้ปล่อยเป็น list เปล่า
                            st.session_state.dividend_data = []
                    
                    # หลังจากดึงข้อมูลแล้ว โค้ดส่วนเดิมของคุณจะทำงานต่อได้อย่างปกติครับ
                    if st.session_state.dividend_data:
                        df_div = pd.DataFrame(st.session_state.dividend_data)
                        
                        total_received = df_div['ยอดรับสุทธิ'].sum() if 'ยอดรับสุทธิ' in df_div.columns else 0
                        total_tax = df_div['ภาษีหัก ณ ที่จ่าย'].sum() if 'ภาษีหัก ณ ที่จ่าย' in df_div.columns else 0
                        
                        m1, m2 = st.columns(2)
                        m1.metric("💰 เงินปันผลรับสุทธิรวมทั้งสิ้น", f"{total_received:,.2f} ฿")
                        m2.metric("🏛️ ภาษีหัก ณ ที่จ่ายรวม", f"{total_tax:,.2f} ฿")
                        
                        st.markdown("<br>", unsafe_allow_html=True)
                        
                        with st.expander("📂 ดูตารางประวัติและแก้ไขข้อมูลปันผล", expanded=False):
                            edited_div_df = st.data_editor(df_div, use_container_width=True, key="div_editor")
                            
                            if st.button("💾 อัปเดตการแก้ไขตารางปันผล", key="update_div_btn"):
                                st.session_state.dividend_data = edited_div_df.to_dict('records')
                                save_dividend_data()
                                st.success("✅ อัปเดตข้อมูลสำเร็จ!")
                                st.rerun()
                                
                            csv_div = df_div.to_csv(index=False).encode('utf-8-sig')
                            st.download_button("📥 Export ประวัติปันผลเป็น CSV", data=csv_div, file_name="dividend_history.csv", mime="text/csv", key="export_div_btn")
                        
                        # --- ส่วนที่ 4: กราฟวิเคราะห์และสรุปยอดเงินปันผลรับ ---
                        st.markdown("---")
                        st.markdown("##### 📊 วิเคราะห์ข้อมูลเงินปันผล (Dividend Analytics)")
                        
                        if 'วันที่ได้รับ' in df_div.columns:
                            df_div['วันที่ได้รับ'] = pd.to_datetime(df_div['วันที่ได้รับ'], errors='coerce')
                            df_div['Year'] = df_div['วันที่ได้รับ'].dt.year.fillna(0).astype(int)
                        
                        col_f1, col_f2 = st.columns([2, 2])
                        with col_f1:
                            available_years = sorted([y for y in df_div['Year'].unique() if y > 0], reverse=True)
                            year_options = ["All Time (ทั้งหมด)"] + [str(y) for y in available_years]
                            selected_period = st.selectbox("📅 กรองช่วงเวลา (ปี):", year_options, key="div_year_filter")
                        
                        df_filtered_div = df_div.copy()
                        if selected_period != "All Time (ทั้งหมด)":
                            df_filtered_div = df_filtered_div[df_filtered_div['Year'] == int(selected_period)]
                        
                        if not df_filtered_div.empty:
                            total_received_filtered = df_filtered_div['ยอดรับสุทธิ'].sum() if 'ยอดรับสุทธิ' in df_filtered_div.columns else 0
                            total_tax_filtered = df_filtered_div['ภาษีหัก ณ ที่จ่าย'].sum() if 'ภาษีหัก ณ ที่จ่าย' in df_filtered_div.columns else 0
                            
                            mf1, mf2 = st.columns(2)
                            mf1.metric(f"💰 เงินปันผลรับสุทธิ ({selected_period})", f"{total_received_filtered:,.2f} ฿")
                            mf2.metric(f"🏛️ ภาษีหัก ณ ที่จ่ายรวม ({selected_period})", f"{total_tax_filtered:,.2f} ฿")
                            
                            st.markdown("<br>", unsafe_allow_html=True)
                        
                            # --- ส่วนที่ 5: วิเคราะห์ Dividend Yield on Cost (%) ---
                            st.markdown("---")
                            st.markdown(f"##### 🎯 วิเคราะห์ผลตอบแทนจากเงินปันผลเทียบกับต้นทุนหุ้น (Dividend Yield on Cost) - [{selected_period}]")
                            
                            if 'Ticker' in df_filtered_div.columns and 'ยอดรับสุทธิ' in df_filtered_div.columns and 'ต้นทุนหุ้น' in df_filtered_div.columns and 'จำนวนหุ้น' in df_filtered_div.columns:
                                df_calc = df_filtered_div.copy()
                                
                                if 'วันที่ได้รับ' in df_calc.columns:
                                    df_calc['วันที่ได้รับ_dt'] = pd.to_datetime(df_calc['วันที่ได้รับ'], errors='coerce')
                                    df_calc = df_calc.sort_values(by='วันที่ได้รับ_dt', ascending=True)
                                
                                df_div_sum = df_calc.groupby('Ticker')['ยอดรับสุทธิ'].sum().reset_index()
                                
                                df_latest = df_calc.groupby('Ticker').agg({
                                    'จำนวนหุ้น': 'last',
                                    'ต้นทุนหุ้น': 'last'
                                }).reset_index()
                                
                                # 1. รวมข้อมูลยอดรับสุทธิและต้นทุนหุ้นรายตัวหุ้นเข้าด้วยกัน
                                df_yield_analysis = pd.merge(df_div_sum, df_latest, on='Ticker', how='inner')
                                
                                # 2. แปลงข้อมูลตัวเลขด้วย pd.to_numeric อย่างปลอดภัย
                                df_yield_analysis['ยอดรับสุทธิ'] = pd.to_numeric(df_yield_analysis['ยอดรับสุทธิ'], errors='coerce').fillna(0)
                                df_yield_analysis['ต้นทุนหุ้น'] = pd.to_numeric(df_yield_analysis['ต้นทุนหุ้น'], errors='coerce').fillna(0)
                                
                                # 3. คำนวณ Yield_on_Cost โดยใช้คอลัมน์ 'ต้นทุนหุ้น'
                                df_yield_analysis['Yield_on_Cost'] = df_yield_analysis.apply(
                                    lambda row: (row['ยอดรับสุทธิ'] / row['ต้นทุนหุ้น'] * 100) if row['ต้นทุนหุ้น'] > 0 else 0.0,
                                    axis=1
                                )
                                
                                valid_cost_df = df_yield_analysis[(df_yield_analysis['ต้นทุนหุ้น'] > 0) & (df_yield_analysis['Yield_on_Cost'] <= 1000)]
                                
                                if not valid_cost_df.empty:
                                    total_portfolio_cost = valid_cost_df['ต้นทุนหุ้น'].sum()
                                    total_portfolio_dividend = valid_cost_df['ยอดรับสุทธิ'].sum()
                                    avg_yield_on_cost = (total_portfolio_dividend / total_portfolio_cost * 100) if total_portfolio_cost > 0 else 0.0
                                    
                                    kpi_col1, kpi_col2, kpi_col3 = st.columns(3)
                                    kpi_col1.metric(f"📊 Avg. Yield on Cost ({selected_period})", f"{avg_yield_on_cost:.2f}%")
                                    kpi_col2.metric(f"💰 ปันผลรับรวม ({selected_period})", f"{total_portfolio_dividend:,.2f} ฿")
                                    kpi_col3.metric("🏛️ ต้นทุนพอร์ตหุ้นรวม", f"{total_portfolio_cost:,.2f} ฿")
                                    
                                    st.markdown("<br>", unsafe_allow_html=True)
                                    
                                    df_yield_sorted = valid_cost_df.sort_values(by='Yield_on_Cost', ascending=True)
                                    df_yield_sorted['Text_Label'] = df_yield_sorted['Yield_on_Cost'].apply(lambda x: f"{x:.2f}%")
                                    
                                    fig_yield_bar = px.bar(
                                        df_yield_sorted,
                                        x='Yield_on_Cost',
                                        y='Ticker',
                                        orientation='h',
                                        text='Text_Label',
                                        color='Yield_on_Cost',
                                        color_continuous_scale='Tealgrn'
                                    )
                                    
                                    fig_yield_bar.update_traces(textposition='outside')
                                    fig_yield_bar.update_layout(
                                        xaxis_title=f"Dividend Yield on Cost (%) [{selected_period}]",
                                        yaxis_title="ชื่อหุ้น (Ticker)",
                                        height=max(320, len(df_yield_sorted) * 40),
                                        margin=dict(l=10, r=20, t=20, b=20),
                                        coloraxis_showscale=False
                                    )
                                    st.plotly_chart(fig_yield_bar, use_container_width=True)
                                    
                                    st.markdown(f"##### 📋 ตารางสรุป Yield on Cost ({selected_period})")
                                    df_table_display = df_yield_sorted[['Ticker', 'ยอดรับสุทธิ', 'ต้นทุนหุ้น', 'Yield_on_Cost']].copy()
                                    
                                    div_col_name = f"เงินปันผลรับรวม ({selected_period}) (บาท)"
                                    df_table_display.columns = ['ชื่อหุ้น (Ticker)', div_col_name, 'ต้นทุนรวมทั้งหมด (บาท)', 'Dividend Yield on Cost (%)']
                                    
                                    df_table_display[div_col_name] = df_table_display[div_col_name].apply(lambda x: f"{x:,.2f}")
                                    df_table_display['ต้นทุนรวมทั้งหมด (บาท)'] = df_table_display['ต้นทุนรวมทั้งหมด (บาท)'].apply(lambda x: f"{x:,.2f}")
                                    df_table_display['Dividend Yield on Cost (%)'] = df_table_display['Dividend Yield on Cost (%)'].apply(lambda x: f"{x:.2f}%")
                                    
                                    st.dataframe(df_table_display.reset_index(drop=True), use_container_width=True)
                                else:
                                    st.info(f"💡 ไม่มีข้อมูลปันผลหรือต้นทุนหุ้นในช่วงเวลา {selected_period}")
                            else:
                                st.info("ยังไม่มีข้อมูลเพียงพอสำหรับวิเคราะห์ Yield on Cost")
                                
                        # --- ส่วนที่ 6: ปุ่มล้างข้อมูลทั้งหมด (Danger Zone) ---
                        st.markdown("---")
                        with st.expander("⚠️ พื้นที่จัดการข้อมูล (Danger Zone)", expanded=False):
                            st.warning("การล้างข้อมูลจะทำการลบประวัติเงินปันผลทั้งหมดออกจากระบบอย่างถาวร กรุณาตรวจสอบให้แน่ใจก่อนดำเนินการ")
                            
                            if "confirm_clear_div" not in st.session_state:
                                st.session_state.confirm_clear_div = False
                                
                            if not st.session_state.confirm_clear_div:
                                if st.button("🗑️ ล้างข้อมูลเงินปันผลทั้งหมด", type="secondary", key="btn_clear_dividend_main"):
                                    st.session_state.confirm_clear_div = True
                                    st.rerun()
                            else:
                                st.error("❗ คุณแน่ใจจริงๆ หรือไม่ที่จะลบข้อมูลทั้งหมด? การกระทำนี้ไม่สามารถย้อนกลับได้")
                                col_c1, col_c2, _ = st.columns([1, 1, 2])
                                with col_c1:
                                    if st.button("✔️ ยืนยันการลบ", type="primary", key="btn_confirm_clear_div"):
                                        st.session_state.dividend_data = []
                                        save_dividend_data()
                                        st.session_state.confirm_clear_div = False
                                        st.success("✅ ล้างข้อมูลเงินปันผลทั้งหมดเรียบร้อยแล้วครับ")
                                        st.rerun()
                                with col_c2:
                                    if st.button("❌ ยกเลิก", key="btn_cancel_clear_div"):
                                        st.session_state.confirm_clear_div = False
                                        st.rerun()
                        
                        # ตรวจสอบว่ามีข้อมูลในระบบหรือไม่ ถ้าไม่มีให้แสดงข้อความแนะนำ
                        if df_div.empty:
                            st.info("💡 ยังไม่มีข้อมูลเงินปันผลในระบบ สามารถเพิ่มข้อมูลผ่านฟอร์มด้านบนหรืออัปโหลดไฟล์รายงาน TSD ได้เลยครับ")
                        else:
                            # --- กราฟที่ 4: ยอดปันผลรับสุทธิสะสมรายปี (Yearly Bar Chart) ---
                            st.markdown("---")
                            st.markdown("##### 📅 ยอดปันผลรับสุทธิสะสมรายปี (Yearly Dividend)")
                            if 'Year' in df_div.columns and 'ยอดรับสุทธิ' in df_div.columns:
                                df_yearly_sum = df_div[df_div['Year'] > 0].groupby('Year')['ยอดรับสุทธิ'].sum().reset_index()
                                df_yearly_sum['Year'] = df_yearly_sum['Year'].astype(str)
                                
                                fig_yearly = px.bar(
                                    df_yearly_sum,
                                    x='Year',
                                    y='ยอดรับสุทธิ',
                                    text=df_yearly_sum['ยอดรับสุทธิ'].apply(lambda x: f"{x:,.2f} ฿"),
                                    color='ยอดรับสุทธิ',
                                    color_continuous_scale='Blues'
                                )
                                fig_yearly.update_traces(textposition='outside')
                                fig_yearly.update_layout(
                                    xaxis_title="ปี (Year)",
                                    yaxis_title="ยอดปันผลรับสุทธิ (บาท)",
                                    height=380,
                                    margin=dict(l=10, r=10, t=20, b=20),
                                    coloraxis_showscale=False
                                )
                                st.plotly_chart(fig_yearly, use_container_width=True)
                                
                            # --- กราฟที่ 3: Stacked Horizontal Bar Chart (ยอดปันผลแยกตามหุ้น ซ้อนสีตามปี) ---
                            st.markdown("---")
                            st.markdown("##### 📊 ยอดปันผลรับสุทธิรายหุ้น (เรียงจากยอดมากไปน้อย แบ่งตามปีที่ได้รับ)")
                            
                            if 'Ticker' in df_filtered_div.columns and 'Year' in df_filtered_div.columns and 'ยอดรับสุทธิ' in df_filtered_div.columns:
                                df_stacked = df_filtered_div[df_filtered_div['Year'] > 0].groupby(['Ticker', 'Year'])['ยอดรับสุทธิ'].sum().reset_index()
                                
                                if not df_stacked.empty:
                                    df_ticker_totals = df_stacked.groupby('Ticker')['ยอดรับสุทธิ'].sum().reset_index()
                                    df_ticker_totals = df_ticker_totals.sort_values(by='ยอดรับสุทธิ', ascending=True)
                                    sorted_tickers = df_ticker_totals['Ticker'].tolist()
                                    
                                    df_stacked['Total_Stock_Sum'] = df_stacked['Ticker'].map(df_stacked.groupby('Ticker')['ยอดรับสุทธิ'].sum())
                                    df_stacked['Percentage'] = (df_stacked['ยอดรับสุทธิ'] / df_stacked['Total_Stock_Sum']) * 100
                                    df_stacked['Year_Str'] = df_stacked['Year'].astype(str)
                                    
                                    df_stacked['Text_Label'] = df_stacked.apply(
                                        lambda row: f"{row['ยอดรับสุทธิ']:,.0f} ฿ ({row['Percentage']:.1f}%)" if row['Percentage'] > 5 else "", 
                                        axis=1
                                    )
                                    
                                    fig_stacked_bar = px.bar(
                                        df_stacked,
                                        x='ยอดรับสุทธิ',
                                        y='Ticker',
                                        color='Year_Str',
                                        orientation='h',
                                        text='Text_Label',
                                        barmode='stack',
                                        category_orders={'Ticker': sorted_tickers},
                                        color_discrete_sequence=px.colors.qualitative.Bold
                                    )
                                    
                                    fig_stacked_bar.update_traces(
                                        textposition='inside', 
                                        insidetextanchor='middle'
                                    )
                                    
                                    fig_stacked_bar.update_layout(
                                        xaxis_title="ยอดปันผลรับสุทธิรวม (บาท)",
                                        yaxis_title="ชื่อหุ้น (Ticker)",
                                        height=max(350, len(sorted_tickers) * 45),
                                        margin=dict(l=10, r=20, t=20, b=20),
                                        legend_title="ปีที่ได้รับ (Year)"
                                    )
                                    st.plotly_chart(fig_stacked_bar, use_container_width=True)
                                else:
                                    st.info("ไม่มีข้อมูลเพียงพอสำหรับสร้างกราฟ Stacked Bar ในช่วงเวลานี้")
                            else:
                                st.info(f"ไม่มีข้อมูลเงินปันผลในช่วงปีที่เลือก")
                            
                            # --- ส่วนที่ 5: กราฟแท่งซ้อน %Yield / Cost รายปี (ที่เคยขาดหายไป) ---
                            st.markdown("---")
                            st.markdown("##### 🚀 วิเคราะห์การเติบโต Dividend Yield on Cost รายปี (Stacked Bar Chart)")
                            
                            if 'dividend_data' in st.session_state and st.session_state.dividend_data:
                                df_div_local = pd.DataFrame(st.session_state.dividend_data)
                            else:
                                df_div_local = pd.DataFrame()
                            
                            if not df_div_local.empty and 'Ticker' in df_div_local.columns and 'ยอดรับสุทธิ' in df_div_local.columns and 'ต้นทุนหุ้น' in df_div_local.columns and 'จำนวนหุ้น' in df_div_local.columns:
                                df_stack_calc = df_div_local.copy()
                                
                                if 'วันที่ได้รับ' in df_stack_calc.columns:
                                    df_stack_calc['วันที่ได้รับ_dt'] = pd.to_datetime(df_stack_calc['วันที่ได้รับ'], errors='coerce')
                                    df_stack_calc['Year'] = df_stack_calc['วันที่ได้รับ_dt'].dt.year.fillna(0).astype(int)
                                else:
                                    df_stack_calc['Year'] = 0
                                    
                                available_stack_years = sorted([y for y in df_stack_calc['Year'].unique() if y > 0], reverse=True)
                                stack_year_options = ["All Time (ทั้งหมด)"] + [str(y) for y in available_stack_years]
                                
                                selected_stack_period = st.selectbox(
                                    "📅 กรองช่วงเวลากราฟ Stacked Bar:", 
                                    stack_year_options, 
                                    key="stack_bar_year_filter"
                                )
                                
                                if selected_stack_period != "All Time (ทั้งหมด)":
                                    df_stack_filtered = df_stack_calc[df_stack_calc['Year'] == int(selected_stack_period)].copy()
                                else:
                                    df_stack_filtered = df_stack_calc.copy()
                                    
                                if not df_stack_filtered.empty:
                                    df_stack_filtered['Year_Str'] = df_stack_filtered['Year'].astype(str)
                                    
                                    df_latest = df_stack_calc.groupby('Ticker').agg({
                                        'จำนวนหุ้น': 'last',
                                        'ต้นทุนหุ้น': 'last'
                                    }).reset_index()
                                    
                                    # แปลงข้อมูลเป็นตัวเลขอย่างปลอดภัยก่อนนำมาคูณกัน
                                    df_latest['ต้นทุนหุ้น'] = pd.to_numeric(df_latest['ต้นทุนหุ้น'], errors='coerce').fillna(0)
                                    df_latest['จำนวนหุ้น'] = pd.to_numeric(df_latest['จำนวนหุ้น'], errors='coerce').fillna(0)
                                    
                                    # คำนวณต้นทุนรวมทั้งหมดของแต่ละ Ticker ใช้ชื่อคอลัมน์ว่า 'ต้นทุนหุ้น'
                                    df_latest['ต้นทุนหุ้น'] = df_latest['ต้นทุนหุ้น'] * df_latest['จำนวนหุ้น']
                                    
                                    df_grouped_yearly = df_stack_filtered.groupby(['Ticker', 'Year_Str'])['ยอดรับสุทธิ'].sum().reset_index()
                                    df_merged_yearly = pd.merge(df_grouped_yearly, df_latest[['Ticker', 'ต้นทุนหุ้น']], on='Ticker')
                                    
                                    # แปลงค่าให้เป็นตัวเลขเพื่อความปลอดภัยในการคำนวณ
                                    df_merged_yearly['ยอดรับสุทธิ'] = pd.to_numeric(df_merged_yearly['ยอดรับสุทธิ'], errors='coerce').fillna(0)
                                    df_merged_yearly['ต้นทุนหุ้น'] = pd.to_numeric(df_merged_yearly['ต้นทุนหุ้น'], errors='coerce').fillna(0)
                                    
                                    df_merged_yearly['Yield_on_Cost_Annual'] = df_merged_yearly.apply(
                                        lambda row: (row['ยอดรับสุทธิ'] / row['ต้นทุนหุ้น'] * 100) if row['ต้นทุนหุ้น'] > 0 else 0.0,
                                        axis=1
                                    )
                                    
                                    if not df_merged_yearly.empty:
                                        df_total_yield = df_merged_yearly.groupby('Ticker')['Yield_on_Cost_Annual'].sum().reset_index()
                                        sorted_tickers_yield = df_total_yield.sort_values(by='Yield_on_Cost_Annual', ascending=True)['Ticker'].tolist()
                                        
                                        df_merged_yearly['Text_Label'] = df_merged_yearly['Yield_on_Cost_Annual'].apply(
                                            lambda x: f"{x:.2f}%" if x > 0.5 else ""
                                        )
    
                                        fig_stacked = px.bar(
                                            df_merged_yearly,
                                            x='Yield_on_Cost_Annual',
                                            y='Ticker',
                                            color='Year_Str',
                                            orientation='h',
                                            barmode='stack',
                                            category_orders={'Ticker': sorted_tickers_yield},
                                            text='Text_Label',
                                            color_discrete_sequence=px.colors.qualitative.Prism
                                        )
                                        
                                        fig_stacked.update_traces(
                                            textposition='inside', 
                                            insidetextanchor='middle'
                                        )
                                        
                                        fig_stacked.update_layout(
                                            xaxis_title=f"Annual Dividend Yield on Cost (%) [{selected_stack_period}]",
                                            yaxis_title="ชื่อหุ้น (Ticker)",
                                            height=max(350, len(sorted_tickers_yield) * 45),
                                            margin=dict(l=10, r=20, t=20, b=20),
                                            legend_title="ปีที่ได้รับ (Year)"
                                        )
                                        st.plotly_chart(fig_stacked, use_container_width=True)
                                    else:
                                        st.info("ไม่มีข้อมูลเพียงพอสำหรับกราฟ Stacked Bar รายปีนี้")
                                else:
                                    st.info("ไม่มีข้อมูลในช่วงเวลาที่เลือกสำหรับกราฟนี้")
                            else:
                                st.info("💡 ยังไม่มีข้อมูลเงินปันผลในระบบ สามารถเพิ่มข้อมูลผ่านฟอร์มด้านบนหรืออัปโหลดไฟล์รายงาน TSD ได้เลยครับ")
                                            
                                                
                #########################
                with tab_journal:
                    st.markdown("#### 📖 บันทึกผลการเทรด (Trading Journal)")
                    
                    # --- ส่วนการ Upload ไฟล์ ---
                    with st.expander("📤 อัปโหลดข้อมูลจากไฟล์ Excel/CSV"):
                        uploaded_file = st.file_uploader("เลือกไฟล์ของคุณ", type=['csv', 'xlsx', 'xls'])
                        if uploaded_file:
                            if st.button("ยืนยันการนำเข้าข้อมูล"):
                                load_data_from_file(uploaded_file)
                    # --------------------------
                    
                    ################ เรียกการคำนวนนับจำนวนวันถือหุ้น #####################
                    def calculate_journal_stats(df):
                        df = df[df['สถานะ'] == 'Closed (ขายแล้ว)'].copy()
                        
                        # 1. จัดการคอลัมน์และคำนวณวันที่
                        if 'วันที่ซื้อ' not in df.columns: df['วันที่ซื้อ'] = df['วันที่'] 
                        if 'วันที่ขาย' not in df.columns: df['วันที่ขาย'] = df['วันที่'] 
                        
                        df['วันที่ซื้อ'] = pd.to_datetime(df['วันที่ซื้อ'])
                        df['วันที่ขาย'] = pd.to_datetime(df['วันที่ขาย'])
                        df['Holding_Days'] = (df['วันที่ขาย'] - df['วันที่ซื้อ']).dt.days.clip(lower=0)
                        
                        # 2. คำนวณเป็น % (Profit / Cost) * 100
                        df['ROI_Percent'] = (df['กำไร/ขาดทุน (บาท)'] / df['ต้นทุน (บาท)'].replace(0, np.nan)) * 100
                        
                        df['Year'] = df['วันที่ขาย'].dt.year
                        df['Month'] = df['วันที่ขาย'].dt.month
                        
                        # 3. สรุปผลเป็น % ตามที่ต้องการ
                        stats = df.groupby(['Year', 'Month']).agg(
                            Avg_Profit_Pct=('ROI_Percent', lambda x: x[x>0].mean()),
                            Avg_Loss_Pct=('ROI_Percent', lambda x: x[x<=0].mean()),
                            Win_Rate=('ROI_Percent', lambda x: (x>0).mean() * 100),
                            Trade_Count=('ROI_Percent', 'count'),
                            Max_Profit_Pct=('ROI_Percent', 'max'),
                            Max_Loss_Pct=('ROI_Percent', 'min'),
                            Avg_Days_Win=('Holding_Days', lambda x: x[df['ROI_Percent']>0].mean()),
                            Avg_Days_Loss=('Holding_Days', lambda x: x[df['ROI_Percent']<=0].mean())
                        )
                        stats = stats.round({'Avg_Days_Win': 0, 'Avg_Days_Loss': 0})
                        stats = stats.round(2)
                        return stats
                    ########################################################################
                
                    ### แสดงข้อมูลสถิติ รายเดือน รายปี ####
                    if st.session_state.journal_data:
                        df_journal = pd.DataFrame(st.session_state.journal_data)
                        
                        # --- เริ่มต้น Data Migration ---
                        cols_to_check = ['วันที่ซื้อ', 'วันที่ขาย']
                        for col in cols_to_check:
                            if col not in df_journal.columns:
                                df_journal[col] = df_journal['วันที่']
                        
                        df_journal['วันที่ซื้อ'] = pd.to_datetime(df_journal['วันที่ซื้อ'], errors='coerce')
                        df_journal['วันที่ขาย'] = pd.to_datetime(df_journal['วันที่ขาย'], errors='coerce')
                        st.session_state.journal_data = df_journal.to_dict('records')
                        # --- จบการ Data Migration ---
                    
                        # 2. ส่วนสรุป Metric 3 ค่าด้านบน (อิงจากช่วงเวลาที่เลือก)
                        with st.expander("📊 สถิติการเทรดรายเดือน", expanded=False):
                            stats_df = calculate_journal_stats(df_journal)
                            
                            st.markdown("##### 🎯 สถิติการเทรดจริง & การปรับจุดคัทลอส (RR 2:1)")
                            period = st.radio("ดูค่าเฉลี่ยย้อนหลัง:", ["3 เดือน", "6 เดือน", "1 ปี"], horizontal=True, key="stats_period")
                            
                            months_map = {"3 เดือน": 3, "6 เดือน": 6, "1 ปี": 12}
                            cutoff_date = pd.Timestamp.now() - pd.DateOffset(months=months_map[period])
                            
                            if 'วันที่ขาย' not in df_journal.columns:
                                df_journal['วันที่ขาย'] = df_journal['วันที่']
                            
                            df_journal['วันที่ขาย'] = pd.to_datetime(df_journal['วันที่ขาย'], errors='coerce')
                            
                            df_period = df_journal[(df_journal['วันที่ขาย'] >= cutoff_date) & 
                                                   (df_journal['สถานะ'] == 'Closed (ขายแล้ว)')].copy()
                            
                            if not df_period.empty:
                                if 'วันที่ซื้อ' not in df_period.columns:
                                    df_period['วันที่ซื้อ'] = df_period['วันที่']
                                if 'วันที่ขาย' not in df_period.columns:
                                    df_period['วันที่ขาย'] = df_period['วันที่']
                                    
                                df_period['วันที่ซื้อ'] = pd.to_datetime(df_period['วันที่ซื้อ'], errors='coerce')
                                df_period['วันที่ขาย'] = pd.to_datetime(df_period['วันที่ขาย'], errors='coerce')
                                df_period['Holding_Days'] = (df_period['วันที่ขาย'] - df_period['วันที่ซื้อ']).dt.days.clip(lower=0)
                                
                                col_profit_loss = 'กำไร/ขาดทุน (บาท)'
                                col_cost = 'ต้นทุน (บาท)'
                                
                                df_period[col_profit_loss] = pd.to_numeric(df_period[col_profit_loss], errors='coerce')
                                df_period[col_cost] = pd.to_numeric(df_period[col_cost], errors='coerce')
                                
                                w_rate = (df_period[col_profit_loss] > 0).mean() * 100
                                
                                profit_mask = (df_period[col_profit_loss] > 0) & (df_period[col_cost] > 0)
                                profit_series = (df_period.loc[profit_mask, col_profit_loss] / df_period.loc[profit_mask, col_cost]) * 100
                                avg_profit = profit_series.clip(upper=500).mean() if not profit_series.empty else 0
                    
                                loss_mask = (df_period[col_profit_loss] <= 0) & (df_period[col_cost] > 0)
                                loss_series = (df_period.loc[loss_mask, col_profit_loss] / df_period.loc[loss_mask, col_cost]) * 100
                                loss_series = loss_series[loss_series >= -100] 
                                avg_loss = loss_series.mean() if not loss_series.empty else 0
                                
                                loss_adj = (avg_profit / 2) * -1
                                
                                c1, c2, c3 = st.columns(3)
                                c1.metric("Win Rate", f"{w_rate:.1f} %")
                                c2.metric("Avg P/L", f"{avg_profit:.1f}% / {avg_loss:.1f}%")
                                c3.metric("Rec. Cut Loss (RR 2:1)", f"{loss_adj:.1f} %")
                            else:
                                st.info("ไม่มีข้อมูลย้อนหลังในช่วงเวลานี้")
                            
                            st.markdown("---")
                            
                            if not stats_df.empty:
                                years = sorted(stats_df.index.get_level_values('Year').unique())
                                selected_year = st.selectbox("เลือกปีที่ต้องการดูสถิติ:", years, key="stats_year")
                                
                                year_data = stats_df.loc[selected_year]
                                
                                styled_df = year_data.style.format({
                                    'Avg_Profit_Pct': '{:.2f} %',
                                    'Avg_Loss_Pct': '{:.2f} %',
                                    'Win_Rate': '{:.2f} %',
                                    'Max_Profit_Pct': '{:.2f} %',
                                    'Max_Loss_Pct': '{:.2f} %',
                                    'Avg_Days_Win': '{:.0f} วัน', 
                                    'Avg_Days_Loss': '{:.0f} วัน'
                                })
                                st.table(styled_df)
                    
                        ########################################################################
                        # 3. ตารางประวัติ 
                        df_journal = pd.DataFrame(st.session_state.journal_data)
                        df_journal['วันที่'] = pd.to_datetime(df_journal['วันที่'])            
                        
                        df_journal['temp_sort'] = df_journal['สถานะ'].apply(lambda x: 0 if "Open" in x else 1)
                        df_journal = df_journal.sort_values(by=['temp_sort', 'วันที่'], ascending=[True, False])
                        df_journal = df_journal.drop(columns=['temp_sort'])
                    
                        with st.expander("📂 ดูประวัติการเทรดย้อนหลัง", expanded=False):
                            items_per_page = 50
                            total_pages = (len(df_journal) - 1) // items_per_page + 1
                            page = st.number_input("หน้า:", min_value=1, max_value=total_pages, value=1, key="journal_page")
                            
                            start_idx = (page - 1) * items_per_page
                            df_display = df_journal.iloc[start_idx : start_idx + items_per_page]
                            
                            edited_journal = st.data_editor(df_display, use_container_width=True, key="journal_editor")
                            
                            if st.button("💾 อัปเดตตารางหน้านี้", key="save_journal_page"):
                                edited_journal['ราคาหุ้นที่ซื้อ (บาท/หุ้น)'] = pd.to_numeric(edited_journal['ราคาหุ้นที่ซื้อ (บาท/หุ้น)'], errors='coerce')
                                edited_journal['จำนวนหุ้นที่ซื้อ'] = pd.to_numeric(edited_journal['จำนวนหุ้นที่ซื้อ'], errors='coerce')
                                edited_journal['ต้นทุน (บาท)'] = edited_journal['ราคาหุ้นที่ซื้อ (บาท/หุ้น)'] * edited_journal['จำนวนหุ้นที่ซื้อ']
                                
                                date_cols = ['วันที่', 'วันที่ซื้อ', 'วันที่ขาย']
                                for col in date_cols:
                                    if col in edited_journal.columns:
                                        edited_journal[col] = pd.to_datetime(edited_journal[col], errors='coerce').dt.strftime('%Y-%m-%d')
                                
                                st.session_state.journal_data = edited_journal.to_dict('records')
                                save_journal()
                                st.success("บันทึกข้อมูลเรียบร้อยแล้วครับ!")
                            
                            csv = df_journal.to_csv(index=False).encode('utf-8-sig')
                            st.download_button("📥 Export เป็นไฟล์ Excel (CSV)", data=csv, file_name="trading_journal.csv", mime="text/csv", key="export_journal_csv")
                    else:
                        st.info("ยังไม่มีข้อมูลรายการเทรดในระบบครับ")
                
                
                    #################################################
                    # --- ตารางแสดงแผนการเทรด ---
                    with tab_plan:
                        st.subheader("📝 แผนการเทรดและตั้งค่า Alert")
                        
                        # 1. ส่วนฟอร์มเพิ่มหุ้นใหม่
                        with st.form("trading_plan_form", clear_on_submit=True):
                            col1, col2 = st.columns(2)
                            with col1:
                                ticker = st.text_input("ชื่อหุ้น:", value=st.session_state.get("selected_ticker", ""))
                                entry = st.number_input("ราคาเข้าซื้อ:", min_value=0.0, format="%.2f", value=0.0)
                                stop_loss = st.number_input("จุดตัดขาดทุน:", value=float(entry * 0.95) if entry > 0 else 0.0, format="%.2f")
                                support = st.number_input("แนวรับ:", min_value=0.0, format="%.2f", value=0.0)
                            with col2:
                                resistance = st.number_input("แนวต้าน:", min_value=0.0, format="%.2f", value=0.0)
                                take_profit = st.number_input("จุดขายทำกำไร:", min_value=0.0, format="%.2f", value=0.0)
                                image_url = st.text_input("วาง Link รูปภาพ (URL):")
                            
                            submit_button = st.form_submit_button("บันทึกแผนลงตาราง")
                        
                        if submit_button:
                            if not ticker:
                                st.error("กรุณาระบุชื่อหุ้นครับ!")
                            else:
                                from datetime import datetime
                                
                                # 1. สร้าง Dictionary ของหุ้นใหม่
                                new_data = {
                                    'Ticker': ticker, 'Entry_Price': entry, 'ราคาตลาด': 0.0,
                                    'Stop_Loss': stop_loss, 'แนวรับ': support, 'แนวต้าน': resistance, 
                                    'ห่างจาก_SL(%)': 0.0, 'Take_Profit': take_profit,
                                    'สถานะ': 'ปกติ', 'Timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    'Image_URL': image_url, 'Alert_Date': ''
                                }
                                
                                # 2. โหลดข้อมูลปัจจุบันจาก Google Sheet ออกมาก่อน
                                current_df = load_data("TradingPlan")
                                
                                # ถ้าตารางว่าง ให้สร้าง DataFrame ใหม่ขึ้นมาเลย
                                if current_df is None or current_df.empty:
                                    final_df = pd.DataFrame([new_data])
                                else:
                                    # รวมหุ้นเดิมกับหุ้นใหม่เข้าด้วยกัน
                                    new_df = pd.DataFrame([new_data])
                                    final_df = pd.concat([current_df, new_df], ignore_index=True)
                                    
                                # 3. บันทึกข้อมูลที่รวมแล้วด้วยฟังก์ชัน clear_and_save_data
                                # (เพราะฟังก์ชันนี้ลบของเก่าแล้วเขียนทับใหม่ เราจึงต้องส่ง 'ข้อมูลก้อนใหม่' ที่รวมตัวเก่าไปให้)
                                if clear_and_save_data(final_df, "TradingPlan"):
                                    st.success("บันทึกแผนเรียบร้อย!")
                                    st.cache_data.clear()
                                    st.rerun()
                                else:
                                    st.error("เกิดข้อผิดพลาดในการบันทึกข้อมูลครับ")
                 
                        # 2. ส่วนตารางแสดงผล
                        st.divider()
                        st.subheader("📊 ตารางแผนการเทรดของฉัน")
                        plan_df = load_data("TradingPlan")
                        
                        # กำหนดคอลัมน์มาตรฐาน (ลบ 'Alert_Date' ออกแล้ว)
                        cols = ['Ticker', 'Entry_Price', 'แนวรับ', 'แนวต้าน', 'ราคาตลาด', 'Stop_Loss', 'Take_Profit', 'ห่างจาก_SL(%)', 'สถานะ', 'Timestamp', 'Image_URL']
                        
                        if plan_df.empty or 'Ticker' not in plan_df.columns:
                            plan_df = pd.DataFrame(columns=cols)
                        else:
                            plan_df.columns = plan_df.columns.str.strip()
                        
                        # คำนวณข้อมูล
                        if not plan_df.empty and 'Ticker' in plan_df.columns:
                            plan_df.columns = plan_df.columns.str.strip()
                            
                            # แปลงคอลัมน์ตัวเลข
                            target_cols = ['Entry_Price', 'Stop_Loss', 'Take_Profit']
                            for c in target_cols:
                                if c in plan_df.columns:
                                    plan_df[c] = pd.to_numeric(plan_df[c], errors='coerce').fillna(0.0)
                                else:
                                    plan_df[c] = 0.0
                            
                            # ดึงราคาตลาด (Batch)
                            tickers = [f"{t}.BK" for t in plan_df['Ticker'].unique()]
                            try:
                                price_data = yf.download(tickers, period="1d", group_by='ticker', progress=False)['Close']
                                def get_price(t):
                                    symbol = f"{t}.BK"
                                    try:
                                        if isinstance(price_data, pd.DataFrame): return float(price_data[symbol].iloc[-1])
                                        return float(price_data.iloc[-1])
                                    except: return 0.0
                                plan_df['ราคาตลาด'] = plan_df['Ticker'].apply(get_price)
                            except:
                                plan_df['ราคาตลาด'] = 0.0
                        
                            # คำนวณห่างจาก SL และสถานะ
                            plan_df['ห่างจาก_SL(%)'] = np.where(plan_df['ราคาตลาด'] > 0, ((plan_df['ราคาตลาด'] - plan_df['Stop_Loss']) / plan_df['ราคาตลาด'] * 100), 0.0).round(2)
                            plan_df['สถานะ'] = plan_df.apply(check_alerts, axis=1)
                        
                        # แสดงตาราง (ลบ Alert_Date ออกจาก column_config แล้ว)
                        edited_df = st.data_editor(
                            plan_df[cols],
                            column_config={
                                "Ticker": st.column_config.TextColumn("หุ้น", disabled=True, width="small"),
                                "Entry_Price": st.column_config.NumberColumn("ราคาซื้อ", format="%.2f", width="small"),
                                "แนวรับ": st.column_config.NumberColumn("แนวรับ", format="%.2f", width="small"),
                                "แนวต้าน": st.column_config.NumberColumn("แนวต้าน", format="%.2f", width="small"),
                                "ราคาตลาด": st.column_config.NumberColumn("ราคาตลาด", format="%.2f", disabled=True, width="small"),
                                "Stop_Loss": st.column_config.NumberColumn("จุดตัดขาดทุน", format="%.2f", width="small"),
                                "Take_Profit": st.column_config.NumberColumn("จุดขายทำกำไร", format="%.2f", width="small"),
                                "ห่างจาก_SL(%)": st.column_config.NumberColumn("ห่างจาก SL (%)", format="%.2f%%", disabled=True, width="small"),
                                "สถานะ": st.column_config.TextColumn("สถานะ", disabled=True, width="medium"),
                                "Image_URL": st.column_config.LinkColumn("Plan trade", display_text="ดูรูปแผนเทรด", disabled=True, width="medium"),
                            },
                            use_container_width=True, 
                            key="fixed_plan_editor_v2", 
                            num_rows="dynamic"
                        )
                        
                        if st.button("💾 บันทึกการแก้ไข"):
                            final_df = edited_df.copy()
                            final_df['สถานะ'] = "" # ล้างค่าให้ระบบคำนวณใหม่
                            
                            for c in cols:
                                if c not in final_df.columns: final_df[c] = ""
                                    
                            if clear_and_save_data(final_df[cols], "TradingPlan"):
                                st.success("บันทึกและอัปเดตตารางเรียบร้อย!")
                                st.cache_data.clear()
                                st.rerun()
            
        ###################################################################
        # # --- ฟังก์ชัน Main tap stock Finish---
        ###################################################################
        # 2. ส่วน TFEX
        with tab_tfex:
            st.subheader("📝 ระบบเทรด TFEX")
            
            # 1. โหลดข้อมูล
            tfex_df = load_data("TFEX_History") 
            cash_df = load_data("Cash_Flow")
            
            # 2. กรองข้อมูลเฉพาะรายการที่ปิดสถานะแล้ว (Realized PnL)
            if not tfex_df.empty and 'Close_Price' in tfex_df.columns:
                # แปลงคอลัมน์ Close_Price ให้เป็นตัวเลขก่อน (errors='coerce' จะเปลี่ยนค่าที่อ่านไม่ได้เป็น NaN)
                # จากนั้น fillna(0) เพื่อเปลี่ยน NaN ให้เป็น 0 จะได้เปรียบเทียบ > 0 ได้
                close_prices = pd.to_numeric(tfex_df['Close_Price'], errors='coerce').fillna(0)
                
                # กรองเอาเฉพาะที่ราคามากกว่า 0
                closed_trades = tfex_df[close_prices > 0].copy()
            else:
                closed_trades = tfex_df.copy()
            
            # คำนวณ Net_Profit
            if not closed_trades.empty and 'Net_Profit' in closed_trades.columns:
                # แปลง Net_Profit เป็นตัวเลขด้วย เพื่อป้องกัน error ในอนาคต
                total_pnl = pd.to_numeric(closed_trades['Net_Profit'], errors='coerce').sum()
            else:
                total_pnl = 0
            # 3. คำนวณเงินต้นสุทธิ
            # ใช้ .astype(str).str.lower() เพื่อป้องกันปัญหาตัวอักษรพิมพ์เล็ก/ใหญ่
            total_deposit = cash_df[cash_df['Type'].astype(str).str.lower() == 'deposit']['Amount'].sum() if not cash_df.empty else 0
            total_withdraw = cash_df[cash_df['Type'].astype(str).str.lower() == 'withdraw']['Amount'].sum() if not cash_df.empty else 0
            net_capital = total_deposit - total_withdraw
            
            # 4. คำนวณพอร์ต (ใช้ Realized PnL)
            net_worth = net_capital + total_pnl
            growth_pct = (total_pnl / net_capital * 100) if net_capital > 0 else 0
            # ⭐️ เพิ่มบรรทัดนี้ เพื่อแชร์ค่าพอร์ต TFEX ไปให้หน้าหลักใช้งาน
            st.session_state['tfex_net_worth'] = net_worth
            
            # แสดง Dashboard
            c1, c2, c3 = st.columns(3)
            c1.metric("มูลค่าพอร์ตสุทธิ (Cash Basis)", f"{net_worth:,.2f} บาท")
            c2.metric("กำไรรวมสุทธิ (Realized)", f"{total_pnl:,.2f} บาท")
            c3.metric("การเติบโต", f"{growth_pct:.2f} %")
            st.divider()
        
            # --- เริ่มแถวที่ 2: Performance Metrics (รวมเชิงลึก) ---
            st.subheader("📊 Performance Monitor")
            
            # 1. สร้าง Filter ช่วงเวลา
            period_options = {"3 เดือน": 90, "6 เดือน": 180, "1 ปี": 365, "ทั้งหมด": 9999}
            selected_period = st.radio("เลือกช่วงเวลา:", list(period_options.keys()), horizontal=True, key="perf_filter")
            
            # 2. กรองข้อมูลตามช่วงเวลา
            perf_df = closed_trades.copy()
            if 'Date_Close' in perf_df.columns:
                perf_df['Date_Close'] = pd.to_datetime(perf_df['Date_Close'])
            else:
                # ถ้าไม่มีคอลัมน์ Date_Close ให้ลองเช็คว่ามีคอลัมน์วันที่ชื่ออื่นไหม เช่น 'Date' หรือข้ามไปก่อน
                if 'Date' in perf_df.columns:
                    perf_df['Date_Close'] = pd.to_datetime(perf_df['Date'])
            days_ago = period_options[selected_period]
            if days_ago != 9999:
                cutoff_date = pd.Timestamp.now() - pd.Timedelta(days=days_ago)
                if 'Date_Close' in perf_df.columns:
                    perf_df = perf_df[perf_df['Date_Close'] >= cutoff_date]
                elif 'Date' in perf_df.columns:
                    perf_df = perf_df[perf_df['Date'] >= cutoff_date]
        
            # 3. คำนวณ Metrics ทั้งหมดจาก perf_df ที่กรองแล้ว
            total_trades = len(perf_df)
            # ป้องกัน KeyError กรณีไม่มีคอลัมน์ Net_Profit
            if 'Net_Profit' in perf_df.columns:
                win_trades = len(perf_df[perf_df['Net_Profit'] > 0])
            elif 'กำไรสุทธิ' in perf_df.columns:
                win_trades = len(perf_df[perf_df['กำไรสุทธิ'] > 0])
            else:
                win_trades = 0
            win_rate = (win_trades / total_trades * 100) if total_trades > 0 else 0
            
            avg_win = perf_df[perf_df['Net_Profit'] > 0]['Net_Profit'].mean() if win_trades > 0 else 0
            avg_loss = perf_df[perf_df['Net_Profit'] <= 0]['Net_Profit'].abs().mean() if (total_trades - win_trades) > 0 else 0
            rr_ratio = (avg_win / avg_loss) if avg_loss > 0 else 0
            
            gross_profit = perf_df[perf_df['Net_Profit'] > 0]['Net_Profit'].sum()
            gross_loss = perf_df[perf_df['Net_Profit'] <= 0]['Net_Profit'].abs().sum()
            profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0)
            
            expectancy = (win_rate/100 * avg_win) - ((1 - win_rate/100) * avg_loss)
            
            # คำนวณเชิงลึก (Efficiency Analysis)
            perf_df['Points'] = perf_df['Net_Profit'] / 200
            avg_win_pts = perf_df[perf_df['Points'] > 0]['Points'].mean() if len(perf_df[perf_df['Points'] > 0]) > 0 else 0
            avg_loss_pts = perf_df[perf_df['Points'] <= 0]['Points'].abs().mean() if len(perf_df[perf_df['Points'] <= 0]) > 0 else 0
            
            # Max Drawdown (คำนวณจากช่วงที่กรอง)
            temp_df = perf_df.sort_values('Date_Close')
            temp_df['Cumulative'] = temp_df['Net_Profit'].cumsum()
            max_drawdown = (temp_df['Cumulative'] - temp_df['Cumulative'].cummax()).min() if not temp_df.empty else 0
            
            # ระยะเวลาถือครอง
            perf_df['Date_Open'] = pd.to_datetime(perf_df['Date_Open'])
            perf_df['Hold_Days'] = (perf_df['Date_Close'] - perf_df['Date_Open']).dt.days
            avg_hold = perf_df['Hold_Days'].mean() if not perf_df.empty else 0
        
            # 4. แสดงผลแบบ Grid
            # แถวแรก
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Win Rate", f"{win_rate:.1f}%")
            c2.metric("R:R Ratio", f"{rr_ratio:.2f}")
            c3.metric("Profit Factor", f"{profit_factor:.2f}")
            c4.metric("Expectancy", f"{expectancy:,.0f}")
            
            st.write("---") # เส้นคั่น
            
            # แถวสอง (เชิงลึก)
            e1, e2, e3, e4 = st.columns(4)
            e1.metric("กำไรเฉลี่ย (จุด)", f"{avg_win_pts:.1f} pts")
            e2.metric("ขาดทุนเฉลี่ย (จุด)", f"{avg_loss_pts:.1f} pts")
            e3.metric("Max Drawdown", f"{max_drawdown:,.0f} บาท")
            e4.metric("ระยะเวลาถือเฉลี่ย", f"{avg_hold:.1f} วัน")
            
            st.divider()
            
            # 3. สร้าง 3 Tabs
            sub_tfex_input, sub_tfex_close, sub_tfex_cash, sub_tfex_history = st.tabs([
            "➕ บันทึกเทรดใหม่", 
            "🏁 ปิดสถานะเทรด", 
            "➕ บันทึกเติม/ถอนเงิน", 
            "📜 ประวัติและ Portfolio"
            ])
            with sub_tfex_input:
                st.subheader("🛡 คำนวณขนาดสัญญา (Position Size)")
                
                # ดึงค่า ATR และ Multiplier ที่ใช้งานล่าสุดจาก session_state มาเป็นค่าตั้งต้น
                current_atr = st.session_state.get('active_atr', 6.5)
                
                c1, c2, c3 = st.columns(3)
                # เปลี่ยนเป็น Slider เลือกความเสี่ยง 0% ถึง 5% (เพิ่มทีละ 0.25% เพื่อความละเอียด)
                risk_pct = c1.slider("ความเสี่ยงที่ยอมรับได้ (% ของพอร์ต)", min_value=0.0, max_value=5.0, value=1.0, step=0.25)
                
                # ⭐️ ช่องกรอก ATR ที่เชื่อมโยงกับค่ากลาง (สามารถพิมพ์แก้ไขเพื่อดูจาก TradingView ได้เช่นกัน)
                user_atr = c2.number_input("ค่า ATR ปัจจุบัน (แก้ไขได้)", value=float(current_atr), step=0.1)
                
                # ช่องกรอกตัวคูณ Multiplier สำหรับ ATR
                atr_multiplier = c3.number_input("ตัวคูณ ATR (Multiplier)", value=1.5, step=0.1)
                
                # คำนวณระยะ Stop Loss จาก ATR ที่ใช้งานจริง (ATR * Multiplier)
                stop_loss_points = user_atr * atr_multiplier
                st.caption(f"📍 ระยะจุดตัดขาดทุนคำนวณจาก ATR อัตโนมัติ: **{stop_loss_points:.2f} จุด** (ATR: {user_atr} x Multiplier: {atr_multiplier})")
                
                # คำนวณเงินที่ยอมขาดทุนได้จริงจากเปอร์เซ็นต์พอร์ต (Net Worth)
                risk_amount = net_worth * (risk_pct / 100.0)
                
                # ใช้ตัวแปร Global ที่เราตั้งค่าไว้
                im_per_contract = IM_PER_CONTRACT 
                
                # คำนวณสัญญา (สมมติ 1 จุด TFEX = 200 บาท)
                contract_by_risk = risk_amount / (stop_loss_points * 200) if (stop_loss_points * 200) > 0 else 0
                contract_by_margin = net_worth / im_per_contract if im_per_contract > 0 else 0 # net_worth ดึงมาจาก Dashboard
                
                max_contracts = min(int(contract_by_risk), int(contract_by_margin))
                
                # แสดงผลแบบมืออาชีพ
                st.info(f"📋 ข้อมูลการคำนวณ:")
                st.write(f"- เงินต้นรวม (Net Worth): {net_worth:,.0f} บาท")
                st.write(f"- ยอมขาดทุนได้สูงสุด: **{risk_amount:,.2f} บาท** ({risk_pct}%)")
                st.write(f"- ค่า IM ปัจจุบัน: {im_per_contract:,.0f} บาท/สัญญา")
                
                if max_contracts <= 0:
                    st.error("⚠️ เงินในพอร์ตไม่เพียงพอที่จะเปิดสัญญาภายใต้เงื่อนไขความเสี่ยงนี้")
                else:
                    st.success(f"✅ **สรุป: คุณควรเปิดสถานะไม่เกิน {max_contracts} สัญญา**")
                            
                # 1. แสดงรายการที่ถืออยู่ (Open Positions)
                # 1. แสดงรายการที่ถืออยู่ (Open Positions)
                st.subheader("📊 สถานะที่ถืออยู่ (Open Positions)")
                
                tfex_df['Close_Price_Cleaned'] = pd.to_numeric(tfex_df['Close_Price'], errors='coerce').fillna(0)
                open_positions = tfex_df[tfex_df['Close_Price_Cleaned'] == 0].copy()
                
                if not open_positions.empty:
                    # ⭐️ เชื่อมโยงค่า ATR และ Multiplier ที่ผู้ใช้ใช้งานล่าสุด (จากฟอร์มด้านบน) มาแสดงและคำนวณในตาราง
                    open_positions['ATR'] = user_atr 
                    
                    # แปลงข้อมูลราคาเปิดและ ATR ให้เป็นตัวเลขเพื่อความปลอดภัย
                    open_positions['Open_Price'] = pd.to_numeric(open_positions['Open_Price'], errors='coerce')
                    open_positions['ATR'] = pd.to_numeric(open_positions['ATR'], errors='coerce')
                    
                    # คำนวณจุด Stop Loss จาก ATR แยกตามสถานะ Long / Short ของแต่ละไม้
                    # Long: ราคาเปิด - (ATR * Multiplier)
                    # Short: ราคาเปิด + (ATR * Multiplier)
                    open_positions['ATR_Stop_Loss'] = open_positions.apply(
                        lambda row: (row['Open_Price'] - (row['ATR'] * atr_multiplier)) if row['Status'] == 'Long' 
                        else (row['Open_Price'] + (row['ATR'] * atr_multiplier)), 
                        axis=1
                    )
                    
                    # แสดงผลตารางพร้อมคอลัมน์ ATR และ Stop Loss ที่คำนวณสดๆ ตรงกัน
                    st.dataframe(
                        open_positions[['Trade_ID', 'Date_Open', 'Series', 'Status', 'Size', 'Open_Price', 'ATR', 'ATR_Stop_Loss']], 
                        use_container_width=True
                    )
                else:
                    st.info("ไม่มีรายการที่ถืออยู่ในปัจจุบัน")
                
                # คำนวณ Margin Utilization
                total_margin_used = open_positions['Size'].sum() * IM_PER_CONTRACT 
                utilization = (total_margin_used / net_worth) * 100 if net_worth > 0 else 0
                
                # --- แบ่งหน้าจอเป็น 2 คอลัมน์ เพื่อวางกราฟคู่กัน ---
                col_left, col_right = st.columns(2)
                
                with col_left:
                    st.subheader("🎯 สถิติแพ้ / ชนะ (Win / Loss)")
                    # กรองเฉพาะรายการที่ปิดสถานะแล้ว (Close_Price > 0) มาคำนวณ Win/Loss
                    closed_positions = tfex_df[tfex_df['Close_Price_Cleaned'] > 0]
                    
                    if not closed_positions.empty and 'Win_Lose' in closed_positions.columns:
                        win_count = len(closed_positions[closed_positions['Win_Lose'] == 'Win'])
                        lose_count = len(closed_positions[closed_positions['Win_Lose'] == 'Lose'])
                    else:
                        win_count, lose_count = 0, 0
                    
                    # สร้างกราฟโดนัทแสดง Win/Loss ด้วย Plotly
                    fig_winloss = go.Figure(go.Pie(
                        labels=['Win (ชนะ)', 'Lose (แพ้)'],
                        values=[win_count, lose_count],
                        hole=0.5,
                        marker_colors=['#26A69A', '#EF5350']
                    ))
                    fig_winloss.update_layout(height=250, margin=dict(l=20, r=20, t=30, b=20), showlegend=True)
                    st.plotly_chart(fig_winloss, use_container_width=True)
                
                with col_right:
                    # 2. สร้าง Gauge Chart (กราฟ Margin เดิมของคุณ)
                    fig_gauge = go.Figure(go.Indicator(
                        mode = "gauge+number",
                        value = utilization,
                        domain = {'x': [0, 1], 'y': [0, 1]},
                        title = {'text': "Margin Utilization (%)"},
                        gauge = {
                            'axis': {'range': [0, 100]},
                            'bar': {'color': "darkblue"},
                            'steps': [
                                {'range': [0, 50], 'color': "#26A69A"},
                                {'range': [50, 80], 'color': "#FBC02D"},
                                {'range': [80, 100], 'color': "#EF5350"}
                            ],
                            'threshold': {
                                'line': {'color': "white", 'width': 4},
                                'thickness': 0.75,
                                'value': utilization
                            }
                        }
                    ))
                    
                    fig_gauge.update_layout(height=250, margin=dict(l=20, r=20, t=50, b=20))
                    st.plotly_chart(fig_gauge, use_container_width=True)
                                
                st.divider()
                
                # 2. ส่วนของฟอร์มรับค่าการเทรด TFEX และการดึง ATR อัตโนมัติด้วยปุ่มกด
                with st.form("tfex_entry_form", clear_on_submit=True):
                    st.subheader("🛡 คำนวณขนาดสัญญาและระบบ ATR Stop Loss")
                    
                    # ส่วนสำหรับกดปุ่มดึงค่า ATR ล่าสุด
                    col_btn1, col_btn2 = st.columns([1, 2])
                    with col_btn1:
                        fetch_atr_clicked = st.form_submit_button("🔄 ดึงค่า ATR ล่าสุด")
                    
                    # จัดการเก็บค่า ATR ไว้ใน session_state เมื่อมีการกดปุ่ม
                    if fetch_atr_clicked:
                        with st.spinner("กำลังดึงข้อมูลราคาจากตลาด..."):
                            latest_atr = get_auto_atr_cached("^SET50")
                            st.session_state['active_atr'] = latest_atr
                            st.success(f"ดึงค่า ATR สำเร็จ: {latest_atr} จุด")
                    
                    # กำหนดค่า ATR เริ่มต้นหากยังไม่เคยกดปุ่ม (Default เป็น 6.5 หรือค่าล่าสุดใน session)
                    default_atr = st.session_state.get('active_atr', 6.5)
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        date_open = st.date_input("วันที่เปิด")
                        series = st.text_input("Series (เช่น S50U26)", value="S50U26")
                        Status = st.selectbox("สถานะ:", ["Long", "Short"])
                    with col2:
                        entry = st.number_input("ราคา Open:", format="%.2f", value=950.0)
                        size = st.number_input("จำนวนสัญญา:", min_value=1, value=1)
                        trade_id_input = st.text_input("Trade ID (เว้นว่างเพื่อรันอัตโนมัติ):")  
                    with col3:
                        comm_input = st.number_input("ค่าคอมมิชชัน + ค่าธรรมเนียม (บาท):", min_value=0.0, step=10.0, value=50.0)
                        
                        # ⭐️ เพิ่มช่องให้พิมพ์แก้ไขค่า ATR ได้เอง (โดยดึงค่า default มาแสดง และยอมให้พิมพ์ทับได้เพื่อดูจาก TradingView)
                        user_atr = st.number_input("ค่า ATR (แก้ไขได้):", min_value=0.1, step=0.1, value=float(default_atr))
                        
                        # ตัวคูณ ATR (Multiplier)
                        atr_multiplier = st.number_input("ตัวคูณ ATR (Multiplier):", min_value=0.5, step=0.1, value=1.5)
                        
                        # คำนวณจุด SL จากค่า ATR ที่ผู้ใช้ใช้งานจริง (user_atr)
                        calculated_sl_pts = user_atr * atr_multiplier
                        st.write(f"📌 Stop Loss แนะนำ: **{calculated_sl_pts:.2f} จุด** (จาก ATR: {user_atr})")
                        
                        reason = st.text_area("เหตุผลที่เข้าเทรด:")
                    
                    # ปุ่มยืนยันการเปิดสถานะเทรดจริง
                    submit_trade = st.form_submit_button("เปิดสถานะเทรด")
                    
                    if submit_trade:
                        final_trade_id = trade_id_input.strip()
                        if not final_trade_id:
                            final_trade_id = f"TX-{pd.Timestamp.now().strftime('%Y%m%d%H%M%S')}"
                            
                        # คำนวณราคา Stop Loss จริงบนกระดาน โดยใช้ calculated_sl_pts ที่คำนวณจาก user_atr
                        calculated_sl_price = (entry - calculated_sl_pts) if Status == "Long" else (entry + calculated_sl_pts)
                            
                        required_columns = [
                            "Trade_ID", "Date_Open", "Date_Close", "Series", "Status", 
                            "Size", "Open_Price", "Close_Price", "Realized", 
                            "Comm", "Net_Profit", "Win_Lose", "Points", "Reason"
                        ]
                        
                        # สร้าง Dictionary ใหม่ที่มั่นใจว่ามีครบทุกคอลัมน์ (เผื่ออนาคตมีการเพิ่ม/ลด)
                        new_record = {
                            "Trade_ID": final_trade_id,
                            "Date_Open": date_open.strftime("%Y-%m-%d"),
                            "Date_Close": "",
                            "Series": series,
                            "Status": Status,
                            "Size": size,
                            "Open_Price": entry,
                            "Close_Price": 0,
                            "Realized": 0,
                            "Comm": comm_input,
                            "Net_Profit": 0,
                            "Win_Lose": "",
                            "Points": 0,  # เพิ่มคอลัมน์ Points ที่ขาดไปใน dictionary เดิม
                            "Reason": f"{reason} | ATR SL: {calculated_sl_price:.2f}"
                        }
                        
                        # สร้าง DataFrame และ Reindex ให้ตรงเป๊ะ
                        df_to_save = pd.DataFrame([new_record])
                        df_to_save = df_to_save.reindex(columns=required_columns)
                        
                        with st.spinner("⏳ กำลังเปิดสถานะและบันทึกลง Google Sheets..."):
                            if save_data_to_sheet(df_to_save, "TFEX_History"):
                                st.cache_data.clear()
                                st.toast("เปิดสถานะเทรดเรียบร้อย! 🎉", icon="✅")
                                st.rerun()
                                
            with sub_tfex_close:
                st.subheader("🏁 ปิดสถานะเทรด")
                
                # ดึงข้อมูลจากฟังก์ชัน load_data สดๆ ใหม่ๆ
                tfex_df = load_data("TFEX_History")
                
                # ตรวจสอบว่ามีข้อมูลและคอลัมน์ที่จำเป็นอยู่ครบถ้วนหรือไม่
                if not tfex_df.empty and 'Close_Price' in tfex_df.columns:
                    # แปลง Close_Price เป็นตัวเลข (ถ้าค่าว่าง, ไม่มี หรือเป็น 0 จะนับว่ายังไม่ปิดสถานะ)
                    tfex_df['Close_Price_Cleaned'] = pd.to_numeric(tfex_df['Close_Price'], errors='coerce').fillna(0)
                    open_trades = tfex_df[tfex_df['Close_Price_Cleaned'] == 0]
                else:
                    open_trades = pd.DataFrame()
                
                if not open_trades.empty and 'Trade_ID' in open_trades.columns:
                    # ให้เลือก Trade_ID
                    selected_trade_id = st.selectbox("เลือก Trade ที่ต้องการปิด:", open_trades['Trade_ID'].tolist())
                    
                    # แสดงรายละเอียดออเดอร์เดิมให้เห็นก่อนปิด (ดึงตาม Header จริงของคุณ)
                    trade_detail = open_trades[open_trades['Trade_ID'] == selected_trade_id].iloc[0]
                    
                    status_val = trade_detail.get('Status', 'N/A')
                    size_val = trade_detail.get('Size', 0)
                    open_price_val = trade_detail.get('Open_Price', 0)
                    series_val = trade_detail.get('Series', 'N/A')
                    
                    st.info(f"🔍 รายละเอียด: ซีรีส์ **{series_val}** | สถานะ: **{status_val}** | จำนวน: **{size_val}** สัญญา | ราคาเปิด: **{open_price_val}**")
                    
                    # ฟอร์มกรอกข้อมูลปิดสถานะ
                    c_col1, c_col2 = st.columns(2)
                    
                    # แปลง Open_Price เป็น float สำหรับค่าเริ่มต้นใน number_input
                    default_open_price = pd.to_numeric(open_price_val, errors='coerce')
                    if pd.isna(default_open_price):
                        default_open_price = 0.0
                        
                    close_price = c_col1.number_input("ราคาปิด (Close_Price):", value=float(default_open_price), step=0.1, format="%.2f")
                    close_date = c_col2.date_input("วันที่ปิด (Date_Close):")
                    
                    if st.button("ยืนยันการปิดสถานะ", use_container_width=True, type="primary"):
                        # บันทึกปิดสถานะพร้อม Loading Spinner และล้าง Cache ทันที
                        with st.spinner("⏳ กำลังบันทึกการปิดสถานะและคำนวณผลลัพธ์..."):
                            # ส่งค่าไปอัปเดต (ตรวจสอบให้แน่ใจว่าฟังก์ชัน update_trade_close รับพารามิเตอร์ตามนี้)
                            success = update_trade_close('1moD7gjKnnLXDvCTfwVVhBmDwo5t0c7emErGbtJtGEWU', selected_trade_id, close_price, str(close_date))
                            
                            if success:
                                st.cache_data.clear()  # ล้าง Cache ข้อมูลในหน่วยความจำ
                                st.toast("ปิดสถานะสำเร็จ และคำนวณกำไรเรียบร้อย! 🏁", icon="🏆")
                                st.rerun()             # โหลดหน้าจอใหม่เพื่อให้ข้อมูลปัจจุบันที่สุดแสดงทันที
                            else:
                                st.error("เกิดข้อผิดพลาดในการบันทึกข้อมูลลงฐานข้อมูล กรุณาลองใหม่อีกครั้ง")
                else:
                    st.info("ไม่มีรายการที่ถือครองอยู่ครับ (ไม่พบรายการที่ Close_Price เป็นค่าว่างหรือ 0)")
                    
            with sub_tfex_cash:
                st.subheader("💰 บันทึกเติม/ถอนเงิน")
                
                with st.form("cash_flow"):
                    col1, col2 = st.columns(2)
                    with col1:
                        cash_date = st.date_input("วันที่:")
                        cash_type = st.selectbox("ประเภท:", ["Deposit", "Withdraw"])
                    with col2:
                        amount = st.number_input("จำนวนเงิน (บาท):", min_value=0.0, step=100.0)
                        note = st.text_input("หมายเหตุ:")
                    
                    if st.form_submit_button("บันทึกรายการ"):
                        new_cash = pd.DataFrame([{
                            "Date": str(cash_date),
                            "Type": cash_type,
                            "Amount": amount,
                            "Note": note
                        }])
                        if save_cash_to_gsheet(new_cash, "Cash_Flow"):
                            st.success("บันทึกข้อมูลเงินเรียบร้อย!")
                            st.rerun()
        
                st.divider()
                st.write("รายการล่าสุด:")
                st.dataframe(cash_df, use_container_width=True)
            
            with sub_tfex_history:
                st.subheader("📜 ประวัติการเทรดและกำไรสะสม")
                
                if not tfex_df.empty and 'Net_Profit' in tfex_df.columns:
                    # 1. จัดเตรียมข้อมูล
                    # แปลงคอลัมน์ Close_Price เป็นตัวเลขก่อนเปรียบเทียบ > 0 ป้องกัน TypeError
                    close_prices_5154 = pd.to_numeric(tfex_df['Close_Price'], errors='coerce').fillna(0)
                    closed_trades = tfex_df[close_prices_5154 > 0].copy()
                    
                    # 3. ตารางแสดงราย Series (เปรียบเทียบว่า Series ไหนเทรดแล้วกำไรที่สุด)
                    st.write("📊 สรุปผลงานราย Series:")
                    series_perf = perf_df.groupby('Series').agg({
                        'Net_Profit': 'sum',
                        'Trade_ID': 'count'
                    }).rename(columns={'Trade_ID': 'Trades', 'Net_Profit': 'Total PnL'})
                    
                    st.dataframe(series_perf.sort_values(by='Total PnL', ascending=False), use_container_width=True)
    
                    # --- กราฟแสดงการเติบโตของพอร์ต TFEX ---
                    st.subheader("📈 กราฟการเติบโตของพอร์ต (Portfolio Growth)")
    
                    if not perf_df.empty:
                        # 1. ทำตัวเลือกช่วงเวลา (Quick Filter) สำหรับกราฟ TFEX
                        c_f1, c_f2 = st.columns([2, 2])
                        with c_f1:
                            tfex_view_range = st.selectbox(
                                "⏳ เลือกช่วงเวลาแสดงผล (TFEX):",
                                ["ทั้งหมด (All Time)", "3 เดือนล่าสุด", "6 เดือนล่าสุด", "1 ปีล่าสุด (YTD / 12M)"],
                                key="tfex_line_view_range"
                            )
                        
                        # แปลงคอลัมน์วันที่ให้เป็น datetime
                        perf_df['Date_Close'] = pd.to_datetime(perf_df['Date_Close'], errors='coerce')
                        df_tfex_filtered = perf_df.dropna(subset=['Date_Close']).sort_values('Date_Close').copy()
                        
                        max_date = df_tfex_filtered['Date_Close'].max()
                        initial_capital_base = net_capital  # เงินต้นเริ่มต้น
                        
                        # กรองข้อมูลตามช่วงเวลาที่เลือก และคำนวณกำไรย้อนหลังที่ถูกตัดออกไปรวมกับฐานเงินต้น
                        if tfex_view_range == "3 เดือนล่าสุด":
                            start_date = max_date - pd.DateOffset(months=3)
                            past_slice = df_tfex_filtered[df_tfex_filtered['Date_Close'] < start_date]
                            initial_capital_base += past_slice['Net_Profit'].sum()
                            df_tfex_filtered = df_tfex_filtered[df_tfex_filtered['Date_Close'] >= start_date]
                        elif tfex_view_range == "6 เดือนล่าสุด":
                            start_date = max_date - pd.DateOffset(months=6)
                            past_slice = df_tfex_filtered[df_tfex_filtered['Date_Close'] < start_date]
                            initial_capital_base += past_slice['Net_Profit'].sum()
                            df_tfex_filtered = df_tfex_filtered[df_tfex_filtered['Date_Close'] >= start_date]
                        elif tfex_view_range == "1 ปีล่าสุด (YTD / 12M)":
                            start_date = max_date - pd.DateOffset(years=1)
                            past_slice = df_tfex_filtered[df_tfex_filtered['Date_Close'] < start_date]
                            initial_capital_base += past_slice['Net_Profit'].sum()
                            df_tfex_filtered = df_tfex_filtered[df_tfex_filtered['Date_Close'] >= start_date]
                    
                        if not df_tfex_filtered.empty:
                            # 2. Dynamic Aggregation: ถ้าระยะเวลานานกว่า 1 ปี ให้ยุบกลุ่มเป็น "รายเดือน" เพื่อความสะอาดของกราฟ
                            date_span_days = (df_tfex_filtered['Date_Close'].max() - df_tfex_filtered['Date_Close'].min()).days
                            
                            if date_span_days > 365 and tfex_view_range == "ทั้งหมด (All Time)":
                                df_tfex_filtered['Period_Key'] = df_tfex_filtered['Date_Close'].dt.to_period('M')
                                df_tfex_filtered['Time_Label'] = df_tfex_filtered['Period_Key'].apply(lambda r: r.strftime('%b %Y'))
                                df_tfex_filtered['Sort_Time'] = df_tfex_filtered['Period_Key'].dt.start_time
                                agg_freq_text = "รายเดือน (มุมมองระยะยาว)"
                            else:
                                df_tfex_filtered['Period_Key'] = df_tfex_filtered['Date_Close'].dt.to_period('W-MON')
                                df_tfex_filtered['Time_Label'] = df_tfex_filtered['Period_Key'].apply(lambda r: f"W{r.week} {r.start_time.strftime('%b %Y')}")
                                df_tfex_filtered['Sort_Time'] = df_tfex_filtered['Period_Key'].dt.start_time
                                agg_freq_text = "รายสัปดาห์ (เจาะลึก)"
                    
                            with c_f2:
                                st.markdown(f"<p style='padding-top:28px; color:gray; font-size:13px;'>ℹ️ ความละเอียด: <b>{agg_freq_text}</b></p>", unsafe_allow_html=True)
                    
                            # รวมกำไรตามช่วงเวลาที่จัดกลุ่ม
                            growth_df = df_tfex_filtered.groupby(['Sort_Time', 'Time_Label'], as_index=False).agg({
                                'Net_Profit': 'sum'
                            }).sort_values('Sort_Time')
                            
                            # คำนวณมูลค่าพอร์ตสะสม
                            growth_df['Cumulative_Profit'] = growth_df['Net_Profit'].cumsum()
                            growth_df['Portfolio_Value'] = initial_capital_base + growth_df['Cumulative_Profit']
                            
                            # เพิ่มจุดเริ่มต้น (Start Point) ให้กราฟเริ่มสวยงามที่ฐานเงินต้น
                            start_date_point = growth_df['Sort_Time'].min() - pd.Timedelta(days=1)
                            start_row = pd.DataFrame({
                                'Sort_Time': [start_date_point], 
                                'Time_Label': ['จุดเริ่มต้น'], 
                                'Portfolio_Value': [initial_capital_base]
                            })
                            growth_df = pd.concat([start_row, growth_df[['Sort_Time', 'Time_Label', 'Portfolio_Value']]], ignore_index=True)
                            growth_df = growth_df.sort_values('Sort_Time').reset_index(drop=True)
                    
                            # 3. สร้างกราฟเส้นด้วย Plotly
                            fig_growth = px.line(
                                growth_df, 
                                x='Time_Label', 
                                y='Portfolio_Value',
                                markers=True,
                                line_shape='spline'
                            )
                            
                            # ปรับแต่งหน้าตาให้ดูมืออาชีพ พร้อมเผื่อสเกลแกน Y ด้านบนไม่ให้เส้นชนขอบ
                            y_max = growth_df['Portfolio_Value'].max()
                            y_min = growth_df['Portfolio_Value'].min()
                            y_upper_margin = (y_max - y_min) * 0.15 if y_max != y_min else y_max * 0.15
                    
                            fig_growth.update_traces(line=dict(color='#26A69A', width=3))
                            fig_growth.update_layout(
                                xaxis_title="ช่วงเวลา",
                                yaxis_title="มูลค่าพอร์ต (บาท)",
                                yaxis=dict(range=[y_min * 0.98, y_max + y_upper_margin]),
                                margin=dict(l=20, r=20, t=30, b=20),
                                hovermode="x unified"
                            )
                            
                            st.plotly_chart(fig_growth, use_container_width=True)
                        else:
                            st.info("ไม่มีข้อมูลในช่วงเวลาที่เลือก")
                    else:
                        st.info("ยังไม่มีข้อมูลประวัติการเทรด TFEX ที่ปิดสถานะ")
    
                    # --- สรุปผลรายเดือนแบบ Combo Chart & Table ---
                    st.divider()
                    st.subheader("🗓 สรุปผลรายเดือน")
                    if not closed_trades.empty:
                        # 1. เพิ่มตัวเลือกช่วงเวลา (Quick Filter) สำหรับสรุปผลรายเดือน
                        col_f1, col_f2 = st.columns([2, 2])
                        with col_f1:
                            monthly_view_range = st.selectbox(
                                "⏳ เลือกช่วงเวลาแสดงผล (สรุปรายเดือน):",
                                ["ทั้งหมด (All Time)", "3 เดือนล่าสุด", "6 เดือนล่าสุด", "1 ปีล่าสุด (YTD / 12M)"],
                                key="monthly_view_range"
                            )
                        
                        # แปลงคอลัมน์วันที่ให้เป็น datetime และสำเนาข้อมูล
                        closed_trades['Date_Close'] = pd.to_datetime(closed_trades['Date_Close'], errors='coerce')
                        df_monthly_filtered = closed_trades.dropna(subset=['Date_Close']).sort_values('Date_Close').copy()
                        
                        max_date = df_monthly_filtered['Date_Close'].max()
                        capital_base_for_monthly = net_capital  # เงินต้นเริ่มต้น
                        
                        # กรองข้อมูลตามช่วงเวลาที่ผู้ใช้เลือก
                        if monthly_view_range == "3 เดือนล่าสุด":
                            start_date = max_date - pd.DateOffset(months=3)
                            past_slice = df_monthly_filtered[df_monthly_filtered['Date_Close'] < start_date]
                            capital_base_for_monthly += past_slice['Net_Profit'].sum()
                            df_monthly_filtered = df_monthly_filtered[df_monthly_filtered['Date_Close'] >= start_date]
                        elif monthly_view_range == "6 เดือนล่าสุด":
                            start_date = max_date - pd.DateOffset(months=6)
                            past_slice = df_monthly_filtered[df_monthly_filtered['Date_Close'] < start_date]
                            capital_base_for_monthly += past_slice['Net_Profit'].sum()
                            df_monthly_filtered = df_monthly_filtered[df_monthly_filtered['Date_Close'] >= start_date]
                        elif monthly_view_range == "1 ปีล่าสุด (YTD / 12M)":
                            start_date = max_date - pd.DateOffset(years=1)
                            past_slice = df_monthly_filtered[df_monthly_filtered['Date_Close'] < start_date]
                            capital_base_for_monthly += past_slice['Net_Profit'].sum()
                            df_monthly_filtered = df_monthly_filtered[df_monthly_filtered['Date_Close'] >= start_date]
                    
                        if not df_monthly_filtered.empty:
                            # 2. จัดเตรียมและคำนวณค่าต่างๆ ตามข้อมูลที่ถูกกรอง
                            monthly_perf = df_monthly_filtered.groupby(df_monthly_filtered['Date_Close'].dt.to_period('M'))['Net_Profit'].sum().reset_index()
                            monthly_perf['Month'] = monthly_perf['Date_Close'].dt.strftime('%Y-%m')
                            
                            # คำนวณค่าสถิติต่างๆ ต่อเนื่อง
                            monthly_perf['Cumulative_Profit'] = monthly_perf['Net_Profit'].cumsum()
                            monthly_perf['Portfolio_Value'] = capital_base_for_monthly + monthly_perf['Cumulative_Profit']
                            monthly_perf['Monthly_Return_Pct'] = (monthly_perf['Net_Profit'] / capital_base_for_monthly) * 100
                            monthly_perf['Cumulative_Pct'] = (monthly_perf['Cumulative_Profit'] / capital_base_for_monthly) * 100
                            
                            # 3. คำนวณสเกลแกน Y ให้เผื่อ Gap ทั้งบนและล่าง (ป้องกันแท่งกราฟชนขอบ)
                            y1_min = monthly_perf['Net_Profit'].min()
                            y1_max = monthly_perf['Net_Profit'].max()
                            # เผื่อสเกลแกน Y ฝั่งซ้าย (Net Profit) ขึ้น/ลง 20%
                            y1_padding = (y1_max - y1_min) * 0.2 if y1_max != y1_min else abs(y1_max) * 0.2
                            if y1_padding == 0: y1_padding = 1000
                            y1_range = [min(0, y1_min) - y1_padding, y1_max + y1_padding]
                    
                            y2_min = monthly_perf['Cumulative_Pct'].min()
                            y2_max = monthly_perf['Cumulative_Pct'].max()
                            # เผื่อสเกลแกน Y ฝั่งขวา (% สะสม) ขึ้น/ลง 20%
                            y2_padding = (y2_max - y2_min) * 0.2 if y2_max != y2_min else abs(y2_max) * 0.2
                            if y2_padding == 0: y2_padding = 5
                            y2_range = [min(0, y2_min) - y2_padding, y2_max + y2_padding]
                    
                            # 4. วาดกราฟ Plotly Combo
                            bar_colors = ['#26A69A' if val >= 0 else '#EF5350' for val in monthly_perf['Net_Profit']]
                            fig = make_subplots(specs=[[{"secondary_y": True}]])
                            
                            fig.add_trace(go.Bar(x=monthly_perf['Month'], y=monthly_perf['Net_Profit'], name="กำไร/ขาดทุน", marker_color=bar_colors), secondary_y=False)
                            fig.add_trace(go.Scatter(x=monthly_perf['Month'], y=monthly_perf['Cumulative_Pct'], name="% สะสม", mode='lines+markers', line=dict(color='#FFA500', width=3)), secondary_y=True)
                            
                            fig.update_layout(
                                title_text=f"Monthly Performance ({monthly_view_range})", 
                                height=400, 
                                margin=dict(l=20, r=20, t=40, b=20), 
                                showlegend=True
                            )
                            
                            # กำหนดช่วงสเกลแกน Y ทั้งสองฝั่งให้มีระยะห่าง (Gap)
                            fig.update_yaxes(title_text="กำไร/ขาดทุน (บาท)", range=y1_range, secondary_y=False)
                            fig.update_yaxes(title_text="% สะสม", range=y2_range, secondary_y=True)
                    
                            st.plotly_chart(fig, use_container_width=True)
                            
                            # 5. สร้างตารางสรุป
                            def color_negative_red(val):
                                if isinstance(val, (int, float)):
                                    color = '#26A69A' if val > 0 else '#EF5350' if val < 0 else 'black'
                                    return f'color: {color}'
                                return None
                    
                            monthly_df = monthly_perf[['Month', 'Net_Profit', 'Monthly_Return_Pct', 'Portfolio_Value', 'Cumulative_Pct']]
                            monthly_df.columns = ['เดือน', 'กำไร/ขาดทุน (บาท)', '% รายเดือน', 'มูลค่าพอร์ต (บาท)', '% สะสม']
                    
                            # --- CSS สำหรับจัดตารางให้ชิดขวา ---
                            styled_df = monthly_df.style.format({
                                'กำไร/ขาดทุน (บาท)': '{:,.2f}',
                                '% รายเดือน': '{:+.2f} %', 
                                'มูลค่าพอร์ต (บาท)': '{:,.2f}',
                                '% สะสม': '{:+.2f} %'
                            }) \
                            .map(color_negative_red, subset=['กำไร/ขาดทุน (บาท)', '% รายเดือน', '% สะสม']) \
                            .set_properties(**{'text-align': 'right'}) \
                            .set_table_styles([
                                {'selector': 'th', 'props': [('text-align', 'right')]},
                                {'selector': 'td', 'props': [('text-align', 'right')]}
                            ])
                    
                            # แสดงตารางผ่าน styled_df
                            st.dataframe(styled_df, use_container_width=True)
                        else:
                            st.warning("ไม่มีข้อมูลรายการเทรดในช่วงเวลาที่เลือกครับ")
                    else:
                        st.warning("ยังไม่มีข้อมูลรายการเทรดที่ปิดสถานะแล้วครับ")
            
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

            # 1. ใช้ @st.cache_data เพื่อดึงข้อมูลทุกชีตรวมกันครั้งเดียวและเก็บไว้ 10 นาที (ลดจำนวน Request มหาศาล)
            # 🔧 แก้บั๊ก: เดิมฟังก์ชันนี้ดึงข้อมูล 9 ชีตพร้อมกันแล้ว Cache รวมเป็นก้อนเดียว 10 นาที
            # ถ้าชีตใดชีตหนึ่งโหลดพลาดแค่ชีตเดียว ระบบจะจำเป็นค่าว่างของ "ทั้ง 9 ชีต" รวมกันไปเลย 10 นาที
            # (และ Cache นี้ใช้ร่วมกันทุกคนที่เปิดแอป ไม่ใช่แค่เครื่องคุณ) ทำให้ข้อมูลหายไปเป็นช่วงๆ โดยไม่ทราบสาเหตุ
            # ตอนนี้แยก Cache เป็นรายชีต ถ้าชีตไหนพลาด จะลองใหม่แค่ชีตนั้นในรอบถัดไป ไม่กระทบชีตอื่นที่โหลดสำเร็จแล้ว
            @st.cache_data(ttl=600, show_spinner=False)
            def _fetch_ws_records_safe(ws_name, max_retries=3):
                client = get_gsheet_client()
                last_error = None
                for i in range(max_retries):
                    try:
                        sheet = get_cached_spreadsheet(client, 'MyStockData').worksheet(ws_name)
                        return sheet.get_all_records()
                    except Exception as e:
                        last_error = str(e)
                        time.sleep(1 + i)  # หน่วงเวลาก่อนลองใหม่ (Exponential Backoff)
                raise RuntimeError(last_error or f"โหลดชีต {ws_name} ไม่สำเร็จ")

            def fetch_all_wealth_overview_data():
                def get_ws_records_safe(ws_name):
                    try:
                        return _fetch_ws_records_safe(ws_name)
                    except Exception:
                        return []
        
                return {
                    "pvd": get_ws_records_safe('Provident_Fund'),
                    "insurance": get_ws_records_safe('Insurance'),
                    "coop": get_ws_records_safe('Coop'),
                    "bank": get_ws_records_safe('Bank_Account'),
                    "sso": get_ws_records_safe('SSO'),
                    "pension": get_ws_records_safe('Pension'),
                    "mutual_fund": get_ws_records_safe('Fund_History'),
                    "real_estate": get_ws_records_safe('Real_Estate'),
                    "portfolio_hist": get_ws_records_safe('Stock_TFEX_History')
                }
        
            # เรียกใช้งานข้อมูลทั้งหมดรอบเดียวจบ
            all_data = fetch_all_wealth_overview_data()
        
            # --- 2. ดึงและคำนวณมูลค่าสินทรัพย์แต่ละส่วนจาก Cache ---
            
            # PVD (สมมติดึงแถวสุดท้ายของ Provident_Fund)
            pvd_value = 0.0
            if all_data["pvd"]:
                last_pvd = all_data["pvd"][-1]
                raw_pvd = last_pvd.get('Grand_Total', last_pvd.get('Value', 0))
                pvd_value = float(str(raw_pvd).replace(',', '')) if str(raw_pvd).strip() != "" else 0.0
        
            # ประกัน Unit Linked
            insurance_value = 0.0
            if all_data["insurance"]:
                last_ins = all_data["insurance"][-1]
                raw_ins = last_ins.get('Redemption_Value', last_ins.get('Value', 0))
                insurance_value = float(str(raw_ins).replace(',', '')) if str(raw_ins).strip() != "" else 0.0
        
            # สหกรณ์
            coop_value = 0.0
            if all_data["coop"]:
                last_coop = all_data["coop"][-1]
                raw_coop = last_coop.get('Coop_Value', last_coop.get('Value', 0))
                coop_value = float(str(raw_coop).replace(',', '')) if str(raw_coop).strip() != "" else 0.0
        
            # กองทุนรวม (Fund_History)
            mutual_fund_value = 0.0
            if all_data["mutual_fund"]:
                last_mf = all_data["mutual_fund"][-1]
                raw_mf = last_mf.get('Value', last_mf.get('Market_Value', last_mf.get('มูลค่าตลาด', 0)))
                mutual_fund_value = float(str(raw_mf).replace(',', '')) if str(raw_mf).strip() != "" else 0.0
        
            # ทองคำ (จาก session_state)
            total_gold_value = st.session_state.get('total_gold_portfolio_value', 0.0)
            
            # ประกันสังคม
            sso_value = 0.0
            if all_data["sso"]:
                raw_sso = all_data["sso"][-1].get('Value', 0)
                sso_value = float(str(raw_sso).replace(',', '')) if str(raw_sso).strip() != "" else 0.0
            
            # ประกันบำนาญ (รวมทุกอายุ)
            pension_insurance_value = 0.0
            if all_data["pension"]:
                for row in all_data["pension"]:
                    val_raw = row.get('Value', 0)
                    
                    # แปลงค่าให้เป็นตัวเลขที่สะอาดขึ้น
                    if val_raw:
                        # 1. แปลงเป็นสตริง, 2. ลบเครื่องหมายจุลภาค, 3. ลบสัญลักษณ์เงิน, 4. ลบการเว้นวรรค
                        val_str = str(val_raw).replace(',', '').replace('฿', '').replace('THB', '').strip()
                        
                        # ตรวจสอบว่าเป็นตัวเลขหรือไม่ก่อนแปลง
                        try:
                            val_clean = float(val_str)
                            pension_insurance_value += val_clean
                        except ValueError:
                            # ถ้าแปลงไม่ได้ (เช่นเป็นคำว่า "ไม่มี" หรือว่างเปล่า) ให้ข้ามไป
                            continue
                    
            pension_insurance_value = float(pension_insurance_value)
            
            # บัญชีธนาคาร
            bank_balance = 0.0
            if all_data["bank"]:
                raw_bank = all_data["bank"][-1].get('Balance', 0)
                bank_balance = float(str(raw_bank).replace(',', '')) if str(raw_bank).strip() != "" else 0.0
        
            # อสังหาริมทรัพย์
            house1_value = 0.0  
            house2_value = 0.0  
            condo_value = 0.0   
            
            real_estate_items = st.session_state.get('real_estate_portfolio', [])
            if not real_estate_items:
                real_estate_items = all_data["real_estate"]
        
            for item in real_estate_items:
                name = str(item.get("ชื่อทรัพย์สิน", "")).lower()
                note = str(item.get("หมายเหตุ", "")).lower()
                
                m_val = item.get("มูลค่าตลาด (บาท)", item.get("มูลค่าตลาด", 0))
                market_val = float(str(m_val).replace(',', '')) if str(m_val).strip() != "" else 0.0
                
                d_val = item.get("ยอดหนี้คงเหลือ (บาท)", item.get("ยอดหนี้คงเหลือ", 0))
                debt_val = float(str(d_val).replace(',', '')) if str(d_val).strip() != "" else 0.0
                
                net_val = market_val - debt_val
                
                if "condo" in name or "คอนโด" in name or "ดีคอนโด" in name:
                    condo_value += net_val
                elif "พ่อแม่" in note or "พ่อแม่" in name:
                    house2_value += net_val
                else:
                    house1_value += net_val
            
            total_real_estate = house1_value + house2_value + condo_value
            
            # พอร์ตหุ้นรวม + พอร์ต TFEX
            base_stock_value = total_value if 'total_value' in locals() else 0.0
            tfex_portfolio_value = st.session_state.get('tfex_net_worth', 0.0)
            total_stock_and_tfex = base_stock_value + tfex_portfolio_value
            
            # คำนวณ Net Worth
            net_worth_excl_re = (total_stock_and_tfex + pvd_value + insurance_value + 
                                 coop_value + sso_value + pension_insurance_value + 
                                 bank_balance + total_gold_value + mutual_fund_value)
            net_worth_total = net_worth_excl_re + total_real_estate
            
            # --- 3. แสดงผล Net Worth ทั้งสองแบบ ---
            with st.container(border=True):
                col_nw1, col_nw2 = st.columns(2)
            
                with col_nw1:
                    st.markdown(
                        f"""
                        <div style="text-align: left; padding: 5px;">
                            <h4 style="color: #28a745; margin-bottom: 0px;">Net Worth (ไม่รวมอสังหาฯ)</h4>
                            <h1 style="color: #28a745; font-size: 2.3em; margin-top: 5px;">{net_worth_excl_re:,.0f} ฿</h1>
                        </div>
                        """, unsafe_allow_html=True
                    )
                with col_nw2:
                    st.markdown(
                        f"""
                        <div style="text-align: left; padding: 5px;">
                            <h4 style="color: #28a745; margin-bottom: 0px;">Net Worth รวมทั้งหมด</h4>
                            <h1 style="color: #28a745; font-size: 2.3em; margin-top: 5px;">{net_worth_total:,.0f} ฿</h1>
                        </div>
                        """, unsafe_allow_html=True
                    )
                        
        
            # --- 4. แสดงผลใน Metrics ย่อย ---
            with st.container(border=True):
                st.markdown("#### 💼 สินทรัพย์สภาพคล่องและการลงทุน")
                row1_col1, row1_col2, row1_col3, row1_col4 = st.columns(4)
                row1_col1.metric("พอร์ตหุ้น + TFEX", f"{total_stock_and_tfex:,.0f} ฿")
                row1_col2.metric("กองทุนรวม", f"{mutual_fund_value:,.0f} ฿")
                row1_col3.metric("กองทุนสำรองเลี้ยงชีพ", f"{pvd_value:,.0f} ฿")
                row1_col4.metric("ประกัน Unit Linked", f"{insurance_value:,.0f} ฿")
            
                row2_col1, row2_col2, row2_col3, row2_col4 = st.columns(4)
                row2_col1.metric("สหกรณ์ฯ", f"{coop_value:,.0f} ฿")
                row2_col2.metric("ประกันสังคม", f"{sso_value:,.0f} ฿")
                row2_col3.metric("บัญชีธนาคาร", f"{bank_balance:,.0f} ฿")
                row2_col4.metric("ประกันบำนาญ", f"{pension_insurance_value:,.0f} ฿")
            
                # ย้าย Note มาไว้ใน col4 ของแถวนี้ เพื่อให้อยู่ใต้ประกันบำนาญพอดี
                if all_data["pension"]:
                    pension_notes_html = '<div style="margin-top: -10px; margin-bottom: 5px;">'
                    for row in all_data["pension"]:
                        age_val = row.get('Age', '-')
                        money_val = row.get('Value', 0)
                        
                        clean_money = float(str(money_val).replace(',', '').replace('฿', '').strip() or 0)
                        
                        if clean_money > 0:
                            pension_notes_html += (
                                f'<p style="color: #888888; font-size: 0.75em; margin: 0px;">'
                                f'• ถอนออก ณ อายุ {age_val} ปี: {clean_money:,.0f} ฿'
                                f'</p>'
                            )
                    pension_notes_html += '</div>'
                    
                    # แสดงผลข้อความไว้ใต้ช่องประกันบำนาญโดยตรง
                    row2_col4.markdown(pension_notes_html, unsafe_allow_html=True)
            
                row3_col1, _, _, _ = st.columns(4)
                row3_col1.metric("พอร์ตทองคำ", f"{total_gold_value:,.0f} ฿")
                
                st.markdown("<br>", unsafe_allow_html=True)
                
                # --- 5. แสดงผลอสังหาริมทรัพย์ ---
                st.markdown("#### 🏡 อสังหาริมทรัพย์")
                row_re1, row_re2, row_re3, row_re4 = st.columns(4)
                row_re1.metric("รวมอสังหาริมทรัพย์", f"{total_real_estate:,.0f} ฿")
                row_re2.metric("บ้าน (ปัจจุบัน)", f"{house1_value:,.0f} ฿")
                row_re3.metric("บ้าน (พ่อแม่อยู่)", f"{house2_value:,.0f} ฿")
                row_re4.metric("คอนโด", f"{condo_value:,.0f} ฿")
                
            
            st.subheader("📈 วิเคราะห์สัดส่วนสินทรัพย์สภาพคล่องและการลงทุน")

            # 1. เตรียมข้อมูลสัดส่วนสินทรัพย์
            asset_data = {
                "Asset_Type": ["พอร์ตหุ้น + TFEX", "กองทุนรวม", "PVD", "ประกัน Unit Linked", "สหกรณ์ก๊าซ ปตท.", "ประกันสังคม", "บัญชีธนาคาร", "ประกันบำนาญ", "ทองคำ"],
                "Value": [total_stock_and_tfex, mutual_fund_value, pvd_value, insurance_value, coop_value, sso_value, bank_balance, pension_insurance_value, total_gold_value]
            }
            df_assets = pd.DataFrame(asset_data)
            df_assets = df_assets[df_assets["Value"] > 0]

            with st.container(border=True):
                col_chart1, col_chart2 = st.columns(2)
                
                with col_chart1:
                    st.markdown("### 🍩 สัดส่วนสินทรัพย์ปัจจุบัน")
                    if not df_assets.empty:
                        import plotly.express as px
                        fig_donut = px.pie(
                            df_assets, names="Asset_Type", values="Value", hole=0.4,
                            color_discrete_sequence=px.colors.qualitative.Pastel
                        )
                        fig_donut.update_traces(textposition='inside', textinfo='percent+label')
                        fig_donut.update_layout(margin=dict(t=10, b=10, l=10, r=10), showlegend=False)
                        st.plotly_chart(fig_donut, use_container_width=True, key="donut_main_chart")
                    else:
                        st.info("ยังไม่มีข้อมูลสำหรับแสดงกราฟโดนัท")
                
                with col_chart2:
                    st.markdown("### 📊 มูลค่าแยกตามประเภทสินทรัพย์")
                    if not df_assets.empty:
                        fig_bar = px.bar(
                            df_assets, x="Asset_Type", y="Value", text="Value",
                            color="Asset_Type", color_discrete_sequence=px.colors.qualitative.Pastel
                        )
                        fig_bar.update_traces(texttemplate='%{text:,.0f} ฿', textposition='outside')
                        fig_bar.update_layout(margin=dict(t=10, b=10, l=10, r=10), showlegend=False, xaxis_title="", yaxis_title="บาท")
                        st.plotly_chart(fig_bar, use_container_width=True, key="bar_main_chart")
                    else:
                        st.info("ยังไม่มีข้อมูลสำหรับแสดงกราฟแท่ง")
            
            # 2. กราฟแนวโน้ม Net Worth (ดึงข้อมูลใหม่แบบรวมศูนย์)
            with st.container(border=True):
                st.markdown("### 📉 กราฟแนวโน้มการเติบโตของความมั่งคั่งสุทธิ (Net Worth)")
                
                try:
                    import time
                    
                    # 🔧 แก้บั๊ก: เดิมจุดนี้มี Cache ซ้อนอีกชั้น (@st.cache_data ครอบทั้ง 7 ชีต) แยกต่างหาก
                    # จากตัวช่วย _fetch_ws_records_safe ด้านบน ทำให้เกิดปัญหาเดียวกัน คือถ้าชีตใดชีตหนึ่งพลาด
                    # กราฟทั้งหมดจะหายไป 10 นาที ตอนนี้เปลี่ยนมาใช้ _fetch_ws_records_safe ตัวเดียวกับแท็บภาพรวม
                    # ซึ่งจำผลแยกเป็นรายชีตอยู่แล้ว จึงไม่ต้อง Cache ซ้อนอีกชั้น
                    def fetch_all_wealth_data():
                        def get_df_safe(ws_name):
                            try:
                                return pd.DataFrame(_fetch_ws_records_safe(ws_name))
                            except Exception:
                                return pd.DataFrame()
                        
                        return (get_df_safe('Provident_Fund'), get_df_safe('Insurance'), 
                                get_df_safe('Coop'), get_df_safe('Bank_Account'), 
                                get_df_safe('SSO'), get_df_safe('Fund_History'), 
                                get_df_safe('Stock_TFEX_History'))
                
                    df_pvd, df_ins, df_coop, df_bank, df_sso, df_mf, df_portfolio_hist = fetch_all_wealth_data()
                            
                    def prepare_series(df, date_col, val_col, name):
                        df = df.copy()
                        if df.empty: return pd.DataFrame(columns=[name], index=pd.to_datetime([]))
                        if date_col == 'Month':
                            thai_months = {'มกราคม': '01', 'กุมภาพันธ์': '02', 'มีนาคม': '03', 'เมษายน': '04', 'พฤษภาคม': '05', 'มิถุนายน': '06', 'กรกฎาคม': '07', 'สิงหาคม': '08', 'กันยายน': '09', 'ตุลาคม': '10', 'พฤศจิกายน': '11', 'ธันวาคม': '12'}
                            df['Month_Num'] = df[date_col].map(thai_months).fillna('12')
                            df['Date'] = pd.to_datetime(df['Year_CE'].astype(str) + '-' + df['Month_Num'] + '-01', errors='coerce')
                        else:
                            df['Date'] = pd.to_datetime(df[date_col], errors='coerce')
                        df[name] = df[val_col].astype(str).str.replace(',', '').astype(float)
                        return df.dropna(subset=['Date']).set_index('Date')[[name]]
                
                    s_pvd = prepare_series(df_pvd, 'Month', 'Grand_Total', 'PVD')
                    s_ins = prepare_series(df_ins, 'Date', 'Redemption_Value', 'Insurance')
                    s_sso = prepare_series(df_sso, 'Date', 'Value', 'SSO')
                    s_coop = prepare_series(df_coop, 'Date', 'Coop_Value', 'Coop')
                    s_bank = prepare_series(df_bank, 'Date', 'Balance', 'Bank')
                    s_mf = prepare_series(df_mf, 'Date', 'Value', 'Mutual_Fund')
                    s_port = prepare_series(df_portfolio_hist, 'Date', 'Total_Value', 'Stock+TFEX')
                
                    if not s_ins.empty and not s_sso.empty:
                        s_ins = s_ins.join(s_sso, how='outer').sort_index().ffill().fillna(0)
                        s_ins['Insurance'] = s_ins['Insurance'] + s_ins['SSO']
                        s_ins = s_ins[['Insurance']]
                    elif s_ins.empty and not s_sso.empty:
                        s_ins = s_sso.rename(columns={'SSO': 'Insurance'})
                
                    series_list = [s for s in [s_pvd, s_ins, s_coop, s_bank, s_mf, s_port] if not s.empty]
                    
                    if series_list:
                        df_merged = series_list[0]
                        for s in series_list[1:]: df_merged = df_merged.join(s, how='outer')
                        df_merged = df_merged.sort_index().ffill().fillna(0)
                        df_merged['Total'] = df_merged.sum(axis=1)
                
                        import plotly.graph_objects as go
                        fig = go.Figure()
                        for col in df_merged.columns:
                            fig.add_trace(go.Scatter(x=df_merged.index, y=df_merged[col], name=col, mode='lines+markers', line=dict(width=3 if col == 'Total' else 2)))
                        
                        fig.update_layout(yaxis=dict(range=[0, (df_merged['Total'].max() * 1.2) if df_merged['Total'].max() > 0 else 12000000], tickformat=",.0f"),
                                          legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                        
                        st.plotly_chart(fig, use_container_width=True, key="net_worth_trend_chart_final")
                    else:
                        st.info("💡 ยังไม่มีข้อมูลเพียงพอสำหรับแสดงกราฟแนวโน้ม")
                except Exception as e:
                    st.error(f"เกิดข้อผิดพลาดในการดึงข้อมูลกราฟ: {e}")

        # --- ส่วน UI สำหรับจัดการกองทุน (นำไปวางในหน้า App ของคุณ) ---
        
        # 1. Tab ซื้อกองทุนใหม่
        with wealth_tab_funds:
            render_tab_funds()
        
        # ==========================================
        # TAB ย่อยที่ 2: บันทึกข้อมูล (PVD / สหกรณ์ / ประกัน)
        # ==========================================
        with wealth_tab_form_general:
            st.markdown("### 📝 บันทึกและอัปเดตข้อมูลสินทรัพย์ระยะยาว")
            
            # --- 1. ส่วน PVD (รวมฟอร์มและตารางสรุปไว้ใน Expander เดียวกัน) ---
            with st.expander("📤 เพิ่ม/อัปเดตข้อมูลกองทุนสำรองเลี้ยงชีพ (PVD) รายเดือน", expanded=False):
                with st.form("pvd_upload_form"):
                    col_y1, col_y2, col_m = st.columns(3)
                    
                    with col_y1:
                        input_year_be = st.number_input("ปี พ.ศ.", min_value=2500, max_value=2570, value=2569)
                    with col_y2:
                        st.info(f"ค.ศ.: **{int(input_year_be) - 543}**")
                    with col_m:
                        months_list = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", 
                                       "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
                        selected_month = st.selectbox("เลือกเดือน", months_list)
                        
                    uploaded_pvd_file = st.file_uploader("อัปโหลดรูปภาพรายงาน PVD รายเดือน (JPG, PNG)", type=["jpg", "jpeg", "png"])
                    
                    submitted_pvd = st.form_submit_button("🔍 อ่านข้อมูลจากรูปภาพด้วย AI")
                    
                    if submitted_pvd:
                        if uploaded_pvd_file is not None:
                            with st.spinner("กำลังให้ AI อ่านและวิเคราะห์ข้อมูลจากภาพ..."):
                                df_extracted = extract_pvd_from_image(uploaded_pvd_file, input_year_be, selected_month)
                                
                                if df_extracted is not None and not df_extracted.empty:
                                    if 'Month' not in df_extracted.columns:
                                        df_extracted.insert(0, 'Month', selected_month)
                                    
                                    st.success("อ่านข้อมูลสำเร็จ! ตรวจสอบความถูกต้องด้านล่าง:")
                                    st.dataframe(df_extracted, use_container_width=True)
                                    
                                    st.session_state['temp_pvd_df'] = df_extracted
                                else:
                                    st.warning("ไม่สามารถดึงข้อมูลจากรูปภาพได้ กรุณาลองใหม่อีกครั้ง")
                        else:
                            st.warning("กรุณาอัปโหลดรูปภาพก่อนกดปุ่มประมวลผล")
                
                # ส่วนยืนยันบันทึกข้อมูล (อยู่นอกฟอร์มหลัก แต่ยังอยู่ใน Expander)
                if 'temp_pvd_df' in st.session_state and st.session_state['temp_pvd_df'] is not None:
                    st.write("---")
                    st.write("📋 **ข้อมูลที่พร้อมบันทึก:**")
                    st.dataframe(st.session_state['temp_pvd_df'], use_container_width=True)
                    
                    if st.button("💾 ยืนยันบันทึกข้อมูลนี้ลง Google Sheets", key="confirm_pvd_save"):
                        try:
                            client = get_gsheet_client()
                            sheet = get_cached_spreadsheet(client, 'MyStockData').worksheet('Provident_Fund')
                            
                            existing_data = sheet.get_all_records()
                            df_existing = pd.DataFrame(existing_data) if existing_data else pd.DataFrame()
                            
                            df_to_save = st.session_state['temp_pvd_df'].fillna(0)
                            
                            is_duplicate = False
                            if not df_existing.empty and 'Month' in df_existing.columns and 'Year_BE' in df_existing.columns:
                                match_idx = df_existing[
                                    (df_existing['Year_BE'].astype(str) == str(input_year_be)) & 
                                    (df_existing['Month'] == selected_month)
                                ].index
                                
                                if len(match_idx) > 0:
                                    is_duplicate = True
                                    row_number_to_update = match_idx[0] + 2 
                                    
                                    values_to_write = list(df_to_save.iloc[0].values)
                                    sheet.update(f"A{row_number_to_update}", [values_to_write])
                                    st.success(f"✅ อัปเดตข้อมูลของ **{selected_month} พ.ศ. {input_year_be}** เรียบร้อยแล้ว")
                            
                            if not is_duplicate:
                                for row in df_to_save.values.tolist():
                                    sheet.append_row(row)
                                st.success(f"✅ บันทึกข้อมูลใหม่ของ **{selected_month} พ.ศ. {input_year_be}** เรียบร้อยแล้ว!")
                            
                            del st.session_state['temp_pvd_df']
                            
                            # 👇 --- แทรกตรงนี้ครับ เพื่อรอให้ Google Sheets บันทึกข้อมูลเสร็จและเคลียร์แคชก่อนรีรัน ---
                            import time
                            time.sleep(1.5)
                            st.cache_data.clear()
                            # --------------------------------------------------------------------------------
                            
                            st.rerun()
                            
                        except Exception as e:
                            if "429" in str(e) or "Quota exceeded" in str(e):
                                st.error("❌ Google Sheets API เกินโควตาชั่วคราว (Rate Limit 429) กรุณารอสัก 30 วินาที แล้วลองกดบันทึกใหม่อีกครั้งครับ")
                            else:
                                st.error(f"❌ เกิดข้อผิดพลาดในการบันทึก: {e}")
            
                # --- 1. ดึงข้อมูลจาก Google Sheets มาเตรียมไว้ก่อน ---
                df_pvd_history = pd.DataFrame()
                try:
                    client = get_gsheet_client()
                    sheet_pvd = get_cached_spreadsheet(client, 'MyStockData').worksheet('Provident_Fund')
                    pvd_records = sheet_pvd.get_all_records()
                    if pvd_records:
                        df_pvd_history = pd.DataFrame(pvd_records)
                except Exception as e:
                    pass
   
                # --- ส่วนแสดงกราฟแท่ง % ผลตอบแทน (% Benefit) คำนวณอัตโนมัติจากข้อมูลที่มี ---
                st.markdown("---")
                st.subheader("📊 กราฟแสดง % ผลตอบแทนรายบุคคล (YTD Net Return %)")
                
                if not df_pvd_history.empty:
                    try:
                        def clean_num(series):
                            if series is None:
                                return pd.Series(0.0, index=df_pvd_history.index)
                            return pd.to_numeric(
                                series.astype(str)
                                .str.replace(',', '', regex=False)
                                .str.replace(' ', '', regex=False)
                                .str.replace('%', '', regex=False),
                                errors='coerce'
                            ).fillna(0.0)
            
                        # ดึงข้อมูลจากคอลัมน์ YTD_Net_Return_Pct โดยตรง
                        if 'YTD_Net_Return_Pct' in df_pvd_history.columns:
                            chart_col = 'YTD_Net_Return_Pct'
                            df_pvd_history[chart_col] = clean_num(df_pvd_history[chart_col])
                        else:
                            # เผื่อกรณียังไม่มีคอลัมน์นี้ในชีต ให้สร้างเป็น 0 ไปก่อนเพื่อกัน error
                            df_pvd_history['YTD_Net_Return_Pct'] = 0.0
                            chart_col = 'YTD_Net_Return_Pct'
                            
                    except Exception as e:
                        st.warning(f"⚠️ เกิดข้อผิดพลาดในการอ่านข้อมูลกราฟ: {e}")
                        chart_col = None
                        
                    if chart_col and chart_col in df_pvd_history.columns:
                        if 'Month' in df_pvd_history.columns and 'Year_BE' in df_pvd_history.columns:
                            # 🔧 แก้บั๊ก: เรียงลำดับข้อมูลตามปี พ.ศ. และเดือนจริงๆ ก่อนสร้างกราฟ
                            # (เดิมกราฟแสดงตามลำดับแถวที่กรอกใน Google Sheets ทำให้เดือนสลับกัน)
                            thai_month_order = {
                                "มกราคม": 1, "กุมภาพันธ์": 2, "มีนาคม": 3, "เมษายน": 4,
                                "พฤษภาคม": 5, "มิถุนายน": 6, "กรกฎาคม": 7, "สิงหาคม": 8,
                                "กันยายน": 9, "ตุลาคม": 10, "พฤศจิกายน": 11, "ธันวาคม": 12
                            }
                            df_pvd_sorted = df_pvd_history.copy()
                            df_pvd_sorted['_Month_Num'] = df_pvd_sorted['Month'].map(thai_month_order).fillna(0).astype(int)
                            df_pvd_sorted['_Year_Num'] = pd.to_numeric(df_pvd_sorted['Year_BE'], errors='coerce').fillna(0).astype(int)
                            df_pvd_sorted = df_pvd_sorted.sort_values(by=['_Year_Num', '_Month_Num'])
                            
                            df_pvd_sorted['Period'] = df_pvd_sorted['Month'].astype(str) + " " + df_pvd_sorted['Year_BE'].astype(str)
                            chart_data = df_pvd_sorted.set_index('Period')[chart_col]
                        else:
                            chart_data = df_pvd_history[chart_col]
                        
                        chart_data = pd.to_numeric(chart_data, errors='coerce').fillna(0.0)
                        
                        # แสดงกราฟแท่ง (เปลี่ยนมาใช้ Plotly เพื่อกำหนดสีแยกตามค่าบวก/ลบได้)
                        # 🎨 บวก = เขียว, ลบ = แดง
                        bar_colors = ['#2ECC71' if v >= 0 else '#E74C3C' for v in chart_data]
                        fig_pvd = go.Figure(data=[
                            go.Bar(
                                x=chart_data.index.tolist(),
                                y=chart_data.values.tolist(),
                                marker_color=bar_colors
                            )
                        ])
                        fig_pvd.update_layout(
                            height=400,
                            margin=dict(l=20, r=20, t=20, b=20),
                            yaxis_title="YTD Net Return (%)"
                        )
                        st.plotly_chart(fig_pvd, use_container_width=True)
                    else:
                        st.info("💡 ไม่สามารถสร้างกราฟได้ เนื่องจากข้อมูลคอลัมน์ไม่เพียงพอ")
                else:
                    st.info("💡 ยังไม่มีข้อมูลสำหรับแสดงกราฟ กรุณาอัปโหลดข้อมูลก่อนครับ")
            
                # --- 3. ส่วนแสดงตารางสรุปการเติบโต ---
                st.markdown("---")
                st.subheader("📈 ตารางสรุปการเติบโตและผลตอบแทนกองทุน PVD")
                if not df_pvd_history.empty:
                    if 'Year_BE' in df_pvd_history.columns:
                        df_pvd_history['Year_BE'] = pd.to_numeric(df_pvd_history['Year_BE'], errors='coerce')
                    st.dataframe(df_pvd_history, use_container_width=True, hide_index=True)
                else:
                    st.info("ยังไม่มีข้อมูลประวัติในชีต Provident_Fund")

            # --- 2. ส่วนประกันภัย Unit Linked ---
            with st.expander("📤 เพิ่ม/อัปเดตข้อมูลประกันควบการลงทุน (Unit Linked)", expanded=False):
                with st.form("insurance_upload_form"):
                    col_d, col_v = st.columns(2)
                    
                    with col_d:
                        ins_date = st.date_input("เลือกวันที่อัปเดตข้อมูล", value=date.today(), key="ins_date_input")
                        
                    with col_v:
                        ins_redemption_value = st.number_input(
                            "มูลค่ารับซื้อคืนหน่วยลงทุน (บาท)", 
                            min_value=0.0, 
                            format="%.2f", 
                            value=0.0,
                            key="ins_redemption_input",
                            help="กรอกยอดมูลค่าพอร์ตประกันตามใบแจ้งยอดหรือแอปพลิเคชัน ณ วันที่อัปเดต"
                        )
                    
                    submitted_ins = st.form_submit_button("💾 บันทึก/อัปเดตข้อมูลประกันภัย")
                    
                    if submitted_ins:
                        if ins_redemption_value > 0:
                            try:
                                client = get_gsheet_client()
                                sheet_ins = get_cached_spreadsheet(client, 'MyStockData').worksheet('Insurance')
                                
                                existing_data = sheet_ins.get_all_records()
                                df_existing_ins = pd.DataFrame(existing_data) if existing_data else pd.DataFrame()
                                
                                date_str = ins_date.strftime("%Y-%m-%d")
                                year_ce = ins_date.year
                                
                                is_duplicate = False
                                
                                if not df_existing_ins.empty and 'Date' in df_existing_ins.columns:
                                    match_idx = df_existing_ins[df_existing_ins['Date'].astype(str) == date_str].index
                                    
                                    if len(match_idx) > 0:
                                        is_duplicate = True
                                        row_num = match_idx[0] + 2 
                                        
                                        updated_values = [date_str, year_ce, ins_redemption_value]
                                        sheet_ins.update(f"A{row_num}:C{row_num}", [updated_values])
                                        st.success(f"✅ อัปเดตมูลค่าประกันของวันที่ **{date_str}** เป็น **{ins_redemption_value:,.2f} บาท** เรียบร้อยแล้ว!")
                                
                                if not is_duplicate:
                                    new_row = [date_str, year_ce, ins_redemption_value]
                                    sheet_ins.append_row(new_row)
                                    st.success(f"✅ บันทึกข้อมูลใหม่ของวันที่ **{date_str}** เรียบร้อยแล้ว!")
                                    
                                st.rerun()
                                
                            except Exception as e:
                                st.error(f"❌ เกิดข้อผิดพลาดในการบันทึกข้อมูลประกัน: {e}")
                        else:
                            st.warning("กรุณากรอกมูลค่ารับซื้อคืนหน่วยลงทุนให้มากกว่า 0")

            # --- 3. ส่วนสหกรณ์ก๊าซ ปตท. (พร้อมระบบ Auto เพิ่มเงินทุกสิ้นเดือน) ---
            def get_coop_sheet():
                client = get_gsheet_client()
                return get_cached_spreadsheet(client, 'MyStockData').worksheet('Coop')
            
            def get_sso_sheet():
                client = get_gsheet_client()
                return get_cached_spreadsheet(client, 'MyStockData').worksheet('SSO')
            
            def get_bank_sheet():
                client = get_gsheet_client()
                return get_cached_spreadsheet(client, 'MyStockData').worksheet('Bank_Account')
            
            # --- ฟังก์ชันคำนวณยอดอัติโนมัติสะสมตามเดือนที่ผ่านไป ---
            def calculate_auto_coop_value(last_date_str, last_val, monthly_add, is_auto_active):
                if not is_auto_active or monthly_add <= 0:
                    return last_val, last_date_str
                
                try:
                    last_dt = datetime.strptime(last_date_str, "%Y-%m-%d").date()
                    today_dt = date.today()
                    
                    # ตรวจสอบว่าข้ามเดือนมาแล้วหรือไม่ (เทียบสิ้นเดือน)
                    # คำนวณจำนวนเดือนที่ห่างกัน
                    diff_months = (today_dt.year - last_dt.year) * 12 + (today_dt.month - last_dt.month)
                    
                    # หากผ่านไปอย่างน้อย 1 เดือนเต็ม และวันนี้เลยวันที่บันทึกล่าสุดมาแล้ว
                    if diff_months > 0:
                        # คำนวณยอดเงินที่ควรเพิ่มขึ้นตามจำนวนเดือนที่ผ่านไป
                        updated_val = last_val + (diff_months * monthly_add)
                        updated_date_str = today_dt.strftime("%Y-%m-%d")
                        return updated_val, updated_date_str
                except Exception:
                    pass
                    
                return last_val, last_date_str
    
            with st.expander("📤 เพิ่ม/อัปเดตข้อมูลสหกรณ์ก๊าซ ปตท.", expanded=False):
                # ดึงข้อมูลล่าสุดจาก Sheet เพื่อมาแสดงค่าตั้งต้น
                latest_coop_val = 0.0
                latest_coop_date = date.today().strftime("%Y-%m-%d")
                try:
                    sheet_coop = get_coop_sheet()
                    coop_records = sheet_coop.get_all_records()
                    if coop_records:
                        last_row = coop_records[-1]
                        latest_coop_date = str(last_row.get('Date', date.today().strftime("%Y-%m-%d")))
                        latest_coop_val = float(str(last_row.get('Value', 0)).replace(',', ''))
                except Exception:
                    pass
    
                # ตั้งค่าสถานะ Auto ใน session_state (ค่าเริ่มต้น: เปิดใช้งาน, เติมเดือนละ 10,000)
                if 'coop_auto_active' not in st.session_state:
                    st.session_state['coop_auto_active'] = True
                if 'coop_monthly_amount' not in st.session_state:
                    st.session_state['coop_monthly_amount'] = 10000.0
    
                # ตรวจสอบและบวกยอดอัตโนมัติหากผ่านพ้นสิ้นเดือน
                calculated_val, calculated_date = calculate_auto_coop_value(
                    latest_coop_date, 
                    latest_coop_val, 
                    st.session_state['coop_monthly_amount'], 
                    st.session_state['coop_auto_active']
                )
    
                with st.form("coop_upload_form"):
                    st.markdown("##### ⚙️ ตั้งค่าระบบเติมเงินอัตโนมัติ (Auto Save)")
                    col_cfg1, col_cfg2 = st.columns(2)
                    with col_cfg1:
                        auto_active_input = st.checkbox("เปิดใช้งาน Auto เติมเงินทุกสิ้นเดือน", value=st.session_state['coop_auto_active'], key="form_coop_auto_chk")
                    with col_cfg2:
                        monthly_amount_input = st.number_input("ยอดเติมอัตโนมัติ (บาท/เดือน)", min_value=0.0, step=1000.0, value=float(st.session_state['coop_monthly_amount']), key="form_coop_monthly_val")
                    
                    st.markdown("---")
                    col_d, col_v = st.columns(2)
                    with col_d:
                        coop_date = st.date_input("เลือกวันที่อัปเดตข้อมูลสหกรณ์", value=datetime.strptime(calculated_date, "%Y-%m-%d").date() if calculated_date else date.today(), key="coop_date_input")
                    with col_v:
                        coop_value = st.number_input(
                            "ยอดเงินสหกรณ์ / มูลค่าหุ้นสหกรณ์ (บาท)", 
                            min_value=0.0, format="%.2f", value=float(calculated_val), key="coop_value_input",
                            help="ระบบจะคำนวณบวกยอด Auto ให้ หรือคุณสามารถพิมพ์แก้ไขยอดสุทธิใหม่ได้เองตามต้องการ"
                        )
                    
                    submitted_coop = st.form_submit_button("💾 บันทึก/อัปเดตข้อมูลสหกรณ์")
                    
                    if submitted_coop:
                        if coop_value > 0:
                            try:
                                # บันทึกสถานะ Auto ลง session_state
                                st.session_state['coop_auto_active'] = auto_active_input
                                st.session_state['coop_monthly_amount'] = monthly_amount_input
                                
                                sheet_coop = get_coop_sheet()
                                date_str = coop_date.strftime("%Y-%m-%d")
                                year_ce = coop_date.year
                                
                                date_column = sheet_coop.col_values(1) # สมมติคอลัมน์ A คือ Date
                                
                                if date_str in date_column:
                                    row_num = date_column.index(date_str) + 1
                                    sheet_coop.update(f"A{row_num}:C{row_num}", [[date_str, year_ce, coop_value]])
                                    st.success(f"✅ อัปเดตข้อมูลสหกรณ์ของวันที่ **{date_str}** เป็นยอด **{coop_value:,.2f} บาท** เรียบร้อยแล้ว!")
                                else:
                                    sheet_coop.append_row([date_str, year_ce, coop_value])
                                    st.success(f"✅ บันทึกข้อมูลใหม่สหกรณ์ของวันที่ **{date_str}** ยอด **{coop_value:,.2f} บาท** เรียบร้อยแล้ว!")
                                
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ เกิดข้อผิดพลาด (อาจติด Limit API กรุณารอสักครู่): {e}")
                        else:
                            st.warning("กรุณากรอกยอดเงินให้มากกว่า 0")
            # --- ส่วนประกันสังคม ---
            with st.expander("📤 เพิ่ม/อัปเดตข้อมูลประกันสังคม", expanded=False):
                with st.form("sso_upload_form"):
                    col_d, col_v = st.columns(2)
                    with col_d:
                        sso_date = st.date_input("เลือกวันที่อัปเดตข้อมูลประกันสังคม", value=date.today(), key="sso_date_input")
                    with col_v:
                        sso_value = st.number_input(
                            "ยอดสะสมประกันสังคม / เงินสมทบ (บาท)", 
                            min_value=0.0, format="%.2f", value=0.0, key="sso_value_input",
                            help="กรอกยอดเงินสะสมหรือเงินสมทบประกันสังคม ณ วันที่อัปเดต"
                        )
                    
                    submitted_sso = st.form_submit_button("💾 บันทึก/อัปเดตข้อมูลประกันสังคม")
                    
                    if submitted_sso:
                        if sso_value > 0:
                            try:
                                sheet_sso = get_sso_sheet()
                                date_str = sso_date.strftime("%Y-%m-%d")
                                year_ce = sso_date.year
                                
                                date_column = sheet_sso.col_values(1)
                                
                                if date_str in date_column:
                                    row_num = date_column.index(date_str) + 1
                                    sheet_sso.update(f"A{row_num}:C{row_num}", [[date_str, year_ce, sso_value]])
                                    st.success(f"✅ อัปเดตข้อมูลประกันสังคมของวันที่ **{date_str}** เรียบร้อยแล้ว!")
                                else:
                                    sheet_sso.append_row([date_str, year_ce, sso_value])
                                    st.success(f"✅ บันทึกข้อมูลใหม่ประกันสังคมของวันที่ **{date_str}** เรียบร้อยแล้ว!")
                                
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ เกิดข้อผิดพลาด (อาจติด Limit API กรุณารอสักครู่): {e}")
                        else:
                            st.warning("กรุณากรอกยอดเงินให้มากกว่า 0")
                            
            # --- ส่วนบัญชีธนาคาร (กระแสเงินสด) ---
            with st.expander("💰 บันทึก/อัปเดต บัญชีเงินฝากกระแสเงินสด", expanded=False):
                with st.form("bank_account_form"):
                    col1, col2 = st.columns(2)
                    with col1:
                        bank_date = st.date_input("วันที่", value=datetime.now(), key="bank_date_input")
                        bank_type = st.selectbox("ประเภท", ["ฝากเงิน (Deposit)", "ถอนเงิน (Withdraw)"], key="bank_type_input")
                    with col2:
                        bank_amount = st.number_input("จำนวนเงิน (บาท)", min_value=0.0, step=100.0, key="bank_amount_input")
                        bank_desc = st.text_input("หมายเหตุ", key="bank_desc_input")
                    
                    submitted_bank = st.form_submit_button("บันทึกรายการบัญชี")
                    
                    if submitted_bank:
                        try:
                            in_val = bank_amount if "ฝาก" in bank_type else 0
                            out_val = bank_amount if "ถอน" in bank_type else 0
                            
                            sheet_bank = get_bank_sheet()
                            
                            # ดึงเฉพาะคอลัมน์ Balance หรือดึงข้อมูลแถวสุดท้ายมาคำนวณเพื่อลดการโหลดข้อมูลทั้งหมด
                            all_values = sheet_bank.get_all_values()
                            last_balance = 0.0
                            
                            if len(all_values) > 1: # มี Header แล้ว
                                last_row = all_values[-1]
                                # สมมติว่าคอลัมน์ Balance อยู่ที่สุดท้าย (index -1)
                                try:
                                    last_balance = float(str(last_row[-1]).replace(',', ''))
                                except:
                                    last_balance = 0.0
                            
                            new_balance = last_balance + in_val - out_val
                            
                            sheet_bank.append_row([str(bank_date), bank_type, bank_desc, in_val, out_val, new_balance])
                            st.success("บันทึกรายการบัญชีเรียบร้อย!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ เกิดข้อผิดพลาดในการบันทึกบัญชี: {e}")
                            
            with st.expander("📤 เพิ่ม/อัปเดตข้อมูลประกันบำนาญตามอายุ", expanded=False):
                with st.form("pension_upload_form"):
                    col_p1, col_p2 = st.columns(2)
                    with col_p1:
                        pension_age = st.number_input(
                            "อายุที่เริ่มรับเงินบำนาญ (ปี)", 
                            min_value=55, max_value=100, value=55, step=1, 
                            key="pension_age_input",
                            help="ประกันบำนาญมักเริ่มถอน/รับเงินได้ตั้งแต่ช่วงอายุ 55 ปีขึ้นไป"
                        )
                    with col_p2:
                        pension_value = st.number_input(
                            "ยอดเงินบำนาญที่จะได้รับ (บาท)", 
                            min_value=0.0, format="%.2f", value=0.0, key="pension_value_input",
                            help="กรอกยอดเงินตามตารางกรมธรรม์ ณ อายุที่เลือก"
                        )
                    
                    submitted_pension = st.form_submit_button("💾 บันทึก/อัปเดตข้อมูลประกันบำนาญ")
                    
                    if submitted_pension:
                        if pension_value >= 0:
                            try:
                                # ปรับวิธีเรียกใช้งานให้รองรับฟังก์ชันกลางและป้องกัน Error
                                client = get_gsheet_client()
                                sheet_pension = get_worksheet_safely(client, 'MyStockData', 'Pension')
                                
                                if sheet_pension is None:
                                    raise Exception("ไม่สามารถเชื่อมต่อกับชีต 'Pension' ได้ กรุณาตรวจสอบชื่อชีตอีกครั้ง")
                                
                                # แปลงอายุเป็น string เพื่อใช้ตรวจสอบในคอลัมน์ A (อายุ)
                                age_str = str(int(pension_age))
                                
                                # ดึงข้อมูลในคอลัมน์ A ทั้งหมดมาเช็คว่ามีอายุนี้หรือยัง
                                age_column = [str(cell) for cell in sheet_pension.col_values(1)]
                                
                                if age_str in age_column:
                                    row_num = age_column.index(age_str) + 1
                                    # อัปเดตข้อมูลในบรรทัดเดิม (คอลัมน์ A คือ อายุ, คอลัมน์ B คือ ยอดเงิน)
                                    sheet_pension.update(f"A{row_num}:B{row_num}", [[age_str, pension_value]])
                                    st.success(f"✅ อัปเดตข้อมูลประกันบำนาญสำหรับ **อายุ {age_str} ปี** เรียบร้อยแล้ว!")
                                else:
                                    # เพิ่มบรรทัดใหม่
                                    sheet_pension.append_row([age_str, pension_value])
                                    st.success(f"✅ บันทึกข้อมูลใหม่ประกันบำนาญสำหรับ **อายุ {age_str} ปี** เรียบร้อยแล้ว!")
                                
                                time.sleep(0.5)
                                st.rerun()
                                
                            except Exception as e:
                                st.error(f"❌ เกิดข้อผิดพลาดในการบันทึก: {e}")
                        else:
                            st.warning("กรุณากรอกยอดเงินให้ถูกต้อง")
                
        ######## REAL ESTATE ########################                    
        with wealth_tab_real_estate:
            render_tab_real_estate()
# ------------------------------
if __name__ == "__main__":
    main()
