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

/* ---------- ปรับสำหรับจอมือถือ/จอแคบ (กว้างไม่เกิน 640px) ---------- */
@media (max-width: 640px) {
    /* แท็บมี 3 ชั้นซ้อนกัน ข้อความไทยยาวๆ อาจล้นจอ ลดขนาดตัวอักษร/ระยะห่างลง */
    [data-testid="stTabs"] button[role="tab"] {
        font-size: 13px !important;
        padding: 8px 10px !important;
    }
    [data-testid="stTabs"] button[role="tab"] p {
        font-size: 13px !important;
    }
    /* กล่อง Metric แคบลง ลด padding เพื่อให้ตัวเลขไม่ล้นกรอบ */
    [data-testid="stMetric"] {
        padding: 10px 12px;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.4rem !important;
    }
    /* หัวข้อใหญ่ (h1) ลดขนาดลงให้พอดีจอ ไม่ตัดคำแปลกๆ */
    h1 {
        font-size: 1.5rem !important;
    }
}
</style>
"""


def render_metric_card(col, label, value, icon="", delta=None, delta_positive=None, caption=None, updated_date=None):
    """
    🆕 การ์ดตัวเลขสไตล์เดียวกับหน้าภาพรวม Net Worth (กรอบมน/เงา/ฟอนต์) ใช้แทน st.metric()
    ธรรมดาได้ทุกจุดในแอป เพื่อให้หน้าตาไปในทิศทางเดียวกันทั้งหมด
    - icon: ไอคอนหน้าป้ายชื่อ (ใส่หรือไม่ใส่ก็ได้)
    - value: ค่าที่ต้องการโชว์ตัวใหญ่ (ใส่เป็นข้อความที่จัดรูปแบบมาแล้ว เช่น "1,234.00 ฿")
    - delta + delta_positive: badge เล็กๆ ใต้ตัวเลข (True=เขียว, False=แดง, None=เทาเฉยๆ)
    - caption: ข้อความหมายเหตุเล็กๆ สีเทา ต่อท้ายล่างสุด
    - updated_date: วันที่บันทึกข้อมูลล่าสุด (datetime/date หรือสตริง) โชว์เป็นข้อความเล็กๆ
      มุมขวาบนของการ์ด รูปแบบ "@DD/MM/YY" ใช้กับการ์ดที่มาจากข้อมูลกรอกมือ ให้รู้ว่าข้อมูลเก่าแค่ไหน
    """
    icon_html = f'<span style="font-size:18px;margin-right:6px;">{icon}</span>' if icon else ''
    updated_html = ""
    if updated_date:
        updated_html = (
            f'<span style="position:absolute;top:12px;right:16px;color:#9CA3AF;font-size:0.68em;'
            f'font-family:\'Sarabun\',sans-serif;">{format_updated_badge(updated_date)}</span>'
        )
    delta_html = ""
    if delta is not None:
        if delta_positive is True:
            color, bg, arrow = "#4E9A6E", "rgba(78,154,110,0.12)", "↑"
        elif delta_positive is False:
            color, bg, arrow = "#E0798A", "rgba(224,121,138,0.12)", "↓"
        else:
            color, bg, arrow = "#6B7280", "rgba(107,114,128,0.12)", ""
        delta_html = (
            f'<span style="display:inline-block;background:{bg};color:{color};'
            f'font-size:0.78em;font-weight:600;padding:2px 9px;border-radius:12px;margin-top:8px;">'
            f'{arrow} {delta}</span>'
        )
    caption_html = f'<div style="color:#9CA3AF;font-size:0.72em;margin-top:6px;">{caption}</div>' if caption else ''
    # 🔧 แก้บั๊ก: เดิมการ์ดสูงตามเนื้อหาข้างในเอง การ์ดที่มีแบดจ์/หมายเหตุจึงสูงกว่าการ์ดที่ไม่มี
    # ทำให้แถวเดียวกันสูงไม่เท่ากัน (ดูไม่เรียบร้อย) ตอนนี้กำหนด min-height ให้ทุกการ์ดสูงเท่ากัน
    # เสมอ (สูงพอสำหรับการ์ดที่มีทั้งแบดจ์และหมายเหตุ) การ์ดที่เนื้อหาน้อยกว่าจะมีที่ว่างด้านล่างแทน
    card_html = (
        '<div style="position:relative;background:#FFFFFF;border:1px solid #E5E1D8;border-radius:14px;'
        'padding:16px 18px;box-shadow:0 2px 10px rgba(45,49,66,0.06);margin-bottom:14px;'
        'min-height:128px;box-sizing:border-box;">'
        f'{updated_html}'
        f'<div style="color:#6B7280;font-size:0.85em;font-family:\'Sarabun\',sans-serif;margin-bottom:6px;">{icon_html}{label}</div>'
        f'<div style="font-family:\'Prompt\',sans-serif;font-size:1.55em;font-weight:600;color:#2D3142;">{value}</div>'
        f'{delta_html}'
        f'{caption_html}'
        '</div>'
    )
    col.markdown(card_html, unsafe_allow_html=True)


def format_updated_badge(updated_date):
    """
    แปลงวันที่ (datetime/date/สตริง หลายรูปแบบ) ให้เป็นข้อความ "@DD/MM/YY" สำหรับ badge มุมขวาบน
    ของการ์ด ถ้าแปลงไม่ได้ (เช่นสตริงรูปแบบแปลกๆ) จะโชว์ค่าที่ส่งมาตรงๆ แทน ไม่ทำให้การ์ดพัง
    """
    import datetime as _dt

    if isinstance(updated_date, (_dt.datetime, _dt.date)):
        return f"@{updated_date.strftime('%d/%m/%y')}"

    text = str(updated_date).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return f"@{_dt.datetime.strptime(text, fmt).strftime('%d/%m/%y')}"
        except ValueError:
            continue
    return f"@{text}"


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
