import argparse
import json
import re
from pathlib import Path
import sys
from typing import Iterable

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate total earnings per check date across multiple Excel files and export as CSV."
        )
    )
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="Excel workbooks to scan. Defaults to all .xlsx files in the current directory.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("check_dates_totals_2.csv"),
        help="Destination CSV file.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path("check_dates_totals_2.json"),
        help="Optional JSON export path (records format).",
    )
    parser.add_argument(
        "--pivot-output",
        type=Path,
        default=Path("check_dates_totals_pivot.csv"),
        help=(
            "Optional wide-format CSV with one row per check date and one column per store's daily average."
        ),
    )
    parser.add_argument(
        "--bins-output",
        type=Path,
        default=Path("check_dates_totals_bins.csv"),
        help=(
            "Optional biweekly bins CSV with global 14-day periods; columns per store's daily average aligned to bins."
        ),
    )
    parser.add_argument(
        "--sheet",
        default=0,
        help="Worksheet index or name; defaults to the first worksheet.",
    )
    parser.add_argument(
        "--header-row",
        type=int,
        default=6,
        help="Row number (0-indexed) that contains the table headers.",
    )
    parser.add_argument(
        "--date-column",
        default=r"Payment\s+\d+\s+Check Date",
        help=(
            "Regex pattern for check date columns. Default matches labels like 'Payment  1  Check Date'."
        ),
    )
    parser.add_argument(
        "--earnings-column",
        default="Total Earnings",
        help="Column that stores the total earnings for each employee.",
    )
    parser.add_argument(
        "--period-length",
        type=int,
        default=14,
        help="Assumed pay period length in days (used for the first period per store).",
    )
    parser.add_argument(
        "--daily-column",
        default="Daily Average",
        help="Column name for the per-day pay calculation.",
    )
    return parser.parse_args()


def resolve_files(explicit: Iterable[Path]) -> list[Path]:
    files = list(explicit)
    if not files:
        files = sorted(Path.cwd().glob("*.xlsx"))
    return [path for path in files if path.suffix.lower() == ".xlsx"]


def normalize_date(value: pd.Series) -> pd.Series:
    return pd.to_datetime(value, errors="coerce").dt.normalize()


def extract_first_valid_date(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
    combined = pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns]")
    for column in columns:
        column_dates = normalize_date(frame[column])
        combined = combined.fillna(column_dates)
    return combined


def coerce_earnings(series: pd.Series) -> pd.Series:
    cleaned = series.replace({pd.NA: None})
    cleaned = cleaned.astype(str).str.replace(r"[^0-9.\-]", "", regex=True)
    return pd.to_numeric(cleaned, errors="coerce")


def main() -> int:
    args = parse_args()

    workbooks = resolve_files(args.files)
    if not workbooks:
        print("No Excel files found to process.")
        return 1

    try:
        column_pattern = re.compile(args.date_column)
    except re.error as exc:
        print(f"Invalid date column pattern '{args.date_column}': {exc}")
        return 1

    output_rows: list[dict[str, object]] = []

    for workbook in workbooks:
        if not workbook.exists():
            print(f"Skipping missing file: {workbook}")
            continue

        try:
            frame = pd.read_excel(
                workbook, sheet_name=args.sheet, header=args.header_row
            )
        except Exception as exc:  # noqa: BLE001
            print(f"Failed to read {workbook}: {exc}")
            continue

        matching_columns = [
            col
            for col in frame.columns
            if isinstance(col, str) and column_pattern.fullmatch(str(col).strip())
        ]
        if not matching_columns:
            print(
                f"No check date columns matched in {workbook.name}; skipping this workbook."
            )
            continue

        earnings_column = args.earnings_column
        if earnings_column not in frame.columns:
            print(
                f"Missing earnings column '{earnings_column}' in {workbook.name}; skipping this workbook."
            )
            continue

        earnings = coerce_earnings(frame[earnings_column])
        combined_dates = extract_first_valid_date(frame, matching_columns)

        valid_mask = combined_dates.notna() & earnings.notna()
        if not valid_mask.any():
            print(f"No valid check date + earnings pairs in {workbook.name}.")
            continue

        grouped = (
            earnings[valid_mask]
            .groupby(combined_dates[valid_mask])
            .sum()
            .sort_index()
        )

        store_name = workbook.stem
        for check_date, total_pay in grouped.items():
            output_rows.append(
                {
                    "check dates": check_date,
                    "Total Pay": float(total_pay),
                    "store name": store_name,
                }
            )

    if not output_rows:
        print("No data collected; CSV not written.")
        return 1

    output_frame = pd.DataFrame(output_rows)
    # Keep datetime check dates for accurate grouping and pivoting.
    output_frame["check dates"] = pd.to_datetime(output_frame["check dates"], errors="coerce")
    output_frame.sort_values(["store name", "check dates"], inplace=True)

    # Period end is 10 days before the check date.
    output_frame["end date"] = output_frame["check dates"] - pd.Timedelta(days=10)
    # Period start is the day after the prior period end within the same store.
    period_start = (
        output_frame.groupby("store name")["end date"].shift(1) + pd.Timedelta(days=1)
    )

    first_period_mask = period_start.isna()
    if first_period_mask.any():
        adjustment = pd.Timedelta(days=max(args.period_length - 1, 0))
        period_start.loc[first_period_mask] = (
            output_frame.loc[first_period_mask, "end date"] - adjustment
        )

    output_frame["start date"] = period_start

    # Prepare final column ordering and friendly date formatting.
    output_frame[args.daily_column] = output_frame["Total Pay"] / args.period_length

    # Preserve a datetime version for pivoting before formatting dates as strings.
    pivot_source = output_frame[[
        "check dates",
        "start date",
        "end date",
        args.daily_column,
        "store name",
    ]].copy()

    # Long-form export
    long_frame = output_frame[[
        "check dates",
        "start date",
        "end date",
        "Total Pay",
        args.daily_column,
        "store name",
    ]].copy()
    for column in ["check dates", "start date", "end date"]:
        long_frame[column] = long_frame[column].dt.strftime("%d/%m/%y")

    long_frame.to_csv(args.output, index=False)
    print(f"Wrote {len(long_frame)} rows to {args.output}")

    # Wide-form (pivot) export: index by check date, columns per store daily average.
    try:
        pivot_values = pivot_source.pivot_table(
            index="check dates",
            columns="store name",
            values=args.daily_column,
            aggfunc="sum",
        ).sort_index()

        # Also include shared end date (10 days before check date) and min start date across stores.
        period_bounds = pivot_source.groupby("check dates").agg({
            "end date": "first",
            "start date": "min",
        }).sort_index()

        pivot_output = period_bounds.join(pivot_values)
        # Format dates for readability.
        for column in ["start date", "end date"]:
            pivot_output[column] = pivot_output[column].dt.strftime("%d/%m/%y")
        pivot_output.index = pivot_output.index.strftime("%d/%m/%y")
        pivot_output.index.name = "check dates"

        if args.pivot_output:
            pivot_output.to_csv(args.pivot_output)
            print(f"Wrote {len(pivot_output)} rows to {args.pivot_output}")
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to build pivot export: {exc}")

    # Build canonical biweekly bins aligned by end date using a global anchor.
    try:
        # Ensure datetime types
        end_dates = pd.to_datetime(pivot_source["end date"], errors="coerce")
        if end_dates.isna().all():
            raise ValueError("No valid end dates to build bins.")

        anchor_end = end_dates.min()
        # Assign each record to a bin by end date distance from anchor.
        bin_index = ((end_dates - anchor_end).dt.days // args.period_length).astype(int)
        bin_end = anchor_end + pd.to_timedelta(bin_index * args.period_length, unit="D")
        bin_start = bin_end - pd.Timedelta(days=args.period_length - 1)

        bins_frame = pivot_source.copy()
        bins_frame["bin_end"] = bin_end
        bins_frame["bin_start"] = bin_start

        # Aggregate per store within each bin; sum if multiple entries fall in the same bin.
        bins_values = bins_frame.pivot_table(
            index="bin_end",
            columns="store name",
            values=args.daily_column,
            aggfunc="sum",
        ).sort_index()

        # Attach the bin start for readability.
        bins_bounds = bins_frame.groupby("bin_end").agg({
            "bin_start": "first",
        }).sort_index()

        bins_output = bins_bounds.join(bins_values)
        # Format dates as strings.
        bins_output.index = bins_output.index.strftime("%d/%m/%y")
        bins_output.index.name = "bin end"
        bins_output["bin_start"] = pd.to_datetime(bins_output["bin_start"]).dt.strftime("%d/%m/%y")

        if args.bins_output:
            bins_output.to_csv(args.bins_output)
            print(f"Wrote {len(bins_output)} rows to {args.bins_output}")
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to build bins export: {exc}")

    if args.json_output:
        json_payload: dict[str, list[dict[str, object]]] = {}
        for _, row in long_frame.iterrows():
            check_date = row["check dates"]
            entry = {
                "start date": row["start date"],
                "end date": row["end date"],
                "Total Pay": float(row["Total Pay"]),
                args.daily_column: float(row[args.daily_column]),
                "store name": row["store name"],
            }
            json_payload.setdefault(check_date, []).append(entry)
        args.json_output.write_text(json.dumps(json_payload, indent=2))
        print(f"Wrote JSON export to {args.json_output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
