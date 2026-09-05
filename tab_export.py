# =============================================================
# tab_export.py
# แท็บ Export Excel — ดาวน์โหลดข้อมูลเลือกได้เป็นไฟล์ .xlsx (คนละไฟล์กับระบบ backup
# อัตโนมัติรายวันที่ backup_firestore_to_sheets.py ทำ — อันนี้ให้ผู้ใช้กดดาวน์โหลดเองตามต้องการ)
# =============================================================
import io
from datetime import date

import pandas as pd
import streamlit as st

from backend_functions import get_gsheet_client, get_active_sheet_name, get_worksheet_safely

# ป้ายชื่อที่ผู้ใช้เห็น -> ชื่อ worksheet จริงที่ดึงข้อมูล
EXPORT_CATEGORIES = {
    "Portfolio": "PortfolioData",
    "ประวัติซื้อขายหุ้นทั้งหมด": "JournalData",
    "ประวัติซื้อขาย TFEX": "TFEX_History",
    "ประวัติ PVD": "Provident_Fund",
    "ประวัติซื้อขายกองทุน": "Fund_History",
    "ทองคำ - ถือครองจริง": "Gold_Physical",
    "ทองคำ - เทรด Short/Long": "Gold_Trades",
    "ทองคำ - ซื้อสะสม (DCA)": "Gold_DCA",
}


def _on_select_all_change():
    value = st.session_state.get("export_select_all", False)
    for label in EXPORT_CATEGORIES:
        st.session_state[f"export_chk_{label}"] = value


def _build_excel(selected_labels):
    client = get_gsheet_client()
    spreadsheet_name = get_active_sheet_name()
    buffer = io.BytesIO()

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for label in selected_labels:
            ws_name = EXPORT_CATEGORIES[label]
            try:
                sheet = get_worksheet_safely(client, spreadsheet_name, ws_name)
                records = sheet.get_all_records() if sheet else []
            except Exception:
                records = []
            df = pd.DataFrame(records)
            # ชื่อ sheet ใน Excel ห้ามเกิน 31 ตัวอักษร และห้ามมีอักขระ : \ / ? * [ ]
            safe_name = label[:31]
            for ch in ':\\/?*[]':
                safe_name = safe_name.replace(ch, '_')
            df.to_excel(writer, sheet_name=safe_name, index=False)

    buffer.seek(0)
    return buffer.getvalue()


def render_tab_export():
    st.subheader("📥 Export ข้อมูลเป็น Excel")
    st.caption("เลือกข้อมูลที่ต้องการ แล้วกดสร้างไฟล์เพื่อดาวน์โหลดเก็บไว้เอง")

    st.checkbox("✅ เลือกทั้งหมด", key="export_select_all", on_change=_on_select_all_change)

    selected = []
    cols = st.columns(2)
    for i, label in enumerate(EXPORT_CATEGORIES):
        with cols[i % 2]:
            if st.checkbox(label, key=f"export_chk_{label}"):
                selected.append(label)

    st.divider()

    if st.button("📊 สร้างไฟล์ Excel", type="primary", disabled=not selected):
        with st.spinner("กำลังดึงข้อมูลและสร้างไฟล์..."):
            excel_bytes = _build_excel(selected)
        file_name = f"backup_{get_active_sheet_name()}_{date.today().isoformat()}.xlsx"
        st.success(f"สร้างไฟล์สำเร็จ ({len(selected)} รายการ)")
        st.download_button(
            "⬇️ ดาวน์โหลดไฟล์ Excel",
            data=excel_bytes,
            file_name=file_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    if not selected:
        st.info("กรุณาเลือกข้อมูลอย่างน้อย 1 รายการก่อนสร้างไฟล์")
