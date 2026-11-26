# Krishna Colour – Asian Paints
## Customer Management System

A focused, database-backed **Customer Management System** built with Python, Streamlit, and SQLAlchemy (PostgreSQL / Supabase Cloud & SQLite fallback).

### Core Features
- **Minimal Executive Dashboard:**
  - Three summary cards: **Year Amount**, **Month Amount** (based on Final Deal Amount), and **Active Customers**.
  - **Payment Pending Customers** table with search and click-to-open customer profile.
- **Customer Directory & Multi-Bill Profiles:**
  - Auto-generated unique Customer IDs (`KC-000001`, `KC-000002`, ...).
  - Multiple manual bill numbers per customer (1 to 5+ digits, e.g., `244`, `245`, `246`, `12540`) with duplicate bill number prevention.
  - Search by Customer Name, Mobile Number, Customer ID, or Bill Number; filter by `All`, `Paid`, `Payment Pending`.
- **Two-Option Item Entry:**
  - **Option A (Dropdown):** Category → Product → Pack Size (`1 L`, `4 L`, `10 L`, `20 L`) loaded from the database.
  - **Option B (Custom Item Textbox):** Manual entry for custom products and sizes.
- **Gujarat Bargaining – Final Deal Amount Logic:**
  - Tracks **Original Amount** (optional reference), **Final Deal Amount** (agreed price), and **Amount Received**.
  - **Pending Amount = Final Deal Amount − Amount Received** (Paid when 0, Payment Pending when > 0).
- **Admin Settings:**
  - Add, rename, archive/deactivate, or delete dropdown Categories, Products, and Pack Sizes while preserving historical customer records.
  - Password updates (Argon2/bcrypt), user management, and database backup/restore.

### Running Locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

### Running Tests
```bash
python tests/run_all_tests.py
```
