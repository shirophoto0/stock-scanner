# =============================================================
# tab_fundamental_watchlist.py
# 📊 Watchlist เชิงปัจจัยพื้นฐาน (Fundamental Watchlist) — แยกจาก Watchlist เดิมที่ใช้เทรดโดยสิ้นเชิง
# เก็บหุ้นที่สนใจติดตามงบการเงินรายไตรมาส มีไอคอนลิงก์ไปหน้าดาวน์โหลดงบจริงบน set.or.th ให้เลย
# อัปโหลด PDF งบเอง (มือ) ให้ Claude อ่าน สกัดตัวเลขสำคัญสไตล์ Mark Minervini ออกมาเป็นโครงสร้าง
# ที่เทียบข้ามไตรมาสได้ง่าย บันทึกประวัติถาวร เรียกดูย้อนหลัง + ให้ AI วิเคราะห์แนวโน้มการเติบโตได้
# =============================================================
import streamlit as st
import pandas as pd
import base64
import json
from backend_functions import (
    get_active_sheet_name,
    get_set_financial_statement_url,
    load_fundamental_watchlist,
    add_to_fundamental_watchlist,
    remove_from_fundamental_watchlist,
    save_fundamental_analysis,
    load_fundamental_analysis_history,
)
from theme import render_metric_card
# 🆕 ดึงฟังก์ชันแปลง Excel/Word เป็นข้อความ ที่มีอยู่แล้วจากแท็บ "วิเคราะห์เอกสาร AI" มาใช้ร่วมกัน
# ไม่ต้องเขียนตรรกะซ้ำอีกรอบ (ทั้ง 2 แท็บอ่านไฟล์ประเภทเดียวกัน แค่คนละบริบทการใช้งาน)
from tab_document_analysis import _extract_text_from_xlsx, _extract_text_from_docx

MODEL_NAME = "claude-sonnet-5"

ANALYSIS_PROMPT_TEMPLATE = """คุณเป็นนักวิเคราะห์หุ้นสไตล์ Mark Minervini ที่เน้นดูการเติบโตของยอดขายและกำไรเป็นหลัก
อ่านงบการเงินไตรมาสที่แนบมา (บริษัท {ticker} ไตรมาสที่ {quarter}/{year}) แล้วตอบกลับเป็น JSON เท่านั้น
ห้ามมีข้อความอื่นนอกเหนือจาก JSON เลยแม้แต่คำเดียว ห้ามมีคำนำ ห้ามมีคำอธิบายก่อนหรือหลัง JSON
ห้ามใส่ ```json ครอบ ตอบเริ่มต้นด้วยเครื่องหมาย {{ ทันทีที่ตัวอักษรแรกของคำตอบ ตามโครงสร้างนี้เป๊ะๆ:

{{
  "revenue": <ตัวเลขรายได้รวม หน่วยล้านบาท ตัวเลขล้วนไม่มีข้อความ ถ้าไม่พบใส่ null>,
  "revenue_yoy_growth_pct": <% การเติบโตของรายได้เทียบไตรมาสเดียวกันปีก่อน ถ้าไม่ระบุในเอกสารใส่ null>,
  "net_profit": <กำไรสุทธิ หน่วยล้านบาท ถ้าไม่พบใส่ null>,
  "net_profit_yoy_growth_pct": <% การเติบโตกำไรสุทธิเทียบปีก่อน ถ้าไม่มีใส่ null>,
  "eps": <กำไรต่อหุ้น บาท ถ้าไม่พบใส่ null>,
  "gross_margin_pct": <อัตรากำไรขั้นต้น % ถ้าไม่พบใส่ null>,
  "net_margin_pct": <อัตรากำไรสุทธิ % ถ้าไม่พบใส่ null>,
  "debt_to_equity": <อัตราส่วนหนี้สินต่อทุน ถ้าไม่พบใส่ null>,
  "summary": "<สรุปภาพรวมไตรมาสนี้ 2-3 ประโยค ภาษาไทย>",
  "highlights": "<จุดเด่นของไตรมาสนี้ 2-3 ประโยค ภาษาไทย>",
  "risks": "<จุดเสี่ยง/สัญญาณเตือนที่ควรระวัง 2-3 ประโยค ภาษาไทย>"
}}"""

TREND_ANALYSIS_PROMPT = """คุณเป็นนักวิเคราะห์หุ้นสไตล์ Mark Minervini กรุณาดูข้อมูลงบการเงินย้อนหลังของหุ้น {ticker}
ที่มีอยู่ (เรียงจากไตรมาสเก่าสุดไปใหม่สุด) แล้วตอบเป็นภาษาไทยกระชับ ครบ 3 หัวข้อ:

1. **แนวโน้มการเติบโต** — รายได้/กำไรเติบโตต่อเนื่องจริงไหม หรือเริ่มชะลอตัว/ถดถอย
2. **จุดที่ควรจับตา** — สัญญาณเปลี่ยนแปลงที่เห็นจากการเทียบไตรมาสต่อไตรมาส
3. **ควรถือต่อหรือไม่** — ให้มุมมองประกอบการตัดสินใจ (ไม่ใช่คำแนะนำการลงทุนโดยตรง แค่สรุปสิ่งที่ตัวเลขบอก)

ข้อมูลย้อนหลัง:
{history_text}"""


def _call_claude_document_analysis(api_key, file_bytes, file_ext, prompt_text):
    """
    ส่งเอกสาร (PDF/Excel/Word) + Prompt ไปให้ Claude วิเคราะห์ คืนค่าเป็น (ข้อความผลลัพธ์, usage info)
    🆕 รองรับทั้ง 3 ประเภทไฟล์แล้ว (เดิมรองรับแค่ PDF) — PDF ส่งเข้า API ได้ตรงๆ (รองรับทั้งข้อความ
    และภาพ/กราฟ/ตารางในตัว) ส่วน Excel/Word ต้องแปลงเป็นข้อความก่อน เพราะ Claude API ไม่รองรับ
    ไฟล์ 2 ประเภทนี้โดยตรง (ใช้ตัวแปลงเดียวกับแท็บ "วิเคราะห์เอกสาร AI")
    """
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    if file_ext == "pdf":
        base64_data = base64.standard_b64encode(file_bytes).decode("utf-8")
        message_content = [
            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": base64_data}},
            {"type": "text", "text": prompt_text},
        ]
    elif file_ext == "xlsx":
        extracted_text = _extract_text_from_xlsx(file_bytes)
        message_content = f"เนื้อหาจากไฟล์ Excel:\n\n{extracted_text}\n\n{prompt_text}"
    elif file_ext == "docx":
        extracted_text = _extract_text_from_docx(file_bytes)
        message_content = f"เนื้อหาจากไฟล์ Word:\n\n{extracted_text}\n\n{prompt_text}"
    else:
        raise ValueError(f"ไม่รองรับไฟล์ประเภทนี้: .{file_ext}")

    response = client.messages.create(
        model=MODEL_NAME,
        # 🔧 เพิ่มจาก 1500 เป็น 4000 — สงสัยว่าคำตอบ AI อาจยาวเกินขีดจำกัดเดิมจนถูกตัดกลางคัน
        # (โดยเฉพาะไฟล์ Excel ที่มีหลายชีต เนื้อหายาว ทำให้ AI ต้องตอบละเอียดขึ้นตามไปด้วย)
        max_tokens=4000,
        messages=[{"role": "user", "content": message_content}],
    )
    result_text = "".join(block.text for block in response.content if block.type == "text")

    # 🆕 เช็คว่าคำตอบถูกตัดกลางคันเพราะชน max_tokens จริงไหม (stop_reason == "max_tokens") ถ้าใช่
    # จะได้รู้สาเหตุที่แท้จริงทันที ไม่ต้องเดาสุ่มว่าทำไม JSON ไม่สมบูรณ์
    if response.stop_reason == "max_tokens":
        result_text += "\n\n[⚠️ คำตอบถูกตัดกลางคัน เพราะยาวเกิน max_tokens ที่ตั้งไว้]"

    return result_text, response.usage


def _call_claude_text_analysis(api_key, prompt_text):
    """ส่ง Prompt ข้อความล้วนไปให้ Claude วิเคราะห์ (ใช้กับการวิเคราะห์แนวโน้มจากประวัติ ไม่มี PDF แนบ)"""
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt_text}],
    )
    result_text = "".join(block.text for block in response.content if block.type == "text")
    return result_text, response.usage


def render_tab_fundamental_watchlist():
    st.markdown("### 📊 Watchlist เชิงปัจจัยพื้นฐาน")
    st.markdown(
        "ติดตามหุ้นที่สนใจเชิงปัจจัยพื้นฐาน — ดาวน์โหลดงบการเงินจาก set.or.th เอง แล้วอัปโหลดให้ AI "
        "อ่านและสกัดตัวเลขสำคัญให้อัตโนมัติ บันทึกประวัติย้อนหลัง เปรียบเทียบการเติบโตข้ามไตรมาสได้ "
        "**(แยกจากแท็บ Watchlist เดิมที่ใช้ติดตามราคาเพื่อเทรดโดยสิ้นเชิง)**"
    )

    api_key = st.secrets.get("ANTHROPIC_API_KEY") if hasattr(st, "secrets") else None
    if not api_key:
        # 🆕 แสดง "ชื่อ Secret ที่ระบบเจอจริง" ด้วย (ไม่โชว์ค่าจริงเพื่อความปลอดภัย) เพื่อวินิจฉัย
        # ปัญหาการพิมพ์ผิด/วางผิดตำแหน่งได้ตรงจุด
        _found_keys = list(st.secrets.keys()) if hasattr(st, "secrets") else []
        st.warning(
            "⚠️ ยังไม่ได้ตั้งค่า Claude API Key ครับ — ไปที่ Streamlit Cloud → Settings → Secrets "
            "แล้วเพิ่ม `ANTHROPIC_API_KEY = \"sk-ant-...\"`\n\n"
            f"🔍 **ตรวจสอบ:** ตอนนี้ระบบเจอชื่อ Secret ทั้งหมด {len(_found_keys)} รายการ: "
            f"{', '.join(_found_keys) if _found_keys else '(ไม่เจอเลยสักตัว)'}"
        )
        return

    spreadsheet_name = get_active_sheet_name()

    # --- 1. จัดการรายชื่อหุ้นใน Watchlist เชิงปัจจัยพื้นฐาน ---
    st.divider()
    with st.form("add_fundamental_ticker_form"):
        col1, col2 = st.columns([3, 1])
        new_ticker = col1.text_input("เพิ่มหุ้นเข้า Watchlist เชิงปัจจัยพื้นฐาน", placeholder="เช่น PTT, AOT, CPALL")
        add_submitted = col2.form_submit_button("➕ เพิ่ม", use_container_width=True)

    if add_submitted and new_ticker.strip():
        success, msg = add_to_fundamental_watchlist(spreadsheet_name, new_ticker)
        if success:
            st.success(msg)
            st.cache_data.clear()
            st.rerun()
        else:
            st.warning(msg)

    watchlist = load_fundamental_watchlist(spreadsheet_name)

    if not watchlist:
        st.info("ยังไม่มีหุ้นใน Watchlist เชิงปัจจัยพื้นฐานเลยครับ — เพิ่มหุ้นตัวแรกด้านบนได้เลย")
        return

    st.divider()
    st.markdown("#### 📋 หุ้นในการติดตาม")

    for item in watchlist:
        ticker = str(item.get('Ticker', '')).strip().upper()
        set_url = get_set_financial_statement_url(ticker)

        with st.container(border=True):
            h1, h2, h3 = st.columns([2, 1, 1])
            h1.markdown(f"### {ticker}")
            h2.markdown(f"[📥 ดาวน์โหลดงบจาก SET]({set_url})")
            if h3.button("🗑️ ลบออกจาก Watchlist", key=f"del_fund_{ticker}"):
                success, msg = remove_from_fundamental_watchlist(spreadsheet_name, ticker)
                if success:
                    st.success(msg)
                    st.cache_data.clear()
                    st.rerun()

            # --- 2. อัปโหลดงบไตรมาสใหม่ ให้ AI วิเคราะห์ ---
            with st.expander(f"📤 อัปโหลดงบการเงินไตรมาสใหม่ — {ticker}"):
                with st.form(f"upload_form_{ticker}"):
                    u1, u2, u3 = st.columns([1, 1, 2])
                    quarter = u1.selectbox("ไตรมาส", [1, 2, 3, 4], key=f"q_{ticker}")
                    year = u2.number_input("ปี (พ.ศ.)", min_value=2560, max_value=2580, value=2568, step=1, key=f"y_{ticker}")
                    # 🔧 แก้บั๊ก: เดิมรับแค่ .pdf แต่ไฟล์งบการเงินที่ดาวน์โหลดจาก set.or.th มักแตกไฟล์
                    # ออกมาเป็น .xlsx หรือ .docx (ไม่ใช่ .pdf เสมอไป) ตอนนี้รับได้ทั้ง 3 ประเภทแล้ว
                    doc_file = u3.file_uploader("ไฟล์งบการเงิน (PDF/Excel/Word)", type=["pdf", "xlsx", "docx"], key=f"doc_{ticker}")
                    upload_submitted = st.form_submit_button("🔍 วิเคราะห์งบนี้ด้วย AI", type="primary")

                if upload_submitted:
                    if doc_file is None:
                        st.warning("กรุณาแนบไฟล์ก่อนครับ (รองรับ PDF, Excel, Word)")
                    else:
                        with st.spinner("กำลังให้ AI อ่านงบการเงิน... (10-30 วินาที)"):
                            try:
                                _file_ext = doc_file.name.split(".")[-1].lower()
                                prompt = ANALYSIS_PROMPT_TEMPLATE.format(ticker=ticker, quarter=quarter, year=year)
                                result_text, usage = _call_claude_document_analysis(
                                    api_key, doc_file.read(), _file_ext, prompt
                                )

                                # 🔧 แก้บั๊ก: เดิมเช็คแค่ "ขึ้นต้นด้วย ```" เท่านั้น ถ้า AI ตอบมาโดยมี
                                # ข้อความอื่นนำหน้าก่อน JSON (เช่น "นี่คือผลวิเคราะห์ครับ:" ก่อนเข้า
                                # เนื้อหาจริง) จะแกะไม่ออกทันที เปลี่ยนมาใช้ Regex ค้นหาตำแหน่ง { แรก
                                # และ } สุดท้ายในข้อความทั้งหมดแทน ทนทานกว่ามาก ไม่สนใจว่าจะมีข้อความ
                                # อื่นล้อมรอบ JSON อยู่หรือไม่
                                import re
                                _json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
                                if not _json_match:
                                    raise json.JSONDecodeError("ไม่พบโครงสร้าง JSON ในคำตอบเลย", result_text, 0)
                                metrics = json.loads(_json_match.group(0))

                                success, msg = save_fundamental_analysis(
                                    spreadsheet_name, ticker, quarter, year, metrics, result_text
                                )
                                if success:
                                    st.success(f"✅ วิเคราะห์และบันทึกสำเร็จ! (token: อินพุต {usage.input_tokens:,} / เอาต์พุต {usage.output_tokens:,})")
                                    st.cache_data.clear()
                                    st.rerun()
                                else:
                                    st.error(msg)
                            except json.JSONDecodeError:
                                # 🆕 แสดงคำตอบจริงที่ AI ส่งกลับมา (ตัวอย่าง 600 ตัวอักษรแรก) ให้เห็น
                                # ตรงๆ แทนที่จะซ่อนไว้ จะได้วินิจฉัยได้ทันทีว่าติดปัญหาอะไรกันแน่
                                st.error("⚠️ AI ตอบกลับมาในรูปแบบที่ไม่ใช่ JSON ที่คาดไว้")
                                st.code(result_text[:600], language=None)
                            except Exception as e:
                                st.error(f"❌ เกิดข้อผิดพลาด: {e}")

            # --- 3. แสดงประวัติย้อนหลัง + วิเคราะห์แนวโน้ม ---
            df_history = load_fundamental_analysis_history(spreadsheet_name, ticker)
            if not df_history.empty:
                st.markdown(f"##### 📈 ประวัติย้อนหลัง — {ticker} ({len(df_history)} ไตรมาส)")

                display_cols = [c for c in ['Quarter', 'Year', 'Revenue', 'Net_Profit', 'EPS', 'Net_Margin_Pct'] if c in df_history.columns]
                if display_cols:
                    st.dataframe(df_history[display_cols], use_container_width=True, hide_index=True)

                if len(df_history) >= 2:
                    if st.button(f"🤖 ให้ AI วิเคราะห์แนวโน้มการเติบโต — {ticker}", key=f"trend_{ticker}"):
                        with st.spinner("กำลังวิเคราะห์แนวโน้ม..."):
                            try:
                                # 🔧 แก้บั๊กเดียวกัน: to_markdown() ต้องพึ่งไลบรารี tabulate ที่ไม่มี
                                # อยู่ในระบบ เปลี่ยนมาใช้ to_csv() แทน (AI อ่านเข้าใจได้เหมือนกัน)
                                history_text = df_history.to_csv(index=False)
                                prompt = TREND_ANALYSIS_PROMPT.format(ticker=ticker, history_text=history_text)
                                result_text, usage = _call_claude_text_analysis(api_key, prompt)
                                st.markdown(result_text)
                                st.caption(f"💰 token: อินพุต {usage.input_tokens:,} / เอาต์พุต {usage.output_tokens:,}")
                            except Exception as e:
                                st.error(f"❌ เกิดข้อผิดพลาด: {e}")
                else:
                    st.caption("💡 มีข้อมูลตั้งแต่ 2 ไตรมาสขึ้นไป ถึงจะให้ AI วิเคราะห์แนวโน้มการเติบโตได้ครับ")
