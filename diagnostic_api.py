import requests

api_key = "41AD58D0-E463-3F72-923C-121ADCB45A9A"
GEOCODE_URL = "http://api.vworld.kr/req/address"
SEARCH_URL  = "http://api.vworld.kr/req/search"

def test_geocode(addr):
    # Test lowercase getcoord
    params1 = {
        "service": "address", "request": "getcoord", "version": "2.0",
        "crs": "epsg:4326", "address": addr, "format": "json",
        "type": "ROAD", "key": api_key
    }
    
    # Test CamelCase getCoord
    params2 = {
        "service": "address", "request": "getCoord", "version": "2.0",
        "crs": "epsg:4326", "address": addr, "format": "json",
        "type": "ROAD", "key": api_key
    }

    try:
        r1 = requests.get(GEOCODE_URL, params=params1).json()
        print(f"Request 'getcoord' status: {r1.get('response', {}).get('status')}")
    except Exception as e:
        print(f"Request 'getcoord' failed: {e}")

    try:
        r2 = requests.get(GEOCODE_URL, params=params2).json()
        print(f"Request 'getCoord' status: {r2.get('response', {}).get('status')}")
    except Exception as e:
        print(f"Request 'getCoord' failed: {e}")

def test_search(query):
    # Test type PLACE
    params1 = {
        "service": "search", "request": "search", "version": "2.0",
        "crs": "epsg:4326", "query": query, "type": "PLACE",
        "format": "json", "key": api_key
    }
    
    # Test type place
    params2 = {
        "service": "search", "request": "search", "version": "2.0",
        "crs": "epsg:4326", "query": query, "type": "place",
        "format": "json", "key": api_key
    }

    try:
        r1 = requests.get(SEARCH_URL, params=params1).json()
        # print(r1)
        print(f"Search 'PLACE' status: {r1.get('response', {}).get('status')}")
    except Exception as e:
        print(f"Search 'PLACE' failed: {e}")

    try:
        r2 = requests.get(SEARCH_URL, params=params2).json()
        # print(r2)
        print(f"Search 'place' status: {r2.get('response', {}).get('status')}")
    except Exception as e:
        print(f"Search 'place' failed: {e}")

addr = "서울 중구 한강대로 405"
print(f"--- Testing Address: {addr} ---")
test_geocode(addr)
test_search(addr)

addr2 = "만리재로 81"
print(f"\n--- Testing Address: {addr2} ---")
test_geocode(addr2)
test_search(addr2)
