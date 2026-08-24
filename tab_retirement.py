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


def _fetch_current_pvd_value():
    """ดึงมูลค่า PVD ล่าสุด (แถวสุดท้าย) จากชีต Provident_Fund มาเป็นฐานตั้งต้นให้อัตโนมัติ"""
    try:
        client = get_gsheet_client()
        sheet_pvd = get_worksheet_safely(client, get_active_sheet_name(), 'Provident_Fund')
        if sheet_pvd is None:
            return 0.0
        records = sheet_pvd.get_all_records()
        if not records:
            return 0.0
        last_row = records[-1]
        raw_pvd = last_row.get('Grand_Total', last_row.get('Value', 0))
        return float(str(raw_pvd).replace(',', '')) if str(raw_pvd).strip() != "" else 0.0
    except Exception:
        return 0.0


def _project_growth(current_age, retirement_age, other_current, pvd_current,
                     monthly_savings, annual_return_pct, pvd_annual_growth_pct):
    """
    คำนวณโปรเจกชัน Net Worth รายปี (แยกเติบโต PVD กับพอร์ตทั่วไปคนละอัตรา แล้วรวมกันแสดงผล)
    คืนค่าเป็น (list ของอายุแต่ละปี, list ของ Net Worth รวมแต่ละปี, Net Worth รวม ณ ปีเกษียณ)
    """
    years_to_go = max(retirement_age - current_age, 0)
    ages = [current_age]
    totals = [other_current + pvd_current]

    _other = other_current
    _pvd = pvd_current
    for _ in range(years_to_go):
        _other = _other * (1 + annual_return_pct / 100) + monthly_savings * 12
        _pvd = _pvd * (1 + pvd_annual_growth_pct / 100)
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

    _current_pvd = _fetch_current_pvd_value()

    with st.form("retirement_calc_form"):
        st.markdown("#### 📝 ข้อมูลพื้นฐาน")
        c1, c2 = st.columns(2)
        with c1:
            current_age = st.number_input("อายุปัจจุบัน", min_value=18, max_value=90, value=35, step=1)
            target_net_worth = st.number_input(
                "เป้าหมาย Net Worth ตอนเกษียณ (บาท)", min_value=0.0, value=20000000.0, step=100000.0, format="%.0f"
            )
            current_net_worth = st.number_input(
                "Net Worth ปัจจุบันทั้งหมด (บาท)", min_value=0.0, value=0.0, step=100000.0, format="%.0f",
                help="ดูตัวเลขนี้ได้จากแท็บ \"ภาพรวม Net Worth & สัดส่วนสินทรัพย์\" (การ์ด Net Worth รวมทั้งหมด)"
            )
        with c2:
            retirement_age = st.number_input("อายุที่ต้องการเกษียณ", min_value=18, max_value=90, value=50, step=1)
            monthly_expense_after = st.number_input(
                "ค่าใช้จ่ายต่อเดือนที่คาดหวังหลังเกษียณ (บาท)", min_value=0.0, value=50000.0, step=1000.0, format="%.0f"
            )
            st.metric("💼 มูลค่า PVD ปัจจุบัน (ดึงอัตโนมัติ)", f"{_current_pvd:,.0f} ฿")

        st.markdown("#### 📈 สมมติฐานอัตราผลตอบแทน")
        r1, r2 = st.columns(2)
        with r1:
            annual_return_pct = st.slider(
                "อัตราผลตอบแทนเฉลี่ยต่อปี — พอร์ตทั่วไป (%)", 0.0, 20.0, 7.0, step=0.5,
                help="ใช้กับ Net Worth ส่วนที่ไม่ใช่ PVD (หุ้น กองทุน ทองคำ ฯลฯ)"
            )
        with r2:
            pvd_annual_growth_pct = st.slider(
                "อัตราการเติบโตต่อปี — PVD (%)", 0.0, 20.0, 6.0, step=0.5,
                help="แยกต่างหากจากพอร์ตทั่วไป เพราะ PVD มักมีเงินสมทบจากนายจ้าง+เงื่อนไขต่างกัน"
            )

        monthly_savings = st.number_input(
            "เงินออม/ลงทุนเพิ่มต่อเดือน (บาท, ไม่รวม PVD)", min_value=0.0, value=20000.0, step=1000.0, format="%.0f"
        )

        submitted = st.form_submit_button("🧮 คำนวณ", use_container_width=True)

    if not submitted:
        return

    if retirement_age <= current_age:
        st.error("อายุที่ต้องการเกษียณต้องมากกว่าอายุปัจจุบันครับ")
        return

    years_to_go = retirement_age - current_age
    other_current = max(current_net_worth - _current_pvd, 0.0)

    ages, totals, projected_at_retirement = _project_growth(
        current_age, retirement_age, other_current, _current_pvd,
        monthly_savings, annual_return_pct, pvd_annual_growth_pct
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
            f"**{_extra_monthly:,.0f} ฿/เดือน** (รวมเป็น {monthly_savings + _extra_monthly:,.0f} ฿/เดือน)"
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

    # เช็คความยั่งยืนหลังเกษียณ
    st.divider()
    st.markdown("#### 🏖️ เช็คความยั่งยืนของเงินหลังเกษียณ")
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
