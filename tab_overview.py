# =============================================================
# tab_overview.py
# แท็บภาพรวม Net Worth & สัดส่วนสินทรัพย์ (Phase 2 ของการแยกไฟล์)
# =============================================================
import streamlit as st
import pandas as pd
import time
from datetime import date
import plotly.graph_objects as go
import plotly.express as px
from backend_functions import get_gsheet_client, get_cached_spreadsheet, get_active_sheet_name, check_and_auto_stamp_fund_value, check_and_auto_stamp_value_history, generate_net_worth_pdf_report, get_net_worth_trend_data, compute_live_net_worth
from theme import style_plotly, format_updated_badge, render_asset_card, render_hero_card, THEME_COLORS

# 🔧 _asset_card / _hero_card เดิมของไฟล์นี้ถูกย้ายไปรวมศูนย์ที่ theme.py แล้ว
# (เป็น render_asset_card / render_hero_card) เพื่อให้แท็บอื่นเรียกใช้การ์ดสไตล์เดียวกันได้โดยไม่ต้อง
# คัดลอกโค้ด HTML/CSS ซ้ำ — ปรับสไตล์การ์ดในอนาคตแก้ที่ theme.py จุดเดียวพอ ไฟล์นี้เหลือแค่เรียกใช้
_asset_card = render_asset_card
_hero_card = render_hero_card


def render_tab_overview():

    # 1. ใช้ @st.cache_data เพื่อดึงข้อมูลทุกชีตรวมกันครั้งเดียวและเก็บไว้ 10 นาที (ลดจำนวน Request มหาศาล)
    # 🔧 แก้บั๊ก: เดิมฟังก์ชันนี้ดึงข้อมูล 9 ชีตพร้อมกันแล้ว Cache รวมเป็นก้อนเดียว 10 นาที
    # ถ้าชีตใดชีตหนึ่งโหลดพลาดแค่ชีตเดียว ระบบจะจำเป็นค่าว่างของ "ทั้ง 9 ชีต" รวมกันไปเลย 10 นาที
    # (และ Cache นี้ใช้ร่วมกันทุกคนที่เปิดแอป ไม่ใช่แค่เครื่องคุณ) ทำให้ข้อมูลหายไปเป็นช่วงๆ โดยไม่ทราบสาเหตุ
    # ตอนนี้แยก Cache เป็นรายชีต ถ้าชีตไหนพลาด จะลองใหม่แค่ชีตนั้นในรอบถัดไป ไม่กระทบชีตอื่นที่โหลดสำเร็จแล้ว
    @st.cache_data(ttl=600, show_spinner=False)
    def _fetch_ws_records_safe(ws_name, active_sheet_name, max_retries=3):
        # 🔧 แก้บั๊ก: เดิมฟังก์ชันนี้ "จำ" ผลลัพธ์แยกตามชื่อชีต (ws_name) เท่านั้น โดยไม่รู้ว่า
        # ผู้ใช้คนไหนเป็นคนขอ (เรียก get_active_sheet_name() ข้างในเฉยๆ ไม่ได้รับมาเป็นพารามิเตอร์)
        # ทำให้ถ้าแฟนขอข้อมูล Fund_History ไปก่อน แล้วคุณ login มาขอชื่อชีตเดียวกัน (แค่คนละคน)
        # ระบบจะเข้าใจผิดว่าเป็นคำถามเดียวกัน แล้วส่งคำตอบเก่าของแฟนกลับมาให้แทนจนกว่าจะครบเวลา
        # 10 นาที ตอนนี้รับชื่อชีตของผู้ใช้ (active_sheet_name) เป็นพารามิเตอร์ตรงๆ เพื่อให้ระบบจำ
        # แยกตามผู้ใช้อัตโนมัติ (คนละชื่อชีต = คำถามคนละแบบ ไม่มีทางปนกัน)
        client = get_gsheet_client()
        last_error = None
        for i in range(max_retries):
            try:
                sheet = get_cached_spreadsheet(client, active_sheet_name).worksheet(ws_name)
                return sheet.get_all_records()
            except Exception as e:
                last_error = str(e)
                time.sleep(1 + i)  # หน่วงเวลาก่อนลองใหม่ (Exponential Backoff)
        raise RuntimeError(last_error or f"โหลดชีต {ws_name} ไม่สำเร็จ")

    def fetch_all_wealth_overview_data():
        def get_ws_records_safe(ws_name):
            try:
                return _fetch_ws_records_safe(ws_name, get_active_sheet_name())
            except Exception:
                return []

        return {
            "pvd": get_ws_records_safe('Provident_Fund'),
            "insurance": get_ws_records_safe('Insurance'),
            "coop": get_ws_records_safe('Coop'),
            "bank": get_ws_records_safe('Bank_Account'),
            "sso": get_ws_records_safe('SSO'),
            "pension": get_ws_records_safe('Pension'),
            "mutual_fund": get_ws_records_safe('Fund_History'),
            "real_estate": get_ws_records_safe('Real_Estate'),
            # 🔧 ปรับปรุง: หลังจัดระเบียบ tab_gold.py ใหม่ ข้อมูลทองย้ายจาก Gold_Portfolio เดิม
            # ไปเก็บคนละชีต (Gold_Physical/Gold_Trades/Gold_DCA) ใช้ Gold_Physical + Gold_DCA
            # รวมกันหาวันที่บันทึกล่าสุด (มูลค่าจริงคำนวณแยกอยู่แล้วใน compute_live_net_worth)
            "gold": get_ws_records_safe('Gold_Physical') + get_ws_records_safe('Gold_DCA'),
            "portfolio_hist": get_ws_records_safe('Stock_TFEX_History')
        }

    # เรียกใช้งานข้อมูลทั้งหมดรอบเดียวจบ
    all_data = fetch_all_wealth_overview_data()

    # 🆕 หาว่าแต่ละหมวดสินทรัพย์ (ที่กรอกข้อมูลด้วยมือ) บันทึกล่าสุดไว้เมื่อไหร่ ใช้โชว์เป็น
    # badge เล็กๆ "@DD/MM/YY" มุมขวาบนของการ์ดแต่ละใบด้านล่าง ให้รู้ว่าตัวเลขไหนอาจจะเก่าแล้ว
    _THAI_MONTHS = {
        'มกราคม': '01', 'กุมภาพันธ์': '02', 'มีนาคม': '03', 'เมษายน': '04',
        'พฤษภาคม': '05', 'มิถุนายน': '06', 'กรกฎาคม': '07', 'สิงหาคม': '08',
        'กันยายน': '09', 'ตุลาคม': '10', 'พฤศจิกายน': '11', 'ธันวาคม': '12',
    }

    def _last_row_date(rows, field='Date'):
        if not rows:
            return None
        val = rows[-1].get(field)
        return val if val not in (None, '') else None

    def _pvd_last_date(rows):
        if not rows:
            return None
        last = rows[-1]
        month_num = _THAI_MONTHS.get(last.get('Month'))
        year_ce = last.get('Year_CE')
        if month_num and year_ce:
            try:
                return f"{int(year_ce)}-{month_num}-01"
            except (ValueError, TypeError):
                return None
        return None

    def _max_field(rows, *fields):
        """หาค่าวันที่ล่าสุด (สตริงมากสุดตามลำดับตัวอักษร ใช้ได้กับฟอร์แมต YYYY-MM-DD) จากหลายแถว
        โดยลองหลายชื่อคอลัมน์ตามลำดับต่อแถว (คอลัมน์แรกที่มีค่าไม่ว่างของแต่ละแถว)"""
        dates = []
        for row in rows:
            for field in fields:
                v = row.get(field)
                if v not in (None, ''):
                    dates.append(str(v))
                    break
        return max(dates) if dates else None

    pvd_updated = _pvd_last_date(all_data["pvd"])
    insurance_updated = _last_row_date(all_data["insurance"])
    coop_updated = _last_row_date(all_data["coop"])
    sso_updated = _last_row_date(all_data["sso"])
    bank_updated = _last_row_date(all_data["bank"])
    mutual_fund_updated = _max_field(
        [r for r in all_data["mutual_fund"] if r.get('Status', 'Holding') == 'Holding'],
        'Price_Updated_Date', 'Date_Buy'
    )
    gold_updated = _max_field(all_data["gold"], 'Date')

    # --- 2. ดึงและคำนวณมูลค่าสินทรัพย์แต่ละส่วนจาก Cache ---

    # PVD (สมมติดึงแถวสุดท้ายของ Provident_Fund)
    pvd_value = 0.0
    if all_data["pvd"]:
        last_pvd = all_data["pvd"][-1]
        raw_pvd = last_pvd.get('Grand_Total', last_pvd.get('Value', 0))
        pvd_value = float(str(raw_pvd).replace(',', '')) if str(raw_pvd).strip() != "" else 0.0

    # ประกัน Unit Linked
    insurance_value = 0.0
    if all_data["insurance"]:
        last_ins = all_data["insurance"][-1]
        raw_ins = last_ins.get('Redemption_Value', last_ins.get('Value', 0))
        insurance_value = float(str(raw_ins).replace(',', '')) if str(raw_ins).strip() != "" else 0.0

    # สหกรณ์
    coop_value = 0.0
    if all_data["coop"]:
        last_coop = all_data["coop"][-1]
        raw_coop = last_coop.get('Coop_Value', last_coop.get('Value', 0))
        coop_value = float(str(raw_coop).replace(',', '')) if str(raw_coop).strip() != "" else 0.0

    # กองทุนรวม (Fund_History)
    # 🔧 แก้บั๊ก: เดิมไปดึง "แถวสุดท้าย" แถวเดียวแล้วหาฟิลด์ Value/Market_Value ซึ่งไม่มีอยู่จริง
    # ในตาราง Fund_History เพราะตารางนี้เก็บแบบ 1 แถวต่อการซื้อกองทุน 1 ครั้ง (มีคอลัมน์ราคาต้นทุน/
    # ราคาปัจจุบัน/จำนวนหน่วยแยกกัน) ไม่ใช่แบบ "ยอดรวมล่าสุด" เหมือน PVD/ประกัน/สหกรณ์
    # ต้องรวมมูลค่าปัจจุบัน (ราคาปัจจุบัน x จำนวนหน่วย) ของทุกกองทุนที่ยังถืออยู่ (Status = Holding) แทน
    mutual_fund_value = 0.0
    for fund_row in all_data["mutual_fund"]:
        if fund_row.get('Status', 'Holding') == 'Holding':
            try:
                curr_p = float(str(fund_row.get('Current_Price', 0)).replace(',', ''))
                units = float(str(fund_row.get('Units', 0)).replace(',', ''))
                mutual_fund_value += curr_p * units
            except (ValueError, TypeError):
                pass

    # 🆕 บันทึกยอดกองทุนรวมสิ้นเดือนอัตโนมัติ (ทำครั้งเดียวต่อเดือน) เพื่อใช้วาดกราฟแนวโน้มด้านล่าง
    try:
        _client_for_stamp = get_gsheet_client()
        check_and_auto_stamp_fund_value(_client_for_stamp, mutual_fund_value)
    except Exception:
        pass

    # ทองคำ + หุ้น+TFEX (คำนวณสดตรงนี้เลย)
    # 🔧 แก้บั๊ก: เดิมดึงค่าจาก st.session_state ที่ตั้งโดยแท็บหุ้น/ทองคำเท่านั้น ('total_gold_
    # portfolio_value', 'stock_net_worth', 'tfex_net_worth') ทำให้ต้องไปเยี่ยมแท็บนั้นก่อนถึงจะมี
    # ค่า — ก่อนหน้านี้ตอนใช้ st.tabs() แบบเดิม ทุกแท็บ render พร้อมกันหมดเสมอ (ค่าเลยพร้อมใช้เสมอ
    # โดยไม่รู้ตัว) แต่พอเปลี่ยนมาใช้เมนู Sidebar แบบใหม่ที่ render แค่หน้าที่เลือกอยู่เท่านั้น ค่า
    # เหล่านี้เลยเป็น 0 ค้างอยู่จนกว่าจะไปคลิกแท็บหุ้น/ทองคำเองก่อน ตอนนี้เรียก compute_live_net_
    # worth() คำนวณสดตรงนี้แทน (มี cache 5 นาทีไว้แล้ว ไม่ต้องกลัวช้า) ไม่ต้องพึ่งว่าแท็บไหนเคย
    # render ไปแล้วหรือยังเลย
    _live_net_worth = compute_live_net_worth(get_active_sheet_name())
    total_gold_value = _live_net_worth['gold_value']

    # 🆕 บันทึกยอดทองคำสิ้นเดือนอัตโนมัติ (ทำครั้งเดียวต่อเดือน) เพื่อใช้วาดกราฟแนวโน้มด้านล่าง
    # (จุดนี้เดิมไม่มีการบันทึกประวัติเลย ทำให้กราฟแนวโน้มไม่มีเส้นทองคำแสดงมาตลอด)
    try:
        _client_for_stamp = get_gsheet_client()
        check_and_auto_stamp_value_history(_client_for_stamp, 'Gold_Value_History', total_gold_value, "ทองคำ")
    except Exception:
        pass

    # ประกันสังคม
    sso_value = 0.0
    if all_data["sso"]:
        raw_sso = all_data["sso"][-1].get('Value', 0)
        sso_value = float(str(raw_sso).replace(',', '')) if str(raw_sso).strip() != "" else 0.0

    # ประกันบำนาญ (รวมทุกอายุ)
    pension_insurance_value = 0.0
    if all_data["pension"]:
        for row in all_data["pension"]:
            val_raw = row.get('Value', 0)

            # แปลงค่าให้เป็นตัวเลขที่สะอาดขึ้น
            if val_raw:
                # 1. แปลงเป็นสตริง, 2. ลบเครื่องหมายจุลภาค, 3. ลบสัญลักษณ์เงิน, 4. ลบการเว้นวรรค
                val_str = str(val_raw).replace(',', '').replace('฿', '').replace('THB', '').strip()

                # ตรวจสอบว่าเป็นตัวเลขหรือไม่ก่อนแปลง
                try:
                    val_clean = float(val_str)
                    pension_insurance_value += val_clean
                except ValueError:
                    # ถ้าแปลงไม่ได้ (เช่นเป็นคำว่า "ไม่มี" หรือว่างเปล่า) ให้ข้ามไป
                    continue

    pension_insurance_value = float(pension_insurance_value)

    # บัญชีธนาคาร
    bank_balance = 0.0
    if all_data["bank"]:
        raw_bank = all_data["bank"][-1].get('Balance', 0)
        bank_balance = float(str(raw_bank).replace(',', '')) if str(raw_bank).strip() != "" else 0.0

    # อสังหาริมทรัพย์
    house1_value = 0.0  
    house2_value = 0.0  
    condo_value = 0.0   

    real_estate_items = st.session_state.get('real_estate_portfolio', [])
    if not real_estate_items:
        real_estate_items = all_data["real_estate"]

    for item in real_estate_items:
        name = str(item.get("ชื่อทรัพย์สิน", "")).lower()
        note = str(item.get("หมายเหตุ", "")).lower()

        m_val = item.get("มูลค่าตลาด (บาท)", item.get("มูลค่าตลาด", 0))
        market_val = float(str(m_val).replace(',', '')) if str(m_val).strip() != "" else 0.0

        d_val = item.get("ยอดหนี้คงเหลือ (บาท)", item.get("ยอดหนี้คงเหลือ", 0))
        debt_val = float(str(d_val).replace(',', '')) if str(d_val).strip() != "" else 0.0

        net_val = market_val - debt_val

        if "condo" in name or "คอนโด" in name or "ดีคอนโด" in name:
            condo_value += net_val
        elif "พ่อแม่" in note or "พ่อแม่" in name:
            house2_value += net_val
        else:
            house1_value += net_val

    total_real_estate = house1_value + house2_value + condo_value
    real_estate_updated = _max_field(real_estate_items, 'วันที่บันทึก')

    # 🆕 บันทึกยอดอสังหาริมทรัพย์สิ้นเดือนอัตโนมัติ (ทำครั้งเดียวต่อเดือน) เพื่อใช้วาดกราฟแนวโน้ม
    # ด้านล่าง (จุดนี้เดิมไม่มีการบันทึกประวัติเลย ทำให้กราฟแนวโน้มไม่มีเส้นอสังหาฯ แสดงมาตลอด)
    try:
        _client_for_stamp = get_gsheet_client()
        check_and_auto_stamp_value_history(_client_for_stamp, 'Real_Estate_Value_History', total_real_estate, "อสังหาริมทรัพย์")
    except Exception:
        pass

    # พอร์ตหุ้นรวม + พอร์ต TFEX
    # 🔧 แก้บั๊ก: เดิมดึงจาก st.session_state (ปัญหาเดียวกับทองคำด้านบน) ตอนนี้ใช้ค่าที่คำนวณสดไว้
    # แล้วจาก compute_live_net_worth() ที่เรียกไว้ครั้งเดียวด้านบนสุด (ไม่ต้องเรียกซ้ำอีกรอบ
    # ประหยัดเวลา เพราะฟังก์ชันนี้ยิง API ดึงราคาหุ้นทีละตัว ค่อนข้างช้า)
    total_stock_and_tfex = _live_net_worth['stock_and_tfex_value']

    # 🆕 บันทึกยอดพอร์ตหุ้น+TFEX สิ้นเดือนอัตโนมัติ เผื่อไว้กรณีเดือนนั้นไม่มีการซื้อขายเลย
    # (ปกติมีการบันทึกอยู่แล้วทุกครั้งที่ซื้อ-ขาย ผ่าน save_portfolio_snapshot() แต่ถ้าเดือนไหน
    # ไม่มีการเทรดเลย จะไม่มีจุดข้อมูลของเดือนนั้น จุดนี้ช่วยให้มีข้อมูลครบทุกเดือนแน่นอน)
    try:
        _client_for_stamp = get_gsheet_client()
        check_and_auto_stamp_value_history(_client_for_stamp, 'Portfolio_History', total_stock_and_tfex, "พอร์ตหุ้น+TFEX")
    except Exception:
        pass

    # คำนวณ Net Worth
    net_worth_excl_re = (total_stock_and_tfex + pvd_value + insurance_value + 
                         coop_value + sso_value + pension_insurance_value + 
                         bank_balance + total_gold_value + mutual_fund_value)
    net_worth_total = net_worth_excl_re + total_real_estate

    # 🆕 เก็บค่าไว้ใน session_state ให้แท็บ "🎯 เกษียณอายุ" ดึงไปใช้ต่อได้เลย (ไม่ต้องคำนวณซ้ำ /
    # ไม่ต้องให้ผู้ใช้กรอกเอง) ปลอดภัยเพราะ Streamlit รันโค้ดของ main_tab_wealth (ที่แท็บนี้อยู่)
    # ก่อน main_tab_retirement เสมอตามลำดับการประกาศใน App.py
    st.session_state['net_worth_excl_re'] = net_worth_excl_re
    st.session_state['pvd_value'] = pvd_value

    # --- 3. แสดงผล Net Worth ทั้งสองแบบ ---
    # 🔧 ปรับปรุง: เปลี่ยนจากกล่องสีเขียวธรรมดา เป็นการ์ดสไตล์เดียวกับสินทรัพย์ย่อยด้านล่าง
    # (กรอบ/เงา/ฟอนต์เหมือนกัน) พร้อมไอคอน 💰/💎 และจัดข้อความกึ่งกลางกล่อง
    col_nw1, col_nw2 = st.columns(2)
    _hero_card(col_nw1, "💰", "Net Worth (ไม่รวมอสังหาฯ)", net_worth_excl_re)
    _hero_card(col_nw2, "💎", "Net Worth รวมทั้งหมด", net_worth_total)


    # --- 4. แสดงผลใน Metrics ย่อย ---
    with st.container(border=True):
        st.markdown("#### 💼 สินทรัพย์สภาพคล่องและการลงทุน")
        # 🔧 ปรับปรุง: เปลี่ยนจากเรียง 4-4-1 เป็น 3-3-3 (มีทั้งหมด 9 รายการพอดี) ให้ดูสมมาตร
        # สวยงามขึ้น (ไอคอน: 📈 หุ้น/TFEX, 🧺 กองทุนรวม, 🏛️ PVD, 🛡️ ประกัน, 🤝 สหกรณ์,
        # 👥 ประกันสังคม, 🏦 ธนาคาร, 🌅 บำนาญ, 🥇 ทองคำ)
        row1_col1, row1_col2, row1_col3 = st.columns(3)
        _asset_card(row1_col1, "📈", "พอร์ตหุ้น + TFEX", total_stock_and_tfex, net_worth_total)
        _asset_card(row1_col2, "🧺", "กองทุนรวม", mutual_fund_value, net_worth_total, updated_date=mutual_fund_updated)
        _asset_card(row1_col3, "🏛️", "กองทุนสำรองเลี้ยงชีพ", pvd_value, net_worth_total, updated_date=pvd_updated)

        row2_col1, row2_col2, row2_col3 = st.columns(3)
        _asset_card(row2_col1, "🛡️", "ประกัน Unit Linked", insurance_value, net_worth_total, updated_date=insurance_updated)
        _asset_card(row2_col2, "🤝", "สหกรณ์ฯ", coop_value, net_worth_total, updated_date=coop_updated)
        _asset_card(row2_col3, "👥", "ประกันสังคม", sso_value, net_worth_total, updated_date=sso_updated)

        row3_col1, row3_col2, row3_col3 = st.columns(3)
        _asset_card(row3_col1, "🏦", "บัญชีธนาคาร", bank_balance, net_worth_total, updated_date=bank_updated)
        _asset_card(row3_col2, "🌅", "ประกันบำนาญ", pension_insurance_value, net_worth_total)
        _asset_card(row3_col3, "🥇", "พอร์ตทองคำ", total_gold_value, net_worth_total, updated_date=gold_updated)

        # ย้าย Note มาไว้ใต้การ์ดประกันบำนาญ (ตอนนี้อยู่แถว 3 คอลัมน์ 2)
        if all_data["pension"]:
            pension_notes_html = '<div style="margin-top: -8px; margin-bottom: 5px;">'
            for row in all_data["pension"]:
                age_val = row.get('Age', '-')
                money_val = row.get('Value', 0)

                clean_money = float(str(money_val).replace(',', '').replace('฿', '').strip() or 0)

                if clean_money > 0:
                    pension_notes_html += (
                        f'<p style="color: {THEME_COLORS["text_secondary"]}; font-size: 0.75em; margin: 0px;">'
                        f'• ถอนออก ณ อายุ {age_val} ปี: {clean_money:,.0f} ฿'
                        f'</p>'
                    )
            pension_notes_html += '</div>'

            # แสดงผลข้อความไว้ใต้ช่องประกันบำนาญโดยตรง
            row3_col2.markdown(pension_notes_html, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # --- 5. แสดงผลอสังหาริมทรัพย์ ---
        st.markdown("#### 🏡 อสังหาริมทรัพย์")
        row_re1, row_re2, row_re3, row_re4 = st.columns(4)
        _asset_card(row_re1, "🏘️", "รวมอสังหาริมทรัพย์", total_real_estate, net_worth_total, updated_date=real_estate_updated)
        _asset_card(row_re2, "🏠", "บ้าน (ปัจจุบัน)", house1_value, total_real_estate)
        _asset_card(row_re3, "🏡", "บ้าน (พ่อแม่อยู่)", house2_value, total_real_estate)
        _asset_card(row_re4, "🏢", "คอนโด", condo_value, total_real_estate)

        # --- 5.5 รายได้เสริม (Stock Photo Income) — การ์ดข้อมูลแยกต่างหาก ไม่นับรวมใน Net Worth ---
        if get_active_sheet_name() == "MyStockData":
            # 🔧 แก้บั๊ก: เดิมค้นหาสเปรดชีตด้วยชื่อ (client.open) ทุกครั้งที่แคชข้อมูลหมดอายุ (10 นาที)
            # ซึ่งเป็นการค้นหาผ่าน Google Drive API ที่ช้ากว่าการเปิดตรงพอสมควร ทำให้การ์ดขึ้นช้า
            # ตอนแคชหมดอายุพอดี ตอนนี้แยกเป็น 2 ชั้น: จำตำแหน่งชีต (ค้นหาแค่ครั้งเดียวตลอดอายุแอพ
            # ด้วย cache_resource) กับแคชข้อมูลตัวเลข (cache_data อายุ 30 นาที ยาวขึ้นจากเดิม
            # เพราะรายได้เปลี่ยนไม่บ่อยเท่าราคาหุ้น) พร้อมใส่ spinner ให้เห็นว่ากำลังโหลดอยู่
            @st.cache_resource(show_spinner=False)
            def _get_photo_income_sheet():
                client = get_gsheet_client()
                return client.open("PhotoStockIncome").worksheet("Income")
    
            @st.cache_data(ttl=1800, show_spinner="กำลังโหลดข้อมูลรายได้เสริม...")
            def _fetch_photo_income_records():
                sheet = _get_photo_income_sheet()
                return sheet.get_all_records()
    
            try:
                _income_records = _fetch_photo_income_records()
            except Exception:
                _income_records = []
    
            if _income_records:
                _today = date.today()
                _window_keys = set()
                for _i in range(12):
                    _m = _today.month - _i
                    _y = _today.year
                    while _m <= 0:
                        _m += 12
                        _y -= 1
                    _window_keys.add((_y, _m))
    
                _total_thb = 0.0
                _active_months = set()
                for _row in _income_records:
                    try:
                        _y = int(_row.get("Year"))
                        _m = int(_row.get("Month"))
                        _thb = float(_row.get("Amount_THB") or 0)
                    except (ValueError, TypeError):
                        continue
                    if (_y, _m) in _window_keys and _thb:
                        _total_thb += _thb
                        _active_months.add((_y, _m))
    
                _avg_per_month_12m = (_total_thb / len(_active_months)) if _active_months else 0.0
    
                st.markdown("#### 💵 รายได้เสริม")
                row_income1, row_income2 = st.columns(2)
                _asset_card(row_income1, "📷", "รายได้ขายภาพสต็อก (รวม 12 เดือนล่าสุด)", _total_thb)
                _asset_card(row_income2, "📊", "เฉลี่ยต่อเดือน (12 เดือนล่าสุด)", _avg_per_month_12m)
                st.caption("💡 ยอดรายได้เสริมนี้เป็นข้อมูลอ้างอิงเท่านั้น **ไม่ถูกนับรวม** ในยอด Net Worth ด้านบน")

    st.subheader("📈 วิเคราะห์สัดส่วนสินทรัพย์สภาพคล่องและการลงทุน")

    # 1. เตรียมข้อมูลสัดส่วนสินทรัพย์
    asset_data = {
        "Asset_Type": ["พอร์ตหุ้น + TFEX", "กองทุนรวม", "PVD", "ประกัน Unit Linked", "สหกรณ์ก๊าซ ปตท.", "ประกันสังคม", "บัญชีธนาคาร", "ประกันบำนาญ", "ทองคำ"],
        "Value": [total_stock_and_tfex, mutual_fund_value, pvd_value, insurance_value, coop_value, sso_value, bank_balance, pension_insurance_value, total_gold_value]
    }
    df_assets = pd.DataFrame(asset_data)
    df_assets = df_assets[df_assets["Value"] > 0]

    with st.container(border=True):
        col_chart1, col_chart2 = st.columns(2)

        with col_chart1:
            st.markdown("### 🍩 สัดส่วนสินทรัพย์ปัจจุบัน")
            if not df_assets.empty:
                import plotly.express as px
                fig_donut = px.pie(
                    df_assets, names="Asset_Type", values="Value", hole=0.4,
                    color_discrete_sequence=px.colors.qualitative.Pastel
                )
                fig_donut.update_traces(textposition='inside', textinfo='percent+label')
                fig_donut.update_layout(margin=dict(t=10, b=10, l=10, r=10), showlegend=False)
                st.plotly_chart(style_plotly(fig_donut), use_container_width=True, key="donut_main_chart")
            else:
                st.info("ยังไม่มีข้อมูลสำหรับแสดงกราฟโดนัท")

        with col_chart2:
            st.markdown("### 📊 มูลค่าแยกตามประเภทสินทรัพย์")
            if not df_assets.empty:
                fig_bar = px.bar(
                    df_assets, x="Asset_Type", y="Value", text="Value",
                    color="Asset_Type", color_discrete_sequence=px.colors.qualitative.Pastel
                )
                fig_bar.update_traces(texttemplate='%{text:,.0f} ฿', textposition='outside')
                fig_bar.update_layout(margin=dict(t=10, b=10, l=10, r=10), showlegend=False, xaxis_title="", yaxis_title="บาท")
                st.plotly_chart(style_plotly(fig_bar), use_container_width=True, key="bar_main_chart")
            else:
                st.info("ยังไม่มีข้อมูลสำหรับแสดงกราฟแท่ง")

    # 2. กราฟแนวโน้ม Net Worth (ดึงข้อมูลใหม่แบบรวมศูนย์)
    with st.container(border=True):
        st.markdown("### 📉 กราฟแนวโน้มการเติบโตของความมั่งคั่งสุทธิ (Net Worth)")

        try:
            import time

            # 🔧 แก้บั๊ก: เดิมจุดนี้มี Cache ซ้อนอีกชั้น (@st.cache_data ครอบทั้ง 7 ชีต) แยกต่างหาก
            # จากตัวช่วย _fetch_ws_records_safe ด้านบน ทำให้เกิดปัญหาเดียวกัน คือถ้าชีตใดชีตหนึ่งพลาด
            # กราฟทั้งหมดจะหายไป 10 นาที ตอนนี้เปลี่ยนมาใช้ _fetch_ws_records_safe ตัวเดียวกับแท็บภาพรวม
            # ซึ่งจำผลแยกเป็นรายชีตอยู่แล้ว จึงไม่ต้อง Cache ซ้อนอีกชั้น
            def fetch_all_wealth_data():
                def get_df_safe(ws_name):
                    try:
                        return pd.DataFrame(_fetch_ws_records_safe(ws_name, get_active_sheet_name()))
                    except Exception:
                        return pd.DataFrame()

                # 🔧 แก้บั๊ก: เดิมดึงชื่อชีต 'Stock_TFEX_History' ซึ่งไม่มีอยู่จริง (ชีตที่บันทึกจริง
                # ชื่อ 'Portfolio_History' ต่างหาก) ทำให้เส้น Stock+TFEX ในกราฟไม่เคยมีข้อมูลเลย
                # ตั้งแต่ต้น ตอนนี้แก้ให้ตรงกับชื่อชีตจริง พร้อมเพิ่มทองคำ/อสังหาริมทรัพย์ที่หายไป
                # จากกราฟมาตลอด (เพิ่งเพิ่มการบันทึกประวัติให้ 2 ประเภทนี้ด้านบน)
                return (get_df_safe('Provident_Fund'), get_df_safe('Insurance'), 
                        get_df_safe('Coop'), get_df_safe('Bank_Account'), 
                        get_df_safe('SSO'), get_df_safe('Fund_Value_History'), 
                        get_df_safe('Portfolio_History'), get_df_safe('Gold_Value_History'),
                        get_df_safe('Real_Estate_Value_History'))

            df_pvd, df_ins, df_coop, df_bank, df_sso, df_mf, df_portfolio_hist, df_gold, df_re = fetch_all_wealth_data()

            def prepare_series(df, date_col, val_col, name):
                df = df.copy()
                if df.empty: return pd.DataFrame(columns=[name], index=pd.to_datetime([]))
                # 🔧 แก้บั๊ก: เดิมถ้าชื่อคอลัมน์ที่คาดไว้ (val_col) ไม่ตรงกับที่มีอยู่จริงในชีต
                # (เช่น ชื่อหัวตารางที่คนตั้งไว้ไม่ตรงกับที่โค้ดคาดเดา) จะ error แล้วลากทั้งกราฟทุกเส้น
                # พังไปด้วย (เพราะครอบด้วย try/except ใหญ่อันเดียวทั้งบล็อก) ตอนนี้เช็คก่อนเสมอว่า
                # คอลัมน์ที่ต้องการมีอยู่จริงไหม ถ้าไม่มี ข้ามแค่เส้นนี้เส้นเดียว เส้นอื่นยังแสดงได้ปกติ
                if val_col not in df.columns or date_col not in df.columns:
                    st.caption(f"⚠️ ไม่พบคอลัมน์ '{val_col}' หรือ '{date_col}' ในชีตของ{name} (ข้ามเส้นนี้ไปก่อน)")
                    return pd.DataFrame(columns=[name], index=pd.to_datetime([]))
                if date_col == 'Month':
                    thai_months = {'มกราคม': '01', 'กุมภาพันธ์': '02', 'มีนาคม': '03', 'เมษายน': '04', 'พฤษภาคม': '05', 'มิถุนายน': '06', 'กรกฎาคม': '07', 'สิงหาคม': '08', 'กันยายน': '09', 'ตุลาคม': '10', 'พฤศจิกายน': '11', 'ธันวาคม': '12'}
                    df['Month_Num'] = df[date_col].map(thai_months).fillna('12')
                    df['Date'] = pd.to_datetime(df['Year_CE'].astype(str) + '-' + df['Month_Num'] + '-01', errors='coerce')
                else:
                    df['Date'] = pd.to_datetime(df[date_col], errors='coerce')
                df[name] = df[val_col].astype(str).str.replace(',', '').astype(float)
                return df.dropna(subset=['Date']).set_index('Date')[[name]]

            s_pvd = prepare_series(df_pvd, 'Month', 'Grand_Total', 'PVD')
            s_ins = prepare_series(df_ins, 'Date', 'Redemption_Value', 'Insurance')
            s_sso = prepare_series(df_sso, 'Date', 'Value', 'SSO')
            s_coop = prepare_series(df_coop, 'Date', 'Coop_Value', 'Coop')
            s_bank = prepare_series(df_bank, 'Date', 'Balance', 'Bank')
            # 🆕 ตอนนี้ df_mf ดึงจากชีต Fund_Value_History (ยอดรวมรายเดือนที่บันทึกอัตโนมัติ)
            # แทนที่จะเป็น Fund_History เดิม (รายการซื้อแต่ละครั้ง) จึงมีคอลัมน์ Date/Value ให้ใช้ตรงๆ ได้แล้ว
            s_mf = prepare_series(df_mf, 'Date', 'Value', 'Mutual_Fund')
            # 🔧 แก้บั๊ก: คอลัมน์จริงในชีต Portfolio_History ชื่อ 'Market_Value' (เช็คกับผู้ใช้แล้ว
            # ยืนยันตรงกัน ไม่ใช่ 'total_equity' หรือ 'Total_Value' ที่เดาไว้ก่อนหน้า)
            s_port = prepare_series(df_portfolio_hist, 'Date', 'Market_Value', 'Stock+TFEX')
            # 🆕 เพิ่มเส้นทองคำและอสังหาริมทรัพย์ที่หายไปจากกราฟแนวโน้มมาตลอด
            s_gold = prepare_series(df_gold, 'Date', 'Value', 'Gold')
            s_re = prepare_series(df_re, 'Date', 'Value', 'Real_Estate')

            if not s_ins.empty and not s_sso.empty:
                s_ins = s_ins.join(s_sso, how='outer').sort_index().ffill().fillna(0)
                s_ins['Insurance'] = s_ins['Insurance'] + s_ins['SSO']
                s_ins = s_ins[['Insurance']]
            elif s_ins.empty and not s_sso.empty:
                s_ins = s_sso.rename(columns={'SSO': 'Insurance'})

            series_list = [s for s in [s_pvd, s_ins, s_coop, s_bank, s_mf, s_port, s_gold, s_re] if not s.empty]

            if series_list:
                df_merged = series_list[0]
                for s in series_list[1:]: df_merged = df_merged.join(s, how='outer')
                df_merged = df_merged.sort_index().ffill().fillna(0)
                df_merged['Total'] = df_merged.sum(axis=1)

                import plotly.graph_objects as go
                fig = go.Figure()
                for col in df_merged.columns:
                    fig.add_trace(go.Scatter(x=df_merged.index, y=df_merged[col], name=col, mode='lines+markers', line=dict(width=3 if col == 'Total' else 2)))

                fig.update_layout(yaxis=dict(range=[0, (df_merged['Total'].max() * 1.2) if df_merged['Total'].max() > 0 else 12000000], tickformat=",.0f"),
                                  legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))

                st.plotly_chart(style_plotly(fig), use_container_width=True, key="net_worth_trend_chart_final")
            else:
                st.info("💡 ยังไม่มีข้อมูลเพียงพอสำหรับแสดงกราฟแนวโน้ม")
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการดึงข้อมูลกราฟ: {e}")

    # 3. ปุ่มส่งออกรายงาน Net Worth เป็น PDF
    # 🆕 รายงานเป็นภาษาอังกฤษ (ตามที่ตกลงไว้) เพื่อไม่ต้องฝังไฟล์ฟอนต์ไทยเพิ่มเติมใน repo
    # (ฟอนต์มาตรฐานของ reportlab ไม่รองรับภาษาไทย) ใช้ตัวเลขที่คำนวณไว้แล้วด้านบนทั้งหมด
    # ไม่ต้องคำนวณซ้ำ
    st.divider()
    with st.container(border=True):
        st.markdown("### 📄 ส่งออกรายงาน Net Worth")
        st.caption("สร้างรายงานสรุปสินทรัพย์ทั้งหมดเป็นไฟล์ PDF ดาวน์โหลดเก็บไว้ดูนอกแอปได้ (ภาษาอังกฤษ)")
        try:
            _pdf_app_title = st.session_state.get("app_title", "Wealth Report")
            _pdf_asset_breakdown = [
                ("Stock + TFEX Portfolio", total_stock_and_tfex),
                ("Mutual Funds", mutual_fund_value),
                ("Provident Fund (PVD)", pvd_value),
                ("Unit-Linked Insurance", insurance_value),
                ("Cooperative Fund", coop_value),
                ("Social Security Fund", sso_value),
                ("Bank Accounts", bank_balance),
                ("Pension Insurance", pension_insurance_value),
                ("Gold", total_gold_value),
                ("Real Estate", total_real_estate),
            ]
            # 🆕 ดึงข้อมูลแนวโน้มมาใส่กราฟเส้นในรายงานด้วย (ใช้ฟังก์ชันกลางเดียวกับที่วาดกราฟ
            # แนวโน้มด้านบนของหน้านี้ และเดียวกับที่สคริปต์รายงานอัตโนมัติรายเดือนใช้)
            _trend_df_for_pdf = get_net_worth_trend_data(get_active_sheet_name())
            _pdf_bytes = generate_net_worth_pdf_report(
                _pdf_app_title, net_worth_excl_re, net_worth_total, _pdf_asset_breakdown,
                trend_df=_trend_df_for_pdf
            )
            st.download_button(
                "📥 ดาวน์โหลดรายงาน PDF",
                data=_pdf_bytes,
                file_name=f"net_worth_report_{date.today().strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
        except Exception as e:
            st.warning(f"ยังไม่สามารถสร้างรายงาน PDF ได้ในขณะนี้: {e}")
