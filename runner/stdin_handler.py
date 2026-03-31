"""
stdin 交互处理器：检测询问并弹出对话框获取用户输入
"""
import re
from PySide6.QtWidgets import QMessageBox, QInputDialog, QWidget
from PySide6.QtCore import QObject, Signal, Qt, QTimer


class StdinHandler(QObject):
    """
    stdin 交互处理器

    检测脚本输出中的询问模式，显示对话框并将用户选择写回 stdin

    支持的询问：
    - Y/N 确认 (是否继续？/Continue?等)
    - 文本输入 (请输入...)
    """

    # 询问模式正则
    PROMPT_PATTERNS = [
        re.compile(r'是否继续\s*[?？]\s*\(?[y/n]\)?', re.IGNORECASE),
        re.compile(r'继续\s*[?？]\s*\(?[y/n]\)?', re.IGNORECASE),
        re.compile(r'Continue\s*\?\s*\(?[y/n]\)?', re.IGNORECASE),
        re.compile(r'Proceed\s*\?\s*\(?[y/n]\)?', re.IGNORECASE),
        re.compile(r'\(y/n\)', re.IGNORECASE),
    ]

    # "按回车"/"Press Enter"/"Press any key" 等等待类提示
    WAIT_PROMPT = re.compile(
        r'(按.*回车|按.*键|Press\s+(any\s+)?key|Press\s+Enter|输入.*退出|to\s+exit)',
        re.IGNORECASE
    )

    INPUT_PROMPT = re.compile(r'请输入\s*[:：]?\s*', re.IGNORECASE)

    # 信号
    yn_prompt_detected = Signal(str)  # 问题文本
    text_prompt_detected = Signal(str)  # 提示文本
    response_sent = Signal(str)  # 响应已发送

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pending = False
        self._prompt_type = None  # 'yn' 或 'text'
        self._buffer = ""
        self._parent_widget = None
        self._current_prompt = ""

    def set_parent_widget(self, widget):
        """设置用于弹窗的父窗口"""
        self._parent_widget = widget

    def process_output(self, text: str) -> bool:
        """
        处理输出，检测是否需要用户交互

        Args:
            text: 输出文本

        Returns:
            True 如果检测到交互请求需要处理
        """
        self._buffer += text

        # 按行检查
        lines = self._buffer.split('\n')
        # 检查最近的行
        recent_lines = lines[-5:] if len(lines) > 5 else lines

        for line in reversed(recent_lines):
            line = line.strip()
            # 检测 Y/N 询问
            for pattern in self.PROMPT_PATTERNS:
                if pattern.search(line):
                    self._pending = True
                    self._prompt_type = 'yn'
                    self._current_prompt = line
                    self.yn_prompt_detected.emit(line)
                    return True

            # 检测文本输入询问
            if self.INPUT_PROMPT.search(line):
                self._pending = True
                self._prompt_type = 'text'
                self._current_prompt = line
                self.text_prompt_detected.emit(line)
                return True

            # 检测"按回车"/"Press Enter"等等待提示 → 自动发送空行
            if self.WAIT_PROMPT.search(line):
                self._pending = True
                self._prompt_type = 'wait'
                self._current_prompt = line
                self.text_prompt_detected.emit(line)
                return True

        return False

    def has_pending(self) -> bool:
        """是否有待处理的交互"""
        return self._pending

    def handle_yn_dialog(self, question: str = None) -> str:
        """
        弹出 Yes/No 对话框 (阻塞)

        Args:
            question: 问题文本

        Returns:
            'y' 或 'n'
        """
        parent = self._parent_widget
        question_text = question or self._current_prompt or "请确认:"

        # 标准化按钮文字
        if 'y' in question_text.lower() and 'n' in question_text.lower():
            pass  # 保持原样
        else:
            question_text = f"{question_text}\n\n请选择:"

        reply = QMessageBox.question(
            parent,
            "用户确认",
            question_text,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        return 'y' if reply == QMessageBox.Yes else 'n'

    def handle_text_dialog(self, prompt: str = None) -> str:
        """
        弹出文本输入对话框 (阻塞)

        Args:
            prompt: 提示文本

        Returns:
            用户输入的文本 (可能为空)
        """
        parent = self._parent_widget
        prompt_text = prompt or self._current_prompt or "请输入:"

        text, ok = QInputDialog.getText(parent, "用户输入", prompt_text)
        return text if ok else ""

    def send_response(self, response: str, write_callback) -> bool:
        """
        将响应写回进程

        Args:
            response: 响应文本
            write_callback: 写入 stdin 的回调函数 (如 process_manager.write_stdin)

        Returns:
            是否成功发送
        """
        try:
            if callable(write_callback):
                write_callback(response)
            self._pending = False
            self._buffer = ""
            self._current_prompt = ""
            self.response_sent.emit(response)
            return True
        except Exception as e:
            print(f"发送响应失败: {e}")
            return False

    def reset(self):
        """重置状态"""
        self._pending = False
        self._buffer = ""
        self._current_prompt = ""
