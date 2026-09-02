import re
import streamlit as st
import pandas as pd
import os
import json
import firebase_admin
from firebase_admin import credentials, firestore

# ==========================================================
# ชั้นเชื่อมต่อ Firebase (แทนที่ get_gsheet_client เดิม)
# ==========================================================

@st.cache_resource(show_spinner=False)
def get_firestore_client():
    try:
        if not firebase_admin._apps:
            if 'FIREBASE_APPLICATION_CREDENTIALS' in os.environ:
                creds_dict = json.loads(os.environ['FIREBASE_APPLICATION_CREDENTIALS'])
            else:
                creds_dict = dict(st.secrets["firebase_service_account"])
            cred = credentials.Certificate(creds_dict)
            firebase_admin.initialize_app(cred)
        return firestore.client()
    except Exception as e:
        print(f"Error เชื่อมต่อ Firebase: {e}")
        raise e

# alias ให้ชื่อเดียวกับของเดิม เพื่อให้ทุกไฟล์ (App.py, tab_*.py) ที่เคยเรียก
# get_gsheet_client() ยังทำงานได้เหมือนเดิมโดยไม่ต้องแก้ไฟล์เหล่านั้นเลย
def get_gsheet_client():
    return get_firestore_client()


def get_active_sheet_name():
    return st.session_state.get('active_sheet_name', 'MyStockData')


# ==========================================================
# ตัวเลียนแบบ gspread Worksheet ด้วย Firestore
#
# โครงสร้างข้อมูลใน Firestore: users/{sheet_name}/{worksheet_name}/{doc}
# gspread ไม่มีแนวคิด "เลขแถว/เลขคอลัมน์" ใน Firestore (เป็น document แต่ละใบ)
# จึงต้องจำลองขึ้นมาเอง:
#   - document พิเศษชื่อ "_meta" เก็บ {"columns": [...], "next_seq": N} แทน "หัวตาราง"
#     ของ gspread (คอลัมน์ที่ 1 = columns[0], แถวที่ 1 = columns ทั้งหมด)
#   - แต่ละ "แถวข้อมูล" คือ 1 document ชื่อ = เลขลำดับ (_seq) ที่เพิ่มขึ้นเรื่อยๆ ตอน append
#     แถวที่ 2 ของ gspread (แถวข้อมูลแรก) = document ที่มี _seq=0, แถวที่ 3 = _seq=1, ...
#     (แถวที่ 1 ถูกกันไว้ให้ "หัวตาราง" เหมือน gspread เสมอ)
#   - เรียงลำดับด้วย query .order_by('_seq') ซึ่ง Firestore จะไม่คืน document ที่ไม่มี
#     field นี้ (เช่น "_meta") มาด้วยโดยอัตโนมัติอยู่แล้ว
# ทุก method ในคลาสนี้ query ข้อมูลสดจาก Firestore ทุกครั้ง (ไม่ cache ข้อมูลไว้ในตัว
# object) เพื่อกันบั๊กเรื่องเลขแถวเพี้ยนจากการที่ object นี้ถูกแชร์ข้ามผู้ใช้/เซสชัน
# (get_cached_worksheet cache ตัว object นี้ไว้ 5 นาที ใช้ร่วมกันทุกคนที่เปิดชีตเดียวกัน)
# ==========================================================

class _FirestoreCell:
    """เลียนแบบ gspread.Cell แบบพื้นฐาน (มีแค่ .row/.col/.value ที่โค้ดเดิมใช้จริง)"""
    def __init__(self, row, col, value):
        self.row = row
        self.col = col
        self.value = value


class FirestoreWorksheet:
    """
    เลียนแบบ method หลักของ gspread Worksheet เพื่อให้โค้ดเดิมในไฟล์อื่นที่เรียก
    sheet.get_all_records(), sheet.append_row()/append_rows(), sheet.update_cell(),
    sheet.update(), sheet.find(), sheet.delete_rows(), sheet.row_values(),
    sheet.get_all_values(), sheet.clear() ยังทำงานได้เหมือนเดิม ไม่ต้องแก้ไฟล์เหล่านั้น
    """

    _CELL_RE = re.compile(r'^([A-Za-z]+)(\d+)$')

    def __init__(self, client, collection_ref):
        self._client = client
        self._collection = collection_ref
        self._meta_ref = collection_ref.document('_meta')

    # --------------------------------------------------------
    # helper ภายใน
    # --------------------------------------------------------
    def _get_columns(self):
        snap = self._meta_ref.get()
        meta = snap.to_dict() if snap.exists else {}
        return list(meta.get('columns', []))

    def _fetch_rows(self):
        """คืน list ของ {'doc_id':..., 'data':...} เรียงตามลำดับที่ถูก append (เหมือนแถวใน gspread)"""
        docs = self._collection.order_by('_seq').stream()
        rows = []
        for doc in docs:
            if doc.id == '_meta':
                continue
            data = dict(doc.to_dict() or {})
            data.pop('_seq', None)
            rows.append({'doc_id': doc.id, 'data': data})
        return rows

    def _ensure_columns(self, columns):
        if columns:
            self._meta_ref.set({'columns': list(columns)}, merge=True)

    def _next_seq(self):
        """เพิ่มเลขลำดับถัดไปแบบ atomic ด้วย transaction กันปัญหาสองคนเขียนพร้อมกันได้เลขซ้ำ"""
        meta_ref = self._meta_ref

        @firestore.transactional
        def _txn(transaction):
            snap = meta_ref.get(transaction=transaction)
            meta = snap.to_dict() if snap.exists else {}
            seq = meta.get('next_seq', 0)
            transaction.set(meta_ref, {'next_seq': seq + 1}, merge=True)
            return seq

        return _txn(self._client.transaction())

    def _delete_all_docs(self):
        refs = [d.reference for d in self._collection.stream()]
        for i in range(0, len(refs), 400):  # Firestore batch จำกัดสูงสุด 500 การเขียนต่อ batch
            batch = self._client.batch()
            for ref in refs[i:i + 400]:
                batch.delete(ref)
            batch.commit()

    @classmethod
    def _col_to_idx(cls, letters):
        idx = 0
        for ch in letters.upper():
            idx = idx * 26 + (ord(ch) - ord('A') + 1)
        return idx

    @classmethod
    def _parse_cell_ref(cls, ref):
        m = cls._CELL_RE.match(ref.strip())
        if not m:
            raise ValueError(f"ตำแหน่งเซลล์ไม่ถูกต้อง: {ref}")
        col_letters, row_str = m.groups()
        return cls._col_to_idx(col_letters), int(row_str)

    # --------------------------------------------------------
    # อ่านข้อมูล
    # --------------------------------------------------------
    def get_all_records(self):
        return [r['data'] for r in self._fetch_rows()]

    def get_all_values(self):
        columns = self._get_columns()
        values = [columns]
        for r in self._fetch_rows():
            values.append([r['data'].get(c, '') for c in columns])
        return values

    def row_values(self, row):
        columns = self._get_columns()
        if row == 1:
            return columns
        rows = self._fetch_rows()
        idx = row - 2
        if idx < 0 or idx >= len(rows):
            return []
        data = rows[idx]['data']
        return [data.get(c, '') for c in columns] if columns else list(data.values())

    def find(self, query):
        columns = self._get_columns()
        for i, r in enumerate(self._fetch_rows()):
            data = r['data']
            cols_to_check = columns if columns else list(data.keys())
            for col_idx, col_name in enumerate(cols_to_check, start=1):
                if str(data.get(col_name, '')) == str(query):
                    return _FirestoreCell(row=i + 2, col=col_idx, value=query)
        return None

    # --------------------------------------------------------
    # เขียนข้อมูล
    # --------------------------------------------------------
    def append_rows(self, rows, columns=None):
        if not rows:
            return
        if columns is None:
            if isinstance(rows[0], dict):
                columns = list(rows[0].keys())
            else:
                raise ValueError("append_rows กับข้อมูลแบบ list ต้องระบุ columns=[...] ด้วย")
        self._ensure_columns(columns)
        for row in rows:
            # เติม '' ให้คอลัมน์ที่ไม่ได้ส่งค่ามาเสมอ (เช่น add_to_watchlist ส่งมาแค่ 4 ค่า
            # ทั้งที่หัวตารางมี 7 คอลัมน์) ให้ตรงกับ gspread จริงที่เซลล์ว่างอ่านกลับมาเป็น '' เสมอ
            # ไม่ใช่ field หายไปเลยจาก document (ต่างจาก dict(zip(...)) ที่ตัดคอลัมน์ส่วนเกินทิ้ง)
            if isinstance(row, dict):
                row_dict = {c: row.get(c, '') for c in columns}
            else:
                row_dict = {c: (row[i] if i < len(row) else '') for i, c in enumerate(columns)}
            seq = self._next_seq()
            doc_data = dict(row_dict)
            doc_data['_seq'] = seq
            self._collection.document(str(seq)).set(doc_data)

    def append_row(self, values):
        columns = self._get_columns()
        if not columns:
            raise ValueError(
                "ยังไม่มีหัวตาราง (_meta.columns) ของ worksheet นี้ — "
                "ต้องทำ migration ก่อน หรือเรียก append_rows(..., columns=[...]) ก่อนใช้ append_row()"
            )
        self.append_rows([values], columns=columns)

    def update_cell(self, row, col, value):
        rows = self._fetch_rows()
        idx = row - 2
        if idx < 0 or idx >= len(rows):
            raise IndexError(f"ไม่พบแถวที่ {row}")
        columns = self._get_columns()
        if col < 1 or col > len(columns):
            raise IndexError(f"ไม่พบคอลัมน์ที่ {col}")
        field_name = columns[col - 1]
        self._collection.document(rows[idx]['doc_id']).update({field_name: value})

    def update(self, *args, **kwargs):
        """
        เลียนแบบ gspread Worksheet.update() ซึ่งรองรับได้หลายรูปแบบการเรียกในโค้ดเดิม:
          - update('A1', values)                          -> เขียนทับทั้งชีต (values[0]=หัวตาราง)
          - update(range_name='A1', values=values)         -> เหมือนกัน
          - update(values)                                 -> ไม่ระบุ range = เริ่มที่ A1 เหมือนกัน
          - update(range_name='C5:M5', values=[[...]])      -> แก้บางคอลัมน์ของแถวที่ 5 เท่านั้น
          - update(range_name='A7', values=[[...]])         -> แก้ทั้งแถวที่ 7 เริ่มจากคอลัมน์ A
        กติกา: ถ้า values มีมากกว่า 1 แถว และเริ่มที่แถว 1 (แถวหัวตาราง) ถือว่าเป็นการ
        "เขียนทับทั้งชีต" (ลบของเดิมทั้งหมดแล้วเขียนใหม่) เพราะเป็น pattern เดียวที่โค้ดเดิม
        ใช้กรณีนี้จริง (ไม่มีการอัปเดตหลายแถวพร้อมกันแบบเจาะจงเซลล์)
        """
        range_name = kwargs.get('range_name')
        values = kwargs.get('values')
        for a in args:
            if isinstance(a, str) and range_name is None:
                range_name = a
            elif isinstance(a, list) and values is None:
                values = a
        if not values:
            return

        if range_name:
            col_start, row_start = self._parse_cell_ref(range_name.split(':')[0])
        else:
            col_start, row_start = 1, 1

        if row_start == 1 and len(values) > 1:
            header = [str(v) for v in values[0]]
            self._replace_all(header, values[1:])
            return

        if row_start == 1:
            # เขียนแค่แถวหัวตารางแถวเดียว (ไม่พบการใช้งาน pattern นี้จริงในระบบ กันเหนียวไว้)
            self._meta_ref.set({'columns': list(values[0])}, merge=True)
            return

        rows = self._fetch_rows()
        idx = row_start - 2
        if idx < 0 or idx >= len(rows):
            raise IndexError(f"ไม่พบแถวที่ {row_start}")
        columns = self._get_columns()
        value_row = values[0]
        update_dict = {}
        for i, v in enumerate(value_row):
            col_idx = col_start + i
            if col_idx - 1 < len(columns):
                update_dict[columns[col_idx - 1]] = v
        self._collection.document(rows[idx]['doc_id']).update(update_dict)

    def _replace_all(self, header, data_rows):
        self._delete_all_docs()
        self._meta_ref.set({'columns': header, 'next_seq': 0})
        if data_rows:
            self.append_rows(data_rows, columns=header)

    def delete_rows(self, row):
        rows = self._fetch_rows()
        idx = row - 2
        if idx < 0 or idx >= len(rows):
            raise IndexError(f"ไม่พบแถวที่ {row}")
        self._collection.document(rows[idx]['doc_id']).delete()

    def clear(self):
        self._delete_all_docs()


@st.cache_resource(ttl=300, show_spinner=False)
def get_cached_worksheet(_client, spreadsheet_name, worksheet_name):
    collection_ref = _client.collection('users').document(spreadsheet_name).collection(worksheet_name)
    return FirestoreWorksheet(_client, collection_ref)


def get_worksheet_safely(client, spreadsheet_name, worksheet_name, retries=2, delay=1):
    try:
        return get_cached_worksheet(client, spreadsheet_name, worksheet_name)
    except Exception as e:
        st.error(f"❌ ไม่สามารถเชื่อมต่อ Firestore ได้: {e}")
        return None


# ==========================================================
# ฟังก์ชันบันทึกที่ต้องปรับ (ต้องระบุ columns เพราะ Firestore ไม่มี "หัวตาราง" แบบ Sheets)
# ==========================================================

def save_cash_to_gsheet(df):
    if df.empty:
        st.warning("ไม่มีข้อมูลที่จะบันทึก")
        return False
    try:
        client = get_gsheet_client()
        sheet = get_cached_worksheet(client, get_active_sheet_name(), "Cash_Flow")
        sheet.append_rows(df.values.tolist(), columns=df.columns.tolist())
        return True
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการบันทึก Cash_Flow: {e}")
        return False


def save_data_to_sheet(new_df, sheet_name):
    try:
        client = get_gsheet_client()
        sheet = get_cached_worksheet(client, get_active_sheet_name(), 'TFEX_History')
        cols = ["Trade_ID", "Date_Open", "Date_Close", "Series", "Status", "Size", "Open_Price",
                "Close_Price", "Realized", "Comm", "Net_Profit", "Win_Lose", "Reason"]
        new_df = new_df.reindex(columns=cols)
        sheet.append_rows(new_df.values.tolist(), columns=cols)
        st.cache_data.clear()
        st.success("เปิดสถานะสำเร็จ!")
        st.rerun()
        return True
    except Exception as e:
        st.error(f"บันทึกข้อมูลไม่สำเร็จ: {e}")
        return False
