# =============================================================
# tab_pvd.py
# แท็บบันทึกข้อมูล PVD / สหกรณ์ / ประกัน / ธนาคาร (Phase 2 ของการแยกไฟล์)
# =============================================================
import streamlit as st
import pandas as pd
import time
import plotly.graph_objects as go
from datetime import date, datetime
from backend_functions import extract_pvd_from_image, get_cached_spreadsheet, get_gsheet_client, get_worksheet_safely


def render_tab_pvd():
    st.markdown("### 📝 บันทึกและอัปเดตข้อมูลสินทรัพย์ระยะยาว")

    # --- 1. ส่วน PVD (รวมฟอร์มและตารางสรุปไว้ใน Expander เดียวกัน) ---
    with st.expander("📤 เพิ่ม/อัปเดตข้อมูลกองทุนสำรองเลี้ยงชีพ (PVD) รายเดือน", expanded=False):
        with st.form("pvd_upload_form"):
            col_y1, col_y2, col_m = st.columns(3)

            with col_y1:
                input_year_be = st.number_input("ปี พ.ศ.", min_value=2500, max_value=2570, value=2569)
            with col_y2:
                st.info(f"ค.ศ.: **{int(input_year_be) - 543}**")
            with col_m:
                months_list = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", 
                               "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
                selected_month = st.selectbox("เลือกเดือน", months_list)

            uploaded_pvd_file = st.file_uploader("อัปโหลดรูปภาพรายงาน PVD รายเดือน (JPG, PNG)", type=["jpg", "jpeg", "png"])

            submitted_pvd = st.form_submit_button("🔍 อ่านข้อมูลจากรูปภาพด้วย AI")

            if submitted_pvd:
                if uploaded_pvd_file is not None:
                    with st.spinner("กำลังให้ AI อ่านและวิเคราะห์ข้อมูลจากภาพ..."):
                        df_extracted = extract_pvd_from_image(uploaded_pvd_file, input_year_be, selected_month)

                        if df_extracted is not None and not df_extracted.empty:
                            if 'Month' not in df_extracted.columns:
                                df_extracted.insert(0, 'Month', selected_month)

                            st.success("อ่านข้อมูลสำเร็จ! ตรวจสอบความถูกต้องด้านล่าง:")
                            st.dataframe(df_extracted, use_container_width=True)

                            st.session_state['temp_pvd_df'] = df_extracted
                        else:
                            st.warning("ไม่สามารถดึงข้อมูลจากรูปภาพได้ กรุณาลองใหม่อีกครั้ง")
                else:
                    st.warning("กรุณาอัปโหลดรูปภาพก่อนกดปุ่มประมวลผล")

        # ส่วนยืนยันบันทึกข้อมูล (อยู่นอกฟอร์มหลัก แต่ยังอยู่ใน Expander)
        if 'temp_pvd_df' in st.session_state and st.session_state['temp_pvd_df'] is not None:
            st.write("---")
            st.write("📋 **ข้อมูลที่พร้อมบันทึก:**")
            st.dataframe(st.session_state['temp_pvd_df'], use_container_width=True)

            if st.button("💾 ยืนยันบันทึกข้อมูลนี้ลง Google Sheets", key="confirm_pvd_save"):
                try:
                    client = get_gsheet_client()
                    sheet = get_cached_spreadsheet(client, 'MyStockData').worksheet('Provident_Fund')

                    existing_data = sheet.get_all_records()
                    df_existing = pd.DataFrame(existing_data) if existing_data else pd.DataFrame()

                    df_to_save = st.session_state['temp_pvd_df'].fillna(0)

                    is_duplicate = False
                    if not df_existing.empty and 'Month' in df_existing.columns and 'Year_BE' in df_existing.columns:
                        match_idx = df_existing[
                            (df_existing['Year_BE'].astype(str) == str(input_year_be)) & 
                            (df_existing['Month'] == selected_month)
                        ].index

                        if len(match_idx) > 0:
                            is_duplicate = True
                            row_number_to_update = match_idx[0] + 2 

                            values_to_write = list(df_to_save.iloc[0].values)
                            sheet.update(f"A{row_number_to_update}", [values_to_write])
                            st.success(f"✅ อัปเดตข้อมูลของ **{selected_month} พ.ศ. {input_year_be}** เรียบร้อยแล้ว")

                    if not is_duplicate:
                        for row in df_to_save.values.tolist():
                            sheet.append_row(row)
                        st.success(f"✅ บันทึกข้อมูลใหม่ของ **{selected_month} พ.ศ. {input_year_be}** เรียบร้อยแล้ว!")

                    del st.session_state['temp_pvd_df']

                    # 👇 --- แทรกตรงนี้ครับ เพื่อรอให้ Google Sheets บันทึกข้อมูลเสร็จและเคลียร์แคชก่อนรีรัน ---
                    import time
                    time.sleep(1.5)
                    st.cache_data.clear()
                    # --------------------------------------------------------------------------------

                    st.rerun()

                except Exception as e:
                    if "429" in str(e) or "Quota exceeded" in str(e):
                        st.error("❌ Google Sheets API เกินโควตาชั่วคราว (Rate Limit 429) กรุณารอสัก 30 วินาที แล้วลองกดบันทึกใหม่อีกครั้งครับ")
                    else:
                        st.error(f"❌ เกิดข้อผิดพลาดในการบันทึก: {e}")

        # --- 1. ดึงข้อมูลจาก Google Sheets มาเตรียมไว้ก่อน ---
        df_pvd_history = pd.DataFrame()
        try:
            client = get_gsheet_client()
            sheet_pvd = get_cached_spreadsheet(client, 'MyStockData').worksheet('Provident_Fund')
            pvd_records = sheet_pvd.get_all_records()
            if pvd_records:
                df_pvd_history = pd.DataFrame(pvd_records)
        except Exception as e:
            pass

        # --- ส่วนแสดงกราฟแท่ง % ผลตอบแทน (% Benefit) คำนวณอัตโนมัติจากข้อมูลที่มี ---
        st.markdown("---")
        st.subheader("📊 กราฟแสดง % ผลตอบแทนรายบุคคล (YTD Net Return %)")

        if not df_pvd_history.empty:
            try:
                def clean_num(series):
                    if series is None:
                        return pd.Series(0.0, index=df_pvd_history.index)
                    return pd.to_numeric(
                        series.astype(str)
                        .str.replace(',', '', regex=False)
                        .str.replace(' ', '', regex=False)
                        .str.replace('%', '', regex=False),
                        errors='coerce'
                    ).fillna(0.0)

                # ดึงข้อมูลจากคอลัมน์ YTD_Net_Return_Pct โดยตรง
                if 'YTD_Net_Return_Pct' in df_pvd_history.columns:
                    chart_col = 'YTD_Net_Return_Pct'
                    df_pvd_history[chart_col] = clean_num(df_pvd_history[chart_col])
                else:
                    # เผื่อกรณียังไม่มีคอลัมน์นี้ในชีต ให้สร้างเป็น 0 ไปก่อนเพื่อกัน error
                    df_pvd_history['YTD_Net_Return_Pct'] = 0.0
                    chart_col = 'YTD_Net_Return_Pct'

            except Exception as e:
                st.warning(f"⚠️ เกิดข้อผิดพลาดในการอ่านข้อมูลกราฟ: {e}")
                chart_col = None

            if chart_col and chart_col in df_pvd_history.columns:
                if 'Month' in df_pvd_history.columns and 'Year_BE' in df_pvd_history.columns:
                    # 🔧 แก้บั๊ก: เรียงลำดับข้อมูลตามปี พ.ศ. และเดือนจริงๆ ก่อนสร้างกราฟ
                    # (เดิมกราฟแสดงตามลำดับแถวที่กรอกใน Google Sheets ทำให้เดือนสลับกัน)
                    thai_month_order = {
                        "มกราคม": 1, "กุมภาพันธ์": 2, "มีนาคม": 3, "เมษายน": 4,
                        "พฤษภาคม": 5, "มิถุนายน": 6, "กรกฎาคม": 7, "สิงหาคม": 8,
                        "กันยายน": 9, "ตุลาคม": 10, "พฤศจิกายน": 11, "ธันวาคม": 12
                    }
                    df_pvd_sorted = df_pvd_history.copy()
                    df_pvd_sorted['_Month_Num'] = df_pvd_sorted['Month'].map(thai_month_order).fillna(0).astype(int)
                    df_pvd_sorted['_Year_Num'] = pd.to_numeric(df_pvd_sorted['Year_BE'], errors='coerce').fillna(0).astype(int)
                    df_pvd_sorted = df_pvd_sorted.sort_values(by=['_Year_Num', '_Month_Num'])

                    df_pvd_sorted['Period'] = df_pvd_sorted['Month'].astype(str) + " " + df_pvd_sorted['Year_BE'].astype(str)
                    chart_data = df_pvd_sorted.set_index('Period')[chart_col]
                else:
                    chart_data = df_pvd_history[chart_col]

                chart_data = pd.to_numeric(chart_data, errors='coerce').fillna(0.0)

                # แสดงกราฟแท่ง (เปลี่ยนมาใช้ Plotly เพื่อกำหนดสีแยกตามค่าบวก/ลบได้)
                # 🎨 บวก = เขียว, ลบ = แดง
                bar_colors = ['#2ECC71' if v >= 0 else '#E74C3C' for v in chart_data]
                fig_pvd = go.Figure(data=[
                    go.Bar(
                        x=chart_data.index.tolist(),
                        y=chart_data.values.tolist(),
                        marker_color=bar_colors
                    )
                ])
                fig_pvd.update_layout(
                    height=400,
                    margin=dict(l=20, r=20, t=20, b=20),
                    yaxis_title="YTD Net Return (%)"
                )
                st.plotly_chart(fig_pvd, use_container_width=True)
            else:
                st.info("💡 ไม่สามารถสร้างกราฟได้ เนื่องจากข้อมูลคอลัมน์ไม่เพียงพอ")
        else:
            st.info("💡 ยังไม่มีข้อมูลสำหรับแสดงกราฟ กรุณาอัปโหลดข้อมูลก่อนครับ")

        # --- 3. ส่วนแสดงตารางสรุปการเติบโต ---
        st.markdown("---")
        st.subheader("📈 ตารางสรุปการเติบโตและผลตอบแทนกองทุน PVD")
        if not df_pvd_history.empty:
            if 'Year_BE' in df_pvd_history.columns:
                df_pvd_history['Year_BE'] = pd.to_numeric(df_pvd_history['Year_BE'], errors='coerce')
            st.dataframe(df_pvd_history, use_container_width=True, hide_index=True)
        else:
            st.info("ยังไม่มีข้อมูลประวัติในชีต Provident_Fund")

    # --- 2. ส่วนประกันภัย Unit Linked ---
    with st.expander("📤 เพิ่ม/อัปเดตข้อมูลประกันควบการลงทุน (Unit Linked)", expanded=False):
        with st.form("insurance_upload_form"):
            col_d, col_v = st.columns(2)

            with col_d:
                ins_date = st.date_input("เลือกวันที่อัปเดตข้อมูล", value=date.today(), key="ins_date_input")

            with col_v:
                ins_redemption_value = st.number_input(
                    "มูลค่ารับซื้อคืนหน่วยลงทุน (บาท)", 
                    min_value=0.0, 
                    format="%.2f", 
                    value=0.0,
                    key="ins_redemption_input",
                    help="กรอกยอดมูลค่าพอร์ตประกันตามใบแจ้งยอดหรือแอปพลิเคชัน ณ วันที่อัปเดต"
                )

            submitted_ins = st.form_submit_button("💾 บันทึก/อัปเดตข้อมูลประกันภัย")

            if submitted_ins:
                if ins_redemption_value > 0:
                    try:
                        client = get_gsheet_client()
                        sheet_ins = get_cached_spreadsheet(client, 'MyStockData').worksheet('Insurance')

                        existing_data = sheet_ins.get_all_records()
                        df_existing_ins = pd.DataFrame(existing_data) if existing_data else pd.DataFrame()

                        date_str = ins_date.strftime("%Y-%m-%d")
                        year_ce = ins_date.year

                        is_duplicate = False

                        if not df_existing_ins.empty and 'Date' in df_existing_ins.columns:
                            match_idx = df_existing_ins[df_existing_ins['Date'].astype(str) == date_str].index

                            if len(match_idx) > 0:
                                is_duplicate = True
                                row_num = match_idx[0] + 2 

                                updated_values = [date_str, year_ce, ins_redemption_value]
                                sheet_ins.update(f"A{row_num}:C{row_num}", [updated_values])
                                st.success(f"✅ อัปเดตมูลค่าประกันของวันที่ **{date_str}** เป็น **{ins_redemption_value:,.2f} บาท** เรียบร้อยแล้ว!")

                        if not is_duplicate:
                            new_row = [date_str, year_ce, ins_redemption_value]
                            sheet_ins.append_row(new_row)
                            st.success(f"✅ บันทึกข้อมูลใหม่ของวันที่ **{date_str}** เรียบร้อยแล้ว!")

                        st.rerun()

                    except Exception as e:
                        st.error(f"❌ เกิดข้อผิดพลาดในการบันทึกข้อมูลประกัน: {e}")
                else:
                    st.warning("กรุณากรอกมูลค่ารับซื้อคืนหน่วยลงทุนให้มากกว่า 0")

    # --- 3. ส่วนสหกรณ์ก๊าซ ปตท. (พร้อมระบบ Auto เพิ่มเงินทุกสิ้นเดือน) ---
    def get_coop_sheet():
        client = get_gsheet_client()
        return get_cached_spreadsheet(client, 'MyStockData').worksheet('Coop')

    def get_sso_sheet():
        client = get_gsheet_client()
        return get_cached_spreadsheet(client, 'MyStockData').worksheet('SSO')

    def get_bank_sheet():
        client = get_gsheet_client()
        return get_cached_spreadsheet(client, 'MyStockData').worksheet('Bank_Account')

    # --- ฟังก์ชันคำนวณยอดอัติโนมัติสะสมตามเดือนที่ผ่านไป ---
    def calculate_auto_coop_value(last_date_str, last_val, monthly_add, is_auto_active):
        if not is_auto_active or monthly_add <= 0:
            return last_val, last_date_str

        try:
            last_dt = datetime.strptime(last_date_str, "%Y-%m-%d").date()
            today_dt = date.today()

            # ตรวจสอบว่าข้ามเดือนมาแล้วหรือไม่ (เทียบสิ้นเดือน)
            # คำนวณจำนวนเดือนที่ห่างกัน
            diff_months = (today_dt.year - last_dt.year) * 12 + (today_dt.month - last_dt.month)

            # หากผ่านไปอย่างน้อย 1 เดือนเต็ม และวันนี้เลยวันที่บันทึกล่าสุดมาแล้ว
            if diff_months > 0:
                # คำนวณยอดเงินที่ควรเพิ่มขึ้นตามจำนวนเดือนที่ผ่านไป
                updated_val = last_val + (diff_months * monthly_add)
                updated_date_str = today_dt.strftime("%Y-%m-%d")
                return updated_val, updated_date_str
        except Exception:
            pass

        return last_val, last_date_str

    with st.expander("📤 เพิ่ม/อัปเดตข้อมูลสหกรณ์ก๊าซ ปตท.", expanded=False):
        # ดึงข้อมูลล่าสุดจาก Sheet เพื่อมาแสดงค่าตั้งต้น
        latest_coop_val = 0.0
        latest_coop_date = date.today().strftime("%Y-%m-%d")
        try:
            sheet_coop = get_coop_sheet()
            coop_records = sheet_coop.get_all_records()
            if coop_records:
                last_row = coop_records[-1]
                latest_coop_date = str(last_row.get('Date', date.today().strftime("%Y-%m-%d")))
                latest_coop_val = float(str(last_row.get('Value', 0)).replace(',', ''))
        except Exception:
            pass

        # ตั้งค่าสถานะ Auto ใน session_state (ค่าเริ่มต้น: เปิดใช้งาน, เติมเดือนละ 10,000)
        if 'coop_auto_active' not in st.session_state:
            st.session_state['coop_auto_active'] = True
        if 'coop_monthly_amount' not in st.session_state:
            st.session_state['coop_monthly_amount'] = 10000.0

        # ตรวจสอบและบวกยอดอัตโนมัติหากผ่านพ้นสิ้นเดือน
        calculated_val, calculated_date = calculate_auto_coop_value(
            latest_coop_date, 
            latest_coop_val, 
            st.session_state['coop_monthly_amount'], 
            st.session_state['coop_auto_active']
        )

        with st.form("coop_upload_form"):
            st.markdown("##### ⚙️ ตั้งค่าระบบเติมเงินอัตโนมัติ (Auto Save)")
            col_cfg1, col_cfg2 = st.columns(2)
            with col_cfg1:
                auto_active_input = st.checkbox("เปิดใช้งาน Auto เติมเงินทุกสิ้นเดือน", value=st.session_state['coop_auto_active'], key="form_coop_auto_chk")
            with col_cfg2:
                monthly_amount_input = st.number_input("ยอดเติมอัตโนมัติ (บาท/เดือน)", min_value=0.0, step=1000.0, value=float(st.session_state['coop_monthly_amount']), key="form_coop_monthly_val")

            st.markdown("---")
            col_d, col_v = st.columns(2)
            with col_d:
                coop_date = st.date_input("เลือกวันที่อัปเดตข้อมูลสหกรณ์", value=datetime.strptime(calculated_date, "%Y-%m-%d").date() if calculated_date else date.today(), key="coop_date_input")
            with col_v:
                coop_value = st.number_input(
                    "ยอดเงินสหกรณ์ / มูลค่าหุ้นสหกรณ์ (บาท)", 
                    min_value=0.0, format="%.2f", value=float(calculated_val), key="coop_value_input",
                    help="ระบบจะคำนวณบวกยอด Auto ให้ หรือคุณสามารถพิมพ์แก้ไขยอดสุทธิใหม่ได้เองตามต้องการ"
                )

            submitted_coop = st.form_submit_button("💾 บันทึก/อัปเดตข้อมูลสหกรณ์")

            if submitted_coop:
                if coop_value > 0:
                    try:
                        # บันทึกสถานะ Auto ลง session_state
                        st.session_state['coop_auto_active'] = auto_active_input
                        st.session_state['coop_monthly_amount'] = monthly_amount_input

                        sheet_coop = get_coop_sheet()
                        date_str = coop_date.strftime("%Y-%m-%d")
                        year_ce = coop_date.year

                        date_column = sheet_coop.col_values(1) # สมมติคอลัมน์ A คือ Date

                        if date_str in date_column:
                            row_num = date_column.index(date_str) + 1
                            sheet_coop.update(f"A{row_num}:C{row_num}", [[date_str, year_ce, coop_value]])
                            st.success(f"✅ อัปเดตข้อมูลสหกรณ์ของวันที่ **{date_str}** เป็นยอด **{coop_value:,.2f} บาท** เรียบร้อยแล้ว!")
                        else:
                            sheet_coop.append_row([date_str, year_ce, coop_value])
                            st.success(f"✅ บันทึกข้อมูลใหม่สหกรณ์ของวันที่ **{date_str}** ยอด **{coop_value:,.2f} บาท** เรียบร้อยแล้ว!")

                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ เกิดข้อผิดพลาด (อาจติด Limit API กรุณารอสักครู่): {e}")
                else:
                    st.warning("กรุณากรอกยอดเงินให้มากกว่า 0")
    # --- ส่วนประกันสังคม ---
    with st.expander("📤 เพิ่ม/อัปเดตข้อมูลประกันสังคม", expanded=False):
        with st.form("sso_upload_form"):
            col_d, col_v = st.columns(2)
            with col_d:
                sso_date = st.date_input("เลือกวันที่อัปเดตข้อมูลประกันสังคม", value=date.today(), key="sso_date_input")
            with col_v:
                sso_value = st.number_input(
                    "ยอดสะสมประกันสังคม / เงินสมทบ (บาท)", 
                    min_value=0.0, format="%.2f", value=0.0, key="sso_value_input",
                    help="กรอกยอดเงินสะสมหรือเงินสมทบประกันสังคม ณ วันที่อัปเดต"
                )

            submitted_sso = st.form_submit_button("💾 บันทึก/อัปเดตข้อมูลประกันสังคม")

            if submitted_sso:
                if sso_value > 0:
                    try:
                        sheet_sso = get_sso_sheet()
                        date_str = sso_date.strftime("%Y-%m-%d")
                        year_ce = sso_date.year

                        date_column = sheet_sso.col_values(1)

                        if date_str in date_column:
                            row_num = date_column.index(date_str) + 1
                            sheet_sso.update(f"A{row_num}:C{row_num}", [[date_str, year_ce, sso_value]])
                            st.success(f"✅ อัปเดตข้อมูลประกันสังคมของวันที่ **{date_str}** เรียบร้อยแล้ว!")
                        else:
                            sheet_sso.append_row([date_str, year_ce, sso_value])
                            st.success(f"✅ บันทึกข้อมูลใหม่ประกันสังคมของวันที่ **{date_str}** เรียบร้อยแล้ว!")

                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ เกิดข้อผิดพลาด (อาจติด Limit API กรุณารอสักครู่): {e}")
                else:
                    st.warning("กรุณากรอกยอดเงินให้มากกว่า 0")

    # --- ส่วนบัญชีธนาคาร (กระแสเงินสด) ---
    with st.expander("💰 บันทึก/อัปเดต บัญชีเงินฝากกระแสเงินสด", expanded=False):
        with st.form("bank_account_form"):
            col1, col2 = st.columns(2)
            with col1:
                bank_date = st.date_input("วันที่", value=datetime.now(), key="bank_date_input")
                bank_type = st.selectbox("ประเภท", ["ฝากเงิน (Deposit)", "ถอนเงิน (Withdraw)"], key="bank_type_input")
            with col2:
                bank_amount = st.number_input("จำนวนเงิน (บาท)", min_value=0.0, step=100.0, key="bank_amount_input")
                bank_desc = st.text_input("หมายเหตุ", key="bank_desc_input")

            submitted_bank = st.form_submit_button("บันทึกรายการบัญชี")

            if submitted_bank:
                try:
                    in_val = bank_amount if "ฝาก" in bank_type else 0
                    out_val = bank_amount if "ถอน" in bank_type else 0

                    sheet_bank = get_bank_sheet()

                    # ดึงเฉพาะคอลัมน์ Balance หรือดึงข้อมูลแถวสุดท้ายมาคำนวณเพื่อลดการโหลดข้อมูลทั้งหมด
                    all_values = sheet_bank.get_all_values()
                    last_balance = 0.0

                    if len(all_values) > 1: # มี Header แล้ว
                        last_row = all_values[-1]
                        # สมมติว่าคอลัมน์ Balance อยู่ที่สุดท้าย (index -1)
                        try:
                            last_balance = float(str(last_row[-1]).replace(',', ''))
                        except:
                            last_balance = 0.0

                    new_balance = last_balance + in_val - out_val

                    sheet_bank.append_row([str(bank_date), bank_type, bank_desc, in_val, out_val, new_balance])
                    st.success("บันทึกรายการบัญชีเรียบร้อย!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ เกิดข้อผิดพลาดในการบันทึกบัญชี: {e}")

    with st.expander("📤 เพิ่ม/อัปเดตข้อมูลประกันบำนาญตามอายุ", expanded=False):
        with st.form("pension_upload_form"):
            col_p1, col_p2 = st.columns(2)
            with col_p1:
                pension_age = st.number_input(
                    "อายุที่เริ่มรับเงินบำนาญ (ปี)", 
                    min_value=55, max_value=100, value=55, step=1, 
                    key="pension_age_input",
                    help="ประกันบำนาญมักเริ่มถอน/รับเงินได้ตั้งแต่ช่วงอายุ 55 ปีขึ้นไป"
                )
            with col_p2:
                pension_value = st.number_input(
                    "ยอดเงินบำนาญที่จะได้รับ (บาท)", 
                    min_value=0.0, format="%.2f", value=0.0, key="pension_value_input",
                    help="กรอกยอดเงินตามตารางกรมธรรม์ ณ อายุที่เลือก"
                )

            submitted_pension = st.form_submit_button("💾 บันทึก/อัปเดตข้อมูลประกันบำนาญ")

            if submitted_pension:
                if pension_value >= 0:
                    try:
                        # ปรับวิธีเรียกใช้งานให้รองรับฟังก์ชันกลางและป้องกัน Error
                        client = get_gsheet_client()
                        sheet_pension = get_worksheet_safely(client, 'MyStockData', 'Pension')

                        if sheet_pension is None:
                            raise Exception("ไม่สามารถเชื่อมต่อกับชีต 'Pension' ได้ กรุณาตรวจสอบชื่อชีตอีกครั้ง")

                        # แปลงอายุเป็น string เพื่อใช้ตรวจสอบในคอลัมน์ A (อายุ)
                        age_str = str(int(pension_age))

                        # ดึงข้อมูลในคอลัมน์ A ทั้งหมดมาเช็คว่ามีอายุนี้หรือยัง
                        age_column = [str(cell) for cell in sheet_pension.col_values(1)]

                        if age_str in age_column:
                            row_num = age_column.index(age_str) + 1
                            # อัปเดตข้อมูลในบรรทัดเดิม (คอลัมน์ A คือ อายุ, คอลัมน์ B คือ ยอดเงิน)
                            sheet_pension.update(f"A{row_num}:B{row_num}", [[age_str, pension_value]])
                            st.success(f"✅ อัปเดตข้อมูลประกันบำนาญสำหรับ **อายุ {age_str} ปี** เรียบร้อยแล้ว!")
                        else:
                            # เพิ่มบรรทัดใหม่
                            sheet_pension.append_row([age_str, pension_value])
                            st.success(f"✅ บันทึกข้อมูลใหม่ประกันบำนาญสำหรับ **อายุ {age_str} ปี** เรียบร้อยแล้ว!")

                        time.sleep(0.5)
                        st.rerun()

                    except Exception as e:
                        st.error(f"❌ เกิดข้อผิดพลาดในการบันทึก: {e}")
                else:
                    st.warning("กรุณากรอกยอดเงินให้ถูกต้อง")

######## REAL ESTATE ########################
