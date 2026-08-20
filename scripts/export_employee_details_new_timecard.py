import os
import json
from collections import Counter
from typing import List, Dict, Any, Tuple

import pandas as pd


def parse_float(value: Any) -> float:
    """Parse a numeric cell that may contain $, commas, or be blank/NaN."""
    if value is None:
        return 0.0
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return 0.0
    s = s.replace("$", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def find_header_row(df_raw: pd.DataFrame) -> int:
    """Locate the row index that contains the 'Employee Name' header."""
    header_row_idx = -1
    for i, row in df_raw.iterrows():
        if row.astype(str).str.contains("Employee Name", case=False).any():
            header_row_idx = int(i)
            break
    return header_row_idx


def build_earning_groups(columns: List[Any]) -> List[Tuple[int, int]]:
    """Return list of (earning_label_col_index, rate_col_index) pairs.

    Columns come in repeating groups like:
    'Earning  1', 'Hours', 'Rate', 'Amount', 'Earning  2', 'Hours', 'Rate', 'Amount', ...
    We only care about the earning label column and its corresponding Rate column.
    """
    groups: List[Tuple[int, int]] = []
    for i, col in enumerate(columns):
        name = str(col)
        if name.lower().startswith("earning"):
            rate_idx = i + 2
            if rate_idx < len(columns):
                groups.append((i, rate_idx))
    return groups


def extract_employee_rows(df: pd.DataFrame, store: str) -> List[Dict[str, Any]]:
    """Extract per-employee rates and tax/EL ratios from a Payroll Detail sheet."""
    records: List[Dict[str, Any]] = []

    # Column mappings we expect from the header row
    emp_col = next((c for c in df.columns if "employee" in str(c).lower() and "name" in str(c).lower()), None)
    ssn_col = next((c for c in df.columns if "ssn" in str(c).lower()), None)
    total_earnings_col = next((c for c in df.columns if "total earnings" in str(c).lower()), None)
    total_taxes_col = next((c for c in df.columns if "total taxes" in str(c).lower()), None)
    total_el_col = next((c for c in df.columns if "total employer liability" in str(c).lower()), None)

    if not all([emp_col, ssn_col, total_earnings_col, total_taxes_col, total_el_col]):
        missing = [
            name
            for name, col in [
                ("Employee Name", emp_col),
                ("SSN", ssn_col),
                ("Total Earnings", total_earnings_col),
                ("Total Taxes", total_taxes_col),
                ("Total Employer Liability", total_el_col),
            ]
            if not col
        ]
        print(f"Skipping store {store}: missing columns {missing}")
        return records

    # Build earning groups from header so we can detect Regular and Overtime rates per row
    earning_groups = build_earning_groups(list(df.columns))

    # Columns containing individual payment amounts (Payment 1 Amount ... Payment N Amount)
    payment_amount_cols = [
        c
        for c in df.columns
        if "payment" in str(c).lower() and "amount" in str(c).lower()
    ]

    for _, row in df.iterrows():
        employee = row.get(emp_col)
        if pd.isna(employee):
            continue

        ssn = str(row.get(ssn_col)).strip()
        if not ssn or ssn.lower() == "nan":
            continue

        # Skip totals/footers
        if "total" in str(employee).lower():
            continue

        # Derive regular hourly rate from earning groups
        regular_rate = 0.0

        for earn_idx, rate_idx in earning_groups:
            label_raw = row.iloc[earn_idx]
            label = str(label_raw).strip().lower() if not pd.isna(label_raw) else ""

            if "regular" in label and regular_rate == 0.0:
                regular_rate = parse_float(row.iloc[rate_idx])

        # Per requirement: Overtime Rate is always Regular Rate * 1.5
        overtime_rate = regular_rate * 1.5 if regular_rate > 0 else 0.0

        total_earnings = parse_float(row.get(total_earnings_col))
        total_taxes = parse_float(row.get(total_taxes_col))
        total_el = parse_float(row.get(total_el_col))

        tax_rate = total_taxes / total_earnings if total_earnings > 0 else 0.0
        el_rate = total_el / total_earnings if total_earnings > 0 else 0.0

        # Determine the most frequent payment amount (mode) across all payment amount columns
        payments: List[float] = []
        for col in payment_amount_cols:
            val = parse_float(row.get(col))
            # Ignore zeros and missing values
            if val > 0:
                payments.append(round(val, 2))

        mode_amount = 0.0
        if payments:
            counts = Counter(payments)
            mode_amount = counts.most_common(1)[0][0]

        records.append(
            {
                "SSN": ssn,
                "Employee Name": employee,
                "Store": store,
                "Regular Rate": round(regular_rate, 4),
                "Overtime Rate": round(overtime_rate, 4),
                "Tax Rate": round(tax_rate, 6),
                "EL Rate": round(el_rate, 6),
                "Total Earnings": round(total_earnings, 2),
                # Raw totals for zero-rate analysis and reference
                "Tax": round(total_taxes, 2),
                "EL": round(total_el, 2),
                "Amount": round(mode_amount, 2),
            }
        )

    return records


def build_employee_docs_by_name(df_unique: pd.DataFrame) -> Dict[str, List[Dict[str, Any]]]:
    """Build a name-keyed JSON-friendly mapping of employee payroll summaries."""
    employee_docs: Dict[str, List[Dict[str, Any]]] = {}

    for _, row in df_unique.iterrows():
        employee_name = str(row.get("Employee Name", "")).strip()
        if not employee_name:
            continue

        doc = {
            "Store": row.get("Store", ""),
            "Regular": round(float(row.get("Regular Rate", 0.0) or 0.0), 4),
            "Overtime": round(float(row.get("Overtime Rate", 0.0) or 0.0), 4),
            "Pay": round(float(row.get("Total Earnings", 0.0) or 0.0) / 10.0, 2),
        }
        employee_docs.setdefault(employee_name, []).append(doc)

    return employee_docs


def main() -> None:
    # Resolve project root as the parent of this script's folder
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    input_dir = os.path.join(project_root, "New_Timecard", "Inputs")
    output_dir = os.path.join(project_root, "outputs")
    os.makedirs(output_dir, exist_ok=True)

    store_files = [
        ("AMFC PayrollDetail (4).xlsx", "AMFC"),
        ("Fremont PayrollDetail (4).xlsx", "Fremont"),
        ("Karthik PayrollDetail (4).xlsx", "Karthik"),
        ("Milpitas PayrollDetail (4).xlsx", "Milpitas"),
        ("Panwaari PayrollDetail (4).xlsx", "Panwaari"),
        ("Sunnyvale PayrollDetail (4).xlsx", "Sunnyvale"),
    ]

    all_records: List[Dict[str, Any]] = []

    for filename, store in store_files:
        file_path = os.path.join(input_dir, filename)
        if not os.path.exists(file_path):
            print(f"Skipping: {file_path} (file not found)")
            continue

        print(f"Processing {file_path} for store {store}...")

        # 1. Load raw data to find header row
        df_raw = pd.read_excel(file_path, header=None)
        header_row_idx = find_header_row(df_raw)

        if header_row_idx < 0:
            print(f"Could not find header row in {file_path}")
            continue

        # 2. Read with correct headers
        df = pd.read_excel(file_path, skiprows=header_row_idx)

        store_records = extract_employee_rows(df, store)
        all_records.extend(store_records)
        print(f"  -> extracted {len(store_records)} employees")

    if not all_records:
        print("No employee data extracted from any store.")
        return

    # Deduplicate by SSN, keeping the first occurrence (typically first store)
    df_all = pd.DataFrame(all_records)
    df_unique = df_all.drop_duplicates(subset=["SSN"], keep="first").reset_index(drop=True)

    # Split into employees with valid regular rates and those with zero regular rate
    df_with_rate = df_unique[df_unique["Regular Rate"] > 0].reset_index(drop=True)
    df_zero_rate = df_unique[df_unique["Regular Rate"] <= 0].reset_index(drop=True)

    # For main employee details, keep only rate-related fields
    rate_columns = [
        "SSN",
        "Employee Name",
        "Store",
        "Regular Rate",
        "Overtime Rate",
        "Tax Rate",
        "EL Rate",
    ]
    df_with_rate_out = df_with_rate[rate_columns].copy()

    output_with_rate = os.path.join(output_dir, "employee_details_unique.csv")
    output_zero_rate = os.path.join(output_dir, "zero_rows_employee_details_unique.csv")

    # Write CSVs
    df_with_rate_out.to_csv(output_with_rate, index=False)
    df_zero_rate.to_csv(output_zero_rate, index=False)

    # --- JSON outputs ---
    # 1) Employee details unique: same columns as df_with_rate_out
    emp_json_path = os.path.join(output_dir, "employee_details_unique.json")
    with open(emp_json_path, "w", encoding="utf-8") as f_emp:
        json.dump(df_with_rate_out.to_dict(orient="records"), f_emp, indent=2)

    # 1b) Employee docs keyed by employee name with pay derived from total earnings.
    employee_docs_by_name = build_employee_docs_by_name(df_unique)
    emp_by_name_json_path = os.path.join(output_dir, "employee_docs_by_name.json")
    with open(emp_by_name_json_path, "w", encoding="utf-8") as f_emp_by_name:
        json.dump(employee_docs_by_name, f_emp_by_name, indent=2)

    # 2) Zero-rows employees: drop rate and raw tax/EL columns, add Amount Per Day = Amount/14
    zero_for_json = df_zero_rate.copy()
    for col in ["Regular Rate", "Overtime Rate", "Tax", "EL"]:
        if col in zero_for_json.columns:
            zero_for_json = zero_for_json.drop(columns=[col])

    if "Amount" in zero_for_json.columns:
        zero_for_json["Amount Per Day"] = zero_for_json["Amount"].fillna(0).astype(float) / 14.0
    else:
        zero_for_json["Amount Per Day"] = 0.0

    zero_json_path = os.path.join(output_dir, "zero_rows_employee_details_unique.json")
    with open(zero_json_path, "w", encoding="utf-8") as f_zero:
        json.dump(zero_for_json.to_dict(orient="records"), f_zero, indent=2)

    print(f"\nDone! Saved {len(df_with_rate_out)} employees with rates to {output_with_rate} and {emp_json_path}")
    print(f"Done! Saved {len(employee_docs_by_name)} employee-name groups to {emp_by_name_json_path}")
    print(f"Done! Saved {len(df_zero_rate)} employees with 0 regular rate to {output_zero_rate} and {zero_json_path}")


if __name__ == "__main__":
    main()
