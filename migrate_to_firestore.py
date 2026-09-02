"""
สคริปต์ย้ายข้อมูลจริงจาก Google Sheets (MyStockData, Nujiwealth) ไปยัง Firestore

หลักการความปลอดภัย:
- อ่านจาก Google Sheets แบบ "อ่านอย่างเดียว" เท่านั้น (ไม่มีการเขียน/แก้ไข/ลบต้นทางเด็ดขาด)
- ค่าเริ่มต้นคือโหมด dry-run (--apply ถึงจะเขียนจริงลง Firestore)
- เขียนลง Firestore ผ่าน FirestoreWorksheet ตัวเดียวกับที่ backend_functions.py จะใช้จริงใน
  อนาคต (ผ่านการทดสอบ Phase A ครบ 9 ข้อแล้ว) เพื่อให้ข้อมูลที่ย้ายมามีรูปแบบตรงกับที่
  แอปจะอ่านได้ทันที (_meta.columns ถูกตั้งค่าให้ครบ)
- แต่ละ worksheet จะถูก "เขียนทับทั้งหมด" (clear แล้วเขียนใหม่) ทำให้รันซ้ำได้เรื่อยๆ
  อย่างปลอดภัย (idempotent) — รันกี่ครั้งก็ได้ผลลัพธ์เหมือนเดิมเสมอ ไม่สร้างข้อมูลซ้ำซ้อน
- หลังเขียนทุก worksheet จะอ่านกลับมาเทียบกับข้อมูลต้นทางทันที ถ้าไม่ตรงจะแจ้งเตือนทันที

วิธีใช้:
    python migrate_to_firestore.py                                   # dry-run ทั้ง MyStockData + Nujiwealth
    python migrate_to_firestore.py --apply                           # เขียนจริงลง Firestore ทั้ง 2 บัญชี
    python migrate_to_firestore.py --sheets MyStockData --apply       # เขียนจริงเฉพาะบัญชีเดียว
    python migrate_to_firestore.py --sheets MyStockData \\
        --worksheets Watchlist,PortfolioData --apply                 # เขียนจริงเฉพาะบาง worksheet (ทดสอบทีละตัวก่อนได้)
"""
import argparse
import random
import sys
import time

from backend_functions import get_gsheet_client
from firestore_functions import get_firestore_client, get_cached_worksheet


def _retry_sheets_call(fn, *args, retries=6, **kwargs):
    """
    ห่อการเรียก Google Sheets API ด้วย retry กันโดน 429 — โควตา 'Read requests per minute'
    ของ Google Sheets API ค่อนข้างจำกัด (เป็นโควตาต่อนาที) เวลาไล่อ่านหลายสิบ worksheet รวด
    จึงต้องรอนานพอที่โควตาจะรีเซ็ตในรอบถัดไป ไม่ใช่แค่รอสั้นๆ แบบสุ่ม
    """
    for attempt in range(retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if attempt < retries - 1 and ("429" in str(e) or "Quota exceeded" in str(e)):
                wait = 15 * (attempt + 1) + random.uniform(1, 5)
                print(f"    ⏳ โดน rate limit รอ {wait:.1f}s แล้วลองใหม่ (ครั้งที่ {attempt + 1}/{retries})...")
                time.sleep(wait)
                continue
            raise


def migrate_worksheet(spreadsheet, fs_client, spreadsheet_name, ws_title, apply_changes):
    print(f"  → {ws_title}")
    try:
        ws = _retry_sheets_call(spreadsheet.worksheet, ws_title)
        records = _retry_sheets_call(ws.get_all_records)
        # ดึงหัวตารางจาก key ของแถวแรกเลย (ประหยัด API call กว่าเรียก row_values(1) แยก)
        # ยกเว้นตอนไม่มีข้อมูลเลย ถึงจะต้องเรียก row_values(1) เพื่อให้ยังได้หัวตารางมา
        header = list(records[0].keys()) if records else _retry_sheets_call(ws.row_values, 1)
    except Exception as e:
        print(f"    ❌ อ่านจาก Google Sheets ไม่สำเร็จ: {e}")
        return False

    if not header:
        print("    ⏭️  worksheet ว่างเปล่า (ไม่มีหัวตาราง) — ข้าม")
        return True

    print(f"    พบ {len(records)} แถว, {len(header)} คอลัมน์: {header}")

    if not apply_changes:
        preview = records[:2]
        print(f"    (dry-run) ตัวอย่างข้อมูล: {preview}")
        return True

    try:
        target = get_cached_worksheet(fs_client, spreadsheet_name, ws_title)
        target.clear()
        data_matrix = [[rec.get(h, '') for h in header] for rec in records]
        target.update('A1', [header] + data_matrix)
    except Exception as e:
        print(f"    ❌ เขียนลง Firestore ไม่สำเร็จ: {e}")
        return False

    # ตรวจสอบย้อนกลับทันทีว่าข้อมูลที่เขียนไปตรงกับต้นทางเป๊ะ
    try:
        readback = target.get_all_records()
    except Exception as e:
        print(f"    ❌ อ่านกลับจาก Firestore เพื่อตรวจสอบไม่สำเร็จ: {e}")
        return False

    if readback != records:
        print(f"    ❌ ข้อมูลที่อ่านกลับไม่ตรงกับต้นฉบับ! ต้นฉบับ {len(records)} แถว, อ่านกลับได้ {len(readback)} แถว")
        for i, (a, b) in enumerate(zip(records, readback)):
            if a != b:
                print(f"       แถวที่ {i + 2} ไม่ตรง: ต้นฉบับ={a} | Firestore={b}")
                break
        return False

    print(f"    ✅ ย้ายสำเร็จและตรวจสอบแล้วตรงกับต้นฉบับ ({len(records)} แถว)")
    return True


def main():
    parser = argparse.ArgumentParser(description="ย้ายข้อมูลจาก Google Sheets ไปยัง Firestore")
    parser.add_argument("--sheets", default="MyStockData,Nujiwealth", help="รายชื่อ spreadsheet คั่นด้วย , (ค่าเริ่มต้น: MyStockData,Nujiwealth)")
    parser.add_argument("--worksheets", default=None, help="จำกัดเฉพาะบาง worksheet คั่นด้วย , (ค่าเริ่มต้น: ทุก worksheet ในสเปรดชีต)")
    parser.add_argument("--apply", action="store_true", help="เขียนจริงลง Firestore (ค่าเริ่มต้นคือ dry-run แสดงตัวอย่างอย่างเดียว)")
    args = parser.parse_args()

    sheet_names = [s.strip() for s in args.sheets.split(",") if s.strip()]
    worksheet_filter = None
    if args.worksheets:
        worksheet_filter = {w.strip() for w in args.worksheets.split(",") if w.strip()}

    mode_label = "🔴 APPLY (เขียนจริงลง Firestore)" if args.apply else "🟡 DRY-RUN (แสดงตัวอย่างอย่างเดียว ไม่เขียนอะไร)"
    print(f"โหมด: {mode_label}")
    print(f"Spreadsheets: {sheet_names}")
    if worksheet_filter:
        print(f"จำกัดเฉพาะ worksheet: {sorted(worksheet_filter)}")
    print()

    try:
        gs_client = get_gsheet_client()
    except Exception as e:
        print(f"❌ เชื่อมต่อ Google Sheets ไม่สำเร็จ: {e}")
        sys.exit(1)

    fs_client = None
    if args.apply:
        try:
            fs_client = get_firestore_client()
        except Exception as e:
            print(f"❌ เชื่อมต่อ Firestore ไม่สำเร็จ: {e}")
            sys.exit(1)

    overall_ok = True
    for spreadsheet_name in sheet_names:
        print(f"=== {spreadsheet_name} ===")
        try:
            spreadsheet = _retry_sheets_call(gs_client.open, spreadsheet_name)
            worksheets = _retry_sheets_call(spreadsheet.worksheets)
        except Exception as e:
            print(f"❌ เปิด spreadsheet '{spreadsheet_name}' ไม่สำเร็จ: {e}")
            overall_ok = False
            continue

        titles = [ws.title for ws in worksheets]
        if worksheet_filter:
            titles = [t for t in titles if t in worksheet_filter]

        print(f"พบ {len(titles)} worksheet: {titles}")
        for i, title in enumerate(titles):
            if i > 0:
                time.sleep(1.5)  # เว้นจังหวะระหว่าง worksheet กันยิง API ถี่จนโดน 429
            ok = migrate_worksheet(spreadsheet, fs_client, spreadsheet_name, title, args.apply)
            overall_ok = overall_ok and ok
        print()

    if overall_ok:
        print("🎉 เสร็จสิ้นทุกขั้นตอนโดยไม่มีข้อผิดพลาด")
    else:
        print("⚠️ มีบาง worksheet ที่ผิดพลาด ดูรายละเอียดด้านบน — ยังไม่ควรสลับ backend_functions.py ไปใช้ Firestore จนกว่าจะแก้ให้ผ่านหมด")
        sys.exit(1)


if __name__ == "__main__":
    main()
