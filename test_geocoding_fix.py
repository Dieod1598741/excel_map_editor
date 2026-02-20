from utils.geocoding import GeocodeEngine
import requests

api_key = "41AD58D0-E463-3F72-923C-121ADCB45A9A"
engine = GeocodeEngine(api_key)

addresses = [
    "서울 중구 한강대로 405",
    "만리재로 81",
    "서울특별시 중구 한강대로 405"
]

for addr in addresses:
    print(f"\n--- Testing: {addr} ---")
    lon, lat, r_addr = engine.geocode(addr)
    if lon:
        print(f"Success! {lon}, {lat} ({r_addr})")
    else:
        print("Failed.")
