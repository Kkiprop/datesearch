#!/usr/bin/env python3
import argparse
from pathlib import Path
import re
from typing import Dict, Optional, Tuple

import sys
import pandas as pd


HEADER_FROM_PATTERN = re.compile(r"check\s+dates?\s+from", re.IGNORECASE)
HEADER_TO_PATTERN = re.compile(r"\bto\b", re.IGNORECASE)
DATE_PATTERN = re.compile(r"(\d{1,2}/\d{1,2}/\d{2,4})")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Enrich zero-rows employee details with pay-period information and earnings "
            "by looking up each employee in the store payroll Excel workbooks."
        )
    )
    parser.add_argument(
        "--zero-rows",
        type=Path,
        default=Path("outputs/zero_rows_employee_details_unique.csv"),
        help="Path to the zero-rows employee details CSV.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/zero_rows_employee_details_with_earnings.csv"),
        help="Destination CSV with additional period and earnings columns.",
    )
    parser.add_argument(
        "--header-row",
        type=int,
        default=6,
        help=(
            "Row number (0-indexed) that contains the payroll table headers in the Excel "
            "files (matches other scripts; typically row 7 in Excel)."
        ),
    )
    return parser.parse_args()


def find_employee_column(columns) -> Optional[str]:
    lower_map = {str(c).strip().lower(): c for c in columns}
    candidates = ["employee name", "employee", "name"]
    for key in lower_map:
        for cand in candidates:
            if cand == key or cand in key:
                return lower_map[key]
    return None


def find_total_earnings_column(columns) -> Optional[str]:
    lower_map = {str(c).strip().lower(): c for c in columns}
    candidates = ["total earnings", "earnings", "total pay"]
    for key in lower_map:
        for cand in candidates:
            if cand == key or cand in key:
                return lower_map[key]
    return None


def extract_period_from_header(workbook_path: Path) -> Optional[Tuple[pd.Timestamp, pd.Timestamp]]:
    """Scan the top few rows of the first sheet for a 'Check Dates From ... To ...' string.

    Uses pandas to read the header area so we don't depend on openpyxl directly.
    """

    try:
        header_df = pd.read_excel(
            workbook_path,
            sheet_name=0,
            header=None,
            nrows=10,
        )
    except Exception:
        return None

    from_text: Optional[str] = None
    to_text: Optional[str] = None

    # Search a reasonable area (first 10 rows, all columns read)
    for _, row in header_df.iterrows():
        for val in row.tolist():
            if not isinstance(val, str):
                continue
            lower_val = val.lower()
            # Example: "Check Dates From: 9/30/2025 - Prior 1"
            if from_text is None and HEADER_FROM_PATTERN.search(lower_val):
                m = DATE_PATTERN.search(val)
                if m:
                    from_text = m.group(1).strip()
            # Example: "To: 2/11/2026 - Payroll 1"
            if to_text is None and HEADER_TO_PATTERN.search(lower_val):
                m = DATE_PATTERN.search(val)
                if m:
                    to_text = m.group(1).strip()
        if from_text and to_text:
            break

    if not (from_text and to_text):
        return None

    start = pd.to_datetime(from_text, errors="coerce")
    end = pd.to_datetime(to_text, errors="coerce")
    if pd.isna(start) or pd.isna(end):
        return None
    return start.normalize(), end.normalize()


def build_store_workbook_map(base_dir: Path) -> Dict[str, Path]:
    """Map store names (as in the zero-rows CSV) to workbook paths.

    This follows the naming convention in the current workspace.
    """

    candidates = {
        "AMFC": "AMFC.xlsx",
        "Fremont": "Fremont.xlsx",
        "Karthik": "Karthik.xlsx",
        "Milpitas": "Milpitas.xlsx",
        "Sunnyvale": "sunnyvale.xlsx",
        "Panwaari": "Panwaari.xlsx",
    }

    mapping: Dict[str, Path] = {}
    for store, filename in candidates.items():
        path = base_dir / filename
        if path.exists():
            mapping[store] = path
    return mapping


def load_payroll_for_workbook(
    workbook_path: Path, header_row: int
) -> Tuple[Optional[pd.DataFrame], Optional[Tuple[pd.Timestamp, pd.Timestamp]]]:
    try:
        frame = pd.read_excel(workbook_path, sheet_name=0, header=header_row)
    except Exception as exc:
        print(f"Failed to read {workbook_path} with header_row={header_row}: {exc}")
        return None, None

    # Debug: show detected columns for this workbook.
    print(f"Loaded {workbook_path.name} with header_row={header_row}; columns: {list(frame.columns)}")

    emp_col = find_employee_column(frame.columns)
    earn_col = find_total_earnings_column(frame.columns)
    if emp_col is None or earn_col is None:
        return None, None

    period = extract_period_from_header(workbook_path)
    return frame[[emp_col, earn_col]].copy(), period


def normalize_name(name: object) -> str:
    return str(name).strip().lower()


def main() -> int:
    # Simple runtime info to ensure we're using the expected interpreter.
    print(f"Running with Python: {sys.executable}")

    args = parse_args()

    if not args.zero_rows.exists():
        print(f"Zero-rows CSV not found: {args.zero_rows}")
        return 1

    try:
        zero_df = pd.read_csv(args.zero_rows)
    except Exception as exc:
        print(f"Failed to read zero-rows CSV: {exc}")
        return 1

    base_dir = args.zero_rows.parent.parent if args.zero_rows.parent.name == "outputs" else args.zero_rows.parent
    store_to_workbook = build_store_workbook_map(base_dir)

    # Preload data from all relevant workbooks.
    employee_lookup: Dict[str, Dict[str, object]] = {}

    for store, workbook in store_to_workbook.items():
        frame, period = load_payroll_for_workbook(workbook, args.header_row)
        if frame is None:
            print(f"Skipping workbook (no suitable columns): {workbook}")
            continue

        if period is None:
            print(f"Could not extract period header from {workbook}; earnings will still be used without dates.")
        start, end = period if period is not None else (None, None)
        if start is not None and end is not None:
            num_days = (end - start).days + 1
        else:
            num_days = None

        for _, row in frame.iterrows():
            name = row.iloc[0]
            earnings = row.iloc[1]
            if pd.isna(name) or pd.isna(earnings):
                continue
            key = normalize_name(name)
            employee_lookup.setdefault(key, {})[store] = {
                "total_earnings": float(earnings),
                "start": start,
                "end": end,
                "num_days": num_days,
                "workbook": workbook.name,
            }

    # Prepare new columns.
    zero_df["Period"] = ""
    zero_df["Number of days"] = pd.NA
    zero_df["Total Earnings"] = pd.NA
    zero_df["Earnings Per day"] = pd.NA

    # Use store-specific workbook first, then fall back to any match.
    for idx, row in zero_df.iterrows():
        name = row.get("Employee Name")
        store = row.get("Store")
        if pd.isna(name):
            continue
        key = normalize_name(name)

        store_data = employee_lookup.get(key, {})
        info = None

        # Try matching by store name.
        if isinstance(store, str) and store in store_data:
            info = store_data[store]
        elif store_data:
            # Fallback: use any store match for this employee.
            # This handles cases where store labels differ slightly.
            info = next(iter(store_data.values()))

        if not info:
            continue

        total = info.get("total_earnings")
        start = info.get("start")
        end = info.get("end")
        num_days = info.get("num_days")

        if start is not None and end is not None:
            period_str = f"{start.strftime('%d/%m/%y')} to {end.strftime('%d/%m/%y')}"
            zero_df.at[idx, "Period"] = period_str
        if num_days is not None:
            zero_df.at[idx, "Number of days"] = int(num_days)
        if total is not None:
            zero_df.at[idx, "Total Earnings"] = float(total)
            if num_days and num_days > 0:
                zero_df.at[idx, "Earnings Per day"] = float(total) / num_days

    args.output.parent.mkdir(parents=True, exist_ok=True)
    zero_df.to_csv(args.output, index=False)
    print(f"Wrote enriched zero-rows data to {args.output}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
