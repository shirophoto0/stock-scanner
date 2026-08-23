# =============================================================
# auth.py
# ระบบ Login แยกผู้ใช้ + กำหนดว่าแต่ละคนใช้ Google Sheet ชื่อไหน
# =============================================================
import streamlit as st


def check_login():
    """
    แสดงหน้า Login ถ้ายังไม่ได้ล็อกอิน และหยุดการทำงานของแอปไว้ก่อน (st.stop())
    ถ้าล็อกอินสำเร็จแล้ว จะคืนค่าชื่อ Google Sheet ที่ผู้ใช้คนนั้นควรใช้
    """
    # ถ้าล็อกอินอยู่แล้ว (เคยกรอกถูกในเซสชันนี้) ไม่ต้องแสดงฟอร์มซ้ำ
    if st.session_state.get("logged_in", False):
        return st.session_state.get("active_sheet_name", "MyStockData")

    st.markdown("## 🔐 เข้าสู่ระบบ")
    st.caption("กรุณากรอกชื่อผู้ใช้และรหัสผ่านเพื่อเข้าใช้งานแอป")

    with st.form("login_form"):
        username = st.text_input("ชื่อผู้ใช้ (Username)")
        password = st.text_input("รหัสผ่าน (Password)", type="password")
        submitted = st.form_submit_button("เข้าสู่ระบบ", use_container_width=True, type="primary")

    if submitted:
        try:
            users = st.secrets["users"]
        except Exception:
            st.error("❌ ยังไม่ได้ตั้งค่าผู้ใช้งานในระบบ (Secrets) กรุณาติดต่อผู้ดูแลแอป")
            st.stop()

        user_info = users.get(username)
        if user_info is not None and password == user_info.get("password"):
            st.session_state["logged_in"] = True
            st.session_state["username"] = username
            st.session_state["active_sheet_name"] = user_info.get("sheet_name", "MyStockData")
            st.rerun()
        else:
            st.error("❌ ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")

    # ยังไม่ล็อกอินสำเร็จ ให้หยุดการทำงานของแอปไว้ตรงนี้ ไม่ให้รันโค้ดส่วนอื่นต่อ
    st.stop()


def logout():
    """เคลียร์ข้อมูลทั้งหมดในเซสชันนี้ แล้วพากลับไปหน้า Login"""
    st.session_state.clear()
    st.rerun()


def show_user_bar():
    """แสดงชื่อผู้ใช้ที่ login อยู่ + ปุ่มออกจากระบบ ไว้ที่แถบด้านข้าง (Sidebar)"""
    with st.sidebar:
        st.markdown(f"👤 เข้าสู่ระบบในชื่อ: **{st.session_state.get('username', '')}**")
        if st.button("🚪 ออกจากระบบ (Logout)", use_container_width=True):
            logout()
        st.divider()
