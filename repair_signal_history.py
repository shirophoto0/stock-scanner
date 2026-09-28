# =============================================================
# repair_signal_history.py
# 🔧 สคริปต์แก้ข้อมูลครั้งเดียว (one-time repair) — รันผ่าน GitHub Actions workflow_dispatch
# (repair_signal_history.yml) เพื่อล้างค่า Return_30D/60D/90D ที่ผิดพลาดใน Signal_History ของทั้ง 2
# บัญชี ที่เกิดจากบั๊ก resolve_pending_signals() เดิมยิง yf.download() ด้วยชื่อหุ้นที่ตัด ".BK" ออก
# แล้ว จับคู่กับหุ้นคนละตัวที่บังเอิญใช้ชื่อย่อเดียวกันในตลาดอื่น (ดูรายละเอียดที่คอมเมนต์ของ
# repair_corrupted_signal_returns() ใน backend_functions.py) — ใช้ครั้งเดียวแล้วลบไฟล์นี้ทิ้งได้เลย
# ไม่ต้องเก็บไว้ถาวรเหมือน daily_scan.py
# =============================================================
from backend_functions import repair_corrupted_signal_returns

TARGET_SPREADSHEETS = ["MyStockData", "Nujiwealth"]

if __name__ == "__main__":
    for spreadsheet_name in TARGET_SPREADSHEETS:
        cleared = repair_corrupted_signal_returns(spreadsheet_name)
        print(f"✅ ล้างค่า Return_% ที่ผิดพลาดใน {spreadsheet_name} แล้ว {cleared} ช่อง")
