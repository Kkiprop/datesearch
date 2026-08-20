import requests
import json
from datetime import  datetime, timedelta
import datetime as dt
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDS_PATH = os.path.join(BASE_DIR, "json_creds", "revel_creds.json")
EXPORT_DIR = os.path.join(BASE_DIR, "revel_exports")
EXPORT_PATH = os.path.join(EXPORT_DIR, "revel_first_100_records.json")


def load_revel_credentials():
    with open(CREDS_PATH, "r", encoding="utf-8") as file:
        return json.load(file)


def build_revel_url(base_url, endpoint_path):
    normalized_base_url = base_url.rstrip("/")
    if normalized_base_url.endswith("/reports"):
        normalized_base_url = normalized_base_url[: -len("/reports")]

    return f"{normalized_base_url}/{endpoint_path.lstrip('/')}"


def save_revel_export(date_str, store_data):
    os.makedirs(EXPORT_DIR, exist_ok=True)

    payload = {
        "generated_at": datetime.now().isoformat(),
        "date": date_str,
        "data": store_data,
    }

    with open(EXPORT_PATH, "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=4)

    return EXPORT_PATH

def fetch_sales_summary(date_str):
    # === Load API credentials ===
    api_details = load_revel_credentials()
    export_data = {}

    for api in api_details:
        # print(f"Using API: {api['base_url']}")
        base_url = api["base_url"]
        auth_header = f"{api['api_auth_key']}:{api['api_auth_secret']}"
        establishments = api["establishments"]

        for establishment in establishments:
            establishment_name = f"{base_url.split('.')[0].split('//')[1]}{establishment}"
            print()
            print(f"Fetching data for {establishment_name} on {date_str}...")
            # date is already a pure date() object
            range_from = date_str + " 00:00"
            range_to   = date_str + " 23:59"

            # === Construct the full URL ===
            url = build_revel_url(base_url, "reports/sales_summary/json/")
            params = {
                "posstation": "",
                "employee": "",
                "show_unpaid": 1,
                "show_irregular": 1,
                "range_from": range_from,
                "range_to": range_to,
                "establishment": establishment,
                "format": "json",
            }
            headers = {
                "API-AUTHENTICATION": auth_header,
                "Accept": "application/json"
            }

            # print(f"📡 Fetching data from: {url}")
            response = requests.get(url, headers=headers, params=params, timeout=60)

            if response.status_code == 200:
                print("✅ Data retrieved successfully!")
                data = response.json()
                if isinstance(data, list):
                    first_100_items = data[:100]
                else:
                    first_100_items = [data]

                export_data[establishment_name] = {
                    "item_count": len(first_100_items),
                    "items": first_100_items,
                }
                print(f"💾 Prepared {len(first_100_items)} items for {establishment_name}")
            else:
                print(f"❌ Failed to fetch data. HTTP {response.status_code}: {response.text}")
                # return None

    output_path = save_revel_export(date_str, export_data)
    print(f"💾 Saved Revel export → {output_path}")
    return output_path


def get_sales_mongo_connection():
    try:
        from pymongo import MongoClient

        with open('json_creds/mongo_string.json') as f:
            mongo_string = json.load(f)["mongo_string"]
        
        client = MongoClient(mongo_string)
        db = client["Dashboard_data"]
        collection = db["store_wise_sales"]
        collection.find_one()
        print("✅ Connected to MongoDB successfully.")
        return collection
    except Exception as e:
        print(f"❌ Error connecting to MongoDB: {e}")
        return None
    
def get_customer_dashboard_mongo_connection():
    """
    Returns a MongoDB connection and collection object.
    """
    try:
        from pymongo import MongoClient

        with open('json_creds/mongo_string.json') as f:
            mongo_string = json.load(f)["mongo_string"]
        
        client = MongoClient(mongo_string)
        db = client["Dashboard_data"]
        collection = db["customer_count"]
        
        # Test the connection
        collection.find_one()
        print("✅ Connected to MongoDB successfully.")
        return collection
    except Exception as e:
        print(f"❌ Error connecting to MongoDB: {e}")
        return None


def update_mongo(date_str):
    sales_collection = get_sales_mongo_connection()
    customer_collection = get_customer_dashboard_mongo_connection()

    if sales_collection is None or customer_collection is None:
        print("❌ No Mongo connection for both sales and customer count, aborting update.")
        return

    establishment_mapping = {
        "apnabazar1": "Sunnyvale",
        "apnabazar2": "Fremont",
        "stopandshopca1": "Karthik",
        "stopandshopca2": "Milpitas"
    }

    filename = "sales_summary/sales_summary.json"

    if not os.path.exists(filename):
        print("❌ sales_summary.json file not found.")
        return

    # Load sales JSON
    with open(filename, "r", encoding="utf-8") as f:
        try:
            all_data = json.load(f)
        except json.JSONDecodeError:
            print("❌ sales_summary.json is corrupted or invalid JSON.")
            return

    if date_str not in all_data:
        print(f"⚠️ No data found for {date_str} in sales_summary.json")
        return
    # Extract the day's data
    day_data = all_data[date_str]
    # print(day_data)
    mapped_day_data = {
            establishment_mapping.get(store_key, store_key): store_values
            for store_key, store_values in day_data.items()
            }
    
    try:
        gross_margin_file ='gross_margin/gross_margin_history.json'
        if os.path.exists(gross_margin_file):
            try:
                with open(gross_margin_file, "r") as f:
                    history = json.load(f)
            except Exception:
                history = {}
        else:
            history = {}
        # # Prepare results
        # results_for_date = {
        #     "date": date_str,
        #     "stores": {}
        # }
        results_for_date = history[date_str]
        results_for_date["sales_data"] = mapped_day_data

        history[date_str] = results_for_date
        try:
            with open(gross_margin_file, "w") as f:
                json.dump(history, f, indent=4, default=str)
            print(f"✅ Gross margin results saved/updated in {gross_margin_file}")
        except Exception as e:
            print(f"❌ Error writing to {gross_margin_file}: {e}")
    except Exception as e:
        print("Adding sales data to gm file failed",e)

    

    sales_data = {}
    customer_count_data = {}

    # Map and prepare for Mongo
    for store_key, store_values in day_data.items():
        mapped_name = establishment_mapping.get(store_key, store_key)

        customer_count_data[mapped_name] = store_values.get("customer_count", 0)
        # Copy all other metrics except 'customer_count'
        sales_data[mapped_name] = {
            key: value
            for key, value in store_values.items()
            if key != "customer_count"
        }


    # ✅ Update MongoDB: Sales Summary
    sales_collection.update_one(
        {"date": date_str},
        {
            "$set": {
                "date": date_str,
                "sales_data": sales_data,
                "updated_at": datetime.now()
            }
        },
        upsert=True
    )
    print(f"✅ Sales data updated for {date_str}")

    # ✅ Update MongoDB: Customer Count Summary
    customer_collection.update_one(
        {"date": date_str},
        {
            "$set": {
                "date": date_str,
                "customer_count": customer_count_data,
                "updated_at": datetime.now()
            }
        },
        upsert=True
    )
    print(f"✅ Customer count data updated for {date_str}")

def get_missing_dates_from_2024(collection):

    today_sf = datetime.now().date()

    start_date = dt.date(2024, 1, 1)
    end_date = today_sf - timedelta(days=1)
    print()
    print(f"Checking for missing dates from {start_date} to {end_date} in MongoDB collection: {collection.name}")

    # ✅ Get all existing dates (only by date field)
    existing_dates = collection.distinct("date")
    existing_dates_set = set(existing_dates)

    missing_dates = []
    current_date = start_date

    while current_date <= end_date:
        date_str = current_date.strftime("%Y-%m-%d")

        if date_str not in existing_dates_set:
            missing_dates.append(date_str)

        current_date += timedelta(days=1)

    print("\n📊 Missing Dates Summary")
    print(f"Total Expected Days : {(end_date - start_date).days + 1}")
    print(f"Existing Dates      : {len(existing_dates_set)}")
    print(f"Missing Dates Count : {len(missing_dates)} ,{missing_dates}")

    return missing_dates

def main():
    date_str = (datetime.now() - timedelta(days=1)).date().strftime("%Y-%m-%d")

    print()
    print(f"Processing date: {date_str}")
    print("=" * 70)
    print(f"⏳ Fetching first 100 sales summary items for {date_str}")
    print("=" * 70)

    try:
        fetch_sales_summary(date_str)
        print("✅ Revel export completed.")
    except Exception as e:
        print(f"❌ Error occurred: {e}")

if __name__ == "__main__":
    main()
