import pandas as pd
from rapidfuzz import process, fuzz

# File paths
input_file = r"C:\Users\Admin\Downloads\vendors_types.csv"
output_file = r"C:\Users\Admin\Downloads\vendor_match_results.csv"

# Read CSV
df = pd.read_csv(input_file)

# Clean names
df["csv_vendor_names"] = df["csv_vendor_names"].fillna("").astype(str).str.strip()
df["db_vendor_names"] = df["db_vendor_names"].fillna("").astype(str).str.strip()

# List of QB vendor names
qb_names = df["db_vendor_names"].dropna().unique().tolist()

results = []

MATCH_THRESHOLD = 80  # Adjust if needed

for vendor in df["csv_vendor_names"]:
    if vendor == "":
        results.append({
            "csv_vendor_name": vendor,
            "matched_qb_vendor": "",
            "match_score": 0,
            "status": "No Match"
        })
        continue

    match = process.extractOne(
        vendor,
        qb_names,
        scorer=fuzz.token_sort_ratio
    )

    if match:
        best_match, score, _ = match

        results.append({
            "csv_vendor_name": vendor,
            "matched_db_vendor": best_match if score >= MATCH_THRESHOLD else "",
            "match_score": score,
            "status": "Matched" if score >= MATCH_THRESHOLD else "No Match"
        })
    else:
        results.append({
            "csv_vendor_name": vendor,
            "matched_db_vendor": "",
            "match_score": 0,
            "status": "No Match"
        })

# Save results
results_df = pd.DataFrame(results)
results_df.to_csv(output_file, index=False)

print(f"Done! Results saved to:\n{output_file}")