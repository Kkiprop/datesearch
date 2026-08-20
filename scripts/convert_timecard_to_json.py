import pandas as pd
import json

def parse_timecard_report(input_file, output_file):
    try:
        # Load the Excel file without headers to scan row by row manually
        df = pd.read_excel(input_file, header=None)
        
        data_tree = {}
        current_employee = None
        looking_for_employee = False
        collecting_data = False

        for i, row in df.iterrows():
            row_list = row.tolist()
            # Convert row to string to make searching easier
            row_str = [str(val).strip().lower() for val in row_list if pd.notna(val)]

            # 1. TRIGGER: Found the Employee Header Row
            if "employee name" in row_str and "pay period" in row_str:
                looking_for_employee = True
                collecting_data = False
                continue

            # 2. ACTION: Pick the Employee Name (The row right below the header)
            if looking_for_employee:
                # Assuming Employee Name is in the same column index as the header (likely index 0 or 1)
                # We find the index where 'employee name' was in the previous row
                current_employee = str(row_list[0] if pd.notna(row_list[0]) else row_list[1]).strip()
                looking_for_employee = False
                continue

            # 3. TRIGGER: Found the Data Header Row (Date, Start Work, etc.)
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
                    # Parse the Date
                    raw_date = pd.to_datetime(row[0])
                    date_key = raw_date.strftime('%Y-%m-%d')
                    
                    # Identify columns by typical index: Date(0), Regular(3), Overtime(4)
                    # Adjust these indices [0, 3, 4] if your columns are in different spots
                    reg_hours = row[3] if pd.notna(row[3]) else 0
                    ot_hours = row[4] if pd.notna(row[4]) else 0

                    # Structure: { Date: { Employee: { Regular, Overtime } } }
                    if date_key not in data_tree:
                        data_tree[date_key] = {}
                    
                    data_tree[date_key][current_employee] = {
                        "Regular": reg_hours,
                        "Overtime": ot_hours
                    }
                except:
                    # If the first column isn't a date, skip this row
                    continue

        # Write to JSON
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data_tree, f, indent=4)

        print(f"Successfully created {output_file} with {len(data_tree)} unique dates.")

    except Exception as e:
        print(f"An error occurred: {e}")

parse_timecard_report('Timecard Fremont.xlsx', 'timesheet.json')