import json
import os
import time
from datetime import datetime, timedelta

import requests


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "revel_exports")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "revel_sales_customer_first_101.json")
POLL_INTERVAL_SECONDS = int(os.environ.get("REVEL_POLL_INTERVAL_SECONDS", "60"))
STORE_NAME_MAPPING = {
    "apnabazar1": "Sunnyvale",
    "apnabazar2": "Fremont",
    "stopandshopca1": "Karthik",
    "stopandshopca2": "Milpitas",
}
FIELD_NAMES = [
    "sales_amount",
    "customer_count",
    "total_discounts",
    "refunds_total",
    "voided_total",
    "returned_total",
    "net_sales",
]


def resolve_creds_path():
    candidate_paths = [
        os.path.join(SCRIPT_DIR, "json_creds", "revel_creds.json"),
        os.path.join(os.getcwd(), "Revel", "json_creds", "revel_creds.json"),
        os.path.join(os.getcwd(), "json_creds", "revel_creds.json"),
    ]

    for candidate_path in candidate_paths:
        if os.path.exists(candidate_path):
            return candidate_path

    raise FileNotFoundError("Could not find revel_creds.json")


def load_revel_credentials():
    creds_path = resolve_creds_path()
    with open(creds_path, "r", encoding="utf-8") as file:
        return json.load(file)


def build_revel_url(base_url, endpoint_path):
    normalized_base_url = base_url.rstrip("/")
    if normalized_base_url.endswith("/reports"):
        normalized_base_url = normalized_base_url[: -len("/reports")]

    return f"{normalized_base_url}/{endpoint_path.lstrip('/')}"


def to_sales_customer_record(record):
    sales_amount = float(record.get("total_sales", 0) or 0)
    customer_count = int(record.get("total_orders", 0) or 0)
    total_discounts = float(record.get("total_discounts", 0) or 0)
    refunds_total = float(record.get("refunds_total", 0) or 0)
    voided_total = float(record.get("voided_total", 0) or 0)
    returned_total = float(record.get("returned_total", 0) or 0)
    net_sales = sales_amount - (total_discounts + refunds_total + voided_total + returned_total)

    return {
        "sales_amount": round(sales_amount, 2),
        "customer_count": customer_count,
        "total_discounts": round(total_discounts, 2),
        "refunds_total": round(refunds_total, 2),
        "voided_total": round(voided_total, 2),
        "returned_total": round(returned_total, 2),
        "net_sales": round(net_sales, 2),
    }


def save_export(date_str, export_data):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    payload = {
        "generated_at": datetime.now().isoformat(),
        "date": date_str,
        "fields": FIELD_NAMES,
        "data": export_data,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=4)

    return OUTPUT_FILE


def fetch_sales_summary(date_str):
    api_details = load_revel_credentials()
    export_data = {}

    for api in api_details:
        base_url = api["base_url"]
        auth_header = f"{api['api_auth_key']}:{api['api_auth_secret']}"

        for establishment in api["establishments"]:
            revel_establishment_name = f"{base_url.split('.')[0].split('//')[1]}{establishment}"
            establishment_name = STORE_NAME_MAPPING.get(revel_establishment_name, revel_establishment_name)
            print()
            print(f"Fetching data for {establishment_name} on {date_str}...")

            url = build_revel_url(base_url, "reports/sales_summary/json/")
            params = {
                "posstation": "",
                "employee": "",
                "show_unpaid": 1,
                "show_irregular": 1,
                "range_from": f"{date_str} 00:00",
                "range_to": f"{date_str} 23:59",
                "establishment": establishment,
                "format": "json",
            }
            headers = {
                "API-AUTHENTICATION": auth_header,
                "Accept": "application/json",
            }

            response = requests.get(url, headers=headers, params=params, timeout=60)

            if response.status_code != 200:
                print(f"❌ Failed to fetch data. HTTP {response.status_code}: {response.text}")
                export_data[establishment_name] = {
                    "item_count": 0,
                    "items": [],
                }
                continue

            print("✅ Data retrieved successfully!")
            response_data = response.json()
            if isinstance(response_data, list):
                source_items = response_data[:100]
            elif response_data:
                source_items = [response_data]
            else:
                source_items = []

            filtered_items = [to_sales_customer_record(item) for item in source_items]
            export_data[establishment_name] = {
                "item_count": len(filtered_items),
                "items": filtered_items,
            }
            print(f"💾 Prepared {len(filtered_items)} filtered items for {establishment_name}")

    output_path = save_export(date_str, export_data)
    print(f"💾 Saved Revel export → {output_path}")
    return output_path


def get_target_date():
    target_date = os.environ.get("REVEL_TARGET_DATE")
    if target_date:
        return target_date

    use_yesterday = os.environ.get("REVEL_USE_YESTERDAY", "false").lower() == "true"
    base_date = datetime.now() - timedelta(days=1) if use_yesterday else datetime.now()
    return base_date.date().strftime("%Y-%m-%d")


def run_once():
    date_str = get_target_date()

    print()
    print(f"Processing date: {date_str}")
    print("=" * 70)
    print(f"⏳ Fetching first 100 filtered sales summary items for {date_str}")
    print("=" * 70)

    try:
        fetch_sales_summary(date_str)
        print("✅ Revel export completed.")
    except Exception as error:
        print(f"❌ Error occurred: {error}")


def run_continuously():
    print(f"▶ Continuous polling enabled. Interval: {POLL_INTERVAL_SECONDS} seconds")

    while True:
        run_once()
        print(f"⏲ Waiting {POLL_INTERVAL_SECONDS} seconds before next fetch...")
        time.sleep(POLL_INTERVAL_SECONDS)


def main():
    continuous_mode = os.environ.get("REVEL_CONTINUOUS", "true").lower() == "true"
    if continuous_mode:
        run_continuously()
        return

    run_once()


if __name__ == "__main__":
    main()