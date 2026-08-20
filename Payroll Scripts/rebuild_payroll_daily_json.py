import os
import csv
import json
from datetime import datetime, timedelta
from typing import Dict, Tuple


def parse_amount(amount_str: str) -> float:
    """Convert an amount string like "139613.87" or "$137,805.64" to a float.

    Empty strings or malformed values are treated as 0.0.
    """
    if amount_str is None:
        return 0.0

    s = str(amount_str).strip()
    if not s:
        return 0.0

    if s.startswith("$"):
        s = s[1:]
    s = s.replace(",", "")

    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_date_us(date_str: str) -> datetime.date:
    """Parse a date in M/D/YYYY or MM/DD/YYYY format to a date object."""
    return datetime.strptime(date_str.strip(), "%m/%d/%Y").date()


def build_daily_payroll(project_root: str) -> None:
    payroll_outputs_dir = os.path.join(project_root, "Payroll Outputs")

    # Map summarized CSV filenames (based on new "Payroll Hist" naming) to store names
    store_file_map = {
        "Payroll Hist AMFC summarized.csv": "Apni mandi fulfillment centre",
        "Payroll Hist Fremont summarized.csv": "Fremont",
        "Payroll Hist Karthik summarized.csv": "Karthik",
        "Payroll History Milpitas summarized.csv": "Milpitas",
        "Payroll Hist Panwaari summarized.csv": "Panwaari",
        "Payroll Hist Sunnyvale summarized.csv": "Sunnyvale",
    }

    # (date_iso, store) -> daily amount
    daily_amounts: Dict[Tuple[str, str], float] = {}

    for filename, store_name in store_file_map.items():
        input_path = os.path.join(payroll_outputs_dir, filename)
        if not os.path.isfile(input_path):
            continue

        with open(input_path, newline="", encoding="utf-8-sig") as f_in:
            reader = csv.DictReader(f_in)

            for row in reader:
                period_start_str = (row.get("Period Start") or "").strip()
                if not period_start_str:
                    continue

                amount_total = parse_amount(row.get("Amount", ""))
                if amount_total == 0.0:
                    continue

                try:
                    start_date = parse_date_us(period_start_str)
                except ValueError:
                    continue

                # Assume biweekly 14-day periods, divide evenly across 14 days
                days_in_period = 14
                daily_amount = amount_total / days_in_period

                for offset in range(days_in_period):
                    day = start_date + timedelta(days=offset)
                    date_key = day.isoformat()
                    key = (date_key, store_name)
                    daily_amounts[key] = daily_amounts.get(key, 0.0) + daily_amount

    # Collect all dates and stores actually used
    dates = sorted({date for (date, _store) in daily_amounts.keys()})
    # Use a fixed order for stores to match the existing JSON style
    store_order = [
        "Panwaari",
        "Milpitas",
        "Apni mandi fulfillment centre",
        "Fremont",
        "Sunnyvale",
        "Karthik",
    ]

    documents = []

    for date_str in dates:
        payroll_data: Dict[str, object] = {}
        for store in store_order:
            value = daily_amounts.get((date_str, store), 0.0)
            # Use null when there is effectively no payroll data for that store/date
            if abs(value) < 1e-9:
                payroll_data[store] = None
            else:
                payroll_data[store] = round(value, 2)

        doc = {
            "date": date_str,
            "payroll_data": payroll_data,
        }
        documents.append(doc)

    # Write JSON into a Daily subfolder under Payroll Outputs
    daily_dir = os.path.join(payroll_outputs_dir, "Daily")
    os.makedirs(daily_dir, exist_ok=True)

    output_path = os.path.join(daily_dir, "Payroll_dashboard.Payroll_daily.json")
    with open(output_path, "w", encoding="utf-8") as f_out:
        json.dump(documents, f_out, indent=2)

    print(f"Wrote {len(documents)} daily payroll records to {output_path}")


def main() -> None:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    build_daily_payroll(project_root)


if __name__ == "__main__":
    main()
