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
# =============================================================
import os
from backend_functions import (
    check_portfolio_sl_tp_alerts_realtime,
    check_watchlist_price_alerts_realtime,
    send_telegram_message,
)

# รายชื่อ Google Sheet (ของแต่ละคน) ที่ต้องการเช็คให้
TARGET_SPREADSHEETS = ["MyStockData", "Nujiwealth"]


def build_realtime_alert_message(sl_tp_alerts, watchlist_alerts):
    """สร้างข้อความแจ้งเตือนราคาแบบ real-time (SL/TP ในพอร์ต + ราคาเป้าหมายใน Watchlist) สำหรับส่งผ่าน Telegram"""
    lines = ["⚡ <b>แจ้งเตือนราคาสด (Real-time)</b>"]

    for spreadsheet_name, alerts in sl_tp_alerts.items():
        if alerts:
            lines.append(f"\n🛡️ <b>ถึงจุด Stop Loss / Take Profit ({spreadsheet_name}):</b>")
            for a in alerts:
                _type_label = "🔴 Stop Loss" if a['type'] == 'SL' else "🟢 Take Profit"
                lines.append(
                    f"• {a['ticker']} — {_type_label}: ราคาปัจจุบัน {a['current_price']:,.2f} ฿ "
                    f"(ต้นทุน {a['avg_price']:,.2f} ฿ | {a['pct_change']:+.2f}%)"
                )

    for spreadsheet_name, alerts in watchlist_alerts.items():
        if alerts:
            lines.append(f"\n🎯 <b>ราคาเป้าหมาย Watchlist ถึงแล้ว ({spreadsheet_name}):</b>")
            for a in alerts:
                _dir_label = "ลงมาถึง" if a['direction'] == 'below' else "ขึ้นมาถึง"
                lines.append(
                    f"• {a['ticker']}: ราคาปัจจุบัน {a['current_price']:,.2f} ฿ "
                    f"({_dir_label}เป้าหมาย {a['target_price']:,.2f} ฿)"
                )

    return "\n".join(lines)


def main():
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        print("ℹ️ ยังไม่ได้ตั้งค่า TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID ข้ามการเช็ครอบนี้")
        return

    print("⚡ กำลังเช็คจุด Stop Loss / Take Profit ในพอร์ต + ราคาเป้าหมาย Watchlist แบบ real-time...")
    sl_tp_alerts = {}
    watchlist_alerts = {}
    for spreadsheet_name in TARGET_SPREADSHEETS:
        sl_tp_alerts[spreadsheet_name] = check_portfolio_sl_tp_alerts_realtime(spreadsheet_name)
        watchlist_alerts[spreadsheet_name] = check_watchlist_price_alerts_realtime(spreadsheet_name)

    if not any(sl_tp_alerts.values()) and not any(watchlist_alerts.values()):
        print("✅ ไม่มีหุ้นตัวไหนถึงราคาเป้าหมายในรอบนี้ (ไม่ส่งข้อความ เพื่อไม่ให้รบกวนบ่อยเกินไป)")
        return

    message = build_realtime_alert_message(sl_tp_alerts, watchlist_alerts)
    success, msg = send_telegram_message(bot_token, chat_id, message)
    print(f"{'✅' if success else '⚠️'} {msg}")


if __name__ == "__main__":
    main()
