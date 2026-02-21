"""
config.py - 설정 및 상수 관리 모듈
"""

# 브이월드 API 엔드포인트
VWORLD_GEOCODE_URL = "http://api.vworld.kr/req/address"
VWORLD_SEARCH_URL  = "http://api.vworld.kr/req/search"
VWORLD_STATIC_MAP_URL = "http://api.vworld.kr/req/image"

# 네이버 지도 API 엔드포인트
NAVER_GEOCODE_URL = "https://maps.apigw.ntruss.com/map-geocode/v2/geocode"
NAVER_STATIC_MAP_URL = "https://maps.apigw.ntruss.com/map-static/v2/raster"

# 기본 지도 서비스 제공자
DEFAULT_PROVIDER = "vworld"  # "vworld" 또는 "naver"

# 하위 호환성을 위한 별칭
GEOCODE_URL = VWORLD_GEOCODE_URL
SEARCH_URL = VWORLD_SEARCH_URL
STATIC_MAP_URL = VWORLD_STATIC_MAP_URL

# 투영법 및 지도 관련 상수
TILE_SIZE = 256
DEFAULT_MAP_SIZE = (800, 800)
ZOOM_RANGE = (7.0, 19.0)

# UI 프리셋 색상 팔레트
PRESET_PALETTES = [
    "#1A3A8F",  # 네이비 블루
    "#E83030",  # 빨강
    "#2A9A2A",  # 초록
    "#E87A00",  # 주황
    "#8B008B",  # 보라
    "#008B8B",  # 청록
]

# 타입별 초기 팔레트 인덱스
TYPE_COLOR_MAP = {
    "A": 0, "B": 1, "C": 2, "D": 3, "색상변경": 0
}

# 핀 사이즈 배율
PIN_SIZE_MULT = {
    "작게": 0.7, "보통": 1.0, "크게": 1.4
}

# 방향 선택 사전 (UI 표시용)
LABEL_DIRECTIONS = {
    "↖ 좌상":  "top-left",
    "↑ 위":    "top",
    "↗ 우상":  "top-right",
    "← 왼쪽":  "left",
    "→ 오른쪽": "right",
    "↙ 좌하":  "bottom-left",
    "↓ 아래":  "bottom",
    "↘ 우하":  "bottom-right",
}
LABEL_DIR_KEYS = list(LABEL_DIRECTIONS.keys())

# 방향 아이콘 매핑
DIR_ICON_MAP = {
    "top": "↑", "bottom": "↓", "left": "←", "right": "→",
    "top-left": "↖", "top-right": "↗", "bottom-left": "↙", "bottom-right": "↘"
}

# 사용 가능 폰트 설정
FONT_OPTIONS = {
    "굴림": "gulim.ttc",
    "맑은 고딕": "malgun.ttf"
}
