"""
进度监控控件
"""
from PySide6.QtWidgets import QProgressBar, QWidget, QVBoxLayout, QLabel, QHBoxLayout
from PySide6.QtCore import Qt, QTimer, Signal
from typing import Optional


class ProgressWidget(QWidget):
    """
    独立的进度监控区域

    特点：
    - 自动合并 tqdm 进度刷新
    - 显示当前进度百分比
    - 支持隐藏/显示
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_percentage = 0
        self._setup_ui()

    def _setup_ui(self):
        """初始化 UI"""
        layout = QHBoxLayout()
        layout.setContentsMargins(5, 4, 5, 4)
        layout.setSpacing(8)

        self.title_label = QLabel("进度")
        self.title_label.setFixedWidth(44)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet("font-size: 11pt; font-weight: 600;")
        layout.addWidget(self.title_label)

        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        self.label = QLabel("")
        self.label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        right_layout.addWidget(self.label)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        right_layout.addWidget(self.progress_bar)

        layout.addLayout(right_layout, stretch=1)

        self.setLayout(layout)

    def update_progress(self, percentage: int, detail: str = "") -> None:
        """
        更新进度

        Args:
            percentage: 0-100 的整数
        """
        # 限制范围
        percentage = max(0, min(100, percentage))

        # 仅当百分比或说明变化时更新
        label_text = detail if detail else f"{percentage}%"
        if percentage != self.current_percentage or self.label.text() != label_text:
            self.current_percentage = percentage
            self.progress_bar.setValue(percentage)
            self.label.setText(label_text)

    def reset(self) -> None:
        """重置进度"""
        self.current_percentage = 0
        self.progress_bar.reset()
        self.label.setText("")

    def show_message(self, message: str) -> None:
        """显示消息（替代进度）"""
        self.label.setText(message)
        self.progress_bar.setRange(0, 0)  # 无限进度条
        self.progress_bar.setValue(0)

    def hide_progress(self) -> None:
        """隐藏进度条区域"""
        self.hide()

    def show_progress(self) -> None:
        """显示进度条区域"""
        self.show()
