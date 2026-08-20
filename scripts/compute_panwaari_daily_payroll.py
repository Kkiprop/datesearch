import os
import json
import csv
from typing import Dict, Tuple, Any


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

    # Numeric already
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


def load_panwaari_rates(employee_csv_path: str) -> Dict[str, Tuple[float, float]]:
    """Load Panwaari employees and return mapping normalized_name -> (reg_rate, ot_rate)."""
    mapping: Dict[str, Tuple[float, float]] = {}

    with open(employee_csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("Store", "").strip() != "Panwaari":
                continue

            name = row.get("Employee Name", "")
            reg_rate = float(row.get("Regular Rate", 0.0) or 0.0)
            ot_rate = float(row.get("Overtime Rate", 0.0) or 0.0)

            norm = normalize_name(name)
            mapping[norm] = (reg_rate, ot_rate)

    return mapping


def compute_panwaari_for_date(project_root: str, target_date: str) -> None:
    timesheet_path = os.path.join(project_root, "outputs", "timesheet_panwaari.json")
    employees_csv = os.path.join(project_root, "outputs", "employee_details_unique.csv")

    if not os.path.isfile(timesheet_path):
        raise SystemExit(f"Missing Panwaari timesheet JSON: {timesheet_path}. Run convert_timecard_panwaari_to_json.py first.")

    with open(timesheet_path, "r", encoding="utf-8") as f:
        timesheet = json.load(f)

    day_data = timesheet.get(target_date)
    if not day_data:
        raise SystemExit(f"No Panwaari timecard data for {target_date} in {timesheet_path}.")

    rate_map = load_panwaari_rates(employees_csv)

    total_regular_pay = 0.0
    total_ot_pay = 0.0
    details = []

    for emp_name, hours_dict in day_data.items():
        norm = normalize_name(emp_name)
        reg_rate, ot_rate = rate_map.get(norm, (0.0, 0.0))

        reg_hours = parse_hours(hours_dict.get("Regular"))
        ot_hours = parse_hours(hours_dict.get("Overtime"))

        reg_pay = reg_hours * reg_rate
        ot_pay = ot_hours * ot_rate

        total_regular_pay += reg_pay
        total_ot_pay += ot_pay

        details.append(
            {
                "Employee Name": emp_name,
                "Regular Hours": reg_hours,
                "Overtime Hours": ot_hours,
                "Regular Rate": reg_rate,
                "Overtime Rate": ot_rate,
                "Regular Pay": reg_pay,
                "Overtime Pay": ot_pay,
            }
        )

    total_pay = total_regular_pay + total_ot_pay

    print(f"Panwaari payroll for {target_date}:")
    print(f"  Regular pay: ${total_regular_pay:,.2f}")
    print(f"  Overtime pay: ${total_ot_pay:,.2f}")
    print(f"  Total pay:   ${total_pay:,.2f}\n")

    # Optional: print a compact per-employee breakdown
    for d in details:
        print(
            f"- {d['Employee Name']}: Reg {d['Regular Hours']:.2f}h x ${d['Regular Rate']:.2f} = ${d['Regular Pay']:.2f}; "
            f"OT {d['Overtime Hours']:.2f}h x ${d['Overtime Rate']:.2f} = ${d['Overtime Pay']:.2f}"
        )


def main() -> None:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    # Target date: 16 Feb 2026
    compute_panwaari_for_date(project_root, "2026-02-16")


if __name__ == "__main__":
    main()
