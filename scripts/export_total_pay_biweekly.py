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
            "Aggregate total earnings per check date across multiple Excel files and export as CSV, plus biweekly bins aligned by period end dates."
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
        default=Path("check_dates_totals_biweekly.csv"),
        help="Destination long-form CSV file.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path("check_dates_totals_biweekly.json"),
        help="Optional JSON export path (records format).",
    )
    parser.add_argument(
        "--bins-output",
        type=Path,
        default=Path("check_dates_totals_bins_by_checkdate.csv"),
        help=(
            "Biweekly bins CSV aligned so each bin's data comes from the check date that is 10 days after the bin end."
        ),
    )
    parser.add_argument(
        "--daily-output",
        type=Path,
        default=Path("check_dates_totals_daily.csv"),
        help=(
            "Daily time series CSV: one row per calendar date from first start to last end, columns per store's daily average."
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
        help="Biweekly period length in days.",
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


def build_long_form(output_rows: list[dict[str, object]], period_length: int, daily_column: str) -> pd.DataFrame:
    frame = pd.DataFrame(output_rows)
    frame["check dates"] = pd.to_datetime(frame["check dates"], errors="coerce")
    frame.sort_values(["store name", "check dates"], inplace=True)

    # End date is 10 days before the check date; start is derived by fixed length.
    frame["end date"] = frame["check dates"] - pd.Timedelta(days=10)
    period_start = (
        frame.groupby("store name")["end date"].shift(1) + pd.Timedelta(days=1)
    )

    first_mask = period_start.isna()
    if first_mask.any():
        period_adjust = pd.Timedelta(days=max(period_length - 1, 0))
        period_start.loc[first_mask] = frame.loc[first_mask, "end date"] - period_adjust

    frame["start date"] = period_start
    frame[daily_column] = frame["Total Pay"] / period_length
    return frame


def build_bins_from_checkdate(long_frame: pd.DataFrame, period_length: int, daily_column: str) -> pd.DataFrame:
    # We derive bin_end from check dates: bin_end = check_date - 10 days.
    end_dates = pd.to_datetime(long_frame["end date"], errors="coerce")
    if end_dates.isna().all():
        raise ValueError("No valid end dates for binning.")

    # Global anchor and canonical 14-day cadence.
    anchor_end = end_dates.min()
    # Map each row to its canonical bin end using exact match to cadence.
    bin_index = ((end_dates - anchor_end).dt.days // period_length).astype(int)
    bin_end = anchor_end + pd.to_timedelta(bin_index * period_length, unit="D")
    bin_start = bin_end - pd.Timedelta(days=period_length - 1)

    bins_frame = long_frame[["store name", daily_column]].copy()
    bins_frame["bin_end"] = bin_end
    bins_frame["bin_start"] = bin_start

    # Aggregate per store per bin (sum in case of multiple entries landing in same bin).
    bins_values = bins_frame.pivot_table(
        index="bin_end",
        columns="store name",
        values=daily_column,
        aggfunc="sum",
    ).sort_index()

    bins_bounds = bins_frame.groupby("bin_end").agg({
        "bin_start": "first",
    }).sort_index()

    bins_output = bins_bounds.join(bins_values)
    bins_output.index = bins_output.index.strftime("%d/%m/%y")
    bins_output.index.name = "bin end"
    bins_output["bin_start"] = pd.to_datetime(bins_output["bin_start"]).dt.strftime("%d/%m/%y")
    return bins_output


def build_daily_timeseries(long_frame: pd.DataFrame, daily_column: str) -> pd.DataFrame:
    # Create a date index covering the entire range across stores.
    start_min = pd.to_datetime(long_frame["start date"], errors="coerce").min()
    end_max = pd.to_datetime(long_frame["end date"], errors="coerce").max()
    if pd.isna(start_min) or pd.isna(end_max):
        raise ValueError("Invalid start/end dates for daily expansion.")

    date_index = pd.date_range(start=start_min, end=end_max, freq="D")
    stores = sorted(long_frame["store name"].unique())
    daily_df = pd.DataFrame(index=date_index, columns=stores, dtype=float)

    # Fill per store: for each period, assign the per-day value to all dates in the inclusive range.
    for store in stores:
        rows = long_frame[long_frame["store name"] == store]
        for _, r in rows.iterrows():
            s = pd.to_datetime(r["start date"], errors="coerce")
            e = pd.to_datetime(r["end date"], errors="coerce")
            val = float(r[daily_column]) if pd.notna(r[daily_column]) else None
            if pd.isna(s) or pd.isna(e) or val is None:
                continue
            rng = pd.date_range(start=s, end=e, freq="D")
            # Assign value; if overlapping periods occur, sum values.
            # Align index slices to avoid SettingWithCopy issues.
            existing = daily_df.loc[rng, store]
            daily_df.loc[rng, store] = existing.fillna(0.0).astype(float) + val

    # Format index as dd/mm/yy for output readability.
    daily_df.index = daily_df.index.strftime("%d/%m/%y")
    daily_df.index.name = "date"
    return daily_df


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

    long_frame = build_long_form(output_rows, args.period_length, args.daily_column)

    # Long-form export with human-friendly dates
    export_long = long_frame[[
        "check dates",
        "start date",
        "end date",
        "Total Pay",
        args.daily_column,
        "store name",
    ]].copy()
    for column in ["check dates", "start date", "end date"]:
        export_long[column] = export_long[column].dt.strftime("%d/%m/%y")

    export_long.to_csv(args.output, index=False)
    print(f"Wrote {len(export_long)} rows to {args.output}")

    # Bins output based on check dates occurring 10 days after bin end (i.e., rows grouped by end date cadence)
    try:
        bins_output = build_bins_from_checkdate(long_frame, args.period_length, args.daily_column)
        if args.bins_output:
            bins_output.to_csv(args.bins_output)
            print(f"Wrote {len(bins_output)} rows to {args.bins_output}")
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to build bins export: {exc}")

    if args.json_output:
        json_payload: dict[str, list[dict[str, object]]] = {}
        for _, row in export_long.iterrows():
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

    # Daily time series output: one row per calendar date, columns per store.
    try:
        daily_output = build_daily_timeseries(long_frame, args.daily_column)
        if args.daily_output:
            daily_output.to_csv(args.daily_output)
            print(f"Wrote {len(daily_output)} rows to {args.daily_output}")
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to build daily time series export: {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
