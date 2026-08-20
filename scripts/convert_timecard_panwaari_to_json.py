import os
import pandas as pd
import json


def parse_timecard_report(input_file: str, output_file: str) -> None:
    """Parse an ADP-style timecard Excel export into a JSON timesheet.

    Output structure:
    {
        "YYYY-MM-DD": {
            "Employee Name": {"Regular": <value>, "Overtime": <value>},
            ...
        },
        ...
    }
    """
    try:
        df = pd.read_excel(input_file, header=None)

        data_tree = {}
        current_employee = None
        looking_for_employee = False
        collecting_data = False

        for _, row in df.iterrows():
            row_list = row.tolist()
            # Non-null values as lowercase strings for pattern matching
            row_str = [str(val).strip().lower() for val in row_list if pd.notna(val)]

            # 1. TRIGGER: Found the Employee Header Row
            if "employee name" in row_str and "pay period" in row_str:
                looking_for_employee = True
                collecting_data = False
                continue

            # 2. ACTION: Pick the Employee Name (row right below the header)
            if looking_for_employee:
                # Employee name is typically in first non-null column
                if pd.notna(row_list[0]):
                    current_employee = str(row_list[0]).strip()
                else:
                    current_employee = str(row_list[1]).strip()
                looking_for_employee = False
                continue

            # 3. TRIGGER: Found the Data Header Row (Date, Regular, etc.)
            if "date" in row_str and "regular" in row_str:
                collecting_data = True
                continue

            # 4. ACTION: Collect the data rows
            if collecting_data and current_employee:
                # Stop collecting if we hit an empty row or a total row
                if pd.isna(row[0]) or "total" in str(row[0]).lower():
                    collecting_data = False
                    continue

                try:
                    raw_date = pd.to_datetime(row[0])
                    date_key = raw_date.strftime("%Y-%m-%d")

                    # Typical indices: Date(0), Regular(3), Overtime(4)
                    reg_hours = row[3] if len(row_list) > 3 and pd.notna(row[3]) else 0
                    ot_hours = row[4] if len(row_list) > 4 and pd.notna(row[4]) else 0

                    if date_key not in data_tree:
                        data_tree[date_key] = {}

                    data_tree[date_key][current_employee] = {
                        "Regular": reg_hours,
                        "Overtime": ot_hours,
                    }
                except Exception:
                    # Skip rows where first column is not a valid date
                    continue

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data_tree, f, indent=4)

        print(f"Successfully created {output_file} with {len(data_tree)} unique dates.")

    except Exception as e:
        print(f"An error occurred while parsing {input_file}: {e}")


def main() -> None:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    input_file = os.path.join(project_root, "inputs", "Panwaari.xlsx")
    output_file = os.path.join(project_root, "outputs", "timesheet_panwaari.json")

    parse_timecard_report(input_file, output_file)


if __name__ == "__main__":
    main()
