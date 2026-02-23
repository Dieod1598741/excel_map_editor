import requests
import json
import os

def test_naver():
    # De-duplicated keys based on dist/config.json observation
    client_id = "kqja3dhvg0"
    client_secret = "WkNeQvPDGfyKtZW9Eg6kXKhfysbD4ug7L9zZxbAK"
    
    url = "https://maps.apigw.ntruss.com/map-geocode/v2/geocode"
    headers = {
        "X-NCP-APIGW-API-KEY-ID": client_id,
        "X-NCP-APIGW-API-KEY": client_secret,
        "Accept": "application/json"
    }
    params = {"query": "서울특별시 중구 세종대로 110"}
    
    print(f"Testing Naver API with ID: {client_id}...")
    try:
        res = requests.get(url, headers=headers, params=params, timeout=10)
        print(f"Status Code: {res.status_code}")
        print(f"Response: {res.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_naver()
