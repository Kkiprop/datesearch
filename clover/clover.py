import os
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd
import requests
from dotenv import load_dotenv

# =====================================================
# Load environment variables
# =====================================================

load_dotenv()

MID = os.getenv("mId")
API_KEY = os.getenv("apiKey")
BASE_URL = os.getenv("base_url")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json"
}

CSV_FILE = "kitchen_orders.csv"

# =====================================================
# Date range (2026 only)
# =====================================================

START_2026 = int(datetime(2026, 7, 24, tzinfo=timezone.utc).timestamp() * 1000)
END_2026 = int(datetime(2026, 7, 25, tzinfo=timezone.utc).timestamp() * 1000)

# =====================================================
# Timestamp conversion
# =====================================================

def convert_time(ms):
    if ms is None:
        return None

    return datetime.fromtimestamp(
        ms / 1000,
        tz=timezone.utc
    ).strftime("%Y-%m-%d %H:%M:%S UTC")

# =====================================================
# Generic paginated fetch
# =====================================================

def fetch_all_pages(url, extra_params=None):

    results = []

    limit = 1000
    offset = 0

    while True:

        params = []

        if extra_params:
            params.extend(extra_params)

        params.extend([
            ("limit", limit),
            ("offset", offset)
        ])

        response = requests.get(
            url,
            headers=HEADERS,
            params=params
        )

        response.raise_for_status()

        data = response.json()

        batch = data.get("elements", [])

        if not batch:
            break

        results.extend(batch)

        print(f"Fetched {len(batch)} records (Total: {len(results)})")

        if len(batch) < limit:
            break

        offset += limit

    return results

# =====================================================
# Orders
# =====================================================

def fetch_orders():

    url = f"{BASE_URL}/{MID}/orders"

    filters = [
        ("filter", f"createdTime>={START_2026}"),
        ("filter", f"createdTime<{END_2026}")
    ]

    return fetch_all_pages(url, filters)

# =====================================================
# Payments
# =====================================================

def fetch_payments(order_id):

    url = f"{BASE_URL}/{MID}/orders/{order_id}/payments"

    return fetch_all_pages(url)

# =====================================================
# Line Items
# =====================================================

def fetch_line_items(order_id):

    url = f"{BASE_URL}/{MID}/orders/{order_id}/line_items"

    return fetch_all_pages(url)

# =====================================================
# Build rows
# =====================================================

def build_rows():

    rows = []

    orders = fetch_orders()

    print(f"\nFound {len(orders)} orders\n")

    for i, order in enumerate(orders, start=1):

        order_id = order["id"]

        print(f"[{i}/{len(orders)}] Processing {order_id}")

        payments = fetch_payments(order_id)
        line_items = fetch_line_items(order_id)

        payment = payments[0] if payments else {}

        created_ms = (
            payment.get("createdTime")
            or order.get("createdTime")
        )

        # If an order has no line items, still save one row
        if not line_items:

            rows.append({
                "order_id": order_id,
                "product": None,
                "product_price": None,
                "order_total": order.get("total"),
                "amount": payment.get("amount"),
                "tipAmount": payment.get("tipAmount"),
                "taxAmount": payment.get("taxAmount"),
                "cashbackAmount": payment.get("cashbackAmount"),
                "created_timestamp": created_ms,
                "created_at": convert_time(created_ms)
            })

            continue

        # One row per product
        for item in line_items:

            rows.append({

                "order_id": order_id,

                "product": item.get("name"),

                "product_price": item.get("price"),

                "order_total": order.get("total"),

                "amount": payment.get("amount"),

                "tipAmount": payment.get("tipAmount"),

                "taxAmount": payment.get("taxAmount"),

                "cashbackAmount": payment.get("cashbackAmount"),

                "created_timestamp": created_ms,

                "created_at": convert_time(created_ms)

            })

    return rows

# =====================================================
# Upsert CSV
# =====================================================

def upsert_csv(rows):

    new_df = pd.DataFrame(rows)

    if Path(CSV_FILE).exists():

        old_df = pd.read_csv(CSV_FILE)

        df = pd.concat(
            [old_df, new_df],
            ignore_index=True
        )

        df.drop_duplicates(
            subset=["order_id", "product"],
            keep="last",
            inplace=True
        )

    else:

        df = new_df

    df.sort_values(
        "created_timestamp",
        inplace=True
    )

    df.to_csv(
        CSV_FILE,
        index=False
    )

    print(f"\nSaved {len(df)} rows to {CSV_FILE}")

# =====================================================
# Main
# =====================================================

def main():

    rows = build_rows()

    upsert_csv(rows)

if __name__ == "__main__":
    main()