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
    parse_hours,
    normalize_name,
    parse_timecard_report,
)


def find_pay_header_row(df_raw: pd.DataFrame) -> int:
    for index, row in df_raw.iterrows():
        if row.astype(str).str.contains("Employee Name", case=False).any():
            return int(index)
    return -1


def parse_pay_sheet(pay_path: str) -> Dict[str, Dict[str, float]]:
    """Parse Fremont Pay.xlsx into per-employee hours and rates.

    Returns map keyed by normalized employee name with:
      - employee_name
      - reg_hours, ot_hours
      - reg_rate, ot_rate
    using only data from the pay sheet.
    """
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
    reg_rate_col = None
    ot_rate_col = None

    # Identify columns based on exact header text patterns
    for i in range(1, len(columns)):
        raw_name = str(columns[i])
        name = raw_name.strip().lower()
        prev = str(columns[i - 1]).strip().lower()

        # Regular hours/rate: after "Earning  1"
        if name.startswith("hours") and "earning" in prev and "1" in prev:
            reg_hours_col = columns[i]
        if name.startswith("rate") and "earning" in prev and "1" in prev:
            reg_rate_col = columns[i]

        # Overtime hours/rate: after "Earning  2"
        if name.startswith("hours") and "earning" in prev and "2" in prev:
            ot_hours_col = columns[i]
        if name.startswith("rate") and "earning" in prev and "2" in prev:
            ot_rate_col = columns[i]

    # Fallback to known column names if pattern scan above failed
    if reg_hours_col is None:
        for col in columns:
            if str(col).strip().lower() == "hours":
                reg_hours_col = col
                break
    if reg_rate_col is None:
        for col in columns:
            if str(col).strip().lower() == "rate":
                reg_rate_col = col
                break

    if reg_hours_col is None or reg_rate_col is None:
        raise ValueError("Could not find Regular hours/rate columns (Earning 1)")

    pay_map: Dict[str, Dict[str, float]] = {}

    for _, row in df.iterrows():
        emp_raw = row.get(employee_col)
        if pd.isna(emp_raw):
            continue

        employee_name = str(emp_raw).strip()
        if not employee_name or "employee name" in employee_name.lower():
            continue

        reg_hours = parse_hours(row.get(reg_hours_col))
        ot_hours = parse_hours(row.get(ot_hours_col)) if ot_hours_col is not None else 0.0

        # Rates are numeric; treat NaN as 0
        def _rate(val: Any) -> float:
            try:
                v = float(val)
                if pd.isna(v):
                    return 0.0
                return v
            except Exception:
                return 0.0

        reg_rate = _rate(row.get(reg_rate_col))
        ot_rate = _rate(row.get(ot_rate_col)) if ot_rate_col is not None else 0.0

        key = normalize_name(employee_name)
        pay_map[key] = {
            "employee_name": employee_name,
            "reg_hours_pay": float(reg_hours),
            "ot_hours_pay": float(ot_hours),
            "reg_rate": reg_rate,
            "ot_rate": ot_rate,
        }

    return pay_map


def aggregate_time_hours(time_path: str) -> Dict[str, Dict[str, float]]:
    """Aggregate Regular + Overtime hours per employee from Fremont Time.xlsx."""
    timesheet = parse_timecard_report(time_path)

    aggregated: Dict[str, Dict[str, float]] = {}
    for _date_key, employees in timesheet.items():
        for emp_name, hours_dict in employees.items():
            reg_h = parse_hours(hours_dict.get("Regular"))
            ot_h = parse_hours(hours_dict.get("Overtime"))

            key = normalize_name(emp_name)
            agg = aggregated.setdefault(key, {"employee_name": emp_name, "reg_hours_time": 0.0, "ot_hours_time": 0.0})
            agg["reg_hours_time"] += float(reg_h)
            agg["ot_hours_time"] += float(ot_h)

    return aggregated


def build_employee_pay_detail(pay_path: str, time_path: str) -> str:
    pay_map = parse_pay_sheet(pay_path)
    time_map = aggregate_time_hours(time_path)

    # Union of all employees seen in either sheet (by normalized name)
    all_keys = sorted(set(pay_map.keys()) | set(time_map.keys()))

    rows: list[Dict[str, Any]] = []

    for key in all_keys:
        pay_entry = pay_map.get(key, {})
        time_entry = time_map.get(key, {})

        # Prefer name from pay sheet, otherwise from time sheet
        employee_name = (
            pay_entry.get("employee_name")
            or time_entry.get("employee_name")
            or ""
        )

        reg_rate = float(pay_entry.get("reg_rate", 0.0))
        ot_rate = float(pay_entry.get("ot_rate", 0.0))

        reg_hours_pay = float(pay_entry.get("reg_hours_pay", 0.0))
        ot_hours_pay = float(pay_entry.get("ot_hours_pay", 0.0))

        reg_hours_time = float(time_entry.get("reg_hours_time", 0.0))
        ot_hours_time = float(time_entry.get("ot_hours_time", 0.0))

        payroll_pay = reg_hours_pay * reg_rate + ot_hours_pay * ot_rate
        payroll_time = reg_hours_time * reg_rate + ot_hours_time * ot_rate

        # Include every employee, even if everything is zero
        rows.append(
            {
                "Employee Name": employee_name,
                "Reg Hours (Pay)": round(reg_hours_pay, 4),
                "OT Hours (Pay)": round(ot_hours_pay, 4),
                "Reg Hours (Time)": round(reg_hours_time, 4),
                "OT Hours (Time)": round(ot_hours_time, 4),
                "Regular Rate": round(reg_rate, 4),
                "Overtime Rate": round(ot_rate, 4),
                "Payroll (Pay Sheet)": round(payroll_pay, 2),
                "Payroll (Time Sheet)": round(payroll_time, 2),
            }
        )

    output_dir = os.path.join(PROJECT_ROOT, "Test", "Outputs")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "fremont_employee_pay_detail.csv")

    pd.DataFrame(rows).to_csv(output_path, index=False)
    return output_path


def main() -> None:
    pay_path = os.path.join(PROJECT_ROOT, "Test", "Fremont Pay.xlsx")
    time_path = os.path.join(PROJECT_ROOT, "Test", "Fremont Time.xlsx")

    print("Building Fremont employee pay detail from Pay and Time sheets using only Regular & Overtime rates...")
    output_path = build_employee_pay_detail(pay_path, time_path)
    print(f"Wrote employee pay detail CSV to {output_path}")


if __name__ == "__main__":
    main()
