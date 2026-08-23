# =============================================================
# tab_risk.py
# แท็บ Risk Management & Position Sizing (Phase 2 ของการแยกไฟล์)
# =============================================================
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from constants import SET100_TICKERS
from backend_functions import calculate_total_portfolio_value, get_total_market_value, load_total_cash_balance
from theme import render_metric_card


def render_tab_risk():
    st.markdown("#### 🚀 ระบบคำนวณ Risk Management & Position Sizing")

    # --- 1. ส่วนเลือก/พิมพ์ชื่อหุ้น (ผูก Key ตามตัวแปรหุ้นเพื่อบังคับ Refresh Widget) ---
    all_tickers = [t.replace('.BK', '') for t in SET100_TICKERS] if 'SET100_TICKERS' in globals() else ["KBANK", "PTT", "SCB", "CPALL", "PTTEP"]
    current_selected = st.session_state.get("selected_ticker", "KBANK")

    # 🟢 เทคนิคสำคัญ: ใส่ชื่อหุ้นลงไปใน Key ด้วย เพื่อป้องกัน Streamlit จำค่าเก่า
    risk_ticker_input = st.selectbox(
        "🔍 เลือกหรือพิมพ์ชื่อหุ้นที่ต้องการคำนวณความเสี่ยง:",
        options=all_tickers,
        index=all_tickers.index(current_selected) if current_selected in all_tickers else 0,
        key=f"risk_stock_selectbox_{current_selected}"
    )

    if risk_ticker_input != current_selected:
        st.session_state.selected_ticker = risk_ticker_input
        st.rerun()

    st.divider()

    # --- 2. ฟังก์ชันดึงข้อมูลแบบแยก Cache เฉพาะตัว ---
    @st.cache_data(ttl=60)
    def fetch_risk_data_unique(ticker_symbol):
        df = yf.download(ticker_symbol, period="3mo", interval="1d", progress=False)
        if not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df['EMA10'] = df['Close'].ewm(span=10, adjust=False).mean()
            df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
            return {
                "price": float(df['Close'].iloc[-1]),
                "ema10": float(df['EMA10'].iloc[-1]),
                "ema20": float(df['EMA20'].iloc[-1])
            }
        return None

    ticker_symbol = f"{st.session_state.selected_ticker}.BK"
    risk_data = fetch_risk_data_unique(ticker_symbol)

    if risk_data:
        current_p = risk_data["price"]
        ema10_val = risk_data["ema10"]
        ema20_val = risk_data["ema20"]
    else:
        st.warning(f"ไม่พบข้อมูลของหุ้น {st.session_state.selected_ticker}")
        st.stop()

    # --- 3. แสดงสถานะพอร์ตปัจจุบัน ---
    if "cash_balance" not in st.session_state:
        st.session_state.cash_balance = load_total_cash_balance()

    cash_balance = st.session_state.cash_balance
    market_value = get_total_market_value()
    total_equity = cash_balance + market_value

    st.markdown(f"##### 💰 สรุปสถานะพอร์ตปัจจุบัน (กำลังวิเคราะห์หุ้น: **{st.session_state.selected_ticker}**)")
    col_a, col_b, col_c = st.columns(3)
    render_metric_card(col_a, "เงินสดคงเหลือ", f"{cash_balance:,.0f} ฿", icon="💵")
    render_metric_card(col_b, "มูลค่าหุ้นที่ถือ", f"{market_value:,.0f} ฿", icon="📈")
    render_metric_card(col_c, "มูลค่าพอร์ตสุทธิ", f"{total_equity:,.0f} ฿", icon="💰")

    st.divider()

    # --- 4. เตรียมข้อมูล Stop Loss และ Slider ---
    r_col1, r_col2 = st.columns([1, 1])

    with r_col1:
        max_alloc_pct = st.slider("1. สัดส่วนเงินลงทุนสูงสุดสำหรับไม้ซื้อนี้ (% ของพอร์ต):", min_value=5.0, max_value=100.0, value=20.0, step=5.0, key=f"risk_alloc_{st.session_state.selected_ticker}")
        max_budget = total_equity * (max_alloc_pct / 100.0)
        effective_budget = min(max_budget, cash_balance)
        st.info(f"💡 วงเงินสูงสุดสำหรับไม้นี้: **{effective_budget:,.0f} ฿**")

        risk_pct = st.slider("2. ความเสี่ยงสูงสุดต่อไม้ (% ของพอร์ต):", min_value=0.25, max_value=3.0, value=1.0, step=0.25, key=f"risk_pct_{st.session_state.selected_ticker}")

    with r_col2:
        st.markdown(f"📌 **ราคาปัจจุบันของ {st.session_state.selected_ticker}:** `{current_p:,.2f} ฿`")

        sl_options = [
            f"เส้น EMA 10 ({ema10_val:.2f} บาท)",
            f"เส้น EMA 20 ({ema20_val:.2f} บาท)",
            "กำหนดเป็นเปอร์เซ็นต์คงที่ (Fixed %)",
            "กำหนดราคาคัทด้วยตัวเอง (Manual Price)"
        ]
        sl_type = st.selectbox("3. เลือกเกณฑ์จุดตัดขาดทุน (Stop Loss):", sl_options, key=f"final_sl_type_{st.session_state.selected_ticker}")

        if "EMA 10" in sl_type:
            sl_price = ema10_val
        elif "EMA 20" in sl_type:
            sl_price = ema20_val
        elif "กำหนดเป็นเปอร์เซ็นต์คงที่" in sl_type:
            fixed_sl_pct = st.slider("ระบุ % Stop Loss:", min_value=2.0, max_value=12.0, value=7.0, step=0.5, key=f"risk_fixed_sl_{st.session_state.selected_ticker}")
            sl_price = current_p * (1 - (fixed_sl_pct / 100))
        else: 
            sl_price = st.number_input("ระบุราคา Stop Loss (บาท):", min_value=0.0, value=float(current_p * 0.93), step=0.25, key=f"risk_manual_sl_{st.session_state.selected_ticker}")

    # --- 5. คำนวณผลลัพธ์ ---
    max_risk_money = total_equity * (risk_pct / 100) 
    risk_per_share = current_p - sl_price

    if risk_per_share <= 0:
        st.error("⚠️ ราคา Stop Loss ต้องต่ำกว่าราคาซื้อปัจจุบันครับ!")
    else:
        shares_by_risk = max_risk_money / risk_per_share       
        shares_by_budget = effective_budget / current_p         
        shares_to_buy = int(min(shares_by_risk, shares_by_budget))
        total_buy_value = shares_to_buy * current_p

        st.markdown("##### 📊 ผลลัพธ์หน้าเทรดและขนาดไม้ที่เหมาะสม:")
        res_col1, res_col2, res_col3, res_col4 = st.columns(4)
        render_metric_card(res_col1, "จำนวนที่ควรซื้อ", f"{shares_to_buy:,} หุ้น", icon="🛒")
        render_metric_card(res_col2, "เงินลงทุน (Position Size)", f"{total_buy_value:,.0f} ฿", icon="📥")
        render_metric_card(res_col3, "ตั้ง SL ที่ราคา", f"{sl_price:.2f} ฿", icon="🛑")
        render_metric_card(res_col4, "เสียเงินสูงสุดหากแพ้", f"{max_risk_money:,.0f} ฿", icon="⚠️")

        if total_buy_value > cash_balance:
            st.warning(f"⚠️ เงินลงทุนที่คำนวณได้สูงกว่าเงินสดคงเหลือในพอร์ต")
        else:
            st.success(f"✅ วงเงินและเงินสดในพอร์ตเพียงพอสำหรับการซื้อไม้นี้")

#######################          
    st.markdown("---")
    st.markdown("##### 🛡️ การบริหารความเสี่ยง (Risk Monitoring)")

    # 1. ดึงข้อมูลจาก journal_data มาแปลงเป็น DataFrame
    if 'journal_data' in st.session_state and st.session_state.journal_data:
        df_filtered = pd.DataFrame(st.session_state.journal_data)
    else:
        df_filtered = pd.DataFrame()

    # แปลงคอลัมน์ 'กำไร/ขาดทุน (บาท)' ให้เป็นตัวเลขอย่างปลอดภัย (กันกรณีมีคอมมาหรือข้อความปน)
    if not df_filtered.empty and 'กำไร/ขาดทุน (บาท)' in df_filtered.columns:
        df_filtered['กำไร/ขาดทุน (บาท)'] = pd.to_numeric(
            df_filtered['กำไร/ขาดทุน (บาท)'].astype(str).str.replace(',', ''), 
            errors='coerce'
        ).fillna(0)

    # 2. คำนวณ Exposure
    total_market_val = calculate_total_portfolio_value() 
    current_cash = st.session_state.get('cash_balance', 0.0)
    total_equity = total_market_val + current_cash

    exposure_pct = (total_market_val / total_equity) * 100 if total_equity > 0 else 0

    # 3. คำนวณ Expectancy และแยกไม้ชนะ/แพ้
    if not df_filtered.empty and 'กำไร/ขาดทุน (บาท)' in df_filtered.columns:
        wins = df_filtered[df_filtered['กำไร/ขาดทุน (บาท)'] > 0]
        losses = df_filtered[df_filtered['กำไร/ขาดทุน (บาท)'] <= 0]

        win_rate = len(wins) / len(df_filtered) if len(df_filtered) > 0 else 0
        avg_win = wins['กำไร/ขาดทุน (บาท)'].mean() if len(wins) > 0 else 0
        avg_loss = abs(losses['กำไร/ขาดทุน (บาท)'].mean()) if len(losses) > 0 else 0
        loss_rate = 1 - win_rate

        expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)
    else:
        win_rate = 0.0
        avg_win = 0.0
        avg_loss = 0.0
        loss_rate = 0.0
        expectancy = 0.0

    # 3. แสดงผลด้วยการ์ด
    col_r1, col_r2 = st.columns(2)
    render_metric_card(col_r1, "Market Exposure", f"{exposure_pct:.1f}%", icon="📊")
    render_metric_card(col_r2, "Expectancy (ต่อไม้)", f"{expectancy:,.0f} ฿", icon="🧮")


    # --- 1. ประกาศฟังก์ชันไว้ด้านบน (ห้ามย่อหน้า) ---
    def calculate_strategy(win_rate, profit_pct, loss_pct, trades=30, initial_capital=100000):
        fixed_capital = initial_capital
        fixed_balance = initial_capital
        comp_balance = initial_capital

        for i in range(trades):
            win = np.random.rand() < win_rate
            # คำนวณแบบไม่ทบต้น
            fixed_profit = (profit_pct * fixed_capital) if win else (-loss_pct * fixed_capital)
            fixed_balance += fixed_profit
            # คำนวณแบบทบต้น
            comp_profit = (profit_pct * comp_balance) if win else (-loss_pct * comp_balance)
            comp_balance += comp_profit

        return fixed_balance, comp_balance

    def show_strategy_analysis():
        st.header("📊 ตารางเปรียบเทียบกลยุทธ์: ทบต้น vs ไม่ทบต้น")
        initial_cap = 100000
        loss_pct = 0.08
        trades = 30
        win_rates = [0.4, 0.5, 0.6]
        profit_pcts = [0.10, 0.12, 0.14, 0.16]

        data = []
        for wr in win_rates:
            for pr in profit_pcts:
                wins = trades * wr
                losses = trades * (1 - wr)
                fixed_profit = (wins * pr * initial_cap) - (losses * loss_pct * initial_cap)

                comp_cap = initial_cap
                for i in range(trades):
                    if np.random.rand() < wr: comp_cap *= (1 + pr)
                    else: comp_cap *= (1 - loss_pct)

                data.append({
                    "Win Rate": f"{int(wr*100)}%",
                    "Profit %": f"{int(pr*100)}%",
                    "ไม่ทบต้น (กำไร)": f"{fixed_profit:,.0f}",
                    "ทบต้น (กำไร)": f"{comp_cap - initial_cap:,.0f}",
                    "กลยุทธ์ที่แนะนำ": "ทบต้น" if comp_cap > (initial_cap + fixed_profit) else "ไม่ทบต้น"
                })
        st.table(pd.DataFrame(data))

    # --- ส่วนแสดงผลความเสี่ยง ทบต้น VS ไม่ทบต้น ---
    st.markdown("---")

    st.header("🧮 วิเคราะห์ความเสี่ยงและกลยุทธ์ ทบต้น VS ไม่ทบต้น")

    # เพิ่มส่วนเลือกช่วงเวลา
    time_period = st.radio(
        "เลือกช่วงเวลาที่ต้องการวิเคราะห์:",
        ["1 เดือน", "3 เดือน", "6 เดือน", "1 ปี", "Overall"],
        horizontal=True
    )

    if "journal_data" in st.session_state and st.session_state.journal_data:
        df_journal = pd.DataFrame(st.session_state.journal_data)
        # ตรวจสอบว่าคอลัมน์วันที่เป็น datetime
        df_journal['วันที่ขาย'] = pd.to_datetime(df_journal['วันที่ขาย'], errors='coerce')

        # คำนวณวันย้อนหลังตามช่วงเวลา
        today = pd.Timestamp.now()
        if time_period == "1 เดือน": filter_date = today - pd.Timedelta(days=30)
        elif time_period == "3 เดือน": filter_date = today - pd.Timedelta(days=90)
        elif time_period == "6 เดือน": filter_date = today - pd.Timedelta(days=180)
        elif time_period == "1 ปี": filter_date = today - pd.Timedelta(days=365)
        else: filter_date = pd.Timestamp('1900-01-01') # Overall

        # กรองข้อมูล
        df_filtered = df_journal[df_journal['วันที่ขาย'] >= filter_date].copy()

        if not df_filtered.empty:
            # --- ปรับ Logic การคำนวณให้ใช้ข้อมูลทั้งหมดที่กรองได้ ---
            # คำนวณ ROI% เองโดยตรงจาก df_filtered
            df_filtered['ROI_Percent'] = (df_filtered['กำไร/ขาดทุน (บาท)'] / df_filtered['ต้นทุน (บาท)'].replace(0, np.nan)) * 100

            total_trades = len(df_filtered)
            win_trades = df_filtered[df_filtered['ROI_Percent'] > 0]
            loss_trades = df_filtered[df_filtered['ROI_Percent'] <= 0]

            win_rate_val = (len(win_trades) / total_trades) * 100
            avg_profit_val = win_trades['ROI_Percent'].mean() if not win_trades.empty else 0
            avg_loss_val = abs(loss_trades['ROI_Percent'].mean()) if not loss_trades.empty else 0
            rr_ratio = (avg_profit_val / avg_loss_val) if avg_loss_val != 0 else 0

            # แสดงผล
            col1, col2, col3 = st.columns(3)
            render_metric_card(col1, "Win Rate", f"{win_rate_val:.1f}%", icon="🎯")
            render_metric_card(col2, "R:R Ratio", f"{rr_ratio:.2f} : 1", icon="📏")
            render_metric_card(col3, "กลยุทธ์แนะนำ", "ทบต้น" if win_rate_val >= 45 and rr_ratio >= 1.5 else "ไม่ทบต้น", icon="🧭")

            st.write(f"ผลงานรวมในช่วง {time_period} (ทั้งหมด **{total_trades} ไม้**):")
        else:
            st.warning("ไม่มีข้อมูลการเทรดในช่วงเวลาที่เลือก")

    st.divider()

    # --- 3. ตารางเปรียบเทียบ (แบบซ่อนได้) ---
    with st.expander("📊 ดูตาราง Simulation เทียบเคียง"):
        # 1. ดึงข้อมูลจาก df_period มาคำนวณแบบสดๆ ตรงนี้เลย เพื่อความชัวร์ (ไม่ให้ไปดึงตัวแปรเก่าข้างนอกมาปน)
        if 'df_period' in locals() and not df_period.empty:
            col_pl_sim = 'กำไร/ขาดทุน (บาท)'
            col_cost_sim = 'ต้นทุน (บาท)'

            # คำนวณ Win Rate สดๆ
            wr_val = (df_period[col_pl_sim] > 0).mean() * 100

            # คำนวณ Avg Profit สดๆ
            p_mask = (df_period[col_pl_sim] > 0) & (df_period[col_cost_sim] > 0)
            p_series = (df_period.loc[p_mask, col_pl_sim] / df_period.loc[p_mask, col_cost_sim]) * 100
            pr_val = p_series.clip(upper=500).mean() if not p_series.empty else 10.0 # ค่าสำรองถ้าไม่มีข้อมูล

            # คำนวณ Avg Loss สดๆ (และบังคับให้เป็นบวกทันทีด้วย abs)
            l_mask = (df_period[col_pl_sim] <= 0) & (df_period[col_cost_sim] > 0)
            l_series = (df_period.loc[l_mask, col_pl_sim] / df_period.loc[l_mask, col_cost_sim]) * 100
            l_series = l_series[l_series >= -100] # กรองค่าเพี้ยน
            ls_val = abs(l_series.mean()) if not l_series.empty else 5.0 # ค่าสำรองถ้าไม่มีข้อมูล
        else:
            # ค่า Default เผื่อกรณีไม่มีข้อมูลในช่วงเวลานั้น
            wr_val, pr_val, ls_val = 50.0, 10.0, 5.0

        act_wr = wr_val / 100.0
        act_profit = pr_val / 100.0
        act_loss = ls_val / 100.0  # ตอนนี้ ls_val จะเป็นค่าบวกปกติ (เช่น 7.49%) หาร 100 จะได้ 0.0749

        # 2. สร้าง Range สำหรับจำลองตาราง
        wr_range = [act_wr - 0.10, act_wr - 0.05, act_wr, act_wr + 0.05, act_wr + 0.10]
        pr_range = [act_profit - 0.05, act_profit - 0.025, act_profit, act_profit + 0.025, act_profit + 0.05]

        sim_data = []
        for wr in wr_range:
            wr_display = max(0.0, min(1.0, wr)) 
            row = {"Win Rate": f"{wr_display*100:.1f}%"}
            for pr in pr_range:
                # คำนวณ Expected Value (EV) 
                ev = (wr_display * pr) - ((1.0 - wr_display) * act_loss)

                # แปลงค่า EV กลับเป็นเปอร์เซ็นต์ (%)
                row[f"{pr*100:.1f}% Profit"] = ev * 100 

            sim_data.append(row)

        # 3. เตรียมข้อมูลและเซต Index
        df_full = pd.DataFrame(sim_data)
        df_full = df_full.set_index("Win Rate")

        # 4. แปลงข้อมูลเป็นตัวเลขเพื่อทำ Style
        df_numeric = df_full.astype(float)

        # 5. สร้าง Styler และจัด Format เป็น %
        st_table = df_numeric.style.background_gradient(cmap="RdYlGn", axis=None).format("{:.2f}%")

        # 6. แสดงผลผ่านตาราง
        st.dataframe(st_table, use_container_width=True)

        st.caption(f"ตารางแสดง Expected Return (%) ต่อไม้ โดยอ้างอิงจาก Avg Loss ฐานข้อมูลที่ {ls_val:.2f}%")
