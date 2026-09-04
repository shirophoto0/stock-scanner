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
import traceback
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
import re
import random
from gspread.exceptions import APIError
from bs4 import BeautifulSoup
from constants import SET100_TICKERS
from theme import style_plotly

# 🆕 ระบบ Login หลายผู้ใช้: ฟังก์ชันนี้คืนชื่อ Google Sheet ของผู้ใช้ที่ล็อกอินอยู่ตอนนี้
# (ตั้งค่าไว้ตอน Login สำเร็จใน auth.py) ถ้ายังไม่มีการล็อกอิน จะใช้ 'MyStockData' เป็นค่าเริ่มต้น
def get_active_sheet_name():
    return st.session_state.get('active_sheet_name', 'MyStockData')


# 🧪 Phase D: สวิตช์สลับไป Firestore ทีละบัญชี — ต้องเพิ่มชื่อ sheet_name (เช่น "MyStockData")
# เข้า _FIRESTORE_ENABLED_SHEETS ใน secrets ถึงจะสลับไปใช้ Firestore สำหรับบัญชีนั้น บัญชีที่ไม่ได้
# อยู่ในลิสต์ (หรือถ้าไม่ได้ตั้งค่า _FIRESTORE_ENABLED_SHEETS เลย) จะยังใช้ Google Sheets เหมือนเดิม
# เสมอ — ทำให้สลับ umwealth/nujiwealth แยกกันได้ ไม่ต้องสลับพร้อมกันทั้งแอป และ rollback ได้ทันที
# แค่เอาชื่อบัญชีออกจากลิสต์บน Streamlit Cloud secrets
#
# 🔧 แก้บั๊ก: st.secrets ด้านบนอ่านได้เฉพาะตอนรันบน Streamlit Cloud (หรือมีไฟล์
# .streamlit/secrets.toml อยู่ในเครื่อง) เท่านั้น — ตอนรันผ่าน GitHub Actions (daily_scan.py,
# monthly_report.py, realtime_sl_tp_check.py) ไม่มีไฟล์นี้เลย (ถูก .gitignore ไว้ไม่ให้ push ขึ้น
# repo) ทำให้ st.secrets.get(...) โยน StreamlitSecretNotFoundError ทุกครั้ง ตกไปเข้า except แล้ว
# คืนค่า False เสมอ ทั้ง 3 สคริปต์จึงยังคงใช้ Google Sheets (gspread) อยู่ตลอด ต่อให้ตั้งค่า
# _FIRESTORE_ENABLED_SHEETS ครบทั้งสองบัญชีบน Streamlit Cloud secrets แล้วก็ตาม เพิ่มการอ่านจาก
# Environment Variable FIRESTORE_ENABLED_SHEETS (ตั้งค่าผ่าน workflow .yml ได้เลย ไม่ใช่ข้อมูลลับ
# จึงไม่ต้องเก็บเป็น GitHub Secret) เป็นทางเลือกสำรองไว้ด้วย
def _use_firestore():
    enabled_sheets = set()
    try:
        enabled_sheets |= set(st.secrets.get("_FIRESTORE_ENABLED_SHEETS", []))
    except Exception:
        pass

    env_list = os.environ.get("FIRESTORE_ENABLED_SHEETS", "")
    enabled_sheets |= {name.strip() for name in env_list.split(",") if name.strip()}

    try:
        active_sheet = get_active_sheet_name()
    except Exception:
        active_sheet = "MyStockData"

    return active_sheet in enabled_sheets


def get_gsheet_client():
    if _use_firestore():
        from firestore_functions import get_firestore_client
        return get_firestore_client()

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
class _FirestoreSpreadsheetProxy:
    """
    เลียนแบบ gspread Spreadsheet แค่พอให้ .worksheet(name) ใช้งานได้ — บางไฟล์ (tab_overview.py,
    tab_pvd.py, tab_stock.py) เรียก get_cached_spreadsheet(client, name).worksheet(ws_name) ตรงๆ
    โดยไม่ผ่าน get_cached_worksheet() ที่มีสวิตช์ _use_firestore() อยู่แล้ว proxy นี้ทำให้จุดเหล่านั้น
    ใช้งานกับ Firestore ได้เหมือนกันโดยไม่ต้องไปตามแก้ทีละไฟล์
    """
    def __init__(self, client, spreadsheet_name):
        self._client = client
        self._spreadsheet_name = spreadsheet_name

    def worksheet(self, worksheet_name):
        from firestore_functions import get_cached_worksheet as _fs_get_cached_worksheet
        return _fs_get_cached_worksheet(self._client, self._spreadsheet_name, worksheet_name)


@st.cache_resource(ttl=300, show_spinner=False)
def get_cached_spreadsheet(_client, spreadsheet_name):
    if _use_firestore():
        return _FirestoreSpreadsheetProxy(_client, spreadsheet_name)
    return _client.open(spreadsheet_name)


# 🔧 แก้บั๊ก (สำคัญ): เดิม "จำ" แค่ตัวไฟล์สเปรดชีตทั้งไฟล์ไว้เท่านั้น (get_cached_spreadsheet ด้านบน)
# แต่การเปิด "ชีตย่อย" แต่ละแผ่น (.worksheet(name) เช่น Watchlist, Real_Estate, PortfolioData)
# ยังไม่ได้ถูกจำไว้เลย ทุกครั้งที่แท็บไหนก็ตามเรียกใช้ จะยิง API ใหม่เสมอ — ปัญหาคือ Streamlit
# รันโค้ดทุกแท็บพร้อมกันทุกครั้งที่มีการโต้ตอบอะไรก็ตามในแอป (ไม่ใช่แค่แท็บที่เปิดดูอยู่) พอมีหลาย
# แท็บเรียกเปิดชีตย่อยพร้อมกันในจังหวะเดียว โควตาต่อนาทีจึงหมดเร็วผิดปกติ ตอนนี้จำชีตย่อยที่เปิด
# ไว้แล้วด้วย (5 นาที เหมือนกับตัวสเปรดชีต) ช่วยลดจำนวนครั้งที่ยิง API ลงได้อีกมาก ทุกแท็บที่ใช้
# get_worksheet_safely() จะได้ประโยชน์นี้โดยอัตโนมัติ ไม่ต้องแก้ทีละแท็บ
@st.cache_resource(ttl=300, show_spinner=False)
def get_cached_worksheet(_client, spreadsheet_name, worksheet_name):
    if _use_firestore():
        from firestore_functions import get_cached_worksheet as _fs_get_cached_worksheet
        return _fs_get_cached_worksheet(_client, spreadsheet_name, worksheet_name)
    return get_cached_spreadsheet(_client, spreadsheet_name).worksheet(worksheet_name)


def get_worksheet_safely(client, spreadsheet_name, worksheet_name, retries=4, delay=2):
    """ฟังก์ชันเปิด Google Sheet พร้อมระบบป้องกันและลองใหม่เมื่อติดปัญหา Quota Exceeded (429)"""
    if _use_firestore():
        from firestore_functions import get_worksheet_safely as _fs_get_worksheet_safely
        return _fs_get_worksheet_safely(client, spreadsheet_name, worksheet_name)
    for attempt in range(retries):
        try:
            sheet = get_cached_worksheet(client, spreadsheet_name, worksheet_name)
            return sheet
        except APIError as e:
            if "429" in str(e) or "Quota exceeded" in str(e):
                if attempt < retries - 1:
                    # 🔧 แก้บั๊ก: เดิมรอ "เท่ากันเป๊ะ" ทุกครั้ง (2, 4, 6 วินาที) ทำให้ถ้าหลายแท็บติด 429
                    # พร้อมกัน (เช่น ตอนโหลดครั้งแรกหลัง reboot แคชยังว่างเปล่า) จะลองใหม่พร้อมกันอีก
                    # รอบ แล้วชนโควตากันซ้ำเหมือนเดิม ตอนนี้เพิ่ม "สุ่มเวลารอ" เข้าไปเล็กน้อยในแต่ละ
                    # รอบ ช่วยกระจายจังหวะการลองใหม่ของแต่ละแท็บให้ไม่ตรงกันเป๊ะ ลดโอกาสชนกันซ้ำ
                    wait_time = delay * (attempt + 1) + random.uniform(0.5, 2.5)
                    time.sleep(wait_time)
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
        sheet_history = get_cached_worksheet(client, get_active_sheet_name(), 'Stock_TFEX_History')
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

def check_and_auto_stamp_fund_value(client, current_total_value):
    """
    🆕 บันทึกยอดรวมมูลค่ากองทุนรวม ณ สิ้นเดือน ลงชีต Fund_Value_History โดยอัตโนมัติ
    (ทำครั้งเดียวต่อเดือน ถ้าเดือนที่แล้วยังไม่เคยบันทึกไว้) เพื่อให้มีข้อมูลสำหรับวาดกราฟแนวโน้ม
    ต้องมีชีตชื่อ 'Fund_Value_History' (คอลัมน์ Date, Value) อยู่ใน Google Sheet ของผู้ใช้แล้ว
    """
    try:
        sheet_history = get_cached_worksheet(client, get_active_sheet_name(), 'Fund_Value_History')
        data = sheet_history.get_all_records()

        last_recorded_month = ""
        if data:
            last_date_str = str(data[-1].get('Date', ''))
            if last_date_str:
                last_recorded_month = last_date_str[:7]  # ตัดเอาแค่ 'YYYY-MM'

        today = datetime.today()
        prev_month_date = today.replace(day=1) - timedelta(days=5)
        target_month_str = prev_month_date.strftime('%Y-%m')
        target_date_str = prev_month_date.strftime('%Y-%m-%d')

        if last_recorded_month != target_month_str:
            sheet_history.append_row([target_date_str, current_total_value])
            st.toast(f"📊 ระบบบันทึกยอดกองทุนรวมสิ้นเดือนอัตโนมัติเรียบร้อย: {target_month_str}", icon="✅")

    except Exception:
        # ถ้ายังไม่มีชีต Fund_Value_History หรือเกิดปัญหาใดๆ ให้ข้ามไปเงียบๆ ไม่ให้แอปพัง
        pass


def check_and_auto_stamp_value_history(client, sheet_name, current_total_value, toast_label):
    """
    🆕 เวอร์ชันทั่วไปของ check_and_auto_stamp_fund_value() ใช้บันทึกยอดสินทรัพย์ประเภทไหนก็ได้
    (ไม่จำกัดแค่กองทุนรวม) ลงชีตประวัติรายเดือนโดยอัตโนมัติ ทำงานแบบเดียวกันทุกประการ แค่รับชื่อ
    ชีตและข้อความแจ้งเตือนเป็นพารามิเตอร์แทน จะได้ใช้ซ้ำกับทองคำ/อสังหาริมทรัพย์/ฯลฯ ได้โดยไม่ต้อง
    เขียนฟังก์ชันซ้ำหลายตัว ต้องมีชีตชื่อตามที่ระบุ (คอลัมน์ Date, Value) อยู่ใน Google Sheet ก่อน
    """
    try:
        sheet_history = get_cached_worksheet(client, get_active_sheet_name(), sheet_name)
        data = sheet_history.get_all_records()

        last_recorded_month = ""
        if data:
            last_date_str = str(data[-1].get('Date', ''))
            if last_date_str:
                last_recorded_month = last_date_str[:7]

        today = datetime.today()
        prev_month_date = today.replace(day=1) - timedelta(days=5)
        target_month_str = prev_month_date.strftime('%Y-%m')
        target_date_str = prev_month_date.strftime('%Y-%m-%d')

        if last_recorded_month != target_month_str:
            sheet_history.append_row([target_date_str, current_total_value])
            st.toast(f"📊 ระบบบันทึกยอด{toast_label}สิ้นเดือนอัตโนมัติเรียบร้อย: {target_month_str}", icon="✅")

    except Exception as e:
        # 🔧 แก้บั๊ก: เดิมกลืน error ไปเงียบๆ ทั้งหมด ทำให้ถ้าชื่อชีตสะกดไม่ตรง (พิมพ์ผิด/เว้นวรรค
        # ผิด) หรือมีปัญหาอื่นใด จะไม่มีทางรู้เลยว่าทำไมข้อมูลไม่เข้า Google Sheets ตอนนี้แจ้งเตือน
        # แบบเบาๆ (ไม่รบกวนจนเกินไป) ให้เห็นสาเหตุจริง ผ่าน st.toast
        st.toast(f"⚠️ บันทึกยอด{toast_label}อัตโนมัติไม่สำเร็จ: {e}", icon="⚠️")


# =============================================================
# 🆕 ระบบ Watchlist (เก็บติดตามหุ้นที่สนใจ แยกจากพอร์ตจริง ไม่ต้องซื้อจริงก็เก็บได้)
# ต้องมีชีตชื่อ 'Watchlist' (คอลัมน์ Ticker, Date_Added, Price_When_Added, Note)
# อยู่ใน Google Sheet ของผู้ใช้ก่อนถึงจะใช้งานได้
# =============================================================
def load_watchlist():
    """โหลดรายชื่อหุ้นทั้งหมดใน Watchlist คืนค่าเป็น list of dict (ว่างเปล่าถ้ายังไม่มีชีต/ข้อมูล)"""
    try:
        client = get_gsheet_client()
        sheet = get_cached_worksheet(client, get_active_sheet_name(), 'Watchlist')
        return sheet.get_all_records()
    except Exception:
        return []


def add_to_watchlist(ticker, current_price, note=""):
    """
    เพิ่มหุ้นเข้า Watchlist (กันเพิ่มซ้ำ ถ้ามีอยู่แล้วจะแจ้งเตือนแทนที่จะเพิ่มซ้ำ)
    คืนค่าเป็น (สำเร็จหรือไม่: bool, ข้อความ: str)
    """
    ticker = str(ticker).strip().upper()
    try:
        client = get_gsheet_client()
        sheet = get_cached_worksheet(client, get_active_sheet_name(), 'Watchlist')
        existing = sheet.get_all_records()
        existing_tickers = [str(r.get('Ticker', '')).strip().upper() for r in existing]
        if ticker in existing_tickers:
            return False, f"{ticker} อยู่ใน Watchlist อยู่แล้ว"
        sheet.append_row([ticker, str(date.today()), current_price, note])
        return True, f"เพิ่ม {ticker} เข้า Watchlist สำเร็จ"
    except Exception as e:
        return False, f"เพิ่มไม่สำเร็จ: {e}"


def remove_from_watchlist(ticker):
    """ลบหุ้นออกจาก Watchlist ด้วยชื่อ Ticker คืนค่าเป็น (สำเร็จหรือไม่: bool, ข้อความ: str)"""
    ticker = str(ticker).strip().upper()
    try:
        client = get_gsheet_client()
        sheet = get_cached_worksheet(client, get_active_sheet_name(), 'Watchlist')
        cell = sheet.find(ticker)
        if cell:
            sheet.delete_rows(cell.row)
            return True, f"ลบ {ticker} ออกจาก Watchlist แล้ว"
        return False, f"ไม่พบ {ticker} ใน Watchlist"
    except Exception as e:
        return False, f"ลบไม่สำเร็จ: {e}"


def update_watchlist_target(ticker, target_price, direction):
    """
    🆕 ตั้ง/แก้ราคาเป้าหมายของหุ้นใน Watchlist (ใช้กับระบบแจ้งเตือนราคาผ่าน Telegram)
    direction: 'below' (แจ้งเตือนตอนราคาลงมาถึง/ต่ำกว่าเป้าหมาย) หรือ 'above' (แจ้งเตือนตอนราคา
    ขึ้นมาถึง/เกินเป้าหมาย) ทุกครั้งที่ตั้งราคาเป้าหมายใหม่ จะรีเซ็ตสถานะ "เคยแจ้งเตือนแล้ว" กลับ
    เป็นยังไม่เคยแจ้งเสมอ (เผื่อกรณีตั้งราคาเป้าหมายใหม่ทับของเดิมที่เคยแจ้งเตือนไปแล้ว)
    คืนค่าเป็น (สำเร็จหรือไม่: bool, ข้อความ: str) ต้องมีคอลัมน์ Target_Price, Target_Direction,
    Alert_Sent ในชีต Watchlist ก่อน (คอลัมน์ที่ 5, 6, 7 ตามลำดับ)
    """
    ticker = str(ticker).strip().upper()
    try:
        client = get_gsheet_client()
        sheet = get_cached_worksheet(client, get_active_sheet_name(), 'Watchlist')
        cell = sheet.find(ticker)
        if not cell:
            return False, f"ไม่พบ {ticker} ใน Watchlist"
        sheet.update_cell(cell.row, 5, target_price)
        sheet.update_cell(cell.row, 6, direction)
        sheet.update_cell(cell.row, 7, "FALSE")
        return True, f"ตั้งราคาเป้าหมาย {ticker} ที่ {target_price} ({'ลงมาถึง' if direction == 'below' else 'ขึ้นมาถึง'}) เรียบร้อย"
    except Exception as e:
        return False, f"ตั้งราคาเป้าหมายไม่สำเร็จ: {e}"


def _check_watchlist_with_price_map(spreadsheet_name, price_map):
    """
    🔧 ฟังก์ชันกลางสำหรับเช็คราคาเป้าหมาย Watchlist โดยรับ price_map (dict {ticker: ราคา}) มาตรงๆ
    แยกออกมาเพื่อใช้ร่วมกันได้ทั้งแบบราคาปิดรายวัน (Daily Scan) และราคาสดแบบ real-time (เช็คถี่
    ระหว่างเวลาตลาดเปิด) ไม่ต้องเขียนตรรกะซ้ำ 2 ที่
    """
    triggered = []
    try:
        client = get_gsheet_client()
        sheet = get_cached_worksheet(client, spreadsheet_name, 'Watchlist')
        records = sheet.get_all_records()
    except Exception:
        return triggered

    if not records or not price_map:
        return triggered

    for idx, row in enumerate(records):
        ticker = str(row.get('Ticker', '')).strip().upper()
        target_price = row.get('Target_Price')
        direction = str(row.get('Target_Direction', '')).strip().lower()
        already_sent = str(row.get('Alert_Sent', '')).strip().upper() == 'TRUE'

        if not ticker or not target_price or already_sent or direction not in ('below', 'above'):
            continue
        try:
            target_price = float(target_price)
        except (ValueError, TypeError):
            continue

        current_price = price_map.get(ticker)
        if current_price is None:
            continue
        try:
            current_price = float(current_price)
        except (ValueError, TypeError):
            continue

        _hit = (direction == 'below' and current_price <= target_price) or \
               (direction == 'above' and current_price >= target_price)
        if _hit:
            triggered.append({
                'ticker': ticker, 'target_price': target_price,
                'direction': direction, 'current_price': current_price
            })
            try:
                sheet.update_cell(idx + 2, 7, "TRUE")  # +2 = ชดเชยแถวหัวตาราง + index เริ่มที่ 0
            except Exception:
                pass

    return triggered


def check_watchlist_price_alerts(spreadsheet_name, df_scan_latest):
    """
    🆕 เช็คหุ้นใน Watchlist ของบัญชีที่ระบุ ว่าตัวไหนราคาปัจจุบันถึงเป้าหมายที่ตั้งไว้แล้วบ้าง —
    เวอร์ชันนี้ใช้ "ราคาปิด" จากผลสแกนรายวัน (df_scan_latest) เหมาะกับ Daily Scan ที่รันวันละครั้ง
    คืนค่าเป็น list of dict [{'ticker':..., 'target_price':..., 'direction':..., 'current_price':...}]
    """
    if df_scan_latest is None or df_scan_latest.empty or 'Ticker' not in df_scan_latest.columns:
        return []
    price_map = dict(zip(df_scan_latest['Ticker'], df_scan_latest['ราคาล่าสุด']))
    return _check_watchlist_with_price_map(spreadsheet_name, price_map)


def get_watchlist_tickers_pending_alert(spreadsheet_name):
    """
    🆕 ดึงรายชื่อหุ้นใน Watchlist ของบัญชีที่ระบุ ที่ตั้งราคาเป้าหมายไว้แล้วแต่ยังไม่เคยแจ้งเตือน
    ใช้สำหรับดึงราคาสดแบบ real-time เฉพาะหุ้นที่จำเป็นเท่านั้น (ไม่ต้องดึงทั้ง Watchlist)
    """
    try:
        client = get_gsheet_client()
        sheet = get_cached_worksheet(client, spreadsheet_name, 'Watchlist')
        records = sheet.get_all_records()
    except Exception:
        return []

    tickers = set()
    for row in records:
        ticker = str(row.get('Ticker', '')).strip().upper()
        target_price = row.get('Target_Price')
        direction = str(row.get('Target_Direction', '')).strip().lower()
        already_sent = str(row.get('Alert_Sent', '')).strip().upper() == 'TRUE'
        if ticker and target_price and not already_sent and direction in ('below', 'above'):
            tickers.add(ticker)
    return list(tickers)


def check_watchlist_price_alerts_realtime(spreadsheet_name):
    """
    🆕 เช็คหุ้นใน Watchlist ของบัญชีที่ระบุ ว่าตัวไหนถึงราคาเป้าหมายแล้วบ้าง — เวอร์ชันนี้ดึง
    "ราคาสด" แบบ real-time (delay ~15 นาทีจาก Yahoo Finance) ต่อหุ้นโดยตรง เหมาะกับการเช็คถี่ๆ
    ระหว่างเวลาตลาดเปิด (ผ่าน workflow แยกต่างหากจาก Daily Scan)
    """
    tickers = get_watchlist_tickers_pending_alert(spreadsheet_name)
    if not tickers:
        return []

    price_map = {}
    for t in tickers:
        info = get_cached_stock_info(f"{t}.BK")
        price = info.get('currentPrice') or info.get('regularMarketPrice')
        if price:
            price_map[t] = price

    return _check_watchlist_with_price_map(spreadsheet_name, price_map)


def _check_sl_tp_with_price_map(spreadsheet_name, price_map):
    """
    🔧 ฟังก์ชันกลางสำหรับเช็ค SL/TP โดยรับ price_map (dict {ticker: ราคา}) มาโดยตรง แยกออกมา
    เพื่อใช้ร่วมกันได้ทั้ง 2 แบบ: เช็คจากราคาปิดของผลสแกนรายวัน (ครั้งเดียวต่อวัน) และเช็คจาก
    ราคาสดแบบ real-time (ถี่ขึ้นระหว่างเวลาตลาดเปิด) ไม่ต้องเขียนตรรกะซ้ำ 2 ที่
    """
    triggered = []
    try:
        client = get_gsheet_client()
        sheet = get_cached_worksheet(client, spreadsheet_name, 'PortfolioData')
        records = sheet.get_all_records()
    except Exception:
        return triggered

    if not records or not price_map:
        return triggered

    headers = sheet.row_values(1) if records else []

    def _col_index(col_name):
        return headers.index(col_name) + 1 if col_name in headers else None

    for idx, row in enumerate(records):
        ticker = str(row.get('หุ้น', '')).strip().upper()
        avg_price = row.get('avg_price')
        if not ticker:
            continue

        current_price = price_map.get(ticker)
        if current_price is None:
            continue
        try:
            current_price = float(current_price)
            avg_price = float(avg_price) if avg_price else 0.0
        except (ValueError, TypeError):
            continue

        # เช็ค Stop Loss
        sl_price = row.get('stop_loss_price')
        sl_sent = str(row.get('sl_alert_sent', '')).strip().upper() == 'TRUE'
        if sl_price and not sl_sent:
            try:
                sl_price = float(sl_price)
                if current_price <= sl_price:
                    pct_change = ((current_price - avg_price) / avg_price * 100) if avg_price > 0 else 0.0
                    triggered.append({
                        'ticker': ticker, 'type': 'SL', 'target_price': sl_price,
                        'current_price': current_price, 'avg_price': avg_price, 'pct_change': pct_change
                    })
                    _c = _col_index('sl_alert_sent')
                    if _c:
                        sheet.update_cell(idx + 2, _c, "TRUE")
            except (ValueError, TypeError):
                pass

        # เช็ค Take Profit
        tp_price = row.get('take_profit_price')
        tp_sent = str(row.get('tp_alert_sent', '')).strip().upper() == 'TRUE'
        if tp_price and not tp_sent:
            try:
                tp_price = float(tp_price)
                if current_price >= tp_price:
                    pct_change = ((current_price - avg_price) / avg_price * 100) if avg_price > 0 else 0.0
                    triggered.append({
                        'ticker': ticker, 'type': 'TP', 'target_price': tp_price,
                        'current_price': current_price, 'avg_price': avg_price, 'pct_change': pct_change
                    })
                    _c = _col_index('tp_alert_sent')
                    if _c:
                        sheet.update_cell(idx + 2, _c, "TRUE")
            except (ValueError, TypeError):
                pass

    return triggered


def check_portfolio_sl_tp_alerts(spreadsheet_name, df_scan_latest):
    """
    🆕 เช็คหุ้นในพอร์ตจริง (ไม่ใช่ Watchlist) ของบัญชีที่ระบุ ว่าตัวไหนราคาปัจจุบันถึงจุดตัดขาดทุน
    (Stop Loss) หรือจุดขายทำกำไร (Take Profit) ที่ตั้งไว้แล้วบ้าง — เวอร์ชันนี้ใช้ "ราคาปิด" จาก
    ผลสแกนรายวัน (df_scan_latest) เหมาะกับ Daily Scan ที่รันวันละครั้ง
    ต้องมีคอลัมน์ stop_loss_price, take_profit_price, sl_alert_sent, tp_alert_sent ในชีต
    PortfolioData ก่อน (เพิ่มได้จากหน้าเว็บโดยตรง ไม่ต้องแก้หัวตารางเองใน Google Sheets เพราะชีตนี้
    บันทึกจาก dict ทั้งก้อนอัตโนมัติอยู่แล้ว)
    """
    if df_scan_latest is None or df_scan_latest.empty or 'Ticker' not in df_scan_latest.columns:
        return []
    price_map = dict(zip(df_scan_latest['Ticker'], df_scan_latest['ราคาล่าสุด']))
    return _check_sl_tp_with_price_map(spreadsheet_name, price_map)


def get_portfolio_tickers_pending_sl_tp(spreadsheet_name):
    """
    🆕 ดึงรายชื่อหุ้นในพอร์ตของบัญชีที่ระบุ ที่ตั้ง SL หรือ TP ไว้แล้วแต่ยังไม่เคยแจ้งเตือน
    ใช้สำหรับดึงราคาสดแบบ real-time เฉพาะหุ้นที่จำเป็นเท่านั้น (ไม่ต้องดึงทั้งพอร์ต ประหยัดเวลา
    และลดความเสี่ยงโดน Yahoo Finance จำกัดการเรียกข้อมูล)
    """
    try:
        client = get_gsheet_client()
        sheet = get_cached_worksheet(client, spreadsheet_name, 'PortfolioData')
        records = sheet.get_all_records()
    except Exception:
        return []

    tickers = set()
    for row in records:
        ticker = str(row.get('หุ้น', '')).strip().upper()
        if not ticker:
            continue
        sl_price = row.get('stop_loss_price')
        sl_sent = str(row.get('sl_alert_sent', '')).strip().upper() == 'TRUE'
        tp_price = row.get('take_profit_price')
        tp_sent = str(row.get('tp_alert_sent', '')).strip().upper() == 'TRUE'
        if (sl_price and not sl_sent) or (tp_price and not tp_sent):
            tickers.add(ticker)
    return list(tickers)


def check_portfolio_sl_tp_alerts_realtime(spreadsheet_name):
    """
    🆕 เช็คหุ้นในพอร์ตของบัญชีที่ระบุ ว่าตัวไหนถึงจุด SL/TP แล้วบ้าง — เวอร์ชันนี้ดึง "ราคาสด"
    แบบ real-time (delay ~15 นาทีจาก Yahoo Finance) ต่อหุ้นโดยตรง แทนที่จะใช้ราคาปิดจากผลสแกน
    รายวัน เหมาะกับการเช็คถี่ๆ ระหว่างเวลาตลาดเปิด (ผ่าน workflow แยกต่างหากจาก Daily Scan)
    """
    tickers = get_portfolio_tickers_pending_sl_tp(spreadsheet_name)
    if not tickers:
        return []

    price_map = {}
    for t in tickers:
        info = get_cached_stock_info(f"{t}.BK")
        price = info.get('currentPrice') or info.get('regularMarketPrice')
        if price:
            price_map[t] = price

    return _check_sl_tp_with_price_map(spreadsheet_name, price_map)


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
        sheet = get_cached_worksheet(client, get_active_sheet_name(), 'Provident_Fund')
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
        sheet_pen = get_cached_worksheet(client, get_active_sheet_name(), 'Pension')
        return sheet_pen
    except Exception:
        return None
        
def get_latest_insurance_value():
    try:
        client = get_gsheet_client()
        sheet_ins = get_cached_worksheet(client, get_active_sheet_name(), 'Insurance')
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
        sheet_coop = get_cached_worksheet(client, get_active_sheet_name(), 'Coop')
        data = sheet_coop.get_all_records()
        if data:
            df_coop = pd.DataFrame(data)
            if not df_coop.empty and 'Coop_Value' in df_coop.columns:
                return float(str(df_coop.iloc[-1]['Coop_Value']).replace(',', ''))
    except Exception:
        pass
    return 0.0

def calculate_fund_result(cost_price, current_price, units):
    # 🔧 ทศนิยม: ต้นทุน/มูลค่า (ราคาต่อหน่วย x จำนวนหน่วย) ใช้ 4 ตำแหน่ง ให้ตรงกับหน่วยกองทุนรวม
    # (NAV/หน่วยลงทุน มักมีทศนิยมละเอียดถึง 4 ตำแหน่ง) ส่วนกำไร/ขาดทุนใช้ 2 ตำแหน่งเหมือนตัวเลข
    # เงินบาททั่วไป — ตามที่ใช้แสดงผล/บันทึกในแท็บกองทุนรวมทั้งหมด
    total_cost = cost_price * units
    current_value = current_price * units
    profit_loss = current_value - total_cost
    profit_loss_pct = (profit_loss / total_cost) * 100 if total_cost > 0 else 0
    return {
        "Total_Cost": round(total_cost, 4),
        "Current_Value": round(current_value, 4),
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
        sheet = get_cached_worksheet(client, get_active_sheet_name(), 'TFEX_History')
        
        records = sheet.get_all_records()
        df = pd.DataFrame(records)
        
        # 🔧 กันเหนียว: ถ้าตารางว่างสนิท (ไม่มีคอลัมน์ Trade_ID เลย) ให้ถือว่าไม่เจอรายการ
        # แทนที่จะปล่อยให้ error (แม้ในทางปฏิบัติจะไม่ค่อยเกิดเพราะต้องมีไม้เปิดอยู่ก่อนถึงจะมากดปิดได้)
        if 'Trade_ID' not in df.columns:
            print("Error: ไม่พบข้อมูลในตาราง TFEX_History")
            return False
        
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
        
        # ⭐️ สำคัญมาก: แปลงข้อมูลทั้งหมดให้เป็น Python Native Type (ป้องกัน TypeError จาก gspread)
        # 🔧 แก้บั๊ก: เดิมมี "M: Points" ต่อท้ายแล้วเขียนทับด้วย range C:M แต่คอลัมน์ M จริงในตาราง
        # (ตาม cols ของ save_data_to_sheet) คือ "Reason" ไม่ใช่ Points ทำให้ทุกครั้งที่ปิดสถานะ
        # ค่า Reason ที่ผู้ใช้กรอกไว้ตอนเปิดสถานะถูกเขียนทับด้วยตัวเลข points ไปโดยไม่ตั้งใจ (เกิด
        # เหมือนกันทั้งบน Google Sheets เดิมและ Firestore เพราะเป็นบั๊กเดิมของโค้ด ไม่เกี่ยวกับการย้าย
        # ระบบ) ตอนนี้ตัดคอลัมน์ M ออกจากการอัปเดต ให้ค่า Reason เดิมไม่ถูกแตะเลยตอนปิดสถานะ
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
        ]

        # อัปเดตข้อมูลลง Google Sheets แบบระบุ Range
        sheet.update(range_name=f'C{row_index}:L{row_index}', values=[data_to_update])
        
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
        sheet_cash = get_cached_worksheet(client, spreadsheet_name, 'CashFlow')
        records_cash = sheet_cash.get_all_records()
        
        total_cash_flow = 0.0
        if records_cash:
            df_cash = pd.DataFrame(records_cash)
            if 'Amount' in df_cash.columns:
                df_cash['Amount'] = pd.to_numeric(df_cash['Amount'], errors='coerce').fillna(0)
                total_cash_flow = float(df_cash['Amount'].sum())
                
        # 2. บังคับคำนวณต้นทุนหุ้นทั้งหมดจาก shares * avg_price โดยตรง
        sheet_portfolio = get_cached_worksheet(client, spreadsheet_name, 'PortfolioData')
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
        sheet = get_cached_worksheet(client, get_active_sheet_name(), "Cash_Flow")
        # FirestoreWorksheet.append_rows() ต้องรู้ชื่อคอลัมน์ (Firestore ไม่มี "หัวตาราง" แบบ
        # Sheets) ส่วน gspread เวอร์ชันจริงไม่รับ kwarg นี้ จึงส่งเฉพาะตอนใช้ Firestore เท่านั้น
        kwargs = {'columns': df.columns.tolist()} if _use_firestore() else {}
        sheet.append_rows(df.values.tolist(), **kwargs)
        return True
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการบันทึก Cash_Flow: {e}")
        return False 


def save_data_to_sheet(new_df, sheet_name):
    try:
        client = get_gsheet_client()
        # 🔧 แก้บั๊ก: เดิมเขียน ID ของ Google Sheet ตายตัวไว้ ตอนนี้เปลี่ยนตามผู้ใช้ที่ login แล้ว
        sheet = get_cached_worksheet(client, get_active_sheet_name(), 'TFEX_History')
        
        cols = ["Trade_ID", "Date_Open", "Date_Close", "Series", "Status", "Size", "Open_Price", 
                "Close_Price", "Realized", "Comm", "Net_Profit", "Win_Lose", "Reason"]
        
        new_df = new_df.reindex(columns=cols)
        kwargs = {'columns': cols} if _use_firestore() else {}
        sheet.append_rows(new_df.values.tolist(), **kwargs)

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
            sheet = get_cached_worksheet(client, get_active_sheet_name(), 'Dividend')
            
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
def load_data(sheet_name, active_sheet_name):
    # 🔧 แก้บั๊ก: เดิมฟังก์ชันนี้ "จำ" ผลลัพธ์แยกตามชื่อ worksheet (เช่น TFEX_History) เท่านั้น
    # โดยไม่รู้ว่าผู้ใช้คนไหนเป็นคนขอ (เรียก get_active_sheet_name() ข้างในเฉยๆ) ทำให้สลับ user
    # แล้วยังเห็นข้อมูล TFEX/Cash_Flow/แผนเทรด ของคนก่อนหน้าค้างอยู่ ตอนนี้รับชื่อชีตของผู้ใช้
    # (active_sheet_name) เป็นพารามิเตอร์ตรงๆ เพื่อให้ระบบจำแยกตามผู้ใช้อัตโนมัติ
    # 🔧 แก้บั๊กเพิ่ม: เดิมไม่มีระบบลองใหม่อัตโนมัติเลย พอเจอโควตา Google Sheets ชั่วคราว (429 -
    # พบบ่อยตอนสลับผู้ใช้ที่มีหลายแท็บยิงขอข้อมูลพร้อมกัน) จะยอมแพ้ทันทีแล้วคืนตารางว่างสนิท
    # (ไม่มีแม้แต่ชื่อคอลัมน์) ทำให้จุดที่อ่านคอลัมน์ตรงๆ พังต่อ ตอนนี้ลองใหม่ก่อน 3 ครั้ง
    last_error = None
    for attempt in range(3):
        try:
            client = get_gsheet_client()
            sheet = get_cached_worksheet(client, active_sheet_name, sheet_name)
            data = sheet.get_all_records()
            if data:
                return pd.DataFrame(data)
            # ถ้าชีตว่างสนิท (มีแต่หัวตาราง ไม่มีแถวข้อมูล) get_all_records() จะคืนค่าว่างเปล่า
            # ทำให้ตารางที่ได้ไม่มีแม้แต่ "ชื่อคอลัมน์" เลย (ต่างจากตารางเปล่าที่ยังมีชื่อคอลัมน์ครบ)
            # โค้ดทุกจุดที่เช็คหาคอลัมน์ (เช่น 'Net_Profit' in df.columns) จะพังทันทีเพราะไม่เจอคอลัมน์เลยสักตัว
            # ตอนนี้ดึงแค่แถวหัวตารางมาสร้างตารางเปล่าที่ยังมีชื่อคอลัมน์ครบแทน เพื่อให้จุดอื่นๆ ทำงานได้ปกติ
            headers = sheet.row_values(1)
            return pd.DataFrame(columns=headers) if headers else pd.DataFrame()
        except Exception as e:
            last_error = e
            if "429" in str(e) or "Quota exceeded" in str(e):
                time.sleep(1.5 * (attempt + 1))
                continue
            break
    st.error(f"โหลดข้อมูล {sheet_name} ไม่สำเร็จ: {last_error}")
    return pd.DataFrame()



@st.cache_data(ttl=3600)  
def get_cached_stock_info(ticker):
    """
    ดึงข้อมูลพื้นฐานของหุ้น (P/E, Market Cap, Margin ฯลฯ) จาก Yahoo Finance ผ่าน yfinance
    🔧 แก้บั๊ก: เดิมลองดึงข้อมูลแค่ครั้งเดียว ไม่มีระบบลองใหม่อัตโนมัติเลย พอ Yahoo Finance สะดุด
    ชั่วขณะ (rate limit/เชื่อมต่อสะดุด — เกิดขึ้นเป็นครั้งคราวกับทุกหุ้น ไม่ใช่ปัญหาเฉพาะตัวใดตัว
    หนึ่ง) จะยอมแพ้ทันที ตอนนี้เพิ่ม retry แบบ exponential backoff + jitter เหมือนจุดอื่นๆ ในระบบ
    ที่เคยแก้ปัญหา Yahoo Finance สะดุดมาก่อน (ราคาทอง, SET Index) ลองสูงสุด 3 ครั้งก่อนจะยอมแพ้จริงๆ
    """
    last_error = None
    for attempt in range(3):
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            if not info or len(info) <= 1:
                last_error = "ได้ข้อมูลว่างเปล่ากลับมา"
            else:
                return info
        except Exception as e:
            last_error = str(e)

        if attempt < 2:  # ไม่ต้องหน่วงเวลาหลังจากลองครั้งสุดท้ายแล้ว
            time.sleep((2 ** (attempt + 1)) + random.uniform(0.5, 1.5))

    print(f"Warning: Could not fetch info for {ticker} after 3 attempts due to: {last_error}")
    return {}


# =============================================================
# 8. ฟังก์ชันการจัดการบันทึกและซิงค์ข้อมูลลง Google Sheets (Sync & Sheets Operations)
# =============================================================
def clear_and_save_data(df, sheet_name):
    try:
        client = get_gsheet_client()
        sheet = get_cached_worksheet(client, get_active_sheet_name(), 'TradingPlan')
        
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
    sheet = get_cached_worksheet(client, get_active_sheet_name(), 'StockData')
    
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
    sheet = get_cached_worksheet(client, get_active_sheet_name(), 'JournalData')
    
    sheet.clear()
    sheet.update([df_temp.columns.values.tolist()] + df_temp.fillna('').values.tolist())


def load_journal():
    # 🔧 แก้บั๊ก: เดิมฟังก์ชันนี้ไม่มีระบบลองใหม่อัตโนมัติเลย พอเจอโควตา Google Sheets ชั่วคราว (429)
    # จะ error ทันที ต่างจากฟังก์ชันอื่นๆ ในแอปที่มีระบบลองใหม่อยู่แล้ว ตอนนี้เพิ่มให้เหมือนกัน
    last_error = None
    for attempt in range(3):
        try:
            client = get_gsheet_client()
            sheet = get_cached_worksheet(client, get_active_sheet_name(), 'JournalData')
            data = sheet.get_all_records()
            st.session_state.journal_data = data
            return
        except Exception as e:
            last_error = e
            if "429" in str(e) or "Quota exceeded" in str(e):
                time.sleep(1.5 * (attempt + 1))
                continue
            break
    st.error(f"ไม่สามารถโหลดข้อมูลจาก Google Sheets ได้: {last_error}")
    st.session_state.journal_data = []


def save_portfolio():
    try:
        if st.session_state.my_portfolio is None:
            st.session_state.my_portfolio = []
            
        client = get_gsheet_client()
        sheet = get_cached_worksheet(client, get_active_sheet_name(), 'PortfolioData')
        
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
    # 🔧 แก้บั๊ก: เดิมฟังก์ชันนี้ไม่มีระบบลองใหม่อัตโนมัติเลย พอเจอโควตา Google Sheets ชั่วคราว (429)
    # จะ error ทันที (โดยเฉพาะตอนสลับผู้ใช้ที่มีหลายแท็บยิงขอข้อมูลพร้อมกันจำนวนมาก)
    last_error = None
    for attempt in range(3):
        try:
            client = get_gsheet_client()
            sheet = get_cached_worksheet(client, get_active_sheet_name(), 'PortfolioData')
            data = sheet.get_all_records()
            st.session_state.my_portfolio = data if data else []
            return
        except Exception as e:
            last_error = e
            if "429" in str(e) or "Quota exceeded" in str(e):
                time.sleep(1.5 * (attempt + 1))
                continue
            break
    st.error(f"โหลดพอร์ตไม่สำเร็จ: {last_error}")
    st.session_state.my_portfolio = []


def log_portfolio_snapshot():
    """บันทึกยอดพอร์ตรายวันลงตาราง Portfolio_History"""
    client = get_gsheet_client()
    sheet = get_cached_worksheet(client, get_active_sheet_name(), 'Portfolio_History')
    
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
    cash_df = load_data("Cash_Flow", get_active_sheet_name())
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
    sheet = get_cached_worksheet(client, get_active_sheet_name(), 'Portfolio_History')
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
        st.plotly_chart(style_plotly(fig1), use_container_width=True)
        
    with col2:
        st.subheader("💰 พอร์ตจริง vs เงินลงทุน")
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=df['Date'], y=df['Market_Value'], name='มูลค่าพอร์ต', fill='tozeroy'))
        fig2.add_trace(go.Scatter(x=df['Date'], y=df['Invested_Capital'], name='เงินทุนจริง', line=dict(dash='dash')))
        st.plotly_chart(style_plotly(fig2), use_container_width=True)

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
        sheet_cash = get_cached_worksheet(client, get_active_sheet_name(), 'CashFlow')
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
        sheet = get_cached_worksheet(client, get_active_sheet_name(), 'Portfolio_History')
        
        sheet.clear()
        sheet.update([df_history.columns.values.tolist()] + df_history.values.tolist())
        
        st.success("อัปเดตเรียบร้อย! กราฟของคุณพร้อมใช้งานแล้ว")
        st.rerun()
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการบันทึก Portfolio_History: {e}")
    
def get_current_portfolio_value():
    # ฟังก์ชันนี้ดึงราคาปัจจุบันของหุ้นทุกตัวใน st.session_state.my_portfolio
    # 🔧 แก้บั๊ก: เหมือนจุดที่แก้ใน get_total_market_value() ด้านบน รองรับชื่อคอลัมน์ทั้งไทย/อังกฤษ
    total_market_value = 0
    for item in st.session_state.my_portfolio:
        ticker = item.get('หุ้น', item.get('Ticker', ''))
        try:
            shares = float(str(item.get('จำนวน', item.get('shares', 0))).replace(',', ''))
        except (ValueError, TypeError):
            shares = 0.0
        try:
            avg_price = float(str(item.get('ต้นทุนเฉลี่ย', item.get('avg_price', 0))).replace(',', ''))
        except (ValueError, TypeError):
            avg_price = 0.0
        # ดึงราคาตลาดปัจจุบัน (Real-time)
        try:
            m_price = yf.Ticker(f"{ticker}.BK").history(period="1d")['Close'].iloc[-1]
        except:
            m_price = avg_price # ถ้าดึงไม่ได้ ให้ใช้ราคาต้นทุน
        total_market_value += (shares * m_price)
    return total_market_value

def update_stock_data(df):
    client = get_gsheet_client()
    # 🔧 แก้บั๊ก: เดิมเขียน ID ของ Google Sheet ตายตัวไว้ ตอนนี้เปลี่ยนตามผู้ใช้ที่ login แล้ว
    sheet = get_cached_worksheet(client, get_active_sheet_name(), 'StockData')
    
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
        sheet = get_cached_worksheet(client, get_active_sheet_name(), 'CashFlow')
        
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
            sheet = get_cached_worksheet(client, get_active_sheet_name(), 'JournalData')
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
        sheet = get_cached_worksheet(client, get_active_sheet_name(), 'CashFlow')
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
            # 🔧 แก้บั๊ก: เดิมอ่านคอลัมน์ 'shares' ตรงๆ เท่านั้น ถ้าชีตของผู้ใช้บันทึกด้วยชื่อ
            # คอลัมน์ภาษาไทย ('จำนวน', 'ต้นทุนเฉลี่ย') แทน จะเจอ KeyError ทันที
            # (เจอกับบัญชีแฟนที่ Google Sheet บันทึกชื่อคอลัมน์ต่างจากของคุณ)
            # ตอนนี้รองรับทั้งสองแบบ เหมือนจุดอื่นๆ ในแอปที่ทำไว้อยู่แล้ว
            ticker = item.get('หุ้น', item.get('Ticker', ''))
            try:
                shares = float(str(item.get('จำนวน', item.get('shares', 0))).replace(',', ''))
            except (ValueError, TypeError):
                shares = 0.0
            try:
                avg_price = float(str(item.get('ต้นทุนเฉลี่ย', item.get('avg_price', 0))).replace(',', ''))
            except (ValueError, TypeError):
                avg_price = 0.0
            try:
                # ดึงราคาปิดล่าสุด
                m_price = yf.Ticker(f"{ticker}.BK").history(period="1d")['Close'].iloc[-1]
                # 🔧 แก้บั๊ก: เดิมถ้าดึงราคาได้แต่ค่าที่ได้ดันเป็น NaN (เช่น หุ้นถูกพักการซื้อขาย
                # หรือข้อมูลผิดปกติชั่วคราว) จะไม่เข้า except เลย เพราะ NaN ไม่ใช่ error แต่เป็น
                # float ที่ถูกต้องตามชนิดข้อมูล ทำให้ total_val กลายเป็น NaN ไปด้วยทั้งก้อน แล้ว
                # ลามไปทำให้หน้า Risk Management พังตอนแปลงเป็น int() ตอนนี้เช็ค NaN เพิ่ม แล้ว
                # ตกไปใช้ราคาต้นทุนแทนเหมือนกับกรณี error ปกติ
                if pd.isna(m_price):
                    m_price = avg_price
            except:
                m_price = avg_price # ถ้าดึงไม่ได้ ให้ใช้ต้นทุนไปก่อน
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
    
    st.plotly_chart(style_plotly(fig), use_container_width=True)
    
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
        sheet = get_cached_worksheet(client, get_active_sheet_name(), 'StockData')
        data = sheet.get_all_records()
        
        if not data:
            st.warning("ไม่มีข้อมูลใน Google Sheet ครับ")
            # 🔧 แก้บั๊ก: เดิม return None ตรงนี้ ทำให้โค้ดที่เรียกใช้ (ซึ่งคาดหวังว่าจะได้ตาราง
            # กลับไป แล้วจะเช็ค .empty ต่อ) พังทันทีด้วย AttributeError เพราะ None ไม่มี .empty
            # ตอนนี้คืนตารางเปล่าแทน ปลอดภัยกว่าและพฤติกรรมเหมือนกับตอนไม่มีข้อมูลทุกจุดอื่นในแอป
            return pd.DataFrame()
            
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
        sheet = get_cached_worksheet(client, get_active_sheet_name(), sheet_name)
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
        "EA.BK": "ทรัพยากร", "EASTW.BK": "ทรัพยากร", "ECF.BK": "สินค้าอุตสาหกรรม", "ECL.BK": "ธุรกิจการเงิน", "EFORL.BK": "บริการ", "EGCO.BK": "ทรัพยากร", "EKH.BK": "บริการ", "EMC.BK": "อสังหาริมทรัพย์และก่อสร้าง", "EP.BK": "ทรัพยากร", "EPG.BK": "สินค้าอุตสาหกรรม", "ERW.BK": "บริการ", "ESTAR.BK": "อสังหาริมทรัพย์และก่อสร้าง", "ETC.BK": "ทรัพยากร", "EVER.BK": "อสังหาริมทรัพย์และก่อสร้าง", "F&D.BK": "เกษตรและอุตสาหกรรมอาหาร", "FANCY.BK": "สินค้าอุตสาหกรรม", "FENIX.BK": "สินค้าอุตสาหกรรม", "FMT.BK": "สินค้าอุตสาหกรรม", "FN.BK": "บริการ", "FNS.BK": "ธุรกิจการเงิน", "FORTH.BK": "เทคโนโลยี", "FPI.BK": "สินค้าอุตสาหกรรม", "FPT.BK": "อสังหาริมทรัพย์และก่อสร้าง", "FSMART.BK": "บริการ", "FVC.BK": "บริการ",
        "GABLE.BK": "เทคโนโลยี", "FVC.BK": "บริการ", "GBX.BK": "ธุรกิจการเงิน", "GC.BK": "ทรัพยากร", "GCAP.BK": "ธุรกิจการเงิน", "GEL.BK": "อสังหาริมทรัพย์และก่อสร้าง", "GFPT.BK": "เกษตรและอุตสาหกรรมอาหาร", "GGC.BK": "ทรัพยากร", "GIFT.BK": "เกษตรและอุตสาหกรรมอาหาร", "GJ.BK": "สินค้าอุตสาหกรรม", "GLOBAL.BK": "บริการ", "GLOW.BK": "ทรัพยากร", "GPSC.BK": "ทรัพยากร", "GRAMMY.BK": "สื่อสิ่งพิมพ์และสื่อสาร", "GULF.BK": "ทรัพยากร", "GUNKUL.BK": "ทรัพยากร", "GYT.BK": "สินค้าอุตสาหกรรม", "HANA.BK": "เทคโนโลยี", "HENG.BK": "ธุรกิจการเงิน", "HMPRO.BK": "บริการ", "HTC.BK": "เกษตรและอุตสาหกรรมอาหาร", "HTECH.BK": "สินค้าอุตสาหกรรม", "HUMAN.BK": "เทคโนโลยี", "HYDB.BK": "บริการ", "I2.BK": "เทคโนโลยี", "ICN.BK": "เทคโนโลยี", "ILINK.BK": "เทคโนโลยี", "ILM.BK": "บริการ", "IMH.BK": "บริการ", "INET.BK": "เทคโนโลยี", "INGRS.BK": "สินค้าอุตสาหกรรม", "INSET.BK": "เทคโนโลยี", "IRC.BK": "สินค้าอุตสาหกรรม", "IRPC.BK": "ทรัพยากร", "IT.BK": "บริการ", "ITD.BK": "อสังหาริมทรัพย์และก่อสร้าง", "ITI.BK": "บริการ", "ITEL.BK": "เทคโนโลยี", "J.BK": "อสังหาริมทรัพย์และก่อสร้าง", " JAS.BK": "สื่อสิ่งพิมพ์และสื่อสาร", "JCK.BK": "อสังหาริมทรัพย์และก่อสร้าง", "JDF.BK": "เกษตรและอุตสาหกรรมอาหาร", "JKN.BK": "บริการ", "JMART.BK": "บริการ", "JMT.BK": "ธุรกิจการเงิน", "JR.BK": "บริการ", "JTS.BK": "เทคโนโลยี", "JUBILE.BK": "บริการ", "JUTHA.BK": "บริการ",
        "KAMART.BK": "บริการ", "KBANK.BK": "ธุรกิจการเงิน", "KBS.BK": "เกษตรและอุตสาหกรรมอาหาร", "KCAR.BK": "บริการ", "KCE.BK": "เทคโนโลยี", "KGI.BK": "ธุรกิจการเงิน", "KKP.BK": "ธุรกิจการเงิน", "KSL.BK": "เกษตรและอุตสาหกรรมอาหาร", "KTB.BK": "ธุรกิจการเงิน", "KTC.BK": "ธุรกิจการเงิน", "KTIS.BK": "เกษตรและอุตสาหกรรมอาหาร", "KUN.BK": "อสังหาริมทรัพย์และก่อสร้าง", "KWM.BK": "สินค้าอุตสาหกรรม", "KYE.BK": "สินค้าอุตสาหกรรม", "L&E.BK": "สินค้าอุตสาหกรรม", "LALIN.BK": "อสังหาริมทรัพย์และก่อสร้าง", "LANNA.BK": "ทรัพยากร", "LH.BK": "อสังหาริมทรัพย์และก่อสร้าง", "LHFG.BK": "ธุรกิจการเงิน", "LHK.BK": "สินค้าอุตสาหกรรม", "LIT.BK": "ธุรกิจการเงิน", "LOXLEY.BK": "บริการ", "LPH.BK": "บริการ", "LPN.BK": "อสังหาริมทรัพย์และก่อสร้าง", "LRH.BK": "บริการ", "LST.BK": "เกษตรและอุตสาหกรรมอาหาร", "M.BK": "บริการ", "MAJOR.BK": "บริการ", "M-CHAI.BK": "บริการ", "MALEE.BK": "เกษตรและอุตสาหกรรมอาหาร", "MASTER.BK": "บริการ", "MATI.BK": "สื่อสิ่งพิมพ์และสื่อสาร", "MBK.BK": "บริการ", "MC.BK": "สินค้าอุตสาหกรรม", "M-DAE.BK": "บริการ", "MDX.BK": "อสังหาริมทรัพย์และก่อสร้าง", "MEB.BK": "บริการ", "MEGA.BK": "บริการ", "METCO.BK": "สินค้าอุตสาหกรรม", "MFC.BK": "ธุรกิจการเงิน", "MGC.BK": "บริการ", "MGI.BK": "บริการ", "MINT.BK": "บริการ", "MK.BK": "อสังหาริมทรัพย์และก่อสร้าง", "ML.BK": "ธุรกิจการเงิน", "MOONG.BK": "สินค้าอุตสาหกรรม", "MPIC.BK": "สื่อสิ่งพิมพ์และสื่อสาร", "MSC.BK": "เทคโนโลยี", "MTC.BK": "ธุรกิจการเงิน", "MTI.BK": "ธุรกิจการเงิน", "MTW.BK": "สินค้าอุตสาหกรรม", "MULTI.BK": "บริการ", "MVC.BK": "สินค้าอุตสาหกรรม", "NC.BK": "สินค้าอุตสาหกรรม", "NCH.BK": "อสังหาริมทรัพย์และก่อสร้าง", "NCL.BK": "บริการ", "NEO.BK": "สินค้าอุตสาหกรรม", "NER.BK": "เกษตรและอุตสาหกรรมอาหาร", "NETBAY.BK": "เทคโนโลยี", "NEW.BK": "บริการ", "NEX.BK": "บริการ", "NOBLE.BK": "อสังหาริมทรัพย์และก่อสร้าง", "NOVA.BK": "สินค้าอุตสาหกรรม", "NPK.BK": "เกษตรและอุตสาหกรรมอาหาร", "NSL.BK": "เกษตรและอุตสาหกรรมอาหาร", "NTV.BK": "บริการ", "NVD.BK": "อสังหาริมทรัพย์และก่อสร้าง", "NYT.BK": "บริการ",
        "O.BK": "บริการ", "OCB.BK": "ธุรกิจการเงิน", "OKJ.BK": "บริการ", "ORI.BK": "อสังหาริมทรัพย์และก่อสร้าง", "OSP.BK": "เกษตรและอุตสาหกรรมอาหาร", "PAC.BK": "สินค้าอุตสาหกรรม", "PACO.BK": "สินค้าอุตสาหกรรม", "PAP.BK": "สินค้าอุตสาหกรรม", "PATH.BK": "บริการ", "PB.BK": "เกษตรและอุตสาหกรรมอาหาร", "PCSGH.BK": "สินค้าอุตสาหกรรม", "PDG.BK": "สินค้าอุตสาหกรรม", "PDI.BK": "ทรัพยากร", "PEACE.BK": "อสังหาริมทรัพย์และก่อสร้าง", "PERM.BK": "สินค้าอุตสาหกรรม", "PF.BK": "อสังหาริมทรัพย์และก่อสร้าง", "PHG.BK": "บริการ", "PJW.BK": "สินค้าอุตสาหกรรม", "PLANB.BK": "บริการ", "PLAT.BK": "อสังหาริมทรัพย์และก่อสร้าง", "PLUS.BK": "เกษตรและอุตสาหกรรมอาหาร", "PM.BK": "เกษตรและอุตสาหกรรมอาหาร", "PMTA.BK": "เกษตรและอุตสาหกรรมอาหาร", "POLAR.BK": "อสังหาริมทรัพย์และก่อสร้าง", "POLY.BK": "สินค้าอุตสาหกรรม", "POPN.BK": "เกษตรและอุตสาหกรรมอาหาร", "PORT.BK": "บริการ", "POST.BK": "สื่อสิ่งพิมพ์และสื่อสาร", "PPPM.BK": "เกษตรและอุตสาหกรรมอาหาร", "PR9.BK": "บริการ", "PRAKIT.BK": "บริการ", "PRAPAT.BK": "บริการ", "PREB.BK": "อสังหาริมทรัพย์และก่อสร้าง", "PRG.BK": "เกษตรและอุตสาหกรรมอาหาร", "PRM.BK": "บริการ", "PRO.BK": "สินค้าอุตสาหกรรม", "PROEN.BK": "เทคโนโลยี", "PSG.BK": "อสังหาริมทรัพย์และก่อสร้าง", "PSH.BK": "อสังหาริมทรัพย์และก่อสร้าง", "PSI.BK": "สินค้าอุตสาหกรรม", "PSL.BK": "บริการ", "PSTC.BK": "ทรัพยากร", "PT.BK": "บริการ", "PTG.BK": "ทรัพยากร", "PTL.BK": "สินค้าอุตสาหกรรม", "PTT.BK": "ทรัพยากร", "PTTEP.BK": "ทรัพยากร", "PTTGC.BK": "ทรัพยากร", "PYLON.BK": "อสังหาริมทรัพย์และก่อสร้าง", "Q-CON.BK": "สินค้าอุตสาหกรรม", "QH.BK": "อสังหาริมทรัพย์และก่อสร้าง", "QLT.BK": "สินค้าอุตสาหกรรม", "QTC.BK": "สินค้าอุตสาหกรรม", "RABBIT.BK": "ธุรกิจการเงิน", "RATCH.BK": "ทรัพยากร", "RBF.BK": "เกษตรและอุตสาหกรรมอาหาร", "RCL.BK": "บริการ", "RJH.BK": "บริการ", "ROJNA.BK": "อสังหาริมทรัพย์และก่อสร้าง", "RP.BK": "บริการ", "RPC.BK": "ทรัพยากร", "RPH.BK": "บริการ", "RS.BK": "บริการ", "RT.BK": "อสังหาริมทรัพย์และก่อสร้าง", "RTC.BK": "บริการ", "RWI.BK": "สินค้าอุตสาหกรรม",
        "S.BK": "อสังหาริมทรัพย์และก่อสร้าง", "SABINA.BK": "สินค้าอุตสาหกรรม", "SABUY.BK": "บริการ", "SAF.BK": "อสังหาริมทรัพย์และก่อสร้าง", "SAFE.BK": "บริการ", "SAK.BK": "ธุรกิจการเงิน", "SAMCO.BK": "อสังหาริมทรัพย์และก่อสร้าง", "SAMART.BK": "เทคโนโลยี", "SAMTEL.BK": "เทคโนโลยี", "SAPPE.BK": "เกษตรและอุตสาหกรรมอาหาร", "SAT.BK": "สินค้าอุตสาหกรรม", "SBNEXT.BK": "บริการ", "SC.BK": "อสังหาริมทรัพย์และก่อสร้าง", "SCAP.BK": "ธุรกิจการเงิน", "SCB.BK": "ธุรกิจการเงิน", "SCC.BK": "สินค้าอุตสาหกรรม", "SCCC.BK": "สินค้าอุตสาหกรรม", "SCG.BK": "บริการ", "SCGD.BK": "สินค้าอุตสาหกรรม", "SCI.BK": "เทคโนโลยี", "SCN.BK": "ทรัพยากร", "SCP.BK": "สินค้าอุตสาหกรรม", "SDC.BK": "เทคโนโลยี", "SE-ED.BK": "บริการ", "SEAFCO.BK": "อสังหาริมทรัพย์และก่อสร้าง", "SECURE.BK": "เทคโนโลยี", "SENA.BK": "อสังหาริมทรัพย์และก่อสร้าง", "SF.BK": "บริการ", "SFT.BK": "สินค้าอุตสาหกรรม", "SGC.BK": "ธุรกิจการเงิน", "SGP.BK": "ทรัพยากร", "SGT.BK": "ธุรกิจการเงิน", "SHR.BK": "บริการ", "SICT.BK": "เทคโนโลยี", "SIMAT.BK": "เทคโนโลยี", "SINO.BK": "บริการ", "SINGER.BK": "ธุรกิจการเงิน", "SIRI.BK": "อสังหาริมทรัพย์และก่อสร้าง", "SIS.BK": "เทคโนโลยี", "SISB.BK": "บริการ", "SK.BK": "อสังหาริมทรัพย์และก่อสร้าง", "SKN.BK": "เกษตรและอุตสาหกรรมอาหาร", "SKR.BK": "บริการ", "SKY.BK": "บริการ", "SLM.BK": "บริการ", "SM.BK": "บริการ", "SMART.BK": "สินค้าอุตสาหกรรม", "SMD.BK": "บริการ", "SMIT.BK": "สินค้าอุตสาหกรรม", "SMPC.BK": "สินค้าอุตสาหกรรม", "SNC.BK": "สินค้าอุตสาหกรรม", "SO.BK": "บริการ", "SOLAR.BK": "ทรัพยากร", "SONIC.BK": "บริการ", "SORKON.BK": "เกษตรและอุตสาหกรรมอาหาร", "SPA.BK": "บริการ", "SPALI.BK": "อสังหาริมทรัพย์และก่อสร้าง", "SPc.BK": "สินค้าอุตสาหกรรม", "SPCG.BK": "ทรัพยากร", "SPHI.BK": "บริการ", "SPI.BK": "สินค้าอุตสาหกรรม", "SPRC.BK": "ทรัพยากร", "SPSU.BK": "สินค้าอุตสาหกรรม", "SPVI.BK": "บริการ", "SQ.BK": "บริการ", "SR.BK": "อสังหาริมทรัพย์และก่อสร้าง", "SRICHA.BK": "บริการ", "SSP.BK": "ทรัพยากร", "SSPF.BK": "กองทุนรวมอสังหาริมทรัพย์และกองทรัสต์เพื่อการลงทุนในอสังหาริมทรัพย์", "SST.BK": "บริการ", "STA.BK": "เกษตรและอุตสาหกรรมอาหาร", 
        "STANLY.BK": "สินค้าอุตสาหกรรม", "STAR.BK": "สินค้าอุตสาหกรรม", "STARK.BK": "สินค้าอุตสาหกรรม", "STC.BK": "อสังหาริมทรัพย์และก่อสร้าง", "STGT.BK": "เกษตรและอุตสาหกรรมอาหาร", "STPI.BK": "สินค้าอุตสาหกรรม", "SUC.BK": "สินค้าอุตสาหกรรม", "SUN.BK": "เกษตรและอุตสาหกรรมอาหาร", "SVR.BK": "อสังหาริมทรัพย์และก่อสร้าง", "SVT.BK": "บริการ", "SYNEX.BK": "เทคโนโลยี", "SYNTEC.BK": "อสังหาริมทรัพย์และก่อสร้าง", "T.BK": "บริการ", "TAE.BK": "เกษตรและอุตสาหกรรมอาหาร", "TAKUNI.BK": "บริการ", "TASCO.BK": "สินค้าอุตสาหกรรม", "TBN.BK": "เทคโนโลยี", "TC.BK": "เกษตรและอุตสาหกรรมอาหาร", "TCAP.BK": "ธุรกิจการเงิน", "TCC.BK": "สินค้าอุตสาหกรรม", "TCCC.BK": "เกษตรและอุตสาหกรรมอาหาร", "TCJ.BK": "สินค้าอุตสาหกรรม", "TCM.BK": "สินค้าอุตสาหกรรม", "TFG.BK": "เกษตรและอุตสาหกรรมอาหาร", "TFM.BK": "เกษตรและอุตสาหกรรมอาหาร", "TFMAMA.BK": "เกษตรและอุตสาหกรรมอาหาร", "TGPRO.BK": "สินค้าอุตสาหกรรม", "TH.BK": "ธุรกิจการเงิน", "THAI.BK": "บริการ", "THANA.BK": "อสังหาริมทรัพย์และก่อสร้าง", "THANI.BK": "ธุรกิจการเงิน", "THG.BK": "บริการ", "THIP.BK": "สินค้าอุตสาหกรรม", "TIDLOR.BK": "ธุรกิจการเงิน", "TIPH.BK": "ธุรกิจการเงิน", "TISCO.BK": "ธุรกิจการเงิน", "TK.BK": "ธุรกิจการเงิน", "TKN.BK": "เกษตรและอุตสาหกรรมอาหาร", "TKS.BK": "บริการ", "TKT.BK": "สินค้าอุตสาหกรรม", "TLI.BK": "ธุรกิจการเงิน", "TM.BK": "บริการ", "TMC.BK": "สินค้าอุตสาหกรรม", "TMD.BK": "สินค้าอุตสาหกรรม", "TMILL.BK": "เกษตรและอุตสาหกรรมอาหาร", "TMT.BK": "สินค้าอุตสาหกรรม", "TNDT.BK": "บริการ", "TNH.BK": "บริการ", "TNP.BK": "บริการ", "TNR.BK": "เกษตรและอุตสาหกรรมอาหาร", "TOA.BK": "สินค้าอุตสาหกรรม", "TOG.BK": "สินค้าอุตสาหกรรม", "TOP.BK": "ทรัพยากร", "TPBI.BK": "สินค้าอุตสาหกรรม", "TPCH.BK": "ทรัพยากร", "TPIPL.BK": "สินค้าอุตสาหกรรม", "TPIPP.BK": "ทรัพยากร", "TPL.BK": "บริการ", "TPOLY.BK": "อสังหาริมทรัพย์และก่อสร้าง", "TPP.BK": "สินค้าอุตสาหกรรม", "TPS.BK": "เทคโนโลยี", "TQM.BK": "ธุรกิจการเงิน", "TR.BK": "บริการ", "TRC.BK": "อสังหาริมทรัพย์และก่อสร้าง", "TRP.BK": "บริการ", "TRUE.BK": "สื่อสิ่งพิมพ์และสื่อสาร", 
        "TSE.BK": "ทรัพยากร", "TSI.BK": "ธุรกิจการเงิน", " TSR.BK": "บริการ", "TSTE.BK": "เกษตรและอุตสาหกรรมอาหาร", "TSTH.BK": "สินค้าอุตสาหกรรม", "TTA.BK": "บริการ", "TTB.BK": "ธุรกิจการเงิน", "TTCL.BK": "บริการ", "TTW.BK": "ทรัพยากร", "TU.BK": "เกษตรและอุตสาหกรรมอาหาร", "TVD.BK": "บริการ", "TVDH.BK": "บริการ", "TVO.BK": "เกษตรและอุตสาหกรรมอาหาร", "TWPC.BK": "เกษตรและอุตสาหกรรมอาหาร", "TYCN.BK": "สินค้าอุตสาหกรรม", "UAC.BK": "ทรัพยากร", "UBIS.BK": "สินค้าอุตสาหกรรม", "UEC.BK": "สินค้าอุตสาหกรรม", "UMC.BK": "สินค้าอุตสาหกรรม", "UNIQ.BK": "อสังหาริมทรัพย์และก่อสร้าง", "UPF.BK": "ธุรกิจการเงิน", "UPOIC.BK": "เกษตรและอุตสาหกรรมอาหาร", "UV.BK": "อสังหาริมทรัพย์และก่อสร้าง", "UVAN.BK": "เกษตรและอุตสาหกรรมอาหาร", "VCOM.BK": "เทคโนโลยี", "VGI.BK": "บริการ", "VIBHA.BK": "บริการ", "VL.BK": "บริการ", "VNG.BK": "สินค้าอุตสาหกรรม", "WACOAL.BK": "สินค้าอุตสาหกรรม", "WAVE.BK": "บริการ", "WHA.BK": "อสังหาริมทรัพย์และก่อสร้าง", "WHAUP.BK": "ทรัพยากร", "WICE.BK": "บริการ", "WIN.BK": "สินค้าอุตสาหกรรม", "WINMED.BK": "บริการ", "WINNER.BK": "เกษตรและอุตสาหกรรมอาหาร", "WORK.BK": "บริการ", "WORLD.BK": "ธุรกิจการเงิน", "WP.BK": "ทรัพยากร", "XO.BK": "เกษตรและอุตสาหกรรมอาหาร", "XPG.BK": "ธุรกิจการเงิน", "YONG.BK": "อสังหาริมทรัพย์และก่อสร้าง", "ZEN.BK": "บริการ", "ZIGA.BK": "สินค้าอุตสาหกรรม",
    }
    
    # เผื่อกรณีพิมพ์หุ้นมาแบบไม่มี .BK ให้ลองเช็คแบบเติม .BK ดูด้วย
    if ticker not in sector_dict and not ticker.endswith(".BK"):
        if f"{ticker}.BK" in sector_dict:
            return sector_dict[f"{ticker}.BK"]
            
    return sector_dict.get(ticker, "General / Unspecified")
    
@st.cache_data(ttl=3600)
def fetch_set_index_history():
    """
    🆕 ดึงข้อมูลราคาย้อนหลังของดัชนี SET Index (2 ปี) แบบทนทาน — แยกออกมาจากฟังก์ชันสแกนหุ้น
    เพื่อให้ใช้ซ้ำได้ทั้งตอนคำนวณ RS_Line และตอนเทียบผลงานพอร์ตกับตลาด (ไม่ต้องเขียนตรรกะเดิมซ้ำ)
    ลองหลายวิธีเรียงกัน (วิธีไหนได้ข้อมูลพอก่อน ใช้วิธีนั้นเลย) เพราะ Yahoo Finance บางครั้งให้
    ข้อมูลย้อนหลังของดัชนี SET ไม่ครบผ่านบางฟังก์ชัน/บางสัญลักษณ์ (ดูรายละเอียดในคอมเมนต์ย่อยแต่ละ
    วิธี) คืนค่าเป็น (pd.Series ราคาปิดรายวัน เรียงตามวันที่ ไม่มีเขตเวลาติด, ชื่อวิธีที่ใช้ได้ผล หรือ
    None ถ้าล้มเหลวทั้งหมด)
    """
    def _try_fetch(symbol):
        # 🔧 แก้บั๊ก: เดิมกลืน error message ทั้งหมดไปเงียบๆ (except Exception: pass) พอทุกวิธี
        # ล้มเหลวติดต่อกันหลายวัน ไม่มีทางรู้เลยว่าสาเหตุจริงคืออะไร (Yahoo บล็อก IP ของ GitHub
        # Actions? เปลี่ยนสัญลักษณ์? โดน rate limit?) ตอนนี้พิมพ์ข้อความ error จริงออกมาให้เห็นใน
        # log ทุกครั้งที่ลองแล้วไม่สำเร็จ จะได้วินิจฉัยสาเหตุที่แท้จริงได้จาก log ของ GitHub Actions
        try:
            s = yf.Ticker(symbol).history(period="2y")['Close']
            if isinstance(s, pd.Series) and len(s) >= 30:
                return s, f"yf.Ticker('{symbol}').history()"
            print(f"⚠️ yf.Ticker('{symbol}').history() ได้ข้อมูลไม่พอ ({len(s) if isinstance(s, pd.Series) else 0} แถว)")
        except Exception as e:
            print(f"⚠️ yf.Ticker('{symbol}').history() ล้มเหลว: {type(e).__name__}: {e}")
        try:
            s = yf.download(symbol, period="2y")['Close'].squeeze()
            if isinstance(s, pd.Series) and len(s) >= 30:
                return s, f"yf.download('{symbol}')"
            print(f"⚠️ yf.download('{symbol}') ได้ข้อมูลไม่พอ ({len(s) if isinstance(s, pd.Series) else 0} แถว)")
        except Exception as e:
            print(f"⚠️ yf.download('{symbol}') ล้มเหลว: {type(e).__name__}: {e}")
        return pd.Series(dtype=float), None

    set_market = pd.Series(dtype=float)
    set_market_source = None
    # เพิ่มสัญลักษณ์สำรองอีก 2 แบบ (^SET กับ SET เฉยๆ ไม่มี .BK) เผื่อ Yahoo Finance เปลี่ยน
    # รูปแบบสัญลักษณ์ที่รองรับสำหรับดัชนี SET Index ไปแล้ว
    for _sym in ["^SET.BK", "SET.BK", "^SET", "SET"]:
        set_market, set_market_source = _try_fetch(_sym)
        if set_market_source is not None:
            break

    # ตัดเขตเวลาออกเสมอ (ถ้ามี) ให้ใช้งานร่วมกับข้อมูลอื่นที่ไม่มีเขตเวลาได้อย่างปลอดภัย
    if isinstance(set_market, pd.Series) and getattr(set_market.index, 'tz', None) is not None:
        set_market.index = set_market.index.tz_localize(None)

    if isinstance(set_market, pd.Series) and len(set_market) >= 30:
        _save_set_index_cache(set_market)  # ดึงสดสำเร็จ บันทึกสำรองไว้ทันที เผื่อวันหลังดึงสดไม่ได้
        return set_market, set_market_source

    # 🆕 ดึงสดจาก Yahoo Finance ไม่สำเร็จเลยสักวิธี (Yahoo บางวันมีข้อมูลดัชนี SET Index ให้ไม่ครบ
    # เป็นข้อจำกัดฝั่ง Yahoo เอง ควบคุมไม่ได้โดยตรง) ลองดึงจาก "ข้อมูลสำรอง" ที่เคยบันทึกไว้ล่าสุด
    # แทน (อาจเก่าไปหนึ่งวันสองวัน แต่ยังดีกว่าไม่มีข้อมูลเลย หรือตั้ง RS_Line เป็น 0 ทั้งหมด)
    print("⚠️ ดึงข้อมูล SET Index สดจาก Yahoo Finance ไม่สำเร็จทุกวิธี กำลังลองใช้ข้อมูลสำรองที่เคยบันทึกไว้ล่าสุดแทน...")
    cached_market = _load_cached_set_index()
    if len(cached_market) >= 30:
        print(f"✅ ใช้ข้อมูลสำรอง SET Index ที่เคยบันทึกไว้ล่าสุดแทน ({len(cached_market)} แถว, ข้อมูลล่าสุดถึงวันที่ {cached_market.index[-1].strftime('%Y-%m-%d')})")
        return cached_market, "ข้อมูลสำรองที่เคยบันทึกไว้ล่าสุด (ดึงสดไม่สำเร็จวันนี้)"

    return pd.Series(dtype=float), None


def _save_set_index_cache(set_market, spreadsheet_name="MyStockData"):
    """
    🆕 บันทึกข้อมูลดัชนี SET Index ที่เพิ่งดึงสดสำเร็จ ไว้เป็นข้อมูลสำรองในชีต 'SET_Index_Cache'
    (ต้องมีชีตนี้อยู่ใน Google Sheet ของ MyStockData ก่อน — คอลัมน์ Date, Close) เผื่อวันไหน
    Yahoo Finance มีปัญหา ดึงสดไม่สำเร็จ จะได้มีข้อมูลสำรองมาใช้แทนได้ (ไม่ต้องตั้ง RS_Line เป็น 0)
    """
    try:
        client = get_gsheet_client()
        sheet = get_cached_worksheet(client, spreadsheet_name, 'SET_Index_Cache')
        df_to_save = set_market.reset_index()
        df_to_save.columns = ['Date', 'Close']
        df_to_save['Date'] = df_to_save['Date'].astype(str)
        data_to_write = [df_to_save.columns.tolist()] + df_to_save.values.tolist()
        sheet.update(range_name='A1', values=data_to_write)
    except Exception as e:
        print(f"⚠️ บันทึกข้อมูลสำรอง SET Index ไม่สำเร็จ (ไม่กระทบการทำงานหลัก): {e}")


def _load_cached_set_index(spreadsheet_name="MyStockData"):
    """โหลดข้อมูลดัชนี SET Index ที่เคยบันทึกสำรองไว้ล่าสุด (ใช้ตอนดึงสดจาก Yahoo Finance ไม่สำเร็จ)"""
    try:
        client = get_gsheet_client()
        sheet = get_cached_worksheet(client, spreadsheet_name, 'SET_Index_Cache')
        records = sheet.get_all_records()
        if not records:
            return pd.Series(dtype=float)
        df = pd.DataFrame(records)
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
        df = df.dropna(subset=['Date', 'Close']).set_index('Date').sort_index()
        return df['Close']
    except Exception as e:
        print(f"⚠️ โหลดข้อมูลสำรอง SET Index ไม่สำเร็จ: {e}")
        return pd.Series(dtype=float)


@st.cache_data(ttl=86400) # เก็บข้อมูลไว้วันละครั้งเพื่อความเร็ว
def load_and_calculate_stock_data_optimized():
    status_text = st.empty()
    # 🔧 แก้บั๊ก: เดิมข้อความบอกว่า "SET100" ตายตัว แต่จริงๆ ดึงข้อมูลหุ้นตามจำนวนในระบบ
    # ปัจจุบัน (494 ตัว ไม่ใช่ 100 ตัวแล้ว) เปลี่ยนให้แสดงจำนวนจริงแบบไดนามิกแทน
    status_text.text(f"กำลังดาวน์โหลดข้อมูลหุ้น {len(SET100_TICKERS)} ตัว... (กรุณารอ อาจใช้เวลาสักครู่)")
    
    # 1. เตรียม Tickers
    # 🔧 แก้บั๊ก: เดิมเติม ".BK" ต่อท้ายซ้ำ ทั้งที่ชื่อหุ้นใน constants.py มี ".BK" อยู่แล้วทุกตัว
    # (เช่น "A5.BK") ทำให้กลายเป็น "A5.BK.BK" ซึ่งไม่มีอยู่จริงบน Yahoo Finance ดึงข้อมูลไม่สำเร็จ
    # เลยสักตัวเดียว (Yahoo แจ้ง "possibly delisted" ทุกตัว) ตอนนี้ใช้ชื่อจาก SET100_TICKERS ตรงๆ
    # โดยไม่เติมอะไรเพิ่ม
    tickers_full = SET100_TICKERS
    
    # 2. ดึงข้อมูลทั้งหมดในคราวเดียว (Batch Download)
    # ใช้ threads=True ช่วยให้ดึงข้อมูลเร็วขึ้นหลายเท่า
    data = yf.download(tickers_full, period="2y", group_by='ticker', threads=True)
    
    # 🔧 ปรับปรุง: ย้ายตรรกะดึงข้อมูลดัชนี SET Index ไปเป็นฟังก์ชันกลาง fetch_set_index_history()
    # ด้านบน (ใช้ซ้ำกับฟีเจอร์เทียบผลงานพอร์ตกับตลาดได้ด้วย ไม่ต้องเขียนตรรกะเดิมซ้ำอีก)
    set_market, set_market_source = fetch_set_index_history()
    set_market_usable = isinstance(set_market, pd.Series) and len(set_market) >= 30
    if set_market_usable:
        print(f"✅ ดึงข้อมูลดัชนี SET Index สำเร็จผ่าน {set_market_source} ({len(set_market)} แถว) ใช้คำนวณ RS_Line ได้ตามปกติ")
    else:
        print("⚠️ ข้อมูลดัชนี SET Index ไม่พอสำหรับคำนวณ RS_Line (ลองครบทุกวิธีแล้ว) จะข้ามการคำนวณ RS_Line ไปก่อน แต่ยังคงบันทึกข้อมูลอื่นๆ ตามปกติ")
    
    stock_list = []
    failed_tickers = []  # 🆕 เก็บรายชื่อหุ้นที่ดึงข้อมูลไม่สำเร็จ เพื่อรายงานให้ผู้ใช้ทราบ
    total = len(SET100_TICKERS)
    
    for i, ticker in enumerate(SET100_TICKERS):
        try:
            # ดึงเฉพาะข้อมูลของหุ้นตัวนั้นๆ จาก DataFrame ที่โหลดมา
            # 🔧 แก้บั๊ก: เดิมพยายามค้นหาด้วยชื่อที่ตัด ".BK" ออก (เช่น "A5") แต่ข้อมูลที่ดาวน์โหลด
            # มาจริงถูกเก็บด้วยชื่อเต็ม "A5.BK" (ตรงกับที่ใช้ตอนดาวน์โหลด) ค้นหาไม่เจอเลยสักตัว
            # ตอนนี้ใช้ ticker ตรงๆ (มี .BK อยู่แล้ว) ให้ตรงกับชื่อที่ดาวน์โหลดมาจริง
            # 🔧 แก้บั๊กเพิ่ม: เพิ่ม .copy() ตรงนี้ เพื่อตัดขาดจาก DataFrame ใหญ่ที่โหลดมาทั้งก้อน
            # (data) อย่างชัดเจน ป้องกัน pandas เตือน SettingWithCopyWarning ตอนแก้ไขคอลัมน์ข้างล่าง
            df = data[ticker].copy()
            if df.empty or len(df) < 200:
                failed_tickers.append(ticker)
                continue
            
            # คำนวณ RSI
            df['RSI'] = calculate_rsi(df['Close'], period=14)

            # 🆕 ดึงข้อมูล P/E Ratio และเงินปันผล (%) จริงจาก Yahoo (ต้องดึงทีละหุ้น ช้ากว่าราคา
            # ที่ดึงเป็นชุดใหญ่ทีเดียวด้านบน) ครอบด้วย try/except แยกต่างหาก เพื่อไม่ให้ถ้าจุดนี้
            # พลาด ไปทำให้ข้อมูลราคา/RSI/Trend Template ที่คำนวณสำเร็จแล้วของหุ้นตัวนี้เสียไปด้วย
            try:
                stock_info = yf.Ticker(ticker).info
                pe_ratio_raw = stock_info.get('trailingPE')
                dividend_yield_raw = stock_info.get('dividendYield')
                pe_ratio_val = round(float(pe_ratio_raw), 2) if pe_ratio_raw is not None else 0.0
                # 🔧 แก้บั๊ก: เดิมคูณ 100 เพิ่ม โดยเข้าใจว่า yfinance คืนค่าเป็นเลขทศนิยม (เช่น 0.0278 = 2.78%)
                # แต่ yfinance เวอร์ชันที่ใช้งานจริงคืนค่าเป็น "เปอร์เซ็นต์" มาให้ตรงๆ อยู่แล้ว (เช่น 2.78
                # หมายถึง 2.78% เลย) พอเอาไปคูณ 100 ซ้ำ เลยกลายเป็นเลขหลักร้อยที่ผิดเพี้ยน (เช่น 278)
                # ตอนนี้ใช้ค่าที่ได้มาตรงๆ โดยไม่คูณซ้ำ
                dividend_pct_val = round(float(dividend_yield_raw), 2) if dividend_yield_raw is not None else 0.0

                # 🆕 ดึงวันขึ้น XD (Ex-Dividend Date) ล่าสุดที่ Yahoo มีบันทึกไว้ ช่วยให้รู้ว่า
                # % ปันผลที่คำนวณไว้ (เป็นค่าย้อนหลัง 12 เดือน ไม่ได้บอกว่าขึ้น XD ไปหรือยัง) มาจาก
                # รอบจ่ายปันผลล่าสุดเมื่อไหร่ ค่านี้เป็น Unix timestamp ต้องแปลงเป็นวันที่อ่านง่ายก่อน
                # หมายเหตุ: ข้อมูลนี้ของหุ้นไทยบางตัวอาจไม่มี/ไม่ครบใน Yahoo Finance (ข้อจำกัดของ
                # แหล่งข้อมูล ไม่ใช่บั๊กของโค้ด) ถ้าไม่มีจะปล่อยว่างไว้แทน
                ex_div_raw = stock_info.get('exDividendDate')
                if ex_div_raw:
                    try:
                        ex_dividend_date_str = datetime.fromtimestamp(ex_div_raw).strftime('%Y-%m-%d')
                    except Exception:
                        ex_dividend_date_str = ""
                else:
                    ex_dividend_date_str = ""
            except Exception:
                pe_ratio_val = 0.0
                dividend_pct_val = 0.0
                ex_dividend_date_str = ""

            # 🆕 แจ้งความคืบหน้าเป็นระยะ (ทุก 50 ตัว) เพราะขั้นตอนนี้ดึงข้อมูลทีละหุ้น ใช้เวลานาน
            # กว่าจุดอื่น ถ้าไม่แจ้งความคืบหน้า จะดูเหมือนค้างไม่ทำงาน โดยเฉพาะตอนรันแบบ headless
            if (i + 1) % 50 == 0:
                print(f"⏳ ดึงข้อมูล P/E และปันผลไปแล้ว {i + 1}/{total} ตัว...")
            
            # คำนวณ RS_Line (ข้ามไปถ้าข้อมูลดัชนี SET ไม่พอ ตั้งเป็น 0 แทน)
            # 🆕 เพิ่มการคำนวณ 3 ค่าที่ตัวกรอง "กลุ่ม RS Line" ในหน้าเว็บต้องใช้ (เดิมมีแค่ค่า
            # RS_Line ล่าสุดวันเดียว ไม่พอสำหรับดูแนวโน้มย้อนหลัง) โดยเก็บ RS_Line ทั้งช่วงเวลา
            # (ไม่ใช่แค่ค่าล่าสุด) มาคำนวณต่อ:
            #   - Is_RS_Above_0: RS_Line ตอนนี้อยู่เหนือเส้น 0 ไหม
            #   - RS_Line_50D_Max: ค่าสูงสุดของ RS_Line ใน 50 วันที่ผ่านมา (ไม่รวมวันนี้) ใช้เช็คว่า
            #     วันนี้ทำจุดสูงสุดใหม่หรือยัง
            #   - ตัดเส้น0ขึ้นมาแล้ว(วัน) / อยู่ใต้เส้น0มาแล้ว(วัน): นับจำนวนวันติดต่อกันล่าสุดที่
            #     RS_Line อยู่ฝั่งเดียวกับตอนนี้ (บวกต่อเนื่องกี่วัน หรือติดลบต่อเนื่องกี่วัน)
            if set_market_usable:
                combined = df[['Close']].join(set_market.rename('Market_Close'), how='inner')
                base_stock = combined['Close'].iloc[0]
                base_market = combined['Market_Close'].iloc[0]
                
                stock_perf = ((combined['Close'] - base_stock) / base_stock) * 100
                market_perf = ((combined['Market_Close'] - base_market) / base_market) * 100
                rs_line_series = stock_perf - market_perf
                current_rs_val = rs_line_series.iloc[-1]

                is_rs_above_0 = bool(current_rs_val > 0)
                rs_line_50d_max = rs_line_series.iloc[:-1].tail(50).max() if len(rs_line_series) > 1 else current_rs_val

                # นับจำนวนวันติดต่อกันล่าสุดที่ RS_Line อยู่ฝั่งเดียวกับปัจจุบัน (นับย้อนจากวันล่าสุด)
                sign_series = (rs_line_series > 0).tolist()
                current_sign = sign_series[-1]
                streak_days = 0
                for val in reversed(sign_series):
                    if val == current_sign:
                        streak_days += 1
                    else:
                        break
                days_above_0 = streak_days if current_sign else 0
                days_below_0 = streak_days if not current_sign else 0
            else:
                current_rs_val = 0.0
                is_rs_above_0 = False
                rs_line_50d_max = 0.0
                days_above_0 = 0
                days_below_0 = 0
            
            # คำนวณค่าทางเทคนิคอื่นๆ (ใช้ค่าจาก df ที่มีอยู่แล้ว)
            latest_price = df['Close'].iloc[-1]
            high_3m = df['High'].iloc[:-1].tail(60).max()
            high_6m = df['High'].iloc[:-1].tail(120).max()
            high_52w = df['High'].iloc[:-1].tail(250).max()
            low_52w = df['Low'].iloc[:-1].tail(250).min()

            # 🆕 1. Trend Template (สไตล์ Minervini): ราคาอยู่เหนือเส้นค่าเฉลี่ย + เส้นค่าเฉลี่ยเรียงตัวขาขึ้น
            ma50 = df['Close'].rolling(window=50).mean().iloc[-1]
            ma150 = df['Close'].rolling(window=150).mean().iloc[-1]
            ma200 = df['Close'].rolling(window=200).mean().iloc[-1]
            price_above_all_ma = bool(latest_price > ma50 and latest_price > ma150 and latest_price > ma200)
            ma_aligned_uptrend = bool(ma50 > ma150 > ma200)
            trend_template_pass = bool(price_above_all_ma and ma_aligned_uptrend)

            # 🆕 2. ระยะห่างจากจุดสูงสุด/ต่ำสุด 52 สัปดาห์ (เป็น % เทียบกับราคาปัจจุบัน)
            pct_from_52w_high = ((latest_price - high_52w) / high_52w) * 100  # ค่าติดลบ = ต่ำกว่าจุดสูงสุดอยู่เท่าไหร่
            pct_above_52w_low = ((latest_price - low_52w) / low_52w) * 100    # ค่าบวก = สูงกว่าจุดต่ำสุดอยู่เท่าไหร่
            near_52w_high = bool(pct_from_52w_high >= -15)  # ห่างจากจุดสูงสุดไม่เกิน 15%
            recovered_from_low = bool(pct_above_52w_low >= 30)  # ฟื้นตัวจากจุดต่ำอย่างน้อย 30%

            # 🆕 5. เพิ่งทำจุดสูงสุดใหม่ 52 สัปดาห์ "วันนี้พอดี" (ต่างจาก Is_52W_High ที่แค่บอกว่า
            # ราคาใกล้จุดสูงสุด ไม่เกิน 5% เท่านั้น) ใช้สำหรับระบบแจ้งเตือน Telegram โดยเฉพาะ — เทียบ
            # ราคาล่าสุดกับจุดสูงสุดของ 250 วันก่อนหน้า (ไม่รวมวันนี้ เพราะ high_52w คำนวณแบบตัดวันนี้
            # ออกไปแล้ว) ถ้าราคาวันนี้สูงกว่าจุดสูงสุดเดิมจริงๆ แปลว่าทำจุดสูงสุดใหม่วันนี้พอดี
            is_new_52w_high_today = bool(latest_price > high_52w)

            # 🆕 3. ปริมาณการซื้อขายพุ่งผิดปกติ (Volume Spike): เทียบ Volume ล่าสุดกับค่าเฉลี่ย 50 วัน
            avg_vol_50 = df['Volume'].iloc[:-1].tail(50).mean()
            latest_vol = df['Volume'].iloc[-1]
            volume_spike_ratio = (latest_vol / avg_vol_50) if avg_vol_50 > 0 else 0.0
            is_volume_spike = bool(volume_spike_ratio >= 2.0)  # ปริมาณมากกว่าค่าเฉลี่ย 2 เท่าขึ้นไป

            # 🆕 4. หุ้นแกว่งตัวแคบก่อนวิ่ง (Volatility Contraction): ช่วงแกว่งราคา 10 วันล่าสุด แคบกว่า 50 วันก่อนหน้า
            daily_range_pct = (df['High'] - df['Low']) / df['Close'] * 100
            recent_volatility = daily_range_pct.tail(10).mean()
            baseline_volatility = daily_range_pct.tail(50).mean()
            is_volatility_contracting = bool(baseline_volatility > 0 and recent_volatility <= (baseline_volatility * 0.7))

            # 🆕 6. Golden Cross "วันนี้พอดี" — MA50 เพิ่งตัดขึ้นเหนือ MA150 (เมื่อวานยังไม่ตัด วันนี้
            # ตัดแล้ว) เทียบจากข้อมูลราคาย้อนหลังชุดเดียวกันที่มีอยู่แล้ว ใช้ .iloc[-2] แทน .iloc[-1]
            # เพื่อดูค่า MA ของ "เมื่อวาน" โดยไม่ต้องพึ่งข้อมูลสแกนเก่าจากภายนอกเลย
            ma50_series = df['Close'].rolling(window=50).mean()
            ma150_series = df['Close'].rolling(window=150).mean()
            ma50_yesterday = ma50_series.iloc[-2] if len(ma50_series) >= 2 else None
            ma150_yesterday = ma150_series.iloc[-2] if len(ma150_series) >= 2 else None
            is_golden_cross_today = bool(
                pd.notna(ma50_yesterday) and pd.notna(ma150_yesterday) and pd.notna(ma50) and pd.notna(ma150)
                and ma50_yesterday <= ma150_yesterday and ma50 > ma150
            )

            # 🆕 7. RSI ดีดกลับจากโซน Oversold "วันนี้พอดี" — เมื่อวาน RSI ยังต่ำกว่า 30 (ขายมากเกินไป)
            # วันนี้ดีดกลับขึ้นมาเหนือ 30 แล้ว เป็นสไตล์ Mean Reversion ต่างจาก Momentum ทั้งหมดที่มีอยู่
            rsi_yesterday = df['RSI'].iloc[-2] if len(df['RSI']) >= 2 else None
            rsi_today_val = df['RSI'].iloc[-1]
            is_rsi_oversold_bounce_today = bool(
                pd.notna(rsi_yesterday) and rsi_yesterday < 30 and pd.notna(rsi_today_val) and rsi_today_val >= 30
            )

            # 🆕 8. VCP Breakout "วันนี้พอดี" (สไตล์ Mark Minervini) — เมื่อวานยังอยู่ในสถานะแกว่งตัว
            # แคบ (Volatility Contraction) แล้ววันนี้ทะลุกรอบขึ้นมาพร้อม Volume พุ่งผิดปกติ และราคาปิด
            # สูงกว่าเมื่อวาน คำนวณสถานะ "แกว่งแคบของเมื่อวาน" โดยตัดวันนี้ออกจากข้อมูลก่อน (.iloc[:-1])
            # แล้วเลื่อนหน้าต่างไปอีก 1 วัน เหมือนย้อนเวลากลับไปมองเมื่อวานจริงๆ
            daily_range_pct_excl_today = daily_range_pct.iloc[:-1]
            recent_vol_yesterday = daily_range_pct_excl_today.tail(10).mean()
            baseline_vol_yesterday = daily_range_pct_excl_today.tail(50).mean()
            was_volatility_contracting_yesterday = bool(
                baseline_vol_yesterday > 0 and recent_vol_yesterday <= (baseline_vol_yesterday * 0.7)
            )
            price_up_today = bool(len(df['Close']) >= 2 and latest_price > df['Close'].iloc[-2])
            is_vcp_breakout_today = bool(
                was_volatility_contracting_yesterday and is_volume_spike and price_up_today
            )

            stock_list.append({
                'Ticker': ticker.replace('.BK', ''),
                'ราคาล่าสุด': round(float(latest_price), 2),
                'RSI_14': round(float(df['RSI'].iloc[-1]), 2),
                'RS_Line': round(float(current_rs_val), 2),
                'PE_Ratio': pe_ratio_val,
                'ปันผล_%': dividend_pct_val,
                'Ex_Dividend_Date': ex_dividend_date_str,
                # 🆕 คอลัมน์สำหรับตัวกรอง "กลุ่ม RS Line" ทั้ง 3 แบบในหน้าเว็บ
                'Is_RS_Above_0': is_rs_above_0,
                'RS_Line_50D_Max': round(float(rs_line_50d_max), 2),
                'ตัดเส้น0ขึ้นมาแล้ว(วัน)': days_above_0,
                'อยู่ใต้เส้น0มาแล้ว(วัน)': days_below_0,
                'Is_3M_High': latest_price >= (high_3m * 0.95),
                'Is_6M_High': latest_price >= (high_6m * 0.95),
                'Is_52W_High': latest_price >= (high_52w * 0.95),
                # 🆕 คอลัมน์ใหม่สำหรับตัวกรองเพิ่มเติม
                'MA50': round(float(ma50), 2) if pd.notna(ma50) else None,
                'MA150': round(float(ma150), 2) if pd.notna(ma150) else None,
                'MA200': round(float(ma200), 2) if pd.notna(ma200) else None,
                'Trend_Template_Pass': trend_template_pass,
                'Pct_From_52W_High': round(float(pct_from_52w_high), 2),
                'Pct_Above_52W_Low': round(float(pct_above_52w_low), 2),
                'Near_52W_High': near_52w_high,
                'Is_New_52W_High_Today': is_new_52w_high_today,
                'Recovered_From_Low': recovered_from_low,
                'Volume_Spike_Ratio': round(float(volume_spike_ratio), 2),
                'Is_Volume_Spike': is_volume_spike,
                'Is_Volatility_Contracting': is_volatility_contracting,
                # 🆕 3 สัญญาณใหม่สำหรับ Backtest + ตัวกรองในแท็บวิเคราะห์กราฟเทคนิคัล
                'Is_Golden_Cross_Today': is_golden_cross_today,
                'Is_RSI_Oversold_Bounce_Today': is_rsi_oversold_bounce_today,
                'Is_VCP_Breakout_Today': is_vcp_breakout_today,
            })
            
        except Exception as e:
            failed_tickers.append(ticker)
            # 🔧 แก้บั๊ก: เดิม print แค่ประเภท+ข้อความ error สั้นๆ ยังไม่พอจะรู้ว่า "บรรทัดไหน"
            # ในโค้ดที่พังจริง ตอนนี้ print traceback แบบเต็มของ 2 ตัวแรกที่พลาด จะได้เห็น
            # เลขบรรทัดที่แท้จริงในโค้ดที่ทำให้เกิด error
            if len(failed_tickers) <= 2:
                print(f"⚠️ {ticker} พลาดเพราะ (traceback เต็ม):")
                traceback.print_exc()
            continue
            
    status_text.empty()

    # 🆕 รายงานผลลัพธ์ให้ผู้ใช้ทราบชัดเจน แทนที่จะข้ามหุ้นที่พลาดไปเงียบๆ แบบเดิม
    # (สำคัญเพราะการดึงข้อมูล 494 ตัวพร้อมกัน มีโอกาสที่ Yahoo Finance จะปฏิเสธคำขอบางตัว
    # ระหว่างทาง ถ้าไม่รายงาน ผู้ใช้จะไม่รู้เลยว่าทำไมจำนวนหุ้นที่ได้ถึงน้อยกว่า 494)
    # 🔧 แก้บั๊กเพิ่ม: st.warning/st.success ใช้ไม่ได้เลยตอนรันแบบ headless (เช่น daily_scan.py
    # ผ่าน GitHub Actions) เพิ่ม print() คู่กันไปด้วย จะได้เห็นสรุปผลใน log เสมอไม่ว่าจะรันแบบไหน
    success_count = len(stock_list)
    if failed_tickers:
        summary_msg = (
            f"⚠️ ดึงข้อมูลสำเร็จ {success_count} จาก {total} ตัว "
            f"({len(failed_tickers)} ตัวดึงไม่สำเร็จ — อาจเป็นเพราะ Yahoo Finance ปฏิเสธคำขอชั่วคราว "
            f"หรือหุ้นตัวนั้นมีข้อมูลย้อนหลังไม่ครบ 200 วัน) "
            f"ลองกดอัปเดตอีกครั้งภายหลังถ้าต้องการให้ครบทุกตัว"
        )
        print(summary_msg)
        st.warning(summary_msg)
        with st.expander(f"ดูรายชื่อ {len(failed_tickers)} ตัวที่ดึงไม่สำเร็จ"):
            st.write(", ".join(failed_tickers))
    else:
        print(f"✅ ดึงข้อมูลสำเร็จครบทั้ง {total} ตัว")
        st.success(f"✅ ดึงข้อมูลสำเร็จครบทั้ง {total} ตัว")
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
# 🆕 ระบบส่งออกรายงาน Net Worth เป็น PDF (ภาษาอังกฤษ เพื่อไม่ต้องฝังฟอนต์ไทยเพิ่มเติม —
# ฟอนต์มาตรฐานของ reportlab ไม่รองรับภาษาไทย ถ้าจะทำเป็นไทยต้องฝังไฟล์ฟอนต์เองก่อน)
# =============================================================
def generate_net_worth_pdf_report(app_title, net_worth_excl_re, net_worth_total, asset_breakdown, trend_df=None):
    """
    สร้างรายงานสรุปสินทรัพย์เป็นไฟล์ PDF คืนค่าเป็น bytes (ใช้กับ st.download_button ได้ตรงๆ)
    asset_breakdown: list of (ชื่อสินทรัพย์: str, มูลค่า: float) เรียงตามลำดับที่จะแสดงในตาราง
    trend_df: (ไม่บังคับ) DataFrame จาก get_net_worth_trend_data() ที่มีคอลัมน์ 'Total_Excl_RE'
    ถ้าใส่มา จะเพิ่มกราฟเส้นแนวโน้ม Net Worth รวม (ไม่รวมอสังหาฯ) ต่อท้ายกราฟวงกลมให้ด้วย
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    from reportlab.lib.units import cm

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm)
    styles = getSampleStyleSheet()
    story = []

    # --- หัวรายงาน ---
    story.append(Paragraph(f"{app_title} - Net Worth Report", styles['Title']))
    story.append(Paragraph(f"Generated on {datetime.today().strftime('%d %B %Y')}", styles['Normal']))
    story.append(Spacer(1, 20))

    # --- สรุป Net Worth ---
    story.append(Paragraph("Net Worth Summary", styles['Heading2']))
    summary_table = Table([
        ["Net Worth (excl. Real Estate)", f"{net_worth_excl_re:,.2f} THB"],
        ["Net Worth (Total, incl. Real Estate)", f"{net_worth_total:,.2f} THB"],
    ], colWidths=[320, 180])
    summary_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F1EEE8')),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 20))

    # --- ตารางสัดส่วนสินทรัพย์ ---
    story.append(Paragraph("Asset Allocation", styles['Heading2']))
    _total_for_pct = sum(v for _, v in asset_breakdown) or 1
    table_data = [["Asset Category", "Value (THB)", "% of Total"]]
    for name, value in asset_breakdown:
        pct = (value / _total_for_pct) * 100
        table_data.append([name, f"{value:,.2f}", f"{pct:.1f}%"])

    asset_table = Table(table_data, colWidths=[220, 150, 100])
    asset_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#7C9885')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(asset_table)
    story.append(Spacer(1, 20))

    # --- กราฟวงกลมสัดส่วนสินทรัพย์ (วาดด้วย matplotlib แล้วฝังเป็นรูปภาพ) ---
    # 🔧 แก้บั๊ก: เดิมใส่ป้ายชื่อ (labels) ติดบนกราฟโดยตรงทุกชิ้น ทำให้สัดส่วนเล็กๆ หลายชิ้นที่อยู่
    # ใกล้กัน (เช่น สหกรณ์, ประกันสังคม, ธนาคาร) ป้ายชื่อทับกันจนอ่านไม่ออกเลย ตอนนี้เปลี่ยนมาใช้
    # "คำอธิบายด้านข้าง" (Legend) แทน ซึ่งเรียงเป็นรายการแนวตั้งเสมอ ไม่มีทางทับกันไม่ว่าจะมีกี่ชิ้น
    # และซ่อน % บนชิ้นที่เล็กกว่า 3% ไปเลย (มีตัวเลขแม่นยำอยู่ในตารางด้านบนแล้วอยู่แล้ว)
    try:
        _names = [n for n, v in asset_breakdown if v > 0]
        _values = [v for n, v in asset_breakdown if v > 0]
        if _values:
            def _autopct_format(pct):
                return f'{pct:.1f}%' if pct >= 3 else ''

            fig, ax = plt.subplots(figsize=(8, 5))
            wedges, _texts, _autotexts = ax.pie(
                _values, autopct=_autopct_format, startangle=90, pctdistance=0.75,
                textprops={'fontsize': 9, 'color': 'white', 'weight': 'bold'}
            )
            ax.axis('equal')
            ax.legend(
                wedges, _names, title="Asset Category",
                loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize=9
            )
            img_buffer = io.BytesIO()
            plt.savefig(img_buffer, format='png', dpi=150, bbox_inches='tight')
            plt.close(fig)
            img_buffer.seek(0)
            story.append(Paragraph("Asset Allocation Chart", styles['Heading2']))
            story.append(Image(img_buffer, width=480, height=300))
    except Exception:
        pass  # ถ้าวาดกราฟพลาด ยังคงส่งรายงานที่เหลือ (หัวข้อ+ตาราง) ออกไปได้ตามปกติ

    # 🆕 กราฟเส้นแนวโน้ม Net Worth รวม (ไม่รวมอสังหาริมทรัพย์) — แสดงก็ต่อเมื่อมีข้อมูลส่งเข้ามา
    # (trend_df ไม่ใช่ None และมีข้อมูลจริง) ถ้าไม่ส่งมาเลย (เช่น เรียกจากปุ่มดาวน์โหลดเดิมในหน้าเว็บ
    # ที่ยังไม่ได้แก้ให้ส่งมา) จะข้ามส่วนนี้ไปเงียบๆ รายงานที่เหลือยังคงออกมาได้ตามปกติ
    if trend_df is not None and not trend_df.empty and 'Total_Excl_RE' in trend_df.columns:
        try:
            fig2, ax2 = plt.subplots(figsize=(8, 4))
            ax2.plot(trend_df.index, trend_df['Total_Excl_RE'], color='#7C9885', linewidth=2.5, marker='o', markersize=4)
            ax2.set_ylabel('Net Worth excl. Real Estate (THB)')
            ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x:,.0f}'))
            fig2.autofmt_xdate()
            img_buffer2 = io.BytesIO()
            plt.savefig(img_buffer2, format='png', dpi=150, bbox_inches='tight')
            plt.close(fig2)
            img_buffer2.seek(0)
            story.append(Paragraph("Net Worth Trend (excl. Real Estate)", styles['Heading2']))
            story.append(Image(img_buffer2, width=480, height=240))
        except Exception:
            pass  # ถ้าวาดกราฟแนวโน้มพลาด ยังคงส่งรายงานที่เหลือออกไปได้ตามปกติ

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


# =============================================================
# 🆕 ระบบแจ้งเตือนอัตโนมัติผ่าน Telegram (ต่อท้าย Daily Scan)
# ใช้ Telegram Bot API ตรงๆ ผ่าน requests ไม่ต้องติดตั้ง library เพิ่ม (LINE Notify ปิดให้บริการ
# ไปแล้วตั้งแต่ 31 มี.ค. 2025 จึงเลือกใช้ Telegram แทน — ตั้งค่าง่ายกว่าและยังใช้งานได้จริง)
# =============================================================
def send_telegram_message(bot_token, chat_id, message):
    """
    ส่งข้อความแจ้งเตือนผ่าน Telegram Bot คืนค่าเป็น (สำเร็จหรือไม่: bool, ข้อความ: str)
    ต้องมี bot_token (จาก @BotFather) และ chat_id (ไอดีแชทที่จะส่งไปหา) ก่อน
    """
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    try:
        resp = requests.post(url, data=payload, timeout=10)
        if resp.status_code == 200:
            return True, "ส่งข้อความ Telegram สำเร็จ"
        return False, f"ส่งไม่สำเร็จ (HTTP {resp.status_code}): {resp.text}"
    except Exception as e:
        return False, f"ส่งไม่สำเร็จ: {e}"


# =============================================================
# 🆕 ระบบ Backtest กลยุทธ์การสแกน — บันทึกหุ้นที่ผ่านเกณฑ์เด่นแต่ละวัน (Trend Template ผ่านใหม่,
# RS Line ตัดเส้น 0 ขึ้น, ทำจุดสูงสุดใหม่ 52 สัปดาห์) แล้วย้อนกลับมาเช็คว่าราคาไปทางไหนต่อจริงๆ ใน
# 30/60/90 วันถัดมา เก็บเฉพาะหุ้นที่มีสัญญาณเด่นเท่านั้น (ไม่ใช่ทั้ง 472 ตัว) ทั้งเพราะประหยัดพื้นที่
# และเพราะตรงกับขอบเขตคำถามที่ต้องการตอบพอดี (สนใจแค่ "หลังสัญญาณเกิด ราคาไปทางไหน" ไม่ใช่ราคา
# ของหุ้นที่ไม่มีสัญญาณ) เก็บย้อนหลังสูงสุด 5 ปี เก่ากว่านั้นลบทิ้งอัตโนมัติ
# =============================================================
def log_signal_history(spreadsheet_name, notable, price_map):
    """
    บันทึกหุ้นที่ผ่านเกณฑ์เด่นวันนี้ลงชีต 'Signal_History' (ต้องมีชีตนี้อยู่ก่อน คอลัมน์ตามลำดับ:
    Date, Ticker, Signal_Type, Price_At_Signal, Return_30D, Return_60D, Return_90D)
    คืนค่าเป็นจำนวนแถวที่บันทึกสำเร็จ
    """
    try:
        client = get_gsheet_client()
        sheet = get_cached_worksheet(client, spreadsheet_name, 'Signal_History')
        today_str = str(date.today())
        rows_to_add = []
        for signal_type, tickers in [
            ('Trend_Template', notable.get('trend_template', [])),
            ('RS_Cross_Up', notable.get('rs_cross_up', [])),
            ('New_52W_High', notable.get('new_52w_high', [])),
            ('Volume_Spike', notable.get('volume_spike', [])),
            ('Golden_Cross', notable.get('golden_cross', [])),
            ('RSI_Oversold_Bounce', notable.get('rsi_oversold_bounce', [])),
            ('VCP_Breakout', notable.get('vcp_breakout', [])),
        ]:
            for t in tickers:
                price = price_map.get(t, '')
                if price:
                    rows_to_add.append([today_str, t, signal_type, price, '', '', ''])
        if rows_to_add:
            sheet.append_rows(rows_to_add)
        return len(rows_to_add)
    except Exception as e:
        print(f"⚠️ บันทึกประวัติสัญญาณไม่สำเร็จ (ไม่กระทบการทำงานหลัก): {e}")
        return 0


def resolve_pending_signals(spreadsheet_name):
    """
    เช็คสัญญาณเก่าที่ครบกำหนด 30/60/90 วันแล้ว แต่ยังไม่มีผลตอบแทนบันทึกไว้ ดึงราคาย้อนหลังของ
    เฉพาะหุ้นที่จำเป็นต้องใช้ (ไม่ใช่ทั้ง 472 ตัว ประหยัด API มาก) มาคำนวณ % เปลี่ยนแปลงจากวันที่
    สัญญาณเกิด แล้วอัปเดตกลับเข้าไปในชีต คืนค่าเป็นจำนวนช่องที่อัปเดตสำเร็จ
    """
    try:
        client = get_gsheet_client()
        sheet = get_cached_worksheet(client, spreadsheet_name, 'Signal_History')
        records = sheet.get_all_records()
        if not records:
            return 0

        today = date.today()
        pending_tickers = set()
        rows_needing_update = []

        for idx, row in enumerate(records):
            try:
                signal_date = datetime.strptime(str(row.get('Date', '')), '%Y-%m-%d').date()
            except ValueError:
                continue
            days_elapsed = (today - signal_date).days
            needs = []
            if days_elapsed >= 30 and not str(row.get('Return_30D', '')).strip():
                needs.append(30)
            if days_elapsed >= 60 and not str(row.get('Return_60D', '')).strip():
                needs.append(60)
            if days_elapsed >= 90 and not str(row.get('Return_90D', '')).strip():
                needs.append(90)
            if needs:
                pending_tickers.add(str(row.get('Ticker', '')).strip())
                rows_needing_update.append((idx, row, signal_date, needs))

        if not rows_needing_update:
            return 0

        tickers_list = [t for t in pending_tickers if t]
        if not tickers_list:
            return 0

        # ดึงราคาย้อนหลังเฉพาะหุ้นที่จำเป็นต้องใช้เท่านั้น (คนละก้อนกับการสแกนหลักทั้ง 472 ตัว)
        raw_data = yf.download(tickers_list, period="1y", group_by='ticker', threads=True)

        updated_count = 0
        col_index_map = {30: 5, 60: 6, 90: 7}  # ตำแหน่งคอลัมน์ Return_30D/60D/90D (นับจาก 1)

        for idx, row, signal_date, needs in rows_needing_update:
            ticker = str(row.get('Ticker', '')).strip()
            try:
                price_at_signal = float(row.get('Price_At_Signal', 0) or 0)
            except (ValueError, TypeError):
                continue
            if price_at_signal <= 0:
                continue

            try:
                ticker_hist = raw_data['Close'] if len(tickers_list) == 1 else raw_data[ticker]['Close']
            except (KeyError, TypeError):
                continue
            ticker_hist = ticker_hist.dropna()
            if ticker_hist.empty:
                continue

            for days in needs:
                target_date = signal_date + timedelta(days=days)
                future_prices = ticker_hist[ticker_hist.index.date >= target_date]
                if future_prices.empty:
                    continue  # ยังไม่ถึงวันซื้อขายที่มีราคาหลังจากวันเป้าหมาย รอรอบถัดไป
                price_at_target = float(future_prices.iloc[0])
                pct_return = ((price_at_target - price_at_signal) / price_at_signal) * 100
                try:
                    sheet.update_cell(idx + 2, col_index_map[days], round(pct_return, 2))
                    updated_count += 1
                except Exception:
                    pass

        return updated_count
    except Exception as e:
        print(f"⚠️ อัปเดตผลตอบแทนสัญญาณเก่าไม่สำเร็จ (ไม่กระทบการทำงานหลัก): {e}")
        return 0


def cleanup_old_signals(spreadsheet_name, retention_years=5):
    """ลบสัญญาณที่เก่าเกินระยะเวลาที่กำหนด (ค่าเริ่มต้น 5 ปี) ออกจากชีต Signal_History เพื่อไม่ให้ข้อมูลสะสมมากเกินไป"""
    try:
        client = get_gsheet_client()
        sheet = get_cached_worksheet(client, spreadsheet_name, 'Signal_History')
        records = sheet.get_all_records()
        if not records:
            return 0

        cutoff_date = date.today() - timedelta(days=retention_years * 365)
        headers = sheet.row_values(1)
        rows_to_keep = [headers]
        removed_count = 0

        for row in records:
            try:
                signal_date = datetime.strptime(str(row.get('Date', '')), '%Y-%m-%d').date()
            except ValueError:
                rows_to_keep.append([row.get(h, '') for h in headers])
                continue
            if signal_date >= cutoff_date:
                rows_to_keep.append([row.get(h, '') for h in headers])
            else:
                removed_count += 1

        if removed_count > 0:
            sheet.clear()
            sheet.update(range_name='A1', values=rows_to_keep)

        return removed_count
    except Exception as e:
        print(f"⚠️ ล้างข้อมูลสัญญาณเก่าไม่สำเร็จ (ไม่กระทบการทำงานหลัก): {e}")
        return 0


@st.cache_data(ttl=600, show_spinner=False)
def load_signal_history(spreadsheet_name):
    """โหลดประวัติสัญญาณทั้งหมดจากชีต Signal_History มาเป็น DataFrame (จำผลลัพธ์ไว้ 10 นาที กันยิง API ซ้ำ)"""
    try:
        client = get_gsheet_client()
        sheet = get_cached_worksheet(client, spreadsheet_name, 'Signal_History')
        records = sheet.get_all_records()
        return pd.DataFrame(records) if records else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


# =============================================================
# 🆕 ระบบรายงานสรุปอัตโนมัติผ่าน Telegram — ดึงตรรกะกราฟแนวโน้ม Net Worth ที่มีอยู่แล้วในหน้าเว็บ
# (แท็บภาพรวม Net Worth) มาเป็นฟังก์ชันกลาง ใช้ได้ทั้งหน้าเว็บและสคริปต์รายงานอัตโนมัติรายเดือน
# =============================================================
def get_net_worth_trend_data(spreadsheet_name):
    """
    ดึงข้อมูลแนวโน้ม Net Worth ทุกหมวด (PVD, ประกัน, สหกรณ์, ธนาคาร, ประกันสังคม, กองทุนรวม,
    หุ้น+TFEX, ทองคำ, อสังหาริมทรัพย์) มารวมเป็นตารางเดียว (Total = รวมทุกหมวด รวมอสังหาฯ ด้วย,
    Total_Excl_RE = รวมทุกหมวดยกเว้นอสังหาฯ) คืนค่าเป็น DataFrame ว่างเปล่าถ้าไม่มีข้อมูลเลย
    ตรรกะเดียวกับกราฟแนวโน้มที่แสดงในแท็บ "ภาพรวม Net Worth" บนหน้าเว็บทุกประการ
    """
    try:
        client = get_gsheet_client()

        def get_df_safe(ws_name):
            try:
                sheet = get_cached_worksheet(client, spreadsheet_name, ws_name)
                records = sheet.get_all_records()
                return pd.DataFrame(records) if records else pd.DataFrame()
            except Exception:
                return pd.DataFrame()

        df_pvd = get_df_safe('Provident_Fund')
        df_ins = get_df_safe('Insurance')
        df_coop = get_df_safe('Coop')
        df_bank = get_df_safe('Bank_Account')
        df_sso = get_df_safe('SSO')
        df_mf = get_df_safe('Fund_Value_History')
        df_portfolio_hist = get_df_safe('Portfolio_History')
        df_gold = get_df_safe('Gold_Value_History')
        df_re = get_df_safe('Real_Estate_Value_History')

        def prepare_series(df, date_col, val_col, name):
            df = df.copy()
            if df.empty or val_col not in df.columns or date_col not in df.columns:
                return pd.DataFrame(columns=[name], index=pd.to_datetime([]))
            if date_col == 'Month':
                thai_months = {'มกราคม': '01', 'กุมภาพันธ์': '02', 'มีนาคม': '03', 'เมษายน': '04', 'พฤษภาคม': '05', 'มิถุนายน': '06', 'กรกฎาคม': '07', 'สิงหาคม': '08', 'กันยายน': '09', 'ตุลาคม': '10', 'พฤศจิกายน': '11', 'ธันวาคม': '12'}
                df['Month_Num'] = df[date_col].map(thai_months).fillna('12')
                df['Date'] = pd.to_datetime(df['Year_CE'].astype(str) + '-' + df['Month_Num'] + '-01', errors='coerce')
            else:
                df['Date'] = pd.to_datetime(df[date_col], errors='coerce')
            df[name] = df[val_col].astype(str).str.replace(',', '').replace('', '0').astype(float)
            return df.dropna(subset=['Date']).set_index('Date')[[name]]

        s_pvd = prepare_series(df_pvd, 'Month', 'Grand_Total', 'PVD')
        s_ins = prepare_series(df_ins, 'Date', 'Redemption_Value', 'Insurance')
        s_sso = prepare_series(df_sso, 'Date', 'Value', 'SSO')
        s_coop = prepare_series(df_coop, 'Date', 'Coop_Value', 'Coop')
        s_bank = prepare_series(df_bank, 'Date', 'Balance', 'Bank')
        s_mf = prepare_series(df_mf, 'Date', 'Value', 'Mutual_Fund')
        s_port = prepare_series(df_portfolio_hist, 'Date', 'Market_Value', 'Stock+TFEX')
        s_gold = prepare_series(df_gold, 'Date', 'Value', 'Gold')
        s_re = prepare_series(df_re, 'Date', 'Value', 'Real_Estate')

        if not s_ins.empty and not s_sso.empty:
            s_ins = s_ins.join(s_sso, how='outer').sort_index().ffill().fillna(0)
            s_ins['Insurance'] = s_ins['Insurance'] + s_ins['SSO']
            s_ins = s_ins[['Insurance']]
        elif s_ins.empty and not s_sso.empty:
            s_ins = s_sso.rename(columns={'SSO': 'Insurance'})

        series_list = [s for s in [s_pvd, s_ins, s_coop, s_bank, s_mf, s_port, s_gold, s_re] if not s.empty]
        if not series_list:
            return pd.DataFrame()

        df_merged = series_list[0]
        for s in series_list[1:]:
            df_merged = df_merged.join(s, how='outer')
        df_merged = df_merged.sort_index().ffill().fillna(0)
        df_merged['Total'] = df_merged.sum(axis=1)
        # 🆕 Total_Excl_RE = รวมทุกหมวดยกเว้นอสังหาริมทรัพย์ (ใช้ในกราฟรายงานอัตโนมัติตามที่ขอ)
        df_merged['Total_Excl_RE'] = df_merged['Total'] - df_merged.get('Real_Estate', 0)

        return df_merged
    except Exception as e:
        print(f"⚠️ ดึงข้อมูลแนวโน้ม Net Worth ไม่สำเร็จ: {e}")
        return pd.DataFrame()


def send_telegram_document(bot_token, chat_id, file_path, caption=""):
    """ส่งไฟล์แนบ (เช่น PDF) ผ่าน Telegram Bot คืนค่าเป็น (สำเร็จหรือไม่: bool, ข้อความ: str)"""
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    try:
        with open(file_path, 'rb') as f:
            files = {'document': f}
            payload = {'chat_id': chat_id, 'caption': caption, 'parse_mode': 'HTML'}
            resp = requests.post(url, data=payload, files=files, timeout=30)
        if resp.status_code == 200:
            return True, "ส่งไฟล์ Telegram สำเร็จ"
        return False, f"ส่งไม่สำเร็จ (HTTP {resp.status_code}): {resp.text}"
    except Exception as e:
        return False, f"ส่งไม่สำเร็จ: {e}"


# =============================================================
# 🆕 คำนวณ Net Worth แบบ "สด" (Live) สำหรับใช้ในรายงานอัตโนมัติรายเดือน — ให้ตัวเลขตรงกับที่
# หน้าเว็บแสดง ณ ขณะนั้นเป๊ะๆ (ไม่ใช่ยอดที่สแตมป์ไว้รายเดือนซึ่งอาจมาจากคนละวันกันในแต่ละหมวด)
# ดึงราคาตลาดสดจริงสำหรับหมวดที่ผันผวนรายวัน (หุ้น+TFEX ผ่าน yfinance, ทองคำผ่าน goldtraders.or.th)
# ส่วนหมวดอื่นๆ (PVD, ประกัน, สหกรณ์, ธนาคาร, ประกันสังคม, ประกันบำนาญ, กองทุนรวม) ใช้ยอดล่าสุดที่
# บันทึกไว้ในชีต ตรงกับที่หน้าเว็บทำอยู่แล้วทุกประการ (เพราะเป็นค่าที่กรอกเองเป็นครั้งคราว ไม่ใช่
# ราคาตลาดที่ขยับทุกวัน จึงไม่มีปัญหาความคลาดเคลื่อนแบบเดียวกับหุ้น/ทองคำ)
# =============================================================
# 🆕 เพิ่ม cache ไว้ 5 นาที เพราะฟังก์ชันนี้ยิง API ดึงราคาหุ้นทีละตัว + ราคาทองสด ค่อนข้างช้า
# ถ้าไม่แคชไว้ จะทำให้หน้า "ภาพรวม Net Worth" โหลดช้าลงมากทุกครั้งที่เปิด/รีเฟรชหน้า
@st.cache_data(ttl=300, show_spinner=False)
def compute_live_net_worth(spreadsheet_name):
    """
    คำนวณ Net Worth แบบสด คืนค่าเป็น dict {
        'asset_breakdown': [(ชื่อหมวด, มูลค่า), ...],   # เรียงเหมือนหน้าเว็บ ใช้กับ PDF ได้ตรงๆ
        'net_worth_excl_re': float, 'net_worth_total': float
    }
    """
    client = get_gsheet_client()

    def get_records_safe(ws_name):
        try:
            sheet = get_cached_worksheet(client, spreadsheet_name, ws_name)
            return sheet.get_all_records()
        except Exception:
            return []

    def safe_float(raw, default=0.0):
        s = str(raw).replace(',', '').replace('฿', '').replace('THB', '').strip()
        if not s:
            return default
        try:
            return float(s)
        except ValueError:
            return default

    # --- หมวดที่ใช้ "ยอดล่าสุดที่บันทึกไว้" (เหมือนหน้าเว็บทุกประการ ไม่ต้องคำนวณสดเพิ่ม) ---
    pvd_records = get_records_safe('Provident_Fund')
    pvd_value = safe_float(pvd_records[-1].get('Grand_Total', pvd_records[-1].get('Value', 0))) if pvd_records else 0.0

    ins_records = get_records_safe('Insurance')
    insurance_value = safe_float(ins_records[-1].get('Redemption_Value', ins_records[-1].get('Value', 0))) if ins_records else 0.0

    coop_records = get_records_safe('Coop')
    coop_value = safe_float(coop_records[-1].get('Coop_Value', coop_records[-1].get('Value', 0))) if coop_records else 0.0

    sso_records = get_records_safe('SSO')
    sso_value = safe_float(sso_records[-1].get('Value', 0)) if sso_records else 0.0

    pension_records = get_records_safe('Pension')
    pension_insurance_value = sum(safe_float(row.get('Value', 0)) for row in pension_records)

    bank_records = get_records_safe('Bank_Account')
    bank_balance = safe_float(bank_records[-1].get('Balance', 0)) if bank_records else 0.0

    # --- กองทุนรวม: คำนวณสดจาก Fund_History (ราคาปัจจุบันที่กรอกไว้ล่าสุด x จำนวนหน่วยที่ถืออยู่) ---
    fund_records = get_records_safe('Fund_History')
    mutual_fund_value = 0.0
    for fund_row in fund_records:
        if fund_row.get('Status', 'Holding') == 'Holding':
            try:
                curr_p = safe_float(fund_row.get('Current_Price', 0))
                units = safe_float(fund_row.get('Units', 0))
                mutual_fund_value += curr_p * units
            except (ValueError, TypeError):
                pass

    # --- อสังหาริมทรัพย์ ---
    re_records = get_records_safe('Real_Estate')
    total_real_estate = 0.0
    for item in re_records:
        market_val = safe_float(item.get("มูลค่าตลาด (บาท)", item.get("มูลค่าตลาด", 0)))
        debt_val = safe_float(item.get("ยอดหนี้คงเหลือ (บาท)", item.get("ยอดหนี้คงเหลือ", 0)))
        total_real_estate += (market_val - debt_val)

    # --- หุ้น: คำนวณสด ดึงราคาล่าสุดจริงต่อหุ้นแต่ละตัวที่ถืออยู่ (เหมือนหน้าเว็บ) ---
    portfolio_records = get_records_safe('PortfolioData')
    total_stock_value = 0.0
    for p in portfolio_records:
        # 🔧 แก้บั๊ก: เดิมอ่านแค่คอลัมน์ 'หุ้น'/'shares' อย่างเดียว แต่ระบบนี้ผ่านการเปลี่ยนชื่อ
        # คอลัมน์มาหลายรอบตลอดการพัฒนา (มีทั้ง 'หุ้น'/'Ticker' และ 'shares'/'จำนวน' ปนกันอยู่ตาม
        # ช่วงเวลาที่บันทึกไว้ — โค้ดจุดอื่นในระบบ เช่น tab_stock.py ก็มี fallback ครบทั้ง 2 แบบไว้
        # อยู่แล้ว) ทำให้บัญชีที่ข้อมูลพอร์ตยังเป็นชื่อคอลัมน์แบบเก่าอยู่ (เช่น 'Ticker' แทน 'หุ้น')
        # หาหุ้นไม่เจอเลยสักตัว คำนวณได้ 0 บาทเสมอ ทั้งที่มีข้อมูลอยู่จริง ตอนนี้เพิ่ม fallback ให้
        # ครบทุกชื่อคอลัมน์ที่เคยใช้มา เหมือนกับจุดอื่นๆ ในระบบ
        ticker = str(p.get('หุ้น', p.get('Ticker', ''))).strip().upper()
        shares = safe_float(p.get('shares', p.get('จำนวน', 0)))
        if not ticker or shares <= 0:
            continue
        try:
            m_price = float(yf.Ticker(f"{ticker}.BK").history(period="1d")['Close'].iloc[-1])
        except Exception:
            m_price = safe_float(p.get('avg_price', p.get('ต้นทุนเฉลี่ย', 0)))  # ดึงสดไม่สำเร็จ ใช้ราคาต้นทุนแทนชั่วคราว
        total_stock_value += shares * m_price

    # --- TFEX: เงินฝาก-ถอนสุทธิ + กำไร-ขาดทุนจากรายการที่ปิดสถานะแล้ว (ไม่ต้องดึงราคาตลาดสด
    # เพราะคำนวณจาก Realized PnL ที่บันทึกไว้แล้วเท่านั้น เหมือนหน้าเว็บ) ---
    tfex_records = get_records_safe('TFEX_History')
    total_pnl = 0.0
    for row in tfex_records:
        close_price = safe_float(row.get('Close_Price', 0))
        if close_price > 0:
            total_pnl += safe_float(row.get('Net_Profit', row.get('กำไรสุทธิ', 0)))

    cash_flow_records = get_records_safe('Cash_Flow')
    total_deposit = sum(safe_float(row.get('Amount', 0)) for row in cash_flow_records if str(row.get('Type', '')).strip().lower() == 'deposit')
    total_withdraw = sum(safe_float(row.get('Amount', 0)) for row in cash_flow_records if str(row.get('Type', '')).strip().lower() == 'withdraw')
    tfex_net_worth = (total_deposit - total_withdraw) + total_pnl

    total_stock_and_tfex = total_stock_value + tfex_net_worth

    # --- ทองคำ: ดึงราคาสดจากเว็บสมาคมค้าทองคำ (ใช้ฟังก์ชันกลาง fetch_live_gold_price() ที่แก้
    # ไปแล้ว ดึงจากเว็บ classic แทนเว็บใหม่ที่โหลดราคาผ่าน JavaScript) ---
    gold_records = get_records_safe('Gold_Portfolio')
    _live_bar, _live_jewelry, _ = fetch_live_gold_price()
    ref_gold_bar = _live_bar if _live_bar is not None else 68300.0
    ref_gold_jewelry = _live_jewelry if _live_jewelry is not None else 69100.0

    total_gold_value = 0.0
    for row in gold_records:
        g_type = row.get("ประเภท", "")
        weight_val = safe_float(row.get("น้ำหนัก/มูลค่าซื้อ", row.get("น้ำหนัก", 0.0)))
        if g_type == "ทองคำแท่ง":
            market_val = (weight_val / 15.244) * ref_gold_bar
        elif g_type == "ทองรูปพรรณ":
            market_val = weight_val * ref_gold_jewelry
        else:
            m_val = safe_float(row.get("มูลค่าตลาด", 0.0))
            market_val = m_val if m_val > 0 else weight_val
        total_gold_value += market_val

    net_worth_excl_re = (
        total_stock_and_tfex + pvd_value + insurance_value + coop_value + sso_value
        + pension_insurance_value + bank_balance + total_gold_value + mutual_fund_value
    )
    net_worth_total = net_worth_excl_re + total_real_estate

    asset_breakdown = [
        ("Stock + TFEX Portfolio", total_stock_and_tfex),
        ("Mutual Funds", mutual_fund_value),
        ("Provident Fund (PVD)", pvd_value),
        ("Unit-Linked Insurance", insurance_value),
        ("Cooperative Fund", coop_value),
        ("Social Security Fund", sso_value),
        ("Bank Accounts", bank_balance),
        ("Pension Insurance", pension_insurance_value),
        ("Gold", total_gold_value),
        ("Real Estate", total_real_estate),
    ]

    return {
        'asset_breakdown': asset_breakdown,
        'net_worth_excl_re': net_worth_excl_re,
        'net_worth_total': net_worth_total,
        # 🆕 เพิ่ม field แยกส่วนหุ้น+TFEX กับทองคำไว้ให้ดึงใช้ตรงๆ ได้ง่าย (ไม่ต้องแกะจาก
        # asset_breakdown list) — ใช้แก้ปัญหา "Net Worth แสดง 0 ตอนเปิดหน้าแรก" ในแท็บภาพรวม
        # Net Worth ซึ่งเดิมพึ่งค่าจาก st.session_state ที่ตั้งโดยแท็บหุ้น/ทองคำเท่านั้น (ต้องไป
        # เยี่ยมแท็บนั้นก่อนถึงจะมีค่า) พอเปลี่ยนมาใช้เมนู Sidebar แบบใหม่ที่ render แค่หน้าที่เลือก
        # อยู่เท่านั้น (ไม่ใช่ทุกแท็บพร้อมกันเหมือน st.tabs() เดิม) ค่าที่ยังไม่เคยไปเยี่ยมแท็บนั้นจะ
        # เป็น 0 ค้างอยู่ ตอนนี้คำนวณสดตรงนี้แทน ไม่ต้องพึ่งว่าแท็บไหนเคย render ไปแล้วหรือยัง
        'stock_and_tfex_value': total_stock_and_tfex,
        'gold_value': total_gold_value,
    }


# =============================================================
# 🆕 แก้บั๊ก: ฟังก์ชันดึงราคาทองสดเดิม (เดิมอยู่กระจายซ้ำใน tab_gold.py และในฟังก์ชัน
# compute_live_net_worth ด้านบน) ดึงราคาไม่สำเร็จเลยสักครั้ง — ลองมาแล้ว 2 เว็บของสมาคมค้าทองคำ
# เอง (www.goldtraders.or.th เว็บใหม่ และ classic.goldtraders.or.th เว็บเก่า) ทั้งคู่โหลดตาราง
# ราคาผ่าน JavaScript หลังโหลดหน้าเสร็จทั้งหมด (ราคาไม่ได้ฝังมาใน HTML ตอนโหลดหน้าครั้งแรกเลย)
# ดึงด้วย requests/BeautifulSoup ตรงๆ จึงไม่เจอตัวเลขราคาเลยสักครั้ง ตกไปใช้ราคาสำรอง (Fallback)
# ตลอดเวลา ไม่เคยอัปเดตจริง ตอนนี้เปลี่ยนไปใช้ goldprice88.com แทน (เว็บบุคคลที่สามที่จัดทำและ
# ตรวจสอบราคาจากประกาศของสมาคมค้าทองคำอีกที) ซึ่งหน้าแรกเป็น Server-Side Rendered จริง ราคาฝัง
# มาใน HTML ตรงๆ ตั้งแต่โหลดครั้งแรก รวมเป็นฟังก์ชันกลางจุดเดียว ใช้ร่วมกันได้ทั้งหน้าเว็บทองคำ
# และรายงานอัตโนมัติรายเดือน
# =============================================================
def fetch_live_gold_price():
    """
    ดึงราคาทองคำแท่ง/ทองรูปพรรณ (ขายออก) สดจาก goldprice88.com คืนค่าเป็น
    (ราคาทองคำแท่งขายออก, ราคาทองรูปพรรณขายออก, ข้อความสาเหตุ) — ราคาเป็น None ถ้าดึงไม่สำเร็จ
    ให้ผู้เรียกตัดสินใจเองว่าจะใช้ค่าสำรองอะไรต่อ
    ใช้ print() รายงานสาเหตุด้วย (เห็นใน log ของ GitHub Actions ตอนเรียกจาก monthly_report.py)
    และคืนค่าข้อความสาเหตุกลับไปเป็นค่าที่ 3 ด้วย (ให้ผู้เรียกจากหน้าเว็บ Streamlit เอาไปแสดงตรง
    หน้าเว็บได้เลย เพราะ Streamlit Cloud ไม่แสดง print() ธรรมดาใน log ของ "Manage app")
    """
# 🔧 แก้บั๊กรอบที่ 2: เว็บ classic.goldtraders.or.th ก็ใช้ไม่ได้เหมือนกัน — ตรวจสอบแล้วพบว่า
# ตารางราคาบนหน้านั้นก็โหลดผ่าน JavaScript แยกต่างหากด้วย (HTML ที่ได้มามีแค่เมนูนำทาง ไม่มี
# ตารางราคาเลย) เปลี่ยนมาใช้ goldprice88.com แทน ซึ่งเป็นเว็บบุคคลที่สามที่จัดทำและตรวจสอบราคา
# จากสมาคมค้าทองคำอีกที แต่หน้าแรกของเว็บนี้เป็น Server-Side Rendered จริง (ราคาฝังมาใน HTML ตรงๆ
# ตั้งแต่โหลดหน้าครั้งแรก ไม่ต้องพึ่ง JavaScript) มีราคาอยู่หลายจุดในหน้าเดียวกัน รวมถึงส่วน
# "ตัวแปรราคาใน Dataset" ที่เป็นรูปแบบ label แล้วตามด้วยตัวเลขบรรทัดถัดไปสะอาดมาก เหมาะกับการ
# ดึงด้วย Regex ที่สุดในบรรดาที่ลองมาทั้งหมด
# =============================================================
def fetch_live_gold_price():
    """
    ดึงราคาทองคำแท่ง/ทองรูปพรรณ (ขายออก) สดจาก goldprice88.com (จัดทำข้อมูลจากประกาศราคาของ
    สมาคมค้าทองคำ) คืนค่าเป็น (ราคาทองคำแท่งขายออก, ราคาทองรูปพรรณขายออก, ข้อความสาเหตุ)
    ราคาเป็น None ถ้าดึงไม่สำเร็จ ให้ผู้เรียกตัดสินใจเองว่าจะใช้ค่าสำรองอะไรต่อ
    """
    try:
        headers_req = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        resp = requests.get("https://goldprice88.com/", headers=headers_req, timeout=8)

        if resp.status_code != 200:
            _msg = f"เว็บตอบกลับ HTTP {resp.status_code}"
            print(f"⚠️ ดึงราคาทองไม่สำเร็จ: {_msg}")
            return None, None, _msg

        soup = BeautifulSoup(resp.text, 'html.parser')
        full_text = soup.get_text()

        # รูปแบบข้อความบนเว็บนี้: "ทองคำแท่ง 96.5% ขายออก" ตามด้วยตัวเลขในบรรทัดถัดไป (อาจมี
        # ช่องว่าง/ขึ้นบรรทัดใหม่คั่นกลาง) ใช้ re.DOTALL ให้จุด (.) จับขึ้นบรรทัดใหม่ได้ด้วย
        bar_match = re.search(r'ทองคำแท่ง\s*96\.5%\s*ขายออก\D{0,20}([\d,]+\.?\d*)', full_text, re.DOTALL)
        jewelry_match = re.search(r'ทองรูปพรรณ\s*96\.5%\s*ขายออก\D{0,20}([\d,]+\.?\d*)', full_text, re.DOTALL)

        bar_val = float(bar_match.group(1).replace(',', '')) if bar_match else None
        jewelry_val = float(jewelry_match.group(1).replace(',', '')) if jewelry_match else None

        # กันเผื่อ Regex จับตัวเลขผิดเพี้ยนไปนอกช่วงราคาทองที่สมเหตุสมผล (เช่น จับเลขปี/รหัสอื่น
        # มาแทน) ราคาทองคำควรอยู่ในช่วงหลักหมื่นบาทเสมอ ไม่ใช่หลักสิบ/ร้อย/ล้าน
        _bar_out_of_range = bar_val is not None and not (10000 <= bar_val <= 200000)
        _jewelry_out_of_range = jewelry_val is not None and not (10000 <= jewelry_val <= 200000)
        if _bar_out_of_range:
            bar_val = None
        if _jewelry_out_of_range:
            jewelry_val = None

        if bar_val is None or jewelry_val is None:
            # 🆕 แนบตัวอย่างเนื้อหาจริงที่ดึงได้มาด้วย (ตัดช่องว่าง/บรรทัดว่างส่วนเกินออกก่อน แล้ว
            # เอาแค่ 400 ตัวอักษรแรก) เพื่อดูว่าเจอหน้าเว็บแบบไหนกันแน่ (หน้าจริง? หน้าเช็คบอท?
            # หน้า redirect? ข้อความ error อื่นๆ?) โดยไม่ต้องเดาสุ่มแก้ไปเรื่อยๆ
            _cleaned_preview = ' '.join(full_text.split())[:400]
            _msg = (
                f"HTTP 200 แต่หาตัวเลขราคาทองไม่เจอ (bar_match={'พบ' if bar_match else 'ไม่พบ'}"
                f"{'/นอกช่วง' if _bar_out_of_range else ''}, "
                f"jewelry_match={'พบ' if jewelry_match else 'ไม่พบ'}{'/นอกช่วง' if _jewelry_out_of_range else ''}, "
                f"ความยาวเนื้อหา={len(full_text)} ตัวอักษร) | ตัวอย่างเนื้อหาที่ได้จริง: {_cleaned_preview}"
            )
            print(f"⚠️ ดึงราคาทองไม่สำเร็จ: {_msg}")
            return bar_val, jewelry_val, _msg

        return bar_val, jewelry_val, "สำเร็จ"
    except Exception as e:
        _msg = f"{type(e).__name__}: {e}"
        print(f"⚠️ ดึงราคาทองไม่สำเร็จ: {_msg}")
        return None, None, _msg


# =============================================================
# 🆕 ระบบ Watchlist เชิงปัจจัยพื้นฐาน (Fundamental Watchlist) — แยกจาก Watchlist เดิมที่ใช้เทรด
# โดยสิ้นเชิง เก็บหุ้นที่สนใจติดตามงบการเงินรายไตรมาส อัปโหลด PDF งบเอง (ดาวน์โหลดจาก set.or.th)
# ให้ Claude อ่าน สกัดตัวเลขสำคัญสไตล์ Mark Minervini ออกมาเป็นโครงสร้างที่เทียบข้ามไตรมาสได้ง่าย
# แล้วบันทึกประวัติถาวรไว้ เรียกดูย้อนหลัง + ให้ AI วิเคราะห์แนวโน้มการเติบโตได้
# =============================================================

# URL ไปหน้าวิเคราะห์งบการเงินของหุ้นแต่ละตัวบน SET (ยืนยันแล้วว่าใช้งานได้จริง)
SET_FINANCIAL_STATEMENT_URL_TEMPLATE = "https://www.set.or.th/th/market/product/stock/quote/{ticker}/financial-statement/financial-statements-analysis"


def get_set_financial_statement_url(ticker):
    """คืนค่า URL ไปหน้าวิเคราะห์งบการเงินของหุ้นตัวนั้นๆ บนเว็บ SET (ให้ผู้ใช้กดไปดาวน์โหลด PDF งบเอง)"""
    return SET_FINANCIAL_STATEMENT_URL_TEMPLATE.format(ticker=ticker.strip().upper())


def load_fundamental_watchlist(spreadsheet_name):
    """
    โหลดรายชื่อหุ้นในระบบ Watchlist เชิงปัจจัยพื้นฐาน (แยกจาก Watchlist เดิมที่ใช้เทรด) คืนค่าเป็น
    list ของ dict
    🔧 แก้บั๊ก: เดิม except Exception: return [] กลืน error ทุกชนิดไปเงียบๆ (429 Rate Limit,
    ปัญหาเชื่อมต่อชั่วคราว ฯลฯ) แล้วคืนค่า list ว่างเปล่าเหมือนกับ "ไม่มีข้อมูลจริง" ทำให้หน้าเว็บ
    ขึ้นข้อความ "ยังไม่มีหุ้นเลย" ทั้งที่ข้อมูลยังอยู่ครบใน Google Sheets เพียงแค่โหลดไม่สำเร็จ
    ชั่วคราวเท่านั้น (เจอบ่อยตอนรีเฟรชหน้าเว็บ เพราะมีการยิง API หลายจุดพร้อมกัน) ตอนนี้เพิ่ม retry
    แบบ exponential backoff + jitter ก่อน และถ้ายังไม่สำเร็จจริงๆ ให้ "โยน error" ออกไปแทนที่จะ
    คืนค่า [] เงียบๆ เพื่อให้ผู้เรียก (หน้าเว็บ) แยกแยะได้ว่า "โหลดไม่สำเร็จ" กับ "ไม่มีข้อมูลจริง"
    เป็นคนละกรณีกัน
    """
    last_error = None
    for attempt in range(3):
        try:
            client = get_gsheet_client()
            sheet = get_cached_worksheet(client, spreadsheet_name, 'Fundamental_Watchlist')
            return sheet.get_all_records()
        except Exception as e:
            last_error = e
        if attempt < 2:
            time.sleep((2 ** (attempt + 1)) + random.uniform(0.5, 1.5))
    raise RuntimeError(f"โหลด Fundamental Watchlist ไม่สำเร็จหลังลองครบ 3 ครั้ง: {last_error}")


def add_to_fundamental_watchlist(spreadsheet_name, ticker, note=""):
    """เพิ่มหุ้นเข้า Watchlist เชิงปัจจัยพื้นฐาน คืนค่าเป็น (สำเร็จหรือไม่: bool, ข้อความ: str)"""
    try:
        client = get_gsheet_client()
        sheet = get_cached_worksheet(client, spreadsheet_name, 'Fundamental_Watchlist')
        existing = sheet.get_all_records()
        ticker_clean = ticker.strip().upper()
        if any(str(row.get('Ticker', '')).strip().upper() == ticker_clean for row in existing):
            return False, f"{ticker_clean} อยู่ใน Watchlist นี้อยู่แล้วครับ"
        sheet.append_row([ticker_clean, str(date.today()), note])
        return True, f"เพิ่ม {ticker_clean} เข้า Watchlist เชิงปัจจัยพื้นฐานสำเร็จ"
    except Exception as e:
        return False, f"เพิ่มไม่สำเร็จ: {e}"


def remove_from_fundamental_watchlist(spreadsheet_name, ticker):
    """ลบหุ้นออกจาก Watchlist เชิงปัจจัยพื้นฐาน คืนค่าเป็น (สำเร็จหรือไม่: bool, ข้อความ: str)"""
    try:
        client = get_gsheet_client()
        sheet = get_cached_worksheet(client, spreadsheet_name, 'Fundamental_Watchlist')
        records = sheet.get_all_records()
        ticker_clean = ticker.strip().upper()
        rows_to_keep = [r for r in records if str(r.get('Ticker', '')).strip().upper() != ticker_clean]
        sheet.clear()
        sheet.append_row(["Ticker", "Date_Added", "Note"])
        for r in rows_to_keep:
            sheet.append_row([r.get('Ticker', ''), r.get('Date_Added', ''), r.get('Note', '')])
        return True, f"ลบ {ticker_clean} ออกจาก Watchlist สำเร็จ"
    except Exception as e:
        return False, f"ลบไม่สำเร็จ: {e}"


def save_fundamental_analysis(spreadsheet_name, ticker, quarter, year, metrics_dict, raw_analysis_json):
    """
    บันทึกผลวิเคราะห์งบการเงินรายไตรมาสลงชีต 'Fundamental_Analysis_History' — เก็บทั้งตัวเลขสำคัญ
    แยกคอลัมน์ (เทียบข้ามไตรมาสได้ง่าย) และข้อความ JSON เต็มไว้ด้วยเผื่อใช้อ้างอิงทีหลัง
    """
    try:
        client = get_gsheet_client()
        sheet = get_cached_worksheet(client, spreadsheet_name, 'Fundamental_Analysis_History')
        row = [
            ticker.strip().upper(), f"{quarter}", f"{year}", str(date.today()),
            metrics_dict.get('revenue'), metrics_dict.get('revenue_yoy_growth_pct'),
            metrics_dict.get('net_profit'), metrics_dict.get('net_profit_yoy_growth_pct'),
            metrics_dict.get('eps'), metrics_dict.get('gross_margin_pct'),
            metrics_dict.get('net_margin_pct'), metrics_dict.get('debt_to_equity'),
            metrics_dict.get('summary', ''), metrics_dict.get('highlights', ''),
            metrics_dict.get('risks', ''), raw_analysis_json,
        ]
        sheet.append_row(row)
        return True, "บันทึกผลวิเคราะห์สำเร็จ"
    except Exception as e:
        return False, f"บันทึกไม่สำเร็จ: {e}"


@st.cache_data(ttl=300, show_spinner=False)
def load_fundamental_analysis_history(spreadsheet_name, ticker=None):
    """
    โหลดประวัติผลวิเคราะห์งบการเงินทั้งหมด (หรือกรองเฉพาะหุ้นตัวเดียวถ้าระบุ ticker) คืนค่าเป็น DataFrame
    🔧 แก้บั๊กเดียวกับ load_fundamental_watchlist: เดิมกลืน error ทุกชนิดเงียบๆ คืนค่า DataFrame
    ว่างเปล่า ทำให้ดูเหมือน "ยังไม่มีประวัติ" ทั้งที่โหลดไม่สำเร็จชั่วคราวเท่านั้น ตอนนี้เพิ่ม retry
    ก่อน แล้วโยน error ออกไปถ้ายังไม่สำเร็จจริงๆ ให้ผู้เรียกจัดการแยกจากกรณี "ไม่มีข้อมูลจริง"
    """
    last_error = None
    for attempt in range(3):
        try:
            client = get_gsheet_client()
            sheet = get_cached_worksheet(client, spreadsheet_name, 'Fundamental_Analysis_History')
            records = sheet.get_all_records()
            if not records:
                return pd.DataFrame()
            df = pd.DataFrame(records)
            if ticker and 'Ticker' in df.columns:
                df = df[df['Ticker'].astype(str).str.upper() == ticker.strip().upper()]
            return df
        except Exception as e:
            last_error = e
        if attempt < 2:
            time.sleep((2 ** (attempt + 1)) + random.uniform(0.5, 1.5))
    raise RuntimeError(f"โหลดประวัติผลวิเคราะห์งบการเงินไม่สำเร็จหลังลองครบ 3 ครั้ง: {last_error}")


def save_document_analysis_history(spreadsheet_name, filename, analysis_result):
    """
    บันทึกผลวิเคราะห์เอกสาร (จากแท็บ "วิเคราะห์เอกสาร AI") ลงชีต 'Document_Analysis_History'
    เรียกดูย้อนหลังได้ในภายหลัง — ก่อนหน้านี้แสดงแค่บนหน้าจอตอนนั้น พอปิด/รีเฟรชหน้าเว็บ ผลลัพธ์
    จะหายไปเลย ไม่มีทางเรียกดูย้อนหลังได้
    """
    try:
        client = get_gsheet_client()
        sheet = get_cached_worksheet(client, spreadsheet_name, 'Document_Analysis_History')
        sheet.append_row([str(date.today()), filename, analysis_result])
        return True, "บันทึกสำเร็จ"
    except Exception as e:
        return False, f"บันทึกไม่สำเร็จ: {e}"


@st.cache_data(ttl=300, show_spinner=False)
def load_document_analysis_history(spreadsheet_name):
    """โหลดประวัติผลวิเคราะห์เอกสารทั้งหมด คืนค่าเป็น DataFrame"""
    try:
        client = get_gsheet_client()
        sheet = get_cached_worksheet(client, spreadsheet_name, 'Document_Analysis_History')
        records = sheet.get_all_records()
        return pd.DataFrame(records) if records else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


# =============================================================
# 🆕 บันทึกผลวิเคราะห์แนวโน้มการเติบโต (จากปุ่ม "ให้ AI วิเคราะห์แนวโน้มการเติบโต" ใน Fundamental
# Watchlist) ลง Google Sheets แทนที่จะแสดงแค่บนหน้าจอตอนนั้นแล้วหายไปเมื่อรีเฟรช เรียกดูย้อนหลังได้
# โดยไม่ต้องเรียก AI ซ้ำ ประหยัดโควต้า API
# =============================================================
def save_trend_analysis(spreadsheet_name, ticker, analysis_text, quarters_count):
    """บันทึกผลวิเคราะห์แนวโน้มของหุ้นตัวหนึ่งลงชีต 'Trend_Analysis_History' (เขียนทับของเดิมถ้ามีอยู่แล้ว เก็บแค่ผลล่าสุดต่อหุ้น)"""
    try:
        client = get_gsheet_client()
        sheet = get_cached_worksheet(client, spreadsheet_name, 'Trend_Analysis_History')
        records = sheet.get_all_records()
        ticker_clean = ticker.strip().upper()

        headers = sheet.row_values(1) or ["Ticker", "Date_Analyzed", "Quarters_Count", "Analysis_Text"]
        new_row = [ticker_clean, str(date.today()), quarters_count, analysis_text]

        # หาว่าหุ้นตัวนี้เคยมีผลวิเคราะห์บันทึกไว้แล้วหรือยัง (แถวไหน) ถ้ามีให้เขียนทับแถวเดิม
        # (เก็บแค่ผลล่าสุดต่อหุ้นพอ ไม่สะสมประวัติซ้อนกันไปเรื่อยๆ)
        existing_row_idx = None
        for i, row in enumerate(records):
            if str(row.get('Ticker', '')).strip().upper() == ticker_clean:
                existing_row_idx = i + 2  # +2 เพราะแถว 1 คือหัวตาราง และ index เริ่มที่ 0
                break

        if existing_row_idx:
            sheet.update(range_name=f'A{existing_row_idx}', values=[new_row])
        else:
            sheet.append_row(new_row)

        return True, "บันทึกผลวิเคราะห์แนวโน้มสำเร็จ"
    except Exception as e:
        return False, f"บันทึกไม่สำเร็จ: {e}"


@st.cache_data(ttl=60, show_spinner=False)
def load_trend_analysis(spreadsheet_name, ticker):
    """โหลดผลวิเคราะห์แนวโน้มล่าสุดของหุ้นตัวหนึ่ง คืนค่าเป็น dict หรือ None ถ้ายังไม่เคยวิเคราะห์"""
    try:
        client = get_gsheet_client()
        sheet = get_cached_worksheet(client, spreadsheet_name, 'Trend_Analysis_History')
        records = sheet.get_all_records()
        ticker_clean = ticker.strip().upper()
        for row in records:
            if str(row.get('Ticker', '')).strip().upper() == ticker_clean:
                return row
        return None
    except Exception:
        return None
