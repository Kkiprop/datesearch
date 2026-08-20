import os
from serpapi import GoogleSearch

# Your SerpApi Key
API_KEY = "218610204b15734acad6664bc8a19db25ab24dc365f8e0091f047195b19b58c1"  # Note: double-check if this key was truncated!

# Initialize the search with Google Events engine
search = GoogleSearch(
    {
        "engine": "google_events",
        "q": "events in Mombasa",
        "hl": "en",  # Language
        "gl": "ke",  # Country code (Kenya)
        "api_key": API_KEY,  # Passing the variable here
    }
)

results = search.get_dict()

if "error" in results:
    print(f"SerpApi Error: {results['error']}")
else:
    events_list = results.get("events_results", [])

    print(f"Found {len(events_list)} events in Mombasa:\n" + "=" * 40 + "\n")

    # Parse and print the events data
    for event in events_list:
        # SerpApi dates usually provide a 'when' string (e.g., "Fri, Jul 3, 6 PM")
        event_date = event.get("date", {}).get("when", "No date listed")

        print(f"🎉 Title: {event.get('title')}")
        print(f"📅 Date: {event_date}")
        print(f"📍 Venue: {event.get('venue', {}).get('name', 'Unknown Venue')}")
        print(f"🔗 Link: {event.get('link', 'No link available')}\n" + "-" * 30)