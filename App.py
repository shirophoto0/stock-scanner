# Import และ Setup
import streamlit as st
import pandas as pd
import yfinance as yf
import altair as alt
import numpy as np
import pandas as pd  
import plotly.graph_objects as go
import os
import json
import requests
import gspread
import seaborn as sns
import matplotlib.pyplot as plt
from oauth2client.service_account import ServiceAccountCredentials
from google.oauth2.service_account import Credentials
from plotly.subplots import make_subplots
# =============================================================
# 1. ฟังก์ชันจัดการ Google Sheets (Utility)
# =============================================================
def send_line_notify(message, token):
    url = "https://notify-api.line.me/api/notify"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"message": message}
    try:
        requests.post(url, headers=headers, data=payload)
    except Exception as e:
        print(f"Error sending Line Notify: {e}")

# ใส่ Token ของพี่อ้ำตรงนี้ครับ
LINE_TOKEN = "ใส่_TOKEN_ที่ก๊อปปี้มาไว้ตรงนี้"

def get_gsheet_client():
    scope = [
        "https://spreadsheets.google.com/feeds",
        'https://www.googleapis.com/auth/spreadsheets',
        "https://www.googleapis.com/auth/drive"
    ]
    
    try:
        # 1. เช็คจาก GitHub Actions (Environment Variable)
        if 'GOOGLE_APPLICATION_CREDENTIALS' in os.environ:
            creds_dict = json.loads(os.environ['GOOGLE_APPLICATION_CREDENTIALS'])
        # 2. เช็คจาก Streamlit Cloud (Secrets)
        else:
            # ใช้ dict() เพื่อแปลง st.secrets เป็น dictionary ธรรมดา
            creds_dict = dict(st.secrets["gcp_service_account"])
            
        # สร้าง Credentials ด้วยวิธีมาตรฐานที่รองรับทั้งคู่
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds)
        
    except Exception as e:
        # ถ้าพัง ให้ print ออกมาดูใน Log ของ GitHub
        print(f"Error ในการเชื่อมต่อ Google Sheets: {e}")
        raise e
# =============================================================
# 2. ฟังก์ชัน Load/Save ข้อมูล
# =============================================================
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
    sheet = client.open('MyStockData').worksheet('JournalData')
    
    # ล้างข้อมูลเดิมและเขียนใหม่ (Header + Data)
    sheet.clear()
    sheet.update([df_temp.columns.values.tolist()] + df_temp.fillna('').values.tolist())

def load_journal():
    try:
        client = get_gsheet_client()
        sheet = client.open('MyStockData').worksheet('JournalData')
        data = sheet.get_all_records()
        st.session_state.journal_data = data
    except Exception as e:
        st.error(f"ไม่สามารถโหลดข้อมูลจาก Google Sheets ได้: {e}")
        st.session_state.journal_data = []
        
def save_portfolio():
    try:
        if st.session_state.my_portfolio is None:
            st.session_state.my_portfolio = []
            
        client = get_gsheet_client()
        sheet = client.open('MyStockData').worksheet('PortfolioData')
        
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

# --- ฟังก์ชันโหลดพอร์ต (วางไว้คู่กัน) ---
def load_portfolio():
    try:
        client = get_gsheet_client()
        sheet = client.open('MyStockData').worksheet('PortfolioData')
        data = sheet.get_all_records()
        
        # ใส่บรรทัดนี้ไว้เช็ค (รันแล้วลองดูว่ามันแสดงข้อมูลอะไรออกมาที่หน้าเว็บไหม)
        # st.write("ข้อมูลที่ดึงมา:", data) 
        
        st.session_state.my_portfolio = data if data else []
    except Exception as e:
        st.error(f"โหลดพอร์ตไม่สำเร็จ: {e}")
        st.session_state.my_portfolio = []
        
def get_current_portfolio_value():
    # ฟังก์ชันนี้ดึงราคาปัจจุบันของหุ้นทุกตัวใน st.session_state.my_portfolio
    total_market_value = 0
    for item in st.session_state.my_portfolio:
        ticker = item['หุ้น']
        shares = item['shares']
        # ดึงราคาตลาดปัจจุบัน (Real-time)
        try:
            m_price = yf.Ticker(f"{ticker}.BK").history(period="1d")['Close'].iloc[-1]
        except:
            m_price = item['avg_price'] # ถ้าดึงไม่ได้ ให้ใช้ราคาต้นทุน
        total_market_value += (shares * m_price)
    return total_market_value

def save_to_gsheet(df):
    print("DEBUG: กำลังเชื่อมต่อ Google Sheets...")
    client = get_gsheet_client()
    
    # 1. ใช้ Key (ID) แทนชื่อไฟล์ เพื่อป้องกันความผิดพลาดกรณีเปลี่ยนชื่อไฟล์
    # ให้เอาตัวอักษรยาวๆ ใน URL ของ Google Sheets มาใส่แทนตรงนี้ครับ
    spreadsheet_id = '1moD7gjKnnLXDvCTfwVVhBmDwo5t0c7emErGbtJtGEWU'
    
    print("DEBUG: กำลังเข้าถึง Worksheet...")
    sheet = client.open_by_key(spreadsheet_id).worksheet('StockData')
    
    # 2. ล้างข้อมูลเก่า
    print("DEBUG: ล้างข้อมูลเดิม...")
    sheet.clear()
    
    # 3. เตรียมข้อมูล (Header + ข้อมูล)
    data_to_write = [df.columns.values.tolist()] + df.values.tolist()
    
    # 4. เขียนข้อมูลใหม่โดยระบุตำแหน่งเริ่มที่ A1
    # คำสั่ง update ใน gspread รุ่นใหม่ต้องใส่ 'A1' บอกจุดเริ่มด้วยครับ
    print("DEBUG: กำลังเขียนข้อมูลลง Sheet...")
    sheet.update('A1', data_to_write)
    
    print("DEBUG: บันทึกข้อมูลเสร็จสิ้น!")
# 2. ฟังก์ชันอเนกประสงค์ (เอามาแทรกตรงนี้)
@st.cache_data(ttl=600)
def load_data(sheet_name):
    client = get_gsheet_client()
    sheet = client.open('MyStockData').worksheet(sheet_name)
    data = sheet.get_all_records()
    return pd.DataFrame(data)

def save_data(df, sheet_name):
    client = get_gsheet_client()
    sheet = client.open('MyStockData').worksheet(sheet_name)
    sheet.clear()
    sheet.update([df.columns.values.tolist()] + df.values.tolist())
    
def save_cash_balance(amount):
    try:
        client = get_gsheet_client()
        sheet = client.open('MyStockData').worksheet('CashFlow')
        sheet.update('D2', [[amount]]) # เขียนเงินสดลงเซลล์ D2
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการบันทึกเงินสด: {e}")

def load_cash_balance():
    try:
        client = get_gsheet_client()
        sheet = client.open('MyStockData').worksheet('CashFlow')
        val = sheet.acell('D2').value
        if val is None or val == "":
            st.warning("เซลล์ D2 ว่างเปล่า ระบบใช้ 100,000 เป็นค่าเริ่มต้น")
            return 100000.0
        return float(val)
    except Exception as e:
        st.error(f"โหลดเงินสดจาก Sheets ไม่ได้: {e}")
        return 100000.0 # ถ้าพังจริงๆ ก็ใช้ 100,000 ไปก่อน
        
def log_cash_transaction(date, trans_type, amount, note):
    try:
        client = get_gsheet_client()
        sheet = client.open('MyStockData').worksheet('CashFlow')
        
        # เตรียมข้อมูลที่จะบันทึก (Date, Type, Amount, Note)
        row_data = [str(date), trans_type, amount, note]
        
        # เพิ่มแถวใหม่ต่อท้ายข้อมูลเดิม
        sheet.append_row(row_data)
        st.toast("บันทึกรายการเงินสดเรียบร้อย!", icon="💰")
    except Exception as e:
        st.error(f"บันทึกรายการเงินสดไม่สำเร็จ: {e}")
        
def load_total_cash_balance():
    try:
        client = get_gsheet_client()
        sheet = client.open('MyStockData').worksheet('CashFlow')
        df = pd.DataFrame(sheet.get_all_records())
        
        if not df.empty:
            # รวมยอด Amount ทั้งหมด
            return float(df['Amount'].sum())
        return 69102.44 # ถ้าไม่มีข้อมูลให้ใช้ยอดเริ่มต้น
    except:
        return 69102.44
        
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

def get_equity_curve_data():
    # 1. เตรียมข้อมูล Journal
    if "journal_data" not in st.session_state or not st.session_state.journal_data:
        return pd.DataFrame()
    
    df_j = pd.DataFrame(st.session_state.journal_data)
    # ทำความสะอาดชื่อคอลัมน์ (ตัดช่องว่างหน้าหลัง)
    df_j.columns = df_j.columns.str.strip()
    
    # ตรวจสอบชื่อคอลัมน์จริง (ใช้บรรทัดนี้ Debug ถ้ายัง Error)
    # st.write("Columns found:", df_j.columns.tolist())
    
    # เปลี่ยนชื่อคอลัมน์ให้ตรงกับที่เราเรียกใช้
    # หากใน Sheet พี่อ้ำเขียนว่า 'กำไร/ขาดทุน' ให้ใช้ชื่อนั้นครับ
    if 'กำไร/ขาดทุน' in df_j.columns:
        df_j = df_j.rename(columns={'กำไร/ขาดทุน': 'PnL'})
    elif 'กำไร/ขาดทุน (บาท)' in df_j.columns:
        df_j = df_j.rename(columns={'กำไร/ขาดทุน (บาท)': 'PnL'})
    
    df_j['วันที่ขาย'] = pd.to_datetime(df_j['วันที่ขาย'], errors='coerce')

    # 2. เตรียมข้อมูล CashFlow
    client = get_gsheet_client()
    sheet = client.open('MyStockData').worksheet('CashFlow')
    df_cash = pd.DataFrame(sheet.get_all_records())
    df_cash.columns = df_cash.columns.str.strip()
    df_cash['Date'] = pd.to_datetime(df_cash['Date'], errors='coerce')
    
    # 3. Filter วันที่
    start_date = pd.Timestamp('2026-04-01')
    df_j = df_j[df_j['วันที่ขาย'] >= start_date].copy()
    df_cash = df_cash[df_cash['Date'] >= start_date].copy()
    
    # 4. คำนวณ
    daily_pnl = df_j.groupby('วันที่ขาย')['PnL'].sum().cumsum().reset_index()
    daily_pnl.columns = ['Date', 'Cumulative_PnL']
    
    daily_cash = df_cash.groupby('Date')['Amount'].sum().cumsum().reset_index()
    daily_cash.columns = ['Date', 'Net_Cash_In']
    
    # 5. รวมตาราง
    df_equity = pd.merge(daily_pnl, daily_cash, on='Date', how='outer').fillna(0)
    initial_balance = 69102.44 
    
    df_equity['Cash_Base'] = df_equity['Cumulative_PnL'] + df_equity['Net_Cash_In'] + initial_balance
    
    # 6. คำนวณ M2M
    current_market_val = get_total_market_value()
    # หัก Cumulative PnL ออกเพื่อให้เหลือเงินสดจริง แล้วบวกมูลค่าหุ้นปัจจุบัน
    df_equity['Market_To_Market'] = (df_equity['Cash_Base'] - df_equity['Cumulative_PnL']) + current_market_val
    
    return df_equity
    
def get_total_market_value():
    """คำนวณมูลค่าหุ้นทั้งหมดที่ถืออยู่ ณ ราคาปัจจุบัน"""
    total_val = 0
    if "my_portfolio" in st.session_state:
        for item in st.session_state.my_portfolio:
            ticker = item['หุ้น']
            shares = float(item['shares'])
            try:
                # ดึงราคาปิดล่าสุด
                m_price = yf.Ticker(f"{ticker}.BK").history(period="1d")['Close'].iloc[-1]
            except:
                m_price = float(item['avg_price']) # ถ้าดึงไม่ได้ ให้ใช้ต้นทุนไปก่อน
            total_val += (shares * m_price)
    return total_val
    
def plot_dual_equity_curve(df_equity):
    # df_equity ต้องมีคอลัมน์: 'Date', 'Market_To_Market', 'Cash_Base'
    
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # เส้นที่ 1: Market to Market (แกนซ้าย)
    fig.add_trace(
        go.Scatter(x=df_equity['Date'], y=df_equity['Market_To_Market'], name="มูลค่าพอร์ตจริง (M2M)", line=dict(color="#00CC96", width=2)),
        secondary_y=False,
    )

    # เส้นที่ 2: Cash Base (แกนขวา)
    fig.add_trace(
        go.Scatter(x=df_equity['Date'], y=df_equity['Cash_Base'], name="เงินสด+กำไรที่ขายแล้ว", line=dict(color="#636EFA", width=2, dash='dot')),
        secondary_y=True,
    )

    # ปรับแต่ง Layout
    fig.update_layout(title_text="เปรียบเทียบพอร์ต: M2M vs Cash Base")
    fig.update_yaxes(title_text="มูลค่าพอร์ตจริง (฿)", secondary_y=False)
    fig.update_yaxes(title_text="เงินสดสะสม (฿)", secondary_y=True)
    
    st.plotly_chart(fig, use_container_width=True)
    
def get_pe_ratio(ticker_obj):
    try:
        # พยายามดึงจาก info
        pe = ticker_obj.info.get('trailingPE')
        if pe is None:
            # ถ้าไม่มี trailingPE ลองหา forwardPE แทน
            pe = ticker_obj.info.get('forwardPE', 0)
        return pe if pe is not None else 0
    except:
        return 0   
        
def append_to_gsheet(data_dict, sheet_name):
    try:
        client = get_gsheet_client()
        sheet = client.open('MyStockData').worksheet("TradingPlan")
        # ดึงค่าจาก Dictionary มาทำเป็น List เพื่อ append
        row_values = [
            data_dict.get('Ticker'),
            data_dict.get('Entry_Price'),
            data_dict.get('Stop_Loss'),
            data_dict.get('Take_Profit'),
            data_dict.get('Image_URL'),
            data_dict.get('Timestamp')
        ]
        sheet.append_row(row_values)
        return True
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการบันทึก: {e}")
        return False
        
def get_latest_prices(tickers):
    prices = {}
    for t in tickers:
        # ตัดช่องว่างทั้งหมด และบังคับให้เป็นตัวพิมพ์ใหญ่
        clean_t = t.strip().upper() 
        symbol = f"{clean_t}.BK" if not clean_t.endswith(".BK") else clean_t
        
        try:
            # เพิ่ม timeout เพื่อป้องกันการค้าง
            df = yf.download(symbol, period="1d", progress=False, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
            if not df.empty and 'Close' in df.columns:
                prices[clean_t] = float(df['Close'].iloc[-1])
            else:
                prices[clean_t] = 0.0
        except Exception as e:
            prices[clean_t] = 0.0
    return prices
    
# =============================================================
# ส่วนเร่ิมต้นของ file
# =============================================================

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

# ตั้งค่าหน้าจอ
st.set_page_config(layout="wide")

st.title("📈 แอปพลิเคชันวิเคราะห์หุ้นไทย (Mark Minervini Style - RS vs SET Index)")
st.write("ระบบสแกนหุ้นกลุ่ม SET100 พร้อมกราฟเปรียบเทียบความแข็งแกร่งกับตลาดภาพรวม (SET Index)")

# จัดการ Session State เพื่อเก็บชื่อหุ้นที่เลือกไว้กลางระบบ
if "selected_ticker" not in st.session_state:
    st.session_state.selected_ticker = "KBANK"

# =============================================================
# 3. ฟังก์ชันคำนวณทางเทคนิคและสแกนหุ้น
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
    "A5.BK", "AAI.BK", "AAV.BK", "ABM.BK", "ACC.BK", "ACE.BK", "ACG.BK", "ADB.BK", "ADD.BK", "ADVANC.BK",
    "ADVICE.BK", "AE.BK", "AEONTS.BK", "AF.BK", "AGE.BK", "AH.BK", "AHC.BK", "AI.BK", "AIE.BK", "AIT.BK",
    "AJ.BK", "AJA.BK", "AKP.BK", "AKR.BK", "ALLA.BK", "ALLY.BK", "ALPHAX.BK", "ALT.BK", "ALUCON.BK", "AMA.BK",
    "AMANAH.BK", "AMARC.BK", "AMATA.BK", "AMR.BK", "ANAN.BK", "ANI.BK", "AOT.BK", "AP.BK", "APCO.BK", "APCS.BK",
    "APO.BK", "APP.BK", "APURE.BK", "AQUA.BK", "ARIN.BK", "ARIP.BK", "ARROW.BK", "AS.BK", "ASAP.BK", "ASEFA.BK",
    "ASIA.BK", "ASIAN.BK", "ASIMAR.BK", "ASK.BK", "ASN.BK", "ASP.BK", "ASW.BK", "ATP30.BK", "AU.BK", "AUCT.BK",
    "AURA.BK", "AWC.BK", "B.BK", "BA.BK", "BAFS.BK", "BAM.BK", "BANPU.BK", "BAY.BK", "BBGI.BK", "BBIK.BK",
    "BBL.BK", "BC.BK", "BCH.BK", "BCP.BK", "BCPG.BK", "BCT.BK", "BDMS.BK", "BE8.BK", "BEAUTY.BK", "BEC.BK",
    "BEM.BK", "BGC.BK", "BGRIM.BK", "BH.BK", "BIS.BK", "BIZ.BK", "BJC.BK", "BJCHI.BK", "BKD.BK", "BLAND.BK",
    "BLC.BK", "BM.BK", "BOL.BK", "BPP.BK", "BRI.BK", "BRR.BK", "BSBM.BK", "BTG.BK", "BTS.BK", "BWG.BK", "BYD.BK",
    "CBG.BK", "CCET.BK", "CCP.BK", "CGD.BK", "CH.BK", "CHAYO.BK", "CHEWA.BK", "CHG.BK", "CHO.BK", "CHOW.BK",
    "CI.BK", "CIG.BK", "CIMBT.BK", "CIVIL.BK", "CK.BK", "CKP.BK", "CM.BK", "CMC.BK", "CMO.BK", "CMR.BK",
    "CNT.BK", "COLOR.BK", "COM7.BK", "CPALL.BK", "CPF.BK", "CPI.BK", "CPN.BK", "CPT.BK", "CRC.BK", "CRD.BK",
    "CSC.BK", "CSP.BK", "CSS.BK", "CV.BK", "CWT.BK", "D.BK", "DCC.BK", "DDD.BK", "DELTA.BK", "DEMCO.BK",
    "DEXON.BK", "DHOUSE.BK", "DITTO.BK", "DMT.BK", "DOHOME.BK", "DOD.BK", "DRT.BK", "DTCENT.BK", "DTCI.BK",
    "EA.BK", "EASTW.BK", "EE.BK", "EFORL.BK", "EKH.BK", "EMC.BK", "EP.BK", "ERW.BK", "ESTAR.BK", "ETC.BK",
    "ETE.BK", "EURO.BK", "FANCY.BK", "FMT.BK", "FNS.BK", "FORTH.BK", "FPI.BK", "FSMART.BK", "FSS.BK", "FTE.BK",
    "GABLE.BK", "GBX.BK", "GC.BK", "GCAP.BK", "GEL.BK", "GENCO.BK", "GFPT.BK", "GGC.BK", "GLAND.BK", "GLOBAL.BK",
    "GLOCON.BK", "GPI.BK", "GPSC.BK", "GRAMMY.BK", "GREEN.BK", "GSC.BK", "GTB.BK", "GULF.BK", "GUNKUL.BK", "GVREIT.BK",
    "HANA.BK", "HARN.BK", "HENG.BK", "HFT.BK", "HL.BK", "HMPRO.BK", "HTC.BK", "HTECH.BK", "HUMAN.BK", "HYDRO.BK",
    "ICC.BK", "ICHI.BK", "ICN.BK", "IFEC.BK", "IFS.BK", "IHL.BK", "III.BK", "ILINK.BK", "IMH.BK", "IND.BK",
    "INET.BK", "INGRS.BK", "INOX.BK", "INSURE.BK", "INTUCH.BK", "IRC.BK", "IRCP.BK", "IT.BK", "ITC.BK", "ITEL.BK",
    "ITD.BK", "IVL.BK", "J.BK", "JAS.BK", "JCK.BK", "JCKH.BK", "JMART.BK", "JMT.BK", "JSP.BK", "JTS.BK",
    "K.BK", "KAMART.BK", "KBANK.BK", "KBS.BK", "KC.BK", "KCE.BK", "KEX.BK", "KGI.BK", "KHC.BK", "KJL.BK",
    "KKP.BK", "KSL.BK", "KTB.BK", "KTC.BK", "KTIS.BK", "KWC.BK", "KWM.BK", "L&E.BK", "LALIN.BK", "LANNA.BK",
    "LEO.BK", "LH.BK", "LHK.BK", "LPN.BK", "LRH.BK", "LST.BK", "M.BK", "MACO.BK", "MAJOR.BK", "MAKRO.BK",
    "MC.BK", "MCA.BK", "MCOT.BK", "MCS.BK", "MDX.BK", "MEGA.BK", "META.BK", "MFC.BK", "MGT.BK", "MICRO.BK",
    "MINT.BK", "MITSIB.BK", "MJD.BK", "MK.BK", "ML.BK", "MOSHI.BK", "MTC.BK", "NCAP.BK", "NCH.BK", "NER.BK",
    "NETBAY.BK", "NEX.BK", "NKI.BK", "NNCL.BK", "NOBLE.BK", "NOK.BK", "NRF.BK", "NUSA.BK", "NVD.BK", "NYT.BK",
    "OCC.BK", "OGC.BK", "OISHI.BK", "OR.BK", "ORI.BK", "OSP.BK", "OTO.BK", "PACE.BK", "PAF.BK", "PAP.BK",
    "PCSGH.BK", "PDG.BK", "PERM.BK", "PF.BK", "PG.BK", "PHOL.BK", "PICO.BK", "PIN.BK", "PIS.BK", "PLANB.BK",
    "PLAT.BK", "PLE.BK", "PM.BK", "PMC.BK", "PMP.BK", "PPP.BK", "PPPM.BK", "PR9.BK", "PREB.BK", "PRG.BK",
    "PRINC.BK", "PRM.BK", "PROEN.BK", "PROS.BK", "PSH.BK", "PSL.BK", "PT.BK", "PTC.BK", "PTG.BK", "PTL.BK",
    "PTT.BK", "PTTEP.BK", "PTTGC.BK", "PYLON.BK", "QH.BK", "QLT.BK", "QTC.BK", "RATCH.BK", "RBF.BK", "RCL.BK",
    "RICHY.BK", "RJH.BK", "RML.BK", "ROJNA.BK", "RPC.BK", "RPH.BK", "RS.BK", "RSP.BK", "S.BK", "S11.BK",
    "SABINA.BK", "SAK.BK", "SAPPE.BK", "SAT.BK", "SAWAD.BK", "SC.BK", "SCB.BK", "SCC.BK", "SCCC.BK", "SCGP.BK",
    "SCI.BK", "SCP.BK", "SDC.BK", "SEAFCO.BK", "SEAOIL.BK", "SECURE.BK", "SELIC.BK", "SENA.BK", "SFLEX.BK", "SGP.BK",
    "SHR.BK", "SIRI.BK", "SIS.BK", "SITHAI.BK", "SJWD.BK", "SKN.BK", "SKE.BK", "SKR.BK", "SNNP.BK", "SNP.BK",
    "SORKON.BK", "SPALI.BK", "SPC.BK", "SPCG.BK", "SPG.BK", "SPI.BK", "SPRC.BK", "SR.BK", "SSC.BK", "SSF.BK",
    "SSP.BK", "SSSC.BK", "STANLY.BK", "STEC.BK", "STGT.BK", "STPI.BK", "SUSCO.BK", "SUTHA.BK", "SVI.BK",
    "SVOA.BK", "SVT.BK", "SYMC.BK", "SYNEX.BK", "SYNTEC.BK", "TACC.BK", "TAE.BK", "TAKUNI.BK", "TASCO.BK", "TCAP.BK",
    "TCMC.BK", "TCOAT.BK", "TEAM.BK", "TEGH.BK", "TFFIF.BK", "TFG.BK", "TFMAMA.BK", "TGE.BK", "TGH.BK", "TIDLOR.BK",
    "TIPH.BK", "TISCO.BK", "TKN.BK", "TKS.BK", "TKT.BK", "TLI.BK", "TM.BK", "TMD.BK", "TMILL.BK", "TMT.BK",
    "TNP.BK", "TOA.BK", "TOG.BK", "TOP.BK", "TPA.BK", "TPBI.BK", "TPIPL.BK", "TPIPP.BK", "TPOLY.BK", "TPP.BK",
    "TRC.BK", "TRU.BK", "TRUBB.BK", "TRUE.BK", "TSC.BK", "TSE.BK", "TSI.BK", "TSTH.BK", "TTA.BK", "TTB.BK",
    "TTCL.BK", "TTI.BK", "TTW.BK", "TU.BK", "TVO.BK", "TWPC.BK", "UAC.BK", "UBE.BK", "UBIS.BK", "UEC.BK",
    "UKEM.BK", "UMI.BK", "UNIQ.BK", "UP.BK", "UPF.BK", "UPL.BK", "UPOIC.BK", "UV.BK", "UVAN.BK", "VARO.BK",
    "VGI.BK", "VIBHA.BK", "VIH.BK", "VL.BK", "VNG.BK", "VPO.BK", "W.BK", "WACOAL.BK", "WAVE.BK", "WGE.BK",
    "WHA.BK", "WHART.BK", "WICE.BK", "WIIK.BK", "WIN.BK", "WORK.BK", "WP.BK", "WPH.BK", "XO.BK", "YGG.BK",
    "ZEN.BK", "ZIGA.BK", "EPG.BK", "GTV.BK", "MRDIYT.BK"
]

# =============================================================
# 4. ดึงข้อมูลและคำนวณฐานข้อมูลกลุ่ม SET100 โค้ดส่วนสแกนหุ้น (load_and_calculate_stock_data) และการทำ Filter
# ============================================================
@st.cache_data(ttl=3600)
def load_from_gsheet():
    try:
        client = get_gsheet_client()
        sheet = client.open('MyStockData').worksheet('StockData')
        data = sheet.get_all_records()
        
        if not data:
            st.warning("ไม่มีข้อมูลใน Google Sheet ครับ")
            return None
            
        # ดึงข้อมูลออกมาเป็น DataFrame
        df = pd.DataFrame(data)
        
        # ล้างชื่อคอลัมน์ (เผื่อมีช่องว่างติดมา)
        df.columns = df.columns.str.strip()
        
        # แปลงคอลัมน์ตัวเลขให้เป็นตัวเลขจริงๆ
        numeric_cols = ['ราคาล่าสุด', 'RSI_14', 'RS_Line', 'PE_Ratio', 'ปันผล_%']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        return df

    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการดึงข้อมูล: {e}")
        return None
        
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
            status_text.text(f"กำลังคำนวณสัญญาณหุ้น: {ticker} ({i+1}/{total})")
            progress_bar.progress((i + 1) / total)
            
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2y")
            
            # ตรวจสอบว่ามีข้อมูลพอหรือไม่
            if hist.empty or len(hist) < 200: 
                continue
                
            if hist.index.tz is not None:
                hist.index = hist.index.tz_localize(None)
            
            latest_price = hist['Close'].iloc[-1]
            combined = hist[['Open', 'High', 'Low', 'Close']].join(hist_market_all, how='inner')
            
            if combined.empty or len(combined) < 2:
                continue
                
            combined['RSI'] = calculate_rsi(combined['Close'], period=14)
            current_rsi = combined['RSI'].iloc[-1]
            
            # คำนวณ RS_Line
            base_stock = combined['Close'].iloc[0]
            stock_perf = ((combined['Close'] - base_stock) / base_stock) * 100
            base_market = combined['Market_Close'].iloc[0]
            market_perf = ((combined['Market_Close'] - base_market) / base_market) * 100
            combined['RS_Line'] = stock_perf - market_perf
            current_rs_val = combined['RS_Line'].iloc[-1]
            
            # คำนวณสถานะเส้น RS
            is_rs_above_zero = current_rs_val > 0
            days_above_zero = 0
            days_below_zero = 0
            
            # คำนวณค่าทางเทคนิคแบบปลอดภัย
            high_3m = combined['High'].iloc[:-1].tail(60).max()
            high_6m = combined['High'].iloc[:-1].tail(120).max()
            high_52w = combined['High'].iloc[:-1].tail(250).max()

            # 1. หาวันที่ล่าสุด (วันปัจจุบันที่รันสแกน)
            today_date = combined.index[-1]
            
            # 2. คำนวณจำนวนวันสำหรับ 3 Month High
            # หาข้อมูลช่วง 3 เดือนที่ผ่านมา
            df_3m = combined['High'].tail(60)
            # หาว่า High สูงสุดเกิดขึ้นที่ตำแหน่งไหน (วันไหน)
            last_high_3m_date = df_3m[df_3m == high_3m].index[-1]
            days_3m = (today_date - last_high_3m_date).days
            
            # 3. คำนวณจำนวนวันสำหรับ 6 Month High
            df_6m = combined['High'].tail(120)
            last_high_6m_date = df_6m[df_6m == high_6m].index[-1]
            days_6m = (today_date - last_high_6m_date).days
            
            # 4. คำนวณจำนวนวันสำหรับ 52 Week High
            df_52w = combined['High'].tail(250)
            last_high_52w_date = df_52w[df_52w == high_52w].index[-1]
            days_52w = (today_date - last_high_52w_date).days
            
            # คำนวณปันผลจากข้อมูลจริง (ไม่ใช้ .info)
            dividends_history = stock.dividends
            total_div_1y = 0.0
            if not dividends_history.empty:
                last_year = pd.Timestamp.now(tz='UTC') - pd.Timedelta(days=365)
                div_1y = dividends_history[dividends_history.index.tz_localize(None) > last_year.replace(tzinfo=None)]
                total_div_1y = div_1y.sum()
            
            calc_div_yield = ((total_div_1y / latest_price) * 100) if total_div_1y > 0 else 0.0
            
            # ดึง PE ด้วยวิธีที่ปลอดภัย (ไม่ใช้ .info)
            pe_ratio = get_pe_ratio(stock)
            
            # รวมผลลัพธ์
            stock_list.append({
                'Ticker': ticker.replace('.BK', ''),
                'ราคาล่าสุด': round(latest_price, 2),
                'RSI_14': round(current_rsi, 2) if not pd.isna(current_rsi) else 0,
                'RS_Line': round(current_rs_val, 2),
                'PE_Ratio': round(pe_ratio, 2) if pe_ratio else 0,
                'ปันผล_%': round(calc_div_yield, 2),
                'Is_RS_Above_0': is_rs_above_zero,
                'ตัดเส้น0ขึ้นมาแล้ว(วัน)': days_above_zero,
                'อยู่ใต้เส้น0มาแล้ว(วัน)': days_below_zero,
                'Is_3M_High': latest_price >= (high_3m * 0.95),
                'Is_6M_High': latest_price >= (high_6m * 0.95),
                'Is_52W_High': latest_price >= (high_52w * 0.95),
                'New_High_3M_มาแล้ว(วัน)': days_3m,
                'New_High_6M_มาแล้ว(วัน)': days_6m,
                'New_High_52W_มาแล้ว(วัน)': days_52w,
            })
            
            # ใส่หน่วงเวลาเล็กน้อยเพื่อป้องกันการถูกบล็อก
            time.sleep(0.1)
            
        except Exception:
            continue
            
    progress_bar.empty()
    status_text.empty()
    return pd.DataFrame(stock_list)


###################################################################
# # --- ฟังก์ชัน Main ---
###################################################################
def save_to_gsheet(df):
    client = get_gsheet_client()
    # ใช้ ID แทนชื่อไฟล์เพื่อความชัวร์ (เปลี่ยนเลข ID เป็นของพี่อ้ำนะครับ)
    sheet = client.open_by_key('1moD7gjKnnLXDvCTfwVVhBmDwo5t0c7emErGbtJtGEWU').worksheet('StockData')
    
    sheet.clear()
    # เขียนข้อมูลโดยระบุตำแหน่ง A1
    data_to_write = [df.columns.values.tolist()] + df.values.tolist()
    sheet.update('A1', data_to_write)
    print("GitHub Actions: บันทึกข้อมูลลง Google Sheet สำเร็จ!")

def highlight_rsi_zones(row):
    if row['RSI_14'] >= 65.0:
        return ['background-color: #fce4d6; color: black'] * len(row)
    elif 30.0 <= row['RSI_14'] <= 45.0:
        return ['background-color: #e2f0d9; color: black'] * len(row)
    return [''] * len(row)

#####################################
# Def Main ส่วนครอบ code ทั้งหมด
######################################
st.set_page_config(layout="wide")
def main():
    # --- กรณีรันผ่าน GitHub Actions ---
    if 'GOOGLE_APPLICATION_CREDENTIALS' in os.environ:
        print("GitHub Mode: กำลังเริ่มสแกน...")
        df_new = load_and_calculate_stock_data()
        save_to_gsheet(df_new)
        print("GitHub Mode: บันทึกข้อมูลสำเร็จ")
        return # จบการทำงาน ไม่ต้องแสดง UI

    # --- กรณีรันผ่านหน้าเว็บ Streamlit ---
    st.title("📈 แอปพลิเคชันวิเคราะห์หุ้นไทย")
    
    # ดึงข้อมูลจาก Sheets หรือ Yahoo
    if st.button("🔄 อัปเดตข้อมูลใหม่ (ดึงจาก Yahoo)"):
        with st.spinner("กำลังดึงข้อมูล..."):
            df_all_stocks = load_and_calculate_stock_data()
            save_to_gsheet(df_all_stocks)
    else:
        try:
            df_all_stocks = load_from_gsheet()
            st.success("✅ โหลดข้อมูลจาก Google Sheets เรียบร้อย")
        except:
            st.warning("⚠️ ไม่พบข้อมูลใน Sheet กำลังโหลดใหม่...")
            df_all_stocks = load_and_calculate_stock_data()
            
            # แสดงตาราง
            st.dataframe(filtered_df, use_container_width=True)
        
        ################################
        # 1. Slidebar (ตัวกรอง)
        ################################
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
            
        # 3. แสดงผลตารางและกราฟ
        # ... (เอาโค้ดส่วนแสดงผล st.dataframe และ st.plotly_chart มาใส่ตรงนี้) ...
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
        # 7. ผลลัพธ์การสแกน (ใช้ filtered_df ที่กรองผ่าน Sidebar มาแล้ว)
        # =============================================================
        
        # 1. เช็คข้อมูลจาก Sidebar (ถ้าไม่มีให้ใช้ df_all_stocks)
        df_scan = filtered_df.copy() if 'filtered_df' in locals() else df_all_stocks.copy()

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
                    
        # 4. ส่วนของ Tabs ต่างๆ
        # ... (เอาโค้ด tab_dashboard, tab_risk, tab_portfolio ของพี่อ้ำมาใส่) ...
        ##########################
        # 8.แท็บข้อมูล
        ##############################  
        st.markdown("---") # เส้นคั่น เพื่อแยกส่วนกับตารางด้านบนให้ชัด
        st.subheader("🛠 ระบบจัดการข้อมูลและวิเคราะห์พอร์ต")
        
        # 1. สร้าง Tabs (จัดรวม แผนและ Alert ไว้ใน tab เดียวกัน)
        tab_dashboard, tab_risk, tab_portfolio, tab_journal, tab_plan = st.tabs([
            "📈 Dashboard", "🧮 คำนวณความเสี่ยง", "📊 พอร์ตโฟลิโอ", "📖 สมุดบันทึก", "📝 แผนและ Alert"
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
                    
                    ####################
                    # Equity Curve 
                    st.subheader("📈 Equity Curve")
                
                    df_equity = get_equity_curve_data()
            
                    if not df_equity.empty:
                        # พล็อตกราฟ
                        plot_dual_equity_curve(df_equity)
                        
                        # คำนวณค่าสถิติ
                        max_m2m = df_equity['Market_To_Market'].max()
                        cur_m2m = df_equity['Market_To_Market'].iloc[-1]
                        max_cash = df_equity['Cash_Base'].max()
                        cur_cash = df_equity['Cash_Base'].iloc[-1]
                        
                        # แสดง Metric 4 ช่อง
                        st.markdown("##### 📊 สรุปสถิติพอร์ต")
                        col1, col2 = st.columns(2)
                        col1.metric("มูลค่าพอร์ตสูงสุด (M2M)", f"{max_m2m:,.0f} ฿")
                        col2.metric("มูลค่าพอร์ตปัจจุบัน (M2M)", f"{cur_m2m:,.0f} ฿")
                        
                        col3, col4 = st.columns(2)
                        col3.metric("เงินสด+กำไรสูงสุด", f"{max_cash:,.0f} ฿")
                        col4.metric("เงินสด+กำไรปัจจุบัน", f"{cur_cash:,.0f} ฿")
                        
                    else:
                        st.info("สะสมข้อมูลการเทรดสักพัก เพื่อสร้างเส้น Equity Curve ครับ")
        #########################            
        with tab_portfolio:
            st.markdown("#### 💼 ระบบบันทึกพอร์ตโฟลิโอส่วนตัว")
            
            # 1. จัดการเงินสด (แก้ไขด้วยตัวเองได้ตลอดเวลา)
            if "cash_balance" not in st.session_state:
                st.session_state.cash_balance = load_cash_balance()
                
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
                with st.form("portfolio_journal_form", clear_on_submit=True):
                    col1, col2 = st.columns(2)
                    
                    portfolio_stocks = [item['หุ้น'] for item in st.session_state.my_portfolio] if "my_portfolio" in st.session_state else []
                    
                    with col1:
                        options = ["  "] + portfolio_stocks
                        select_ticker = st.selectbox("เลือกหุ้นจากพอร์ต:", options)
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
        
                        # 1. จัดการข้อมูล Portfolio
                        found_idx = next((i for i, item in enumerate(st.session_state.my_portfolio) if item['หุ้น'] == ticker_upper), -1)
                        
                        if "ซื้อ" in p_type:
                            # บันทึกประวัติเงินสด (จ่ายออก)
                            log_cash_transaction(
                                date=str(p_buy_date),
                                trans_type="ซื้อหุ้น " + ticker_upper,
                                amount=-(total_val + p_comm),
                                note=f"ซื้อ {p_qty} หุ้น ที่ราคา {p_price}"
                            )
                            st.session_state.cash_balance -= (total_val + p_comm)
                            
                            if found_idx != -1:
                                old = st.session_state.my_portfolio[found_idx]
                                new_shares = old['shares'] + p_qty
                                new_cost = ((old['shares'] * old['avg_price']) + total_val) / new_shares
                                st.session_state.my_portfolio[found_idx] = {'หุ้น': ticker_upper, 'shares': new_shares, 'avg_price': new_cost}
                            else:
                                st.session_state.my_portfolio.append({'หุ้น': ticker_upper, 'shares': p_qty, 'avg_price': p_price})
                        
                        else: # กรณีขาย
                            # บันทึกประวัติเงินสด (รับเข้า)
                            log_cash_transaction(
                                date=str(p_buy_date),
                                trans_type="ขายหุ้น " + ticker_upper,
                                amount=(total_val - p_comm),
                                note=f"ขาย {p_qty} หุ้น ที่ราคา {p_price}"
                            )
                            st.session_state.cash_balance += (total_val - p_comm)
                            
                            if found_idx != -1:
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
                        # ... ในส่วน submitted ของ form
                        st.session_state.cash_balance -= (total_val + p_comm) # หรือ + สำหรับการขาย
                        save_portfolio()
                        save_journal()
                        save_cash_balance(st.session_state.cash_balance) # เพิ่มบรรทัดนี้ครับ!
                        
                        st.success(f"บันทึกรายการ {ticker_upper} เรียบร้อย! เงินสดคงเหลือ: {st.session_state.cash_balance:,.2f} ฿")
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
                # สรุปยอดรวม (ปรับเป็น 4 คอลัมน์)
                col_s1, col_s2, col_s3, col_s4 = st.columns(4)
                
                # 1. เงินสดคงเหลือ
                col_s1.metric("เงินสดคงเหลือ", f"{st.session_state.cash_balance:,.0f} ฿")
                
                # 2. เงินลงทุนรวม (หุ้น)
                col_s2.metric("เงินลงทุนรวม", f"{total_invest:,.0f} ฿")
                
                # 3. มูลค่าปัจจุบัน (หุ้น)
                col_s3.metric("มูลค่าปัจจุบัน", f"{total_value:,.0f} ฿")
                
                # 4. กำไร/ขาดทุนรวม
                diff = total_value - total_invest
                col_s4.metric("กำไร/ขาดทุนรวม", f"{diff:,.0f} ฿", 
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
        
            with st.expander("📂 ดูประวัติการเทรดย้อนหลัง", expanded=False):
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
                # --- 1. ประกาศฟังก์ชันไว้ด้านบน (ห้ามย่อหน้า) ---
                def calculate_strategy(win_rate, profit_pct, loss_pct, trades=30, initial_capital=100000):
                    fixed_capital = initial_capital
                    fixed_balance = initial_capital
                    comp_balance = initial_capital
                    
                    for i in range(trades):
                        win = np.random.rand() < win_rate
                        # คำนวณแบบไม่ทบต้น
                        fixed_profit = (profit_pct * fixed_capital) if win else (-loss_pct * fixed_capital)
                        fixed_balance += fixed_profit
                        # คำนวณแบบทบต้น
                        comp_profit = (profit_pct * comp_balance) if win else (-loss_pct * comp_balance)
                        comp_balance += comp_profit
                        
                    return fixed_balance, comp_balance
                
                def show_strategy_analysis():
                    st.header("📊 ตารางเปรียบเทียบกลยุทธ์: ทบต้น vs ไม่ทบต้น")
                    initial_cap = 100000
                    loss_pct = 0.08
                    trades = 30
                    win_rates = [0.4, 0.5, 0.6]
                    profit_pcts = [0.10, 0.12, 0.14, 0.16]
                
                    data = []
                    for wr in win_rates:
                        for pr in profit_pcts:
                            wins = trades * wr
                            losses = trades * (1 - wr)
                            fixed_profit = (wins * pr * initial_cap) - (losses * loss_pct * initial_cap)
                            
                            comp_cap = initial_cap
                            for i in range(trades):
                                if np.random.rand() < wr: comp_cap *= (1 + pr)
                                else: comp_cap *= (1 - loss_pct)
                            
                            data.append({
                                "Win Rate": f"{int(wr*100)}%",
                                "Profit %": f"{int(pr*100)}%",
                                "ไม่ทบต้น (กำไร)": f"{fixed_profit:,.0f}",
                                "ทบต้น (กำไร)": f"{comp_cap - initial_cap:,.0f}",
                                "กลยุทธ์ที่แนะนำ": "ทบต้น" if comp_cap > (initial_cap + fixed_profit) else "ไม่ทบต้น"
                            })
                    st.table(pd.DataFrame(data))
                
                # --- ส่วนแสดงผลความเสี่ยง ทบต้น VS ไม่ทบต้น ---
                st.markdown("---")
                
                st.header("🧮 วิเคราะห์ความเสี่ยงและกลยุทธ์ ทบต้น VS ไม่ทบต้น")
            
                # เพิ่มส่วนเลือกช่วงเวลา
                time_period = st.radio(
                    "เลือกช่วงเวลาที่ต้องการวิเคราะห์:",
                    ["1 เดือน", "3 เดือน", "6 เดือน", "1 ปี", "Overall"],
                    horizontal=True
                )
                
                if "journal_data" in st.session_state and st.session_state.journal_data:
                    df_journal = pd.DataFrame(st.session_state.journal_data)
                    # ตรวจสอบว่าคอลัมน์วันที่เป็น datetime
                    df_journal['วันที่ขาย'] = pd.to_datetime(df_journal['วันที่ขาย'], errors='coerce')
                    
                    # คำนวณวันย้อนหลังตามช่วงเวลา
                    today = pd.Timestamp.now()
                    if time_period == "1 เดือน": filter_date = today - pd.Timedelta(days=30)
                    elif time_period == "3 เดือน": filter_date = today - pd.Timedelta(days=90)
                    elif time_period == "6 เดือน": filter_date = today - pd.Timedelta(days=180)
                    elif time_period == "1 ปี": filter_date = today - pd.Timedelta(days=365)
                    else: filter_date = pd.Timestamp('1900-01-01') # Overall
                    
                    # กรองข้อมูล
                    df_filtered = df_journal[df_journal['วันที่ขาย'] >= filter_date].copy()
                    
                    if not df_filtered.empty:
                        # --- ปรับ Logic การคำนวณให้ใช้ข้อมูลทั้งหมดที่กรองได้ ---
                        # คำนวณ ROI% เองโดยตรงจาก df_filtered
                        df_filtered['ROI_Percent'] = (df_filtered['กำไร/ขาดทุน (บาท)'] / df_filtered['ต้นทุน (บาท)'].replace(0, np.nan)) * 100
                        
                        total_trades = len(df_filtered)
                        win_trades = df_filtered[df_filtered['ROI_Percent'] > 0]
                        loss_trades = df_filtered[df_filtered['ROI_Percent'] <= 0]
                        
                        win_rate_val = (len(win_trades) / total_trades) * 100
                        avg_profit_val = win_trades['ROI_Percent'].mean() if not win_trades.empty else 0
                        avg_loss_val = abs(loss_trades['ROI_Percent'].mean()) if not loss_trades.empty else 0
                        rr_ratio = (avg_profit_val / avg_loss_val) if avg_loss_val != 0 else 0
                        
                        # แสดงผล
                        col1, col2, col3 = st.columns(3)
                        col1.metric("Win Rate", f"{win_rate_val:.1f}%")
                        col2.metric("R:R Ratio", f"{rr_ratio:.2f} : 1")
                        col3.metric("กลยุทธ์แนะนำ", "ทบต้น" if win_rate_val >= 45 and rr_ratio >= 1.5 else "ไม่ทบต้น")
                        
                        st.write(f"ผลงานรวมในช่วง {time_period} (ทั้งหมด **{total_trades} ไม้**):")
                    else:
                        st.warning("ไม่มีข้อมูลการเทรดในช่วงเวลาที่เลือก")
                        
                st.divider()
            
                # --- 3. ตารางเปรียบเทียบ (แบบซ่อนได้) ---
                with st.expander("📊 ดูตาราง Simulation เทียบเคียง"):
                    # 1. ดึงค่า Default
                    wr_val = w_rate if 'w_rate' in locals() else 0
                    pr_val = avg_profit if 'avg_profit' in locals() else 0
                    ls_val = avg_loss if 'avg_loss' in locals() else 0
                    
                    act_wr = wr_val / 100
                    act_profit = pr_val / 100
                    act_loss = ls_val / 100
                    
                    # 2. สร้าง Range
                    wr_range = [act_wr - 0.10, act_wr - 0.05, act_wr, act_wr + 0.05, act_wr + 0.10]
                    pr_range = [act_profit - 0.05, act_profit - 0.025, act_profit, act_profit + 0.025, act_profit + 0.05]
                    
                    sim_data = []
                    for wr in wr_range:
                        wr_display = max(0, min(1, wr)) 
                        row = {"Win Rate": f"{wr_display*100:.1f}%"}
                        for pr in pr_range:
                            ev = (wr_display * pr) - ((1 - wr_display) * abs(act_loss))
                            row[f"{pr*100:.1f}% Profit"] = ev * 100 
                        sim_data.append(row)
                    
                    # 3. เตรียมข้อมูลและเซต Index
                    df_full = pd.DataFrame(sim_data)
                    df_full = df_full.set_index("Win Rate")
                    
                    # 4. แปลงข้อมูลเป็นตัวเลขเพื่อทำ Style
                    df_numeric = df_full.astype(float)
                    
                    # 5. สร้าง Styler และจัด Format (แก้ปัญหา Styler object Error)
                    st_table = df_numeric.style.background_gradient(cmap="RdYlGn", axis=None).format("{:.2f}%")
                    
                    # 6. แสดงผลผ่านตาราง
                    st.dataframe(st_table, use_container_width=True)
                    
                    st.caption(f"ตารางแสดง Expected Return (%) ต่อไม้ โดยอ้างอิงจาก Avg Loss คงที่ {ls_val:.2f}%")
                #################################################
                with tab_plan:
                    st.subheader("📝 แผนการเทรดและตั้งค่า Alert")
                    
                    with st.form("trading_plan_form", clear_on_submit=True):
                        col1, col2 = st.columns(2)
                        with col1:
                            ticker = st.text_input("ชื่อหุ้น:", value=st.session_state.get("selected_ticker", ""))
                            entry = st.number_input("ราคาเข้าซื้อ:", min_value=0.0, format="%.2f")
                            stop_loss = st.number_input("จุดตัดขาดทุน:", value=float(entry * 0.95), format="%.2f")
                        with col2:
                            take_profit = st.number_input("จุดขายทำกำไร:", min_value=0.0, format="%.2f")
                            image_url = st.text_input("วาง Link รูปภาพ (URL):")
                        
                        submit_button = st.form_submit_button("บันทึกแผนลงตาราง")
                
                    if submit_button:
                        from datetime import datetime
                        new_data = {
                            'Ticker': ticker,
                            'Entry_Price': entry,
                            'Stop_Loss': stop_loss,
                            'Take_Profit': take_profit,
                            'Image_URL': image_url,
                            'Timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        if append_to_gsheet(new_data, "TradingPlan"):
                            st.success("บันทึกแผนเรียบร้อย!")
                            st.cache_data.clear()
                            st.rerun()
                
                    # --- ตารางแสดงแผนการเทรด ---
                    # --- ตารางแสดงแผนการเทรด ---
                    st.divider()
                    st.subheader("📊 ตารางแผนการเทรดของฉัน")
                    plan_df = load_data("TradingPlan") 
                    
                    if not plan_df.empty:
                        prices = [] # สร้าง List เก็บราคา
                        for ticker in plan_df['Ticker']:
                            symbol = f"{ticker}.BK"
                            try:
                                # ดึงราคาแบบเดียวกับพอร์ต
                                m_price = yf.Ticker(symbol).history(period="1d")['Close'].iloc[-1]
                                prices.append(float(m_price))
                            except:
                                prices.append(0.0) # ถ้าดึงไม่ได้ให้เป็น 0
                                
                        # เอา List ราคาที่ได้ใส่กลับเข้าไปใน DataFrame โดยตรง
                        plan_df['ราคาตลาด'] = prices
                    
                        # 4. คำนวณห่างจาก SL (เช็คไม่ให้หารด้วย 0)
                        plan_df['ห่างจาก_SL(%)'] = plan_df.apply(
                            lambda x: ((x['ราคาตลาด'] - x['Stop_Loss']) / x['ราคาตลาด'] * 100) 
                            if x['ราคาตลาด'] > 0 else 0.0, axis=1
                        ).round(2)
                    
                        # 5. ฟังก์ชันสถานะ
                        def check_alerts(row):
                            price = row['ราคาตลาด']
                            entry = row['Entry_Price']
                            sl = row['Stop_Loss']
                            tp = row['Take_Profit']
                            if price <= 0: return "ไม่มีราคา"
                            if abs(price - entry) / entry <= 0.01: return "⚠️ ใกล้จุดซื้อ"
                            if sl > 0 and (price - sl) / sl <= 0.01 and price > sl: return "🚨 ใกล้จุด SL (ระวัง!)"
                            if price >= tp: return "💰 ถึงเป้า TP!"
                            return "ปกติ"
                    
                        plan_df['สถานะ'] = plan_df.apply(check_alerts, axis=1)
                    
                        # 6. แสดงผล
                        # 6. แสดงผลตารางที่ปรับให้แก้ไขได้ตามต้องการ
                        edited_df = st.data_editor(
                            plan_df[['Ticker', 'Entry_Price', 'ราคาตลาด', 'Stop_Loss', 'ห่างจาก_SL(%)', 'Take_Profit', 'สถานะ', 'Timestamp', 'Image_URL']],
                            column_config={
                                "Ticker": st.column_config.TextColumn("หุ้น", disabled=True),
                                "ราคาตลาด": st.column_config.NumberColumn("ราคาตลาด", format="%.2f", disabled=True),
                                "ห่างจาก_SL(%)": st.column_config.NumberColumn("ห่างจาก SL (%)", format="%.2f%%", disabled=True),
                                "สถานะ": st.column_config.TextColumn("สถานะการแจ้งเตือน", disabled=True),
                                "Timestamp": None, # ซ่อนถ้าไม่จำเป็นต้องแก้ไข
                                "Image_URL": st.column_config.LinkColumn(
                                    "Plan trade", 
                                    help="คลิกเพื่อดูรูปภาพแผนการเทรด",
                                    display_text="ดูรูปแผนเทรด"
                                ),
                                # ตั้งค่าคอลัมน์ที่ต้องการให้แก้ไขได้เป็น disabled=False
                                "Entry_Price": st.column_config.NumberColumn("ราคาซื้อ", format="%.2f", disabled=False),
                                "Stop_Loss": st.column_config.NumberColumn("Stop Loss", format="%.2f", disabled=False),
                                "Take_Profit": st.column_config.NumberColumn("Take Profit", format="%.2f", disabled=False),
                            },
                            use_container_width=True,
                            key="editable_plan_table"
                        )
                    
                        if st.button("💾 บันทึกการแก้ไข", key="btn_update_plan"):
                            save_data(edited_df, "TradingPlan")
                            st.success("อัปเดตข้อมูลเรียบร้อย!")
                            st.rerun()
                    else:
                        st.info("ยังไม่มีข้อมูลแผนการเทรด")
# ------------------------------
if __name__ == "__main__":
    main()


###################################################################
# # --- ฟังก์ชัน Main Finish---
###################################################################
