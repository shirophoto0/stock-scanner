# =============================================================
# backend_functions.py
# รวมฟังก์ชันเบื้องหลัง (เชื่อม Google Sheets, คำนวณ, โหลด/บันทึกข้อมูล)
# แยกออกมาจาก App.py เพื่อให้จัดการง่ายขึ้น (Phase 1 ของการแยกไฟล์)
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
from constants import SET100_TICKERS

# 🆕 ระบบ Login หลายผู้ใช้: ฟังก์ชันนี้คืนชื่อ Google Sheet ของผู้ใช้ที่ล็อกอินอยู่ตอนนี้
# (ตั้งค่าไว้ตอน Login สำเร็จใน auth.py) ถ้ายังไม่มีการล็อกอิน จะใช้ 'MyStockData' เป็นค่าเริ่มต้น
def get_active_sheet_name():
    return st.session_state.get('active_sheet_name', get_active_sheet_name())

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
            creds_dict = dict(st.secrets["gcp_service_account"])
            
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds)
        
    except Exception as e:
        print(f"Error ในการเชื่อมต่อ Google Sheets: {e}")
        raise e


# 🔧 แก้บั๊ก: จุดสำคัญที่ช่วยลดปัญหา "Google Sheets API เกินโควตา (429)"
# เดิม client.open('MyStockData') ถูกเรียกซ้ำๆ หลายสิบครั้งในทุกครั้งที่หน้าเว็บโหลด/รีเฟรช
# (ทุกฟังก์ชันที่ต้องใช้ชีต จะเปิดสเปรดชีตด้วยชื่อใหม่ทุกครั้ง ซึ่งกิน API quota เยอะมาก)
# ตอนนี้ "จำ" สเปรดชีตที่เปิดไว้แล้วไว้ 5 นาที ทุกฟังก์ชันที่เรียกชื่อเดียวกันจะใช้ตัวที่จำไว้แทน
# การเปิดซ้ำ ลดจำนวนครั้งที่ยิง API ลงได้มาก โดยไม่กระทบพฤติกรรมการทำงานของแอปเลย
@st.cache_resource(ttl=300, show_spinner=False)
def get_cached_spreadsheet(_client, spreadsheet_name):
    return _client.open(spreadsheet_name)


# =============================================================
# 2. ฟังก์ชันจัดการ Google Sheets & ข้อมูลทรัพย์สิน (Wealth & Google Sheets)
# =============================================================
def get_worksheet_safely(client, spreadsheet_name, worksheet_name, retries=3, delay=2):
    """ฟังก์ชันเปิด Google Sheet พร้อมระบบป้องกันและลองใหม่เมื่อติดปัญหา Quota Exceeded (429)"""
    for attempt in range(retries):
        try:
            sheet = get_cached_spreadsheet(client, spreadsheet_name).worksheet(worksheet_name)
            return sheet
        except APIError as e:
            if "429" in str(e) or "Quota exceeded" in str(e):
                if attempt < retries - 1:
                    time.sleep(delay * (attempt + 1))
                    continue
                else:
                    st.error("❌ Google Sheets API เกินโควตาชั่วคราว (Rate Limit 429) กรุณารอสักครู่แล้วลองรีเฟรชหน้าจอใหม่อีกครั้งครับ")
                    return None
            else:
                st.error(f"❌ เกิดข้อผิดพลาดเกี่ยวกับ Google Sheets API: {e}")
                return None
        except Exception as e:
            st.error(f"❌ ไม่สามารถเปิด Google Sheets ได้: {e}")
            return None
    return None
    
def check_and_auto_stamp_portfolio(client, current_total_value):
    try:
        sheet_history = get_cached_spreadsheet(client, get_active_sheet_name()).worksheet('Stock_TFEX_History')
        data = sheet_history.get_all_records()
        
        last_recorded_month = ""
        if data:
            last_date_str = str(data[-1].get('Date', ''))
            if last_date_str:
                last_recorded_month = last_date_str[:7] # ตัดเอาแค่ 'YYYY-MM'
        
        today = datetime.today()
        prev_month_date = today.replace(day=1) - timedelta(days=5)
        target_month_str = prev_month_date.strftime('%Y-%m')
        target_date_str = prev_month_date.strftime('%Y-%m-%d')
        
        if last_recorded_month != target_month_str:
            sheet_history.append_row([target_date_str, current_total_value])
            st.toast(f"📊 ระบบบันทึกยอดพอร์ตหุ้น+TFEX สิ้นเดือนอัตโนมัติเรียบร้อย: {target_month_str}", icon="✅")
            
    except Exception as e:
        pass

def extract_pvd_from_image(image_file, year_be, month_name="ธันวาคม"):
    try:
        api_key = st.secrets.get("GOOGLE_API_KEY", "")
        if not api_key:
            st.error("ไม่พบ GOOGLE_API_KEY ใน st.secrets กรุณาตรวจสอบการตั้งค่า")
            return None
            
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-3.5-flash')
                
        year_ce = int(year_be) - 543
        
        prompt = f"""
        คุณเป็นผู้ช่วยทางการเงินอัจฉริยะ หน้าที่ของคุณคืออ่านรูปภาพรายงานยอดรวมกองทุนสำรองเลี้ยงชีพของเดือน {month_name} ปี พ.ศ. {year_be} (ค.ศ. {year_ce}) นี้ 
        โดยให้สังเกตที่มุมขวาบนของเอกสารจะมีหัวข้อ "อัตราผลตอบแทนรายบุคคล % (Individual YTD Net Return %)" อยู่ (เช่น 7.01 %)
        และในรูปจะมีตาราง "ยอดรวมทุกนโยบายการลงทุน (Total Portfolio Balance)" ซึ่งแยกรายการย่อยออกมาดังนี้:
        1. ยอดยกมา (Balance as of)
        2. เงินเข้าระหว่างปี (Transferred in during this year)
        
        โปรดสกัดข้อมูลตัวเลขทั้งหมดตามหัวตาราง CSV ด้านล่างนี้ให้ออกมาเป็นข้อมูลของเดือน {month_name} ปี {year_ce}:
        
        หัวตาราง CSV:
        Month,Year_CE,Year_BE,Brought_Forward_Member_Saving,Brought_Forward_Member_Benefit,Brought_Forward_Employer_Matching,Brought_Forward_Employer_Benefit,Transferred_Member_Saving,Transferred_Member_Benefit,Transferred_Employer_Matching,Transferred_Employer_Benefit,Member_Saving,Member_Benefit,Member_Total,Employer_Matching,Employer_Benefit,Employer_Total,Grand_Total,Total_Units,YTD_Net_Return_Pct
        
        คำอธิบายฟิลด์ข้อมูล:
        - Month: {month_name}
        - Year_CE: {year_ce}
        - Year_BE: {year_be}
        - Brought_Forward_Member_Saving: ยอดสะสมยกมา (แถว "ยอดยกมา" ช่องเงินสะสมส่วนของสมาชิก)
        - Brought_Forward_Member_Benefit: ผลประโยชน์ยกมา (แถว "ยอดยกมา" ช่องผลประโยชน์ส่วนของสมาชิก)
        - Brought_Forward_Employer_Matching: เงินสมทบยกมา (แถว "ยอดยกมา" ช่องเงินสมทบส่วนของนายจ้าง)
        - Brought_Forward_Employer_Benefit: ผลประโยชน์เงินสมทบยกมา (แถว "ยอดยกมา" ช่องผลประโยชน์ส่วนของนายจ้าง)
        - Transferred_Member_Saving: เงินสะสมเข้าระหว่างปี (แถว "เงินเข้าระหว่างปี" ช่องเงินสะสมส่วนของสมาชิก)
        - Transferred_Member_Benefit: ผลประโยชน์เงินสะสมเข้าระหว่างปี (แถว "เงินเข้าระหว่างปี" ช่องผลประโยชน์ส่วนของสมาชิก)
        - Transferred_Employer_Matching: เงินสมทบเข้าระหว่างปี (แถว "เงินเข้าระหว่างปี" ช่องเงินสมทบส่วนของนายจ้าง)
        - Transferred_Employer_Benefit: ผลประโยชน์เงินสมทบเข้าระหว่างปี (แถว "เงินเข้าระหว่างปี" ช่องผลประโยชน์ส่วนของนายจ้าง)
        - Member_Saving: ยอดเงินสะสมรวม (รวม Total)
        - Member_Benefit: ผลประโยชน์เงินสะสมรวม (รวม Total)
        - Member_Total: รวมส่วนของสมาชิก (Total Amount)
        - Employer_Matching: เงินสมทบรวม (รวม Total)
        - Employer_Benefit: ผลประโยชน์เงินสมทบรวม (รวม Total)
        - Employer_Total: รวมส่วนของนายจ้าง (Total Amount)
        - Grand_Total: ยอดรวมทั้งสิ้น
        - Total_Units: จำนวนหน่วยรวม
        - YTD_Net_Return_Pct: อัตราผลตอบแทนรายบุคคล % ที่อยู่มุมขวาบนของเอกสาร (ใส่เฉพาะตัวเลข เช่น 7.01 ถ้าไม่มีให้ใส่ 0.00)
        
        กฎสำคัญในการแสดงผลตัวเลข:
        - ทุกค่าที่เป็น "จำนวนเงิน" หรือ "จำนวนหน่วย" ต้องใส่เครื่องหมายจุลภาค (,) คั่นหลักพันให้ถูกต้อง (เช่น 1,204,406.92) ถ้าไม่มีให้ใส่ 0.00
        - ช่อง YTD_Net_Return_Pct ใส่เฉพาะตัวเลขทศนิยม (เช่น 7.01) ไม่ต้องใส่เครื่องหมาย %
        - โปรดส่งกลับมาเฉพาะข้อมูล CSV ที่สะอาด (หัวตาราง 1 บรรทัด และข้อมูลตัวเลข 1 บรรทัด) ไม่มีคำอธิบายเพิ่มเติม ไม่ต้องใส่เครื่องหมาย ```csv ครอบ
        """
        
        img = Image.open(image_file)
        response = model.generate_content([prompt, img])
        
        csv_text = response.text.replace("```csv", "").replace("```", "").strip()
        df_result = pd.read_csv(io.StringIO(csv_text))
        return df_result
        
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการประมวลผลรูปภาพ: {e}")
        return None

def st_neumorphic_container():
    # สร้าง Container ที่มีขอบนูน
    return st.container(border=True) # ปัจจุบัน streamlit มี parameter border=True ที่สวยงามอยู่แล้ว
    
# 🔧 แก้บั๊ก: เอาโค้ดแต่งสไตล์ CSS ที่เคยอยู่ตรงนี้ออก เพราะเป็นโค้ดระดับบนสุดของไฟล์นี้เช่นกัน
# (รันแค่ครั้งเดียวตอน import ครั้งแรก ไม่ได้ผลกับผู้ใช้คนอื่นๆ อยู่แล้ว และอาจทำให้ Streamlit
# error เรื่องลำดับคำสั่งได้ เนื่องจากรันก่อน st.set_page_config() ซึ่ง Streamlit กำหนดว่าต้องมาก่อนเสมอ)

def get_latest_pvd_value():
    try:
        client = get_gsheet_client()
        sheet = get_cached_spreadsheet(client, get_active_sheet_name()).worksheet('Provident_Fund')
        data = sheet.get_all_records()
        if data:
            df = pd.DataFrame(data)
            latest_val = str(df.iloc[-1]['Grand_Total']).replace(',', '')
            return float(latest_val)
    except:
        return 0.0
    return 0.0

def get_pension_sheet(client):
    try:
        sheet_pen = get_cached_spreadsheet(client, get_active_sheet_name()).worksheet('Pension')
        return sheet_pen
    except Exception:
        return None
        
def get_latest_insurance_value():
    try:
        client = get_gsheet_client()
        sheet_ins = get_cached_spreadsheet(client, get_active_sheet_name()).worksheet('Insurance')
        data = sheet_ins.get_all_records()
        if data:
            df_ins = pd.DataFrame(data)
            if not df_ins.empty and 'Redemption_Value' in df_ins.columns:
                return float(str(df_ins.iloc[-1]['Redemption_Value']).replace(',', ''))
    except Exception:
        pass
    return 0.0

def get_latest_coop_value():
    try:
        client = get_gsheet_client()
        sheet_coop = get_cached_spreadsheet(client, get_active_sheet_name()).worksheet('Coop')
        data = sheet_coop.get_all_records()
        if data:
            df_coop = pd.DataFrame(data)
            if not df_coop.empty and 'Coop_Value' in df_coop.columns:
                return float(str(df_coop.iloc[-1]['Coop_Value']).replace(',', ''))
    except Exception:
        pass
    return 0.0

def calculate_fund_result(cost_price, current_price, units):
    total_cost = cost_price * units
    current_value = current_price * units
    profit_loss = current_value - total_cost
    profit_loss_pct = (profit_loss / total_cost) * 100 if total_cost > 0 else 0
    return {
        "Total_Cost": round(total_cost, 2),
        "Current_Value": round(current_value, 2),
        "Profit_Loss": round(profit_loss, 2),
        "Profit_Loss_Pct": round(profit_loss_pct, 2)
    }
    
# =============================================================
# 3. ฟังก์ชันการจัดการ TFEX และคำนวณทางเทคนิค
# =============================================================
IM_PER_CONTRACT = 13300 

def update_trade_close(trade_id, close_price, date_close):
    try:
        client = get_gsheet_client()
        # 🔧 แก้บั๊ก: เดิมรับ spreadsheet_id ตายตัวจากภายนอก (ผู้เรียกใช้ส่ง ID ตายตัวมา)
        # ตอนนี้เปิดตามชื่อชีตของผู้ใช้ที่ login อยู่แทน สอดคล้องกับฟังก์ชันอื่นในระบบ
        sheet = get_cached_spreadsheet(client, get_active_sheet_name()).worksheet('TFEX_History')
        
        records = sheet.get_all_records()
        df = pd.DataFrame(records)
        
        idx_list = df.index[df['Trade_ID'] == trade_id].tolist()
        if not idx_list:
            print("Error: Trade_ID not found")
            return False
            
        row_index = idx_list[0] + 2 
        trade_row = df.loc[idx_list[0]]
        
        # คำนวณผลลัพธ์
        open_price_val = float(trade_row['Open_Price'])
        size_val = int(trade_row['Size'])
        comm_val = size_val * 50
        
        calc = calculate_tfex_result(
            open_price_val, 
            float(close_price), 
            size_val, 
            comm_val, 
            str(trade_row['Status'])
        )
        
        # คำนวณ Points
        if str(trade_row['Status']) == 'Long':
            points = float(close_price) - open_price_val
        else:
            points = open_price_val - float(close_price)
        
        # ⭐️ สำคัญมาก: แปลงข้อมูลทั้งหมดให้เป็น Python Native Type (ป้องกัน TypeError จาก gspread)
        data_to_update = [
            str(date_close),                 # C: Date_Close
            str(trade_row['Series']),        # D: Series
            str(trade_row['Status']),        # E: Status
            int(size_val),                   # F: Size
            float(open_price_val),           # G: Open_Price
            float(close_price),              # H: Close_Price
            float(calc['Realized']),         # I: Realized
            float(comm_val),                 # J: Comm
            float(calc['Net_Profit']),       # K: Net_Profit
            str(calc['Win_Lose']),           # L: Win_Lose
            round(float(points), 2)          # M: Points
        ]
        
        # อัปเดตข้อมูลลง Google Sheets แบบระบุ Range
        sheet.update(range_name=f'C{row_index}:M{row_index}', values=[data_to_update])
        
        return True
    except Exception as e:
        # ปริ้น Error จริงออกมาดูใน Console ของ Streamlit Cloud
        print(f"Detailed Error in update_trade_close: {e}")
        return False 
        

@st.cache_data(ttl=3600, show_spinner=False)
def get_auto_atr_cached(symbol="^SET50"):
    """ดึงข้อมูลราคาและคำนวณ ATR ย้อนหลัง 14 วัน"""
    try:
        data = yf.download(symbol, period="1m", interval="1d", progress=False)
        
        if data.empty or len(data) < 15:
            return 6.5  
        
        high = data['High']
        low = data['Low']
        close = data['Close']
        
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
        return 6.5

def calculate_tfex_result(entry, close, size, comm, Status):
    multiplier = 200
    points = (close - entry) if Status == "Long" else (entry - close)
    realized = points * size * multiplier
    net_profit = realized - comm
    win_lose = "Win" if net_profit > 0 else "Lose"
    
    return {
        "Realized": round(realized, 2),
        "Net_Profit": round(net_profit, 2),
        "Win_Lose": win_lose,
        "Points": round(points, 2)
    }


# =============================================================
# 4. ฟังก์ชันการจัดการบันทึกข้อมูลและเงินสด (Logging & Cash Balance)
# =============================================================
def load_total_cash_balance():
    """คำนวณเงินสดคงเหลือที่แท้จริง: (ยอดรวม Cash Flow ทั้งหมด) - (ผลรวม shares * avg_price ของทุกหุ้นในพอร์ต)"""
    try:
        client = get_gsheet_client()
        spreadsheet_name = get_active_sheet_name()
        
        # 1. ดึงยอดรวมจากชีต Cash_Flow ทั้งหมด
        sheet_cash = get_cached_spreadsheet(client, spreadsheet_name).worksheet('CashFlow')
        records_cash = sheet_cash.get_all_records()
        
        total_cash_flow = 0.0
        if records_cash:
            df_cash = pd.DataFrame(records_cash)
            if 'Amount' in df_cash.columns:
                df_cash['Amount'] = pd.to_numeric(df_cash['Amount'], errors='coerce').fillna(0)
                total_cash_flow = float(df_cash['Amount'].sum())
                
        # 2. บังคับคำนวณต้นทุนหุ้นทั้งหมดจาก shares * avg_price โดยตรง
        sheet_portfolio = get_cached_spreadsheet(client, spreadsheet_name).worksheet('PortfolioData')
        records_portfolio = sheet_portfolio.get_all_records()
        
        total_stock_cost = 0.0
        if records_portfolio:
            for row in records_portfolio:
                # จัดการ key ให้สะอาด ป้องกันปัญหาเรื่องเว้นวรรค
                cleaned_row = {str(k).strip(): v for k, v in row.items()}
                
                try:
                    # ดึงค่าหุ้น (รองรับทั้งชื่อภาษาอังกฤษและไทย)
                    shares_val = cleaned_row.get('shares', cleaned_row.get('จำนวน', 0))
                    shares = float(str(shares_val).replace(',', '')) if shares_val not in [None, ''] else 0.0
                except (ValueError, TypeError):
                    shares = 0.0
                    
                try:
                    # ดึงค่าต้นทุนเฉลี่ย (รองรับทั้งชื่อภาษาอังกฤษและไทย)
                    avg_val = cleaned_row.get('avg_price', cleaned_row.get('ต้นทุนเฉลี่ย', 0.0))
                    avg_price = float(str(avg_val).replace(',', '')) if avg_val not in [None, ''] else 0.0
                except (ValueError, TypeError):
                    avg_price = 0.0
                    
                # นำจำนวนหุ้นคูณต้นทุนเฉลี่ย แล้วบวกสะสมเข้าไป
                total_stock_cost += (shares * avg_price)
                    
        # 3. เงินสดคงเหลือที่แท้จริง = ยอดรวม Cash Flow - ต้นทุนหุ้นในพอร์ต
        actual_cash_balance = total_cash_flow - total_stock_cost
        
        return float(actual_cash_balance)
        
    except Exception as e:
        st.error(f"❌ เกิดข้อผิดพลาดในการคำนวณเงินสด: {e}")
        return 0.0
        
# =============================================================
# 5. ฟังก์ชันการจัดการ Cash Balance และข้อมูลพอร์ตการลงทุน (Portfolio & Cash)
# =============================================================

# --- 🔧 แก้บั๊ก: เอาโค้ดกำหนดค่าเริ่มต้น Cash Balance ที่เคยอยู่ตรงนี้ออก
# เพราะเป็นโค้ดระดับบนสุดของไฟล์นี้ (backend_functions.py) ซึ่งจะรันแค่ครั้งเดียวตอน import ครั้งแรกเท่านั้น
# ไม่ได้รันซ้ำทุกครั้งที่มีคนเปิดแอปเหมือนโค้ดใน App.py ทำให้คนที่เปิดแอปทีหลังได้ค่าผิด (ดู App.py แทน) ---


def save_cash_balance(balance):
    try:
        # อัปเดตค่าใน session_state ทันที
        st.session_state.cash_balance = float(balance)
        st.toast(f"บันทึกยอดเงินสดคงเหลือสำเร็จ: {balance:,.2f} บาท", icon="✅")
    except Exception as e:
        st.error(f"Error saving cash balance: {e}")


def save_cash_to_gsheet(df):
    """
    ฟังก์ชันเฉพาะสำหรับบันทึกรายการเงินเข้าหน้า Cash_Flow เท่านั้น
    """
    if df.empty:
        st.warning("ไม่มีข้อมูลที่จะบันทึก")
        return False
        
    try:
        client = get_gsheet_client()
        sheet = get_cached_spreadsheet(client, get_active_sheet_name()).worksheet("Cash_Flow")
        sheet.append_rows(df.values.tolist())
        return True
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการบันทึก Cash_Flow: {e}")
        return False 


def save_data_to_sheet(new_df, sheet_name):
    try:
        client = get_gsheet_client()
        # 🔧 แก้บั๊ก: เดิมเขียน ID ของ Google Sheet ตายตัวไว้ ตอนนี้เปลี่ยนตามผู้ใช้ที่ login แล้ว
        sheet = get_cached_spreadsheet(client, get_active_sheet_name()).worksheet('TFEX_History')
        
        cols = ["Trade_ID", "Date_Open", "Date_Close", "Series", "Status", "Size", "Open_Price", 
                "Close_Price", "Realized", "Comm", "Net_Profit", "Win_Lose", "Reason"]
        
        new_df = new_df.reindex(columns=cols)
        sheet.append_rows(new_df.values.tolist())
        
        st.cache_data.clear() 
        st.success("เปิดสถานะสำเร็จ!")
        st.rerun()            
        
        return True
    except Exception as e:
        st.error(f"บันทึกข้อมูลไม่สำเร็จ: {e}")
        return False


# =============================================================
# 6. ฟังก์ชันการจัดการข้อมูลเงินปันผล (Dividend Management)
# =============================================================
DIVIDEND_FILE = "dividend_data.csv"

def load_dividend_data():
    if os.path.exists(DIVIDEND_FILE):
        try:
            df = pd.read_csv(DIVIDEND_FILE)
            return df.to_dict('records')
        except Exception as e:
            print(f"Error loading CSV: {e}")
            return []
    return []


def save_dividend_data(df_div=None):
    """ฟังก์ชันบันทึกข้อมูลปันผล ป้องกัน Error JSON และป้องกันชีทพัง"""
    try:
        if df_div is None:
            if "dividend_data" in st.session_state and st.session_state.dividend_data:
                df_div = pd.DataFrame(st.session_state.dividend_data)
            else:
                df_div = pd.DataFrame(columns=[
                    "วันที่ได้รับ", "Ticker", "จำนวนหุ้น", "ปันผลต่อหุ้น", 
                    "ยอดรวมก่อนภาษี", "ภาษีหัก ณ ที่จ่าย", "ยอดรับสุทธิ", "ต้นทุนหุ้น", "หมายเหตุ"
                ])

        # 1. บันทึกลง session_state
        st.session_state.dividend_data = df_div.to_dict('records')
         
        # 2. บันทึกลง CSV ท้องถิ่น
        df_div.to_csv(DIVIDEND_FILE, index=False, encoding='utf-8-sig')
         
        # 3. บันทึกลง Google Sheets แบบปลอดภัย
        try:
            client = get_gsheet_client()
            sheet = get_cached_spreadsheet(client, get_active_sheet_name()).worksheet('Dividend')
            
            df_clean = df_div.fillna("")
            data_to_write = [df_clean.columns.tolist()] + df_clean.astype(str).values.tolist()
            
            if len(data_to_write) > 0:
                sheet.update(range_name=f"A1:I{len(data_to_write)}", values=data_to_write)
                
        except Exception as gsheet_err:
            st.warning(f"⚠️ บันทึกลงเครื่องสำเร็จ แต่ซิงค์ Google Sheets ไม่สำเร็จ: {gsheet_err}")
             
        return True
    except Exception as e:
        st.error(f"❌ เกิดข้อผิดพลาดในการบันทึกข้อมูล: {e}")
        return False


# =============================================================
# 7. ฟังก์ชันการคำนวณทางเทคนิคและดึงข้อมูลตลาด (Technical & Market Data)
# =============================================================
def calculate_atr(df, period=14):
    """คำนวณค่า Average True Range (ATR) จากข้อมูลราคา"""
    if df.empty or len(df) < period:
        return 10.0 
    
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


@st.cache_data(ttl=60)
def load_data(sheet_name):
    try:
        client = get_gsheet_client()
        sheet = get_cached_spreadsheet(client, get_active_sheet_name()).worksheet(sheet_name) 
        data = sheet.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"โหลดข้อมูล {sheet_name} ไม่สำเร็จ: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=3600)  
def get_cached_stock_info(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        if not info or len(info) <= 1:
            return {}
        return info
    except Exception as e:
        print(f"Warning: Could not fetch info for {ticker} due to: {e}")
        return {}


# =============================================================
# 8. ฟังก์ชันการจัดการบันทึกและซิงค์ข้อมูลลง Google Sheets (Sync & Sheets Operations)
# =============================================================
def clear_and_save_data(df, sheet_name):
    try:
        client = get_gsheet_client()
        sheet = get_cached_spreadsheet(client, get_active_sheet_name()).worksheet('TradingPlan')
        
        sheet.clear()
        
        cols = ['Ticker', 'Entry_Price', 'แนวรับ', 'แนวต้าน', 'ราคาตลาด', 'Stop_Loss', 'Take_Profit', 'ห่างจาก_SL(%)', 'สถานะ', 'Alert_Date', 'Timestamp', 'Image_URL']
        save_df = df[[c for c in cols if c in df.columns]]
        
        data_to_save = [save_df.columns.tolist()] + save_df.fillna("").values.tolist()
        sheet.update('A1', data_to_save)
        return True
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาด: {e}")
        return False


def save_to_gsheet(df, sheet_name='StockData'):
    client = get_gsheet_client()
    # 🔧 แก้บั๊ก: เดิมเขียน ID ของ Google Sheet ตายตัวไว้ ตอนนี้เปลี่ยนตามผู้ใช้ที่ login แล้ว
    sheet = get_cached_spreadsheet(client, get_active_sheet_name()).worksheet('StockData')
    
    df = df.replace([np.inf, -np.inf], 0).fillna("")
    data_to_write = [df.columns.tolist()] + df.values.tolist()
    
    sheet.update(range_name='A1', values=data_to_write)
    print(f"บันทึกข้อมูลลง {sheet_name} สำเร็จ!")


def save_journal():
    df_temp = pd.DataFrame(st.session_state.journal_data)
    
    date_cols = ['วันที่', 'วันที่ซื้อ', 'วันที่ขาย']
    for col in date_cols:
        if col in df_temp.columns:
            df_temp[col] = pd.to_datetime(df_temp[col], errors='coerce').dt.strftime('%Y-%m-%d')
            
    client = get_gsheet_client()
    sheet = get_cached_spreadsheet(client, get_active_sheet_name()).worksheet('JournalData')
    
    sheet.clear()
    sheet.update([df_temp.columns.values.tolist()] + df_temp.fillna('').values.tolist())


def load_journal():
    try:
        client = get_gsheet_client()
        sheet = get_cached_spreadsheet(client, get_active_sheet_name()).worksheet('JournalData')
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
        sheet = get_cached_spreadsheet(client, get_active_sheet_name()).worksheet('PortfolioData')
        
        sheet.clear() 
        if st.session_state.my_portfolio:
            df = pd.DataFrame(st.session_state.my_portfolio)
            sheet.update([df.columns.values.tolist()] + df.fillna('').values.tolist())
            st.toast("บันทึกข้อมูลพอร์ตเรียบร้อย!", icon="✅") 
        else:
            st.toast("ข้อมูลพอร์ตว่างเปล่า", icon="⚠️")
            
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการบันทึกพอร์ต: {e}")


def load_portfolio():
    try:
        client = get_gsheet_client()
        sheet = get_cached_spreadsheet(client, get_active_sheet_name()).worksheet('PortfolioData')
        data = sheet.get_all_records()
        
        st.session_state.my_portfolio = data if data else []
    except Exception as e:
        st.error(f"โหลดพอร์ตไม่สำเร็จ: {e}")
        st.session_state.my_portfolio = []


def log_portfolio_snapshot():
    """บันทึกยอดพอร์ตรายวันลงตาราง Portfolio_History"""
    client = get_gsheet_client()
    sheet = get_cached_spreadsheet(client, get_active_sheet_name()).worksheet('Portfolio_History')
    
    current_date = datetime.now().strftime('%Y-%m-%d')
    market_val = calculate_total_portfolio_value() 
    total_cash_invested = load_total_cash_balance() 
    
    sheet.append_row([current_date, market_val, total_cash_invested]) 


def calculate_total_portfolio_value():
    """คำนวณมูลค่าหุ้นในพอร์ตปัจจุบัน (Market Value ของหุ้นทั้งหมด)"""
    if 'journal_data' not in st.session_state or not st.session_state.journal_data:
        return 0.0
        
    try:
        df = pd.DataFrame(st.session_state.journal_data)
        if df.empty:
            return 0.0
            
        stock_col = None
        for col in ['หุ้น', 'Ticker', 'Symbol', 'Stock']:
            if col in df.columns:
                stock_col = col
                break
                
        type_col = None
        for col in ['ประเภท', 'Type', 'Transaction']:
            if col in df.columns:
                type_col = col
                break
                
        shares_col = None
        for col in ['จำนวนหุ้นที่ซื้อ', 'จำนวน', 'Shares', 'Volume']:
            if col in df.columns:
                shares_col = col
                break
                
        if not stock_col or not type_col or not shares_col:
            return 0.0

        all_tickers = df[stock_col].unique()
        total_stock_value = 0
        
        for ticker in all_tickers:
            if not ticker or pd.isna(ticker):
                continue
                
            buys = df[(df[stock_col] == ticker) & (df[type_col].astype(str).str.contains("ซื้อ", na=False))][shares_col].sum()
            sells = df[(df[stock_col] == ticker) & (df[type_col].astype(str).str.contains("ขาย", na=False))][shares_col].sum()
            
            try:
                shares = float(buys) - float(sells)
            except:
                shares = 0
            
            if shares > 0:
                try:
                    ticker_obj = yf.Ticker(f"{ticker}.BK")
                    market_price = ticker_obj.fast_info.get('last_price', 0)
                    
                    if not market_price or pd.isna(market_price):
                        hist = ticker_obj.history(period="1d")
                        if not hist.empty:
                            market_price = hist['Close'].iloc[-1]
                        else:
                            market_price = 0
                            
                    total_stock_value += (shares * float(market_price))
                except:
                    pass
                    
        return total_stock_value
        
    except Exception as e:
        return 0.0
        
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
    try:
        # ใช้ .get() เพื่อป้องกัน KeyError รองรับทั้ง 'shares' และ 'จำนวน', รวมถึง 'current_price' และ 'avg_price'
        total_stock_value = sum([
            float(item.get('shares', item.get('จำนวน', 0))) * float(item.get('current_price', item.get('avg_price', 0))) 
            for item in st.session_state.my_portfolio
        ]) if "my_portfolio" in st.session_state else 0
        
        current_cash = st.session_state.get('cash_balance', 0)
        total_equity = total_stock_value + current_cash
        
        # บันทึกข้อมูลลงในตาราง Portfolio_History
        # รูปแบบ: [วันที่, มูลค่าพอร์ตรวม, เงินต้นสะสม]
        log_to_sheet("Portfolio_History", [str(datetime.now().date()), total_equity, total_invested_capital()])
        
    except Exception as e:
        print(f"DEBUG: Error ใน save_portfolio_snapshot: {e}")
    
def display_performance_dashboard():
    # 1. โหลดข้อมูล
    client = get_gsheet_client()
    sheet = get_cached_spreadsheet(client, get_active_sheet_name()).worksheet('Portfolio_History')
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
        try:
            hist = yf.Ticker(f"{ticker}.BK").history(period="max")
            hist.index = pd.to_datetime(hist.index).tz_localize(None)
            price_history[ticker] = hist['Close']
        except:
            pass

    # โหลดข้อมูล CashFlow เผื่อไว้คำนวณเงินลงทุนจริง (ถ้ามี)
    try:
        client = get_gsheet_client()
        sheet_cash = get_cached_spreadsheet(client, get_active_sheet_name()).worksheet('CashFlow')
        cash_data = sheet_cash.get_all_records()
        df_cash = pd.DataFrame(cash_data) if cash_data else pd.DataFrame()
        if not df_cash.empty:
            df_cash.columns = df_cash.columns.str.strip()
            df_cash['Date'] = pd.to_datetime(df_cash['Date'], errors='coerce')
            df_cash['Amount'] = pd.to_numeric(df_cash['Amount'], errors='coerce').fillna(0)
    except:
        df_cash = pd.DataFrame()

    # 3. ลูปคำนวณรายวัน
    for date in all_dates:
        date = date.normalize() 
        df_upto = df[df['วันที่'] <= date]
        
        # คำนวณจำนวนหุ้น
        current_holdings = {}
        for ticker in all_tickers:
            if ticker in price_history:
                buys = df_upto[(df_upto['หุ้น'] == ticker) & (df_upto['ประเภท'].str.contains("ซื้อ", na=False))]['จำนวนหุ้นที่ซื้อ'].sum()
                sells = df_upto[(df_upto['หุ้น'] == ticker) & (df_upto['ประเภท'].str.contains("ขาย", na=False))]['จำนวนหุ้นที่ซื้อ'].sum()
                shares = buys - sells
                if shares > 0:
                    current_holdings[ticker] = shares
        
        # คำนวณ Market Value
        market_val = 0
        for ticker, shares in current_holdings.items():
            if ticker in price_history:
                price_series = price_history[ticker]
                price_at_date = price_series[price_series.index <= date]
                if not price_at_date.empty:
                    market_val += (shares * price_at_date.iloc[-1])
        
        # [จุดที่แก้ไข] คำนวณเงินลงทุนจริงจาก CashFlow สะสม (ไม่เอาเงินหมุนจากการขายมานับซ้ำ)
        if not df_cash.empty and 'Date' in df_cash.columns and 'Amount' in df_cash.columns:
            df_cash_upto = df_cash[df_cash['Date'] <= date]
            invested = df_cash_upto['Amount'].sum() if not df_cash_upto.empty else 1283405
        else:
            # ถ้าไม่มีชีท CashFlow ให้ใช้ทุนเริ่มต้นตายตัว หรือใช้วิ่ายอดซื้อวันแรกสุดครั้งเดียว
            invested = 1283405
        
        history_list.append({
            'Date': date.strftime('%Y-%m-%d'),
            'Market_Value': market_val,
            'Invested_Capital': invested
        })
    
    # 4. บันทึกข้อมูลลงชีท Portfolio_History โดยตรง
    df_history = pd.DataFrame(history_list)
    df_history = df_history.fillna(0)
    
    try:
        client = get_gsheet_client()
        sheet = get_cached_spreadsheet(client, get_active_sheet_name()).worksheet('Portfolio_History')
        
        sheet.clear()
        sheet.update([df_history.columns.values.tolist()] + df_history.values.tolist())
        
        st.success("อัปเดตเรียบร้อย! กราฟของคุณพร้อมใช้งานแล้ว")
        st.rerun()
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการบันทึก Portfolio_History: {e}")
    
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
    # 🔧 แก้บั๊ก: เดิมเขียน ID ของ Google Sheet ตายตัวไว้ ตอนนี้เปลี่ยนตามผู้ใช้ที่ login แล้ว
    sheet = get_cached_spreadsheet(client, get_active_sheet_name()).worksheet('StockData')
    
    # 1. เตรียมข้อมูล: แปลง Header และข้อมูลเป็น list
    data_to_update = [df.columns.values.tolist()] + df.values.tolist()
    
    # 2. ใช้ update แทน clear() 
    # วิธีนี้จะเขียนทับตั้งแต่เซลล์ A1 ยาวไปจนจบข้อมูลใหม่ 
    # ข้อมูลเดิมจะถูกเขียนทับด้วยค่าใหม่ทันที โดยไม่ลบโครงสร้าง Sheet ทิ้ง
    sheet.update('A1', data_to_update)
    
    print("DEBUG: อัปเดตข้อมูลหุ้นเรียบร้อย!")
    
# 2. ฟังก์ชันอเนกประสงค์ (เอามาแทรกตรงนี้)    
def log_cash_transaction(date, trans_type, amount, note):
    try:
        client = get_gsheet_client()
        sheet = get_cached_spreadsheet(client, get_active_sheet_name()).worksheet('CashFlow')
        
        # เตรียมข้อมูลที่จะบันทึก (Date, Type, Amount, Note)
        row_data = [str(date), trans_type, amount, note]
        
        # เพิ่มแถวใหม่ต่อท้ายข้อมูลเดิม
        sheet.append_row(row_data)
        st.toast("บันทึกรายการเงินสดเรียบร้อย!", icon="💰")
    except Exception as e:
        st.error(f"บันทึกรายการเงินสดไม่สำเร็จ: {e}")
        
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
        # ลองโหลดจาก Google Sheets ดูก่อนถ้า session ว่าง
        try:
            client = get_gsheet_client()
            sheet = get_cached_spreadsheet(client, get_active_sheet_name()).worksheet('JournalData')
            data = sheet.get_all_records()
            if not data:
                return pd.DataFrame()
            df_j = pd.DataFrame(data)
        except:
            return pd.DataFrame()
    else:
        df_j = pd.DataFrame(st.session_state.journal_data)
        
    if df_j.empty:
        return pd.DataFrame()

    # ทำความสะอาดชื่อคอลัมน์ (ตัดช่องว่างหน้าหลัง)
    df_j.columns = df_j.columns.str.strip()
    
    # ค้นหาคอลัมน์กำไร/ขาดทุนอัตโนมัติ (รองรับหลายชื่อที่เป็นไปได้)
    pnl_col_candidates = ['กำไร/ขาดทุน', 'กำไร/ขาดทุน (บาท)', 'Net_Profit', 'Realized', 'PnL']
    pnl_column = next((col for col in pnl_col_candidates if col in df_j.columns), None)
    
    if not pnl_column:
        st.warning("⚠️ ไม่พบคอลัมน์กำไร/ขาดทุนใน JournalData กรุณาตรวจสอบชื่อคอลัมน์")
        return pd.DataFrame()
        
    df_j['PnL'] = pd.to_numeric(df_j[pnl_column], errors='coerce').fillna(0)
    
    # ค้นหาคอลัมน์วันที่ขายหรือวันที่ปิด
    date_col_candidates = ['วันที่ขาย', 'Date_Close', 'วันที่']
    date_column = next((col for col in date_col_candidates if col in df_j.columns), None)
    
    if date_column:
        df_j['Date_Sell'] = pd.to_datetime(df_j[date_column], errors='coerce')
    else:
        df_j['Date_Sell'] = pd.to_datetime(pd.Timestamp.today())

    # 2. เตรียมข้อมูล CashFlow (ป้องกันกรณีชีท CashFlow Error)
    try:
        client = get_gsheet_client()
        sheet = get_cached_spreadsheet(client, get_active_sheet_name()).worksheet('CashFlow')
        cash_data = sheet.get_all_records()
        df_cash = pd.DataFrame(cash_data) if cash_data else pd.DataFrame()
    except:
        df_cash = pd.DataFrame()

    if not df_cash.empty:
        df_cash.columns = df_cash.columns.str.strip()
        if 'Date' in df_cash.columns and 'Amount' in df_cash.columns:
            df_cash['Date'] = pd.to_datetime(df_cash['Date'], errors='coerce')
            df_cash['Amount'] = pd.to_numeric(df_cash['Amount'], errors='coerce').fillna(0)
            daily_cash = df_cash.groupby('Date')['Amount'].sum().cumsum().reset_index()
            daily_cash.columns = ['Date', 'Net_Cash_In']
        else:
            daily_cash = pd.DataFrame(columns=['Date', 'Net_Cash_In'])
    else:
        daily_cash = pd.DataFrame(columns=['Date', 'Net_Cash_In'])

    # 3. คำนวณ PnL รายวัน
    df_j['Date'] = df_j['Date_Sell'].dt.normalize()
    daily_pnl = df_j.groupby('Date')['PnL'].sum().cumsum().reset_index()
    daily_pnl.columns = ['Date', 'Cumulative_PnL']

    if daily_pnl.empty:
        return pd.DataFrame()

    # 4. รวมตาราง Equity
    if not daily_cash.empty:
        df_equity = pd.merge(daily_pnl, daily_cash, on='Date', how='outer').fillna(0)
    else:
        df_equity = daily_pnl.copy()
        df_equity['Net_Cash_In'] = 0

    df_equity = df_equity.sort_values('Date').dropna(subset=['Date'])
    
    initial_balance = 69102.44  
    df_equity['Cash_Base'] = df_equity['Cumulative_PnL'] + df_equity['Net_Cash_In'] + initial_balance
    
    # 5. คำนวณ M2M
    current_market_val = get_total_market_value()
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
        sheet = get_cached_spreadsheet(client, get_active_sheet_name()).worksheet('StockData')
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

def log_to_sheet(sheet_name, row_data):
    """ฟังก์ชันอเนกประสงค์สำหรับ append แถวข้อมูลใหม่ลงใน Google Sheets"""
    try:
        client = get_gsheet_client()
        sheet = get_cached_spreadsheet(client, get_active_sheet_name()).worksheet(sheet_name)
        sheet.append_row(row_data)
    except Exception as e:
        print(f"DEBUG: Error ใน log_to_sheet ({sheet_name}): {e}")
        
# ฟังก์ชันสำหรับค้นหา Sector จาก Mapping ที่เราทำไว้
import streamlit as st
import pandas as pd

# 🌟 1. วางฟังก์ชันนี้ไว้บนสุดของโค้ด (นอก main)
def get_sector_from_mapping(ticker, df_mapping=None):
    ticker = str(ticker).strip().upper()
    
    # ฐานข้อมูล Sector แบบฝังโค้ด
    sector_dict = {
        "A5.BK": "อสังหาริมทรัพย์และก่อสร้าง", "AAI.BK": "เกษตรและอุตสาหกรรมอาหาร", "AAV.BK": "บริการ", "ABM.BK": "ทรัพยากร", "ACC.BK": "อสังหาริมทรัพย์และก่อสร้าง", "ACE.BK": "ทรัพยากร", "ACG.BK": "บริการ", "ADB.BK": "สินค้าอุตสาหกรรม", "ADD.BK": "เทคโนโลยี", "ADVANC.BK": "เทคโนโลยี", "ADVICE.BK": "บริการ", "AE.BK": "บริการ", "AEONTS.BK": "ธุรกิจการเงิน", "AF.BK": "ธุรกิจการเงิน", "AGE.BK": "ทรัพยากร", "AH.BK": "สินค้าอุตสาหกรรม", "AHC.BK": "บริการ", "AI.BK": "สินค้าอุตสาหกรรม", "AIE.BK": "เกษตรและอุตสาหกรรมอาหาร", "AIT.BK": "เทคโนโลยี", "AJ.BK": "สินค้าอุตสาหกรรม", "AJA.BK": "เทคโนโลยี", "AKP.BK": "สินค้าอุตสาหกรรม", "AKR.BK": "สินค้าอุตสาหกรรม", "ALLA.BK": "สินค้าอุตสาหกรรม", "ALLY.BK": "กองทุนรวมอสังหาริมทรัพย์และกองทรัสต์เพื่อการลงทุนในอสังหาริมทรัพย์", "ALPHAX.BK": "อสังหาริมทรัพย์และก่อสร้าง", "ALT.BK": "เทคโนโลยี", "ALUCON.BK": "สินค้าอุตสาหกรรม", "AMA.BK": "บริการ", "AMANAH.BK": "ธุรกิจการเงิน", "AMARC.BK": "บริการ", "AMATA.BK": "อสังหาริมทรัพย์และก่อสร้าง", "AMR.BK": "เทคโนโลยี", "ANAN.BK": "อสังหาริมทรัพย์และก่อสร้าง", "ANI.BK": "บริการ", "AOT.BK": "บริการ", "AP.BK": "อสังหาริมทรัพย์และก่อสร้าง", "APCO.BK": "บริการ", "APCS.BK": "อสังหาริมทรัพย์และก่อสร้าง", "APO.BK": "เกษตรและอุตสาหกรรมอาหาร", "APP.BK": "เทคโนโลยี", "APURE.BK": "เกษตรและอุตสาหกรรมอาหาร", "AQUA.BK": "สื่อสิ่งพิมพ์และสื่อสาร", "ARIN.BK": "อสังหาริมทรัพย์และก่อสร้าง", "ARIP.BK": "บริการ", "ARROW.BK": "อสังหาริมทรัพย์และก่อสร้าง", "AS.BK": "เทคโนโลยี", "ASAP.BK": "บริการ", "ASEFA.BK": "สินค้าอุตสาหกรรม", "ASIA.BK": "ธุรกิจการเงิน", "ASIAN.BK": "เกษตรและอุตสาหกรรมอาหาร", "ASK.BK": "ธุรกิจการเงิน", "ASN.BK": "ธุรกิจการเงิน", "ASP.BK": "ธุรกิจการเงิน", "ASW.BK": "อสังหาริมทรัพย์และก่อสร้าง", "ATP30.BK": "บริการ", "AU.BK": "บริการ", "AUCT.BK": "บริการ", "AURA.BK": "บริการ", "AWC.BK": "อสังหาริมทรัพย์และก่อสร้าง", "AYUD.BK": "ธุรกิจการเงิน", "BA.BK": "บริการ", "BAFS.BK": "บริการ", "BAM.BK": "ธุรกิจการเงิน", "BANPU.BK": "ทรัพยากร", "BAY.BK": "ธุรกิจการเงิน", "BBGI.BK": "ทรัพยากร", "BBL.BK": "ธุรกิจการเงิน", "BCH.BK": "บริการ",
        "BCP.BK": "ทรัพยากร", "BCPG.BK": "ทรัพยากร", "BDMS.BK": "บริการ", "BEAUTY.BK": "บริการ", "BEC.BK": "สื่อสิ่งพิมพ์และสื่อสาร", "BEM.BK": "บริการ", "BGC.BK": "สินค้าอุตสาหกรรม", "BGRIM.BK": "ทรัพยากร", "BH.BK": "บริการ", "BIG.BK": "บริการ", "BIZ.BK": "บริการ", "BJC.BK": "บริการ", "BLA.BK": "ธุรกิจการเงิน", "BLC.BK": "สินค้าอุตสาหกรรม", "BRI.BK": "อสังหาริมทรัพย์และก่อสร้าง", "BROCK.BK": "อสังหาริมทรัพย์และก่อสร้าง", "BRR.BK": "เกษตรและอุตสาหกรรมอาหาร", "BSM.BK": "อสังหาริมทรัพย์และก่อสร้าง", "BTC.BK": "บริการ", "BTNPL.BK": "สินค้าอุตสาหกรรม", "BTS.BK": "บริการ", "BTSGIF.BK": "กองทุนรวมอสังหาริมทรัพย์และกองทรัสต์เพื่อการลงทุนในอสังหาริมทรัพย์", "BYD.BK": "บริการ", "CBG.BK": "เกษตรและอุตสาหกรรมอาหาร", "CCET.BK": "เทคโนโลยี", "CENTEL.BK": "บริการ", "CFRESH.BK": "เกษตรและอุตสาหกรรมอาหาร", "CGH.BK": "ธุรกิจการเงิน", "CH.BK": "อสังหาริมทรัพย์และก่อสร้าง", "CHAYO.BK": "ธุรกิจการเงิน", "CHG.BK": "บริการ", "CHOW.BK": "ทรัพยากร", "CIG.BK": "สินค้าอุตสาหกรรม", "CIMBT.BK": "ธุรกิจการเงิน", "CINE.BK": "บริการ", "CK.BK": "อสังหาริมทรัพย์และก่อสร้าง", "CKP.BK": "ทรัพยากร", "CM.BK": "เกษตรและอุตสาหกรรมอาหาร", "CMAN.BK": "สินค้าอุตสาหกรรม", "CMC.BK": "อสังหาริมทรัพย์และก่อสร้าง", "CMO.BK": "บริการ", "CMR.BK": "บริการ", "CNT.BK": "อสังหาริมทรัพย์และก่อสร้าง", "COCOCO.BK": "เกษตรและอุตสาหกรรมอาหาร", "CPALL.BK": "บริการ", "CPAXT.BK": "บริการ", "CPF.BK": "เกษตรและอุตสาหกรรมอาหาร", "CPN.BK": "อสังหาริมทรัพย์และก่อสร้าง", "CPH.BK": "สินค้าอุตสาหกรรม", "CPW.BK": "บริการ", "CRC.BK": "บริการ", "CRD.BK": "อสังหาริมทรัพย์และก่อสร้าง", "CSC.BK": "สินค้าอุตสาหกรรม", "CSP.BK": "สินค้าอุตสาหกรรม", "CSR.BK": "สินค้าอุตสาหกรรม", "CSS.BK": "บริการ", "CTW.BK": "สินค้าอุตสาหกรรม", "CWT.BK": "สินค้าอุตสาหกรรม", "D.BK": "บริการ", "DCC.BK": "สินค้าอุตสาหกรรม", "DELTA.BK": "เทคโนโลยี", "DEXON.BK": "บริการ", "DHOUSE.BK": "อสังหาริมทรัพย์และก่อสร้าง", "DITTO.BK": "เทคโนโลยี", "DMT.BK": "บริการ", "DOHOME.BK": "บริการ", "DRT.BK": "สินค้าอุตสาหกรรม", "DTCENT.BK": "บริการ", "DTCI.BK": "บริการ", "DUSIT.BK": "บริการ",
        "EA.BK": "ทรัพยากร", "EASTW.BK": "ทรัพยากร", "ECF.BK": "สินค้าอุตสาหกรรม", "ECL.BK": "ธุรกิจการเงิน", "EE.BK": "เกษตรและอุตสาหกรรมอาหาร", "EFORL.BK": "บริการ", "EGCO.BK": "ทรัพยากร", "EKH.BK": "บริการ", "EMC.BK": "อสังหาริมทรัพย์และก่อสร้าง", "EP.BK": "ทรัพยากร", "EPG.BK": "สินค้าอุตสาหกรรม", "ERW.BK": "บริการ", "ESTAR.BK": "อสังหาริมทรัพย์และก่อสร้าง", "ETC.BK": "ทรัพยากร", "EVER.BK": "อสังหาริมทรัพย์และก่อสร้าง", "F&D.BK": "เกษตรและอุตสาหกรรมอาหาร", "FANCY.BK": "สินค้าอุตสาหกรรม", "FENIX.BK": "สินค้าอุตสาหกรรม", "FMT.BK": "สินค้าอุตสาหกรรม", "FN.BK": "บริการ", "FNS.BK": "ธุรกิจการเงิน", "FORTH.BK": "เทคโนโลยี", "FPI.BK": "สินค้าอุตสาหกรรม", "FPT.BK": "อสังหาริมทรัพย์และก่อสร้าง", "FSMART.BK": "บริการ", "FVC.BK": "บริการ",
        "GABLE.BK": "เทคโนโลยี", "FVC.BK": "บริการ", "GBX.BK": "ธุรกิจการเงิน", "GC.BK": "ทรัพยากร", "GCAP.BK": "ธุรกิจการเงิน", "GEL.BK": "อสังหาริมทรัพย์และก่อสร้าง", "GFPT.BK": "เกษตรและอุตสาหกรรมอาหาร", "GGC.BK": "ทรัพยากร", "GIFT.BK": "เกษตรและอุตสาหกรรมอาหาร", "GJ.BK": "สินค้าอุตสาหกรรม", "GLOBAL.BK": "บริการ", "GLOCON.BK": "เกษตรและอุตสาหกรรมอาหาร", "GLOW.BK": "ทรัพยากร", "GPSC.BK": "ทรัพยากร", "GRAMMY.BK": "สื่อสิ่งพิมพ์และสื่อสาร", "GULF.BK": "ทรัพยากร", "GUNKUL.BK": "ทรัพยากร", "GYT.BK": "สินค้าอุตสาหกรรม", "HANA.BK": "เทคโนโลยี", "HENG.BK": "ธุรกิจการเงิน", "HMPRO.BK": "บริการ", "HTC.BK": "เกษตรและอุตสาหกรรมอาหาร", "HTECH.BK": "สินค้าอุตสาหกรรม", "HUMAN.BK": "เทคโนโลยี", "HYDB.BK": "บริการ", "I2.BK": "เทคโนโลยี", "ICN.BK": "เทคโนโลยี", "IFEC.BK": "ทรัพยากร", "ILINK.BK": "เทคโนโลยี", "ILM.BK": "บริการ", "IMH.BK": "บริการ", "INET.BK": "เทคโนโลยี", "INGRS.BK": "สินค้าอุตสาหกรรม", "INSET.BK": "เทคโนโลยี", "INTUCH.BK": "เทคโนโลยี", "IRC.BK": "สินค้าอุตสาหกรรม", "IRPC.BK": "ทรัพยากร", "IT.BK": "บริการ", "ITD.BK": "อสังหาริมทรัพย์และก่อสร้าง", "ITI.BK": "บริการ", "ITEL.BK": "เทคโนโลยี", "J.BK": "อสังหาริมทรัพย์และก่อสร้าง", " JAS.BK": "สื่อสิ่งพิมพ์และสื่อสาร", "JCK.BK": "อสังหาริมทรัพย์และก่อสร้าง", "JCKH.BK": "บริการ", "JDF.BK": "เกษตรและอุตสาหกรรมอาหาร", "JKN.BK": "บริการ", "JMART.BK": "บริการ", "JMT.BK": "ธุรกิจการเงิน", "JR.BK": "บริการ", "JTS.BK": "เทคโนโลยี", "JUBILE.BK": "บริการ", "JUTHA.BK": "บริการ",
        "KAMART.BK": "บริการ", "KBANK.BK": "ธุรกิจการเงิน", "KBS.BK": "เกษตรและอุตสาหกรรมอาหาร", "KCAR.BK": "บริการ", "KCE.BK": "เทคโนโลยี", "KEX.BK": "บริการ", "KGI.BK": "ธุรกิจการเงิน", "KKP.BK": "ธุรกิจการเงิน", "KSL.BK": "เกษตรและอุตสาหกรรมอาหาร", "KTB.BK": "ธุรกิจการเงิน", "KTC.BK": "ธุรกิจการเงิน", "KTIS.BK": "เกษตรและอุตสาหกรรมอาหาร", "KUN.BK": "อสังหาริมทรัพย์และก่อสร้าง", "KWM.BK": "สินค้าอุตสาหกรรม", "KYE.BK": "สินค้าอุตสาหกรรม", "L&E.BK": "สินค้าอุตสาหกรรม", "LALIN.BK": "อสังหาริมทรัพย์และก่อสร้าง", "LANNA.BK": "ทรัพยากร", "LH.BK": "อสังหาริมทรัพย์และก่อสร้าง", "LHFG.BK": "ธุรกิจการเงิน", "LHK.BK": "สินค้าอุตสาหกรรม", "LIT.BK": "ธุรกิจการเงิน", "LOXLEY.BK": "บริการ", "LPH.BK": "บริการ", "LPN.BK": "อสังหาริมทรัพย์และก่อสร้าง", "LRH.BK": "บริการ", "LST.BK": "เกษตรและอุตสาหกรรมอาหาร", "M.BK": "บริการ", "MAJOR.BK": "บริการ", "M-CHAI.BK": "บริการ", "MALEE.BK": "เกษตรและอุตสาหกรรมอาหาร", "MASTER.BK": "บริการ", "MATI.BK": "สื่อสิ่งพิมพ์และสื่อสาร", "MBK.BK": "บริการ", "MC.BK": "สินค้าอุตสาหกรรม", "M-DAE.BK": "บริการ", "MDX.BK": "อสังหาริมทรัพย์และก่อสร้าง", "MEB.BK": "บริการ", "MEGA.BK": "บริการ", "METCO.BK": "สินค้าอุตสาหกรรม", "MFC.BK": "ธุรกิจการเงิน", "MGC.BK": "บริการ", "MGI.BK": "บริการ", "MINT.BK": "บริการ", "MK.BK": "อสังหาริมทรัพย์และก่อสร้าง", "ML.BK": "ธุรกิจการเงิน", "MOONG.BK": "สินค้าอุตสาหกรรม", "MPIC.BK": "สื่อสิ่งพิมพ์และสื่อสาร", "MSC.BK": "เทคโนโลยี", "MTC.BK": "ธุรกิจการเงิน", "MTI.BK": "ธุรกิจการเงิน", "MTW.BK": "สินค้าอุตสาหกรรม", "MULTI.BK": "บริการ", "MVC.BK": "สินค้าอุตสาหกรรม", "NC.BK": "สินค้าอุตสาหกรรม", "NCH.BK": "อสังหาริมทรัพย์และก่อสร้าง", "NCL.BK": "บริการ", "NEO.BK": "สินค้าอุตสาหกรรม", "NER.BK": "เกษตรและอุตสาหกรรมอาหาร", "NETBAY.BK": "เทคโนโลยี", "NEW.BK": "บริการ", "NEX.BK": "บริการ", "NOBLE.BK": "อสังหาริมทรัพย์และก่อสร้าง", "NOVA.BK": "สินค้าอุตสาหกรรม", "NPK.BK": "เกษตรและอุตสาหกรรมอาหาร", "NSL.BK": "เกษตรและอุตสาหกรรมอาหาร", "NTV.BK": "บริการ", "NUSA.BK": "อสังหาริมทรัพย์และก่อสร้าง", "NVD.BK": "อสังหาริมทรัพย์และก่อสร้าง", "NYT.BK": "บริการ",
        "O.BK": "บริการ", "OCB.BK": "ธุรกิจการเงิน", "OISHI.BK": "เกษตรและอุตสาหกรรมอาหาร", "OKJ.BK": "บริการ", "ORI.BK": "อสังหาริมทรัพย์และก่อสร้าง", "OSP.BK": "เกษตรและอุตสาหกรรมอาหาร", "OTO.BK": "เทคโนโลยี", "PAC.BK": "สินค้าอุตสาหกรรม", "PACO.BK": "สินค้าอุตสาหกรรม", "PAP.BK": "สินค้าอุตสาหกรรม", "PATH.BK": "บริการ", "PB.BK": "เกษตรและอุตสาหกรรมอาหาร", "PCSGH.BK": "สินค้าอุตสาหกรรม", "PDG.BK": "สินค้าอุตสาหกรรม", "PDI.BK": "ทรัพยากร", "PEACE.BK": "อสังหาริมทรัพย์และก่อสร้าง", "PERM.BK": "สินค้าอุตสาหกรรม", "PF.BK": "อสังหาริมทรัพย์และก่อสร้าง", "PHG.BK": "บริการ", "PJW.BK": "สินค้าอุตสาหกรรม", "PLANB.BK": "บริการ", "PLAT.BK": "อสังหาริมทรัพย์และก่อสร้าง", "PLUS.BK": "เกษตรและอุตสาหกรรมอาหาร", "PM.BK": "เกษตรและอุตสาหกรรมอาหาร", "PMTA.BK": "เกษตรและอุตสาหกรรมอาหาร", "POLAR.BK": "อสังหาริมทรัพย์และก่อสร้าง", "POLY.BK": "สินค้าอุตสาหกรรม", "POPN.BK": "เกษตรและอุตสาหกรรมอาหาร", "PORT.BK": "บริการ", "POST.BK": "สื่อสิ่งพิมพ์และสื่อสาร", "PPPM.BK": "เกษตรและอุตสาหกรรมอาหาร", "PR9.BK": "บริการ", "PRAKIT.BK": "บริการ", "PRAPAT.BK": "บริการ", "PREB.BK": "อสังหาริมทรัพย์และก่อสร้าง", "PRG.BK": "เกษตรและอุตสาหกรรมอาหาร", "PRM.BK": "บริการ", "PRO.BK": "สินค้าอุตสาหกรรม", "PROEN.BK": "เทคโนโลยี", "PSG.BK": "อสังหาริมทรัพย์และก่อสร้าง", "PSH.BK": "อสังหาริมทรัพย์และก่อสร้าง", "PSI.BK": "สินค้าอุตสาหกรรม", "PSL.BK": "บริการ", "PSTC.BK": "ทรัพยากร", "PT.BK": "บริการ", "PTG.BK": "ทรัพยากร", "PTL.BK": "สินค้าอุตสาหกรรม", "PTT.BK": "ทรัพยากร", "PTTEP.BK": "ทรัพยากร", "PTTGC.BK": "ทรัพยากร", "PYLON.BK": "อสังหาริมทรัพย์และก่อสร้าง", "Q-CON.BK": "สินค้าอุตสาหกรรม", "QH.BK": "อสังหาริมทรัพย์และก่อสร้าง", "QLT.BK": "สินค้าอุตสาหกรรม", "QTC.BK": "สินค้าอุตสาหกรรม", "RABBIT.BK": "ธุรกิจการเงิน", "RATCH.BK": "ทรัพยากร", "RBF.BK": "เกษตรและอุตสาหกรรมอาหาร", "RCL.BK": "บริการ", "RJH.BK": "บริการ", "ROJNA.BK": "อสังหาริมทรัพย์และก่อสร้าง", "RP.BK": "บริการ", "RPC.BK": "ทรัพยากร", "RPH.BK": "บริการ", "RS.BK": "บริการ", "RT.BK": "อสังหาริมทรัพย์และก่อสร้าง", "RTC.BK": "บริการ", "RWI.BK": "สินค้าอุตสาหกรรม",
        "S.BK": "อสังหาริมทรัพย์และก่อสร้าง", "SABINA.BK": "สินค้าอุตสาหกรรม", "SABUY.BK": "บริการ", "SAF.BK": "อสังหาริมทรัพย์และก่อสร้าง", "SAFE.BK": "บริการ", "SAK.BK": "ธุรกิจการเงิน", "SAMCO.BK": "อสังหาริมทรัพย์และก่อสร้าง", "SAMART.BK": "เทคโนโลยี", "SAMTEL.BK": "เทคโนโลยี", "SAPPE.BK": "เกษตรและอุตสาหกรรมอาหาร", "SAT.BK": "สินค้าอุตสาหกรรม", "SBNEXT.BK": "บริการ", "SC.BK": "อสังหาริมทรัพย์และก่อสร้าง", "SCAP.BK": "ธุรกิจการเงิน", "SCB.BK": "ธุรกิจการเงิน", "SCC.BK": "สินค้าอุตสาหกรรม", "SCCC.BK": "สินค้าอุตสาหกรรม", "SCG.BK": "บริการ", "SCGD.BK": "สินค้าอุตสาหกรรม", "SCI.BK": "เทคโนโลยี", "SCN.BK": "ทรัพยากร", "SCP.BK": "สินค้าอุตสาหกรรม", "SDC.BK": "เทคโนโลยี", "SE-ED.BK": "บริการ", "SEAFCO.BK": "อสังหาริมทรัพย์และก่อสร้าง", "SECURE.BK": "เทคโนโลยี", "SENA.BK": "อสังหาริมทรัพย์และก่อสร้าง", "SF.BK": "บริการ", "SFT.BK": "สินค้าอุตสาหกรรม", "SGC.BK": "ธุรกิจการเงิน", "SGP.BK": "ทรัพยากร", "SGT.BK": "ธุรกิจการเงิน", "SHR.BK": "บริการ", "SICT.BK": "เทคโนโลยี", "SIMAT.BK": "เทคโนโลยี", "SINO.BK": "บริการ", "SINGER.BK": "ธุรกิจการเงิน", "SIRI.BK": "อสังหาริมทรัพย์และก่อสร้าง", "SIS.BK": "เทคโนโลยี", "SISB.BK": "บริการ", "SK.BK": "อสังหาริมทรัพย์และก่อสร้าง", "SKN.BK": "เกษตรและอุตสาหกรรมอาหาร", "SKR.BK": "บริการ", "SKY.BK": "บริการ", "SLM.BK": "บริการ", "SM.BK": "บริการ", "SMART.BK": "สินค้าอุตสาหกรรม", "SMD.BK": "บริการ", "SMIT.BK": "สินค้าอุตสาหกรรม", "SMPC.BK": "สินค้าอุตสาหกรรม", "SNC.BK": "สินค้าอุตสาหกรรม", "SO.BK": "บริการ", "SOLAR.BK": "ทรัพยากร", "SONIC.BK": "บริการ", "SORKON.BK": "เกษตรและอุตสาหกรรมอาหาร", "SPA.BK": "บริการ", "SPALI.BK": "อสังหาริมทรัพย์และก่อสร้าง", "SPc.BK": "สินค้าอุตสาหกรรม", "SPCG.BK": "ทรัพยากร", "SPHI.BK": "บริการ", "SPI.BK": "สินค้าอุตสาหกรรม", "SPRC.BK": "ทรัพยากร", "SPSU.BK": "สินค้าอุตสาหกรรม", "SPVI.BK": "บริการ", "SQ.BK": "บริการ", "SR.BK": "อสังหาริมทรัพย์และก่อสร้าง", "SRICHA.BK": "บริการ", "SSP.BK": "ทรัพยากร", "SSPF.BK": "กองทุนรวมอสังหาริมทรัพย์และกองทรัสต์เพื่อการลงทุนในอสังหาริมทรัพย์", "SST.BK": "บริการ", "STA.BK": "เกษตรและอุตสาหกรรมอาหาร", 
        "STANLY.BK": "สินค้าอุตสาหกรรม", "STAR.BK": "สินค้าอุตสาหกรรม", "STARK.BK": "สินค้าอุตสาหกรรม", "STC.BK": "อสังหาริมทรัพย์และก่อสร้าง", "STEC.BK": "อสังหาริมทรัพย์และก่อสร้าง", "STGT.BK": "เกษตรและอุตสาหกรรมอาหาร", "STPI.BK": "สินค้าอุตสาหกรรม", "SUC.BK": "สินค้าอุตสาหกรรม", "SUN.BK": "เกษตรและอุตสาหกรรมอาหาร", "SVR.BK": "อสังหาริมทรัพย์และก่อสร้าง", "SVT.BK": "บริการ", "SYNEX.BK": "เทคโนโลยี", "SYNTEC.BK": "อสังหาริมทรัพย์และก่อสร้าง", "T.BK": "บริการ", "TAE.BK": "เกษตรและอุตสาหกรรมอาหาร", "TAKUNI.BK": "บริการ", "TASCO.BK": "สินค้าอุตสาหกรรม", "TBN.BK": "เทคโนโลยี", "TC.BK": "เกษตรและอุตสาหกรรมอาหาร", "TCAP.BK": "ธุรกิจการเงิน", "TCC.BK": "สินค้าอุตสาหกรรม", "TCCC.BK": "เกษตรและอุตสาหกรรมอาหาร", "TCJ.BK": "สินค้าอุตสาหกรรม", "TCM.BK": "สินค้าอุตสาหกรรม", "TFG.BK": "เกษตรและอุตสาหกรรมอาหาร", "TFM.BK": "เกษตรและอุตสาหกรรมอาหาร", "TFMAMA.BK": "เกษตรและอุตสาหกรรมอาหาร", "TGPRO.BK": "สินค้าอุตสาหกรรม", "TH.BK": "ธุรกิจการเงิน", "THAI.BK": "บริการ", "THANA.BK": "อสังหาริมทรัพย์และก่อสร้าง", "THANI.BK": "ธุรกิจการเงิน", "THG.BK": "บริการ", "THIP.BK": "สินค้าอุตสาหกรรม", "TIDLOR.BK": "ธุรกิจการเงิน", "TIPH.BK": "ธุรกิจการเงิน", "TISCO.BK": "ธุรกิจการเงิน", "TK.BK": "ธุรกิจการเงิน", "TKN.BK": "เกษตรและอุตสาหกรรมอาหาร", "TKS.BK": "บริการ", "TKT.BK": "สินค้าอุตสาหกรรม", "TLI.BK": "ธุรกิจการเงิน", "TM.BK": "บริการ", "TMC.BK": "สินค้าอุตสาหกรรม", "TMD.BK": "สินค้าอุตสาหกรรม", "TMILL.BK": "เกษตรและอุตสาหกรรมอาหาร", "TMT.BK": "สินค้าอุตสาหกรรม", "TNDT.BK": "บริการ", "TNH.BK": "บริการ", "TNP.BK": "บริการ", "TNR.BK": "เกษตรและอุตสาหกรรมอาหาร", "TOA.BK": "สินค้าอุตสาหกรรม", "TOG.BK": "สินค้าอุตสาหกรรม", "TOP.BK": "ทรัพยากร", "TPBI.BK": "สินค้าอุตสาหกรรม", "TPCH.BK": "ทรัพยากร", "TPIPL.BK": "สินค้าอุตสาหกรรม", "TPIPP.BK": "ทรัพยากร", "TPL.BK": "บริการ", "TPOLY.BK": "อสังหาริมทรัพย์และก่อสร้าง", "TPP.BK": "สินค้าอุตสาหกรรม", "TPS.BK": "เทคโนโลยี", "TQM.BK": "ธุรกิจการเงิน", "TR.BK": "บริการ", "TRC.BK": "อสังหาริมทรัพย์และก่อสร้าง", "TRP.BK": "บริการ", "TRUE.BK": "สื่อสิ่งพิมพ์และสื่อสาร", 
        "TSE.BK": "ทรัพยากร", "TSI.BK": "ธุรกิจการเงิน", " TSR.BK": "บริการ", "TSTE.BK": "เกษตรและอุตสาหกรรมอาหาร", "TSTH.BK": "สินค้าอุตสาหกรรม", "TTA.BK": "บริการ", "TTB.BK": "ธุรกิจการเงิน", "TTCL.BK": "บริการ", "TTW.BK": "ทรัพยากร", "TU.BK": "เกษตรและอุตสาหกรรมอาหาร", "TVD.BK": "บริการ", "TVDH.BK": "บริการ", "TVO.BK": "เกษตรและอุตสาหกรรมอาหาร", "TWPC.BK": "เกษตรและอุตสาหกรรมอาหาร", "TYCN.BK": "สินค้าอุตสาหกรรม", "UAC.BK": "ทรัพยากร", "UBIS.BK": "สินค้าอุตสาหกรรม", "UEC.BK": "สินค้าอุตสาหกรรม", "UMC.BK": "สินค้าอุตสาหกรรม", "UNIQ.BK": "อสังหาริมทรัพย์และก่อสร้าง", "UPF.BK": "ธุรกิจการเงิน", "UPOIC.BK": "เกษตรและอุตสาหกรรมอาหาร", "UV.BK": "อสังหาริมทรัพย์และก่อสร้าง", "UVAN.BK": "เกษตรและอุตสาหกรรมอาหาร", "VCOM.BK": "เทคโนโลยี", "VGI.BK": "บริการ", "VIBHA.BK": "บริการ", "VL.BK": "บริการ", "VNG.BK": "สินค้าอุตสาหกรรม", "W.BK": "อสังหาริมทรัพย์และก่อสร้าง", "WACOAL.BK": "สินค้าอุตสาหกรรม", "WAVE.BK": "บริการ", "WHA.BK": "อสังหาริมทรัพย์และก่อสร้าง", "WHAUP.BK": "ทรัพยากร", "WICE.BK": "บริการ", "WIN.BK": "สินค้าอุตสาหกรรม", "WINMED.BK": "บริการ", "WINNER.BK": "เกษตรและอุตสาหกรรมอาหาร", "WORK.BK": "บริการ", "WORLD.BK": "ธุรกิจการเงิน", "WP.BK": "ทรัพยากร", "XO.BK": "เกษตรและอุตสาหกรรมอาหาร", "XPG.BK": "ธุรกิจการเงิน", "YONG.BK": "อสังหาริมทรัพย์และก่อสร้าง", "ZEN.BK": "บริการ", "ZIGA.BK": "สินค้าอุตสาหกรรม",
    }
    
    # เผื่อกรณีพิมพ์หุ้นมาแบบไม่มี .BK ให้ลองเช็คแบบเติม .BK ดูด้วย
    if ticker not in sector_dict and not ticker.endswith(".BK"):
        if f"{ticker}.BK" in sector_dict:
            return sector_dict[f"{ticker}.BK"]
            
    return sector_dict.get(ticker, "General / Unspecified")
    
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
