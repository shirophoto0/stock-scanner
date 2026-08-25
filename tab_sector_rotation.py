# =============================================================
# tab_sector_rotation.py
# 🔄 Sector Rotation Dashboard — ดูว่ากลุ่มอุตสาหกรรมไหนแข็งแรง/อ่อนแรงกว่าตลาดตอนนี้
# หลักการ: เอาค่า RS_Line ของหุ้นทุกตัวมาเฉลี่ยรวมตาม Sector ยิ่งเฉลี่ยสูง แปลว่าเงินกำลังไหลเข้า
# กลุ่มนั้นมากกว่ากลุ่มอื่น (เทียบกับ SET Index) — ยังไม่เก็บข้อมูลย้อนหลัง (เห็นแค่สถานะปัจจุบัน)
# เพราะยังไม่เคยมีการบันทึกประวัติ RS_Line รายวันมาก่อน (อยู่ใน backlog แยกต่างหาก)
# =============================================================
import streamlit as st
import pandas as pd
import plotly.express as px
from backend_functions import load_from_gsheet, get_sector_from_mapping
from theme import style_plotly, render_metric_card, get_theme_colors


def render_tab_sector_rotation(df_sector_map=None):
    st.markdown("### 🔄 Sector Rotation Dashboard")
    st.markdown(
        "ดูว่ากลุ่มอุตสาหกรรมไหน **แข็งแรงกว่าตลาด** (เงินกำลังไหลเข้า) และกลุ่มไหน **อ่อนแรงกว่าตลาด** "
        "(เงินกำลังไหลออก) ในตอนนี้ — คำนวณจากค่า RS_Line เฉลี่ยของหุ้นทุกตัวในแต่ละกลุ่ม"
    )

    try:
        df_scan = load_from_gsheet()
    except Exception as e:
        st.error(f"ไม่สามารถโหลดข้อมูลผลสแกนหุ้นได้: {e}")
        return

    if df_scan is None or df_scan.empty or 'RS_Line' not in df_scan.columns or 'Ticker' not in df_scan.columns:
        st.info("ยังไม่มีข้อมูลผลสแกนหุ้นเพียงพอ — รอข้อมูลจาก Daily Scan รอบถัดไปครับ")
        return

    # เตรียมข้อมูล: หา Sector ของแต่ละหุ้น + แปลง RS_Line เป็นตัวเลข
    df_work = df_scan.copy()
    df_work['RS_Line'] = pd.to_numeric(df_work['RS_Line'], errors='coerce')
    df_work = df_work.dropna(subset=['RS_Line'])
    df_work['Sector'] = df_work['Ticker'].apply(lambda x: get_sector_from_mapping(x, df_sector_map))
    df_work = df_work[df_work['Sector'].notna() & (df_work['Sector'] != '')]

    if df_work.empty:
        st.info("ยังไม่มีข้อมูล RS_Line ที่ใช้คำนวณได้ครับ")
        return

    # 1. คำนวณค่าเฉลี่ย RS_Line ต่อ Sector แล้วจัดอันดับจากแข็งแกร่งสุดไปอ่อนแอสุด
    # 🔧 แก้บั๊ก: เดิมใช้ชื่อคอลัมน์ภาษาไทยเป็น keyword argument ตรงๆ ใน .agg() ซึ่งบาง
    # เวอร์ชันของ Python/pandas (เช่น Python 3.14 บน Streamlit Cloud) จัดการ keyword argument
    # ที่เป็นภาษาไทยได้ไม่แน่นอน ทำให้คอลัมน์ผลลัพธ์ไม่ได้ชื่อตามที่ตั้งไว้ พอไปเรียกใช้
    # row['จำนวนหุ้น'] ทีหลังเลย error ว่าหาคอลัมน์นี้ไม่เจอ ตอนนี้เปลี่ยนมาใช้ชื่อภาษาอังกฤษ
    # (mean, count) ก่อน แล้วค่อยเปลี่ยนชื่อเป็นไทยด้วย .rename() ทีหลัง ปลอดภัยกว่าแน่นอน
    sector_summary = (
        df_work.groupby('Sector')['RS_Line']
        .agg(['mean', 'count'])
        .reset_index()
        .rename(columns={'mean': 'RS_Line_เฉลี่ย', 'count': 'จำนวนหุ้น'})
        .sort_values('RS_Line_เฉลี่ย', ascending=False)
    )

    st.divider()
    st.markdown("#### 🏆 อันดับความแข็งแกร่งของแต่ละกลุ่มอุตสาหกรรม")
    st.caption("RS_Line เฉลี่ย > 0 หมายถึงกลุ่มนี้แข็งแรงกว่าตลาดโดยรวม (SET Index) ในตอนนี้")

    _tc = get_theme_colors()
    fig = px.bar(
        sector_summary, x='RS_Line_เฉลี่ย', y='Sector', orientation='h',
        text=sector_summary['RS_Line_เฉลี่ย'].apply(lambda x: f"{x:+.2f}"),
        color='RS_Line_เฉลี่ย', color_continuous_scale=['#EF5350', '#26A69A'], color_continuous_midpoint=0
    )
    fig.update_traces(textposition='outside')
    fig.update_layout(
        height=max(350, 40 * len(sector_summary)), xaxis_title="RS_Line เฉลี่ย", yaxis_title="",
        yaxis=dict(categoryorder='total ascending'), margin=dict(l=20, r=60, t=20, b=20),
        coloraxis_showscale=False
    )
    st.plotly_chart(style_plotly(fig), use_container_width=True)

    # 2. ตารางสรุป + Top 10 หุ้นแข็งแกร่งสุดในแต่ละ Sector (กล่องพับเก็บได้ต่อ Sector)
    st.divider()
    st.markdown("#### 📋 หุ้น 10 อันดับแรกที่ RS_Line แรงสุดในแต่ละกลุ่ม")
    st.caption("คลิกกลุ่มที่สนใจเพื่อดูรายชื่อหุ้น เรียงตามลำดับความแข็งแกร่งจากมากไปน้อย")

    for _, row in sector_summary.iterrows():
        _sector_name = row['Sector']
        _avg_rs = row['RS_Line_เฉลี่ย']
        _count = int(row['จำนวนหุ้น'])
        _emoji = "🟢" if _avg_rs > 0 else "🔴" if _avg_rs < 0 else "⚪"

        with st.expander(f"{_emoji} **{_sector_name}** — RS_Line เฉลี่ย {_avg_rs:+.2f} ({_count} หุ้น)"):
            top10 = (
                df_work[df_work['Sector'] == _sector_name]
                .sort_values('RS_Line', ascending=False)
                .head(10)
            )
            _display_cols = ['Ticker', 'RS_Line']
            for _extra_col in ['ราคาล่าสุด', 'RSI_14', 'Trend_Template_Pass']:
                if _extra_col in top10.columns:
                    _display_cols.append(_extra_col)

            st.dataframe(
                top10[_display_cols].reset_index(drop=True).style.format({
                    'RS_Line': '{:+.2f}',
                    **({'ราคาล่าสุด': '{:.2f}'} if 'ราคาล่าสุด' in _display_cols else {}),
                    **({'RSI_14': '{:.1f}'} if 'RSI_14' in _display_cols else {}),
                }),
                use_container_width=True, hide_index=True
            )
