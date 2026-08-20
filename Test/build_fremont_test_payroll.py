import json
import os
from collections import defaultdict
from typing import Any

import pandas as pd


def parse_float(value: Any) -> float:
    if value is None:
        return 0.0

    text = str(value).strip()
    if not text or text.lower() == "nan":
        return 0.0

    text = text.replace("$", "").replace(",", "")

    try:
        return float(text)
    except ValueError:
        return 0.0


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


def normalize_name(name: str) -> str:
    if name is None:
        return ""

    normalized = str(name).lower()
    for char in [",", " "]:
        normalized = normalized.replace(char, "")
    return normalized


def find_header_row(df_raw: pd.DataFrame) -> int:
    for index, row in df_raw.iterrows():
        if row.astype(str).str.contains("Employee Name", case=False).any():
            return int(index)
    return -1


def build_earning_groups(columns: list[Any]) -> list[tuple[int, int]]:
    groups: list[tuple[int, int]] = []

    for index, column in enumerate(columns):
        if str(column).lower().startswith("earning"):
            rate_index = index + 2
            if rate_index < len(columns):
                groups.append((index, rate_index))

    return groups


def extract_fremont_rates(payroll_file: str) -> dict[str, dict[str, float]]:
    df_raw = pd.read_excel(payroll_file, header=None)
    header_row = find_header_row(df_raw)
    if header_row < 0:
        raise ValueError("Could not find Employee Name header in Fremont pay sheet")

    df = pd.read_excel(payroll_file, skiprows=header_row)

    employee_col = next(
        (column for column in df.columns if "employee" in str(column).lower() and "name" in str(column).lower()),
        None,
    )
    total_earnings_col = next((column for column in df.columns if "total earnings" in str(column).lower()), None)
    total_taxes_col = next((column for column in df.columns if "total taxes" in str(column).lower()), None)
    total_el_col = next(
        (column for column in df.columns if "total employer liability" in str(column).lower()),
        None,
    )

    if not all([employee_col, total_earnings_col, total_taxes_col, total_el_col]):
        raise ValueError("Missing one or more required payroll detail columns")

    earning_groups = build_earning_groups(list(df.columns))
    rate_map: dict[str, dict[str, float]] = {}

    for _, row in df.iterrows():
        employee_name = row.get(employee_col)
        if pd.isna(employee_name):
            continue

        employee_name = str(employee_name).strip()
        if not employee_name or "total" in employee_name.lower():
            continue

        regular_rate = 0.0

        for earning_index, rate_index in earning_groups:
            label_raw = row.iloc[earning_index]
            label = str(label_raw).strip().lower() if not pd.isna(label_raw) else ""
            if "regular" in label and regular_rate == 0.0:
                regular_rate = parse_float(row.iloc[rate_index])

        total_earnings = parse_float(row.get(total_earnings_col))
        total_taxes = parse_float(row.get(total_taxes_col))
        total_el = parse_float(row.get(total_el_col))
        tax_rate = total_taxes / total_earnings if total_earnings > 0 else 0.0
        el_rate = total_el / total_earnings if total_earnings > 0 else 0.0

        rate_map[normalize_name(employee_name)] = {
            "employee_name": employee_name,
            "regular_rate": regular_rate,
            "overtime_rate": regular_rate * 1.5 if regular_rate > 0 else 0.0,
            "tax_rate": tax_rate,
            "el_rate": el_rate,
        }

    return rate_map


def parse_fremont_timesheet(timecard_file: str) -> dict[str, dict[str, dict[str, float]]]:
    df = pd.read_excel(timecard_file, sheet_name="Summary", header=None)

    data_tree: dict[str, dict[str, dict[str, float]]] = {}
    current_employee: str | None = None
    looking_for_employee = False
    collecting_data = False

    for _, row in df.iterrows():
        row_list = row.tolist()
        row_str = [str(value).strip().lower() for value in row_list if pd.notna(value)]

        if "employee name" in row_str and "pay period" in row_str:
            looking_for_employee = True
            collecting_data = False
            continue

        if looking_for_employee:
            current_employee = str(row_list[0] if pd.notna(row_list[0]) else row_list[1]).strip()
            looking_for_employee = False
            continue

        if "date" in row_str and "regular" in row_str:
            collecting_data = True
            continue

        if collecting_data and current_employee:
            if pd.isna(row[0]) or "total" in str(row[0]).lower():
                collecting_data = False
                continue

            try:
                date_key = pd.to_datetime(row[0]).strftime("%Y-%m-%d")
            except Exception:
                continue

            regular_hours = row[3] if len(row_list) > 3 and pd.notna(row[3]) else 0
            overtime_hours = row[4] if len(row_list) > 4 and pd.notna(row[4]) else 0

            employee_bucket = data_tree.setdefault(date_key, {}).setdefault(
                current_employee,
                {"Regular": 0.0, "Overtime": 0.0},
            )
            employee_bucket["Regular"] += parse_hours(regular_hours)
            employee_bucket["Overtime"] += parse_hours(overtime_hours)

    return data_tree


def compute_fremont_test_payroll(project_root: str) -> tuple[str, str, str, str]:
    test_dir = os.path.join(project_root, "Test")
    output_dir = os.path.join(test_dir, "Outputs")
    os.makedirs(output_dir, exist_ok=True)

    payroll_file = os.path.join(test_dir, "Fremont Pay.xlsx")
    timecard_file = os.path.join(test_dir, "Fremont Time.xlsx")

    rate_map = extract_fremont_rates(payroll_file)
    timesheet = parse_fremont_timesheet(timecard_file)

    employee_daily_records: list[dict[str, Any]] = []
    store_daily_totals: dict[str, float] = defaultdict(float)
    matched_employees: set[str] = set()

    for date_key in sorted(timesheet):
        employees = timesheet[date_key]

        for employee_name, hours in sorted(employees.items()):
            rates = rate_map.get(normalize_name(employee_name))
            if not rates:
                continue

            matched_employees.add(normalize_name(employee_name))

            regular_hours = parse_hours(hours.get("Regular"))
            overtime_hours = parse_hours(hours.get("Overtime"))

            regular_pay = regular_hours * rates["regular_rate"]
            overtime_pay = overtime_hours * rates["overtime_rate"]
            gross_pay = regular_pay + overtime_pay
            tax_amount = gross_pay * rates["tax_rate"]
            el_amount = gross_pay * rates["el_rate"]
            total_payroll = gross_pay + tax_amount + el_amount

            employee_daily_records.append(
                {
                    "date": date_key,
                    "store": "Fremont",
                    "employee_name": employee_name,
                    "regular_hours": round(regular_hours, 4),
                    "overtime_hours": round(overtime_hours, 4),
                    "regular_rate": round(rates["regular_rate"], 4),
                    "overtime_rate": round(rates["overtime_rate"], 4),
                    "tax_rate": round(rates["tax_rate"], 6),
                    "el_rate": round(rates["el_rate"], 6),
                    "regular_pay": round(regular_pay, 4),
                    "overtime_pay": round(overtime_pay, 4),
                    "gross_pay": round(gross_pay, 4),
                    "tax_amount": round(tax_amount, 4),
                    "el_amount": round(el_amount, 4),
                    "total_payroll": round(total_payroll, 4),
                }
            )
            store_daily_totals[date_key] += total_payroll

    unmatched_timecard_names = sorted(
        employee_name
        for daily_employees in timesheet.values()
        for employee_name in daily_employees
        if normalize_name(employee_name) not in matched_employees
    )

    employee_json_path = os.path.join(output_dir, "fremont_employee_daily_payroll.json")
    employee_csv_path = os.path.join(output_dir, "fremont_employee_daily_payroll.csv")
    store_json_path = os.path.join(output_dir, "fremont_store_daily_payroll.json")
    store_plus_2000_json_path = os.path.join(output_dir, "fremont_store_daily_payroll_plus_2000.json")

    with open(employee_json_path, "w", encoding="utf-8") as file_handle:
        json.dump(employee_daily_records, file_handle, indent=2)

    pd.DataFrame(employee_daily_records).to_csv(employee_csv_path, index=False)

    store_daily_records = [
        {
            "date": date_key,
            "payroll_data": {"Fremont": round(store_daily_totals[date_key], 2)},
        }
        for date_key in sorted(store_daily_totals)
    ]

    with open(store_json_path, "w", encoding="utf-8") as file_handle:
        json.dump(
            {
                "store": "Fremont",
                "days": len(store_daily_records),
                "matched_employee_count": len(matched_employees),
                "unmatched_timecard_names": unmatched_timecard_names,
                "daily_payroll": store_daily_records,
            },
            file_handle,
            indent=2,
        )

    store_daily_plus_2000_records = [
        {
            "date": record["date"],
            "payroll_data": {
                "Fremont": round(record["payroll_data"]["Fremont"] + 2000, 2),
            },
        }
        for record in store_daily_records
    ]

    with open(store_plus_2000_json_path, "w", encoding="utf-8") as file_handle:
        json.dump(
            {
                "store": "Fremont",
                "days": len(store_daily_plus_2000_records),
                "matched_employee_count": len(matched_employees),
                "unmatched_timecard_names": unmatched_timecard_names,
                "daily_payroll": store_daily_plus_2000_records,
            },
            file_handle,
            indent=2,
        )

    return employee_json_path, employee_csv_path, store_json_path, store_plus_2000_json_path


def main() -> None:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    employee_json_path, employee_csv_path, store_json_path, store_plus_2000_json_path = compute_fremont_test_payroll(project_root)
    print(f"Wrote employee daily JSON to {employee_json_path}")
    print(f"Wrote employee daily CSV to {employee_csv_path}")
    print(f"Wrote store daily JSON to {store_json_path}")
    print(f"Wrote store daily +2000 JSON to {store_plus_2000_json_path}")


if __name__ == "__main__":
    main()