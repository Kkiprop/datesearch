import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Sum amounts for specified stores over a date window relative to a target date."
        )
    )
    parser.add_argument(
        "--target-date",
        default="2025-02-13",
        help="Target date in YYYY-MM-DD (default: 2025-02-13)",
    )
    parser.add_argument(
        "--lower-days",
        type=int,
        default=23,
        help="Lower bound offset in days (default: 23)",
    )
    parser.add_argument(
        "--upper-days",
        type=int,
        default=10,
        help="Upper bound offset in days (default: 10)",
    )
    parser.add_argument(
        "--stores",
        nargs="*",
        default=["Fremont", "Milpitas", "sunnyvale", "Karthik"],
        help="Store names to include (case-insensitive match)",
    )
    parser.add_argument(
        "--input-json",
        type=Path,
        default=Path("outputs/check_dates_totals_daily_bydate.json"),
        help="Path to daily-by-date JSON file",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=Path("outputs/amounts_sum_2025-02-13_window_23_10.csv"),
        help="Where to write the summarized CSV",
    )
    return parser.parse_args()


def parse_ddmmyy(date_str: str) -> datetime:
    return datetime.strptime(date_str, "%d/%m/%y")


def main() -> int:
    args = parse_args()

    target = datetime.strptime(args.target_date, "%Y-%m-%d")
    start = target - timedelta(days=args.lower_days)
    end = target - timedelta(days=args.upper_days)

    with args.input_json.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # Normalize store filters to lowercase for case-insensitive match
    wanted = {s.lower() for s in args.stores}

    # Aggregate
    totals = {s: 0.0 for s in wanted}

    for date_key, entries in data.items():
        try:
            d = parse_ddmmyy(date_key)
        except ValueError:
            # Skip non-standard keys
            continue

        if d < start or d > end:
            continue

        for entry in entries:
            store = str(entry.get("store name", "")).lower()
            if store not in wanted:
                continue
            amount = float(entry.get("Total Pay", 0.0))
            totals[store] += amount

    # Write CSV output
    lines = ["store name,amount_sum,window_start,window_end,target_date"]
    for store in args.stores:
        key = store.lower()
        amt = totals.get(key, 0.0)
        lines.append(
            f"{store},{amt:.2f},{start.date()},{end.date()},{target.date()}"
        )

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    args.output_csv.write_text("\n".join(lines), encoding="utf-8")

    # Also print to console for quick visibility
    print("Summed amounts by store:")
    for store in args.stores:
        print(f"  {store}: {totals.get(store.lower(), 0.0):.2f}")
    print(
        f"Window: {start.date()} to {end.date()} (target {target.date()}) -> {args.output_csv}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
