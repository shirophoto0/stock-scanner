# =============================================================
# tab_watchlist.py
# ⭐ แท็บ Watchlist (สำหรับเทรด) — เก็บติดตามหุ้นที่สนใจ แยกจากพอร์ตจริงโดยสิ้นเชิง
# แยกออกมาจาก tab_stock.py เดิม (ย้ายไปอยู่กลุ่ม "สแกนหุ้น" ในเมนูใหม่) เพราะส่วนนี้ทำงานอิสระ
# จาก Portfolio โดยสมบูรณ์ ไม่ได้อ้างอิงข้อมูลพอร์ตที่ถืออยู่จริงเลย (ต่างจาก SL/TP ที่ยังคงอยู่กับ
# แท็บ "หุ้น (Stock)" เดิม เพราะผูกกับหุ้นที่ถืออยู่ในพอร์ตจริง ไม่ใช่ฟีเจอร์ของ Watchlist)
# =============================================================
import streamlit as st
from backend_functions import (
    load_from_gsheet, load_watchlist, remove_from_watchlist,
    update_watchlist_target, add_to_watchlist,
)
from theme import get_theme_colors


def render_tab_watchlist():
    st.markdown("### ⭐ หุ้นที่สนใจ (Watchlist)")
    st.caption("เก็บติดตามหุ้นที่สนใจไว้ดูเฉยๆ ไม่ต้องซื้อจริง แยกออกจากพอร์ตจริงโดยสิ้นเชิง")

    # ดึงราคา/RSI/RS_Line ปัจจุบันจากข้อมูลสแกนล่าสุด — ย้ายมาโหลดก่อนตรงนี้ (เดิมโหลดทีหลัง
    # เฉพาะตอนมีรายการอยู่แล้ว) เพราะตอนนี้ต้องใช้ตั้งแต่ช่องพิมพ์ชื่อหุ้นเองด้านล่างด้วย
    try:
        df_scan_latest = load_from_gsheet()
    except Exception:
        df_scan_latest = None

    _scan_map = {}
    if df_scan_latest is not None and not df_scan_latest.empty and 'Ticker' in df_scan_latest.columns:
        # 🔧 แก้บั๊ก: เดิม set_index('Ticker') แล้วแปลงเป็น dict ตรงๆ พังทันทีถ้ามีหุ้นชื่อซ้ำกัน
        # มากกว่า 1 แถวในชีต StockData (ValueError: DataFrame index must be unique) ซึ่งอาจ
        # เกิดจากการสแกนบางรอบที่ไม่สมบูรณ์ ตอนนี้ตัดแถวที่ซ้ำออกก่อนเสมอ (เก็บแถวสุดท้ายไว้
        # เพราะเป็นข้อมูลล่าสุด) กันไม่ให้แอปพังจากข้อมูลซ้ำแบบนี้อีก
        df_scan_latest = df_scan_latest.drop_duplicates(subset='Ticker', keep='last')
        _scan_map = df_scan_latest.set_index('Ticker').to_dict('index')

    # 🆕 เพิ่มหุ้นเข้า Watchlist ด้วยการพิมพ์ชื่อเองได้โดยตรง (นอกจากกดปุ่ม "⭐ เพิ่มเข้า Watchlist"
    # จากตารางผลการสแกนในแท็บวิเคราะห์กราฟเทคนิคัล) ทำงานแบบเดียวกันทุกประการ แค่ไม่ต้องไปคลิก
    # เลือกจากตารางก่อน
    # 🔧 แก้บั๊ก: เดิม text_input อยู่นอกฟอร์ม พิมพ์ชื่อหุ้นทีละตัวอักษรแล้วหน้าเว็บรันใหม่ทันที
    # (ซ้ำร้ายกว่านั้น expander นี้ยังปิดกลับเองทุกครั้งที่รันซ้ำด้วย เพราะ expanded=False ตั้ง
    # ค่าคงที่ไว้) ตอนนี้ครอบด้วย st.form() แก้ได้ทั้ง 2 ปัญหาพร้อมกัน เพราะพิมพ์ในฟอร์มจะไม่
    # trigger rerun เลยจนกว่าจะกดปุ่ม
    with st.expander("➕ พิมพ์ชื่อหุ้นเพิ่มเข้า Watchlist เอง", expanded=False):
        with st.form("manual_watchlist_form"):
            _wc_add_col1, _wc_add_col2 = st.columns([3, 1])
            _manual_ticker_raw = _wc_add_col1.text_input(
                "ชื่อหุ้น (Ticker)", placeholder="เช่น PTT, AOT, CPALL", key="manual_watchlist_ticker"
            )
            _manual_add_submitted = _wc_add_col2.form_submit_button("⭐ เพิ่มเข้า Watchlist", use_container_width=True)

        if _manual_add_submitted:
            _manual_ticker = _manual_ticker_raw.strip().upper()
            if not _manual_ticker:
                st.warning("กรุณาพิมพ์ชื่อหุ้นก่อนครับ")
            else:
                _scan_info_manual = _scan_map.get(_manual_ticker, {})
                _price_manual = float(_scan_info_manual.get('ราคาล่าสุด', 0) or 0)
                _success, _msg = add_to_watchlist(_manual_ticker, _price_manual)
                if _success:
                    st.success(_msg)
                    st.rerun()
                else:
                    st.warning(_msg)

    watchlist_data = load_watchlist()

    if not watchlist_data:
        st.info(
            "ยังไม่มีหุ้นใน Watchlist ครับ — พิมพ์ชื่อหุ้นเพิ่มเองด้านบนได้เลย หรือไปที่แท็บ "
            "\"วิเคราะห์กราฟเทคนิคัล\" คลิกเลือกหุ้นที่สนใจจากตารางผลการสแกน แล้วกดปุ่ม "
            "\"⭐ เพิ่มเข้า Watchlist\""
        )
        return

    _tc = get_theme_colors()
    for item in watchlist_data:
        _ticker = str(item.get('Ticker', '')).strip().upper()
        _price_added = float(item.get('Price_When_Added', 0) or 0)
        _date_added = item.get('Date_Added', '-')
        _note = item.get('Note', '')

        _scan_info = _scan_map.get(_ticker, {})
        _price_now = float(_scan_info.get('ราคาล่าสุด', 0) or 0)
        _rsi_now = _scan_info.get('RSI_14', None)
        _rs_line_now = _scan_info.get('RS_Line', None)

        _pct_change = ((_price_now - _price_added) / _price_added * 100) if _price_added > 0 and _price_now > 0 else None

        with st.container(border=True):
            _wc1, _wc2, _wc3, _wc4, _wc5, _wc6 = st.columns([1.5, 1, 1, 1, 0.5, 0.5])
            _wc1.markdown(f"**⭐ {_ticker}**")
            _wc1.caption(f"เพิ่มเมื่อ {_date_added}" + (f" • {_note}" if _note else ""))

            _wc2.metric("ราคาตอนเพิ่ม", f"{_price_added:,.2f} ฿" if _price_added > 0 else "N/A")

            if _price_now > 0:
                _wc3.metric(
                    "ราคาปัจจุบัน", f"{_price_now:,.2f} ฿",
                    f"{_pct_change:+.2f}%" if _pct_change is not None else None
                )
            else:
                _wc3.metric("ราคาปัจจุบัน", "รอข้อมูล Daily Scan")

            _wc4.metric("RSI_14", f"{float(_rsi_now):.1f}" if _rsi_now not in (None, "") else "-")

            # 🆕 ไอคอนลิงก์ไปดูกราฟเต็มรูปแบบที่ TradingView (เปิดแท็บใหม่)
            with _wc5:
                st.markdown(
                    f'<a href="https://www.tradingview.com/symbols/SET-{_ticker}/" target="_blank" '
                    f'style="text-decoration:none;font-size:1.5em;" title="ดูกราฟ {_ticker} ที่ TradingView">📈</a>',
                    unsafe_allow_html=True
                )

            if _wc6.button("🗑️", key=f"del_wl_{_ticker}", help=f"ลบ {_ticker} ออกจาก Watchlist"):
                _success, _msg = remove_from_watchlist(_ticker)
                if _success:
                    st.success(_msg)
                    st.rerun()
                else:
                    st.warning(_msg)

            # 🆕 ตั้งราคาเป้าหมาย + ทิศทาง สำหรับระบบแจ้งเตือนอัตโนมัติผ่าน Telegram
            # (เช็คทุกวันตอน Daily Scan ทำงาน) แสดงสถานะเป้าหมายปัจจุบันไว้ด้วยถ้ามีการตั้งไว้
            _target_price = item.get('Target_Price')
            _target_dir = str(item.get('Target_Direction', '')).strip().lower()
            _alert_sent = str(item.get('Alert_Sent', '')).strip().upper() == 'TRUE'
            if _target_price:
                _dir_label = "ลงมาถึง" if _target_dir == 'below' else "ขึ้นมาถึง"
                _status_label = " (แจ้งเตือนไปแล้ว)" if _alert_sent else " (รอเช็คทุกวัน)"
                st.caption(f"🎯 ราคาเป้าหมายปัจจุบัน: {_dir_label} {float(_target_price):,.2f} ฿{_status_label}")

            # 🔧 แก้บั๊ก: เดิม _new_target/_new_dir อยู่นอกฟอร์ม พิมพ์ตัวเลขทีละตัวแล้วหน้าเว็บ
            # รันใหม่ทันที (expander นี้ก็ปิดกลับเองทุกครั้งด้วย เพราะ expanded ไม่ได้ผูกกับ
            # session_state) ตอนนี้ครอบด้วย st.form() แก้ได้ทั้ง 2 ปัญหาพร้อมกัน
            with st.expander(f"🎯 ตั้ง/แก้ราคาเป้าหมายแจ้งเตือน — {_ticker}"):
                with st.form(f"target_form_{_ticker}"):
                    _tp_col1, _tp_col2, _tp_col3 = st.columns([1, 1, 1])
                    _new_target = _tp_col1.number_input(
                        "ราคาเป้าหมาย", min_value=0.0, step=0.01, format="%.2f", key=f"target_price_{_ticker}"
                    )
                    _new_dir = _tp_col2.selectbox(
                        "เงื่อนไข", ["below", "above"],
                        format_func=lambda x: "ราคาลงมาถึง/ต่ำกว่า (ซื้อตอนถูก)" if x == "below" else "ราคาขึ้นมาถึง/เกิน (ขายทำกำไร)",
                        key=f"target_dir_{_ticker}"
                    )
                    _target_submitted = _tp_col3.form_submit_button("💾 บันทึกเป้าหมาย")

                if _target_submitted:
                    if _new_target <= 0:
                        st.warning("กรุณาระบุราคาเป้าหมายมากกว่า 0")
                    else:
                        _success, _msg = update_watchlist_target(_ticker, _new_target, _new_dir)
                        if _success:
                            st.success(_msg)
                            st.rerun()
                        else:
                            st.warning(_msg)
