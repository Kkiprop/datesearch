import argparse
import csv
import json
import os
from datetime import datetime

FIELDNAMES = ["id", "date", "payroll_data", "payroll_sources", "updated_at"]


def parse_timestamp(value):
    if value is None:
        return ""
    if isinstance(value, dict) and "$date" in value:
        value = value["$date"]
    if not isinstance(value, str):
        return str(value)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return value


def load_json_records(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # Support MongoDB export format containing top-level documents in an array
        return [data]
    raise ValueError("Unsupported JSON format: expected an array or object of records")


def write_csv(records, output_path):
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()

        for idx, record in enumerate(records, start=1):
            payroll_data = record.get("payroll_data") or {}
            payroll_sources = record.get("payroll_sources") or {}
            updated_at = parse_timestamp(record.get("updatedAt") or record.get("updated_at"))

            writer.writerow({
                "id": idx,
                "date": record.get("date", ""),
                "payroll_data": json.dumps(payroll_data, ensure_ascii=False),
                "payroll_sources": json.dumps(payroll_sources, ensure_ascii=False),
                "updated_at": updated_at,
            })


def build_output_path(input_path, output_path=None):
    if output_path:
        return output_path
    base, _ = os.path.splitext(input_path)
    return f"{base}.csv"


def main():
    parser = argparse.ArgumentParser(description="Convert Payroll_daily JSON to CSV")
    parser.add_argument("input", help="Path to the Payroll_daily JSON file")
    parser.add_argument("output", nargs="?", help="Path to the output CSV file")
    args = parser.parse_args()

    input_path = args.input
    output_path = build_output_path(input_path, args.output)

    records = load_json_records(input_path)
    write_csv(records, output_path)
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
