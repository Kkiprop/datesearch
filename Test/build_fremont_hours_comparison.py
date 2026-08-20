import os
from typing import Any

import pandas as pd


def parse_hours(value: Any) -> float:
    if value is None:
        return 0.0

    if isinstance(value, (int, float)):
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    text = str(value).strip()
    if not text or text.lower() == "nan":
        return 0.0

    if ":" in text:
        try:
            hours_text, minutes_text = text.split(":", 1)
            hours = int(hours_text)
            minutes = int(minutes_text)
            return hours + minutes / 60.0
        except ValueError:
            return 0.0

    try:
        return float(text)
    except ValueError:
        return 0.0


def normalize_name(name: str | None) -> str:
    if name is None:
        return ""

    normalized = str(name).lower()
    for char in [",", " "]:
        normalized = normalized.replace(char, "")
    return normalized


def find_header_row(df_raw: pd.DataFrame) -> int:
    """Find first row that contains an "Employee Name" header.

    This is used for the payroll workbook, which is laid out as a
    regular table with a single header row.
    """
    for index, row in df_raw.iterrows():
        if row.astype(str).str.contains("Employee Name", case=False).any():
            return int(index)
    return -1


def extract_hours_from_payroll_workbook(workbook_path: str, hours_label: str) -> dict[str, dict[str, float]]:
    """Return mapping of normalized employee name -> {employee_name, hours} for the payroll workbook.

    hours_label is matched case-insensitively against the column header,
    e.g. "total hours".
    """
    df_raw = pd.read_excel(workbook_path, header=None)
    header_row = find_header_row(df_raw)
    if header_row < 0:
        raise ValueError(f"Could not find Employee Name header in {os.path.basename(workbook_path)}")

    df = pd.read_excel(workbook_path, skiprows=header_row)

    employee_col = next(
        (column for column in df.columns if "employee" in str(column).lower() and "name" in str(column).lower()),
        None,
    )
    hours_col = next(
        (column for column in df.columns if hours_label in str(column).lower()),
        None,
    )

    if not employee_col or not hours_col:
        raise ValueError(
            f"Missing required columns (Employee Name / {hours_label}) in {os.path.basename(workbook_path)}",
        )

    hours_map: dict[str, dict[str, float]] = {}

    for _, row in df.iterrows():
        employee_name_raw = row.get(employee_col)
        if pd.isna(employee_name_raw):
            continue

        employee_name = str(employee_name_raw).strip()
        if not employee_name or "total" in employee_name.lower():
            continue

        hours_value = parse_hours(row.get(hours_col))
        key = normalize_name(employee_name)
        hours_map[key] = {"employee_name": employee_name, "hours": hours_value}

    return hours_map


def extract_hours_from_time_workbook(workbook_path: str) -> dict[str, dict[str, float]]:
    """Extract total paid hours per employee from the Time Excel.

    The Time workbook is laid out as repeated blocks:
      header row with columns including "Employee Name", "Pay Period",
      "Date Range", "Total Paid Hours", followed by a single row
      containing that employee's values.

    Employee rows are not in a single contiguous table, so we scan for
    each header block and read the row immediately below it.
    """
    df = pd.read_excel(workbook_path, header=None)

    hours_map: dict[str, dict[str, float]] = {}

    num_rows = len(df)
    row_idx = 0

    while row_idx < num_rows:
        row = df.iloc[row_idx]
        # Normalised non-empty cell strings for header detection
        header_cells = [str(v).strip().lower() for v in row if pd.notna(v)]

        has_employee = any("employee name" in cell for cell in header_cells)
        has_pay_period = any("pay period" in cell for cell in header_cells)
        has_date_range = any("date range" in cell for cell in header_cells)
        has_total_paid = any("total paid hours" in cell for cell in header_cells)

        if has_employee and has_pay_period and has_date_range and has_total_paid:
            # Identify the actual column indices for Employee Name and Total Paid Hours
            full_row_cells = [str(v).strip().lower() if pd.notna(v) else "" for v in row]
            employee_col_idx = next(
                (i for i, cell in enumerate(full_row_cells) if "employee name" in cell), None
            )
            hours_col_idx = next(
                (i for i, cell in enumerate(full_row_cells) if "total paid hours" in cell), None
            )

            next_idx = row_idx + 1
            if employee_col_idx is not None and hours_col_idx is not None and next_idx < num_rows:
                data_row = df.iloc[next_idx]

                emp_raw = data_row.iloc[employee_col_idx]
                hours_raw = data_row.iloc[hours_col_idx]

                if pd.notna(emp_raw):
                    employee_name = str(emp_raw).strip()
                    if employee_name and "total" not in employee_name.lower():
                        key = normalize_name(employee_name)
                        hours_value = parse_hours(hours_raw)
                        hours_map[key] = {"employee_name": employee_name, "hours": hours_value}

            # Skip past the data row we just consumed
            row_idx += 2
            continue

        row_idx += 1

    return hours_map


def build_fremont_hours_comparison(project_root: str) -> str:
    test_dir = os.path.join(project_root, "Test")
    output_dir = os.path.join(test_dir, "Outputs")
    os.makedirs(output_dir, exist_ok=True)

    payroll_file = os.path.join(test_dir, "Fremont Pay.xlsx")
    timecard_file = os.path.join(test_dir, "Fremont Time.xlsx")

    payroll_hours = extract_hours_from_payroll_workbook(payroll_file, "total hours")
    timecard_hours = extract_hours_from_time_workbook(timecard_file)

    all_keys = sorted(set(payroll_hours.keys()) | set(timecard_hours.keys()))

    rows: list[dict[str, float | str]] = []
    for key in all_keys:
        payroll_entry = payroll_hours.get(key)
        timecard_entry = timecard_hours.get(key)

        if not payroll_entry and not timecard_entry:
            continue

        employee_name = (payroll_entry or timecard_entry)["employee_name"]  # type: ignore[index]
        payroll_value = payroll_entry["hours"] if payroll_entry else 0.0
        timecard_value = timecard_entry["hours"] if timecard_entry else 0.0

        rows.append(
            {
                "Employee Name": employee_name,
                "Payroll Hours": round(float(payroll_value), 4),
                "Timecard Hours": round(float(timecard_value), 4),
            }
        )

    output_path = os.path.join(output_dir, "fremont_pay_vs_time_hours.csv")
    pd.DataFrame(rows).to_csv(output_path, index=False)

    return output_path


def main() -> None:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    output_path = build_fremont_hours_comparison(project_root)
    print(f"Wrote Fremont pay vs time hours comparison to {output_path}")


if __name__ == "__main__":
    main()
