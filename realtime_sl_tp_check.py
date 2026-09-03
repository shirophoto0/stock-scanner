# =============================================================
# realtime_sl_tp_check.py
# สคริปต์สำหรับรันถี่ๆ (ทุก 15 นาที ผ่าน GitHub Actions) ระหว่างเวลาตลาดหุ้นไทยเปิด เพื่อเช็คว่า
# 1) หุ้นในพอร์ตตัวไหนถึงจุด Stop Loss / Take Profit ที่ตั้งไว้แล้วบ้าง
# 2) หุ้นใน Watchlist ตัวไหนถึงราคาเป้าหมายที่ตั้งไว้แล้วบ้าง
# โดยใช้ "ราคาสด" แบบ real-time (delay ~15 นาทีจาก Yahoo Finance) แทนที่จะรอให้ Daily Scan ตอน
# 17:30 น. (หลังตลาดปิดแล้ว) ถึงจะรู้ว่าหุ้นเคยแตะราคาเป้าหมายระหว่างวันหรือเปล่า
#
# 🔧 ทำไมต้องแยกไฟล์นี้ออกมาจาก daily_scan.py:
# Daily Scan สแกนหุ้นทั้ง 494 ตัวแบบเต็มรูปแบบ เหมาะรันวันละครั้งพอ ถ้าเอามารันถี่ทุก 15 นาทีจะ
# ช้าเกินไปและเสี่ยงโดน Yahoo Finance จำกัดการเรียกข้อมูลจากการยิงคำขอถี่เกินไป สคริปต์นี้จึงเช็ค
# "เฉพาะหุ้นในพอร์ต/Watchlist ที่ตั้งราคาเป้าหมายไว้และยังไม่เคยแจ้งเตือน" เท่านั้น (จำนวนน้อยกว่า
# มาก) ทำให้รันได้เร็วและปลอดภัยกว่าการสแกนทั้งตลาด
#
# 🆕 ข้อมูล SL/TP และ Watchlist เป็นข้อมูลส่วนตัวของแต่ละคนล้วนๆ (ไม่มีส่วนกลางเหมือน Daily Scan)
# จึงส่งแจ้งเตือนแยกเฉพาะเจ้าของบัญชีนั้นๆ เท่านั้น ผ่าน Chat ID ของแต่ละคน (ใช้ Bot ตัวเดียวกันได้
# เพราะ Bot หนึ่งตัวส่งข้อความหาคนละ Chat ID ได้อยู่แล้ว)
# =============================================================
import os
import streamlit as st
from backend_functions import (
    check_portfolio_sl_tp_alerts_realtime,
    check_watchlist_price_alerts_realtime,
    send_telegram_message,
)

# รายชื่อ Google Sheet (ของแต่ละคน) ที่ต้องการเช็คให้
TARGET_SPREADSHEETS = ["MyStockData", "Nujiwealth"]

# 🆕 แผนผังเชื่อมชื่อ Google Sheet เข้ากับ Telegram Chat ID ของเจ้าของบัญชีนั้นๆ (ตัวเดียวกับที่ใช้
# ใน daily_scan.py)
SPREADSHEET_TELEGRAM_CHAT_IDS = {
    "MyStockData": os.environ.get("TELEGRAM_CHAT_ID"),
    "Nujiwealth": os.environ.get("TELEGRAM_CHAT_ID_PARTNER"),
}


def build_realtime_alert_message(sl_tp_alerts, watchlist_alerts):
    """สร้างข้อความแจ้งเตือนราคาแบบ real-time (SL/TP ในพอร์ต + ราคาเป้าหมายใน Watchlist) ของบัญชีเดียว สำหรับส่งผ่าน Telegram"""
    lines = ["⚡ <b>แจ้งเตือนราคาสด (Real-time)</b>"]

    if sl_tp_alerts:
        lines.append("\n🛡️ <b>ถึงจุด Stop Loss / Take Profit:</b>")
        for a in sl_tp_alerts:
            _type_label = "🔴 Stop Loss" if a['type'] == 'SL' else "🟢 Take Profit"
            lines.append(
                f"• {a['ticker']} — {_type_label}: ราคาปัจจุบัน {a['current_price']:,.2f} ฿ "
                f"(ต้นทุน {a['avg_price']:,.2f} ฿ | {a['pct_change']:+.2f}%)"
            )

    if watchlist_alerts:
        lines.append("\n🎯 <b>ราคาเป้าหมาย Watchlist ถึงแล้ว:</b>")
        for a in watchlist_alerts:
            _dir_label = "ลงมาถึง" if a['direction'] == 'below' else "ขึ้นมาถึง"
            lines.append(
                f"• {a['ticker']}: ราคาปัจจุบัน {a['current_price']:,.2f} ฿ "
                f"({_dir_label}เป้าหมาย {a['target_price']:,.2f} ฿)"
            )

    return "\n".join(lines)


def main():
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        print("ℹ️ ยังไม่ได้ตั้งค่า TELEGRAM_BOT_TOKEN ข้ามการเช็ครอบนี้ทั้งหมด")
        return

    print("⚡ กำลังเช็คจุด Stop Loss / Take Profit ในพอร์ต + ราคาเป้าหมาย Watchlist แบบ real-time...")
    for spreadsheet_name in TARGET_SPREADSHEETS:
        chat_id = SPREADSHEET_TELEGRAM_CHAT_IDS.get(spreadsheet_name)
        if not chat_id:
            print(f"ℹ️ ยังไม่ได้ตั้งค่า Telegram Chat ID ของ {spreadsheet_name} ข้ามการเช็คบัญชีนี้")
            continue

        st.session_state['active_sheet_name'] = spreadsheet_name
        sl_tp_alerts = check_portfolio_sl_tp_alerts_realtime(spreadsheet_name)
        watchlist_alerts = check_watchlist_price_alerts_realtime(spreadsheet_name)

        if not sl_tp_alerts and not watchlist_alerts:
            print(f"✅ {spreadsheet_name}: ไม่มีหุ้นตัวไหนถึงราคาเป้าหมายในรอบนี้ (ไม่ส่งข้อความ)")
            continue

        message = build_realtime_alert_message(sl_tp_alerts, watchlist_alerts)
        success, msg = send_telegram_message(bot_token, chat_id, message)
        print(f"{'✅' if success else '⚠️'} ส่งแจ้งเตือนให้ {spreadsheet_name}: {msg}")


if __name__ == "__main__":
    main()
