# =============================================================
# daily_scan.py
# สคริปต์สำหรับรันอัตโนมัติทุกวัน (ผ่าน GitHub Actions) เพื่อสแกนข้อมูลหุ้นทั้งหมด
# แล้วบันทึกผลลัพธ์ลง Google Sheets ของทั้ง 2 บัญชี (ข้อมูลตลาดหุ้นเป็นข้อมูลทั่วไป
# ไม่ใช่ข้อมูลส่วนตัวของใครคนใดคนหนึ่ง จึงบันทึกซ้ำให้ทั้งสองบัญชีมีข้อมูลล่าสุดเหมือนกัน)
#
# 🔧 ทำไมต้องแยกไฟล์นี้ออกมาจาก App.py:
# 1. App.py มีระบบ Login (check_login()) อยู่เกือบบนสุดของไฟล์ ถ้ารัน "python App.py" ตรงๆ
#    ในเครื่อง GitHub Actions (ไม่มีคนกรอกรหัสผ่านจริง) จะไปค้างที่หน้า Login แล้วหยุดทำงาน
#    ทันที (st.stop()) ไม่มีทางไปถึงขั้นตอนสแกนหุ้นได้เลย
# 2. การสแกนหุ้นในหน้าเว็บถูกออกแบบให้ทำงานตอน "กดปุ่ม" เท่านั้น การรัน App.py แบบสคริปต์เฉยๆ
#    ไม่มีคนกดปุ่มจริง จึงไม่มีทางไปถึงขั้นตอนสแกนได้อยู่แล้วตั้งแต่แรก (ไม่เกี่ยวกับระบบ Login)
# ไฟล์นี้จึงเรียกเฉพาะฟังก์ชันสแกน+บันทึกข้อมูลตรงๆ โดยไม่ผ่านหน้าเว็บ/ปุ่ม/Login เลย
# =============================================================
import numpy as np
from backend_functions import (
    load_and_calculate_stock_data_optimized,
    get_gsheet_client,
    get_cached_spreadsheet,
)

# รายชื่อ Google Sheet (ของแต่ละคน) ที่ต้องการบันทึกผลสแกนลงไป
# ข้อมูลตลาดหุ้นเหมือนกันทุกบัญชี จึงบันทึกซ้ำให้ครบทุกชื่อในลิสต์นี้
TARGET_SPREADSHEETS = ["MyStockData", "Nujiwealth"]


def save_scan_result(df, spreadsheet_name):
    """
    บันทึกผลสแกนลงชีต StockData ของ Google Sheet ที่ระบุ
    เขียนแบบไม่พึ่งพา st.session_state เลย (ต่างจาก save_to_gsheet() ในหน้าเว็บที่อ่านชื่อชีต
    จาก session_state ของผู้ใช้ที่ login อยู่ ซึ่งไม่มีค่าในการรันแบบอัตโนมัตินี้)
    """
    client = get_gsheet_client()
    sheet = get_cached_spreadsheet(client, spreadsheet_name).worksheet('StockData')
    df_clean = df.replace([np.inf, -np.inf], 0).fillna("")
    data_to_write = [df_clean.columns.tolist()] + df_clean.values.tolist()
    sheet.update(range_name='A1', values=data_to_write)
    print(f"✅ บันทึกข้อมูลลง {spreadsheet_name} สำเร็จ ({len(df_clean)} แถว)")


def main():
    print("🔄 เริ่มสแกนข้อมูลหุ้นทั้งหมด...")
    df_result = load_and_calculate_stock_data_optimized()

    if df_result is None or df_result.empty:
        print("❌ สแกนไม่สำเร็จ หรือไม่มีข้อมูลหุ้นเลย ยกเลิกการบันทึก")
        return

    print(f"📊 สแกนสำเร็จ {len(df_result)} ตัว กำลังบันทึกลง {len(TARGET_SPREADSHEETS)} ชีต...")
    for spreadsheet_name in TARGET_SPREADSHEETS:
        try:
            save_scan_result(df_result, spreadsheet_name)
        except Exception as e:
            # ถ้าชีตใดชีตหนึ่งบันทึกไม่สำเร็จ ให้ข้ามไปทำชีตถัดไปต่อ ไม่ให้ทั้ง job ล้มเหลวไปด้วย
            print(f"⚠️ บันทึกลง {spreadsheet_name} ไม่สำเร็จ: {e}")

    print("🏁 จบการทำงานสแกนหุ้นรายวัน")


if __name__ == "__main__":
    main()
