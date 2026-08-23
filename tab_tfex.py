# =============================================================
# tab_tfex.py
# แท็บ TFEX (Phase 2 ของการแยกไฟล์)
# =============================================================
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from backend_functions import IM_PER_CONTRACT, get_auto_atr_cached, load_data, save_cash_to_gsheet, save_data_to_sheet, update_trade_close, get_active_sheet_name


def render_tab_tfex():
    st.subheader("📝 ระบบเทรด TFEX")

    # 1. โหลดข้อมูล
    tfex_df = load_data("TFEX_History", get_active_sheet_name()) 
    cash_df = load_data("Cash_Flow", get_active_sheet_name())
    # 🔧 แก้บั๊ก: มาตรฐานชื่อคอลัมน์กำไร/ขาดทุนให้เป็น 'Net_Profit' ตั้งแต่จุดโหลดข้อมูลเลย
    # (บางบัญชีบันทึกเป็น 'กำไรสุทธิ' แทน) เพื่อให้โค้ดทั้งหมดที่ใช้ tfex_df ต่อจากนี้ทำงานถูกต้อง
    if not tfex_df.empty:
        if 'Net_Profit' not in tfex_df.columns and 'กำไรสุทธิ' in tfex_df.columns:
            tfex_df = tfex_df.rename(columns={'กำไรสุทธิ': 'Net_Profit'})
        # 🔧 แก้บั๊ก: สร้างคอลัมน์ 'Close_Price_Cleaned' ไว้ตั้งแต่ต้นฟังก์ชันเลย (ครั้งเดียว)
        # เดิมคอลัมน์นี้ถูกสร้างกระจายอยู่หลายจุดในไฟล์แบบมีเงื่อนไขไม่ตรงกัน ทำให้บางจุดที่ใช้
        # คอลัมน์นี้ต่อ (เช่น ส่วนคำนวณ Win/Loss) ไม่มีการเช็คก่อนว่าคอลัมน์นี้ถูกสร้างไว้แล้วหรือยัง
        if 'Close_Price' in tfex_df.columns:
            tfex_df['Close_Price_Cleaned'] = pd.to_numeric(tfex_df['Close_Price'], errors='coerce').fillna(0)

    # 2. กรองข้อมูลเฉพาะรายการที่ปิดสถานะแล้ว (Realized PnL)
    if not tfex_df.empty and 'Close_Price' in tfex_df.columns:
        # แปลงคอลัมน์ Close_Price ให้เป็นตัวเลขก่อน (errors='coerce' จะเปลี่ยนค่าที่อ่านไม่ได้เป็น NaN)
        # จากนั้น fillna(0) เพื่อเปลี่ยน NaN ให้เป็น 0 จะได้เปรียบเทียบ > 0 ได้
        close_prices = pd.to_numeric(tfex_df['Close_Price'], errors='coerce').fillna(0)

        # กรองเอาเฉพาะที่ราคามากกว่า 0
        closed_trades = tfex_df[close_prices > 0].copy()
    else:
        closed_trades = tfex_df.copy()

    # คำนวณ Net_Profit
    if not closed_trades.empty and 'Net_Profit' in closed_trades.columns:
        # แปลง Net_Profit เป็นตัวเลขด้วย เพื่อป้องกัน error ในอนาคต
        total_pnl = pd.to_numeric(closed_trades['Net_Profit'], errors='coerce').sum()
    else:
        total_pnl = 0
    # 3. คำนวณเงินต้นสุทธิ
    # ใช้ .astype(str).str.lower() เพื่อป้องกันปัญหาตัวอักษรพิมพ์เล็ก/ใหญ่
    total_deposit = cash_df[cash_df['Type'].astype(str).str.lower() == 'deposit']['Amount'].sum() if not cash_df.empty else 0
    total_withdraw = cash_df[cash_df['Type'].astype(str).str.lower() == 'withdraw']['Amount'].sum() if not cash_df.empty else 0
    net_capital = total_deposit - total_withdraw

    # 4. คำนวณพอร์ต (ใช้ Realized PnL)
    net_worth = net_capital + total_pnl
    growth_pct = (total_pnl / net_capital * 100) if net_capital > 0 else 0
    # ⭐️ เพิ่มบรรทัดนี้ เพื่อแชร์ค่าพอร์ต TFEX ไปให้หน้าหลักใช้งาน
    st.session_state['tfex_net_worth'] = net_worth

    # แสดง Dashboard
    c1, c2, c3 = st.columns(3)
    c1.metric("มูลค่าพอร์ตสุทธิ (Cash Basis)", f"{net_worth:,.2f} บาท")
    c2.metric("กำไรรวมสุทธิ (Realized)", f"{total_pnl:,.2f} บาท")
    c3.metric("การเติบโต", f"{growth_pct:.2f} %")
    st.divider()

    # --- เริ่มแถวที่ 2: Performance Metrics (รวมเชิงลึก) ---
    st.subheader("📊 Performance Monitor")

    # 1. สร้าง Filter ช่วงเวลา
    period_options = {"3 เดือน": 90, "6 เดือน": 180, "1 ปี": 365, "ทั้งหมด": 9999}
    selected_period = st.radio("เลือกช่วงเวลา:", list(period_options.keys()), horizontal=True, key="perf_filter")

    # 2. กรองข้อมูลตามช่วงเวลา
    perf_df = closed_trades.copy()
    # 🔧 แก้บั๊ก: มาตรฐานชื่อคอลัมน์ให้เป็น 'Net_Profit' ตั้งแต่ต้นเลย (เผื่อบางบัญชีบันทึกเป็น
    # 'กำไรสุทธิ' แทน) เพราะโค้ดด้านล่างหลายจุดอ้างอิงชื่อ 'Net_Profit' ตรงๆ โดยไม่มีการเช็คซ้ำ
    # เดิมมีการป้องกันไว้แค่บางจุด (บรรทัด win_trades) แต่จุดอื่นๆ ยังพังอยู่ถ้าคอลัมน์ชื่อไม่ตรง
    if 'Net_Profit' not in perf_df.columns and 'กำไรสุทธิ' in perf_df.columns:
        perf_df = perf_df.rename(columns={'กำไรสุทธิ': 'Net_Profit'})
    if 'Net_Profit' not in perf_df.columns:
        perf_df['Net_Profit'] = 0.0
    if 'Date_Close' in perf_df.columns:
        perf_df['Date_Close'] = pd.to_datetime(perf_df['Date_Close'])
    else:
        # ถ้าไม่มีคอลัมน์ Date_Close ให้ลองเช็คว่ามีคอลัมน์วันที่ชื่ออื่นไหม เช่น 'Date' หรือข้ามไปก่อน
        if 'Date' in perf_df.columns:
            perf_df['Date_Close'] = pd.to_datetime(perf_df['Date'])
    days_ago = period_options[selected_period]
    if days_ago != 9999:
        cutoff_date = pd.Timestamp.now() - pd.Timedelta(days=days_ago)
        if 'Date_Close' in perf_df.columns:
            perf_df = perf_df[perf_df['Date_Close'] >= cutoff_date]
        elif 'Date' in perf_df.columns:
            perf_df = perf_df[perf_df['Date'] >= cutoff_date]

    # 3. คำนวณ Metrics ทั้งหมดจาก perf_df ที่กรองแล้ว
    total_trades = len(perf_df)
    # ป้องกัน KeyError กรณีไม่มีคอลัมน์ Net_Profit
    if 'Net_Profit' in perf_df.columns:
        win_trades = len(perf_df[perf_df['Net_Profit'] > 0])
    elif 'กำไรสุทธิ' in perf_df.columns:
        win_trades = len(perf_df[perf_df['กำไรสุทธิ'] > 0])
    else:
        win_trades = 0
    win_rate = (win_trades / total_trades * 100) if total_trades > 0 else 0

    avg_win = perf_df[perf_df['Net_Profit'] > 0]['Net_Profit'].mean() if win_trades > 0 else 0
    avg_loss = perf_df[perf_df['Net_Profit'] <= 0]['Net_Profit'].abs().mean() if (total_trades - win_trades) > 0 else 0
    rr_ratio = (avg_win / avg_loss) if avg_loss > 0 else 0

    gross_profit = perf_df[perf_df['Net_Profit'] > 0]['Net_Profit'].sum()
    gross_loss = perf_df[perf_df['Net_Profit'] <= 0]['Net_Profit'].abs().sum()
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0)

    expectancy = (win_rate/100 * avg_win) - ((1 - win_rate/100) * avg_loss)

    # คำนวณเชิงลึก (Efficiency Analysis)
    perf_df['Points'] = perf_df['Net_Profit'] / 200
    avg_win_pts = perf_df[perf_df['Points'] > 0]['Points'].mean() if len(perf_df[perf_df['Points'] > 0]) > 0 else 0
    avg_loss_pts = perf_df[perf_df['Points'] <= 0]['Points'].abs().mean() if len(perf_df[perf_df['Points'] <= 0]) > 0 else 0

    # Max Drawdown (คำนวณจากช่วงที่กรอง)
    # 🔧 แก้บั๊ก: ถ้าตารางว่างสนิท (ไม่มีแม้แต่แถวเทรดเดียว) จะไม่มีคอลัมน์ Date_Close/Date_Open
    # ให้ใช้เลย ต้องเช็คก่อนเสมอ ไม่งั้น sort_values('Date_Close') จะ error ทันที
    if not perf_df.empty and 'Date_Close' in perf_df.columns:
        temp_df = perf_df.sort_values('Date_Close')
        temp_df['Cumulative'] = temp_df['Net_Profit'].cumsum()
        max_drawdown = (temp_df['Cumulative'] - temp_df['Cumulative'].cummax()).min() if not temp_df.empty else 0
    else:
        max_drawdown = 0

    # ระยะเวลาถือครอง
    if not perf_df.empty and 'Date_Open' in perf_df.columns and 'Date_Close' in perf_df.columns:
        perf_df['Date_Open'] = pd.to_datetime(perf_df['Date_Open'])
        perf_df['Hold_Days'] = (perf_df['Date_Close'] - perf_df['Date_Open']).dt.days
        avg_hold = perf_df['Hold_Days'].mean()
    else:
        avg_hold = 0

    # 4. แสดงผลแบบ Grid
    # แถวแรก
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Win Rate", f"{win_rate:.1f}%")
    c2.metric("R:R Ratio", f"{rr_ratio:.2f}")
    c3.metric("Profit Factor", f"{profit_factor:.2f}")
    c4.metric("Expectancy", f"{expectancy:,.0f}")

    st.write("---") # เส้นคั่น

    # แถวสอง (เชิงลึก)
    e1, e2, e3, e4 = st.columns(4)
    e1.metric("กำไรเฉลี่ย (จุด)", f"{avg_win_pts:.1f} pts")
    e2.metric("ขาดทุนเฉลี่ย (จุด)", f"{avg_loss_pts:.1f} pts")
    e3.metric("Max Drawdown", f"{max_drawdown:,.0f} บาท")
    e4.metric("ระยะเวลาถือเฉลี่ย", f"{avg_hold:.1f} วัน")

    st.divider()

    # 3. สร้าง 3 Tabs
    sub_tfex_input, sub_tfex_close, sub_tfex_cash, sub_tfex_history = st.tabs([
    "➕ บันทึกเทรดใหม่", 
    "🏁 ปิดสถานะเทรด", 
    "➕ บันทึกเติม/ถอนเงิน", 
    "📜 ประวัติและ Portfolio"
    ])
    with sub_tfex_input:
        st.subheader("🛡 คำนวณขนาดสัญญา (Position Size)")

        # ดึงค่า ATR และ Multiplier ที่ใช้งานล่าสุดจาก session_state มาเป็นค่าตั้งต้น
        current_atr = st.session_state.get('active_atr', 6.5)

        c1, c2, c3 = st.columns(3)
        # เปลี่ยนเป็น Slider เลือกความเสี่ยง 0% ถึง 5% (เพิ่มทีละ 0.25% เพื่อความละเอียด)
        risk_pct = c1.slider("ความเสี่ยงที่ยอมรับได้ (% ของพอร์ต)", min_value=0.0, max_value=5.0, value=1.0, step=0.25)

        # ⭐️ ช่องกรอก ATR ที่เชื่อมโยงกับค่ากลาง (สามารถพิมพ์แก้ไขเพื่อดูจาก TradingView ได้เช่นกัน)
        user_atr = c2.number_input("ค่า ATR ปัจจุบัน (แก้ไขได้)", value=float(current_atr), step=0.1)

        # ช่องกรอกตัวคูณ Multiplier สำหรับ ATR
        atr_multiplier = c3.number_input("ตัวคูณ ATR (Multiplier)", value=1.5, step=0.1)

        # คำนวณระยะ Stop Loss จาก ATR ที่ใช้งานจริง (ATR * Multiplier)
        stop_loss_points = user_atr * atr_multiplier
        st.caption(f"📍 ระยะจุดตัดขาดทุนคำนวณจาก ATR อัตโนมัติ: **{stop_loss_points:.2f} จุด** (ATR: {user_atr} x Multiplier: {atr_multiplier})")

        # คำนวณเงินที่ยอมขาดทุนได้จริงจากเปอร์เซ็นต์พอร์ต (Net Worth)
        risk_amount = net_worth * (risk_pct / 100.0)

        # ใช้ตัวแปร Global ที่เราตั้งค่าไว้
        im_per_contract = IM_PER_CONTRACT 

        # คำนวณสัญญา (สมมติ 1 จุด TFEX = 200 บาท)
        contract_by_risk = risk_amount / (stop_loss_points * 200) if (stop_loss_points * 200) > 0 else 0
        contract_by_margin = net_worth / im_per_contract if im_per_contract > 0 else 0 # net_worth ดึงมาจาก Dashboard

        max_contracts = min(int(contract_by_risk), int(contract_by_margin))

        # แสดงผลแบบมืออาชีพ
        st.info(f"📋 ข้อมูลการคำนวณ:")
        st.write(f"- เงินต้นรวม (Net Worth): {net_worth:,.0f} บาท")
        st.write(f"- ยอมขาดทุนได้สูงสุด: **{risk_amount:,.2f} บาท** ({risk_pct}%)")
        st.write(f"- ค่า IM ปัจจุบัน: {im_per_contract:,.0f} บาท/สัญญา")

        if max_contracts <= 0:
            st.error("⚠️ เงินในพอร์ตไม่เพียงพอที่จะเปิดสัญญาภายใต้เงื่อนไขความเสี่ยงนี้")
        else:
            st.success(f"✅ **สรุป: คุณควรเปิดสถานะไม่เกิน {max_contracts} สัญญา**")

        # 1. แสดงรายการที่ถืออยู่ (Open Positions)
        st.subheader("📊 สถานะที่ถืออยู่ (Open Positions)")

        # 🔧 แก้บั๊ก: กันเหนียวเพิ่ม เผื่อ load_data() ลองใหม่ครบ 3 ครั้งแล้วยังพลาด (เช่นโควตาติดยาว)
        # จะได้ตารางว่างสนิทไม่มีคอลัมน์เลย ป้องกันไม่ให้เข้าถึงคอลัมน์ 'Close_Price'/'Size' ตรงๆ
        if not tfex_df.empty and 'Close_Price' in tfex_df.columns:
            tfex_df['Close_Price_Cleaned'] = pd.to_numeric(tfex_df['Close_Price'], errors='coerce').fillna(0)
            open_positions = tfex_df[tfex_df['Close_Price_Cleaned'] == 0].copy()
        else:
            open_positions = pd.DataFrame()

        if not open_positions.empty:
            # ⭐️ เชื่อมโยงค่า ATR และ Multiplier ที่ผู้ใช้ใช้งานล่าสุด (จากฟอร์มด้านบน) มาแสดงและคำนวณในตาราง
            open_positions['ATR'] = user_atr 

            # แปลงข้อมูลราคาเปิดและ ATR ให้เป็นตัวเลขเพื่อความปลอดภัย
            open_positions['Open_Price'] = pd.to_numeric(open_positions['Open_Price'], errors='coerce')
            open_positions['ATR'] = pd.to_numeric(open_positions['ATR'], errors='coerce')

            # คำนวณจุด Stop Loss จาก ATR แยกตามสถานะ Long / Short ของแต่ละไม้
            # Long: ราคาเปิด - (ATR * Multiplier)
            # Short: ราคาเปิด + (ATR * Multiplier)
            open_positions['ATR_Stop_Loss'] = open_positions.apply(
                lambda row: (row['Open_Price'] - (row['ATR'] * atr_multiplier)) if row['Status'] == 'Long' 
                else (row['Open_Price'] + (row['ATR'] * atr_multiplier)), 
                axis=1
            )

            # แสดงผลตารางพร้อมคอลัมน์ ATR และ Stop Loss ที่คำนวณสดๆ ตรงกัน
            st.dataframe(
                open_positions[['Trade_ID', 'Date_Open', 'Series', 'Status', 'Size', 'Open_Price', 'ATR', 'ATR_Stop_Loss']], 
                use_container_width=True
            )
        else:
            st.info("ไม่มีรายการที่ถืออยู่ในปัจจุบัน")

        # คำนวณ Margin Utilization
        # 🔧 กันเหนียว: ถ้า open_positions ว่างสนิทไม่มีคอลัมน์ Size ให้ถือว่ายังไม่ได้ใช้ margin เลย
        if not open_positions.empty and 'Size' in open_positions.columns:
            total_margin_used = open_positions['Size'].sum() * IM_PER_CONTRACT
        else:
            total_margin_used = 0
        utilization = (total_margin_used / net_worth) * 100 if net_worth > 0 else 0

        # --- แบ่งหน้าจอเป็น 2 คอลัมน์ เพื่อวางกราฟคู่กัน ---
        col_left, col_right = st.columns(2)

        with col_left:
            st.subheader("🎯 สถิติแพ้ / ชนะ (Win / Loss)")
            # กรองเฉพาะรายการที่ปิดสถานะแล้ว (Close_Price > 0) มาคำนวณ Win/Loss
            # 🔧 แก้บั๊ก: เช็คว่ามีคอลัมน์ Close_Price_Cleaned จริงก่อนใช้ (จะไม่มีถ้าตารางว่างสนิท)
            if not tfex_df.empty and 'Close_Price_Cleaned' in tfex_df.columns:
                closed_positions = tfex_df[tfex_df['Close_Price_Cleaned'] > 0]
            else:
                closed_positions = pd.DataFrame()

            if not closed_positions.empty and 'Win_Lose' in closed_positions.columns:
                win_count = len(closed_positions[closed_positions['Win_Lose'] == 'Win'])
                lose_count = len(closed_positions[closed_positions['Win_Lose'] == 'Lose'])
            else:
                win_count, lose_count = 0, 0

            # สร้างกราฟโดนัทแสดง Win/Loss ด้วย Plotly
            fig_winloss = go.Figure(go.Pie(
                labels=['Win (ชนะ)', 'Lose (แพ้)'],
                values=[win_count, lose_count],
                hole=0.5,
                marker_colors=['#26A69A', '#EF5350']
            ))
            fig_winloss.update_layout(height=250, margin=dict(l=20, r=20, t=30, b=20), showlegend=True)
            st.plotly_chart(fig_winloss, use_container_width=True)

        with col_right:
            # 2. สร้าง Gauge Chart (กราฟ Margin เดิมของคุณ)
            fig_gauge = go.Figure(go.Indicator(
                mode = "gauge+number",
                value = utilization,
                domain = {'x': [0, 1], 'y': [0, 1]},
                title = {'text': "Margin Utilization (%)"},
                gauge = {
                    'axis': {'range': [0, 100]},
                    'bar': {'color': "darkblue"},
                    'steps': [
                        {'range': [0, 50], 'color': "#26A69A"},
                        {'range': [50, 80], 'color': "#FBC02D"},
                        {'range': [80, 100], 'color': "#EF5350"}
                    ],
                    'threshold': {
                        'line': {'color': "white", 'width': 4},
                        'thickness': 0.75,
                        'value': utilization
                    }
                }
            ))

            fig_gauge.update_layout(height=250, margin=dict(l=20, r=20, t=50, b=20))
            st.plotly_chart(fig_gauge, use_container_width=True)

        st.divider()

        # 2. ส่วนของฟอร์มรับค่าการเทรด TFEX และการดึง ATR อัตโนมัติด้วยปุ่มกด
        with st.form("tfex_entry_form", clear_on_submit=True):
            st.subheader("🛡 คำนวณขนาดสัญญาและระบบ ATR Stop Loss")

            # ส่วนสำหรับกดปุ่มดึงค่า ATR ล่าสุด
            col_btn1, col_btn2 = st.columns([1, 2])
            with col_btn1:
                fetch_atr_clicked = st.form_submit_button("🔄 ดึงค่า ATR ล่าสุด")

            # จัดการเก็บค่า ATR ไว้ใน session_state เมื่อมีการกดปุ่ม
            if fetch_atr_clicked:
                with st.spinner("กำลังดึงข้อมูลราคาจากตลาด..."):
                    latest_atr = get_auto_atr_cached("^SET50")
                    st.session_state['active_atr'] = latest_atr
                    st.success(f"ดึงค่า ATR สำเร็จ: {latest_atr} จุด")

            # กำหนดค่า ATR เริ่มต้นหากยังไม่เคยกดปุ่ม (Default เป็น 6.5 หรือค่าล่าสุดใน session)
            default_atr = st.session_state.get('active_atr', 6.5)

            col1, col2, col3 = st.columns(3)
            with col1:
                date_open = st.date_input("วันที่เปิด")
                series = st.text_input("Series (เช่น S50U26)", value="S50U26")
                Status = st.selectbox("สถานะ:", ["Long", "Short"])
            with col2:
                entry = st.number_input("ราคา Open:", format="%.2f", value=950.0)
                size = st.number_input("จำนวนสัญญา:", min_value=1, value=1)
                trade_id_input = st.text_input("Trade ID (เว้นว่างเพื่อรันอัตโนมัติ):")  
            with col3:
                comm_input = st.number_input("ค่าคอมมิชชัน + ค่าธรรมเนียม (บาท):", min_value=0.0, step=10.0, value=50.0)

                # ⭐️ เพิ่มช่องให้พิมพ์แก้ไขค่า ATR ได้เอง (โดยดึงค่า default มาแสดง และยอมให้พิมพ์ทับได้เพื่อดูจาก TradingView)
                user_atr = st.number_input("ค่า ATR (แก้ไขได้):", min_value=0.1, step=0.1, value=float(default_atr))

                # ตัวคูณ ATR (Multiplier)
                atr_multiplier = st.number_input("ตัวคูณ ATR (Multiplier):", min_value=0.5, step=0.1, value=1.5)

                # คำนวณจุด SL จากค่า ATR ที่ผู้ใช้ใช้งานจริง (user_atr)
                calculated_sl_pts = user_atr * atr_multiplier
                st.write(f"📌 Stop Loss แนะนำ: **{calculated_sl_pts:.2f} จุด** (จาก ATR: {user_atr})")

                reason = st.text_area("เหตุผลที่เข้าเทรด:")

            # ปุ่มยืนยันการเปิดสถานะเทรดจริง
            submit_trade = st.form_submit_button("เปิดสถานะเทรด")

            if submit_trade:
                final_trade_id = trade_id_input.strip()
                if not final_trade_id:
                    final_trade_id = f"TX-{pd.Timestamp.now().strftime('%Y%m%d%H%M%S')}"

                # คำนวณราคา Stop Loss จริงบนกระดาน โดยใช้ calculated_sl_pts ที่คำนวณจาก user_atr
                calculated_sl_price = (entry - calculated_sl_pts) if Status == "Long" else (entry + calculated_sl_pts)

                required_columns = [
                    "Trade_ID", "Date_Open", "Date_Close", "Series", "Status", 
                    "Size", "Open_Price", "Close_Price", "Realized", 
                    "Comm", "Net_Profit", "Win_Lose", "Points", "Reason"
                ]

                # สร้าง Dictionary ใหม่ที่มั่นใจว่ามีครบทุกคอลัมน์ (เผื่ออนาคตมีการเพิ่ม/ลด)
                new_record = {
                    "Trade_ID": final_trade_id,
                    "Date_Open": date_open.strftime("%Y-%m-%d"),
                    "Date_Close": "",
                    "Series": series,
                    "Status": Status,
                    "Size": size,
                    "Open_Price": entry,
                    "Close_Price": 0,
                    "Realized": 0,
                    "Comm": comm_input,
                    "Net_Profit": 0,
                    "Win_Lose": "",
                    "Points": 0,  # เพิ่มคอลัมน์ Points ที่ขาดไปใน dictionary เดิม
                    "Reason": f"{reason} | ATR SL: {calculated_sl_price:.2f}"
                }

                # สร้าง DataFrame และ Reindex ให้ตรงเป๊ะ
                df_to_save = pd.DataFrame([new_record])
                df_to_save = df_to_save.reindex(columns=required_columns)

                with st.spinner("⏳ กำลังเปิดสถานะและบันทึกลง Google Sheets..."):
                    if save_data_to_sheet(df_to_save, "TFEX_History"):
                        st.cache_data.clear()
                        st.toast("เปิดสถานะเทรดเรียบร้อย! 🎉", icon="✅")
                        st.rerun()

    with sub_tfex_close:
        st.subheader("🏁 ปิดสถานะเทรด")

        # ดึงข้อมูลจากฟังก์ชัน load_data สดๆ ใหม่ๆ
        tfex_df = load_data("TFEX_History", get_active_sheet_name())
        # 🔧 แก้บั๊ก: มาตรฐานชื่อคอลัมน์เหมือนจุดอื่น เผื่อบางบัญชีบันทึกเป็น 'กำไรสุทธิ' แทน
        if not tfex_df.empty and 'Net_Profit' not in tfex_df.columns and 'กำไรสุทธิ' in tfex_df.columns:
            tfex_df = tfex_df.rename(columns={'กำไรสุทธิ': 'Net_Profit'})

        # ตรวจสอบว่ามีข้อมูลและคอลัมน์ที่จำเป็นอยู่ครบถ้วนหรือไม่
        if not tfex_df.empty and 'Close_Price' in tfex_df.columns:
            # แปลง Close_Price เป็นตัวเลข (ถ้าค่าว่าง, ไม่มี หรือเป็น 0 จะนับว่ายังไม่ปิดสถานะ)
            tfex_df['Close_Price_Cleaned'] = pd.to_numeric(tfex_df['Close_Price'], errors='coerce').fillna(0)
            open_trades = tfex_df[tfex_df['Close_Price_Cleaned'] == 0]
        else:
            open_trades = pd.DataFrame()

        if not open_trades.empty and 'Trade_ID' in open_trades.columns:
            # ให้เลือก Trade_ID
            selected_trade_id = st.selectbox("เลือก Trade ที่ต้องการปิด:", open_trades['Trade_ID'].tolist())

            # แสดงรายละเอียดออเดอร์เดิมให้เห็นก่อนปิด (ดึงตาม Header จริงของคุณ)
            trade_detail = open_trades[open_trades['Trade_ID'] == selected_trade_id].iloc[0]

            status_val = trade_detail.get('Status', 'N/A')
            size_val = trade_detail.get('Size', 0)
            open_price_val = trade_detail.get('Open_Price', 0)
            series_val = trade_detail.get('Series', 'N/A')

            st.info(f"🔍 รายละเอียด: ซีรีส์ **{series_val}** | สถานะ: **{status_val}** | จำนวน: **{size_val}** สัญญา | ราคาเปิด: **{open_price_val}**")

            # ฟอร์มกรอกข้อมูลปิดสถานะ
            c_col1, c_col2 = st.columns(2)

            # แปลง Open_Price เป็น float สำหรับค่าเริ่มต้นใน number_input
            default_open_price = pd.to_numeric(open_price_val, errors='coerce')
            if pd.isna(default_open_price):
                default_open_price = 0.0

            close_price = c_col1.number_input("ราคาปิด (Close_Price):", value=float(default_open_price), step=0.1, format="%.2f")
            close_date = c_col2.date_input("วันที่ปิด (Date_Close):")

            if st.button("ยืนยันการปิดสถานะ", use_container_width=True, type="primary"):
                # บันทึกปิดสถานะพร้อม Loading Spinner และล้าง Cache ทันที
                with st.spinner("⏳ กำลังบันทึกการปิดสถานะและคำนวณผลลัพธ์..."):
                    # ส่งค่าไปอัปเดต (ตรวจสอบให้แน่ใจว่าฟังก์ชัน update_trade_close รับพารามิเตอร์ตามนี้)
                    # 🔧 แก้บั๊ก: เดิมส่ง ID ของ Google Sheet ตายตัวเป็นพารามิเตอร์แรก ตอนนี้ฟังก์ชันเปิดชีต
                    # ตามผู้ใช้ที่ login เองแล้ว จึงไม่ต้องส่ง ID มาจากตรงนี้อีกต่อไป
                    success = update_trade_close(selected_trade_id, close_price, str(close_date))

                    if success:
                        st.cache_data.clear()  # ล้าง Cache ข้อมูลในหน่วยความจำ
                        st.toast("ปิดสถานะสำเร็จ และคำนวณกำไรเรียบร้อย! 🏁", icon="🏆")
                        st.rerun()             # โหลดหน้าจอใหม่เพื่อให้ข้อมูลปัจจุบันที่สุดแสดงทันที
                    else:
                        st.error("เกิดข้อผิดพลาดในการบันทึกข้อมูลลงฐานข้อมูล กรุณาลองใหม่อีกครั้ง")
        else:
            st.info("ไม่มีรายการที่ถือครองอยู่ครับ (ไม่พบรายการที่ Close_Price เป็นค่าว่างหรือ 0)")

    with sub_tfex_cash:
        st.subheader("💰 บันทึกเติม/ถอนเงิน")

        with st.form("cash_flow"):
            col1, col2 = st.columns(2)
            with col1:
                cash_date = st.date_input("วันที่:")
                cash_type = st.selectbox("ประเภท:", ["Deposit", "Withdraw"])
            with col2:
                amount = st.number_input("จำนวนเงิน (บาท):", min_value=0.0, step=100.0)
                note = st.text_input("หมายเหตุ:")

            if st.form_submit_button("บันทึกรายการ"):
                new_cash = pd.DataFrame([{
                    "Date": str(cash_date),
                    "Type": cash_type,
                    "Amount": amount,
                    "Note": note
                }])
                if save_cash_to_gsheet(new_cash, "Cash_Flow"):
                    st.success("บันทึกข้อมูลเงินเรียบร้อย!")
                    st.rerun()

        st.divider()
        st.write("รายการล่าสุด:")
        st.dataframe(cash_df, use_container_width=True)

    with sub_tfex_history:
        st.subheader("📜 ประวัติการเทรดและกำไรสะสม")

        if not tfex_df.empty and 'Net_Profit' in tfex_df.columns and 'Close_Price' in tfex_df.columns:
            # 1. จัดเตรียมข้อมูล
            # แปลงคอลัมน์ Close_Price เป็นตัวเลขก่อนเปรียบเทียบ > 0 ป้องกัน TypeError
            close_prices_5154 = pd.to_numeric(tfex_df['Close_Price'], errors='coerce').fillna(0)
            closed_trades = tfex_df[close_prices_5154 > 0].copy()

            # 3. ตารางแสดงราย Series (เปรียบเทียบว่า Series ไหนเทรดแล้วกำไรที่สุด)
            st.write("📊 สรุปผลงานราย Series:")
            series_perf = perf_df.groupby('Series').agg({
                'Net_Profit': 'sum',
                'Trade_ID': 'count'
            }).rename(columns={'Trade_ID': 'Trades', 'Net_Profit': 'Total PnL'})

            st.dataframe(series_perf.sort_values(by='Total PnL', ascending=False), use_container_width=True)

            # --- กราฟแสดงการเติบโตของพอร์ต TFEX ---
            st.subheader("📈 กราฟการเติบโตของพอร์ต (Portfolio Growth)")

            if not perf_df.empty:
                # 1. ทำตัวเลือกช่วงเวลา (Quick Filter) สำหรับกราฟ TFEX
                c_f1, c_f2 = st.columns([2, 2])
                with c_f1:
                    tfex_view_range = st.selectbox(
                        "⏳ เลือกช่วงเวลาแสดงผล (TFEX):",
                        ["ทั้งหมด (All Time)", "3 เดือนล่าสุด", "6 เดือนล่าสุด", "1 ปีล่าสุด (YTD / 12M)"],
                        key="tfex_line_view_range"
                    )

                # แปลงคอลัมน์วันที่ให้เป็น datetime
                perf_df['Date_Close'] = pd.to_datetime(perf_df['Date_Close'], errors='coerce')
                df_tfex_filtered = perf_df.dropna(subset=['Date_Close']).sort_values('Date_Close').copy()

                max_date = df_tfex_filtered['Date_Close'].max()
                initial_capital_base = net_capital  # เงินต้นเริ่มต้น

                # กรองข้อมูลตามช่วงเวลาที่เลือก และคำนวณกำไรย้อนหลังที่ถูกตัดออกไปรวมกับฐานเงินต้น
                if tfex_view_range == "3 เดือนล่าสุด":
                    start_date = max_date - pd.DateOffset(months=3)
                    past_slice = df_tfex_filtered[df_tfex_filtered['Date_Close'] < start_date]
                    initial_capital_base += past_slice['Net_Profit'].sum()
                    df_tfex_filtered = df_tfex_filtered[df_tfex_filtered['Date_Close'] >= start_date]
                elif tfex_view_range == "6 เดือนล่าสุด":
                    start_date = max_date - pd.DateOffset(months=6)
                    past_slice = df_tfex_filtered[df_tfex_filtered['Date_Close'] < start_date]
                    initial_capital_base += past_slice['Net_Profit'].sum()
                    df_tfex_filtered = df_tfex_filtered[df_tfex_filtered['Date_Close'] >= start_date]
                elif tfex_view_range == "1 ปีล่าสุด (YTD / 12M)":
                    start_date = max_date - pd.DateOffset(years=1)
                    past_slice = df_tfex_filtered[df_tfex_filtered['Date_Close'] < start_date]
                    initial_capital_base += past_slice['Net_Profit'].sum()
                    df_tfex_filtered = df_tfex_filtered[df_tfex_filtered['Date_Close'] >= start_date]

                if not df_tfex_filtered.empty:
                    # 2. Dynamic Aggregation: ถ้าระยะเวลานานกว่า 1 ปี ให้ยุบกลุ่มเป็น "รายเดือน" เพื่อความสะอาดของกราฟ
                    date_span_days = (df_tfex_filtered['Date_Close'].max() - df_tfex_filtered['Date_Close'].min()).days

                    if date_span_days > 365 and tfex_view_range == "ทั้งหมด (All Time)":
                        df_tfex_filtered['Period_Key'] = df_tfex_filtered['Date_Close'].dt.to_period('M')
                        df_tfex_filtered['Time_Label'] = df_tfex_filtered['Period_Key'].apply(lambda r: r.strftime('%b %Y'))
                        df_tfex_filtered['Sort_Time'] = df_tfex_filtered['Period_Key'].dt.start_time
                        agg_freq_text = "รายเดือน (มุมมองระยะยาว)"
                    else:
                        df_tfex_filtered['Period_Key'] = df_tfex_filtered['Date_Close'].dt.to_period('W-MON')
                        df_tfex_filtered['Time_Label'] = df_tfex_filtered['Period_Key'].apply(lambda r: f"W{r.week} {r.start_time.strftime('%b %Y')}")
                        df_tfex_filtered['Sort_Time'] = df_tfex_filtered['Period_Key'].dt.start_time
                        agg_freq_text = "รายสัปดาห์ (เจาะลึก)"

                    with c_f2:
                        st.markdown(f"<p style='padding-top:28px; color:gray; font-size:13px;'>ℹ️ ความละเอียด: <b>{agg_freq_text}</b></p>", unsafe_allow_html=True)

                    # รวมกำไรตามช่วงเวลาที่จัดกลุ่ม
                    growth_df = df_tfex_filtered.groupby(['Sort_Time', 'Time_Label'], as_index=False).agg({
                        'Net_Profit': 'sum'
                    }).sort_values('Sort_Time')

                    # คำนวณมูลค่าพอร์ตสะสม
                    growth_df['Cumulative_Profit'] = growth_df['Net_Profit'].cumsum()
                    growth_df['Portfolio_Value'] = initial_capital_base + growth_df['Cumulative_Profit']

                    # เพิ่มจุดเริ่มต้น (Start Point) ให้กราฟเริ่มสวยงามที่ฐานเงินต้น
                    start_date_point = growth_df['Sort_Time'].min() - pd.Timedelta(days=1)
                    start_row = pd.DataFrame({
                        'Sort_Time': [start_date_point], 
                        'Time_Label': ['จุดเริ่มต้น'], 
                        'Portfolio_Value': [initial_capital_base]
                    })
                    growth_df = pd.concat([start_row, growth_df[['Sort_Time', 'Time_Label', 'Portfolio_Value']]], ignore_index=True)
                    growth_df = growth_df.sort_values('Sort_Time').reset_index(drop=True)

                    # 3. สร้างกราฟเส้นด้วย Plotly
                    fig_growth = px.line(
                        growth_df, 
                        x='Time_Label', 
                        y='Portfolio_Value',
                        markers=True,
                        line_shape='spline'
                    )

                    # ปรับแต่งหน้าตาให้ดูมืออาชีพ พร้อมเผื่อสเกลแกน Y ด้านบนไม่ให้เส้นชนขอบ
                    y_max = growth_df['Portfolio_Value'].max()
                    y_min = growth_df['Portfolio_Value'].min()
                    y_upper_margin = (y_max - y_min) * 0.15 if y_max != y_min else y_max * 0.15

                    fig_growth.update_traces(line=dict(color='#26A69A', width=3))
                    fig_growth.update_layout(
                        xaxis_title="ช่วงเวลา",
                        yaxis_title="มูลค่าพอร์ต (บาท)",
                        yaxis=dict(range=[y_min * 0.98, y_max + y_upper_margin]),
                        margin=dict(l=20, r=20, t=30, b=20),
                        hovermode="x unified"
                    )

                    st.plotly_chart(fig_growth, use_container_width=True)
                else:
                    st.info("ไม่มีข้อมูลในช่วงเวลาที่เลือก")
            else:
                st.info("ยังไม่มีข้อมูลประวัติการเทรด TFEX ที่ปิดสถานะ")

            # --- สรุปผลรายเดือนแบบ Combo Chart & Table ---
            st.divider()
            st.subheader("🗓 สรุปผลรายเดือน")
            if not closed_trades.empty:
                # 1. เพิ่มตัวเลือกช่วงเวลา (Quick Filter) สำหรับสรุปผลรายเดือน
                col_f1, col_f2 = st.columns([2, 2])
                with col_f1:
                    monthly_view_range = st.selectbox(
                        "⏳ เลือกช่วงเวลาแสดงผล (สรุปรายเดือน):",
                        ["ทั้งหมด (All Time)", "3 เดือนล่าสุด", "6 เดือนล่าสุด", "1 ปีล่าสุด (YTD / 12M)"],
                        key="monthly_view_range"
                    )

                # แปลงคอลัมน์วันที่ให้เป็น datetime และสำเนาข้อมูล
                closed_trades['Date_Close'] = pd.to_datetime(closed_trades['Date_Close'], errors='coerce')
                df_monthly_filtered = closed_trades.dropna(subset=['Date_Close']).sort_values('Date_Close').copy()

                max_date = df_monthly_filtered['Date_Close'].max()
                capital_base_for_monthly = net_capital  # เงินต้นเริ่มต้น

                # กรองข้อมูลตามช่วงเวลาที่ผู้ใช้เลือก
                if monthly_view_range == "3 เดือนล่าสุด":
                    start_date = max_date - pd.DateOffset(months=3)
                    past_slice = df_monthly_filtered[df_monthly_filtered['Date_Close'] < start_date]
                    capital_base_for_monthly += past_slice['Net_Profit'].sum()
                    df_monthly_filtered = df_monthly_filtered[df_monthly_filtered['Date_Close'] >= start_date]
                elif monthly_view_range == "6 เดือนล่าสุด":
                    start_date = max_date - pd.DateOffset(months=6)
                    past_slice = df_monthly_filtered[df_monthly_filtered['Date_Close'] < start_date]
                    capital_base_for_monthly += past_slice['Net_Profit'].sum()
                    df_monthly_filtered = df_monthly_filtered[df_monthly_filtered['Date_Close'] >= start_date]
                elif monthly_view_range == "1 ปีล่าสุด (YTD / 12M)":
                    start_date = max_date - pd.DateOffset(years=1)
                    past_slice = df_monthly_filtered[df_monthly_filtered['Date_Close'] < start_date]
                    capital_base_for_monthly += past_slice['Net_Profit'].sum()
                    df_monthly_filtered = df_monthly_filtered[df_monthly_filtered['Date_Close'] >= start_date]

                if not df_monthly_filtered.empty:
                    # 2. จัดเตรียมและคำนวณค่าต่างๆ ตามข้อมูลที่ถูกกรอง
                    monthly_perf = df_monthly_filtered.groupby(df_monthly_filtered['Date_Close'].dt.to_period('M'))['Net_Profit'].sum().reset_index()
                    monthly_perf['Month'] = monthly_perf['Date_Close'].dt.strftime('%Y-%m')

                    # คำนวณค่าสถิติต่างๆ ต่อเนื่อง
                    monthly_perf['Cumulative_Profit'] = monthly_perf['Net_Profit'].cumsum()
                    monthly_perf['Portfolio_Value'] = capital_base_for_monthly + monthly_perf['Cumulative_Profit']
                    monthly_perf['Monthly_Return_Pct'] = (monthly_perf['Net_Profit'] / capital_base_for_monthly) * 100
                    monthly_perf['Cumulative_Pct'] = (monthly_perf['Cumulative_Profit'] / capital_base_for_monthly) * 100

                    # 3. คำนวณสเกลแกน Y ให้เผื่อ Gap ทั้งบนและล่าง (ป้องกันแท่งกราฟชนขอบ)
                    y1_min = monthly_perf['Net_Profit'].min()
                    y1_max = monthly_perf['Net_Profit'].max()
                    # เผื่อสเกลแกน Y ฝั่งซ้าย (Net Profit) ขึ้น/ลง 20%
                    y1_padding = (y1_max - y1_min) * 0.2 if y1_max != y1_min else abs(y1_max) * 0.2
                    if y1_padding == 0: y1_padding = 1000
                    y1_range = [min(0, y1_min) - y1_padding, y1_max + y1_padding]

                    y2_min = monthly_perf['Cumulative_Pct'].min()
                    y2_max = monthly_perf['Cumulative_Pct'].max()
                    # เผื่อสเกลแกน Y ฝั่งขวา (% สะสม) ขึ้น/ลง 20%
                    y2_padding = (y2_max - y2_min) * 0.2 if y2_max != y2_min else abs(y2_max) * 0.2
                    if y2_padding == 0: y2_padding = 5
                    y2_range = [min(0, y2_min) - y2_padding, y2_max + y2_padding]

                    # 4. วาดกราฟ Plotly Combo
                    bar_colors = ['#26A69A' if val >= 0 else '#EF5350' for val in monthly_perf['Net_Profit']]
                    fig = make_subplots(specs=[[{"secondary_y": True}]])

                    fig.add_trace(go.Bar(x=monthly_perf['Month'], y=monthly_perf['Net_Profit'], name="กำไร/ขาดทุน", marker_color=bar_colors), secondary_y=False)
                    fig.add_trace(go.Scatter(x=monthly_perf['Month'], y=monthly_perf['Cumulative_Pct'], name="% สะสม", mode='lines+markers', line=dict(color='#FFA500', width=3)), secondary_y=True)

                    fig.update_layout(
                        title_text=f"Monthly Performance ({monthly_view_range})", 
                        height=400, 
                        margin=dict(l=20, r=20, t=40, b=20), 
                        showlegend=True
                    )

                    # กำหนดช่วงสเกลแกน Y ทั้งสองฝั่งให้มีระยะห่าง (Gap)
                    fig.update_yaxes(title_text="กำไร/ขาดทุน (บาท)", range=y1_range, secondary_y=False)
                    fig.update_yaxes(title_text="% สะสม", range=y2_range, secondary_y=True)

                    st.plotly_chart(fig, use_container_width=True)

                    # 5. สร้างตารางสรุป
                    def color_negative_red(val):
                        if isinstance(val, (int, float)):
                            color = '#26A69A' if val > 0 else '#EF5350' if val < 0 else 'black'
                            return f'color: {color}'
                        return None

                    monthly_df = monthly_perf[['Month', 'Net_Profit', 'Monthly_Return_Pct', 'Portfolio_Value', 'Cumulative_Pct']]
                    monthly_df.columns = ['เดือน', 'กำไร/ขาดทุน (บาท)', '% รายเดือน', 'มูลค่าพอร์ต (บาท)', '% สะสม']

                    # --- CSS สำหรับจัดตารางให้ชิดขวา ---
                    styled_df = monthly_df.style.format({
                        'กำไร/ขาดทุน (บาท)': '{:,.2f}',
                        '% รายเดือน': '{:+.2f} %', 
                        'มูลค่าพอร์ต (บาท)': '{:,.2f}',
                        '% สะสม': '{:+.2f} %'
                    }) \
                    .map(color_negative_red, subset=['กำไร/ขาดทุน (บาท)', '% รายเดือน', '% สะสม']) \
                    .set_properties(**{'text-align': 'right'}) \
                    .set_table_styles([
                        {'selector': 'th', 'props': [('text-align', 'right')]},
                        {'selector': 'td', 'props': [('text-align', 'right')]}
                    ])

                    # แสดงตารางผ่าน styled_df
                    st.dataframe(styled_df, use_container_width=True)
                else:
                    st.warning("ไม่มีข้อมูลรายการเทรดในช่วงเวลาที่เลือกครับ")
            else:
                st.warning("ยังไม่มีข้อมูลรายการเทรดที่ปิดสถานะแล้วครับ")
