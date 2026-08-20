import os
import csv
from typing import Dict, Tuple


def parse_amount(amount_str: str) -> float:
    """Convert an amount string like "$137,805.64" to a float.

    Empty strings or malformed values are treated as 0.0.
    """
    if amount_str is None:
        return 0.0

    s = amount_str.strip()
    if not s:
        return 0.0

    # Remove optional leading "$" and thousands separators
    if s.startswith("$"):
        s = s[1:]
    s = s.replace(",", "")

    try:
        return float(s)
    except ValueError:
        return 0.0


def summarize_file(input_path: str, output_path: str) -> None:
    """Read a payroll CSV and write a summarized version with unique Period Start.

    Groups by Period Start and sums Amount.
    Keeps the first encountered values for all other columns.
    Output columns match the input CSV columns.
    """
    groups: Dict[str, Dict[str, object]] = {}

    with open(input_path, newline="", encoding="utf-8-sig") as f_in:
        reader = csv.DictReader(f_in)

        if reader.fieldnames is None:
            return

        fieldnames = list(reader.fieldnames)

        for row in reader:
            period_start = (row.get("Period Start") or "").strip()
            if not period_start:
                # Skip rows without a Period Start
                continue

            amount = parse_amount(row.get("Amount", ""))
            key = period_start

            if key not in groups:
                # Start a new group with this row's data
                grouped_row: Dict[str, object] = dict(row)
                grouped_row["Amount"] = amount
                groups[key] = grouped_row
            else:
                # Add to existing group's amount
                existing = groups[key]
                existing["Amount"] = float(existing.get("Amount", 0.0)) + amount

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()

        # Sort by Period Start for readability
        for period_start, data in sorted(groups.items(), key=lambda kv: kv[0]):
            out_row = dict(data)
            # Format Amount as numeric string with 2 decimals
            out_row["Amount"] = f"{float(data.get('Amount', 0.0)):.2f}"
            writer.writerow(out_row)


def main() -> None:
    # Resolve project root as the parent of this script's folder
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    input_dir = os.path.join(project_root, "Payroll Inputs")
    output_dir = os.path.join(project_root, "Payroll Outputs")

    if not os.path.isdir(input_dir):
        raise SystemExit(f"Input directory not found: {input_dir}")

    os.makedirs(output_dir, exist_ok=True)

    for filename in os.listdir(input_dir):
        if not filename.lower().endswith(".csv"):
            continue

        input_path = os.path.join(input_dir, filename)

        base, ext = os.path.splitext(filename)
        output_filename = f"{base} summarized{ext}"
        output_path = os.path.join(output_dir, output_filename)

        summarize_file(input_path, output_path)
        print(f"Summarized {filename} -> {output_filename}")


if __name__ == "__main__":
    main()
