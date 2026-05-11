"""
excel_export.py
---------------
Generates Excel files from SQL query results.
Uses openpyxl library.
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

# pyrefly: ignore [missing-import]
import openpyxl
# pyrefly: ignore [missing-import]
from openpyxl.styles import Font, PatternFill, Alignment
# pyrefly: ignore [missing-import]
from openpyxl.utils import get_column_letter


def cleanup_old_exports(max_age_minutes: int = 30) -> None:
    """
    Delete Excel files older than max_age_minutes.
    Called at start of generate_excel() to keep disk clean.
    """
    exports_dir = Path(__file__).parent.parent / "exports"
    if not exports_dir.exists():
        return

    now = datetime.now()
    for file in exports_dir.glob("*.xlsx"):
        try:
            age_seconds = (now - datetime.fromtimestamp(
                file.stat().st_mtime
            )).total_seconds()
            age_minutes = age_seconds / 60
            if age_minutes > max_age_minutes:
                file.unlink()
                print(f"[ExcelExport] Deleted old file: {file.name}")
        except Exception as e:
            print(f"[ExcelExport] Could not delete {file.name}: {e}")


def generate_excel(
    results: list[dict],
    filename: str | None = None
) -> str:
    """
    Generate an Excel file from SQL query results.

    Args:
        results: List of dicts from database (each dict = one row)
        filename: Optional custom filename

    Returns:
        Absolute path to generated .xlsx file
    """
    # Step 1: Clean up old files first
    cleanup_old_exports()

    # Step 2: Create exports directory
    exports_dir = Path(__file__).parent.parent / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    # Step 3: Generate filename with timestamp
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"query_results_{timestamp}.xlsx"

    filepath = exports_dir / filename

    # Step 4: Create workbook and sheet
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Query Results"

    if not results:
        wb.save(str(filepath))
        return str(filepath)

    # Step 5: Get headers from first row
    headers = list(results[0].keys())

    # Step 6: Style definitions
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(
        start_color="4F8EF7",
        end_color="4F8EF7",
        fill_type="solid"
    )
    alt_fill = PatternFill(
        start_color="F0F4FF",
        end_color="F0F4FF",
        fill_type="solid"
    )
    center_align = Alignment(horizontal="left", vertical="center")

    # Step 7: Write header row
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=str(header))
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align

    # Step 8: Write data rows with alternating colors
    for row_idx, row_data in enumerate(results, start=2):
        is_alternate = (row_idx % 2 == 0)
        for col_idx, header in enumerate(headers, start=1):
            value = row_data.get(header, "")

            # Convert non-serializable types
            if hasattr(value, "isoformat"):
                value = value.isoformat()
            elif not isinstance(value, (str, int, float, bool, type(None))):
                value = str(value)

            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.alignment = center_align
            if is_alternate:
                cell.fill = alt_fill

    # Step 9: Auto-fit column widths
    for col_idx, header in enumerate(headers, start=1):
        col_letter = get_column_letter(col_idx)

        # Max width based on header and data
        max_width = len(str(header))
        for row_data in results[:100]:  # Check first 100 rows only
            cell_val = str(row_data.get(header, ""))
            max_width = max(max_width, len(cell_val))

        # Cap width between 10 and 50
        ws.column_dimensions[col_letter].width = min(max(max_width + 2, 10), 50)

    # Step 10: Freeze header row
    ws.freeze_panes = "A2"

    # Step 11: Save file
    wb.save(str(filepath))
    print(f"[ExcelExport] Generated: {filename} ({len(results)} rows)")

    return str(filepath)

def should_offer_excel(
    results: list[dict],
    question: str,
    row_count: int
) -> bool:
    """
    Decide if Excel download should be offered to the user.

    Returns True if:
      1. User explicitly asked for excel/download/export/file, OR
      2. Result is list-type: more than 1 row AND more than 1 column

    Returns False for:
      - Count/aggregation queries (single row, single column)
      - Empty results
    """
    if not results or row_count == 0:
        return False

    # Case 1: User explicitly asked for Excel or file download
    excel_keywords = [
        "excel", "download", "export",
        "sheet", "spreadsheet", "file",
        "csv", "save", "generate file"
    ]
    if any(kw in question.lower() for kw in excel_keywords):
        return True

    # Case 2: List-type result (multiple rows AND multiple columns)
    num_columns = len(results[0].keys()) if results else 0
    if row_count > 1 and num_columns > 1:
        return True

    # Single value, count, sum, avg = no Excel needed
    return False