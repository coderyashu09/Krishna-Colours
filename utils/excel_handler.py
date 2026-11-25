"""
Excel and CSV import/export handler.
Provides structured data export with OpenPyXL formatting and rigorous, non-silent import validation.
"""
import io
from decimal import Decimal, InvalidOperation
from typing import List, Dict, Any, Tuple, Optional
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from config.settings import settings
from utils.validators import validate_mobile, parse_decimal


def export_dataframe_to_excel(df: pd.DataFrame, sheet_name: str = "Data", title: Optional[str] = None) -> bytes:
    """
    Format and export a pandas DataFrame into a beautifully styled Excel spreadsheet.
    Returns bytes of the .xlsx file.
    """
    output = io.BytesIO()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name[:31]

    # Theme colors
    header_fill = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    data_font = Font(name="Segoe UI", size=10)
    border_thin = Side(border_style="thin", color="E5E7EB")
    border_box = Border(left=border_thin, right=border_thin, top=border_thin, bottom=border_thin)

    start_row = 1
    if title:
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(len(df.columns), 1))
        title_cell = ws.cell(row=1, column=1, value=title)
        title_cell.font = Font(name="Segoe UI", size=14, bold=True, color="172033")
        title_cell.alignment = Alignment(horizontal="left", vertical="center")
        ws.row_dimensions[1].height = 25
        start_row = 3

    # Header Row
    for col_idx, col_name in enumerate(df.columns, start=1):
        cell = ws.cell(row=start_row, column=col_idx, value=str(col_name))
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center" if "date" in col_name.lower() or "#" in col_name else "left", vertical="center")
        cell.border = border_box
    ws.row_dimensions[start_row].height = 22

    # Data Rows
    for row_idx, row_data in enumerate(df.values, start=start_row + 1):
        for col_idx, value in enumerate(row_data, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.font = data_font
            cell.border = border_box
            # Align numeric columns right
            if isinstance(value, (int, float, Decimal)):
                cell.alignment = Alignment(horizontal="right", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")
        ws.row_dimensions[row_idx].height = 18

    # Auto-adjust column widths
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or "")
            if len(val_str) > max_len and cell.row >= start_row:
                max_len = len(val_str)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    wb.save(output)
    output.seek(0)
    return output.getvalue()


def parse_and_validate_products_import(
    file_bytes: bytes,
    file_name: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Parse and validate imported product spreadsheet (.xlsx, .xls, .csv).
    Returns (valid_rows, error_rows).
    Never silently discards any invalid row.
    """
    # Read file
    if file_name.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(file_bytes), dtype=str)
    else:
        df = pd.read_excel(io.BytesIO(file_bytes), dtype=str)

    df = df.fillna("")

    # Map column headers case-insensitively
    col_map = {str(c).strip().lower(): str(c) for c in df.columns}

    def get_val(row, *aliases):
        for alias in aliases:
            for k in col_map:
                if alias.lower() in k:
                    return str(row[col_map[k]]).strip()
        return ""

    valid_rows = []
    error_rows = []

    for index, row in df.iterrows():
        row_num = index + 2  # Excel 1-based indexing with header
        name = get_val(row, "product name", "product", "item name", "name")
        category = get_val(row, "category", "cat")
        unit = get_val(row, "unit", "uom") or "Litre"
        purchase_price_raw = get_val(row, "purchase price", "cost price", "purchase", "rate")
        selling_price_raw = get_val(row, "selling price", "sale price", "selling", "mrp")
        opening_stock_raw = get_val(row, "opening stock", "initial stock", "stock", "quantity", "qty")
        min_stock_raw = get_val(row, "min stock", "min level", "minimum stock") or "5.00"
        code = get_val(row, "product code", "code", "item code", "sku")
        brand = get_val(row, "brand", "company") or "Asian Paints"
        subcategory = get_val(row, "subcategory", "sub-category")
        description = get_val(row, "description", "details")

        errors = []

        if not name:
            errors.append("Product name is required.")
        if not category:
            errors.append("Category is required.")

        try:
            purchase_price = parse_decimal(purchase_price_raw, default=Decimal("0.00"), field_name="Purchase Price")
            if purchase_price < 0:
                errors.append("Purchase price cannot be negative.")
        except Exception as e:
            errors.append(str(e))
            purchase_price = Decimal("0.00")

        try:
            selling_price = parse_decimal(selling_price_raw, default=Decimal("0.00"), field_name="Selling Price")
            if selling_price < 0:
                errors.append("Selling price cannot be negative.")
        except Exception as e:
            errors.append(str(e))
            selling_price = Decimal("0.00")

        try:
            opening_stock = parse_decimal(opening_stock_raw, default=Decimal("0.00"), field_name="Opening Stock")
            if opening_stock < 0:
                errors.append("Opening stock cannot be negative.")
        except Exception as e:
            errors.append(str(e))
            opening_stock = Decimal("0.00")

        try:
            min_stock = parse_decimal(min_stock_raw, default=Decimal("5.00"), field_name="Minimum Stock")
            if min_stock < 0:
                errors.append("Minimum stock cannot be negative.")
        except Exception as e:
            errors.append(str(e))
            min_stock = Decimal("5.00")

        if errors:
            error_rows.append({
                "Row #": row_num,
                "Name": name or "[Empty]",
                "Category": category or "[Empty]",
                "Reason": "; ".join(errors)
            })
        else:
            valid_rows.append({
                "product_code": code or None,
                "name": name,
                "brand": brand,
                "category": category,
                "subcategory": subcategory or None,
                "description": description or None,
                "unit": unit,
                "purchase_price": purchase_price,
                "selling_price": selling_price,
                "opening_stock": opening_stock,
                "min_stock_level": min_stock,
            })

    return valid_rows, error_rows


def parse_and_validate_customers_import(
    file_bytes: bytes,
    file_name: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Parse and validate imported customer list (.xlsx, .csv).
    Returns (valid_rows, error_rows).
    """
    if file_name.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(file_bytes), dtype=str)
    else:
        df = pd.read_excel(io.BytesIO(file_bytes), dtype=str)

    df = df.fillna("")
    col_map = {str(c).strip().lower(): str(c) for c in df.columns}

    def get_val(row, *aliases):
        for alias in aliases:
            for k in col_map:
                if alias.lower() in k:
                    return str(row[col_map[k]]).strip()
        return ""

    valid_rows = []
    error_rows = []

    for index, row in df.iterrows():
        row_num = index + 2
        name = get_val(row, "customer name", "name", "client")
        mobile = get_val(row, "mobile", "phone", "contact")
        alt_mobile = get_val(row, "alternate", "alt mobile", "alternate phone")
        address = get_val(row, "address", "addr")
        city = get_val(row, "city", "town")
        notes = get_val(row, "notes", "remarks")
        code = get_val(row, "customer code", "code", "cust id")

        errors = []
        if not name:
            errors.append("Customer name is required.")

        valid_m, clean_mobile = validate_mobile(mobile)
        if not valid_m:
            errors.append(clean_mobile)

        if errors:
            error_rows.append({
                "Row #": row_num,
                "Name": name or "[Empty]",
                "Mobile": mobile or "[Empty]",
                "Reason": "; ".join(errors)
            })
        else:
            valid_rows.append({
                "customer_code": code or None,
                "name": name,
                "mobile": clean_mobile,
                "alternate_mobile": alt_mobile or None,
                "address": address or None,
                "city": city or None,
                "notes": notes or None,
            })

    return valid_rows, error_rows
