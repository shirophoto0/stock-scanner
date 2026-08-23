# =============================================================
# theme.py
# ควบคุมหน้าตา (สี, ฟอนต์) ของแอปทั้งหมด รองรับ 2 โหมด: Dark กับ Light/Pastel
# ไฟล์นี้ไม่แตะต้องข้อมูลหรือการคำนวณใดๆ ในแอปเลย มีหน้าที่แค่ฉีด CSS เข้าไปเท่านั้น
# =============================================================
import streamlit as st

# --- ฟอนต์ที่ใช้ร่วมกันทั้ง 2 โหมด ---
FONT_IMPORT = """
@import url('https://fonts.googleapis.com/css2?family=Prompt:wght@400;500;600;700&family=Sarabun:wght@300;400;500;600;700&display=swap');
"""

# =============================================================
# 🌙 DARK MODE — "Trading Terminal"
# พื้นเทาเข้มอมน้ำเงิน + ทองแอนทีค + เขียวมิ้นท์/ส้มอมชมพู
# =============================================================
DARK_VARS = """
    --bg-primary: #12161D;
    --bg-secondary: #1A2029;
    --bg-tertiary: #232B37;
    --bg-card: #1A2029;
    --accent-primary: #C9A961;
    --accent-primary-soft: #E8D9AE;
    --accent-hover: #D9BC7A;
    --positive: #4ADE80;
    --negative: #F87171;
    --text-primary: #EAE7E0;
    --text-secondary: #9CA3AF;
    --text-on-accent: #12161D;
    --border-color: #2A3441;
    --shadow-color: rgba(0, 0, 0, 0.35);
"""

# =============================================================
# ☀️ LIGHT / PASTEL MODE — "Modern Wealth"
# พื้นขาวอมครีม + เขียวเสจ + พีชนุ่มๆ
# =============================================================
LIGHT_VARS = """
    --bg-primary: #FAF8F5;
    --bg-secondary: #FFFFFF;
    --bg-tertiary: #F1EEE8;
    --bg-card: #FFFFFF;
    --accent-primary: #7C9885;
    --accent-primary-soft: #C3D4C8;
    --accent-hover: #6B8574;
    --positive: #4E9A6E;
    --negative: #E0798A;
    --text-primary: #2D3142;
    --text-secondary: #6B7280;
    --text-on-accent: #FFFFFF;
    --border-color: #E5E1D8;
    --shadow-color: rgba(45, 49, 66, 0.08);
"""

# --- CSS หลัก (ใช้ CSS Variables ด้านบน ปรับสีตามโหมดที่เลือก) ---
BASE_CSS = """
<style>
%(font_import)s

:root {
    %(vars)s
}

/* ---------- พื้นหลังหลักของแอป ---------- */
[data-testid="stAppViewContainer"] {
    background-color: var(--bg-primary);
}
[data-testid="stHeader"] {
    background-color: var(--bg-primary);
}
[data-testid="stSidebar"] {
    background-color: var(--bg-secondary);
    border-right: 1px solid var(--border-color);
}

/* ---------- ฟอนต์ทั้งแอป ---------- */
html, body, [class*="css"] {
    font-family: 'Sarabun', sans-serif;
    color: var(--text-primary);
}
h1, h2, h3, h4, h5, h6 {
    font-family: 'Prompt', sans-serif !important;
    color: var(--text-primary) !important;
    font-weight: 600 !important;
}
p, span, div, label {
    color: var(--text-primary);
}

/* ---------- แท็บ (Tabs) ---------- */
[data-testid="stTabs"] button[role="tab"] {
    font-family: 'Prompt', sans-serif;
    color: var(--text-secondary);
    font-weight: 500;
}
[data-testid="stTabs"] button[aria-selected="true"] {
    color: var(--accent-primary) !important;
    font-weight: 600;
}
[data-testid="stTabs"] [data-baseweb="tab-highlight"] {
    background-color: var(--accent-primary) !important;
}
[data-testid="stTabs"] [data-baseweb="tab-border"] {
    background-color: var(--border-color) !important;
}

/* ---------- กล่องข้อมูล (Container ที่มีขอบ / Metric) ---------- */
[data-testid="stMetric"] {
    background-color: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: 14px;
    padding: 16px 18px;
    box-shadow: 0 2px 10px var(--shadow-color);
}
[data-testid="stMetricLabel"] {
    color: var(--text-secondary) !important;
    font-family: 'Sarabun', sans-serif !important;
}
[data-testid="stMetricValue"] {
    color: var(--text-primary) !important;
    font-family: 'Prompt', sans-serif !important;
}
[data-testid="stMetricDelta"] svg {
    display: inline;
}

div[data-testid="stVerticalBlockBorderWrapper"] {
    border-color: var(--border-color) !important;
    border-radius: 14px !important;
}

/* ---------- ปุ่ม ---------- */
.stButton > button, .stFormSubmitButton > button {
    font-family: 'Prompt', sans-serif;
    border-radius: 10px;
    border: 1px solid var(--accent-primary);
    color: var(--accent-primary);
    background-color: transparent;
    transition: all 0.15s ease-in-out;
}
.stButton > button:hover, .stFormSubmitButton > button:hover {
    background-color: var(--accent-primary);
    color: var(--text-on-accent);
    border-color: var(--accent-primary);
}
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {
    background-color: var(--accent-primary);
    color: var(--text-on-accent);
    border: none;
}
.stButton > button[kind="primary"]:hover, .stFormSubmitButton > button[kind="primary"]:hover {
    background-color: var(--accent-hover);
}

/* ---------- ช่องกรอกข้อมูล / Dropdown (กล่องตอนปิด) ---------- */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stDateInput"] input,
[data-baseweb="select"] > div,
[data-testid="stSelectbox"] div[data-baseweb="select"] {
    background-color: var(--bg-tertiary) !important;
    border-color: var(--border-color) !important;
    color: var(--text-primary) !important;
    border-radius: 8px !important;
}

/* ---------- เมนูตัวเลือกตอนกดเปิด Dropdown (Popup/Listbox) ---------- */
/* จุดนี้แยกจากกล่องตอนปิดด้านบน เพราะ Streamlit เปิดเมนูเป็นชั้นลอยแยกต่างหาก (Popover) */
div[data-baseweb="popover"] [data-baseweb="menu"],
ul[data-baseweb="menu"],
div[role="listbox"] {
    background-color: var(--bg-tertiary) !important;
    border: 1px solid var(--border-color) !important;
}
li[role="option"], div[role="option"] {
    background-color: var(--bg-tertiary) !important;
    color: var(--text-primary) !important;
}
li[role="option"]:hover, div[role="option"]:hover,
li[aria-selected="true"], div[aria-selected="true"] {
    background-color: var(--accent-primary-soft) !important;
    color: var(--text-on-accent) !important;
}
/* ปุ่มตัวเลือกแบบ Radio / Segmented (เช่น "แสดงกราฟ" / "แสดงตาราง") */
[data-testid="stRadio"] label, [data-testid="stRadio"] p {
    color: var(--text-primary) !important;
}

/* ---------- ตาราง (Dataframe) ---------- */
[data-testid="stDataFrame"] {
    border: 1px solid var(--border-color);
    border-radius: 10px;
}

/* ---------- Expander ---------- */
[data-testid="stExpander"] {
    background-color: var(--bg-card);
    border: 1px solid var(--border-color) !important;
    border-radius: 12px !important;
}

/* ---------- สีเขียว/แดงสำหรับ ค่า Delta ของ Metric (กำไร/ขาดทุน) ---------- */
[data-testid="stMetricDelta"] {
    color: var(--text-secondary);
}

/* ---------- เส้นคั่น ---------- */
hr {
    border-color: var(--border-color) !important;
}
</style>
"""


def get_theme_colors():
    """
    🆕 คืนค่าสีของโหมดที่เลือกอยู่ตอนนี้ เป็น dict — ใช้กับจุดที่ CSS ธรรมดาเข้าไม่ถึง
    เช่น ตารางที่สร้างผ่าน pandas Styler (.style.set_properties()) ซึ่งต้องกำหนดสีเป็น
    inline style ตรงๆ ไม่สามารถใช้ CSS variable จากภายนอกอ้างอิงได้เสมอไป
    """
    mode = st.session_state.get("theme_mode", "dark")
    if mode == "dark":
        return {"bg": "#1A2029", "text": "#EAE7E0", "border": "#2A3441"}
    return {"bg": "#FFFFFF", "text": "#2D3142", "border": "#E5E1D8"}


def apply_theme():
    """
    ฉีด CSS ของโหมดที่เลือกอยู่ตอนนี้เข้าไปในหน้าเว็บ (เรียกครั้งเดียวตอนต้นของแอป)
    อ่านค่าจาก st.session_state['theme_mode'] ('dark' หรือ 'light') ถ้ายังไม่มีค่าจะใช้ 'dark' เป็นค่าเริ่มต้น
    """
    mode = st.session_state.get("theme_mode", "dark")
    theme_vars = DARK_VARS if mode == "dark" else LIGHT_VARS
    css = BASE_CSS % {"font_import": FONT_IMPORT, "vars": theme_vars}
    st.markdown(css, unsafe_allow_html=True)


def render_theme_toggle():
    """แสดงสวิตช์สลับโหมด Dark/Light ไว้ที่แถบด้านข้าง (Sidebar)"""
    current_mode = st.session_state.get("theme_mode", "dark")
    is_dark = current_mode == "dark"

    toggled_on = st.sidebar.toggle(
        "🌙 Dark Mode" if is_dark else "☀️ Light Mode",
        value=is_dark,
        key="theme_toggle_switch",
    )

    new_mode = "dark" if toggled_on else "light"
    if new_mode != current_mode:
        st.session_state["theme_mode"] = new_mode
        st.rerun()


def style_plotly(fig):
    """
    🆕 ทำให้พื้นหลังกราฟ Plotly โปร่งใส (โชว์สีพื้นหลังของแอปทะลุออกมาแทน) และปรับสีตัวอักษร/
    เส้นกริดให้เข้ากับโหมดสีที่เลือกอยู่ตอนนี้ ต้องเรียกฟังก์ชันนี้ครอบทุกกราฟก่อนแสดงผลด้วย
    st.plotly_chart() เพราะกราฟ Plotly มีพื้นหลังเป็นของตัวเอง ไม่ได้ปรับตาม CSS ของหน้าเว็บอัตโนมัติ
    """
    mode = st.session_state.get("theme_mode", "dark")
    text_color = "#EAE7E0" if mode == "dark" else "#2D3142"
    grid_color = "rgba(255,255,255,0.08)" if mode == "dark" else "rgba(45,49,66,0.08)"

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
    🆕 ทำให้พื้นหลังกราฟ Altair โปร่งใส และปรับสีตัวอักษร/แกน/เส้นกริดให้เข้ากับโหมดสีที่เลือกอยู่
    (Altair เป็นคนละไลบรารีกับ Plotly ใช้คนละวิธีตั้งค่าสี ต้องมีฟังก์ชันของตัวเองแยกจาก style_plotly)
    ต้องเรียกครอบ "กราฟระดับบนสุด" เท่านั้น (หลังรวมหลายเลเยอร์เข้าด้วยกันแล้ว เช่น chart1 + chart2)
    """
    mode = st.session_state.get("theme_mode", "dark")
    text_color = "#EAE7E0" if mode == "dark" else "#2D3142"
    grid_color = "#2A3441" if mode == "dark" else "#E5E1D8"

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
