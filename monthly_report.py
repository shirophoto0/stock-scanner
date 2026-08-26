# =============================================================
# monthly_report.py
# สคริปต์สำหรับรันอัตโนมัติทุกสิ้นเดือน (ผ่าน GitHub Actions) เพื่อสร้างรายงานสรุป Net Worth
# เป็นไฟล์ PDF (รวมกราฟวงกลมสัดส่วนสินทรัพย์ + กราฟเส้นแนวโน้ม Net Worth ไม่รวมอสังหาฯ) แล้วส่งเข้า
# Telegram ของแต่ละบัญชี — ต่อยอดจากระบบ PDF Export ที่มีอยู่แล้วในหน้าเว็บ (เดิมกดดาวน์โหลดเอง)
#
# 🔧 ทำไมต้องแยกไฟล์นี้ออกมา: เหตุผลเดียวกับ daily_scan.py — ไม่ผ่านหน้าเว็บ/ปุ่ม/Login เลย
# เรียกฟังก์ชันคำนวณ+สร้างรายงาน+ส่ง Telegram ตรงๆ
#
# ใช้ Chat ID เดียวกับระบบแจ้งเตือน Daily Scan (SPREADSHEET_TELEGRAM_CHAT_IDS) — ถ้าบัญชีไหนยังไม่
# ได้ตั้งค่า Chat ID จะข้ามการส่งรายงานให้บัญชีนั้นไปเงียบๆ (บัญชีอื่นยังได้รับตามปกติ)
# =============================================================
import os
from datetime import date
from backend_functions import (
    get_net_worth_trend_data,
    compute_live_net_worth,
    generate_net_worth_pdf_report,
    send_telegram_document,
)

TARGET_SPREADSHEETS = ["MyStockData", "Nujiwealth"]

SPREADSHEET_TELEGRAM_CHAT_IDS = {
    "MyStockData": os.environ.get("TELEGRAM_CHAT_ID"),
    "Nujiwealth": os.environ.get("TELEGRAM_CHAT_ID_PARTNER"),
}

# ชื่อที่จะโชว์บนรายงาน PDF ของแต่ละบัญชี
SPREADSHEET_APP_TITLES = {
    "MyStockData": "UM-Wealth",
    "Nujiwealth": "NJ-Wealth",
}


def main():
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        print("ℹ️ ยังไม่ได้ตั้งค่า TELEGRAM_BOT_TOKEN ข้ามการส่งรายงานเดือนนี้ทั้งหมด")
        return

    for spreadsheet_name in TARGET_SPREADSHEETS:
        chat_id = SPREADSHEET_TELEGRAM_CHAT_IDS.get(spreadsheet_name)
        if not chat_id:
            print(f"ℹ️ ยังไม่ได้ตั้งค่า Telegram Chat ID ของ {spreadsheet_name} ข้ามบัญชีนี้")
            continue

        print(f"📊 กำลังสร้างรายงานสำหรับ {spreadsheet_name}...")

        # 🔧 แก้บั๊ก: เดิมใช้ยอดที่ "สแตมป์ไว้รายเดือน" (จากชีต History ต่างๆ) มาสร้างสรุป/ตาราง
        # ในรายงาน แต่แต่ละหมวดสแตมป์คนละวันกัน (ตามแต่ว่าใครไปเปิดหน้าเว็บ/ทำธุรกรรมวันไหน) ทำให้
        # ตัวเลขรวมออกมาไม่ตรงกับที่หน้าเว็บแสดง ณ ตอนนั้นเป๊ะๆ โดยเฉพาะหุ้น+TFEX กับทองคำที่ราคา
        # ขยับทุกวัน ตอนนี้เปลี่ยนมาใช้ compute_live_net_worth() คำนวณสดใหม่ทั้งหมด ตรงกับหน้าเว็บ
        # เป๊ะๆ แทน — ส่วนกราฟเส้นแนวโน้มด้านล่างยังคงใช้ข้อมูลย้อนหลังแบบเดิม (get_net_worth_trend_data)
        # เพราะกราฟแนวโน้มต้องดูพัฒนาการข้ามเวลาอยู่แล้ว ไม่ใช่ตัวเลข ณ จุดเดียว
        live_data = compute_live_net_worth(spreadsheet_name)
        asset_breakdown = live_data['asset_breakdown']
        net_worth_excl_re = live_data['net_worth_excl_re']
        net_worth_total = live_data['net_worth_total']

        if not asset_breakdown or net_worth_total <= 0:
            print(f"⚠️ {spreadsheet_name}: ยังไม่มีข้อมูลสินทรัพย์เพียงพอ ข้ามการส่งรายงานเดือนนี้")
            continue

        trend_df = get_net_worth_trend_data(spreadsheet_name)
        app_title = SPREADSHEET_APP_TITLES.get(spreadsheet_name, spreadsheet_name)

        pdf_bytes = generate_net_worth_pdf_report(
            app_title, net_worth_excl_re, net_worth_total, asset_breakdown, trend_df=trend_df
        )

        file_name = f"/tmp/net_worth_report_{spreadsheet_name}_{date.today().strftime('%Y%m')}.pdf"
        with open(file_name, 'wb') as f:
            f.write(pdf_bytes)

        caption = (
            f"📊 <b>รายงานสรุป Net Worth ประจำเดือน {date.today().strftime('%B %Y')}</b>\n"
            f"Net Worth (ไม่รวมอสังหาฯ): {net_worth_excl_re:,.0f} ฿\n"
            f"Net Worth (รวมทั้งหมด): {net_worth_total:,.0f} ฿"
        )
        success, msg = send_telegram_document(bot_token, chat_id, file_name, caption)
        print(f"{'✅' if success else '⚠️'} ส่งรายงานให้ {spreadsheet_name}: {msg}")


if __name__ == "__main__":
    main()
