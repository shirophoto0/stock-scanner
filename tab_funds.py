# =============================================================
# tab_funds.py
# แท็บกองทุนรวม (Phase 2 ของการแยกไฟล์)
# =============================================================
import streamlit as st
import pandas as pd
from datetime import date
from backend_functions import calculate_fund_result, get_gsheet_client, get_cached_spreadsheet, get_active_sheet_name


def render_tab_funds():
    st.subheader("💰 ระบบจัดการกองทุนรวม")

    # สร้าง Tab ย่อยสำหรับการจัดการกองทุน
    tab_buy, tab_update, tab_summary = st.tabs(["➕ ซื้อกองทุนเพิ่ม", "🔄 อัปเดตราคา/ขาย", "📈 ภาพรวมพอร์ต"])

    # 1. Tab ซื้อกองทุนใหม่
    with tab_buy:
        st.markdown("### บันทึกซื้อกองทุนใหม่")
        with st.form("form_buy_fund"):
            col1, col2 = st.columns(2)
            fund_name = col1.text_input("ชื่อกองทุน (เช่น SCBSET, K-Equity):")
            # แก้ไขจาก datetime.date.today() เป็น date.today() เพื่อป้องกัน Error
            date_buy = col2.date_input("วันที่ซื้อ:", date.today())

            col3, col4 = st.columns(2)
            cost_price = col3.number_input("ราคาต้นทุนเฉลี่ยต่อหน่วย:", min_value=0.0, step=0.01, format="%.4f")
            units = col4.number_input("จำนวนหน่วย (Units):", min_value=0.0001, step=1.0, format="%.4f")

            submitted = st.form_submit_button("บันทึกการซื้อกองทุน", use_container_width=True, type="primary")
            if submitted:
                if not fund_name:
                    st.warning("กรุณากรอกชื่อกองทุนครับ")
                else:
                    try:
                        client = get_gsheet_client()
                        # 🔧 แก้บั๊ก: เดิมเขียน ID ของ Google Sheet ตายตัวไว้ (ไม่ใช่ชื่อ "MyStockData")
                        # ทำให้ไม่ว่าใคร login เข้ามาก็จะไปอ่าน/เขียนไฟล์เดียวกันเป๊ะๆ เสมอ ไม่แยกตามผู้ใช้
                        # เปลี่ยนมาใช้ระบบเดียวกับแท็บอื่น (เปิดตามชื่อชีตของผู้ใช้ที่ login อยู่)
                        sheet = get_cached_spreadsheet(client, get_active_sheet_name()).worksheet('Fund_History')

                        # หา Fund_ID ถัดไป
                        existing_data = sheet.get_all_records()
                        new_id = len(existing_data)

                        # ข้อมูลที่จะ append: Fund_ID, Fund_Name, Date_Buy, Date_Sell, Cost_Price, Current_Price, Units, Status
                        row_data = [new_id, fund_name, str(date_buy), "", cost_price, cost_price, units, "Holding"]
                        sheet.append_row(row_data)

                        st.cache_data.clear()
                        st.success("บันทึกกองทุนสำเร็จ! 🎉")
                        st.rerun()
                    except Exception as e:
                        st.error(f"เกิดข้อผิดพลาด: {e}")

    # 2. Tab อัปเดตราคาปัจจุบัน หรือ ขายกองทุน
    with tab_update:
        st.markdown("### อัปเดตราคาหรือขายกองทุน")

        # ฟังก์ชันช่วยแปลงค่าให้เป็น float อย่างปลอดภัย (ป้องกัน Error ตัวอักษรปน)
        def safe_float(val):
            try:
                if val is None or str(val).strip() == "":
                    return 0.0
                # ตัดคอมมาออกแล้วแปลงเป็น float
                return float(str(val).replace(',', '').strip())
            except ValueError:
                return 0.0

        # 1. ดึงข้อมูลกองทุนทั้งหมดมาทำ Dropdown
        try:
            client = get_gsheet_client()
            # 🔧 แก้บั๊ก: เดิมเขียน ID ของ Google Sheet ตายตัวไว้ ตอนนี้เปลี่ยนตามผู้ใช้ที่ login แล้ว
            sheet = get_cached_spreadsheet(client, get_active_sheet_name()).worksheet('Fund_History')

            all_data = sheet.get_all_records()

            if all_data:
                fund_list = sorted(list(set(row['Fund_Name'] for row in all_data if row.get('Fund_Name') and row.get('Status') == 'Holding')))

                if not fund_list:
                    fund_list = sorted(list(set(row['Fund_Name'] for row in all_data if row['Fund_Name'])))

                if fund_list:
                    selected_fund = st.selectbox("เลือกกองทุนที่ต้องการจัดการ:", fund_list, key="selected_fund_update")

                    selected_row_data = None
                    selected_row_index = -1
                    for idx, row in enumerate(all_data):
                        if row['Fund_Name'] == selected_fund and row.get('Status', 'Holding') == 'Holding':
                            selected_row_data = row
                            selected_row_index = idx + 2 
                            break

                    if selected_row_data:
                        # ดึงค่าและแปลงเป็นตัวเลขอย่างปลอดภัย
                        units_val = safe_float(selected_row_data.get('Units', 0))
                        avg_price_val = safe_float(selected_row_data.get('Average_Price', 0))
                        current_price_val = safe_float(selected_row_data.get('Current_Price', 0))

                        st.info(f"📌 **ข้อมูลปัจจุบันของกองทุน:** {selected_fund}\n\n"
                                f"- **จำนวนหน่วย:** {units_val:,.2f}\n"
                                f"- **ราคาเฉลี่ย/ต้นทุน:** {avg_price_val:,.4f}\n"
                                f"- **ราคาปัจจุบันล่าสุด:** {current_price_val:,.4f}")

                        action_type = st.radio("เลือกการดำเนินการ:", ["อัปเดตราคาปัจจุบัน", "ขายกองทุนออก"], horizontal=True, key="fund_action_radio")

                        if action_type == "อัปเดตราคาปัจจุบัน":
                            new_price = st.number_input("ราคาปัจจุบันใหม่:", min_value=0.0, step=0.01, format="%.4f", key="new_price_input")

                            if st.button("💾 บันทึกราคาอัปเดต"):
                                sheet.update_cell(selected_row_index, 6, new_price)
                                st.success(f"อัปเดตราคา {selected_fund} เป็น {new_price} สำเร็จ!")
                                st.rerun()

                        elif action_type == "ขายกองทุนออก":
                            sell_units = st.number_input("จำนวนหน่วยที่ต้องการขาย:", min_value=0.0, max_value=units_val, step=0.01, format="%.2f", key="sell_units_input")
                            sell_price = st.number_input("ราคาขายต่อหน่วย:", min_value=0.0, step=0.01, format="%.4f", key="sell_price_input")

                            if st.button("💸 ยืนยันการขายกองทุน"):
                                remaining_units = units_val - sell_units
                                if remaining_units <= 0:
                                    sheet.update_cell(selected_row_index, 8, "Sold")
                                    st.success(f"ขายกองทุน {selected_fund} ทั้งหมดเรียบร้อยแล้ว!")
                                else:
                                    sheet.update_cell(selected_row_index, 3, remaining_units)
                                    st.success(f"ขายกองทุน {selected_fund} บางส่วน คงเหลือ {remaining_units:,.2f} หน่วย")
                                st.rerun()
                    else:
                        st.warning("ไม่พบข้อมูลกองทุนที่มีสถานะถือครองอยู่ในระบบ")
                else:
                    st.info("ยังไม่มีกองทุนในสถานะถือครอง")
            else:
                st.info("ยังไม่มีข้อมูลกองทุนในระบบ")

        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการโหลดข้อมูล: {e}")

    # 3. Tab ภาพรวมพอร์ต (แสดงมูลค่าต้นทุน, มูลค่าปัจจุบัน)
    with tab_summary:
        st.markdown("### สรุปมูลค่าพอร์ตลงทุน")
        try:
            client = get_gsheet_client()
            # 🔧 แก้บั๊ก: เดิมเขียน ID ของ Google Sheet ตายตัวไว้ ตอนนี้เปลี่ยนตามผู้ใช้ที่ login แล้ว
            sheet = get_cached_spreadsheet(client, get_active_sheet_name()).worksheet('Fund_History')
            summary_df = pd.DataFrame(sheet.get_all_records())

            if not summary_df.empty and 'Status' in summary_df.columns:
                active_df = summary_df[summary_df['Status'] == 'Holding'].copy()

                if not active_df.empty:
                    # คำนวณค่าพอร์ตแต่ละตัว
                    total_portfolio_cost = 0
                    total_portfolio_value = 0

                    display_data = []
                    for _, row in active_df.iterrows():
                        cost_p = float(row['Cost_Price'])
                        curr_p = float(row['Current_Price'])
                        units = float(row['Units'])
                        res = calculate_fund_result(cost_p, curr_p, units)

                        total_portfolio_cost += res['Total_Cost']
                        total_portfolio_value += res['Current_Value']

                        display_data.append({
                            "ชื่อกองทุน": row['Fund_Name'],
                            "วันที่ซื้อ": row['Date_Buy'],
                            "ต้นทุนเฉลี่ย": cost_p,
                            "ราคาปัจจุบัน": curr_p,
                            "จำนวนหน่วย": units,
                            "มูลค่าต้นทุน": res['Total_Cost'],
                            "มูลค่าปัจจุบัน": res['Current_Value'],
                            "กำไร/ขาดทุน": res['Profit_Loss'],
                            "(%)": f"{res['Profit_Loss_Pct']}%"
                        })

                    # แสดง Metric รวมด้านบน
                    total_profit = total_portfolio_value - total_portfolio_cost
                    m1, m2, m3 = st.columns(3)
                    m1.metric("มูลค่าต้นทุนรวม", f"{total_portfolio_cost:,.2f} บาท")
                    m2.metric("มูลค่าปัจจุบันรวม", f"{total_portfolio_value:,.2f} บาท", f"{total_profit:,.2f} บาท")
                    m3.metric("ผลตอบแทนรวม (%)", f"{(total_profit/total_portfolio_cost)*100:.2f}%" if total_portfolio_cost > 0 else "0.00%")

                    st.divider()
                    st.dataframe(pd.DataFrame(display_data), use_container_width=True)
                else:
                    st.info("ไม่มีกองทุนในพอร์ตที่กำลังถืออยู่")
            else:
                st.info("ยังไม่มีข้อมูลกองทุนในชีต")
        except Exception as e:
            st.warning(f"ยังไม่พบชีต Fund_History หรือเกิดข้อผิดพลาด: {e}")
