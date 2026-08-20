import argparse
import json
from pathlib import Path

import pandas as pd
import re


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a daily CSV of store averages to JSON."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("check_dates_totals_daily.csv"),
        help="Source daily CSV file (one row per date).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("check_dates_totals_daily.json"),
        help="Destination JSON file.",
    )
    parser.add_argument(
        "--orient",
        choices=["records", "index", "ndjson", "bydate"],
        default="records",
        help=(
            "Output format: 'records' => list of objects; 'index' => {date: {store: value}}; 'ndjson' => one JSON document per line; 'bydate' => {date: [{entry per store}]}."
        ),
    )
    parser.add_argument(
        "--mongo-friendly",
        action="store_true",
        help=(
            "Transform fields for MongoDB import: add 'collection', rename 'date' to 'check_date' (ISO yyyy-mm-dd)."
        ),
    )
    parser.add_argument(
        "--collection-value",
        default="daily_averages",
        help="Value to set in the 'collection' field when --mongo-friendly is used.",
    )
    parser.add_argument(
        "--check-date-field",
        default="check_date",
        help="Field name to use for the date when --mongo-friendly is used (default: check_date).",
    )
    parser.add_argument(
        "--keep-date",
        action="store_true",
        help="Keep the original 'date' column when --mongo-friendly is used (default: drop it).",
    )
    parser.add_argument(
        "--add-start-end",
        action="store_true",
        help=(
            "Add 'start date' and 'end date' fields to each record. By default these equal the source 'date'."
        ),
    )
    parser.add_argument(
        "--start-end-iso",
        action="store_true",
        help=(
            "Format 'start date' and 'end date' as ISO yyyy-mm-dd instead of the CSV's dd/mm/yy."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.input.exists():
        print(f"Input CSV not found: {args.input}")
        return 1

    df = pd.read_csv(args.input)
    # Ensure strict JSON compliance: replace NaN/NA with None and forbid NaN in dumps.
    df = df.astype(object).where(pd.notna(df), None)

    # Optional Mongo-friendly transformations
    if args.mongo_friendly:
        if "date" not in df.columns:
            print("CSV missing 'date' column required for --mongo-friendly.")
            return 1
        # First try robust manual parsing of dd/mm/yy to ISO yyyy-mm-dd to avoid None values.
        def ddmmyy_to_iso(s: str) -> str | None:
            if s is None:
                return None
            s = str(s).strip()
            m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{2})", s)
            if not m:
                return None
            dd, mm, yy = m.groups()
            yyyy = int(yy)
            yyyy = 2000 + yyyy  # assume 20xx for two-digit year
            return f"{yyyy:04d}-{int(mm):02d}-{int(dd):02d}"

        iso_dates = [ddmmyy_to_iso(v) for v in df["date"].tolist()]
        # Fallback to pandas when manual parse fails
        if any(v is None for v in iso_dates):
            dt = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
            iso_dates = [
                (d.strftime("%Y-%m-%d") if pd.notna(d) else iso)
                for d, iso in zip(dt, iso_dates)
            ]

        df[args.check_date_field] = iso_dates
        df["collection"] = args.collection_value
        if not args.keep_date:
            df = df.drop(columns=["date"]) 

        # Optionally add start/end in ISO if requested; otherwise keep dd/mm/yy
        if args.add_start_end:
            if args.start_end_iso:
                dt_iso = pd.to_datetime(iso_dates, format="%Y-%m-%d", errors="coerce")
                df["start date"] = [
                    d.strftime("%Y-%m-%d") if pd.notna(d) else None for d in dt_iso
                ]
                df["end date"] = [
                    d.strftime("%Y-%m-%d") if pd.notna(d) else None for d in dt_iso
                ]
            else:
                # When keep_date was dropped, we still have the original string values in a temp series
                original_date = pd.read_csv(args.input)["date"]
                df["start date"] = original_date.tolist()
                df["end date"] = original_date.tolist()

        # Drop any records that still have a null check_date to avoid unique index collisions
        if args.check_date_field in df.columns:
            df = df[df[args.check_date_field].notna()]
    else:
        # Non-mongo-friendly path: optionally add start/end mirroring the 'date' string
        if args.add_start_end and "date" in df.columns:
            if args.start_end_iso:
                dt = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
                df["start date"] = [
                    d.strftime("%Y-%m-%d") if pd.notna(d) else None for d in dt
                ]
                df["end date"] = [
                    d.strftime("%Y-%m-%d") if pd.notna(d) else None for d in dt
                ]
            else:
                df["start date"] = df["date"]
                df["end date"] = df["date"]

    if args.orient == "ndjson":
        lines = []
        for record in df.to_dict(orient="records"):
            lines.append(json.dumps(record, separators=(",", ":"), ensure_ascii=False, allow_nan=False))
        args.output.write_text("\n".join(lines))
        print(f"Wrote NDJSON to {args.output}")
    elif args.orient == "bydate":
        if "date" not in df.columns:
            print("CSV missing 'date' column for bydate-oriented JSON.")
            return 1
        # Build mapping: date -> list of entries per store for that day
        date_entries: dict[str, list[dict]] = {}
        store_cols = [c for c in df.columns if c not in {"date", "collection", args.check_date_field, "start date", "end date"}]
        for _, row in df.iterrows():
            date_str = row.get("date")
            entries = []
            for store in store_cols:
                val = row.get(store)
                if val is None:
                    continue
                entry = {
                    "start date": row.get("start date", date_str),
                    "end date": row.get("end date", date_str),
                    "Total Pay": float(val),
                    "Daily Average": float(val),
                    "store name": store,
                }
                entries.append(entry)
            # only add date key if there is at least one store value
            if entries:
                date_entries.setdefault(str(date_str), []).extend(entries)

        args.output.write_text(json.dumps(date_entries, indent=2, ensure_ascii=False, allow_nan=False))
        print(f"Wrote date-keyed JSON to {args.output}")
    else:
        if args.orient == "records":
            payload = df.to_dict(orient="records")
        else:
            # index: map date -> {store: value}
            if "date" not in df.columns:
                print("CSV missing 'date' column for index-oriented JSON.")
                return 1
            df = df.set_index("date")
            payload = df.to_dict(orient="index")

        args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False))
        print(f"Wrote JSON to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
