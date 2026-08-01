import bisect
import mmap
import os
import re
import threading
import time
import tkinter as tk
import traceback
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

try:
    import large_file_core

    RUST_AVAILABLE = True
    print("[LargeFileViewer] Rust 가속 코어가 활성화되었습니다.")
except ImportError as e:
    RUST_AVAILABLE = False
    print(f"[LargeFileViewer] Rust 코어를 로드할 수 없어 파이썬 폴백 모드로 동작합니다: {e}")

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class CTkCustomMenu(ctk.CTkFrame):
    def __init__(self, parent, master_window, items):
        super().__init__(
            parent,
            fg_color="#2b2b2b",
            border_width=1,
            border_color="#3a3a3a",
            corner_radius=6,
        )
        self.master_window = master_window
        self.items = items
        self.buttons = []
        self._bind_id = None

        for item in self.items:
            if item == "separator":
                sep = ctk.CTkFrame(self, height=1, fg_color="#3a3a3a")
                sep.pack(fill="x", padx=5, pady=4)
            else:
                target_cmd = item.get("command")
                btn = ctk.CTkButton(
                    self,
                    text=item["label"],
                    command=lambda cmd=target_cmd: self._on_item_click(cmd),
                    font=("Malgun Gothic", 11),
                    anchor="w",
                    fg_color="transparent",
                    hover_color="#1d5287",
                    text_color="#ffffff",
                    height=26,
                    corner_radius=4,
                )
                btn.pack(fill="x", padx=4, pady=2)
                self.buttons.append(btn)

    def show(self, x, y):
        self.place(x=x, y=y)
        self.lift()
        self.after(10, self._bind_click)

    def _bind_click(self):
        if self.winfo_exists():
            self._bind_id = self.master_window.bind("<Button-1>", self._on_outside_click, add="+")

    def hide(self):
        self.place_forget()
        if self._bind_id:
            try:
                self.master_window.unbind("<Button-1>", self._bind_id)
            except Exception:
                pass
            self._bind_id = None

    def _on_item_click(self, command):
        if command:
            try:
                command()
            except Exception as e:
                print(f"Menu action error: {e}")
        self.hide()

    def _on_outside_click(self, event):
        if not self.winfo_exists():
            return
        widget = event.widget
        try:
            x, y = event.x_root, event.y_root
            mx, my = self.winfo_rootx(), self.winfo_rooty()
            mw, mh = self.winfo_width(), self.winfo_height()
            if mx <= x <= (mx + mw) and my <= y <= (my + mh):
                return
        except Exception:
            pass
        if widget in [self.master_window.menu_file_btn, self.master_window.menu_tools_btn]:
            return
        self.hide()


class UltimateLargeFileViewer(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Ultimate Large File Viewer & Searcher (SIMD Super-Fast) V1.7.0")
        self.geometry("1150x850")
        self.minsize(900, 650)

        self.file_path = ""
        self.total_lines = 0
        self.max_visible_lines = 30
        self.current_start_line = 0
        self.detected_encoding = "utf-8"
        self.filesize_text = ""

        self.rust_lock = threading.Lock()  # Rust 객체 동시 접근 방지용 락
        self.rust_core = None
        if RUST_AVAILABLE:
            self.rust_core = large_file_core.FileIndexCore()

        self.line_offsets = []
        self.current_engine_used_rust = False

        self.is_indexing = False
        self.is_splitting = False
        self.is_merging = False
        self.is_searching = False

        self.is_following = False
        self.follow_timer = None
        self.last_known_file_size = 0

        # 드래그 선택 중 렌더링 스킵 플래그
        self.is_selecting = False

        self.file_handle = None
        self.mmap_obj = None

        self.filter_start = None
        self.filter_end = None

        self.search_panel_visible = False
        self.resize_timer = None

        self.setup_dark_scrollbar_style()
        self.setup_custom_dark_menu()

        self.top_frame = ctk.CTkFrame(self)
        self.top_frame.pack(fill="x", padx=15, pady=(10, 5))

        self.btn_open = ctk.CTkButton(
            self.top_frame,
            text="파일 열기",
            font=("Malgun Gothic", 12, "bold"),
            width=100,
            command=self.start_open_file_thread,
        )
        self.btn_open.pack(side="left", padx=(10, 5), pady=10)

        self.btn_close = ctk.CTkButton(
            self.top_frame,
            text="파일 닫기",
            font=("Malgun Gothic", 12, "bold"),
            width=100,
            fg_color="#27ae60",
            hover_color="#1e8449",
            command=self.close_file,
        )

        self.lbl_encoding = ctk.CTkLabel(self.top_frame, text="인코딩:", font=("Malgun Gothic", 11))
        self.lbl_encoding.pack(side="left", padx=(5, 2), pady=10)

        self.encoding_var = ctk.StringVar(value="[자동 감지 (Auto)]")
        self.combo_encoding = ctk.CTkOptionMenu(
            self.top_frame,
            values=["[자동 감지 (Auto)]", "UTF-8", "CP949 / EUC-KR", "UTF-16", "ASCII"],
            variable=self.encoding_var,
            width=150,
            font=("Malgun Gothic", 11),
            fg_color="#2b2b2b",
            button_color="#3a3a3a",
            button_hover_color="#4f4f4f",
            dropdown_fg_color="#2b2b2b",
            dropdown_hover_color="#1d5287",
            text_color="#d0d0d0",
        )
        self.combo_encoding.pack(side="left", padx=(0, 10), pady=10)

        self.lbl_file = ctk.CTkLabel(
            self.top_frame,
            text="선택된 파일이 없습니다. 인코딩을 지정하고 [파일 열기] 버튼을 누르세요.",
            font=("Malgun Gothic", 12),
            text_color="#aaaaaa",
            anchor="w",
        )
        self.lbl_file.pack(side="left", fill="x", expand=True, padx=5, pady=10)

        self.tab_panel_frame = ctk.CTkFrame(self)

        self.view_mode_var = ctk.StringVar(value="전체보기 (FULL)")
        self.tab_selector = ctk.CTkSegmentedButton(
            self.tab_panel_frame,
            values=["앞부분 보기 (HEAD)", "뒷부분 보기 (TAIL)", "실시간 추적 (FOLLOW)", "전체보기 (FULL)"],
            variable=self.view_mode_var,
            font=("Malgun Gothic", 12, "bold"),
            command=self.on_tab_changed,
        )
        self.tab_selector.pack(side="left", padx=15, pady=10)

        self.tab_option_frame = ctk.CTkFrame(self.tab_panel_frame, fg_color="transparent")
        self.tab_option_frame.pack(side="left", fill="y", padx=10)

        self.lbl_filter_lines = ctk.CTkLabel(self.tab_option_frame, text="출력 줄 수:", font=("Malgun Gothic", 11))
        self.lbl_filter_lines.pack(side="left", padx=5, pady=10)

        self.entry_filter_lines = ctk.CTkEntry(self.tab_option_frame, width=70, justify="center")
        self.entry_filter_lines.insert(0, "50")
        self.entry_filter_lines.bind("<Return>", lambda event: self.apply_tab_filter())
        self.entry_filter_lines.pack(side="left", padx=5, pady=10)

        self.btn_apply_filter = ctk.CTkButton(
            self.tab_option_frame,
            text="필터 적용",
            font=("Malgun Gothic", 11, "bold"),
            width=80,
            fg_color="#2b73b8",
            hover_color="#1d5287",
            command=self.apply_tab_filter,
        )
        self.btn_apply_filter.pack(side="left", padx=10, pady=10)

        self.body_container = ctk.CTkFrame(self, fg_color="transparent")
        self.body_container.pack(fill="both", expand=True, padx=15, pady=(5, 15))

        self.main_container = ctk.CTkFrame(self.body_container)
        self.main_container.pack(side="left", fill="both", expand=True)

        self.lbl_content_title = ctk.CTkLabel(
            self.main_container,
            text="FILE CONTENTS (0 / 0 줄)",
            font=("Consolas", 11, "bold"),
            text_color="#2b73b8",
        )
        self.lbl_content_title.pack(anchor="w", padx=15, pady=(10, 2))

        self.editor_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.editor_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        self.text_area = ctk.CTkTextbox(
            self.editor_frame,
            font=("Consolas", 13),
            wrap="none",
            corner_radius=8,
            fg_color="#2b2b2b",
            text_color="#a9b7c6",
        )
        self.text_area.pack(side="left", fill="both", expand=True)
        self.text_area._textbox.configure(spacing1=4, spacing3=4)

        self.text_area.bind("<MouseWheel>", self.on_mouse_wheel)
        self.text_area.bind("<Up>", lambda event: self.scroll_by_keyboard(-1))
        self.text_area.bind("<Down>", lambda event: self.scroll_by_keyboard(1))
        self.text_area.bind("<Prior>", lambda event: self.scroll_by_keyboard(-10))
        self.text_area.bind("<Next>", lambda event: self.scroll_by_keyboard(10))
        self.text_area.bind("<Control-a>", self.safe_select_all)
        self.text_area.bind("<Control-A>", self.safe_select_all)
        self.text_area.bind("<Control-c>", self.safe_copy)
        self.text_area.bind("<Control-C>", self.safe_copy)

        # 드래그 선택 시 튀는 현상 방지를 위한 이벤트 바인딩
        self.text_area.bind("<Button-1>", self._on_text_drag_start)
        self.text_area.bind("<ButtonRelease-1>", self._on_text_drag_end)

        self.text_area.configure(state="disabled")

        self.v_scrollbar = ttk.Scrollbar(
            self.editor_frame,
            orient="vertical",
            command=self.on_scroll,
            style="Dark.Vertical.TScrollbar",
        )
        self.v_scrollbar.pack(side="right", fill="y")
        self.text_area.bind("<Configure>", self.update_visible_count)

        self.search_panel_frame = ctk.CTkFrame(self.body_container, width=260)
        self.search_header_frame = ctk.CTkFrame(self.search_panel_frame, fg_color="transparent")
        self.search_header_frame.pack(fill="x", padx=10, pady=(10, 2))

        self.lbl_search_title = ctk.CTkLabel(
            self.search_header_frame,
            text="⚡ 초고속 검색 Engine",
            font=("Malgun Gothic", 12, "bold"),
            text_color="#2b73b8",
        )
        self.lbl_search_title.pack(side="left", padx=5)

        self.btn_close_search = ctk.CTkButton(
            self.search_header_frame,
            text="✕",
            width=22,
            height=22,
            fg_color="transparent",
            hover_color="#ff4444",
            text_color="#aaaaaa",
            font=("Malgun Gothic", 11, "bold"),
            command=self.toggle_search_panel,
        )
        self.btn_close_search.pack(side="right", padx=5)

        self.search_ctrl_frame = ctk.CTkFrame(self.search_panel_frame, fg_color="transparent")
        self.search_ctrl_frame.pack(fill="x", padx=10, pady=2)

        self.entry_search = ctk.CTkEntry(
            self.search_ctrl_frame,
            placeholder_text="검색 키워드/정규식 입력...",
            font=("Malgun Gothic", 12),
            height=28,
        )
        self.entry_search.pack(side="left", fill="x", expand=True, padx=(5, 5))
        self.entry_search.bind("<Return>", lambda event: self.start_search_thread())

        self.btn_search = ctk.CTkButton(
            self.search_ctrl_frame,
            text="검색",
            width=50,
            height=28,
            font=("Malgun Gothic", 11, "bold"),
            command=self.start_search_thread,
        )
        self.btn_search.pack(side="right", padx=(0, 5))

        self.search_options_frame = ctk.CTkFrame(self.search_panel_frame, fg_color="transparent")
        self.search_options_frame.pack(fill="x", padx=15, pady=(2, 2))

        self.use_regex_var = ctk.BooleanVar(value=False)
        self.chk_use_regex = ctk.CTkCheckBox(
            self.search_options_frame,
            text="정규식 (Regex)",
            variable=self.use_regex_var,
            font=("Malgun Gothic", 11),
            checkbox_width=18,
            checkbox_height=18,
            border_width=2,
        )
        self.chk_use_regex.pack(side="left")

        self.nav_frame = ctk.CTkFrame(self.search_panel_frame, fg_color="transparent")
        self.nav_frame.pack(fill="x", padx=10, pady=2)

        self.btn_prev = ctk.CTkButton(
            self.nav_frame,
            text="◀ 이전",
            height=26,
            font=("Malgun Gothic", 11),
            command=self.select_prev,
        )
        self.btn_prev.pack(side="left", fill="x", expand=True, padx=5)

        self.btn_next = ctk.CTkButton(
            self.nav_frame,
            text="다음 ▶",
            height=26,
            font=("Malgun Gothic", 11),
            command=self.select_next,
        )
        self.btn_next.pack(side="right", fill="x", expand=True, padx=5)

        self.lbl_search_status = ctk.CTkLabel(
            self.search_panel_frame,
            text="검색 전입니다.",
            font=("Malgun Gothic", 11),
            text_color="#aaaaaa",
        )
        self.lbl_search_status.pack(fill="x", padx=15, pady=(2, 0))

        self.lbl_limit_info = ctk.CTkLabel(
            self.search_panel_frame,
            text="",
            text_color="#ffcc00",
            font=("Malgun Gothic", 10),
            anchor="w",
        )
        self.lbl_limit_info.pack(fill="x", padx=15, pady=(0, 2))

        self.search_list_frame = ctk.CTkFrame(self.search_panel_frame, fg_color="transparent")
        self.search_list_frame.pack(fill="both", expand=True, padx=15, pady=(2, 12))

        self.result_listbox = tk.Listbox(
            self.search_list_frame,
            bg="#1e1e1e",
            fg="#a9b7c6",
            selectbackground="#1d5287",
            selectforeground="#ffffff",
            font=("Consolas", 12, "bold"),
            bd=0,
            highlightthickness=1,
            highlightcolor="#2b73b8",
            highlightbackground="#333333",
            justify="center",
        )
        self.result_listbox.pack(side="left", fill="both", expand=True)
        self.result_listbox.bind("<Double-Button-1>", self.on_search_result_double_click)

        self.list_scrollbar = ttk.Scrollbar(
            self.search_list_frame,
            orient="vertical",
            command=self.result_listbox.yview,
            style="Dark.Vertical.TScrollbar",
        )
        self.list_scrollbar.pack(side="right", fill="y")
        self.result_listbox.config(yscrollcommand=self.list_scrollbar.set)

        self.search_match_lines = []

        self.bind("<Control-f>", lambda event: self.toggle_search_panel())
        self.bind("<Control-F>", lambda event: self.toggle_search_panel())

    def _on_text_drag_start(self, event):
        self.is_selecting = True

    def _on_text_drag_end(self, event):
        self.is_selecting = False

    def stop_following(self):
        self.is_following = False
        if self.follow_timer is not None:
            self.after_cancel(self.follow_timer)
            self.follow_timer = None

    def start_following(self):
        self.stop_following()
        self.is_following = True
        self.check_file_updates()

    def check_file_updates(self):
        if not self.is_following or not self.file_path or not os.path.exists(self.file_path):
            return

        try:
            current_size = os.path.getsize(self.file_path)
            if current_size > self.last_known_file_size:
                self._incremental_index_for_follow(current_size)
            elif current_size < self.last_known_file_size:
                self._reindex_file_for_follow()
            else:
                # 2번: 스마트 스크롤 제어 (사용자가 맨 아래 근처를 보고 있을 때만 스크롤 고정)
                scroll_pos = self.v_scrollbar.get()
                if scroll_pos[1] >= 0.90:
                    self.apply_tab_filter()
        except Exception as e:
            print(f"Follow check error: {e}")

        if self.is_following and self.winfo_exists():
            self.follow_timer = self.after(500, self.check_file_updates)

    def _incremental_index_for_follow(self, current_size):
        if self.is_indexing:
            return

        def worker():
            try:
                self.is_indexing = True
                old_size = self.last_known_file_size
                self.last_known_file_size = current_size

                with open(self.file_path, "rb") as f:
                    f.seek(old_size)
                    new_bytes = f.read(current_size - old_size)

                added_offsets = []
                pos = 0
                while True:
                    idx = new_bytes.find(b"\n", pos)
                    if idx == -1:
                        break
                    added_offsets.append(old_size + idx + 1)
                    pos = idx + 1

                if RUST_AVAILABLE and self.rust_core is not None:
                    with self.rust_lock:
                        self.total_lines = self.rust_core.index_file(self.file_path, None)
                else:
                    self.line_offsets.extend(added_offsets)
                    self.total_lines = len(self.line_offsets)

                if self.mmap_obj is not None:
                    try:
                        self.mmap_obj.close()
                    except Exception:
                        pass
                if self.file_handle is not None:
                    try:
                        self.file_handle.close()
                    except Exception:
                        pass

                self.file_handle = open(self.file_path, "rb")
                self.mmap_obj = mmap.mmap(self.file_handle.fileno(), 0, access=mmap.ACCESS_READ)

                if self.winfo_exists():
                    # 2번: 스마트 스크롤 제어 적용
                    scroll_pos = self.v_scrollbar.get()
                    if scroll_pos[1] >= 0.90:
                        self.after(0, self.apply_tab_filter)
            except Exception as e:
                print(f"Incremental follow error: {e}")
            finally:
                self.is_indexing = False

        threading.Thread(target=worker, daemon=True).start()

    def _reindex_file_for_follow(self):
        if self.is_indexing:
            return

        def worker():
            try:
                self.is_indexing = True
                if self.mmap_obj is not None:
                    try:
                        self.mmap_obj.close()
                    except Exception:
                        pass
                    self.mmap_obj = None

                self.last_known_file_size = os.path.getsize(self.file_path)

                if RUST_AVAILABLE and self.rust_core is not None:
                    with self.rust_lock:
                        self.total_lines = self.rust_core.index_file(self.file_path, None)
                else:
                    self.line_offsets = [0]
                    file_pos = 0
                    with open(self.file_path, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                        while True:
                            idx = mm.find(b"\n", file_pos)
                            if idx == -1:
                                break
                            next_pos = idx + 1
                            self.line_offsets.append(next_pos)
                            file_pos = next_pos
                    self.total_lines = len(self.line_offsets)

                if self.file_handle is not None:
                    try:
                        self.file_handle.close()
                    except Exception:
                        pass

                self.file_handle = open(self.file_path, "rb")
                self.mmap_obj = mmap.mmap(self.file_handle.fileno(), 0, access=mmap.ACCESS_READ)

                if self.winfo_exists():
                    self.after(0, self.apply_tab_filter)
            except Exception as e:
                print(f"Reindex follow error: {e}")
            finally:
                self.is_indexing = False

        threading.Thread(target=worker, daemon=True).start()

    def _close_mmap(self):
        self.stop_following()
        if self.mmap_obj is not None:
            try:
                self.mmap_obj.close()
            except Exception:
                pass
            self.mmap_obj = None
        if self.file_handle is not None:
            try:
                self.file_handle.close()
            except Exception:
                pass
            self.file_handle = None

        self.line_offsets = []
        self.total_lines = 0
        self.current_start_line = 0
        self.filter_start = None
        self.filter_end = None

    def destroy(self):
        self.stop_following()
        if self.resize_timer is not None:
            self.after_cancel(self.resize_timer)
        self._close_mmap()
        super().destroy()

    def _auto_detect_encoding(self, file_path):
        try:
            with open(file_path, "rb") as f:
                raw = f.read(1024 * 64)
                if not raw or raw.startswith(b"\xef\xbb\xbf"):
                    return "utf-8"
                if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
                    return "utf-16"

                for enc in ["utf-8", "cp949", "ascii"]:
                    try:
                        raw.decode(enc)
                        return enc
                    except UnicodeDecodeError:
                        continue
        except Exception:
            pass
        return "utf-8"

    def _get_selected_encoding(self):
        choice = self.encoding_var.get()
        if "[자동 감지" in choice:
            return self.detected_encoding
        if "CP949" in choice:
            return "cp949"
        elif "UTF-16" in choice:
            return "utf-16"
        elif "ASCII" in choice:
            return "ascii"
        return "utf-8"

    def _move_selection(self, idx):
        if idx < 0 or idx >= self.result_listbox.size():
            return
        self.result_listbox.select_clear(0, "end")
        self.result_listbox.select_set(idx)
        self.result_listbox.activate(idx)
        self.result_listbox.see(idx)

        target_line = self.search_match_lines[idx]
        keyword = self.entry_search.get().strip()
        use_regex = self.use_regex_var.get()
        self.render_view(max(0, target_line - 2), keyword, use_regex=use_regex)

    def select_prev(self):
        current = self.result_listbox.curselection()
        if current:
            new_idx = max(0, current[0] - 1)
            self._move_selection(new_idx)

    def select_next(self):
        current = self.result_listbox.curselection()
        size = self.result_listbox.size()
        if current:
            new_idx = min(size - 1, current[0] + 1)
            self._move_selection(new_idx)

    def setup_dark_scrollbar_style(self):
        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except Exception:
            pass
        self.style.configure(
            "Dark.Vertical.TScrollbar",
            gripcount=0,
            background="#3a3a3a",
            troughcolor="#1e1e1e",
            bordercolor="#2b2b2b",
            arrowcolor="#aaaaaa",
            lightcolor="#3a3a3a",
            darkcolor="#3a3a3a",
        )
        self.style.map("Dark.Vertical.TScrollbar", background=[("active", "#4f4f4f")])

    def setup_custom_dark_menu(self):
        self.menu_bar = ctk.CTkFrame(self, height=32, corner_radius=0, fg_color="#1e1e1e", border_width=0)
        self.menu_bar.pack(fill="x", side="top")

        self.menu_sep = ctk.CTkFrame(self, height=1, corner_radius=0, fg_color="#2b2b2b")
        self.menu_sep.pack(fill="x", side="top")

        self.menu_file_btn = ctk.CTkButton(
            self.menu_bar,
            text="파일(F)",
            font=("Malgun Gothic", 11),
            width=55,
            height=26,
            fg_color="transparent",
            hover_color="#2d2d2d",
            text_color="#ffffff",
        )
        self.menu_file_btn.pack(side="left", padx=(10, 2), pady=3)

        self.menu_tools_btn = ctk.CTkButton(
            self.menu_bar,
            text="도구(T)",
            font=("Malgun Gothic", 11),
            width=55,
            height=26,
            fg_color="transparent",
            hover_color="#2d2d2d",
            text_color="#ffffff",
        )
        self.menu_tools_btn.pack(side="left", padx=2, pady=3)

        file_items = [
            {"label": "파일 열기...", "command": self.start_open_file_thread},
            {"label": "파일 닫기", "command": self.close_file},
            "separator",
            {"label": "종료", "command": self.quit},
        ]

        tools_items = [
            {"label": "검색 패널 열기/닫기 (Ctrl + F)", "command": self.toggle_search_panel},
            "separator",
            {
                "label": "지정 용량(MB)으로 파일 분할 내보내기...",
                "command": self.popup_split_dialog,
            },
            {"label": "여러 텍스트 파일 하나로 합치기...", "command": self.popup_merge_dialog},
        ]

        self.file_dropdown_custom = CTkCustomMenu(self, self, file_items)
        self.tools_dropdown_custom = CTkCustomMenu(self, self, tools_items)

        self.menu_file_btn.bind("<Button-1>", lambda event: self._toggle_file_menu())
        self.menu_tools_btn.bind("<Button-1>", lambda event: self._toggle_tools_menu())

    def _toggle_file_menu(self):
        if self.file_dropdown_custom.winfo_manager():
            self.file_dropdown_custom.hide()
        else:
            if self.tools_dropdown_custom.winfo_manager():
                self.tools_dropdown_custom.hide()
            x = self.menu_file_btn.winfo_x()
            y = self.menu_file_btn.winfo_y() + self.menu_file_btn.winfo_height() + 2
            self.file_dropdown_custom.show(x, y)

    def _toggle_tools_menu(self):
        if self.tools_dropdown_custom.winfo_manager():
            self.tools_dropdown_custom.hide()
        else:
            if self.file_dropdown_custom.winfo_manager():
                self.file_dropdown_custom.hide()
            x = self.menu_tools_btn.winfo_x()
            y = self.menu_tools_btn.winfo_y() + self.menu_tools_btn.winfo_height() + 2
            self.tools_dropdown_custom.show(x, y)

    def toggle_search_panel(self):
        if not self.file_path:
            messagebox.showinfo("안내", "파일을 먼저 열어주세요.")
            return
        self._force_close_search_panel()

    def _force_close_search_panel(self):
        if self.search_panel_visible:
            self.search_panel_frame.pack_forget()
            self.main_container.pack_configure(padx=0)
            self.search_panel_visible = False
        else:
            self.main_container.pack_configure(padx=(0, 5))
            self.search_panel_frame.pack(side="right", fill="both", expand=False, padx=(5, 0))

            self.entry_search.delete(0, "end")
            self.result_listbox.delete(0, "end")
            self.lbl_search_status.configure(text="검색 전입니다.", text_color="#aaaaaa")
            self.search_match_lines = []

            self.search_panel_visible = True
            self.entry_search.focus()

    def start_search_thread(self):
        if not self.file_path or self.is_indexing or self.is_searching:
            return

        keyword = self.entry_search.get().strip()
        if not keyword:
            messagebox.showwarning("검색 경고", "검색할 내용을 입력해 주세요.")
            return

        use_regex = self.use_regex_var.get()

        self.is_searching = True
        self.btn_search.configure(state="disabled")
        search_type_lbl = "정규식" if use_regex else "SIMD"
        self.lbl_search_status.configure(text=f"{search_type_lbl} 가속 검색 중...", text_color="#ffcc00")
        self.result_listbox.delete(0, "end")
        self.search_match_lines = []

        self.view_mode_var.set("전체보기 (FULL)")
        self.toggle_tab_options(show=False)
        self.filter_start = 0
        self.filter_end = self.total_lines

        t = threading.Thread(
            target=self.search_keyword_worker,
            args=(keyword, use_regex),
            daemon=True,
        )
        t.start()

    def search_keyword_worker(self, keyword, use_regex):
        matches = []
        line_indices = []
        total_found = 0
        enc = self._get_selected_encoding()
        mm = self.mmap_obj

        if mm is None or self.total_lines == 0:
            self.is_searching = False
            if self.winfo_exists():
                self.after(0, lambda: self.btn_search.configure(state="normal"))
            return

        try:
            if RUST_AVAILABLE and self.rust_core is not None:
                try:
                    rust_pattern = keyword.encode(enc, errors="ignore")
                    with self.rust_lock:
                        matches, line_indices, total_found = self.rust_core.search_keyword(rust_pattern, use_regex)

                    if self.winfo_exists():
                        self.after(
                            0,
                            lambda: self.on_complete_search_ui(matches, line_indices, total_found),
                        )
                    return
                except Exception as rust_err:
                    print(f"[디버그] Rust 검색 예외 발생, 파이썬 모드로 전환: {rust_err}")
                    traceback.print_exc()

            k_bytes = keyword.encode(enc, errors="ignore")
            matched_offsets = []
            file_size = mm.size()

            if use_regex:
                try:
                    pattern_re = re.compile(k_bytes, re.MULTILINE)
                    for m in pattern_re.finditer(mm):
                        matched_offsets.append(m.start())
                        if len(matched_offsets) >= 2000:
                            break
                except re.error:
                    if self.winfo_exists():
                        self.after(
                            0,
                            lambda: messagebox.showerror(
                                "정규식 오류",
                                "올바르지 않은 정규식 패턴입니다.",
                            ),
                        )
                    self.after(0, lambda: self.btn_search.configure(state="normal"))
                    self.is_searching = False
                    return
            else:
                search_pos = 0
                while search_pos < file_size:
                    if self.mmap_obj is None:
                        break
                    pos = mm.find(k_bytes, search_pos)
                    if pos == -1:
                        break
                    matched_offsets.append(pos)
                    search_pos = pos + len(k_bytes)
                    if len(matched_offsets) >= 2000:
                        break

            if matched_offsets:
                last_line_idx = -1
                for offset in matched_offsets:
                    line_idx = bisect.bisect_right(self.line_offsets, offset) - 1
                    if line_idx != last_line_idx:
                        total_found += 1
                        if len(matches) < 2000:
                            matches.append(f"Line {line_idx + 1:,}")
                            line_indices.append(line_idx)
                        last_line_idx = line_idx

        except Exception as e:
            print(f"Search exception: {e}")

        if self.winfo_exists():
            self.after(0, lambda: self.on_complete_search_ui(matches, line_indices, total_found))

    def on_complete_search_ui(self, matches, line_indices, total_found):
        self.search_match_lines = line_indices
        self.result_listbox.delete(0, "end")

        for item in matches:
            self.result_listbox.insert("end", item)

        if total_found > 0:
            self.lbl_search_status.configure(
                text=f"검색 완료: {total_found:,}건" + (" [최대 2,000까지 조회]" if total_found >= 2000 else ""),
                text_color="#27ae60",
            )
            if total_found > 2000:
                self.lbl_limit_info.configure(text="※ 화면은 2,000개까지만 표시됩니다.")
            else:
                self.lbl_limit_info.configure(text="")
            self.result_listbox.focus_set()
            if self.result_listbox.size() > 0:
                self.result_listbox.select_set(0)
        else:
            self.lbl_search_status.configure(text="결과 없음", text_color="#ff4444")
            self.lbl_limit_info.configure(text="")

        self.btn_search.configure(state="normal")
        self.is_searching = False

    def on_search_result_double_click(self, event):
        selection = self.result_listbox.curselection()
        if not selection:
            return

        list_idx = selection[0]
        target_line = self.search_match_lines[list_idx]
        keyword = self.entry_search.get().strip()
        use_regex = self.use_regex_var.get()

        self.view_mode_var.set("전체보기 (FULL)")
        self.toggle_tab_options(show=False)
        self.filter_start = 0
        self.filter_end = self.total_lines
        self.current_start_line = max(0, target_line - 2)

        self.set_scroll_bar_position(self.current_start_line)
        self.render_view(self.current_start_line, highlight_keyword=keyword, use_regex=use_regex)

    def toggle_tab_options(self, show=True):
        if show:
            self.tab_option_frame.pack(side="left", fill="y", padx=10)
        else:
            self.tab_option_frame.pack_forget()

    def on_tab_changed(self, choice):
        if not self.file_path:
            return

        if "FOLLOW" in choice:
            self.toggle_tab_options(show=True)
            self.start_following()
        else:
            self.stop_following()
            if "FULL" in choice:
                self.toggle_tab_options(show=False)
                self.reset_to_full_view()
            else:
                self.toggle_tab_options(show=True)
                self.apply_tab_filter()

    def apply_tab_filter(self):
        if not self.file_path or self.total_lines == 0:
            return
        try:
            count = int(self.entry_filter_lines.get())
            if count <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("입력 오류", "줄 수는 1 이상의 양의 정수로 입력해야 합니다.")
            return

        choice = self.view_mode_var.get()
        if "HEAD" in choice:
            self.filter_start = 0
            self.filter_end = min(count, self.total_lines)
            # HEAD 모드는 맨 위(Top)부터 시작
            self.current_start_line = self.filter_start
        elif "TAIL" in choice or "FOLLOW" in choice:
            self.filter_start = max(0, self.total_lines - count)
            self.filter_end = self.total_lines
            # TAIL / FOLLOW 모드는 화면 크기를 고려해 맨 아래(Bottom)가 보이도록 시작 줄 설정
            self.current_start_line = max(self.filter_start, self.filter_end - self.max_visible_lines)

        self.set_scroll_bar_position(self.current_start_line)
        self.render_view(self.current_start_line)

    def reset_to_full_view(self):
        self.filter_start = 0
        self.filter_end = self.total_lines
        self.current_start_line = 0
        self.set_scroll_bar_position(0)
        self.render_view(0)

    def start_open_file_thread(self):
        if self.is_indexing or self.is_searching or self.is_splitting or self.is_merging:
            return
        file_selected = filedialog.askopenfilename(
            title="대용량 텍스트 파일 선택",
            filetypes=[("All files", "*.*"), ("Text/Log files", "*.txt;*.log;*.csv;*.json;*.tsv")],
        )
        if not file_selected:
            return

        self.tab_panel_frame.pack_forget()
        if self.search_panel_visible:
            self._force_close_search_panel()

        self._close_mmap()
        self.file_path = file_selected
        self.last_known_file_size = os.path.getsize(file_selected)

        if "[자동 감지" in self.encoding_var.get():
            self.lbl_file.configure(text="인코딩 속성 분석 중...", text_color="#ffcc00")
            self.detected_encoding = self._auto_detect_encoding(file_selected)

        filename = os.path.basename(file_selected)
        filesize_bytes = self.last_known_file_size
        self.filesize_text = (
            f"{filesize_bytes / (1024 * 1024):.2f} MB" if filesize_bytes < 1024 * 1024 * 1024 else f"{filesize_bytes / (1024 * 1024 * 1024):.2f} GB"
        )

        self.lbl_file.configure(text=f"파일 구조 분석 중...: {filename} ({self.filesize_text})", text_color="#ffcc00")
        self.btn_open.configure(state="disabled")
        self.btn_close.pack_forget()
        self.combo_encoding.configure(state="disabled")
        self.is_indexing = True

        t = threading.Thread(target=self.index_file_worker, daemon=True)
        t.start()

    def index_file_worker(self):
        try:
            file_size = os.path.getsize(self.file_path)
            if file_size == 0:
                self.total_lines = 0
                if self.winfo_exists():
                    self.after(0, self.on_indexing_complete)
                return

            if RUST_AVAILABLE and self.rust_core is not None:
                try:
                    self.current_engine_used_rust = True
                    if self.winfo_exists():
                        self.after(
                            0,
                            lambda: self.lbl_file.configure(
                                text=f"인덱싱 중... 0% (0 줄 발견) — {os.path.basename(self.file_path)} (Rust 가속)",
                                text_color="#ffcc00",
                            ),
                        )

                    def rust_progress_callback(pct, line_count):
                        if self.winfo_exists():
                            self.after(
                                0,
                                lambda p=pct, n=line_count: self._update_index_progress(p, n, is_rust=True),
                            )

                    with self.rust_lock:
                        self.total_lines = self.rust_core.index_file(self.file_path, rust_progress_callback)

                    self.file_handle = open(self.file_path, "rb")
                    self.mmap_obj = mmap.mmap(self.file_handle.fileno(), 0, access=mmap.ACCESS_READ)

                    if self.winfo_exists():
                        self.after(0, self.on_indexing_complete)
                    return
                except Exception as rust_err:
                    print(f"[디버그] Rust 인덱싱 코어 예외 발생, 파이썬 모드로 전환: {rust_err}")
                    traceback.print_exc()

            self.current_engine_used_rust = False
            self.line_offsets = [0]
            self.file_handle = open(self.file_path, "rb")
            self.mmap_obj = mmap.mmap(self.file_handle.fileno(), 0, access=mmap.ACCESS_READ)
            mm = self.mmap_obj

            initial_shown = False
            file_pos = 0
            while True:
                if self.mmap_obj is None:
                    break

                idx = mm.find(b"\n", file_pos)
                if idx == -1:
                    break

                next_pos = idx + 1
                self.line_offsets.append(next_pos)
                file_pos = next_pos

                if not initial_shown and len(self.line_offsets) >= 100:
                    self.total_lines = len(self.line_offsets)
                    initial_shown = True
                    if self.winfo_exists():
                        self.after(0, self._show_progressive_content)

            self.total_lines = len(self.line_offsets)
            if self.winfo_exists():
                self.after(0, self.on_indexing_complete)
        except Exception as err:
            err_msg = str(err)
            if self.winfo_exists():
                self.after(
                    0,
                    lambda: messagebox.showerror("오류", f"분석 중 오류 발생:\n{err_msg}"),
                )
                self.after(0, self.reset_open_button)
        finally:
            self.is_indexing = False

    def _update_index_progress(self, pct, line_count, is_rust=False):
        if not self.winfo_exists():
            return
        filename = os.path.basename(self.file_path)
        enc_lbl = f"Auto:{self.detected_encoding.upper()}" if "[자동 감지" in self.encoding_var.get() else self.encoding_var.get()
        mode_label = " (Rust 가속)" if is_rust else " (파이썬 모드)"

        self.lbl_file.configure(
            text=f"인덱싱 중... {pct}% ({line_count:,} 줄 발견) — {filename}{mode_label} [{enc_lbl}]",
            text_color="#ffcc00",
        )

    def _show_progressive_content(self):
        if not self.winfo_exists():
            return
        self.tab_panel_frame.pack(fill="x", padx=15, pady=5, after=self.top_frame)
        self.view_mode_var.set("전체보기 (FULL)")
        self.toggle_tab_options(show=False)
        self.filter_start = 0
        self.filter_end = self.total_lines
        self.current_start_line = 0
        self.set_scroll_bar_position(0)
        self.render_view(0)

    def on_indexing_complete(self):
        filename = os.path.basename(self.file_path)
        enc_lbl = f"Auto:{self.detected_encoding.upper()}" if "[자동 감지" in self.encoding_var.get() else self.encoding_var.get()
        mode_label = " (Rust 가속 완료)" if self.current_engine_used_rust else " (파이썬 완료)"

        self.lbl_file.configure(
            text=f"선택됨: {filename} ({self.filesize_text}) (총 {self.total_lines:,} 줄 인덱싱 완료){mode_label} — [{enc_lbl}]",
            text_color="#ffffff",
        )
        self.btn_open.configure(state="normal")
        self.btn_close.pack(side="left", padx=(0, 5), pady=10, after=self.btn_open)
        self.combo_encoding.configure(state="normal")

        try:
            self.tab_panel_frame.pack_info()
        except tk.TclError:
            self.tab_panel_frame.pack(fill="x", padx=15, pady=5, after=self.top_frame)

        self.filter_start = 0
        self.filter_end = self.total_lines
        self.view_mode_var.set("전체보기 (FULL)")
        self.toggle_tab_options(show=False)
        self.set_scroll_bar_position(self.current_start_line)
        self.render_view(self.current_start_line)

    def reset_open_button(self):
        self.lbl_file.configure(text="파일 로드에 실패했습니다.", text_color="#ff4444")
        self.btn_open.configure(state="normal")
        self.btn_close.pack_forget()
        self.combo_encoding.configure(state="normal")
        self.tab_panel_frame.pack_forget()
        if self.search_panel_visible:
            self._force_close_search_panel()

    def close_file(self):
        if self.is_indexing or self.is_searching or self.is_splitting or self.is_merging:
            messagebox.showwarning("경고", "작업이 진행 중일 때는 파일을 닫을 수 없습니다.")
            return

        if self.search_panel_visible:
            self._force_close_search_panel()

        self._close_mmap()
        self.file_path = ""
        self.filesize_text = ""

        self.tab_panel_frame.pack_forget()

        self.text_area.configure(state="normal")
        self.text_area.delete("1.0", "end")
        self.text_area.configure(state="disabled")

        self.lbl_content_title.configure(text="FILE CONTENTS (0 / 0 줄)")
        self.lbl_file.configure(
            text="선택된 파일이 없습니다. 인코딩을 지정하고 [파일 열기] 버튼을 누르세요.",
            text_color="#aaaaaa",
        )
        self.v_scrollbar.set(0.0, 1.0)
        self.btn_close.pack_forget()

    def update_visible_count(self, event=None):
        if self.resize_timer is not None:
            self.after_cancel(self.resize_timer)
        self.resize_timer = self.after(150, self._deferred_update_visible_count)

    def _deferred_update_visible_count(self):
        if not self.winfo_exists():
            return
        line_height = 13 + 8 + 4
        widget_height = self.text_area.winfo_height()
        if widget_height > 20:
            self.max_visible_lines = (widget_height // line_height) + 1
            if self.file_path and self.total_lines > 0:
                self.render_view(self.current_start_line)
                self.set_scroll_bar_position(self.current_start_line)

    def render_view(self, start_line, highlight_keyword=None, use_regex=False):
        if not self.file_path or self.total_lines == 0 or self.mmap_obj is None:
            return

        if self.is_indexing:
            return

        # 1번: 드래그 영역 선택 중일 경우 렌더링 스킵하여 화면 튐 방지
        if getattr(self, "is_selecting", False):
            return

        f_start = self.filter_start if self.filter_start is not None else 0
        f_end = self.filter_end if self.filter_end is not None else self.total_lines
        total_filtered_lines = f_end - f_start

        max_scroll_limit = max(f_start, f_end - self.max_visible_lines)
        start_line = max(f_start, min(start_line, max_scroll_limit))
        self.current_start_line = start_line
        end_line = min(start_line + self.max_visible_lines, f_end)

        if self.is_following:
            title_text = f"MAIN VIEWER [실시간 추적 (FOLLOW)] ({start_line + 1 - f_start:,} ~ {end_line - f_start:,} 줄 표시)"
        elif total_filtered_lines == self.total_lines:
            title_text = f"MAIN VIEWER ({start_line + 1:,} ~ {end_line:,} 줄) [전체보기]"
        else:
            mode_name = "HEAD 필터" if f_start == 0 else "TAIL 필터"
            title_text = f"MAIN VIEWER [{mode_name}] ({start_line + 1 - f_start:,} ~ {end_line - f_start:,} 줄 표시)"
        self.lbl_content_title.configure(text=title_text)

        self.text_area.configure(state="normal")
        self.text_area.delete("1.0", "end")

        enc = self._get_selected_encoding()
        mm = self.mmap_obj

        try:
            file_size = mm.size()
            text_parts = []
            count = end_line - start_line

            if self.current_engine_used_rust and self.rust_core is not None:
                with self.rust_lock:
                    offsets = self.rust_core.get_offsets_range(start_line, count + 1)
            else:
                offsets = self.line_offsets[start_line : start_line + count + 1]

            for i in range(count):
                idx = start_line + i
                start_offset = offsets[i] if i < len(offsets) else 0
                end_offset = offsets[i + 1] if (i + 1) < len(offsets) else file_size

                line_data = mm[start_offset:end_offset]
                decoded_line = line_data.decode(enc, errors="ignore")
                text_parts.append(f"{idx + 1:>7} | {decoded_line}")

            full_text = "".join(text_parts)
            self.text_area.insert("end", full_text)

            if highlight_keyword:
                self.text_area.tag_config("highlight", background="#d4d420", foreground="#000000")
                search_start = "1.0"

                while True:
                    match_count = tk.IntVar()
                    pos = self.text_area.search(
                        highlight_keyword,
                        search_start,
                        stopindex="end",
                        nocase=False,
                        regexp=use_regex,
                        count=match_count,
                    )
                    if not pos:
                        break

                    kw_len = match_count.get()
                    if kw_len <= 0:
                        kw_len = 1

                    self.text_area.tag_add("highlight", pos, f"{pos}+{kw_len}c")
                    search_start = f"{pos}+{kw_len}c"

            self.text_area.configure(state="disabled")
        except Exception as e:
            print(f"Render error: {e}")

    def popup_split_dialog(self):
        if not self.file_path or self.is_indexing or self.is_splitting:
            messagebox.showwarning("경고", "먼저 분석 완료된 파일이 존재해야 하며 진행 중인 분할 작업이 없어야 합니다.")
            return
        dialog = ctk.CTkToplevel(self)
        dialog.title("용량별 파일 분할")
        dialog.geometry("400x200")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog,
            text="[파일 용량별 분할 내보내기]",
            font=("Malgun Gothic", 14, "bold"),
            text_color="#2b73b8",
        ).pack(pady=(20, 5))
        frame_input = ctk.CTkFrame(dialog, fg_color="transparent")
        frame_input.pack(pady=10)
        ctk.CTkLabel(frame_input, text="분할할 단위 용량 :", font=("Malgun Gothic", 12)).pack(side="left", padx=5)
        entry_size = ctk.CTkEntry(frame_input, width=90, justify="center")
        entry_size.insert(0, "100")
        entry_size.pack(side="left", padx=5)
        ctk.CTkLabel(frame_input, text="MB", font=("Malgun Gothic", 12, "bold")).pack(side="left", padx=5)

        def run_split():
            try:
                size_mb = float(entry_size.get())
                if size_mb <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("입력 오류", "올바른 분할 용량(MB)을 입력하세요.", parent=dialog)
                return
            dialog.destroy()

            save_dir = filedialog.askdirectory(title="분할된 파일들이 저장될 폴더 선택")
            if not save_dir:
                return

            self.is_splitting = True
            self.lbl_file.configure(text="파일 분할 내보내기 진행 중...", text_color="#ffcc00")
            self.popup_progress_window("파일 분할 작업 진행률", "파일 분할 중입니다. 잠시만 기다려주세요...")

            t = threading.Thread(target=self.split_file_worker, args=(size_mb, save_dir), daemon=True)
            t.start()

        ctk.CTkButton(
            dialog,
            text="저장 폴더 선택 후 분할 시작",
            font=("Malgun Gothic", 12, "bold"),
            fg_color="#27ae60",
            hover_color="#1e8449",
            command=run_split,
        ).pack(pady=15)

    def popup_progress_window(self, title_text, msg_text):
        self.prog_win = ctk.CTkToplevel(self)
        self.prog_win.title(title_text)
        self.prog_win.geometry("450x160")
        self.prog_win.resizable(False, False)
        self.prog_win.transient(self)
        self.prog_win.grab_set()

        self.prog_lbl_msg = ctk.CTkLabel(self.prog_win, text=msg_text, font=("Malgun Gothic", 12))
        self.prog_lbl_msg.pack(pady=(20, 5), padx=20, fill="x")

        self.prog_bar = ctk.CTkProgressBar(self.prog_win, width=380)
        self.prog_bar.set(0.0)
        self.prog_bar.pack(pady=10, padx=20)

        self.prog_lbl_pct = ctk.CTkLabel(self.prog_win, text="준비 중... (0%)", font=("Malgun Gothic", 11, "bold"))
        self.prog_lbl_pct.pack(pady=(0, 10))

    def _update_progress_ui(self, float_val, status_text):
        if hasattr(self, "prog_win") and self.prog_win.winfo_exists():
            self.prog_bar.set(float_val)
            self.prog_lbl_pct.configure(text=status_text)

    def _close_progress_ui(self):
        if hasattr(self, "prog_win") and self.prog_win.winfo_exists():
            self.prog_win.destroy()

    def split_file_worker(self, size_mb, save_dir):
        target_chunk_bytes = int(size_mb * 1024 * 1024)
        file_total_size = os.path.getsize(self.file_path)

        if target_chunk_bytes >= file_total_size:
            if self.winfo_exists():
                self.after(0, self._close_progress_ui)
                self.after(
                    0,
                    lambda: messagebox.showwarning("경고", "입력한 분할 용량이 원본 파일의 전체 크기보다 크거나 같습니다."),
                )
                self.after(0, lambda: self._on_split_complete(False))
            return

        base_filename = os.path.splitext(os.path.basename(self.file_path))[0]
        ext = os.path.splitext(os.path.basename(self.file_path))[1] or ".txt"
        success_flag = False

        try:
            with open(self.file_path, "rb") as f_src:
                part_num = 1
                current_line_idx = 0
                total_offsets = self.total_lines

                last_ui_update_time = time.time()

                while current_line_idx < total_offsets - 1:
                    if self.mmap_obj is None:
                        break

                    if self.current_engine_used_rust and self.rust_core is not None:
                        with self.rust_lock:
                            start_offset = max(0, self.rust_core.get_offset(current_line_idx) or 0)
                    else:
                        start_offset = self.line_offsets[current_line_idx]

                    target_end_offset = start_offset + target_chunk_bytes
                    end_line_idx = current_line_idx

                    while end_line_idx < total_offsets - 1:
                        if self.current_engine_used_rust and self.rust_core is not None:
                            with self.rust_lock:
                                next_offset = max(start_offset, self.rust_core.get_offset(end_line_idx + 1) or 0)
                        else:
                            next_offset = self.line_offsets[end_line_idx + 1]

                        if next_offset > target_end_offset:
                            break
                        end_line_idx += 1

                    if end_line_idx == current_line_idx:
                        end_line_idx = min(current_line_idx + 1, total_offsets - 1)

                    if self.current_engine_used_rust and self.rust_core is not None:
                        with self.rust_lock:
                            actual_end_offset = max(
                                start_offset,
                                (self.rust_core.get_offset(end_line_idx) or file_total_size) if end_line_idx < total_offsets else file_total_size,
                            )
                    else:
                        actual_end_offset = self.line_offsets[end_line_idx] if end_line_idx < total_offsets else file_total_size

                    bytes_to_write = actual_end_offset - start_offset
                    if bytes_to_write <= 0:
                        break

                    part_filepath = os.path.join(save_dir, f"{base_filename}_part{part_num}{ext}")
                    f_src.seek(start_offset)
                    with open(part_filepath, "wb") as f_dst:
                        buffer_size = 1024 * 1024 * 16
                        written = 0
                        while written < bytes_to_write:
                            to_read = min(buffer_size, bytes_to_write - written)
                            chunk = f_src.read(to_read)
                            if not chunk:
                                break
                            f_dst.write(chunk)
                            written += len(chunk)
                    part_num += 1
                    current_line_idx = end_line_idx

                    current_time = time.time()
                    if current_time - last_ui_update_time >= 0.5:
                        pct_float = actual_end_offset / file_total_size
                        pct_text = f"분할 내보내기 중... {int(pct_float * 100)}% (Part {part_num - 1})"
                        if self.winfo_exists():
                            self.after(0, lambda f=pct_float, t=pct_text: self._update_progress_ui(f, t))
                        last_ui_update_time = current_time
                        time.sleep(0.001)

            success_flag = True
            if self.winfo_exists():
                self.after(
                    0,
                    lambda: messagebox.showinfo(
                        "분할 완료",
                        f"성공적으로 총 {part_num - 1}개의 파일로 분할 저장을 완료했습니다!\n저장 경로: {save_dir}",
                    ),
                )
        except Exception as e:
            err_msg = str(e)
            if self.winfo_exists():
                self.after(
                    0,
                    lambda: messagebox.showerror("분할 실패", f"파일을 분할하는 중 시스템 오류가 발생했습니다:\n{err_msg}"),
                )
        finally:
            if self.winfo_exists():
                self.after(0, self._close_progress_ui)
                self.after(0, lambda sf=success_flag: self._on_split_complete(sf))

    def _on_split_complete(self, success):
        self.is_splitting = False
        if not self.file_path:
            return
        filename = os.path.basename(self.file_path)
        enc_lbl = f"Auto:{self.detected_encoding.upper()}" if "[자동 감지" in self.encoding_var.get() else self.encoding_var.get()
        if success:
            mode_label = " (Rust 가속 완료)" if self.current_engine_used_rust else " (파이썬 완료)"
            self.lbl_file.configure(
                text=f"선택됨: {filename} ({self.filesize_text}) (총 {self.total_lines:,} 줄 인덱싱 완료){mode_label} — [{enc_lbl}]",
                text_color="#ffffff",
            )
        else:
            self.lbl_file.configure(text="파일 분할 처리에 실패했습니다.", text_color="#ff4444")

    def popup_merge_dialog(self):
        if self.is_indexing or self.is_splitting or self.is_merging:
            messagebox.showwarning("경고", "다른 파일 작업이 현재 진행 중입니다.")
            return

        files_selected = filedialog.askopenfilenames(
            title="하나로 합칠 여러 텍스트 파일 선택",
            filetypes=[("All files", "*.*"), ("Text/Log files", "*.txt;*.log;*.csv;*.json;*.tsv")],
        )
        if files_selected:
            files_selected = sorted(files_selected)
        if not files_selected or len(files_selected) < 2:
            messagebox.showwarning("안내", "최소 2개 이상의 파일을 선택해야 병합할 수 있습니다.")
            return

        save_file_path = filedialog.asksaveasfilename(
            title="합쳐진 최종 파일 저장 위치 선택",
            defaultextension=".txt",
            filetypes=[("All files", "*.*"), ("Text file", "*.txt"), ("Log file", "*.log")],
        )
        if not save_file_path:
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title("텍스트 파일 병합")
        dialog.geometry("420x220")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog,
            text="[여러 텍스트 파일 하나로 합치기]",
            font=("Malgun Gothic", 14, "bold"),
            text_color="#2b73b8",
        ).pack(pady=(20, 5))
        lbl_info = ctk.CTkLabel(
            dialog,
            text=f"선택한 {len(files_selected)}개의 파일을 아래 파일로 병합합니다:\n\n{os.path.basename(save_file_path)}",
            font=("Malgun Gothic", 11),
            justify="center",
        )
        lbl_info.pack(pady=10)

        def run_merge():
            dialog.destroy()
            self.is_merging = True
            self.lbl_file.configure(text="여러 텍스트 파일 병합 진행 중...", text_color="#ffcc00")
            self.popup_progress_window("파일 병합 작업 진행률", "파일을 순서대로 통합 병합 중입니다...")

            t = threading.Thread(target=self.merge_files_worker, args=(files_selected, save_file_path), daemon=True)
            t.start()

        ctk.CTkButton(
            dialog,
            text="파일 병합 시작",
            font=("Malgun Gothic", 12, "bold"),
            fg_color="#27ae60",
            hover_color="#1e8449",
            command=run_merge,
        ).pack(pady=10)

    def merge_files_worker(self, src_files, dst_file):
        success_flag = False
        total_files = len(src_files)
        try:
            with open(dst_file, "wb") as f_dst:
                last_ui_update_time = time.time()

                for idx, file_path in enumerate(src_files):
                    with open(file_path, "rb") as f_src:
                        buffer_size = 1024 * 1024 * 16
                        while True:
                            chunk = f_src.read(buffer_size)
                            if not chunk:
                                break
                            f_dst.write(chunk)

                    current_time = time.time()
                    if current_time - last_ui_update_time >= 0.5:
                        pct_float = (idx + 1) / total_files
                        pct_text = f"전체 {total_files}개 중 {idx + 1}개 파일 병합 완료 ({int(pct_float * 100)}%)"
                        if self.winfo_exists():
                            self.after(0, lambda f=pct_float, t=pct_text: self._update_progress_ui(f, t))
                        last_ui_update_time = current_time
                        time.sleep(0.001)

            success_flag = True
            if self.winfo_exists():
                self.after(
                    0,
                    lambda: messagebox.showinfo(
                        "병합 완료",
                        f"성공적으로 총 {len(src_files)}개의 파일을 하나로 합쳤습니다!\n파일 위치: {dst_file}",
                    ),
                )
        except Exception as e:
            err_msg = str(e)
            if self.winfo_exists():
                self.after(
                    0,
                    lambda: messagebox.showerror("병합 실패", f"파일을 합치는 도중 시스템 오류가 발생했습니다:\n{err_msg}"),
                )
        finally:
            if self.winfo_exists():
                self.after(0, self._close_progress_ui)
                self.after(0, lambda: self._on_merge_complete(success_flag))

    def _on_merge_complete(self, success):
        self.is_merging = False
        if not self.file_path:
            self.lbl_file.configure(
                text="선택된 파일이 없습니다. 인코딩을 지정하고 [파일 열기] 버튼을 누르세요.",
                text_color="#aaaaaa",
            )
            return
        filename = os.path.basename(self.file_path)
        enc_lbl = f"Auto:{self.detected_encoding.upper()}" if "[자동 감지" in self.encoding_var.get() else self.encoding_var.get()
        if success:
            mode_label = " (Rust 가속 완료)" if self.current_engine_used_rust else " (파이썬 완료)"
            self.lbl_file.configure(
                text=f"선택됨: {filename} ({self.filesize_text}) (총 {self.total_lines:,} 줄 인덱싱 완료){mode_label} — [{enc_lbl}]",
                text_color="#ffffff",
            )
        else:
            self.lbl_file.configure(text="파일 병합 처리에 실패했습니다.", text_color="#ff4444")

    def safe_select_all(self, event):
        if self.total_lines > 10000:
            messagebox.showwarning("선택 제한", "대용량 파일은 전체 선택을 지원하지 않습니다.")
            return "break"
        self.text_area.tag_add("sel", "1.0", "end")
        return "break"

    def safe_copy(self, event):
        try:
            selected_text = self.text_area.get("sel.first", "sel.last")
            if len(selected_text.encode("utf-8")) > 30 * 1024 * 1024:
                messagebox.showerror("복사 제한", "복사하려는 텍스트 용량이 너무 큽니다.")
                return "break"
            self.clipboard_clear()
            self.clipboard_append(selected_text)
        except Exception:
            pass
        return "break"

    def set_scroll_bar_position(self, start_line):
        f_start = self.filter_start if self.filter_start is not None else 0
        f_end = self.filter_end if self.filter_end is not None else self.total_lines
        total_filtered_lines = f_end - f_start
        if total_filtered_lines <= 0:
            return
        first = (start_line - f_start) / total_filtered_lines
        last = (start_line - f_start + self.max_visible_lines) / total_filtered_lines
        self.v_scrollbar.set(max(0.0, first), min(last, 1.0))

    def on_scroll(self, action, fraction, unit=None):
        if self.total_lines == 0:
            return
        f_start = self.filter_start if self.filter_start is not None else 0
        f_end = self.filter_end if self.filter_end is not None else self.total_lines
        total_filtered_lines = f_end - f_start

        if action == "moveto":
            fraction = max(0.0, min(float(fraction), 1.0))
            start_line = f_start + int(fraction * total_filtered_lines)
        elif action == "scroll":
            current_first = self.v_scrollbar.get()[0]
            start_line = f_start + int(current_first * total_filtered_lines)
            start_line += int(fraction) * self.max_visible_lines if unit == "pages" else int(fraction)

        max_scroll_limit = max(f_start, f_end - self.max_visible_lines)
        start_line = max(f_start, min(start_line, max_scroll_limit))
        self.set_scroll_bar_position(start_line)
        self.render_view(start_line)

    def on_mouse_wheel(self, event):
        if self.total_lines == 0:
            return "break"
        f_start = self.filter_start if self.filter_start is not None else 0
        f_end = self.filter_end if self.filter_end is not None else self.total_lines

        step = -1 if event.delta > 0 else 1
        start_line = self.current_start_line + (step * 3)
        max_scroll_limit = max(f_start, f_end - self.max_visible_lines)
        start_line = max(f_start, min(start_line, max_scroll_limit))
        self.set_scroll_bar_position(start_line)
        self.render_view(start_line)
        return "break"

    def scroll_by_keyboard(self, steps):
        if self.total_lines == 0:
            return "break"
        f_start = self.filter_start if self.filter_start is not None else 0
        f_end = self.filter_end if self.filter_end is not None else self.total_lines

        start_line = self.current_start_line + steps
        max_scroll_limit = max(f_start, f_end - self.max_visible_lines)
        start_line = max(f_start, min(start_line, max_scroll_limit))
        self.set_scroll_bar_position(start_line)
        self.render_view(start_line)
        return "break"


if __name__ == "__main__":
    app = UltimateLargeFileViewer()
    app.mainloop()
