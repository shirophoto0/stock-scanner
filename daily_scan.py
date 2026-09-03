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
# (Trend Template ผ่านใหม่, RS Line เพิ่งตัดเส้น 0 ขึ้นวันนี้พอดี, ทำจุดสูงสุดใหม่ 52 สัปดาห์) ส่งให้
# ทั้ง 2 บัญชีเหมือนกัน (ข้อมูลตลาดหุ้นเป็นข้อมูลทั่วไป ไม่ใช่ข้อมูลส่วนตัวของใครคนใดคนหนึ่ง) ส่วน
# แจ้งเตือนหุ้นใน Watchlist ที่ราคาถึงเป้าหมาย + จุด Stop Loss / Take Profit จะส่งเฉพาะให้เจ้าของ
# บัญชีนั้นๆ เท่านั้น (ข้อมูลส่วนตัวของแต่ละคน) ต้องตั้งค่า Environment Variables TELEGRAM_BOT_TOKEN,
# TELEGRAM_CHAT_ID (ของคุณ), TELEGRAM_CHAT_ID_PARTNER (ของแฟน) ก่อน (ผ่าน GitHub Secrets) — ถ้า
# บัญชีไหนยังไม่ได้ตั้งค่า Chat ID จะข้ามการแจ้งเตือนเฉพาะบัญชีนั้นไปเงียบๆ (ยังคงสแกน+บันทึกข้อมูล
# ได้ตามปกติ แค่ไม่ส่งแจ้งเตือนให้บัญชีที่ยังไม่พร้อม)
# =============================================================
import os
import numpy as np
import pandas as pd
import streamlit as st
from backend_functions import (
    load_and_calculate_stock_data_optimized,
    get_gsheet_client,
    get_cached_spreadsheet,
    send_telegram_message,
    check_watchlist_price_alerts,
    check_portfolio_sl_tp_alerts,
    log_signal_history,
    resolve_pending_signals,
    cleanup_old_signals,
)

# รายชื่อ Google Sheet (ของแต่ละคน) ที่ต้องการบันทึกผลสแกนลงไป
# ข้อมูลตลาดหุ้นเหมือนกันทุกบัญชี จึงบันทึกซ้ำให้ครบทุกชื่อในลิสต์นี้
TARGET_SPREADSHEETS = ["MyStockData", "Nujiwealth"]

# 🆕 แผนผังเชื่อมชื่อ Google Sheet เข้ากับ Telegram Chat ID ของเจ้าของบัญชีนั้นๆ (อ่านจาก
# Environment Variables ที่ตั้งค่าผ่าน GitHub Secrets) ใช้ Bot ตัวเดียวกันทั้งคู่ได้เลย เพราะ Bot
# หนึ่งตัวส่งข้อความหาคนละ Chat ID ได้อยู่แล้วโดยไม่ต้องสร้าง Bot แยก
SPREADSHEET_TELEGRAM_CHAT_IDS = {
    "MyStockData": os.environ.get("TELEGRAM_CHAT_ID"),
    "Nujiwealth": os.environ.get("TELEGRAM_CHAT_ID_PARTNER"),
}

# ใช้ชีตแรกในลิสต์เป็น "ตัวแทน" สำหรับเทียบข้อมูลเก่า-ใหม่ (ข้อมูลตลาดหุ้นเหมือนกันทุกบัญชีอยู่แล้ว
# ไม่จำเป็นต้องเทียบซ้ำทุกบัญชี)
REFERENCE_SPREADSHEET = TARGET_SPREADSHEETS[0]


def load_previous_scan(spreadsheet_name):
    """
    โหลดผลสแกนของ "เมื่อวาน" (ก่อนจะถูกเขียนทับด้วยผลสแกนวันนี้) ไว้เทียบหาหุ้นที่ผ่านเกณฑ์เด่น
    ใหม่วันนี้ คืนค่าเป็น DataFrame ว่างเปล่าถ้าโหลดไม่สำเร็จ (เช่น รันครั้งแรกยังไม่เคยมีข้อมูลเก่า)
    """
    try:
        st.session_state['active_sheet_name'] = spreadsheet_name
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
    คืนค่าเป็น dict {'trend_template': [...], 'rs_cross_up': [...], 'new_52w_high': [...],
    'volume_spike': [...], 'golden_cross': [...], 'rsi_oversold_bounce': [...], 'vcp_breakout': [...]}
    """
    result = {
        'trend_template': [], 'rs_cross_up': [], 'new_52w_high': [],
        'volume_spike': [], 'golden_cross': [], 'rsi_oversold_bounce': [], 'vcp_breakout': [],
    }

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

    # 🆕 4. Volume พุ่งผิดปกติวันนี้ (Is_Volume_Spike เป็นค่ารายวันอยู่แล้ว ไม่ใช่สถานะสะสมหลายวัน
    # แบบ Trend Template จึงไม่ต้องเทียบกับเมื่อวานเพิ่ม เช็คแค่ค่าวันนี้ก็ถือว่า "เพิ่งเกิด" แล้ว)
    if 'Is_Volume_Spike' in df_new.columns:
        volume_spike_today = df_new[df_new['Is_Volume_Spike'] == True]
        result['volume_spike'] = volume_spike_today['Ticker'].tolist()

    # 🆕 5-7. Golden Cross / RSI ดีดกลับจาก Oversold / VCP Breakout — คำนวณเทียบ "เมื่อวาน vs วันนี้"
    # มาให้พร้อมแล้วตั้งแต่ขั้นตอนสแกน (ใช้ข้อมูลราคาย้อนหลังชุดเดียวกัน ไม่ต้องพึ่งข้อมูลสแกนเก่า
    # จากภายนอกเหมือน Trend Template) เช็คแค่ค่าวันนี้ก็พอ
    if 'Is_Golden_Cross_Today' in df_new.columns:
        result['golden_cross'] = df_new[df_new['Is_Golden_Cross_Today'] == True]['Ticker'].tolist()
    if 'Is_RSI_Oversold_Bounce_Today' in df_new.columns:
        result['rsi_oversold_bounce'] = df_new[df_new['Is_RSI_Oversold_Bounce_Today'] == True]['Ticker'].tolist()
    if 'Is_VCP_Breakout_Today' in df_new.columns:
        result['vcp_breakout'] = df_new[df_new['Is_VCP_Breakout_Today'] == True]['Ticker'].tolist()

    return result


def build_shared_notable_message(notable):
    """
    🔧 สร้างข้อความส่วน "กลาง" (Trend Template / RS Line / 52W High) ที่ส่งเหมือนกันให้ทุกบัญชี
    แยกออกมาจาก build_telegram_message() เดิม เพื่อให้ประกอบรวมกับข้อความส่วนตัวของแต่ละบัญชีได้
    """
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

    if notable['volume_spike']:
        lines.append(f"\n📢 <b>Volume พุ่งผิดปกติวันนี้ ({len(notable['volume_spike'])} ตัว):</b>")
        lines.append(", ".join(notable['volume_spike']))

    if notable['golden_cross']:
        lines.append(f"\n🌟 <b>Golden Cross วันนี้ ({len(notable['golden_cross'])} ตัว):</b>")
        lines.append(", ".join(notable['golden_cross']))

    if notable['rsi_oversold_bounce']:
        lines.append(f"\n🔄 <b>RSI ดีดกลับจาก Oversold วันนี้ ({len(notable['rsi_oversold_bounce'])} ตัว):</b>")
        lines.append(", ".join(notable['rsi_oversold_bounce']))

    if notable['vcp_breakout']:
        lines.append(f"\n🎯 <b>VCP Breakout วันนี้ ({len(notable['vcp_breakout'])} ตัว):</b>")
        lines.append(", ".join(notable['vcp_breakout']))

    if not any(notable.values()):
        lines.append("\nวันนี้ไม่มีหุ้นตัวใหม่ที่ผ่านเกณฑ์เด่นเป็นพิเศษครับ")

    return "\n".join(lines)


def build_personal_alerts_message(watchlist_alerts, portfolio_sl_tp_alerts):
    """
    🔧 สร้างข้อความส่วน "ส่วนตัว" (Watchlist + Stop Loss/Take Profit) ของบัญชีเดียว คืนค่าเป็น
    string ว่างเปล่าถ้าไม่มีอะไรจะแจ้ง (ผู้เรียกจะได้รู้ว่าไม่ต้องต่อท้ายเข้ากับข้อความส่วนกลาง)
    """
    lines = []

    if watchlist_alerts:
        lines.append(f"\n🎯 <b>ราคาเป้าหมาย Watchlist ถึงแล้ว:</b>")
        for a in watchlist_alerts:
            _dir_label = "ลงมาถึง" if a['direction'] == 'below' else "ขึ้นมาถึง"
            lines.append(
                f"• {a['ticker']}: ราคาปัจจุบัน {a['current_price']:,.2f} ฿ "
                f"({_dir_label}เป้าหมาย {a['target_price']:,.2f} ฿)"
            )

    if portfolio_sl_tp_alerts:
        lines.append(f"\n🛡️ <b>ถึงจุด Stop Loss / Take Profit แล้ว:</b>")
        for a in portfolio_sl_tp_alerts:
            _type_label = "🔴 Stop Loss" if a['type'] == 'SL' else "🟢 Take Profit"
            lines.append(
                f"• {a['ticker']} — {_type_label}: ราคาปัจจุบัน {a['current_price']:,.2f} ฿ "
                f"(ต้นทุน {a['avg_price']:,.2f} ฿ | {a['pct_change']:+.2f}%)"
            )

    return "\n".join(lines)


def save_scan_result(df, spreadsheet_name):
    """
    บันทึกผลสแกนลงชีต StockData ของ Google Sheet ที่ระบุ
    เขียนแบบไม่พึ่งพา st.session_state เลย (ต่างจาก save_to_gsheet() ในหน้าเว็บที่อ่านชื่อชีต
    จาก session_state ของผู้ใช้ที่ login อยู่ ซึ่งไม่มีค่าในการรันแบบอัตโนมัตินี้)
    🔧 แก้บั๊ก: เดิมเขียนทับด้วย sheet.update() ตั้งแต่ A1 ลงไปเฉยๆ โดยไม่ได้ล้างชีตก่อน ทำให้ถ้า
    รอบนี้มีจำนวนแถวน้อยกว่ารอบก่อน (เช่น ตอนลดจำนวนหุ้นจาก 494 เหลือ 472 ตัว) แถวเก่าที่เกินมา
    จะค้างอยู่ในชีตต่อไปเฉยๆ กลายเป็นข้อมูลซ้ำซ้อนกับแถวใหม่ (Ticker ซ้ำกัน) จนทำให้หน้าเว็บที่
    แปลงข้อมูลเป็น dict โดยอิงจาก Ticker พังทันที (ValueError: index must be unique) ตอนนี้ล้าง
    ชีตทั้งหมดก่อนเขียนข้อมูลใหม่ทุกครั้ง รับประกันว่าไม่มีแถวเก่าตกค้างอีกต่อไป
    """
    st.session_state['active_sheet_name'] = spreadsheet_name
    client = get_gsheet_client()
    sheet = get_cached_spreadsheet(client, spreadsheet_name).worksheet('StockData')
    df_clean = df.replace([np.inf, -np.inf], 0).fillna("")
    data_to_write = [df_clean.columns.tolist()] + df_clean.values.tolist()
    sheet.clear()
    sheet.update(range_name='A1', values=data_to_write)
    print(f"✅ บันทึกข้อมูลลง {spreadsheet_name} สำเร็จ ({len(df_clean)} แถว)")


def send_daily_alert(df_result, notable):
    """
    ส่งแจ้งเตือนสรุปหุ้นเด่นวันนี้ (ส่วนกลาง ส่งให้ทุกบัญชีเหมือนกัน) + ราคาเป้าหมาย Watchlist/
    Stop Loss/Take Profit (ส่วนตัว ส่งเฉพาะเจ้าของบัญชีนั้นๆ) ผ่าน Telegram — วนส่งทีละบัญชีตาม
    SPREADSHEET_TELEGRAM_CHAT_IDS ถ้าบัญชีไหนยังไม่ได้ตั้งค่า Chat ID จะข้ามการแจ้งเตือนเฉพาะ
    บัญชีนั้นไปเงียบๆ (บัญชีอื่นยังได้รับตามปกติ)
    🔧 ปรับปรุง: รับ notable เป็นพารามิเตอร์แทนการคำนวณเองข้างใน เพราะตอนนี้ main() ต้องใช้ notable
    ตัวเดียวกันนี้ต่อสำหรับบันทึกประวัติสัญญาณ (Backtest) ด้วย ไม่ต้องคำนวณซ้ำ 2 ที่
    """
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        print("ℹ️ ยังไม่ได้ตั้งค่า TELEGRAM_BOT_TOKEN ข้ามการส่งแจ้งเตือนวันนี้ทั้งหมด")
        return

    shared_message = build_shared_notable_message(notable)

    for spreadsheet_name in TARGET_SPREADSHEETS:
        chat_id = SPREADSHEET_TELEGRAM_CHAT_IDS.get(spreadsheet_name)
        if not chat_id:
            print(f"ℹ️ ยังไม่ได้ตั้งค่า Telegram Chat ID ของ {spreadsheet_name} ข้ามการแจ้งเตือนบัญชีนี้")
            continue

        print(f"🎯 กำลังเช็คราคาเป้าหมาย Watchlist + จุด SL/TP ของ {spreadsheet_name}...")
        st.session_state['active_sheet_name'] = spreadsheet_name
        watchlist_alerts = check_watchlist_price_alerts(spreadsheet_name, df_result)
        sl_tp_alerts = check_portfolio_sl_tp_alerts(spreadsheet_name, df_result)
        personal_message = build_personal_alerts_message(watchlist_alerts, sl_tp_alerts)

        full_message = shared_message + ("\n" + personal_message if personal_message else "")
        success, msg = send_telegram_message(bot_token, chat_id, full_message)
        print(f"{'✅' if success else '⚠️'} ส่งแจ้งเตือนให้ {spreadsheet_name}: {msg}")


def main():
    print("🔄 เริ่มสแกนข้อมูลหุ้นทั้งหมด...")
    df_result = load_and_calculate_stock_data_optimized()

    if df_result is None or df_result.empty:
        print("❌ สแกนไม่สำเร็จ หรือไม่มีข้อมูลหุ้นเลย ยกเลิกการบันทึก")
        return

    print(f"📊 สแกนสำเร็จ {len(df_result)} ตัว กำลังบันทึกลง {len(TARGET_SPREADSHEETS)} ชีต...")

    # 🔧 สำคัญ: ต้องหาหุ้นเด่นใหม่ "ก่อน" ที่จะเขียนทับข้อมูลเก่าเท่านั้น เพราะหลังบันทึกลงชีตแล้ว
    # ข้อมูล "เมื่อวาน" จะหายไปเลย (บันทึกด้วยการเขียนทับทั้งหมด ไม่ใช่ต่อท้าย) จึงต้องคำนวณ notable
    # ก่อน save_scan_result() เสมอ
    print("🔍 กำลังเทียบหาหุ้นที่ผ่านเกณฑ์เด่นใหม่วันนี้...")
    df_old = load_previous_scan(REFERENCE_SPREADSHEET)
    notable = find_notable_stocks(df_old, df_result)

    send_daily_alert(df_result, notable)

    # 🆕 ระบบ Backtest — บันทึกหุ้นที่มีสัญญาณเด่นวันนี้ไว้เป็นประวัติ + เช็คผลตอบแทนของสัญญาณเก่า
    # ที่ครบกำหนด 30/60/90 วันแล้ว + ล้างข้อมูลเก่าเกิน 5 ปีทิ้ง (ใช้ REFERENCE_SPREADSHEET เป็น
    # ที่เก็บกลางเพียงที่เดียว เพราะเป็นข้อมูลตลาดหุ้นทั่วไป ไม่ใช่ข้อมูลส่วนตัวของใครคนใดคนหนึ่ง
    # เหมือนกับ StockData)
    print("📝 กำลังบันทึกประวัติสัญญาณสำหรับ Backtest...")
    st.session_state['active_sheet_name'] = REFERENCE_SPREADSHEET
    price_map = dict(zip(df_result['Ticker'], df_result['ราคาล่าสุด']))
    _logged = log_signal_history(REFERENCE_SPREADSHEET, notable, price_map)
    print(f"✅ บันทึกสัญญาณใหม่ {_logged} รายการ")

    print("🔄 กำลังเช็คผลตอบแทนของสัญญาณเก่าที่ครบกำหนด 30/60/90 วันแล้ว...")
    _resolved = resolve_pending_signals(REFERENCE_SPREADSHEET)
    print(f"✅ อัปเดตผลตอบแทน {_resolved} ช่อง")

    print("🧹 กำลังล้างข้อมูลสัญญาณเก่าเกิน 5 ปีทิ้ง...")
    _cleaned = cleanup_old_signals(REFERENCE_SPREADSHEET, retention_years=5)
    if _cleaned > 0:
        print(f"✅ ลบข้อมูลเก่าเกิน 5 ปีทิ้งแล้ว {_cleaned} รายการ")

    for spreadsheet_name in TARGET_SPREADSHEETS:
        try:
            save_scan_result(df_result, spreadsheet_name)
        except Exception as e:
            # ถ้าชีตใดชีตหนึ่งบันทึกไม่สำเร็จ ให้ข้ามไปทำชีตถัดไปต่อ ไม่ให้ทั้ง job ล้มเหลวไปด้วย
            print(f"⚠️ บันทึกลง {spreadsheet_name} ไม่สำเร็จ: {e}")

    print("🏁 จบการทำงานสแกนหุ้นรายวัน")


if __name__ == "__main__":
    main()
