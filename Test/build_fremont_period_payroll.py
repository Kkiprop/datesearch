import os
import sys
from typing import Dict, Any, Tuple

import pandas as pd


# Ensure project root (which contains the "scripts" package) is on sys.path
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(THIS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.compute_payroll_estimates_new_timecard import (  # type: ignore[import]
    build_rate_maps,
    parse_hours,
    normalize_name,
    parse_timecard_report,
)


def find_pay_header_row(df_raw: pd.DataFrame) -> int:
    for index, row in df_raw.iterrows():
        if row.astype(str).str.contains("Employee Name", case=False).any():
            return int(index)
    return -1


def compute_total_from_pay_sheet(pay_path: str, rate_map: Dict[Tuple[str, str], Dict[str, float]]) -> float:
    df_raw = pd.read_excel(pay_path, header=None)
    header_row = find_pay_header_row(df_raw)
    if header_row < 0:
        raise ValueError(f"Could not find Employee Name header in {os.path.basename(pay_path)}")

    df = pd.read_excel(pay_path, skiprows=header_row)

    columns = list(df.columns)

    employee_col = next(
        (col for col in columns if "employee" in str(col).lower() and "name" in str(col).lower()),
        None,
    )
    if employee_col is None:
        raise ValueError("Could not locate Employee Name column in pay sheet")

    reg_hours_col = None
    ot_hours_col = None

    for i in range(1, len(columns)):
        name = str(columns[i]).strip().lower()
        prev = str(columns[i - 1]).strip().lower()

        if name == "hours" and "earning" in prev and "1" in prev:
            reg_hours_col = columns[i]
        if name == "hours" and "earning" in prev and "2" in prev:
            ot_hours_col = columns[i]

    if reg_hours_col is None:
        raise ValueError("Could not find Regular hours column (Earning 1 / Hours)")

    total = 0.0
    missing_rates: set[str] = set()

    for _, row in df.iterrows():
        emp_raw = row.get(employee_col)
        if pd.isna(emp_raw):
            continue

        employee_name = str(emp_raw).strip()
        if not employee_name or "employee name" in employee_name.lower():
            continue

        reg_hours = parse_hours(row.get(reg_hours_col))
        ot_hours = parse_hours(row.get(ot_hours_col)) if ot_hours_col is not None else 0.0

        norm = normalize_name(employee_name)
        rates = rate_map.get(("Fremont", norm))
        if not rates:
            missing_rates.add(employee_name)
            continue

        reg_rate = rates["reg_rate"]
        ot_rate = rates["ot_rate"]

        total += reg_hours * reg_rate + ot_hours * ot_rate

    if missing_rates:
        print("[Pay sheet] Missing rate info for:")
        for name in sorted(missing_rates):
            print("  -", name)

    return total


def compute_total_from_time_sheet(time_path: str, rate_map: Dict[Tuple[str, str], Dict[str, float]]) -> float:
    timesheet = parse_timecard_report(time_path)

    # Aggregate hours per employee across the whole period
    aggregated: Dict[str, Dict[str, float]] = {}
    for _date_key, employees in timesheet.items():
        for emp_name, hours_dict in employees.items():
            reg_h = parse_hours(hours_dict.get("Regular"))
            ot_h = parse_hours(hours_dict.get("Overtime"))

            agg = aggregated.setdefault(emp_name, {"reg": 0.0, "ot": 0.0})
            agg["reg"] += reg_h
            agg["ot"] += ot_h

    total = 0.0
    missing_rates: set[str] = set()

    for emp_name, hrs in aggregated.items():
        norm = normalize_name(emp_name)
        rates = rate_map.get(("Fremont", norm))
        if not rates:
            missing_rates.add(emp_name)
            continue

        reg_rate = rates["reg_rate"]
        ot_rate = rates["ot_rate"]

        total += hrs["reg"] * reg_rate + hrs["ot"] * ot_rate

    if missing_rates:
        print("[Time sheet] Missing rate info for:")
        for name in sorted(missing_rates):
            print("  -", name)

    return total


def main() -> None:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    ready_dir = os.path.join(project_root, "Ready")
    rate_map, _ = build_rate_maps(ready_dir)

    pay_path = os.path.join(project_root, "Test", "Fremont Pay.xlsx")
    time_path = os.path.join(project_root, "Test", "Fremont Time.xlsx")

    print("Computing Fremont payroll for this period using Regular and Overtime rates only...\n")

    total_pay = compute_total_from_pay_sheet(pay_path, rate_map)
    total_time = compute_total_from_time_sheet(time_path, rate_map)

    print(f"Total payroll from Pay sheet (base rates only): {total_pay:,.2f}")
    print(f"Total payroll from Time sheet (base rates only): {total_time:,.2f}")
    diff = total_time - total_pay
    print(f"Difference (Time - Pay): {diff:,.2f}")


if __name__ == "__main__":
    main()
