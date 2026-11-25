# KRISHNA COLOUR – ASIAN PAINTS
## Complete Production-Ready Inventory & Shop Management System

A production-grade, centralized, database-driven inventory, Point-of-Sale (POS), billing, and shop management system architected specifically for **Krishna Colour – Asian Paints**.

Built with **Python**, **Streamlit**, **PostgreSQL** / **SQLAlchemy ORM**, **ReportLab**, **Plotly**, **OpenPyXL**, and secured with **Argon2 / bcrypt** password hashing.

---

## 🎨 System Highlights

1. **Executive Dashboard**:
   - Live KPI cards calculated directly from real database records (Zero hardcoded metrics).
   - Sales trends (Daily, Monthly, Average Bill Value).
   - Real-time inventory valuation (Purchase Cost vs Retail Selling Value).
   - Aging customer receivables (>30 days overdue).
   - Tabular quick-monitors for low-stock alerts, high-pending dues, recent invoices, and partner shop returns.
2. **Product Catalog & Inventory**:
   - Full paint catalog with brand, category, subcategory, unit of measure (Litre, KG, Bucket, Can, etc.).
   - Decimal monetary precision for purchase and selling rates.
   - Excel and CSV bulk catalog import with line-by-line validation preview (never silently drops rows).
   - Real-time stock movement ledger (Stock In, Stock Out, Bill Sale, Shop Issue, Returns).
   - Strict negative stock prevention with authorized administrator override.
   - Transaction cancellation with exact-once inventory reversal.
3. **Customer Management & Ledger Statements**:
   - Unlimited bills per customer account.
   - Real-time computation of total billed, total collected, and net outstanding balance.
   - Printable Customer Account Statement (PDF & Excel).
   - Soft-deletion protection preserving historical financial integrity.
4. **Billing & POS System**:
   - Supports BOTH **Manual bill numbering** (e.g. `244`, `245`, `246`) and **Automatic sequential numbering** (e.g. `KC-2026-0001`).
   - Strict duplicate bill number prevention.
   - Multi-item bills with line discounts and GST/tax calculations.
   - Automatic inventory deduction upon invoice finalization.
   - Draft bills do not alter inventory.
   - Cancelled bills reverse inventory effects exactly once.
   - High-resolution, professional printable PDF invoices generated with ReportLab.
5. **Payment Collections**:
   - Multiple payments against a single invoice.
   - Supports Cash, UPI, Bank Transfer, Cheque, and Other.
   - Automatic balance updates across bills and customer accounts.
   - Overpayment protection.
   - Audited payment reversals/refunds.
6. **Other Shops Management & Returns**:
   - Dedicated partner paint shop registry.
   - Issue products to other shops (tracked separately from retail sales).
   - Multi-stage partial returns (e.g., takes 10 buckets, returns 6, then 2, then 2).
   - Returned products increase store inventory only upon confirmation.
   - Explicit **"MARK AS DONE"** verification that prohibits premature completion while unreturned items remain.
7. **15 Comprehensive Business Reports**:
   - Daily, Weekly, Monthly, and Annual Sales.
   - Customer-wise and Product-wise Sales.
   - Stock In, Stock Out, Current Inventory, and Low Stock Reports.
   - Customer Pending Payments & Payment Collections.
   - Other-Shop Transactions, Pending Returns, and Completed Returns.
   - One-click export to formatted Excel (.xlsx) and CSV.
8. **Enterprise Security & Disaster Recovery**:
   - Initial administrative password: **`1454`** (securely hashed with Argon2id / bcrypt).
   - Configurable without code changes via `.env` or Streamlit secrets.
   - Secure in-app password change mechanism.
   - Role-Based Access Control (RBAC): Administrator vs Staff.
   - Login rate-limiting and automatic lockout protection.
   - Session timeout management.
   - Complete audit logging of all operational activities.
   - One-click database backup and validated disaster restore.

---

## 🏗️ Technology Stack

| Layer | Technology |
|---|---|
| **Frontend UI** | Streamlit, Custom Responsive CSS (`#F8FAFC`, `#FFFFFF`, `#172033`, `#2563EB`, `#DC2626`) |
| **Backend & Logic** | Python 3.10+ / 3.14 (Modular service architecture) |
| **Database** | PostgreSQL / SQLite (via SQLAlchemy 2.0 ORM & Alembic migrations) |
| **PDF Generation** | ReportLab (A4 printable invoices and statements) |
| **Spreadsheets** | OpenPyXL & Pandas (Styled Excel exports and validated imports) |
| **Analytics & Charts** | Plotly Express & Plotly Graph Objects |
| **Security & Auth** | Argon2id (`argon2-cffi`) / `bcrypt` password hashing |

---

## 🚀 Quick Start & Local Setup

### 1. Clone or Open Project Directory
```bash
cd "d:\Krishna Colour"
```

### 2. Install Required Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env`:
```ini
# Centralized PostgreSQL connection (or leave as SQLite for zero-config local run)
DATABASE_URL=sqlite:///krishna_colour.db

# Initial Admin Password (default is 1454)
INITIAL_ADMIN_PASSWORD=1454

# Application Secret Key
SECRET_KEY=krishna-colour-asian-paints-super-secret-key-change-in-production

# Session Timeout (minutes)
SESSION_TIMEOUT_MINUTES=60
```

### 4. Run the Application
```bash
streamlit run app.py
```
Open your browser at `http://localhost:8501`.

### 5. Initial Log In
- **Username:** `admin`
- **Password:** `1454`

*(Once logged in, you can change the password at any time from the **Settings** page).*

---

## 🗄️ Database Architecture & Migrations

The database models are defined in `database/models.py`.

### Database Tables:
1. `users`: System user credentials, roles (`admin`, `staff`), and status.
2. `customers`: Customer profiles, codes (`KC-CUST-xxxx`), contacts, and ledger history.
3. `products`: Inventory catalog, categories, pricing, stock levels, and alert thresholds.
4. `categories`: Paint categories (Interior, Exterior, Enamel, Waterproofing, Tools).
5. `suppliers`: Paint distributors and depot contacts.
6. `bills`: Invoices, manual/auto numbering, tax, discounts, totals, and lifecycle states.
7. `bill_items`: Multi-product line items with quantities and unit prices.
8. `payments`: Payment receipts, payment methods (Cash, UPI, Cheque, etc.), and bill allocations.
9. `stock_transactions`: Complete transactional ledger of all stock movements.
10. `other_shops`: Partner paint shop directory.
11. `shop_issues`: Product issue transactions to other shops.
12. `shop_issue_items`: Items and quantities issued to partner shops.
13. `shop_returns`: Confirmed return records from partner shops.
14. `shop_return_items`: Individual items returned with condition notes.
15. `audit_logs`: Immutable audit trail for security and regulatory compliance.
16. `business_settings`: Dynamic shop profile, GSTIN, address, and invoice terms.
17. `backup_logs`: History and status of database backup archives.

### Running Migrations with Alembic:
```bash
alembic upgrade head
```
*(Note: When running `app.py`, `init_db()` automatically ensures all tables and required baseline configurations are seeded if they do not yet exist).*

---

## 🧪 Automated Test Suite

A comprehensive test suite verifies all mandatory business rules, transaction balances, stock deductions, and security checks.

To run the master test runner:
```bash
python tests/run_all_tests.py
```

Or using `pytest`:
```bash
pytest tests/
```

### Test Coverage Highlights:
- **Authentication**: Password hashing with Argon2/bcrypt, valid/invalid logins, rate-limiting lockout, and role restrictions.
- **Inventory**: Product CRUD, stock in/out, negative stock prevention, and transaction reversal.
- **Billing**: Manual bill numbering (`244`), auto bill numbering, duplicate bill number blocking, multi-item line total precision, stock auto-deduction upon finalization, and cancellation stock restoration.
- **Payments**: Partial payments, multiple payments per invoice, overpayment prevention, receipt generation, and payment reversal.
- **Other Shops**: Issue creation, multi-stage partial returns (10 -> 6 -> 2 -> 0), "MARK AS DONE" verification, and inventory re-stocking.
- **Reports**: Verification of all 15 report generation queries and live dashboard aggregations.

---

## 🚢 Production Deployment

### Option A: Cloud Managed PostgreSQL (AWS RDS / Supabase / Neon / Render)
1. Provision a PostgreSQL instance.
2. Set the environment variable in your production environment or Streamlit secrets:
   ```ini
   DATABASE_URL=postgresql+psycopg://postgres:your_password@your_db_host:5432/krishna_colour
   INITIAL_ADMIN_PASSWORD=your_strong_admin_password
   SECRET_KEY=generate_a_random_32_byte_secret_key
   ```
3. Run migrations or launch `streamlit run app.py`. All application nodes will share the same central database.

### Option B: Linux VPS / Docker
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

---

## 📦 Importing Business Owner's Real Product Catalog

1. Log into the system as `admin`.
2. Navigate to the **Products** page.
3. Switch to the **Excel / CSV Import** tab.
4. Click **Download Excel Template** to inspect the required columns:
   - `Product Name` *(Mandatory)*
   - `Category` *(Mandatory)*
   - `Unit` *(e.g. Litre, KG, Bucket)*
   - `Purchase Price` *(Cost price per unit)*
   - `Selling Price` *(Retail selling rate)*
   - `Opening Stock` *(Initial physical count)*
   - `Min Stock Level` *(Alert threshold, default 5)*
   - `Brand`, `Subcategory`, `Product Code`, `Description` *(Optional)*
5. Upload the completed Excel (`.xlsx`) or CSV file.
6. The system previews all valid rows and flags any invalid row with exact row numbers and error descriptions.
7. Click **Confirm & Import Valid Products Into Database**.

---

## 🔒 Security & Disaster Recovery

- **Data Privacy:** Database credentials, secrets, and raw password hashes are strictly kept on the server and never exposed to the frontend.
- **Financial Calculations:** All monetary arithmetic uses `decimal.Decimal` to avoid floating-point inaccuracies.
- **Database Backup:** Administrators can trigger on-demand backups or download historical archives from the **Settings -> Database Backups** tab.
- **Disaster Restore:** Backups can be restored with safety verification requiring the administrator to type `RESTORE DATABASE`.

---

© Krishna Colour – Asian Paints. All Rights Reserved.
