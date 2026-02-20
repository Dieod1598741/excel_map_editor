import requests
import json
import os
import math

GEOCODE_URL = "http://api.vworld.kr/req/address"
SEARCH_URL = "http://api.vworld.kr/req/search"
api_key = "41AD58D0-E463-3F72-923C-121ADCB45A9A"

def _try_geocode_api(address):
    addr_params = {
        "service": "address",
        "request": "getCoord",
        "key": api_key,
        "address": address,
        "type": "ROAD",
        "format": "json"
    }
    try:
        response = requests.get(GEOCODE_URL, params=addr_params)
        data = response.json()
        if data.get("response", {}).get("status") == "OK":
            result = data["response"]["result"]["point"]
            refined_addr = data["response"].get("refined", {}).get("text", address)
            return float(result["x"]), float(result["y"]), refined_addr
    except: pass
    return None, None, None

def _try_search_api(address, refined=False):
    query = address
    if refined and " " not in address:
        query = f"{address} 서울"
        
    search_params = {
        "service": "search",
        "request": "search",
        "key": api_key,
        "query": query,
        "type": "place",
        "category": "point",
        "size": 10,
        "format": "json"
    }
    try:
        response = requests.get(SEARCH_URL, params=search_params)
        data = response.json()
        if data.get("response", {}).get("status") == "OK":
            items = data["response"]["result"]["items"]
            if items:
                point = items[0]["point"]
                road_addr = items[0].get("roadAddress")
                if not road_addr: road_addr = items[0].get("address", "주소 정보 없음")
                return float(point["x"]), float(point["y"]), road_addr
    except: pass
    return None, None, None

def geocode(address):
    address = str(address).strip()
    if not address or address == "nan":
        return None, None, None
        
    addr_keywords = ['시 ', '구 ', '로 ', '길 ', '동 ', '읍 ', '면 ']
    is_address_like = any(kw in address for kw in addr_keywords)
    
    if not is_address_like:
        print(f"[{address}] Treating as POI-first")
        lon, lat, road_addr = _try_search_api(address)
        if lon: return lon, lat, road_addr
        
        lon, lat, refined_addr = _try_geocode_api(address)
        if lon: return lon, lat, refined_addr
        
        return _try_search_api(address, refined=True)
    else:
        print(f"[{address}] Treating as Address-first")
        lon, lat, refined_addr = _try_geocode_api(address)
        if lon: return lon, lat, refined_addr
        
        return _try_search_api(address)

test_cases = ["서울역", "경복궁", "서울특별시 중구 세종대로 110"]
for case in test_cases:
    lon, lat, addr = geocode(case)
    print(f"Result for '{case}': {lon}, {lat} ({addr})")
