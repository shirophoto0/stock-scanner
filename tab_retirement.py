# =============================================================
# tab_retirement.py
# 🎯 เครื่องคำนวณเป้าหมายเกษียณ (Retirement Goal Calculator)
# แยกคำนวณการเติบโตของ PVD ต่างหากจากพอร์ตทั่วไป (คนละอัตราผลตอบแทน คนละเงื่อนไข)
# เพราะ PVD มักมีเงินสมทบจากนายจ้างและเงื่อนไขถอนที่ต่างจากการลงทุนด้วยตัวเองล้วนๆ
# =============================================================
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from backend_functions import get_gsheet_client, get_worksheet_safely, get_active_sheet_name
from theme import style_plotly, render_metric_card, get_theme_colors


def _fetch_pvd_history_and_cagr():
    """
    🆕 ดึงประวัติ PVD ทั้งหมด (ไม่ใช่แค่แถวล่าสุด) แล้วคำนวณ CAGR (อัตราเติบโตทบต้นเฉลี่ยต่อปี)
    จากข้อมูลจริงย้อนหลัง แทนการให้ผู้ใช้เดาอัตราเติบโตเอง คืนค่าเป็น (มูลค่าล่าสุด, CAGR %, จำนวนปีที่มีข้อมูล)
    """
    try:
        client = get_gsheet_client()
        sheet_pvd = get_worksheet_safely(client, get_active_sheet_name(), 'Provident_Fund')
        if sheet_pvd is None:
            return 0.0, 0.0, 0
        records = sheet_pvd.get_all_records()
        if not records:
            return 0.0, 0.0, 0

        def _get_val(row):
            raw = row.get('Grand_Total', row.get('Value', 0))
            return float(str(raw).replace(',', '')) if str(raw).strip() != "" else 0.0

        last_val = _get_val(records[-1])

        if len(records) < 2:
            return last_val, 0.0, 0

        first_val = _get_val(records[0])
        first_year = records[0].get('Year_CE')
        last_year = records[-1].get('Year_CE')

        years_span = None
        if first_year and last_year:
            try:
                years_span = float(last_year) - float(first_year)
            except (ValueError, TypeError):
                years_span = None
        if not years_span or years_span <= 0:
            years_span = len(records) - 1  # สำรอง: นับจากจำนวนแถว (สมมติบันทึกปีละครั้ง)

        if first_val > 0 and years_span > 0:
            cagr = ((last_val / first_val) ** (1 / years_span) - 1) * 100
        else:
            cagr = 0.0

        return last_val, round(cagr, 2), int(years_span)
    except Exception:
        return 0.0, 0.0, 0


def _project_growth(current_age, retirement_age, other_current, pvd_current,
                     monthly_savings, annual_savings_increase_pct,
                     annual_return_pct, pvd_annual_growth_pct):
    """
    คำนวณโปรเจกชัน Net Worth รายปี — แยกเติบโต PVD กับพอร์ตทั่วไปคนละอัตรา แล้วรวมกันแสดงผล
    เงินออมต่อเดือนเพิ่มขึ้นทุกปีตามอัตราที่กำหนด (จำลองเงินเดือน/ความสามารถออมที่โตขึ้นตามอายุงาน)
    คืนค่าเป็น (list อายุแต่ละปี, list Net Worth รวมแต่ละปี, Net Worth รวม ณ ปีเกษียณ)
    """
    years_to_go = max(retirement_age - current_age, 0)
    ages = [current_age]
    totals = [other_current + pvd_current]

    _other = other_current
    _pvd = pvd_current
    _monthly_savings_now = monthly_savings
    for _ in range(years_to_go):
        _other = _other * (1 + annual_return_pct / 100) + _monthly_savings_now * 12
        _pvd = _pvd * (1 + pvd_annual_growth_pct / 100)
        _monthly_savings_now = _monthly_savings_now * (1 + annual_savings_increase_pct / 100)
        ages.append(ages[-1] + 1)
        totals.append(_other + _pvd)

    return ages, totals, totals[-1] if totals else 0.0


def _required_monthly_savings(target_shortfall, years_to_go, annual_return_pct):
    """คำนวณเงินออมเพิ่มต่อเดือนที่ต้องใช้ ถึงจะปิดช่องว่างให้ถึงเป้าหมายพอดี (สูตร Future Value of Annuity)"""
    if target_shortfall <= 0 or years_to_go <= 0:
        return 0.0
    months = years_to_go * 12
    monthly_rate = (1 + annual_return_pct / 100) ** (1 / 12) - 1
    if monthly_rate > 0:
        annuity_factor = ((1 + monthly_rate) ** months - 1) / monthly_rate
        return target_shortfall / annuity_factor
    return target_shortfall / months


def _years_money_lasts(principal, monthly_withdrawal, annual_return_pct, cap_years=100):
    """คำนวณว่าเงินก้อนจะอยู่ได้กี่ปีหลังเกษียณ (ยังคงได้ผลตอบแทนต่อระหว่างถอนใช้ทุกเดือน)"""
    if principal <= 0:
        return 0.0
    monthly_rate = (1 + annual_return_pct / 100) ** (1 / 12) - 1
    balance = principal
    months = 0
    max_months = cap_years * 12
    while balance > 0 and months < max_months:
        balance = balance * (1 + monthly_rate) - monthly_withdrawal
        months += 1
    return months / 12


def render_tab_retirement():
    st.markdown("### 🎯 เครื่องคำนวณเป้าหมายเกษียณ")
    st.markdown(
        "กรอกข้อมูลด้านล่าง ระบบจะคำนวณว่าตามแผนการออมปัจจุบัน จะถึงเป้าหมาย Net Worth "
        "ตอนเกษียณได้ทันหรือไม่ พร้อมแยกคำนวณการเติบโตของ **PVD ต่างหาก** จากพอร์ตทั่วไป "
        "เพราะมักมีอัตราเติบโต/เงื่อนไขต่างกัน"
    )

    # 🆕 ดึง Net Worth (ไม่รวมอสังหาฯ) + PVD จาก session_state ที่แท็บ "ภาพรวม Net Worth" เตรียมไว้
    # ให้อัตโนมัติ (ไม่ต้องให้ผู้ใช้กรอกเอง) ถ้ายังไม่มีค่า (เช่น ยังไม่เคยเปิดแท็บภาพรวมเลยในเซสชันนี้)
    # จะเตือนให้ไปเปิดแท็บนั้นก่อนสักครั้ง
    _current_net_worth = st.session_state.get('net_worth_excl_re')
    _current_pvd = st.session_state.get('pvd_value')

    if _current_net_worth is None or _current_pvd is None:
        st.warning(
            "⚠️ ยังไม่มีข้อมูล Net Worth ปัจจุบัน — กรุณาเปิดแท็บ \"🌐 ภาพรวมความมั่งคั่ง\" → "
            "\"ภาพรวม Net Worth & สัดส่วนสินทรัพย์\" สักครั้งก่อน (ระบบจะดึงมาให้อัตโนมัติ) แล้วค่อยกลับมาที่นี่"
        )
        return

    _pvd_last_value, _pvd_cagr, _pvd_years_span = _fetch_pvd_history_and_cagr()

    st.info(
        f"💰 Net Worth ปัจจุบัน (ไม่รวมอสังหาฯ, รวม PVD แล้ว): **{_current_net_worth:,.0f} ฿** "
        f"(ในนี้เป็น PVD **{_current_pvd:,.0f} ฿**) — ดึงมาจากแท็บภาพรวม Net Worth อัตโนมัติ"
    )

    with st.form("retirement_calc_form"):
        st.markdown("#### 📝 ข้อมูลพื้นฐาน")
        c1, c2 = st.columns(2)
        with c1:
            current_age = st.number_input("อายุปัจจุบัน", min_value=18, max_value=90, value=35, step=1)
            target_net_worth = st.number_input(
                "เป้าหมาย Net Worth ตอนเกษียณ (บาท)", min_value=0.0, value=20000000.0, step=100000.0, format="%.0f"
            )
        with c2:
            retirement_age = st.number_input("อายุที่ต้องการเกษียณ", min_value=18, max_value=90, value=50, step=1)
            monthly_expense_after = st.number_input(
                "ค่าใช้จ่ายต่อเดือนที่คาดหวังหลังเกษียณ (บาท)", min_value=0.0, value=50000.0, step=1000.0, format="%.0f"
            )

        st.markdown("#### 📈 สมมติฐานอัตราผลตอบแทน")
        r1, r2 = st.columns(2)
        with r1:
            annual_return_pct = st.slider(
                "อัตราผลตอบแทนเฉลี่ยต่อปี — พอร์ตทั่วไป (%)", 0.0, 20.0, 7.0, step=0.5,
                help="ใช้กับ Net Worth ส่วนที่ไม่ใช่ PVD (หุ้น กองทุน ทองคำ ฯลฯ)"
            )
        with r2:
            # 🆕 ใช้ CAGR จากข้อมูล PVD จริงย้อนหลังเป็นค่าเริ่มต้นของ slider แทนเลขสุ่มเดา
            # (ยังปรับเองทับได้ตามปกติ ถ้าอยากสมมติสถานการณ์อื่น)
            _pvd_default = _pvd_cagr if _pvd_years_span > 0 else 6.0
            pvd_annual_growth_pct = st.slider(
                "อัตราการเติบโตต่อปี — PVD (%)", 0.0, 20.0, float(min(max(_pvd_default, 0.0), 20.0)), step=0.5,
                help=(
                    f"คำนวณจากข้อมูล PVD จริงย้อนหลัง {_pvd_years_span} ปี ได้ {_pvd_cagr:.2f}%/ปี (ปรับเองทับได้)"
                    if _pvd_years_span > 0 else "ยังไม่มีข้อมูล PVD ย้อนหลังพอคำนวณ ใช้ค่าเริ่มต้นไปก่อน (ปรับเองได้)"
                )
            )
            if _pvd_years_span > 0:
                st.caption(f"📊 อ้างอิงจากข้อมูลจริง {_pvd_years_span} ปีที่ผ่านมา (CAGR = {_pvd_cagr:.2f}%/ปี)")

        st.markdown("#### 💵 เงินออม/ลงทุนต่อเดือน")
        st.caption("รวมเงินออม/ลงทุนทุกประเภท (เงินสด, ซื้อหุ้น, สหกรณ์ ฯลฯ) ยกเว้น PVD ซึ่งคำนวณแยกไว้แล้วด้านบน")
        s1, s2 = st.columns(2)
        with s1:
            monthly_savings = st.number_input(
                "เงินออม/ลงทุนเพิ่มต่อเดือน (บาท, ไม่รวม PVD)", min_value=0.0, value=20000.0, step=1000.0, format="%.0f"
            )
        with s2:
            # 🆕 อัตราเพิ่มเงินเก็บต่อปี (ทบต้นทุกปีจนถึงอายุเกษียณ) จำลองเงินเดือน/ความสามารถออมที่โต
            # ขึ้นตามอายุงาน แทนที่จะสมมติว่าออมเท่าเดิมทุกปีตลอดจนเกษียณ
            annual_savings_increase_pct = st.slider(
                "% อัตราเพิ่มเงินเก็บต่อปี (ทบต้น)", 0.0, 20.0, 3.0, step=0.5,
                help="เช่น ตั้ง 3% แปลว่าปีถัดไปออมเพิ่มขึ้นอีก 3% จากปีก่อน ทบต้นไปเรื่อยๆ จนถึงอายุเกษียณ"
            )

        submitted = st.form_submit_button("🧮 คำนวณ", use_container_width=True)

    # 🔧 แก้บั๊ก: เดิมเช็คแค่ "submitted" เฉยๆ ซึ่งเป็น True แค่รอบเดียวตอนกดปุ่มจริงๆ พอไปเลื่อน
    # slider หุ้นปันผล (อยู่นอกฟอร์ม) ด้านล่าง หน้าเว็บจะรันใหม่ทั้งหมด แต่รอบนั้น submitted จะ
    # กลับเป็น False เพราะไม่ได้เพิ่งกดปุ่ม ทำให้ระบบเข้าใจผิดว่า "ยังไม่เคยคำนวณ" แล้วเด้งกลับไป
    # หน้าแรกทันที ตอนนี้ใช้ session_state จดจำว่า "เคยกดคำนวณไปแล้วอย่างน้อย 1 ครั้ง" แบบถาวร
    # แทน (ค่าตัวแปรจากฟอร์ม เช่น current_age, target_net_worth ฯลฯ ยังคงค่าถูกต้องข้ามการรันซ้ำ
    # อยู่แล้วโดยธรรมชาติของ Streamlit ไม่ต้องเก็บซ้ำเพิ่มเติม)
    if submitted:
        st.session_state['retirement_calculated'] = True

    if not st.session_state.get('retirement_calculated', False):
        return

    if retirement_age <= current_age:
        st.error("อายุที่ต้องการเกษียณต้องมากกว่าอายุปัจจุบันครับ")
        return

    years_to_go = retirement_age - current_age
    other_current = max(_current_net_worth - _current_pvd, 0.0)

    ages, totals, projected_at_retirement = _project_growth(
        current_age, retirement_age, other_current, _current_pvd,
        monthly_savings, annual_savings_increase_pct, annual_return_pct, pvd_annual_growth_pct
    )

    shortfall = target_net_worth - projected_at_retirement
    on_track = shortfall <= 0

    st.divider()
    st.markdown("#### 📊 ผลการคำนวณ")

    m1, m2, m3 = st.columns(3)
    render_metric_card(
        m1, f"Net Worth คาดการณ์ตอนอายุ {retirement_age}",
        f"{projected_at_retirement:,.0f} ฿", icon="📈"
    )
    render_metric_card(
        m2, "เป้าหมาย", f"{target_net_worth:,.0f} ฿", icon="🎯"
    )
    render_metric_card(
        m3, "ส่วนต่าง", f"{abs(shortfall):,.0f} ฿", icon="✅" if on_track else "⚠️",
        delta="เกินเป้าหมาย" if on_track else "ยังขาดอยู่", delta_positive=on_track
    )

    if on_track:
        st.success(
            f"🎉 ตามแผนการออมปัจจุบัน คาดว่าจะถึงเป้าหมายได้ทันตอนอายุ {retirement_age} ปี "
            f"(เกินเป้าหมายไปอีก {abs(shortfall):,.0f} ฿)"
        )
    else:
        _extra_monthly = _required_monthly_savings(shortfall, years_to_go, annual_return_pct)
        st.warning(
            f"⚠️ ตามแผนการออมปัจจุบัน คาดว่าจะยังไม่ถึงเป้าหมาย ขาดอยู่ {shortfall:,.0f} ฿ "
            f"ตอนอายุ {retirement_age} ปี — ถ้าต้องการให้ถึงเป้าหมายพอดี ต้องออมเพิ่มอีกประมาณ "
            f"**{_extra_monthly:,.0f} ฿/เดือน** (รวมเป็น {monthly_savings + _extra_monthly:,.0f} ฿/เดือน "
            f"ณ ปีแรก ก่อนเพิ่มขึ้นตามอัตรา {annual_savings_increase_pct:.1f}%/ปีที่ตั้งไว้)"
        )

    # กราฟโปรเจกชัน
    st.markdown("#### 📉 กราฟโปรเจกชัน Net Worth ถึงวัยเกษียณ")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=ages, y=totals, mode='lines+markers', name='Net Worth คาดการณ์',
        line=dict(width=3, color='#7C9885')
    ))
    fig.add_trace(go.Scatter(
        x=[ages[0], ages[-1]], y=[target_net_worth, target_net_worth],
        mode='lines', name='เป้าหมาย', line=dict(width=2, color='#C9A961', dash='dash')
    ))
    fig.update_layout(
        height=400, xaxis_title="อายุ", yaxis_title="Net Worth (บาท)",
        margin=dict(l=20, r=20, t=20, b=20)
    )
    st.plotly_chart(style_plotly(fig), use_container_width=True)

    # เช็คความยั่งยืนหลังเกษียณ (กฎ 4%)
    st.divider()
    st.markdown("#### 🏖️ เช็คความยั่งยืนของเงินหลังเกษียณ (แบบถอนใช้ทั่วไป)")
    _final_amount = max(projected_at_retirement, 0)
    _years_last = _years_money_lasts(_final_amount, monthly_expense_after, annual_return_pct)
    _safe_monthly_4pct = (_final_amount * 0.04) / 12

    s1, s2 = st.columns(2)
    render_metric_card(
        s1, "เงินก้อนจะอยู่ได้ประมาณ",
        f"{_years_last:,.0f} ปี" if _years_last < 100 else "100+ ปี (ไม่มีวันหมด)",
        icon="⏳", caption=f"คำนวณจากค่าใช้จ่าย {monthly_expense_after:,.0f} ฿/เดือน (เงินยังได้ผลตอบแทนต่อระหว่างถอนใช้)"
    )
    render_metric_card(
        s2, "ถอนใช้ปลอดภัยตามกฎ 4%",
        f"{_safe_monthly_4pct:,.0f} ฿/เดือน",
        icon="🛡️", caption="แนวทางมาตรฐานสากล ถอน 4% ของเงินต้นต่อปี มีโอกาสสูงที่เงินจะไม่มีวันหมด"
    )

    if _years_last >= 100:
        st.success("🎉 ด้วยค่าใช้จ่ายที่ตั้งไว้ เงินก้อนนี้แทบไม่มีวันหมดเลยครับ (มากกว่า 100 ปี)")
    elif monthly_expense_after > _safe_monthly_4pct:
        st.warning(
            f"⚠️ ค่าใช้จ่ายที่ตั้งไว้ ({monthly_expense_after:,.0f} ฿/เดือน) สูงกว่าระดับที่ถอนใช้ได้อย่างปลอดภัยตามกฎ 4% "
            f"({_safe_monthly_4pct:,.0f} ฿/เดือน) — เงินอาจหมดก่อนที่คาดไว้ ลองพิจารณาลดค่าใช้จ่าย หรือเพิ่มเป้าหมาย Net Worth ดูครับ"
        )
    else:
        st.info(f"ค่าใช้จ่ายที่ตั้งไว้อยู่ในระดับที่ปลอดภัยตามกฎ 4% ครับ")

    # 🆕 กลยุทธ์แบ่งเงินไปลงทุนหุ้นปันผล — คำนวณแยกจากกฎ 4% ด้านบน ให้เห็นเทียบกันว่าถ้าเปลี่ยนมา
    # ใช้กลยุทธ์นี้แทน จะมีเงินใช้ได้จริงต่อเดือนเท่าไหร่ แสดง 2 แบบให้เทียบกัน:
    #   1) ไม่แตะเงินต้นเลย — ใช้แค่เงินปันผลจากส่วนที่ลงทุนหุ้นปันผล เงินส่วนที่เหลือเก็บไว้เฉยๆ
    #   2) แตะเงินต้น 4% — เอาเงินปันผลจากข้อ 1) มาบวกเพิ่มกับเงินที่ถอนจาก "ส่วนที่เหลือ" ตามกฎ 4%
    #      ต่อปี ได้เงินใช้ต่อเดือนมากขึ้น แต่เงินส่วนที่เหลือจะค่อยๆ ลดลงไปตามเวลา
    st.divider()
    st.markdown("#### 💎 กลยุทธ์แบ่งเงินไปลงทุนหุ้นปันผล (ทางเลือกเทียบกับกฎ 4%)")
    st.caption("จำลองการแบ่งเงินก้อนหลังเกษียณส่วนหนึ่งไปลงทุนหุ้นปันผล ใช้เงินปันผลเป็นรายได้ต่อเดือน")

    d1, d2 = st.columns(2)
    with d1:
        dividend_alloc_pct = st.slider(
            "% ของ Wealth ทั้งหมด ไปลงทุนหุ้นปันผล", 0, 100, 50, step=5, key="dividend_alloc_pct"
        )
    with d2:
        dividend_yield_pct = st.slider(
            "% เงินปันผลเฉลี่ยต่อปี", 0.0, 15.0, 5.0, step=0.5, key="dividend_yield_pct"
        )

    dividend_invested_amount = _final_amount * dividend_alloc_pct / 100
    remaining_amount = _final_amount - dividend_invested_amount
    monthly_dividend_income = (dividend_invested_amount * dividend_yield_pct / 100) / 12

    render_metric_card(st, "เงินลงทุนในหุ้นปันผล", f"{dividend_invested_amount:,.0f} ฿ (จากทั้งหมด {_final_amount:,.0f} ฿)", icon="💎")

    st.markdown("##### 🔒 แบบที่ 1: ไม่แตะเงินต้นเลย")
    nv1, nv2 = st.columns(2)
    render_metric_card(nv1, "เงินส่วนที่เหลือ (เก็บไว้เฉยๆ ไม่ใช้)", f"{remaining_amount:,.0f} ฿", icon="🏦")
    render_metric_card(
        nv2, "รายได้ใช้ได้จริงต่อเดือน", f"{monthly_dividend_income:,.0f} ฿/เดือน",
        icon="✨", caption="เฉพาะเงินปันผลเท่านั้น เงินต้นทั้งหมดยังอยู่ครบ ไม่ลดลงเลย"
    )

    # 🆕 แบบที่ 2: ดึงเงินแบบ "ไล่ลำดับ" — ถ้าปันผลเพียงอย่างเดียวไม่พอกับค่าใช้จ่าย ให้ดึงส่วนต่าง
    # (shortfall) จาก "เงินส่วนที่เหลือ" มาเสริมก่อน (Phase 1) พอเงินส่วนที่เหลือหมด ค่อยไปดึงส่วนต่าง
    # เดิมนี้จาก "เงินก้อนที่ลงทุนหุ้นปันผล" ต่อ (Phase 2 — เงินก้อนนี้ยังได้ปันผลของตัวเองต่อไปด้วย
    # ระหว่างถูกดึงออก) คำนวณว่าทั้ง 2 ช่วงรวมกันจะอยู่ได้ทั้งหมดกี่ปี
    st.markdown("##### 💸 แบบที่ 2: ดึงเงินแบบไล่ลำดับ (ส่วนที่เหลือหมดก่อน แล้วค่อยแตะก้อนปันผล)")

    _shortfall_monthly = max(monthly_expense_after - monthly_dividend_income, 0)

    if _shortfall_monthly <= 0:
        st.success("ปันผลเพียงอย่างเดียวก็พอแล้วครับ ไม่จำเป็นต้องดึงเงินต้นส่วนไหนเพิ่มเลย")
        _phase1_years, _phase2_years, _total_years = 0.0, 0.0, float('inf')
    else:
        _phase1_years = _years_money_lasts(remaining_amount, _shortfall_monthly, annual_return_pct)
        _phase2_years = _years_money_lasts(dividend_invested_amount, _shortfall_monthly, dividend_yield_pct)
        _total_years = _phase1_years + _phase2_years

        tv1, tv2, tv3 = st.columns(3)
        render_metric_card(
            tv1, "ต้องดึงเพิ่มจากปันผลอีก", f"{_shortfall_monthly:,.0f} ฿/เดือน",
            icon="📉", caption="ส่วนต่างที่ปันผลอย่างเดียวยังไม่พอ"
        )
        render_metric_card(
            tv2, "ช่วงที่ 1: ดึงจากเงินส่วนที่เหลือ", f"{_phase1_years:,.0f} ปี" if _phase1_years < 100 else "100+ ปี",
            icon="🏦", caption="อยู่ได้นานแค่ไหนก่อนเงินส่วนที่เหลือหมด"
        )
        render_metric_card(
            tv3, "ช่วงที่ 2: ดึงต่อจากก้อนปันผล", f"{_phase2_years:,.0f} ปี" if _phase2_years < 100 else "100+ ปี",
            icon="💎", caption="อยู่ได้เพิ่มอีกเท่าไหร่ หลังเริ่มแตะก้อนปันผล"
        )

        st.markdown(
            f"**รวมทั้งหมด: เงินจะพอใช้ไปได้ประมาณ {_total_years:,.0f} ปี** "
            f"(นับจากวันเกษียณ)" if _total_years < 100 else
            "**รวมทั้งหมด: เงินแทบไม่มีวันหมดเลยครับ (มากกว่า 100 ปี)**"
        )

    st.markdown("##### 📋 สรุปเทียบทั้ง 2 แบบ")
    if monthly_dividend_income >= monthly_expense_after:
        st.success(
            f"🎉 **แบบไม่แตะเงินต้น** ก็เพียงพอกับค่าใช้จ่ายที่ตั้งไว้แล้ว ({monthly_expense_after:,.0f} ฿/เดือน) "
            f"โดยที่เงินต้นทั้งก้อนยังอยู่ครบ ไม่ต้องแตะเงินต้นเลยครับ"
        )
    elif _total_years >= 100:
        st.info(
            f"แบบไม่แตะเงินต้นเพียงอย่างเดียวยังไม่พอ (ขาด {_shortfall_monthly:,.0f} ฿/เดือน) "
            f"แต่ถ้ายอมรับดึงเงินต้นเพิ่มแบบไล่ลำดับ (**แบบที่ 2**) เงินจะพอใช้ไปได้ตลอดชีวิตครับ"
        )
    else:
        st.warning(
            f"⚠️ ถ้าใช้ **แบบที่ 2** เงินทั้งหมดจะพอใช้ไปได้ประมาณ {_total_years:,.0f} ปีเท่านั้น "
            f"(ช่วงที่ 1: {_phase1_years:,.0f} ปี + ช่วงที่ 2: {_phase2_years:,.0f} ปี) — ถ้าอยากให้อยู่ได้นานกว่านี้ "
            f"ลองปรับสัดส่วน/อัตราปันผล ลดค่าใช้จ่าย หรือเพิ่มเป้าหมาย Net Worth ดูครับ"
        )
