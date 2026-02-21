import os
import sys
from typing import List

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.geocoding import GeocodeEngine
import json

def test_advanced_geocoding():
    # .env 또는 config.json에서 키 가져오기
    n_id = ""
    n_sec = ""
    v_key = ""
    
    env_path = ".env"
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if k == "NAVER_CLIENT_ID": n_id = v
                    elif k == "NAVER_CLIENT_SECRET": n_sec = v
                    elif k == "VWORLD_KEY": v_key = v

    if not n_id or not v_key:
        cfg_path = "config.json"
        if os.path.exists(cfg_path):
            with open(cfg_path, "r") as f:
                data = json.load(f)
                n_id = n_id or data.get("naver_client_id", "")
                n_sec = n_sec or data.get("naver_client_secret", "")
                v_key = v_key or data.get("vworld_key", "")

    engine = GeocodeEngine(vworld_key=v_key, naver_client_id=n_id, naver_client_secret=n_sec)
    
    test_cases = ["강남역", "인천국제공항", "롯데월드타워", "서울시청"]
    providers = ["naver", "vworld"]

    print(f"--- Advanced Geocoding Test (Hybrid Orchestrator) ---")
    
    for provider in providers:
        print(f"\n[Provider: {provider.upper()}]")
        for case in test_cases:
            print(f"Testing: {case}...")
            lon, lat, addr = engine.geocode(case, provider=provider)
            if lon:
                print(f"  SUCCESS: {case} -> ({lon}, {lat}) | {addr}")
            else:
                print(f"  FAILED: {case}")

if __name__ == "__main__":
    test_advanced_geocoding()
