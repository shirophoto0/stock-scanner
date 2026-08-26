# =============================================================
# tab_gold.py
# แท็บจัดการพอร์ตทองคำ (Phase 2 ของการแยกไฟล์)
# =============================================================
import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
from backend_functions import get_worksheet_safely, get_active_sheet_name, fetch_live_gold_price
from theme import render_metric_card


def render_tab_gold(client):
    st.markdown("### 🟡 จัดการพอร์ตการลงทุนทองคำ")
    st.markdown("เลือกประเภทการลงทุน: ทองคำแท่ง/ทองรูปพรรณ หรือ เทรดทอง/กองทุนทอง (ระบบดึงข้อมูลแบบ Web Scraping สดจากเว็บอ้างอิง)")

    from datetime import datetime, timedelta

    # 🔧 แก้บั๊ก: เดิมฟังก์ชันนี้ดึงราคาจาก www.goldtraders.or.th ไม่สำเร็จเลยสักครั้ง เพราะเว็บ
    # ย้ายไปเป็น React App ที่โหลดราคาผ่าน JavaScript หลังโหลดหน้าเสร็จ (ราคาไม่ได้ฝังมาใน HTML
    # ตอนโหลดครั้งแรก) ทำให้ตกไปใช้ราคาสำรอง (68,300/69,100) ตลอดเวลา ไม่เคยอัปเดตจริงเลย ตอนนี้
    # เปลี่ยนไปเรียกใช้ fetch_live_gold_price() ฟังก์ชันกลางใน backend_functions.py ที่แก้ไปแล้ว
    # (ดึงจากเว็บ classic.goldtraders.or.th ซึ่งยังเป็น HTML แบบดั้งเดิม + ค้นหาด้วย Regex ที่
    # ทนทานกว่าเดิม) ใช้ร่วมกับฟังก์ชันคำนวณ Net Worth สดในรายงานอัตโนมัติรายเดือนด้วย
    def get_gold_price_by_scraping():
        # ตรวจสอบ Cache ใน Session ไม่ให้ยิงถี่เกินไป (ภายใน 3 ชม.)
        # 🔧 กันเผื่อเพิ่ม: ถ้าค่าที่แคชไว้ดันตรงกับราคาสำรอง (Fallback) เป๊ะๆ (68,300 หรือ 69,100)
        # ถือว่าน่าสงสัยว่าอาจเป็นค่าค้างจากตอนที่ดึงสดไม่สำเร็จมาก่อนหน้านี้ ให้ข้ามแคชแล้วลองดึง
        # สดใหม่ทันที แทนที่จะเชื่อค่าที่แคชไว้ตรงๆ
        if 'scraped_gold_date' in st.session_state:
            last_update = st.session_state['scraped_gold_date']
            _cached_bar = st.session_state.get('scraped_gold_bar')
            _cached_jewelry = st.session_state.get('scraped_gold_jewelry')
            _looks_like_stale_fallback = _cached_bar == 68300.0 or _cached_jewelry == 69100.0
            if (
                isinstance(last_update, datetime) and (datetime.now() - last_update) < timedelta(hours=3)
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

        # Fallback: ถ้า Scrape ไม่สำเร็จ ดึงค่าเดิมมาใช้ หรือใช้ค่าสำรองปัจจุบัน
        # 🔧 แก้บั๊ก: เดิมโชว์แค่ข้อความทั่วไป ไม่บอกสาเหตุจริง ตอนนี้แนบข้อความ debug_msg ที่ได้
        # จาก fetch_live_gold_price() มาแสดงต่อท้ายด้วยเลย เห็นสาเหตุจริงตรงในหน้าเว็บทันที
        st.session_state['gold_price_status'] = f"⚠️ ดึงราคาสดไม่สำเร็จ (สาเหตุ: {debug_msg}) กำลังใช้ราคาสำรอง/ราคาเก่าที่มีอยู่แทน"
        fallback_bar = st.session_state.get('scraped_gold_bar', 68300.0)
        fallback_jewelry = st.session_state.get('scraped_gold_jewelry', 69100.0)
        return fallback_bar, fallback_jewelry

    # 🆕 ปุ่มบังคับรีเฟรชราคาทองทันที (เคลียร์แคชแล้วดึงสดใหม่) ใช้ทดสอบ/วินิจฉัยปัญหาได้ตรงจุด
    # โดยไม่ต้องพึ่งการเช็ค log ฝั่งเซิร์ฟเวอร์ เพราะเห็นผลตรงในหน้าเว็บทันที
    _refresh_col1, _refresh_col2 = st.columns([3, 1])
    with _refresh_col2:
        if st.button("🔄 รีเฟรชราคาทองคำ", use_container_width=True):
            for _k in ['scraped_gold_date', 'scraped_gold_bar', 'scraped_gold_jewelry', 'gold_price_status']:
                st.session_state.pop(_k, None)
            st.rerun()

    # เรียกใช้งานฟังก์ชัน Scraping
    ref_gold_bar, ref_gold_jewelry = get_gold_price_by_scraping()

    # 🆕 แสดงสถานะจริงของการดึงราคาไว้ให้เห็นตรงในหน้าเว็บ (แทนการต้องเช็ค log ฝั่งเซิร์ฟเวอร์
    # ซึ่งบางครั้งอาจไม่แสดงผลตามที่คาดไว้) เห็นผลได้ทันทีว่าดึงสดสำเร็จหรือใช้ราคาสำรองอยู่
    with _refresh_col1:
        _status_msg = st.session_state.get('gold_price_status', "✅ ดึงราคาสดสำเร็จล่าสุด")
        if "⚠️" in _status_msg:
            st.warning(_status_msg)
        else:
            st.success(_status_msg)


    # แสดงผลราคาอ้างอิง
    # 🔧 ปรับปรุง: จัดเป็นตาราง 2x3 (2 แถว x 3 คอลัมน์) ให้กล่องขนาดเท่ากันทั้งหมด
    # แถวแรกใส่ราคาทอง 2 กล่อง จัดกึ่งกลางด้วยการเว้นช่องว่างครึ่งหนึ่งไว้ทั้งซ้าย-ขวา
    # (สัดส่วน 0.5:1:1:0.5 ทำให้การ์ดตรงกลางกว้างเท่ากับ 1 ใน 3 ส่วน พอดีกับการ์ดในแถว 2)
    # แถวสองจอง "ที่ว่าง" ไว้ล่วงหน้าสำหรับการ์ดสรุปยอดพอร์ต 3 อัน (ที่จริงๆ คำนวณได้ทีหลังมาก
    # หลังประมวลผลตารางพอร์ตเสร็จแล้ว แต่อยากให้แสดงตำแหน่งนี้ จึงใช้ placeholder จองที่ไว้ก่อน)
    _sp1, row1_col1, row1_col2, _sp2 = st.columns([0.5, 1, 1, 0.5])
    render_metric_card(row1_col1, "ราคาทองคำแท่ง (Scraped)", f"{ref_gold_bar:,.2f} ฿ / บาททอง", icon="📌")
    render_metric_card(row1_col2, "ราคาทองรูปพรรณ (Scraped)", f"{ref_gold_jewelry:,.2f} ฿ / บาททอง", icon="📌")

    row2_col1, row2_col2, row2_col3 = st.columns(3)
    gold_summary_placeholder_1 = row2_col1.empty()
    gold_summary_placeholder_2 = row2_col2.empty()
    gold_summary_placeholder_3 = row2_col3.empty()
    st.markdown("---")

    # 🔄 โหลดข้อมูลจาก Google Sheets และคำนวณพอร์ตทองคำต่อ
    if 'gold_portfolio' not in st.session_state:
        st.session_state['gold_portfolio'] = []
        try:
            sheet_gold = get_worksheet_safely(client, get_active_sheet_name(), 'Gold_Portfolio')
            if sheet_gold is not None:
                records = sheet_gold.get_all_records()
                for row in records:
                    g_type = str(row.get("ประเภท", "")).strip()
                    if g_type != "":
                        raw_weight = row.get("น้ำหนัก/มูลค่าซื้อ", row.get("น้ำหนัก", 0))
                        val_weight = float(str(raw_weight).replace(',', '')) if raw_weight else 0.0
                        unit_str = str(row.get("หน่วย", ""))
                        cost_avg = float(str(row.get("ราคาต้นทุนเฉลี่ย", 0)).replace(',', '')) if row.get("ราคาต้นทุนเฉลี่ย") else 0.0
                        cost_val = float(str(row.get("มูลค่าตั้งต้น", 0)).replace(',', '')) if row.get("มูลค่าตั้งต้น") else 0.0
                        market_price = float(str(row.get("ราคาตลาดปัจจุบัน", 0)).replace(',', '')) if row.get("ราคาตลาดปัจจุบัน") else 0.0
                        market_val = float(str(row.get("มูลค่าตลาด", 0)).replace(',', '')) if row.get("มูลค่าตลาด") else 0.0
                        note_str = str(row.get("หมายเหตุ", ""))

                        if g_type == "ทองคำแท่ง":
                            if market_price == 0: market_price = ref_gold_bar
                            if market_val == 0 and val_weight > 0: market_val = (val_weight / 15.244) * ref_gold_bar
                            if cost_val == 0: cost_val = market_val  
                            if cost_avg == 0: cost_avg = ref_gold_bar

                        elif g_type == "ทองรูปพรรณ":
                            if market_price == 0: market_price = ref_gold_jewelry
                            if market_val == 0 and val_weight > 0: market_val = val_weight * ref_gold_jewelry
                            if cost_val == 0: cost_val = market_val
                            if cost_avg == 0: cost_avg = ref_gold_jewelry

                        else:  
                            if cost_val == 0: cost_val = val_weight
                            if market_val == 0: market_val = cost_val
                            if market_price == 0: market_price = market_val

                        st.session_state['gold_portfolio'].append({
                            "ประเภท": g_type,
                            "น้ำหนัก/มูลค่าซื้อ": val_weight,
                            "หน่วย": unit_str,
                            "ราคาต้นทุนเฉลี่ย": cost_avg,
                            "มูลค่าตั้งต้น": cost_val,
                            "ราคาตลาดปัจจุบัน": market_price,
                            "มูลค่าตลาด": market_val,
                            "หมายเหตุ": note_str
                        })
        except Exception as e:
            st.error(f"⚠️ โหลดข้อมูลพอร์ตทองคำไม่สำเร็จ: {e}")

    st.markdown("#### 📝 บันทึกข้อมูลการถือครองทองคำ")

    gold_type = st.selectbox(
        "ประเภททองคำ / การลงทุน", 
        ["ทองคำแท่ง", "ทองรูปพรรณ", "เทรดทอง / กองทุนทอง"],
        key="form_gold_type_select"
    )

    with st.form("gold_investment_form"):
        col_f1, col_f2 = st.columns(2)

        with col_f1:
            if gold_type == "ทองคำแท่ง":
                weight_input = st.number_input("น้ำหนัก (กรัม)", min_value=0.0, step=1.0, value=0.0, key="weight_gram")
            elif gold_type == "ทองรูปพรรณ":
                weight_input = st.number_input("น้ำหนัก (บาททองคำ)", min_value=0.0, step=0.25, value=1.0, key="weight_baht")
            else:
                weight_input = st.number_input("👉 มูลค่าเงินทุนที่ซื้อเพิ่ม (บาท):", min_value=0.0, step=1000.0, value=0.0, help="หากซื้อเพิ่ม ให้กรอกจำนวนเงินที่ซื้อเพิ่ม ระบบจะนำไปบวกทบเข้ากับต้นทุนเดิมให้อัตโนมัติ", key="trade_cap_input")
                market_val_input = st.number_input("👉 มูลค่าตลาดปัจจุบัน (บาท) [อัปเดตรายเดือน]:", min_value=0.0, step=1000.0, value=0.0, help="กรอกมูลค่าตลาดล่าสุดจากการประเมินประจำเดือน", key="trade_market_input")

        with col_f2:
            note_input = st.text_input("หมายเหตุ / ชื่อกองทุน / สาขา", placeholder="เช่น กองทุนทองคำ T-GOLD, ฮั่วเซ่งเฮง", key="gold_note")

        submitted = st.form_submit_button("➕ บันทึก / เพิ่มรายการเข้าพอร์ต")

        if submitted:
            if 'gold_portfolio' not in st.session_state:
                st.session_state['gold_portfolio'] = []

            if gold_type != "เทรดทอง / กองทุนทอง" and weight_input > 0:
                if gold_type == "ทองคำแท่ง":
                    unit_name = "กรัม"
                    p_unit = ref_gold_bar
                    init_m_val = (weight_input / 15.244) * ref_gold_bar
                    cost_val = init_m_val 
                else:
                    unit_name = "บาททองคำ"
                    p_unit = ref_gold_jewelry
                    init_m_val = weight_input * ref_gold_jewelry
                    cost_val = init_m_val

                found = False
                for item in st.session_state['gold_portfolio']:
                    if item["ประเภท"] == gold_type and item["หมายเหตุ"] == note_input:
                        item["น้ำหนัก/มูลค่าซื้อ"] += weight_input
                        if gold_type == "ทองคำแท่ง":
                            item["มูลค่าตั้งต้น"] = (item["น้ำหนัก/มูลค่าซื้อ"] / 15.244) * ref_gold_bar
                            item["มูลค่าตลาด"] = item["มูลค่าตั้งต้น"]
                        else:
                            item["มูลค่าตั้งต้น"] = item["น้ำหนัก/มูลค่าซื้อ"] * ref_gold_jewelry
                            item["มูลค่าตลาด"] = item["มูลค่าตั้งต้น"]
                        found = True
                        break

                if not found:
                    st.session_state['gold_portfolio'].append({
                        "ประเภท": gold_type,
                        "น้ำหนัก/มูลค่าซื้อ": weight_input,
                        "หน่วย": unit_name,
                        "ราคาต้นทุนเฉลี่ย": p_unit,
                        "มูลค่าตั้งต้น": init_m_val,
                        "ราคาตลาดปัจจุบัน": p_unit,
                        "มูลค่าตลาด": init_m_val,
                        "หมายเหตุ": note_input
                    })

                # บันทึกลง Google Sheets
                try:
                    sheet_gold = get_worksheet_safely(client, get_active_sheet_name(), 'Gold_Portfolio')
                    if sheet_gold is not None:
                        sheet_gold.clear()
                        sheet_gold.append_row(["ประเภท", "น้ำหนัก/มูลค่าซื้อ", "หน่วย", "ราคาต้นทุนเฉลี่ย", "มูลค่าตั้งต้น", "ราคาตลาดปัจจุบัน", "มูลค่าตลาด", "หมายเหตุ", "วันที่บันทึก"])
                        current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        rows_to_append = []
                        for item in st.session_state['gold_portfolio']:
                            rows_to_append.append([
                                item["ประเภท"],
                                item["น้ำหนัก/มูลค่าซื้อ"],
                                item["หน่วย"],
                                item["ราคาต้นทุนเฉลี่ย"],
                                item["มูลค่าตั้งต้น"],
                                item["ราคาตลาดปัจจุบัน"],
                                item["มูลค่าตลาด"],
                                item["หมายเหตุ"],
                                current_date
                            ])
                        sheet_gold.append_rows(rows_to_append)
                except Exception as e:
                    st.error(f"⚠️ บันทึกลง Google Sheets ไม่สำเร็จ: {e}")

                st.success(f"บันทึกข้อมูล {gold_type} สำเร็จ!")
                st.rerun()

            elif gold_type == "เทรดทอง / กองทุนทอง":
                if weight_input > 0 or market_val_input > 0:
                    found = False
                    for item in st.session_state['gold_portfolio']:
                        if item["ประเภท"] == gold_type and item["หมายเหตุ"] == note_input:
                            item["น้ำหนัก/มูลค่าซื้อ"] += weight_input
                            item["มูลค่าตั้งต้น"] += weight_input
                            if market_val_input > 0:
                                item["มูลค่าตลาด"] = market_val_input
                            found = True
                            break

                    if not found:
                        m_final = market_val_input if market_val_input > 0 else weight_input
                        st.session_state['gold_portfolio'].append({
                            "ประเภท": gold_type,
                            "น้ำหนัก/มูลค่าซื้อ": weight_input,
                            "หน่วย": "บาท (THB)",
                            "ราคาต้นทุนเฉลี่ย": 1.0,
                            "มูลค่าตั้งต้น": weight_input,
                            "ราคาตลาดปัจจุบัน": m_final,
                            "มูลค่าตลาด": m_final,
                            "หมายเหตุ": note_input if note_input else "เทรดทองทั่วไป"
                        })

                        try:
                            sheet_gold = get_worksheet_safely(client, get_active_sheet_name(), 'Gold_Portfolio')
                            if sheet_gold is not None:
                                sheet_gold.clear()
                                sheet_gold.append_row(["ประเภท", "น้ำหนัก/มูลค่าซื้อ", "หน่วย", "ราคาต้นทุนเฉลี่ย", "มูลค่าตั้งต้น", "ราคาตลาดปัจจุบัน", "มูลค่าตลาด", "หมายเหตุ", "วันที่บันทึก"])
                                current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                rows_to_append = []
                                for item in st.session_state['gold_portfolio']:
                                    rows_to_append.append([
                                        item["ประเภท"],
                                        item["น้ำหนัก/มูลค่าซื้อ"],
                                        item["หน่วย"],
                                        item["ราคาต้นทุนเฉลี่ย"],
                                        item["มูลค่าตั้งต้น"],
                                        item["ราคาตลาดปัจจุบัน"],
                                        item["มูลค่าตลาด"],
                                        item["หมายเหตุ"],
                                        current_date
                                    ])
                                sheet_gold.append_rows(rows_to_append)
                        except Exception as e:
                            st.error(f"⚠️ บันทึกลง Google Sheets ไม่สำเร็จ: {e}")

                        st.success(f"บันทึกข้อมูลการเทรดทอง/กองทุนทองสำเร็จ!")
                        st.rerun()
                else:
                    st.error("กรุณากรอกข้อมูลให้มากกว่า 0")

    if 'gold_portfolio' in st.session_state and len(st.session_state['gold_portfolio']) > 0:
        st.markdown("#### 📊 สรุปมูลค่าพอร์ตการลงทุนทองคำทั้งหมด")

        df_gold = pd.DataFrame(st.session_state['gold_portfolio'])

        calculated_cost = []
        calculated_market = []
        profit_losses = []
        profit_loss_pcts = []

        for idx, row in df_gold.iterrows():
            g_type = row.get("ประเภท", "")
            weight_val = row.get("น้ำหนัก/มูลค่าซื้อ", row.get("น้ำหนัก", 0.0))

            try:
                weight_val = float(str(weight_val).replace(',', '').strip())
            except:
                weight_val = 0.0

            # ดึงต้นทุนตั้งต้นเดิม (ถ้ามี)
            c_val = row.get("มูลค่าตั้งต้น", 0.0)
            try:
                c_val = float(str(c_val).replace(',', '').strip())
            except:
                c_val = 0.0

            # ดึงราคาต้นทุนเฉลี่ย (กรณีใช้คำนวณกลับ)
            cost_avg_val = row.get("ราคาต้นทุนเฉลี่ย", 0.0)
            try:
                cost_avg_val = float(str(cost_avg_val).replace(',', '').strip())
            except:
                cost_avg_val = 0.0

            # 1. คำนวณ "มูลค่าตลาดปัจจุบัน" ตามเรทราคาอ้างอิงล่าสุด
            if g_type == "ทองคำแท่ง":
                market_val = (weight_val / 15.244) * ref_gold_bar
            elif g_type == "ทองรูปพรรณ":
                market_val = weight_val * ref_gold_jewelry
            else:
                m_val = row.get("มูลค่าตลาด", 0.0)
                try:
                    m_val = float(str(m_val).replace(',', '').strip())
                except:
                    m_val = 0.0
                market_val = m_val if m_val > 0 else weight_val

            # 2. กำหนด "มูลค่าตั้งต้น" ให้คงที่ (ไม่เปลี่ยนตามราคาตลาด)
            if c_val > 0:
                cost_val = c_val
            elif cost_avg_val > 0:
                # คำนวณต้นทุนจากราคาเฉลี่ยต่อบาททอง
                if g_type == "ทองคำแท่ง":
                    cost_val = (weight_val / 15.244) * cost_avg_val
                elif g_type == "ทองรูปพรรณ":
                    cost_val = weight_val * cost_avg_val
                else:
                    cost_val = weight_val
            else:
                # ถ้าไม่มีต้นทุนเลยจริงๆ ให้ใช้มูลค่าตลาดตอนนั้นเป็นฐานไว้ครั้งแรกครั้งเดียว
                cost_val = market_val

            # 3. คำนวณกำไร/ขาดทุน
            p_l = market_val - cost_val
            p_l_pct = (p_l / cost_val * 100) if cost_val > 0 else 0.0

            calculated_cost.append(cost_val)
            calculated_market.append(market_val)
            profit_losses.append(p_l)
            profit_loss_pcts.append(p_l_pct)

        df_gold["มูลค่าตั้งต้น"] = calculated_cost
        df_gold["มูลค่าตลาด"] = calculated_market
        df_gold["กำไร/ขาดทุน (บาท)"] = profit_losses
        df_gold["% กำไร/ขาดทุน"] = profit_loss_pcts

        # เพิ่มคอลัมน์สำหรับลบ
        df_gold.insert(0, "ลบ", False)

        display_columns = ["ลบ", "ประเภท", "น้ำหนัก/มูลค่าซื้อ", "หน่วย", "มูลค่าตั้งต้น", "มูลค่าตลาด", "กำไร/ขาดทุน (บาท)", "% กำไร/ขาดทุน", "หมายเหตุ"]
        df_display = df_gold[[col for col in display_columns if col in df_gold.columns]]

        edited_df = st.data_editor(
            df_display,
            column_config={
                "ลบ": st.column_config.CheckboxColumn("🗑️ ลบ", help="ติ๊กเพื่อเลือกรายการที่ต้องการลบ", default=False),
                "น้ำหนัก/มูลค่าซื้อ": st.column_config.NumberColumn("น้ำหนัก/มูลค่าซื้อ", format="%.2f"),
                "มูลค่าตั้งต้น": st.column_config.NumberColumn(format="%.2f", disabled=True),
                "มูลค่าตลาด": st.column_config.NumberColumn(format="%.2f", disabled=True),
                "กำไร/ขาดทุน (บาท)": st.column_config.NumberColumn(format="%.2f", disabled=True),
                "% กำไร/ขาดทุน": st.column_config.NumberColumn(format="%.2f%%", disabled=True),
            },
            disabled=[col for col in df_display.columns if col != "ลบ"],
            hide_index=True,
            use_container_width=True
        )

        st.markdown("---")
        total_market_value = sum(calculated_market)
        total_cost_value = sum(calculated_cost)
        total_pl = sum(profit_losses)
        total_pl_pct = (total_pl / total_cost_value * 100) if total_cost_value > 0 else 0.0

        st.session_state['total_gold_portfolio_value'] = total_market_value

        # 🔧 ปรับปรุง: เติมเนื้อหาลงใน placeholder ที่จองที่ไว้แล้วตั้งแต่แถวบนสุด (ใต้การ์ด
        # ราคาทองคำแท่ง/ทองรูปพรรณ) แทนที่จะวาดการ์ดใหม่ตรงนี้ ตำแหน่งที่เห็นจริงบนจอจะอยู่
        # แถว 2 ต่อจากราคาทองทันที ตามที่ขอ ถึงแม้โค้ดคำนวณจะอยู่ตรงนี้ก็ตาม
        render_metric_card(gold_summary_placeholder_1, "มูลค่าตลาดพอร์ตทองรวม", f"{total_market_value:,.2f} ฿", icon="💰")
        render_metric_card(gold_summary_placeholder_2, "มูลค่าตั้งต้นรวม", f"{total_cost_value:,.2f} ฿", icon="📦")
        render_metric_card(gold_summary_placeholder_3, "กำไร/ขาดทุนรวม", f"{total_pl:,.2f} ฿", icon="📈",
                            delta=f"{total_pl_pct:,.2f}%", delta_positive=(total_pl >= 0))

        if st.button("🗑️ ล้างข้อมูลพอร์ตทองคำทั้งหมด"):
            st.session_state['gold_portfolio'] = []
            st.session_state['total_gold_portfolio_value'] = 0.0
            try:
                sheet_gold = get_worksheet_safely(client, get_active_sheet_name(), 'Gold_Portfolio')
                if sheet_gold is not None:
                    sheet_gold.clear()
                    sheet_gold.append_row(["ประเภท", "น้ำหนัก/มูลค่าซื้อ", "หน่วย", "ราคาต้นทุนเฉลี่ย", "มูลค่าตั้งต้น", "ราคาตลาดปัจจุบัน", "มูลค่าตลาด", "หมายเหตุ", "วันที่บันทึก"])
            except:
                pass
            st.rerun()
    else:
        st.info("ยังไม่มีข้อมูลในพอร์ตทองคำ กรุณากรอกฟอร์มด้านบนเพื่อเพิ่มรายการ")
