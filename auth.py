# =============================================================
# auth.py
# ระบบ Login แยกผู้ใช้ + กำหนดว่าแต่ละคนใช้ Google Sheet ชื่อไหน
# 🆕 รองรับการ "จำสถานะ Login" ไว้แม้กดรีเฟรชหน้าเว็บ (ไม่ต้องพิมพ์รหัสผ่านซ้ำทุกครั้ง)
# โดยฝากโทเค็นอ้างอิงไว้ใน URL ของเบราว์เซอร์ อายุ 30 วัน จนกว่าจะกด Logout หรือหมดอายุ
# =============================================================
import streamlit as st
import hashlib
import time

# อายุของสถานะ Login ที่จำไว้ (วินาที) — ตั้งไว้ 1 วัน ปรับตัวเลขนี้ได้ถ้าอยากเปลี่ยนอีก
REMEMBER_ME_SECONDS = 1 * 24 * 60 * 60


def _make_session_token(username, password):
    """
    สร้างโทเค็นอ้างอิงจากชื่อผู้ใช้+รหัสผ่าน (ไม่เก็บรหัสผ่านตรงๆ ใน URL)
    ใช้เพื่อยืนยันตอนโหลดหน้าใหม่ว่า "เคย login ถูกต้องมาก่อนจริง" โดยไม่ต้องพิมพ์รหัสซ้ำ
    """
    raw = f"{username}:{password}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _try_restore_login_from_url(users):
    """
    🆕 เช็คว่ามีโทเค็นค้างอยู่ใน URL ไหม (จากตอน login สำเร็จครั้งก่อนหน้า) ถ้ามีและยังไม่หมดอายุ
    จะ login ให้อัตโนมัติ โดยไม่ต้องกรอกรหัสผ่านซ้ำ — นี่คือกลไกที่ทำให้กดรีเฟรชหน้าแล้วไม่หลุด login
    """
    remembered_user = st.query_params.get("u")
    remembered_token = st.query_params.get("t")
    remembered_exp = st.query_params.get("exp")

    if not (remembered_user and remembered_token and remembered_exp):
        return False

    try:
        if int(remembered_exp) < int(time.time()):
            return False  # โทเค็นหมดอายุแล้ว ต้อง login ใหม่
    except ValueError:
        return False

    user_info = users.get(remembered_user)
    if user_info is None:
        return False

    expected_token = _make_session_token(remembered_user, user_info.get("password", ""))
    if remembered_token != expected_token:
        return False  # โทเค็นไม่ตรง (เช่น รหัสผ่านถูกเปลี่ยนใน Secrets ไปแล้ว)

    # ผ่านทุกการตรวจสอบแล้ว — login ให้อัตโนมัติ
    st.session_state["logged_in"] = True
    st.session_state["username"] = remembered_user
    st.session_state["active_sheet_name"] = user_info.get("sheet_name", "MyStockData")
    st.session_state["app_title"] = user_info.get("app_title", "NJ-Wealth")
    return True


def check_login():
    """
    แสดงหน้า Login ถ้ายังไม่ได้ล็อกอิน และหยุดการทำงานของแอปไว้ก่อน (st.stop())
    ถ้าล็อกอินสำเร็จแล้ว จะคืนค่าชื่อ Google Sheet ที่ผู้ใช้คนนั้นควรใช้
    """
    # ถ้าล็อกอินอยู่แล้ว (เคยกรอกถูกในเซสชันนี้) ไม่ต้องแสดงฟอร์มซ้ำ
    if st.session_state.get("logged_in", False):
        return st.session_state.get("active_sheet_name", "MyStockData")

    # ดึงรายชื่อผู้ใช้ทั้งหมดมาจาก Secrets เพื่อสร้างเป็น Dropdown (ไม่ต้องพิมพ์เอง พิมพ์ผิดไม่ได้)
    try:
        users = st.secrets["users"]
        user_list = list(users.keys())
    except Exception:
        st.error("❌ ยังไม่ได้ตั้งค่าผู้ใช้งานในระบบ (Secrets) กรุณาติดต่อผู้ดูแลแอป")
        st.stop()

    # 🆕 ลองเช็คโทเค็นที่ค้างอยู่ใน URL ก่อน (มาจากการ login สำเร็จครั้งก่อนหน้าที่ยังไม่หมดอายุ)
    # ถ้าเจอและถูกต้อง จะข้ามหน้า Login ไปเลย ไม่ต้องพิมพ์รหัสผ่านซ้ำ
    if _try_restore_login_from_url(users):
        return st.session_state.get("active_sheet_name", "MyStockData")

    st.markdown("## 🔐 เข้าสู่ระบบ")
    st.caption("กรุณาเลือกชื่อผู้ใช้และกรอกรหัสผ่านเพื่อเข้าใช้งานแอป")

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
            # 🆕 จำชื่อแอปที่จะแสดงบนหัวข้อใหญ่ ต่อผู้ใช้แต่ละคน (ตั้งค่าได้ใน Secrets ด้วย
            # app_title ถ้าไม่ตั้งไว้ จะใช้ "NJ-Wealth" เป็นค่าเริ่มต้น)
            st.session_state["app_title"] = user_info.get("app_title", "NJ-Wealth")

            # 🆕 บันทึกโทเค็นไว้ใน URL เพื่อให้จำสถานะ login ไว้ได้แม้กดรีเฟรชหน้า (อายุ 30 วัน)
            token = _make_session_token(username, password)
            st.query_params["u"] = username
            st.query_params["t"] = token
            st.query_params["exp"] = str(int(time.time()) + REMEMBER_ME_SECONDS)

            st.rerun()
        else:
            st.error("❌ รหัสผ่านไม่ถูกต้อง")

    # ยังไม่ล็อกอินสำเร็จ ให้หยุดการทำงานของแอปไว้ตรงนี้ ไม่ให้รันโค้ดส่วนอื่นต่อ
    st.stop()


def logout():
    """เคลียร์ข้อมูลทั้งหมดในเซสชันนี้ + ลบโทเค็นที่จำไว้ใน URL แล้วพากลับไปหน้า Login"""
    st.session_state.clear()
    st.query_params.clear()  # 🆕 ลบโทเค็นออกจาก URL ด้วย ไม่งั้นจะ login อัตโนมัติกลับเข้ามาอีก
    st.rerun()


def show_user_bar():
    """แสดงชื่อผู้ใช้ที่ login อยู่ + ปุ่มออกจากระบบ ไว้ที่แถบด้านข้าง (Sidebar)"""
    with st.sidebar:
        st.markdown(f"👤 เข้าสู่ระบบในชื่อ: **{st.session_state.get('username', '')}**")
        if st.button("🚪 ออกจากระบบ (Logout)", use_container_width=True):
            logout()
