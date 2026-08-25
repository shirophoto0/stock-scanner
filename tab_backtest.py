# =============================================================
# tab_backtest.py
# 🔬 Backtest กลยุทธ์การสแกน — ดูว่าเกณฑ์เด่นที่สแกนหาทุกวัน (Trend Template, RS ตัดเส้น 0,
# 52W High) ทำนายราคาในอนาคตได้จริงไหม โดยดูผลตอบแทนเฉลี่ยที่ 30/60/90 วันหลังสัญญาณเกิด
# ใช้ข้อมูลที่ Daily Scan สะสมไว้ในชีต Signal_History (เก็บย้อนหลังสูงสุด 5 ปี)
# =============================================================
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from backend_functions import load_signal_history
from theme import style_plotly, render_metric_card, get_theme_colors

# 🔧 แก้บั๊ก: เดิมใช้ get_active_sheet_name() (ชีตของผู้ใช้ที่ login อยู่ตอนนั้น) แต่ Signal_History
# เป็นข้อมูลตลาดหุ้นรวม ไม่ใช่ข้อมูลส่วนตัว บันทึกไว้ที่ "MyStockData" เพียงที่เดียวเท่านั้น (ตาม
# REFERENCE_SPREADSHEET ใน daily_scan.py) ถ้าแฟน login ด้วย Nujiwealth แล้วอ่านจากชีตของตัวเอง
# จะไม่เจอข้อมูลเลย ตอนนี้ตรึงชื่อชีตต้นทางให้ตรงกับที่ daily_scan.py บันทึกไว้จริง ทั้ง 2 บัญชี
# จะเห็นข้อมูล Backtest ชุดเดียวกันเสมอ (สมเหตุสมผล เพราะเป็นข้อมูลตลาดหุ้นรวม ไม่ใช่ของใครคนเดียว)
SIGNAL_HISTORY_SPREADSHEET = "MyStockData"

SIGNAL_TYPE_LABELS = {
    "Trend_Template": "✅ Trend Template ผ่านใหม่",
    "RS_Cross_Up": "⭐ RS Line ตัดเส้น 0 ขึ้น",
    "New_52W_High": "🚀 ทำจุดสูงสุดใหม่ 52 สัปดาห์",
}


def render_tab_backtest():
    st.markdown("### 🔬 Backtest กลยุทธ์การสแกน")
    st.markdown(
        "ดูว่าหุ้นที่ผ่านเกณฑ์เด่นในอดีต **ราคาไปทางไหนต่อจริงๆ** ใน 30/60/90 วันถัดมา "
        "ช่วยตอบคำถามว่าเกณฑ์ที่สแกนหาทุกวันนี้ใช้ได้ผลจริงหรือไม่ — ข้อมูลเริ่มสะสมตั้งแต่วันที่เริ่มใช้ฟีเจอร์นี้ "
        "(เก็บย้อนหลังสูงสุด 5 ปี)"
    )

    df_signals = load_signal_history(SIGNAL_HISTORY_SPREADSHEET)

    if df_signals.empty:
        st.info(
            "ยังไม่มีข้อมูลสัญญาณสะสมเลยครับ — ระบบจะเริ่มบันทึกอัตโนมัติทุกวันตอน Daily Scan ทำงาน "
            "รอสักระยะ (อย่างน้อย 30 วัน) ถึงจะเริ่มเห็นผลตอบแทนช่วงแรกครับ"
        )
        return

    # เตรียมข้อมูล: แปลงคอลัมน์ตัวเลขให้พร้อมใช้งาน
    for col in ['Return_30D', 'Return_60D', 'Return_90D']:
        if col in df_signals.columns:
            df_signals[col] = pd.to_numeric(df_signals[col], errors='coerce')

    st.divider()
    signal_filter = st.selectbox(
        "เลือกประเภทสัญญาณที่จะดู",
        ["ทั้งหมด"] + list(SIGNAL_TYPE_LABELS.keys()),
        format_func=lambda x: "ทั้งหมด (รวมทุกประเภท)" if x == "ทั้งหมด" else SIGNAL_TYPE_LABELS.get(x, x)
    )

    df_filtered = df_signals if signal_filter == "ทั้งหมด" else df_signals[df_signals['Signal_Type'] == signal_filter]

    if df_filtered.empty:
        st.info("ยังไม่มีข้อมูลสัญญาณประเภทนี้ครับ")
        return

    st.caption(f"สะสมสัญญาณทั้งหมด **{len(df_filtered):,} รายการ** (นับตั้งแต่เริ่มเก็บข้อมูล)")

    # 1. สรุปสถิติภาพรวม 30/60/90 วัน (เฉพาะรายการที่ "ครบกำหนด" แล้วเท่านั้น มีผลตอบแทนบันทึกไว้)
    st.divider()
    st.markdown("#### 📊 สรุปผลตอบแทนเฉลี่ย")

    cols = st.columns(3)
    for i, (days, col_name) in enumerate([(30, 'Return_30D'), (60, 'Return_60D'), (90, 'Return_90D')]):
        with cols[i]:
            resolved = df_filtered[col_name].dropna() if col_name in df_filtered.columns else pd.Series(dtype=float)
            if resolved.empty:
                render_metric_card(
                    st, f"{days} วันหลังสัญญาณ", "รอข้อมูล",
                    icon="⏳", caption="ยังไม่มีสัญญาณไหนครบกำหนดเวลานี้"
                )
            else:
                avg_return = resolved.mean()
                win_rate = (resolved > 0).mean() * 100
                render_metric_card(
                    st, f"{days} วันหลังสัญญาณ", f"{avg_return:+.2f}%",
                    icon="📈" if avg_return >= 0 else "📉",
                    caption=f"Win Rate {win_rate:.1f}% (จาก {len(resolved)} รายการที่ครบกำหนดแล้ว)"
                )

    # 2. กราฟเปรียบเทียบผลตอบแทนเฉลี่ยตามประเภทสัญญาณ (เฉพาะตอนเลือกดู "ทั้งหมด")
    if signal_filter == "ทั้งหมด" and 'Signal_Type' in df_signals.columns:
        st.divider()
        st.markdown("#### 📊 เปรียบเทียบผลตอบแทนเฉลี่ยตามประเภทสัญญาณ")

        summary_rows = []
        for sig_type, label in SIGNAL_TYPE_LABELS.items():
            sub = df_signals[df_signals['Signal_Type'] == sig_type]
            row = {'ประเภทสัญญาณ': label}
            for days, col_name in [(30, 'Return_30D'), (60, 'Return_60D'), (90, 'Return_90D')]:
                resolved = sub[col_name].dropna() if col_name in sub.columns else pd.Series(dtype=float)
                row[f'{days} วัน'] = resolved.mean() if not resolved.empty else None
            summary_rows.append(row)

        df_compare = pd.DataFrame(summary_rows)
        fig = go.Figure()
        for days_col in ['30 วัน', '60 วัน', '90 วัน']:
            fig.add_trace(go.Bar(
                x=df_compare['ประเภทสัญญาณ'], y=df_compare[days_col], name=days_col
            ))
        fig.update_layout(
            barmode='group', height=380, yaxis_title="ผลตอบแทนเฉลี่ย (%)",
            margin=dict(l=20, r=20, t=20, b=20)
        )
        st.plotly_chart(style_plotly(fig), use_container_width=True)

    # 3. ตารางรายละเอียดล่าสุด
    st.divider()
    st.markdown("#### 📋 รายการล่าสุด")
    _display_cols = ['Date', 'Ticker', 'Signal_Type', 'Price_At_Signal', 'Return_30D', 'Return_60D', 'Return_90D']
    _available_cols = [c for c in _display_cols if c in df_filtered.columns]
    df_recent = df_filtered[_available_cols].sort_values('Date', ascending=False).head(50)

    st.dataframe(
        df_recent.style.format({
            'Price_At_Signal': '{:.2f}',
            'Return_30D': lambda x: f'{x:+.2f}%' if pd.notna(x) else '-',
            'Return_60D': lambda x: f'{x:+.2f}%' if pd.notna(x) else '-',
            'Return_90D': lambda x: f'{x:+.2f}%' if pd.notna(x) else '-',
        }, na_rep='-'),
        use_container_width=True, hide_index=True
    )
