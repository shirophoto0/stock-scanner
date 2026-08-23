# =============================================================
# tab_stock.py
# แท็บหุ้น (Dashboard, พอร์ตโฟลิโอ, ปันผล, สมุดบันทึก, แผนและ Alert) (Phase 2 ของการแยกไฟล์)
# =============================================================
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import altair as alt
import plotly
import plotly.graph_objects as go
import plotly.express as px
import os
from datetime import date, datetime
from backend_functions import (
    backfill_portfolio_history, check_alerts, clear_and_save_data,
    display_performance_dashboard, get_cached_spreadsheet, get_gsheet_client,
    get_sector_from_mapping, load_data, load_data_from_file, load_total_cash_balance,
    log_cash_transaction, save_cash_balance, save_dividend_data, save_journal,
    save_portfolio, save_portfolio_snapshot
)


def render_tab_stock():
    ##########################
    # 8.แท็บข้อมูล
    ##############################  
    st.markdown("---") # เส้นคั่น เพื่อแยกส่วนกับตารางด้านบนให้ชัด
    st.subheader("🛠 ระบบจัดการข้อมูลและวิเคราะห์พอร์ต")

    # 1. สร้าง Tabs (จัดรวม แผนและ Alert ไว้ใน tab เดียวกัน)
    tab_dashboard, tab_portfolio, tab_dividend, tab_journal, tab_plan = st.tabs([
        "📈 Dashboard", "📊 พอร์ตโฟลิโอ", "💰 ข้อมูลปันผล", "📖 สมุดบันทึก", "📝 แผนและ Alert"
    ])

    ##############################
    with tab_dashboard:
        st.markdown("### 📊 Trading Performance Dashboard")

        # 1. ตรวจสอบและดึงข้อมูลจาก Google Sheets ชีต 'JournalData' ถ้า session_state ยังไม่มี
        if 'journal_data' not in st.session_state or not st.session_state['journal_data']:
            try:
                client = get_gsheet_client()
                sheet_journal = get_cached_spreadsheet(client, 'MyStockData').worksheet('JournalData') 
                raw_journal_data = sheet_journal.get_all_records()
                if raw_journal_data:
                    st.session_state['journal_data'] = raw_journal_data
            except Exception as e:
                st.error(f"❌ ไม่สามารถดึงข้อมูลประวัติการเทรดจาก Google Sheets ได้: {e}")

        # 2. ตรวจสอบข้อมูลใน session_state เพื่อนำมาแสดงผล
        if not st.session_state.get('journal_data'):
            st.info("ยังไม่มีข้อมูลรายการเทรดครับ กรุณาตรวจสอบการเชื่อมต่อ Google Sheets หรือเพิ่มข้อมูลรายการเทรดก่อน")
        else:
            df_journal = pd.DataFrame(st.session_state['journal_data'])

            # ป้องกันกรณีชื่อคอลัมน์มีช่องว่างติดมา
            df_journal.columns = [str(c).strip() for c in df_journal.columns]

            if 'วันที่' in df_journal.columns:
                df_journal['วันที่'] = pd.to_datetime(df_journal['วันที่'], errors='coerce')

            if 'สถานะ' in df_journal.columns:
                df_closed = df_journal[df_journal['สถานะ'] == 'Closed (ขายแล้ว)'].copy()
            else:
                df_closed = pd.DataFrame()

            if df_closed.empty:
                st.info("ยังไม่มีข้อมูลรายการที่ปิดสถานะ (Closed) เพื่อสรุปผลงานครับ")
            else:
                # ทำความสะอาดข้อมูลตัวเลข
                df_closed['กำไร/ขาดทุน (บาท)'] = pd.to_numeric(df_closed['กำไร/ขาดทุน (บาท)'].astype(str).str.replace(',', ''), errors='coerce')
                df_closed['ต้นทุน (บาท)'] = pd.to_numeric(df_closed['ต้นทุน (บาท)'].astype(str).str.replace(',', ''), errors='coerce')

                df_clean = df_closed.dropna(subset=['กำไร/ขาดทุน (บาท)', 'ต้นทุน (บาท)'])
                df_clean = df_clean[df_clean['ต้นทุน (บาท)'] > 100]
                df_clean['% ROI'] = (df_clean['กำไร/ขาดทุน (บาท)'] / df_clean['ต้นทุน (บาท)']) * 100

                # ตัวกรองข้อมูล (Filter)
                col_f1, col_f2 = st.columns([1, 3])
                filter_type = col_f1.selectbox("แสดงผลตาม:", ["ทั้งหมด", "รายปี", "รายเดือน"], key="dash_filter_type")

                df_filtered = df_clean.copy()
                available_years = sorted(df_clean['วันที่'].dt.year.dropna().unique(), reverse=True)

                if filter_type == "รายปี" and available_years:
                    year = col_f2.selectbox("เลือกปี:", available_years, key="dash_year")
                    df_filtered = df_clean[df_clean['วันที่'].dt.year == year]
                elif filter_type == "รายเดือน" and available_years:
                    col_y, col_m = col_f2.columns(2)
                    year = col_y.selectbox("เลือกปี:", available_years, key="dash_year_m")
                    month = col_m.selectbox("เลือกเดือน:", range(1, 13), key="dash_month")
                    df_filtered = df_clean[(df_clean['วันที่'].dt.year == year) & (df_clean['วันที่'].dt.month == month)]

                # คำนวณตัวชี้วัด (Metrics)
                wins = df_filtered[df_filtered['กำไร/ขาดทุน (บาท)'] > 0]
                losses = df_filtered[df_filtered['กำไร/ขาดทุน (บาท)'] < 0]
                avg_win = wins['กำไร/ขาดทุน (บาท)'].mean() if not wins.empty else 0
                avg_loss = abs(losses['กำไร/ขาดทุน (บาท)'].mean()) if not losses.empty else 1
                rr_ratio_actual = avg_win / avg_loss

                col1, col2, col3, col4, col5 = st.columns(5)

                # กำหนดยอดกำไรในอดีตที่ต้องการบวกเพิ่ม
                historical_profit = 77420.5
                total_net_profit = df_filtered['กำไร/ขาดทุน (บาท)'].sum() + historical_profit

                # แสดง Metric กำไร/ขาดทุนสุทธิ
                col1.metric("กำไร/ขาดทุนสุทธิ", f"{total_net_profit:,.2f} ฿")

                # ใส่ Note สีเทาอ่อนไว้ใต้ Metric ของ col1
                col1.markdown(
                    "<span style='color: #888888; font-size: 0.8em;'>historical profit 2018-2025 = 77,420.50</span>", 
                    unsafe_allow_html=True
                )
                col2.metric("ค่าเฉลี่ยต่อไม้ (%):", f"{df_clean['% ROI'].mean():.2f} %")
                col3.metric("Win Rate", f"{(len(wins)/len(df_filtered)*100):.1f}%" if not df_filtered.empty else "0%")
                col4.metric("Profit Factor", f"{(wins['กำไร/ขาดทุน (บาท)'].sum() / abs(losses['กำไร/ขาดทุน (บาท)'].sum())):.2f}" if not losses.empty and losses['กำไร/ขาดทุน (บาท)'].sum() != 0 else "N/A")
                col5.metric("Realized R:R", f"{rr_ratio_actual:.2f} : 1")

                st.markdown("---")
                st.markdown("##### 🔍 สถิติการเทรดเชิงลึก")
                col_s1, col_s2, col_s3 = st.columns(3)

                if not df_filtered.empty:  # 🔧 กันเหนียว: ถ้าเดือน/ปีที่เลือกไม่มีข้อมูลการเทรด ให้แจ้งเตือนแทนการ error
                    # 1. คำนวณกำไร/ขาดทุนต่อไม้ (เพื่อหา Best/Worst)
                    df_filtered['Profit_Pct'] = (df_filtered['กำไร/ขาดทุน (บาท)'] / df_filtered['ต้นทุน (บาท)']) * 100
                    idx_best = df_filtered['กำไร/ขาดทุน (บาท)'].idxmax()
                    idx_worst = df_filtered['กำไร/ขาดทุน (บาท)'].idxmin()

                    # 2. คำนวณ Max Drawdown จากประวัติมูลค่าพอร์ตสะสม (สมมติว่าคุณมี df_history หรือคำนวณจากยอดสะสม)
                    # กรณีนี้ผมใช้ logic หาค่า Drawdown สูงสุดจากยอดสะสมใน df_filtered
                    cumulative_profit = df_filtered['กำไร/ขาดทุน (บาท)'].cumsum()
                    running_max = cumulative_profit.cummax()
                    drawdown = (cumulative_profit - running_max) / (running_max + abs(df_filtered['ต้นทุน (บาท)'].sum())) # ประมาณการ MDD
                    max_drawdown = drawdown.min() * 100

                    # 3. ดึงค่า Best/Worst
                    best_val = df_filtered.loc[idx_best, 'กำไร/ขาดทุน (บาท)']
                    best_pct = df_filtered.loc[idx_best, 'Profit_Pct']
                    worst_val = df_filtered.loc[idx_worst, 'กำไร/ขาดทุน (บาท)']
                    worst_pct = df_filtered.loc[idx_worst, 'Profit_Pct']

                    # 4. แสดงผล 3 ช่อง
                    col_s1.metric("Max Drawdown", f"{max_drawdown:.1f}%")
                    col_s2.metric("กำไรสูงสุดต่อไม้", f"{best_val:,.0f} ฿", f"{best_pct:.1f}%")
                    col_s3.metric("ขาดทุนหนักสุดต่อไม้", f"{worst_val:,.0f} ฿", f"{worst_pct:.1f}%")
                else:
                    st.info(f"ℹ️ ไม่มีข้อมูลการเทรดในช่วงเวลาที่เลือก")

                ######### กราฟรายเดือน vs พร์อตสะสม ###################
                st.markdown("##### 📈 ผลงานรายเดือน vs พอร์ตสะสม")
                # --- 0. เตรียมข้อมูลรายการที่ขายแล้ว (Closed) และยึด "วันที่ขาย" เป็นหลัก ---
                if 'journal_data' in st.session_state and st.session_state.journal_data:
                    df_j_all = pd.DataFrame(st.session_state.journal_data)
                    df_closed_perf = df_j_all[df_j_all['สถานะ'] == 'Closed (ขายแล้ว)'].copy()
                else:
                    df_closed_perf = df_filtered.copy()

                df_closed_perf['Sell_Date'] = pd.to_datetime(df_closed_perf['วันที่ขาย'], errors='coerce')
                df_closed_perf['กำไร/ขาดทุน (บาท)'] = pd.to_numeric(df_closed_perf['กำไร/ขาดทุน (บาท)'], errors='coerce').fillna(0)
                df_closed_perf['ต้นทุน (บาท)'] = pd.to_numeric(df_closed_perf['ต้นทุน (บาท)'], errors='coerce').fillna(0)

                # ==========================================
                # ส่วนที่ 1: สำหรับกราฟแท่งและตาราง (รายเดือน มี Dropdown เลือกปี)
                # ==========================================
                available_years = sorted(df_closed_perf['Sell_Date'].dt.year.dropna().unique(), reverse=True)
                if not available_years:
                    available_years = [2026]

                df_closed_perf_sorted = df_closed_perf.sort_values('Sell_Date')

                # --- 3. ตัวเลือกสลับดูเป็น กราฟ หรือ ตาราง ---
                view_mode = st.radio("เลือกรูปแบบการแสดงผล:", ["📊 แสดงกราฟ", "📋 แสดงตารางข้อมูล"], horizontal=True, label_visibility="collapsed", key="view_mode_perf")

                if view_mode == "📊 แสดงกราฟ":
                    c1, c2 = st.columns(2)

                    with c1:
                        with st.container(border=True):
                            # ย้าย Dropdown เลือกปีเข้ามาไว้ด้านในฝั่งซ้าย (ให้ขนานกับ Dropdown ช่วงเวลากราฟเส้นฝั่งขวา)
                            selected_year = st.selectbox("📅 เลือกปีที่ต้องการดูผลงานกราฟแท่ง:", available_years, key="select_year_perf")

                            df_filtered_year = df_closed_perf_sorted[df_closed_perf_sorted['Sell_Date'].dt.year == selected_year].copy()

                            months_range = pd.date_range(start=f"{selected_year}-01-01", end=f"{selected_year}-12-01", freq='MS')
                            df_full_year = pd.DataFrame({
                                'Date': months_range,
                                'Month_Label': months_range.strftime('%b %Y')
                            })

                            if not df_filtered_year.empty:
                                df_filtered_year['Month_Label'] = df_filtered_year['Sell_Date'].dt.strftime('%b %Y')
                                df_grouped = df_filtered_year.groupby('Month_Label', sort=False).agg({
                                    'กำไร/ขาดทุน (บาท)': 'sum',
                                    'ต้นทุน (บาท)': 'sum'
                                }).reset_index()

                                df_monthly = pd.merge(df_full_year, df_grouped, on='Month_Label', how='left').fillna({
                                    'กำไร/ขาดทุน (บาท)': 0,
                                    'ต้นทุน (บาท)': 0
                                })
                            else:
                                df_monthly = df_full_year.copy()
                                df_monthly['กำไร/ขาดทุน (บาท)'] = 0
                                df_monthly['ต้นทุน (บาท)'] = 0

                            df_monthly = df_monthly.sort_values('Date').reset_index(drop=True)
                            df_monthly.columns = ['Date', 'Month_Label', 'Profit_Sum', 'Cost_Sum']
                            df_monthly['Color'] = df_monthly['Profit_Sum'].apply(lambda x: 'Profit' if x >= 0 else 'Loss')
                            df_monthly['Monthly_ROI'] = df_monthly.apply(
                                lambda row: (row['Profit_Sum'] / row['Cost_Sum'] * 100) if row['Cost_Sum'] > 0 else 0, 
                                axis=1
                            )
                            df_monthly['ROI_Text'] = df_monthly['Monthly_ROI'].apply(lambda x: f"{x:+.2f}%")

                            st.markdown(f"**📊 ผลงานรายเดือน ประจำปี {selected_year}**")

                            chart_bar = alt.Chart(df_monthly).mark_bar(width=25).encode(
                                x=alt.X('Month_Label:O', title='เดือน (ตามวันที่ขาย)', sort=None), 
                                y=alt.Y('Profit_Sum:Q', title='กำไร/ขาดทุน (บาท)'),
                                color=alt.Color('Color', scale=alt.Scale(domain=['Profit', 'Loss'], range=['#2ecc71', '#e74c3c']), legend=None),
                                tooltip=['Month_Label', 'Profit_Sum', alt.Tooltip('Monthly_ROI:Q', format='.2f', title='% ROI เดือน')]
                            )

                            text_labels = alt.Chart(df_monthly).mark_text(
                                align='center',
                                baseline='bottom', 
                                dy=-5, 
                                color='#888888', 
                                fontSize=10
                            ).encode(
                                x=alt.X('Month_Label:O', sort=None),
                                y=alt.Y('Profit_Sum:Q'),
                                text='ROI_Text:N'
                            )

                            rule = alt.Chart(pd.DataFrame({'y': [0]})).mark_rule(color='#666666', strokeDash=[3,3]).encode(y='y')

                            st.altair_chart((chart_bar + text_labels + rule).properties(height=350), use_container_width=True)

                    with c2:
                        with st.container(border=True):
                            # ==========================================
                            # ส่วนที่ 2: สำหรับกราฟเส้น (รองรับหลายปี + ตัวเลือกช่วงเวลา + Dynamic Aggregation + Zoom)
                            # ==========================================
                            initial_past_profit = 77420.5 # กำไรตั้งต้น

                            st.markdown("##### 📈 กราฟเส้นกำไรสะสมพอร์ตระยะยาว")

                            if not df_closed_perf_sorted.empty:
                                # 1. ทำตัวเลือกช่วงเวลา (Quick Filter) สำหรับกราฟเส้นโดยเฉพาะ
                                c_f1, c_f2 = st.columns([2, 2])
                                with c_f1:
                                    line_view_range = st.selectbox(
                                        "⏳ เลือกช่วงเวลาแสดงผล (กราฟเส้น):",
                                        ["ทั้งหมด (All Time)", "3 เดือนล่าสุด", "6 เดือนล่าสุด", "1 ปีล่าสุด (YTD / 12M)"],
                                        key="line_view_range"
                                    )

                                # กรองข้อมูลตามช่วงเวลาที่เลือก
                                df_line_filtered = df_closed_perf_sorted.copy()
                                max_date = df_line_filtered['Sell_Date'].max()

                                if line_view_range == "3 เดือนล่าสุด":
                                    start_date = max_date - pd.DateOffset(months=3)
                                    past_slice = df_line_filtered[df_line_filtered['Sell_Date'] < start_date]
                                    initial_past_profit_adjusted = initial_past_profit + past_slice['กำไร/ขาดทุน (บาท)'].sum()
                                    df_line_filtered = df_line_filtered[df_line_filtered['Sell_Date'] >= start_date]
                                elif line_view_range == "6 เดือนล่าสุด":
                                    start_date = max_date - pd.DateOffset(months=6)
                                    past_slice = df_line_filtered[df_line_filtered['Sell_Date'] < start_date]
                                    initial_past_profit_adjusted = initial_past_profit + past_slice['กำไร/ขาดทุน (บาท)'].sum()
                                    df_line_filtered = df_line_filtered[df_line_filtered['Sell_Date'] >= start_date]
                                elif line_view_range == "1 ปีล่าสุด (YTD / 12M)":
                                    start_date = max_date - pd.DateOffset(years=1)
                                    past_slice = df_line_filtered[df_line_filtered['Sell_Date'] < start_date]
                                    initial_past_profit_adjusted = initial_past_profit + past_slice['กำไร/ขาดทุน (บาท)'].sum()
                                    df_line_filtered = df_line_filtered[df_line_filtered['Sell_Date'] >= start_date]
                                else:
                                    initial_past_profit_adjusted = initial_past_profit

                                if not df_line_filtered.empty:
                                    # 2. Dynamic Aggregation: ตรวจสอบช่วงเวลา ถ้าระยะเวลามากกว่า 1 ปี ให้ยุบเป็น "รายเดือน" อัตโนมัติเพื่อกันกราฟแน่น
                                    date_span_days = (df_line_filtered['Sell_Date'].max() - df_line_filtered['Sell_Date'].min()).days

                                    if date_span_days > 365 and line_view_range == "ทั้งหมด (All Time)":
                                        df_line_filtered['Period_Key'] = df_line_filtered['Sell_Date'].dt.to_period('M')
                                        df_line_filtered['Time_Label'] = df_line_filtered['Period_Key'].apply(lambda r: r.strftime('%b %Y'))
                                        df_line_filtered['Sort_Time'] = df_line_filtered['Period_Key'].dt.start_time
                                        agg_freq_text = "รายเดือน (มุมมองระยะยาว)"
                                    else:
                                        df_line_filtered['Period_Key'] = df_line_filtered['Sell_Date'].dt.to_period('W-MON')
                                        df_line_filtered['Time_Label'] = df_line_filtered['Period_Key'].apply(lambda r: f"W{r.week} {r.start_time.strftime('%b %Y')}")
                                        df_line_filtered['Sort_Time'] = df_line_filtered['Period_Key'].dt.start_time
                                        agg_freq_text = "รายสัปดาห์ (เจาะลึก)"

                                    with c_f2:
                                        st.markdown(f"<p style='padding-top:28px; color:gray; font-size:13px;'>ℹ️ ความละเอียด: <b>{agg_freq_text}</b></p>", unsafe_allow_html=True)

                                    # รวมกำไรตามช่วงเวลาที่จัดกลุ่ม
                                    df_line_grouped = df_line_filtered.groupby(['Sort_Time', 'Time_Label'], as_index=False).agg({
                                        'กำไร/ขาดทุน (บาท)': 'sum'
                                    }).sort_values('Sort_Time')

                                    # คำนวณกำไรสะสมต่อเนื่อง
                                    df_line_grouped['Cumulative_Profit'] = initial_past_profit_adjusted + df_line_grouped['กำไร/ขาดทุน (บาท)'].cumsum()

                                    # 3. คำนวณขอบเขตแกน Y ให้เผื่อพื้นที่ด้านบนเพิ่ม 15% (แก้ปัญหาเส้นชนขอบบน)
                                    y_max = df_line_grouped['Cumulative_Profit'].max()
                                    y_min = df_line_grouped['Cumulative_Profit'].min()
                                    y_upper_limit = y_max * 1.15 if y_max > 0 else y_max * 0.85

                                    # สร้างกราฟเส้นพร้อมกำหนด Scale แกน Y และเปิด Interactive Zoom & Pan
                                    chart_line = alt.Chart(df_line_grouped).mark_line(point=True, color='#3498db', strokeWidth=3).encode(
                                        x=alt.X('Time_Label:O', title='ช่วงเวลาที่มีการเคลื่อนไหว', sort=list(df_line_grouped['Time_Label'])),
                                        y=alt.Y('Cumulative_Profit:Q', title='กำไรสะสม (บาท)', scale=alt.Scale(domain=[y_min, y_upper_limit], nice=True)),
                                        tooltip=['Time_Label', 'Cumulative_Profit']
                                    ).properties(
                                        height=350
                                    ).interactive()

                                    st.altair_chart(chart_line, use_container_width=True)
                                else:
                                    st.info("ไม่มีข้อมูลในช่วงเวลาที่เลือก")
                            else:
                                st.info("ยังไม่มีข้อมูลประวัติการเทรดที่ปิดสถานะ")

                else:
                    # สำหรับโหมดตาราง (ใช้ปีที่เลือกจากฝั่งซ้ายมาแสดงผล)
                    selected_year = st.session_state.get('select_year_perf', available_years[0])
                    df_filtered_year = df_closed_perf_sorted[df_closed_perf_sorted['Sell_Date'].dt.year == selected_year].copy()

                    months_range = pd.date_range(start=f"{selected_year}-01-01", end=f"{selected_year}-12-01", freq='MS')
                    df_full_year = pd.DataFrame({
                        'Date': months_range,
                        'Month_Label': months_range.strftime('%b %Y')
                    })

                    if not df_filtered_year.empty:
                        df_filtered_year['Month_Label'] = df_filtered_year['Sell_Date'].dt.strftime('%b %Y')
                        df_grouped = df_filtered_year.groupby('Month_Label', sort=False).agg({
                            'กำไร/ขาดทุน (บาท)': 'sum',
                            'ต้นทุน (บาท)': 'sum'
                        }).reset_index()
                        df_monthly = pd.merge(df_full_year, df_grouped, on='Month_Label', how='left').fillna({
                            'กำไร/ขาดทุน (บาท)': 0,
                            'ต้นทุน (บาท)': 0
                        })
                    else:
                        df_monthly = df_full_year.copy()
                        df_monthly['กำไร/ขาดทุน (บาท)'] = 0
                        df_monthly['ต้นทุน (บาท)'] = 0

                    df_monthly = df_monthly.sort_values('Date').reset_index(drop=True)
                    df_monthly.columns = ['Date', 'Month_Label', 'Profit_Sum', 'Cost_Sum']
                    df_monthly['Monthly_ROI'] = df_monthly.apply(
                        lambda row: (row['Profit_Sum'] / row['Cost_Sum'] * 100) if row['Cost_Sum'] > 0 else 0, 
                        axis=1
                    )

                    st.markdown(f"##### 📋 ตารางสรุปผลงานรายเดือน (อิงวันที่ขาย) ประจำปี {selected_year}")
                    df_display = df_monthly[['Month_Label', 'Profit_Sum', 'Cost_Sum', 'Monthly_ROI']].copy()
                    df_display.columns = ['เดือน', 'กำไร/ขาดทุน (บาท)', 'ต้นทุนประจำเดือน (บาท)', '% กำไร/ขาดทุน (ROI)']

                    st.dataframe(
                        df_display.style.format({
                            'กำไร/ขาดทุน (บาท)': '{:,.2f}',
                            'ต้นทุนประจำเดือน (บาท)': '{:,.2f}',
                            '% กำไร/ขาดทุน (ROI)': '{:.2f}%'
                        }),
                        use_container_width=True
                    )

                ##### กราฟกระจายตัว (Histogram) ###########
                with st.container(border=True):
                    st.markdown("##### 🔔 การกระจายตัวกำไร/ขาดทุน (%)")

                    # 1. จัดการข้อมูลให้พร้อมก่อนแสดงผล
                    if not df_filtered.empty:
                        df_filtered = df_filtered.copy()
                        df_filtered['Profit_Pct'] = (df_filtered['กำไร/ขาดทุน (บาท)'] / df_filtered['ต้นทุน (บาท)'].replace(0, 1)) * 100
                        wins = df_filtered[df_filtered['กำไร/ขาดทุน (บาท)'] > 0]
                        losses = df_filtered[df_filtered['กำไร/ขาดทุน (บาท)'] < 0]

                        mean_val = df_filtered['Profit_Pct'].mean()
                        avg_loss_pct = losses['Profit_Pct'].mean() if not losses.empty else 0
                        optimal_cutloss_pct = -(wins['Profit_Pct'].mean() / 2.0) if not wins.empty else None

                        # 2. แสดง Metric ด้วย HTML เพื่อคุมสีให้ตรงกับสีเส้นในกราฟ
                        col_m1, col_m2, col_m3 = st.columns(3)
                        col_m1.markdown(f"<div style='text-align: center; color: #12da58; font-size: 20px; font-weight: bold;'>Mean</div><div style='text-align: center; font-size: 24px;'>{mean_val:.1f}%</div>", unsafe_allow_html=True)
                        col_m2.markdown(f"<div style='text-align: center; color: #9b59b6; font-size: 20px; font-weight: bold;'>Avg Loss</div><div style='text-align: center; font-size: 24px;'>{avg_loss_pct:.1f}%</div>", unsafe_allow_html=True)
                        if optimal_cutloss_pct is not None:
                            col_m3.markdown(f"<div style='text-align: center; color: #f21d2b; font-size: 20px; font-weight: bold;'>Target Cut</div><div style='text-align: center; font-size: 24px;'>{optimal_cutloss_pct:.1f}%</div>", unsafe_allow_html=True)

                        # 3. วาดกราฟ (เรียกผ่าน plotly.express โดยตรง ป้องกัน Error ซ้ำซ้อน)
                        fig = plotly.express.histogram(df_filtered, x='Profit_Pct', nbins=20, opacity=0.6, color_discrete_sequence=['#3498db'])

                        # เพิ่ม annotation_yshift ให้ต่ำลงเล็กน้อย และลดระยะห่าง
                        fig.add_vline(x=mean_val, line_dash="dash", line_color="#12da58", 
                                      annotation_text=f"Mean ({mean_val:.1f}%)", annotation_position="top right", annotation_yshift=20)
                        fig.add_vline(x=avg_loss_pct, line_dash="dot", line_color="#9b59b6", 
                                      annotation_text=f"Avg Loss ({avg_loss_pct:.1f}%)", annotation_position="top right", annotation_yshift=-10)
                        if optimal_cutloss_pct is not None:
                            fig.add_vline(x=optimal_cutloss_pct, line_dash="dashdot", line_color="#f21d2b", 
                                          annotation_text=f"Target ({optimal_cutloss_pct:.1f}%)", annotation_position="top right", annotation_yshift=-40)

                        # เพิ่ม margin top เพื่อให้มีพื้นที่เหลือให้ป้ายข้อความด้านบนไม่ถูกตัด
                        fig.update_layout(margin=dict(t=50, b=20, l=20, r=20), height=350, plot_bgcolor='rgba(0,0,0,0)')
                        st.plotly_chart(fig, use_container_width=True)

                    else:
                        st.info("ยังไม่มีข้อมูลเพียงพอที่จะแสดงกราฟการกระจายตัวครับ")

                ####################
                if st.button("🔄 อัปเดตข้อมูลย้อนหลัง (Backfill)"):
                    with st.spinner('กำลังคำนวณข้อมูลย้อนหลัง (อาจใช้เวลาสักครู่)...'):
                        # เรียกใช้ฟังก์ชันที่เขียนไว้
                        backfill_portfolio_history()
                        st.success("อัปเดตเรียบร้อย! กราฟของคุณพร้อมใช้งานแล้ว")
                # Equity Curve 
                st.markdown("---")
                with st.container(border=True):
                    st.markdown("##### 📈 Equity Curve")

                    # เรียกใช้งานฟังก์ชันที่ย้ายไปด้านบน
                    try:
                        display_performance_dashboard()
                    except Exception as e:
                        st.warning(f"ยังไม่พบข้อมูล Portfolio_History หรือเกิดข้อผิดพลาดในการโหลด: {e}")

                    # --- 2. ส่วนวิเคราะห์ Sector Performance (แก้ไขป้องกัน Error ประเภทข้อมูล) ---
                    journal_df = pd.DataFrame(st.session_state.get('journal_data', []))
                    closed_trades = journal_df[journal_df['สถานะ'] == 'Closed (ขายแล้ว)'] if not journal_df.empty else pd.DataFrame()

                    if not journal_df.empty:
                        sector_data_list = []
                        for idx, row in journal_df.iterrows():
                            ticker = row.get('หุ้น', 'UNKNOWN')

                            # ป้องกันค่าที่เป็น String หรือค่าว่าง ให้แปลงเป็น float ทันที
                            try:
                                profit = float(row.get('กำไร/ขาดทุน (บาท)', 0))
                            except (ValueError, TypeError):
                                profit = 0.0

                            try:
                                cost = float(row.get('ต้นทุน (บาท)', 0))
                            except (ValueError, TypeError):
                                cost = 0.0

                            sector = row.get('Sector', 'General / Unspecified')
                            if pd.isna(sector) or str(sector).strip() == '': 
                                sector = 'General / Unspecified'

                            sector_data_list.append({
                                'Sector': str(sector).strip(),
                                'Ticker': str(ticker).strip(),
                                'Net_Profit': profit,
                                'Invested_Cost': cost
                            })

                        if len(sector_data_list) > 0:
                            df_sector_source = pd.DataFrame(sector_data_list)

                            # บังคับแปลงชนิดข้อมูลให้เป็นตัวเลขชัวร์ๆ อีกรอบก่อน Groupby
                            df_sector_source['Net_Profit'] = pd.to_numeric(df_sector_source['Net_Profit'], errors='coerce').fillna(0)
                            df_sector_source['Invested_Cost'] = pd.to_numeric(df_sector_source['Invested_Cost'], errors='coerce').fillna(0)

                            df_sector_summary = df_sector_source.groupby('Sector', as_index=False).agg({
                                'Net_Profit': 'sum',
                                'Invested_Cost': 'sum',
                                'Ticker': lambda x: ', '.join(x.unique())
                            })

                            df_sector_summary['Return_Pct'] = df_sector_summary.apply(
                                lambda r: (r['Net_Profit'] / r['Invested_Cost'] * 100) if r['Invested_Cost'] > 0 else 0, 
                                axis=1
                            )
                            df_sector_summary = df_sector_summary.sort_values(by='Net_Profit', ascending=False)

                            # 📊 ส่วน กราฟแท่ง (Bar Chart)
                            st.markdown("##### 📊 กำไร/ขาดทุนสะสมแยกตามกลุ่มอุตสาหกรรม")
                            fig_bar = px.bar(
                                df_sector_summary, 
                                x='Sector', 
                                y='Net_Profit', 
                                text=df_sector_summary['Net_Profit'].apply(lambda x: f"{x:,.2f} ฿"), 
                                color='Net_Profit', 
                                color_continuous_scale=['#EF5350', '#26A69A']
                            )
                            fig_bar.update_traces(textposition='outside')
                            fig_bar.update_layout(
                                xaxis_title="กลุ่มอุตสาหกรรม (Sector)", 
                                yaxis_title="กำไร/ขาดทุนสุทธิ (บาท)", 
                                height=400, 
                                margin=dict(l=20, r=20, t=30, b=20), 
                                coloraxis_showscale=False
                            )
                            st.plotly_chart(fig_bar, use_container_width=True)

                            # 🗺️ ส่วน Treemap
                            st.markdown("##### 🗺️ แผนผังแสดงสัดส่วนและผลงานพอร์ตตาม Sector (Treemap)")
                            fig_tree = px.treemap(
                                df_sector_summary, 
                                path=['Sector'], 
                                values='Invested_Cost', 
                                color='Return_Pct', 
                                color_continuous_scale='Tealrose', 
                                color_continuous_midpoint=0, 
                                custom_data=['Net_Profit', 'Return_Pct', 'Ticker']
                            )
                            fig_tree.update_traces(
                                hovertemplate='<b>Sector:</b> %{label}<br><b>เงินลงทุนรวม:</b> %{value:,.2f} ฿<br><b>กำไร/ขาดทุน:</b> %{customdata[0]:,.2f} ฿<br><b>ผลตอบแทน:</b> %{customdata[1]:+.2f}%<br><b>หุ้นในกลุ่ม:</b> %{customdata[2]}'
                            )
                            fig_tree.update_layout(height=400, margin=dict(l=10, r=10, t=10, b=10))
                            st.plotly_chart(fig_tree, use_container_width=True)

                            # 📋 ตารางสรุปข้อมูล Sector (ปัดเศษทศนิยม 2 ตำแหน่งจริง ๆ ก่อนแสดงผล)
                            st.markdown("##### 📋 ตารางสรุปข้อมูลแยกตาม Sector")
                            display_sector_df = df_sector_summary[['Sector', 'Invested_Cost', 'Net_Profit', 'Return_Pct', 'Ticker']].copy()

                            # ปัดเศษทศนิยม 2 ตำแหน่งให้คอลัมน์ Return_Pct ตรงนี้เลย
                            display_sector_df['Return_Pct'] = display_sector_df['Return_Pct'].round(2)

                            display_sector_df.columns = ['กลุ่มอุตสาหกรรม (Sector)', 'เงินลงทุนรวม (บาท)', 'กำไร/ขาดทุนสุทธิ (บาท)', '% ผลตอบแทน', 'รายชื่อหุ้นที่เกี่ยวข้อง']

                            st.dataframe(
                                display_sector_df.style.format({
                                    'เงินลงทุนรวม (บาท)': '{:,.2f}',
                                    'กำไร/ขาดทุนสุทธิ (บาท)': '{:,.2f}',
                                    '% ผลตอบแทน': '{:+.2f}%'
                                }).set_properties(**{'text-align': 'right'}), 
                                use_container_width=True
                            )
                        else:
                            st.info("ยังไม่มีข้อมูลเพียงพอสำหรับการวิเคราะห์ Sector")
                    else:
                        st.info("ยังไม่มีข้อมูลรายการเทรดในระบบครับ")

                #######################################
                # 1. จัดการข้อมูล (ยังคงตรรกะเดิมไว้)
                df_summary = df_filtered.groupby('หุ้น')['กำไร/ขาดทุน (บาท)'].sum().reset_index()
                df_summary = df_summary.sort_values(by='กำไร/ขาดทุน (บาท)', ascending=False)
                top_ticker = df_summary.iloc[0]['หุ้น']

                # แสดงข้อมูลหุ้นตัวเก่งแบบสรุปที่เปิดตลอดเวลา
                st.info(f"หุ้นที่ทำกำไรให้คุณมากที่สุดในปัจจุบันคือ: **{top_ticker}**")

                # --- ส่วนตารางสรุปรายหุ้น (ซ่อนได้) ---
                with st.expander("🏆 ดูตารางสรุปผลงานรายหุ้น"):
                    # แปลงคอลัมน์วันที่ให้เป็น datetime
                    df_filtered['วันที่ซื้อ'] = pd.to_datetime(df_filtered['วันที่ซื้อ'])
                    df_filtered['วันที่ขาย'] = pd.to_datetime(df_filtered['วันที่ขาย'])

                    # 1. คำนวณ Holding Time ทีละแถว
                    # ถ้าวันที่ขายเป็น NaT (คือยังไม่ขาย) ให้ใช้วันปัจจุบัน
                    now = pd.Timestamp.now()
                    df_filtered['Hold_Days'] = df_filtered.apply(
                        lambda row: (row['วันที่ขาย'] - row['วันที่ซื้อ']).days 
                        if pd.notnull(row['วันที่ขาย']) 
                        else (now - row['วันที่ซื้อ']).days, 
                        axis=1
                    )
                    # คำนวณข้อมูลตามเดิม
                    summary = df_filtered.groupby('หุ้น').agg({
                        'กำไร/ขาดทุน (บาท)': 'sum',
                        'ต้นทุน (บาท)': 'sum'
                    })
                    summary['% Return'] = (summary['กำไร/ขาดทุน (บาท)'] / summary['ต้นทุน (บาท)']) * 100

                    df_filtered['วันที่'] = pd.to_datetime(df_filtered['วันที่'])
                    hold_time = df_filtered.groupby('หุ้น')['วันที่'].min()
                    summary['Holding Time'] = (pd.Timestamp.now() - hold_time).dt.days

                    # ปรับชื่อคอลัมน์และเลือกเฉพาะที่ต้องการ
                    display_df = summary.reset_index()
                    display_df = display_df[['หุ้น', 'กำไร/ขาดทุน (บาท)', '% Return', 'Holding Time']]
                    display_df.columns = ['Ticker', 'Total Profit/Loss', '% Return', 'Holding Time']

                    # แสดงตารางแบบไม่ต้องใช้ column_config ก่อน เพื่อเช็คว่าข้อมูลมาครบไหม
                    # ถ้าวิธีนี้เห็นตัวเลข แสดงว่าปัญหาอยู่ที่ column_config ที่คุณใช้
                    st.dataframe(display_df, use_container_width=True)

                    # ถ้าข้อมูลในตารางนี้แสดงผลครบถ้วน ให้ค่อยๆ เพิ่ม column_config ทีละส่วนครับ
                with st.expander("🎯 Win Rate รายหุ้น (หุ้นตัวไหนแม่นที่สุด)"):
                    # 1. เตรียมข้อมูลสำหรับคำนวณ Win Rate
                    # แยกกำไร (>0) และ ขาดทุน (<=0)
                    df_filtered['is_win'] = df_filtered['กำไร/ขาดทุน (บาท)'] > 0

                    # 2. Group ข้อมูลรายหุ้น
                    win_rate_df = df_filtered.groupby('หุ้น').agg(
                        Total_Trades=('หุ้น', 'count'),
                        Wins=('is_win', 'sum')
                    )

                    # คำนวณ % Win Rate
                    win_rate_df['Win Rate (%)'] = (win_rate_df['Wins'] / win_rate_df['Total_Trades']) * 100

                    # 3. จัดระเบียบตาราง
                    win_rate_df = win_rate_df.sort_values(by='Win Rate (%)', ascending=False).reset_index()
                    win_rate_df = win_rate_df.rename(columns={'หุ้น': 'Ticker'})

                    # 4. แสดงตารางแบบ Basic ที่ดูง่าย
                    st.dataframe(
                        win_rate_df[['Ticker', 'Win Rate (%)', 'Total_Trades']],
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "Win Rate (%)": st.column_config.ProgressColumn(
                                "Win Rate (%)",
                                format="%.1f%%",
                                min_value=0,
                                max_value=100,
                            ),
                            "Total_Trades": "จำนวนครั้งที่เทรด"
                        }
                    )

                    # 5. สรุปสั้นๆ ให้
                    best_stock = win_rate_df.iloc[0]['Ticker']
                    worst_stock = win_rate_df.iloc[-1]['Ticker']
                    st.write(f"✅ หุ้นที่วินเรทสูงที่สุด: **{best_stock}**")
                    st.write(f"⚠️ หุ้นที่วินเรทต่ำที่สุด: **{worst_stock}**")
                #########
                with st.expander("🏆 ตารางสรุปผลงานรายหุ้น (Annualized Return)"):
                    # 1. จัดเตรียมข้อมูล: แปลงวันที่และจัดการค่าว่าง
                    df_filtered['วันที่ซื้อ'] = pd.to_datetime(df_filtered['วันที่ซื้อ'])
                    df_filtered['วันที่ขาย'] = pd.to_datetime(df_filtered['วันที่ขาย'])
                    now = pd.Timestamp.now()

                    # 2. คำนวณ Holding Time อย่างปลอดภัย
                    df_filtered['Hold_Days'] = df_filtered.apply(
                        lambda row: (row['วันที่ขาย'] - row['วันที่ซื้อ']).days if pd.notnull(row['วันที่ขาย']) 
                        else (now - row['วันที่ซื้อ']).days, axis=1
                    )
                    df_filtered['Hold_Days'] = df_filtered['Hold_Days'].clip(lower=1)

                    # 3. คำนวณสรุปรายหุ้น
                    summary = df_filtered.groupby('หุ้น').agg({
                        'กำไร/ขาดทุน (บาท)': 'sum',
                        'ต้นทุน (บาท)': 'sum',
                        'Hold_Days': 'mean'
                    })

                    # 4. คำนวณตัวเลข
                    summary['% Return'] = (summary['กำไร/ขาดทุน (บาท)'] / summary['ต้นทุน (บาท)']) * 100
                    summary['Annualized Return'] = (((1 + (summary['% Return'] / 100)) ** (365 / summary['Hold_Days'])) - 1) * 100
                    summary = summary.replace([float('inf'), -float('inf')], 0).fillna(0)

                    # 5. เตรียม DataFrame สำหรับแสดงผล
                    display_df = summary.reset_index()

                    # 6. แปลงข้อมูลเป็น String ที่จัดรูปแบบตามต้องการ (วิธีนี้แก้ปัญหาช่องว่างได้ถาวร)
                    final_df = pd.DataFrame({
                        "Ticker": display_df['หุ้น'],
                        "Profit/Loss (บาท)": display_df['กำไร/ขาดทุน (บาท)'].apply(lambda x: f"{x:,.2f} ฿"),
                        "Return (%)": display_df['% Return'].apply(lambda x: f"{x:.2f} %"),
                        "Annualized Return (%)": display_df['Annualized Return'].apply(lambda x: f"{x:,.2f} %"),
                        "Holding Time (วัน)": display_df['Hold_Days'].apply(lambda x: f"{int(x)} วัน")
                    })

                    # 7. แสดงผล
                    st.dataframe(
                        final_df,
                        use_container_width=True,
                        hide_index=True
                    )
                ########
                with st.expander("📊 วิเคราะห์ประสิทธิภาพเชิงลึก (Efficiency & Time-to-Profit)"):
                    # คำนวณเบื้องต้น (ต่อจากของเดิม)
                    # ... (สมมติว่ามี df_filtered อยู่แล้ว)

                    # 1. แยกกลุ่มหุ้นทำกำไร และหุ้นขาดทุน เพื่อหา Time-to-Profit
                    winners = df_filtered[df_filtered['กำไร/ขาดทุน (บาท)'] > 0]
                    losers = df_filtered[df_filtered['กำไร/ขาดทุน (บาท)'] <= 0]

                    avg_win_time = winners['Hold_Days'].mean() if not winners.empty else 0
                    avg_loss_time = losers['Hold_Days'].mean() if not losers.empty else 0

                    # 2. คำนวณ Efficiency Ratio รายหุ้น (กำไรต่อวัน)
                    summary['Profit Per Day'] = summary['กำไร/ขาดทุน (บาท)'] / summary['Hold_Days']

                    # 3. เตรียมข้อมูลแสดงผลเป็นข้อความ (ป้องกัน error)
                    analytics_df = pd.DataFrame({
                        "Ticker": summary.index,
                        "Profit/Loss (บาท)": summary['กำไร/ขาดทุน (บาท)'].apply(lambda x: f"{x:,.2f} ฿"),
                        "Profit Per Day (บาท/วัน)": summary['Profit Per Day'].apply(lambda x: f"{x:,.2f} ฿"),
                        "Avg Hold Days (วัน)": summary['Hold_Days'].apply(lambda x: f"{x:.1f} วัน")
                    })

                    # แสดงตารางวิเคราะห์
                    st.dataframe(analytics_df, use_container_width=True, hide_index=True)

                    # 4. แสดงสรุปเชิงกลยุทธ์ (Time-to-Profit Insights)
                    st.divider()
                    st.subheader("💡 วิเคราะห์นิสัยการเทรด (Insights)")

                    col1, col2 = st.columns(2)
                    col1.metric("ถือหุ้นกำไรเฉลี่ย", f"{avg_win_time:.1f} วัน")
                    col2.metric("ถือหุ้นขาดทุนเฉลี่ย", f"{avg_loss_time:.1f} วัน")

                    if avg_win_time < avg_loss_time:
                        st.success("✅ ระบบของคุณ: ทำกำไรได้รวดเร็ว (ถือหุ้นกำไรสั้นกว่าหุ้นที่ขาดทุน)")
                    else:
                        st.warning("⚠️ ข้อสังเกต: คุณอาจจะทนถือหุ้นที่ขาดทุนนานกว่าหุ้นที่ทำกำไร (Loss Aversion)")

                #####
                with st.expander("📈 Opportunity Cost Matrix (หุ้นไหนควรเก็บ หุ้นไหนควรทิ้ง)"):
                    # 1. เตรียมข้อมูลสำหรับทำกราฟ
                    plot_df = summary.reset_index()
                    plot_df['% Return'] = (plot_df['กำไร/ขาดทุน (บาท)'] / plot_df['ต้นทุน (บาท)']) * 100

                    # 2. สร้างกราฟ Scatter Plot
                    fig = px.scatter(
                        plot_df, 
                        x='Hold_Days', 
                        y='% Return', 
                        text='หุ้น',
                        title="Holding Time vs % Return",
                        labels={'Hold_Days': 'ระยะเวลาการถือครอง (วัน)', '% Return': 'ผลตอบแทน (%)'},
                        size_max=60
                    )

                    # 3. เพิ่มเส้นแบ่ง (Quadrants) เพื่อให้ดูง่ายขึ้น
                    fig.add_hline(y=0, line_dash="dash", line_color="red") # เส้นแบ่ง กำไร/ขาดทุน
                    fig.add_vline(x=plot_df['Hold_Days'].mean(), line_dash="dash", line_color="gray") # เส้นแบ่ง ถือสั้น/ถือนาน

                    fig.update_traces(textposition='top center')

                    # 4. แสดงผล
                    st.plotly_chart(fig, use_container_width=True)

                    # 5. สรุปคำแนะนำจากกราฟ
                    st.markdown("""
                    **วิธีอ่านกราฟ Opportunity Cost:**
                    *   **บน-ซ้าย (High Return, Low Holding Time):** ✅ **Super Stock** ของคุณ! ทำเงินได้เร็วและคุ้มค่าที่สุด
                    *   **ล่าง-ขวา (Low Return, High Holding Time):** ⚠️ **Dead Money** หุ้นตัวที่กินเวลาชีวิตคุณไปนานแต่ไม่ทำกำไร (พิจารณาขายทิ้งเพื่อนำเงินไปหาโอกาสใหม่)
                    *   **บน-ขวา (High Return, High Holding Time):** 🐢 **Value/Trend Stock** เป็นหุ้นที่ต้องถือยาวถึงจะกำไร ถ้าคุณชอบสไตล์นี้ถือว่าโอเคครับ
                    """)
                # --- ส่วนกราฟเปรียบเทียบ (ซ่อนได้) ---
                with st.expander("📈 ดูพอร์ตภาพรวม vs พอร์ตหักหุ้นตัวเก่งออก"):
                    # แยกข้อมูลพอร์ต
                    df_rest = df_filtered[df_filtered['หุ้น'] != top_ticker]

                    # คำนวณกราฟ
                    df_filtered_sorted = df_filtered.sort_values('วันที่')
                    df_rest_sorted = df_rest.sort_values('วันที่')

                    all_portfolio = df_filtered_sorted.set_index('วันที่')['กำไร/ขาดทุน (บาท)'].cumsum().groupby('วันที่').last()
                    core_portfolio = df_rest_sorted.set_index('วันที่')['กำไร/ขาดทุน (บาท)'].cumsum().groupby('วันที่').last()

                    # สร้าง DataFrame
                    chart_data = pd.concat([all_portfolio, core_portfolio], axis=1)
                    chart_data.columns = ['พอร์ตทั้งหมด', 'พอร์ตหักหุ้นตัวเก่ง']

                    # วิธีที่ชัวร์ที่สุดสำหรับ Pandas ทุกเวอร์ชัน
                    chart_data = chart_data.ffill() 
                    chart_data = chart_data.fillna(0)

                    st.line_chart(chart_data)

    #########################            
    with tab_portfolio:
        st.markdown("#### 💼 ระบบบันทึกพอร์ตโฟลิโอส่วนตัว")

        # 1. จัดการเงินสด (แก้ไขด้วยตัวเองได้ตลอดเวลา)
        if "cash_balance" not in st.session_state:
            st.session_state.cash_balance = load_total_cash_balance()

        # ส่วนแสดงปุ่มเข้าออกเงินสด 
        with st.expander("💰 บันทึกรายการเงินสดเข้า-ออก"):
            with st.form("cash_flow_form", clear_on_submit=True):
                c1, c2, c3 = st.columns(3)
                with c1:
                    log_date = st.date_input("วันที่:")
                with c2:
                    log_type = st.selectbox("ประเภท:", ["เติมเงินสด", "เงินปันผล", "เงินรายได้อื่นๆ", "ถอนเงินสด"])
                with c3:
                    log_amount = st.number_input("จำนวนเงิน:", step=100.0)

                log_note = st.text_input("หมายเหตุ:")
                submitted_cash = st.form_submit_button("บันทึกรายการเงินสด")

                if submitted_cash:
                    # คำนวณค่าบวก/ลบ ตามประเภท
                    actual_amount = log_amount if log_type in ["เติมเงินสด", "เงินปันผล", "เงินรายได้อื่นๆ"] else -log_amount

                    # บันทึกผ่านฟังก์ชันที่เราทำไว้
                    log_cash_transaction(
                        date=str(log_date),
                        trans_type=log_type,
                        amount=actual_amount,
                        note=log_note
                    )
                    # อัปเดต Session เพื่อให้ยอดเงินโชว์ทันที
                    st.session_state.cash_balance += actual_amount
                    st.success(f"บันทึก {log_type} สำเร็จ!")
                    st.rerun()

        # 2. ฟอร์มเพิ่ม/ลดหุ้น
        with st.expander("🔄 บันทึกการซื้อขายหุ้น (อัปเดต Portfolio & Journal)"):
            col1, col2 = st.columns(2)

            portfolio_stocks = [item['หุ้น'] for item in st.session_state.my_portfolio] if "my_portfolio" in st.session_state else []

            with col1:
                options = ["  "] + portfolio_stocks

                # 🌟 สร้างฟังก์ชัน Callback สำหรับอัปเดต Sector อัตโนมัติเมื่อเปลี่ยนตัวเลือกหุ้น
                def update_sector_on_select():
                    # ใช้ .get() เพื่อป้องกัน AttributeError ถ้าคีย์ยังไม่ถูกสร้างใน session_state
                    selected = st.session_state.get("journal_select_ticker", "  ")
                    if selected != "  ":
                        # 1. เช็คจากพอร์ตก่อน
                        matched_item = next((item for item in st.session_state.get('my_portfolio', []) if item.get('หุ้น', item.get('Ticker', '')) == selected), None)
                        if matched_item and matched_item.get('Sector') and matched_item.get('Sector') != "General / Unspecified":
                            st.session_state.journal_p_sector = matched_item['Sector']
                        else:
                            # 2. ถ้าไม่มีในพอร์ต ดึงจาก Dictionary A-Z
                            st.session_state.journal_p_sector = get_sector_from_mapping(selected)
                    else:
                        st.session_state.journal_p_sector = "General / Unspecified"

                select_ticker = st.selectbox(
                    "เลือกหุ้นจากพอร์ต:", 
                    options, 
                    key="journal_select_ticker",
                    on_change=update_sector_on_select
                )

                # กำหนดค่าเริ่มต้นของ Sector ตอนโหลดครั้งแรก
                if "journal_p_sector" not in st.session_state:
                    st.session_state.journal_p_sector = "General / Unspecified"

                if select_ticker != "  ":
                    p_ticker = select_ticker
                else:
                    p_ticker = st.text_input("ชื่อหุ้น:", key="journal_p_ticker")
                    # ถ้าพิมพ์ชื่อหุ้นใหม่เอง ให้เช็คจาก Dictionary แล้วอัปเดตลงช่อง Sector ทันที
                    if p_ticker:
                        st.session_state.journal_p_sector = get_sector_from_mapping(p_ticker)

                # ช่องกรอก Sector ที่ผูกกับ st.session_state.journal_p_sector โดยตรง
                p_sector = st.text_input("กลุ่มอุตสาหกรรม (Sector):", key="journal_p_sector")

                p_status = st.selectbox("สถานะรายการ:", ["Open (กำลังถือ)", "Closed (ขายแล้ว)"], key="journal_p_status")

                if p_status == "Closed (ขายแล้ว)":
                    p_buy_date = st.date_input("📅 วันที่ซื้อหุ้น (ต้นทุนเดิม):", key="journal_p_buy_date")
                    p_sell_date = st.date_input("📅 วันที่ขายจริง (วันที่ทำรายการ):", key="journal_p_sell_date")
                else:
                    p_buy_date = st.date_input("📅 วันที่ทำรายการซื้อ:", key="journal_open_date")
                    p_sell_date = None

            with col2:
                p_type = st.selectbox("ประเภท:", ["ซื้อ (Buy)", "ขายทำกำไร (Take Profit)", "ขายตัดขาดทุน (Stop Loss)"], key="journal_p_type")
                p_result = st.number_input("กำไร/ขาดทุน (บาท):", step=100.0, format="%.2f", help="กรอกแค่ตัวเลข ระบบจะใส่เครื่องหมายให้เอง", key="journal_p_result")
                p_price = st.number_input("ราคาต่อหุ้น:", min_value=0.01, step=0.05, format="%.2f", key="journal_p_price")
                p_qty = st.number_input("จำนวนหุ้น:", min_value=1, step=100, key="journal_p_qty")
                p_comm = st.number_input("ค่าธรรมเนียม:", min_value=0.0, step=1.0, key="journal_p_comm")

            p_reason = st.text_area("เหตุผล/กลยุทธ์:", key="journal_p_reason")
            submitted = st.button("ยืนยันรายการบันทึก", type="primary")

            if submitted:
                if not p_ticker or p_ticker.strip() == "":
                    st.error("กรุณาระบุชื่อหุ้นให้เรียบร้อยครับ")
                else:
                    total_val = (p_qty * p_price)
                    ticker_upper = p_ticker.upper()

                    # Logic อัตโนมัติ: ถ้าเป็น Stop Loss หรือ ขาดทุน ให้บังคับเป็นค่าลบ
                    final_result = float(p_result)
                    if "Stop Loss" in p_type or "ขาดทุน" in p_status:
                        final_result = -abs(final_result) 
                    else:
                        final_result = abs(final_result)  

                    transaction_date_str = str(p_sell_date) if p_status == "Closed (ขายแล้ว)" else str(p_buy_date)

                    # 1. จัดการข้อมูล Portfolio (ใช้ .get ป้องกัน KeyError 100%)
                    found_idx = next((i for i, item in enumerate(st.session_state.my_portfolio) if item.get('หุ้น', item.get('Ticker', '')) == ticker_upper), -1)

                    if "ซื้อ" in p_type and p_status != "Closed (ขายแล้ว)":
                        log_cash_transaction(date=transaction_date_str, trans_type="ซื้อหุ้น " + ticker_upper, amount=-(total_val + p_comm), note=f"ซื้อ {p_qty} หุ้น ที่ราคา {p_price}")
                        st.session_state.cash_balance -= (total_val + p_comm)

                        if found_idx != -1:
                            old = st.session_state.my_portfolio[found_idx]
                            old_shares = float(old.get('shares', old.get('จำนวน', 0)))
                            old_avg_price = float(old.get('avg_price', old.get('ต้นทุนเฉลี่ย', 0)))

                            new_shares = old_shares + p_qty
                            # คำนวณต้นทุนเฉลี่ยใหม่ (Average Cost) อย่างถูกต้องแม่นยำ
                            new_cost = ((old_shares * old_avg_price) + total_val) / new_shares if new_shares > 0 else p_price

                            st.session_state.my_portfolio[found_idx] = {
                                'หุ้น': ticker_upper, 
                                'shares': new_shares, 
                                'avg_price': new_cost, 
                                'Sector': p_sector
                            }
                        else:
                            st.session_state.my_portfolio.append({
                                'หุ้น': ticker_upper, 
                                'shares': p_qty, 
                                'avg_price': p_price, 
                                'Sector': p_sector
                            })

                    else: # กรณีขาย (รองรับทั้งขายหมดและทยอยขาย)
                        log_cash_transaction(date=transaction_date_str, trans_type="ขายหุ้น " + ticker_upper, amount=(total_val - p_comm), note=f"ขาย {p_qty} หุ้น ที่ราคา {p_price}")
                        st.session_state.cash_balance += (total_val - p_comm)

                        if found_idx != -1:
                            old = st.session_state.my_portfolio[found_idx]
                            old_shares = float(old.get('shares', old.get('จำนวน', 0)))

                            new_shares = old_shares - p_qty

                            if new_shares > 0:
                                # อัปเดตจำนวนหุ้นที่เหลือ (ต้นทุนเฉลี่ยตัวเดิมไม่ต้องเปลี่ยน)
                                st.session_state.my_portfolio[found_idx]['shares'] = new_shares
                            else:
                                # ถ้าขายหมดพอร์ต ลบรายการออก
                                st.session_state.my_portfolio.pop(found_idx)

                    # 2. เพิ่มข้อมูลเข้า Journal (รวม Sector)
                    if "journal_data" not in st.session_state:
                        st.session_state.journal_data = []

                    new_entry = {
                        "วันที่": transaction_date_str, 
                        "วันที่ซื้อ": str(p_buy_date),
                        "วันที่ขาย": str(p_sell_date) if p_status == "Closed (ขายแล้ว)" else "",
                        "หุ้น": ticker_upper,
                        "Sector": p_sector,
                        "สถานะ": p_status,
                        "ประเภท": p_type,
                        "กำไร/ขาดทุน (บาท)": final_result,
                        "ต้นทุน (บาท)": total_val,
                        "ราคาหุ้นที่ซื้อ (บาท/หุ้น)": p_price,
                        "จำนวนหุ้นที่ซื้อ": p_qty,
                        "เหตุผล": p_reason
                    }
                    st.session_state.journal_data.append(new_entry)

                    # 3. บันทึกข้อมูลลง Google Sheets
                    save_portfolio()
                    save_journal()
                    save_cash_balance(st.session_state.cash_balance)
                    save_portfolio_snapshot()

                    st.success(f"บันทึก {ticker_upper} สำเร็จ! (กำไร/ขาดทุน: {final_result:,.2f} ฿)")
                    st.rerun()

        # 3. ตารางแสดงพอร์ต (เชื่อมต่อ Google Sheets)
        st.divider()
        st.subheader("📊 สรุปพอร์ตการลงทุน")

        # 1. ตรวจสอบและโหลดข้อมูลพอร์ตจาก Google Sheets (ชีต PortfolioData) ถ้ายังไม่มีใน session_state
        if "my_portfolio" not in st.session_state or not st.session_state["my_portfolio"]:
            try:
                client = get_gsheet_client()
                sheet_portfolio = get_cached_spreadsheet(client, 'MyStockData').worksheet('PortfolioData')
                raw_portfolio_data = sheet_portfolio.get_all_records()

                if raw_portfolio_data:
                    # แปลงชื่อคอลัมน์ให้สะอาด ป้องกันปัญหาช่องว่าง
                    cleaned_portfolio = []
                    for row in raw_portfolio_data:
                        cleaned_row = {str(k).strip(): v for k, v in row.items()}
                        cleaned_portfolio.append(cleaned_row)
                    st.session_state["my_portfolio"] = cleaned_portfolio
            except Exception as e:
                st.error(f"❌ ไม่สามารถดึงข้อมูลพอร์ตจาก Google Sheets (PortfolioData) ได้: {e}")

        # 2. ตรวจสอบว่ามีข้อมูลในพอร์ตหรือไม่
        if "my_portfolio" in st.session_state and st.session_state["my_portfolio"]:
            portfolio_list = []
            total_invest = 0
            total_value = 0

            # ฟังก์ชันกำหนดสีสำหรับตารางพอร์ต
            def color_portfolio(val):
                if isinstance(val, (int, float)):
                    color = '#26A69A' if val > 0 else '#EF5350' if val < 0 else 'black'
                    return f'color: {color}'
                return None

            for row in st.session_state["my_portfolio"]:
                # รองรับชื่อคอลัมน์ได้ทั้งภาษาไทยและอังกฤษ (กันเหนียว)
                ticker = str(row.get('หุ้น', row.get('Ticker', ''))).strip()

                try:
                    shares = float(str(row.get('จำนวน', row.get('shares', 0))).replace(',', ''))
                except:
                    shares = 0.0

                try:
                    avg_price = float(str(row.get('ต้นทุนเฉลี่ย', row.get('avg_price', 0.0))).replace(',', ''))
                except:
                    avg_price = 0.0

                sector_val = row.get('Sector', 'General / Unspecified')

                if ticker:
                    try:
                        # ดึงราคาตลาดล่าสุดผ่าน yfinance
                        m_price = yf.Ticker(f"{ticker}.BK").history(period="1d")['Close'].iloc[-1]
                    except:
                        m_price = avg_price

                    cost_value = shares * avg_price
                    market_value = shares * m_price
                    profit = market_value - cost_value
                    profit_pct = (profit / cost_value * 100) if cost_value > 0 else 0

                    portfolio_list.append({
                        "หุ้น": ticker,
                        "Sector": sector_val,
                        "จำนวน": shares,
                        "ต้นทุนเฉลี่ย": avg_price,
                        "มูลค่าต้นทุน": cost_value,
                        "ราคาตลาด": m_price,
                        "มูลค่าตลาด": market_value,
                        "กำไร/ขาดทุน": profit,
                        "% กำไร/ขาดทุน": profit_pct
                    })
                    total_invest += cost_value
                    total_value += market_value

            if portfolio_list:
                # ดึงยอดเงินสดคงเหลือจาก session_state (ถ้ามี ถ้าไม่มีให้เป็น 0)
                cash_bal = st.session_state.get('cash_balance', 0.0)

                # สรุปยอดรวม Metrics ด้านบน
                col_s1, col_s2, col_s3, col_s4 = st.columns(4)
                col_s1.metric("เงินสดคงเหลือ", f"{cash_bal:,.0f} ฿")
                col_s2.metric("เงินลงทุนรวม", f"{total_invest:,.0f} ฿")
                col_s3.metric("มูลค่าปัจจุบัน", f"{total_value:,.0f} ฿")
                # 🔧 แก้บั๊ก: ส่งค่ามูลค่าพอร์ตหุ้นผ่าน session_state (เหมือนที่ TFEX ทำอยู่แล้ว)
                # เพราะหลังแยกไฟล์ แท็บ "ภาพรวม Net Worth" อยู่คนละไฟล์แล้ว มองไม่เห็นตัวแปร total_value โดยตรง
                st.session_state['stock_net_worth'] = total_value
                diff = total_value - total_invest
                col_s4.metric("กำไร/ขาดทุนรวม", f"{diff:,.0f} ฿", delta=f"{((diff)/total_invest)*100:.2f}%" if total_invest > 0 else "0%")

                # แสดงตารางพอร์ตหลัก
                df_p = pd.DataFrame(portfolio_list)
                df_display_p = df_p.drop(columns=['Sector']) if 'Sector' in df_p.columns else df_p

                st.dataframe(
                    df_display_p.style.format({
                        "จำนวน": "{:,.0f}", "ต้นทุนเฉลี่ย": "{:.2f}", "มูลค่าต้นทุน": "{:,.0f}",
                        "ราคาตลาด": "{:.2f}", "มูลค่าตลาด": "{:,.0f}", "กำไร/ขาดทุน": "{:,.0f}",
                        "% กำไร/ขาดทุน": "{:.2f}%"
                    })
                    .map(color_portfolio, subset=["กำไร/ขาดทุน", "% กำไร/ขาดทุน"])
                    .set_properties(**{'text-align': 'right'})
                    .set_table_styles([{'selector': 'th', 'props': [('text-align', 'right')]}])
                    , use_container_width=True
                )

                if st.button("✏️ แก้ไขข้อมูลหุ้นในพอร์ต"):
                    st.session_state.edit_mode = True
            else:
                st.info("ยังไม่มีข้อมูลหุ้นในพอร์ตการลงทุนครับ")
        else:
            st.info("ยังไม่มีข้อมูลในชีต PortfolioData กรุณาตรวจสอบ Google Sheets อีกครั้งครับ")

        # --- ส่วนแสดงกราฟสรุปพอร์ต ---
        st.divider()

        # แบ่งคอลัมน์สัดส่วน 25% : 25% : 50%
        col_p1, col_p2, col_p3 = st.columns([1, 1, 2])

        # 1. Pie Chart: มูลค่าตลาด (25%)
        with col_p1:
            st.subheader("🥧 มูลค่าตลาด")
            fig_pie1 = px.pie(df_p, values='มูลค่าตลาด', names='หุ้น', hole=0.4)
            fig_pie1.update_traces(
                textposition='outside', 
                textinfo='label+percent',
                textfont=dict(size=9),
                automargin=True
            )
            fig_pie1.update_layout(height=300, margin=dict(l=0, r=0, t=20, b=20), showlegend=False)
            st.plotly_chart(fig_pie1, use_container_width=True)
            st.markdown("<p style='text-align: center; font-size: 13px;'>สัดส่วนมูลค่าตลาดปัจจุบัน</p>", unsafe_allow_html=True)

        # 2. Pie Chart: มูลค่าต้นทุน (25%)
        with col_p2:
            st.subheader("🥧 มูลค่าต้นทุน")
            fig_pie2 = px.pie(df_p, values='มูลค่าต้นทุน', names='หุ้น', hole=0.4)
            fig_pie2.update_traces(
                textposition='outside', 
                textinfo='label+percent',
                textfont=dict(size=9),
                automargin=True
            )
            fig_pie2.update_layout(height=300, margin=dict(l=0, r=0, t=20, b=20), showlegend=False)
            st.plotly_chart(fig_pie2, use_container_width=True)
            st.markdown("<p style='text-align: center; font-size: 13px;'>สัดส่วนเงินลงทุนต้นทุน</p>", unsafe_allow_html=True)

        # 3. Bar Chart: กำไร/ขาดทุน (50%)
        with col_p3:
            st.subheader("📈 กำไร/ขาดทุนรายตัว")
            text_labels = [f"{row['กำไร/ขาดทุน']:,.0f} / {row['% กำไร/ขาดทุน']:.1f}%" for _, row in df_p.iterrows()]
            bar_colors = ['#26A69A' if val >= 0 else '#EF5350' for val in df_p['กำไร/ขาดทุน']]

            fig_bar = go.Figure(data=[go.Bar(
                x=df_p['หุ้น'], y=df_p['กำไร/ขาดทุน'],
                marker_color=bar_colors, text=text_labels, textposition='auto'
            )])
            fig_bar.update_traces(textfont_size=10)
            fig_bar.update_layout(height=300, margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig_bar, use_container_width=True)
            st.markdown("<p style='text-align: center; font-size: 13px;'>กำไร/ขาดทุน เป็น THB และ %</p>", unsafe_allow_html=True)

        # --- ส่วนแดชบอร์ดวิเคราะห์ Sector Allocation ใน Tab Portfolio ---
        # --- ส่วนแดชบอร์ดวิเคราะห์ Sector Allocation ใน Tab Portfolio ---
        st.divider()
        st.subheader("🥧 การกระจายตัวของพอร์ตตามกลุ่มอุตสาหกรรม (Sector Allocation)")

        if not df_p.empty:
            # จัดกลุ่มรวมตาม Sector ของหุ้นในพอร์ตปัจจุบัน (ใช้ as_index=False และ reset_index เพื่อความชัวร์)
            df_port_sector = df_p.groupby('Sector', as_index=False).agg({
                'มูลค่าตลาด': 'sum',
                'มูลค่าต้นทุน': 'sum',
                'หุ้น': lambda x: ', '.join(x.unique())
            }).reset_index(drop=True)

            # 1. คำนวณสัดส่วน % ตาม "มูลค่าตลาด"
            total_market_val = df_port_sector['มูลค่าตลาด'].sum()
            if total_market_val > 0:
                df_port_sector['Market_Weight_Pct'] = (df_port_sector['มูลค่าตลาด'] / total_market_val) * 100
            else:
                df_port_sector['Market_Weight_Pct'] = 0.0

            # 2. คำนวณสัดส่วน % ตาม "เงินลงทุน (ต้นทุน)"
            total_cost_val = df_port_sector['มูลค่าต้นทุน'].sum()
            if total_cost_val > 0:
                df_port_sector['Cost_Weight_Pct'] = (df_port_sector['มูลค่าต้นทุน'] / total_cost_val) * 100
            else:
                df_port_sector['Cost_Weight_Pct'] = 0.0

            # เรียงลำดับตามเงินลงทุนต้นทุนจากมากไปน้อย
            df_port_sector = df_port_sector.sort_values(by='มูลค่าต้นทุน', ascending=False).reset_index(drop=True)

            # 📊 แบ่ง 2 คอลัมน์สำหรับกราฟโดนัท (เงินลงทุนต้นทุน VS มูลค่าตลาด)
            col_sec1, col_sec2 = st.columns(2)

            with col_sec1:
                st.markdown("###### 🥧 สัดส่วนตามเงินลงทุน (Cost Weight)")
                fig_donut_cost = px.pie(
                    df_port_sector,
                    names='Sector',
                    values='มูลค่าต้นทุน',
                    hole=0.4,
                    color_discrete_sequence=px.colors.qualitative.Pastel
                )
                fig_donut_cost.update_traces(
                    textinfo='percent+label',
                    hovertemplate='<b>Sector:</b> %{label}<br><b>เงินลงทุนต้นทุน:</b> %{value:,.2f} ฿<br><b>สัดส่วนต้นทุน:</b> %{percent}'
                )
                fig_donut_cost.update_layout(
                    height=380,
                    margin=dict(l=10, r=10, t=40, b=40),
                    showlegend=False
                )
                if 'fig_donut_cost' in locals() and fig_donut_cost is not None:
                    st.plotly_chart(fig_donut_cost, use_container_width=True, key="donut_cost_chart")
                else:
                    st.warning("ไม่มีข้อมูลสำหรับกราฟ Cost Weight")

            with col_sec2:
                st.markdown("###### 🥧 สัดส่วนตามมูลค่าตลาด (Market Weight)")
                fig_donut_market = px.pie(
                    df_port_sector,
                    names='Sector',
                    values='มูลค่าตลาด',
                    hole=0.4,
                    color_discrete_sequence=px.colors.qualitative.Set3
                )
                fig_donut_market.update_traces(
                    textinfo='percent+label',
                    hovertemplate='<b>Sector:</b> %{label}<br><b>มูลค่าตลาด:</b> %{value:,.2f} ฿<br><b>สัดส่วนตลาด:</b> %{percent}'
                )
                fig_donut_market.update_layout(
                    height=380,
                    margin=dict(l=10, r=10, t=40, b=40),
                    showlegend=True
                )
                if 'fig_donut_market' in locals() and fig_donut_market is not None:
                    st.plotly_chart(fig_donut_market, use_container_width=True, key="donut_market_chart")
                else:
                    st.warning("ไม่มีข้อมูลสำหรับกราฟ Market Weight")

            # 📋 ตารางสรุปน้ำหนักการลงทุนแต่ละกลุ่ม
            st.markdown("##### 📋 ตารางสรุปน้ำหนักการลงทุนแต่ละกลุ่มในพอร์ต")
            display_port_sector = df_port_sector[[
                'Sector', 'มูลค่าต้นทุน', 'Cost_Weight_Pct', 'มูลค่าตลาด', 'Market_Weight_Pct', 'หุ้น'
            ]].copy()

            display_port_sector.columns = [
                'กลุ่มอุตสาหกรรม (Sector)', 
                'เงินลงทุนต้นทุน (บาท)', 
                'สัดส่วนต้นทุน (%)', 
                'มูลค่าตลาดรวม (บาท)', 
                'สัดส่วนตลาด (%)', 
                'รายชื่อหุ้นในกลุ่ม'
            ]

            st.dataframe(
                display_port_sector.style.format({
                    'เงินลงทุนต้นทุน (บาท)': '{:,.2f}',
                    'สัดส่วนต้นทุน (%)': '{:.2f} %',
                    'มูลค่าตลาดรวม (บาท)': '{:,.2f}',
                    'สัดส่วนตลาด (%)': '{:.2f} %'
                }).set_properties(**{'text-align': 'right'}),
                use_container_width=True,
                hide_index=True  # เพิ่มคำสั่งนี้เพื่อซ่อนคอลัมน์ Index ที่เกินมาครับ
            )

        else:
            st.info("ยังไม่มีข้อมูลหุ้นในพอร์ตปัจจุบันครับ")

    #########################
    with tab_dividend:
        DATA_FILE = "dividend_database.csv"

        # โหลดข้อมูลจากไฟล์ CSV เข้า session_state ทุกครั้งที่เปิดหรือรีเฟรชแอป
        if "dividend_data" not in st.session_state:
            if os.path.exists(DATA_FILE):
                try:
                    df_saved = pd.read_csv(DATA_FILE)
                    if not df_saved.empty:
                        st.session_state.dividend_data = df_saved.to_dict('records')
                    else:
                        st.session_state.dividend_data = []
                except Exception:
                    st.session_state.dividend_data = []
            else:
                st.session_state.dividend_data = []

        st.markdown("#### 💰 บันทึกและจัดการข้อมูลเงินปันผล (Dividend Tracker)")

        # --- ส่วนที่ 1: อัปโหลดไฟล์ TSD Portal หรือ CSV ---
        with st.expander("📤 อัปโหลดประวัติเงินปันผลจากรายงาน TSD หรือไฟล์ Excel/CSV"):
            uploaded_div_file = st.file_uploader("เลือกไฟล์รายงานปันผล", type=['csv', 'xlsx', 'xls'], key="div_file")
            if uploaded_div_file:
                if st.button("ยืนยันการนำเข้าไฟล์ปันผล"):
                    try:
                        if uploaded_div_file.name.endswith('.csv'):
                            df_upload = pd.read_csv(uploaded_div_file)
                        else:
                            df_upload = pd.read_excel(uploaded_div_file)

                        processed_rows = []

                        if 'ชื่อย่อหลักทรัพย์' in df_upload.columns and 'วันที่จ่าย' in df_upload.columns:
                            for idx, row in df_upload.iterrows():
                                ticker = str(row.get('ชื่อย่อหลักทรัพย์', '')).strip().upper()
                                if not ticker or ticker == 'NAN':
                                    continue
                                if not ticker.endswith('.BK'):
                                    ticker = f"{ticker}.BK"

                                pay_date = str(row.get('วันที่จ่าย', ''))[:10]
                                total_div_before_tax = 0.0
                                total_tax = 0.0

                                for col in df_upload.columns:
                                    col_str = str(col)
                                    val = row.get(col, 0)
                                    try:
                                        val_num = float(val) if pd.notna(val) else 0.0
                                    except:
                                        val_num = 0.0

                                    if 'จำนวนเงินปันผล' in col_str or 'ดอกเบี้ยหุ้นกู้' in col_str or 'เงินเทียบเท่าเงินปันผล' in col_str:
                                        total_div_before_tax += val_num
                                    elif 'ภาษีของเงินปันผล' in col_str or 'ภาษีของดอกเบี้ย' in col_str:
                                        total_tax += val_num

                                net_receive = total_div_before_tax - total_tax

                                cost_val = 0.0
                                for cost_col in ['ต้นทุน', 'Cost', 'ทุนรวม', 'มูลค่าลงทุน']:
                                    if cost_col in df_upload.columns:
                                        try:
                                            cost_val = float(row.get(cost_col, 0))
                                        except:
                                            pass

                                processed_rows.append({
                                    "วันที่ได้รับ": pay_date,
                                    "Ticker": ticker,
                                    "จำนวนหุ้น": 0.0,
                                    "ปันผลต่อหุ้น": 0.0,
                                    "ยอดรวมก่อนภาษี": total_div_before_tax,
                                    "ภาษีหัก ณ ที่จ่าย": total_tax,
                                    "ยอดรับสุทธิ": net_receive,
                                    "ต้นทุนหุ้น": cost_val,
                                    "หมายเหตุ": "นำเข้าจาก TSD Portal"
                                })
                        else:
                            if 'ต้นทุนหุ้น' not in df_upload.columns:
                                df_upload['ต้นทุนหุ้น'] = 0.0
                            processed_rows = df_upload.to_dict('records')

                        existing_df = pd.DataFrame(st.session_state.dividend_data)
                        new_df = pd.DataFrame(processed_rows)

                        if not existing_df.empty:
                            combined_df = pd.concat([existing_df, new_df]).drop_duplicates(
                                subset=['วันที่ได้รับ', 'Ticker', 'ยอดรับสุทธิ'], 
                                keep='first'
                            )
                            added_count = len(combined_df) - len(existing_df)
                        else:
                            combined_df = new_df.drop_duplicates(subset=['วันที่ได้รับ', 'Ticker', 'ยอดรับสุทธิ'], keep='first')
                            added_count = len(combined_df)

                        st.session_state.dividend_data = combined_df.to_dict('records')

                        # 🟢 ส่ง combined_df เข้าไปในฟังก์ชันบันทึกเพื่อป้องกัน Error missing positional argument
                        save_dividend_data(combined_df)

                        if added_count > 0:
                            st.success(f"✅ นำเข้าข้อมูลสำเร็จ! (เพิ่มรายการใหม่ {added_count} รายการ, ข้ามรายการซ้ำ)")
                        else:
                            st.info("ℹ️ ข้อมูลในไฟล์นี้มีอยู่แล้วในระบบทั้งหมด จึงไม่มีการเพิ่มรายการซ้ำ")
                        st.rerun()

                    except Exception as e:
                        st.error(f"❌ เกิดข้อผิดพลาดในการอ่านไฟล์: {e}")

        # --- ส่วนที่ 2: ฟอร์มกรอกข้อมูลแบบ Manual ---
        with st.expander("➕ เพิ่มรายการรับเงินปันผล (Manual Input)", expanded=True):
            with st.form("dividend_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                with col1:
                    div_date = st.date_input("วันที่ได้รับเงินปันผล", value=date.today())
                    ticker = st.text_input("ชื่อหุ้น (Ticker)").upper()
                    shares = st.number_input("จำนวนหุ้นที่ได้รับสิทธิ์", min_value=0.0, step=1.0)
                    total_cost = st.number_input("ต้นทุนหุ้นรวม (บาท)", min_value=0.0, step=100.0, format="%.2f", help="มูลค่าเงินลงทุนหรือต้นทุนรวมของหุ้นตัวนี้")

                with col2:
                    dps = st.number_input("เงินปันผลต่อหุ้น (บาท/หุ้น)", min_value=0.0000, format="%.4f", step=0.01)
                    auto_gross = shares * dps
                    gross_div = st.number_input("เงินปันผลรวมก่อนภาษี (บาท)", value=auto_gross, format="%.2f", step=1.0)

                    tax_wht = gross_div * 0.10
                    net_div = gross_div - tax_wht

                    st.caption(f"💡 คำนวณอัตโนมัติ: ภาษีหัก ณ ที่จ่าย 10% = {tax_wht:,.2f} ฿ | รับสุทธิ = {net_div:,.2f} ฿")

                notes = st.text_input("หมายเหตุ (เช่น ปันผล Q2/2026)")
                submitted = st.form_submit_button("💾 บันทึกเงินปันผล")

                if submitted:
                    if ticker:
                        formatted_ticker = ticker if ticker.endswith('.BK') else f"{ticker}.BK"
                        new_entry = {
                            "วันที่ได้รับ": str(div_date),
                            "Ticker": formatted_ticker,
                            "จำนวนหุ้น": shares,
                            "ปันผลต่อหุ้น": dps,
                            "ยอดรวมก่อนภาษี": gross_div,
                            "ภาษีหัก ณ ที่จ่าย": tax_wht,
                            "ยอดรับสุทธิ": net_div,
                            "ต้นทุนหุ้น": total_cost,
                            "หมายเหตุ": notes
                        }
                        st.session_state.dividend_data.append(new_entry)

                        # แปลง session_state ทั้งหมดเป็น DataFrame แล้วส่งให้ save_dividend_data() บันทึก
                        final_df = pd.DataFrame(st.session_state.dividend_data)
                        save_dividend_data(final_df)

                        st.success(f"✅ บันทึกเงินปันผลของหุ้น {formatted_ticker} เรียบร้อยแล้วครับ!")
                        st.rerun()
                    else:
                        st.warning("⚠️ กรุณากรอกชื่อหุ้น (Ticker)")

        # --- ส่วนที่ 3: สรุปภาพรวมและประวัติเงินปันผลรับ ---
        st.markdown("---")
        st.markdown("##### 📊 สรุปภาพรวมและประวัติเงินปันผลรับ")

        # 🛠️ [เพิ่มส่วนนี้] เช็คและดึงข้อมูลจาก Google Sheets เสมอ หากใน session_state ยังไม่มีข้อมูล
        if 'dividend_data' not in st.session_state or not st.session_state.dividend_data:
            try:
                client = get_gsheet_client()
                # ดึงข้อมูลจาก worksheet ชื่อ 'Dividend' (ปรับชื่อให้ตรงกับชีตจริงของคุณ เช่น 'Dividend' หรือ 'Dividend_History')
                div_records = get_cached_spreadsheet(client, 'MyStockData').worksheet('Dividend').get_all_records()
                st.session_state.dividend_data = div_records
            except Exception as e:
                # ถ้าดึงไม่สำเร็จหรือยังไม่มีชีต ให้ปล่อยเป็น list เปล่า
                st.session_state.dividend_data = []

        # หลังจากดึงข้อมูลแล้ว โค้ดส่วนเดิมของคุณจะทำงานต่อได้อย่างปกติครับ
        if st.session_state.dividend_data:
            df_div = pd.DataFrame(st.session_state.dividend_data)

            total_received = df_div['ยอดรับสุทธิ'].sum() if 'ยอดรับสุทธิ' in df_div.columns else 0
            total_tax = df_div['ภาษีหัก ณ ที่จ่าย'].sum() if 'ภาษีหัก ณ ที่จ่าย' in df_div.columns else 0

            m1, m2 = st.columns(2)
            m1.metric("💰 เงินปันผลรับสุทธิรวมทั้งสิ้น", f"{total_received:,.2f} ฿")
            m2.metric("🏛️ ภาษีหัก ณ ที่จ่ายรวม", f"{total_tax:,.2f} ฿")

            st.markdown("<br>", unsafe_allow_html=True)

            with st.expander("📂 ดูตารางประวัติและแก้ไขข้อมูลปันผล", expanded=False):
                edited_div_df = st.data_editor(df_div, use_container_width=True, key="div_editor")

                if st.button("💾 อัปเดตการแก้ไขตารางปันผล", key="update_div_btn"):
                    st.session_state.dividend_data = edited_div_df.to_dict('records')
                    save_dividend_data()
                    st.success("✅ อัปเดตข้อมูลสำเร็จ!")
                    st.rerun()

                csv_div = df_div.to_csv(index=False).encode('utf-8-sig')
                st.download_button("📥 Export ประวัติปันผลเป็น CSV", data=csv_div, file_name="dividend_history.csv", mime="text/csv", key="export_div_btn")

            # --- ส่วนที่ 4: กราฟวิเคราะห์และสรุปยอดเงินปันผลรับ ---
            st.markdown("---")
            st.markdown("##### 📊 วิเคราะห์ข้อมูลเงินปันผล (Dividend Analytics)")

            if 'วันที่ได้รับ' in df_div.columns:
                df_div['วันที่ได้รับ'] = pd.to_datetime(df_div['วันที่ได้รับ'], errors='coerce')
                df_div['Year'] = df_div['วันที่ได้รับ'].dt.year.fillna(0).astype(int)

            col_f1, col_f2 = st.columns([2, 2])
            with col_f1:
                available_years = sorted([y for y in df_div['Year'].unique() if y > 0], reverse=True)
                year_options = ["All Time (ทั้งหมด)"] + [str(y) for y in available_years]
                selected_period = st.selectbox("📅 กรองช่วงเวลา (ปี):", year_options, key="div_year_filter")

            df_filtered_div = df_div.copy()
            if selected_period != "All Time (ทั้งหมด)":
                df_filtered_div = df_filtered_div[df_filtered_div['Year'] == int(selected_period)]

            if not df_filtered_div.empty:
                total_received_filtered = df_filtered_div['ยอดรับสุทธิ'].sum() if 'ยอดรับสุทธิ' in df_filtered_div.columns else 0
                total_tax_filtered = df_filtered_div['ภาษีหัก ณ ที่จ่าย'].sum() if 'ภาษีหัก ณ ที่จ่าย' in df_filtered_div.columns else 0

                mf1, mf2 = st.columns(2)
                mf1.metric(f"💰 เงินปันผลรับสุทธิ ({selected_period})", f"{total_received_filtered:,.2f} ฿")
                mf2.metric(f"🏛️ ภาษีหัก ณ ที่จ่ายรวม ({selected_period})", f"{total_tax_filtered:,.2f} ฿")

                st.markdown("<br>", unsafe_allow_html=True)

                # --- ส่วนที่ 5: วิเคราะห์ Dividend Yield on Cost (%) ---
                st.markdown("---")
                st.markdown(f"##### 🎯 วิเคราะห์ผลตอบแทนจากเงินปันผลเทียบกับต้นทุนหุ้น (Dividend Yield on Cost) - [{selected_period}]")

                if 'Ticker' in df_filtered_div.columns and 'ยอดรับสุทธิ' in df_filtered_div.columns and 'ต้นทุนหุ้น' in df_filtered_div.columns and 'จำนวนหุ้น' in df_filtered_div.columns:
                    df_calc = df_filtered_div.copy()

                    if 'วันที่ได้รับ' in df_calc.columns:
                        df_calc['วันที่ได้รับ_dt'] = pd.to_datetime(df_calc['วันที่ได้รับ'], errors='coerce')
                        df_calc = df_calc.sort_values(by='วันที่ได้รับ_dt', ascending=True)

                    df_div_sum = df_calc.groupby('Ticker')['ยอดรับสุทธิ'].sum().reset_index()

                    df_latest = df_calc.groupby('Ticker').agg({
                        'จำนวนหุ้น': 'last',
                        'ต้นทุนหุ้น': 'last'
                    }).reset_index()

                    # 1. รวมข้อมูลยอดรับสุทธิและต้นทุนหุ้นรายตัวหุ้นเข้าด้วยกัน
                    df_yield_analysis = pd.merge(df_div_sum, df_latest, on='Ticker', how='inner')

                    # 2. แปลงข้อมูลตัวเลขด้วย pd.to_numeric อย่างปลอดภัย
                    df_yield_analysis['ยอดรับสุทธิ'] = pd.to_numeric(df_yield_analysis['ยอดรับสุทธิ'], errors='coerce').fillna(0)
                    df_yield_analysis['ต้นทุนหุ้น'] = pd.to_numeric(df_yield_analysis['ต้นทุนหุ้น'], errors='coerce').fillna(0)

                    # 3. คำนวณ Yield_on_Cost โดยใช้คอลัมน์ 'ต้นทุนหุ้น'
                    df_yield_analysis['Yield_on_Cost'] = df_yield_analysis.apply(
                        lambda row: (row['ยอดรับสุทธิ'] / row['ต้นทุนหุ้น'] * 100) if row['ต้นทุนหุ้น'] > 0 else 0.0,
                        axis=1
                    )

                    valid_cost_df = df_yield_analysis[(df_yield_analysis['ต้นทุนหุ้น'] > 0) & (df_yield_analysis['Yield_on_Cost'] <= 1000)]

                    if not valid_cost_df.empty:
                        total_portfolio_cost = valid_cost_df['ต้นทุนหุ้น'].sum()
                        total_portfolio_dividend = valid_cost_df['ยอดรับสุทธิ'].sum()
                        avg_yield_on_cost = (total_portfolio_dividend / total_portfolio_cost * 100) if total_portfolio_cost > 0 else 0.0

                        kpi_col1, kpi_col2, kpi_col3 = st.columns(3)
                        kpi_col1.metric(f"📊 Avg. Yield on Cost ({selected_period})", f"{avg_yield_on_cost:.2f}%")
                        kpi_col2.metric(f"💰 ปันผลรับรวม ({selected_period})", f"{total_portfolio_dividend:,.2f} ฿")
                        kpi_col3.metric("🏛️ ต้นทุนพอร์ตหุ้นรวม", f"{total_portfolio_cost:,.2f} ฿")

                        st.markdown("<br>", unsafe_allow_html=True)

                        df_yield_sorted = valid_cost_df.sort_values(by='Yield_on_Cost', ascending=True)
                        df_yield_sorted['Text_Label'] = df_yield_sorted['Yield_on_Cost'].apply(lambda x: f"{x:.2f}%")

                        fig_yield_bar = px.bar(
                            df_yield_sorted,
                            x='Yield_on_Cost',
                            y='Ticker',
                            orientation='h',
                            text='Text_Label',
                            color='Yield_on_Cost',
                            color_continuous_scale='Tealgrn'
                        )

                        fig_yield_bar.update_traces(textposition='outside')
                        fig_yield_bar.update_layout(
                            xaxis_title=f"Dividend Yield on Cost (%) [{selected_period}]",
                            yaxis_title="ชื่อหุ้น (Ticker)",
                            height=max(320, len(df_yield_sorted) * 40),
                            margin=dict(l=10, r=20, t=20, b=20),
                            coloraxis_showscale=False
                        )
                        st.plotly_chart(fig_yield_bar, use_container_width=True)

                        st.markdown(f"##### 📋 ตารางสรุป Yield on Cost ({selected_period})")
                        df_table_display = df_yield_sorted[['Ticker', 'ยอดรับสุทธิ', 'ต้นทุนหุ้น', 'Yield_on_Cost']].copy()

                        div_col_name = f"เงินปันผลรับรวม ({selected_period}) (บาท)"
                        df_table_display.columns = ['ชื่อหุ้น (Ticker)', div_col_name, 'ต้นทุนรวมทั้งหมด (บาท)', 'Dividend Yield on Cost (%)']

                        df_table_display[div_col_name] = df_table_display[div_col_name].apply(lambda x: f"{x:,.2f}")
                        df_table_display['ต้นทุนรวมทั้งหมด (บาท)'] = df_table_display['ต้นทุนรวมทั้งหมด (บาท)'].apply(lambda x: f"{x:,.2f}")
                        df_table_display['Dividend Yield on Cost (%)'] = df_table_display['Dividend Yield on Cost (%)'].apply(lambda x: f"{x:.2f}%")

                        st.dataframe(df_table_display.reset_index(drop=True), use_container_width=True)
                    else:
                        st.info(f"💡 ไม่มีข้อมูลปันผลหรือต้นทุนหุ้นในช่วงเวลา {selected_period}")
                else:
                    st.info("ยังไม่มีข้อมูลเพียงพอสำหรับวิเคราะห์ Yield on Cost")

            # --- ส่วนที่ 6: ปุ่มล้างข้อมูลทั้งหมด (Danger Zone) ---
            st.markdown("---")
            with st.expander("⚠️ พื้นที่จัดการข้อมูล (Danger Zone)", expanded=False):
                st.warning("การล้างข้อมูลจะทำการลบประวัติเงินปันผลทั้งหมดออกจากระบบอย่างถาวร กรุณาตรวจสอบให้แน่ใจก่อนดำเนินการ")

                if "confirm_clear_div" not in st.session_state:
                    st.session_state.confirm_clear_div = False

                if not st.session_state.confirm_clear_div:
                    if st.button("🗑️ ล้างข้อมูลเงินปันผลทั้งหมด", type="secondary", key="btn_clear_dividend_main"):
                        st.session_state.confirm_clear_div = True
                        st.rerun()
                else:
                    st.error("❗ คุณแน่ใจจริงๆ หรือไม่ที่จะลบข้อมูลทั้งหมด? การกระทำนี้ไม่สามารถย้อนกลับได้")
                    col_c1, col_c2, _ = st.columns([1, 1, 2])
                    with col_c1:
                        if st.button("✔️ ยืนยันการลบ", type="primary", key="btn_confirm_clear_div"):
                            st.session_state.dividend_data = []
                            save_dividend_data()
                            st.session_state.confirm_clear_div = False
                            st.success("✅ ล้างข้อมูลเงินปันผลทั้งหมดเรียบร้อยแล้วครับ")
                            st.rerun()
                    with col_c2:
                        if st.button("❌ ยกเลิก", key="btn_cancel_clear_div"):
                            st.session_state.confirm_clear_div = False
                            st.rerun()

            # ตรวจสอบว่ามีข้อมูลในระบบหรือไม่ ถ้าไม่มีให้แสดงข้อความแนะนำ
            if df_div.empty:
                st.info("💡 ยังไม่มีข้อมูลเงินปันผลในระบบ สามารถเพิ่มข้อมูลผ่านฟอร์มด้านบนหรืออัปโหลดไฟล์รายงาน TSD ได้เลยครับ")
            else:
                # --- กราฟที่ 4: ยอดปันผลรับสุทธิสะสมรายปี (Yearly Bar Chart) ---
                st.markdown("---")
                st.markdown("##### 📅 ยอดปันผลรับสุทธิสะสมรายปี (Yearly Dividend)")
                if 'Year' in df_div.columns and 'ยอดรับสุทธิ' in df_div.columns:
                    df_yearly_sum = df_div[df_div['Year'] > 0].groupby('Year')['ยอดรับสุทธิ'].sum().reset_index()
                    df_yearly_sum['Year'] = df_yearly_sum['Year'].astype(str)

                    fig_yearly = px.bar(
                        df_yearly_sum,
                        x='Year',
                        y='ยอดรับสุทธิ',
                        text=df_yearly_sum['ยอดรับสุทธิ'].apply(lambda x: f"{x:,.2f} ฿"),
                        color='ยอดรับสุทธิ',
                        color_continuous_scale='Blues'
                    )
                    fig_yearly.update_traces(textposition='outside')
                    fig_yearly.update_layout(
                        xaxis_title="ปี (Year)",
                        yaxis_title="ยอดปันผลรับสุทธิ (บาท)",
                        height=380,
                        margin=dict(l=10, r=10, t=20, b=20),
                        coloraxis_showscale=False
                    )
                    st.plotly_chart(fig_yearly, use_container_width=True)

                # --- กราฟที่ 3: Stacked Horizontal Bar Chart (ยอดปันผลแยกตามหุ้น ซ้อนสีตามปี) ---
                st.markdown("---")
                st.markdown("##### 📊 ยอดปันผลรับสุทธิรายหุ้น (เรียงจากยอดมากไปน้อย แบ่งตามปีที่ได้รับ)")

                if 'Ticker' in df_filtered_div.columns and 'Year' in df_filtered_div.columns and 'ยอดรับสุทธิ' in df_filtered_div.columns:
                    df_stacked = df_filtered_div[df_filtered_div['Year'] > 0].groupby(['Ticker', 'Year'])['ยอดรับสุทธิ'].sum().reset_index()

                    if not df_stacked.empty:
                        df_ticker_totals = df_stacked.groupby('Ticker')['ยอดรับสุทธิ'].sum().reset_index()
                        df_ticker_totals = df_ticker_totals.sort_values(by='ยอดรับสุทธิ', ascending=True)
                        sorted_tickers = df_ticker_totals['Ticker'].tolist()

                        df_stacked['Total_Stock_Sum'] = df_stacked['Ticker'].map(df_stacked.groupby('Ticker')['ยอดรับสุทธิ'].sum())
                        df_stacked['Percentage'] = (df_stacked['ยอดรับสุทธิ'] / df_stacked['Total_Stock_Sum']) * 100
                        df_stacked['Year_Str'] = df_stacked['Year'].astype(str)

                        df_stacked['Text_Label'] = df_stacked.apply(
                            lambda row: f"{row['ยอดรับสุทธิ']:,.0f} ฿ ({row['Percentage']:.1f}%)" if row['Percentage'] > 5 else "", 
                            axis=1
                        )

                        fig_stacked_bar = px.bar(
                            df_stacked,
                            x='ยอดรับสุทธิ',
                            y='Ticker',
                            color='Year_Str',
                            orientation='h',
                            text='Text_Label',
                            barmode='stack',
                            category_orders={'Ticker': sorted_tickers},
                            color_discrete_sequence=px.colors.qualitative.Bold
                        )

                        fig_stacked_bar.update_traces(
                            textposition='inside', 
                            insidetextanchor='middle'
                        )

                        fig_stacked_bar.update_layout(
                            xaxis_title="ยอดปันผลรับสุทธิรวม (บาท)",
                            yaxis_title="ชื่อหุ้น (Ticker)",
                            height=max(350, len(sorted_tickers) * 45),
                            margin=dict(l=10, r=20, t=20, b=20),
                            legend_title="ปีที่ได้รับ (Year)"
                        )
                        st.plotly_chart(fig_stacked_bar, use_container_width=True)
                    else:
                        st.info("ไม่มีข้อมูลเพียงพอสำหรับสร้างกราฟ Stacked Bar ในช่วงเวลานี้")
                else:
                    st.info(f"ไม่มีข้อมูลเงินปันผลในช่วงปีที่เลือก")

                # --- ส่วนที่ 5: กราฟแท่งซ้อน %Yield / Cost รายปี (ที่เคยขาดหายไป) ---
                st.markdown("---")
                st.markdown("##### 🚀 วิเคราะห์การเติบโต Dividend Yield on Cost รายปี (Stacked Bar Chart)")

                if 'dividend_data' in st.session_state and st.session_state.dividend_data:
                    df_div_local = pd.DataFrame(st.session_state.dividend_data)
                else:
                    df_div_local = pd.DataFrame()

                if not df_div_local.empty and 'Ticker' in df_div_local.columns and 'ยอดรับสุทธิ' in df_div_local.columns and 'ต้นทุนหุ้น' in df_div_local.columns and 'จำนวนหุ้น' in df_div_local.columns:
                    df_stack_calc = df_div_local.copy()

                    if 'วันที่ได้รับ' in df_stack_calc.columns:
                        df_stack_calc['วันที่ได้รับ_dt'] = pd.to_datetime(df_stack_calc['วันที่ได้รับ'], errors='coerce')
                        df_stack_calc['Year'] = df_stack_calc['วันที่ได้รับ_dt'].dt.year.fillna(0).astype(int)
                    else:
                        df_stack_calc['Year'] = 0

                    available_stack_years = sorted([y for y in df_stack_calc['Year'].unique() if y > 0], reverse=True)
                    stack_year_options = ["All Time (ทั้งหมด)"] + [str(y) for y in available_stack_years]

                    selected_stack_period = st.selectbox(
                        "📅 กรองช่วงเวลากราฟ Stacked Bar:", 
                        stack_year_options, 
                        key="stack_bar_year_filter"
                    )

                    if selected_stack_period != "All Time (ทั้งหมด)":
                        df_stack_filtered = df_stack_calc[df_stack_calc['Year'] == int(selected_stack_period)].copy()
                    else:
                        df_stack_filtered = df_stack_calc.copy()

                    if not df_stack_filtered.empty:
                        df_stack_filtered['Year_Str'] = df_stack_filtered['Year'].astype(str)

                        df_latest = df_stack_calc.groupby('Ticker').agg({
                            'จำนวนหุ้น': 'last',
                            'ต้นทุนหุ้น': 'last'
                        }).reset_index()

                        # แปลงข้อมูลเป็นตัวเลขอย่างปลอดภัยก่อนนำมาคูณกัน
                        df_latest['ต้นทุนหุ้น'] = pd.to_numeric(df_latest['ต้นทุนหุ้น'], errors='coerce').fillna(0)
                        df_latest['จำนวนหุ้น'] = pd.to_numeric(df_latest['จำนวนหุ้น'], errors='coerce').fillna(0)

                        # คำนวณต้นทุนรวมทั้งหมดของแต่ละ Ticker ใช้ชื่อคอลัมน์ว่า 'ต้นทุนหุ้น'
                        df_latest['ต้นทุนหุ้น'] = df_latest['ต้นทุนหุ้น'] * df_latest['จำนวนหุ้น']

                        df_grouped_yearly = df_stack_filtered.groupby(['Ticker', 'Year_Str'])['ยอดรับสุทธิ'].sum().reset_index()
                        df_merged_yearly = pd.merge(df_grouped_yearly, df_latest[['Ticker', 'ต้นทุนหุ้น']], on='Ticker')

                        # แปลงค่าให้เป็นตัวเลขเพื่อความปลอดภัยในการคำนวณ
                        df_merged_yearly['ยอดรับสุทธิ'] = pd.to_numeric(df_merged_yearly['ยอดรับสุทธิ'], errors='coerce').fillna(0)
                        df_merged_yearly['ต้นทุนหุ้น'] = pd.to_numeric(df_merged_yearly['ต้นทุนหุ้น'], errors='coerce').fillna(0)

                        df_merged_yearly['Yield_on_Cost_Annual'] = df_merged_yearly.apply(
                            lambda row: (row['ยอดรับสุทธิ'] / row['ต้นทุนหุ้น'] * 100) if row['ต้นทุนหุ้น'] > 0 else 0.0,
                            axis=1
                        )

                        if not df_merged_yearly.empty:
                            df_total_yield = df_merged_yearly.groupby('Ticker')['Yield_on_Cost_Annual'].sum().reset_index()
                            sorted_tickers_yield = df_total_yield.sort_values(by='Yield_on_Cost_Annual', ascending=True)['Ticker'].tolist()

                            df_merged_yearly['Text_Label'] = df_merged_yearly['Yield_on_Cost_Annual'].apply(
                                lambda x: f"{x:.2f}%" if x > 0.5 else ""
                            )

                            fig_stacked = px.bar(
                                df_merged_yearly,
                                x='Yield_on_Cost_Annual',
                                y='Ticker',
                                color='Year_Str',
                                orientation='h',
                                barmode='stack',
                                category_orders={'Ticker': sorted_tickers_yield},
                                text='Text_Label',
                                color_discrete_sequence=px.colors.qualitative.Prism
                            )

                            fig_stacked.update_traces(
                                textposition='inside', 
                                insidetextanchor='middle'
                            )

                            fig_stacked.update_layout(
                                xaxis_title=f"Annual Dividend Yield on Cost (%) [{selected_stack_period}]",
                                yaxis_title="ชื่อหุ้น (Ticker)",
                                height=max(350, len(sorted_tickers_yield) * 45),
                                margin=dict(l=10, r=20, t=20, b=20),
                                legend_title="ปีที่ได้รับ (Year)"
                            )
                            st.plotly_chart(fig_stacked, use_container_width=True)
                        else:
                            st.info("ไม่มีข้อมูลเพียงพอสำหรับกราฟ Stacked Bar รายปีนี้")
                    else:
                        st.info("ไม่มีข้อมูลในช่วงเวลาที่เลือกสำหรับกราฟนี้")
                else:
                    st.info("💡 ยังไม่มีข้อมูลเงินปันผลในระบบ สามารถเพิ่มข้อมูลผ่านฟอร์มด้านบนหรืออัปโหลดไฟล์รายงาน TSD ได้เลยครับ")


    #########################
    with tab_journal:
        st.markdown("#### 📖 บันทึกผลการเทรด (Trading Journal)")

        # --- ส่วนการ Upload ไฟล์ ---
        with st.expander("📤 อัปโหลดข้อมูลจากไฟล์ Excel/CSV"):
            uploaded_file = st.file_uploader("เลือกไฟล์ของคุณ", type=['csv', 'xlsx', 'xls'])
            if uploaded_file:
                if st.button("ยืนยันการนำเข้าข้อมูล"):
                    load_data_from_file(uploaded_file)
        # --------------------------

        ################ เรียกการคำนวนนับจำนวนวันถือหุ้น #####################
        def calculate_journal_stats(df):
            df = df[df['สถานะ'] == 'Closed (ขายแล้ว)'].copy()

            # 1. จัดการคอลัมน์และคำนวณวันที่
            if 'วันที่ซื้อ' not in df.columns: df['วันที่ซื้อ'] = df['วันที่'] 
            if 'วันที่ขาย' not in df.columns: df['วันที่ขาย'] = df['วันที่'] 

            df['วันที่ซื้อ'] = pd.to_datetime(df['วันที่ซื้อ'])
            df['วันที่ขาย'] = pd.to_datetime(df['วันที่ขาย'])
            df['Holding_Days'] = (df['วันที่ขาย'] - df['วันที่ซื้อ']).dt.days.clip(lower=0)

            # 2. คำนวณเป็น % (Profit / Cost) * 100
            df['ROI_Percent'] = (df['กำไร/ขาดทุน (บาท)'] / df['ต้นทุน (บาท)'].replace(0, np.nan)) * 100

            df['Year'] = df['วันที่ขาย'].dt.year
            df['Month'] = df['วันที่ขาย'].dt.month

            # 3. สรุปผลเป็น % ตามที่ต้องการ
            stats = df.groupby(['Year', 'Month']).agg(
                Avg_Profit_Pct=('ROI_Percent', lambda x: x[x>0].mean()),
                Avg_Loss_Pct=('ROI_Percent', lambda x: x[x<=0].mean()),
                Win_Rate=('ROI_Percent', lambda x: (x>0).mean() * 100),
                Trade_Count=('ROI_Percent', 'count'),
                Max_Profit_Pct=('ROI_Percent', 'max'),
                Max_Loss_Pct=('ROI_Percent', 'min'),
                Avg_Days_Win=('Holding_Days', lambda x: x[df['ROI_Percent']>0].mean()),
                Avg_Days_Loss=('Holding_Days', lambda x: x[df['ROI_Percent']<=0].mean())
            )
            stats = stats.round({'Avg_Days_Win': 0, 'Avg_Days_Loss': 0})
            stats = stats.round(2)
            return stats
        ########################################################################

        ### แสดงข้อมูลสถิติ รายเดือน รายปี ####
        if st.session_state.journal_data:
            df_journal = pd.DataFrame(st.session_state.journal_data)

            # --- เริ่มต้น Data Migration ---
            cols_to_check = ['วันที่ซื้อ', 'วันที่ขาย']
            for col in cols_to_check:
                if col not in df_journal.columns:
                    df_journal[col] = df_journal['วันที่']

            df_journal['วันที่ซื้อ'] = pd.to_datetime(df_journal['วันที่ซื้อ'], errors='coerce')
            df_journal['วันที่ขาย'] = pd.to_datetime(df_journal['วันที่ขาย'], errors='coerce')
            st.session_state.journal_data = df_journal.to_dict('records')
            # --- จบการ Data Migration ---

            # 2. ส่วนสรุป Metric 3 ค่าด้านบน (อิงจากช่วงเวลาที่เลือก)
            with st.expander("📊 สถิติการเทรดรายเดือน", expanded=False):
                stats_df = calculate_journal_stats(df_journal)

                st.markdown("##### 🎯 สถิติการเทรดจริง & การปรับจุดคัทลอส (RR 2:1)")
                period = st.radio("ดูค่าเฉลี่ยย้อนหลัง:", ["3 เดือน", "6 เดือน", "1 ปี"], horizontal=True, key="stats_period")

                months_map = {"3 เดือน": 3, "6 เดือน": 6, "1 ปี": 12}
                cutoff_date = pd.Timestamp.now() - pd.DateOffset(months=months_map[period])

                if 'วันที่ขาย' not in df_journal.columns:
                    df_journal['วันที่ขาย'] = df_journal['วันที่']

                df_journal['วันที่ขาย'] = pd.to_datetime(df_journal['วันที่ขาย'], errors='coerce')

                df_period = df_journal[(df_journal['วันที่ขาย'] >= cutoff_date) & 
                                       (df_journal['สถานะ'] == 'Closed (ขายแล้ว)')].copy()

                if not df_period.empty:
                    if 'วันที่ซื้อ' not in df_period.columns:
                        df_period['วันที่ซื้อ'] = df_period['วันที่']
                    if 'วันที่ขาย' not in df_period.columns:
                        df_period['วันที่ขาย'] = df_period['วันที่']

                    df_period['วันที่ซื้อ'] = pd.to_datetime(df_period['วันที่ซื้อ'], errors='coerce')
                    df_period['วันที่ขาย'] = pd.to_datetime(df_period['วันที่ขาย'], errors='coerce')
                    df_period['Holding_Days'] = (df_period['วันที่ขาย'] - df_period['วันที่ซื้อ']).dt.days.clip(lower=0)

                    col_profit_loss = 'กำไร/ขาดทุน (บาท)'
                    col_cost = 'ต้นทุน (บาท)'

                    df_period[col_profit_loss] = pd.to_numeric(df_period[col_profit_loss], errors='coerce')
                    df_period[col_cost] = pd.to_numeric(df_period[col_cost], errors='coerce')

                    w_rate = (df_period[col_profit_loss] > 0).mean() * 100

                    profit_mask = (df_period[col_profit_loss] > 0) & (df_period[col_cost] > 0)
                    profit_series = (df_period.loc[profit_mask, col_profit_loss] / df_period.loc[profit_mask, col_cost]) * 100
                    avg_profit = profit_series.clip(upper=500).mean() if not profit_series.empty else 0

                    loss_mask = (df_period[col_profit_loss] <= 0) & (df_period[col_cost] > 0)
                    loss_series = (df_period.loc[loss_mask, col_profit_loss] / df_period.loc[loss_mask, col_cost]) * 100
                    loss_series = loss_series[loss_series >= -100] 
                    avg_loss = loss_series.mean() if not loss_series.empty else 0

                    loss_adj = (avg_profit / 2) * -1

                    c1, c2, c3 = st.columns(3)
                    c1.metric("Win Rate", f"{w_rate:.1f} %")
                    c2.metric("Avg P/L", f"{avg_profit:.1f}% / {avg_loss:.1f}%")
                    c3.metric("Rec. Cut Loss (RR 2:1)", f"{loss_adj:.1f} %")
                else:
                    st.info("ไม่มีข้อมูลย้อนหลังในช่วงเวลานี้")

                st.markdown("---")

                if not stats_df.empty:
                    years = sorted(stats_df.index.get_level_values('Year').unique())
                    selected_year = st.selectbox("เลือกปีที่ต้องการดูสถิติ:", years, key="stats_year")

                    year_data = stats_df.loc[selected_year]

                    styled_df = year_data.style.format({
                        'Avg_Profit_Pct': '{:.2f} %',
                        'Avg_Loss_Pct': '{:.2f} %',
                        'Win_Rate': '{:.2f} %',
                        'Max_Profit_Pct': '{:.2f} %',
                        'Max_Loss_Pct': '{:.2f} %',
                        'Avg_Days_Win': '{:.0f} วัน', 
                        'Avg_Days_Loss': '{:.0f} วัน'
                    })
                    st.table(styled_df)

            ########################################################################
            # 3. ตารางประวัติ 
            df_journal = pd.DataFrame(st.session_state.journal_data)
            df_journal['วันที่'] = pd.to_datetime(df_journal['วันที่'])            

            df_journal['temp_sort'] = df_journal['สถานะ'].apply(lambda x: 0 if "Open" in x else 1)
            df_journal = df_journal.sort_values(by=['temp_sort', 'วันที่'], ascending=[True, False])
            df_journal = df_journal.drop(columns=['temp_sort'])

            with st.expander("📂 ดูประวัติการเทรดย้อนหลัง", expanded=False):
                items_per_page = 50
                total_pages = (len(df_journal) - 1) // items_per_page + 1
                page = st.number_input("หน้า:", min_value=1, max_value=total_pages, value=1, key="journal_page")

                start_idx = (page - 1) * items_per_page
                df_display = df_journal.iloc[start_idx : start_idx + items_per_page]

                edited_journal = st.data_editor(df_display, use_container_width=True, key="journal_editor")

                if st.button("💾 อัปเดตตารางหน้านี้", key="save_journal_page"):
                    edited_journal['ราคาหุ้นที่ซื้อ (บาท/หุ้น)'] = pd.to_numeric(edited_journal['ราคาหุ้นที่ซื้อ (บาท/หุ้น)'], errors='coerce')
                    edited_journal['จำนวนหุ้นที่ซื้อ'] = pd.to_numeric(edited_journal['จำนวนหุ้นที่ซื้อ'], errors='coerce')
                    edited_journal['ต้นทุน (บาท)'] = edited_journal['ราคาหุ้นที่ซื้อ (บาท/หุ้น)'] * edited_journal['จำนวนหุ้นที่ซื้อ']

                    date_cols = ['วันที่', 'วันที่ซื้อ', 'วันที่ขาย']
                    for col in date_cols:
                        if col in edited_journal.columns:
                            edited_journal[col] = pd.to_datetime(edited_journal[col], errors='coerce').dt.strftime('%Y-%m-%d')

                    st.session_state.journal_data = edited_journal.to_dict('records')
                    save_journal()
                    st.success("บันทึกข้อมูลเรียบร้อยแล้วครับ!")

                csv = df_journal.to_csv(index=False).encode('utf-8-sig')
                st.download_button("📥 Export เป็นไฟล์ Excel (CSV)", data=csv, file_name="trading_journal.csv", mime="text/csv", key="export_journal_csv")
        else:
            st.info("ยังไม่มีข้อมูลรายการเทรดในระบบครับ")


        #################################################
        # --- ตารางแสดงแผนการเทรด ---
        with tab_plan:
            st.subheader("📝 แผนการเทรดและตั้งค่า Alert")

            # 1. ส่วนฟอร์มเพิ่มหุ้นใหม่
            with st.form("trading_plan_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                with col1:
                    ticker = st.text_input("ชื่อหุ้น:", value=st.session_state.get("selected_ticker", ""))
                    entry = st.number_input("ราคาเข้าซื้อ:", min_value=0.0, format="%.2f", value=0.0)
                    stop_loss = st.number_input("จุดตัดขาดทุน:", value=float(entry * 0.95) if entry > 0 else 0.0, format="%.2f")
                    support = st.number_input("แนวรับ:", min_value=0.0, format="%.2f", value=0.0)
                with col2:
                    resistance = st.number_input("แนวต้าน:", min_value=0.0, format="%.2f", value=0.0)
                    take_profit = st.number_input("จุดขายทำกำไร:", min_value=0.0, format="%.2f", value=0.0)
                    image_url = st.text_input("วาง Link รูปภาพ (URL):")

                submit_button = st.form_submit_button("บันทึกแผนลงตาราง")

            if submit_button:
                if not ticker:
                    st.error("กรุณาระบุชื่อหุ้นครับ!")
                else:
                    from datetime import datetime

                    # 1. สร้าง Dictionary ของหุ้นใหม่
                    new_data = {
                        'Ticker': ticker, 'Entry_Price': entry, 'ราคาตลาด': 0.0,
                        'Stop_Loss': stop_loss, 'แนวรับ': support, 'แนวต้าน': resistance, 
                        'ห่างจาก_SL(%)': 0.0, 'Take_Profit': take_profit,
                        'สถานะ': 'ปกติ', 'Timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'Image_URL': image_url, 'Alert_Date': ''
                    }

                    # 2. โหลดข้อมูลปัจจุบันจาก Google Sheet ออกมาก่อน
                    current_df = load_data("TradingPlan")

                    # ถ้าตารางว่าง ให้สร้าง DataFrame ใหม่ขึ้นมาเลย
                    if current_df is None or current_df.empty:
                        final_df = pd.DataFrame([new_data])
                    else:
                        # รวมหุ้นเดิมกับหุ้นใหม่เข้าด้วยกัน
                        new_df = pd.DataFrame([new_data])
                        final_df = pd.concat([current_df, new_df], ignore_index=True)

                    # 3. บันทึกข้อมูลที่รวมแล้วด้วยฟังก์ชัน clear_and_save_data
                    # (เพราะฟังก์ชันนี้ลบของเก่าแล้วเขียนทับใหม่ เราจึงต้องส่ง 'ข้อมูลก้อนใหม่' ที่รวมตัวเก่าไปให้)
                    if clear_and_save_data(final_df, "TradingPlan"):
                        st.success("บันทึกแผนเรียบร้อย!")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error("เกิดข้อผิดพลาดในการบันทึกข้อมูลครับ")

            # 2. ส่วนตารางแสดงผล
            st.divider()
            st.subheader("📊 ตารางแผนการเทรดของฉัน")
            plan_df = load_data("TradingPlan")

            # กำหนดคอลัมน์มาตรฐาน (ลบ 'Alert_Date' ออกแล้ว)
            cols = ['Ticker', 'Entry_Price', 'แนวรับ', 'แนวต้าน', 'ราคาตลาด', 'Stop_Loss', 'Take_Profit', 'ห่างจาก_SL(%)', 'สถานะ', 'Timestamp', 'Image_URL']

            if plan_df.empty or 'Ticker' not in plan_df.columns:
                plan_df = pd.DataFrame(columns=cols)
            else:
                plan_df.columns = plan_df.columns.str.strip()

            # คำนวณข้อมูล
            if not plan_df.empty and 'Ticker' in plan_df.columns:
                plan_df.columns = plan_df.columns.str.strip()

                # แปลงคอลัมน์ตัวเลข
                target_cols = ['Entry_Price', 'Stop_Loss', 'Take_Profit']
                for c in target_cols:
                    if c in plan_df.columns:
                        plan_df[c] = pd.to_numeric(plan_df[c], errors='coerce').fillna(0.0)
                    else:
                        plan_df[c] = 0.0

                # ดึงราคาตลาด (Batch)
                tickers = [f"{t}.BK" for t in plan_df['Ticker'].unique()]
                try:
                    price_data = yf.download(tickers, period="1d", group_by='ticker', progress=False)['Close']
                    def get_price(t):
                        symbol = f"{t}.BK"
                        try:
                            if isinstance(price_data, pd.DataFrame): return float(price_data[symbol].iloc[-1])
                            return float(price_data.iloc[-1])
                        except: return 0.0
                    plan_df['ราคาตลาด'] = plan_df['Ticker'].apply(get_price)
                except:
                    plan_df['ราคาตลาด'] = 0.0

                # คำนวณห่างจาก SL และสถานะ
                plan_df['ห่างจาก_SL(%)'] = np.where(plan_df['ราคาตลาด'] > 0, ((plan_df['ราคาตลาด'] - plan_df['Stop_Loss']) / plan_df['ราคาตลาด'] * 100), 0.0).round(2)
                plan_df['สถานะ'] = plan_df.apply(check_alerts, axis=1)

            # แสดงตาราง (ลบ Alert_Date ออกจาก column_config แล้ว)
            edited_df = st.data_editor(
                plan_df[cols],
                column_config={
                    "Ticker": st.column_config.TextColumn("หุ้น", disabled=True, width="small"),
                    "Entry_Price": st.column_config.NumberColumn("ราคาซื้อ", format="%.2f", width="small"),
                    "แนวรับ": st.column_config.NumberColumn("แนวรับ", format="%.2f", width="small"),
                    "แนวต้าน": st.column_config.NumberColumn("แนวต้าน", format="%.2f", width="small"),
                    "ราคาตลาด": st.column_config.NumberColumn("ราคาตลาด", format="%.2f", disabled=True, width="small"),
                    "Stop_Loss": st.column_config.NumberColumn("จุดตัดขาดทุน", format="%.2f", width="small"),
                    "Take_Profit": st.column_config.NumberColumn("จุดขายทำกำไร", format="%.2f", width="small"),
                    "ห่างจาก_SL(%)": st.column_config.NumberColumn("ห่างจาก SL (%)", format="%.2f%%", disabled=True, width="small"),
                    "สถานะ": st.column_config.TextColumn("สถานะ", disabled=True, width="medium"),
                    "Image_URL": st.column_config.LinkColumn("Plan trade", display_text="ดูรูปแผนเทรด", disabled=True, width="medium"),
                },
                use_container_width=True, 
                key="fixed_plan_editor_v2", 
                num_rows="dynamic"
            )

            if st.button("💾 บันทึกการแก้ไข"):
                final_df = edited_df.copy()
                final_df['สถานะ'] = "" # ล้างค่าให้ระบบคำนวณใหม่

                for c in cols:
                    if c not in final_df.columns: final_df[c] = ""

                if clear_and_save_data(final_df[cols], "TradingPlan"):
                    st.success("บันทึกและอัปเดตตารางเรียบร้อย!")
                    st.cache_data.clear()
                    st.rerun()
