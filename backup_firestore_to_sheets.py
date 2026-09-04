"""
สคริปต์ backup ข้อมูลจาก Firestore (ฐานข้อมูลจริงที่แอปใช้งานอยู่) กลับไปที่ Google Sheets
รันอัตโนมัติทุกสัปดาห์ (เที่ยงคืนวันจันทร์) ผ่าน GitHub Actions (.github/workflows/backup_firestore_to_sheets.yml)

หลักการความปลอดภัย:
- อ่านจาก Firestore แบบ "อ่านอย่างเดียว" เท่านั้น (ไม่มีการเขียน/แก้ไข/ลบ Firestore เด็ดขาด)
- เขียนทับ Google Sheets ทั้งชีต (clear แล้วเขียนใหม่ทั้งหมด) ในแต่ละ worksheet ที่เจอ — ปลอดภัย
  เพราะ Google Sheets ตอนนี้เป็นแค่สำเนา backup ที่ไม่มีแอปไหนอ่าน/เขียนจริงแล้ว (Firestore เป็น
  แหล่งข้อมูลจริงของแอป) การเขียนทับทุกวันจึงไม่กระทบการทำงานของแอปเลย
- ใช้ client ของ Google Sheets แบบตรงๆ เสมอ (ไม่ผ่านสวิตช์ _FIRESTORE_ENABLED_SHEETS ใน
  backend_functions.py) เพื่อไม่ให้พลาดไปเปิด Firestore client แทนตอนจะเขียนข้อมูลลง Sheets

วิธีใช้:
    python backup_firestore_to_sheets.py                 # dry-run แสดงตัวอย่างอย่างเดียว
    python backup_firestore_to_sheets.py --apply          # เขียนจริงลง Google Sheets
    python backup_firestore_to_sheets.py --sheets MyStockData --apply
"""
import argparse
import json
import os
import random
import sys
import time

import gspread
import streamlit as st
from google.oauth2.service_account import Credentials

from firestore_functions import get_firestore_client, get_cached_worksheet

# worksheet ที่ไม่ backup — เป็นข้อมูลผลสแกนหุ้นของตลาดโดยรวม (ไม่ใช่ข้อมูลทางการเงินส่วนตัว)
# แถวเยอะมาก (StockData ~472 แถว, Sector_Mapping ~494 แถว, Signal_History ~977 แถว) กิน Firestore
# read quota ต่อวันเยอะโดยไม่จำเป็น เพราะ scan ใหม่ได้ทุกวันอยู่แล้วผ่าน daily_scan.py ไม่ต้องมี backup
EXCLUDE_FROM_BACKUP = {"StockData", "Sector_Mapping", "Signal_History"}


def get_real_gsheet_client():
    """เหมือนกับใน migrate_to_firestore.py — ต้องได้ client ของ Google Sheets จริงเสมอ ไม่ผ่านสวิตช์"""
    scope = [
        "https://spreadsheets.google.com/feeds",
        'https://www.googleapis.com/auth/spreadsheets',
        "https://www.googleapis.com/auth/drive"
    ]
    if 'GOOGLE_APPLICATION_CREDENTIALS' in os.environ:
        creds_dict = json.loads(os.environ['GOOGLE_APPLICATION_CREDENTIALS'])
    else:
        creds_dict = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    return gspread.authorize(creds)


_RETRYABLE_MARKERS = ("429", "Quota exceeded", "503", "currently unavailable", "500", "Internal error")


def _retry_sheets_call(fn, *args, retries=6, **kwargs):
    for attempt in range(retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if attempt < retries - 1 and any(m in str(e) for m in _RETRYABLE_MARKERS):
                wait = 15 * (attempt + 1) + random.uniform(1, 5)
                print(f"    ⏳ โดนปัญหาชั่วคราว ({e}) รอ {wait:.1f}s แล้วลองใหม่ (ครั้งที่ {attempt + 1}/{retries})...")
                time.sleep(wait)
                continue
            raise


def backup_worksheet(fs_client, spreadsheet, spreadsheet_name, ws_name, apply_changes):
    print(f"  → {ws_name}")
    try:
        fs_sheet = get_cached_worksheet(fs_client, spreadsheet_name, ws_name)
        header = fs_sheet.row_values(1)
        records = fs_sheet.get_all_records()
    except Exception as e:
        print(f"    ❌ อ่านจาก Firestore ไม่สำเร็จ: {e}")
        return False

    if not header:
        print("    ⏭️  worksheet ว่างเปล่าใน Firestore — ข้าม")
        return True

    print(f"    พบ {len(records)} แถว, {len(header)} คอลัมน์")

    if not apply_changes:
        print(f"    (dry-run) ตัวอย่างข้อมูล: {records[:2]}")
        return True

    try:
        try:
            gs_sheet = _retry_sheets_call(spreadsheet.worksheet, ws_name)
        except gspread.exceptions.WorksheetNotFound:
            gs_sheet = _retry_sheets_call(
                spreadsheet.add_worksheet, title=ws_name, rows=max(len(records) + 10, 100), cols=max(len(header), 10)
            )
        data_matrix = [[rec.get(h, '') for h in header] for rec in records]
        _retry_sheets_call(gs_sheet.clear)
        _retry_sheets_call(gs_sheet.update, [header] + data_matrix)
    except Exception as e:
        print(f"    ❌ เขียนลง Google Sheets ไม่สำเร็จ: {e}")
        return False

    print(f"    ✅ backup สำเร็จ ({len(records)} แถว)")
    return True


def main():
    parser = argparse.ArgumentParser(description="Backup ข้อมูลจาก Firestore กลับไป Google Sheets")
    parser.add_argument("--sheets", default="MyStockData,Nujiwealth", help="รายชื่อ spreadsheet คั่นด้วย ,")
    parser.add_argument("--apply", action="store_true", help="เขียนจริงลง Google Sheets (ค่าเริ่มต้นคือ dry-run)")
    args = parser.parse_args()

    sheet_names = [s.strip() for s in args.sheets.split(",") if s.strip()]
    mode_label = "🔴 APPLY (เขียนจริงลง Google Sheets)" if args.apply else "🟡 DRY-RUN (แสดงตัวอย่างอย่างเดียว)"
    print(f"โหมด: {mode_label}")
    print(f"Spreadsheets: {sheet_names}\n")

    try:
        fs_client = get_firestore_client()
    except Exception as e:
        print(f"❌ เชื่อมต่อ Firestore ไม่สำเร็จ: {e}")
        sys.exit(1)

    gs_client = None
    if args.apply:
        try:
            gs_client = get_real_gsheet_client()
        except Exception as e:
            print(f"❌ เชื่อมต่อ Google Sheets ไม่สำเร็จ: {e}")
            sys.exit(1)
        if not hasattr(gs_client, "open"):
            print("❌ client ที่ได้ไม่ใช่ gspread client จริง (ไม่มี .open) — หยุดทันที")
            sys.exit(1)

    overall_ok = True
    for spreadsheet_name in sheet_names:
        print(f"=== {spreadsheet_name} ===")

        # หา worksheet ทั้งหมดที่มีอยู่จริงใน Firestore ของบัญชีนี้ (ไม่ต้องเขียนชื่อ hardcode ไว้
        # ตายตัว เผื่อมี worksheet ใหม่เพิ่มขึ้นมาทีหลัง จะ backup ให้ครบอัตโนมัติ)
        try:
            spreadsheet_doc_ref = fs_client.collection('users').document(spreadsheet_name)
            worksheet_names = [c.id for c in spreadsheet_doc_ref.collections() if c.id not in EXCLUDE_FROM_BACKUP]
        except Exception as e:
            print(f"❌ อ่านรายชื่อ worksheet จาก Firestore ไม่สำเร็จ: {e}")
            overall_ok = False
            continue

        print(f"พบ {len(worksheet_names)} worksheet ใน Firestore (หลังตัด {sorted(EXCLUDE_FROM_BACKUP)} ออก): {worksheet_names}")

        spreadsheet = None
        if args.apply:
            try:
                spreadsheet = _retry_sheets_call(gs_client.open, spreadsheet_name)
            except Exception as e:
                print(f"❌ เปิด spreadsheet '{spreadsheet_name}' บน Google Sheets ไม่สำเร็จ: {e}")
                overall_ok = False
                continue

        for i, ws_name in enumerate(worksheet_names):
            if i > 0:
                time.sleep(1.5)  # เว้นจังหวะกัน 429
            ok = backup_worksheet(fs_client, spreadsheet, spreadsheet_name, ws_name, args.apply)
            overall_ok = overall_ok and ok
        print()

    if overall_ok:
        print("🎉 เสร็จสิ้นทุกขั้นตอนโดยไม่มีข้อผิดพลาด")
    else:
        print("⚠️ มีบาง worksheet ที่ผิดพลาด ดูรายละเอียดด้านบน")
        sys.exit(1)


if __name__ == "__main__":
    main()
