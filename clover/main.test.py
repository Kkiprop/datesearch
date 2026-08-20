import requests
import pandas as pd
import json
import time
import os
from pathlib import Path
from datetime import datetime

# ==========================================================
# CONFIG
# ==========================================================

MERCHANT_ID = "2TTAH3S6K6KQ1"
TOKEN = "75c00cb9-e0ad-5c88-cd3b-44f69207e899"

BASE_URL = f"https://api.clover.com/v3/merchants/{MERCHANT_ID}"

LIMIT = 20
REQUEST_DELAY = 1.5
MAX_RETRIES = 3

HEADERS = {
    "Authorization": f"Bearer {TOKEN}"
}

# ==========================================================
# OUTPUT FOLDERS
# ==========================================================

BASE_DIR = Path("clover_audit")

RAW_DIR = BASE_DIR / "raw_json"
CSV_DIR = BASE_DIR / "csv"
REPORT_DIR = BASE_DIR / "reports"
LOG_DIR = BASE_DIR / "logs"

for d in [RAW_DIR, CSV_DIR, REPORT_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ==========================================================
# TRACKING
# ==========================================================

endpoint_summary = []
failed_endpoints = []
field_inventory = []
field_coverage = []

# ==========================================================
# HELPERS
# ==========================================================

def flatten_json(obj, parent_key=""):
    items = {}

    if isinstance(obj, dict):
        for k, v in obj.items():
            new_key = f"{parent_key}.{k}" if parent_key else k

            if isinstance(v, (dict, list)):
                items.update(flatten_json(v, new_key))
            else:
                items[new_key] = v

    elif isinstance(obj, list):
        if len(obj) > 0:
            first = obj[0]

            if isinstance(first, (dict, list)):
                items.update(flatten_json(first, parent_key))
            else:
                items[parent_key] = str(obj)

    return items


def extract_fields(obj, parent=""):
    fields = set()

    if isinstance(obj, dict):
        for k, v in obj.items():
            name = f"{parent}.{k}" if parent else k

            fields.add(name)

            if isinstance(v, (dict, list)):
                fields.update(extract_fields(v, name))

    elif isinstance(obj, list):
        for item in obj[:5]:
            fields.update(extract_fields(item, parent))

    return fields


def save_json(data, filename):
    path = RAW_DIR / f"{filename}.json"

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def save_csv(data, filename):

    if not data:
        return

    rows = []

    for row in data:
        rows.append(flatten_json(row))

    df = pd.DataFrame(rows)

    df.to_csv(
        CSV_DIR / f"{filename}.csv",
        index=False
    )


def request_endpoint(url):

    for attempt in range(MAX_RETRIES):

        start = time.time()

        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=60
            )

            elapsed = round(
                (time.time() - start) * 1000,
                2
            )

            if response.status_code == 429:

                wait = 10 * (attempt + 1)

                print(
                    f"429 received. Waiting {wait}s..."
                )

                time.sleep(wait)
                continue

            return response, elapsed

        except Exception as e:

            if attempt == MAX_RETRIES - 1:
                raise e

            time.sleep(5)

    return None, None


def process_endpoint(
        endpoint_name,
        endpoint_path,
        params=None
):

    url = f"{BASE_URL}{endpoint_path}"

    if params:

        query = "&".join(
            f"{k}={v}"
            for k, v in params.items()
        )

        url += f"?{query}"

    print(f"\nFetching {endpoint_name}")

    response, elapsed = request_endpoint(url)

    if response is None:

        failed_endpoints.append({
            "endpoint": endpoint_name,
            "status": "REQUEST_FAILED",
            "error": "No Response"
        })

        return None

    status = response.status_code

    try:
        payload = response.json()
    except:
        payload = {}

    if status != 200:

        failed_endpoints.append({
            "endpoint": endpoint_name,
            "status": status,
            "error": str(payload)
        })

        endpoint_summary.append({
            "endpoint": endpoint_name,
            "status": status,
            "rows": 0,
            "fields": 0,
            "response_ms": elapsed
        })

        return None

    save_json(payload, endpoint_name)

    records = []

    if isinstance(payload, dict):

        if "elements" in payload:
            records = payload["elements"]

        else:
            records = [payload]

    elif isinstance(payload, list):
        records = payload

    save_csv(records, endpoint_name)

    discovered_fields = set()

    for row in records:
        discovered_fields.update(
            extract_fields(row)
        )

    for field in discovered_fields:
        field_inventory.append({
            "endpoint": endpoint_name,
            "field": field
        })

    # coverage

    if records:

        flat_rows = [
            flatten_json(x)
            for x in records
        ]

        df = pd.DataFrame(flat_rows)

        for col in df.columns:

            coverage = round(
                (
                    df[col]
                    .notna()
                    .sum()
                    / len(df)
                ) * 100,
                2
            )

            field_coverage.append({
                "endpoint": endpoint_name,
                "field": col,
                "populated_pct": coverage
            })

    endpoint_summary.append({
        "endpoint": endpoint_name,
        "status": status,
        "rows": len(records),
        "fields": len(discovered_fields),
        "response_ms": elapsed
    })

    time.sleep(REQUEST_DELAY)

    return records


# ==========================================================
# ENDPOINTS
# ==========================================================

ENDPOINTS = [

    ("merchant", "", None),

    ("orders",
     "/orders",
     {"limit": LIMIT}),

    ("orders_expanded",
     "/orders",
     {"limit": LIMIT,
      "expand": "true"}),

    ("payments",
     "/payments",
     {"limit": LIMIT}),

    ("payments_expanded",
     "/payments",
     {"limit": LIMIT,
      "expand": "true"}),

    ("refunds",
     "/refunds",
     {"limit": LIMIT}),

    ("customers",
     "/customers",
     {"limit": LIMIT}),

    ("customers_expanded",
     "/customers",
     {"limit": LIMIT,
      "expand": "true"}),

    ("items",
     "/items",
     {"limit": LIMIT}),

    ("items_expanded",
     "/items",
     {"limit": LIMIT,
      "expand": "true"}),

    ("categories",
     "/categories",
     {"limit": LIMIT}),

    ("modifier_groups",
     "/modifier_groups",
     {"limit": LIMIT}),

    ("modifiers",
     "/modifiers",
     {"limit": LIMIT}),

    ("tags",
     "/tags",
     {"limit": LIMIT}),

    ("tax_rates",
     "/tax_rates",
     {"limit": LIMIT}),

    ("cash_events",
     "/cash_events",
     {"limit": LIMIT}),

    ("employees",
     "/employees",
     {"limit": LIMIT}),

    ("tenders",
     "/tenders",
     {"limit": LIMIT}),

    ("order_types",
     "/order_types",
     {"limit": LIMIT}),

    ("service_charges",
     "/service_charges",
     {"limit": LIMIT})
]

# ==========================================================
# MAIN AUDIT
# ==========================================================

print("=" * 80)
print("STARTING CLOVER AUDIT")
print("=" * 80)

results = {}

for name, path, params in ENDPOINTS:

    try:

        records = process_endpoint(
            name,
            path,
            params
        )

        results[name] = records

    except Exception as e:

        failed_endpoints.append({
            "endpoint": name,
            "status": "EXCEPTION",
            "error": str(e)
        })

# ==========================================================
# CHILD ENDPOINT DISCOVERY
# ==========================================================

print("\nDiscovering child endpoints...")

orders = results.get("orders")

if orders:

    try:

        order_id = orders[0]["id"]

        process_endpoint(
            "order_detail",
            f"/orders/{order_id}"
        )

        process_endpoint(
            "order_line_items",
            f"/orders/{order_id}/line_items"
        )

    except Exception as e:
        print(e)

items = results.get("items")

if items:

    try:

        item_id = items[0]["id"]

        process_endpoint(
            "item_detail",
            f"/items/{item_id}"
        )

    except Exception as e:
        print(e)

customers = results.get("customers")

if customers:

    try:

        customer_id = customers[0]["id"]

        process_endpoint(
            "customer_detail",
            f"/customers/{customer_id}"
        )

    except Exception as e:
        print(e)

# ==========================================================
# REPORTS
# ==========================================================

pd.DataFrame(
    endpoint_summary
).to_csv(
    REPORT_DIR / "endpoint_summary.csv",
    index=False
)

pd.DataFrame(
    failed_endpoints
).to_csv(
    REPORT_DIR / "failed_endpoints.csv",
    index=False
)

pd.DataFrame(
    field_inventory
).drop_duplicates().to_csv(
    REPORT_DIR / "field_inventory.csv",
    index=False
)

pd.DataFrame(
    field_coverage
).to_csv(
    REPORT_DIR / "field_coverage.csv",
    index=False
)

with open(
        REPORT_DIR / "endpoint_summary.json",
        "w",
        encoding="utf-8"
) as f:

    json.dump(
        {
            "generated_at":
                datetime.now().isoformat(),
            "endpoint_summary":
                endpoint_summary,
            "failed_endpoints":
                failed_endpoints
        },
        f,
        indent=2
    )

print("\n" + "=" * 80)
print("AUDIT COMPLETE")
print("=" * 80)

print(
    f"Endpoints audited: {len(endpoint_summary)}"
)

print(
    f"Failed endpoints: {len(failed_endpoints)}"
)

print(
    f"Reports saved to: {REPORT_DIR}"
)