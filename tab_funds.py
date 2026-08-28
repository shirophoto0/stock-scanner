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
from theme import style_plotly, render_metric_card, get_theme_colors


# 🆕 แก้บั๊ก 429 Rate Limit: เดิมทุก sub-tab (ภาพรวมพอร์ต/ซื้อกองทุนเพิ่ม/อัปเดตราคา) ต่างเรียก
# .worksheet('Fund_History').get_all_records() แยกกันเอง — เพราะ Streamlit's st.tabs() รันทุกแท็บ
# พร้อมกันหมดทุกครั้งที่หน้าเว็บรันซ้ำ (แค่ซ่อนแท็บที่ไม่ได้เลือกไว้ด้วย CSS เท่านั้น ไม่ได้ข้ามการ
# ประมวลผล) ทำให้ยิง API อ่านข้อมูลรัว 3-4 ครั้งทุกครั้งที่มีการโต้ตอบใดๆ ในหน้านี้ จนโดน Rate Limit
# ตอนนี้ห่อด้วย @st.cache_data ให้ทุกจุดที่ต้องการอ่านข้อมูลกองทุน เรียกผ่านฟังก์ชันเดียวกันนี้แทน
# (ยิง API จริงแค่ครั้งเดียวทุก 2 นาที ไม่ว่าจะมีกี่แท็บเรียกพร้อมกันก็ตาม)
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


def render_tab_funds():
    st.subheader("💰 ระบบจัดการกองทุนรวม")

    # สร้าง Tab ย่อยสำหรับการจัดการกองทุน
    # 🔧 ปรับปรุง: สลับลำดับแท็บย่อย ให้ "ภาพรวมพอร์ต" อยู่ซ้ายสุด จะได้เห็นหน้า Dashboard ก่อนทันที
    # ที่เปิดแท็บกองทุนรวม (สลับแค่ลำดับตอนประกาศตรงนี้ ไม่ต้องย้ายเนื้อหาข้างในเลย เพราะโค้ด
    # อ้างอิงผ่านชื่อตัวแปรอยู่แล้ว ไม่ขึ้นกับตำแหน่งที่ประกาศ)
    tab_summary, tab_buy, tab_update = st.tabs(["📈 ภาพรวมพอร์ต", "➕ ซื้อกองทุนเพิ่ม", "🔄 อัปเดตราคา/ขาย"])

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
                        # เปลี่ยนมาใช้ระบบเดียวกับแท็บอื่น (เปิดตามชื่อชีตของผู้ใช้ที่ login อยู่) และ
                        # เปลี่ยนจาก get_cached_spreadsheet().worksheet() เป็น get_cached_worksheet()
                        # ซึ่งแคชครบทั้ง spreadsheet และ worksheet object ในตัวเดียว ลด API call ซ้ำซ้อน
                        sheet = get_cached_worksheet(client, get_active_sheet_name(), 'Fund_History')

                        # หา Fund_ID ถัดไป (ใช้ข้อมูลที่แคชไว้ ไม่ต้องยิง API อ่านซ้ำ)
                        existing_data = _load_fund_history_cached(get_active_sheet_name())
                        new_id = len(existing_data)

                        # ข้อมูลที่จะ append: Fund_ID, Fund_Name, Date_Buy, Date_Sell, Cost_Price, Current_Price, Units, Status, Price_Updated_Date
                        # 🆕 เพิ่มคอลัมน์ Price_Updated_Date (วันที่อัปเดตราคาล่าสุด) ไว้ท้ายสุด เพื่อใช้
                        # เตือน "ราคาเก่า" ในหน้าภาพรวมพอร์ต — ตอนซื้อใหม่ ใช้วันที่ซื้อเป็นวันแรกที่
                        # ถือว่าราคาอัปเดตล่าสุด (เพราะ Cost_Price = Current_Price ตอนซื้อพอดี)
                        row_data = [new_id, fund_name, str(date_buy), "", cost_price, cost_price, units, "Holding", str(date_buy)]
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

                    selected_row_data = None
                    selected_row_index = -1
                    for idx, row in enumerate(all_data):
                        if row.get('Fund_Name') == selected_fund and row.get('Status', 'Holding') == 'Holding':
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

                        # 🔧 แก้บั๊ก: เดิม new_price/sell_units/sell_price อยู่นอกฟอร์มทั้งหมด พิมพ์ตัวเลข
                        # ทีละตัวแล้วหน้าเว็บรันใหม่ทันที ตอนนี้ครอบด้วย st.form() แยกตาม action ที่
                        # เลือก (คนละฟอร์ม คนละปุ่ม) ให้กรอกครบก่อนค่อยกดปุ่มยืนยัน — selected_fund กับ
                        # action_type ด้านบนยังอยู่นอกฟอร์มเหมือนเดิม เพราะต้องอัปเดตสดจริงๆ (โชว์ข้อมูล
                        # กองทุนที่เลือก, สลับช่องกรอกตาม action ที่เลือก)
                        if action_type == "อัปเดตราคาปัจจุบัน":
                            with st.form("fund_update_price_form"):
                                new_price = st.number_input("ราคาปัจจุบันใหม่:", min_value=0.0, step=0.01, format="%.4f", key="new_price_input")
                                update_price_submitted = st.form_submit_button("💾 บันทึกราคาอัปเดต")

                            if update_price_submitted:
                                sheet.update_cell(selected_row_index, 6, new_price)
                                # 🆕 บันทึกวันที่อัปเดตราคาล่าสุดไว้ที่คอลัมน์ 9 (Price_Updated_Date)
                                # ด้วย ใช้เตือน "ราคาเก่า" ในหน้าภาพรวมพอร์ตถ้าไม่ได้อัปเดตนานเกินไป
                                sheet.update_cell(selected_row_index, 9, str(date.today()))
                                st.cache_data.clear()  # 🆕 ล้างแคชทันที กันเห็นราคาเก่าค้างอยู่
                                st.success(f"อัปเดตราคา {selected_fund} เป็น {new_price} สำเร็จ!")
                                st.rerun()

                        elif action_type == "ขายกองทุนออก":
                            with st.form("fund_sell_form"):
                                sell_units = st.number_input("จำนวนหน่วยที่ต้องการขาย:", min_value=0.0, max_value=units_val, step=0.01, format="%.2f", key="sell_units_input")
                                sell_price = st.number_input("ราคาขายต่อหน่วย:", min_value=0.0, step=0.01, format="%.4f", key="sell_price_input")
                                sell_submitted = st.form_submit_button("💸 ยืนยันการขายกองทุน")

                            if sell_submitted:
                                remaining_units = units_val - sell_units
                                if remaining_units <= 0:
                                    sheet.update_cell(selected_row_index, 8, "Sold")
                                    st.success(f"ขายกองทุน {selected_fund} ทั้งหมดเรียบร้อยแล้ว!")
                                else:
                                    sheet.update_cell(selected_row_index, 3, remaining_units)
                                    st.success(f"ขายกองทุน {selected_fund} บางส่วน คงเหลือ {remaining_units:,.2f} หน่วย")
                                st.cache_data.clear()  # 🆕 ล้างแคชทันที กันเห็นข้อมูลเก่าค้างอยู่
                                st.rerun()
                    else:
                        st.warning("ไม่พบข้อมูลกองทุนที่มีสถานะถือครองอยู่ในระบบ")
                else:
                    st.info("ยังไม่มีกองทุนในสถานะถือครอง")
            else:
                st.info("ยังไม่มีข้อมูลกองทุนในระบบ")

        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการโหลดข้อมูล: {e}")

    # 3. Tab ภาพรวมพอร์ต (แสดงมูลค่าต้นทุน, มูลค่าปัจจุบัน + Dashboard ติดตามผลงาน)
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
                    # คำนวณค่าพอร์ตแต่ละตัว (รวมกองเดียวกันที่ซื้อหลายรอบเข้าด้วยกัน)
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

                        # 🆕 หาว่าราคาอัปเดตล่าสุดเมื่อไหร่ (คอลัมน์ Price_Updated_Date ถ้ามี)
                        price_updated_str = str(row.get('Price_Updated_Date', '')).strip()
                        days_since_update = None
                        if price_updated_str:
                            try:
                                price_updated_date = datetime.strptime(price_updated_str, '%Y-%m-%d').date()
                                days_since_update = (date.today() - price_updated_date).days
                            except ValueError:
                                pass

                        display_data.append({
                            "ชื่อกองทุน": row['Fund_Name'],
                            "วันที่ซื้อ": row['Date_Buy'],
                            "ต้นทุนเฉลี่ย": cost_p,
                            "ราคาปัจจุบัน": curr_p,
                            "จำนวนหน่วย": units,
                            "มูลค่าต้นทุน": res['Total_Cost'],
                            "มูลค่าปัจจุบัน": res['Current_Value'],
                            "กำไร/ขาดทุน": res['Profit_Loss'],
                            "% กำไร/ขาดทุน": res['Profit_Loss_Pct'],
                            "_days_since_update": days_since_update,
                        })

                    df_display = pd.DataFrame(display_data)
                    total_profit = total_portfolio_value - total_portfolio_cost
                    total_profit_pct = (total_profit / total_portfolio_cost) * 100 if total_portfolio_cost > 0 else 0.0

                    # 🆕 (1) การ์ดสรุปภาพรวม — ใช้การ์ดสไตล์เดียวกับหน้าอื่นในแอปแทน st.metric เดิม
                    m1, m2, m3 = st.columns(3)
                    render_metric_card(m1, "มูลค่าต้นทุนรวม", f"{total_portfolio_cost:,.2f} บาท", icon="📥")
                    render_metric_card(m2, "มูลค่าปัจจุบันรวม", f"{total_portfolio_value:,.2f} บาท", icon="📈")
                    render_metric_card(
                        m3, "กำไร/ขาดทุนรวม", f"{total_profit:,.2f} บาท", icon="💹",
                        delta=f"{total_profit_pct:.2f}%", delta_positive=(total_profit >= 0)
                    )

                    # 🆕 (4) เตือนราคาเก่า — ถ้ากองไหนไม่ได้อัปเดตราคาเกิน 35 วัน (หรือไม่มีข้อมูลวันที่
                    # อัปเดตเลย เพราะเป็นรายการเก่าก่อนมีฟีเจอร์นี้) จะเตือนให้ไปอัปเดตราคาก่อน เพราะ
                    # ตัวเลขทั้งหมดในหน้านี้คำนวณจากราคาที่กรอกเองรายเดือน ถ้าลืมอัปเดต ตัวเลขจะผิดเพี้ยน
                    _stale_funds = [
                        d["ชื่อกองทุน"] for d in display_data
                        if d["_days_since_update"] is None or d["_days_since_update"] > 35
                    ]
                    if _stale_funds:
                        st.warning(
                            f"⚠️ **กองทุนต่อไปนี้ยังไม่ได้อัปเดตราคานานเกิน 35 วัน (หรือไม่มีข้อมูลวันที่อัปเดต):** "
                            f"{', '.join(_stale_funds)} — ไปที่แท็บ \"🔄 อัปเดตราคา/ขาย\" เพื่ออัปเดตให้ตัวเลขแม่นยำขึ้นครับ"
                        )

                    st.divider()

                    # 🆕 (2) ตารางเปรียบเทียบผลงานรายกองทุน — เรียงจากกำไรมากไปน้อย พร้อมสีเขียว/แดง
                    st.markdown("##### 📋 เปรียบเทียบผลงานรายกองทุน")
                    df_table = df_display.drop(columns=['_days_since_update']).sort_values('% กำไร/ขาดทุน', ascending=False)
                    _tc = get_theme_colors()

                    def _color_pl(val):
                        if isinstance(val, (int, float)):
                            return f"color: {'#26A69A' if val > 0 else '#EF5350' if val < 0 else _tc['text']}"
                        return None

                    st.dataframe(
                        df_table.style.format({
                            "ต้นทุนเฉลี่ย": "{:.4f}", "ราคาปัจจุบัน": "{:.4f}", "จำนวนหน่วย": "{:,.2f}",
                            "มูลค่าต้นทุน": "{:,.2f}", "มูลค่าปัจจุบัน": "{:,.2f}",
                            "กำไร/ขาดทุน": "{:,.2f}", "% กำไร/ขาดทุน": "{:+.2f}%"
                        })
                        .set_properties(**{'text-align': 'right', 'background-color': _tc['bg']})
                        .map(_color_pl, subset=["กำไร/ขาดทุน", "% กำไร/ขาดทุน"])
                        .set_table_styles([
                            {'selector': 'th', 'props': [('background-color', '#F1EEE8'), ('color', _tc['text']),
                                                          ('font-family', "'Prompt',sans-serif"), ('font-weight', '600'),
                                                          ('border-color', _tc['border'])]},
                            {'selector': 'td', 'props': [('border-color', _tc['border'])]},
                        ]),
                        use_container_width=True, hide_index=True
                    )

                    # กองที่ทำผลงานดีสุด/แย่สุด (สรุปให้เห็นไวๆ ไม่ต้องไล่หาในตาราง)
                    _best = df_table.iloc[0]
                    _worst = df_table.iloc[-1]
                    _b1, _b2 = st.columns(2)
                    _b1.success(f"🏆 **ผลงานดีสุด:** {_best['ชื่อกองทุน']} ({_best['% กำไร/ขาดทุน']:+.2f}%)")
                    _b2.error(f"📉 **ผลงานแย่สุด:** {_worst['ชื่อกองทุน']} ({_worst['% กำไร/ขาดทุน']:+.2f}%)")

                    st.divider()

                    # 🆕 (5) กราฟเปรียบเทียบผลงานระหว่างกองทุน (% กำไร/ขาดทุน)
                    st.markdown("##### 📊 เปรียบเทียบ % ผลตอบแทนระหว่างกองทุน")
                    fig_compare = px.bar(
                        df_table, x='ชื่อกองทุน', y='% กำไร/ขาดทุน',
                        text=df_table['% กำไร/ขาดทุน'].apply(lambda x: f"{x:+.2f}%"),
                        color='% กำไร/ขาดทุน', color_continuous_scale=['#EF5350', '#26A69A'],
                        color_continuous_midpoint=0
                    )
                    fig_compare.update_traces(textposition='outside')
                    fig_compare.update_layout(
                        xaxis_title="", yaxis_title="% กำไร/ขาดทุน", height=380,
                        margin=dict(l=20, r=20, t=30, b=80), coloraxis_showscale=False, xaxis=dict(tickangle=-30)
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
