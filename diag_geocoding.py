import requests
import json
import os
import sys

# Add current directory to path
sys.path.append(os.getcwd())

from config import VWORLD_GEOCODE_URL, VWORLD_SEARCH_URL, NAVER_GEOCODE_URL

def test_vworld(key):
    print(f"--- Testing Vworld (Key: {key[:5]}...) ---")
    params = {
        "service": "address", "request": "getCoord", "version": "2.0",
        "crs": "epsg:4326", "address": "서울시 중구 세종대로 110", "format": "json",
        "type": "ROAD", "key": key
    }
    try:
        res = requests.get(VWORLD_GEOCODE_URL, params=params, timeout=5, verify=False)
        print(f"Status Code: {res.status_code}")
        print(f"Response: {res.text}")
    except Exception as e:
        print(f"Exception: {e}")

def test_naver(client_id, client_secret):
    print(f"--- Testing Naver (ID: {client_id[:3]}...) ---")
    headers = {
        "X-NCP-APIGW-API-KEY-ID": client_id,
        "X-NCP-APIGW-API-KEY": client_secret
    }
    params = {"query": "서울시 중구 세종대로 110"}
    try:
        res = requests.get(NAVER_GEOCODE_URL, headers=headers, params=params, timeout=5, verify=False)
        print(f"Status Code: {res.status_code}")
        print(f"Response: {res.text}")
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    cfg_path = "config.json"
    if os.path.exists(cfg_path):
        with open(cfg_path, "r") as f:
            cfg = json.load(f)
            v_key = cfg.get("vworld_key", "")
            n_id = cfg.get("naver_client_id", "")
            n_sec = cfg.get("naver_client_secret", "")
            
            test_vworld(v_key)
            print("\n")
            # Also test the hardcoded key from test_geocode.py
            test_vworld("41AD58D0-E463-3F72-923C-121ADCB45A9A")
            print("\n")
            test_naver(n_id, n_sec)
    else:
        print("config.json not found")
