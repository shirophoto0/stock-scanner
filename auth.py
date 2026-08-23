# =============================================================
# auth.py
# ระบบ Login แยกผู้ใช้ + กำหนดว่าแต่ละคนใช้ Google Sheet ชื่อไหน + จำโหมดสีที่แต่ละคนชอบ
# =============================================================
import streamlit as st
from theme import render_theme_toggle


def check_login():
    """
    แสดงหน้า Login ถ้ายังไม่ได้ล็อกอิน และหยุดการทำงานของแอปไว้ก่อน (st.stop())
    ถ้าล็อกอินสำเร็จแล้ว จะคืนค่าชื่อ Google Sheet ที่ผู้ใช้คนนั้นควรใช้
    """
    # ถ้าล็อกอินอยู่แล้ว (เคยกรอกถูกในเซสชันนี้) ไม่ต้องแสดงฟอร์มซ้ำ
    if st.session_state.get("logged_in", False):
        return st.session_state.get("active_sheet_name", "MyStockData")

    st.markdown("## 🔐 เข้าสู่ระบบ")
    st.caption("กรุณาเลือกชื่อผู้ใช้และกรอกรหัสผ่านเพื่อเข้าใช้งานแอป")

    # ดึงรายชื่อผู้ใช้ทั้งหมดมาจาก Secrets เพื่อสร้างเป็น Dropdown (ไม่ต้องพิมพ์เอง พิมพ์ผิดไม่ได้)
    try:
        users = st.secrets["users"]
        user_list = list(users.keys())
    except Exception:
        st.error("❌ ยังไม่ได้ตั้งค่าผู้ใช้งานในระบบ (Secrets) กรุณาติดต่อผู้ดูแลแอป")
        st.stop()

    with st.form("login_form"):
        username = st.selectbox("ชื่อผู้ใช้ (Username)", options=user_list)
        password = st.text_input("รหัสผ่าน (Password)", type="password")
        submitted = st.form_submit_button("เข้าสู่ระบบ", use_container_width=True, type="primary")

    if submitted:
        user_info = users.get(username)
        if user_info is not None and password == user_info.get("password"):
            st.session_state["logged_in"] = True
            st.session_state["username"] = username
            st.session_state["active_sheet_name"] = user_info.get("sheet_name", "MyStockData")
            # 🆕 จำโหมดสี (Dark/Light) ที่ผู้ใช้คนนี้ตั้งไว้ใน Secrets เป็นค่าเริ่มต้นให้อัตโนมัติ
            # (ตั้งค่า theme = "dark" หรือ "light" ต่อผู้ใช้ได้ใน Secrets ถ้าไม่ตั้งไว้ จะใช้ dark)
            st.session_state["theme_mode"] = user_info.get("theme", "dark")
            st.rerun()
        else:
            st.error("❌ รหัสผ่านไม่ถูกต้อง")

    # ยังไม่ล็อกอินสำเร็จ ให้หยุดการทำงานของแอปไว้ตรงนี้ ไม่ให้รันโค้ดส่วนอื่นต่อ
    st.stop()


def logout():
    """เคลียร์ข้อมูลทั้งหมดในเซสชันนี้ แล้วพากลับไปหน้า Login"""
    st.session_state.clear()
    st.rerun()


def show_user_bar():
    """แสดงชื่อผู้ใช้ที่ login อยู่ + สวิตช์สลับโหมดสี + ปุ่มออกจากระบบ ไว้ที่แถบด้านข้าง (Sidebar)"""
    with st.sidebar:
        st.markdown(f"👤 เข้าสู่ระบบในชื่อ: **{st.session_state.get('username', '')}**")
        render_theme_toggle()
        if st.button("🚪 ออกจากระบบ (Logout)", use_container_width=True):
            logout()
        st.divider()
