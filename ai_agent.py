import os
import re
import json
import urllib.request
import urllib.error
from datetime import datetime
from db import get_db_connection

# Month conversion mappings
MONTH_NUM_TO_NAME = {
    1: 'January', 2: 'February', 3: 'March', 4: 'April', 5: 'May', 6: 'June',
    7: 'July', 8: 'August', 9: 'September', 10: 'October', 11: 'November', 12: 'December'
}
MONTH_NAME_TO_NUM = {v: k for k, v in MONTH_NUM_TO_NAME.items()}
SHORT_MONTHS = {
    'jan': 1, 'feb': 2, 'fe': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
}

_CACHED_GEMINI_KEY = None
_KEY_CHECKED = False

def get_gemini_api_key():
    """Retrieve Gemini API key from cache, .env file, env var, or settings table in database."""
    global _CACHED_GEMINI_KEY, _KEY_CHECKED
    if _KEY_CHECKED and _CACHED_GEMINI_KEY:
        return _CACHED_GEMINI_KEY
        
    key = os.environ.get('GEMINI_API_KEY')
    if not key:
        env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
        if os.path.exists(env_file):
            try:
                with open(env_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('GEMINI_API_KEY='):
                            key = line.split('GEMINI_API_KEY=', 1)[1].strip().strip("'\"")
                            break
            except Exception:
                pass

    if key and key.strip():
        _CACHED_GEMINI_KEY = key.strip()
        _KEY_CHECKED = True
        return _CACHED_GEMINI_KEY
    
    # Check in settings table as last resort
    try:
        conn = get_db_connection()
        row = conn.execute("SELECT value FROM settings WHERE key = 'gemini_api_key'").fetchone()
        conn.close()
        if row and row['value']:
            _CACHED_GEMINI_KEY = row['value'].strip()
        else:
            _CACHED_GEMINI_KEY = None
    except Exception:
        _CACHED_GEMINI_KEY = None
        
    _KEY_CHECKED = True
    return _CACHED_GEMINI_KEY

def set_gemini_api_key(api_key):
    """Save Gemini API key to .env file, settings table, and update memory cache."""
    global _CACHED_GEMINI_KEY, _KEY_CHECKED
    k = api_key.strip()
    _CACHED_GEMINI_KEY = k
    _KEY_CHECKED = True
    
    # Save to .env
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    try:
        lines = []
        if os.path.exists(env_file):
            with open(env_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        
        has_gemini = False
        new_lines = []
        for line in lines:
            if line.strip().startswith('GEMINI_API_KEY='):
                new_lines.append(f"GEMINI_API_KEY={k}\n")
                has_gemini = True
            else:
                new_lines.append(line)
        if not has_gemini:
            new_lines.append(f"GEMINI_API_KEY={k}\n")
            
        with open(env_file, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
    except Exception as e:
        print(f"Warning: could not write key to .env: {e}")
        
    # Also save to settings DB
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('gemini_api_key', ?)", (k,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error saving Gemini API key to DB: {e}")
        return True  # .env was already saved
    finally:
        conn.close()

# -------------------------------------------------------------
# CORE DATABASE TOOLS (Action Handlers)
# -------------------------------------------------------------

# Class Synonyms and Mapping for robust Roman Urdu / English class matching
CLASS_SYNONYMS = {
    '1': ['1', 'one', '1st', 'first'],
    '2': ['2', 'two', '2nd', 'second'],
    '3': ['3', 'three', '3rd', 'third'],
    '4': ['4', 'four', '4th', 'fourth'],
    '5': ['5', 'five', '5th', 'fifth'],
    '6': ['6', 'six', '6th', 'sixth'],
    '7': ['7', 'seven', '7th', 'seventh'],
    '8': ['8', 'eight', '8th', 'eighth'],
    '9': ['9', 'nine', '9th', 'ninth'],
    '10': ['10', 'ten', '10th', 'tenth'],
    'nursery': ['nursery', 'nur'],
    'prep': ['prep'],
    'pg': ['pg', 'playgroup', 'play group', 'play'],
    'playgroup': ['pg', 'playgroup', 'play group', 'play'],
    'graduate': ['graduate', 'passed', 'alumni']
}

def get_class_aliases(class_name):
    """Return all aliases/variations of a class (e.g. '2' -> ['2', 'two', '2nd', 'second'])."""
    if not class_name:
        return []
    c = str(class_name).lower().replace('class', '').replace('grade', '').replace('jamaat', '').strip()
    for k, aliases in CLASS_SYNONYMS.items():
        if c == k or c in aliases:
            return aliases
    return [c]

# -------------------------------------------------------------
# URDU & PAKISTANI NAME TRANSLITERATION SYSTEM
# -------------------------------------------------------------

# Comprehensive Pakistani Names Dictionary (Urdu Script -> English)
URDU_NAME_MAP = {
    'علی': 'Ali', 'رضا': 'Raza', 'محمد': 'Muhammad', 'احمد': 'Ahmad', 'حسن': 'Hassan',
    'حسین': 'Hussain', 'عثمان': 'Usman', 'حمزہ': 'Hamza', 'فاطمہ': 'Fatima', 'عائشہ': 'Ayesha',
    'زینب': 'Zainab', 'طہ': 'Taha', 'عبداللہ': 'Abdullah', 'بلال': 'Bilal', 'عاطف': 'Atif',
    'اسد': 'Asad', 'سعد': 'Saad', 'عمر': 'Umar', 'ابوبکر': 'Abubakar', 'طاہر': 'Tahir',
    'طیب': 'Tayyab', 'مریم': 'Maryam', 'نور': 'Noor', 'اقرا': 'Iqra', 'اقراء': 'Iqra',
    'سید': 'Syed', 'رانا': 'Rana', 'ملک': 'Malik', 'چوہدری': 'Chaudhry', 'خان': 'Khan',
    'لیاقت': 'Liaqat', 'شوکت': 'Shokat', 'توصیف': 'Touseef', 'ثنااللہ': 'Sanaullah',
    'نفیس': 'Nafees', 'عادل': 'Adil', 'محمود': 'Mehmood', 'ثاقب': 'Saqib', 'عاصم': 'Asim',
    'حیدر': 'Haider', 'شکیل': 'Shakeel', 'انیب': 'Aneeb', 'عبیرہ': 'Abeerah', 'ہادیہ': 'Hadia',
    'عفان': 'Affan', 'شایان': 'Shayan', 'عنایہ': 'Anaya', 'ایمان': 'Iman', 'حرا': 'Hira',
    'ہادی': 'Hadi', 'عبد': 'Abdul', 'عبدالہادی': 'Abdul Hadi', 'عبدالرحمان': 'Abdul Rehman',
    'عبدالرحمن': 'Abdul Rehman', 'عبدالرحمٰن': 'Abdul Rehman', 'جاوید': 'Javed', 'ندیم': 'Nadeem',
    'افضل': 'Afzal', 'سلطان': 'Sultan', 'شریف': 'Sharif', 'شفیق': 'Shafeeq', 'طارق': 'Tariq',
    'کاشف': 'Kashif', 'وقار': 'Waqar', 'وقاص': 'Waqas', 'فیصل': 'Faisal', 'ارسلان': 'Arslan',
    'سلمان': 'Salman', 'نعیم': 'Naeem', 'وسیم': 'Waseem', 'ظہیر': 'Zaheer', 'منیر': 'Muneer',
    'بشیر': 'Basheer', 'خالد': 'Khalid', 'شاہد': 'Shahid', 'ساجد': 'Sajid', 'ماجد': 'Majid',
    'انور': 'Anwar', 'اختر': 'Akhtar', 'اصغر': 'Asghar', 'اکبر': 'Akbar', 'امجد': 'Amjad',
    'ارشد': 'Arshad', 'اقبال': 'Iqbal', 'اعجاز': 'Ijaz', 'اشرف': 'Ashraf', 'مظہر': 'Mazhar',
    'محسن': 'Mohsin', 'مرتضیٰ': 'Murtaza', 'مرتضی': 'Murtaza', 'مصطفیٰ': 'Mustafa', 'مصطفی': 'Mustafa',
    'مجتبیٰ': 'Mujtaba', 'مجتبی': 'Mujtaba', 'کامران': 'Kamran', 'عرفان': 'Irfan', 'فرحان': 'Farhan',
    'شہزاد': 'Shehzad', 'نوید': 'Naveed', 'زوہیب': 'Zohaib', 'عدیل': 'Adeel', 'ریحان': 'Rehan',
    'صہیب': 'Suhaib', 'عمیر': 'Umair', 'زبیر': 'Zubair', 'شعیب': 'Shoaib', 'یاسر': 'Yasir',
    'راشد': 'Rashid', 'زاہد': 'Zahid', 'پرویز': 'Parvez', 'تنویر': 'Tanveer', 'نذیر': 'Nazeer',
    'شبیر': 'Shabbir', 'الیاس': 'Ilyas', 'مقصود': 'Maqsood', 'وارث': 'Waris', 'ایوب': 'Ayoub',
    'حماد': 'Hammad', 'عظیم': 'Azeem', 'نسیم': 'Naseem', 'سہیل': 'Sohail', 'نعمان': 'Nouman',
    'فاروق': 'Farooq', 'حارث': 'Haris', 'داؤد': 'Dawood', 'قاسم': 'Qasim', 'ابراہیم': 'Ibrahim',
    'اسماعیل': 'Ismail', 'اسحاق': 'Ishaq', 'یوسف': 'Yousaf', 'یحییٰ': 'Yahya', 'یحیی': 'Yahya',
    'موسیٰ': 'Musa', 'موسی': 'Musa', 'عیسیٰ': 'Isa', 'سلیمان': 'Sulaiman', 'یونس': 'Younas',
    'ہارون': 'Haroon', 'سیف': 'Saif', 'ضیاء': 'Zia', 'ضیا': 'Zia', 'بابر': 'Babar', 'جہانگیر': 'Jahangir',
    'حفصہ': 'Hafsa', 'سائرہ': 'Saira', 'سمیرا': 'Samira', 'نائلہ': 'Naila', 'شازیہ': 'Shazia',
    'بشریٰ': 'Bushra', 'بشری': 'Bushra', 'صبا': 'Saba', 'ارم': 'Irum', 'سدرہ': 'Sidra',
    'طاہرہ': 'Tahira', 'انعم': 'Anam', 'فروا': 'Farwa', 'حوریہ': 'Hooria', 'مہرین': 'Mehreen',
    'مومنہ': 'Momina', 'انابیہ': 'Anabia', 'دعا': 'Dua', 'ہانیہ': 'Hania', 'علینہ': 'Aleena',
    'فریحہ': 'Fariha', 'امنہ': 'Amna', 'آمنہ': 'Amna', 'اسماء': 'Asma', 'اسما': 'Asma',
    'فضاء': 'Fiza', 'فضا': 'Fiza', 'کنزہ': 'Kinza', 'مروہ': 'Marwa', 'شفا': 'Shifa',
    'عروج': 'Urooj', 'زہرا': 'Zahra', 'زہرہ': 'Zahra', 'ابیہا': 'Abiha', 'حافظ': 'Hafiz',
    'قاری': 'Qari', 'صاحب': 'Sahib'
}

URDU_CHAR_MAP = {
    'ا': 'a', 'آ': 'aa', 'ب': 'b', 'پ': 'p', 'ت': 't', 'ٹ': 't', 'ث': 's',
    'ج': 'j', 'چ': 'ch', 'ح': 'h', 'خ': 'kh', 'د': 'd', 'ڈ': 'd', 'ذ': 'z',
    'ر': 'r', 'ڑ': 'r', 'ز': 'z', 'ژ': 'z', 'س': 's', 'ش': 'sh', 'ص': 's',
    'ض': 'z', 'ط': 't', 'ظ': 'z', 'ع': 'a', 'غ': 'gh', 'ف': 'f', 'ق': 'q',
    'ک': 'k', 'گ': 'g', 'ل': 'l', 'م': 'm', 'ن': 'n', 'ں': 'n', 'و': 'o',
    'ہ': 'h', 'ھ': 'h', 'ء': '', 'ی': 'i', 'ے': 'e'
}

URDU_DIGITS_MAP = {
    '۰': '0', '۱': '1', '۲': '2', '۳': '3', '۴': '4',
    '۵': '5', '۶': '6', '۷': '7', '۸': '8', '۹': '9'
}

URDU_WORDS_MAP = {
    'فیس': 'fee', 'فیسیں': 'fees', 'کتنی': 'kitni', 'کتنا': 'kitna', 'بتاؤ': 'batao',
    'بتائیں': 'batao', 'بتایں': 'batao', 'بتا': 'batao', 'دکھاؤ': 'batao', 'دیکھو': 'batao',
    'چیک': 'check', 'کلاس': 'class', 'جماعت': 'class', 'گریڈ': 'grade',
    'ایک': 'one', 'دو': 'two', 'تین': 'three', 'چار': 'four', 'پانچ': 'five',
    'چھ': 'six', 'سات': 'seven', 'آٹھ': 'eight', 'نو': 'nine', 'دس': 'ten',
    'نرسری': 'nursery', 'پریپ': 'prep', 'کر': 'kar', 'دو': 'do', 'دیں': 'do',
    'رکھ': 'rakh', 'بدل': 'badal', 'اپڈیٹ': 'update', 'سیٹ': 'set',
    'ڈیفالٹر': 'defaulter', 'ڈیفالٹرز': 'defaulters', 'بقایا': 'arrears', 'بقایاجات': 'arrears',
    'پینڈنگ': 'pending', 'ٹوٹل': 'total', 'کل': 'total', 'بچے': 'bache', 'طالب علم': 'student',
    'کی': 'ki', 'کا': 'ka', 'کے': 'ke', 'میں': 'mein', 'ہے': 'hai', 'ہیں': 'hain', 'کو': 'ko',
    'سے': 'se', 'پر': 'par', 'اور': 'aur', 'والد': 'walid', 'ابو': 'walid', 'باپ': 'walid',
    'فون': 'phone', 'موبائل': 'mobile', 'نمبر': 'number', 'رابطہ': 'rabta', 'نام': 'naam'
}

URDU_VERBAL_AMOUNTS = {
    'پچیس سو': '2500', 'ڈھائی ہزار': '2500', 'دو ہزار': '2000', 'تین ہزار': '3000',
    'ساڑھے تین ہزار': '3500', 'پینتیس سو': '3500', 'چار ہزار': '4000', 'ساڑھے چار ہزار': '4500',
    'پینتالیس سو': '4500', 'پانچ ہزار': '5000', 'چھ ہزار': '6000', 'سات ہزار': '7000',
    'آٹھ ہزار': '8000', 'نو ہزار': '9000', 'دس ہزار': '10000', 'پندرہ سو': '1500',
    'سولہ سو': '1600', 'سترہ سو': '1700', 'اٹھارہ سو': '1800', 'انیس سو': '1900',
    'اکیس سو': '2100', 'بائیس سو': '2200', 'تیئیس سو': '2300', 'چوبیس سو': '2400',
    'چھبیس سو': '2600', 'ستائیس سو': '2700', 'اٹھائیس سو': '2800', 'انتس سو': '2900',
    'بتیس سو': '3200', 'چوتیس سو': '3400', 'چھتیس سو': '3600', 'اڑتیس سو': '3800'
}

def transliterate_urdu_name(text):
    """Converts Urdu Arabic script student name to English Latin letters."""
    if not text:
        return text
    if not any('\u0600' <= ch <= '\u06FF' for ch in text):
        return text
    words = text.split()
    translated_words = []
    for w in words:
        clean_w = re.sub(r'[^\u0600-\u06FF]', '', w)
        if clean_w in URDU_NAME_MAP:
            translated_words.append(URDU_NAME_MAP[clean_w])
        else:
            char_trans = ''.join(URDU_CHAR_MAP.get(c, c) for c in clean_w)
            translated_words.append(char_trans.title() if char_trans else w)
    return ' '.join(translated_words)

def transliterate_urdu_to_roman(text):
    """Converts full Urdu user speech/query into Roman Urdu/English text."""
    if not text:
        return text
    # 1. Verbal amounts
    for phrase, num in URDU_VERBAL_AMOUNTS.items():
        text = text.replace(phrase, num)
    # 2. Digits
    for u_d, e_d in URDU_DIGITS_MAP.items():
        text = text.replace(u_d, e_d)
    # Check if contains Urdu
    if not any('\u0600' <= ch <= '\u06FF' for ch in text):
        return text
    words = text.split()
    out = []
    for w in words:
        clean = re.sub(r'[^\u0600-\u06FF]', '', w)
        if clean in URDU_NAME_MAP:
            out.append(URDU_NAME_MAP[clean])
        elif clean in URDU_WORDS_MAP:
            out.append(URDU_WORDS_MAP[clean])
        elif any('\u0600' <= ch <= '\u06FF' for ch in w):
            char_trans = ''.join(URDU_CHAR_MAP.get(c, c) for c in clean)
            out.append(char_trans.title() if char_trans else w)
        else:
            out.append(w)
    return ' '.join(out)

# Common spelling variants in Pakistani school software
NAME_VARIANTS = {
    'ahmad': ['ahmad', 'ahmed'],
    'ahmed': ['ahmad', 'ahmed'],
    'hassan': ['hassan', 'hasan'],
    'hasan': ['hassan', 'hasan'],
    'hussain': ['hussain', 'husain'],
    'husain': ['hussain', 'husain'],
    'usman': ['usman', 'othman', 'osman'],
    'fatima': ['fatima', 'fatimah'],
    'ayesha': ['ayesha', 'aisha'],
    'aisha': ['ayesha', 'aisha'],
    'saad': ['saad', "sa'ad"],
    'naveed': ['naveed', 'navid'],
    'waseem': ['waseem', 'wasim'],
    'nadeem': ['nadeem', 'nadim'],
    'chaudhry': ['chaudhry', 'choudhry', 'chaudhary'],
    'mehmood': ['mehmood', 'mahmood'],
    'touseef': ['touseef', 'tauseef'],
    'shakeel': ['shakeel', 'shakil'],
    'nafees': ['nafees', 'nafis']
}

def find_students(query, class_name=None, campus_id=None, limit=8):
    """
    Search for students by ID or name, filtered by optional class or campus.
    Fully handles:
    1. Urdu Arabic script (e.g. 'علی رضا', 'محمد حسن', 'بلال لیاقت')
    2. Pakistani name transliteration to English Latin script
    3. 'Muhammad' matching against 'M.' and 'M ' prefixes in database (1,290+ students)
    4. Common spelling variations (Ahmad/Ahmed, Hassan/Hasan, Usman/Othman, etc.)
    5. Clean parameterized SQL queries safe from psycopg % formatting bugs
    6. Intelligent Python-level relevance scoring
    """
    if not query:
        return []
        
    query_str = str(query).strip()
    
    # 1. Automatic Urdu Script to English Transliteration
    if any('\u0600' <= ch <= '\u06FF' for ch in query_str):
        query_str = transliterate_urdu_name(query_str)
        
    conn = get_db_connection()
    sql = """
        SELECT s.id, s.name, s.father_name, s.class, s.monthly_fee, s.opening_arrears, 
               s.phone_number, s.status, s.campus_id, c.name as campus_name
        FROM students s
        LEFT JOIN campuses c ON s.campus_id = c.id
        WHERE 1=1
    """
    params = []
    
    if campus_id:
        sql += " AND s.campus_id = ?"
        params.append(campus_id)
        
    if class_name:
        aliases = get_class_aliases(class_name)
        if aliases:
            conds = []
            for a in aliases:
                conds.append("LOWER(s.class) = ?")
                conds.append("LOWER(s.class) LIKE ?")
                params.extend([a.lower(), f"%{a.lower()}%"])
            sql += f" AND ({' OR '.join(conds)})"
        else:
            sql += " AND (LOWER(s.class) = ? OR LOWER(s.class) LIKE ?)"
            params.extend([class_name.lower(), f"%{class_name.lower()}%"])
            
    if query_str.isdigit():
        sql += " AND (s.id = ? OR CAST(s.id AS TEXT) LIKE ?)"
        params.extend([int(query_str), f"%{query_str}%"])
        sql += " ORDER BY s.name ASC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]
        
    # Word-based name search with Muhammad prefix and spelling variants
    words = query_str.split()
    for w in words:
        w_lower = w.lower().rstrip('.')
        if w_lower in ('muhammad', 'mohammad', 'mohd', 'm'):
            sql += " AND (LOWER(s.name) LIKE ? OR LOWER(s.name) LIKE ? OR LOWER(s.name) LIKE ? OR LOWER(COALESCE(s.father_name, '')) LIKE ? OR LOWER(COALESCE(s.father_name, '')) LIKE ?)"
            params.extend(['m.%', 'm %', '%muhammad%', 'm.%', '%muhammad%'])
        else:
            variants = NAME_VARIANTS.get(w_lower, [w_lower])
            conds = []
            for var in variants:
                conds.append("LOWER(s.name) LIKE ?")
                conds.append("LOWER(COALESCE(s.father_name, '')) LIKE ?")
                params.extend([f"%{var}%", f"%{var}%"])
            sql += f" AND ({' OR '.join(conds)})"
            
    sql += " LIMIT 50"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    
    candidates = [dict(r) for r in rows]
    if not candidates:
        return []
        
    # Intelligent Scoring
    def score_student(s):
        score = 0
        s_name = (s['name'] or '').lower()
        s_father = (s['father_name'] or '').lower()
        q_lower = query_str.lower()
        
        # Exact name match
        if s_name == q_lower:
            score += 100
        elif s_name.startswith(q_lower):
            score += 50
            
        has_m_query = any(w.lower().rstrip('.') in ('muhammad', 'mohammad', 'mohd', 'm') for w in words)
        name_starts_with_m = s_name.startswith('m.') or s_name.startswith('m ') or s_name.startswith('muhammad')
        
        if has_m_query and name_starts_with_m:
            score += 35
        elif has_m_query and not name_starts_with_m:
            score -= 10
            
        for w in words:
            w_l = w.lower().rstrip('.')
            if w_l in ('muhammad', 'mohammad', 'mohd', 'm'):
                continue
            if w_l in s_name:
                score += 25
            elif any(v in s_name for v in NAME_VARIANTS.get(w_l, [])):
                score += 20
            elif w_l in s_father:
                score += 5
                
        if s.get('status') == 'active':
            score += 5
            
        return score
        
    candidates.sort(key=score_student, reverse=True)
    return candidates[:limit]

def get_student_fee_status(student_id):
    from app import get_student_fee_details
    conn = get_db_connection()
    student = conn.execute("""
        SELECT s.*, c.name as campus_name 
        FROM students s 
        LEFT JOIN campuses c ON s.campus_id = c.id 
        WHERE s.id = ?
    """, (student_id,)).fetchone()
    
    if not student:
        conn.close()
        return None
        
    now = datetime.now()
    cur_m_name = MONTH_NUM_TO_NAME.get(now.month, 'March')
    cur_year = now.year
    
    details = get_student_fee_details(student, cur_m_name, cur_year)
    
    # Recent payments
    payments = conn.execute("""
        SELECT month, year, paid_amount, date_paid, payment_mode, reference_no 
        FROM fees 
        WHERE student_id = ? 
        ORDER BY id DESC LIMIT 3
    """, (student_id,)).fetchall()
    conn.close()
    
    res = dict(student)
    res['fee_details'] = details
    res['recent_payments'] = [dict(p) for p in payments]
    res['current_month'] = cur_m_name
    res['current_year'] = cur_year
    return res

def execute_update_student_fee(student_id, new_monthly_fee, executed_by='AI Assistant'):
    """Updates the monthly fee of a student in the database."""
    conn = get_db_connection()
    student = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    if not student:
        conn.close()
        return {'success': False, 'error': f'Student with ID {student_id} not found.'}
        
    old_fee = float(student['monthly_fee'] or 0.0)
    new_fee = float(new_monthly_fee)
    
    cur = conn.cursor()
    cur.execute("UPDATE students SET monthly_fee = ? WHERE id = ?", (new_fee, student_id))
    conn.commit()
    conn.close()
    
    return {
        'success': True,
        'student_id': student_id,
        'student_name': student['name'],
        'student_class': student['class'],
        'old_fee': old_fee,
        'new_fee': new_fee,
        'executed_by': executed_by,
        'timestamp': datetime.now().strftime('%Y-%m-%d %I:%M %p')
    }

def execute_record_fee_payment(student_id, paid_amount, month_name=None, year=None, notes=None, collected_by='AI Assistant', campus_id=None):
    """Records a fee payment for a student."""
    from app import record_tuition_payment
    conn = get_db_connection()
    student = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    if not student:
        conn.close()
        return {'success': False, 'error': f'Student with ID {student_id} not found.'}
        
    now = datetime.now()
    m_name = month_name or MONTH_NUM_TO_NAME.get(now.month, 'March')
    y_val = year or now.year
    p_amount = float(paid_amount)
    c_notes = notes or f"Paid via AI Assistant on {now.strftime('%d-%b-%Y')}"
    
    summary = record_tuition_payment(
        conn=conn,
        student=student,
        start_month_name=m_name,
        start_year=y_val,
        paid_amount=p_amount,
        payment_mode='Cash',
        notes=c_notes,
        collected_by=collected_by
    )
    conn.commit()
    conn.close()
    
    return {
        'success': True,
        'student_id': student_id,
        'student_name': student['name'],
        'student_class': student['class'],
        'paid_amount': p_amount,
        'month': m_name,
        'year': y_val,
        'summary': summary
    }

def get_class_defaulters(class_name=None, campus_id=None, limit=10):
    """Get list of students with outstanding dues."""
    from app import get_student_fee_details
    conn = get_db_connection()
    sql = "SELECT s.*, c.name as campus_name FROM students s LEFT JOIN campuses c ON s.campus_id = c.id WHERE s.status = 'active'"
    params = []
    
    if campus_id:
        sql += " AND s.campus_id = ?"
        params.append(campus_id)
        
    if class_name:
        aliases = get_class_aliases(class_name)
        if aliases:
            conds = []
            for a in aliases:
                conds.append("LOWER(s.class) = ?")
                conds.append("LOWER(s.class) LIKE ?")
                params.extend([a.lower(), f"%{a.lower()}%"])
            sql += f" AND ({' OR '.join(conds)})"
        else:
            sql += " AND (LOWER(s.class) = ? OR LOWER(s.class) LIKE ?)"
            params.extend([class_name.lower(), f"%{class_name.lower()}%"])
        
    sql += " ORDER BY s.class, s.name"
    students = conn.execute(sql, params).fetchall()
    
    now = datetime.now()
    cur_m = MONTH_NUM_TO_NAME.get(now.month, 'March')
    cur_y = now.year
    
    student_ids = [s['id'] for s in students]
    fees_map = {sid: [] for sid in student_ids}
    if student_ids:
        placeholders = ','.join(['?'] * len(student_ids))
        all_fees = conn.execute(
            f"SELECT student_id, month, year, paid_amount, notes FROM fees WHERE student_id IN ({placeholders})",
            student_ids
        ).fetchall()
        for f in all_fees:
            fees_map[f['student_id']].append(f)
            
    conn.close()
    
    defaulters = []
    for s in students:
        details = get_student_fee_details(s, cur_m, cur_y, payments=fees_map.get(s['id'], []))
        remaining = details.get('remaining_payable', 0.0)
        if remaining > 0:
            defaulters.append({
                'id': s['id'],
                'name': s['name'],
                'class': s['class'],
                'father_name': s['father_name'],
                'phone': s['phone_number'],
                'monthly_fee': float(s['monthly_fee'] or 0),
                'arrears': details.get('arrears', 0.0),
                'total_due': remaining
            })
            if len(defaulters) >= limit:
                break
                
    return defaulters

def get_campus_stats(campus_id=None):
    """Get campus statistical summary."""
    conn = get_db_connection()
    where_sql = ""
    params = []
    if campus_id:
        where_sql = " WHERE campus_id = ?"
        params = [campus_id]
        
    total_students = conn.execute(f"SELECT COUNT(*) FROM students {where_sql}", params).fetchone()[0]
    active_students = conn.execute(f"SELECT COUNT(*) FROM students WHERE (status = 'active' OR status IS NULL) AND LOWER(class) != 'graduate' {' AND campus_id = ?' if campus_id else ''}", params).fetchone()[0]
    classes = conn.execute(f"SELECT COUNT(DISTINCT class) FROM students {where_sql}", params).fetchone()[0]
    
    # Monthly fee collection this month
    now = datetime.now()
    cur_m = MONTH_NUM_TO_NAME.get(now.month, 'March')
    cur_y = now.year
    fee_col_sql = "SELECT COALESCE(SUM(paid_amount), 0) FROM fees WHERE month = ? AND year = ?"
    col_params = [cur_m, cur_y]
    if campus_id:
        fee_col_sql += " AND campus_id = ?"
        col_params.append(campus_id)
    collected_month = conn.execute(fee_col_sql, col_params).fetchone()[0]
    
    conn.close()
    return {
        'total_students': total_students,
        'active_students': active_students,
        'total_classes': classes,
        'current_month': cur_m,
        'current_year': cur_y,
        'collected_this_month': float(collected_month or 0.0)
    }

def get_campuses_summary():
    """Returns list of campuses with active student counts (excluding graduates)."""
    conn = get_db_connection()
    try:
        campuses = conn.execute("SELECT id, name FROM campuses ORDER BY id").fetchall()
        result = []
        for c in campuses:
            count = conn.execute("SELECT COUNT(*) FROM students WHERE campus_id = ? AND (status = 'active' OR status IS NULL) AND LOWER(class) != 'graduate'", (c['id'],)).fetchone()[0]
            result.append({
                'id': c['id'],
                'name': c['name'],
                'student_count': count
            })
        return result
    finally:
        conn.close()

def get_classes_summary(campus_id=None):
    """Returns list of distinct classes with student counts."""
    conn = get_db_connection()
    try:
        where_sql = "WHERE (status = 'active' OR status IS NULL) AND LOWER(class) != 'graduate'"
        params = []
        if campus_id:
            where_sql += " AND campus_id = ?"
            params.append(campus_id)
        rows = conn.execute(f"SELECT class, COUNT(*) as count FROM students {where_sql} GROUP BY class ORDER BY count DESC", params).fetchall()
        return [{'class': r['class'], 'count': r['count']} for r in rows]
    finally:
        conn.close()

# -------------------------------------------------------------
# HYBRID INTELLIGENCE: RULE-BASED INTENT PARSER (OFFLINE READY)
# -------------------------------------------------------------



def parse_with_rule_engine(message, campus_id=None, user_session=None, history=None):
    if not message or not message.strip():
        return {'text': 'Aap ka koi sawal ya command nahi mila. Barah-e-karam kuch type karein.'}

    msg = message.strip()
    raw = transliterate_urdu_to_roman(msg.lower())

    # 0. Conversational Chit-Chat & Greetings
    # Check for praise / compliments
    has_praise = any(p in raw for p in ['very good', 'shukriya', 'shukria', 'thanks', 'thank you', 'great', 'zabardast', 'nice', 'boht acha', 'bohot acha', 'boht khoob', 'good job', 'well done', 'wah', 'mashallah', 'masha allah'])
    polite_prefix = "Boht shukriya! 😊 " if has_praise else ""

    # Pure compliment/gratitude without other questions
    clean_praise = re.sub(r'\b(very good|shukriya|shukria|thanks|thank you|great|zabardast|nice|boht acha|bohot acha|boht khoob|good job|well done|wah|ok|okay|theek hai|theek he|theek h|ji|hanji|jee)\b', '', raw).strip()
    if has_praise and len(clean_praise.split()) <= 1:
        return {
            'text': "Boht shukriya! ❤️ Main aapka AI Copilot hoon aur hamesha aapki madad ke liye tayar hoon.\n\nAap school ke kisi student ki fee check/update karwana chahte hain, ya campuses aur stats dekhna chahte hain?"
        }

    # Greeting & How-are-you detection
    if any(k in raw for k in ['salam', 'assalam', 'aoa', 'kya hal', 'kaise ho', 'kaisi ho', 'kese ho', 'kya haal', 'sunao', 'kya chal', 'hello', 'hi', 'hey']):
        return {
            'text': f"Walaikum Assalam! Main bilkul theek hoon, alhamdulillah! 😊\n\n"
                    f"Aap sunayein, school ka kaam kaisa chal raha hai? Aaj kis student ya class ki fee check ya update karni hai?"
        }

    # Identity / Who are you / Chatbot questions
    if any(k in raw for k in ['tum kaun ho', 'tum kon ho', 'kaun ho', 'kon ho', 'chatbot', 'ai ho', 'robot', 'naam kya', 'kya cheez ho', 'who are you']):
        return {
            'text': f"Main aapka **School AI Copilot & Chatbot** hoon! 🤖✨\n\n"
                    f"Main aapki baaton ka jawab bhi deta hoon aur school system par direct actions bhi perform karta hoon:\n\n"
                    f"• 🏫 **Campuses:** *'Mery pas kitny campus hain?'*\n"
                    f"• 💰 **Fee Update:** *'Class 2 ke Ali Raza ki fee 2500 kar do'*\n"
                    f"• 🔍 **Fee Status:** *'Ali Raza (Class 2) ki fee kitni hai?'*\n"
                    f"• 📋 **Defaulters:** *'Class 5 ke defaulters dikhao'*\n"
                    f"• 📊 **Campus Stats:** *'Total kitne bache enrolled hain?'*\n"
                    f"• 👨‍👦 **Family Details:** *'Ali Raza ke walid ka naam kya hai?'*\n\n"
                    f"Aap Roman Urdu, Urdu ya English me bol kar ya likh kar koi bhi instruction de sakte hain."
        }

    # Appreciation & Politeness detection
    if any(k in raw for k in ['theek hai', 'theek h', 'shukriya', 'shukria', 'thanks', 'thank you', 'zabardast', 'good', 'acha', 'bohat khoob', 'great', 'ok', 'okay']) and len(raw.split()) <= 4:
        return {
            'text': f"Bohat shukriya! Agar koi aur kaam ya maloomat chahiye ho to bila-jhijhak batayein, main hamesha hazir hoon. 👍"
        }

    # Current Date / Time query
    if any(k in raw for k in ['aaj kya date', 'aaj ki date', 'aaj kya tareekh', 'aaj ki tareekh', 'today date', 'current date', 'aaj konsa din', 'aaj ka din']):
        today_str = datetime.now().strftime("%d %B %Y (%A)")
        return {
            'text': f"📅 Aaj ki date **{today_str}** hai."
        }

    # School Name query
    if any(k in raw for k in ['school ka naam', 'school name', 'campus name', 'ye konsa school']):
        conn = get_db_connection()
        row = conn.execute("SELECT value FROM settings WHERE key = 'school_name'").fetchone()
        conn.close()
        s_name = row['value'] if row and row['value'] else "Allied School"
        return {
            'text': f"🏫 Hamare school ka naam **{s_name}** hai."
        }

    # Capabilities / Help
    if any(k in raw for k in ['kya kar sakte', 'kya kr skty', 'what can you do', 'madad', 'help', 'kaam kya hai', 'features', 'guideline']):
        return {
            'text': f"Main aapka **School AI Copilot** hoon! 🤖\n\n"
                    f"Aap mujh se aam bol chal (Roman Urdu, Urdu ya English) me baat bhi kar sakte hain aur school ke kaam bhi karwa sakte hain:\n\n"
                    f"1. 🏫 **Campuses:** *'Kitne campus hain?'*\n"
                    f"2. 💰 **Fee Update:** *'Class 2 ke Ali Raza ki fee 2500 kar do'*\n"
                    f"3. 🔍 **Fee Status:** *'Ali Raza (Class 2) ki fee kitni hai?'*\n"
                    f"4. 📋 **Defaulters:** *'Class 5 ke defaulters dikhao'*\n"
                    f"5. 📊 **Campus Stats:** *'Total kitne bache enrolled hain?'*\n"
                    f"6. 📞 **Student Details:** *'Ali Raza ke walid ka naam kya hai?'*\n\n"
                    f"Aap type kar ke ya mic se bol kar jo chahein pooch sakte hain!"
        }

    # Check for Campus / Branch inquiry
    # e.g. "kitny campus he", "mery pas kitny campus he", "campuses dikhao", "branches", "active campus"
    is_campus_query = any(k in raw for k in [
        'campus', 'campuses', 'branch', 'branches', 
        'kitny campus', 'kitne campus', 'kitni branch', 'kitni branches',
        'mery pas kitny', 'mere pas kitne', 'total campus', 'total branch',
        'kon se campus', 'konsa campus', 'kon kon se campus'
    ])
    if is_campus_query:
        campuses = get_campuses_summary()
        total_students = sum(c['student_count'] for c in campuses)
        rows = []
        for i, c in enumerate(campuses, 1):
            rows.append(f"{i}. 🏛️ **{c['name']}** (ID: {c['id']}) — **{c['student_count']:,}** Active Students")
            
        return {
            'text': f"{polite_prefix}Aapke school management system me is waqt total **{len(campuses)} campuses** registered hain:\n\n" +
                    "\n".join(rows) +
                    f"\n\n📊 **Overall School Strength:** **{total_students:,}** Active Students across all branches.\n" +
                    f"💡 *Tip:* Aap screen ke upar header dropdown se kisi bhi campus me switch kar ke uska record dekh sakte hain!"
        }

    # Check for Classes list / count
    is_classes_query = any(k in raw for k in ['kitni classes', 'kitni class', 'classes list', 'classes dikhao', 'konsi class', 'classes name', 'total classes', 'classes kitni'])
    if is_classes_query:
        classes = get_classes_summary(campus_id=campus_id)
        total_in_scope = sum(c['count'] for c in classes)
        rows = [f"• **Class {c['class']}**: {c['count']} Students" for c in classes]
        return {
            'text': f"{polite_prefix}School me is waqt **{len(classes)} classes** enrolled hain:\n\n" +
                    "\n".join(rows) +
                    f"\n\n👥 **Total Enrolled Students:** {total_in_scope:,}"
        }

    # Feature guidance: Vouchers print
    if any(k in raw for k in ['voucher', 'challan', 'chalan']) and any(k in raw for k in ['print', 'kaise', 'kahan', 'kesy', 'batao', 'tareeqa', 'how', 'generate']):
        return {
            'text': f"{polite_prefix}📌 **Fee Vouchers Print Karne Ka Tareeqa:**\n\n"
                    f"1. Left menu se **Voucher Studio** par click karein.\n"
                    f"2. **Single Student Challan:** Student search karein aur 'Print Challan' dabayein (3-part bank challan print hoga).\n"
                    f"3. **Class Batch Challans:** 'Class Wise Batch Print' select karein, class choose karein aur puri class ke challans aik sath print karein!\n\n"
                    f"💡 Kisi student ki fee check karni ho to likhein: *'Ali Raza ki fee kitni hai'*."
        }

    # Feature guidance: Fee entry
    if any(k in raw for k in ['fee jama', 'fee entry', 'fees kaise', 'fee register', 'fee kaise enter']):
        return {
            'text': f"{polite_prefix}💰 **Fee Record / Entry Ka Tareeqa:**\n\n"
                    f"1. Left menu se **Class Fee Register** par click karein.\n"
                    f"2. Class aur Billing Month select karein.\n"
                    f"3. Student ke samne 'Fee Entry' button dabayein, amount enter karein aur Save karein!\n\n"
                    f"💡 Main bhi kisi student ki monthly fee update kar sakta hoon (jaise: *'Ali Raza ki fee 2500 kar do'*)."
        }

    # 1. Normalize typos and common colloquial variations
    # Replace typos for 'batao' (e.g. 'tbtao', 'btao', 'btayein', 'batao', 'dikhao')
    raw = re.sub(r'\b(tbtao|btao|btaon|btaen|btayein|btaye|btado|batao|batana|bataye|bataen|dikhao|dekho|check|check karo|maloom)\b', 'batao', raw)
    # Replace variants of 'kar do'
    raw = re.sub(r'\b(krna|krni|karni|krdo|kardo|kr do|kar do|kar dain|kar dein|kardein|kardain|set karo|rakh do|bana do)\b', 'kar do', raw)
    # Remove filler / colloquial helper clauses
    raw = re.sub(r'\b(ma he|me he|mai he|me h|ma h|mein h|mein he|mein hai|parhta he|parta he|parhta ha|parhta hai|parhti hai|parhta|parhti|parhte)\b', ' ', raw)
    raw = re.sub(r'\b(ha|he|hai|hain|h|tha|the|thi)\b', ' ', raw)
    
    # 2. Extract explicit ID (e.g. "ID 4042", "Roll No: 12", "#4042")
    explicit_id_match = re.search(r'\b(?:id|roll\s*no\.?|std|student\s*id|#)\s*[:=]?\s*(\d+)\b', raw)
    explicit_id = int(explicit_id_match.group(1)) if explicit_id_match else None
    
    # Contextual Pronoun check: e.g. "iski fee 2500 kardo", "isy 3000 kar do"
    has_pronoun = any(k in raw for k in ['iski', 'iska', 'iske', 'uske', 'uski', 'uska', 'isy', 'usey', 'isko', 'usko'])
    if not explicit_id and has_pronoun and user_session and user_session.get('ai_last_student_id'):
        explicit_id = user_session.get('ai_last_student_id')
    raw = re.sub(r'\b(us ki|uski|uske|iske|iska|uska|un ki|unki|isy|usey|isko|usko)\b', ' ', raw)

    # 3. Extract Class
    class_match = re.search(r'\b(?:class|grade|jamaat)\s*([0-9a-zA-Z]+)\b', raw)
    if not class_match:
        class_match = re.search(r'\b([0-9]+)(?:st|nd|rd|th)?\s*(?:class|grade|jamaat)\b', raw)
    if not class_match:
        class_match = re.search(r'\b(nursery|prep|playgroup|play group|pg|one|two|three|four|five|six|seven|eight|nine|ten)\b', raw)
    class_hint = class_match.group(1) if class_match else None
    
    # 4. Check for Student Count / Strength in a class
    # e.g.: "class 2 me kitne bache hain", "class 5 student count"
    if class_hint and any(k in raw for k in ['kitne bache', 'kitne student', 'total bache', 'total student', 'strength', 'count']):
        conn = get_db_connection()
        aliases = get_class_aliases(class_hint)
        conds = ["LOWER(class) = ? OR LOWER(class) LIKE ?" for _ in aliases]
        c_params = []
        for a in aliases:
            c_params.extend([a.lower(), f"%{a.lower()}%"])
        c_sql = f"SELECT COUNT(*) FROM students WHERE status = 'active' AND ({' OR '.join(conds)})"
        if campus_id:
            c_sql += " AND campus_id = ?"
            c_params.append(campus_id)
        count = conn.execute(c_sql, c_params).fetchone()[0]
        conn.close()
        return {
            'text': f"📚 **Class {class_hint.title()}:** Is waqt is class me total **{count}** active students enrolled hain."
        }
    
    # 5. Check Defaulters List
    # e.g.: "defaulters dikhao", "class 5 ke defaulters", "pending fees"
    if any(k in raw for k in ['defaulter', 'defaulters', 'pending fee', 'baqaya', 'arrear', 'fees pending']):
        defaulters = get_class_defaulters(class_name=class_hint, campus_id=campus_id, limit=8)
        if not defaulters:
            target = f"Class {class_hint.title()}" if class_hint else "selected campus"
            return {'text': f"🎉 Mubarak ho! **{target}** me koi pending fee defaulters nahi hain."}
            
        rows_text = []
        for d in defaulters:
            rows_text.append(f"• **{d['name']}** (Class {d['class']}, ID: {d['id']}) - Total Due: **Rs. {d['total_due']:,.0f}** (Arrears: Rs. {d['arrears']:,.0f})")
            
        return {
            'text': f"📋 **Fee Defaulters List{' (Class ' + class_hint.title() + ')' if class_hint else ''}:**\n\n" + "\n".join(rows_text) + "\n\nIn students se fee collection ke liye aap Voucher Studio ya Fee Register use kar sakte hain."
        }

    # 6. Campus Summary / Overview
    # e.g.: "summary", "stats", "total student", "kitne bache", "collection"
    if any(k in raw for k in ['summary', 'stats', 'total student', 'kitne bache', 'collection', 'campus overview']):
        stats = get_campus_stats(campus_id=campus_id)
        return {
            'text': f"📊 **Campus Overview & Stats ({stats['current_month']} {stats['current_year']}):**\n\n"
                    f"• **Total Students Enrolled:** {stats['total_students']:,}\n"
                    f"• **Active Students:** {stats['active_students']:,}\n"
                    f"• **Total Classes:** {stats['total_classes']}\n"
                    f"• **Tuition Fee Collected This Month:** **Rs. {stats['collected_this_month']:,.0f}**"
        }

    # 7. Update Student Fee
    # e.g.: "Ali ki fee 4500 kar do", "Class 2 ke Ali Raza ki fee 3000 kar do", "ID 4042 fee 2000 set karo"
    is_update_intent = ('kar do' in raw or any(k in raw for k in ['update', 'set', 'change', 'badal', 'rakh'])) and any(c.isdigit() for c in raw)
    if is_update_intent:
        all_numbers = [int(n) for n in re.findall(r'\b\d+\b', raw)]
        new_amount = None
        target_student_id = explicit_id

        if explicit_id:
            for num in all_numbers:
                if num != explicit_id and num >= 100:
                    new_amount = float(num)
                    break
            if not new_amount and all_numbers:
                if all_numbers[-1] != explicit_id:
                    new_amount = float(all_numbers[-1])
        else:
            fee_candidates = [n for n in all_numbers if n >= 100]
            if fee_candidates:
                new_amount = float(fee_candidates[-1])

        if new_amount is not None:
            candidates = []
            if target_student_id:
                candidates = find_students(target_student_id, campus_id=campus_id)
            else:
                # Clean name: remove amount and keywords
                clean_name = raw
                clean_name = re.sub(r'\b' + str(int(new_amount)) + r'\b', ' ', clean_name)
                if class_match:
                    clean_name = clean_name[:class_match.start()] + ' ' + clean_name[class_match.end():]
                clean_name = re.sub(r'[^a-zA-Z0-9\s]', ' ', clean_name)
                clean_name = re.sub(
                    r'\b(ki|ka|ke|k|fee|fees|monthly_fee|kar|do|to|ko|se|is|rs|pkr|class|grade|jamaat|set|update|change|badal|bana|rakh|karo|batao)\b',
                    ' ',
                    clean_name
                ).strip()
                clean_name = ' '.join(clean_name.split())

                if clean_name:
                    candidates = find_students(clean_name, class_name=class_hint, campus_id=campus_id)
                    if not candidates and len(clean_name.split()) > 1:
                        candidates = find_students(clean_name.split()[0], class_name=class_hint, campus_id=campus_id)

            if len(candidates) == 1:
                s = candidates[0]
                if user_session is not None:
                    user_session['ai_last_student_id'] = s['id']
                    user_session['ai_last_student_name'] = s['name']
                old_fee = float(s['monthly_fee'] or 0.0)
                return {
                    'text': f"Maine student **{s['name']}** (Class: {s['class']}, Roll No: {s['id']}) ko dhoond liya hai.\n\n"
                            f"📌 **Current Monthly Fee:** Rs. {old_fee:,.0f}\n"
                            f"✨ **New Requested Fee:** Rs. {new_amount:,.0f}\n\n"
                            f"Kya aap is student ki monthly fee update karna chahte hain? Neeche button par click kar ke confirm karein:",
                    'action_proposal': {
                        'type': 'update_fee',
                        'student_id': s['id'],
                        'student_name': s['name'],
                        'student_class': s['class'],
                        'old_fee': old_fee,
                        'new_fee': new_amount,
                        'label': f"Confirm Fee Update for {s['name']} (Rs. {old_fee:,.0f} ➔ Rs. {new_amount:,.0f})"
                    }
                }
            elif len(candidates) > 1:
                options = "\n".join([f"• ID {c['id']}: **{c['name']}** (Class: {c['class']}, Father: {c['father_name'] or 'N/A'}, Current Fee: Rs. {float(c['monthly_fee'] or 0):,.0f})" for c in candidates[:6]])
                return {
                    'text': f"Is naam se aik se zyada students mile hain:\n\n{options}\n\n"
                            f"Barah-e-karam student ka ID ya Class sath batayein (jaise: *'ID {candidates[0]['id']} ki fee {int(new_amount)} kar do'*)."
                }
            else:
                return {
                    'text': f"⚠️ Student system me nahi mila. Barah-e-karam sahi student naam ya ID darj karein (jaise: *'ID 123 ki fee {int(new_amount)} kar do'*)."
                }

    # 8. Check Student Fee & Profile
    # Only search if there is actual student or fee intent:
    has_student_intent = bool(explicit_id) or bool(class_hint) or any(k in raw for k in [
        'fee', 'fees', 'arrear', 'arrears', 'baqaya', 'due', 'challan', 
        'walid', 'father', 'phone', 'mobile', 'details', 'record', 'profile', 
        'parhta', 'student', 'bache', 'roll no', 'ledger', 'balance'
    ])

    clean_name = raw
    if class_match:
        clean_name = clean_name[:class_match.start()] + ' ' + clean_name[class_match.end():]
    clean_name = re.sub(r'[^a-zA-Z0-9\s]', ' ', clean_name)
    clean_name = re.sub(
        r'\b(ki|ka|ke|k|fee|fees|status|check|karo|batao|details|info|of|kitni|hai|he|h|kya|class|grade|jamaat|roll|no|std|walid|father|phone|number|mobile|naam|name)\b',
        ' ',
        clean_name
    ).strip()
    clean_name = ' '.join(clean_name.split())

    # Only run student search if explicit ID or explicit student intent with reasonable name length
    if explicit_id or (clean_name and has_student_intent and len(clean_name.split()) <= 4):
        target_q = explicit_id if explicit_id else clean_name
        candidates = find_students(target_q, class_name=class_hint, campus_id=campus_id)
        if len(candidates) == 1:
            s_cand = candidates[0]
            if user_session is not None:
                user_session['ai_last_student_id'] = s_cand['id']
                user_session['ai_last_student_name'] = s_cand['name']

            # If asking specifically about father or phone
            if any(k in raw for k in ['walid', 'father', 'baap', 'parent']):
                return {
                    'text': f"👨‍👦 Student **{s_cand['name']}** (Class: {s_cand['class']}, Roll No: {s_cand['id']}) ke walid ka naam **{s_cand['father_name'] or 'N/A'}** hai."
                }
            if any(k in raw for k in ['phone', 'mobile', 'rabta', 'number', 'contact']):
                return {
                    'text': f"📞 Student **{s_cand['name']}** (Class: {s_cand['class']}, Roll No: {s_cand['id']}) ka contact number **{s_cand['phone_number'] or 'Not Provided'}** hai."
                }

            status_info = get_student_fee_status(s_cand['id'])
            if status_info:
                fd = status_info['fee_details']
                return {
                    'text': f"🎓 **Student Fee Profile:**\n\n"
                            f"• **Name:** {status_info['name']} (ID: {status_info['id']})\n"
                            f"• **Class:** {status_info['class']} | **Father:** {status_info['father_name'] or 'N/A'}\n"
                            f"• **Monthly Tuition Fee:** Rs. {fd['monthly_fee']:,.0f}\n"
                            f"• **Past Arrears:** Rs. {fd['arrears']:,.0f}\n"
                            f"• **Current Month Due ({status_info['current_month']}):** Rs. {fd['current_month_due']:,.0f}\n"
                            f"• **Paid This Month:** Rs. {fd['paid_this_month']:,.0f}\n"
                            f"• **Total Remaining Payable:** **Rs. {fd['remaining_payable']:,.0f}**\n\n"
                            f"💡 Agar aap is student ki fee badalna chahte hain to keh sakte hain:\n"
                            f"*'{status_info['name']} ki fee 2500 kar do'*"
                }
        elif len(candidates) > 1:
            options = "\n".join([f"• ID {c['id']}: **{c['name']}** (Class: {c['class']}, Father: {c['father_name'] or 'N/A'}, Fee: Rs. {float(c['monthly_fee'] or 0):,.0f})" for c in candidates[:6]])
            return {
                'text': f"Is naam se aik se zyada students mile hain:\n\n{options}\n\n"
                        f"Barah-e-karam student ka ID sath batayein (jaise: *'ID {candidates[0]['id']} ki fee batao'*)."
            }
        elif clean_name and has_student_intent:
            target_desc = f"'{clean_name}'" + (f" (Class {class_hint.title()})" if class_hint else "")
            return {'text': f"{polite_prefix}⚠️ Student **{target_desc}** system me nahi mila. Barah-e-karam student ka naam ya ID verify karein."}

    # 9. Natural Conversational Fallback (Just like ChatGPT)
    return {
        'text': f"{polite_prefix}Main aapka **School AI Copilot** hoon! 🤖\n\n"
                f"Main aapke school system me yeh tamaam kaam kar sakta hoon:\n\n"
                f"• 🏫 **Campuses:** *'Mery pas kitny campus hain?'* ya *'Campuses list'*\n"
                f"• 🔍 **Student Fee Inquiry:** *'Ali Raza (Class 2) ki fee kitni hai?'*\n"
                f"• ✏️ **Fee Update:** *'Class 2 ke Ali Raza ki fee 2500 kar do'*\n"
                f"• 📋 **Defaulters List:** *'Class 2 ke defaulters dikhao'*\n"
                f"• 📚 **Classes & Strength:** *'Total kitne bache hain?'* ya *'Kitni classes hain?'*\n"
                f"• 🖨️ **Help & Guidance:** *'Voucher kaise print karein?'*\n\n"
                f"Barah-e-karam batayein main aapki kya madad karoon?"
    }

# -------------------------------------------------------------
# GEMINI AI INTEGRATION (LLM WITH FUNCTION CALLING)
# -------------------------------------------------------------

GEMINI_TOOLS_DECLARATION = [
    {
        "name": "find_students",
        "description": "Find and search students by name, ID, or class. IMPORTANT: All student names, father names, and classes in the database are stored in English/Latin letters (e.g. 'Ali Raza', 'M. Hassan', 'Bilal Liaqat', 'Fatima', 'Class 2'). If the user speaks or writes in Urdu script (e.g. 'علی رضا', 'محمد حسن', 'بلال لیاقت', 'فاطمہ'), transliterate the student name into English letters in the query parameter (e.g. query='Ali Raza', query='Muhammad Hassan', query='Bilal Liaqat').",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "Student name in English Latin letters (e.g. 'Ali Raza', 'Muhammad Hassan', 'Bilal Liaqat') or numeric student ID."},
                "class_name": {"type": "STRING", "description": "Optional class name or grade e.g. 'Class 5', 'Nursery', '10'."}
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_student_fee_status",
        "description": "Get detailed fee breakdown (monthly fee, arrears, balance, payments) for a student.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "student_id": {"type": "INTEGER", "description": "The exact numeric student ID."}
            },
            "required": ["student_id"]
        }
    },
    {
        "name": "propose_update_student_fee",
        "description": "Propose changing the monthly fee of a student. This creates a confirmation card for the admin.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "student_id": {"type": "INTEGER", "description": "Student numeric ID."},
                "new_monthly_fee": {"type": "NUMBER", "description": "The new monthly tuition fee amount in PKR (e.g. 4500)."}
            },
            "required": ["student_id", "new_monthly_fee"]
        }
    },
    {
        "name": "get_class_defaulters",
        "description": "Get a list of fee defaulters with pending arrears.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "class_name": {"type": "STRING", "description": "Optional class name filter like 'Class 6'."}
            }
        }
    },
    {
        "name": "get_campus_stats",
        "description": "Get statistical summary and fee collection total for the campus.",
        "parameters": {
            "type": "OBJECT",
            "properties": {}
        }
    },
    {
        "name": "get_campuses_summary",
        "description": "Get the list of all school campuses/branches, total campus count, and student count per campus.",
        "parameters": {
            "type": "OBJECT",
            "properties": {}
        }
    }
]

SYSTEM_INSTRUCTION = """You are the intelligent School Admin AI Copilot for Alliedian School Management System.
You assist school operators, principals, and accountants with everything: students, fees, arrears, vouchers, campus stats, advice, and general conversation.
Language & Tone:
- You understand and speak fluent Urdu, Roman Urdu, and English naturally, just like ChatGPT/Antigravity.
- Understand all Pakistani Urdu and Roman Urdu slang, informal phrasing, and typos (e.g. 'esy work ni krta', 'kya hal he', 'batao', 'tbtao', 'kr do', 'ma he', 'mujhe samjhao').
- Always be polite, warm, and highly intelligent. Use Pakistani currency formatting (e.g., Rs. 4,500).

Urdu Voice & Script Transliteration:
- CRITICAL DATABASE RULE: All student names in the school database are stored in English Latin letters (e.g. 'Ali Raza', 'M. Hassan', 'Fatima', 'Bilal Liaqat', 'Play Group').
- When the user speaks or writes in Urdu script (e.g., 'علی رضا کی فیس کتنی ہے' or 'محمد حسن کا ریکارڈ دکھاؤ' or 'بلال کی فیس ۲۵۰۰ کر دو'):
  1. Transliterate all Urdu student names into English Latin script when calling tools (e.g. query='Ali Raza', query='Muhammad Hassan', query='Bilal Liaqat').
  2. Note that 'محمد' is often recorded as 'M.' or 'M ' in student names (e.g. 'M. Hassan', 'M. Ahmad').
  3. You can reply back to the user in fluent Urdu, Roman Urdu, or English matching the user's conversational language!

Capabilities:
1. Conversational & General Help: You can answer ANY question, general queries, school advice, guidance on how to manage admissions, fees, accounting, or casual chat.
2. Database Actions:
   - When asked to search a student or check fee, call `find_students` or `get_student_fee_status`.
   - When asked to change or update a fee, call `find_students` or `propose_update_student_fee`.
   - When asked for fee defaulters, call `get_class_defaulters`.
   - When asked for stats or fee collection, call `get_campus_stats`.
   - When asked about campuses/branches, call `get_campuses_summary`.

School Context:
- 7 Campuses: Main Campus Okara (ID 2), 28 Campus (ID 1), 44_2l campus (ID 3), 21_GD campus (ID 5), Firdous Town Campus (ID 7), 44_GD Campus (ID 6), Gobindpur Campus (ID 4). Total active students: ~4,500.
- Classes: Play Group, Nursery, Prep, One to Ten.
- Key modules: Student Registry, Fee Entry & Register, Voucher Studio (bank challans), Defaulters Ledger, Class Promotion.
"""

_GEMINI_COOLDOWN_UNTIL = 0

def call_gemini_api(api_key, user_message, campus_id=None, history=None, user_session=None):
    """
    Calls Gemini REST API with multi-turn conversation history, zero thinking budget
    for lightning-fast responses (<1.5s), reliable model fallback chain, and instant tool resolution.
    """
    global _GEMINI_COOLDOWN_UNTIL
    
    now_ts = datetime.now().timestamp()
    if now_ts < _GEMINI_COOLDOWN_UNTIL:
        return None

    # Fast and reliable model fallback chain: flash-lite is ultra-fast (<1.5s) and avoids 503 high demand
    models = ['gemini-3.5-flash-lite', 'gemini-3.1-flash-lite', 'gemini-3.8-flash']
    
    # Build contents with previous chat history
    gemini_contents = []
    if history and isinstance(history, list):
        for h in history[-8:]:
            r = "user" if h.get('role') == 'user' else "model"
            txt = h.get('content', '')
            if txt and isinstance(txt, str):
                gemini_contents.append({
                    "role": r,
                    "parts": [{"text": txt}]
                })
                
    gemini_contents.append({
        "role": "user",
        "parts": [{"text": user_message}]
    })
    
    headers = {"Content-Type": "application/json"}
    
    for model_name in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        payload = {
            "contents": list(gemini_contents),
            "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
            "tools": [{"functionDeclarations": GEMINI_TOOLS_DECLARATION}]
        }
        
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
            with urllib.request.urlopen(req, timeout=3.5) as response:
                res_data = json.loads(response.read().decode('utf-8'))
                candidates = res_data.get('candidates', [])
                if not candidates:
                    continue
                    
                model_content = candidates[0].get('content', {})
                parts = model_content.get('parts', [])
                
                text_response = ""
                action_proposal = None
                has_function_call = False
                fn_name = None
                fn_args = {}
                
                for part in parts:
                    if 'text' in part:
                        text_response += part['text'] + "\n"
                    if 'functionCall' in part:
                        has_function_call = True
                        fn = part['functionCall']
                        fn_name = fn.get('name')
                        fn_args = fn.get('args', {})
                
                # If Gemini called a tool function, execute tool with fast resolution
                if has_function_call and fn_name:
                    if fn_name == 'find_students':
                        students = find_students(fn_args.get('query'), class_name=fn_args.get('class_name'), campus_id=campus_id)
                        if students and len(students) == 1:
                            s = students[0]
                            if user_session is not None:
                                user_session['ai_last_student_id'] = s['id']
                                user_session['ai_last_student_name'] = s['name']
                                
                            # Check if user wanted to update fee directly in this request
                            amounts = [int(n) for n in re.findall(r'\b\d+\b', user_message) if int(n) >= 100]
                            has_update = any(k in user_message.lower() for k in ['kar do', 'kr do', 'update', 'set', 'badal', 'change', 'karo', 'rakh'])
                            if has_update and amounts:
                                old_fee = float(s['monthly_fee'] or 0.0)
                                new_fee = float(amounts[-1])
                                return {
                                    'text': f"Maine student **{s['name']}** (Class: {s['class']}, Roll No: {s['id']}) ko dhoond liya hai.\n\n"
                                            f"📌 **Current Monthly Fee:** Rs. {old_fee:,.0f}\n"
                                            f"✨ **New Requested Fee:** Rs. {new_fee:,.0f}\n\n"
                                            f"Kya aap is student ki fee update karna chahte hain? Neeche confirmation button dabayein:",
                                    'action_proposal': {
                                        'type': 'update_fee',
                                        'student_id': s['id'],
                                        'student_name': s['name'],
                                        'student_class': s['class'],
                                        'old_fee': old_fee,
                                        'new_fee': new_fee,
                                        'label': f"Confirm Fee Update for {s['name']} (Rs. {old_fee:,.0f} ➔ Rs. {new_fee:,.0f})"
                                    }
                                }
                            
                            # Check if user asked for fee status
                            has_fee_inquiry = any(k in user_message.lower() for k in ['fee', 'fees', 'status', 'arrear', 'baqaya', 'kitni', 'tbtao', 'batao'])
                            if has_fee_inquiry:
                                status_info = get_student_fee_status(s['id'])
                                if status_info:
                                    fd = status_info['fee_details']
                                    return {
                                        'text': f"🎓 **Student Fee Profile:**\n\n"
                                                f"• **Name:** {status_info['name']} (ID: {status_info['id']})\n"
                                                f"• **Class:** {status_info['class']} | **Father:** {status_info['father_name'] or 'N/A'}\n"
                                                f"• **Monthly Tuition Fee:** Rs. {fd['monthly_fee']:,.0f}\n"
                                                f"• **Past Arrears:** Rs. {fd['arrears']:,.0f}\n"
                                                f"• **Current Month Due ({status_info['current_month']}):** Rs. {fd['current_month_due']:,.0f}\n"
                                                f"• **Total Remaining Payable:** **Rs. {fd['remaining_payable']:,.0f}**\n\n"
                                                f"💡 Fee badalne ke liye keh sakte hain: *'{status_info['name']} ki fee 2500 kar do'*",
                                        'action_proposal': None
                                    }
                        elif students and len(students) > 1:
                            options = "\n".join([f"• ID {c['id']}: **{c['name']}** (Class: {c['class']}, Father: {c['father_name'] or 'N/A'}, Fee: Rs. {float(c['monthly_fee'] or 0):,.0f})" for c in students[:6]])
                            return {
                                'text': f"Is naam se aik se zyada students mile hain:\n\n{options}\n\nBarah-e-karam student ka ID ya Class sath batayein."
                            }
                        else:
                            return {
                                'text': f"⚠️ Student **{fn_args.get('query')}** system me nahi mila. Barah-e-karam naam ya ID verify karein."
                            }

                    elif fn_name == 'get_student_fee_status':
                        s_info = get_student_fee_status(fn_args.get('student_id'))
                        if s_info:
                            fd = s_info['fee_details']
                            return {
                                'text': f"🎓 **{s_info['name']}** (Class {s_info['class']}, ID {s_info['id']}):\n"
                                        f"• Monthly Fee: Rs. {fd['monthly_fee']:,.0f}\n"
                                        f"• Arrears: Rs. {fd['arrears']:,.0f}\n"
                                        f"• Remaining Payable: **Rs. {fd['remaining_payable']:,.0f}**"
                            }

                    elif fn_name == 'propose_update_student_fee':
                        s_id = fn_args.get('student_id')
                        new_fee = fn_args.get('new_monthly_fee')
                        conn = get_db_connection()
                        s = conn.execute("SELECT * FROM students WHERE id = ?", (s_id,)).fetchone()
                        conn.close()
                        if s:
                            old_fee = float(s['monthly_fee'] or 0.0)
                            return {
                                'text': f"Maine student **{s['name']}** (Class: {s['class']}, ID: {s['id']}) ki monthly fee **Rs. {new_fee:,.0f}** update karne ki proposal tayar kar di hai. Tasdeeq ke liye neeche button dabayein:",
                                'action_proposal': {
                                    'type': 'update_fee',
                                    'student_id': s['id'],
                                    'student_name': s['name'],
                                    'student_class': s['class'],
                                    'old_fee': old_fee,
                                    'new_fee': new_fee,
                                    'label': f"Confirm Fee Update for {s['name']} (Rs. {old_fee:,.0f} ➔ Rs. {new_fee:,.0f})"
                                }
                            }

                    elif fn_name == 'get_class_defaulters':
                        defs = get_class_defaulters(class_name=fn_args.get('class_name'), campus_id=campus_id)
                        if defs:
                            rows = "\n".join([f"• **{d['name']}** (Class {d['class']}, ID: {d['id']}): Due Rs. {d['total_due']:,.0f}" for d in defs[:8]])
                            return {'text': f"📋 **Fee Defaulters List:**\n\n{rows}"}
                        else:
                            return {'text': "🎉 Is class me koi pending fee defaulters nahi hain."}

                    elif fn_name == 'get_campus_stats':
                        stats = get_campus_stats(campus_id=campus_id)
                        return {
                            'text': f"📊 **Campus Stats:**\n• Total Students: {stats['total_students']}\n• Active Students: {stats['active_students']}\n• Collected This Month: Rs. {stats['collected_this_month']:,.0f}"
                        }

                    elif fn_name == 'get_campuses_summary':
                        campuses = get_campuses_summary()
                        if campuses:
                            lines = [f"🏢 **Aap ke system me kul {len(campuses)} campuses registered hain:**\n"]
                            for i, c in enumerate(campuses, 1):
                                lines.append(f"{i}. 🏛️ **{c['name']}** (ID: {c['id']}) — 👥 **{c['student_count']:,}** active students")
                            return {'text': "\n".join(lines)}
                        else:
                            return {'text': "System me koi campus registered nahi mila."}

                final_text = text_response.strip()
                if final_text:
                    return {
                        'text': final_text,
                        'action_proposal': None
                    }
        except urllib.error.HTTPError as e:
            print(f"Gemini API model {model_name} HTTP {e.code}: {e}")
            # Try next model in chain instead of breaking
            continue
        except Exception as e:
            print(f"Gemini API model {model_name} execution error: {e}")
            # Try next model in chain instead of breaking
            continue
            
    # If all models failed, short cooldown (15s) so rule engine handles immediate repeat, but Gemini re-attempts soon
    _GEMINI_COOLDOWN_UNTIL = datetime.now().timestamp() + 30
    return None

# -------------------------------------------------------------
# MAIN AGENT INTERACTION DISPATCHER
# -------------------------------------------------------------

def process_agent_request(message, user_session=None, active_campus_id=None, confirmed_action=None, history=None):
    """
    Main entry point for handling AI agent chat & actions.
    Supports multi-turn memory, Gemini Generative AI, and intelligent offline rule engine.
    """
    username = user_session.get('username', 'operator') if user_session else 'operator'
    
    # Handle confirmed action execution (e.g. user clicked "Confirm Update")
    if confirmed_action:
        action_type = confirmed_action.get('type')
        if action_type == 'update_fee':
            student_id = confirmed_action.get('student_id')
            new_fee = confirmed_action.get('new_fee')
            res = execute_update_student_fee(student_id, new_fee, executed_by=username)
            if res.get('success'):
                return {
                    'text': f"✅ **Kamyabi!** Student **{res['student_name']}** (Class: {res['student_class']}, ID: {res['student_id']}) ki monthly fee kamyabi se update ho kar **Rs. {res['new_fee']:,.0f}** kar di gayi hai. (Pehle: Rs. {res['old_fee']:,.0f})",
                    'action_completed': True,
                    'result': res
                }
            else:
                return {
                    'text': f"❌ Error: {res.get('error', 'Fee update nahi ho saki.')}",
                    'action_completed': False
                }

    # If no message provided
    if not message or not message.strip():
        return {'text': 'Barah-e-karam koi sawal ya instruction darj karein.'}

    # Attempt Gemini API first if API key is configured
    api_key = get_gemini_api_key()
    if api_key:
        ai_res = call_gemini_api(api_key, message, campus_id=active_campus_id, history=history, user_session=user_session)
        if ai_res and (ai_res.get('text') or ai_res.get('action_proposal')):
            return ai_res
            
    # Fallback to Smart Built-in Rule Engine (with session & history support)
    return parse_with_rule_engine(message, campus_id=active_campus_id, user_session=user_session, history=history)

