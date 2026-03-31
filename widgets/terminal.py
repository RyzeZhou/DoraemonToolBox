"""
终端输出控件：支持亮色/暗色主题切换
"""
from PySide6.QtWidgets import QTextBrowser
from PySide6.QtGui import QFont, QColor, QTextCharFormat, QTextCursor
from PySide6.QtCore import Qt
from typing import Optional


# 主题样式
_DARK_STYLE = """
TerminalWidget {
    background-color: #1e1e1e;
    color: #d4d4d4;
    border: 1px solid #333;
    padding: 4px;
}
"""

_LIGHT_STYLE = """
TerminalWidget {
    background-color: #1e1e1e;
    color: #d4d4d4;
    border: 1px solid #999;
    padding: 4px;
}
"""


class TerminalWidget(QTextBrowser):
    """
    终端输出显示控件

    特性：
    - 深色终端外观（与主题独立，终端始终深色以保持终端风格）
    - 等宽字体
    - 自动滚动到底部
    - 支持追加文本和颜色
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_dark = True
        self._setup_style()

    def _setup_style(self):
        """配置样式"""
        self.setStyleSheet(_DARK_STYLE if self._is_dark else _LIGHT_STYLE)

        font = QFont("Consolas, 'Courier New', monospace")
        font.setStyleHint(QFont.Monospace)
        font.setPointSize(9)
        self.setFont(font)

        self.setReadOnly(True)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)

    def apply_theme(self, is_dark: bool):
        """应用主题（终端保持深色风格，亮色主题下略微调亮边框）"""
        self._is_dark = is_dark
        self._setup_style()

    def append_text(self, text: str, color: Optional[str] = None) -> None:
        """
        追加文本到终端

        Args:
            text: 要追加的文本
            color: 可选的颜色 (十六进制字符串，如 '#ff0000')
        """
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)

        if color:
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color))
            cursor.setCharFormat(fmt)
        else:
            # 重置为默认颜色
            fmt = QTextCharFormat()
            fmt.setForeground(QColor("#d4d4d4"))
            cursor.setCharFormat(fmt)

        cursor.insertText(text)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def clear_terminal(self) -> None:
        """清空终端内容"""
        self.clear()
