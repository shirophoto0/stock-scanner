# =============================================================
# tab_funds.py
# แท็บกองทุนรวม (Phase 2 ของการแยกไฟล์)
# =============================================================
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, datetime
from backend_functions import calculate_fund_result, get_gsheet_client, get_cached_worksheet, get_active_sheet_name
from theme import style_plotly, render_metric_card


# 🆕 แก้บั๊ก 429 Rate Limit: เดิมทุก sub-tab (ภาพรวมพอร์ต/ซื้อกองทุนเพิ่ม/อัปเดตราคา) ต่างเรียก
# .worksheet('Fund_History').get_all_records() แยกกันเอง — เพราะ Streamlit's st.tabs() รันทุกแท็บ
# พร้อมกันหมดทุกครั้งที่หน้าเว็บรันซ้ำ (แค่ซ่อนแท็บที่ไม่ได้เลือกไว้ด้วย CSS เท่านั้น ไม่ได้ข้ามการ
# ประมวลผล) ทำให้ยิง API อ่านข้อมูลรัว 3-4 ครั้งทุกครั้งที่มีการโต้ตอบใดๆ ในหน้านี้ จนโดน Rate Limit
# ตอนนี้ห่อด้วย @st.cache_data ให้ทุกจุดที่ต้องการอ่านข้อมูลกองทุน เรียกผ่านฟังก์ชันเดียวกันนี้แทน
# (ยิง API จริงแค่ครั้งเดียวทุก 2 นาที ไม่ว่าจะมีกี่แท็บเรียกพร้อมกันก็ตาม)
#
# หมายเหตุเรื่อง 429: ฟังก์ชันนี้เรียกผ่าน get_gsheet_client()/get_cached_worksheet() ซึ่งมีสวิตช์
# _use_firestore() อยู่ในตัวอยู่แล้ว (ดูใน backend_functions.py) ถ้าบัญชีที่ใช้งานอยู่ถูกเปิด Firestore
# ไว้ (ผ่าน _FIRESTORE_ENABLED_SHEETS ใน Streamlit secrets) จุดนี้จะไม่ยิง Google Sheets API เลย
# ถ้ายังเจอ "APIError: [429] ... sheets.googleapis.com" อยู่ แปลว่าบัญชีที่ล็อกอินอยู่ตอนนั้น "ไม่ได้"
# อยู่ในลิสต์ _FIRESTORE_ENABLED_SHEETS บน Streamlit Cloud secrets (เช็ก sheet_name ให้ตรงตัวกับที่
# ตั้งไว้ใน [users.xxx] เป๊ะๆ) ไม่ใช่บั๊กที่จุดนี้ในโค้ด
@st.cache_data(ttl=120, show_spinner=False)
def _load_fund_history_cached(spreadsheet_name):
    """โหลดข้อมูลกองทุนทั้งหมดจากชีต Fund_History (แคชไว้ 2 นาที กันยิง API ซ้ำจนโดน Rate Limit)"""
    client = get_gsheet_client()
    sheet = get_cached_worksheet(client, spreadsheet_name, 'Fund_History')
    return sheet.get_all_records()


@st.cache_data(ttl=300, show_spinner=False)
def _load_fund_value_history_cached(spreadsheet_name):
    """โหลดข้อมูลแนวโน้มมูลค่ากองทุนจากชีต Fund_Value_History (แคชไว้ 5 นาที เพราะเป็นข้อมูลย้อนหลังรายเดือน ไม่ต้องอัปเดตบ่อย)"""
    client = get_gsheet_client()
    sheet = get_cached_worksheet(client, spreadsheet_name, 'Fund_Value_History')
    return sheet.get_all_records()


@st.cache_data(ttl=120, show_spinner=False)
def _load_fund_dividend_cached(spreadsheet_name):
    """🆕 โหลดประวัติปันผลที่บันทึกไว้เองจากชีต Fund_Dividend (แคชไว้ 2 นาทีเหมือน Fund_History)"""
    client = get_gsheet_client()
    sheet = get_cached_worksheet(client, spreadsheet_name, 'Fund_Dividend')
    return sheet.get_all_records()


_FUND_DIVIDEND_COLUMNS = ["Dividend_ID", "Fund_Name", "Date", "Amount", "Note"]


def _append_row_with_columns(sheet, row_values, columns):
    """
    🆕 เขียนแถวใหม่ลง worksheet ที่อาจจะยังไม่เคยมีข้อมูลมาก่อนเลย (เช่น Fund_Dividend ที่เพิ่งมี
    ครั้งแรก) — รองรับทั้ง 2 backend: Firestore (FirestoreWorksheet.append_rows ต้องระบุ columns=
    ให้ตอนเขียนแถวแรกสุด เพราะไม่มี "หัวตาราง" ในตัวแบบ Sheets ให้อ้างอิง) และ Google Sheets จริง
    (gspread.Worksheet.append_rows ไม่มีพารามิเตอร์ columns เลย ต้องมีแท็บชีต+หัวตารางสร้างไว้
    ก่อนแล้ว) ลองแบบ Firestore ก่อน ถ้าไม่รองรับ (TypeError จาก keyword ที่ไม่รู้จัก) ค่อย fallback
    ไปเรียก append_row ธรรมดาแทน
    """
    try:
        sheet.append_rows([row_values], columns=columns)
    except TypeError:
        sheet.append_row(row_values)


# ฟังก์ชันช่วยแปลงค่าให้เป็น float อย่างปลอดภัย (ป้องกัน Error ตัวอักษรปน) — ใช้ร่วมกันหลาย sub-tab
def _safe_float(val):
    try:
        if val is None or str(val).strip() == "":
            return 0.0
        return float(str(val).replace(',', '').strip())
    except ValueError:
        return 0.0


_NEW_FUND_OPTION = "➕ กองทุนใหม่ (พิมพ์ชื่อเอง)"


def render_tab_funds():
    st.subheader("💰 ระบบจัดการกองทุนรวม")

    # สร้าง Tab ย่อยสำหรับการจัดการกองทุน
    # 🔧 ปรับปรุง: สลับลำดับแท็บย่อย ให้ "ภาพรวมพอร์ต" อยู่ซ้ายสุด จะได้เห็นหน้า Dashboard ก่อนทันที
    # ที่เปิดแท็บกองทุนรวม (สลับแค่ลำดับตอนประกาศตรงนี้ ไม่ต้องย้ายเนื้อหาข้างในเลย เพราะโค้ด
    # อ้างอิงผ่านชื่อตัวแปรอยู่แล้ว ไม่ขึ้นกับตำแหน่งที่ประกาศ)
    tab_summary, tab_buy, tab_update, tab_dividend = st.tabs(
        ["📈 ภาพรวมพอร์ต", "➕ ซื้อกองทุนเพิ่ม", "🔄 อัปเดตราคา/ขาย", "💵 บันทึกปันผล"]
    )

    # 1. Tab ซื้อกองทุนใหม่/ซื้อเพิ่ม
    with tab_buy:
        st.markdown("### บันทึกซื้อกองทุนใหม่")
        st.caption("เลือกกองทุนที่มีอยู่แล้วในพอร์ตเพื่อ \"ซื้อเพิ่ม\" ได้เลย หรือเลือก \"กองทุนใหม่\" แล้วพิมพ์ชื่อกองทุนเอง")

        # 🆕 ดึงรายชื่อกองทุนที่มีอยู่แล้วในพอร์ต มาทำเป็น dropdown ให้เลือก "ซื้อเพิ่ม" ได้
        # (ใช้ข้อมูลที่แคชไว้อยู่แล้ว ไม่ยิง API อ่านเพิ่ม)
        try:
            _existing_fund_data = _load_fund_history_cached(get_active_sheet_name())
        except Exception:
            _existing_fund_data = []
        _existing_fund_names = sorted(set(
            r.get('Fund_Name', '') for r in _existing_fund_data if r.get('Fund_Name')
        ))

        # 🆕 กันฟอร์มค้างค่าเดิมหลังกด save: ทุกครั้งที่บันทึกสำเร็จ จะเพิ่มเลข nonce นี้ขึ้น 1
        # แล้วต่อท้าย key ของทุกช่องกรอกในฟอร์ม — Streamlit จะมองว่าเป็น widget ใหม่ทั้งหมด (ไม่มีค่า
        # เดิมค้างใน session_state) จึงกลับไปเป็นค่าเริ่มต้นว่างๆ ให้อัตโนมัติ โดยไม่ต้องเคลียร์เอง
        # ทีละช่อง (ทำแบบนั้นไม่ได้ด้วยซ้ำ เพราะ widget ที่อยู่ใน st.form ห้ามแก้ session_state
        # ของมันเองหลัง instantiate แล้ว)
        st.session_state.setdefault('fund_buy_form_nonce', 0)
        _nonce = st.session_state['fund_buy_form_nonce']

        with st.form(f"form_buy_fund_{_nonce}"):
            fund_choice = st.selectbox(
                "เลือกกองทุน:",
                [_NEW_FUND_OPTION] + _existing_fund_names,
                key=f"fund_buy_choice_{_nonce}",
            )
            new_fund_name = st.text_input(
                "ชื่อกองทุนใหม่ (กรอกเฉพาะกรณีเลือก \"กองทุนใหม่\" ด้านบน เช่น SCBSET, K-Equity):",
                key=f"fund_buy_new_name_{_nonce}",
            )

            col1, col2 = st.columns(2)
            # แก้ไขจาก datetime.date.today() เป็น date.today() เพื่อป้องกัน Error
            date_buy = col1.date_input("วันที่ซื้อ:", date.today(), key=f"fund_buy_date_{_nonce}")
            cost_price = col2.number_input(
                "ราคาต้นทุนเฉลี่ยต่อหน่วย (มูลค่าตลาด):",
                min_value=0.0, step=0.0001, format="%.4f", key=f"fund_buy_cost_{_nonce}",
            )

            col3, col4 = st.columns(2)
            units = col3.number_input(
                "จำนวนหน่วย (Units):",
                min_value=0.0, step=0.0001, format="%.4f", key=f"fund_buy_units_{_nonce}",
            )
            # 🆕 ช่องกรอกทางเลือก: กรอก "ราคาต้นทุนเฉลี่ยต่อหน่วย" ด้านบน หรือ "มูลค่าเงินลงทุนรวม"
            # ด้านล่างนี้ อย่างใดอย่างหนึ่งก็ได้ ถ้าไม่กรอกราคาต่อหน่วย ระบบจะคำนวณราคาต่อหน่วยให้เอง
            # จาก มูลค่ารวม ÷ จำนวนหน่วย
            total_cost_value = col4.number_input(
                "หรือกรอกมูลค่าเงินลงทุนรวมแทน:",
                min_value=0.0, step=0.0001, format="%.4f", key=f"fund_buy_total_{_nonce}",
                help="กรอกอย่างใดอย่างหนึ่งพอครับ: ราคาต้นทุนเฉลี่ยต่อหน่วยด้านบน หรือมูลค่าเงินลงทุนรวมช่องนี้ ระบบจะคำนวณอีกค่าให้อัตโนมัติจากจำนวนหน่วย"
            )

            submitted = st.form_submit_button("บันทึกการซื้อกองทุน", use_container_width=True, type="primary")
            if submitted:
                fund_name = (new_fund_name or "").strip() if fund_choice == _NEW_FUND_OPTION else fund_choice

                if not fund_name:
                    st.warning("กรุณาเลือกกองทุน หรือกรอกชื่อกองทุนใหม่ครับ")
                elif units <= 0:
                    st.warning("กรุณากรอกจำนวนหน่วย (Units) ครับ")
                elif cost_price <= 0 and total_cost_value <= 0:
                    st.warning("กรุณากรอกราคาต้นทุนเฉลี่ยต่อหน่วย หรือ มูลค่าเงินลงทุนรวม อย่างใดอย่างหนึ่งครับ")
                else:
                    if cost_price <= 0:
                        cost_price = total_cost_value / units
                    cost_price = round(cost_price, 4)
                    units = round(units, 4)
                    try:
                        client = get_gsheet_client()
                        # 🔧 แก้บั๊ก: เดิมเขียน ID ของ Google Sheet ตายตัวไว้ (ไม่ใช่ชื่อ "MyStockData")
                        # ทำให้ไม่ว่าใคร login เข้ามาก็จะไปอ่าน/เขียนไฟล์เดียวกันเป๊ะๆ เสมอ ไม่แยกตามผู้ใช้
                        # เปลี่ยนมาใช้ระบบเดียวกับแท็บอื่น (เปิดตามชื่อชีตของผู้ใช้ที่ login อยู่) และ
                        # เปลี่ยนจาก get_cached_spreadsheet().worksheet() เป็น get_cached_worksheet()
                        # ซึ่งแคชครบทั้ง spreadsheet และ worksheet object ในตัวเดียว ลด API call ซ้ำซ้อน
                        sheet = get_cached_worksheet(client, get_active_sheet_name(), 'Fund_History')

                        # หา Fund_ID ถัดไป (ใช้ข้อมูลที่แคชไว้ ไม่ต้องยิง API อ่านซ้ำ)
                        existing_data = _load_fund_history_cached(get_active_sheet_name())
                        new_id = len(existing_data)

                        # 🆕 ซื้อกองทุนเดิมเพิ่ม (เลือกจาก dropdown แทนที่จะพิมพ์ชื่อเอง) ก็ยัง
                        # append_row เป็นแถวใหม่แยกต่างหากเสมอเหมือนเดิม (1 แถว = การซื้อ 1 ครั้ง)
                        # เพราะแต่ละครั้งมีต้นทุน/วันที่ซื้อต่างกัน — ฝั่ง UI (แท็บภาพรวมพอร์ต และ
                        # แท็บอัปเดตราคา/ขาย) เป็นฝ่ายรวมยอดของกองทุนชื่อเดียวกันให้แสดงเป็นบรรทัด
                        # เดียวเองตอนแสดงผล ไม่ใช่รวมตอนบันทึก
                        #
                        # ข้อมูลที่จะ append: Fund_ID, Fund_Name, Date_Buy, Date_Sell, Cost_Price, Current_Price, Units, Status, Price_Updated_Date
                        # 🆕 เพิ่มคอลัมน์ Price_Updated_Date (วันที่อัปเดตราคาล่าสุด) ไว้ท้ายสุด เพื่อใช้
                        # เตือน "ราคาเก่า" ในหน้าภาพรวมพอร์ต — ตอนซื้อใหม่ ใช้วันที่ซื้อเป็นวันแรกที่
                        # ถือว่าราคาอัปเดตล่าสุด (เพราะ Cost_Price = Current_Price ตอนซื้อพอดี)
                        row_data = [new_id, fund_name, str(date_buy), "", cost_price, cost_price, units, "Holding", str(date_buy)]
                        sheet.append_row(row_data)

                        st.cache_data.clear()
                        # 🆕 ล้างฟอร์มหลังบันทึกสำเร็จ (ดูคอมเมนต์ตอนประกาศ nonce ด้านบน)
                        st.session_state['fund_buy_form_nonce'] += 1
                        st.success("บันทึกกองทุนสำเร็จ! 🎉")
                        st.rerun()
                    except Exception as e:
                        st.error(f"เกิดข้อผิดพลาด: {e}")

    # 2. Tab อัปเดตราคาปัจจุบัน หรือ ขายกองทุน
    with tab_update:
        st.markdown("### อัปเดตราคาหรือขายกองทุน")

        # 1. ดึงข้อมูลกองทุนทั้งหมดมาทำ Dropdown
        try:
            client = get_gsheet_client()
            # 🔧 แก้บั๊ก: เดิมเขียน ID ของ Google Sheet ตายตัวไว้ ตอนนี้เปลี่ยนตามผู้ใช้ที่ login แล้ว
            # และเปลี่ยนมาอ่านผ่านฟังก์ชันที่แคชไว้แทน (ไม่ยิง API อ่านซ้ำทุกครั้งที่หน้าเว็บรัน)
            sheet = get_cached_worksheet(client, get_active_sheet_name(), 'Fund_History')
            all_data = _load_fund_history_cached(get_active_sheet_name())

            if all_data:
                # 🔧 แก้บั๊ก: ใช้ .get() แทนการเข้าถึงตรงๆ เผื่อชีตของบางบัญชีไม่มีคอลัมน์นี้
                fund_list = sorted(list(set(row.get('Fund_Name', '') for row in all_data if row.get('Fund_Name') and row.get('Status') == 'Holding')))

                if not fund_list:
                    fund_list = sorted(list(set(row.get('Fund_Name', '') for row in all_data if row.get('Fund_Name'))))

                if fund_list:
                    selected_fund = st.selectbox("เลือกกองทุนที่ต้องการจัดการ:", fund_list, key="selected_fund_update")

                    # 🆕 รองรับกองทุนที่ซื้อเพิ่มหลายครั้ง (หลาย "ล็อต"/หลายแถวใน Fund_History):
                    # เดิมโค้ดหาแค่แถวแรกที่ Fund_Name ตรงกันแล้วหยุด (แถวอื่นที่เหลือของกองทุนเดียวกัน
                    # ถูกมองข้ามไปเลย ทั้งตอนอัปเดตราคาและตอนขาย) ตอนนี้รวบรวมทุกล็อตที่ยังถือครองอยู่
                    # (Status Holding) ของกองทุนที่เลือกไว้ทั้งหมด แล้วเรียงจากวันที่ซื้อเก่าสุดก่อน
                    # (ใช้ตัดขายแบบ FIFO ด้านล่าง)
                    lots = []
                    for idx, row in enumerate(all_data):
                        if row.get('Fund_Name') == selected_fund and row.get('Status', 'Holding') == 'Holding':
                            lots.append({
                                'row_index': idx + 2,
                                'units': _safe_float(row.get('Units', 0)),
                                'cost_price': _safe_float(row.get('Cost_Price', 0)),
                                'current_price': _safe_float(row.get('Current_Price', 0)),
                                'price_updated': str(row.get('Price_Updated_Date', '')).strip(),
                                'date_buy': str(row.get('Date_Buy', '')),
                            })
                    lots.sort(key=lambda l: l['date_buy'])

                    if lots:
                        units_val = sum(l['units'] for l in lots)
                        total_cost_val = sum(l['units'] * l['cost_price'] for l in lots)
                        avg_price_val = (total_cost_val / units_val) if units_val > 0 else 0.0
                        # ราคาปัจจุบันที่โชว์ให้ดู: เอาจากล็อตที่มีวันที่อัปเดตล่าสุดสุด (ปกติทุกล็อต
                        # ของกองทุนเดียวกันจะถูกอัปเดตพร้อมกันเสมอจากปุ่ม "อัปเดตราคา" ด้านล่าง)
                        _lots_with_date = [l for l in lots if l['price_updated']]
                        if _lots_with_date:
                            current_price_val = max(_lots_with_date, key=lambda l: l['price_updated'])['current_price']
                        else:
                            current_price_val = lots[0]['current_price']

                        _lots_note = f"\n\n📦 ถือครองอยู่ {len(lots)} รายการซื้อ (จะรวมยอดกัน)" if len(lots) > 1 else ""
                        st.info(f"📌 **ข้อมูลปัจจุบันของกองทุน:** {selected_fund}\n\n"
                                f"- **จำนวนหน่วย:** {units_val:,.4f}\n"
                                f"- **ราคาเฉลี่ย/ต้นทุน:** {avg_price_val:,.4f}\n"
                                f"- **ราคาปัจจุบันล่าสุด:** {current_price_val:,.4f}"
                                f"{_lots_note}")

                        action_type = st.radio("เลือกการดำเนินการ:", ["อัปเดตราคาปัจจุบัน", "ขายกองทุนออก"], horizontal=True, key="fund_action_radio")

                        # 🆕 กันฟอร์มค้างค่าเดิมหลังกด save เหมือนกับฟอร์มซื้อด้านบน (เพิ่ม nonce
                        # แยกกันของฟอร์มอัปเดตราคา/ฟอร์มขาย เพราะเป็นคนละฟอร์มคนละปุ่ม)
                        st.session_state.setdefault('fund_price_form_nonce', 0)
                        st.session_state.setdefault('fund_sell_form_nonce', 0)

                        # 🔧 แก้บั๊ก: เดิม new_price/sell_units/sell_price อยู่นอกฟอร์มทั้งหมด พิมพ์ตัวเลข
                        # ทีละตัวแล้วหน้าเว็บรันใหม่ทันที ตอนนี้ครอบด้วย st.form() แยกตาม action ที่
                        # เลือก (คนละฟอร์ม คนละปุ่ม) ให้กรอกครบก่อนค่อยกดปุ่มยืนยัน — selected_fund กับ
                        # action_type ด้านบนยังอยู่นอกฟอร์มเหมือนเดิม เพราะต้องอัปเดตสดจริงๆ (โชว์ข้อมูล
                        # กองทุนที่เลือก, สลับช่องกรอกตาม action ที่เลือก)
                        if action_type == "อัปเดตราคาปัจจุบัน":
                            _pnonce = st.session_state['fund_price_form_nonce']
                            with st.form(f"fund_update_price_form_{_pnonce}"):
                                col_p1, col_p2 = st.columns(2)
                                new_price = col_p1.number_input(
                                    "ราคาปัจจุบันใหม่ (มูลค่าตลาดต่อหน่วย):",
                                    min_value=0.0, step=0.0001, format="%.4f", key=f"new_price_input_{_pnonce}",
                                )
                                # 🆕 ช่องกรอกทางเลือก: กรอก "ราคาปัจจุบันใหม่" ด้านซ้าย หรือ "มูลค่าปัจจุบันรวม"
                                # ด้านนี้ อย่างใดอย่างหนึ่งก็ได้ ถ้าไม่กรอกราคาต่อหน่วย ระบบจะคำนวณราคาต่อหน่วย
                                # ให้เองจาก มูลค่ารวม ÷ จำนวนหน่วยที่ถืออยู่ (units_val รวมทุกล็อต)
                                new_total_value = col_p2.number_input(
                                    "หรือมูลค่าปัจจุบันรวม:", min_value=0.0, step=0.0001, format="%.4f", key=f"new_total_value_input_{_pnonce}",
                                    help="กรอกอย่างใดอย่างหนึ่งพอครับ: ราคาต่อหน่วยด้านซ้าย หรือมูลค่ารวมช่องนี้ ระบบจะคำนวณอีกค่าให้อัตโนมัติจากจำนวนหน่วยที่ถืออยู่ทั้งหมด"
                                )
                                update_price_submitted = st.form_submit_button("💾 บันทึกราคาอัปเดต")

                            if update_price_submitted and new_price <= 0 and new_total_value <= 0:
                                st.warning("กรุณากรอกราคาปัจจุบันใหม่ หรือ มูลค่าปัจจุบันรวม อย่างใดอย่างหนึ่งครับ")
                            elif update_price_submitted:
                                if new_price <= 0:
                                    new_price = new_total_value / units_val
                                new_price = round(new_price, 4)
                                # 🆕 อัปเดตราคาให้ "ทุกล็อต" ของกองทุนนี้พร้อมกัน (ราคาตลาด/NAV ต้องเท่า
                                # กันทุกล็อตของกองทุนเดียวกันอยู่แล้ว) เดิมอัปเดตแค่ล็อตแรกล็อตเดียว ทำให้
                                # ล็อตที่เหลือค้างราคาเก่าและถูกเตือนว่า "ราคาเก่าเกิน 35 วัน" ผิดๆ ตลอด
                                for l in lots:
                                    sheet.update_cell(l['row_index'], 6, new_price)
                                    # 🆕 บันทึกวันที่อัปเดตราคาล่าสุดไว้ที่คอลัมน์ 9 (Price_Updated_Date)
                                    # ด้วย ใช้เตือน "ราคาเก่า" ในหน้าภาพรวมพอร์ตถ้าไม่ได้อัปเดตนานเกินไป
                                    sheet.update_cell(l['row_index'], 9, str(date.today()))
                                st.cache_data.clear()  # 🆕 ล้างแคชทันที กันเห็นราคาเก่าค้างอยู่
                                st.session_state['fund_price_form_nonce'] += 1
                                st.success(f"อัปเดตราคา {selected_fund} เป็น {new_price:,.4f} สำเร็จ!")
                                st.rerun()

                        elif action_type == "ขายกองทุนออก":
                            _snonce = st.session_state['fund_sell_form_nonce']
                            if len(lots) > 1:
                                st.caption("💡 มีมากกว่า 1 รายการซื้อ ระบบจะตัดขายจากรายการที่ซื้อมาก่อนสุดไปหาหลังสุด (FIFO) ให้อัตโนมัติ")
                            with st.form(f"fund_sell_form_{_snonce}"):
                                sell_units = st.number_input(
                                    "จำนวนหน่วยที่ต้องการขาย:",
                                    min_value=0.0, max_value=units_val, step=0.0001, format="%.4f", key=f"sell_units_input_{_snonce}",
                                )
                                sell_price = st.number_input(
                                    "ราคาขายต่อหน่วย:",
                                    min_value=0.0, step=0.0001, format="%.4f", key=f"sell_price_input_{_snonce}",
                                )
                                sell_submitted = st.form_submit_button("💸 ยืนยันการขายกองทุน")

                            if sell_submitted and sell_units <= 0:
                                st.warning("กรุณากรอกจำนวนหน่วยที่ต้องการขายครับ")
                            elif sell_submitted:
                                # 🆕 ตัดขายแบบ FIFO ไล่จากล็อตที่ซื้อก่อนสุด จนกว่าจะครบจำนวนหน่วยที่ขาย
                                # 🔧 แก้บั๊ก (สำคัญ): เดิมกรณีขายบางส่วน โค้ดเขียนจำนวนหน่วยที่เหลือลง
                                # คอลัมน์ที่ 3 (Date_Buy) แทนที่จะเป็นคอลัมน์ที่ 7 (Units) ทำให้วันที่ซื้อ
                                # ของกองทุนถูกเขียนทับด้วยตัวเลขจำนวนหน่วยทุกครั้งที่ขายบางส่วน ข้อมูล
                                # เพี้ยนไปเรื่อยๆ — ตอนนี้แก้ให้ตรงคอลัมน์แล้ว (ดูลำดับคอลัมน์ตอน append_row
                                # ด้านบน: Fund_ID, Fund_Name, Date_Buy, Date_Sell, Cost_Price,
                                # Current_Price, Units, Status, Price_Updated_Date)
                                remaining_to_sell = round(sell_units, 4)
                                for l in lots:
                                    if remaining_to_sell <= 0:
                                        break
                                    if remaining_to_sell >= l['units']:
                                        sheet.update_cell(l['row_index'], 8, "Sold")
                                        remaining_to_sell = round(remaining_to_sell - l['units'], 4)
                                    else:
                                        new_units = round(l['units'] - remaining_to_sell, 4)
                                        sheet.update_cell(l['row_index'], 7, new_units)
                                        remaining_to_sell = 0.0

                                remaining_units = round(units_val - sell_units, 4)
                                if remaining_units <= 0:
                                    st.success(f"ขายกองทุน {selected_fund} ทั้งหมดเรียบร้อยแล้ว!")
                                else:
                                    st.success(f"ขายกองทุน {selected_fund} บางส่วน คงเหลือ {remaining_units:,.4f} หน่วย")
                                st.cache_data.clear()  # 🆕 ล้างแคชทันที กันเห็นข้อมูลเก่าค้างอยู่
                                st.session_state['fund_sell_form_nonce'] += 1
                                st.rerun()
                    else:
                        st.warning("ไม่พบข้อมูลกองทุนที่มีสถานะถือครองอยู่ในระบบ")
                else:
                    st.info("ยังไม่มีกองทุนในสถานะถือครอง")
            else:
                st.info("ยังไม่มีข้อมูลกองทุนในระบบ")

        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการโหลดข้อมูล: {e}")

    # 3. Tab บันทึกปันผลที่ได้รับ (🆕 บางกองทุนมีจ่ายปันผล ระบบไม่ได้ดึงข้อมูลนี้อัตโนมัติจากที่ไหน
    # จึงต้องให้กรอกเองเป็นรายครั้ง แล้วนำไปรวมกับกำไร/ขาดทุนจากราคาในแท็บภาพรวมพอร์ต เพื่อดู
    # "ผลตอบแทนรวม" ที่แท้จริงของแต่ละกองทุน)
    with tab_dividend:
        st.markdown("### บันทึกปันผลที่ได้รับ")
        st.caption("บันทึกเงินปันผลที่ได้รับจากกองทุนแต่ละกองด้วยตนเอง (ระบบไม่มีข้อมูลปันผลอัตโนมัติ) ยอดที่บันทึกจะถูกนำไปรวมแสดงเป็น \"ผลตอบแทนรวม\" ในแท็บภาพรวมพอร์ต")

        try:
            _div_fund_data = _load_fund_history_cached(get_active_sheet_name())
        except Exception:
            _div_fund_data = []
        # 🆕 ให้เลือกได้จากกองทุนทุกกองที่เคยมีในระบบ (ไม่ใช่แค่ที่ถือครองอยู่ตอนนี้) เผื่อได้รับ
        # ปันผลงวดล่าสุดก่อนขาย หรือมาบันทึกย้อนหลังทีหลัง
        _div_fund_names = sorted(set(r.get('Fund_Name', '') for r in _div_fund_data if r.get('Fund_Name')))

        st.session_state.setdefault('fund_div_form_nonce', 0)
        _dnonce = st.session_state['fund_div_form_nonce']

        if not _div_fund_names:
            st.info("ยังไม่มีกองทุนในระบบ กรุณาซื้อกองทุนก่อนในแท็บ \"➕ ซื้อกองทุนเพิ่ม\" ครับ")
        else:
            with st.form(f"form_fund_dividend_{_dnonce}"):
                div_fund = st.selectbox("กองทุน:", _div_fund_names, key=f"fund_div_choice_{_dnonce}")
                col_d1, col_d2 = st.columns(2)
                div_date = col_d1.date_input("วันที่ได้รับปันผล:", date.today(), key=f"fund_div_date_{_dnonce}")
                div_amount = col_d2.number_input(
                    "จำนวนเงินปันผลที่ได้รับ (บาท):",
                    min_value=0.0, step=0.0001, format="%.4f", key=f"fund_div_amount_{_dnonce}",
                )
                div_note = st.text_input("หมายเหตุ (ถ้ามี):", key=f"fund_div_note_{_dnonce}")

                div_submitted = st.form_submit_button("💾 บันทึกปันผล", use_container_width=True, type="primary")
                if div_submitted:
                    if div_amount <= 0:
                        st.warning("กรุณากรอกจำนวนเงินปันผลที่ได้รับครับ")
                    else:
                        try:
                            client = get_gsheet_client()
                            sheet = get_cached_worksheet(client, get_active_sheet_name(), 'Fund_Dividend')
                            existing_div = _load_fund_dividend_cached(get_active_sheet_name())
                            new_div_id = len(existing_div)
                            row_data = [new_div_id, div_fund, str(div_date), round(div_amount, 4), div_note]
                            _append_row_with_columns(sheet, row_data, _FUND_DIVIDEND_COLUMNS)

                            st.cache_data.clear()
                            st.session_state['fund_div_form_nonce'] += 1
                            st.success("บันทึกปันผลสำเร็จ! 🎉")
                            st.rerun()
                        except Exception as e:
                            st.error(f"เกิดข้อผิดพลาด: {e}")

        st.divider()
        st.markdown("#### 📜 ประวัติปันผลที่บันทึกไว้")
        try:
            _div_history = _load_fund_dividend_cached(get_active_sheet_name())
        except Exception:
            _div_history = []

        _div_history = [d for d in _div_history if d.get('Fund_Name')]
        if _div_history:
            df_div = pd.DataFrame(_div_history)
            df_div_display = pd.DataFrame({
                "ชื่อกองทุน": df_div.get('Fund_Name', ''),
                "วันที่ได้รับ": df_div.get('Date', ''),
                "จำนวนเงิน (บาท)": df_div.get('Amount', 0).apply(_safe_float) if 'Amount' in df_div.columns else 0.0,
                "หมายเหตุ": df_div.get('Note', ''),
            }).sort_values("วันที่ได้รับ", ascending=False)

            st.dataframe(
                df_div_display.style.format({"จำนวนเงิน (บาท)": "{:,.4f}"}),
                use_container_width=True, hide_index=True
            )
            st.caption(f"รวมปันผลที่บันทึกไว้ทั้งหมด: {df_div_display['จำนวนเงิน (บาท)'].sum():,.4f} บาท")
        else:
            st.info("ยังไม่มีประวัติปันผลที่บันทึกไว้ครับ")

    # 4. Tab ภาพรวมพอร์ต (แสดงมูลค่าต้นทุน, มูลค่าปัจจุบัน + Dashboard ติดตามผลงาน)
    with tab_summary:
        st.markdown("### 📊 Dashboard ติดตามผลงานกองทุนรวม")
        try:
            # 🔧 แก้บั๊ก: เดิมเขียน ID ของ Google Sheet ตายตัวไว้ ตอนนี้เปลี่ยนตามผู้ใช้ที่ login แล้ว
            # และเปลี่ยนมาอ่านผ่านฟังก์ชันที่แคชไว้แทน (จุดนี้เป็นสาเหตุหลักของ 429 เพราะแท็บนี้เรียก
            # API ถึง 2 ครั้ง — Fund_History และ Fund_Value_History — ทุกครั้งที่หน้าเว็บรันซ้ำ) ไม่ต้อง
            # เรียก get_gsheet_client() เองตรงนี้แล้ว เพราะฟังก์ชัน cached จัดการให้ครบในตัวอยู่แล้ว
            summary_df = pd.DataFrame(_load_fund_history_cached(get_active_sheet_name()))

            if not summary_df.empty and 'Status' in summary_df.columns:
                active_df = summary_df[summary_df['Status'] == 'Holding'].copy()

                if not active_df.empty:
                    # 🆕 รวมยอดกองทุนชื่อเดียวกันที่ซื้อหลายรอบ (หลายแถวใน Fund_History) เข้าเป็น
                    # "หนึ่งบรรทัด" ต่อกองทุนตอนแสดงผล — ฝั่งข้อมูลจริงยังคงแยกเก็บทีละแถวต่อการซื้อ
                    # 1 ครั้งเหมือนเดิม (ดูคอมเมนต์ตอน append_row ในแท็บ "ซื้อกองทุนเพิ่ม") เดิมโค้ด
                    # จุดนี้ไม่ได้รวม ทำให้กองทุนที่ซื้อเพิ่มหลายรอบโผล่ซ้ำหลายบรรทัดในตาราง/กราฟด้านล่าง
                    # 🆕 ดึงประวัติปันผลที่บันทึกเองมารวมด้วย (ดูแท็บ "💵 บันทึกปันผล") ใช้คำนวณ
                    # "ผลตอบแทนรวม" (ทุน + ปันผล) ของแต่ละกองทุน — ถ้ายังไม่เคยมีชีต Fund_Dividend
                    # เลย (ยังไม่เคยบันทึกปันผลสักครั้ง) ให้ถือว่าไม่มีปันผลเลย ไม่ต้อง error
                    try:
                        _div_data = _load_fund_dividend_cached(get_active_sheet_name())
                    except Exception:
                        _div_data = []
                    fund_dividends = {}
                    for d in _div_data:
                        _dfname = d.get('Fund_Name', '')
                        if not _dfname:
                            continue
                        fund_dividends[_dfname] = fund_dividends.get(_dfname, 0.0) + _safe_float(d.get('Amount', 0))
                    total_dividends_all = sum(fund_dividends.values())

                    total_portfolio_cost = 0.0
                    total_portfolio_value = 0.0
                    _fund_groups = {}
                    _latest_price_update = None

                    for _, row in active_df.iterrows():
                        cost_p = float(row['Cost_Price'])
                        curr_p = float(row['Current_Price'])
                        units = float(row['Units'])
                        res = calculate_fund_result(cost_p, curr_p, units)

                        total_portfolio_cost += res['Total_Cost']
                        total_portfolio_value += res['Current_Value']

                        fname = row['Fund_Name']
                        g = _fund_groups.setdefault(fname, {
                            'units': 0.0, 'total_cost': 0.0, 'total_value': 0.0,
                            'date_buy_first': str(row['Date_Buy']),
                            'lot_count': 0, 'max_days': None, 'any_missing': False,
                            'lots': [],
                        })
                        g['units'] += units
                        g['total_cost'] += res['Total_Cost']
                        g['total_value'] += res['Current_Value']
                        g['lot_count'] += 1
                        if str(row['Date_Buy']) < g['date_buy_first']:
                            g['date_buy_first'] = str(row['Date_Buy'])
                        # 🆕 เก็บรายละเอียดแต่ละ "ไม้"/ล็อตที่ซื้อไว้ด้วย ใช้แสดงตอนคลิกกางดูรายกอง
                        # ทุนด้านล่าง (ดูส่วน st.expander ต่อกองทุน)
                        g['lots'].append({
                            "วันที่ซื้อ": str(row['Date_Buy']),
                            "ต้นทุน/หน่วย": round(cost_p, 4),
                            "จำนวนหน่วย": round(units, 4),
                            "มูลค่าต้นทุน": res['Total_Cost'],
                            "มูลค่าปัจจุบัน": res['Current_Value'],
                        })

                        # 🆕 หาว่าราคาอัปเดตล่าสุดเมื่อไหร่ (คอลัมน์ Price_Updated_Date ถ้ามี)
                        price_updated_str = str(row.get('Price_Updated_Date', '')).strip()
                        days_since_update = None
                        if price_updated_str:
                            try:
                                price_updated_date = datetime.strptime(price_updated_str, '%Y-%m-%d').date()
                                days_since_update = (date.today() - price_updated_date).days
                                # 🆕 ไล่หาวันที่อัปเดตราคาล่าสุดสุดในบรรดากองทุนทั้งหมด ใช้โชว์เป็น
                                # badge บนการ์ด "มูลค่าปัจจุบันรวม" ด้านล่าง
                                if _latest_price_update is None or price_updated_date > _latest_price_update:
                                    _latest_price_update = price_updated_date
                            except ValueError:
                                pass

                        if days_since_update is None:
                            g['any_missing'] = True
                        else:
                            g['max_days'] = days_since_update if g['max_days'] is None else max(g['max_days'], days_since_update)

                    display_data = []
                    for fname, g in _fund_groups.items():
                        g_units = g['units']
                        g_cost = g['total_cost']
                        g_value = g['total_value']
                        avg_cost_price = (g_cost / g_units) if g_units > 0 else 0.0
                        avg_curr_price = (g_value / g_units) if g_units > 0 else 0.0
                        profit = g_value - g_cost
                        profit_pct = (profit / g_cost * 100) if g_cost > 0 else 0.0
                        is_stale = g['any_missing'] or (g['max_days'] is not None and g['max_days'] > 35)
                        # 🆕 ผลตอบแทนรวม = กำไร/ขาดทุนจากราคา + ปันผลสะสมที่บันทึกไว้ของกองทุนนี้
                        fund_dividend = fund_dividends.get(fname, 0.0)
                        total_return = profit + fund_dividend
                        total_return_pct = (total_return / g_cost * 100) if g_cost > 0 else 0.0

                        display_data.append({
                            "ชื่อกองทุน": fname,
                            "วันที่ซื้อ": g['date_buy_first'],
                            "ต้นทุนเฉลี่ย": round(avg_cost_price, 4),
                            "ราคาปัจจุบัน": round(avg_curr_price, 4),
                            "จำนวนหน่วย": round(g_units, 4),
                            "มูลค่าต้นทุน": round(g_cost, 4),
                            "มูลค่าปัจจุบัน": round(g_value, 4),
                            "กำไร/ขาดทุน": round(profit, 4),
                            "% กำไร/ขาดทุน": round(profit_pct, 4),
                            "ปันผลสะสม": round(fund_dividend, 4),
                            "ผลตอบแทนรวม": round(total_return, 4),
                            "% ผลตอบแทนรวม": round(total_return_pct, 4),
                            "_is_stale": is_stale,
                            "_lot_count": g['lot_count'],
                            "_lots": g['lots'],
                        })

                    df_display = pd.DataFrame(display_data)
                    total_profit = total_portfolio_value - total_portfolio_cost
                    total_profit_pct = (total_profit / total_portfolio_cost) * 100 if total_portfolio_cost > 0 else 0.0

                    # 🆕 (1) การ์ดสรุปภาพรวม — ใช้การ์ดสไตล์เดียวกับหน้าอื่นในแอปแทน st.metric เดิม
                    m1, m2, m3, m4 = st.columns(4)
                    render_metric_card(m1, "มูลค่าต้นทุนรวม", f"{total_portfolio_cost:,.4f} บาท", icon="📥")
                    render_metric_card(
                        m2, "มูลค่าปัจจุบันรวม", f"{total_portfolio_value:,.4f} บาท", icon="📈",
                        updated_date=_latest_price_update
                    )
                    render_metric_card(
                        m3, "กำไร/ขาดทุนรวม", f"{total_profit:,.4f} บาท", icon="💹",
                        delta=f"{total_profit_pct:.4f}%", delta_positive=(total_profit >= 0)
                    )
                    # 🆕 (1b) การ์ดปันผลสะสม + ผลตอบแทนรวม (ทุน+ปันผล) — ปันผลนับรวมกองที่ขายไปแล้ว
                    # ด้วย เพราะเป็นเงินสดที่ได้รับจริงไม่ว่าจะยังถือกองทุนนั้นอยู่หรือไม่ก็ตาม
                    _total_return_all = total_profit + total_dividends_all
                    _total_return_all_pct = (_total_return_all / total_portfolio_cost * 100) if total_portfolio_cost > 0 else 0.0
                    render_metric_card(
                        m4, "ปันผลสะสมทั้งหมด", f"{total_dividends_all:,.4f} บาท", icon="💵",
                        caption="รวมกองที่ขายไปแล้วด้วย"
                    )
                    st.caption(
                        f"🎯 **ผลตอบแทนรวม (ทุน + ปันผล) ของทั้งพอร์ต:** {_total_return_all:,.4f} บาท "
                        f"({_total_return_all_pct:+.4f}%)"
                    )

                    # 🆕 (4) เตือนราคาเก่า — ถ้ากองไหนไม่ได้อัปเดตราคาเกิน 35 วัน (หรือไม่มีข้อมูลวันที่
                    # อัปเดตเลย เพราะเป็นรายการเก่าก่อนมีฟีเจอร์นี้) จะเตือนให้ไปอัปเดตราคาก่อน เพราะ
                    # ตัวเลขทั้งหมดในหน้านี้คำนวณจากราคาที่กรอกเองรายเดือน ถ้าลืมอัปเดต ตัวเลขจะผิดเพี้ยน
                    _stale_funds = [d["ชื่อกองทุน"] for d in display_data if d["_is_stale"]]
                    if _stale_funds:
                        st.warning(
                            f"⚠️ **กองทุนต่อไปนี้ยังไม่ได้อัปเดตราคานานเกิน 35 วัน (หรือไม่มีข้อมูลวันที่อัปเดต):** "
                            f"{', '.join(_stale_funds)} — ไปที่แท็บ \"🔄 อัปเดตราคา/ขาย\" เพื่ออัปเดตให้ตัวเลขแม่นยำขึ้นครับ"
                        )

                    st.divider()

                    # 🆕 (2) เปรียบเทียบผลงานรายกองทุน — เรียงจากกำไรมากไปน้อย หนึ่งบรรทัดต่อกองทุน
                    # แม้จะซื้อมาหลายรอบก็ตาม (ดูคอมเมนต์การรวมยอดด้านบน) เปลี่ยนจากตาราง st.dataframe
                    # เดิมมาเป็น st.expander ต่อกองทุนแทน — คลิกที่ชื่อกองทุนเพื่อกางดูรายละเอียด
                    # แต่ละ "ไม้" (แต่ละครั้ง) ที่ซื้อกองทุนนั้นได้เลย
                    st.markdown("##### 📋 เปรียบเทียบผลงานรายกองทุน")
                    st.caption("💡 คลิกที่แถบกองทุนแต่ละอันเพื่อดูรายละเอียดทุกครั้งที่ซื้อ (กรณีซื้อกองทุนเดียวกันหลายรอบ)")
                    df_table = df_display.drop(columns=['_is_stale', '_lot_count', '_lots']).sort_values('% กำไร/ขาดทุน', ascending=False)
                    _sorted_display = sorted(display_data, key=lambda d: d["% กำไร/ขาดทุน"], reverse=True)

                    for d in _sorted_display:
                        _lot_suffix = f" · ซื้อ {d['_lot_count']} ครั้ง" if d['_lot_count'] > 1 else ""
                        _pl_sign = "📈" if d["% กำไร/ขาดทุน"] > 0 else "📉" if d["% กำไร/ขาดทุน"] < 0 else "➖"
                        _label = (
                            f"{_pl_sign} **{d['ชื่อกองทุน']}**{_lot_suffix}  —  "
                            f"มูลค่าปัจจุบัน {d['มูลค่าปัจจุบัน']:,.4f} บาท  ({d['% กำไร/ขาดทุน']:+.4f}%)"
                        )
                        with st.expander(_label):
                            c1, c2, c3 = st.columns(3)
                            c1.metric("ต้นทุนเฉลี่ย/หน่วย", f"{d['ต้นทุนเฉลี่ย']:,.4f}")
                            c2.metric("ราคาปัจจุบัน/หน่วย", f"{d['ราคาปัจจุบัน']:,.4f}")
                            c3.metric("จำนวนหน่วยรวม", f"{d['จำนวนหน่วย']:,.4f}")

                            c4, c5, c6 = st.columns(3)
                            c4.metric("มูลค่าต้นทุน", f"{d['มูลค่าต้นทุน']:,.4f}")
                            c5.metric("กำไร/ขาดทุน (จากราคา)", f"{d['กำไร/ขาดทุน']:,.4f}", delta=f"{d['% กำไร/ขาดทุน']:+.4f}%")
                            c6.metric("ปันผลสะสม", f"{d['ปันผลสะสม']:,.4f}")

                            st.caption(
                                f"🎯 ผลตอบแทนรวม (ทุน + ปันผล): {d['ผลตอบแทนรวม']:,.4f} บาท "
                                f"({d['% ผลตอบแทนรวม']:+.4f}%)"
                            )

                            st.markdown(f"**รายละเอียดแต่ละครั้งที่ซื้อ ({d['_lot_count']} รายการ):**")
                            df_lots = pd.DataFrame(d['_lots']).sort_values("วันที่ซื้อ")
                            st.dataframe(
                                df_lots.style.format({
                                    "ต้นทุน/หน่วย": "{:.4f}", "จำนวนหน่วย": "{:,.4f}",
                                    "มูลค่าต้นทุน": "{:,.4f}", "มูลค่าปัจจุบัน": "{:,.4f}",
                                }),
                                use_container_width=True, hide_index=True
                            )

                    st.divider()

                    # กองที่ทำผลงานดีสุด/แย่สุด (สรุปให้เห็นไวๆ ไม่ต้องไล่หาในตาราง)
                    _best = df_table.iloc[0]
                    _worst = df_table.iloc[-1]
                    _b1, _b2 = st.columns(2)
                    _b1.success(f"🏆 **ผลงานดีสุด:** {_best['ชื่อกองทุน']} ({_best['% กำไร/ขาดทุน']:+.4f}%)")
                    _b2.error(f"📉 **ผลงานแย่สุด:** {_worst['ชื่อกองทุน']} ({_worst['% กำไร/ขาดทุน']:+.4f}%)")

                    st.divider()

                    # 🆕 (5) กราฟเปรียบเทียบผลงานระหว่างกองทุน (% กำไร/ขาดทุน)
                    st.markdown("##### 📊 เปรียบเทียบ % ผลตอบแทนระหว่างกองทุน")
                    fig_compare = px.bar(
                        df_table, x='ชื่อกองทุน', y='% กำไร/ขาดทุน',
                        text=df_table['% กำไร/ขาดทุน'].apply(lambda x: f"{x:+.4f}%"),
                        color='% กำไร/ขาดทุน', color_continuous_scale=['#EF5350', '#26A69A'],
                        color_continuous_midpoint=0
                    )
                    fig_compare.update_traces(textposition='outside')
                    fig_compare.update_layout(
                        xaxis_title="", yaxis_title="% กำไร/ขาดทุน", height=380,
                        margin=dict(l=20, r=20, t=30, b=80), coloraxis_showscale=False, xaxis=dict(tickangle=-30),
                        # 🆕 แก้แท่งกราฟกว้างเกินไปตอนมีกองทุนน้อย (bargap เดิม = ค่า default ของ Plotly
                        # ~0.2 ทำให้แท่งขยายเต็มพื้นที่จนดูอ้วนเทอะทะ) เพิ่มช่องว่างระหว่างแท่งให้กว้างขึ้น
                        # แท่งจะได้ดูสมส่วนไม่ว่าจะมีกองทุนกี่กองก็ตาม
                        bargap=0.55,
                    )
                    st.plotly_chart(style_plotly(fig_compare), use_container_width=True)

                    st.divider()

                    # 🆕 (3) กราฟแนวโน้มมูลค่ากองทุนรวมตามเวลา — ใช้ข้อมูลจากชีต Fund_Value_History
                    # ที่ระบบบันทึกอัตโนมัติทุกเดือนอยู่แล้ว (ดูรายละเอียดใน check_and_auto_stamp_fund_value)
                    st.markdown("##### 📉 กราฟแนวโน้มมูลค่ากองทุนรวมตามเวลา")
                    try:
                        # 🔧 แก้บั๊กเดียวกัน: เปลี่ยนมาอ่านผ่านฟังก์ชันที่แคชไว้แทน
                        hist_data = _load_fund_value_history_cached(get_active_sheet_name())
                        if hist_data:
                            df_hist = pd.DataFrame(hist_data)
                            df_hist['Date'] = pd.to_datetime(df_hist['Date'], errors='coerce')
                            df_hist['Value'] = pd.to_numeric(df_hist['Value'], errors='coerce')
                            df_hist = df_hist.dropna(subset=['Date', 'Value']).sort_values('Date')
                            if not df_hist.empty:
                                fig_trend = go.Figure()
                                fig_trend.add_trace(go.Scatter(
                                    x=df_hist['Date'], y=df_hist['Value'], mode='lines+markers',
                                    name='มูลค่ากองทุนรวม', line=dict(width=3, color='#7C9885')
                                ))
                                fig_trend.update_layout(height=350, margin=dict(l=20, r=20, t=20, b=20), yaxis_tickformat=",.0f")
                                st.plotly_chart(style_plotly(fig_trend), use_container_width=True)
                            else:
                                st.info("ยังไม่มีข้อมูลย้อนหลังเพียงพอสำหรับวาดกราฟแนวโน้ม")
                        else:
                            st.info("ยังไม่มีข้อมูลในชีต Fund_Value_History (ระบบจะบันทึกให้อัตโนมัติทุกเดือนที่เข้าแท็บภาพรวม Net Worth)")
                    except Exception:
                        st.info("ยังไม่พบชีต Fund_Value_History — ข้อมูลจะเริ่มบันทึกอัตโนมัติเมื่อเข้าแท็บภาพรวม Net Worth ครั้งถัดไป")

                else:
                    st.info("ไม่มีกองทุนในพอร์ตที่กำลังถืออยู่")
            else:
                st.info("ยังไม่มีข้อมูลกองทุนในชีต")
        except Exception as e:
            st.warning(f"ยังไม่พบชีต Fund_History หรือเกิดข้อผิดพลาด: {e}")
