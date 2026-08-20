import pandas as pd
import os

store_files = [
    ("AMFC.xlsx", "AMFC"),
    ("Fremont.xlsx", "Fremont"),
    ("Karthik.xlsx", "Karthik"),
    ("Milpitas.xlsx", "Milpitas"),
    ("Panwaari.xlsx", "Panwaari"),
    ("sunnyvale.xlsx", "Sunnyvale"),
]

all_data = []

for filename, store in store_files:
    if not os.path.exists(filename):
        print(f"Skipping: {filename} (File not found)")
        continue
    
    # 1. Load raw data to find header row
    df_raw = pd.read_excel(filename, header=None)
    header_row_idx = None
    for i, row in df_raw.iterrows():
        if row.astype(str).str.contains('Employee Name', case=False).any():
            header_row_idx = i
            break
            
    if header_row_idx is None:
        print(f"Could not find header row in {filename}")
        continue

    # 2. Read with correct headers
    df = pd.read_excel(filename, skiprows=header_row_idx)
    
    # 3. Map required columns dynamically
    emp_col = next((c for c in df.columns if 'employee' in str(c).lower() and 'name' in str(c).lower()), None)
    ssn_col = next((c for c in df.columns if 'ssn' in str(c).lower()), None)
    reg_col = next((c for c in df.columns if 'rate' in str(c).lower()), None)

    if all([emp_col, ssn_col, reg_col]):
        for _, row in df.iterrows():
            employee = row[emp_col]
            ssn = str(row[ssn_col]).strip()
            
            # Skip totals, footers, or empty SSNs
            if pd.isna(employee) or 'total' in str(employee).lower() or ssn == 'nan' or ssn == '':
                continue
                
            # Clean Rate
            raw_rate = row[reg_col]
            try:
                reg_rate = float(str(raw_rate).replace('$', '').replace(',', '')) if pd.notna(raw_rate) else 0.0
            except ValueError:
                reg_rate = 0.0

            all_data.append({
                'SSN': ssn,
                'Employee Name': employee,
                'Regular Rate': reg_rate,
                'Overtime Rate': round(reg_rate * 1.5, 2),
                'Store': store
            })
        print(f"Processed {filename}")
    else:
        missing = [col for col, val in zip(['Name', 'SSN', 'Rate'], [emp_col, ssn_col, reg_col]) if not val]
        print(f"Missing columns {missing} in {filename}")

# --- Deduplication Logic ---
if all_data:
    final_df = pd.DataFrame(all_data)
    
    # Sort by store or rate if you want a specific duplicate kept, 
    # otherwise drop_duplicates keeps the first one it finds.
    final_df = final_df.drop_duplicates(subset=['SSN'], keep='first')
    
    # Remove SSN from final output if you don't want it in the CSV
    # final_df = final_df.drop(columns=['SSN']) 

    final_df.to_csv('employee_details_unique.csv', index=False)
    print(f'\nDone! Saved {len(final_df)} unique employees to employee_details_unique.csv')
else:
    print("No data extracted.")