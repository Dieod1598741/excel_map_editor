"""
utils/geo_utils.py - 좌표계 변환 및 지도 계산 유틸리티
"""
import math
from typing import Tuple, List
from config import TILE_SIZE

def latlon_to_pixel(lat: float, lon: float, zoom: float, center_lat: float, center_lon: float, map_width: int, map_height: int) -> Tuple[int, int]:
    """
    WGS84 위경도를 Web Mercator 투영법을 통해 픽셀 좌표로 변환합니다.
    """
    def lon_to_x(ln, z):
        return (ln + 180.0) / 360.0 * (TILE_SIZE * (2 ** z))

    def lat_to_y(lt, z):
        lr = math.radians(lt)
        return (1.0 - math.log(math.tan(lr) + 1.0 / math.cos(lr)) / math.pi) / 2.0 * (TILE_SIZE * (2 ** z))

    cx = lon_to_x(center_lon, zoom)
    cy = lat_to_y(center_lat, zoom)
    px = lon_to_x(lon, zoom)
    py = lat_to_y(lat, zoom)
    return int(map_width / 2 + (px - cx)), int(map_height / 2 + (py - cy))

def calculate_zoom_and_center(coords: List[Tuple[float, float]], map_width: int, map_height: int, padding: float = 0.05) -> Tuple[float, float, float]:
    """
    데이터 포인트들이 모두 포함되도록 최적의 중심점과 줌 레벨을 계산합니다.
    """
    if not coords:
        return 37.5666, 126.9784, 12.0

    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    min_lon, max_lon = min(lons), max(lons)
    min_lat, max_lat = min(lats), max(lats)

    def lat_to_merc_y(lt):
        lr = math.radians(lt)
        return math.log(math.tan(lr) + 1.0 / math.cos(lr))

    def merc_y_to_lat(y):
        return math.degrees(math.atan(math.sinh(y)))

    min_y = lat_to_merc_y(min_lat)
    max_y = lat_to_merc_y(max_lat)
    center_lon = (min_lon + max_lon) / 2
    center_lat = merc_y_to_lat((min_y + max_y) / 2)

    # 핀과 라벨 공간 확보용 여백
    base_margin    = int(map_width * padding / 2)
    pin_height_buf = 30
    label_width_buf = 60
    top_margin  = base_margin + pin_height_buf
    side_margin = base_margin + label_width_buf

    for test_zoom in range(180, 69, -1):
        z = test_zoom / 10.0
        all_fit = True
        for lon, lat in coords:
            px, py = latlon_to_pixel(lat, lon, z, center_lat, center_lon, map_width, map_height)
            if (px < side_margin or px > map_width - side_margin or
                    py < top_margin or py > map_height - base_margin):
                all_fit = False
                break
        if all_fit:
            return center_lat, center_lon, z

    return center_lat, center_lon, 7.0

def hex_to_rgba(hex_color: str, alpha: int = 140) -> Tuple[int, int, int, int]:
    """16진수 색상 코드를 RGBA 튜플로 변환합니다."""
    hex_color = hex_color.lstrip('#')
    lv = len(hex_color)
    rgb = tuple(int(hex_color[i:i + lv // 3], 16) for i in range(0, lv, lv // 3))
    return (*rgb, alpha)
