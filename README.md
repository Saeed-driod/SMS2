# Allied School Okara — Fee & Voucher Studio Guide

This guide provides details on the School Management & Fee Voucher Studio built for **Allied School Al-Rehman Campus, Okara**. It replaces the existing Excel fee sheet tracking system with a SQLite database-backed web dashboard.

---

## 📂 Project Directory Structure

Here is the folder structure established in the workspace:

```text
e:\SMS\
├── app.py                  # Main Flask web application containing all routes & business logic
├── import_excel.py         # SQLite DB initializer & Excel workbook parser
├── sms.db                  # Live SQLite database containing student and payment ledger data
├── Run Studio.bat          # Easy double-click batch script to run python server & open browser
├── Fee record 2026.xlsx    # Source Excel file containing 3,000+ student profiles
├── Sample Voucher.docx     # Reference MS Word voucher template
├── static/
│   ├── css/
│   │   └── style.css       # Premium custom stylesheet with dark glassmorphism & print layouts
│   └── js/
│       └── main.js        # JavaScript helpers for real-time autocomplete student search
└── templates/
    ├── base.html           # HTML5 boilerplate containing layout wrappers, CSS/JS links & nav
    ├── login.html          # Admin Portal login page
    ├── dashboard.html      # Main stats panel showing collections, quick links & breakdowns
    ├── students.html       # Enrolled students directory with search, filters & pagination
    ├── student_add.html    # Form to enroll a new student
    ├── student_edit.html   # Form to edit a student's profile or billing cycle
    ├── fee_entry.html      # Fee Collection registry with live arrears audit panels
    ├── fee_history.html    # Individual student ledger transaction history
    ├── voucher_generate.html # Challan generator setup screen (Class/Student selection)
    ├── voucher.html        # Landscape print template displaying 3 challan copies on A4
    ├── defaulters.html     # Defaulters panel listing students with outstanding balances
    └── settings.html       # School parameters configuration & admin password management
```

---

## 🗄️ Database Architecture

The SQLite database (`sms.db`) contains four primary tables:

### 1. `students` Table
Tracks active student profiles, basic details, tuition rates, and start times of billing.
* **`id`**: Primary Key (Integer, Auto-increment).
* **`name`**: Student name.
* **`father_name`**: Father's name.
* **`class`**: Current class or grade (corresponds to sheet names like PG, One, Prep).
* **`monthly_fee`**: Current tuition fee rate (e.g., Rs. 2,600).
* **`start_month`**: Calendar month when this student's billing record begins (default `3` for March).
* **`start_year`**: Calendar year when billing begins (default `2026`).

### 2. `fees` Table
Stores ledger payment history.
* **`id`**: Primary Key (Integer, Auto-increment).
* **`student_id`**: Foreign Key linking to `students.id`.
* **`month`**: Billed month string (e.g., `March`, `April`).
* **`year`**: Billed year (Integer).
* **`paid_amount`**: Amount deposited by the student.
* **`date_paid`**: Date transaction occurred (YYYY-MM-DD format).

### 3. `users` Table
Handles administrative credentials.
* **`id`**: Primary Key (Integer).
* **`username`**: Unique administrative login (`admin`).
* **`password`**: Hashed administrative password.

### 4. `settings` Table
Key-value parameters database for configurable school settings.
* **`key`**: Configuration key (e.g., `school_name`).
* **`value`**: Configuration value text.

---

## 🧮 Arrears & Fee Calculation Formulas

The billing engine calculates arrears dynamically, avoiding data corruption and ensuring real-time correctness:

1. **Prior Billing Months Count ($N$):**
   Determined by calculating the calendar months difference between the student's admission/start date and the current billing month:
   $$N = (\text{Target Year} - \text{Start Year}) \times 12 + (\text{Target Month Num} - \text{Start Month})$$
   *If $N < 0$, it is set to $0$ (the student has not yet entered their billing cycle).*

2. **Total Cumulative Due Prior to Billing Month:**
   $$\text{Total Due Prior} = \text{Student's Monthly Fee} \times N$$

3. **Total Cumulative Payments Prior to Billing Month:**
   $$\text{Total Paid Prior} = \sum (\text{Paid Amount in fees table where Year/Month is before Target Year/Month})$$

4. **Previous Unpaid Arrears:**
   $$\text{Arrears} = \max(0, \text{Total Due Prior} - \text{Total Paid Prior})$$

5. **Total Payable Amount (Before Due Date):**
   $$\text{Total Payable} = \text{Student's Monthly Fee} + \text{Arrears}$$

6. **Total Payable Amount (After Due Date):**
   $$\text{Payable After Due Date} = \text{Total Payable} + \text{Late Payment Surcharge}$$
   *(Late Payment Surcharge defaults to Rs. 100 and is configurable in Settings).*

---

## 📄 Printable Challan Voucher Design

The voucher template (`templates/voucher.html`) generates **3 copies side-by-side on a single landscape page** (A4 size). It matches the layout from `Sample Voucher.docx`:
* **Copies generated:** *Bank Copy*, *Campus Copy*, and *Student Copy*.
* **Visual Dividers:** Divided by clean, vertical dashed lines featuring scissors symbols (`✂`) to mark cut paths.
* **Content Inclusions:**
  * School Name & Campus details.
  * Unique Challan Serial number (derived from current year and Student ID).
  * Issue Date and Due Date.
  * Student Name, Father's Name, Class, and ID.
  * Particulars table listing Tuition Fee and Arrears separately.
  * Total Payable by due date and Total Payable after due date (with late surcharge).
  * Bank instructions and designated signature lines (Depositor, Principal).
* **Print Optimization:** The page utilizes an `@media print` style block that hides navigation bars, header dashboards, and action buttons, switching to high-contrast black-and-white layouts fitting A4 landscape margins.

---

## ⚡ Instructions to Run Locally

Follow these steps to launch the system on a local machine:

### Method 1: Using the Batch Launcher (Recommended)
1. Double-click the **`Run Studio.bat`** script in the `e:\SMS` directory.
2. The batch launcher will automatically:
   * Verify your Python installation.
   * Scan and install any missing library dependencies (`flask`, `openpyxl`, `pandas`).
   * Boot up the local web server on port `5000` in a minimized background process.
   * Open your default internet browser to the login portal: **`http://localhost:5000`**.
3. Log in with the default credentials:
   * **Username:** `admin`
   * **Password:** `admin`
4. Once you are done, press any key in the Command Prompt batch window to safely close the background server.

### Method 2: Manual Start (Command Line)
If you prefer running commands manually, execute the following in your shell:
```powershell
# 1. Install dependencies
pip install flask openpyxl pandas

# 2. Initialize database and import the Excel spreadsheet (Required only once)
python import_excel.py

# 3. Start the server
python app.py
```
After executing, navigate to `http://localhost:5000` in your web browser.
