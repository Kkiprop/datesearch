import argparse
import re
from pathlib import Path
import sys

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Summarize total hours for employees whose payment check date matches the selected date."
        )
    )
    parser.add_argument("file", type=Path, help="Path to the Excel file to inspect.")
    parser.add_argument(
        "check_date",
        nargs="?",
        help=(
            "Date to find (YYYY-MM-DD or any pandas-parsable format). If omitted you will be prompted."
        ),
    )
    parser.add_argument(
        "--sheet",
        default=0,
        help="Worksheet index or name; defaults to the first worksheet.",
    )
    parser.add_argument(
        "--header-row",
        type=int,
        default=6,
        help="Row number (0-indexed) that contains the table headers.",
    )
    parser.add_argument(
        "--date-column",
        default=r"Payment\s+\d+\s+Check Date",
        help=(
            "Regex pattern for check date columns. Default matches labels like 'Payment  1  Check Date'."
        ),
    )
    parser.add_argument(
        "--hours-column",
        default="Total Hours",
        help="Column that stores the total hours for each employee.",
    )
    return parser.parse_args()


def normalize_date(value: str) -> pd.Timestamp:
    """Parse a date string and drop time components."""

    parsed = pd.to_datetime(value, errors="raise")
    return parsed.normalize()


def main() -> int:
    args = parse_args()

    if not args.file.exists():
        print(f"File not found: {args.file}")
        return 1

    if args.check_date is None:
        try:
            args.check_date = input("Enter check date: ").strip()
        except EOFError:
            print("No date provided.")
            return 1

    if not args.check_date:
        print("Check date is required.")
        return 1

    try:
        frame = pd.read_excel(args.file, sheet_name=args.sheet, header=args.header_row)
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to read Excel file: {exc}")
        return 1

    hours_column = args.hours_column
    if hours_column not in frame.columns:
        available = ", ".join(str(col) for col in frame.columns if "Hours" in str(col))
        print(
            f"Missing hours column: {hours_column}. Available hours-like columns: {available}"
        )
        return 1

    try:
        column_pattern = re.compile(args.date_column)
    except re.error as exc:
        print(f"Invalid date column pattern '{args.date_column}': {exc}")
        return 1

    matching_columns = [
        col
        for col in frame.columns
        if isinstance(col, str) and column_pattern.fullmatch(str(col).strip())
    ]

    if not matching_columns:
        available = ", ".join(
            str(col) for col in frame.columns if "Check Date" in str(col)
        )
        print(
            "No columns matched the pattern. "
            f"Pattern: {args.date_column}. Available check date columns: {available}"
        )
        return 1

    try:
        target_date = normalize_date(args.check_date)
    except Exception as exc:  # noqa: BLE001
        print(f"Unable to parse check date '{args.check_date}': {exc}")
        return 1

    # Build a combined mask for any column matching the target date.
    any_match = pd.Series(False, index=frame.index, dtype=bool)
    per_column_counts = []

    for column in matching_columns:
        column_dates = pd.to_datetime(frame[column], errors="coerce").dt.normalize()
        column_mask = column_dates == target_date
        count = int(column_mask.sum())
        if count:
            per_column_counts.append((column, count))
            any_match |= column_mask

    if not per_column_counts:
        print("No match found.")
        return 1

    hours_series = pd.to_numeric(frame[hours_column], errors="coerce")
    total_hours = float(hours_series[any_match].sum())
    employee_count = int(any_match.sum())

    print(f"Match found for {employee_count} employee(s) totaling {total_hours:.2f} hours:")
    for column, count in per_column_counts:
        print(f"  {column}: {count} employee(s)")

    print(frame.loc[any_match, list(matching_columns) + [hours_column]])

    return 0


if __name__ == "__main__":
    sys.exit(main())
