# 1. ฟังก์ชัน Import และ Setup
import streamlit as st
import yfinance as yf
import pandas as pd
import altair as alt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import json
import gspread
import seaborn as sns
import matplotlib.pyplot as plt
from oauth2client.service_account import ServiceAccountCredentials

# 2. ฟังก์ชัน Load/Save Sheets
def get_gsheet_client():
    # ดึงค่าจาก secrets.toml
    creds_dict = st.secrets["gcp_service_account"]
    scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

def save_to_gsheet(df):
    client = get_gsheet_client()
    # เปลี่ยน 'ชื่อไฟล์ Sheet ของพี่อ้ำ' ให้ตรงกับไฟล์ใน Google Drive นะครับ
    sheet = client.open('ชื่อไฟล์ Google Sheet ของพี่อ้ำ').worksheet('JournalData')
    
    # ล้างข้อมูลเก่าและเขียนใหม่
    sheet.clear()
    sheet.update([df.columns.values.tolist()] + df.values.tolist())

def load_from_gsheet():
    client = get_gsheet_client()
    sheet = client.open('ชื่อไฟล์ Google Sheet ของพี่อ้ำ').worksheet('JournalData')
    data = sheet.get_all_records()
    return pd.DataFrame(data)

# ฟังก์ชันเชื่อมต่อ Google Sheets
def get_gsheet_client():
    creds_dict = st.secrets["gcp_service_account"]
    # เพิ่ม Scope ให้ครอบคลุมทุกอย่างที่ Google Sheets ต้องการ
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

# ปรับฟังก์ชัน SAVE (บันทึกลง Google Sheets)
def save_journal():
    df_temp = pd.DataFrame(st.session_state.journal_data)
    
    # แปลงวันที่เป็น String ก่อนบันทึก
    date_cols = ['วันที่', 'วันที่ซื้อ', 'วันที่ขาย']
    for col in date_cols:
        if col in df_temp.columns:
            df_temp[col] = pd.to_datetime(df_temp[col], errors='coerce').dt.strftime('%Y-%m-%d')
            
    # บันทึกลง Google Sheet
    client = get_gsheet_client()
    sheet = client.open('.Json').worksheet('JournalData')
    
    # ล้างข้อมูลเดิมและเขียนใหม่ (Header + Data)
    sheet.clear()
    sheet.update([df_temp.columns.values.tolist()] + df_temp.fillna('').values.tolist())

def save_portfolio():
    try:
        if st.session_state.my_portfolio is None:
            st.session_state.my_portfolio = []
            
        client = get_gsheet_client()
        sheet = client.open('.Json').worksheet('PortfolioData')
        
        sheet.clear() # ล้างข้อมูลเก่า
        if st.session_state.my_portfolio:
            df = pd.DataFrame(st.session_state.my_portfolio)
            # เขียน Header + ข้อมูล
            sheet.update([df.columns.values.tolist()] + df.fillna('').values.tolist())
            st.toast("บันทึกข้อมูลพอร์ตเรียบร้อย!", icon="✅") # เพิ่มตัวช่วยแจ้งเตือน
        else:
            st.toast("ข้อมูลพอร์ตว่างเปล่า", icon="⚠️")
            
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการบันทึกพอร์ต: {e}")

# ปรับฟังก์ชัน LOAD (อ่านจาก Google Sheets)
def load_journal():
    try:
        client = get_gsheet_client()
        sheet = client.open('.Json').worksheet('JournalData')
        data = sheet.get_all_records()
        st.session_state.journal_data = data
    except Exception as e:
        st.error(f"ไม่สามารถโหลดข้อมูลจาก Google Sheets ได้: {e}")
        st.session_state.journal_data = []

# ฟังก์ชัน Load ไฟล์ CSV/Excel (ยังคงใช้ได้เหมือนเดิม)
def load_data_from_file(uploaded_file):
    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
            
            # แปลงวันที่เป็น String
            if 'วันที่' in df.columns:
                df['วันที่'] = pd.to_datetime(df['วันที่']).dt.strftime('%Y-%m-%d')
            
            st.session_state.journal_data = df.to_dict('records')
            save_journal() # เรียกฟังก์ชันบันทึกลง Google Sheets
            st.success("นำเข้าข้อมูลสำเร็จ!")
            st.rerun()
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการอ่านไฟล์: {e}")

# --- ฟังก์ชันโหลดพอร์ต (วางไว้คู่กัน) ---
def load_portfolio():
    try:
        client = get_gsheet_client()
        sheet = client.open('.Json').worksheet('PortfolioData')
        data = sheet.get_all_records()
        
        # ใส่บรรทัดนี้ไว้เช็ค (รันแล้วลองดูว่ามันแสดงข้อมูลอะไรออกมาที่หน้าเว็บไหม)
        # st.write("ข้อมูลที่ดึงมา:", data) 
        
        st.session_state.my_portfolio = data if data else []
    except Exception as e:
        st.error(f"โหลดพอร์ตไม่สำเร็จ: {e}")
        st.session_state.my_portfolio = []

# --- ส่วนเริ่มต้นของไฟล์ ---#

if "journal_data" not in st.session_state:
    load_journal()   # <--- ใส่บรรทัดนี้ลงไปครับ! มันจะช่วยดึงข้อมูลจากไฟล์มาโชว์ตอนเปิดแอป

if "my_portfolio" not in st.session_state:
    load_portfolio()

# เรียกโหลดข้อมูลทุกครั้งที่รันแอปฯ
if "my_portfolio" not in st.session_state:
    load_portfolio()

if "journal_data" not in st.session_state:
    load_journal()

# --- Initialize Session State ---
# เช็คว่ามีค่าใน session_state หรือยัง ถ้าไม่มีให้โหลดจากไฟล์
if "cash_balance" not in st.session_state:
    st.session_state.cash_balance = 100000.0

# ตั้งค่าหน้าจอ
st.set_page_config(layout="wide")

st.title("📈 แอปพลิเคชันวิเคราะห์หุ้นไทย (Mark Minervini Style - RS vs SET Index)")
st.write("ระบบสแกนหุ้นกลุ่ม SET100 พร้อมกราฟเปรียบเทียบความแข็งแกร่งกับตลาดภาพรวม (SET Index)")

# จัดการ Session State เพื่อเก็บชื่อหุ้นที่เลือกไว้กลางระบบ
if "selected_ticker" not in st.session_state:
    st.session_state.selected_ticker = "KBANK"

# =============================================================
# ฟังก์ชันคำนวณทางเทคนิค (RSI สำหรับใช้ในตารางสแกน)
# =============================================================
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

# สารตั้งต้นข้อมูลหุ้นกลุ่ม SET100
SET100_TICKERS = [
    'AAV.BK', 'ACC.BK', 'ACE.BK', 'ADVANC.BK', 'AEONTS.BK', 'AH.BK', 'AMATA.BK', 'AOT.BK', 'AP.BK', 'AWC.BK', 
    'BAM.BK', 'BANPU.BK', 'BBL.BK', 'BCH.BK', 'BCP.BK', 'BCPG.BK', 'BDMS.BK', 'BEAUTY.BK', 'BEC.BK', 'BEM.BK', 
    'BGRIM.BK', 'BH.BK', 'BJC.BK', 'BLA.BK', 'BPP.BK', 'BTS.BK', 'CBG.BK', 'CENTEL.BK', 'CHG.BK', 'CK.BK', 
    'CKP.BK', 'COM7.BK', 'CPALL.BK', 'CPF.BK', 'CPN.BK', 'CRC.BK', 'DELTA.BK', 'DOHOME.BK', 'EA.BK', 'EGCO.BK', 
    'EPG.BK', 'ERW.BK', 'ESSO.BK', 'FORTH.BK', 'GLOBAL.BK', 'GPSC.BK', 'GULF.BK', 'GUNKUL.BK', 'HANA.BK', 'HMPRO.BK', 
    'ICHI.BK', 'III.BK', 'INTUCH.BK', 'IRPC.BK', 'IVL.BK', 'JAS.BK', 'JMART.BK', 'JMT.BK', 'KBANK.BK', 'KCE.BK', 
    'KKP.BK', 'KTB.BK', 'KTC.BK', 'LH.BK', 'MAJOR.BK', 'MEGA.BK', 'MINT.BK', 'MTC.BK', 'NER.BK', 'OR.BK', 
    'ORI.BK', 'OSP.BK', 'PLANB.BK', 'PRM.BK', 'PSH.BK', 'PTG.BK', 'PTL.BK', 'PTT.BK', 'PTTEP.BK', 'PTTGC.BK', 
    'QH.BK', 'RATCH.BK', 'RBF.BK', 'RS.BK', 'SAWAD.BK', 'SCB.BK', 'SCC.BK', 'SCGP.BK', 'SINGER.BK', 'SIRI.BK', 
    'SJWD.BK', 'SPALI.BK', 'SPRC.BK', 'STA.BK', 'STGT.BK', 'STEC.BK', 'SYNEX.BK', 'TASCO.BK', 'TCAP.BK', 'THANI.BK',
    'CCET.BK', 'TISCO.BK', 'TMB.BK', 'TOP.BK', 'TOA.BK', 'TPIPP.BK', 'TRUE.BK', 'TTA.BK', 'TTW.BK', 'TU.BK', 'TVI.BK','ttb.BK', 'UNIQ.BK', 'UNION.BK', 'UPA.BK', 'VGI.BK', 'WHA.BK', 'WICE.BK', 'WORK.BK', 'WPH.BK', 'WPRO.BK'
]
# 3. โค้ดส่วนสแกนหุ้น (load_and_calculate_stock_data) และการทำ Filter
# =============================================================
# ดึงข้อมูลและคำนวณฐานข้อมูลกลุ่ม SET100
# ============================================================
@st.cache_data(ttl=3600)
def load_and_calculate_stock_data():
    stock_list = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    total = len(SET100_TICKERS)
    
    set_market_pre = yf.Ticker("^SET.BK")
    hist_market_all = set_market_pre.history(period="2y")['Close'].to_frame(name='Market_Close')
    if hist_market_all.index.tz is not None:
        hist_market_all.index = hist_market_all.index.tz_localize(None)

    for i, ticker in enumerate(SET100_TICKERS):
        try:
            status_text.text(f"กำลังคำนวณสัญญาณเทคนิคัลและคัดกรองหุ้นซุปเปอร์สต็อก: {i+1}/{total}")
            progress_bar.progress((i + 1) / total)
            
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2y")
            
            if hist.empty or len(hist) < 200 or hist_market_all.empty:
                continue
                
            if hist.index.tz is not None:
                hist.index = hist.index.tz_localize(None)
                
            info = stock.info
            latest_price = hist['Close'].iloc[-1]
            
            combined = hist[['Open', 'High', 'Low', 'Close']].join(hist_market_all, how='inner')
            if combined.empty or len(combined) < 2:
                continue
                
            combined['RSI'] = calculate_rsi(combined['Close'], period=14)
            current_rsi = combined['RSI'].iloc[-1]
            
            base_stock = combined['Close'].iloc[0]
            stock_perf = ((combined['Close'] - base_stock) / base_stock) * 100
            
            base_market = combined['Market_Close'].iloc[0]
            market_perf = ((combined['Market_Close'] - base_market) / base_market) * 100
            
            combined['RS_Line'] = stock_perf - market_perf
            current_rs_val = combined['RS_Line'].iloc[-1]
            
            is_rs_above_zero = current_rs_val > 0
            days_above_zero = 0
            if is_rs_above_zero:
                for idx in range(1, len(combined) + 1):
                    if combined['RS_Line'].iloc[-idx] > 0:
                        days_above_zero += 1
                    else:
                        break
            
            days_below_zero = 0
            if current_rs_val <= 0:
                for idx in range(1, len(combined) + 1):
                    if combined['RS_Line'].iloc[-idx] <= 0:
                        days_below_zero += 1
                    else:
                        break
            
            high_3m = combined['High'].iloc[:-1].tail(60).max()
            high_6m = combined['High'].iloc[:-1].tail(120).max()
            high_52w = combined['High'].iloc[:-1].tail(250).max()
            
            def count_high_days(high_value):
                count = 0
                for idx in range(1, 15):
                    if len(combined) < idx: break
                    if combined['Close'].iloc[-idx] >= (high_value * 0.985):
                        count += 1
                    else:
                        break
                return count

            days_3m = count_high_days(high_3m)
            days_6m = count_high_days(high_6m)
            days_52w = count_high_days(high_52w)
            
            dividends_history = stock.dividends
            total_div_1y = 0.0
            if not dividends_history.empty:
                last_year = pd.Timestamp.now(tz='UTC') - pd.Timedelta(days=365)
                dividends_history.index = dividends_history.index.tz_convert('UTC')
                div_1y = dividends_history[dividends_history.index > last_year]
                total_div_1y = div_1y.sum()
            
            calc_div_yield = (total_div_1y / latest_price) * 100 if total_div_1y > 0 else 0.0
            pe_ratio = info.get('trailingPE', None)
            
            stock_list.append({
                'Ticker': ticker.replace('.BK', ''),
                'ราคาล่าสุด': round(latest_price, 2),
                'PE_Ratio': round(pe_ratio, 2) if pe_ratio else None,
                'ปันผล_%': round(calc_div_yield, 2),
                'RSI_14': round(current_rsi, 2) if not pd.isna(current_rsi) else None,
                'RS_Line_ปัจจุบัน': round(current_rs_val, 2),
                'Is_RS_Above_0': is_rs_above_zero,
                'ตัดเส้น0ขึ้นมาแล้ว(วัน)': days_above_zero if is_rs_above_zero else 0,
                'อยู่ใต้เส้น0มาแล้ว(วัน)': days_below_zero if not is_rs_above_zero else 0,
                'Is_3M_High': latest_price >= (high_3m * 0.99),
                'Is_6M_High': latest_price >= (high_6m * 0.99),
                'Is_52W_High': latest_price >= (high_52w * 0.99),
                'New_High_3M_มาแล้ว(วัน)': days_3m,
                'New_High_6M_มาแล้ว(วัน)': days_6m,
                'New_High_52W_มาแล้ว(วัน)': days_52w
            })
        except Exception as e:
            continue
            
    progress_bar.empty()
    status_text.empty()
    return pd.DataFrame(stock_list)

with st.spinner("⏳ กำลังประมวลผลระบบสแกนความแข็งแกร่งเชิงเปรียบเทียบ..."):
    df_set100 = load_and_calculate_stock_data()
################################    
# Sidebar (ตัวกรอง)
#################################
with st.sidebar.expander("⚙️ เมนูตัวกรองหุ้น (คลิกเพื่อเปิด/ปิด)", expanded=True):
    
    st.header("🎯 ตั้งค่าเงื่อนไขการสแกน")
    
    # 1. กรองพื้นฐาน
    max_pe = st.slider("1. ค่า P/E สูงสุด:", min_value=5.0, max_value=100.0, value=100.0, step=1.0)
    min_dividend = st.slider("2. ปันผลขั้นต่ำ (%):", min_value=0.0, max_value=10.0, value=0.0, step=0.1)
    rsi_range = st.slider("3. ช่วงค่า RSI:", min_value=10.0, max_value=90.0, value=(10.0, 90.0), step=1.0)
    
    st.markdown("---")
    
    # 2. สูตรคัดหุ้น
    st.subheader("🔮 สูตรคัดหุ้นผู้นำ")
    strategy_option = st.selectbox(
        "เลือกหน้าเทรด:",
        options=[
            "ไม่กรองเงื่อนไขนี้", 
            "⭐ RS Line ตัดเส้น 0 ขึ้นมาแล้ว", 
            "📈 RS Line ทำจุดสูงสุดใหม่ (RS New High)",
            "🔥 RS Line ใกล้จะตัด 0 (จ่อระเบิด)", 
            "3 Month High", 
            "6 Month High", 
            "52 Week High"
        ]
    )
min_days_threshold = 120 
if strategy_option == "🔥 RS Line ใกล้จะตัด 0 (จ่อระเบิด)":
    st.sidebar.markdown("---")
    st.sidebar.subheader("⏳ ตั้งค่าเวลาจ่อระเบิด (ผ่อนเกณฑ์)")
    time_choice = st.sidebar.selectbox(
        "เลือกระยะเวลาขั้นต่ำที่จมใต้เส้น 0:",
        options=["3 เดือน (60 วันทำการ)", "6 เดือน (120 วันทำการ)", "1 ปี (240 วันทำการ)"],
        index=1 
    )
    
    if time_choice == "3 เดือน (60 วันทำการ)":
        min_days_threshold = 60
    elif time_choice == "6 เดือน (120 วันทำการ)":
        min_days_threshold = 120
    else:
        min_days_threshold = 240

# ก่อนจะเข้าส่วน Filter ใน Sidebar (ช่วงการเตรียมข้อมูล)
# ตรวจสอบให้มั่นใจว่า df_set100 มีคอลัมน์ RS_Line อยู่แล้ว
if 'RS_Line' in df_set100.columns:
    # คำนวณหาค่าสูงสุดย้อนหลัง 50 วัน (ถ้ามีข้อมูลน้อยกว่า 50 วัน มันจะเอาค่าสูงสุดที่มี)
    df_set100['RS_Line_50D_Max'] = df_set100['RS_Line'].rolling(window=50, min_periods=1).max()
else:
    # ถ้าหาไม่เจอ ให้ใส่ค่า default เป็น -999 ป้องกัน Error
    df_set100['RS_Line_50D_Max'] = -999.0


# กรองพื้นฐาน (PE, Dividend, RSI)
filtered_df = df_set100.copy()
if max_pe < 100:
    filtered_df = filtered_df[(filtered_df['PE_Ratio'].notna()) & (filtered_df['PE_Ratio'] <= max_pe)]
filtered_df = filtered_df[filtered_df['ปันผล_%'] >= min_dividend]
filtered_df = filtered_df[(filtered_df['RSI_14'].notna()) & (filtered_df['RSI_14'] >= rsi_range[0]) & (filtered_df['RSI_14'] <= rsi_range[1])]

# กรองกลยุทธ์ (เพิ่มเงื่อนไข RS New High)
if strategy_option == "⭐ RS Line ตัดเส้น 0 ขึ้นมาแล้ว":
    filtered_df = filtered_df[filtered_df['Is_RS_Above_0'] == True]
    show_columns = ['Ticker', 'ราคาล่าสุด', 'PE_Ratio', 'ปันผล_%', 'RSI_14', 'RS_Line_ปัจจุบัน', 'ตัดเส้น0ขึ้นมาแล้ว(วัน)']
    sort_by_col, ascending_sort = 'ตัดเส้น0ขึ้นมาแล้ว(วัน)', True

elif strategy_option == "📈 RS Line ทำจุดสูงสุดใหม่ (RS New High)":
    # เงื่อนไข: RS Line ปัจจุบัน ต้อง >= ค่าสูงสุดย้อนหลัง 50 วัน (หรือตามที่คุณตั้งค่าไว้)
    filtered_df = filtered_df[filtered_df['RS_Line_ปัจจุบัน'] >= filtered_df['RS_Line_50D_Max']]
    show_columns = ['Ticker', 'ราคาล่าสุด', 'PE_Ratio', 'ปันผล_%', 'RSI_14', 'RS_Line_ปัจจุบัน']
    sort_by_col, ascending_sort = 'RS_Line_ปัจจุบัน', False

elif strategy_option == "🔥 RS Line ใกล้จะตัด 0 (จ่อระเบิด)":
    filtered_df = filtered_df[
        (-5.0 <= filtered_df['RS_Line_ปัจจุบัน']) & 
        (filtered_df['RS_Line_ปัจจุบัน'] <= 0.0) & 
        (filtered_df['อยู่ใต้เส้น0มาแล้ว(วัน)'] >= min_days_threshold)
    ]
    show_columns = ['Ticker', 'ราคาล่าสุด', 'PE_Ratio', 'ปันผล_%', 'RSI_14', 'RS_Line_ปัจจุบัน', 'อยู่ใต้เส้น0มาแล้ว(วัน)']
    sort_by_col, ascending_sort = 'RS_Line_ปัจจุบัน', False

elif strategy_option == "3 Month High":
    filtered_df = filtered_df[filtered_df['Is_3M_High'] == True]
    show_columns = ['Ticker', 'ราคาล่าสุด', 'PE_Ratio', 'ปันผล_%', 'RSI_14', 'New_High_3M_มาแล้ว(วัน)']
    sort_by_col = 'New_High_3M_มาแล้ว(วัน)'
    ascending_sort = True
elif strategy_option == "6 Month High":
    filtered_df = filtered_df[filtered_df['Is_6M_High'] == True]
    show_columns = ['Ticker', 'ราคาล่าสุด', 'PE_Ratio', 'ปันผล_%', 'RSI_14', 'New_High_6M_มาแล้ว(วัน)']
    sort_by_col = 'New_High_6M_มาแล้ว(วัน)'
    ascending_sort = True
elif strategy_option == "52 Week High":
    filtered_df = filtered_df[filtered_df['Is_52W_High'] == True]
    show_columns = ['Ticker', 'ราคาล่าสุด', 'PE_Ratio', 'ปันผล_%', 'RSI_14', 'New_High_52W_มาแล้ว(วัน)']
    sort_by_col = 'New_High_52W_มาแล้ว(วัน)'
    ascending_sort = True

else:
    show_columns = ['Ticker', 'ราคาล่าสุด', 'PE_Ratio', 'ปันผล_%', 'RSI_14', 'RS_Line_ปัจจุบัน']
    sort_by_col, ascending_sort = 'Ticker', True

# สรุปผล
final_sorted_df = filtered_df[show_columns].sort_values(by=sort_by_col, ascending=ascending_sort).reset_index(drop=True)

##########################
# 4. ส่วนการเลือกหุ้น (เป็นตัวกลางส่งค่าไป Fundamental และ กราฟ)

st.subheader("🔍 1. วิเคราะห์กราฟเทคนิคัลอัจฉริยะ (Multi-Timeframe & RS vs SET Index)")

col_input, col_metrics = st.columns([1, 3])

with col_input:
    all_tickers = [t.replace('.BK', '') for t in SET100_TICKERS]
    
    # 1. กำหนดค่าเริ่มต้น
    current_selected = st.session_state.get("selected_ticker", "KBANK")
    
    # 2. สร้าง Selectbox
    ticker_input = st.selectbox(
        "เลือกหรือพิมพ์ชื่อหุ้นที่ต้องการดูราคากราฟรายละเอียด:", 
        options=all_tickers, 
        index=all_tickers.index(current_selected) if current_selected in all_tickers else 0
    )
    
    # 3. จุดสำคัญ: ถ้าค่าที่เลือกใหม่ไม่ตรงกับค่าใน session_state ให้สั่งอัปเดตและ Rerun
    if ticker_input != current_selected:
        st.session_state.selected_ticker = ticker_input
        st.rerun()  # บังคับให้โปรแกรมเริ่มทำงานใหม่ตั้งแต่บรรทัดบนสุดเพื่อให้กราฟโหลดข้อมูลหุ้นตัวใหม่
    
    ticker = f"{st.session_state.selected_ticker}.BK"

selected_ticker = st.session_state.selected_ticker 
ticker = f"{selected_ticker}.BK"
stock_data = yf.Ticker(ticker)
info = stock_data.info # ดึง info มาที่นี่เพื่อให้ Fundamental ใช้ได้   
    
##### link web set and trading view ########
# สร้างคอลัมน์ 2 ช่อง (ขนาดเท่ากัน)
col1, col2 = st.columns(2)

# ปุ่มที่ 1 (ใส่ในคอลัมน์ที่ 1)
with col1:
    set_url = f"https://www.set.or.th/th/market/product/stock/quote/{st.session_state.selected_ticker}/company-profile/information"
    st.link_button(f"🌐 ข้อมูล SET", set_url, use_container_width=True)

# ปุ่มที่ 2 (ใส่ในคอลัมน์ที่ 2)
with col2:
    tv_url = f"https://www.tradingview.com/chart/?symbol=SET%3A{st.session_state.selected_ticker}"
    st.link_button(f"📈 กราฟ TradingView", tv_url, use_container_width=True)

# 5. Fundamental Dashboard
if info:
    st.markdown("#### 📊 Fundamental Growth Dashboard (คัดกรองพลังขับเคลื่อนตามสูตร SEPA)")

    # ดึงงบอย่างปลอดภัย (เนื่องจากหุ้นไทยบางตัวบน Yahoo Finance ข้อมูลบางช่องอาจเป็น None)
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
        st.write(f"• **ราคาต่อกำไรสุทธิ (P/E Ratio ยืนยัน):** {info.get('trailingPE', 'ไม่มีข้อมูล')} เท่า")
        
    st.info("💡 **ข้อแนะนำจากระบบ:** หุ้นซุปเปอร์สต็อกตามสไตล์ Mark Minervini มักจะมี EPS Growth ขยายตัวมากกว่า 20%-25% ขึ้นไป ควบคู่กับราคาหุ้นที่ยกฐานยืนเหนือเส้น EMA ขาขึ้น")

#####################################

st.markdown("##### ⚙️ ตั้งค่าการแสดงผลกราฟ")
col_tf, col_period = st.columns([1, 1])

tf_mapping = {
    "1 ชม. (1hr)": "1h",
    "4 ชม. (4hr)": "4h",
    "1 วัน (Day)": "1d",
    "1 สัปดาห์ (Week)": "1wk",
    "1 เดือน (Month)": "1mo"
}
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
    if selected_tf in ["1h", "4h"]:
        period_options = ["6 เดือน (6m)", "1 ปี (1y)"]
        chart_period = st.pills("เลือกช่วงเวลากราฟ (สั้น/กลาง):", options=period_options, default="6 เดือน (6m)")
    else:
        period_options = ["6 เดือน (6m)", "1 ปี (1y)", "5 ปี (5y)", "ตั้งแต่เข้าตลาด (All Time)"]
        chart_period = st.pills("เลือกช่วงเวลากราฟ (ทั้งหมด):", options=period_options, default="6 เดือน (6m)")
    if not chart_period:
        chart_period = "6 เดือน (6m)" if selected_tf in ["1h", "4h"] else "1 เดือน (1y)"

# =============================================================
# 6. กราฟเทคนิคัล
# =============================================================
try:
    ticker = f"{st.session_state.selected_ticker}.BK"
    stock_data = yf.Ticker(ticker)
    set_market = yf.Ticker("^SET.BK")
    info = stock_data.info
    
    
    # 3.1 กำหนดช่วงเวลา 
    p_map = {"6 เดือน (6m)": "6mo", "1 ปี (1y)": "1y", "5 ปี (5y)": "5y", "ตั้งแต่เข้าตลาด (All Time)": "max"}
    selected_period = p_map.get(chart_period, "1y")
    actual_interval = "1h" if selected_tf == "4h" else selected_tf
    
    # กันเหนียว: ถ้า TF สั้น (1h/4h) เลือก Period ยาวเกินไป ให้ตัดเหลือ 1 ปี เพื่อป้องกันกราฟไม่ขึ้น
    if selected_tf in ["1h", "4h"] and selected_period in ["5y", "max"]:
        selected_period = "1y"

    # 3.2 ดึงข้อมูล
    hist_chart = stock_data.history(period=selected_period, interval=actual_interval)
    hist_market = set_market.history(period=selected_period, interval=actual_interval)
    
    # กรณีดึงข้อมูลมาแล้วว่าง ให้ลองถอยกลับไปดึง period ที่สั้นลง (Fallback)
    if hist_chart.empty:
        hist_chart = stock_data.history(period="6mo", interval=actual_interval)
        hist_market = set_market.history(period="6mo", interval=actual_interval)

    # 3.3 จัดการ Resample สำหรับ 4h
    if selected_tf == "4h" and not hist_chart.empty:
        conversion = {'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}
        hist_chart = hist_chart.resample('4h').agg(conversion).ffill()
        hist_market = hist_market.resample('4h').agg(conversion).ffill()
        
    if not hist_chart.empty:
        # ปรับ Timezone และรวมข้อมูล
        if hist_chart.index.tz is not None: hist_chart.index = hist_chart.index.tz_localize(None)
        if not hist_market.empty and hist_market.index.tz is not None: hist_market.index = hist_market.index.tz_localize(None)

        hist_market_close = hist_market['Close'].to_frame(name='Market_Close')
        chart_combined = hist_chart[['Open', 'High', 'Low', 'Close']].join(hist_market_close, how='inner')
        
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
            m1, m2, m3, m4 = st.columns(4)
        # ปรับส่วนดึงข้อมูลปันผลในส่วน 3.5 Metrics
        raw_div = info.get('dividendYield') or info.get('trailingAnnualDividendYield', 0)

        if raw_div:
            # ถ้าค่าที่ได้ > 1 (เช่น 3.5) แสดงว่าเป็นเปอร์เซ็นต์อยู่แล้ว
            # ถ้าค่าที่ได้ <= 1 (เช่น 0.035) แสดงว่าเป็นทศนิยม ต้องคูณ 100
            if raw_div > 1:
                div_display = f"{raw_div:.2f}%"
            else:
                div_display = f"{raw_div * 100:.2f}%"
        else:
            div_display = "N/A"

        m4.metric("ปันผล (Yield)", div_display)
        m1.metric("ชื่อบริษัท", info.get('longName', 'N/A'))
        m2.metric("ราคาล่าสุด", f"{latest_price_single:.2f} บ.")
        m3.metric("สถานะ RS", "แข็งแกร่งกว่าตลาด" if chart_combined['RS_Line'].iloc[-1] > chart_combined['RS_EMA20'].iloc[-1] else "อ่อนแอกว่าตลาด")
    

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
    # (แนะนำให้พี่อ้ำใช้โค้ดเดิมในส่วนนี้ได้เลยครับ ผมตัดมาให้สั้นลงเพื่อดูโครงสร้าง)
    # ...


except Exception as e:
    st.error(f"⚠️ เกิดข้อผิดพลาดในการวาดกราฟ: {str(e)}")

# =============================================================
# 7. ผลลัพธ์การสแกน
# =============================================================
###################################################
st.subheader(f"📊 2. ผลลัพธ์การสแกน ({strategy_option}): เจอทั้งหมด {len(final_sorted_df)} ตัว")
st.write("💡 **คำแนะนำสีไฮไลท์อัจฉริยะ:** สีเขียว 🟢 = เขตสะสมกำลัง (RSI 30-45) | สีแดง 🔴 = เขตร้อนแรงระวังดอย (RSI >= 65)")

def highlight_rsi_zones(row):
    if row['RSI_14'] >= 65.0:
        return ['background-color: #fce4d6; color: black'] * len(row)
    elif 30.0 <= row['RSI_14'] <= 45.0:
        return ['background-color: #e2f0d9; color: black'] * len(row)
    return [''] * len(row)

styled_df = final_sorted_df.style.format({
    'ราคาล่าสุด': '{:.2f}',
    'PE_Ratio': '{:.2f}',
    'ปันผล_%': '{:.2f}',
    'RSI_14': '{:.2f}',
    'RS_Line_ปัจจุบัน': '{:.2f}'
}, na_rep='-').apply(highlight_rsi_zones, axis=1)


# ปรับการรับ Selection ให้รัดกุมขึ้น
event = st.dataframe(
    styled_df,
    use_container_width=True,
    selection_mode="single-row",
    on_select="rerun",
    key="stock_table"
)
# ดึงข้อมูลการเลือกจาก event
if event.selection and "rows" in event.selection and event.selection["rows"]:
    selected_index = event.selection["rows"][0]
    clicked_ticker = final_sorted_df.iloc[selected_index]['Ticker']
    
    if st.session_state.get("selected_ticker") != clicked_ticker:
        st.session_state.selected_ticker = clicked_ticker
        st.rerun()

# แก้ไขส่วนการดึงข้อมูลจาก event ให้รัดกุมขึ้น
if event.selection and "rows" in event.selection and event.selection["rows"]:
    selected_index = event.selection["rows"][0]
    
    # [จุดสำคัญ] ตรวจสอบว่า Index ที่เลือก มีอยู่จริงในตารางใหม่หรือไม่
    if selected_index < len(final_sorted_df):
        clicked_ticker = final_sorted_df.iloc[selected_index]['Ticker']
        
        if st.session_state.get("selected_ticker") != clicked_ticker:
            st.session_state.selected_ticker = clicked_ticker
            st.rerun()
    else:
        # ถ้า Index เกินจำนวนแถว ให้เคลียร์การเลือกหรือทำอะไรบางอย่าง
        st.warning("ตารางถูกกรองใหม่ โปรดเลือกหุ้นใหม่อีกครั้ง")

##########################
# 8.แท็บข้อมูล
##############################  
st.markdown("---") # เส้นคั่น เพื่อแยกส่วนกับตารางด้านบนให้ชัด
st.subheader("🛠 ระบบจัดการข้อมูลและวิเคราะห์พอร์ต")

# 1. ปรับแก้บรรทัดสร้าง Tabs เพิ่ม tab_dashboard เข้าไปครับ
tab_dashboard, tab_risk, tab_portfolio, tab_journal = st.tabs([
    "📈 Dashboard", "🧮 คำนวณความเสี่ยง", "📊 พอร์ตโฟลิโอ", "📖 สมุดบันทึก"
])

##############################
with tab_dashboard:
    st.markdown("### 📊 Trading Performance Dashboard")
    
    if not st.session_state.get('journal_data'):
        st.info("ยังไม่มีข้อมูลรายการเทรดครับ")
    else:
        df_journal = pd.DataFrame(st.session_state.journal_data)
        df_journal['วันที่'] = pd.to_datetime(df_journal['วันที่'])
        df_closed = df_journal[df_journal['สถานะ'] == 'Closed (ขายแล้ว)'].copy()
        
        if df_closed.empty:
            st.info("ยังไม่มีข้อมูลรายการที่ปิดสถานะ (Closed) เพื่อสรุปผลงานครับ")
        else:
            # ทำความสะอาดข้อมูล
            df_closed['กำไร/ขาดทุน (บาท)'] = pd.to_numeric(df_closed['กำไร/ขาดทุน (บาท)'], errors='coerce')
            df_closed['ต้นทุน (บาท)'] = pd.to_numeric(df_closed['ต้นทุน (บาท)'], errors='coerce')
            df_clean = df_closed.dropna(subset=['กำไร/ขาดทุน (บาท)', 'ต้นทุน (บาท)'])
            df_clean = df_clean[df_clean['ต้นทุน (บาท)'] > 100]
            df_clean['% ROI'] = (df_clean['กำไร/ขาดทุน (บาท)'] / df_clean['ต้นทุน (บาท)']) * 100

            # Filter
            col_f1, col_f2 = st.columns([1, 3])
            filter_type = col_f1.selectbox("แสดงผลตาม:", ["ทั้งหมด", "รายปี", "รายเดือน"])
            
            df_filtered = df_clean.copy()
            if filter_type == "รายปี":
                year = col_f2.selectbox("เลือกปี:", sorted(df_clean['วันที่'].dt.year.unique(), reverse=True))
                df_filtered = df_clean[df_clean['วันที่'].dt.year == year]
            elif filter_type == "รายเดือน":
                year = col_f2.selectbox("เลือกปี:", sorted(df_clean['วันที่'].dt.year.unique(), reverse=True))
                month = col_f2.selectbox("เลือกเดือน:", range(1, 13))
                df_filtered = df_clean[(df_clean['วันที่'].dt.year == year) & (df_clean['วันที่'].dt.month == month)]

            # คำนวณ Metric
            wins = df_filtered[df_filtered['กำไร/ขาดทุน (บาท)'] > 0]
            losses = df_filtered[df_filtered['กำไร/ขาดทุน (บาท)'] < 0]
            avg_win = wins['กำไร/ขาดทุน (บาท)'].mean() if not wins.empty else 0
            avg_loss = abs(losses['กำไร/ขาดทุน (บาท)'].mean()) if not losses.empty else 1
            rr_ratio_actual = avg_win / avg_loss
            
            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("กำไร/ขาดทุนสุทธิ", f"{df_filtered['กำไร/ขาดทุน (บาท)'].sum():,.0f} ฿")
            col2.metric("ค่าเฉลี่ยต่อไม้ (%):", f"{df_clean['% ROI'].mean():.2f} %")
            col3.metric("Win Rate", f"{(len(wins)/len(df_filtered)*100):.1f}%" if not df_filtered.empty else "0%")
            col4.metric("Profit Factor", f"{(wins['กำไร/ขาดทุน (บาท)'].sum() / abs(losses['กำไร/ขาดทุน (บาท)'].sum())):.2f}" if not losses.empty and losses['กำไร/ขาดทุน (บาท)'].sum() != 0 else "N/A")
            col5.metric("Realized R:R", f"{rr_ratio_actual:.2f} : 1")

            st.markdown("---")

            st.markdown("##### 🔍 สถิติการเทรดเชิงลึก")
            col_s1, col_s2 = st.columns(2)
            
            # --- แก้ KeyError: บังคับคำนวณคอลัมน์ก่อนใช้งาน ---
            df_filtered['Profit_Pct'] = (df_filtered['กำไร/ขาดทุน (บาท)'] / df_filtered['ต้นทุน (บาท)']) * 100
            
            # 1. หา index ของไม้ที่กำไรดีสุด และขาดทุนหนักสุด
            idx_best = df_filtered['กำไร/ขาดทุน (บาท)'].idxmax()
            idx_worst = df_filtered['กำไร/ขาดทุน (บาท)'].idxmin()
            
            # 2. ดึงค่าเงินและ % ตาม index ที่หาได้
            best_val = df_filtered.loc[idx_best, 'กำไร/ขาดทุน (บาท)']
            best_pct = df_filtered.loc[idx_best, 'Profit_Pct']
            
            worst_val = df_filtered.loc[idx_worst, 'กำไร/ขาดทุน (บาท)']
            worst_pct = df_filtered.loc[idx_worst, 'Profit_Pct']

            # 3. แสดงผลในรูปแบบ "เงิน / %"
            col_s1.metric("กำไรสูงสุดต่อไม้", f"{best_val:,.0f} ฿ / {best_pct:.1f}%")
            col_s2.metric("ขาดทุนหนักสุดต่อไม้", f"{worst_val:,.0f} ฿ / {worst_pct:.1f}%")
            
            st.markdown("---")
            ######### กราฟรายเดือน vs พร์อตสะสม ###################
            st.markdown("##### 📈 ผลงานรายเดือน vs พอร์ตสะสม")
            c1, c2 = st.columns(2)

            # --- ข้อมูลรายเดือน ---
            df_monthly = df_filtered.copy()
            df_monthly['Date'] = pd.to_datetime(df_monthly['วันที่'])
            
            # สร้าง Month_Label และรักษาค่าเวลาไว้สำหรับการเรียง
            df_monthly['Month_Label'] = df_monthly['Date'].dt.strftime('%b %Y')
            
            # **หัวใจสำคัญ:** เรียงตาม 'Date' ก่อนที่จะ Groupby เพื่อให้เดือนเรียงจากอดีตไปปัจจุบัน
            df_monthly = df_monthly.sort_values('Date') 
            
            df_monthly = df_monthly.groupby('Month_Label', sort=False)['กำไร/ขาดทุน (บาท)'].sum().reset_index()
            df_monthly.columns = ['Month_Label', 'Profit_Sum']
            
            # --- คำนวณกำไรสะสม ---
            df_monthly['Cumulative_Profit'] = df_monthly['Profit_Sum'].cumsum()
            df_monthly['Color'] = df_monthly['Profit_Sum'].apply(lambda x: 'Profit' if x >= 0 else 'Loss')

            c1, c2 = st.columns(2)

            with c1:
                # กราฟแท่ง (ใช้ sort=None เพราะเราเรียง df_monthly มาแล้ว)
                chart_bar = alt.Chart(df_monthly).mark_bar(width=40).encode(
                    x=alt.X('Month_Label:O', title='เดือน', sort=None), 
                    y=alt.Y('Profit_Sum:Q', title='กำไร/ขาดทุน (บาท)'),
                    color=alt.Color('Color', scale=alt.Scale(domain=['Profit', 'Loss'], range=['#2ecc71', '#e74c3c']), legend=None),
                    tooltip=['Month_Label', 'Profit_Sum']
                ).properties(height=300)
                
                rule = alt.Chart(pd.DataFrame({'y': [0]})).mark_rule(color='#666666', strokeDash=[3,3]).encode(y='y')
                st.altair_chart(chart_bar + rule, use_container_width=True)

            with c2:
                # กราฟเส้น (ใช้ sort=None เช่นกัน)
                chart_line = alt.Chart(df_monthly).mark_line(point=True, color='#3498db', strokeWidth=3).encode(
                    x=alt.X('Month_Label:O', title='เดือน', sort=None),
                    y=alt.Y('Cumulative_Profit:Q', title='กำไรสะสม (บาท)'),
                    tooltip=['Month_Label', 'Cumulative_Profit']
                ).properties(height=300)
                
                st.altair_chart(chart_line, use_container_width=True)

            ##### เร่ิมกราฟกระจายตัว ###########
            # --- 1. คำนวณ % ตั้งแต่เนิ่นๆ ---
            df_filtered = df_clean.copy() # หรือตาม logic เดิมของพี่อ้ำ
            # (ตรวจสอบให้แน่ใจว่าได้ filter ตามวันที่เรียบร้อยแล้วก่อนบรรทัดนี้)
            df_filtered['Profit_Pct'] = (df_filtered['กำไร/ขาดทุน (บาท)'] / df_filtered['ต้นทุน (บาท)']) * 100

            # --- 2. ค่อยแยก wins/losses ออกมา ---
            wins = df_filtered[df_filtered['กำไร/ขาดทุน (บาท)'] > 0]
            losses = df_filtered[df_filtered['กำไร/ขาดทุน (บาท)'] < 0]

            # --- 3. ส่วนวาดกราฟ ---
            st.markdown("##### 🔔 การกระจายตัวกำไร/ขาดทุน (%)")
            fig, ax = plt.subplots(figsize=(10, 4))
            
            sns.histplot(df_filtered['Profit_Pct'], kde=True, color='#3498db', 
                         binwidth=1, edgecolor='none', alpha=0.3, ax=ax)
            
            # เส้นค่าเฉลี่ย
            mean_val = df_filtered['Profit_Pct'].mean()
            ax.axvline(mean_val, color="#12da58", linestyle='--', linewidth=1.5, label=f'Mean: {mean_val:.1f}%')
            # เพิ่มเส้นนี้เข้าไปในกราฟครับ
            avg_loss_pct = losses['Profit_Pct'].mean()
            ax.axvline(avg_loss_pct, color='#9b59b6', linestyle=':', linewidth=2, 
                 label=f'Actual Avg Loss: {avg_loss_pct:.1f}%')
            
            # เส้น Optimal Cutloss (RR 2:1)
            if not wins.empty:
                avg_win_pct = wins['Profit_Pct'].mean()
                optimal_cutloss_pct = -(avg_win_pct / 2.0)
                ax.axvline(optimal_cutloss_pct, color="#f21d2b", linestyle='-.', linewidth=2, 
                           label=f'Target Cutloss (RR 2:1): {optimal_cutloss_pct:.1f}%')

            # ปรับแต่งกราฟ
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.grid(False)
            ax.yaxis.set_visible(True)
            
            from matplotlib.ticker import MultipleLocator
            ax.xaxis.set_major_locator(MultipleLocator(1))
            ax.set_xlabel('Profit/Loss (%)', fontsize=12)
            ax.set_ylabel('no.Trades', fontsize=12)
            
            plt.xticks(fontsize=5, rotation=90) 
            ax.legend(frameon=False)
            
            fig.tight_layout(pad=2.0)
            st.pyplot(fig)

########################
with tab_portfolio:
    st.markdown("#### 💼 ระบบบันทึกพอร์ตโฟลิโอส่วนตัว")
    
    # 1. จัดการเงินสด (แก้ไขด้วยตัวเองได้ตลอดเวลา)
    if "cash_balance" not in st.session_state: st.session_state.cash_balance = 100000.0
    
    # ใช้ callback หรืออัปเดตค่าจาก input นี้ไปที่ session_state โดยตรง
    st.session_state.cash_balance = st.number_input(
        "💵 เงินสดคงเหลือในพอร์ต (บาท):", 
        value=float(st.session_state.cash_balance), 
        step=1000.0
    )
    
    # 2. ฟอร์มเพิ่ม/ลดหุ้น
    with st.expander("🔄 บันทึกการซื้อขายหุ้น (อัปเดต Portfolio & Journal)"):
        with st.form("portfolio_journal_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            
            # ดึงรายชื่อหุ้นจากพอร์ตเพื่อนำมาแสดงใน selectbox
            portfolio_stocks = [item['หุ้น'] for item in st.session_state.my_portfolio] if "my_portfolio" in st.session_state else []
            
            with col1:
                options = ["  "] + portfolio_stocks
                select_ticker = st.selectbox("เลือกหุ้นจากพอร์ต (หรือพิมพ์ใหม่):", options)
                p_ticker = st.text_input("ชื่อหุ้น:") if select_ticker == "  " else select_ticker
                p_buy_date = st.date_input("วันที่ทำรายการ:")
                p_status = st.selectbox("สถานะรายการ:", ["Open (กำลังถือ)", "Closed (ขายแล้ว)"])
                j_sell_date = st.date_input("วันที่ขาย (ถ้าขายแล้ว):") if p_status == "Closed (ขายแล้ว)" else None
                
            with col2:
                p_type = st.selectbox("ประเภท:", ["ซื้อ (Buy)", "ขายทำกำไร (Take Profit)", "ขายตัดขาดทุน (Stop Loss)"])
                p_result = st.number_input("กำไร/ขาดทุน (บาท):", step=100.0, format="%.2f")
                p_price = st.number_input("ราคาต่อหุ้น:", min_value=0.01, step=0.05, format="%.2f")
                p_qty = st.number_input("จำนวนหุ้น:", min_value=1, step=100)
                p_comm = st.number_input("ค่าธรรมเนียม:", min_value=0.0, step=1.0)
                
            p_reason = st.text_area("เหตุผล/กลยุทธ์:")
            submitted = st.form_submit_button("ยืนยันรายการ")

            if submitted:
                total_val = (p_qty * p_price)
                ticker_upper = p_ticker.upper()

                # 1. จัดการข้อมูล Portfolio (อัปเดตสถานะจำนวนหุ้น)
                found_idx = next((i for i, item in enumerate(st.session_state.my_portfolio) if item['หุ้น'] == ticker_upper), -1)
                
                if "ซื้อ" in p_type:
                    st.session_state.cash_balance -= (total_val + p_comm)
                    if found_idx != -1:
                        old = st.session_state.my_portfolio[found_idx]
                        new_shares = old['shares'] + p_qty
                        new_cost = ((old['shares'] * old['avg_price']) + total_val) / new_shares
                        st.session_state.my_portfolio[found_idx] = {'หุ้น': ticker_upper, 'shares': new_shares, 'avg_price': new_cost}
                    else:
                        st.session_state.my_portfolio.append({'หุ้น': ticker_upper, 'shares': p_qty, 'avg_price': p_price})
                else: # กรณีขาย
                    if found_idx != -1:
                        st.session_state.cash_balance += (total_val - p_comm)
                        st.session_state.my_portfolio[found_idx]['shares'] -= p_qty
                        if st.session_state.my_portfolio[found_idx]['shares'] <= 0:
                            st.session_state.my_portfolio.pop(found_idx)
                
                # 2. เพิ่มข้อมูลเข้า Journal (ปรับ Key ให้ตรงกับสูตรสถิติเดิมของพี่อ้ำ)
                new_entry = {
                    "วันที่": str(p_buy_date), 
                    "วันที่ซื้อ": str(p_buy_date),
                    "วันที่ขาย": str(j_sell_date) if j_sell_date else None,
                    "หุ้น": ticker_upper,
                    "สถานะ": p_status,
                    "ประเภท": p_type,
                    "กำไร/ขาดทุน (บาท)": p_result,
                    "ต้นทุน (บาท)": total_val,
                    "ราคาหุ้นที่ซื้อ (บาท/หุ้น)": p_price,
                    "จำนวนหุ้นที่ซื้อ": p_qty,
                    "เหตุผล": p_reason
                }
                st.session_state.journal_data.append(new_entry)

                # 3. บันทึกลง Google Sheets
                save_portfolio() 
                save_journal()
                
                st.success(f"บันทึกรายการ {ticker_upper} เรียบร้อย!")
                st.rerun()

    # 3. ตารางแสดงพอร์ต (เชื่อมต่อ Google Sheets)
    st.divider()
    st.markdown("##### 📊 สรุปพอร์ตการลงทุน")
    
    if "my_portfolio" not in st.session_state:
        load_portfolio()

    if st.session_state.my_portfolio:
        portfolio_list = []
        total_invest = 0
        total_value = 0
        
        for index, row in enumerate(st.session_state.my_portfolio):
            ticker = row.get('หุ้น', '')
            shares = float(row.get('shares', 0))
            avg_price = float(row.get('avg_price', 0.0))
            
            try:
                m_price = yf.Ticker(f"{ticker}.BK").history(period="1d")['Close'].iloc[-1]
            except:
                m_price = avg_price
            
            cost_value = shares * avg_price
            market_value = shares * m_price
            profit = market_value - cost_value
            # คำนวณ % กำไร/ขาดทุน
            profit_pct = (profit / cost_value * 100) if cost_value > 0 else 0
            
            portfolio_list.append({
                "หุ้น": ticker,
                "จำนวน": shares,
                "ต้นทุนเฉลี่ย": avg_price,
                "มูลค่าต้นทุน": cost_value,
                "ราคาตลาด": m_price,
                "มูลค่าตลาด": market_value,
                "กำไร/ขาดทุน": profit,
                "% กำไร/ขาดทุน": profit_pct,
                "สถานะ": '🟢' if profit > 0 else ('🔴' if profit < 0 else '⚪')
            })
            
            total_invest += cost_value
            total_value += market_value

        # สรุปยอดรวม
        col_s1, col_s2, col_s3 = st.columns(3)
        col_s1.metric("เงินลงทุนรวม", f"{total_invest:,.0f} ฿")
        col_s2.metric("มูลค่าปัจจุบัน", f"{total_value:,.0f} ฿")
        diff = total_value - total_invest
        col_s3.metric("กำไร/ขาดทุนรวม", f"{diff:,.0f} ฿", 
                    delta=f"{((diff)/total_invest)*100:.2f}%" if total_invest > 0 else "0%")

        # แสดงตารางเดียวที่แก้ไขได้
        df_p = pd.DataFrame(portfolio_list)
        edited_df = st.data_editor(
            df_p, 
            use_container_width=True, 
            key="portfolio_editor",
            column_config={
                "หุ้น": st.column_config.TextColumn(disabled=True),
                "จำนวน": st.column_config.NumberColumn(format="%d"),
                "ต้นทุนเฉลี่ย": st.column_config.NumberColumn(format="%.2f"),
                "มูลค่าต้นทุน": st.column_config.NumberColumn(format="%,.0f", disabled=True),
                "ราคาตลาด": st.column_config.NumberColumn(format="%.2f", disabled=True),
                "มูลค่าตลาด": st.column_config.NumberColumn(format="%,.0f", disabled=True),
                "กำไร/ขาดทุน": st.column_config.NumberColumn(format="%,.0f", disabled=True),
                "% กำไร/ขาดทุน": st.column_config.NumberColumn(format="%.2f%%", disabled=True),
                "สถานะ": st.column_config.TextColumn(disabled=True)
            }
        )

        # อัปเดตข้อมูลเมื่อมีการแก้ไข
        if st.session_state.portfolio_editor["edited_rows"]:
            for idx, changes in st.session_state.portfolio_editor["edited_rows"].items():
                if "จำนวน" in changes: st.session_state.my_portfolio[idx]["shares"] = changes["จำนวน"]
                if "ต้นทุนเฉลี่ย" in changes: st.session_state.my_portfolio[idx]["avg_price"] = changes["ต้นทุนเฉลี่ย"]
            save_portfolio()
            st.rerun()
    else:
        st.info("ยังไม่มีข้อมูลหุ้นในพอร์ตโฟลิโอครับ")

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

################# เรียกการคำนวนนับจำนวนวันถือหุ้น #####################
def calculate_journal_stats(df):
    df = df[df['สถานะ'] == 'Closed (ขายแล้ว)'].copy()
    
    # 1. จัดการคอลัมน์และคำนวณวันที่
    if 'วันที่ซื้อ' not in df.columns: df['วันที่ซื้อ'] = df['วันที่'] 
    if 'วันที่ขาย' not in df.columns: df['วันที่ขาย'] = df['วันที่'] 
    
    df['วันที่ซื้อ'] = pd.to_datetime(df['วันที่ซื้อ'])
    df['วันที่ขาย'] = pd.to_datetime(df['วันที่ขาย'])
    df['Holding_Days'] = (df['วันที่ขาย'] - df['วันที่ซื้อ']).dt.days.clip(lower=0)
    
    # 2. คำนวณเป็น % (Profit / Cost) * 100
    # ใช้ .replace(0, np.nan) เพื่อกัน Error หารด้วยศูนย์
    df['ROI_Percent'] = (df['กำไร/ขาดทุน (บาท)'] / df['ต้นทุน (บาท)'].replace(0, np.nan)) * 100
    
    df['Year'] = df['วันที่ขาย'].dt.year
    df['Month'] = df['วันที่ขาย'].dt.month
    
    # 3. สรุปผลเป็น % ตามที่พี่อ้ำต้องการ
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
    # แยกการปัดเศษให้คอลัมน์ % เป็น 2 ตำแหน่ง และคอลัมน์จำนวนวันเป็นจำนวนเต็ม
    stats = stats.round({'Avg_Days_Win': 0, 'Avg_Days_Loss': 0})
    stats = stats.round(2) # ที่เหลือปัดเป็น 2 ตำแหน่ง
    return stats
########################################################################
### แสดงข้อมูลสถิติ รายเดือน รายปี ####
if st.session_state.journal_data:
        df_journal = pd.DataFrame(st.session_state.journal_data)
        # --- เริ่มต้น Data Migration ---
        # 1. เช็คว่ามีคอลัมน์สำคัญไหม ถ้าไม่มีให้สร้าง
        cols_to_check = ['วันที่ซื้อ', 'วันที่ขาย']
        for col in cols_to_check:
            if col not in df_journal.columns:
                # ถ้าไม่มี ให้ก๊อปปี้ค่าจาก 'วันที่' (ที่เป็นค่าตั้งต้น) มาใส่
                df_journal[col] = df_journal['วันที่']
        
        # 2. แปลงทุกอย่างเป็น datetime เพื่อความปลอดภัยในการคำนวณ
        df_journal['วันที่ซื้อ'] = pd.to_datetime(df_journal['วันที่ซื้อ'], errors='coerce')
        df_journal['วันที่ขาย'] = pd.to_datetime(df_journal['วันที่ขาย'], errors='coerce')
        
        # 3. อัปเดตกลับไปที่ session_state เพื่อให้บันทึกถาวรในรอบถัดไป
        st.session_state.journal_data = df_journal.to_dict('records')
        # --- จบการ Data Migration ---
        with st.expander("📊 สถิติการเทรดรายเดือน", expanded=False):
            # 1. ส่วนคำนวณสถิติ
            stats_df = calculate_journal_stats(df_journal)
            
            # 2. ส่วนสรุป Metric 3 ค่าด้านบน (อิงจากช่วงเวลาที่เลือก)
            st.markdown("##### 🎯 สถิติการเทรดจริง & การปรับจุดคัทลอส (RR 2:1)")
            period = st.radio("ดูค่าเฉลี่ยย้อนหลัง:", ["3 เดือน", "6 เดือน", "1 ปี"], horizontal=True, key="stats_period")
            
            # กรองข้อมูลตามช่วงเวลา
            # กรองข้อมูลตามช่วงเวลา
            months_map = {"3 เดือน": 3, "6 เดือน": 6, "1 ปี": 12}
            cutoff_date = pd.Timestamp.now() - pd.DateOffset(months=months_map[period])
            
            # --- ส่วนแก้ไข: เพิ่มบรรทัดนี้ก่อนเรียกใช้ 'วันที่ขาย' ---
            if 'วันที่ขาย' not in df_journal.columns:
                df_journal['วันที่ขาย'] = df_journal['วันที่'] # ถ้าไม่มีให้ใช้ 'วันที่' เดิมไปก่อน
            
            # แปลงให้เป็น datetime ทุกครั้งก่อนใช้งาน
            df_journal['วันที่ขาย'] = pd.to_datetime(df_journal['วันที่ขาย'], errors='coerce')
            # ---------------------------------------------------
            
            df_period = df_journal[(df_journal['วันที่ขาย'] >= cutoff_date) & 
                          (df_journal['สถานะ'] == 'Closed (ขายแล้ว)')].copy()
            
            
            if not df_period.empty:
                # 1. ตรวจสอบและสร้างคอลัมน์วันที่ (ใช้ df_period)
                if 'วันที่ซื้อ' not in df_period.columns:
                    df_period['วันที่ซื้อ'] = df_period['วันที่']
                if 'วันที่ขาย' not in df_period.columns:
                    df_period['วันที่ขาย'] = df_period['วันที่']
                    
                # 2. แปลงเป็น datetime เสมอ
                df_period['วันที่ซื้อ'] = pd.to_datetime(df_period['วันที่ซื้อ'], errors='coerce')
                df_period['วันที่ขาย'] = pd.to_datetime(df_period['วันที่ขาย'], errors='coerce')
                
                # 3. คำนวณ Holding Days (ใช้ .clip เพื่อป้องกันค่าติดลบกรณีเลือกวันพลาด)
                df_period['Holding_Days'] = (df_period['วันที่ขาย'] - df_period['วันที่ซื้อ']).dt.days.clip(lower=0)
                
                # 4. แปลงตัวเลขสำหรับคำนวณ Metric (ใช้ชื่อคอลัมน์จริง)
                col_profit_loss = 'กำไร/ขาดทุน (บาท)'
                col_cost = 'ต้นทุน (บาท)'
                
                df_period[col_profit_loss] = pd.to_numeric(df_period[col_profit_loss], errors='coerce')
                df_period[col_cost] = pd.to_numeric(df_period[col_cost], errors='coerce')
                
                # คำนวณค่าจริง
                w_rate = (df_period[col_profit_loss] > 0).mean() * 100
                
                # คำนวณ Avg Profit / Avg Loss
                avg_profit = (df_period[df_period[col_profit_loss] > 0][col_profit_loss] / 
                              df_period[df_period[col_profit_loss] > 0][col_cost]).mean() * 100
                              
                avg_loss = (df_period[df_period[col_profit_loss] <= 0][col_profit_loss] / 
                            df_period[df_period[col_profit_loss] <= 0][col_cost]).mean() * 100
                
                loss_adj = (avg_profit / 2) * -1
                
                # แสดง Metric
                c1, c2, c3 = st.columns(3)
                c1.metric("Win Rate", f"{w_rate:.1f} %")
                c2.metric("Avg P/L", f"{avg_profit:.1f}% / {avg_loss:.1f}%")
                c3.metric("Rec. Cut Loss (RR 2:1)", f"{loss_adj:.1f} %")
            else:
                st.info("ไม่มีข้อมูลย้อนหลังในช่วงเวลานี้")

            st.markdown("---")
            
            # 3. ส่วนตารางสถิติรายเดือน
            if not stats_df.empty:
                years = sorted(stats_df.index.get_level_values('Year').unique())
                selected_year = st.selectbox("เลือกปีที่ต้องการดูสถิติ:", years, key="stats_year")
                
                year_data = stats_df.loc[selected_year]
                
                # ใส่ Style ให้สวยงาม
                styled_df = year_data.style.format({
                'Avg_Profit_Pct': '{:.2f} %',
                'Avg_Loss_Pct': '{:.2f} %',
                'Win_Rate': '{:.2f} %',
                'Max_Profit_Pct': '{:.2f} %',
                'Max_Loss_Pct': '{:.2f} %',
                'Avg_Days_Win': '{:.0f} วัน',     # แก้ตรงนี้: .0f คือทศนิยม 0 ตำแหน่ง
                'Avg_Days_Loss': '{:.0f} วัน'    # แก้ตรงนี้: .0f คือทศนิยม 0 ตำแหน่ง
            })
            st.table(styled_df)

 
########################################################################
# 3. ตารางประวัติ 
if st.session_state.journal_data:
    df_journal = pd.DataFrame(st.session_state.journal_data)
    df_journal['วันที่'] = pd.to_datetime(df_journal['วันที่'])             
    # แก้ไข Data Type วันที่ป้องกัน Error
    df_journal['วันที่'] = pd.to_datetime(df_journal['วันที่'])

    # เรียงลำดับ: Open ขึ้นก่อน, ตามด้วยวันที่ใหม่ล่าสุด
    df_journal['temp_sort'] = df_journal['สถานะ'].apply(lambda x: 0 if "Open" in x else 1)
    df_journal = df_journal.sort_values(by=['temp_sort', 'วันที่'], ascending=[True, False])
    df_journal = df_journal.drop(columns=['temp_sort'])

    with st.expander("📂 ดูประวัติการเทรดย้อนหลัง", expanded=True):
        # แบ่งหน้า (Pagination)
        items_per_page = 50
        total_pages = (len(df_journal) - 1) // items_per_page + 1
        page = st.number_input("หน้า:", min_value=1, max_value=total_pages, value=1)
        
        start_idx = (page - 1) * items_per_page
        df_display = df_journal.iloc[start_idx : start_idx + items_per_page]
        
        # แก้ไขข้อมูลผ่านตาราง
        edited_journal = st.data_editor(df_display, use_container_width=True)
        
        if st.button("💾 อัปเดตตารางหน้านี้"):
            # 1. บังคับแปลงตัวเลขเพื่อคำนวณต้นทุนใหม่
            edited_journal['ราคาหุ้นที่ซื้อ (บาท/หุ้น)'] = pd.to_numeric(edited_journal['ราคาหุ้นที่ซื้อ (บาท/หุ้น)'], errors='coerce')
            edited_journal['จำนวนหุ้นที่ซื้อ'] = pd.to_numeric(edited_journal['จำนวนหุ้นที่ซื้อ'], errors='coerce')
            edited_journal['ต้นทุน (บาท)'] = edited_journal['ราคาหุ้นที่ซื้อ (บาท/หุ้น)'] * edited_journal['จำนวนหุ้นที่ซื้อ']
            
            # 2. บังคับแปลงวันที่ให้เป็น String รูปแบบ YYYY-MM-DD เพื่อป้องกัน Error ตอนบันทึก JSON
            date_cols = ['วันที่', 'วันที่ซื้อ', 'วันที่ขาย']
            for col in date_cols:
                if col in edited_journal.columns:
                    # ใช้ errors='coerce' เพื่อให้ค่าที่ไม่ใช่วันที่กลายเป็น NaT และแปลงเป็น String
                    edited_journal[col] = pd.to_datetime(edited_journal[col], errors='coerce').dt.strftime('%Y-%m-%d')
            
            # 3. อัปเดตลง session_state และบันทึก
            st.session_state.journal_data = edited_journal.to_dict('records')
            save_journal()
            st.success("บันทึกข้อมูลเรียบร้อยแล้วครับ!")
        
        # ปุ่ม Export
        csv = df_journal.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 Export เป็นไฟล์ Excel (CSV)", data=csv, file_name="trading_journal.csv", mime="text/csv")

############################        
with tab_risk:
        st.markdown("#### 🚀 ระบบคำนวณ Risk Management & Position Sizing (ตามหลัก Minervini)")
        
        r_col1, r_col2 = st.columns([1, 1])
        with r_col1:
            total_cap = st.number_input("1. เงินทุนทั้งหมดในพอร์ตของพี่อ้ำ (บาท):", min_value=5000, value=100000, step=5000)
            risk_pct = st.slider("2. ความเสี่ยงสูงสุดที่ยอมขาดทุนต่อไม้ (% ของพอร์ต):", min_value=0.25, max_value=3.0, value=1.0, step=0.25, help="ตามหลักสากลแนะนำไม่เกิน 1%")
        
        with r_col2:
            sl_type = st.selectbox("3. เลือกเกณฑ์จุดตัดขาดทุน (Stop Loss):", [
                f"เส้น EMA 10 ({chart_combined['EMA10'].iloc[-1]:.2f} บาท)",
                f"เส้น EMA 20 ({chart_combined['EMA20'].iloc[-1]:.2f} บาท)",
                "กำหนดเป็นเปอร์เซ็นต์คงที่ (Fixed %)",
                "กำหนดราคาคัทด้วยตัวเอง (Manual Price)"
            ])
            
            latest_p = float(latest_price_single)
            if "EMA 10" in sl_type:
                sl_price = chart_combined['EMA10'].iloc[-1]
            elif "EMA 20" in sl_type:
                sl_price = chart_combined['EMA20'].iloc[-1]
            elif "กำหนดเป็นเปอร์เซ็นต์คงที่" in sl_type:
                fixed_sl_pct = st.slider("ระบุ % Stop Loss ที่ต้องการ:", min_value=2.0, max_value=12.0, value=7.0, step=0.5)
                sl_price = latest_p * (1 - (fixed_sl_pct / 100))
            else:
                sl_price = st.number_input("ระบุราคา Stop Loss ที่ต้องการคัท (บาท):", min_value=0.0, value=latest_p * 0.93, step=0.25)
        
        # ประมวลผลลัพธ์คุมเสี่ยง
        max_risk_money = total_cap * (risk_pct / 100)
        risk_per_share = latest_p - sl_price
        
        if risk_per_share <= 0:
            st.error("⚠️ ขอบเขตราคาผิดพลาด: ราคา Stop Loss ต้องต่ำกว่าราคาซื้อปัจจุบันครับพี่อ้ำ กรุณาปรับใหม่อีกครั้ง")
        else:
            shares_to_buy = int(max_risk_money / risk_per_share)
            total_buy_value = shares_to_buy * latest_p
            portfolio_exposure = (total_buy_value / total_cap) * 100
            actual_sl_pct = ((latest_p - sl_price) / latest_p) * 100
            
            st.markdown("##### 📊 ผลลัพธ์หน้าเทรดและขนาดไม้ที่เหมาะสม:")
            res_col1, res_col2, res_col3, res_col4 = st.columns(4)
            res_col1.metric(label="จำนวนหุ้นที่ควรซื้อ", value=f"{shares_to_buy:,} หุ้น")
            res_col2.metric(label="เงินลงทุนไม้ซื้อนี้ (Position Size)", value=f"{total_buy_value:,.2f} บาท", delta=f"{portfolio_exposure:.1f}% ของพอร์ต")
            res_col3.metric(label="ตั้ง Stop Loss ที่ราคา", value=f"{sl_price:.2f} บาท", delta=f"-{actual_sl_pct:.2f}%")
            res_col4.metric(label="หากแพ้จะเสียเงินสูงสุด", value=f"{max_risk_money:,.2f} บาท", delta="ปลอดภัยตามวินัยเทรด", delta_color="inverse")
#######################          
        st.markdown("---")
            def calculate_strategy(win_rate, profit_pct, loss_pct, trades=30, initial_capital=100000):
                # 1. ไม่ทบต้น (Fixed Risk: ลงทุนจำนวนเงินเท่าเดิมต่อไม้)
                fixed_capital = initial_capital
                fixed_balance = initial_capital
                results_fixed = []
                
                # 2. ทบต้น (Compounding: ทบเงินกำไร)
                comp_balance = initial_capital
                results_comp = []
                
                for i in range(trades):
                    # สุ่มผลลัพธ์ตาม Win Rate
                    win = np.random.rand() < win_rate
                    
                    # คำนวณแบบไม่ทบต้น
                    fixed_profit = (profit_pct * fixed_capital) if win else (-loss_pct * fixed_capital)
                    fixed_balance += fixed_profit
                    
                    # คำนวณแบบทบต้น
                    comp_profit = (profit_pct * comp_balance) if win else (-loss_pct * comp_balance)
                    comp_balance += comp_profit
                    
                return fixed_balance, comp_balance
            
            # สร้างตารางวิเคราะห์
            # --- ส่วนเพิ่ม: ฟังก์ชันวิเคราะห์ตารางเปรียบเทียบกลยุทธ์ ---
            def show_strategy_analysis():
                st.header("📊 ตารางเปรียบเทียบกลยุทธ์: ทบต้น vs ไม่ทบต้น")
            with st.expander("📊 กดเพื่อดูตารางเปรียบเทียบผลตอบแทน ทบต้น vs ไม่ทบต้น"):   
                # กำหนดค่าคงที่
                initial_cap = 100000
                loss_pct = 0.08  # Fix loss 8% ตามที่พี่อ้ำต้องการ
                trades = 30
                win_rates = [0.4, 0.5, 0.6]
                profit_pcts = [0.10, 0.12, 0.14, 0.16]
            
                data = []
                for wr in win_rates:
                    for pr in profit_pcts:
                        # คำนวณแบบไม่ทบต้น (Fixed Risk)
                        # กำไรสะสม = ทุน + (จำนวนครั้งที่ชนะ * กำไรต่อไม้) - (จำนวนครั้งที่แพ้ * ขาดทุนต่อไม้)
                        wins = trades * wr
                        losses = trades * (1 - wr)
                        fixed_profit = (wins * pr * initial_cap) - (losses * loss_pct * initial_cap)
                        
                        # คำนวณแบบทบต้น (Compounding)
                        comp_cap = initial_cap
                        for i in range(trades):
                            if np.random.rand() < wr:
                                comp_cap *= (1 + pr)
                            else:
                                comp_cap *= (1 - loss_pct)
                        
                        data.append({
                            "Win Rate": f"{int(wr*100)}%",
                            "Profit %": f"{int(pr*100)}%",
                            "ไม่ทบต้น (กำไร/ขาดทุน)": f"{fixed_profit:,.0f}",
                            "ทบต้น (เงินรวมสุดท้าย)": f"{comp_cap - initial_cap:,.0f}",
                            "กลยุทธ์ที่แนะนำ": "ทบต้น" if comp_cap > (initial_cap + fixed_profit) else "ไม่ทบต้น"
                        })
            
                df_viz = pd.DataFrame(data)
                st.table(df_viz)
                
                st.info("""
                **คำแนะนำ:** - ถ้า Win Rate ต่ำ (40%) ควรเน้น 'ไม่ทบต้น' เพื่อคุมความเสี่ยง
                - การทบต้นจะเริ่มทรงพลังเมื่อ Win Rate สูงขึ้น (50%+) และ Profit per trade มากกว่า Loss 1.5 เท่า
                """)
            
            # เรียกใช้ฟังก์ชันในหน้าแอป
            show_strategy_analysis()
            




