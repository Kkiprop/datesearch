#!/usr/bin/env python3
import json
import os
from pathlib import Path
from typing import Dict, List


def compute_store_payroll(records: List[dict]) -> Dict[str, float]:
    """Compute total zero-rows payroll per store.

    Payroll per employee is defined as:
      Payroll = Amount Per Day + (Amount Per Day * EL Rate) + (Amount Per Day * Tax Rate)
              = Amount Per Day * (1 + EL Rate + Tax Rate)

    We sum this over all employees in each store.
    """

    totals: Dict[str, float] = {}

    for rec in records:
        store = str(rec.get("Store", "")).strip()
        if not store:
            continue

        amount_per_day = float(rec.get("Amount Per Day", 0.0) or 0.0)
        tax_rate = float(rec.get("Tax Rate", 0.0) or 0.0)
        el_rate = float(rec.get("EL Rate", 0.0) or 0.0)

        payroll = amount_per_day * (1.0 + tax_rate + el_rate)
        totals[store] = totals.get(store, 0.0) + payroll

    return totals


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent

    # Input JSON derived from zero_rows_employee_details_unique
    ready_dir = project_root / "Ready"
    input_path = ready_dir / "zero_rows_employee_details_unique.json"

    if not input_path.exists():
        print(f"Input JSON not found: {input_path}")
        return 1

    with input_path.open("r", encoding="utf-8") as f:
        records = json.load(f)

    if not isinstance(records, list):
        print("Expected a list of records in zero_rows_employee_details_unique.json")
        return 1

    totals = compute_store_payroll(records)

    # Build the 6-document output: one document per store
    output_docs = []
    for store, total in sorted(totals.items()):
        output_docs.append({
            "Store": store,
            "Payroll": round(total, 2),
        })

    # Write alongside other Ready artifacts
    output_path = ready_dir / "zero_rows_store_payroll_summary.json"
    with output_path.open("w", encoding="utf-8") as f_out:
        json.dump(output_docs, f_out, indent=2)

    print(f"Wrote {len(output_docs)} store payroll documents to {output_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
