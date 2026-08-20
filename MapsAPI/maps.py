import json
import requests

API_KEY = "218610204b15734acad6664bc8a19db25ab24dc365f8e0091f047195b19b58c1"
BASE_URL = "https://serpapi.com/search.json"

# Updated with your working Postman query string
locations = [
    {"q": "apni mandi fremont", "ll": "@37.4529199,-122.1284151,11z"},
    {"q": "apni mandi san jose", "ll": "@37.3382082,-121.8863286,14z"},
    {"q": "apni mandi sunnyvale", "ll": "@37.3688301,-122.0363496,14z"},
]

results = []

for loc in locations:
    print(f"Processing: {loc['q']}...")

    params = {
        "engine": "google_maps",
        "q": loc["q"],
        "ll": loc["ll"],
        "api_key": API_KEY,
    }

    try:
        response = requests.get(BASE_URL, params=params)
        data = response.json()
    except Exception as e:
        print(f"  Error fetching data: {e}")
        continue

    if "error" in data:
        print(f"  SerpApi Error: {data['error']}")
        continue

    # --- CASE 1: Multiple results (List View) ---
    local_results = data.get("local_results", [])

    # --- CASE 2: Single exact match (Direct Profile View) ---
    # If it's a direct match, SerpApi wraps it in 'place_results' instead of a list
    if not local_results and "place_results" in data:
        local_results = [data.get("place_results")]

    if not local_results:
        print(f"  ❌ No results or place profile found for this query.")
        continue

    # Extract popular_times
    for place in local_results:
        popular_times = place.get("popular_times")
        name = place.get("title") or place.get("name")

        if popular_times:
            results.append(
                {
                    "name": name,
                    "address": place.get("address"),
                    "query": loc["q"],
                    "popular_times": popular_times,
                }
            )
            print(f"  ✅ Successfully saved popular_times for {name}")
        else:
            print(f"  ⚠️ Found {name}, but no popular_times graph available.")

# Output to JSON file
output_file = "popular_times.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print(
    f"\nDone. {len(results)} place(s) with popular_times saved to {output_file}"
)