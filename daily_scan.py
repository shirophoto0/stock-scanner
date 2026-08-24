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
#
# 🆕 เพิ่มระบบแจ้งเตือนอัตโนมัติผ่าน Telegram หลังสแกนเสร็จ — สรุปหุ้นที่ผ่านเกณฑ์เด่นใหม่วันนี้
# (Trend Template ผ่านใหม่, RS Line เพิ่งตัดเส้น 0 ขึ้นวันนี้พอดี) + แจ้งเตือนหุ้นใน Watchlist ที่
# ราคาถึงเป้าหมายที่ตั้งไว้แล้ว ต้องตั้งค่า Environment Variables TELEGRAM_BOT_TOKEN และ
# TELEGRAM_CHAT_ID ก่อน (ผ่าน GitHub Secrets) ไม่งั้นจะข้ามขั้นตอนนี้ไปเงียบๆ
# (ยังคงสแกน+บันทึกข้อมูลได้ตามปกติ แค่ไม่ส่งแจ้งเตือน)
# =============================================================
import os
import numpy as np
import pandas as pd
from backend_functions import (
    load_and_calculate_stock_data_optimized,
    get_gsheet_client,
    get_cached_spreadsheet,
    send_telegram_message,
    check_watchlist_price_alerts,
)

# รายชื่อ Google Sheet (ของแต่ละคน) ที่ต้องการบันทึกผลสแกนลงไป
# ข้อมูลตลาดหุ้นเหมือนกันทุกบัญชี จึงบันทึกซ้ำให้ครบทุกชื่อในลิสต์นี้
TARGET_SPREADSHEETS = ["MyStockData", "Nujiwealth"]

# ใช้ชีตแรกในลิสต์เป็น "ตัวแทน" สำหรับเทียบข้อมูลเก่า-ใหม่ (ข้อมูลตลาดหุ้นเหมือนกันทุกบัญชีอยู่แล้ว
# ไม่จำเป็นต้องเทียบซ้ำทุกบัญชี)
REFERENCE_SPREADSHEET = TARGET_SPREADSHEETS[0]


def load_previous_scan(spreadsheet_name):
    """
    โหลดผลสแกนของ "เมื่อวาน" (ก่อนจะถูกเขียนทับด้วยผลสแกนวันนี้) ไว้เทียบหาหุ้นที่ผ่านเกณฑ์เด่น
    ใหม่วันนี้ คืนค่าเป็น DataFrame ว่างเปล่าถ้าโหลดไม่สำเร็จ (เช่น รันครั้งแรกยังไม่เคยมีข้อมูลเก่า)
    """
    try:
        client = get_gsheet_client()
        sheet = get_cached_spreadsheet(client, spreadsheet_name).worksheet('StockData')
        data = sheet.get_all_records()
        return pd.DataFrame(data) if data else pd.DataFrame()
    except Exception as e:
        print(f"⚠️ โหลดผลสแกนเก่าไม่สำเร็จ (ข้ามการเทียบหาเกณฑ์เด่นใหม่): {e}")
        return pd.DataFrame()


def find_notable_stocks(df_old, df_new):
    """
    เทียบผลสแกนเก่า-ใหม่ หาหุ้นที่ "เพิ่งผ่านเกณฑ์เด่น" วันนี้พอดี (ไม่ใช่ผ่านมาหลายวันแล้ว)
    คืนค่าเป็น dict {'trend_template': [...], 'rs_cross_up': [...], 'new_52w_high': [...]}
    """
    result = {'trend_template': [], 'rs_cross_up': [], 'new_52w_high': []}

    # 1. Trend Template ผ่านใหม่วันนี้ (เทียบกับเมื่อวาน — ต้องมีข้อมูลเก่าถึงจะเทียบได้)
    if not df_old.empty and 'Ticker' in df_old.columns and 'Trend_Template_Pass' in df_old.columns:
        old_pass_set = set(
            df_old[df_old['Trend_Template_Pass'].astype(str).str.lower() == 'true']['Ticker']
        )
        if 'Trend_Template_Pass' in df_new.columns:
            new_pass = df_new[df_new['Trend_Template_Pass'] == True]
            result['trend_template'] = [
                t for t in new_pass['Ticker'].tolist() if t not in old_pass_set
            ]

    # 2. RS Line เพิ่งตัดเส้น 0 ขึ้นวันนี้พอดี (ใช้คอลัมน์ "จำนวนวันที่อยู่เหนือเส้น 0" == 1 ได้เลย
    # ไม่ต้องเทียบกับเมื่อวาน เพราะค่านี้คำนวณมาให้พร้อมอยู่แล้วว่าตัดขึ้นมากี่วันแล้ว)
    if 'ตัดเส้น0ขึ้นมาแล้ว(วัน)' in df_new.columns:
        cross_today = df_new[
            pd.to_numeric(df_new['ตัดเส้น0ขึ้นมาแล้ว(วัน)'], errors='coerce') == 1
        ]
        result['rs_cross_up'] = cross_today['Ticker'].tolist()

    # 3. เพิ่งทำจุดสูงสุดใหม่ 52 สัปดาห์วันนี้พอดี (คำนวณมาให้พร้อมแล้วว่าราคาวันนี้สูงกว่าจุดสูงสุด
    # เดิมของ 250 วันก่อนหน้าจริงไหม ไม่ต้องเทียบกับเมื่อวานเพิ่ม)
    if 'Is_New_52W_High_Today' in df_new.columns:
        new_high_today = df_new[df_new['Is_New_52W_High_Today'] == True]
        result['new_52w_high'] = new_high_today['Ticker'].tolist()

    return result


def build_telegram_message(notable, watchlist_alerts):
    """สร้างข้อความสรุปหุ้นที่ผ่านเกณฑ์เด่นใหม่วันนี้ + แจ้งเตือนราคาเป้าหมายที่ถึงแล้ว สำหรับส่งผ่าน Telegram"""
    lines = ["📊 <b>สรุปผลสแกนหุ้นวันนี้</b>"]

    if notable['trend_template']:
        lines.append(f"\n✅ <b>ผ่าน Trend Template ใหม่วันนี้ ({len(notable['trend_template'])} ตัว):</b>")
        lines.append(", ".join(notable['trend_template']))

    if notable['rs_cross_up']:
        lines.append(f"\n⭐ <b>RS Line เพิ่งตัดเส้น 0 ขึ้นวันนี้ ({len(notable['rs_cross_up'])} ตัว):</b>")
        lines.append(", ".join(notable['rs_cross_up']))

    if notable['new_52w_high']:
        lines.append(f"\n🚀 <b>ทำจุดสูงสุดใหม่ 52 สัปดาห์วันนี้ ({len(notable['new_52w_high'])} ตัว):</b>")
        lines.append(", ".join(notable['new_52w_high']))

    # 🆕 แจ้งเตือนราคาเป้าหมายใน Watchlist ที่ถึงแล้ว (แยกตามบัญชี เพราะ Watchlist เป็นข้อมูล
    # ส่วนตัวของแต่ละคน ไม่เหมือนผลสแกนหุ้นที่ใช้ร่วมกัน)
    for spreadsheet_name, alerts in watchlist_alerts.items():
        if alerts:
            lines.append(f"\n🎯 <b>ราคาเป้าหมายถึงแล้ว ({spreadsheet_name}):</b>")
            for a in alerts:
                _dir_label = "ลงมาถึง" if a['direction'] == 'below' else "ขึ้นมาถึง"
                lines.append(
                    f"• {a['ticker']}: ราคาปัจจุบัน {a['current_price']:,.2f} ฿ "
                    f"({_dir_label}เป้าหมาย {a['target_price']:,.2f} ฿)"
                )

    if (
        not notable['trend_template'] and not notable['rs_cross_up']
        and not notable['new_52w_high'] and not any(watchlist_alerts.values())
    ):
        lines.append("\nวันนี้ไม่มีหุ้นตัวใหม่ที่ผ่านเกณฑ์เด่น หรือถึงราคาเป้าหมายเป็นพิเศษครับ")

    return "\n".join(lines)


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


def send_daily_alert(df_result):
    """
    ส่งแจ้งเตือนสรุปหุ้นเด่นวันนี้ + ราคาเป้าหมายใน Watchlist ที่ถึงแล้ว ผ่าน Telegram ถ้าตั้งค่า
    TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID ไว้แล้ว (ผ่าน Environment Variables / GitHub Secrets)
    ถ้ายังไม่ตั้งค่า จะข้ามขั้นตอนนี้ไปเงียบๆ
    """
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        print("ℹ️ ยังไม่ได้ตั้งค่า TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID ข้ามการส่งแจ้งเตือนวันนี้")
        return

    print("🔍 กำลังเทียบหาหุ้นที่ผ่านเกณฑ์เด่นใหม่วันนี้...")
    df_old = load_previous_scan(REFERENCE_SPREADSHEET)
    notable = find_notable_stocks(df_old, df_result)

    # 🆕 เช็คราคาเป้าหมายใน Watchlist ของทุกบัญชี (Watchlist เป็นข้อมูลส่วนตัวของแต่ละคน
    # ต่างจากผลสแกนหุ้นที่ใช้ร่วมกัน จึงต้องเช็คแยกทีละบัญชี)
    print("🎯 กำลังเช็คราคาเป้าหมายใน Watchlist ของทุกบัญชี...")
    watchlist_alerts = {}
    for spreadsheet_name in TARGET_SPREADSHEETS:
        watchlist_alerts[spreadsheet_name] = check_watchlist_price_alerts(spreadsheet_name, df_result)

    message = build_telegram_message(notable, watchlist_alerts)

    success, msg = send_telegram_message(bot_token, chat_id, message)
    print(f"{'✅' if success else '⚠️'} {msg}")


def main():
    print("🔄 เริ่มสแกนข้อมูลหุ้นทั้งหมด...")
    df_result = load_and_calculate_stock_data_optimized()

    if df_result is None or df_result.empty:
        print("❌ สแกนไม่สำเร็จ หรือไม่มีข้อมูลหุ้นเลย ยกเลิกการบันทึก")
        return

    print(f"📊 สแกนสำเร็จ {len(df_result)} ตัว กำลังบันทึกลง {len(TARGET_SPREADSHEETS)} ชีต...")

    # 🔧 สำคัญ: ต้องหาหุ้นเด่นใหม่ "ก่อน" ที่จะเขียนทับข้อมูลเก่าเท่านั้น เพราะหลังบันทึกลงชีตแล้ว
    # ข้อมูล "เมื่อวาน" จะหายไปเลย (บันทึกด้วยการเขียนทับทั้งหมด ไม่ใช่ต่อท้าย) จึงต้องเรียก
    # send_daily_alert() ก่อน save_scan_result() เสมอ
    send_daily_alert(df_result)

    for spreadsheet_name in TARGET_SPREADSHEETS:
        try:
            save_scan_result(df_result, spreadsheet_name)
        except Exception as e:
            # ถ้าชีตใดชีตหนึ่งบันทึกไม่สำเร็จ ให้ข้ามไปทำชีตถัดไปต่อ ไม่ให้ทั้ง job ล้มเหลวไปด้วย
            print(f"⚠️ บันทึกลง {spreadsheet_name} ไม่สำเร็จ: {e}")

    print("🏁 จบการทำงานสแกนหุ้นรายวัน")


if __name__ == "__main__":
    main()
