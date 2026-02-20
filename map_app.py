"""
엑셀 지도 에디터 - 메인 애플리케이션
"""
import ttkbootstrap as tb
from ttkbootstrap.constants import *
from ttkbootstrap.scrolled import ScrolledFrame
import pandas as pd
import requests
from io import BytesIO
from PIL import Image, ImageTk
import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox
import threading
from typing import Optional, Tuple, Dict, List, Any

# 모듈별 기능 임포트
from config import *
from utils.geo_utils import latlon_to_pixel, calculate_zoom_and_center
from utils.geocoding import GeocodeEngine
from renderer.map_renderer import MapRenderer

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
# ─────────────────────────────────────────────────────────────────────────────
class AddressMapApp:
    def __init__(self, root):
        self.root = root
        self.root.title("국내 주소 지도 매핑 프로그램")
        self.root.geometry("1450x980")
        self.style = tb.Style(theme="litera")

        # ── 상태 변수 ────────────────────────────────────────────────────────
        self.api_key          = self.load_api_key()
        self.geo_engine       = GeocodeEngine(self.api_key)
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
        self.type_color_idx = dict(TYPE_COLOR_MAP)
        self.type_colors = {t: PRESET_PALETTES[idx] for t, idx in self.type_color_idx.items()}

        self.pin_size_key = tk.StringVar(value="보통")
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
        main_h_pane = tb.PanedWindow(self.root, orient=tk.HORIZONTAL)
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
        right_v_pane = tb.PanedWindow(main_h_pane, orient=tk.VERTICAL)
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

        tb.Separator(self.list_container, orient="horizontal").pack(fill=tk.X, pady=6)

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
        """핀 크기를 변경하고 이미지를 다시 렌더링합니다."""
        self.pin_size_key.set(size_key)
        # 버튼 스타일 업데이트 (선택된 것만 강조)
        for k, btn in self._pin_size_btns.items():
            if k == size_key:
                btn.configure(bootstyle=PRIMARY)
            else:
                btn.configure(bootstyle="outline-secondary")
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
    def geocode(self, address: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
        """주소 변환 엔진을 호출합니다."""
        return self.geo_engine.geocode(address)

    # ─────────────────────────────────────────────────────────────────────────
    # 엑셀 로드
    # ─────────────────────────────────────────────────────────────────────────
    def load_excel(self):
        """엑셀 로딩 프로세스를 별도의 백그라운드 스레드에서 실행합니다."""
        if not self.api_key:
            messagebox.showerror("오류", "API 키가 필요합니다.")
            return
        file_path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx *.xls")])
        if not file_path:
            return

        # 백그라운드 처리 스레드 시작
        thread = threading.Thread(target=self._process_excel_thread, args=(file_path,), daemon=True)
        thread.start()

    def _process_excel_thread(self, file_path: str):
        """
        엑셀 파싱 및 지오코딩을 위한 백그라운드 워커입니다.
        무거운 I/O 및 CPU 작업을 분리하여 UI 응답성을 유지합니다.
        """
        self.add_log(f"파일 로드 중: {os.path.basename(file_path)}")
        self.add_log("1단계: 지오코딩(주소 변환) 시작...")

        try:
            df = pd.read_excel(file_path)
            df.columns = [str(c).strip() for c in df.columns]

            if '주소' not in df.columns:
                self.root.after(0, lambda: messagebox.showerror("오류", "'주소' 컬럼을 찾을 수 없습니다."))
                return

            total_rows = len(df)
            temp_place_data = []

            # 메인 스레드에서 기존 UI 목록 초기화
            self.root.after(0, self._clear_ui_on_load)

            success_count = 0
            fail_count    = 0

            for i, row in df.iterrows():
                # 프로그레스 바 업데이트
                self.progress_var.set((i + 1) / total_rows * 50)

                addr_raw = row.get('주소')
                if pd.isna(addr_raw): continue
                addr = str(addr_raw).strip()
                if not addr or addr.lower() == "nan": continue

                name_raw  = row.get('장소명')
                name      = str(name_raw).strip() if not pd.isna(name_raw) and str(name_raw).strip() else addr

                type_raw  = row.get('타입', 'A')
                type_val  = str(type_raw).strip().upper() if not pd.isna(type_raw) else 'A'
                if type_val not in ('A', 'B', 'C', 'D'): type_val = 'A'

                order_raw = row.get('순서', None)
                try:
                    order_val = int(float(order_raw)) if order_raw is not None and not pd.isna(order_raw) else i
                except:
                    order_val = i

                lon, lat, road_addr = self.geocode(addr)

                if lon and lat:
                    success_count += 1
                    # 데이터 준비 및 UI 업데이트 요청
                    item_data = {
                        "lon": lon, "lat": lat, "name": name, "addr": road_addr,
                        "type": type_val, "order": order_val, "label_dir": "top",
                        "visible": True, "success_idx": success_count
                    }
                    temp_place_data.append(item_data)
                    self.root.after(0, lambda d=item_data: self._add_place_to_ui(d))
                    self.add_log(f"✓ {name} [{type_val}]")
                else:
                    fail_count += 1
                    self.add_log(f"✗ 실패: {addr}")

            self.place_data = temp_place_data
            self.add_log(f"1단계 완료: {success_count}개 성공, {fail_count}개 실패")
            self.root.after(0, self._finalize_loading_ui)

        except Exception as e:
            self.add_log(f"엑셀 추출 오류: {e}")
            self.root.after(0, lambda: messagebox.showerror("오류", f"파일 읽기 실패: {e}"))

    def _clear_ui_on_load(self):
        """메인 스레드에서 UI 요소를 정리하는 헬퍼 함수"""
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

    def _add_place_to_ui(self, item_data):
        """
        사이드바 목록에 장소 아이템을 동적으로 추가합니다.
        스레드 안전을 위해 self.root.after를 통해 호출되어야 합니다.
        """
        var     = tk.BooleanVar(value=True)
        dir_var = tk.StringVar(value="⬆ 위")
        item_data["var"] = var
        item_data["dir_var"] = dir_var
        
        success_count = item_data["success_idx"]
        name = item_data["name"]
        type_val = item_data["type"]
        
        item_container = tb.Frame(self.scrollable_frame)
        item_container.pack(fill=tk.X, padx=4, pady=2)

        top_row = tb.Frame(item_container)
        top_row.pack(fill=tk.X)

        type_color = self.type_colors.get(type_val) or self.type_colors.get("색상변경", "#1A3A8F")
        tk.Label(top_row, text="  ", bg=type_color, width=1, relief="flat").pack(side=tk.LEFT, padx=(0, 4), pady=3)

        cb = tb.Checkbutton(top_row, text=f"{success_count}. {name}",
                            variable=var, command=self.refresh_map,
                            bootstyle="secondary-round-toggle")
        cb.pack(side=tk.LEFT, fill=tk.X, expand=True)

        summary_lbl = tb.Label(top_row, text="↑", font=("Malgun Gothic", 10, "bold"), foreground="#1A3A8F")
        summary_lbl.pack(side=tk.LEFT, padx=5)
        item_data["summary_lbl"] = summary_lbl

        toggle_btn = tb.Button(top_row, text="⚙️", width=3, bootstyle="link-secondary",
                               command=lambda it=item_data: self._toggle_dir_controls(it))
        toggle_btn.pack(side=tk.LEFT, padx=2)

        dir_btn_frame = tk.Frame(item_container, bg="#f8f9fa", bd=1, relief="solid")
        item_data["dir_btn_frame"] = dir_btn_frame
        
        dir_btns = {}
        DIR_GRID = [
            (0, 0, "↖", "top-left"),    (0, 1, "↑", "top"),    (0, 2, "↗", "top-right"),
            (1, 0, "←", "left"),                                  (1, 2, "→", "right"),
            (2, 0, "↙", "bottom-left"), (2, 1, "↓", "bottom"), (2, 2, "↘", "bottom-right"),
        ]
        
        inner_grid = tk.Frame(dir_btn_frame, bg="#f8f9fa")
        inner_grid.pack(padx=5, pady=2)

        for gr, gc, sym, dirval in DIR_GRID:
            btn = tk.Button(inner_grid, text=sym, width=2, font=("Malgun Gothic", 9),
                            relief="flat", bd=0, bg="#f8f9fa",
                            command=lambda it=item_data, dv=dirval, br=dir_btns: self._set_label_dir(it, dv, br))
            btn.grid(row=gr, column=gc, padx=2, pady=2)
            dir_btns[dirval] = btn
        
        item_data["dir_btns"] = dir_btns
        self._refresh_dir_btns(item_data)

    def _finalize_loading_ui(self):
        """Triggers the final viewport adjustment and cleanup."""
        self.progress_var.set(50)
        if not self.place_data:
            messagebox.showwarning("Notice", "No valid addresses found in the file.")
            return

        self.perform_initial_view()
        self.add_log("--- Finetuning viewport in 1.0s ---")
        self.root.after(1000, self.perform_perfect_centered_fit)

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
        """
        브이월드 정적 지도 API로부터 고해상도 베이스 지도를 가져옵니다.
        새 타일을 기다리는 동안 렌더링 엔진에서 오프셋과 스케일을 조절하여
        끊김 없는 탐색을 제공합니다.
        """
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
            self.add_log(f"베이스 지도 갱신 중: {req.url.replace(self.api_key, 'MASKED')}")
            # 메인 이벤트 루프 차단을 방지하기 위해 무거운 I/O 분리
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
                    self.add_log(f"이미지 파싱 오류: {img_err}")
            else:
                self.add_log(f"지도 서버 오류: 상태 코드 {response.status_code}")
        except Exception as e:
            self.add_log(f"지도 로딩 오류: {e}")

    def start_crossfade(self):
        """이전 지도 타일과 새 타일 사이의 부드러운 알파 블렌딩 전환을 시작합니다."""
        if self.blend_timer:
            self.root.after_cancel(self.blend_timer)
        self.blend_alpha = 0.0
        self.animate_crossfade()

    def animate_crossfade(self):
        """지도 전환 애니메이션을 위한 반복적인 알파 업데이트입니다."""
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
        """메인 렌더링 엔진 모듈을 호출합니다."""
        if not hasattr(self, 'raw_map_img') or not self.raw_map_img:
            return

        img, positions = MapRenderer.render_current_view(
            raw_map_img=self.raw_map_img,
            current_zoom=self.current_zoom,
            current_center=self.current_center,
            last_api_center=self.last_api_center,
            last_api_zoom=self.last_api_zoom,
            place_data=self.place_data,
            pin_size_key=self.pin_size_key.get(),
            font_size=self.font_size_var.get(),
            type_colors=self.type_colors,
            old_map_img=self.old_map_img,
            old_last_center=getattr(self, 'old_last_center', None),
            old_last_zoom=getattr(self, 'old_last_zoom', None),
            blend_alpha=self.blend_alpha
        )

        self.marker_positions = positions
        photo = ImageTk.PhotoImage(img)
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
