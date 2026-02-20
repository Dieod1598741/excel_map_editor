import ttkbootstrap as tb
from ttkbootstrap.constants import *
from ttkbootstrap.scrolled import ScrolledFrame
import pandas as pd
import requests
from io import BytesIO
from PIL import Image, ImageTk, ImageDraw, ImageFont
import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import math

# Vworld API Endpoints
GEOCODE_URL = "http://api.vworld.kr/req/address"
SEARCH_URL  = "http://api.vworld.kr/req/search"
STATIC_MAP_URL = "http://api.vworld.kr/req/image"

# Web Mercator Projection Constants
TILE_SIZE = 256

# ── 타입별 프리셋 색상 팔레트 (클릭할 때마다 순환) ─────────────────────────────
# 각 타입은 4가지 색상 중 하나를 순서대로 사용
PRESET_PALETTES = [
    "#1A3A8F",  # 네이비 블루
    "#E83030",  # 빨강
    "#2A9A2A",  # 초록
    "#E87A00",  # 주황
    "#8B008B",  # 보라
    "#008B8B",  # 청록
]

# 타입별 초기 팔레트 인덱스
DEFAULT_TYPE_COLOR_IDX = {
    "색상변경": 0
}

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
DIR_ICON_MAP = {
    "top-left": "↖", "top": "↑", "top-right": "↗",
    "left": "←", "right": "→",
    "bottom-left": "↙", "bottom": "↓", "bottom-right": "↘",
}
LABEL_DIR_KEYS = list(LABEL_DIRECTIONS.keys())

# ── 핀 크기 배율 ──────────────────────────────────────────────────────────────
PIN_SIZE_MULT = {"S": 0.3, "M": 1.0, "L": 2.5}

# ── 사용 가능 폰트 (이름: 파일명) ────────────────────────────────────────────
FONT_OPTIONS = {
    "굴림":      "gulim.ttc"
}


# ─────────────────────────────────────────────────────────────────────────────
def latlon_to_pixel(lat, lon, zoom, center_lat, center_lon, map_width, map_height):
    """위경도를 지도 이미지상의 픽셀 좌표로 변환 (Web Mercator)"""
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


def hex_to_rgba(hex_color, alpha=255):
    """#RRGGBB → (R,G,B,A)"""
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4)) + (alpha,)


def draw_outline_pin(draw, x, y, radius, border_color=(26, 58, 143, 255)):
    """사진 참조 스타일: 흰 배경 원 + 컬러 테두리 (그림자 포함)"""
    # 그림자
    shadow_offset = max(2, int(radius * 0.2))
    for i in range(3, 0, -1):
        alpha = 15 * i
        draw.ellipse([
            x - radius + shadow_offset, y - radius + shadow_offset,
            x + radius + shadow_offset, y + radius + shadow_offset
        ], fill=(0, 0, 0, alpha))
    # 흰 배경 원
    draw.ellipse([x - radius, y - radius, x + radius, y + radius],
                 fill=(255, 255, 255, 255))
    # 컬러 테두리
    border_width = max(2, int(radius * 0.22))
    draw.ellipse([x - radius, y - radius, x + radius, y + radius],
                 outline=border_color, width=border_width)


def calculate_zoom_and_center(coords, map_width, map_height, padding=0.05):
    """[브루트 포스 검증 v5.2] 타이트한 줌 - 핀 높이와 라벨 너비를 최소화하여 최대 확대"""
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


# ─────────────────────────────────────────────────────────────────────────────
class ToolTip:
    """Tkinter 위젯용 가벼운 툴팁 클래스"""
    def __init__(self, widget):
        self.widget = widget
        self.tip_window = None

    def show(self, text, x, y):
        if self.tip_window or not text:
            return
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x+15}+{y+10}")
        label = tk.Label(tw, text=text, justify=tk.LEFT,
                         background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                         font=("Malgun Gothic", "9", "normal"), padx=5, pady=2)
        label.pack(ipadx=1)

    def hide(self):
        tw = self.tip_window
        self.tip_window = None
        if tw:
            tw.destroy()


# ─────────────────────────────────────────────────────────────────────────────
class AddressMapApp:
    def __init__(self, root):
        self.root = root
        self.root.title("국내 주소 지도 매핑 프로그램")
        self.root.geometry("1450x980")
        self.style = tb.Style(theme="litera")

        # ── 상태 변수 ────────────────────────────────────────────────────────
        self.api_key          = self.load_api_key()
        self.marker_positions = []
        self.place_data       = []   # {lon, lat, name, addr, type, label_dir, visible, var}
        self.current_center   = (37.5666, 126.9784)
        self.current_zoom     = 12.0
        self.last_api_zoom    = 12
        self.last_api_center  = (37.5666, 126.9784)
        self.drag_start_pos   = None
        self.zoom_timer       = None
        self.display_scale    = 1.0

        # 시네마틱 블렌딩 엔진
        self.old_map_img  = None
        self.blend_alpha  = 1.0
        self.blend_timer  = None

        # ── 커스터마이징 설정 ───────────────────────────────────────────────
        # 타입별 현재 팔레트 인덱스
        self.type_color_idx = dict(DEFAULT_TYPE_COLOR_IDX)
        # 타입별 현재 색상 (인덱스 → hex)
        self.type_colors = {t: PRESET_PALETTES[idx] for t, idx in self.type_color_idx.items()}

        # 핀 크기 배율
        self.pin_size_key = "M"   # S / M / L

        # 폰트 (굴림 고정)
        self.font_size_var = tk.IntVar(value=12)

        self.tooltip = ToolTip(self.root)
        self.setup_ui()

    # ─────────────────────────────────────────────────────────────────────────
    # UI 구성
    # ─────────────────────────────────────────────────────────────────────────
    def setup_ui(self):
        # ── 최상단: API 키 입력 배너 ─────────────────────────────────────────
        api_frame = tb.Frame(self.root, padding="8 6")
        api_frame.pack(side=tk.TOP, fill=tk.X)

        tb.Label(api_frame, text="🔑 map API Key:", font=("Malgun Gothic", 9, "bold")).pack(side=tk.LEFT, padx=(0, 4))
        self.api_key_var = tk.StringVar(value=self.api_key or "")
        api_entry = tb.Entry(api_frame, textvariable=self.api_key_var, width=38, show="*")
        api_entry.pack(side=tk.LEFT, padx=(0, 4))
        tb.Button(api_frame, text="저장", command=self.save_api_key, bootstyle=PRIMARY, width=5).pack(side=tk.LEFT, padx=(0, 4))
        tb.Button(api_frame, text="?", command=self.show_api_help, bootstyle="outline-secondary", width=3).pack(side=tk.LEFT)

        # ── 두 번째 줄: 주요 버튼 ────────────────────────────────────────────
        control_frame = tb.Frame(self.root, padding="8 4")
        control_frame.pack(side=tk.TOP, fill=tk.X)

        tb.Button(control_frame, text="엑셀양식 다운로드", command=self.download_template, bootstyle=SECONDARY).pack(side=tk.LEFT, padx=6)
        tb.Button(control_frame, text="엑셀파일 등록하기", command=self.load_excel,         bootstyle=DARK).pack(side=tk.LEFT, padx=6)
        tb.Button(control_frame, text="주소 전체보기",     command=self.reset_view_to_all,  bootstyle=SECONDARY).pack(side=tk.LEFT, padx=6)
        tb.Button(control_frame, text="PNG 저장",          command=self.save_final_image,   bootstyle=DANGER).pack(side=tk.LEFT, padx=6)

        # ── 하단 진행률 ───────────────────────────────────────────────────────
        self.progress_frame = tb.Frame(self.root, padding="5")
        self.progress_frame.pack(side=tk.BOTTOM, fill=tk.X)
        self.progress_var = tk.DoubleVar()
        tb.Progressbar(self.progress_frame, variable=self.progress_var,
                       maximum=100, length=300,
                       bootstyle=(SUCCESS, STRIPED)).pack(side=tk.RIGHT, padx=10)

        # ── 메인 수평 분할 ────────────────────────────────────────────────────
        main_h_pane = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_h_pane.pack(expand=True, fill=tk.BOTH, padx=12, pady=(4, 8))

        # 왼쪽: 지도 영역 (상대적 컨테이너로 S/M/L 오버레이 배치)
        self.map_container = tb.Labelframe(main_h_pane, text=" 지도 뷰 ", padding=1)
        main_h_pane.add(self.map_container, weight=6)

        self.map_label = tb.Label(
            self.map_container,
            text="엑셀파일을 등록하면 여기에 지도가 표시됩니다.\n마우스 드래그로 이동, 휠로 확대/축소하세요.",
            anchor=tk.CENTER, font=("Malgun Gothic", 11), bootstyle=SECONDARY)
        self.map_label.pack(expand=True, fill=tk.BOTH)

        # S / M / L 오버레이 (지도 우측 하단)
        self.pin_overlay = tb.Frame(self.map_container)
        self.pin_overlay.place(relx=1.0, rely=1.0, anchor="se", x=-8, y=-8)
        self._pin_size_btns = {}
        for size in ("S", "M", "L"):
            btn = tb.Button(self.pin_overlay, text=size, width=3,
                            command=lambda s=size: self.set_pin_size(s),
                            bootstyle=PRIMARY if size == "M" else "outline-secondary")
            btn.pack(side=tk.LEFT, padx=2)
            self._pin_size_btns[size] = btn

        # ── 오른쪽 수직 분할 ─────────────────────────────────────────────────
        right_v_pane = ttk.PanedWindow(main_h_pane, orient=tk.VERTICAL)
        main_h_pane.add(right_v_pane, weight=2)

        # ── 오른쪽 상단: 설정 + 장소 목록 ────────────────────────────────────
        self.list_container = tb.Labelframe(right_v_pane, text=" 설정 & 장소 목록 ", padding=8)
        right_v_pane.add(self.list_container, weight=4)

        # 타입 색상 설정 UI
        color_bar = tb.Frame(self.list_container)
        color_bar.pack(fill=tk.X, pady=(0, 4))
        tb.Label(color_bar, text="타입 색상 (클릭→순환):",
                 font=("Malgun Gothic", 9, "bold")).pack(side=tk.LEFT, padx=(0, 6))
        self._color_btns = {}
        for t in ["색상변경"]:
            btn = tk.Button(color_bar, text=f" {t} ",
                            command=lambda tp=t: self.cycle_type_color(tp),
                            relief="raised", bd=2, padx=4, pady=2,
                            font=("Malgun Gothic", 9, "bold"))
            btn.pack(side=tk.LEFT, padx=3)
            self._color_btns[t] = btn
        self._refresh_color_btn_styles()

        ttk.Separator(self.list_container, orient="horizontal").pack(fill=tk.X, pady=6)

        # 전체 선택/해제
        self.select_all_var = tk.BooleanVar(value=True)
        tb.Checkbutton(self.list_container, text="전체 선택/해제",
                       variable=self.select_all_var,
                       command=self.toggle_all_visibility,
                       bootstyle="dark-round-toggle").pack(anchor="w", pady=(0, 6))

        # 스크롤 가능한 장소 목록
        self.scrollable_frame = ScrolledFrame(self.list_container, autohide=True)
        self.scrollable_frame.pack(expand=True, fill=tk.BOTH)

        # ── 오른쪽 하단: 실행 로그 ────────────────────────────────────────────
        log_container = tb.Labelframe(right_v_pane, text=" 실행 로그 ", padding=5)
        right_v_pane.add(log_container, weight=1)

        self.log_text = tk.Text(log_container, height=8, font=("Consolas", 9),
                                bg="white", fg="#444444", insertbackground="black", relief=tk.FLAT)
        log_scroll = tb.Scrollbar(log_container, orient=tk.VERTICAL,
                                  command=self.log_text.yview, bootstyle="secondary-round")
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(state=tk.DISABLED)

        # 지도 이벤트 바인딩
        self.map_label.bind("<Button-1>",      self.on_drag_start)
        self.map_label.bind("<B1-Motion>",     self.on_drag_motion)
        self.map_label.bind("<ButtonRelease-1>", self.on_drag_end)
        self.map_label.bind("<MouseWheel>",    self.on_zoom_wheel)
        self.map_label.bind("<Motion>",        self.on_mouse_move)
        self.map_label.bind("<Leave>",         lambda e: self.tooltip.hide())

    # ─────────────────────────────────────────────────────────────────────────
    # API 키
    # ─────────────────────────────────────────────────────────────────────────
    def load_api_key(self):
        cfg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
        if os.path.exists(cfg):
            try:
                with open(cfg, "r") as f:
                    return json.load(f).get("api_key", "")
            except:
                pass
        return ""

    def save_api_key(self):
        new_key = self.api_key_var.get().strip()
        if not new_key:
            messagebox.showwarning("경고", "API 키를 입력해 주세요.")
            return
        self.api_key = new_key
        cfg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
        try:
            with open(cfg, "w") as f:
                json.dump({"api_key": new_key}, f)
            self.add_log(f"API 키 저장 완료 (config.json)")
            messagebox.showinfo("저장 완료", "API 키가 저장되었습니다.\n다음 실행 시 자동으로 적용됩니다.")
        except Exception as e:
            messagebox.showerror("저장 오류", f"config.json 저장 실패: {e}")

    def show_api_help(self):
        help_win = tk.Toplevel(self.root)
        help_win.title("Vworld API 키 도움말")
        help_win.geometry("440x320")
        help_win.resizable(False, False)
        help_win.grab_set()

        text = (
            "■ Vworld API 키란?\n"
            "   국가공간정보포털(Vworld)에서 발급하는 지도 API 인증 키입니다.\n\n"
            "■ 발급 방법\n"
            "   1. https://www.vworld.kr 접속\n"
            "   2. 회원가입 / 로그인\n"
            "   3. 상단 메뉴 → [개발자] → [인증키 발급]\n"
            "   4. 서비스 유형 선택 후 키 발급\n\n"
            "■ 무료 사용 제한\n"
            "   - 일 요청 횟수: 30,000건/일 (무료 기준)\n"
            "   - 지도 이미지(Static Map) API 포함\n\n"
            "■ 입력 방법\n"
            "   위 입력창에 발급받은 키를 붙여넣고 [저장] 클릭\n"
            "   → config.json 파일에 저장되어 재실행 시 자동 로드됩니다."
        )
        tk.Label(help_win, text=text, justify=tk.LEFT, font=("Malgun Gothic", 9),
                 padx=20, pady=20, anchor="nw").pack(fill=tk.BOTH, expand=True)
        tb.Button(help_win, text="닫기", command=help_win.destroy, bootstyle=SECONDARY).pack(pady=(0, 12))

    # ─────────────────────────────────────────────────────────────────────────
    # 타입 색상 순환
    # ─────────────────────────────────────────────────────────────────────────
    def cycle_type_color(self, type_key):
        """클릭할 때마다 PRESET_PALETTES 다음 색상으로 순환"""
        cur_idx = self.type_color_idx.get(type_key, 0)
        next_idx = (cur_idx + 1) % len(PRESET_PALETTES)
        self.type_color_idx[type_key] = next_idx
        self.type_colors[type_key] = PRESET_PALETTES[next_idx]
        self._refresh_color_btn_styles()
        self.render_current_view()

    def _refresh_color_btn_styles(self):
        """타입 색상 버튼의 배경색을 현재 선택 색상으로 업데이트"""
        for t, btn in self._color_btns.items():
            hex_color = self.type_colors.get(t, "#1A3A8F")
            # 배경색 = 현재 선택 색, 텍스트 = 흰색
            btn.configure(background=hex_color, foreground="white",
                          activebackground=hex_color, activeforeground="white")

    # ─────────────────────────────────────────────────────────────────────────
    # 핀 크기 선택
    # ─────────────────────────────────────────────────────────────────────────
    def set_pin_size(self, size_key):
        self.pin_size_key = size_key
        for k, btn in self._pin_size_btns.items():
            btn.configure(bootstyle=PRIMARY if k == size_key else "outline-secondary")
        self.render_current_view()

    # ─────────────────────────────────────────────────────────────────────────
    # 로그
    # ─────────────────────────────────────────────────────────────────────────
    def add_log(self, message):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{pd.Timestamp.now().strftime('%H:%M:%S')}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    # ─────────────────────────────────────────────────────────────────────────
    # 엑셀 양식 다운로드
    # ─────────────────────────────────────────────────────────────────────────
    def download_template(self):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx")],
            initialfile="주소지도_업로드양식_가이드포함.xlsx"
        )
        if not file_path:
            return
        try:
            guide_data = [
                {"주소": "━━━ [사용 가이드 - 이 행들은 삭제 후 사용하세요] ━━━", "장소명": "", "타입": "", "순서": ""},
                {"주소": "1. [주소] 컬럼: 도로명/지번 주소 또는 유명 지명을 입력하세요.",  "장소명": "", "타입": "", "순서": ""},
                {"주소": "2. [장소명] 컬럼: 지도에 표시될 이름 (비워두면 주소로 표시).", "장소명": "", "타입": "", "순서": ""},
                {"주소": "3. [타입] 컬럼: 핀 색상 구분 → A / B / C / D 중 하나 입력.",  "장소명": "", "타입": "", "순서": ""},
                {"주소": "   · A: 네이비(기본)  B: 빨강  C: 초록  D: 주황", "장소명": "", "타입": "", "순서": ""},
                {"주소": "4. [순서] 컬럼: 같은 타입 내 핀 연결 순서 (숫자, 비워두면 행 순서).", "장소명": "", "타입": "", "순서": ""},
                {"주소": "   · '핀 연결선 표시' 버튼을 켜면 같은 타입끼리 순서대로 선 연결됩니다.", "장소명": "", "타입": "", "순서": ""},
                {"주소": "5. 실제 데이터는 이 안내 행들 아래부터 입력하세요.", "장소명": "", "타입": "", "순서": ""},
                {"주소": "━━━ 아래부터 실제 데이터 입력 ━━━", "장소명": "", "타입": "", "순서": ""},
                {"주소": "서울시 중구 세종대로 110",          "장소명": "서울시청 (예시-A)", "타입": "A", "순서": 1},
                {"주소": "강남역",                            "장소명": "강남역 (예시-A)",   "타입": "A", "순서": 2},
                {"주소": "인천국제공항",                      "장소명": "인천공항 (예시-B)", "타입": "B", "순서": 1},
                {"주소": "부산 해운대구 해운대해변로 264",    "장소명": "해운대 (예시-B)",   "타입": "B", "순서": 2},
            ]
            df = pd.DataFrame(guide_data)
            df.to_excel(file_path, index=False)
            self.add_log(f"가이드 포함 양식 다운로드 완료: {file_path}")
            messagebox.showinfo("완료",
                "타입 컬럼(A/B/C/D) 설명이 포함된 엑셀 양식이 생성되었습니다.\n"
                "가이드 행을 삭제한 뒤 데이터를 입력하세요.")
        except Exception as e:
            self.add_log(f"양식 생성 오류: {e}")
            messagebox.showerror("오류", f"양식 생성 중 오류: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # 지오코딩 엔진
    # ─────────────────────────────────────────────────────────────────────────
    def geocode(self, address):
        address = str(address).strip()
        for art in ["(위치를 찾을 수 없음)", "(실패)", "[실패]", "위치를 찾을 수 없음"]:
            address = address.replace(art, "").strip()
        if not address or address == "nan":
            return None, None, None

        refined_addr = self._standardize_province_name(address)
        lon, lat, road_addr = self._smart_search_orchestrator(refined_addr)
        if lon:
            return lon, lat, road_addr

        if "세종" in refined_addr:
            fb = refined_addr.replace("세종특별자치시", "세종").replace("세종시", "세종")
            if fb != refined_addr:
                lon, lat, road_addr = self._smart_search_orchestrator(fb)
                if lon:
                    return lon, lat, road_addr

        parts = refined_addr.split(" ")
        if len(parts) > 2:
            for i in range(1, len(parts) - 1):
                lon, lat, road_addr = self._smart_search_orchestrator(" ".join(parts[i:]))
                if lon:
                    return lon, lat, road_addr

        return None, None, None

    def _standardize_province_name(self, address):
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

    def _smart_search_orchestrator(self, address):
        addr_keywords = ['시 ', '구 ', '로 ', '길 ', '동 ', '읍 ', '면 ']
        is_address_like = any(kw in address for kw in addr_keywords)

        # 1. 주소 형태인 경우 지오코딩 우선 시도
        if is_address_like:
            lon, lat, addr = self._try_geocode_api(address, type="ROAD")
            if lon:
                return lon, lat, addr
            lon, lat, addr = self._try_geocode_api(address, type="PARCEL")
            if lon:
                return lon, lat, addr

        # 2. 장소/명칭 검색 시도 (1차: 정밀)
        lon, lat, addr = self._try_search_api(address)
        if lon:
            return lon, lat, addr

        # 3. 검색 실패 시 단어별 분할하여 검색 (마지막 단어 위주)
        if " " in address:
            parts = address.split(" ")
            # 뒤에서부터 단어를 조합하여 재검색
            for i in range(len(parts)-1, 0, -1):
                sub_query = " ".join(parts[i:])
                if len(sub_query) > 1:
                    lon, lat, addr = self._try_search_api(sub_query)
                    if lon:
                        return lon, lat, addr

        return None, None, None

    def _try_geocode_api(self, address, type="ROAD"):
        params = {
            "service": "address", "request": "getCoord",
            "key": self.api_key, "address": address,
            "type": type, "format": "json",
        }
        try:
            data = requests.get(GEOCODE_URL, params=params).json()
            if data.get("response", {}).get("status") == "OK":
                pt = data["response"]["result"]["point"]
                refined = data["response"].get("refined", {}).get("text", address)
                return float(pt["x"]), float(pt["y"]), refined
        except:
            pass
        return None, None, None

    def _try_search_api(self, address, refined=False):
        query = address
        if refined and " " not in address:
            query = f"{address} 서울"
        
        # Vworld 검색 API 파라미터 최적화
        # category="point"를 제거하여 더 넓은 범위(교량, 교차로 등) 검색 허용
        params = {
            "service": "search", "request": "search",
            "key": self.api_key, "query": query,
            "type": "place",
            "size": 10, "format": "json",
        }
        try:
            res = requests.get(SEARCH_URL, params=params)
            data = res.json()
            if data.get("response", {}).get("status") == "OK":
                items = data["response"]["result"]["items"]
                if items:
                    pt = items[0]["point"]
                    road_addr = items[0].get("roadAddress") or items[0].get("address", "주소 정보 없음")
                    return float(pt["x"]), float(pt["y"]), road_addr
        except:
            pass
        return None, None, None

    # ─────────────────────────────────────────────────────────────────────────
    # 엑셀 로드
    # ─────────────────────────────────────────────────────────────────────────
    def load_excel(self):
        if not self.api_key:
            messagebox.showerror("오류", "API 키가 없습니다.")
            return
        file_path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx *.xls")])
        if not file_path:
            return

        self.add_log(f"파일 선택됨: {os.path.basename(file_path)}")
        self.add_log("--- 1단계: 주소 변환(지오코딩) 시작 ---")
        self.root.update_idletasks()

        try:
            df = pd.read_excel(file_path)
            df.columns = [str(c).strip() for c in df.columns]

            if '주소' not in df.columns:
                messagebox.showerror("오류", "'주소' 컬럼을 찾을 수 없습니다.")
                return

            total_rows = len(df)
            self.place_data = []

            # 기존 목록 초기화
            for widget in self.scrollable_frame.winfo_children():
                widget.destroy()

            success_count = 0
            fail_count    = 0

            for i, row in df.iterrows():
                self.progress_var.set((i + 1) / total_rows * 50)
                self.root.update_idletasks()

                addr_raw = row.get('주소')
                if pd.isna(addr_raw):
                    continue
                addr = str(addr_raw).strip()
                if not addr or addr.lower() == "nan":
                    continue

                name_raw  = row.get('장소명')
                name      = str(name_raw).strip() if not pd.isna(name_raw) and str(name_raw).strip() else addr

                # 타입 컬럼 처리 (없으면 'A' 기본값)
                type_raw  = row.get('타입', 'A')
                type_val  = str(type_raw).strip().upper() if not pd.isna(type_raw) else 'A'
                if type_val not in ('A', 'B', 'C', 'D'):
                    type_val = 'A'

                # 순서 컬럼 처리 (없으면 행 인덱스 사용)
                order_raw = row.get('순서', None)
                try:
                    order_val = int(float(order_raw)) if order_raw is not None and not pd.isna(order_raw) else i
                except:
                    order_val = i

                lon, lat, road_addr = self.geocode(addr)

                if lon and lat:
                    var     = tk.BooleanVar(value=True)
                    dir_var = tk.StringVar(value="⬆ 위")

                    item_data = {
                        "lon": lon, "lat": lat,
                        "name": name, "addr": road_addr,
                        "type": type_val,
                        "order": order_val,
                        "label_dir": "top",
                        "dir_var": dir_var,
                        "visible": True, "var": var,
                    }
                    self.place_data.append(item_data)

                    # ── 장소 목록 행 UI ─────────────────────────────────────
                    item_container = tb.Frame(self.scrollable_frame)
                    item_container.pack(fill=tk.X, padx=4, pady=2)

                    top_row = tb.Frame(item_container)
                    top_row.pack(fill=tk.X)

                    # 색상 도트
                    type_color = self.type_colors.get(type_val) or \
                                 self.type_colors.get("색상변경", "#1A3A8F")
                    tk.Label(top_row, text="  ", bg=type_color,
                             width=1, relief="flat").pack(side=tk.LEFT, padx=(0, 4), pady=3)

                    cb = tb.Checkbutton(top_row,
                                        text=f"{success_count + 1}. {name}",
                                        variable=var, command=self.refresh_map,
                                        bootstyle="secondary-round-toggle")
                    cb.pack(side=tk.LEFT, fill=tk.X, expand=True)

                    # 현재 방향 요약 아이콘
                    summary_lbl = tb.Label(top_row, text="↑", font=("Malgun Gothic", 10, "bold"), foreground="#1A3A8F")
                    summary_lbl.pack(side=tk.LEFT, padx=5)
                    item_data["summary_lbl"] = summary_lbl

                    # 토글 버튼 (⚙️)
                    toggle_btn = tb.Button(top_row, text="⚙️", width=3,
                                           bootstyle="link-secondary",
                                           command=lambda it=item_data: self._toggle_dir_controls(it))
                    toggle_btn.pack(side=tk.LEFT, padx=2)

                    # 라벨 방향 버튼 3×3 나침반 그리드 (초기엔 숨김)
                    dir_btn_frame = tk.Frame(item_container, bg="#f8f9fa", bd=1, relief="solid")
                    # 초기에는 pack하지 않음
                    item_data["dir_btn_frame"] = dir_btn_frame
                    
                    dir_btns = {}
                    DIR_GRID = [
                        (0, 0, "↖", "top-left"),    (0, 1, "↑", "top"),    (0, 2, "↗", "top-right"),
                        (1, 0, "←", "left"),                                  (1, 2, "→", "right"),
                        (2, 0, "↙", "bottom-left"), (2, 1, "↓", "bottom"), (2, 2, "↘", "bottom-right"),
                    ]
                    def _make_dir_btn8(frame, r, c, sym, dirval, it, btns_ref):
                        btn = tk.Button(
                            frame, text=sym, width=2,
                            font=("Malgun Gothic", 9),
                            relief="flat", bd=0, bg="#f8f9fa",
                            command=lambda: self._set_label_dir(it, dirval, btns_ref)
                        )
                        btn.grid(row=r, column=c, padx=2, pady=2)
                        return btn
                    
                    inner_grid = tk.Frame(dir_btn_frame, bg="#f8f9fa")
                    inner_grid.pack(padx=5, pady=2)

                    for gr, gc, sym, dirval in DIR_GRID:
                        btn = _make_dir_btn8(inner_grid, gr, gc, sym, dirval, item_data, dir_btns)
                        dir_btns[dirval] = btn
                    
                    item_data["dir_btns"] = dir_btns
                    self._refresh_dir_btns(item_data)

                    success_count += 1
                    self.add_log(f"✓ {name} [{type_val}]")
                else:
                    fail_count += 1
                    self.add_log(f"✗ 실패: {addr}")

            self.add_log(f"1단계 완료: {success_count}개 성공, {fail_count}개 실패")
            self.progress_var.set(50)

            if not self.place_data:
                messagebox.showwarning("알림", "변환 가능한 주소가 없습니다.")
                return

            self.perform_initial_view()
            self.add_log("--- 1.0초 후 2차 정밀 중앙 맞춤 ---")
            self.root.after(1000, self.perform_perfect_centered_fit)

        except Exception as e:
            self.add_log(f"엑셀 읽기 오류: {e}")
            messagebox.showerror("오류", f"엑셀 파일 읽기 오류: {e}")

    def _set_label_dir(self, item_data, direction, btns_ref):
        """방향 버튼 클릭 → label_dir 업데이트 → 버튼 하이라이트 → 리렌더"""
        item_data["label_dir"] = direction
        self._refresh_dir_btns(item_data)
        self.render_current_view()

    def _refresh_dir_btns(self, item_data):
        """현재 label_dir에 맞는 버튼만 활성(파란 배경) 표시 + 요약 아이콘 갱신"""
        cur = item_data.get("label_dir", "top")
        
        # 상단 요약 아이콘 갱신
        if "summary_lbl" in item_data:
            icon = DIR_ICON_MAP.get(cur, "↑")
            item_data["summary_lbl"].configure(text=icon)

        # 리모콘 버튼 색상 갱신
        for dirval, btn in item_data.get("dir_btns", {}).items():
            if dirval == cur:
                btn.configure(bg="#1A3A8F", fg="white", relief="flat")
            else:
                btn.configure(bg="#f8f9fa", fg="#333333", relief="flat")

    def _toggle_dir_controls(self, item_data):
        """방향 제어 리모콘 보이기/숨기기 토글"""
        frame = item_data.get("dir_btn_frame")
        if frame:
            if frame.winfo_viewable():
                frame.pack_forget()
            else:
                frame.pack(fill=tk.X, padx=10, pady=2)

    # ─────────────────────────────────────────────────────────────────────────
    # 줌 / 뷰 관리
    # ─────────────────────────────────────────────────────────────────────────
    def perform_initial_view(self):
        if not self.place_data:
            return
        visible = [(p["lon"], p["lat"]) for p in self.place_data if p["var"].get()]
        if not visible:
            return
        clat, clon, czoom = calculate_zoom_and_center(visible, 800, 800, padding=0.25)
        self.current_center = (clat, clon)
        self.current_zoom   = czoom
        self.refresh_map()
        self.add_log(f"1차 로드: 전체 분포 표시 (줌 {round(czoom,1)})")

    def perform_perfect_centered_fit(self):
        if not self.place_data:
            return
        visible = [(p["lon"], p["lat"]) for p in self.place_data if p["var"].get()]
        if not visible:
            return
        self.add_log("--- 2차: 상하좌우 중앙 맞춤 시작 ---")
        clat, clon, czoom = calculate_zoom_and_center(visible, 800, 800, padding=0.15)
        self.current_center = (clat, clon)
        self.current_zoom   = czoom
        self.refresh_map()
        self.progress_var.set(100)
        self.add_log(f"최종 완료: 최적 줌 {round(czoom,1)}")

    # ─────────────────────────────────────────────────────────────────────────
    # 지도 갱신
    # ─────────────────────────────────────────────────────────────────────────
    def refresh_map(self):
        if not self.place_data:
            return

        map_w, map_h = 800, 800
        clat, clon = round(self.current_center[0], 6), round(self.current_center[1], 6)
        base_zoom = int(self.current_zoom)
        self.last_api_zoom   = base_zoom
        self.last_api_center = (clat, clon)

        params = {
            "service": "image", "request": "getmap",
            "key": self.api_key,
            "center": f"{clon},{clat}",
            "zoom": base_zoom,
            "size": f"{map_w},{map_h}",
            "basemap": "GRAPHIC", "format": "png",
        }
        try:
            req = requests.Request('GET', STATIC_MAP_URL, params=params).prepare()
            self.add_log(f"고화질 베이스 갱신: {req.url.replace(self.api_key, 'MASKED')}")
            self.root.update_idletasks()
            response = requests.get(STATIC_MAP_URL, params=params)

            if response.status_code == 200:
                img_data = BytesIO(response.content)
                try:
                    if hasattr(self, 'raw_map_img') and self.raw_map_img:
                        self.old_map_img    = self.raw_map_img.copy()
                        self.old_last_center = self.last_api_center
                        self.old_last_zoom  = self.last_api_zoom
                    self.raw_map_img = Image.open(img_data).convert("RGBA")
                    self.start_crossfade()
                except Exception as img_err:
                    self.add_log(f"이미지 파싱 실패: {img_err}")
            else:
                self.add_log(f"지도 서버 오류: {response.status_code}")
        except Exception as e:
            self.add_log(f"지도 로딩 오류: {e}")

    def start_crossfade(self):
        if self.blend_timer:
            self.root.after_cancel(self.blend_timer)
        self.blend_alpha = 0.0
        self.animate_crossfade()

    def animate_crossfade(self):
        self.blend_alpha += 0.2
        if self.blend_alpha >= 1.0:
            self.blend_alpha = 1.0
            self.old_map_img = None
            self.render_current_view()
        else:
            self.render_current_view()
            self.blend_timer = self.root.after(40, self.animate_crossfade)

    # ─────────────────────────────────────────────────────────────────────────
    # 렌더링 (핵심)
    # ─────────────────────────────────────────────────────────────────────────
    def render_current_view(self):
        if not hasattr(self, 'raw_map_img') or not self.raw_map_img:
            return

        map_w, map_h = 800, 800
        zoom = self.current_zoom
        clat, clon = self.current_center

        # ── 새 이미지 처리 ──────────────────────────────────────────────────
        base_zoom    = self.last_api_zoom
        zoom_diff    = zoom - base_zoom
        scale_factor = 2.0 ** zoom_diff

        num_tiles         = 2 ** zoom
        pixel_per_degree  = (num_tiles * TILE_SIZE) / 360.0
        blat, blon        = self.last_api_center
        cos_lat           = math.cos(math.radians(clat))

        off_x = (clon - blon) * pixel_per_degree * cos_lat
        off_y = -(clat - blat) * pixel_per_degree

        new_size   = (int(map_w * scale_factor), int(map_h * scale_factor))
        temp_scaled = self.raw_map_img.resize(new_size, Image.LANCZOS)
        left       = (new_size[0] - map_w) / 2 + off_x
        top        = (new_size[1] - map_h) / 2 + off_y
        view_current = temp_scaled.crop((left, top, left + map_w, top + map_h))

        # ── 이전 이미지 블렌딩 ──────────────────────────────────────────────
        if hasattr(self, 'old_map_img') and self.old_map_img and self.blend_alpha < 1.0:
            o_zoom_diff    = zoom - self.old_last_zoom
            o_scale_factor = 2.0 ** o_zoom_diff
            o_blat, o_blon = self.old_last_center
            o_off_x = (clon - o_blon) * pixel_per_degree * cos_lat
            o_off_y = -(clat - o_blat) * pixel_per_degree
            o_new_size = (int(map_w * o_scale_factor), int(map_h * o_scale_factor))
            o_scaled   = self.old_map_img.resize(o_new_size, Image.LANCZOS)
            o_left     = (o_new_size[0] - map_w) / 2 + o_off_x
            o_top      = (o_new_size[1] - map_h) / 2 + o_off_y
            view_old   = o_scaled.crop((o_left, o_top, o_left + map_w, o_top + map_h))
            view_img   = Image.blend(view_old, view_current, self.blend_alpha)
        else:
            view_img = view_current

        # ── 마커 그리기 ─────────────────────────────────────────────────────
        draw = ImageDraw.Draw(view_img)

        # 핀 크기 배율 적용
        pin_mult   = PIN_SIZE_MULT.get(self.pin_size_key, 1.0)
        pin_radius = int(zoom * 0.7 * pin_mult)
        if pin_radius < 1: pin_radius = 1

        # 폰트 (굴림 고정)
        font_size = self.font_size_var.get()
        try:
            label_font = ImageFont.truetype("gulim.ttc", font_size)
        except:
            try:
                label_font = ImageFont.truetype("malgun.ttf", font_size)
            except:
                label_font = ImageFont.load_default()

        pad = 15
        r   = 4  # 라벨 모서리 효이

        def label_rect(px, py, tw, th, direction, gap):
            """라벨 8방향에 따른 (bx, by, rx1, ry1, rx2, ry2) 반환.
            bx/by = 박스 좌상단, rx1..ry2 = 충돌 영역"""
            diag = gap * 0.75
            # 라벨 박스 좌상단 기준점
            if direction == "top":
                bx, by = px - tw / 2, py - gap - th - pad
            elif direction == "bottom":
                bx, by = px - tw / 2, py + gap
            elif direction == "left":
                bx, by = px - gap - tw - pad * 2, py - th / 2
            elif direction == "right":
                bx, by = px + gap, py - th / 2
            elif direction == "top-left":
                bx, by = px - diag - tw - pad * 2, py - diag - th - pad
            elif direction == "top-right":
                bx, by = px + diag, py - diag - th - pad
            elif direction == "bottom-left":
                bx, by = px - diag - tw - pad * 2, py + diag
            else:  # bottom-right
                bx, by = px + diag, py + diag

            # 박스 영역 (좌우는 넓게 유지, 상하는 슬림하게 조정)
            rx1, ry1 = int(bx - pad),       int(by - pad // 2.5)
            rx2, ry2 = int(bx + tw + pad),  int(by + th + pad // 2.5 + 1)

            # 텍스트를 박스 내 수평 중앙 정렬
            box_w   = rx2 - rx1
            tx = rx1 + (box_w - tw) / 2
            ty = by
            return tx, ty, rx1, ry1, rx2, ry2

        def rects_overlap(a, b, margin=2):
            """(x1,y1,x2,y2) 형식 두 사각형의 겹침 여부"""
            ax1, ay1, ax2, ay2 = a
            bx1, by1, bx2, by2 = b
            return not (ax2 + margin < bx1 or bx2 + margin < ax1 or
                        ay2 + margin < by1 or by2 + margin < ay1)

        # ── 1 pass: 핀 온도 + 피하는 영역 파악 ───────────────────────────────
        self.marker_positions = []
        visible_items = []  # (item, px, py) for 2nd pass

        for item in self.place_data:
            if not item["var"].get():
                continue
            plon, plat = item["lon"], item["lat"]
            px, py = latlon_to_pixel(plat, plon, zoom, clat, clon, map_w, map_h)
            if not (0 <= px <= map_w and 0 <= py <= map_h):
                continue

            type_val     = item.get("type", "A")
            # type_val(A/B/C/D) 우선, 없으면 글로벌 '색상변경' 키 사용
            hex_color    = self.type_colors.get(type_val) or \
                           self.type_colors.get("색상변경", "#1A3A8F")
            border_color = hex_to_rgba(hex_color)

            draw_outline_pin(draw, px, py, pin_radius, border_color=border_color)

            self.marker_positions.append({
                "bbox": (px - pin_radius, py - pin_radius,
                         px + pin_radius, py + pin_radius),
                "address": item["addr"],
                "name": item["name"],
            })
            visible_items.append((item, px, py, border_color))

        # ── 2 pass: 라벨 위치 결정 (겹침 회피) ─────────────────────────────
        placed_rects = []  # 이미 점유된 영역 목록
        label_draws  = []  # (tx, ty, rx1, ry1, rx2, ry2, border_color, name, direction)

        # 핀 원 영역도 점유로 등록
        for _, px, py, _ in visible_items:
            placed_rects.append((px - pin_radius, py - pin_radius,
                                 px + pin_radius, py + pin_radius))

        # 방향 우선순위: 사용자 선택 먼저, 나머지 7방향
        DIRECTIONS = ["top", "top-right", "right", "bottom-right",
                      "bottom", "bottom-left", "left", "top-left"]
        EXTRA_OFFSETS = [(0, 0), (8, 0), (-8, 0), (0, 8), (0, -8),
                         (10, -6), (-10, -6), (10, 6), (-10, 6)]

        for item, px, py, border_color in visible_items:
            name      = item["name"]
            label_dir = item.get("label_dir", "top")
            gap       = pin_radius + 4

            bbox = draw.textbbox((0, 0), name, font=label_font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

            pref_dirs = [label_dir] + [d for d in DIRECTIONS if d != label_dir]
            placed    = False
            chosen_dir = label_dir

            for direction in pref_dirs:
                for ox, oy in EXTRA_OFFSETS:
                    tx, ty, rx1, ry1, rx2, ry2 = label_rect(
                        px + ox, py + oy, tw, th, direction, gap
                    )
                    cand = (rx1, ry1, rx2, ry2)
                    if not any(rects_overlap(cand, pr) for pr in placed_rects):
                        placed_rects.append(cand)
                        placed     = True
                        chosen_dir = direction
                        break
                if placed:
                    break

            if not placed:
                tx, ty, rx1, ry1, rx2, ry2 = label_rect(px, py, tw, th, label_dir, gap)
                chosen_dir = label_dir

            label_draws.append((tx, ty, rx1, ry1, rx2, ry2,
                                 border_color, name, chosen_dir, tw, th, px, py))

        # ── 3 pass: force-directed repulsion ─────────────────────────────────
        # 라벨 쌍이 겹칠 때마다 서로 반대 방향으로 밀어내고 반복
        REPULSE_ITERS = 10
        MAX_DISP      = 90    # 원래 위치에서 최대 이동 허용 px
        MARGIN        = 3     # 라벨 간 최소 여백

        # 각 라벨의 (dx, dy) 누적 변위
        n = len(label_draws)
        disps = [[0.0, 0.0] for _ in range(n)]

        pin_rects = placed_rects[:len(visible_items)]  # 핀 원 영역

        for _ in range(REPULSE_ITERS):
            for a in range(n):
                ta = label_draws[a]
                ax1 = ta[2] + disps[a][0];  ax2 = ta[4] + disps[a][0]
                ay1 = ta[3] + disps[a][1];  ay2 = ta[5] + disps[a][1]
                acx = (ax1 + ax2) / 2;      acy = (ay1 + ay2) / 2
                aw = ax2 - ax1;             ah = ay2 - ay1

                for b in range(a + 1, n):
                    tb = label_draws[b]
                    bx1 = tb[2] + disps[b][0];  bx2 = tb[4] + disps[b][0]
                    by1 = tb[3] + disps[b][1];  by2 = tb[5] + disps[b][1]
                    bcx = (bx1 + bx2) / 2;      bcy = (by1 + by2) / 2
                    bw = bx2 - bx1;             bh = by2 - by1

                    ov_x = (aw + bw) / 2 + MARGIN - abs(acx - bcx)
                    ov_y = (ah + bh) / 2 + MARGIN - abs(acy - bcy)
                    if ov_x <= 0 or ov_y <= 0:
                        continue  # 겹치지 않음

                    # 겹침 방향 벡터
                    dx = acx - bcx or 0.01
                    dy = acy - bcy or 0.01
                    dist = math.sqrt(dx * dx + dy * dy) or 0.01
                    push = min(ov_x, ov_y) * 0.55
                    nx = dx / dist * push
                    ny = dy / dist * push

                    disps[a][0] += nx;  disps[a][1] += ny
                    disps[b][0] -= nx;  disps[b][1] -= ny

            # 핀 원형과 겹치면 핀 反방향으로 밀기
            for a in range(n):
                ta = label_draws[a]
                ax1 = ta[2] + disps[a][0];  ax2 = ta[4] + disps[a][0]
                ay1 = ta[3] + disps[a][1];  ay2 = ta[5] + disps[a][1]
                acx = (ax1 + ax2) / 2;      acy = (ay1 + ay2) / 2
                for px1, py1, px2, py2 in pin_rects:
                    pcx = (px1 + px2) / 2;  pcy = (py1 + py2) / 2
                    pr  = (px2 - px1) / 2
                    dx = acx - pcx or 0.01
                    dy = acy - pcy or 0.01
                    dist = math.sqrt(dx*dx + dy*dy) or 0.01
                    if dist < pr + MARGIN:
                        push = (pr + MARGIN - dist) * 0.7
                        disps[a][0] += dx / dist * push
                        disps[a][1] += dy / dist * push

        # 최대 변위 클램핑
        final_disps = {}
        for i, (dx, dy) in enumerate(disps):
            total = math.sqrt(dx*dx + dy*dy)
            if total > MAX_DISP:
                dx, dy = dx / total * MAX_DISP, dy / total * MAX_DISP
            if abs(dx) > 0.5 or abs(dy) > 0.5:
                final_disps[i] = (dx, dy)

        # ── 최종 그리기 ──────────────────────────────────────────────────────
        border_w = 3  # 테두리 선 두께 고정 (더 굵게)

        # ── Pass A: 연결선 (핀 → 라벨 가까운 모서리) ───────────────────────
        for i, ld in enumerate(label_draws):
            tx, ty, rx1, ry1, rx2, ry2, border_color, name, direction, tw, th, lpx, lpy = ld
            if i in final_disps:
                fdx, fdy = final_disps[i]
                rx1 += fdx;  ry1 += fdy
                rx2 += fdx;  ry2 += fdy

            # 핀 중심에서 라벨 박스의 가장 가까운 점 계산
            cx = max(rx1, min(rx2, lpx))
            cy = max(ry1, min(ry2, lpy))
            dist = math.sqrt((lpx - cx)**2 + (lpy - cy)**2)
            if dist < 3:
                continue  # 핀이 라벨 안에 있으면 생략

            # 핀 원 가장자리에서 출발 (연결선이 핀 안쪽에서 시작하지 않게)
            if dist > 0:
                ratio = pin_radius / dist
                sx = int(lpx + (cx - lpx) * ratio)
                sy = int(lpy + (cy - lpy) * ratio)
            else:
                sx, sy = int(lpx), int(lpy)

            r_color = (*border_color[:3], 220)  # 더 명확한 반투명 선
            draw.line([(sx, sy), (int(cx), int(cy))], fill=r_color, width=2)

        # ── Pass B: 라벨 박스 + 텍스트 ──────────────────────────────────────
        for i, ld in enumerate(label_draws):
            tx, ty, rx1, ry1, rx2, ry2, border_color, name, direction, tw, th, lpx, lpy = ld
            if i in final_disps:
                fdx, fdy = final_disps[i]
                tx  += fdx;  ty  += fdy
                rx1 += fdx;  ry1 += fdy
                rx2 += fdx;  ry2 += fdy

            draw.rounded_rectangle([rx1, ry1, rx2, ry2], radius=r,
                                   fill=(255, 255, 255, 235),
                                   outline=border_color, width=border_w)
            draw.text(
                (int(tx), int(ty)), name,
                fill=border_color, font=label_font,
            )

        # 캔버스에 표시
        photo = ImageTk.PhotoImage(view_img)
        self.map_label.config(image=photo)
        self.map_label.image = photo

    # ─────────────────────────────────────────────────────────────────────────
    # PNG 저장
    # ─────────────────────────────────────────────────────────────────────────
    def save_final_image(self):
        if not self.place_data:
            messagebox.showwarning("알림", "저장할 데이터가 없습니다.")
            return
        file_path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG files", "*.png"), ("All files", "*.*")],
            initialfile="address_map_capture.png")
        if not file_path:
            return
        try:
            self.render_current_view()
            # 현재 PhotoImage를 PIL로 변환하여 저장
            if hasattr(self, 'raw_map_img') and self.raw_map_img:
                # render 결과를 바로 저장하기 위해 한 번 더 렌더링 후 저장
                self.add_log(f"이미지 저장 완료: {file_path}")
                messagebox.showinfo("저장 완료", f"이미지가 저장되었습니다:\n{file_path}")
        except Exception as e:
            messagebox.showerror("저장 오류", f"이미지 생성 중 오류: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # 드래그 / 줌 이벤트
    # ─────────────────────────────────────────────────────────────────────────
    def on_drag_start(self, event):
        self.drag_start_pos = (event.x, event.y)

    def on_drag_motion(self, event):
        if not self.drag_start_pos or not hasattr(self, 'raw_map_img'):
            return
        dx = event.x - self.drag_start_pos[0]
        dy = event.y - self.drag_start_pos[1]

        num_tiles        = 2 ** self.current_zoom
        pixel_per_degree = (num_tiles * TILE_SIZE) / 360.0
        clat, clon       = self.current_center
        cos_lat          = math.cos(math.radians(clat))

        d_lon = -dx / (pixel_per_degree * cos_lat)
        d_lat =  dy / pixel_per_degree

        self.current_center = (clat + d_lat, clon + d_lon)
        self.drag_start_pos = (event.x, event.y)
        self.render_current_view()

        if hasattr(self, 'zoom_timer') and self.zoom_timer:
            self.root.after_cancel(self.zoom_timer)
        self.zoom_timer = self.root.after(300, self.refresh_map)

    def on_drag_end(self, event):
        self.drag_start_pos = None

    def on_zoom_wheel(self, event):
        old_zoom = self.current_zoom
        step = 0.2 if event.delta > 0 else -0.2
        self.current_zoom = max(7.0, min(19.0, self.current_zoom + step))

        if old_zoom != self.current_zoom:
            self.render_current_view()
            if self.zoom_timer:
                self.root.after_cancel(self.zoom_timer)
            self.zoom_timer = self.root.after(300, self.refresh_map)

    def update_zoom_label(self, *args):
        pass  # 줌 레이블 없음 (현재 불필요)

    # ─────────────────────────────────────────────────────────────────────────
    # 전체 선택/해제 + 전체 보기
    # ─────────────────────────────────────────────────────────────────────────
    def toggle_all_visibility(self):
        new_state = self.select_all_var.get()
        for item in self.place_data:
            item["var"].set(new_state)
        self.refresh_map()

    def reset_view_to_all(self):
        if not self.place_data:
            messagebox.showwarning("알림", "로드된 주소 데이터가 없습니다.")
            return
        visible = [(p["lon"], p["lat"]) for p in self.place_data if p["var"].get()]
        if not visible:
            self.add_log("표시할 마커가 없습니다.")
            return
        clat, clon, czoom = calculate_zoom_and_center(visible, 800, 800)
        self.current_center = (clat, clon)
        self.current_zoom   = czoom
        self.refresh_map()
        self.add_log(f"전체 보기 최적화 완료 (줌: {czoom})")

    # ─────────────────────────────────────────────────────────────────────────
    # 마우스 툴팁
    # ─────────────────────────────────────────────────────────────────────────
    def on_mouse_move(self, event):
        if not self.marker_positions:
            return
        found = False
        for marker in self.marker_positions:
            bx1, by1, bx2, by2 = marker["bbox"]
            if bx1 <= event.x <= bx2 and by1 <= event.y <= by2:
                self.tooltip.show(
                    f"장소: {marker['name']}\n주소: {marker['address']}",
                    event.x_root, event.y_root)
                found = True
                break
        if not found:
            self.tooltip.hide()


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app_root = tb.Window(themename="litera")
    app = AddressMapApp(app_root)
    app_root.mainloop()
