import os
import re
import openpyxl
from db import get_db_connection, is_postgres, init_db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXCEL_PATH = os.path.join(BASE_DIR, 'Fee record Main Campus.xlsx')

MONTH_LOOKUP = {
    'jan': ('January', 1), 'january': ('January', 1),
    'feb': ('February', 2), 'fe': ('February', 2), 'february': ('February', 2),
    'mar': ('March', 3), 'march': ('March', 3),
    'apr': ('April', 4), 'april': ('April', 4),
    'may': ('May', 5),
    'jun': ('June', 6), 'june': ('June', 6),
    'jul': ('July', 7), 'july': ('July', 7),
    'aug': ('August', 8), 'august': ('August', 8),
    'sep': ('September', 9), 'sept': ('September', 9), 'september': ('September', 9),
    'oct': ('October', 10), 'october': ('October', 10),
    'nov': ('November', 11), 'november': ('November', 11),
    'dec': ('December', 12), 'dece': ('December', 12), 'december': ('December', 12)
}

MONTH_NUM_TAG = {
    'jan': 1, 'january': 1,
    'feb': 2, 'fe': 2, 'february': 2,
    'mar': 3, 'march': 3,
    'apr': 4, 'april': 4,
    'may': 5,
    'jun': 6, 'june': 6,
    'jul': 7, 'july': 7,
    'aug': 8, 'august': 8,
    'sep': 9, 'sept': 9, 'september': 9,
    'oct': 10, 'october': 10,
    'nov': 11, 'november': 11,
    'dec': 12, 'dece': 12, 'december': 12
}

def derive_start_month_year(arrears_tag, default_start_m=3, default_start_y=2026):
    if not arrears_tag:
        return default_start_m, default_start_y
    tag = str(arrears_tag).lower().strip()
    
    # Find matching month
    matched_m = None
    for mk, mnum in MONTH_NUM_TAG.items():
        if mk in tag:
            matched_m = mnum
            break
            
    if not matched_m:
        return default_start_m, default_start_y
        
    if matched_m == 11:
        return 12, 2025 # next month is Dec 2025
    elif matched_m == 12:
        return 1, 2026 # next month is Jan 2026
    elif matched_m in (1, 2):
        return matched_m + 1, 2026
    elif matched_m >= 3 and matched_m <= 10:
        return matched_m + 1, 2026
        
    return default_start_m, default_start_y

def parse_pending_amount(val):
    """Extracts pending amount from strings like '2000p', '4500(2000p)', '4000(1000p', '1500(3500p)'"""
    if val is None:
        return 0
    s = str(val).strip().lower()
    m_split = re.search(r'\((\d+)\s*p?\)?', s)
    if m_split:
        return int(m_split.group(1))
    m_p = re.search(r'^(\d+)\s*p$', s)
    if m_p:
        return int(m_p.group(1))
    return 0

def is_month_arrears(val_str):
    """Checks if value is like '21800july', '60600jul', '4800nov', '15200pending till june'"""
    val_lower = val_str.lower().strip()
    m = re.match(r'^(\d+)\s*([a-zA-Z]+.*)$', val_lower)
    if m:
        amt = int(m.group(1))
        suffix = m.group(2).strip().lower()
        if suffix not in ('p', 'st', 'stat', 'party', 'prty') and any(m_key in suffix for m_key in ['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec','clear','pend']):
            return True, amt, suffix
    if 'pending till' in val_lower or 'till' in val_lower:
        m_amt = re.search(r'\d+', val_str)
        if m_amt:
            return True, int(m_amt.group()), val_str
    return False, 0, ''

def parse_cell_amount(val, default_fee=0):
    if val is None or val == '':
        return 0, ''
    if isinstance(val, (int, float)):
        if val == 0:
            return default_fee, 'Waived (0)'
        return int(val), ''
    val_str = str(val).strip()
    if not val_str or val_str.lower() in ('nan', 'none', '-'):
        return 0, ''
        
    val_lower = val_str.lower()
    
    if val_lower in ('0', '0.0', 'zero', 'nil', 'free', 'waived'):
        return default_fee, 'Waived (0)'
    
    # Check if month arrears e.g. 21800july
    is_arr, arr_amt, arr_suffix = is_month_arrears(val_str)
    if is_arr:
        return 0, f'arrears:{arr_amt}:{arr_suffix}'

    # Check if 'done' or 'paid' or 'clear'
    if any(k in val_lower for k in ('done', 'paid', 'clear', 'ok', 'yes')):
        return default_fee, val_str

    # Pattern like '1500(3500p)' or '4000(4000p)'
    m_split = re.match(r'(\d+)\s*\(\s*(\d+)\s*p?\s*\)', val_lower)
    if m_split:
        paid = int(m_split.group(1))
        pending = int(m_split.group(2))
        return paid, f'{pending} pending'

    # Pattern like '650p' or '2700p' or '5000p'
    m_p_only = re.match(r'^(\d+)\s*p$', val_lower)
    if m_p_only:
        pending = int(m_p_only.group(1))
        return 0, f'{pending} pending'

    # Pattern like '1500st' or '1250party'
    m_num_suffix = re.match(r'^(\d+)\s*([a-zA-Z]+.*)$', val_lower)
    if m_num_suffix:
        amt = int(m_num_suffix.group(1))
        note = m_num_suffix.group(2).strip()
        return amt, note

    # General extract number
    m = re.search(r'\d+', val_str)
    if m:
        return int(m.group()), val_str
        
    return 0, val_str

def parse_ac_cell(val, default_ac=2700):
    if val is None or str(val).strip() == '':
        return default_ac, 0, 'blank_pending'
    val_str = str(val).strip()
    val_lower = val_str.lower()
    
    if val_lower in ('none', 'nan', '-'):
        return default_ac, 0, 'blank_pending'
    if val_lower in ('0', 'zero', 'nil'):
        return 0, 0, 'exempt_zero'
        
    # Pattern like '5000(3500p)' or '1500(3500p)'
    m_split = re.match(r'^(\d+)\s*\(\s*(\d+)\s*p?\s*\)', val_lower)
    if m_split:
        p1 = int(m_split.group(1))
        p2 = int(m_split.group(2))
        if p1 > p2:
            total_ac = p1
            paid_ac = p1 - p2
        else:
            paid_ac = p1
            total_ac = p1 + p2
        return total_ac, paid_ac, f'{p2} pending'

    # Pattern like '2700p' or '1350p' or '5000p'
    m_p_only = re.match(r'^(\d+)\s*p$', val_lower)
    if m_p_only:
        pending = int(m_p_only.group(1))
        return pending, 0, f'{pending} pending'

    # Number with party like '1250party'
    m_party = re.match(r'^(\d+)\s*part', val_lower)
    if m_party:
        paid = int(m_party.group(1))
        return paid, paid, 'partial'

    # Pure number like 2700
    m_num = re.search(r'\d+', val_str)
    if m_num:
        amt = int(m_num.group())
        return amt, amt, 'paid'
        
    return default_ac, 0, val_str

def is_row_red(ws, r):
    for c in range(1, min(6, ws.max_column+1)):
        cell = ws.cell(r, c)
        fill = cell.fill
        if fill and fill.fill_type:
            fg = fill.fgColor
            rgb = str(getattr(fg, 'rgb', ''))
            theme = getattr(fg, 'theme', None)
            tint = getattr(fg, 'tint', 0.0)
            if rgb in ('FFFF0000', 'FFC00000', 'FFD99795', 'FFFF6666', 'FFFFC7CE', 'FFFF2020') or (theme == 9 and tint < 0):
                return True
    return False

def import_main_campus():
    init_db()
    
    if not os.path.exists(EXCEL_PATH):
        print(f"Error: {EXCEL_PATH} not found!")
        return
        
    print(f"Loading Excel file: {EXCEL_PATH}...")
    wb = openpyxl.load_workbook(EXCEL_PATH, data_only=True)
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 1. Identify Main Campus ID
    campus_row = cur.execute("SELECT id, name FROM campuses WHERE code = 'main_campus' OR name LIKE '%Main%' ORDER BY id ASC LIMIT 1").fetchone()
    if campus_row:
        campus_id = campus_row['id']
        campus_name = campus_row['name']
    else:
        campus_row = cur.execute("SELECT id, name FROM campuses ORDER BY id ASC LIMIT 1").fetchone()
        campus_id = campus_row['id'] if campus_row else 1
        campus_name = campus_row['name'] if campus_row else 'Default Campus'
        
    print(f"Importing to Campus: {campus_name} (ID: {campus_id})")
    
    # 2. Clear existing records for this campus to prevent duplicates
    cur.execute("DELETE FROM fees WHERE campus_id = ?", (campus_id,))
    cur.execute("DELETE FROM annual_charges_payments WHERE campus_id = ?", (campus_id,))
    cur.execute("DELETE FROM students WHERE campus_id = ?", (campus_id,))
    conn.commit()
    print("Previous records for this campus cleared successfully.")
    
    total_students_imported = 0
    total_active = 0
    total_withdrawn = 0
    total_arrears_students = 0
    total_arrears_amount = 0
    total_fee_records = 0
    total_fee_amount = 0
    total_ac_records = 0
    total_ac_amount = 0
    
    for sheetname in wb.sheetnames:
        if sheetname == 'van Charges':
            continue
            
        ws = wb[sheetname]
        headers = []
        for c in range(1, ws.max_column + 1):
            v = ws.cell(3, c).value
            headers.append(str(v).strip() if v is not None else '')
            
        # Check AC / Annual columns
        ac_cols = []
        for c in range(4, min(14, ws.max_column + 1)):
            h = headers[c-1].lower() if c-1 < len(headers) else ''
            if h in ('ac', 'sp', 'annual'):
                ac_cols.append((c, headers[c-1]))
                
        sheet_students_data = []
        sheet_ac_data = []
        sheet_fee_data = []
        
        for r in range(4, ws.max_row + 1):
            name_val = ws.cell(r, 2).value
            if not name_val or str(name_val).strip().lower() in ('none', 'nan', '', 'student name', 'name', 'sr. #', 'sr#'):
                continue
                
            name = str(name_val).strip()
            father = str(ws.cell(r, 3).value).strip() if ws.cell(r, 3).value else ''
            if father.lower() in ('none', 'nan'):
                father = ''
                
            status = 'withdrawn' if is_row_red(ws, r) else 'active'
            if status == 'withdrawn':
                total_withdrawn += 1
            else:
                total_active += 1
                
            # Determine monthly fee
            monthly_fee = 0
            for c in range(4, min(14, ws.max_column + 1)):
                h = headers[c-1].lower() if c-1 < len(headers) else ''
                if ('month' in h or 'monthly' in h) and not any(h.startswith(m) for m in MONTH_LOOKUP):
                    v = ws.cell(r, c).value
                    amt, _ = parse_cell_amount(v)
                    if amt > 0:
                        monthly_fee = amt
            if monthly_fee == 0:
                monthly_fee = 2400
                
            # Calculate opening arrears from month-tagged entries (like 21800july or 20700may)
            student_opening_arrears = 0
            arrears_tag = None
            for c in range(4, ws.max_column + 1):
                v = ws.cell(r, c).value
                if v is not None:
                    val_str = str(v).strip()
                    is_arr, arr_amt, arr_suffix = is_month_arrears(val_str)
                    if is_arr:
                        student_opening_arrears += arr_amt
                        arrears_tag = arr_suffix
                        
            # Also add pending dues from non-monthly columns (e.g. Book 4500(2000p), Admission 2000p, Sationary 5000p, Sp 500p)
            for c in range(4, ws.max_column + 1):
                h = headers[c-1].lower() if c-1 < len(headers) else ''
                if h in ('month', 'monthly', 'month 26', 'month26', 'monthly 24') or any(h.startswith(m) for m in MONTH_LOOKUP):
                    continue
                if h == 'ac':
                    continue # AC pending is handled directly in annual_charges
                v = ws.cell(r, c).value
                p_amt = parse_pending_amount(v)
                if p_amt > 0:
                    student_opening_arrears += p_amt
                        
            if student_opening_arrears > 0:
                total_arrears_students += 1
                total_arrears_amount += student_opening_arrears
                
            # Derive start_month & start_year from arrears tag (e.g. 20700may -> billing starts June 2026)
            start_month, start_year = derive_start_month_year(arrears_tag, default_start_m=3, default_start_y=2026)
            
            # Calculate Annual Charges for this student from AC column
            class_standard_ac = 2600 if sheetname == 'Graduate' else 2700
            student_annual_charges = 0
            for ac_col_idx, ac_col_name in ac_cols:
                if ac_col_name.lower() == 'ac':
                    v = ws.cell(r, ac_col_idx).value
                    total_ac, paid_ac, ac_note = parse_ac_cell(v, class_standard_ac)
                    student_annual_charges = total_ac
                    
            student_idx = len(sheet_students_data)
            sheet_students_data.append((
                name, father, sheetname, monthly_fee, student_annual_charges,
                student_opening_arrears, start_month, start_year, campus_id, status
            ))
            total_students_imported += 1
            
            # Collect Annual Charges Payments (AC / Sp)
            for ac_col_idx, ac_col_name in ac_cols:
                v = ws.cell(r, ac_col_idx).value
                if v is not None:
                    if ac_col_name.lower() == 'ac':
                        total_ac, paid_ac, ac_note = parse_ac_cell(v, class_standard_ac)
                        if paid_ac > 0:
                            date_paid = "2026-03-01"
                            note_text = f"Annual Charges: {ac_note}"
                            sheet_ac_data.append((student_idx, paid_ac, date_paid, campus_id, note_text))
                            total_ac_records += 1
                            total_ac_amount += paid_ac
                    else:
                        # Sp (Summer Pack)
                        amt, note = parse_cell_amount(v)
                        if amt > 0:
                            date_paid = "2026-06-01"
                            note_text = f"{ac_col_name}: {note}" if note else f"{ac_col_name} Payment"
                            sheet_ac_data.append((student_idx, amt, date_paid, campus_id, note_text))
                            total_ac_records += 1
                            total_ac_amount += amt
                        
            # Collect Monthly Fee Payments
            for c in range(4, ws.max_column + 1):
                h = headers[c-1].lower() if c-1 < len(headers) else ''
                m_matched = None
                for mk, (mname, mnum) in MONTH_LOOKUP.items():
                    if h.startswith(mk):
                        m_matched = (mname, mnum)
                        break
                        
                if m_matched:
                    mname, mnum = m_matched
                    v = ws.cell(r, c).value
                    if v is not None and str(v).strip() != '':
                        paid, note = parse_cell_amount(v, monthly_fee)
                        if paid > 0:
                            year = 2025 if (mname in ('November', 'December') and c < 8) else 2026
                            date_paid = f"{year}-{mnum:02d}-01"
                            note_text = note if note else 'Imported from Excel'
                            sheet_fee_data.append((student_idx, mname, year, paid, date_paid, campus_id, note_text))
                            total_fee_records += 1
                            total_fee_amount += paid

        # Fast Batch Insert for this sheet
        if is_postgres():
            from psycopg2.extras import execute_values
            raw_conn = conn._conn
            raw_cur = raw_conn.cursor()
            
            if sheet_students_data:
                res = execute_values(
                    raw_cur,
                    """INSERT INTO students (name, father_name, class, monthly_fee, annual_charges, opening_arrears, start_month, start_year, campus_id, status)
                       VALUES %s RETURNING id""",
                    sheet_students_data,
                    fetch=True
                )
                student_ids = [r[0] for r in res]
                
                if sheet_ac_data:
                    ac_to_insert = [
                        (student_ids[item[0]], 2026, item[1], item[2], item[3], item[4])
                        for item in sheet_ac_data
                    ]
                    execute_values(
                        raw_cur,
                        """INSERT INTO annual_charges_payments (student_id, year, paid_amount, date_paid, campus_id, notes)
                           VALUES %s""",
                        ac_to_insert
                    )
                    
                if sheet_fee_data:
                    fees_to_insert = [
                        (student_ids[item[0]], item[1], item[2], item[3], item[4], item[5], item[6])
                        for item in sheet_fee_data
                    ]
                    execute_values(
                        raw_cur,
                        """INSERT INTO fees (student_id, month, year, paid_amount, date_paid, campus_id, notes)
                           VALUES %s""",
                        fees_to_insert
                    )
            raw_conn.commit()
        else:
            # SQLite insertion
            student_ids = []
            for s_row in sheet_students_data:
                cur.execute('''
                    INSERT INTO students (name, father_name, class, monthly_fee, annual_charges, opening_arrears, start_month, start_year, campus_id, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', s_row)
                student_ids.append(cur.lastrowid)
                
            for item in sheet_ac_data:
                cur.execute('''
                    INSERT INTO annual_charges_payments (student_id, year, paid_amount, date_paid, campus_id, notes)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (student_ids[item[0]], 2026, item[1], item[2], item[3], item[4]))
                
            for item in sheet_fee_data:
                cur.execute('''
                    INSERT INTO fees (student_id, month, year, paid_amount, date_paid, campus_id, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (student_ids[item[0]], item[1], item[2], item[3], item[4], item[5], item[6]))
            conn.commit()

        print(f"  Processed Sheet '{sheetname}': {len(sheet_students_data)} students, {len(sheet_fee_data)} fee records.")
        conn.commit()
        
    conn.commit()
    conn.close()
    
    print("\n========================================================")
    print("         MAIN CAMPUS IMPORT COMPLETED SUCCESSFULLY!      ")
    print("========================================================")
    print(f"Total Students Imported: {total_students_imported}")
    print(f"   Active Students: {total_active}")
    print(f"   Withdrawn (Red) Students: {total_withdrawn}")
    print(f"Students with Opening Arrears: {total_arrears_students} (Total: Rs. {total_arrears_amount:,})")
    print(f"Total Monthly Fee Transactions: {total_fee_records} (Total: Rs. {total_fee_amount:,})")
    print(f"Total Annual / AC Charges: {total_ac_records} (Total: Rs. {total_ac_amount:,})")
    print("========================================================\n")

if __name__ == '__main__':
    import_main_campus()
