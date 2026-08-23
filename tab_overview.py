# =============================================================
# tab_overview.py
# แท็บภาพรวม Net Worth & สัดส่วนสินทรัพย์ (Phase 2 ของการแยกไฟล์)
# =============================================================
import streamlit as st
import pandas as pd
import time
import plotly.graph_objects as go
import plotly.express as px
from backend_functions import get_gsheet_client, get_cached_spreadsheet, get_active_sheet_name


def render_tab_overview():

    # 1. ใช้ @st.cache_data เพื่อดึงข้อมูลทุกชีตรวมกันครั้งเดียวและเก็บไว้ 10 นาที (ลดจำนวน Request มหาศาล)
    # 🔧 แก้บั๊ก: เดิมฟังก์ชันนี้ดึงข้อมูล 9 ชีตพร้อมกันแล้ว Cache รวมเป็นก้อนเดียว 10 นาที
    # ถ้าชีตใดชีตหนึ่งโหลดพลาดแค่ชีตเดียว ระบบจะจำเป็นค่าว่างของ "ทั้ง 9 ชีต" รวมกันไปเลย 10 นาที
    # (และ Cache นี้ใช้ร่วมกันทุกคนที่เปิดแอป ไม่ใช่แค่เครื่องคุณ) ทำให้ข้อมูลหายไปเป็นช่วงๆ โดยไม่ทราบสาเหตุ
    # ตอนนี้แยก Cache เป็นรายชีต ถ้าชีตไหนพลาด จะลองใหม่แค่ชีตนั้นในรอบถัดไป ไม่กระทบชีตอื่นที่โหลดสำเร็จแล้ว
    @st.cache_data(ttl=600, show_spinner=False)
    def _fetch_ws_records_safe(ws_name, max_retries=3):
        client = get_gsheet_client()
        last_error = None
        for i in range(max_retries):
            try:
                sheet = get_cached_spreadsheet(client, get_active_sheet_name()).worksheet(ws_name)
                return sheet.get_all_records()
            except Exception as e:
                last_error = str(e)
                time.sleep(1 + i)  # หน่วงเวลาก่อนลองใหม่ (Exponential Backoff)
        raise RuntimeError(last_error or f"โหลดชีต {ws_name} ไม่สำเร็จ")

    def fetch_all_wealth_overview_data():
        def get_ws_records_safe(ws_name):
            try:
                return _fetch_ws_records_safe(ws_name)
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
            "portfolio_hist": get_ws_records_safe('Stock_TFEX_History')
        }

    # เรียกใช้งานข้อมูลทั้งหมดรอบเดียวจบ
    all_data = fetch_all_wealth_overview_data()

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

    # ทองคำ (จาก session_state)
    total_gold_value = st.session_state.get('total_gold_portfolio_value', 0.0)

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

    # พอร์ตหุ้นรวม + พอร์ต TFEX
    # 🔧 แก้บั๊ก: เดิมใช้ 'total_value' in locals() ซึ่งใช้ได้ตอนแท็บนี้ยังอยู่ไฟล์เดียวกับแท็บหุ้น
    # แต่หลังแยกไฟล์แล้ว ต้องอ่านค่าผ่าน session_state แทน (แท็บหุ้นตั้งค่านี้ไว้ให้แล้ว)
    base_stock_value = st.session_state.get('stock_net_worth', 0.0)
    tfex_portfolio_value = st.session_state.get('tfex_net_worth', 0.0)
    total_stock_and_tfex = base_stock_value + tfex_portfolio_value

    # คำนวณ Net Worth
    net_worth_excl_re = (total_stock_and_tfex + pvd_value + insurance_value + 
                         coop_value + sso_value + pension_insurance_value + 
                         bank_balance + total_gold_value + mutual_fund_value)
    net_worth_total = net_worth_excl_re + total_real_estate

    # --- 3. แสดงผล Net Worth ทั้งสองแบบ ---
    with st.container(border=True):
        col_nw1, col_nw2 = st.columns(2)

        with col_nw1:
            st.markdown(
                f"""
                <div style="text-align: left; padding: 5px;">
                    <h4 style="color: #28a745; margin-bottom: 0px;">Net Worth (ไม่รวมอสังหาฯ)</h4>
                    <h1 style="color: #28a745; font-size: 2.3em; margin-top: 5px;">{net_worth_excl_re:,.0f} ฿</h1>
                </div>
                """, unsafe_allow_html=True
            )
        with col_nw2:
            st.markdown(
                f"""
                <div style="text-align: left; padding: 5px;">
                    <h4 style="color: #28a745; margin-bottom: 0px;">Net Worth รวมทั้งหมด</h4>
                    <h1 style="color: #28a745; font-size: 2.3em; margin-top: 5px;">{net_worth_total:,.0f} ฿</h1>
                </div>
                """, unsafe_allow_html=True
            )


    # --- 4. แสดงผลใน Metrics ย่อย ---
    with st.container(border=True):
        st.markdown("#### 💼 สินทรัพย์สภาพคล่องและการลงทุน")
        row1_col1, row1_col2, row1_col3, row1_col4 = st.columns(4)
        row1_col1.metric("พอร์ตหุ้น + TFEX", f"{total_stock_and_tfex:,.0f} ฿")
        row1_col2.metric("กองทุนรวม", f"{mutual_fund_value:,.0f} ฿")
        row1_col3.metric("กองทุนสำรองเลี้ยงชีพ", f"{pvd_value:,.0f} ฿")
        row1_col4.metric("ประกัน Unit Linked", f"{insurance_value:,.0f} ฿")

        row2_col1, row2_col2, row2_col3, row2_col4 = st.columns(4)
        row2_col1.metric("สหกรณ์ฯ", f"{coop_value:,.0f} ฿")
        row2_col2.metric("ประกันสังคม", f"{sso_value:,.0f} ฿")
        row2_col3.metric("บัญชีธนาคาร", f"{bank_balance:,.0f} ฿")
        row2_col4.metric("ประกันบำนาญ", f"{pension_insurance_value:,.0f} ฿")

        # ย้าย Note มาไว้ใน col4 ของแถวนี้ เพื่อให้อยู่ใต้ประกันบำนาญพอดี
        if all_data["pension"]:
            pension_notes_html = '<div style="margin-top: -10px; margin-bottom: 5px;">'
            for row in all_data["pension"]:
                age_val = row.get('Age', '-')
                money_val = row.get('Value', 0)

                clean_money = float(str(money_val).replace(',', '').replace('฿', '').strip() or 0)

                if clean_money > 0:
                    pension_notes_html += (
                        f'<p style="color: #888888; font-size: 0.75em; margin: 0px;">'
                        f'• ถอนออก ณ อายุ {age_val} ปี: {clean_money:,.0f} ฿'
                        f'</p>'
                    )
            pension_notes_html += '</div>'

            # แสดงผลข้อความไว้ใต้ช่องประกันบำนาญโดยตรง
            row2_col4.markdown(pension_notes_html, unsafe_allow_html=True)

        row3_col1, _, _, _ = st.columns(4)
        row3_col1.metric("พอร์ตทองคำ", f"{total_gold_value:,.0f} ฿")

        st.markdown("<br>", unsafe_allow_html=True)

        # --- 5. แสดงผลอสังหาริมทรัพย์ ---
        st.markdown("#### 🏡 อสังหาริมทรัพย์")
        row_re1, row_re2, row_re3, row_re4 = st.columns(4)
        row_re1.metric("รวมอสังหาริมทรัพย์", f"{total_real_estate:,.0f} ฿")
        row_re2.metric("บ้าน (ปัจจุบัน)", f"{house1_value:,.0f} ฿")
        row_re3.metric("บ้าน (พ่อแม่อยู่)", f"{house2_value:,.0f} ฿")
        row_re4.metric("คอนโด", f"{condo_value:,.0f} ฿")


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
                st.plotly_chart(fig_donut, use_container_width=True, key="donut_main_chart")
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
                st.plotly_chart(fig_bar, use_container_width=True, key="bar_main_chart")
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
                        return pd.DataFrame(_fetch_ws_records_safe(ws_name))
                    except Exception:
                        return pd.DataFrame()

                return (get_df_safe('Provident_Fund'), get_df_safe('Insurance'), 
                        get_df_safe('Coop'), get_df_safe('Bank_Account'), 
                        get_df_safe('SSO'), get_df_safe('Fund_History'), 
                        get_df_safe('Stock_TFEX_History'))

            df_pvd, df_ins, df_coop, df_bank, df_sso, df_mf, df_portfolio_hist = fetch_all_wealth_data()

            def prepare_series(df, date_col, val_col, name):
                df = df.copy()
                if df.empty: return pd.DataFrame(columns=[name], index=pd.to_datetime([]))
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
            s_mf = prepare_series(df_mf, 'Date', 'Value', 'Mutual_Fund')
            s_port = prepare_series(df_portfolio_hist, 'Date', 'Total_Value', 'Stock+TFEX')

            if not s_ins.empty and not s_sso.empty:
                s_ins = s_ins.join(s_sso, how='outer').sort_index().ffill().fillna(0)
                s_ins['Insurance'] = s_ins['Insurance'] + s_ins['SSO']
                s_ins = s_ins[['Insurance']]
            elif s_ins.empty and not s_sso.empty:
                s_ins = s_sso.rename(columns={'SSO': 'Insurance'})

            series_list = [s for s in [s_pvd, s_ins, s_coop, s_bank, s_mf, s_port] if not s.empty]

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

                st.plotly_chart(fig, use_container_width=True, key="net_worth_trend_chart_final")
            else:
                st.info("💡 ยังไม่มีข้อมูลเพียงพอสำหรับแสดงกราฟแนวโน้ม")
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการดึงข้อมูลกราฟ: {e}")
