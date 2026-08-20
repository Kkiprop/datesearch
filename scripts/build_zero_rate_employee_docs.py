#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import List, Dict, Any

import pandas as pd


REQUIRED_COLUMNS = [
    "Employee Name",
    "Store",
    "Regular Rate",
    "Overtime Rate",
    "Total Earnings",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build one JSON document per employee for the employees listed in "
            "employee_details_zero_rates.xlsx."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("employee_details_zero_rates.xlsx"),
        help="Path to the Excel workbook containing the 36 zero-rate employees.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/employee_details_zero_rates.json"),
        help="Destination path for the generated JSON document.",
    )
    return parser.parse_args()


def validate_columns(frame: pd.DataFrame) -> None:
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def build_documents(frame: pd.DataFrame) -> List[Dict[str, Any]]:
    documents: List[Dict[str, Any]] = []

    for _, row in frame.iterrows():
        employee_name = str(row["Employee Name"]).strip()
        if not employee_name:
            continue

        total_earnings = float(row["Total Earnings"] or 0.0)
        documents.append({
            "Employee Name": employee_name,
            "Store": str(row["Store"]).strip(),
            "Regular": round(float(row["Regular Rate"] or 0.0), 4),
            "Overtime": round(float(row["Overtime Rate"] or 0.0), 4),
            "Pay": round(total_earnings / 10.0, 2),
        })

    return documents


def main() -> int:
    args = parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"Input workbook not found: {args.input}")

    frame = pd.read_excel(args.input)
    validate_columns(frame)
    documents = build_documents(frame)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(documents, handle, indent=2)

    print(f"Wrote {len(documents)} employee documents to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())