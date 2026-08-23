# =============================================================
# tab_gold.py
# แท็บจัดการพอร์ตทองคำ (Phase 2 ของการแยกไฟล์)
# =============================================================
import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
from backend_functions import get_worksheet_safely


def render_tab_gold(client):
    st.markdown("### 🟡 จัดการพอร์ตการลงทุนทองคำ")
    st.markdown("เลือกประเภทการลงทุน: ทองคำแท่ง/ทองรูปพรรณ หรือ เทรดทอง/กองทุนทอง (ระบบดึงข้อมูลแบบ Web Scraping สดจากเว็บอ้างอิง)")

    import requests
    import pandas as pd
    from bs4 import BeautifulSoup
    from datetime import datetime, timedelta

    # 🔄 ฟังก์ชัน Scraping ราคาทองคำจากเว็บสมาคมฯ หรือเว็บสำรอง
    def get_gold_price_by_scraping():
        # ตรวจสอบ Cache ใน Session ไม่ให้ยิงถี่เกินไป (ภายใน 3 ชม.)
        if 'scraped_gold_date' in st.session_state:
            last_update = st.session_state['scraped_gold_date']
            if isinstance(last_update, datetime) and (datetime.now() - last_update) < timedelta(hours=3):
                if 'scraped_gold_bar' in st.session_state and 'scraped_gold_jewelry' in st.session_state:
                    return st.session_state['scraped_gold_bar'], st.session_state['scraped_gold_jewelry']

        try:
            # ใช้ User-Agent เพื่อป้องกันเว็บมองว่าเป็น Bot แล้วบล็อก
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }

            # ตัวอย่างดึงจากเว็บราคาทองไทยยอดนิยม (เช่น goldtraders หรือเว็บตัวแทนที่โครงสร้างอ่านง่าย)
            # หมายเหตุ: หากโครงสร้าง HTML ของเว็บสมาคมมีการเปลี่ยนแปลง อาจต้องปรับตัวเลือก tag ค้นหา
            url = "https://www.goldtraders.or.th/"
            response = requests.get(url, headers=headers, timeout=8)

            if response.status_code == 200:
                # ใช้ lxml หรือ html.parser แกะโครงสร้าง HTML
                soup = BeautifulSoup(response.text, 'html.parser')

                # ค้นหาตามโครงสร้างตารางราคาของเว็บสมาคมฯ (ตัวอย่าง ID หรือ Class มาตรฐาน)
                # โดยปกติเว็บสมาคมจะแสดงราคาทองคำแท่งและทองรูปพรรณในตารางหน้าแรก
                bar_val = None
                jewelry_val = None

                # ค้นหาตัวเลขราคาจาก element ที่เกี่ยวข้อง
                # (โครงสร้างเว็บสมาคมค้าทองคำหลักมักจะใช้ id เช่น DetailPlace_LabelBuy หรือคล้ายกัน)
                # หากเว็บหลักบล็อกหรือโครงสร้างเปลี่ยน เราสามารถสลับมาดึงผ่านเว็บสำรองที่โครงสร้างนิ่งกว่าได้

                # ลองค้นหาจากตารางราคารับซื้อ/ขายออกทั่วไป
                spans = soup.find_all('span')
                prices = []
                for span in spans:
                    text = span.get_text().strip().replace(',', '')
                    # กรองหาตัวเลขที่เป็นเรทราคาทอง (เช่น อยู่ในช่วง 30,000 - 100,000 บาท)
                    try:
                        val = float(text)
                        if 30000 <= val <= 100000:
                            prices.append(val)
                    except ValueError:
                        pass

                # ถอดรหัสค่าที่ดึงได้ (มักเรียงตาม ลำดับ ทองคำแท่งขายออก, ทองรูปพรรณขายออก ฯลฯ)
                if len(prices) >= 2:
                    # สมมติฐานตำแหน่งราคาขายออกแท่งและรูปพรรณ
                    bar_val = prices[0] # ปรับแก้ตามหน้าเว็บจริง
                    jewelry_val = prices[1]

                    # บันทึกลง Session
                    st.session_state['scraped_gold_date'] = datetime.now()
                    st.session_state['scraped_gold_bar'] = bar_val
                    st.session_state['scraped_gold_jewelry'] = jewelry_val

                    return bar_val, jewelry_val

        except Exception as e:
            pass

        # Fallback: ถ้า Scrape ไม่สำเร็จ ดึงค่าเดิมมาใช้ หรือใช้ค่าสำรองปัจจุบัน
        fallback_bar = st.session_state.get('scraped_gold_bar', 68300.0)
        fallback_jewelry = st.session_state.get('scraped_gold_jewelry', 69100.0)
        return fallback_bar, fallback_jewelry

    # เรียกใช้งานฟังก์ชัน Scraping
    ref_gold_bar, ref_gold_jewelry = get_gold_price_by_scraping()

    # แสดงผลราคาอ้างอิง
    col_p1, col_p2 = st.columns(2)
    col_p1.metric("📌 ราคาทองคำแท่ง (Scraped)", f"{ref_gold_bar:,.2f} ฿ / บาททอง")
    col_p2.metric("📌 ราคาทองรูปพรรณ (Scraped)", f"{ref_gold_jewelry:,.2f} ฿ / บาททอง")
    st.markdown("---")

    # 🔄 โหลดข้อมูลจาก Google Sheets และคำนวณพอร์ตทองคำต่อ
    if 'gold_portfolio' not in st.session_state:
        st.session_state['gold_portfolio'] = []
        try:
            sheet_gold = get_worksheet_safely(client, 'MyStockData', 'Gold_Portfolio')
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
                    sheet_gold = get_worksheet_safely(client, 'MyStockData', 'Gold_Portfolio')
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
                            sheet_gold = get_worksheet_safely(client, 'MyStockData', 'Gold_Portfolio')
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

        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("💰 มูลค่าตลาดพอร์ตทองรวม", f"{total_market_value:,.2f} ฿")
        col_m2.metric("📦 มูลค่าตั้งต้นรวม", f"{total_cost_value:,.2f} ฿")
        col_m3.metric("📈 กำไร/ขาดทุนรวม", f"{total_pl:,.2f} ฿", f"{total_pl_pct:,.2f}%")

        if st.button("🗑️ ล้างข้อมูลพอร์ตทองคำทั้งหมด"):
            st.session_state['gold_portfolio'] = []
            st.session_state['total_gold_portfolio_value'] = 0.0
            try:
                sheet_gold = get_worksheet_safely(client, 'MyStockData', 'Gold_Portfolio')
                if sheet_gold is not None:
                    sheet_gold.clear()
                    sheet_gold.append_row(["ประเภท", "น้ำหนัก/มูลค่าซื้อ", "หน่วย", "ราคาต้นทุนเฉลี่ย", "มูลค่าตั้งต้น", "ราคาตลาดปัจจุบัน", "มูลค่าตลาด", "หมายเหตุ", "วันที่บันทึก"])
            except:
                pass
            st.rerun()
    else:
        st.info("ยังไม่มีข้อมูลในพอร์ตทองคำ กรุณากรอกฟอร์มด้านบนเพื่อเพิ่มรายการ")
