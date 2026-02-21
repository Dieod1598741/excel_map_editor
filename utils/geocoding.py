"""
utils/geocoding.py - 브이월드 API 연동 주소 변환 모듈 (복구 및 강화 버전)
"""
import requests
from typing import Tuple, Optional, Dict
from config import VWORLD_GEOCODE_URL, VWORLD_SEARCH_URL, NAVER_GEOCODE_URL

class GeocodeEngine:
    """주소 변환 및 검색 최적화 엔진 클래스 (Vworld & Naver 지원)"""
    
    def __init__(self, vworld_key: str = "", naver_client_id: str = "", naver_client_secret: str = ""):
        self.vworld_key = vworld_key
        self.naver_client_id = naver_client_id
        self.naver_client_secret = naver_client_secret
        self.provider = "vworld"
        self.cache: Dict[str, Tuple[float, float, str]] = {}

    def geocode(self, address: str, provider: str = None) -> Tuple[Optional[float], Optional[float], Optional[str]]:
        """
        주소를 좌표로 변환합니다. 캐시를 먼저 확인하고 없으면 선택된 API를 호출합니다.
        """
        if provider:
            self.provider = provider
            
        address = str(address).strip()
        if not address or address.lower() == "nan":
            return None, None, None

        cache_key = f"{self.provider}:{address}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        # 불필요한 문구 제거
        for art in ["(위치를 찾을 수 없음)", "(실패)", "[실패]", "위치를 찾을 수 없음"]:
            address = address.replace(art, "").strip()

        # 1. 광역시/도 이름 정규화 (특별자치도 등 대응)
        refined_addr = self._standardize_province_name(address)
        
        # 2. 스마트 오케스트레이터 호출
        lon, lat, road_addr = self._smart_search_orchestrator(refined_addr)
        
        # 3. 실패 시 세종시 특수 처리
        if not lon and "세종" in refined_addr:
            fb = refined_addr.replace("세종특별자치시", "세종").replace("세종시", "세종")
            if fb != refined_addr:
                lon, lat, road_addr = self._smart_search_orchestrator(fb)

        # 4. 여전히 실패 시 토큰 단위 검색 시도
        if not lon:
            parts = refined_addr.split(" ")
            if len(parts) > 2:
                for i in range(1, len(parts) - 1):
                    lon, lat, road_addr = self._smart_search_orchestrator(" ".join(parts[i:]))
                    if lon: break

        if lon:
            self.cache[cache_key] = (lon, lat, road_addr)
            return lon, lat, road_addr

        # 5. [Advanced] Cross-Provider Fallback
        # 선택한 엔진이 실패했을 경우, 다른 엔진의 검색(POI) 기능을 최후의 수단으로 사용
        other_provider = "vworld" if self.provider == "naver" else "naver"
        print(f"[Advanced Fallback] Trying alternate provider: {other_provider}")
        
        # 임시로 프로바이더 변경 후 오케스트레이터 호출
        original_provider = self.provider
        self.provider = other_provider
        lon, lat, road_addr = self._smart_search_orchestrator(refined_addr)
        self.provider = original_provider
        
        if lon:
            print(f"[Advanced Fallback Success] {address} found via {other_provider}")
            self.cache[cache_key] = (lon, lat, road_addr)
            
        return lon, lat, road_addr

    def _smart_search_orchestrator(self, address: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
        """선택된 프로바이더에 따라 지오코딩과 검색 API를 조율합니다."""
        if self.provider == "naver":
            return self._naver_orchestrator(address)
        else:
            return self._vworld_orchestrator(address)

    def _naver_orchestrator(self, address: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
        """네이버 전용 검색 오케스트레이터 (현재는 지오코딩 중심)"""
        # 1. 일반 지오코딩 시도
        lon, lat, addr = self._naver_geocode_raw(address)
        if lon: return lon, lat, addr

        # 2. (향후 확장) 네이버 지역 검색 API 연동 지점
        # 현재는 네이버 지오코딩 실패 시 바로 리턴하여 상위 단계의 Cross-Fallback 유도
        return None, None, None

    def _vworld_orchestrator(self, address: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
        """Vworld 전용 검색 오케스트레이터"""
        addr_keywords = ['시 ', '구 ', '로 ', '길 ', '동 ', '읍 ', '면 ']
        is_address_like = any(kw in address for kw in addr_keywords)

        if is_address_like:
            lon, lat, addr = self._vworld_geocode_raw(address, type="ROAD")
            if lon: return lon, lat, addr
            lon, lat, addr = self._vworld_geocode_raw(address, type="PARCEL")
            if lon: return lon, lat, addr

        lon, lat, addr = self._vworld_search_raw(address)
        if lon: return lon, lat, addr

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
            "type": type, "key": self.vworld_key
        }
        try:
            print(f"[Vworld Geocode Request] {addr} (type={type})")
            res_raw = requests.get(VWORLD_GEOCODE_URL, params=params, timeout=5, verify=False)
            res = res_raw.json()
            if res.get("response", {}).get("status") == "OK":
                pt = res["response"]["result"]["point"]
                refined = res["response"].get("refined", {}).get("text", addr)
                print(f"[Vworld Geocode Success] {addr} -> {pt['x']}, {pt['y']}")
                return float(pt["x"]), float(pt["y"]), refined
            else:
                # 에러 로그 (개발 및 디버그용)
                print(f"[Vworld Geocode Error] {addr}: {res.get('response', {}).get('status')}")
        except Exception as e:
            print(f"[Vworld Geocode Exception] {e}")
        return None, None, None

    def _vworld_search_raw(self, query: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
        """Vworld 검색(POI) API 직접 호출"""
        params = {
            "service": "search", "request": "search", "version": "2.0",
            "crs": "epsg:4326", "query": query, "type": "place",
            "format": "json", "key": self.vworld_key, "size": 10
        }
        try:
            print(f"[Vworld Search Request] {query}")
            res_raw = requests.get(VWORLD_SEARCH_URL, params=params, timeout=5, verify=False)
            res = res_raw.json()
            if res.get("response", {}).get("status") == "OK":
                items = res["response"]["result"]["items"]
                if items:
                    pt = items[0]["point"]
                    addr_data = items[0].get("roadAddress") or items[0].get("address", "주소 정보 없음")
                    if isinstance(addr_data, dict):
                        # 딕셔너리인 경우 도로명 주소를 우선하고 없으면 지번 주소 사용
                        addr = addr_data.get("road") or addr_data.get("parcel") or "주소 정보 없음"
                    else:
                        addr = str(addr_data)
                    
                    print(f"[Vworld Search Success] {query} -> {pt['x']}, {pt['y']}")
                    return float(pt["x"]), float(pt["y"]), addr
            else:
                print(f"[Vworld Search Error] {query}: {res.get('response', {}).get('status')}")
        except Exception as e:
            print(f"[Vworld Search Exception] {e}")
        return None, None, None

    def _naver_geocode_raw(self, addr: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
        """네이버 지오코딩 API 직접 호출"""
        headers = {
            "X-NCP-APIGW-API-KEY-ID": self.naver_client_id,
            "X-NCP-APIGW-API-KEY": self.naver_client_secret,
            "Accept": "application/json"
        }
        params = {"query": addr}
        try:
            print(f"[Naver Geocode Request] {addr}")
            res_raw = requests.get(NAVER_GEOCODE_URL, headers=headers, params=params, timeout=5, verify=False)
            res = res_raw.json()
            if res.get("addresses"):
                item = res["addresses"][0]
                print(f"[Naver Geocode Success] {addr} -> {item['x']}, {item['y']}")
                return float(item["x"]), float(item["y"]), item["roadAddress"] or item["jibunAddress"]
            else:
                print(f"[Naver Geocode Error] {addr}: {res.get('errorMessage', 'No results')}")
        except Exception as e:
            print(f"[Naver Geocode Exception] {e}")
        return None, None, None

    def _standardize_province_name(self, address: str) -> str:
        """광역시/도 이름을 정식 명칭이나 특별자치도 명칭으로 보정합니다."""
        replacements = {
            "서울시 ": "서울특별시 ",
            "서울 ": "서울특별시 ",
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
