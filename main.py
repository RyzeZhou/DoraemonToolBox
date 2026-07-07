#!/usr/bin/env python3
"""
哆啦A梦百宝箱 v1.2 - Python 脚本 GUI 中台
"""
import sys
import os

# 全局样式实例，供 CustomStyle 注入 _is_dark
_app_custom_style: "CustomStyle" = None
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QStyle, QProxyStyle, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QLabel, QPushButton, QToolBar,
    QTextBrowser, QTabWidget, QScrollArea, QFormLayout,
    QMessageBox, QFileDialog, QStatusBar, QProgressBar,
    QSplitter, QLineEdit, QComboBox, QFrame, QMenu, QSizePolicy, QGridLayout
)
from PySide6.QtCore import Qt, QSize, Signal, QTimer, QPointF
from PySide6.QtGui import QAction, QKeySequence, QFont, QPainter, QColor, QPen, QPalette

from config.validator import validate_parameters
from core import ScriptConfig, ScriptRegistry
from widgets import ParameterWidget, TerminalWidget, ProgressWidget
from runner import ProcessManager, TqdmInterceptor, StdinHandler


# ──────────────────────────────────────────────

# ── 自定义样式：复选框勾+下拉框箭头 ─────────────────────────────
class CustomStyle(QProxyStyle):
    # _is_dark 由 MainWindow 在知道主题后注入
    _is_dark: bool = True

    def drawPrimitive(self, element, option, painter, widget=None):
        # ── 1. 复选框勾 ──────────────────────────────────────
        if element == QStyle.PrimitiveElement.PE_IndicatorCheckBox:
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing)
            # 用 widget.isChecked() 比 option.state 更可靠
            checked = widget.isChecked() if widget else bool(option.state & QStyle.StateFlag.State_On)
            bg_color = (widget.palette().color(widget.backgroundRole())
                        if widget else QColor("#1e1e1e"))
            painter.fillRect(option.rect, bg_color)
            rect = option.rect.adjusted(1, 1, -1, -1)
            if checked:
                painter.setBrush(QColor("#0078d4"))
                painter.setPen(QPen(QColor("#0078d4"), 1))
                painter.drawRoundedRect(rect, 4, 4)
                path_pen = QPen(Qt.GlobalColor.white, 2,
                                Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                                Qt.PenJoinStyle.RoundJoin)
                painter.setPen(path_pen)
                x, y, w, h = float(rect.x()), float(rect.y()), float(rect.width()), float(rect.height())
                p1 = QPointF(x + w * 0.25, y + h * 0.52)
                p2 = QPointF(x + w * 0.45, y + h * 0.72)
                p3 = QPointF(x + w * 0.75, y + h * 0.32)
                painter.drawLine(p1, p2)
                painter.drawLine(p2, p3)
            else:
                # 未勾选：暗黑模式深灰底深灰边框，浅色模式白底浅灰边框
                if self._is_dark:
                    painter.setBrush(QColor("#3c3c3c"))
                    painter.setPen(QPen(QColor("#555555"), 1))
                else:
                    painter.setBrush(QColor("#ffffff"))
                    painter.setPen(QPen(QColor("#c0c0c0"), 1))
                painter.drawRoundedRect(rect, 4, 4)
            painter.restore()

        # ── 2. item 视图面板（QComboBox 下拉框 hover/selected）──
        # QListWidget：QSS 已覆盖颜色，交给 super() 渲染
        # QComboBox 弹出视图：QSS 匹配不到，直接画
        elif element == QStyle.PrimitiveElement.PE_PanelItemViewItem:
            if isinstance(widget, QListWidget):
                super().drawPrimitive(element, option, painter, widget)
            elif option.state & (QStyle.StateFlag.State_Selected |
                                QStyle.StateFlag.State_MouseOver):
                bg = QColor("#b3d9ff") if not self._is_dark else QColor("#0078d4")
                painter.save()
                painter.fillRect(option.rect, bg)
                painter.restore()
            else:
                super().drawPrimitive(element, option, painter, widget)

        else:
            super().drawPrimitive(element, option, painter, widget)


#  标签按钮
# ──────────────────────────────────────────────
class TagButton(QPushButton):
    toggled_filter = Signal(str, bool)

    def __init__(self, tag: str, parent=None):
        super().__init__(tag, parent)
        self._tag = tag
        self.setCheckable(True)
        self.setFixedHeight(26)  # 加高，适配高 DPI
        self.setCursor(Qt.PointingHandCursor)
        self._update_style()
        self.toggled.connect(self._on_toggled)

    @property
    def tag(self) -> str:
        return self._tag

    def _on_toggled(self, checked: bool):
        self._update_style()
        self.toggled_filter.emit(self._tag, checked)

    def _update_style(self):
        if self.isChecked():
            self.setStyleSheet(
                "QPushButton { background-color: #0078d4; color: white; "
                "border: 1px solid #005a9e; border-radius: 11px; padding: 2px 12px; font-size: 10pt; }"
            )
        else:
            self.setStyleSheet(
                "QPushButton { background-color: transparent; color: #888; "
                "border: 1px solid #666; border-radius: 11px; padding: 2px 12px; font-size: 10pt; }"
                "QPushButton:hover { border-color: #0078d4; color: #ccc; }"
            )


# ──────────────────────────────────────────────
#  脚本列表项控件（名称 + 标签两行布局）
# ──────────────────────────────────────────────
class ScriptListItemWidget(QWidget):
    """脚本列表项：名称在上，标签小字在下（强制两行）"""

    def __init__(self, name: str, tags: list, is_dark: bool = True, parent=None):
        super().__init__(parent)
        self.setFixedHeight(42)
        self.setStyleSheet("background: transparent;")

        # 根据主题设定文字颜色
        name_color = "#d4d4d4" if is_dark else "#1e1e1e"

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 3, 8, 3)
        lay.setSpacing(1)

        # 第一行：脚本名称
        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(f"font-weight: 500; color: {name_color}; background: transparent;")
        name_lbl.setWordWrap(False)
        lay.addWidget(name_lbl)

        # 第二行：标签
        tag_bg = "rgba(0, 120, 212, 0.15)"
        tag_text = "#1a5ea8" if not is_dark else "#4daaff"
        tag_row = QHBoxLayout()
        tag_row.setContentsMargins(0, 0, 0, 0)
        tag_row.setSpacing(3)
        if tags:
            for t in tags:
                tag_lbl = QLabel(t)
                tag_lbl.setStyleSheet(
                    f"background-color: {tag_bg}; "
                    f"color: {tag_text}; "
                    "border-radius: 7px; "
                    "padding: 0px 5px; "
                    "font-size: 8pt;"
                )
                tag_lbl.setFixedHeight(15)
                tag_row.addWidget(tag_lbl)
        tag_row.addStretch()
        lay.addLayout(tag_row)


# ──────────────────────────────────────────────
#  多终端 Tab 容器
# ──────────────────────────────────────────────
class MultiTerminalWidget(QTabWidget):
    tab_finished = Signal(int, int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTabsClosable(True)
        self.setMovable(True)
        # 标签过多时可滚动
        self.tabBar().setUsesScrollButtons(True)
        self.tabBar().setElideMode(Qt.ElideRight)
        self.tabCloseRequested.connect(self._on_tab_close)

    def add_terminal(self, title: str) -> tuple[TerminalWidget, int]:
        terminal = TerminalWidget()
        idx = self.addTab(terminal, f"▶ {title}")
        self.setCurrentIndex(idx)
        return terminal, idx

    def update_tab_title(self, index: int, title: str, status: str = ""):
        prefix_map = {"running": "▶", "done": "✓", "failed": "✗", "stopped": "■"}
        prefix = prefix_map.get(status, "")
        self.setTabText(index, f"{prefix} {title}" if prefix else title)

    def get_task_info(self, index: int) -> Optional[dict]:
        """获取某个 tab 绑定的 task_info"""
        w = self.widget(index)
        if w:
            return w.property("task_info")
        return None

    def _on_tab_close(self, index: int):
        widget = self.widget(index)
        if widget is None:
            return
        pm = widget.property("process_manager")
        if pm and isinstance(pm, ProcessManager) and pm.is_running():
            reply = QMessageBox.question(
                self, "确认",
                "该终端的脚本仍在运行，确定要强制终止并关闭吗？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                pm.terminate()
                pm.waitForFinished(3000)  # 等待进程结束
            else:
                return
        self.removeTab(index)
        widget.deleteLater()


# ──────────────────────────────────────────────
#  主窗口
# ──────────────────────────────────────────────
class MainWindow(QMainWindow):

    THEME_CONFIG_PATH = Path("theme.json")
    SORT_OPTIONS = [("名称 ↑", "name_asc"), ("名称 ↓", "name_desc"), ("标签", "tags")]

    def __init__(self):
        super().__init__()
        self.setWindowTitle("哆啦A梦百宝箱 v1.2")
        self.setMinimumSize(1400, 900)

        self.registry = ScriptRegistry(script_dirs=[Path('scripts')])
        self.current_script: Optional[ScriptConfig] = None
        self.param_widgets: List[ParameterWidget] = []
        self._param_cache_path = Path('param_cache.json')
        self._search_text = ""
        self._sort_mode = "name_asc"
        self._active_tags: Set[str] = set()
        self._running_tasks: Dict[int, dict] = {}
        self._params_auto_loaded = False  # 标记当前脚本参数是否来自自动载入
        self._is_dark = self._load_theme_preference()
        self._python_path_cache = self._load_python_path_cache()
        # 同步到全局 CustomStyle（checkbox 颜色依赖此值）
        _app_custom_style._is_dark = self._is_dark
        from widgets.parameters import CustomCheckBox
        CustomCheckBox.set_theme(self._is_dark)  # 初始化复选框主题

        self._setup_ui()
        self._load_styles()
        self._scan_scripts()

    # ── 主题 ──────────────────────────────────
    def _load_theme_preference(self) -> bool:
        if self.THEME_CONFIG_PATH.exists():
            try:
                return json.loads(self.THEME_CONFIG_PATH.read_text(encoding='utf-8')).get('dark', True)
            except Exception:
                pass
        return True

    def _save_theme_preference(self):
        try:
            self.THEME_CONFIG_PATH.write_text(json.dumps({'dark': self._is_dark}), encoding='utf-8')
        except Exception:
            pass

    def _load_styles(self):
        theme_file = 'dark.qss' if self._is_dark else 'light.qss'
        style_path = Path(__file__).parent / 'styles' / theme_file
        try:
            if style_path.exists():
                with open(style_path, 'r', encoding='utf-8') as f:
                    self.setStyleSheet(f.read())
        except Exception as e:
            print(f"加载样式失败: {e}")

    def _toggle_theme(self):
        self._is_dark = not self._is_dark
        _app_custom_style._is_dark = self._is_dark  # 同步 checkbox 颜色
        from widgets.parameters import CustomCheckBox
        CustomCheckBox.set_theme(self._is_dark)      # 刷新自定义复选框
        self._load_styles()
        self._save_theme_preference()
        self._update_theme_btn()
        for i in range(self.terminal_tabs.count()):
            terminal = self.terminal_tabs.widget(i)
            if isinstance(terminal, TerminalWidget):
                terminal.apply_theme(self._is_dark)
        # 刷新列表以应用新主题的脚本名颜色（已选脚本因 early return 不会重建表单）
        self._refresh_script_list()

    def _update_theme_btn(self):
        if hasattr(self, 'btn_theme'):
            self.btn_theme.setText("☀️" if self._is_dark else "🌙")

    # ── UI 构建 ────────────────────────────────
    def _setup_ui(self):
        # ── 工具栏（无菜单栏）──
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(18, 18))
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)

        self.btn_refresh = QAction("🔄 刷新", self)
        self.btn_refresh.triggered.connect(self._scan_scripts)
        toolbar.addAction(self.btn_refresh)

        self.btn_add_dir = QAction("📁 添加目录", self)
        self.btn_add_dir.triggered.connect(self._add_script_directory)
        toolbar.addAction(self.btn_add_dir)

        self.btn_backup = QAction("💾 备份库", self)
        self.btn_backup.triggered.connect(self._backup_scripts)
        toolbar.addAction(self.btn_backup)

        self.btn_load_params = QAction("📂 载入上次参数", self)
        self.btn_load_params.triggered.connect(self._load_last_params)
        toolbar.addAction(self.btn_load_params)

        self.btn_reset_params = QAction("🔄 恢复默认参数", self)
        self.btn_reset_params.triggered.connect(self._reset_to_defaults)
        toolbar.addAction(self.btn_reset_params)

        toolbar.addSeparator()

        self.btn_run = QAction("▶ 运行", self)
        self.btn_run.triggered.connect(self._run_selected_script)
        toolbar.addAction(self.btn_run)

        self.btn_stop = QAction("⏹ 终止当前", self)
        self.btn_stop.triggered.connect(self._stop_current_tab)
        self.btn_stop.setEnabled(False)
        toolbar.addAction(self.btn_stop)

        self.btn_stop_all = QAction("⏹ 全部终止", self)
        self.btn_stop_all.triggered.connect(self._stop_all_tasks)
        self.btn_stop_all.setEnabled(False)
        toolbar.addAction(self.btn_stop_all)

        toolbar.addSeparator()

        self.btn_clear = QAction("🗑 清空", self)
        self.btn_clear.triggered.connect(self._clear_current_terminal)
        toolbar.addAction(self.btn_clear)

        toolbar.addSeparator()

        self.btn_theme = QAction("", self)
        self.btn_theme.triggered.connect(self._toggle_theme)
        toolbar.addAction(self.btn_theme)
        self._update_theme_btn()

        toolbar.addSeparator()

        self.btn_about = QAction("ℹ 关于", self)
        self.btn_about.triggered.connect(self._show_about)
        toolbar.addAction(self.btn_about)

        # ── 中心区域 ──
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 主分割器：左(脚本列表) | 右(描述+参数+终端)
        main_splitter = QSplitter(Qt.Horizontal)

        # === 左侧面板 ===
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(6, 6, 6, 6)
        left_lay.setSpacing(4)

        left_lay.addWidget(QLabel("📋 脚本列表"))

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 搜索...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setFixedHeight(28)
        self.search_input.textChanged.connect(self._on_search_changed)
        left_lay.addWidget(self.search_input)

        sort_row = QHBoxLayout()
        sort_row.setSpacing(4)
        sort_lbl = QLabel("排序:")
        sort_lbl.setFixedWidth(30)
        sort_row.addWidget(sort_lbl)
        self.sort_combo = QComboBox()
        self.sort_combo.setFixedHeight(26)
        for label, mode in self.SORT_OPTIONS:
            self.sort_combo.addItem(label, mode)
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        sort_row.addWidget(self.sort_combo, stretch=1)

        self.tag_filter_btn = QPushButton("标签")
        self.tag_filter_btn.setFixedHeight(26)
        self.tag_filter_btn.setMinimumWidth(72)
        self.tag_filter_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.tag_filter_btn.clicked.connect(self._show_tag_popup)
        sort_row.addWidget(self.tag_filter_btn)

        self.clear_tags_btn = QPushButton("清除")
        self.clear_tags_btn.setFixedSize(36, 26)
        self.clear_tags_btn.setStyleSheet("font-size: 8pt; padding: 0;")
        self.clear_tags_btn.clicked.connect(self._clear_tag_filters)
        self.clear_tags_btn.setVisible(False)
        sort_row.addWidget(self.clear_tags_btn)
        left_lay.addLayout(sort_row)

        self._all_tags: List[str] = []
        self._tag_popup: Optional[QFrame] = None
        self._tag_search_input: Optional[QLineEdit] = None
        self._tag_grid_widget: Optional[QWidget] = None

        # 脚本列表
        self.script_list = QListWidget()
        self.script_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.script_list.customContextMenuRequested.connect(self._show_script_context_menu)
        self.script_list.setMinimumWidth(200)
        self.script_list.setMaximumWidth(350)
        self.script_list.currentItemChanged.connect(self._on_script_selected)
        left_lay.addWidget(self.script_list, stretch=1)

        self.count_label = QLabel("")
        self.count_label.setStyleSheet("color: #888; font-size: 9pt;")
        self.count_label.setFixedHeight(18)  # 固定高度
        left_lay.addWidget(self.count_label)

        main_splitter.addWidget(left)

        # === 右侧面板 ===
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(6, 6, 6, 6)
        right_lay.setSpacing(6)

        # 脚本描述头：标签 + 脚本名称 + 标签（同一行）
        desc_header = QHBoxLayout()
        desc_header.setSpacing(6)
        desc_header.addWidget(QLabel("📝 脚本描述:"))

        # 分隔竖条
        sep = QLabel("|")
        sep.setStyleSheet("color: #666; font-weight: 300;")
        desc_header.addWidget(sep)

        # 脚本名称（动态更新）
        self.script_name_label = QLabel("")
        self.script_name_label.setStyleSheet("font-weight: 500;")
        desc_header.addWidget(self.script_name_label)

        # 标签区域（动态更新）
        self.script_tags_widget = QWidget()
        self.script_tags_layout = QHBoxLayout(self.script_tags_widget)
        self.script_tags_layout.setContentsMargins(0, 0, 0, 0)
        self.script_tags_layout.setSpacing(3)
        desc_header.addWidget(self.script_tags_widget)

        desc_header.addStretch()
        right_lay.addLayout(desc_header)

        # 描述内容
        self.info_browser = QTextBrowser()
        self.info_browser.setReadOnly(True)
        desc_font = self.info_browser.font()
        desc_font.setPointSize(10)
        self.info_browser.setFont(desc_font)
        self.info_browser.setMinimumHeight(130)

        # ── 描述区域 + 参数配置 + 终端输出 可拖动分割 ──
        top_splitter = QSplitter(Qt.Vertical)
        top_splitter.addWidget(self.info_browser)
        top_splitter.setStretchFactor(0, 0)  # info_browser 可压缩

        # ── Python 路径配置栏（描述框和参数表单之间）──
        self._python_path_container = QFrame()
        self._python_path_container.setFrameShape(QFrame.NoFrame)
        self._python_path_container.setFixedHeight(40)
        self._python_path_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._python_path_container.setStyleSheet(
            "QFrame { border-top: 1px solid #555; padding: 2px 4px; }"
        )
        python_path_layout = QHBoxLayout(self._python_path_container)
        python_path_layout.setContentsMargins(0, 2, 0, 2)
        python_path_layout.setSpacing(4)
        top_splitter.addWidget(self._python_path_container)

        bottom_splitter = QSplitter(Qt.Horizontal)

        # 左：参数配置
        param_box = QWidget()
        param_lay = QVBoxLayout(param_box)
        param_lay.setContentsMargins(0, 0, 4, 0)
        param_lay.setSpacing(4)
        param_lay.addWidget(QLabel("⚙ 参数配置"))
        self.param_scroll = QScrollArea()
        self.param_scroll.setWidgetResizable(True)
        self.param_container = QWidget()
        self.param_form_layout = QFormLayout(self.param_container)
        self.param_form_layout.setContentsMargins(6, 6, 6, 6)
        self.param_form_layout.setSpacing(6)
        self.param_scroll.setWidget(self.param_container)
        param_lay.addWidget(self.param_scroll)
        bottom_splitter.addWidget(param_box)

        # 右：终端输出（带标签）
        term_box = QWidget()
        term_lay = QVBoxLayout(term_box)
        term_lay.setContentsMargins(4, 0, 0, 0)
        term_lay.setSpacing(4)
        term_lay.addWidget(QLabel("🖥 终端输出:"))
        self.terminal_tabs = MultiTerminalWidget()
        self.terminal_tabs.tab_finished.connect(self._on_task_tab_finished)
        self.terminal_tabs.currentChanged.connect(self._on_terminal_tab_changed)
        term_lay.addWidget(self.terminal_tabs)

        # 进度条跟随终端标签页，归属于终端输出栏
        self.progress_widget = ProgressWidget()
        self.progress_widget.setFixedHeight(50)
        self.progress_widget.hide_progress()
        term_lay.addWidget(self.progress_widget)

        bottom_splitter.addWidget(term_box)

        # 参数区较窄，终端区较宽
        bottom_splitter.setSizes([350, 700])

        top_splitter.addWidget(bottom_splitter)
        top_splitter.setCollapsible(0, False)
        top_splitter.setCollapsible(1, False)
        top_splitter.setCollapsible(2, False)
        top_splitter.setStretchFactor(1, 1)  # bottom_splitter 获得拉伸权重
        top_splitter.setStretchFactor(2, 8)
        top_splitter.setSizes([150, 40, 650])
        right_lay.addWidget(top_splitter, stretch=1)

        main_splitter.addWidget(right)
        main_splitter.setSizes([280, 1120])
        outer.addWidget(main_splitter)

        # ── 状态栏 ──
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        self.status_label = QLabel("就绪")
        status_bar.addWidget(self.status_label, 1)
        self.running_label = QLabel("")
        self.running_label.setStyleSheet("color: #0078d4; font-weight: bold;")
        status_bar.addPermanentWidget(self.running_label)

    # ── 信号连接 ────────────────────────────────
    def _connect_task_signals(self, task_info: dict, tab_index: int):
        pm = task_info['process_manager']
        ti = task_info['tqdm_interceptor']
        pm.output_received.connect(lambda text, idx=tab_index: self._on_task_output(idx, text))
        pm.finished.connect(lambda code, stdout, stderr, idx=tab_index: self._on_task_finished(idx, code))
        ti._timer.timeout.connect(lambda idx=tab_index: self._on_task_progress(idx))

    # ── 脚本扫描 & 过滤 ─────────────────────────
    def _scan_scripts(self):
        self.status_label.setText("扫描中...")
        self.registry.scan()
        self._rebuild_tag_buttons()
        self._refresh_script_list()
        errors = self.registry.errors
        if errors:
            QMessageBox.warning(self, "扫描警告", "\n".join(errors))

    def _rebuild_tag_buttons(self):
        all_tags: Set[str] = set()
        for script in self.registry.list_scripts():
            all_tags.update(script.tags)

        self._all_tags = sorted(all_tags, key=lambda t: t.lower())
        self._update_tag_filter_button()
        if self._tag_popup and self._tag_popup.isVisible():
            self._rebuild_tag_popup_tags()

    def _show_tag_popup(self):
        if not self._tag_popup:
            self._tag_popup = QFrame(self, Qt.Popup)
            self._tag_popup.setFrameShape(QFrame.StyledPanel)
            self._tag_popup.setFixedWidth(520)
            self._tag_popup.setStyleSheet(
                "QFrame { border: 1px solid #666; border-radius: 4px; }"
            )

            popup_lay = QVBoxLayout(self._tag_popup)
            popup_lay.setContentsMargins(8, 8, 8, 8)
            popup_lay.setSpacing(8)

            self._tag_search_input = QLineEdit()
            self._tag_search_input.setPlaceholderText("搜索标签...")
            self._tag_search_input.setClearButtonEnabled(True)
            self._tag_search_input.setFixedHeight(28)
            self._tag_search_input.textChanged.connect(self._rebuild_tag_popup_tags)
            popup_lay.addWidget(self._tag_search_input)

            tag_scroll = QScrollArea()
            tag_scroll.setWidgetResizable(True)
            tag_scroll.setFrameShape(QFrame.NoFrame)
            tag_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            tag_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            tag_scroll.setMinimumHeight(120)
            tag_scroll.setFixedHeight(290)

            self._tag_grid_widget = QWidget()
            tag_scroll.setWidget(self._tag_grid_widget)
            popup_lay.addWidget(tag_scroll)

        self._tag_search_input.clear()
        self._rebuild_tag_popup_tags()

        popup_width = 520
        popup_height = 360
        self._tag_popup.resize(popup_width, popup_height)
        pos = self.tag_filter_btn.mapToGlobal(self.tag_filter_btn.rect().topRight())
        self._tag_popup.move(pos.x() + 6, pos.y())
        self._tag_popup.show()
        self._tag_search_input.setFocus()

    def _rebuild_tag_popup_tags(self):
        if not self._tag_grid_widget:
            return

        old_layout = self._tag_grid_widget.layout()
        if old_layout:
            while old_layout.count():
                item = old_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            old_layout.deleteLater()

        grid = QGridLayout(self._tag_grid_widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)

        query = self._tag_search_input.text().strip().lower() if self._tag_search_input else ""
        tags = [tag for tag in self._all_tags if not query or query in tag.lower()]
        columns = 3
        for index, tag in enumerate(tags):
            btn = TagButton(tag)
            btn.setMinimumWidth(150)
            btn.setChecked(tag in self._active_tags)
            btn.toggled_filter.connect(self._on_tag_toggled)
            row, col = divmod(index, columns)
            grid.addWidget(btn, row, col)

        if not tags:
            empty = QLabel("没有匹配标签")
            empty.setStyleSheet("color: #888; padding: 8px;")
            grid.addWidget(empty, 0, 0)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        self._tag_grid_widget.adjustSize()

    def _update_tag_filter_button(self):
        count = len(self._active_tags)
        self.tag_filter_btn.setText(f"标签({count})" if count else "标签")
        self.clear_tags_btn.setVisible(count > 0)

    def _refresh_script_list(self):
        scripts = self.registry.list_scripts()

        # 保存当前选中脚本，刷新后恢复
        current_id = self.current_script.id if self.current_script else None

        filtered = []
        for s in scripts:
            if self._search_text:
                q = self._search_text.lower()
                if q not in s.name.lower() and q not in s.description.lower():
                    continue
            if self._active_tags:
                if not self._active_tags.intersection(set(s.tags)):
                    continue
            filtered.append(s)

        if self._sort_mode == "name_asc":
            filtered.sort(key=lambda s: s.name.lower())
        elif self._sort_mode == "name_desc":
            filtered.sort(key=lambda s: s.name.lower(), reverse=True)
        elif self._sort_mode == "tags":
            filtered.sort(key=lambda s: (s.tags[0].lower() if s.tags else 'zzz', s.name.lower()))

        self.script_list.blockSignals(True)
        self.script_list.clear()
        for script in filtered:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, script.id)
            item.setToolTip(script.description[:120] if script.description else script.name)
            item.setSizeHint(QSize(0, 44))  # 统一高度
            self.script_list.addItem(item)
            widget = ScriptListItemWidget(script.name, script.tags, self._is_dark)
            self.script_list.setItemWidget(item, widget)
        self.script_list.blockSignals(False)

        total = len(scripts)
        shown = len(filtered)
        self.count_label.setText(f"共 {total} 个" if shown == total else f"{shown}/{total}")

        # 恢复之前选中的脚本，不自动跳到第一个
        if current_id:
            for i in range(self.script_list.count()):
                item = self.script_list.item(i)
                if item.data(Qt.UserRole) == current_id:
                    self.script_list.setCurrentItem(item)
                    return
        if self.script_list.count() > 0:
            self.script_list.setCurrentRow(0)
        else:
            self.current_script = None
            self._clear_parameter_form()
            self.info_browser.clear()

    def _clear_parameter_form(self):
        self.param_widgets.clear()
        while self.param_form_layout.count():
            item = self.param_form_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    # ── 搜索 / 排序 / 标签 回调 ──────────────────
    def _on_search_changed(self, text: str):
        self._search_text = text.strip()
        self._refresh_script_list()

    def _on_sort_changed(self, index: int):
        self._sort_mode = self.sort_combo.currentData()
        self._refresh_script_list()

    def _on_tag_toggled(self, tag: str, active: bool):
        if active:
            self._active_tags.add(tag)
        else:
            self._active_tags.discard(tag)
        self._update_tag_filter_button()
        self._refresh_script_list()

    def _clear_tag_filters(self):
        self._active_tags.clear()
        self._update_tag_filter_button()
        if self._tag_popup and self._tag_popup.isVisible():
            self._rebuild_tag_popup_tags()
        self._refresh_script_list()

    # ── 脚本选择 ─────────────────────────────────
    def _on_script_selected(self, current: QListWidgetItem, previous):
        if not current:
            return
        script_id = current.data(Qt.UserRole)
        # 同一脚本被重复选中（如主题切换时刷新列表），跳过避免重建表单
        if self.current_script and self.current_script.id == script_id:
            return
        script = self.registry.get_script(script_id)
        if script:
            self.current_script = script
            self._display_script_info(script)
            self._rebuild_python_path_bar(script)
            self._build_parameter_form(script)
            # 有缓存时静默自动载入，不弹窗
            cache = self._load_param_cache()
            if script.id in cache:
                self._load_last_params()
                self._params_auto_loaded = True
                self.status_label.setText("就绪，已载入上次参数")
            else:
                self._params_auto_loaded = False
                self.status_label.setText("就绪")

    def _display_script_info(self, script: ScriptConfig):
        # 更新名称标签
        self.script_name_label.setText(script.name)

        # 更新标签区域
        while self.script_tags_layout.count():
            item = self.script_tags_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for t in script.tags:
            tag_lbl = QLabel(t)
            tag_bg = "rgba(0, 120, 212, 0.15)"
            tag_text = "#1a5ea8" if not self._is_dark else "#4daaff"
            tag_lbl.setStyleSheet(
                f"background-color: {tag_bg}; "
                f"color: {tag_text}; "
                "border-radius: 7px; "
                "padding: 0px 5px; "
                "font-size: 8pt;"
            )
            tag_lbl.setFixedHeight(15)
            self.script_tags_layout.addWidget(tag_lbl)

        # 描述内容（YAML | 块 scalars 的 \n 需要转成 <br> 才会在 HTML 里正确换行）
        # 格式: |脚本名\n描述内容 → 脚本名加粗，其余正常
        info = ""
        if script.description:
            text = script.description
            first_newline = text.find('\n')
            if first_newline > 0:
                name_part = text[:first_newline]
                body_part = text[first_newline:]
                info += f"<b>{name_part}</b>"
                info += body_part.replace('\n', '<br>')
            else:
                info = f"<b>{text}</b>"
        if script.has_progress_file():
            if info:
                info += "<br>"
            info += '<span style="color:#ff8c00;">⚠ 存在未完成任务</span>'
        self.info_browser.setHtml(info if info else "<span style='color:#888;'>暂无描述</span>")

    def _build_parameter_form(self, script: ScriptConfig):
        self._clear_parameter_form()
        for param in script.parameters:
            widget = ParameterWidget(param)
            self.param_widgets.append(widget)
            self.param_form_layout.addRow(widget)

    def _collect_parameters(self) -> Dict[str, Any]:
        return {w.param_config['name']: w.get_value() for w in self.param_widgets}

    # ── 终端 tab 切换 → 更新终止按钮 ─────────────
    def _on_terminal_tab_changed(self, index: int):
        self._update_stop_buttons()
        self._sync_progress_widget_to_current_tab()

    # ── 脚本运行 ─────────────────────────────────
    def _run_selected_script(self):
        if not self.current_script:
            QMessageBox.warning(self, "提示", "请先选择一个脚本")
            return

        params = self._collect_parameters()
        errors = validate_parameters(params, self.current_script.parameters)
        if errors:
            QMessageBox.warning(self, "参数错误", "\n".join(f"• {e}" for e in errors))
            return

        # 校验Python路径不存在（从控件实时读取，不依赖缓存）
        mode_combo = None
        for child in self._python_path_container.findChildren(QComboBox):
            if child.currentData() in ('system', 'conda', 'custom'):
                mode_combo = child
                break
        current_mode = mode_combo.currentData() if mode_combo else 'system'
        python_path = None  # None → 使用 sys.executable

        if current_mode == 'conda':
            # 从conda combo实时读取
            conda_combo = None
            for child in self._python_path_container.findChildren(QComboBox):
                if child != mode_combo:
                    conda_combo = child
                    break
            conda_name = conda_combo.currentData() or '' if conda_combo else ''
            if not conda_name:
                QMessageBox.warning(self, "Python路径错误", "未选择conda环境，请先在Python路径配置中选择环境")
                return
            env_names = [name for name, path in self._detect_conda_envs()]
            if conda_name not in env_names:
                reply = QMessageBox.question(
                    self, "Python路径错误",
                    f"conda环境 '{conda_name}' 不存在，将使用系统默认Python继续运行。\n是否继续？",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                )
                if reply == QMessageBox.No:
                    return
            # 校验通过，从conda环境列表取实际路径
            for name, path in self._detect_conda_envs():
                if name == conda_name:
                    python_path = path
                    break
        elif current_mode == 'custom':
            # 从编辑框实时读取
            custom_edit = self._python_path_container.findChild(QLineEdit)
            custom_path = custom_edit.text().strip() if custom_edit else ''
            if not custom_path:
                QMessageBox.warning(self, "Python路径错误", "未指定Python解释器路径，请先在Python路径配置中指定")
                return
            if not os.path.exists(custom_path):
                reply = QMessageBox.question(
                    self, "Python路径错误",
                    f"Python路径不存在：\n{custom_path}\n将使用系统默认Python继续运行。\n是否继续？",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                )
                if reply == QMessageBox.No:
                    return
            # 校验通过，直接使用实时读取的路径
            python_path = custom_path

        args = []
        for name, value in params.items():
            if value is None or value == '':
                continue
            param_def = next((p for p in self.current_script.parameters if p['name'] == name), None)
            if param_def:
                ptype = param_def.get('type')
                if ptype == 'boolean':
                    # 布尔参数只有为 True 时才加标志位，不传值
                    if value:
                        args.append(f"--{name}")
                elif ptype in ('list', 'multi_file', 'multi_directory', 'list_string'):
                    if isinstance(value, list) and value:
                        args.append(f"--{name}")
                        args.extend([str(v) for v in value if v])
                else:
                    args.extend([f"--{name}", str(value)])

        script_name = self.current_script.name
        terminal, tab_index = self.terminal_tabs.add_terminal(script_name)

        pm = ProcessManager()
        pm.set_working_directory(self.current_script.script_path.parent)
        ti = TqdmInterceptor()
        sh = StdinHandler()
        sh.set_parent_widget(self)

        task_info = {
            'process_manager': pm, 'tqdm_interceptor': ti,
            'stdin_handler': sh, 'terminal': terminal,
            'script_name': script_name, 'script_config': self.current_script,
            'tab_index': tab_index,
            'progress_percent': 0, 'progress_text': '', 'has_tqdm': False,
        }
        self._running_tasks[tab_index] = task_info
        self._connect_task_signals(task_info, tab_index)
        terminal.setProperty("process_manager", pm)
        terminal.setProperty("task_info", task_info)
        sh.yn_prompt_detected.connect(lambda prompt, idx=tab_index: None)
        sh.text_prompt_detected.connect(lambda prompt, idx=tab_index: None)

        # 使用前面从UI控件实时读取的python_path，不依赖缓存
        success = pm.start(script_path=self.current_script.script_path, arguments=args, python_path=python_path)
        if not success:
            QMessageBox.critical(self, "启动失败", "无法启动脚本进程")
            self.terminal_tabs.update_tab_title(tab_index, script_name, "failed")
            return

        self.terminal_tabs.update_tab_title(tab_index, script_name, "running")
        self.terminal_tabs.setCurrentIndex(tab_index)
        self._sync_progress_widget_to_current_tab()
        self._update_running_label()
        self._update_stop_buttons()
        self._save_param_cache()

    # ── 任务输出处理 ─────────────────────────────
    def _on_task_output(self, tab_index: int, text: str):
        task = self._running_tasks.get(tab_index)
        if not task:
            return
        terminal, ti, sh = task['terminal'], task['tqdm_interceptor'], task['stdin_handler']

        # 去重：避免 _on_task_finished 中 flush_remaining() 重复追加同一内容
        dedup_cache: set = task.setdefault('_output_dedup', set())
        lines = ti.clean_tqdm_from_text(text).splitlines(keepends=True)
        for line in lines:
            if line not in dedup_cache:
                dedup_cache.add(line)
                terminal.append_text(line)

        if ti.process_output(text) is not None:
            task['progress_percent'] = ti.get_last_percentage()
            task['progress_text'] = ti.get_last_detail()
            task['has_tqdm'] = True
            if self.terminal_tabs.currentIndex() == tab_index:
                self.progress_widget.show_progress()
                self.progress_widget.update_progress(task['progress_percent'], task['progress_text'])
        if sh.process_output(text):
            QTimer.singleShot(100, lambda idx=tab_index: self._handle_stdin_interaction(idx))

    def _on_task_progress(self, tab_index: int):
        task = self._running_tasks.get(tab_index)
        if not task:
            return
        ti = task['tqdm_interceptor']
        task['progress_percent'] = ti.get_last_percentage()
        task['progress_text'] = ti.get_last_detail()
        if task.get('progress_text') or task['progress_percent']:
            task['has_tqdm'] = True
        if self.terminal_tabs.currentIndex() == tab_index and task.get('has_tqdm'):
            self.progress_widget.show_progress()
            self.progress_widget.update_progress(task['progress_percent'], task['progress_text'])

    def _on_task_finished(self, tab_index: int, exit_code: int):
        task = self._running_tasks.get(tab_index)
        if not task:
            return

        ti = task['tqdm_interceptor']
        terminal = task['terminal']
        script_name = task['script_name']
        dedup_cache: set = task.setdefault('_output_dedup', set())

        # 检查终端控件是否还存在（用户可能已关闭标签页）
        import shiboken6
        terminal_alive = terminal is not None and shiboken6.isValid(terminal)

        if terminal_alive:
            for line in ti.flush_remaining():
                if line not in dedup_cache:
                    dedup_cache.add(line)
                    terminal.append_text(line + '\n')

        status = "done" if exit_code == 0 else "failed"

        # 更新 tab 标题（检查 tab 是否还存在）
        if tab_index < self.terminal_tabs.count():
            self.terminal_tabs.update_tab_title(tab_index, script_name, status)

        if terminal_alive:
            if exit_code == 0:
                terminal.append_text(f"\n{'─'*40}\n✓ 完成 (退出码: 0)\n", color="#4ec9b0")
            else:
                terminal.append_text(f"\n{'─'*40}\n✗ 失败 (退出码: {exit_code})\n", color="#f44747")

        self._update_running_label()
        self._update_stop_buttons()
        if self.terminal_tabs.currentIndex() == tab_index:
            self._sync_progress_widget_to_current_tab()

    def _on_task_tab_finished(self, tab_index: int, exit_code: int, script_name: str):
        pass

    # ── 进度 & 状态 ─────────────────────────────
    def _sync_progress_widget_to_current_tab(self):
        idx = self.terminal_tabs.currentIndex()
        task = self._running_tasks.get(idx)
        if not task or not task.get('has_tqdm'):
            self.progress_widget.reset()
            self.progress_widget.hide_progress()
            return
        percent = task.get('progress_percent', 0)
        detail = task.get('progress_text', '')
        self.progress_widget.show_progress()
        self.progress_widget.update_progress(percent, detail)

    def _update_running_label(self):
        count = sum(1 for t in self._running_tasks.values() if t['process_manager'].is_running())
        if count > 0:
            self.running_label.setText(f"⚡ {count} 个运行中")
            self.status_label.setText("运行中...")
        else:
            self.running_label.setText("")
            self.status_label.setText(
                "就绪，已载入上次参数" if self._params_auto_loaded else "就绪"
            )

    def _update_stop_buttons(self):
        # 全部终止：有任意运行中的任务就启用
        has_any = any(t['process_manager'].is_running() for t in self._running_tasks.values())
        self.btn_stop_all.setEnabled(has_any)

        # 终止当前：当前选中的 tab 有运行中任务才启用
        idx = self.terminal_tabs.currentIndex()
        task = self._running_tasks.get(idx)
        current_running = task is not None and task['process_manager'].is_running()
        self.btn_stop.setEnabled(current_running)

    # ── 终止操作 ─────────────────────────────────
    def _stop_current_tab(self):
        """终止当前选中终端页对应的进程"""
        idx = self.terminal_tabs.currentIndex()
        task = self._running_tasks.get(idx)
        if not task or not task['process_manager'].is_running():
            return
        task['process_manager'].terminate()
        self.terminal_tabs.update_tab_title(idx, task['script_name'], "stopped")
        task['terminal'].append_text("\n■ 已终止\n", color="#f44747")
        self._update_running_label()
        self._update_stop_buttons()

    def _stop_all_tasks(self):
        running = [(idx, t) for idx, t in self._running_tasks.items() if t['process_manager'].is_running()]
        if not running:
            return
        reply = QMessageBox.question(
            self, "确认", f"终止全部 {len(running)} 个任务？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            for idx, task in running:
                task['process_manager'].terminate()
                self.terminal_tabs.update_tab_title(idx, task['script_name'], "stopped")
                task['terminal'].append_text("\n■ 已终止\n", color="#f44747")
            self._update_running_label()
            self._update_stop_buttons()

    # ── stdin 交互 ──────────────────────────────
    def _handle_stdin_interaction(self, tab_index: int):
        task = self._running_tasks.get(tab_index)
        if not task:
            return
        sh, pm = task['stdin_handler'], task['process_manager']
        if not sh.has_pending():
            return
        try:
            if sh._prompt_type == 'yn':
                response = sh.handle_yn_dialog()
            elif sh._prompt_type == 'text':
                response = sh.handle_text_dialog()
            elif sh._prompt_type == 'wait':
                # "按回车退出" 类提示：自动发送空行，不弹窗
                response = ""
            else:
                return
            sh.send_response(response, pm.write_stdin)
            if response:
                task['terminal'].append_text(f"  → {response}\n", color="#0078d4")
            else:
                task['terminal'].append_text("  → [自动回车]\n", color="#888")
        except Exception as e:
            print(f"stdin 交互失败: {e}")
            sh.reset()

    # ── 终端操作 ─────────────────────────────────
    def _clear_current_terminal(self):
        idx = self.terminal_tabs.currentIndex()
        terminal = self.terminal_tabs.widget(idx)
        if isinstance(terminal, TerminalWidget):
            terminal.clear_terminal()

    # ── Python 路径配置（每个脚本独立记忆）──────────────
    def _load_python_path_cache(self) -> Dict[str, dict]:
        """加载每个脚本的Python路径缓存 {script_id: {mode, conda_name, custom_path}}"""
        if self._param_cache_path.exists():
            try:
                data = json.loads(self._param_cache_path.read_text(encoding='utf-8'))
                return data.get('_python_paths', {})
            except Exception:
                pass
        return {}

    def _save_python_path_cache(self, script_id: str, mode: str, conda_name: str = '', custom_path: str = '') -> None:
        """保存单个脚本的Python路径配置到param_cache.json
        注意：系统默认模式不写入缓存，切换回system时删除该脚本的记录"""
        cache = self._load_param_cache()
        python_paths = cache.get('_python_paths', {})
        if mode == 'system':
            # 系统默认不记忆，删除已有记录
            python_paths.pop(script_id, None)
        else:
            python_paths[script_id] = {'mode': mode, 'conda_name': conda_name, 'custom_path': custom_path}
        cache['_python_paths'] = python_paths
        try:
            with open(self._param_cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _get_script_python_path(self, script_id: str) -> Optional[str]:
        """根据脚本ID获取实际要使用的Python解释器路径
        如果路径/环境不存在，返回None（回退到sys.executable）"""
        cache = self._load_python_path_cache()
        cfg = cache.get(script_id, {})
        mode = cfg.get('mode', 'system')
        if mode == 'system':
            return None  # 使用 sys.executable
        elif mode == 'conda':
            conda_envs = self._detect_conda_envs()
            conda_name = cfg.get('conda_name', '')
            for name, path in conda_envs:
                if name == conda_name:
                    return path
            # 环境不存在，返回None
            return None
        elif mode == 'custom':
            custom_path = cfg.get('custom_path', '')
            if custom_path and os.path.exists(custom_path):
                return custom_path
            # 路径不存在，返回None
            return None
        return None

    def _detect_conda_envs(self) -> list:
        """自动检测系统上的conda环境，返回 [(name, python_path), ...]"""
        envs = []
        import glob
        # 常见conda安装路径
        conda_roots = []
        # 当前conda
        import shutil
        conda_exe = shutil.which('conda')
        if conda_exe:
            import subprocess
            try:
                result = subprocess.run([conda_exe, 'env', 'list', '--json'], capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    data = json.loads(result.stdout)
                    for p in data.get('envs', []):
                        name = os.path.basename(p) or 'base'
                        python_path = os.path.join(p, 'python.exe' if sys.platform == 'win32' else 'bin', 'python')
                        if os.path.exists(python_path):
                            envs.append((name, python_path))
                    return envs
            except Exception:
                pass
        # 回退：常见路径扫描
        home = Path.home()
        patterns = [
            home / 'Miniconda3' / 'envs' / '*' / ('python.exe' if sys.platform == 'win32' else 'bin/python'),
            home / 'anaconda3' / 'envs' / '*' / ('python.exe' if sys.platform == 'win32' else 'bin/python'),
            home / '.conda' / 'envs' / '*' / ('python.exe' if sys.platform == 'win32' else 'bin/python'),
        ]
        for pattern in patterns:
            for p in glob.glob(str(pattern)):
                name = os.path.basename(os.path.dirname(os.path.dirname(p) if sys.platform != 'win32' else os.path.dirname(p)))
                envs.append((name, p))
        return envs

    def _rebuild_python_path_bar(self, script: ScriptConfig):
        """重建Python路径配置栏（切换脚本时调用）- 单行布局"""
        from PySide6.QtWidgets import QComboBox, QLineEdit, QPushButton, QLabel

        container = self._python_path_container
        main_layout = container.layout()
        row_height = 28

        # 清除旧控件
        while main_layout.count():
            item = main_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # ── 单行：🐍 Python: [模式下拉] [路径区域] ──
        title_label = QLabel("🐍 Python:")
        title_label.setFixedHeight(row_height)
        title_label.setWordWrap(False)
        main_layout.addWidget(title_label)

        mode_combo = QComboBox()
        mode_combo.addItem("系统默认", "system")
        mode_combo.addItem("Conda环境", "conda")
        mode_combo.addItem("自定义路径", "custom")
        mode_combo.setMinimumWidth(110)
        mode_combo.setFixedHeight(row_height)
        mode_combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        main_layout.addWidget(mode_combo)

        # 路径区域控件（根据模式显示/隐藏）
        # 系统默认：只读标签
        sys_label = QLabel()
        sys_label.setStyleSheet("color: #888; font-size: 11px;")
        sys_label.setFixedHeight(row_height)
        sys_label.setWordWrap(False)
        sys_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        sys_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        main_layout.addWidget(sys_label, stretch=1)

        # conda：环境下拉
        conda_combo = QComboBox()
        conda_combo.setMinimumWidth(180)
        conda_combo.setFixedHeight(row_height)
        conda_combo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        conda_envs = self._detect_conda_envs()
        for name, path in conda_envs:
            conda_combo.addItem(f"{name}  ({path})", name)
        conda_combo.setVisible(False)
        main_layout.addWidget(conda_combo, stretch=1)

        # 自定义：路径输入+浏览
        custom_edit = QLineEdit()
        custom_edit.setPlaceholderText("输入 python.exe 完整路径")
        custom_edit.setFixedHeight(row_height)
        custom_edit.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        custom_edit.setVisible(False)
        main_layout.addWidget(custom_edit, stretch=1)

        btn_browse = QPushButton("浏览…")
        btn_browse.setFixedWidth(55)
        btn_browse.setFixedHeight(row_height)
        btn_browse.setVisible(False)
        main_layout.addWidget(btn_browse)

        # 错误提示（紧跟在路径区域后面）
        error_label = QLabel("")
        error_label.setStyleSheet("color: #ff4444; font-size: 11px;")
        error_label.setFixedHeight(row_height)
        error_label.setWordWrap(False)
        error_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        error_label.setVisible(False)
        main_layout.addWidget(error_label)

        main_layout.addStretch()

        # 加载缓存
        cache = self._load_python_path_cache()
        cfg = cache.get(script.id, {})
        mode = cfg.get('mode', 'system')
        idx = mode_combo.findData(mode)
        if idx >= 0:
            mode_combo.setCurrentIndex(idx)

        def validate_and_show_error(m, custom_path_from_edit=None):
            """校验路径/环境是否存在，不存在则红显+显示错误"""
            if m == 'system':
                container.setStyleSheet("QFrame { border-top: 1px solid #555; padding: 2px 4px; }")
                error_label.setVisible(False)
                return True
            elif m == 'conda':
                conda_name = conda_combo.currentData() or ''
                if not conda_name:
                    container.setStyleSheet("QFrame { border: 1px solid #ff4444; border-radius: 3px; padding: 2px 4px; }")
                    error_label.setText("⚠ 未选择conda环境")
                    error_label.setVisible(True)
                    return False
                env_names = [name for name, path in conda_envs]
                if conda_name not in env_names:
                    container.setStyleSheet("QFrame { border: 1px solid #ff4444; border-radius: 3px; padding: 2px 4px; }")
                    error_label.setText(f"⚠ conda环境 '{conda_name}' 不存在")
                    error_label.setVisible(True)
                    return False
                container.setStyleSheet("QFrame { border-top: 1px solid #555; padding: 2px 4px; }")
                error_label.setVisible(False)
                return True
            elif m == 'custom':
                custom_p = custom_path_from_edit if custom_path_from_edit is not None else custom_edit.text().strip()
                if not custom_p:
                    container.setStyleSheet("QFrame { border: 1px solid #ff4444; border-radius: 3px; padding: 2px 4px; }")
                    error_label.setText("⚠ 未指定Python路径")
                    error_label.setVisible(True)
                    return False
                if not os.path.exists(custom_p):
                    container.setStyleSheet("QFrame { border: 1px solid #ff4444; border-radius: 3px; padding: 2px 4px; }")
                    error_label.setText(f"⚠ 路径不存在: {custom_p}")
                    error_label.setVisible(True)
                    return False
                container.setStyleSheet("QFrame { border-top: 1px solid #555; padding: 2px 4px; }")
                error_label.setVisible(False)
                return True
            return True

        def on_mode_changed(index):
            m = mode_combo.itemData(index)
            sys_label.setVisible(False)
            conda_combo.setVisible(False)
            custom_edit.setVisible(False)
            btn_browse.setVisible(False)

            if m == 'system':
                sys_label.setText(f"当前: {sys.executable}")
                sys_label.setVisible(True)
            elif m == 'conda':
                conda_combo.setVisible(True)
            elif m == 'custom':
                custom_edit.setVisible(True)
                btn_browse.setVisible(True)

            validate_and_show_error(m)

        def on_browse():
            file_path, _ = QFileDialog.getOpenFileName(container, "选择 Python 解释器", "", "Python (*.exe);;All Files (*)")
            if file_path:
                custom_edit.setText(file_path)
                validate_and_show_error('custom', custom_path_from_edit=file_path)

        def on_mode_saved(index):
            m = mode_combo.itemData(index)
            conda_name = conda_combo.currentData() or '' if m == 'conda' else ''
            custom_path = custom_edit.text().strip() if m == 'custom' else ''
            self._save_python_path_cache(script.id, m, conda_name, custom_path)

        def on_conda_changed():
            conda_name = conda_combo.currentData() or ''
            self._save_python_path_cache(script.id, 'conda', conda_name, '')
            validate_and_show_error('conda')

        def on_custom_changed():
            custom_path = custom_edit.text().strip()
            self._save_python_path_cache(script.id, 'custom', '', custom_path)
            validate_and_show_error('custom')

        mode_combo.currentIndexChanged.connect(on_mode_changed)
        mode_combo.currentIndexChanged.connect(on_mode_saved)
        conda_combo.currentIndexChanged.connect(on_conda_changed)
        custom_edit.editingFinished.connect(on_custom_changed)
        btn_browse.clicked.connect(on_browse)

        # 触发初始化
        on_mode_changed(mode_combo.currentIndex())

        # 恢复conda/custom选择
        if mode == 'conda':
            conda_name = cfg.get('conda_name', '')
            ci = conda_combo.findData(conda_name)
            if ci >= 0:
                conda_combo.setCurrentIndex(ci)
        elif mode == 'custom':
            custom_edit.setText(cfg.get('custom_path', ''))

        # 初始校验
        if mode != 'system':
            validate_and_show_error(mode)

    def _show_about(self):
        """显示关于对话框"""
        QMessageBox.about(
            self,
            "关于 哆啦A梦百宝箱",
            "<h3>哆啦A梦百宝箱 v1.2</h3>"
            "<p>一个基于 PySide6 的 Python 脚本 GUI 管理工具。</p>"
            "<p><b>功能特性：</b></p>"
            "<ul>"
            "<li>YAML 配置驱动的参数界面</li>"
            "<li>多终端并行执行</li>"
            "<li>tqdm 进度条捕获</li>"
            "<li>GUI 内置 stdin 交互</li>"
            "<li>文件拖拽输入</li>"
            "<li>脚本搜索 / 排序 / 标签</li>"
            "<li>亮色 / 暗色主题切换</li>"
            "<li>自定义 Python 解释器路径（conda 兼容）</li>"
            "</ul>"
            "<p style='color:#888;'>统一脚本工具框架 — 让小工具拥有 GUI</p>"
        )

    def _add_script_directory(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择脚本目录")
        if dir_path:
            self.registry.add_script_dir(Path(dir_path))
            self._scan_scripts()

    # ── 脚本列表右键菜单 ───────────────────────────────
    def _show_script_context_menu(self, pos):
        item = self.script_list.itemAt(pos)
        if not item:
            return
        script_id = item.data(Qt.UserRole)
        script = self.registry.get_script(script_id)
        if not script:
            return

        menu = QMenu(self)

        act_copy = QAction("复制名称", self)
        act_copy.triggered.connect(lambda: self._copy_script_name(script))
        menu.addAction(act_copy)

        act_open_script = QAction("打开脚本文件", self)
        act_open_script.triggered.connect(lambda: self._open_script_file(script))
        menu.addAction(act_open_script)

        act_open_cfg = QAction("打开配置文件", self)
        act_open_cfg.triggered.connect(lambda: self._open_config_file(script))
        menu.addAction(act_open_cfg)

        menu.addSeparator()

        act_remove = QAction("从库中删除", self)
        act_remove.triggered.connect(lambda: self._remove_script_from_lib(script))
        menu.addAction(act_remove)

        menu.popup(self.script_list.mapToGlobal(pos))

    def _copy_script_name(self, script: 'ScriptConfig'):
        clipboard = QApplication.clipboard()
        clipboard.setText(script.name)

    def _open_script_file(self, script: 'ScriptConfig'):
        import os, sys
        path = str(script.script_path)
        if sys.platform == 'win32':
            os.startfile(path)
        elif sys.platform == 'darwin':
            os.system(f'open "{path}"')
        else:
            os.system(f'xdg-open "{path}"')

    def _open_config_file(self, script: 'ScriptConfig'):
        import os, sys
        cfg_path = script.script_path.with_suffix('.yaml')
        if not cfg_path.exists():
            cfg_path = script.script_path.with_suffix('.json')
        if cfg_path.exists():
            path = str(cfg_path)
            if sys.platform == 'win32':
                os.startfile(path)
            elif sys.platform == 'darwin':
                os.system(f'open "{path}"')
            else:
                os.system(f'xdg-open "{path}"')
        else:
            QMessageBox.information(self, "提示", f"未找到配置文件：\n{cfg_path}")

    def _remove_script_from_lib(self, script: 'ScriptConfig'):
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要从库中移除「{script.name}」？\n（不会删除文件，仅从列表移除）",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.registry.remove_script(script.id)
            self._scan_scripts()

    # ── 备份脚本库 ────────────────────────────────────
    def _backup_scripts(self):
        default_name = f"scripts_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.tar.gz"
        path, _ = QFileDialog.getSaveFileName(
            self, "保存备份", default_name,
            "Tarball (*.tar.gz);;All Files (*)"
        )
        if not path:
            return
        import tarfile, io
        try:
            with tarfile.open(path, "w:gz") as tar:
                tar.add("scripts", arcname="scripts")
            QMessageBox.information(self, "完成", f"备份已保存：\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "备份失败", f"无法创建备份：\n{e}")

    # ── 参数缓存 ──────────────────────────────────
    def _load_param_cache(self) -> Dict[str, Dict[str, Any]]:
        """加载参数缓存文件"""
        if not self._param_cache_path.exists():
            return {}
        try:
            with open(self._param_cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_param_cache(self) -> None:
        """保存当前脚本参数到缓存"""
        if not self.current_script:
            return
        cache = self._load_param_cache()
        params = {w.param_config['name']: w.get_value() for w in self.param_widgets}
        # 只保存非 None 值
        params = {k: v for k, v in params.items() if v is not None and v != ''}
        if params:
            cache[self.current_script.id] = params
        try:
            with open(self._param_cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_last_params(self) -> None:
        """从缓存载入上次参数并填充到控件"""
        if not self.current_script:
            return
        cache = self._load_param_cache()
        cached = cache.get(self.current_script.id, {})
        if not cached:
            return
        name_to_widget = {w.param_config['name']: w for w in self.param_widgets}
        for name, value in cached.items():
            if name in name_to_widget:
                try:
                    name_to_widget[name].set_value(value)
                except Exception:
                    pass

    def _reset_to_defaults(self) -> None:
        """将所有参数控件恢复为 YAML 里的默认值，同时重置Python路径"""
        if not self.current_script:
            return
        for widget in self.param_widgets:
            default_val = widget.param_config.get('default')
            try:
                widget.set_value(default_val)
            except Exception:
                pass
        # 重置Python路径为系统默认
        self._save_python_path_cache(self.current_script.id, 'system')
        self._rebuild_python_path_bar(self.current_script)

    def closeEvent(self, event):
        running = [(idx, t) for idx, t in self._running_tasks.items() if t['process_manager'].is_running()]
        if running:
            reply = QMessageBox.question(
                self, "确认退出",
                f"有 {len(running)} 个任务仍在运行，退出将强制终止。\n确定退出？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.No:
                event.ignore()
                return
            for idx, task in running:
                task['process_manager'].terminate()
        self._save_theme_preference()
        event.accept()


def main():
    # ── 高 DPI 支持（必须在 QApplication 之前设置）──
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    from PySide6.QtWidgets import QStyleFactory
    app.setStyle(QStyleFactory.create("Fusion"))
    global _app_custom_style
    _app_custom_style = CustomStyle()           # 存全局，后续注入 _is_dark
    app.setStyle(_app_custom_style)  # 复选框勾+下拉框箭头
    app.setApplicationName("哆啦A梦百宝箱")
    app.setApplicationVersion("1.1")

    # ── 字体平滑：Windows 上中文渲染优化 ──
    import platform
    if platform.system() == "Windows":
        # 使用支持中文的字体，优先微软雅黑
        font = QFont("Microsoft YaHei", 10)
        font.setStyleStrategy(QFont.PreferAntialias)      # 优先抗锯齿
        font.setHintingPreference(QFont.PreferNoHinting)   # 关闭 hinting（高 DPI 下更平滑）
        app.setFont(font)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
# test
