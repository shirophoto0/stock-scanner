import streamlit as st
import pandas as pd
import os
import json
import firebase_admin
from firebase_admin import credentials, firestore

# ==========================================================
# ชั้นเชื่อมต่อ Firebase (แทนที่ get_gsheet_client เดิม)
# ==========================================================

@st.cache_resource(show_spinner=False)
def get_firestore_client():
    try:
        if not firebase_admin._apps:
            if 'FIREBASE_APPLICATION_CREDENTIALS' in os.environ:
                creds_dict = json.loads(os.environ['FIREBASE_APPLICATION_CREDENTIALS'])
            else:
                creds_dict = dict(st.secrets["firebase_service_account"])
            cred = credentials.Certificate(creds_dict)
            firebase_admin.initialize_app(cred)
        return firestore.client()
    except Exception as e:
        print(f"Error เชื่อมต่อ Firebase: {e}")
        raise e

# alias ให้ชื่อเดียวกับของเดิม เพื่อให้ทุกไฟล์ (App.py, tab_*.py) ที่เคยเรียก
# get_gsheet_client() ยังทำงานได้เหมือนเดิมโดยไม่ต้องแก้ไฟล์เหล่านั้นเลย
def get_gsheet_client():
    return get_firestore_client()


def get_active_sheet_name():
    return st.session_state.get('active_sheet_name', 'MyStockData')


# ==========================================================
# ตัวเลียนแบบ gspread Worksheet ด้วย Firestore
# โครงสร้างข้อมูลใน Firestore: users/{sheet_name}/{worksheet_name}/{แต่ละแถว}
# ==========================================================

class FirestoreWorksheet:
    """
    เลียนแบบ method หลักของ gspread Worksheet (get_all_records, append_rows)
    เพื่อให้โค้ดเดิมในไฟล์อื่นที่เรียก sheet.get_all_records() หรือ
    sheet.append_rows() ยังทำงานได้เหมือนเดิม ไม่ต้องแก้ไฟล์เหล่านั้น
    """
    def __init__(self, collection_ref):
        self._collection = collection_ref

    def get_all_records(self):
        docs = self._collection.stream()
        return [doc.to_dict() for doc in docs if doc.id != '_meta']

    def append_rows(self, rows, columns=None):
        if not rows:
            return
        if columns is None:
            if isinstance(rows[0], dict):
                for row in rows:
                    self._collection.add(row)
                return
            raise ValueError("append_rows กับข้อมูลแบบ list ต้องระบุ columns=[...] ด้วย")
        for row in rows:
            self._collection.add(dict(zip(columns, row)))


@st.cache_resource(ttl=300, show_spinner=False)
def get_cached_worksheet(_client, spreadsheet_name, worksheet_name):
    collection_ref = _client.collection('users').document(spreadsheet_name).collection(worksheet_name)
    return FirestoreWorksheet(collection_ref)


def get_worksheet_safely(client, spreadsheet_name, worksheet_name, retries=2, delay=1):
    try:
        return get_cached_worksheet(client, spreadsheet_name, worksheet_name)
    except Exception as e:
        st.error(f"❌ ไม่สามารถเชื่อมต่อ Firestore ได้: {e}")
        return None


# ==========================================================
# ฟังก์ชันบันทึกที่ต้องปรับ (ต้องระบุ columns เพราะ Firestore ไม่มี "หัวตาราง" แบบ Sheets)
# ==========================================================

def save_cash_to_gsheet(df):
    if df.empty:
        st.warning("ไม่มีข้อมูลที่จะบันทึก")
        return False
    try:
        client = get_gsheet_client()
        sheet = get_cached_worksheet(client, get_active_sheet_name(), "Cash_Flow")
        sheet.append_rows(df.values.tolist(), columns=df.columns.tolist())
        return True
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการบันทึก Cash_Flow: {e}")
        return False


def save_data_to_sheet(new_df, sheet_name):
    try:
        client = get_gsheet_client()
        sheet = get_cached_worksheet(client, get_active_sheet_name(), 'TFEX_History')
        cols = ["Trade_ID", "Date_Open", "Date_Close", "Series", "Status", "Size", "Open_Price",
                "Close_Price", "Realized", "Comm", "Net_Profit", "Win_Lose", "Reason"]
        new_df = new_df.reindex(columns=cols)
        sheet.append_rows(new_df.values.tolist(), columns=cols)
        st.cache_data.clear()
        st.success("เปิดสถานะสำเร็จ!")
        st.rerun()
        return True
    except Exception as e:
        st.error(f"บันทึกข้อมูลไม่สำเร็จ: {e}")
        return False
