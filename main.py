#!/usr/bin/env python3
"""
哆啦A梦百宝箱 v1.1 - Python 脚本 GUI 中台
"""
import sys

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
    QSplitter, QLineEdit, QComboBox, QFrame, QMenu
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
        self.setWindowTitle("哆啦A梦百宝箱 v1.1")
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
        left_lay.addLayout(sort_row)

        tag_row = QHBoxLayout()
        tag_row.addWidget(QLabel("🏷"))
        tag_row.addStretch()
        self.clear_tags_btn = QPushButton("清除")
        self.clear_tags_btn.setFixedSize(36, 22)
        self.clear_tags_btn.setStyleSheet("font-size: 8pt; padding: 0;")
        self.clear_tags_btn.clicked.connect(self._clear_tag_filters)
        self.clear_tags_btn.setVisible(False)
        tag_row.addWidget(self.clear_tags_btn)
        left_lay.addLayout(tag_row)

        # 标签滚动区 - 高 DPI 下留足空间，始终预留滚动条高度避免漂移
        self.tag_scroll = QScrollArea()
        self.tag_scroll.setFixedHeight(44)  # 加高，175% DPI 下标签+滚动条不截断
        self.tag_scroll.setWidgetResizable(True)
        self.tag_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)  # 始终显示，避免出现/消失引起跳动
        self.tag_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tag_scroll.setFrameShape(QFrame.NoFrame)
        # 滚动条细一些
        self.tag_scroll.setStyleSheet(
            "QScrollBar:horizontal { height: 12px; }"
        )
        self.tag_container = QWidget()
        self.tag_layout = QHBoxLayout(self.tag_container)
        self.tag_layout.setContentsMargins(0, 2, 0, 0)  # 上边距给标签文字留空间
        self.tag_layout.setSpacing(6)
        self.tag_layout.addStretch()
        self.tag_scroll.setWidget(self.tag_container)
        left_lay.addWidget(self.tag_scroll)

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
        right_lay.addWidget(self.info_browser)

        # ── 描述区域 + 参数配置 + 终端输出 可拖动分割 ──
        top_splitter = QSplitter(Qt.Vertical)
        top_splitter.addWidget(self.info_browser)
        top_splitter.setStretchFactor(0, 0)  # info_browser 可压缩

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
        bottom_splitter.addWidget(term_box)

        # 参数区较窄，终端区较宽
        bottom_splitter.setSizes([350, 700])

        top_splitter.addWidget(bottom_splitter)
        top_splitter.setStretchFactor(1, 1)  # bottom_splitter 获得拉伸权重
        right_lay.addWidget(top_splitter, stretch=1)

        # 进度条
        self.progress_widget = ProgressWidget()
        self.progress_widget.setFixedHeight(50)
        right_lay.addWidget(self.progress_widget)

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
        while self.tag_layout.count() > 1:
            item = self.tag_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        all_tags: Set[str] = set()
        for script in self.registry.list_scripts():
            all_tags.update(script.tags)

        for tag in sorted(all_tags):
            btn = TagButton(tag)
            if tag in self._active_tags:
                btn.setChecked(True)
            btn.toggled_filter.connect(self._on_tag_toggled)
            self.tag_layout.insertWidget(self.tag_layout.count() - 1, btn)

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
        self.clear_tags_btn.setVisible(len(self._active_tags) > 0)
        self._refresh_script_list()

    def _clear_tag_filters(self):
        self._active_tags.clear()
        for i in range(self.tag_layout.count()):
            item = self.tag_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), TagButton):
                item.widget().setChecked(False)
        self.clear_tags_btn.setVisible(False)
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
        }
        self._running_tasks[tab_index] = task_info
        self._connect_task_signals(task_info, tab_index)
        terminal.setProperty("process_manager", pm)
        terminal.setProperty("task_info", task_info)
        sh.yn_prompt_detected.connect(lambda prompt, idx=tab_index: None)
        sh.text_prompt_detected.connect(lambda prompt, idx=tab_index: None)

        success = pm.start(script_path=self.current_script.script_path, arguments=args)
        if not success:
            QMessageBox.critical(self, "启动失败", "无法启动脚本进程")
            self.terminal_tabs.update_tab_title(tab_index, script_name, "failed")
            return

        self.terminal_tabs.update_tab_title(tab_index, script_name, "running")
        self.terminal_tabs.setCurrentIndex(tab_index)
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

        ti.process_output(text)
        if sh.process_output(text):
            QTimer.singleShot(100, lambda idx=tab_index: self._handle_stdin_interaction(idx))

    def _on_task_progress(self, tab_index: int):
        task = self._running_tasks.get(tab_index)
        if not task:
            return
        if self.terminal_tabs.currentIndex() == tab_index:
            self.progress_widget.update_progress(task['tqdm_interceptor'].get_last_percentage())

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
            self.progress_widget.reset()

    def _on_task_tab_finished(self, tab_index: int, exit_code: int, script_name: str):
        pass

    # ── 进度 & 状态 ─────────────────────────────
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

    # ── 其他 ─────────────────────────────────────
    def _show_about(self):
        """显示关于对话框"""
        QMessageBox.about(
            self,
            "关于 哆啦A梦百宝箱",
            "<h3>哆啦A梦百宝箱 v1.1</h3>"
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
        """将所有参数控件恢复为 YAML 里的默认值"""
        if not self.current_script:
            return
        for widget in self.param_widgets:
            default_val = widget.param_config.get('default')
            try:
                widget.set_value(default_val)
            except Exception:
                pass

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
