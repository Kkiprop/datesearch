import os
import json
from datetime import datetime
from typing import Dict, Any, Tuple, List

import pandas as pd


def normalize_name(name: str) -> str:
    """Normalize a name for fuzzy matching (lowercase, remove spaces, commas)."""
    if name is None:
        return ""
    s = str(name).lower()
    for ch in [",", " "]:
        s = s.replace(ch, "")
    return s


def parse_hours(value: Any) -> float:
    """Parse hours from formats like "3:53", "0", 0, or "0:00" to decimal hours."""
    if value is None:
        return 0.0

    if isinstance(value, (int, float)):
        try:
            return float(value)
        except Exception:
            return 0.0

    s = str(value).strip()
    if not s or s.lower() == "nan":
        return 0.0

    if ":" in s:
        try:
            h_str, m_str = s.split(":", 1)
            hours = int(h_str)
            minutes = int(m_str)
            return hours + minutes / 60.0
        except Exception:
            return 0.0

    try:
        return float(s)
    except Exception:
        return 0.0


def parse_timecard_report(input_file: str) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Parse an ADP-style timecard Excel into {date: {employee: {Regular, Overtime}}}."""
    df = pd.read_excel(input_file, header=None)

    data_tree: Dict[str, Dict[str, Dict[str, Any]]] = {}
    current_employee: str | None = None
    looking_for_employee = False
    collecting_data = False

    for _, row in df.iterrows():
        row_list = row.tolist()
        row_str = [str(val).strip().lower() for val in row_list if pd.notna(val)]

        # 1. Employee header row
        if "employee name" in row_str and "pay period" in row_str:
            looking_for_employee = True
            collecting_data = False
            continue

        # 2. Employee name row (right below header)
        if looking_for_employee:
            if pd.notna(row_list[0]):
                current_employee = str(row_list[0]).strip()
            else:
                current_employee = str(row_list[1]).strip()
            looking_for_employee = False
            continue

        # 3. Data header row
        if "date" in row_str and "regular" in row_str:
            collecting_data = True
            continue

        # 4. Data rows
        if collecting_data and current_employee:
            if pd.isna(row[0]) or "total" in str(row[0]).lower():
                collecting_data = False
                continue

            try:
                raw_date = pd.to_datetime(row[0])
                date_key = raw_date.strftime("%Y-%m-%d")

                reg_hours = row[3] if len(row_list) > 3 and pd.notna(row[3]) else 0
                ot_hours = row[4] if len(row_list) > 4 and pd.notna(row[4]) else 0

                if date_key not in data_tree:
                    data_tree[date_key] = {}

                data_tree[date_key][current_employee] = {
                    "Regular": reg_hours,
                    "Overtime": ot_hours,
                }
            except Exception:
                continue

    return data_tree


def build_rate_maps(ready_dir: str) -> Tuple[Dict[Tuple[str, str], Dict[str, float]], Dict[str, float]]:
    """Load employee rates and zero-rate employees from Ready JSONs.

    Returns:
      rate_map: (store_rate_name, normalized_employee_name) -> {reg, ot, tax_rate, el_rate}
      zero_pay_per_day: store_display_name -> pay per day including taxes & EL
    """
    emp_path = os.path.join(ready_dir, "employee_details_unique.json")
    zero_path = os.path.join(ready_dir, "zero_rows_employee_details_unique.json")

    with open(emp_path, "r", encoding="utf-8") as f:
        emp_data = json.load(f)

    with open(zero_path, "r", encoding="utf-8") as f:
        zero_data = json.load(f)

    # Map from internal store code to display name in final JSON
    store_display_map = {
        "AMFC": "Apni mandi fulfillment centre",
        "Fremont": "Fremont",
        "Karthik": "Karthik",
        "Milpitas": "Milpitas",
        "Panwaari": "Panwaari",
        "Sunnyvale": "Sunnyvale",
    }

    rate_map: Dict[Tuple[str, str], Dict[str, float]] = {}

    for rec in emp_data:
        store_code = str(rec.get("Store", "")).strip()
        name = rec.get("Employee Name", "")
        if not store_code or not name:
            continue

        norm = normalize_name(name)
        key = (store_code, norm)

        reg_rate = float(rec.get("Regular Rate", 0.0) or 0.0)
        ot_rate = float(rec.get("Overtime Rate", 0.0) or 0.0)
        tax_rate = float(rec.get("Tax Rate", 0.0) or 0.0)
        el_rate = float(rec.get("EL Rate", 0.0) or 0.0)

        rate_map[key] = {
            "reg_rate": reg_rate,
            "ot_rate": ot_rate,
            "tax_rate": tax_rate,
            "el_rate": el_rate,
        }

    zero_pay_per_day: Dict[str, float] = {}

    for rec in zero_data:
        store_code = str(rec.get("Store", "")).strip()
        display = store_display_map.get(store_code)
        if not display:
            continue

        amount_per_day = float(rec.get("Amount Per Day", 0.0) or 0.0)
        tax_rate = float(rec.get("Tax Rate", 0.0) or 0.0)
        el_rate = float(rec.get("EL Rate", 0.0) or 0.0)

        pay_zero = amount_per_day * (1.0 + tax_rate + el_rate)
        zero_pay_per_day[display] = zero_pay_per_day.get(display, 0.0) + pay_zero

    return rate_map, zero_pay_per_day


def compute_daily_payroll(project_root: str) -> None:
    ready_dir = os.path.join(project_root, "Ready")
    new_timecard_inputs = os.path.join(project_root, "New_Timecard", "Inputs")

    rate_map, zero_pay_per_day = build_rate_maps(ready_dir)

    # Mapping of stores to their timecard filenames and display names
    store_configs = [
        {
            "store_code": "AMFC",
            "display": "Apni mandi fulfillment centre",
            "timecard_file": "AMFCTimecard .xlsx",
        },
        {
            "store_code": "Fremont",
            "display": "Fremont",
            "timecard_file": "FremontTimecard .xlsx",
        },
        {
            "store_code": "Karthik",
            "display": "Karthik",
            "timecard_file": "KarthikTimecard .xlsx",
        },
        {
            "store_code": "Milpitas",
            "display": "Milpitas",
            "timecard_file": "MilpitasTimecard .xlsx",
        },
        {
            "store_code": "Panwaari",
            "display": "Panwaari",
            "timecard_file": "PanwaariTimecard .xlsx",
        },
        {
            "store_code": "Sunnyvale",
            "display": "Sunnyvale",
            "timecard_file": "SunnyvaleTimecard .xlsx",
        },
    ]

    # (date_iso, store_display) -> payroll estimate (rated employees only)
    daily_store_totals: Dict[Tuple[str, str], float] = {}
    all_dates: set[str] = set()

    for cfg in store_configs:
        store_code = cfg["store_code"]
        display = cfg["display"]
        timecard_path = os.path.join(new_timecard_inputs, cfg["timecard_file"])

        if not os.path.isfile(timecard_path):
            print(f"Skipping timecard for store {display}: {timecard_path} not found")
            continue

        print(f"Processing timecard for store {display}: {timecard_path}")
        timesheet = parse_timecard_report(timecard_path)

        for date_key, employees in timesheet.items():
            all_dates.add(date_key)

            for emp_name, hours_dict in employees.items():
                norm = normalize_name(emp_name)
                rates = rate_map.get((store_code, norm))
                if not rates:
                    # No rate info found; contributes 0
                    continue

                reg_hours = parse_hours(hours_dict.get("Regular"))
                ot_hours = parse_hours(hours_dict.get("Overtime"))

                reg_rate = rates["reg_rate"]
                ot_rate = rates["ot_rate"]
                tax_rate = rates["tax_rate"]
                el_rate = rates["el_rate"]

                payroll_est = reg_hours * reg_rate + ot_hours * ot_rate
                payroll_with_tax_el = payroll_est * (1.0 + tax_rate + el_rate)

                key = (date_key, display)
                daily_store_totals[key] = daily_store_totals.get(key, 0.0) + payroll_with_tax_el

    # Build final documents
    dates_sorted = sorted(all_dates)
    store_order = [
        "Panwaari",
        "Milpitas",
        "Apni mandi fulfillment centre",
        "Fremont",
        "Sunnyvale",
        "Karthik",
    ]

    documents: List[Dict[str, Any]] = []

    for date_str in dates_sorted:
        payroll_data: Dict[str, Any] = {}
        for store_display in store_order:
            base_val = daily_store_totals.get((date_str, store_display), 0.0)
            zero_val = zero_pay_per_day.get(store_display, 0.0)
            total_val = base_val + zero_val

            if abs(total_val) < 1e-9:
                payroll_data[store_display] = None
            else:
                payroll_data[store_display] = round(total_val, 2)

        documents.append({"date": date_str, "payroll_data": payroll_data})

    # Write output JSON, mirroring existing location
    outputs_dir = os.path.join(project_root, "outputs")
    os.makedirs(outputs_dir, exist_ok=True)
    out_path = os.path.join(outputs_dir, "Payroll_dashboard.Payroll_daily.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(documents, f, indent=2)

    print(f"Wrote {len(documents)} daily payroll records to {out_path}")


def main() -> None:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    compute_daily_payroll(project_root)


if __name__ == "__main__":
    main()
