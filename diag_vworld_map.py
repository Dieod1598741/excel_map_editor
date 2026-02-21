import requests
import json
import os

def test_vworld_map(key):
    print(f"--- Testing Vworld Static Map (Key: {key[:5]}...) ---")
    url = "http://api.vworld.kr/req/image"
    params = {
        "service": "image", "request": "getmap",
        "key": key,
        "center": "126.9784,37.5666", # clon, clat
        "zoom": 12,
        "size": "800,800",
        "basemap": "GRAPHIC", "format": "png",
    }
    try:
        res = requests.get(url, params=params, timeout=10, verify=False)
        print(f"Status Code: {res.status_code}")
        print(f"Content Length: {len(res.content)}")
        if res.status_code == 200:
            if b"PNG" in res.content[:10]:
                print("Success: Valid PNG received")
                with open("test_map_vworld.png", "wb") as f:
                    f.write(res.content)
                print("Saved to test_map_vworld.png")
            else:
                print(f"Error: Invalid content type or error message: {res.text[:200]}")
        else:
            print(f"Error: HTTP {res.status_code}")
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    # .env 파일에서 키 읽기 시도
    v_key = os.getenv("VWORLD_API_KEY", "")
    if not v_key:
        # env_path = ".env"
        # ... logic to read .env ...
        pass
    
    # 임시 하드코딩 (테스트용)
    if not v_key:
        v_key = "41AD58D0-E463-3F72-923C-121ADCB45A9A"
        
    test_vworld_map(v_key)
