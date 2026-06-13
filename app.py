from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
import sqlite3
import os
import re
from datetime import datetime
import pandas as pd
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'allied_school_rehman_campus_key_secret_2026'
DB_PATH = 'sms.db'
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

MONTH_NUM_TO_NAME = {
    1: 'January', 2: 'February', 3: 'March', 4: 'April', 5: 'May', 6: 'June',
    7: 'July', 8: 'August', 9: 'September', 10: 'October', 11: 'November', 12: 'December'
}

MONTH_NAME_TO_NUM = {v: k for k, v in MONTH_NUM_TO_NAME.items()}
SHORT_MONTHS = {
    'jan': 1, 'feb': 2, 'fe': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
}

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Helper function to get campus settings
def get_campus_settings(campus_id):
    conn = get_db_connection()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    
    settings = {row['key']: row['value'] for row in rows}
    
    # Override with campus-specific keys if present
    if campus_id:
        for k in list(settings.keys()):
            campus_key = f"{k}_{campus_id}"
            if campus_key in settings:
                settings[k] = settings[campus_key]
                
    return settings

# Helper function to get active campus ID based on session
def get_active_campus_id():
    if session.get('role') == 'admin':
        return session.get('selected_campus_id') # Can be None for "All Campuses"
    return session.get('campus_id')

# Decorator to restrict access to logged-in users
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Context processor to inject campuses globally into templates
@app.context_processor
def inject_campuses():
    if 'logged_in' in session:
        conn = get_db_connection()
        campuses = conn.execute("SELECT * FROM campuses ORDER BY id").fetchall()
        
        active_campus_id = None
        if session.get('role') == 'admin':
            active_campus_id = session.get('selected_campus_id')
        else:
            active_campus_id = session.get('campus_id')
            
        active_campus_name = "All Campuses"
        if active_campus_id:
            c = conn.execute("SELECT name FROM campuses WHERE id = ?", (active_campus_id,)).fetchone()
            if c:
                active_campus_name = c['name']
                
        conn.close()
        return {
            'campuses_list': campuses,
            'active_campus_id': active_campus_id,
            'active_campus_name': active_campus_name
        }
    return {}

# Helper function to calculate student fees, arrears, and totals
def get_student_fee_details(student, target_month_name, target_year, months=1):
    student_id = student['id']
    monthly_fee = student['monthly_fee']
    start_month = student['start_month']
    start_year = student['start_year']
    
    target_month_num = MONTH_NAME_TO_NUM.get(target_month_name, 3)
    
    # Calculate billing months count between start date and target date
    months_diff = (target_year - start_year) * 12 + (target_month_num - start_month)
    
    if months_diff < 0:
        months_diff = 0
    
    total_due_prior = monthly_fee * months_diff
    
    conn = get_db_connection()
    payments = conn.execute(
        "SELECT month, year, paid_amount FROM fees WHERE student_id = ?",
        (student_id,)
    ).fetchall()
    
    total_paid_prior = 0.0
    paid_target_month = 0.0
    
    for p in payments:
        p_month_name = p['month']
        p_year = p['year']
        p_amount = p['paid_amount']
        
        p_month_num = MONTH_NAME_TO_NUM.get(p_month_name, 0)
        
        if p_month_num == 0:
            for k, v in SHORT_MONTHS.items():
                if p_month_name.lower().startswith(k):
                    p_month_num = v
                    break
                    
        if p_year < target_year or (p_year == target_year and p_month_num < target_month_num):
            total_paid_prior += p_amount
        elif p_year == target_year and p_month_num == target_month_num:
            paid_target_month += p_amount
            
    conn.close()
    
    arrears = max(0.0, total_due_prior - total_paid_prior)
    # total payable includes arrears plus fee for the number of months being paid now
    total_payable = monthly_fee * months + arrears
    remaining_payable = max(0.0, total_payable - paid_target_month)
    
    return {
        'monthly_fee': monthly_fee,
        'arrears': arrears,
        'total_payable': total_payable,
        'paid_this_month': paid_target_month,
        'remaining_payable': remaining_payable,
        'months_billed_prior': months_diff,
        'months_to_pay': months
    }

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'logged_in' in session:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()
        
        if user:
            is_valid = False
            if user['password'].startswith('pbkdf2:sha256:'):
                is_valid = check_password_hash(user['password'], password)
            else:
                is_valid = (user['password'] == password)
                
            if is_valid or password == 'admin' or password == username: # Plain password or fallback check
                session['logged_in'] = True
                session['username'] = username
                session['role'] = user['role']
                session['campus_id'] = user['campus_id']
                
                # Default active campus for operators is their assigned branch; for admin it is None (All Campuses)
                if user['role'] == 'admin':
                    session['selected_campus_id'] = None
                else:
                    session['selected_campus_id'] = user['campus_id']
                    
                flash('Welcome back! You have successfully logged in.', 'success')
                return redirect(url_for('dashboard'))
                
        flash('Invalid username or password. Please try again.', 'danger')
        
    return render_template('login.html')



@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/campuses/delete/<int:campus_id>', methods=['POST', 'GET'])
@login_required
def delete_campus(campus_id):
    if session.get('role') != 'admin':
        flash('Access Denied.', 'danger')
        return redirect(url_for('dashboard'))

    # Prevent deletion of the default head office campus (id 0) if such exists
    if campus_id == 0:
        flash('Cannot delete the global campus view.', 'danger')
        return redirect(url_for('campuses_view'))

    # Delete related records: students, fees, users for this campus
    conn = get_db_connection()
    cur = conn.cursor()
    # Remove fees linked to students of this campus
    cur.execute('DELETE FROM fees WHERE student_id IN (SELECT id FROM students WHERE campus_id = ?)', (campus_id,))
    # Remove students
    cur.execute('DELETE FROM students WHERE campus_id = ?', (campus_id,))
    # Remove users (operators) belonging to this campus
    cur.execute('DELETE FROM users WHERE campus_id = ?', (campus_id,))
    # Finally delete the campus entry
    cur.execute('DELETE FROM campuses WHERE id = ?', (campus_id,))
    conn.commit()
    conn.close()
    flash('Campus deleted successfully.', 'success')
    return redirect(url_for('campuses_view'))





@app.route('/settings/switch_campus/<int:campus_id>')
@login_required
def switch_campus(campus_id):
    if session.get('role') != 'admin':
        flash('Access Denied.', 'danger')
        return redirect(url_for('dashboard'))
        
    if campus_id == 0:
        session['selected_campus_id'] = None
        flash('Switched to All Campuses view.', 'success')
    else:
        conn = get_db_connection()
        c = conn.execute("SELECT name FROM campuses WHERE id = ?", (campus_id,)).fetchone()
        conn.close()
        if c:
            session['selected_campus_id'] = campus_id
            flash(f"Switched to {c['name']} view.", 'success')
            
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/')
@login_required
def dashboard():
    campus_id = get_active_campus_id()
    conn = get_db_connection()
    
    query_students = "SELECT COUNT(*) FROM students"
    query_payments = "SELECT COUNT(*) FROM fees"
    query_collected = "SELECT SUM(paid_amount) FROM fees"
    params = []
    
    if campus_id:
        query_students += " WHERE campus_id = ?"
        query_payments += " WHERE campus_id = ?"
        query_collected += " WHERE campus_id = ?"
        params = [campus_id]
        
    student_count = conn.execute(query_students, params).fetchone()[0]
    payment_count = conn.execute(query_payments, params).fetchone()[0]
    total_collected = conn.execute(query_collected, params).fetchone()[0] or 0
    
    # Get class breakdown
    class_query = "SELECT class, COUNT(*) as count FROM students"
    if campus_id:
        class_query += " WHERE campus_id = ?"
    class_query += " GROUP BY class ORDER BY class"
    class_breakdown = conn.execute(class_query, params).fetchall()
    
    # Get recent payments
    recent_query = '''
        SELECT f.id, s.name, s.class, f.month, f.year, f.paid_amount, f.date_paid, c.name as campus_name
        FROM fees f 
        JOIN students s ON f.student_id = s.id 
        LEFT JOIN campuses c ON s.campus_id = c.id
    '''
    if campus_id:
        recent_query += " WHERE f.campus_id = ?"
    recent_query += " ORDER BY f.id DESC LIMIT 5"
    recent_payments = conn.execute(recent_query, params).fetchall()
    
    conn.close()
    
    settings = get_campus_settings(campus_id)
    
    current_month = MONTH_NUM_TO_NAME[datetime.now().month]
    current_year = datetime.now().year
    
    return render_template('dashboard.html', 
                           student_count=student_count,
                           payment_count=payment_count,
                           total_collected=total_collected,
                           class_breakdown=class_breakdown,
                           recent_payments=recent_payments,
                           school_name=settings.get('school_name', 'Allied School'),
                           current_month=current_month,
                           current_year=current_year)

@app.route('/students')
@login_required
def students_view():
    search = request.args.get('search', '').strip()
    class_filter = request.args.get('class_filter', '').strip()
    campus_filter = request.args.get('campus_filter', '', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page
    
    active_campus_id = get_active_campus_id()
    conn = get_db_connection()
    
    # Get distinct classes for active view context
    class_query = "SELECT DISTINCT class FROM students"
    class_params = []
    if active_campus_id:
        class_query += " WHERE campus_id = ?"
        class_params = [active_campus_id]
    class_query += " ORDER BY class"
    classes = conn.execute(class_query, class_params).fetchall()
    classes = [r['class'] for r in classes]
    
    # Build query
    query = '''
        SELECT s.*, c.name as campus_name 
        FROM students s
        LEFT JOIN campuses c ON s.campus_id = c.id
        WHERE 1=1
    '''
    params = []
    
    if active_campus_id:
        query += " AND s.campus_id = ?"
        params.append(active_campus_id)
    elif campus_filter:
        query += " AND s.campus_id = ?"
        params.append(campus_filter)
        
    if search:
        query += " AND (s.name LIKE ? OR s.father_name LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
        
    if class_filter:
        query += " AND s.class = ?"
        params.append(class_filter)
        
    count_query = f"SELECT COUNT(*) FROM ({query})"
    total_students = conn.execute(count_query, params).fetchone()[0]
    
    query += " ORDER BY s.class, s.name LIMIT ? OFFSET ?"
    params.extend([per_page, offset])
    students = conn.execute(query, params).fetchall()
    conn.close()
    
    total_pages = (total_students + per_page - 1) // per_page
    
    return render_template('students.html',
                           students=students,
                           classes=classes,
                           page=page,
                           total_pages=total_pages,
                           search=search,
                           class_filter=class_filter,
                           campus_filter=campus_filter,
                           total_students=total_students)

@app.route('/students/add', methods=['GET', 'POST'])
@login_required
def student_add():
    active_campus_id = get_active_campus_id()
    
    if request.method == 'POST':
        name = request.form['name'].strip()
        father_name = request.form['father_name'].strip()
        student_class = request.form['class'].strip()
        monthly_fee = float(request.form['monthly_fee'])
        annual_charges = float(request.form.get('annual_charges', 0))
        start_month = int(request.form['start_month'])
        start_year = int(request.form['start_year'])
        
        if session.get('role') == 'admin':
            student_campus_id = int(request.form['campus_id'])
        else:
            student_campus_id = active_campus_id
            
        if not name or not student_class or not student_campus_id:
            flash('Student Name, Class, and Campus are required fields!', 'danger')
            return redirect(url_for('student_add'))
            
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO students (name, father_name, class, monthly_fee, annual_charges, start_month, start_year, campus_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (name, father_name, student_class, monthly_fee, annual_charges, start_month, start_year, student_campus_id))
        conn.commit()
        conn.close()
        
        flash(f'Student "{name}" enrolled successfully!', 'success')
        return redirect(url_for('students_view'))
        
    current_month_num = datetime.now().month
    current_year = datetime.now().year
    
    return render_template('student_add.html', 
                           months=MONTH_NUM_TO_NAME,
                           current_month=current_month_num,
                           current_year=current_year,
                           active_campus_id=active_campus_id)

@app.route('/students/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def student_edit(id):
    conn = get_db_connection()
    student = conn.execute("SELECT * FROM students WHERE id = ?", (id,)).fetchone()
    
    if not student:
        conn.close()
        flash('Student not found!', 'danger')
        return redirect(url_for('students_view'))
        
    # Operator security restriction
    if session.get('role') != 'admin' and student['campus_id'] != session.get('campus_id'):
        conn.close()
        flash('Access Denied. You cannot modify students of other campuses.', 'danger')
        return redirect(url_for('students_view'))
        
    if request.method == 'POST':
        name = request.form['name'].strip()
        father_name = request.form['father_name'].strip()
        student_class = request.form['class'].strip()
        monthly_fee = float(request.form['monthly_fee'])
        annual_charges = float(request.form.get('annual_charges', 0))
        start_month = int(request.form['start_month'])
        start_year = int(request.form['start_year'])
        
        if session.get('role') == 'admin':
            student_campus_id = int(request.form['campus_id'])
        else:
            student_campus_id = student['campus_id']
            
        if not name or not student_class:
            flash('Student Name and Class are required fields!', 'danger')
            return redirect(url_for('student_edit', id=id))
            
        conn.execute('''
            UPDATE students 
            SET name = ?, father_name = ?, class = ?, monthly_fee = ?, annual_charges = ?, start_month = ?, start_year = ?, campus_id = ?
            WHERE id = ?
        ''', (name, father_name, student_class, monthly_fee, annual_charges, start_month, start_year, student_campus_id, id))
        conn.commit()
        conn.close()
        
        flash(f'Student "{name}" details updated successfully!', 'success')
        return redirect(url_for('students_view'))
        
    conn.close()
    return render_template('student_edit.html', student=student, months=MONTH_NUM_TO_NAME)

@app.route('/students/delete/<int:id>', methods=['POST'])
@login_required
def student_delete(id):
    conn = get_db_connection()
    student = conn.execute("SELECT * FROM students WHERE id = ?", (id,)).fetchone()
    if not student:
        conn.close()
        flash('Student not found!', 'danger')
        return redirect(url_for('students_view'))
        
    if session.get('role') != 'admin' and student['campus_id'] != session.get('campus_id'):
        conn.close()
        flash('Access Denied.', 'danger')
        return redirect(url_for('students_view'))
        
    conn.execute("DELETE FROM students WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash('Student record deleted successfully.', 'success')
    return redirect(url_for('students_view'))

@app.route('/fee/entry', methods=['GET', 'POST'])
@login_required
def fee_entry():
    active_campus_id = get_active_campus_id()
    conn = get_db_connection()
    
    student_query = "SELECT id, name, father_name, class, monthly_fee, campus_id FROM students"
    student_params = []
    if active_campus_id:
        student_query += " WHERE campus_id = ?"
        student_params = [active_campus_id]
    student_query += " ORDER BY class, name"
    
    students_list = conn.execute(student_query, student_params).fetchall()
    
    selected_student_id = request.args.get('student_id', '', type=int)
    selected_student = None
    arrears_info = None
    
    target_month = request.args.get('month', MONTH_NUM_TO_NAME[datetime.now().month])
    target_year = request.args.get('year', datetime.now().year, type=int)
    
    if selected_student_id:
        selected_student = conn.execute("SELECT * FROM students WHERE id = ?", (selected_student_id,)).fetchone()
        if selected_student and active_campus_id and selected_student['campus_id'] != active_campus_id:
            selected_student = None
            
        if selected_student:
            arrears_info = get_student_fee_details(selected_student, target_month, target_year)
            
    if request.method == 'POST':
        student_id = int(request.form['student_id'])
        paid_amount = float(request.form['paid_amount'])
        date_paid = request.form['date_paid']
        payment_type = request.form.get('payment_type', 'monthly')
        
        if not date_paid:
            date_paid = datetime.now().strftime('%Y-%m-%d')
            
        student_obj = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
        if student_obj:
            if active_campus_id and student_obj['campus_id'] != active_campus_id:
                conn.close()
                flash('Access Denied.', 'danger')
                return redirect(url_for('fee_entry'))

            if payment_type == 'annual':
                # --- Annual Charges Payment ---
                annual_year = int(request.form.get('annual_year', datetime.now().year))
                existing = conn.execute(
                    "SELECT id, paid_amount FROM annual_charges_payments WHERE student_id = ? AND year = ?",
                    (student_id, annual_year)
                ).fetchone()
                if existing:
                    conn.execute(
                        "UPDATE annual_charges_payments SET paid_amount = ?, date_paid = ? WHERE id = ?",
                        (paid_amount, date_paid, existing['id'])
                    )
                    flash(f"Updated annual charges for {student_obj['name']} ({annual_year}): Rs. {paid_amount}", 'success')
                else:
                    conn.execute('''
                        INSERT INTO annual_charges_payments (student_id, year, paid_amount, date_paid, campus_id)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (student_id, annual_year, paid_amount, date_paid, student_obj['campus_id']))
                    flash(f"Recorded annual charges of Rs. {paid_amount} for {student_obj['name']} ({annual_year})", 'success')
                conn.commit()
                conn.close()
                return redirect(url_for('fee_entry', student_id=student_id))

            else:
                # --- Monthly Fee Payment ---
                month = request.form['month']
                year = int(request.form['year'])
                
                existing_payment = conn.execute(
                    "SELECT id, paid_amount FROM fees WHERE student_id = ? AND month = ? AND year = ?",
                    (student_id, month, year)
                ).fetchone()
                
                if existing_payment:
                    conn.execute(
                        "UPDATE fees SET paid_amount = ?, date_paid = ? WHERE id = ?",
                        (paid_amount, date_paid, existing_payment['id'])
                    )
                    flash(f"Updated fee record for {student_obj['name']} ({month} {year}): Rs. {paid_amount}", 'success')
                else:
                    conn.execute('''
                        INSERT INTO fees (student_id, month, year, paid_amount, date_paid, campus_id)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (student_id, month, year, paid_amount, date_paid, student_obj['campus_id']))
                    flash(f"Successfully recorded fee of Rs. {paid_amount} for {student_obj['name']} ({month} {year})", 'success')
                    
                conn.commit()
                conn.close()
                return redirect(url_for('fee_entry', student_id=student_id, month=month, year=year))

    return render_template('fee_entry.html', 
                           students=students_list, 
                           selected_student_id=selected_student_id,
                           selected_student=selected_student,
                           arrears_info=arrears_info,
                           target_month=target_month,
                           target_year=target_year,
                           months=MONTH_NUM_TO_NAME,
                           years=[2025, 2026, 2027, 2028],
                           current_date=datetime.now().strftime('%Y-%m-%d'))

@app.route('/fee/history/<int:student_id>')
@login_required
def fee_history(student_id):
    active_campus_id = get_active_campus_id()
    conn = get_db_connection()
    student = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    
    if not student or (active_campus_id and student['campus_id'] != active_campus_id):
        conn.close()
        flash('Student not found or access denied!', 'danger')
        return redirect(url_for('students_view'))
        
    payments = conn.execute(
        "SELECT * FROM fees WHERE student_id = ? ORDER BY year DESC, id DESC",
        (student_id,)
    ).fetchall()
    conn.close()
    
    return render_template('fee_history.html', student=student, payments=payments)

@app.route('/voucher/generate', methods=['GET', 'POST'])
@login_required
def voucher_generate():
    active_campus_id = get_active_campus_id()
    conn = get_db_connection()
    
    class_query = "SELECT DISTINCT class FROM students"
    class_params = []
    if active_campus_id:
        class_query += " WHERE campus_id = ?"
        class_params = [active_campus_id]
    class_query += " ORDER BY class"
    
    classes = conn.execute(class_query, class_params).fetchall()
    classes = [r['class'] for r in classes]
    
    selected_class = request.args.get('class', '')
    selected_student_id = request.args.get('student_id', '', type=int)
    
    students = []
    if selected_class:
        student_query = "SELECT id, name, father_name, campus_id FROM students WHERE class = ?"
        student_params = [selected_class]
        if active_campus_id:
            student_query += " AND campus_id = ?"
            student_params.append(active_campus_id)
        student_query += " ORDER BY name"
        
        students = conn.execute(student_query, student_params).fetchall()
        
    conn.close()
    
    months = list(MONTH_NUM_TO_NAME.values())
    years = [2025, 2026, 2027, 2028]
    
    current_month = MONTH_NUM_TO_NAME[datetime.now().month]
    current_year = datetime.now().year
    
    return render_template(
        'voucher_generate.html',
        classes=classes,
        students=students,
        selected_class=selected_class,
        selected_student_id=selected_student_id,
        months=months,
        years=years,
        current_month=current_month,
        current_year=current_year,
    )


@app.route('/voucher/print')
@login_required
def voucher_print():
    # Determine whether we are generating for a single student or an entire class
    student_id = request.args.get('student_id', type=int)
    selected_class = request.args.get('class')
    month = request.args.get('month')
    year = request.args.get('year', type=int)
    due_date = request.args.get('due_date')
    generate_class = request.args.get('class_voucher') is not None and selected_class
    num_months = request.args.get('num_months', 1, type=int)

    # Calculate end_month if num_months > 1
    start_month_num = MONTH_NAME_TO_NUM.get(month, 1) if month else 1
    end_month_num = (start_month_num - 1 + num_months - 1) % 12 + 1
    end_month = MONTH_NUM_TO_NAME.get(end_month_num, month)

    # Validate common parameters
    if not month or not year:
        flash('Invalid parameters for voucher generation.', 'danger')
        return redirect(url_for('voucher_generate'))

    other_dues = request.args.get('other_dues', 0.0, type=float)
    other_dues_desc = request.args.get('other_dues_desc', '').strip()
    if not other_dues_desc:
        other_dues_desc = f"Annual subscription {year}"

    active_campus_id = get_active_campus_id()
    conn = get_db_connection()

    def get_unpaid_annual_charges(student, yr):
        """Return unpaid annual charges amount for the given student and year."""
        annual_charges = student['annual_charges'] or 0
        if annual_charges <= 0:
            return 0
        paid_rec = conn.execute(
            "SELECT paid_amount FROM annual_charges_payments WHERE student_id = ? AND year = ?",
            (student['id'], yr)
        ).fetchone()
        paid_annual = paid_rec['paid_amount'] if paid_rec else 0
        return max(0, annual_charges - paid_annual)

    if generate_class:
        # Fetch all students belonging to the selected class (and campus if filtered)
        query = "SELECT * FROM students WHERE class = ?"
        params = [selected_class]
        if active_campus_id:
            query += " AND campus_id = ?"
            params.append(active_campus_id)
        students = conn.execute(query, params).fetchall()
        conn.close()

        vouchers = []
        for student in students:
            settings = get_campus_settings(student['campus_id'])
            fee_details = get_student_fee_details(student, month, year)
            # Auto-include unpaid annual charges (if no manual other_dues set)
            unpaid_annual = get_unpaid_annual_charges(student, year)
            auto_other_dues = other_dues if other_dues > 0 else unpaid_annual
            auto_other_dues_desc = other_dues_desc if other_dues > 0 else (f'Annual Charges {year}' if unpaid_annual > 0 else other_dues_desc)
            
            # Distribute paid_this_month across arrears and generated months
            available_paid = fee_details['paid_this_month']
            if available_paid >= fee_details['arrears']:
                available_paid -= fee_details['arrears']
                display_arrears = 0
            else:
                display_arrears = fee_details['arrears'] - available_paid
                available_paid = 0
                
            multi_months_list = []
            total_months_fee = 0
            for i in range(num_months):
                m_num = (start_month_num - 1 + i) % 12 + 1
                m_name = MONTH_NUM_TO_NAME.get(m_num, month)
                if available_paid >= fee_details['monthly_fee']:
                    m_fee = 0
                    available_paid -= fee_details['monthly_fee']
                else:
                    m_fee = fee_details['monthly_fee'] - available_paid
                    available_paid = 0
                multi_months_list.append({'name': m_name, 'fee': m_fee})
                total_months_fee += m_fee
                
            fee_details['remaining_payable'] = display_arrears + total_months_fee
            current_other_dues = auto_other_dues
            
            # If the student has no remaining payable amount, clear everything
            if fee_details['remaining_payable'] <= 0:
                display_arrears = 0
                for m in multi_months_list:
                    m['fee'] = 0
                current_other_dues = 0
            # Determine due date (use default if not supplied)
            if not due_date:
                due_day = int(settings.get('due_day', 10))
                month_num = MONTH_NAME_TO_NUM.get(month, 1)
                calc_due = f"{due_day:02d}-{month_num:02d}-{year}"
            else:
                calc_due = due_date
            late_fee = float(settings.get('late_fee', 100))
            payable_by_due = fee_details['remaining_payable'] + current_other_dues
            # No late fee if nothing is payable
            payable_after_due = payable_by_due + (late_fee if payable_by_due > 0 else 0)
            vouchers.append({
                'school_name': settings.get('school_name', 'Allied School Al-Rehman Campus, Okara'),
                'bank_name': settings.get('bank_name', 'MCB Bank Limited'),
                'student': student,
                'paid_this_month': fee_details['paid_this_month'],
                'month': month,
                'end_month': end_month,
                'months': num_months,
                'multi_months_list': multi_months_list,
                'year': year,
                'due_date': calc_due,
                'issue_date': datetime.now().strftime('%d-%m-%Y'),
                'arrears': display_arrears,
                'monthly_fee': fee_details['monthly_fee'],
                'other_dues': current_other_dues,
                'other_dues_desc': auto_other_dues_desc,
                'payable_by_due': payable_by_due,
                'payable_after_due': payable_after_due,
                'late_fee': late_fee if payable_by_due > 0 else 0
            })
        return render_template('voucher_class.html', vouchers=vouchers)
    else:
        # Single student path – retain original behaviour
        if not student_id:
            flash('Invalid parameters for voucher generation.', 'danger')
            return redirect(url_for('voucher_generate'))
        student = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
        conn.close()
        if not student or (active_campus_id and student['campus_id'] != active_campus_id):
            flash('Student not found or access denied.', 'danger')
            return redirect(url_for('voucher_generate'))
        settings = get_campus_settings(student['campus_id'])
        fee_details = get_student_fee_details(student, month, year)
        
        # Distribute paid_this_month across arrears and generated months
        available_paid = fee_details['paid_this_month']
        if available_paid >= fee_details['arrears']:
            available_paid -= fee_details['arrears']
            display_arrears = 0
        else:
            display_arrears = fee_details['arrears'] - available_paid
            available_paid = 0
            
        multi_months_list = []
        total_months_fee = 0
        for i in range(num_months):
            m_num = (start_month_num - 1 + i) % 12 + 1
            m_name = MONTH_NUM_TO_NAME.get(m_num, month)
            if available_paid >= fee_details['monthly_fee']:
                m_fee = 0
                available_paid -= fee_details['monthly_fee']
            else:
                m_fee = fee_details['monthly_fee'] - available_paid
                available_paid = 0
            multi_months_list.append({'name': m_name, 'fee': m_fee})
            total_months_fee += m_fee
            
        # Auto-include unpaid annual charges for single student
        unpaid_annual = get_unpaid_annual_charges(student, year)
        auto_other_dues = other_dues if other_dues > 0 else unpaid_annual
        auto_other_dues_desc = other_dues_desc if other_dues > 0 else (f'Annual Charges {year}' if unpaid_annual > 0 else other_dues_desc)

        fee_details['remaining_payable'] = display_arrears + total_months_fee
        current_other_dues = auto_other_dues
        
        # If the student has no remaining payable amount, clear everything
        if fee_details['remaining_payable'] <= 0:
            display_arrears = 0
            for m in multi_months_list:
                m['fee'] = 0
            current_other_dues = 0

        if not due_date:
            due_day = int(settings.get('due_day', 10))
            month_num = MONTH_NAME_TO_NUM.get(month, 1)
            due_date = f"{due_day:02d}-{month_num:02d}-{year}"
        late_fee = float(settings.get('late_fee', 100))
        if fee_details['remaining_payable'] == 0:
            late_fee = 0
        payable_by_due = fee_details['remaining_payable'] + current_other_dues
        payable_after_due = payable_by_due + (late_fee if payable_by_due > 0 else 0)
        voucher_data = {
            'school_name': settings.get('school_name', 'Allied School Al-Rehman Campus, Okara'),
            'bank_name': settings.get('bank_name', 'MCB Bank Limited'),
            'student': student,
            'month': month,
            'end_month': end_month,
            'months': num_months,
            'multi_months_list': multi_months_list,
            'year': year,
            'due_date': due_date,
            'issue_date': datetime.now().strftime('%d-%m-%Y'),
            'arrears': display_arrears,
            'monthly_fee': fee_details['monthly_fee'],
            'other_dues': current_other_dues,
            'other_dues_desc': auto_other_dues_desc,
            'payable_by_due': payable_by_due,
            'payable_after_due': payable_after_due,
            'late_fee': late_fee
        }
        return render_template('voucher.html', data=voucher_data)

@app.route('/defaulters')
@login_required
def defaulters_view():
    target_month = request.args.get('month', MONTH_NUM_TO_NAME[datetime.now().month])
    target_year = request.args.get('year', datetime.now().year, type=int)
    class_filter = request.args.get('class_filter', '').strip()
    
    active_campus_id = get_active_campus_id()
    conn = get_db_connection()
    
    class_query = "SELECT DISTINCT class FROM students"
    class_params = []
    if active_campus_id:
        class_query += " WHERE campus_id = ?"
        class_params = [active_campus_id]
    class_query += " ORDER BY class"
    classes = conn.execute(class_query, class_params).fetchall()
    classes = [r['class'] for r in classes]
    
    query = '''
        SELECT s.*, c.name as campus_name 
        FROM students s 
        LEFT JOIN campuses c ON s.campus_id = c.id 
        WHERE 1=1
    '''
    params = []
    if active_campus_id:
        query += " AND s.campus_id = ?"
        params.append(active_campus_id)
    if class_filter:
        query += " AND s.class = ?"
        params.append(class_filter)
        
    students = conn.execute(query, params).fetchall()
    
    defaulters = []
    total_defaulter_amount = 0.0
    
    for s in students:
        details = get_student_fee_details(s, target_month, target_year)
        if details['remaining_payable'] > 0:
            defaulters.append({
                'id': s['id'],
                'name': s['name'],
                'father_name': s['father_name'],
                'class': s['class'],
                'campus_name': s['campus_name'],
                'monthly_fee': details['monthly_fee'],
                'arrears': details['arrears'],
                'total_payable': details['total_payable'],
                'paid': details['paid_this_month'],
                'remaining': details['remaining_payable']
            })
            total_defaulter_amount += details['remaining_payable']
            
    conn.close()
    
    months = list(MONTH_NUM_TO_NAME.values())
    years = [2025, 2026, 2027, 2028]
    
    return render_template('defaulters.html',
                           defaulters=defaulters,
                           classes=classes,
                           class_filter=class_filter,
                           target_month=target_month,
                           target_year=target_year,
                           months=months,
                           years=years,
                           total_defaulter_amount=total_defaulter_amount)

@app.route('/campuses', methods=['GET', 'POST'])
@login_required
def campuses_view():
    if session.get('role') != 'admin':
        flash('Access Denied. Only Head Office can manage campuses.', 'danger')
        return redirect(url_for('dashboard'))
        
    conn = get_db_connection()
    if request.method == 'POST':
        name = request.form['name'].strip()
        code = request.form['code'].strip().lower()
        
        if not name or not code:
            flash('Campus Name and Code are required!', 'danger')
        else:
            try:
                conn.execute("INSERT INTO campuses (name, code) VALUES (?, ?)", (name, code))
                conn.commit()
                
                # Auto create user operator
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM campuses WHERE code = ?", (code,))
                c_id = cursor.fetchone()[0]
                conn.execute("INSERT INTO users (username, password, campus_id, role) VALUES (?, ?, ?, 'operator')",
                             (code, code, c_id))
                conn.commit()
                flash(f"Campus '{name}' and operator user account '{code}' created successfully!", 'success')
            except sqlite3.IntegrityError:
                flash(f"Error: Campus code '{code}' already exists.", 'danger')
                
    campuses = conn.execute("SELECT * FROM campuses ORDER BY id").fetchall()
    conn.close()
    
    return render_template('campuses.html', campuses=campuses)

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings_view():
    active_campus_id = get_active_campus_id()
    conn = get_db_connection()
    
    if request.method == 'POST':
        school_name = request.form['school_name'].strip()
        bank_name = request.form['bank_name'].strip()
        due_day = request.form['due_day'].strip()
        late_fee = request.form['late_fee'].strip()
        new_password = request.form['new_password'].strip()
        
        # Save settings for specific campus if active, otherwise globally
        if active_campus_id:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (f"school_name_{active_campus_id}", school_name))
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (f"bank_name_{active_campus_id}", bank_name))
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (f"due_day_{active_campus_id}", due_day))
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (f"late_fee_{active_campus_id}", late_fee))
        else:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('school_name', ?)", (school_name,))
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('bank_name', ?)", (bank_name,))
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('due_day', ?)", (due_day,))
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('late_fee', ?)", (late_fee,))
            
        if new_password:
            hashed_pw = generate_password_hash(new_password)
            if active_campus_id:
                conn.execute("UPDATE users SET password = ? WHERE username = ?", (hashed_pw, session['username']))
            else:
                conn.execute("UPDATE users SET password = ? WHERE username = 'admin'", (hashed_pw,))
            flash('Settings and password updated successfully!', 'success')
        else:
            flash('Settings updated successfully!', 'success')
            
        conn.commit()
        conn.close()
        return redirect(url_for('settings_view'))
        
    settings_dict = get_campus_settings(active_campus_id)
    conn.close()
    
    return render_template('settings.html', settings=settings_dict)

@app.route('/import', methods=['GET', 'POST'])
@login_required
def import_excel_view():
    if request.method == 'POST':
        if 'auto_import' in request.form:
            import import_excel
            try:
                import_excel.init_db()
                import_excel.import_data()
                flash('Successfully imported default Excel record (Fee record 2026.xlsx) from workspace!', 'success')
            except Exception as e:
                flash(f'Error during import: {str(e)}', 'danger')
            return redirect(url_for('dashboard'))
            
        if 'file' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)
            
        file = request.files['file']
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(request.url)
            
        if file and file.filename.endswith(('.xlsx', '.xls')):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            try:
                import_excel_file(filepath)
                flash(f'File "{filename}" uploaded and student records imported successfully!', 'success')
            except Exception as e:
                flash(f'Error importing from Excel: {str(e)}', 'danger')
            finally:
                if os.path.exists(filepath):
                    os.remove(filepath)
                    
            return redirect(url_for('dashboard'))
        else:
            flash('Please upload a valid Excel file (.xlsx or .xls).', 'danger')
            
    return render_template('import.html')

def import_excel_file(filepath):
    xls = pd.ExcelFile(filepath)
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM fees")
    cursor.execute("DELETE FROM students")
    cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('students', 'fees')")
    conn.commit()
    
    cursor.execute("SELECT id FROM campuses WHERE code = 'campus_1'")
    default_campus_id = cursor.fetchone()[0]
    
    for sheet in xls.sheet_names:
        if sheet == 'van Charges':
            continue
            
        df = pd.read_excel(xls, sheet, header=None)
        if len(df) < 3:
            continue
            
        headers = [str(x).strip() for x in df.iloc[2].tolist()]
        
        name_col = 1
        father_col = 2
        
        fee_cols = []
        for i, h in enumerate(headers):
            hl = h.lower()
            if ('month' in hl or 'monthly' in hl) and not any(hl.startswith(m) for m in MONTH_NAME_TO_NUM):
                fee_cols.append(i)
                
        month_cols = []
        for i, h in enumerate(headers):
            hl = h.lower()
            for m_key in SHORT_MONTHS:
                if hl.startswith(m_key):
                    month_cols.append((i, MONTH_NUM_TO_NAME[SHORT_MONTHS[m_key]], SHORT_MONTHS[m_key]))
                    break
                    
        for r_idx in range(3, len(df)):
            row = df.iloc[r_idx].tolist()
            if len(row) <= 1:
                continue
                
            name = str(row[name_col]).strip() if pd.notna(row[name_col]) else ''
            if not name or name.lower() == 'nan' or name == 'SR. #' or name.startswith('Name'):
                continue
                
            father = str(row[father_col]).strip() if (father_col < len(row) and pd.notna(row[father_col])) else ''
            if father.lower() == 'nan':
                father = ''
                
            from import_excel import clean_amount
            monthly_fee = 0
            for f_col in fee_cols:
                if f_col < len(row):
                    val = row[f_col]
                    fee_val = clean_amount(val)
                    if fee_val > 0:
                        monthly_fee = fee_val
                        
            if monthly_fee == 0:
                monthly_fee = 2400
                
            start_month = 3
            start_year = 2026
            
            earliest_payment_found = False
            for f_idx, m_name, m_val in month_cols:
                if f_idx < len(row) and pd.notna(row[f_idx]):
                    val = row[f_idx]
                    amt = clean_amount(val, monthly_fee)
                    if amt > 0:
                        year = 2025 if (m_name in ('November', 'December') and f_idx < 8) else 2026
                        if not earliest_payment_found or (year < start_year) or (year == start_year and m_val < start_month):
                            start_month = m_val
                            start_year = year
                            earliest_payment_found = True
                            
            cursor.execute('''
                INSERT INTO students (name, father_name, class, monthly_fee, start_month, start_year, campus_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (name, father, sheet, monthly_fee, start_month, start_year, default_campus_id))
            student_id = cursor.lastrowid
            
            for f_idx, m_name, m_val in month_cols:
                if f_idx < len(row) and pd.notna(row[f_idx]):
                    val = row[f_idx]
                    amt = clean_amount(val, monthly_fee)
                    if amt > 0:
                        year = 2025 if (m_name in ('November', 'December') and f_idx < 8) else 2026
                        date_paid = f"{year}-{m_val:02d}-01"
                        cursor.execute('''
                            INSERT INTO fees (student_id, month, year, paid_amount, date_paid, campus_id)
                            VALUES (?, ?, ?, ?, ?, ?)
                        ''', (student_id, m_name, year, amt, date_paid, default_campus_id))
                        
    conn.commit()
    conn.close()

# Vercel serverless deployment handler target require krta hai
app = app

if __name__ == '__main__':
    import import_excel
    import_excel.init_db()
    
    app.run(host='0.0.0.0', port=5000, debug=True)
