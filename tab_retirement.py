# =============================================================
# tab_retirement.py
# 🎯 แท็บเกษียณอายุ — แบ่งเป็น 2 แท็บย่อย:
#   1. 📊 ประเมินเงินเกษียณ — คำนวณว่าจะถึงเป้าหมาย Net Worth ตอนเกษียณได้ทันไหม
#   2. 🌴 Life After Retirement — วางแผนว่าจะเอาเงินก้อนหลังเกษียณไปแบ่งลงทุนยังไง
#      ให้มีเงินใช้พอ (Concept 1: กำหนดสัดส่วนเอง / Concept 2: ให้ระบบออกแบบให้)
# =============================================================
import streamlit as st
import pandas as pd
from datetime import date
import plotly.graph_objects as go
from backend_functions import get_gsheet_client, get_worksheet_safely, get_active_sheet_name
from theme import style_plotly, render_metric_card, get_theme_colors


# =============================================================
# ฟังก์ชันคำนวณกลาง (ใช้ร่วมกันได้ทั้ง 2 แท็บย่อย)
# =============================================================
@st.cache_data(ttl=600, show_spinner=False)
def _fetch_pvd_history_and_cagr(active_sheet_name):
    """
    ดึงประวัติ PVD ทั้งหมด (ไม่ใช่แค่แถวล่าสุด) แล้วคำนวณ CAGR (อัตราเติบโตทบต้นเฉลี่ยต่อปี)
    จากข้อมูลจริงย้อนหลัง แทนการให้ผู้ใช้เดาอัตราเติบโตเอง คืนค่าเป็น (มูลค่าล่าสุด, CAGR %, จำนวนปีที่มีข้อมูล)
    🔧 แก้บั๊ก: เดิมฟังก์ชันนี้ไม่มีการจำผลลัพธ์ (cache) เลย ในขณะที่แท็บ "Life After Retirement"
    ข้างๆ กันมี slider เยอะมาก ทุกครั้งที่เลื่อน slider ไหนก็ตาม หน้าเว็บจะรันใหม่ทั้งหมด รวมถึง
    แท็บย่อยนี้ด้วย (ทุกแท็บย่อยรันพร้อมกันเสมอ) ทำให้ยิง API ไปขอข้อมูล PVD ซ้ำๆ ทุกครั้งที่ขยับ
    slider แม้แต่ครั้งเดียว จนชนโควตา 429 ได้ง่าย ตอนนี้จำผลลัพธ์ไว้ 10 นาที (เหมือนจุดอื่นในแอป
    เช่น อสังหาริมทรัพย์) พร้อมรับชื่อชีตของผู้ใช้เป็นพารามิเตอร์ตรงๆ กันข้อมูลปนกันข้ามผู้ใช้ด้วย
    """
    try:
        client = get_gsheet_client()
        sheet_pvd = get_worksheet_safely(client, active_sheet_name, 'Provident_Fund')
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


def _max_monthly_withdrawal_with_residual(principal, years, annual_return_pct, residual_pct=0.20):
    """
    🆕 คำนวณเงินถอนใช้ต่อเดือนสูงสุด ที่ทำให้เงินต้นค่อยๆ ลดลงจนเหลือพอดีตามสัดส่วนที่กำหนด
    (เช่น residual_pct=0.20 คือให้เหลือเงิน 20% ของเงินต้นเริ่มต้นตอนสิ้นสุดช่วงเวลา ไม่ใช่หมดเกลี้ยง
    หรือไม่แตะเลย) ใช้สูตร Annuity ที่มีมูลค่าคงเหลือปลายทาง (Annuity with Residual Value)
    """
    if principal <= 0 or years <= 0:
        return 0.0
    months = years * 12
    monthly_rate = (1 + annual_return_pct / 100) ** (1 / 12) - 1
    residual = principal * residual_pct
    if monthly_rate > 0:
        growth_factor = (1 + monthly_rate) ** months
        return (principal * growth_factor - residual) * monthly_rate / (growth_factor - 1)
    return (principal - residual) / months


def _required_wealth_with_residual(target_monthly, years, annual_return_pct, residual_pct=0.20):
    """
    🆕 ฟังก์ชันย้อนกลับของ _max_monthly_withdrawal_with_residual — หาว่าต้องมีเงินต้นเท่าไหร่
    ถึงจะถอนใช้ตามยอดที่ต้องการต่อเดือนได้ตลอดจำนวนปีที่กำหนด แล้วยังเหลือเงินตามสัดส่วนที่ตั้งไว้
    (เทียบเป็น % ของเงินต้นที่หาได้เอง) ตอนสิ้นสุดช่วงเวลาพอดี
    """
    if target_monthly <= 0 or years <= 0:
        return 0.0
    months = years * 12
    monthly_rate = (1 + annual_return_pct / 100) ** (1 / 12) - 1
    if monthly_rate > 0:
        growth_factor = (1 + monthly_rate) ** months
        denominator = monthly_rate * (growth_factor - residual_pct)
        if denominator <= 0:
            return float('inf')
        return target_monthly * (growth_factor - 1) / denominator
    return target_monthly * months / (1 - residual_pct)
    return months / 12


# =============================================================
# แท็บย่อยที่ 1: 📊 ประเมินเงินเกษียณ
# =============================================================
def _render_assessment_tab():
    st.markdown("### 🎯 เครื่องคำนวณเป้าหมายเกษียณ")
    st.markdown(
        "กรอกข้อมูลด้านล่าง ระบบจะคำนวณว่าตามแผนการออมปัจจุบัน จะถึงเป้าหมาย Net Worth "
        "ตอนเกษียณได้ทันหรือไม่ พร้อมแยกคำนวณการเติบโตของ **PVD ต่างหาก** จากพอร์ตทั่วไป "
        "เพราะมักมีอัตราเติบโต/เงื่อนไขต่างกัน"
    )

    # ดึง Net Worth (ไม่รวมอสังหาฯ) + PVD จาก session_state ที่แท็บ "ภาพรวม Net Worth" เตรียมไว้
    # ให้อัตโนมัติ (ไม่ต้องให้ผู้ใช้กรอกเอง) ถ้ายังไม่มีค่า จะเตือนให้ไปเปิดแท็บนั้นก่อนสักครั้ง
    _current_net_worth = st.session_state.get('net_worth_excl_re')
    _current_pvd = st.session_state.get('pvd_value')

    if _current_net_worth is None or _current_pvd is None:
        st.warning(
            "⚠️ ยังไม่มีข้อมูล Net Worth ปัจจุบัน — กรุณาเปิดแท็บ \"🌐 ภาพรวมความมั่งคั่ง\" → "
            "\"ภาพรวม Net Worth & สัดส่วนสินทรัพย์\" สักครั้งก่อน (ระบบจะดึงมาให้อัตโนมัติ) แล้วค่อยกลับมาที่นี่"
        )
        return

    _pvd_last_value, _pvd_cagr, _pvd_years_span = _fetch_pvd_history_and_cagr(get_active_sheet_name())

    st.info(
        f"💰 Net Worth ปัจจุบัน (ไม่รวมอสังหาฯ, รวม PVD แล้ว): **{_current_net_worth:,.0f} ฿** "
        f"(ในนี้เป็น PVD **{_current_pvd:,.0f} ฿**) — ดึงมาจากแท็บภาพรวม Net Worth อัตโนมัติ"
    )

    # 🆕 อายุปัจจุบัน คำนวณจากปีเกิดอัตโนมัติ (ปีปัจจุบัน - ปีเกิด) แทนตัวเลขตายตัว จะได้ถูกต้อง
    # เสมอทุกปีโดยไม่ต้องแก้เอง — ค่าเริ่มต้นปีเกิด 1980 (อายุ 46 ปี ณ ปี 2026)
    _default_birth_year = 1980
    _default_current_age = date.today().year - _default_birth_year

    with st.form("retirement_calc_form"):
        st.markdown("#### 📝 ข้อมูลพื้นฐาน")
        c1, c2 = st.columns(2)
        with c1:
            birth_year = st.number_input(
                "ปีเกิด (ค.ศ.)", min_value=1930, max_value=date.today().year - 18,
                value=_default_birth_year, step=1,
                help="ระบบจะคำนวณอายุปัจจุบันให้อัตโนมัติจากปีนี้ ถูกต้องเสมอทุกปีโดยไม่ต้องแก้เอง"
            )
            current_age = date.today().year - birth_year
            st.caption(f"🎂 อายุปัจจุบัน: **{current_age} ปี** (คำนวณจากปีเกิดอัตโนมัติ)")

            target_net_worth = st.number_input(
                "เป้าหมาย Net Worth ตอนเกษียณ (บาท)", min_value=0.0, value=20000000.0, step=100000.0, format="%.0f"
            )
        with c2:
            retirement_age = st.number_input("อายุที่ต้องการเกษียณ", min_value=18, max_value=90, value=55, step=1)
            monthly_expense_after = st.number_input(
                "ค่าใช้จ่ายต่อเดือนที่คาดหวังหลังเกษียณ (บาท)", min_value=0.0, value=100000.0, step=1000.0, format="%.0f"
            )

        st.markdown("#### 📈 สมมติฐานอัตราผลตอบแทน")
        r1, r2 = st.columns(2)
        with r1:
            annual_return_pct = st.slider(
                "อัตราผลตอบแทนเฉลี่ยต่อปี — พอร์ตทั่วไป (%)", 0.0, 20.0, 7.0, step=0.5,
                help="ใช้กับ Net Worth ส่วนที่ไม่ใช่ PVD (หุ้น กองทุน ทองคำ ฯลฯ)"
            )
        with r2:
            # ใช้ CAGR จากข้อมูล PVD จริงย้อนหลังเป็นค่าเริ่มต้นของ slider แทนเลขสุ่มเดา
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
                "เงินออม/ลงทุนเพิ่มต่อเดือน (บาท, ไม่รวม PVD)", min_value=0.0, value=50000.0, step=1000.0, format="%.0f"
            )
        with s2:
            annual_savings_increase_pct = st.slider(
                "% อัตราเพิ่มเงินเก็บต่อปี (ทบต้น)", 0.0, 20.0, 3.0, step=0.5,
                help="เช่น ตั้ง 3% แปลว่าปีถัดไปออมเพิ่มขึ้นอีก 3% จากปีก่อน ทบต้นไปเรื่อยๆ จนถึงอายุเกษียณ"
            )

        submitted = st.form_submit_button("🧮 คำนวณ", use_container_width=True)

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

    # 🆕 เก็บผลลัพธ์ไว้ให้แท็บย่อย "Life After Retirement" ดึงไปใช้เป็นค่าเริ่มต้นได้เลย
    st.session_state['retirement_projected_wealth'] = projected_at_retirement
    st.session_state['retirement_age_selected'] = retirement_age

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

    st.info("💡 เงินก้อนที่คำนวณได้นี้ จะถูกส่งไปเป็นค่าเริ่มต้นในแท็บ **\"🌴 Life After Retirement\"** ให้อัตโนมัติ (แก้ไขเองที่นั่นได้)")


# =============================================================
# แท็บย่อยที่ 2: 🌴 Life After Retirement
# =============================================================
def _render_life_after_retirement_tab():
    st.markdown("### 🌴 Life After Retirement")
    st.markdown("วางแผนว่าจะเอาเงินก้อนหลังเกษียณไปแบ่งลงทุนยังไง ให้มีเงินใช้พอในแต่ละเดือน")

    _default_wealth = st.session_state.get('retirement_projected_wealth', 20000000.0)
    _default_retirement_age = st.session_state.get('retirement_age_selected', 55)

    total_wealth = st.number_input(
        "💰 เงินก้อนหลังเกษียณทั้งหมด (บาท)", min_value=0.0, value=float(_default_wealth),
        step=100000.0, format="%.0f",
        help="ดึงมาจากผลคำนวณในแท็บ \"ประเมินเงินเกษียณ\" อัตโนมัติ — แก้ไขเป็นตัวเลขอื่นเองได้เลย"
    )

    st.divider()
    concept_choice = st.radio(
        "เลือกแนวทางวางแผน:",
        ["🧩 Concept 1: กำหนดสัดส่วนลงทุนเอง", "🎯 Concept 2: ให้ระบบออกแบบให้"],
        horizontal=True, key="life_after_retirement_concept"
    )

    if concept_choice.startswith("🧩"):
        _render_concept1(total_wealth, _default_retirement_age)
    else:
        _render_concept2(total_wealth, _default_retirement_age)


def _render_concept1(total_wealth, retirement_age):
    """Concept 1: ผู้ใช้กำหนดสัดส่วนการลงทุนเอง แล้วระบบคำนวณเงินใช้ได้ต่อเดือนให้"""
    st.markdown("#### 🧩 Concept 1: กำหนดสัดส่วนการลงทุนเอง")
    st.caption("แบ่งเงินก้อนทั้งหมดไปลงทุนแต่ละประเภท (รวมกันควรเป็น 100%) แล้วดูว่าจะมีเงินใช้ต่อเดือนเท่าไหร่")

    # 🆕 จับคู่ slider แต่ละกลุ่มไว้ในกรอบสีจาง (st.container(border=True)) ให้เห็นชัดว่าอันไหน
    # คู่กับอันไหน (เช่น % หุ้น คู่กับ % ปันผลหุ้น) แทนที่จะปล่อยเรียงกันเฉยๆ แบบเดิม
    a1, a2 = st.columns(2)
    with a1:
        with st.container(border=True):
            cash_pct = st.slider("💵 % เงินสด (สภาพคล่อง ไม่ลงทุน)", 0, 100, 10, key="c1_cash_pct")
        with st.container(border=True):
            stock_pct = st.slider("📈 % หุ้น", 0, 100, 40, key="c1_stock_pct")
            stock_yield_pct = st.slider("　└ % ปันผลหุ้นเฉลี่ยต่อปี", 0.0, 15.0, 5.0, step=0.5, key="c1_stock_yield")
    with a2:
        # 🆕 slide bar อายุที่คาดว่าจะมีชีวิตอยู่ วางคู่กับ % เงินสด (อยู่ด้านขวาของมันพอดี)
        with st.container(border=True):
            death_age = st.slider(
                "🕊️ อายุที่คาดว่าจะมีชีวิตอยู่ถึง", min_value=retirement_age + 1, max_value=110,
                value=min(85, 110), step=1, key="c1_death_age",
                help="ใช้คำนวณว่าเงินจะพอใช้ไปตลอดกี่ปี ถ้าเลือกแตะเงินต้นด้วย"
            )
        with st.container(border=True):
            fund_pct = st.slider("🧺 % กองทุน", 0, 100, 30, key="c1_fund_pct")
            fund_yield_pct = st.slider("　└ % ผลตอบแทนกองทุนเฉลี่ยต่อปี", 0.0, 15.0, 4.0, step=0.5, key="c1_fund_yield")

    with st.container(border=True):
        other_pct = st.slider("🏦 % อื่นๆ (ตราสารหนี้ / REITs / ฝากประจำ ฯลฯ)", 0, 100, 20, key="c1_other_pct")
        other_yield_pct = st.slider("　└ % ผลตอบแทนอื่นๆ เฉลี่ยต่อปี", 0.0, 15.0, 3.0, step=0.5, key="c1_other_yield")

    total_pct = cash_pct + stock_pct + fund_pct + other_pct
    if total_pct != 100:
        st.warning(f"⚠️ ตอนนี้สัดส่วนรวมกันได้ {total_pct}% (ควรรวมกันให้ได้ 100% พอดี ลองปรับ slider ดูครับ)")

    cash_amount = total_wealth * cash_pct / 100
    stock_amount = total_wealth * stock_pct / 100
    fund_amount = total_wealth * fund_pct / 100
    other_amount = total_wealth * other_pct / 100

    monthly_income = (
        stock_amount * stock_yield_pct / 100
        + fund_amount * fund_yield_pct / 100
        + other_amount * other_yield_pct / 100
    ) / 12

    st.divider()
    st.markdown("##### 📊 ผลการแบ่งสัดส่วน")
    b1, b2, b3, b4 = st.columns(4)
    render_metric_card(b1, "เงินสด", f"{cash_amount:,.0f} ฿", icon="💵")
    render_metric_card(b2, "หุ้น", f"{stock_amount:,.0f} ฿", icon="📈")
    render_metric_card(b3, "กองทุน", f"{fund_amount:,.0f} ฿", icon="🧺")
    render_metric_card(b4, "อื่นๆ", f"{other_amount:,.0f} ฿", icon="🏦")

    render_metric_card(
        st, "✨ เงินใช้ได้จริงต่อเดือน (ไม่แตะเงินต้นเลย)", f"{monthly_income:,.0f} ฿/เดือน",
        icon="💰", caption="รวมปันผล/ผลตอบแทนจากหุ้น กองทุน และอื่นๆ (เงินสดไม่สร้างรายได้)"
    )

    # 🆕 การ์ดเพิ่มเติม: แบบแตะเงินต้น ถอนใช้จนกว่าจะตาย โดยยังเหลือเงิน 20% ก่อนตาย (ใช้สูตร
    # Annuity ที่มีมูลค่าคงเหลือปลายทาง) ใช้ผลตอบแทนถัวเฉลี่ยของทั้งพอร์ต (ไม่รวมเงินสดที่ไม่โต)
    # เป็นอัตราการเติบโตระหว่างถอนใช้ — ให้เห็นว่าถ้าใช้แบบเต็มที่ (ไม่ต้องเก็บเงินต้นไว้ทั้งหมด)
    # จะมีเงินใช้ต่อเดือนได้มากขึ้นแค่ไหน
    st.divider()
    st.markdown("##### 🎉 แบบใช้เงินเต็มที่ (แตะเงินต้น เหลือ 20% ก่อนตาย)")
    years_to_live = max(death_age - retirement_age, 0)
    blended_yield_all = (
        (stock_amount * stock_yield_pct + fund_amount * fund_yield_pct + other_amount * other_yield_pct)
        / total_wealth
    ) if total_wealth > 0 else 0.0

    if years_to_live <= 0:
        st.info("กรุณาตั้งอายุที่คาดว่าจะมีชีวิตอยู่ให้มากกว่าอายุเกษียณก่อนครับ")
    else:
        max_monthly_spend = _max_monthly_withdrawal_with_residual(
            total_wealth, years_to_live, blended_yield_all, residual_pct=0.20
        )
        render_metric_card(
            st, f"💸 เงินใช้ได้เต็มที่ต่อเดือน (แตะเงินต้น, ใช้ {years_to_live} ปี)",
            f"{max_monthly_spend:,.0f} ฿/เดือน", icon="🥳",
            caption=f"คำนวณให้เหลือเงิน 20% ของเงินต้น ({total_wealth * 0.20:,.0f} ฿) ไว้ตอนอายุ {death_age} ปีพอดี"
        )


def _render_concept2(total_wealth, default_retirement_age):
    """Concept 2: ผู้ใช้กำหนดเงินที่อยากใช้ต่อเดือน แล้วระบบคำนวณย้อนกลับว่าต้องมีเงินก้อน/แบ่งสัดส่วนยังไง"""
    st.markdown("#### 🎯 Concept 2: ให้ระบบออกแบบให้")
    st.caption("บอกว่าอยากมีเงินใช้ต่อเดือนเท่าไหร่ ระบบจะคำนวณย้อนกลับให้ว่าต้องมีเงินก้อนเท่าไหร่ และควรแบ่งสัดส่วนลงทุนยังไง")

    target_income = st.number_input(
        "💭 อยากมีเงินใช้ต่อเดือนเท่าไหร่ (บาท)", min_value=0.0, value=100000.0, step=5000.0, format="%.0f"
    )

    st.markdown("##### ⚙️ สมมติฐาน")
    # 🆕 จับคู่ slider ไว้ในกรอบสีจางเหมือน Concept 1 + เพิ่ม slide bar อายุที่จะตาย คู่กับ
    # เงินสดสำรอง (ใช้คำนวณผลลัพธ์แบบแตะเงินต้น 4% ด้านล่าง)
    e1, e2 = st.columns(2)
    with e1:
        with st.container(border=True):
            cash_buffer_pct = st.slider(
                "💵 % เงินสดสำรอง (กันไว้ ไม่เอาไปลงทุน)", 0, 50, 10, key="c2_cash_buffer_pct"
            )
    with e2:
        with st.container(border=True):
            death_age = st.slider(
                "🕊️ อายุที่คาดว่าจะมีชีวิตอยู่ถึง", min_value=default_retirement_age + 1, max_value=110,
                value=min(85, 110), step=1, key="c2_death_age",
                help="ใช้คำนวณผลลัพธ์แบบแตะเงินต้น 4% ด้านล่าง"
            )

    st.caption("สัดส่วนของเงินที่ **นำไปลงทุนจริง** (ไม่รวมเงินสดสำรอง) แบ่งเป็น 3 ประเภท ปรับได้ตามต้องการ")
    f1, f2, f3 = st.columns(3)
    with f1:
        with st.container(border=True):
            invest_stock_pct = st.slider("📈 % หุ้น (ของเงินลงทุน)", 0, 100, 50, key="c2_invest_stock_pct")
            stock_yield_pct2 = st.slider("% ปันผลหุ้น/ปี", 0.0, 15.0, 5.0, step=0.5, key="c2_stock_yield")
    with f2:
        with st.container(border=True):
            invest_fund_pct = st.slider("🧺 % กองทุน (ของเงินลงทุน)", 0, 100, 30, key="c2_invest_fund_pct")
            fund_yield_pct2 = st.slider("% ผลตอบแทนกองทุน/ปี", 0.0, 15.0, 4.0, step=0.5, key="c2_fund_yield")
    with f3:
        with st.container(border=True):
            invest_other_pct = max(100 - invest_stock_pct - invest_fund_pct, 0)
            st.metric("🏦 % อื่นๆ (ส่วนที่เหลือ)", f"{invest_other_pct}%")
            other_yield_pct2 = st.slider("% ผลตอบแทนอื่นๆ/ปี", 0.0, 15.0, 3.0, step=0.5, key="c2_other_yield")

    if invest_stock_pct + invest_fund_pct > 100:
        st.warning("⚠️ % หุ้น + % กองทุน รวมกันเกิน 100% แล้วครับ ลองปรับลดลงหน่อย")

    blended_yield_pct = (
        invest_stock_pct * stock_yield_pct2
        + invest_fund_pct * fund_yield_pct2
        + invest_other_pct * other_yield_pct2
    ) / 100

    st.divider()
    st.markdown("##### 📐 ผลการออกแบบ (แบบที่ 1: ไม่แตะเงินต้นเลย)")
    st.caption("ใช้แค่ปันผล/ผลตอบแทนที่ได้จากเงินลงทุน เงินต้นทั้งหมดยังอยู่ครบตลอดไป")

    if blended_yield_pct <= 0:
        st.error("อัตราผลตอบแทนเฉลี่ยรวมเป็น 0% ครับ กรุณาปรับสัดส่วน/อัตราผลตอบแทนก่อน")
        return

    required_invested_amount = (target_income * 12) / (blended_yield_pct / 100)
    required_total_wealth = (
        required_invested_amount / (1 - cash_buffer_pct / 100) if cash_buffer_pct < 100 else float('inf')
    )

    required_cash = required_total_wealth * cash_buffer_pct / 100
    required_stock = required_invested_amount * invest_stock_pct / 100
    required_fund = required_invested_amount * invest_fund_pct / 100
    required_other = required_invested_amount * invest_other_pct / 100

    g1, g2, g3, g4 = st.columns(4)
    render_metric_card(g1, "เงินสดสำรอง", f"{required_cash:,.0f} ฿", icon="💵")
    render_metric_card(g2, "หุ้น", f"{required_stock:,.0f} ฿", icon="📈")
    render_metric_card(g3, "กองทุน", f"{required_fund:,.0f} ฿", icon="🧺")
    render_metric_card(g4, "อื่นๆ", f"{required_other:,.0f} ฿", icon="🏦")

    render_metric_card(
        st, "🎯 เงินก้อนที่ต้องมีทั้งหมด (ไม่แตะเงินต้น)", f"{required_total_wealth:,.0f} ฿",
        icon="💰", caption=f"อัตราผลตอบแทนเฉลี่ยรวม {blended_yield_pct:.2f}%/ปี ตามสัดส่วนที่เลือก"
    )

    st.divider()
    diff = total_wealth - required_total_wealth
    if diff >= 0:
        st.success(
            f"🎉 เงินก้อนที่คาดว่าจะมี ({total_wealth:,.0f} ฿) **เพียงพอ** กับที่ต้องใช้ "
            f"({required_total_wealth:,.0f} ฿) แล้วครับ! เหลือเผื่ออีก {diff:,.0f} ฿"
        )
    else:
        st.warning(
            f"⚠️ เงินก้อนที่คาดว่าจะมี ({total_wealth:,.0f} ฿) ยังไม่พอกับที่ต้องใช้ตามแผนนี้ "
            f"({required_total_wealth:,.0f} ฿) — ขาดอยู่ {abs(diff):,.0f} ฿ ลองปรับสัดส่วน/อัตราผลตอบแทน "
            f"หรือลดเงินที่อยากใช้ต่อเดือนดูครับ"
        )

    # 🆕 ผลการออกแบบ แบบที่ 2: แตะเงินต้น 4% (ใช้สูตรมาตรฐานสากล Safe Withdrawal Rate 4%)
    # ต้องการเงินก้อนน้อยกว่าแบบไม่แตะเงินต้นเสมอ เพราะยอมให้เงินต้นค่อยๆ ลดลงไปตามเวลาได้บ้าง
    st.divider()
    st.markdown("##### 📐 ผลการออกแบบ (แบบที่ 2: แตะเงินต้น 4% ตามกฎมาตรฐานสากล)")
    st.caption("ยอมให้ถอนเงินต้นออกมาใช้ด้วย 4% ของเงินก้อนต่อปี (กฎ Safe Withdrawal Rate ที่ใช้กันแพร่หลาย) ต้องการเงินก้อนน้อยกว่าแบบแรก")

    required_total_wealth_4pct = (target_income * 12) / 0.04

    h1, h2 = st.columns(2)
    render_metric_card(
        h1, "🎯 เงินก้อนที่ต้องมีทั้งหมด (แตะเงินต้น 4%)", f"{required_total_wealth_4pct:,.0f} ฿",
        icon="💸", caption="คำนวณจากกฎ 4% มาตรฐาน (เงินที่ต้องใช้ต่อปี ÷ 4%)"
    )
    _diff_4pct = total_wealth - required_total_wealth_4pct
    render_metric_card(
        h2, "เทียบกับเงินก้อนที่คาดว่าจะมี", f"{abs(_diff_4pct):,.0f} ฿",
        icon="✅" if _diff_4pct >= 0 else "⚠️",
        delta="เหลือเผื่อ" if _diff_4pct >= 0 else "ยังขาดอยู่", delta_positive=(_diff_4pct >= 0)
    )

    # เช็คว่าเงินก้อนที่มีจริง (ตามแบบที่ 2) จะพอใช้ไปถึงอายุที่ตั้งไว้ไหม โดยใช้สูตรถอนแบบไล่ลำดับ
    # เดียวกับที่ใช้ใน Concept 1 (ให้เหลือ 0% ก็ได้ในกรณีนี้ เพราะกฎ 4% ออกแบบมาให้ใช้เกือบหมดพอดี)
    years_available = max(death_age - default_retirement_age, 0)
    if years_available > 0 and total_wealth > 0:
        _actual_years_last = _years_money_lasts(total_wealth, target_income, 4.0)
        if _actual_years_last >= years_available or _actual_years_last >= 100:
            st.success(
                f"🎉 ด้วยเงินก้อนที่คาดว่าจะมีจริง ({total_wealth:,.0f} ฿) ถอนใช้ {target_income:,.0f} ฿/เดือน "
                f"ที่ผลตอบแทน 4%/ปี จะอยู่ได้เกินอายุ {death_age} ปีที่ตั้งไว้แน่นอนครับ"
            )
        else:
            _end_age = default_retirement_age + _actual_years_last
            st.warning(
                f"⚠️ ด้วยเงินก้อนที่คาดว่าจะมีจริง ({total_wealth:,.0f} ฿) ถอนใช้ {target_income:,.0f} ฿/เดือน "
                f"ที่ผลตอบแทน 4%/ปี จะอยู่ได้ถึงอายุประมาณ {_end_age:,.0f} ปีเท่านั้น (ก่อนอายุ {death_age} ปีที่ตั้งไว้)"
            )


# =============================================================
# ฟังก์ชันหลัก — รวม 2 แท็บย่อยเข้าด้วยกัน
# =============================================================
def render_tab_retirement():
    sub_tab_assessment, sub_tab_life_after = st.tabs([
        "📊 ประเมินเงินเกษียณ", "🌴 Life After Retirement"
    ])

    with sub_tab_assessment:
        _render_assessment_tab()

    with sub_tab_life_after:
        _render_life_after_retirement_tab()
