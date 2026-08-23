# =============================================================
# tab_tech.py
# แท็บวิเคราะห์กราฟเทคนิคัล (มี Risk Management ซ้อนอยู่ข้างใน) (Phase 2 ของการแยกไฟล์)
# =============================================================
import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from constants import SET100_TICKERS
from backend_functions import get_cached_stock_info, get_sector_from_mapping, highlight_rsi_zones, load_from_gsheet, save_to_gsheet
from theme import style_plotly
from tab_risk import render_tab_risk


def render_tab_tech(tab_risk, df_sector_map, df_all_stocks):
################################
    # 1. Slidebar (ตัวกรอง)
    with st.sidebar.expander("⚙️ เมนูตัวกรองหุ้น", expanded=True):
        max_pe = st.slider("1. ค่า P/E สูงสุด:", 5.0, 100.0, 100.0)
        min_dividend = st.slider("2. ปันผลขั้นต่ำ (%):", 0.0, 10.0, 0.0)
        rsi_range = st.slider("3. ช่วงค่า RSI:", 10.0, 90.0, (10.0, 90.0))

        strategy_option = st.selectbox(
            "เลือกหน้าเทรด:",
            options=[
                "ไม่กรองเงื่อนไขนี้", 
                "--- กลุ่ม RS Line ---",
                "⭐ RS Line ตัดเส้น 0 ขึ้นมาแล้ว", 
                "📈 RS Line ทำจุดสูงสุดใหม่ (RS New High)",
                "🔥 RS Line ใกล้จะตัด 0 (จ่อระเบิด)", 
                "--- กลุ่ม New High ---",
                "3 Month High", 
                "6 Month High", 
                "52 Week High"
            ]
        )

        # ตรวจสอบข้อมูลก่อนโชว์
        if df_all_stocks is not None and not df_all_stocks.empty:
            # 1. เตรียมข้อมูลและทำความสะอาด
            filtered_df = df_all_stocks.copy()
            filtered_df.columns = filtered_df.columns.str.strip()

            # แปลงคอลัมน์ตัวเลข
            numeric_cols = ['PE_Ratio', 'ปันผล_%', 'RSI_14', 'RS_Line']
            for col in numeric_cols:
                if col in filtered_df.columns:
                    filtered_df[col] = pd.to_numeric(filtered_df[col], errors='coerce').fillna(0)

            # แปลงคอลัมน์ Boolean (สำคัญมากสำหรับการกรองเงื่อนไข)
            bool_cols = ['Is_RS_Above_0', 'Is_3M_High', 'Is_6M_High', 'Is_52W_High']
            for col in bool_cols:
                if col in filtered_df.columns:
                    filtered_df[col] = filtered_df[col].astype(str).str.lower().str.strip() == 'true'

            # 2. กรองพื้นฐานด้วย Slider (จะกรองทับกันไปเรื่อยๆ)
            if max_pe < 100:
                filtered_df = filtered_df[filtered_df['PE_Ratio'] <= max_pe]
            filtered_df = filtered_df[filtered_df['ปันผล_%'] >= min_dividend]
            filtered_df = filtered_df[(filtered_df['RSI_14'] >= rsi_range[0]) & (filtered_df['RSI_14'] <= rsi_range[1])]

            # 3. กำหนดคอลัมน์พื้นฐานและ Sort
            show_columns = ['Ticker', 'ราคาล่าสุด', 'RSI_14', 'RS_Line', 'PE_Ratio', 'ปันผล_%']
            sort_by_col = 'Ticker'
            ascending_sort = True

            # 4. กรองตามหน้าเทรด (Strategy)
            if strategy_option == "⭐ RS Line ตัดเส้น 0 ขึ้นมาแล้ว":
                filtered_df = filtered_df[filtered_df['Is_RS_Above_0'] == True]
                show_columns.append('ตัดเส้น0ขึ้นมาแล้ว(วัน)')
                sort_by_col, ascending_sort = 'ตัดเส้น0ขึ้นมาแล้ว(วัน)', True

            elif strategy_option == "📈 RS Line ทำจุดสูงสุดใหม่ (RS New High)":
                filtered_df = filtered_df[filtered_df['RS_Line'] >= filtered_df['RS_Line_50D_Max']]
                sort_by_col, ascending_sort = 'RS_Line', False

            elif strategy_option == "🔥 RS Line ใกล้จะตัด 0 (จ่อระเบิด)":
                time_map = {"3 เดือน (60 วัน)": 60, "6 เดือน (120 วัน)": 120, "1 ปี (240 วัน)": 240}
                time_choice = st.sidebar.selectbox("เลือกระยะเวลาจมใต้เส้น 0:", list(time_map.keys()), index=1)
                min_days = time_map[time_choice]
                filtered_df = filtered_df[(filtered_df['RS_Line'] <= 0.0) & (filtered_df['อยู่ใต้เส้น0มาแล้ว(วัน)'] >= min_days)]
                show_columns.append('อยู่ใต้เส้น0มาแล้ว(วัน)')
                sort_by_col, ascending_sort = 'RS_Line', False

            elif strategy_option == "3 Month High":
                filtered_df = filtered_df[filtered_df['Is_3M_High'] == True]
                show_columns.append('New_High_3M_มาแล้ว(วัน)')
                sort_by_col, ascending_sort = 'New_High_3M_มาแล้ว(วัน)', True

            elif strategy_option == "6 Month High":
                filtered_df = filtered_df[filtered_df['Is_6M_High'] == True]
                show_columns.append('New_High_6M_มาแล้ว(วัน)')
                sort_by_col, ascending_sort = 'New_High_6M_มาแล้ว(วัน)', True

            elif strategy_option == "52 Week High":
                filtered_df = filtered_df[filtered_df['Is_52W_High'] == True]
                show_columns.append('New_High_52W_มาแล้ว(วัน)')
                sort_by_col, ascending_sort = 'New_High_52W_มาแล้ว(วัน)', True

            # 5. แสดงผล
            results_container = st.empty() 


            # กรองคอลัมน์ที่เลือกให้โชว์
            valid_cols = [c for c in show_columns if c in filtered_df.columns]

    ##########################
    # 4. ส่วนการเลือกหุ้น (เป็นตัวกลางส่งค่าไป Fundamental และ กราฟ)

    st.subheader("🔍 1. วิเคราะห์กราฟเทคนิคัลอัจฉริยะ (Multi-Timeframe & RS vs SET Index)")

    # ส่วนจัดการการโหลดข้อมูล (ปรับแก้ให้เข้ากับ Session State)
    if st.button("🔄 อัปเดตข้อมูลใหม่ (ดึงจาก Yahoo)"):
        with st.spinner("กำลังดึงข้อมูล..."):
            df_new = load_and_calculate_stock_data()

            # 🟢 เติม Sector อัตโนมัติหลังกดอัปเดตจาก Yahoo
            if not df_new.empty and 'df_sector_map' in locals() and not df_sector_map.empty:
                target_col = 'หุ้น' if 'หุ้น' in df_new.columns else 'Ticker'
                if target_col in df_new.columns:
                    df_new['Sector'] = df_new[target_col].apply(lambda x: get_sector_from_mapping(x, df_sector_map))

            save_to_gsheet(df_new)

            # 📌 อัปเดตข้อมูลลง Session State เพื่อให้หน้าเว็บรับข้อมูลชุดใหม่ทันที
            st.session_state.df_all_stocks = df_new 
            st.success("อัปเดตข้อมูลจาก Yahoo สำเร็จ!")
            st.rerun()  # 📌 สั่งรีเฟรชหน้าเบาๆ ให้กราฟและ Selectbox ด้านล่างเปลี่ยนตาม
    else:
        # 📌 ดึงข้อมูลจาก Session State ที่โหลดไว้แล้วจาก def main() แทนการโหลดซ้ำจาก Google Sheets
        df_all_stocks = st.session_state.get('df_all_stocks', pd.DataFrame())

        # ถ้าใน Session State ยังว่างเปล่า ค่อยดึงจาก Sheet อีกรอบ
        if df_all_stocks.empty:
            df_all_stocks = load_from_gsheet()
            st.session_state.df_all_stocks = df_all_stocks

    col_input, col_metrics = st.columns([1, 3])

    with col_input:
        all_tickers = [t.replace('.BK', '') for t in SET100_TICKERS]

        # 1. กำหนดค่าเริ่มต้นจาก Session State กลาง
        current_selected = st.session_state.get("selected_ticker", "KBANK")

        # 2. สร้าง Selectbox สำหรับเลือกหุ้น
        # 🔧 แก้บั๊ก: ใช้ Key แบบ Dynamic (เปลี่ยนตามหุ้นที่เลือกอยู่) เหมือนแท็บ Risk Management
        # เพื่อไม่ให้ dropdown "จำค่าเก่าของตัวเอง" ค้างไว้ ไม่ว่าหุ้นจะถูกเปลี่ยนมาจากทางไหนก็ตาม
        # (จากการพิมพ์ในนี้เอง, จากการกดตาราง, หรือจากแท็บ Risk Management)
        ticker_input = st.selectbox(
            "เลือกหรือพิมพ์ชื่อหุ้นที่ต้องการดูราคากราฟรายละเอียด:", 
            options=all_tickers, 
            index=all_tickers.index(current_selected) if current_selected in all_tickers else 0,
            key=f"tech_stock_selectbox_{current_selected}"
        )

        # 3. ถ้าค่าที่เลือกเปลี่ยน ให้บันทึกเข้า session_state แล้ว Rerun ทันที
        if ticker_input != current_selected:
            st.session_state.selected_ticker = ticker_input
            st.rerun() 

    # ใช้ค่ากลางจาก session_state
    selected_ticker = st.session_state.selected_ticker 
    ticker = f"{selected_ticker}.BK"

    # ใช้ฟังก์ชัน Cache ดึงข้อมูล
    info = get_cached_stock_info(ticker) 
    stock_data = yf.Ticker(ticker) 

    ##### link web set and trading view ########
    col1, col2 = st.columns(2)

    with col1:
        set_url = f"https://www.set.or.th/th/market/product/stock/quote/{st.session_state.selected_ticker}/company-profile/information"
        st.link_button("🌐 ข้อมูล SET", set_url, use_container_width=True)

    with col2:
        tv_url = f"https://www.tradingview.com/chart/?symbol=SET%3A{st.session_state.selected_ticker}"
        st.link_button("📈 กราฟ TradingView", tv_url, use_container_width=True)

    st.markdown("---")

    # ==========================================
    # 5. Fundamental Dashboard (ให้อยู่ระดับชิดซ้ายปกติ)
    # ==========================================
    # 5. Fundamental Dashboard (พร้อมระบบ Try-Catch และ Fallback ป้องกันเว็บพัง)
    st.markdown("#### 📊 Fundamental Growth Dashboard (คัดกรองพลังขับเคลื่อนตามสูตร SEPA)")

    # ฟังก์ชันดึงข้อมูลแบบปลอดภัยด้วย Try-Catch
    def safe_get_stock_fundamentals(ticker_symbol):
        try:
            # ดึงข้อมูลจากฟังก์ชันแคชเดิมของคุณ
            stock_info = get_cached_stock_info(ticker_symbol)
            if stock_info and isinstance(stock_info, dict) and len(stock_info) > 0:
                return stock_info, True
        except Exception as e:
            pass

        # Fallback: ถ้าดึงไม่ได้ ให้ส่งค่าว่างและบอกสถานะว่าดึงไม่สำเร็จ
        return {}, False

    # เรียกใช้งานฟังก์ชัน
    info, is_success = safe_get_stock_fundamentals(ticker)

    if is_success and info:
        # ดึงงบอย่างปลอดภัย
        m_cap = info.get('marketCap', None)
        rev_growth = info.get('quarterlyRevenueGrowth', info.get('revenueGrowth', None))
        eps_growth = info.get('quarterlyEarningsGrowth', info.get('earningsGrowth', None))
        gross_margins = info.get('grossMargins', None)
        profit_margins = info.get('profitMargins', None)
        roe = info.get('returnOnEquity', None)
        pb_ratio = info.get('priceToBook', None)

        f_col1, f_col2 = st.columns(2)
        with f_col1:
            st.write("##### 📈 ตัวเลขการเจริญเติบโต (Growth Metrics)")
            if rev_growth is not None:
                st.metric("อัตราเติบโตของรายได้ (Revenue Growth YoY)", f"{rev_growth * 100:.2f} %")
            else:
                st.write("• **Revenue Growth YoY:** ไม่มีข้อมูลระบบส่งตรง")

            if eps_growth is not None:
                is_sepa_growth = "🔥 ผ่านเกณฑ์หุ้นเติบโตแรง (>20%)" if eps_growth >= 0.20 else "ปกติ"
                st.metric("อัตราเติบโตของกำไรต่อหุ้น (EPS Growth YoY)", f"{eps_growth * 100:.2f} %", delta=is_sepa_growth)
            else:
                st.write("• **EPS Growth YoY:** ไม่มีข้อมูลระบบส่งตรง")

            if m_cap is not None:
                st.write(f"🏢 **มูลค่าบริษัท (Market Cap):** {m_cap / 1_000_000_000:,.2f} พันล้านบาท")

        with f_col2:
            st.write("##### 💰 อัตราการทำกำไรและมูลค่า (Profitability & Valuation)")
            if gross_margins is not None:
                st.write(f"• **อัตรากำไรขั้นต้น (Gross Margin):** {gross_margins * 100:.2f} %")
            if profit_margins is not None:
                st.write(f"• **อัตรากำไรสุทธิ (Net Profit Margin):** {profit_margins * 100:.2f} %")
            if roe is not None:
                st.write(f"• **ผลตอบแทนต่อส่วนผู้ถือหุ้น (ROE):** {roe * 100:.2f} %")
            if pb_ratio is not None:
                st.write(f"• **ราคาต่อมูลค่าทางบัญชี (P/B Ratio):** {pb_ratio:.2f} เท่า")

            pe_value = info.get('trailingPE')
            if pe_value is not None:
                st.write(f"• **ราคาต่อกำไรสุทธิ (P/E Ratio ยืนยัน):** {pe_value:.2f} เท่า")
            else:
                st.write("• **ราคาต่อกำไรสุทธิ (P/E Ratio ยืนยัน):** ไม่มีข้อมูล")

        st.info("💡 **ข้อแนะนำจากระบบ:** หุ้นซุปเปอร์สต็อกตามสไตล์ Mark Minervini มักจะมี EPS Growth ขยายตัวมากกว่า 20%-25% ขึ้นไป ควบคู่กับราคาหุ้นที่ยกฐานยืนเหนือเส้น EMA ขาขึ้น")

    else:
        # กรณีดึงข้อมูลไม่สำเร็จ แสดงกล่องแจ้งเตือนแบบนุ่มนวล พร้อมปุ่มให้ลองกดโหลดใหม่เฉพาะจุด
        st.warning(f"⚠️ ขณะนี้ Yahoo Finance ไม่ตอบสนองต่อการดึงข้อมูลพื้นฐานของหุ้น `{selected_ticker}` (อาจติดปัญหา Rate Limit หรือการเชื่อมต่อ)")

        if st.button(f"🔄 ลองดึงข้อมูล {selected_ticker} อีกครั้ง"):
            # เคลียร์ Cache เฉพาะตัวหรือสั่ง Rerun ให้ลองใหม่
            if 'get_cached_stock_info' in globals() and hasattr(get_cached_stock_info, 'clear'):
                get_cached_stock_info.clear()
            st.rerun()

    # 3. แสดงผลตารางและกราฟ
    # ... (เอาโค้ดส่วนแสดงผล st.dataframe และ st.plotly_chart มาใส่ตรงนี้) ...
    #####################################

    with st.expander ("⚙️ ตั้งค่าการแสดงผลกราฟ"):
        col_tf, col_period = st.columns([1, 1])

        tf_mapping = {
            "1 วัน (Day)": "1d",
            "1 สัปดาห์ (Week)": "1wk",
            "1 เดือน (Month)": "1mo"
        }
        # 🔧 ตัดตัวเลือก 1hr/4hr ออก เพราะ Yahoo Finance ไม่มีข้อมูลราคารายชั่วโมงสำหรับหุ้นไทย (.BK)
        # ทำให้กราฟไม่ขึ้น — มีลิงก์ TradingView ไว้สำหรับดูกราฟช่วงเวลาสั้นแทนอยู่แล้ว
        # เพิ่ม Mapping นี้ไว้ก่อนส่วนที่เรียก stock_data.history
        p_map = {
            "6 เดือน (6m)": "6mo", 
            "1 ปี (1y)": "1y", 
            "5 ปี (5y)": "5y", 
            "ตั้งแต่เข้าตลาด (All Time)": "max"
        }


        with col_tf:
            tf_select = st.pills("เลือกความถี่แท่งเทียน (Timeframe):", options=list(tf_mapping.keys()), default="1 วัน (Day)")
            if not tf_select:
                tf_select = "1 วัน (Day)"
            selected_tf = tf_mapping[tf_select]

        with col_period:
            period_options = ["6 เดือน (6m)", "1 ปี (1y)", "5 ปี (5y)", "ตั้งแต่เข้าตลาด (All Time)"]
            chart_period = st.pills("เลือกช่วงเวลากราฟ (ทั้งหมด):", options=period_options, default="6 เดือน (6m)")
            if not chart_period:
                chart_period = "6 เดือน (6m)"

        # =============================================================
        # 6. กราฟเทคนิคัล
        # =============================================================
        try:
            ticker = f"{st.session_state.selected_ticker}.BK"
            stock_data = yf.Ticker(ticker)
            set_market = yf.Ticker("^SET.BK")
            info = get_cached_stock_info(ticker)


            # 3.1 กำหนดช่วงเวลา 
            p_map = {"6 เดือน (6m)": "6mo", "1 ปี (1y)": "1y", "5 ปี (5y)": "5y", "ตั้งแต่เข้าตลาด (All Time)": "max"}
            selected_period = p_map.get(chart_period, "1y")
            actual_interval = selected_tf

            # 3.2 ดึงข้อมูล
            hist_chart = stock_data.history(period=selected_period, interval=actual_interval)
            hist_market = set_market.history(period=selected_period, interval=actual_interval)

            # กรณีดึงข้อมูลมาแล้วว่าง ให้ลองถอยกลับไปดึง period ที่สั้นลง (Fallback)
            if hist_chart.empty:
                hist_chart = stock_data.history(period="6mo", interval=actual_interval)
                hist_market = set_market.history(period="6mo", interval=actual_interval)

            if not hist_chart.empty:
                # ปรับ Timezone และรวมข้อมูล
                if hist_chart.index.tz is not None: hist_chart.index = hist_chart.index.tz_localize(None)
                if not hist_market.empty and hist_market.index.tz is not None: hist_market.index = hist_market.index.tz_localize(None)

                hist_market_close = hist_market['Close'].to_frame(name='Market_Close')
                chart_combined = hist_chart[['Open', 'High', 'Low', 'Close']].join(hist_market_close, how='inner')

                if len(chart_combined) >= 5:  # 🔧 กันเหนียว: ถ้าข้อมูลน้อยเกินไป (เช่น Timeframe 1ชม./4ชม. ไม่มีข้อมูล) ให้แจ้งเตือนแทนการวาดกราฟเปล่า
                    # คำนวณค่าเทคนิคัล
                    base_stock = chart_combined['Close'].iloc[0]
                    chart_combined['Stock_Perf'] = ((chart_combined['Close'] - base_stock) / base_stock) * 100

                    base_market = chart_combined['Market_Close'].iloc[0]
                    market_perf = ((chart_combined['Market_Close'] - base_market) / base_market) * 100
                    chart_combined['RS_Line'] = chart_combined['Stock_Perf'] - market_perf
                    chart_combined['RS_EMA20'] = chart_combined['RS_Line'].ewm(span=20, adjust=False).mean()
                    chart_combined['Is_Above_0'] = chart_combined['RS_Line'] > 0
                    chart_combined['Days_Above_0'] = chart_combined['Is_Above_0'].groupby((~chart_combined['Is_Above_0']).cumsum()).cumsum()
                    chart_combined['EMA10'] = chart_combined['Close'].ewm(span=10, adjust=False).mean()
                    chart_combined['EMA20'] = chart_combined['Close'].ewm(span=20, adjust=False).mean()
                    chart_combined['EMA50'] = chart_combined['Close'].ewm(span=50, adjust=False).mean()
                    chart_combined['EMA100'] = chart_combined['Close'].ewm(span=100, adjust=False).mean()
                    chart_combined['EMA200'] = chart_combined['Close'].ewm(span=200, adjust=False).mean()

                    # สร้างตารางวันหยุด
                    missing_dates = pd.date_range(start=chart_combined.index.min(), end=chart_combined.index.max(), freq='D').difference(pd.to_datetime(chart_combined.index.date))

                    # 3.5 แสดง Metrics
                    latest_price_single = info.get('currentPrice', chart_combined['Close'].iloc[-1])
                    latest_rs_status = "แข็งแกร่งกว่าตลาด (Outperform)" if chart_combined['RS_Line'].iloc[-1] > chart_combined['RS_EMA20'].iloc[-1] else "อ่อนแอกว่าตลาด (Underperform)"
                    with col_metrics:
                        m1, m2, m3, m4 = st.columns([2, 1, 1.5, 1]) 

                        # ปรับส่วนดึงข้อมูลปันผล
                        raw_div = info.get('dividendYield') or info.get('trailingAnnualDividendYield', 0)

                        if raw_div:
                            if raw_div > 1:
                                div_display = f"{raw_div:.2f}%"
                            else:
                                div_display = f"{raw_div * 100:.2f}%"
                        else:
                            div_display = "N/A"

                        # --- m1: ชื่อบริษัท ---
                        m1.caption("ชื่อบริษัท")
                        m1.write(f"**{info.get('longName', 'N/A')}**")

                        # --- m2: ราคาล่าสุด ---
                        m2.caption("ราคาล่าสุด")
                        m2.write(f"**{latest_price_single:.2f} บ.**")

                        # --- m3: สถานะ RS ---
                        m3.caption("สถานะ RS")
                        m3.write(f"**{'แข็งแกร่งกว่าตลาด' if chart_combined['RS_Line'].iloc[-1] > chart_combined['RS_EMA20'].iloc[-1] else 'อ่อนแอกว่าตลาด'}**")

                        # --- m4: ปันผล (Yield) ---
                        m4.caption("ปันผล (Yield)")
                        m4.write(f"**{div_display}**")

                    # 3.4 วาดกราฟ
                    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_width=[0.3, 0.7])
                    fig.add_trace(go.Candlestick(x=chart_combined.index, open=chart_combined['Open'], high=chart_combined['High'], low=chart_combined['Low'], close=chart_combined['Close'], name='Price'), row=1, col=1)

                    ema_hover_config = dict(bgcolor='rgba(255, 255, 255, 0.20)', bordercolor='rgba(0,0,0,0)')
                    fig.add_trace(go.Scatter(x=chart_combined.index, y=chart_combined['EMA10'], line=dict(color='orange', width=1.5), name='EMA 10', hovertemplate="EMA10: %{y:.2f}<extra></extra>", hoverlabel=ema_hover_config), row=1, col=1)
                    fig.add_trace(go.Scatter(x=chart_combined.index, y=chart_combined['EMA20'], line=dict(color='magenta', width=1.5), name='EMA 20', hovertemplate="EMA20: %{y:.2f}<extra></extra>", hoverlabel=ema_hover_config), row=1, col=1)
                    fig.add_trace(go.Scatter(x=chart_combined.index, y=chart_combined['EMA50'], line=dict(color='blue', width=1.5), name='EMA 50', hovertemplate="EMA50: %{y:.2f}<extra></extra>", hoverlabel=ema_hover_config), row=1, col=1)
                    fig.add_trace(go.Scatter(x=chart_combined.index, y=chart_combined['EMA100'], line=dict(color='brown', width=1.5), name='EMA 100', hovertemplate="EMA100: %{y:.2f}<extra></extra>", hoverlabel=ema_hover_config), row=1, col=1)
                    fig.add_trace(go.Scatter(x=chart_combined.index, y=chart_combined['EMA200'], line=dict(color='black', width=2.0), name='EMA 200', hovertemplate="EMA200: %{y:.2f}<extra></extra>", hoverlabel=ema_hover_config), row=1, col=1)

                    # กราฟ RS Line (Purple)
                    fig.add_trace(go.Scatter(
                        x=chart_combined.index, 
                        y=chart_combined['RS_Line'], 
                        line=dict(color='#9c27b0', width=2), 
                        name='RS Line',
                        hovertemplate="RS Line: %{y:.2f}%<extra></extra>"
                    ), row=2, col=1)

                    # กราฟ RS EMA 20 (Orange Dash)
                    fig.add_trace(go.Scatter(
                        x=chart_combined.index, 
                        y=chart_combined['RS_EMA20'], 
                        line=dict(color='#ff9800', width=1.5, dash='dot'), 
                        name='RS EMA20',
                        hovertemplate="RS EMA20: %{y:.2f}%<extra></extra>"
                    ), row=2, col=1)

                    # เส้นอ้างอิงแนวนอน (Hline)
                    fig.add_hline(y=0, line_dash="solid", line_color="grey", line_width=1, row=2, col=1)
                    fig.add_hline(y=20, line_dash="dot", line_color="rgba(255, 0, 0, 0.3)", row=2, col=1)
                    fig.add_hline(y=-20, line_dash="dot", line_color="rgba(0, 0, 255, 0.3)", row=2, col=1)

                    # 1. ตั้งค่า Candlestick ให้แสดงข้อมูลพื้นฐาน
                    fig.update_xaxes(
                            rangebreaks=[dict(values=missing_dates)],
                            showgrid=True,
                            gridcolor='rgba(150,150,150,0.08)',
                            showspikes=True,
                            spikecolor='#888',
                            spikethickness=1,
                            spikesnap='cursor',
                            spikemode='across'
                        )
                    fig.update_yaxes(
                            showgrid=True,
                            gridcolor='rgba(150,150,150,0.08)',
                            showspikes=True,
                            spikecolor='#888',
                            spikethickness=1,
                            spikesnap='cursor',
                            spikemode='across'
                        )

                    fig.update_layout(
                height=800,
                margin=dict(l=40, r=60, t=50, b=40), # เพิ่มขอบขวา (r=60) เพื่อให้มีที่ว่างสำหรับป้ายราคา
                hovermode='x unified',
                xaxis_rangeslider_visible=False,
                # ปรับแกน Y ให้แสดงป้ายราคาที่ "ชี้" ไปที่ราคาล่าสุด
                yaxis=dict(
                    showspikes=False, # ปิด spike แกน Y เพื่อไม่ให้บังป้ายราคา
                    side='right',     # ย้ายแกนราคาไปไว้ขวาเหมือน TradingView
                    showgrid=True,
                )
            )
                    st.plotly_chart(style_plotly(fig), use_container_width=True)
                else:
                    st.warning(f"⚠️ ไม่มีข้อมูลกราฟเพียงพอสำหรับ Timeframe นี้ (พบแค่ {len(chart_combined)} แท่งเทียน) "
                                     f"อาจเป็นเพราะ Yahoo Finance ไม่มีข้อมูลรายชั่วโมง/4ชั่วโมงของหุ้นไทยตัวนี้ "
                                     f"ลองเปลี่ยนเป็น Timeframe รายวัน (Day) แทนครับ")
            # (แนะนำให้พี่อ้ำใช้โค้ดเดิมในส่วนนี้ได้เลยครับ ผมตัดมาให้สั้นลงเพื่อดูโครงสร้าง)
            # ...


        except Exception as e:
            st.error(f"⚠️ เกิดข้อผิดพลาดในการวาดกราฟ: {str(e)}")
    # ==========================================
    # เริ่ม Tab ถัดไป (เช่น tab_risk) ตรงนี้
    # ==========================================
    with tab_risk:
        render_tab_risk()
    # =============================================================
    # 7. ผลลัพธ์การสแกน (ใช้ filtered_df ที่กรองผ่าน Sidebar มาแล้ว)
    # =============================================================
    with st.expander("📊 ผลลัพธ์การสแกน"):
        # 1. เช็คข้อมูลจาก Sidebar (ถ้าไม่มีให้ใช้ df_all_stocks)
        # แก้ไขบรรทัดที่ 1152 เป็นแบบนี้ครับ
        try:
            # พยายามใช้ filtered_df ถ้ามี และมีค่า
            if 'filtered_df' in locals() and filtered_df is not None:
                df_scan = filtered_df.copy()
            # ถ้าไม่มี ให้ใช้ df_all_stocks แต่ต้องเช็คว่ามีอยู่จริงด้วย
            elif 'df_all_stocks' in locals() and df_all_stocks is not None:
                df_scan = df_all_stocks.copy()
            else:
                # กรณีแย่ที่สุด คือไม่มีข้อมูลเลย ให้สร้าง DataFrame เปล่าขึ้นมา
                df_scan = pd.DataFrame()
                st.error("ไม่พบข้อมูลหุ้นในระบบ กรุณาตรวจสอบการโหลดข้อมูล")
        except Exception as e:
            df_scan = pd.DataFrame()
            st.error(f"เกิดข้อผิดพลาดในการเตรียมตาราง: {e}")

        df_scan = filtered_df.copy() if filtered_df is not None else df_all_stocks.copy()

        # 2. กรองตาม Strategy ที่เลือก (ถ้ามี)
        if strategy_option == "3 Month High":
            final_sorted_df = df_scan[df_scan['Is_3M_High'] == True]
        elif strategy_option == "6 Month High":
            final_sorted_df = df_scan[df_scan['Is_6M_High'] == True]
        elif strategy_option == "52 Week High":
            final_sorted_df = df_scan[df_scan['Is_52W_High'] == True]
        elif strategy_option == "⭐ RS Line ตัดเส้น 0 ขึ้นมาแล้ว":
            final_sorted_df = df_scan[df_scan['Is_RS_Above_0'] == True]
        elif strategy_option == "📈 RS Line ทำจุดสูงสุดใหม่ (RS New High)":
            final_sorted_df = df_scan[df_scan['RS_Line'] >= df_scan['RS_Line_50D_Max']]
        else:
            final_sorted_df = df_scan

        # 3. แสดงผลหัวข้อ
        st.subheader(f"📊 ผลลัพธ์การสแกน ({strategy_option}): พบทั้งหมด {len(final_sorted_df)} ตัว")

        # 4. เลือกคอลัมน์ที่จะแสดง (Whitelist)
        fixed_cols = ['Ticker', 'ราคาล่าสุด', 'RSI_14', 'RS_Line', 'PE_Ratio', 'ปันผล_%']
        strategy_cols_map = {
            "3 Month High": ['New_High_3M_มาแล้ว(วัน)'], 
            "6 Month High": ['New_High_6M_มาแล้ว(วัน)'],
            "52 Week High": ['New_High_52W_มาแล้ว(วัน)'],
            "⭐ RS Line ตัดเส้น 0 ขึ้นมาแล้ว": ['ตัดเส้น0ขึ้นมาแล้ว(วัน)'],
            "🔥 RS Line ใกล้จะตัด 0 (จ่อระเบิด)": ['อยู่ใต้เส้น0มาแล้ว(วัน)']
        }

        cols_to_show = fixed_cols + strategy_cols_map.get(strategy_option, [])
        existing_cols = [c for c in cols_to_show if c in final_sorted_df.columns]
        df_display = final_sorted_df[existing_cols].copy()

        # 5. บังคับแปลงตัวเลขเพื่อจัดรูปแบบ
        numeric_cols = ['PE_Ratio', 'ปันผล_%', 'ราคาล่าสุด', 'RSI_14', 'RS_Line']
        for col in numeric_cols:
            if col in df_display.columns:
                df_display[col] = pd.to_numeric(df_display[col], errors='coerce')

        # 6. จัดรูปแบบตาราง
        styled_df = df_display.style.format({
            'ราคาล่าสุด': '{:.2f}', 'RSI_14': '{:.2f}', 'RS_Line': '{:.2f}', 
            'PE_Ratio': '{:.2f}', 'ปันผล_%': '{:.2f}'
        }, na_rep='-').apply(highlight_rsi_zones, axis=1)

        # 7. แสดงตารางและดึง Event
        event = st.dataframe(
            styled_df,
            use_container_width=True,
            selection_mode="single-row",
            on_select="rerun",
            key="stock_table"
        )

        # 8. ดึงข้อมูลการเลือกหุ้น (สรุปรวมเหลือบล็อกเดียว)
        if event.selection and "rows" in event.selection and event.selection["rows"]:
            selected_index = event.selection["rows"][0]

            # ตรวจสอบว่า Index อยู่ในขอบเขตข้อมูลปัจจุบันหรือไม่
            if selected_index < len(final_sorted_df):
                clicked_ticker = final_sorted_df.iloc[selected_index]['Ticker']

                # ถ้าหุ้นที่เลือกเปลี่ยนไปจากเดิม ถึงจะสั่ง Rerun
                if st.session_state.get("selected_ticker") != clicked_ticker:
                    st.session_state.selected_ticker = clicked_ticker
                    st.rerun()
            else:
                # กรณีตารางถูกกรองจน Index เดิมหายไป (เช่น สลับหน้าเทรด) 
                # ล้างค่า Selection เก่าออกเพื่อความปลอดภัย
                if st.session_state.get("selected_ticker"):
                    del st.session_state.selected_ticker
                    st.rerun()

# 🔧 แก้บั๊ก: 2 บรรทัดด้านล่างนี้เดิมหลุดไปอยู่นอกฟังก์ชัน render_tab_tech() โดยไม่ตั้งใจ
# (ตอนแยกไฟล์ ดึงโค้ดเกินขอบเขตของแท็บนี้มาด้วย) ย้ายกลับเข้ามาในฟังก์ชันให้ถูกต้อง
    st.markdown("---") # เส้นคั่น เพื่อแยกส่วนกับตารางด้านบนให้ชัด
