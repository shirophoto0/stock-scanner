# =============================================================
# restore_real_estate.py
# 🔧 สคริปต์กู้คืนข้อมูลครั้งเดียว (one-time restore) — รันผ่าน GitHub Actions workflow_dispatch
# (restore_real_estate.yml) เพื่อกู้คืนข้อมูล Real_Estate ของบัญชี MyStockData ที่หายไปทั้งหมด
# เพราะบั๊กเดิมใน tab_real_estate.py: save_real_estate_to_sheet_safe() เรียก sheet.clear() ก่อน
# append_row()/append_rows() เสมอ (clear() ลบ schema (_meta) ของ FirestoreWorksheet ทิ้งไปด้วย)
# ทำให้ตอนผู้ใช้กดบันทึกแก้ไขครั้งแรก (ก่อนแก้บั๊กใน commit e3f0282) ข้อมูลถูกลบไปจริงตั้งแต่ก่อน
# ที่จะเขียนข้อมูลใหม่กลับเข้าไปไม่สำเร็จ — ใช้ข้อมูล 3 รายการที่ผู้ใช้ยืนยันจากภาพหน้าจอก่อนข้อมูลหาย
# ใช้ครั้งเดียวแล้วลบไฟล์นี้ทิ้งได้เลย ไม่ต้องเก็บไว้ถาวรเหมือน daily_scan.py
# =============================================================
from datetime import datetime
from backend_functions import get_gsheet_client, get_worksheet_safely

SPREADSHEET_NAME = "MyStockData"

HEADER = ["ชื่อทรัพย์สิน", "มูลค่าตลาด (บาท)", "ยอดหนี้คงเหลือ (บาท)", "มูลค่าสุทธิ (บาท)", "หมายเหตุ", "วันที่บันทึก"]

ITEMS = [
    {"name": "D Condo นครระยอง", "market": 1500000.00, "debt": 0.00, "note": "ปล่อยเช่าอยู่"},
    {"name": "Life in the garden banchang", "market": 5200000.00, "debt": 921718.00, "note": ""},
    {"name": "บ้านแฝด ตำบลสุเทพ เชียงใหม่", "market": 1800000.00, "debt": 0.00, "note": "พ่อแม่อาศัยอยู่"},
]

if __name__ == "__main__":
    current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    for item in ITEMS:
        net_val = item["market"] - item["debt"]
        rows.append([item["name"], item["market"], item["debt"], net_val, item["note"], current_date])

    client = get_gsheet_client()
    sheet = get_worksheet_safely(client, SPREADSHEET_NAME, "Real_Estate")
    if sheet is None:
        print("❌ เปิด worksheet Real_Estate ไม่สำเร็จ")
    else:
        sheet.clear()
        sheet.update("A1", [HEADER] + rows)
        print(f"✅ กู้คืนข้อมูล Real_Estate ของ {SPREADSHEET_NAME} สำเร็จ {len(rows)} รายการ")
