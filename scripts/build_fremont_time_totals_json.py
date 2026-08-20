import os
import json
from typing import Any, Dict

import pandas as pd


def parse_hours(value: Any) -> float:
    if value is None:
        return 0.0

    if isinstance(value, (int, float)):
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    text = str(value).strip()
    if not text or text.lower() == "nan":
        return 0.0

    if ":" in text:
        try:
            hours_text, minutes_text = text.split(":", 1)
            hours = int(hours_text)
            minutes = int(minutes_text)
            return hours + minutes / 60.0
        except ValueError:
            return 0.0

    try:
        return float(text)
    except ValueError:
        return 0.0


def extract_hours_from_time_workbook(workbook_path: str) -> Dict[str, Dict[str, float]]:
    """Extract total paid hours per employee from the Fremont Time Excel.

    The workbook is laid out in repeated blocks:
      - Header row with columns including "Employee Name", "Pay Period",
        "Date Range", "Total Paid Hours".
      - The next row contains the employee name and their total hours for
        the pay period.

    Returns mapping: normalized name -> {"employee_name": str, "hours": float}
    """
    df = pd.read_excel(workbook_path, header=None)

    hours_map: Dict[str, Dict[str, float]] = {}

    num_rows = len(df)
    row_idx = 0

    while row_idx < num_rows:
        row = df.iloc[row_idx]
        header_cells = [str(v).strip().lower() for v in row if pd.notna(v)]

        has_employee = any("employee name" in cell for cell in header_cells)
        has_pay_period = any("pay period" in cell for cell in header_cells)
        has_date_range = any("date range" in cell for cell in header_cells)
        has_total_paid = any("total paid hours" in cell for cell in header_cells)

        if has_employee and has_pay_period and has_date_range and has_total_paid:
            full_row_cells = [str(v).strip().lower() if pd.notna(v) else "" for v in row]
            employee_col_idx = next(
                (i for i, cell in enumerate(full_row_cells) if "employee name" in cell), None
            )
            hours_col_idx = next(
                (i for i, cell in enumerate(full_row_cells) if "total paid hours" in cell), None
            )

            next_idx = row_idx + 1
            if employee_col_idx is not None and hours_col_idx is not None and next_idx < num_rows:
                data_row = df.iloc[next_idx]

                emp_raw = data_row.iloc[employee_col_idx]
                hours_raw = data_row.iloc[hours_col_idx]

                if pd.notna(emp_raw):
                    employee_name = str(emp_raw).strip()
                    if employee_name and "total" not in employee_name.lower():
                        key = employee_name  # keep original name as key in this script
                        hours_value = parse_hours(hours_raw)
                        hours_map[key] = {"employee_name": employee_name, "hours": hours_value}

            row_idx += 2
            continue

        row_idx += 1

    return hours_map


def main() -> None:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    input_file = os.path.join(project_root, "Test", "Fremont Time.xlsx")
    output_file = os.path.join(project_root, "outputs", "fremont_time_employee_totals.json")

    hours_map = extract_hours_from_time_workbook(input_file)

    # Convert to a simple list of records for readability
    records = []
    for emp_name, entry in sorted(hours_map.items(), key=lambda kv: kv[0]):
        records.append(
            {
                "Employee Name": entry["employee_name"],
                "Total Paid Hours": round(float(entry["hours"]), 4),
            }
        )

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)

    print(f"Wrote {len(records)} employee total records to {output_file}")


if __name__ == "__main__":
    main()
