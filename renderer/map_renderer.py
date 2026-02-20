"""
renderer/map_renderer.py - 지도 마커 및 라벨 렌더링 엔진
"""
import math
from typing import List, Dict, Tuple, Any, Optional
from PIL import Image, ImageDraw, ImageFont
from config import TILE_SIZE, PIN_SIZE_MULT, DIR_ICON_MAP
from utils.geo_utils import latlon_to_pixel

def draw_outline_pin(draw, px, py, radius, border_color=(26, 58, 143, 200), border_width=2):
    """지정된 위치에 외곽선이 있는 핀(마커)을 그립니다."""
    draw.ellipse([px - radius, py - radius, px + radius, py + radius], 
                 fill=(255, 255, 255, 255), 
                 outline=border_color, width=border_width)

def hex_to_rgba(hex_color: str, alpha: int = 255) -> Tuple[int, int, int, int]:
    """16진수 색상 코드를 RGBA 튜플로 변환합니다."""
    hex_color = hex_color.lstrip('#')
    lv = len(hex_color)
    rgb = tuple(int(hex_color[i:i + lv // 3], 16) for i in range(0, lv, lv // 3))
    return (*rgb, alpha)

class MapRenderer:
    """지도 이미지 위에 마커와 라벨을 그리는 렌더링 클래스"""

    @staticmethod
    def render_current_view(
        raw_map_img: Image.Image,
        current_zoom: float,
        current_center: Tuple[float, float],
        last_api_center: Tuple[float, float],
        last_api_zoom: int,
        place_data: List[Dict[str, Any]],
        pin_size_key: str,
        font_size: int,
        type_colors: Dict[str, str],
        old_map_img: Optional[Image.Image] = None,
        old_last_center: Optional[Tuple[float, float]] = None,
        old_last_zoom: Optional[int] = None,
        blend_alpha: float = 1.0
    ) -> Tuple[Image.Image, List[Dict[str, Any]]]:
        """
        메인 하이브리드 렌더링 엔진.
        지도의 팬/줌 처리 및 충돌 방지 로직이 포함된 마커/라벨 배치를 수행합니다.
        """
        map_w, map_h = 800, 800
        zoom = current_zoom
        clat, clon = current_center

        # 1. 하이브리드 확대/축소 로직
        zoom_diff = zoom - last_api_zoom
        scale_factor = 2.0 ** zoom_diff
        num_tiles = 2 ** zoom
        pixel_per_degree = (num_tiles * TILE_SIZE) / 360.0
        blat, blon = last_api_center
        cos_lat = math.cos(math.radians(clat))

        off_x = (clon - blon) * pixel_per_degree * cos_lat
        off_y = -(clat - blat) * pixel_per_degree

        new_size = (int(map_w * scale_factor), int(map_h * scale_factor))
        temp_scaled = raw_map_img.resize(new_size, Image.LANCZOS)
        left = (new_size[0] - map_w) / 2 + off_x
        top  = (new_size[1] - map_h) / 2 + off_y
        view_current = temp_scaled.crop((left, top, left + map_w, top + map_h))

        if old_map_img and blend_alpha < 1.0:
            o_zoom_diff = zoom - old_last_zoom
            o_scale_factor = 2.0 ** o_zoom_diff
            o_blat, o_blon = old_last_center
            o_off_x = (clon - o_blon) * pixel_per_degree * cos_lat
            o_off_y = -(clat - o_blat) * pixel_per_degree
            o_new_size = (int(map_w * o_scale_factor), int(map_h * o_scale_factor))
            o_scaled = old_map_img.resize(o_new_size, Image.LANCZOS)
            o_left = (o_new_size[0] - map_w) / 2 + o_off_x
            o_top  = (o_new_size[1] - map_h) / 2 + o_off_y
            view_old = o_scaled.crop((o_left, o_top, o_left + map_w, o_top + map_h))
            view_img = Image.blend(view_old, view_current, blend_alpha)
        else:
            view_img = view_current

        draw = ImageDraw.Draw(view_img)
        pin_mult = PIN_SIZE_MULT.get(pin_size_key, 1.0)
        pin_radius = int(zoom * 0.7 * pin_mult)
        if pin_radius < 1: pin_radius = 1

        try:
            label_font = ImageFont.truetype("gulim.ttc", font_size)
        except:
            label_font = ImageFont.load_default()

        marker_positions = []
        visible_items = []
        for item in place_data:
            if not item.get("var") or not item["var"].get(): continue
            plon, plat = item["lon"], item["lat"]
            px, py = latlon_to_pixel(plat, plon, zoom, clat, clon, map_w, map_h)
            if not (0 <= px <= map_w and 0 <= py <= map_h): continue

            type_val = item.get("type", "A")
            hex_color = type_colors.get(type_val) or type_colors.get("색상변경", "#1A3A8F")
            border_color = hex_to_rgba(hex_color)

            draw_outline_pin(draw, px, py, pin_radius, border_color=border_color)
            marker_positions.append({
                "bbox": (px - pin_radius, py - pin_radius, px + pin_radius, py + pin_radius),
                "address": item["addr"], "name": item["name"]
            })
            visible_items.append((item, px, py, border_color))

        placed_rects = [(px-pin_radius, py-pin_radius, px+pin_radius, py+pin_radius) for _, px, py, _ in visible_items]
        label_draws = []
        pad = 15

        def label_rect(px, py, tw, th, direction, gap):
            diag = gap * 0.75
            if direction == "top": bx, by = px - tw/2, py - gap - th - pad
            elif direction == "bottom": bx, by = px - tw/2, py + gap
            elif direction == "left": bx, by = px - gap - tw - pad*2, py - th/2
            elif direction == "right": bx, by = px + gap, py - th/2
            elif direction == "top-left": bx, by = px - diag - tw - pad*2, py - diag - th - pad
            elif direction == "top-right": bx, by = px + diag, py - diag - th - pad
            elif direction == "bottom-left": bx, by = px - diag - tw - pad*2, py + diag
            else: bx, by = px + diag, py + diag
            rx1, ry1 = int(bx - pad), int(by - pad // 2.5)
            rx2, ry2 = int(bx + tw + pad), int(by + th + pad // 2.5 + 1)
            return rx1 + (rx2 - rx1 - tw) / 2, by, rx1, ry1, rx2, ry2

        def rects_overlap(a, b, margin=2):
            return not (a[2] + margin < b[0] or b[2] + margin < a[0] or a[3] + margin < b[1] or b[3] + margin < a[1])

        DIRECTIONS = ["top", "top-right", "right", "bottom-right", "bottom", "bottom-left", "left", "top-left"]
        EXTRA_OFFSETS = [(0, 0), (8, 0), (-8, 0), (0, 8), (0, -8)]

        for item, px, py, border_color in visible_items:
            name = item["name"]
            label_dir = item.get("label_dir", "top")
            gap = pin_radius + 4
            bbox = draw.textbbox((0, 0), name, font=label_font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            pref_dirs = [label_dir] + [d for d in DIRECTIONS if d != label_dir]
            placed = False
            for direction in pref_dirs:
                for ox, oy in EXTRA_OFFSETS:
                    tx, ty, rx1, ry1, rx2, ry2 = label_rect(px+ox, py+oy, tw, th, direction, gap)
                    if not any(rects_overlap((rx1, ry1, rx2, ry2), pr) for pr in placed_rects):
                        placed_rects.append((rx1, ry1, rx2, ry2)); label_draws.append((tx, ty, rx1, ry1, rx2, ry2, border_color, name, direction, tw, th, px, py))
                        placed = True; break
                if placed: break
            if not placed:
                tx, ty, rx1, ry1, rx2, ry2 = label_rect(px, py, tw, th, label_dir, gap)
                label_draws.append((tx, ty, rx1, ry1, rx2, ry2, border_color, name, label_dir, tw, th, px, py))

        n = len(label_draws); disps = [[0.0, 0.0] for _ in range(n)]; MARGIN = 3
        for _ in range(10):
            for a in range(n):
                ta = label_draws[a]; acx, acy = (ta[2]+ta[4])/2 + disps[a][0], (ta[3]+ta[5])/2 + disps[a][1]
                aw, ah = ta[4]-ta[2], ta[5]-ta[3]
                for b in range(a + 1, n):
                    tb = label_draws[b]; bcx, bcy = (tb[2]+tb[4])/2 + disps[b][0], (tb[3]+tb[5])/2 + disps[b][1]
                    bw, bh = tb[4]-tb[2], tb[5]-tb[3]
                    ov_x, ov_y = (aw + bw) / 2 + MARGIN - abs(acx - bcx), (ah + bh) / 2 + MARGIN - abs(acy - bcy)
                    if ov_x > 0 and ov_y > 0:
                        dx, dy = (acx-bcx) or 0.01, (acy-bcy) or 0.01; dist = math.sqrt(dx*dx + dy*dy)
                        disps[a][0] += dx/dist*min(ov_x,ov_y)*0.5; disps[a][1] += dy/dist*min(ov_x,ov_y)*0.5
                        disps[b][0] -= dx/dist*min(ov_x,ov_y)*0.5; disps[b][1] -= dy/dist*min(ov_x,ov_y)*0.5

        for i, ld in enumerate(label_draws):
            tx, ty, rx1, ry1, rx2, ry2, b_col, name, _, _, _, lpx, lpy = ld
            dx, dy = disps[i]; tx, rx1, rx2 = tx+dx, rx1+dx, rx2+dx; ty, ry1, ry2 = ty+dy, ry1+dy, ry2+dy
            cx, cy = max(rx1, min(rx2, lpx)), max(ry1, min(ry2, lpy))
            dist = math.sqrt((lpx-cx)**2+(lpy-cy)**2)
            if dist > pin_radius:
                draw.line([(int(lpx+(cx-lpx)*pin_radius/dist), int(lpy+(cy-lpy)*pin_radius/dist)), (int(cx), int(cy))], fill=(*b_col[:3], 200), width=2)
            draw.rounded_rectangle([rx1, ry1, rx2, ry2], radius=4, fill=(255, 255, 255, 230), outline=b_col, width=3)
            draw.text((int(tx), int(ty)), name, fill=b_col, font=label_font)

        return view_img, marker_positions
