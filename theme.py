# =============================================================
# theme.py
# ปรับแต่งส่วนที่ธีมจริงของ Streamlit (.streamlit/config.toml) ควบคุมไม่ถึง
# ได้แก่ ฟอนต์ไทยที่กำหนดเอง และสีของกราฟ Plotly/Altair (กราฟไม่ได้ตามธีมของ Streamlit อัตโนมัติ)
#
# 🔧 หมายเหตุสำคัญ: เดิมไฟล์นี้เคยพยายามเขียน CSS ควบคุมสีพื้นหลัง/สีตัวหนังสือของทั้งแอปเอง
# (รวมถึงแท็บ, dropdown, ตาราง) แต่พบว่าไปแข่งกับสไตล์ภายในของ Streamlit เองไม่ได้ผลจริง
# (โดยเฉพาะ dropdown และตารางที่เป็นองค์ประกอบพิเศษ CSS ทั่วไปเข้าไม่ถึง)
# ตอนนี้เปลี่ยนมาตั้งค่าธีมจริงผ่าน .streamlit/config.toml แทน (เข้าถึงได้ลึกกว่ามาก ถูกต้องกว่า)
# ไฟล์นี้จึงเหลือหน้าที่แค่เสริมความสวยงามในจุดที่ config.toml ควบคุมไม่ถึงเท่านั้น
# =============================================================
import streamlit as st

# --- ฟอนต์ที่ใช้ทั้งแอป ---
FONT_IMPORT = """
@import url('https://fonts.googleapis.com/css2?family=Prompt:wght@400;500;600;700&family=Sarabun:wght@300;400;500;600;700&display=swap');
"""

# สีอ้างอิง (ให้ตรงกับค่าใน .streamlit/config.toml) ใช้กับจุดที่ config.toml ควบคุมไม่ถึง
# เช่น กราฟ Plotly/Altair และตารางที่สร้างผ่าน pandas Styler
THEME_COLORS = {
    "bg": "#FFFFFF",
    "text": "#2D3142",
    "text_secondary": "#6B7280",
    "border": "#E5E1D8",
    "accent": "#7C9885",
}

BASE_CSS = """
<style>
%(font_import)s

html, body, [class*="css"] {
    font-family: 'Sarabun', sans-serif;
}
h1, h2, h3, h4, h5, h6 {
    font-family: 'Prompt', sans-serif !important;
    font-weight: 600 !important;
}
[data-testid="stTabs"] button[role="tab"] {
    font-family: 'Prompt', sans-serif;
    font-weight: 500;
}
.stButton > button, .stFormSubmitButton > button {
    font-family: 'Prompt', sans-serif;
    border-radius: 10px;
}
[data-testid="stMetric"] {
    border: 1px solid rgba(45, 49, 66, 0.08);
    border-radius: 14px;
    padding: 16px 18px;
    box-shadow: 0 2px 10px rgba(45, 49, 66, 0.06);
}
[data-testid="stMetricValue"] {
    font-family: 'Prompt', sans-serif !important;
}
</style>
"""


def get_theme_colors():
    """
    คืนค่าสีอ้างอิงของธีม — ใช้กับจุดที่ CSS/config.toml เข้าไม่ถึง
    เช่น ตารางที่สร้างผ่าน pandas Styler (.style.set_properties()) ซึ่งต้องกำหนดสีเป็น
    inline style ตรงๆ
    """
    return {"bg": THEME_COLORS["bg"], "text": THEME_COLORS["text"], "border": THEME_COLORS["border"]}


def apply_theme():
    """ฉีดฟอนต์ไทยและสไตล์เสริมเล็กน้อยที่ config.toml ควบคุมไม่ถึง (เรียกครั้งเดียวตอนต้นของแอป)"""
    css = BASE_CSS % {"font_import": FONT_IMPORT}
    st.markdown(css, unsafe_allow_html=True)


def style_plotly(fig):
    """
    ทำให้พื้นหลังกราฟ Plotly โปร่งใส และปรับสีตัวอักษร/เส้นกริดให้อ่านง่ายบนพื้นหลังของแอป
    (กราฟ Plotly มีพื้นหลังเป็นของตัวเอง ไม่ได้ปรับตามธีมของ Streamlit อัตโนมัติ)
    """
    text_color = THEME_COLORS["text"]
    grid_color = "rgba(45,49,66,0.08)"

    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color=text_color, family="Sarabun, sans-serif"),
        legend=dict(font=dict(color=text_color)),
    )
    fig.update_xaxes(gridcolor=grid_color, zerolinecolor=grid_color, color=text_color)
    fig.update_yaxes(gridcolor=grid_color, zerolinecolor=grid_color, color=text_color)
    return fig


def style_altair(chart):
    """
    ทำให้พื้นหลังกราฟ Altair โปร่งใส และปรับสีตัวอักษร/แกน/เส้นกริดให้อ่านง่ายบนพื้นหลังของแอป
    ต้องเรียกครอบ "กราฟระดับบนสุด" เท่านั้น (หลังรวมหลายเลเยอร์เข้าด้วยกันแล้ว เช่น chart1 + chart2)
    """
    text_color = THEME_COLORS["text"]
    grid_color = THEME_COLORS["border"]

    return chart.properties(
        background='transparent'
    ).configure_view(
        strokeWidth=0
    ).configure_axis(
        labelColor=text_color,
        titleColor=text_color,
        gridColor=grid_color,
        domainColor=grid_color,
        labelFont='Sarabun',
        titleFont='Sarabun',
    ).configure_legend(
        labelColor=text_color,
        titleColor=text_color,
        labelFont='Sarabun',
        titleFont='Sarabun',
    ).configure_title(
        color=text_color,
        font='Prompt',
    )
