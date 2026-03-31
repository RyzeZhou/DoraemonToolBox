"""
参数控件：动态生成不同类型的参数输入控件
支持文件拖拽（file / directory / multi_file 类型）
"""
from PySide6.QtWidgets import (
    QWidget, QFormLayout, QLineEdit, QPushButton, QFileDialog,
    QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox, QHBoxLayout, QVBoxLayout,
    QLabel, QMessageBox
)
from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from typing import Dict, Any, Optional


class DragDropLineEdit(QLineEdit):
    """
    支持拖拽文件/文件夹的输入框

    - file 模式：接受单个文件
    - directory 模式：接受文件夹
    - multi_file 模式：接受多个文件（追加到已有内容，分号分隔）
    """

    def __init__(self, mode: str = "file", parent=None):
        super().__init__(parent)
        self._drag_mode = mode  # file | directory | multi_file
        self.setAcceptDrops(True)
        self.setPlaceholderText("拖拽文件/文件夹到此处，或点击浏览..." if mode != "directory"
                                else "拖拽文件夹到此处，或点击浏览...")

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            # 高亮反馈
            self.setStyleSheet(self.styleSheet() + "border: 2px dashed #0078d4;")
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        # 移除高亮：直接清除内联样式，让父样式表生效
        self.setStyleSheet("")
        event.accept()

    def dropEvent(self, event: QDropEvent):
        # 移除高亮
        self.setStyleSheet("")

        urls = event.mimeData().urls()
        if not urls:
            event.ignore()
            return

        paths = []
        for url in urls:
            if url.isLocalFile():
                path = url.toLocalFile()
                # Windows: 修复 Qt 返回的路径（斜杠标准化）
                path = path.replace('/', '\\') if '\\' in path else path
                paths.append(path)

        if not paths:
            event.ignore()
            return

        if self._drag_mode == "directory":
            # 取第一个路径，必须是目录
            p = paths[0]
            import os
            if os.path.isdir(p):
                self.setText(p)
                event.acceptProposedAction()
            else:
                event.ignore()

        elif self._drag_mode == "multi_file":
            # 追加模式
            current = self.text().strip()
            if current:
                existing = [f.strip() for f in current.split(';') if f.strip()]
                all_paths = existing + paths
            else:
                all_paths = paths
            self.setText(';'.join(all_paths))
            event.acceptProposedAction()

        else:
            # file 模式：取第一个
            self.setText(paths[0])
            event.acceptProposedAction()


class ParameterWidget(QWidget):
    """
    单个参数控件

    根据配置动态创建对应的输入控件
    """
    value_changed = Signal()

    def __init__(self, param_config: Dict[str, Any], parent=None):
        """
        初始化参数控件

        Args:
            param_config: 参数配置字典
                {
                    'name': 'input_file',
                    'label': '输入文件',
                    'type': 'file',  # string, file, directory, integer, float, boolean, choice
                    'required': True,
                    'default': None,
                    'file_filter': 'JSON Files (*.json)',
                    'choices': ['a', 'b'],
                    'min': 0,
                    'max': 100,
                    ...
                }
        """
        super().__init__(parent)
        self.param_config = param_config
        self._value = param_config.get('default')
        self.control = None
        self.init_ui()

    def init_ui(self):
        """初始化 UI"""
        layout = QFormLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(8)
        # 标签过长时自动换行，不挤压控件
        layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        ptype = self.param_config.get('type', 'string')
        label_text = self.param_config.get('label', self.param_config['name'])
        required = self.param_config.get('required', False)
        label = QLabel(f"{label_text}:" if required else f"{label_text} (可选):")
        label.setStyleSheet("font-weight: bold;" if required else "")
        label.setWordWrap(True)
        # 鼠标悬停显示 description 或 help
        desc = self.param_config.get('description') or self.param_config.get('help') or ''
        if desc:
            label.setToolTip(desc)

        # 规范：有 choices 字段的参数统一渲染为下拉框，不论 type 写的是什么
        has_choices = bool(self.param_config.get('choices'))

        # 根据类型创建控件
        if has_choices:
            self._create_choice_control(layout, label)

        elif ptype == 'string':
            self.control = QLineEdit()
            self.control.setText(str(self._value) if self._value is not None else '')
            self.control.textChanged.connect(self._on_value_changed)
            layout.addRow(label, self.control)

        elif ptype == 'file':
            self._create_file_control(layout, label)

        elif ptype == 'save_file':
            self._create_save_file_control(layout, label)

        elif ptype == 'directory':
            self._create_directory_control(layout, label)

        elif ptype == 'integer':
            self._create_integer_control(layout, label)

        elif ptype == 'float':
            self._create_float_control(layout, label)

        elif ptype == 'boolean':
            self.control = QCheckBox()
            if self._value:
                self.control.setChecked(True)
            self.control.toggled.connect(self._on_value_changed)
            layout.addRow(label, self.control)

        elif ptype == 'list':
            self._create_list_control(layout, label)

        elif ptype == 'multi_file':
            self._create_multi_file_list_control(layout, label)

        elif ptype == 'list_string':
            self._create_list_string_control(layout, label)

        else:
            # 未知类型，回退到 string
            self.control = QLineEdit()
            self.control.setText(str(self._value) if self._value is not None else '')
            self.control.textChanged.connect(self._on_value_changed)
            layout.addRow(label, self.control)

        self.setLayout(layout)

    def _create_file_control(self, layout: QFormLayout, label: QLabel):
        """创建文件选择控件（支持拖拽）

        布局：标签独占一行 → 输入框+按钮独立一行（占满宽度）
        """
        self.control = DragDropLineEdit(mode="file")
        self.control.setMinimumHeight(28)
        self.control.setText(str(self._value) if self._value is not None else '')
        self.control.textChanged.connect(self._on_value_changed)

        browse_btn = QPushButton('浏览...')
        browse_btn.setMinimumHeight(28)
        browse_btn.clicked.connect(self._browse_file)

        hbox = QHBoxLayout()
        hbox.addWidget(self.control, 1)
        hbox.addWidget(browse_btn)

        # 两行合并到一个 vbox，再作为一行整体加入 FormLayout
        vbox = QVBoxLayout()
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(4)
        vbox.addWidget(label)
        vbox.addLayout(hbox)

        wrapper = QWidget()
        wrapper.setLayout(vbox)
        layout.addRow(wrapper)

    def _create_save_file_control(self, layout: QFormLayout, label: QLabel):
        """创建保存文件控件（弹出保存对话框，而非打开文件）

        布局：标签独占一行 → 输入框+按钮独立一行（占满宽度）
        """
        self.control = DragDropLineEdit(mode="file")
        self.control.setMinimumHeight(28)
        self.control.setText(str(self._value) if self._value is not None else '')
        self.control.textChanged.connect(self._on_value_changed)

        browse_btn = QPushButton('浏览...')
        browse_btn.setMinimumHeight(28)
        browse_btn.clicked.connect(self._browse_save_file)

        hbox = QHBoxLayout()
        hbox.addWidget(self.control, 1)
        hbox.addWidget(browse_btn)

        vbox = QVBoxLayout()
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(4)
        vbox.addWidget(label)
        vbox.addLayout(hbox)

        wrapper = QWidget()
        wrapper.setLayout(vbox)
        layout.addRow(wrapper)

    def _browse_save_file(self):
        """保存文件浏览（getSaveFileName）"""
        title = self.param_config.get('dialog_title', '保存文件')
        file_filter = self.param_config.get('file_filter', 'All Files (*)')
        # getSaveFileName: 弹出保存对话框，若文件已存在会提示覆盖
        file_path, _ = QFileDialog.getSaveFileName(self, title, filter=file_filter)
        if file_path:
            self.control.setText(file_path)

    def _create_directory_control(self, layout: QFormLayout, label: QLabel):
        """创建目录选择控件（支持拖拽）

        布局：标签独占一行 → 输入框+按钮独立一行（占满宽度）
        """
        self.control = DragDropLineEdit(mode="directory")
        self.control.setMinimumHeight(28)
        self.control.setText(str(self._value) if self._value is not None else '')
        self.control.textChanged.connect(self._on_value_changed)

        browse_btn = QPushButton('浏览...')
        browse_btn.setMinimumHeight(28)
        browse_btn.clicked.connect(self._browse_directory)

        hbox = QHBoxLayout()
        hbox.addWidget(self.control, 1)
        hbox.addWidget(browse_btn)

        vbox = QVBoxLayout()
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(4)
        vbox.addWidget(label)
        vbox.addLayout(hbox)

        wrapper = QWidget()
        wrapper.setLayout(vbox)
        layout.addRow(wrapper)

    def _create_choice_control(self, layout: QFormLayout, label: QLabel):
        """创建下拉框控件

        支持两种写法：
        1. choices: [1, 2, 3]                          → 显示1/2/3，返回1/2/3
        2. choices: ["标签A", "标签B"] + values: [1, 2] → 显示标签，返回对应值
        """
        self.control = QComboBox()
        choices = self.param_config.get('choices', [])
        values = self.param_config.get('values', None)

        if values is not None:
            # labels + values 映射模式
            for display_text, data_val in zip(choices, values):
                self.control.addItem(str(display_text), data_val)
        else:
            # 简单模式：choices 既当显示文本也当数据值
            for choice in choices:
                self.control.addItem(str(choice), choice)

        # 设置当前值（与 data 值匹配）
        current_value = self._value
        if current_value is not None:
            idx = self.control.findData(current_value)
            if idx >= 0:
                self.control.setCurrentIndex(idx)

        self.control.currentIndexChanged.connect(self._on_value_changed)

        # 路径类参数用两层结构，其他用标准 addRow
        ptype = self.param_config.get('type', 'string')
        if ptype in ('file', 'directory', 'multi_file'):
            # 复用两层结构布局
            hbox = QHBoxLayout()
            hbox.addWidget(self.control, 1)
            vbox = QVBoxLayout()
            vbox.setContentsMargins(0, 0, 0, 0)
            vbox.setSpacing(4)
            vbox.addWidget(label)
            vbox.addLayout(hbox)
            wrapper = QWidget()
            wrapper.setLayout(vbox)
            layout.addRow(wrapper)
        else:
            layout.addRow(label, self.control)

    def _create_integer_control(self, layout: QFormLayout, label: QLabel):
        """创建整数输入控件"""
        self.control = QSpinBox()
        min_val = self.param_config.get('min', -2147483647)
        max_val = self.param_config.get('max', 2147483647)

        # 自动识别 threads 参数，max 约束为 CPU 线程数
        param_name = self.param_config.get('name', '').lower()
        if param_name == 'threads' and 'max' not in self.param_config:
            try:
                import multiprocessing
                max_val = multiprocessing.cpu_count()
            except Exception:
                pass

        self.control.setRange(min_val, max_val)

        default = self._value if self._value is not None else 0
        self.control.setValue(default)
        self.control.valueChanged.connect(self._on_value_changed)
        layout.addRow(label, self.control)

    def _create_float_control(self, layout: QFormLayout, label: QLabel):
        """创建浮点数输入控件"""
        self.control = QDoubleSpinBox()
        min_val = self.param_config.get('min', -1e10)
        max_val = self.param_config.get('max', 1e10)
        self.control.setRange(min_val, max_val)
        self.control.setDecimals(self.param_config.get('decimals', 6))

        default = self._value if self._value is not None else 0.0
        self.control.setValue(default)
        self.control.valueChanged.connect(self._on_value_changed)
        layout.addRow(label, self.control)

    def _browse_file(self):
        """文件浏览"""
        title = self.param_config.get('dialog_title', '选择文件')
        file_filter = self.param_config.get('file_filter', 'All Files (*)')
        file_path, _ = QFileDialog.getOpenFileName(self, title, filter=file_filter)
        if file_path:
            self.control.setText(file_path)

    def _browse_directory(self):
        """目录浏览"""
        title = self.param_config.get('dialog_title', '选择目录')
        dir_path = QFileDialog.getExistingDirectory(self, title)
        if dir_path:
            self.control.setText(dir_path)

    def _on_value_changed(self, *args):
        """值改变信号"""
        self.value_changed.emit()

    def get_value(self) -> Any:
        """
        获取当前控件的值

        Returns:
            根据类型返回对应的 Python 值
        """
        ptype = self.param_config.get('type', 'string')

        if ptype == 'string':
            if hasattr(self.control, 'text'):
                return self.control.text().strip() or None
            return self.control.currentText().strip() or None

        elif ptype in ['file', 'directory', 'save_file']:
            text = self.control.text().strip() if hasattr(self.control, 'text') else self.control.currentText().strip()
            return text if text else None

        elif ptype == 'choice':
            return self.control.currentData()

        elif ptype == 'integer':
            return self.control.value()

        elif ptype == 'float':
            return self.control.value()

        elif ptype == 'boolean':
            return self.control.isChecked()

        else:
            return self.control.text().strip() if hasattr(self.control, 'text') else None

    def set_value(self, value: Any) -> None:
        """设置控件值"""
        ptype = self.param_config.get('type', 'string')

        if ptype == 'string':
            self.control.setText(str(value) if value is not None else '')

        elif ptype in ['file', 'directory', 'save_file']:
            self.control.setText(str(value) if value is not None else '')

        elif ptype == 'choice':
            idx = self.control.findData(value)
            if idx >= 0:
                self.control.setCurrentIndex(idx)

        elif ptype in ['integer', 'float']:
            if value is not None:
                self.control.setValue(float(value) if ptype == 'float' else int(value))

        elif ptype == 'boolean':
            self.control.setChecked(bool(value))

        # 未知类型，回退到 string
        else:
            self.control = QLineEdit()
            self.control.setText(str(self._value) if self._value is not None else '')
            self.control.textChanged.connect(self._on_value_changed)
            layout.addRow(label, self.control)

    def _create_list_control(self, layout: QFormLayout, label: QLabel):
        """创建动态列表控件"""
        from PySide6.QtWidgets import QPushButton, QScrollArea, QVBoxLayout, QWidget

        container = QWidget()
        container_layout = QVBoxLayout()
        container_layout.setContentsMargins(0, 0, 0, 0)
        container.setLayout(container_layout)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMaximumHeight(200)

        list_container = QWidget()
        self.list_layout = QVBoxLayout()
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        list_container.setLayout(self.list_layout)

        scroll_area.setWidget(list_container)
        container_layout.addWidget(scroll_area)

        # 按钮区域
        btn_layout = QHBoxLayout()
        add_btn = QPushButton('+ 添加')
        add_btn.clicked.connect(lambda: self._add_list_item())
        btn_layout.addWidget(add_btn)
        btn_layout.addStretch()
        container_layout.addLayout(btn_layout)

        layout.addRow(label, container)

        # 添加初始空项提示
        self._add_list_item()

    def _create_multi_file_control(self, layout: QFormLayout, label: QLabel):
        """创建多文件选择控件（支持拖拽多个文件）

        布局：标签独占一行 → 输入框+按钮独立一行（占满宽度）
        """
        self.control = DragDropLineEdit(mode="multi_file")
        self.control.setText(str(self._value) if self._value is not None else '')
        self.control.textChanged.connect(self._on_value_changed)

        browse_btn = QPushButton('浏览... (多选)')
        browse_btn.setMinimumHeight(28)
        browse_btn.clicked.connect(self._browse_multi_file)

        hbox = QHBoxLayout()
        hbox.addWidget(self.control, 1)
        hbox.addWidget(browse_btn)

        vbox = QVBoxLayout()
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(4)
        vbox.addWidget(label)
        vbox.addLayout(hbox)

        wrapper = QWidget()
        wrapper.setLayout(vbox)
        layout.addRow(wrapper)

    def _create_list_string_control(self, layout: QFormLayout, label: QLabel):
        """创建多值文本输入控件（每行一个输入框，可增删）

        布局：标签独占一行 → 内容区域（每行 + 输入框 + − 按钮）
        """
        self._list_string_rows: list = []  # 每行: QLineEdit

        container = QWidget()
        vbox = QVBoxLayout()
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(4)
        container.setLayout(vbox)

        self._list_string_rows_widget = QWidget()
        self._list_string_layout = QVBoxLayout()
        self._list_string_layout.setContentsMargins(0, 0, 0, 0)
        self._list_string_layout.setSpacing(4)
        self._list_string_rows_widget.setLayout(self._list_string_layout)
        vbox.addWidget(self._list_string_rows_widget)

        # 两行：标签独占一行，内容区域跨满列
        layout.addRow(label)
        layout.addRow(container)

        initial = self._value if isinstance(self._value, list) else []
        if not initial:
            self._add_list_string_row()
        else:
            for v in initial:
                self._add_list_string_row(str(v))

    def _add_list_string_row(self, value: str = '', after_idx: int = -1):
        """在指定位置后插入一行，after_idx=-1 表示追加到末尾"""
        row = QWidget()
        row_lay = QHBoxLayout()
        row_lay.setContentsMargins(0, 0, 0, 0)
        row_lay.setSpacing(4)

        edit = QLineEdit()
        edit.setMinimumHeight(28)
        edit.setText(value)
        edit.setPlaceholderText("输入值...")
        edit.textChanged.connect(self._on_value_changed)

        add_btn = QPushButton('+')
        add_btn.setMinimumHeight(28)
        add_btn.setStyleSheet("font: 13pt;")
        add_btn.setToolTip("在此行后插入一行")
        add_btn.clicked.connect(lambda: self._insert_list_string_row_after(row))

        remove_btn = QPushButton('-')
        remove_btn.setMinimumHeight(28)
        remove_btn.setStyleSheet("font: 13pt; color: #cc3333;")
        remove_btn.setToolTip("删除此行")
        remove_btn.clicked.connect(lambda: self._remove_list_string_row(row, edit))

        row_lay.addWidget(edit, 1)
        row_lay.addWidget(add_btn)
        row_lay.addWidget(remove_btn)
        row.setLayout(row_lay)

        if after_idx < 0 or after_idx >= self._list_string_layout.count():
            self._list_string_layout.addWidget(row)
        else:
            self._list_string_layout.insertWidget(after_idx + 1, row)
        self._list_string_rows.append(edit)

    def _insert_list_string_row_after(self, row_widget: QWidget):
        idx = self._list_string_layout.indexOf(row_widget)
        self._add_list_string_row(after_idx=idx)

    def _remove_list_string_row(self, row: QWidget, edit: QLineEdit):
        if self._list_string_layout.count() <= 1:
            edit.clear()
            edit.setFocus()
            return
        self._list_string_layout.removeWidget(row)
        row.deleteLater()
        if edit in self._list_string_rows:
            self._list_string_rows.remove(edit)
        self._on_value_changed()

    def _create_multi_file_list_control(self, layout: QFormLayout, label: QLabel):
        """创建多路径输入控件（每行一个输入框，可增删）

        布局：标签独占一行 → 内容区域（每行：输入框 + 浏览 + + − 按钮）
        """
        self._multi_file_rows: list = []  # 每行: DragDropLineEdit

        container = QWidget()
        vbox = QVBoxLayout()
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(4)
        container.setLayout(vbox)

        self._multi_file_rows_widget = QWidget()
        self._multi_file_layout = QVBoxLayout()
        self._multi_file_layout.setContentsMargins(0, 0, 0, 0)
        self._multi_file_layout.setSpacing(4)
        self._multi_file_rows_widget.setLayout(self._multi_file_layout)
        vbox.addWidget(self._multi_file_rows_widget)

        # 两行：标签独占一行，内容区域跨满列
        layout.addRow(label)
        layout.addRow(container)

        initial = self._value if isinstance(self._value, list) else []
        if not initial:
            self._add_multi_file_row()
        else:
            for v in initial:
                self._add_multi_file_row(str(v))

    def _add_multi_file_row(self, value: str = '', after_idx: int = -1):
        """添加一行 multi_file 输入框"""
        row = QWidget()
        row_lay = QHBoxLayout()
        row_lay.setContentsMargins(0, 0, 0, 0)
        row_lay.setSpacing(4)

        drag_edit = DragDropLineEdit(mode="file")
        drag_edit.setMinimumHeight(28)
        drag_edit.setText(value)
        drag_edit.textChanged.connect(self._on_value_changed)

        browse_btn = QPushButton('浏览...')
        browse_btn.setMinimumHeight(28)
        browse_btn.clicked.connect(lambda: self._browse_single_file_row(drag_edit))

        add_btn = QPushButton('+')
        add_btn.setMinimumHeight(28)
        add_btn.setStyleSheet("font: 13pt;")
        add_btn.setToolTip("在此行后插入一行")
        add_btn.clicked.connect(lambda: self._insert_multi_file_row_after(row))

        remove_btn = QPushButton('-')
        remove_btn.setMinimumHeight(28)
        remove_btn.setStyleSheet("font: 13pt; color: #cc3333;")
        remove_btn.setToolTip("删除此行")
        remove_btn.clicked.connect(lambda: self._remove_multi_file_row(row, drag_edit))

        row_lay.addWidget(drag_edit, 1)
        row_lay.addWidget(browse_btn)
        row_lay.addWidget(add_btn)
        row_lay.addWidget(remove_btn)
        row.setLayout(row_lay)

        if after_idx < 0 or after_idx >= self._multi_file_layout.count():
            self._multi_file_layout.addWidget(row)
        else:
            self._multi_file_layout.insertWidget(after_idx + 1, row)
        self._multi_file_rows.append(drag_edit)

    def _insert_multi_file_row_after(self, row_widget: QWidget):
        idx = self._multi_file_layout.indexOf(row_widget)
        self._add_multi_file_row(after_idx=idx)

    def _remove_multi_file_row(self, row: QWidget, edit: DragDropLineEdit):
        if self._multi_file_layout.count() <= 1:
            edit.setText('')
            edit.setFocus()
            return
        self._multi_file_layout.removeWidget(row)
        row.deleteLater()
        if edit in self._multi_file_rows:
            self._multi_file_rows.remove(edit)
        self._on_value_changed()

    def _browse_single_file_row(self, edit: DragDropLineEdit):
        title = self.param_config.get('dialog_title', '选择文件')
        file_filter = self.param_config.get('file_filter', 'All Files (*)')
        path, _ = QFileDialog.getOpenFileName(self, title, filter=file_filter)
        if path:
            edit.setText(path)

    def _add_list_item(self):
        """添加列表项"""
        item_type = self.param_config.get('item_type', 'string')
        item_config = self.param_config.get('item_config', {}).copy()

        # 创建子控件
        item_widget = QWidget()
        item_layout = QHBoxLayout()
        item_layout.setContentsMargins(0, 0, 0, 0)

        # 根据类型创建对应的编辑器
        if item_type == 'string':
            editor = QLineEdit()
            editor.setText(item_config.get('default', ''))
            editor.setPlaceholderText(item_config.get('label', '值'))
            item_layout.addWidget(editor)

        elif item_type == 'integer':
            editor = QSpinBox()
            editor.setRange(item_config.get('min', -2147483647), item_config.get('max', 2147483647))
            editor.setValue(item_config.get('default', 0))
            item_layout.addWidget(editor)

        elif item_type == 'float':
            editor = QDoubleSpinBox()
            editor.setRange(item_config.get('min', -1e10), item_config.get('max', 1e10))
            editor.setValue(item_config.get('default', 0.0))
            item_layout.addWidget(editor)

        elif item_type == 'boolean':
            editor = QCheckBox()
            editor.setChecked(item_config.get('default', False))
            item_layout.addWidget(editor)

        else:
            editor = QLineEdit()
            editor.setText(str(item_config.get('default', '')))
            item_layout.addWidget(editor)

        # 删除按钮
        remove_btn = QPushButton('×')
        remove_btn.setMaximumWidth(30)
        remove_btn.clicked.connect(lambda: self._remove_list_item(item_widget))
        item_layout.addWidget(remove_btn)

        item_widget.setLayout(item_layout)
        self.list_layout.addWidget(item_widget)

    def _remove_list_item(self, item_widget):
        """移除列表项"""
        self.list_layout.removeWidget(item_widget)
        item_widget.deleteLater()

    def _browse_multi_file(self):
        """多文件浏览"""
        title = self.param_config.get('dialog_title', '选择文件')
        file_filter = self.param_config.get('file_filter', 'All Files (*)')
        files, _ = QFileDialog.getOpenFileNames(self, title, filter=file_filter)
        if files:
            current_text = self.control.text()
            if current_text:
                current_files = current_text.split(';')
                all_files = current_files + files
            else:
                all_files = files
            # 使用分号分隔多个文件
            self.control.setText(';'.join(all_files))

    def _on_value_changed(self, *args):
        """值改变信号"""
        self.value_changed.emit()

    def get_value(self) -> Any:
        """
        获取当前控件的值

        Returns:
            根据类型返回对应的 Python 值
        """
        ptype = self.param_config.get('type', 'string')

        if ptype == 'string':
            if hasattr(self.control, 'text'):
                return self.control.text().strip() or None
            return self.control.currentText().strip() or None

        elif ptype in ['file', 'directory', 'save_file']:
            text = self.control.text().strip() if hasattr(self.control, 'text') else self.control.currentText().strip()
            return text if text else None

        elif ptype == 'choice':
            return self.control.currentData()

        elif ptype == 'integer':
            return self.control.value()

        elif ptype == 'float':
            return self.control.value()

        elif ptype == 'boolean':
            return self.control.isChecked()

        elif ptype == 'list':
            # 收集所有子控件的值
            values = []
            for i in range(self.list_layout.count()):
                item_widget = self.list_layout.itemAt(i).widget()
                if item_widget:
                    # 找到编辑器控件（排除删除按钮）
                    editor = None
                    for child in item_widget.children():
                        if isinstance(child, (QLineEdit, QSpinBox, QDoubleSpinBox, QCheckBox)):
                            editor = child
                            break
                    if editor:
                        if isinstance(editor, QLineEdit):
                            val = editor.text().strip()
                            values.append(val if val else None)
                        elif isinstance(editor, QSpinBox):
                            values.append(editor.value())
                        elif isinstance(editor, QDoubleSpinBox):
                            values.append(editor.value())
                        elif isinstance(editor, QCheckBox):
                            values.append(editor.isChecked())
            return [v for v in values if v is not None]

        elif ptype == 'multi_file':
            values = [e.text().strip() for e in getattr(self, '_multi_file_rows', [])
                      if e.text().strip()]
            return values if values else None

        elif ptype == 'list_string':
            values = [e.text().strip() for e in getattr(self, '_list_string_rows', [])
                      if e.text().strip()]
            return values if values else None

        else:
            return self.control.text().strip() if hasattr(self.control, 'text') else None

    def set_value(self, value: Any) -> None:
        """设置控件值"""
        ptype = self.param_config.get('type', 'string')

        if ptype == 'string':
            self.control.setText(str(value) if value is not None else '')

        elif ptype in ['file', 'directory', 'save_file']:
            self.control.setText(str(value) if value is not None else '')

        elif ptype == 'choice':
            idx = self.control.findData(value)
            if idx >= 0:
                self.control.setCurrentIndex(idx)

        elif ptype in ['integer', 'float']:
            if value is not None:
                self.control.setValue(float(value) if ptype == 'float' else int(value))

        elif ptype == 'boolean':
            self.control.setChecked(bool(value))

        elif ptype == 'list':
            # 清除现有项
            while self.list_layout.count():
                item = self.list_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            # 添加新项
            if isinstance(value, list):
                for val in value:
                    # 根据item_type创建对应编辑器并设置值
                    item_type = self.param_config.get('item_type', 'string')
                    item_config = self.param_config.get('item_config', {}).copy()
                    item_widget = QWidget()
                    item_layout = QHBoxLayout()
                    item_layout.setContentsMargins(0, 0, 0, 0)

                    if item_type == 'string':
                        editor = QLineEdit()
                        editor.setText(str(val) if val is not None else '')
                        item_layout.addWidget(editor)
                    elif item_type == 'integer':
                        editor = QSpinBox()
                        editor.setRange(item_config.get('min', -2147483647), item_config.get('max', 2147483647))
                        if val is not None:
                            editor.setValue(int(val))
                        item_layout.addWidget(editor)
                    elif item_type == 'float':
                        editor = QDoubleSpinBox()
                        editor.setRange(item_config.get('min', -1e10), item_config.get('max', 1e10))
                        if val is not None:
                            editor.setValue(float(val))
                        item_layout.addWidget(editor)
                    elif item_type == 'boolean':
                        editor = QCheckBox()
                        editor.setChecked(bool(val))
                        item_layout.addWidget(editor)
                    else:
                        editor = QLineEdit()
                        editor.setText(str(val) if val is not None else '')
                        item_layout.addWidget(editor)

                    remove_btn = QPushButton('×')
                    remove_btn.setMaximumWidth(30)
                    remove_btn.clicked.connect(lambda: self._remove_list_item(item_widget))
                    item_layout.addWidget(remove_btn)

                    item_widget.setLayout(item_layout)
                    self.list_layout.addWidget(item_widget)

        elif ptype == 'multi_file':
            if not hasattr(self, '_multi_file_rows'):
                return
            vals = value if isinstance(value, list) else ([value] if value else [])
            # 清空现有行，重新建立
            while self._multi_file_layout.count():
                w = self._multi_file_layout.takeAt(0).widget()
                if w:
                    w.deleteLater()
            self._multi_file_rows.clear()
            if vals:
                for v in vals:
                    self._add_multi_file_row(str(v))
            else:
                self._add_multi_file_row()

        elif ptype == 'list_string':
            if not hasattr(self, '_list_string_rows'):
                return
            vals = value if isinstance(value, list) else ([value] if value else [])
            while self._list_string_layout.count():
                w = self._list_string_layout.takeAt(0).widget()
                if w:
                    w.deleteLater()
            self._list_string_rows.clear()
            if vals:
                for v in vals:
                    self._add_list_string_row(str(v))
            else:
                self._add_list_string_row()
