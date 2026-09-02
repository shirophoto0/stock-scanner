"""
สคริปต์ทดสอบ FirestoreWorksheet (Phase A) แบบแยกเดี่ยว — ไม่แตะแอปหลัก ไม่แตะ
collection จริงของ production (MyStockData / Nujiwealth)

วิธีรัน:
    streamlit run test_firestore_connection.py

ทดสอบทุก method ที่ backend_functions.py เรียกใช้จริงผ่าน gspread Worksheet:
get_all_records, append_rows, append_row, update_cell, find, delete_rows,
row_values, get_all_values, update() (ทั้งแบบเขียนทับทั้งชีต และแก้บางแถว), clear()
ทุกอย่างยิงใส่ collection ทดสอบ "_connection_test" เท่านั้น แล้วลบทิ้งเมื่อจบ
"""
import streamlit as st
from firestore_functions import get_firestore_client, get_cached_worksheet

st.title("🔥 ทดสอบ FirestoreWorksheet (Phase A)")

TEST_SPREADSHEET_NAME = "_connection_test"
TEST_WORKSHEET_NAME = "_ping"


def check(label, condition, detail=""):
    if condition:
        st.success(f"✅ {label}" + (f" — {detail}" if detail else ""))
    else:
        st.error(f"❌ {label}" + (f" — {detail}" if detail else ""))
    return condition


if st.button("เริ่มทดสอบ", type="primary"):
    all_ok = True

    st.write("### 1. เชื่อมต่อ Firestore")
    try:
        client = get_firestore_client()
        all_ok &= check("เชื่อมต่อสำเร็จ", True, f"project: {client.project}")
    except Exception as e:
        check("เชื่อมต่อไม่สำเร็จ", False, str(e))
        st.stop()

    st.cache_resource.clear()
    sheet = get_cached_worksheet(client, TEST_SPREADSHEET_NAME, TEST_WORKSHEET_NAME)
    # เก็บกวาดข้อมูลทดสอบเก่า (ถ้ามีจากรันครั้งก่อน) ก่อนเริ่ม
    sheet.clear()

    st.write("### 2. append_rows() + get_all_records()")
    try:
        sheet.append_rows(
            [["AAA", 10, "note1"], ["BBB", 20, "note2"]],
            columns=["Ticker", "Value", "Note"],
        )
        records = sheet.get_all_records()
        all_ok &= check("append_rows / get_all_records", records == [
            {"Ticker": "AAA", "Value": 10, "Note": "note1"},
            {"Ticker": "BBB", "Value": 20, "Note": "note2"},
        ], f"ได้ {records}")
    except Exception as e:
        all_ok &= check("append_rows / get_all_records", False, str(e))

    st.write("### 3. append_row() (เอกพจน์)")
    try:
        sheet.append_row(["CCC", 30, "note3"])
        records = sheet.get_all_records()
        all_ok &= check("append_row", len(records) == 3 and records[2]["Ticker"] == "CCC", f"ได้ {records}")
    except Exception as e:
        all_ok &= check("append_row", False, str(e))

    st.write("### 4. row_values() / get_all_values()")
    try:
        header = sheet.row_values(1)
        row2 = sheet.row_values(2)
        all_ok &= check("row_values", header == ["Ticker", "Value", "Note"] and row2 == ["AAA", 10, "note1"], f"header={header}, row2={row2}")
        all_values = sheet.get_all_values()
        all_ok &= check("get_all_values", len(all_values) == 4, f"ได้ {all_values}")
    except Exception as e:
        all_ok &= check("row_values / get_all_values", False, str(e))

    st.write("### 5. find() + update_cell()")
    try:
        cell = sheet.find("BBB")
        all_ok &= check("find", cell is not None and cell.row == 3, f"cell.row={getattr(cell, 'row', None)}")
        sheet.update_cell(cell.row, 3, "updated-note")
        records = sheet.get_all_records()
        all_ok &= check("update_cell", records[1]["Note"] == "updated-note", f"ได้ {records[1]}")
    except Exception as e:
        all_ok &= check("find / update_cell", False, str(e))

    st.write("### 6. update() แบบแก้ทั้งแถว (anchor เดียว)")
    try:
        sheet.update(range_name="A2", values=[["AAA2", 11, "note1-edit"]])
        records = sheet.get_all_records()
        all_ok &= check("update (single row anchor)", records[0] == {"Ticker": "AAA2", "Value": 11, "Note": "note1-edit"}, f"ได้ {records[0]}")
    except Exception as e:
        all_ok &= check("update (single row anchor)", False, str(e))

    st.write("### 7. delete_rows()")
    try:
        sheet.delete_rows(4)  # ลบแถว CCC (แถวที่ 4 = doc ลำดับที่ 3)
        records = sheet.get_all_records()
        all_ok &= check("delete_rows", len(records) == 2, f"เหลือ {records}")
    except Exception as e:
        all_ok &= check("delete_rows", False, str(e))

    st.write("### 8. update() แบบเขียนทับทั้งชีต")
    try:
        new_table = [
            ["Ticker", "Value", "Note"],
            ["XXX", 99, "fresh1"],
            ["YYY", 88, "fresh2"],
            ["ZZZ", 77, "fresh3"],
        ]
        sheet.update("A1", new_table)
        records = sheet.get_all_records()
        all_ok &= check("update (full replace)", len(records) == 3 and records[0]["Ticker"] == "XXX", f"ได้ {records}")
    except Exception as e:
        all_ok &= check("update (full replace)", False, str(e))

    st.write("### 9. clear()")
    try:
        sheet.clear()
        records = sheet.get_all_records()
        all_ok &= check("clear", records == [], f"ได้ {records}")
    except Exception as e:
        all_ok &= check("clear", False, str(e))

    st.write("---")
    if all_ok:
        st.success("🎉 ผ่านครบทุกขั้นตอน — FirestoreWorksheet (Phase A) ทำงานถูกต้อง")
    else:
        st.error("⚠️ มีบางขั้นตอนไม่ผ่าน ดูรายละเอียดด้านบน")
