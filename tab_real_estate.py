# =============================================================
# tab_real_estate.py
# แท็บจัดการพอร์ตอสังหาริมทรัพย์ (Phase 2 ของการแยกไฟล์)
# =============================================================
import streamlit as st
import pandas as pd
import time
from datetime import datetime
from backend_functions import get_gsheet_client, get_worksheet_safely


def render_tab_real_estate():

    st.markdown("### 🏠 จัดการพอร์ตอสังหาริมทรัพย์ (บ้าน / คอนโด)")
    st.markdown("บันทึกมูลค่าประเมินปัจจุบันและหักลบด้วยยอดหนี้คงเหลือ เพื่อคำนวณมูลค่าสุทธิ (Equity) เข้าพอร์ตความมั่งคั่ง")

    # ฟังก์ชันดึงข้อมูลชีต Real_Estate พร้อมระบบ Cache และ Retry อัตโนมัติ ป้องกันการติด Limit API
    # 🔧 แก้บั๊ก: ถ้าโหลดไม่สำเร็จหลังลองครบ 3 ครั้ง ให้ "โยน error" ออกไป แทนที่จะคืนค่า [] เงียบๆ
    # เพราะถ้าคืน [] เฉยๆ ระบบจะเข้าใจผิดว่า "โหลดสำเร็จแต่ไม่มีข้อมูล" แล้วจะไม่ยอมลองโหลดใหม่อีกเลย
    @st.cache_data(ttl=600, show_spinner=False)
    def fetch_real_estate_data_cached():
        client = get_gsheet_client()
        last_error = None
        for attempt in range(3):
            try:
                sheet_re = get_worksheet_safely(client, 'MyStockData', 'Real_Estate')
                if sheet_re is not None:
                    return sheet_re.get_all_records()
                last_error = "ไม่พบชีต Real_Estate"
            except Exception as e:
                last_error = str(e)
            time.sleep(1 + attempt)
        raise RuntimeError(last_error or "โหลดข้อมูลไม่สำเร็จ")

    # ฟังก์ชันช่วยบันทึกข้อมูลลง Google Sheets พร้อม Retry ป้องกัน API พัง
    def save_real_estate_to_sheet_safe(portfolio_items):
        client = get_gsheet_client()
        for attempt in range(3):
            try:
                sheet_re = get_worksheet_safely(client, 'MyStockData', 'Real_Estate')
                if sheet_re is not None:
                    sheet_re.clear()
                    sheet_re.append_row(["ชื่อทรัพย์สิน", "มูลค่าตลาด (บาท)", "ยอดหนี้คงเหลือ (บาท)", "มูลค่าสุทธิ (บาท)", "หมายเหตุ", "วันที่บันทึก"])

                    current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    rows_to_append = []
                    for item in portfolio_items:
                        net_val = item["มูลค่าตลาด"] - item["ยอดหนี้คงเหลือ"]
                        rows_to_append.append([
                            item["ชื่อทรัพย์สิน"],
                            item["มูลค่าตลาด"],
                            item["ยอดหนี้คงเหลือ"],
                            net_val,
                            item["หมายเหตุ"],
                            current_date
                        ])
                    if rows_to_append:
                        sheet_re.append_rows(rows_to_append)

                    # เคลียร์ Cache ทันทีที่มีการเปลี่ยนแปลงข้อมูล เพื่อให้ดึงข้อมูลล่าสุดรอบหน้า
                    fetch_real_estate_data_cached.clear()
                    return True
            except Exception:
                time.sleep(1.5 + attempt)
        return False

    # ปุ่มโหลดข้อมูลใหม่ (เคลียร์ Cache และ Session)
    col_r1, col_r2 = st.columns([3, 1])
    with col_r2:
        if st.button("🔄 โหลดข้อมูลใหม่จาก Sheet", key="btn_reload_re"):
            fetch_real_estate_data_cached.clear()
            if 'real_estate_portfolio' in st.session_state:
                del st.session_state['real_estate_portfolio']
            if 're_table_selection' in st.session_state:
                del st.session_state['re_table_selection']
            st.success("รีเซ็ตข้อมูลสำเร็จ กำลังโหลดใหม่...")
            st.rerun()

    # โหลดข้อมูลจาก Google Sheets / Cache เข้า session_state
    # 🔧 แก้บั๊ก: ถ้าโหลดไม่สำเร็จ จะ "ไม่" ตั้งค่า session_state ให้เป็น [] เพื่อให้ระบบลองโหลดใหม่
    # อัตโนมัติในรอบถัดไปที่หน้าเว็บรีเฟรช (เช่น สลับแท็บ, กดปุ่มอื่น) โดยไม่ต้องรอให้ผู้ใช้กดปุ่ม reload เอง
    if 'real_estate_portfolio' not in st.session_state:
        try:
            records = fetch_real_estate_data_cached()
            loaded_items = []
            for row in records:
                asset_name = str(row.get("ชื่อทรัพย์สิน", "")).strip()
                if asset_name != "":
                    m_raw = row.get("มูลค่าตลาด (บาท)", row.get("มูลค่าตลาด", 0))
                    m_val = float(str(m_raw).replace(',', '')) if str(m_raw).strip() != "" else 0.0

                    d_raw = row.get("ยอดหนี้คงเหลือ (บาท)", row.get("ยอดหนี้คงเหลือ", 0))
                    d_val = float(str(d_raw).replace(',', '')) if str(d_raw).strip() != "" else 0.0

                    n_val = str(row.get("หมายเหตุ", ""))

                    loaded_items.append({
                        "ชื่อทรัพย์สิน": asset_name,
                        "มูลค่าตลาด": m_val,
                        "ยอดหนี้คงเหลือ": d_val,
                        "หมายเหตุ": n_val
                    })
            # ตั้งค่า session_state ก็ต่อเมื่อโหลดสำเร็จเท่านั้น (ไม่ว่าจะมีข้อมูลจริงหรือว่างเปล่าจริงๆ ก็ตาม)
            st.session_state['real_estate_portfolio'] = loaded_items
        except Exception as e:
            st.warning(f"⚠️ ไม่สามารถโหลดข้อมูลอสังหาฯ จาก Google Sheets ได้ กำลังจะลองใหม่อัตโนมัติ: {e}")

    st.markdown("---")
    st.markdown("#### 📝 เพิ่ม / แก้ไขข้อมูลอสังหาริมทรัพย์")
    st.info("💡 **วิธีแก้ไข:** คลิกเลือกแถวที่ต้องการในตารางด้านล่าง ข้อมูลจะวิ่งขึ้นมาที่ฟอร์มนี้ให้อัตโนมัติ")

    # ตรวจสอบว่ามีการคลิกเลือกแถวจากตารางด้านล่างหรือไม่
    selected_indices = st.session_state.get("re_table_selection", {}).get("selection", {}).get("rows", [])

    default_name = ""
    default_market = 0.0
    default_debt = 0.0
    default_note = ""
    is_editing = False

    if selected_indices and len(st.session_state['real_estate_portfolio']) > 0:
        idx = selected_indices[0]
        if idx < len(st.session_state['real_estate_portfolio']):
            target_item = st.session_state['real_estate_portfolio'][idx]
            default_name = target_item["ชื่อทรัพย์สิน"]
            default_market = target_item["มูลค่าตลาด"]
            default_debt = target_item["ยอดหนี้คงเหลือ"]
            default_note = target_item["หมายเหตุ"]
            is_editing = True
            st.success(f"กำลังเลือกแก้ไขทรัพย์สิน: **{default_name}**")

    # ฟอร์มรับข้อมูล
    with st.form("real_estate_form"):
        col_re1, col_re2 = st.columns(2)

        with col_re1:
            if not is_editing:
                re_name = st.text_input("ชื่อทรัพย์สิน", placeholder="เช่น คอนโดสุขุมวิท, บ้านเดี่ยวบางนา", key="form_re_name")
            else:
                st.text(f"ชื่อทรัพย์สิน (ล็อคไว้เพื่อแก้ไข): {default_name}")
                re_name = default_name

            re_market_value = st.number_input("มูลค่าประเมินตลาดปัจจุบัน (บาท)", min_value=0.0, step=50000.0, value=float(default_market), key="form_re_market")

        with col_re2:
            re_debt = st.number_input("ยอดหนี้คงเหลือกับธนาคาร (บาท)", min_value=0.0, step=10000.0, value=float(default_debt), key="form_re_debt")
            re_note = st.text_input("หมายเหตุ / ทำเล", value=str(default_note), placeholder="เช่น ปล่อยเช่าอยู่, อยู่เอง", key="form_re_note")

        btn_label = "💾 บันทึกการแก้ไข" if is_editing else "➕ เพิ่มอสังหาริมทรัพย์เข้าพอร์ต"
        re_submitted = st.form_submit_button(btn_label)

        if re_submitted:
            if re_name and re_market_value > 0:
                if not is_editing:
                    if any(item["ชื่อทรัพย์สิน"] == re_name for item in st.session_state['real_estate_portfolio']):
                        st.error(f"มีทรัพย์สินชื่อ '{re_name}' อยู่แล้วในระบบ กรุณาคลิกเลือกแถวเดิมในตารางหากต้องการแก้ไข")
                        st.stop()
                    else:
                        st.session_state['real_estate_portfolio'].append({
                            "ชื่อทรัพย์สิน": re_name,
                            "มูลค่าตลาด": re_market_value,
                            "ยอดหนี้คงเหลือ": re_debt,
                            "หมายเหตุ": re_note
                        })
                else:
                    for item in st.session_state['real_estate_portfolio']:
                        if item["ชื่อทรัพย์สิน"] == default_name:
                            item["มูลค่าตลาด"] = re_market_value
                            item["ยอดหนี้คงเหลือ"] = re_debt
                            item["หมายเหตุ"] = re_note
                            break

                # บันทึกลง Google Sheets ผ่านระบบปลอดภัยที่เตรียมไว้
                saved_success = save_real_estate_to_sheet_safe(st.session_state['real_estate_portfolio'])

                if saved_success:
                    st.success(f"บันทึกข้อมูล '{re_name}' สำเร็จ!")
                    st.rerun()
                else:
                    st.error("⚠️ บันทึกลง Google Sheets ไม่สำเร็จเนื่องจากติดขีดจำกัด API หรือเชื่อมต่อไม่ได้ กรุณาลองใหม่อีกครั้ง")
            else:
                st.error("กรุณากรอกชื่อทรัพย์สินและมูลค่าประเมินตลาดให้ถูกต้อง")

    # แสดงผลตารางสรุป พร้อมเปิดใช้งานการคลิกเลือกแถว (Selection)
    if 'real_estate_portfolio' in st.session_state and len(st.session_state['real_estate_portfolio']) > 0:
        st.markdown("#### 📊 สรุปมูลค่าสุทธิอสังหาริมทรัพย์ (คลิกแถวเพื่อแก้ไข)")

        df_re = pd.DataFrame(st.session_state['real_estate_portfolio'])
        df_re["มูลค่าสุทธิ (บาท)"] = df_re["มูลค่าตลาด"] - df_re["ยอดหนี้คงเหลือ"]

        event_selection = st.dataframe(
            df_re.style.format({
                "มูลค่าตลาด": "{:,.2f}",
                "ยอดหนี้คงเหลือ": "{:,.2f}",
                "มูลค่าสุทธิ (บาท)": "{:,.2f}"
            }),
            use_container_width=True,
            selection_mode="single-row",
            on_select="rerun",
            key="re_table_selection"
        )

        total_re_value = df_re["มูลค่าสุทธิ (บาท)"].sum()
        st.session_state['total_real_estate_value'] = total_re_value

        col_m1, col_m2 = st.columns([2, 1])
        col_m1.metric("🏡 มูลค่าสุทธิอสังหาริมทรัพย์รวม (Equity)", f"{total_re_value:,.2f} ฿")

        existing_names = [item["ชื่อทรัพย์สิน"] for item in st.session_state['real_estate_portfolio']]
        with col_m2:
            if existing_names:
                del_target = st.selectbox("เลือกรายการที่จะลบ", existing_names, key="re_del_select")
                if st.button("🗑️ ลบรายการที่เลือก", key="btn_del_single_re"):
                    st.session_state['real_estate_portfolio'] = [item for item in st.session_state['real_estate_portfolio'] if item["ชื่อทรัพย์สิน"] != del_target]
                    save_real_estate_to_sheet_safe(st.session_state['real_estate_portfolio'])
                    st.success(f"ลบ {del_target} สำเร็จ")
                    st.rerun()

                if st.button("🗑️ ล้างข้อมูลอสังหาริมทรัพย์ทั้งหมด", key="btn_clear_all_re"):
                    st.session_state['real_estate_portfolio'] = []
                    st.session_state['total_real_estate_value'] = 0.0
                    save_real_estate_to_sheet_safe([])
                    st.rerun()
    else:
        st.info("ยังไม่มีข้อมูลอสังหาริมทรัพย์ กรุณากดปุ่ม '🔄 โหลดข้อมูลใหม่จาก Sheet' ด้านบน")
