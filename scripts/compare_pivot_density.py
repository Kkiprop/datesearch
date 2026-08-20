import csv
import os
from collections import defaultdict


def analyze_csv(path: str) -> dict:
    with open(path, 'r', newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)
        exclude = {h.lower() for h in ['check dates', 'end date', 'start date', 'bin end', 'bin_start']}
        store_cols = [i for i, h in enumerate(header) if h.lower() not in exclude]
        store_names = [header[i] for i in store_cols]

        rows = list(reader)
        n_rows = len(rows)
        per_store = defaultdict(int)
        filled_total = 0

        for row in rows:
            for i, name in zip(store_cols, store_names):
                val = row[i].strip()
                if val:
                    per_store[name] += 1
                    filled_total += 1

        total_cells = n_rows * len(store_cols)
        pct = (filled_total / total_cells * 100.0) if total_cells else 0.0
        return {
            'file': os.path.basename(path),
            'rows': n_rows,
            'stores': store_names,
            'filled_cells': filled_total,
            'total_cells': total_cells,
            'fill_pct': round(pct, 2),
            'per_store_counts': dict(per_store),
        }


def main() -> None:
    root = os.getcwd()
    files = [
        os.path.join(root, 'check_dates_totals_pivot.csv'),
        os.path.join(root, 'check_dates_totals_bins_by_checkdate.csv'),
    ]

    results = [analyze_csv(p) for p in files]
    # Print concise comparison summary
    for r in results:
        print(f"File: {r['file']}")
        print(f"  Rows: {r['rows']}")
        print(f"  Stores: {', '.join(r['stores'])}")
        print(f"  Filled cells: {r['filled_cells']} / {r['total_cells']} ({r['fill_pct']}%)")
        print(f"  Per-store filled counts: {r['per_store_counts']}")
        print()

    # Which is denser overall
    densest = max(results, key=lambda x: x['fill_pct'])
    print(f"Densest by overall fill percentage: {densest['file']} ({densest['fill_pct']}%)")


if __name__ == '__main__':
    main()
