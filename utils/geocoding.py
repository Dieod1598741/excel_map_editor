"""
utils/geocoding.py - 브이월드 API 연동 주소 변환 모듈 (복구 및 강화 버전)
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

        # 1. 광역시/도 이름 정규화 (특별자치도 등 대응)
        refined_addr = self._standardize_province_name(address)
        
        # 2. 스마트 오케스트레이터 호출 (지오코딩 -> 검색 -> 세종시 예외 -> 부분 검색)
        lon, lat, road_addr = self._smart_search_orchestrator(refined_addr)
        
        # 3. 실패 시 세종시 특수 처리 (축약형 시도)
        if not lon and "세종" in refined_addr:
            fb = refined_addr.replace("세종특별자치시", "세종").replace("세종시", "세종")
            if fb != refined_addr:
                lon, lat, road_addr = self._smart_search_orchestrator(fb)

        # 4. 여전히 실패 시 토큰 단위 검색 시도 (상위 주소 축약)
        if not lon:
            parts = refined_addr.split(" ")
            if len(parts) > 2:
                for i in range(1, len(parts) - 1):
                    lon, lat, road_addr = self._smart_search_orchestrator(" ".join(parts[i:]))
                    if lon: break

        if lon:
            self.cache[address] = (lon, lat, road_addr)
            
        return lon, lat, road_addr

    def _smart_search_orchestrator(self, address: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
        """주소 지오코딩과 검색 API를 병행하여 결과를 찾습니다."""
        addr_keywords = ['시 ', '구 ', '로 ', '길 ', '동 ', '읍 ', '면 ']
        is_address_like = any(kw in address for kw in addr_keywords)

        # 1. 주소 형태인 경우 지오코딩 우선 시도 (ROAD -> PARCEL)
        if is_address_like:
            lon, lat, addr = self._vworld_geocode_raw(address, type="ROAD")
            if lon: return lon, lat, addr
            lon, lat, addr = self._vworld_geocode_raw(address, type="PARCEL")
            if lon: return lon, lat, addr

        # 2. 장소/명칭 검색 시도 (POI 검색)
        lon, lat, addr = self._vworld_search_raw(address)
        if lon: return lon, lat, addr

        # 3. 뒤에서부터 단어를 조합하여 재검색 (복합 명칭 대응)
        if " " in address:
            parts = address.split(" ")
            for i in range(len(parts)-1, 0, -1):
                sub_query = " ".join(parts[i:])
                if len(sub_query) > 1:
                    lon, lat, addr = self._vworld_search_raw(sub_query)
                    if lon: return lon, lat, addr

        return None, None, None

    def _vworld_geocode_raw(self, addr: str, type: str = "ROAD") -> Tuple[Optional[float], Optional[float], Optional[str]]:
        """Vworld 주소 지오코딩 API 직접 호출"""
        params = {
            "service": "address", "request": "getCoord", "version": "2.0",
            "crs": "epsg:4326", "address": addr, "format": "json",
            "type": type, "key": self.api_key
        }
        try:
            res = requests.get(GEOCODE_URL, params=params).json()
            if res.get("response", {}).get("status") == "OK":
                pt = res["response"]["result"]["point"]
                refined = res["response"].get("refined", {}).get("text", addr)
                return float(pt["x"]), float(pt["y"]), refined
        except: pass
        return None, None, None

    def _vworld_search_raw(self, query: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
        """Vworld 검색(POI) API 직접 호출"""
        params = {
            "service": "search", "request": "search", "version": "2.0",
            "crs": "epsg:4326", "query": query, "type": "place",
            "format": "json", "key": self.api_key, "size": 10
        }
        try:
            res = requests.get(SEARCH_URL, params=params).json()
            if res.get("response", {}).get("status") == "OK":
                items = res["response"]["result"]["items"]
                if items:
                    pt = items[0]["point"]
                    addr = items[0].get("roadAddress") or items[0].get("address", "주소 정보 없음")
                    return float(pt["x"]), float(pt["y"]), addr
        except: pass
        return None, None, None

    def _standardize_province_name(self, address: str) -> str:
        """광역시/도 이름을 정식 명칭이나 특별자치도 명칭으로 보정합니다."""
        replacements = {
            "강원도": "강원특별자치도",
            "전라북도": "전북특별자치도",
            "세종시": "세종특별자치시",
            "세종 ": "세종특별자치시 ",
            "제주시": "제주특별자치도 제주시",
            "서귀포시": "제주특별자치도 서귀포시",
        }
        for old, new in replacements.items():
            if old in address and new not in address:
                address = address.replace(old, new)
        return address
