# =============================================================
# tab_correlation.py
# 🔗 วิเคราะห์ความสัมพันธ์พอร์ต (Correlation Analysis) — ดูว่าหุ้นที่ถืออยู่จริงเคลื่อนไหวไป
# ทางเดียวกันแค่ไหน ช่วยตอบคำถามว่า "กระจายความเสี่ยงได้จริง หรือแค่ดูเหมือนกระจาย" (ถ้า
# Correlation สูง แปลว่าหุ้นขึ้นลงพร้อมกันหมด ตลาดร่วงพอร์ตร่วงพร้อมกันทั้งก้อน แม้จะถือหลายตัวก็ตาม)
# =============================================================
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.express as px
from backend_functions import get_sector_from_mapping
from theme import style_plotly, render_metric_card, get_theme_colors

MIN_HOLDINGS_NEEDED = 2
LOOKBACK_PERIOD = "6mo"
HIGH_CORRELATION_THRESHOLD = 0.7


@st.cache_data(ttl=1800, show_spinner=False)
def _fetch_price_history_for_correlation(tickers_tuple):
    """
    ดึงราคาปิดย้อนหลัง 6 เดือนของหุ้นทุกตัวที่ระบุพร้อมกันในคำขอเดียว (ประหยัด API มากกว่าดึงทีละตัว)
    คืนค่าเป็น DataFrame (แถว=วันที่, คอลัมน์=Ticker) จำผลลัพธ์ไว้ 30 นาที กันยิงซ้ำบ่อยเกินไป
    """
    tickers_list = list(tickers_tuple)
    yf_symbols = [f"{t}.BK" for t in tickers_list]
    try:
        raw = yf.download(yf_symbols, period=LOOKBACK_PERIOD, group_by='ticker', threads=True, progress=False)
    except Exception:
        return pd.DataFrame()

    price_df = pd.DataFrame()
    for t, sym in zip(tickers_list, yf_symbols):
        try:
            close_series = raw[sym]['Close'] if len(yf_symbols) > 1 else raw['Close']
            price_df[t] = close_series
        except (KeyError, TypeError):
            continue
    return price_df.dropna(how='all')


def render_tab_correlation():
    st.markdown("### 🔗 วิเคราะห์ความสัมพันธ์พอร์ต (Correlation Analysis)")
    st.markdown(
        "ดูว่าหุ้นที่ถืออยู่จริงใน**เคลื่อนไหวไปทางเดียวกันแค่ไหน** — ถ้าหุ้นหลายตัวมีค่าความสัมพันธ์"
        "(Correlation) สูง แปลว่าขึ้นลงพร้อมกันหมด ต่อให้ถือหลายตัว พอตลาดร่วง พอร์ตก็ร่วงพร้อมกันทั้งก้อน "
        "ไม่ได้กระจายความเสี่ยงจริงตามที่คิด"
    )

    if "my_portfolio" not in st.session_state or not st.session_state.my_portfolio:
        st.info("ยังไม่มีข้อมูลพอร์ตหุ้นเลยครับ — ไปเพิ่มรายการซื้อขายในแท็บ \"พอร์ตโฟลิโอ\" ก่อน")
        return

    # เตรียมรายชื่อหุ้น + มูลค่าถือครอง (ใช้ถ่วงน้ำหนักคำนวณคะแนนรวม)
    holdings = []
    for item in st.session_state.my_portfolio:
        ticker = str(item.get('หุ้น', item.get('Ticker', ''))).strip().upper()
        try:
            shares = float(str(item.get('จำนวน', item.get('shares', 0))).replace(',', ''))
        except (ValueError, TypeError):
            shares = 0.0
        try:
            avg_price = float(str(item.get('ต้นทุนเฉลี่ย', item.get('avg_price', 0))).replace(',', ''))
        except (ValueError, TypeError):
            avg_price = 0.0
        if ticker and shares > 0:
            holdings.append({'Ticker': ticker, 'Cost_Value': shares * avg_price})

    if len(holdings) < MIN_HOLDINGS_NEEDED:
        st.info(f"ต้องมีหุ้นถืออยู่อย่างน้อย {MIN_HOLDINGS_NEEDED} ตัวขึ้นไป ถึงจะวิเคราะห์ความสัมพันธ์ได้ครับ (ตอนนี้มี {len(holdings)} ตัว)")
        return

    df_holdings = pd.DataFrame(holdings).groupby('Ticker', as_index=False).sum()
    tickers = df_holdings['Ticker'].tolist()

    with st.spinner(f"กำลังดึงราคาย้อนหลัง {LOOKBACK_PERIOD} ของหุ้น {len(tickers)} ตัว..."):
        price_df = _fetch_price_history_for_correlation(tuple(sorted(tickers)))

    if price_df.empty or len(price_df.columns) < MIN_HOLDINGS_NEEDED:
        st.warning("ดึงข้อมูลราคาย้อนหลังไม่สำเร็จ หรือได้ข้อมูลไม่พอสำหรับหุ้นในพอร์ต ลองรีเฟรชหน้าเว็บใหม่อีกครั้งครับ")
        return

    # คำนวณผลตอบแทนรายวัน (% เปลี่ยนแปลง) แล้วหา Correlation Matrix จากผลตอบแทน (ไม่ใช่ราคาตรงๆ
    # เพราะราคาตรงๆ มักมีแนวโน้มขึ้นด้วยกันตามธรรมชาติของตลาด ทำให้ Correlation สูงเทียมได้)
    returns_df = price_df.pct_change().dropna(how='all')
    valid_tickers = [t for t in tickers if t in returns_df.columns and returns_df[t].notna().sum() >= 20]

    if len(valid_tickers) < MIN_HOLDINGS_NEEDED:
        st.warning("มีข้อมูลราคาย้อนหลังไม่พอสำหรับคำนวณความสัมพันธ์อย่างน่าเชื่อถือครับ (ต้องมีข้อมูลอย่างน้อย 20 วันต่อหุ้น)")
        return

    corr_matrix = returns_df[valid_tickers].corr()

    # --- 1. คะแนนกระจายความเสี่ยงโดยรวม (ถ่วงน้ำหนักตามมูลค่าถือครอง) ---
    st.divider()
    st.markdown("#### 📊 คะแนนกระจายความเสี่ยงโดยรวม")

    weight_map = df_holdings.set_index('Ticker')['Cost_Value'].to_dict()
    pair_corrs = []
    pair_weights = []
    for i, t1 in enumerate(valid_tickers):
        for t2 in valid_tickers[i + 1:]:
            pair_corrs.append(corr_matrix.loc[t1, t2])
            pair_weights.append(weight_map.get(t1, 1) * weight_map.get(t2, 1))

    avg_corr = float(np.average(pair_corrs, weights=pair_weights)) if pair_corrs else 0.0

    if avg_corr < 0.3:
        _diversify_label, _diversify_icon, _diversify_color = "กระจายความเสี่ยงได้ดีมาก", "🟢", "success"
    elif avg_corr < 0.6:
        _diversify_label, _diversify_icon, _diversify_color = "กระจายความเสี่ยงพอใช้ได้", "🟡", "warning"
    else:
        _diversify_label, _diversify_icon, _diversify_color = "กระจายความเสี่ยงไม่ดี ควรพิจารณาปรับพอร์ต", "🔴", "warning"

    m1, m2 = st.columns(2)
    render_metric_card(
        m1, "ค่าความสัมพันธ์เฉลี่ยของพอร์ต (ถ่วงน้ำหนักตามมูลค่า)", f"{avg_corr:.2f}",
        icon=_diversify_icon, caption="ยิ่งใกล้ 0 ยิ่งกระจายความเสี่ยงได้ดี ยิ่งใกล้ 1 ยิ่งเคลื่อนไหวไปทางเดียวกันหมด"
    )
    render_metric_card(m2, "สรุปผล", _diversify_label, icon=_diversify_icon)

    getattr(st, _diversify_color)(f"{_diversify_icon} {_diversify_label} (ค่าความสัมพันธ์เฉลี่ย {avg_corr:.2f})")

    # --- 2. ตารางความสัมพันธ์ (Correlation Matrix Heatmap) ---
    st.divider()
    st.markdown("#### 🌡️ ตารางความสัมพันธ์ระหว่างหุ้นในพอร์ต")
    st.caption("สีแดง = เคลื่อนไหวไปทางเดียวกันมาก (เสี่ยง) | สีเขียว = กระจายความเสี่ยงได้ดี | ยิ่งเข้ม ยิ่งชัดเจน")

    fig = px.imshow(
        corr_matrix, text_auto='.2f', color_continuous_scale=['#26A69A', '#FFFFFF', '#EF5350'],
        zmin=-1, zmax=1, aspect='auto'
    )
    fig.update_layout(height=max(350, 45 * len(valid_tickers)), margin=dict(l=20, r=20, t=20, b=20))
    st.plotly_chart(style_plotly(fig), use_container_width=True)

    # --- 3. คู่หุ้นที่ Correlation สูงเกินเกณฑ์ (แจ้งเตือนเฉพาะจุด) ---
    st.divider()
    st.markdown("#### ⚠️ คู่หุ้นที่เคลื่อนไหวคล้ายกันมากเป็นพิเศษ")

    high_corr_pairs = []
    for i, t1 in enumerate(valid_tickers):
        for t2 in valid_tickers[i + 1:]:
            c = corr_matrix.loc[t1, t2]
            if c >= HIGH_CORRELATION_THRESHOLD:
                high_corr_pairs.append((t1, t2, c))

    if not high_corr_pairs:
        st.success(f"✅ ไม่พบคู่หุ้นไหนที่มีความสัมพันธ์สูงเกิน {HIGH_CORRELATION_THRESHOLD} เลยครับ พอร์ตกระจายความเสี่ยงได้ดี")
    else:
        high_corr_pairs.sort(key=lambda x: x[2], reverse=True)
        for t1, t2, c in high_corr_pairs:
            _sector1 = get_sector_from_mapping(t1)
            _sector2 = get_sector_from_mapping(t2)
            _same_sector_note = f" (อยู่กลุ่ม {_sector1} เหมือนกัน)" if _sector1 == _sector2 else f" ({_sector1} กับ {_sector2})"
            st.warning(f"🔴 **{t1}** และ **{t2}** มีความสัมพันธ์สูงถึง **{c:.2f}**{_same_sector_note} — เคลื่อนไหวคล้ายกันมาก ลองพิจารณาปรับสัดส่วนดูครับ")

    # --- 4. สัดส่วนพอร์ตแยกตาม Sector (บริบทเพิ่มเติม ช่วยอธิบายว่าทำไม Correlation สูง) ---
    st.divider()
    st.markdown("#### 🏢 สัดส่วนมูลค่าพอร์ตแยกตามกลุ่มอุตสาหกรรม")
    st.caption("หุ้นในกลุ่มเดียวกันมักมี Correlation สูงกันเองโดยธรรมชาติ ดูตรงนี้ประกอบเพื่อเข้าใจสาเหตุ")

    df_holdings['Sector'] = df_holdings['Ticker'].apply(lambda t: get_sector_from_mapping(t))
    sector_alloc = df_holdings.groupby('Sector')['Cost_Value'].sum().reset_index().sort_values('Cost_Value', ascending=False)

    fig2 = px.pie(sector_alloc, names='Sector', values='Cost_Value', hole=0.4)
    fig2.update_traces(textposition='inside', textinfo='percent+label')
    fig2.update_layout(height=400, margin=dict(l=20, r=20, t=20, b=20))
    st.plotly_chart(style_plotly(fig2), use_container_width=True)
