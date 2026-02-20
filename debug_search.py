import requests
import json
import os

api_key = "41AD58D0-E463-3F72-923C-121ADCB45A9A"
query = "서울역"

SEARCH_URL = "http://api.vworld.kr/req/search"

# Try Search API with different types
search_params = {
    "service": "search",
    "request": "search",
    "key": api_key,
    "query": query,
    "type": "place", # POI
    "format": "json",
    "size": 5
}
try:
    res = requests.get(SEARCH_URL, params=search_params).json()
    with open("search_debug.json", "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2, ensure_ascii=False)
    print("search_debug.json saved")
except Exception as e:
    print(f"Error: {e}")
