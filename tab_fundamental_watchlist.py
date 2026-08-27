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

MODEL_NAME = "claude-sonnet-5"

ANALYSIS_PROMPT_TEMPLATE = """คุณเป็นนักวิเคราะห์หุ้นสไตล์ Mark Minervini ที่เน้นดูการเติบโตของยอดขายและกำไรเป็นหลัก
อ่านงบการเงินไตรมาสที่แนบมา (บริษัท {ticker} ไตรมาสที่ {quarter}/{year}) แล้วตอบกลับเป็น JSON เท่านั้น
ห้ามมีข้อความอื่นนอกเหนือจาก JSON เลย ตามโครงสร้างนี้เป๊ะๆ:

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


def _call_claude_pdf_analysis(api_key, pdf_bytes, prompt_text):
    """ส่ง PDF + Prompt ไปให้ Claude วิเคราะห์ คืนค่าเป็น (สำเร็จหรือไม่, ข้อความผลลัพธ์หรือ error, usage info)"""
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    base64_data = base64.standard_b64encode(pdf_bytes).decode("utf-8")
    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=1500,
        messages=[{
            "role": "user",
            "content": [
                {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": base64_data}},
                {"type": "text", "text": prompt_text},
            ],
        }],
    )
    result_text = "".join(block.text for block in response.content if block.type == "text")
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
        st.warning(
            "⚠️ ยังไม่ได้ตั้งค่า Claude API Key ครับ — ไปที่ Streamlit Cloud → Settings → Secrets "
            "แล้วเพิ่ม `ANTHROPIC_API_KEY = \"sk-ant-...\"`"
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
                    pdf_file = u3.file_uploader("ไฟล์ PDF งบการเงิน", type=["pdf"], key=f"pdf_{ticker}")
                    upload_submitted = st.form_submit_button("🔍 วิเคราะห์งบนี้ด้วย AI", type="primary")

                if upload_submitted:
                    if pdf_file is None:
                        st.warning("กรุณาแนบไฟล์ PDF ก่อนครับ")
                    else:
                        with st.spinner("กำลังให้ AI อ่านงบการเงิน... (10-30 วินาที)"):
                            try:
                                prompt = ANALYSIS_PROMPT_TEMPLATE.format(ticker=ticker, quarter=quarter, year=year)
                                result_text, usage = _call_claude_pdf_analysis(api_key, pdf_file.read(), prompt)

                                # แกะ JSON ออกจากคำตอบ (เผื่อ Claude ใส่ ```json ครอบมาด้วย)
                                cleaned = result_text.strip()
                                if cleaned.startswith("```"):
                                    cleaned = cleaned.split("```")[1]
                                    if cleaned.startswith("json"):
                                        cleaned = cleaned[4:]
                                metrics = json.loads(cleaned.strip())

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
                                st.error("⚠️ AI ตอบกลับมาในรูปแบบที่ไม่ใช่ JSON ที่คาดไว้ ลองอัปโหลดใหม่อีกครั้งครับ")
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
                                history_text = df_history.to_markdown(index=False)
                                prompt = TREND_ANALYSIS_PROMPT.format(ticker=ticker, history_text=history_text)
                                result_text, usage = _call_claude_text_analysis(api_key, prompt)
                                st.markdown(result_text)
                                st.caption(f"💰 token: อินพุต {usage.input_tokens:,} / เอาต์พุต {usage.output_tokens:,}")
                            except Exception as e:
                                st.error(f"❌ เกิดข้อผิดพลาด: {e}")
                else:
                    st.caption("💡 มีข้อมูลตั้งแต่ 2 ไตรมาสขึ้นไป ถึงจะให้ AI วิเคราะห์แนวโน้มการเติบโตได้ครับ")
