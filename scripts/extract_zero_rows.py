#!/usr/bin/env python3
import csv
import argparse
import re
import os


def clean_num(s):
    if s is None:
        return None
    s = str(s).strip()
    if s == "":
        return None
    # remove common non-numeric characters like $ ,
    s = re.sub(r"[^0-9.\-]", "", s)
    try:
        return float(s)
    except:
        return None


def find_column_index(header, name):
    name = name.strip().lower()
    # exact match
    for i, h in enumerate(header):
        if h.strip().lower() == name:
            return i
    # contains
    for i, h in enumerate(header):
        if name in h.strip().lower():
            return i
    # fuzzy keywords
    keywords = name.split()
    for i, h in enumerate(header):
        hl = h.strip().lower()
        if all(k in hl for k in keywords):
            return i
    return None


def auto_detect(header, candidates):
    # candidates is list of lists of possible names for (regular, overtime)
    header_l = [h.strip().lower() for h in header]
    for reg_opts, ot_opts in candidates:
        reg_idx = None
        ot_idx = None
        for opt in reg_opts:
            if opt in header_l:
                reg_idx = header_l.index(opt)
                break
        for opt in ot_opts:
            if opt in header_l:
                ot_idx = header_l.index(opt)
                break
        if reg_idx is not None and ot_idx is not None:
            return reg_idx, ot_idx
    # fallback: find any header containing keywords
    reg_keywords = ['regular','reg','straight']
    ot_keywords = ['overtime','ot']
    reg_idx = next((i for i,h in enumerate(header_l) if any(k in h for k in reg_keywords)), None)
    ot_idx = next((i for i,h in enumerate(header_l) if any(k in h for k in ot_keywords)), None)
    if reg_idx is not None and ot_idx is not None:
        return reg_idx, ot_idx
    return None, None


def main():
    p = argparse.ArgumentParser(description="Extract rows where regular or overtime equals 0")
    p.add_argument('--input', '-i', required=True, help='Input CSV file')
    p.add_argument('--regular', '-r', help='Regular hours column name (or index)')
    p.add_argument('--overtime', '-o', help='Overtime hours column name (or index)')
    p.add_argument('--output', '-O', help='Output CSV file', default='outputs/zero_rows.csv')
    p.add_argument('--encoding', '-e', help='File encoding', default='utf-8')
    args = p.parse_args()

    inp = args.input
    outp = args.output

    if not os.path.isfile(inp):
        print(f"Input file not found: {inp}")
        return

    os.makedirs(os.path.dirname(outp) or '.', exist_ok=True)

    with open(inp, newline='', encoding=args.encoding, errors='replace') as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            print('Input CSV is empty')
            return
        # find indices
        reg_idx = None
        ot_idx = None
        if args.regular:
            # try numeric index
            try:
                idx = int(args.regular)
                reg_idx = idx
            except:
                reg_idx = find_column_index(header, args.regular)
        if args.overtime:
            try:
                idx = int(args.overtime)
                ot_idx = idx
            except:
                ot_idx = find_column_index(header, args.overtime)

        if reg_idx is None or ot_idx is None:
            # try auto-detection
            candidates = [
                (['regular','regular_hours','reg_hours','regular hours','regularrate','regular rate'], ['overtime','overtime_hours','ot_hours','overtime hours','overtime rate','overtime_rate','ot']),
            ]
            a_reg, a_ot = auto_detect(header, candidates)
            if a_reg is not None and a_ot is not None:
                if reg_idx is None:
                    reg_idx = a_reg
                if ot_idx is None:
                    ot_idx = a_ot

        if reg_idx is None or ot_idx is None:
            print('Could not determine column indices automatically.')
            print('Header columns:')
            for i,h in enumerate(header):
                print(f'{i}: {h}')
            print('\nRerun with --regular and --overtime specifying column names or indices.')
            return

        rows_out = []
        total = 0
        matched = 0
        for row in reader:
            total += 1
            # ensure row is long enough
            def safe_get(r, idx):
                return r[idx] if idx < len(r) else ''
            reg_val = clean_num(safe_get(row, reg_idx))
            ot_val = clean_num(safe_get(row, ot_idx))
            # treat None as 0 only if empty; if unparsable, treat as None (not zero)
            if reg_val is None and (safe_get(row, reg_idx) or safe_get(row, reg_idx) == ''):
                # unparsable? leave as None
                pass
            if ot_val is None and (safe_get(row, ot_idx) or safe_get(row, ot_idx) == ''):
                pass
            # consider numeric zeros
            is_zero_reg = (reg_val is not None and reg_val == 0)
            is_zero_ot = (ot_val is not None and ot_val == 0)
            # include rows where either is zero (or both)
            if is_zero_reg or is_zero_ot:
                matched += 1
                rows_out.append(row)

    # write output
    with open(outp, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows_out)

    print(f'Total rows scanned: {total}')
    print(f'Rows matched (regular==0 or overtime==0): {matched}')
    print(f'Wrote output to: {outp}')


if __name__ == '__main__':
    main()
