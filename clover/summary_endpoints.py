import json

POSTMAN_FILE = r"C:\Users\Admin\Downloads\clover_api_tutorial.postman_collection.json_\clover_api_tutorial.postman_collection.json"

with open(POSTMAN_FILE, "r", encoding="utf-8") as f:
    collection = json.load(f)

print("=" * 120)
print(f"{'METHOD':8} {'ENDPOINT':65} {'NAME':35}")
print("=" * 120)

def walk(items):
    for item in items:

        # Folder
        if "item" in item:
            walk(item["item"])
            continue

        req = item["request"]

        method = req.get("method", "")

        url = req["url"]

        if isinstance(url, str):
            endpoint = url
        else:
            endpoint = url.get("raw", "")

        print(f"{method:8} {endpoint:65} {item['name']}")

walk(collection["item"])

print("=" * 120)