"""
进度监控控件
"""
from PySide6.QtWidgets import QProgressBar, QWidget, QVBoxLayout, QLabel
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
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # 标签
        self.label = QLabel("进度:")
        layout.addWidget(self.label)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        layout.addWidget(self.progress_bar)

        self.setLayout(layout)

    def update_progress(self, percentage: int) -> None:
        """
        更新进度

        Args:
            percentage: 0-100 的整数
        """
        # 限制范围
        percentage = max(0, min(100, percentage))

        # 仅当百分比变化时更新
        if percentage != self.current_percentage:
            self.current_percentage = percentage
            self.progress_bar.setValue(percentage)
            self.label.setText(f"进度: {percentage}%")

    def reset(self) -> None:
        """重置进度"""
        self.current_percentage = 0
        self.progress_bar.reset()
        self.label.setText("进度:")

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
