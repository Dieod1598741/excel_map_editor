"""
utils/geocoding.py - 브이월드 API 연동 주소 변환 모듈
"""
import requests
from typing import Tuple, Optional, Dict
from config import GEOCODE_URL, SEARCH_URL

class GeocodeEngine:
    """주소 변환 및 검색 최적화 엔진 클래스"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.cache: Dict[str, Tuple[float, float, str]] = {}

    def geocode(self, address: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
        """
        주소를 좌표로 변환합니다. 캐시를 먼저 확인하고 없으면 API를 호출합니다.
        """
        address = str(address).strip()
        if not address or address.lower() == "nan":
            return None, None, None

        if address in self.cache:
            return self.cache[address]

        # 불필요한 문구 제거
        for art in ["(위치를 찾을 수 없음)", "(실패)", "[실패]", "위치를 찾을 수 없음"]:
            address = address.replace(art, "").strip()

        refined_addr = self._standardize_province_name(address)
        lon, lat, road_addr = self._smart_search_orchestrator(refined_addr)
        
        # 세종시 특수 처리
        if not lon and "세종" in refined_addr:
            fb = refined_addr.replace("세종특별자치시", "세종").replace("세종시", "세종")
            if fb != refined_addr:
                lon, lat, road_addr = self._smart_search_orchestrator(fb)

        # 토큰 단위 검색 시도 (상위 주소 축약)
        if not lon:
            parts = refined_addr.split(" ")
            if len(parts) > 2:
                for i in range(1, len(parts) - 1):
                    lon, lat, road_addr = self._smart_search_orchestrator(" ".join(parts[i:]))
                    if lon: break

        if lon:
            self.cache[address] = (lon, lat, road_addr)
            
        return lon, lat, road_addr

    def _smart_search_orchestrator(self, addr: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
        """주소 지오코딩과 검색 API를 병행하여 결과를 찾습니다."""
        # 1. 일반 지오코딩 시도
        lon, lat, r_addr = self._vworld_geocode_raw(addr)
        if lon: return lon, lat, r_addr
        
        # 2. 검색 서비스(POI) 시도
        lon, lat, r_addr = self._vworld_search_raw(addr)
        return lon, lat, r_addr

    def _vworld_geocode_raw(self, addr: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
        params = {
            "service": "address", "request": "getcoord", "version": "2.0",
            "crs": "epsg:4326", "address": addr, "format": "json",
            "type": "ROAD", "key": self.api_key
        }
        try:
            res = requests.get(GEOCODE_URL, params=params).json()
            if res.get("response", {}).get("status") == "OK":
                p = res["response"]["result"]["point"]
                a = res["response"]["refined"]["text"]
                return float(p["x"]), float(p["y"]), a
        except: pass
        return None, None, None

    def _vworld_search_raw(self, query: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
        params = {
            "service": "search", "request": "search", "version": "2.0",
            "crs": "epsg:4326", "query": query, "type": "PLACE",
            "format": "json", "key": self.api_key
        }
        try:
            res = requests.get(SEARCH_URL, params=params).json()
            if res.get("response", {}).get("status") == "OK":
                items = res["response"]["result"]["items"]
                if items:
                    p = items[0]["point"]
                    a = items[0]["address"]["road"] or items[0]["address"]["parcel"]
                    return float(p["x"]), float(p["y"]), a
        except: pass
        return None, None, None

    def _standardize_province_name(self, address: str) -> str:
        replacements = {
            "경기도": "경기", "서울특별시": "서울", "강원도": "강원",
            "충청북도": "충북", "충청남도": "충남", "전라북도": "전북",
            "전라남도": "전남", "경상북도": "경북", "경상남도": "경남",
            "제주특별자치도": "제주", "제주도": "제주", "인천광역시": "인천",
            "부산광역시": "부산", "대구광역시": "대구", "광주광역시": "광주",
            "대전광역시": "대전", "울산광역시": "울산"
        }
        for full, short in replacements.items():
            if address.startswith(full):
                return address.replace(full, short, 1)
        return address
