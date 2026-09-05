# =============================================================
# tab_gold.py
# แท็บจัดการพอร์ตทองคำ
# 🆕 จัดระเบียบใหม่ทั้งหมด (เดิมมีหน้าเดียว ปนกันทั้งทองจริง/เทรด/สะสม ไม่รองรับการเปิด-ปิด
# สถานะเทรดจริงแบบ Long/Short และต้นทุนเฉลี่ยทองคำแท่งคำนวณผิด เพราะทุกครั้งที่ซื้อเพิ่มจะเซ็ต
# ต้นทุนใหม่จากราคาตลาด ณ ตอนนั้นทับของเดิม ไม่ใช่ต้นทุนถัวเฉลี่ยจริง):
# แยกเป็น 4 แท็บย่อยตามแบบเดียวกับ TFEX (Dashboard ขึ้นก่อน ตามด้วยแท็บใช้งานจริง)
#   - 📊 Dashboard: ภาพรวมทุกประเภท (มูลค่ารวม, สัดส่วน, กำไรสะสมจากเทรด, สถานะที่เปิดอยู่)
#   - 🪙 ทองคำแท่ง/รูปพรรณ (ถือครองจริง): ล็อกซื้อ/ขายทีละรายการ คำนวณต้นทุนเฉลี่ยถ่วงน้ำหนักจริง
#   - 📈 เทรด Short/Long: เปิด/ปิดสถานะแบบเดียวกับ TFEX (มีกำไร/ขาดทุนตามจริงเมื่อปิดสถานะ)
#   - 🐷 ซื้อสะสม (DCA): บันทึกซื้อสะสมเป็นงวดๆ เทียบต้นทุนเฉลี่ย DCA กับราคาตลาด
# ข้อมูลเก็บคนละชีตกัน (Gold_Physical, Gold_Trades, Gold_DCA) แยกจาก Gold_Portfolio เดิม
# =============================================================
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
from gspread.exceptions import WorksheetNotFound
from backend_functions import (
    get_gsheet_client, get_cached_spreadsheet, get_cached_worksheet, get_worksheet_safely,
    get_active_sheet_name, load_data, fetch_live_gold_price,
)
from theme import render_metric_card, style_plotly

GOLD_BAHT_TO_GRAM = 15.244  # 1 บาททองคำ = 15.244 กรัม (มาตรฐานสมาคมค้าทองคำไทย)


# 🔧 แก้บั๊ก 429: เดิมแท็บนี้เก็บข้อมูลทองทุกประเภทไว้ในชีตเดียว (Gold_Portfolio) พอแยกเป็น 3 ชีต
# (Gold_Physical/Gold_Trades/Gold_DCA) จำนวนครั้งที่ต้องอ่าน Google Sheets API ต่อการเปิดแท็บนี้
# 1 ครั้งเพิ่มขึ้นเป็น 3 เท่า ทั้งที่ load_data() มี @st.cache_data(ttl=60) อยู่แล้ว แต่ 60 วินาที
# สั้นเกินไปเมื่อมีผู้ใช้หลายคนเข้าแท็บนี้พร้อมกัน (ใช้ service account เดียวกันทั้งแอป จึงชนโควตา
# "Read requests per minute" ร่วมกัน) ตอนนี้ห่อด้วยแคชอีกชั้นที่ TTL ยาวกว่า (3 นาที) เฉพาะจุดนี้
# ลดจำนวนครั้งที่ยิง API ของ 3 ชีตนี้ลงได้อีก โดยไม่ต้องแก้ TTL ของ load_data() ที่จุดอื่นทั้งแอปใช้ร่วมกัน
@st.cache_data(ttl=180, show_spinner=False)
def _load_gold_sheet_cached(sheet_name, active_sheet_name):
    return load_data(sheet_name, active_sheet_name)


# =============================================================
# ส่วนที่ 1: ราคาทองอ้างอิงสด (ย้ายมาจากโค้ดเดิม ไม่เปลี่ยน logic)
# =============================================================
def _get_gold_price_by_scraping():
    if 'scraped_gold_date' in st.session_state:
        last_update = st.session_state['scraped_gold_date']
        _cached_bar = st.session_state.get('scraped_gold_bar')
        _cached_jewelry = st.session_state.get('scraped_gold_jewelry')
        _looks_like_stale_fallback = _cached_bar == 68300.0 or _cached_jewelry == 69100.0
        if (
            isinstance(last_update, datetime) and (datetime.now() - last_update) < pd.Timedelta(hours=3)
            and _cached_bar is not None and _cached_jewelry is not None
            and not _looks_like_stale_fallback
        ):
            st.session_state['gold_price_status'] = f"✅ ใช้ราคาที่แคชไว้ (ดึงสดล่าสุดเมื่อ {last_update.strftime('%H:%M:%S')})"
            return _cached_bar, _cached_jewelry

    bar_val, jewelry_val, debug_msg = fetch_live_gold_price()

    if bar_val is not None and jewelry_val is not None:
        st.session_state['scraped_gold_date'] = datetime.now()
        st.session_state['scraped_gold_bar'] = bar_val
        st.session_state['scraped_gold_jewelry'] = jewelry_val
        st.session_state['gold_price_status'] = f"✅ ดึงราคาสดสำเร็จ ({datetime.now().strftime('%H:%M:%S')})"
        return bar_val, jewelry_val

    st.session_state['gold_price_status'] = f"⚠️ ดึงราคาสดไม่สำเร็จ (สาเหตุ: {debug_msg}) กำลังใช้ราคาสำรอง/ราคาเก่าที่มีอยู่แทน"
    fallback_bar = st.session_state.get('scraped_gold_bar', 68300.0)
    fallback_jewelry = st.session_state.get('scraped_gold_jewelry', 69100.0)
    return fallback_bar, fallback_jewelry


def _render_gold_price_ticker():
    """แสดงราคาทองอ้างอิงสด + ปุ่มรีเฟรช คืนค่า (ราคาทองคำแท่ง, ราคาทองรูปพรรณ) ต่อบาททองคำ"""
    _refresh_col1, _refresh_col2 = st.columns([3, 1])
    with _refresh_col2:
        if st.button("🔄 รีเฟรชราคาทองคำ", use_container_width=True):
            for _k in ['scraped_gold_date', 'scraped_gold_bar', 'scraped_gold_jewelry', 'gold_price_status']:
                st.session_state.pop(_k, None)
            st.rerun()

    ref_gold_bar, ref_gold_jewelry = _get_gold_price_by_scraping()

    with _refresh_col1:
        _status_msg = st.session_state.get('gold_price_status', "✅ ดึงราคาสดสำเร็จล่าสุด")
        if "⚠️" in _status_msg and "| ตัวอย่างเนื้อหาที่ได้จริง:" in _status_msg:
            _short_part, _preview_part = _status_msg.split("| ตัวอย่างเนื้อหาที่ได้จริง:", 1)
            st.warning(_short_part.strip())
            st.code(_preview_part.strip(), language=None)
        elif "⚠️" in _status_msg:
            st.warning(_status_msg)
        else:
            st.success(_status_msg)

    c1, c2 = st.columns(2)
    render_metric_card(c1, "ราคาทองคำแท่ง (Scraped)", f"{ref_gold_bar:,.2f} ฿ / บาททอง", icon="📌")
    render_metric_card(c2, "ราคาทองรูปพรรณ (Scraped)", f"{ref_gold_jewelry:,.2f} ฿ / บาททอง", icon="📌")
    return ref_gold_bar, ref_gold_jewelry


def _spot_price_per_unit(gold_type, ref_gold_bar, ref_gold_jewelry):
    """ราคาต่อ 'หน่วยที่ใช้กรอกน้ำหนัก' ของประเภททองนั้นๆ (ทองคำแท่งกรอกเป็นกรัม เลยต้องแปลงจาก
    ราคาต่อบาททองคำ /15.244 ก่อน ส่วนทองรูปพรรณกรอกเป็นบาททองคำอยู่แล้วใช้ราคาตรงๆ ได้เลย)"""
    if gold_type == "ทองคำแท่ง":
        return ref_gold_bar / GOLD_BAHT_TO_GRAM
    return ref_gold_jewelry


# =============================================================
# ส่วนที่ 2: เขียนข้อมูลลง Google Sheets (สร้างชีต+หัวตารางให้อัตโนมัติถ้ายังไม่มี)
# =============================================================
def _get_or_create_worksheet(sheet_name, columns):
    client = get_gsheet_client()
    spreadsheet = get_cached_spreadsheet(client, get_active_sheet_name())
    try:
        return spreadsheet.worksheet(sheet_name)
    except WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=max(10, len(columns)))
        sheet.append_row(columns)
        return sheet


def _append_rows(sheet_name, columns, rows):
    try:
        sheet = _get_or_create_worksheet(sheet_name, columns)
        if not sheet.row_values(1):
            sheet.append_row(columns)
        sheet.append_rows(rows)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"⚠️ บันทึกข้อมูลไม่สำเร็จ: {e}")
        return False


# =============================================================
# ส่วนที่ 3: 🪙 ทองคำแท่ง/รูปพรรณ (ถือครองจริง) — ล็อกซื้อ/ขาย + ต้นทุนเฉลี่ยถ่วงน้ำหนักจริง
# =============================================================
GOLD_PHYSICAL_COLS = ["Txn_ID", "Date", "Gold_Type", "Action", "Weight", "Unit", "Price_Per_Unit", "Total_Value", "Note"]


def _migrate_legacy_physical_gold_if_needed(physical_df):
    """
    🆕 แก้บั๊ก: หลังจัดระเบียบแท็บนี้ใหม่ ข้อมูลทองคำแท่ง/ทองรูปพรรณที่ผู้ใช้เคยบันทึกไว้จริงในชีต
    Gold_Portfolio เดิม (ก่อนแยกเป็น Gold_Physical/Gold_Trades/Gold_DCA) หายไปจากหน้าจอทันที เพราะ
    แท็บนี้เปลี่ยนไปอ่านจากชีตใหม่ล้วนๆ ที่ยังไม่เคยมีข้อมูลเลย — ไม่ใช่ข้อมูลหายจริง แค่ยังไม่ได้
    ย้ายมาเก็บที่ใหม่ ตอนนี้ถ้า Gold_Physical ยังว่างสนิท (ยังไม่เคยย้าย/ยังไม่เคยบันทึกในระบบใหม่)
    แต่ Gold_Portfolio เดิมยังมีแถวประเภท "ทองคำแท่ง"/"ทองรูปพรรณ" อยู่ จะย้ายเข้ามาให้อัตโนมัติ
    ครั้งเดียว (แต่ละแถวเดิมคือ "ยอดสุทธิ" ที่ถือรวมอยู่แล้ว ไม่ใช่ประวัติทีละรายการซื้อ จึงแปลงเป็น
    1 รายการ "ซื้อ" ต่อแถว โดยใช้ราคาต้นทุนเฉลี่ยเดิมเป็นราคาต่อหน่วย น้ำหนัก/ต้นทุนเฉลี่ยรวมที่ได้
    จึงตรงกับของเดิมเป๊ะ) ส่วนประเภท "เทรดทอง / กองทุนทอง" เดิม ดูฟังก์ชัน
    _migrate_legacy_fund_gold_if_needed() ด้านล่างแทน (ย้ายเข้า Gold_DCA แยกต่างหาก)
    """
    if not physical_df.empty or st.session_state.get('_gold_physical_migration_checked'):
        return physical_df
    st.session_state['_gold_physical_migration_checked'] = True

    try:
        client = get_gsheet_client()
        # 🔧 แก้บั๊ก 429: เดิมเรียก .worksheet() ตรงๆ ทุกครั้ง (ไม่ผ่านแคช) ยิง API เพิ่มโดยไม่จำเป็น
        # เปลี่ยนมาใช้ get_cached_worksheet() ที่แคช worksheet object ไว้ 5 นาทีเหมือนจุดอื่นในแอป
        legacy_sheet = get_cached_worksheet(client, get_active_sheet_name(), 'Gold_Portfolio')
        legacy_records = legacy_sheet.get_all_records()
    except Exception:
        return physical_df

    new_rows = []
    for row in legacy_records:
        g_type = str(row.get('ประเภท', '')).strip()
        if g_type not in ('ทองคำแท่ง', 'ทองรูปพรรณ'):
            continue
        raw_weight = row.get('น้ำหนัก/มูลค่าซื้อ', row.get('น้ำหนัก', 0))
        try:
            weight = float(str(raw_weight).replace(',', '').strip() or 0)
        except (ValueError, TypeError):
            weight = 0.0
        if weight <= 0:
            continue
        raw_price = row.get('ราคาต้นทุนเฉลี่ย', 0)
        try:
            price = float(str(raw_price).replace(',', '').strip() or 0)
        except (ValueError, TypeError):
            price = 0.0
        unit = str(row.get('หน่วย', '')).strip() or ('กรัม' if g_type == 'ทองคำแท่ง' else 'บาททองคำ')
        note = str(row.get('หมายเหตุ', '')).strip()
        date_str = str(row.get('วันที่บันทึก', '')).split(' ')[0] or datetime.now().strftime('%Y-%m-%d')
        new_rows.append([
            f"GP-MIGRATED-{len(new_rows) + 1}", date_str, g_type, "ซื้อ", weight, unit, price, round(weight * price, 2),
            f"{note} (ย้ายมาจากระบบเดิม)".strip(),
        ])

    if not new_rows:
        return physical_df

    if _append_rows("Gold_Physical", GOLD_PHYSICAL_COLS, new_rows):
        st.info(f"📦 นำเข้าข้อมูลทองคำแท่ง/รูปพรรณที่เคยบันทึกไว้ {len(new_rows)} รายการจากระบบเดิมให้อัตโนมัติแล้วครับ")
        return load_data("Gold_Physical", get_active_sheet_name())
    return physical_df


def _migrate_legacy_fund_gold_if_needed(dca_df):
    """
    🆕 แก้บั๊ก: แถวประเภทเดิม "เทรดทอง / กองทุนทอง" (เช่น กองทุนทองคำ SCBGOLDH — มีจำนวนหน่วยสะสม,
    ต้นทุนเฉลี่ย/หน่วย, ราคาตลาดปัจจุบัน/หน่วย แต่ไม่มีทิศทาง Long/Short) ตรงกับความหมายของ
    "ซื้อสะสม (DCA)" มากกว่าเทรด Short/Long จึงย้ายเข้า Gold_DCA แทน (ตอนแรกไม่ได้ย้ายอัตโนมัติ
    เพราะกลัวเดา intent ผิด แต่ทบทวนแล้วเห็นว่าตรงกับ DCA ชัดเจนกว่า) — ปัญหาคือกองทุนพวกนี้มีราคา
    NAV ของตัวเอง ไม่ได้ผูกกับราคาทองสดเหมือนทองคำแท่ง/รูปพรรณจริง ถ้าใช้ราคาทองสดตีมูลค่าจะผิดมหาศาล
    จึงย้ายมาพร้อมตั้งค่าคอลัมน์ Reference_Price ด้วย (จากราคาตลาดปัจจุบันเดิม) ให้ _compute_dca_summary()
    รู้ว่าต้องตีมูลค่ากลุ่มนี้จากราคานี้แทนราคาทองสด (ดูคอมเมนต์ที่ GOLD_DCA_COLS ด้านล่าง)
    """
    if not dca_df.empty or st.session_state.get('_gold_dca_migration_checked'):
        return dca_df
    st.session_state['_gold_dca_migration_checked'] = True

    try:
        client = get_gsheet_client()
        legacy_sheet = get_cached_worksheet(client, get_active_sheet_name(), 'Gold_Portfolio')
        legacy_records = legacy_sheet.get_all_records()
    except Exception:
        return dca_df

    new_rows = []
    for row in legacy_records:
        g_type = str(row.get('ประเภท', '')).strip()
        if g_type != 'เทรดทอง / กองทุนทอง':
            continue
        raw_units = row.get('น้ำหนัก/มูลค่าซื้อ', 0)
        try:
            units = float(str(raw_units).replace(',', '').strip() or 0)
        except (ValueError, TypeError):
            units = 0.0
        if units <= 0:
            continue
        raw_cost = row.get('ราคาต้นทุนเฉลี่ย', 0)
        try:
            cost_per_unit = float(str(raw_cost).replace(',', '').strip() or 0)
        except (ValueError, TypeError):
            cost_per_unit = 0.0
        raw_current = row.get('ราคาตลาดปัจจุบัน', 0)
        try:
            current_price = float(str(raw_current).replace(',', '').strip() or 0)
        except (ValueError, TypeError):
            current_price = 0.0
        note = str(row.get('หมายเหตุ', '')).strip() or 'กองทุนทอง'
        date_str = str(row.get('วันที่บันทึก', '')).split(' ')[0] or datetime.now().strftime('%Y-%m-%d')
        amount_invested = round(units * cost_per_unit, 2)
        new_rows.append([
            f"DCA-MIGRATED-{len(new_rows) + 1}", date_str, amount_invested, cost_per_unit, units,
            f"{note} (ย้ายมาจากระบบเดิม)", current_price,
        ])

    if not new_rows:
        return dca_df

    if _append_rows("Gold_DCA", GOLD_DCA_COLS, new_rows):
        st.info(f"📦 นำเข้าข้อมูลกองทุนทอง/เทรดทองที่เคยบันทึกไว้ {len(new_rows)} รายการจากระบบเดิมเป็นข้อมูล DCA ให้อัตโนมัติแล้วครับ")
        return load_data("Gold_DCA", get_active_sheet_name())
    return dca_df


def _compute_physical_summary(physical_df, ref_gold_bar, ref_gold_jewelry):
    """เดินไล่ทีละรายการตามลำดับวันที่ (ซื้อ = ถัวเฉลี่ยต้นทุนใหม่ / ขาย = รับรู้กำไรจากส่วนต่างกับ
    ต้นทุนเฉลี่ย ณ ตอนนั้น ไม่แตะต้นทุนเฉลี่ยของที่เหลือ) แยกกลุ่มตาม (ประเภททอง, หมายเหตุ)"""
    groups = {}
    if not physical_df.empty:
        df = physical_df.copy()
        df["Weight"] = pd.to_numeric(df.get("Weight", 0), errors="coerce").fillna(0.0)
        df["Price_Per_Unit"] = pd.to_numeric(df.get("Price_Per_Unit", 0), errors="coerce").fillna(0.0)
        if "Date" in df.columns:
            df["_sort_date"] = pd.to_datetime(df["Date"], errors="coerce")
            df = df.sort_values("_sort_date")
        for _, row in df.iterrows():
            g_type = str(row.get("Gold_Type", "")).strip()
            note = str(row.get("Note", "")).strip()
            action = str(row.get("Action", "")).strip()
            unit = str(row.get("Unit", "")).strip()
            weight = float(row["Weight"])
            price = float(row["Price_Per_Unit"])
            key = (g_type, note)
            g = groups.setdefault(key, {"weight": 0.0, "avg_cost": 0.0, "realized": 0.0, "unit": unit})
            if action == "ซื้อ":
                new_weight = g["weight"] + weight
                if new_weight > 0:
                    g["avg_cost"] = (g["weight"] * g["avg_cost"] + weight * price) / new_weight
                g["weight"] = new_weight
            elif action == "ขาย":
                sell_w = min(weight, g["weight"])
                g["realized"] += (price - g["avg_cost"]) * sell_w
                g["weight"] -= sell_w
            if unit:
                g["unit"] = unit

    rows = []
    total_market = total_cost = total_realized = total_unrealized = 0.0
    for (g_type, note), g in groups.items():
        if g["weight"] <= 0.0001 and g["realized"] == 0.0:
            continue
        spot = _spot_price_per_unit(g_type, ref_gold_bar, ref_gold_jewelry)
        market_val = g["weight"] * spot
        cost_val = g["weight"] * g["avg_cost"]
        unrealized = market_val - cost_val
        rows.append({
            "ประเภท": g_type, "หมายเหตุ": note, "น้ำหนักคงเหลือ": g["weight"], "หน่วย": g["unit"],
            "ต้นทุนเฉลี่ย/หน่วย": g["avg_cost"], "มูลค่าตลาด": market_val,
            "กำไร/ขาดทุน (ยังไม่ขาย)": unrealized, "กำไร/ขาดทุน (รับรู้แล้ว)": g["realized"],
        })
        total_market += market_val
        total_cost += cost_val
        total_unrealized += unrealized
        total_realized += g["realized"]

    return {
        "holdings_df": pd.DataFrame(rows),
        "total_market_value": total_market,
        "total_cost_value": total_cost,
        "total_unrealized_pl": total_unrealized,
        "total_realized_pl": total_realized,
    }


def _render_physical_tab(physical_df, ref_gold_bar, ref_gold_jewelry, summary):
    st.subheader("🪙 ทองคำแท่ง/ทองรูปพรรณ (ถือครองจริง)")
    st.caption("บันทึกทุกครั้งที่ซื้อ/ขายทองจริง ระบบคำนวณต้นทุนเฉลี่ยแบบถ่วงน้ำหนักให้อัตโนมัติ "
               "(ราคาต่อหน่วยกรอกได้เอง เผื่อบันทึกย้อนหลังหรือซื้อคนละราคากับตลาดวันนี้)")

    with st.form("gold_physical_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            g_date = st.date_input("วันที่ทำรายการ", key="gp_date")
            g_type = st.selectbox("ประเภททอง", ["ทองคำแท่ง", "ทองรูปพรรณ"], key="gp_type")
            action = st.selectbox("รายการ", ["ซื้อ", "ขาย"], key="gp_action")
        with c2:
            is_bar = g_type == "ทองคำแท่ง"
            unit_label = "น้ำหนัก (กรัม)" if is_bar else "น้ำหนัก (บาททองคำ)"
            weight = st.number_input(unit_label, min_value=0.0, step=(1.0 if is_bar else 0.25), key="gp_weight")
            default_price = _spot_price_per_unit(g_type, ref_gold_bar, ref_gold_jewelry)
            price = st.number_input(
                f"ราคาต่อหน่วย ({'บาท/กรัม' if is_bar else 'บาท/บาททองคำ'})",
                min_value=0.0, value=round(default_price, 2), step=1.0, key="gp_price",
                help="ค่าเริ่มต้นคือราคาตลาดสดวันนี้ แก้ไขได้ถ้าซื้อ/ขายไปคนละราคา หรือบันทึกย้อนหลัง",
            )
        with c3:
            note = st.text_input("หมายเหตุ / ร้าน", placeholder="เช่น ฮั่วเซ่งเฮง", key="gp_note")
            st.metric("มูลค่ารวมโดยประมาณ", f"{weight * price:,.2f} ฿")

        if st.form_submit_button("➕ บันทึกรายการ"):
            if weight <= 0:
                st.error("กรุณากรอกน้ำหนักมากกว่า 0")
            else:
                unit = "กรัม" if g_type == "ทองคำแท่ง" else "บาททองคำ"
                new_row = [
                    f"GP-{pd.Timestamp.now().strftime('%Y%m%d%H%M%S')}", str(g_date), g_type, action,
                    weight, unit, price, weight * price, note,
                ]
                if _append_rows("Gold_Physical", GOLD_PHYSICAL_COLS, [new_row]):
                    st.toast("บันทึกรายการทองจริงเรียบร้อย!", icon="✅")
                    st.rerun()

    st.divider()
    st.subheader("📊 สรุปการถือครองปัจจุบัน (แยกตามประเภท+หมายเหตุ)")
    holdings_df = summary["holdings_df"]
    if not holdings_df.empty:
        st.dataframe(
            holdings_df.style.format({
                "น้ำหนักคงเหลือ": "{:,.2f}", "ต้นทุนเฉลี่ย/หน่วย": "{:,.2f}", "มูลค่าตลาด": "{:,.2f}",
                "กำไร/ขาดทุน (ยังไม่ขาย)": "{:+,.2f}", "กำไร/ขาดทุน (รับรู้แล้ว)": "{:+,.2f}",
            }),
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("ยังไม่มีรายการถือครองทองจริง")

    c1, c2, c3 = st.columns(3)
    render_metric_card(c1, "มูลค่าตลาดรวม", f"{summary['total_market_value']:,.2f} ฿", icon="💰")
    render_metric_card(c2, "กำไร/ขาดทุนที่ยังไม่ขาย", f"{summary['total_unrealized_pl']:,.2f} ฿", icon="📈",
                        delta_positive=(summary['total_unrealized_pl'] >= 0))
    render_metric_card(c3, "กำไร/ขาดทุนที่รับรู้แล้ว", f"{summary['total_realized_pl']:,.2f} ฿", icon="✅",
                        delta_positive=(summary['total_realized_pl'] >= 0))

    st.divider()
    st.write("ประวัติรายการทั้งหมด:")
    st.dataframe(physical_df, use_container_width=True, hide_index=True)


# =============================================================
# ส่วนที่ 4: 📈 เทรด Short/Long — เปิด/ปิดสถานะแบบเดียวกับ TFEX
# =============================================================
GOLD_TRADES_COLS = ["Trade_ID", "Date_Open", "Date_Close", "Instrument", "Unit", "Status", "Size",
                     "Open_Price", "Close_Price", "Realized", "Comm", "Net_Profit", "Win_Lose", "Reason"]


def calculate_gold_trade_result(entry, close, size, comm, status):
    """กำไร/ขาดทุนทองคำคำนวณตรงๆ จากส่วนต่างราคา x ขนาด (ต่างจาก TFEX ที่มี multiplier 200 บาท/จุด
    เพราะราคาทองคำที่กรอกเป็นราคาต่อหน่วยเป็นบาทอยู่แล้ว ไม่มีหน่วยจุดแบบสัญญา TFEX)"""
    diff = (close - entry) if status == "Long" else (entry - close)
    realized = diff * size
    net_profit = realized - comm
    win_lose = "Win" if net_profit > 0 else "Lose"
    return {"Realized": round(realized, 2), "Net_Profit": round(net_profit, 2), "Win_Lose": win_lose}


def _update_gold_trade_close(trade_id, close_price, close_date, calc):
    try:
        sheet = _get_or_create_worksheet("Gold_Trades", GOLD_TRADES_COLS)
        records = sheet.get_all_records()
        df = pd.DataFrame(records)
        if "Trade_ID" not in df.columns:
            st.error("ไม่พบข้อมูลในตาราง Gold_Trades")
            return False
        idx_list = df.index[df["Trade_ID"] == trade_id].tolist()
        if not idx_list:
            st.error("ไม่พบ Trade_ID นี้")
            return False
        row_index = idx_list[0] + 2
        trade_row = df.loc[idx_list[0]]

        # C:M = Date_Close, Instrument, Unit, Status, Size, Open_Price, Close_Price, Realized, Comm, Net_Profit, Win_Lose
        # (ไม่แตะคอลัมน์ N "Reason" เพื่อไม่ให้ทับข้อความเหตุผลเดิมที่กรอกไว้ตอนเปิดสถานะ)
        data_to_update = [
            str(close_date), str(trade_row.get("Instrument", "")), str(trade_row.get("Unit", "")),
            str(trade_row.get("Status", "")), float(trade_row.get("Size", 0)), float(trade_row.get("Open_Price", 0)),
            float(close_price), float(calc["Realized"]), float(trade_row.get("Comm", 0)),
            float(calc["Net_Profit"]), str(calc["Win_Lose"]),
        ]
        sheet.update(range_name=f"C{row_index}:M{row_index}", values=[data_to_update])
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"⚠️ ปิดสถานะไม่สำเร็จ: {e}")
        return False


def _compute_trades_summary(trades_df):
    if trades_df.empty:
        return {"open_positions": pd.DataFrame(), "closed_trades": pd.DataFrame(),
                "total_realized": 0.0, "win_rate": 0.0}

    df = trades_df.copy()
    df["Close_Price_Cleaned"] = pd.to_numeric(df.get("Close_Price", 0), errors="coerce").fillna(0.0)
    open_positions = df[df["Close_Price_Cleaned"] == 0].copy()
    closed_trades = df[df["Close_Price_Cleaned"] > 0].copy()

    total_realized = 0.0
    if "Net_Profit" in closed_trades.columns:
        total_realized = float(pd.to_numeric(closed_trades["Net_Profit"], errors="coerce").fillna(0).sum())

    win_count = 0
    if "Win_Lose" in closed_trades.columns:
        win_count = int((closed_trades["Win_Lose"] == "Win").sum())
    win_rate = (win_count / len(closed_trades) * 100) if len(closed_trades) > 0 else 0.0

    return {"open_positions": open_positions, "closed_trades": closed_trades,
            "total_realized": total_realized, "win_rate": win_rate}


def _render_trade_tab(trades_df, summary):
    st.subheader("📈 เทรด Short / Long (ทองคำ Spot / CFD / ฟิวเจอร์ส)")

    sub_open, sub_close = st.tabs(["➕ เปิดสถานะใหม่", "🏁 ปิดสถานะ"])

    with sub_open:
        st.markdown("##### 🛡 คำนวณขนาดสถานะจากความเสี่ยง (ไม่บังคับ ใช้เป็นตัวช่วยตัดสินใจ)")
        c1, c2, c3 = st.columns(3)
        risk_pct = c1.slider("ความเสี่ยงที่ยอมรับ (% ของพอร์ตทอง)", 0.0, 5.0, 1.0, 0.25, key="gt_risk_pct")
        entry_preview = c2.number_input("ราคาเข้าโดยประมาณ", min_value=0.0, value=40000.0, step=100.0, key="gt_entry_preview")
        sl_preview = c3.number_input("ราคา Stop Loss โดยประมาณ", min_value=0.0, value=39500.0, step=100.0, key="gt_sl_preview")

        portfolio_ref = st.session_state.get('gold_net_worth', 0.0)
        risk_amount = portfolio_ref * (risk_pct / 100.0)
        sl_distance = abs(entry_preview - sl_preview)
        max_size = (risk_amount / sl_distance) if sl_distance > 0 else 0
        st.caption(f"ยอมขาดทุนได้ {risk_amount:,.2f} ฿ ({risk_pct}% ของมูลค่าพอร์ตทองรวม {portfolio_ref:,.2f} ฿) "
                   f"ที่ระยะ SL {sl_distance:,.2f} บาท/หน่วย → เปิดได้ไม่เกิน **{max_size:,.2f} หน่วย**")

        st.divider()

        with st.form("gold_trade_open_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                date_open = st.date_input("วันที่เปิด")
                instrument = st.text_input("สินค้า", value="Gold Spot", help="เช่น XAUUSD, Gold Spot, GF (ฟิวเจอร์สทองคำ)")
                unit = st.selectbox("หน่วย", ["บาททองคำ", "ออนซ์ (oz)", "กรัม", "สัญญา"])
            with c2:
                status_dir = st.selectbox("ทิศทาง", ["Long", "Short"])
                entry = st.number_input("ราคาเปิด (บาท/หน่วย)", min_value=0.0, step=10.0, value=40000.0)
                size = st.number_input("ขนาด (จำนวนหน่วย)", min_value=0.0, step=0.1, value=1.0)
            with c3:
                comm = st.number_input("ค่าคอมมิชชัน/ค่าธรรมเนียม (บาท)", min_value=0.0, step=10.0, value=0.0)
                reason = st.text_area("เหตุผลที่เข้าเทรด")

            if st.form_submit_button("เปิดสถานะเทรด"):
                trade_id = f"GT-{pd.Timestamp.now().strftime('%Y%m%d%H%M%S')}"
                new_row = [
                    trade_id, str(date_open), "", instrument, unit, status_dir, size,
                    entry, 0, 0, comm, 0, "", reason,
                ]
                if _append_rows("Gold_Trades", GOLD_TRADES_COLS, [new_row]):
                    st.toast("เปิดสถานะเทรดทองเรียบร้อย!", icon="✅")
                    st.rerun()

    with sub_close:
        open_positions = summary["open_positions"]
        if open_positions.empty or "Trade_ID" not in open_positions.columns:
            st.info("ไม่มีสถานะที่ถือครองอยู่ในปัจจุบัน")
        else:
            selected_id = st.selectbox("เลือก Trade ที่จะปิด", open_positions["Trade_ID"].tolist())
            detail = open_positions[open_positions["Trade_ID"] == selected_id].iloc[0]
            st.info(f"🔍 {detail.get('Instrument', '')} | {detail.get('Status', '')} | ขนาด {detail.get('Size', '')} "
                    f"{detail.get('Unit', '')} | ราคาเปิด {detail.get('Open_Price', '')}")

            default_open = pd.to_numeric(detail.get("Open_Price", 0), errors="coerce")
            default_open = float(default_open) if pd.notna(default_open) else 0.0

            with st.form("gold_trade_close_form"):
                close_price = st.number_input("ราคาปิด", value=default_open, step=10.0, format="%.2f")
                close_date = st.date_input("วันที่ปิด")
                if st.form_submit_button("ยืนยันปิดสถานะ", type="primary", use_container_width=True):
                    size_val = float(pd.to_numeric(detail.get("Size", 0), errors="coerce") or 0.0)
                    comm_val = float(pd.to_numeric(detail.get("Comm", 0), errors="coerce") or 0.0)
                    calc = calculate_gold_trade_result(default_open, float(close_price), size_val,
                                                        comm_val, str(detail.get("Status", "Long")))
                    with st.spinner("⏳ กำลังบันทึกการปิดสถานะ..."):
                        if _update_gold_trade_close(selected_id, close_price, str(close_date), calc):
                            st.toast("ปิดสถานะเรียบร้อย! 🏆", icon="🏆")
                            st.rerun()

    st.divider()
    st.write("ประวัติการเทรดทั้งหมด:")
    st.dataframe(trades_df, use_container_width=True, hide_index=True)


# =============================================================
# ส่วนที่ 5: 🐷 ซื้อสะสม (DCA) — บันทึกซื้อสะสมเป็นงวดๆ เทียบต้นทุนเฉลี่ยกับราคาตลาด
# =============================================================
# 🔧 แก้บั๊ก: เพิ่มคอลัมน์ Reference_Price ท้ายสุด — DCA เดิมสมมติว่าทุกแถวเป็น "ทองคำจริง" หน่วย
# บาททองคำ ตีมูลค่าปัจจุบันจากราคาทองสดเสมอ (ref_gold_bar) แต่บางรายการ (เช่น กองทุนทองคำ
# SCBGOLDH) เป็นหน่วยลงทุนของกองทุนที่มีราคา NAV ของตัวเอง ไม่ได้เกาะราคาทองสดตรงๆ ถ้าตีราคาด้วย
# ref_gold_bar จะได้มูลค่าผิดเพี้ยนมหาศาล (เอาจำนวนหน่วยกองทุนไปคูณราคาทองคำแท่งเป็นบาท/บาททองคำ)
# ตอนนี้ถ้าแถวไหนระบุ Reference_Price ไว้ (>0) จะถือว่าเป็น "กองทุน/สินทรัพย์ที่มีราคาของตัวเอง"
# ใช้ราคานี้ตีมูลค่าแทนราคาทองสด — ปล่อยว่างไว้ (ไม่เคยตั้งเลย) จะตีราคาจากราคาทองสดตามปกติเหมือนเดิม
GOLD_DCA_COLS = ["DCA_ID", "Date", "Amount_Invested", "Price_Per_Unit", "Weight_Bought", "Note", "Reference_Price"]


def _compute_dca_summary(dca_df, ref_gold_bar):
    """
    🔧 แก้บั๊ก: เดิมรวมทุกแถวเป็นก้อนเดียว (total_weight/avg_cost เดียว) ทำให้ถ้ามีทั้งทองคำจริง
    (หน่วยบาททองคำ) กับกองทุน (หน่วยของกองทุนเอง) ปนกัน ตัวเลขจะปนกันมั่วผิดหน่วย ตอนนี้แยกกลุ่ม
    ตาม "Note" (ชื่อกองทุน/แพลตฟอร์ม) ก่อน แล้วค่อยตีมูลค่าแต่ละกลุ่มแยกกัน (ดูคอมเมนต์
    Reference_Price ด้านบน) ก่อนรวมเป็นยอดรวมทั้งหมด (บาทไทยรวมกันได้ปกติ ไม่มีปัญหาเรื่องหน่วย)
    """
    if dca_df.empty:
        return {"groups": [], "total_invested": 0.0, "market_value": 0.0, "unrealized_pl": 0.0}

    df = dca_df.copy()
    df["Amount_Invested"] = pd.to_numeric(df.get("Amount_Invested", 0), errors="coerce").fillna(0.0)
    df["Price_Per_Unit"] = pd.to_numeric(df.get("Price_Per_Unit", 0), errors="coerce").fillna(0.0)
    df["Weight_Bought"] = pd.to_numeric(df.get("Weight_Bought", 0), errors="coerce").fillna(0.0)
    df["Reference_Price"] = pd.to_numeric(df.get("Reference_Price", 0), errors="coerce").fillna(0.0)
    df["Note"] = df.get("Note", "").fillna("").astype(str)
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.sort_values("Date")

    groups = []
    total_invested = total_market = 0.0
    for note, g in df.groupby("Note", sort=False):
        g_invested = float(g["Amount_Invested"].sum())
        g_weight = float(g["Weight_Bought"].sum())
        g_avg_cost = (g_invested / g_weight) if g_weight > 0 else 0.0

        # ราคาที่ใช้ตีมูลค่าปัจจุบันของกลุ่มนี้: ถ้าเคยมีการระบุ Reference_Price ไว้ (>0) ในแถวใด
        # แถวหนึ่งของกลุ่มนี้ ถือว่าเป็นกองทุน/สินทรัพย์ที่มีราคาของตัวเอง ใช้ค่าล่าสุดที่บันทึกไว้
        # (เรียงตามวันที่แล้ว จึงหยิบแถวสุดท้ายที่มีค่า) แทนราคาทองสด — ถ้าไม่เคยระบุเลยสักแถว
        # ถือเป็นทองคำจริง ใช้ราคาทองสดตามปกติ
        ref_rows = g[g["Reference_Price"] > 0]
        is_fund_style = not ref_rows.empty
        current_price = float(ref_rows.iloc[-1]["Reference_Price"]) if is_fund_style else ref_gold_bar

        g_market = g_weight * current_price
        if g_weight <= 0 and g_invested <= 0:
            continue  # แถวที่เป็นแค่ "อัปเดตราคา" ล้วนๆ (ไม่มีเงินลงทุน/หน่วยใหม่) ไม่ต้องนับเป็นกลุ่มแยก
        groups.append({
            "note": note or "(ไม่ระบุ)", "invested": g_invested, "weight": g_weight,
            "avg_cost": g_avg_cost, "current_price": current_price, "market_value": g_market,
            "unrealized": g_market - g_invested, "is_fund_style": is_fund_style,
        })
        total_invested += g_invested
        total_market += g_market

    return {
        "groups": groups, "total_invested": total_invested,
        "market_value": total_market, "unrealized_pl": total_market - total_invested,
    }


def _render_dca_tab(dca_df, ref_gold_bar, summary):
    st.subheader("🐷 ซื้อสะสม (DCA) — ทองคำออมทรัพย์ / กองทุนทอง")
    st.caption(
        "บันทึกการซื้อสะสมเป็นงวดๆ แยกกลุ่มตาม \"หมายเหตุ\" (เช่น ชื่อกองทุน/แพลตฟอร์ม) — ถ้าเป็น"
        "ทองคำจริง (หน่วยบาททองคำ) ระบบตีมูลค่าปัจจุบันจากราคาทองสดให้อัตโนมัติ ถ้าเป็นกองทุนที่มี"
        "ราคา NAV ของตัวเอง (ไม่ผูกกับราคาทองสดตรงๆ เช่น SCBGOLDH) ให้กรอก \"ราคาปัจจุบันของกองทุน\" "
        "ในฟอร์มด้านล่างด้วย ระบบจะใช้ราคานั้นตีมูลค่าแทน"
    )

    with st.form("gold_dca_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            d_date = st.date_input("วันที่ซื้อ", key="dca_date")
            note = st.text_input("หมายเหตุ / ชื่อกองทุน / แพลตฟอร์ม", placeholder="เช่น GSB Gold, กองทุน T-GOLD, SCBGOLDH", key="dca_note")
        with c2:
            amount = st.number_input("จำนวนเงินที่ซื้อ (บาท)", min_value=0.0, step=500.0, value=1000.0, key="dca_amount")
            price = st.number_input("ราคา ณ วันที่ซื้อ (บาท/หน่วย)", min_value=0.0,
                                     value=round(ref_gold_bar, 2), step=10.0, key="dca_price",
                                     help="ทองคำจริงใช้หน่วยบาททองคำ กองทุนใช้ราคา NAV/หน่วยของกองทุนนั้น")
        with c3:
            weight_preview = (amount / price) if price > 0 else 0.0
            st.metric("จำนวนหน่วยที่ได้โดยประมาณ", f"{weight_preview:.4f}")
            ref_price_input = st.number_input(
                "ราคาปัจจุบันของกองทุน (กรอกเฉพาะกองทุนที่ไม่ผูกราคาทองสด)",
                min_value=0.0, step=1.0, value=0.0, key="dca_ref_price",
                help="เว้นว่างไว้ถ้าเป็นทองคำจริง (ตีมูลค่าจากราคาทองสดอัตโนมัติ) กรอกถ้าเป็นกองทุนที่มีราคา NAV ของตัวเอง",
            )

        if st.form_submit_button("➕ บันทึกการซื้อสะสม"):
            if amount <= 0 or price <= 0:
                st.error("กรุณากรอกจำนวนเงินและราคาให้มากกว่า 0")
            else:
                new_row = [
                    f"DCA-{pd.Timestamp.now().strftime('%Y%m%d%H%M%S')}", str(d_date),
                    amount, price, amount / price, note, ref_price_input,
                ]
                if _append_rows("Gold_DCA", GOLD_DCA_COLS, [new_row]):
                    st.toast("บันทึกการซื้อสะสมเรียบร้อย!", icon="✅")
                    st.rerun()

    st.divider()
    c1, c2, c3 = st.columns(3)
    render_metric_card(c1, "เงินลงทุนสะสมรวม", f"{summary['total_invested']:,.2f} ฿", icon="💵")
    render_metric_card(c2, "มูลค่าปัจจุบันรวม", f"{summary['market_value']:,.2f} ฿", icon="💰")
    unrealized_pct = (summary['unrealized_pl'] / summary['total_invested'] * 100) if summary['total_invested'] > 0 else 0.0
    render_metric_card(c3, "กำไร/ขาดทุน (Mark-to-Market)", f"{summary['unrealized_pl']:,.2f} ฿", icon="📈",
                        delta=f"{unrealized_pct:+.2f}%", delta_positive=(summary['unrealized_pl'] >= 0))

    st.divider()
    st.subheader("📊 สรุปแยกตามรายการ (หมายเหตุ)")
    groups = summary["groups"]
    if groups:
        df_groups = pd.DataFrame([{
            "หมายเหตุ": g["note"],
            "เงินลงทุนสะสม": g["invested"],
            "จำนวนหน่วยสะสม": g["weight"],
            "ต้นทุนเฉลี่ย/หน่วย": g["avg_cost"],
            "ราคาปัจจุบัน/หน่วย": g["current_price"],
            "มูลค่าปัจจุบัน": g["market_value"],
            "กำไร/ขาดทุน": g["unrealized"],
            "อ้างอิงราคา": "ราคาที่กรอกเอง (กองทุน)" if g["is_fund_style"] else "ราคาทองสด",
        } for g in groups])
        st.dataframe(
            df_groups.style.format({
                "เงินลงทุนสะสม": "{:,.2f}", "จำนวนหน่วยสะสม": "{:,.4f}",
                "ต้นทุนเฉลี่ย/หน่วย": "{:,.4f}", "ราคาปัจจุบัน/หน่วย": "{:,.4f}",
                "มูลค่าปัจจุบัน": "{:,.2f}", "กำไร/ขาดทุน": "{:+,.2f}",
            }),
            use_container_width=True, hide_index=True,
        )

        # 🆕 กองทุนที่ไม่มีราคาทองสดให้อ้างอิงอัตโนมัติ ต้องมีทางอัปเดตราคาล่าสุดเป็นระยะ แยกจาก
        # ฟอร์มซื้อเพิ่มด้านบน (ไม่นับเป็นเงินลงทุน/หน่วยใหม่ แค่ปักหมุดราคาล่าสุดของกลุ่มนั้น)
        fund_notes = [g["note"] for g in groups if g["is_fund_style"]]
        if fund_notes:
            st.caption("💡 กองทุนที่ไม่มีราคาทองสดอัตโนมัติ อัปเดตราคาล่าสุดได้ที่นี่ (ไม่นับเป็นการซื้อเพิ่ม)")
            with st.form("gold_dca_update_price_form", clear_on_submit=True):
                uc1, uc2 = st.columns(2)
                update_note = uc1.selectbox("เลือกรายการ (หมายเหตุ)", fund_notes, key="dca_update_note")
                update_price = uc2.number_input("ราคาปัจจุบันใหม่ (บาท/หน่วย)", min_value=0.01, step=1.0, key="dca_update_price")
                if st.form_submit_button("💾 อัปเดตราคาปัจจุบัน"):
                    new_row = [
                        f"DCA-PRICE-{pd.Timestamp.now().strftime('%Y%m%d%H%M%S')}", str(datetime.now().strftime('%Y-%m-%d')),
                        0, 0, 0, update_note, update_price,
                    ]
                    if _append_rows("Gold_DCA", GOLD_DCA_COLS, [new_row]):
                        st.toast(f"อัปเดตราคา {update_note} เรียบร้อย!", icon="✅")
                        st.rerun()
    else:
        st.info("ยังไม่มีข้อมูลพอร์ต DCA")

    st.divider()
    st.write("ประวัติการซื้อสะสมทั้งหมด:")
    st.dataframe(dca_df, use_container_width=True, hide_index=True)


# =============================================================
# ส่วนที่ 6: 📊 Dashboard — ภาพรวมทุกประเภท
# =============================================================
def _render_dashboard_tab(physical_summary, trades_summary, dca_summary):
    # มูลค่าพอร์ตรวมนับเฉพาะทองที่ถือ mark-to-market ได้จริง (ถือจริง + DCA) ส่วนสถานะเทรด
    # Short/Long ที่เปิดอยู่ยังไม่นับรวมตรงนี้ เพราะเป็นสัญญา/margin ไม่ใช่การถือทองจริง และยังไม่ realize
    total_value = physical_summary["total_market_value"] + dca_summary["market_value"]
    total_pl = (physical_summary["total_unrealized_pl"] + physical_summary["total_realized_pl"]
                + dca_summary["unrealized_pl"] + trades_summary["total_realized"])
    # 🆕 ฐานคิด % = ต้นทุนของทองที่ถือจริง + DCA เท่านั้น (ไม่รวมเทรด Short/Long เพราะไม่มี
    # "เงินลงทุน" ที่ยังค้างอยู่ให้เทียบ เป็นแค่กำไร/ขาดทุนที่รับรู้แล้วจากมาร์จิ้น) เหมือนฐานคิด
    # ของ total_value ด้านบนที่ไม่รวมสถานะเทรดที่เปิดอยู่เช่นกัน
    total_cost_base = physical_summary["total_cost_value"] + dca_summary["total_invested"]
    total_pl_pct = (total_pl / total_cost_base * 100) if total_cost_base > 0 else 0.0

    # แชร์มูลค่าพอร์ตทองไปให้แท็บ "เทรด Short/Long" ใช้คำนวณขนาดสถานะจากความเสี่ยง
    # และให้หน้าภาพรวม Net Worth ดึงไปใช้ได้เหมือนที่ TFEX/Fund ทำไว้
    st.session_state['gold_net_worth'] = total_value

    c1, c2, c3 = st.columns(3)
    render_metric_card(c1, "มูลค่าพอร์ตทองรวม (ถือจริง + DCA)", f"{total_value:,.2f} ฿", icon="💰")
    render_metric_card(c2, "กำไร/ขาดทุนรวมทุกประเภท", f"{total_pl:,.2f} ฿", icon="💹",
                        delta=f"{total_pl_pct:+.2f}%", delta_positive=(total_pl >= 0))
    render_metric_card(c3, "กำไรจากเทรด Short/Long (รับรู้แล้ว)", f"{trades_summary['total_realized']:,.2f} ฿",
                        icon="📈", delta=f"Win rate {trades_summary['win_rate']:.1f}%",
                        delta_positive=(trades_summary['total_realized'] >= 0))

    st.divider()
    st.subheader("🥧 สัดส่วนมูลค่าพอร์ตทองคำ")
    pie_labels, pie_values = [], []
    if physical_summary["total_market_value"] > 0:
        pie_labels.append("ทองคำแท่ง/รูปพรรณ (ถือจริง)")
        pie_values.append(physical_summary["total_market_value"])
    if dca_summary["market_value"] > 0:
        pie_labels.append("ซื้อสะสม (DCA)")
        pie_values.append(dca_summary["market_value"])
    if pie_values:
        fig_pie = go.Figure(go.Pie(labels=pie_labels, values=pie_values, hole=0.5))
        fig_pie.update_layout(height=300, margin=dict(l=20, r=20, t=20, b=20))
        st.plotly_chart(style_plotly(fig_pie), use_container_width=True)
    else:
        st.info("ยังไม่มีข้อมูลพอร์ตทองคำให้แสดงสัดส่วน")

    st.divider()
    st.subheader("📈 กำไรสะสมจากเทรด Short/Long")
    closed = trades_summary["closed_trades"]
    if not closed.empty and "Date_Close" in closed.columns and "Net_Profit" in closed.columns:
        closed = closed.copy()
        closed["Date_Close"] = pd.to_datetime(closed["Date_Close"], errors="coerce")
        closed = closed.dropna(subset=["Date_Close"]).sort_values("Date_Close")
        closed["Cumulative"] = pd.to_numeric(closed["Net_Profit"], errors="coerce").fillna(0).cumsum()
        fig_growth = px.line(closed, x="Date_Close", y="Cumulative", markers=True)
        fig_growth.update_traces(line=dict(color="#26A69A", width=3))
        fig_growth.update_layout(height=300, margin=dict(l=20, r=20, t=20, b=20), yaxis_title="กำไรสะสม (บาท)")
        st.plotly_chart(style_plotly(fig_growth), use_container_width=True)
    else:
        st.info("ยังไม่มีการปิดสถานะเทรดทองที่จะแสดงกราฟกำไรสะสม")

    st.divider()
    st.subheader("📋 สถานะเทรดที่เปิดอยู่")
    open_pos = trades_summary["open_positions"]
    if not open_pos.empty:
        cols_show = [c for c in ["Trade_ID", "Date_Open", "Instrument", "Status", "Size", "Unit", "Open_Price"]
                     if c in open_pos.columns]
        st.dataframe(open_pos[cols_show], use_container_width=True, hide_index=True)
    else:
        st.info("ไม่มีสถานะเทรดทองที่เปิดอยู่ในปัจจุบัน")


# =============================================================
# ส่วนที่ 7: จุดเข้าใช้งานหลักของแท็บ
# =============================================================
def render_tab_gold(client):
    st.markdown("### 🟡 จัดการพอร์ตการลงทุนทองคำ")
    st.caption("แยกเป็น 3 รูปแบบการลงทุนทองคำ: ถือครองจริง / เทรด Short-Long / ซื้อสะสม (DCA) "
               "ดู Dashboard สำหรับภาพรวมทั้งหมด")

    ref_gold_bar, ref_gold_jewelry = _render_gold_price_ticker()
    st.markdown("---")

    physical_df = _load_gold_sheet_cached("Gold_Physical", get_active_sheet_name())
    physical_df = _migrate_legacy_physical_gold_if_needed(physical_df)
    trades_df = _load_gold_sheet_cached("Gold_Trades", get_active_sheet_name())
    dca_df = _load_gold_sheet_cached("Gold_DCA", get_active_sheet_name())
    dca_df = _migrate_legacy_fund_gold_if_needed(dca_df)

    physical_summary = _compute_physical_summary(physical_df, ref_gold_bar, ref_gold_jewelry)
    trades_summary = _compute_trades_summary(trades_df)
    dca_summary = _compute_dca_summary(dca_df, ref_gold_bar)

    sub_dash, sub_physical, sub_trade, sub_dca = st.tabs([
        "📊 Dashboard", "🪙 ทองคำแท่ง/รูปพรรณ", "📈 เทรด Short/Long", "🐷 ซื้อสะสม (DCA)",
    ])

    with sub_physical:
        _render_physical_tab(physical_df, ref_gold_bar, ref_gold_jewelry, physical_summary)
    with sub_trade:
        _render_trade_tab(trades_df, trades_summary)
    with sub_dca:
        _render_dca_tab(dca_df, ref_gold_bar, dca_summary)
    with sub_dash:
        _render_dashboard_tab(physical_summary, trades_summary, dca_summary)
