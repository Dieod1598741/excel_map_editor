import requests
import json
import os

def test_naver_verbose():
    # .env 또는 config.json에서 키 가져오기
    vworld_key = ""
    n_id = ""
    n_sec = ""
    
    env_path = ".env"
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if k == "NAVER_CLIENT_ID": n_id = v
                    elif k == "NAVER_CLIENT_SECRET": n_sec = v

    if not n_id:
        cfg_path = "config.json"
        if os.path.exists(cfg_path):
            with open(cfg_path, "r") as f:
                data = json.load(f)
                n_id = data.get("naver_client_id", "")
                n_sec = data.get("naver_client_secret", "")

    print(f"--- Naver API Verbose Test ---")
    print(f"Client ID: {n_id}")
    # print(f"Client Secret: {n_sec}")

    url = "https://maps.apigw.ntruss.com/map-geocode/v2/geocode"
    headers = {
        "X-NCP-APIGW-API-KEY-ID": n_id,
        "X-NCP-APIGW-API-KEY": n_sec,
        "Accept": "application/json"
    }
    params = {"query": "서울특별시 중구 세종대로 110"}

    try:
        print(f"Requesting URL: {url}")
        res = requests.get(url, headers=headers, params=params, timeout=5, verify=False)
        print(f"HTTP Status Code: {res.status_code}")
        print("Response Body (Raw JSON):")
        print(json.dumps(res.json(), indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    test_naver_verbose()
