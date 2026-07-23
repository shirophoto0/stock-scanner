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
import plotly.express as px
import plotly.graph_objects as go
from oauth2client.service_account import ServiceAccountCredentials
from google.oauth2.service_account import Credentials
from plotly.subplots import make_subplots
from datetime import datetime
# =============================================================
# 1. ฟังก์ชันจัดการ Google Sheets (Utility)
# =============================================================

###################
# Def TEFEX #
###################
# --- CONFIGURATION ---
# ค่า IM ของ SET50 Index Futures ต่อ 1 สัญญา (อัปเดต 1 กรกฎาคม 2026)
# พี่อ้ำสามารถปรับเปลี่ยนค่านี้ได้ตามประกาศจาก TFO/TCH
IM_PER_CONTRACT = 13300 
# ---------------------
def update_trade_close(spreadsheet_id, trade_id, close_price, date_close):
    client = get_gsheet_client()
    spreadsheet_id = '1moD7gjKnnLXDvCTfwVVhBmDwo5t0c7emErGbtJtGEWU' 
    sheet = client.open_by_key(spreadsheet_id).worksheet('TFEX_History')
    
    records = sheet.get_all_records()
    df = pd.DataFrame(records)
    
    # หาตำแหน่ง Row
    idx_list = df.index[df['Trade_ID'] == trade_id].tolist()
    if not idx_list:
        st.error("ไม่พบ Trade ID นี้ในระบบ")
        return False
    row_index = idx_list[0] + 2 
    
    # ดึงค่าเดิมมาคำนวณ
    trade_row = df.loc[idx_list[0]]
    open_price = float(trade_row['Open_Price'])
    size = int(trade_row['Size'])
    status = trade_row['Status']
    
    # คำนวณผลลัพธ์ผ่านฟังก์ชันเดิม
    comm = size * 50 
    calc = calculate_tfex_result(open_price, close_price, size, comm, status)
    
    # อัปเดตข้อมูล
    sheet.update_cell(row_index, 3, date_close)       # Date_Close
    sheet.update_cell(row_index, 8, close_price)      # Close_Price
    sheet.update_cell(row_index, 9, calc['Realized']) # Realized
    sheet.update_cell(row_index, 10, comm)            # Comm
    sheet.update_cell(row_index, 11, calc['Net_Profit']) # Net_Profit
    sheet.update_cell(row_index, 12, calc['Win_Lose'])   # Win_Lose
    
    # --- ส่วนที่เพิ่มเข้ามาเพื่อแก้ปัญหาดีเลย์ ---
    st.cache_data.clear()   # 1. ล้าง Cache ข้อมูลเก่าทิ้งทันที
    st.toast("บันทึกสำเร็จ! กำลังอัปเดตหน้าจอ...", icon="✅")
    st.rerun()              # 2. บังคับโหลดหน้าจอใหม่เพื่อให้ข้อมูลปัจจุบันที่สุดแสดงทันที
    
    return True

# 1. ฟังก์ชันคำนวณค่า ATR แบบมี Cache (ปลอดภัย ไม่โดน Block บ่อย)
@st.cache_data(ttl=3600, show_spinner=False)
def get_auto_atr_cached(symbol="^SET50"):
    """ดึงข้อมูลราคาและคำนวณ ATR ย้อนหลัง 14 วัน"""
    try:
        # ดึงข้อมูลจาก Yahoo Finance (SET50 Index)
        data = yf.download(symbol, period="1m", interval="1d", progress=False)
        
        if data.empty or len(data) < 15:
            return 6.5  # ค่าสำรองเริ่มต้น
        
        high = data['High']
        low = data['Low']
        close = data['Close']
        
        # จัดการโครงสร้างข้อมูล DataFrame กรณีเป็น MultiIndex
        if isinstance(high, pd.DataFrame):
            high = high.iloc[:, 0]
            low = low.iloc[:, 0]
            close = close.iloc[:, 0]

        prev_close = close.shift(1)
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr_value = tr.rolling(window=14).mean().iloc[-1]
        
        return round(float(atr_value), 2)
    except Exception as e:
        # กรณีเกิด Error หรือโดน Rate Limit ให้คืนค่าเริ่มต้นเพื่อความเสถียร
        return 6.5

def calculate_tfex_result(entry, close, size, comm, Status):
    # Multiplier ของ S50 ปกติคือ 200
    multiplier = 200
    
    # คำนวณจุดที่ได้ (Points)
    points = (close - entry) if Status == "Long" else (entry - close)
    
    # คำนวณกำไร/ขาดทุนก่อนหักคอม
    realized = points * size * multiplier
    
    # กำไรสุทธิ
    net_profit = realized - comm
    
    # สถานะ Win/Lose
    win_lose = "Win" if net_profit > 0 else "Lose"
    
    return {
        "Realized": round(realized, 2),
        "Net_Profit": round(net_profit, 2),
        "Win_Lose": win_lose,
        "Points": round(points, 2)
    }

def log_to_sheet(sheet_name, row_data):
    """ฟังก์ชันสำหรับบันทึกข้อมูลแถวใหม่ลง Google Sheets"""
    try:
        # ใช้ตัวแปร sheet_name เพื่อให้รองรับหลายชีทตามที่เราเรียกใช้งาน
        sheet = client.open('MyStockData').worksheet(sheet_name)
        sheet.append_row(row_data)
        return True
    except Exception as e:
        print(f"Error logging to {sheet_name}: {e}")
        return False
        
def save_data_to_sheet(new_df, sheet_name):
    try:
        client = get_gsheet_client()
        spreadsheet_id = '1moD7gjKnnLXDvCTfwVVhBmDwo5t0c7emErGbtJtGEWU' 
        sheet = client.open_by_key(spreadsheet_id).worksheet('TFEX_History')
        
        cols = ["Trade_ID", "Date_Open", "Date_Close", "Series", "Status", "Size", "Open_Price", 
                "Close_Price", "Realized", "Comm", "Net_Profit", "Win_Lose", "Reason"]
        
        new_df = new_df.reindex(columns=cols)
        
        sheet.append_rows(new_df.values.tolist())
        
        # --- เพิ่มส่วนนี้เพื่อให้หน้าจออัปเดตทันทีเมื่อ Open สถานะ ---
        st.cache_data.clear() # ล้างข้อมูลเก่า
        st.success("เปิดสถานะสำเร็จ!")
        st.rerun()            # โหลดหน้าจอใหม่ทันที
        
        return True
    except Exception as e:
        st.error(f"บันทึกข้อมูลไม่สำเร็จ: {e}")
        return False

def calculate_atr(df, period=14):
    """คำนวณค่า Average True Range (ATR) จากข้อมูลราคา"""
    if df.empty or len(df) < period:
        return 10.0 # ค่าสำรองเริ่มต้น (จุด) หากข้อมูลยังไม่พอ
    
    # สมมติ df มีคอลัมน์ High, Low, Close
    high = df['High']
    low = df['Low']
    close = df['Close']
    
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean().iloc[-1]
    
    return float(atr) if not pd.isna(atr) else 10.0
    
def save_cash_to_gsheet(df):
    """
    ฟังก์ชันเฉพาะสำหรับบันทึกรายการเงินเข้าหน้า Cash_Flow เท่านั้น
    """
    if df.empty:
        st.warning("ไม่มีข้อมูลที่จะบันทึก")
        return False
        
    try:
        # 1. เชื่อมต่อ (ใช้ client เดิมของคุณ)
        client = get_gsheet_client()
        
        # 2. เปิดไฟล์ MyStockData และระบุชื่อ Sheet ตรงนี้เลย
        # การใส่ชื่อนี้โดยตรงในโค้ดจะช่วยป้องกันความผิดพลาดเรื่องการพิมพ์ชื่อ Sheet
        sheet = client.open('MyStockData').worksheet("Cash_Flow")
        
        # 3. เตรียมและบันทึกข้อมูลต่อท้าย
        sheet.append_rows(df.values.tolist())
        
        return True
        
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการบันทึก Cash_Flow: {e}")
        return False        
####################

@st.cache_data(ttl=60)
def load_data(sheet_name):
    try:
        client = get_gsheet_client()
        # เปลี่ยนจาก 'TradingPlan' เป็นตัวแปร sheet_name ที่รับเข้ามา
        sheet = client.open('MyStockData').worksheet(sheet_name) 
        data = sheet.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"โหลดข้อมูล {sheet_name} ไม่สำเร็จ: {e}")
        return pd.DataFrame()
        
@st.cache_data(ttl=3600) # จำข้อมูลไว้ 1 ชม. ค่อยดึงใหม่
def get_cached_stock_info(ticker):
    stock = yf.Ticker(ticker)
    return stock.info  
    
def clear_and_save_data(df, sheet_name):
    try:
        client = get_gsheet_client()
        sheet = client.open('MyStockData').worksheet('TradingPlan')
        
        # ล้างข้อมูลเดิม
        sheet.clear()
        
        # เลือกเฉพาะคอลัมน์หลักที่เราใช้ในตาราง เพื่อความชัวร์
        cols = ['Ticker', 'Entry_Price', 'แนวรับ', 'แนวต้าน', 'ราคาตลาด', 'Stop_Loss', 'Take_Profit', 'ห่างจาก_SL(%)', 'สถานะ', 'Alert_Date', 'Timestamp', 'Image_URL']
        # กรองเอาเฉพาะคอลัมน์ที่มีอยู่จริง
        save_df = df[[c for c in cols if c in df.columns]]
        
        # เตรียมข้อมูล Header + Data
        data_to_save = [save_df.columns.tolist()] + save_df.fillna("").values.tolist()
        
        # บันทึก
        sheet.update('A1', data_to_save)
        return True
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาด: {e}")
        return False

def save_to_gsheet(df, sheet_name='StockData'):
    client = get_gsheet_client()
    spreadsheet_id = '1moD7gjKnnLXDvCTfwVVhBmDwo5t0c7emErGbtJtGEWU'
    sheet = client.open_by_key(spreadsheet_id).worksheet('StockData')
    
    # --- จุดแก้ไขสำคัญ: ล้างข้อมูลก่อนส่ง ---
    # 1. แทนที่ค่าที่เป็น NaN หรือ None ให้เป็นค่าว่าง ""
    # 2. แทนที่ค่า Infinity (inf) ให้เป็น 0
    df = df.replace([np.inf, -np.inf], 0).fillna("")
    
    # รวม Header และ ข้อมูล
    data_to_write = [df.columns.tolist()] + df.values.tolist()
    
    # ใช้ชื่อพารามิเตอร์เพื่อให้เป็นไปตามกฎใหม่ของ gspread
    sheet.update(range_name='A1', values=data_to_write)
    print(f"บันทึกข้อมูลลง {sheet_name} สำเร็จ!")
    
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
        
def log_portfolio_snapshot():
    """บันทึกยอดพอร์ตรายวันลงตาราง Portfolio_History"""
    client = get_gsheet_client()
    sheet = client.open('MyStockData').worksheet('Portfolio_History')
    
    # ดึงค่าปัจจุบัน
    current_date = datetime.now().strftime('%Y-%m-%d')
    market_val = get_total_market_value() # พี่อ้ำมีฟังก์ชันนี้อยู่แล้ว
    total_cash_invested = load_total_cash_balance() # พี่อ้ำมีฟังก์ชันนี้อยู่แล้ว
    
    # บันทึกแถวใหม่
    sheet.append_row([current_date, market_val, total_cash_invested])    

def calculate_total_portfolio_value():
    """คำนวณมูลค่าหุ้นในพอร์ตปัจจุบัน (Market Value ของหุ้นทั้งหมด)"""
    # 1. ดึงข้อมูล Journal มาคำนวณจำนวนหุ้นคงเหลือปัจจุบัน
    df = pd.DataFrame(st.session_state.journal_data)
    all_tickers = df['หุ้น'].unique()
    
    total_stock_value = 0
    
    # 2. ดึงราคาตลาดปัจจุบัน (Market Price) ของแต่ละตัว
    for ticker in all_tickers:
        buys = df[(df['หุ้น'] == ticker) & (df['ประเภท'].str.contains("ซื้อ", na=False))]['จำนวนหุ้นที่ซื้อ'].sum()
        sells = df[(df['หุ้น'] == ticker) & (df['ประเภท'].str.contains("ขาย", na=False))]['จำนวนหุ้นที่ซื้อ'].sum()
        shares = buys - sells
        
        if shares > 0:
            # ดึงราคาปัจจุบัน
            try:
                ticker_obj = yf.Ticker(f"{ticker}.BK")
                # ใช้ fast_info หรือ history เพื่อเอาราคาล่าสุด
                market_price = ticker_obj.fast_info['last_price']
                total_stock_value += (shares * market_price)
            except:
                # ถ้าดึงราคาไม่ได้ ให้ใช้ราคาทุนล่าสุดเพื่อไม่ให้ Error
                total_stock_value += 0 
                
    return total_stock_value

def total_invested_capital():
    # ดึงข้อมูลกระแสเงินสดมาคำนวณเงินลงทุนสุทธิ
    cash_df = load_data("Cash_Flow")
    if not cash_df.empty and 'Type' in cash_df.columns and 'Amount' in cash_df.columns:
        total_deposit = cash_df[cash_df['Type'].astype(str).str.lower() == 'deposit']['Amount'].sum()
        total_withdraw = cash_df[cash_df['Type'].astype(str).str.lower() == 'withdraw']['Amount'].sum()
        return total_deposit - total_withdraw
    return 0

def save_portfolio_snapshot():
    """บันทึกมูลค่าพอร์ตปัจจุบันลงไฟล์/Sheet ประวัติ"""
    # คำนวณมูลค่าหุ้นทั้งหมดจากพอร์ตใน session_state
    total_stock_value = sum([item['shares'] * item.get('current_price', item['avg_price']) for item in st.session_state.my_portfolio]) if "my_portfolio" in st.session_state else 0
    current_cash = st.session_state.cash_balance
    total_equity = total_stock_value + current_cash
    
    # บันทึกข้อมูลลงในตาราง Portfolio_History
    # รูปแบบ: [วันที่, มูลค่าพอร์ตรวม, เงินต้นสะสม]
    log_to_sheet("Portfolio_History", [str(datetime.now().date()), total_equity, total_invested_capital()])
    
def display_performance_dashboard():
    # 1. โหลดข้อมูล
    client = get_gsheet_client()
    sheet = client.open('MyStockData').worksheet('Portfolio_History')
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    
    # ตรวจสอบว่ามีข้อมูลจริงก่อนวาดกราฟ
    if df.empty:
        st.info("ยังไม่มีข้อมูลในตาราง Portfolio_History ครับ")
        return

    df['Date'] = pd.to_datetime(df['Date'])
    df['Indexed_Performance'] = (df['Market_Value'] / df['Market_Value'].iloc[0]) * 100
    
    # 2. แสดงผล (ย้ายส่วนแสดงผลมาไว้ในฟังก์ชันนี้)
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🚀 ความสามารถในการทำกำไร (Indexed)")
        fig1 = px.line(df, x='Date', y='Indexed_Performance', markers=True)
        st.plotly_chart(fig1, use_container_width=True)
        
    with col2:
        st.subheader("💰 พอร์ตจริง vs เงินลงทุน")
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=df['Date'], y=df['Market_Value'], name='มูลค่าพอร์ต', fill='tozeroy'))
        fig2.add_trace(go.Scatter(x=df['Date'], y=df['Invested_Capital'], name='เงินทุนจริง', line=dict(dash='dash')))
        st.plotly_chart(fig2, use_container_width=True)

def backfill_portfolio_history():
    # 1. เตรียมข้อมูล
    df = pd.DataFrame(st.session_state.journal_data)
    df['วันที่'] = pd.to_datetime(df['วันที่'])
    df = df.sort_values('วันที่')
    
    # กำหนดช่วงเวลา (ให้แน่ใจว่าเป็น datetime ไม่มี timezone)
    all_dates = pd.date_range(start=df['วันที่'].min(), end=pd.Timestamp.now().normalize())
    history_list = []
    
    # 2. ดึงราคาประวัติย้อนหลังเก็บไว้ใน dict
    all_tickers = df['หุ้น'].unique()
    price_history = {}
    for ticker in all_tickers:
        hist = yf.Ticker(f"{ticker}.BK").history(period="max")
        # แก้ไขจุดนี้: ปรับ Index ให้เป็น datetime และลบ timezone ออก
        hist.index = pd.to_datetime(hist.index).tz_localize(None)
        price_history[ticker] = hist['Close']

    # 3. ลูปคำนวณรายวัน
    for date in all_dates:
        # ใช้ .normalize() เพื่อให้ date เป็นเวลา 00:00:00 เป๊ะๆ
        date = date.normalize() 
        df_upto = df[df['วันที่'] <= date]
        
        # คำนวณจำนวนหุ้น
        current_holdings = {}
        for ticker in all_tickers:
            buys = df_upto[(df_upto['หุ้น'] == ticker) & (df_upto['ประเภท'].str.contains("ซื้อ"))]['จำนวนหุ้นที่ซื้อ'].sum()
            sells = df_upto[(df_upto['หุ้น'] == ticker) & (df_upto['ประเภท'].str.contains("ขาย"))]['จำนวนหุ้นที่ซื้อ'].sum()
            shares = buys - sells
            if shares > 0:
                current_holdings[ticker] = shares
        
        # คำนวณ Market Value
        market_val = 0
        for ticker, shares in current_holdings.items():
            price_series = price_history[ticker]
            # กรองข้อมูลที่ <= date หลังจากที่แปลง index เป็น datetime แล้ว
            price_at_date = price_series[price_series.index <= date]
            if not price_at_date.empty:
                market_val += (shares * price_at_date.iloc[-1])
        
        # คำนวณเงินลงทุน
        df_buys = df_upto[df_upto['ประเภท'].str.contains("ซื้อ", na=False)]
        invested = pd.to_numeric(df_buys['ต้นทุน (บาท)'], errors='coerce').fillna(0).sum()
        
        history_list.append({
            'Date': date.strftime('%Y-%m-%d'),
            'Market_Value': market_val,
            'Invested_Capital': invested
        })
    
    # 4. บันทึก
    # 4. บันทึก (แปลงเป็น DataFrame ก่อน)
    df_history = pd.DataFrame(history_list)
    df_history = df_history.fillna(0)
    save_to_gsheet("Portfolio_History", df_history)
    st.rerun()
    
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

def update_stock_data(df):
    client = get_gsheet_client()
    spreadsheet_id = '1moD7gjKnnLXDvCTfwVVhBmDwo5t0c7emErGbtJtGEWU'
    sheet = client.open_by_key(spreadsheet_id).worksheet('StockData')
    
    # 1. เตรียมข้อมูล: แปลง Header และข้อมูลเป็น list
    data_to_update = [df.columns.values.tolist()] + df.values.tolist()
    
    # 2. ใช้ update แทน clear() 
    # วิธีนี้จะเขียนทับตั้งแต่เซลล์ A1 ยาวไปจนจบข้อมูลใหม่ 
    # ข้อมูลเดิมจะถูกเขียนทับด้วยค่าใหม่ทันที โดยไม่ลบโครงสร้าง Sheet ทิ้ง
    sheet.update('A1', data_to_update)
    
    print("DEBUG: อัปเดตข้อมูลหุ้นเรียบร้อย!")
    
# 2. ฟังก์ชันอเนกประสงค์ (เอามาแทรกตรงนี้)
@st.cache_data(ttl=600)  
def save_cash_balance(amount):
    try:
        client = get_gsheet_client()
        sheet = client.open('MyStockData').worksheet('CashFlow')
        sheet.update('D2', [[amount]]) # เขียนเงินสดลงเซลล์ D2
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการบันทึกเงินสด: {e}")
        
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
        
        # ดึงข้อมูลทั้งหมด
        records = sheet.get_all_records()
        df = pd.DataFrame(records)
        
        # ตรวจสอบว่าคอลัมน์ Amount มีอยู่จริง
        if 'Amount' in df.columns:
            # 1. แปลงค่าใน Amount ให้เป็นตัวเลข ถ้าเจอข้อความ ให้เปลี่ยนเป็น NaN
            df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce')
            
            # 2. .dropna() จะลบแถวที่แปลงไม่ได้ (พวกที่มีข้อความ) ออกไป
            # 3. .sum() จะบวกเฉพาะตัวเลขที่เหลือ
            total_balance = df['Amount'].dropna().sum()
            return float(total_balance)
        
        return 69102.44 # ยอดเริ่มต้นถ้าหาคอลัมน์ไม่เจอ
    except Exception as e:
        print(f"DEBUG: Error ในการโหลดเงินสด: {e}")
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

from datetime import datetime

def check_alerts(row):
    # 1. จัดการข้อมูลให้เป็นตัวเลขที่นำไปคำนวณได้จริง
    try:
        price = float(row['ราคาตลาด'])
        sl = float(row['Stop_Loss']) if row['Stop_Loss'] else 0.0
        tp = float(row['Take_Profit']) if row['Take_Profit'] else 0.0
        support = float(row['แนวรับ']) if str(row['แนวรับ']).replace('.','',1).replace('-','').isdigit() else 0.0
        resistance = float(row['แนวต้าน']) if str(row['แนวต้าน']).replace('.','',1).replace('-','').isdigit() else 0.0
    except:
        return "ปกติ"
    
    if price <= 0:
        return "ไม่มีข้อมูลราคา"

    # 2. คำนวณลำดับความสำคัญ (Priority) ของสถานะ
    # เราเช็ค SL/TP ก่อน เพราะสำคัญกว่าแนวรับต้าน
    
    # กรณีถึงเป้าหมายหรือจุดคัท (ราคาแตะแล้ว)
    if sl > 0 and price <= sl:
        return f"⚠️ ถึงจุด Stop Loss {sl:.2f}"
    if tp > 0 and price >= tp:
        return f"🎉 ถึงจุด Take Profit {tp:.2f}"
    
    # กรณีใกล้เป้าหมาย (ใช้ระยะ 1% เพื่อแจ้งเตือนก่อนถึง)
    # เช็คแนวรับ/แนวต้าน
    if support > 0 and abs(price - support) / support <= 0.01:
        return f"🔔 ใกล้แนวรับ {support:.2f}"
    if resistance > 0 and abs(price - resistance) / resistance <= 0.01:
        return f"🔔 ใกล้แนวต้าน {resistance:.2f}"
    
    # ถ้าไม่เข้าเงื่อนไขเลย ให้คืนค่าปกติ
    return "ปกติ"

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
        
@st.cache_data(ttl=86400) # เก็บข้อมูลไว้วันละครั้งเพื่อความเร็ว
def load_and_calculate_stock_data_optimized():
    status_text = st.empty()
    status_text.text("กำลังดาวน์โหลดข้อมูลหุ้น SET100... (กรุณารอ)")
    
    # 1. เตรียม Tickers (เติม .BK ต่อท้ายทุกตัว)
    tickers_full = [f"{t}.BK" for t in SET100_TICKERS]
    
    # 2. ดึงข้อมูลทั้งหมดในคราวเดียว (Batch Download)
    # ใช้ threads=True ช่วยให้ดึงข้อมูลเร็วขึ้นหลายเท่า
    data = yf.download(tickers_full, period="2y", group_by='ticker', threads=True)
    
    # ดึงข้อมูล SET Index
    set_market = yf.download("^SET.BK", period="2y")['Close']
    
    stock_list = []
    total = len(SET100_TICKERS)
    
    for i, ticker in enumerate(SET100_TICKERS):
        try:
            # ดึงเฉพาะข้อมูลของหุ้นตัวนั้นๆ จาก DataFrame ที่โหลดมา
            df = data[ticker.replace('.BK', '')]
            if df.empty or len(df) < 200: continue
            
            # คำนวณ RSI
            df['RSI'] = calculate_rsi(df['Close'], period=14)
            
            # คำนวณ RS_Line
            combined = df[['Close']].join(set_market.rename('Market_Close'), how='inner')
            base_stock = combined['Close'].iloc[0]
            base_market = combined['Market_Close'].iloc[0]
            
            stock_perf = ((combined['Close'] - base_stock) / base_stock) * 100
            market_perf = ((combined['Market_Close'] - base_market) / base_market) * 100
            current_rs_val = (stock_perf - market_perf).iloc[-1]
            
            # คำนวณค่าทางเทคนิคอื่นๆ (ใช้ค่าจาก df ที่มีอยู่แล้ว)
            latest_price = df['Close'].iloc[-1]
            high_3m = df['High'].iloc[:-1].tail(60).max()
            high_6m = df['High'].iloc[:-1].tail(120).max()
            high_52w = df['High'].iloc[:-1].tail(250).max()
            
            stock_list.append({
                'Ticker': ticker.replace('.BK', ''),
                'ราคาล่าสุด': round(float(latest_price), 2),
                'RSI_14': round(float(df['RSI'].iloc[-1]), 2),
                'RS_Line': round(float(current_rs_val), 2),
                'Is_3M_High': latest_price >= (high_3m * 0.95),
                'Is_6M_High': latest_price >= (high_6m * 0.95),
                'Is_52W_High': latest_price >= (high_52w * 0.95),
            })
            
        except Exception:
            continue
            
    status_text.empty()
    return pd.DataFrame(stock_list)


###################################################################
# # --- ฟังก์ชัน Main ---
###################################################################

def highlight_rsi_zones(row):
    if row['RSI_14'] >= 65.0:
        return ['background-color: #fce4d6; color: black'] * len(row)
    elif 30.0 <= row['RSI_14'] <= 45.0:
        return ['background-color: #e2f0d9; color: black'] * len(row)
    return [''] * len(row)

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi
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

st.title("📈 แอปพลิเคชันวิเคราะห์หุ้นไทย")
st.write("ระบบสแกนหุ้นพร้อมกราฟเปรียบเทียบความแข็งแกร่งกับตลาดภาพรวม (SET Index)")

# จัดการ Session State เพื่อเก็บชื่อหุ้นที่เลือกไว้กลางระบบ
if "selected_ticker" not in st.session_state:
    st.session_state.selected_ticker = "KBANK"

# =============================================================
# 3. ฟังก์ชันคำนวณทางเทคนิคและสแกนหุ้น
# =============================================================


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


#####################################
# Def Main ส่วนครอบ code ทั้งหมด
######################################
        

    
# --- Initialize Session State ---

# ตั้งค่าหน้าจอ
st.set_page_config(layout="wide")
def main():
    # 1. ประกาศตัวแปรเริ่มต้น
    df_all_stocks = pd.DataFrame() 
    filtered_df = None

  # 2. โหมด GitHub (ทำงานจบในตัว)
    if 'GOOGLE_APPLICATION_CREDENTIALS' in os.environ:
        print("GitHub Mode: กำลังเริ่มสแกน...")
        df_new = load_and_calculate_stock_data_optimized()
        save_to_gsheet(df_new)
        print("GitHub Mode: บันทึกข้อมูลสำเร็จ")
        return # จบการทำงานทันที

    # ส่วนจัดการการโหลดข้อมูล
    if st.button("🔄 อัปเดตข้อมูลใหม่ (ดึงจาก Yahoo)"):
        with st.spinner("กำลังดึงข้อมูล..."):
            df_all_stocks = load_and_calculate_stock_data()
            save_to_gsheet(df_all_stocks)
            st.success("อัปเดตข้อมูลจาก Yahoo สำเร็จ!")
    else:
        # โหลดปกติจาก Google Sheets
        df_all_stocks = load_from_gsheet()
        
        # ถ้าโหลดไม่ขึ้น ให้ลองดึงจาก Yahoo ให้อัตโนมัติครั้งเดียว
        if df_all_stocks is None or df_all_stocks.empty:
            st.warning("ไม่พบข้อมูลใน Sheet กำลังดึงจาก Yahoo ใหม่...")
            df_all_stocks = load_and_calculate_stock_data()
            save_to_gsheet(df_all_stocks)
    
    # ตรวจสอบก่อนแสดงผล
    if not df_all_stocks.empty:
        # ใช้ filtered_df ถ้ามี (เช่นจากการ Filter ของผู้ใช้) ถ้าไม่มีก็ใช้ df_all_stocks
        df_to_show = filtered_df if filtered_df is not None else df_all_stocks
        # st.dataframe(df_to_show, use_container_width=True)
    else:
        st.error("ไม่สามารถโหลดข้อมูลหุ้นได้เลย กรุณาตรวจสอบการเชื่อมต่อ Google Sheets")

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
    
    # ใช้ฟังก์ชัน Cache ดึงข้อมูลแทนการดึงตรงจาก Ticker object
    info = get_cached_stock_info(ticker) 
    
    # ถ้าพี่อ้ำยังต้องใช้ stock_data เพื่อดึงข้อมูลกราฟ หรืออย่างอื่น
    # ก็ให้ประกาศ stock_data ไว้เหมือนเดิมได้ แต่ไม่ต้องดึง .info แล้วครับ
    stock_data = yf.Ticker(ticker) 
        
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
            pe_value = info.get('trailingPE')
            
            if pe_value is not None:
                st.write(f"• **ราคาต่อกำไรสุทธิ (P/E Ratio ยืนยัน):** {pe_value:.2f} เท่า")
            else:
                st.write("• **ราคาต่อกำไรสุทธิ (P/E Ratio ยืนยัน):** ไม่มีข้อมูล")
            
        st.info("💡 **ข้อแนะนำจากระบบ:** หุ้นซุปเปอร์สต็อกตามสไตล์ Mark Minervini มักจะมี EPS Growth ขยายตัวมากกว่า 20%-25% ขึ้นไป ควบคู่กับราคาหุ้นที่ยกฐานยืนเหนือเส้น EMA ขาขึ้น")

        with st.expander("⚙️ ตั้งค่าการแสดงผลกราฟ"):
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
                info = get_cached_stock_info(ticker)
                
                
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
                # (แนะนำให้พี่อ้ำใช้โค้ดเดิมในส่วนนี้ได้เลยครับ ผมตัดมาให้สั้นลงเพื่อดูโครงสร้าง)
                # ...
            
            
            except Exception as e:
                st.error(f"⚠️ เกิดข้อผิดพลาดในการวาดกราฟ: {str(e)}")
            
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

    # สร้าง Columns โดยระบุให้จัดกึ่งกลางแนวตั้ง
    # ปรับสัดส่วนคอลัมน์ให้ชิดขึ้นอีก (0.08 คือพื้นที่ของไอคอน)
    # ปรับสัดส่วนให้สมดุลขึ้น
    # ปรับสัดส่วนให้สมดุล
    col1, col2 = st.columns([0.07, 0.93], vertical_alignment="center")
    
    with col1:
        st.markdown("<div style='font-size: 40px; margin: 0px;'>💹</div>", unsafe_allow_html=True)
    
    with col2:
        st.markdown("<h2 style='margin: 0px;'>Stock and TFEX Management</h2>", unsafe_allow_html=True)
    
    # --- ปรับขนาดเฉพาะข้อความใน Tab ---
    st.markdown("""
        <style>
        /* ปรับขนาดตัวหนังสือใน Tab โดยเฉพาะ */
        div[data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {
            font-size: 60px !important;
            font-weight: bold !important;
        }
        
        /* ปรับความสูงของ Tab ให้รับกับตัวหนังสือที่ใหญ่ขึ้น */
        button[data-baseweb="tab"] {
            padding: 30px 70px !important;
        }
        </style>
    """, unsafe_allow_html=True)
    
    tab_stock, tab_tfex = st.tabs(["📊 หุ้น (Stock)", "📈 TFEX"])
    
    # 1. ส่วนหุ้น
    with tab_stock:
                       
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
                        col_s1, col_s2, col_s3 = st.columns(3)
                        
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
                        
                        ######### กราฟรายเดือน vs พร์อตสะสม ###################
                        st.markdown("##### 📈 ผลงานรายเดือน vs พอร์ตสะสม")
                        c1, c2 = st.columns(2)
            
                        # --- ข้อมูลรายเดือน ---
                        df_monthly = df_filtered.copy()
                        df_monthly['Date'] = pd.to_datetime(df_monthly['วันที่'])
                        df_monthly['Month_Label'] = df_monthly['Date'].dt.strftime('%b %Y')
                        df_monthly = df_monthly.sort_values('Date') 
                        df_monthly = df_monthly.groupby('Month_Label', sort=False)['กำไร/ขาดทุน (บาท)'].sum().reset_index()
                        df_monthly.columns = ['Month_Label', 'Profit_Sum']
                        df_monthly['Cumulative_Profit'] = df_monthly['Profit_Sum'].cumsum()
                        df_monthly['Color'] = df_monthly['Profit_Sum'].apply(lambda x: 'Profit' if x >= 0 else 'Loss')
            
                        with c1:
                            chart_bar = alt.Chart(df_monthly).mark_bar(width=40).encode(
                                x=alt.X('Month_Label:O', title='เดือน', sort=None), 
                                y=alt.Y('Profit_Sum:Q', title='กำไร/ขาดทุน (บาท)'),
                                color=alt.Color('Color', scale=alt.Scale(domain=['Profit', 'Loss'], range=['#2ecc71', '#e74c3c']), legend=None),
                                tooltip=['Month_Label', 'Profit_Sum']
                            ).properties(height=300)
                            rule = alt.Chart(pd.DataFrame({'y': [0]})).mark_rule(color='#666666', strokeDash=[3,3]).encode(y='y')
                            st.altair_chart(chart_bar + rule, use_container_width=True)
            
                        with c2:
                            chart_line = alt.Chart(df_monthly).mark_line(point=True, color='#3498db', strokeWidth=3).encode(
                                x=alt.X('Month_Label:O', title='เดือน', sort=None),
                                y=alt.Y('Cumulative_Profit:Q', title='กำไรสะสม (บาท)'),
                                tooltip=['Month_Label', 'Cumulative_Profit']
                            ).properties(height=300)
                            st.altair_chart(chart_line, use_container_width=True)
                                                                
                        ##### กราฟกระจายตัว (Histogram) ###########
                        st.markdown("---")
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
                            # สี: Mean=#12da58, Avg Loss=#9b59b6, Target=#f21d2b
                            col_m1, col_m2, col_m3 = st.columns(3)
                            col_m1.markdown(f"<div style='text-align: center; color: #12da58; font-size: 20px; font-weight: bold;'>Mean</div><div style='text-align: center; font-size: 24px;'>{mean_val:.1f}%</div>", unsafe_allow_html=True)
                            col_m2.markdown(f"<div style='text-align: center; color: #9b59b6; font-size: 20px; font-weight: bold;'>Avg Loss</div><div style='text-align: center; font-size: 24px;'>{avg_loss_pct:.1f}%</div>", unsafe_allow_html=True)
                            if optimal_cutloss_pct is not None:
                                col_m3.markdown(f"<div style='text-align: center; color: #f21d2b; font-size: 20px; font-weight: bold;'>Target Cut</div><div style='text-align: center; font-size: 24px;'>{optimal_cutloss_pct:.1f}%</div>", unsafe_allow_html=True)
                            
                            # 3. วาดกราฟ
                            fig = px.histogram(df_filtered, x='Profit_Pct', nbins=20, opacity=0.6, color_discrete_sequence=['#3498db'])
                            
                            # เพิ่ม annotation_yshift ให้ต่ำลงเล็กน้อย และลดระยะห่าง
                            fig.add_vline(x=mean_val, line_dash="dash", line_color="#12da58", 
                                          annotation_text=f"Mean ({mean_val:.1f}%)", annotation_position="top right", annotation_yshift=20)
                            fig.add_vline(x=avg_loss_pct, line_dash="dot", line_color="#9b59b6", 
                                          annotation_text=f"Avg Loss ({avg_loss_pct:.1f}%)", annotation_position="top right", annotation_yshift=-10)
                            if optimal_cutloss_pct is not None:
                                fig.add_vline(x=optimal_cutloss_pct, line_dash="dashdot", line_color="#f21d2b", 
                                              annotation_text=f"Target ({optimal_cutloss_pct:.1f}%)", annotation_position="top right", annotation_yshift=-40)
                            
                            # **สำคัญ:** เพิ่ม margin top เพื่อให้มีพื้นที่เหลือให้ป้ายข้อความด้านบนไม่ถูกตัด
                            fig.update_layout(margin=dict(t=50, b=20, l=20, r=20), height=350, plot_bgcolor='rgba(0,0,0,0)')
                            st.plotly_chart(fig, use_container_width=True)
                            
                        else:
                            st.info("ยังไม่มีข้อมูลเพียงพอที่จะแสดงกราฟการกระจายตัวครับ")

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
                            
                        ####################
                        if st.button("🔄 อัปเดตข้อมูลย้อนหลัง (Backfill)"):
                            with st.spinner('กำลังคำนวณข้อมูลย้อนหลัง (อาจใช้เวลาสักครู่)...'):
                                # เรียกใช้ฟังก์ชันที่เขียนไว้
                                backfill_portfolio_history()
                                st.success("อัปเดตเรียบร้อย! กราฟของคุณพร้อมใช้งานแล้ว")
                        # Equity Curve 
                        st.markdown("---")
                        st.markdown("##### 📈 Equity Curve")
                        
                        # เรียกใช้งานฟังก์ชันที่ย้ายไปด้านบน
                        try:
                            display_performance_dashboard()
                        except Exception as e:
                            st.warning(f"ยังไม่พบข้อมูล Portfolio_History หรือเกิดข้อผิดพลาดในการโหลด: {e}")
                                               
                            
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
                            # เปลี่ยนเป็นรับค่ากำไร/ขาดทุนที่เป็นตัวเลขบวก/ลบธรรมดา ระบบจะปรับให้เอง
                            p_result = st.number_input("กำไร/ขาดทุน (บาท):", step=100.0, format="%.2f", help="กรอกแค่ตัวเลข ระบบจะใส่เครื่องหมายให้เอง")
                            p_price = st.number_input("ราคาต่อหุ้น:", min_value=0.01, step=0.05, format="%.2f")
                            p_qty = st.number_input("จำนวนหุ้น:", min_value=1, step=100)
                            p_comm = st.number_input("ค่าธรรมเนียม:", min_value=0.0, step=1.0)
                            
                        p_reason = st.text_area("เหตุผล/กลยุทธ์:")
                        submitted = st.form_submit_button("ยืนยันรายการ")
                
                        if submitted:
                            total_val = (p_qty * p_price)
                            ticker_upper = p_ticker.upper()
                            
                            # --- Logic อัตโนมัติ: ถ้าเป็น Stop Loss หรือ ขาดทุน ให้บังคับเป็นค่าลบ ---
                            final_result = float(p_result)
                            if "Stop Loss" in p_type or "ขาดทุน" in p_status:
                                final_result = -abs(final_result) # บังคับติดลบ
                            else:
                                final_result = abs(final_result)  # บังคับเป็นบวกสำหรับกำไร
                
                            # 1. จัดการข้อมูล Portfolio (อัปเดตสถานะเงินสดและหุ้น)
                            found_idx = next((i for i, item in enumerate(st.session_state.my_portfolio) if item['หุ้น'] == ticker_upper), -1)
                            
                            if "ซื้อ" in p_type:
                                log_cash_transaction(date=str(p_buy_date), trans_type="ซื้อหุ้น " + ticker_upper, amount=-(total_val + p_comm), note=f"ซื้อ {p_qty} หุ้น ที่ราคา {p_price}")
                                st.session_state.cash_balance -= (total_val + p_comm)
                                
                                if found_idx != -1:
                                    old = st.session_state.my_portfolio[found_idx]
                                    new_shares = old['shares'] + p_qty
                                    new_cost = ((old['shares'] * old['avg_price']) + total_val) / new_shares
                                    st.session_state.my_portfolio[found_idx] = {'หุ้น': ticker_upper, 'shares': new_shares, 'avg_price': new_cost}
                                else:
                                    st.session_state.my_portfolio.append({'หุ้น': ticker_upper, 'shares': p_qty, 'avg_price': p_price})
                            
                            else: # กรณีขาย
                                log_cash_transaction(date=str(p_buy_date), trans_type="ขายหุ้น " + ticker_upper, amount=(total_val - p_comm), note=f"ขาย {p_qty} หุ้น ที่ราคา {p_price}")
                                st.session_state.cash_balance += (total_val - p_comm)
                                
                                if found_idx != -1:
                                    st.session_state.my_portfolio[found_idx]['shares'] -= p_qty
                                    if st.session_state.my_portfolio[found_idx]['shares'] <= 0:
                                        st.session_state.my_portfolio.pop(found_idx)
                            
                            # 2. เพิ่มข้อมูลเข้า Journal ด้วยค่า final_result ที่จัดการเครื่องหมายเรียบร้อย
                            new_entry = {
                                "วันที่": str(p_buy_date), 
                                "วันที่ซื้อ": str(p_buy_date),
                                "วันที่ขาย": str(j_sell_date) if j_sell_date else None,
                                "หุ้น": ticker_upper,
                                "สถานะ": p_status,
                                "ประเภท": p_type,
                                "กำไร/ขาดทุน (บาท)": final_result,
                                "ต้นทุน (บาท)": total_val,
                                "ราคาหุ้นที่ซื้อ (บาท/หุ้น)": p_price,
                                "จำนวนหุ้นที่ซื้อ": p_qty,
                                "เหตุผล": p_reason
                            }
                            st.session_state.journal_data.append(new_entry)
                
                            # 3. บันทึกลง Google Sheets และอัปเดตหน้าจอ
                            save_portfolio()
                            save_journal()
                            save_cash_balance(st.session_state.cash_balance)
                            
                            # --- เพิ่มการคำนวณมูลค่าพอร์ตสุทธิ (Total Equity) ตรงนี้ให้ชัวร์ ---
                            # คำนวณมูลค่าหุ้นคงเหลือในพอร์ตปัจจุบัน
                            total_stock_value = sum([item['shares'] * item.get('current_price', item['avg_price']) for item in st.session_state.my_portfolio]) if "my_portfolio" in st.session_state else 0
                            total_equity = st.session_state.cash_balance + total_stock_value
                            
                            # เรียกบันทึก Snapshot หลังจากคำนวณค่าเสร็จแล้ว
                            save_portfolio_snapshot()
                            
                            st.success(f"บันทึก {ticker_upper} สำเร็จ! (กำไร/ขาดทุน: {final_result:,.2f} ฿)")
                            st.rerun()
                            
                # 3. ตารางแสดงพอร์ต (เชื่อมต่อ Google Sheets)
                st.divider()
                st.subheader("📊 สรุปพอร์ตการลงทุน")
            
                if "my_portfolio" not in st.session_state:
                    load_portfolio()
                
                if st.session_state.my_portfolio:
                    portfolio_list = []
                    total_invest = 0
                    total_value = 0
                    
                    # ฟังก์ชันกำหนดสีสำหรับตารางพอร์ต
                    def color_portfolio(val):
                        if isinstance(val, (int, float)):
                            color = '#26A69A' if val > 0 else '#EF5350' if val < 0 else 'black'
                            return f'color: {color}'
                        return None
        
                    for row in st.session_state.my_portfolio:
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
                        profit_pct = (profit / cost_value * 100) if cost_value > 0 else 0
                        
                        portfolio_list.append({
                            "หุ้น": ticker,
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
                    
                    # สรุปยอดรวม
                    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
                    col_s1.metric("เงินสดคงเหลือ", f"{st.session_state.cash_balance:,.0f} ฿")
                    col_s2.metric("เงินลงทุนรวม", f"{total_invest:,.0f} ฿")
                    col_s3.metric("มูลค่าปัจจุบัน", f"{total_value:,.0f} ฿")
                    diff = total_value - total_invest
                    col_s4.metric("กำไร/ขาดทุนรวม", f"{diff:,.0f} ฿", delta=f"{((diff)/total_invest)*100:.2f}%" if total_invest > 0 else "0%")
        
                    # แสดงตาราง
                    df_p = pd.DataFrame(portfolio_list)
                    st.dataframe(
                        df_p.style.format({
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
    
                    # --- ส่วนแสดงกราฟสรุปพอร์ต ---
                    st.divider()
                    
                    # แบ่งคอลัมน์สัดส่วน 25% : 25% : 50%
                    col_p1, col_p2, col_p3 = st.columns([1, 1, 2])
                    
                    # 1. Pie Chart: มูลค่าตลาด (25%)
                    with col_p1:
                        st.subheader("🥧 มูลค่าตลาด")
                        fig_pie1 = px.pie(df_p, values='มูลค่าตลาด', names='หุ้น', hole=0.4) # ปรับ hole เป็น 0.4 ให้โปร่งขึ้น
                        # แก้ไขในส่วน Pie Chart ทั้ง 2 อันครับ
                        fig_pie1.update_traces(
                            textposition='outside', 
                            textinfo='label+percent',
                            textfont=dict(size=9), # ลดอีกนิด
                            automargin=True        # หัวใจสำคัญ: สั่งให้ Plotly ขยับพื้นที่เองเพื่อไม่ให้ทับซ้อน
                        )
                        fig_pie1.update_layout(height=300, margin=dict(l=0, r=0, t=20, b=20), showlegend=False)
                        st.plotly_chart(fig_pie1, use_container_width=True)
                        st.markdown("<p style='text-align: center; font-size: 13px;'>สัดส่วนมูลค่าตลาดปัจจุบัน</p>", unsafe_allow_html=True)
        
                    # 2. Pie Chart: มูลค่าต้นทุน (25%)
                    with col_p2:
                        st.subheader("🥧 มูลค่าต้นทุน")
                        fig_pie2 = px.pie(df_p, values='มูลค่าต้นทุน', names='หุ้น', hole=0.4) # ปรับ hole เป็น 0.4
                        # แก้ไขในส่วน Pie Chart ทั้ง 2 อันครับ
                        fig_pie2.update_traces(
                            textposition='outside', 
                            textinfo='label+percent',
                            textfont=dict(size=9), # ลดอีกนิด
                            automargin=True        # หัวใจสำคัญ: สั่งให้ Plotly ขยับพื้นที่เองเพื่อไม่ให้ทับซ้อน
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
                        # ปรับ font ของ Bar Chart ให้เล็กลงเล็กน้อยเพื่อไม่ให้ล้นแท่ง
                        fig_bar.update_traces(textfont_size=10)
                        fig_bar.update_layout(height=300, margin=dict(l=10, r=10, t=30, b=10))
                        st.plotly_chart(fig_bar, use_container_width=True)
                        st.markdown("<p style='text-align: center; font-size: 13px;'>กำไร/ขาดทุน เป็น THB และ %</p>", unsafe_allow_html=True)
        
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
                        with st.expander("📊 สถิติการเทรดรายเดือน", expanded=False):
                            # 1. ส่วนคำนวณสถิติ
                            stats_df = calculate_journal_stats(df_journal)
                            
                            # 2. ส่วนสรุป Metric 3 ค่าด้านบน (อิงจากช่วงเวลาที่เลือก)
                            st.markdown("##### 🎯 สถิติการเทรดจริง & การปรับจุดคัทลอส (RR 2:1)")
                            period = st.radio("ดูค่าเฉลี่ยย้อนหลัง:", ["3 เดือน", "6 เดือน", "1 ปี"], horizontal=True, key="stats_period")
                            
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
                                
                                # --- ส่วนแก้ไขการคำนวณ Avg Profit / Avg Loss เพื่อป้องกันค่าเพี้ยน (Outlier) ---
                                profit_mask = (df_period[col_profit_loss] > 0) & (df_period[col_cost] > 0)
                                profit_series = (df_period.loc[profit_mask, col_profit_loss] / df_period.loc[profit_mask, col_cost]) * 100
                                avg_profit = profit_series.clip(upper=500).mean() if not profit_series.empty else 0
                
                                loss_mask = (df_period[col_profit_loss] <= 0) & (df_period[col_cost] > 0)
                                loss_series = (df_period.loc[loss_mask, col_profit_loss] / df_period.loc[loss_mask, col_cost]) * 100
                                
                                # กรองค่าที่ติดลบเกิน -100% ออก เพื่อไม่ให้ค่าเฉลี่ยพังกรณีต้นทุนต่ำผิดปกติ
                                loss_series = loss_series[loss_series >= -100] 
                                avg_loss = loss_series.mean() if not loss_series.empty else 0
                                # --------------------------------------------------------------------------
                                
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
                    st.markdown("#### 🚀 ระบบคำนวณ Risk Management & Position Sizing")

                    # 1. แสดงสถานะพอร์ตปัจจุบัน (เอาไว้ดูข้อมูล)
                    cash_balance = load_total_cash_balance()
                    market_value = get_total_market_value()
                    total_equity = cash_balance + market_value
                    
                    st.markdown("##### 💰 สรุปสถานะพอร์ตปัจจุบัน")
                    col_a, col_b, col_c = st.columns(3)
                    col_a.metric("เงินสดคงเหลือ", f"{cash_balance:,.0f} ฿")
                    col_b.metric("มูลค่าหุ้นที่ถือ", f"{market_value:,.0f} ฿")
                    col_c.metric("มูลค่าพอร์ตสุทธิ", f"{total_equity:,.0f} ฿")
                    
                    st.divider()
                    
                    # 2. ส่วนการคำนวณ
                    r_col1, r_col2 = st.columns([1, 1])

                    with r_col1:
                        total_cap = st.number_input(
                            "👉 ระบุจำนวนเงินทุนที่ต้องการใช้คำนวณไม้ซื้อนี้ (บาท):", 
                            min_value=1000, 
                            value=int(total_equity), # นี่คือค่าเริ่มต้นที่ดึงมาจากพอร์ตจริง
                            step=1000,
                            help="สามารถลบตัวเลขนี้แล้วพิมพ์จำนวนเงินที่ต้องการใช้ซื้อจริงได้เลยครับ"
                        )
                        risk_pct = st.slider("2. ความเสี่ยงสูงสุดต่อไม้ (% ของพอร์ต):", min_value=0.25, max_value=3.0, value=1.0, step=0.25)
                    
                    with r_col2:
                        latest_p = float(latest_price_single)
                        
                        sl_type = st.selectbox("3. เลือกเกณฑ์จุดตัดขาดทุน (Stop Loss):", [
                            f"เส้น EMA 10 ({chart_combined['EMA10'].iloc[-1]:.2f} บาท)",
                            f"เส้น EMA 20 ({chart_combined['EMA20'].iloc[-1]:.2f} บาท)",
                            "กำหนดเป็นเปอร์เซ็นต์คงที่ (Fixed %)",
                            "กำหนดราคาคัทด้วยตัวเอง (Manual Price)"
                        ])
                        
                        # กำหนดค่า sl_price ตามเงื่อนไขที่เลือก
                        if "EMA 10" in sl_type:
                            sl_price = float(chart_combined['EMA10'].iloc[-1])
                        elif "EMA 20" in sl_type:
                            sl_price = float(chart_combined['EMA20'].iloc[-1])
                        elif "กำหนดเป็นเปอร์เซ็นต์คงที่" in sl_type:
                            fixed_sl_pct = st.slider("ระบุ % Stop Loss ที่ต้องการ:", min_value=2.0, max_value=12.0, value=7.0, step=0.5)
                            sl_price = latest_p * (1 - (fixed_sl_pct / 100))
                        else: # Manual Price
                            sl_price = st.number_input("ระบุราคา Stop Loss (บาท):", min_value=0.0, value=latest_p * 0.93, step=0.25)
                    
                    # 3. คำนวณผลลัพธ์
                    max_risk_money = total_cap * (risk_pct / 100)
                    risk_per_share = latest_p - sl_price
                    
                    # ตรวจสอบก่อนนำไปหาร เพื่อป้องกัน Error
                    if risk_per_share <= 0:
                        st.error("⚠️ ราคา Stop Loss ต้องต่ำกว่าราคาซื้อปัจจุบันครับ!")
                    else:
                        shares_to_buy = int(max_risk_money / risk_per_share)
                        total_buy_value = shares_to_buy * latest_p
                        
                        st.markdown("##### 📊 ผลลัพธ์หน้าเทรดและขนาดไม้ที่เหมาะสม:")
                        res_col1, res_col2, res_col3, res_col4 = st.columns(4)
                        res_col1.metric("จำนวนที่ควรซื้อ", f"{shares_to_buy:,} หุ้น")
                        res_col2.metric("เงินลงทุน (Position Size)", f"{total_buy_value:,.0f} ฿")
                        res_col3.metric("ตั้ง SL ที่ราคา", f"{sl_price:.2f} ฿")
                        res_col4.metric("เสียเงินสูงสุดหากแพ้", f"{max_risk_money:,.0f} ฿")
                                            
            #######################          
                    st.markdown("---")

                    st.markdown("##### 🛡️ การบริหารความเสี่ยง (Risk Monitoring)")

                    # 1. คำนวณ Exposure (เงินในหุ้น / เงินทุนรวมทั้งหมด)
                    # สมมติว่า total_market_val คือมูลค่าหุ้นปัจจุบัน และ st.session_state.cash_balance คือเงินสด
                    total_market_val = calculate_total_portfolio_value() 
                    current_cash = st.session_state.cash_balance
                    total_equity = total_market_val + current_cash
                    
                    exposure_pct = (total_market_val / total_equity) * 100 if total_equity > 0 else 0
                    
                    # 2. คำนวณ Expectancy
                    # WinRate, AverageWin, AverageLoss ต้องคำนวณจาก df_filtered
                    wins = df_filtered[df_filtered['กำไร/ขาดทุน (บาท)'] > 0]
                    losses = df_filtered[df_filtered['กำไร/ขาดทุน (บาท)'] <= 0]
                    
                    win_rate = len(wins) / len(df_filtered) if len(df_filtered) > 0 else 0
                    avg_win = wins['กำไร/ขาดทุน (บาท)'].mean() if len(wins) > 0 else 0
                    avg_loss = abs(losses['กำไร/ขาดทุน (บาท)'].mean()) if len(losses) > 0 else 0
                    loss_rate = 1 - win_rate
                    
                    expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)
                    
                    # 3. แสดงผลด้วย st.metric
                    col_r1, col_r2 = st.columns(2)
                    col_r1.metric("Market Exposure", f"{exposure_pct:.1f}%")
                    col_r2.metric("Expectancy (ต่อไม้)", f"{expectancy:,.0f} ฿")

                
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
                        # 1. ดึงข้อมูลจาก df_period มาคำนวณแบบสดๆ ตรงนี้เลย เพื่อความชัวร์ (ไม่ให้ไปดึงตัวแปรเก่าข้างนอกมาปน)
                        if 'df_period' in locals() and not df_period.empty:
                            col_pl_sim = 'กำไร/ขาดทุน (บาท)'
                            col_cost_sim = 'ต้นทุน (บาท)'
                            
                            # คำนวณ Win Rate สดๆ
                            wr_val = (df_period[col_pl_sim] > 0).mean() * 100
                            
                            # คำนวณ Avg Profit สดๆ
                            p_mask = (df_period[col_pl_sim] > 0) & (df_period[col_cost_sim] > 0)
                            p_series = (df_period.loc[p_mask, col_pl_sim] / df_period.loc[p_mask, col_cost_sim]) * 100
                            pr_val = p_series.clip(upper=500).mean() if not p_series.empty else 10.0 # ค่าสำรองถ้าไม่มีข้อมูล
                            
                            # คำนวณ Avg Loss สดๆ (และบังคับให้เป็นบวกทันทีด้วย abs)
                            l_mask = (df_period[col_pl_sim] <= 0) & (df_period[col_cost_sim] > 0)
                            l_series = (df_period.loc[l_mask, col_pl_sim] / df_period.loc[l_mask, col_cost_sim]) * 100
                            l_series = l_series[l_series >= -100] # กรองค่าเพี้ยน
                            ls_val = abs(l_series.mean()) if not l_series.empty else 5.0 # ค่าสำรองถ้าไม่มีข้อมูล
                        else:
                            # ค่า Default เผื่อกรณีไม่มีข้อมูลในช่วงเวลานั้น
                            wr_val, pr_val, ls_val = 50.0, 10.0, 5.0
                    
                        act_wr = wr_val / 100.0
                        act_profit = pr_val / 100.0
                        act_loss = ls_val / 100.0  # ตอนนี้ ls_val จะเป็นค่าบวกปกติ (เช่น 7.49%) หาร 100 จะได้ 0.0749
                        
                        # 2. สร้าง Range สำหรับจำลองตาราง
                        wr_range = [act_wr - 0.10, act_wr - 0.05, act_wr, act_wr + 0.05, act_wr + 0.10]
                        pr_range = [act_profit - 0.05, act_profit - 0.025, act_profit, act_profit + 0.025, act_profit + 0.05]
                        
                        sim_data = []
                        for wr in wr_range:
                            wr_display = max(0.0, min(1.0, wr)) 
                            row = {"Win Rate": f"{wr_display*100:.1f}%"}
                            for pr in pr_range:
                                # คำนวณ Expected Value (EV) 
                                ev = (wr_display * pr) - ((1.0 - wr_display) * act_loss)
                                
                                # แปลงค่า EV กลับเป็นเปอร์เซ็นต์ (%)
                                row[f"{pr*100:.1f}% Profit"] = ev * 100 
                                
                            sim_data.append(row)
                        
                        # 3. เตรียมข้อมูลและเซต Index
                        df_full = pd.DataFrame(sim_data)
                        df_full = df_full.set_index("Win Rate")
                        
                        # 4. แปลงข้อมูลเป็นตัวเลขเพื่อทำ Style
                        df_numeric = df_full.astype(float)
                        
                        # 5. สร้าง Styler และจัด Format เป็น %
                        st_table = df_numeric.style.background_gradient(cmap="RdYlGn", axis=None).format("{:.2f}%")
                        
                        # 6. แสดงผลผ่านตาราง
                        st.dataframe(st_table, use_container_width=True)
                        
                        st.caption(f"ตารางแสดง Expected Return (%) ต่อไม้ โดยอ้างอิงจาก Avg Loss ฐานข้อมูลที่ {ls_val:.2f}%")
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
        # สมมติว่าถ้ายังไม่ปิด Close_Price จะเป็น 0 หรือเป็นค่าว่าง
        # หากคอลัมน์พี่อ้ำชื่ออื่น (เช่น 'Status' ที่บอกว่า 'Open') ให้เปลี่ยนในบรรทัดถัดไปครับ
        closed_trades = tfex_df[tfex_df['Close_Price'] > 0] if not tfex_df.empty and 'Close_Price' in tfex_df.columns else tfex_df
        total_pnl = closed_trades['Net_Profit'].sum() if not closed_trades.empty and 'Net_Profit' in closed_trades.columns else 0
        
        # 3. คำนวณเงินต้นสุทธิ
        # ใช้ .astype(str).str.lower() เพื่อป้องกันปัญหาตัวอักษรพิมพ์เล็ก/ใหญ่
        total_deposit = cash_df[cash_df['Type'].astype(str).str.lower() == 'deposit']['Amount'].sum() if not cash_df.empty else 0
        total_withdraw = cash_df[cash_df['Type'].astype(str).str.lower() == 'withdraw']['Amount'].sum() if not cash_df.empty else 0
        net_capital = total_deposit - total_withdraw
        
        # 4. คำนวณพอร์ต (ใช้ Realized PnL)
        net_worth = net_capital + total_pnl
        growth_pct = (total_pnl / net_capital * 100) if net_capital > 0 else 0
        
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
        perf_df['Date_Close'] = pd.to_datetime(perf_df['Date_Close'])
        days_ago = period_options[selected_period]
        if days_ago != 9999:
            cutoff_date = pd.Timestamp.now() - pd.Timedelta(days=days_ago)
            perf_df = perf_df[perf_df['Date_Close'] >= cutoff_date]
    
        # 3. คำนวณ Metrics ทั้งหมดจาก perf_df ที่กรองแล้ว
        total_trades = len(perf_df)
        win_trades = len(perf_df[perf_df['Net_Profit'] > 0])
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
            
            c1, c2 = st.columns(2)
            # เปลี่ยนเป็น Slider เลือกความเสี่ยง 0% ถึง 5% (เพิ่มทีละ 0.25% เพื่อความละเอียด)
            risk_pct = c1.slider("ความเสี่ยงที่ยอมรับได้ (% ของพอร์ต)", min_value=0.0, max_value=5.0, value=1.0, step=0.25)
            stop_loss_points = c2.number_input("ระยะห่างจุดตัดขาดทุน (จุด)", value=2.0)
            
            # คำนวณเงินที่ยอมขาดทุนได้จริงจากเปอร์เซ็นต์พอร์ต (Net Worth)
            risk_amount = net_worth * (risk_pct / 100.0)
            
            # ใช้ตัวแปร Global ที่เราตั้งค่าไว้
            im_per_contract = IM_PER_CONTRACT 
            
            # คำนวณสัญญา
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
                # สมมติฐาน: ถ้าในข้อมูลมีคอลัมน์ 'ATR' อยู่แล้ว จะนำมาใช้คำนวณทันที 
                # แต่ถ้ายังไม่มี ให้กำหนดค่า ATR จำลองหรือดึงจากฟังก์ชันคำนวณ ATR ของคุณมาใส่แทนได้ครับ
                if 'ATR' not in open_positions.columns:
                    open_positions['ATR'] = 10.0  # ค่า ATR สมมติ (ปรับเปลี่ยนตามหน้างานจริงของคุณ)
                
                # แปลงข้อมูลราคาเปิดและ ATR ให้เป็นตัวเลขเพื่อความปลอดภัย
                open_positions['Open_Price'] = pd.to_numeric(open_positions['Open_Price'], errors='coerce')
                open_positions['ATR'] = pd.to_numeric(open_positions['ATR'], errors='coerce')
                
                # คำนวณจุด Stop Loss จาก ATR (ใช้ตัวคูณ 2 เท่าจากราคาเปิด สำหรับ Long Position)
                # สูตร: Stop Loss = ราคาซื้อ - (ATR * Multiplier)
                multiplier = 2.0
                open_positions['ATR_Stop_Loss'] = open_positions['Open_Price'] - (open_positions['ATR'] * multiplier)
                
                # แสดงผลตารางพร้อมคอลัมน์ ATR และ Stop Loss ที่เพิ่มเข้ามา
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
            
                # กำหนดค่า ATR เริ่มต้นหากยังไม่เคยกดปุ่ม
                current_atr = st.session_state.get('active_atr', 6.5)
            
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
                    
                    # แสดงช่อง ATR และตัวคูณเพื่อให้ระบบคำนวณจุดหนีความเสี่ยงอัตโนมัติ
                    atr_multiplier = st.number_input("ตัวคูณ ATR (Multiplier):", min_value=0.5, step=0.1, value=1.5)
                    calculated_sl_pts = current_atr * atr_multiplier
                    st.write(f"📌 Stop Loss แนะนำ: **{calculated_sl_pts:.2f} จุด** (จาก ATR: {current_atr})")
                    
                    reason = st.text_area("เหตุผลที่เข้าเทรด:")
                
                # ปุ่มยืนยันการเปิดสถานะเทรดจริง
                submit_trade = st.form_submit_button("เปิดสถานะเทรด")
                
                if submit_trade:
                    final_trade_id = trade_id_input.strip()
                    if not final_trade_id:
                        final_trade_id = f"TX-{pd.Timestamp.now().strftime('%Y%m%d%H%M%S')}"
                        
                    # คำนวณราคา Stop Loss จริงบนกระดาน
                    calculated_sl_price = (entry - calculated_sl_pts) if Status == "Long" else (entry + calculated_sl_pts)
                        
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
                        "Reason": f"{reason} | ATR SL: {calculated_sl_price:.2f}"
                    }
                    
                    df_to_save = pd.DataFrame([new_record])
                    
                    with st.spinner("⏳ กำลังเปิดสถานะและบันทึกลง Google Sheets..."):
                        if save_data_to_sheet(df_to_save, "TFEX_History"):
                            st.cache_data.clear()  
                            st.toast("เปิดสถานะเทรดเรียบร้อย! 🎉", icon="✅")
                            st.rerun()
        
        with sub_tfex_close:
            st.subheader("🏁 ปิดสถานะเทรด")
            
            # ดึงข้อมูลจากฟังก์ชัน load_data สดๆ ใหม่ๆ
            tfex_df = load_data("TFEX_History")
            
            # กรองเฉพาะรายการที่ยังถืออยู่
            tfex_df['Close_Price_Cleaned'] = pd.to_numeric(tfex_df['Close_Price'], errors='coerce').fillna(0)
            open_trades = tfex_df[tfex_df['Close_Price_Cleaned'] == 0]
            
            if not open_trades.empty:
                # ให้เลือก Trade_ID
                selected_trade_id = st.selectbox("เลือก Trade ที่ต้องการปิด:", open_trades['Trade_ID'].tolist())
                
                # แสดงรายละเอียดออเดอร์เดิมให้เห็นก่อนปิด
                trade_detail = open_trades[open_trades['Trade_ID'] == selected_trade_id].iloc[0]
                st.info(f"🔍 รายละเอียดออเดอร์เดิม: **{trade_detail['Status']}** จำนวน **{trade_detail['Size']}** สัญญา ที่ราคา **{trade_detail['Open_Price']}**")
                
                # ฟอร์มกรอกข้อมูลปิดสถานะ
                c_col1, c_col2 = st.columns(2)
                close_price = c_col1.number_input("ราคาปิด:", value=float(trade_detail['Open_Price']), step=0.1, format="%.2f")
                close_date = c_col2.date_input("วันที่ปิด:")
                
                if st.button("ยืนยันการปิดสถานะ", use_container_width=True, type="primary"):
                    # บันทึกปิดสถานะพร้อม Loading Spinner และล้าง Cache ทันที
                    with st.spinner("⏳ กำลังบันทึกการปิดสถานะและคำนวณผลลัพธ์..."):
                        success = update_trade_close('1moD7gjKnnLXDvCTfwVVhBmDwo5t0c7emErGbtJtGEWU', selected_trade_id, close_price, str(close_date))
                        if success:
                            st.cache_data.clear()  # ล้าง Cache ข้อมูลในหน่วยความจำ
                            st.toast("ปิดสถานะสำเร็จ และคำนวณกำไรเรียบร้อย! 🏁", icon="🏆")
                            st.rerun()             # โหลดหน้าจอใหม่เพื่อให้ข้อมูลปัจจุบันที่สุดแสดงทันที
            else:
                st.info("ไม่มีรายการที่ถือครองอยู่ครับ")
                
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
                closed_trades = tfex_df[tfex_df['Close_Price'] > 0].copy()
                closed_trades['Date_Close'] = pd.to_datetime(closed_trades['Date_Close'])
                
                # 3. ตารางแสดงราย Series (เปรียบเทียบว่า Series ไหนเทรดแล้วกำไรที่สุด)
                st.write("📊 สรุปผลงานราย Series:")
                series_perf = perf_df.groupby('Series').agg({
                    'Net_Profit': 'sum',
                    'Trade_ID': 'count'
                }).rename(columns={'Trade_ID': 'Trades', 'Net_Profit': 'Total PnL'})
                
                st.dataframe(series_perf.sort_values(by='Total PnL', ascending=False), use_container_width=True)

                # --- กราฟแสดงการเติบโตของพอร์ต TFEX ---
                st.subheader("📈 กราฟการเติบโตของพอร์ต (Portfolio Growth)")
                
                # 1. เตรียมข้อมูลเพื่อทำกราฟ
                # นำข้อมูลที่ปิดสถานะแล้วมาเรียงตามวันที่ปิด
                growth_df = perf_df.sort_values('Date_Close').copy()
                
                # คำนวณกำไรสะสม
                growth_df['Cumulative_Profit'] = growth_df['Net_Profit'].cumsum()
                
                # นำไปรวมกับเงินต้นเริ่มต้น (net_capital)
                growth_df['Portfolio_Value'] = net_capital + growth_df['Cumulative_Profit']
                
                # เพิ่มบรรทัดเริ่มที่จุดศูนย์ (วันเริ่มต้น)
                start_date = growth_df['Date_Close'].min() - pd.Timedelta(days=1)
                start_row = pd.DataFrame({'Date_Close': [start_date], 'Portfolio_Value': [net_capital]})
                growth_df = pd.concat([start_row, growth_df[['Date_Close', 'Portfolio_Value']]], ignore_index=True)
                
                # 2. สร้างกราฟเส้นด้วย Plotly
                fig_growth = px.line(
                    growth_df, 
                    x='Date_Close', 
                    y='Portfolio_Value',
                    markers=True,
                    line_shape='spline' # ให้เส้นดูโค้งมนสวยงาม
                )
                
                # ปรับแต่งให้ดูโปร
                fig_growth.update_traces(line=dict(color='#26A69A', width=3))
                fig_growth.update_layout(
                    xaxis_title="วันที่",
                    yaxis_title="มูลค่าพอร์ต (บาท)",
                    margin=dict(l=20, r=20, t=30, b=20),
                    hovermode="x unified"
                )
                
                st.plotly_chart(fig_growth, use_container_width=True)

                # --- สรุปผลรายเดือนแบบ Combo Chart & Table ---
                st.divider()
                st.subheader("🗓 สรุปผลรายเดือน")
                
                # 1. จัดเตรียมและคำนวณค่าต่างๆ ให้เสร็จก่อนสร้างตาราง
                monthly_perf = closed_trades.groupby(closed_trades['Date_Close'].dt.to_period('M'))['Net_Profit'].sum().reset_index()
                monthly_perf['Month'] = monthly_perf['Date_Close'].dt.strftime('%Y-%m')
                
                # คำนวณค่าสถิติต่างๆ
                monthly_perf['Cumulative_Profit'] = monthly_perf['Net_Profit'].cumsum()
                monthly_perf['Portfolio_Value'] = net_capital + monthly_perf['Cumulative_Profit']
                monthly_perf['Monthly_Return_Pct'] = (monthly_perf['Net_Profit'] / net_capital) * 100
                monthly_perf['Cumulative_Pct'] = (monthly_perf['Cumulative_Profit'] / net_capital) * 100
                
                # 2. วาดกราฟ Plotly Combo
                bar_colors = ['#26A69A' if val >= 0 else '#EF5350' for val in monthly_perf['Net_Profit']]
                fig = make_subplots(specs=[[{"secondary_y": True}]])
                
                fig.add_trace(go.Bar(x=monthly_perf['Month'], y=monthly_perf['Net_Profit'], name="กำไร/ขาดทุน", marker_color=bar_colors), secondary_y=False)
                fig.add_trace(go.Scatter(x=monthly_perf['Month'], y=monthly_perf['Cumulative_Pct'], name="% สะสม", mode='lines+markers', line=dict(color='#FFA500', width=3)), secondary_y=True)
                
                fig.update_layout(title_text="Monthly Performance", height=400, margin=dict(l=20, r=20, t=40, b=20), showlegend=True)
                st.plotly_chart(fig, use_container_width=True)
                
                # 3. สร้างตารางสรุป
                def color_negative_red(val):
                    if isinstance(val, (int, float)):
                        color = '#26A69A' if val > 0 else '#EF5350' if val < 0 else 'black'
                        return f'color: {color}'
                    return None
    
                monthly_df = monthly_perf[['Month', 'Net_Profit', 'Monthly_Return_Pct', 'Portfolio_Value', 'Cumulative_Pct']]
                monthly_df.columns = ['เดือน', 'กำไร/ขาดทุน (บาท)', '% รายเดือน', 'มูลค่าพอร์ต (บาท)', '% สะสม']

                # --- CSS สำหรับจัดตารางให้ชิดขวา ---
                # สร้าง Style object ขึ้นมา
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
                st.warning("ยังไม่มีข้อมูลรายการเทรดที่ปิดสถานะแล้วครับ")

# ------------------------------
if __name__ == "__main__":
    main()
    
