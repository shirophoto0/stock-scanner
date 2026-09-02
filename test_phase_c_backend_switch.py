"""
ทดสอบ Phase C: backend_functions.py จริง (ไม่ใช่ firestore_functions.py เฉยๆ) เมื่อสลับไปใช้
Firestore ผ่านสวิตช์ _TEST_FIRESTORE — ทดสอบเฉพาะ spreadsheet ทดสอบ "_phase_c_test" เท่านั้น
ไม่แตะ MyStockData / Nujiwealth ที่ย้ายมาจริงเลย

ทดสอบฟังก์ชันที่เสี่ยงที่สุด (ใช้ find/update_cell/delete_rows ที่เขียนขึ้นใหม่ใน Phase A):
  - add_to_watchlist / update_watchlist_target / remove_from_watchlist
  - _check_sl_tp_with_price_map (row_values + update_cell ผ่าน header lookup)
  - save_cash_to_gsheet (เพิ่งแก้ให้ส่ง columns ให้ Firestore)

วิธีรัน:
    python test_phase_c_backend_switch.py

ต้องมี _TEST_FIRESTORE = true ใน .streamlit/secrets.toml ก่อน (ในเครื่องนี้เท่านั้น)
"""
import sys

import pandas as pd
import streamlit as st

import backend_functions as bf
import firestore_functions as ff

TEST_SHEET = "_phase_c_test"

# ไม่พึ่งพา st.session_state (อาจไม่ทำงานเต็มรูปแบบนอก Streamlit runtime) — monkeypatch ตรงๆ แทน
bf.get_active_sheet_name = lambda: TEST_SHEET

all_ok = True


def check(label, condition, detail=""):
    global all_ok
    if condition:
        print(f"✅ {label}" + (f" — {detail}" if detail else ""))
    else:
        print(f"❌ {label}" + (f" — {detail}" if detail else ""))
        all_ok = False
    return condition


if TEST_SHEET not in set(st.secrets.get("_FIRESTORE_ENABLED_SHEETS", [])):
    print(f"❌ ยังไม่ได้เพิ่ม '{TEST_SHEET}' เข้า _FIRESTORE_ENABLED_SHEETS ใน .streamlit/secrets.toml — หยุดทดสอบ")
    sys.exit(1)

print(f"โหมด backend_functions._use_firestore() = {bf._use_firestore()}")
if not bf._use_firestore():
    print("❌ สวิตช์ไม่ทำงาน หยุดทดสอบ")
    sys.exit(1)

fs_client = ff.get_firestore_client()


def seed(worksheet_name, columns, rows):
    """เตรียมข้อมูลตั้งต้นเหมือนชีตจริงที่มีหัวตาราง+ข้อมูลอยู่แล้ว (ผ่าน firestore_functions ตรงๆ)"""
    sheet = ff.get_cached_worksheet(fs_client, TEST_SHEET, worksheet_name)
    sheet.clear()
    if rows:
        sheet.append_rows(rows, columns=columns)
    else:
        sheet.update('A1', [columns])
    return sheet


print("\n=== เตรียมข้อมูลทดสอบ (เหมือนชีตจริงที่ตั้งค่าไว้แล้ว) ===")
seed("Watchlist",
     ["Ticker", "Date_Added", "Price_When_Added", "Note", "Target_Price", "Target_Direction", "Alert_Sent"],
     [["EXIST", "2026-01-01", 10, "seed", "", "", "FALSE"]])
seed("PortfolioData",
     ["หุ้น", "shares", "avg_price", "cost_value", "m_price", "market_value", "profit", "profit_ptc",
      "Sector", "stop_loss_price", "sl_alert_sent", "take_profit_price", "tp_alert_sent"],
     [["TESTX", 1000, 10.0, "", "", "", "", "", "ทดสอบ", 8.0, "FALSE", 15.0, "FALSE"]])
seed("Cash_Flow", ["Date", "Type", "Amount", "Note"], [])
print("เตรียมข้อมูลเสร็จ")

print("\n=== 1. add_to_watchlist ===")
ok, msg = bf.add_to_watchlist("NEWTICK", 99.5, note="test-add")
check("add_to_watchlist ครั้งแรก", ok, msg)
records = ff.get_cached_worksheet(fs_client, TEST_SHEET, "Watchlist").get_all_records()
check("มี NEWTICK ใน Watchlist", any(r["Ticker"] == "NEWTICK" for r in records), f"ได้ {records}")

ok2, msg2 = bf.add_to_watchlist("NEWTICK", 99.5, note="test-add-dup")
check("add_to_watchlist ซ้ำต้องถูกกัน", not ok2, msg2)

print("\n=== 2. update_watchlist_target (find + update_cell) ===")
ok3, msg3 = bf.update_watchlist_target("NEWTICK", 88.0, "below")
check("update_watchlist_target สำเร็จ", ok3, msg3)
records = ff.get_cached_worksheet(fs_client, TEST_SHEET, "Watchlist").get_all_records()
new_row = next((r for r in records if r["Ticker"] == "NEWTICK"), None)
check("Target_Price/Target_Direction/Alert_Sent ถูกต้อง", new_row is not None
      and float(new_row["Target_Price"]) == 88.0
      and new_row["Target_Direction"] == "below"
      and str(new_row["Alert_Sent"]).upper() == "FALSE",
      f"ได้ {new_row}")

print("\n=== 3. remove_from_watchlist (find + delete_rows) ===")
ok4, msg4 = bf.remove_from_watchlist("EXIST")
check("remove_from_watchlist สำเร็จ", ok4, msg4)
records = ff.get_cached_worksheet(fs_client, TEST_SHEET, "Watchlist").get_all_records()
check("EXIST ถูกลบไปแล้ว เหลือแค่ NEWTICK", len(records) == 1 and records[0]["Ticker"] == "NEWTICK", f"ได้ {records}")

print("\n=== 4. _check_sl_tp_with_price_map (row_values header lookup + update_cell) ===")
triggered = bf._check_sl_tp_with_price_map(TEST_SHEET, {"TESTX": 7.5})  # ต่ำกว่า stop_loss_price=8.0
check("ตรวจเจอ SL trigger", len(triggered) == 1 and triggered[0]["type"] == "SL" and triggered[0]["ticker"] == "TESTX", f"ได้ {triggered}")
records = ff.get_cached_worksheet(fs_client, TEST_SHEET, "PortfolioData").get_all_records()
row = records[0]
check("sl_alert_sent ถูกตั้งเป็น TRUE แล้ว", str(row["sl_alert_sent"]).upper() == "TRUE", f"ได้ {row}")

print("\n=== 5. save_cash_to_gsheet (append_rows + columns delegation fix) ===")
df_cash = pd.DataFrame([{"Date": "2026-09-02", "Type": "ทดสอบ", "Amount": 1000, "Note": "phase-c-test"}])
ok5 = bf.save_cash_to_gsheet(df_cash)
check("save_cash_to_gsheet สำเร็จ", ok5)
records = ff.get_cached_worksheet(fs_client, TEST_SHEET, "Cash_Flow").get_all_records()
check("ข้อมูล Cash_Flow ถูกบันทึกถูกต้อง", len(records) == 1 and records[0]["Amount"] == 1000, f"ได้ {records}")

print("\n=== เก็บกวาดข้อมูลทดสอบ ===")
for ws_name in ["Watchlist", "PortfolioData", "Cash_Flow"]:
    ff.get_cached_worksheet(fs_client, TEST_SHEET, ws_name).clear()
print("ลบข้อมูลทดสอบทิ้งเรียบร้อย")

print("\n" + ("🎉 Phase C ผ่านครบทุกขั้นตอน" if all_ok else "⚠️ มีบางขั้นตอนไม่ผ่าน ดูรายละเอียดด้านบน"))
sys.exit(0 if all_ok else 1)
