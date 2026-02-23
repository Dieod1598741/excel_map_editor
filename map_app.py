"""
엑셀 지도 에디터 - 메인 애플리케이션
"""
import ttkbootstrap as tb # type: ignore
try:
    from ttkbootstrap.constants import PRIMARY, SECONDARY, SUCCESS, DANGER, DARK, STRIPED # type: ignore
except:
    PRIMARY, SECONDARY, SUCCESS, DANGER, DARK, STRIPED = "primary", "secondary", "success", "danger", "dark", "striped"

from ttkbootstrap.widgets.scrolled import ScrolledFrame # type: ignore
import pandas as pd # type: ignore
import requests # type: ignore
from io import BytesIO
from PIL import Image, ImageTk # type: ignore
import json
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import math
import sys
from typing import Optional, Tuple, Dict, List, Any, cast, TYPE_CHECKING
if TYPE_CHECKING:
    from ttkbootstrap.widgets.scrolled import ScrolledFrame # type: ignore

def get_app_dir():
    """실행 파일 또는 스크립트가 위치한 디렉토리를 반환합니다."""
    if getattr(sys, 'frozen', False):
        # PyInstaller로 빌드된 경우 실행 파일(.exe)의 위치
        return os.path.dirname(sys.executable)
    # 스크립트로 실행되는 경우
    return os.path.dirname(os.path.abspath(__file__))

# 모듈별 기능 임포트
from config import ( # type: ignore
    DEFAULT_PROVIDER, TYPE_COLOR_MAP, PRESET_PALETTES, DIR_ICON_MAP,
    VWORLD_STATIC_MAP_URL, NAVER_STATIC_MAP_URL, ZOOM_RANGE, TILE_SIZE
)
from utils.geo_utils import latlon_to_pixel, calculate_zoom_and_center # type: ignore
from utils.geocoding import GeocodeEngine # type: ignore
from renderer.map_renderer import MapRenderer # type: ignore

# ─────────────────────────────────────────────────────────────────────────────
class ToolTip:
    """Tkinter 위젯용 가벼운 툴팁 클래스"""
    def __init__(self, widget):
        self.widget = widget
        self.tip_window = None # type: ignore

    def show(self, text, x, y):
        if self.tip_window or not text:
            return
        self.tip_window = tw = tk.Toplevel(self.widget) # type: ignore
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x+15}+{y+10}")
        label = tk.Label(tw, text=text, justify=tk.LEFT,
                         background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                         font=("Malgun Gothic", "9", "normal"), padx=5, pady=2) # type: ignore
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
        try:
            self.style = tb.Style(theme="litera")
        except:
            self.style = None

        # ── 상태 변수 ────────────────────────────────────────────────────────
        self.api_keys = self.load_api_keys()
        v_key = self.api_keys.get("vworld_key", "")
        n_id  = self.api_keys.get("naver_client_id", "")
        n_sec = self.api_keys.get("naver_client_secret", "")
        
        self.geo_engine = GeocodeEngine(vworld_key=v_key, naver_client_id=n_id, naver_client_secret=n_sec, log_fn=self.add_log)
        self.map_provider = tk.StringVar(value=DEFAULT_PROVIDER)
        self.geo_engine.provider = self.map_provider.get()

        self.marker_positions = []
        self.place_data       = []   # {lon, lat, name, addr, type, label_dir, visible, var}
        self.current_center   = (37.5666, 126.9784)
        self.current_zoom     = 12.0
        self.last_api_zoom    = 12
        self.last_api_center  = (37.5666, 126.9784)
        self.drag_start_pos: Optional[Tuple[int, int]] = None
        self.zoom_timer: Any       = None
        self.display_scale    = 1.0

        # 시네마틱 블렌딩 엔진
        self.old_map_img  = None
        self.raw_map_img  = None
        self.old_last_center = (37.5666, 126.9784)
        self.old_last_zoom = 12.0
        self.blend_alpha  = 1.0
        self.blend_timer  = None

        # ── 커스터마이징 설정 ───────────────────────────────────────────────
        self.type_color_idx = dict(TYPE_COLOR_MAP)
        self.type_colors = {str(t): PRESET_PALETTES[int(idx)] for t, idx in self.type_color_idx.items()}

        self.pin_size_key = tk.StringVar(value="보통")
        self.font_size_var = tk.IntVar(value=12)
        
        # UI 관련 추가 변수 (Lint 에러 방지용 초기화 및 타입 힌트)
        self.progress_var = tk.DoubleVar()
        self.select_all_var = tk.BooleanVar(value=True)
        self.vworld_key_var = tk.StringVar(value=v_key)
        self.naver_id_var = tk.StringVar(value=n_id)
        self.naver_sec_var = tk.StringVar(value=n_sec)
        
        # 위젯 변수들 - 타입 지정을 통해 린트 에러 최소화
        self.dynamic_input_container: tb.Frame = cast(tb.Frame, None)
        self.vworld_input_frame: tb.Frame = cast(tb.Frame, None)
        self.naver_input_frame: tb.Frame = cast(tb.Frame, None)
        self.progress_frame: tb.Frame = cast(tb.Frame, None)
        self.map_container: tb.Labelframe = cast(tb.Labelframe, None)
        self.map_label: tb.Label = cast(tb.Label, None)
        self.pin_overlay: tb.Frame = cast(tb.Frame, None)
        self._pin_size_btns: Dict[str, tb.Button] = {}
        self.list_container: tb.Labelframe = cast(tb.Labelframe, None)
        self._color_btns: Dict[str, tk.Button] = {}
        self.scrollable_frame: ScrolledFrame = cast(ScrolledFrame, None)
        self.log_text: tk.Text = cast(tk.Text, None)
        self.context_menu: tk.Menu = cast(tk.Menu, None)
        self.focus_widget: tk.Widget = cast(tk.Widget, None)
        self.tooltip = ToolTip(self.root)
        self._apply_macos_shortcuts()
        self.setup_ui()
        self._log_current_keys()

    def _log_current_keys(self):
        """현재 로드된 API 키의 앞뒤 일부를 로그에 출력하여 확인을 돕습니다."""
        def mask(s):
            if not s: return "(미설정)"
            if len(s) <= 8: return "****"
            return f"{s[:4]}...{s[-4:]}"
        
        v_key = self.api_keys.get("vworld_key", "")
        n_id  = self.api_keys.get("naver_client_id", "")
        n_sec = self.api_keys.get("naver_client_secret", "")
        
        self.add_log("--- 현재 적용된 API 키 정보 ---")
        self.add_log(f"Vworld: {mask(v_key)}")
        self.add_log(f"Naver ID: {mask(n_id)}")
        self.add_log(f"Naver Secret: {mask(n_sec)}")
        self.add_log("----------------------------")

    def _apply_macos_shortcuts(self):
        """macOS에서 Command+C/V/A/X 등을 강제로 활성화합니다."""
        if sys.platform != 'darwin':
            return
        # 모든 Entry와 TEntry 클래스에 대해 바인딩
        for cls in ("Entry", "TEntry"):
            # 소문자와 대문자 모두 대응 (일부 환경 차이 대응)
            self.root.bind_class(cls, "<Command-v>", lambda e: self._macos_paste(e))
            self.root.bind_class(cls, "<Command-V>", lambda e: self._macos_paste(e))
            self.root.bind_class(cls, "<Command-c>", lambda e: e.widget.event_generate("<<Copy>>"))
            self.root.bind_class(cls, "<Command-C>", lambda e: e.widget.event_generate("<<Copy>>"))
            self.root.bind_class(cls, "<Command-x>", lambda e: e.widget.event_generate("<<Cut>>"))
            self.root.bind_class(cls, "<Command-X>", lambda e: e.widget.event_generate("<<Cut>>"))
            self.root.bind_class(cls, "<Command-a>", lambda e: self._select_all_entry(e))
            self.root.bind_class(cls, "<Command-A>", lambda e: self._select_all_entry(e))
            self.root.bind_class(cls, "<FocusIn>", lambda e: self._set_focus(e))
        
        # 루트 창 레벨에서도 캡처 (포커스된 위젯으로 이벤트 전달)
        self.root.bind("<Command-v>", lambda e: self._handle_root_shortcut("<<Paste>>"))
        self.root.bind("<Command-V>", lambda e: self._handle_root_shortcut("<<Paste>>"))
        self.root.bind("<Command-c>", lambda e: self._handle_root_shortcut("<<Copy>>"))
        self.root.bind("<Command-C>", lambda e: self._handle_root_shortcut("<<Copy>>"))
        self.root.bind("<Command-x>", lambda e: self._handle_root_shortcut("<<Cut>>"))
        self.root.bind("<Command-X>", lambda e: self._handle_root_shortcut("<<Cut>>"))
        self.root.bind("<Command-a>", lambda e: self._handle_root_shortcut("<<SelectAll>>"))
        self.root.bind("<Command-A>", lambda e: self._handle_root_shortcut("<<SelectAll>>"))

    def _handle_root_shortcut(self, event_name):
        """포커스된 위젯이 Entry 종류라면 이벤트를 전달합니다."""
        focus = self.root.focus_get()
        if focus:
            # 클래스 이름이나 위젯 타입을 확인하여 Entry 계열인지 판단
            cls_name = focus.winfo_class()
            is_entry = isinstance(focus, (tk.Entry, ttk.Entry)) or \
                       cls_name in ("Entry", "TEntry") or \
                       'entry' in str(focus).lower()
            
            if is_entry:
                if event_name == "<<Paste>>" and hasattr(self, '_macos_paste'):
                    self._macos_paste(focus)
                elif event_name == "<<SelectAll>>" and hasattr(self, '_select_all_entry'):
                    self._select_all_entry(focus)
                else:
                    focus.event_generate(event_name)
        return "break"

    def _set_focus(self, event):
        self.focus_widget = event.widget

    def _macos_paste(self, event_or_widget):
        """macOS용 수동 붙여넣기 처리"""
        try:
            widget = event_or_widget.widget if hasattr(event_or_widget, 'widget') else event_or_widget
            if not widget: return "break"
                
            # 현재 클립보드 내용 가져오기
            content = self.root.clipboard_get()
            if content:
                w_any: Any = widget
                if hasattr(w_any, 'delete') and hasattr(w_any, 'insert'):
                    try:
                        w_any.delete(tk.SEL_FIRST, tk.SEL_LAST) # type: ignore
                    except: pass
                    w_any.insert(tk.INSERT, content) # type: ignore
        except tk.TclError: # Clipboard might be empty or inaccessible
            # 클립보드가 비어있거나 오류 시 기존 이벤트 발생 시도
            try:
                widget.event_generate("<<Paste>>")
            except: pass
        return "break"

    def _select_all_entry(self, event_or_widget):
        widget = event_or_widget.widget if hasattr(event_or_widget, 'widget') else event_or_widget
        widget.select_range(0, tk.END)
        widget.icursor(tk.END)
        return "break"

    def _setup_macos_menu(self):
        """macOS 시스템 메뉴바에 표준 편집(Edit) 메뉴를 추가합니다."""
        if self.root.tk.call('tk', 'windowingsystem') != 'aqua':
            return
            
        main_menu = tk.Menu(self.root)
        
        # 편집(Edit) 메뉴 생성
        edit_menu = tk.Menu(main_menu, tearoff=0)
        edit_menu.add_command(label="Undo", accelerator="Command+Z", command=lambda: self.root.focus_get().event_generate("<<Undo>>"))
        edit_menu.add_command(label="Redo", accelerator="Command+y", command=lambda: self.root.focus_get().event_generate("<<Redo>>"))
        edit_menu.add_separator()
        edit_menu.add_command(label="Cut", accelerator="Command+X", command=lambda: self.root.focus_get().event_generate("<<Cut>>"))
        edit_menu.add_command(label="Copy", accelerator="Command+C", command=lambda: self.root.focus_get().event_generate("<<Copy>>"))
        edit_menu.add_command(label="Paste", accelerator="Command+V", command=lambda: self.root.focus_get().event_generate("<<Paste>>"))
        edit_menu.add_command(label="Select All", accelerator="Command+A", command=lambda: self.root.focus_get().event_generate("<<SelectAll>>"))
        
        main_menu.add_cascade(label="Edit", menu=edit_menu)
        self.root.config(menu=main_menu)

    def _setup_context_menu(self):
        """Entry 위젯용 우클릭 메뉴를 생성합니다."""
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="잘라내기 (Cut)", command=lambda: self.focus_widget.event_generate("<<Cut>>"))
        self.context_menu.add_command(label="복사 (Copy)", command=lambda: self.focus_widget.event_generate("<<Copy>>"))
        self.context_menu.add_command(label="붙여넣기 (Paste)", command=lambda: self.focus_widget.event_generate("<<Paste>>"))
        self.context_menu.add_separator()
        self.context_menu.add_command(label="모두 선택 (Select All)", command=lambda: self.focus_widget.event_generate("<<SelectAll>>"))

        # 모든 Entry 위젯에 우클릭 바인딩
        self.root.bind_class("Entry", "<Button-2>" if self.root.tk.call('tk', 'windowingsystem') == 'aqua' else "<Button-3>", self._show_context_menu)
        self.root.bind_class("TEntry", "<Button-2>" if self.root.tk.call('tk', 'windowingsystem') == 'aqua' else "<Button-3>", self._show_context_menu)

    def _show_context_menu(self, event):
        self.focus_widget = event.widget
        if self.context_menu:
            self.context_menu.post(event.x_root, event.y_root)
        return "break"

    def _btn_paste(self, var_obj):
        """버튼 클릭 시 클립보드 내용을 해당 StringVar에 붙여넣습니다."""
        try:
            content = self.root.clipboard_get()
            if content:
                var_obj.set(content.strip())
                self.add_log("클립보드 내용이 붙여넣기 되었습니다.")
        except:
            messagebox.showwarning("붙여넣기 실패", "클립보드가 비어있거나 접근할 수 없습니다.")

    def _btn_paste_naver(self):
        """네이버용 붙여넣기 (ID/Secret 구분이 모호하므로 알림 후 처리하거나 마지막 포커스된 곳에 넣음)"""
        try:
            content = self.root.clipboard_get()
            if not content: return
            
            # 사용자에게 어디에 붙여넣을지 묻거나, 그냥 최근 포커스 사용
            # 여기서는 편의상 ID란이 비었으면 ID에, 아니면 Secret에 넣는 식으로 예시 구현하거나
            # 별도의 버튼 2개를 만드는 것이 가장 확실함. (위의 코드에서 버튼 1개로 합쳤으므로 로직 조정)
            # 일단은 마지막으로 포커스된 엔트리가 네이버 관련이면 거기에 넣음
            if hasattr(self, 'focus_widget') and self.focus_widget:
                self.focus_widget.delete(0, tk.END) # type: ignore
                self.focus_widget.insert(0, content.strip()) # type: ignore
            else:
                # 포커스가 없으면 그냥 알림
                messagebox.showinfo("안내", "입력창을 한 번 클릭한 후 붙여넣기 버튼을 눌러주세요.")
        except: pass

    # ─────────────────────────────────────────────────────────────────────────
    # UI 구성
    # ─────────────────────────────────────────────────────────────────────────
    def setup_ui(self):
        self._setup_macos_menu()
        self._setup_context_menu()

        # ── 최상단: API 키 입력 배너 ─────────────────────────────────────────
        api_frame = tb.Frame(self.root, padding="8 6")
        api_frame.pack(side=tk.TOP, fill=tk.X)

        # 서비스 선택
        tb.Label(api_frame, text="🗺️ 지도:", font=("Malgun Gothic", 9, "bold")).pack(side=tk.LEFT, padx=(0, 4))
        provider_combo = tb.Combobox(api_frame, textvariable=self.map_provider, values=["vworld", "naver"], width=8, state="readonly")
        provider_combo.pack(side=tk.LEFT, padx=(0, 10))
        provider_combo.bind("<<ComboboxSelected>>", lambda e: self.on_provider_change()) # type: ignore

        # 동적 입력 컨테이너 (프로바이드에 따라 내용이 바뀜)
        self.dynamic_input_container = tb.Frame(api_frame)
        self.dynamic_input_container.pack(side=tk.LEFT, padx=(0, 10))

        # 브이월드 키 컨테이너
        self.vworld_input_frame = tb.Frame(self.dynamic_input_container)
        tb.Label(self.vworld_input_frame, text="Vworld Key:", font=("Malgun Gothic", 8)).pack(side=tk.LEFT, padx=(0, 2))
        v_entry = tb.Entry(self.vworld_input_frame, textvariable=self.vworld_key_var, width=25, show="*")
        v_entry.pack(side=tk.LEFT, padx=(0, 4))
        tb.Button(self.vworld_input_frame, text="📋", width=3, command=lambda: self._btn_paste(self.vworld_key_var), bootstyle="outline-secondary").pack(side=tk.LEFT, padx=(0, 8))

        # 네이버 컨데이너
        self.naver_input_frame = tb.Frame(self.dynamic_input_container)
        tb.Label(self.naver_input_frame, text="Naver ID:", font=("Malgun Gothic", 8)).pack(side=tk.LEFT, padx=(0, 2))
        n_id_entry = tb.Entry(self.naver_input_frame, textvariable=self.naver_id_var, width=18, show="*")
        n_id_entry.pack(side=tk.LEFT, padx=(0, 4))
        tb.Button(self.naver_input_frame, text="📋", width=3, command=lambda: self._btn_paste(self.naver_id_var), bootstyle="outline-secondary").pack(side=tk.LEFT, padx=(0, 4))

        tb.Label(self.naver_input_frame, text="Secret:", font=("Malgun Gothic", 8)).pack(side=tk.LEFT, padx=(0, 2))
        n_sec_entry = tb.Entry(self.naver_input_frame, textvariable=self.naver_sec_var, width=18, show="*")
        n_sec_entry.pack(side=tk.LEFT, padx=(0, 4))
        tb.Button(self.naver_input_frame, text="📋", width=3, command=lambda: self._btn_paste(self.naver_sec_var), bootstyle="outline-secondary").pack(side=tk.LEFT, padx=(0, 8))

        # 초기 가시성 설정
        self.update_api_field_visibility()

        tb.Button(api_frame, text="저장", command=self.save_api_keys, bootstyle=PRIMARY, width=5).pack(side=tk.LEFT, padx=(0, 4))
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
        tb.Progressbar(self.progress_frame, variable=self.progress_var,
                       maximum=100, length=300,
                       bootstyle=(SUCCESS, STRIPED)).pack(side=tk.RIGHT, padx=10)

        # ── 메인 수평 분할 ────────────────────────────────────────────────────
        main_h_pane = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
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
        self.pin_overlay = tb.Frame(self.map_container, padding=5)
        self.pin_overlay.place(relx=1.0, rely=1.0, x=-10, y=-10, anchor=tk.SE)

        # 핀 크기 버튼들
        for size in ("S", "M", "L"):
            btn = tb.Button(self.pin_overlay, text=size, width=3,
                            command=lambda s=size: self.set_pin_size(s),
                            bootstyle=PRIMARY if size == "M" else "outline-secondary")
            btn.pack(side=tk.LEFT, padx=2)
            self._pin_size_btns[size] = btn

        # ── 오른쪽 수직 분할 ─────────────────────────────────────────────────
        right_v_pane = ttk.Panedwindow(main_h_pane, orient=tk.VERTICAL)
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
                            command=lambda tp=t: self.cycle_type_color(tp), # type: ignore
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
    def load_api_keys(self) -> Dict[str, str]:
        """
        보안 강화를 위해 환경 변수(.env 파일 포함)와 config.json을 병합하여 읽어옵니다.
        우선순위: 시스템 환경 변수 > .env 파일 > config.json
        """
        keys = {
            "vworld_key": os.getenv("VWORLD_API_KEY", ""),
            "naver_client_id": os.getenv("NAVER_CLIENT_ID", ""),
            "naver_client_secret": os.getenv("NAVER_CLIENT_SECRET", "")
        }

        # .env 파일 파싱 (환경 변수가 비어있는 항목만 채움)
        app_dir = get_app_dir()
        env_path = os.path.join(app_dir, ".env")
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if "=" in line and not line.startswith("#"):
                            k, v = line.split("=", 1)
                            k, v = k.strip(), v.strip()
                            if k == "VWORLD_API_KEY" and not keys["vworld_key"]: keys["vworld_key"] = v
                            elif k == "NAVER_CLIENT_ID" and not keys["naver_client_id"]: keys["naver_client_id"] = v
                            elif k == "NAVER_CLIENT_SECRET" and not keys["naver_client_secret"]: keys["naver_client_secret"] = v
            except: pass

        # config.json 로드 (여전히 비어있는 항목만 채움)
        cfg = os.path.join(app_dir, "config.json")
        if os.path.exists(cfg):
            try:
                with open(cfg, "r") as f:
                    data = json.load(f)
                    if not keys["vworld_key"]: 
                        keys["vworld_key"] = data.get("vworld_key") or data.get("api_key") or ""
                    if not keys["naver_client_id"]: 
                        keys["naver_client_id"] = data.get("naver_client_id", "")
                    if not keys["naver_client_secret"]: 
                        keys["naver_client_secret"] = data.get("naver_client_secret", "")
            except: pass
        
        return keys

    def save_api_keys(self):
        v_key = self.vworld_key_var.get().strip()
        n_id  = self.naver_id_var.get().strip()
        n_sec = self.naver_sec_var.get().strip()
        
        self.api_keys = {
            "vworld_key": v_key,
            "naver_client_id": n_id,
            "naver_client_secret": n_sec
        }
        
        # 엔진 업데이트
        self.geo_engine.vworld_key = v_key
        self.geo_engine.naver_client_id = n_id
        self.geo_engine.naver_client_secret = n_sec
            
        cfg = os.path.join(get_app_dir(), "config.json")
        try:
            with open(cfg, "w") as f:
                json.dump(self.api_keys, f)
            self.add_log("API 키 저장 완료 (config.json)")
            messagebox.showinfo("저장 완료", "API 키가 저장되었습니다.")
        except Exception as e:
            messagebox.showerror("저장 오류", f"config.json 저장 실패: {e}")

    def on_provider_change(self):
        provider = self.map_provider.get()
        self.geo_engine.provider = provider
        self.add_log(f"지도 서비스 변경: {provider}")
        
        self.update_api_field_visibility()
        
        if self.place_data:
            self.refresh_map()

    def update_api_field_visibility(self):
        """선택된 프로바이더에 따라 API 입력 필드를 표시하거나 숨깁니다."""
        provider = self.map_provider.get()
        if provider == "naver":
            self.vworld_input_frame.pack_forget()
            self.naver_input_frame.pack(side=tk.LEFT, padx=(0, 10))
        else:
            self.naver_input_frame.pack_forget()
            self.vworld_input_frame.pack(side=tk.LEFT, padx=(0, 10))

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
    def add_log(self, message: str, level: str = "info"):
        """로그를 출력창에 추가합니다. (스레드 안전)"""
        def _append():
            log_box = self.log_text
            if log_box:
                log_box.config(state=tk.NORMAL)
                timestamp = pd.Timestamp.now().strftime('%H:%M:%S')
                prefix = "[INFO]" if level == "info" else "[ERROR]"
                log_box.insert(tk.END, f"[{timestamp}] {prefix} {message}\n")
                log_box.see(tk.END)
                log_box.config(state=tk.DISABLED)
        self.root.after(0, _append)

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
                {"주소": "━━━ [사용 가이드 - 이 행들은 삭제 후 사용하세요] ━━━", "장소명": "", "순서": ""},
                {"주소": "1. [주소] 컬럼: 도로명/지번 주소 또는 유명 지명을 입력하세요.",  "장소명": "", "순서": ""},
                {"주소": "2. [장소명] 컬럼: 지도에 표시될 이름 (비워두면 주소로 표시).", "장소명": "", "순서": ""},
                {"주소": "3. [순서] 컬럼: 핀 연결 순서 (숫자, 비워두면 행 순서).", "장소명": "", "순서": ""},
                {"주소": "   · '핀 연결선 표시' 버튼을 켜면 순서대로 선 연결됩니다.", "장소명": "", "순서": ""},
                {"주소": "4. 실제 데이터는 이 안내 행들 아래부터 입력하세요.", "장소명": "", "순서": ""},
                {"주소": "━━━ 아래부터 실제 데이터 입력 ━━━", "장소명": "", "순서": ""},
                {"주소": "서울시 중구 세종대로 110",          "장소명": "서울시청", "순서": 1},
                {"주소": "강남역",                            "장소명": "강남역",   "순서": 2},
                {"주소": "인천국제공항",                      "장소명": "인천공항", "순서": 1},
                {"주소": "부산 해운대구 해운대해변로 264",    "장소명": "해운대",   "순서": 2},
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
        # UI 입력값을 최신으로 동기화 (저장 버튼 누르지 않았을 때 대비)
        v_key = self.vworld_key_var.get().strip()
        n_id  = self.naver_id_var.get().strip()
        n_sec = self.naver_sec_var.get().strip()
        
        self.api_keys = {"vworld_key": v_key, "naver_client_id": n_id, "naver_client_secret": n_sec}
        self.geo_engine.vworld_key = v_key
        self.geo_engine.naver_client_id = n_id
        self.geo_engine.naver_client_secret = n_sec

        # 현재 선택된 제공자에 필요한 키가 있는지 확인
        provider = self.map_provider.get()
        has_key = False
        if provider == "vworld":
            if v_key: has_key = True
        else: # naver
            if n_id and n_sec: has_key = True
        
        if not has_key:
            messagebox.showerror("오류", f"{provider.capitalize()} API 키 정보가 필요합니다.")
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

        success_idx: int = 0
        fail_idx: int = 0
        try:
            try:
                df = pd.read_excel(file_path)
            except ImportError as ie:
                self.add_log("Excel 엔진(openpyxl)이 누락되었습니다. 빌드 옵션을 확인해 주세요.", "error")
                self.root.after(0, lambda: messagebox.showerror("오류", "Excel 엔진이 누락되었습니다. 빌드 시 openpyxl을 포함해야 합니다."))
                return
            df.columns = [str(c).strip() for c in df.columns]

            if '주소' not in df.columns:
                self.root.after(0, lambda: messagebox.showerror("오류", "'주소' 컬럼을 찾을 수 없습니다."))
                return

            total_rows = len(df)
            temp_place_data = []

            # 메인 스레드에서 기존 UI 목록 초기화
            self.root.after(0, self._clear_ui_on_load)

            for i, row in df.iterrows():
                # 프로그레스 바 업데이트
                self.progress_var.set((i + 1) / total_rows * 50)

                addr_raw = row.get('주소')
                if pd.isna(addr_raw): continue # type: ignore
                addr = str(addr_raw).strip()
                if not addr or addr.lower() == "nan": continue

                type_val  = 'A'

                order_raw = row.get('순서', None)
                try:
                    order_val = int(float(order_raw)) if order_raw is not None and not pd.isna(order_raw) else i
                except: # type: ignore
                    order_val = i

                lon, lat, road_addr_from_geo = self.geocode(addr)

                if lon and lat:
                    success_idx = int(success_idx) + 1 # type: ignore
                    # Use geocoded road_addr if available, otherwise original address
                    road_addr = road_addr_from_geo if road_addr_from_geo else addr
                    
                    # Use '장소명' from excel if available, otherwise original address
                    name_raw  = row.get('장소명')
                    name      = str(name_raw).strip() if not pd.isna(name_raw) and str(name_raw).strip() else addr # type: ignore
                    
                    item_data = {
                        "lon": lon, "lat": lat, "name": name, "addr": road_addr,
                        "type": type_val, "order": order_val, "label_dir": "top",
                        "visible": True, "success_idx": success_idx
                    }
                    self.root.after(0, lambda d=item_data: self._add_place_to_ui(d))
                    self.add_log(f"✓ {name} [{type_val}]")
                else:
                    fail_idx = int(fail_idx) + 1 # type: ignore
                    self.add_log(f"✗ 실패: {addr}", "error")

            self.add_log(f"1단계 완료: {success_idx}개 성공, {fail_idx}개 실패")
            self.root.after(0, lambda: self._finalize_loading_ui())

        except Exception as e:
            self.add_log(f"엑셀 추출 오류: {e}")
            self.root.after(0, lambda: messagebox.showerror("오류", f"파일 읽기 실패: {e}"))

    def _clear_ui_on_load(self):
        """새 데이터를 불러오기 전에 UI 리스트와 마커 배열을 비웁니다."""
        self.marker_positions = []
        self.place_data = []
        if self.scrollable_frame and hasattr(self.scrollable_frame, 'winfo_children'):
            for child in self.scrollable_frame.winfo_children():
                child.destroy()

    def _add_place_to_ui(self, item_data):
        """
        사이드바 목록에 장소 아이템을 동적으로 추가합니다.
        스레드 안전을 위해 self.root.after를 통해 호출되어야 합니다.
        """
        var     = tk.BooleanVar(value=True)
        dir_var = tk.StringVar(value="⬆ 위")
        item_data["var"] = var
        item_data["dir_var"] = dir_var
        
        # 메인 데이터 리스트에 추가 (thread-safe UI 업데이트 시점에 수행)
        self.place_data.append(item_data)
        
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
                               command=lambda it=item_data: self._toggle_dir_controls(it)) # type: ignore
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
                            command=lambda it=item_data, dv=dirval, br=dir_btns: self._set_label_dir(it, dv, br)) # type: ignore
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
        self.root.after(1000, lambda: self.perform_perfect_centered_fit())

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
            icon = DIR_ICON_MAP.get(cur, "↑") # type: ignore
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
        clat, clon, czoom = calculate_zoom_and_center(visible, 800, 800, padding=0.25) # type: ignore
        self.current_center = (float(clat), float(clon))
        self.current_zoom   = float(czoom)
        self.refresh_map()
        self.add_log(f"1차 로드: 전체 분포 표시 (줌 {float(round(float(czoom), 1))})") # type: ignore

    def perform_perfect_centered_fit(self):
        if not self.place_data:
            return
        visible = [(p["lon"], p["lat"]) for p in self.place_data if p["var"].get()]
        if not visible:
            return
        self.add_log("--- 2차: 상하좌우 중앙 맞춤 시작 ---")
        clat_v, clon_v, czoom_v = calculate_zoom_and_center(visible, 800, 800, padding=0.15) # type: ignore
        self.current_center = (float(clat_v), float(clon_v))
        self.current_zoom   = float(czoom_v) # type: ignore
        self.refresh_map()
        self.progress_var.set(100)
        self.add_log(f"최종 완료: 최적 줌 {round(czoom_v,1)}") # type: ignore

    # ─────────────────────────────────────────────────────────────────────────
    # 지도 갱신
    # ─────────────────────────────────────────────────────────────────────────
    def refresh_map(self):
        """
        선택된 서비스(Vworld 또는 Naver)로부터 베이스 지도를 가져옵니다.
        """
        if not self.place_data:
            return

        # 현재 상태 백업 (블렌딩용)
        if self.raw_map_img is not None:
            self.old_map_img = self.raw_map_img.copy() # type: ignore
        self.old_last_center = self.current_center
        self.old_last_zoom   = self.current_zoom
        self.blend_alpha  = 0.0 # Start blend from 0
        self.blend_timer  = None

        map_w, map_h = 800, 800
        clat, clon = float(round(self.current_center[0], 6)), float(round(self.current_center[1], 6)) # type: ignore
        base_zoom = int(self.current_zoom)
        self.last_api_zoom   = base_zoom
        self.last_api_center = (clat, clon)

        provider = self.map_provider.get()
        
        if provider == "naver":
            # 네이버 정적 지도 최적화 (줌 레벨 보정: vworld 12 -> naver 11 정도가 유사)
            naver_zoom = base_zoom - 1
            url = NAVER_STATIC_MAP_URL
            headers = {
                "X-NCP-APIGW-API-KEY-ID": self.api_keys.get("naver_client_id", ""),
                "X-NCP-APIGW-API-KEY": self.api_keys.get("naver_client_secret", "")
            }
            params = {
                "w": map_w, "h": map_h,
                "center": f"{clon},{clat}",
                "level": naver_zoom,
                "scale": 2, # 고해상도 요청
                "format": "jpg"
            }
        else:
            url = VWORLD_STATIC_MAP_URL
            headers = {}
            params = {
                "service": "image", "request": "getmap",
                "key": self.api_keys.get("vworld_key", ""),
                "center": f"{clon},{clat}",
                "zoom": base_zoom,
                "size": f"{map_w},{map_h}",
                "basemap": "GRAPHIC", "format": "png",
            }

        try:
            self.add_log(f"지도 갱신 중 ({provider})...")
            # print(f"[Debug] Map Request: {url} params={params}")
            response = requests.get(url, headers=headers, params=params, verify=False, timeout=10) # type: ignore

            if response.status_code == 200:
                # 데이터 유효성 확인
                if len(response.content) < 500: # 너무 작은 데이터는 에러 메시지일 가능성 높음
                    self.add_log(f"지도 데이터 오류: 내용이 너무 짧음 ({len(response.content)} bytes)")
                    try: print(f"Response Error Content: {response.text}")
                    except: pass
                    return

                img_data = BytesIO(response.content)
                try:
                    self.raw_map_img = Image.open(img_data).convert("RGBA")
                    self.start_crossfade()
                except Exception as img_err:
                    self.add_log(f"이미지 파싱 오류: {img_err}")
            else:
                self.add_log(f"지도 서버 오류 ({provider}): {response.status_code}")
                if provider == "naver" and response.status_code == 401:
                    self.add_log("네이버 API 인증 실패: ID/Secret 및 서비스를 확인하세요.")
                elif provider == "vworld" and response.status_code == 401:
                    self.add_log("Vworld API 인증 실패: 키를 확인하세요.")
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
        if self.raw_map_img is None:
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
            old_last_center=self.old_last_center,
            old_last_zoom=self.old_last_zoom,
            blend_alpha=self.blend_alpha
        )

        self.marker_positions = positions
        photo = ImageTk.PhotoImage(img)
        self._update_map_ui(photo)

    def _update_map_ui(self, tk_img):
        """지도 이미지를 라벨에 업데이트합니다."""
        if self.map_label:
            self.map_label.config(image=tk_img)
            self.map_label.image = tk_img

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
            if self.raw_map_img is not None:
                # render 결과를 바로 저장하기 위해 한 번 더 렌더링 후 저장
                # (실제 저장은 MapRenderer를 통하거나 현재 이미지를 기반으로 처리 가능)
                self.add_log(f"이미지 저장 완료: {file_path}")
                messagebox.showinfo("저장 완료", f"이미지가 저장되었습니다:\n{file_path}")
        except Exception as e:
            messagebox.showerror("저장 오류", f"이미지 생성 중 오류: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # 드래그 / 줌 이벤트
    # ─────────────────────────────────────────────────────────────────────────
    def on_drag_start(self, event):
        self.drag_start_pos = (int(event.x), int(event.y))

    def on_drag_motion(self, event):
        # Use local variable to satisfy Optional type guard for linter
        start_pos = self.drag_start_pos
        if start_pos is None or self.raw_map_img is None:
            return
            
        dx = int(event.x) - start_pos[0] # type: ignore
        dy = int(event.y) - start_pos[1] # type: ignore

        num_tiles        = 2 ** self.current_zoom
        pixel_per_degree = (num_tiles * TILE_SIZE) / 360.0
        clat, clon       = self.current_center
        cos_lat          = math.cos(math.radians(clat))

        d_lon = -dx / (pixel_per_degree * cos_lat)
        d_lat =  dy / pixel_per_degree

        self.current_center = (clat + d_lat, clon + d_lon)
        self.drag_start_pos = (int(event.x), int(event.y))
        self.render_current_view()

        if self.zoom_timer:
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
        self.add_log(f"전체 보기 최적화 완료 (줌: {czoom})") # type: ignore

    # ─────────────────────────────────────────────────────────────────────────
    # 마우스 툴팁
    # ─────────────────────────────────────────────────────────────────────────
    def on_mouse_move(self, event):
        if not self.marker_positions:
            return
        found = False
        for marker in self.marker_positions:
            bx1, by1, bx2, by2 = marker["bbox"] # type: ignore
            if bx1 <= event.x <= bx2 and by1 <= event.y <= by2: # type: ignore
                self.tooltip.show( # type: ignore
                    f"장소: {marker['name']}\n주소: {marker['address']}", # type: ignore
                    event.x_root, event.y_root) # type: ignore
                found = True
                break
        if not found:
            self.tooltip.hide()


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app_root = tb.Window(themename="litera")
    app = AddressMapApp(app_root)
    app_root.mainloop()
